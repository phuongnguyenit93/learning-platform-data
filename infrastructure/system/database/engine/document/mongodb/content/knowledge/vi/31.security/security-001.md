# Mô hình đe dọa và các lớp bảo vệ MongoDB

## 1. Tại sao bảo mật MongoDB không chỉ là đặt mật khẩu?

Giả sử một nền tảng thương mại điện tử sử dụng MongoDB để lưu đơn hàng, tài khoản khách hàng và địa chỉ giao hàng. Hệ thống có API Java, nhân viên quản trị, công cụ báo cáo, hệ thống sao lưu và một cụm MongoDB nhiều node.

Nếu chỉ bật xác thực và đặt mật khẩu đủ dài, những tình huống sau vẫn có thể gây sự cố:

- Kẻ tấn công chiếm được biến môi trường chứa connection string của ứng dụng.
- Một service dùng tài khoản có quyền `root` nên khi bị khai thác có thể đọc và xóa mọi collection.
- Kết nối giữa ứng dụng và database không được xác thực chứng chỉ TLS đúng cách.
- Một endpoint cho phép người dùng truyền BSON filter tùy ý, dẫn tới **NoSQL injection**.
- Bản backup được đẩy vào kho lưu trữ mở quyền công khai hoặc không có bản bất biến.
- Database có RBAC nhưng một nhân viên hợp lệ xuất dữ liệu khách hàng trái phạm vi công việc.
- Một job báo cáo chạy aggregation cực nặng làm hệ thống hết tài nguyên.
- Một thao tác xóa nhầm hoặc ransomware được replication sao chép sang secondary; không còn bản backup phục hồi được.

Đó là lý do cần **mô hình đe dọa (threat model)** và **phòng thủ nhiều lớp (defense in depth)**. Threat model trả lời “cái gì cần bảo vệ, ai có thể tấn công, tấn công qua đường nào và hậu quả ra sao?”. Defense in depth trả lời “nếu một lớp thất bại, lớp nào tiếp theo vẫn giới hạn thiệt hại?”.

### 1.1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Lập sơ đồ các thành phần và **trust boundary** trong hệ thống MongoDB.
2. Xác định tài sản, đối tượng tấn công, bề mặt tấn công và giả định bảo mật.
3. Phân tích nguy cơ theo **STRIDE** và đánh giá ưu tiên rủi ro.
4. Giải thích vai trò của **network isolation, TLS, authentication, RBAC, encryption, auditing, backups, monitoring**.
5. Phòng vệ trước lộ credential, lạm dụng tài khoản ứng dụng, injection, rò rỉ backup, xóa dữ liệu và từ chối dịch vụ.
6. Hiểu sự khác nhau giữa **Atlas** và **self-managed MongoDB** khi triển khai kiểm soát.
7. Thiết kế kiểm tra bảo mật, kịch bản ứng phó sự cố và bài thực hành với phạm vi an toàn.

**Giới hạn phạm vi:** ví dụ dùng để học cấu hình/thiết kế an toàn, không phải hướng dẫn chạy trực tiếp trên cluster production. Các tính năng cụ thể có thể phụ thuộc **phiên bản MongoDB, loại triển khai và gói dịch vụ**.

## 2. Những tài sản cần bảo vệ

Hãy bắt đầu từ tài sản, **không** từ danh sách tính năng MongoDB.

| Tài sản | Ví dụ | Nếu bị xâm phạm |
|---|---|---|
| Dữ liệu khách hàng | Tên, địa chỉ, số điện thoại | Lộ PII, vi phạm quyền riêng tư |
| Dữ liệu kinh doanh | Đơn hàng, giá, giao dịch | Gian lận, báo cáo sai |
| Danh tính truy cập | User DB, API key, chứng chỉ | Giả mạo ứng dụng/người quản trị |
| Quyền quản trị | Roles, user administration | Leo thang đặc quyền, mất kiểm soát |
| Khóa mã hóa | KMS master key, data encryption key | Mất khả năng giải mã hoặc lộ dữ liệu |
| Hạ tầng MongoDB | Primary, secondary, mongos, config servers | Mất tính sẵn sàng/toàn vẹn |
| Metadata và index | Sharding metadata, schema, indexes | Truy vấn sai hoặc gián đoạn |
| Bản sao lưu | Snapshot, dump, PITR metadata | Khôi phục không được hoặc dữ liệu bị lấy cắp |
| Audit/monitoring | Authentication events, admin actions | Mất khả năng phát hiện/điều tra |
| Cấu hình và pipeline CI/CD | URI, IaC, secret references | Thay đổi trái phép, phát tán bí mật |

Một đối tượng có thể thuộc nhiều nhóm. Ví dụ, collection `users` vừa chứa thông tin cá nhân vừa chứa dữ liệu phân quyền nghiệp vụ. Cần xác định **data owner, độ nhạy cảm, retention và quyền được đọc** cho từng loại.

### 2.1. Tam giác CIA

Ba mục tiêu cổ điển của an toàn thông tin:

- **Confidentiality — Bảo mật:** người không được phép không đọc được dữ liệu.
- **Integrity — Toàn vẹn:** thay đổi phải hợp lệ, có thể phát hiện sửa trái phép.
- **Availability — Sẵn sàng:** hệ thống vẫn phục vụ khi có lỗi/sự cố trong phạm vi mục tiêu đã đặt.

Ví dụ:

```text
Lộ địa chỉ khách hàng    -> Confidentiality
Sửa số dư trái phép      -> Integrity
Xóa collection orders    -> Integrity + Availability
Query làm cạn CPU        -> Availability
Mất khóa giải mã         -> Availability + Confidentiality
```

### 2.2. Thêm tính truy cứu trách nhiệm

Trong hệ thống quan trọng cần biết **ai làm gì, khi nào, từ đâu, qua đường nào**. Authentication, audit logs, application correlation ID và quy trình vận hành giúp hỗ trợ **accountability**.

Mã hóa không tự cung cấp accountability; audit không tự ngăn lộ dữ liệu; backup không tự ngăn injection. Các kiểm soát phải phối hợp.

## 3. Sơ đồ hệ thống và ranh giới tin cậy

Một kiến trúc ví dụ:

```text
                           INTERNET / USER
                                  |
                           [TLS HTTPS]
                                  |
                     +------------------------+
                     | WAF / API Gateway      |
                     | AuthN / Rate limiting  |
                     +------------------------+
                                  |
                 TRUST BOUNDARY A | (request không tin cậy)
                                  v
                     +------------------------+
                     | Java API Service       |
                     | Business authorization |
                     | Input validation       |
                     +------------------------+
                            |         |
                            |         +------------------+
                            |                            |
                       [TLS+mTLS?]                    Secrets/KMS
                            |                            |
                 TRUST BOUNDARY B                       |
                            v                            v
                 +--------------------+        +------------------+
                 | Private Network    |        | IAM / Key Store  |
                 | MongoDB endpoints  |        +------------------+
                 +--------------------+
                            |
           +----------------+----------------------+
           |                |                      |
       mongos/router      mongod nodes         Monitoring
           |                |                      |
           +-------> Shards/Replica Set <---------+
                            |
                   TRUST BOUNDARY C
                            |
                   Encrypted Backup Store
                   (separate permissions)
```

Đây là **mô hình khái quát**. Với replica set không sharding, thường không có `mongos`. Với Atlas, nhiều thành phần được quản lý bởi nhà cung cấp nhưng **không biến phần trách nhiệm của ứng dụng thành trách nhiệm của Atlas**.

### 3.1. Trust boundary là gì?

Một **ranh giới tin cậy** nằm giữa hai vùng mà một bên **không tự được tin** chỉ vì bên kia tin nó.

Các ranh giới điển hình:

1. **Internet → API:** mọi tham số từ client đều phải kiểm tra.
2. **API → MongoDB:** app có credential nhưng không được mặc định có quyền quản trị toàn cụm.
3. **Ứng dụng → Secrets/KMS:** ứng dụng chỉ nhận khóa/secret cần dùng.
4. **Primary ↔ Secondary:** node cũng phải xác thực và mã hóa kết nối nội bộ.
5. **MongoDB → Backup storage:** backup cần quyền/khóa/retention độc lập.
6. **Human operator → Admin interface:** đăng nhập người quản trị và hoạt động khẩn cấp cần ghi nhận.

### 3.2. Data flow diagram (DFD) tối thiểu

Khi lập threat model, nên ghi mỗi luồng:

```text
Luồng: Java API -> MongoDB
Tài sản: order documents
Protocol: MongoDB wire protocol over TLS
Identity: orders_service
Permissions: đọc/ghi các collection cần thiết
Mạng: private subnet
Trust boundary: application process -> DB tier
Log: connection/auth failures, audit policy
Data sensitivity: PII, order state
```

Làm tương tự cho monitoring, backup, ETL, admin, migration job và CI/CD.

## 4. Nhận diện kẻ tấn công và bề mặt tấn công

### 4.1. Những tác nhân đáng xét

| Tác nhân | Năng lực giả định | Mục tiêu có thể có |
|---|---|---|
| Người dùng Internet không xác thực | Gửi request tới API | Đọc/ghi trái phép, gây DoS |
| Tài khoản người dùng bị chiếm | Có session hợp lệ | Đọc dữ liệu ngoài tenant |
| Ứng dụng bị xâm nhập | Có quyền của service DB user | Đọc/xóa dữ liệu trong phạm vi user |
| Người nội bộ có quyền thật | Truy cập theo vai trò | Lạm dụng, xuất dữ liệu |
| Operator cấu hình nhầm | Có quyền quản trị | Phơi cổng, mất backup, xóa dữ liệu |
| Kẻ lấy được máy/volume backup | Đọc file/đĩa | Lấy cắp dữ liệu hoặc khóa |
| Supply-chain attacker | Tác động image/dependency/CI | Đánh cắp secret, chạy mã trái phép |

Không cần mặc định mọi tác nhân có thể làm mọi việc. Threat model tốt nêu rõ **năng lực đầu vào** và **phạm vi thực tế**.

### 4.2. Bề mặt tấn công MongoDB

- Cổng kết nối MongoDB (`mongod`, `mongos`).
- API ứng dụng cho phép tạo filter, sort, aggregation.
- Database users và authentication mechanisms.
- Admin console, Atlas organization/project, automation API.
- Kết nối nội bộ replica set/sharded cluster.
- Secret store, credential trong CI/CD, log hoặc URI.
- Snapshot, bản dump, object storage backup.
- Metrics/log exporters và database monitoring.
- Máy chủ lưu data files, OS service account.
- Docker/Kubernetes orchestration, cloud networking.

Đừng coi database không mở trực tiếp ra Internet là **miễn nhiễm**: ứng dụng có thể bị khai thác và trở thành đường truy cập gián tiếp.

## 5. Phương pháp STRIDE cho hệ thống MongoDB

STRIDE là khung phân tích phổ biến:

| STRIDE | Câu hỏi | Ví dụ với MongoDB |
|---|---|---|
| **S — Spoofing** | Ai có thể giả mạo danh tính? | Dùng credential bị lộ để đăng nhập `orders_service` |
| **T — Tampering** | Ai có thể sửa dữ liệu/trạng thái? | Sửa `status` đơn hàng hoặc role |
| **R — Repudiation** | Có thể phủ nhận hành động không? | Không có audit khi operator xóa collection |
| **I — Information disclosure** | Dữ liệu có thể lộ ra sao? | Public endpoint, backup lộ, query vượt tenant |
| **D — Denial of service** | Có thể làm dịch vụ gián đoạn không? | Query/aggregation quá nặng làm cạn CPU/I/O |
| **E — Elevation of privilege** | Có thể có quyền cao hơn không? | App dùng role `root` hoặc bí mật admin bị lấy |

### 5.1. Áp STRIDE vào một luồng cụ thể

Luồng `Java API → MongoDB`:

**Spoofing:** nếu attacker lấy được URI/password, có thể giả service.

**Tampering:** nếu service account được phép update quá nhiều collection, endpoint bị khai thác có thể làm sai dữ liệu.

**Repudiation:** nếu mọi microservice chia sẻ cùng DB user, audit khó biết service nào tạo thao tác.

**Information disclosure:** endpoint trả document không lọc `tenantId`, hoặc lỗi log in ra password.

**DoS:** một endpoint cho phép `sort`/regex/aggregation tùy ý, gây truy vấn nặng.

**Elevation:** service có quyền user administration không cần thiết nên có thể cấp thêm role.

### 5.2. Mỗi rủi ro cần map tới một kiểm soát

Ví dụ:

```text
Tài sản: orders
Đe dọa: bị sửa status trái phép
Đường vào: API endpoint /orders/{id}
Điều kiện: IDOR (không kiểm tra tenant ownership)
Tác động: gian lận và sai trạng thái

Phòng vệ:
  - AuthN ở API
  - AuthZ theo tenant/ownership trong mỗi query
  - DB user chỉ readWrite phạm vi cần thiết
  - Schema/business invariants
  - Audit cho thao tác nhạy cảm
  - Khả năng khôi phục từ backup/ledger
```

Đây là defense in depth: **không một lớp đơn lẻ nào** chịu trách nhiệm cho tất cả.

## 6. Đánh giá mức ưu tiên rủi ro

Threat model cần đi từ danh sách đe dọa đến quyết định hành động.

### 6.1. Ma trận định tính

| Khả năng xảy ra | Tác động thấp | Tác động vừa | Tác động cao |
|---|---|---|---|
| Thấp | Theo dõi | Cân nhắc giảm thiểu | Giảm thiểu |
| Trung bình | Cân nhắc | Giảm thiểu | Ưu tiên cao |
| Cao | Giảm thiểu | Ưu tiên cao | Khẩn cấp |

Đây chỉ là **ma trận minh họa**. Mức độ phải dựa trên dữ liệu thật: mức lộ hệ thống, độ nhạy cảm, khả năng phục hồi, lợi ích của attacker và bằng chứng sự cố.

### 6.2. Ví dụ risk register

| ID | Rủi ro | Tác động | Biện pháp | Bằng chứng kiểm soát |
|---|---|---|---|---|
| R01 | MongoDB port công khai | Lộ dữ liệu/DoS | Private network, firewall | Security group review |
| R02 | App dùng DB admin | Leo thang, sửa/xóa rộng | RBAC tối thiểu | Roles của service |
| R03 | TLS không xác minh cert | MITM/mạo danh server | Require TLS, CA/SAN validation | Connection test |
| R04 | Query operator injection | Đọc trái phạm vi | Allowlist, typed parameters | Negative tests |
| R05 | Backup cùng account production | Ransomware xóa cả bản backup | Isolation, immutability | Restore drill |
| R06 | Thiếu audit | Khó điều tra | Audit/events, central logs | Alert/truy xuất log |
| R07 | Key encryption nằm cùng data | Lộ plaintext khi bị chiếm host | KMS/key separation | Key access policies |

Mỗi item nên có **owner, deadline, trạng thái, residual risk** và lịch kiểm tra lại.

## 7. Defense in depth: những lớp bảo vệ

```text
               DỮ LIỆU NHẠY CẢM
                      |
           +---------------------+
           | Application AuthZ   |
           | schema + validation |
           +---------------------+
                      |
           +---------------------+
           | MongoDB RBAC        |
           | least privilege     |
           +---------------------+
                      |
           +---------------------+
           | Identity + Secrets  |
           | SCRAM / X.509 / IAM |
           +---------------------+
                      |
           +---------------------+
           | TLS + cert checks   |
           +---------------------+
                      |
           +---------------------+
           | Private network     |
           | firewall/endpoint   |
           +---------------------+
                      |
           +---------------------+
           | OS/storage/KMS      |
           | backup/recovery     |
           +---------------------+
                      |
           +---------------------+
           | Audit/monitoring    |
           | incident response   |
           +---------------------+
```

Sơ đồ **không phải chuỗi các lớp phụ thuộc cứng**. Encryption tại client còn có thể bảo vệ data ngay cả khi database admin có quyền đọc file. Backup và audit cũng hoạt động xuyên các lớp thay vì chỉ là “vòng ngoài”.

**Nguyên tắc:** mỗi kiểm soát giải quyết một tập rủi ro riêng. Phải biết **nó không bảo vệ được điều gì** để tránh cảm giác an toàn giả.

## 8. Lớp mạng: hạn chế ai có thể chạm tới MongoDB

### 8.1. Đưa MongoDB vào mạng tin cậy

Thông thường ứng dụng đi qua:

```text
Internet -> Load Balancer -> API -> Private MongoDB subnet
```

Database không nên có port mở trực tiếp ra Internet nếu không có yêu cầu đặc biệt và kiểm soát tương xứng.

Biện pháp:

- VPC/VNet/subnet riêng.
- Firewall/security groups chỉ cho phép nguồn cần thiết.
- Private endpoint/private connectivity cho dịch vụ managed.
- Giới hạn egress từ máy chủ DB.
- Bastion/zero-trust access dành cho người vận hành.
- Không đưa `mongod`/`mongos` vào public load balancer chung với web.

### 8.2. `bindIp` là một lớp, không phải firewall

Ví dụ cấu hình **standalone lab chỉ trên máy local**:

```yaml
net:
  port: 27017
  bindIp: 127.0.0.1
```

`127.0.0.1` chỉ nhận kết nối từ host local. Với replica set/sharded cluster, các node cần giao tiếp từ các địa chỉ private được phép; **không sao chép cấu hình localhost đó sang tất cả node rồi mong replication hoạt động**.

Không dùng:

```yaml
net:
  bindIp: 0.0.0.0
```

như giải pháp nhanh để sửa lỗi kết nối production. Nó yêu cầu xem lại firewall, TLS, authorization và phạm vi network. `bindIp` không thay thế cơ chế xác thực hoặc firewall.

### 8.3. Zero trust ở từng kết nối

Một IP nằm trong private subnet **không tự đủ quyền đọc dữ liệu**. Ngay cả service cùng mạng vẫn phải xác thực bằng credential/certificate và được cấp RBAC đúng chức năng.

### 8.4. Các port khác cũng cần kiểm soát

Threat model không chỉ xét port ứng dụng dùng. Cần kiểm tra:

- MongoDB wire protocol endpoints.
- Cổng metrics/exporter.
- Monitoring agents.
- Admin automation/API.
- SSH/remote management.
- Storage snapshot interfaces.

Một exporter không yêu cầu auth có thể tiết lộ tên database, topology hoặc metrics nhạy cảm dù DB port đã đóng.

## 9. TLS: bảo vệ dữ liệu khi truyền

### 9.1. TLS giúp chống điều gì?

- Nghe lén dữ liệu trên đường truyền.
- Sửa đổi gói tin trong quá trình giao tiếp.
- Giả mạo server khi client xác minh chứng chỉ/hostname đúng.

TLS phải được áp dụng cho **ứng dụng ↔ MongoDB** và **các thành phần MongoDB ↔ nhau** theo kiến trúc.

### 9.2. Một cấu hình minh họa cho standalone có TLS

```yaml
# mongod.conf - minh họa, không dùng nguyên trong production.
net:
  port: 27017
  bindIp: 127.0.0.1
  tls:
    mode: requireTLS
    certificateKeyFile: /secure/path/server.pem
    CAFile: /secure/path/ca.pem

security:
  authorization: enabled
```

Điều kiện:

- File certificate/private key có owner/quyền đọc tối thiểu.
- Chứng chỉ hợp lệ, được CA mà client tin tưởng ký.
- Hostname/SAN phù hợp tên DNS client thực sự kết nối.
- Đã có user quản trị và quy trình bootstrapping phù hợp.
- Với replica set/sharded cluster cần thêm **internal authentication** và TLS giữa nodes.

Không copy cấu hình trên sang môi trường mới mà không thiết lập certificates, user và internal cluster auth.

### 9.3. Kết nối mongosh có xác minh TLS

```bash
mongosh "mongodb://db.internal.example:27017/shop?tls=true&authSource=admin" --tlsCAFile /secure/path/ca.pem --username orders_service --password
```

`--password` không kèm giá trị trong ví dụ để tránh ghi password trực tiếp vào shell history. Tên host/cert và CA phải đúng môi trường.

### 9.4. Không tắt xác minh chứng chỉ để sửa lỗi

Các tùy chọn như:

```text
tlsAllowInvalidCertificates
tlsAllowInvalidHostnames
tlsInsecure
```

làm yếu xác minh TLS. Không dùng trong production để “cho kết nối được” sau lỗi hostname hoặc CA.

Hãy sửa **DNS/SAN/chain/certificate trust**, không bỏ qua kiểm tra định danh máy chủ.

### 9.5. TLS không bảo vệ sau khi credential bị chiếm

Nếu attacker lấy được credential hợp lệ và truy cập qua TLS, server vẫn thấy một kết nối được mã hóa **nhưng có thể là attacker**. Vì vậy TLS phải đi cùng authentication, RBAC, network isolation và monitoring.

## 10. Authentication: ai đang kết nối?

### 10.1. Authentication khác authorization

**Authentication (AuthN)**: xác định danh tính.

**Authorization (AuthZ)**: quyết định danh tính đó được làm gì.

```text
SCRAM/X.509/...  ->  "Đây là orders_service"
RBAC             ->  "orders_service được phép tìm/ghi order
                      trong phạm vi quy định"
```

Một user đăng nhập thành công **không** mặc nhiên có quyền đọc mọi collection.

### 10.2. SCRAM

MongoDB Community hỗ trợ SCRAM, bao gồm **SCRAM-SHA-256**. Trong hệ thống tự quản trị, đây là cơ chế xác thực bằng username/password phổ biến.

Hệ thống cần:

- Mật khẩu mạnh/duy nhất cho service.
- Không dùng chung credential giữa service, developer và automation.
- Secret manager hoặc giải pháp cấp phát an toàn.
- Quy trình rotation và thu hồi.
- TLS để bảo vệ giao tiếp và xác thực server.

### 10.3. X.509

Authentication dựa trên chứng chỉ X.509 có thể hữu ích với hạ tầng PKI. Nó yêu cầu xử lý vòng đời certificate/private key, xác minh danh tính, mapping identity và expiration.

**TLS certificate và user identity không phải lúc nào cũng là cùng một khái niệm.** Một hệ thống có thể dùng TLS xác thực server, nhưng client vẫn dùng SCRAM để đăng nhập. Nếu chọn X.509 client authentication, phải thiết kế yêu cầu chứng chỉ client và role mapping riêng.

### 10.4. LDAP/Kerberos/OIDC

Một số hình thức xác thực tích hợp hệ thống danh tính doanh nghiệp phụ thuộc MongoDB Enterprise/Atlas, phiên bản và cấu hình cụ thể.

Không tuyên bố một deployment Community có thể bật mọi cơ chế chỉ bằng thêm một dòng config. Hãy xác nhận tính năng, điều kiện và vòng đời token/certificate của bản đang dùng.

### 10.5. Internal authentication

Trong replica set/sharded cluster, các MongoDB member phải xác thực nhau. Những phương án như keyfile hoặc X.509 cần được cấu hình đúng theo phiên bản.

**Nếu chỉ bảo vệ kết nối client mà bỏ qua member-to-member authentication/TLS, trust boundary nội bộ vẫn còn yếu.**

## 11. RBAC và nguyên tắc đặc quyền tối thiểu

MongoDB dùng **Role-Based Access Control (RBAC)** để quyết định một identity có quyền nào trên resource nào.

### 11.1. Đừng cấp `root` cho application

Một ứng dụng chỉ cần:

```text
orders_service:
  read/write shop.orders
  read shop.products
  không quản trị users/roles
  không drop database
  không sửa config/sharding
```

Tài khoản `root` có khả năng quản trị rất rộng. Nếu endpoint ứng dụng bị khai thác, attacker có thể dùng quyền của process; **mọi quyền dư thừa làm tăng blast radius**.

### 11.2. Built-in roles và custom roles

Một số built-in roles:

- `read`: quyền đọc trong scope được cấp.
- `readWrite`: các quyền đọc/ghi trong scope được cấp.
- `dbAdmin`: quản trị database theo phạm vi role, không phải chỉ đọc.
- `userAdmin`: quản lý user/role trong scope liên quan; có rủi ro leo thang nếu cấp sai.
- `root`: đặc quyền quản trị rất rộng.

**Built-in `readWrite` trên toàn database có thể quá rộng** nếu service chỉ được ghi một collection. Khi cần quyền chi tiết hơn, dùng **custom roles với privileges được chỉ định rõ**.

### 11.3. Ví dụ tạo user lab

Chỉ chạy trên MongoDB **lab mà bạn quản trị**, sau khi đã thiết lập quyền tạo user và cơ chế bootstrap an toàn:

```javascript
const adminDb = db.getSiblingDB("admin");

adminDb.createUser({
  user: "orders_service_lab",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "shop_lab" }
  ]
});
```

Ở đây user được định danh trong **database `admin`**; role `readWrite` áp dụng cho `shop_lab`. Kết nối dùng `authSource=admin` tương ứng.

`passwordPrompt()` giúp tránh viết plaintext password vào source/shell history.

**Không chạy mã tạo user mới trên production** như bài tập nếu không có quyền và quy trình thay đổi đã được phê duyệt.

### 11.4. Giới hạn cần nhớ

`readWrite` cấp quyền đọc/ghi trong database được chọn; nó **không thay** quyền kiểm tra tenant ở ứng dụng nếu nhiều tenant dùng chung một collection.

Phân quyền DB phải kết hợp:

```text
API AuthN -> API AuthZ -> Tenant-aware query -> MongoDB RBAC
```

## 12. Phân quyền nghiệp vụ đa tenant

### 12.1. Rủi ro IDOR / broken object authorization

Giả sử endpoint:

```text
GET /orders/O1001
```

đã xác thực user Alice nhưng code chỉ query:

```javascript
db.orders.findOne({ _id: "O1001" });
```

Nếu Alice đoán được ID đơn hàng của Bob, API có thể trả dữ liệu sai quyền dù kết nối MongoDB dùng TLS và DB user có RBAC hợp lệ.

### 12.2. Đưa tenant/ownership vào điều kiện query

Ví dụ:

```javascript
const tenantId = authenticatedContext.tenantId;
const orderId = validatedOrderId;

db.orders.findOne({
  _id: orderId,
  tenantId: tenantId
});
```

**Không** lấy `tenantId` tin cậy từ query parameter do user tự sửa rồi dùng làm căn cứ duy nhất.

### 12.3. Update cũng phải giữ quyền

```javascript
db.orders.updateOne(
  {
    _id: validatedOrderId,
    tenantId: authenticatedContext.tenantId,
    status: "CREATED"
  },
  {
    $set: { status: "CANCELLED" }
  }
);
```

Filter vừa hạn chế ownership vừa bảo vệ state transition đơn giản. Tuy nhiên, business rule phức tạp có thể cần transaction và validation khác; không coi một filter là toàn bộ hệ thống authorization.

### 12.4. Nếu nhiều tenant chia sẻ database user

MongoDB RBAC thông thường cấp theo database/collection/action, **không tự sinh row-level security theo `tenantId`** cho mọi truy vấn. Cần API/business authorization, kiến trúc tách tenant hoặc cơ chế dữ liệu tương xứng.

## 13. NoSQL injection: không nhận filter do client điều khiển

### 13.1. Vấn đề khác SQL injection nhưng cùng bản chất

NoSQL injection xảy ra khi input không tin cậy được đưa vào **cấu trúc query/operator** thay vì chỉ là **giá trị dữ liệu**.

Ví dụ chống chỉ định:

```javascript
// Sai: client tự gửi filter object, server dùng trực tiếp.
const clientFilter = req.body.filter;
const user = db.users.findOne(clientFilter);
```

Nếu `clientFilter` chứa các operator như `$ne`, `$regex` hoặc điều kiện khác, ý nghĩa truy vấn có thể khác hoàn toàn so với yêu cầu nghiệp vụ.

### 13.2. Xây filter có schema cố định

```javascript
function validateUsername(value) {
  if (typeof value !== "string" ||
      value.length < 1 ||
      value.length > 100) {
    throw new Error("Invalid username");
  }
  return value;
}

const username = validateUsername(req.body.username);
const user = db.users.findOne({ username: username });
```

Người dùng chỉ kiểm soát **String username**, không được kiểm soát operator hoặc field name.

### 13.3. Không thực thi JavaScript server-side tùy ý

MongoDB có các tính năng/biểu thức có thể thực thi JavaScript server-side như `$where`, `$function` và `$accumulator` trong các ngữ cảnh/phiên bản tương ứng.

Nếu ứng dụng không cần các khả năng này, tài liệu security checklist của MongoDB khuyến nghị cân nhắc **vô hiệu hóa server-side scripting** ở self-managed deployments bằng cấu hình phù hợp, đồng thời loại bỏ các phụ thuộc nghiệp vụ vào chúng trước.

Không cho user gửi những biểu thức này vào API dưới dạng đoạn mã rồi chạy như pipeline đã tin cậy.

### 13.4. Typed API và allowlist

Ví dụ API tìm sản phẩm:

```javascript
const allowedSorts = new Map([
  ["priceAsc", { price: 1, _id: 1 }],
  ["priceDesc", { price: -1, _id: 1 }],
  ["newest", { createdAt: -1, _id: 1 }]
]);

const sort = allowedSorts.get(req.query.sort) ||
             allowedSorts.get("newest");

const limit = Math.min(
  Math.max(Number(req.query.limit) || 20, 1),
  100
);

db.products.find({
  active: true,
  tenantId: authenticatedContext.tenantId
}).sort(sort).limit(limit);
```

Không đưa `req.query.sort` thẳng vào `sort()` nếu nó có thể chứa các field/operator bị cấm. Cũng cần validate rõ tính nguyên, finite và dữ liệu lỗi của `limit` trong code production; snippet chỉ minh họa allowlist và upper bound.

## 14. Java Driver: tránh dynamic filter tùy ý

### 14.1. Query tham số hóa bằng builders

```java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;

import org.bson.conversions.Bson;

String tenantId = authenticatedTenantId;
String orderId = validatedOrderId;

Bson filter = and(
    eq("_id", orderId),
    eq("tenantId", tenantId)
);

Document order = orders.find(filter).first();
```

Builder APIs giúp biểu đạt **field/operator cố định**, còn input chỉ cung cấp giá trị.

### 14.2. Phương án nguy hiểm

```java
// Chống chỉ định nếu rawJson là input không tin cậy.
Bson filter = Document.parse(rawJsonFromClient);
orders.find(filter);
```

Vấn đề không chỉ là parse JSON thành công; việc nhận cả document query cho user điều khiển có thể cho phép thêm operator, field trái quyền hoặc pipeline nặng.

### 14.3. Đừng log MongoDB URI có secret

Ví dụ trong logging:

```java
// Không nên:
logger.info("Mongo URI: {}", mongoUriWithPassword);

// Nên:
logger.info("MongoDB connection initialized for service {}", serviceName);
```

Ứng dụng cần chính sách redaction cho exception, connection strings, auth failures và log của request.

## 15. Schema validation: giảm sai dữ liệu, không thay quyền

MongoDB hỗ trợ **collection validation** qua `$jsonSchema`.

Ví dụ một collection đơn hàng lab:

```javascript
db.getSiblingDB("security_lab_327").createCollection(
  "orders327",
  {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["tenantId", "status", "total"],
        properties: {
          tenantId: {
            bsonType: "string",
            minLength: 1
          },
          status: {
            enum: ["CREATED", "PAID", "CANCELLED"]
          },
          total: {
            bsonType: ["int", "long", "decimal"],
            minimum: 0
          }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  }
);
```

Collection validation có thể ngăn một số trường hợp dữ liệu sai kiểu/sai giá trị, nhưng:

- Không xác định user hiện tại có quyền thay đổi đơn hàng nào.
- Không thay thế kiểm tra business invariant liên quan nhiều document.
- Không bảo đảm mọi document legacy đã hợp lệ.
- Có thể có quyền/đường bypass theo role hoặc cấu hình, cần kiểm soát.

**Schema validation bảo vệ chất lượng/toàn vẹn cấu trúc; RBAC và application AuthZ bảo vệ quyền truy cập.**

## 16. Mã hóa khi lưu và mã hóa phía client

Ba lớp dễ bị nhầm:

| Lớp | Dữ liệu được bảo vệ ở đâu? | Giúp chống | Không tự chống |
|---|---|---|---|
| **TLS** | Trên đường truyền | Nghe lén/MITM khi cert được xác minh | Credential hợp lệ bị lộ, user có quyền đọc |
| **Encryption at rest** | File/volume/backup được mã hóa khi lưu | Mất đĩa, đọc file vật lý ngoài quyền | DB user đọc plaintext qua server đang chạy |
| **Client-side field encryption** | Field được mã hóa **trước khi gửi đến server** | Một số kịch bản DB admin/host không có key đọc field | App bị chiếm khi đang giữ key và plaintext |

### 16.1. Encryption at rest

MongoDB có hỗ trợ mã hóa tại storage engine trong những edition/cấu hình tương ứng; có thể dùng mã hóa ổ đĩa/file system hoặc các cơ chế managed encryption.

Mã hóa at rest giúp giảm rủi ro:

- Ổ đĩa bị mất/đánh cắp.
- Snapshot/file data bị truy cập trái phép mà không có key.
- Máy chủ bị tháo storage.

Nhưng khi `mongod` đang chạy và một user có quyền truy vấn, dữ liệu có thể được giải mã bởi server. **Encryption at rest không thay thế RBAC.**

### 16.2. Client-Side Field Level Encryption (CSFLE)

CSFLE cho phép client mã hóa một số field trước khi gửi MongoDB:

```text
Ứng dụng tin cậy:
  plaintext PII
     |
     v
  Encrypt bằng DEK
     |
     v
MongoDB lưu ciphertext
     |
     v
Ứng dụng có key phù hợp giải mã
```

Ví dụ dữ liệu:

```javascript
{
  _id: "C001",
  name: "Customer A",
  personalId: /* encrypted BSON value */
}
```

Server có thể lưu encrypted field nhưng không có key giải mã ở client. Quyền đọc MongoDB trên collection **không đồng nghĩa** có thể đọc plaintext của field đó.

### 16.3. Queryable Encryption

Queryable Encryption cho phép một số truy vấn trên field được mã hóa phía client theo những chế độ/kiểu dữ liệu được hỗ trợ.

Không suy rằng:

- Mọi field encrypted đều query được bằng mọi operator.
- Mọi kiểu BSON và aggregation đều được hỗ trợ.
- Search index, regex, sort, join, range đều hoạt động như plaintext.
- Chỉ cần bật Queryable Encryption là hệ thống không còn rủi ro.

**Khả năng query, hạn chế type/operator và hiệu năng phụ thuộc MongoDB version**, cần đối chiếu tài liệu chính xác và test workload trước khi triển khai.

### 16.4. Client-side encryption không cứu được client bị chiếm

Nếu attacker kiểm soát application process có quyền truy cập plaintext và KMS, attacker có thể:

- Gọi API giải mã trong process.
- Đọc dữ liệu trước khi mã hóa.
- Trích dữ liệu khi phục vụ request hợp lệ.

Do đó CSFLE/Queryable Encryption là **một ranh giới bảo vệ bổ sung**, không thay thế việc harden ứng dụng và quản lý quyền truy cập KMS.

## 17. Quản lý khóa: tách dữ liệu và khả năng giải mã

### 17.1. Các lớp khóa

Một mô hình có:

- **Data Encryption Key (DEK):** dùng mã hóa dữ liệu/field.
- **Customer Master Key (CMK):** bảo vệ/bao gói DEK.
- **Key vault:** lưu metadata và các DEK được bảo vệ.
- **KMS:** cung cấp cơ chế quản lý/kiểm soát master keys.

```text
Application
   |
   +--> KMS -> cấp quyền giải mã/unwrap DEK
   |
   +--> MongoDB Key Vault -> encrypted DEK metadata
   |
   +--> MongoDB business collection -> encrypted fields
```

### 17.2. Nguyên tắc

1. Không hardcode key trong source code hoặc image.
2. Tách quyền quản lý key khỏi quyền đọc database.
3. Giới hạn service nào có quyền unwrap/decrypt.
4. Audit truy cập KMS và rotate theo policy.
5. Giữ kế hoạch phục hồi key, nếu mất key có thể **mất khả năng giải mã dữ liệu**.
6. Test restore backup bao gồm key vault và KMS availability.

### 17.3. Mã hóa backup cần quản lý khóa độc lập

Nếu backup được mã hóa nhưng key bị mất, backup vẫn có thể “khôi phục file” nhưng không thể sử dụng dữ liệu. Mục tiêu khôi phục phải bao gồm **khả năng giải mã và kiểm tra tính đúng đắn**, không chỉ số lượng file.

## 18. Quản lý secrets và credential rotation

### 18.1. Secret có thể rò ở đâu?

- Repository, commit history.
- CI logs.
- File `.env` được chia sẻ.
- Container image.
- Process arguments/shell history.
- Crash dump và application logs.
- Monitoring dashboard.
- Kết quả backup config.

### 18.2. Những biện pháp hữu ích

- Secret manager/KMS/vault phù hợp.
- Phân quyền đọc secret theo service identity.
- Secret khác nhau cho development/staging/production.
- Không dùng một database admin password cho mọi app.
- Phát hiện secret lộ bằng scanning và quy trình revoke/rotate.
- Hạn chế in URI đầy đủ khi logging.

### 18.3. Rotation không chỉ là đổi string trong file

Quy trình:

```text
1. Tạo credential mới có quyền tối thiểu.
2. Cập nhật secret store/config ứng dụng.
3. Triển khai service dùng credential mới.
4. Xác nhận kết nối và business flows.
5. Thu hồi credential cũ.
6. Kiểm tra logs, audit và những consumer còn sử dụng.
```

Với người dùng/tình huống khác, có thể cần cách xoay credential riêng để tránh downtime. Không xóa credential cũ trước khi hệ thống hoàn tất chuyển đổi nếu chưa có kế hoạch rollback.

## 19. Hardening máy chủ và runtime

Ngay cả khi MongoDB có authentication và TLS, host bị chiếm có thể dẫn tới lộ data files, logs, keyfiles hoặc kiểm soát database.

### 19.1. Nguyên tắc OS

- Chạy MongoDB bằng **dedicated OS user**, không chạy như root nếu không cần.
- Giới hạn quyền thư mục data, config, cert và backup.
- Dùng bản vá OS/MongoDB được hỗ trợ.
- Quản trị remote qua kênh kiểm soát truy cập.
- Đặt service trong phân đoạn network phù hợp.
- Kiểm soát installed packages và agent.
- Có baseline cấu hình và phát hiện drift.

### 19.2. Container/Kubernetes

Khi dùng container:

- Không đặt password trong image.
- Tránh privileged container và quyền host filesystem không cần thiết.
- Bảo vệ PersistentVolume/snapshot.
- Dùng network policies và secrets RBAC.
- Giới hạn Kubernetes service account.
- Theo dõi thay đổi StatefulSet/Operator.
- Đảm bảo backup không phụ thuộc một node có thể biến mất.

**Kubernetes Secret mặc định không tự thay thế KMS và chính sách bảo vệ backup**; cần hiểu cách lưu, encrypt at rest và cấp quyền trên cluster.

### 19.3. Antivirus/EDR

Theo hướng dẫn MongoDB, các scanner có thể ảnh hưởng I/O khi quét trực tiếp data/log directories hoặc quarantine file DB. Cần thiết kế **exclusion phù hợp** cùng biện pháp bảo vệ endpoint khác, không tự tắt mọi EDR chỉ vì MongoDB dùng nhiều disk.

## 20. Từ chối dịch vụ: bảo vệ tài nguyên

Không phải đe dọa nào cũng là lấy cắp dữ liệu. Một query nặng có thể làm user hợp lệ không truy cập được dịch vụ.

### 20.1. Các nguồn DoS

- Regex không kiểm soát, không có index phù hợp.
- Aggregation nhiều stage, join/`$lookup` lớn.
- Sort không có index, dùng nhiều RAM/disk.
- Query không giới hạn kết quả.
- Connection pool mở quá nhiều kết nối.
- Transaction kéo dài, giữ tài nguyên.
- Bulk writes không có kiểm soát.
- Backup hoặc index build chạy trong giờ cao điểm.

### 20.2. Những lớp giảm rủi ro

**Ở API:** authentication, quota/rate limiting, request size, allowlist search fields, pagination.

**Ở driver:** pool size và timeout phù hợp, retry có giới hạn.

**Ở query:** index, projection, `limit`, `maxTimeMS` theo ngữ cảnh, query shape được kiểm soát.

**Ở infrastructure:** CPU/memory/disk I/O capacity, alerts, autoscaling phù hợp, resource isolation.

**Ở operations:** backup/index maintenance window, monitoring và runbook.

### 20.3. `maxTimeMS` không thay giới hạn quyền

Ví dụ:

```javascript
db.orders.find({ status: "PAID" })
  .limit(100)
  .maxTimeMS(2000);
```

`maxTimeMS` yêu cầu MongoDB giới hạn thời gian thực thi trong điều kiện được hỗ trợ, nhưng không có nghĩa mọi tác vụ bị hủy tuyệt đối đúng 2.000 ms hoặc đã giải quyết memory/connection exhaustion.

Không dùng `maxTimeMS` để bù cho việc client có thể chạy pipeline tùy ý.

### 20.4. Khả năng sẵn sàng không chỉ dựa vào replica set

Replica set giúp chịu lỗi một số node, nhưng không bảo vệ khỏi:

- Lệnh xóa hợp lệ nhưng sai do con người.
- Credential admin bị lộ.
- Query quá nặng lan lên các node.
- Sự cố cả region.
- Corruption được phát hiện muộn.

Cần backup/restore, quota và chính sách vận hành khác.

## 21. Replica set và sharded cluster có thêm trust boundaries

### 21.1. Replica set

Các member truyền dữ liệu replication và tham gia election. Cần:

- Internal authentication.
- TLS giữa member trong phạm vi triển khai.
- Chứng chỉ/keyfile có vòng đời bảo mật.
- Network chỉ cho phép member cần thiết.
- Theo dõi election, lag và thay đổi cấu hình.

```text
Application
    |
   TLS/AuthN
    |
  Primary  ---- replication ---> Secondary A
    |                              |
    +---- replication ----------> Secondary B
```

Một secondary vẫn chứa bản sao dữ liệu nhạy cảm. **Không chỉ mã hóa/kiểm soát primary**.

### 21.2. Sharded cluster

Sharded cluster có thêm:

```text
App -> mongos -> shard replica sets
          |
          +-> config server replica set
```

Bề mặt cần bảo vệ bao gồm:

- Các `mongos` được ứng dụng truy cập.
- Shard endpoints và internal auth.
- Config servers và metadata sharding.
- Admin/automation hoạt động balancer, zone, resharding.
- Kết nối mạng giữa các thành phần.

Không cho người dùng ứng dụng **kết nối trực tiếp shard member** chỉ để “bỏ qua một lớp định tuyến” nếu việc đó vi phạm mô hình truy cập.

### 21.3. Metadata cũng là tài sản nhạy cảm

Thông tin sharding/cluster metadata có thể tiết lộ topology, namespace và cách phân bố tenant. Sửa sai metadata có thể gây mất khả năng định tuyến dữ liệu.

Không sửa thủ công `config.*` bằng CRUD ngoài quy trình MongoDB hỗ trợ.

## 22. Atlas và self-managed: cùng mục tiêu, khác phần việc

### 22.1. Khi dùng Atlas

Một số thành phần vận hành hạ tầng được Atlas quản lý theo sản phẩm/gói dịch vụ, nhưng đội phát triển vẫn chịu trách nhiệm:

- Thiết kế application authentication/authorization.
- Cấp quyền database users và quản lý Atlas project/organization access.
- Bảo vệ credentials/API keys.
- Cấu hình IP access list/private connectivity.
- Chọn encryption/KMS nếu use case yêu cầu.
- Bật/audit/monitoring phù hợp khả năng tier.
- Quản lý dữ liệu, retention, schema, indexes và backup/restore policy.

Không nói “Atlas an toàn sẵn nên app không cần kiểm tra tenant”.

### 22.2. Khi self-managed

Nhóm vận hành còn phải đảm nhận:

- Cấu hình mongod/mongos, user auth, internal auth.
- TLS certs/keyfiles.
- OS patching, network/firewall.
- Storage encryption, disk permissions.
- Backup orchestration, testing restore.
- Monitoring/logging/auditing theo bản sử dụng.
- Upgrades và xử lý CVE.

### 22.3. Feature parity không tuyệt đối

Ví dụ:

- Cơ chế LDAP/Kerberos/OIDC có thể phụ thuộc edition.
- Auditing server-side trên self-managed có điều kiện hỗ trợ khác giữa Community và Enterprise.
- Encryption at rest dùng engine/KMS/managed capability khác nhau.
- Một số quản trị/alerting của Atlas phụ thuộc tier.

**Đừng sao chép cấu hình Enterprise sang Community rồi giả định nó được hỗ trợ.** Hãy đọc tài liệu cho phiên bản/edition đang chạy.

## 23. Audit logging: biết ai làm gì và khi nào

### 23.1. Audit cần trả lời

- Identity nào đăng nhập?
- Từ host/IP nào?
- Đã thay đổi user/role không?
- Có thao tác quản trị bất thường không?
- Có truy cập vào dữ liệu nhạy cảm ngoài thời điểm cho phép không?
- Ai thực hiện restore/drop/change config?

### 23.2. Nguồn thông tin

- Authentication/connection events.
- MongoDB server logs.
- Auditing facility (nếu deployment hỗ trợ).
- Atlas activity/project audit logs theo cấu hình.
- Application access logs/correlation IDs.
- KMS access events.
- Cloud network/storage logs.

### 23.3. Không chỉ có “bật log”

Một logging system đáng tin cậy cần:

1. Đồng bộ thời gian các thành phần.
2. Centralized collection và hạn chế quyền chỉnh sửa.
3. Retention phù hợp điều tra/compliance.
4. Redact password, tokens, PII và query chứa dữ liệu nhạy cảm.
5. Gắn correlation IDs khi có thể.
6. Alert cho sự kiện cần chú ý.
7. Kiểm tra việc log pipeline vẫn hoạt động.

### 23.4. Audit không tự chặn tấn công

Nếu attacker đọc 50.000 document bằng credential hợp lệ, audit có thể giúp phát hiện **sau hoặc trong** sự kiện, nhưng không phải cơ chế hạn chế số lượng document được đọc. Cần RBAC, tenant auth, rate limiting, anomaly detection và egress controls.

## 24. Monitor và cảnh báo

| Tín hiệu | Rủi ro gợi ý | Hành động điều tra |
|---|---|---|
| Nhiều authentication failures | Credential guessing/config lỗi | Kiểm tra IP/user, auth logs |
| Login admin khác thường | Credential compromise | Xác minh identity, thời điểm, MFA |
| Tăng read volume/egress | Exfiltration hoặc report mới | Kiểm tra query patterns, app release |
| Drop/rename bất thường | Tampering/ransomware | Audit, role, change window |
| Tạo user/role lạ | Privilege escalation | Xem change log, revoke sau xác minh |
| CPU/IO tăng, slow queries | DoS/load regression | Explain/query shape/index |
| Disk gần đầy | Availability risk | Capacity/retention/index |
| Replication lag/election | Khả năng sẵn sàng | Kiểm tra topology, network |
| Backup thất bại | Không khôi phục được | Chạy retry/alert và restore test |
| Secret bị quét thấy trong repo | Credential exposure | Revoke/rotate, điều tra truy cập |

Không kết luận **mọi login failure đều là tấn công**: deployment sai mật khẩu mới cũng có thể tạo hàng nghìn lỗi. Cảnh báo cần context, ngưỡng và triage.

### 24.1. Metric bảo mật và metric hiệu năng cần ghép

Ví dụ lưu lượng đọc tăng:

```text
T1: release report mới
T2: read throughput tăng 8x
T3: egress tăng
```

Đây có thể là nhu cầu hợp lệ hoặc exfiltration. Phải đối chiếu change calendar, service identity, query shape và mục tiêu business thay vì tự động chặn toàn bộ traffic mà không điều tra.

## 25. Backup và khả năng khôi phục: lớp sống còn

### 25.1. Replication không phải backup

Nếu một admin vô tình chạy:

```javascript
db.orders.deleteMany({ status: "PAID" });
```

trên production, thao tác xóa **được replication** đến secondary khi nó là thao tác hợp lệ. Replica set không tự giữ bản copy “trước khi xóa” để rollback theo yêu cầu nghiệp vụ.

**Không chạy lệnh ví dụ trên ở production**; nó chỉ minh họa tính lan truyền của thao tác hợp lệ.

### 25.2. Backup cần tách blast radius

Một phương án phòng ransomware có thể gồm:

- Backup credentials **khác** tài khoản quản trị production.
- Object storage/backup service với quyền hạn tách biệt.
- Backup immutability hoặc retention lock khi hỗ trợ.
- Mã hóa backup và bảo vệ keys.
- Lịch sao lưu và point-in-time recovery phù hợp yêu cầu.
- Kiểm thử restore định kỳ vào môi trường cách ly.
- Theo dõi backup success, age và restore time.

### 25.3. RPO và RTO

**RPO — Recovery Point Objective:** mức dữ liệu tối đa có thể mất khi khôi phục.

**RTO — Recovery Time Objective:** thời gian tối đa chấp nhận được để phục hồi dịch vụ.

Ví dụ:

```text
RPO = 15 phút
RTO = 2 giờ
```

Nghĩa là kiến trúc cần khả năng phục hồi đáp ứng mục tiêu đó **trong điều kiện đã thử nghiệm**. Không coi đây là SLA đã đạt chỉ vì có snapshot hàng ngày.

### 25.4. Restore drill phải thật

Một bài kiểm thử restore nên xác minh:

1. Backup có thể truy cập bằng danh tính khôi phục.
2. Keys cần thiết còn sẵn.
3. Dữ liệu được giải mã và đọc.
4. Index/constraints/sharding metadata được khôi phục theo phương pháp backup.
5. Ứng dụng kết nối và kiểm thử dữ liệu quan trọng.
6. Thời gian restore thực tế đáp ứng RTO dự kiến.
7. Có log/bằng chứng hoàn thành và người chịu trách nhiệm.

## 26. Sự cố do người nội bộ và quyền quản trị

### 26.1. Tại sao người có quyền vẫn là một threat actor?

Họ có thể:

- Xuất dữ liệu vượt phạm vi được giao.
- Xóa nhầm collection.
- Cấp quyền quá rộng.
- Để lộ backup hoặc connection string.
- Vô tình tắt audit/monitoring.

Threat modeling không đồng nghĩa nghi ngờ mọi nhân viên; nó là cách thiết kế **quy trình và công cụ giảm tác động của lỗi/nguy cơ**.

### 26.2. Separation of duties

Ví dụ:

```text
App developer:
  Có quyền deploy service, không có DB root production.

DB operator:
  Có quyền quản trị MongoDB, không đọc client-side encryption keys.

Security officer:
  Có quyền xem audit, không tự sửa dữ liệu đơn hàng.

Backup operator:
  Có quyền kiểm tra/khôi phục trong phạm vi,
  không có quyền xóa mọi bản backup.
```

### 26.3. Break-glass access

Trường hợp khẩn cấp cần quyền cao có thể dùng tài khoản **break-glass**:

- Lưu và cấp phát qua quy trình có kiểm soát.
- MFA ở lớp quản trị/identity provider nơi có hỗ trợ.
- Giới hạn thời gian/quyền.
- Audit chặt và review sau sự kiện.
- Rotate credential khi cần.

Không dùng break-glass như tài khoản daily của ứng dụng.

## 27. DevSecOps và chuỗi cung ứng

### 27.1. Bảo vệ từ code đến runtime

```text
Source -> CI -> Artifact -> Deploy -> Application -> MongoDB
   |       |       |          |           |         |
 secret  SBOM    sign      runtime     RBAC/TLS   audit
 scan    deps    image     policies    validation  backup
```

Những cơ chế cụ thể tùy tổ chức, nhưng các câu hỏi cần có:

- Ai được sửa MongoDB connection settings?
- Pipeline có thể đọc secret production không?
- Có phát hiện dependency vulnerabilities không?
- Image có provenance/signing không?
- Có cơ chế rollback không?
- Có review schema/index/privileges migration không?

### 27.2. Không đưa credential vào file thử nghiệm

Ví dụ URI chống chỉ định:

```text
mongodb://admin:SuperSecretPassword@db.internal:27017/admin
```

Không commit URI như vậy dù repository private. Khi sử dụng secret URI, nên cấu hình qua secret manager/identity phù hợp và log **URI đã redacted**.

### 27.3. Secret lộ: xóa khỏi Git chưa đủ

Nếu password đã được commit, xóa ở commit mới **không đảm bảo** secret đã biến mất khỏi clone, history hoặc logs. Cần **rotate/revoke** credential và kiểm tra những lần dùng trái phép.

## 28. Lab: hình dung các lớp bảo vệ

Phần lab chỉ sử dụng **MongoDB cá nhân hoặc môi trường được phép**. Không thử đánh giá lỗ hổng hệ thống không thuộc quyền quản trị.

### 28.1. Tạo database và dữ liệu đơn giản

```javascript
const lab = db.getSiblingDB("security_lab_327");
const orders = lab.ordersLab327;

// Chỉ nạp vào collection mới/rỗng.
if (orders.countDocuments({}) !== 0) {
  throw new Error("Collection da co du lieu; chon lab moi");
}

orders.insertMany([
  { _id:"O1", tenantId:"T01", status:"CREATED", total:100000 },
  { _id:"O2", tenantId:"T02", status:"PAID", total:250000 },
  { _id:"O3", tenantId:"T01", status:"PAID", total:500000 }
]);
```

### 28.2. Kiểm tra logic truy vấn có tenant

```javascript
const authorizedTenant = "T01";

orders.find({
  tenantId: authorizedTenant
}, {
  _id: 1,
  tenantId: 1,
  status: 1
});
```

Ứng dụng T01 không nên nhận O2 nếu O2 thuộc T02. Kiểm tra này minh họa **business authorization**, không chứng minh server MongoDB đã tự áp row-level policy.

### 28.3. Khảo sát role trong lab

Nếu user có quyền thích hợp:

```javascript
db.getSiblingDB("admin").runCommand({
  usersInfo: "orders_service_lab",
  showPrivileges: true
});
```

Không phải mọi deployment/user đều có quyền xem thông tin này. Đừng dùng quyền admin production để khám phá các user khác ngoài phạm vi được phê duyệt.

### 28.4. Kiểm tra index để giảm DoS query

```javascript
orders.createIndex({ tenantId: 1, status: 1 });

orders.find({
  tenantId: "T01",
  status: "PAID"
}).explain("executionStats");
```

Index không phải cơ chế authorization, nhưng có thể giảm chi phí các query thường gặp. Với dữ liệu chỉ vài document, explain không đại diện hiệu năng production.

### 28.5. Tập xác minh kỹ thuật

Trên môi trường được phép, có thể kiểm tra:

- Kết nối không có credential phù hợp có bị từ chối không?
- Role readonly có bị từ chối khi ghi không?
- User của service A có quyền trên database service B không?
- TLS có xác minh CA/hostname đúng không?
- Backup có thể restore trong môi trường cách ly không?
- Credential cũ có hết hiệu lực sau rotation không?

Không cần thực hiện các cuộc tấn công thật để xác minh phần lớn yêu cầu bảo mật cơ bản này.

## 29. Threat modeling workshop: các bước thực hiện

### Bước 1 — Xác định scope

Ví dụ:

```text
Application: Order Management
MongoDB: Replica set 3 nodes
Environment: Production (mô hình thiết kế, không thao tác thật)
Integrations: API, analytics, backup, admin
Data sensitivity: PII + order state
```

### Bước 2 — Liệt kê tài sản

Số điện thoại, địa chỉ, đơn hàng, credential, backup, logs, encryption keys.

### Bước 3 — Vẽ luồng và trust boundaries

User → API → MongoDB; Admin → management plane; MongoDB → backup; MongoDB → monitoring.

### Bước 4 — Nêu giả định

Ví dụ:

- MongoDB không mở public.
- TLS và certificate verification được bật.
- User DB chỉ có role theo nhu cầu.
- Backend đã xác minh tenant.
- Backup account bị tách khỏi production admin.

Đánh dấu giả định nào **chưa được kiểm chứng**. Một threat model không được coi giả định thành sự thật chỉ vì nó ghi trong sơ đồ.

### Bước 5 — Dùng STRIDE tại mỗi boundary

Đặt sáu câu hỏi:

```text
Giả danh identity?
Sửa dữ liệu?
Phủ nhận thao tác?
Rò rỉ thông tin?
Từ chối dịch vụ?
Leo thang đặc quyền?
```

### Bước 6 — Đánh giá rủi ro

Tác động, khả năng, phạm vi, thời gian phát hiện, khả năng khôi phục, yêu cầu pháp lý.

### Bước 7 — Map controls

Network, TLS, AuthN, AuthZ, app validation, encryption, backups, monitoring và response.

### Bước 8 — Kiểm chứng

Lấy bằng chứng cấu hình, test quyền, restore drill, log alerts, secret scanning.

### Bước 9 — Giao owner và deadline

Một item không có owner và tiêu chí hoàn thành vẫn là rủi ro chưa xử lý.

### Bước 10 — Cập nhật khi hệ thống thay đổi

Mỗi thay đổi về topology, dịch vụ kết nối, dữ liệu nhạy cảm, role, KMS hoặc backup có thể mở thêm bề mặt tấn công.

## 30. Kịch bản sự cố 1: credential ứng dụng bị lộ

### 30.1. Kịch bản

Một token/URI của `orders_service` xuất hiện trong CI log. Tài khoản có `readWrite` trên database `shop`.

### 30.2. Điều gì có thể xảy ra?

Nếu attacker truy cập được mạng MongoDB, họ có thể đọc/ghi trong **phạm vi role**. Nếu service có `root`, blast radius nghiêm trọng hơn.

### 30.3. Những lớp giúp giảm thiệt hại

- Private network: ngăn truy cập trực tiếp từ nguồn không được phép.
- TLS: bảo vệ truyền tải, nhưng không chặn người có credential hợp lệ.
- RBAC: giới hạn phạm vi quyền.
- Audit: phát hiện identity/IP/query bất thường.
- Backup: hỗ trợ phục hồi dữ liệu bị sửa/xóa.
- Secrets rotation: vô hiệu hóa thông tin đã lộ.

### 30.4. Quy trình ứng phó có kiểm soát

1. Xác minh phạm vi secret và hệ thống bị ảnh hưởng.
2. Giới hạn quyền/phiên truy cập nghi vấn theo incident policy.
3. Phát hành credential mới và chuyển service.
4. Revoke/rotate credential lộ.
5. Xem audit/logs để đánh giá truy cập trái phép.
6. Đối chiếu tính toàn vẹn dữ liệu và khôi phục nếu cần.
7. Xử lý nguồn lộ secret trong CI/log/repo.
8. Rút kinh nghiệm và thêm kiểm soát phòng ngừa.

**Không chỉ xóa dòng log là coi đã xử lý xong sự cố.**

## 31. Kịch bản sự cố 2: query động làm lộ dữ liệu tenant

### 31.1. Kịch bản

API nhận:

```json
{
  "filter": {
    "tenantId": "T01"
  }
}
```

rồi chuyển nguyên `filter` vào MongoDB.

### 31.2. Vấn đề

Client có thể thay đổi cấu trúc filter. Nếu backend coi filter do client tạo là biểu thức được tin cậy, việc truy cập vượt tenant có thể xảy ra ngay cả khi database user có quyền hợp lệ.

### 31.3. Cách thiết kế đúng

Backend lấy `tenantId` từ authentication context, validate business parameters, tự xây filter cố định và chỉ cho phép các field/sort đã định nghĩa.

```javascript
const filter = {
  tenantId: authenticatedContext.tenantId,
  status: validatedStatus
};

db.orders.find(filter);
```

Cần test âm tính để bảo đảm một request từ tenant T01 **không thể** truy cập document T02.

## 32. Kịch bản sự cố 3: xóa dữ liệu và backup cùng blast radius

### 32.1. Kịch bản

Attacker có credential admin, xóa collection và dùng cùng tài khoản đó xóa luôn object storage backup.

### 32.2. Vì sao replication không đủ?

Delete/drop hợp lệ được sao chép sang secondary. Nếu backup nằm trong cùng phạm vi quyền, mọi bản khôi phục có thể biến mất.

### 32.3. Biện pháp

- Separate backup account và namespace/cloud account khi hợp lý.
- Immutable backup/retention lock.
- KMS access controls và kế hoạch phục hồi keys.
- Audit admin và backup actions.
- Restore drills và RPO/RTO mục tiêu.

Đây là ví dụ rõ nhất cho nguyên tắc **defense in depth**: backup phải độc lập đủ để tồn tại khi một lớp quản trị production thất bại.

## 33. Kịch bản sự cố 4: nội gián có quyền đọc thật

Một nhân viên hỗ trợ hợp lệ có quyền đọc collection khách hàng, nhưng muốn xuất toàn bộ số điện thoại.

### 33.1. Tại sao mật khẩu và TLS không giải quyết?

Identity **không giả mạo** và connection **đúng TLS**. Rủi ro nằm ở việc quyền thật quá rộng hoặc hành vi vượt mục đích.

### 33.2. Những kiểm soát phù hợp

- Role theo công việc, giảm phạm vi export.
- API chỉ trả trường cần thiết.
- Truy cập dữ liệu nhạy cảm qua workflow được duyệt.
- Field-level encryption nếu đòi phân tách quyền giải mã.
- Audit, watermark, anomaly detection, DLP.
- Review quyền định kỳ.

Một hệ thống compliance quan trọng cần cả kỹ thuật và quy trình, không chỉ database config.

## 34. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
|---|---|
| Bật mật khẩu là đủ an toàn | Còn network, TLS, RBAC, app và backup |
| TLS làm credential bị lộ vô dụng | Người có credential hợp lệ vẫn có thể đăng nhập nếu chạm được endpoint |
| Private IP đồng nghĩa chỉ ứng dụng hợp lệ truy cập | Máy trong mạng vẫn có thể bị chiếm hoặc cấu hình sai |
| User `readWrite` luôn ít quyền | Có thể ghi nhiều collection trong cả database |
| DB RBAC tự lọc `tenantId` | App cần tenant-aware authorization |
| Mọi filter BSON client gửi đều an toàn | Có nguy cơ NoSQL injection/operator abuse |
| Có schema validation là không thể gian lận | Schema không xác định ownership/business authorization |
| Mã hóa at rest che dữ liệu khỏi DB admin đang truy vấn | Server có thể giải mã theo quyền hợp lệ |
| CSFLE chống mọi attacker | App có plaintext/key vẫn là mục tiêu |
| Queryable Encryption hỗ trợ mọi query như plaintext | Có giới hạn types/operators/version |
| Replica set là backup | Xóa/sửa hợp lệ có thể được replication |
| Backup đã tạo là chắc chắn restore được | Phải test restore + keys |
| Audit log tự chặn hành vi sai | Audit chủ yếu hỗ trợ phát hiện/điều tra |
| Không mở port public thì không có injection | Lỗi API vẫn là đường tấn công |
| Mọi auth failure là brute force | Có thể do lỗi triển khai/cấu hình |
| Một admin account chung giúp dễ quản trị | Khó truy cứu và tăng blast radius |
| Secret xóa khỏi HEAD Git là an toàn | Có thể còn trong history/clone/log |
| `bindIp: 0.0.0.0` chỉ là tiện cấu hình | Tăng bề mặt tiếp nhận kết nối |
| Tắt kiểm tra TLS cert không vấn đề vì đã mã hóa | Có nguy cơ mạo danh server/MITM |
| Bật tất cả audit đồng nghĩa tốt hơn | Cần cân bằng dữ liệu nhạy cảm, chi phí và giá trị log |
| MongoDB Atlas quản lý hết bảo mật ứng dụng | App vẫn chịu trách nhiệm AuthZ, secrets, dữ liệu |
| Mọi tính năng bảo mật có ở mọi edition | Phụ thuộc version, deployment và plan |
| Mức rủi ro tự suy từ lý thuyết STRIDE | Cần gắn asset, exposure và impact thực tế |
| Một lần kiểm tra cấu hình là đủ mãi mãi | Threat model phải cập nhật theo thay đổi hệ thống |

## 35. Bài tập thực hành

### Bài 1 — Vẽ sơ đồ trust boundary

Một hệ thống gồm trình duyệt, API Java, MongoDB replica set, công cụ báo cáo và backup storage. Hãy vẽ ít nhất ba trust boundaries, ghi rõ authentication/authorization của mỗi luồng.

### Bài 2 — Phân loại CIA

Phân loại: rò rỉ địa chỉ khách, sửa số dư, mất backup, query làm cạn CPU, thay đổi user role trái phép. Với mỗi mục, nêu các thuộc tính CIA bị ảnh hưởng và tại sao.

### Bài 3 — STRIDE

Với endpoint `GET /orders/{id}`, hãy nêu một threat cho từng chữ trong STRIDE. Không cần giả định attacker đã có quyền admin.

### Bài 4 — Ưu tiên rủi ro

Chọn ba rủi ro: port MongoDB public, thiếu audit login admin, backup không được test restore. Hãy lập risk register gồm likelihood, impact, owner, control và bằng chứng.

### Bài 5 — Đặc quyền tối thiểu

Một service chỉ cần đọc `shop.products` và ghi `shop.orders`. Vì sao role `root` không phù hợp? So sánh built-in `readWrite` database với custom role theo collection.

### Bài 6 — Tenant isolation

Một user thuộc tenant T01 đoán được order ID của T02. Hãy sửa điều kiện `findOne()` và `updateOne()` để luôn ràng buộc tenant theo context đã xác thực.

### Bài 7 — NoSQL injection

Một API nhận raw JSON filter từ browser và gọi `Document.parse()` để truy vấn. Rủi ro nằm ở đâu? Hãy viết một DTO gồm các tham số giới hạn và dùng builder API để tạo filter an toàn.

### Bài 8 — TLS

Một nhóm phát hiện lỗi hostname certificate và đề xuất bật `tlsAllowInvalidHostnames` trên production. Đánh giá rủi ro và đề xuất cách sửa đúng.

### Bài 9 — Mã hóa ba lớp

Giải thích khác biệt giữa TLS, encryption at rest và CSFLE trong kịch bản:

1. Ổ đĩa bị đánh cắp.
2. Kết nối bị nghe lén.
3. Database admin có quyền đọc document nhưng không có key phía client.
4. Java app process bị chiếm.

### Bài 10 — KMS và phục hồi

Backup data được mã hóa nhưng master key bị xóa. Vì sao backup không đồng nghĩa có thể phục hồi? Hãy thiết kế trách nhiệm quản lý/rotation/recovery keys.

### Bài 11 — Replica set

Vì sao secondary cũng cần TLS, internal authentication, OS hardening và encryption at rest? Việc xóa document ở primary có được secondary “cứu” tự động không?

### Bài 12 — Sharding

Một hệ thống có `mongos` public nhưng shard private. Những threat boundaries nào còn tồn tại? Vì sao config servers và cluster metadata cũng cần bảo vệ?

### Bài 13 — DoS

Ứng dụng cho phép người dùng gửi bất kỳ aggregation pipeline nào. Hãy đề xuất ít nhất sáu biện pháp phòng vệ gồm allowlist, timeout, indexes, quotas, pool và monitoring.

### Bài 14 — Secret rotation

Credential của `orders_service` lộ trong CI log. Viết quy trình ứng phó và rotation để không làm sập ứng dụng, đồng thời hạn chế người có credential cũ tiếp tục truy cập.

### Bài 15 — Audit and monitoring

Bạn thấy 100 login failures trong một phút, read traffic tăng và admin user mới xuất hiện. Hãy phân loại alert, thông tin cần điều tra, nguồn log phù hợp và cách tránh kết luận khi chưa có chứng cứ.

### Bài 16 — Backup vs replication

Một admin vô tình xóa collection lúc 10:05. Cụm có ba node replica set. Hãy giải thích vì sao replication không bảo đảm rollback, rồi thiết kế RPO/RTO và restore drill.

### Bài 17 — Atlas vs self-managed

Lập bảng ai chịu trách nhiệm cho OS patching, DB users, application AuthZ, VPC rules, backup policy, KMS keys, auditing và incident response ở hai mô hình triển khai.

### Bài 18 — Phân tích quyền nội bộ

Một nhân viên support cần tra cứu trạng thái đơn hàng nhưng không cần xem PII đầy đủ. Hãy đề xuất cách giảm dữ liệu lộ từ API, DB roles và field encryption khi phù hợp.

### Bài 19 — Threat model đầy đủ

Thiết kế threat model cho nền tảng:

```text
User -> API -> MongoDB sharded cluster
               |
               +-> Analytics ETL
               +-> Daily backup
               +-> Audit/monitoring
```

Yêu cầu đầu ra:

1. Danh sách tài sản.
2. Sơ đồ data flow và trust boundaries.
3. Ít nhất 10 threats thuộc các nhóm STRIDE.
4. Risk register ưu tiên.
5. Map threat → preventive/detective/recovery controls.
6. Bằng chứng kiểm thử và owner.

### Bài 20 — Tabletop incident response

Giả sử có bằng chứng admin credential bị chiếm, dữ liệu khách hàng bị đọc và vài collection bị xóa. Hãy lập kế hoạch:

- Containment không làm mất bằng chứng.
- Thu hồi credential, điều tra log và egress.
- Phân loại dữ liệu và mức tác động.
- Restore trong môi trường cách ly.
- Đối chiếu tính toàn vẹn.
- Khôi phục dịch vụ và rút kinh nghiệm.

Không thực hiện thao tác xóa hoặc điều tra trái quyền trên hệ thống thật.

## 36. Checklist an toàn trước và sau triển khai

### Trước khi production go-live

1. MongoDB endpoints chỉ có thể tới từ mạng và identity được cho phép.
2. TLS bắt buộc và certificate/hostname được xác minh đúng.
3. Client authentication và internal member authentication đã được cấu hình.
4. Mỗi service có DB user/identity riêng, không dùng chung `root`.
5. Quyền đã review theo **principle of least privilege**.
6. API áp tenant/business authorization và validate input.
7. Query/pagination/aggregation không cho user điều khiển operator tùy ý.
8. Data files/backups/keys được bảo vệ theo yêu cầu nhạy cảm.
9. Audit/monitoring có owner, retention và alert.
10. Backup có chính sách RPO/RTO và bài test restore.
11. Secret rotation và revoke có runbook.
12. Bản vá MongoDB/OS/driver và CVE review nằm trong lifecycle.

### Trong vận hành

1. Review network exposure và IAM drift định kỳ.
2. Kiểm tra service account privileges.
3. Xác minh TLS certificate expiration/rotation.
4. Theo dõi auth failures, admin actions, data egress.
5. Theo dõi query latency/slow operations và capacity.
6. Chạy restore drills, kiểm tra cả KMS/key vault.
7. Kiểm tra secrets trong CI/repo/log.
8. Cập nhật threat model khi thêm service, region, shard hoặc dữ liệu nhạy cảm.
9. Đánh giá audit retention và quyền đọc log.
10. Duy trì playbook incident response, contact owner và đường escalation.

## 37. Tổng kết

**Threat model là cách suy nghĩ từ tài sản và đường tấn công đến kiểm soát.** Trong MongoDB, các rủi ro điển hình gồm lộ credential, truy cập ngoài tenant, NoSQL injection, lạm dụng quyền quản trị, rò rỉ backup, từ chối dịch vụ và phá hoại dữ liệu. STRIDE giúp không bỏ sót các lớp nguy cơ quan trọng, còn risk register giúp ưu tiên xử lý có trách nhiệm.

**Defense in depth là nguyên tắc cốt lõi.** Network isolation giảm bề mặt tiếp cận; TLS bảo vệ đường truyền; authentication xác minh identity; RBAC và application AuthZ giới hạn hành động; schema validation giúp tính toàn vẹn dữ liệu; encryption at rest và client-side encryption bảo vệ trước các kịch bản đọc trái phép khác nhau; audit/monitoring phát hiện; backup và restore giảm hậu quả khi sự cố đã xảy ra.

**Không kiểm soát nào là “nút an toàn tuyệt đối”.** TLS không cứu credential đã bị chiếm, encryption at rest không thay quyền DB, RBAC không tự lọc tenant trong một collection dùng chung, replica set không thay backup, còn backup không có restore drill và key recovery thì chưa bảo đảm phục hồi.

Một hệ thống MongoDB đáng tin cậy cần **phân quyền tối thiểu, ranh giới tin cậy rõ ràng, vận hành quan sát được và khả năng khôi phục đã kiểm chứng**. Threat model phải được xem lại mỗi khi kiến trúc, dữ liệu nhạy cảm, identity hoặc ranh giới hệ thống thay đổi.

## Tài liệu tham khảo

- [MongoDB — Security Checklist for Self-Managed Deployments](https://www.mongodb.com/docs/manual/administration/security-checklist/): các lớp kiểm soát quan trọng, hardening và bảo vệ dữ liệu.
- [MongoDB — Security](https://www.mongodb.com/docs/manual/security/): authentication, authorization, TLS, encryption và auditing.
- [MongoDB — Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/): vai trò, privilege và giới hạn quyền.
- [MongoDB — Configure TLS](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/): cấu hình TLS và xác minh kết nối.
- [MongoDB — Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/): mã hóa field phía ứng dụng.
- [MongoDB — Queryable Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/): truy vấn trên field được mã hóa cùng các giới hạn.
- [MongoDB — Encryption Key Management](https://www.mongodb.com/docs/manual/core/csfle/fundamentals/manage-keys/): DEK, CMK, key vault và KMS.
- [OWASP — Threat Modeling](https://owasp.org/www-community/Threat_Modeling): phương pháp xác định threats và trust boundaries.
- [OWASP — NoSQL Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/NoSQL_Security_Cheat_Sheet.html): validate input, least privilege và phòng injection.
