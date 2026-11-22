# Lỗi xác thực, quyền, TLS và chứng thư hết hạn trong Apache Cassandra

## 1. Vấn đề và mục tiêu xử lý sự cố

Ứng dụng Java có thể gặp lỗi kết nối Apache Cassandra dù `nodetool status` báo các node `UN`, ổ đĩa còn dung lượng và CQL đọc/ghi không có vấn đề hiệu suất. Các sự cố bảo mật thường nằm **trước hoặc ở ranh giới thực thi CQL**: handshake TLS không hoàn tất, chứng thư không được tin cậy, thông tin đăng nhập không hợp lệ, role không đủ quyền hoặc chứng thư hết hạn.

Trong chương **Xử lý sự cố** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, bài này hướng tới việc phân loại và xử lý có căn cứ các sự cố liên quan đến:

1. **Authentication** — client có chứng minh được mình là role/user hợp lệ không?
2. **Authorization** — role đã xác thực có quyền thực thi câu CQL đó không?
3. **TLS** — client và server có xây dựng được kênh mã hóa, xác minh được danh tính peer không?
4. **Certificate validity** — chuỗi CA, tên máy chủ, hạn dùng, mục đích sử dụng và thời gian có hợp lệ không?
5. **Java Driver 4.x** — exception ở tầng driver, root cause trong `AllNodesFailedException.getAllErrors()` và cách log an toàn.
6. **Phạm vi sự cố** — một node, một DC, một nhóm pod, một phiên bản ứng dụng hay toàn bộ cluster?
7. **Khôi phục an toàn** — rollback/rotate certificate, cập nhật truststore, phục hồi role/permissions theo thay đổi có kiểm soát.
8. **Phòng ngừa** — thời hạn chứng thư, dry-run rotation, thử nghiệm failover, logging tối thiểu và runbook.

Apache Cassandra là hệ phân tán wide-column; **partition key**, thiết kế bảng theo truy vấn, replication, consistency level, compaction và repair tiếp tục ảnh hưởng khả năng phục vụ sau khi sửa lỗi bảo mật. Tuy nhiên **lỗi TLS/role không được chữa bằng cách hạ consistency level, mở `ALLOW FILTERING` hay tăng retry vô hạn**.

> **Nguyên tắc ưu tiên:** giữ nguyên xác minh TLS và phân quyền tối thiểu. Không vô hiệu hóa hostname verification, bỏ kiểm tra certificate, bật anonymous access hoặc chia sẻ tài khoản admin để “làm API chạy lại”.

### 1.1. Một tình huống tiêu biểu

Sau đợt thay chứng thư CA, một nửa pod Java mới triển khai trả HTTP 503; pod cũ vẫn đọc Cassandra được. Dashboard có `AllNodesFailedException`, nhưng `nodetool status` hiển thị các node `UN`. Nguyên nhân có thể là **truststore của pod mới không chứa CA cần thiết** hoặc chain server không đúng, chứ không nhất thiết Cassandra down hay mất replica.

Một tình huống khác: ứng dụng đăng nhập, `SELECT` chạy thành công nhưng `INSERT` bị từ chối. Đây thường là **authorization**, không phải TLS: role có quyền `SELECT` nhưng không có quyền `MODIFY` trên table đích.

### 1.2. Không nhầm bảo mật với consistency

| Nhóm vấn đề | Câu hỏi chính | Ví dụ |
|---|---|---|
| TLS transport | Có xác minh được peer và thiết lập kênh mã hóa? | `SSLHandshakeException`, PKIX |
| Authentication | Server có xác nhận role/client identity? | Sai password, role `LOGIN=false` |
| Authorization | Role có quyền với resource/statement? | Thiếu `MODIFY` |
| Cassandra availability | Đủ replica đáp ứng CL? | `UnavailableException` |
| Cassandra latency | Replica/coordinator phản hồi kịp deadline? | `ReadTimeoutException` |
| Java driver/connectivity | Có coordinator candidate khả dụng? | `AllNodesFailedException` |
| Data modeling | Query hợp lệ và hiệu quả theo partition key? | Query thiếu partition key |

**Không quy mọi lỗi trong `AllNodesFailedException` thành “cluster DOWN”.** Cần đọc cause của từng coordinator candidate.

## 2. Bản đồ các đường kết nối bảo mật

~~~mermaid
flowchart LR
    A["Java service / cqlsh"] -->|"Native CQL / TLS"| B["Cassandra coordinator"]
    B -->|"Internode messages / TLS theo cấu hình"| C["Replica node khác"]
    D["nodetool / operator"] -->|"JMX auth/TLS (riêng)"| B
    E["Monitoring/JMX exporter"] -->|"JMX hoặc exporter endpoint"| B
    F["Secret manager/PKI"] -.->|"CA, cert, truststore, credentials"| A
    F -.->|"node certificates"| B
    F -.->|"node certificates"| C
~~~

Cần phân biệt **ít nhất ba mặt phẳng**:

- **Client-to-node native transport:** Java Driver, cqlsh, các service kết nối CQL; thường dùng cổng native transport như `9042` theo cấu hình, có thể đổi hoặc tách TLS port tùy phiên bản.
- **Node-to-node internode transport:** các node Cassandra trao đổi replica messages, gossip/streaming theo loại kết nối và cấu hình mã hóa tương ứng.
- **JMX/management:** `nodetool` và agent vận hành kết nối qua JMX hoặc endpoint quản lý; có xác thực, TLS, port và quyền **khác** với user CQL.

**Một phép thử `nodetool status` thành công không chứng minh Java driver TLS/role hoạt động.** Tương tự, cqlsh kết nối CQL thành công không tự chứng minh internode TLS ở các DC đang khỏe.

### 2.1. Xác thực peer có thể diễn ra theo những cơ chế khác nhau

- **Server authentication trong TLS:** client xác minh server certificate theo trust anchors và tên host.
- **Cassandra CQL authentication:** username/password hoặc auth provider được cấu hình; có thể diễn ra **trên kênh TLS** khi TLS được bật.
- **Mutual TLS (mTLS):** server cũng xác minh client certificate khi được yêu cầu.
- **JMX authentication:** có thể dùng cơ chế credential/SSL khác, không tự suy ra từ role Cassandra.

Cơ chế xác thực/ủy quyền nào được hỗ trợ còn phụ thuộc Cassandra release, bản phân phối và cấu hình plugin. Không suy “đã có client certificate thì không cần role/password CQL” nếu server chưa được cấu hình tích hợp ánh xạ identity như vậy.

### 2.2. Các trạng thái có thể cùng xuất hiện

| Native TLS | CQL auth | CQL authorization | Kết quả |
|---|---|---|---|
| Lỗi handshake | Chưa bắt đầu/không tới được | Chưa xét | Client không có CQL session |
| Thành công | Sai credentials | Chưa xét | Authentication failure |
| Thành công | Thành công | Thiếu `SELECT` | Một `SELECT` bị từ chối |
| Thành công | Thành công | Đủ quyền | CQL mới được kiểm tra query/schema/CL |
| Thành công | Thành công | Đủ quyền | Vẫn có thể timeout/unavailable do replica |

Bảng này là **mô hình chẩn đoán**, không khẳng định mọi driver/server version phát lỗi cùng class hoặc cùng lúc.

## 3. Quy trình triage 5 phút đầu tiên

Khi báo động “Java service không vào Cassandra”, đừng thay chứng thư hoặc cấp admin ngay. Thu bằng chứng tối thiểu:

1. **Ảnh hưởng người dùng:** read, write hay cả hai? Bao nhiêu request thất bại, từ thời điểm nào?
2. **Phạm vi client:** một pod, namespace, app version, region hay tất cả service?
3. **Phạm vi node:** một coordinator candidate, một rack/DC hay mọi contact point?
4. **Class và root cause:** TLS handshake, authentication, authorization, timeout, DNS hay network?
5. **Change timeline:** vừa rotate certificate, CA, password/secret, driver, JDK, DNS, firewall, RBAC hay server config?
6. **Dữ liệu an toàn:** query template ID, UTC time, request correlation ID, fingerprint/serial được phép chia sẻ, node/DC.
7. **Tình trạng cluster:** `nodetool status`, native transport errors, server logs có quyền, latency/CPU/GC/disk.
8. **Guardrails:** giảm retry storm; không hạ TLS/CL/quyền hoặc ghi secret vào ticket.

### 3.1. Ma trận suy luận ban đầu

| Dấu hiệu | Khả năng nổi bật | Bước kế |
|---|---|---|
| Tất cả request của pod mới lỗi TLS | Truststore/JDK/chain/hostname khác | So config và certificate chain |
| Chỉ node A gây handshake failures | Cert/key/chain/SAN ở A sai hoặc hết hạn | Kiểm tra A và đường mạng tới A |
| `AuthenticationException`, TLS kết nối được | Credentials, role LOGIN, authenticator mismatch | Kiểm tra role/secret/auth config |
| `UnauthorizedException` khi INSERT | Role thiếu MODIFY | Kiểm tra grants theo table |
| Node status `UN` nhưng app không kết nối | Client→node network/TLS/auth | Test từ đúng app network |
| cqlsh trên node chạy, pod không chạy | Truststore/DNS/hostname/NAT/policy | So hostnames và CA của client |
| Lỗi sau JDK upgrade | Disabled algorithms/truststore/cipher/protocol | So JDK security policy |
| Cert còn hạn nhưng lỗi PKIX | CA chain/trust anchor không đúng | Kiểm tra issuer/chain/intermediates |
| Chỉ lỗi khi IP được thay bằng DNS | SAN/hostname verification | So contact points và SAN |
| Xảy ra đúng ngày cert hết hạn | NotAfter/clock skew/secret chưa rollout | Lập phương án rotate/rollback |
| Lỗi `Unavailable` khi node down | RF/CL/replica availability | Điều tra topology, không sửa cert |
| p99 tăng sau sửa TLS | Connection churn, handshake/GC/CPU hoặc backend load | Đo lại driver/node metrics |

**Thứ tự xử lý:** lớp thất bại sớm nhất trong connection/request lifecycle trước. Không sửa CQL nếu handshake chưa hoàn tất; không sửa grants nếu role vẫn chưa đăng nhập thành công.

## 4. Phân biệt authentication và authorization

### 4.1. Authentication: bạn là ai?

Cassandra có thể được cấu hình với `PasswordAuthenticator` và cơ chế role management tương ứng. Trên cluster hỗ trợ CQL role authentication, role đăng nhập cần có:

- Identity/role tồn tại.
- Thuộc tính **`LOGIN=true`** nếu role được dùng để login.
- Credential/auth mechanism đúng.
- Kết nối đến cluster/keyspace chính xác.
- Cơ chế authenticator trên server thực sự bật và đồng nhất.

Authentication xảy ra trước khi permission của câu query được kiểm tra. Sai username/password thường làm cả SELECT/INSERT đều thất bại khi session mở hoặc authenticate.

**Bảo mật vận hành:** không đưa mật khẩu vào command line có thể bị ghi vào shell history/process list; không in password dưới dạng log, exception detail hoặc tracing.

### 4.2. Authorization: bạn được phép làm gì?

Sau khi role đăng nhập thành công, `CassandraAuthorizer` hoặc authorizer/plugin được cấu hình đánh giá quyền trên resource (keyspace/table/role). Các quyền CQL thường gặp:

| Permission | Ví dụ thao tác | Lưu ý |
|---|---|---|
| `SELECT` | Đọc table/row | Có thể cấp trên table/keyspace theo tài nguyên |
| `MODIFY` | INSERT/UPDATE/DELETE | Không đồng nghĩa quyền ALTER/DROP schema |
| `CREATE` | Tạo resource phù hợp | Thường không cấp role runtime |
| `ALTER` | Sửa schema/resource | Chỉ cho migration/admin |
| `DROP` | Xóa resource | Quyền nhạy cảm |
| `AUTHORIZE` | Quản lý grants | Không cấp ứng dụng bình thường |
| `DESCRIBE` và quyền khác | Tùy version/resource | Kiểm tra release CQL reference |

Cassandra authorizer mặc định hoặc bản phân phối có thể khác; nếu đang dùng `AllowAllAuthorizer`, phân quyền theo role không được cưỡng chế như `CassandraAuthorizer`. **Không coi việc gọi GRANT thành công là bằng chứng policy đang được thực thi**, phải test cả thao tác bị từ chối.

### 4.3. Không sửa unauthorized bằng cách cấp quyền rộng

Một ứng dụng chỉ cần ghi vào một bảng không nên được cấp `ALL PERMISSIONS ON ALL KEYSPACES`. Thay vào đó:

~~~cql
-- CQL minh họa, chạy bằng role quản trị được phê duyệt.
GRANT SELECT ON TABLE telemetry_lab.readings_by_device_day
TO telemetry_reader;

GRANT MODIFY ON TABLE telemetry_lab.readings_by_device_day
TO telemetry_writer;

-- Xem quyền hiệu lực theo release/cơ chế authorizer.
LIST ALL PERMISSIONS OF telemetry_reader;
LIST ALL PERMISSIONS OF telemetry_writer;
~~~

Các role `telemetry_reader`/`telemetry_writer` giả định đã được provisioning an toàn. Cú pháp và khả năng liệt kê inherited permissions phụ thuộc Cassandra version/authorizer; cần kiểm tra output thực của release.

### 4.4. Role hierarchy không thay thế kiểm tra tenant

Một role Cassandra có quyền `SELECT` trên cả table **không tự giới hạn** được row thuộc tenant nào. Nếu nhiều tenant cùng bảng, ứng dụng còn phải:

- Xác thực principal của request.
- Xác minh quyền/ownership tenant.
- Xây dựng partition key có tenant dimension nếu phù hợp.
- Bind tenant từ context đáng tin cậy, không chỉ lấy raw route/query parameter.
- Tránh lộ dữ liệu qua logging/metrics.

**CQL bind parameters chống nối giá trị tùy tiện nhưng không giải quyết authorization nghiệp vụ.**

## 5. TLS handshake: thất bại ở bước nào?

~~~mermaid
sequenceDiagram
    participant C as Java Driver
    participant S as Cassandra native transport
    C->>S: TCP connection
    C->>S: TLS ClientHello (protocol/ciphers/SNI)
    S-->>C: ServerHello + certificate chain
    C->>C: Trust chain, validity, hostname, key usage
    opt mTLS được yêu cầu
        S->>C: CertificateRequest
        C->>S: Client certificate + proof
        S->>S: Verify client cert/chain
    end
    C-->>S: TLS handshake complete
    C->>S: CQL native protocol + authentication
    S-->>C: Auth success/failure
    C->>S: CQL statement
    S-->>C: Authorized result or Unauthorized
~~~

Đây là sơ đồ logic rút gọn; thứ tự messages cụ thể khác giữa TLS 1.2 và 1.3, driver, server và mTLS. Điều quan trọng để chẩn đoán:

- **TCP refused/reset**: chưa tới handshake, kiểm network/firewall/listener.
- **Protocol/cipher mismatch**: không thống nhất TLS version/cipher, thường handshake failure.
- **Unknown CA/PKIX**: client không xây được chain từ server cert tới trust anchor được tin cậy.
- **Hostname mismatch**: certificate không phù hợp DNS/IP mà driver xác minh.
- **Expired/not-yet-valid**: validity interval không phù hợp thời điểm kiểm chứng.
- **Client certificate required/invalid**: mTLS không cung cấp được cert/key/chain phù hợp.
- **Auth rejected**: TLS có thể đã thành công, nhưng CQL credentials/role không hợp lệ.
- **Unauthorized**: auth thành công nhưng thiếu permission trên resource.

### 5.1. TLS không tự bảo đảm authorization

Một kênh TLS với certificate hợp lệ chỉ nói rằng các bên xác minh peer theo chính sách. Nó không có nghĩa Java role mặc định có quyền `ALTER KEYSPACE`, và cũng không ngăn một app dùng role hợp lệ truy cập tenant khác nếu business authorization thiếu.

### 5.2. Các kết quả lỗi có thể bị bọc

Trong Java Driver, một handshake exception có thể là **cause bên trong** `AllNodesFailedException` hoặc connection initialization failure. Đừng chỉ lấy outer class rồi dừng điều tra. Cần xem cause theo node, với logging được giới hạn để không rò secret/host topology.

## 6. Hiểu chứng thư X.509 và truststore

### 6.1. Những trường cần kiểm tra

| Trường/khái niệm | Vai trò | Lỗi điển hình |
|---|---|---|
| `Subject` | Thông tin chủ thể của certificate | Không đủ thay SAN để hostname validation |
| `Subject Alternative Name (SAN)` | DNS/IP names được chứng thư bảo vệ | Connect IP nhưng cert chỉ có DNS SAN |
| `Issuer` | CA phát hành cert | Thiếu intermediate/trust root |
| `NotBefore` | Mốc bắt đầu hiệu lực | Cert chưa tới ngày hiệu lực |
| `NotAfter` | Mốc kết thúc hiệu lực | Cert hết hạn |
| `Extended Key Usage (EKU)` | Ví dụ TLS serverAuth/clientAuth | Cert dùng sai mục đích |
| `Key Usage` | Khả năng dùng key theo profile | Key usage không phù hợp |
| `Public key / algorithm` | Thuật toán và độ dài khóa | Policy JDK không chấp nhận |
| `Signature algorithm` | Thuật toán ký chứng thư | Bị JDK/FIPS/security policy chặn |
| `Certificate chain` | Leaf → intermediate → root CA | Thiếu intermediate hoặc root không tin |
| `Serial/fingerprint` | Định danh cert trong incident | Cần so đúng cert đã rollout |

**Truststore** chứa trust anchors/certificates được client tin cậy; **keystore** có thể chứa private key và certificate chain của client/node khi thực hiện TLS/mTLS. Không đưa private key vào truststore “cho chắc”, không commit keystore chứa secret.

### 6.2. Chứng thư còn hạn vẫn có thể không được tin

Ví dụ:

~~~text
Leaf:        cassandra-1.dc1.example.internal
Issuer:      Intermediate-CA-2026
NotAfter:    2027-02-01

Client truststore chỉ chứa:
    OldRoot-CA

Server gửi:
    Leaf
    (thiếu Intermediate-CA-2026)

Kết quả:
    Có thể báo PKIX path building failed
    dù Leaf chưa hết hạn.
~~~

Cần xác minh **chain và trust anchors**, không chỉ nhìn ngày hết hạn.

### 6.3. Hostname verification và IP SAN

Nếu ứng dụng dùng contact point `10.10.4.12` nhưng certificate chỉ có DNS SAN `cassandra-1.dc1.example.internal`, việc xác minh IP có thể fail. Cách khắc phục:

- Dùng DNS name **được certificate bảo vệ** và có DNS/routing ổn định; hoặc
- Cấp certificate có IP SAN phù hợp nếu thật sự phải kết nối bằng IP; và
- Kiểm tra driver/node discovery dùng địa chỉ nào sau contact point.

**Không** tắt hostname verification như biện pháp sửa lỗi production. Trong Cassandra, driver có thể khám phá peer addresses khác contact points ban đầu, nên certificate/name policy phải khớp **mọi endpoint mà driver có thể kết nối**.

## 7. Lỗi chứng thư hết hạn và đồng hồ lệch

### 7.1. Hai điều kiện về thời gian

Với certificate:

~~~text
NotBefore: 2026-10-01T00:00:00Z
NotAfter:  2026-11-30T00:00:00Z

Tại 2026-11-21:
  Hợp lệ về thời gian (nếu các kiểm tra khác pass).

Tại 2026-12-01:
  Hết hạn.

Nếu clock client/server lệch mạnh:
  Có thể thấy expired hoặc not-yet-valid
  ngay cả khi một máy khác kết nối thành công.
~~~

Đây là ví dụ về interval; certificate còn cần CA chain, name, EKU, algorithm policy và các điều kiện khác.

### 7.2. Clock UTC và timezone hiển thị

Certificate validity thường được biểu diễn bằng mốc tuyệt đối. Người trực on-call có thể nhìn giờ local, nhưng phải so dưới cùng chuẩn **UTC** hoặc đổi có kiểm chứng. Lưu incident timeline dưới UTC và timezone hiển thị rõ; đừng thay múi giờ của JVM để “kéo dài” certificate.

### 7.3. Không sửa certificate expiry bằng cách dịch đồng hồ

**Không** chỉnh thời gian hệ điều hành Cassandra node hoặc Java pod để qua qua `NotAfter`. Clock skew có thể ảnh hưởng:

- TLS validity, certificate rotation và authentication.
- Cassandra write timestamps/reconciliation, TTL và LWT.
- Hints/repair/log timelines.
- Token/cluster maintenance diagnostics.
- Các hệ thống khác trên cùng host.

Cần **certificate renewal/rotation** đúng chain và SAN, đồng bộ thời gian bằng NTP/chrony hoặc hệ thống được phê duyệt.

## 8. Nhận diện exception theo tầng trong Java Driver 4.x

### 8.1. Outer exception và root cause

| Java/server signal | Tầng điều tra | Không nên suy ra |
|---|---|---|
| `SSLHandshakeException` | TLS negotiation/verification | Cassandra data lost |
| `CertificateExpiredException` | Cert ngoài NotAfter theo validation | Password sai |
| `CertificateNotYetValidException` | Cert chưa đến NotBefore/clock | Hết hạn theo giờ local chắc chắn |
| `ValidatorException`, `PKIX path building failed` | Trust chain/CA | Cert nhất định đã hết hạn |
| `SSLPeerUnverifiedException` / hostname mismatch | SAN/identity verification | Firewall lỗi |
| `AuthenticationException` | CQL auth/role/credentials | Thiếu table SELECT |
| `UnauthorizedException` | CQL permission/authorizer | TLS handshake lỗi |
| `AllNodesFailedException` | Driver không dùng được coordinator candidates | Mọi physical replica DOWN |
| `DriverTimeoutException` | Driver request deadline | CQL permission chắc chắn lỗi |
| `ReadTimeoutException` / `UnavailableException` | Replica/CL/server path | Cần rotate TLS certificate |

Tên class/package và nesting tùy driver major/minor, JDK và Cassandra version. Một số lỗi handshake có thể xuất hiện qua `CompletionException` khi dùng async API; phải unwrap tầng Future đúng trước khi phân loại.

### 8.2. Nguyên tắc xử lý exception

Không bao giờ:

~~~java
// ANTI-PATTERN: biến mọi lỗi Cassandra thành dữ liệu rỗng.
try {
    return loadReadings();
} catch (RuntimeException error) {
    return java.util.List.of();
}
~~~

Một query thành công và trả 0 row khác hoàn toàn TLS/auth/permission failure. Handler cần giữ outcome rõ: `SUCCESS_EMPTY`, `AUTH_FAILURE`, `PERMISSION_DENIED`, `TRANSPORT_TLS_FAILURE`, `TIMEOUT` và `UNAVAILABLE` theo error contract của ứng dụng.

### 8.3. Kiểm tra loại lỗi thay vì parse message làm logic nghiệp vụ

Certificate errors từ JDK thường có nested classes/message khác nhau theo version/language. Tránh:

~~~java
// ANTI-PATTERN: không ổn định giữa JDK/driver versions.
if (error.getMessage().contains("PKIX")) {
    retryForever();
}
~~~

Chủ yếu dùng **exception type/cause chain** và structured logging. Một TLS trust failure thường là cấu hình **permanent cho phiên bản pod hiện tại**, retry vô hạn chỉ tạo handshake storm.

## 9. `AllNodesFailedException.getAllErrors()`: lỗi theo coordinator, không phải replica ACK

### 9.1. Đọc map đúng ý nghĩa

Trong Java Driver 4.x, `AllNodesFailedException.getAllErrors()` cung cấp thông tin theo **coordinator candidate** và danh sách Throwable mà driver ghi nhận. Nó **không** phải bản đồ cho biết replica nào đã apply mutation hay toàn bộ node đang DOWN.

~~~text
AllNodesFailedException
  node A -> SSLHandshakeException
            -> PKIX path building failed
  node B -> SSLHandshakeException
            -> CertificateExpiredException
  node C -> connection initialization error

Đúng: không ứng viên coordinator nào được thử phục vụ được request.
Sai: cả cluster mất dữ liệu hoặc write trước đó chắc chắn rollback.
~~~

### 9.2. Ví dụ Java Driver 4.x

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.metadata.Node;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public final class FailureInspector {
    private FailureInspector() {}

    public static Throwable unwrapFuture(Throwable throwable) {
        Throwable current = throwable;
        for (int i = 0; i < 8; i++) {
            if ((current instanceof CompletionException
                    || current instanceof ExecutionException)
                    && current.getCause() != null) {
                current = current.getCause();
            } else {
                return current;
            }
        }
        return current;
    }

    public static void inspect(Throwable failure) {
        Throwable root = unwrapFuture(failure);
        if (!(root instanceof AllNodesFailedException all)) {
            emit("failure", root.getClass().getSimpleName(),
                "no_per_node_map");
            return;
        }

        Map<Node, List<Throwable>> errors = all.getAllErrors();
        emit("all_nodes_failed", "AllNodesFailedException",
            "node_entries=" + errors.size());

        errors.forEach((node, causes) -> {
            String dc = node.getDatacenter();
            for (Throwable cause : causes) {
                emit("coordinator_candidate_failure",
                    unwrapFuture(cause).getClass().getSimpleName(),
                    dc == null ? "unknown_dc" : dc);
            }
        });
    }

    private static void emit(
            String event, String errorClass, String safeTag) {
        // Structured logging/metrics có sampling và rate limit.
        // Không ghi secrets, raw bind values hoặc private keys.
    }
}
~~~

Mã sử dụng pattern matching `instanceof` nên cần JDK tương thích. Type `Node` và chữ ký phương thức phải đối chiếu với artifact Java Driver đang dùng. `getAllErrors()` có thể có **nhiều Throwable cho mỗi node**; không coi số entry là số replica chưa trả ACK.

### 9.3. Duyệt cause chain để nhận biết lỗi chứng thư

~~~java
import javax.net.ssl.SSLHandshakeException;
import java.security.cert.CertificateExpiredException;
import java.security.cert.CertificateNotYetValidException;
import java.util.IdentityHashMap;
import java.util.Map;

public static String classifyTls(Throwable failure) {
    Map<Throwable, Boolean> seen = new IdentityHashMap<>();
    boolean handshake = false;

    for (Throwable t = failure;
         t != null && !seen.containsKey(t);
         t = t.getCause()) {
        seen.put(t, Boolean.TRUE);

        if (t instanceof CertificateExpiredException)
            return "CERT_EXPIRED";
        if (t instanceof CertificateNotYetValidException)
            return "CERT_NOT_YET_VALID";
        if (t instanceof SSLHandshakeException)
            handshake = true;
    }
    return handshake ? "TLS_HANDSHAKE_FAILURE" : "OTHER";
}
~~~

Đây là **classifier minh họa**, không thể nhận mọi kiểu PKIX/SAN/cipher/JDK security error. Nếu thấy `TLS_HANDSHAKE_FAILURE`, phải kiểm tra chi tiết truststore, chain, EKU, hostname, mTLS và protocol. Không tự suy mọi SSLHandshakeException là expired cert.

### 9.4. Retry và tính đúng

Handshake fail do CA/SAN/expiry là lỗi **khó tự hồi phục khi config chưa thay đổi**. Retry vô hạn tạo handshake storm, tăng CPU/network và che nguyên nhân. Fail fast có phân loại; chỉ retry bounded nếu có bằng chứng transient network, deadline và retry budget.

Với CQL write đã gửi, timeout khác TLS fail trước request: kết quả mutation có thể không chắc chắn. Không coi `AllNodesFailedException` của một request là bằng chứng dữ liệu đã được rollback.

## 10. Chẩn đoán certificate bằng `openssl`

### 10.1. Kiểm tra từ cùng mạng với ứng dụng lỗi

Dùng một endpoint mẫu không tồn tại để minh họa, **chỉ áp dụng trên hạ tầng được phép**:

~~~bash
openssl s_client \
  -connect cassandra-1.example.invalid:9042 \
  -servername cassandra-1.example.invalid \
  -showcerts -verify_return_error \
  </dev/null
~~~

`-connect` là TCP endpoint, `-servername` cung cấp SNI. **SNI không phải hostname verification**. Nếu OpenSSL version hỗ trợ, bổ sung:

~~~bash
openssl s_client \
  -connect cassandra-1.example.invalid:9042 \
  -servername cassandra-1.example.invalid \
  -verify_hostname cassandra-1.example.invalid \
  -verify_return_error \
  </dev/null
~~~

OpenSSL có thể dùng **system CA store** khác Java truststore, nên kết quả thành công/thất bại không tự chứng minh Java driver sẽ giống hệt. Khi dùng private CA, một `-CAfile` chứa **public CA certificates được phê duyệt** có thể giúp tái tạo trust policy, không bao giờ dùng private key.

### 10.2. Xem validity, SAN, issuer và fingerprint

~~~bash
# server-leaf.pem chỉ chứa public leaf certificate.
openssl x509 -in server-leaf.pem -noout \
  -subject -issuer -dates \
  -ext subjectAltName \
  -fingerprint -sha256
~~~

So với những gì **server đang thực sự phát trên cổng native**, không chỉ file certificate trên disk. Một secret/cert mới có thể đã mount nhưng process chưa nạp lại hoặc vẫn có các pod/node cũ.

### 10.3. Kiểm tra chain đến CA tin cậy

~~~bash
# Public CA bundle/intermediates, không chứa private key.
openssl verify \
  -CAfile approved-root-ca.pem \
  -untrusted approved-intermediates.pem \
  server-leaf.pem
~~~

Kiểm tra hostname nếu version hỗ trợ:

~~~bash
openssl verify \
  -verify_hostname cassandra-1.example.invalid \
  -CAfile approved-root-ca.pem \
  -untrusted approved-intermediates.pem \
  server-leaf.pem
~~~

| Dấu hiệu | Giả thuyết | Hành động có kiểm soát |
|---|---|---|
| Expired | Leaf/intermediate/root đã hết hạn | Renew/rotate đúng chain |
| Unable to get issuer | Thiếu intermediate/root CA | Sửa server chain/client trust |
| Hostname mismatch | SAN không khớp DNS/IP | Cấp cert đúng tên hoặc sửa endpoint |
| Bad certificate trong mTLS | Client chain/key/EKU sai | Kiểm tra client keystore/server trust |
| No shared protocol/cipher | TLS/JDK policy không tương thích | So protocol/cipher policy theo release |
| Connection refused | Chưa tới TLS, listener/network | Kiểm port/firewall/native transport |

**Không sửa lỗi PKIX bằng cách hạ CL**; **không sửa TCP refused bằng cách cấp MODIFY**.

## 11. `keytool` và nguồn trust thực tế của Java

### 11.1. Liệt kê chứng thư trong truststore

~~~bash
# Keytool có thể hỏi mật khẩu theo chính sách CLI.
# Không đưa -storepass vào command ghi shell history chung.
keytool -list -v \
  -keystore /secure/path/cassandra-truststore.p12 \
  -storetype PKCS12
~~~

Cần xác minh:

- Root/intermediate CA có trong truststore thật của pod đang lỗi không?
- Fingerprint/issuer/validity có đúng CA mới?
- Truststore runtime được lấy từ JDK `cacerts`, Java system properties, driver SSL engine factory hay custom `SSLContext`?
- Pod mới và cũ có cùng mount secret, file permissions và JDK image không?
- Process đã reload SSLContext/cert sau secret rotation chưa?

Một file truststore **có tồn tại** không chứng minh driver **đang sử dụng** nó. Java default CA, OpenSSL system CA và container secret volume là ba nguồn khác nhau.

### 11.2. Truststore và keystore phục vụ hai mục đích

| Store | Chứa gì? | Ai dùng |
|---|---|---|
| Client truststore | Public CA/trust anchors | Java xác minh Cassandra server |
| Server keystore | Server private key và cert chain | Cassandra native TLS endpoint |
| Server truststore | CA tin client khi dùng mTLS | Cassandra xác minh client cert |
| Client keystore | Client private key và cert chain | Java client trong mTLS |
| Internode cert/trust | Vật liệu xác minh giữa nodes | Cassandra internode transport |
| JMX TLS stores | Vật liệu management TLS | Nodetool/monitoring |

**Không copy private keys từ production về laptop hoặc ticket**. Nếu cần tái tạo lỗi cert, dùng PKI test riêng trong môi trường cô lập.

### 11.3. Đối chiếu hostname trong driver node discovery

Driver thường khám phá **peer endpoints** ngoài contact points ban đầu. Nếu client kết nối bằng IP còn certificate chỉ có DNS SAN, hoặc peers quảng bá địa chỉ khác DNS, hostname validation có thể fail sau bootstrap.

Khắc phục bằng SAN/endpoint/address advertisement phù hợp, không tắt hostname verification. Với TLS proxy/service mesh, xác định nơi TLS kết thúc và chứng thư nào cần bảo vệ từng hop.

## 12. Cấu hình Cassandra: authenticator, authorizer và client TLS

Trong một số Cassandra releases dùng cấu hình tương ứng:

~~~yaml
# Minh họa TÊN CẤU HÌNH, không phải file production.
authenticator: PasswordAuthenticator
authorizer: CassandraAuthorizer
role_manager: CassandraRoleManager

client_encryption_options:
  enabled: true
  optional: false
  require_client_auth: false

# Keystore/truststore/secret/protocol/cipher settings phải
# được xác định theo phiên bản và công cụ quản trị cấu hình.
~~~

Cần đọc tài liệu **đúng Cassandra 3.x/4.x/5.x hoặc distribution** trước khi sửa: các khóa config, giá trị `optional`, hỗ trợ TLS/cert reloading và SSL context có thể khác.

**Không dùng `AllowAllAuthenticator` hoặc `AllowAllAuthorizer` để chữa incident**. Các thao tác thay auth settings/keystore có thể đòi rolling restart; phải giữ RF/CL availability và có rollback.

### 12.1. Quan sát server log có giới hạn

Ghi lại timeline (UTC), node/DC, loại lỗi handshake/role, version TLS/JDK, certificate fingerprint/serial đã được cho phép và change ID. Tránh bật `javax.net.debug=all` hoặc verbose SSL logs toàn production vì có thể gây log storm, lộ metadata và tăng I/O. Nếu cần debug, chọn đúng node/pod, khoảng thời gian ngắn, giới hạn quyền xem.

### 12.2. Không đổi cấu hình toàn cluster một lúc

Khi rotate server cert/CA:

- Client cũ và mới phải có giai đoạn trust overlap nếu CA đổi.
- Node có thể cần restart/reload tùy version; không giả định file mount mới tự được nạp.
- Rolling theo DC/rack với xác minh native TLS **và** internode compatibility.
- Theo dõi hints, streaming, compaction, GC, p99 và error rate.
- Giữ rollback material còn hiệu lực trong cửa sổ được phép.
- Không để một thay đổi TLS khiến số replica còn hoạt động thấp hơn quorum của CL.

## 13. Java Driver 4.x: cấu hình CqlSession có TLS

### 13.1. Code hướng dẫn có boundary rõ

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;
import javax.net.ssl.SSLContext;

public final class SecureSessionFactory {
    public static CqlSession open(
            String hostname,
            int nativePort,
            String localDc,
            String username,
            String secretFromApprovedProvider,
            SSLContext approvedSslContext) {

        return CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress(hostname, nativePort))
            .withLocalDatacenter(localDc)
            .withAuthCredentials(
                username, secretFromApprovedProvider)
            .withSslContext(approvedSslContext)
            .build();
    }
}
~~~

Ví dụ dùng API phổ biến trong Java Driver 4.x; kiểm tra chữ ký và SSL engine factory của **artifact/version thực tế**. `approvedSslContext` phải được khởi tạo với CA/trust managers đúng, **không phải trust-all**. Secret provider cần giới hạn vòng đời, rotation và không log password; overload nhận `String` không làm secret biến mất khỏi heap.

Không tạo một `CqlSession` mới cho mỗi request — session/pool được tái sử dụng trong vòng đời ứng dụng.

### 13.2. Không vô hiệu hóa peer verification

Các anti-pattern như `X509TrustManager.checkServerTrusted(...)` rỗng hoặc SSL hostname verifier luôn trả true sẽ khiến client dễ bị giả mạo peer. Tắt verification trong production làm suy yếu bảo mật dù traffic vẫn được mã hóa.

**Đảm bảo hostname validation đã được cấu hình rõ** theo driver/SSL engine factory; đừng giả định mọi bản 4.x có mặc định giống nhau.

### 13.3. Lặp lại phép thử từ đúng mạng của pod lỗi

Một `cqlsh` chạy ngay trên Cassandra node có thể đi loopback và dùng CA/role khác pod Kubernetes. Để chẩn đoán:

1. So DNS resolution/contact point của pod lỗi và pod khỏe.
2. So advertised peer addresses do driver khám phá.
3. So truststore/JDK image/secret mounts/SSL config.
4. So local DC, auth provider và keyspace.
5. Dùng query smoke-test có đủ partition key và `LIMIT`.
6. Thu cause trong `getAllErrors()` theo coordinator, không log raw bind values.

## 14. Đối chiếu quyền theo CQL và role thực tế

### 14.1. Quyền tối thiểu

~~~cql
-- Giả định các role đã được provisioning an toàn.
GRANT SELECT ON TABLE telemetry_lab.readings_by_device_day
TO telemetry_reader;

GRANT MODIFY ON TABLE telemetry_lab.readings_by_device_day
TO telemetry_writer;
~~~

Một role chỉ cần SELECT không nên có MODIFY/ALTER/DROP. Một role runtime không nên được dùng để sửa keyspace, repair hoặc rotate credentials quản trị.

### 14.2. Kiểm tra permissions và role hierarchy

~~~cql
-- Role có quyền quản trị/quan sát phù hợp:
LIST ROLES;
LIST ALL PERMISSIONS OF telemetry_reader;
~~~

Cassandra có role inheritance/cache theo cấu hình và release. Sau `GRANT`, phải test query qua role Java **đang dùng**; không mặc định permission mới hiện trên mọi node/session tức thì nếu cache chưa làm mới. Không dùng việc restart toàn bộ node hoặc cấp ALL PERMISSIONS để xử lý độ trễ cache.

### 14.3. Permission denied khác CQL invalid

| Kết quả | Hướng chẩn đoán |
|---|---|
| Unauthorized SELECT/INSERT | ROLE, grants, keyspace/table, authorizer |
| Authentication rejected | Password, role LOGIN, authenticator |
| Unconfigured table | Sai schema/keyspace/migration |
| Invalid query/ALLOW FILTERING request | Thiếu partition key/index/query shape |
| SSL handshake exception | Trust, SAN, expiry, TLS protocol/mTLS |
| ReadTimeout/Unavailable | RF, CL, replica liveness/performance |

**Không dùng ALLOW FILTERING để sửa permissions** và không tăng quyền khi query thực ra sai data model.

### 14.4. Multi-tenancy vẫn cần authorization ở ứng dụng

Quyền `SELECT` trên một table không tự bảo đảm row-level isolation giữa các tenant cùng bảng. App phải kiểm principal/tenant ownership; typed bind UUID không thay authorization. Không log tenant IDs/partition keys làm metric labels có cardinality lớn.

## 15. Native CQL, internode TLS và JMX là ba vùng sự cố khác nhau

| Triệu chứng | Hướng ưu tiên |
|---|---|
| Java CQL fail, `nodetool status` chạy | Client TLS/auth/network, không suy cluster healthy cho CQL |
| `nodetool` fail nhưng Java CQL khỏe | JMX auth/TLS/port riêng |
| CQL tới coordinator khỏe nhưng mất quorum | Internode link/TLS, replica, RF/CL |
| Sau rotate CA internode, nodes mất peer connectivity | Trust overlap, internode cert/node config |
| Proxy TLS thành công nhưng backend CQL fail | TLS kết thúc ở proxy; kiểm hop proxy→Cassandra |
| Chỉ client từ region A fail | Egress/firewall/DNS/TLS route và client config |

Cụ thể, `nodetool` thường đi qua JMX; việc nó hoạt động không xác minh certificate trên native transport 9042. `netstats` thể hiện SSTable streaming, không phải tất cả traffic native CQL.

Internode TLS phụ thuộc Cassandra version/topology; sự cố có thể làm replica messaging, gossip, streaming hoặc repair gián đoạn ngay cả khi Java client handshake với một node thành công.

## 16. Test bằng cqlsh mà không rò secret

`cqlsh` có thể dùng Python/OpenSSL trust path và cấu hình `cqlshrc` riêng, khác Java Driver. Khi thử:

- Dùng đúng Cassandra native endpoint/port và xác định TLS được bật theo version.
- Dùng role đại diện `telemetry_reader`, không chỉ role admin.
- Ưu tiên credential input/config secret an toàn; không đưa password vào shell arguments, command history hay CI logs.
- Thử một SELECT theo full partition key và volume nhỏ.
- Nếu cần kiểm MODIFY, dùng **table test chuyên dụng** trong môi trường được phép.
- Không chạy `SELECT *` toàn bảng lớn để “test TLS”.

Ví dụ cần tránh:

~~~bash
# ANTI-PATTERN: password hiện trong process list/shell history.
cqlsh -u telemetry_app -p "SENSITIVE_PASSWORD" host 9042
~~~

Một `cqlsh` kết nối được không chứng minh app Java sẽ dùng cùng CA, hostname verification, JDK cipher policy hoặc role.

## 17. Quy trình thay chứng thư và CA an toàn

### 17.1. Gia hạn leaf certificate và đổi CA là hai bài toán khác nhau

**Gia hạn leaf cert cùng CA** thường đơn giản hơn: trust anchors của client không cần đổi nếu chain và SAN vẫn đúng. Tuy nhiên vẫn cần chắc chắn keystore/certificate mới thực sự được nạp.

**Đổi root/intermediate CA** đòi kế hoạch đồng thời cho trust của các client, Cassandra native TLS, mTLS và internode (nếu sử dụng). Nếu thay server cert theo CA mới **trước** khi client tin CA mới, cả pod khỏe có thể bắt đầu lỗi `PKIX path building failed`.

### 17.2. Mẫu CA rotation có trust overlap

~~~mermaid
flowchart TD
    A["Inventory: clients, nodes, CA, expiry, SAN"] --> B["Phân phối trust bundle chứa CA cũ + CA mới"]
    B --> C["Xác minh clients/nodes đã nhận trust mới"]
    C --> D["Rolling thay leaf/server certificate sang CA mới"]
    D --> E["Smoke test native TLS + CQL auth + SELECT/MODIFY"]
    E --> F["Kiểm tra internode/JMX/mTLS theo phạm vi"]
    F --> G["Đợi mọi consumer hết phụ thuộc CA cũ"]
    G --> H["Gỡ CA cũ qua change có rollback"]
~~~

Đây là **mẫu sequencing**, không phải lệnh trực tiếp. Trong mTLS, server cũng phải tin **client CA mới/cũ** đúng giai đoạn; internode TLS cần điều phối hai chiều giữa node cũ và mới.

### 17.3. Inventory trước khi rotate

| Tài sản | Cần nắm |
|---|---|
| Node native endpoint | DNS/IP, SAN, leaf fingerprint/serial, NotAfter |
| Client pods | Truststore path, JDK image, CA version, SSL engine policy |
| Internode | Node certificates, trust roots, topology/ports |
| JMX/monitoring | Có TLS và certificate riêng hay dùng chung? |
| mTLS clients | Client keystore, clientAuth EKU, chain và server trust |
| Secret manager | Secret IDs/versions, rotation policy, rollout method |
| Load balancer/proxy | TLS termination points, SNI, backend validation |
| Dependencies | Clients của team khác, batch jobs, repair tooling, cqlsh |
| Rollback | Old/new cert còn hạn, image/config restore được không? |

Một thay đổi chứng thư có thể ảnh hưởng cả **job ít chạy** (ví dụ nightly backfill). Việc API chính pass chưa có nghĩa tất cả consumer đã migrate.

### 17.4. Không cắt CA cũ quá sớm

Sau khi server chuyển sang CA mới, client cũ có thể vẫn mở connection TCP/TLS đã được thiết lập từ trước và chỉ lỗi khi reconnect. Vì thế:

- Test **new connection**, không chỉ reuse pool đã mở.
- Kiểm tra từng application version/region/DC.
- Thử reconnect/restart có kiểm soát trong lab hoặc canary.
- Chờ cache/secret mounts/rollout hoàn tất.
- Ghi bằng chứng zero errors với trust cũ/new overlap window.

**Một vài giờ không lỗi không chứng minh 100% clients đã cập nhật** nếu có batch jobs tuần/tháng chưa chạy. Dựa vào inventory và chứng cứ cụ thể.

## 18. Runbook A — `PKIX path building failed` sau CA rotation

**Tình huống:** Java pod mới nhận `AllNodesFailedException`; root cause ở các candidates là `SSLHandshakeException` với thông tin PKIX. Pod cũ vẫn xử lý request.

1. **Đóng khung sự cố:** pod version/namespace, JDK image, truststore secret version, local DC, giờ UTC bắt đầu lỗi.
2. **Phân tích per-node map:** `getAllErrors()` cho thấy coordinator candidates nào fail; không kết luận cluster DOWN.
3. **Kiểm tra endpoint đúng:** DNS/IP/native port mà driver thực tế kết nối, không chỉ contact point đầu.
4. **Xem chain được server serve:** `openssl s_client -showcerts` từ mạng được phép, so leaf/intermediate/root và validity.
5. **So trust ở client:** `keytool -list -v` đối chiếu CA fingerprint của pod khỏe và lỗi; xem `SSLContext`/JDK đang dùng.
6. **Xác định lỗi chính:** missing root CA, missing intermediate, expired intermediate, JDK algorithm rejection hay hostname mismatch.
7. **Khắc phục an toàn:** phân phối trust bundle/chain hợp lệ hoặc rollback thay đổi CA theo change runbook; **không dùng trust-all manager**.
8. **Canary:** mở **connection mới**, chạy CQL nhỏ bằng role ứng dụng; xác minh TLS/auth và query success.
9. **Rollout có kiểm soát:** theo dõi driver handshake failures, API p99/errors, memory/CPU và internode nếu CA dùng chung.
10. **Prevent:** CA trust overlap, cert chain lint, smoke test trong CI và giám sát thời hạn.

**Phân biệt:** nếu `openssl` báo chain hợp lệ nhưng Java vẫn PKIX, cần xem JDK truststore/algorithm constraints/SSLContext. Không chỉ dùng OpenSSL kết luận client Java sai.

## 19. Runbook B — Chứng thư Cassandra server hoặc client đã hết hạn

**Tình huống:** Tại thời điểm gần `NotAfter`, handshake failures tăng trên một số node hoặc pod, trong khi CPU/disk Cassandra bình thường.

### 19.1. Xác định chứng thư nào đã hết hạn

- **Server leaf certificate:** có thể khiến mọi client xác minh node đó thất bại.
- **Intermediate CA:** toàn chain có thể không được chấp nhận dù leaf còn hạn.
- **Client certificate trong mTLS:** chỉ ứng dụng/pod dùng client cert ấy bị từ chối.
- **Internode certificate:** gây lỗi giữa node/replica, có thể ảnh hưởng RF/CL.
- **JMX certificate:** ảnh hưởng công cụ quản lý riêng, không tự là lỗi native CQL.

Dùng inventory, `openssl x509 -dates`, fingerprints, client/server logs và UTC timeline để xác định chính xác.

### 19.2. Các bước xử lý

1. **Đánh giá scope:** một node hay tất cả; một DC hay multi-DC; clientAuth hoặc serverAuth.
2. **Kiểm tra clock:** node/pod NTP offset; phân biệt `expired` với `not yet valid`.
3. **Renew cert đúng policy:** SAN, issuer chain, EKU, key usage, algorithm/cipher.
4. **Chuẩn bị trust overlap** nếu CA thay đổi; mTLS đòi cả hai chiều.
5. **Canary và rolling** theo node/pod phù hợp RF/CL.
6. **Đảm bảo reload/restart đúng cách:** chứng thư trên disk mới không đồng nghĩa listener đã phát cert mới.
7. **Kiểm tra chứng thư đang được serve:** fingerprint/NotAfter qua native TLS endpoint.
8. **Smoke-test:** connection mới, role login, `SELECT`/`MODIFY` trong phạm vi được phép.
9. **Theo dõi hậu quả:** handshake error rate, hints/streaming, replica health, p99 và timeout.
10. **Ghi RCA:** tại sao monitoring/owner/rotation pipeline không phát hiện sớm?

**Không** chỉnh system clock lùi lại, không chấp nhận expired cert qua trust manager bỏ kiểm tra, không tắt TLS trên production.

## 20. Runbook C — Đăng nhập được nhưng bị `UnauthorizedException`

**Tình huống:** Java service dùng cùng TLS và username, `SELECT` theo partition key thành công nhưng `UPDATE` trả permission denied.

1. **Xác định statement:** CQL template, keyspace/table và operation (SELECT/INSERT/UPDATE/DELETE/DDL).
2. **Xác định role thực:** role mà session đang dùng, inherited roles và môi trường cluster đúng.
3. **Kiểm tra authorizer:** `CassandraAuthorizer`/plugin và role cache theo version.
4. **Đối chiếu grants:** ví dụ `LIST ALL PERMISSIONS OF telemetry_writer;` bằng role được phép.
5. **Tách quyền:** `SELECT` cho read, `MODIFY` cho write, không tự cấp `ALTER`/`DROP`.
6. **Đánh giá nguyên nhân:** migration tạo table mới chưa grant? Role rename? Permission propagation/cache? Secret chuyển sang role khác?
7. **Khắc phục:** cấp **quyền nhỏ nhất trên đúng resource** qua change control, có audit.
8. **Test cả positive và negative:** write được phép phải chạy, resource không được phép vẫn bị từ chối.
9. **Đo lường:** Unauthorized error rate giảm, không tăng error ở API/cluster.
10. **Prevent:** grants như migration artifact được review và kiểm thử contract sau schema deployment.

### 20.1. Positive/negative permission test

Với một role chỉ đọc:

~~~text
Allowed:
    SELECT từ telemetry_lab.readings_by_device_day

Denied:
    INSERT/UPDATE/DELETE trên cùng table
    ALTER TABLE
    DROP KEYSPACE
    GRANT permissions
~~~

Test trên **keyspace test cô lập** với role có quyền tương ứng. Không thực hiện DDL nguy hiểm trên production chỉ để xác minh “deny đúng”.

### 20.2. Auth cache và permission propagation

Sau GRANT, nếu một node/session vẫn báo Unauthorized trong một thời gian ngắn, xác minh caches/release và đúng target cluster/role. Không tự xóa cache toàn cluster hoặc restart hàng loạt khi chưa hiểu tác động. Kiểm chứng qua nhiều coordinator trong canary nếu cần.

## 21. Runbook D — Mật khẩu/secret rotate khiến client authentication thất bại

**Tình huống:** Một nhóm pod mới dùng secret version B, nhóm cũ dùng version A. TLS handshake thành công nhưng user authentication bị từ chối; error có thể nằm trong connection initialization / `AllNodesFailedException`.

1. **Không log secret:** chỉ ghi secret version ID, role ID được phép và timestamp rollout.
2. **Xác định authenticator:** có dùng `PasswordAuthenticator` hay provider khác? Role có `LOGIN=true` không?
3. **Xác định cluster/keyspace:** app có trỏ nhầm môi trường khác với role/credentials khác không?
4. **So role identity:** có role rename, account locked/disabled (nếu provider hỗ trợ) hoặc rotation chưa lan truyền?
5. **Kiểm tra dependency:** vault/k8s secret mount, env var snapshot, config cache và session lifecycle.
6. **Khôi phục theo kế hoạch:** dùng secret hợp lệ/rollback app version, hoặc phased credential rotation bằng **hai identities/overlap** khi hệ thống hỗ trợ.
7. **Không dùng shared superuser:** không đổi user ứng dụng thành admin để vượt lỗi.
8. **Canary:** session mới đăng nhập và thực thi SELECT nhỏ; nếu cần WRITE, thử trong table được phép.
9. **Rollout từng nhóm:** theo dõi authentication failures, connection churn và API SLO.
10. **Prevent:** rotation contract, dự phòng overlap/canary/expiry alerts, kiểm tra stale consumers.

### 21.1. Cẩn thận với single-user password rotation

Nếu hệ thống chỉ có **một role và một credential hiệu lực**, việc đổi password trong khi client pod cũ chưa nhận secret mới có thể gây downtime ở những connection/reconnect mới. Lựa chọn tốt hơn có thể là **hai role có cùng permissions tối thiểu**, triển khai role mới trước rồi thu hồi role cũ sau cutover, nếu policy/architecture cho phép.

Mục tiêu là **chuyển identity an toàn**, không giữ credential cũ tồn tại vô thời hạn.

## 22. Runbook E — Hostname mismatch sau thay contact point/DNS

**Tình huống:** Java service đổi contact point từ `cassandra-1.dc1.example.invalid` sang IP hoặc một load balancer alias. TLS fail chỉ trên một số peer; server certificate vẫn còn hạn.

1. So endpoint driver đang kết nối: contact point ban đầu và peer addresses đã khám phá.
2. Xem SAN của server cert: có DNS/IP thực tế dùng không?
3. Xem `-servername`/SNI và validation name trong driver SSL engine policy.
4. Kiểm DNS record, IP NAT, Kubernetes Service, proxy và advertised native address.
5. Không tắt hostname verification.
6. Sửa endpoint hoặc cấp certificate bao phủ SAN hợp lệ theo PKI.
7. Với proxy TLS termination, kiểm cert của cả client→proxy và proxy→Cassandra.
8. Test **connection mới** tới tất cả peers ở local DC, không chỉ một contact point.
9. Kiểm p99, handshake failures và native transport pool stability sau rollout.
10. Ghi lại quy tắc naming cho node join/bootstrap/replace tiếp theo.

**Quan trọng:** Khi thêm node mới, certificate naming policy phải đi trước bootstrap; không chạy một node chưa có SAN/CA thích hợp rồi kỳ vọng driver tự bỏ qua validation.

## 23. Runbook F — Internode TLS lỗi khi rolling upgrade/rotate CA

**Tình huống:** Java pod vẫn TLS thành công với vài node, nhưng một DC có nhiều replica unavailable, hints/streaming chậm sau khi thay internode trust.

1. **Triage cluster safety:** RF, CL, node status, rack/DC, khả năng còn quorum.
2. **Tách đường TLS:** Java→coordinator có thể khỏe, nhưng internode node→node bị lỗi.
3. **Kiểm tra từng node:** cert chain, trust bundle, EKU/SAN, protocol/cipher, keystore reload.
4. **So old/new trust overlap:** có node mới chỉ tin CA mới trong khi node cũ vẫn phát CA cũ không?
5. **Đối chiếu internode logs:** handshake failures, gossip/streaming, connection resets.
6. **Không restart đồng loạt:** rolling theo kế hoạch cluster-safe, giữ replica availability.
7. **Nếu đã mất quorum:** ưu tiên khôi phục đường node-to-node/trust theo SOP; không tự hạ CL như cách xử lý mặc định.
8. **Canary từng bước:** node sau recovery trao đổi replica traffic ổn, không chỉ `UN`.
9. **Quan sát hậu quả:** hints, streaming, repair, compaction/disk, read/write timeout và API p99.
10. **Prevent:** CA overlap cho internode, test mixed-version/mixed-cert lab, rollback được diễn tập trước.

JMX auth/TLS có thể gây lỗi cho `nodetool` riêng: nếu native CQL và internode khỏe, kiểm tra JMX credentials/SSL/port trước khi sửa Cassandra cluster TLS khác.

## 24. Bảo mật log, metrics và báo cáo sự cố

### 24.1. Structured event nên ghi

~~~text
event=cassandra_security_connection_failure
timestamp_utc=2026-11-21T10:00:00Z
app_component=telemetry-reader
deployment_version=v42
query_template=latest20_by_device_day
outcome=tls_handshake_failure
error_family=cert_chain_validation
local_dc=dc1
candidate_nodes=3
cert_fingerprint=approved_digest_or_redacted
secret_version=approved_version_id_only
~~~

Đây là **log schema do ứng dụng thiết kế**, không phải log mặc định của Cassandra. Chỉ ghi metadata node/cert/secret phiên bản được phép theo security policy; không ghi secrets, password, private key, raw CQL bind values hoặc user personal data.

### 24.2. Metrics phù hợp

| Metric | Gợi ý label hữu hạn | Ý nghĩa |
|---|---|---|
| Auth failure rate | app, version, DC, error family | Secret/role mismatch |
| Unauthorized rate | query template, role class | Thiếu grants |
| TLS handshake failures | app, DC, failure family | CA/SAN/protocol/cert |
| AllNodesFailed rate | app, error family | Candidate coordinator failures |
| Connection pool | app instance/DC, in-flight, reconnect | Churn, handshake storm |
| Cert expiration | certificate group, days remaining | Cảnh báo sớm |
| API p99 / 5xx | endpoint/query template | Ảnh hưởng người dùng |
| Cassandra availability | DC/rack/node, RF/CL | Cluster safety |
| Internode errors | DC/rack/error family | Replica communication |

Không dùng error message nguyên văn hoặc hostname/IP của mọi kết nối làm nhãn động không kiểm soát. Không coi certificate days remaining là đủ: cần kiểm **not-yet-valid, chain, SAN, EKU, key rotation status**.

### 24.3. Thông tin không nên đưa vào ticket/chat

- Database username/password đầy đủ nếu vượt phạm vi need-to-know.
- Truststore/keystore password.
- PEM private key hoặc secret từ K8s/Vault.
- Raw TLS session keys, token bearer hoặc query bind values.
- Customer/tenant IDs và dữ liệu bản ghi thật.
- Stack trace lặp hàng triệu dòng hoặc dump heap chứa secrets.

Dùng fingerprint/serial công khai và log trích chọn có redaction; artifact bảo mật phải lưu trong hệ thống được phép.

### 24.4. Phân biệt warning và actual outage

Certificate còn 20 ngày không tự là incident, nhưng có thể là **risk** cần rotation có owner. Certificate đã quá hạn ở một node chưa chắc toàn cluster outage (nếu client chưa route tới nó), nhưng là **lỗi cần sửa khẩn cấp**, đặc biệt trước reconnect/rolling restart.

SLO app, availability, native TLS errors và inventory expiry đều phải được theo dõi.

## 25. Kiểm thử hồi quy và diễn tập trong cluster cô lập

### 25.1. Test matrix cho authentication, authorization và TLS

| ID | Tình huống | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| T01 | Server cert hợp lệ, CA đã trust, SAN đúng | TLS handshake thành công | Connection + CQL smoke test |
| T02 | Client thiếu root/intermediate CA | TLS handshake bị từ chối | PKIX/chain error được phân loại |
| T03 | Server cert hết hạn | Client từ chối peer | Expired certificate cause/metadata |
| T04 | Server cert chưa có hiệu lực | Client từ chối peer | NotBefore/not-yet-valid |
| T05 | IP endpoint không nằm trong SAN | Hostname verification fail | SAN và endpoint không khớp |
| T06 | TLS protocol/cipher mismatch | Handshake fail, không tới CQL | Protocol negotiation evidence |
| T07 | mTLS yêu cầu client cert nhưng client thiếu | Server từ chối client | Handshake/cert request logs |
| T08 | mTLS client cert sai EKU/chain | Handshake fail | Client cert chain metadata |
| T09 | Đúng TLS nhưng sai CQL password | Auth failure | CQL authenticate outcome |
| T10 | Role có `LOGIN=false` | Không được login qua role ấy | Authentication outcome |
| T11 | Role có SELECT đúng table | SELECT thành công | Read một row seed theo full key |
| T12 | Role chỉ có SELECT thử INSERT | Unauthorized | CQL permission denied |
| T13 | Role có MODIFY đúng table | INSERT/UPDATE trong table test được phép | Read-back |
| T14 | Role runtime thử ALTER/DROP | Unauthorized | Negative permission test |
| T15 | GRANT mới và cache/role refresh | Truy vấn được phép sau propagation hợp lệ | Thời điểm và node/role thực tế |
| T16 | CA cũ + mới cùng trong trust bundle | Client kết nối được khi server dùng một trong hai chain được tin | Test new connections |
| T17 | Gỡ CA cũ sau all consumers migrated | Chỉ cert CA mới được tin | Inventory + canary reconnect |
| T18 | Cùng secret version nhưng hai JDK images | Phát hiện disabled cipher/algorithm/truststore mismatch | JDK/SSL diagnostics |
| T19 | Một server node có cert lỗi | Per-node map chỉ ra đúng nhóm lỗi | `getAllErrors()` |
| T20 | Java→coordinator OK, internode TLS sai | RF/CL errors được phân biệt | Server/internode logs |
| T21 | JMX credentials sai, Java CQL vẫn OK | Chỉ management path lỗi | Nodetool và Java outcomes |
| T22 | Clock skew trong môi trường cô lập | Certificate validity được đánh giá đúng | UTC/NTP offset |
| T23 | Secret rotate giữa nhóm pod | Canary/rollback không gây outage rộng | Connection + API metrics |
| T24 | TLS failure bị retry vô hạn (test negative) | Guardrail/retry budget ngăn storm | Retry attempts / CPU |
| T25 | Authorization test qua tenant khác | Principal bị từ chối đúng | Business authorization outcome |

**Không diễn tập T02–T08, T20, T22 trên production.** Testcert phải được dựng trên lab/CI với PKI riêng, không làm giả private key production hay điều chỉnh đồng hồ node thật.

### 25.2. Giới hạn của Testcontainers một node

Một Cassandra Testcontainers instance có thể kiểm:

- SSL/auth configuration trong một môi trường hỗ trợ.
- Role SELECT/MODIFY và negative grants.
- Java driver truststore/keystore parsing.
- Root-cause logging và query smoke tests.

Nhưng một node RF=1 **không đại diện** multi-DC internode failures, quorum dưới node outage, role/permission cache toàn cluster hoặc rolling CA rotation xuyên rack. Những tình huống đó cần **cluster nhiều node** trong lab với network policies được phép thay đổi.

### 25.3. Kiểm thử tính đúng, không chỉ handshake

TLS thành công + authentication thành công mới là **điều kiện cần**. Sau đó cần thử:

1. SELECT đúng partition key và expected result.
2. INSERT/UPDATE chỉ bằng role được phép trong table test.
3. Unauthorized cho những operations không được phép.
4. RF/CL success/failure đúng thiết kế khi fault trong lab.
5. Không có duplicate write side effects do retries.
6. Không có regression về driver p95/p99 hoặc connection churn.
7. Không lộ secret/PII trong logs dù kết nối thất bại.

## 26. Quy trình xác minh phục hồi từ ứng dụng tới replica

### 26.1. Health check ba tầng

~~~text
Lớp 1 — Transport & TLS
  [ ] TCP/native listener reachable từ app namespace
  [ ] Certificate chain, validity, SAN và TLS policy hợp lệ
  [ ] New connection từ canary handshake thành công

Lớp 2 — Identity & permissions
  [ ] CQL authentication bằng đúng role runtime thành công
  [ ] SELECT/MODIFY được phép đúng table
  [ ] DDL/unapproved table bị từ chối theo least privilege

Lớp 3 — Data & distributed availability
  [ ] Query có đủ partition key thành công với CL nghiệp vụ
  [ ] Replica availability đạt RF/CL
  [ ] Timeout/error/p99 trong SLO
  [ ] Internode, hints, repair, streaming, compaction ổn định
~~~

Một hệ có thể pass lớp 1 nhưng fail lớp 2; pass lớp 2 nhưng fail lớp 3. **Không thông báo “khắc phục hoàn toàn” ngay khi openssl handshake thành công.**

### 26.2. Kiểm tra role runtime trên đúng môi trường

Trong các ứng dụng Spring Boot/Spring Data Cassandra, credentials có thể đến từ nhiều profile:

- Local development secrets.
- Kubernetes Secrets, mounted files hoặc environment injection.
- Vault/secret manager plugin.
- Driver profile/session factory được app tạo.
- Cấu hình tự động của Spring Boot/driver version.
- CI/staging test overrides.

Cần so **effective configuration** theo pod/version nhưng không in secret. Một property đúng trong Git chưa chắc đã là giá trị process đang sử dụng. Tương tự, secret mount đổi chưa chắc driver đang tự reload credentials.

### 26.3. Đo hậu quả performance sau sửa bảo mật

Sau rotation có thể có:

- TLS handshakes tăng tạm thời do reconnect.
- CPU tăng do mã hóa và certificate validation.
- Driver connection pool tái tạo chậm.
- Read/write latency tăng khi một nhóm node restart.
- Hints/streaming/compaction kéo dài sau rolling.
- Connection errors tập trung một rack/DC.

Do đó recovery assessment nên theo dõi **healthy steady state**: API success rate, p99, driver exceptions, connection counts, node status và replica resources.

### 26.4. Chống false-positive do kết nối cũ còn sống

Một pool đã mở trước `NotAfter` hoặc trước CA rotation có thể tiếp tục truyền dữ liệu trên kết nối đang hoạt động theo implementation/policy cho đến khi reconnect. Vì vậy smoke test phải gồm:

- **New CqlSession/new connection** trong lab/canary.
- Canaries chạy đủ qua connection renewal.
- Thử từng node/DC liên quan, không chỉ một hostname.
- Rollout status của tất cả batch jobs/client applications.

Không cưỡng ép restart toàn production chỉ để “thử” nếu không có approved change procedure.

## 27. Những anti-pattern gây sự cố thứ cấp

| Hành động sai | Vì sao nguy hiểm | Cách xử lý đúng |
|---|---|---|
| Tắt TLS khi cert lỗi | Mất bảo mật đường truyền | Renew/rotate đúng chain |
| Trust-all `X509TrustManager` | Không xác minh peer, nguy cơ MITM | Truststore với CA được duyệt |
| Tắt hostname verification | Cho phép giả mạo endpoint | SAN và hostname policy phù hợp |
| Hạ CL từ LOCAL_QUORUM xuống ONE để chữa TLS | Thay correctness mà không sửa lỗi | Điều tra security/replica path |
| Cấp superuser cho app khi Unauthorized | Quyền vượt nhu cầu, tăng blast radius | GRANT tối thiểu trên resource |
| Bật `AllowAllAuthorizer` | Mất kiểm soát quyền Cassandra | Cấu hình authorizer đúng |
| Đổi password qua command có `-p password` | Shell history/process args lộ secret | Secret provider/secure prompt |
| Log hết `getMessage()` mỗi request | Rò metadata/secret, log storm | Structured log có redaction/sampling |
| Retry `SSLHandshakeException` vô hạn | Không tạo CA bị thiếu; CPU/network storm | Fail fast và sửa config/PKI |
| Coi `AllNodesFailed` là mọi node DOWN | Sai scope, xử lý nhầm replica | `getAllErrors()` theo coordinator |
| Chỉ so cert trên disk | Process có thể serve cert cũ | Kiểm leaf thực tế qua endpoint |
| Xóa CA cũ trước khi client migrate | Clients cũ bị PKIX | Trust overlap |
| Rotate mọi Cassandra node cùng lúc | Mất RF/CL quorum | Rolling theo topology |
| Dùng `nodetool status` để chứng minh CQL TLS khỏe | JMX khác native transport | Java/cqlsh smoke test |
| Dùng cqlsh admin rồi kết luận app role có quyền | Role khác nhau | Test role runtime |
| Chỉnh clock node khi cert hết hạn | Hỏng time assumptions của hệ phân tán | Renew cert và đồng bộ NTP |
| Phân tích timezone local không quy đổi | Đọc sai NotBefore/NotAfter | UTC normalized timeline |
| Bỏ qua intermediate CA | Chain incomplete dù leaf còn hạn | Verify full chain/trust |
| Bỏ qua discovery peer addresses | Contact point OK nhưng node khác fail | SAN cho mọi endpoint driver dùng |
| Coi mTLS cert là quyền SELECT | TLS identity khác RBAC | Phân tách TLS/CQL authorization |
| Coi sửa auth là sửa data correctness | Có thể còn lỗi CL/partition | Kiểm ba tầng |
| Reconnect mọi service cùng lúc | Connection storm/CPU/network | Canary và staggered rollout |
| Không test negative permission | Authorizer có thể không thực thi | Assert thao tác trái phép bị deny |
| Bỏ qua job chạy theo lịch | CA cũ bị gỡ khi batch job chưa migrate | Inventory và window đủ dài |

## 28. Câu hỏi luyện tập có đáp án

### Câu 1 — Authentication và authorization

Client kết nối TLS được, login thành công, SELECT thành công nhưng INSERT báo denied. Tầng nào có khả năng lỗi nhất?

**Đáp án:** Authorization. Role có thể có `SELECT` nhưng thiếu `MODIFY` trên table. Không sửa truststore hay cấp superuser.

### Câu 2 — PKIX khi cert còn hạn

Server leaf còn sáu tháng nhưng Java báo `PKIX path building failed`. Có chắc cert expired không?

**Đáp án:** Không. Truststore có thể thiếu CA hoặc server gửi thiếu intermediate; cũng cần xem JDK policy.

### Câu 3 — SAN và IP

Driver kết nối qua IP, certificate chỉ có DNS SAN. Vì sao handshake có thể fail?

**Đáp án:** Hostname/IP validation không khớp SAN. Cần dùng endpoint hợp lệ hoặc cấp cert có IP SAN phù hợp; không tắt verification.

### Câu 4 — NotBefore

Certificate mới có `NotBefore` trong tương lai so với client. Thao tác đúng?

**Đáp án:** Xác minh clock UTC/NTP và thời điểm phát hành, cấp lại/rollout cert hợp lệ nếu cần; không chỉnh đồng hồ hệ thống để vượt kiểm tra.

### Câu 5 — NotAfter

Chứng thư server vừa hết hạn nhưng pod vẫn có kết nối cũ đang đọc được. Có thể coi rotation không gấp không?

**Đáp án:** Không. New connections/reconnect có thể fail. Phải gia hạn/rotate và kiểm chứng listener thực sự phát cert mới.

### Câu 6 — getAllErrors

`AllNodesFailedException.getAllErrors()` có node A/B. Đây có là bản đồ mọi replica ACK không?

**Đáp án:** Không. Đó là coordinator candidates và lỗi driver ghi nhận; không dùng để suy outcome write trên replica.

### Câu 7 — Auth fail vs unauthorized

Username/password sai thường có xảy ra sau khi `SELECT` đang thực thi không?

**Đáp án:** Sai credential thường khiến session authentication thất bại trước quyền CQL; Unauthorized liên quan permissions sau authentication.

### Câu 8 — JMX khác CQL

`nodetool status` thành công, Java CQL báo handshake failure. Node có chắc healthy ở native TLS không?

**Đáp án:** Không. Nodetool thường đi đường JMX, còn Java qua native transport/TLS. Phải thử từ mạng app.

### Câu 9 — mTLS

Cassandra server yêu cầu client certificate nhưng Java chỉ có truststore CA cho server. Đã đủ chưa?

**Đáp án:** Chưa. Client cần identity certificate/private key và chain phù hợp, server phải trust client CA. CQL auth/permissions vẫn có thể cần riêng.

### Câu 10 — CA rotation

Thứ tự nào an toàn hơn: thay leaf theo CA mới rồi mới phân phối trust, hay phân phối trust cũ+mới trước?

**Đáp án:** Thông thường **mở rộng trust trước**, xác minh clients/nodes đã nhận, rồi rolling leaf mới; chỉ gỡ CA cũ khi consumers đã migrate.

### Câu 11 — CqlSession

Tạo `CqlSession` mới cho mỗi HTTP request giúp tránh TLS lỗi lâu dài không?

**Đáp án:** Không. Có thể tạo connection/handshake storm, tăng CPU và latency. Tái sử dụng session và sửa trust/auth root cause.

### Câu 12 — Password rotation

Pod mới dùng secret B, pod cũ dùng A, một role chỉ có một password đang hiệu lực. Rủi ro nào?

**Đáp án:** Mixed pods có thể fail authentication khi reconnect. Cần phased identity/credential rotation hoặc overlap theo policy.

### Câu 13 — Role ít quyền

Service chỉ đọc một table. Quyền nào phù hợp?

**Đáp án:** `SELECT` trên đúng table/keyspace theo nhu cầu, không `ALL PERMISSIONS ON ALL KEYSPACES`.

### Câu 14 — Query invalid

Cassandra từ chối query vì thiếu partition key. Có nên `GRANT MODIFY` để sửa?

**Đáp án:** Không. Đó là lỗi query shape/CQL restrictions, không phải permission; cần thiết kế truy vấn/schema.

### Câu 15 — Tenant security

Role Cassandra có SELECT toàn bảng; app nhận tenant ID từ URL không kiểm quyền. TLS và CQL bind parameter có đủ bảo vệ dữ liệu?

**Đáp án:** Không. Cần xác thực principal, kiểm ownership/authorization ở application và thiết kế cách ly tenant.

### Câu 16 — TLS proxy

Client kết nối TLS thành công đến proxy. Có thể chứng minh hop proxy→Cassandra cũng TLS đã xác minh không?

**Đáp án:** Không. Cần kiểm architecture, trust/cert và policies của từng hop.

### Câu 17 — Root/intermediate

Leaf được ký bởi Intermediate-CA; client chỉ tin root hợp lệ nhưng server không gửi intermediate. Điều gì có thể xảy ra?

**Đáp án:** Client không xây được chain và báo PKIX/issuer error. Server cần gửi chain phù hợp hoặc client có intermediate đáng tin theo policy.

### Câu 18 — Debug logs

Có nên bật verbose SSL debug cho mọi pod production trong nhiều ngày?

**Đáp án:** Không. Gây I/O/log storm và có thể lộ metadata; chỉ debug theo phạm vi/time window có redaction và quyền truy cập.

### Câu 19 — Rolling internode CA

Một nửa node chỉ trust CA mới, nửa còn lại chỉ có leaf CA cũ. Tình huống này có thể gây gì?

**Đáp án:** Internode handshake failure, replica messaging/streaming/CL errors. Cần trust overlap và rolling sequencing, không restart đồng loạt.

### Câu 20 — Certificate alert

Leaf còn 14 ngày, có owner và renewal pipeline nhưng không có canary test. Đã đủ phòng ngừa chưa?

**Đáp án:** Chưa. Cần kiểm renewal, chain/SAN, rollout/reload, new connections và monitoring trước deadline; alert phải gắn với action và owner.

### Câu 21 — TLS vs CQL timeouts

Driver báo `ReadTimeoutException` sau khi session authenticate được. Có thể kết luận chứng thư hết hạn?

**Đáp án:** Không. Đây là tín hiệu read/replica/CL path; điều tra latency/availability, không suy TLS expiry.

### Câu 22 — Phục hồi

Sau khi renew cert, OpenSSL handshake đã thành công. Có thể đóng incident ngay?

**Đáp án:** Chưa. Cần kiểm role authentication, permissions, query theo full partition key, CL, success/error/p99 và new connections ở các client versions/DC.

## 29. Checklist production trước và sau rotation

### 29.1. Trước thay chứng thư/secret

~~~text
[ ] Inventory mọi client, batch job, node, DC, proxy, mTLS/JMX paths.
[ ] Ghi NotBefore/NotAfter, SAN, issuer, chain, fingerprint/serial.
[ ] Có CA bundle cũ+mới nếu thay CA, cùng trust overlap window.
[ ] Đã thử JDK/driver/server TLS compatibility trong lab.
[ ] Biết driver SSLContext/truststore đang dùng thực tế.
[ ] Secrets/keystore/private keys được bảo vệ trong vault/PKI.
[ ] Có owner, change window, rollback và guardrails theo RF/CL.
[ ] Có canary test new connections, không chỉ reuse open pool.
[ ] Có alert expiry và kiểm chứng certificate thực sự đang serve.
[ ] Không hạ TLS verification, không cấp superuser tạm.
~~~

### 29.2. Trong rollout

~~~text
[ ] Canary pod mới có TLS handshake + CQL auth thành công.
[ ] Xem getAllErrors() theo candidates khi thất bại.
[ ] Role runtime đúng, SELECT/MODIFY theo nhu cầu, DDL bị deny.
[ ] TLS SAN/chain/validity đúng mọi node/peer được driver discovery.
[ ] Internode/JMX paths được kiểm riêng theo topology.
[ ] Rolling giữ đủ replica theo RF/CL, không restart đồng loạt.
[ ] Retry/connection churn không tạo CPU/handshake storm.
[ ] API p95/p99, errors, driver pools và node metrics được giám sát.
[ ] Không in secret/password/raw query bind values trong logs.
[ ] Có quyền rollback khi criteria fail, không tiếp tục mở rộng sự cố.
~~~

### 29.3. Sau rollout

~~~text
[ ] New connections đến từng local DC/peer phục vụ ổn.
[ ] Query theo full primary key đúng dữ liệu, CL và timeout budget.
[ ] Unauthorized và authentication fail rate về baseline.
[ ] Chứng thư đang serve là bản mới, expiry horizon đủ dài.
[ ] Clients cũ/batch jobs đã migrate hoặc có kế hoạch cụ thể.
[ ] Internode streaming, hints, compaction/repair và p99 ổn định.
[ ] Chỉ gỡ CA cũ sau khi có bằng chứng mọi consumer sẵn sàng.
[ ] Có RCA, cập nhật inventory/trust matrix, automation expiry alerts.
[ ] Không coi fix bảo mật là thay thế kiểm tra data correctness.
[ ] STEP 6 Content QA sẽ được tiến hành riêng theo quy trình.
~~~

## 30. Tổng kết

Xử lý **lỗi xác thực, quyền, TLS và chứng thư hết hạn** trong Apache Cassandra đòi hỏi phân tích đúng ranh giới:

1. **TLS transport** xác minh peer/chain/hostname/protocol; lỗi PKIX, SAN hoặc expiry diễn ra trước khi CQL permission được xét.
2. **Authentication** xác nhận role/identity có thể login; password/secret và `LOGIN`/authenticator phải đúng.
3. **Authorization** kiểm tra quyền resource; thiếu `SELECT`/`MODIFY` không thể sửa bằng thay certificate.
4. **Native CQL, internode và JMX** là các đường bảo mật riêng; một đường hoạt động không chứng minh tất cả đường khác khỏe.
5. **`AllNodesFailedException.getAllErrors()`** phải được đọc theo coordinator candidates và cause chain, không biến thành replica ACK map hoặc kết luận toàn cluster DOWN.
6. **Chứng thư có nhiều điều kiện hợp lệ**: CA chain, NotBefore/NotAfter, SAN, EKU, algorithm policy, JDK truststore và clock UTC.
7. **Java Driver và hệ điều hành có thể dùng trust khác nhau**; OpenSSL thành công không đảm bảo SSLContext Java sẽ thành công.
8. **Rotation phải có trust overlap, canary và rolling**; đừng gỡ CA cũ trước khi mọi client/node đã migrate.
9. **Không lấy đường tắt làm suy giảm bảo mật**: trust-all, tắt hostname validation, AllowAllAuthorizer, shared admin user hoặc chỉnh system clock đều sai.
10. **Sửa lỗi có thể gây hậu quả phân tán**: restart node, internode trust, replica availability, hints/repair/compaction và p99 cần được theo dõi.
11. **Khôi phục chỉ hoàn tất khi cả ba tầng pass**: TLS, role/permissions và query correctness/CL/API SLO.
12. **Ngăn sự cố lặp lại** bằng cert expiry alerts, inventory CA/secret, tested rollback, negative permission tests và logging an toàn.

Câu hỏi cốt lõi không phải **“Tại sao Java không kết nối được Cassandra?”** ở mức chung chung, mà là **“Tại bước nào kết nối bị từ chối, peer/cert/role/resource nào không khớp, lỗi có phạm vi node/DC/client nào, và thay đổi nào khôi phục đúng danh tính và quyền mà vẫn giữ nguyên bảo đảm RF/CL của cluster?”**. Trả lời bằng chứng cứ theo từng lớp giúp sửa đúng nguyên nhân và không biến một sự cố chứng thư thành sự cố dữ liệu hoặc bảo mật lớn hơn.


