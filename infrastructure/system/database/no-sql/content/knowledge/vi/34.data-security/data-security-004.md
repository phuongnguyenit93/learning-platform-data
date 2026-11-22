# Xác thực người dùng hoặc dịch vụ và quản lý vòng đời thông tin đăng nhập

Một ứng dụng Java kết nối đến MongoDB, Cassandra, Redis hoặc DynamoDB phải chứng minh **nó là ai** trước khi cơ sở dữ liệu cho phép thực hiện thao tác. Nhưng người dùng đăng nhập ứng dụng, ứng dụng xác thực đến database và một worker lấy quyền đọc secrets từ hệ quản lý danh tính là **ba ranh giới tin cậy khác nhau**. Nếu dùng lẫn lộn, một tài khoản bị lộ có thể biến từ quyền xem một hồ sơ thành quyền đọc toàn bộ dữ liệu khách hàng hoặc quyền xóa database.

Ví dụ, một Booking API phục vụ khách hàng cần:

- Xác thực **người dùng cuối** khi họ gửi yêu cầu xem hoặc đặt phòng.
- Xác định người dùng có quyền truy cập đúng booking/tenant hay không.
- Xác thực **dịch vụ Booking API** khi kết nối database.
- Giới hạn tài khoản database chỉ được thực hiện những thao tác cần thiết.
- Phân phối, thay thế, thu hồi và giám sát thông tin đăng nhập mà không làm gián đoạn toàn bộ dịch vụ.

Trong chương **Bảo mật dữ liệu** của module **Database No SQL**, bài này phân biệt xác thực với phân quyền, mô hình danh tính người dùng và service/workload, password/MFA/OIDC, SCRAM, TLS/mTLS, IAM và token ngắn hạn; đồng thời thiết kế **vòng đời thông tin đăng nhập** từ cấp phát tới xoay vòng, thu hồi và kiểm toán. Các ví dụ Java và sơ đồ vận hành tập trung vào những lỗi dễ gặp khi triển khai NoSQL trong môi trường nhiều services.

> **Nguyên tắc cốt lõi:** database credential của một service là danh tính kỹ thuật của service, **không phải** danh tính của người dùng đang gọi API. Xác thực trả lời “ai đang kết nối?”, còn phân quyền và kiểm tra ownership trả lời “họ được làm gì với dữ liệu nào?”.

## 1. Bốn lớp cần tách trong một request

~~~text
Người dùng
    |
    | (1) Đăng nhập bằng passkey/MFA/OIDC
    v
Identity Provider (IdP)
    |
    | Access token/session
    v
Java Booking API
    | (2) Xác minh token/session
    | (3) Kiểm tra quyền thao tác booking/tenant
    |
    | (4) Xác thực bằng workload identity/DB credentials
    v
NoSQL Database
    |
    +--> Chỉ cho phép role của Booking API
~~~

**Bốn bước không thay thế cho nhau:**

1. **User authentication:** xác thực chủ thể là người dùng thật hoặc một tài khoản người dùng.
2. **Application authorization:** kiểm tra quyền trên endpoint, resource, tenant và trạng thái nghiệp vụ.
3. **Service authentication:** chứng minh Booking API/worker là workload đã được cấp quyền kết nối.
4. **Database authorization:** database kiểm quyền thao tác theo user/role/IAM policy của kết nối.

Nếu Java service kết nối bằng một database account có quyền rộng, database có thể không biết user cuối là ai. Khi đó app **phải bảo vệ tenant isolation** đúng cách; DB account không tự thực hiện mọi kiểm tra ownership của từng user.

## 2. Phân biệt authentication, authorization và accounting

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication (AuthN) | Ai đang kết nối? | SCRAM xác minh DB user |
| Authorization (AuthZ) | Chủ thể được làm gì? | Role chỉ được đọc collection listings |
| Accounting/Auditing | Chủ thể đã làm gì, khi nào? | Audit event ghi nhận UPDATE |
| Identification | Tên/ID chủ thể tự khai | Username trong request |
| Session management | Sau khi đăng nhập, phiên nào còn hợp lệ? | Access token 15 phút |

Một username truyền trong HTTP header do client tự tạo **chưa phải bằng chứng**. Chỉ sau khi kiểm chứng token/session hoặc một cơ chế xác thực tương đương, hệ mới có cơ sở gán request cho principal đó.

**Ví dụ:** `userId=U42` trong JSON body không cho phép client sửa booking của U42; app phải xác thực principal và kiểm ownership/tenant dựa trên dữ liệu có thẩm quyền.

## 3. Các loại principal

| Principal | Điểm nhận dạng | Credential thường gặp |
| --- | --- | --- |
| Người dùng cuối | User/account tại IdP | Passkey, password + MFA, session/token |
| Service/workload | Deployment, workload identity | IAM role, service token, mTLS cert |
| Batch/CDC worker | Job hoặc consumer | Service account, workload federation |
| Administrator | Nhân sự vận hành | SSO/MFA, tài khoản break-glass riêng |
| Automation/CI | Pipeline có scope | Federated OIDC, ephemeral role |
| Database internal node | Thành viên cluster | Certificates, keyfile, internal auth tùy DB |

Nguyên tắc: **không chia một credential chung cho tất cả principal**. Mỗi service/environment nên có identity riêng để thu hồi theo phạm vi và audit được.

## 4. Danh tính người dùng không nên đi thẳng vào database

Một anti-pattern:

~~~text
Browser → MongoDB/Redis endpoint
          with application DB username/password
~~~

Nếu gửi DB credentials xuống browser/mobile app, người dùng có thể trích xuất chúng khỏi ứng dụng. Sau đó họ có thể kết nối ngoài API, bỏ qua kiểm tra nghiệp vụ, rate limit và tenant authorization.

**Thiết kế thông dụng hơn:**

~~~text
Browser/Mobile -- user token --> API
API -- app-owned DB credential --> NoSQL
~~~

API dùng principal đã xác thực để lựa chọn query và kiểm quyền. Database role giới hạn **blast radius** nếu API hoặc secret bị lộ. Có những kiến trúc dùng identity propagation tới DB; khi dùng, phải có hỗ trợ từ DB và giao thức delegation rõ ràng, không tự nhận rằng user token HTTP có thể thay DB credential.

## 5. Threat model: điều gì có thể bị tấn công?

| Nguy cơ | Kịch bản | Hàng rào bảo vệ |
| --- | --- | --- |
| Lộ password | Password trong Git hoặc log | Secret manager, quét secret, rotation |
| Password spraying | Thử mật khẩu phổ biến trên nhiều accounts | MFA, rate limit, monitoring |
| Credential stuffing | Dùng mật khẩu rò rỉ từ nơi khác | MFA/passkey, kiểm mật khẩu yếu |
| Replay token | Access token bị đánh cắp | TLS, lifetime ngắn, audience, revocation strategy |
| Service impersonation | Workload giả mạo service thật | Workload identity, mTLS, issuer/audience validation |
| Privilege escalation | App dùng admin account | Least privilege, separation of duties |
| Lateral movement | Một secret dùng cho nhiều clusters | Per-service/environment accounts |
| Token confusion | ID token bị dùng như access token | Kiểm token type/audience/issuer |
| Lost revocation | Token/connection còn hiệu lực sau khóa account | Short TTL, connection recycling, audit |
| Confused deputy | API dùng quyền DB mạnh thay user không đúng | Per-request ownership/tenant checks |

Không có một cơ chế xác thực nào thay được các lớp bảo vệ còn lại. MFA giảm rủi ro mật khẩu bị lộ, nhưng không tự sửa phân quyền rộng. TLS bảo vệ truyền thông, nhưng không quyết định quyền truy cập record.

## 6. Kiểu thông tin đăng nhập và độ tin cậy

**Credential** là bằng chứng hoặc vật liệu dùng để chứng minh danh tính, ví dụ:

- Username + password.
- API key hoặc secret token.
- Private key kết hợp public-key certificate.
- Access token được cấp bởi IdP hoặc authorization server.
- Cloud workload identity sinh ra short-lived credentials.
- Client certificate trong mutual TLS.
- Hardware-backed credential/passkey cho người dùng.

Những loại này có vòng đời và tính năng thu hồi khác nhau:

| Kiểu | Điểm mạnh | Rủi ro cần quản lý |
| --- | --- | --- |
| Password dài hạn | Phổ biến, dễ tích hợp | Lộ, tái sử dụng, rotation khó |
| Static API key | Đơn giản cho automation | Khó truy nguồn nếu chia sẻ, dễ sống lâu |
| Short-lived access token | Giới hạn lifetime | Refresh, clock skew, bearer theft |
| mTLS certificate | Xác thực hai chiều bằng khóa bất đối xứng | CA trust, key bảo vệ, expiry/revocation |
| Cloud IAM role | Không cần nhúng khóa tĩnh | Policy, credential chain, trust configuration |
| Workload federation | Token theo identity deployment | Token exchange/issuer/audience, bootstrap |

**Ưu tiên danh tính workload và credentials ngắn hạn** khi hệ hạ tầng hỗ trợ, thay vì đưa database admin password vào mọi container.

## 7. Password người dùng: lưu và xác minh đúng cách

Nếu hệ bắt buộc tự quản lý password người dùng, **không lưu password dạng rõ** trong NoSQL document, không mã hóa có thể đảo ngược chỉ để so sánh password, và không dùng plain SHA-256/SHA-1 cho password storage.

Quy trình phù hợp:

~~~text
User chooses password
      |
      v
Password hashing function (Argon2id / phù hợp chính sách)
      |
      v
Store encoded hash parameters + unique salt + result
      |
      v
On login: verify candidate against stored representation
~~~

Một lựa chọn hiện đại phổ biến là **Argon2id** với memory/time/parallelism cost được đánh giá cho hạ tầng. Scrypt hoặc PBKDF2 có thể phù hợp trong các môi trường/yêu cầu cụ thể. Mỗi password cần **salt ngẫu nhiên riêng**; pepper nếu có phải được lưu và quản lý riêng với database.

### Những điều nên tránh

~~~text
password: "MyPassword123"
passwordHash: SHA256(password)
passwordHash: MD5(password)
~~~

Hash một lần bằng hàm nhanh rất dễ bị thử hàng loạt khi database bị lộ. Password hashing cần hàm chuyên dụng với cost phù hợp; đồng thời có rate limit, MFA và giám sát.

## 8. Đăng nhập người dùng: SSO, OIDC và MFA

Một ứng dụng hiện đại có thể dùng **OpenID Connect (OIDC)** với identity provider:

~~~text
User → IdP login (passkey/MFA)
     → application receives validated login result
     → application establishes session
     → API receives access token/session
~~~

Những điểm quan trọng:

- **OIDC** dùng để xác thực danh tính người dùng và bổ sung lớp identity cho OAuth 2.0.
- **Access token** dành cho API resource access, không tự đồng nghĩa ID token.
- **ID token** mô tả authentication event và đối tượng client, không dùng bừa như bearer credential để gọi mọi API.
- Nếu token là JWT, API phải kiểm chữ ký, issuer, audience, expiry, not-before và thuật toán/khóa được chấp nhận.
- Nếu token là opaque, API có thể cần introspection/session lookup theo IdP contract.
- Khi dùng browser, cân nhắc secure/HttpOnly/SameSite cookies và CSRF protection tùy flow.

**MFA và passkeys** tăng chống phishing/credential theft; recovery và reset MFA cũng phải có kiểm soát để không trở thành đường tắt.

## 9. JWT validation: không chỉ decode payload

Một chuỗi giống JWT thường có ba phần được phân tách:

~~~text
header.payload.signature
~~~

Việc Base64URL-decode payload **không chứng minh chữ ký đúng**.

API cần:

1. Chỉ chấp nhận issuer tin cậy (giá trị `iss`).
2. Chỉ nhận đúng audience của API (`aud`).
3. Kiểm expiration (`exp`), not-before (`nbf`) và clock skew hợp lý.
4. Kiểm signature bằng khóa tin cậy; hạn chế algorithms theo policy, không tin algorithm tùy ý từ token.
5. Kiểm token type/scope/permission cần thiết.
6. Phân biệt authentication và authorization trên từng resource.
7. Có chiến lược JWKS key rotation/cache/refresh; không chấp nhận khóa lạ tùy tiện.
8. Có revocation/session termination policy khi yêu cầu.

Không log nguyên access token/refresh token. Một token hợp lệ về chữ ký **vẫn có thể không đủ quyền** với booking cụ thể.

## 10. Authentication khác authorization ở database

Giả sử service kết nối MongoDB bằng tài khoản `booking-api`. SCRAM hoặc một cơ chế được cấu hình có thể xác nhận username/password. Sau đó DB áp dụng role:

~~~text
booking-api
  ├── read: reservations của app
  ├── update: những collection được phép
  └── không có quyền quản lý users/cluster
~~~

Vấn đề **per-user ownership** vẫn nằm ở application nếu DB principal đại diện cho cả service:

~~~text
Authenticated end user U42
  requests booking R99

API must verify:
  R99 belongs to U42 or U42 is otherwise authorized
~~~

Đừng coi “database cho phép query” là đủ chứng minh “người dùng được phép xem record”.

## 11. Least privilege và blast radius

Một matrix đơn giản:

| Workload | Quyền cần thiết | Quyền không nên có |
| --- | --- | --- |
| Catalog reader | Read published listings | User admin, write bookings |
| Booking writer | Read/write đúng booking collections | Drop database, manage cluster |
| CDC worker | Read change stream/required data | Modify business records |
| Analytics ETL | Read/append datasets được cho phép | Delete toàn bộ source |
| DBA/operator | Privileged admin qua quy trình được kiểm soát | Dùng cho request handling |

Một admin credential dùng chung cho toàn bộ services biến một incident nhỏ thành sự cố toàn cluster.

### Phân tầng danh tính

Nên có accounts/roles riêng theo **service, environment và chức năng**. Không dùng cùng database password cho production và staging, hoặc cho Booking API và một notebook phân tích.

## 12. Các nhóm cơ chế xác thực NoSQL

| Hệ | Cơ chế thường gặp | Phạm vi cần kiểm |
| --- | --- | --- |
| MongoDB | SCRAM; X.509 và cơ chế enterprise/cloud tùy deployment | auth database, roles, TLS |
| Cassandra | Role/password authentication khi được cấu hình; TLS và authorizer | Cluster roles, permissions, node-to-node config |
| Redis | ACL username/password; TLS khi được cấu hình | Command/key patterns, users |
| DynamoDB | AWS IAM credentials/roles, request signing | IAM policies, role trust, region/account |
| Managed NoSQL | Provider IAM/workload federation hoặc service-specific auth | Tenant/project/namespace scope |

**Mỗi sản phẩm, phiên bản và dịch vụ managed có semantics khác nhau.** Không giả định Redis password, MongoDB database user và AWS IAM role là những credential có thể thay thế lẫn nhau.

## 13. MongoDB: auth database, SCRAM và role

MongoDB có thể xác thực database user qua SCRAM. Ví dụ cấu trúc cấu hình:

~~~text
Application principal: booking-api
Authentication mechanism: SCRAM-SHA-256
Authentication database: admin (ví dụ; tùy nơi tạo user)
Authorized database/collection: booking
Transport: TLS
~~~

**Authentication database** là nơi user được tạo/đăng ký, không nhất thiết là database chứa business data. Sai `authSource` khiến login fail dù username/password đúng.

### Không hardcode credential trong URI của Git

Không:

~~~text
mongodb://booking-api:plain-secret@db.example.internal/booking
~~~

Đây là một ví dụ về **cách không nên lưu credential**, không phải chuỗi kết nối được phép dùng. Nếu URI chứa credential, không log/ghi vào commit, và phải mã hóa percent-encoding ký tự đặc biệt đúng theo driver.

Tốt hơn: nhận connection details và credential từ một secret provider/identity configuration an toàn; dùng TLS, role hẹp và logging redaction.

## 14. MongoDB Java: cấu hình kết nối có xác thực

Ví dụ với MongoDB synchronous driver; dependency và version phải được cấu hình ở project:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;

public final class MongoConnectionExample {
    public static void main(String[] args) {
        // Được inject an toàn từ deployment/secret provider.
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                    "MongoDB connection config is required");
        }

        ConnectionString connectionString =
                new ConnectionString(uri);

        // Không System.out.println(uri):
        // URI có thể chứa username/password.
        try (MongoClient client =
                MongoClients.create(connectionString)) {
            MongoDatabase db =
                    client.getDatabase("booking");

            // Tác vụ/health check phải theo policy
            // và quyền thực sự của service identity.
            db.runCommand(new org.bson.Document("ping", 1));
        }
    }
}
~~~

### Điểm phải hiểu

- Environment variable là cách **cấp vào runtime** minh họa, chưa tự là secret manager; env có thể lộ qua process inspection, diagnostics hoặc dump tùy môi trường.
- Production nên cân nhắc workload identity/secret manager, process isolation, restricted logs và runtime injection policy.
- TLS certificate verification/hostname validation phải cấu hình đúng; không tắt chỉ để “kết nối được”.
- `ping` có thể cần quyền phù hợp theo deployment; health check không nên đòi admin role.
- Driver connection pool cần được xử lý khi secret rotate, không chỉ cập nhật nơi lưu secret.

## 15. MongoDB: rotate user password không bằng đổi một biến

Giả sử service dùng password phiên bản `v1`:

~~~text
DB user booking-api: password v1
Java pods: pooled connections authenticated with v1
Secret manager: v1
~~~

Nếu đổi DB password sang `v2` trước khi ứng dụng có thể nhận `v2`, các **kết nối mới** có thể lỗi. Kết nối cũ có thể còn sống tùy DB/session/driver behavior, tạo cảm giác sự cố chưa xảy ra cho tới lúc pool reconnect.

Một rotation plan phải quản lý:

1. Credential mới và quyền tương đương cần thiết.
2. Phân phối credential mới.
3. Reconnect/rebuild pools hoặc refresh auth theo driver.
4. Xác minh cả reads/writes dùng `v2`.
5. Thu hồi `v1` và kiểm các clients cũ đã biến mất.

**Không kết luận rotate thành công chỉ vì secret-manager version đã thay đổi.**

## 16. Cassandra: roles, authentication và authorization

Cassandra có thể dùng cơ chế authenticator/authorizer tùy cấu hình. Một application role nên có quyền đúng keyspace/table; không cấp superuser cho request service.

~~~text
role: booking_writer
permissions:
  - SELECT on required booking tables
  - MODIFY on required booking tables
not:
  - SUPERUSER
  - ALTER/DROP unrelated keyspaces
~~~

Trong thực tế, câu lệnh/permission model và cơ chế phân phối role thay đổi theo phiên bản và provider. Chỉ khái quát này không thay quy trình cấu hình bảo mật cluster cụ thể.

### Java driver ví dụ

~~~java
import com.datastax.oss.driver.api.core.CqlSession;

public final class CassandraConnectionExample {
    public static CqlSession openSession() {
        String user = System.getenv("CASSANDRA_USER");
        String password =
                System.getenv("CASSANDRA_PASSWORD");
        if (user == null || password == null) {
            throw new IllegalStateException(
                    "Cassandra credentials missing");
        }

        // Endpoint, local datacenter, TLS,
        // timeout và pooling cần cấu hình riêng.
        return CqlSession.builder()
                .withAuthCredentials(user, password)
                .build();
    }
}
~~~

Ví dụ này chỉ minh họa API credential của Java Driver 4, **không phải kết nối production đầy đủ**. TLS và trust validation không được mặc định bỏ qua, và secret lifetime/pool reconnect cần có kế hoạch khi thay password.

## 17. Redis: ACL user và phạm vi command/key

Redis có thể dùng Access Control Lists (ACL) để giới hạn cả nhóm lệnh và key patterns theo user, tùy phiên bản/cấu hình:

~~~text
User: catalog-reader
Purpose: only read designated catalog cache keys
Allowed: appropriate read commands on catalog namespace
Denied: FLUSHALL, ACL SETUSER, CONFIG, arbitrary keys
Transport: TLS when supported/configured
~~~

### Các bẫy

- Một password Redis chung cho mọi services không thể hiện tốt nguyên tắc least privilege.
- ACL cho phép đọc cache không đồng nghĩa dữ liệu cached được phép tiết lộ cho mọi tenant.
- Không đưa Redis password vào command-line arguments/histories hoặc logs; runtime provisioning phải bảo vệ credentials.
- Trong cluster/managed service, ACL, certificate và failover cần được cấu hình theo cách nhà cung cấp hỗ trợ.
- Redis `AUTH` và TLS là hai chức năng khác nhau: AUTH xác thực danh tính, TLS bảo vệ và xác minh kênh truyền.

## 18. DynamoDB: IAM thay cho database username/password

DynamoDB sử dụng **AWS IAM credentials và request signing** thay vì một database password cố định giống cơ chế truyền thống. IAM principal có thể là role gắn với compute workload; request authorization xét policies, resources, actions và conditions.

~~~text
Java service in supported compute environment
    |
    v
Workload/IAM role
    |
    v
Temporary credentials from supported credential provider
    |
    v
Signed DynamoDB API request
    |
    v
IAM authorization + DynamoDB service
~~~

### Quyền tối thiểu minh họa

Một role phục vụ read path có thể chỉ cần `dynamodb:GetItem` và `dynamodb:Query` cho những table/index cần thiết. Không cấp `dynamodb:*` trên mọi resources chỉ để bỏ qua lỗi AccessDenied.

IAM conditions như scope tài khoản, VPC endpoint hoặc leading keys có thể hỗ trợ tenant/data boundaries trong những trường hợp phù hợp, nhưng phải kiểm khả năng của từng API và thiết kế dữ liệu.

## 19. DynamoDB Java SDK v2: default credentials chain

Một Java service nên ưu tiên **credentials provider chain hoặc workload role**, không nhúng access key trong source:

~~~java
import java.time.Duration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.auth.credentials
        .DefaultCredentialsProvider;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model
        .DescribeTableRequest;

public final class DynamoRoleExample {
    public static void main(String[] args) {
        try (DynamoDbClient db =
                DynamoDbClient.builder()
                    .region(Region.AP_SOUTHEAST_1)
                    .credentialsProvider(
                        DefaultCredentialsProvider.create())
                    .build()) {

            db.describeTable(DescribeTableRequest.builder()
                    .tableName("Listings")
                    .build());
        }
    }
}
~~~

### Lưu ý

- Đây là skeleton cho **AWS SDK for Java v2**; cần dependency tương ứng và IAM role có quyền `DescribeTable`. Import `Duration` không bắt buộc và có thể bỏ trong project thực.
- `DefaultCredentialsProvider` hỗ trợ nhiều nguồn credentials. **Không cấu hình static environment access keys trong production** khi workload identity/role sẵn có, vì static keys có thể chiếm ưu tiên trong chain và vô tình che role.
- Trong môi trường container/cloud được quản lý, dùng service account/instance role/federation phù hợp và kiểm trust policy.
- Temporary credentials tự refresh theo provider contract; code không nên cache thủ công access key/secret token ngoài provider.
- Không log AWS secret access key hoặc session token.

## 20. TLS và mTLS: xác thực ở kênh truyền

**TLS** bảo vệ kết nối trước nghe lén/chỉnh sửa và thường xác minh **server identity** qua certificate chain/hostname. **Mutual TLS (mTLS)** còn cho server xác minh certificate/key của client.

~~~text
Service A                        NoSQL / Gateway
    |----- ClientHello ---------------->|
    |<---- Server certificate ----------|
    |----- Client certificate (*) ----->|
    |<---- Handshake result ------------|
    |===== Encrypted channel ===========|
~~~

`(*)` là bước dùng khi mTLS được cấu hình.

### Điều cần bảo vệ

- Trust anchors/CA chain đúng.
- Hostname/SAN validation đúng.
- Private key được bảo vệ, ưu tiên keystore/KMS/HSM phù hợp.
- Certificate expiry có cảnh báo trước.
- Rotation có overlap cả leaf certificate và trust bundle/CA khi cần.
- Revocation có giới hạn: CRL/OCSP, session lifetime và behavior của từng stack phải được xác định.

**Không dùng insecure trust-all certificate manager/disable hostname verification** để giải quyết lỗi cấu hình trong production.

## 21. Xác thực dịch vụ với workload identity

Thay vì secret cứng được copy vào deployment:

~~~text
Orchestrator / cloud control plane
    |
    | Attests workload identity
    v
Short-lived token or credentials
    |
    v
DB, gateway or cloud API
~~~

Workload identity có thể dựa trên instance profile, service account, federated OIDC token, workload certificate hoặc agent cấp token. Mỗi kiến trúc có trust boundary khác nhau.

### Các câu hỏi cần hỏi

1. Ai xác nhận pod/VM/service là principal đó?
2. Token có audience đúng đích không?
3. Trust policy có giới hạn namespace/service account/project không?
4. Quyền có phân tách production/staging không?
5. Token lifetime và refresh làm việc thế nào?
6. Khi workload bị compromise, có cách revoke hoặc khóa role không?
7. Ai có quyền gắn identity này vào workload mới?

**Workload identity giải quyết việc cấp credential, nhưng IAM/DB authorization vẫn phải áp least privilege.**

## 22. Không đặt secrets ở đâu?

| Vị trí | Nguy cơ |
| --- | --- |
| Git repository / config committed | Lộ qua history, forks, artifacts |
| Container image layers | Có thể extract dù file đã bị xóa ở layer sau |
| Public CI logs | Lộ trong output |
| Application exception messages | Stacktrace có thể in URI/token |
| Metrics labels | Phát tán qua monitoring system |
| Tracing spans | Header/token được tự động capture |
| Command-line arguments | Có thể lộ qua process listing/history |
| Shared clipboard/chat/ticket | Copy sang môi trường không có controls |
| Browser/mobile binary | Có thể trích xuất từ client |

Một secret “đã xóa khỏi dòng mới nhất trong Git” vẫn có thể tồn tại trong history/CI build caches. Khi phát hiện lộ secret phải **thu hồi/rotate**, không chỉ xóa chuỗi khỏi mã nguồn.

## 23. Nơi lưu secrets và kiểm soát truy cập

Một secret manager nên hỗ trợ:

- Encryption at rest và phân tách key access.
- IAM/role-based read permissions tối thiểu.
- Versioned secret values.
- Audit logs cho get/update/delete.
- Rotation integration hoặc automation có kiểm soát.
- Availability và disaster recovery phù hợp.
- Policy chống export không cần thiết.

Tuy nhiên **secret manager không tự làm secret an toàn** nếu một service account có quyền đọc tất cả secrets hoặc logs ghi ra plaintext.

### Bootstrap trust

Để đọc secret manager, ứng dụng phải chứng minh nó là service nào. Không giải quyết bằng việc giấu một **root secret dài hạn** trong image. Ưu tiên workload identity, instance roles hoặc cơ chế bootstrap được quản lý bởi nền tảng.

## 24. Biến môi trường, file mounts và SDK

Ba cách cấp credential:

| Cách | Ưu điểm | Rủi ro/chú ý |
| --- | --- | --- |
| Environment variable | Tích hợp dễ | Process dumps, debug logs, khó refresh khi process chạy |
| Runtime-mounted file | Có thể thay file theo volume/agent | Quyền file, reload semantics, accidental backup |
| SDK secret provider | Có thể fetch version/refresh theo policy | Identity bootstrap, cache, network failure |

Không có cách nào miễn nhiễm hoàn toàn với compromise của process. Điều quan trọng là **giới hạn phạm vi quyền, lifetime, audit, memory exposure và hành vi rotation**.

### File permission

Nếu cấp secret qua file, cần restrict owner/mode/namespace, không mount cho container không cần. Một pod gồm sidecar có thể chia sẻ file system/memory/trust boundaries; xem cấu hình thực tế.

## 25. Mô hình vòng đời của credential

~~~text
REQUEST/APPROVAL
      |
      v
GENERATE / ENROLL
      |
      v
PROVISION / DISTRIBUTE
      |
      v
ACTIVE USE
      |
      +------> MONITOR / AUDIT
      |
      v
ROTATE / RENEW
      |
      v
REVOKE / DISABLE
      |
      v
RETIRE / DELETE / AUDIT CLOSEOUT
~~~

Mỗi giai đoạn cần owner, policy, logs và điều kiện rollback/recovery.

| Giai đoạn | Câu hỏi vận hành |
| --- | --- |
| Request | Service nào thực sự cần quyền? Ai phê duyệt? |
| Generate | Secret đủ entropy? Có uniqueness per service? |
| Provision | Phân phối qua kênh tin cậy? |
| Use | Connection/auth hoạt động trong phạm vi quyền? |
| Monitor | Có misuse/login failures/leak detection? |
| Rotate | Có overlap/zero-downtime strategy? |
| Revoke | Old credential và sessions còn tồn tại không? |
| Retire | Secret copies, credentials trong backup/log xử lý sao? |

## 26. Tạo password và key cho service

Service credential cần:

- Sinh từ nguồn ngẫu nhiên mật mã an toàn.
- Đủ độ dài/entropy theo policy.
- Không tái sử dụng qua environments hoặc services.
- Không phụ thuộc tên service hoặc ngày tháng dễ đoán.
- Không tự “tăng số đuôi” từ một secret cũ.

**Password người dùng** có thể đi qua password hashing; **database secret do service sử dụng** thường phải được phục hồi để trình bày cho hệ xác thực, nên cần encryption/secret manager và access controls, không chỉ lưu một hash trong app để có thể login.

Các private keys cần sinh và lưu theo chuẩn khóa tương ứng; bảo vệ export, access, backup và revocation.

## 27. Không dùng chính password cũ làm công cụ rotate

Một cách thủ công thường thấy:

~~~text
NewPassword = OldPassword + "2026!"
~~~

Điều này tạo quan hệ dễ đoán; nếu secret cũ lộ, secret mới cũng có thể bị suy ra.

Thay vào đó tạo credential **độc lập bằng CSPRNG**, phân phối qua secret manager và ghi nhận version/rotation event. Tương tự, không copy password của user admin để dùng cho service.

## 28. Rotation: thiết kế trước khi cần xử lý sự cố

Rotation không chỉ là “đổi một secret trong vault”.

~~~text
New credential generated
        |
        v
DB/IdP accepts new credential
        |
        v
Service obtains new credential
        |
        v
New connections authenticate successfully
        |
        v
Old connections drained / old token expires
        |
        v
Old credential revoked
~~~

Các chủ thể độc lập (database, secrets backend, Java pods, connection pool, brokers, CDC workers) **không cập nhật cùng một thời điểm**. Phải có kế hoạch overlap và rollback phù hợp với mỗi DB/IdP.

## 29. Hai-credential overlap (dual identity)

Khi một hệ không cho một user giữ hai password song song đáng tin, có thể cân nhắc **hai service accounts** cùng bộ quyền tối thiểu:

~~~text
booking-api-a (old)  ← existing connections
booking-api-b (new)  ← newly deployed instances
~~~

Runbook:

1. Tạo `booking-api-b` với role đúng, kiểm quyền.
2. Cấp secret mới qua secret manager.
3. Canary instances kết nối bằng B.
4. Rollout B cho toàn bộ instances/workers.
5. Kiểm không còn new connections từ A; drain old pools.
6. Disable A, xác minh lỗi auth không tăng.
7. Xóa A theo retention/audit policy.

### Giới hạn

- Hai identities làm tăng attack surface **trong thời gian overlap**; giới hạn thời gian rõ.
- Không thể áp y nguyên lên mọi database/protocol.
- Nếu account name có ảnh hưởng authorization, audit hoặc grants khác nhau, phải đồng bộ các chính sách cần thiết.
- Cần chống stale configuration tự đưa A trở lại sau restart.

## 30. Connection pooling và credential rotation

Một Java service có connection pool:

~~~text
Pool created with credential v1
    |
    +--> connection 1 authenticated
    +--> connection 2 authenticated
    +--> connection 3 authenticated

Secret manager now returns v2
    |
    +--> old pool may still use v1 or old authenticated sessions
~~~

**Cập nhật secret manager không tự đổi tất cả connections đã mở**.

### Cần kiểm

- Driver có refresh credential provider không?
- Session/connection có re-auth trên từng request hay chỉ khi mở kết nối?
- Pool có thể rebuild/drain không?
- In-flight transactions được hoàn tất hoặc hủy thế nào?
- Connection max lifetime/idle timeout có làm rollout kéo dài?
- Application có thể recover khi credential expired giữa một retry không?

Với access tokens ngắn hạn, refresh phải xảy ra **trước expiry** với buffer cho clock skew và retry; không chỉ khi đã nhận `401`/auth failure.

## 31. Clock skew và token expiry

Nếu token có `exp` và `nbf`:

~~~text
Issued at t0
Valid from t0
Expires at t0+15 minutes
~~~

Ứng dụng có thể gặp lỗi sớm hoặc muộn nếu clocks lệch. Thiết kế:

- NTP/time synchronization cho nodes.
- Refresh trước expiry theo safety margin.
- Cho phép clock skew **nhỏ và có kiểm soát** ở validator, không mở quá rộng.
- Không dùng token đã expired vì IdP tạm unavailable nếu hợp đồng bảo mật không cho phép.
- Jitter refresh giữa nhiều pods để tránh stampede.
- Metric token refresh failures và time to expiry.

**Đừng “sửa” lỗi clock skew bằng cách bỏ kiểm expiry**.

## 32. Revocation không luôn lập tức

Một password bị disable ở DB có thể chặn **new authentication**, nhưng existing sessions/connections có thể còn hiệu lực theo semantics của DB/driver. Access token JWT tự xác minh có thể tiếp tục hợp lệ tới expiry nếu không có revocation check/denylist/short TTL.

Vì vậy policy phải mô tả:

1. Thu hồi credential tại authority.
2. Cắt/rotate sessions, pools và tokens khi cần.
3. Vô hiệu authorization grants/roles liên quan.
4. Kiểm mọi workers/regions/replicas.
5. Xác nhận old credential không thể tạo kết nối mới.
6. Theo dõi attempts sử dụng credential đã revoke.

### Mức độ khẩn

Một quyền nguy hiểm bị lộ có thể cần khóa ngay và chấp nhận gián đoạn; rotation thông thường có thể ưu tiên rollout ít downtime. Đây là **hai quy trình khác nhau**.

## 33. Thu hồi người dùng và thu hồi dịch vụ khác nhau

Khi nhân viên rời tổ chức:

- Vô hiệu user account, sessions/refresh tokens.
- Thu hồi group membership và privileged access.
- Kiểm shared accounts/API keys mà họ từng có quyền.
- Audit recent access.

Khi một service bị compromise:

- Cô lập workload.
- Rotate/revoke service account/IAM role hoặc key.
- Kiểm các workloads khác dùng chung secret.
- Kiểm tokens/active sessions và suspicious DB operations.
- Restore từ clean image/deployment nếu cần.

**Xóa user khỏi IdP không tự thu hồi mọi static database password mà user từng biết.** Phải quản lý cả secrets đã bị tiếp xúc.

## 34. Break-glass access

Đôi khi cần emergency administrator access khi IdP, automation hoặc networking gặp sự cố. Một break-glass identity phải:

- Được quản lý riêng, có owner rõ.
- Bảo vệ bằng yếu tố mạnh và storage an toàn.
- Chỉ kích hoạt theo incident/approval policy.
- Được audit đặc biệt và review sau sử dụng.
- Có rotation và thử nghiệm khôi phục định kỳ.
- Không dùng làm credential mặc định của app hoặc CI.

Break-glass không phải lý do để duy trì admin password trong file `application.yml` hoặc chat nhóm.

## 35. Audit: chứng minh ai đã làm gì

Một sự kiện audit hữu ích:

~~~json
{
  "timestamp": "2026-11-14T08:00:00Z",
  "principal": "service:booking-api",
  "environment": "production",
  "resource": "booking.reservations",
  "action": "UPDATE",
  "result": "ALLOW",
  "correlationId": "req-801"
}
~~~

**Không chứa password, secret key hoặc raw bearer token**.

### Đủ bối cảnh

- Ai: service principal/role hoặc user principal có xác minh.
- Làm gì: login success/failure, role change, secret read, create/revoke credential.
- Khi nào: timestamp có nguồn tin cậy.
- Ở đâu: environment, cluster, project, source (cân nhắc quyền riêng tư).
- Kết quả: allow/deny và reason category.
- Truy xuất: request/trace correlation, privileged approval ID.

Audit log cũng cần integrity, retention, access control và bảo vệ khỏi tampering; logging mọi payload nhạy cảm làm tăng rủi ro mới.

## 36. Authentication metrics và cảnh báo

| Metric | Câu hỏi |
| --- | --- |
| Auth success/failure rate | Login lỗi bất thường? |
| Distinct principals with failures | Password spraying hay misconfig? |
| Token refresh errors | Credential provider down? |
| Secret fetch failures/latency | Vault/identity dependency có lỗi? |
| Certificate days to expiry | Sắp hết hạn? |
| Key/secret version adoption | Pods đã chuyển sang v2 chưa? |
| Old credential login attempts | Có clients stale hoặc attacker? |
| PermissionDenied rate | Role thiếu hoặc bị abuse? |
| Privileged actions | Có thay roles/credentials ngoài change window? |
| DB connection/auth handshake failure | Rotation gây outage? |

**Không dùng credential value/token làm metric label.** Label chỉ nên chứa low-cardinality fields như service name, environment, error category, credential *version ID không nhạy cảm* khi cần.

## 37. Phân biệt authentication failure và authorization failure

Trong HTTP:

- `401 Unauthorized` thường biểu diễn request chưa được xác thực hợp lệ/thiếu credentials.
- `403 Forbidden` thường biểu diễn principal đã được biết nhưng không được phép truy cập resource.

Trong NoSQL driver, mỗi hệ có mã lỗi/exception riêng cho login, insufficient privileges, TLS handshake hoặc network. Không gộp tất cả thành `DB_DOWN`.

### Ví dụ runbook

~~~text
Authentication failed after deployment
  → Check credential version, authSource, expiry, trust

Permission denied after role change
  → Check intended grants and resource scope

TLS hostname verification failed
  → Check endpoint, certificate SAN/CA and rotation

Connection timeout without auth result
  → Check network/DNS/endpoint/availability
~~~

Không phản hồi ra client rằng username nào có tồn tại hoặc secret nào gần đúng. Error messages bên ngoài nên đủ ít thông tin, còn internal logs chứa **category** để xử lý mà không lộ bí mật.

## 38. Secret rotation plan: bình thường và khẩn cấp

| Mục | Rotation định kỳ | Rotation sau rò rỉ |
| --- | --- | --- |
| Mục tiêu | Đổi credential ít gián đoạn | Cắt quyền attacker nhanh |
| Ưu tiên | Planned overlap, canary | Containment/revocation nhanh |
| Old credential | Thu hồi sau khi migration hoàn tất | Có thể disable ngay |
| Verification | New auth, all instances adopted | Old attempts fail, audit misuse |
| Truyền thông | Change management | Incident response/on-call |
| Phục hồi | Rollback có kiểm soát nếu không compromised | Không tái dùng key đã lộ |

### Không nhầm rollback và phục hồi

Trong incident lộ key, **rollback về credential cũ bị lộ là không an toàn** dù nó giúp dịch vụ chạy lại. Phải có clean replacement hoặc quyền dự phòng được bảo vệ.

## 39. Một rotation runbook theo từng bước

~~~text
PREPARE
  Inventory all users/pods/jobs that use old identity
  Create new least-privileged identity/credential
  Test new identity on staging/canary

DEPLOY
  Publish new secret version via trusted system
  Roll pods and rotate connection pools
  Watch auth errors and DB SLOs

VERIFY
  Check new connections use new identity
  Check reads/writes/CDC jobs still work
  Confirm no old workload remains

REVOKE
  Disable old identity
  Verify old login/new connections fail
  Monitor attempts and session behavior

CLOSE
  Audit change
  Update inventory/rotation schedule
  Record incident or rollout learnings
~~~

Điều kiện phải tùy DB: một số systems có API cập nhật password, một số hỗ trợ hai user identities, cloud role có cơ chế token ngắn hạn. Đừng copy thứ tự bất kỳ nếu sản phẩm chỉ chấp nhận một credential hoạt động tại một thời điểm.

## 40. Credential inventory

Mỗi credential nên có metadata không nhạy cảm:

~~~yaml
credentialId: "booking-api-db-prod"
principal: "service:booking-api"
environment: "production"
system: "booking-nosql"
privilegeProfile: "booking-read-write"
ownerTeam: "booking-platform"
issuer: "managed-secret-service"
createdAt: "illustrative-time"
expiresAt: "policy-defined"
rotationPolicy: "managed, with canary and reconnect"
dependentWorkloads:
  - "booking-api"
  - "reservation-worker"
recoveryRunbook: "internal"
breakGlass: false
~~~

Không đưa **secret value/private key** vào inventory. Inventory hỗ trợ biết nên liên hệ ai, khi nào rotate, workloads nào cần restart và quyền nào sẽ bị ảnh hưởng.

## 41. Bảo vệ CI/CD và automation

Không để pipeline build có static production DB admin key chỉ để chạy tests.

### Thiết kế tốt hơn

- CI xác thực với cloud qua OIDC federation hoặc identity do runner cung cấp.
- Scope role chỉ cho deployment/resource cần thiết.
- Token ngắn hạn gắn với repository/environment/branch/trust policy khi phù hợp.
- Tách quyền build image và quyền truy cập production data.
- Không in variables/secrets ra logs.
- Review third-party actions/plugins và supply-chain exposure.
- Rotate/revoke role trust khi pipeline bị compromise.

**Ai có quyền chỉnh workflow CI có thể gián tiếp có quyền nhận credentials** nếu trust policy quá rộng. Authorization cho CI phải xét đường leo thang này.

## 42. Backup, disaster recovery và secrets

Một database được restore có thể chứa:

- Accounts và role mappings cũ.
- Password hashes/verifiers.
- User metadata/old sessions.
- Encryption key references.

Nhưng secret manager/runtime may have **newer credential versions**. Sau restore, ứng dụng có thể không đăng nhập được hoặc các accounts đã revoke có thể vô tình hồi sinh.

### Kịch bản cần tập dượt

1. DB backup từ trước rotation.
2. Secret manager đang ở credential version mới.
3. Restore database vào một môi trường recovery cô lập.
4. Đồng bộ account/role/credential theo **recovery policy**, không dùng lại secret bị lộ.
5. Kiểm audit và revocation status.
6. Chỉ cho traffic trở lại sau khi kiểm access đúng.

Không đưa plaintext secrets vào backup theo kiểu tiện tay, và không bỏ qua **vòng đời credential** khi diễn tập DR.

## 43. Multi-tenant và tài khoản service chung

Một service thường dùng **một DB principal cho cả API**, trong khi mỗi request thuộc tenant khác:

~~~text
Request A: user U1 of tenant T1
Request B: user U2 of tenant T2

Both use:
  DB principal booking-api
~~~

Do đó DB role cho phép đọc collection không tự đảm bảo T1 không đọc T2.

Các biện pháp:

- Xác thực principal và tenant context tại API.
- Không tin `tenantId` do client gửi nếu chưa kiểm quyền.
- Ràng buộc query/filter theo tenant/ownership.
- Dùng resource-level authorizer, test cross-tenant access.
- Tách databases/collections/roles nếu isolation requirement đáng giá.
- Với cloud IAM conditions hỗ trợ resource partition, kiểm chính xác giới hạn API.

**AuthN đúng nhưng AuthZ sai vẫn là lộ dữ liệu.**

## 44. Đặt secrets trong Java memory

Ngay cả khi secret lấy từ vault, Java process vẫn có thể phải giữ nó tạm thời để xác thực.

### Hạn chế rủi ro

- Không lưu credentials trong static logs, exception messages hay `toString()` của config objects.
- Không bật heap dump tự do với quyền đọc rộng; dumps có thể chứa credential.
- Hạn chế thời gian sống của credential plaintext theo SDK/provider khả dụng.
- Không cache secrets vô hạn hoặc copy sang nhiều layers không cần.
- Ghi nhớ `String` immutable có thể không xóa ngay khỏi heap; dùng `char[]`/secure buffers khi API hỗ trợ nhưng không xem đó là giải pháp tuyệt đối.
- Bảo vệ debug endpoints, Java agents và process diagnostics.

Nếu chính process đã bị attacker điều khiển, secret manager không ngăn attacker dùng quyền mà process đang có; cần isolation, detection, least privilege và incident response.

## 45. Ví dụ Java: token validator ở lớp ứng dụng

Đây là **mã giả dạng interface**, cố ý không tự viết thuật toán chữ ký:

~~~java
record Principal(String subject, String tenantId) {}

interface AccessTokenVerifier {
    // Implementation dùng thư viện OIDC/OAuth/JWT uy tín.
    // Kiểm signature/issuer/audience/expiry/token type.
    Principal verifyAccessToken(String bearerToken);
}

interface BookingAuthorizer {
    // Có thể tra source có thẩm quyền về ownership.
    boolean canRead(Principal principal, String bookingId);
}

final class BookingHandler {
    private final AccessTokenVerifier verifier;
    private final BookingAuthorizer authorizer;

    BookingHandler(AccessTokenVerifier verifier,
                   BookingAuthorizer authorizer) {
        this.verifier = verifier;
        this.authorizer = authorizer;
    }

    void handle(String bearerToken, String bookingId) {
        Principal principal =
                verifier.verifyAccessToken(bearerToken);

        if (!authorizer.canRead(principal, bookingId)) {
            throw new SecurityException("Forbidden");
        }

        // Lúc này service dùng DB credential riêng
        // để đọc booking đã được xác minh quyền.
    }
}
~~~

Không tự viết JWT verification bằng cách decode Base64 rồi tin payload. Cần thư viện/IdP validation đúng chuẩn và tests cho forged/expired/wrong-audience tokens.

## 46. Xác minh rotation qua kết nối mới

Một smoke test hợp lý:

~~~text
New instance identity = booking-api-v2
    |
    v
Open NEW DB connection
    |
    +--> Authentication success
    +--> Expected read allowed
    +--> Expected write allowed when appropriate
    +--> Forbidden admin action remains denied
~~~

Đồng thời:

~~~text
Old identity disabled
    |
    +--> NEW auth attempt must fail
    +--> Existing sessions assessed per DB semantics
~~~

Không chỉ kiểm một ping qua pool đã mở từ nhiều giờ trước; nó có thể thành công dù mọi **new connections** bằng credential cũ đang fail.

## 47. Fault matrix: các lỗi cần thử

| ID | Tình huống | Hành vi kỳ vọng |
| --- | --- | --- |
| F1 | Secret manager tạm unavailable | Retry/backoff có giới hạn, không log secret |
| F2 | Credential expired trước khi refresh | Phát hiện, refresh, không dùng expired token vô hạn |
| F3 | Password đổi khi pool còn connections cũ | New pool dùng v2; old pool được drain |
| F4 | Old account bị revoke | New authentication bằng v1 thất bại |
| F5 | Partial rollout: 20% pods vẫn v1 | Dashboard phát hiện drift trước revoke |
| F6 | Sai MongoDB authSource | Auth failure rõ, không tăng quyền |
| F7 | Redis TLS hostname/CA sai | Handshake fail closed |
| F8 | IAM policy quá hẹp | AccessDenied, chỉ bổ sung quyền có bằng chứng |
| F9 | IAM policy quá rộng | Kiểm privileged actions không cần bị hạn chế |
| F10 | Token có wrong audience | API từ chối |
| F11 | JWT expired hoặc invalid signature | API từ chối |
| F12 | User T1 truy cập booking T2 | 403/denial, audit |
| F13 | Secret bị in ra log | Quarantine/redact logs, revoke và incident handling |
| F14 | Key leak khi CI bị compromise | Disable trust, rotate, audit |
| F15 | DR restore từ trước rotation | Không tự hồi sinh old privileged identity |
| F16 | mTLS certificate hết hạn | Alert trước expiry và phối hợp renewal |

**Fault injection chỉ thực hiện trong môi trường an toàn được phép**, không cố ý làm lộ secrets hoặc khóa tài khoản production ngoài quy trình incident.

## 48. Runbook: auth failures tăng sau deploy

1. Xác nhận phạm vi: service, region, DB cluster, new connections hay existing pooled sessions?
2. Kiểm error category: invalid credentials, permission denied, TLS handshake, network timeout.
3. Xác minh credential version đang được service sử dụng (chỉ metadata, không in secret).
4. Kiểm DB principal còn active, grants đúng, auth database/issuer/audience đúng.
5. Kiểm access tới secret manager, token expiry, clock sync và refresh failures.
6. Nếu vừa rotate, đối chiếu số pods/workers dùng phiên bản cũ.
7. Mở canary connection mới với new credential và expected minimal permissions.
8. Mitigate: roll instances/pools, sửa trust/config hoặc scale identity provider theo runbook.
9. Không “sửa nhanh” bằng cách cấp admin role/disable TLS.
10. Xác minh login success, SLO recovery và old credential revocation.

## 49. Runbook: nghi ngờ credential bị rò rỉ

1. Xác định credential/principal và các systems có thể bị ảnh hưởng.
2. Khoanh vùng: cô lập workload, khóa bất thường, áp security incident process.
3. Thu hồi hoặc rotate credential, ưu tiên cắt quyền attacker.
4. Xác minh **new authentications** của old credential thất bại; xem existing sessions.
5. Đánh giá audit logs, DB queries, exfiltration indicators và privileged changes.
6. Tạo identity/credential sạch, grants tối thiểu, phục hồi ứng dụng.
7. Xử lý bản sao secret ở logs, Git history, CI artifacts, images, caches theo retention/security policy.
8. Đối soát dữ liệu, thông báo sự cố theo nghĩa vụ nội bộ/pháp lý khi cần.
9. Đổi quy trình để tránh lặp lại (secret scanning, IAM, code review, rotation).

**Không paste credential nghi bị lộ vào ticket/chat để “kiểm chứng”**; sử dụng metadata và kênh IR được quản lý.

## 50. Bài tập thực hành

### Bài 1 — Xác thực và phân quyền

User U1 đăng nhập hợp lệ nhưng yêu cầu booking thuộc U2. DB credential của Java service cho phép đọc collection. Có được trả booking không?

**Gợi ý:** AuthN đúng, AuthZ ownership sai.

### Bài 2 — Hai danh tính

Vẽ sơ đồ user OIDC token và service DB credential trong một request Booking API. Chỉ rõ nơi kiểm token, nơi kiểm quyền tenant và nơi database xác thực service.

### Bài 3 — Credential inventory

Thiết kế inventory cho ba workloads: Booking API, CDC worker và Analytics ETL. Vì sao không nên dùng chung admin credential?

### Bài 4 — Password storage

Vì sao plain SHA-256(password) không phù hợp để lưu password người dùng? Nêu salt, Argon2id và rate limiting.

### Bài 5 — MFA

Một user biết password của đồng nghiệp nhưng không có MFA. Hệ bảo vệ được gì? Nếu attacker đánh cắp session token thì MFA có tự ngăn replay không?

### Bài 6 — JWT

Một JWT có chữ ký hợp lệ nhưng `aud` thuộc dịch vụ khác. API Booking có được chấp nhận không?

**Gợi ý:** audience validation.

### Bài 7 — ID token vs access token

Vì sao không tự dùng ID token của client như token quyền truy cập đến mọi NoSQL-backed API?

### Bài 8 — Mongo authSource

MongoDB user tạo trong `admin` nhưng connection authenticate vào `booking`. Lỗi nào có thể xảy ra? Cách xác định đúng auth database?

### Bài 9 — Mongo least privilege

Thiết kế role cho service chỉ đọc listings và role cho service update reservations. Vì sao không dùng `root` cho cả hai?

### Bài 10 — Cassandra

Một Cassandra Java worker dùng superuser để đọc một keyspace. Hãy đề xuất service role với permissions tối thiểu và TLS.

### Bài 11 — Redis ACL

Một catalog reader chỉ được đọc keys namespace riêng. Thiết kế loại command/key patterns cần cho phép và nhóm thao tác phải từ chối.

### Bài 12 — IAM role

DynamoDB service chạy trong cloud có workload role. Vì sao nên dùng SDK credentials provider chain thay vì nhúng access key vào application properties?

### Bài 13 — IAM denied

Một request `Query` bị `AccessDenied`. Có nên cấp `dynamodb:*` cho service để sửa nhanh không? Nêu quy trình phân tích resource/action/conditions.

### Bài 14 — TLS/mTLS

Phân biệt TLS server authentication và mTLS client authentication. Khi hostname certificate không khớp, có nên tắt verification không?

### Bài 15 — Secret manager bootstrap

Ứng dụng cần truy cập vault để lấy DB secret. Nếu phải nhúng root vault password vào image, thiết kế bootstrap còn vấn đề gì?

### Bài 16 — Environment variables

Environment variable có tự trở thành nơi lưu secret an toàn hoàn toàn không? Nêu ít nhất ba con đường lộ.

### Bài 17 — Rotation order

DB password đổi trước khi pods nhận secret mới, new connections bắt đầu fail. Lập runbook không downtime theo khả năng của DB.

### Bài 18 — Dual identity

Thiết kế rotate `booking-api-a` sang `booking-api-b`. Khi nào mới disable account A?

### Bài 19 — Pooled connections

Secret manager đã là v2 nhưng 10% pods còn connections v1. Vì sao kiểm một `ping` không đủ? Cần đo metrics nào?

### Bài 20 — Token expiry

Access token hết hạn trong 30 giây, clock skew 10 giây. Thiết kế refresh buffer và xử lý refresh failure.

### Bài 21 — Revocation

Old password đã disable nhưng một pooled connection vẫn hoạt động. Có thể tuyên bố thu hồi hoàn toàn chưa? Phải xem semantics gì?

### Bài 22 — Incident response

Một secret production bị commit lên Git. Chỉ xóa dòng secret rồi merge PR có đủ không? Nêu các bước revoke, audit và cleanup.

### Bài 23 — Tenant isolation

T1 và T2 dùng chung DB principal của API. Thiết kế tests để bảo đảm một user của T1 không đọc được record của T2.

### Bài 24 — CI federation

Đề xuất cách cấp tạm thời quyền deploy cho CI mà không lưu production static admin key. Trust policy phải giới hạn những gì?

### Bài 25 — Audit logs

Chọn tối thiểu tám fields cho event audit database access/secret rotation mà không ghi plaintext token.

### Bài 26 — False 401/403

Một client có token hợp lệ nhưng không có quyền đọc booking. Phân biệt lỗi authentication và authorization, cùng điều kiện trả status phù hợp.

### Bài 27 — DR restore

Database được restore từ backup trước ngày rotate password. Những nguy cơ về credential/roles/revocation có thể xuất hiện?

### Bài 28 — Fault matrix

Đề xuất các tests cho expired token, vault outage, MongoDB sai authSource, Redis TLS mismatch, IAM AccessDenied và partial credential rollout. Nêu expected behavior/alerts.

### Bài 29 — Java

Thay `MONGODB_URI` trong ví dụ bằng một secret provider do app quản lý. Mô tả điểm cần đảm bảo khi refresh MongoDB client/pool và không log giá trị URI.

### Bài 30 — Thiết kế tổng hợp

Một nền tảng cho thuê có web/mobile users, Booking API dùng MongoDB, Redis cache, DynamoDB cho một số thao tác, Cassandra event history và CDC worker. Hãy:

1. Vẽ user authentication qua IdP/MFA.
2. Phân biệt user principal với workload principals.
3. Thiết kế least privilege cho từng database/service.
4. Chọn TLS/mTLS/IAM/SCRAM/ACL theo từng kết nối.
5. Thiết kế secret inventory và issuance.
6. Đưa ra zero/low-downtime rotation plan với connection pools.
7. Chọn revocation/incident response cho compromised credential.
8. Có audit/metrics và alert trước certificate expiry.
9. Test cross-tenant authorization và failed authentication.
10. Mô tả recovery khi vault/identity provider không khả dụng.

**Gợi ý:** tách danh tính ở mỗi trust boundary, rồi gắn vòng đời cụ thể vào từng credential thay vì đặt mọi password chung trong một file.

## 51. Checklist thiết kế xác thực và vòng đời credential

1. Người dùng cuối và ứng dụng có principals riêng không?
2. IdP token được xác minh signature/issuer/audience/expiry đúng không?
3. Authentication và per-resource authorization có tách rõ không?
4. DB service account có least privilege thay vì admin không?
5. Mỗi service/environment có identity riêng không?
6. Có TLS certificate/hostname verification mà không bật trust-all không?
7. Database-specific authSource, role/IAM policy/ACL đã được xác nhận chưa?
8. Password người dùng được băm bằng password hashing chuyên dụng với salt chưa?
9. MFA/passkey và recovery policy có an toàn không?
10. Secrets có bị hardcode trong Git, image, logs, metrics hoặc tickets không?
11. Secret manager có IAM tối thiểu, audit và bootstrap trust không?
12. Có credential inventory/owner/expiry/rotation policy không?
13. Credential được sinh ngẫu nhiên và không tái dùng không?
14. Có rotation plan bao gồm old/new credentials, rollout và pool reconnect không?
15. Có kiểm new connections khi xác nhận rotate không?
16. Revocation có xét active sessions, token lifetime, driver semantics không?
17. Có theo dõi login failures, permission denied và expired certificates không?
18. Có alert khi pods/workers dùng credential phiên bản cũ không?
19. CI/CD có dùng workload federation/ephemeral identity thay static admin key khi khả thi không?
20. Break-glass account có bảo vệ và audit không?
21. Backup/DR có kiểm tình trạng old accounts và secrets sau restore không?
22. Incident runbook có rotate/revoke/audit/containment không?
23. Các tests có bao phủ tenant isolation và wrong-audience token không?
24. Không có fallback insecure khi IdP/vault bị lỗi chứ?
25. Logs/audit có đủ traceability mà không lộ PII/credentials không?

## 52. Tổng kết

1. **Authentication xác minh danh tính; authorization kiểm quyền; audit ghi nhận hành động.** Không được đồng nhất ba việc.
2. **User identity và service DB identity là hai trust boundaries riêng.** User token không thay database credential một cách tùy tiện.
3. **Password người dùng phải được hash đúng cách**, còn service secrets cần quản lý qua nền tảng có kiểm soát truy cập và audit.
4. **OIDC/MFA/passkeys bảo vệ đăng nhập người dùng**; JWT/access token phải được xác minh đầy đủ, không tin payload chỉ vì decode được.
5. **NoSQL có nhiều cơ chế xác thực:** MongoDB SCRAM/roles, Cassandra roles, Redis ACL, DynamoDB IAM, TLS/mTLS và workload identity theo sản phẩm.
6. **Least privilege và per-service identity giảm blast radius** khi credential bị lộ.
7. **Secret manager không tự giải quyết mọi rủi ro.** Bootstrap identity, logs, process memory, CI, backups và role policies đều cần bảo vệ.
8. **Credential rotation là một workflow phân tán** gồm cấp phát, rollout, refresh pools, xác minh new connections và thu hồi old identity.
9. **Revocation không phải lúc nào tức thì** với sessions/tokens/pooled connections; phải kiểm theo DB/driver/IdP contract.
10. **Audit, fault injection, break-glass và incident response** biến thiết kế credential thành năng lực vận hành thay vì chỉ là một cấu hình.

**Nguyên tắc thực hành:** với mỗi kết nối NoSQL, hãy trả lời được **“principal nào đang xác thực?”, “nó thực sự cần quyền gì?”, “credential đến từ đâu?”, “làm sao rotate mà không ngắt hệ?”, và “khi lộ credential, làm sao thu hồi và chứng minh quyền cũ đã hết hiệu lực?”**. Nếu năm câu hỏi được giải quyết bằng cấu hình, quy trình và bài kiểm thử cụ thể, hệ thống mới có một mô hình xác thực và quản lý vòng đời thông tin đăng nhập đáng tin cậy.
