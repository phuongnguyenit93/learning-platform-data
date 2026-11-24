# Quản lý secret và certificate trong Spring Integration Adapters

## 1. Bối cảnh production: kết nối ngoài đồng nghĩa quản lý niềm tin

Trong module **SPRING_INTEGRATION_ADAPTERS**, ứng dụng Spring Integration kết nối các hệ thống bằng **inbound/outbound adapter**, **gateway**, **poller** và **MessageChannel**. Một flow có thể lấy file qua SFTP, ghi JDBC, gọi HTTP API đối tác, gửi JMS/AMQP/Kafka rồi trả kết quả. Để luồng hoạt động trong production, mỗi điểm kết nối phải trả lời hai câu hỏi độc lập:

1. **Ta đang kết nối đúng hệ thống đích và có kênh truyền bảo mật không?**
2. **Danh tính ứng dụng đang sử dụng có được phép thực hiện tác vụ đó không?**

Đó là lý do **secret** và **certificate** cần được quản lý như một phần của thiết kế tích hợp, không phải chỉ là vài chuỗi cấu hình.

Một mật khẩu DB bị lộ có thể cho phép đọc/sửa bảng nghiệp vụ. Một API token bị lộ có thể cho phép giả mạo outbound request. Một chứng chỉ máy chủ hết hạn có thể làm dừng hàng nghìn yêu cầu HTTP/SFTP qua các poller. Một truststore sai có thể khiến client từ chối máy chủ hợp lệ hoặc — nguy hiểm hơn — chấp nhận máy chủ giả nếu đội vận hành đã vô hiệu hóa xác minh để khắc phục tạm.

### Mục tiêu bài học

Sau bài này, người học có thể:

1. Phân biệt **secret, credential, private key, public key, certificate, truststore, keystore, CA** và các cơ chế SSH khác TLS.
2. Xác định thông tin xác thực và tài sản tin cậy cho từng adapter File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC.
3. Sử dụng nguồn secret ngoài mã nguồn, tách môi trường, chủ sở hữu và quyền truy cập tối thiểu.
4. Thiết kế **TLS/mTLS**, hostname verification, certificate chain và SFTP host-key verification đúng ranh giới.
5. Triển khai **rotation/renewal** có overlap, reload kết nối và rollback an toàn.
6. Giám sát expiry, lỗi authentication, TLS handshake, pinning, secret exposure và incident response.
7. Viết kiểm thử tích hợp về secret/certificate lifecycle, không chỉ kiểm tra kết nối thành công.

**Nguyên tắc xuyên suốt:** tài liệu hướng dẫn cách tổ chức bảo mật cho hệ thống thực tế; các ví dụ không chứa password, token hoặc private key thật. Những điểm phụ thuộc nhà cung cấp và phiên bản cần được xác minh với API của adapter, driver và broker tương ứng.

## 2. Thuật ngữ phải phân biệt

| Khái niệm | Bản chất | Điều cần bảo vệ / kiểm tra |
|---|---|---|
| Secret | Dữ liệu không được phép lộ | Mật khẩu, API key, token, private key, SASL credential |
| Credential | Bằng chứng xác thực danh tính | Mật khẩu, bearer token, SSH key pair, client certificate |
| Public key | Khóa công khai | Phải gắn đúng chủ thể, không cần giữ bí mật |
| Private key | Khóa bí mật của key pair | Bảo vệ nghiêm ngặt, không ghi log/commit; có thể ở HSM |
| X.509 certificate | Chứng chỉ ràng buộc public key với subject/SAN và thời hạn | Xác minh chữ ký, chain, tên đích, mục đích sử dụng |
| CA | Đơn vị phát hành/ký chứng chỉ | Chỉ tin CA/anchor được phê duyệt |
| Truststore | Tập trust anchors/certificates phía client tin cậy | Không nhầm với private key dùng xác thực client |
| Keystore | Kho có thể giữ khóa và chứng chỉ của một danh tính | Kiểm soát truy cập private key và mật khẩu kho |
| TLS | Giao thức bảo mật kênh truyền | Xác thực peer, mã hóa, toàn vẹn, phiên bản/cipher policy |
| mTLS | TLS xác thực cả client và server bằng certificate | Cả hai phía phải kiểm tra danh tính peer |
| SSH host key | Public key xác thực máy chủ SSH/SFTP | Xác minh fingerprint/known_hosts đúng đích |
| SSH client key | Key pair dùng xác thực người dùng/client SSH | Private key cần bí mật, public key đăng ký phía server |
| OAuth access token | Bearer hoặc proof-of-possession token cấp quyền API | Phạm vi quyền, thời hạn, lưu giữ/renewal |
| SASL | Khung xác thực dùng bởi Kafka/broker | Credential và mechanism cụ thể, thường đi kèm TLS |

### 2.1. Certificate không phải lúc nào cũng là secret

Public certificate thường có thể được phân phối công khai. **Private key đi kèm certificate mới là phần cần giữ bí mật**. Tuy vậy, tập trust anchors, hostname/fingerprint pinning và các file cấu hình liên quan cần được quản lý tính toàn vẹn: thay CA tin cậy sai có thể làm ứng dụng chấp nhận peer giả.

### 2.2. mTLS không thay authorization

Một HTTP client xuất trình chứng chỉ hợp lệ chứng minh danh tính mà server đã chấp nhận, **không mặc định được phép gọi mọi endpoint hay truy cập dữ liệu mọi tenant**. Cần authorization riêng theo principal, scope, role, resource và business contract.

### 2.3. SFTP dùng SSH, không dùng X.509 TLS như HTTPS

SFTP chạy trên SSH. **SSH host key verification** (known_hosts/fingerprint) không giống **TLS certificate chain verification**. File private key SSH dùng client authentication cũng không phải PEM certificate chain mTLS, dù đều có khái niệm public/private key.

Không dùng một thiết lập chung kiểu “trust all certificates” để giả vờ thay thế host-key checking trong SFTP; mỗi giao thức cần xác minh peer theo cách của nó.

## 3. Bản đồ secret và certificate của các adapter

| Adapter / ranh giới | Thông tin cần cung cấp | Đối tượng cần xác minh | Rủi ro chính |
|---|---|---|---|
| File local | Quyền filesystem, key mã hóa lưu trữ nếu áp dụng | Path, ownership, permissions | Đọc nhầm file/đọc lộ secret, symlink và quyền quá rộng |
| SFTP inbound/outbound | SSH private key hoặc password; passphrase nếu có | SSH server host key, identity đối tác | MITM, host key thay đổi không kiểm soát, lộ private key |
| HTTP outbound | API token, OAuth client credential; client cert/private key khi mTLS | Server TLS certificate, SAN/hostname | Token lộ, trust-all TLS, sai scope |
| HTTP inbound gateway | Server TLS private key/certificate; CA của client nếu mTLS | Client certificate, OAuth/JWT nếu có | Mất khóa server, xác thực client thiếu, route sai tenant |
| JMS | Broker credential, TLS key/trust material tùy provider | Broker certificate, auth principal | Kết nối nhầm broker, password hết hạn, listener dừng |
| AMQP/RabbitMQ | Username/password hoặc cơ chế xác thực khác; TLS certs | RabbitMQ broker, client certificate nếu yêu cầu | Credential lộ, vhost permission quá rộng |
| Kafka | SASL credential/OAuth token hoặc client cert; TLS trust | Bootstrap brokers và kết nối broker | Phá xác thực, sai principal, lỗi cert broker luân phiên |
| JDBC | Database credential/token/certificate | DB server certificate và hostname | Lộ quyền DB, failover endpoint sai TLS |
| Secret manager | Workload identity hoặc bootstrap credential có kiểm soát | Secret manager endpoint và IAM policy | Lộ bootstrap token, quyền đọc quá rộng |

Chỉ cấu hình TLS ở **một đầu kết nối** chưa đủ. Cần hiểu endpoint nào đóng vai client/server, nơi kết thúc TLS (ứng dụng, reverse proxy, service mesh, broker) và liệu đoạn mạng sau điểm terminate có cần được bảo vệ tiếp hay không.

### 3.1. Một MessageChannel không tự giải quyết transport security

Trong cùng ứng dụng, DirectChannel hoặc QueueChannel chuyển message giữa endpoint; security thường nằm ở **các adapter và lớp ứng dụng**. Nếu một message được đưa qua HTTP/Kafka/SFTP, bí mật và bảo đảm TLS thuộc connection factory/client/server tương ứng.

Đừng vì cùng một IntegrationFlow mà mặc định mọi hop dùng cùng credential, CA hay authorization policy.

### 3.2. Luồng ví dụ

~~~mermaid
flowchart LR
    SFTP["Đối tác SFTP"] --> S["SFTP inbound adapter"]
    S --> CH["MessageChannel"]
    CH --> DB["JDBC outbound"]
    DB --> HTTP["HTTP outbound gateway"]
    HTTP --> K["Kafka outbound"]
    SEC["Secret manager + identity"] -. "SSH key + known_hosts" .-> S
    SEC -. "DB credential + DB CA" .-> DB
    SEC -. "OAuth token / mTLS" .-> HTTP
    SEC -. "SASL/TLS material" .-> K
    AUDIT["Audit + metrics"] -. "metadata, không phải secret" .-> SEC
~~~

Sơ đồ thể hiện **các security contexts riêng**. Không tạo một tài khoản “super integration” dùng chung cho SFTP, DB, HTTP và Kafka.

## 4. Mô hình đe dọa và phân loại thông tin

### 4.1. Các đe dọa thường gặp

- **Credential leakage:** token lộ qua Git, image Docker, CI output, log, trace, exception, actuator dump hoặc snapshot.
- **Machine impersonation / MITM:** bỏ kiểm tra hostname/host key hoặc trust quá rộng.
- **Privilege escalation:** tài khoản DB có DDL/admin trong khi adapter chỉ cần SELECT/UPDATE hạn chế.
- **Cross-environment access:** credential production bị dùng nhầm ở staging.
- **Long-lived access:** token/SSH private key không có vòng đời, không được thu hồi sau thay đổi đối tác.
- **Compromised supply chain:** file secret được nhúng vào artifact, backup hoặc image do nhiều người có quyền đọc.
- **Availability failure:** certificate hết hạn, CA rotation bất ngờ, secret revoke trước khi consumer reload.
- **Replay/misrouting:** retry message sai tenant hoặc dùng credential của service khác.

### 4.2. Tài sản cần kiểm kê

Mỗi kết nối nên có hồ sơ:

| Trường | Ví dụ mô tả |
|---|---|
| Connection ID | sftp-orders-partner-b |
| Owner | Integration team + chủ hệ thống đối tác |
| Environment | production |
| Adapter và hướng | SFTP inbound |
| Authentication type | SSH public-key |
| Secret reference | secret manager path/ID, không chứa giá trị |
| Trust reference | pinned/approved host key hoặc known_hosts path |
| Rotation policy | Chu kỳ theo phân loại rủi ro và hợp đồng |
| Expiry / review | Ngày chứng chỉ/token hết hạn hoặc ngày rà soát key |
| Blast radius | Các flow/tenant bị ảnh hưởng nếu credential ngừng hoạt động |
| Revocation owner | Ai có quyền thu hồi phía client và server |

### 4.3. Nguyên tắc least privilege

- Dùng **identity riêng theo workload, hệ thống đối tác và môi trường** khi phù hợp.
- Chỉ cấp quyền đọc thư mục SFTP cần thiết, không cấp shell/admin nếu không có nhu cầu.
- Database account dùng quyền theo schema/table/operation, không mặc định là superuser.
- Kafka principal chỉ có ACL với topic/group cần thiết; AMQP user chỉ truy cập vhost/exchange/queue cần thiết.
- OAuth token có audience/scope/thời hạn phù hợp, không dùng token chung cho mọi API.
- Secret manager policy chỉ cho service cần thiết đọc những secret references cụ thể.

### 4.4. Phân nhiệm

**Security/PKI team** quản lý CA, policy và phát hành; **platform team** quản lý secret delivery/identity; **integration owner** quản lý flow và kiểm tra hoạt động; **partner owner** phối hợp rollover đối tác. Trong tổ chức nhỏ, một nhóm có thể đảm nhận nhiều vai trò nhưng **quy trình phê duyệt và audit** vẫn cần xác định.

## 5. TLS, mTLS và vòng tin cậy của certificate

### 5.1. Client phải xác minh điều gì?

Một TLS client khi kết nối đến API/DB/broker cần xác minh ít nhất:

1. Chain của server certificate dẫn tới trust anchor được chấp nhận.
2. Certificate còn hiệu lực theo thời gian và policy.
3. Certificate áp dụng đúng hostname/service identity, thường dựa vào **SAN**, không chỉ CN.
4. Certificate/key usage và thuật toán được policy chấp nhận.
5. Quy tắc revocation khi hạ tầng/policy triển khai kiểm tra thu hồi.

**Không chỉ kiểm tra certificate chưa hết hạn.** Một certificate còn hạn nhưng thuộc hostname khác không được coi là server đúng.

### 5.2. Server và client trong mTLS

~~~mermaid
sequenceDiagram
    participant C as Spring Integration HTTP client
    participant S as Partner HTTPS server
    C->>S: ClientHello
    S-->>C: Server cert chain + TLS handshake
    Note over C: Validate chain, SAN/hostname, validity, policy
    S-->>C: CertificateRequest nếu yêu cầu mTLS
    C->>S: Client certificate + proof of private key
    Note over S: Validate client cert, trust, mapped identity
    C->>S: Protected HTTP request
    S-->>C: Protected HTTP response
~~~

Sơ đồ khái niệm; message handshake cụ thể tùy TLS version. Private key **không được gửi qua mạng** trong TLS handshake, client chứng minh sở hữu key bằng thao tác mật mã.

### 5.3. Certificate chain và CA rotation

Server có thể cung cấp leaf certificate và intermediate(s); client đã có trust anchor tin cậy. Nếu thiếu intermediate hoặc đổi CA bất ngờ, handshake có thể thất bại. Khi luân phiên CA, cần có **giai đoạn trust overlap** được phê duyệt: client tin cả chain cũ và mới trong thời gian chuyển tiếp, sau đó gỡ CA cũ theo kế hoạch.

Đừng thêm “toàn bộ public CAs” vào truststore nội bộ chỉ để xử lý một lỗi chain. Trust roots quá rộng làm tăng bề mặt tin cậy.

### 5.4. Truststore và keystore khác nhau

| Trường hợp | Truststore | Keystore / key material |
|---|---|---|
| HTTP outbound TLS | CA tin server | Không cần client key nếu chỉ server-auth TLS |
| HTTP outbound mTLS | CA tin server | Client private key + client certificate chain |
| HTTP inbound TLS | Theo hạ tầng server | Server private key + server certificate chain |
| HTTP inbound mTLS | CA tin client | Server key/cert và client identity mapping |
| Kafka/AMQP/JMS TLS | CA tin broker | Client key/cert nếu broker yêu cầu mTLS |
| JDBC TLS | CA tin DB | Client key/cert nếu driver/server yêu cầu |

JKS, PKCS#12, PEM hay HSM/PKCS#11 chỉ là **định dạng/nguồn lưu trữ**. Loại file không tự chứng minh chứng chỉ thuộc đúng peer, key chưa bị lộ hoặc cấu hình hostname verification đúng.

### 5.5. Revocation, pinning và thời gian

- **Revocation:** certificate bị thu hồi trước expiry có thể cần CRL/OCSP hoặc cơ chế thu hồi khác theo chính sách; mức hỗ trợ phụ thuộc TLS stack.
- **Pinning:** pin một leaf fingerprint có thể gây outage khi đối tác gia hạn; nếu pinning cần thiết, thiết kế rotation overlap và quy trình xác thực ngoài băng.
- **Clock skew:** đồng hồ sai có thể khiến notBefore/notAfter bị đánh giá sai. Đồng bộ thời gian production và monitor lỗi thời gian.
- **Short-lived certificate:** giảm thời gian phơi nhiễm nhưng đòi tự động phát hành/reload đáng tin cậy.

### 5.6. Không vô hiệu hóa xác minh để “chữa cháy”

Những workaround như trust-all TrustManager, tắt hostname verification, chấp nhận mọi SSH host key hoặc chuyển TLS sang plaintext **không phải cách sửa lỗi certificate**. Cần xác định CA, SAN, chain, expiry, thời gian hệ thống hoặc identity mapping đang sai và sửa ở nguồn.

## 6. Lấy và cấp phát secret: tránh đưa giá trị bí mật vào artifact

### 6.1. Bốn nguồn cấu hình phổ biến

| Nguồn | Ưu điểm | Rủi ro / lưu ý |
|---|---|---|
| Biến môi trường được inject lúc chạy | Dễ tích hợp hệ thống deployment | Có thể lộ qua process inspection, crash dump, support tooling; khó reload |
| File/mounted volume chỉ đọc | Hỗ trợ PEM/keystore, có thể update có kiểm soát | Quyền file, thời điểm mount, nguyên tử cập nhật và reload |
| Secret manager API | IAM policy, audit, phiên bản, vòng đời/rotation | Bootstrap identity, mạng, cache, quota và lỗi manager |
| HSM/KMS hoặc managed identity | Hạn chế private key xuất khỏi phần cứng/dịch vụ | Tích hợp provider, latency, lifecycle và chi phí |

**Không nguồn nào mặc định an toàn nếu quản lý sai quyền.** Secret ở environment vẫn có thể bị đọc bởi tiến trình/công cụ có quyền thích hợp. Secret file vẫn có thể bị lộ qua image layer, backup hoặc quyền mount. Secret manager vẫn có thể bị truy cập bởi một workload identity được cấp quyền quá rộng.

### 6.2. Phân biệt bootstrap identity và application secret

Nếu ứng dụng dùng secret manager, nó cần xác thực để lấy secret. Không nên giải bài toán bằng một **bootstrap root token dài hạn** hard-code trong JAR. Ưu tiên identity ngắn hạn gắn với workload/deployment, có audience/role phù hợp và cơ chế thu hồi khi workload bị gỡ.

Ví dụ conceptual:

~~~mermaid
sequenceDiagram
    participant W as Application workload
    participant IAM as Workload identity issuer
    participant SM as Secret manager
    participant A as SFTP/DB/HTTP adapter
    W->>IAM: Xin identity/attestation theo runtime
    IAM-->>W: Credential ngắn hạn theo policy
    W->>SM: Đọc secret reference theo identity
    SM-->>W: Phiên bản secret được phép
    W->>A: Khởi tạo connector với secret trong memory hoặc file mount
    A-->>W: Kết quả kết nối
~~~

Sơ đồ không ngụ ý ứng dụng nên copy secret vào log hoặc persist plaintext trong cache. Thời hạn session, cache TTL và khả năng reload phải được thiết kế.

### 6.3. Một nguồn sự thật cho mỗi credential

Tổ chức quy ước:

- Mỗi secret có **owner, scope, environment, version, rotation policy** và trạng thái active/deprecated/revoked.
- Ứng dụng lưu **reference hoặc path cấu hình**, không lưu giá trị secret thật.
- Nếu rotation diễn ra, nhiều phiên bản có thể **cùng hợp lệ trong một khoảng overlap**.
- Secret được truy cập theo workload role, không cấp wildcard đến mọi môi trường.
- Không ghi giá trị secret vào YAML bài học, tài liệu chia sẻ, Git, issue hay test fixtures.

### 6.4. Tách secret và non-secret configuration

**Non-secret:** hostname, port, topic, queue, channel name, retry policy, timeout, trust reference (tùy phân loại tổ chức).

**Secret:** password, API key, refresh token, OAuth client secret, SASL password, SSH private key, TLS private key, passphrase bảo vệ private key.

Một số metadata như tenant ID, private endpoint, file path có thể là thông tin nhạy cảm theo tổ chức dù không phải secret xác thực. Cần xét phân loại dữ liệu và quyền đọc.

### 6.5. Secret có thể hết hạn khi ứng dụng đang chạy

Nếu ứng dụng chỉ đọc secret lúc startup rồi giữ connector sống hàng tuần, phiên bản mới trên secret manager **không tự đến session đã mở**. Phải quyết định refresh/reconnect strategy cho từng adapter, tránh giả định cập nhật secret reference là đủ.

## 7. Quy ước cấu hình Spring Boot và Spring Integration

### 7.1. Không hard-code credential trong IntegrationFlow

Không viết mật khẩu trong Java source, không đưa private key PEM vào String literal và không truyền token vào log/exception. Một integration flow nên phụ thuộc **connection factory/client bean đã được cấu hình an toàn**:

~~~text
Configuration properties
        |
        +--> Secret references / mounted key material
        |
        v
Validated connector configuration
        |
        +--> SFTP session factory
        +--> HTTP client / request factory / gateway
        +--> JMS/AMQP connection factory
        +--> Kafka producer/consumer factory
        +--> JDBC DataSource/pool
        |
        v
Spring Integration endpoints + MessageChannels
~~~

### 7.2. YAML chỉ chứa placeholder và tham chiếu

~~~yaml
integration:
  partner-b:
    sftp:
      host: sftp.partner.example
      port: 22
      username: order-importer
      private-key: file:/run/secrets/sftp-client-key
      known-hosts: file:/etc/integration/ssh/known_hosts
    http:
      base-url: https://api.partner.example
      ssl-bundle: partner-b-client
      oauth-client-registration: partner-b
  jdbc:
    credential-reference: prod/integration/orders-db
~~~

Đây là **schema application-specific minh họa**; Spring Boot/Spring Integration không tự hiểu các khóa dưới integration.partner-b trừ khi ứng dụng định nghĩa property binding. URL dùng domain ví dụ, không phải endpoint thật. Giá trị file path không chứa private key; secret phải có quyền filesystem phù hợp.

### 7.3. Spring Boot SSL bundle cho PEM

Với các phiên bản Spring Boot hiện đại có hỗ trợ **SSL bundles**, có thể định nghĩa một bundle PEM tham chiếu file certificate/private key/trust anchors, rồi **gắn bundle vào HTTP client hoặc adapter được hỗ trợ**.

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        partner-b-client:
          keystore:
            certificate: file:/run/secrets/partner-client-chain.pem
            private-key: file:/run/secrets/partner-client-key.pem
          truststore:
            certificate: file:/etc/integration/ca/partner-server-ca.pem
~~~

Ở đây:

- **Keystore** biểu diễn client certificate chain và private key để xác thực mTLS;
- **Truststore** biểu diễn certificate/CA dùng xác minh server;
- **Bundle name** chỉ là tham chiếu cấu hình; **không tự động áp dụng** cho mọi RestTemplate, WebClient, Kafka hay SFTP connector.

**Quan trọng:** cách khai báo, API gắn SSL bundle và hỗ trợ reload có thể khác theo phiên bản Spring Boot và loại client. Khi dùng với một adapter, phải cấu hình đúng HTTP client/connection factory; nếu connector không hỗ trợ bundle trực tiếp, cần cầu nối phù hợp của phiên bản thực tế.

### 7.4. Cấu hình typed properties và validate

Ví dụ dùng Spring Boot ConfigurationProperties để quản lý **metadata không phải secret value**:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integration.partner-b")
public record PartnerConnectionProperties(
        Sftp sftp,
        Http http) {

    public record Sftp(
            String host,
            int port,
            String username,
            String privateKey,
            String knownHosts) {}

    public record Http(
            String baseUrl,
            String sslBundle,
            String oauthClientRegistration) {}
}
~~~

Đây là một type mẫu, không có code bật binding/validation. Khi dùng thực tế, cần enable/scan configuration properties, validate required fields và **không tự động in toàn bộ object trong log/actuator** nếu về sau có bổ sung secret property. Record có String reference, không phải private key bytes.

### 7.5. Không nhầm che log với bảo vệ secret

Ẩn password bằng ký tự ****** trong log chỉ giải quyết một đường lộ. Cần còn kiểm soát:

- Actuator endpoints và quyền truy cập configuration/environment;
- Debug logs của HTTP/JDBC client, broker library và connection URL;
- Exception serialization, tracing tags và dump;
- Kịch bản hỗ trợ khách hàng đòi xuất cấu hình;
- Build logs, CI variables, artifact caching, deployment manifests;
- Quyền đọc process/runtime filesystem và backup.

## 8. HTTPS inbound/outbound: TLS, mTLS và OAuth

### 8.1. HTTP outbound gateway: xác minh server trước khi gửi credential

Một HTTP outbound gateway có thể dùng RestTemplate hoặc client được cấu hình phù hợp. Client phải xác minh server TLS chain và hostname, rồi mới gửi Authorization header trong kênh đã được bảo vệ. **Không gửi Bearer token sang một hostname không đúng hoặc URL bị redirect tới host không đáng tin**.

Checklist:

1. URL chỉ dùng **https** theo policy;
2. Trust roots phục vụ xác minh server được quản lý và cập nhật có kiểm soát;
3. Hostname/SAN verification được bật;
4. Nếu dùng mTLS, client private key/cert đúng cho đối tác và scope;
5. OAuth client/token có audience, scope và expiry phù hợp;
6. HTTP redirection, proxy và retry policy không làm rò Authorization tới host khác;
7. Timeout và idempotency được cấu hình để retry không gây side effect trùng.

### 8.2. HTTP inbound gateway: nơi TLS terminate

Khi API được cung cấp qua reverse proxy, ingress hoặc service mesh, TLS có thể terminate ở ranh giới đó. Ứng dụng cần hiểu:

- Ai sở hữu server private key và certificate?
- Kết nối từ proxy vào ứng dụng còn được mã hóa/xác thực không?
- Identity client certificate (nếu có mTLS) được truyền vào backend bằng kênh đáng tin thế nào?
- Backend có tự chấp nhận một header do client gửi mạo danh certificate principal không?
- Phân quyền endpoint/tenant được áp dụng ở lớp nào?

Nếu ứng dụng trực tiếp terminate TLS, secret/key và certificate lifecycle thuộc application server configuration. Nếu proxy terminate, cần có owner và rotation workflow của proxy, không bỏ qua đoạn sau terminate.

### 8.3. mTLS và OAuth thường bổ sung cho nhau

**mTLS** xác thực kết nối hoặc workload identity; **OAuth**/JWT có thể biểu diễn scope và quyền truy cập API. Một certificate hợp lệ chưa tự cho phép gọi endpoint /admin. Một token hợp lệ cũng không nên được gửi qua kết nối chưa xác minh server. Dùng cả hai tùy yêu cầu, không mặc định chúng thay thế nhau.

### 8.4. Token lifecycle

Một integration flow chạy liên tục cần:

- Cache token theo expiry và audience thích hợp, không cache toàn bộ refresh credentials vào log;
- Refresh **trước expiry** với khoảng an toàn và đồng bộ khi nhiều threads cùng yêu cầu;
- Không dùng refresh token/token của tenant này cho tenant khác;
- Phân biệt 401 do token hết hạn với 403 do thiếu quyền;
- Có alert nếu Identity Provider hoặc token endpoint không hoạt động;
- Bảo đảm task/retry không giữ token đã thu hồi trong header quá lâu.

### 8.5. HTTP sample ở mức cấu trúc

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class PartnerOrderPublisher {

    private final PartnerApiClient partnerApiClient;

    public PartnerOrderPublisher(PartnerApiClient partnerApiClient) {
        this.partnerApiClient = partnerApiClient;
    }

    @ServiceActivator(inputChannel = "partnerOrders")
    public void publish(Message<OrderCommand> message) {
        OrderCommand command = message.getPayload();
        partnerApiClient.sendOrder(command);
    }
}

interface PartnerApiClient {
    void sendOrder(OrderCommand command);
}

record OrderCommand(String orderId, String partnerId) {}
~~~

Đây là ví dụ **tách nghiệp vụ khỏi credential plumbing**. PartnerApiClient phải được triển khai với HTTPS client đã bật TLS verification, token supplier/mTLS credential và idempotency policy. Đoạn code không tự tạo client an toàn; cần cấu hình nó trước khi dùng.

## 9. SFTP: quản lý SSH private key và server host key

### 9.1. Phân biệt hai chiều xác thực

**Server authentication:** SFTP client cần biết nó đang nói chuyện với đúng SSH server của đối tác, thường qua **known_hosts hoặc danh tính host key đã được phê duyệt**.

**Client authentication:** SFTP server xác minh username/password hoặc proof-of-possession của SSH private key tương ứng public key được đăng ký.

Hai bước này độc lập. Có private key client đúng **không có nghĩa kết nối đã an toàn nếu bỏ qua kiểm tra server host key**.

### 9.2. Cấp phát host key đáng tin cậy

Đối tác cung cấp fingerprint/host key theo **kênh xác thực ngoài băng** (portal quản trị đã xác minh, quy trình thay đổi được phê duyệt...). Lưu nó trong known_hosts hoặc cấu hình tương đương đúng hostname/port. Không dùng một host key vừa nhận trong kết nối đầu tiên qua kênh không tin cậy để tự tuyên bố peer hợp lệ nếu hệ thống yêu cầu xác thực mạnh.

### 9.3. Cấu hình ý tưởng cho SFTP session factory

~~~text
SftpSessionFactory
  host: sftp.partner.example
  port: 22
  user: integration-reader
  client private key: /run/secrets/sftp-client-key
  private key passphrase: từ secret manager nếu cần
  known hosts: /etc/integration/ssh/known_hosts
  host key verification: BẬT
  session cache: có giới hạn + reconnect/recreate strategy
~~~

Tên API Java cụ thể khác giữa các thế hệ Spring Integration (đặc biệt khi thư viện SFTP underlying thay đổi). **Không copy một ví dụ của phiên bản cũ rồi vô hiệu hóa host key checking khi có lỗi**; đọc đúng tài liệu Spring Integration SFTP/SSH client của dependency đang dùng.

### 9.4. Rotate client SSH key

1. Tạo key pair mới ở nơi được cấp phép, lưu private key ngoài repo.
2. Đăng ký **public key mới** ở phía đối tác trong khi key cũ vẫn được phép trong khoảng overlap.
3. Cập nhật secret reference và cho connector tạo **session mới** dùng key mới.
4. Kiểm tra download/upload/read-only permissions và hiệu quả của host-key verification.
5. Xác minh toàn bộ instances đã chuyển; thu hồi public key cũ ở SFTP server.
6. Dọn key cũ khỏi secret store và backup theo quy trình retention, audit sự thay đổi.

### 9.5. Rotate server host key

Khi server đổi SSH host key, phía client phải kiểm chứng key mới **trước khi chấp nhận**. Có thể chuẩn bị known_hosts chứa cả key cũ và mới nếu client/format và policy hỗ trợ, triển khai staged rollout, rồi loại key cũ khi hoàn tất.

**Không xóa known_hosts toàn bộ hoặc bật allowUnknownKeys=true trong production chỉ để khôi phục kết nối**, vì điều đó làm mất xác minh danh tính SSH server.

### 9.6. SFTP poller, cache và session lifetime

Session đã mở có thể tiếp tục chạy sau khi private key trên volume được thay thế; key mới thường được dùng khi **mở session mới**. Nếu ứng dụng dùng CachingSessionFactory, cần xem cache eviction/reconnect và lifecycle adapter khi rotate. Kiểm tra:

- Có session nào giữ credential cũ không?
- Đóng/refresh session có làm gián đoạn transfer dở không?
- Poller có backoff khi auth fail không?
- File filter/metadata có bị ảnh hưởng sau restart không?
- Hai versions của client key có thể cùng dùng trong giai đoạn chuyển tiếp không?

**Không coi việc một poll tick thành công là bằng chứng mọi cached session đã dùng key mới.**

## 10. JMS: broker authentication, TLS và listener lifecycle

### 10.1. JMS không có một bộ TLS properties chung cho mọi provider

JMS là API messaging. Việc cấu hình TLS, truststore, mTLS và phương thức xác thực tùy **ActiveMQ, IBM MQ, Artemis hoặc provider khác**. Spring Integration JMS inbound/outbound adapters thường nhận một **JMS ConnectionFactory** hoặc listener container đã được cấu hình.

Do đó, trách nhiệm nên tách:

- **Provider ConnectionFactory:** broker URL, TLS trust/key material, authentication mechanism, reconnect policy.
- **Spring Integration JMS adapter:** destination, inbound/outbound mapping, channel, acknowledgment/transaction và error handling.
- **Secret manager:** cấp credential/keystore reference và hỗ trợ rotation.

### 10.2. Kiểm thử bắt buộc

| Tình huống | Mong đợi |
|---|---|
| Broker certificate hợp lệ, hostname đúng | TLS handshake thành công |
| Broker certificate do CA không tin | Kết nối bị từ chối, không fallback plaintext |
| Certificate còn hạn nhưng hostname sai | Kết nối bị từ chối theo policy |
| Username/password bị revoke | Authentication fail, alert đúng identity |
| Client certificate mới trong overlap | Connection mới dùng identity mới |
| Client certificate cũ bị thu hồi | Connection mới không còn chấp nhận key cũ |
| Broker failover | Endpoint mới vẫn phải được xác minh |
| Listener reconnect sau rotation | Container khôi phục có kiểm soát, không phát side effect trùng |

### 10.3. Connection pooling và credential cũ

Một JMS ConnectionFactory/pool có thể giữ physical connections đã xác thực. **Cập nhật password/keystore ở secret store không tự thay credential trong connection cũ.** Cần kế hoạch đóng/mở lại connection hoặc restart có kiểm soát, đồng thời xác minh redelivery/transaction nếu listener đang xử lý message.

### 10.4. JMS authorization

Broker user/service principal nên chỉ được đọc/ghi các queue/topic tương ứng. Không dùng một tài khoản admin chung cho toàn bộ inbound/outbound adapters. Khi chuyển credential, kiểm tra ACL và identity mapping, không chỉ handshake thành công.

## 11. AMQP/RabbitMQ: connection factory, vhost và TLS

### 11.1. Bảo vệ ba lớp

1. **Transport:** TLS và certificate validation của broker.
2. **Authentication:** username/password, client certificate hoặc cơ chế do RabbitMQ triển khai.
3. **Authorization:** vhost, exchanges, queues và permissions.

Một RabbitMQ connection thành công với user admin **không có nghĩa cấu hình đã đạt least privilege**.

### 11.2. Cấu hình ý tưởng

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal.example
    port: 5671
    virtual-host: /orders
    username: order-integration
    ssl:
      enabled: true
    # Password và trust/key material được cấp qua secret/config system.
    # Không lưu plaintext password trong file YAML được commit.
~~~

Đây là minh họa một số property thông dụng của Spring Boot khi dùng Spring AMQP; **không giả định cấu hình bật SSL đã tự xác minh đúng hostname hoặc trust anchors trên mọi phiên bản**. Cần đối chiếu Spring Boot/Spring AMQP version, SSL bundle hoặc RabbitMQ Java client configuration, và kiểm thử certificate không hợp lệ bị từ chối.

### 11.3. Credential rotation và reconnect

Trong quá trình rotate RabbitMQ user password hoặc certificate:

- Tạo credential mới có quyền tương đương nhưng không quá rộng;
- Đưa ứng dụng mới/instances mới chuyển dần, giới hạn reconnect storm;
- Quan sát connection/channel count, unacked message và consumer recovery;
- Đảm bảo consumer không mất message khi connection đóng;
- Chỉ revoke credential cũ sau khi đã xác nhận không còn sử dụng và hết overlap;
- Xác minh publisher confirm/return, DLX/DLQ theo policy khi rotate.

### 11.4. Đừng nhầm TLS error với broker backpressure

Handshake failure thường xuất hiện lúc thiết lập connection. Một message publish timeout có thể do broker flow control, network hoặc xử lý chậm, không nhất thiết secret hết hạn. Dùng taxonomy và metric đúng để không phát động xoay vòng password vô ích.

## 12. Kafka: SASL_SSL, SSL và ACL

### 12.1. Hai mô hình phổ biến

**SSL + client certificate:** Kafka broker xác thực qua TLS client certificate nếu được cấu hình; cần client key/certificate và truststore.

**SASL_SSL:** TLS bảo vệ kênh, SASL xác thực principal bằng mechanism như SCRAM hoặc OAuth theo broker/platform. Không nhầm **SASL_SSL** với **SASL_PLAINTEXT**; production nên chọn transport theo security policy và broker compatibility.

Kafka có thể dùng nhiều authentication mechanisms khác; mô hình thực tế phụ thuộc cluster/platform. Không suy rằng mỗi Kafka cluster đều dùng user/password hay mỗi cluster đều hỗ trợ mTLS.

### 12.2. Sample client config với placeholder

~~~properties
bootstrap.servers=kafka-1.internal.example:9093,kafka-2.internal.example:9093
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
ssl.truststore.location=/run/trust/kafka-client-truststore.p12
ssl.truststore.type=PKCS12
# sasl.jaas.config và mật khẩu truststore được inject qua secret source.
# Không commit SASL username/password vào properties này.
~~~

Đây là Kafka **client properties minh họa**, không phải file đủ để kết nối: phải cấu hình JAAS/callback/credentials theo cơ chế SASL được chọn và quyền truy cập từ runtime. Với PEM hoặc SSL bundle, property layout có thể khác; đọc đúng tài liệu Kafka client và Spring for Apache Kafka của version đang dùng.

### 12.3. Kafka principal và ACL

- **Producer:** quyền WRITE/DESCRIBE với topic cần thiết;
- **Consumer:** quyền READ với topic và group tương ứng;
- **Transactional producer:** quyền theo transactional ID nếu sử dụng;
- **Admin client:** chỉ quyền thao tác quản trị nếu được yêu cầu riêng;
- **Cross-tenant:** tách topic/ACL, authorization và key như thiết kế.

Một client certificate hợp lệ hoặc SASL login thành công chỉ là **authentication**. ACL mới quyết định được publish/consume ở đâu.

### 12.4. Rotation trong Kafka consumer/producer

Khi certificate, SASL password hoặc OAuth token thay đổi:

1. Xác định producer/consumer factories và số ứng dụng đang mở kết nối;
2. Chuẩn bị credential mới và ACL trước khi triển khai;
3. Chuyển các instances theo đợt, refresh/restart clients theo API được hỗ trợ;
4. Theo dõi rebalance, consumer lag, records in-flight, producer errors;
5. Kiểm tra Kafka offset/ack, retry và DLT behavior sau reconnect;
6. Thu hồi phiên bản cũ khi mọi producers/consumers đã chuyển.

**Cập nhật Kafka client properties tại runtime không mặc định làm KafkaProducer/KafkaConsumer đang sống nạp lại SSLContext hoặc SASL credential.** Cần cơ chế cập nhật client cụ thể hoặc tái tạo client.

### 12.5. Handshake thành công nhưng authorization thất bại

Nếu Kafka client đăng nhập được nhưng báo TopicAuthorizationException/GroupAuthorizationException, đó có thể là **ACL hoặc mapping principal** sai chứ không phải certificate chain. Không giải quyết bằng cách vô hiệu hóa TLS.

## 13. JDBC: mật khẩu, token ngắn hạn và server verification

### 13.1. DataSource là điểm quản lý credential

Spring Integration JDBC inbound/outbound adapters thường dùng DataSource. DataSource/pool quyết định kết nối, credential và các tham số TLS. Cần:

- Mỗi application/workload có DB principal chỉ đủ quyền SELECT/INSERT/UPDATE cần thiết;
- Không đặt username/password trong SQL statement/log;
- Trust CA và hostname đúng DB server/failover endpoint;
- Có policy cho TLS, authentication, credential expiry và pool eviction;
- Không tự mở kết nối DB từ error handler với credential admin khi nguồn gặp lỗi.

### 13.2. Driver-specific TLS configuration

Các JDBC drivers có property khác nhau. Ví dụ PostgreSQL JDBC có các SSL modes, trong đó **verify-full** nhằm xác minh certificate và hostname theo cơ chế driver; trong hệ thống khác (MySQL, SQL Server, Oracle...), tên property và policy có thể khác.

Đừng cho rằng một flag “encrypt=true” bất kỳ đảm bảo certificate hostname verification nếu driver đó còn có tùy chọn trust server certificate. Kiểm thử **server cert do CA không tin và sai hostname phải fail**.

### 13.3. Credential rotation với connection pool

HikariCP hoặc pool khác có thể giữ nhiều kết nối đã login. Khi password mới được cấp:

1. DB chấp nhận credential mới trong giai đoạn chuyển tiếp hoặc tạo identity mới;
2. Ứng dụng nhận phiên bản mới và tạo physical connections mới;
3. Dần drain/evict connections cũ theo chiến lược của pool;
4. Không cắt transaction đang chạy giữa chừng nếu có thể tránh;
5. Kiểm tra connection validation và query nghiệp vụ thực tế;
6. Revoke credential cũ sau khi không còn dùng;
7. Giám sát connection failures, pool exhaustion và transaction rollback.

Nếu DB không hỗ trợ đồng thời hai password cho một principal, cân nhắc **hai principal thay phiên** hoặc cơ chế provider hỗ trợ, theo quy định quản trị. Không giả định thay password trong secret manager sẽ tự giữ session DB hiện tại và các reconnect hoạt động.

### 13.4. Database failover và certificate

Khi kết nối sang standby/host khác, certificate cần khớp service endpoint/hostname theo quy tắc TLS. Không tắt verification để “giúp failover”. Cần test cả primary, replica, DNS alias, load balancer và cơ chế chứng chỉ của managed database provider.

### 13.5. SQL query, error channel và secret

Một DataAccessException phát sinh trong poller có thể được publish thành ErrorMessage tùy error strategy. Exception message có thể lộ SQL, DB URL hoặc parameter. Error handler nên log **error category, stage, connection alias, correlation** chứ không mặc định ghi stack trace đầy đủ ở kênh không được kiểm soát.

## 14. File adapters và dữ liệu bí mật trong filesystem

### 14.1. File-based secret là một tài sản production

File adapter có thể xử lý file CSV, XML, JSON hoặc binary chứa dữ liệu nhạy cảm. **Secret quản lý kết nối** và **business data cần bảo vệ** là hai lớp khác nhau, nhưng cùng phải được bảo vệ ở filesystem:

- Quyền truy cập owner/group tối thiểu;
- Không ghi vào thư mục world-readable hoặc log path công khai;
- Mã hóa lưu trữ theo policy nếu cần;
- Kiểm soát symlink/path traversal, tên file và canonical path;
- Atomic write/rename hoặc ready marker để tránh đọc file dở;
- Quarantine và retention rõ ràng sau lỗi;
- Phân quyền truy cập backup/archive.

### 14.2. Không dùng inbox làm nơi lưu private key

Nếu SFTP client private key và inbound File adapter cùng quan sát một directory, filter sai có thể khiến private key bị đưa vào pipeline hoặc archive. **Tách hẳn thư mục secret material khỏi thư mục dữ liệu inbound/outbound**, và không cho file poller quét thư mục secret hay root filesystem.

### 14.3. Tránh đưa secret trong Message headers

Một flow có thể gắn API token vào HTTP outbound request, nhưng không nên sao chép nó vào các Spring Message headers tồn tại lâu hoặc được publish qua ErrorMessage/log. Tốt hơn là để **outbound HTTP client/token interceptor** lấy token ở thời điểm gửi với phạm vi hẹp.

### 14.4. File encryption không thay TLS

Một file được mã hóa ở nơi lưu trữ vẫn cần kết nối SFTP/TLS được xác minh khi truyền. Ngược lại, TLS bảo vệ khi truyền không tự mã hóa file tại đích. Nếu đối tác yêu cầu **message-level encryption/PGP**, đó là một lớp bổ sung với vòng đời key riêng, không thay cho xác minh SSH host key.

## 15. Vòng đời của secret và certificate

### 15.1. Từ phát hành tới thu hồi

~~~mermaid
flowchart LR
    PLAN["Đề nghị + phê duyệt"] --> ISSUE["Generate / Issue"]
    ISSUE --> STORE["Store an toàn"]
    STORE --> DISTR["Distribute theo workload IAM"]
    DISTR --> ACT["Activate + verify"]
    ACT --> OBS["Monitor + review"]
    OBS --> ROTA["Rotate / Renew"]
    ROTA --> DISTR
    OBS --> REVOKE["Revoke / Expire"]
    REVOKE --> CLEAN["Disable + remove references + audit"]
~~~

**Issue:** tạo mới secret/private key và certificate với chủ sở hữu rõ ràng. **Store:** nơi lưu được phân quyền, mã hóa và có audit. **Distribute:** chỉ cấp cho workload được phép. **Activate:** kết nối thử và xác minh identity. **Monitor:** theo dõi thời hạn, thất bại và sử dụng. **Rotate:** cấp phiên bản mới có chuyển tiếp. **Revoke:** loại bỏ phiên bản không còn được phép, kể cả ở bên đối tác.

### 15.2. Các chiều thời gian

| Thời hạn | Đặc điểm | Rủi ro nếu bỏ quên |
|---|---|---|
| Certificate notBefore/notAfter | Khoảng chứng chỉ được coi là có hiệu lực | Kết nối mới fail trước/sau kỳ hiệu lực |
| OAuth access token expiry | Token ngắn hạn | Lỗi 401 và retry storm khi token hết hạn |
| Refresh token/client secret validity | Credential để xin token mới | Không refresh được khi quay vòng |
| SSH private key policy | Key có thể không tự có expiry kỹ thuật | Key cũ tồn tại vô thời hạn nếu không có policy |
| SASL/DB password policy | Thời hạn do broker/DB/identity provider quy định | Listener/pool reconnect thất bại |
| Session/connection lifetime | Kết nối có thể tồn tại lâu sau khi config đổi | Rotation không áp dụng cho session mới hoặc session cũ vẫn tồn tại |
| Trust anchor lifecycle | CA/intermediate/host key được chấp nhận | Client từ chối endpoint mới hoặc tin anchor không còn nên tin |

### 15.3. Rotation và renewal khác nhau nhưng có cùng yêu cầu triển khai

**Renewal** có thể cấp chứng chỉ mới với hoặc không với key pair mới; **key rotation** cần đổi private key. Đối với incident lộ private key, chỉ gia hạn certificate nhưng **tái sử dụng khóa bị lộ** không giải quyết được vấn đề. Chính sách cần nêu lúc nào bắt buộc tạo key mới và thu hồi key cũ.

### 15.4. Secret versioning

Một secret manager có thể hỗ trợ phiên bản:

~~~text
orders-db-credential
  version 12: previous, scheduled for revocation
  version 13: current, verified in canary
  version 14: pending (not active)
~~~

Ví dụ chỉ minh họa version states; API/alias thực của secret manager khác nhau. Nếu ứng dụng tham chiếu alias “latest”, phải biết khi nào alias đổi và runtime có đọc lại không. Dùng version pinning có thể giúp rollback nhưng **không để pin tới key cũ vô hạn**.

### 15.5. Rotation cadence theo rủi ro

Không có một số ngày cố định phù hợp mọi secret. Quyết định dựa trên loại credential, khả năng short-lived, rủi ro lộ, SLA đối tác, tài liệu chính sách và khả năng automation. **Rotation ngay khi nghi ngờ compromise** có thể quan trọng hơn lịch định kỳ.

## 16. Runbook rotation không gián đoạn kết nối

### 16.1. Điều kiện trước khi bắt đầu

1. Kiểm kê chính xác connection ID, app instances và adapter liên quan.
2. Xác định owner và quyền thu hồi ở cả hai đầu kết nối.
3. Xác định có thể **accept old/new đồng thời** không.
4. Xác định reload được tại runtime hay cần restart/recreate connection factory.
5. Đo baseline latency/error rate/consumer lag/poller success.
6. Chuẩn bị canary instance hoặc một kênh kiểm thử tương đương.
7. Lên kế hoạch rollback **an toàn** trước khi revoke old credential.

### 16.2. Các bước chuyển tiếp

~~~mermaid
sequenceDiagram
    participant OPS as Operator / automation
    participant ID as Secret/PKI provider
    participant REM as Remote SFTP/DB/HTTP/broker
    participant APP as Integration app
    OPS->>ID: Issue version NEW
    OPS->>REM: Enable NEW identity/trust
    ID-->>APP: NEW reference available
    OPS->>APP: Canary reload/restart connector
    APP->>REM: Connect with NEW
    REM-->>APP: Auth + authorization verified
    OPS->>APP: Rollout all instances
    APP->>REM: New sessions use NEW
    OPS->>REM: Revoke OLD after verification
    OPS->>ID: Retire OLD version and audit
~~~

**Những hệ thống không hỗ trợ overlap** cần chiến lược thay thế phù hợp (ví dụ blue/green principal, dual certificate chain, ngừng nhận input có kiểm soát hoặc maintenance window). Không hứa zero downtime khi giao thức/nhà cung cấp không hỗ trợ.

### 16.3. Kiểm tra ở từng adapter

| Adapter | Sau khi inject NEW cần làm gì? | Bằng chứng chuyển đổi |
|---|---|---|
| SFTP | Mở session mới, refresh cache phù hợp | Auth thành công với NEW, host key đúng |
| HTTP outbound | Đổi token supplier/SSLContext hoặc tạo client mới | TLS/mTLS handshake và API call thành công |
| HTTP inbound | Reload proxy/server TLS listener theo hạ tầng | Client mới xác minh chain/SAN, mTLS auth |
| JMS | Rebuild/reconnect ConnectionFactory/container nếu cần | Listener nhận/gửi đúng, ack/tx ổn |
| AMQP | Recreate connections/channels theo client policy | Consumer phục hồi, unacked không mất |
| Kafka | Recreate producer/consumer/streams theo runtime | SASL/TLS, ACL, lag, offset an toàn |
| JDBC | New pool connections dùng credential mới | Query hợp lệ, pool health, không rollback hàng loạt |

### 16.4. Đảm bảo transaction/in-flight messages

Nếu một JMS listener đang thực hiện transaction hoặc poller đang tải file lớn, đóng cưỡng bức connection có thể gây retry/redelivery. Rotation nên có **drain hoặc graceful stop** phù hợp:

- Tạm ngừng nhận message mới nếu endpoint hỗ trợ;
- Chờ in-flight operations hoàn tất trong giới hạn thời gian;
- Đóng session/pool theo thứ tự phù hợp;
- Tạo connection factory/client với credential mới;
- Resume và quan sát recovery;
- Dùng idempotency chống side effect trùng nếu redelivery xảy ra.

### 16.5. Rollback đúng nghĩa

Nếu NEW credential không hoạt động, có thể quay lại OLD **chỉ khi OLD vẫn còn hợp lệ và chưa được xác định là compromised**. Nếu OLD bị lộ, không được “rollback” bằng cách tái kích hoạt key lộ; thay bằng key khác an toàn và áp dụng emergency access procedure.

### 16.6. Khi nào được thu hồi OLD?

Chỉ khi:

- Mọi instances/regions/tenants dự kiến đã dùng NEW hoặc đã được cô lập;
- Các connection mới có thể xác thực với NEW;
- Không còn session cũ ngoài phạm vi được chấp nhận;
- Metric và kiểm thử chức năng cho các adapter trọng yếu đều đạt;
- Có owner xác nhận thu hồi theo thay đổi;
- Khả năng recovery sau revoke đã được xem xét.

**Một phép thử “GET /health” thành công chưa đủ** nếu health endpoint không thực hiện handshake bằng key mới. Cần smoke tests có bảo mật thực sự đến từng hệ thống ngoài.

## 17. Certificate expiry, trust rollover và renewal

### 17.1. Quản lý expiry như một công việc có deadline

Certificate inventory nên chứa:

- Subject, SAN, issuer, serial hoặc fingerprint tham chiếu;
- Nơi certificate được dùng: ingress, HTTP client, broker, DB, proxy;
- notBefore/notAfter và thời điểm phát hiện;
- Owner, cách renew, lịch deploy và trường hợp ngoại lệ;
- CA/intermediate chain và trust anchors liên quan;
- Phương thức reload/restart;
- Canary/negative tests trước khi hết hạn.

### 17.2. Kiểm tra certificate identity, không chỉ hạn

~~~text
Certificate checks:
  trusted chain?                 YES
  hostname/SAN match?            YES
  time valid?                    YES
  correct key usage/policy?      YES
  relevant revocation policy?    SATISFIED
  peer mapped to expected ID?    YES
~~~

Checklist này là khái niệm. Khả năng kiểm tra revocation và chính sách EKU/algorithm tùy TLS stack và tổ chức; không khẳng định mọi JVM bật OCSP/CRL mặc định.

### 17.3. CA rollover theo hai pha

1. **Client trust preparation:** cập nhật truststore/bundle để tin CA mới cùng CA cũ trong giai đoạn hợp lệ;
2. **Server certificate switch:** server đổi leaf/intermediate theo CA mới;
3. **Verification:** mọi client/instances handshake thành công với cert mới;
4. **Trust cleanup:** loại bỏ CA cũ khỏi truststore khi không còn yêu cầu;
5. **Audit:** xác nhận không còn trust anchors thừa.

Lỗi thường gặp là đổi server cert trước khi client tin CA mới, dẫn tới outage toàn bộ pollers/clients.

### 17.4. Certificate pinning và certificate renewal

Nếu client pin leaf fingerprint, mỗi renewal tạo certificate mới có thể làm fingerprint thay đổi và gây kết nối fail, kể cả CA đáng tin. Chỉ pin khi policy/bối cảnh thực sự cần; ưu tiên identity/CA verification chuẩn, hoặc thiết kế backup pins/rollover xác thực ngoài băng nếu pinning là bắt buộc.

### 17.5. Đồng bộ thời gian

TLS/SSH/cert/token expiry có thể nhạy với thời gian. Giám sát clock drift của application hosts, proxies và brokers; đồng bộ NTP theo tiêu chuẩn tổ chức. Không sửa lỗi notBefore bằng cách sửa đồng hồ hệ thống thủ công.

## 18. Quản trị connection lifecycle khi secret thay đổi

### 18.1. Cached secret không đồng nghĩa active connection

Một connector có thể chứa:

1. Secret reference và version đang lấy;
2. Secret bytes đang giữ trong runtime;
3. SSLContext/SSH identity được tạo từ secret;
4. Connection/session đang mở;
5. Pool cache và in-flight messages;
6. Retry tasks có credential hoặc session cũ được giữ lại.

Rotation phải xác định **ở tầng nào đã đổi và tầng nào chưa**. Cập nhật secret file không chắc đổi SSLContext; đổi SSLContext không tự đóng session đã được thiết lập.

### 18.2. Ma trận hành vi refresh

| Thay đổi | Cần xem xét |
|---|---|
| API token tự hết hạn | Token supplier, refresh-before-expiry, đồng bộ refresh |
| OAuth client secret đổi | Token client configuration, refresh credential, in-flight requests |
| Server CA đổi | Truststore/SSLContext của client, mở connection mới |
| Client certificate/key đổi | Keystore/SSLContext và identity của connection mới |
| SFTP SSH key đổi | SessionFactory/cache, mở SSH session mới |
| Broker password đổi | ConnectionFactory/pool reconnect |
| DB password đổi | DataSource/pool tạo physical connections mới |

### 18.3. Reload nóng hay rolling restart?

**Hot reload** có thể giảm downtime nhưng cần API thực sự hỗ trợ, consistency khi nhiều threads cùng dùng client và rollback dễ hiểu.

**Rolling restart** thường dễ kiểm soát hơn với nhiều libraries không hỗ trợ reload live, nhưng cần bảo đảm:

- Nhiều instances/consumers đủ phục vụ traffic;
- Graceful stop không làm mất message;
- Health/readiness checks kiểm tra kết nối ngoài đúng cách;
- Kafka consumer rebalance, JMS/AMQP redelivery và poller lease được tính đến;
- Mọi side effect duplicate được bảo vệ bằng idempotency.

### 18.4. Failure mode ở secret manager

Nếu secret manager tạm không khả dụng, ứng dụng phải có policy:

- Với secret đã cache hợp lệ: có thể tiếp tục dùng trong giới hạn được phép;
- Với secret hết hạn hoặc bị revoke: **không tiếp tục dùng chỉ để tránh outage**;
- Với new instance chưa lấy được secret: fail startup hoặc fail readiness phù hợp;
- Với rotation đang diễn ra: retry có backoff/quota và không tạo stampede;
- Với manager compromise: dừng cấp phát, cô lập identity và theo incident runbook.

Không tự tăng TTL cache vô hạn khi provider lỗi. **Availability phải cân bằng với security policy và vòng đời revocation**.

### 18.5. Kết nối dài hạn và observability

Ghi nhận thời điểm credential version được áp dụng trong app, số connections đang sống theo client generation (không gắn secret value), lần handshake mới gần nhất, credential reload result và tỷ lệ authentication failures. Có thể có trường hợp toàn bộ traffic đang chạy trên session cũ, không có handshake mới để chứng minh key đã đổi.

## 19. Observability: giám sát secret, certificate và kết nối mà không rò rỉ dữ liệu

### 19.1. Cần đo cả security lẫn availability

| Metric / signal | Giá trị vận hành |
|---|---|
| cert_days_until_expiry theo connection ID | Phát hiện chứng chỉ sắp hết hạn |
| secret_rotation_age theo loại credential | Nhận diện secret lâu chưa được review/rotate |
| credential_refresh_success_total / failure_total | Kiểm tra token/password refresh |
| tls_handshake_failure_total theo adapter | Phát hiện certificate/trust/hostname lỗi |
| ssh_host_key_verification_failure_total | Báo thay đổi SSH server identity |
| authentication_failure_total | Phân biệt lỗi đăng nhập với network |
| authorization_denied_total | Phát hiện role/scope/ACL thiếu hoặc bị lạm dụng |
| active_connections theo connector generation | Biết kết nối cũ còn tồn tại |
| connection_reconnect_total | Theo dõi reconnect storm |
| poller_last_success_timestamp | SFTP/File/JDBC poller vẫn chạy và có kết quả |
| kafka_consumer_lag / amqp_unacked / jdbc_pool_wait | Đánh giá backlog sau rotation |
| secret_access_denied_total | Phát hiện quyền secret manager sai |

Tên metric là **gợi ý triển khai**, không phải tất cả đều được Spring Integration/Micrometer xuất mặc định. Cần thiết kế instrument ở điểm có dữ liệu đáng tin, tránh nhúng secret value vào label/tag.

### 19.2. Không dùng định danh bí mật làm metric label

Một nhãn metric như accessToken hoặc full certificate subject có thể tạo **high cardinality** và rò rỉ thông tin. Nên gắn:

- Connection ID được quản lý;
- Loại adapter và môi trường;
- Failure category;
- Trạng thái client generation;
- Certificate inventory ID được phép công bố.

Fingerprint/serial đôi khi hữu ích cho audit nhưng cần phân loại, không đưa tùy tiện vào dashboard công khai.

### 19.3. Phân loại lỗi để chẩn đoán

| Lỗi biểu hiện | Nguyên nhân có thể | Xử lý đầu tiên |
|---|---|---|
| PKIX path building failed | Chain hoặc trust anchor không hợp lệ | Kiểm tra chain/CA/truststore |
| Certificate expired / not yet valid | notBefore/notAfter hoặc đồng hồ sai | Kiểm tra cert thực và clock |
| No subject alternative names / hostname mismatch | Identity server không khớp URL | Sửa server cert/SAN hoặc endpoint |
| TLS handshake alert bad_certificate | mTLS client cert/chain/usage không được chấp nhận | Kiểm tra client cert và trust policy hai phía |
| SSH host key mismatch | Server đổi host key, nhầm host hoặc nguy cơ MITM | Dừng kết nối, xác minh fingerprint ngoài băng |
| HTTP 401 | Token hết hạn/sai audience/credential | Kiểm tra token issuer/expiry/cấu hình |
| HTTP 403 | Identity đã xác thực nhưng thiếu quyền | Kiểm tra scope/policy, không tắt TLS |
| Kafka authentication failed | SASL/client cert/identity mapping | Kiểm tra cơ chế auth, secret version |
| Kafka topic authorization failed | ACL topic/group thiếu | Điều chỉnh ACL tối thiểu |
| JDBC login failed | Password/token/principal không hợp lệ | Kiểm tra pool generation và DB auth |
| Timeout / connection refused | Network, firewall, DNS, overload | Kiểm tra hạ tầng trước khi rotate secret |

Đừng log toàn bộ exception hoặc bật network wire logging trên production lâu dài để “tìm password sai”. Nếu debug cần dữ liệu nhạy cảm, phải được phê duyệt, giới hạn thời gian, che thông tin và thu hồi kết quả điều tra sau đó.

### 19.4. Alert dựa trên thời hạn và tác động

Thiết lập cảnh báo **trước ngày hết hạn** đủ để phát hành và triển khai theo SLA của tổ chức. Kết hợp thêm:

- Số pollers không kết nối được kéo dài;
- Tỷ lệ HTTP auth errors vượt ngưỡng;
- Kafka lag/consumer group inactive sau rollout;
- JMS/AMQP reconnect hoặc redelivery bất thường;
- JDBC pool không tạo được physical connection mới;
- Secret manager access denied đột biến;
- Rollover chưa hoàn tất khi sắp revoke OLD;
- Failures ở canary dù certificate mới đã được publish.

Đừng chỉ báo “certificate expires soon” mà không chỉ ra connection ID, owner, issuer, môi trường, phương thức renew và phạm vi ảnh hưởng.

### 19.5. ErrorMessage và errorChannel có thể trở thành đường lộ secret

Khi adapter/poller ném exception, Spring Integration có thể publish **ErrorMessage** tới **errorChannel** mặc định hoặc kênh lỗi riêng, tùy cấu hình. ErrorMessage có payload là Throwable và đôi khi có failedMessage/originalMessage; các đối tượng này có thể chứa HTTP headers, JDBC URL, tên file, request metadata hoặc thông tin sensitive nếu ứng dụng đã đưa chúng vào Message.

Vì vậy:

- Không dùng errorChannel như một nơi lưu/forward nguyên văn credential hoặc message chứa dữ liệu bí mật.
- Không ghi mặc định toàn bộ ErrorMessage, MessageHeaders, Throwable message và payload khi chưa đánh giá nội dung.
- Không gửi stacktrace chứa token/password sang hệ thống alert hoặc dead-letter event không được phân quyền.
- Dùng structured error category, connection ID, adapter, correlation ID và nội dung đã masking.
- Áp dụng retention/authorization cho log, trace, metrics và error recovery queue như các kho dữ liệu có rủi ro.

Việc publish ErrorMessage **không tự refresh token, rotate certificate, rollback transaction hay retry message nguồn**. Error handling phải phối hợp với connection lifecycle và trạng thái nghiệp vụ riêng của File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC.

## 20. Security testing và kiểm thử âm tính

### 20.1. Vì sao test “kết nối thành công” chưa đủ?

Một client cấu hình trust-all vẫn kết nối thành công tới server thật. Một SFTP client bỏ host key checking vẫn tải file được. Một broker user admin có thể publish/consume mọi topic. Vì vậy **positive tests** phải đi cùng **negative tests** xác minh các peer không được tin và quyền không hợp lệ đều bị từ chối.

### 20.2. Ma trận test TLS và certificate

| Test case | Thiết lập | Kỳ vọng |
|---|---|---|
| Valid TLS chain | Server cert hợp lệ, đúng SAN | Connect success |
| Unknown CA | Server cert ký bởi CA không nằm trong trust policy | Handshake fail, không fallback |
| Wrong hostname | Cert còn hạn nhưng SAN khác hostname | Verification fail |
| Expired cert | Cert hết hạn trong test fixture | Reject theo policy |
| Missing intermediate | Server chain không đầy đủ trong môi trường xác minh | Fail nếu không xây được chain |
| Future notBefore | Cert chưa có hiệu lực | Reject, kiểm tra clock |
| Missing client cert | mTLS server yêu cầu certificate | Authentication fail |
| Revoked client identity | Identity bị revoke ở server/broker | New session bị từ chối theo mechanism |
| CA rollover overlap | Client tin CA cũ và mới trong cửa sổ | Hai endpoints hợp lệ cùng được tin |
| CA cleanup | Gỡ CA cũ sau giai đoạn chuyển tiếp | Endpoint cert cũ không còn được chấp nhận |

Kết quả revocation phụ thuộc **policy thực thi và cơ chế revocation có sẵn**, không giả định mọi TLS client tự truy vấn OCSP/CRL. Fixture chứng chỉ test cần tạo đúng các trường SAN, key usage và thời hạn mong muốn.

### 20.3. Ma trận test SFTP

- Host key đúng, client key đúng → kết nối và thao tác được phép thành công.
- Host key sai → client **từ chối** dù username/private key hợp lệ.
- Private key sai hoặc key bị revoke → authentication thất bại.
- Key mới được phép song song với key cũ trong overlap → cả hai xác thực theo kế hoạch.
- Thu hồi key cũ → **new sessions** không thể dùng lại key cũ.
- Session cache được refresh → session mới dùng key mới, file đang chuyển không bị hỏng.
- Network fail giữa transfer → partial file không bị coi là đã xử lý thành công.

### 20.4. Test secret manager

1. Workload identity đúng đọc được secret references của chính nó.
2. Identity khác hoặc staging identity **không** đọc được production secret.
3. Secret version NEW được inject đúng vào canary.
4. Secret manager không khả dụng → ứng dụng xử lý theo startup/runtime policy, không lộ secret.
5. Secret bị revoke → refresh/reconnect không tiếp tục dùng credential cũ khi không còn được phép.
6. Audit trail có principal, connection ID, timestamp, hành động mà **không chứa secret value**.

### 20.5. Test vòng đời kết nối khi rotation

Test không chỉ đọc config property sau khi rotate. Cần tạo **connection mới thật** và kiểm tra:

~~~text
Given OLD credential currently used by connector
And NEW credential issued and enabled at remote system
When application reloads/recreates connection client
Then new physical connection authenticates with NEW
And application can send/receive an authorized test message
When OLD is revoked
Then no new connection succeeds with OLD
And normal traffic remains healthy under NEW
~~~

Đây là kịch bản kiểm thử, không phải một đoạn code runnable. Với Kafka/JMS/AMQP nên xác minh ack/offset và redelivery; với DB kiểm tra transaction; với SFTP kiểm tra file lifecycle; với HTTP kiểm tra idempotency của test request.

### 20.6. Test log không lộ secret

Chèn một **canary value giả, không phải credential production** vào secret provider trong test. Kích hoạt success path, auth fail path, retry, exception và ErrorMessage. Sau đó kiểm tra canary value **không xuất hiện** trong application logs, tracing spans, actuator response, diagnostic output hoặc error event đã serialize.

Không đưa secret thật vào snapshot tests hoặc CI artifacts. Test tự động nên dọn test volumes, cert fixtures và log có dữ liệu nhạy cảm giả theo chính sách.

### 20.7. Load và failure injection

Khi có hàng chục pollers/consumer instances cùng rotate:

- Có xảy ra reconnect storm tới broker/secret manager không?
- Có burst OAuth token refresh làm quá tải issuer không?
- Worker nào giữ SSLContext cũ đến quá deadline?
- Pool eviction có làm hết DB connections không?
- HTTP retries có nhân số request làm side effect trùng không?
- Message broker redelivery có được idempotent xử lý không?

Mục tiêu là chứng minh cả **security invariant** (không chấp nhận identity sai) và **availability invariant** (traffic hợp lệ phục hồi theo SLA đã đặt).

## 21. Case study: chuỗi tích hợp SFTP → JDBC → HTTPS → Kafka

### 21.1. Bối cảnh

Một doanh nghiệp nhận file order từ đối tác B bằng SFTP, lưu dữ liệu vào DB, gọi HTTPS tới đơn vị vận chuyển C rồi publish event lên Kafka. Hệ thống chạy nhiều instances và phải luân phiên credential mà không mất đơn hàng.

Hồ sơ kết nối:

| Kết nối | Loại identity/trust | Owner |
|---|---|---|
| SFTP đối tác B | SSH client private key + verified server host key | Partner integration |
| JDBC orders | DB service principal + TLS server CA | Data platform |
| HTTPS logistics C | OAuth client credential + mTLS cert/trust CA | API integration + security |
| Kafka events | SASL_SSL hoặc mTLS + topic ACL | Messaging platform |
| Secret manager | Workload identity + scoped secret references | Platform security |

### 21.2. Một sự cố rotation

Kỳ thay đổi sắp tới:

1. SFTP đối tác yêu cầu đổi SSH client key.
2. C chuẩn bị chuyển server certificate sang CA mới.
3. DB password được rotate theo policy.
4. Kafka SASL principal được đổi vì tách quyền theo ứng dụng.

Nếu thực hiện đồng loạt không có staging, có thể:

- SFTP pollers ngừng lấy file vì key bị revoke trước khi session mới dùng key mới;
- HTTPS client từ chối CA mới;
- DB pool không tạo thêm connections dù những connections cũ còn sống;
- Kafka consumers bị authentication failure, consumer lag tăng;
- Các retry tasks chạy không kiểm soát, dẫn tới duplicate side effects.

### 21.3. Kế hoạch thay đổi an toàn

**Pha chuẩn bị:** inventory từng kết nối, cấp NEW credentials/certs, tạo rollback plan và owner. SFTP server cho phép public key mới; HTTPS client trust cả CA cũ/mới; DB tạo identity mới hoặc overlap theo capability; Kafka ACL được cấp cho principal mới.

**Pha canary:** một application instance/connector test phiên bản mới, xác minh SFTP list/download, JDBC query, HTTP authenticated request và Kafka publish/consume trên test resources. Negative tests xác nhận host key sai, CA sai và principal thiếu quyền bị từ chối.

**Pha rollout:** triển khai theo đợt, drain in-flight requests/transactions; tạo session/connection mới. Theo dõi sftp poll last-success, DB pool failures, HTTP 401/403/TLS errors, Kafka lag và retries.

**Pha retire:** xác minh toàn bộ instances dùng NEW, thông báo đối tác thu hồi OLD, gỡ CA/host key cũ khi đã qua overlap và không còn cần, kiểm tra logs không chứa secret value.

### 21.4. Khi CA đổi trước khi ứng dụng cập nhật

HTTPS outbound bắt đầu báo lỗi certificate path validation. **Không tắt hostname verification/trust-all.** Tổ vận hành dừng rollout server certificate mới nếu có quyền điều phối, hoặc cập nhật trust anchors được phê duyệt rồi recreate HTTPS client/SSLContext, test đúng SAN/hostname và xác minh API trả kết quả.

Nếu một số requests chưa rõ outcome, phải **đối soát/idempotency** trước khi replay. TLS failure ở handshake thường xảy ra trước HTTP request, nhưng không suy rằng mọi timeout cùng thời điểm đều là handshake failure.

### 21.5. Khi DB password đổi nhưng connection cũ vẫn chạy

Metric queries vẫn thành công từ một số pool connections. Một instance scale-up hoặc pool refill gặp authentication error, gây outage muộn. **Smoke test phải buộc tạo physical connection mới** với credential NEW, không chỉ gọi một query trên connection có sẵn.

### 21.6. Khi SFTP host key thay đổi ngoài kế hoạch

Client phát hiện host key mismatch. Đây là tín hiệu phải **dừng và xác minh ngoài băng**, vì có thể là server migration hợp lệ hoặc MITM. Không chỉnh known_hosts dựa trên fingerprint đọc được từ chính kết nối không đáng tin. Khi key được xác nhận bởi owner, triển khai theo kế hoạch, kiểm thử file state và restart pollers có kiểm soát.

### 21.7. Bằng chứng bàn giao

Một thay đổi rotation hoàn thành khi có:

- Secret/certificate references và version (không lộ giá trị);
- Trust identities đã xác minh theo từng adapter;
- Kết quả smoke test **new connections**;
- Kết quả negative tests cần thiết;
- Bằng chứng các instances/regions đã chuyển;
- Kết quả loại bỏ OLD hoặc ticket chờ loại bỏ có deadline;
- Audit gồm owner, approver, thời điểm và tác động;
- Không còn backlog/retry/unknown outcome vượt SLA.

## 22. Incident response: secret bị lộ hoặc certificate không còn đáng tin

### 22.1. Phân biệt expiry và compromise

**Certificate expiry:** một identity hết hạn theo thời gian; mục tiêu là phục hồi service bằng certificate hợp lệ và root trust đúng.

**Private key compromise:** kẻ tấn công có thể sở hữu material xác thực; cần **revoke/disable key hoặc identity cũ** và điều tra truy cập, không chỉ renew leaf certificate sử dụng cùng private key.

**Host key mismatch:** server identity bất ngờ thay đổi; cần dừng xác minh peer, không mặc định đó là expiry. Một update known_hosts không được phê duyệt có thể biến sai sót thành lỗ hổng MITM.

### 22.2. Runbook khi phát hiện secret exposure

1. **Triage:** xác định loại secret, hệ thống, chủ sở hữu, nơi bị lộ, thời gian có thể bị khai thác.
2. **Containment:** hạn chế đường truy cập, vô hiệu hóa credential nếu có thể mà không làm tăng tác hại ngoài kiểm soát.
3. **Rotate/replace:** tạo key/token/password mới từ nguồn an toàn, cấp quyền tối thiểu, triển khai tới workloads đã xác minh.
4. **Revoke old:** thu hồi ở phía server/IdP/broker/DB; với private key bị lộ, ưu tiên revocation theo chính sách khẩn cấp, không chờ overlap thông thường.
5. **Investigate:** xem audit logs, access logs, token usage, hoạt động bất thường, thời gian bị ảnh hưởng và blast radius.
6. **Remediate exposure:** gỡ secret khỏi nơi lộ; nếu từng commit vào Git, **xóa khỏi lịch sử chỉ là cleanup**, không thay thế revocation.
7. **Verify:** xác minh NEW credential hoạt động, OLD không thể dùng cho new sessions theo cơ chế remote; rà soát session/token đã cấp trước đó.
8. **Recover business flow:** đối soát File/SFTP/JDBC/broker/HTTP messages đã retry, pending, duplicate hoặc có thể bị thao túng.
9. **Report:** ghi evidence và liên hệ incident owner, stakeholders, yêu cầu thông báo theo chính sách/pháp luật áp dụng.

### 22.3. Trường hợp token đã được cấp từ credential cũ

Thu hồi OAuth client secret **không tự thu hồi mọi access token đã phát hành** nếu hệ thống token cho phép chúng tiếp tục đến expiry hoặc có cơ chế khác. Phải kiểm tra chính sách revocation/session invalidation của IdP và resource server. Với broker/DB, các session đã xác thực có thể còn sống cho tới khi bị đóng hoặc hết hạn.

### 22.4. Không ghi secret vào ticket sự cố

Incident ticket nên chứa connection ID, secret version/reference, owner, thời điểm, error category, fingerprint được phép dùng để nhận diện, không chứa private key, password, refresh token, SASL JAAS credentials hoặc access token. Các hệ thống chat, email và ticket có thể là bề mặt lộ mới nếu chia sẻ dữ liệu điều tra sai cách.

### 22.5. Nếu không thể rotate ngay

Sử dụng compensating controls được phê duyệt như giới hạn network ACL, tạm disable affected principal, giảm scope, chặn endpoint rủi ro và giám sát nâng cao. Phải có deadline thay credential; **không coi việc tăng logging là thay thế cho thu hồi key đã bị lộ**.

## 23. Runbook chẩn đoán lỗi kết nối và certificate trên production

### Bước A — Xác định loại lỗi

- **Không kết nối TCP:** DNS, firewall, route, service down, port sai.
- **TLS handshake fail:** CA chain, hostname/SAN, expiry, cipher/protocol, client cert.
- **SSH host key verification fail:** host key không khớp known_hosts.
- **Authentication fail:** password/key/token/principal không hợp lệ.
- **Authorization fail:** scope/role/ACL/tenant không đủ.
- **Operation fail:** kết nối xác thực được nhưng File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC operation lỗi nghiệp vụ.

Đừng tự động rotate mọi secret chỉ vì HTTP timeout hoặc JDBC pool exhausted.

### Bước B — Xác định phiên bản credential thực sự được dùng

1. Kiểm tra secret reference và version đã được cấp cho workload.
2. Kiểm tra app/connector đã reload hay chưa.
3. Kiểm tra pool/session/SSLContext/client generation và lifecycle.
4. Kiểm tra phía remote còn chấp nhận OLD/NEW không.
5. Kiểm tra identity mapping và authorization sau authentication.
6. Kiểm tra thời gian hệ thống và certificate notBefore/notAfter.

Chỉ so sánh cấu hình mới trong Git/deployment không đủ nếu các connections cũ vẫn tồn tại.

### Bước C — Kiểm tra từng ranh giới

| Adapter | Phần kiểm tra thiết yếu |
|---|---|
| SFTP | Host fingerprint đã được xác minh ngoài băng, client key, username, remote permissions, session cache |
| HTTP client | URL host và SAN, CA chain, mTLS key, OAuth token audience/scope, redirect |
| HTTP inbound | Ingress TLS terminator, client cert mapping nếu dùng, authorization, proxy trust |
| JMS | Provider-specific trust/keystore, broker principal, destination ACL, listener reconnect |
| AMQP | Broker TLS, vhost permission, username/cert, consumer recovery |
| Kafka | security.protocol, SASL mechanism/client cert, bootstrap host, principal ACL, offset/lag |
| JDBC | Driver TLS mode, host verification, DataSource credentials, pool eviction, DB role |
| File | Source path ownership, permissions, secret directory separation, quarantine |

### Bước D — Khôi phục mà không giảm mức bảo mật

- Sửa chain/CA/SAN hoặc cập nhật endpoint đã được phê duyệt;
- Cấp credential đúng scope và version;
- Refresh/recreate connector hoặc rolling restart có kiểm soát;
- Kiểm thử kết nối mới và operation thực tế;
- Không tắt hostname/host key verification hoặc dùng admin account làm giải pháp lâu dài;
- Giữ retry hữu hạn, không tạo kết nối hàng loạt làm cạn resources.

### Bước E — Kiểm tra thông điệp nghiệp vụ

Sau khi kết nối phục hồi:

1. File/SFTP có file nào tải dở, đã filter accepted nhưng chưa xử lý?
2. HTTP POST có request nào outcome unknown?
3. JMS/AMQP có messages redelivered, unacked hoặc vào DLQ?
4. Kafka có lag, offset commit không đúng hoặc records vào DLT?
5. JDBC có transaction rollback/partial side effect?
6. Retry có thể làm tạo trùng order/shipment không?

**Có một handshake mới thành công không có nghĩa toàn bộ integration flow đã phục hồi về trạng thái nghiệp vụ đúng.**

### Bước F — Đóng sự cố

Ghi nhận root cause, credential/cert version, cách trust được xác minh, thời gian ảnh hưởng, messages impacted, retry/reconciliation, rollback/rotation steps và prevention. Bàn giao bằng chứng không chứa secret.

## 24. Anti-pattern và cách sửa

| Anti-pattern | Rủi ro | Hướng khắc phục |
|---|---|---|
| Commit password/API key/SSH private key vào Git | Secret lộ qua repo/history/CI | Secret manager/identity, revoke key cũ |
| Đóng gói private key trong JAR/image | Nhiều bản artifact có secret | Inject lúc runtime, quản lý quyền |
| Tắt TLS hostname verification | Dễ bị giả mạo máy chủ | Sửa SAN/CA/endpoint |
| Dùng trust-all TrustManager | Chấp nhận certificate không đáng tin | Truststore hạn chế và negative test |
| Tắt SSH host key checking | MITM qua SFTP | Verified known_hosts/host key policy |
| Dùng cùng credential cho dev và production | Cross-environment compromise | Tách identity, role và secret references |
| Dùng broker/DB admin credential | Blast radius quá rộng | Principal và ACL tối thiểu |
| Coi public certificate là bí mật nhưng để private key public | Bảo vệ nhầm tài sản | Kiểm kê public/private key đúng |
| Chỉ xem certificate expiry, bỏ SAN/chain | TLS sai identity vẫn bị tin | Full certificate verification |
| Pin leaf fingerprint không có rollover plan | Outage khi renew | Backup pin/trust policy và overlap |
| Rotate server trước khi trust client CA mới | Handshake fail diện rộng | Prepare trust trước, rollout có giai đoạn |
| Revoke OLD trước khi instances dùng NEW | Toàn bộ connector bị mất quyền | Canary, overlap khi an toàn, staged revoke |
| Secret file đã đổi nhưng pool vẫn dùng OLD | Outage muộn khi reconnect | Recreate physical connections, verify |
| Chỉ test HTTP GET /health để xác minh mTLS mới | Không chứng minh client dùng NEW | Test new handshake và identity |
| Token hết hạn trong long-running poller | Retry storm, HTTP 401 | Token supplier refresh và metrics |
| Log exception và toàn bộ Message headers | Lộ credentials/PII | Structured logging và masking |
| Lưu Throwable nguyên vẹn trong Kafka error event | Rò secret/serialization không ổn | Chuẩn hóa error event an toàn |
| Cho secret manager read-all | Workload bị compromise đọc mọi secret | Scoped IAM policy, workload identity |
| Không monitor poller khi error count bằng 0 | Poller chết im lặng | Last-successful-poll, backlog |
| Không kiểm tra failover hostname | DB/broker failover phá TLS | Test SAN/CA cho endpoints mới |
| Chạy retry vô hạn khi auth fail | Lockout, quá tải, che giấu compromise | Phân loại lỗi, backoff/alert |
| Rollback về key đã bị compromise | Tiếp tục mở đường tấn công | Emergency replacement, không tái dùng |
| Dùng file inbox chung với key material | Poller có thể đọc nhầm secret | Separate mount và filesystem ACL |
| Quên revoke credential đối tác cũ | Tồn dư quyền truy cập | Revocation và audit sau rollout |
| Coi mTLS đồng nghĩa authorization | Peer hợp lệ nhưng quyền quá rộng | ACL/scope/tenant authorization |

## 25. Checklist go-live cho quản lý secret/certificate

### A. Kiểm kê và trách nhiệm

- [ ] Mỗi File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC connection có ID và owner.
- [ ] Biết vị trí endpoint, môi trường, giao thức và authentication mechanism.
- [ ] Secret references/version được lưu an toàn, không lưu giá trị vào repo.
- [ ] Có blast-radius analysis và revocation owner.
- [ ] Có SLA rotation/renewal và cảnh báo trước expiry.

### B. Transport trust và identity

- [ ] HTTPS/JMS/AMQP/Kafka/JDBC dùng TLS phù hợp security policy.
- [ ] Chain, SAN/hostname, validity và trust anchors được xác minh.
- [ ] Nếu dùng mTLS, client key/cert và server trust policy được cấu hình.
- [ ] SFTP SSH server host key được xác minh bằng known_hosts/fingerprint đáng tin.
- [ ] Không tồn tại trust-all, skip host-key verification hoặc plaintext fallback không được phê duyệt.
- [ ] Failover endpoints có certificate và identity đúng.

### C. Least privilege và bí mật

- [ ] Identity khác nhau theo workload/environment/partner khi phù hợp.
- [ ] DB role, Kafka topic ACL, AMQP vhost permission, JMS destination ACL ở mức tối thiểu.
- [ ] OAuth token có scope/audience và thời hạn phù hợp.
- [ ] Secret manager sử dụng workload identity và scoped read.
- [ ] File key material chỉ đọc bởi process/owner được phép.
- [ ] Không đưa secret vào Message headers/logs/traces/actuator/CI artifacts.

### D. Rotation và connection lifecycle

- [ ] Có đường issue → distribute → activate → verify → revoke → retire.
- [ ] Đã xác định adapter nào reload live, adapter nào cần restart/recreate.
- [ ] Có canary test dùng **connection mới thật** với NEW.
- [ ] Có overlap khi phù hợp và rollback plan không dùng key compromised.
- [ ] Pool/session cache được refresh có kiểm soát.
- [ ] Sau revoke, OLD không còn dùng cho new sessions theo thiết kế.
- [ ] Trạng thái File/JMS/AMQP/Kafka/JDBC được đối soát sau reconnect.

### E. Kiểm thử và vận hành

- [ ] Test hợp lệ và không hợp lệ: CA, SAN, expiry, host key, credential, ACL.
- [ ] Test mTLS, OAuth refresh, token expiry, SFTP SSH key rollover.
- [ ] Test secret manager unavailable và access denied.
- [ ] Test rotation với nhiều app instances/in-flight messages.
- [ ] Test no-secret-in-logs bằng canary value giả.
- [ ] Có metrics expiry, auth failures, TLS/SSH errors, pool reconnect và backlog.
- [ ] Có runbook incident compromise, expiry, CA rollover và rotation thất bại.
- [ ] Có audit, approver và evidence trước khi ghi nhận production ready.

## 26. Câu hỏi tự kiểm tra

**Câu 1. Secret và certificate có giống nhau không?**

**Đáp án:** Không. Secret là dữ liệu cần giữ bí mật như password, token hoặc private key. Một X.509 certificate thường mang public key và thông tin nhận diện do CA xác nhận; private key tương ứng mới là bí mật. Certificate/truststore vẫn cần bảo vệ tính toàn vẹn và quản lý vòng đời.

**Câu 2. Dùng HTTPS có đồng nghĩa API đã được authorize đúng không?**

**Đáp án:** Không. HTTPS xác thực server (và client nếu dùng mTLS) và bảo vệ kênh truyền. Authorization endpoint/resource vẫn cần scope, role, principal và tenant policy.

**Câu 3. Vì sao SFTP không dùng truststore X.509 của HTTPS để xác minh host?**

**Đáp án:** SFTP dùng SSH. Server được xác minh bằng SSH host key/known_hosts hoặc một cơ chế SSH trust tương ứng, khác với chain CA/TLS/SAN của HTTPS.

**Câu 4. Nếu client SSH có private key đúng nhưng tắt host key checking, có an toàn không?**

**Đáp án:** Không. Nó có thể bị kết nối đến SSH server giả. Cần xác minh host key qua nguồn đáng tin trước khi gửi thông tin xác thực và dữ liệu.

**Câu 5. mTLS có truyền private key tới server không?**

**Đáp án:** Không. Private key được dùng để chứng minh quyền sở hữu thông qua thao tác mật mã; certificate/public key có thể được trao đổi, private key phải ở nơi bảo vệ.

**Câu 6. Truststore và keystore khác nhau như thế nào?**

**Đáp án:** Truststore giữ trust anchors/certificates để xác minh peer. Keystore/key material có thể giữ private key và certificate chain của danh tính client/server. Một ứng dụng mTLS có thể cần cả hai.

**Câu 7. Certificate chưa hết hạn có đủ để tin server không?**

**Đáp án:** Không. Phải kiểm tra chain/trust anchor, SAN/hostname, tính hợp lệ, chính sách mục đích sử dụng và revocation nếu được yêu cầu.

**Câu 8. Vì sao không bật trust-all khi gặp PKIX path building failed?**

**Đáp án:** Trust-all bỏ qua xác minh CA, cho phép kẻ tấn công giả mạo server. Phải sửa chain, trust anchors và identity đúng cách.

**Câu 9. Cập nhật file certificate trên volume có làm RestTemplate/WebClient đang sống dùng certificate mới không?**

**Đáp án:** Không thể mặc định. Client/SSLContext/connection pool có thể đã giữ key material cũ. Cần cơ chế reload thực sự hoặc tái tạo client/connection phù hợp với phiên bản.

**Câu 10. Rotation DB password xong nhưng query cũ vẫn chạy. Đã chứng minh pool dùng NEW chưa?**

**Đáp án:** Chưa. Physical DB connections cũ có thể còn được dùng. Cần tạo connection mới để xác minh authentication bằng NEW, rồi drain/evict connections cũ.

**Câu 11. Khi nào nên thu hồi OLD credential?**

**Đáp án:** Sau khi các instances đã được xác minh dùng NEW và không còn đường cần OLD, trừ tình huống compromise cần thu hồi khẩn theo incident policy. Không được kéo dài overlap vô hạn.

**Câu 12. Secret bị lộ trong Git và đã xóa commit chứa nó. Secret đã an toàn chưa?**

**Đáp án:** Chưa. Secret có thể tồn tại trong lịch sử, fork, cache, artifacts. Phải revoke/rotate credential và điều tra phạm vi lộ; cleanup repo chỉ là bước bổ sung.

**Câu 13. Access token đã phát hành có tự bị thu hồi khi client secret đổi không?**

**Đáp án:** Không mặc định. Phụ thuộc cách IdP/resource server phát hành, kiểm tra và thu hồi token. Cần xét token đang lưu hành và phiên làm việc hiện tại.

**Câu 14. Vì sao secret manager vẫn cần least-privilege IAM?**

**Đáp án:** Vì một workload identity bị compromise có thể đọc mọi secret mà nó được cấp quyền. Secret manager có audit không đồng nghĩa policy rộng là an toàn.

**Câu 15. Kafka SASL_SSL bảo vệ những thành phần nào?**

**Đáp án:** TLS bảo vệ kênh truyền, SASL xác thực principal theo mechanism được chọn. Topic/group ACL và transaction authorization vẫn cần cấu hình riêng.

**Câu 16. Kafka client xác thực thành công nhưng bị TopicAuthorizationException. Nên tắt SSL không?**

**Đáp án:** Không. Đây thường là vấn đề authorization/ACL hoặc principal mapping. Kiểm tra quyền tối thiểu cho đúng topic và group.

**Câu 17. JMS và AMQP có cùng properties TLS không?**

**Đáp án:** Không. JMS có nhiều providers và TLS thường do provider ConnectionFactory quyết định. AMQP/RabbitMQ có cấu hình riêng của client/connection factory. Phải đối chiếu version và broker.

**Câu 18. Một certificate đổi CA làm các clients cùng fail. Trình tự chuẩn nên là gì?**

**Đáp án:** Client trust preparation trước, server certificate switch sau, test handshake và cleanup old CA cuối cùng. Nếu không thể overlap cần maintenance/transition plan.

**Câu 19. Vì sao leaf fingerprint pinning có thể gây outage khi renewal?**

**Đáp án:** Certificate mới thường có fingerprint khác. Nếu pinning không hỗ trợ backup pins/overlap và quy trình cập nhật, client sẽ từ chối một server hợp lệ.

**Câu 20. SFTP host key mismatch có nên được sửa bằng cách xóa known_hosts không?**

**Đáp án:** Không. Phải dừng kết nối, xác minh host key mới qua kênh ngoài băng được phê duyệt và cập nhật trust có kiểm soát.

**Câu 21. Một secret manager bị outage, có thể dùng token đã hết hạn vô thời hạn để giữ hệ thống chạy không?**

**Đáp án:** Không. Caching và fallback phải tuân thủ expiry/revocation policy. Nếu không thể cấp credential hợp lệ, fail readiness hoặc chuyển trạng thái dịch vụ phù hợp, không bỏ qua security controls.

**Câu 22. Vì sao không nên gắn API key trực tiếp vào Message headers?**

**Đáp án:** Headers có thể được truyền qua nhiều channel, giữ lâu, ghi log hoặc xuất hiện trong ErrorMessage và traces. Nên gắn credential sát outbound client/interceptor với phạm vi hẹp.

**Câu 23. HTTP POST timeout sau rotation có chắc server chưa xử lý request không?**

**Đáp án:** Không. Nếu request đã gửi trước timeout, server có thể đã commit. Dùng idempotency key hoặc reconciliation để tránh tạo side effect trùng.

**Câu 24. Bằng chứng nào cho thấy rotation thành công end-to-end?**

**Đáp án:** NEW được dùng trong **new connections thật**, auth và authorization đúng, thao tác nghiệp vụ thử thành công, mọi instances đã chuyển, OLD được thu hồi theo policy, metrics/backlog ổn và không có dữ liệu sai hoặc message mất/trùng.

**Câu 25. Khi không thấy TLS errors, poller có chắc hoạt động bình thường?**

**Đáp án:** Không. Poller có thể ngừng chạy hoặc không nhận file mà không ném lỗi. Phải đo last successful poll, số message nhận và backlog theo SLA.

## 27. Kết luận và hướng đọc tiếp

Trong **Spring Integration Adapters**, quản lý secret và certificate không phải một bước cấu hình rời rạc. Nó gắn trực tiếp với **danh tính workload, quyền truy cập hệ thống ngoài, TLS/SSH peer verification, lifecycle của connection factories, pools, sessions, listener containers, pollers và các MessageChannels** mang thông điệp nghiệp vụ.

Một giải pháp production nên đáp ứng:

1. **Không lưu secret trong mã nguồn hoặc artifact;** dùng nguồn cấp phát được phân quyền, có audit và version.
2. **Xác minh đúng peer** bằng TLS chain/SAN/hostname hoặc SSH host key được phê duyệt; không dùng trust-all/skip verification.
3. **Áp dụng least privilege** cho DB, HTTP/OAuth, JMS/AMQP/Kafka, SFTP và secret manager.
4. **Xoay vòng có kế hoạch:** cấp NEW, chuẩn bị trust/permission, triển khai canary, tạo connection mới, xác minh, rồi thu hồi OLD.
5. **Hiểu các kết nối tồn tại lâu:** thay file/secret reference không tự đồng nghĩa SSLContext/session/connection pool đã dùng phiên bản mới.
6. **Quan sát và kiểm thử tiêu cực:** peer không tin cậy phải bị từ chối; secret lộ không được xuất hiện trong log; expiry/rotation có cảnh báo.
7. **Đối soát kết quả nghiệp vụ:** một connector phục hồi không chứng minh mọi file, HTTP request, JDBC transaction hoặc broker message đã xử lý đúng sau sự cố.

Khi vận hành các luồng File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC, hãy quản lý đồng thời **credential lifecycle** và **message lifecycle**. Secret/certificate bảo vệ **ai được kết nối và kết nối tới ai**, còn idempotency, ack, transaction, retries và recovery quyết định **message có được xử lý đúng sau khi kết nối gián đoạn hay không**.

### Tài liệu chính thức nên tham khảo theo phiên bản dự án

- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): adapters, endpoint lifecycle, pollers và channel error handling.
- [Spring Integration SFTP Support](https://docs.spring.io/spring-integration/reference/sftp.html): SSH session factory, host key và kết nối SFTP.
- [Spring Boot SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): SSL bundles, PEM/keystore và cấu hình client/server.
- [Spring Security OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): OAuth client registration, authorized clients và token management.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/): RabbitMQ connection factory, TLS, lifecycle và messaging.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): client/broker security, consumers, producers và listener containers.
- [Apache Kafka Security](https://kafka.apache.org/documentation/#security): TLS, SASL và ACL theo phiên bản Kafka.
- [PostgreSQL JDBC SSL](https://jdbc.postgresql.org/documentation/ssl/): driver TLS mode và xác minh server.
- [Java Secure Socket Extension Reference](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): JSSE, trust/key material và TLS.

**Ghi chú:** ví dụ YAML, Java, properties, JSON, Mermaid và sơ đồ trong bài nhằm minh họa kỹ thuật. Cấu hình cụ thể thay đổi theo phiên bản Spring Boot/Spring Integration, JDK, SSH implementation, broker/DB driver và nhà cung cấp secret manager. Trước production, phải kiểm tra API của phiên bản đang dùng, triển khai đúng policy bảo mật và kiểm thử trên môi trường đại diện hệ thống thật.
