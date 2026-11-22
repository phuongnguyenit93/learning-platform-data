# Rà soát cấu hình trước khi đưa hệ thống ra môi trường thật

Một MongoDB database có thể chạy đúng chức năng trên máy lập trình nhưng vẫn **không đủ an toàn để đưa lên production**. Ứng dụng vẫn insert, update và query thành công, trong khi cluster đang mở cổng ra Internet, chưa bật authentication, dùng tài khoản toàn quyền, không xác thực chứng chỉ TLS, không có backup khôi phục được hoặc log vô tình chứa dữ liệu nhạy cảm.

Vì vậy, **rà soát cấu hình trước khi đưa hệ thống ra môi trường thật** (*production security readiness review*) là một hoạt động có tiêu chí, bằng chứng và người chịu trách nhiệm. Mục tiêu không phải chỉ đánh dấu “đã bật bảo mật”, mà là trả lời được:

- Ai có thể kết nối tới MongoDB, từ mạng nào và bằng cơ chế nào?
- Kết nối có được mã hóa và **xác thực đúng máy chủ** hay không?
- Từng tài khoản chỉ có đúng những quyền nghiệp vụ cần thiết không?
- Các node của replica set và sharded cluster xác thực lẫn nhau ra sao?
- Secrets, private keys, backup files và bản sao dữ liệu được bảo vệ thế nào?
- Có thể phát hiện truy cập trái phép, thay đổi quyền và hành vi bất thường không?
- Khi mất dữ liệu hoặc sự cố ransomware, có thể phục hồi **thực sự** trong RPO/RTO đã cam kết không?
- Các tính năng như change streams, MongoDB Search/Vector Search, analytics và hệ thống downstream có tạo thêm bề mặt rò rỉ dữ liệu không?
- Những điều kiện nào **phải chặn release** cho đến khi được khắc phục?

Bài học nằm trong chương **Bảo mật** của module **Database Engine Document MongoDB**. Nội dung áp dụng cho hai mô hình chính: **MongoDB Atlas** (dịch vụ được quản lý) và **MongoDB self-managed** (đội vận hành tự quản lý `mongod`, `mongos`, hệ điều hành, chứng chỉ và hạ tầng).

> **Nguyên tắc:** “Database hoạt động được” không đồng nghĩa “database được cấu hình an toàn”. **Mọi kết luận PASS cần có bằng chứng phù hợp với deployment**, người kiểm tra, thời điểm kiểm tra và phương án xử lý khi cấu hình thay đổi.

## 1. Xác định phạm vi của cuộc rà soát

Trước khi kiểm tra một tham số, phải biết **hệ thống thực tế gồm những gì**.

Ví dụ kiến trúc:

```text
End user / Browser
        │
        ▼
API Gateway / Load Balancer
        │
        ▼
Application services
        │
        ├── MongoDB driver / connection pool
        │           │
        │           ▼
        │     MongoDB deployment
        │       ├── mongod replica set nodes
        │       ├── mongos routers (nếu sharded)
        │       ├── config servers (nếu sharded)
        │       └── Search/Vector Search (nếu dùng)
        │
        ├── Cache / Message queue
        ├── Search index / Analytics
        ├── Embedding/AI providers
        └── Monitoring / Backup
```

Một checklist chỉ nhìn vào `mongod.conf` không thể phát hiện:

- API làm lộ connection string qua log.
- Kubernetes Secret bị cấp quyền đọc cho mọi namespace.
- Backup của MongoDB được upload vào bucket public.
- Admin dùng tài khoản root để chạy mọi service.
- Một connector CDC sao chép PII sang hệ thống khác mà không có retention.
- Search result cache trả dữ liệu thuộc tenant khác.

### 1.1. Inventory tối thiểu

Lập bảng có thể dùng trong review:

| Thành phần | Cần ghi nhận |
|---|---|
| Môi trường | Dev, staging, production |
| Deployment | Atlas Dedicated/Flex hay self-managed |
| Phiên bản | MongoDB Server, FCV, driver, Search process nếu có |
| Topology | Standalone, replica set, sharded cluster |
| Nodes/regions | Nơi đặt node và vùng dữ liệu |
| Public/private endpoints | Đường truy cập được phép |
| Ứng dụng | Những service có connection tới MongoDB |
| Identity | Database users, Atlas project users, service accounts |
| Dữ liệu | Loại dữ liệu, PII, secrets, phân loại nhạy cảm |
| Key management | TLS CA, KMS, encryption keys, rotation |
| Backups | Lịch, vị trí, encryption, restore drills |
| Observability | Logs, audit, metrics, alerts, người nhận |
| Downstream | BI, CDC, Search, Vector Search, ETL, exports |
| Owners | Ai phê duyệt và xử lý từng hạng mục |

Nếu chưa rõ MongoDB có những client và data flows nào, chưa thể kết luận an toàn sau một lần nhìn cấu hình cluster.

### 1.2. Phân loại mức độ nghiêm trọng

Một cách tổ chức cổng kiểm soát trước phát hành:

| Mức | Ví dụ | Quyết định |
|---|---|---|
| **BLOCKER** | Không có authentication; Internet-exposed DB; TLS không xác thực; quyền cross-tenant; không có backup phù hợp với dữ liệu quan trọng | **Không go-live** |
| **HIGH** | Service account có quyền rộng; chưa có kế hoạch rotation; audit thiếu cho hệ thống bắt buộc tuân thủ; không có restore test | Khắc phục hoặc có quyết định chấp nhận rủi ro được phê duyệt |
| **MEDIUM** | Log retention không rõ, alert chưa tối ưu, index/driver nâng cấp sắp tới | Gắn owner và deadline |
| **LOW** | Metadata tài sản chưa đầy đủ, quy trình vận hành cần chuẩn hóa | Theo dõi cải tiến |

Mức độ thực tế phải dựa trên **phân loại dữ liệu, khả năng bị khai thác và tác động kinh doanh**; bảng chỉ là khung minh họa.

## 2. Rà soát theo mô hình trách nhiệm chia sẻ

MongoDB Atlas và self-managed khác nhau về việc ai chịu trách nhiệm vận hành, nhưng không mô hình nào khiến ứng dụng được miễn trách nhiệm bảo mật dữ liệu.

### 2.1. MongoDB Atlas

Atlas quản lý nhiều phần của deployment, ví dụ provisioning, hệ thống nền, cập nhật và một số lớp backup/monitoring tùy tier. Nhưng tổ chức vẫn phải kiểm soát:

- Atlas Organization/Project roles;
- Network access lists và private connectivity;
- Database users, service accounts, credentials;
- Cấu hình mã hóa/KMS được sử dụng;
- Application authorization và tenant isolation;
- Retention, data classification, exports;
- Backup/PITR plan theo tier;
- Atlas API keys, access tokens;
- Cấu hình Search/Vector Search và downstream data access;
- Chính sách theo dõi sự cố và review quyền.

**Managed không có nghĩa “an toàn tự động cho mọi cách sử dụng”.**

### 2.2. MongoDB self-managed

Ngoài các trách nhiệm trên, đội vận hành còn phải tự quản lý:

- Hệ điều hành, kernel, container runtime và patching;
- Firewall, network segmentation, DNS, host hardening;
- Cài đặt/phiên bản `mongod`, `mongos`, config servers;
- TLS certificate/key lifecycle;
- Internal member authentication;
- Filesystem permissions và storage encryption;
- Process users và service manager;
- Audit logging/configuration tùy edition;
- Replication, backup agents, monitoring agents;
- Resource limits, disk, time sync, failover;
- Restore và disaster recovery.

Một máy phát triển `mongod --bind_ip_all` rồi đưa lên Internet không trở thành production chỉ vì có đủ RAM.

### 2.3. Checklist phải theo deployment thật

| Hạng mục | Atlas | Self-managed |
|---|---|---|
| Database authentication | Cấu hình database users, roles | Phải bật/kiểm tra `authorization` và users |
| TLS phía client | Dùng TLS endpoint đúng, kiểm tra cert | Tự cấp cert/CA, thiết lập `requireTLS` |
| Network | IP access list, peering/private endpoint | Firewall/security groups, VPC, bindIp |
| Internal member auth | Atlas quản lý theo deployment | Phải cấu hình keyFile hoặc X.509 phù hợp |
| Secrets | Tài khoản/URI/Atlas API keys | Cả những secrets trên + TLS private keys |
| Backup | Chọn/gắn retention, PITR theo tier | Tự triển khai và test |
| Logging/audit | Các tính năng Atlas/tier hỗ trợ | Tự cấu hình và bảo vệ |
| Version patches | Atlas lifecycle và kế hoạch upgrade | Tự quản lý server/OS/driver |
| Data authorization | Ứng dụng chịu trách nhiệm | Ứng dụng chịu trách nhiệm |

## 3. Threat model trước khi xem tham số

Một review hiệu quả bắt đầu từ **tài sản và đối tượng đe dọa**.

### 3.1. Tài sản cần bảo vệ

- Dữ liệu khách hàng, thông tin tài chính, PII;
- Đơn hàng, hợp đồng và lịch sử giao dịch;
- Credentials, refresh tokens, API keys;
- Metadata tenant, RBAC/ACL;
- Backup, snapshots, exports;
- Search indexes và embeddings của tài liệu nhạy cảm;
- Audit logs;
- Encryption keys;
- Connection strings và cấu hình hạ tầng.

### 3.2. Đường tấn công có thể xảy ra

```text
Internet
   │
   ├── Public DB endpoint
   ├── Stolen application credentials
   ├── Compromised CI/CD secrets
   ├── Misconfigured backup bucket
   ├── Application injection / broken authorization
   └── Exposed monitoring or management API
           │
           ▼
       MongoDB / dữ liệu
```

Không chỉ xem “có ai biết password không”. Đối tượng tấn công có thể là:

- Người ngoài Internet;
- Nhân viên nội bộ có quyền rộng;
- Một service bị compromise;
- Một tenant cố truy cập dữ liệu tenant khác;
- Nhà cung cấp/connector có quyền truy xuất dữ liệu;
- Một deployment pipeline bị chiếm quyền.

### 3.3. Mô hình phòng vệ nhiều lớp

Để đọc một document nhạy cảm, attacker phải vượt qua nhiều lớp độc lập:

```text
Network boundary
   ↓
TLS verification
   ↓
Authentication
   ↓
Database RBAC
   ↓
Application authorization
   ↓
Tenant/document ACL
   ↓
Data classification / field filtering
   ↓
Logging & detection
```

**Không dùng một lớp để thay toàn bộ các lớp khác**. Ví dụ IP allowlist không thay password/TLS; database read role không tự biết user nào được đọc một đơn hàng.

## 4. Rà soát mạng: database có bị phơi ra ngoài không?

### 4.1. Nguyên tắc mặc định

MongoDB không nên được mở tới toàn bộ Internet chỉ để ứng dụng kết nối thuận tiện.

Các câu hỏi cần có câu trả lời:

1. Những host/subnet nào **cần** kết nối?
2. Cổng `27017` hoặc cổng cấu hình khác có bị public không?
3. Có đường private networking hợp lệ không?
4. Kết nối từ CI/CD, admin và support có qua đường kiểm soát không?
5. Egress từ app tới MongoDB có bị hạn chế theo policy không?
6. Có bastion/VPN/zero-trust access cho admin không?
7. Có network diagrams và owners cập nhật không?

### 4.2. Atlas Network Access

Đối với Atlas, kiểm tra:

- Atlas project IP access list có bị mở quá rộng không;
- Có entry kiểu `0.0.0.0/0` hoặc IPv6 tương đương không;
- Các IP cũ của nhân viên, máy CI, đối tác đã được thu hồi chưa;
- Có sử dụng Private Endpoint, peering hoặc private networking khi cần không;
- Các network identities được phép có đúng theo thiết kế không.

**IP access list là kiểm soát mạng, không phải cơ chế authentication.** Một IP đã được phép nhưng dùng credentials sai vẫn phải bị từ chối. Ngược lại, một credential hợp lệ không nên mở đường từ mọi nơi.

Cấu hình allow-all có thể xuất hiện trong tutorial dev, nhưng là **BLOCKER** khi không có ngoại lệ production được phê duyệt và biện pháp bù đắp phù hợp.

### 4.3. Self-managed: `bindIp` và firewall

Ví dụ một bản cấu hình khái niệm:

```yaml
# mongod.conf - minh họa, không copy nguyên sang production
net:
  port: 27017
  bindIp: "127.0.0.1,10.10.1.25"
```

`bindIp` xác định các network interfaces mà `mongod` lắng nghe. Nó **không thay thế host firewall, security groups, Kubernetes NetworkPolicy hoặc phân vùng mạng**.

Nếu ứng dụng chạy ở subnet khác, cần kết hợp đúng interface và firewall rules. Không “sửa nhanh” bằng cách mở `0.0.0.0` trên một host có public IP.

### 4.4. Kiểm tra từ cả hai phía

- Từ application subnet: kết nối phải thành công với TLS và credentials đúng.
- Từ mạng không được phép: kết nối phải bị từ chối theo đường thiết kế.
- Từ admin network: chỉ đúng tài khoản và phương thức kiểm soát được phép.
- Từ Internet: không thấy cổng database nếu kiến trúc yêu cầu private-only.

Đối với production, thử kiểm tra theo scope được phép và có kế hoạch thay đổi; tránh quét mạng ngoài phạm vi được cấp quyền.

### 4.5. Không gửi client trực tiếp từ browser tới MongoDB

Browser/public mobile clients thông thường nên gọi backend API, không chứa MongoDB connection string có database credentials.

```text
Browser / Mobile
       │ HTTPS + user identity
       ▼
Application API
       │ MongoDB driver + service identity
       ▼
MongoDB
```

Nếu nhét credentials vào JavaScript frontend, người dùng có thể trích xuất chúng và vượt qua validation/authorization ở backend.

## 5. TLS: mã hóa chưa đủ, phải xác thực đúng máy chủ

TLS bảo vệ data in transit khi client kết nối tới database và khi các thành phần giao tiếp theo kiến trúc được hỗ trợ.

Review cần xác nhận:

- TLS thực sự được yêu cầu;
- Chứng chỉ máy chủ được ký bởi CA được tin cậy;
- Hostname trong URI khớp certificate SAN;
- Chứng chỉ chưa hết hạn;
- Client không tắt certificate/hostname verification;
- Protocol/ciphers phù hợp với policy và phiên bản;
- Private keys có quyền filesystem nghiêm ngặt;
- Có quy trình rotation trước ngày hết hạn.

### 5.1. MongoDB Atlas URI

Một ví dụ an toàn về cấu trúc:

```text
mongodb+srv://APP_USER:<PASSWORD>@cluster.example.mongodb.net/
  ?retryWrites=true&w=majority
```

Dấu xuống dòng trong ví dụ chỉ để dễ đọc; URI thực là **một chuỗi liên tục**, và tên host chỉ là placeholder.

`mongodb+srv` dùng DNS SRV/TXT để tìm hosts/options. Với Atlas, dùng connection string do Atlas cấp và **xác thực TLS đầy đủ**. Không hardcode URI có password trong mã nguồn.

### 5.2. Các tùy chọn TLS nguy hiểm

Không dùng trong production:

```text
tlsAllowInvalidCertificates=true
tlsAllowInvalidHostnames=true
tlsInsecure=true
```

Các tùy chọn này có thể làm suy yếu hoặc bỏ qua phần xác minh chứng chỉ. Một ứng dụng “đã mã hóa kết nối” nhưng không xác minh đúng server vẫn có thể chịu rủi ro man-in-the-middle.

Với Java MongoDB Driver, dùng truststore/CA hợp lệ thay vì viết `TrustManager` chấp nhận mọi chứng chỉ.

### 5.3. Self-managed `requireTLS`

Một cấu hình tham khảo:

```yaml
net:
  port: 27017
  bindIp: "127.0.0.1,10.10.1.25"
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/server.pem
    CAFile: /etc/mongodb/tls/ca.pem
```

Ví dụ **chỉ là khung cấu hình**; production phải dùng đường dẫn cert thật, cấu hình node cụ thể, permissions, certificate chain và khả năng kết nối của clients. Đừng bật `requireTLS` đột ngột khiến replica set/client mất kết nối; rollout cần kế hoạch tương thích và rollback.

### 5.4. TLS nội bộ

Nếu MongoDB có nhiều members, cần kiểm tra cả:

- TLS giữa clients và server;
- TLS giữa các members/router/config servers theo topology;
- Internal authentication;
- TLS của monitoring/backup agents;
- TLS của Search/analytics connectors nếu dùng.

Một client URI có TLS **không tự chứng minh** mọi đường kết nối nội bộ đã đúng policy.

## 6. Authentication: không được để database ở trạng thái open

### 6.1. Self-managed `authorization`

Trong self-managed, một cấu hình thường cần:

```yaml
security:
  authorization: enabled
```

Nếu dùng replica set với keyfile internal authentication, cấu hình có thể gồm:

```yaml
security:
  authorization: enabled
  keyFile: /etc/mongodb/secrets/replica-key
```

**Không copy và restart ngay** trên production. Việc triển khai authentication cho replica set/sharded cluster phải theo thứ tự, đặc biệt khi trước đó đang chạy không auth hoặc chưa tạo admin user. Làm sai có thể khóa người vận hành khỏi cluster hoặc làm các members không xác thực nhau.

### 6.2. Các cơ chế authentication

MongoDB hỗ trợ nhiều cơ chế tùy edition/version/triển khai:

| Cơ chế | Ngữ cảnh |
|---|---|
| SCRAM-SHA-256 | Username/password phổ biến |
| SCRAM-SHA-1 | Legacy compatibility, nên xem policy và nâng cấp |
| X.509 | Certificate-based auth cho clients/members theo cấu hình |
| LDAP/Kerberos | Tùy edition/mô hình tích hợp hỗ trợ |
| OIDC | Tùy server/Atlas/driver version và cấu hình identity provider |
| Atlas cloud/IAM integrations | Theo cơ chế Atlas/tier được hỗ trợ |

Không chọn một cơ chế chỉ dựa vào tên gọi. Cần kiểm tra compatibility, identity lifecycle, revocation, MFA cho admin và yêu cầu audit.

### 6.3. MFA thuộc đúng lớp

MFA đặc biệt quan trọng cho **human admin access**, như Atlas UI, identity provider và môi trường điều hành. Một ứng dụng backend dùng service account không thường tương tác MFA theo mỗi database request; nó cần short-lived identity/secret rotation, network controls và least privilege.

Không ghi “MongoDB user có password nên hệ thống đã có MFA” nếu thực tế chỉ Atlas console có MFA.

### 6.4. Localhost exception là cơ chế bootstrap, không phải chính sách vận hành

MongoDB có cơ chế hỗ trợ tạo user quản trị đầu tiên trong một số trường hợp localhost khi chưa có users. Đó là **tình huống bootstrap** có điều kiện, không nên được dùng như một cách quản trị thường xuyên hoặc giả định luôn an toàn.

Phải có quy trình tạo admin user ban đầu trước khi khóa các đường truy cập, và xác nhận hệ thống không bị kẹt trong trạng thái thiếu tài khoản quản lý.

## 7. RBAC và nguyên tắc đặc quyền tối thiểu

Sau authentication là câu hỏi: **tài khoản được làm gì?**

Trong MongoDB, một database user có thể được cấp các built-in roles như `read`, `readWrite`, `dbAdmin`, `userAdmin`, cùng các roles cấp cluster. Những roles mạnh như `root`, `readWriteAnyDatabase`, `userAdminAnyDatabase` có phạm vi rộng và thường không phù hợp cho ứng dụng thông thường.

### 7.1. Phân chia identities

Nên có identities tách biệt:

| Identity | Mục tiêu | Quyền điển hình |
|---|---|---|
| API đọc catalog | Chỉ truy vấn collection cần thiết | Custom read role hoặc `read` đúng DB |
| Order writer | Đọc/ghi collections nghiệp vụ cụ thể | Custom role có actions giới hạn |
| Migration job | Thay schema/index theo kế hoạch | Quyền elevated có hạn sử dụng |
| Backup agent | Đọc dữ liệu cần backup theo công cụ | Role backup phù hợp |
| Monitoring agent | Thu metrics/trạng thái | Role monitoring phù hợp |
| DBA/operator | Quản trị hệ thống | Elevated role qua phê duyệt |
| Break-glass admin | Khắc phục sự cố đặc biệt | Quyền tối đa, cô lập và audit |

Không dùng chung một username/password giữa API, worker, BI connector và migration job. Khi một credential bị lộ, blast radius phải bị giới hạn.

### 7.2. Database role không phải row-level tenant ACL

Một account có quyền `read` trên collection `orders` có thể đọc **nhiều document** trong collection theo phạm vi role. MongoDB RBAC truyền thống không tự hiểu:

```text
user U1 chỉ được xem đơn hàng của tenant A
user U2 chỉ được xem đơn hàng của tenant B
```

Đây là trách nhiệm của application authorization, data access layer hoặc kiến trúc phân tách dữ liệu mạnh hơn.

Trong shared collection multi-tenant, phải có:

- Trusted tenant ID từ authentication;
- Query predicate tenant bắt buộc;
- Kiểm soát direct-by-ID access;
- Test cross-tenant;
- Không để user tự sửa scope bằng URL/body.

### 7.3. Kiểm tra quyền của phiên kết nối

Trong `mongosh`, ở môi trường được phép:

```javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
```

Lệnh này hữu ích để xem authenticated users/roles và một số privileges thực tế theo quyền được cấp. Output cụ thể phụ thuộc phiên bản/permissions.

Không chỉ nhìn danh sách roles trong manifest rồi kết luận; cần xác nhận **service account đang dùng trong production** có đúng identity và privilege set.

### 7.4. Xem users/roles với tài khoản được phép

```javascript
use admin;

db.runCommand({
  usersInfo: 1,
  showPrivileges: true
});
```

Lệnh cần quyền phù hợp, và output có thể chứa metadata về users/roles. **Không dán nguyên output vào ticket công khai**. Với ứng dụng có nhiều databases, cần kiểm tra ở đúng authentication database và role scope.

### 7.5. Quyền quản lý Search indexes và database indexes

Tạo/xóa MongoDB Search/Vector Search indexes là thao tác quản trị có tác động tới query và chi phí. Application API dùng `$search` hoặc `$vectorSearch` thông thường không nên có quyền tạo/xóa những indexes đó.

Tương tự, không để public-facing service sở hữu quyền thay users/roles hoặc drop databases.

## 8. Internal authentication trong replica set và sharded cluster

Một replica set có nhiều `mongod` phải xác thực các members với nhau. Một sharded cluster còn có `mongos` và config server replica set.

### 8.1. Vì sao chỉ bật user authentication chưa đủ?

Nếu client authentication có nhưng các members không có trust relationship được cấu hình đúng, hệ thống có thể gặp lỗi replication, failover hoặc bị lợi dụng bởi thành phần không tin cậy.

MongoDB cung cấp các cơ chế internal authentication như:

- Shared `security.keyFile` theo quy tắc triển khai;
- X.509 certificate-based member authentication;
- Các thiết lập `clusterAuthMode` theo chiến lược chuyển đổi/cấu hình.

### 8.2. Keyfile là một secret hạ tầng

Một keyfile trên disk phải được bảo vệ:

- Không lưu plaintext trong Git;
- Không gửi qua chat/email;
- Có filesystem ownership/permissions hạn chế;
- Được phân phối an toàn tới những members được phép;
- Có kế hoạch rotate;
- Có bản dự phòng theo chính sách bảo mật để khôi phục;
- Không chụp vào logs hoặc image layers.

Với Linux/POSIX, keyfile thường phải có permission chặt (chẳng hạn chỉ owner đọc). Windows có quy tắc khác; đừng copy lệnh `chmod` vào mọi môi trường rồi cho rằng đã đúng.

### 8.3. Kiểm tra topology, không đổi cấu hình tùy hứng

Các lệnh đọc trạng thái trên replica set nếu có quyền:

```javascript
rs.status();
```

Trên sharded cluster, tùy phiên bản/công cụ:

```javascript
sh.status();
```

Đây là các lệnh xem thông tin topology/status; chúng **không xác minh toàn bộ cấu hình bảo mật**. Phải kết hợp network/TLS/internal auth và operational evidence.

Đừng chạy `rs.initiate()`, `rs.reconfig()`, rotate keyfile hoặc restart tất cả members trong một bài “kiểm tra” production. Những thao tác đó là **change management** riêng.

## 9. Secrets management: không hardcode, không log, phải rotate

Các secrets MongoDB có thể gồm:

- Database usernames/passwords;
- Atlas programmatic API keys;
- Private keys của TLS certificates;
- Internal authentication keyfiles;
- KMS credentials;
- Backup encryption keys;
- Tokens của identity provider;
- Secrets của monitoring/CDC connectors.

### 9.1. Những nơi không được lưu secrets

- Source code/public repository;
- Dockerfile/container image layers;
- CI logs;
- Command line history;
- Chat/ticket không được kiểm soát;
- Frontend JavaScript/mobile bundle;
- Traces hoặc raw exception dumps;
- File `.env` đã commit vào Git;
- README copy-paste chứa password thật.

### 9.2. Mẫu đọc URI ở Java

```java
String uri = System.getenv("MONGODB_URI");

if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is missing");
}

// Trong ứng dụng thực, đưa URI cho MongoClients.create(uri)
// và quản lý MongoClient theo application lifecycle.
```

Biến môi trường có thể tốt hơn hardcode nhưng **không tự động là secret manager hoàn chỉnh**. Trong môi trường production, ưu tiên secret management được tổ chức phê duyệt, ví dụ workload identity, vault hoặc cloud secret store với policies/rotation.

### 9.3. Rotation cần hai trạng thái

Một kế hoạch rotation:

```text
1. Provision credential mới hoặc identity mới.
2. Deploy clients hỗ trợ credential mới.
3. Xác minh kết nối hoạt động.
4. Thu hồi credential cũ.
5. Kiểm tra client cũ đã được cập nhật.
6. Audit và ghi mốc rotation.
```

Với certificate/CA rotation hoặc internal auth keys, quy trình phức tạp hơn và cần xét compatibility giữa nodes trong rollout.

Không thay secret theo cách mọi application pods cùng mất kết nối rồi mới bắt đầu khôi phục.

### 9.4. Cấp quyền secrets theo service

Một service đọc catalog không cần quyền đọc keyfile của replica set. Một monitoring service không cần API key của payment provider. Secrets phải được phân quyền theo **need-to-know** và tài khoản vận hành được kiểm toán.

## 10. Kiểm tra encryption at rest và key management

Có hai lớp khác nhau:

- **Encryption in transit:** TLS bảo vệ kết nối.
- **Encryption at rest:** bảo vệ dữ liệu được lưu trên disk/snapshot/backup theo cơ chế triển khai.

Trong Atlas, encryption at rest được cung cấp theo tier/mô hình; một số lựa chọn hỗ trợ **customer-managed keys** qua KMS theo điều kiện. Trong self-managed, các lựa chọn gồm disk/volume encryption và các tính năng MongoDB Enterprise được cấp phép/hỗ trợ theo phiên bản.

### 10.1. Những câu hỏi phải xác nhận

1. Dữ liệu MongoDB trên disk có encryption không?
2. Snapshots, backups và exports có encryption tương ứng không?
3. Master keys/data encryption keys thuộc ai quản lý?
4. Có rotation policy không?
5. Ai có quyền decrypt/restore?
6. Key có nằm cùng nơi với ciphertext mà attacker truy cập được không?
7. Có khả năng restore khi key bị mất/thu hồi không?
8. Có audit của KMS operations không?
9. Có data residency/region requirement không?

**Có mã hóa nhưng mất key thì có thể đồng nghĩa mất khả năng khôi phục dữ liệu.**

### 10.2. Queryable Encryption không thay thế RBAC

MongoDB có những tính năng client-side encryption như Queryable Encryption cho những loại query/field được hỗ trợ. Đây là chức năng có giới hạn phiên bản, field type, query operator và performance.

Không giả định:

- Mã hóa mọi field bất kỳ vẫn query/sort/index như trước;
- Client-side encryption tự cung cấp tenant authorization;
- Search/Vector Search hoạt động trực tiếp trên ciphertext như plaintext;
- Backups mã hóa là đủ để đáp ứng quyền xóa dữ liệu.

Nếu dùng CSFLE/Queryable Encryption, phải review **schema encrypted fields, key vault, KMS, driver compatibility, policy của client** và hạn chế truy vấn riêng.

### 10.3. Encryption keys là một dependency của DR

Một restore drill chỉ được coi là thành công nếu:

- Backup đọc được;
- Keys có sẵn theo chính sách;
- Database restore thành công;
- User/roles/policies được xác lập đúng;
- Ứng dụng truy vấn dữ liệu sau restore được;
- Mọi dữ liệu nhạy cảm vẫn được bảo vệ.

## 11. Audit logging và truy vết hành vi nhạy cảm

Production có thể cần biết:

- Ai tạo/xóa user;
- Ai cấp hoặc thu hồi role;
- Ai thay đổi cấu hình mạng/cluster;
- Ai thay đổi encryption/KMS;
- Có truy cập thất bại bất thường không;
- Có export dữ liệu hàng loạt không;
- Có nâng privilege ngoài quy trình không.

### 11.1. Phân biệt các loại log

| Loại | Chủ yếu giúp |
|---|---|
| Application log | Request ID, business actor, kết quả nghiệp vụ |
| MongoDB server log | Hoạt động, lỗi kết nối, replication, cảnh báo |
| MongoDB audit log (nếu feature/edition hỗ trợ) | Các hoạt động được audit theo cấu hình |
| Atlas Activity Feed/Project logs | Thay đổi quản trị Atlas |
| OS/cloud audit | VM, IAM, KMS, network và storage actions |
| Access gateway logs | Ai vào bastion/VPN/console |
| Backup logs | Backup thành công/thất bại, restore, retention |

Server log không tự biết user nghiệp vụ nào nhấn nút “Xóa đơn hàng” nếu nhiều người dùng đi qua cùng một backend service account. Application audit log cần chứa **business actor/correlation ID** theo policy.

### 11.2. Audit log không tự động có trên mọi phiên bản

Khả năng và hình thức audit logging phụ thuộc MongoDB Atlas tier, MongoDB Enterprise/self-managed và phiên bản. Không viết checklist “đã bật audit” chỉ vì server có một file log.

Kiểm tra:

- Audit functionality thực sự được hỗ trợ?
- Audit filter có ghi đủ những operation bắt buộc?
- Log retention bao lâu?
- Log lưu ở đâu, có mã hóa không?
- Ai được quyền xóa/sửa log?
- Có alert cho tình huống cần phản ứng không?
- Có thử giả lập sự kiện hợp lệ để xác minh trace không?

### 11.3. Không log PII và secrets

Ví dụ không nên:

```javascript
// Tránh trên production:
printjson(db.customers.findOne({ _id: "CUSTOMER-123" }));
```

Nếu document chứa mật khẩu hash, session token, email, địa chỉ và thông tin tài chính, việc in cả document vào stdout/CI logs có thể tạo rò rỉ.

Tốt hơn, log metadata tối thiểu:

```javascript
printjson({
  traceId: "TRACE-EXAMPLE",
  operation: "customer-read",
  result: "success",
  recordCount: 1
});
```

ID phải được xem xét theo privacy policy; không phải cứ thay nội dung bằng ID là hoàn toàn không nhạy cảm.

## 12. Backup: “có backup” chưa đủ

Một trong những rủi ro production lớn nhất là hệ thống có backup job chạy hàng ngày nhưng **chưa từng restore thử**.

### 12.1. Hai khái niệm cần xác định

- **RPO — Recovery Point Objective:** mất tối đa bao nhiêu dữ liệu khi sự cố xảy ra.
- **RTO — Recovery Time Objective:** khôi phục dịch vụ trong tối đa bao lâu.

Ví dụ:

```text
RPO = 15 phút
RTO = 2 giờ
```

Nghĩa là tổ chức kỳ vọng có thể mất tối đa 15 phút dữ liệu và phục hồi trong vòng hai giờ, theo phạm vi sự cố đã định. Không thể hứa RPO 15 phút nếu chỉ backup mỗi 24 giờ mà không có cơ chế PITR/oplog phù hợp.

### 12.2. Các câu hỏi kiểm tra backup

1. Backup có tự chạy theo lịch và được monitor không?
2. Có retention phù hợp không?
3. Backup có được mã hóa không?
4. Có lưu **ngoài failure domain chính** không?
5. Có bản sao immutable hoặc chống chỉnh sửa/xóa trái phép khi cần không?
6. Có test restore định kỳ không?
7. Có backup MongoDB config, users/roles và Search index definitions khi cần không?
8. Có đủ disk/network/time để restore dataset thật không?
9. Key decrypt có thể phục hồi an toàn không?
10. Có runbook xác định ai được phép khôi phục và xác minh dữ liệu không?

### 12.3. Replica set không phải backup

Replica set tăng availability và replication, nhưng:

- Nếu ứng dụng xóa nhầm document và lệnh được replicate, các members đều nhận thay đổi.
- Nếu attacker có quyền `dropDatabase`, thao tác cũng được replicate.
- Nếu dữ liệu bị thay bằng giá trị sai, replication cũng có thể lan giá trị sai.

Vì vậy, **replication không thay backup**. Availability và recoverability là hai khả năng khác nhau.

### 12.4. Sharded cluster cần backup nhất quán

Với sharded cluster, backup cần xét **mọi shards, config servers và metadata liên quan** theo giải pháp hỗ trợ. Chụp snapshot từng shard tùy thời điểm rồi ghép lại có thể không tạo được ảnh toàn cluster nhất quán.

Nên dùng quy trình backup/restore được MongoDB hoặc nền tảng vận hành hỗ trợ; không tự copy rời rạc data files trong khi cluster còn ghi rồi mặc định đó là backup có thể restore.

### 12.5. Restore drill phải kiểm chứng ứng dụng

```text
Backup artifact
      │
      ▼
Isolated restore environment
      │
      ▼
MongoDB starts / topology healthy
      │
      ▼
Data integrity checks
      │
      ▼
Application smoke tests
      │
      ▼
RPO/RTO recorded
      │
      ▼
Evidence + remediation items
```

Không restore test trực tiếp đè lên production. Dùng môi trường cô lập và bảo vệ dữ liệu khôi phục theo cùng mức nhạy cảm.

### 12.6. MongoDB Search/Vector Search sau restore

Search index là dữ liệu dẫn xuất có vòng đời đồng bộ riêng. Sau restore, cần kiểm tra:

- Search index definitions còn phù hợp;
- Index queryable/ready;
- Initial sync hoặc rebuild đã xong chưa;
- Kết quả Search/Vector Search đã phản ánh dữ liệu nguồn;
- App có fallback khi Search chưa sẵn sàng không.

Không tuyên bố DR hoàn tất chỉ vì `db.collection.findOne()` hoạt động nếu chức năng tìm kiếm là yêu cầu dịch vụ quan trọng.

## 13. Availability không phải chỉ có một primary

Một production deployment cần quan tâm đến:

- Replica set với các voting members theo topology phù hợp;
- Failure domains/availability zones;
- Election và failover;
- Primary stepdown;
- Majority write concern/reads theo mục tiêu dữ liệu;
- Connection pooling/retry;
- Disk space, inode, IOPS, CPU/RAM;
- Network partitions;
- Backup và disaster recovery;
- Sharding availability nếu có.

### 13.1. Standalone và replica set

Standalone có thể phù hợp học tập hoặc workload rất hẹp, nhưng nhiều hệ production yêu cầu HA/change streams/transactions có những điều kiện replication riêng. Không dùng mô hình một process không backup rồi gọi đó là “HA”.

### 13.2. Write concern không phải cơ chế bảo mật

`w: "majority"` giúp thay đổi được xác nhận theo semantics replication phù hợp. Nó **không thay TLS, authentication, RBAC hoặc backup**.

Tương tự, `readConcern` liên quan semantics đọc, không cấp quyền đọc.

### 13.3. Rủi ro khi all members cùng failure domain

Ba `mongod` trên cùng một VM hoặc cùng một ổ đĩa không bảo vệ được khi VM/disk đó hỏng. Cần kiểm tra **độc lập failure domains**, không chỉ đếm số members.

## 14. Phiên bản MongoDB và bản vá bảo mật

Trước go-live, xác nhận:

- MongoDB Server version;
- Feature Compatibility Version (FCV);
- Driver versions;
- `mongosh`, backup agent và automation tooling;
- `mongos`, config servers, shards;
- OS/container runtime;
- MongoDB Search/Vector Search processes nếu có;
- Các CVEs đã công bố ảnh hưởng đến thành phần đang dùng;
- EOL/support status;
- Upgrade/rollback plan.

### 14.1. Lệnh xem phiên bản

Trong `mongosh`, nếu đã kết nối:

```javascript
db.version();
```

Có thể kiểm tra FCV với tài khoản có privilege phù hợp:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Không copy thông tin nội bộ/connection metadata ra tài liệu công khai nếu policy không cho phép.

### 14.2. Không suy từ major version là đủ an toàn

Hai deployments cùng MongoDB 8.x có thể khác nhau vì patch level, edition, build và cấu hình. Không chỉ ghi “8.x” trong checklist. Khi một lỗ hổng bảo mật mới được công bố, tổ chức cần đối chiếu advisory với **đúng build đang chạy**.

### 14.3. Tránh upgrade cùng lúc nhiều biến số

Khi chuyển staging → production, tránh đồng thời:

- Nâng major server version;
- Đổi authentication;
- Đổi TLS CA;
- Di chuyển VPC;
- Chuyển shard key;
- Thay encryption provider;
- Thay driver;
- Backfill dữ liệu.

Nếu phải thay nhiều thành phần, cần rollout có thứ tự, kiểm thử và rollback độc lập để dễ khoanh vùng lỗi.

## 15. Hardening hệ điều hành, container và Kubernetes

Áp dụng cho self-managed MongoDB hoặc các agents/connectors tự vận hành.

### 15.1. Process identity và filesystem

- `mongod` chạy dưới dedicated OS account, không chạy root nếu không bắt buộc.
- Data directory chỉ cấp quyền cho process/nhóm cần thiết.
- TLS private keys và internal keyfiles có permissions nghiêm ngặt.
- Không mount host filesystem rộng vào container.
- Không chạy container privileged nếu không có yêu cầu được phê duyệt.
- OS packages và images cập nhật theo policy.
- Chặn truy cập interactive shell không kiểm soát.
- Có resource limits, disk alert, log rotation.

### 15.2. Container security

Một Docker image an toàn hơn cần:

- Image nguồn được tin cậy, pin tag/digest theo policy;
- Scanner phát hiện vulnerabilities;
- Không bake credentials vào image;
- Không publish port ra mọi interfaces chỉ để test;
- Persistent volumes có encryption/permission phù hợp;
- Read-only filesystem khi tương thích;
- Cơ chế startup/shutdown cho replica set đúng quy trình.

Ví dụ development:

```yaml
services:
  mongodb:
    image: mongo:8.0
    ports:
      - "127.0.0.1:27017:27017"
```

**Ví dụ này chỉ để thể hiện bind port localhost trong development**, chưa phải cấu hình production: thiếu authentication, TLS, volume, backups, replica set topology và nhiều biện pháp khác. Không triển khai nguyên mẫu.

### 15.3. Kubernetes

Rà soát:

- Namespace isolation;
- Kubernetes RBAC;
- Pod Security settings;
- `runAsNonRoot`/security context theo image;
- `NetworkPolicy` giới hạn ingress/egress;
- Secrets từ KMS/external secret store nếu cần;
- Persistent Volume encryption/access;
- Node/pod affinity và failure domains;
- Backup và restore của PVC/data;
- Image provenance;
- Audit logs;
- Readiness/liveness probes phù hợp với MongoDB topology.

Không đặt liveness probe quá mạnh khiến một primary/secondary bị restart liên tục khi đang recovery hoặc initial sync.

### 15.4. Infrastructure as Code

Security groups, firewall, Atlas config và secrets bindings nên được quản lý qua IaC/policy-as-code nếu tổ chức hỗ trợ. Đừng chỉ chụp screenshot cấu hình “đã an toàn hôm nay” rồi để nó drift trong nhiều tháng.

## 16. Kiểm tra connection strings, driver và application config

Một backend dùng MongoDB Driver có nhiều cấu hình ảnh hưởng đến bảo mật và độ bền.

### 16.1. URI và authentication database

Ví dụ:

```text
mongodb://APP_USER:<PASSWORD>@db-internal.example:27017/app
  ?authSource=admin&tls=true
```

Với URI một dòng thật, `authSource` phải trỏ tới **database chứa user được xác thực**, không phải tự động là DB nghiệp vụ trong mọi deployment.

Các ký tự đặc biệt trong username/password cần được **percent-encode** đúng trong connection string. Không sửa mật khẩu bằng cách bỏ ký tự đặc biệt cho “dễ kết nối”.

### 16.2. Các điều kiện cần kiểm tra

- `MONGODB_URI` lấy từ secret store;
- Không log nguyên URI khi exception;
- Driver có TLS verification chuẩn;
- Auth mechanism phù hợp;
- `retryWrites` và write concern theo yêu cầu;
- Server selection/connect timeouts có giới hạn;
- Connection pool có sizing;
- Không tạo MongoClient mới cho mỗi HTTP request;
- Không dùng admin user cho business API;
- Không dùng `tlsInsecure`;
- Không để URI tự chọn database khác vượt permission;
- Có test failover và cert expiry.

### 16.3. Java driver: không tắt hostname verification

Một ví dụ cách đọc URI:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

String uri = System.getenv("MONGODB_URI");

if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is not set");
}

try (MongoClient client = MongoClients.create(uri)) {
    var database = client.getDatabase("app");
    var collection = database.getCollection("orders");

    System.out.println("Configured MongoDB client created.");
}
```

Trong web application thật, `MongoClient` nên có **lifecycle dùng chung** thay vì đóng trong từng request. Ví dụ chỉ cho thấy nguồn config; chưa đủ để thay một production connection manager.

Không dùng custom TrustManager “trust all” để khắc phục lỗi chứng chỉ. Phải sửa CA/SAN/hostname đúng.

### 16.4. Schema validation vẫn là lớp an toàn

MongoDB document model linh hoạt, nhưng trong production nên xác định:

- Field bắt buộc;
- Kiểu BSON hợp lệ;
- Miền giá trị;
- Tenant ID không bị ghi thiếu;
- Những field nhạy cảm không bị ghi vào vùng public;
- API input validation và schema version.

Schema validation không thay authentication, nhưng giúp ngăn lỗi dữ liệu mà một client có quyền ghi gây ra.

## 17. Kiểm tra ứng dụng chống injection và broken authorization

MongoDB không dùng SQL, nhưng điều đó **không có nghĩa miễn nhiễm với injection**.

### 17.1. Unsafe operator injection

Một endpoint nhận JSON trực tiếp:

```javascript
// Sai về thiết kế:
const filter = request.body;
db.users.find(filter);
```

Nếu client được tự quyết định toàn bộ filter/operator, nó có thể gửi những điều kiện không đúng quyền hoặc phá logic ứng dụng.

Hướng đúng:

```javascript
// Minh họa: chỉ lấy userId từ identity context,
// còn trạng thái tìm kiếm từ một allowlist đã kiểm tra.
const filter = {
  tenantId: trustedTenantId,
  ownerId: trustedUserId,
  status: allowedStatus
};

db.orders.find(filter);
```

Không build query bằng cách nối các đoạn BSON/JSON từ input chưa kiểm soát. Validate kiểu dữ liệu và allowlist operators.

### 17.2. Direct-by-ID cross-tenant access

Một API:

```text
GET /orders/ORDER-999
```

nếu query chỉ `{_id: "ORDER-999"}`, có thể trả order của tenant khác nếu các IDs đoán được.

Cách an toàn hơn:

```javascript
db.orders.findOne({
  _id: orderIdFromValidatedInput,
  tenantId: trustedTenantId
});
```

Cộng với authorization business-level nếu một tenant có nhiều users với quyền khác nhau.

### 17.3. Unique index không thay authorization

Một index unique bảo đảm tính duy nhất theo key/partial filter được định nghĩa. Nó không quyết định ai được phép tạo/sửa document. Ví dụ `unique({tenantId,orderNumber})` có thể bảo đảm order number duy nhất trong tenant, nhưng không chặn attacker có quyền ghi vào tenant khác nếu API thiếu kiểm tra quyền.

## 18. MongoDB Search, Vector Search và Change Streams cũng cần bảo mật

Nhiều ứng dụng production không chỉ dùng `find()` mà còn dùng những thành phần dẫn xuất.

### 18.1. Search index có thể chứa dữ liệu nhạy cảm

Full-text Search có thể index những field từ tài liệu. Dù chỉ lưu tokens hoặc bản dẫn xuất, những index này vẫn có thể chứa thông tin nhạy cảm. Cần kiểm tra:

- Field mappings có đưa PII không cần thiết vào index không;
- Stored source có chứa toàn bộ document không;
- Ai được phép query Search;
- Có tenant filter không;
- Có kiểm tra authorization sau retrieval không;
- Search logs/metrics có chứa raw query hay không.

### 18.2. Search index có độ trễ đồng bộ

Timeline:

```text
T1: Admin thu hồi quyền DOC-1.
T2: MongoDB source cập nhật ACL.
T3: Search index chưa bắt kịp.
T4: User search và nhìn thấy candidate cũ.
```

Nếu chỉ dựa vào ACL đã index, có thể rò rỉ nội dung. Cần **authoritative permission check** trước khi trả kết quả và trước khi đưa content tới reranker/LLM.

### 18.3. Vector embedding không tự vô hại

Embeddings là các vector số nhưng có thể mang thông tin ngữ nghĩa về dữ liệu gốc. Cần:

- Giới hạn access;
- Không trả nguyên embeddings cho frontend nếu không cần;
- Xem chính sách của external embedding provider;
- Cấp quyền theo tenant;
- Không trộn query scopes;
- Kiểm soát cache và retention.

### 18.4. Change streams có thể phát dữ liệu trước khi xóa

Nếu bật pre-images, một delete event có thể chứa **document trước khi xóa**. Consumer CDC/audit cần bảo vệ pipeline, credentials, logs và nơi lưu event.

Quyền đọc change streams không đồng nghĩa consumer được phép lưu toàn bộ PII vô hạn. Xác định retention và redaction cho downstream.

### 18.5. Analytics/BI/ETL exports

Một BI account chỉ cần tổng số đơn hàng không nên có quyền dump toàn bộ database khách hàng. Nên dùng:

- Read-only roles với phạm vi tối thiểu;
- Views hoặc collections đã được hạn chế trường khi phù hợp;
- Data masking/pseudonymization;
- Approved export destinations;
- TTL/retention;
- Audit quyền truy cập.

Không cấp `readAnyDatabase` cho một dashboard chỉ đọc vài bảng.

## 19. Dữ liệu cá nhân và vòng đời lưu trữ

Bảo mật không chỉ là chống hacker; còn là **không giữ dữ liệu nhạy cảm quá mức cần thiết**.

### 19.1. Phân loại dữ liệu

Ví dụ:

| Loại dữ liệu | Kiểm soát bổ sung |
|---|---|
| Public catalog | Integrity và chống sửa trái phép |
| Internal docs | Access control, logging |
| Customer PII | Retention, masking, quyền truy cập |
| Payment-related data | Chính sách bảo vệ riêng của tổ chức/chuẩn liên quan |
| Credentials/secrets | Không lưu plaintext, key rotation |
| Audit records | Integrity, restricted access, retention |
| Health/legal/HR records | Phân loại nhạy cảm, legal/compliance review |

Các nghĩa vụ pháp lý thay đổi theo quốc gia/ngành. Review kỹ thuật cần phối hợp với người phụ trách pháp lý và bảo mật thay vì tự suy ra thời hạn lưu.

### 19.2. TTL indexes không phải cơ chế xóa tức thì

MongoDB TTL index có thể tự xóa document đã hết hạn, nhưng quá trình xóa diễn ra bất đồng bộ. Không xem TTL là lời hứa document sẽ biến mất đúng đến từng millisecond tại deadline.

Với yêu cầu xóa dữ liệu, phải xét:

- Source document;
- Backups/snapshots;
- Search indexes;
- Change streams/pre-images;
- Caches;
- Downstream exports;
- Logs;
- Analytics tables.

### 19.3. Soft delete khác physical delete

Soft delete giữ document nhưng đánh dấu inactive:

```javascript
{
  _id: "CUSTOMER-1",
  deletedAt: ISODate("2026-11-14T00:00:00Z")
}
```

Điều này không đáp ứng mọi yêu cầu xóa vật lý. Nếu ứng dụng cần loại record khỏi Search, phải filter và kiểm tra lại quyền/current state.

## 20. Observability và phát hiện sự cố

Production security review cần xác minh **có thể nhận biết khi hệ thống bắt đầu sai**.

### 20.1. Những metrics cần cảnh báo

- Authentication failures tăng bất thường;
- Connection attempts từ mạng lạ;
- Số users/roles thay đổi ngoài lịch;
- CPU/disk/IOPS bất thường;
- Số connections tăng đột biến;
- Replication lag;
- Election/primary flapping;
- Disk space thiếu;
- Backup job failures;
- Restore test quá hạn;
- TLS certificate sắp hết hạn;
- KMS errors/denials;
- Audit logging pipeline failures;
- Dữ liệu query/export tăng đột biến;
- Search index sync lag hoặc stale permissions;
- Secret rotation overdue.

### 20.2. Một cảnh báo phải có người nhận

Một alert không có on-call owner, escalation và runbook chỉ là notification.

Mỗi alert quan trọng nên có:

```text
Signal
   │
Threshold / condition
   │
Owner/on-call
   │
Runbook
   │
Escalation
   │
Post-incident review
```

### 20.3. Không tạo thêm lỗ hổng qua monitoring

Nếu exporter dùng database credentials, nó cũng phải được xem là một client bảo mật:

- Least privilege;
- TLS;
- Private network;
- Secret rotation;
- Không export PII;
- Dashboard access control;
- Log retention;
- TLS giữa exporter và backend giám sát nếu cần.

## 21. Kiểm tra bằng lệnh đọc-only trong `mongosh`

Những lệnh sau giúp **thu thập bằng chứng**, nhưng không tạo ra một đánh giá bảo mật hoàn chỉnh. Chúng cần quyền thích hợp và nên chạy trên môi trường được phép.

### 21.1. Phiên bản server

```javascript
db.version();
```

### 21.2. Thông tin phiên authentication/roles

```javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
```

Không đăng output nguyên văn lên ticket công khai; chỉ trích xuất thông tin cần thiết sau khi redact.

### 21.3. Xem startup options của self-managed

Nếu có quyền quản trị:

```javascript
db.adminCommand({
  getCmdLineOpts: 1
});
```

Output có thể chứa cấu hình đường dẫn và metadata nhạy cảm; **đừng paste toàn bộ ra bên ngoài**. Mục đích kiểm tra các nhóm như:

- `net.bindIp`;
- `net.tls`;
- `security.authorization`;
- `security.keyFile`;
- Các paths cấu hình.

Không phải tất cả tham số runtime đều xuất hiện đầy đủ ở dạng dễ đọc trong mọi deployment. Với Atlas, nhiều thuộc tính được quản lý bởi service và cần kiểm tra qua **Atlas configuration/console/API** thay vì suy từ command này.

### 21.4. Kiểm tra indexes

```javascript
db.getSiblingDB("app").orders.getIndexes();
```

Indexes giúp performance và uniqueness theo mục đích, nhưng **không chứng minh database đã được cấu hình an toàn**.

### 21.5. Kiểm tra replication

```javascript
rs.status();
```

Chỉ chạy trong ngữ cảnh replica set và user có quyền. Đây là thông tin availability/topology, không phải toàn bộ security audit.

### 21.6. Kiểm tra Search index

Nếu hệ thống dùng MongoDB Search và phiên bản hỗ trợ:

```javascript
db.getSiblingDB("app").knowledge.aggregate([
  {
    $listSearchIndexes: {}
  }
]);
```

Search index status là phần của operational readiness. Rà soát mappings/permissions và tính mới của dữ liệu Search ở bước khác.

### 21.7. Không chạy lệnh thay đổi trong preflight tự động

Một script “audit” không nên tự:

```javascript
db.dropDatabase();
db.orders.deleteMany({});
db.grantRolesToUser("app", [{role:"root", db:"admin"}]);
```

Đây là các **lệnh thay đổi có tác động lớn**, không phải lệnh đọc kiểm tra. Bài học không khuyến nghị chạy chúng; chúng chỉ nhắc những thao tác cần được tách khỏi cơ chế preflight read-only.

## 22. Preflight evidence: kiểm tra những gì bằng nguồn nào?

Một ma trận thực hành:

| Hạng mục | Nguồn bằng chứng | Điều kiện PASS |
|---|---|---|
| Network exposure | Firewall/SG/Atlas IP access list | Chỉ mạng được phê duyệt |
| Private connectivity | VPC/endpoint config | Đúng đường private nếu bắt buộc |
| TLS | URI/driver config, cert inspection | `requireTLS` và verify cert/hostname |
| Authentication | Deployment config và test kết nối | Không anonymous access |
| RBAC | Users/roles privilege review | Không quyền thừa |
| Internal auth | Node config/topology evidence | Members xác thực đúng |
| Secret storage | Vault/IAM/CI config | Không secrets hardcode/đọc rộng |
| Encryption at rest | Atlas/OS/KMS settings | Đúng policy dữ liệu |
| Audit logging | Config + sample event | Bắt được sự kiện bắt buộc |
| Backup | Backup jobs/retention | Lịch, lưu trữ, encryption đúng |
| Restore | Restore drill report | RPO/RTO đo được |
| Patch level | Version inventory/advisories | Không thiếu bản vá bắt buộc |
| Monitoring | Dashboards/alerts/on-call | Alert quan trọng có owner |
| Tenant isolation | Automated security tests | Không cross-tenant |
| Search/CDC | Index/connector config và tests | Không rò qua data projection |
| DR | Runbook + simulation | Có phương án và bằng chứng |
| Ownership | Service catalog | Có owner và escalation |

Đây là **bảng kiểm cho release**, không phải lời khẳng định chỉ cần có một screenshot là mọi kiểm soát đã thực sự hoạt động.

## 23. Thứ tự thực hiện review trước go-live

Một quy trình hợp lý:

```text
Inventory & classify data
           │
           ▼
Threat model / trust boundaries
           │
           ▼
Network & TLS
           │
           ▼
Authentication & RBAC
           │
           ▼
Secrets / encryption / key management
           │
           ▼
Backups / restore / DR
           │
           ▼
Logging / audit / monitoring
           │
           ▼
Application authorization tests
           │
           ▼
Operational readiness & patching
           │
           ▼
Evidence review + release decision
```

**Nếu phát hiện BLOCKER**, không nên tiếp tục rollout với giả định “điều chỉnh sau”. Vẫn có thể hoàn tất những kiểm tra read-only khác, nhưng quyết định go-live phải bị chặn cho đến khi issue được xử lý hoặc ngoại lệ có thẩm quyền được phê duyệt theo policy.

### 23.1. Mỗi vấn đề cần chủ sở hữu

Một record nên có:

```text
Finding ID: SEC-MONGO-001
Environment: Production
Component: MongoDB Network Access
Severity: BLOCKER
Observed: Public access rule wider than approved
Evidence: Redacted config snapshot + timestamp
Risk: Untrusted network may reach database endpoint
Owner: Platform Team
Remediation: Restrict access and verify from approved/unapproved networks
Target date: Before release
Verification owner: Security reviewer
Status: OPEN
```

Không đưa password, keys hoặc thông tin quá nhạy cảm vào evidence ticket.

## 24. Atlas production checklist chi tiết

Đối với Atlas, kiểm tra theo các nhóm:

### 24.1. Organization và Project

- Có đúng project cho production, tách khỏi dev/staging;
- Admin/user roles theo least privilege;
- SSO/MFA cho human operators;
- API keys/service identities scoped đúng;
- Không có người đã nghỉ việc vẫn có quyền;
- Alert cấu hình truy cập không mong muốn;
- Project activity được audit theo khả năng Atlas.

### 24.2. Cluster

- Tier phù hợp workload và tính năng;
- Region/data residency được phê duyệt;
- Backup/PITR settings đúng tier;
- Có HA/failure domains theo SLO;
- MongoDB version/patch level và upgrade schedule;
- Search Nodes (nếu dùng) được sizing và bảo vệ;
- Có monitoring.

### 24.3. Network và identities

- IP access list không mở rộng bất hợp lý;
- Private connectivity nếu policy yêu cầu;
- Database users/roles tối thiểu;
- Không dùng shared admin account cho app;
- Connection strings/credentials nằm trong secret store;
- Các quyền cũ được thu hồi;
- Các connectors/BI accounts được review.

### 24.4. Dữ liệu

- Classifications;
- Encryption at rest/customer-managed KMS nếu cần;
- TLS mặc định được xác thực đúng;
- Retention cho backups/logs/exports;
- Search/Vector mappings không chứa dữ liệu không cần thiết;
- Có delete/DSR runbook khi cần;
- Tenant isolation tests.

## 25. Self-managed production checklist chi tiết

Với self-managed, review thêm:

### 25.1. Host và service

- OS hardened và patched;
- Database process chạy bằng service account riêng;
- Data/log/key dirs có permissions;
- Firewall và routing private;
- No unnecessary services/ports;
- No insecure debug interfaces;
- NTP/time sync phù hợp;
- Filesystem và disk encryption;
- Monitoring/backup agents chạy với identities riêng.

### 25.2. MongoDB config

- `security.authorization: enabled` theo topology;
- Internal authentication (`keyFile`/X.509) đúng;
- `net.tls.mode: requireTLS` hoặc chính sách tương đương được phê duyệt;
- Certificate SAN/CA hợp lệ, không bỏ verification;
- `bindIp` không mở rộng bất hợp lý;
- Replica set/shard/config server auth/network đúng;
- Không để cấu hình dev tạm thời còn tồn tại;
- Không có users/roles không dùng;
- Log/audit theo feature edition và policy;
- Backup and restore tested.

### 25.3. Data directories và host access

Người có quyền đọc **data files, snapshots hoặc process memory** có thể tiếp cận dữ liệu ở mức thấp hơn các database roles. Vì vậy RBAC trong MongoDB không thay OS/filesystem access control. Những account SSH/root/volume snapshot cũng phải được review.

## 26. Các tình huống lỗi và cách đánh giá

### Tình huống A — Không bật authentication

```text
MongoDB chỉ dùng cho nội bộ
security.authorization: disabled
Firewall cho mọi máy trong VPN truy cập
```

Kết luận: Không đủ an toàn. “Trong VPN” không phải giới hạn quyền từng user/service. Đây thường là **BLOCKER** với production có dữ liệu thật.

### Tình huống B — Có TLS nhưng bỏ hostname verification

```text
tls=true
tlsAllowInvalidHostnames=true
```

Kết luận: Có encryption nhưng **không bảo đảm đúng server identity**. Phải sửa cert/SAN/CA, không coi đây là PASS.

### Tình huống C — Ứng dụng dùng root

```text
API service
  MongoDB user roles: root@admin
```

Kết luận: Một lỗ hổng API hoặc credential leak có thể làm ảnh hưởng toàn cluster. Tạo service identity với quyền phù hợp; đây là vấn đề quyền cao.

### Tình huống D — Backup có nhưng không restore

```text
Backup job status: SUCCESS
Last restore test: chưa từng
```

Kết luận: Chưa có bằng chứng RPO/RTO đạt. Hạng mục backup **không nên được đánh dấu PASS hoàn chỉnh**.

### Tình huống E — Search trả dữ liệu đã thu hồi quyền

```text
T1: ACL của document bị thu hồi
T2: MongoDB source đã cập nhật
T3: Search index chưa đồng bộ
T4: API trả nội dung từ Search
```

Kết luận: Broken authorization dù user đã đăng nhập hợp lệ. Cần authoritative ACL check trước khi trả content.

### Tình huống F — Chỉ có replica set, không backup

```text
Three replica set members
No independent backup
```

Kết luận: Replica set không bảo vệ khỏi deletion được replicate, lỗi nghiệp vụ hoặc ransomware có đủ quyền. Chưa đáp ứng recoverability.

### Tình huống G — Credentials nằm trong CI logs

```text
CI step prints MONGODB_URI
Log accessible to project-wide readers
```

Kết luận: Credential disclosure. Cần revoke/rotate bị lộ, xóa/giới hạn logs theo policy và sửa pipeline. Không chỉ tắt dòng print rồi giữ secret cũ.

### Tình huống H — User biết `_id` của tenant khác

```text
GET /orders/ORDER-B
Backend query: {_id:"ORDER-B"}
```

Kết luận: Nếu endpoint không kiểm tra tenant/owner, đây là lỗi authorization ở ứng dụng. Database username/password không ngăn user đã login khai thác lỗi này.

## 27. Mẫu báo cáo readiness để áp dụng trong dự án

Một bản review ngắn gọn có thể dùng cấu trúc:

```text
MONGODB PRODUCTION SECURITY REVIEW

Environment:
Deployment type:
MongoDB Server / FCV:
Application release:
Review date:
Reviewer:
System owner:

CONTROL RESULTS
[ ] Network isolation
[ ] TLS and certificate validation
[ ] Database authentication
[ ] RBAC / least privilege
[ ] Internal member authentication
[ ] Secrets and rotation
[ ] Encryption at rest / key management
[ ] Application tenant isolation
[ ] Backup retention / restore test
[ ] Audit / log redaction
[ ] Monitoring / on-call
[ ] Server/driver patch level
[ ] Search/Vector/CDC permissions (if used)
[ ] Data retention/deletion policy
[ ] Disaster recovery runbook

Findings:
  - Finding ID:
    Severity:
    Evidence:
    Owner:
    Remediation:
    Status:

Release decision:
  GO / NO-GO / CONDITIONALLY APPROVED

Approval:
  Service owner:
  Security owner:
  Platform/DBA:
```

Trong môi trường có yêu cầu compliance, thêm chữ ký/phiên bản bằng chứng/chu kỳ phê duyệt và tài liệu audit theo chính sách tổ chức.

### 27.1. Điều kiện GO đề xuất

Chỉ GO khi:

1. Không còn **BLOCKER**.
2. HIGH findings đã được xử lý hoặc có exception có thời hạn theo policy.
3. Evidence có ngày và deployment cụ thể.
4. Recovery được thử và đạt RPO/RTO.
5. Auth/TLS/network/least privilege được xác minh.
6. Tenant/field-level access có test với dữ liệu thật hoặc fixtures đại diện.
7. Có on-call/runbook và rollback plan.
8. Secret/backup/audit owners được phân công.

Một trang checklist “tất cả đã OK” mà không có evidence có thể mang giá trị điều phối, nhưng chưa đủ cho security review kỹ thuật.

## 28. Bài tập thực hành

### Bài 1 — Xác định blocker

Đội vận hành có cấu hình:

```yaml
net:
  bindIp: "0.0.0.0"
  port: 27017
security:
  authorization: disabled
```

1. Nêu ít nhất ba rủi ro.
2. Tại sao firewall là bắt buộc nhưng chưa đủ?
3. Điều kiện nào phải được đáp ứng trước go-live?
4. Có thể sửa bằng cách bật TLS thôi không?
5. Đề xuất thứ tự chuyển sang authentication/TLS an toàn.

### Bài 2 — TLS kiểm tra đúng hostname

Một Java app kết nối thành công với:

```text
tls=true&tlsAllowInvalidCertificates=true
```

1. Vì sao “kết nối thành công” không là bằng chứng an toàn?
2. Điều kiện certificate chain và SAN là gì?
3. Cần quản lý CA/truststore thế nào?
4. Test nào cần thực hiện trước triển khai?
5. Rủi ro của một custom TrustManager chấp nhận mọi cert?

### Bài 3 — Thiết kế RBAC cho ba services

Có:

- Catalog Reader chỉ xem sản phẩm published;
- Order API đọc/ghi `orders`;
- Reporting worker chỉ tạo báo cáo tổng hợp.

Hãy đề xuất database users/roles riêng, chỉ rõ quyền nào không cấp, và giải thích phần **row-level authorization** vẫn phải xử lý ở ứng dụng.

### Bài 4 — Kiểm tra Atlas access

Một Atlas project có:

```text
IP Access List:
  0.0.0.0/0
  Office old IP
  Production NAT IP
```

1. Phần nào đáng lo?
2. Nếu xóa allow-all ngay, có thể tác động gì tới app?
3. Cần kiểm tra network path trước thay đổi thế nào?
4. Khi nào dùng private endpoint?
5. Ai phải approve thay đổi?

### Bài 5 — Replica set keyfile

Một replica set có ba members, keyfile được lưu trong Docker image.

1. Rủi ro chính là gì?
2. Nên dùng secret distribution nào?
3. Rotate keys thế nào để không làm mất quorum?
4. Vì sao không restart cả ba members cùng lúc?
5. Internal auth và client auth khác nhau thế nào?

### Bài 6 — Backup không có restore drill

Hệ thống yêu cầu RPO=15 phút và RTO=2 giờ, nhưng chỉ có backup mỗi ngày.

1. Có thể đạt RPO không?
2. Cần tính thêm PITR/oplog thế nào?
3. Restore drill cần đo gì?
4. Key management ảnh hưởng restore ra sao?
5. Nếu Search index cần rebuild lâu, RTO có bị tác động không?

### Bài 7 — Khóa quyền cross-tenant

API:

```javascript
db.orders.findOne({ _id: request.params.orderId });
```

1. Vấn đề gì khi orderId đoán được?
2. Thêm tenant predicate ở đâu?
3. TenantId nên đến từ nguồn nào?
4. Có cần kiểm tra owner/team roles không?
5. Viết ba integration tests để chặn regression.

### Bài 8 — Secret leak

Một developer vô tình commit `MONGODB_URI` có password vào repository.

1. Chỉ xóa commit mới nhất đã đủ chưa?
2. Cần revoke/rotate secret như thế nào?
3. Làm sao kiểm tra ảnh hưởng trong logs/CI?
4. Secrets scanner và repository protections giúp gì?
5. Làm sao ngăn lỗi lặp lại?

### Bài 9 — Kiểm tra quyền monitoring account

Một exporter metrics đang dùng user `root`.

1. Vì sao không phù hợp?
2. Cần những quyền quan sát nào?
3. Có cần quyền ghi dữ liệu nghiệp vụ không?
4. Credentials và TLS của exporter cần xử lý ra sao?
5. Metrics endpoint có cần network/auth controls không?

### Bài 10 — Chứng minh backup khôi phục được

Thiết kế một buổi restore drill:

1. Chọn backup artifact nào?
2. Restore vào đâu?
3. Xác nhận user/roles/encryption keys thế nào?
4. Kiểm tra data integrity và application smoke tests ra sao?
5. Ghi kết quả RPO/RTO như thế nào?
6. Ai phê duyệt kết quả?

### Bài 11 — Search index và ACL stale

Một tài liệu đã chuyển từ public sang private, nhưng Search index chưa đồng bộ.

1. Pre-filter có thể trả kết quả cũ không?
2. Đặt hậu kiểm ở bước nào?
3. Có được chuyển candidate đến external LLM trước hậu kiểm không?
4. Khi authz service lỗi, nên fail open hay fail closed?
5. Cache phải xử lý ra sao?

### Bài 12 — Data lifecycle

Một user yêu cầu xóa thông tin cá nhân.

1. Cần kiểm tra những bản sao dữ liệu nào?
2. TTL index có bảo đảm xóa ngay đúng millisecond không?
3. Change stream pre-image có thể chứa dữ liệu cũ không?
4. Backup retention có ảnh hưởng gì?
5. Quy trình xác minh hoàn tất cần evidence gì?

### Bài 13 — Bảng release gate

Tạo bảng gồm tối thiểu 10 controls:

```text
Control | Evidence | Owner | Status | Severity | Decision
```

Gán ít nhất ba findings giả lập. Quyết định GO/NO-GO và giải thích căn cứ.

### Bài 14 — Java connection security

Kiểm tra đoạn code dùng `MongoClients.create(uri)`:

1. URI được đọc từ đâu?
2. Có log secrets không?
3. TLS verification còn nguyên không?
4. AuthSource đúng không?
5. MongoClient lifecycle phù hợp không?
6. Có timeout và monitoring không?

### Bài 15 — Bảo mật self-managed Kubernetes

Một deployment MongoDB trong Kubernetes sử dụng:

- Container chạy root;
- Service type LoadBalancer public;
- Secrets mount vào mọi pods;
- Không NetworkPolicy;
- Không backup.

1. Chỉ ra các blockers;
2. Đề xuất tách network và pod security;
3. Thiết kế secret access;
4. Backup/restore plan;
5. Readiness probes/rolling update cần tránh điều gì?

### Bài 16 — Threat modeling cho hệ thống thực tế

Mô hình:

```text
Browser → API → MongoDB Atlas
                 │
                 ├── Vector Search → RAG
                 ├── CDC → Data Warehouse
                 └── Backup → Object Storage
```

Xác định:

1. Trust boundaries;
2. Những data flows chứa PII;
3. Identity của mỗi service;
4. Network/TLS controls;
5. ACL recheck trước RAG;
6. Quyền cho CDC/warehouse;
7. Encryption/retention backup;
8. Audit và incident response.

## 29. Checklist bàn giao cho đội vận hành

### Access và hạ tầng

- [ ] Inventory có owner, versions, regions và data classification.
- [ ] Không có public DB exposure ngoài scope được phê duyệt.
- [ ] Atlas IP access list/firewall/security groups đã được rà soát.
- [ ] Private connectivity được dùng nếu bắt buộc.
- [ ] TLS bắt buộc, cert/hostname được xác minh.
- [ ] Không có `tlsInsecure` hoặc bỏ qua certificate checks.
- [ ] Database authentication được bật theo topology.
- [ ] Internal member authentication đúng.
- [ ] Human admin có MFA/SSO theo policy.
- [ ] Service identities tách biệt và có least privilege.
- [ ] Không có users/roles cũ hoặc không xác định owner.

### Dữ liệu và khóa

- [ ] Secrets ở kho được phê duyệt, không trong repo/images/logs.
- [ ] Có kế hoạch key/password rotation.
- [ ] Encryption at rest phù hợp dữ liệu và deployment.
- [ ] Key backup/restore plan đã được kiểm thử.
- [ ] Client-side encryption được dùng đúng giới hạn nếu có.
- [ ] Retention/deletion policy rõ.
- [ ] Data exports, analytics, Search/Vector/CDC đều được review.
- [ ] Schema validation và tenant ACL tests có bằng chứng.

### Resilience và quan sát

- [ ] Backup chạy và được monitor.
- [ ] Restore drill đạt RPO/RTO.
- [ ] Backup độc lập failure domain chính và được bảo vệ.
- [ ] MongoDB version/driver được cập nhật đúng policy.
- [ ] HA/failover/recovery được thử ở staging.
- [ ] Audit logs thực sự có khả năng ghi sự kiện bắt buộc.
- [ ] Logs không chứa credentials/PII không cần thiết.
- [ ] Alerts có on-call owners và runbooks.
- [ ] Có incident-response/rollback plan.
- [ ] Search indexes/derived data có plan rebuild sau restore.
- [ ] Mọi findings BLOCKER được đóng trước go-live.

## 30. Tài liệu chính thức tham khảo

Đối chiếu với tài liệu MongoDB và tài liệu Atlas tương ứng **đúng phiên bản, tier và môi trường** đang triển khai:

- [MongoDB Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/)
- [MongoDB Security Overview](https://www.mongodb.com/docs/manual/security/)
- [Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- [Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- [Enable Access Control](https://www.mongodb.com/docs/manual/tutorial/enable-authentication/)
- [TLS/SSL Configuration](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/)
- [Internal Authentication / Keyfile](https://www.mongodb.com/docs/manual/tutorial/enforce-keyfile-access-control-in-existing-replica-set/)
- [MongoDB Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/)
- [Audit Messages](https://www.mongodb.com/docs/manual/reference/audit-message/)
- [MongoDB Atlas Security](https://www.mongodb.com/docs/atlas/security/)
- [Atlas Network Access](https://www.mongodb.com/docs/atlas/security/ip-access-list/)
- [Atlas Private Endpoints](https://www.mongodb.com/docs/atlas/security-private-endpoint/)
- [MongoDB Atlas Backups](https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/)
- [MongoDB Encryption at Rest](https://www.mongodb.com/docs/manual/core/security-encryption-at-rest/)
- [Queryable Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/)
- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Search](https://www.mongodb.com/docs/search/)
- [MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)

## Kết luận

**Rà soát cấu hình MongoDB trước production** không phải một lệnh `db.adminCommand()` hay một file `mongod.conf` “mẫu”. Đây là một quá trình kiểm chứng **toàn bộ đường đi của dữ liệu và quyền truy cập**.

Những kiểm soát nền tảng phải được xác nhận gồm: **network isolation, TLS có xác thực chứng chỉ, authentication, RBAC theo least privilege, internal member authentication, secrets management, mã hóa dữ liệu, logging/audit, backup và restore thực sự, patching, monitoring và application-level authorization**. Với Atlas, tổ chức vẫn quản lý identities/network/data policy; với self-managed, đội vận hành còn phải bảo vệ host, process, TLS/keyfiles và topology.

Một hệ thống có thể có ba replica set members, bật TLS và chạy nhanh nhưng vẫn không an toàn nếu **API dùng root, tài khoản khác tenant đọc được document, hoặc bản backup không thể restore**. Các tính năng Search/Vector Search và CDC còn đòi thêm kiểm soát vì chỉ mục/bản sao dẫn xuất có thể chứa thông tin nhạy cảm và đồng bộ trễ so với quyền truy cập hiện hành.

**Chỉ quyết định GO-LIVE khi các hạng mục bắt buộc có bằng chứng đạt, không còn blockers, có người chịu trách nhiệm, có phương án khôi phục và có quy trình quan sát sự cố. Sự an toàn của MongoDB là đặc tính của toàn bộ hệ thống vận hành, không chỉ của database engine.**

