# Thay chứng thư đầu vào và thời điểm cần đăng nhập lại

## 1. Bối cảnh: chứng thư nào đang được thay?

Trong chương **Chứng thư và tài khoản** của module **SPRING_VAULT**, ứng dụng Java dùng Spring Vault để kết nối HashiCorp Vault qua `VaultTemplate`. Một mô hình xác thực phổ biến cho máy hoặc workload là **TLS certificate authentication**: ứng dụng gửi chứng thư X.509 và chứng minh đang sở hữu private key tương ứng trong phiên TLS; Vault kiểm tra chứng thư với cấu hình của auth method `cert` rồi cấp **Vault client token**. Những request KV, Transit hoặc PKI tiếp theo được phân quyền bằng Vault token này.

Khi thay chứng thư, câu hỏi quan trọng không chỉ là “file chứng thư mới đã xuất hiện chưa?” mà còn là **TLS client của JVM đã dùng chứng thư mới chưa, Vault role đã tin chứng thư mới chưa và Vault session cũ có cần đăng nhập lại không?**

Trước hết phải xác định đúng loại chứng thư:

| Chứng thư / dữ liệu | Vai trò | Thay đổi ảnh hưởng tới điều gì? | Có cần login lại Vault? |
|---|---|---|---|
| **Client certificate + private key** của ứng dụng để gọi Vault `auth/cert/login` | Chứng minh danh tính workload khi xác thực Vault bằng TLS certificate auth | TLS handshake, việc Vault nhận diện chứng thư, khả năng gia hạn Vault token theo certificate binding | **Có khi chuyển hẳn sang danh tính/chứng thư mới**: cần tạo session bằng chứng thư mới; token cũ có thể còn sống tạm thời, nhưng renew có thể bị từ chối. |
| **CA/truststore** để ứng dụng xác minh chứng thư TLS *server* của Vault | Xác minh đầu bên kia đúng là Vault | TLS handshake và kết nối HTTPS đến Vault | **Không mặc nhiên**; cần cập nhật truststore/SSLContext và kết nối. Login lại chỉ khi session Vault token đã mất hiệu lực hoặc cần chủ động đổi session. |
| **Chứng thư cấp bởi Vault PKI** cho HTTPS/mTLS giữa ứng dụng và một hệ thống khác | Danh tính hoặc mã hóa cho dịch vụ đích | TLS client/server của **hệ thống sử dụng chứng thư đó** | **Không mặc nhiên**; PKI certificate rotation và Vault authentication là hai cơ chế riêng, trừ khi dùng chính chứng thư ấy để xác thực Vault. |
| **Vault client token** nhận sau cert login | Dùng để gọi KV, Transit, PKI theo policy | TTL, renewal, revocation và Vault ACL | Token có thể `renew` hoặc cần đăng nhập lại tùy trạng thái; thay file chứng thư không tự cấp token mới. |

Trong bài này, **“chứng thư đầu vào”** chủ yếu là **client certificate + private key dùng để xác thực vào Vault**; hai trường hợp CA/truststore và Vault PKI được đối chiếu để tránh áp dụng sai quy trình.

## 2. Mối quan hệ giữa TLS certificate và Vault session

Đối với `cert` auth method, có **hai lớp** xác thực liên quan nhưng độc lập:

1. **TLS handshake:** ứng dụng phải tin chứng thư máy chủ Vault; khi Vault yêu cầu, ứng dụng có thể gửi client certificate và chứng minh sở hữu private key. Chứng thư phải còn hạn và có mục đích phù hợp, thường là Extended Key Usage `ClientAuth`.
2. **Vault auth login:** client gọi `POST /v1/auth/cert/login` qua kết nối TLS đã chứa chứng thư client. Vault so khớp certificate chain và các giới hạn của role (ví dụ SAN, CA, CRL/OCSP); khi thành công, Vault trả về một **Vault client token**, thời gian sống, quyền và khả năng renew.

Sau đó, request của `VaultTemplate` dùng token của session:

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng Java
    participant T as TLS client / KeyStore
    participant V as Vault cert auth
    participant S as Vault KV / Transit / PKI
    A->>T: Khởi tạo SSLContext từ client cert A
    T->>V: TLS handshake, trình chứng thư A
    A->>V: POST /v1/auth/cert/login
    V-->>A: Vault token V1 + TTL + policy
    A->>S: VaultTemplate request với token V1
    S-->>A: Kết quả theo ACL
    Note over A,T: Thay file client cert A bằng B trên disk
    Note over A,V: V1 không tự trở thành token của B
    A->>T: Tạo TLS client mới thực sự dùng cert B
    T->>V: TLS handshake, chứng thư B
    A->>V: POST /v1/auth/cert/login bằng B
    V-->>A: Vault token V2
    A->>S: Request tiếp theo dùng V2
~~~

**Không có quy tắc “thay certificate đồng nghĩa token cũ lập tức hết hạn”.** Token V1 được Vault phát hành có TTL và trạng thái thu hồi riêng. Ngay cả khi chứng thư A hết hạn hoặc bị thay, V1 có thể vẫn được chấp nhận cho những request sử dụng token cho đến khi hết TTL hoặc bị Vault revoke; việc renew có thể chịu thêm kiểm tra danh tính certificate. Vì vậy, khi cần chấm dứt quyền truy cập của V1 ngay, quản trị viên cần **thu hồi token/token tree** tương ứng chứ không chỉ thay chứng thư.

### Certificate binding khi renew

Vault `cert` auth method có cấu hình `disable_binding` (mặc định `false`). Theo mặc định, khi renew token từ certificate authentication, Vault có thể yêu cầu danh tính của chứng thư TLS hiện được trình phải phù hợp với danh tính tại lần login ban đầu. Nếu đổi từ cert A sang cert B, **renew của token V1 có thể bị Vault từ chối**, ngay cả khi B được cấp từ cùng CA và được phép login.

Giải pháp vận hành là **login mới bằng B**, lấy token V2 rồi chuyển ứng dụng sang V2. Không nên bật `disable_binding=true` chỉ để tránh phải đăng nhập lại, vì làm suy yếu ràng buộc danh tính được thiết kế trong cert auth.

## 3. Khi nào cần đăng nhập lại?

| Sự kiện | Điều cần làm | Thời điểm login lại |
|---|---|---|
| Thay **client certificate A → B** và B là credential mới dùng để xác thực Vault | Nạp B vào TLS client đang hoạt động, đóng kết nối cũ khi cần, xác minh role Vault chấp nhận B | **Ngay trong đợt chuyển đổi**, trước khi rút A; không chờ đến lúc token V1 hết hạn. |
| Chỉ thay **server TLS certificate** của Vault, CA vẫn được tin cậy | Kiểm tra chain/SAN và mở TLS connection mới | Không bắt buộc login lại nếu V1 còn hợp lệ. |
| Thay **CA/truststore** xác minh Vault server | Nạp trust anchors mới vào JVM TLS client; kiểm tra TLS kết nối mới | Không tự động login lại; chỉ login mới nếu token cần cấp lại hoặc session không còn hợp lệ. |
| Vault token còn hạn, `renew-self` thành công với credential hiện tại | Session manager tiếp tục sử dụng token | Chưa cần login lại. |
| Vault token gần max TTL, không renewable, bị revoke hoặc renew thất bại vì binding | Session manager cần nhận token khác từ auth method | Login lại bằng **chứng thư đang hoạt động và được Vault tin cậy**. |
| Pod/process bị restart, session token chỉ nằm trong memory | Tạo TLS client và SessionManager mới khi boot | Login lại lúc ứng dụng cần lấy Vault token lần đầu. |
| Chứng thư client bị thu hồi vì lộ private key | Ngừng dùng cert/key cũ, sửa Vault cert role/CRL/OCSP theo quy trình và revoke các token bị ảnh hưởng | Login lại bằng chứng thư thay thế **sau khi** credential mới đã được cho phép. Không giữ token cũ. |
| Cấp chứng thư từ Vault PKI cho mTLS ở một upstream khác | Phát hành mới/reload certificate tại upstream client hoặc server | Không cần login lại vào Vault, trừ khi vừa thay credential dùng cho Vault auth. |

> **Quy tắc trọng tâm:** Có hai công việc khác nhau: **(1) chuyển TLS client sang chứng thư B** và **(2) chuyển Vault session sang token được phát hành qua B**. Một công việc thành công không chứng minh công việc còn lại đã hoàn tất.

## 4. Cấu hình chứng thư để Vault chấp nhận login

Giả sử Vault auth method `cert` đã được mount tại `auth/cert`, role `payments-client` cấp policy `payments-kv-read`. Ứng dụng Java có chứng thư A với DNS SAN `payments.internal`, ký bởi CA dành cho client authentication.

Một ví dụ cấu hình phía Vault **chỉ dùng trong môi trường lab hoặc sau khi đã có phê duyệt quản trị**:

~~~bash
# Bật auth method nếu chưa có trong môi trường thử nghiệm:
vault auth enable cert

# Đăng ký CA và ràng buộc DNS SAN đúng workload:
vault write auth/cert/certs/payments-client \
  certificate=@client-auth-ca.pem \
  allowed_dns_sans=payments.internal \
  token_policies=payments-kv-read \
  token_ttl=20m \
  token_max_ttl=1h
~~~

Lệnh trên giả định chứng thư client A và B cùng do CA này ký và cùng có SAN `payments.internal`. Nếu role Vault ghim một chứng thư cụ thể (self-signed hoặc exact certificate), phải đăng ký/đổi trust configuration để **B được chấp nhận trước khi vô hiệu hóa A**. Khi xoay cả issuing CA, phải chuẩn bị giai đoạn chấp nhận CA cũ và mới theo cơ chế role/trust phù hợp và kiểm chứng login của từng credential.

Không dùng một CA chung quá rộng mà không ràng buộc tên/các extension thích hợp: bất kỳ certificate nào được CA tin cậy ký và đáp ứng điều kiện role đều có thể nhận policy tương ứng. Policy Vault `payments-kv-read` cũng phải tuân thủ ít quyền nhất, ví dụ:

~~~hcl
path "kv-app/data/payments/config" {
  capabilities = ["read"]
}
~~~

Vault `cert` auth yêu cầu cấu hình TLS listener cho phép client certificates (không tắt client cert processing). Nếu đứng sau load balancer/reverse proxy chấm dứt TLS, phải hiểu rõ cách Vault nhận và xác minh danh tính chứng thư được proxy chuyển tiếp; **không được tin vào header do client Internet tự gửi**.

## 5. Spring Cloud Vault: keystore, truststore và session lifecycle

Với ứng dụng Spring Boot dùng Spring Cloud Vault, cấu hình tham khảo:

~~~yaml
spring:
  cloud:
    vault:
      uri: https://vault.example.internal:8200
      authentication: CERT
      ssl:
        key-store: file:/run/secrets/vault-client/client-auth.p12
        key-store-type: PKCS12
        key-store-password: ${VAULT_CLIENT_KEYSTORE_PASSWORD}
        trust-store: file:/run/secrets/vault-client/vault-trust.p12
        trust-store-type: PKCS12
        trust-store-password: ${VAULT_TRUSTSTORE_PASSWORD}
        cert-auth-path: cert
        role: payments-client
      session:
        lifecycle:
          enabled: true
          refresh-before-expiry: 10s
          expiry-threshold: 20s
~~~

**Chú thích theo phiên bản:** `spring.cloud.vault.ssl.role` dùng chọn cert auth role khi login và có trong các bản Spring Cloud Vault mới (thuộc dòng 5.x); nếu đang chạy phiên bản khác, phải tra property appendix đúng release. Bản không hỗ trợ `role` thường để Vault tự tìm role khớp chứng thư. Các cấu hình `ssl.*` ở đây dành cho **kết nối Spring Cloud Vault đến Vault**, không phải `server.ssl.*` của HTTP server Spring Boot.

Các thành phần:

| Cấu hình | Mục đích |
|---|---|
| `authentication: CERT` | Chọn xác thực Vault bằng TLS client certificate. |
| `ssl.key-store` | Nơi lưu **chứng thư client + private key**; không được chỉ chứa public certificate. |
| `ssl.trust-store` | CA/chứng thư dùng để **tin Vault HTTPS server**; khác với key-store. |
| `ssl.cert-auth-path` | Đường dẫn mount auth method, ví dụ `cert` tương ứng `auth/cert/login`. |
| `ssl.role` (nếu phiên bản hỗ trợ) | Chọn cert auth role cụ thể tại login, ví dụ `payments-client`. |
| `session.lifecycle.enabled` | Cho phép Spring Cloud Vault quản lý renew/re-login cho Vault token thay vì giữ token tĩnh. |
| `refresh-before-expiry`, `expiry-threshold` | Điều chỉnh thời điểm refresh TTL và ngưỡng coi token sắp hết hạn. |

Trong Spring Vault Core, cấu hình qua `AbstractVaultConfiguration` có thể tạo `ClientCertificateAuthentication` từ `ClientCertificateAuthenticationOptions`; vẫn phải cấu hình HTTP client/SSLContext với client certificate và truststore. Với Spring Cloud Vault có auto-configuration, tránh tự tạo thêm SessionManager cạnh tranh nếu không có lý do rõ ràng.

**Điều quan trọng nhất khi rotate:** cấu hình `file:/run/.../client-auth.p12` chỉ là đường dẫn. JVM/HTTP client có thể đã đọc KeyStore và tạo `SSLContext`/**KeyManager** từ khi khởi động. **Thay file trên filesystem không chứng minh SSLContext đang sử dụng file mới.** Không mặc định Spring Cloud Vault sẽ hot-reload private key, client certificate, truststore và mọi connection pool chỉ vì Secret volume đã thay đổi.

## 6. Một ví dụ Java đọc secret qua VaultTemplate

Service sau đọc một khóa KV v2 để minh họa hành vi ứng dụng **sau khi đã login**. Spring Cloud Vault cung cấp `VaultTemplate` và session manager; code nghiệp vụ không tự gọi cert login:

~~~java
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultTemplate;

@Service
public class PaymentSettingsReader {

    private final VaultTemplate vaultTemplate;

    public PaymentSettingsReader(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public Map<String, Object> load() {
        var kv = vaultTemplate.opsForVersionedKeyValue("kv-app");
        var response = kv.get("payments/config");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                    "Expected KV v2 secret is unavailable");
        }
        return response.getData();
    }
}
~~~

Ví dụ trên không trực tiếp thực hiện certificate rotation. Để kiểm tra **chứng thư B thực sự được dùng cho lần login mới**, cần xác minh TLS client và session lifecycle ở tầng cấu hình, sau đó dùng một request `VaultTemplate` như trên để kiểm tra quyền và khả năng truy cập KV. Đọc KV thành công bằng một token V1 còn hạn **chưa đủ** để kết luận chuyển đổi certificate đã hoàn tất.

## 7. Quy trình thay chứng thư đầu vào không gián đoạn

Giả sử muốn chuyển từ certificate **A** sang **B** cho nhiều Pod đang chạy. Quy trình triển khai:

1. **Kiểm kê:** xác định hostname Vault, TLS termination, auth mount, cert role, Vault policy, identity của ứng dụng, nơi chứa KeyStore/truststore, từng Deployment và TTL của Vault token. Phân biệt client-auth certificate với chứng thư PKI đang cấp cho downstream.
2. **Chuẩn bị B:** cấp cert có private key tương ứng, thời hạn hợp lệ, EKU cho client authentication và SAN/extension được Vault role chấp nhận. Không tái sử dụng private key A nếu quy trình yêu cầu thay cả khóa.
3. **Cho Vault tin B trước:** nếu dùng pinned cert hoặc CA mới, cập nhật role/chain/trust configuration để B có thể login. Với CA-based role và cùng CA, vẫn phải đối chiếu `allowed_dns_sans`, CN/URI và revocation policy.
4. **Kiểm tra B một cách độc lập:** dùng một workload/canary hoặc môi trường thử nghiệm với TLS client B để gọi `auth/cert/login` và đọc đúng path được phép. Không xem việc Vault chấp nhận một cert ở TLS handshake là bằng chứng role auth đã cấp đúng policy.
5. **Phân phối atomically:** tạo KeyStore PKCS12 mới và mount Secret/file an toàn, tránh để các bản nửa chừng hoặc file chứa private key bị người không có quyền đọc. Không commit key hoặc password vào Git.
6. **Làm mới TLS client:** nếu ứng dụng **không có cơ chế hot-reload được thiết kế và kiểm thử**, dùng **rolling restart** từng Pod để Spring khởi tạo HTTP client/SSLContext từ file B và login lại. Nếu có reload động, phải thay KeyManager/TrustManager/SSLContext theo contract của HTTP client, đóng hoặc tái tạo pooled TLS connections và thiết lập session mới bằng B.
7. **Chuyển session sang B:** xác minh có một lần `auth/cert/login` thành công bằng B; Vault token V2 phải có role/policies đúng. Mỗi Pod phải dùng phiên mới thay vì tiếp tục dựa vào token V1 của cert A.
8. **Rút A:** sau khi toàn bộ replica đã hoạt động bằng B, loại A khỏi nơi phân phối, cập nhật CRL/OCSP hoặc role khi phù hợp. Nếu chính sách yêu cầu vô hiệu hóa quyền truy cập ngay, **revoke Vault token cũ** và đánh giá các dynamic leases liên quan.
9. **Giám sát và hoàn tất:** kiểm tra tỷ lệ lỗi TLS, login/renew, `VaultTemplate` đọc KV, restart và readiness. Ghi nhận certificate serial/fingerprint, thời điểm triển khai và kết quả; không ghi private key hay Vault token.

~~~mermaid
flowchart TD
    A[Chuẩn bị cert B và private key] --> B[Đăng ký trust và role cho B tại Vault]
    B --> C[Canary login bằng B]
    C --> D{Đã được cấp token và policy đúng?}
    D -- Không --> E[Kiểm tra CA, SAN, EKU, TLS, role, CRL]
    E --> C
    D -- Có --> F[Đưa KeyStore B tới Pod]
    F --> G[Reload SSLContext + session hoặc rolling restart]
    G --> H[Pod login mới bằng B, nhận V2]
    H --> I{Mọi replica đọc secret thành công?}
    I -- Không --> J[Giữ A trong giai đoạn overlap, xử lý lỗi]
    J --> G
    I -- Có --> K[Ngừng tin A, xử lý token/lease cũ]
    K --> L[Giám sát và đóng đợt rotation]
~~~

### Vì sao rolling restart thường đáng tin cậy?

Trên Kubernetes, thay một `Secret` đang được mount thành volume có thể làm file trên disk được cập nhật sau một khoảng thời gian, nhưng **không tự xây lại JVM TLS client**. Nếu dùng Secret qua environment variable, Pod cũng phải restart để nhận giá trị mới. Với Spring Cloud Vault không có cơ chế hot-reload riêng được chứng minh, rolling update từng Pod tạo **một TLS client mới + một Vault session mới** ở thời điểm startup, dễ xác minh hơn.

Ví dụ thao tác trên **Deployment thử nghiệm** sau khi Secret được cập nhật:

~~~bash
kubectl -n payments rollout restart deployment/payments-api
kubectl -n payments rollout status deployment/payments-api
kubectl -n payments get pods -l app=payments-api
~~~

Với production, cấu hình `maxUnavailable`/`maxSurge`, readiness và dependency Vault phù hợp để giữ khả năng phục vụ. Không đưa password KeyStore lên command line hoặc log của rollout.

## 8. Kiểm tra chứng thư trước khi đưa vào ứng dụng

Để kiểm tra những trường thông thường của certificate **công khai** (không in private key):

~~~bash
openssl x509 -in client-B.pem -noout \
  -subject -issuer -dates -serial -fingerprint -sha256

openssl x509 -in client-B.pem -noout -text
~~~

Kiểm tra `NotBefore`/`NotAfter`, DNS/URI SAN, `Extended Key Usage: TLS Web Client Authentication`, certificate chain và serial. Đối chiếu cert B với policy Vault role. Dòng `-text` có thể chứa thông tin danh tính và các extension, vì vậy chỉ dùng ở môi trường vận hành được phép; không copy toàn bộ output vào log công khai.

Nếu KeyStore là PKCS12:

~~~bash
# Chỉ là minh họa tạo keystore trong lab, không dùng private key thật trong repo.
openssl pkcs12 -export \
  -in client-B.pem \
  -inkey client-B.key \
  -certfile client-chain.pem \
  -name vault-client \
  -out client-auth-B.p12

# Lệnh yêu cầu mật khẩu tương tác; không truyền password qua argv.
keytool -list -v -storetype PKCS12 -keystore client-auth-B.p12
~~~

Xác minh KeyStore có **PrivateKeyEntry** (không phải chỉ `trustedCertEntry`), alias được KeyManager chọn đúng, chain đầy đủ và password triển khai khớp. Một PKCS12 có chứng thư công khai nhưng thiếu private key **không thể dùng để chứng minh danh tính client khi TLS handshake**.

Thao tác login thử từ môi trường cô lập:

~~~bash
# Vault trả về client_token trong response; không dùng output này
# làm log chung hoặc commit vào hệ thống lưu trữ.
curl --request POST \
  --cacert vault-server-ca.pem \
  --cert client-B.pem \
  --key client-B.key \
  --header "Content-Type: application/json" \
  --data '{"name":"payments-client"}' \
  "$VAULT_ADDR/v1/auth/cert/login"
~~~

`--cacert` ở đây dùng xác minh **server TLS certificate của Vault**; `--cert`/`--key` là **client credential** để đăng nhập Vault. Cần kiểm tra Vault token nhận được chỉ trong môi trường lab được bảo vệ; tránh đưa response có token vào terminal history, artifact build hoặc dashboard công khai. Trong vận hành thực tế có thể dùng công cụ kiểm thử redaction để chỉ xuất trạng thái, role và policy cần thiết.

## 9. Vai trò của LifecycleAwareSessionManager

Spring Vault cung cấp `LifecycleAwareSessionManager` giúp quản lý `LoginToken` sau khi thực hiện auth login:

- **Renew**: khi token còn renewable và chưa chạm giới hạn lifetime, session manager có thể gia hạn, thường **không login lại**.
- **Re-login**: khi không thể tiếp tục dùng session token (TTL chạm giới hạn, token không renewable, bị revoke hoặc renew thất bại), session manager sử dụng `ClientAuthentication` để lấy token mới.
- **Shutdown**: lifecycle manager có thể revoke những `LoginToken` do nó quản lý khi đóng session; nếu Pod bị kill đột ngột thì không chắc revoke đã chạy.

Không nên dựa vào `LifecycleAwareSessionManager` để quyết định thời điểm **thay TLS certificate A → B**. Nó quản lý **Vault token**, không mặc nhiên theo dõi thay đổi file KeyStore, tạo `SSLContext` mới, tắt socket cũ và chuyển ngay sang danh tính mới.

Nếu cần hot-reload không restart, thiết kế và kiểm thử một cơ chế cấp lại TLS client + session đồng bộ. Không giả định đổi một trường cấu hình hoặc gọi `renew` sẽ buộc login bằng cert B. Trước khi hủy token cũ, tính đến tác động đối với secret leases: Vault có thể revoke lease phụ thuộc token khi token bị thu hồi/hết hạn. Nếu đang dùng dynamic secrets, cần cơ chế renew/reissue riêng như `SecretLeaseContainer` hoặc luồng lấy lại credential theo lifecycle ứng dụng.

## 10. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| `SSLHandshakeException`, `bad_certificate` hoặc `certificate_unknown` | Certificate B thiếu EKU, private key không khớp, client cert không được gửi, trust/chain sai, TLS termination cấu hình sai | Xem handshake ở môi trường test, KeyStore entry, chứng thư client và server, truststore và Vault TLS listener. |
| `PKIX path building failed` | JVM không tin chain chứng thư TLS server Vault | Cập nhật **truststore**/SSLContext; không sửa nhầm cert auth role. |
| `auth/cert/login` trả `400/403` | Cert handshake đã có nhưng không khớp CA, SAN/role, CRL/OCSP hoặc auth path | So khớp cấu hình Vault `auth/cert/certs/<role>` và log/audit được phép. |
| Chứng thư B đã nằm trên disk nhưng login vẫn hiện danh tính A | JVM/HTTP connection pool/KeyManager đang dùng SSLContext cũ | Rolling restart hoặc cơ chế reload TLS client đã kiểm thử; kiểm tra serial/fingerprint từ phía Vault audit. |
| V1 renew thất bại ngay sau đổi cert A → B | Certificate binding giữ danh tính từ lần login cũ, token max TTL, hoặc token bị revoke | Đăng nhập mới bằng B, dùng V2; không vô hiệu hóa binding để che lỗi. |
| Đọc KV bằng `VaultTemplate` vẫn thành công dù B login chưa được | Ứng dụng còn dùng V1 hợp lệ | Xác minh sự kiện login của **B** và token/session mới, không chỉ nhìn một request đọc thành công. |
| Sau restart, tất cả Pod không thể login | Role chưa tin B, KeyStore/password sai, secret volume chưa sẵn sàng, Vault outage | Dừng rollout, giữ replica A đang hoạt động nếu an toàn và khôi phục trust/config. |
| `403 permission denied` ở `kv-app/data/...` sau login thành công | Token V2 thiếu policy phù hợp hoặc path KV v2 không đúng | So sánh policy/role/token metadata; không tự retry login liên tục như lỗi mạng. |
| Đã revoke cert A nhưng token V1 vẫn dùng được | Revocation chứng thư và revocation Vault token là hai cơ chế khác nhau | Tìm và thu hồi token liên quan theo quy trình; điều chỉnh TTL để giới hạn thời gian rủi ro. |

Các lỗi authentication, authorization và network có thể cùng xuất hiện sau rollout. Khi chẩn đoán, ghi **phase** rõ ràng: TLS handshake → `auth/cert/login` → Vault token renew → `VaultTemplate` request. Không log private key, password, header `X-Vault-Token` hoặc raw body login.

## 11. Giám sát và kiểm thử tích hợp

Hãy dùng Vault lab, client certificate A/B tự cấp cho kiểm thử, auth role giới hạn path và Spring Boot app có `VaultTemplate`. Tối thiểu kiểm tra:

| Test case | Thực hiện | Kết quả kỳ vọng |
|---|---|---|
| Login ban đầu | App khởi động với KeyStore chứa A | Vault cert login trả token V1; đọc đúng KV v2 path có quyền. |
| B được Vault chấp nhận | Cấp B cùng CA/SAN; login độc lập trước khi cập nhật app | B lấy được token với role/policy dự định, không được thêm quyền. |
| Thay file khi app đang chạy | Thay file PKCS12 trên volume **mà chưa reload SSLContext** | Không tự kết luận app đã dùng B; phân tích TLS/login chứng minh có thể vẫn dùng A. |
| Rolling restart với B | Đổi Secret/volume rồi restart canary/Pod | Pod mới login qua B và `VaultTemplate` đọc được KV. |
| Renew ở đúng identity | Tạo token V1 bằng A, đổi TLS credential sang B và thử renew theo cấu hình mặc định | Quan sát binding có thể làm renew V1 thất bại; login B thành công và nhận V2. |
| Thử certificate hết hạn/không tin cậy | Dùng chứng thư test hết hạn, sai SAN hoặc CA không đăng ký | Login/handshake bị từ chối đúng tầng; không xuất token. |
| Thay Vault server CA | Chuyển sang certificate server có CA mới trong lab | App cần truststore mới; client cert auth role không phải nơi sửa trust phía client. |
| Quyền KV sau login | Đổi policy role test để bỏ `read` | Login vẫn có thể thành công nhưng KV `403`; phân biệt lỗi ACL với lỗi certificate. |
| Thu hồi V1 khi ngừng dùng A | Revoke token cũ bằng quy trình admin trên lab | Request dùng V1 bị từ chối; luồng dùng V2 tiếp tục làm việc. |

Một kiểm thử tích hợp Java cho hành vi **đọc secret sau login** (không tự kiểm chứng rotation) có thể viết như sau:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.vault.core.VaultTemplate;

@SpringBootTest
class VaultCertificateAuthenticationIT {

    @Autowired VaultTemplate vaultTemplate;

    @Test
    void readsKvAfterCertificateLogin() {
        var kv = vaultTemplate.opsForVersionedKeyValue("kv-app");
        var secret = kv.get("payments/config");
        assertNotNull(secret, "Lab KV secret must exist and be readable");
    }
}
~~~

Test này yêu cầu một Vault server và cert auth role đã được cấu hình; nếu chưa có server/KeyStore phù hợp, nó sẽ fail ngay ở khâu setup. Với kiểm thử **rotation**, cần test orchestration tái tạo HTTP client và session, thực hiện login B rồi quan sát role và identity từ audit/metadata redacted; không thể chỉ mock `VaultTemplate` hay chỉ assert một lần đọc KV bằng V1.

### Gợi ý metric/alert cho production

- Thời điểm chứng thư client A/B hết hạn, số ngày còn lại, số replica đã chạy chứng thư mới (chỉ dùng serial/fingerprint trong phạm vi giám sát được phép).
- Tỷ lệ thành công/thất bại của TLS handshake, `auth/cert/login`, `auth/token/renew-self` và các request KV/Transit/PKI.
- Số lần re-login không mong muốn, TTL Vault token tổng hợp, lỗi `403` sau login và độ trễ Vault.
- Readiness của Pod, tỷ lệ restart hoặc rollout failure. Không ép liveness phụ thuộc trực tiếp vào Vault uptime để tránh restart dây chuyền khi Vault tạm gián đoạn.
- Audit trail actor/role/cert serial cùng thời điểm chuyển A → B, nhưng **không** gắn token, private key hoặc raw secret lên nhãn metric.

## 12. Checklist trước khi tuyên bố thay chứng thư thành công

- [ ] Xác định chính xác chứng thư client auth, Vault server CA hay cert PKI downstream đang được thay.
- [ ] Certificate B còn hạn, có private key khớp, EKU/SAN thích hợp và chain hợp lệ.
- [ ] Vault cert auth role tin certificate B, giới hạn identity và gắn policy ít quyền nhất.
- [ ] Keystore/truststore mới được phân phối an toàn và JVM TLS client **thực sự nạp lại** chúng.
- [ ] Một phiên `auth/cert/login` bằng B đã thành công; token V2 có đúng policies/TTL.
- [ ] `VaultTemplate` thực hiện được các thao tác cần thiết **bằng V2** trên từng replica.
- [ ] Token/lease phụ thuộc session A được xử lý theo yêu cầu vận hành và bảo mật.
- [ ] Chứng thư A được loại bỏ hoặc revoke **sau khi** B hoạt động ổn định; không kéo dài khoảng overlap ngoài kế hoạch.
- [ ] Các thông số lỗi, audit, readiness và cảnh báo được kiểm tra trong vòng rotation thực.

## 13. Tổng kết

Trong SPRING_VAULT, thay chứng thư đầu vào dùng cho Vault `cert` authentication đòi hỏi **Vault tin chứng thư mới**, **Spring Vault dùng đúng KeyStore/TLS context mới** và **ứng dụng tạo một Vault session mới bằng chứng thư đó**. Vault token vẫn có lifecycle độc lập: nó có thể renew khi còn hợp lệ, hoặc cần re-login khi chạm giới hạn, bị revoke hay không còn đáp ứng certificate binding. Thay truststore server hoặc chứng thư PKI của hệ thống khác có cơ chế riêng, không mặc nhiên yêu cầu đăng nhập lại Vault.

Trong hệ thống Java/Kubernetes, quy trình đáng tin cậy thường là chuẩn bị B, kiểm chứng login B, rolling restart các Pod không có hot-reload TLS được xác minh, xác nhận nhận token V2 và đọc được secret, sau cùng loại A và xử lý token/lease cũ. Việc phân biệt tầng TLS, chứng thư và Vault session giúp tránh cả lỗi gián đoạn lẫn lỗ hổng quyền truy cập tồn tại sau rotation.

## Tài liệu tham khảo

- HashiCorp Vault — [TLS Certificate Auth Method](https://developer.hashicorp.com/vault/docs/auth/cert).
- HashiCorp Vault — [TLS Certificate Auth HTTP API](https://developer.hashicorp.com/vault/api-docs/auth/cert), gồm `auth/cert/login` và `disable_binding`.
- Spring Cloud Vault — [TLS Certificate Authentication](https://docs.spring.io/spring-cloud-vault/reference/authentication.html).
- Spring Cloud Vault — [Common application properties](https://docs.spring.io/spring-cloud-vault/reference/appendix.html).
- Spring Vault — [Authentication methods and Token Lifecycle](https://docs.spring.io/spring-vault/reference/vault/authentication.html).
- Spring Vault — [Credential Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html).
- Spring Cloud Vault — [SSL Bundles](https://docs.spring.io/spring-cloud-vault/reference/ssl-bundles.html), dành cho chứng thư PKI quản lý bởi Vault được ứng dụng khác sử dụng.
