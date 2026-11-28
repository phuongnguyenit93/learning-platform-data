# Định dạng lưu khóa, alias và lựa chọn khóa theo mục đích

Trong một hệ thống tích hợp SOAP doanh nghiệp, câu hỏi “ứng dụng dùng certificate nào?” chưa đủ chính xác. Một Java keystore có thể chứa **nhiều khóa riêng**, **nhiều chứng chỉ công khai** và các **alias** phục vụ những mục đích rất khác nhau: chứng chỉ TLS của server, chứng chỉ mTLS của client, khóa ký WS-Security, chứng chỉ đối tác dùng để mã hóa SOAP và khóa riêng để giải mã phản hồi. Một alias hợp lệ về cú pháp nhưng trỏ sai entry hoặc sai mục đích vẫn có thể khiến handshake thất bại, SOAP Fault `FailedCheck` hoặc giải mã thất bại.

Bài **“Định dạng lưu khóa, alias và lựa chọn khóa theo mục đích”** thuộc chương **Chứng chỉ và khóa** của module `SPRING_WEB_SERVICES`. Bối cảnh là phát triển SOAP **contract-first** bằng Spring Web Services: thiết kế XSD/WSDL, JAXB, `@Endpoint`, `WebServiceTemplate`, SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích với các hệ thống Java, .NET, legacy.

**Mục tiêu học tập:** nhận diện các định dạng JKS, PKCS#12, PEM và các keystore phụ thuộc provider; phân biệt private key/certificate/trust anchor; hiểu alias là **định danh cục bộ của một entry** chứ không phải danh tính bảo mật toàn cục; chọn đúng vật liệu khóa cho TLS, mTLS, ký, xác minh chữ ký, mã hóa và giải mã SOAP; kiểm tra bằng `keytool`/OpenSSL/Java; xây dựng chính sách xoay khóa và test cả positive lẫn negative.

Các tên alias, đường dẫn, mật khẩu và endpoint dưới đây chỉ là **dữ liệu giả/lab**. Không đưa private key thật, mật khẩu hay PFX production vào repository, ticket, log hoặc tài liệu học tập. API Spring-WS được minh họa theo dòng **4.1.x/WSS4J 2.x**, phải đối chiếu đúng JAR, JDK và security provider đang chạy trước khi áp dụng.

## 1. Một certificate không đồng nghĩa với một private key

Trước khi bàn về định dạng file, hãy xác định những đối tượng thực sự được lưu:

| Đối tượng | Chứa gì? | Có thể chia sẻ với đối tác? | Dùng trong trường hợp nào? |
| --- | --- | --- | --- |
| **Private key** | Phần bí mật của cặp khóa bất đối xứng. | **Không**; phải bảo vệ bằng keystore/HSM/secret controls. | Ký SOAP, giải mã khóa phiên, xác thực TLS/mTLS ở phía chủ sở hữu. |
| **Public key** | Phần công khai tương ứng private key. | Có thể, theo policy. | Xác minh chữ ký hoặc mã hóa dữ liệu cho chủ sở hữu private key. |
| **X.509 certificate** | Public key + subject/issuer, thời hạn, extensions, chữ ký CA. | Thường **có thể chia sẻ**; không bao gồm private key. | Gắn public key với identity, xác thực chuỗi tin cậy/mục đích sử dụng. |
| **Certificate chain** | Leaf certificate và intermediate CAs, có thể kèm root theo đóng gói. | Có thể chia sẻ các certificate công khai. | Dựng/kiểm chứng đường tin cậy tới trust anchor. |
| **Trust anchor** | CA/khóa được bên nhận chủ động tin cậy. | Bản public có thể chia sẻ; quyết định *tin ai* là cấu hình riêng. | Kiểm tra certificate chain của TLS peer hoặc WS-Security signer. |
| **Secret/symmetric key** | Khóa bí mật chung như AES key. | Không chia sẻ tùy tiện; chỉ qua key management được duyệt. | Một số cơ chế mã hóa/đối xứng, không thay X.509 key pair. |

Một chứng chỉ `.cer` hoặc `.crt` đơn lẻ thường chỉ chứa public certificate. Chỉ copy nó vào client **không tạo được khả năng ký**. Để ký SOAP hoặc làm mTLS identity, bên ký cần **private key tương ứng** và chứng chỉ/chain phù hợp, hoặc một key handle không xuất được từ HSM.

### 1.1. Khóa nào thực hiện từng phép toán?

~~~mermaid
flowchart LR
    A["Bên A: Private Key A"] -->|"Ký XML"| S["SOAP Signature"]
    S -->|"Gửi kèm KeyInfo/Cert theo policy"| B["Bên B: Public Cert A + trust policy"]
    B -->|"Xác minh chữ ký"| V["Đúng signer + integrity, nếu trust/authorization đạt"]

    C["Bên A: Public Cert B"] -->|"Mã hóa khóa phiên"| E["SOAP EncryptedData/EncryptedKey"]
    E -->|"Gửi"| D["Bên B: Private Key B"]
    D -->|"Giải mã khóa phiên và payload"| P["Plaintext xử lý có kiểm soát"]
~~~

**Ký và mã hóa có hướng ngược nhau:**

- **Ký outbound:** dùng **private key của người gửi**. **Xác minh inbound:** dùng public certificate của người gửi và kiểm tra trust/identity/policy.
- **Mã hóa outbound cho B:** dùng **public certificate của B**. **Giải mã inbound tại B:** dùng **private key của B**.
- **TLS server authentication:** server trình chứng chỉ/chain và chứng minh sở hữu private key; client dùng trust policy để xác thực server.
- **mTLS client authentication:** client cũng phải có private key/chứng chỉ identity; server kiểm tra certificate chain và quyền client.

Từ đây có thể thấy một ứng dụng SOAP đôi khi cần **nhiều key stores và trust stores độc lập**. Việc chứa tất cả trong một file không tự bảo đảm chọn đúng certificate.

## 2. Các định dạng lưu khóa: PKCS#12, JKS, PEM, JCEKS, BCFKS

Trong Java, `java.security.KeyStore` là **API trừu tượng**. Các `KeyStore` providers thực thi cách đọc/lưu theo từng **type**. Phần mở rộng của file là **quy ước**, còn type thực tế mới quyết định có parse được hay không.

### 2.1. Bảng so sánh định dạng

| Định dạng | Phần mở rộng thường gặp | Có thể chứa | Khi nào dùng | Điểm cần nhớ |
| --- | --- | --- | --- | --- |
| **PKCS#12** (`PKCS12`) | `.p12`, `.pfx` | Private key + certificate chain; certificate entries, tùy provider. | Ưu tiên cho trao đổi Java/.NET/OpenSSL và phần lớn Java runtime mới. | Chuẩn phổ biến; cần kiểm tra alias/password/thuật toán tương thích. |
| **JKS** (`JKS`) | `.jks` | Private keys + certificate chains và trusted certificates. | Tương thích hệ thống Java legacy. | Định dạng đặc thù Java; với ứng dụng mới thường ưu tiên PKCS#12. |
| **PEM** | `.pem`, `.crt`, `.key` | Một hoặc nhiều blocks `CERTIFICATE`/`PRIVATE KEY` tùy file. | Trao đổi với OpenSSL, ingress, proxy, Kubernetes. | **Không phải** Java `KeyStore` type chung; không mặc định `KeyStore.getInstance("PEM")`. |
| **JCEKS** | `.jceks` | Private keys, trusted certs và secret key entries theo provider. | Một số hệ thống Java cũ quản lý secret keys. | Không mặc định dùng cho thiết kế mới; cân nhắc crypto/provider và thuật toán bảo vệ. |
| **BCFKS** | `.bcfks` | Key/cert entries theo Bouncy Castle provider. | Môi trường chọn Bouncy Castle/BC FIPS và chính sách tương ứng. | Cần provider, cấu hình, compatibility test; không phải chuẩn built-in mọi JDK. |
| **PKCS#11 token/HSM** | Không nhất thiết là file | Key handles, certificate objects tùy token. | Khóa không được xuất; HSM/USB token/cloud HSM gateway. | `PKCS11` là provider/token interface; không đồng nghĩa một `.p12` trên đĩa. |

Theo Java `KeyStore` API, **PKCS12** là một type tiêu chuẩn được nền tảng Java hỗ trợ; `JKS` phụ thuộc implementation phổ biến của JDK. Trên các JDK hiện đại, `KeyStore.getDefaultType()` thông thường là **`pkcs12`** (Java 9+), nhưng giá trị có thể được cấu hình trong `java.security`. Đừng suy từ `file.p12` mà bỏ `-storetype PKCS12` khi đang thao tác với môi trường legacy.

### 2.2. PEM là encoding/container khác nghĩa PKCS#12

PEM là biểu diễn văn bản Base64 có đánh dấu đầu/cuối block, ví dụ dữ liệu giả rút gọn:

~~~text
-----BEGIN CERTIFICATE-----
...base64 certificate bytes...
-----END CERTIFICATE-----
~~~

Một private key PEM có thể được ghi bằng `-----BEGIN PRIVATE KEY-----` (PKCS#8) hoặc `-----BEGIN ENCRYPTED PRIVATE KEY-----`; các dạng legacy như `RSA PRIVATE KEY` cũng tồn tại. **Không trộn certificate PEM với private key PEM** rồi gọi cả hai là “certificate file”. Một người sở hữu `cert.pem` công khai **không** sở hữu `key.pem`.

PKCS#12 là binary keystore/container có mật khẩu và các entries. Khi đối tác gửi `client.pfx`, hãy xác nhận file có private key entry hay chỉ certificate. Không dùng `keytool -importcert` trên một certificate PEM để kỳ vọng tạo private key entry.

### 2.3. Không có định dạng nào tự thay chính sách bảo vệ khóa

- File PKCS#12 với mật khẩu yếu hoặc file permissions mở rộng vẫn có nguy cơ rò private key.
- JKS/PKCS#12 sử dụng các thuật toán bảo vệ/password schemes tùy JDK/provider; không tự đánh giá an toàn dựa trên extension.
- Một file PEM encrypted vẫn có thể bị lộ nếu password được hardcode cùng repository.
- HSM giảm nguy cơ **xuất private key**, nhưng vẫn cần kiểm soát quyền sử dụng key, audit, rotation và approval.
- Keystore chứa public certificates không đồng nghĩa tất cả certificates bên trong đều là trusted anchors.

### 2.4. Định dạng vật lý khác với vai trò keystore/truststore

**Keystore** thường được dùng theo nghĩa “nguồn identity/private key của chính ứng dụng”. **Truststore** thường chứa public certificates hoặc CA được ứng dụng cho phép tin cậy. Tuy nhiên, hai từ này là **vai trò cấu hình**, không phải hai file format riêng:

~~~text
client-identity.p12   [PKCS12] PrivateKeyEntry của SOAP client
partner-trust.p12     [PKCS12] trustedCertEntry của CA/cert đối tác
soap-signing.p12      [PKCS12] PrivateKeyEntry của người gửi SOAP
recipient-certs.p12   [PKCS12] public cert dùng để Encrypt outbound
~~~

Một file có thể chứa cả private entries lẫn trusted cert entries, nhưng tách theo **purpose, quyền truy cập và vòng đời** thường an toàn, dễ audit hơn. Đặc biệt không nên chép private key vào mọi ứng dụng chỉ để tất cả có “cùng keystore”.

## 3. Entry và alias: tên cục bộ phải khớp **loại entry**

Java `KeyStore` quản lý các entry bằng một chuỗi **alias**. Alias giúp Java/WSS4J tìm entry, **không phải** tên subject của certificate, hostname TLS hay `wsse:UsernameToken` theo một quy tắc chung.

### 3.1. Ba entry types trong Java

| Entry | Java API | Có private/secret key? | Chọn dùng cho |
| --- | --- | --- | --- |
| **PrivateKeyEntry** | `KeyStore.PrivateKeyEntry` | **Private key** + certificate chain. | XML Signature outbound, XML decryption inbound, TLS/mTLS identity. |
| **TrustedCertificateEntry** | `KeyStore.TrustedCertificateEntry` | **Không**, chỉ public certificate. | Tin cậy certificate/CA khi verify hoặc lookup recipient public cert khi Encrypt. |
| **SecretKeyEntry** | `KeyStore.SecretKeyEntry` | **Secret/symmetric key**. | Một số kịch bản symmetric crypto; phải kiểm tra type/provider và WSS4J callback. |

Không tự coi mọi `isKeyEntry(alias) == true` là RSA/ECDSA private key: `isKeyEntry` có thể đúng cả với **SecretKeyEntry**. Muốn ký XML bằng khóa bất đối xứng, cần xác minh entry thực sự cung cấp **PrivateKey + X.509 chain**.

### 3.2. Ví dụ một inventory keystore có nhiều aliases

~~~text
File: service-identity.p12          Type: PKCS12

Alias                         Entry type          Mục đích dự kiến
----------------------------  ------------------  ------------------------------
soap-signing-2026             PrivateKeyEntry     Ký SOAP outbound
tls-client-orders             PrivateKeyEntry     Xác thực mTLS tới Orders
soap-decrypt-2025             PrivateKeyEntry     Giải mã dữ liệu cũ khi rotation
partner-encryption-2026       trustedCertEntry    Mã hóa SOAP gửi cho đối tác
partner-root-ca               trustedCertEntry    Trust anchor đối tác (nếu policy)
~~~

Đây là **minh họa inventory**, không phải output cố định của `keytool`. Tên alias `partner-root-ca` có ý nghĩa quản trị nhưng **không làm certificate tự trở nên đáng tin**: người vận hành phải xác minh fingerprint/chain/issuer và phạm vi tin cậy trước khi import.

### 3.3. Những tính chất của alias cần lưu ý

- Alias là **khóa tra cứu nội bộ** của một keystore. Tên `soap-signing-2026` không xuất hiện trong WSDL/XSD theo mặc định.
- Alias có thể **khác** certificate subject, Subject Alternative Name (SAN), serial number và certificate fingerprint.
- Tính phân biệt **chữ hoa/thường** phụ thuộc provider; Java API khuyến nghị tránh hai aliases chỉ khác case.
- Alias **không phải secret**, nhưng có thể lộ metadata hạ tầng nếu ghi ra log công khai.
- Cùng tên alias ở hai keystores khác nhau **không có nghĩa** cùng private/public key.
- Một alias có thể được gán lại/đổi key khi rotation; cần kiểm tra fingerprint/key identifiers của certificate được chọn.
- Khi đổi từ JKS sang PKCS#12, **không mặc định** tool giữ nguyên mọi alias/entry passwords/attribute như ý trong mọi provider. Phải kiểm tra hậu chuyển đổi.

### 3.4. Chọn theo purpose, không theo “alias đầu tiên”

Một số lỗi thực tế:

~~~text
securementUsername = "partner-encryption-2026"
securementActions  = Signature
~~~

Alias đó trong inventory là `trustedCertEntry`, **không có private key**; vì vậy không thể dùng để ký outbound. Ngược lại:

~~~text
securementEncryptionUser = "soap-signing-2026"
~~~

có thể dùng public cert từ entry của chính mình để mã hóa, khiến **đối tác không giải mã được** nếu không sở hữu private key đó. Với Encrypt outbound cho đối tác, phải chọn **certificate public của recipient**.

## 4. Kiểm kê keystore bằng keytool và OpenSSL, không làm lộ bí mật

Trước khi viết cấu hình Spring-WS, hãy **xác minh những gì thực sự nằm trong file**. Không dựa vào tên `client.p12`, lời mô tả của nhà cung cấp hay mỗi thuộc tính `alias` trong file application configuration.

### 4.1. Liệt kê tất cả entries

`keytool` là công cụ của JDK. Các lệnh sau được viết để **hỏi mật khẩu tương tác**, không ghi `-storepass` hay `-keypass` ngay trên command line:

~~~bash
# Xem keystore PKCS#12. Chạy trong môi trường được phép.
keytool -list -v -keystore client-identity.p12 -storetype PKCS12

# Xem chính xác một alias:
keytool -list -v -keystore client-identity.p12 -storetype PKCS12 -alias soap-signing-2026

# Legacy JKS:
keytool -list -v -keystore legacy-signing.jks -storetype JKS
~~~

Trong output thường thấy:

~~~text
Alias name: soap-signing-2026
Entry type: PrivateKeyEntry
Certificate chain length: 2
Owner: CN=orders-signing.example.test, O=Example
Issuer: CN=Example Issuing CA, O=Example
Valid from: ... until: ...
SHA256: ... (fingerprint)
~~~

Các dòng trên chỉ là **minh họa**. `keytool -list -v` có thể in subject, serial, certificate extensions và chain. Chỉ lưu output trong hệ thống quản trị được phân quyền; không copy nguyên output có thông tin nội bộ vào issue công khai.

Cần xem **entry type, alias, certificate chain, fingerprint, thời hạn, key algorithm và extensions**, chứ không chỉ có/không có alias. Lệnh `-list` không kiểm tra được mọi handshake/authentication policy; nó chứng minh keystore đang chứa gì.

### 4.2. Tại sao không nên nhập mật khẩu trực tiếp trên CLI?

Ví dụ cần **tránh**:

~~~text
keytool -list -keystore production-identity.p12 -storepass DO_NOT_PUT_PASSWORD_HERE
~~~

Mật khẩu có thể lộ qua shell history, process listing, CI logs và màn hình ghi lại lệnh. Chạy `keytool` tương tác hoặc dùng secret integration do môi trường chuẩn hóa; không copy nguyên credential vào tài liệu.

Nếu hệ thống CI bắt buộc chạy không tương tác, sử dụng secret manager/credential helper, thiết kế cleanup và kiểm soát visibility. Một số phiên bản `keytool` có các lựa chọn như `-storepass:env`/`-storepass:file`; chúng vẫn cần đánh giá quyền đọc, log masking, lifecycle của environment/file và chính sách nội bộ. **Không để password plaintext nằm cùng file keystore trong repository.**

### 4.3. Kiểm tra public certificate bằng OpenSSL

Đối với certificate **công khai** đã được duyệt:

~~~bash
openssl x509 -in partner-public.pem -noout -subject -issuer -dates -fingerprint -sha256

# Xem thêm extensions nếu cần:
openssl x509 -in partner-public.pem -noout -text
~~~

Các thuộc tính cần đọc:

- **Subject / SAN:** mô tả định danh certificate theo profile; với TLS hostname verification hiện đại, kiểm tra DNS SAN chứ không chỉ CN.
- **Issuer / chain:** certificate được CA nào ký; kiểm tra cả intermediate chain và trust anchor.
- **Validity:** `notBefore` và `notAfter` so với thời gian hệ thống.
- **KeyUsage / ExtendedKeyUsage (EKU):** có phù hợp TLS server/client hay chữ ký/mã hóa theo chính sách không?
- **Public key algorithm/size:** ví dụ RSA hoặc EC; phải phù hợp cơ chế ký/mã hóa mà SOAP stack và đối tác hỗ trợ.
- **SHA-256 fingerprint:** hỗ trợ đối chiếu certificate đúng identity khi import/rotation, nhưng **không phải** bằng chứng authorization duy nhất.

Để kiểm tra PKCS#12 có cấu trúc đọc được bằng OpenSSL, có thể dùng:

~~~bash
openssl pkcs12 -in client-identity.p12 -info -noout
~~~

Lệnh này có thể yêu cầu password; tùy OpenSSL/provider phiên bản, một số thuật toán legacy có thể cần cấu hình tương thích đặc biệt. Không kết luận password sai chỉ vì OpenSSL mới từ chối một PFX cũ dùng thuật toán không còn bật; nhưng cũng **không hạ chuẩn crypto** trong production để tiếp tục dùng vật liệu lỗi thời mà chưa được đánh giá.

**Tránh xuất private key dưới dạng PEM plaintext** để “kiểm tra nhanh”. Việc đó tạo thêm một bản private key trên filesystem, có thể vào backup, cache, clipboard hoặc log. Nếu phải di chuyển private key giữa keystores, dùng công cụ được duyệt, lưu tạm trong vùng bảo vệ và xóa an toàn theo chính sách, hoặc dùng HSM non-exportable key nếu có.

### 4.4. Phân biệt export certificate và export private key

`keytool -exportcert` **xuất certificate công khai**, không phải private key:

~~~bash
keytool -exportcert -rfc -keystore client-identity.p12 -storetype PKCS12 -alias soap-signing-2026 -file soap-signer-public.pem
~~~

Kết quả `soap-signer-public.pem` cho đối tác **chỉ nên chứa public certificate**. Đối tác cần xác minh fingerprint/chain qua kênh tin cậy trước khi quyết định trust.

Nếu certificate cần được thêm vào truststore, lệnh `-importcert` có thể tạo **TrustedCertificateEntry**:

~~~bash
keytool -importcert -keystore partner-trust.p12 -storetype PKCS12 -alias partner-signing-ca -file partner-ca-public.pem
~~~

Trước khi import certificate vào truststore, phải **xác minh fingerprint và phạm vi tin cậy** từ một kênh tin cậy độc lập. Đừng tự động dùng `-noprompt` cho một certificate vừa tải trên Internet; import làm thay đổi **ai được tin cậy**. Chỉ import đúng leaf/CA theo trust model, không tin một CA công khai hoặc root không liên quan chỉ để test pass.

### 4.5. Tạo key pair trong môi trường lab

Để học cấu trúc `PrivateKeyEntry`, có thể tạo **chứng chỉ tự ký chỉ dùng trong lab**:

~~~bash
keytool -genkeypair -alias soap-sign-lab -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 30 -dname "CN=soap-sign-lab.example.test,O=Example Lab" -keystore soap-lab.p12 -storetype PKCS12
~~~

Đây **không phải** cách phát hành certificate production. Trong production, khóa/chứng chỉ có thể được cấp qua PKI/CSR/CA hoặc HSM với chính sách, thời hạn, EKU/KeyUsage và bảo vệ key material tương ứng. Một key pair lab dùng cho ký XML **không tự thích hợp** làm TLS server certificate; hostname SAN, EKU và chain có thể không đáp ứng.

### 4.6. Chuyển đổi JKS sang PKCS#12

Một thao tác migration thường gặp:

~~~bash
keytool -importkeystore -srckeystore legacy-signing.jks -srcstoretype JKS -destkeystore signing-migrated.p12 -deststoretype PKCS12
~~~

Lệnh cần được thực hiện trong môi trường được phân quyền với backup/rollback và password prompts thích hợp. Với keystore có nhiều aliases, hãy xem các lựa chọn `-srcalias` và `-destalias` để chỉ chuyển đúng entry theo policy. Sau chuyển đổi **bắt buộc** so sánh:

~~~text
Before: alias, entry type, certificate chain, fingerprint
After:  alias, entry type, certificate chain, fingerprint
~~~

và xác minh private key **thực sự dùng được** trong test ký/giải mã/TLS theo mục đích. Hành vi key password riêng so với store password có thể khác theo provider/PKCS#12 implementation. Đừng tự đổi cùng lúc định dạng, alias, mật khẩu, thuật toán và SOAP policy rồi khó phân biệt nguyên nhân thất bại.

## 5. Kiểm tra alias bằng Java KeyStore API

Việc kiểm kê trong startup/test giúp phát hiện cấu hình sai **trước khi có request thật**. Một chương trình có thể kiểm tra alias, entry type, certificate algorithm/validity và chain mà **không cần in private key**.

~~~java
import java.io.InputStream;
import java.security.KeyStore;
import java.security.cert.X509Certificate;
import java.util.Enumeration;

public final class KeyStoreInspector {

    private KeyStoreInspector() {}

    public static void inspect(
            InputStream input,
            char[] storePassword) throws Exception {

        KeyStore store = KeyStore.getInstance("PKCS12");
        store.load(input, storePassword);

        Enumeration<String> aliases = store.aliases();
        while (aliases.hasMoreElements()) {
            String alias = aliases.nextElement();

            String type;
            if (store.entryInstanceOf(
                    alias, KeyStore.PrivateKeyEntry.class)) {
                type = "PRIVATE_KEY";
            } else if (store.entryInstanceOf(
                    alias, KeyStore.SecretKeyEntry.class)) {
                type = "SECRET_KEY";
            } else if (store.entryInstanceOf(
                    alias, KeyStore.TrustedCertificateEntry.class)) {
                type = "TRUSTED_CERT";
            } else {
                type = "OTHER";
            }

            System.out.printf("alias=%s type=%s%n", alias, type);

            if (store.getCertificate(alias) instanceof X509Certificate x509) {
                x509.checkValidity();
                System.out.printf(
                    "  publicKeyAlg=%s chainLength=%d%n",
                    x509.getPublicKey().getAlgorithm(),
                    store.getCertificateChain(alias) == null
                        ? 0 : store.getCertificateChain(alias).length);
            }
        }
    }
}
~~~

**Điều kiện ví dụ:** phương thức `inspect` nhận một `InputStream` do caller đóng và `char[]` password lấy từ nguồn bí mật được quản trị. Nó **không** tự mở đường dẫn từ dữ liệu SOAP request. `checkValidity()` chỉ kiểm tra thời gian hợp lệ, **không phải kiểm tra đường tin cậy hay mục đích EKU**; cần xác thực chain và policy riêng nếu được dùng để quyết định trust.

Đối với runtime thực tế:

- Không dump mọi alias/certificate subject vào log public.
- Tên alias nên theo whitelist cấu hình của ứng dụng, không do request SOAP chọn.
- Nếu dùng private key, chỉ xác nhận entry type và capability/permission ở startup; không log `PrivateKey#getEncoded()` hoặc giá trị key.
- Khi một alias không tồn tại, trỏ sai entry hoặc certificate hết hạn, **fail readiness/startup** theo mức độ nghiêm trọng thay vì chờ đến giao dịch đầu tiên.
- Với keystore PKCS#11/HSM, cách đọc/chọn alias có thể phụ thuộc provider/session và **key có thể không export**; không coi đó là lỗi.

### 5.1. Lấy đúng private key khác với lấy certificate

~~~java
// Trích đoạn trong một method đã có:
// KeyStore store = ...;  (đã load an toàn)
String alias = "soap-signing-2026";

if (!store.entryInstanceOf(alias, KeyStore.PrivateKeyEntry.class)) {
    throw new IllegalStateException(
        "Selected alias has no private key entry");
}

X509Certificate certificate =
    (X509Certificate) store.getCertificate(alias);

// certificate.getPublicKey() chỉ là public key.
// Private key cần quyền và key-entry password riêng.
~~~

Đây là trích đoạn minh họa, không chứa password/private key. Nếu ứng dụng gọi `getKey(alias, keyPassword)` hoặc `getEntry(...)`, phải bảo vệ `char[]` password, giới hạn scope và không ghi lại. Tránh gọi `getKey` chỉ để kiểm tra certificate trong truststore: trusted certificate entry **không có key**.

### 5.2. Vì sao tên alias không thể xác minh danh tính?

Alias `partner-signing` là **label do người quản trị keystore đặt**. Nếu ai đó thay certificate dưới cùng tên alias vào một keystore không được kiểm soát, label vẫn y hệt.

Để xác minh bên gửi, phải kết hợp:

1. Kiểm tra **cryptographic signature** trên đúng phần SOAP đã được ký.
2. Dựng và xác thực **certificate chain/trust anchor** đúng policy.
3. Kiểm tra thời hạn, KeyUsage/EKU và yêu cầu kiểm tra thu hồi nếu chính sách áp dụng.
4. Liên kết **certificate identity** với principal/đối tác có quyền thực hiện operation.
5. Kiểm tra SOAP security policy: timestamp/replay, signed parts, token references và các header cần bảo vệ.

Alias giúp lựa chọn key/cert nội bộ, **không tự là chứng minh identity hoặc authorization**.

## 6. Chọn khóa theo mục đích — bảng quyết định quan trọng nhất

Trước khi viết XML config hoặc Java bean, lập bảng **ai sở hữu private key** và **bên nào thực hiện phép toán**.

| Mục đích | Bên gửi/nhận | Vật liệu khóa bắt buộc | Entry/alias phù hợp | Thuộc cấu hình nào? |
| --- | --- | --- | --- | --- |
| **Ký SOAP outbound** | Người gửi A | **Private key A** và certificate chain A. | `PrivateKeyEntry`, ví dụ `soap-signing-2026`. | WSS4J `securementSignatureCrypto` + `securementUsername` + private key password. |
| **Verify SOAP inbound** | Bên nhận B | Public certificate A và **trust/authorization policy**. | Trusted cert/CA hoặc trust Crypto theo policy. | WSS4J `validationSignatureCrypto`. |
| **Encrypt SOAP outbound cho B** | Người gửi A | **Public certificate B**. | Certificate entry của B, ví dụ `partner-encryption-2026`. | WSS4J `securementEncryptionCrypto` + `securementEncryptionUser`. |
| **Decrypt SOAP inbound ở B** | Bên nhận B | **Private key B** và password/key handle. | `PrivateKeyEntry`, ví dụ `soap-decrypt-2026`. | WSS4J `validationDecryptionCrypto` + password callback. |
| **TLS server identity** | SOAP HTTPS server | Private key server, leaf certificate, chain. | `PrivateKeyEntry`, certificate hợp lệ cho hostname. | HTTPS container/SSLContext, không phải WSS4J signature alias. |
| **Verify TLS server** | HTTPS client | Trust anchors/CA và hostname validation. | `TrustedCertificateEntry`/OS/JDK truststore theo policy. | JSSE `TrustManager`/HTTP sender SSLContext. |
| **mTLS client identity** | SOAP HTTPS client A | Private key/certificate **client A**. | `PrivateKeyEntry`, có EKU clientAuth khi policy yêu cầu. | JSSE `KeyManager`/HTTP sender SSLContext. |
| **Verify mTLS client** | HTTPS server | CA/cert tin cậy của client và identity mapping. | Truststore/CA của mTLS clients. | TLS connector `TrustManager`/authorization. |
| **XML symmetric secret** | Theo SOAP security policy | Secret key và callback/algorithm phù hợp. | `SecretKeyEntry` nếu provider hỗ trợ. | WSS4J symmetric key callback, không mặc định như X.509. |

### 6.1. Sơ đồ hai chiều giữa hai dịch vụ SOAP

~~~mermaid
sequenceDiagram
    participant A as Orders SOAP Client A
    participant B as Payments SOAP Server B

    Note over A: Private signing key A
    Note over A: Public encryption cert B
    Note over B: Trusted signing cert/CA A
    Note over B: Private decryption key B

    A->>A: Sign request bằng private key A
    A->>A: Encrypt Body cho public key B
    A->>B: HTTPS + WS-Security SOAP Envelope
    B->>B: Decrypt bằng private key B
    B->>B: Verify signature/trust của A
    B->>B: Validate XSD/authorization
    B-->>A: SOAP response/Fault theo contract và policy
~~~

Sơ đồ minh họa trách nhiệm, **không cố định thứ tự Encrypt/Signature**: WS-Security policy có thể yêu cầu *sign-then-encrypt* hoặc *encrypt-then-sign* và các signed/encrypted parts khác nhau. Tùy stack, thứ tự hiển thị khi gửi có thể không đồng nhất thứ tự kiểm tra inbound. Cần thống nhất với đối tác qua policy và interoperability tests.

### 6.2. Một chứng chỉ có dùng cho mọi mục đích được không?

Về mặt kỹ thuật, có chứng chỉ/key pair được phát hành với nhiều mục đích, nhưng **không phải khuyến nghị mặc định**. Sử dụng cùng private key cho TLS client, SOAP signing và decryption làm tăng phạm vi ảnh hưởng nếu khóa bị lộ, đồng thời gây khó khăn rotation và phân quyền.

Nên tách theo **purpose** khi khả thi:

~~~text
tls-client-orders-2026       ← private key cho mTLS
soap-sign-orders-2026        ← private key cho WS-Security Signature
soap-decrypt-payments-2026   ← private key cho inbound WS-Encryption
partner-encrypt-payments-v2  ← public certificate của recipient
partner-sign-ca-2026         ← trust anchor / signer trust theo policy
~~~

Một số hệ thống/đối tác có thể áp đặt dùng chung certificate. Khi đó phải đánh giá KeyUsage/EKU, issuer, khả năng thuật toán, lịch rotation và quyền truy cập trước khi chấp nhận ngoại lệ.

### 6.3. Chỉ trùng alias không đủ để tương thích

Ví dụ A và B đều có alias `payments` trong PKCS#12:

~~~text
A: payments → certificate công khai của B năm 2025
B: payments → private key của B năm 2026
~~~

Nếu B đã rotation sang key pair mới mà A vẫn encrypt bằng cert 2025, B chỉ giải mã được **nếu vẫn giữ private key cũ và policy cho phép**. Cùng chuỗi alias không hề bảo đảm public/private keys khớp.

**Đối chiếu certificate fingerprint/public key và lifecycle**, không lấy alias làm căn cứ duy nhất.

### 6.4. Certificate KeyUsage và EKU là điều kiện cần kiểm tra

Một X.509 certificate có thể có extensions:

| Extension | Điều cần hiểu |
| --- | --- |
| `KeyUsage: digitalSignature` | Liên quan phép ký; kiểm tra cùng algorithm và certificate policy. |
| `KeyUsage: keyEncipherment` | Thường có ý nghĩa cho RSA key transport ở profile phù hợp; không suy mọi EC key đều dùng tương tự. |
| `KeyUsage: keyAgreement` | Liên quan một số mô hình thỏa thuận khóa, không đồng nghĩa key transport RSA. |
| `ExtendedKeyUsage: serverAuth` | TLS server authentication khi bên xác minh yêu cầu EKU này. |
| `ExtendedKeyUsage: clientAuth` | TLS client authentication (mTLS) khi policy yêu cầu. |
| `BasicConstraints: CA` | Phân biệt certificate CA có thể ký chứng chỉ con với leaf cert. |

**Không có quy tắc đơn giản “mỗi certificate có một EKU cố định cho mọi trường hợp WS-Security”**: mục đích WS-Security signing/encryption phụ thuộc profile, PKI policy và WSS4J validation. Nhưng khi có KeyUsage/EKU hạn chế, phải **tuân thủ** ý nghĩa đó. Certificate `serverAuth` không tự là lựa chọn hợp lệ để ký mọi SOAP operation.

## 7. WS-Security với Spring-WS: Crypto, alias và callback

Trong Spring-WS 4.1.x, **`org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor`** là adapter tích hợp Apache WSS4J 2.x với client/server SOAP pipeline. Các phép ký, xác minh chữ ký, mã hóa và giải mã dùng `org.apache.wss4j.common.crypto.Crypto`. Spring-WS cung cấp **`CryptoFactoryBean`** để tạo và cấu hình Crypto từ keystore.

Cần tách **ba cấp lựa chọn**:

~~~text
1. Chọn nguồn khóa:
     CryptoFactoryBean
       ├── keyStoreLocation = path/resource
       ├── keyStoreType = PKCS12/JKS/...
       └── keyStorePassword = store-level protection

2. Chọn entry hoặc tiêu chí tìm certificate:
     securementUsername (ký)
     securementEncryptionUser (mã hóa cho recipient)
     KeyInfo/X509 identifiers + trust policy (verify/decrypt)

3. Quyền dùng private key:
     securementPassword hoặc callback handler
       → private key entry password / HSM PIN tùy provider
~~~

**Store password, private key password và alias không phải cùng một giá trị.** Một số PKCS#12 providers có hạn chế về việc dùng password riêng cho từng entry; không nên tùy tiện đổi một trong ba rồi suy lỗi xảy ra ở SOAP layer.

### 7.1. CryptoFactoryBean khai báo đúng định dạng

Javadoc Spring-WS 4.1.4 công bố các setter:

| Setter | Vai trò | Nhầm lẫn cần tránh |
| --- | --- | --- |
| `setKeyStoreLocation(Resource)` | Nguồn keystore cho Crypto. | Không truyền một certificate PEM riêng rồi mong có private key. |
| `setKeyStoreType(String)` | Kiểu vật lý, ví dụ `PKCS12`. | Default từ `KeyStore.getDefaultType()` không luôn là JKS. |
| `setKeyStorePassword(String)` | Mật khẩu mở/kiểm tra store. | Không tự thay được password của private key entry trong mọi provider. |
| `setKeyStoreProvider(String)` | Provider keystore khi cần. | BCFKS/PKCS#11 có thêm ràng buộc/provider. |
| `setDefaultX509Alias(String)` | Alias certificate **mặc định** trong Crypto khi không có key info theo semantics WSS4J. | **Không thay** `securementUsername` khi chọn khóa ký outbound. |
| `setConfiguration(Properties)` | Cấu hình WSS4J Crypto nâng cao. | Có thể ghi đè typed properties; tránh cấu hình cùng một thuộc tính ở hai nơi. |

**Không sử dụng giá trị mặc định mật khẩu do thư viện tài liệu hóa** để triển khai production. Luôn nạp password từ secret manager/hệ thống injection được quản trị và xác thực đường dẫn keystore. Nếu dùng keystore nằm trong `classpath`, nó có thể bị đóng vào JAR/container image: **không nhúng private key production vào image dùng chung**.

### 7.2. Cấu hình ký SOAP outbound bằng private key alias

Ví dụ Spring configuration sau dùng `CryptoFactoryBean` và `Wss4jSecurityInterceptor` trong Spring-WS 4.1.x. Password được đọc từ **cấu hình do môi trường cấp và bảo vệ**, không có literal secret trong source:

~~~java
package com.example.orders.security;

import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.io.FileSystemResource;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;
import org.springframework.ws.soap.security.wss4j2.support.CryptoFactoryBean;

@Configuration
public class SoapSigningConfig {

    @Bean
    public Crypto signingCrypto(Environment env) throws Exception {
        CryptoFactoryBean factory = new CryptoFactoryBean();
        factory.setKeyStoreLocation(
            new FileSystemResource("/run/secrets/soap-signing.p12"));
        factory.setKeyStoreType("PKCS12");
        factory.setKeyStorePassword(
            env.getRequiredProperty("soap.signing.storePassword"));
        factory.afterPropertiesSet();
        return factory.getObject();
    }

    @Bean
    public Wss4jSecurityInterceptor outboundSigner(
            @Qualifier("signingCrypto") Crypto crypto,
            Environment env) {

        Wss4jSecurityInterceptor interceptor =
            new Wss4jSecurityInterceptor();

        interceptor.setSecurementActions("Signature");
        interceptor.setSecurementUsername("soap-signing-2026");
        interceptor.setSecurementPassword(
            env.getRequiredProperty("soap.signing.keyPassword"));
        interceptor.setSecurementSignatureCrypto(crypto);
        interceptor.setSecurementSignatureKeyIdentifier(
            "DirectReference");
        return interceptor;
    }
}
~~~

**Giả định:** secret keys `soap.signing.storePassword` và `soap.signing.keyPassword` được inject qua cơ chế an toàn của deployment; chỉ ứng dụng có quyền mới đọc `/run/secrets/soap-signing.p12`; alias `soap-signing-2026` thực sự là `PrivateKeyEntry`. Path ví dụ phù hợp một kiểu runtime Linux container, cần điều chỉnh trong môi trường khác. `factory.afterPropertiesSet()` là cần thiết vì trong ví dụ ta tự tạo `CryptoFactoryBean` trong method rồi lấy `getObject()`; một `CryptoFactoryBean` được khai báo riêng làm Spring bean sẽ có lifecycle tự quản lý.

**Đây là cấu hình một interceptor cho mục đích ký, chưa gắn vào `WebServiceTemplate`.** Với client, phải đăng ký nó như `ClientInterceptor` của template theo API Spring-WS đang dùng; với endpoint server, đăng ký trong interceptor chain phù hợp. Không để bean tồn tại nhưng không được sử dụng.

`DirectReference` giúp gắn/reference X.509 certificate theo WS-Security policy; nó **không** biến chứng chỉ chưa được tin cậy thành trusted cert. Đối tác vẫn phải xác minh signer, signed parts, chain và quyền thực hiện operation. Khi policy yêu cầu `IssuerSerial` hoặc key identifier khác, cấu hình phải theo thỏa thuận; không áp `DirectReference` tùy tiện.

### 7.3. Kết nối interceptor với WebServiceTemplate phía client

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

// Trong @Bean method đã có template, marshaller và sender:
void attachSecurity(
        WebServiceTemplate template,
        Wss4jSecurityInterceptor signer) {

    template.setInterceptors(new ClientInterceptor[]{signer});
}
~~~

`Wss4jSecurityInterceptor` được Spring-WS hỗ trợ cho client và server security pipeline. Đây là trích đoạn phương thức **không phải toàn bộ client configuration**; JAXB/WSDL/SOAPAction/TLS sender và exception handling còn phải cấu hình riêng.

Đối với request có cả ký và mã hóa, cần cấu hình **đúng thứ tự WS-Security actions trong cùng chính sách**, không mù quáng đăng ký hai interceptors rồi giả định kết quả đúng chuẩn WS-Security của partner. Nên kiểm thử full SOAP Header, signed/encrypted parts và response decryption/verification ở hai đầu.

### 7.4. Xác minh chữ ký inbound: Crypto trust và signer identity

Khi nhận SOAP đã ký, server dùng `validationActions=Signature` và `validationSignatureCrypto` để kiểm tra:

~~~java
import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

// crypto được tạo từ store/trust material đã duyệt.
Wss4jSecurityInterceptor verifier =
    new Wss4jSecurityInterceptor();
verifier.setValidationActions("Signature");
verifier.setValidationSignatureCrypto(trustedSignerCrypto);
~~~

`trustedSignerCrypto` là một `Crypto` do ứng dụng quản lý, được cấu hình với trust anchors/certificates được phê duyệt; đoạn này là **trích đoạn minh họa**, không chứa khai báo biến đầy đủ. Tùy WSS4J Crypto/provider, trust checking có thể dựa vào keystore/truststore chứa certificate/CA; cần kiểm chứng **đúng chain policy, issuer constraints và identity mapping**.

**Không chỉ kiểm tra chữ ký có cấu trúc hợp lệ.** Nếu người lạ tự ký XML bằng certificate của họ, phép tính chữ ký có thể đúng, nhưng người đó chưa được ủy quyền là đối tác Orders. Cần kiểm tra chain/issuer/CA được tin, validity/revocation theo policy và liên kết certificate identity tới principal/tenant/operation.

Với `wsse:BinarySecurityToken` được nhúng trong request, token mang **public certificate**, không tự chứng minh rằng certificate đó đáng tin. Không “tin luôn certificate có trong SOAP Header” để test pass.

### 7.5. Mã hóa outbound: dùng public certificate của recipient

Với việc A gửi SOAP đã mã hóa tới B:

~~~java
Wss4jSecurityInterceptor encryptor =
    new Wss4jSecurityInterceptor();

encryptor.setSecurementActions("Encrypt");
encryptor.setSecurementEncryptionUser(
    "partner-encryption-2026");
encryptor.setSecurementEncryptionCrypto(
    recipientPublicCertificateCrypto);
~~~

`recipientPublicCertificateCrypto` phải chứa **public certificate của B** được đánh giá phù hợp (đúng recipient, algorithm, validity, policy); alias `partner-encryption-2026` là tên entry bên A đặt cho certificate B.

**Encrypt không đòi private key của B ở bên A**, và bản thân encryption **không xác thực danh tính người gửi A**. Nếu contract yêu cầu chữ ký, phải thêm `Signature` theo đúng policy.

Ngược lại, nếu alias trỏ vào public certificate của **A**, bản tin có thể được mã hóa cho A và **B không giải mã được**. Đây là lỗi lựa chọn alias, không phải lỗi XSD/JAXB.

### 7.6. Giải mã inbound: private key của chính recipient + password callback

Theo Spring-WS reference 4.1.4, một SOAP message có `xenc:EncryptedKey` thường được xử lý bằng `validationActions=Encrypt`, `validationDecryptionCrypto` chứa private key của bên nhận và một callback cung cấp password để mở private key:

~~~java
import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;
import org.springframework.ws.soap.security.wss4j2.callback.KeyStoreCallbackHandler;

// Trong @Bean method để Spring quản lý lifecycle:
KeyStoreCallbackHandler callback =
    new KeyStoreCallbackHandler();
callback.setPrivateKeyPassword(
    env.getRequiredProperty("soap.decrypt.keyPassword"));

Wss4jSecurityInterceptor decryptor =
    new Wss4jSecurityInterceptor();
decryptor.setValidationActions("Encrypt");
decryptor.setValidationDecryptionCrypto(
    recipientPrivateKeyCrypto);
decryptor.setValidationCallbackHandler(callback);
~~~

Các biến `env`/`recipientPrivateKeyCrypto` cần được cung cấp bằng dependency injection. **Trong cấu hình chạy thật, khai báo callback như Spring-managed bean**, để nó được gọi `afterPropertiesSet()` nếu implementation/lifecycle yêu cầu; không dùng trích đoạn này như chương trình độc lập.

Khi giải mã, WSS4J có thể dùng thông tin KeyInfo/EncryptedKey và crypto configuration để xác định private key tương ứng. Đừng nghĩ chỉ đặt một tên alias giống bên gửi là đủ. **Bên nhận cần sở hữu private key thực sự tương ứng với public certificate mà bên gửi đã dùng để Encrypt.**

### 7.7. SecretKeyEntry không thay thế private key X.509

Một số WS-Security profiles có thể dùng symmetric secret key với `ds:KeyName` hoặc cơ chế riêng. `KeyStoreCallbackHandler` có `setSymmetricKeyPassword` và `setKeyStore` để phục vụ các callbacks này. Nhưng:

- Không tự chọn `SecretKeyEntry` để thay `PrivateKeyEntry` trong luồng X.509 RSA key transport.
- Không đưa symmetric key ra SOAP Header dưới dạng plaintext.
- Kiểm tra `JCEKS`/`PKCS12`/provider có thực sự hỗ trợ secret key entries như profile yêu cầu.
- Chọn mode mã hóa/chữ ký theo WS-Security policy và khả năng client/server; không suy từ tên alias.

### 7.8. Không nhầm defaultX509Alias với việc “ép xác minh một người”

`CryptoFactoryBean#setDefaultX509Alias` xác định certificate alias mặc định theo semantics WSS4J, ví dụ khi KeyInfo không cung cấp đủ thông tin. Nó **không phải cơ chế authorization** và không tự biến incoming signer thành một người được tin cậy.

Đối với outbound signing, property cần chọn key là `securementUsername`; đối với outbound encryption, property xác định certificate của recipient là `securementEncryptionUser`. Với inbound signature, WSS4J có thể lấy signer cert từ KeyInfo/Token, nhưng phải kiểm tra trust và map identity. Với inbound decryption, phải có private key/crypto và password callback, không chỉ một public certificate.

## 8. TLS và mTLS: alias được chọn bởi JSSE KeyManager

TLS và WS-Security bảo vệ những tầng khác nhau:

~~~mermaid
flowchart TD
    A["WebServiceTemplate + JAXB"] --> B["WS-Security WSS4J"]
    B --> C["SOAP Envelope: Signature/Encrypt"]
    C --> D["HTTP sender: JDK HttpClient / Apache"]
    D --> E["JSSE SSLContext"]
    E --> F["KeyManager: chọn local TLS identity"]
    E --> G["TrustManager: kiểm tra remote certificate"]
    F --> H["TLS handshake"]
    G --> H
    H --> I["HTTPS SOAP endpoint"]
~~~

**Không có một “alias SOAP” duy nhất được JSSE tự hiểu.** Khi WSS4J ký XML, nó dùng `securementUsername` để chọn private key entry. Khi TLS client thực hiện mTLS, **JSSE KeyManager** tìm một certificate/private key entry phù hợp điều kiện handshake (key algorithm, issuer được chấp nhận, policy, đôi khi SNI/peer info), chứ **không lấy `securementUsername`** của WSS4J.

### 8.1. Mô hình SSLContext cho một SOAP client mTLS

Ví dụ Java thuần sau nhận **hai nguồn tách biệt**: identity keystore để client chứng minh danh tính và truststore để xác minh server.

~~~java
import java.io.InputStream;
import java.security.KeyStore;
import java.security.SecureRandom;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class TlsContextFactory {

    private TlsContextFactory() {}

    public static SSLContext createMtlsContext(
            InputStream clientIdentityP12,
            char[] identityStorePassword,
            char[] privateKeyPassword,
            InputStream trustedServersP12,
            char[] trustStorePassword) throws Exception {

        KeyStore identity = KeyStore.getInstance("PKCS12");
        identity.load(clientIdentityP12, identityStorePassword);

        KeyStore trust = KeyStore.getInstance("PKCS12");
        trust.load(trustedServersP12, trustStorePassword);

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(identity, privateKeyPassword);

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trust);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
            kmf.getKeyManagers(),
            tmf.getTrustManagers(),
            new SecureRandom());

        return context;
    }
}
~~~

**Phạm vi:** caller quản lý đóng InputStreams và bảo vệ/thu hồi `char[]` password theo lifecycle. Ví dụ giả định **PKCS#12 của provider cho phép KeyManagerFactory khôi phục private key bằng password truyền vào**. Với nhiều entries có passwords khác nhau hoặc HSM, cần chiến lược `KeyStore.Builder`/`KeyManager`/provider cụ thể, không mặc định một password mở mọi key. File `trustedServersP12` cần chứa **trust anchors đã được duyệt**, không phải tập public cert không xác minh nguồn.

Để dùng SSLContext cho sender JDK:

~~~java
import java.net.http.HttpClient;
import org.springframework.ws.transport.http.JdkHttpClientMessageSender;

// sslContext được tạo bằng hàm ở trên, sau khi load secrets.
HttpClient httpClient = HttpClient.newBuilder()
        .sslContext(sslContext)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

JdkHttpClientMessageSender sender =
        new JdkHttpClientMessageSender(httpClient);

// Gắn sender vào WebServiceTemplate bằng setMessageSender(sender).
~~~

**Chỉ áp dụng khi phiên bản Spring-WS có `JdkHttpClientMessageSender`.** Bản Spring-WS cũ có thể cần sender khác; phương thức cung cấp SSLContext/KeyManager/TrustManager phụ thuộc HTTP stack đang dùng. Việc SSLContext có private key client **chưa chứng minh** server thực sự yêu cầu/nhận mTLS: phải test handshake với server đã bật client certificate authentication.

### 8.2. JSSE chọn TLS alias như thế nào?

`X509KeyManager` và `X509ExtendedKeyManager` có các method:

~~~java
String chooseClientAlias(
    String[] keyType,
    java.security.Principal[] issuers,
    java.net.Socket socket);

String chooseServerAlias(
    String keyType,
    java.security.Principal[] issuers,
    java.net.Socket socket);

// Khi TLS client chạy trên SSLEngine:
String chooseEngineClientAlias(
    String[] keyType,
    java.security.Principal[] issuers,
    javax.net.ssl.SSLEngine engine);
~~~

Những khai báo trên là **chữ ký minh họa**, không phải class compile độc lập. Key manager xem danh sách key types, issuer constraints và khả năng của provider để chọn local identity; với server identity, SNI cũng có thể tham gia. Một keystore chứa hai `PrivateKeyEntry` không bảo đảm JSSE chọn alias giống code WSS4J.

| Cơ chế | Alias chịu điều khiển bởi | Khác biệt |
| --- | --- | --- |
| TLS server private key | HTTPS connector/JSSE KeyManager và có thể key-alias option do container cung cấp. | Chứng chỉ phải phù hợp DNS SAN/hostname và serverAuth/policy. |
| mTLS client private key | JSSE `KeyManager`, key type/issuer/handshake. | Không chọn từ `Wss4jSecurityInterceptor#setSecurementUsername`. |
| SOAP outbound signature | WSS4J `securementUsername` + Crypto. | Ký các SOAP parts theo WS-Security policy. |
| SOAP outbound encryption | WSS4J `securementEncryptionUser` + Crypto public cert. | Chọn certificate của recipient, không bắt buộc là TLS peer cert. |

Khi cần cố định alias mTLS, phương án đơn giản nhất thường là **keystore identity chỉ chứa đúng private key/cert mà endpoint đó được phép dùng**. Nếu phải dùng một keystore nhiều aliases, hãy dùng **KeyManager wrapper/provider được thiết kế và test đúng TLS/SSLEngine** thay vì tự thay alias sau handshake. Không trả một alias không phù hợp với issuer/key algorithm chỉ để “ép” dùng certificate.

### 8.3. Server SSL certificate khác SOAP signing certificate

Một server `https://orders.example.test/ws` có thể:

- Dùng `tls-orders.example.test` PrivateKeyEntry để làm TLS server identity.
- Dùng `soap-signing-orders-2026` PrivateKeyEntry để ký SOAP response.
- Dùng `soap-decrypt-orders-2026` PrivateKeyEntry để giải mã SOAP request.
- Dùng public certificates của partner để xác minh request signatures.
- Dùng mTLS trust policy để kiểm tra client certificate của transport.

**Có thể trùng nhau trong một deployment cụ thể, nhưng không mặc định.** Certificate server TLS thay mới không bắt buộc SOAP Signature certificate cũng đổi, và ngược lại. Quy trình rotation phải xác định đúng scope của từng key.

Trong Spring Boot, các thuộc tính TLS của embedded server như `server.ssl.key-store`/`server.ssl.key-alias` (khi version hỗ trợ) liên quan HTTPS connector. Chúng **không** thay `securementUsername` của WSS4J. Với SOAP **client**, `server.ssl.*` của ứng dụng server cũng không tự cấu hình outbound `WebServiceTemplate`; cần SSLContext/HTTP sender ở client.

### 8.4. TrustManager của TLS khác Crypto trust của WS-Security

Một Spring-WS client có thể kết nối HTTPS thành công bởi certificate TLS của đối tác được trust, nhưng vẫn từ chối **SOAP response signature** nếu WS-Security signer là certificate khác không được WSS4J Crypto trust.

Chiều ngược lại, WSS4J có certificate của signer trong trust store nhưng TLS server certificate hết hạn hoặc hostname sai, kết nối có thể **không được thiết lập** nên chưa có SOAP message để kiểm tra chữ ký.

~~~text
TLS trust:
  ai đang sở hữu HTTPS endpoint trên connection này?

WS-Security signature trust:
  ai đã ký SOAP message/parts này, chain có tin cậy,
  và identity đó được phép thực hiện operation này không?
~~~

Không lấy việc **TLS handshake pass** làm lý do bỏ `validationSignatureCrypto` khi WSDL/WS-Security policy yêu cầu ký. Cũng không dùng `TrustManager` chấp nhận mọi certificate để vượt lỗi; đó là mất một ranh giới bảo mật quan trọng.

## 9. Bảo vệ private keys và password trong Spring-WS deployments

Lựa chọn đúng alias nhưng phân phối khóa sai cách vẫn tạo rủi ro bảo mật lớn.

### 9.1. Cách lưu trữ nên ưu tiên

| Cách lưu vật liệu | Ưu điểm | Rủi ro/cần kiểm soát |
| --- | --- | --- |
| Secret manager + mounted file read-only | Tách secret khỏi source/image; có rotation/access policy. | Kiểm soát file permissions, lifecycle, audit, reload. |
| PKCS#12/JKS encrypted file trên volume được bảo vệ | Dễ tích hợp JDK/WSS4J. | Password không để cùng file dưới quyền đọc rộng; backup mã hóa. |
| HSM/PKCS#11 hoặc cloud key service | Có thể giữ private key non-exportable và audit key operations. | Provider compatibility, latency, sessions, failover và WSS4J integration. |
| Certificate-only trust bundle | Không chứa private key, dễ phân phối. | Import CA sai hoặc trust quá rộng có thể mở đường spoofing. |
| Classpath JAR chứa private key production | Thuận tiện xây app nhưng **không nên là mặc định**. | Private key bị sao chép vào image, artifacts, developer machines, backup. |
| Environment variable chứa password | Dễ inject vào ứng dụng. | Có thể lộ qua môi trường tiến trình, diagnostics hoặc deployment logs; kiểm soát runtime access. |

**Không tự lưu private key production bằng plain PEM trong repository**, kể cả repository private. Các file keystore phải được phân quyền theo nguyên tắc least privilege, mã hóa khi lưu truyền và có audit trail truy cập.

### 9.2. Store password khác private key password

Một keystore có thể dùng:

~~~text
store password   → tải/xác minh integrity của container
entry password   → khôi phục private key/secret key được bảo vệ
HSM PIN/credential → mở session hoặc quyền dùng key handle
~~~

Trong ví dụ Spring-WS:

~~~text
CryptoFactoryBean.keyStorePassword = store password
Wss4jSecurityInterceptor.securementPassword = signing key password
KeyStoreCallbackHandler.privateKeyPassword = decryption key password
~~~

Một số PKCS#12 implementations yêu cầu hoặc thường sử dụng store/key passwords giống nhau; hành vi thay đổi theo JDK/provider, không nên giả định mật khẩu luôn tách được như JKS. Nếu xảy ra `UnrecoverableKeyException`, phải phân biệt store password đúng nhưng **entry password sai** hoặc entry không có private key.

Mật khẩu chỉ là một lớp bảo vệ file; nếu ứng dụng có quyền đọc password và private key thì tài khoản tiến trình bị xâm nhập vẫn có thể dùng khóa. Giới hạn quyền ứng dụng, host/network, secrets audit và thời gian tồn tại của khóa.

### 9.3. Khóa riêng phải có chủ sở hữu và purpose rõ ràng

Hãy quản trị một bảng nội bộ:

| Trường | Ví dụ minh họa |
| --- | --- |
| Key purpose | SOAP outbound signing |
| Owning application | orders-client |
| Environment | staging |
| Keystore type/location | PKCS12, secret-mounted path |
| Alias | `soap-sign-orders-2026` |
| Certificate SHA-256 fingerprint | Hash được quản lý trong registry, không copy tùy tiện |
| Issuer/expiry | CA đã duyệt, ngày hết hạn |
| Trusting parties | payments-partner |
| Rotation owner & contact | Nhóm Security/Platform được chỉ định |
| Revocation plan | Cơ chế thu hồi trust/cert và cập nhật đối tác |
| Rollback/key retention | Thời gian được phép giữ key cũ để đọc dữ liệu lịch sử |

Không dùng tên alias như `prod-key`/`main` nếu hệ thống nhiều keys và nhiều purposes mà không có registry; tên mơ hồ khiến chuyển đổi nguy hiểm.

## 10. Xoay vòng khóa và chứng chỉ không làm gián đoạn SOAP

Trong hệ thống SOAP, rotation không chỉ là thay file `.p12` trên server. Phải quan sát **bên nào cần private key, bên nào cần public cert, khóa cũ còn dùng để giải mã dữ liệu đang bay không**.

### 10.1. Rotation SOAP signing

~~~mermaid
sequenceDiagram
    participant A as Orders (sender)
    participant B as Payments (verifier)

    Note over A,B: Hiện tại sign cert A-old
    A->>B: Cung cấp public cert A-new qua kênh đã xác thực
    B->>B: Trust cả A-old và A-new trong cửa sổ chuyển
    B-->>A: Xác nhận đã sẵn sàng
    A->>A: Đổi securementUsername sang A-new
    A->>B: SOAP signed by private key A-new
    B-->>A: Signature/trust OK
    Note over A,B: Sau thời gian được duyệt: rút trust A-old
~~~

Quy tắc:

1. Phát hành **key pair và certificate mới** với purpose/phạm vi phù hợp.
2. Phân phối **public certificate/chain mới** tới bên xác minh qua kênh tin cậy.
3. Cho phép **overlap trust** trong cửa sổ chuyển có kiểm soát, nếu policy cho phép.
4. Đổi signer alias ở bên gửi, xác minh giao dịch thực và Fault behavior.
5. Gỡ trust cũ sau khi không còn lưu lượng/đáp ứng thời gian xử lý message cũ.
6. Nếu private key bị nghi lộ, có thể **không được** duy trì overlap thông thường; phải tuân theo xử lý sự cố và thu hồi khẩn cấp.

Cần lưu ý identity mapping: khi certificate mới cùng subject nhưng khác key/fingerprint, một số bên nhận có thể coi là identity khác. Không mặc định “same CN = same partner”.

### 10.2. Rotation SOAP encryption/decryption

Khi A encrypt cho B:

~~~text
A: encrypt outbound bằng public cert B-new
B: decrypt inbound bằng private key B-new
B: có thể tạm giữ private key B-old để đọc message cũ/in-flight
~~~

**Trình tự hợp lý:** B sẵn sàng giải mã bằng private key mới trước, sau đó A mới chuyển sang public certificate mới. Nếu A đổi quá sớm, B chưa có private key tương ứng sẽ phát Fault. Nếu B xóa key cũ quá sớm, các message mã hóa trước khi rotation có thể không giải mã được.

Khóa giải mã cũ chỉ được giữ **đúng thời gian cần thiết theo retention, queue depth và policy**. Không kéo dài vô hạn vì “có thể vẫn cần”. Đối với dữ liệu được lưu mã hóa dài hạn, cần chính sách key escrow/archive/re-encryption riêng và quản lý độc lập với SOAP message transit.

### 10.3. TLS certificate rotation

TLS server rotation liên quan SAN/hostname, CA chain, SNI và connector reload. TLS client/mTLS rotation liên quan trust của server và lựa chọn alias tại KeyManager. Những bước này độc lập với SOAP WS-Security certificate rotation trừ khi hệ thống cố tình dùng chung key.

Một file trên volume được thay bằng file mới **không đảm bảo** `SSLContext`, `CryptoFactoryBean` hoặc WSS4J interceptor đang sử dụng vật liệu mới: nhiều thành phần **cache KeyStore/Crypto/SSLContext** trong bộ nhớ. Có thể cần reload/reinitialize bean hoặc rolling restart. Hãy kiểm tra đúng framework/version để biết reload có được hỗ trợ không.

### 10.4. Rotation phải có negative tests

Ngoài test certificate mới **pass**, cần xác minh:

- Alias mới đúng `PrivateKeyEntry` hoặc `TrustedCertificateEntry` theo purpose.
- Certificate cũ bị từ chối **sau** khi hết thời gian overlap.
- Public cert A không tự dùng giải mã private key B; data encrypted với B-old chỉ được đọc khi B-old còn được phép.
- Các trường hợp expiry/revocation/policy violation dẫn tới lỗi an toàn.
- Không log private key, mật khẩu hoặc full decrypted SOAP payload khi debug.
- Timeout/retry không tạo side effects lặp trong giai đoạn cutover.

## 11. Kiểm thử keystore, alias và security end-to-end

Không thể kết luận “WS-Security hoạt động” chỉ vì keystore load thành công. Cần kiểm tra **entry đúng loại, certificate đúng purpose và hai đầu ký/mã hóa/verify/decrypt được theo policy**.

### 11.1. Kiểm tra ở startup trước request SOAP

Một chương trình startup/liveness validation có thể kiểm tra:

~~~text
[OK]   store loaded, type PKCS12
[OK]   alias soap-signing-2026 is PrivateKeyEntry
[OK]   signing cert is time-valid, algorithm compatible
[OK]   alias partner-encryption-2026 has public X.509 cert
[OK]   alias soap-decrypt-2026 is PrivateKeyEntry
[OK]   configured trust anchors match approved fingerprints
[WARN] soap-decrypt-2025 retained for bounded rotation window
~~~

Output trên chỉ là **minh họa**, không phải log mặc định của Spring-WS. **Không in password, private key, keystore bytes hoặc certificate subject/serial nhạy cảm trong log chia sẻ rộng**.

Không dùng một startup check có thao tác ký/giải mã bằng key production nếu quy định audit/HSM không cho phép; sử dụng test operation, quyền kiểm soát và metrics của key provider. Với HSM, availability và permission failures cần được phân loại và cảnh báo rõ.

### 11.2. Ma trận test SOAP key purpose

| Tình huống | Setup | Kỳ vọng |
| --- | --- | --- |
| Sign hợp lệ | `securementUsername` trỏ `PrivateKeyEntry` A. | B xác minh signature và certificate trust; endpoint xử lý. |
| Alias ký không tồn tại | `securementUsername` sai. | Fail rõ ràng, không âm thầm ký bằng một key khác. |
| Alias ký trỏ trustedCertEntry | Có public cert nhưng không có private key. | Không ký được; fail closed. |
| Store password sai | Keystore load bị từ chối. | Không tạo Crypto hoặc request không được gửi; không log secret. |
| Private key password sai | Store đọc được nhưng không khôi phục private key. | Sign/decrypt fail, phân loại key access error. |
| Signer cert không được trust | Signature mathematically valid nhưng issuer/identity không được duyệt. | B từ chối với security result phù hợp. |
| Signer cert hết hạn | Certificate ngoài validity period. | Từ chối theo validation policy, không bỏ qua vì signature đúng. |
| Signature bị sửa | Thay XML Body hoặc signed Header sau khi ký. | Signature validation fail; không vào business service. |
| Chỉ ký sai phần | Body đúng nhưng security policy yêu cầu ký Header khác. | Từ chối policy mismatch; kiểm tra signed parts. |
| Encrypt cho đúng recipient | A dùng cert B, B có private key B. | B giải mã và kiểm tra SOAP/XSD. |
| Encrypt nhầm recipient | A dùng cert C hoặc cert B-old không còn key. | B không giải mã; không fallback plaintext. |
| Decrypt thiếu private key | B chỉ có cert công khai. | Fail; public certificate không thay private key. |
| Decrypt password sai | B có private key nhưng callback sai. | Fail, không dump encrypted key/plaintext. |
| TLS server certificate đúng | Chain/hostname hợp lệ. | HTTP sender kết nối qua HTTPS. |
| TLS hostname sai | Cert SAN không khớp endpoint. | TLS fail, không tạo SOAP Fault giả. |
| mTLS alias không phù hợp | Keystore có private key nhưng issuer/key type không phù hợp. | Handshake bị từ chối, không dùng WSS4J alias để “chữa”. |
| Truststore bị mở rộng sai | Import CA lạ. | Security gate/test phát hiện trust policy drift. |
| PKCS12/JKS migration | Chuyển store format và key password. | Entry count/type, alias, fingerprint và operations vẫn đúng. |
| Rotation signer | A đổi key A-new, B đã trust A-new. | New accepted, old theo cửa sổ policy. |
| Rotation encryption | A đổi cert B-new khi B đã có private key B-new. | New messages decrypt được; old đúng retention. |
| Đồng thời nhiều requests | Nhiều tenant/partner, nhiều aliases. | Không dùng nhầm private key/cert giữa tenants. |

**Đặc biệt:** test phải phân biệt **TLS server cert verification** và **SOAP signature verification**. Một test Spring-WS có thể bypass HTTP network bằng mock sender, nên không kiểm tra được SSLContext alias selection. Test đối tác không chỉ xem HTTP 200: còn phải kiểm tra SOAP Fault, Header security, JAXB response, XSD validation và correlation.

### 11.3. MockWebServiceServer/MockWebServiceClient test được gì?

- `MockWebServiceServer` giúp kiểm tra `WebServiceTemplate` marshal SOAP request và xử lý response/Fault; nếu có WSS4J client interceptor, cần đảm bảo test context thực sự đăng ký interceptor. **Không** dựa vào nó để chứng minh handshake mTLS hoặc KeyManager chọn đúng alias.
- `MockWebServiceClient` chạy các endpoint mappings/adapters/interceptors phía server trong ApplicationContext; hữu ích kiểm tra request signature/validation failure, nhưng **không** tự chứng minh TLS container certificate hoặc client certificate authentication ở gateway.
- Với ký/mã hóa, cần thêm **integration test với hai SOAP stacks hoặc hai application contexts** dùng test keys riêng: sign→verify, encrypt→decrypt, success và negative security Fault, signed parts và trust mapping đúng policy.
- Với TLS/mTLS, cần **test qua HTTPS server thật** với trust roots/lab certificates, không chỉ test raw SOAP XML.

### 11.4. Test end-to-end hai phía Java và .NET

Một đối tác .NET/WCF có thể dùng PKCS#12/Windows certificate store và WS-Security KeyInfo khác Spring-WS. Tập test tối thiểu:

1. Xác nhận WSDL/XSD, SOAP 1.1/1.2, SOAPAction, WS-Addressing nếu hợp đồng yêu cầu.
2. Đối chiếu signer public certificate, chain, alias lựa chọn **chỉ ở bên local** và KeyInfo format trên wire.
3. Kiểm tra phương pháp signature, digest, canonicalization, signed parts và security timestamp.
4. Kiểm tra XML Encryption: recipient cert, key transport, content encryption algorithms và EncryptedKey KeyInfo.
5. Kiểm tra TLS server hostname/SAN và mTLS chain nếu được yêu cầu.
6. Kiểm tra response/fault signed/encrypted theo contract; không chỉ request.
7. Kiểm tra rotation cùng lúc signer và recipient, bảo đảm thời điểm chuyển được phối hợp.
8. Chỉ sử dụng test keys/certificates được phép, không đưa credentials production vào fixtures.

Một certificate có thể đọc được bởi cả Java và .NET nhưng **SOAP Signature vẫn sai** do khác XML canonicalization, security header order, key identifier hoặc signed parts. Đó không phải tự động là lỗi PKCS#12.

## 12. Troubleshooting: tìm đúng loại lỗi trước khi đổi alias

Một exception nói “certificate” hoặc “key” không đủ xác định vấn đề nằm ở **format**, **password**, **alias**, **trust**, **TLS** hay **WS-Security**. Hãy bắt đầu từ bước đầu tiên không thành công.

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra ưu tiên |
| --- | --- | --- |
| `Invalid keystore format` | Chọn JKS cho file PKCS#12, file bị lỗi hoặc provider không hỗ trợ. | `-storetype` đúng, kiểm tra file/format trong môi trường test; tránh tự đổi extension. |
| `Keystore password was incorrect` | Mật khẩu store sai, encoding/provider/algorithm legacy không tương thích. | Password nguồn bí mật, type/provider/JDK, mở bằng keytool phiên bản phù hợp. |
| `UnrecoverableKeyException` | Private key password sai, key bị bảo vệ không tương thích. | Phân biệt **store password** và **key password**, alias loại PrivateKeyEntry. |
| `Alias not found` | Sai tên/case hoặc migration đổi alias. | `keytool -list` đúng store; config và version artifact thực tế. |
| `Cannot find private key` | Alias trỏ `trustedCertEntry` hoặc key không nằm trong store. | Kiểm tra entry type và key permissions; không chỉ certificate presence. |
| Sign outbound báo lỗi password | WSS4J `securementPassword` không khớp key entry. | Đối chiếu privateKeyEntry/callback và secret source, không bật debug in password. |
| Sign outbound dùng nhầm certificate | `securementUsername` sai hoặc Crypto trỏ nhầm file. | Kiểm tra alias, fingerprint và keystore location. |
| SOAP signature mathematically valid nhưng rejected | Signer chưa được trust/authorize hoặc signed parts không đúng. | `validationSignatureCrypto`, certificate chain, KeyUsage/policy, mapping đối tác. |
| `FailedCheck`/`InvalidSecurity` SOAP Fault | Có thể sai signature, trust, encryption, token hoặc action order. | WSS4J security events và Fault code/detail đã lọc. |
| Decrypt SOAP fail sau rotation | Bên gửi dùng cert mới nhưng bên nhận chưa có key hoặc key old bị bỏ. | So fingerprint public recipient cert và private key inventory của B. |
| Encrypted SOAP với cert công khai của chính bên gửi | `securementEncryptionUser` chọn sai recipient. | Đối chiếu certificate recipient theo hợp đồng. |
| TLS `PKIX path building failed` | Không dựng được chain tới trust anchor tin cậy. | Truststore TLS, intermediate CAs, issuer, policy/hostname; không tắt cert verification. |
| TLS hostname mismatch | SAN không khớp endpoint hoặc proxy/SNI sai. | DNS SAN, HTTPS address từ WSDL, SNI và TLS connector. |
| mTLS handshake fails | Client không có private key phù hợp/không gửi cert hoặc server từ chối. | KeyManager selection, clientAuth EKU, issuers, trust và policy server. |
| TLS OK nhưng SOAP Fault Signature | Hai tầng trust khác nhau. | WSS4J Crypto/trust và signed parts; không sửa TLS store mù quáng. |
| SOAP Signature OK nhưng TLS lỗi trước khi gửi | TLS failed; chưa có SOAP response. | JSSE truststore/identity/hostname, kết nối proxy. |
| `KeyStore.getDefaultType()` thay sau upgrade JDK | Format default khác môi trường legacy. | Đặt type rõ ràng, kiểm tra `java.security` và JDK runtime. |
| PKCS#12 đọc được ở Java nhưng OpenSSL khác báo lỗi | Thuật toán bảo vệ/provider legacy hoặc import không tương thích. | Version/tool, profile thuật toán, kế hoạch migration được duyệt. |
| Cùng alias nhưng key fingerprint khác | File/certificate đã rotate hoặc trỏ sai environment. | Registry inventory, fingerprint, subject/issuer/validity. |
| Truststore có cert signer nhưng bị reject | Chain/trust/identity/revocation/policy/signed parts không khớp. | Không chỉ xem entry count; kiểm tra trust decision thực tế. |
| Đã thay file `.p12` nhưng service vẫn dùng cert cũ | Crypto/SSLContext/KeyManager cached. | Kiểm tra lifecycle/reload/rolling restart và certificate thực dùng. |
| Có nhiều key nhưng JSSE chọn alias không mong muốn | KeyManager tự chọn theo algorithm/issuers/SNI. | Đơn giản hóa identity store hoặc test KeyManager wrapper. |
| Test mock pass, production fail mTLS | Mock không chạy network/TLS. | Test thực qua HTTPS/mTLS connector với lab certificates. |

### 12.1. Quy trình điều tra theo tầng

~~~mermaid
flowchart TD
    A["SOAP client/server báo lỗi chứng chỉ hoặc khóa"] --> B{"KeyStore load được?"}
    B -- "Không" --> C["Format/provider/store password/location"]
    B -- "Có" --> D{"Alias và entry type phù hợp?"}
    D -- "Không" --> E["Alias/case/PrivateKeyEntry vs TrustedCert"]
    D -- "Có" --> F{"Lỗi TLS handshake?"}
    F -- "Có" --> G["SSLContext, KeyManager, TrustManager, SAN/chain"]
    F -- "Không" --> H{"SOAP security Fault?"}
    H -- "Có" --> I["Signature, Crypto, recipient key, KeyInfo, policy"]
    H -- "Không" --> J["XSD/WSDL/JAXB/business, transport khác"]
    I --> K["Kiểm tra rotation, cert fingerprint và test đối tác"]
~~~

**Không thay keystore trong production theo phỏng đoán.** Thu thập exception type, step của pipeline, timestamp, alias cấu hình (nếu được phép), SHA-256 fingerprint đã được phê duyệt và correlation ID; không thu raw private key/password để debug.

### 12.2. Logging TLS/WS-Security có thể lộ dữ liệu

JSSE hỗ trợ debug TLS bằng các tùy chọn runtime như `javax.net.debug`; WSS4J cũng có các logger chi tiết. Những công cụ này hữu ích trong **môi trường test cô lập**, nhưng có thể ghi nhiều thông tin certificate, security header, peer metadata và đôi khi dữ liệu nhạy cảm hơn dự kiến.

- Không bật DEBUG/TRACE toàn bộ trên production traffic để “xem alias nào đang dùng” khi chưa đánh giá và phê duyệt.
- Không ghi nguyên `wsse:Security`, UsernameToken, SOAP Body chứa dữ liệu khách hàng hoặc passwords.
- Ưu tiên log **error category, operation, correlationId, certificate fingerprint đã được duyệt, key purpose và version**, không log key material.
- Dùng số liệu TLS handshake failures, SOAP Fault rates, certificate expiry alarms và rotation events có kiểm soát.
- Nếu log đã lộ secret, xử lý như sự cố dữ liệu/credential, không chỉ xóa dòng log trên dashboard.

## 13. Bài tập tình huống có đáp án gợi ý

### Tình huống A — Có certificate nhưng ký không được

`keytool -list -v` cho thấy alias `orders-signing` là `trustedCertEntry`. Ứng dụng đặt `securementUsername=orders-signing` rồi gửi `securementActions=Signature`.

**Đáp án:** `trustedCertEntry` không chứa private key. Cần `PrivateKeyEntry` của **chính bên gửi**, có chain và key password hoặc HSM key handle phù hợp. Public cert một mình chỉ giúp verify hoặc encrypt cho recipient. Không export private key từ một certificate PEM vì certificate không chứa nó.

### Tình huống B — Mã hóa bằng private key của mình

Client A có hai aliases: `my-signing-key` chứa private key A và `partner-encrypt-cert` chứa public cert B. Developer đặt `securementEncryptionUser=my-signing-key`.

**Đáp án:** Trong mô hình XML Encryption X.509, A phải mã hóa cho **public certificate của recipient B**. Nếu encrypt bằng public cert A, chỉ ai có private key A mới giải mã được, B không có khả năng đọc. Đặt `securementEncryptionUser` tới `partner-encrypt-cert` và kiểm thử B decrypt.

### Tình huống C — TLS handshake pass nhưng WSS4J từ chối signature

Java client gọi HTTPS thành công, nhận SOAP Fault về invalid signature/trust. Team định sửa `javax.net.ssl.trustStore` để “tin certificate SOAP”.

**Đáp án:** TLS và WS-Security có trust policy riêng. Kiểm tra `validationSignatureCrypto`, signer certificate chain, signed parts và identity mapping. JVM TLS truststore không tự được dùng làm WS-Security truststore trừ khi cấu hình WSS4J Crypto thực sự liên kết tới nó và policy cho phép.

### Tình huống D — Alias giống nhau trên hai keystores

A và B đều có alias `mycert`. A mã hóa cho certificate của chính A, trong khi B sở hữu private key hoàn toàn khác, nhưng team tin rằng “cùng alias” đủ để decrypt.

**Đáp án:** Alias là tên cục bộ, **không phải cặp khóa chung**. Kiểm tra public-key/certificate fingerprint mà A thực sự dùng và private key B tương ứng. Đổi alias string không làm hai key pairs trở thành một.

### Tình huống E — mTLS dùng sai certificate sau rotation

Keystore client chứa `tls-client-2025` và `tls-client-2026`. WSS4J đã chọn `soap-signing-2026` đúng, nhưng gateway từ chối mTLS.

**Đáp án:** WSS4J signing alias **không quyết định** TLS identity. Kiểm tra JSSE `KeyManager` chọn client cert nào theo key type, issuers và provider; tốt nhất giới hạn identity keystore cho endpoint hoặc dùng key manager có alias policy đã kiểm thử. Đồng thời xem trust/authorization của gateway.

### Tình huống F — Chuyển file JKS thành P12

Sau `keytool -importkeystore`, chương trình chạy JDK mới load được file nhưng không ký SOAP. Chỉ số log cho thấy alias cũ không tồn tại.

**Đáp án:** Kiểm tra danh sách aliases và entry types trước/sau conversion, key password behavior và certificate fingerprints. Có thể `-destalias`/`-srcalias` hoặc provider đã thay metadata; phải xác nhận và sửa cấu hình mapping có kiểm thử, không chỉnh alias của bên nhận bằng phỏng đoán.

### Tình huống G — Đối tác đổi public encryption certificate

B thông báo dùng certificate `B-new` từ ngày mới. A cập nhật ngay `securementEncryptionUser` để Encrypt cho B-new, nhưng B chưa triển khai private key tương ứng.

**Đáp án:** Phải phối hợp **B sẵn sàng decrypt trước, A switch encryption sau**. Trong cửa sổ chuyển B có thể cần giữ old key để đọc message in-flight; A phải dùng đúng public cert theo effective date và policy đã xác nhận.

### Tình huống H — Tự ký certificate để production mTLS

Nhóm phát triển dùng lệnh lab `keytool -genkeypair` tạo self-signed cert 30 ngày, không có SAN phù hợp, rồi đưa vào production để gọi HTTPS server của đối tác.

**Đáp án:** Key pair lab chỉ chứng minh cách tạo `PrivateKeyEntry`. Production mTLS cần PKI/CA/trust và identity mapping theo thỏa thuận, EKU clientAuth khi yêu cầu, thời hạn/rotation và chính sách bảo vệ private key. Server đối tác không tự tin certificate tự ký vì client đặt alias đẹp.

### Tình huống I — Kiểm tra signature chỉ qua certificate đi kèm SOAP

Một server chấp nhận bất kỳ `wsse:BinarySecurityToken` certificate nào có trong SOAP Header, miễn signature khớp public key trong chính token đó.

**Đáp án:** Đó là chỉ kiểm tra **tính toán chữ ký**, chưa kiểm tra **signer trust và authorization**. Attacker có thể tự tạo key pair/cert và ký message của họ. Cần trust anchor/cert pinning theo chính sách, validity và map principal tới quyền operation. Không mặc định trust mọi certificate peer gửi.

### Tình huống J — Test SOAP mock pass nhưng TLS production fail

Test `MockWebServiceServer` cho thấy WSS4J sign request và SOAP response parse được. Khi chạy thật, client nhận `SSLHandshakeException` trước HTTP status.

**Đáp án:** Mock không chạy TLS handshake. Cần integration test với HTTPS/mTLS endpoint thật trong test environment, kiểm tra SSLContext/KeyManager/TrustManager, chain/SAN và JDK/HTTP sender configuration. Đây không nhất thiết là lỗi SOAP signature.

## 14. Checklist cuối bài

| Câu hỏi kiểm tra | Điều kiện đạt |
| --- | --- |
| Biết format thực tế? | Type `PKCS12`/`JKS`/`BCFKS`/`PKCS11` được kiểm tra, không suy từ extension. |
| Hiểu PEM? | Phân biệt certificate PEM và private key PEM; không coi PEM mặc định là JKS/PKCS12. |
| Có inventory alias? | Tên alias, entry type, purpose, owner, expiry và fingerprint đã được quản lý. |
| Đúng entry cho ký? | `securementUsername` trỏ `PrivateKeyEntry` với private key của sender. |
| Đúng entry cho Encrypt? | `securementEncryptionUser` trỏ certificate của recipient, không phải cert của sender. |
| Đúng nguồn verify? | `validationSignatureCrypto` có trust material theo policy signer; xác thực authorization. |
| Đúng nguồn decrypt? | `validationDecryptionCrypto` chứa private key của recipient, callback có key password. |
| Không lẫn password? | Store password, key-entry password, HSM PIN được quản trị rõ. |
| Không lẫn alias/name? | Alias khác subject/SAN/fingerprint; không dựa vào hai store có cùng label. |
| Hỗ trợ đúng Spring-WS version? | `wss4j2`/`CryptoFactoryBean` setters đã được xác nhận ở JAR thực tế. |
| TLS alias độc lập SOAP? | JSSE `KeyManager` được kiểm tra, không dùng WSS4J alias để chọn mTLS. |
| TLS trust độc lập WS-Security trust? | TrustManager/hostname validation và signer trust có policy rõ. |
| KeyUsage/EKU phù hợp? | TLS client/server hoặc WS-Security có algorithms/extensions theo profile. |
| Private key bảo vệ an toàn? | Không commit vào source/image công khai; secrets/permissions/HSM audit phù hợp. |
| Có key rotation plan? | Signer trust overlap, recipient decrypt key overlap, reload/rollback có test. |
| Có full test? | Ký, verify, encrypt, decrypt, TLS/mTLS, Fault và negative cases. |
| Interoperability pass? | Java/.NET/partner stack thống nhất KeyInfo, algorithms, certificates và signed parts. |
| Monitoring an toàn? | Expiry, failure codes, fingerprints được phép; không in private key/password/raw WS-Security. |

## 15. Nguồn tham khảo và cách kiểm chứng API

Các tài liệu chính thức nên được đối chiếu với **phiên bản Java/Spring-WS đang sử dụng**:

- **Oracle — [Java KeyStore API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyStore.html)**: `PrivateKeyEntry`, `SecretKeyEntry`, `TrustedCertificateEntry`, alias, `getCertificate` và `getKey`.
- **Oracle — [keytool command reference (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)**: `-list`, `-genkeypair`, `-exportcert`, `-importcert`, `-importkeystore`, store types và mật khẩu.
- **Oracle — [X509ExtendedKeyManager](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/X509ExtendedKeyManager.html)**: `chooseEngineClientAlias`/`chooseEngineServerAlias`.
- **Oracle — [X509KeyManager](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/X509KeyManager.html)**: key aliases và certificate chain trong TLS.
- **Spring-WS — [Reference Documentation 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)**: `Wss4jSecurityInterceptor`, digital signatures, encryption/decryption và certificate authentication.
- **Spring-WS — [CryptoFactoryBean API 4.1.x](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/security/wss4j2/support/CryptoFactoryBean.html)**: keyStoreLocation/type/password/defaultX509Alias.
- **Spring-WS — [Wss4jSecurityInterceptor API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/security/wss4j2/Wss4jSecurityInterceptor.html)**: securement/validation action properties.
- **Spring-WS — [KeyStoreCallbackHandler API 4.1.x](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/security/wss4j2/callback/KeyStoreCallbackHandler.html)**: private key password và symmetric key callbacks.

**Không áp dụng tên class của WSS4J đời cũ** (`wss4j` package thay vì `wss4j2` ở một số Spring-WS versions), và không suy các thuật toán mặc định luôn giống nhau giữa WSS4J/Java versions. API, provider, JDK crypto policy và PKI profiles đều cần được kiểm thử với runtime thật.

### Ghi nhớ

- **Keystore format, entry type và alias là ba khái niệm khác nhau**. `PKCS12`/`JKS` là định dạng; `PrivateKeyEntry`/`TrustedCertificateEntry` là loại dữ liệu; alias là tên cục bộ dùng để chọn entry.
- **Ký SOAP dùng private key của người gửi; xác minh dùng public certificate và trust/authorization policy. Mã hóa cho đối tác dùng public certificate của người nhận; giải mã cần private key của chính người nhận.**
- Trong Spring-WS/WSS4J, `securementUsername` chọn alias ký outbound, `securementEncryptionUser` chọn recipient cert, `validationSignatureCrypto` phục vụ verify và `validationDecryptionCrypto` + password callback phục vụ decrypt.
- **TLS/mTLS chọn local identity bằng JSSE KeyManager**, độc lập với WSS4J; TLS truststore và SOAP signature trust không được tự xem là một.
- **Alias không chứng minh certificate identity**. Kiểm tra entry type, certificate chain/fingerprint, validity, KeyUsage/EKU, trust và quyền nghiệp vụ.
- **PKCS#12 được ưu tiên cho nhiều tích hợp mới**, nhưng phải kiểm tra provider và migration; không đưa private keys hoặc passwords thật vào source, logs hay test fixtures.
- **Rotation phải phối hợp cả hai phía**: signer public cert được trust trước khi gửi chữ ký mới, recipient private key sẵn sàng trước khi bên gửi đổi public encryption certificate; giữ khóa cũ chỉ trong khoảng thời gian được phê duyệt.
- **Kiểm thử SOAP và TLS thực tế, bao gồm negative tests**, mới chứng minh keystore/alias đang phục vụ đúng mục đích trong hệ thống tích hợp doanh nghiệp.







