# Mã hóa, IAM database authentication và quản lý credential

Một ứng dụng Java chạy trên Amazon ECS hoặc AWS Lambda cần truy vấn dữ liệu khách hàng từ **Amazon RDS** hoặc **Amazon Aurora**. Kiến trúc có thể đã đặt database trong private subnet, nhưng vẫn cần trả lời ba câu hỏi khác nhau: **dữ liệu lưu trên đĩa được mã hóa thế nào?**, **kết nối ứng dụng đến database có được bảo vệ không?**, và **ứng dụng chứng minh quyền đăng nhập vào database bằng gì?**. Ba vấn đề lần lượt gắn với **AWS KMS encryption at rest**, **TLS encryption in transit** và **database authentication/authorization**.

Nếu nhầm những cơ chế này, ta dễ tạo hệ thống “đã bật KMS” nhưng ứng dụng gửi thông tin đăng nhập qua một kết nối không xác minh chứng chỉ; hoặc cấp **rds-db:connect** cho một IAM role rồi tưởng role đó được phép đọc mọi bảng SQL; hoặc lưu database password trong source code dù đã có **AWS Secrets Manager** và cơ chế **IAM database authentication**.

Bài học thuộc chương **Cơ sở dữ liệu RDS và Aurora** của mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung gắn lựa chọn Region/AZ, IAM, VPC, compute, storage, database, tích hợp và serverless với yêu cầu triển khai an toàn, giám sát, phục hồi và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **mã hóa at rest**, **TLS in transit**, **IAM database authentication**, **SQL privileges** và **credential rotation**.
2. Giải thích KMS key trong RDS/Aurora, snapshot, backup, read replica, key policy và rủi ro khi vô hiệu hóa khóa.
3. Chọn **AWS managed KMS key** hoặc **customer managed KMS key**, thiết kế backup/cross-Region restore phù hợp.
4. Cấu hình/kiểm tra TLS, server certificate và yêu cầu bắt buộc kết nối mã hóa theo từng database engine.
5. Thiết lập **IAM database authentication** cho MySQL/MariaDB/PostgreSQL trong các biến thể RDS/Aurora được hỗ trợ.
6. Xây IAM policy **rds-db:connect** với đúng **database resource ID + database username**, phân biệt RDS instance/Aurora cluster/RDS Proxy.
7. Sinh và sử dụng **authentication token 15 phút**, phân biệt token với AWS STS credentials và SQL permissions.
8. Quản lý password qua **AWS Secrets Manager**, RDS-managed master credentials, rotation và RDS Proxy.
9. Dùng CLI/SQL/Java để kiểm tra cấu hình, phát hiện các lỗi TLS/KMS/IAM/DB privilege và dự toán chi phí.

## 2. Ba lớp bảo vệ không thể thay thế nhau

| Lớp | Bảo vệ điều gì? | Cơ chế thường dùng | Không giải quyết điều gì? |
|---|---|---|---|
| **At rest** | Database storage, logs, automated backups, snapshots theo phạm vi dịch vụ | RDS/Aurora storage encryption với AWS KMS | Không tự mã hóa traffic TCP; không hạn chế SQL SELECT |
| **In transit** | Dữ liệu và thông tin xác thực qua kết nối client ↔ DB | **TLS**, xác minh CA/hostname, engine settings | Không thay đổi IAM/SQL quyền; không mã hóa disk |
| **Authentication** | Danh tính nào được đăng nhập database | DB password, **IAM database auth**, Kerberos khi được hỗ trợ | Không tự cấp SELECT/INSERT |
| **SQL authorization** | Tài khoản DB được thao tác schema/table/row nào | SQL GRANT, roles, RLS và kiểm soát nghiệp vụ | Không mở VPC security group |
| **Credential lifecycle** | Lưu, cấp phát, xoay vòng, thu hồi bí mật | Secrets Manager, IAM temporary credentials, rotation | Không thay thế TLS và backups |
| **Network isolation** | Ai có thể đi đến endpoint DB trên cổng TCP | VPC security groups, private subnets, route, NACL | Không tự bảo vệ dữ liệu nếu tài khoản DB bị lộ |

~~~mermaid
flowchart LR
    APP["Java API / Lambda / ECS / EKS"] -->|"TLS / IAM token hoặc password"| ENDPOINT["RDS / Aurora endpoint"]
    IAM["IAM role + rds-db:connect"] -. "Cho phép IAM DB login" .-> ENDPOINT
    SECRET["Secrets Manager"] -. "Cấp DB password khi dùng password auth" .-> APP
    SG["VPC security groups"] -. "Giới hạn TCP 3306/5432" .-> ENDPOINT
    ENDPOINT --> STORAGE["RDS / Aurora storage<br/>Encryption at rest"]
    KMS["AWS KMS key"] -. "Bảo vệ storage encryption key" .-> STORAGE
    ENDPOINT --> SQL["Database users, roles,<br/>GRANT và dữ liệu"]
~~~

**Ví dụ:** bật encryption at rest không cho một **Lambda execution role** quyền SQL. Để truy vấn bảng, Lambda phải đi được qua SG/route, thiết lập TLS, đăng nhập bằng cơ chế được cấu hình, rồi tài khoản database cần đúng **GRANT** trên schema/table tương ứng.

## 3. RDS và Aurora: phạm vi mã hóa at rest

### 3.1. RDS storage encryption

Amazon RDS hỗ trợ mã hóa dữ liệu lưu trữ bằng **AWS KMS**, tùy engine và tính năng. Với một **encrypted DB instance**, phạm vi thường bao gồm underlying database storage, transaction logs, automated backups, read replicas và snapshots liên quan theo cơ chế của RDS.

**At-rest encryption** được dịch vụ thực hiện trong đường lưu trữ; ứng dụng vẫn đọc/ghi database bình thường khi được xác thực và cấp quyền SQL. Không phải viết lại truy vấn SQL để AES mã hóa từng hàng. **KMS key là điều kiện bảo vệ dữ liệu lưu trữ**, không phải “mật khẩu database”.

### 3.2. Aurora cluster encryption

Aurora sử dụng **cluster volume** được quản lý, tách phần compute instances khỏi lớp storage phân tán nhiều AZ theo thiết kế dịch vụ. **Aurora cluster encryption** được cấu hình cho cluster và bảo vệ lớp lưu trữ cùng backups/snapshots theo phạm vi AWS hỗ trợ. Các **Aurora writer/reader instances** trong cùng cluster dùng cùng mô hình encrypted cluster storage.

Không nhầm **Aurora cluster encryption** với **IAM database authentication**: một cluster được mã hóa vẫn có thể dùng password auth, IAM auth hoặc các lựa chọn khác theo engine/version. Aurora reader endpoint và writer endpoint cũng không tự thay đổi quyền SQL của user đăng nhập.

### 3.3. Khả năng hỗ trợ theo engine, Region và version

AWS RDS/Aurora có nhiều engine và engine versions. Các thuộc tính **StorageEncrypted**, **KmsKeyId**, **IAMDatabaseAuthenticationEnabled** và các phương án TLS không có nghĩa mọi loại engine hỗ trợ cùng tính năng. Trước khi tạo/chuyển đổi production, kiểm tra hướng dẫn dành riêng cho **RDS MySQL/MariaDB/PostgreSQL, Aurora MySQL/PostgreSQL** hoặc engine cụ thể.

### 3.4. Ba trạng thái không đồng nghĩa

| Trạng thái | Cách hiểu chính xác |
|---|---|
| **StorageEncrypted = true** | RDS/Aurora sử dụng encryption at rest cho tài nguyên đó |
| **KmsKeyId có ARN** | Khóa KMS được chọn để bảo vệ storage, không chứng minh TLS hoặc IAM auth |
| **IAMDatabaseAuthenticationEnabled = true** | IAM database authentication được bật cho instance/cluster hỗ trợ, nhưng vẫn phải tạo/configure database users và IAM permissions |

## 4. AWS KMS key: AWS managed hay customer managed?

### 4.1. So sánh lựa chọn khóa

| Khóa | Ai quản lý key policy và lifecycle? | Khi phù hợp | Cần lưu ý |
|---|---|---|---|
| **AWS managed KMS key** dành cho RDS | AWS quản lý key policy; các giới hạn theo dịch vụ | Muốn encryption at rest với ít thao tác key administration | Không thể tùy chỉnh key policy như customer managed key |
| **Customer managed KMS key** | Tổ chức quyết định IAM/key policy, rotation, trạng thái và truy cập | Compliance, kiểm toán, kiểm soát lifecycle, cross-account snapshot/copy | Sai key policy hoặc disable/delete key có thể làm DB/snapshot không truy cập được |

**Không cần cho mọi Lambda/ECS application role quyền kms:Decrypt đối với RDS storage key chỉ vì ứng dụng chạy SELECT.** RDS sử dụng KMS trong cơ chế mã hóa lưu trữ do dịch vụ quản lý. IAM/KMS permissions cho **lúc tạo, snapshot, restore, copy** và key grants khác với **quyền kết nối SQL**. Chỉ cấp quyền KMS trực tiếp cho client khi client thực sự gọi KMS hoặc đọc một secret/S3 object được mã hóa riêng.

### 4.2. Envelope encryption và grants

~~~mermaid
flowchart TD
    CREATE["Tạo RDS instance / Aurora cluster<br/>StorageEncrypted = true"] --> SELECT["Chọn KMS key"]
    SELECT --> GRANT["RDS tích hợp KMS / grants<br/>theo quyền được cấp"]
    GRANT --> DATA["Encrypted storage, logs,<br/>backup và snapshot"]
    APP["App đã đăng nhập DB"] --> DB["SQL endpoint"]
    DB --> DATA
    CLIENT["Backup/restore operator"] --> ACCESS["IAM/KMS + RDS permissions"]
    ACCESS --> GRANT
~~~

AWS KMS sử dụng **envelope encryption**: key quản lý tại KMS bảo vệ các data keys được dùng ở lớp storage. RDS có thể dùng **KMS grants** khi tạo/khởi động tài nguyên. Khi mã hóa bằng customer managed key, key policy/IAM phải cho phép các thao tác cần thiết; thay đổi thiếu kiểm soát gây lỗi khởi tạo, snapshot hoặc restore.

### 4.3. Rotation không đồng nghĩa đổi sang KMS key ARN khác

- **Automatic KMS key rotation:** thay key material của cùng logical KMS key khi loại key hỗ trợ; dữ liệu trước đó vẫn được giải mã thông qua key phù hợp theo cơ chế KMS.
- **Thay hẳn KMS key của một DB:** không thể đơn giản sửa **KmsKeyId** tại chỗ trên encrypted RDS instance đã tồn tại. Phương án phổ biến là **snapshot → copy snapshot với key đích → restore thành tài nguyên mới**; với các cấu hình **RDS Blue/Green Deployments** được AWS hỗ trợ, cũng có thể tạo **green environment** dùng key mới qua **TargetKmsKeyId** rồi switchover. Cần kiểm tra kỹ engine/version, constraints, quota và backup/rollback trước khi chọn cách này; không áp dụng máy móc cho mọi Aurora cluster.
- **Khóa dùng cho cross-Region replica/backup:** key phải thuộc Region phù hợp của bản sao/restore; kiểm tra khả năng dịch vụ và cơ chế KMS ở từng Region.

**Một KMS key bị disabled hoặc scheduled for deletion** có thể khiến encrypted database, bản sao lưu hay snapshot không truy cập được, gây downtime và mất đường khôi phục. Không xóa key vì thấy “DB đã chuyển sang key mới” mà chưa kiểm kê toàn bộ snapshot, replicas, backups và retention còn dùng key cũ.

## 5. Snapshot, backup, read replica và khôi phục khi đã mã hóa

### 5.1. Backup và snapshot thừa hưởng trạng thái encryption

Một snapshot của database đã encrypted **tiếp tục encrypted**. Khi sao chép snapshot, có thể chọn KMS key đích theo điều kiện dịch vụ; để khôi phục thành database dùng key khác, quy trình phổ biến là **copy encrypted snapshot → restore**. Trong nhiều trường hợp, bạn cũng có thể tạo encrypted copy từ snapshot chưa encrypted, rồi restore thành tài nguyên encrypted; phải kiểm tra khả năng cho từng engine và snapshot type.

### 5.2. Cross-account snapshot sharing

Khi chia sẻ encrypted snapshot sang AWS account khác:

1. Cần **snapshot sharing/restore permissions** theo hỗ trợ RDS/Aurora và tài nguyên.
2. **AWS managed KMS key** không phù hợp với một số luồng chia sẻ encrypted snapshot cross-account do không thể thay key policy.
3. Nếu dùng **customer managed key**, phải cho account đích quyền dùng key phù hợp và copy snapshot với key do account đích quản lý khi cần.
4. Kiểm tra KMS key policy, IAM permissions, Region, snapshot type, database engine và tài nguyên đích.

Không coi snapshot ARN là bằng chứng người khác có quyền decrypt. **RDS snapshot access** và **KMS key access** là hai lớp độc lập.

### 5.3. Read replicas, Multi-AZ và Aurora Global Database

**Read replica** phục vụ đọc và replication theo khả năng engine, không thay thế backup/DR. **RDS Multi-AZ** và **Aurora** cung cấp các mô hình HA riêng; việc bật KMS không tự đảm bảo RPO/RTO. Với **Aurora Global Database** hoặc cross-Region copy/restore, mỗi Region có yêu cầu KMS riêng; cần diễn tập failover/restore và cập nhật endpoint/DNS/secrets khi chuyển vùng.

### 5.4. Encryption và chiến lược khôi phục phải đi cùng nhau

Checklist tối thiểu: snapshot policy, AWS Backup nếu dùng, retention, copy sang Region khác nếu có yêu cầu DR, kiểm tra quyền key ở vùng đích, thử restore có dữ liệu và chứng minh ứng dụng kết nối được bằng TLS + IAM/password auth sau khi khôi phục.

## 6. TLS encryption in transit: bảo vệ mọi kết nối SQL

Kết nối DB trên cổng **3306 (MySQL/MariaDB)** hoặc **5432 (PostgreSQL)** là đường truyền riêng với KMS encryption at rest. Cần dùng **TLS**, xác minh server certificate và hostname thay vì chỉ dựa vào “database trong private subnet”.

### 6.1. Điều cần xác minh ở ứng dụng

| Hạng mục | Mục tiêu |
|---|---|
| **TLS enabled** | Dữ liệu và thông tin đăng nhập được bảo vệ khi truyền |
| **Trusted CA bundle** | Client xác minh certificate chain tới RDS CA phù hợp |
| **Hostname verification** | Chống kết nối nhầm host; dùng RDS/Aurora endpoint hợp lệ |
| **TLS version/ciphers** | Theo chính sách bảo mật và engine version |
| **Certificate rotation** | App/driver tin cậy CA mới trước khi server certificate đổi |
| **DB server enforcement** | Từ chối plaintext connections khi engine hỗ trợ |

AWS cung cấp **RDS truststore bundle** tại trang quản lý CA. Ví dụ đường dẫn CA toàn cục thường được tài liệu AWS sử dụng:

~~~text
https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
~~~

Chỉ tải bundle từ nguồn AWS tin cậy và cập nhật định kỳ. **Không đặt trust-all SSL certificate verifier**, **sslmode=disable**, hoặc tắt hostname verification “cho hết lỗi” trong production.

### 6.2. PostgreSQL: yêu cầu TLS

Với RDS/Aurora PostgreSQL, tham số **rds.force_ssl** trong parameter group được hỗ trợ có thể yêu cầu kết nối TLS. Mặc định và cách áp dụng thay đổi theo engine version/parameter group; hãy đọc **SHOW rds.force_ssl;** và tài liệu phiên bản thay vì suy đoán.

Client PostgreSQL nên dùng **sslmode=verify-full** với CA phù hợp và endpoint đúng:

~~~text
host=db-demo.abcdefg.ap-southeast-1.rds.amazonaws.com
port=5432
sslmode=verify-full
sslrootcert=/secure/path/global-bundle.pem
~~~

**sslmode=require** thường mã hóa kết nối nhưng không luôn kiểm tra danh tính server đầy đủ như **verify-full**. Khi yêu cầu chống MITM, dùng CA và hostname verification, đồng thời kiểm thử khi certificate rotation.

### 6.3. MySQL/MariaDB: TLS và server enforcement

Với RDS MySQL/Aurora MySQL và các engine phù hợp, tham số như **require_secure_transport** có thể bắt buộc TLS; tính năng và mặc định phụ thuộc engine/version. Ở client MySQL tương thích, dùng **ssl-mode=VERIFY_IDENTITY** cùng CA bundle. Không dùng chế độ TLS “accept any server certificate” khi trao đổi credentials.

### 6.4. TLS và IAM auth liên quan thế nào?

**IAM database authentication token** đóng vai trò password trong handshake database. Kết nối cần được bảo vệ đúng quy định engine/AWS; token ngắn hạn không phải lý do bỏ TLS. Một token 15 phút bị lộ vẫn có thể bị dùng trong cửa sổ hiệu lực nếu các điều kiện auth/network cho phép.

## 7. Mật khẩu truyền thống so với IAM database authentication

| Đặc điểm | DB password authentication | IAM database authentication |
|---|---|---|
| Bí mật client dùng | Password do DB/user quản lý | **Temporary auth token** ký theo AWS credentials |
| Chu kỳ sống | Đến khi rotate/expire theo chính sách | Token dùng để **bắt đầu kết nối** có hiệu lực **15 phút** |
| Quản lý vòng đời | Secrets Manager/rotation hoặc hệ thống secret store | IAM role + AWS SDK/CLI sinh token mới |
| Cấp quyền truy cập | DB user/password + SQL grants | **rds-db:connect** trên dbuser ARN + DB user được cấu hình IAM + SQL grants |
| Cách thu hồi | Đổi password, disable DB user, quản lý session | Thu hồi/giới hạn IAM role/DB user; các phiên đã xác thực có thể vẫn sống |
| Kết nối mới ở lưu lượng cao | Phụ thuộc pool/DB limits | Có overhead IAM auth; nên kiểm soát tỷ lệ tạo kết nối |
| Phạm vi engine | Phổ biến theo DB engine | Chỉ những engine/version RDS/Aurora có hỗ trợ |
| Phù hợp | Ứng dụng/driver cần password, proxy với secret, legacy | Workload AWS với IAM role, rotation token tự động, kết nối không quá dồn dập |

**IAM auth không yêu cầu lưu một database password lâu dài trong app** cho user IAM-enabled; ứng dụng tạo token từ AWS credentials tạm thời của execution/task/pod/instance role. Nhưng **user phải tồn tại bên trong database**, được cấu hình kiểu xác thực thích hợp và có **SQL GRANT** tối thiểu. IAM cho phép *đăng nhập*, không tự cấp quyền đọc bảng.

### 7.1. Engine hỗ trợ theo khả năng AWS

IAM database authentication được hỗ trợ cho các engine/version cụ thể của **RDS for MySQL, MariaDB, PostgreSQL** và **Aurora MySQL-/PostgreSQL-compatible**. Nó **không phải tính năng chung cho mọi RDS engine** như SQL Server hoặc Oracle. Các hạn chế đặc biệt với replica, engine version, global databases hoặc một số tính năng có thể thay đổi; đọc tài liệu engine tương ứng trước khi bật.

### 7.2. Token 15 phút có ý nghĩa gì?

**15 phút** là cửa sổ dùng token để thiết lập **kết nối mới** từ thời điểm tạo token; **không phải giới hạn 15 phút cho thời lượng một SQL session đã kết nối thành công**. Sau khi token hết hạn, kết nối đã được DB chấp nhận có thể tiếp tục tồn tại theo timeout/chính sách kết nối DB. Với reconnect hoặc pool tạo connection mới, cần **sinh token mới**.

**Không cache token đến hết ngày** và không dùng một token được tạo khi ứng dụng khởi động rồi tái sử dụng vô hạn. Nếu clock bị lệch, username/hostname/port khác lúc ký, token quá cũ hoặc SDK credentials hết hạn, DB handshake có thể thất bại.

## 8. Luồng IAM database authentication end-to-end

~~~mermaid
sequenceDiagram
    participant APP as Java app / Lambda
    participant IAM as IAM role credentials
    participant SDK as AWS SDK / CLI signer
    participant RDS as RDS / Aurora endpoint
    participant SQL as DB user + grants
    APP->>IAM: Lấy temporary AWS credentials qua role
    APP->>SDK: Sign DB auth token (host, port, username)
    SDK-->>APP: 15-minute auth token
    APP->>RDS: TLS handshake + DB username + token
    RDS->>RDS: Kiểm tra IAM identity / rds-db:connect
    RDS->>SQL: Kiểm tra DB user có IAM auth và quyền SQL
    SQL-->>APP: Authenticated DB connection
    APP->>SQL: SQL SELECT/INSERT theo GRANT
~~~

Các thao tác gọi token API qua SDK/CLI tạo **một presigned authentication string tại client**, không phải một lời gọi AWS API trả về password từ Secrets Manager. Không nên giả định CloudTrail ghi mọi lần tạo token: thao tác **generate-db-auth-token** được tạo cục bộ theo signing mechanism, cần kiểm tra DB login/audit logs và IAM events riêng.

### 8.1. Những điều kiện phải cùng đúng

1. **IAM database authentication** được bật cho DB instance/cluster thích hợp.
2. **IAM principal** có chính xác **rds-db:connect** cho **DB resource ID + username**.
3. **SQL user** đã được tạo và đánh dấu hỗ trợ IAM auth theo engine.
4. **Kết nối TLS**, server endpoint, cổng và Region dùng để ký token chính xác.
5. **Network** từ ứng dụng tới DB: VPC, subnet, SG, NACL, route và DNS cho phép.
6. **SQL GRANT** cho đúng database/schema/table/action.
7. **IAM role credentials** còn hiệu lực và token chưa quá hạn.

**Bật nút IAM auth trong RDS Console chỉ thực hiện điều kiện (1).** Thiếu một trong những điều còn lại vẫn có thể gây lỗi.

## 9. Chính sách IAM rds-db:connect và database resource ID

Với IAM database authentication, quyền kết nối là **rds-db:connect**, không phải **rds:Connect** hay **rds:DescribeDBInstances**. IAM resource sử dụng ARN của loại **dbuser** và **resource ID nội bộ** của instance, Aurora cluster hoặc proxy tùy endpoint được dùng.

### 9.1. ARN phải dùng resource ID, không dùng DB identifier hiển thị

| Trường hợp | Resource ID cần sử dụng | ARN mẫu |
|---|---|---|
| Kết nối trực tiếp RDS DB instance | **DbiResourceId**, thường có tiền tố **db-** | **arn:aws:rds-db:ap-southeast-1:111122223333:dbuser:db-ABCDEFGHIJKLMNOPQRSTU/app_iam** |
| Kết nối trực tiếp Aurora cluster | **DbClusterResourceId**, thường có tiền tố **cluster-** | **arn:aws:rds-db:ap-southeast-1:111122223333:dbuser:cluster-ABCDEFGHIJKLMNOPQRSTU/app_iam** |
| Kết nối thông qua RDS Proxy | **Proxy resource ID**, thường có tiền tố **prx-** | **arn:aws:rds-db:ap-southeast-1:111122223333:dbuser:prx-ABCDEFGHIJKLMNOPQRSTU/app_iam** |

Các chuỗi resource ID trong bảng **chỉ là placeholders**. **DbiResourceId** không phải DB instance identifier như **orders-prod-db**; **DbClusterResourceId** không phải cluster name như **orders-aurora**. Đối với proxy, phải dùng ARN chứa **proxy resource ID** cho IAM client → proxy, không lẫn với ARN cluster cho client → DB.

### 9.2. Identity policy cho Java application role

Ví dụ IAM policy cho một ứng dụng chỉ được đăng nhập **app_iam** trên một RDS instance:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConnectOnlyAsApplicationUser",
      "Effect": "Allow",
      "Action": "rds-db:connect",
      "Resource": "arn:aws:rds-db:ap-southeast-1:111122223333:dbuser:db-ABCDEFGHIJKLMNOPQRSTU/app_iam"
    }
  ]
}
~~~

Nếu ứng dụng kết nối **Aurora cluster**, thay **db-...** bằng **cluster-...** lấy từ cluster thật. Nếu ứng dụng chỉ kết nối **proxy**, dùng **prx-...**. Khi có nhiều database users, liệt kê rõ từng ARN được cấp; đừng dùng **dbuser:*/*** chỉ để giảm thao tác vận hành.

### 9.3. Phân biệt quyền API với quyền kết nối SQL

~~~text
rds:DescribeDBInstances   → đọc metadata DB từ RDS control plane
rds:ModifyDBInstance      → thay cấu hình DB instance
rds-db:connect            → được phép thử đăng nhập bằng IAM DB auth
secretsmanager:GetSecretValue → lấy secret được cấp quyền
kms:Decrypt               → dùng một KMS key cho secret/tài nguyên phù hợp
SQL SELECT/INSERT/UPDATE  → do database role/GRANT quyết định
~~~

Role có **rds-db:connect** không tự được phép gọi **rds:ModifyDBInstance**, và SQL user **app_iam** cũng không tự là database administrator. IAM Database Authentication không hoạt động như một IAM policy cho từng truy vấn SQL.

### 9.4. Lấy resource ID từ AWS CLI (chỉ đọc)

~~~bash
# Instance resource ID.
aws rds describe-db-instances \
  --region ap-southeast-1 \
  --db-instance-identifier orders-prod-db \
  --query 'DBInstances[].{DB:DBInstanceIdentifier,ResourceId:DbiResourceId,Endpoint:Endpoint.Address,IAM:IAMDatabaseAuthenticationEnabled}' \
  --output json

# Aurora cluster resource ID.
aws rds describe-db-clusters \
  --region ap-southeast-1 \
  --db-cluster-identifier orders-aurora \
  --query 'DBClusters[].{Cluster:DBClusterIdentifier,ResourceId:DbClusterResourceId,Endpoint:Endpoint,IAM:IAMDatabaseAuthenticationEnabled}' \
  --output json

# RDS Proxy resource ID nằm trong DBProxyArn, ví dụ phần prx-...
aws rds describe-db-proxies \
  --region ap-southeast-1 \
  --db-proxy-name orders-db-proxy \
  --query 'DBProxies[].{Name:DBProxyName,Arn:DBProxyArn,Endpoint:Endpoint,Status:Status,DefaultAuthScheme:DefaultAuthScheme}' \
  --output json
~~~

Các lệnh chỉ kiểm kê tài nguyên mà bạn được phép xem. Không tự suy database resource ID bằng cách nối tên DB, account và Region; luôn đọc giá trị do API trả về.

## 10. Cấu hình SQL user cho IAM authentication

**Điều kiện tiên quyết:** đã bật IAM database auth trên instance/cluster tương thích; có quyền database administrator theo quy trình tổ chức; IAM role và TLS/network đã chuẩn bị. Các câu lệnh sau **thay đổi database users/permissions**, chỉ chạy trong môi trường được ủy quyền và kiểm tra cú pháp theo engine/version.

### 10.1. RDS/Aurora MySQL: AWSAuthenticationPlugin

MySQL-compatible engine dùng plugin **AWSAuthenticationPlugin** cho IAM-enabled database user. Ví dụ minh họa:

~~~sql
-- Thực thi bởi database administrator trong hệ thống thử nghiệm.
CREATE USER 'app_iam'@'%'
  IDENTIFIED WITH AWSAuthenticationPlugin AS 'RDS';

-- Không cấp quyền trên toàn server; chỉ cấp nhu cầu thật.
GRANT SELECT, INSERT
  ON orders_db.orders
  TO 'app_iam'@'%';
~~~

**Host pattern '%'** chỉ là cú pháp database user matching trong ví dụ; **không có nghĩa được mở SG từ 0.0.0.0/0**. VPC security group vẫn phải chặn đường mạng không cần thiết. Với MariaDB hoặc những engine/version khác, câu lệnh tạo user có thể khác; tham khảo hướng dẫn **Creating a database account using IAM authentication** của đúng engine.

IAM user không nên dùng đồng thời một password lâu dài với một cấu hình plugin không tương thích. Một **IAM role mapping** được cấp đúng cũng không đủ nếu database user **app_iam** chưa được tạo hoặc plugin không được cấu hình.

### 10.2. RDS/Aurora PostgreSQL: role rds_iam

Với PostgreSQL-compatible engine, cấp role **rds_iam** cho database user:

~~~sql
-- Ví dụ chạy với account quản trị DB có quyền cần thiết.
CREATE ROLE app_iam LOGIN;
GRANT rds_iam TO app_iam;

GRANT CONNECT ON DATABASE orders_db TO app_iam;

-- Chạy trong database orders_db, bởi chủ sở hữu schema/table phù hợp.
GRANT USAGE ON SCHEMA public TO app_iam;
GRANT SELECT, INSERT ON TABLE public.orders TO app_iam;
~~~

**rds_iam** điều khiển hình thức xác thực, **không tự cấp SQL SELECT/INSERT**. Một PostgreSQL user có role **rds_iam** có thể ưu tiên IAM auth so với password authentication; không gắn rds_iam tùy tiện cho **master user**, account replication hoặc những user cần password auth cho cơ chế khác. Kiểm tra khả năng engine, replication và RDS Proxy trước khi thay đổi user đang hoạt động.

### 10.3. Đọc lại SQL privileges trước khi cho production traffic

Với PostgreSQL, có thể kiểm tra role membership, schema/table grants qua hệ thống catalog/views phù hợp. Với MySQL, **SHOW GRANTS FOR 'app_iam'@'%';** trả về quyền được cấp. Không chỉ thử “đăng nhập thành công”: phải chứng minh những lệnh không được cấp, ví dụ **DROP TABLE**, thất bại.

## 11. Sinh IAM database authentication token đúng cách

**Authentication token là chuỗi ký SigV4 dùng thay password khi kết nối SQL**, không phải access key hoặc session token của IAM role. Token phải được tạo với **endpoint DNS thật, port, database username và Region** mà kết nối sẽ sử dụng.

### 11.1. AWS CLI: GenerateDBAuthToken

~~~bash
# Lệnh chạy trong shell Bash trên máy có AWS credentials hợp lệ.
# Giá trị placeholder phải thay bằng endpoint database thực.
DB_HOST="orders-prod-db.abcdefg.ap-southeast-1.rds.amazonaws.com"
DB_PORT="5432"
DB_USER="app_iam"

TOKEN="$(aws rds generate-db-auth-token \
  --region ap-southeast-1 \
  --hostname "$DB_HOST" \
  --port "$DB_PORT" \
  --username "$DB_USER")"

# Tuyệt đối không echo TOKEN ra log/ticket.
~~~

**generate-db-auth-token có thể tạo token không cần kiểm tra trước quyền rds-db:connect**; quyền thực sự được kiểm tra khi database authentication handshake xảy ra. Vì thế token được tạo thành công **không chứng minh** ứng dụng có thể login.

**Không thay RDS endpoint bằng CNAME tùy ý** khi sinh token. AWS yêu cầu dùng endpoint tương ứng lúc ký; token và kết nối phải nhất quán về host/port/user. Với **RDS Proxy**, token phải dùng **proxy endpoint** thay vì DB endpoint.

### 11.2. Kết nối PostgreSQL qua psql

Ví dụ trên Bash với **psql**:

~~~bash
# Dùng token từ bước trên; thiết lập TLS verify-full.
PGPASSWORD="$TOKEN" psql \
  "host=$DB_HOST port=$DB_PORT dbname=orders_db user=$DB_USER sslmode=verify-full sslrootcert=/secure/path/global-bundle.pem" \
  -c 'SELECT current_user, now();'

# Xóa biến token sau khi dùng trong lab shell.
unset TOKEN
~~~

**PGPASSWORD** ở đây là biến môi trường tạm thời, không phải vị trí lưu credential dài hạn. Với application production, ưu tiên SDK/driver/credential provider cho mỗi lần tạo connection và cơ chế bảo vệ secrets trong memory. Đừng copy token vào shell history, process arguments, CI/CD logs hoặc report công khai.

### 11.3. Kết nối MySQL-compatible client

Với MySQL client hỗ trợ authentication plugin và TLS:

~~~bash
# Host/cổng MySQL phải khớp token được tạo (port 3306).
mysql \
  --enable-cleartext-plugin \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/secure/path/global-bundle.pem \
  --host=orders-mysql.abcdefg.ap-southeast-1.rds.amazonaws.com \
  --port=3306 \
  --user=app_iam \
  --password
~~~

Client sẽ yêu cầu nhập password; nhập **IAM token vừa tạo cho host/port/user này** bằng cách an toàn, không gõ token trong tham số **--password=TOKEN** vì argument có thể bị lộ qua process list/history. Với một số MySQL driver/versions, cần bật plugin **mysql_clear_password** hoặc cấu hình tương ứng; kiểm tra tài liệu client/runtime cụ thể. Plugin truyền token trong giao thức xác thực **chỉ an toàn khi kết nối TLS được cấu hình và xác minh đúng**.

### 11.4. Tạo token Java bằng AWS SDK for Java 2.x

AWS SDK for Java v2 cung cấp **RdsUtilities.generateAuthenticationToken**. Ví dụ tập trung vào token, không mở JDBC connection:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.rds.RdsClient;
import software.amazon.awssdk.services.rds.RdsUtilities;

public final class RdsTokenFactory {
    private static final Region REGION = Region.AP_SOUTHEAST_1;
    private static final String HOST =
            "orders-prod-db.abcdefg.ap-southeast-1.rds.amazonaws.com";

    public static String createToken(String username, int port) {
        try (RdsClient rds = RdsClient.builder()
                .region(REGION)
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build()) {

            RdsUtilities utilities = rds.utilities();
            return utilities.generateAuthenticationToken(b -> b
                    .hostname(HOST)
                    .port(port)
                    .username(username));
        }
    }

    private RdsTokenFactory() {}
}
~~~

Ví dụ này yêu cầu dependency **software.amazon.awssdk:rds** và các phiên bản SDK tương thích. Token dùng như password khi tạo JDBC connection; **TLS/CA verification**, timeout, validation query và database grants vẫn phải được cấu hình riêng trong JDBC driver/pool.

**Không tạo RdsClient mới cho mỗi SQL statement trong production.** Có thể reuse RdsClient/Utilities hoặc dùng implementation nhẹ theo SDK/driver, và **tạo token mới cho mỗi lần mở physical database connection** khi token cũ sắp hết hạn. Bảo đảm SDK credentials provider chain có thể refresh credentials từ IAM role.

### 11.5. SQL connection pool và token refresh

Một connection pool như **HikariCP** mở **physical connections** ít hơn số lượng SQL statements. Không cần sinh token mới cho mỗi query trên connection đã xác thực. Nhưng nếu connection pool tạo connection mới sau 15 phút hoặc sau failover, token lưu lúc startup không còn hiệu lực.

Hãy sử dụng một cơ chế **credential supplier/token provider động** trên mỗi physical connection creation theo khả năng của JDBC/driver/pool. Nếu pool chỉ nhận một static password, cần chiến lược refresh và tái cấu hình an toàn hoặc cân nhắc **RDS Proxy**. Thử tình huống **idle vượt 15 phút rồi tạo kết nối mới**, network flap và reader/writer endpoint failover.

## 12. Giới hạn IAM DB auth và chiến lược kết nối

AWS khuyến nghị cân nhắc **IAM database authentication** với lưu lượng tạo kết nối mới không quá cao; tài liệu nêu ngưỡng tham khảo **dưới khoảng 200 new IAM-authenticated connections mỗi giây**, và khuyến nghị connection pooling hoặc **RDS Proxy** khi số lần tạo connection mới lớn. Con số này **không phải quota mặc định chính xác cho mọi DB**, mà là ngưỡng thiết kế cần benchmark theo engine, memory và workload.

### 12.1. Bảo vệ database khỏi connection storm

- **Java service chạy lâu:** dùng pool có **maximumPoolSize** vừa phải, idle timeout, connection lifetime, readiness và reconnect backoff.
- **AWS Lambda:** concurrency tăng có thể tạo rất nhiều DB connections; giảm fan-out, kiểm soát Reserved Concurrency, cân nhắc RDS Proxy.
- **ECS/EKS:** HPA scale-out làm tăng pool instances; mỗi Pod có pool 20 và 100 Pods có thể tạo đến **2.000 DB connections**.
- **Aurora cluster:** writer/reader endpoints có vai trò riêng; phân luồng read/write, theo dõi DBConnections và failover.

### 12.2. IAM DB auth có overhead

IAM database authentication dùng thêm memory/CPU cho xử lý xác thực; AWS khuyến nghị quan sát resource usage và có headroom, đặc biệt với instance nhỏ hoặc mật độ kết nối cao. Không bật IAM auth hàng loạt mà chưa xem **Enhanced Monitoring/Performance Insights/Database Insights**, kết nối DB và tải ứng dụng.

### 12.3. Token không phải bằng chứng cấp quyền truy vấn

IAM role có **rds-db:connect** chỉ mở cánh cửa tới một DB username được khai báo. SQL privileges được đánh giá theo **CREATE USER/ROLE, GRANT, RLS và chính sách dữ liệu** trong database. Nếu user chỉ được SELECT, việc dùng token hợp lệ không biến thành quyền DROP hoặc ALTER.

## 13. AWS Secrets Manager: lưu và xoay vòng password

Trong nhiều hệ thống, **password authentication** vẫn phù hợp: legacy drivers, proxy backend, khả năng engine hoặc yêu cầu tích hợp. **AWS Secrets Manager** giúp không hard-code username/password trong source code, AMI, Docker image hoặc file cấu hình chia sẻ.

### 13.1. Secrets Manager quản lý gì?

| Khả năng | Ý nghĩa |
|---|---|
| **Secret value** | Chuỗi JSON như username/password/host/port/dbname |
| **Encryption** | Secret được mã hóa bằng AWS KMS theo chính sách dịch vụ/khóa |
| **IAM/resource policy** | Quy định principal nào được GetSecretValue/PutSecretValue/RotateSecret |
| **Version stages** | **AWSCURRENT, AWSPENDING, AWSPREVIOUS** trong rotation workflow |
| **Rotation** | Tự động đổi password theo lịch/cơ chế hỗ trợ |
| **Audit/monitoring** | CloudTrail quản lý API, CloudWatch/event metrics, cảnh báo thay đổi |

Một secret cho ứng dụng có thể có giá trị JSON theo schema quy ước:

~~~json
{
  "engine": "postgres",
  "host": "orders-prod-db.abcdefg.ap-southeast-1.rds.amazonaws.com",
  "port": 5432,
  "dbname": "orders_db",
  "username": "app_password",
  "password": "PLACEHOLDER_NOT_REAL"
}
~~~

Đây là **ví dụ dữ liệu, không phải thông tin đăng nhập thật**. Secret có thể chỉ lưu username/password nếu endpoint metadata được quản lý ở nơi khác. Không để giá trị password thật trong Git, CI/CD output, CloudWatch Logs, exception stack traces hay bản tài liệu.

### 13.2. RDS-managed master password

RDS/Aurora hỗ trợ hình thức **ManageMasterUserPassword** trên các DB engines/resources được hỗ trợ: AWS RDS tự quản lý master password qua **AWS Secrets Manager**, có thể xoay vòng theo cơ chế tích hợp. Có thể kiểm tra trạng thái **MasterUserSecret** và cấu hình tương ứng qua RDS API.

**Master credentials không nên là credentials của ứng dụng.** Nên tạo một **least-privilege application DB user** riêng, chỉ có quyền cần thiết, với phương án IAM DB auth hoặc secret/rotation phù hợp. Một secret của master được AWS quản lý không tự tạo/rotate password của mọi application user.

### 13.3. Rotation: single-user và alternating-users

| Chiến lược | Cách làm | Trade-off |
|---|---|---|
| **Single-user rotation** | Đổi password của chính database user đang dùng | Đơn giản hơn, nhưng connections mới trong khoảng chuyển đổi có thể lỗi nếu cache chưa cập nhật |
| **Alternating-users rotation** | Hai user tương đương thay phiên, đổi password user không hoạt động rồi chuyển current secret | Giảm cửa sổ không khớp password; cần quản lý grants và privileged rotation user |
| **RDS-managed master rotation** | AWS quản lý master secret theo khả năng tích hợp | Giảm thao tác nhưng app không nên dùng master account |

Secrets Manager rotation thường dùng một **Lambda rotation function** với các bước như **createSecret, setSecret, testSecret, finishSecret**. Không tự viết function rotation chỉ đổi secret mà **quên đổi password trong database**; điều đó tạo lệch trạng thái. Ngoài ra phải có **VPC connectivity** từ rotation Lambda tới DB, IAM đọc/ghi secret và quyền DB cần thiết.

### 13.4. Cache secret nhưng phải refresh

Ứng dụng có thể dùng **AWS Secrets Manager caching client/extension** hoặc cache tự quản lý có TTL để giảm API calls và latency. Nhưng cache quá dài khiến app dùng password cũ sau rotation, dẫn tới lỗi login khi pool reconnect. Thiết kế một **refresh-on-auth-failure** có giới hạn hoặc refresh theo TTL; kiểm thử connection pool khi đổi password và khi RDS failover.

Không gọi Secrets Manager trên **mỗi truy vấn SQL**. Lấy secret khi mở physical DB connection hoặc theo cơ chế cache; tránh gây tăng chi phí API và tạo dependency latency không cần thiết.

## 14. RDS Proxy: kết nối tập trung và hai cách IAM authentication

**Amazon RDS Proxy** cung cấp **proxy endpoint** để pool/manage database connections, giảm tác động của các kết nối ngắn hạn và một số tình huống failover theo engine/tính năng hỗ trợ. Nó không tự cấp SQL permissions hoặc chữa truy vấn chậm. Session state, transaction dài và một số SQL operations có thể khiến connection bị **pinning**, làm giảm khả năng multiplexing.

### 14.1. Standard IAM và end-to-end IAM khác nhau

| Chế độ | Client → Proxy | Proxy → Database | Database secret trong Secrets Manager |
|---|---|---|---|
| **Standard IAM auth** | IAM token ký cho proxy endpoint | Password authentication | **Cần** để proxy truy cập DB |
| **End-to-end IAM auth** | IAM token ký cho proxy endpoint | IAM database authentication | **Không cần DB password secret** cho luồng này |

AWS hiện hỗ trợ **end-to-end IAM authentication** cho RDS Proxy với các engine thuộc họ **MySQL, MariaDB và PostgreSQL** khi cấu hình/Region/version đáp ứng điều kiện. Hãy kiểm tra **DefaultAuthScheme** của proxy; một proxy đã tồn tại không tự chuyển sang end-to-end chỉ vì client dùng IAM auth.

~~~mermaid
flowchart TD
    APP["Java Lambda / ECS / EKS"] -->|"TLS + IAM token"| PROXY["RDS Proxy endpoint"]
    PROXY --> MODE{"Authentication scheme"}
    MODE -->|"Standard IAM"| SM["Secrets Manager<br/>DB password"]
    SM --> DB["RDS / Aurora"]
    MODE -->|"End-to-end IAM"| ROLE["Proxy IAM role<br/>rds-db:connect DB user"]
    ROLE --> DB
    DB --> SQL["SQL roles / GRANT<br/>business authorization"]
~~~

### 14.2. Quyền khác nhau giữa app và proxy

Trong cả hai mode với IAM client authentication, **application IAM role** phải có **rds-db:connect** trên ARN chứa **proxy resource ID prx-.../db_user**, và token phải ký cho **hostname của proxy**, không phải hostname DB instance.

Với **standard mode**, **proxy IAM role** được cấp **secretsmanager:GetSecretValue** và KMS permissions thích hợp để lấy DB password; ứng dụng không nhất thiết cần đọc secret. Với **end-to-end mode**, proxy IAM role cần **rds-db:connect tới database resource ID**, database user phải hỗ trợ IAM auth, và secrets không còn bắt buộc cho DB password ở đường đó. Đây là **hai principal** và hai bước authorization khác nhau.

### 14.3. TLS và kết nối bị pinning

RDS Proxy sử dụng cơ chế TLS/certificate riêng được AWS quản lý, có thể khác với việc client tin CA trực tiếp của RDS DB endpoint. Cần dùng **TLS** và kiểm tra cách xác minh endpoint, CA, **RequireTLS** theo tài liệu proxy. Connection pool giúp tái sử dụng kết nối nhưng không làm biến mất **long transactions, session variables, temp tables hoặc queries chậm**; quan sát **DatabaseConnections**, **ClientConnections**, **SessionPinnedConnections**, **DatabaseConnectionsBorrowLatency** và backend query latency.

### 14.4. Khi nào nên dùng proxy?

Đặc biệt cân nhắc **Lambda concurrency burst**, microservices với nhiều pool nhỏ, short-lived instances hoặc failover gây reconnect. Với một Java service lâu dài có pool tốt và số kết nối thấp, proxy chưa chắc đáng chi phí; cần benchmark latency, connection counts, memory và proxy charge.

## 15. IAM, SQL, KMS và Secrets Manager: ma trận principal

| Principal/lớp | IAM DB auth trực tiếp | DB password từ Secrets Manager | IAM qua RDS Proxy |
|---|---|---|---|
| **App IAM role** | **rds-db:connect** trên DB user ARN | **secretsmanager:GetSecretValue** + secret KMS permissions nếu cần | **rds-db:connect** trên proxy dbuser ARN |
| **Database user** | IAM plugin/rds_iam + **SQL GRANT** | Password + **SQL GRANT** | Auth method tương thích mode của proxy + SQL GRANT |
| **RDS Proxy IAM role** | Không cần khi kết nối trực tiếp | Không liên quan nếu app tự đọc secret | Secret read/KMS với standard; **rds-db:connect DB** với end-to-end |
| **RDS/KMS storage integration** | Storage encryption do RDS quản lý | Không phải database password | Không thay đổi bởi việc dùng proxy |
| **DB administration role** | Quản lý DB parameters/users/privileges | Quản lý rotation và DB user | Quản lý proxy/targets và IAM config |
| **Backup operator** | Snapshot/RDS + KMS restore permissions | Không cần password để chỉ copy encrypted snapshot | Không phụ thuộc proxy |

### 15.1. IAM policy đọc một secret được cấp quyền

Ví dụ cho một application role **chỉ dùng password auth** và secret được mã hóa bằng customer managed KMS key:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOneDbSecret",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:orders/app-db-REPLACE_SUFFIX"
    },
    {
      "Sid": "DecryptOnlySecretKey",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_SECRET_KEY_ID",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "secretsmanager.ap-southeast-1.amazonaws.com"
        }
      }
    }
  ]
}
~~~

Trong ví dụ, **REPLACE_SUFFIX** và **REPLACE_SECRET_KEY_ID** phải là giá trị thực do hệ thống trả về. KMS key policy cần cho phép quyền tương ứng; nếu secret dùng AWS managed key, quyền cần thiết có thể khác. **KMS key của Secrets Manager không nhất thiết là KMS key dùng mã hóa RDS storage**.

### 15.2. Runtime role phải phù hợp ứng dụng

- **Lambda:** execution role; không lưu IAM user access key trong environment variables.
- **ECS/Fargate:** **task role** cho Java SDK; đừng nhầm với task execution role dùng cho ECR/log setup.
- **EKS:** EKS Pod Identity hoặc IRSA theo service account và khả năng hỗ trợ; tránh dùng node role chung.
- **EC2:** instance profile, IMDSv2 và chính sách least privilege.

IAM policy vẫn chịu SCP, permissions boundary và explicit Deny. Một IAM **Allow rds-db:connect** không thắng **SQL user chưa tồn tại, TLS xác minh thất bại hoặc SG chặn port 5432**. Điều tra đúng lớp thay vì mở IAM wildcard.

## 16. Kiến trúc ứng dụng Java bảo mật theo nhiều lớp

### 16.1. Java API trên ECS với IAM DB auth

~~~mermaid
flowchart TB
    USER["Client"] --> ALB["ALB HTTPS"]
    ALB --> ECS["ECS Java API<br/>Private subnets nhiều AZ"]
    ROLE["ECS task role<br/>rds-db:connect cho app_iam"] -. "SigV4 auth token" .-> ECS
    ECS -->|"TLS verify-full + IAM auth"| DB["RDS / Aurora endpoint<br/>Private DB subnets"]
    SG["DB Security Group:<br/>3306/5432 chỉ từ ECS SG"] -. "TCP authorization" .-> DB
    DB --> STORAGE["Encrypted storage / backups<br/>AWS KMS key"]
    ECS --> LOG["CloudWatch Logs / traces"]
    DB --> MON["RDS metrics / DB logs"]
~~~

**Ưu điểm:** ứng dụng không cần giữ database password dài hạn; credentials IAM role có vòng đời quản lý qua ECS. **Đánh đổi:** Java pool phải biết tạo token mới khi mở physical connection, và SQL DB user **app_iam** phải có GRANT tối thiểu.

### 16.2. Java Lambda qua RDS Proxy, proxy dùng secret

~~~mermaid
flowchart LR
    API["API Gateway"] --> FN["Lambda Java"]
    FN -->|"TLS + IAM auth token"| PROXY["RDS Proxy"]
    ROLE["Lambda execution role<br/>rds-db:connect proxy ARN"] -. "IAM" .-> FN
    PR["Proxy IAM role"] -->|"GetSecretValue"| SM["Secrets Manager<br/>DB password rotation"]
    PROXY -->|"Password tới DB"| DB["RDS / Aurora"]
    DB --> KMS["KMS encrypted storage"]
~~~

Đây là **standard IAM authentication** qua RDS Proxy. Với **end-to-end IAM** được hỗ trợ, proxy dùng IAM DB auth để vào database và không cần DB password secret cho luồng này. Không phải mọi môi trường đều nên bật end-to-end: phải kiểm tra driver, proxy configuration, SQL user setup, IAM role và yêu cầu vận hành.

### 16.3. Network và availability vẫn quan trọng

Database có thể đã encrypted và IAM auth bật, nhưng ứng dụng vẫn phải đi qua **VPC networking**: đúng endpoint, private DNS, security group source, port, NACL và routing. Với RDS Multi-AZ/Aurora, failover có thể làm mất TCP sessions; client phải **reconnect, refresh DNS, retry có giới hạn và giữ idempotency**.

**Multi-AZ không phải DR Multi-Region.** Nếu yêu cầu cấp Region, cần backup/cross-Region copy/global database theo engine, KMS key ở Region đích, DNS/app endpoint update và diễn tập khôi phục.

### 16.4. Lựa chọn endpoint

| Endpoint | Khi dùng | Điều chú ý |
|---|---|---|
| **DB instance endpoint** | Trực tiếp RDS DB | IAM token ký host/port của DB instance |
| **Aurora writer cluster endpoint** | Đọc/ghi | Thay writer khi failover, pool cần reconnect |
| **Aurora reader endpoint** | Read-only workloads | Chấp nhận replica lag theo kiến trúc |
| **RDS Proxy endpoint** | Pool/reconnect theo tính năng | IAM token ký proxy endpoint; IAM dbuser ARN có proxy resource ID |

**Đừng dùng CNAME tùy ý để ký IAM database token** nếu yêu cầu endpoint thực của AWS. Với IAM auth và TLS hostname verification, host mà ứng dụng kết nối, host được ký token và chứng chỉ phải tương thích theo tài liệu chính thức.

## 17. AWS CLI kiểm kê mã hóa, IAM auth và secret (read-only)

Các lệnh sau **chỉ đọc trạng thái**, không sửa AWS resources. Thay Region, identifiers và ARNs giả định bằng tài nguyên được phép của bạn. Sử dụng IAM principal có quyền **Describe** hạn chế thay vì administrator credentials.

### 17.1. Kiểm tra RDS DB instance

~~~bash
aws sts get-caller-identity --output json

aws rds describe-db-instances \
  --region ap-southeast-1 \
  --db-instance-identifier orders-prod-db \
  --query 'DBInstances[].{Name:DBInstanceIdentifier,Engine:Engine,Version:EngineVersion,Encrypted:StorageEncrypted,KmsKey:KmsKeyId,IAMAuth:IAMDatabaseAuthenticationEnabled,ResourceId:DbiResourceId,Endpoint:Endpoint.Address,CA:CACertificateIdentifier}' \
  --output json
~~~

### 17.2. Kiểm tra Aurora DB cluster

~~~bash
aws rds describe-db-clusters \
  --region ap-southeast-1 \
  --db-cluster-identifier orders-aurora \
  --query 'DBClusters[].{Name:DBClusterIdentifier,Engine:Engine,Encrypted:StorageEncrypted,KmsKey:KmsKeyId,IAMAuth:IAMDatabaseAuthenticationEnabled,ResourceId:DbClusterResourceId,Writer:Endpoint,Reader:ReaderEndpoint,MasterSecret:MasterUserSecret}' \
  --output json
~~~

**StorageEncrypted = true** không chứng minh TLS được yêu cầu. **IAMAuth = true** không chứng minh SQL user đã có quyền phù hợp. Cần xem DB parameter groups, thử xác thực bằng user được phép và SQL GRANT.

### 17.3. Kiểm tra KMS key state

~~~bash
aws kms describe-key \
  --region ap-southeast-1 \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_STORAGE_KEY_ID \
  --query 'KeyMetadata.{Arn:Arn,State:KeyState,Enabled:Enabled,KeyManager:KeyManager,DeletionDate:DeletionDate}' \
  --output json
~~~

Nếu key đang **Disabled/PendingDeletion**, phải theo quy trình bảo vệ dữ liệu ngay. Không tự tạo key ARN mới và cho rằng storage của DB đang dùng key cũ đã chuyển sang key mới. **KMS DescribeKey** là đọc metadata, không chứng minh mọi RDS restore/snapshot permission có hiệu lực.

### 17.4. Kiểm tra secret metadata mà không đọc password

~~~bash
aws secretsmanager describe-secret \
  --region ap-southeast-1 \
  --secret-id orders/app-db \
  --query '{Name:Name,Arn:ARN,KmsKey:KmsKeyId,RotationEnabled:RotationEnabled,RotationRules:RotationRules,LastChanged:LastChangedDate,LastRotated:LastRotatedDate}' \
  --output json

aws secretsmanager list-secret-version-ids \
  --region ap-southeast-1 \
  --secret-id orders/app-db \
  --query 'Versions[].{VersionId:VersionId,Stages:VersionStages,Created:CreatedDate}' \
  --output json
~~~

**Không dùng get-secret-value trong ví dụ kiểm toán** để tránh vô tình in secret vào CLI log, ticket hoặc màn hình chia sẻ. Nếu cần xác minh password thực sự, sử dụng quy trình truy cập secret được phép và bảo vệ output.

### 17.5. Kiểm tra RDS Proxy auth mode và health

~~~bash
aws rds describe-db-proxies \
  --region ap-southeast-1 \
  --db-proxy-name orders-db-proxy \
  --query 'DBProxies[].{Name:DBProxyName,Arn:DBProxyArn,Status:Status,Endpoint:Endpoint,RequireTLS:RequireTLS,DefaultAuthScheme:DefaultAuthScheme,Auth:Auth}' \
  --output json

aws rds describe-db-proxy-targets \
  --region ap-southeast-1 \
  --db-proxy-name orders-db-proxy \
  --target-group-name default \
  --output json
~~~

Output **Auth** có thể chứa thông tin cấu hình secret ARN/user mappings; giữ trong phạm vi người có quyền vận hành. Đối chiếu **DefaultAuthScheme** để phân biệt standard IAM và end-to-end IAM, không tự suy từ tên proxy.

### 17.6. Kiểm tra TLS parameters đúng engine

Trong PostgreSQL, cần kiểm tra **rds.force_ssl**; với MySQL/Aurora MySQL có thể có **require_secure_transport**. Đọc đúng **DB parameter group hoặc Aurora DB cluster parameter group**, vì nơi đặt tham số khác theo engine/version.

~~~bash
# Đọc metadata tham số từ một DB parameter group đã biết.
aws rds describe-db-parameters \
  --region ap-southeast-1 \
  --db-parameter-group-name orders-db-params \
  --query 'Parameters[].{Name:ParameterName,Value:ParameterValue,ApplyMethod:ApplyMethod,Source:Source}' \
  --output json

# Với tham số cấp Aurora cluster:
aws rds describe-db-cluster-parameters \
  --region ap-southeast-1 \
  --db-cluster-parameter-group-name orders-aurora-cluster-params \
  --query 'Parameters[].{Name:ParameterName,Value:ParameterValue,ApplyMethod:ApplyMethod,Source:Source}' \
  --output json
~~~

Không sửa parameter group production cho đến khi xác định chính xác **parameter family, tính động/tĩnh, trạng thái pending-reboot và maintenance window**. Việc bắt buộc TLS có thể khiến legacy clients không kết nối được nếu họ chưa có CA bundle/truststore phù hợp.

## 18. Runbook chẩn đoán: không gom mọi lỗi vào AccessDenied

Một yêu cầu SQL có thể lỗi ở **network, TLS, IAM, database auth, SQL permission, secret rotation, KMS storage key hoặc query/runtime**. Mỗi lớp có cách kiểm chứng riêng.

~~~mermaid
flowchart TD
    A["App không truy vấn được RDS / Aurora"] --> B{"Lỗi xảy ra ở giai đoạn nào?"}
    B -->|"Timeout / DNS"| NET["VPC/SG/route/endpoint<br/>DB instance, cluster hay proxy?"]
    B -->|"TLS / x509"| TLS["CA chain, hostname,<br/>certificate, sslmode"]
    B -->|"Authentication failed"| AUTH["DB user/plugin/rds_iam<br/>IAM role rds-db:connect<br/>token expiry và host ký"]
    B -->|"SQL permission denied"| SQL["SQL GRANT, schema/table,<br/>RLS, owner, tenant"]
    B -->|"Secrets/KMS error"| KEY["Secret rotation/stages<br/>KMS key policy/state"]
    NET --> FIX["Chỉ sửa đúng lớp lỗi<br/>kiểm thử trong staging"]
    TLS --> FIX
    AUTH --> FIX
    SQL --> FIX
    KEY --> FIX
    FIX --> VERIFY["Xác nhận TLS, login, SQL grants,<br/>p95 latency và không lộ secret"]
~~~

### 18.1. Bảng triệu chứng và nguyên nhân thường gặp

| Triệu chứng | Nguyên nhân có thể | Bước điều tra đầu tiên |
|---|---|---|
| **Connection timeout** trước khi login | DB endpoint/port sai, SG/NACL/route/DNS, database unavailable | Kiểm tra endpoint thật, DB status, TCP path từ đúng workload subnet |
| **Connection refused** | Wrong port, DB process/target down, proxy target unhealthy | DB/proxy status, engine port, target health |
| **SSL certificate verify failed** | Truststore thiếu CA, hostname không khớp, cert rotation | CA bundle, JDBC/psql sslmode, endpoint được ký |
| **IAM token tạo được nhưng login bị từ chối** | IAM policy sai dbuser ARN, token ký sai host/port/Region, DB IAM auth chưa bật | DbiResourceId/DbClusterResourceId, token age, DB user config |
| **IAM token hết hạn 15 phút** | Pool tái dùng token tạo từ startup cho new connections | Dynamic token generation, physical pool connection creation |
| **MySQL Access denied for user** | User/plugin sai, IAM/KMS? role thiếu, host matching hoặc token không hợp lệ | AWSAuthenticationPlugin, rds-db:connect, username/host/TLS |
| **PostgreSQL PAM authentication failed** | Role rds_iam hoặc IAM authorization không tương thích | SQL role membership, IAM policy, TLS, endpoint |
| **Đăng nhập thành công nhưng SELECT bị từ chối** | Thiếu SQL GRANT/schema permission/RLS | SQL user, table/schema grants, app tenant context |
| **Password login lỗi sau rotation** | Cache chưa refresh, secret AWSCURRENT khác DB user password | Secret stages, rotation logs, connection pool refresh |
| **SecretsManager AccessDenied** | Role thiếu GetSecretValue, resource policy hoặc SCP Deny | App task/execution role và secret ARN chính xác |
| **KMS AccessDenied khi đọc secret** | Secret CMK không cho kms:Decrypt hoặc key policy/boundary chặn | Phân biệt KMS key của secret với storage key |
| **RDS inaccessible-encryption-credentials** | Storage KMS key disabled/unavailable | KMS key state, RDS event, runbook phục hồi khóa |
| **RDS Proxy authentication error** | Token ký DB hostname thay proxy, ARN dbuser sai, standard/end-to-end config sai | Proxy endpoint, DefaultAuthScheme, role/secret/DB user |
| **RDS Proxy connection borrow timeout** | Proxy pool/DB quá tải hoặc session pinning | Proxy metrics, DBConnections, long transactions |
| **Nhiều lỗi sau Multi-AZ failover** | Connections cũ, DNS caching, TLS/reconnect, app retry storm | DB events, pool lifetime, DNS, retry/backoff |
| **Query chậm dù IAM/KMS đúng** | Lock/contention, thiếu index, CPU/IO, DB capacity | Database Insights/Performance Insights, SQL EXPLAIN, CloudWatch |
| **Restore snapshot cross-account thất bại** | Snapshot share permission, KMS key policy/Region, encrypted key type | Snapshot ARN/owner, KMS key permissions, destination Region |

### 18.2. Quy trình khi IAM DB login thất bại

1. Xác định ứng dụng dùng **direct DB** hay **RDS Proxy** và lấy hostname/port thực tế.
2. Dùng **aws sts get-caller-identity** ngay trong runtime được phép để biết IAM role ARN thật.
3. Đọc **IAMDatabaseAuthenticationEnabled** và resource ID của instance/cluster/proxy.
4. So policy **rds-db:connect** với **dbuser:RESOURCE_ID/username**; không thay bằng DB identifier.
5. Kiểm tra DB user: **AWSAuthenticationPlugin** cho MySQL-compatible, **rds_iam** cho PostgreSQL.
6. Tạo lại token với host/port/user/Region thực, kiểm tra đồng hồ và AWS credentials còn hạn.
7. Kết nối TLS có CA và hostname verification; nếu lỗi, ghi nhận error/trace đã **redact token**.
8. Khi login thành công, chạy một SQL SELECT tối thiểu được phép rồi kiểm tra truy vấn thật/SQL GRANT.

**Không log toàn bộ token** để debug. Token IAM dài, chứa thông tin định danh/chữ ký và có giá trị trong thời gian ngắn; log có thể trở thành nguồn lộ quyền. Chỉ ghi metadata an toàn như thời gian tạo token, endpoint alias nội bộ, username đã kiểm soát, error code và trace ID.

### 18.3. Quy trình khi Secrets Manager rotation gây lỗi

1. Kiểm tra secret **RotationEnabled**, **LastRotatedDate**, **VersionStages AWSCURRENT/AWSPENDING**; không đọc SecretString qua kênh công khai.
2. Kiểm tra rotation Lambda/managed rotation status, VPC/SG, DB user permissions và KMS key của secret.
3. Xác minh app cache TTL, thời điểm tạo DB connections và driver/connection pool có refresh không.
4. Thử tạo **kết nối mới** trong staging bằng secret version current, tránh khiến production thêm tải.
5. Nếu rotation bị kẹt, xử lý theo runbook của Secrets Manager/RDS; không tự di chuyển AWSCURRENT hoặc thay password thủ công mà chưa đối chiếu DB.
6. Sau khi sửa, kiểm tra login thành công, old connections, error rate và cảnh báo rotation kế tiếp.

### 18.4. Khi storage KMS key bị disable

Đây là một **sự cố độ sẵn sàng nghiêm trọng**, không phải lỗi password. Tình trạng của encrypted RDS DB có thể chuyển sang trạng thái **inaccessible-encryption-credentials-recoverable** hoặc trạng thái terminal khác tùy điều kiện DB, backup và engine. AWS mô tả một số instance có cửa sổ phục hồi giới hạn; quy trình khác nhau cho Aurora, read replicas và những tài nguyên không thể stop.

**Không xóa snapshot, key hoặc grants** khi chưa xác minh. Ưu tiên điều tra **KeyState, RDS events, key owner/account/Region**; nếu được phép, khôi phục trạng thái key theo runbook chính thức và xác minh database health. Khi không thể khôi phục instance, dùng bản backup/snapshot còn giải mã được theo kế hoạch DR. Không đưa ra lời hứa “bật key lại chắc chắn DB hoạt động ngay” cho mọi engine/trạng thái.

## 19. Giám sát, audit và phản ứng sự cố

### 19.1. Nguồn số liệu cần duy trì

| Nguồn | Theo dõi gì? | Vì sao quan trọng |
|---|---|---|
| **CloudWatch RDS metrics** | DatabaseConnections, CPUUtilization, FreeableMemory, FreeStorageSpace, IOPS, Read/WriteLatency | Phát hiện kết nối tăng đột ngột và suy giảm tài nguyên |
| **Database Insights / Performance Insights** | DB load, waits, SQL bottlenecks theo tính năng được cung cấp | Phân biệt auth overhead với query chậm |
| **Enhanced Monitoring** | OS-level CPU/memory/process metrics | Điều tra memory overhead, saturation |
| **RDS/Aurora events** | Failover, maintenance, snapshot, key access issues | Phục hồi và RCA |
| **Database engine logs** | Login failures, TLS/auth problems, slow queries theo cấu hình | IAM auth/SQL errors không luôn nằm ở AWS control plane |
| **Secrets Manager rotation status** | Rotation success/failure, version stages, last rotated | Tránh credential mismatch |
| **KMS/CloudTrail** | Key state changes, grant changes, KMS APIs, IAM/RDS control plane activity | Audit mã hóa và quyền key |
| **RDS Proxy metrics** | ClientConnections, DatabaseConnections, BorrowLatency, pinned sessions | Phát hiện connection storms |
| **Application traces** | JDBC connection wait, auth retry, query latency, pool errors | Kết nối triệu chứng người dùng với backend |

**CloudTrail là công cụ audit AWS APIs**, không phải một bộ ghi mọi câu SQL hoặc mọi lần login IAM DB auth mặc định. **generate-db-auth-token** tạo token SigV4 tại phía client; không thể dựa vào CloudTrail để đếm số token người dùng đã tạo. Muốn kiểm toán SQL login/query, cần database-specific audit/logging theo engine và chính sách bảo mật.

### 19.2. Alerts nên có

- Tăng đột ngột **DBConnections**, **DatabaseConnectionsBorrowLatency**, application connection timeouts hoặc login failures.
- **Secret rotation failed/impaired** hoặc quá hạn xoay vòng theo lịch đã duyệt.
- **KMS key disabled/pending deletion**, thay đổi key policy/grants, snapshot restore AccessDenied.
- Bản cập nhật **parameter group** làm thay đổi yêu cầu TLS.
- Tăng **RDS/Aurora failover events**, replication lag, storage saturation.
- Thay đổi IAM policies có **rds-db:connect**, **secretsmanager:GetSecretValue**, **kms:Decrypt**, **rds:ModifyDBInstance/Cluster**.

Không dùng một ngưỡng alert duy nhất cho mọi loại workload. Một batch job dùng 500 short-lived connections khác với API giao dịch yêu cầu p99 thấp. Cần xác định SLO, business hours và ngưỡng theo mức nền thực tế.

### 19.3. Chú ý secrets trong telemetry

Không log **database password, IAM auth token, Secrets Manager SecretString, JDBC connection URL có password, Authorization header, private key hoặc data payload nhạy cảm**. Khi lỗi xảy ra, exception message có thể chứa connection details; áp dụng redaction, phân quyền đọc log và retention theo yêu cầu.

## 20. Chi phí và cách chọn phương án

**Mã hóa và quản lý credential** không chỉ có phí KMS. Hệ thống còn trả cho compute/storage, Multi-AZ, replicas, snapshots, secrets, proxy, CloudWatch và network. Tổng chi phí cần tính theo **TCO + SLO**, không chỉ tiền cho từng API.

| Thành phần | Chi phí/ảnh hưởng cần xem |
|---|---|
| **RDS/Aurora compute/storage/I/O** | Instance hoặc ACU, storage mode, provisioned IOPS, I/O requests theo engine |
| **Multi-AZ, replicas, global database** | HA/DR capacity, replication, data transfer và lưu trữ bổ sung |
| **AWS KMS customer managed key** | Phí key/month, request volume, key rotation/storage theo loại key |
| **RDS encryption at rest** | Chi phí KMS và resources liên quan; không nhầm với client-side encryption |
| **Secrets Manager** | Phí theo số secrets và API calls/rotation theo giá hiện hành |
| **Rotation Lambda** | Invocations/duration, private networking, logging |
| **RDS Proxy** | Phí proxy capacity theo mô hình pricing hiện hành |
| **CloudWatch/Database Insights** | Logs, metrics, retention, tính năng phân tích có phí |
| **VPC network endpoints** | Interface endpoints, private networking và data processing |
| **Backup/restore** | Snapshot retained storage, cross-Region copies, data transfer |

### 20.1. Ba mô hình tối ưu tham khảo

| Mô hình | Khi phù hợp | Lưu ý |
|---|---|---|
| **IAM DB auth trực tiếp** | Java service có connection pool ổn định và IAM role rõ ràng | Refresh token khi tạo physical connection, benchmark tỷ lệ new connections |
| **Secrets Manager + DB password** | Legacy clients, engine/driver không hỗ trợ IAM auth | Rotation/cache, quyền GetSecretValue và secret KMS policy |
| **RDS Proxy + IAM client** | Lambda/containers scale-out, nhiều short-lived connections | Có phí proxy, phải chọn standard hoặc end-to-end IAM mode đúng |

**IAM auth không mặc nhiên rẻ hơn Secrets Manager** nếu phải thêm proxy, viết dynamic JDBC token provider và vận hành phức tạp. Ngược lại, nhiều secrets/passwords tự quản lý có thể tăng rủi ro và chi phí sự cố. Benchmark **latency, số connections, throughput, chi phí và mức độ vận hành**.

### 20.2. Quyết định về key policy và snapshot

Nếu compliance yêu cầu customer-managed key và backup liên account/Region, lên kế hoạch KMS keys ngay từ lúc thiết kế. Chuyển key sau khi có dữ liệu production có thể phải tạo snapshot/copy/restore hoặc Blue/Green được hỗ trợ, dẫn tới thêm storage, tài nguyên chuyển tiếp và công kiểm thử.

## 21. Bài tập tình huống

### Tình huống A — KMS đã bật nhưng client vẫn gửi password không an toàn

RDS PostgreSQL có **StorageEncrypted = true** và customer-managed KMS key. Một ứng dụng Java dùng database password nhưng JDBC connection string tắt SSL validation, chỉ mở TCP 5432 từ private subnet.

**Yêu cầu:** giải thích hai lỗ hổng và đề xuất cách sửa.

**Gợi ý:** KMS bảo vệ **at rest**, không bảo vệ dữ liệu trên đường truyền. Bật TLS với **verify-full**, CA truststore/hostname hợp lệ, cân nhắc **rds.force_ssl** và kiểm thử ứng dụng. Sau đó xem **Secrets Manager/rotation** thay vì hard-code password; SG private không thay thế TLS.

### Tình huống B — Lambda có rds-db:connect nhưng không đăng nhập được

Một Lambda Java dùng IAM auth tới Aurora PostgreSQL. Role có:

~~~text
arn:aws:rds-db:ap-southeast-1:111122223333:dbuser:db-EXAMPLE/app_iam
~~~

Trong khi cluster trả **DbClusterResourceId = cluster-REAL_ID**.

**Yêu cầu:** tìm lỗi và đề xuất policy.

**Gợi ý:** đang dùng **db-...** của một instance thay vì **cluster-...** cho kết nối Aurora cluster. Kiểm tra cluster resource ID thật, role **rds-db:connect** trên đúng **dbuser:cluster-REAL_ID/app_iam**, cấu hình PostgreSQL **GRANT rds_iam**, TLS, token/endpoint và SQL GRANT.

### Tình huống C — HikariCP hoạt động ban đầu rồi lỗi sau 15 phút

ECS service tạo IAM token một lần lúc start và gán nó làm password cố định cho HikariCP. Những connections ban đầu hoạt động; sau một thời gian autoscaling/reconnect, app nhận authentication failures.

**Yêu cầu:** vì sao các SQL sessions cũ vẫn chạy mà connections mới lỗi?

**Gợi ý:** token có hiệu lực **15 phút để thiết lập connection mới**, không giới hạn ngay các sessions đã đăng nhập. Dùng dynamic token provider khi tạo physical connection, kiểm tra AWS credentials provider refresh và TLS. Với burst scale lớn, cân nhắc **RDS Proxy**.

### Tình huống D — Secrets Manager rotation xong nhưng API trả 500

Java service đọc password từ secret khi khởi động, cache vĩnh viễn và tạo DB connections mới sau mỗi autoscaling event. Secrets Manager rotation đã thay password DB.

**Yêu cầu:** cải thiện ứng dụng mà không tắt rotation.

**Gợi ý:** dùng cache TTL/refresh-on-auth-failure, kiểm tra stages **AWSCURRENT/AWSPENDING**, DB password thực, pool reconnect và rotation Lambda logs. Không chạy **GetSecretValue cho mỗi SQL query**, cũng không tự rollback secret stages mà thiếu kiểm tra DB.

### Tình huống E — Đổi KMS key rồi không restore được snapshot cũ

Một RDS instance từng dùng **K1**, đội vận hành copy snapshot với **K2** để restore DB mới rồi schedule deletion của **K1**. Sau vài tuần cần restore một snapshot cũ chưa copy sang K2.

**Yêu cầu:** sai sót ở đâu?

**Gợi ý:** snapshot cũ còn phụ thuộc K1. Phải kiểm kê tất cả snapshots/backups/replicas/cross-account copies, khả năng decrypt và retention trước khi disable/delete K1. Tập diễn tập restore và kiểm tra KeyState, IAM/KMS policy, không suy rằng đổi DB key tự mã hóa lại mọi backup cũ.

### Tình huống F — Lambda bùng nổ kết nối tới RDS

API Gateway kích hoạt hàng trăm Lambda Java instances đồng thời, mỗi instance tạo nhiều DB connections. Database có CPU và DatabaseConnections tăng, user-facing latency p99 xấu đi, IAM authentication cũng tạo thêm overhead.

**Yêu cầu:** đánh giá trực tiếp IAM auth, Secrets Manager và RDS Proxy.

**Gợi ý:** tối ưu pool và Lambda concurrency, giới hạn max new connections, đo DB bottlenecks, cân nhắc **RDS Proxy**. Chọn **standard IAM với secret backend** hoặc **end-to-end IAM** nếu hỗ trợ, kiểm tra connection pinning và chi phí proxy. IAM auth là xác thực, **không phải connection pooling**.

### Tình huống G — IAM role có Connect nhưng SQL SELECT bị từ chối

PostgreSQL database user **report_iam** đã được **GRANT rds_iam** và kết nối thành công bằng token. Khi truy vấn **SELECT * FROM finance.transactions**, database trả **permission denied**.

**Yêu cầu:** thêm quyền ở đâu, có nên cấp AmazonRDSFullAccess cho Lambda?

**Gợi ý:** không. Quyền thiếu nằm ở **SQL GRANT USAGE ON SCHEMA/SELECT ON TABLE** hoặc RLS/ownership, không phải IAM RDS control plane. Chỉ cấp đúng bảng và nghiệp vụ, kiểm tra truy cập của tenant khác.

### Tình huống H — Proxy nhận token nhưng backend báo auth failure

Java app sử dụng RDS Proxy endpoint, IAM role có rds-db:connect proxy ARN và token đúng. Proxy ở **standard IAM mode** nhưng Secret Manager secret của proxy có password cũ.

**Yêu cầu:** xác định lớp lỗi và điều chỉnh.

**Gợi ý:** client IAM có thể đúng trong khi **proxy → DB password authentication** lỗi. Kiểm tra proxy **DefaultAuthScheme**, Auth config, Secret ARN/rotation và database password user. Nếu chuyển sang end-to-end IAM, cần cấu hình đúng DB user IAM, proxy role rds-db:connect và các điều kiện engine/version.

### Tình huống I — Mất truy cập customer managed KMS key

Một nhóm bảo mật disabled customer-managed KMS key của RDS để đáp ứng chính sách nội bộ mà không kiểm kê dependency. DB chuyển sang trạng thái không truy cập được.

**Yêu cầu:** thiết kế xử lý sự cố.

**Gợi ý:** đây là vấn đề **at-rest encryption key access**, không phải lỗi JWT/password. Xác minh key ARN, key state, RDS status/events và khả năng phục hồi theo engine/backup; phối hợp KMS key owner khôi phục quyền đúng quy trình, không xóa snapshot, sau đó rà soát SCP/guardrails và lập cảnh báo key deletion/disable.

### Tình huống J — Cross-Region DR có snapshot nhưng không mở được

Hệ thống copy encrypted RDS snapshot sang Region khác nhưng không chuẩn bị customer-managed KMS key/permissions ở Region đích, ứng dụng DR cũng không có TLS CA/truststore và endpoint config chính xác.

**Yêu cầu:** nêu những phần của DR phải kiểm tra.

**Gợi ý:** Region đích cần KMS key và quyền phù hợp, snapshot copy/restore, DB subnet group/SG, parameter group, IAM DB resource ID mới và rds-db:connect ARN mới, SQL users, Secrets Manager và TLS. Khôi phục database nhưng application không kết nối được **chưa đạt RTO**.

## 22. Checklist triển khai production

- [ ] Đã xác định engine/version, loại RDS instance/Aurora cluster, Region và HA/DR requirements.
- [ ] Đã chọn mã hóa storage với **AWS managed KMS key** hoặc **customer managed key** theo compliance/operations.
- [ ] Đã xác minh **StorageEncrypted/KmsKeyId**, KMS key state/policy/grants và snapshot encryption.
- [ ] Đã có backup/restore drill, inventory của snapshot/replica và kế hoạch đổi/copy key an toàn.
- [ ] Đã cấu hình **TLS**, CA bundle, hostname verification và yêu cầu TLS ở DB parameter group theo khả năng engine.
- [ ] Đã kiểm tra **certificate rotation**, không dùng insecure trust-all hoặc SSL disable trong production.
- [ ] DB nằm trong network phân đoạn thích hợp, security group chỉ cho port từ application SG được cấp.
- [ ] Đã chọn **IAM database auth** hoặc **password auth** phù hợp driver, workload và tỷ lệ tạo connection.
- [ ] Với IAM, đã bật **IAMDatabaseAuthenticationEnabled** cho đúng instance/cluster hỗ trợ.
- [ ] Đã cấp **rds-db:connect** đúng **dbuser resource ID/DB username**, không wildcard quá rộng.
- [ ] Đã tạo SQL user với **AWSAuthenticationPlugin** hoặc **rds_iam** theo đúng engine; SQL GRANT least privilege.
- [ ] Token IAM được tạo mới cho **physical connection** khi cần, đúng endpoint/port/Region/username và không bị log.
- [ ] Ứng dụng dùng **Lambda execution role / ECS task role / EKS Pod Identity / EC2 profile**, không hard-code AWS keys.
- [ ] Nếu dùng password, đã lưu bằng **Secrets Manager**, có chính sách KMS/rotation/cache refresh.
- [ ] Master user/secret được quản lý riêng; application không sử dụng master DB account cho nghiệp vụ hàng ngày.
- [ ] Nếu dùng RDS Proxy, đã xác minh **standard IAM** hay **end-to-end IAM**, roles, secrets và TLS.
- [ ] Đã đo pool size, new connection rate, DatabaseConnections, proxy borrow latency và DB p95/p99.
- [ ] Đã thử failover, reconnect, DNS refresh, DB credentials rotation và IAM token expiry.
- [ ] Đã bật logs/alerts về auth failures, key state, rotation, DB performance và quyền IAM thay đổi.
- [ ] Đã giới hạn người được xem secrets, thay KMS key, cập nhật DB parameter group và quản lý database users.
- [ ] Đã dự toán RDS/Aurora compute/storage, Multi-AZ, snapshots, KMS, Secrets Manager, proxy và observability.
- [ ] Đã có runbook phân biệt network, TLS, IAM DB auth, SQL privilege, Secrets rotation và KMS key outage.

## 23. Ghi nhớ

**AWS KMS encryption at rest** bảo vệ RDS/Aurora storage, backup và snapshots theo phạm vi dịch vụ; **TLS** bảo vệ kết nối SQL; **IAM database authentication** xác thực một DB user bằng token SigV4 có hiệu lực **15 phút để tạo kết nối mới**; **SQL GRANT** mới quyết định database user được SELECT/INSERT/UPDATE những gì. Đây là **bốn lớp khác nhau** và không được dùng thay thế lẫn nhau.

Với **IAM DB auth**, ứng dụng dùng IAM role có **rds-db:connect** trên đúng **dbuser ARN với database resource ID**, database user đã được cấu hình plugin/role IAM, kết nối TLS và SQL permissions đúng. Với **password auth**, sử dụng **Secrets Manager** để lưu, rotate và refresh credentials thay vì đặt password trong source code. **RDS Proxy** giúp quản lý connection pools và có thể dùng **standard IAM** (proxy đọc secret) hoặc **end-to-end IAM** khi được hỗ trợ. Cuối cùng, một hệ thống an toàn vẫn phải có **private networking, backup/restore, giám sát key/secret lifecycle, HA/DR và runbook sự cố**.

### Tài liệu AWS chính thức để đối chiếu

- [Amazon RDS: Encrypting RDS resources](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html) — KMS at rest, snapshots, read replicas, key lifecycle và Blue/Green.
- [Amazon Aurora: Encryption at rest](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Overview.Encryption.html) — cluster encryption, backups và KMS.
- [RDS: SSL/TLS for connections](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html) — CA trust, certificate bundles và từng engine.
- [RDS: IAM database authentication for MariaDB, MySQL and PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html) — phạm vi, giới hạn, token 15 phút.
- [IAM DB authentication: Supported Regions and DB engines](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.RDS_Fea_Regions_DB-eng.Feature.IamDatabaseAuthentication.html) — kiểm tra version/Region.
- [IAM DB authentication: Creating a database account](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.DBAccounts.html) — AWSAuthenticationPlugin, rds_iam.
- [IAM DB authentication: Creating IAM policies](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.IAMPolicy.html) — ARN dbuser/resource ID.
- [IAM DB authentication: Connecting](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.Connecting.html) — generate-db-auth-token và SQL client.
- [RDS: Password management with Secrets Manager](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html) — RDS-managed master password/rotation.
- [Secrets Manager: Managed rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_managed.html) — managed service rotation.
- [RDS Proxy: Concepts and authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.howitworks.html) — connection pooling, standard/end-to-end IAM.
- [RDS Proxy: IAM authentication setup](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-iam-setup.html) — proxy role và backend IAM access.
- [RDS Blue/Green: Encryption considerations](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments-considerations.html) — key changes trên green environment.
- [Amazon RDS pricing](https://aws.amazon.com/rds/pricing/), [Amazon Aurora pricing](https://aws.amazon.com/rds/aurora/pricing/), [AWS KMS pricing](https://aws.amazon.com/kms/pricing/), [AWS Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/) và [AWS Pricing Calculator](https://calculator.aws/) — chi phí theo Region và dịch vụ.





