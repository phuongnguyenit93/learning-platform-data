# Keystore chứa chứng thư cùng khóa riêng của client

Khi ứng dụng Java kết nối HashiCorp Vault qua HTTPS, **keystore của client** có thể chứa cặp khóa riêng và chứng thư X.509 để chứng minh danh tính ứng dụng trong quá trình bắt tay TLS. Đây là thành phần thiết yếu nếu ứng dụng dùng **TLS certificate authentication** (auth method `cert`) để nhận Vault token. Spring Vault cung cấp `VaultTemplate`, `ClientCertificateAuthentication` và cấu hình SSL để kết nối với Vault trong trường hợp này.

Bài thuộc chương **Chứng thư và tài khoản** của module `SPRING_VAULT`. Mục tiêu là hiểu keystore chứa những gì, tạo và kiểm tra được keystore, phân biệt nó với truststore, cấu hình đúng cho Spring Cloud Vault hoặc Spring Vault Core, rồi vận hành an toàn khi chứng thư hết hạn hoặc được thay mới. Sau khi được xác thực, Vault token vẫn phải tuân thủ **policy phân quyền** cho KV secrets, vòng đời token/lease, Transit encryption và PKI.

## 1. Keystore chứa những thành phần nào?

Một chứng thư X.509 là dữ liệu **công khai** xác nhận chủ thể (subject), bên cấp (issuer), khóa công khai, thời hạn sử dụng và các extension như Key Usage/Extended Key Usage. Một **private key** tương ứng nằm trong vùng lưu trữ có bảo vệ của client và được dùng để thực hiện thao tác mật mã chứng minh quyền sở hữu khóa trong TLS handshake.

Keystore là cấu trúc lưu trữ có thể chứa một hoặc nhiều entry:

| Entry trong Java KeyStore | Nội dung | Ứng dụng trong Spring Vault |
| --- | --- | --- |
| `PrivateKeyEntry` | **Private key** và chuỗi chứng thư: leaf certificate + intermediate(s), đôi khi kèm root | Cung cấp danh tính TLS của ứng dụng khi Vault yêu cầu client certificate |
| `trustedCertEntry` | Chứng thư được tin cậy, **không chứa private key** | Thường dùng trong truststore để tin cậy CA cấp chứng thư server |
| Alias | Tên để chọn entry, ví dụ `vault-client` | Giúp KeyManager chọn cặp khóa/chứng thư phù hợp |
| Store password | Mật khẩu mở/bảo vệ keystore | Không nên ghi cố định trong Git hoặc container image |
| Key password | Mật khẩu bảo vệ private key entry nếu định dạng/provider hỗ trợ tách riêng | Có thể cần cấu hình riêng với store password |

**Điểm phân biệt cốt lõi:** chỉ có file `client.crt` hoặc `ca.crt` thì chưa đủ để client chứng minh danh tính bằng mTLS. Cần cả **private key khớp với public key trong chứng thư leaf** và một TLS client thực sự tải được entry này. Ngược lại, truststore dùng để kiểm tra **chứng thư server Vault**, nên chỉ cần chứng thư CA/public certificate đáng tin.

```mermaid
flowchart LR
    A["client.p12<br/>PrivateKeyEntry: vault-client<br/>Private key + client certificate chain"] --> B["TLS client KeyManager"]
    C["truststore.p12<br/>trustedCertEntry: vault-server-ca"] --> D["TLS client TrustManager"]
    B --> E["HTTPS tới Vault"]
    D --> E
    E --> F["POST /v1/auth/cert/login"]
    F --> G["Vault token"]
    G --> H["VaultTemplate: KV / Transit / PKI"]
```

`client.p12` và `truststore.p12` có thể là hai file độc lập. Tách riêng giúp phân quyền file và thay đổi chuỗi CA/chứng thư client độc lập, dù Java KeyStore về mặt kỹ thuật có thể chứa cả private key lẫn trusted certificates trong cùng một file.

## 2. Các định dạng thường gặp: PKCS#12, JKS và PEM

| Định dạng | Phần mở rộng thường gặp | Ghi chú |
| --- | --- | --- |
| **PKCS#12** | `.p12`, `.pfx` | Lựa chọn phù hợp cho ứng dụng Java hiện đại; có thể đóng gói private key, leaf cert, certificate chain |
| **JKS** | `.jks` | Định dạng keystore Java truyền thống; vẫn dùng được nếu cấu hình và JDK hỗ trợ |
| **PEM** | `.pem`, `.crt`, `.key` | Biểu diễn certificate/private key bằng khối văn bản; có thể import sang PKCS#12 hoặc dùng trực tiếp nếu phiên bản/client library hỗ trợ |

Một file PEM có khối `-----BEGIN CERTIFICATE-----` chỉ chứa certificate. File private key có header như `-----BEGIN PRIVATE KEY-----` hoặc `-----BEGIN ENCRYPTED PRIVATE KEY-----`. Không đặt private key chưa mã hóa trong kho nguồn và không xuất nội dung file khóa ra log.

Với keystore dùng cho certificate authentication, kiểm tra ít nhất: **có PrivateKeyEntry**, chuỗi chứng thư đúng issuer, chứng thư leaf còn hạn, khóa riêng khớp, Extended Key Usage thích hợp (thường là `TLS Web Client Authentication`), và alias/key password được cấu hình đúng. Nếu entry chỉ có `trustedCertEntry`, TLS client không thể trình bày cặp key/certificate đó như một danh tính riêng.

## 3. Tạo `client.p12` từ chứng thư và khóa đã cấp

Giả sử bộ phận PKI cung cấp:

- `client.crt`: chứng thư ứng dụng, có `Extended Key Usage: clientAuth`;
- `client.key`: khóa riêng của đúng cặp khóa với `client.crt`;
- `intermediate-ca.pem`: một hoặc nhiều chứng thư CA trung gian để hoàn thiện chain;
- `vault-server-ca.pem`: CA tin cậy để xác thực HTTPS server Vault (có thể khác CA cấp certificate cho client).

Chỉ chạy các lệnh sau với **tài liệu/khóa thử nghiệm** hoặc khóa đã được cấp phép sử dụng, ở thư mục có quyền truy cập hạn chế. `openssl` sẽ hỏi mật khẩu xuất file PKCS#12:

```bash
openssl pkcs12 -export \
  -inkey client.key \
  -in client.crt \
  -certfile intermediate-ca.pem \
  -name vault-client \
  -out client.p12
```

Ví dụ sử dụng `keytool` xem loại entry:

```bash
keytool -list -v \
  -keystore client.p12 \
  -storetype PKCS12 \
  -alias vault-client
```

Kết quả mong muốn có:

```text
Alias name: vault-client
Entry type: PrivateKeyEntry
Certificate chain length: 2
Owner: CN=orders-api
Issuer: CN=Example Issuing CA
...
ExtendedKeyUsages: clientAuth
```

Đây là **kết quả minh họa**: số phần tử trong chain và nội dung extension thực tế tùy chứng thư. Nếu `keytool` báo `trustedCertEntry`, bạn có thể đã import mỗi `client.crt` mà chưa nhập private key. Nếu bị `UnrecoverableKeyException` hoặc `bad decrypt`, kiểm tra store/key password và định dạng đầu vào trước khi suy đoán server Vault gặp lỗi.

Có thể xác minh chứng thư và chuỗi CA mà không in private key:

```bash
openssl x509 -in client.crt -noout -subject -issuer -dates -ext extendedKeyUsage
openssl verify -CAfile root-ca.pem -untrusted intermediate-ca.pem client.crt
```

`root-ca.pem` ở lệnh thứ hai phải là root thực sự phát hành chuỗi client; không tự thay bằng `vault-server-ca.pem` nếu đây là hai PKI khác nhau. Khả năng xác minh chain ở máy phát triển cũng chưa đồng nghĩa với việc **Vault cert auth role** đã tin cậy CA đó.

### Tạo truststore cho Vault server

Để Java xác thực chứng thư HTTPS của Vault khi CA không có trong truststore mặc định của JDK:

```bash
keytool -importcert \
  -alias vault-server-ca \
  -file vault-server-ca.pem \
  -keystore truststore.p12 \
  -storetype PKCS12
```

Lệnh `keytool` hỏi mật khẩu và xác nhận tin cậy certificate. Chỉ chấp nhận CA đã được quản trị viên xác minh bằng kênh đáng tin cậy. Truststore không yêu cầu private key. Nếu Vault server sử dụng certificate từ CA công khai đã tin cậy theo JDK, có thể không cần truststore riêng.

## 4. Luồng certificate authentication với Vault

Hai việc diễn ra ở **hai lớp**:

1. **TLS transport:** Java trình bày chứng thư client và chứng minh có private key; đồng thời Java xác minh chứng thư HTTPS của Vault bằng truststore.
2. **Vault auth method `cert`:** ứng dụng gọi `POST /v1/auth/cert/login`; Vault đối chiếu chứng thư client với chứng thư/CA, điều kiện subject/SAN/extension và role đã cấu hình, rồi cấp **Vault client token** nếu hợp lệ.

```mermaid
sequenceDiagram
    participant App as Spring Vault app
    participant TLS as Vault TLS listener
    participant Auth as Vault cert auth backend
    participant KV as Vault KV v2
    App->>TLS: TLS handshake: trình bày client certificate
    TLS-->>App: TLS session thiết lập nếu chứng thư hợp lệ ở tầng transport
    App->>Auth: POST /v1/auth/cert/login (name tùy chọn)
    Auth->>Auth: Kiểm tra certificate role, CA/leaf, subject/SAN
    Auth-->>App: auth.client_token + policies + TTL
    App->>KV: GET /v1/secret/data/payments, X-Vault-Token
    KV-->>App: secret nếu policy cho phép
```

Đối với auth `cert`, client cần dùng HTTPS và Vault listener phải cho phép nhận chứng thư client (`tls_disable=false`, `tls_disable_client_certs=false`). TLS listener có thể được cấu hình **chỉ yêu cầu client certificate khi có**; không phải mọi cấu hình đều bắt buộc client certificate cho tất cả endpoint. Đừng đặt `tls_require_and_verify_client_cert=true` một cách máy móc nếu các ứng dụng khác còn dùng những auth method không có certificate.

Vault phải được cấu hình role của `cert` backend riêng; việc Java có keystore và kết nối TLS được không tự động cấp quyền đọc secrets.

Ví dụ minh họa của người quản trị Vault trong môi trường thử nghiệm:

```bash
vault auth enable cert

# Cách 1: tin cậy một chứng thư client cụ thể
vault write auth/cert/certs/orders-api \
  display_name=orders-api \
  policies=orders-read \
  certificate=@client.crt \
  ttl=1h
```

Nếu muốn cấp quyền cho **chuỗi certificate do một CA ký**, cấu hình role bằng CA phù hợp và ràng buộc thuộc tính client certificate (ví dụ `allowed_common_names`, `allowed_dns_sans`, `allowed_uri_sans`) theo danh tính workload. Tránh tin cậy mọi client certificate được cấp bởi một CA dùng chung nếu không có thêm ràng buộc.

Ví dụ Vault policy tối thiểu cho một secret KV v2:

```hcl
path "secret/data/payments" {
  capabilities = ["read"]
}
```

Chú ý `auth/cert/certs/orders-api` là **tên role/certificate** dùng để đăng nhập; `orders-read` là **policy** được gắn vào Vault token; `vault-client` là **alias trong PKCS#12**. Đây là ba tên thuộc ba tầng khác nhau, không bắt buộc giống nhau.

## 5. Cấu hình Spring Cloud Vault với PKCS#12

Ví dụ cho Spring Boot dùng Spring Cloud Vault phiên bản có hỗ trợ `spring.config.import` và thuộc tính `spring.cloud.vault.ssl.*`:

```yaml
spring:
  config:
    import: vault://
  cloud:
    vault:
      uri: https://vault.internal.example:8200
      authentication: CERT
      ssl:
        key-store: file:/run/secrets/vault/client.p12
        key-store-type: PKCS12
        key-store-password: ${VAULT_KEYSTORE_PASSWORD}
        trust-store: file:/run/secrets/vault/truststore.p12
        trust-store-type: PKCS12
        trust-store-password: ${VAULT_TRUSTSTORE_PASSWORD}
        cert-auth-path: cert
```

Ở đây `authentication: CERT` chọn Vault TLS certificate auth; `key-store` tải private key cùng certificate chain; `trust-store` xác minh HTTPS server Vault; `cert-auth-path: cert` tương ứng mount `auth/cert` trên Vault server. Đường dẫn `file:` giả định certificate được mount qua secret volume. `VAULT_KEYSTORE_PASSWORD` và `VAULT_TRUSTSTORE_PASSWORD` phải được cấp an toàn tại runtime, tránh đưa vào Git, image layer hoặc log.

**Tùy phiên bản Spring Cloud Vault**, `spring.cloud.vault.ssl.role` có thể được dùng để chọn cert role; property này được công bố từ nhánh **Spring Cloud Vault 5.0**. Không thêm property chỉ vì thấy ở tài liệu bản mới khi dự án đang dùng bản cũ. Nếu không chỉ định role, Vault cert auth có thể thử khớp certificate với các role đã tin cậy theo quy tắc của backend. Để cấu hình role chính xác ở các nhánh cũ, đối chiếu phiên bản library hoặc sử dụng cấu hình `ClientCertificateAuthentication` của Spring Vault Core.

Một số HTTP client implementation hỗ trợ cấu hình SSL của Spring Cloud Vault theo cách khác nhau; tài liệu Spring Vault khuyến nghị sử dụng Apache HttpComponents tương ứng với phiên bản client để áp dụng `SslConfiguration`. Nếu `key-store` có cấu hình nhưng TLS handshake vẫn không gửi certificate, hãy xác định **HTTP client thực tế và SSL factory** đang được sử dụng, không chỉ kiểm tra property được bind.

Nếu ứng dụng cần chứng thư client cho mTLS nhưng **đăng nhập Vault qua AppRole/Kubernetes/AWS**, nó vẫn có thể cấu hình keystore ở tầng transport; khi đó `authentication` là phương thức thực tế khác `CERT`. Keystore và Vault auth method không phải một khái niệm.

## 6. Sử dụng Spring Vault Core trực tiếp

Với ứng dụng tự xây `VaultTemplate`, điểm bắt đầu là `org.springframework.vault.support.SslConfiguration`. Ví dụ phương thức tạo cấu hình SSL:

```java
import org.springframework.core.io.FileSystemResource;
import org.springframework.vault.support.SslConfiguration;

SslConfiguration ssl = SslConfiguration.create(
    new FileSystemResource("/run/secrets/vault/client.p12"),
    System.getenv("VAULT_KEYSTORE_PASSWORD").toCharArray(),
    new FileSystemResource("/run/secrets/vault/truststore.p12"),
    System.getenv("VAULT_TRUSTSTORE_PASSWORD").toCharArray()
);
```

Đoạn trên **tạo cấu hình SSL**, chưa tự động cấu hình `VaultTemplate`. Ứng dụng phải dùng một `ClientHttpRequestFactory`/HTTP client hỗ trợ keystore và truststore đó khi tạo client kết nối Vault. Cách tạo factory phụ thuộc Spring Vault, Spring Framework và HTTP client trên classpath; đối chiếu JavaDoc `ClientHttpRequestFactoryFactory` hoặc cơ chế SSL tương ứng với bản đang dùng. Thiếu bước này thì việc khởi tạo `SslConfiguration` không làm certificate xuất hiện trong TLS handshake.

Khi cần chỉ định **key password** hoặc **alias**:

```java
import org.springframework.vault.support.SslConfiguration;
import org.springframework.vault.support.SslConfiguration.KeyConfiguration;
import org.springframework.core.io.FileSystemResource;

SslConfiguration ssl = SslConfiguration.forKeyStore(
    new FileSystemResource("/run/secrets/vault/client.p12"),
    System.getenv("VAULT_KEYSTORE_PASSWORD").toCharArray(),
    KeyConfiguration.of(
        System.getenv("VAULT_KEY_PASSWORD").toCharArray(),
        "vault-client"
    )
);
```

Đây là cấu hình **chỉ cho keystore**, nên vẫn phải bổ sung truststore hoặc sử dụng default trust anchors phù hợp để xác minh Vault server. Tùy cấu hình thực tế, alias có thể quan trọng khi cùng file chứa nhiều `PrivateKeyEntry`.

Spring Vault Core cung cấp authentication client riêng:

```java
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.ClientCertificateAuthentication;
import org.springframework.vault.authentication.ClientCertificateAuthenticationOptions;

// Ví dụ trong lớp cấu hình kế thừa AbstractVaultConfiguration
@Override
public ClientAuthentication clientAuthentication() {
    ClientCertificateAuthenticationOptions options =
        ClientCertificateAuthenticationOptions.builder()
            .path("cert")
            .role("orders-api")
            .build();

    return new ClientCertificateAuthentication(options, vaultClient());
}
```

Mẫu `vaultClient()` phù hợp với **Spring Vault 4.1+**; các nhánh cũ có constructor dựa trên `RestOperations` hoặc `RestClient`. Quan trọng hơn tên constructor: client dùng để login phải **được cấu hình SSL keystore trước đó**, và `SessionManager` phải dùng `ClientAuthentication` này để lấy/duy trì Vault token cho `VaultTemplate`.

## 7. Kiểm tra nội dung keystore ngay trong Java

Không cần tạo kết nối tới Vault để kiểm tra keystore có chứa **private key entry** đúng alias hay không:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.X509Certificate;

public class ClientKeystoreInspector {
    public static void main(String[] args) throws Exception {
        char[] storePassword =
            System.getenv("VAULT_KEYSTORE_PASSWORD").toCharArray();
        char[] keyPassword =
            System.getenv("VAULT_KEY_PASSWORD").toCharArray();

        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(
                Path.of("/run/secrets/vault/client.p12"))) {
            store.load(in, storePassword);
        }

        String alias = "vault-client";
        KeyStore.Entry entry = store.getEntry(
            alias, new KeyStore.PasswordProtection(keyPassword));

        if (!(entry instanceof KeyStore.PrivateKeyEntry privateKeyEntry)) {
            throw new IllegalStateException(
                "Alias does not contain a client private key");
        }

        X509Certificate certificate =
            (X509Certificate) privateKeyEntry.getCertificate();
        certificate.checkValidity();

        // Chỉ hiển thị metadata công khai, tuyệt đối không in private key.
        System.out.println("Subject: " + certificate.getSubjectX500Principal());
        System.out.println("Issuer: " + certificate.getIssuerX500Principal());
        System.out.println("Chain length: "
                + privateKeyEntry.getCertificateChain().length);
    }
}
```

Ví dụ yêu cầu **Java 17+** và hai biến môi trường có giá trị. Với file PKCS#12 thông thường, key password có thể trùng store password; nếu không có mật khẩu riêng, đặt `VAULT_KEY_PASSWORD` bằng mật khẩu store qua secret manager. `certificate.checkValidity()` chỉ kiểm tra ngày hiệu lực, **không xác thực CA chain, hostname của Vault hay Vault auth role**. Những kiểm tra đó phải diễn ra ở TLS/trust và Vault integration test.

## 8. Liên hệ với Vault PKI và vòng đời chứng thư

Vault PKI secrets engine có thể **cấp** chứng thư client X.509 khi role PKI cho phép. Có hai luồng quản lý private key:

| Cách cấp | Private key được tạo ở đâu? | Hệ quả vận hành |
| --- | --- | --- |
| Ứng dụng hoặc hệ thống provisioning tạo CSR rồi gửi tới Vault PKI để ký | Phía client/provisioner | Khóa riêng không cần rời nơi phát sinh, kiểm soát bí mật tốt hơn |
| Gọi API issue của Vault PKI để tạo key và certificate | Vault tạo key và trả khóa riêng trong response nếu dùng kiểu cấp này | Cần đường truyền và nơi lưu trữ an toàn; không log payload chứa private key |

Trong cả hai trường hợp, trước khi dùng **certificate authentication**, cần có `PrivateKeyEntry` hợp lệ trong keystore và Vault cert auth backend tin cậy leaf/CA tương ứng. **PKI issue role** dùng để ký certificate và **cert auth role** dùng để đăng nhập Vault là hai cấu hình khác nhau.

Một certificate có thể hết hạn trong khi Vault token vừa được cấp vẫn đang còn TTL. Ngược lại, Vault token có thể hết hạn và cần đăng nhập lại khi certificate vẫn còn hạn. Ngoài ra:

- **Keystore rotation:** cập nhật `client.p12` và cấu hình có liên quan; phải chắc chắn HTTP client/SSLContext nhận chứng thư mới. Chỉ thay file dưới mount volume không đảm bảo mọi client Java tự reload.
- **Cert auth role rotation:** kiểm tra CA trust, issuer, subject/SAN, role binding và ACL trước khi chuyển sang certificate mới; có kế hoạch chồng lấn thời hạn hợp lệ để tránh downtime.
- **Thu hồi chứng thư:** cập nhật nguồn revocation phù hợp với Vault cert auth và quy trình PKI; khi cần giảm thiểu truy cập ngay, thu hồi các Vault token còn hiệu lực theo quy trình vận hành.
- **Token/lease lifecycle:** dùng session/token lifecycle của Spring Vault để xử lý TTL/renewal; luồng này độc lập với hết hạn X.509.
- **Transit và KV/PKI:** certificate chỉ là một phương thức nhận Vault token; token policy tiếp tục quyết định quyền `read`, `update`, `create` hoặc `delete` trên từng endpoint.

Đối với tổ chức có chứng thư cấp bởi nhiều CA, hãy theo dõi nguồn phát hành, serial number, expiry date và kế hoạch thay CA trung gian. Không dùng một client keystore cho tất cả ứng dụng nếu cần phân biệt workload và quyền truy cập.

## 9. Kiểm thử và xử lý lỗi thường gặp

### Ba cấp độ kiểm thử

| Cấp độ | Kiểm tra gì? | Công cụ/ý tưởng |
| --- | --- | --- |
| Kiểm tra tĩnh | PKCS#12 tồn tại, alias đúng, `PrivateKeyEntry`, certificate hợp lệ về thời gian | `keytool`, `openssl`, Java `KeyStore` |
| HTTP/TLS test | Client có trình bày cert, server chain được xác minh, SSLContext chọn đúng alias | HTTPS server thử nghiệm yêu cầu client certificate; WireMock/MockWebServer có TLS config |
| Vault integration test | `cert` auth thực sự cấp Vault token, policy cho phép/cấm đúng path, hoạt động với rotation | Vault test instance có TLS listener, cert auth mount và role; Spring Vault/`VaultTemplate` |

**Không thể xác minh việc trình bày private key chỉ bằng mock `ClientAuthentication.login()`**. Phần khó nằm ở TLS handshake, nên cần ít nhất một thử nghiệm HTTPS với server yêu cầu client cert hoặc Vault thử nghiệm có cấu hình TLS tương ứng.

Một bài integration test hợp lý gồm các bước:

1. Dùng CA thử nghiệm tạo leaf certificate có EKU `clientAuth`, đóng gói `client.p12` và tạo truststore với CA server thử nghiệm.
2. Khởi động Vault test với TLS listener cho phép client certificates và cert auth role gắn với đúng leaf/CA.
3. Kết nối qua HTTPS, đăng nhập bằng `ClientCertificateAuthentication`, nhận Vault token.
4. Kiểm tra `VaultTemplate` đọc được `secret/data/payments` theo policy và bị từ chối ở path khác.
5. Lặp lại với alias sai, keystore thiếu private key, certificate quá hạn, CA client không tin cậy và truststore server không đúng.
6. Dọn Vault role, token và toàn bộ chứng thư thử nghiệm sau bài test.

### Bảng khoanh vùng sự cố

| Hiện tượng | Nguyên nhân khả dĩ | Bước xác minh |
| --- | --- | --- |
| `UnrecoverableKeyException` / `keystore password was incorrect` | Store/key password sai, kiểu keystore sai, hỏng file | `keytool -list -storetype PKCS12`, kiểm tra alias/password |
| TLS `bad_certificate` hoặc `certificate_required` | Client không gửi certificate, thiếu private key entry, CA không hợp lệ hoặc TLS listener bắt buộc client cert | Kiểm tra `PrivateKeyEntry`, cert chain, KeyManager và listener |
| `PKIX path building failed` | Client không xác minh được chain **server Vault** | Truststore, server CA/hostname/certificate chain |
| `No subject alternative names matching` | Vault server certificate không khớp hostname trong URL | SAN của chứng thư server và `spring.cloud.vault.uri` |
| TLS thành công nhưng `POST /auth/cert/login` trả `403` | Vault cert role không khớp leaf/CA/subject/SAN hoặc auth path sai | Vault auth mount, role, allowed names, thời hạn certificate |
| Vault login OK nhưng KV đọc `403` | Vault token thiếu capability hoặc dùng nhầm KV v1/v2 path | Token policies, KV mount/path `secret/data/...` |
| Chứng thư mới đã mount nhưng app vẫn gửi chứng thư cũ | SSLContext/HTTP client chưa reload keystore | Chiến lược reload/restart và alias/cert fingerprint mới |

Trong giai đoạn điều tra, bật log đủ để biết **thời điểm handshake, alias được chọn, mã lỗi và Vault auth path**, nhưng không in mật khẩu, private key, session secret hoặc Vault token. Có thể dùng SSL debug có giới hạn trong môi trường test, tránh xuất trace đầy đủ ra hệ thống log production.

## 10. Bài thực hành

**Tình huống:** một service Java tên `orders-api` cần truy cập secret KV v2 `secret/data/payments` bằng Vault TLS certificate authentication. Nhóm PKI cung cấp `client.crt`, `client.key`, `intermediate-ca.pem` và CA của Vault server.

1. Tạo `client.p12` với alias `vault-client` và `truststore.p12` chứa CA của HTTPS server Vault; giải thích hai file khác nhau thế nào.
2. Dùng `keytool` xác nhận `PrivateKeyEntry` và chuỗi certificate; dùng `openssl` kiểm tra thời hạn, EKU và issuer.
3. Cấu hình Spring Cloud Vault với `authentication: CERT`, đường dẫn hai keystore, loại `PKCS12`, mật khẩu từ biến môi trường.
4. Cấu hình Vault cert auth role thử nghiệm `orders-api` cấp policy `orders-read`; xác minh đăng nhập `/v1/auth/cert/login` rồi đọc đúng secret.
5. Thử bỏ private key khỏi keystore, dùng sai truststore và cấp policy không đủ quyền; phân biệt lỗi TLS, lỗi cert auth và lỗi Vault policy.
6. Thay certificate client trước khi hết hạn; kiểm tra HTTP client trình bày certificate mới, chứng thư cũ bị thu hồi theo quy trình và Vault token được quản lý đúng TTL.

**Tiêu chí hoàn thành:** hiểu rõ `PrivateKeyEntry` và `trustedCertEntry`, tạo được PKCS#12 có khóa riêng cùng chứng thư client, cấu hình SSL và certificate authentication đúng tầng, bảo vệ bí mật, kiểm thử được cả thành công lẫn lỗi theo TLS/Vault auth/Vault policy.

## Tài liệu tham khảo

- Spring Vault — [Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html), mục TLS certificate authentication.
- Spring Vault — [HTTP Client Support và SSL Configuration](https://docs.spring.io/spring-vault/reference/vault/client-support.html).
- Spring Cloud Vault — [Authentication Methods](https://docs.spring.io/spring-cloud-vault/reference/authentication.html), mục TLS certificate authentication.
- Spring Cloud Vault — [Common Application Properties](https://docs.spring.io/spring-cloud-vault/reference/appendix.html).
- HashiCorp Vault — [TLS Certificates Auth Method](https://developer.hashicorp.com/vault/docs/auth/cert), và [Cert Auth HTTP API](https://developer.hashicorp.com/vault/api-docs/auth/cert).
