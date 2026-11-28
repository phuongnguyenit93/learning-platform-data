# Thiết kế Java KeyStore deployment

Case study này thiết kế cách triển khai Java KeyStore cho một dịch vụ Java chạy trong production, cần cung cấp HTTPS, xác thực client nội bộ bằng mutual TLS (mTLS) và xác minh certificate của các dịch vụ đối tác. Thiết kế bao gồm nơi tạo và lưu private key, cách cấp phát keystore, cách ứng dụng nạp key, cách quản lý truststore, cách triển khai trên container, quy trình rotation và kiểm thử khi có sự cố.

Mục tiêu là giữ private key trong ranh giới bảo vệ được phê duyệt, cấp đúng identity cho đúng workload, triển khai certificate có thể thay thế an toàn và duy trì khả năng vận hành khi key hoặc certificate đến hạn. Java KeyStore là một API và định dạng lưu trữ; bản thân việc dùng KeyStore không tự động bảo đảm key được bảo vệ. Mức an toàn phụ thuộc loại keystore, provider, cách phân phối password, quyền file, KMS/HSM, cấu hình TLS và quy trình vận hành.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chương **Thiết kế case study**. Thiết kế kết nối mật mã đối xứng và bất đối xứng, chữ ký số, certificate/PKI, KMS/HSM, envelope encryption, kiểm soát truy cập, backup, rotation, audit và các rủi ro khi quản lý sai khóa.

## 1. Bối cảnh hệ thống

Giả sử tổ chức vận hành dịch vụ Java tên là orders-api. Dịch vụ nhận HTTPS từ client bên ngoài, gọi các service nội bộ bằng mTLS và kết nối tới một đối tác thanh toán có private CA riêng.

Các yêu cầu chính:

- Server phải trình certificate TLS phù hợp với hostname mà client truy cập.
- Một số endpoint nội bộ chỉ chấp nhận client có certificate do CA nội bộ cấp.
- Outbound connection phải xác minh certificate chain của đối tác.
- Private key của server phải được bảo vệ và không được đưa vào source code hoặc container image.
- Mỗi environment có identity và trust configuration riêng.
- Certificate có thể được rotate mà không phải rebuild image.
- Audit phải xác định được certificate/key version nào đang được triển khai.
- Có thể chuyển sang HSM cho key có mức độ quan trọng cao hơn.

Đây là một dịch vụ mẫu. Với ứng dụng thực tế, số lượng keystore, truststore, alias, CA và consumer phải được xác định từ inventory và kiến trúc của tổ chức.

## 2. Phân biệt KeyStore, TrustStore và Secret Store

Ba khái niệm thường bị nhầm lẫn:

| Thành phần | Nội dung | Vai trò |
|---|---|---|
| KeyStore | Có thể chứa private key, certificate chain và trusted certificate entry | Cung cấp identity/key entry cho ứng dụng |
| TrustStore | Thường chứa trusted certificate hoặc trust anchor | Xác định CA/certificate mà ứng dụng tin cậy |
| Secret Store | Lưu password, token, PIN hoặc secret dùng để mở keystore/kết nối backend | Phân phối thông tin xác thực và cấu hình nhạy cảm |

Một KeyStore có thể chứa nhiều loại entry. PrivateKeyEntry gắn private key với certificate chain; TrustedCertificateEntry chứa certificate công khai được tin cậy. TrustStore là cách tổ chức sử dụng KeyStore cho mục đích trust, không phải một loại mật mã riêng.

Password mở file PKCS#12 không phải private key. Nó bảo vệ nội dung container theo cơ chế của định dạng/provider; password yếu hoặc bị lưu cạnh file làm giảm đáng kể hiệu quả bảo vệ.

## 3. Chọn loại keystore

Các lựa chọn thường gặp:

| Loại | Đặc điểm | Khi cân nhắc |
|---|---|---|
| PKCS#12 | Định dạng chuẩn hóa, hỗ trợ private key và certificate, được Java hỗ trợ rộng | Lựa chọn mặc định thực tế cho phần lớn deployment file-based |
| JKS | Định dạng keystore lịch sử của Java | Chỉ giữ khi tương thích hệ thống cũ hoặc có lý do cụ thể |
| PKCS#11 | Kết nối Java với cryptographic token/HSM thông qua provider | Khi private key phải nằm trong HSM/token |
| Provider-specific keystore | Phụ thuộc nhà cung cấp hoặc nền tảng | Khi cần tính năng riêng, phải kiểm tra portability và support |

Với triển khai mới dùng file, chọn PKCS#12 và khai báo rõ type trong cấu hình. Không dựa vào default keystore type của runtime vì default có thể khác theo phiên bản JDK hoặc môi trường.

Nếu dùng HSM, KeyStore type PKCS#11 thường đại diện cho object/handle trên token. Private key có thể không export được; ứng dụng yêu cầu provider thực hiện ký hoặc TLS operation ngay trong HSM. Không giả định mọi provider hỗ trợ cùng alias, mechanism hoặc KeyManagerFactory behavior.

## 4. Thiết kế identity và trust boundary

Tách rõ bốn vùng:

1. **PKI/issuance:** tạo key pair, tạo CSR, phê duyệt và phát hành certificate.
2. **Key protection:** giữ private key trong HSM hoặc keystore được bảo vệ.
3. **Deployment:** phân phối keystore/certificate tới đúng workload và environment.
4. **Runtime:** Java nạp key/trust material và sử dụng qua JCA/JSSE.

~~~mermaid
flowchart TD
    A["PKI / Certificate Authority"] --> B["Issue server certificate"]
    C["HSM or controlled key generation"] --> D["Private key + certificate chain"]
    B --> D
    D --> E["Protected deployment secret"]
    F["Secret manager / CSI integration"] --> E
    E --> G["Java workload"]
    H["Trust bundle from approved CA"] --> G
    G --> I["JSSE SSLContext"]
    I --> J["HTTPS / mTLS"]
    K["Audit and monitoring"] --> E
    K --> G
~~~

Private key không cần đi qua PKI sau khi CSR được tạo nếu key pair được sinh trong HSM. CA chỉ nhận CSR và trả certificate. Với file-based PKCS#12, private key có thể được tạo trong một quy trình kiểm soát rồi đóng gói vào keystore; file và password phải được phân phối qua các kênh có kiểm soát.

## 5. Quyết định file-based hay HSM-backed

Không phải mọi Java service đều cần HSM. Chọn backend dựa trên yêu cầu bảo vệ, threat model, hiệu năng và khả năng vận hành.

| Tiêu chí | PKCS#12 file-based | HSM/PKCS#11 |
|---|---|---|
| Private key location | File được bảo vệ trên filesystem/secret volume | Object trong HSM/token |
| Exportability | Có thể trích xuất nếu entry/provider cho phép và có password | Thường có thể cấu hình non-extractable |
| Deployment | Phân phối file và password | Cấu hình provider, token session và quyền HSM |
| Availability | Phụ thuộc volume, secret delivery và process | Phụ thuộc HSM cluster/session/network |
| Portability | Tương đối cao | Phụ thuộc vendor/provider |
| Audit | File access và application audit | Có thể có device-level operation audit |
| Chi phí/vận hành | Thấp hơn, cần bảo vệ file tốt | Cao hơn, cần quản trị HSM và ceremony |

Quyết định cho case study:

- Dùng PKCS#12 cho TLS identity của service nếu risk assessment và policy cho phép file-based key.
- Dùng truststore riêng cho CA nội bộ và CA đối tác.
- Dùng HSM-backed key cho code signing, root/intermediate CA hoặc key có yêu cầu non-exportable nghiêm ngặt.
- Nếu policy yêu cầu private TLS key non-exportable, thay PKCS#12 file bằng HSM/PKCS#11 hoặc managed TLS termination có bảo vệ tương đương.

Không tuyên bố PKCS#12 tương đương HSM. PKCS#12 là container có thể mã hóa; HSM là cryptographic module có ranh giới bảo vệ và khả năng kiểm soát khác.

## 6. Quy tắc đặt tên và phân tách theo environment

Mỗi key/certificate phải có identity và mục đích rõ. Ví dụ:

| Environment | Key alias | Certificate subject/SAN | Trust bundle |
|---|---|---|---|
| Development | orders-api-dev | dev-orders.example.internal | Dev CA |
| Staging | orders-api-stg | stg-orders.example.internal | Staging CA |
| Production | orders-api-prod | orders.example.com | Production/internal partner CA |

Không dùng cùng private key cho development, staging và production chỉ để giảm công sức quản lý. Tách biệt giúp giới hạn blast radius và tránh certificate test được chấp nhận trong production.

Alias là tên tra cứu trong keystore, không phải bằng chứng xác thực danh tính. Danh tính TLS được kiểm tra bằng certificate chain, SAN, validity, key usage và trust policy.

## 7. Tạo key pair và phát hành certificate

Quy trình phát hành cho file-based keystore:

1. Owner xác định hostname, SAN, key usage, thuật toán, key size và thời hạn certificate.
2. Quy trình được phê duyệt tạo key pair trong môi trường kiểm soát.
3. Private key được bảo vệ trong keystore PKCS#12.
4. Tạo CSR chứa public key và thông tin identity cần thiết.
5. CA kiểm tra yêu cầu và phát hành certificate cùng chain.
6. Import certificate chain vào đúng alias của keystore.
7. Kiểm tra private key khớp public key trong certificate.
8. Ghi inventory gồm key ID/alias, certificate serial/fingerprint, owner và expiry.
9. Phân phối artifact qua secret delivery channel tới đúng workload.

Nếu key được tạo trong HSM, tạo key pair trong token và tạo CSR bằng HSM provider. Private key không rời HSM; chỉ CSR/public key đi tới CA.

## 8. Ví dụ dùng keytool để kiểm tra và tạo CSR

Các lệnh dưới đây minh họa thao tác quản trị. Keytool sẽ yêu cầu password tương tác nếu không truyền password trong command. Không đặt password trực tiếp trong shell history, script, CI log hoặc process arguments.

~~~bash
# Tạo PKCS#12 và key pair trong môi trường cấp phát được kiểm soát.
keytool -genkeypair \
  -alias orders-api-prod \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 90 \
  -dname "CN=orders.example.com, OU=Platform, O=Example" \
  -ext "SAN=dns:orders.example.com,dns:orders" \
  -storetype PKCS12 \
  -keystore orders-api-prod.p12

# Tạo CSR để gửi tới CA đã được phê duyệt.
keytool -certreq \
  -alias orders-api-prod \
  -file orders-api-prod.csr \
  -storetype PKCS12 \
  -keystore orders-api-prod.p12 \
  -ext "SAN=dns:orders.example.com,dns:orders"

# Kiểm tra metadata và certificate chain sau khi import.
keytool -list -v \
  -alias orders-api-prod \
  -storetype PKCS12 \
  -keystore orders-api-prod.p12
~~~

Thuật toán và key size trong ví dụ chỉ là profile minh họa. Tổ chức cần chọn profile theo policy hiện hành và khả năng CA/client. Với RSA, cần kiểm tra tương thích và signature profile; ECDSA có thể phù hợp nếu toàn bộ client/provider hỗ trợ. Không dùng certificate tự ký cho production trust chỉ vì lệnh tạo key pair thành công.

## 9. Import certificate chain đúng cách

Sau khi CA phát hành certificate:

- Kiểm tra certificate serial, issuer, subject, SAN, validity và key usage.
- Xác minh chain tới đúng trust anchor.
- Xác minh public key trong certificate khớp private key entry.
- Import leaf certificate cùng intermediate chain vào alias tương ứng.
- Tránh import nhầm certificate của environment khác.
- Không thay trust anchor chỉ dựa trên file được gửi qua email/chat.

Một private key entry cần có certificate chain đúng thứ tự theo yêu cầu của provider. Nếu chain thiếu intermediate, một số client có thể không xây dựng được path dù certificate leaf hợp lệ.

## 10. Tổ chức keystore và truststore

Với orders-api, tách file:

- orders-api-identity.p12: private key và certificate chain của server.
- orders-api-trust.p12: CA nội bộ và CA đối tác mà ứng dụng cần tin.
- client identity riêng nếu service phải trình certificate khác với server identity.

Lợi ích:

- Quyền đọc identity keystore có thể hẹp hơn quyền đọc trust bundle.
- Rotation server certificate không bắt buộc thay truststore.
- CA partner có thể được cập nhật theo quy trình trust review.
- Giảm nguy cơ ứng dụng vô tình tin certificate chỉ vì nó nằm cạnh private key.

Không import mọi certificate mà ứng dụng từng gặp vào truststore. Truststore phải phản ánh trust policy có chủ đích.

## 11. Thiết kế cấu hình deployment

Cấu hình ứng dụng chỉ chứa loại keystore, path, alias và các tham số không bí mật. Password được lấy từ secret provider ở runtime.

~~~yaml
security:
  tls:
    identity:
      type: PKCS12
      path: /var/run/key-material/identity/orders-api-identity.p12
      alias: orders-api-prod
    trust:
      type: PKCS12
      path: /var/run/key-material/trust/orders-api-trust.p12
    protocols:
      - TLSv1.3
      - TLSv1.2
    client-auth: need
~~~

Đây là cấu hình khái niệm; tên property cần ánh xạ vào framework hoặc application configuration thực tế. Không đặt store password, key password, PIN hoặc token trong file YAML, Dockerfile, image layer hay repository.

Nếu service chỉ yêu cầu mTLS trên một số endpoint, client-auth policy phải được cấu hình theo listener/route phù hợp. Không bật yêu cầu client certificate toàn bộ ingress nếu có endpoint public không cần mTLS.

## 12. Phân phối keystore tới container

Không bake file PKCS#12 hoặc password vào image. Image chỉ chứa application binary và cấu hình không bí mật.

Deployment pipeline:

1. Build image bất biến, không chứa key material.
2. Workload xác thực bằng workload identity.
3. Secret manager/CSI provider cấp file keystore và truststore cho đúng workload.
4. Password được phân phối riêng qua secret provider hoặc cơ chế secret file.
5. Volume mount ở read-only và chỉ process user cần thiết có quyền đọc.
6. Ứng dụng kiểm tra file/alias/certificate trước khi readiness thành công.
7. Audit ghi secret version, certificate fingerprint và deployment revision.

Nếu dùng Kubernetes Secret, cần bật encryption at rest cho datastore, giới hạn RBAC, tránh cho secret xuất hiện trong manifest/Helm values và kiểm soát backup của cluster. Với yêu cầu cao, cân nhắc external secret store/CSI integration cùng workload identity. Secret volume không tự biến file thành HSM-protected key.

## 13. Ví dụ Kubernetes volume và security context

Manifest khái niệm sau giả định secret volume đã được tạo bởi cơ chế được phê duyệt. Không chứa nội dung Secret hoặc password:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: app
          image: registry.example.com/orders-api:release-digest
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
          volumeMounts:
            - name: key-material
              mountPath: /var/run/key-material
              readOnly: true
      volumes:
        - name: key-material
          csi:
            driver: secrets-store.csi.k8s.io
            readOnly: true
            volumeAttributes:
              secretProviderClass: orders-api-key-material
~~~

Tên CSI driver và SecretProviderClass là ví dụ. Cấu hình thực tế cần xác minh provider, node permissions, rotation support và identity binding. Chỉ mount secret vào pod được phép; không chia sẻ volume giữa workload không cùng trust boundary.

## 14. File permissions và runtime user

Keystore file cần:

- Owner là user/group của process hoặc nhóm được chỉ định.
- Quyền đọc tối thiểu, ví dụ 0400 hoặc 0440 tùy cách mount và group access.
- Không writable bởi application process.
- Không nằm trong web root, temp directory công khai hoặc image layer.
- Không được copy vào heap dump, support bundle hoặc debug archive.
- Filesystem/volume có encryption và access control phù hợp.

Container read-only root filesystem không bảo vệ secret volume nếu volume mount có quyền rộng. Kiểm tra effective UID/GID, fsGroup, mode thực tế sau mount và quyền trên node/storage backend.

## 15. Password và secret delivery

Password bảo vệ PKCS#12 cần được quản lý như credential:

- Lưu trong secret manager hoặc secret delivery system được phê duyệt.
- Phân phối qua workload identity ngắn hạn hoặc mount riêng.
- Không truyền qua command line, log, exception message hoặc environment dump.
- Không lưu chung với file keystore trong cùng artifact hoặc repository.
- Có owner, version, rotation và audit.
- Chỉ cấp cho workload cần mở đúng keystore.

Java API thường yêu cầu char[] cho password. Dùng char[] cho phép ứng dụng ghi đè buffer sau khi sử dụng, dù không thể bảo đảm mọi bản sao nội bộ của JVM/provider đều được xóa.

## 16. Java: nạp PKCS#12 và tạo SSLContext

Ví dụ sau minh họa việc nạp identity keystore và truststore từ file mount. SecretProvider là abstraction của secret manager/CSI integration; implementation phải tránh log password và chỉ trả secret cho workload đã xác thực.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.Arrays;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

interface SecretProvider {
    char[] readChars(String secretReference);
}

SSLContext buildSslContext(
        Path identityPath,
        Path trustPath,
        SecretProvider secrets) throws Exception {

    char[] identityPassword =
            secrets.readChars("orders-api/tls/identity-password");
    char[] trustPassword =
            secrets.readChars("orders-api/tls/truststore-password");

    try {
        KeyStore identity = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(identityPath)) {
            identity.load(in, identityPassword);
        }

        KeyStore trust = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(trustPath)) {
            trust.load(in, trustPassword);
        }

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(identity, identityPassword);

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trust);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);
        return context;
    } finally {
        Arrays.fill(identityPassword, '\0');
        Arrays.fill(trustPassword, '\0');
    }
}
~~~

Đây là skeleton cần được đặt trong class, bổ sung exception type và kiểm tra alias/certificate theo ứng dụng. Ví dụ giả định password của private key entry giống password mở PKCS#12; nếu keystore/provider hỗ trợ password entry riêng, phải quản lý và truyền đúng password cho entry. Không ghi password hoặc key object vào log.

SSLContext chỉ là một phần cấu hình. Server/client cần gắn đúng SSLContext vào HTTP server, HttpClient hoặc framework. Với mTLS, cần xác minh client certificate được yêu cầu và TrustManager chỉ tin CA được duyệt.

## 17. Kiểm tra alias, certificate và expiry trước khi nhận traffic

Readiness nên xác minh:

- Alias identity tồn tại.
- Entry là PrivateKeyEntry nếu server cần private key.
- Certificate chain không rỗng và có issuer/validity hợp lệ.
- SAN chứa hostname dự kiến.
- Key usage/EKU phù hợp TLS server hoặc client authentication.
- Certificate chưa hết hạn và còn đủ thời gian trước ngưỡng rotation.
- Truststore chứa CA cần thiết và không có trust anchor ngoài policy.
- Provider/backend đúng với deployment profile.

Không chỉ kiểm tra file tồn tại. Một file PKCS#12 có thể parse được nhưng alias sai, certificate hết hạn hoặc chain không đúng. Readiness nên fail nếu identity bắt buộc không hợp lệ; log chỉ metadata như alias, serial, fingerprint và expiry.

## 18. TLS server và mTLS client authentication

TLS server dùng KeyManager để chọn private key/certificate chain trình cho client. Client xác minh hostname, chain và validity. Với mTLS, server yêu cầu client trình certificate; TrustManager xác minh chain theo trust policy.

Các điểm cần kiểm tra:

- SAN khớp hostname; không dựa vào Common Name cũ nếu client xác minh SAN.
- Server certificate có EKU serverAuth khi profile yêu cầu.
- Client certificate có EKU clientAuth khi profile yêu cầu.
- Truststore chỉ chứa CA phù hợp với đối tượng cần tin.
- Không tắt hostname verification trong outbound client.
- Không dùng TrustManager chấp nhận mọi certificate.
- TLS protocol/cipher suites phù hợp security baseline.

Nếu dùng nhiều certificate/alias, cần xác định cơ chế alias selection và SNI. Không giả định KeyManager mặc định luôn chọn alias đúng cho mọi virtual host.

## 19. Tách server identity, client identity và signing key

Một service có thể cần nhiều key purpose:

| Key | Mục đích | Backend gợi ý |
|---|---|---|
| Server TLS key | Xác thực orders-api với inbound client | PKCS#12 hoặc HSM theo policy |
| Client mTLS key | Xác thực orders-api với service nội bộ | Keystore riêng theo trust boundary |
| Document signing key | Ký chứng từ hoặc event | HSM non-exportable nếu mức độ quan trọng cao |
| Data encryption KEK | Wrap DEK cho dữ liệu lưu trữ | KMS/HSM |
| Trust anchor | Xác định CA được tin cậy | Truststore được quản lý, không chứa private key |

Không tái sử dụng TLS private key cho document signing hoặc encryption chỉ vì key type tương thích. Purpose separation giúp giảm blast radius, áp dụng policy khác nhau và rotate độc lập.

## 20. Java provider và PKCS#11/HSM

Khi dùng HSM, ứng dụng Java thường cấu hình provider PKCS#11 và truy cập key thông qua KeyStore type PKCS11 hoặc API tương ứng.

Kiến trúc:

1. HSM administrator tạo partition/token và role theo security domain.
2. Key pair được sinh bên trong HSM với thuộc tính non-extractable nếu policy yêu cầu.
3. CA phát hành certificate dựa trên CSR từ public key.
4. Certificate chain được liên kết với private key object trong HSM.
5. Java provider đăng nhập token theo workload identity/credential được bảo vệ.
6. KeyManager hoặc Signature sử dụng key handle; private key bytes không đi vào JVM.
7. HSM audit ghi operation và principal/session theo khả năng thiết bị.

Provider configuration, PIN/session lifecycle, allowed mechanisms, failover và HSM audit phụ thuộc vendor. Kiểm tra compatibility matrix giữa JDK, provider, HSM firmware và TLS algorithm. Không tự động fallback sang software provider khi HSM unavailable.

## 21. Rotation certificate không làm gián đoạn dịch vụ

Rotation nên tạo overlap có kiểm soát:

1. Theo dõi certificate expiry và bắt đầu renewal trước ngưỡng.
2. Tạo key pair mới nếu policy yêu cầu key rotation cùng certificate renewal.
3. Phát hành certificate mới với SAN/EKU/issuer phù hợp.
4. Đóng gói version mới và phân phối tới secret store.
5. Xác minh file, alias, chain và password qua deployment preflight.
6. Rollout workload theo rolling update hoặc reload được hỗ trợ.
7. Kiểm tra handshake TLS/mTLS từ client thực tế.
8. Chuyển traffic hoàn toàn sang version mới.
9. Thu hồi certificate cũ nếu cần và theo PKI policy.
10. Giữ key/certificate cũ chỉ trong thời gian cần thiết cho rollback hoặc compatibility.
11. Hủy bản sao cũ theo retention và destruction policy.

Không ghi đè file đang được process sử dụng nếu ứng dụng không hỗ trợ reload an toàn. Dùng versioned secret path hoặc atomic replacement, rồi xác minh process đã nạp version mới.

## 22. Rotation truststore và CA rollover

Khi CA nội bộ hoặc CA đối tác thay đổi:

- Thêm trust anchor/intermediate mới trước khi đối tác chuyển certificate.
- Giữ trust anchor cũ trong khoảng overlap đã được phê duyệt.
- Kiểm tra chain của cả certificate cũ và mới.
- Cập nhật tất cả consumer và vùng triển khai.
- Theo dõi handshake failure và certificate path.
- Gỡ trust anchor cũ sau khi không còn consumer hợp lệ.
- Ghi lại fingerprint, serial, owner và change record.

Truststore update có thể ảnh hưởng nhiều outbound connection. Cần kiểm tra impact và rollout theo nhóm workload; không xóa CA cũ ngay khi certificate mới vừa được phát hành.

## 23. Rollout, rollback và reload

Chiến lược rollout phụ thuộc khả năng reload TLS material:

- Nếu framework hỗ trợ reload SSLContext an toàn, triển khai version mới và swap context có kiểm soát.
- Nếu không hỗ trợ, dùng rolling restart với readiness gate và connection draining.
- Giữ đủ replica cũ trong giai đoạn overlap để tránh outage, nhưng giới hạn thời gian.
- Theo dõi handshake success, certificate fingerprint và lỗi client authentication.
- Rollback chỉ dùng version còn hợp lệ và chưa bị compromise/revoked.

Rollback không được phục hồi certificate đã bị revoke hoặc private key nghi compromise. Khi rotation là phản ứng incident, phải ưu tiên containment và key replacement theo incident plan thay vì rollback về key cũ.

## 24. Backup và khôi phục keystore

Backup PKCS#12 là bản sao chứa private key được bảo vệ bằng password. Cần:

- Chỉ backup khi policy cho phép.
- Mã hóa backup storage và giới hạn quyền đọc.
- Bảo vệ password riêng, không đặt cùng package.
- Ghi inventory version, fingerprint, owner và retention.
- Có immutable retention hoặc separation of duties phù hợp.
- Kiểm thử restore trong môi trường kiểm soát.
- Xóa temporary copy và artifact sau khi hoàn tất.

Nếu private key được tạo non-exportable trong HSM, backup phải dùng cơ chế backup/clone được vendor hỗ trợ. Không xuất private key plaintext để thay thế quy trình HSM backup.

## 25. Audit và monitoring khi deployment

Ghi nhận các sự kiện:

- Tạo key pair, CSR và certificate issue.
- Tạo hoặc cập nhật PKCS#12/truststore artifact.
- Secret version được publish và mount cho workload.
- Workload identity đọc secret và khởi tạo keystore/provider.
- Certificate fingerprint/serial đang được nạp.
- TLS handshake và client-auth failure theo mức metadata cần thiết.
- Rotation, rollback, revoke và destruction.
- Thay đổi truststore, provider configuration hoặc HSM policy.

Audit event nên có service identity, environment, key alias/ID, certificate fingerprint/serial, secret version, deployment revision, timestamp và outcome. Không log keystore password, PIN, token hoặc private key bytes.

Alert khi certificate sắp hết hạn, fingerprint ngoài baseline, alias không tồn tại, provider thay đổi, secret mount lỗi hoặc workload đọc secret từ environment không đúng.

## 26. Threats và biện pháp giảm thiểu

| Threat | Tác động | Biện pháp |
|---|---|---|
| Keystore nằm trong image/repository | Private key bị phát tán qua registry/source history | External secret delivery, scan artifact, rotate nếu đã lộ |
| Password nằm cạnh keystore | Attacker lấy cả hai và mở private key | Tách kênh, workload identity, access policy |
| File permission quá rộng | User/process khác đọc keystore | Least privilege, read-only mount, UID/GID review |
| Truststore chứa CA không tin cậy | Chấp nhận endpoint giả mạo | Trust inventory, CA approval và periodic review |
| Certificate SAN sai | Client xác minh hostname thất bại hoặc trust sai | SAN validation và handshake test |
| HSM fallback sang software | Private key rời protection boundary | Fail closed, provider pinning và outage test |
| Rotation không hoàn tất | Certificate hết hạn hoặc consumer dùng key cũ | Versioned rollout, readiness và expiry alert |
| Debug/heap dump lộ secret | Password/key có thể bị lấy từ memory | Dump access control, redaction và retention |
| Backup không restore được | Mất identity hoặc không thể phục hồi | Restore drill và key dependency inventory |

## 27. Kiểm thử deployment trước production

Test tối thiểu:

| Test | Kết quả mong đợi |
|---|---|
| Load PKCS#12 đúng password | Load thành công và đúng alias |
| Password sai | Fail rõ ràng, không fallback |
| Alias thiếu | Readiness fail |
| Certificate hết hạn | Deployment bị chặn hoặc cảnh báo theo policy |
| SAN không khớp | TLS hostname verification fail |
| Trust chain thiếu intermediate | Handshake test phát hiện |
| CA không được duyệt | TrustManager từ chối |
| mTLS thiếu client certificate | Endpoint yêu cầu mTLS từ chối |
| Client certificate sai EKU/CA | Authentication fail |
| Keystore volume không mount | Workload không ready |
| Password secret không có | Workload không ready, không log secret |
| HSM unavailable | Không fallback ngoài policy |
| Rotation version mới | Rolling deployment dùng fingerprint mới |
| Rollback | Chỉ khôi phục version còn hợp lệ |
| Backup restore | Keystore phục hồi và certificate/key match |

Kiểm thử cần chạy trên đúng JDK, provider, container base image và runtime user như production. Test local với keystore file không chứng minh HSM/PKCS#11 deployment hoạt động đúng.

## 28. Readiness và health checks

Liveness chỉ kiểm tra process còn sống. Readiness nên kiểm tra keystore và trust material bắt buộc đã được nạp và hợp lệ. Không gọi HSM/KMS quá thường xuyên trong liveness probe vì có thể tạo tải và khuếch đại outage.

Readiness check có thể kiểm tra:

- SSLContext đã khởi tạo.
- Identity alias có certificate hợp lệ.
- Certificate còn thời gian sử dụng theo threshold.
- Truststore đã nạp.
- Provider đúng cấu hình.
- Secret version và deployment revision tương thích.

Không expose password, private key, full keystore path nhạy cảm hoặc token trong health endpoint. Health response nên chỉ trả trạng thái tổng quát và correlation ID.

## 29. Quy trình vận hành và ownership

Phân vai:

| Vai trò | Trách nhiệm |
|---|---|
| PKI owner | CA policy, CSR approval, issue/revoke certificate |
| Key custodian | Key generation, protection, backup và destruction |
| Platform team | Secret delivery, mount, container security và rollout |
| Application owner | Java configuration, TLS behavior và readiness |
| Security team | Crypto baseline, access review, audit và exception |
| Incident responder | Containment, rotation khẩn cấp và evidence |

Một người không nên tự tạo, tự phê duyệt, export và xóa bằng chứng cho cùng một key operation nhạy cảm. Break-glass phải có thời hạn, scope và audit.

## 30. Checklist triển khai Java KeyStore

Trước khi đưa service vào production:

- [ ] Đã xác định server identity, client identity, signing key và trust anchor.
- [ ] Đã chọn PKCS#12, PKCS#11 hoặc provider theo threat model.
- [ ] Key pair được tạo theo quy trình và algorithm profile được duyệt.
- [ ] Certificate có SAN, EKU, validity và chain phù hợp.
- [ ] Keystore và truststore được tách theo purpose.
- [ ] Mỗi environment có key/certificate riêng.
- [ ] Keystore không nằm trong source code, image hoặc artifact công khai.
- [ ] Password được phân phối riêng qua secret provider.
- [ ] Volume read-only, file permission và runtime UID/GID được kiểm tra.
- [ ] Java khai báo keystore type/provider rõ ràng.
- [ ] Hostname verification và mTLS policy được kiểm thử.
- [ ] Không có TrustManager hoặc provider fallback không an toàn.
- [ ] Rotation, CA rollover, rollback và reload đã được diễn tập.
- [ ] Backup/restore có evidence và retention.
- [ ] Audit ghi alias/key ID, certificate fingerprint và secret version.
- [ ] Không log password, PIN, token hoặc key material.
- [ ] Readiness phát hiện certificate/alias/provider sai.
- [ ] KMS/HSM outage và secret delivery failure có runbook.

## 31. Checklist review một deployment đã chạy

Khi kiểm tra deployment hiện hữu:

- [ ] Image và repository không chứa keystore hoặc password.
- [ ] Secret mount chỉ tới đúng workload và environment.
- [ ] Keystore file có owner/mode đúng và không writable từ application.
- [ ] Alias, certificate serial/fingerprint và SAN khớp inventory.
- [ ] Truststore không có CA ngoài policy.
- [ ] JDK/provider/version khớp compatibility baseline.
- [ ] Runtime đang dùng đúng keystore path và type.
- [ ] TLS handshake, hostname verification và mTLS hoạt động đúng.
- [ ] Không có provider fallback sang software key ngoài ý muốn.
- [ ] Certificate expiry và rotation status được giám sát.
- [ ] Secret access và key operation có audit.
- [ ] Backup và restore test thành công.
- [ ] Bản keystore cũ, temporary file và artifact được xử lý đúng retention.

Thiết kế Java KeyStore deployment an toàn cần kết hợp đúng loại keystore, trust boundary, secret delivery, file permission, Java provider, TLS configuration và lifecycle vận hành. PKCS#12 phù hợp với nhiều deployment file-based khi được bảo vệ đúng cách; HSM/PKCS#11 phù hợp khi yêu cầu private key không rời cryptographic boundary. Dù chọn mô hình nào, private key phải có owner và purpose rõ, certificate/trust phải được xác minh, password phải được phân phối riêng, rotation phải có overlap và rollback được kiểm soát, còn audit phải chứng minh workload đang dùng đúng identity đã được phê duyệt.
