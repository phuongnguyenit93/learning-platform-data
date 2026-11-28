# Quản lý mật khẩu kho khóa và tách bí mật khỏi mã nguồn

## 1. Bài toán: SOAP đúng hợp đồng nhưng khóa và mật khẩu đang ở đâu?

Trong tích hợp SOAP doanh nghiệp, một dịch vụ **Spring Web Services (Spring-WS)** có thể cần nhiều loại bí mật cùng lúc: mật khẩu kho khóa PKCS#12, mật khẩu của private-key entry, tài khoản HTTP Basic, shared secret của WS-Security UsernameToken, thông tin truy cập secret manager và đôi khi PIN để sử dụng HSM.

Ví dụ ứng dụng gửi yêu cầu `CreateShipment` qua HTTPS với **mutual TLS (mTLS)**, đồng thời ký SOAP Body bằng **WS-Security XML Signature**. Dịch vụ đối tác phải tin certificate phía client ở tầng TLS và kiểm chữ ký message ở tầng SOAP. Một cấu hình đơn giản nhưng nguy hiểm là:

```java
// ANTI-PATTERN: minh họa cách KHÔNG triển khai production.
String storePassword = "real-password-in-source";
String keyPassword = "another-real-password";
```

Lỗi không chỉ là mật khẩu nằm trong Git. Nó có thể xuất hiện trong image/container layer, CI logs, lỗi exception, heap dump, terminal history hoặc cấu hình được copy giữa các môi trường. Đổi mật khẩu cũng đòi build/deploy code và có thể làm gián đoạn dịch vụ.

Giải pháp là **tách secret material khỏi source code và khỏi metadata công khai**, rồi xác định đúng nơi mỗi loại mật khẩu được sử dụng. Việc nạp secret cần đi qua một nguồn được quản lý, có quyền tối thiểu, rotation, audit và vòng đời rõ ràng.

Bài thuộc chương **Chứng chỉ và khóa** của module **SPRING_WEB_SERVICES**, đặt trong lộ trình phát triển SOAP **contract-first**, thiết kế XSD/WSDL, JAXB/OXM, xây dựng endpoint/client, xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích hệ thống doanh nghiệp.

### Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt **certificate**, public/private key, keystore, truststore và mật khẩu tương ứng.
2. Giải thích tại sao **store password**, **key-entry password**, **HTTP password**, **UsernameToken shared secret** và **HSM PIN** không thể dùng thay thế cho nhau.
3. Hiểu PKCS#12, JKS, PEM, PKCS#11 và các điểm khác nhau về lưu trữ/bảo vệ khóa.
4. Đọc kho khóa Java bằng `KeyStore.load(...)` với `char[]` được lấy từ nguồn được quản lý.
5. Cấu hình `KeyManagerFactory`, `TrustManagerFactory` và `SSLContext` mà không hardcode mật khẩu.
6. Tách cấu hình TLS/mTLS của `WebServiceTemplate` khỏi cấu hình ký/mã hóa SOAP bằng WSS4J.
7. Dùng `WSPasswordCallback` cho `SIGNATURE`/`DECRYPT` với alias và secret scope rõ.
8. Thiết kế secret reference, workload identity, rotation, cache và fail-closed behavior.
9. Nhận diện nguy cơ leak qua logs, môi trường chạy, image, commands và heap.
10. Lập kiểm thử keystore, mTLS, WS-Security, certificate renewal và interoperability.

## 2. Bản đồ thuật ngữ: vật liệu mật mã và nơi sử dụng

| Khái niệm | Bản chất | Có phải secret? | Dùng vào việc gì? |
| --- | --- | --- | --- |
| **Private key** | Khóa bí mật của cặp khóa bất đối xứng | **Có, rất nhạy cảm** | TLS client authentication, XML signing/decryption |
| Public key | Khóa công khai tương ứng | Không | Kiểm chữ ký, mã hóa cho người nhận |
| X.509 certificate | Public key kèm identity/issuer/validity và chữ ký CA | Bản thân chứng chỉ thường không bí mật | Xác minh chủ thể và chuỗi tin cậy |
| Keystore | Kho chứa key entries và/hoặc certificates | **Có thể chứa private key** | Bảo vệ và truy cập material cần dùng |
| Truststore | Kho certificates/CA anchors được tin | Thường không chứa private key; **cần bảo vệ tính toàn vẹn** | Xác minh certificate của peer |
| Store password | Password được `KeyStore.load(...)` sử dụng tùy định dạng/provider | Có | Mở/kiểm tra toàn vẹn kho |
| Key-entry password | Password bảo vệ một private-key entry | Có | Dùng `KeyManagerFactory` hoặc `KeyStore.getKey(...)` truy cập key |
| Alias | Tên định danh entry trong keystore | Thường không, nhưng vẫn là metadata | Chọn key/certificate đúng |
| HSM/KMS key handle | Reference đến key không xuất được | Handle không thay thế authorization | Ký/giải mã qua provider/service |
| HTTP Basic password | Password cho origin/gateway | Có | HTTP `Authorization` |
| UsernameToken shared secret | Secret của WS-Security UsernameToken | Có | Tạo/kiểm token theo profile |
| Vault access token | Credential để lấy secrets | Có | Gọi secret manager |

**Mật khẩu keystore không phải private key.** Một keystore có thể chứa private key được mã hóa bảo vệ bằng password. Biết password không đồng nghĩa có được key nếu không có file/store hay quyền truy cập provider. Ngược lại, có file chứa private key không đồng nghĩa mở được entry nếu thiếu password.

### 2.1. Những từ gần nhau nhưng khác mục đích

- **Keystore password** không luôn bằng **key-entry password**.
- **Truststore password** không phải “mật khẩu của CA”; nó được dùng theo định dạng/provider để đọc hoặc kiểm tra integrity của store.
- **Client certificate** không phải **client private key**.
- **mTLS signing operation** trong TLS handshake không giống **XML Signature** trên SOAP Body, dù có thể dùng cùng hệ PKI theo policy.
- **Certificate chain** không tự là một danh sách trust anchors; server/client vẫn phải kiểm CA, hostname/identity và các ràng buộc khác.

## 3. Keystore và truststore trong Java

`java.security.KeyStore` là abstraction lưu nhiều dạng entry. Một `KeyStore` có thể chứa:

- `PrivateKeyEntry`: private key kèm certificate chain.
- `TrustedCertificateEntry`: certificate được tin cậy.
- `SecretKeyEntry` trong một số keystore types/providers.

Tên “keystore” và “truststore” thường chỉ **vai trò sử dụng**, không phải hai Java classes hoàn toàn khác nhau. Cả hai có thể được load bằng `KeyStore.getInstance(type)` và `load(...)`.

### 3.1. Ví dụ cách phân chia theo mục đích

```text
shipment-client-identity.p12
  alias: client-mtls-v2
  PrivateKeyEntry
    client private key
    client certificate chain

shipment-soap-signing.p12
  alias: signer-v3
  PrivateKeyEntry
    XML Signature private key
    signing certificate chain

partner-trust.p12
  aliases: partner-root-ca, partner-intermediate
  TrustedCertificateEntry
    public CA certificates
```

Đây là sơ đồ logic. Trong thực tế, certificate và private key cho mTLS và SOAP signing có thể cùng một store hoặc khác store, tùy chính sách. **Tách store, alias, quyền và vòng đời theo mục đích** thường làm rotation và least privilege dễ hơn. Không dùng một private key cho mọi protocol chỉ để bớt cấu hình nếu PKI/security policy không cho phép.

### 3.2. Truststore vẫn cần bảo vệ

Certificate trong truststore thường công khai, nhưng nếu kẻ tấn công thay được trusted CA hoặc thêm root CA của họ, ứng dụng có thể tin một endpoint giả. Vì vậy cần:

- Filesystem permissions và image/artifact integrity.
- Quy trình review/approval cho trust anchor changes.
- Audit certificate fingerprints và truststore version.
- Không tải truststore từ URL do SOAP client/Body chỉ định.
- Kiểm certificate chain/hostname thực, không chỉ “file truststore đã load”.

## 4. PKCS#12, JKS, PEM và PKCS#11

| Lựa chọn | Ý nghĩa | Phù hợp khi | Cảnh báo |
| --- | --- | --- | --- |
| **PKCS#12** (`.p12`/`.pfx`) | Container tiêu chuẩn chứa keys/certificates | Trao đổi keystore với Java và nhiều nền tảng | Store/key protection phụ thuộc provider; không giả định mọi file hỗ trợ password semantics y hệt |
| **JKS** | Định dạng kho khóa Java truyền thống | Hệ thống Java cũ | Không phải lựa chọn mặc định tốt nhất cho tính tương tác mới |
| **PEM** | Encoding văn bản của certificate/key material | TLS gateways, OpenSSL và nhiều cloud SDK | File PEM chứa private key là secret dù có dạng text |
| **PKCS#11** | API/protocol truy cập cryptographic token/HSM | Yêu cầu private key không xuất ra ngoài | Cần provider, PIN/credentials, lifecycle và quyền thiết bị |
| **KMS/HSM remote** | Service ký/giải mã hoặc quản lý key | Centralized audit/key isolation | API ký có thể không map trực tiếp sang `KeyStore.getKey` hoặc WSS4J Crypto mặc định |

Với Java hiện đại, **PKCS#12 là lựa chọn phổ biến** cho file keystore. Tuy nhiên, không chuyển JKS→PKCS12 chỉ bằng cách đổi tên đuôi file; cần conversion có kiểm tra entries, certificate chain, algorithms, passwords và interoperability.

### 4.1. Tránh nhầm định dạng với bảo vệ truy cập

- `.p12` được mã hóa/protected **không thay thế** access control của file và secret manager.
- Certificate PEM dạng `-----BEGIN CERTIFICATE-----` thường không bí mật.
- `-----BEGIN PRIVATE KEY-----` có thể là private key **không mã hóa**: phải bảo vệ như credential nhạy cảm nhất.
- `-----BEGIN ENCRYPTED PRIVATE KEY-----` vẫn cần quản lý passphrase tách riêng.
- HSM có thể không cho xuất key, nhưng ứng dụng vẫn phải bảo vệ quyền **sử dụng key**.

## 5. Ranh giới TLS/mTLS và WS-Security trong Spring-WS

```mermaid
flowchart TD
    A[Application / WebServiceTemplate] --> B[SOAP Body từ JAXB/OXM]
    B --> C[WS-Security WSS4J interceptor]
    C --> D[XML Signature / Encryption]
    D --> E[WebServiceMessageSender]
    E --> F[TLS / mTLS qua HTTPS]
    F --> G[Partner endpoint]
    H[Managed secrets] --> I[Key password / Token provider]
    I --> C
    I --> F
    J[Keystore / HSM] --> C
    J --> F
    K[Truststore] --> F
```

Mỗi tầng sử dụng material khác nhau:

- **mTLS sender** dùng `SSLContext`, client private key, certificate chain, trust anchors và handshake.
- **WSS4J SOAP signing** dùng `Crypto`/JCA private-key handling, signing alias, XML Signature policy và key-entry password.
- **WSS4J SOAP validation** dùng trust configuration/certificate validation, message references/algorithms và có thể callback để mở key giải mã.
- **HTTP Basic/proxy** dùng HTTP credential provider; không nên đặt trong SOAP KeyStore.
- **Authorization** kiểm principal/tenant/quyền sau khi security verification thành công.

**TLS bảo vệ kênh; XML Signature có thể bảo vệ thông điệp xuyên trung gian.** Một mTLS certificate hợp lệ không chứng minh SOAP Body đã được ký theo WSDL/security policy, và một SOAP signature hợp lệ không chứng minh HTTP peer được mTLS xác thực.

## 6. Vì sao không để mật khẩu kho khóa trong mã nguồn?

Một anti-pattern:

```java
KeyStore store = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(
        Path.of("client-identity.p12"))) {
    store.load(in, "hardcoded-store-password".toCharArray());
}
```

Mật khẩu trên có thể xuất hiện trong:

1. Git history, forks, pull requests và code review snapshots.
2. Build artifacts, compiled strings/constant pool, caches.
3. Container image layers, config bundles và backup.
4. Dependency/security scans, code search và debugging sessions.
5. IDE autocomplete/indexing hoặc terminal snippets.
6. Logs, stack traces hoặc memory dumps.
7. Bản copy cấu hình gửi qua ticket/chat/email.
8. Môi trường dev/test và production dùng chung secret.

Việc xóa literal khỏi commit mới **không tự thu hồi bí mật đã lộ trong lịch sử**. Nếu secret thật từng bị commit, cần **rotate/revoke** theo kế hoạch, rà soát nơi phát tán và chính sách lưu trữ.

### 6.1. “Mã hóa password trong file properties” có giải quyết triệt để?

Chỉ nếu **khóa giải mã không nằm cạnh dữ liệu và được quản lý bởi một trust boundary tốt hơn**. Nếu một chuỗi encrypted password và hardcoded decryption key cùng trong source, attacker có thể khôi phục secret; bạn chỉ làm mã khó đọc hơn chứ không tách quyền truy cập.

## 7. Phân loại thông tin cấu hình và secret material

Một cấu hình SOAP client nên tách hai nhóm rõ ràng.

**Metadata và policy có thể lưu trong configuration được review:**

- Endpoint URI, proxy host/port, SOAP version.
- Keystore/truststore resource references.
- Kiểu `PKCS12` hoặc `JKS`.
- Key alias như `client-mtls-v2` hoặc `signer-v3`.
- Secret reference names như `secretref://prod/shipment/tls/store-password`.
- Connection timeouts, retry policy, expected peer identity.
- Allowed signature/encryption algorithms và certificate trust policy.

**Secret material phải đi qua kênh quản lý riêng:**

- Store password, key-entry password.
- Private-key bytes hoặc HSM/KMS authentication PIN.
- HTTP password/Bearer token.
- WS-Security UsernameToken shared secret.
- Client certificate bundle nếu kèm private key.
- Secret manager API token/workload credentials.

Một file config không có **giá trị secret** vẫn có thể tiết lộ topology/secret references. Bảo vệ truy cập metadata theo nhu cầu vận hành, nhưng mức bảo vệ phải đặc biệt nghiêm với secret values.

## 8. Threat model: ai có thể đọc mật khẩu?

| Kịch bản | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Developer có read access repo | Lộ password trong source | Không commit secrets; scanning và rotation |
| CI runner có log không được lọc | Password in ra stdout/stderr | Redaction, minimal CI permissions, isolated jobs |
| Container registry bị đọc trái phép | Secret nằm trong image/layer | Không copy private key/secret vào build image |
| Pod bị compromise | Đọc mounted secret hoặc heap | Least privilege, pod isolation, rotation |
| Local file permissions quá rộng | User khác đọc PKCS#12/private key | ACL/permissions và volume policy |
| SOAP client gọi URL tùy ý | SSRF hoặc credential leak cross-origin | Destination allowlist, scoped HTTP auth |
| Log SOAP Header đầy đủ | Lộ UsernameToken/token/cert metadata | Mask/redact, không log raw payload |
| Keystore/truststore bị sửa | Tráo khóa hoặc trust anchor | Artifact integrity, signed release, secure mounts |
| Secret manager outage | TLS/WS-Security không khởi tạo được | Fail closed, bounded cache/TTL và runbook |
| Certificate hết hạn | mTLS handshake/signature thất bại | Expiry monitoring, rollover sớm |
| Secret được rotate không đồng bộ | Một số pods vẫn dùng password cũ | Controlled cutover, probes và instance audit |

**Secret manager không làm rủi ro biến mất**: nó chuyển trách nhiệm sang identity, policy, network, audit và lifecycle của secret source. Mục tiêu là giảm phạm vi truy cập và tăng khả năng thu hồi thay vì hứa không còn nơi nào có thể đọc secret.

## 9. Kiến trúc đưa secret vào ứng dụng

```mermaid
flowchart LR
    A[Reviewed configuration] --> B[Logical secret references]
    B --> C[Secret material adapter]
    D[Workload identity] --> C
    C --> E[Managed secret store]
    E --> C
    C --> F[Scoped char array lease]
    F --> G[KeyStore load / KMF / TLS]
    F --> H[WSS4J key password callback]
    G --> I[WebServiceTemplate]
    H --> I
    I --> J[SOAP partner]
```

**Không để SOAP Body, SOAP Header, HTTP input hoặc caller parameter tự chọn secret reference**. References phải xuất phát từ configuration thuộc quyền operator, đã được kiểm allowlist. Với nhiều đối tác, mapping `partner/alias → secretRef` phải là trusted mapping, không phải nối string từ username chưa được xác thực.

### 9.1. Một lược đồ cấu hình không chứa secret

```yaml
partner:
  shipment:
    endpoint-uri: https://soap.example.invalid/ws/shipments
    tls:
      identity-keystore: /run/secrets/shipment-client.p12
      truststore: /etc/certs/shipment-trust.p12
      key-alias: client-mtls-v2
      store-password-ref: secretref://prod/shipment/tls/store
      key-password-ref: secretref://prod/shipment/tls/key-client-mtls-v2
      truststore-password-ref: secretref://prod/shipment/tls/truststore
    ws-security:
      signing-alias: signer-v3
      signing-keystore: /run/secrets/shipment-signing.p12
      signing-store-password-ref: secretref://prod/shipment/ws-signing/store
      signing-key-password-ref: secretref://prod/shipment/ws-signing/key-signer-v3
```

Đây là **schema minh họa**, không phải các property tự động có của Spring Boot. Những paths/refs phải được provision đúng từ môi trường triển khai, không được lấy tùy ý từ request.

### 9.2. Định danh secretRef không phải password

`secretref://...` là identifier logic, không phải một URL mà XML parser hoặc client HTTP tự truy cập. Chỉ adapter được quản lý mới biết cách resolution. Nếu secret provider dùng remote API, quyền truy cập của ứng dụng phải giới hạn đúng tập references.

## 10. Một abstraction cho nguồn secret được quản lý

Thay vì gọi trực tiếp một SDK Vault/AWS/GCP/Azure trong SOAP adapter, định nghĩa một port:

```java
public interface ManagedSecretSource {
    /**
     * logicalRef thuộc danh sách được cấu hình và phê duyệt.
     * Trả về lease mới, không chia sẻ buffer giữa các requests.
     */
    SecretLease open(String logicalRef)
            throws SecretMaterialUnavailableException;
}
```

`ManagedSecretSource` và `SecretMaterialUnavailableException` là **types do ứng dụng định nghĩa**, không phải Spring-WS built-in. Adapter thật có thể dùng:

- Workload identity + cloud secrets manager.
- Secret store nội bộ qua TLS và least privilege.
- Một service cấp credential per environment.
- Kubernetes mounted secret, với policy phù hợp.
- PKCS#11/HSM PIN provider khi cần.

Điểm cần kiểm chứng là **secret source có thể fail**, credential có thể bị thu hồi và client phải phản ứng an toàn. Không fallback sang mật khẩu demo, mật khẩu môi trường cũ hoặc một secret hardcoded.

## 11. SecretLease: giới hạn vòng đời char[] có kiểm soát

Trong Java, `String` là immutable; không có API xóa nội dung khỏi heap. Các Java cryptographic APIs như `KeyStore.load(InputStream, char[])` và `KeyManagerFactory.init(KeyStore, char[])` hỗ trợ `char[]`, giúp caller **xóa buffer** sau khi sử dụng.

```java
import java.util.Arrays;
import java.util.Objects;

public final class SecretLease implements AutoCloseable {
    private char[] value;

    /**
     * Nhận quyền sở hữu một char[] mới từ source.
     * Caller cũ không tiếp tục dùng hoặc giữ tham chiếu để mutate.
     */
    public SecretLease(char[] ownedValue) {
        this.value = Objects.requireNonNull(ownedValue);
    }

    public char[] chars() {
        if (value == null) {
            throw new IllegalStateException("Secret lease closed");
        }
        return value;
    }

    @Override
    public void close() {
        if (value != null) {
            Arrays.fill(value, '\0');
            value = null;
        }
    }
}
```

Mẫu này có **ownership contract**: `ManagedSecretSource.open(...)` phải cấp một `char[]` riêng cho mỗi lease, không trả trực tiếp array từ cache để bị caller xóa khi vẫn còn consumer khác. Một implementation khác có thể chọn defensive copies, nhưng khi đó cũng phải đảm bảo xóa **tất cả bản sao còn thuộc quyền quản lý**.

### 11.1. Những giới hạn của char[]

- `KeyStore`/JCA/provider có thể copy password nội bộ; việc xóa array caller **không bảo đảm** xóa mọi bản sao.
- Một số Spring/WSS4J setters chỉ nhận `String`; lúc đó một String secret có thể tồn tại đến khi GC.
- Heap dump của JVM có quyền cao vẫn có thể thấy material đã được load.
- JIT/GC/OS memory paging có thể có bản sao mà ứng dụng không trực tiếp kiểm soát.

Vì thế `char[]` là biện pháp **giảm exposure**, không phải bằng chứng “mật khẩu đã biến mất hoàn toàn khỏi memory”.

## 12. Đọc PKCS#12 an toàn bằng KeyStore.load

Ví dụ helper sử dụng một file path từ **trusted configuration**, không cho SOAP caller chọn:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.KeyStore;

public final class SecureKeyStores {

    private SecureKeyStores() {}

    public static KeyStore loadPkcs12(
            Path trustedPath,
            char[] storePassword)
            throws GeneralSecurityException, IOException {

        KeyStore store = KeyStore.getInstance("PKCS12");

        try (InputStream input =
                Files.newInputStream(trustedPath)) {
            store.load(input, storePassword);
        }

        return store;
    }
}
```

Lớp này **không lưu password vào field**, không log nó, và đóng `InputStream` sau khi load. Cần bảo vệ file, đường dẫn, mount và version của keystore; path vẫn có thể tiết lộ thông tin hạ tầng nên không trả chi tiết trực tiếp qua SOAP Fault.

### 12.1. Một chi tiết quan trọng về store password

Với PKCS#12/JKS, `load(...)` dùng password tùy định dạng/provider để kiểm tra integrity hoặc giải mã protected data. Không nên tự giả định `null`, mảng rỗng và mảng có password giống nhau. Có các store hoặc provider cho phép chế độ đặc biệt, nhưng production nên có **một policy password/integrity rõ**, được test trên cùng JDK/provider thực tế.

### 12.2. Không dùng KeyStore.getDefaultType() khi hợp đồng nói PKCS12

`KeyStore.getDefaultType()` có thể phụ thuộc JDK/security properties. Nếu artifact được provision là PKCS#12, hãy chỉ định `KeyStore.getInstance("PKCS12")`; nếu là JKS, chỉ định `"JKS"`. Đổi định dạng phải được review/kiểm entry/chain chứ không đoán theo phần mở rộng file.

## 13. Đọc secret theo scope, không giữ char[] toàn cục

Kết hợp `ManagedSecretSource` và `SecureKeyStores`:

```java
public final class IdentityStoreLoader {
    private final ManagedSecretSource secrets;

    public IdentityStoreLoader(ManagedSecretSource secrets) {
        this.secrets = secrets;
    }

    public KeyStore load(
            Path trustedPath,
            String trustedPasswordRef) throws Exception {

        try (SecretLease password =
                secrets.open(trustedPasswordRef)) {

            return SecureKeyStores.loadPkcs12(
                    trustedPath, password.chars());
        }
    }
}
```

`trustedPasswordRef` phải đến từ **preconfigured allowlist**. Nếu nó được ghép từ một `tenantId` trong SOAP request, caller chưa xác thực có thể làm ứng dụng tìm secret ngoài ý muốn.

### 13.1. Nạp secret theo từng request hay lúc khởi tạo?

Với mTLS keystore, việc tải file và xây `SSLContext` **cho mỗi SOAP request** thường rất tốn kém, có thể dẫn đến race/DoS. Thông thường xây một **client credential profile immutable** khi startup hoặc rotation. Secret chỉ cần dùng trong khâu load/init; HTTP client và key manager giữ material cần thiết để chạy.

Với UsernameToken secrets, có thể cần lookup theo caller ở inbound WSS4J callback. Trường hợp ấy phải có policy cho cache, concurrency, expiration và audit riêng. Không áp một cách lookup cho mọi loại secret.

## 14. Store password và key-entry password: hai bước khác nhau

Ví dụ mTLS identity:

```java
KeyStore identity = SecureKeyStores.loadPkcs12(
        identityPath, storePassword);

KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());

kmf.init(identity, keyEntryPassword);
```

`KeyStore.load(...)` mở/kiểm store. `KeyManagerFactory.init(...)` dùng password để truy cập private-key entries mà manager cần. Hai password **có thể khác nhau về mặt khái niệm và trong một số store/providers**.

### 14.1. Vì sao nhiều ví dụ lại dùng cùng một mật khẩu?

Một số PKCS#12 toolchains hoặc keystore import workflows sử dụng cùng password cho store và private-key entry; một số provider có hạn chế với per-entry passwords. Điều đó **không làm hai khái niệm trở thành một**.

Cần kiểm:

- Tool sinh `.p12` sử dụng store password và key password nào.
- JDK/provider có hỗ trợ khác password hay không.
- `KeyManagerFactory` có thể mở private key đúng alias không.
- Có nhiều key entries với passwords khác nhau không.

Nếu một keystore chứa các entries cần passwords khác nhau, `KeyManagerFactory.init(store, onePassword)` có thể không phù hợp. Có thể cần store tách riêng, `KeyStore.Builder`/provider-specific cơ chế hoặc custom key manager được review. Không giải quyết bằng cách chọn bừa password chung cho mọi key.

### 14.2. Alias là thông tin định tuyến, không phải quyền truy cập

`alias="client-mtls-v2"` chỉ giúp chọn entry. Nếu keystore bị thay hoặc alias trùng nhưng key khác, ứng dụng vẫn có thể dùng khóa sai. Nên verify expected certificate identity/fingerprint và loại entry khi khởi tạo, thay vì tin tên alias tuyệt đối.

## 15. Tạo SSLContext cho Spring-WS client có mTLS

Ví dụ JDK chuẩn:

```java
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class PartnerTlsContextFactory {

    private final ManagedSecretSource secretSource;

    public PartnerTlsContextFactory(
            ManagedSecretSource secretSource) {
        this.secretSource = secretSource;
    }

    public SSLContext create(
            Path trustedIdentityP12,
            Path trustedTruststoreP12,
            String identityStoreSecretRef,
            String privateKeySecretRef,
            String trustStoreSecretRef) throws Exception {

        try (SecretLease storePassword =
                    secretSource.open(identityStoreSecretRef);
             SecretLease keyPassword =
                    secretSource.open(privateKeySecretRef);
             SecretLease trustPassword =
                    secretSource.open(trustStoreSecretRef)) {

            KeyStore clientIdentity = SecureKeyStores.loadPkcs12(
                    trustedIdentityP12, storePassword.chars());

            KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(clientIdentity, keyPassword.chars());

            KeyStore truststore = SecureKeyStores.loadPkcs12(
                    trustedTruststoreP12, trustPassword.chars());

            TrustManagerFactory tmf =
                    TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm());
            tmf.init(truststore);

            SSLContext context = SSLContext.getInstance("TLS");
            context.init(
                    kmf.getKeyManagers(),
                    tmf.getTrustManagers(),
                    new SecureRandom());

            return context;
        }
    }
}
```

Phần trên có trách nhiệm **khởi tạo TLS context**. Nó không tự thiết lập:

- Hostname verification trong mọi HTTP/SSL socket use case.
- Proxy/HTTP Basic authentication.
- Timeout, connection pool hoặc redirect policy.
- SOAP XML Signature và WS-Security.
- Quyền trên vận đơn.

### 15.1. Hostname verification không nằm trong KeyStore.load

`TrustManagerFactory` giúp xác minh certificate chain theo trust anchors/PKIX policy. **Hostname/SAN verification** là kiểm tra identity của HTTPS endpoint trong TLS client. `SSLContext` hợp lệ chưa đủ để khẳng định một raw `SSLSocket` hoặc custom HTTP client luôn bật đúng hostname verification.

Với Java `HttpClient` gọi HTTPS, giữ hostname verification mặc định của HTTPS stack và test với certificate sai SAN. **Không tắt hostname validation** để “sửa” một lỗi chứng chỉ.

### 15.2. Không thay trust manager bằng “trust all”

Đoạn code sau là anti-pattern:

```text
X509TrustManager.checkServerTrusted(...) -> no-op
HostnameVerifier -> always true
```

Nó làm một kẻ ở giữa có thể giả làm SOAP partner, đọc HTTP Basic credentials/SOAP payload hoặc thay đổi response. Giải quyết bằng CA chain, SAN, truststore và certificate issuance chính xác.

## 16. Đưa SSLContext vào WebServiceTemplate

Spring-WS `WebServiceTemplate` gửi SOAP messages qua một `WebServiceMessageSender`. Ví dụ với Spring-WS 4.x và JDK `HttpClient`:

```java
import java.net.http.HttpClient;
import java.time.Duration;

import javax.net.ssl.SSLContext;

import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.http.JdkHttpClientMessageSender;

public final class ShipmentSoapTransport {

    public static WebServiceTemplate create(
            SSLContext trustedContext,
            String trustedEndpointUri) {

        HttpClient client = HttpClient.newBuilder()
            .sslContext(trustedContext)
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        JdkHttpClientMessageSender sender =
                new JdkHttpClientMessageSender(client);
        sender.setRequestTimeout(Duration.ofSeconds(20));

        WebServiceTemplate template = new WebServiceTemplate();
        template.setDefaultUri(trustedEndpointUri);
        template.setMessageSender(sender);

        return template;
    }
}
```

Đây là bộ khung **HTTP/TLS sender**, chưa cấu hình JAXB marshaller/unmarshaller, SOAPAction, WSS4J interceptor, Fault resolver và application gateway. `trustedEndpointUri` phải xuất phát từ application configuration có allowlist, **không** nhận URL tùy ý từ request, để tránh SSRF và credential leakage.

### 16.1. Tại sao tạo client profile lúc startup/rotation?

Một immutable profile có thể gói:

```text
PartnerSoapClientProfile
  - approved endpoint URI
  - SSLContext (client identity + trust anchors)
  - HTTP sender (proxy/auth/timeouts/pooling)
  - SOAP version + JAXB marshaller
  - WS-Security signing/decryption policy
  - operation/certificate version metadata
```

Khi rotation, tạo profile mới, kiểm tra readiness, **hoán đổi theo cách được kiểm soát**, rồi cho requests cũ hoàn tất trước khi retire profile cũ. Tránh đổi keystore password hoặc signing alias trên một singleton đang xử lý requests đồng thời.

## 17. Truststore cho client và server: khác hướng nhưng cùng nguyên lý

**SOAP client outbound:**

- Truststore giúp client xác minh server certificate của đối tác.
- Khi mTLS được bật, keystore identity cung cấp client private key và certificate chain.
- Cần kiểm SAN của hostname theo HTTPS stack và route/proxy policy.

**Spring-WS server inbound:**

- TLS termination layer/container/gateway thường quản lý server certificate/private key.
- Nếu yêu cầu client mTLS, tầng TLS dùng trust configuration để xác minh client certificate.
- SOAP application phải nhận identity từ **kênh đáng tin** sau TLS termination và kiểm quyền.

Không tự tin một HTTP Header như `X-Client-Cert` do caller gửi trực tiếp qua Internet. Nếu gateway chuyển tiếp identity, phải có trust boundary rõ (proxy chỉ được truy cập nội bộ, headers được gateway tạo/ghi đè, có authentication giữa gateway–backend).

### 17.1. Truststore rộng quá mức cũng nguy hiểm

“Nhét mọi CA vào truststore để khỏi lỗi handshake” có thể làm tăng bề mặt trust. Nên chọn trust anchors theo policy, kiểm certificate constraints và hạn chế certificate pinning thiếu kế hoạch rotation. Với partner có CA riêng, test các trường hợp new intermediate, expired certificate, hostname mismatch và trust root thay đổi.

## 18. Mật khẩu kho khóa trong WS-Security khác TLS

Khi SOAP client **ký XML** bằng WSS4J, engine thường cần:

- `Crypto` trỏ tới key/cert store hoặc provider.
- **Signing alias** được provision.
- Mật khẩu để mở private-key entry nếu provider yêu cầu.
- Các signature algorithms và **các phần tử SOAP cần ký**.
- Ký trên nội dung đúng, tránh XML Signature Wrapping.

Khi SOAP server **kiểm chữ ký**, nó thường cần trust/validation `Crypto` để xác minh signer certificate và signature references, **không nhất thiết cần private key password** chỉ để verify.

Khi SOAP server **giải mã**, nó lại cần decryption private key và có thể cần password tương ứng.

### 18.1. Phân chia secret references

| WS-Security operation | Material | SecretRef riêng? |
| --- | --- | --- |
| Securement signature | Signing private key + entry password | Nên có |
| Validation signature | Trust/certificate policy | Truststore integrity cần bảo vệ, không phải always key password |
| Validation decryption | Decryption private key + entry password | Nên có |
| UsernameToken | Shared secret/password-equivalent | Có, tách khỏi signing password |
| Symmetric encryption | Secret key | Có, theo key version/purpose |
| KeyStore encrypted properties | Master decrypt password | Có, tách khỏi key-entry password |

Không dùng chung `SOAP_PASSWORD` cho mọi mục đích chỉ để cấu hình ít biến.

## 19. WSS4J Crypto: khóa nằm ở đâu?

Apache WSS4J có abstraction `org.apache.wss4j.common.crypto.Crypto` cho việc tìm keys, certificates và trust-related operations theo provider. Trong Spring-WS, `Wss4jSecurityInterceptor` có các setter như:

- `setSecurementSignatureCrypto(...)`.
- `setValidationSignatureCrypto(...)`.
- `setValidationDecryptionCrypto(...)`.
- `setSecurementSignatureUser(...)`.
- Các options tương ứng security actions và algorithms.

Một số ví dụ Spring-WS dùng `CryptoFactoryBean` cùng keystore resource/password. **Không copy nguyên mật khẩu literal từ ví dụ thành production configuration.** Đối chiếu phiên bản Spring-WS/WSS4J thật: property names, constructor và khả năng nhận key material thay đổi theo major version/provider.

### 19.1. Không đồng nhất Java SSLContext và WSS4J Crypto

`SSLContext` tạo/bảo vệ TLS session. `Crypto` cung cấp material cho **XML Signature/Encryption**. Cả hai có thể đọc cùng PKCS#12 file theo policy, nhưng:

- Sử dụng certificate/key cho mục đích khác.
- Có algorithms và coverage rules khác.
- Có life cycle, alias selection và validation khác.
- Chữ ký SOAP cần kiểm rằng **SOAP Body thực được dùng** đã được ký.

Không chỉ gắn `SSLContext` rồi kết luận `wsse:Security` được thêm tự động vào SOAP Header.

## 20. CallbackHandler cho private-key entry password

WSS4J có `WSPasswordCallback`, dùng `identifier` và `usage` để yêu cầu secret phù hợp. Với `SIGNATURE` và `DECRYPT`, identifier thường là **key alias** do security configuration chọn; callback có thể cung cấp mật khẩu mở entry.

Một abstraction giới hạn mục đích:

```java
import java.io.IOException;

public interface KeyEntryPasswordSource {
    SecretLease openForSigningAlias(String alias)
            throws IOException;

    SecretLease openForDecryptionAlias(String alias)
            throws IOException;
}
```

Source phải dùng trusted mapping:

```text
signer-v3 -> secretref://prod/shipment/ws-sign/key-signer-v3
decrypt-v2 -> secretref://prod/shipment/ws-decrypt/key-decrypt-v2
```

Không ghép key alias từ SOAP Body hoặc một `wsse:Username` chưa được xác thực để đọc arbitrary secret path.

### 20.1. Java CallbackHandler minh họa

```java
import java.io.IOException;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.UnsupportedCallbackException;

import org.apache.wss4j.common.ext.WSPasswordCallback;

public final class ManagedKeyPasswordCallback
        implements CallbackHandler {

    private final KeyEntryPasswordSource source;

    public ManagedKeyPasswordCallback(
            KeyEntryPasswordSource source) {
        this.source = source;
    }

    @Override
    public void handle(Callback[] callbacks)
            throws IOException, UnsupportedCallbackException {

        for (Callback item : callbacks) {
            if (!(item instanceof WSPasswordCallback callback)) {
                throw new UnsupportedCallbackException(
                        item, "Unsupported WS callback");
            }

            try (SecretLease lease =
                    openAllowedPassword(callback)) {
                if (lease == null || lease.chars().length == 0) {
                    throw new IOException(
                            "Key material unavailable");
                }

                // WSS4J yêu cầu String ở đây; không log nó.
                callback.setPassword(new String(lease.chars()));
            } catch (IOException problem) {
                // Không lộ vault path/endpoint hoặc secret details.
                throw new IOException(
                        "Key material unavailable");
            }
        }
    }

    private SecretLease openAllowedPassword(
            WSPasswordCallback callback)
            throws IOException, UnsupportedCallbackException {

        return switch (callback.getUsage()) {
            case WSPasswordCallback.SIGNATURE ->
                source.openForSigningAlias(
                    callback.getIdentifier());
            case WSPasswordCallback.DECRYPT ->
                source.openForDecryptionAlias(
                    callback.getIdentifier());
            default ->
                throw new UnsupportedCallbackException(
                    callback, "Unsupported key purpose");
        };
    }
}
```

`KeyEntryPasswordSource` phải thực thi **alias allowlist**, không chỉ đọc secret path ghép từ `getIdentifier()`. `SecretLease.close()` xóa char[]; tuy nhiên `new String(...)` vẫn tạo một immutable copy trong JVM do yêu cầu callback API. Không thể tuyên bố tất cả bytes đã được zeroize.

### 20.2. Vì sao không viết một handler trả cùng password cho mọi usage?

`WSPasswordCallback.USERNAME_TOKEN` yêu cầu shared secret cho UsernameToken; `SIGNATURE`/`DECRYPT` dùng key-entry passwords; các usages như `SECRET_KEY` có thể yêu cầu `setKey(byte[])`. Một handler trả cùng `String` cho mọi usage làm sai policy, tăng blast radius và có thể khiến engine xử lý nhầm material.

### 20.3. Callback nào dùng ở inbound/outbound?

Không giả định mọi operation đều dùng cùng setter:

- Spring-WS `setValidationCallbackHandler(...)` dùng callback trong **validation/decryption flows** theo cấu hình.
- Một số outbound securement flows dùng setters như `setSecurementPassword(...)` hoặc WSS4J-specific config/callback integration.
- `SIGNATURE` trong callback thường liên quan việc mở key cho signing action; `DECRYPT` liên quan decryption action.
- **Không bịa method `setSecurementCallbackHandler(...)`** nếu Spring-WS version không công bố API đó.

Cần test actual SOAP message security chain để chứng minh handler có được gọi đúng lúc. Với outbound password bị giữ trong interceptor singleton, cân nhắc **profile recreation khi rotation**, không mutate nóng thiếu đồng bộ.

## 21. Keystore password khác secret manager token

Ứng dụng có thể cần một workload identity để gọi Vault:

```mermaid
flowchart TD
    A[Pod / VM workload identity] --> B[Managed secret store]
    B --> C[Keystore store password]
    B --> D[Private-key entry password]
    C --> E[KeyStore.load]
    D --> F[KeyManagerFactory / WSS4J]
    G[Protected PKCS12 artifact] --> E
    E --> F
```

Workload identity **không phải** store password. Nó là một quyền để yêu cầu secret manager cấp giá trị được phép. Nếu cùng một credential có quyền đọc toàn bộ môi trường production, compromise một ứng dụng có thể lan sang các ứng dụng khác.

### 21.1. Quyền tối thiểu

- Chỉ cấp quyền `read` cho đúng refs cần thiết.
- Không cho phép `list` toàn bộ tenants nếu không cần.
- Phân chia production/staging/dev identities.
- Audit theo secretRef/version, không log secret value.
- Giới hạn network egress của ứng dụng đến secret manager.
- Có chính sách revoke workload token khi ứng dụng bị compromise.
- Nếu source hỗ trợ response encryption/attestation, dùng theo threat model.

**Không đưa URL Vault hoặc token client vào SOAP Fault công khai** nếu lookup gặp lỗi.

## 22. Secrets ở environment variables: có ưu điểm và giới hạn

Environment variables thường dễ tích hợp nhưng có rủi ro:

- Có thể lộ qua process inspection có quyền, diagnostic dumps hoặc debug tooling.
- Có thể bị in trong CI env dumps hoặc startup logs.
- Được lưu dạng String trong runtime; không xóa dễ dàng.
- Biến môi trường lúc process khởi động **không tự refresh** khi secret manager rotate.
- Một số orchestration/monitoring tools hiển thị env metadata cho người có quyền.

Do đó, biến môi trường **không tự biến mật khẩu thành an toàn**. Sử dụng workload identity/mounted secret/secret SDK theo security policy, hạn chế quyền truy cập và đảm bảo log redaction.

### 22.1. Secret file mounts

Với mounted secrets:

- Mount với quyền đọc tối thiểu, path không nằm trong Git.
- Giữ private-key material khỏi build image nếu có thể.
- Tránh đồng bộ secret vào thư mục build artifacts hoặc shared volumes.
- Đảm bảo ứng dụng không in nội dung file khi lỗi.
- Thiết kế cách nhận version mới; file update không tự thay `SSLContext`/JCA objects đã load.
- Kiểm cleanup/revoke sau pod termination và backup policy.

### 22.2. Kubernetes Secrets là gì?

Kubernetes Secret lưu các giá trị được biểu diễn/đưa vào API theo cơ chế của cluster; trường `data` thường dùng **base64 encoding**, **không phải encryption bảo vệ dữ liệu khi ai đó đọc YAML**. Cần RBAC, encryption at rest/KMS theo cấu hình cluster, secret encryption/CSI/external store khi phù hợp, và hạn chế ai được đọc API/etcd.

Không commit file Kubernetes Secret có giá trị production encoded base64 rồi nghĩ nó đã được bảo mật.

## 23. Tránh đưa password vào command-line arguments

Một anti-pattern vận hành:

```text
java -Dkeystore.password=real-secret -jar shipment.jar
```

Command-line args và JVM system properties có thể xuất hiện trong process listings, diagnostic tools, crash reports hoặc launcher logs tùy hệ điều hành và quyền.

Nếu cần chạy `keytool`/`openssl` cho một bài thực hành, dùng prompt tương tác hoặc cơ chế nhập secret được môi trường hỗ trợ an toàn, tránh paste plaintext password vào shell history. Không ghi private key hoặc password vào một câu lệnh được gửi qua chat/ticket.

### 23.1. Không xóa secret bằng cách đổi tên biến

Thay `KEYSTORE_PASSWORD` bằng `SECRET_ENCRYPTED_VALUE` nhưng vẫn để decryption key trong source không giải quyết được vấn đề. Security review cần nhìn **đường dữ liệu của secret**, không chỉ tên thuộc tính.

## 24. Quy trình tạo và lưu PKCS#12 cho môi trường thử nghiệm

Một workflow học tập an toàn:

1. Tạo **test keypair/certificate** bằng công cụ PKI được phê duyệt.
2. Xuất identity bundle PKCS#12 có private key và certificate chain đúng.
3. Gán alias thể hiện purpose/version, ví dụ `client-mtls-test-v1`.
4. Tạo truststore chỉ chứa test CA cần thiết.
5. Đưa password vào test secret provider **không commit vào Git**.
6. Chạy unit/integration tests và kiểm alias/chain.
7. Xóa tệp tạm, log và secret test sau bài tập theo policy.

### 24.1. Kiểm metadata bằng keytool

Ví dụ lệnh không chứa password:

```sh
keytool -list -v -storetype PKCS12 -keystore client-identity.p12
```

Công cụ sẽ hỏi store password hoặc dùng một kênh input do người vận hành cung cấp. Không đưa password thật vào dòng lệnh mẫu. Output có thể chứa subject, issuer, certificate fingerprints và alias; thông tin này không phải private key, nhưng vẫn cần xem xét mức công khai của hạ tầng.

### 24.2. Không dùng test key trong production

Một keypair được sinh để demo, certificate tự ký hoặc password dễ nhớ chỉ phù hợp sandbox. Production certificate phải có identity, key usage, validity, issuer/trust, thuật toán và quản lý vòng đời theo PKI policy.

## 25. Rotation: phải xoay vòng đúng thứ cần thay

Có ít nhất bốn loại thay đổi:

| Thay đổi | Cái nào đổi? | Cái nào có thể giữ nguyên? |
| --- | --- | --- |
| **Store password rotation** | Password bảo vệ container | Private key/certificate có thể giữ nguyên |
| **Key-entry password rotation** | Password bảo vệ một entry | Public certificate có thể giữ nguyên |
| **Private key/certificate rotation** | Keypair/certificate/alias/chain | Một số config khác có thể không đổi |
| **Trust anchor rotation** | CA/intermediate certificates hoặc trust policy | Client signing key có thể giữ nguyên |

Không xem “thay password keystore” là đã rotate certificate hoặc private key. Nếu private key bị lộ, chỉ đổi store password là **không đủ**: phải revoke/replace key/certificate theo PKI incident response policy.

### 25.1. Rollover certificate có thể cần hai chiều

Nếu client mTLS certificate thay:

1. Partner phải tin certificate/issuer mới theo policy.
2. Client phải có private key và chain mới.
3. Alias selection cần chọn đúng identity.
4. Deployment phải hỗ trợ chuyển tiếp không mất request đang chạy.
5. Quan sát handshake failures, wrong issuer/SAN, revoked/expired certificate.
6. Certificate cũ được thu hồi sau thời gian chuyển đổi đã thỏa thuận.

Nếu signing certificate trong SOAP Body thay, partner còn phải cập nhật **WS-Security trust configuration**, không chỉ TLS truststore.

## 26. Blue/green credential profiles và atomic cutover

Một cách triển khai:

```mermaid
flowchart TD
    A[Profile v1 đang hoạt động] --> B[Nhận secret/key/cert v2]
    B --> C[Khởi tạo KeyStore, TLS, WSS4J profile v2]
    C --> D[Kiểm alias, certificate, handshake, signature]
    D --> E{Profile v2 đạt kiểm tra?}
    E -->|Không| F[Giữ v1, alert, không publish v2]
    E -->|Có| G[Hoán đổi routing/client profile]
    G --> H[Cho requests v1 hoàn tất]
    H --> I[Đóng/thu hồi profile v1]
    I --> J[Audit và dọn cache]
```

Trong một dịch vụ nhiều instances, rollout/cutover có thể cần coordination, readiness check và compatibility window giữa hai phía.

### 26.1. Vì sao không sửa mật khẩu trực tiếp trên singleton?

Nếu hai threads cùng ký SOAP messages mà một thread đổi `securementPassword` hoặc alias giữa chừng, request có thể dùng **certificate v2 với password/alias v1**, dẫn đến lỗi hoặc identity sai. Profile immutable + atomic replacement giúp giảm nguy cơ.

### 26.2. SSLContext thường không tự đọc lại file

Đổi `client-identity.p12` trên disk không đồng nghĩa `SSLContext`/`KeyManager` đã khởi tạo sẽ tự nạp identity mới. Cần **rebuild** hoặc cơ chế reload được hỗ trợ và kiểm thử, đồng thời quản lý các existing TLS sessions/connections đang giữ identity cũ.

## 27. Rotation truststore và kiểm certificate validity

Truststore renewal phải có policy:

- Cài CA/trust anchor mới theo quy trình phê duyệt.
- Duy trì các anchors cũ trong overlap window khi được phép.
- Kiểm certificate chain validation khi partner chuyển certificate.
- Kiểm hostname/SAN matching và expected identity.
- Thu hồi anchor cũ sau khi chắc không còn được sử dụng.
- Audit mọi thay đổi thêm CA, vì thêm root CA là tăng phạm vi trust.

### 27.1. Theo dõi hết hạn certificate

Certificate có `notBefore` và `notAfter`, nhưng chỉ đọc ngày hết hạn **không đủ**. Cần theo dõi:

- Expected hostname/SAN và key usage/extended key usage.
- Chain completeness.
- Thuật toán/key size theo policy.
- Certificate revocation nếu môi trường yêu cầu.
- Certificate active ở load balancer/gateway **thực tế**, không chỉ bản file trong repository.
- Rotation lead time đủ cho partner phê duyệt.

Gắn cảnh báo theo **thời gian tương lai** có lead time hợp lý; không đợi production handshake thất bại mới phát hiện.

## 28. Caching secret: hiệu năng không được đánh đổi việc thu hồi

Nạp secrets qua remote service mỗi lần tạo SOAP request là cách tốn latency và có thể tạo DoS. Nhưng cache quá lâu khiến credential đã revoke vẫn còn dùng.

Một **managed secret cache** nên có:

- Keys theo trusted secretRef + version/purpose.
- TTL giới hạn và cache size bound.
- Invalidation khi rotation hoặc revoke.
- Bản sao array khi trả secret cho consumer.
- Thread-safe refresh, hạn chế đồng loạt truy vấn Vault.
- Không lưu raw secrets vào disk dump hoặc JSON.
- Audit hit/miss/refresh theo metadata, không secret value.
- Fail-closed khi secret hết hạn và không thể refresh theo policy.

Với TLS/WS-Security key material đã load vào active client profile, ngoài secret cache còn có **crypto object caches**. Một cache entry bị invalidated không tự phá mọi `SSLContext` hoặc WSS4J Crypto đang hoạt động.

### 28.1. Thế nào là fail closed?

Khi secret không có:

- Không fallback sang mật khẩu mặc định.
- Không bỏ mTLS hoặc tắt signature validation.
- Không sử dụng keystore trống hoặc `TrustManager` trust-all.
- Không tự gọi một insecure SOAP endpoint khác.
- Không trả response nghiệp vụ thành công để che mất xác thực thất bại.

Báo lỗi an toàn và giữ hệ thống ở trạng thái không thực hiện operation mà policy yêu cầu bảo vệ.

## 29. Đa đối tác, nhiều tenant và nguy cơ lẫn khóa

Một ứng dụng tích hợp có thể gọi Partner A và Partner B, mỗi bên có endpoint, client cert, trust anchors và signing key riêng.

Sai lầm:

```java
// ANTI-PATTERN: shared mutable profile cho nhiều đối tác.
sharedTemplate.setDefaultUri(partnerEndpointFromRequest);
sharedSecurity.setSecurementSignatureUser(aliasFromRequest);
```

Hai requests chạy đồng thời có thể khiến client gửi **credential của A đến endpoint B**. Điều này nghiêm trọng hơn một lỗi timeout thông thường.

### 29.1. Tạo profile theo đích đáng tin

```text
Partner A
  endpoint allowlist A
  mTLS identity A
  WS-Security signing alias A
  trust policy A
  secret references A

Partner B
  endpoint allowlist B
  mTLS identity B
  WS-Security signing alias B
  trust policy B
  secret references B
```

Identity của đối tác phải được chọn từ **configuration/validated routing**, không dựa vào XML Body fields do caller tự nhập. Nếu partner có nhiều tenants được phép chia sẻ một key, phải có authorization policy cụ thể; không suy việc dùng chung certificate là quyền truy cập mọi tenant.

## 30. Kiểm tra keystore sau khi load

Load thành công chưa bảo đảm đúng identity. Nên kiểm tra entry và certificate metadata phù hợp với profile:

```java
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;

public final class KeyStoreChecks {

    public static X509Certificate requireIdentity(
            KeyStore store, String trustedAlias)
            throws Exception {

        if (!store.isKeyEntry(trustedAlias)) {
            throw new IllegalStateException(
                "Expected key entry is unavailable");
        }

        Certificate certificate =
                store.getCertificate(trustedAlias);

        if (!(certificate instanceof X509Certificate x509)) {
            throw new IllegalStateException(
                "Expected X.509 identity not found");
        }

        x509.checkValidity();
        return x509;
    }
}
```

Đây là **kiểm tra tối thiểu**, chưa đầy đủ. Production có thể cần:

- Key usage/EKU theo mTLS hoặc XML signing profile.
- Subject/SAN phù hợp identity được provision.
- Expected issuer/chain/public-key fingerprint theo policy.
- Algorithm và key length.
- Certificate path/trust validation.
- Certificate status/revocation khi được yêu cầu.
- Chọn đúng alias trong key manager khi có nhiều entries.

`checkValidity()` chỉ kiểm thời gian, **không chứng minh certificate đáng tin hoặc thuộc partner đúng**. Không log toàn bộ certificate/key khi thất bại; có thể ghi fingerprint/alias metadata an toàn theo runbook.

## 31. Sai mật khẩu nên trả lỗi gì?

Khi `KeyStore.load` hoặc `KeyManagerFactory.init` thất bại:

- `IOException` hoặc `GeneralSecurityException` có thể chứa chi tiết provider.
- Không đưa message ấy trực tiếp vào SOAP Fault hoặc HTTP response.
- Không coi nó là lỗi nghiệp vụ như `SHIPMENT_NOT_FOUND`.
- Nếu xảy ra lúc startup/cutover, có thể đánh dấu application **not ready** và giữ profile cũ được phép.
- Nếu xảy ra runtime và không có profile bảo mật hợp lệ, **không xử lý** request bằng cấu hình giảm bảo vệ.

### 31.1. Phân loại operational errors

| Lỗi | Phân loại | Phản ứng |
| --- | --- | --- |
| Password ref không tồn tại | Configuration/secret management | Fail closed, alert |
| Secret manager 403 | Workload authorization | Kiểm service identity, không đẩy secretRef tới client |
| PKCS#12 password không đúng | Key material/config | Không tạo TLS/WSS4J profile |
| Alias sai | Configuration | Reject profile, không chọn key khác tùy tiện |
| Certificate hết hạn | PKI lifecycle | Reject/rotate theo policy |
| Partner certificate không trust | TLS hoặc XML Signature trust | Giữ verification, sửa trust path |
| Private key/certificate không khớp | Key material integrity | Reject profile |
| HTTP 401/407 | Origin/proxy authentication | Kiểm credential provider riêng |
| WS-Security signature invalid | SOAP security | Từ chối trước use case |
| Timeout sau khi SOAP command đã gửi | Transport/unknown outcome | Tra cứu trạng thái/idempotency |

**Một lỗi keystore có thể xảy ra trước khi có SOAP Envelope**: ví dụ TLS handshake không khởi tạo được. Đừng hứa mọi lỗi chứng chỉ đều có typed SOAP Fault.

## 32. Observability và audit không làm lộ bí mật

Một log sự kiện an toàn có thể như:

```text
partner=shipment-provider
component=tls-client-profile
profileVersion=v3
certificateAlias=client-mtls-v3
event=KEYSTORE_INITIALIZATION_FAILED
correlationId=CFG-1042
result=REJECTED
```

Không ghi:

- `storePassword`, `keyEntryPassword` hoặc `SecretLease.chars()`.
- Toàn bộ `System.getenv()` hay properties khi debug.
- Raw WS-Security UsernameToken hoặc SOAP signed payload nhạy cảm.
- PEM private key, PKCS#12 bytes, Vault token.
- Provider exception chứa URL/credential hoặc secret value.
- KeyStore object dump/stack traces trong lỗi công khai.

### 32.1. Metrics ví dụ

```text
soap_tls_handshake_failures_total{partner="shipment",cause="trust"}
soap_keystore_profile_load_total{partner="shipment",result="failure"}
soap_certificate_days_until_expiry{partner="shipment",role="client-mtls"}
soap_ws_signature_failures_total{partner="shipment"}
soap_secret_lookup_errors_total{source="managed",reason="timeout"}
```

Các tên trên là **mẫu thiết kế**, không phải metrics Spring-WS tự có. Tránh high-cardinality labels như request ID, token, username nguyên gốc hoặc secretRef chi tiết.

### 32.2. Heap dumps và debug tooling

Nếu production incident cần heap dump, phải coi heap dump là **artifact nhạy cảm cao** vì JCA/WSS4J có thể giữ key material và password String. Dùng quyền truy cập hạn chế, mã hóa, thời gian lưu ngắn và quy trình xóa rõ; đừng attach heap dumps vào ticket công khai.

## 33. Unit tests: password source, lease và key store

### 33.1. SecretLease xóa char[]

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class SecretLeaseTest {

    @Test
    void wipesOwnedBufferAfterClose() {
        char[] chars = "TEST-ONLY".toCharArray();

        SecretLease lease = new SecretLease(chars);
        assertEquals("TEST-ONLY", new String(lease.chars()));

        lease.close();

        for (char c : chars) {
            assertEquals('\0', c);
        }

        assertThrows(
            IllegalStateException.class, lease::chars);
    }
}
```

Đây là **test ownership/zeroization của array**, không phải bằng chứng JVM đã xóa mọi bản sao trong heap. Giá trị `TEST-ONLY` là fixture không nhạy cảm.

### 33.2. Fake managed provider

```java
ManagedSecretSource fake = logicalRef -> {
    if (!"test/tls/store".equals(logicalRef)) {
        throw new SecretMaterialUnavailableException(
                "Unavailable test credential");
    }
    return new SecretLease("TEST-STORE-PW".toCharArray());
};
```

`SecretMaterialUnavailableException` là application exception cần định nghĩa. Test phải chứng minh:

- Đúng ref được cung cấp.
- Ref khác bị từ chối.
- Secret values không được log.
- Lỗi provider không kích hoạt default password.
- Mọi lease được đóng kể cả khi `KeyStore.load` ném exception.

### 33.3. Dùng PKCS#12 test artifact riêng

Với một keystore **test** được tạo/provision trong test fixture:

1. Load với đúng password và kiểm alias.
2. Load với sai store password và mong đợi failure.
3. Init `KeyManagerFactory` với key password đúng/sai.
4. Kiểm certificate validity và expected identity.
5. Không mở test store bằng password production.
6. Xóa file tạm và secrets sau test khi policy yêu cầu.

Test có thể tạo in-memory keystore; nhưng các providers hỗ trợ PKCS#12 và key entries khác nhau, nên integration test với **artifact/file thật** vẫn cần thiết.

## 34. Integration tests: TLS, mTLS và SOAP Signature

### 34.1. mTLS test matrix

| Kịch bản | Kết quả cần quan sát |
| --- | --- |
| Client certificate hợp lệ và đúng chain | TLS handshake thành công |
| Client không có certificate nhưng server yêu cầu mTLS | Handshake/security rejection |
| Certificate client hết hạn | Bị từ chối theo trust policy |
| Certificate server sai hostname/SAN | HTTPS client từ chối |
| Certificate server không thuộc CA tin cậy | Từ chối, không dùng trust-all workaround |
| Identity keystore password sai | Client profile không được khởi tạo |
| Key-entry password sai | Key manager không thể mở key |
| Alias được provision không tồn tại | Profile bị từ chối trước traffic |
| Certificate mới trong overlap window | Hoạt động đúng sau trust/update |
| Truststore bị sửa trái phép | Artifact integrity/security check phát hiện |

### 34.2. SOAP WS-Security test matrix

- SOAP Body có chữ ký đúng của signing alias được cấp.
- Chữ ký bị sửa một byte bị từ chối.
- Truststore/validation crypto không tin certificate đối tác.
- Chữ ký đúng nhưng thiếu phần SOAP Body bắt buộc phải ký: bị từ chối theo policy.
- Callback `SIGNATURE`/`DECRYPT` nhận alias chưa được allowlist.
- Private key/password rotation giữa hai requests không gây lẫn credential.
- HTTP/mTLS thành công nhưng SOAP signature sai vẫn bị từ chối.
- SOAP signature hợp lệ nhưng caller không có quyền trên shipment vẫn bị từ chối ở application authorization.

### 34.3. MockWebServiceServer chưa đủ

Spring-WS mock client có thể kiểm SOAP XML/callback, nhưng **không tự chứng minh** TLS handshake, keystore load, proxy, certificate validation và mTLS qua mạng. Cần test với một **TLS server test fixture** có certificate test và một SOAP endpoint/interceptor thật. Với client Java và .NET/ESB của đối tác, cần kiểm interoperability của key identifiers, signature algorithms, canonicalization và trust policy.

### 34.4. Test unknown outcome khi connection đứt

Một SOAP command có thể đã commit trước khi client thấy TLS reset/timeout. Không retry với requestId mới chỉ vì exception là kỹ thuật. Test idempotency, status query và transaction behavior song song với cấu hình chứng chỉ; rotation có thể làm connection reset vào thời điểm khó dự đoán.

## 35. Secrets trong CI/CD và triển khai

Đề xuất pipeline:

1. **Source**: không có password/private key artifacts.
2. **Static scan**: kiểm secret patterns, credentials in Git history và dependencies.
3. **Build**: không copy production keystore/private key vào image.
4. **Deploy**: workload identity/mount từ secret store, policy riêng từng environment.
5. **Startup**: load profile, kiểm aliases/certificates và fail readiness nếu thiếu.
6. **Rotation**: nhận version mới, tạo profile mới, thử handshake/signature.
7. **Observability**: theo dõi expiry, trust failures, secret lookup errors.
8. **Incident**: revoke/rotate nếu secret lộ, xóa bản sao logs/artifacts theo policy.

### 35.1. Nếu mật khẩu đã bị commit trước đây

Xóa literal trong commit hiện tại **không đủ**. Cần xem như bí mật đã có thể bị lộ:

- Thu hồi/rotate password hoặc key/certificate tùy loại compromise.
- Kiểm ảnh hưởng đến đối tác, tài khoản và tenant.
- Rà soát logs, CI artifacts, backups, copied repos.
- Điều tra theo quy trình security incident.
- Chỉ cân nhắc chỉnh Git history nếu tổ chức cho phép; vẫn giả định người khác có thể đã lấy được bản cũ.

### 35.2. Build không nên phụ thuộc secrets production

Unit/contract tests nên dùng test-only keys, fake secret provider hoặc isolated test vault. Nếu integration test cần PKI thật của sandbox, chỉ cấp runner quyền tối thiểu và không lưu secret dưới dạng artifact. Không yêu cầu mọi developer có quyền production secret chỉ để chạy Gradle/Maven build.

## 36. Những anti-pattern phổ biến

### 36.1. Đặt store password trong `application.yml` commit lên Git

**Sửa:** giữ secret reference trong config; secret value được cấp ở runtime theo workload identity.

### 36.2. Đặt private key và password vào cùng container image

**Sửa:** inject/mount qua cơ chế quản trị, giảm quyền file và khả năng trích xuất image.

### 36.3. Nhầm password store và password private-key entry

**Sửa:** phân biệt `KeyStore.load` và `KeyManagerFactory.init`/`KeyStore.getKey`; kiểm provider và test cả hai.

### 36.4. Dùng một secret cho TLS, WSS4J, HTTP Basic và proxy

**Sửa:** tách theo **purpose, environment, partner, lifecycle và quyền truy cập**.

### 36.5. Cứ lỗi truststore thì bật trust-all

**Sửa:** kiểm CA chain/SAN/trust anchor và certificate renewal; không tắt xác thực server.

### 36.6. Đọc secret manager path từ SOAP Header chưa xác thực

**Sửa:** ánh xạ alias/user/partner bằng configuration đáng tin, kiểm identifier allowlist.

### 36.7. Log `KeyStore.load` exception nguyên văn vào SOAP Fault

**Sửa:** public error chung, internal diagnostics có kiểm soát, không lộ file path/password/source endpoint.

### 36.8. Coi file PKCS#12 có password là đủ bảo vệ

**Sửa:** ACL, secret management, integrity, audit, rotation, không đưa file vào repo/artifacts.

### 36.9. Đổi keystore file rồi nghĩ SSLContext tự reload

**Sửa:** rebuild crypto/client profile hoặc dùng reload mechanism đã kiểm chứng.

### 36.10. Coi xóa char[] là xóa hết secret

**Sửa:** hiểu giới hạn JVM/callback String, giảm copies/lifetime, hạn chế heap dumps và sử dụng HSM khi cần.

### 36.11. Dùng cùng mutable WebServiceTemplate cho nhiều partners

**Sửa:** immutable/isolated credential profiles, approved routing và controlled cutover.

### 36.12. Chỉ test JAXB SOAP request mà không test TLS/WS-Security

**Sửa:** có integration tests cho certificate trust, key alias, signature, SOAP Fault và authorization.

## 37. Quy trình triển khai từng bước

1. **Đọc WSDL/XSD và security policy**: có yêu cầu HTTPS, mTLS, UsernameToken, XML Signature/Encryption hay không?
2. **Lập inventory secret material**: store passwords, key passwords, trust anchors, private keys, HSM PIN, HTTP/proxy credentials.
3. **Gán purpose và owner**: origin/partner/environment, nơi dùng, thời hạn, rotation plan.
4. **Chọn kho khóa**: PKCS12/JKS/PEM/PKCS11/KMS phù hợp stack và yêu cầu private key non-exportable.
5. **Tạo artifacts/aliases tin cậy**: certificate chain, SAN/EKU và algorithms đúng policy.
6. **Không commit secrets**: chỉ lưu logical references và cấu hình không nhạy cảm cần thiết.
7. **Thiết kế ManagedSecretSource**: workload identity, allowlist, least privilege, timeout, audit và fail-closed.
8. **Nạp Java KeyStore** bằng `char[]` tạm và xóa buffer sau khi tạo profile.
9. **Tạo TLS profile**: KeyManagerFactory, TrustManagerFactory, SSLContext; test hostname/chain.
10. **Tạo WS-Security profile**: Crypto, signing/decryption alias, callback và algorithm/reference policy.
11. **Tạo WebServiceTemplate/HTTP sender** cho từng partner, không mutate global credentials.
12. **Viết unit tests** cho secret lookup, zeroization, wrong password/alias.
13. **Viết integration tests** cho mTLS handshake, XML Signature verification và SOAP response/Fault.
14. **Kiểm CI/CD** không xuất secret/PKCS#12/private key vào image, logs hoặc artifacts.
15. **Thiết lập rotation/expiry monitoring** và runbook cho partner certificate renewal.
16. **Diễn tập sự cố**: vault outage, key leak, truststore tampering, certificate expired, partial rollout.
17. **Kiểm interoperability** với Java/JAXB và .NET/ESB/sandbox đối tác dưới cùng security policy.

## 38. Bài tập thực hành

### Bài tập 1 — Phân biệt các mật khẩu

Cho một SOAP client mTLS + WS-Security signature với identity PKCS#12, signing PKCS#12 và truststore. Liệt kê rõ **store password, key-entry password, truststore password, HTTP password, UsernameToken secret**; cho biết Java/Spring-WS/WSS4J API nào dùng từng loại.

### Bài tập 2 — Dùng `ManagedSecretSource`

Tạo fake provider chỉ chấp nhận ba logical refs được provision. Dùng `SecretLease` trả `char[]` và kiểm after-close zeroization. Thử ref bất kỳ do request cung cấp và đảm bảo không truy cập provider.

### Bài tập 3 — Đọc PKCS#12

Tạo test PKCS#12 có alias `client-mtls-test-v1`. Đọc bằng `SecureKeyStores.loadPkcs12`, kiểm `isKeyEntry` và certificate validity. Thử sai store password, sai key-entry password. Không ghi password vào source production.

### Bài tập 4 — Kết nối mTLS

Tạo local TLS test service yêu cầu client certificate. Gắn `SSLContext` ở `JdkHttpClientMessageSender` và gọi SOAP operation thử nghiệm. Thử đúng CA/alias, sai hostname, certificate hết hạn và truststore không đúng.

### Bài tập 5 — Ký SOAP XML

Dùng WSS4J ký SOAP Body bằng một signing alias test. Callback lấy key password từ managed source. Kiểm receiver chỉ chấp nhận message có chữ ký/certificate đúng trust policy; sửa Body rồi xác minh bị từ chối.

### Bài tập 6 — Rotation song song

Tạo profile v1/v2 và mô phỏng 50 requests đồng thời. Hoán đổi profile giữa các requests; bảo đảm mỗi request dùng một profile nhất quán, không trộn certificate/alias/password.

### Bài tập 7 — Vault outage

Mô phỏng secret source timeout/403. Đảm bảo fail closed, không tự dùng mật khẩu demo, log chỉ category/correlation ID và readiness phản ánh lỗi khởi tạo.

### Bài tập 8 — CI security audit

Kiểm một repository sandbox có test credentials giả. Tạo quy trình quét secrets, xác minh image không chứa `.p12` có private key hoặc plaintext password, kiểm env/log redaction. Không sử dụng credential production trong bài tập.

## 39. Checklist review trước production

- [ ] XSD/WSDL, SOAPAction và security policy nêu rõ TLS/mTLS/WS-Security requirements.
- [ ] Phân biệt store password, key-entry password, truststore password, HTTP/UsernameToken secrets.
- [ ] Không có password/private key production trong Git, source, build artifacts hay container image.
- [ ] Mọi secret values được cung cấp bởi nguồn quản lý qua workload identity, access control và audit.
- [ ] Chỉ lưu secret refs/alias trong cấu hình được review; không suy refs từ dữ liệu SOAP chưa xác thực.
- [ ] KeyStore type và JDK/provider được chỉ định rõ; đã test PKCS12/JKS semantics.
- [ ] Đường dẫn keystore/truststore thuộc trusted config, file permissions đủ chặt.
- [ ] `KeyStore.load` và `KeyManagerFactory.init` dùng đúng secret theo mục đích.
- [ ] SecretLease hoặc cơ chế tương đương giới hạn lifetime và zeroize caller arrays.
- [ ] Nhận thức được String/JCA heap copies không thể xóa tuyệt đối.
- [ ] TLS SSLContext được cấu hình trust chain, hostname validation, EKU/SAN policy phù hợp.
- [ ] Không có trust-all manager hoặc hostname verifier luôn true.
- [ ] mTLS identity và WS-Security signing identity có purpose/alias rõ.
- [ ] WSS4J Crypto/callback dùng đúng key alias, key-entry password, SIGNATURE/DECRYPT usage.
- [ ] Không nhầm CallbackHandler với việc verify signature/trust certificate hoặc domain authorization.
- [ ] HTTP Basic/proxy credentials tách khỏi keystore và WS-Security secrets.
- [ ] Có rotation riêng cho store password, key-entry password, keypair/certificate và truststore.
- [ ] Profile mới được test trước cutover; existing connections và đồng thời được xử lý an toàn.
- [ ] Cache có TTL/revocation và không trả shared mutable char[] cho nhiều callers.
- [ ] Multi-partner profiles tách credential scope, endpoint routing và trust policy.
- [ ] Certificate expiry, chain, key usage và active endpoint identity được theo dõi.
- [ ] SOAP Fault/log không lộ password, private key, secretRef nhạy cảm hoặc stack traces.
- [ ] CI/CD không đóng gói production key material; test dùng sandbox secrets.
- [ ] Unit tests kiểm source lookup, wrong password, alias, zeroization và fail-closed.
- [ ] Integration tests kiểm TLS/mTLS, SOAP Signature/Encryption, trust, partner interop.
- [ ] Có runbook khi secret manager outage, certificate expired hoặc private key compromise.

## 40. Tài liệu tham khảo

- [Oracle Java — KeyStore API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html): `load`, entries, alias, protected keys và key store types.
- [Oracle Java — KeyManagerFactory API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): cấp private keys/identities cho TLS.
- [Oracle Java — TrustManagerFactory API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): xác minh TLS peer chains.
- [Oracle Java — SSLContext API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLContext.html): tạo TLS context từ key/trust managers.
- [Oracle Java — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TLS/mTLS, keystores, key manager/trust manager và certificate verification.
- [Spring Web Services — Reference](https://docs.spring.io/spring-ws/reference/): `WebServiceTemplate`, HTTP senders và WS-Security integration.
- [Spring-WS — Wss4jSecurityInterceptor API](https://docs.spring.io/spring-ws/docs/4.0.6/api/org/springframework/ws/soap/security/wss4j2/Wss4jSecurityInterceptor.html): Crypto, signing aliases và validation configuration.
- [Apache WSS4J — User Guide](https://ws.apache.org/wss4j/user_guide.html): security actions, Crypto, callback usages và signature/decryption.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): inventory, secret source, rotation và audit.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): certificate validation và TLS hardening.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): access control, encoding và cung cấp secrets cho workloads.
- [OASIS — WS-Security 1.1.1](https://docs.oasis-open.org/wss-m/wss/v1.1.1/os/wss-SOAPMessageSecurity-v1.1.1-os.html): message security, signature/encryption và token processing.

Các ví dụ Java dùng ngôn ngữ Java 17+, Spring-WS 4.x và WSS4J 2.x khi có liên quan. **Tham chiếu API cần được đối chiếu với đúng phiên bản Spring Framework, JDK, provider, HSM và security policy thực tế**; phần code là ví dụ kiến trúc/minh họa, không phải một ứng dụng hoàn chỉnh có thể deploy chỉ bằng copy-paste.

## 41. Tổng kết

**Quản lý mật khẩu kho khóa không chỉ là thay một chuỗi hardcoded bằng một biến môi trường.** Một SOAP integration an toàn phải phân biệt private key, certificate, store password, key-entry password, truststore, HSM PIN, HTTP credentials và UsernameToken shared secret; mỗi loại có purpose, quyền truy cập và vòng đời riêng.

Trong Java, `KeyStore.load(...)`, `KeyManagerFactory.init(...)`, `TrustManagerFactory.init(...)` và `SSLContext.init(...)` giúp xây TLS/mTLS profile từ material đã được cấp. Trong **Spring Web Services**, `WebServiceTemplate` dùng HTTP sender với profile TLS, còn WSS4J dùng `Crypto`, key alias và callback để ký/giải mã SOAP. Chúng không tự thay thế nhau.

Hãy đưa **secret values ra khỏi source/Git/images/logs**, nạp chúng qua một managed provider có allowlist và least privilege, dùng `char[]` có scope khi API hỗ trợ, hạn chế bản sao, bảo vệ certificate integrity, quản lý rotation bằng immutable client/security profiles và **fail closed** khi bí mật không khả dụng. Chỉ sau khi kiểm thử PKCS#12, TLS/mTLS, WS-Security, lỗi, concurrency và interoperability thực tế mới có thể coi một tích hợp **SPRING_WEB_SERVICES** ổn định và sẵn sàng vận hành.
