# Keystore và chứng thư phía client khi cần

## 1. Khi nào ứng dụng Spring Vault cần chứng thư client?

Ứng dụng Java dùng **Spring Vault** thường truy cập **HashiCorp Vault** qua HTTPS để xác thực theo workload và dùng `VaultTemplate` với KV secrets, token/lease, Transit encryption, PKI. Trong kết nối HTTPS thông thường, **máy chủ Vault xuất trình chứng thư** để Java xác minh danh tính máy chủ. Java cần **truststore** chứa CA tin cậy nhưng không nhất thiết cần chứng thư riêng của client.

Một số hệ thống yêu cầu thêm **mutual TLS (mTLS)**: cả máy chủ lẫn ứng dụng đều chứng minh danh tính bằng chứng thư X.509. Lúc này, Java phải có **client certificate** và **private key** tương ứng. Trong triển khai Java, chúng thường được quản lý dưới dạng một **keystore**, chẳng hạn tệp PKCS#12 (`.p12`).

Điều quan trọng là phân biệt ba lớp:

| Lớp | Mục đích | Thành phần thường dùng |
| --- | --- | --- |
| **HTTPS xác minh server** | Java xác định mình đang nối đúng Vault/proxy được tin cậy. | Truststore của Java; kiểm tra chuỗi CA và SAN/hostname của server. |
| **mTLS xác minh client** | Vault listener hoặc gateway xác định Java đang sở hữu private key hợp lệ. | Keystore client có private key và certificate chain; CA tin cậy ở phía server. |
| **Vault authentication & policy** | Vault xác định workload được nhận token nào và có quyền đọc/ghi API path nào. | Kubernetes, AppRole, token hoặc Vault certificate auth; policy và token/lease. |

**mTLS thành công không mặc nhiên cấp quyền truy cập Vault.** Vault vẫn cần một cơ chế authentication phù hợp và token/policy để cho phép API như `/v1/secret/data/...`, Transit hoặc PKI. Ngược lại, token Vault hợp lệ không thể giúp client vượt qua một TLS listener bắt buộc chứng thư client nếu Java chưa xuất trình chứng thư đúng.

## 2. Luồng xác minh hai chiều

```text
 Java / Spring Vault                       Vault TLS listener hoặc gateway
 ┌───────────────────┐                     ┌─────────────────────────┐
 │ truststore: CA    │                     │ server certificate + key│
 │ keystore: cert+key│                     │ trusted client CA       │
 └───────────────────┘                     └─────────────────────────┘
           │                                           │
           │────────── TLS ClientHello ───────────────►│
           │◄──────── server certificate ─────────────│
           │  Xác minh CA, thời hạn, SAN/hostname      │
           │◄──────── yêu cầu client certificate ─────│
           │────────── client certificate ────────────►│
           │────────── chứng minh sở hữu private key ─►│
           │  Server xác minh chain, chứng thư client  │
           │◄════════ kết nối TLS được thiết lập ═════│
           │────────── HTTP Vault API /v1/... ────────►│
           │                 AuthN + policy tại Vault  │
```

Sơ đồ diễn giải logic của TLS handshake; thứ tự, các thông điệp và cách chứng minh sở hữu khóa có khác biệt giữa các phiên bản TLS. **Private key không được gửi qua mạng** trong quá trình bắt tay.

Ở một kết nối HTTPS có mTLS, client thực hiện hai vai trò độc lập:

1. **Xác minh server:** dùng truststore, kiểm tra chuỗi CA và **hostname trong URL** khớp với Subject Alternative Name (SAN) của chứng thư server.
2. **Chứng minh danh tính client:** khi server yêu cầu, chọn chứng thư phù hợp trong keystore và dùng private key để chứng minh quyền sở hữu.

Chứng thư client không thay cho việc Java xác minh chứng thư server. Trong hệ thống dùng cả hai hướng TLS, hai phía thường có **CA/trust anchor riêng**, mặc dù một tổ chức có thể quản lý chúng trong cùng hạ tầng PKI.

## 3. Truststore, keystore và certificate chain có gì khác?

### 3.1. Tệp keystore client chứa những gì?

Một keystore PKCS#12 cho mTLS thường cần ít nhất:

- **Private key entry:** private key thuộc về đúng workload Java; không xuất hiện trong source code, log hay file công khai.
- **Leaf client certificate:** chứng thư X.509 chứa public key tương ứng và danh tính được CA cấp cho workload.
- **Certificate chain:** các chứng thư intermediate CA cần thiết để phía server dựng chuỗi tin cậy.

Ví dụ:

```text
vault-client.p12
└── alias: payments-worker
    ├── private key                        [bí mật]
    └── certificate chain
        ├── leaf: CN=payments-worker       [chứng thư client]
        └── issuing intermediate CA        [nếu có]

vault-truststore.p12                       [phía Java tin server]
└── alias: vault-server-root
    └── CA dùng xác minh Vault/proxy        [chứng thư CA công khai]
```

**Keystore** phục vụ việc *xuất trình danh tính client*; **truststore** phục vụ việc *xác minh danh tính server*. Đừng chỉ copy `vault-truststore.p12` rồi kỳ vọng Java có thể xuất trình chứng thư client: một truststore chỉ chứa CA thường **không có private key** để tham gia mTLS.

Một keystore cũng có thể chứa nhiều alias/client identity. TLS client phải chọn đúng alias phù hợp với CA được server chấp nhận, thuật toán chữ ký và cấu hình chứng thư. Với một ứng dụng chỉ cần một danh tính client, dùng keystore riêng có **một private-key entry** giúp giảm rủi ro chọn nhầm.

### 3.2. Các yêu cầu của chứng thư client

Chứng thư phải được cấp theo chính sách PKI của môi trường. Khi đánh giá một chứng thư dùng cho TLS client authentication, cần kiểm tra:

| Thuộc tính | Điều cần kiểm tra |
| --- | --- |
| Public/private key | Public key trong chứng thư khớp private key của workload. |
| Issuer/chain | Server hoặc gateway tin CA phát hành; intermediate chain được cung cấp đầy đủ. |
| Validity | Chứng thư chưa hết hạn và chưa tới thời điểm bắt đầu hiệu lực; đồng hồ hệ thống đúng. |
| Extended Key Usage (EKU) | Khi EKU được áp dụng, phải cho phép **TLS Web Client Authentication** (`clientAuth`). |
| Key Usage | Phù hợp thuật toán và yêu cầu chữ ký cho TLS client authentication. |
| Identity | Subject/SAN và ràng buộc nhận diện khớp chính sách của server hoặc Vault certificate auth. |
| Thu hồi chứng thư | Cách kiểm tra revocation/CRL hoặc OCSP tùy hạ tầng PKI và cấu hình bên xác minh. |

Không dùng chứng thư server chỉ vì nó có thể xuất khẩu sang PKCS#12. Chứng thư server thường được cấp cho mục đích `serverAuth`; một chứng thư dùng cho `clientAuth` cần được cấp và kiểm soát theo quy trình quản lý danh tính workload.

### 3.3. Chứng thư client không phải Vault token

Một chứng thư mTLS xác minh quyền sở hữu private key tại **lớp TLS**. Một **Vault token** là credential riêng do Vault quản lý, có policy và vòng đời TTL/renewal/revocation. Nếu đăng nhập bằng **Vault certificate authentication method**, Vault có thể dùng chứng thư TLS client để cấp **Vault token**, sau đó các lời gọi KV/Transit/PKI tiếp tục được cấp quyền theo token.

Do đó, thời hạn chứng thư X.509 và thời hạn Vault token là **hai vòng đời độc lập**. Xoay chứng thư không tự gia hạn token đang tồn tại, và gia hạn token không kéo dài thời gian hiệu lực của chứng thư.

## 4. Hai cách sử dụng mTLS với Vault

### Trường hợp A — mTLS để bảo vệ đường truyền, xác thực Vault bằng cách khác

Môi trường yêu cầu mọi ứng dụng kết nối HTTPS đến Vault phải xuất trình chứng thư. Java dùng keystore để hoàn tất TLS handshake, sau đó dùng một cơ chế Vault auth khác, ví dụ AppRole hoặc Kubernetes authentication, để nhận token.

```text
Java keystore -> mTLS listener kiểm tra client certificate -> HTTPS thành công
                                                        │
                                                        ▼
                                         Kubernetes/AppRole login
                                                        │
                                                        ▼
                                         Vault token + policy
                                                        │
                                                        ▼
                                         VaultTemplate gọi KV/Transit/PKI
```

Ở đây **bật mTLS không đồng nghĩa phải chọn `CERT` authentication** trong Spring Cloud Vault. Client certificate chỉ là yêu cầu transport; Vault authentication vẫn do cơ chế được lựa chọn quyết định.

### Trường hợp B — Dùng chứng thư client để đăng nhập Vault

Vault có **certificate authentication method** (`cert`). Nếu auth method được bật và cấu hình ràng buộc danh tính chứng thư/CA với policy, client có thể dùng chứng thư đã xuất trình ở TLS để thực hiện login và nhận token.

Điều kiện cần kiểm tra:

1. Listener/gateway thực sự truyền đến Vault ngữ cảnh TLS client certificate đúng theo mô hình được hỗ trợ.
2. Vault `cert` auth method đã được bật tại **mount path** phù hợp và có cấu hình tin cậy/ràng buộc chứng thư đúng workload.
3. Chứng thư client khớp các điều kiện của auth method; policy gán cho token giới hạn các API path cần thiết.
4. Spring Vault/Spring Cloud Vault dùng đúng cơ chế certificate authentication, thay vì chỉ cấu hình keystore rồi giả định đã login.

**Lưu ý:** tin một CA có nhiều chứng thư không tự tạo được nguyên tắc phân quyền theo từng workload. Nếu phía Vault cert auth cho phép cả một CA, phải ràng buộc thêm danh tính chứng thư theo chính sách đã thiết kế (chẳng hạn subject hoặc SAN/thuộc tính được hỗ trợ), tránh cấp quyền rộng ngoài mục tiêu. Mức kiểm soát cụ thể tùy cấu hình cert auth và phiên bản Vault.

## 5. Chuẩn bị keystore PKCS#12 từ chứng thư được cấp

Giả sử nhóm PKI đã cấp cho workload Java ba tệp:

```text
client.crt                # chứng thư client
client-key.pem            # private key tương ứng (bí mật)
client-issuing-chain.pem  # chuỗi CA trung gian cho chứng thư client
```

Đây là **đầu vào được cấp hợp lệ**, không phải tệp có sẵn trong dự án. Trước khi dùng, cần xác minh thông tin cấp phát, danh tính workload, mục đích `clientAuth`, tính hợp lệ của chuỗi CA và quyền truy cập vào private key.

### 5.1. Đóng gói vào PKCS#12

Với OpenSSL, có thể tạo keystore chứa private key và certificate chain:

```bash
openssl pkcs12 -export \
  -inkey client-key.pem \
  -in client.crt \
  -certfile client-issuing-chain.pem \
  -name payments-worker \
  -out vault-client.p12
```

OpenSSL sẽ hỏi mật khẩu bảo vệ keystore theo cơ chế của lệnh. **Không điền mật khẩu thật trực tiếp vào source code, tài liệu hoặc tham số `-passout` để bị lưu trong shell history.** Với môi trường tự động hóa, mật khẩu/khóa phải được phân phối bằng cơ chế quản lý bí mật phù hợp và quyền file tối thiểu.

Trong thực tế, một PKI có thể bàn giao sẵn PKCS#12; khi đó không cần xuất private key ra PEM chỉ để đóng gói lại. Nên ưu tiên quy trình khiến private key ít bị di chuyển và sao chép nhất.

### 5.2. Kiểm tra alias và loại entry

```bash
keytool -list -v -storetype PKCS12 -keystore vault-client.p12
```

Kiểm tra:

- Alias mong muốn (ví dụ `payments-worker`) tồn tại.
- `Entry type` của danh tính client là **`PrivateKeyEntry`**, không chỉ là `trustedCertEntry`.
- Certificate chain và issuer hợp lệ; ngày hết hạn và EKU phù hợp.
- Không có chứng thư/khóa của workload khác vô tình được đóng gói chung.

Chỉ đọc thông tin chứng thư từ lệnh trên; đừng đưa toàn bộ stdout, tệp PKCS#12, private key hoặc mật khẩu vào hệ thống log/chia sẻ không kiểm soát.

### 5.3. Đưa chứng thư CA của server vào truststore

Nếu Vault hoặc ingress dùng CA nội bộ chưa được JVM tin, chuẩn bị một truststore **riêng** cho việc xác minh phía server:

```bash
keytool -importcert \
  -alias vault-server-root \
  -file vault-server-root-ca.pem \
  -keystore vault-truststore.p12 \
  -storetype PKCS12
```

Tệp `vault-server-root-ca.pem` phải được xác minh nguồn/fingerprint bằng kênh quản trị độc lập trước khi nhập. Cấu hình server có thể phải gửi thêm intermediate chain. **Không lấy private key của CA hoặc Vault server** để cài đặt lên máy ứng dụng.

Nếu Vault API nằm sau ingress kết thúc TLS, CA mà Java cần tin là **CA ký chứng thư HTTPS của ingress**, còn client certificate được ingress kiểm tra theo cấu hình mTLS của nó. Nếu ingress chỉ chuyển tiếp TLS (passthrough), Vault listener mới là phía trực tiếp nhận và xác minh chứng thư client.

## 6. Cấu hình JSSE cho Spring Vault trực tiếp

Khi ứng dụng sử dụng HTTP transport dựa trên JSSE mặc định, có thể cung cấp cấu hình keystore và truststore qua **JVM system properties**:

```text
-Djavax.net.ssl.keyStore=/etc/vault/tls/vault-client.p12
-Djavax.net.ssl.keyStoreType=PKCS12
-Djavax.net.ssl.keyStorePassword=<mật-khẩu-keystore>

-Djavax.net.ssl.trustStore=/etc/vault/tls/vault-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=<mật-khẩu-truststore>
```

Các chuỗi trong dấu `<...>` là placeholder, **không phải giá trị mật khẩu thật**. Nhiều môi trường ghi lại Java command line/process arguments, nên cần thiết kế cách truyền bí mật tránh lộ mật khẩu. Với yêu cầu cách ly tốt hơn, tạo `SSLContext` riêng từ keystore/truststore và gắn vào **HTTP client chỉ dành cho Vault**, thay vì đặt cấu hình toàn JVM.

Ví dụ tạo `VaultTemplate` với một request factory dùng HTTPS mặc định của Java:

```java
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

VaultEndpoint endpoint = new VaultEndpoint();
endpoint.setScheme("https");
endpoint.setHost("vault.example.internal");
endpoint.setPort(8200);

SimpleClientHttpRequestFactory requestFactory =
        new SimpleClientHttpRequestFactory();
requestFactory.setConnectTimeout(3_000);
requestFactory.setReadTimeout(10_000);

// Ví dụ: transport yêu cầu mTLS, còn Vault xác thực bằng token.
String token = System.getenv("VAULT_TOKEN");
if (token == null || token.isBlank()) {
    throw new IllegalStateException("VAULT_TOKEN chưa được cấp");
}
ClientAuthentication authentication = new TokenAuthentication(token);
VaultTemplate vaultTemplate =
        new VaultTemplate(endpoint, authentication, requestFactory);
```

Đoạn mã minh họa **Trường hợp A**: chứng thư client và private key được JSSE dùng trong TLS handshake; `TokenAuthentication` là cơ chế cung cấp Vault token riêng. Với hệ thống thật, token có thể do Kubernetes/AppRole login và session manager lấy/gia hạn thay vì truyền một token tĩnh từ môi trường.

Các điểm cần kiểm tra khi chạy:

- `SimpleClientHttpRequestFactory` mặc định dùng cơ chế HTTPS của Java; JVM properties ở trên áp dụng khi request factory/client không tự thay `SSLContext`.
- HTTP client có SSL context riêng (ví dụ Apache HttpClient tùy chỉnh) **không nhất thiết** đọc các properties trên.
- Nếu keyStore có nhiều private-key entry, Java có thể cần cấu hình **key selection/alias** rõ ràng bằng client TLS phù hợp.
- Truststore luôn cần xác minh **hostname/SAN** của Vault; keystore client không thay thế yêu cầu đó.
- Tác vụ login, token renewal hay lease renewal có thể sử dụng HTTP client khác với `VaultTemplate` tự tạo; cần kiểm tra tất cả đường gọi thực tế.

## 7. Spring Cloud Vault và certificate authentication

Nếu dự án dùng **Spring Cloud Vault** với tích hợp SSL và auth tự động của phiên bản đang triển khai, có thể khai báo các tệp client/server certificate thông qua cấu hình tương ứng:

```yaml
spring:
  cloud:
    vault:
      uri: "https://vault.example.internal:8200"
      ssl:
        key-store: "file:/etc/vault/tls/vault-client.p12"
        key-store-password: "${VAULT_CLIENT_KEYSTORE_PASSWORD}"
        trust-store: "file:/etc/vault/tls/vault-truststore.p12"
        trust-store-password: "${VAULT_TRUSTSTORE_PASSWORD}"
```

Đây là **cấu hình TLS client**: keystore cung cấp danh tính client khi TLS server yêu cầu, còn truststore để xác minh server. Nó **không bắt buộc** sử dụng Vault certificate authentication; cơ chế login có thể là Kubernetes, AppRole hoặc lựa chọn khác phù hợp với ứng dụng.

Khi Vault được cấu hình để **đăng nhập bằng chứng thư client** (Trường hợp B), Spring Cloud Vault ở các phiên bản hỗ trợ có thể sử dụng:

```yaml
spring:
  cloud:
    vault:
      authentication: CERT
      uri: "https://vault.example.internal:8200"
      ssl:
        key-store: "file:/etc/vault/tls/vault-client.p12"
        key-store-password: "${VAULT_CLIENT_KEYSTORE_PASSWORD}"
        trust-store: "file:/etc/vault/tls/vault-truststore.p12"
        trust-store-password: "${VAULT_TRUSTSTORE_PASSWORD}"
```

`authentication: CERT` chỉ có thể hoạt động nếu **Vault cert auth method đã được bật và cấu hình** cho danh tính client. Nếu auth method được mount ở đường dẫn khác mặc định, phải khai báo đường dẫn authentication tương ứng theo **thuộc tính được hỗ trợ bởi phiên bản Spring Cloud Vault**.

Đặc biệt:

- `spring.cloud.vault.ssl.*` là cấu hình **Spring Cloud Vault**, không tự có tác dụng với ứng dụng chỉ thêm `spring-vault-core`.
- Chứng thư client chỉ được trình khi TLS peer yêu cầu và transport thực sự nhận được cấu hình keystore.
- Việc import cấu hình bằng `spring.config.import: "vault://"` (nếu dùng) là cơ chế Config Data; nó không phải scheme TLS và không thay cho `https://` trong `uri`.
- Mật khẩu và private key phải được bảo vệ bằng hệ thống quản lý bí mật; không commit tệp PKCS#12 chứa private key vào Git.

## 8. Phía Vault hoặc gateway phải cấu hình điều gì?

### 8.1. Vault listener nhận client certificate

Một TLS listener của Vault có thể được cấu hình để yêu cầu và xác minh client certificate. Ví dụ HCL **minh họa phía server**:

```hcl
listener "tcp" {
  address                        = "0.0.0.0:8200"
  tls_cert_file                  = "/etc/vault/tls/server-fullchain.pem"
  tls_key_file                   = "/etc/vault/tls/server-key.pem"
  tls_client_ca_file             = "/etc/vault/tls/trusted-client-ca.pem"
  tls_require_and_verify_client_cert = "true"
}
```

Trong đó:

- `tls_cert_file`/`tls_key_file`: danh tính **server** để Java xác minh qua HTTPS.
- `tls_client_ca_file`: CA mà listener sử dụng để xác minh chứng thư **client**.
- `tls_require_and_verify_client_cert`: bật yêu cầu xác minh client certificate tại lớp TLS khi triển khai muốn áp dụng mTLS bắt buộc.

Ví dụ này chỉ nói về **lớp transport**. Cấu hình Vault certificate authentication và policy nằm ở cơ chế auth riêng; listener xác minh chứng thư không tự cấp token có quyền truy cập bí mật. Cần kiểm tra chính xác tùy chọn listener và chính sách đang áp dụng trên **phiên bản Vault thực tế** trước khi triển khai.

### 8.2. Mô hình có reverse proxy/ingress

```text
Java ── mTLS ──► Gateway ── TLS/HTTP riêng ──► Vault
      client cert được          Vault có thể KHÔNG nhìn thấy
      gateway xác minh          TLS client cert của Java
```

Nếu gateway **kết thúc TLS**, phía gateway là nơi nhận và kiểm tra chứng thư client của Java. Vault backend thường không nhìn thấy chứng thư TLS nguyên bản của Java. Do đó:

- Nếu mTLS chỉ bảo vệ **điểm vào**, gateway có thể cưỡng chế client certificate, còn ứng dụng tiếp tục dùng Kubernetes/AppRole/token để login Vault.
- Nếu Vault **cert auth** phải xác minh chứng thư client, cần một kiến trúc bảo toàn ngữ cảnh chứng thư theo cách **được Vault hỗ trợ và tin cậy**, hoặc TLS passthrough đến Vault. Đừng giả định gắn một HTTP header tự do chứa chứng thư là đủ an toàn hoặc được Vault tự động chấp nhận.
- Nếu gateway kết nối HTTPS tới Vault, gateway cũng phải xác minh certificate/SAN của Vault backend theo cấu hình riêng.

## 9. Lỗi thường gặp và cách phân biệt

| Biểu hiện | Khả năng cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `PKIX path building failed` ở Java | Java không tin CA ký chứng thư **server** hoặc chain server thiếu intermediate. | Kiểm tra truststore Java, CA của endpoint HTTPS và chain phía server. |
| `No subject alternative ... matching` | Host trong URI Java không khớp SAN của chứng thư server. | Sửa hostname hoặc cấp đúng chứng thư server; không tắt hostname verification. |
| TLS `certificate_required` / `bad_certificate` | Server yêu cầu client certificate nhưng client thiếu, không dùng được hoặc certificate bị từ chối. | Xem keystore client, alias, private key, chain, EKU và CA được server chấp nhận. |
| TLS `unknown_ca` từ phía server | Server/gateway không tin CA đã cấp chứng thư client. | Kiểm tra `tls_client_ca_file` hoặc cấu hình trust client của gateway. |
| Không chọn được client certificate | Keystore chỉ có `trustedCertEntry`, alias sai hoặc thuật toán không phù hợp. | Xác minh `PrivateKeyEntry`, chain, key và cấu hình key selection. |
| mTLS thành công nhưng Vault `403` | Thiếu token, token hết hạn, policy hoặc namespace không đúng. | Kiểm tra Vault authentication/policy, không thay keystore để sửa lỗi 403. |
| Vault cert login thất bại | Auth method chưa bật/mount sai hoặc chứng thư không khớp cấu hình cert auth. | Kiểm tra auth mount, ràng buộc identity và chứng thư client được Vault nhìn thấy. |
| Java lỗi nhưng `curl` hoạt động | `curl` và Java dùng các kho CA/certificate, key selection khác nhau. | Kiểm tra cấu hình SSL context của HTTP client Java thực tế. |
| Chỉ một số replica lỗi sau khi đổi cert | Truststore/keystore hoặc SSL context chưa được cập nhật đồng bộ. | Xác minh rollout, chứng thư nạp trong từng Pod, pool/handshake mới. |

Một lỗi TLS xuất hiện **trước** khi gửi API Vault khác với response HTTP `401/403/404` được Vault trả về sau khi HTTPS đã thành công. Khi gỡ lỗi, ưu tiên giữ **nguyên nhân gốc** của exception và thông tin endpoint, nhưng không log token, private key, password hoặc response secrets.

## 10. Kiểm tra client certificate bằng công cụ

### 10.1. Xem chứng thư, không xuất private key

Nếu có tệp PEM chứng thư client:

```bash
openssl x509 -in client.crt -noout -subject -issuer -dates -ext extendedKeyUsage -fingerprint -sha256
```

Nếu đang dùng PKCS#12, dùng `keytool -list -v` như mục 5.2 để xem alias, loại entry và chain. Xác minh fingerprint/cấp phát với bên quản lý danh tính; không dựa vào tên tệp để suy ra chứng thư thuộc workload nào.

### 10.2. Thử mTLS với endpoint Vault

Khi có certificate và private key riêng biệt ở môi trường thử nghiệm, có thể kiểm tra kết nối bằng:

```bash
curl --verbose \
  --cacert vault-server-root-ca.pem \
  --cert client.crt \
  --key client-key.pem \
  "https://vault.example.internal:8200/v1/sys/health"
```

`--cacert` dùng để **tin server**, còn `--cert`/`--key` dùng để **chứng minh danh tính client**. `/v1/sys/health` có thể trả mã khác `200` tùy node standby/sealed/uninitialized; cần phân biệt trạng thái Vault với lỗi TLS. Lệnh `curl` thành công **không chứng minh** `VaultTemplate` đã nạp đúng keystore/truststore và chọn đúng alias.

Một kiểm tra sâu hơn với OpenSSL:

```bash
openssl s_client \
  -connect vault.example.internal:8200 \
  -servername vault.example.internal \
  -verify_hostname vault.example.internal \
  -CAfile vault-server-root-ca.pem \
  -cert client.crt \
  -key client-key.pem \
  -verify_return_error
```

Lệnh này xác minh chuỗi server và hostname theo cơ chế OpenSSL, đồng thời cung cấp client certificate khi được yêu cầu. Việc phía server **chấp nhận danh tính client và cấp quyền Vault** còn phải kiểm tra riêng. Quản lý file private key với quyền truy cập hạn chế và tránh gửi log lệnh chứa thông tin nhạy cảm ra bên ngoài.

### 10.3. Xác minh trong chính ứng dụng Java

Trong môi trường kiểm thử có mTLS thực, gọi cùng endpoint bằng chính `VaultTemplate`/HTTP client của ứng dụng. Có thể bật tạm debug của JSSE:

```text
-Djavax.net.debug=ssl,handshake,keymanager,trustmanager
```

Debug giúp xem quá trình chọn client certificate và xác minh chuỗi tin cậy. Log handshake có thể dài và chứa metadata hệ thống, nên chỉ dùng tạm trong môi trường được kiểm soát; không bật tràn lan trong production.

Kiểm thử tích hợp nên có các trường hợp:

1. **Không cung cấp client certificate** khi listener bắt buộc mTLS → TLS bị từ chối.
2. **Certificate đúng CA, đúng mục đích và còn hạn** → TLS handshake hoàn tất.
3. **Private key không khớp hoặc keystore thiếu `PrivateKeyEntry`** → client không xác thực thành công.
4. **Certificate đã hết hạn/CA không tin cậy** → listener/gateway từ chối client.
5. **TLS thành công nhưng policy Vault không đủ** → HTTP authorization thất bại; phân loại đúng.
6. **Dùng Vault cert auth** → login tạo token chỉ khi chứng thư và ràng buộc danh tính thỏa điều kiện.
7. **Xoay chứng thư client** → request và token/lease renewal vẫn hoạt động theo thiết kế sau khi HTTP client nạp cấu hình mới.

## 11. Xoay chứng thư client, bảo vệ khóa và vận hành

Keystore chứa **private key** nên cần kiểm soát chặt hơn truststore chỉ chứa CA:

- Phân phối bằng cơ chế quản lý secret/volume bảo mật, hạn chế quyền đọc ở runtime và hạn chế bản sao.
- Không commit `.p12`, private-key PEM hoặc mật khẩu keystore vào repository; cân nhắc key không xuất khẩu hoặc cơ chế lưu khóa chuyên dụng khi môi trường yêu cầu.
- Cấp chứng thư cho từng workload với danh tính, EKU và quyền tối thiểu; tránh chia sẻ cùng một private key giữa các dịch vụ.
- Theo dõi ngày hết hạn chứng thư và rủi ro thu hồi, chuẩn bị kế hoạch thay trước thời điểm expiry.
- Giữ giai đoạn chuyển tiếp CA/certificate khi phù hợp, đồng bộ server trust và các client instance trước khi thu hồi certificate cũ.

**Thay tệp keystore trên disk chưa chắc làm HTTP client Java nạp private key mới.** Nhiều `SSLContext` và HTTP connection pool giữ key material trong bộ nhớ; một kết nối TLS đang mở cũng có thể tiếp tục được dùng lại. Cần kiểm tra khả năng reload được hỗ trợ, hoặc tái tạo HTTP client/khởi động lại ứng dụng theo rollout có kiểm soát để chứng thư mới được dùng trong handshake.

Khi sử dụng Vault certificate auth, kế hoạch xoay còn phải xét **cấu hình cert auth** và các Vault token đã cấp. Đừng nhầm một token còn TTL với việc chứng thư sắp hết hạn: TLS handshake mới có thể thất bại dù token đã được cấp trước đó vẫn còn hợp lệ.

## 12. Tình huống tự luyện

**Tình huống A — Keystore chỉ có CA:** Java đã có `vault-truststore.p12` nhưng Vault listener yêu cầu mTLS và báo `certificate_required`. Nguyên nhân là Java chưa có chứng thư client kèm private key để xuất trình; nhập thêm CA vào truststore không giải quyết việc này.

**Tình huống B — Có PKCS#12, Vault vẫn trả 403:** TLS handshake hoàn tất vì gateway tin client certificate, nhưng Vault từ chối đọc KV. Cần kiểm tra cơ chế login, Vault token, policy và đúng path KV v1/v2; đây là lỗi quyền ở tầng Vault chứ không phải dấu hiệu thiếu private key.

**Tình huống C — `authentication: CERT` phía sau ingress:** Gateway kết thúc mTLS và không chuyển nguyên ngữ cảnh certificate cho Vault. Vault cert auth có thể không nhận được danh tính cần dùng để login. Cần thiết kế TLS passthrough hoặc kiến trúc auth được Vault hỗ trợ; nếu mTLS chỉ ở gateway, chọn một cơ chế Vault auth độc lập phù hợp.

**Tình huống D — Xoay client CA không đồng bộ:** Một số replica dùng chứng thư do CA mới ký, nhưng Vault listener chỉ tin CA cũ. Các replica mới bị từ chối handshake. Phải cập nhật cấu hình CA tin cậy phía listener/gateway, bảo đảm giai đoạn chồng lấn theo chính sách rồi mới chuyển toàn bộ client.

### Ghi nhớ

Với Spring Vault, **truststore xác minh Vault**, còn **keystore chứa client certificate và private key để Java chứng minh danh tính khi server yêu cầu mTLS**. Chỉ sử dụng Vault certificate authentication nếu Vault đã hỗ trợ, nhận được danh tính certificate cần thiết và có mapping sang policy phù hợp. Hãy kiểm tra chứng thư có `PrivateKeyEntry`, chain, mục đích `clientAuth`, thời hạn, quyền truy cập private key và khả năng reload khi xoay chứng thư; sau đó kiểm thử riêng TLS handshake, Vault login và quyền KV/token/lease/Transit/PKI.
