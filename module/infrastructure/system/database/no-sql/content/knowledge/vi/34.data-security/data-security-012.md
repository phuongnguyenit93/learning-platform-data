# Quản lý bí mật, luân chuyển khóa và tránh ghi thông tin xác thực vào log

## 1. Một ứng dụng NoSQL có thể làm lộ dữ liệu dù database không bị tấn công trực tiếp

Một service Java kết nối MongoDB/Redis qua TLS, database bật xác thực và các quyền truy cập đều được cấu hình đúng. Khi gặp lỗi connection timeout, developer thêm một dòng:

~~~java
logger.error("Cannot connect with config {}", databaseConfig, error);
~~~

Nhưng toString() của databaseConfig lại chứa URI:

~~~text
mongodb+srv://app-reader:<SECRET>@db.example.invalid/orders?retryWrites=true
~~~

Log được chuyển tới hệ quan sát tập trung, được lưu lâu hơn vòng đời mật khẩu và nhiều tài khoản vận hành có quyền đọc. Một sự cố kết nối ngắn đã tạo ra **một bản sao thông tin xác thực** ở nơi không được thiết kế làm kho bí mật.

Một tháng sau, team đổi mật khẩu MongoDB nhưng không xử lý connection pool và không kiểm soát thời điểm hết hạn credential cũ. Một số instances dùng mật khẩu mới, số còn lại vẫn giữ kết nối hoặc cố mở kết nối bằng mật khẩu cũ. Hệ xuất hiện authentication failures và tăng retries.

Ví dụ này có ba bài học liên quan:

1. **Bí mật phải được quản lý qua toàn bộ vòng đời**, không chỉ tránh commit mật khẩu vào Git.
2. **Luân chuyển credential/cryptographic key là một quy trình phối hợp**, không phải chỉ tạo một chuỗi mới.
3. **Log, trace, metric và công cụ chẩn đoán là các điểm rò rỉ thực tế** nếu dữ liệu nhạy cảm không được kiểm soát tại nguồn phát sinh.

Bài thuộc module **Database No SQL**, chương **Bảo mật dữ liệu**, tập trung vào ứng dụng Java làm việc với MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis và các dịch vụ quản lý khóa/bí mật.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt password, API token, access key, private key, encryption key, KMS key, DEK/KEK và key identifier.
2. Dùng identity theo workload, least privilege, secret manager và runtime injection thay vì hardcode bí mật.
3. Thiết kế zero-downtime credential rotation có kiểm tra và phương án rollback.
4. Phân biệt **đổi thông tin xác thực** với **luân chuyển khóa mã hóa dữ liệu**.
5. Hiểu envelope encryption, data key version, rewrap, re-encrypt và phân cấp quyền KMS.
6. Tránh làm lộ secrets qua MongoDB URI, Cassandra config, Redis URL, SDK exceptions, Java toString(), HTTP headers, tracing, profiling và backup.
7. Thiết lập safe logging bằng allowlist, redaction và không gắn dữ liệu nhạy cảm vào metric labels.
8. Xây bộ kiểm thử chống rò rỉ và runbook ứng phó khi credential/key bị lộ.

## 2. Secrets không chỉ là mật khẩu

| Loại | Ví dụ | Nếu bị lộ |
|---|---|---|
| Database password | MongoDB SCRAM user password | Có thể cho phép truy cập theo quyền user |
| Access token | Short-lived token đến dịch vụ dữ liệu | Có thể bị replay đến khi hết hạn/thu hồi |
| Cloud access key | Static cloud credential | Có thể truy cập tài nguyên ngoài NoSQL |
| Private key | Client mTLS private key | Có thể giả danh workload nếu thiếu các kiểm soát khác |
| KMS key material | Khóa chủ do KMS/HSM quản lý | Đe dọa tính bí mật của dữ liệu được bảo vệ |
| DEK | Data Encryption Key | Có thể giải mã dữ liệu do DEK bảo vệ |
| KEK | Key Encryption Key | Có thể unwrap một hoặc nhiều DEK |
| Secret manager credential | Token đọc secret vault | Có thể lấy các secrets theo policy |
| Redis ACL password | Credential của ACL user | Có thể đọc/ghi/xóa dữ liệu theo permissions |
| Client certificate + private key | Xác thực tới Cassandra/mTLS proxy | Có thể giả danh service |
| Signing key | Khóa ký request/JWT | Có thể tạo chữ ký giả mạo |
| Backup encryption password/key | Khóa mã hóa snapshot | Có thể giải mã bản sao dữ liệu |

### 2.1. Không phải mọi giá trị trong cấu hình đều là secret

Hostname, port, database name, cluster identifier hoặc key ID có thể không phải secret, nhưng vẫn có giá trị nhạy cảm về topology. Phải phân loại theo threat model và chính sách công ty.

### 2.2. Secret khác identifier

~~~text
keyId = "orders-prod-key-v3"       // Identifier, không phải raw key bytes.
keyMaterial = [opaque bytes]       // Bí mật tuyệt đối.
~~~

Không dùng key ID công khai như thể nó tự mã hóa được dữ liệu. Ngược lại, không in raw key chỉ vì muốn chẩn đoán “đang dùng phiên bản nào”.

### 2.3. Encoding không phải encryption

Base64, hex hoặc URL-encoding chỉ đổi cách biểu diễn. Một password được base64-encode vẫn là password có thể khôi phục dễ dàng và vẫn phải được bảo vệ.

### 2.4. Hash của secret cũng cần thận trọng

Không log SHA-256 của password thấp entropy để “đối chiếu phiên bản”; attacker có thể đoán offline. Nếu cần định danh phiên bản, dùng **secret version ID** do manager cấp, không tạo fingerprint của raw credential trừ khi threat model và policy phê duyệt.

## 3. Phân biệt credential rotation và encryption key rotation

Hai thao tác nghe giống nhau nhưng khác hệ quả.

### 3.1. Credential rotation

Đổi password/token/private key dùng để **xác thực** ứng dụng với database hoặc API:

~~~text
app credential v1 -> app credential v2
~~~

Mục tiêu: hạn chế thời gian secret bị lộ còn dùng được và bảo đảm quyền xác thực liên tục.

### 3.2. Encryption key rotation

Đổi khóa dùng để **bảo vệ dữ liệu**, chẳng hạn:

~~~text
DEK v1 encrypts old records
DEK v2 encrypts new records
~~~

Mục tiêu: quản trị vòng đời khóa, giảm phạm vi ảnh hưởng của compromise, đáp ứng chính sách cryptography và đôi khi chuyển dữ liệu cũ sang khóa mới.

### 3.3. Rotation không tự làm ciphertext cũ dùng khóa mới

Khi đổi key dùng cho writes tương lai, dữ liệu cũ thường vẫn cần khóa cũ để giải mã. Nếu muốn thay bảo vệ cho dữ liệu cũ, cần **rewrap DEK hoặc re-encrypt dữ liệu** tùy cấu trúc mã hóa.

### 3.4. Token expiration khác chủ động revoke

Một token có thời hạn 10 phút sẽ tự hết hạn, nhưng nếu bị lộ trong 10 phút đó vẫn có thể bị lợi dụng. Một số hệ cho phép revoke sớm, một số token đã phát không thể lập tức thu hồi nếu verifier không tra revocation.

### 3.5. Quy tắc vận hành

Trước mọi rotation, trả lời:

- Secret/key đang được dùng để làm gì?
- Ai là consumer?
- Có bao nhiêu active instances và jobs?
- Có hỗ trợ đồng thời old/new không?
- Làm sao kiểm tra cutover?
- Khi nào được revoke hoặc hủy vật liệu cũ?

## 4. Threat model cho một ứng dụng Java kết nối NoSQL

~~~mermaid
flowchart LR
    A["Java service"] --> B["Secret manager / workload identity"]
    A --> C["MongoDB / DynamoDB / Cassandra / Redis"]
    A --> D["Application logs / traces / metrics"]
    C --> E["Backups / replicas / snapshots"]
    B --> F["KMS / HSM"]
    D --> G["Log storage / alerting"]
    H["CI/CD + IaC"] --> A
    H --> B
~~~

Mỗi mũi tên là một boundary cần biết: ai có quyền, dữ liệu có được mã hóa trên đường truyền không, bí mật có bị copy sang nơi khác không, và thời hạn tồn tại là bao lâu.

### 4.1. Những nơi secret có thể lộ

- Source repository và lịch sử Git.
- File cấu hình local, image layer, CI artifact.
- Environment variables/command-line args/process inspection.
- Heap dump, core dump, crash report.
- Application logs, test logs và debug traces.
- Driver connection URI, exception messages.
- HTTP headers, tracing baggage, message headers.
- Database audit/profiler/query logs.
- Redis MONITOR hoặc proxy/network packet capture.
- Backup/snapshot của nơi lưu credential.

### 4.2. Không có “một lần cấu hình là xong”

Secrets có thể đi qua nhiều hệ thống thứ cấp. Một secret được bảo vệ tốt trong secret manager vẫn có thể bị Java application in ra log hoặc đưa vào response body.

### 4.3. Authentication và authorization là hai việc

Credential hợp lệ xác định workload đang là ai. Database role/IAM/ACL quyết định workload được thực hiện thao tác nào. Một superuser password trong secret manager vẫn là rủi ro rất lớn nếu ứng dụng chỉ cần GET một collection.

## 5. Nguyên tắc quản lý bí mật

### 5.1. Không hardcode

Sai:

~~~java
String password = "hardcoded-password-do-not-use";
~~~

Chuỗi này chỉ là ví dụ minh họa lỗi, không phải credential thực. Trong code thật, không commit password, token, private key hoặc full URI có username/password vào repository.

### 5.2. Không nhúng vào Docker image

Một Dockerfile copy file credentials.json vào image có thể khiến secret nằm trong layers/registry ngay cả khi file bị xóa ở layer sau. Runtime secret mount/identity thường phù hợp hơn.

### 5.3. Dùng nguồn cấp secrets được kiểm soát

Ví dụ:

- Secret manager chuyên dụng.
- Cloud-managed identity và IAM role.
- Kubernetes Secrets được bảo vệ bằng encryption-at-rest và RBAC phù hợp, kết hợp external secret operator khi cần.
- Hệ thống quản lý chứng chỉ/mTLS.

Kubernetes Secret mặc định được encode base64 trong YAML, không có nghĩa tự an toàn nếu quyền đọc etcd/API không được kiểm soát.

### 5.4. Least privilege

Một service đọc catalog không cần quyền drop database, grant roles, tạo user hay liệt kê mọi secret của tổ chức.

### 5.5. Phân tách môi trường

Dev, staging, production nên dùng credentials, roles và key namespaces riêng. Không dùng production credential để chạy integration tests hoặc chia sẻ qua máy cá nhân.

### 5.6. Mục tiêu là giảm bản sao và thời gian sống

Không thể loại bỏ hoàn toàn secret khỏi memory của tiến trình phải sử dụng nó. Nhưng có thể hạn chế số nơi sao chép, thời gian giữ, đặc quyền và khả năng quan sát từ tài khoản khác.

## 6. Secret manager giải quyết những gì?

Một secret manager thường hỗ trợ:

- Lưu secret phiên bản hóa.
- IAM/policy để cấp quyền đọc/ghi/rotate.
- Audit ai đã truy cập secret nào.
- Encryption at rest và TLS transport.
- Rotation workflows và revoke.
- Dynamic credentials với lease khi hỗ trợ.
- Integration với workload identity.

### 6.1. Secret manager không tự tránh rò log

Sau khi Java lấy password vào memory, nếu code log password thì hệ thống quản lý bí mật không thể ngăn log đã chứa nó.

### 6.2. Secret manager không thay database ACL

Một ứng dụng có quyền đọc secret superuser vẫn có khả năng gây thiệt hại lớn khi secret bị lấy. Cần giới hạn cả quyền **đọc secret** và **quyền của credential bên trong**.

### 6.3. Phiên bản secrets

~~~text
orders/mongodb/reader:
  version 17 = old
  version 18 = candidate
  version 18 = active after cutover
~~~

Nhãn active/candidate/versioning là ví dụ khái niệm; mỗi secret manager có cách biểu diễn riêng. Không tự coi thứ tự số version luôn tương ứng lifecycle state.

### 6.4. Khi secret manager unavailable

Ứng dụng phải có chính sách:

- Có được tiếp tục dùng credential đã lấy/còn hiệu lực không?
- Có thể khởi động instance mới không?
- Cache secret ở memory trong bao lâu?
- Có được dùng stale credential khi rotation/revoke đã diễn ra không?
- Khi nào fail closed?

Không fallback sang credential hardcode trong image để “giữ uptime”.

## 7. Ưu tiên identity theo workload thay vì khóa tĩnh dài hạn

### 7.1. Workload identity

Ứng dụng chạy trên compute có danh tính được chứng thực qua nền tảng, rồi lấy short-lived credentials hoặc gọi secret manager qua IAM.

~~~text
Java service identity
    -> auth to cloud/secret manager
    -> scoped short-lived credential or direct signed request
    -> database/service
~~~

### 7.2. Lợi ích

- Ít static keys phải phân phát.
- Có audit gắn với service identity.
- Quyền cấp theo workload/namespace.
- Credential tạm thời tự được làm mới bởi supported SDK/provider.

### 7.3. Không phải mọi NoSQL hỗ trợ cùng một phương thức

DynamoDB có thể dùng AWS IAM và request signing. MongoDB, Redis, Cassandra có mô hình xác thực, version và plugin riêng. Không giả định một cloud role tự động thay username/password cho mọi database.

### 7.4. Scope tối thiểu

Một service chỉ cần đọc một DynamoDB table có thể được cấp quyền GetItem/Query trên tài nguyên cần thiết thay vì quyền wildcard toàn tài khoản.

### 7.5. Tách workload runtime khỏi rotation operator

Ứng dụng thường chỉ cần lấy credential đang active, không cần quyền tạo/revoke mọi credentials. Rotation controller có quyền nâng cao trong một scope giới hạn và phải được audit riêng.

## 8. Java: lấy cấu hình mà không hardcode secret

Một ví dụ interface tách secret khỏi code nghiệp vụ:

~~~java
public interface DatabaseCredentialProvider {
    DatabaseCredential current();
}

public record DatabaseCredential(
        String username,
        char[] password,
        String versionId
) {}
~~~

### 8.1. Interface không tự bảo đảm an toàn

Provider vẫn phải xác thực tới secret manager an toàn, kiểm tra quyền, dùng TLS, định nghĩa refresh và xử lý unavailable. Kiểu char[] giảm khả năng giữ password trong immutable String ở một số đường code, nhưng driver có thể buộc chuyển sang String; không thể đảm bảo mọi copy được xóa.

### 8.2. Không tạo toString có password

Java record mặc định có toString() gồm các components; dù char[] thường không render các phần tử như một chuỗi plaintext theo mọi đường, **không dựa vào hành vi này để bảo vệ bí mật**. Tránh log object credential và ưu tiên class với toString được kiểm soát.

~~~java
public final class SecretValue {
    private final char[] value;

    public SecretValue(char[] value) {
        this.value = value.clone();
    }

    public char[] copyForUse() {
        return value.clone();
    }

    @Override
    public String toString() {
        return "[REDACTED]";
    }
}
~~~

### 8.3. Không xem toString redaction là lớp bảo vệ duy nhất

Secret vẫn có thể lộ qua exception message, concatenation, debugger, serialization hoặc explicit value getter. Cần giới hạn đường dùng secret và áp allowlist logging.

### 8.4. Không dùng một static global secret vô hạn

Nếu credential rotation yêu cầu refresh, thiết kế lifecycle cho provider và connection pool. Một final static String đọc từ startup có thể buộc restart/cutover đồng loạt không cần thiết.

## 9. DynamoDB Java SDK: tránh static access key khi có role

Trên AWS, một service Java có thể dùng **default credentials provider chain** của SDK, để lấy credentials từ môi trường thực thi được cấp quyền thay vì tạo AWS access key dài hạn và commit vào properties.

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

try (DynamoDbClient dynamo = DynamoDbClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .credentialsProvider(DefaultCredentialsProvider.create())
        .build()) {
    // Chỉ gọi các thao tác được IAM cho phép.
}
~~~

### 9.1. Credentials chain không tự giới hạn quyền

Nếu môi trường đang expose static environment credentials có quyền rộng, default provider chain vẫn có thể chọn chúng. Phải kiểm soát **nguồn identity và IAM policy**, không chỉ dùng một class có tên Default.

### 9.2. Chạy trên nền tảng có workload identity

Ví dụ IAM role trên EC2, ECS task role, EKS Pod Identity/IRSA hoặc runtime được hỗ trợ. Cấu hình chi tiết phụ thuộc nền tảng và SDK version.

### 9.3. Cho phép SDK refresh token

Các temporary credentials hết hạn cần được provider làm mới. Không lấy access key/session token rồi giữ trong một String bất biến lâu hơn thời hạn hiệu lực.

### 9.4. Không log request signing data

Authorization header của AWS Signature Version 4 và session token là dữ liệu cần bảo vệ. Không bật raw HTTP wire logging ở production mà không có cơ chế lọc và quyền truy cập phù hợp.

### 9.5. IAM cho từng table/action

Một service chỉ đọc item có thể được cấp các actions cần thiết trên table/index tương ứng, cân nhắc IAM conditions theo thiết kế. Không dùng quyền tạo/xóa table hoặc admin cho đường API đọc thông thường.

### 9.6. Khi cần truy cập secret manager

Workload role có thể được phép GetSecretValue cho **một ARN cần thiết**, không phải mọi secret. Secret resource policy/KMS decrypt permissions và access audit cũng cần xem xét.

## 10. MongoDB: không đưa username/password vào log cùng URI

MongoDB connection string có thể chứa:

~~~text
mongodb+srv://<USERNAME>:<PASSWORD>@cluster.example.invalid/orders
~~~

### 10.1. URI là một secret-bearing value

Ngay cả khi password được percent-encode, chuỗi vẫn có thể khôi phục. Không log URI nguyên vẹn, không đặt làm metric label và không copy vào exception response.

### 10.2. Tách endpoint an toàn khỏi credential

Một cấu hình logic:

~~~text
database.hosts      = cluster.example.invalid
database.name       = orders
credential.version  = 18
credential.source   = secret-manager/orders/mongo-reader
~~~

Chỉ nên log các trường không chứa secret và có thẩm quyền chia sẻ nội bộ; không log giá trị password.

### 10.3. MongoDB Java Driver credential object

~~~java
import com.mongodb.MongoCredential;

char[] password = secretProvider.current().copyPassword();
try {
    MongoCredential credential = MongoCredential.createScramSha256Credential(
            "orders-reader",
            "admin",
            password
    );
    // Supply credential to MongoClientSettings.
} finally {
    java.util.Arrays.fill(password, '\0');
}
~~~

Đây là ví dụ tư duy API: phương thức copyPassword() do ứng dụng định nghĩa, không phải JDK hay driver chuẩn. Xóa bản sao char[] giúp giảm thời gian giữ **bản sao do application sở hữu**, không có nghĩa toàn bộ bản sao nội bộ driver đã bị xóa. Authentication source là ví dụ, không phải mọi MongoDB deployment đều dùng admin.

### 10.4. Role theo mục đích

Tách user:

~~~text
orders-api-reader   -> read-only theo collection cần thiết
orders-api-writer   -> read/write giới hạn
orders-maintenance  -> backup/index/admin operations riêng
~~~

Không chia sẻ một superuser giữa tất cả services.

### 10.5. Thận trọng khi dùng MongoClientSettings

MongoClient chứa connection pools và credential liên quan đến lifecycle. Khi đổi credential, tạo client/pool mới và chuyển traffic an toàn có thể cần thiết; driver không mặc nhiên cập nhật authentication của mọi connection chỉ vì secret manager đã đổi version.

### 10.6. Profiler và command monitoring

Một read/write command có thể chứa filters và update documents có dữ liệu người dùng. Tránh bật command logging với full BSON ở mức DEBUG; sử dụng operation class, elapsed time, result code và request metadata an toàn.

## 11. Redis: ACL users, TLS và credential lifecycle

Redis hiện đại có ACL và có thể dùng username/password. Có thể tách:

~~~text
cache-reader  -> GET/MGET và những key patterns được phép
cache-writer  -> các lệnh ghi trong phạm vi cache
ops-rotate    -> quyền quản trị ACL theo policy riêng
~~~

### 11.1. Một password chung cho mọi service gây blast radius lớn

Nếu nhiều services dùng cùng Redis password với quyền rộng, một secret bị lộ có thể ảnh hưởng mọi tenants/keys. ACL user riêng theo workload và key patterns giúp giới hạn phạm vi.

### 11.2. Bật TLS phù hợp

Một secret được lưu trong manager nhưng truyền qua plaintext Redis connection vẫn có thể bị lộ trên network. TLS server verification, trust store, hostname validation và các cơ chế xác thực phù hợp rất quan trọng.

### 11.3. Redis URL có thể chứa password

~~~text
rediss://<USERNAME>:<PASSWORD>@cache.example.invalid:6380
~~~

URL này không được đưa nguyên văn vào logs. Khi cần mô tả endpoint, log host/port/TLS mode đã được kiểm soát.

### 11.4. Không dùng MONITOR để chẩn đoán tùy tiện

Redis MONITOR có thể phơi bày nội dung commands và các giá trị nhạy cảm, gây thêm overhead. Sử dụng trong môi trường/quyền phù hợp, không ghi output ra log tập trung không được lọc.

### 11.5. Rotation Redis ACL

Nếu deployment hỗ trợ nhiều credentials/passwords cho cùng ACL user hoặc hai users có cùng policy tạm thời, có thể:

1. Thêm credential/user mới.
2. Chuyển client pools.
3. Xác nhận connects và permissions.
4. Chặn credential/user cũ.

Chi tiết commands, giới hạn mật khẩu và khả năng cập nhật động phụ thuộc Redis/version/managed provider.

### 11.6. Không confuse expiration của cache keys với credential

Key TTL cho dữ liệu cache không điều khiển lifecycle của Redis ACL password. Rotation phải dựa trên secret manager và ACL/service configuration.

## 12. Cassandra/ScyllaDB: username/password và mTLS

Java driver có thể dùng authentication provider và TLS configuration tương ứng hệ triển khai.

~~~java
// Pseudocode architecture:
Credential c = credentialProvider.fetch("cassandra/orders-writer");
CqlSession session = buildCqlSession(
        hosts,
        localDatacenter,
        tlsConfiguration,
        c.username(),
        c.password()
);
~~~

### 12.1. Không nhúng password vào driver config file được commit

Một config .conf hoặc application.yaml có cleartext password trong Git vẫn là secret leak. Nếu config placeholder đọc runtime secret thì phải bảo đảm output của config binding/debug không log resolved value.

### 12.2. Quyền theo keyspace/table

Ứng dụng ghi orders_by_id thường không cần quyền ALTER KEYSPACE hoặc CREATE ROLE. Thiết kế database roles/GRANT theo operations cần thiết.

### 12.3. TLS có hai phần

- Xác minh server (client không bị dẫn tới máy giả).
- Client authentication nếu môi trường dùng mTLS.

Không “sửa lỗi chứng chỉ” bằng cách vô hiệu hóa certificate/hostname verification trong production.

### 12.4. Rotation certificate

Đổi private key/certificate cần kiểm tra chain, SAN, trust anchors, thời hạn hiệu lực và phân phối tới nodes/client. Việc đổi server certificate khác credential password của ứng dụng.

### 12.5. Session lifecycle

Một CqlSession có connections/pools; khi đổi identity/credential, thiết kế create-and-switch sessions theo supported driver lifecycle thay vì giả định session cũ tự dùng password mới.

## 13. Connection pool và rotation không zero downtime tự động

Các NoSQL drivers thường quản lý connection pools. Một service có thể có 100 connections đã xác thực bằng credential cũ và nhiều requests đồng thời.

### 13.1. Quy tắc cơ bản

~~~text
old pool: authenticated using credential v17
new pool: authenticated using credential v18
~~~

Chuyển traffic sang pool mới khi đã xác minh nó khỏe; chỉ đóng pool cũ sau khi in-flight requests hoàn tất hoặc hết graceful deadline theo policy.

### 13.2. Không cắt credential cũ quá sớm

Nếu revoke v17 trước khi tất cả instances nhận v18, reconnects từ instances cũ sẽ lỗi. Graceful overlap cần có kiểm soát thời gian và audit.

### 13.3. Overlap cũng có rủi ro

Trong thời gian v17 và v18 cùng hợp lệ, blast radius tạm thời lớn hơn. Nếu rotation vì bị lộ nghiêm trọng, có thể phải ưu tiên revoke ngay và chấp nhận availability impact.

### 13.4. Đừng đo success chỉ bằng existing connections

Một pool có connections cũ vẫn sống có thể tiếp tục query thành công, trong khi **new connection establishment** với credential mới lỗi. Canary nên thực hiện cả fresh connection và các operations đại diện.

### 13.5. Check trước và sau cutover

Theo dõi authentication failures, pool connection age, connection creation rate, database rejected auth, app p99, error rate, secret version distribution và retry attempts.

## 14. Quy trình rotation credential không gián đoạn

Một plan **expand → migrate → contract**:

~~~mermaid
sequenceDiagram
    participant R as Rotation Controller
    participant SM as Secret Manager
    participant DB as NoSQL
    participant APP as Java Service
    R->>DB: Create candidate credential v18
    R->>SM: Store candidate v18
    R->>APP: Notify version available
    APP->>SM: Fetch v18
    APP->>DB: Establish new authenticated pool
    DB-->>APP: Authentication works
    APP->>APP: Switch requests to new pool
    APP-->>R: Version v18 healthy
    R->>DB: Revoke old v17 after safety criteria
    R->>SM: Mark old version retired
~~~

### 14.1. Chuẩn bị

- Inventory mọi consumers: APIs, jobs, migration tools, support scripts, serverless functions.
- Xác định quyền DB cần giữ nguyên hoặc giảm.
- Kiểm tra hỗ trợ nhiều credentials/identities đồng thời.
- Xác định thời gian overlap và failure strategy.

### 14.2. Tạo candidate credential

Credential mới được sinh bằng cơ chế an toàn theo manager/provider, không tạo thủ công qua chat/email hoặc log console. Lưu với metadata version/owner nhưng không in raw value.

### 14.3. Thử fresh auth

Một canary instance lấy v18, mở kết nối mới, thực hiện một thao tác tối thiểu được phép và xác nhận deny đối với quyền không cần.

### 14.4. Phân phối và chuyển traffic

Thông báo secret version thay đổi hoặc refresh theo poll/lease. Deploy/rollout theo waves, không assume mọi pod tự refresh chỉ vì mount hay env đã thay.

### 14.5. Theo dõi

Theo dõi phần trăm instances dùng v18 theo inventory, connection creation success, auth error, DB operations và business SLO.

### 14.6. Thu hồi old

Chỉ revoke v17 khi xác minh không còn consumers cần nó và overlap horizon đã đủ. Với suspected compromise, rút ngắn quá trình theo incident severity và chấp nhận controlled downtime nếu cần.

### 14.7. Sau rotation

Cập nhật audit log/rotation record, kiểm tra secret đã xóa khỏi caches/CI variables không cần thiết và xác nhận không có fallback dùng v17.

## 15. Rotation có deadline và rollback, không phải “đổi rồi xem sao”

### 15.1. Một state machine minh họa

~~~text
PLANNED
  -> CANDIDATE_CREATED
  -> CANDIDATE_VALIDATED
  -> ROLLING_OUT
  -> NEW_ACTIVE
  -> OLD_REVOKED
  -> COMPLETE
~~~

Trạng thái lỗi có thể đi tới ROLLBACK_REQUIRED hoặc EMERGENCY_REVOKE. Không dùng rollback để khôi phục credential đã bị lộ nghiêm trọng một cách vô điều kiện.

### 15.2. Rollback khi candidate không hoạt động

Nếu v18 không thể auth nhưng v17 chưa bị revoke, traffic vẫn trên v17; sửa candidate và retry. Không đẩy v18 thành active khi canary chưa đạt.

### 15.3. Sau old revoke, rollback khác

Không thể luôn “quay lại v17” vì credential đó đã bị thu hồi hoặc không còn an toàn. Có thể cần tạo v19 và tiến hành emergency forward rotation.

### 15.4. Quy trình khi một instance offline

Một batch worker tắt trong lúc rotate sẽ khởi động sau vài ngày. Nếu nó giữ mật khẩu v17 trong file env, sẽ thất bại. Phải để startup fetch version active qua manager, hoặc kiểm soát cấu hình/rollout của offline jobs.

### 15.5. Cảnh báo secret stale

Theo dõi instances báo credentialVersion đã retirement hoặc certificate expiration approaching. Không lưu raw credential trong metric để phân biệt versions.

## 16. Dữ liệu mã hóa: KEK và DEK là gì?

Mã hóa ứng dụng có thể dùng **envelope encryption**:

~~~text
Plaintext data
   |
   | encrypt using DEK (Data Encryption Key)
   v
Ciphertext + nonce + auth tag

DEK
   |
   | wrap using KEK (Key Encryption Key, often in KMS/HSM)
   v
Encrypted DEK
~~~

### 16.1. DEK

Khóa dùng để mã hóa một record, một nhóm records hoặc một phạm vi cụ thể theo crypto design. Cần chọn scope phù hợp với hiệu năng và blast radius.

### 16.2. KEK

Khóa dùng để bảo vệ DEK, thường được quản lý/định quyền qua KMS/HSM. Application có thể cần quyền Encrypt/Decrypt/GenerateDataKey thay vì quyền export raw KEK.

### 16.3. Tách storage và key authority

NoSQL giữ ciphertext, encrypted DEK và metadata. KMS quản lý KEK và access audit. Một kẻ chỉ có read access tới NoSQL không nên tự giải mã được khi không có quyền với key authority.

### 16.4. Mã hóa không thay authorization

Một app có quyền decrypt mọi tenant records vẫn có thể lộ dữ liệu khi bị compromise. Cần tenant isolation, rate limiting, per-service permissions và audit.

## 17. Envelope encryption cho NoSQL document

Ví dụ một order chứa trường nhạy cảm được mã hóa ở application layer:

~~~json
{
  "tenantId": "T17",
  "orderId": "O101",
  "contactEncrypted": {
    "algorithm": "AES-256-GCM",
    "keyVersion": "dek-2026-11-b",
    "wrappedDek": "<BASE64_ENCRYPTED_DEK>",
    "nonce": "<BASE64_NONCE>",
    "ciphertext": "<BASE64_CIPHERTEXT_AND_TAG>"
  }
}
~~~

Đây là representation minh họa; raw ciphertext/nonce/wrappedDek có thể là bytes/Binary trong database thay vì Base64 String. **Không có khóa thật trong ví dụ.**

### 17.1. Metadata phải đủ để giải mã

Cần biết algorithm, phiên bản/scope khóa, nonce/IV, encrypted DEK reference, authentication tag và encoding. Khi migrate schema phải giữ khả năng đọc records cũ.

### 17.2. Không bao giờ tái sử dụng nonce sai cách

Với AES-GCM, tái sử dụng cùng nonce với cùng khóa có thể phá nghiêm trọng tính an toàn. Không tự tạo nonce bằng timestamp giây, order number hoặc static constant. Dùng thiết kế nonce generation được review và thư viện/SDK mã hóa được hỗ trợ.

### 17.3. Associated Data (AAD)

Có thể ràng buộc ciphertext với:

~~~text
tenantId
orderId
fieldName
schemaVersion
~~~

như AAD đã canonicalize. Khi decrypt phải cung cấp đúng AAD; nếu attacker chuyển ciphertext của tenant A sang tenant B, authentication tag phải fail thay vì lộ plaintext ở context khác.

### 17.4. Không xây cryptography tùy tiện

Ưu tiên SDK/KMS hoặc thư viện được đánh giá. Những ví dụ AES-GCM trong bài dùng để hiểu luân chuyển khóa và metadata, không thay security review, nonce management, format compatibility, key lifecycle hay threat modeling.

### 17.5. Search/index limitations

Ciphertext không tự hỗ trợ range queries, prefix search hoặc sort như plaintext. Nếu cần query trên trường nhạy cảm, phải thiết kế riêng theo security/product requirements; không lưu thêm plaintext index “cho nhanh” mà phá mục tiêu mã hóa.

### 17.6. Key caching

Nếu application cache plaintext DEKs trong memory để giảm KMS calls, phải có bounded lifetime, access boundary, audit và zeroization policy khả thi; cache không được làm một key bị revoke tiếp tục được sử dụng vô hạn.

## 18. Ba kiểu thay đổi khóa và tác động tới dữ liệu

| Thay đổi | Điều đổi | Cần đọc khóa cũ? | Có cần chạm mọi ciphertext cũ? |
|---|---|---|---|
| Đổi credential truy cập DB | Password/token | Không vì dữ liệu mã hóa riêng | Không |
| Đổi KEK để wrap DEK | KEK/wrapped DEK | Thường cần quyền unwrap/rewrap cũ trong migration | Có thể chỉ cập nhật wrapped DEKs |
| Đổi DEK dùng cho dữ liệu | Data encryption key | Có để decrypt dữ liệu cũ | Có nếu muốn toàn bộ ciphertext dùng DEK mới |

### 18.1. Rewrap

Nếu DEK không đổi, có thể unwrap DEK bằng KEK cũ rồi wrap DEK bằng KEK mới theo cơ chế an toàn, chỉ thay encrypted DEK metadata. Ciphertext nội dung có thể giữ nguyên.

### 18.2. Re-encrypt

Nếu DEK bị thay, cần decrypt dữ liệu cũ rồi encrypt lại bằng DEK mới (hoặc thay records theo một thiết kế envelope tương đương). Đây là migration dữ liệu thực sự, có chi phí I/O/CPU/KMS và concurrency risk.

### 18.3. Automatic KMS rotation không đồng nghĩa migrate data

Một số KMS providers có cơ chế key material rotation trong cùng logical key ID, tự giữ các key versions cần cho decrypt ciphertext cũ. Chính xác cơ chế phụ thuộc dịch vụ; không suy rằng KMS “đã rotate” nghĩa toàn bộ NoSQL documents đã được mã hóa lại.

### 18.4. Retire khác destroy

Có thể ngừng dùng key cũ để encrypt dữ liệu mới, nhưng vẫn cần cho decrypt records lịch sử, backups hoặc audit. Hủy key material quá sớm có thể làm dữ liệu không thể khôi phục.

### 18.5. Khi có compromise

Nếu nghi ngờ DEK lộ, chỉ rewrap bằng KEK mới không loại bỏ rủi ro vì attacker vẫn có DEK đã lộ. Cần đánh giá dữ liệu được mã hóa bởi DEK đó, đổi DEK/re-encrypt và kế hoạch incident response.

## 19. Key version phải được lưu cùng ciphertext

Nếu chỉ lưu:

~~~text
encryptedValue = ...
~~~

mà không biết phiên bản khóa/algorithm, rotation có thể khiến reader không giải mã được records cũ.

### 19.1. Version trong mỗi record hoặc mỗi envelope

~~~text
keyVersion
algorithm
encryptedDek
nonce
authenticationTag
ciphertext
~~~

### 19.2. Không suy version từ createdAt

Records được backfill, copy, restore hoặc re-encrypt sau khi tạo. createdAt không chắc nói key nào đã encrypt.

### 19.3. Hỗ trợ đọc nhiều versions

Trong giai đoạn migrate:

~~~text
Reader v2:
  reads ciphertext using DEK v1
  reads ciphertext using DEK v2

Writer v2:
  writes only with active DEK v2
~~~

### 19.4. Có validation cho version không biết

Nếu document ghi keyVersion không nằm trong key registry/allowlist, đừng thử bừa mọi key hoặc trả empty String; fail closed và phát lỗi có kiểm soát để điều tra.

### 19.5. Mã hóa xác thực và lỗi tag

AES-GCM authentication/tag failure có thể do ciphertext hỏng, sai AAD, sai key, lỗi migration hoặc tampering. Không log plaintext, raw key, ciphertext toàn bộ hay internal details cho caller; ghi reason category và key version.

## 20. Luân chuyển encryption key không làm gián đoạn

Một quy trình có thứ tự:

~~~mermaid
flowchart TD
    A["Inventory encrypted fields and key versions"] --> B["Create new key / DEK version"]
    B --> C["Roll out readers supporting old and new"]
    C --> D["Switch writers to new active version"]
    D --> E["Migrate old ciphertext or rewrap as planned"]
    E --> F["Reconcile counts, checksums, decrypt ability"]
    F --> G["Retire old encrypt permissions"]
    G --> H["Destroy old material only after retention and recovery review"]
~~~

### 20.1. Readers trước writers

Nếu writer tạo ciphertext v3 trước khi tất cả readers hiểu v3, một số service instances sẽ lỗi. Đẩy dual-version readers trước, sau đó chuyển write version.

### 20.2. Không giữ một “global current key” làm giả định cho read

Để decrypt, dùng keyVersion trên ciphertext. Current active key chủ yếu quyết định encryption cho **records mới/updates mới**.

### 20.3. Migration theo batch với checkpoint

Đừng re-encrypt hàng trăm triệu records trong một transaction hoặc một job không có resume. Dùng partition/range scan, checkpoint, rate limiting, retries và version compare.

### 20.4. Không ghi đè một update mới bằng ciphertext cũ

Một worker đọc document v7 để re-encrypt; user đồng thời update field thành v8. Worker chỉ được write encrypted value nếu document version/current ciphertext vẫn khớp snapshot. Nếu không, retry từ dữ liệu mới.

### 20.5. Dual-write không được tạo hai nguồn sự thật mơ hồ

Trong một số migration cần field oldCiphertext và newCiphertext tạm thời. Định nghĩa reader precedence, checksum, migration state và thời điểm xóa old field. Không để hai ciphertext khác nhau cùng mang authority lâu dài.

### 20.6. Đối soát có bằng chứng

Đo:

~~~text
records_by_key_version
reencrypt_attempts_total
reencrypt_success_total
reencrypt_failure_total{category=...}
decrypt_error_total{key_version=...}
migration_old_version_remaining
~~~

Các metrics chỉ ghi version label có cardinality giới hạn; không ghi plaintext hoặc raw DEKs.

### 20.7. Backups và retention là một phần của kế hoạch

Một snapshot hai năm trước có thể chứa ciphertext v1. Nếu xóa key v1 vì production hiện chỉ còn v3, backup đó có thể không restore được. Cần kiểm tra retention, legal hold và khả năng khôi phục trước khi hủy vật liệu khóa.

## 21. Thử phục hồi dữ liệu sau key rotation

Một rotation chưa hoàn tất chỉ vì service hiện tại decrypt thành công.

### 21.1. Test các nhóm dữ liệu

- Record mã hóa bằng key v1.
- Record mã hóa bằng key v2.
- Record được rewrapped, không đổi ciphertext.
- Record được re-encrypted.
- Record update đồng thời migration.
- Record từ snapshot trước rotation.

### 21.2. Test read/write xuyên deployment versions

Trước khi writer dùng v2, tất cả readers dự kiến còn hoạt động phải hiểu v2. Sau cutover, thử restart instance từ build đang được hỗ trợ và xác nhận không quay về encrypt v1.

### 21.3. Test lỗi mất quyền KMS

Nếu decrypt permission bị thu hồi, application phải fail closed cho dữ liệu bảo vệ, không trả plaintext cache sai, không log raw ciphertext/key nhằm debug.

### 21.4. Test không còn dùng old key

Một reader decrypt old data có thể đúng, nhưng writer tạo ciphertext mới với old key là lỗi rotation. Đo keyVersion của writes mới và audit KMS operations.

### 21.5. Restore isolation

Chạy restore drills trong môi trường được cấp quyền riêng, với keys/permissions thích hợp; tránh copy production key material sang máy developer chỉ để kiểm tra backup.

## 22. Key hierarchy và phạm vi tenant

### 22.1. Một key chung cho mọi tenant

Đơn giản hóa quản lý, nhưng compromise hoặc lỗi phân quyền có thể có blast radius lớn.

### 22.2. Keys theo tenant

Có thể giảm blast radius và cho phép crypto-shredding trong phạm vi nhất định, nhưng tăng số key operations, lifecycle, billing, disaster recovery và complexity.

### 22.3. Một key theo record

Một DEK riêng cho từng record có thể làm giảm phạm vi ảnh hưởng DEK, nhưng số wrapped DEKs/KMS interactions và metadata lớn hơn. Thực tế có thể dùng caching/batching theo design được review.

### 22.4. Crypto-shredding có điều kiện

Hủy khóa có thể làm ciphertext không thể giải mã, nhưng chỉ khi không còn bản sao plaintext/keys trong caches, logs, backups hoặc nơi khác. Không tuyên bố xóa dữ liệu bằng việc hủy một key nếu bản sao vẫn tồn tại.

### 22.5. Encryption context và tenant isolation

KMS APIs có thể hỗ trợ encryption context/AAD. Dùng context đã định nghĩa, như tenantId/purpose, để hạn chế nhầm lẫn và áp quyền khi nhà cung cấp cho phép. Context thường có thể xuất hiện trong audit và không nên chứa secrets/PII.

## 23. Chứng chỉ TLS cũng có vòng đời rotation

### 23.1. Server certificate

NoSQL server/proxy thay certificate cần client trust store hợp lệ và hostname verification. Không phải lúc nào private key của ứng dụng đổi.

### 23.2. Client mTLS certificate

Service có private key/certificate riêng, expiration, SAN/identity và revocation policy. Đây là secret-bearing material khác database password.

### 23.3. Overlap của trust chain

Khi thay certificate authority, thường cần roll out trust của CA mới trước khi server bắt đầu dùng certificate do CA mới ký, rồi mới gỡ trust CA cũ khi an toàn.

### 23.4. Không log private key hoặc PEM

Một Java TLS debug dump hoặc exception khi parse key store không nên ghi PEM private key. Dùng key alias/version, certificate public metadata được phê duyệt, serial/expiry và loại lỗi.

### 23.5. Kiểm tra mốc hết hạn

Theo dõi certificate expiration/renewal errors, thiết lập cảnh báo trước deadline và test fresh TLS handshakes. Một pool đang sống không tự chứng minh certificate mới hoạt động.

## 24. Quyền truy cập KMS là một boundary độc lập

### 24.1. Application quyền encrypt/decrypt

Một service cần decrypt dữ liệu tenant mình phục vụ có thể được cấp quyền tối thiểu. Không mặc định cấp CreateKey, ScheduleKeyDeletion, key policy admin cho runtime.

### 24.2. Rotation operator quyền quản lý key

Rotation controller/admin có thể cần quyền rộng hơn nhưng nên nằm ở principal riêng với approval/audit.

### 24.3. Đọc NoSQL không đồng nghĩa decrypt được

Một read-only DB user có thể xem ciphertext/encryptedDEK nhưng không giải mã được nếu không có quyền KMS và raw DEK không bị lộ.

### 24.4. Nhưng application compromise có thể đọc cả hai

Nếu một service có quyền đọc NoSQL và decrypt bằng KMS, attacker chiếm service có thể yêu cầu decrypt trong giới hạn quyền đó. Cần segmentation, tenant-aware authorization, anomaly detection và giảm quyền.

### 24.5. KMS throttling và cache

Quá nhiều decrypt calls có thể tạo latency/throttle. Tối ưu cache DEK/crypto context cần đánh đổi bảo mật; không giữ raw key bất tận chỉ để giảm p99.

## 25. Khi rotation bị gián đoạn giữa chừng

Một ví dụ:

~~~text
10:00 v2 created.
10:05 Reader 70% instances supports v2.
10:06 Writer starts producing v2.
10:07 Other 30% readers fail to decrypt.
~~~

Đây là lỗi ordering: writer chuyển trước khi reader fleet sẵn sàng.

### 25.1. Giữ migration state bền vững

~~~text
candidateVersion
readerCompatibilityVerified
writerActiveVersion
oldVersionRemaining
lastCheckpoint
failureReason
~~~

### 25.2. Tạm dừng writer cutover khi thiếu readiness

Canary/deployment check phải đủ để biết các readers dự kiến còn hoạt động có hiểu phiên bản mới. Chỉ kiểm thử một endpoint không đảm bảo batch jobs hoặc CDC consumers cũng hiểu.

### 25.3. Không hủy old key khi còn dữ liệu cần decrypt

Một số records cũ chưa được migrate hoặc backup vẫn dùng v1. Old decrypt-only permission có thể cần tồn tại qua quá trình. Việc delete key phải qua review riêng.

### 25.4. Nếu key compromise

Trong incident, có thể phải cắt old decrypt access sớm hơn, chấp nhận hạn chế phục hồi và thực hiện incident playbook. Không dùng availability-first rollout như một quy tắc bất biến khi confidentiality có nguy cơ cấp bách.

## 26. Log là một hệ lưu trữ dữ liệu, không phải vùng an toàn mặc định

Logs có thể được chuyển tới:

~~~text
Java service stdout
   -> container runtime
   -> log collector/agent
   -> message pipeline
   -> central log database
   -> dashboards/alerts
   -> archive/backup/export
~~~

Một secret xuất hiện trong stdout có thể được nhân bản nhiều nơi và tồn tại trong các backups lâu hơn credential đang dùng.

### 26.1. Tại sao việc “xóa dòng log” khó?

Một log đã phát có thể nằm trong immutable archive, hệ search, alert message, incident ticket hoặc máy người đã tải xuống. Xóa một bản sao ở dashboard không đủ chứng minh secret đã được xóa mọi nơi.

### 26.2. Quy tắc số một

**Không tạo log chứa secret ngay từ đầu.** Redaction ở log collector là lớp dự phòng, không phải giải pháp duy nhất.

### 26.3. Không chỉ password

Các dữ liệu không được log:

- Bearer tokens, cookies/session IDs có thể dùng để xác thực.
- AWS access/secret/session tokens.
- Redis ACL passwords.
- MongoDB credentials trong URI.
- Cassandra client private keys.
- KMS plaintext key material/DEKs.
- Authorization headers.
- Password reset tokens, signed URLs có quyền truy cập.
- Personal data hoặc query parameters nhạy cảm theo policy.

### 26.4. Log format có thể làm tăng khả năng phát hiện

Structured logs với field names ổn định giúp áp allowlist/filter và truy vấn sự cố. Nhưng JSON structured log vẫn có thể chứa secret nếu developer thêm trường password. Schema logging phải giới hạn cả fields lẫn giá trị.

## 27. Bẫy Java: log đối tượng cấu hình bằng toString()

~~~java
logger.info("Database config: {}", databaseProperties);
~~~

Nếu databaseProperties là Lombok @Data hoặc record, toString() có thể chứa password/token/URI.

### 27.1. ToString an toàn theo allowlist

~~~java
public final class DbConnectionMetadata {
    private final String database;
    private final String credentialVersion;

    public DbConnectionMetadata(
            String database, String credentialVersion
    ) {
        this.database = database;
        this.credentialVersion = credentialVersion;
    }

    @Override
    public String toString() {
        return "DbConnectionMetadata{" +
                "database=" + database +
                ", credentialVersion=" + credentialVersion +
                ", tls=true" +
                "}";
    }
}
~~~

Ngay cả database name hoặc credentialVersion có thể là metadata nhạy cảm theo tổ chức; ví dụ chỉ minh họa cách chọn các trường được phép log.

### 27.2. Không log object chứa secret rồi kỳ vọng logger tự giấu

SLF4J, Logback, Log4j không tự hiểu mọi field nào là secret. Nếu một object có method toString() lộ raw credential, placeholder thường vẫn gọi toString() và có thể in secret.

### 27.3. Lombok @ToString.Exclude chưa phải biện pháp duy nhất

Có thể exclude field nhạy cảm trong generated toString, nhưng sub-objects, inheritance, exceptions và serializers vẫn có thể rò. Tốt hơn dùng **log DTO allowlist** chỉ gồm safe fields.

### 27.4. Đừng dùng reflection dump của mọi fields

Các utility “dump object to JSON” dùng cho debugging có thể xuất mọi cấu hình đã resolve, nested credential và header. Chỉ log schema đã được phê duyệt.

## 28. Bẫy Java: exception message có thể chứa URI

~~~java
try {
    mongoClient.getDatabase("orders").runCommand(
            new org.bson.Document("ping", 1)
    );
} catch (RuntimeException ex) {
    logger.error("MongoDB ping failed: {}", ex.getMessage());
}
~~~

Không phải mọi exception message đều lộ secrets, nhưng **không có bảo đảm tổng quát** rằng message không chứa URI, query, endpoint hoặc values.

### 28.1. Log class + safe category thay vì message toàn phần

~~~java
logger.warn(
        "Database operation failed operation={} errorClass={} credentialVersion={}",
        "mongodb.ping",
        ex.getClass().getSimpleName(),
        currentCredentialVersion
);
~~~

Đây là một pattern giảm rủi ro, không phải cách duy nhất. ex.getClass().getSimpleName() thường an toàn hơn raw message, nhưng tránh cả user-defined class names chứa dữ liệu không tin cậy.

### 28.2. Stack trace cũng cần chính sách

Stack trace có thể chứa messages và suppressed causes. Nếu log exception object:

~~~java
logger.error("Database failed", ex);
~~~

toàn bộ nested causes có thể được in. Chỉ dùng full stack trace tại nơi đã được đánh giá/redacted và kiểm soát quyền; không giả định “không in ex.getMessage()” thì stack trace chắc chắn an toàn.

### 28.3. Error category đủ để cảnh báo

~~~text
DATABASE_AUTH_FAILED
DATABASE_TIMEOUT
TLS_HANDSHAKE_ERROR
KMS_ACCESS_DENIED
SECRET_REFRESH_FAILED
KEY_VERSION_UNAVAILABLE
~~~

Với category, service/region/keyVersion/time và traceId, on-call thường có đủ thông tin để định vị, rồi truy cập restricted diagnostics khi cần.

### 28.4. Không trả exception nguyên bản qua HTTP

Một API global exception handler không được serialize driver exception object hoặc config field ra JSON response. Trả error code công khai và correlation ID thay vì raw internal details.

## 29. URI/query string: nơi secrets dễ bị log ngầm

### 29.1. Database connection strings

~~~text
mongodb+srv://<USER>:<PASSWORD>@cluster.example.invalid
redis://<USER>:<PASSWORD>@cache.example.invalid:6379
~~~

Các chuỗi chứa credential cần được bảo vệ cả khi lưu config lẫn khi in.

### 29.2. HTTP URL chứa token

Một signed URL hoặc API key đặt trong query parameter có thể bị CDN, proxy access log, browser history và tracing tự ghi lại. Ưu tiên transport/auth mechanism phù hợp; nếu bắt buộc dùng signed URL, đặt TTL ngắn và hạn chế logging.

### 29.3. Log URL phải parse và rebuild an toàn

Không chỉ dùng regex xóa đoạn sau password= vì URI có userinfo, percent-encoding và nhiều query formats. Dùng **allowlist** host/scheme/path đã đánh giá, hoặc các trường metadata riêng từ config model thay vì raw URL.

### 29.4. Đừng log query params toàn bộ

Một endpoint:

~~~text
/admin/debug?token=<SECRET>&connection=<SENSITIVE_URI>
~~~

có thể bị request logging middleware ghi đủ. Không thêm token vào query ngay từ đầu, và cấu hình access logs không giữ raw query string nếu chứa dữ liệu nhạy cảm.

### 29.5. Proxy logs nằm ngoài Java

Ngay cả khi ứng dụng dùng safe logging, ingress/service mesh/API gateway có thể ghi Authorization headers hoặc URL chứa secrets. Cần kiểm soát từng hop.

## 30. Structured logging: allowlist tốt hơn blacklist

Một mẫu event tốt:

~~~json
{
  "event": "nosql_connection_failure",
  "service": "orders-api",
  "databaseType": "mongodb",
  "operationClass": "connection.open",
  "credentialVersion": "v18",
  "tlsEnabled": true,
  "errorCategory": "AUTHENTICATION_FAILED",
  "traceId": "trace-placeholder"
}
~~~

### 30.1. Event không có password

Service vẫn có đủ dữ liệu để hỏi “v18 đang lỗi ở đâu?” mà không in raw credential.

### 30.2. Không log full request/response

Một INSERT MongoDB có thể chứa full customer profile; một DynamoDB PutItem có thể chứa contact address; Redis SET có thể chứa session token. Log operation class và status thay vì body.

### 30.3. Không log full Java properties/map

~~~java
logger.info("Environment: {}", System.getenv()); // Sai về bảo mật.
logger.info("Config: {}", applicationProperties); // Có thể sai.
~~~

Environment và resolved configuration có thể chứa secrets. Ngay cả filter một vài tên như PASSWORD/TOKEN không bắt được credential với tên khác.

### 30.4. Dùng safe log event object

~~~java
public record SafeDbAuditEvent(
        String operationClass,
        String resultCategory,
        String service,
        String credentialVersion,
        long elapsedMillis
) {}
~~~

Chỉ xây event từ những fields đã được phê duyệt; không truyền raw exception/config vào nested object.

### 30.5. Nhãn nội bộ cũng có mức độ nhạy cảm

Tenant ID, hostnames, IPs, cluster topology và credential version có thể bị giới hạn quyền truy cập theo chính sách. “Không phải password” không đồng nghĩa có thể công bố công khai.

## 31. Logging filter ở framework: lớp phòng thủ bổ sung

Logback/Log4j có appenders, encoders, filters và message converters. Có thể cài redaction ở log pipeline nhằm phát hiện patterns:

~~~text
Authorization: Bearer ...
password=...
secretAccessKey=...
mongodb+srv://user:pass@...
~~~

### 31.1. Regex masking có thể bỏ sót

Secrets có thể bị split qua nhiều lines, encode/base64, nằm trong JSON nested fields hoặc dùng tên khác. Masking regex chỉ là **defense in depth**.

### 31.2. Masking sau khi app đã log là muộn đối với một số sinks

Console logs, crash dumps hoặc debug subscribers có thể thấy raw message trước filter. Source-level allowlist logging vẫn quan trọng nhất.

### 31.3. Filter có thể làm hỏng bằng chứng

Một bộ regex quá rộng có thể xóa error codes/metadata cần điều tra. Thử nghiệm trên bộ mẫu logs hợp lệ và test leaks với synthetic markers.

### 31.4. Log levels không là chính sách bảo mật

“Chỉ log password khi DEBUG” vẫn rủi ro vì DEBUG có thể vô tình bật trong production hoặc logs được thu thập tự động. Không có level nào được phép chứa raw credential.

### 31.5. Quản trị thay đổi logging config

Việc bật wire/driver debug logs nên có approval, time limit, owner và post-change verification. Không để bật vô hạn sau incident.

## 32. HTTP request logging và headers

Headers đặc biệt nhạy cảm:

~~~text
Authorization
Cookie
Set-Cookie
X-API-Key
X-Auth-Token
Proxy-Authorization
cloud provider session tokens
~~~

### 32.1. Allowlist headers

Log một số trường như request method, path template, status, duration, trace ID, content length; không log tất cả headers rồi chỉ xóa Authorization.

### 32.2. Request body cũng chứa secrets

Login/password reset, API token generation, database administration endpoints hoặc encryption key metadata có thể chứa dữ liệu nhạy cảm. Không bật body logging ở gateway/app toàn hệ.

### 32.3. Response body cũng có secrets

Một endpoint phát temporary credentials hoặc signed URL cần được bảo vệ cả response logging, APM capture và browser/network tools.

### 32.4. Spring filters/interceptors

Một OncePerRequestFilter logging mọi headers/body là anti-pattern. Cần tạo event với path template, status/latency và request ID đã allowlisted, kiểm soát sự khác biệt giữa public và admin endpoints.

### 32.5. Không lưu token trong MDC

Mapped Diagnostic Context rất hữu ích cho traceId/tenant tier nhưng dễ tự động xuất trên mọi log line. Tuyệt đối không đặt Authorization header hoặc raw session token vào MDC.

## 33. Tracing OpenTelemetry và nguy cơ lan truyền secrets

Một trace thường chứa spans ở:

~~~text
HTTP ingress
Java controller
NoSQL driver
Redis cache
Secret manager call
KMS Decrypt
~~~

### 33.1. Span attributes có thể xuất dữ liệu

Nếu auto-instrumentation thêm raw statement hoặc URL, có thể chứa filters, database names, query parameters hoặc token. Cần xem semantic conventions/instrumentation version và cấu hình sanitization.

### 33.2. Không dùng secrets làm baggage

Tracing baggage thường được truyền xuyên services/headers. Không gửi password, access token, DEK, plaintext PII hoặc private key material trong baggage để “dễ chẩn đoán”.

### 33.3. Metric tag cardinality

Không đưa raw userId, email, session token, API key hoặc secretVersion với không gian vô hạn vào metric labels. Dùng errorCategory, operationClass, service, environment và version identifier có giới hạn.

### 33.4. Spans của KMS

Log operation type, latency, service, error class và key ID an toàn theo policy. Không log raw plaintext/ciphertext data keys hoặc encryption context có PII.

### 33.5. Sampling không thay sanitization

Chỉ sample 1% traces vẫn có thể chứa secret trong 1% đó. Phải loại bỏ tại source trước khi sampling/export.

## 34. Spring Boot Actuator, configuration endpoints và diagnostic dumps

Actuator có thể cung cấp thông tin hữu ích về môi trường runtime, nhưng endpoints và configuration exposure phải được bảo vệ.

### 34.1. Không expose môi trường tùy tiện

Các endpoints liên quan env/configprops có khả năng hiển thị cấu hình; hệ sinh thái Spring Boot có các tùy chọn sanitization/show-values thay đổi theo phiên bản. Cần kiểm tra cấu hình thực tế, RBAC/auth và phạm vi network; đừng dựa vào mặc định mà không verify.

### 34.2. Health endpoint không cần công bố credentials

~~~json
{
  "status": "DOWN",
  "components": {
    "mongodb": {"status": "DOWN"}
  }
}
~~~

Đây là health summary minh họa. Không trả MongoDB URI, username/password hoặc full exception message cho unauthenticated callers.

### 34.3. Heap dump và thread dump

Heap dump có thể chứa String/char[] secrets, cached DEKs, tokens và configs. Thread dumps/stack traces đôi khi chứa args hoặc dữ liệu tình cờ. Hạn chế ai có quyền tạo, tải và lưu diagnostic artifacts.

### 34.4. Java Flight Recorder/profilers

Profiling có thể thu event hoặc sampled allocations; hãy hiểu chính xác data được capture và giới hạn access/retention. Không upload heap dump vào public issue tracker.

### 34.5. Debug flags và verbose TLS

Các cờ debug như Java SSL handshake logging hữu ích lúc điều tra, nhưng cần được phê duyệt và giới hạn thời gian; không mặc định an toàn để lưu toàn bộ output trong log tập trung.

## 35. Database audit, profiler và query logs cũng phải kiểm soát

Ứng dụng đã che password trong app logs không có nghĩa database/proxy tự che mọi giá trị.

### 35.1. MongoDB profiling

Profiler có thể giữ command/query details tùy cấu hình/phiên bản, gồm values của filters hoặc updates. Không bật mức thu thập quá rộng trong production rồi mở quyền xem cho tất cả engineers.

### 35.2. Cassandra query tracing

Query trace và debug events phục vụ chẩn đoán, nhưng statement/parameter metadata có thể chứa identifiers hoặc thông tin nội bộ. Cần hạn chế truy cập, lấy mẫu và thời gian lưu.

### 35.3. DynamoDB CloudTrail và SDK logging

CloudTrail/API events hữu ích cho audit nhưng cần hiểu data events, request parameters và IAM scopes theo dịch vụ/cấu hình. Không giả định mọi audit event hoặc SDK logger đều đã ẩn dữ liệu nhạy cảm trong request.

### 35.4. Redis MONITOR

MONITOR hữu ích khi phân tích commands nhưng có thể xuất values/command details và gây load. Không chạy/ghi output trên dữ liệu thực khi không có phê duyệt và khả năng bảo vệ.

### 35.5. Audit log của secret manager/KMS

Audit nên cho biết **ai**, **lúc nào**, **truy cập version/key nào**, **operation nào**, **kết quả gì**. Không phải ghi raw secret value. Thiết lập retention, RBAC và alert truy cập bất thường.

## 36. CI/CD, IaC và local development là đường rò rỉ phổ biến

### 36.1. Secrets không được nằm trong Git

Không commit production credentials vào:

~~~text
application-prod.yml
.env
Dockerfile
terraform.tfvars
build.gradle properties
test fixtures containing real passwords
~~~

### 36.2. Git history và artifacts

Xóa một line ở commit mới không xóa nó khỏi commit cũ, forks, caches và CI logs. Nếu secret từng được commit, cần xem là có khả năng bị lộ, ưu tiên **revoke/rotate**, rồi làm sạch history/artifacts theo quy trình được phép.

### 36.3. Build arguments và Docker layers

Tránh truyền raw secrets qua Docker ARG/ENV trong lúc build nếu chúng có thể nằm trong image history/layers/build logs. Dùng runtime injection hoặc build secret mechanism hỗ trợ mà không lưu vào artifact, và kiểm chứng output.

### 36.4. CI secret masking không bảo đảm tuyệt đối

CI có thể che exact literal secret nhưng bỏ sót khi secret đã được encode, cắt chuỗi hoặc chuyển format. Không echo environment, không bật shell xtrace quanh secret injection.

### 36.5. Infrastructure as Code state

Terraform/state và các IaC outputs có thể giữ sensitive values. Gắn nhãn sensitive ở UI không tự mã hóa state. Bảo vệ state storage, IAM, encryption và retention.

### 36.6. Developer machine

Không chia sẻ production DB passwords qua chat/email, tài liệu công khai hoặc copy vào clipboard dài hạn. Ưu tiên local identity, test credentials riêng, short-lived access và audit.

## 37. Secret injection: environment, file mount hay API?

| Cách | Ưu điểm | Rủi ro/giới hạn |
|---|---|---|
| Environment variable | Tích hợp đơn giản | Có thể xuất hiện trong process introspection, crash dump, diagnostic logs; rotation thường cần reload/restart |
| Protected file mount | Kiểm soát quyền FS, có thể được cập nhật | Permissions, file watchers và atomic replacement cần thiết kế |
| Secret manager SDK call | Phân quyền, audit, version và refresh chủ động | Network/dependency, startup/unavailable, caching policy |
| Workload identity + SDK | Ít static keys, temporary credentials | Cần IAM, runtime integration và đúng provider chain |
| Hardcoded value | Không có ưu điểm an toàn | Secret leak, khó rotate, bản sao khắp nơi |

### 37.1. Environment variable không phải encryption

Env chỉ là kênh truyền runtime. Secret vẫn có thể nằm trong container config, process memory, diagnostics và deployment metadata tùy hệ thống.

### 37.2. File permission

Protected mount nên giới hạn quyền đọc tới đúng process/user, không ghi world-readable, không tự động sao chép vào backup chưa được quản lý.

### 37.3. Dynamic file update

Một file mount có thể được thay nguyên tử hoặc thay nội dung theo service provider, nhưng Java process cần reload và mở lại connection; không assume Files.readString() khi startup tự nhìn thấy version mới.

### 37.4. SDK caching

Provider có thể cache secrets theo TTL để giảm latency. TTL phải phối hợp với rotation overlap, revocation urgency và maximum credential age.

### 37.5. Secret source priority

Nếu app vừa đọc secret manager vừa có ENV fallback, có thể vô tình dùng credential cũ lâu ngày. Công bố thứ tự ưu tiên và cho phép fail closed khi nguồn yêu cầu không khả dụng.

## 38. Metrics cho rotation và phòng ngừa rò rỉ

| Signal | Metric dạng gợi ý | Câu hỏi |
|---|---|---|
| Secret versions | instances_by_credential_version | Fleet đã chuyển sang version mới? |
| Secret refresh | secret_refresh_failure_total | Có lỗi lấy version active? |
| Authentication | db_auth_failure_total | New connections có bị reject? |
| TLS | tls_handshake_failure_total | Cert/trust chain còn đúng? |
| Certificate lifetime | certificate_expiry_seconds | Có sắp hết hạn? |
| KMS access | kms_access_denied_total | Quyền decrypt có bị sai? |
| Encryption migration | records_by_key_version | Còn dữ liệu dùng key cũ? |
| Decryption failures | decrypt_failure_total{category=...} | Migration/AAD/key mismatch? |
| Audit | unexpected_secret_access_total | Có principal truy cập bất thường? |
| Logs | sensitive_marker_leak_test_failure_total | Kiểm thử chống rò có fail? |
| Data recovery | backup_decrypt_drill_success | Có restore từ backup cũ không? |

### 38.1. Chỉ log version, không log raw key

Để biết v18 đang active, chỉ cần version ID hoặc key alias thuộc danh mục được phép. Không gửi fingerprint từ secret bytes lên metrics.

### 38.2. Cardinality và nhạy cảm

Không dùng raw tenantId, userId, token hash, IP private hoặc secret path nếu chúng là nhãn nhạy cảm/quá nhiều giá trị. Chọn các nhóm aggregate và kiểm soát truy cập telemetry.

### 38.3. Alert sai lệch luân chuyển

~~~text
Secret active version = 18.
5% instances still report version 17 after cutover deadline.
DB authentication errors rise on new connections.
~~~

Cần điều tra trước khi revoke old, trừ trường hợp compromise yêu cầu emergency revoke.

### 38.4. SLO cho refresh

Một service cần mở connection mới sau rotation trong một thời hạn xác định. Theo dõi thời gian từ version active tới mọi consumers nhận version mới, và error rate trong window.

## 39. Kiểm thử chống rò rỉ bằng synthetic secrets

Một cách kiểm thử hữu ích là cấp **synthetic canary credential** chỉ tồn tại trong test và kiểm tra nó không đi qua logging pipeline.

### 39.1. Marker giả không có quyền thực

~~~text
TEST_ONLY_SECRET_MARKER_9B4D7F8A
~~~

Marker này không phải mật khẩu thực và không được dùng làm credential cho production.

### 39.2. Trigger các đường lỗi có chủ đích

- Authentication failed.
- TLS handshake failed.
- Secret manager 403/timeout.
- MongoDB query error.
- Redis connection refused.
- DynamoDB throttling.
- Serialization failure.
- Application config validation error.

### 39.3. Kiểm tra các sinks

Capture logs, traces, metrics, error responses và CI output trong test environment. Assert synthetic marker/raw secret không xuất hiện trong những sinks này; đồng thời xác nhận safe metadata vẫn hiện để có thể chẩn đoán.

### 39.4. Không chỉ test exact marker

Một logger có thể xuất secret dưới URL encoding/Base64/JSON escaping hoặc tách thành nhiều fragments. Kiểm tra các biến thể có chủ đích ở test suite, nhưng không suy test pass nghĩa mọi kiểu leak đều được chặn.

### 39.5. Không dùng secret thật để thử

Không cố tình đưa production password vào lỗi rồi grep logs; đó là hành động tạo rủi ro. Dùng marker giả, ephemeral credential quyền tối thiểu và môi trường cô lập.

## 40. Java test: assert secret không nằm trong log

Một test ý tưởng:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

public final class CredentialLoggingTest {
    @Test
    void configStringMustNotRevealSecret() {
        String marker = "TEST_ONLY_SECRET_MARKER_9B4D7F8A";
        SecretValue secret = new SecretValue(marker.toCharArray());

        String rendered = secret.toString();

        assertFalse(rendered.contains(marker));
        assertEquals("[REDACTED]", rendered);
    }
}
~~~

### 40.1. Test toString chỉ là một test nhỏ

Cần integration test ghi log thật từ đường exception/config reload/driver startup, rồi kiểm tra appender output. Một toString() an toàn không bảo vệ framework tự serialize fields bằng reflection.

### 40.2. Test tại collector

Nếu telemetry collector có redaction bổ sung, có thể kiểm tra cả trước và sau collector để biết raw data có từng xuất hiện ở nguồn không. Đừng chỉ kiểm tra dashboard cuối cùng.

### 40.3. Test không bỏ log hữu ích

Assert errorCategory, operationClass, credentialVersion và traceId vẫn được ghi. Nếu code chỉ tắt toàn bộ logging để pass leak test, khả năng vận hành bị ảnh hưởng.

### 40.4. Trong CI

Chặn merges khi có hardcoded secret pattern, secret-scanning alerts hoặc regression tests rò marker. Secret scanners không phải bằng chứng tuyệt đối; chúng cần được phối hợp với code review và runtime tests.

## 41. Secrets scanning và phân loại cảnh báo

### 41.1. Scanning repository

Tìm AWS access key patterns, private key PEM, tokens, passwords và high-entropy strings trong source/commits/config. Có thể dùng công cụ scanning nội bộ được phê duyệt.

### 41.2. False positives

Một chuỗi test-marker hoặc hash có thể bị báo nhầm. Cần quy trình triage minh bạch, không mặc định bỏ qua mọi alerts trong test folder.

### 41.3. False negatives

Một secret chia thành hai fragments hoặc được encode có thể không match signatures. Không coi scanner pass là đã chứng minh an toàn.

### 41.4. Scanning logs

Khi được phép và có bảo vệ phù hợp, có thể quét log streams cho credentials/synthetic canaries. Không export logs chứa PII tới công cụ bên ngoài không được duyệt.

### 41.5. Phát hiện secret thật

Không copy raw value vào ticket. Ghi secret type, vị trí, thời điểm, phạm vi ảnh hưởng, hashed artifact ID nếu an toàn, rồi **rotate/revoke và điều tra truy cập**.

## 42. Runbook khi credential xuất hiện trong log

### Bước 1 — Coi credential có thể đã lộ

Không tranh luận rằng “chắc chưa ai nhìn thấy” chỉ vì log tồn tại ít phút. Đánh giá theo access, retention và threat model.

### Bước 2 — Chặn phát tán mới

Tắt đường logging gây rò qua cấu hình/patch, giữ service khả dụng nếu an toàn. Không vô tình tạo thêm logs raw secret khi debug.

### Bước 3 — Thu hồi/rotate

Revoke credential đã lộ hoặc tiến hành emergency rotation theo severity. Với DB passwords, cấp credential mới và chuyển clients có kiểm soát; nếu compromise rõ ràng, có thể phải ưu tiên revoke ngay.

### Bước 4 — Xác định phạm vi

Kiểm tra nơi secret đã được xuất: stdout, aggregator, dashboard, alert, export, backup và người có quyền đọc. Không chỉ xóa một log line hiện tại.

### Bước 5 — Điều tra truy cập trái phép

Audit DB/secret manager/KMS actions từ thời điểm secret có thể bị lộ, xem network patterns và IAM/DB role usage bất thường.

### Bước 6 — Xử lý bản sao logs

Theo policy, hạn chế truy cập, xóa hoặc giữ bằng chứng được bảo vệ cho điều tra, cân nhắc bất biến của storage/retention và quy định liên quan. Không tuyên bố tất cả bản sao đã bị xóa nếu chưa xác minh.

### Bước 7 — Khôi phục và phòng ngừa

Thêm test synthetic marker, safe-log DTO, redaction defense-in-depth, kiểm soát driver debug và process để tránh lặp lại.

### Bước 8 — Báo cáo sự cố

Ghi timeline, credential scope, blast radius, evidence, thời điểm revoke/rotate, các hệ thống có thể bị ảnh hưởng, người chịu trách nhiệm và những giả định chưa được xác minh.

## 43. Khi encryption key bị lộ: khác credential leak

Một database password bị lộ cho phép thao tác theo DB role. Một DEK bị lộ có thể cho phép decrypt các ciphertext đã sao chép trước đó, kể cả sau khi attacker không còn truy cập database.

### 43.1. Chặn truy cập hiện tại

Thu hồi KMS/service permissions bị lợi dụng và bảo vệ key material; nếu DEK plaintext đã lộ, chỉ revoke KMS không xóa được bản sao DEK mà attacker có.

### 43.2. Xác định ciphertext nào bị ảnh hưởng

Dựa vào keyVersion/DEK scope, liệt kê records, backups và snapshots đã được mã hóa bằng key có khả năng lộ. Không dùng một key ID chung để mặc định toàn bộ records đều bị ảnh hưởng nếu thực tế DEK scopes khác nhau.

### 43.3. Re-encrypt đúng loại

Nếu KEK lộ nhưng DEK chưa chắc lộ, đánh giá threat model; nếu DEK có thể bị unwrap hoặc đã lộ, rewrap-only có thể không đủ. Có thể cần DEK mới và re-encrypt có kiểm soát.

### 43.4. Bản sao dữ liệu đã bị lấy

Đổi key hôm nay không khiến ciphertext/DEK cũ mà attacker đã copy trở nên an toàn nếu họ đã có key cần thiết. Cần đánh giá disclosure và nghĩa vụ thông báo theo policy/pháp luật liên quan.

### 43.5. Không làm mất khả năng khôi phục

Trong quá trình incident phải phối hợp bảo mật với dữ liệu sống, backups, restore drills và retention. Hủy khóa cũ quá sớm có thể gây mất dữ liệu mà không đảo ngược compromise đã xảy ra.

## 44. Một dashboard quản lý secrets thực dụng

Một dashboard không cần hiển thị raw secrets. Nó nên trả lời:

~~~text
Credential coverage:
  92% pods on v18
   8% pods on v17 (retiring)

Fresh authentication:
  success 99.99%, error categories summarized

Rotation:
  candidate created / validated / active / old revoked

Data encryption:
  new writes use DEK v3
  7.2% historical records still use DEK v2

Security:
  unexpected secret reads: 0
  credential leak regression tests: passing
  upcoming certificate expiration: 21 days
~~~

Các số chỉ minh họa, không phải trạng thái hiện tại của hệ nào.

### 44.1. Đừng hiển thị credential values

Không có lý do cho một dashboard phải hiển thị password, access key hoặc plaintext DEK để báo rotation hoàn tất. Secret manager phải cung cấp metadata về version/state an toàn.

### 44.2. Tách availability và confidentiality

Một rotation có thể nâng bảo mật nhưng tạo nhiều authentication failures. Dashboard cần nhìn cả hai; khi leak khẩn cấp, security incident commander có thể chấp nhận tạm giảm availability.

### 44.3. Alert theo deadline, không chỉ lỗi

Secret sắp hết hạn trong 48 giờ, nhưng hiện chưa có lỗi, vẫn cần action. Nếu chỉ alert khi connection bắt đầu fail thì đã quá muộn.

### 44.4. Kiểm tra consumers tắt máy

Một pod không active không xuất hiện trong gauge “version đang dùng”; batch jobs/dormant workers vẫn có thể giữ config cũ. Inventory phải bao gồm offline consumers.

## 45. Bộ tiêu chí hoàn tất credential rotation

Một change record có thể yêu cầu:

- Candidate credential được tạo trong hệ quản lý secrets.
- Quyền DB mới được kiểm tra tương đương hoặc nhỏ hơn policy đã phê duyệt.
- Fresh auth test thành công.
- TLS hostname/certificate validation vẫn bật.
- Các instances và jobs dự kiến đã chuyển version.
- Không có unauthorized/old secret references trong runtime config.
- Connection pools cũ đã drain hoặc có lý do giữ tạm thời.
- Auth failures, p99, retry rate không vi phạm SLO.
- Old credential đã được revoke theo deadline hoặc incident policy.
- Audit trail và rotation record được lưu.
- Nếu có incident, log/CI artifacts và quyền truy cập liên quan đã được xử lý.

### 45.1. Không đánh dấu complete chỉ vì secret manager label đổi

Manager có thể ghi active=v18 nhưng clients vẫn dùng v17. Cần bằng chứng từ fresh connection metrics, rollout inventory và DB audit.

### 45.2. Không đánh dấu complete nếu còn fallback v17

Một client bị lỗi v18 rồi tự fallback v17 có thể che migration failure. Sau thời gian chuyển đổi, fallback cũ phải được vô hiệu hóa theo kế hoạch.

### 45.3. Test revoke

Trong môi trường kiểm soát, xác nhận credentials cũ không thể tạo **new authenticated sessions** sau revoke. Existing sessions có thể có semantics riêng; nếu cần cắt truy cập ngay phải xác định cách terminate sessions/revoke tokens.

## 46. Bộ tiêu chí hoàn tất encryption key rotation

- New reader code hiểu old/new key versions.
- New writes luôn dùng active key.
- Mọi ciphertext có metadata phiên bản, algorithm và AAD contract.
- Key unwrap/decrypt permissions đúng workload/tenant.
- Migration/re-encrypt có checkpoint và kiểm tra concurrent updates.
- Số records theo old/new versions được đối soát.
- Decryption errors, auth tag failures và KMS throttles nằm trong giới hạn.
- Backups/snapshots còn khả năng decrypt khi restore.
- Old key không còn được dùng encrypt sau thời điểm retire.
- Quyết định retain/destroy old key có phê duyệt và xem xét retention/legal hold.

### 46.1. Khóa cũ decrypt-only có thể tồn tại lâu

Điều này có thể hợp lý khi còn dữ liệu lịch sử và backups. Phải kiểm soát scope và audit; không gọi “rotation không hoàn tất” chỉ vì key cũ được giữ có chủ đích.

### 46.2. Nếu có compromised key

Tiêu chí hoàn tất khắt khe hơn: xác định dữ liệu bị ảnh hưởng, re-encrypt thích hợp và xử lý disclosure. Chỉ hoàn thành theo quy trình incident chứ không đánh dấu hết rủi ro dựa trên vài tests.

## 47. Câu hỏi kiến trúc: secrets per service hay shared?

### 47.1. One credential for all microservices

Đơn giản về vận hành ban đầu nhưng tăng blast radius, khó audit service cụ thể và khó rotate chỉ một consumer.

### 47.2. Separate service principals

Mỗi service identity có role/ACL tương ứng; rotation có thể thực hiện theo service, audit dễ hơn và một credential leak không mặc nhiên cấp quyền mọi hệ.

### 47.3. Separate credentials per tenant

Có thể hữu ích trong SaaS có isolation cao, nhưng làm tăng quản trị, số connection identities, rotation workflow và chi phí. Không tự triển khai mà chưa đo nhu cầu/khả năng backend.

### 47.4. Dynamic short-lived database credentials

Một số secret managers/DB integrations phát credential tạm thời với lease. Giảm thời gian dùng được nếu leak, nhưng cần handle lease renewal, revocation, pool lifecycle và clock skew.

### 47.5. Quyền thấp hơn không thay mã hóa

Role read-only vẫn có thể đọc dữ liệu nhạy cảm khi bị lấy cắp. Đánh giá cả confidentiality, authorization và encryption.

## 48. Tác động của rotation tới latency và availability

Một kế hoạch rotation có thể ảnh hưởng:

- Secret manager request spikes.
- KMS GenerateDataKey/Decrypt quotas và latency.
- Connection pool churn.
- TLS handshakes.
- Authentication backend load.
- Driver retries khi credential sai.
- Cache warmup.
- Batch job reconnection.

### 48.1. Throttle rollout

Thay vì 500 pods cùng refresh và tạo pools trong một giây, rollout theo waves với random jitter, miễn không vi phạm emergency revoke deadline.

### 48.2. Pool drain

In-flight transactions có thể cần thời gian hoàn tất. Đừng close old pool giữa transaction đang commit nếu có thể tránh; nếu buộc cắt, application phải xử lý outcome ambiguity.

### 48.3. Rotation không thể dùng timeout che lỗi

Nếu authentication failures tăng, đừng tự động retry vô hạn hoặc tăng timeout rồi coi rotation thành công. Phân biệt invalid credentials với transient secret manager/network failures.

### 48.4. Capacity test

Test peak connection establishment/kms calls ở staging, nhưng không copy production secrets hoặc plaintext data vào test. Theo dõi resource/quota, retries và p99.

## 49. NoSQL backups, exports và dữ liệu nhạy cảm

Một NoSQL snapshot có thể chứa:

- Ciphertext và wrapped DEKs.
- Credentials vô tình được lưu làm dữ liệu.
- Old key version metadata.
- User access tokens/session objects.
- PII và audit records.

### 49.1. Encryption at rest không luôn đủ

Disk/server-side encryption bảo vệ một số đường mất thiết bị hoặc storage access; một principal có quyền đọc/decrypt snapshot vẫn có thể truy cập dữ liệu. IAM, backup policies và client-side encryption có vai trò riêng.

### 49.2. Đảm bảo restore dùng đúng key

Nếu backup được encrypt bằng KMS key khác production runtime, restore drill cần quyền, key retention và account/Region access đúng. Không tự sao chép key material giữa environments.

### 49.3. Export logs và database dumps

Một migration job ghi toàn bộ documents ra JSON files có thể đưa tokens/PII lên disk không được bảo vệ. Dùng encrypted staging, retention ngắn, RBAC và quy trình xóa sau khi hoàn tất.

### 49.4. Secret trong dữ liệu ứng dụng

Nếu ứng dụng lưu third-party API tokens của khách hàng trong MongoDB, chúng vẫn là secrets, không phải “dữ liệu bình thường” vì nằm trong database. Cần mã hóa phù hợp, tenant isolation, rotation và không query/log raw.

## 50. Phân biệt bảo vệ bí mật, bảo vệ truy cập và bảo vệ dữ liệu

| Lớp | Bảo vệ điều gì | Ví dụ |
|---|---|---|
| Secret management | Ai lấy credential, khi nào, phiên bản nào | Vault/secret manager, audit |
| Authentication | Client có danh tính gì | DB SCRAM, IAM, mTLS |
| Authorization | Client được phép làm gì | MongoDB roles, DynamoDB IAM, Redis ACL |
| Transport encryption | Dữ liệu trên đường truyền | TLS, mTLS |
| Storage encryption | Bản sao trên disk | Provider/server encryption at rest |
| Application encryption | Field nhạy cảm trước khi vào DB | Envelope encryption |
| Safe observability | Không xuất secrets/PII không cần thiết | Allowlist logs, sanitized traces |
| Operational lifecycle | Rotate/revoke/test/restore | Key versions, cutover, incident runbooks |

### 50.1. Không có một lớp thay thế mọi lớp khác

TLS không ngăn log password. Secret manager không ngăn superuser role có quyền xóa mọi collection. Encryption at rest không bảo vệ dữ liệu đã được API trả plaintext cho người không có quyền.

### 50.2. Bảo vệ end-to-end

Một thiết kế mạnh cần giữ nguyên nguyên tắc từ development, deployment, runtime, backup, monitoring tới incident response.

## 51. Checklist trước khi phát hành ứng dụng Java + NoSQL

### 51.1. Secret source

- Không có raw credentials trong Git, image, CI artifacts?
- Secret manager/workload identity cấp quyền tối thiểu?
- Dev/staging/prod tách secrets và roles?
- Có documented owner và rotation interval/threat-based triggers?

### 51.2. Runtime

- DB connection qua TLS với certificate verification?
- Không có credentials trong CLI args/URI log?
- SDK/driver refresh và pool lifecycle khi rotate đã rõ?
- Secret manager unavailable được xử lý theo policy?

### 51.3. Cryptography

- Phân biệt credential, KEK, DEK và signing keys?
- Encryption key IDs/versions lưu cùng ciphertext?
- Nonce/AAD/algorithm được thiết kế bằng thư viện tin cậy?
- Dual-read/single-write rotation và migration checkpoints?
- Backups còn decrypt được sau retire?

### 51.4. Logging và telemetry

- Log DTO allowlist, không stringify config/request bodies?
- Exception/stack trace/query logs được đánh giá?
- Headers/body/query params nhạy cảm không bị thu thập?
- Tracing baggage/metric labels không chứa secrets/PII?
- Log retention, RBAC, audit và exports được kiểm soát?

### 51.5. Tests và vận hành

- Secret scanner hoạt động trong CI?
- Synthetic secret leak tests bao gồm exception paths?
- Fresh connection canary sau rotation?
- Alert secret version drift, auth failure, key expiry?
- Runbook leak/compromise và manual correction có owner?

## 52. Bài tập 1 — phân loại dữ liệu bí mật

Một cấu hình dịch vụ chứa:

~~~text
mongodbHost: db.example.invalid
mongodbUsername: orders-reader
mongodbPassword: <SECRET>
awsRegion: ap-southeast-1
awsSessionToken: <SECRET>
kmsKeyId: alias/orders-key
plainDataEncryptionKey: <SECRET_BYTES>
certificateSerial: example-serial
tlsPrivateKey: <PRIVATE_KEY>
~~~

1. Những trường nào là secrets trực tiếp?
2. Những trường nào không phải raw secrets nhưng vẫn cần kiểm soát thông tin nội bộ?
3. Nếu chỉ được log databaseType, operationClass và credentialVersion, tạo một log JSON an toàn.
4. Vì sao base64-encode mongodbPassword không giải quyết vấn đề?
5. Nếu secret manager bị mất kết nối nhưng runtime còn credential hợp lệ, chính sách fail-open/fail-closed cần phụ thuộc điều kiện nào?

## 53. Bài tập 2 — tìm lỗi trong Java logging

Code:

~~~java
public record DbConfig(
        String uri,
        String username,
        String password
) {}

logger.debug("Connecting with {}", config);
~~~

1. Vì sao mặc định record toString() có thể làm lộ secret?
2. Nếu chuyển logger.debug thành logger.error, rủi ro thay đổi thế nào?
3. Vì sao Lombok @ToString.Exclude chưa đủ khi exception chứa URI?
4. Thiết kế SafeDbAuditEvent chỉ gồm fields được phép.
5. Viết một JUnit test dùng synthetic marker để kiểm tra không lộ trong rendered log object.

## 54. Bài tập 3 — URI và percent encoding

Ứng dụng dùng:

~~~text
mongodb+srv://<USER>:<PASSWORD_ENCODED>@cluster.example.invalid/orders
rediss://<USER>:<PASSWORD_ENCODED>@cache.example.invalid:6380
~~~

1. Vì sao percent-encoding password không làm URI an toàn để log?
2. Nếu log collector chỉ mask đoạn password=, có che được URI userinfo không?
3. Thiết kế method log safe metadata mà không cần parse raw secret-bearing URI.
4. Những chỗ nào ngoài Java app có thể log raw URL?
5. Nếu URI đã xuất hiện trong CI output, cần xử lý như secret leak thế nào?

## 55. Bài tập 4 — IAM và workload identity

Một service Java chỉ cần GetItem và Query trên DynamoDB table Orders và đọc một secret dùng cho hệ khác.

1. Vì sao nên ưu tiên workload identity/role thay cho AWS access key tĩnh trong code?
2. Đề xuất scope IAM tối thiểu cho DynamoDB table và secret ARN liên quan.
3. Tại sao DefaultCredentialsProvider không tự giới hạn quyền?
4. Nếu môi trường có environment static credentials quyền quá rộng, chuỗi provider có thể dùng chúng không?
5. Rotation của temporary credentials khác static key ở điểm nào?
6. Những dấu vết nào không nên log khi AWS SDK ký request?

## 56. Bài tập 5 — MongoDB rotation với pools

Hệ có 40 Java pods, mỗi pod một MongoClient và connection pool. Secret manager active password v7; muốn chuyển v8 không gián đoạn.

1. Vẽ thứ tự create candidate, validate, rollout, switch pool, revoke v7.
2. Vì sao không revoke v7 trước khi mọi pod có v8?
3. Tại sao chỉ nhìn query success trên existing connections chưa đủ?
4. Thiết kế fresh-auth canary.
5. Nếu 2 batch jobs đang offline, làm sao tránh chúng khởi động bằng v7 sau một tuần?
6. Đề xuất metrics về credentialVersion, auth failures và connection creation.
7. Khi v8 lỗi sau khi v7 đã revoke, nên emergency forward rotate hay tự khôi phục v7?

## 57. Bài tập 6 — Redis ACL và logging

Một hệ dùng một default Redis user với toàn quyền cho 10 services.

1. Blast radius nếu password bị lộ là gì?
2. Phác thảo cách chia ACL users theo service/operation và key pattern.
3. Nếu dùng rediss, còn cần certificate verification những gì?
4. Vì sao Redis MONITOR có thể làm lộ session tokens?
5. Khi rotate Redis credential, kiểm tra fresh client connection như thế nào?
6. Vì sao Redis key TTL không liên quan đến tuổi của ACL password?

## 58. Bài tập 7 — Cassandra service account

Một Java service chỉ đọc orders_by_customer nhưng đang dùng database admin role.

1. Thiết kế role/read grant phù hợp.
2. Secret manager giúp gì và không giúp gì nếu admin credential bị lấy?
3. Nếu ứng dụng dùng mTLS, cần quản lý thêm bí mật nào?
4. Sau khi CA đổi, cần update client trust store trước hay server certificate trước theo rollover plan?
5. Nếu CqlSession cũ còn hoạt động nhưng new connections fail, metric nào phát hiện?
6. Log các thông tin nào để điều tra lỗi TLS mà không xuất private key?

## 59. Bài tập 8 — envelope encryption

Một NoSQL document có:

~~~text
keyVersion=dek-v2
algorithm=AES-256-GCM
encryptedDEK=<ENCRYPTED_BYTES>
nonce=<NONCE_BYTES>
ciphertext=<CIPHERTEXT_BYTES>
~~~

1. DEK và KEK có vai trò khác nhau ra sao?
2. Wrapped DEK không phải plaintext DEK — vì sao?
3. Nếu chuyển ciphertext của tenant A sang tenant B, AAD giúp phát hiện như thế nào?
4. Vì sao nonce không được tái sử dụng với cùng key?
5. Nếu KMS quyền Decrypt bị thu hồi, app cần fail như thế nào?
6. Những metadata nào có thể log an toàn theo policy?

## 60. Bài tập 9 — rewrap hay re-encrypt?

Một ứng dụng giữ DEK v1 được wrap bởi KEK A. Nay muốn chuyển KEK A sang KEK B. Ở một tình huống khác, nghi ngờ plaintext DEK v1 đã bị lộ.

1. Khi chỉ đổi KEK, có thể rewrap mà giữ ciphertext data không?
2. Nếu DEK v1 đã lộ, rewrap-only có đủ không?
3. Re-encrypt làm phát sinh những chi phí nào?
4. Tại sao phải version ciphertext?
5. Nếu có 100 triệu documents, thiết kế batch migration/checkpoint thế nào?
6. Làm sao tránh ghi đè user update xảy ra giữa read và rewrite?

## 61. Bài tập 10 — key cũ và backup

Production đã migrate mọi records từ DEK v1 sang v3, nhưng snapshot sáu tháng trước vẫn chứa ciphertext v1.

1. Có nên hủy v1 ngay không?
2. Trước khi hủy key, cần inventory loại backups/archives nào?
3. Thiết kế restore drill với quyền phù hợp.
4. Nếu snapshot đã hết retention và được xác minh không còn, điều kiện nào giúp cân nhắc destroy?
5. Nếu data bị copy ra ngoài cùng với DEK v1 từ trước, key rotation hiện tại có đảo ngược exposure không?
6. Vì sao key ID được phép log khác raw key material?

## 62. Bài tập 11 — Spring Boot actuator

Team bật Actuator env/configprops trong production và cho mạng nội bộ xem tự do vì “mặc định đã mask”.

1. Vì sao không thể dựa vào mặc định của mọi Spring Boot versions?
2. Quyền truy cập, authentication và network exposure cần kiểm soát thế nào?
3. Một health endpoint an toàn có thể trả thông tin gì về MongoDB connection?
4. Có nên trả full exception message để debug auth failure không?
5. Khi incident cần heap dump, cách quản lý artifact nào giảm rủi ro?
6. Thiết kế test synthetic secret để kiểm tra dữ liệu không xuất hiện ở diagnostic output.

## 63. Bài tập 12 — logging filter không đủ

Một bộ filter masking nhận dạng:

~~~text
password=...
Authorization: Bearer ...
~~~

Nhưng một developer log:

~~~java
logger.info("Config JSON {}", objectMapper.writeValueAsString(config));
~~~

1. Vì sao regex có thể không bắt nested JSON password field?
2. Nếu password đã Base64-encode, filter có nhận ra không?
3. Thiết kế allowlist log DTO thay thế.
4. Vì sao filter ở collector chưa chắc bảo vệ console logs?
5. Dùng test marker giả để xác minh các sinks khác nhau.
6. Nếu tắt toàn bộ logging để pass test, mất thông tin chẩn đoán gì?

## 64. Bài tập 13 — OpenTelemetry và high-cardinality metrics

Một engineer gắn các attributes:

~~~text
db.operation = orders.insert
db.password = <SECRET>
enduser.email = <PERSONAL_EMAIL>
app.credential.version = v18
app.error.category = AUTH_FAILED
~~~

1. Field nào tuyệt đối không nên nằm trong trace?
2. Field nào có thể nhạy cảm/PII dù không phải password?
3. Field nào có thể dùng trong dashboard aggregate khi policy cho phép?
4. Vì sao trace sampling 1% không giải quyết leak?
5. Metric label gắn raw userId/secretId gây vấn đề gì?
6. Thiết kế span attributes allowlist cho một database auth failure.

## 65. Bài tập 14 — CI leak và rotation

Một developer vô tình commit application-prod.yml chứa MongoDB password, sau đó xóa line đó trong commit tiếp theo.

1. Tại sao secret vẫn có thể nằm trong Git history/forks/CI?
2. Hành động ưu tiên phải là xóa history hay revoke credential? Vì sao?
3. Những bản sao nào cần inventory?
4. Nếu logs chứa credential, cần áp retention/access restrictions thế nào?
5. Thêm secrets scanning và review check như thế nào?
6. Nếu sự cố liên quan superuser role, cần đánh giá DB audit ra sao?
7. Viết bản tường trình không copy plaintext password vào ticket.

## 66. Bài tập 15 — IAM secret-manager unavailable

Một service Java phụ thuộc secret manager để lấy password MongoDB. Sau sự cố mạng, một số instances đang chạy vẫn có valid credential, còn instances mới không khởi động được.

1. Định nghĩa fail-open/fail-closed theo workload/risk.
2. Cached secret trong memory cần TTL/maximum age và refresh behavior nào?
3. Có nên fallback sang password hardcode trong image không?
4. Có thể giữ existing connections hoạt động khi secret manager tạm không truy cập được không?
5. Khi rotation đã revoke old password, stale cached credential gây kết quả gì?
6. Dashboard cần phân biệt secret_refresh_failure và db_auth_failure ra sao?

## 67. Bài tập 16 — đồng thời user update và re-encrypt

Worker rotation đọc document v10 để re-encrypt field contactEncrypted. User request đồng thời cập nhật contactEncrypted thành v11.

1. Nếu worker replace toàn document snapshot v10, rủi ro gì?
2. Thiết kế update-if-version=10 hoặc compare current ciphertext metadata.
3. Nếu CAS fail, worker làm gì?
4. Vì sao không thể chỉ dựa vào createdAt để biết key version?
5. Nếu v11 đã dùng DEK mới, worker có cần re-encrypt lại v11 không?
6. Theo dõi migration conflict/retry counts thế nào mà không log ciphertext?

## 68. Bài tập 17 — rotation canary và rollback

Một đội vận hành có:

~~~text
Credential v17: active, 100 pods use it.
Credential v18: candidate.
Rotation window: 30 minutes.
Batch jobs: some run only once per day.
~~~

1. Liệt kê inventory consumers cần thu thập trước.
2. Thiết kế fresh-auth test và query permission test.
3. Chọn rollout waves và metrics.
4. Điều kiện nào cho phép revoke v17?
5. Nếu v18 auth thất bại khi v17 còn sống, rollback an toàn thế nào?
6. Nếu nghi ngờ v17 bị compromise, thứ tự ưu tiên thay đổi ra sao?
7. Vì sao batch job offline có thể phá rotation success?

## 69. Bài tập 18 — rò log ở nhiều tầng

Một request admin khiến application phát ra:

~~~text
App stdout: MongoDB URI with credentials
Collector: ingests stdout
Dashboard: searchable for 30 days
Alert email: includes offending log line
Archive: stores immutable logs for one year
~~~

1. Secret tồn tại ở bao nhiêu nơi?
2. Nếu xóa dashboard record, nguy cơ đã hết chưa?
3. Lập kế hoạch immediate revoke/rotate.
4. Lập inventory những nhóm người đã có khả năng xem.
5. Các dữ liệu cần giữ cho incident investigation là gì?
6. Thiết kế quy trình xử lý archives và alert email theo policy.
7. Nêu một regression test chặn phát ra URI chứa userinfo.

## 70. Bài tập 19 — thực hiện audit secrets và keys

Bạn cần audit một service gồm:

~~~text
MongoDB: username/password
Redis: ACL password
DynamoDB: IAM role
Data encryption: KMS KEK + DEK per tenant
Tracing: OpenTelemetry
Logs: centralized
Backups: weekly snapshots
~~~

Hãy tạo bảng:

1. Secret/key nào được dùng và ai là owner?
2. Nơi cấp, quyền lấy và thời hạn hiệu lực?
3. Consumers/connection pools nào giữ credential?
4. Rotation theo version/overlap/failover thế nào?
5. Dữ liệu/bản sao nào cần khóa cũ khi restore?
6. Logs/traces/metrics có thể rò secret qua trường nào?
7. Những alerts và tests nào chứng minh policy còn hiệu lực?
8. Quyết định emergency revoke so với availability của từng secret class.

## 71. Bài tập 20 — thiết kế kiến trúc bảo mật tổng thể

Một nền tảng SaaS đa tenant chạy Java trên Kubernetes. MongoDB giữ Orders, Redis cache Sessions, DynamoDB giữ idempotency claims, KMS dùng mã hóa trường contact.

Yêu cầu thiết kế:

1. Workload identity và IAM cho từng service.
2. Nguồn secret và runtime injection, không hardcode.
3. TLS/auth/ACL theo từng NoSQL backend.
4. Quy trình luân chuyển database password, Redis ACL, client certificate.
5. Envelope encryption metadata và AAD để bảo vệ tenant.
6. Data key version, dual-reader/single-writer rollout, rewrap/re-encrypt.
7. Phương án migration không ghi đè user updates.
8. Phương án decrypt/restore backups lịch sử.
9. Safe logging design cho Java, gateway, tracing, database profiler.
10. Synthetic secret leak tests và Git/CI scanning.
11. Dashboard rotation state, auth failures, KMS errors và deprecated key versions.
12. Incident response khi một credential và một plaintext DEK bị lộ đồng thời.

## 72. Tổng kết

**Quản lý bí mật trong hệ NoSQL không dừng ở việc giấu password trong một file cấu hình.** Bí mật có vòng đời từ cấp phát, lưu trữ, sử dụng, luân chuyển tới thu hồi; khóa mã hóa còn ràng buộc với dữ liệu lịch sử và backups; logging có thể tạo thêm bản sao ngoài tầm kiểm soát nếu không được thiết kế an toàn.

Những nguyên tắc quan trọng:

1. **Xác định đúng loại secret.** Database password, token, access key, mTLS private key, DEK và KEK có mục đích, phạm vi và quy trình rotation khác nhau.
2. **Ưu tiên workload identity và secret manager.** Hạn chế static credentials, audit quyền đọc, tách dev/staging/prod và cấp least privilege.
3. **Không hardcode hoặc đưa secrets vào artifacts.** Git, Docker layers, CI output, IaC state và developer machines đều là nơi cần bảo vệ.
4. **TLS, authentication và authorization là các lớp riêng.** Secret manager không biến một superuser credential thành an toàn, và TLS không ngăn ứng dụng log password.
5. **Credential rotation cần hai giai đoạn sử dụng old/new có kiểm soát.** Tạo credential mới, thử fresh-auth, roll out client pools, xác nhận hoạt động rồi thu hồi old; khi compromise, có thể phải emergency revoke.
6. **Đổi DB password không đổi encryption key.** Đừng trộn credential rotation với DEK/KEK lifecycle và data re-encryption.
7. **Envelope encryption cần metadata rõ.** Lưu key version, encrypted DEK, algorithm, nonce, authentication tag và AAD contract; dùng crypto primitives/SDK được review.
8. **Rewrap khác re-encrypt.** Đổi KEK có thể không cần encrypt lại data; lộ DEK thường đòi đổi DEK và xử lý các ciphertext bị ảnh hưởng.
9. **Key rotation cần backward-read compatibility.** Readers hiểu cả key cũ/mới trước khi writers chuyển; migrations có checkpoint, CAS và kiểm tra data consistency.
10. **Không hủy key cũ quá sớm.** Records lịch sử và backups còn có thể cần decrypt; restore drills và retention quyết định ngày retire/destroy.
11. **Không log raw secrets ở bất kỳ level nào.** SLF4J placeholders, Java toString, stack traces, URL, full HTTP request, debugger và driver command logging đều có thể rò.
12. **Allowlist logging tốt hơn blacklist regex.** Chỉ phát những fields cần chẩn đoán; filter/masking tại collector là defense in depth.
13. **Logs, traces và metrics là dữ liệu có quyền truy cập.** Hạn chế PII, high-cardinality labels, raw query, Authorization headers, tracing baggage và secret-manager payloads.
14. **Instrument việc luân chuyển bằng metadata.** Credential version, fresh-auth success, expiration, deprecated-key counts, KMS error categories và audit đủ cho vận hành mà không lộ key material.
15. **Kiểm thử rò rỉ bằng synthetic markers.** Bao gồm error paths, CI, collector, Actuator và driver logging; không dùng production secret làm test fixture.
16. **Khi lộ credential, ưu tiên thu hồi/rotate và điều tra phạm vi.** Xóa một dòng log hoặc một commit không loại bỏ các bản sao đã phát tán.
17. **Khi lộ DEK, hậu quả có thể tồn tại với ciphertext cũ.** Cần đánh giá scope, re-encrypt phù hợp và incident response chứ không chỉ đổi alias.
18. **Bảo mật và khả dụng phải được cân bằng có chủ đích.** Graceful overlap tốt cho rotation thông thường; emergency incident có thể cần cắt quyền ngay và chấp nhận gián đoạn được kiểm soát.

Câu hỏi thiết kế cuối cùng:

> **“Bí mật và khóa này đang được ai dùng, ở đâu có bản sao, nó có thể bị đưa vào log/backup hay không; khi phải luân chuyển hoặc thu hồi ngay, làm thế nào vừa giới hạn người có quyền vừa không làm mất khả năng đọc dữ liệu hợp lệ?”**









