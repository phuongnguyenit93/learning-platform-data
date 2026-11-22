# Quản lý mật khẩu, chứng chỉ và luân chuyển thông tin bí mật trong MongoDB

## 1. Bối cảnh và mục tiêu

MongoDB có thể bật xác thực và phân quyền đúng nhưng vẫn gặp sự cố bảo mật nếu mật khẩu ứng dụng bị đưa lên Git, chứng chỉ TLS hết hạn, private key bị lộ hoặc việc thay một key của replica set khiến các thành viên không còn xác thực được với nhau.

**Secret rotation** là quá trình cấp thông tin xác thực mới, chuyển những bên sử dụng sang phiên bản mới, xác minh rồi thu hồi thông tin cũ. Một quy trình tốt không chỉ đổi một giá trị trong database: nó phải kiểm soát secrets manager, connection pool, certificate chain, replica-set health, quyền truy cập và khả năng rollback.

Bài học thuộc chương **Bảo mật** trong module **Database Engine Document MongoDB**, với đề bài **Quản lý mật khẩu, chứng chỉ và luân chuyển thông tin bí mật**.

Sau bài học, bạn có thể:

1. Phân biệt password SCRAM, TLS private key, client X.509 certificate, cluster keyfile và master encryption key.
2. Tạo, kiểm tra và thay mật khẩu database user trên self-managed MongoDB.
3. Sử dụng đúng quy trình của MongoDB Atlas để quản lý database users.
4. Thiết kế rotation hạn chế downtime bằng **dual-account/blue-green credentials**.
5. Kiểm soát kết nối TLS, CA chain, SAN, EKU, truststore và keystore.
6. Nạp lại TLS certificate bằng `rotateCertificates` ở các triển khai hỗ trợ.
7. Thiết kế CA rollover và client X.509 credential rotation an toàn.
8. Luân chuyển cluster membership keyfile với giai đoạn chồng lấp old/new keys.
9. Phân biệt cluster keyfile với khóa mã hóa dữ liệu at rest, KMS/CMK và DEK.
10. Tích hợp secrets manager vào Java Sync Driver mà không hardcode password.
11. Xây dựng runbook prepare → stage → switch → revoke, có monitoring và incident response.
12. Xử lý lỗi thường gặp và luyện tập trên những tình huống MongoDB thực tế.

**Điểm quan trọng:** Không có một lệnh duy nhất xoay vòng tất cả loại secrets trong MongoDB. Mỗi secret có phạm vi, quyền truy cập, cơ chế hoạt động và yêu cầu hồi phục khác nhau.

## 2. Phân loại secrets trước khi thực hiện rotation

| Secret | Chủ thể sử dụng | Mục đích | Cách thay chính |
|---|---|---|---|
| Mật khẩu SCRAM | Application/human DB users | Xác thực client với MongoDB | Đổi password hoặc tạo user mới |
| Server TLS certificate + private key | `mongod` / `mongos` | Xác minh server, mã hóa traffic | Cấp cert mới, reload hoặc rolling restart |
| Client X.509 certificate + private key | App/mongosh | mTLS, client authentication | Cấp client cert mới, chuyển clients và thu hồi cũ |
| CA/trust bundle | Clients/servers | Tin cậy certificate chain | Chồng lấp CA cũ và CA mới |
| Cluster keyfile | Replica-set/sharded members | Internal membership authentication | Overlap old+new keys, rolling restart |
| Internal member X.509 certificate | MongoDB nodes | Xác thực nội bộ bằng mTLS | Cấp cert, bảo đảm DN/EKU/CA, luân chuyển từng node |
| KMS/CMK master key | Storage encryption | Bảo vệ khóa mã hóa dữ liệu | Quy trình KMS/KMIP, không phải đổi SCRAM |
| Data Encryption Key (DEK) | CSFLE/Queryable Encryption | Mã hóa trường dữ liệu | Rewrap hoặc rotate theo cơ chế encryption |
| Secret manager token | Workload/automation | Lấy các secrets trên | Short-lived identity/token, policy rotation |

Ba câu hỏi đầu tiên cho mỗi secret:

- **Ai biết/đang sử dụng secret?** Bao gồm API, workers, cronjobs, ETL, backup, monitoring.
- **Secret bị mất tác động tới gì?** Chỉ một application, hay toàn cluster/backup?
- **Có thể chấp nhận đồng thời secret cũ và mới không?** Đây là cơ sở cho rotation ít gián đoạn.

### 2.1. Authentication, authorization và encryption không thay nhau

~~~text
Authentication                  Authorization                  Encryption
"Bên kết nối là ai?"            "Được phép làm gì?"           "Dữ liệu được bảo vệ?"
SCRAM / X.509 / OIDC           Roles, privileges            TLS / at rest / CSFLE
~~~

Thay password mà vẫn cho service role `root` không xử lý được rủi ro quyền quá rộng. Bật TLS mà không bật xác thực database cũng không tương đương có authorization.

### 2.2. Secret inventory không chứa giá trị bí mật

Ví dụ bảng kiểm kê:

| Logical name | Owner | Consumers | Môi trường | Rotation deadline |
|---|---|---|---|---|
| `mongo/orders-api/prod` | Orders team | API, worker | production | Theo policy |
| `mongo/rs0/internal` | Platform team | mongod nodes | production | Theo policy |
| `mongo/rs0/tls` | Platform team | mongod + mongos | production | Trước cert expiry |

Lưu đường dẫn và metadata, **không** chép plaintext password, private key hoặc URI có credentials vào bảng.

## 3. Phân biệt MongoDB Atlas và self-managed

| Quản trị | MongoDB Atlas | Self-managed MongoDB |
|---|---|---|
| Tạo/sửa database users | Atlas UI/CLI/Admin API/tích hợp hỗ trợ | `db.createUser`, `db.updateUser` |
| Đổi database password | Atlas management plane | `db.changeUserPassword` |
| Server TLS certificates | Atlas quản lý hạ tầng tương ứng | Tổ chức tự quản lý |
| Internal keyfile | Atlas quản lý | Tự quản lý nodes và keyfiles |
| Client X.509 | Qua Atlas workflow phù hợp | X.509 user trên `$external` |
| KMS/master keys | Atlas integration theo tier/config | Enterprise/KMIP hoặc giải pháp tương ứng |

**Không sử dụng `db.changeUserPassword()` để thay Atlas database user**. Atlas yêu cầu quản lý users qua Atlas UI, CLI, Administration API hoặc tích hợp được hỗ trợ; MongoDB docs lưu ý những thay đổi trực tiếp khác có thể bị hoàn nguyên.

### 3.1. Hai loại user trên Atlas

- **Atlas user:** người truy cập giao diện quản trị dự án/organization.
- **Database user:** principal được ứng dụng hoặc công cụ sử dụng để truy cập dữ liệu MongoDB.

Đổi mật khẩu Atlas console không có nghĩa đã đổi mật khẩu database user, và ngược lại.

### 3.2. Passwordless có thể phù hợp hơn long-lived password

Các cơ chế như X.509, AWS IAM và OIDC workload identity federation có thể giảm mật khẩu lưu dài hạn trên deployment hỗ trợ. Tuy nhiên OIDC/IAM cũng có vòng đời token, trust policy và quyền cần quản lý; không mặc nhiên hỗ trợ trên mọi tier, edition hoặc driver.

## 4. Threat model: bí mật thường bị lộ ở đâu?

Các trường hợp:

- Connection URI chứa password bị commit vào Git.
- CI job ghi nguyên biến môi trường ra logs.
- Mật khẩu được đưa lên command-line args, shell history hoặc process list.
- Docker image chứa file PEM private key.
- Kubernetes Secret có quyền đọc quá rộng hoặc không được thay trong process.
- Lỗi TLS được xử lý bằng `tlsInsecure=true`.
- Một credential dùng chung nhiều dịch vụ và môi trường.
- Nhân sự nghỉ việc nhưng account/quyền secret manager vẫn tồn tại.
- Old certificate được gia hạn nhưng **chưa bị revoke** sau khi private key lộ.
- Cluster keyfile bị sao chép vào bản backup không được kiểm soát.

Kiểm soát nền tảng:

1. Mỗi service/environment dùng principal riêng.
2. Chỉ cấp MongoDB roles cần thiết.
3. Dùng TLS để bảo vệ credential-in-transit.
4. Secrets được phát qua kênh có phân quyền và audit.
5. Có lịch rotation theo rủi ro/tuân thủ.
6. Có khả năng thu hồi khi compromise.
7. Không ghi plaintext secrets vào logs, metrics hoặc tickets.

## 5. Mật khẩu SCRAM trong MongoDB

MongoDB hỗ trợ SCRAM-SHA-1 và SCRAM-SHA-256; các phiên bản hiện đại sử dụng SCRAM-SHA-256 làm lựa chọn mặc định phù hợp.

SCRAM là challenge-response mechanism và server không lưu password plaintext. **Tuy nhiên**, các thao tác tạo/thay database password có thể gửi giá trị cần xử lý qua network. Dùng TLS để bảo vệ đường truyền khi thực hiện user management.

### 5.1. authSource là nơi user được khai báo

Một user có thể nằm trong database `appdata`:

~~~javascript
use appdata
~~~

Khi xác thực user đó, connection cần chọn đúng auth database, ví dụ `authSource=appdata`. Với Atlas SCRAM database users, `admin` thường là authentication database theo tài liệu Atlas.

### 5.2. Mật khẩu cần thế nào?

- Sinh ngẫu nhiên bằng nguồn CSPRNG đáng tin.
- Đủ dài theo security policy.
- Không dùng cùng password cho prod và staging.
- Không đặt password trong source/config versioned.
- Không tiết lộ password qua ticket/chat.
- Không dùng admin/root account cho ứng dụng đọc/ghi thường ngày.

## 6. Tạo user SCRAM trên self-managed MongoDB

**Chỉ chạy trên self-managed MongoDB lab đã bật authentication, TLS và có admin privileges phù hợp.**

~~~javascript
use appdata

db.createUser({
  user: "orders_svc_v1",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "appdata" }
  ],
  mechanisms: ["SCRAM-SHA-256"]
});
~~~

`passwordPrompt()` yêu cầu nhập password tương tác, tránh hardcode trực tiếp trong lệnh. Nó giảm rủi ro lộ trong history/source nhưng không bảo đảm secret an toàn nếu terminal bị ghi lại hoặc transport không TLS.

### 6.1. Quyền tối thiểu

Nếu một báo cáo chỉ cần đọc, tạo role `read` thay vì `readWrite`. Khi ứng dụng chỉ cần vài collections, cân nhắc custom role theo resource để giảm phạm vi.

Không cấp `root`, `dbOwner` hay `userAdminAnyDatabase` chỉ để “cho hết lỗi permission”.

### 6.2. Kiểm tra metadata của user

~~~javascript
use appdata

db.getUser("orders_svc_v1");
~~~

Kiểm tra roles/mechanisms, không in hoặc tìm cách truy xuất plaintext password. MongoDB không cung cấp cách đọc lại password gốc như một field thường.

### 6.3. Kiểm tra quyền của session hiện tại

~~~javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
~~~

Kết quả cho biết principal hiện tại và privileges. Ngoài `ping`, một canary nên thử read/write **an toàn trên dữ liệu test**, không dùng lệnh xóa dữ liệu production.

## 7. Đổi password trên self-managed: trực tiếp và giới hạn

Trên database chứa user:

~~~javascript
use appdata

db.changeUserPassword(
  "orders_svc_v1",
  passwordPrompt()
);
~~~

Hoặc:

~~~javascript
use appdata

db.updateUser(
  "orders_svc_v1",
  { pwd: passwordPrompt() }
);
~~~

Lệnh cần quyền `changePassword` thích hợp đối với user đang quản lý.

### 7.1. Vì sao đổi password trực tiếp có thể gây gián đoạn?

~~~text
T0: app clients đang dùng oldPassword
T1: server chuyển sang newPassword
T2: pod A nhận newPassword
T3: pod B vẫn đang dùng oldPassword
~~~

Sau T1, những lần **authentication mới** với password cũ có thể bị từ chối. Connections đã authenticated có thể còn sống đến khi bị đóng hoặc pool mở kết nối mới. Không dựa vào kết nối cũ tồn tại để suy ra rotation không gây lỗi.

### 7.2. Một user SCRAM không tự hỗ trợ old+new passwords đồng thời

Theo cách vận hành cơ bản, `changeUserPassword()` thay credential của user; nó không tạo một giai đoạn overlap password cũ và mới cho cùng user.

Nếu uptime quan trọng, sử dụng **dual-account rotation** thay vì cố thay password trực tiếp giữa lúc các pods đang chạy.

### 7.3. Những lỗi cần phân biệt

`AuthenticationFailed` có thể do:

- Username sai.
- authSource sai.
- Password version cũ.
- SCRAM mechanism không phù hợp.
- URI password chưa percent-encode.
- Thay đổi secret nhưng connection pool chưa được tạo lại.

Lỗi TLS handshake xảy ra **trước** khi SCRAM authentication thành công; đừng luôn quy lỗi đó cho password.

## 8. Dual-account rotation: quy trình ít downtime

Giả sử service `orders-api` dùng account `orders_svc_v1`.

Thay vì reset password của v1 ngay, tạo `orders_svc_v2` với quyền tương đương hoặc hẹp hơn:

~~~javascript
use appdata

db.createUser({
  user: "orders_svc_v2",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "appdata" }
  ],
  mechanisms: ["SCRAM-SHA-256"]
});
~~~

Trong giai đoạn chuyển, cả v1 và v2 đều có thể xác thực.

~~~text
                 Secrets Manager
              /                   \
           v1 secret            v2 secret
              |                    |
         Old app pods         New app pods
              \                    /
                     MongoDB
                 users v1 and v2
~~~

### 8.1. Bước 1 — Inventory consumers

Liệt kê API replicas, background workers, cronjobs, ETL, migration scripts, backup/export tools và job chạy hiếm. Nếu quên cronjob mỗi tháng mới chạy, lỗi có thể chỉ xuất hiện rất lâu sau rotation.

### 8.2. Bước 2 — Tạo và phân phối v2

Sinh password mới trong secrets manager, tạo account v2 và cấp cho đúng workload identity. Không đưa password vào image, repo hoặc ticket.

### 8.3. Bước 3 — Canary

Một instance mới:

1. Lấy v2 secret.
2. Tạo MongoClient/connection pool mới.
3. Kiểm tra TLS chain và hostname.
4. Xác thực SCRAM.
5. Thử `ping` và thao tác ứng dụng cho phép.
6. Theo dõi authentication errors, connection pool errors và latency.

### 8.4. Bước 4 — Rollout

Chuyển từng nhóm pods và workers, quan sát số kết nối mới, lỗi 18, API 5xx và job failures. Mọi consumers phải được xác nhận dùng v2.

### 8.5. Bước 5 — Thu hồi v1

Chỉ sau khi xác minh toàn bộ consumers đã chuyển:

~~~javascript
use appdata

db.dropUser("orders_svc_v1");
~~~

Đây là bước thay đổi quyền thực sự, chỉ thực hiện với approval và runbook. Khi security incident yêu cầu thu hồi gấp, ưu tiên containment và chấp nhận các biện pháp giảm gián đoạn phù hợp.

### 8.6. Rollback

Nếu v2 có cấu hình sai, quay lại v1 **chỉ khi v1 chưa bị compromise** và vẫn còn active. Nếu v1 bị lộ, rollback về v1 là không phù hợp về bảo mật.

### 8.7. So sánh hai chiến lược

| Tiêu chí | Đổi password cùng user | Dual-account |
|---|---|---|
| Old/new credentials chồng lấp | Không theo cách cơ bản | Có |
| Canary trước thu hồi cũ | Khó | Có |
| Thời điểm đổi trên server | Một bước | Cấp mới, chuyển, thu hồi |
| Rủi ro downtime | Cao hơn nếu consumers reload chậm | Thường thấp hơn |
| Cleanup | Đơn giản | Cần drop user cũ |
| Rollback | Có thể cần reset tiếp | Có thể dùng user cũ khi an toàn |

## 9. Quản lý users trên MongoDB Atlas

Với Atlas:

1. Mở đúng project.
2. Vào **Security → Database & Network Access**.
3. Mở **Database Users**.
4. Edit user SCRAM hiện có hoặc tạo user v2.
5. Gán roles hợp lý.
6. Lưu credentials trong secrets manager.
7. Rollout ứng dụng.
8. Thu hồi user cũ sau khi kiểm chứng.

Atlas CLI và Atlas Administration API cũng hỗ trợ automation cho database users.

**Không dùng**:

~~~javascript
// Không phải cách quản lý Atlas database users được hỗ trợ.
db.changeUserPassword("orders_svc_v1", passwordPrompt());
~~~

### 9.1. Atlas passwordless options

Tùy tier/driver/version, Atlas hỗ trợ X.509, AWS IAM và workload identity federation (OIDC/OAuth 2.0).

Nếu có workload identity từ cloud/IdP đáng tin, lựa chọn này có thể loại bỏ password dài hạn khỏi app config. Nhưng token refresh, claims, IAM policies và giới hạn deployment vẫn phải được quản lý.

### 9.2. Database user khác Atlas console user

Quyền quản lý Atlas project và quyền database access là hai lớp. Không cho một ứng dụng quyền quản trị project chỉ để kết nối database.

## 10. Secrets Manager và cách ứng dụng nhận credential

Một thiết kế phổ biến:

~~~text
Secret rotation controller
          |
          v
   Secrets Manager
          |
   +------+------+
   |             |
   v             v
App Pod A      App Pod B
   |             |
MongoClient    MongoClient
   \             /
         MongoDB
~~~

Secrets Manager có thể là Vault, cloud secret manager hoặc nền tảng nội bộ hỗ trợ versioning, policy và audit.

### 10.1. Nguyên tắc tích hợp

- Mỗi workload chỉ đọc secret cần dùng.
- Dùng workload identity/short-lived token cho quyền đọc secret nếu có.
- Secret logical name ổn định, version thay đổi.
- Có staging/current/retired lifecycle.
- Không ghi plaintext vào CI logs.
- Có audit cho thao tác đọc và thay.
- Xác định quy trình recovery nếu secret manager gián đoạn.

### 10.2. Environment variables không tự reload

Một process đã nhận biến môi trường lúc start không chắc nhận giá trị mới khi Kubernetes Secret hoặc cloud secret thay đổi. Mounted secret files có thể cập nhật theo cơ chế riêng, nhưng ứng dụng vẫn phải có logic đọc lại và tạo client mới.

**Đổi secret trong kho không đồng nghĩa đổi mọi connection đang dùng.**

### 10.3. Đừng hardcode vào URI

URI an toàn hơn trong tài liệu là dạng placeholder:

~~~text
mongodb://db1.example.test:27017/?authSource=appdata&tls=true
~~~

Nếu URI chứa username/password thật, phải bảo vệ URI như secret. Những ký tự `: / ? # [ ] @` trong username/password cần percent-encode đúng khi đặt vào connection string.

### 10.4. Nhất quán giữa environments

Không tái sử dụng password production cho staging. Không để consumer staging có quyền đọc `mongo/orders/prod`. Kiểm tra IAM bindings và namespace secrets.

## 11. TLS: mã hóa traffic và xác minh server

TLS bảo vệ đường truyền giữa ứng dụng và `mongod`/`mongos`.

~~~text
Application / mongosh
        |
        | verify server CA + hostname
        v
      TLS
        |
        v
mongod / mongos
~~~

TLS server certificate bảo đảm client đang kết nối đúng máy chủ đã được CA tin cậy chứng thực; SCRAM xác minh danh tính database user ở một lớp khác.

### 11.1. Những thành phần của TLS

- **Leaf/server certificate:** định danh endpoint.
- **Private key:** bí mật dùng chứng minh quyền sở hữu certificate.
- **Intermediate/root CA:** chuỗi tin cậy để verify certificate.
- **SAN:** hostname/IP được certificate chứng thực.
- **Validity:** Not Before/Not After.
- **EKU:** certificate dùng để xác thực server hay client.

### 11.2. SAN và hostname

Nếu client kết nối `db1.example.test` nhưng certificate chỉ có SAN `db2.example.test`, hostname verification sẽ thất bại.

Không sửa bằng `tlsInsecure=true` hoặc `tlsAllowInvalidHostnames=true` trong production. Hãy sửa certificate hoặc hostname.

### 11.3. TLS không tự cấp quyền MongoDB

Một client có thể verify server certificate thành công nhưng SCRAM auth vẫn lỗi vì thiếu user/password hoặc authSource sai. Ngược lại, password đúng vẫn không nên dùng qua đường truyền không TLS.

## 12. Cấu hình TLS trên self-managed mongod

Đoạn minh họa, **không phải toàn bộ file cấu hình cho một replica set**:

~~~yaml
net:
  port: 27017
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/server.pem
    CAFile: /etc/mongodb/tls/trusted-ca.pem

security:
  authorization: enabled
~~~

- `requireTLS`: yêu cầu kết nối TLS.
- `certificateKeyFile`: PEM chứa server certificate và private key tương ứng.
- `CAFile`: chain tin cậy cho những peer certificates cần verify.
- `authorization: enabled`: bật kiểm tra quyền truy cập.

Replica set/sharded cluster còn cần internal authentication và các tùy chọn topology tương ứng. Không sao chép cấu hình ngắn này thay nguyên file `mongod.conf` đang chạy.

### 12.1. Quyền private key

Private key phải chỉ được đọc bởi service process và những operators cần thiết. Không:

- Commit PEM vào Git.
- Copy private key vào Docker image.
- Gửi PEM qua ticket/chat.
- Ghi nội dung key vào logs.
- Đặt file cho toàn bộ users trên máy đọc.

### 12.2. Xem thông tin chứng chỉ mà không in private key

Trên máy có OpenSSL:

~~~bash
openssl x509 \
  -in /etc/mongodb/tls/server.pem \
  -noout -dates -subject -issuer -ext subjectAltName
~~~

Xem `notBefore/notAfter`, subject, issuer, SAN. Nếu có EKU, phải phù hợp vai trò certificate.

### 12.3. Monitor expiry

MongoDB có thể cảnh báo certificate sắp hết hạn trong vòng 30 ngày khi kết nối, nhưng nên có cảnh báo PKI chủ động như 30/14/7 ngày trước expiry hoặc theo chính sách tổ chức.

## 13. TLS certificate rotation bằng rotateCertificates

Từ **MongoDB 5.0**, self-managed `mongod` và `mongos` hỗ trợ nạp lại một số TLS artifacts bằng `rotateCertificates`.

Theo tài liệu MongoDB, có thể rotate:

- TLS certificates.
- CA files.
- CRL files trên Linux/Windows theo điều kiện.
- OCSP stapled response cũng có thể được refresh theo cấu hình.

### 13.1. Quy trình chung

1. Cấp certificate mới.
2. Kiểm tra chain, SAN, EKU, validity và private key.
3. Thay file tại **cùng path và filename** mà MongoDB đã cấu hình.
4. Nếu encrypted TLS certificate dùng `certificateKeyFilePassword`, password của PEM mới phải **giữ nguyên** với password cấu hình cũ cho online rotation.
5. Kết nối mongosh vào đúng process.
6. Chạy command.
7. Tạo một **kết nối mới** để kiểm tra certificate mới.
8. Kiểm tra logs, errors và replica health.
9. Lặp lại theo từng node/process có kiểm soát.

### 13.2. Câu lệnh

~~~javascript
use admin

db.runCommand({ rotateCertificates: 1 });
~~~

Hoặc helper:

~~~javascript
db.rotateCertificates();
~~~

Cần quyền `rotateCertificates` thích hợp, thuộc tập quyền của role `hostManager`. Không cấp role đó cho application writer.

### 13.3. Existing connections có bị ngắt không?

Theo MongoDB Manual:

- Lệnh rotation **không chủ động chấm dứt existing connections**.
- Các phiên TLS đã có có thể tiếp tục sử dụng certificate cũ.
- New connections dùng certificate mới.
- Cert files mới không hợp lệ có thể làm rotation thất bại mà không hủy TLS config hiện đang hoạt động.

Vì vậy, kiểm tra thông qua connection pool cũ **không đủ**. Phải xác minh bằng new TLS handshake.

### 13.4. Lệnh này không chạy tự động cho mọi node

Không coi gọi `db.rotateCertificates()` trên một mongos là đã rotate toàn bộ mongod/mongos của sharded cluster. Quản lý từng process theo danh sách inventory/rollout.

### 13.5. Những giới hạn

- Một process chỉ xử lý một rotation request đồng thời.
- Cần path/filename không đổi.
- Encrypted PEM passphrase không thể đổi cùng lúc bằng cách đơn giản này.
- Không dùng command cho deployment/version không hỗ trợ.
- Với certificate selector/OS behavior riêng cần kiểm tra docs đúng bản.

## 14. Gia hạn leaf certificate và CA rollover

**Thay leaf certificate** ký bởi cùng một CA thường đơn giản hơn **chuyển CA**.

Khi CA thay đổi, cần giai đoạn overlap:

~~~text
1. Clients chỉ tin CA-old
2. Clients tin CA-old + CA-new
3. Servers chuyển sang cert ký CA-new
4. Verify mọi client đã nhận trust mới
5. Bỏ CA-old khi an toàn
~~~

### 14.1. Vì sao phải overlap CA?

Nếu server đã dùng cert do CA-new ký nhưng Java truststore chỉ biết CA-old, TLS handshake lỗi trước khi user SCRAM có cơ hội xác thực.

### 14.2. Cần kiểm kê tất cả clients

- API pods.
- Batch jobs.
- ETL/backup tools.
- Monitoring agents.
- mongosh/Compass.
- Replica set internal connections.
- mongos và config servers nếu là sharded cluster.

### 14.3. CRL và OCSP

Certificate revocation có thể dựa trên CRL, OCSP hoặc các policies khác tùy client/server. Kiểm tra network tới revocation responder và failure behavior. Không mặc định phát hành cert mới đã làm cert cũ mất hiệu lực.

### 14.4. Nếu private key đã lộ

Gia hạn certificate **không đủ**. Cần revoke cert cũ theo PKI policy, điều tra phạm vi ảnh hưởng và thay key material thật sự, không chỉ thay ngày hết hạn.

## 15. X.509 client authentication và mTLS

TLS một chiều giúp client xác thực server; **mTLS** thêm bước server xác thực client certificate.

~~~text
Client                            MongoDB
  |------ TLS ClientHello ---------->|
  |<----- Server certificate --------|
  |------ Client certificate ------->|
  |        Mutual authentication     |
  |<===== Encrypted traffic ========>|
~~~

MongoDB có thể dùng X.509 để xác thực database user không cần SCRAM password.

### 15.1. X.509 user và $external trên self-managed

User X.509 thường có danh tính dựa trên certificate subject DN và được định nghĩa tại database đặc biệt `$external`.

Ví dụ **minh họa** khi deployment đã cấu hình X.509 và certificate subject được canonical hóa phù hợp:

~~~javascript
const externalDb = db.getSiblingDB("$external");

externalDb.runCommand({
  createUser: "CN=orders-service,OU=Apps,O=Example Corp,C=VN",
  roles: [
    { role: "readWrite", db: "appdata" }
  ]
});
~~~

DN thực tế phải khớp identity của certificate theo MongoDB certificate-matching rules. Đây không phải phương pháp sửa user trên Atlas.

### 15.2. Rotation client X.509

1. Cấp cert/key mới hợp lệ.
2. Kiểm tra subject/issuer/EKU/clientAuth và trust chain.
3. Đảm bảo MongoDB tin CA mới.
4. Nếu subject DN đổi, chuẩn bị user/role mapping mới.
5. Phân phối private key qua secrets manager hoặc file mount bảo vệ.
6. Tạo client/TLS session mới, kiểm tra role.
7. Chuyển toàn bộ services.
8. Revoke cert cũ và kiểm tra consumers không còn dùng.

Nếu subject giữ nguyên và trust policy phù hợp, có thể giữ principal mapping cũ; nếu subject đổi thì phải đánh giá user mapping.

### 15.3. Atlas-managed X.509

Atlas có workflow cấp/gia hạn X.509 riêng. Sử dụng Atlas UI/API theo chính sách dự án, không áp nguyên các lệnh quản trị user self-managed.

## 16. Java Sync Driver: SCRAM qua TLS mà không nhúng password vào URI

Giả định service có một `secretProvider` do ứng dụng triển khai, lấy secret từ kênh được bảo vệ:

~~~java
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoCredential;
import com.mongodb.ServerAddress;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import java.util.List;

// secretProvider là abstraction của ứng dụng.
char[] password = secretProvider.readPassword(
    "mongo/orders-api/prod"
);

MongoCredential credential =
    MongoCredential.createScramSha256Credential(
        "orders_svc_v2",
        "appdata",
        password
    );

MongoClientSettings settings =
    MongoClientSettings.builder()
        .applyToClusterSettings(builder ->
            builder.hosts(
                List.of(new ServerAddress("db1.example.test", 27017))
            )
        )
        .credential(credential)
        .applyToSslSettings(builder -> builder.enabled(true))
        .build();

MongoClient mongoClient = MongoClients.create(settings);
~~~

Đây là ví dụ kỹ thuật rút gọn cho một host. Production replica set/SRV cần cấu hình topology, retry, timeouts và pooling đúng. Không hardcode host/password thật vào tutorial.

### 16.1. Không ghép password vào URI tùy tiện

Các ký tự đặc biệt như `@`, `:`, `/`, `?` và `#` trong password phải percent-encode khi dùng connection string. Dùng `MongoCredential` giúp tránh tự xử lý escaping của password trong URI.

### 16.2. TLS truststore Java

JDK có thể dùng truststore mặc định hoặc truststore riêng chứa CA. Các system properties phổ biến:

~~~text
javax.net.ssl.trustStore
javax.net.ssl.trustStorePassword
~~~

Nếu server certificate dùng private CA, client phải tin CA đó một cách an toàn.

### 16.3. mTLS client keystore

Khi ứng dụng dùng client certificate, Java cần private key/cert trong keystore hoặc `SSLContext` phù hợp:

~~~text
javax.net.ssl.keyStore
javax.net.ssl.keyStorePassword
~~~

Ví dụ gắn SSLContext được tạo và kiểm tra trước đó:

~~~java
MongoClientSettings settings =
    MongoClientSettings.builder()
        .credential(MongoCredential.createMongoX509Credential())
        .applyToSslSettings(builder -> {
            builder.enabled(true);
            builder.context(sslContext);
        })
        .build();
~~~

`sslContext` là biến do ứng dụng chuẩn bị; nó không tự sinh cert/CA. Không tắt hostname verification khi cấu hình sai.

### 16.4. Credentials rotation và MongoClient

Thay một secret trong mounted file hoặc secrets manager không đảm bảo `MongoClient` đang chạy tự xác thực lại với secret mới. Có thể cần xây MongoClient/SSLContext mới, chuyển traffic rồi đóng pool cũ.

## 17. Quản lý cluster membership keyfile

Replica set members và các thành viên của sharded cluster cần xác thực với nhau. Self-managed deployments có thể dùng shared **membership keyfile**.

~~~text
mongod-A ---- secret nội bộ ---- mongod-B
   |
   +-------- secret nội bộ ---- mongod-C
~~~

Ví dụ cấu hình:

~~~yaml
security:
  authorization: enabled
  keyFile: /etc/mongodb/keys/cluster-keyfile
~~~

Keyfile này **không phải** password app và **không phải** `encryptionKeyFile` của storage engine.

### 17.1. Keyfile chứa nhiều keys

MongoDB hỗ trợ YAML keyfile có một key hoặc một sequence các keys. Hai members có thể xác thực nếu có **ít nhất một key chung**.

Keys phải dùng các ký tự/độ dài được MongoDB hỗ trợ, được sinh ngẫu nhiên và phân phối an toàn. Trên Unix, file không được có group/world permissions.

### 17.2. Luân chuyển theo hai giai đoạn

**Giai đoạn A:** Các nodes chấp nhận cả old và new:

~~~yaml
- "OLD_KEY_FROM_SECURE_GENERATOR"
- "NEW_KEY_FROM_SECURE_GENERATOR"
~~~

Các chuỗi trên là **placeholders**, không phải secrets có thể đưa vào production.

Triển khai file có cả hai keys, rồi rolling restart từng node, secondaries trước. Đợi secondary khỏe và replication ổn định sau mỗi restart. Primary được step down có kế hoạch rồi restart.

**Giai đoạn B:** Sau khi mọi node chấp nhận old+new, chuyển sang chỉ new:

~~~yaml
- "NEW_KEY_FROM_SECURE_GENERATOR"
~~~

Thực hiện một vòng rolling restart tiếp theo. Khi hoàn tất, old key không còn được sử dụng để xác thực membership.

### 17.3. Vì sao không đổi thẳng một node sang new?

Nếu node A chỉ có new còn B/C chỉ có old, không có key chung, authentication nội bộ có thể thất bại, gây mất khả năng tham gia replica set.

### 17.4. Không restart đồng thời toàn replica set

Đảm bảo quorum, election, replication health; dùng `rs.status()` và metrics trước/sau. Sharded clusters có thêm config server replica set, shards và mongos, cần runbook toàn topology.

## 18. Phân biệt membership keyfile và at-rest encryption keyfile

| Tiêu chí | `security.keyFile` | `security.encryptionKeyFile` |
|---|---|---|
| Mục đích | Internal authentication | Encryption at rest local key management |
| Nơi dùng | Replica/sharded members | Encrypted WiredTiger storage engine |
| YAML chứa nhiều keys | Có | Không dùng quy trình này |
| Rotation | Overlap old/new + rolling restarts | Không hỗ trợ local key rotation theo cách tương đương |
| Rủi ro thao tác sai | Thành viên không xác thực được | Có thể không giải mã được dữ liệu |

MongoDB Manual nêu **local key management** cho encryption at rest không hỗ trợ key rotation trực tiếp. Nếu cần rotation, sử dụng key manager/KMIP workflow hoặc quy trình thay node/re-encryption theo tài liệu.

**Không** thay `encryptionKeyFile` bằng một chuỗi ngẫu nhiên mới giống cách thay password app. Điều này có thể làm hỏng khả năng đọc dữ liệu đã mã hóa.

## 19. X.509 authentication giữa các cluster members

Một phương án thay membership keyfile là X.509 internal authentication.

Ví dụ cấu hình **minh họa**:

~~~yaml
security:
  clusterAuthMode: x509

net:
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/server.pem
    clusterFile: /etc/mongodb/tls/member.pem
    CAFile: /etc/mongodb/tls/trusted-ca.pem
~~~

Các member certificates phải thỏa điều kiện CA, distinguished name và EKU tương ứng:

- `certificateKeyFile` dùng làm server certificate cần `serverAuth` nếu EKU có mặt.
- `clusterFile` cho internal client authentication cần `clientAuth`.
- Nếu một cert dùng cho cả server/client roles, EKU cần hỗ trợ cả hai theo hướng dẫn.

Khi rotate, không chỉ kiểm tra certificate mới chưa hết hạn: phải kiểm tra DN matching, O/OU/DC theo MongoDB cluster membership requirements và trust chain của tất cả members.

## 20. Master key/KMS/CMK và dữ liệu mã hóa at rest

TLS bảo vệ data **in transit**. Encryption at rest bảo vệ dữ liệu đã lưu trên disk.

MongoDB Atlas có encryption at rest do hạ tầng quản lý và tùy chọn customer-managed keys theo cấu hình hỗ trợ. Self-managed MongoDB Enterprise encrypted storage engine có thể tích hợp KMIP để quản lý master key.

~~~text
MongoDB data files
      |
      v
Internal database keys
      |
      v
Master key (KMS/KMIP)
      |
      v
Key manager
~~~

### 20.1. Rotate master key khác rotate password

Đổi `db.changeUserPassword` không xoay master encryption key. `rotateCertificates` cũng không re-encrypt data at rest.

### 20.2. KMIP master key rotation

MongoDB cung cấp workflow rotate Customer Master Key cho môi trường Enterprise/KMIP hỗ trợ. Có thể re-encrypt internal keystore bằng CMK mới, trong khi các database keys bên trong giữ nguyên, tránh phải re-encrypt toàn bộ dataset.

Đây là workflow quản trị storage-engine/replica-set, có thể gồm restart/stepdown. Cần làm theo tài liệu đúng version và chỉ xoay từng member để không làm giảm write quorum.

### 20.3. Backup phụ thuộc keys cũ

Dữ liệu backup từ trước có thể cần master key/DEK cũ để giải mã. Không xóa KMS keys cũ ngay sau khi cluster production đã dùng key mới.

Cần:

1. Inventory backups/snapshots.
2. Xác định key dependencies.
3. Kiểm tra quyền giải mã.
4. Thử recovery theo policy.
5. Chỉ retire key khi mọi bản sao phụ thuộc đã được xử lý.

## 21. CSFLE/Queryable Encryption: DEK và CMK

MongoDB hỗ trợ các hình thức mã hóa field phía client trên deployment/driver phù hợp.

~~~text
Sensitive field
      |
      v
Data Encryption Key (DEK)
      |
      v
Encrypted DEK in Key Vault
      |
      v
Customer Master Key (CMK)
      |
      v
Cloud KMS / KMIP
~~~

**DEK rotation và CMK rotation là hai hành động khác nhau.**

- **Rewrap DEK:** mã hóa lại phần khóa dữ liệu được bảo vệ bởi CMK, dùng API như `rewrapManyDataKey()` ở driver/tính năng phù hợp.
- **Thay DEK thực sự:** có thể yêu cầu re-encrypt ciphertext fields tùy thiết kế và loại encryption.

Không tuyên bố thay CMK đồng nghĩa mọi encrypted fields đã được mã hóa lại từ đầu.

### 21.1. Key Vault permissions

Ứng dụng nghiệp vụ chỉ được cấp quyền cần thiết cho encryption operation. Không dùng cùng một service credential vừa đọc/write dữ liệu vừa quản trị toàn bộ KMS/Key Vault nếu không có lý do.

## 22. Runbook rotation: Prepare → Stage → Switch → Revoke

### Pha 1 — Prepare

1. Xác định secret type, owner và phạm vi.
2. Liệt kê mọi consumers.
3. Xác minh Atlas/self-managed và server version.
4. Có change approval, lịch maintenance/SLO.
5. Kiểm tra backup/recovery nếu liên quan keys at rest.
6. Xác định health checks và alerting.
7. Chuẩn bị rollback.
8. Rà soát privilege/ACL cần thiết.

### Pha 2 — Stage

1. Sinh hoặc cấp secret/certificate mới qua kênh đáng tin.
2. Xác minh metadata: roles, SAN, EKU, CA, expiry, dimension/key format.
3. Lưu trong secrets manager với version mới.
4. Cấp read access đúng consumers.
5. Có overlap old/new nếu cơ chế cho phép.
6. Canary kết nối mới.

### Pha 3 — Switch

1. Chuyển từng nhóm app pods/nodes.
2. Mở new TLS/SCRAM connections.
3. Kiểm tra read/write với quyền cho phép.
4. Theo dõi auth failures, TLS errors, pool churn, latency.
5. Với replica set, kiểm tra health/quorum sau từng bước.
6. Đợi consumers chạy theo chu kỳ hoàn thành kiểm chứng.

### Pha 4 — Revoke

1. Xác nhận toàn bộ consumers đã chuyển.
2. Thu hồi user/cert/key cũ theo cơ chế thích hợp.
3. Thu hồi secret version/quyền read không còn cần.
4. Kiểm tra credential cũ không thể dùng qua một bài test được phê duyệt.
5. Cập nhật inventory và audit trail.
6. Đặt rotation deadline tiếp theo.

### 22.1. Không revoke trước switch nếu cần uptime

Một tài khoản mới đúng cú pháp nhưng thiếu quyền read trên collection vẫn có thể vượt qua `ping`. Canary phải kiểm tra chức năng thật trước khi thu hồi old principal.

### 22.2. Rollback khi secret đã compromise

Nếu secret cũ bị lộ, không rollback về nó chỉ để giữ uptime. Khi đó áp incident-response policy: ưu tiên containment, hạn chế quyền/network và sử dụng principal thay thế an toàn.

## 23. Monitoring và audit khi luân chuyển

### 23.1. Metrics cần theo dõi

- `AuthenticationFailed` / error code 18.
- TLS handshake errors.
- Connection pool timeouts.
- API 5xx và latency p95/p99.
- Số app pods dùng version cũ.
- Job failures.
- Replica set health/elections/replication lag.
- Certificate expiry.
- Rotation attempts/success/failures.
- Unusual secret access.

### 23.2. Log có thể chứa metadata, không chứa secret

Ví dụ audit record:

~~~json
{
  "event": "mongo-secret-rotation",
  "service": "orders-api",
  "principalVersion": "v2",
  "result": "success",
  "mechanism": "SCRAM-SHA-256"
}
~~~

Không log:

~~~text
plaintext password
MongoDB URI có password
private key
full PEM certificate keyfile
KMS key material
secrets manager access token
~~~

### 23.3. Lỗi chỉ xuất hiện sau nhiều ngày

Một scheduled job mỗi tuần có thể không chạy trong cửa sổ rollout. Secret inventory và xác nhận scheduled consumers quan trọng hơn chỉ quan sát API traffic vài phút.

## 24. Incident response khi secret bị lộ

Khi connection URI trong Git public hoặc private key bị rò rỉ:

1. Xác định secret bị lộ, nơi rò rỉ và thời gian có thể bị khai thác.
2. Hạn chế quyền truy cập, network reachability và các principal bị nghi compromise.
3. Sinh secret mới bằng kênh an toàn.
4. Deploy clients với credential mới; thu hồi cũ sớm theo mức độ khẩn cấp.
5. Kiểm tra logs/authentication/audit để phát hiện truy cập bất thường.
6. Kiểm tra exfiltration, backup exposure và systems dùng chung secret.
7. Revoke certificate/key cũ đúng PKI/KMS policy.
8. Sửa nguồn rò rỉ: CI logs, repository, secret manager permissions.
9. Thực hiện reporting/notification theo security policy.
10. Xem xét postmortem và cải thiện automation.

**Chỉ đổi password không đủ** nếu attacker vẫn có thể đọc secret mới từ CI hoặc secrets manager.

### 24.1. Private key bị lộ có thể kéo theo PKI revocation

Nếu private key TLS cũ lộ, phát hành certificate mới không tự làm certificate cũ bị từ chối. Cần kiểm tra revocation/trust và mọi nơi đã chấp nhận cert đó.

### 24.2. Không tắt TLS validation để cứu một deployment lỗi cert

`tlsInsecure` và `invalidHostNameAllowed` có thể che giấu vấn đề trust, nhưng làm giảm an toàn. Phải sửa certificate/CA/hostname.

## 25. Một số lệnh kiểm tra ít tác động

### 25.1. Xem danh tính của session

~~~javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
~~~

### 25.2. Thử kết nối ở mức cơ bản

~~~javascript
db.runCommand({ ping: 1 });
~~~

`ping` không thay quyền test nghiệp vụ.

### 25.3. Xem trạng thái replica set

~~~javascript
rs.status();
~~~

Dùng trước và sau rolling restart. Không chạy stepDown/shutdown chỉ để “xem” replica set.

### 25.4. Xem validity của certificate

~~~bash
openssl x509 \
  -in /etc/mongodb/tls/server.pem \
  -noout -dates -subject -issuer -ext subjectAltName
~~~

Không paste private key vào nơi công khai để nhờ kiểm tra.

## 26. Lỗi thường gặp

| Hiểu nhầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Atlas users đổi qua db.changeUserPassword | Unsupported management path | Atlas UI/CLI/Admin API |
| SCRAM không cần TLS | Lộ thông tin khi management commands | Bật TLS |
| Đổi password không ảnh hưởng apps | New auth lỗi | Dual-account/canary |
| Secret Manager đổi là pods tự đổi | Process chưa reload | Tạo MongoClient mới/rolling rollout |
| Một credential cho mọi dịch vụ | Blast radius lớn | Per-service principal |
| Dùng role root cho app | Quá nhiều quyền | Least privilege |
| Password trong URI không encode | Authentication lỗi | Percent-encode hoặc MongoCredential |
| Đổi cert thì tất cả connections dùng cert mới | Existing TLS sessions còn cũ | Test kết nối mới |
| Một rotateCertificates cập nhật toàn cluster | Nodes khác chưa đổi | Rollout từng process |
| Đổi encrypted PEM passphrase khi rotate trực tiếp | Không phù hợp điều kiện | Runbook khác/restart |
| Đổi CA trước khi trust clients cập nhật | TLS handshake fail | Overlap CA |
| Cert mới là cert cũ đã revoke | Certificate cũ có thể còn hợp lệ | PKI revocation |
| Dùng tlsInsecure để sửa lỗi | Mất hostname/CA validation | Sửa SAN/trust |
| Membership keyfile giống encryptionKeyFile | Rủi ro không đọc được dữ liệu | Phân biệt chức năng |
| Đổi keyfile thẳng một node | Không còn shared key | Overlap old+new |
| Restart tất cả members cùng lúc | Mất quorum | Rolling restart |
| Đổi CMK là đổi SCRAM | Nhầm lớp security | KMS workflow |
| Xóa key cũ khi production chạy được | Backups có thể mất khả năng giải mã | Key dependency inventory |
| Chỉ test ping là đủ | Roles bị thiếu | Test use case |
| Không kiểm tra scheduled jobs | Lỗi xuất hiện trễ | Consumer inventory |
| Log full URI/private key | Lộ bí mật | Redaction |
| Rollback về secret đã lộ | Tiếp tục compromise | Incident process |

## 27. Bài tập và tình huống thực hành

Không chạy DDL/user rotation trên production. Các bài self-managed cần replica set hoặc standalone lab phù hợp và quyền được cấp.

### Bài 1 — Phân loại secrets

SCRAM password, server TLS private key, client X.509 key, membership keyfile và KMS CMK có cùng mục đích không? Viết bảng phân biệt.

### Bài 2 — Authentication và authorization

Một app đã đổi password nhưng vẫn có role `root`. Vấn đề gì chưa được xử lý?

### Bài 3 — Tạo SCRAM user

Tạo `lab_reporter_v1` trong database `appdata` với role `read` và `passwordPrompt()`.

### Bài 4 — authSource sai

User ở `appdata` nhưng client đặt `authSource=admin`. Giải thích lỗi có thể xảy ra.

### Bài 5 — Rotation trực tiếp

Đổi password của `lab_reporter_v1` trên self-managed lab. Vì sao new pooled connections có thể lỗi khi app chưa nhận secret?

### Bài 6 — Dual account

Viết các bước tạo `lab_reporter_v2`, canary, rollout, revoke v1. Giai đoạn nào có hai accounts cùng tồn tại?

### Bài 7 — Rollback có điều kiện

v2 thiếu quyền khi rollout 10%, v1 chưa bị lộ. Làm sao khôi phục traffic an toàn?

### Bài 8 — Atlas database users

Nêu nơi thay database password trên Atlas. Vì sao không dùng `db.changeUserPassword` trực tiếp?

### Bài 9 — Password URI

Mật khẩu chứa `@` và `#`. Vì sao cần percent-encode nếu dùng trong MongoDB URI?

### Bài 10 — TLS và SCRAM

TLS handshake thành công nhưng authentication fail. Hai lớp này kiểm tra những gì?

### Bài 11 — SAN mismatch

Client kết nối `db1.example.test` nhưng cert SAN chỉ có `db2.example.test`. Có nên tắt hostname verification không?

### Bài 12 — Chứng chỉ sắp hết hạn

Thiết kế alert 30/14/7 ngày trước expiry; owner và escalation cần những gì?

### Bài 13 — rotateCertificates

Từ MongoDB version nào có online certificate rotation? Có điều kiện gì về file path/filename và encrypted key password?

### Bài 14 — New connections

Vì sao phải test một TLS connection mới sau `rotateCertificates`?

### Bài 15 — CA rollover

Sắp xếp: clients tin old+new CA; servers chuyển cert; bỏ old CA. Vì sao thứ tự quan trọng?

### Bài 16 — X.509 user

Database nào chứa user X.509? Subject DN ảnh hưởng cách mapping principal thế nào?

### Bài 17 — Java TLS

Giải thích khác nhau giữa Java truststore và keystore.

### Bài 18 — Java client reload

Sau khi file certificate đổi, có nên dùng mãi MongoClient cũ? Đề xuất cách chuyển client pool.

### Bài 19 — Internal keyfile

Vì sao keyfile có thể chứa old và new keys cùng lúc? Điều kiện members xác thực được với nhau?

### Bài 20 — Rolling restart

Replica set 3 nodes nên rotate secondaries trước, primary sau vì sao? Kiểm tra health nào sau mỗi bước?

### Bài 21 — Keyfile phân biệt

`security.keyFile` khác `security.encryptionKeyFile` về mục đích và khả năng rotation thế nào?

### Bài 22 — Internal X.509

Khi EKU được khai báo, tại sao internal member cert cần đúng `clientAuth` và server cert cần `serverAuth`?

### Bài 23 — KMS master key

Thay password database user có xoay CMK không? Vì sao?

### Bài 24 — Backup

Nếu KMS key cũ bị xóa, điều gì có thể xảy ra với backup đã mã hóa từ trước?

### Bài 25 — DEK vs CMK

Rewrap DEK có giống re-encrypt mọi encrypted fields bằng DEK mới không?

### Bài 26 — Secrets Manager

Thiết kế metadata cho secret owner, consumers, version, rotation deadline. Những trường gì tuyệt đối không đưa vào bảng?

### Bài 27 — Kubernetes Secret

Khi Secret object thay nhưng ứng dụng chỉ đọc environment variable lúc start, vì sao app chưa chắc nhận secret mới?

### Bài 28 — Incident

Một URI MongoDB chứa password bị commit vào public repository. Lập runbook containment, đổi credential, revoke, audit và xử lý nguồn leak.

### Bài 29 — Debug authentication

Sau rotation xuất hiện `AuthenticationFailed` trên 20% requests. Liệt kê những kiểm tra về v1/v2 secrets, authSource, driver pools và roles.

### Bài 30 — Tổng hợp

Lập rotation plan cho: Atlas SCRAM user, self-managed membership keyfile, server TLS cert, Java client X.509 cert và KMS master key. Với mỗi loại, xác định owner, cách stage, thời điểm switch, verification, rollback và revoke.

## 28. Checklist production

### Mật khẩu và users

- [ ] User ứng dụng có roles tối thiểu.
- [ ] Mỗi service/environment có principal riêng.
- [ ] Password sinh ngẫu nhiên và lưu trong secrets manager.
- [ ] Không có plaintext credentials trong Git/log/ticket.
- [ ] authSource và authMechanism đúng.
- [ ] SCRAM management commands dùng TLS.
- [ ] Atlas user management qua Atlas tools hỗ trợ.
- [ ] Dual-account khi cần overlap.
- [ ] Consumers inventory đầy đủ.
- [ ] Canary đã kiểm tra chức năng thật.
- [ ] v1 được revoke sau verification.

### TLS/X.509

- [ ] SAN khớp hostname thực tế.
- [ ] CA chain và validity đúng.
- [ ] EKU serverAuth/clientAuth phù hợp.
- [ ] Private key permissions an toàn.
- [ ] Không bật tlsInsecure/tlsAllowInvalidHostnames.
- [ ] Expiry alerts đã được cấu hình.
- [ ] rotateCertificates được kiểm tra phiên bản/path/password constraints.
- [ ] New TLS connections đã kiểm tra.
- [ ] Có old/new CA trust overlap.
- [ ] Có phương án revoke old certificate.
- [ ] Java truststore/keystore/SSLContext được cập nhật.

### Internal security và encryption

- [ ] Membership keyfile khác at-rest encryption keyfile.
- [ ] Keyfile rotation dùng old+new overlap.
- [ ] Rolling restart giữ replica-set quorum.
- [ ] Internal X.509 DN/CA/EKU được kiểm tra.
- [ ] KMS/CMK rotation có runbook theo edition.
- [ ] Có backup và kiểm thử khôi phục.
- [ ] Không xóa key cũ khi còn backup phụ thuộc.
- [ ] DEK rewrap được phân biệt với re-encrypt data.

### Vận hành

- [ ] Có owner, deadline, version và consumers.
- [ ] Secrets Manager có audit/least privilege.
- [ ] Có metrics auth errors/TLS failures/pool churn.
- [ ] Có rollback và incident response.
- [ ] Rotation logs không chứa secret.
- [ ] Jobs chạy theo lịch đã được kiểm chứng.
- [ ] Không có hai rotation jobs cùng sửa một secret.
- [ ] Có phê duyệt trước khi thay đổi production.
- [ ] Có ghi nhận thời điểm revoke và next rotation.
- [ ] Đã kiểm thử trên staging.

## 29. Tổng kết

Trong MongoDB, **mật khẩu, chứng chỉ và khóa mã hóa** đều là thông tin nhạy cảm nhưng phục vụ những lớp khác nhau:

- **SCRAM password** xác thực database users. Self-managed hỗ trợ `db.changeUserPassword`; Atlas dùng Atlas management plane. Khi không thể chấp nhận downtime, dùng hai principals trong cửa sổ chuyển tiếp.
- **TLS certificate/private key** bảo vệ đường truyền và danh tính server/client. Kiểm tra SAN/CA/EKU, expiry và dùng `rotateCertificates` trên deployment hỗ trợ với những điều kiện cụ thể.
- **X.509/mTLS** xác thực clients hoặc cluster members bằng chứng chỉ; khi rotate cần quản lý trust chain và identity mapping.
- **Internal membership keyfile** có thể luân chuyển bằng old+new overlap rồi rolling restart, nhưng **at-rest encryption keyfile không dùng quy trình đó**.
- **KMS/CMK/DEK** có quy trình thay riêng; phải bảo vệ khả năng khôi phục historical data.
- **Secrets Manager** chỉ là điểm phát credentials; ứng dụng vẫn cần reload/recreate connection pools, canary, monitoring và revoke.

Mô hình hữu ích cho mọi loại rotation là: **kiểm kê → cấp mới → triển khai có kiểm soát → kiểm chứng → thu hồi cũ → audit**. Nếu secret đã bị compromise, an toàn thu hồi và xử lý nguồn lộ quan trọng hơn khả năng rollback về secret cũ.

## Tài liệu tham khảo chính thức

- [MongoDB Manual — db.changeUserPassword](https://www.mongodb.com/docs/manual/reference/method/db.changeuserpassword/)
- [MongoDB Manual — db.createUser](https://www.mongodb.com/docs/manual/reference/method/db.createuser/)
- [MongoDB Manual — db.updateUser](https://www.mongodb.com/docs/manual/reference/method/db.updateuser/)
- [MongoDB Atlas — Configure Database Users](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/)
- [MongoDB Manual — TLS/SSL Transport Encryption](https://www.mongodb.com/docs/manual/core/security-transport-encryption/)
- [MongoDB Manual — Configure TLS](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/)
- [MongoDB Manual — rotateCertificates](https://www.mongodb.com/docs/manual/reference/command/rotatecertificates/)
- [MongoDB Manual — Internal/Membership Authentication](https://www.mongodb.com/docs/manual/core/security-internal-authentication/)
- [MongoDB Manual — Rotate Replica Set Keys](https://www.mongodb.com/docs/manual/tutorial/rotate-key-replica-set/)
- [MongoDB Manual — Deploy Replica Set with Keyfile](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set-with-keyfile-access-control/)
- [MongoDB Manual — Rotate Encryption Key](https://www.mongodb.com/docs/manual/tutorial/rotate-encryption-key/)
- [MongoDB Manual — Configure Encryption](https://www.mongodb.com/docs/manual/tutorial/configure-encryption/)
- [MongoDB Atlas — Workload Identity Federation](https://www.mongodb.com/docs/atlas/workload-oidc/)
- [MongoDB Java Sync Driver — SCRAM](https://www.mongodb.com/docs/drivers/java/sync/current/security/auth/scram/)
- [MongoDB Java Sync Driver — X.509](https://www.mongodb.com/docs/drivers/java/sync/current/security/auth/x509/)
- [MongoDB Java Sync Driver — TLS](https://www.mongodb.com/docs/drivers/java/sync/current/security/tls/)
- [MongoDB Java Sync Driver — In-Use Encryption](https://www.mongodb.com/docs/drivers/java/sync/current/security/encrypt-fields/)
