# Xác thực, TLS và quản lý bí mật trong cấu hình ứng dụng

Một dịch vụ Java 21 kết nối với cơ sở dữ liệu NoSQL qua mạng nội bộ. Trong môi trường phát triển, lập trình viên chỉ cần host, port và mật khẩu thử nghiệm. Khi triển khai production, mọi việc phức tạp hơn: kết nối có thể đi qua load balancer và nhiều region; database yêu cầu TLS; tài khoản ứng dụng chỉ được truy cập một số collection/table; mật khẩu hoặc token có thể bị xoay vòng trong lúc connection pool vẫn đang mở; chứng chỉ máy chủ có thể hết hạn; hệ thống quản lý bí mật có thể tạm không truy cập được.

Một thiết lập tưởng nhỏ như **bỏ kiểm tra hostname để sửa lỗi TLS**, **đặt password trong application.yml**, hoặc **ghi nguyên connection URI vào log** có thể biến cấu hình kết nối thành một lỗ hổng bảo mật nghiêm trọng. Trái lại, siết cấu hình sai cách cũng có thể làm ứng dụng không khởi động được, pool liên tục reconnect, hoặc một lần xoay vòng chứng chỉ gây outage toàn bộ dịch vụ.

Bài học thuộc **Database No SQL → Kết nối Java** tập trung vào ba lớp phải thiết kế cùng nhau:

1. **Xác thực và phân quyền:** chứng minh ứng dụng là ai, và giới hạn nó được đọc/ghi tài nguyên nào.
2. **TLS và xác minh danh tính máy chủ:** bảo vệ dữ liệu trên đường truyền và ngăn client kết nối nhầm máy chủ giả.
3. **Quản lý bí mật trong cấu hình ứng dụng:** lấy, sử dụng, làm mới và thu hồi mật khẩu, token, private keys mà không làm rò rỉ qua Git, logs, biến môi trường, CI/CD hoặc memory diagnostics.

Nội dung đi từ mô hình đe dọa tới Java JSSE, truststore/keystore, mTLS, MongoDB/Cassandra/Redis/DynamoDB, Spring Boot, secret stores, xoay vòng credentials/chứng chỉ, vận hành và bài tập thực hành.

> **Nguyên tắc:** **TLS không thay authentication; authentication không thay authorization; secret manager không tự đảm bảo ứng dụng dùng bí mật an toàn.** Cần kiểm tra toàn bộ đường đi từ runtime identity → lấy secret → bắt tay TLS → xác thực database → thực thi câu lệnh theo quyền tối thiểu → ghi log và vận hành.

> **Phạm vi:** Các đoạn mã là ví dụ cho Java 21 và các dòng thư viện phổ biến. API/config cụ thể của driver và cloud service có thể khác theo phiên bản. Hostnames, secret paths, tài khoản và thông tin trong ví dụ là giả lập, không phải thông tin truy cập thật.

## 1. Kết nối NoSQL an toàn bảo vệ những gì?

Một application request có thể đi qua:

~~~~mermaid
flowchart LR
    USER["Caller"] --> API["Java service"]
    API --> IDENT["Runtime identity"]
    IDENT --> SECRET["Secret manager / IAM"]
    API --> TLS["TLS: verify server"]
    TLS --> AUTH["Database authentication"]
    AUTH --> RBAC["Database authorization"]
    RBAC --> DATA[("NoSQL data")]
    API --> OBS["Logs / metrics / traces"]
~~~~

Một kết nối an toàn phải bảo vệ:
- **Confidentiality:** người ngoài không đọc được dữ liệu hoặc credentials trên đường truyền.
- **Integrity:** message không bị thay đổi bởi một bên trung gian không được tin cậy.
- **Server authenticity:** client chắc mình đang nói chuyện với database endpoint hợp lệ.
- **Client identity:** server biết service principal nào đang kết nối.
- **Least privilege:** service chỉ có quyền cần thiết, trên tài nguyên cần thiết.
- **Secret confidentiality:** password, token, private key không bị lộ qua file, Git, image, shell history, URI, logs hoặc debugging.
- **Availability:** cert/secret rotation và lỗi mạng không làm tất cả instance mất khả năng phục vụ.
- **Auditability:** biết principal nào thực hiện hành động gì, nhưng không in secret hoặc dữ liệu nhạy cảm dư thừa.

### 1.1. Một mô hình đe dọa nhỏ

| Nguồn rủi ro | Cách tấn công/sự cố | Tác động |
| --- | --- | --- |
| Network interceptor | Nghe lén kết nối không mã hóa | Lộ dữ liệu, password, tokens |
| DNS/route poisoning | Client kết nối server giả | Credential theft, data tampering |
| Secret trong Git | Repository hoặc artifact bị lộ | Truy cập trái phép database |
| Account đặc quyền | Một app bị chiếm quyền dùng root/admin | Phá dữ liệu diện rộng |
| Logs/APM | In connection URI hoặc Authorization header | Secret tồn tại lâu trong hệ log |
| Container image | Bake mật khẩu vào layer/image | Ai đọc image cũng có credential |
| TLS misconfiguration | Trust-all hoặc bỏ hostname verification | MITM dù có encryption |
| Cert hết hạn | Handshake thất bại đồng loạt | Outage khi reconnect/restart |
| Rotation sai thứ tự | Thu hồi credential cũ trước khi app dùng credential mới | Connection/auth failures |
| Multi-tenant data access | Query không lọc tenantId hoặc RBAC quá rộng | Lộ dữ liệu chéo tenant |
| Secret-store outage | Runtime phụ thuộc read secret trên mỗi request | Cascade failure |
| Compromised workload identity | Kẻ tấn công gọi secret store bằng service identity | Đánh cắp secret đúng quyền |

Không có một checkbox duy nhất xử lý tất cả rủi ro trên.

## 2. Phân biệt authentication, authorization và encryption

Ba khái niệm thường bị lẫn:

| Khái niệm | Trả lời | Ví dụ |
| --- | --- | --- |
| **Authentication (AuthN)** | Ứng dụng là ai? | Username/password, mTLS client cert, IAM signed request |
| **Authorization (AuthZ)** | Ứng dụng được phép làm gì? | Read collection Orders, update key prefix đã cấp, không được drop database |
| **Transport encryption (TLS)** | Ai có thể nhìn/sửa dữ liệu khi truyền? | TLS bảo vệ TCP/HTTP connection |
| **Server identity verification** | Đây có đúng server dự định? | Chain CA tin cậy + hostname/SAN match |
| **Secret management** | Lấy và bảo vệ vật chứng xác thực thế nào? | Secret manager, workload identity, rotation |
| **Encryption at rest** | Dữ liệu lưu trên disk/snapshot được bảo vệ ra sao? | KMS-backed storage encryption |

### 2.1. TLS không tự cấp quyền ghi

Một client có thể thiết lập TLS hoàn hảo với database rồi nhận:

~~~~text
Authentication failed
~~~~

hoặc:

~~~~text
Permission denied: dropCollection
~~~~

Điều này bình thường:
- TLS xác minh máy chủ và bảo vệ kênh.
- AuthN xác định principal.
- AuthZ kiểm tra quyền của principal đối với operation.

### 2.2. Mật khẩu đúng vẫn cần TLS

Nếu client gửi username/password qua đường không mã hóa, attacker trên đường mạng có thể lấy password. Một số protocol có cơ chế challenge-response không gửi mật khẩu nguyên văn, nhưng **vẫn cần TLS để bảo vệ transport, metadata và dữ liệu nghiệp vụ** theo policy.

### 2.3. TLS khác mã hóa dữ liệu lưu trữ

TLS bảo vệ **in transit**. Snapshot, WAL, backup, disk hoặc logs có thể vẫn chứa dữ liệu nếu không có encryption-at-rest và access controls.

### 2.4. RBAC database không nhất thiết bảo vệ tenant

Một service principal có quyền read toàn collection Orders. Nếu ứng dụng quên filter tenantId, nó có thể trả dữ liệu tenant khác.

Cần hai tầng:
- Database-level least privilege.
- Application-level authorization cho tenant/user/action.
- Khi engine có hỗ trợ row/item-level IAM conditions hoặc policy, xem xét thêm nhưng không tự cho là thay thế kiểm tra nghiệp vụ.

## 3. Những phương thức xác thực thường gặp trong NoSQL

### 3.1. Username/password

Ví dụ các cơ chế như:
- SCRAM hoặc cơ chế mật khẩu của MongoDB.
- SASL/username-password theo driver và database.
- Redis ACL user/password.
- Basic auth trên HTTPS với một số search/data services.

Lưu ý:
- Phải dùng giao thức được server hỗ trợ và cấu hình khớp.
- Password cần lấy từ nguồn bảo mật, không hardcode.
- Principal cần quyền tối thiểu.
- Không sử dụng tài khoản admin/root chung cho ứng dụng.
- Không in password trong exception/URI/log.
- Secret rotation có thể cần thay connection pool.

### 3.2. Client certificate / mTLS

Trong **mutual TLS**, không chỉ client xác minh server, server còn yêu cầu client trình certificate và chứng minh sở hữu private key.

Điều này có thể dùng làm:
- Một phần authentication của database/proxy.
- Identity của workload.
- Network admission control.

Nhưng:
- Server phải map certificate identity tới principal/roles cụ thể.
- Certificate còn hiệu lực không tự cho phép thao tác trên mọi table.
- Private key phải bảo vệ như một secret.
- Certificate và key cần rotation/revocation.
- Có thể vẫn cần một cơ chế DB authentication khác, tùy hệ.

### 3.3. IAM / cloud-native identity

Một managed NoSQL có thể dùng:
- IAM role/service account gắn với workload.
- Short-lived credentials của identity provider.
- Signed requests (ví dụ SigV4 với AWS).
- Token auth có thời hạn.
- Federated/workload identity.

Ưu điểm:
- Không cần giữ static database password lâu dài trong app.
- Quyền được quản lý tập trung.
- Token/credentials có vòng đời hữu hạn.
- Có audit theo service principal.

Cần:
- Workload identity đáng tin.
- Least privilege policy.
- Refresh credentials trước hết hạn.
- Không log temporary access keys/session tokens.
- Kế hoạch khi identity service/metadata endpoint bị lỗi.

### 3.4. Không tự coi bearer token là an toàn hơn password

Bearer token bị đánh cắp vẫn có thể được dùng tới khi hết hạn/thu hồi, tùy cơ chế. Cần TLS, scope, expiration, storage/rotation và audit.

### 3.5. Chọn phương thức theo deployment

| Môi trường | Hướng ưu tiên thường gặp | Cần kiểm chứng |
| --- | --- | --- |
| Managed NoSQL trên cloud | Native IAM/workload identity nếu hỗ trợ | Permissions, token refresh, network |
| Self-hosted MongoDB | SCRAM/X.509 tùy cấu hình | auth database, roles, TLS |
| Cassandra tự vận hành | Auth provider + TLS theo server | Credentials, DC, hostname validation |
| Redis managed | ACL/token + TLS | User roles, command/key permissions |
| Search/HTTP endpoint | HTTPS + API auth/IAM | Signed requests, endpoint validation |
| Kubernetes workload | Service account federation/secret mount | RBAC, volume permissions, reload |
| Local dev | Test principal và test CA | Không đưa insecure flags vào prod |

Không có một authentication mechanism chung cho mọi NoSQL engine.

## 4. TLS bảo vệ kết nối như thế nào?

Khi Java client dùng TLS, quá trình bắt tay thường gồm:
1. Client và server thương lượng phiên bản TLS/cipher suites.
2. Server trình certificate chain.
3. Client kiểm tra certificate có đáng tin không.
4. Client kiểm tra danh tính endpoint theo hostname/SAN.
5. Hai bên thiết lập session keys.
6. Dữ liệu ứng dụng được mã hóa và bảo vệ toàn vẹn.
7. Nếu mTLS, client còn trình certificate và chứng minh sở hữu private key.

~~~~mermaid
sequenceDiagram
    participant J as Java client
    participant D as NoSQL endpoint
    J->>D: ClientHello + supported TLS settings
    D-->>J: ServerHello + certificate chain
    Note over J: Verify CA chain, validity, hostname/SAN
    J->>D: Key exchange / Finished
    D-->>J: Finished
    Note over J,D: Encrypted application traffic
    J->>D: Database authentication
    D-->>J: Authenticated principal / auth error
~~~~

Đây là mô tả khái niệm; chi tiết handshake thay đổi theo TLS 1.2 và TLS 1.3.

### 4.1. Ba kiểm tra certificate quan trọng

- **Chain of trust:** server certificate dẫn tới CA/root được client tin.
- **Validity và usage:** thời hạn, mục đích sử dụng, các điều kiện xác thực áp dụng.
- **Endpoint identity:** hostname client thực sự kết nối phải khớp với danh tính được cấp trong Subject Alternative Name (SAN) theo quy tắc của TLS stack.

Chỉ chain hợp lệ nhưng hostname không khớp **chưa đủ**.

### 4.2. SAN, hostname và DNS

Certificate có SAN:

~~~~text
DNS: nosql.service.internal
DNS: db-replica-1.service.internal
~~~~

Client kết nối:

~~~~text
nosql.service.internal
~~~~

có thể được xác minh nếu chain và policy khớp. Nếu client kết nối IP trực tiếp:

~~~~text
10.20.1.15
~~~~

mà cert chỉ có DNS SAN, hostname validation có thể thất bại. **Không tắt validation để né lỗi**; cần dùng hostname đúng hoặc cấp certificate có IP SAN phù hợp.

### 4.3. SNI

Server Name Indication cho phép client thông báo hostname đích khi bắt tay TLS, hữu ích cho gateway/load balancer có nhiều certificate. SNI **không thay hostname verification**; cần cả tên đích đúng và cert đúng.

### 4.4. TLS protocol versions

Thực tế thường ưu tiên:
- TLS 1.3 khi cả hai bên và policy hỗ trợ.
- TLS 1.2 nếu cần tương thích và được cấu hình an toàn.
- Không dựa vào những protocol/cipher suite lỗi thời.

Không hardcode duy nhất TLS 1.3 nếu môi trường được hỗ trợ chỉ có TLS 1.2; cũng không hạ xuống plaintext hay tắt kiểm tra cert để “sửa” incompatibility.

### 4.5. TLS có thể được terminate ở proxy

Một kiến trúc:

~~~~text
Java app --TLS--> proxy --TLS?--> database
~~~~

Nếu proxy terminate TLS, cần xác định:
- Java đang xác minh certificate của **proxy** hay database?
- Kết nối proxy→database có mã hóa và authentication không?
- Proxy có được quyền nhìn plaintext dữ liệu không?
- Identity và authorization được forward thế nào?
- Audit ghi principal cuối cùng hay service account dùng chung?

**TLS trên một hop không tự bảo vệ toàn bộ end-to-end path** nếu hop sau là plaintext.

## 5. Truststore, keystore và SSLContext trong Java

### 5.1. Truststore

**Truststore** chứa certificate/CA mà client tin cậy khi kiểm tra server. Nó không phải nơi nên cất password database.

Một truststore có thể:
- Dùng default trust anchors của JDK.
- Dùng private CA của doanh nghiệp.
- Dùng một bộ root/intermediate certificates được quản lý riêng.

Chỉ import CA **đã xác minh** qua kênh bảo mật. Không tải bừa certificate từ endpoint lạ rồi tự coi đó là tin cậy.

### 5.2. Keystore

**Keystore** có thể chứa:
- Client certificate.
- Client private key.
- Certificate chain liên quan.

Trong mTLS, keystore/KeyManager cung cấp danh tính client.

**Private key là secret nhạy cảm**; cần quyền truy cập file chặt hơn truststore chỉ chứa public CA.

### 5.3. PKCS#12

PKCS#12 (.p12/.pfx) là một định dạng được Java hỗ trợ rộng rãi để lưu certificate/private keys với bảo vệ bằng password. Một file có:
- Chỉ public trusted certificates.
- Hoặc client private key kèm cert chain.

Mức độ nhạy cảm phụ thuộc **nội dung**, không chỉ extension .p12.

### 5.4. JSSE

Java Secure Socket Extension (JSSE) cung cấp các API:
- SSLContext.
- TrustManagerFactory.
- KeyManagerFactory.
- KeyStore.
- SSLSocket/SSLEngine.
- SSLParameters.

Các NoSQL drivers thường tạo TLS connection bên trong; nên dùng config/SSLContext được driver hỗ trợ thay vì tự mở raw socket khi production.

### 5.5. JVM-level TLS config và application-specific config

Có thể cấu hình truststore ở JVM level qua system properties, hoặc cung cấp SSLContext cho riêng client. Với nhiều database endpoints có CA/identity khác nhau, **per-client SSLContext** thường cho ranh giới rõ hơn.

Không để một thay đổi truststore toàn JVM vô tình làm hỏng HTTPS calls khác.

## 6. Java 21: tải một truststore PKCS#12 và tạo SSLContext

Ví dụ dùng **custom truststore** để xác minh server. Đoạn mã không dùng trust-all.

~~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Objects;

public final class ClientTls {
    private ClientTls() {}

    public static SSLContext fromTrustStore(
            Path trustStorePath,
            char[] storePassword
    ) throws Exception {
        Objects.requireNonNull(trustStorePath);
        Objects.requireNonNull(storePassword);

        char[] localPassword = storePassword.clone();
        try {
            KeyStore trustStore = KeyStore.getInstance("PKCS12");
            try (InputStream in = Files.newInputStream(trustStorePath)) {
                trustStore.load(in, localPassword);
            }

            TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm()
            );
            tmf.init(trustStore);

            SSLContext context = SSLContext.getInstance("TLS");
            context.init(null, tmf.getTrustManagers(), new SecureRandom());
            return context;
        } finally {
            Arrays.fill(localPassword, '\0');
        }
    }
}
~~~~

### 6.1. Mã này bảo đảm điều gì?

- Sử dụng các trust managers theo truststore đưa vào.
- Không tự bỏ qua validation certificate chain.
- Không hardcode root CA hay password trong code.
- Đóng InputStream.
- Xóa bản sao localPassword sau khi dùng.

### 6.2. Mã chưa bảo đảm điều gì?

**SSLContext không tự chứng minh hostname được xác minh** khi truyền vào một library bất kỳ. Phải bảo đảm driver/TLS engine bật endpoint identification.

Ngoài ra:
- Không tự cấu hình minimum TLS version/cipher suite.
- Không tự reload truststore khi certificate rotation.
- Không cung cấp client certificate cho mTLS.
- Không tự quản lý password gốc do caller giữ.
- Không ngăn secret tồn tại tạm trong heap/SDK.
- Không chứng minh CA import là đúng.
- Không có handling cho secret store outage.

**Tạo được SSLContext không đồng nghĩa production TLS đã cấu hình hoàn chỉnh.**

### 6.3. Default truststore vs custom truststore

Nếu dùng custom truststore chỉ chứa enterprise CA, các HTTPS endpoints công khai dùng root CA khác có thể không được tin nếu cùng context được dùng chung. Ngược lại, dùng global default roots khi cần chỉ tin private CA cũng có thể mở rộng trust anchors hơn mức dự định.

Chọn truststore theo **endpoint và policy tin cậy**.

## 7. Java: kiểm tra hostname khi dùng raw SSLSocket

Một ứng dụng không nên tự viết NoSQL protocol trên SSLSocket, nhưng ví dụ sau cho thấy điểm thường bị bỏ sót: **endpoint identification**.

~~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;

public final class TlsProbe {
    private TlsProbe() {}

    public static void handshake(
            SSLContext context,
            String hostname,
            int port
    ) throws Exception {
        try (SSLSocket socket = (SSLSocket)
                context.getSocketFactory().createSocket(hostname, port)) {

            SSLParameters params = socket.getSSLParameters();

            // Kích hoạt xác minh endpoint identity.
            params.setEndpointIdentificationAlgorithm("HTTPS");
            socket.setSSLParameters(params);

            socket.setSoTimeout(5_000);
            socket.startHandshake();
        }
    }
}
~~~~

Điểm cần nhớ:
- TLS handshake thành công **chưa chứng minh database authentication thành công**.
- Khi dùng raw SSLSocket, phải bật endpoint identification thích hợp.
- NoSQL driver có thể đã làm việc này; không tự chồng một lớp probe vào mọi request.
- Một TLS endpoint có thể yêu cầu client certificate, nên probe thiếu mTLS có thể fail đúng.
- HTTPS là tên thuật toán endpoint identification của JSSE; cấu hình thực tế phụ thuộc protocol/driver.

### 7.1. Bỏ kiểm tra hostname là một lỗi thiết kế

Một cấu hình nguy hiểm về bản chất:

~~~~text
verifyHostname=false
trustAllCertificates=true
allowInvalidCertificates=true
~~~~

Dù channel có mã hóa, client có thể tin một server giả. Không dùng các tùy chọn tương đương trong production.

### 7.2. Phải kiểm tra đúng hostname kết nối

Nếu proxy/Load Balancer có tên db.company.internal nhưng backend certificate cấp cho replica.internal, cần thiết kế:
- Certificate phù hợp endpoint người dùng kết nối.
- DNS/SNI đúng.
- TLS termination/re-encryption rõ.
- Trust domain phù hợp.

Không sửa bằng cách dùng IP hoặc tắt hostname check.

## 8. Java: cấu hình mTLS với client certificate

Khi database/proxy yêu cầu mutual TLS, client cần **truststore** để xác minh server và **identity keystore** để chứng minh danh tính client.

~~~~java
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;

public final class MutualTlsContext {
    private MutualTlsContext() {}

    public static SSLContext create(
            Path trustStoreFile,
            char[] trustStorePassword,
            Path identityStoreFile,
            char[] identityStorePassword
    ) throws Exception {
        char[] trustPass = trustStorePassword.clone();
        char[] keyPass = identityStorePassword.clone();

        try {
            KeyStore trust = KeyStore.getInstance("PKCS12");
            try (InputStream in = Files.newInputStream(trustStoreFile)) {
                trust.load(in, trustPass);
            }

            KeyStore identity = KeyStore.getInstance("PKCS12");
            try (InputStream in = Files.newInputStream(identityStoreFile)) {
                identity.load(in, keyPass);
            }

            TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm()
            );
            tmf.init(trust);

            KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm()
            );
            kmf.init(identity, keyPass);

            SSLContext context = SSLContext.getInstance("TLS");
            context.init(
                    kmf.getKeyManagers(),
                    tmf.getTrustManagers(),
                    new SecureRandom()
            );
            return context;
        } finally {
            Arrays.fill(trustPass, '\0');
            Arrays.fill(keyPass, '\0');
        }
    }
}
~~~~

### 8.1. Hai kiểm tra độc lập

- **Client → server:** kiểm tra server cert chain và SAN.
- **Server → client:** kiểm tra client cert chain/identity theo server policy.

Hai chiều phải được cấu hình đúng. Server nhận một client cert bất kỳ ký bởi CA chung chưa đủ nếu chưa map identity/roles theo policy.

### 8.2. Keystore password và private key

- PKCS#12 file chứa private key phải có filesystem permissions chặt.
- Không bake identity store vào public/container image nếu có thể cấp phát runtime.
- Đổi client certificate trước expiry.
- Giới hạn cert usage, scope và thời hạn.
- Khi rò private key, cần revoke/rotate theo trust policy, không chỉ đổi mật khẩu keystore.

### 8.3. Mutual TLS và connection pools

Đổi file .p12 trên disk không đồng nghĩa những connection đã mở hoặc SSLContext đã tạo sẽ tự dùng cert mới. Thường cần:
- Tạo SSLContext/client mới.
- Warm pool mới.
- Drain/close pool cũ.
- Đo handshake/auth failures trong cutover.
- Có thời gian overlap giữa cert cũ và mới nếu PKI policy cho phép.

Không restart đồng thời toàn bộ pods khi vừa đổi CA mà chưa xác nhận mọi bên tương thích.

## 9. Certificate chain, CA và root rotation

Một chuỗi điển hình:

~~~~text
Trusted Root CA
      |
Intermediate CA
      |
Server certificate (SAN=db.internal.example)
~~~~

Client có thể nhận leaf+intermediate chain từ server; truststore thường chứa root hoặc trust anchor được cấp phép theo policy.

### 9.1. Thiếu intermediate

Nếu server gửi chain không đầy đủ hoặc truststore thiếu trust anchor cần thiết, Java có thể báo lỗi xây đường chứng chỉ.

Không tự khắc phục bằng trust-all. Cần kiểm tra chain được server trình và CA client tin.

### 9.2. Certificate hết hạn

Một cert hết hạn làm TLS handshake thất bại khi:
- Process restart.
- Pool cần mở connection mới.
- Network reconnect.
- Server đổi endpoint.

Các kết nối cũ có thể còn sống một thời gian, khiến lỗi xuất hiện muộn và không đều giữa các instances.

### 9.3. CA rotation cần overlap

Một hướng an toàn:
1. Đưa **CA mới** vào trust bundle của clients, đồng thời giữ CA cũ trong giai đoạn chuyển tiếp theo policy.
2. Xác minh mọi client đã nhận bundle mới và có thể reconnect.
3. Server chuyển sang certificate ký bởi CA mới.
4. Quan sát handshake/auth từ tất cả client pools/regions.
5. Sau giai đoạn grace, bỏ CA cũ và thu hồi theo kế hoạch.

Không đổi server sang CA mới **trước khi** phần lớn client đã trust, nếu điều đó gây outage không cần thiết.

### 9.4. Pinning certificate

Pinning có thể giảm phạm vi trust trong một số threat model nhưng:
- Rất dễ gây outage khi thay cert/key.
- Phải có kế hoạch pins dự phòng/rotation.
- Không thay hostname verification.
- Không nên hardcode duy nhất một leaf certificate vào app khi có cert rotation thường xuyên.

Dùng PKI/CA trust policy phù hợp là lựa chọn nền tảng phổ biến; pinning chỉ nên dùng khi có yêu cầu và vận hành được.

## 10. Cấu hình ứng dụng: tách thông số công khai khỏi bí mật

Một file cấu hình có thể chứa thông tin **không phải secret**:

~~~~yaml
nosql:
  engine: mongodb
  endpoints:
    - db1.internal.example:27017
    - db2.internal.example:27017
  database: order_service
  auth:
    mechanism: scram-sha-256
    usernameSource: workload-config
    passwordSecretRef: prod/order-service/mongo
  tls:
    required: true
    hostnameVerification: true
    trustStorePath: /run/secrets/nosql/truststore.p12
  pool:
    maxSize: 40
    connectionTimeoutMillis: 3000
    socketTimeoutMillis: 5000
~~~~

Đây là **schema minh họa**, không phải application.yml được một framework tự nhận tất cả keys.

**Không xuất hiện password thật** trong ví dụ. passwordSecretRef là **địa chỉ logical** của bí mật, không phải giá trị bí mật.

### 10.1. Những giá trị nào vẫn có thể nhạy cảm?

- Hostnames/IP nội bộ và topology có thể là thông tin nhạy cảm của tổ chức.
- Secret path có thể tiết lộ tên môi trường/ứng dụng.
- Username có thể hỗ trợ enumeration/attack dù không luôn được coi là secret.
- CA certificate public thường không phải secret; private key luôn là secret.
- Truststore password chưa chắc che được dữ liệu public certificate nhưng vẫn không nên log.

Phải dùng phân loại thông tin của tổ chức, không mặc định “không phải password” là được công bố.

### 10.2. Tách môi trường

Môi trường:
- Local development.
- CI/test.
- Staging.
- Production.

Nên có:
- Principals khác nhau.
- Secrets khác nhau.
- Quotas và permissions khác nhau.
- Trust anchors phù hợp.
- Endpoints khác nhau.
- Không cho production đọc fallback secret của development.

Một lỗi nghiêm trọng là app production **tự fallback sang username/password mặc định** khi secret manager lỗi.

### 10.3. Cấu hình phải fail closed

Nếu tls.required=true nhưng application không tạo được truststore:
- **Fail startup** hoặc đánh dấu not ready với lỗi được kiểm soát.
- Không tự chuyển sang plaintext.
- Không tắt cert verification.
- Không dùng hardcoded root credentials.

Nếu password secretRef không tồn tại:
- Không thử username/password “admin/admin”.
- Không ghi secretRef đầy đủ cùng credentials vào log.
- Báo lỗi cấu hình theo mã chung và health signals.

## 11. Nên lưu secrets ở đâu?

Một số lựa chọn:

| Nguồn | Ưu điểm | Rủi ro/điều kiện |
| --- | --- | --- |
| Hardcoded trong Java | Không có ưu điểm bảo mật | Rò qua Git/artifact; cực khó rotate |
| Plaintext trong application.yml | Dễ setup | Dễ vào Git/image/log; không phù hợp production |
| Environment variables | Triển khai đơn giản | Có thể lộ qua process introspection, crash dump, debug, deployment metadata |
| Mounted secret file | Quyền filesystem và rotation có thể kiểm soát | Phải bảo vệ volume, symlink updates và reload |
| Secret manager API | ACL/audit/versioning/rotation tập trung | Cần runtime identity, caching và outage policy |
| Short-lived workload credentials | Giảm static secrets | Phải refresh, IAM và identity trust đúng |
| Java keystore/PKCS#12 | Hợp cho TLS keys/certs | File/key/password vẫn cần bảo vệ |
| Kubernetes Secret | Cách phân phối trong cluster | Base64 không phải encryption; etcd/RBAC/volume policy quan trọng |
| HSM/KMS-backed key operations | Có thể tránh xuất private key ra process | Tùy driver/protocol hỗ trợ, latency/cost, policy |

### 11.1. Secret manager không loại bỏ bootstrap identity

Ứng dụng phải có cách **xác thực với secret manager**:
- Cloud workload identity.
- Kubernetes service account federation.
- VM instance role.
- Vault auth method phù hợp.
- Một cơ chế cấp token/identity được vận hành an toàn.

Không giải quyết bằng cách hardcode **secret-manager master token** trong ứng dụng.

### 11.2. Secret manager phải có least privilege

Nếu order-service cần:

~~~~text
prod/order-service/mongodb/readonly
prod/order-service/mongodb/readwrite
~~~~

nó không nên tự có quyền đọc:
- Payment provider secrets.
- Database root credentials.
- Secret của tenant khác.
- Secret của staging nếu không cần.

Service principal nên chỉ được lấy **những secret refs thật sự sử dụng**.

### 11.3. Caching và outage

Nếu service gọi secret manager cho **mỗi database query**:
- Tăng latency.
- Tăng tải secret provider.
- Secret-store outage có thể gây cascade sang tất cả requests.

Một chiến lược thường:
- Lấy secret khi startup.
- Cache trong phạm vi và TTL được policy chấp nhận.
- Chủ động refresh/rotate.
- Có backoff và circuit breaker với secret provider.
- Không giữ credential đã bị thu hồi vô hạn.
- Fail closed khi không thể xác minh identity cần thiết.

TTL và refresh semantics phụ thuộc loại secret; **static password rotation** khác **short-lived STS token**.

## 12. Java: interface cho secret source

Tách cách lấy secret khỏi connection configuration:

~~~~java
public interface SecretProvider {
    SecretValue fetch(String secretRef) throws Exception;
}

public interface SecretValue extends AutoCloseable {
    String username();

    // Bản sao tạm do caller sở hữu và phải xóa sau khi dùng.
    char[] copyPassword();

    String versionId();

    @Override
    void close();
}
~~~~

Một implementation có thể đọc từ:
- Cloud secret manager SDK.
- Vault.
- Mounted file theo permissions.
- Local test fixture chỉ dùng trong tests.

### 12.1. Vì sao không trả password trong toString?

Nếu một record chứa password hoặc một object tự động in field:
- Logs/debug có thể chứa secret.
- Exception formatting có thể làm lộ.
- IDE debugger có thể render object.

Secret holder nên:
- Không tự in password.
- Có controlled accessor.
- Xóa buffers có thể xóa khi close.
- Không đưa vào tracing baggage.
- Không serialize thành JSON.

### 12.2. char[] không phải phép màu

Java char[] có thể được xóa bằng Arrays.fill, hữu ích để giới hạn bản sao do ứng dụng kiểm soát. Nhưng:
- Một số driver nhận String và có thể tạo bản sao bất biến trong heap.
- Secret manager SDK có thể giữ String.
- TLS/JDK/driver có buffers riêng.
- Heap dump có thể chứa thông tin nhạy cảm.
- GC không bảo đảm xóa mọi bản sao ngay.

Nên giảm lifetime/copies, khóa quyền heap dump, không log secret và dùng workload identity khi có thể.

### 12.3. Không tạo secret mới ở mỗi retry

Một DB operation thất bại vì network không nên liên tục gọi secret store để lấy lại cùng password. Retry của **DB operation** và refresh của **credential** là hai vòng đời khác nhau.

Chỉ refresh credential khi:
- Token sắp hết hạn.
- Secret version đổi.
- Có tín hiệu auth failure phù hợp.
- Theo rotation watcher/schedule.

Không biến transient DB timeout thành secret-store traffic storm.

## 13. Spring Boot: tổ chức cấu hình an toàn

Nếu ứng dụng dùng Spring Boot, có thể tách:
- Các thông số cấu hình không bí mật ở application.yml.
- Bí mật từ secret store/file/environment theo deployment.
- Một bean tạo NoSQL client với SSLContext.
- Readiness check và connection pool management.

Một record cấu hình minh họa:

~~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "nosql")
public record NoSqlProperties(
        String engine,
        String database,
        String endpoint,
        String passwordSecretRef,
        boolean tlsRequired,
        String trustStorePath,
        int poolMaxSize
) {}
~~~~

Một phần YAML tương ứng:

~~~~yaml
nosql:
  engine: mongodb
  database: order_service
  endpoint: db.internal.example:27017
  password-secret-ref: prod/order-service/mongo
  tls-required: true
  trust-store-path: /run/secrets/nosql/truststore.p12
  pool-max-size: 40
~~~~

Để binding hoạt động cần đăng ký configuration properties theo phiên bản Spring Boot đang dùng, xử lý validation và tạo client bean thích hợp. Đoạn ví dụ chỉ cho thấy **phân lớp trách nhiệm**, không phải một ứng dụng hoàn chỉnh.

### 13.1. Validation lúc khởi động

Ứng dụng nên từ chối cấu hình:
- Production nhưng TLS disabled.
- Endpoint rỗng.
- SecretRef rỗng.
- Truststore path không tồn tại khi cần.
- Pool size không hợp lệ.
- Auth mechanism không được hỗ trợ.
- Username/password lấy từ fallback không mong muốn.

Không log toàn bộ Properties object nếu trong đó có secret values.

### 13.2. Spring Actuator và debug endpoints

Cần kiểm tra:
- Những endpoints/config dumps nào được expose.
- Có bị đưa secrets vào environment/property source không.
- Sanitization/redaction có hiệu quả với custom property names không.
- Log level DEBUG/TRACE của driver hoặc HTTP client có in headers/URI không.
- Traces có URI chứa userinfo không.

Không mở public endpoint hiển thị config chỉ để gỡ lỗi production.

### 13.3. Profile không phải secret isolation

Spring profiles giúp chọn configuration theo môi trường. Nhưng:
- application-prod.yml trong Git vẫn không nên chứa password.
- Profile nhầm có thể trỏ production app tới staging DB hoặc ngược lại.
- Runtime secret access permissions phải chặn cross-environment access.
- Secret store ACL và network policy phải độc lập với tên profile.

## 14. MongoDB Java driver: SCRAM + TLS

Một ví dụ dùng credentials được lấy từ secret source và cấu hình TLS. Đoạn code minh họa MongoDB Java sync driver.

~~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoCredential;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

import javax.net.ssl.SSLContext;
import java.util.Arrays;

public final class MongoClientFactory {
    private MongoClientFactory() {}

    public static MongoClient connect(
            String username,
            char[] password,
            SSLContext trustedTlsContext
    ) {
        char[] localPassword = password.clone();
        try {
            ConnectionString address = new ConnectionString(
                    "mongodb://db1.internal.example:27017,"
                    + "db2.internal.example:27017/"
                    + "?replicaSet=rs0"
            );

            MongoCredential credential =
                    MongoCredential.createScramSha256Credential(
                            username,
                            "admin",
                            localPassword
                    );

            MongoClientSettings settings = MongoClientSettings.builder()
                    .applyConnectionString(address)
                    .credential(credential)
                    .applyToSslSettings(ssl -> ssl
                            .enabled(true)
                            .invalidHostNameAllowed(false)
                            .context(trustedTlsContext))
                    .build();

            return MongoClients.create(settings);
        } finally {
            Arrays.fill(localPassword, '\0');
        }
    }

    public static void main(String[] args) throws Exception {
        // Chỉ minh họa flow; username, secret và SSLContext
        // phải lấy từ runtime config / secret provider hợp lệ.
        //
        // try (MongoClient client = connect(user, pass, context)) {
        //     client.getDatabase("order_service")
        //           .runCommand(new Document("ping", 1));
        // }
    }
}
~~~~

### 14.1. Các điểm quan trọng

- Connection URI không chứa password.
- Credential được cấu hình riêng.
- TLS bật và **invalidHostNameAllowed=false**.
- trust context phải chứa CA phù hợp.
- Authentication database admin là ví dụ; thực tế phải khớp user/source của hệ.
- Tài khoản chỉ có roles cần thiết cho order_service.
- Client nên được dùng lại/pool chung, không tạo mới cho mỗi request.

### 14.2. Cảnh báo về char[] lifecycle

Mã xóa localPassword sau khi xây settings, nhưng driver có thể giữ credential material nội bộ để tạo authenticated connections mới. Không được diễn giải là mọi bản sao password trong JVM đã được xóa.

Caller phải quản lý buffer password gốc, secret lease/version và lifecycle MongoClient.

### 14.3. Không đặt userinfo trong URI nếu có thể tránh

Ví dụ rủi ro:

~~~~text
mongodb://username:password@db.internal.example:27017/app
~~~~

URI có thể bị in khi:
- Log kết nối.
- Exception.
- Metrics/traces.
- Diagnostic dump.
- Error reporting.
- Command-line process arguments.

Nếu SDK yêu cầu URI chứa credential, cần kiểm soát redaction/escaping và không ghi nguyên URI ở đâu. Tốt hơn là tách secret khỏi URI khi driver hỗ trợ.

### 14.4. Auth source và privilege

Một MongoDB user có thể được xác thực ở một authentication database nhưng được cấp roles trên database khác. Không tự suy connection path database và authSource là một.

### 14.5. Server certificate trên replica set

Nếu driver discovery chuyển từ db1 sang db2:
- Cả các replica hosts được truy cập phải có certificate phù hợp tên endpoint.
- Truststore của client cần tin chain của các replica theo policy.
- Một cert chỉ hợp cho db1 nhưng driver lại kết nối db2 có thể gây intermittent TLS failures.

Hãy test TLS qua **topology changes/replica failover**, không chỉ ping seed node.

## 15. Cassandra Java driver: authentication, local DC và TLS

Với Java Driver 4.x theo cấu hình được hỗ trợ, ý tưởng:

~~~~java
import com.datastax.oss.driver.api.core.CqlSession;

import javax.net.ssl.SSLContext;
import java.net.InetSocketAddress;

public final class CassandraClientFactory {
    private CassandraClientFactory() {}

    public static CqlSession connect(
            String username,
            String password,
            SSLContext tlsContext
    ) {
        return CqlSession.builder()
                .addContactPoint(new InetSocketAddress(
                        "cassandra-1.internal.example", 9042))
                .withLocalDatacenter("dc1")
                .withAuthCredentials(username, password)
                .withSslContext(tlsContext)
                .build();
    }
}
~~~~

### 15.1. Điều phải kiểm tra thêm

- Auth provider/SASL mechanism server yêu cầu.
- Local DC đúng topology.
- Driver có bật hostname validation ở SSL engine factory đang dùng không.
- Tất cả contact points/advertised node addresses có SAN phù hợp.
- Authentication/authorization ở keyspace/table đúng role.
- Connection pool/reconnect và secret rotation behavior.
- TLS port có đúng, không vô tình connect plaintext.

Mã mẫu không tự ép mọi SSL engine thực thi endpoint verification; phải đối chiếu **driver và phiên bản cụ thể**.

### 15.2. Driver nhận String password

Ở API mẫu, password là String. Không thể xóa String như char[]. Hãy:
- Lấy secret tại runtime, giảm thời gian giữ và số bản sao.
- Không log session/config.
- Giới hạn quyền heap dump.
- Xoay vòng theo client/session lifecycle.
- Dùng auth mechanism phù hợp hơn nếu deployment hỗ trợ.

### 15.3. Role giới hạn

Order service không nên có quyền tạo/drop keyspace, sửa cluster configuration hay mọi table khác chỉ để SELECT/INSERT/UPDATE các tables nghiệp vụ.

## 16. Redis Java và ACL/TLS

Redis có thể dùng:
- TLS endpoint (nếu server/deployment hỗ trợ).
- ACL username/password.
- Network access controls.
- Command/key pattern restrictions.

Ví dụ với Lettuce theo API phù hợp phiên bản:

~~~~java
import io.lettuce.core.RedisClient;
import io.lettuce.core.RedisURI;

public final class RedisConnectionFactory {
    private RedisConnectionFactory() {}

    public static RedisClient client(
            String username,
            char[] password
    ) {
        RedisURI uri = RedisURI.builder()
                .withHost("redis.internal.example")
                .withPort(6380)
                .withSsl(true)
                .withAuthentication(username, password)
                .build();

        return RedisClient.create(uri);
    }
}
~~~~

### 16.1. Điều cần lưu ý

- Port 6380 trong ví dụ **không phải mặc định bắt buộc của mọi Redis TLS deployment**.
- withSsl(true) chưa chứng minh đúng hostname/trust configuration ở mọi connector/version.
- Không để password lộ qua Redis URI được format/log.
- Username/password phải có ACL giới hạn commands và keys phù hợp.
- Redis Cluster discovery/redirect phải duy trì TLS và auth.
- Stateful connections/client resources cần close/shutdown theo lifecycle.

### 16.2. ACL không thay tenant checks

Nếu Redis chứa:

~~~~text
tenant:T-42:booking:B-901
tenant:T-77:booking:B-902
~~~~

Một principal được phép truy cập mọi prefix vẫn có thể đọc chéo tenant nếu app xây key sai. Cần tenant-scoped authorization ở application và key policy khi có thể.

### 16.3. Cache vs source of truth

Redis cache thường không nên giữ mật khẩu DB khác ở value không mã hóa hoặc làm authority cho quyết định quyền/tài chính. Nếu Redis là source của một ứng dụng, phải xác định persistence/replication/failover/auth semantics riêng.

## 17. DynamoDB Java: IAM thay cho static database password

Với AWS SDK for Java v2, DynamoDB thường dùng HTTPS và IAM-authenticated signed requests. Không dùng username/password database như MongoDB.

~~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

public final class DynamoClientFactory {
    private DynamoClientFactory() {}

    public static DynamoDbClient create() {
        return DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }
}
~~~~

### 17.1. DefaultCredentialsProvider tìm credentials từ đâu?

Provider chain có thể dựa trên môi trường, profile hoặc workload identity theo SDK/config. Ở production nên bảo đảm:
- Dùng role/identity đúng.
- Không có static access keys vô tình ghi đè role.
- Không log access key/session token.
- SDK có thể refresh short-lived credentials theo hợp đồng.
- Có IAM policy least privilege.
- Không hardcode custom endpoint plaintext.

### 17.2. SigV4 khác TLS

Signed request xác thực request/identity theo cơ chế cloud API. TLS vẫn bảo vệ channel và xác minh endpoint. Cả hai cần cấu hình phù hợp.

### 17.3. IAM permissions

Một ứng dụng chỉ cần GetItem, Query, PutItem/UpdateItem cho một số tables thì không nên có CreateTable/DeleteTable hay quyền quản trị tài khoản.

Điều kiện IAM có thể hỗ trợ thu hẹp phạm vi theo resource/key trong một số trường hợp nhưng phải xác minh behavior theo API và schema; không dùng chính sách IAM giả định như thay thế kiểm tra quyền tenant ở Java service.

### 17.4. Rotation của short-lived credentials

Đừng giữ một bộ temporary credentials cố định nhiều ngày trong một singleton object tự viết nếu chúng hết hạn. Dùng provider được SDK hỗ trợ refresh, kiểm tra clock skew, expiration và lỗi lấy credentials.

## 18. Neo4j, OpenSearch và HBase: cùng nguyên tắc, khác giao thức

### 18.1. Neo4j

Graph database có Java driver riêng và URI schemes/TLS policies tương ứng. Cần:
- Dùng scheme xác minh server certificate phù hợp.
- Tránh các mode chấp nhận unverified/self-signed certificates trong production không có trust policy.
- Credential từ secret source.
- Roles giới hạn database/query privileges.
- Kiểm tra cert của các cluster endpoints khi routing.

### 18.2. OpenSearch/Elasticsearch

Java client có thể dùng HTTPS với:
- Basic auth.
- API keys/tokens.
- IAM request signing trên managed service hỗ trợ.
- Custom truststore/mTLS nếu deployment yêu cầu.

Không bỏ hostname verification; không log Authorization header; giới hạn search/index roles và request budgets. Search index không tự là source có transaction authority của các nghiệp vụ khác.

### 18.3. HBase

HBase có thể có Kerberos, TLS cho các đường transport liên quan, service credentials/keytab theo cơ sở hạ tầng. Không suy từ MongoDB URI rằng mọi NoSQL dùng một password/TLS port chung.

Keytab/private credentials phải được phân phối và bảo vệ runtime; user/ACL/namespace policies cần giới hạn thao tác thích hợp.

## 19. Quản lý quyền database: least privilege

Một matrix minh họa:

| Principal | Read orders | Write orders | Manage indexes | Read payment secrets | Admin/drop database |
| --- | --- | --- | --- | --- | --- |
| order-api-readonly | Có | Không | Không | Không | Không |
| order-api-writer | Có | Có theo scope | Không | Không | Không |
| order-migration-job | Có | Có | Có khi được cấp tạm | Không | Chỉ quyền cần thiết |
| analytics-reader | Read projection | Không source write | Không | Không | Không |
| db-admin-breakglass | Theo nhiệm vụ | Theo nhiệm vụ | Có | Không mặc định | Có kiểm soát và audit |

### 19.1. Tách application và migration principal

Ứng dụng chạy 24/7 không cần quyền DROP TABLE, CREATE USER hoặc cấu hình cluster. Nếu cần migration:
- Dùng principal/job riêng.
- Cấp quyền có thời hạn nếu được hỗ trợ.
- Phê duyệt/audit.
- Không phát tán admin credentials tới tất cả service pods.

### 19.2. Least privilege không chỉ là role name

Một role tên readwrite vẫn có thể cấp quyền trên cả database. Cần kiểm tra:
- Databases/keyspaces/collections.
- Operations.
- Resources.
- Row/key patterns nếu engine hỗ trợ.
- Regions/endpoints.
- Account/environment boundaries.

### 19.3. Multi-tenancy

Một tài khoản ứng dụng dùng chung cho nhiều tenant phải có:
- Authentication và authorization của end user ở API.
- TenantId được lấy từ trusted auth context.
- Query/key luôn có tenant guard.
- Không tin tenantId do client tự gửi là đủ.
- Audit cho cross-tenant admin operations.
- Test dữ liệu tenant khác trong integration tests.

DB authentication không tự xác thực tenant cuối.

## 20. Kubernetes: bí mật qua Secret, volume hoặc workload identity

### 20.1. Kubernetes Secret không đồng nghĩa mã hóa tự động hoàn chỉnh

Các giá trị trong manifest có thể base64-encoded:
- Base64 là encoding, **không phải encryption**.
- Nếu manifest chứa secret thật rồi commit Git, vẫn là lộ secret.
- Cần kiểm soát etcd encryption-at-rest, RBAC, audit và namespace policy.
- Không cấp quyền get/list tất cả Secrets cho mọi pod/service account.

### 20.2. Environment variables

Ưu điểm:
- Nhiều SDK dễ đọc.
- Phổ biến trên platform.

Nhược điểm:
- Có thể xuất hiện trong process environment/config dump/debug.
- Rotation thường không tự cập nhật env của process đang chạy.
- Dễ bị ghi nhầm khi log environment.
- Có thể rò qua CI/deployment metadata.

Không in toàn bộ environment khi debug sự cố auth.

### 20.3. Mounted files

Ví dụ runtime:

~~~~text
/run/secrets/nosql/password
/run/secrets/nosql/client-identity.p12
/run/secrets/nosql/truststore.p12
~~~~

Ưu điểm:
- Có thể dùng filesystem permissions.
- Một số secret controllers/CSI có thể cập nhật files.
- Tách secret khỏi image.

Nhược điểm:
- App/driver có thể không tự reload khi file đổi.
- Symlink replacement, atomic mount updates có semantics riêng.
- File permissions/owner cần đúng.
- Private key không được để world-readable.
- Crash dumps/backups có thể chứa file/values.

### 20.4. Service account identity

Một service account có thể được federation sang IAM/Vault auth:
- Không cần static database secret trong pod nếu DB/cloud hỗ trợ.
- Workload được cấp short-lived token/role.
- Quyền có thể thu hẹp theo namespace/service.
- Phải bảo vệ token audience, expiration và pod identity.

Đừng dùng cùng service account quyền rộng cho mọi microservices.

### 20.5. Secret rotation trong Kubernetes

Nếu mounted secret file được thay:
- Java process phải phát hiện version/fingerprint đổi.
- Tạo client/SSLContext mới nếu driver không hot reload.
- Warm client mới.
- Drain pool cũ.
- Không restart mọi pods cùng lúc nếu chưa có canary.
- Liveness/readiness phải phản ánh kết nối thực, không vô hạn reconnect.

## 21. Xoay vòng password an toàn

Xoay vòng credential phải có cách hạn chế downtime.

### 21.1. Khi database cho phép hai credentials song song

Một quy trình:
1. **Create:** tạo secret/credential B với quyền tương đương tối thiểu.
2. **Distribute:** ghi secret version B vào secret manager, cấp quyền app lấy B.
3. **Roll:** canary instances tạo new connection pool dùng B.
4. **Verify:** đọc/ghi thử bằng B trong phạm vi test không side effect nguy hiểm.
5. **Expand:** chuyển toàn bộ instances qua B.
6. **Drain:** đóng connections dùng A theo policy.
7. **Revoke:** thu hồi A sau khi xác minh không còn clients hợp lệ cần A.
8. **Audit:** xác nhận access attempts với A biến mất, update incident/runbook.

### 21.2. Nếu chỉ một password có hiệu lực

Một số hệ không cho A và B đồng thời trên cùng account. Khi đó:
- Có thể tạo account mới B thay vì đổi password tại chỗ.
- Hoặc cần một phối hợp maintenance/cutover có kế hoạch.
- Chạy canary và chuẩn bị rollback trong phạm vi có thể.
- Không giả định “password update” atomically đồng thời tới mọi app instances.

### 21.3. Rotation và connection pool

Một connection được authenticate bằng A có thể sống sau khi A bị đổi; những connections mới dùng A thất bại. Vì vậy có thể thấy:
- Requests vẫn thành công một thời gian.
- Pod mới khởi động lại thất bại.
- Pool replacement sau idle timeout thất bại.
- Các instances có secret version khác nhau.

Theo dõi **authentication failure, new connection success, secret version coverage và pool churn**.

### 21.4. Kế hoạch rollback

Nếu B không hoạt động:
- Nếu A vẫn hợp lệ, có thể quay về A bằng cách đổi secret version/connection routing theo policy.
- Nếu A đã revoked, rollback đơn giản có thể không khả thi.
- Khi nghi ngờ A bị lộ, **không rollback về compromised credential** chỉ để phục vụ nhanh; cần quy trình incident response.

## 22. Rotation cho mTLS certificates và CA bundles

### 22.1. Server certificate rotation

Nếu cùng CA và SAN:
- Clients thường không cần đổi truststore.
- Nhưng cần test expiry, certificate chain và new handshake.
- Các clients không được pin leaf cert duy nhất nếu không có rotation mechanism.

### 22.2. Client certificate rotation

Nếu mTLS identity đổi:
- Server phải tin CA/identity mới.
- Principal mapping và roles phải được duy trì/cập nhật.
- Java phải nạp keystore mới.
- Pool phải tạo connections mới.
- Private key cũ phải được thu hồi/tiêu hủy theo chính sách.

### 22.3. CA rotation

Một trình tự điển hình:
1. Client trust bundle hỗ trợ CA old+new trong transition.
2. Server/client cert mới được phát hành.
3. Canary kết nối qua certificate mới.
4. Rollout toàn bộ.
5. Thu hồi/remove CA cũ sau grace period.
6. Test failover/reconnect qua mọi replica/region.

### 22.4. Expiry monitoring

Cần alert trước expiry theo giai đoạn:
- Certificate server.
- Intermediate CA.
- Client certificate.
- Credentials/tokens thời hạn ngắn.
- Truststore version và rotation job health.

Không đợi đến khi TLSHandshakeException xuất hiện trên hàng nghìn requests mới bắt đầu gia hạn.

## 23. Kiểm soát secret leakage trong toàn vòng đời

### 23.1. Source code và Git

Không đưa vào:
- application.yml password thật.
- Java string constants chứa secret.
- Private keys/keystore.
- Test fixture dùng production password.
- Shell scripts có token.
- Notebook, screenshots, sample API calls chứa credentials.

Nếu secret từng được commit:
- Coi như có khả năng đã lộ.
- **Revoke/rotate** secret.
- Xem xét lịch sử Git, CI logs, caches và forks theo quy trình.
- Chỉ xóa commit/file hiện tại không khôi phục an toàn.

### 23.2. CI/CD

Pipeline:
- Không echo secrets.
- Không truyền password qua command-line arguments nếu dễ hiển thị ở process list/log.
- Dùng short-lived identity để lấy secrets khi cần.
- Chỉ job có quyền mới được access production secret.
- Giới hạn fork/untrusted code chạy với secret.
- Masking không thay thế kiểm soát xuất dữ liệu.
- Không upload artifact chứa generated config có password.

### 23.3. Container images

Không:

~~~~dockerfile
FROM eclipse-temurin:21-jre
ENV DB_PASSWORD=real-password
COPY app.jar /app/app.jar
~~~~

Mã là **anti-pattern**, không phải hướng dẫn triển khai. Secret trong image config/layers có thể bị trích xuất ngay cả khi một layer sau xóa ENV.

Thay bằng runtime secrets/workload identity. Container image nên không phụ thuộc một môi trường cụ thể để nhận credential.

### 23.4. Logs, metrics, traces

Không log:
- Authentication header.
- Full DB connection URI có userinfo.
- JWT/bearer token.
- Access key/session token.
- Private key.
- Raw secret-provider response.
- Password chars hoặc credential object toString.
- Query chứa PII không cần thiết.

Chỉ log:
- Secret logical version ID đã được cho phép công bố.
- Error category (TLS_CHAIN, HOSTNAME_MISMATCH, AUTH_FAILED...).
- Endpoint alias, region/cell.
- Connection attempt/handshake latency.
- Request/trace ID.

### 23.5. Heap dumps và debug

JVM heap dump có thể giữ Strings, buffers, token fragments:
- Giới hạn ai tạo/đọc dump.
- Không upload lên support ticket công khai.
- Dùng encrypted secure storage với retention.
- Redact trước khi chia sẻ theo khả năng.
- Bảo vệ profiling/APM agents khỏi in secrets.

### 23.6. Error pages

Một exception hiển thị:
- DB hostname.
- Auth mechanism.
- Username.
- Full URI.
- Internal stack trace.

có thể hữu ích cho attacker. API public nên trả mã lỗi phù hợp; diagnostics chi tiết chỉ ở hệ logging có quyền.

## 24. Secret access và bảo mật cấu hình như một supply chain

Một production runtime lấy secret qua:

~~~~text
CI builds artifact
    -> deployment manifest selects service identity
    -> runtime authenticates to secret store
    -> secret provider returns version B
    -> client builds TLS + auth config
    -> DB verifies principal and applies roles
~~~~

Mỗi bước có trust boundary:
- CI phải được giới hạn quyền release.
- Artifact không chứa secret.
- Deployment identity đúng môi trường.
- Secret store ACL chính xác.
- Database role không quá rộng.
- NoSQL client không downgrade TLS.
- Logs/monitoring không làm lộ material.

### 24.1. IaC và policy as code

Có thể xác minh trong deployment review:
- TLS required.
- Auth enabled.
- SecretRef không trỏ test/prod sai.
- Không có plaintext env password trong YAML công khai.
- Database principal không có admin role.
- Network ingress không public ngoài nhu cầu.
- Secret store read policy có resource scope.
- Rotation/expiry alerts tồn tại.

Những checks này là **security controls bổ sung**, không thay integration test.

### 24.2. Zero trust không phải khẩu hiệu đủ

Ngay cả khi toàn bộ nodes trong VPC:
- Network nội bộ có thể bị truy cập qua lateral movement.
- Service account bị lộ.
- DNS bị sai.
- Một pod bị compromise.

Không tắt TLS/auth chỉ vì endpoint dùng private IP.

## 25. Configuration lifecycle: startup, readiness và refresh

### 25.1. Startup

Một flow:

~~~~mermaid
flowchart TD
    LOAD["Load non-secret config"] --> VALID["Validate TLS/auth policy"]
    VALID --> ID["Resolve workload identity"]
    ID --> SECRET["Fetch secret version"]
    SECRET --> TRUST["Build SSLContext"]
    TRUST --> DB["Construct NoSQL client"]
    DB --> CONNECT["Connect/authenticate"]
    CONNECT --> READY{"Operationally ready?"}
    READY -->|Yes| SERVE["Serve traffic"]
    READY -->|No| FAIL["Not-ready / controlled failure"]
~~~~

### 25.2. Readiness vs liveness

- **Liveness:** process còn hoạt động, có thể cần restart nếu deadlock.
- **Readiness:** instance có thể phục vụ request theo contract hiện tại hay không.

Nếu DB auth bị sai:
- Đánh dấu not-ready để không nhận traffic mới.
- Không restart vô hạn theo chu kỳ cực nhanh làm tăng auth attempts.
- Phải có logging/alert.
- Không in password để debug.

### 25.3. Refresh credentials

Nếu provider báo version B:
- Tải secret B.
- Tạo client B, validate.
- Chuyển traffic có kiểm soát.
- Đóng/drain client A.
- Xóa buffers cũ trong phạm vi quản lý.
- Alert nếu secret version drift.

Nếu provider không reachable:
- Không tự fallback password mặc định.
- Có thể tiếp tục dùng credential A khi còn hợp lệ và policy cho phép.
- Có deadline/grace/expiry monitoring.
- Khi không thể bảo đảm xác thực, fail closed.

### 25.4. Connection pool và secret version

Một pool có thể chứa connections dùng principal/version cũ. Không chỉ nhìn secret-provider fetch thành công; phải kiểm tra **new connection auth**.

### 25.5. Không tạo connection trên mỗi request

MongoClient, CqlSession, RedisClient, DynamoDbClient thường nên được quản lý theo lifecycle thích hợp thay vì tạo rồi đóng liên tục mỗi query. Quá nhiều TLS handshakes/auth requests có thể:
- Tăng CPU/latency.
- Gây connection storms.
- Căng identity provider.
- Làm quá trình rotation khó theo dõi.

## 26. Timeouts, retries và authentication failures

Không phải mọi lỗi kết nối đều nên retry như nhau.

| Lỗi | Retry? | Hướng xử lý |
| --- | --- | --- |
| TCP connection refused tạm thời | Có giới hạn | Network/endpoint health |
| TLS handshake timeout | Có giới hạn khi nghi transient | Đo RTT/server overload |
| Certificate expired | Không retry mù | Rotate cert |
| Hostname mismatch | Không retry mù | Sửa DNS/cert/SAN |
| PKIX path building failed | Không retry mù | Sửa trust chain |
| Invalid username/password | Không retry liên tục | Kiểm tra secret version/auth source |
| Forbidden/permission denied | Không retry y hệt | Sửa role hoặc logic |
| Short-lived token expired | Refresh theo provider | Không giữ static token |
| Throttling/overload | Backoff+jitter/budget | Giảm tải |
| DB quorum unavailable | Backoff/bounded retries | Không giảm consistency lén |
| Credential manager unavailable | Retry có giới hạn + cache policy | Không lấy secret mỗi request |
| Commit ACK lost | Outcome UNKNOWN | Idempotency/reconcile |

### 26.1. Auth failure có thể do secret rotation, không phải hacker

Nếu vài pods còn A và phần còn lại đã dùng B:
- New connections dùng A thất bại sau khi revoke.
- Existing connections có thể vẫn hoạt động.
- Logs cho thấy lỗi phân bố theo pod/version.
- Readiness có thể bất ổn.

Cần correlation với secret version rollout/credential retirement.

### 26.2. Không retry authentication bằng nhiều tài khoản tùy tiện

Một anti-pattern:

~~~~text
try service-user
if fails -> try admin
if fails -> try root
~~~~

Đây là privilege escalation path và tạo thêm rủi ro. Chỉ cấu hình principal được phép, fail rõ và điều tra.

### 26.3. Không nhầm transport timeout với commit status

Khi TLS/auth đã hoàn tất, một write có thể commit rồi response mất. **SocketTimeoutException không chứng minh rollback**. Retry cùng logical operationId theo idempotency contract, không tạo order/payment mới.

## 27. Chẩn đoán TLS từ triệu chứng, không bỏ kiểm tra

### 27.1. PKIX path building failed

Thường gợi ý vấn đề trust chain:
- CA không nằm trong truststore.
- Server gửi intermediate chain thiếu.
- Client dùng truststore nhầm môi trường.
- Certificate chain không hợp policy.

Hướng xử lý:
1. Xác định endpoint thực được kết nối.
2. Kiểm tra chain của endpoint.
3. Đối chiếu truststore đang nạp.
4. Xác minh CA qua kênh tin cậy.
5. Cấp lại hoặc sửa chain/truststore.
6. Test handshake lại với hostname verification bật.

### 27.2. No subject alternative DNS name matching

Host được client dùng không khớp certificate SAN:
- DNS alias mới chưa có trong certificate.
- Kết nối bằng IP nhưng cert chỉ có DNS.
- Driver phát hiện replica với hostname khác seed endpoint.
- Proxy trả certificate của virtual host khác.

Cần sửa hostname/cert/proxy, không tắt endpoint identification.

### 27.3. Certificate expired/not yet valid

Có thể do:
- Cert thật sự hết hạn.
- Server/client clock sai.
- Rollout certificate chậm.
- Intermediate CA hết hạn.

Xác minh thời gian và cấp lại cert đúng chain.

### 27.4. Unsupported protocol/cipher suites

Client và server có thể không có giao TLS version/ciphers. Cần đồng bộ policy và runtime hỗ trợ; không hạ xuống TLS yếu hoặc plaintext.

### 27.5. Handshake thành công nhưng auth failed

Đường TLS đã hoạt động, nhưng:
- Username/password sai.
- Auth DB/source sai.
- Token expired.
- Client cert identity không mapping role.
- Mechanism không khớp server.
- Account locked/disabled.

Đừng thay truststore khi vấn đề là AuthN.

### 27.6. Auth thành công nhưng operation forbidden

Role không cho phép operation. Cần:
- Kiểm tra role/resource.
- Xem service thực sự cần quyền đó không.
- Sửa query hoặc cấp quyền tối thiểu theo approval.
- Không đổi sang root để che lỗi.

## 28. Công cụ chẩn đoán TLS an toàn

### 28.1. OpenSSL s_client

Trong môi trường có OpenSSL, một probe minh họa:

~~~~bash
openssl s_client \
  -connect db.internal.example:27017 \
  -servername db.internal.example \
  -verify_hostname db.internal.example \
  -verify_return_error
~~~~

Lưu ý:
- Lệnh chỉ thử TLS với endpoint.
- Không tự xác thực tới database.
- Không tự chứng minh mọi replica trong cluster có cert đúng.
- Nếu server yêu cầu mTLS, probe thiếu client cert có thể fail đúng.
- Kết quả phụ thuộc CA trust path được OpenSSL dùng, có thể **khác JDK truststore**.
- Không đưa private key/password vào command line nếu điều đó làm lộ qua history/process list.
- Cần timeout/quyền truy cập network phù hợp.

### 28.2. keytool inspect

Có thể kiểm tra certificate/truststore với keytool theo hướng dẫn của JDK; nên tránh in private key, dùng input passwords qua prompts/secret store thay vì args có thể lộ.

Ví dụ mang tính khái niệm:

~~~~bash
keytool -list -v -storetype PKCS12 -keystore truststore.p12
~~~~

Đầu ra certificate metadata có thể chứa tên nội bộ, cần quản lý tương ứng.

### 28.3. JSSE debug

Java có TLS handshake debug options, nhưng có thể in nhiều metadata và chi tiết nội bộ. Chỉ bật:
- Trong môi trường chẩn đoán được phép.
- Với thời gian ngắn.
- Log storage được bảo vệ.
- Redaction và retention phù hợp.
- Không in secret/Authorization headers.

### 28.4. Test đúng đường ứng dụng

Nếu Java driver discovery chuyển sang node khác, một probe chỉ tới seed host không đủ. Cần test:
- Initial connect.
- Auth.
- Read/write có permission.
- Failover/reconnect.
- Rotation.
- Region/replica endpoints.

## 29. Observability cho kết nối và secret lifecycle

| Chỉ số | Ý nghĩa |
| --- | --- |
| TLS handshake successes/failures | Tỷ lệ kết nối TLS hợp lệ |
| TLS error category | Hostname, chain, expiry, protocol, timeout |
| Certificate days-to-expiry | Chủ động rotate |
| Auth failure rate | Secret drift, user disabled, attack |
| Authorization denies | Role lệch với business operations |
| Secret fetch failures | Secret provider health |
| Secret version age/distribution | Pods còn dùng version cũ |
| Credential refresh latency | Token/cert refresh có kịp không |
| Connection pool active/idle/waiting | Connection pressure |
| Pool new-connection success | Xác thực mới sau rotation |
| Connection churn | Có reconnect storm không |
| Readiness failures | Instance không đủ điều kiện phục vụ |
| Region/replica mismatch | Chỉ một số endpoint cert lỗi |
| Retry amplification | Auth/TLS errors có bị retry storm |
| Audit unexpected principal | Có dùng sai identity không |
| Tenant access violations | Có lọt quyền cross-tenant không |

### 29.1. Không đưa secret vào metric labels

Không dùng password, token, full connection URI hoặc raw secret path nhạy cảm làm label. Labels nên có:
- Service.
- Environment.
- Region/cell.
- Driver error category.
- Rotation phase.
- Non-sensitive secret version alias nếu được phép.

OperationId/requestId có cardinality lớn nên đặt ở traces/logs được kiểm soát.

### 29.2. Alert expiry trước khi sự cố

Kết hợp:
- Cert gần hết hạn.
- Secret-provider rotation thất bại.
- Tỷ lệ pods dùng old credential kéo dài.
- New connection auth errors sau rollout.
- Certificate mismatch chỉ trên một replica.

Không đợi liveness failure hàng loạt.

## 30. Kiểm thử bảo mật kết nối

Một bộ test cần cả **positive path** và **negative path**.

### 30.1. Positive tests

- Cert hợp lệ, chain CA được tin, SAN match.
- Username/token/cert hợp lệ.
- Read/write operations đúng role.
- Connection pool reconnect sau failover.
- Secret version B được rollout khi A còn hợp lệ.
- mTLS client cert identity được map đúng principal.
- Không có secret trong logs/metrics.
- All configured replicas có SAN/CA phù hợp.

### 30.2. Negative tests

| Test | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Wrong CA | Client dùng truststore khác | TLS fail |
| Hostname mismatch | Client dùng hostname không có trong SAN | TLS fail |
| Expired server cert | Dùng cert hết hạn trong test | TLS fail |
| Missing client cert | Server bắt mTLS | TLS/auth fail |
| Wrong client cert | Cert không đúng identity/CA | Bị từ chối |
| Wrong password | Credential sai | Auth fail, không fallback |
| Revoked role | Principal không còn read/write | Permission denied |
| Plaintext endpoint | Server không hỗ trợ TLS | App fail, không downgrade |
| Secret unavailable at startup | Provider không truy cập | Controlled startup failure |
| Rotation B invalid | Canary B auth failed | Không revoke A, alert |
| Old secret revoked | Pod còn A tạo connection mới | Bị từ chối; rollout phát hiện |
| Secret leaked through URI log | Exception debug path | Test redaction fail nếu có secret |
| Tenant ID tampering | Client đổi tenantId | Unauthorized |
| Token expired | Short-lived identity hết hạn | Refresh hoặc fail, không dùng mãi |
| Wrong replica certificate | Driver failover sang replica sai SAN | TLS fail rõ |
| Network partition | Một region unreachable | Retry bounded, không hạ auth/TLS |
| Unknown commit | ACK mất sau write | Retry cùng operationId |

### 30.3. Test CA riêng, không bật insecure mode

Trong integration tests:
- Tạo test CA/cert có SAN cho service hostname.
- Test truststore thật sự tin test CA.
- Negative test sai hostname.
- Không đặt trust-all vào shared helper rồi vô tình mang tới production.

### 30.4. Fuzz logs/error paths

Cố tình đưa một dummy secret marker vào config test và kích hoạt:
- Startup error.
- TLS error.
- Auth denied.
- Driver exception.
- Health endpoint.
- Debug serialization.
- Trace export.

Kiểm tra marker **không xuất hiện** trong logs/artifacts. Dummy secret không phải production secret.

## 31. Vận hành khi bị lộ credential

Nếu phát hiện password hoặc token trong Git/log:
1. **Đánh giá scope:** secret nào, principal nào, môi trường nào, thời gian nào.
2. **Containment:** giới hạn truy cập và network nếu có thể mà không phá chứng cứ.
3. **Rotate/revoke:** coi credential có khả năng bị lộ, không chỉ xóa dòng log.
4. **Audit:** kiểm tra access logs, truy vấn/privilege bất thường.
5. **Deploy:** cấp credential mới qua secret manager.
6. **Verify:** canary auth thành công, old credential không còn hiệu lực.
7. **Cleanup:** redaction/retention theo policy cho logs, artifacts và repo history.
8. **Prevent recurrence:** secret scanning, code review, logging redaction và policy tests.

### 31.1. Đừng công bố secret trong ticket

Incident channel có thể có nhiều người đọc. Không dán password/token để chứng minh lỗi. Chia sẻ:
- Secret logical name/version.
- Hash/fingerprint không cho phép tái sử dụng.
- Thời điểm và scope.
- Error category.

### 31.2. Rotate không đủ nếu principal quá quyền

Nếu attacker đã dùng account admin:
- Cần kiểm tra dữ liệu/roles/backup/config có bị thay đổi.
- Xem xét persistence/backdoor users.
- Reconcile data integrity.
- Áp dụng least privilege sau incident.

## 32. Runbook khi TLS/auth lỗi hàng loạt

### Bước 1 — Xác định phạm vi

- Một service hay nhiều services?
- Một region/replica hay toàn cluster?
- Pod mới hay pod cũ?
- Initial connect hay reconnect?
- Lỗi xảy ra sau cert/secret rollout nào?

### Bước 2 — Phân lớp lỗi

~~~~text
DNS / TCP
   -> TLS handshake
      -> Server certificate validation
         -> Client authentication
            -> Authorization
               -> Query/transaction
~~~~

Không sửa sai lớp. Auth failed không được xử bằng tắt TLS; hostname mismatch không được xử bằng đổi password.

### Bước 3 — Kiểm tra metadata không bí mật

- Hostname/SAN.
- Cert chain và expiry.
- Truststore version.
- Driver/JDK versions.
- Secret version alias.
- Principal role mapping.
- Network policy.
- Pool connection creation timestamps.

### Bước 4 — Bảo vệ sản xuất

- Không bật trust-all/invalid-hostname.
- Không dùng admin credentials fallback.
- Không log password để debug.
- Rollback rollout cấu hình nếu an toàn và credential cũ chưa compromised.
- Giữ capacity bằng canary/staged rollout.
- Giới hạn reconnect/retry storms.

### Bước 5 — Khôi phục đúng

- Sửa DNS/cert/SAN/trust chain khi TLS lỗi.
- Sửa secret version/auth source khi AuthN lỗi.
- Sửa role hoặc query khi AuthZ lỗi.
- Cấp trust bundle có overlap cho CA rotation.
- Tạo/warm pools mới.
- Drain pools cũ.
- Verify API read/write đúng contract.

### Bước 6 — Xác nhận

- New handshakes qua mọi replica.
- Auth success theo secret version mới.
- Permission tests không vượt quyền.
- p99/timeout/pool wait về ngưỡng.
- Không secret trong logs.
- Old credential được revoke nếu kế hoạch cho phép.
- Postmortem và alert expiry/rotation.

## 33. Những hiểu nhầm thường gặp

1. **“Cứ có TLS là server đã xác thực client.”** TLS một chiều chỉ xác minh server nếu cấu hình đúng.
2. **“TLS handshake thành công nghĩa DB permission đúng.”** AuthN/AuthZ riêng.
3. **“Mật khẩu đúng thì khỏi cần TLS.”** Dữ liệu/credentials vẫn cần transport protection.
4. **“Kết nối nội bộ không bị nghe lén.”** VPC/cluster cũng có rủi ro.
5. **“Encryption tự chứng minh đúng endpoint.”** Phải verify SAN/hostname.
6. **“Trust-all chỉ bỏ lỗi certificate, vẫn an toàn.”** Có thể cho MITM.
7. **“Tắt hostname check chỉ trong vài ngày không sao.”** Là một lỗ hổng thực.
8. **“SAN của db1 đủ cho mọi replica.”** Driver có thể connect db2.
9. **“Dùng IP thay DNS là sửa TLS.”** IP SAN có thể không khớp.
10. **“SNI thay hostname verification.”** Hai việc khác nhau.
11. **“Custom SSLContext tự bật hostname check.”** Phụ thuộc driver/engine config.
12. **“Truststore và keystore giống nhau.”** Trust anchors khác client private key.
13. **“.p12 lúc nào cũng là secret.”** Nội dung có thể chỉ public CA; private key mới nhạy cảm.
14. **“Base64 trong Kubernetes Secret là encryption.”** Không.
15. **“Đưa password vào environment là an toàn tuyệt đối.”** Vẫn có process/debug/log risks.
16. **“Để secret trong container image rồi xóa layer sau là đủ.”** Image history/layers vẫn có thể lộ.
17. **“Secret manager không cần bootstrap auth.”** Workload vẫn cần identity.
18. **“Có secret manager thì app khỏi cần RBAC DB.”** Vẫn cần least privilege.
19. **“Cứ gọi secret manager mỗi query để an toàn.”** Có thể tạo dependency bottleneck.
20. **“char[] xóa được mọi bản sao mật khẩu.”** Driver/heap có thể giữ String/copies.
21. **“Đổi file truststore thì connections tự reload.”** Thường cần tạo client/context mới.
22. **“Rotation password không ảnh hưởng pool.”** Connection mới có thể auth fail.
23. **“Thu hồi A ngay sau khi tạo B là luôn an toàn.”** Các pods có thể còn dùng A.
24. **“Rollback về credential bị lộ là chấp nhận được.”** Rủi ro compromise vẫn còn.
25. **“Một certificate sống là đủ, không cần chain.”** PKI validation cần chain/trust.
26. **“Có chứng chỉ do CA tin nghĩa hostname nào cũng được.”** SAN match vẫn bắt buộc.
27. **“TLS lỗi thì thử lại vô hạn.”** Expired/mismatch cert không tự hết.
28. **“Auth lỗi thì thử admin/root.”** Tạo privilege escalation.
29. **“Secret Ref không phải password nên có thể public mọi nơi.”** Có thể là metadata nội bộ nhạy cảm.
30. **“Spring profile tách production và staging tuyệt đối.”** Identity/policies phải tách thật.
31. **“Actuator tự ẩn mọi custom secret property.”** Cần test sanitization.
32. **“Một principal readwrite toàn DB đủ least privilege.”** Có thể quyền quá rộng.
33. **“DB auth đã bảo vệ tenant end user.”** App phải enforce tenant scope.
34. **“IAM token loại bỏ yêu cầu TLS.”** Signing/auth khác transport.
35. **“DynamoDB giống MongoDB username/password.”** IAM model khác.
36. **“Mọi NoSQL Java client có cùng TLS option.”** Driver/config khác nhau.
37. **“TLS kết thúc ở proxy nghĩa hop tới DB cũng được mã hóa.”** Phải kiểm tra re-encryption.
38. **“Mở connection mới mỗi request an toàn hơn.”** Tạo handshake/auth storms.
39. **“Socket timeout nghĩa DB write rollback.”** Commit có thể đã xảy ra.
40. **“HTTP 200 của health endpoint chứng minh mọi replica cert hợp lệ.”** Cần test failover/discovery.
41. **“Chỉ theo dõi cert server, không cần client cert.”** mTLS client cert cũng hết hạn.
42. **“Một cert pin duy nhất làm rotation dễ hơn.”** Có thể khiến outage.
43. **“Xóa secret khỏi Git HEAD là hết lộ.”** History/artifacts vẫn có thể chứa.
44. **“Logs nội bộ không cần redaction.”** Logs có thể được chia sẻ lâu dài.
45. **“Heap dump không phải secret artifact.”** Có thể chứa credentials.
46. **“Mỗi pod dùng secret version nào không quan trọng.”** Drift làm rotation lỗi.
47. **“Role migration/admin dùng cho app chính cũng được.”** Không đúng least privilege.
48. **“Khi thiếu TLS cert cứ fallback plaintext.”** Phải fail closed.
49. **“Khi secret store lỗi cứ dùng mật khẩu mặc định.”** Tuyệt đối không.
50. **“Test kết nối thành công là đủ.”** Cần negative tests, rotation, permissions và failover.

## 34. Bài tập thực hành: cấu hình Java NoSQL an toàn

Một nền tảng SaaS đặt chỗ dùng:
- Java 21 và Spring Boot.
- MongoDB làm source lưu Orders và Reservations.
- Redis làm cache.
- DynamoDB dùng cho một pipeline managed trên AWS.
- Ba môi trường dev/staging/prod.
- Service chạy trong Kubernetes.
- Production MongoDB có TLS và SCRAM.
- Redis ACL + TLS.
- AWS workload identity cho DynamoDB.
- Cert nội bộ có CA rotation hằng năm.
- Database password rotation định kỳ.
- Client có khả năng reconnect sau failover.
- Các tenant không được đọc dữ liệu của nhau.

### Phần A — Threat model

Liệt kê ít nhất 10 điểm có thể rò credentials hoặc làm sai server identity:
- Git.
- Container image.
- CI logs.
- Process env.
- JVM debug.
- URI logging.
- Heap dump.
- Mounted keystore.
- DNS/SAN mismatch.
- Proxy TLS termination.
- Secret-store ACL.
- Compromised service account.

Với mỗi điểm, đưa biện pháp phòng ngừa và phát hiện.

### Phần B — AuthN/AuthZ/TLS

Giải thích:
1. TLS server authentication chứng minh gì?
2. SCRAM authentication chứng minh gì?
3. MongoDB roles giới hạn gì?
4. Java application tenantId guard làm gì?
5. Nếu cả TLS và SCRAM đúng nhưng query cross-tenant, lỗ hổng ở lớp nào?

### Phần C — JSSE

Viết một SSLContext load custom PKCS12 truststore. Trả lời:
- TrustManagerFactory khác KeyManagerFactory thế nào?
- Vì sao hostname verification vẫn phải được bật?
- Nếu driver dùng SSLContext nhưng tắt endpoint identification, điều gì nguy hiểm?
- Vì sao truststore chứa CA được xác minh đáng tin hơn trust-all?
- Khi mTLS, thêm client certificate/key bằng cách nào?

### Phần D — Config

Thiết kế một cấu hình production:
- Có endpoint, database, TLS required và secretRef.
- Không có plaintext password.
- Có environment-specific identity.
- Có validation fail closed.
- Có pool timeouts và max connections.
- Không log config chứa secret.

Giải thích vì sao source YAML chỉ nên chứa **tham chiếu bí mật**, không phải giá trị.

### Phần E — MongoDB

Viết factory nhận username, char[] password, SSLContext:
- Tạo MongoCredential.
- Bật TLS.
- Bật hostname validation.
- Không nhét password vào URI.
- Dùng pool/client lifecycle.
- Dùng role chỉ read/write collection cần thiết.

Nếu driver failover từ db1 sang db2 và db2 cert sai SAN, expected behavior là gì?

### Phần F — Redis

Thiết lập ACL principal:
- Chỉ được GET/SET trên key prefix của service.
- Không được FLUSHALL/CONFIG.
- Kết nối TLS.
- Không chia sẻ Redis admin password.
- Bảo vệ tenant scope trong Java.

Tại sao prefix theo tenant trong key **không tự** bảo đảm authorization?

### Phần G — DynamoDB

Dùng DefaultCredentialsProvider:
- Workload identity nên được cấp ở đâu?
- Vì sao không hardcode AWS keys?
- Permissions tối thiểu gồm gì?
- Khi temporary credentials hết hạn, refresh thế nào?
- TLS và SigV4 bảo vệ những lớp khác nhau ra sao?

### Phần H — Rotation

Mô tả state machine:

~~~~text
A_ACTIVE
  -> B_CREATED
  -> B_CANARY_VALIDATED
  -> B_ROLLED_OUT
  -> A_DRAINED
  -> A_REVOKED
~~~~

Ở mỗi giai đoạn:
- Secret version.
- Connection pool version.
- Tiêu chí rollback/cutover.
- Metrics auth failures.
- Không dùng credential bị compromised để rollback.

### Phần I — Certificate rotation

Giả sử CA cũ hết hạn sau 30 ngày:
1. Phân phối trust bundle old+new thế nào?
2. Khi nào server đổi leaf cert?
3. Kiểm tra SAN/chain/expiry trên tất cả replicas?
4. mTLS client cert có cần rotate không?
5. Khi nào remove old CA?
6. Trường hợp một pod chưa nhận trust bundle mới xử lý ra sao?

### Phần J — Negative integration tests

Lập bảng kịch bản và expected result:
1. Wrong CA.
2. Wrong hostname.
3. Expired cert.
4. Missing client cert.
5. Invalid password.
6. Forbidden query.
7. Staging app dùng prod secretRef.
8. Plaintext downgrade attempt.
9. Secret manager unavailable.
10. Rotated secret B invalid.
11. Replica failover sang cert sai.
12. Log full connection URI.
13. Cross-tenant query.
14. Expired short-lived IAM credentials.

### Phần K — Incident response

Một kỹ sư vô tình log MongoDB URI chứa password production suốt 20 phút:
- Các bước containment?
- Rotate/revoke thế nào?
- Kiểm tra logs/artifacts/history ra sao?
- Audit quyền/queries bất thường?
- Vì sao chỉ xóa log mới không đủ?
- Làm gì để phát hiện lần sau?

### Phần L — Phản biện thiết kế

Một đồng nghiệp đề xuất:

> “Database nằm trong VPC nên khỏi cần TLS. Nếu TLS lỗi thì cho phép invalid certificate. Để Mongo password trong application-prod.yml cho đơn giản, Redis dùng default user không hạn chế quyền. Khi rotate password, chỉ đổi giá trị trong secret manager; mọi Java client sẽ tự refresh. Nếu startup lỗi thì fallback admin password.”

Hãy phản biện theo:
- Rủi ro network/MITM.
- Chain/SAN/hostname verification.
- Least privilege và blast radius.
- Secret distribution/CI/Git risks.
- Connection pool lifecycle.
- Fail-closed/rotation stages.
- Tenant authorization và audit.
- Negative tests/monitoring.

### Hướng giải

Một giải pháp vững chắc:
- Mỗi service có **identity riêng**, lấy secret qua workload identity/secret manager khi cần.
- Database principal chỉ có **quyền tối thiểu**, không dùng admin account thường trực.
- TLS luôn bật trong production, client **xác minh server chain + hostname/SAN**; mTLS nếu yêu cầu.
- PKCS12 truststore/keystore được cung cấp runtime với permissions đúng, không hardcode private keys.
- Config lưu endpoint/trust paths/secretRef chứ không lưu password.
- Client/pool có lifecycle và **rotation** gồm canary, rollout, drain, revoke.
- Không fallback plaintext/invalid cert/admin credentials.
- Có TLS/auth/secret metrics, expiry alerts, logs redaction và test failure cases.
- Application tiếp tục enforce tenant scope và business authorization.

## 35. Checklist sẵn sàng production

1. **Đã phân biệt rõ AuthN, AuthZ, TLS và encryption-at-rest?**
2. **Có threat model về network, config, logs và workload identity?**
3. **Mọi kết nối production tới NoSQL có TLS bắt buộc?**
4. **Client xác minh CA chain và hostname/SAN?**
5. **Không dùng trust-all/allowInvalidHostName trong prod?**
6. **Server cert hợp lệ trên mọi replica/endpoint được driver khám phá?**
7. **Truststore chứa đúng CA theo trust policy?**
8. **mTLS keystore/private key được bảo vệ nếu dùng?**
9. **Có cơ chế cert/CA rotation có overlap?**
10. **Có alert certificate và token expiry?**
11. **Ứng dụng dùng principal riêng, không dùng root/admin?**
12. **Roles chỉ được phép đúng database/table/collection/operations?**
13. **Application enforce tenant authorization và query scoping?**
14. **Secret không nằm trong Git, image, config plaintext, sample code?**
15. **Runtime lấy secret qua identity/ACL phù hợp?**
16. **Secret manager không bị gọi trên mọi query vô ích?**
17. **Secret caches/TTL/refresh/revocation có policy?**
18. **Connection pools được refresh sau rotation?**
19. **Credential rotation có create, canary, rollout, drain và revoke?**
20. **Không rollback về credential bị nghi compromise?**
21. **Startup fail closed nếu thiếu TLS/auth/secrets?**
22. **Không fallback plaintext hay default password?**
23. **Không log URI có userinfo, headers, passwords, tokens, private keys?**
24. **Spring Actuator/debug/config endpoints đã kiểm tra redaction?**
25. **Heap dumps/diagnostics được kiểm soát quyền và retention?**
26. **CI/CD và IaC có secret scanning/policy checks?**
27. **Đã test wrong CA/hostname/expired cert/missing mTLS cert?**
28. **Đã test invalid password/permission denied/cross-tenant access?**
29. **Đã test secret manager outage và rotation giữa lúc có traffic?**
30. **Đã test replica failover/reconnect/TLS discovery?**
31. **Có phân biệt TLS handshake, auth, authorization, timeout và UNKNOWN commit?**
32. **Retry có giới hạn, không biến auth lỗi thành reconnect storm?**
33. **Có theo dõi secret version drift, auth failures và pool churn?**
34. **Có runbook khi cert hết hạn hoặc secret bị lộ?**
35. **Có audit/canary trước khi revoke credential cũ?**

**Kết luận:** Cấu hình kết nối NoSQL từ Java phải coi **danh tính, kênh truyền và bí mật** là ba lớp phối hợp. **Authentication** giúp database biết ứng dụng nào đang kết nối; **authorization** giới hạn hành động và tài nguyên; **TLS với chain + hostname verification** giúp kết nối đúng máy chủ và bảo vệ dữ liệu trên đường truyền. Password, token và private key cần được cấp phát **ngoài mã nguồn và image**, thông qua secret manager, mounted files hoặc workload identity phù hợp, với quyền tối thiểu, logging redaction và lifecycle rõ ràng. Trong production, xoay vòng secret và certificate phải tính đến **connection pool, mTLS identity, CA overlap, canary, readiness và rollback constraints**. Đừng giải quyết lỗi handshake bằng trust-all hay auth failure bằng admin fallback; hãy phân loại đúng lớp lỗi và kiểm chứng bằng **negative tests, failover, rotation drills và các chỉ số TLS/auth/secret version**, để giữ cả bảo mật lẫn tính sẵn sàng của hệ NoSQL phân tán.
