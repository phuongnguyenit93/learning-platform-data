# Định dạng PEM, PKCS#8 và kho khóa trong môi trường triển khai Spring Security SAML 2.0

## 1. Mục tiêu bài học

Trong hệ thống **Spring Security – federation**, ứng dụng Spring Boot thường đóng vai **Service Provider (SP/Relying Party)** và tích hợp một hoặc nhiều **Identity Provider (IdP/Asserting Party)**. SP cần certificate/khóa cho các nhiệm vụ khác nhau:

- Dùng **private key SP** để **ký AuthnRequest** hoặc thông điệp SAML do SP phát hành nếu cấu hình yêu cầu.
- Dùng **private key SP** để **giải mã EncryptedAssertion/EncryptedID** mà IdP mã hóa cho SP.
- Dùng **public certificate IdP** để **xác minh chữ ký SAML Response/Assertion** do IdP gửi.
- Nếu hệ thống yêu cầu **signed metadata**, dùng **metadata signer trust anchor** được cấp và xác minh riêng để kiểm tra tài liệu metadata trước khi tin các certificate bên trong.

Một khó khăn rất thường gặp: có đầy đủ file `.pem`, `.key`, `.crt`, `.p12` nhưng Spring Security vẫn báo lỗi đọc private key, certificate không khớp, không ký được AuthnRequest hoặc không giải mã được assertion. Lý do là **định dạng biểu diễn**, **cấu trúc khóa**, **nơi lưu**, **mục đích sử dụng** và **trust policy** là những khái niệm khác nhau.

Bài học thuộc nhóm **Khóa và chứng thư** và giải thích có hệ thống:

1. **PEM, DER, PKCS#8, PKCS#1, X.509, PKCS#12, JKS, PKCS#11** khác nhau ra sao.
2. Cách phân biệt certificate công khai, public key và private key; nhận biết nhãn `BEGIN ...` đúng.
3. Cách chuyển đổi khóa an toàn với OpenSSL và kiểm tra cặp khóa–certificate.
4. Cách Spring Boot/Spring Security đọc **file PEM/PKCS#8** làm signing/decryption credentials, hoặc dùng **Java KeyStore PKCS#12** thông qua code.
5. Cách quản lý khóa trong server, container, Kubernetes, HSM/secret manager, môi trường đa IdP và thời kỳ rotation.
6. Kiểm thử lỗi cấu hình, certificate rollover, quyền truy cập, thuật toán và quy trình triển khai an toàn.

**Nguyên tắc xuyên suốt:** giải được file private key chỉ là bước đầu. Chỉ khi **đúng cặp khóa, đúng registration, đúng purpose, đúng trust và quyền truy cập được quản trị** thì vật liệu mật mã mới phù hợp cho SAML2 production.

## 2. Phân tách ba lớp: encoding, cấu trúc và kho lưu khóa

Hãy xem các thuật ngữ theo ba trục độc lập:

| Lớp | Ví dụ | Câu hỏi mà nó trả lời |
| --- | --- | --- |
| **Biểu diễn/encoding** | PEM, DER | Dữ liệu khóa/chứng thư được biểu diễn thành text Base64 hay binary? |
| **Cấu trúc bên trong** | PKCS#8 PrivateKeyInfo, PKCS#1 RSAPrivateKey, X.509 certificate, SubjectPublicKeyInfo | Bytes được giải mã chứa loại đối tượng mật mã nào? |
| **Kho chứa / truy cập** | PKCS#12 `.p12/.pfx`, JKS, HSM PKCS#11, secret manager | Có bao nhiêu entry, alias/chain, mật khẩu, quyền truy cập và nơi giữ key? |

Ví dụ cùng **một RSA private key** có thể tồn tại dưới nhiều dạng:

```text
RSA private key
   |
   +-- ASN.1 PKCS#1 -> DER -> PEM "BEGIN RSA PRIVATE KEY"
   |
   +-- ASN.1 PKCS#8 -> DER -> PEM "BEGIN PRIVATE KEY"
   |
   +-- PKCS#8 encrypted -> DER -> PEM "BEGIN ENCRYPTED PRIVATE KEY"
   |
   +-- PrivateKeyEntry trong PKCS#12 keystore (kèm X.509 certificate chain)
   |
   +-- Non-exportable key trong HSM, Java ứng dụng thấy qua PKCS#11 provider
```

**`.pem`, `.key` và `.crt` là tên file theo quy ước**, không bảo đảm định dạng thực. Một file `server.key` vẫn có thể chứa PKCS#1 hoặc PKCS#8; một file `idp.crt` có thể là PEM X.509 hoặc DER X.509. Muốn biết thật, phải đọc nhãn, parse đúng cấu trúc và xác minh bằng công cụ thích hợp.

### 2.1. PEM khác DER

**DER** (*Distinguished Encoding Rules*) là định dạng **binary ASN.1**. **PEM** là dạng “bọc” nội dung binary (thường là DER) thành **Base64 có nhãn BEGIN/END**, thích hợp truyền trong file text.

Ví dụ cấu trúc PEM:

```text
-----BEGIN CERTIFICATE-----
MIIB...base64-encoded-X509-certificate...
-----END CERTIFICATE-----
```

Chuỗi Base64 trong ví dụ **chỉ là ký hiệu minh họa**, không phải một certificate thật.

PEM **không tự chỉ** khóa thuộc PKCS#8 hay PKCS#1; thông tin ấy thể hiện qua loại đối tượng DER và nhãn. Đổi đuôi file `.key` thành `.pem` **không chuyển đổi cấu trúc khóa**. Tương tự, đưa bytes PKCS#1 vào một file rồi đổi tên thành `pkcs8.pem` không làm nó trở thành PKCS#8 hợp lệ.

## 3. Cách đọc PEM label và ý nghĩa kỹ thuật

| PEM header | Nội dung thông thường | Mức độ phù hợp với Spring/Java |
| --- | --- | --- |
| `-----BEGIN CERTIFICATE-----` | X.509 certificate công khai (ASN.1 DER được Base64 hóa) | `CertificateFactory.getInstance("X.509")` thường đọc được |
| `-----BEGIN PRIVATE KEY-----` | **PKCS#8 PrivateKeyInfo không mã hóa bằng passphrase** | Phù hợp với `PKCS8EncodedKeySpec` hoặc `RsaKeyConverters.pkcs8()` nếu thuật toán hỗ trợ |
| `-----BEGIN ENCRYPTED PRIVATE KEY-----` | **Encrypted PKCS#8** có thuật toán PBE/password | Cần loader giải mã tương thích; không đưa thẳng vào API chỉ nhận unencrypted PKCS#8 |
| `-----BEGIN RSA PRIVATE KEY-----` | **PKCS#1 RSA private key** kiểu truyền thống | Không được tự coi là PKCS#8; cần converter hỗ trợ hoặc chuyển đổi |
| `-----BEGIN EC PRIVATE KEY-----` | **SEC1 EC private key** kiểu truyền thống | Không phải RSA PKCS#8; loader/provider phải hỗ trợ EC |
| `-----BEGIN PUBLIC KEY-----` | **SubjectPublicKeyInfo (SPKI)** của public key | Có thể dùng `X509EncodedKeySpec`, nhưng **không phải X.509 certificate** |
| `-----BEGIN RSA PUBLIC KEY-----` | Public key RSA cấu trúc PKCS#1 | Khác SPKI, không đưa nguyên vào `X509EncodedKeySpec` |
| `-----BEGIN CERTIFICATE REQUEST-----` | Certificate Signing Request (CSR) PKCS#10 | Dùng yêu cầu cấp cert, không phải certificate cấp cho SAML partner |

**Cần phân biệt hai từ “X.509”:**

- `X509Certificate` là một **certificate** có subject, issuer, validity, public key, signature của certificate, v.v.
- `X509EncodedKeySpec` của JCA lại biểu diễn **public key dạng SPKI**. Nó **không** parse một `BEGIN CERTIFICATE` thành certificate.

Đừng lấy bytes DER của certificate rồi đưa vào `new X509EncodedKeySpec(bytes)`; nếu cần certificate, dùng `CertificateFactory`. Ngược lại, `BEGIN PUBLIC KEY` chỉ có public key, không mang chain, thời hạn hay thông tin chứng thực đối tác tương đương X.509 certificate.

### 3.1. PEM không phải một cơ chế bảo mật

PEM chỉ là **cách biểu diễn text**. Một file `BEGIN PRIVATE KEY` có thể chứa private key **không mã hóa**, ai đọc được file thì có thể sử dụng khóa. “File có đuôi `.pem`” hoặc “file được Base64 hóa” **không** có nghĩa đã được bảo mật. Tính bí mật đến từ cơ chế bảo vệ storage, mã hóa tại nơi lưu, secret management, quyền truy cập, audit và quản lý vòng đời.

## 4. PKCS#8 là gì? Có bắt buộc RSA không?

**PKCS#8** định nghĩa cấu trúc lưu **private-key information** bao gồm định danh thuật toán và bytes khóa. Nó hỗ trợ nhiều loại khóa (RSA, EC và loại được provider hỗ trợ), không chỉ RSA.

Có hai trường hợp cần phân biệt:

1. **PrivateKeyInfo không mã hóa**: thường là `BEGIN PRIVATE KEY`; Java `PKCS8EncodedKeySpec` được thiết kế cho dữ liệu này.
2. **EncryptedPrivateKeyInfo**: thường là `BEGIN ENCRYPTED PRIVATE KEY`; cần **mật khẩu và thuật toán giải mã PBE** tương ứng để lấy PrivateKeyInfo trước khi tạo đối tượng PrivateKey.

**PKCS#8 không đồng nghĩa “khóa đã mã hóa”.** Một file PKCS#8 chưa mã hóa vẫn nguy hiểm nếu bị đọc trộm. PKCS#8 cũng **không phải một kho khóa nhiều entry** như PKCS#12.

### 4.1. PKCS#1 và PKCS#8 khác nhau ở đâu?

**PKCS#1 RSAPrivateKey** chứa các tham số riêng của RSA, ví dụ modulus và các hệ số CRT. **PKCS#8 PrivateKeyInfo** bọc khóa riêng bằng thông tin thuật toán chung (ví dụ OID của RSA), giúp hệ thống đọc theo một cấu trúc thống nhất.

Dạng biểu diễn:

```text
PKCS#1 RSA key:
  RSAPrivateKey { version, modulus, publicExponent,
                  privateExponent, prime1, prime2, ... }

PKCS#8:
  PrivateKeyInfo {
      version,
      privateKeyAlgorithm = rsaEncryption,
      privateKey = OCTET STRING chứa dữ liệu thuật toán tương ứng,
      ...
  }
```

Khi dùng `KeyFactory.generatePrivate(new PKCS8EncodedKeySpec(bytes))`, bytes phải đúng PKCS#8 và algorithm phải được `KeyFactory` hỗ trợ. Nếu đưa PKCS#1 vào sẽ thường gặp `InvalidKeySpecException`, `InvalidKeyException` hoặc thông báo phân tích ASN.1.

Không giải quyết bằng cách “thêm dòng BEGIN PRIVATE KEY” quanh bytes PKCS#1. Cần **chuyển cấu trúc** với công cụ chuẩn, không chỉ đổi header.

### 4.2. Còn PKCS#12 thì sao?

**PKCS#12** là **keystore/container** thường mang private key, certificate và certificate chain, có thể chứa nhiều entry với alias và bảo vệ bằng mật khẩu. File thường có đuôi `.p12` hoặc `.pfx`.

PKCS#8 là **đối tượng private key**; PKCS#12 là **container chứa key và cert**. Hai chuẩn không thay thế cho nhau chỉ bằng đổi đuôi file.

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Một cặp private key + certificate do Spring Boot đọc theo location | PEM PKCS#8 và PEM X.509 với secret mount an toàn |
| Nhiều keypair, certificate chain, alias và password quản lý qua Java | PKCS#12 KeyStore |
| Dự án Java legacy dùng keystore cũ | JKS, cân nhắc migrate phù hợp |
| Khóa không được xuất vào file | HSM/PKCS#11 hoặc KMS/remote signer được tích hợp qua provider |
| Chỉ tin public certificate IdP để verify assertion | Public cert/pinned trust config; không cần private key IdP |

Tài liệu JDK 17 xác nhận **PKCS12 là loại keystore mặc định được khuyến nghị từ JDK 9**, còn JKS là định dạng riêng của Java. PKCS11 là một giao diện cho token/HSM, **không phải một file `.p11` thường dùng như `.p12`**.

## 5. Phân biệt khóa SP và chứng thư IdP trong SAML2

Trong `RelyingPartyRegistration`, thường phải nhìn hai phía:

```text
RelyingPartyRegistration "corp"
│
├── Relying party (SP)
│   ├── entityId: urn:example:portal:prod:sp
│   ├── signing credential:
│   │      private key SP + X.509 certificate SP
│   └── decryption credential:
│          private key SP + X.509 certificate SP
│
└── Asserting party (IdP)
    ├── entityId: https://idp.example.test/saml
    ├── verification credentials:
    │      public X.509 certificate của IdP
    └── SSO endpoint, metadata và binding
```

| Vai trò | Private key do ai giữ? | Dùng khi nào? | Điểm dễ nhầm |
| --- | --- | --- | --- |
| SP signing | **SP** | SP ký AuthnRequest/LogoutRequest theo profile | Dùng nhầm IdP public cert cho signing |
| SP decryption | **SP** | SP giải mã EncryptedAssertion gửi đến SP | Chỉ có cert SP mà thiếu private key |
| IdP verification | **IdP** | SP xác minh response/assertion do IdP ký | Tự nhập một certificate lạ từ response |
| IdP encryption recipient (nếu có) | **IdP** | SP mã hóa assertion/message gửi đến IdP khi profile yêu cầu | Nhầm với SP decryption private key |
| Metadata signature verification | Metadata signer/aggregator | SP xác minh signed metadata | Tự tin signer certificate do metadata chưa xác minh cung cấp |

**Public certificate và private key SP phải tương ứng về public key**, nhưng certificate có thể tự ký hoặc do CA cấp tùy thỏa thuận SAML. Trong SAML federation, IdP thường **pin/đăng ký certificate cụ thể theo SP Entity ID**, không tự xem một chứng thư TLS bất kỳ là SP signing credential đáng tin.

Ngược lại, SP phải biết đúng certificate của IdP theo **nguồn metadata/trust configuration đã xác thực**. Một certificate có chuỗi X.509 hợp lệ không tự chứng minh IdP entityId được phép phát assertion cho ứng dụng.

### 5.1. Tại sao nên tách signing và decryption?

Một tổ chức có thể dùng cùng cặp khóa cho SP signing và decryption nếu hai bên và library hỗ trợ. Tuy nhiên, tách hai mục đích giúp:

- Xoay private key SP signing mà không đồng thời phá khả năng giải mã assertion đang bay.
- Giới hạn phạm vi tác động khi một private key bị lộ.
- Có lịch sử kiểm toán khác nhau cho hoạt động ký và giải mã.
- Duy trì nhiều decryption keys trong cửa sổ đổi certificate IdP sử dụng, trong khi vẫn chỉ ký bằng key hiện hành.

Nếu chọn dùng chung, hãy ghi rõ **purpose** và key rotation policy. Đừng tự cấu hình cùng một certificate cho cả signing/decryption chỉ vì hai property cạnh nhau.

## 6. Lệnh OpenSSL: kiểm tra và chuyển đổi định dạng an toàn

Những lệnh sau giả định chạy **trong môi trường thử nghiệm hoặc máy quản trị được ủy quyền**, sử dụng OpenSSL hiện đại. Không chạy trên private key production nếu không có quyền, quy trình phê duyệt và nơi lưu đầu ra an toàn.

### 6.1. Nhận biết loại file

Với PEM, xem **nhãn BEGIN/END** bằng trình xem text phù hợp, nhưng **không dán hay gửi toàn bộ private key lên chat, ticket, log hoặc dịch vụ web**.

Kiểm tra certificate công khai:

```bash
openssl x509 -in sp-cert.pem -noout -subject -issuer -dates -fingerprint -sha256
```

Lệnh hiển thị subject, issuer, thời hạn và SHA-256 fingerprint certificate. Nó **không in private key**. Tuy nhiên, fingerprint đúng chỉ có giá trị nhận dạng đối tác nếu được đối chiếu với **nguồn tin cậy riêng**, không phải fingerprint tùy ý người gửi cung cấp trên cùng một kênh bị kiểm soát.

Kiểm tra tính parse được của private key mà không xuất private key ra stdout:

```bash
openssl pkey -in sp-private.pem -check -noout
```

Lệnh có thể yêu cầu passphrase nếu key đã mã hóa. Nó không thay thế kiểm tra keypair với certificate hay đánh giá chính sách dùng khóa.

### 6.2. Chuyển PKCS#1/traditional key sang PKCS#8 không mã hóa

```bash
openssl pkcs8 -topk8 -nocrypt \
  -in sp-traditional-key.pem \
  -out sp-private-pkcs8.pem
```

`-topk8` yêu cầu viết PKCS#8. `-nocrypt` ghi **PKCS#8 không mã hóa**, thường có header `BEGIN PRIVATE KEY`. Nó thích hợp cho loader chỉ hỗ trợ unencrypted PKCS#8 **nếu private key được bảo vệ đầy đủ ở filesystem/volume**.

**Cảnh báo:** đây là thao tác **tạo bản plaintext private key mới**. Chỉ chuyển đổi trong khu vực được kiểm soát, với `umask`/quyền file phù hợp, không ghi ra thư mục chia sẻ, workspace đồng bộ, container layer, CI artifact hay log. Không giữ đồng thời nhiều bản plaintext không cần thiết. Nếu chính sách cấm private key không mã hóa trên disk, dùng PKCS#12/HSM/provider phù hợp thay vì áp dụng `-nocrypt` trong production.

### 6.3. Chuyển sang PKCS#8 có mật khẩu

```bash
openssl pkcs8 -topk8 \
  -in sp-private.pem \
  -out sp-private-encrypted-pkcs8.pem
```

OpenSSL thường yêu cầu passphrase khi tạo EncryptedPrivateKeyInfo theo cấu hình mặc định. File kết quả có thể có header `BEGIN ENCRYPTED PRIVATE KEY`. **Không tự mặc định** Spring Boot `private-key-location` hoặc `RsaKeyConverters.pkcs8()` của phiên bản đang chạy đọc được mọi thuật toán/password của EncryptedPrivateKeyInfo. Cần loader PBE/key store hoặc secret integration được kiểm thử.

Tránh truyền password thẳng trên dòng lệnh theo cách có thể lộ qua process list, shell history hoặc CI log. Nếu dùng password file/secret manager, quyền truy cập tới password phải được bảo vệ **riêng** với private key.

### 6.4. Chuyển key/cert sang kho PKCS#12

Với một cặp private key và certificate X.509 hợp lệ đã có:

```bash
openssl pkcs12 -export \
  -inkey sp-private.pem \
  -in sp-cert.pem \
  -out sp-keys.p12 \
  -name sp-signing
```

OpenSSL sẽ yêu cầu export password (và passphrase của input key nếu cần). Nếu có certificate chain đúng, có thể bổ sung `-certfile chain.pem` theo hợp đồng; không tự ghép các CA không liên quan. Việc xuất PKCS#12 tạo ra **một container chứa private key**; phải bảo vệ `.p12` và password như một secret, không chỉ tin rằng file “có password” là đủ.

Kiểm tra alias/entry/chain mà không yêu cầu in private key:

```bash
keytool -list -v -storetype PKCS12 \
  -keystore sp-keys.p12
```

`keytool` có thể yêu cầu mật khẩu. Kiểm tra alias, entry type (ví dụ `PrivateKeyEntry`), certificate subject/issuer, validity, chain, và đảm bảo alias mà code Java sử dụng tồn tại. **Không** dùng `keytool -list` để chứng minh cert tương ứng private key nếu chưa kiểm cặp khóa.

### 6.5. Đối chiếu public key của private key với certificate

Một cặp private key và certificate phải có **public key tương ứng**. Kiểm tra không cần hiển thị private key:

```bash
openssl pkey -in sp-private.pem -pubout -outform DER \
  | openssl dgst -sha256

openssl x509 -in sp-cert.pem -pubkey -noout \
  | openssl pkey -pubin -outform DER \
  | openssl dgst -sha256
```

Hai kết quả SHA-256 của **SPKI DER đã được chuẩn hóa cùng cách** phải bằng nhau đối với cặp khóa tương ứng. Lệnh minh họa dùng pipeline binary của shell POSIX; nếu chạy PowerShell cũ có thể cần cách xử lý binary riêng để tránh đổi bytes trong pipe.

Việc match public key **không tự xác thực đối tác**, không chứng minh certificate đang còn hiệu lực/được chấp nhận hoặc private key chưa bị lộ. Đó chỉ là kiểm tra tương ứng keypair.

### 6.6. Tạo cặp RSA thử nghiệm để hiểu pipeline

Trong **môi trường lab**, bạn có thể tạo RSA key và self-signed certificate minh họa:

```bash
openssl genpkey -algorithm RSA \
  -pkeyopt rsa_keygen_bits:3072 \
  -out lab-sp-private.pem

openssl req -new -x509 \
  -key lab-sp-private.pem \
  -out lab-sp-certificate.pem \
  -days 30 \
  -subj "/CN=lab-saml-sp"
```

Self-signed certificate **không tự biến SP thành đối tác được tin**. IdP phải có hợp đồng/cấu hình import đúng public cert; lab dùng để test parser, certificate/key matching và luồng tạo credentials. Private key lab vẫn cần được bảo vệ, không đưa vào repository.

## 7. Spring Boot: khai báo PEM và PKCS#8 theo Resource location

Ví dụ dưới đây nhắm tới Spring Boot 3.x / Spring Security 6.x và ứng dụng **Servlet SAML2 Relying Party**, đã có `spring-security-saml2-service-provider`. Cấu hình thật phải gắn với IdP metadata/certificate đã xác minh.

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:example:portal:prod:sp"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-sign-pkcs8.pem"
                  certificate-location: "file:/etc/saml/certs/sp-sign.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-decrypt-pkcs8.pem"
                  certificate-location: "file:/etc/saml/certs/sp-decrypt.crt"
            assertingparty:
              metadata-uri: "file:/etc/saml/idp-metadata.xml"
```

**Giải thích chính xác:**

- `corp` là **registrationId** của mối quan hệ SP–IdP, không phải alias trong PKCS#12 và không phải SP Entity ID.
- `entity-id` là SP Entity ID mà IdP cần dùng làm audience và định danh SP theo hợp đồng.
- `signing.credentials[*]` nạp **private key SP signing** và X.509 certificate tương ứng để ký AuthnRequest/thông điệp phù hợp.
- `decryption.credentials[*]` nạp **private key SP decryption** và X.509 certificate tương ứng cho EncryptedAssertion/EncryptedID.
- `assertingparty.metadata-uri` chỉ tới metadata IdP; nó **không phải** đường dẫn private key và không tự chứng minh metadata đã được xác minh chữ ký. Quản lý nguồn metadata/trust riêng.
- `file:` tham chiếu đường dẫn filesystem trong **container hoặc máy đang chạy JVM**, không phải thư mục của developer.
- `classpath:` tham chiếu tài nguyên được đóng gói theo classpath; **không phù hợp để nhúng private key production vào JAR/image**, vì nhiều người có thể đọc artifact.
- `sp-sign-pkcs8.pem` và `sp-decrypt-pkcs8.pem` trong ví dụ phải là key format được loader hỗ trợ; đừng bỏ encrypted PKCS#8 vào property location rồi mặc nhiên trông đợi boot tự xử lý passphrase.

Khi một IdP không yêu cầu AuthnRequest signed hoặc không gửi EncryptedAssertion, bộ credential tối thiểu sẽ khác. **Không bắt buộc thêm private key chỉ để nhận SAML Response có chữ ký**: SP vẫn phải có **public verification certificate IdP**. Khi bài này cấu hình cả signing và decryption, đó là một ví dụ hệ thống có **cả hai yêu cầu**.

### 7.1. Classpath vs file trong ba môi trường

| Môi trường | Thường dùng | Điều cần tránh |
| --- | --- | --- |
| Local development | Key demo tự sinh, riêng ngoài source tree hoặc profile test | Commit file private key demo rồi dùng lại trong staging/prod |
| VM/bare metal | File/keystore trong thư mục bảo mật, chỉ service account được đọc | `chmod 777`, thư mục home dùng chung, backup không mã hóa |
| Docker/Kubernetes | Secret volume hoặc CSI/Vault mount; file path trong container | `COPY private.key` vào image, đưa secret vào image build args/layers |
| HSM/PKCS#11 | Handle/provider/API ký/giải mã, key không được xuất | Ép phải export private key plaintext để tương thích YAML |
| Cloud KMS | API/provider cho signing/decryption phù hợp thuật toán | Nhầm API “lưu secret” với khả năng ký XMLDSig/RSA-OAEP tương thích |

**Một lưu ý quan trọng:** Spring Boot property `private-key-location` là cách thuận tiện khi key tồn tại ở dạng file mà converter hỗ trợ. Nó **không có nghĩa tự động nhận mọi alias PKCS#12, mọi HSM handle hoặc mọi encrypted PEM**; với các loại này thường cần cung cấp `RelyingPartyRegistration`/credential qua cấu hình Java và provider thích hợp.

## 8. Spring Security Java: đọc PEM X.509 và RSA PKCS#8

Tài liệu Spring Security có ví dụ `RsaKeyConverters.pkcs8()` để đọc RSA private key và `CertificateFactory.getInstance("X.509")` để đọc certificate.

Đoạn dưới là **một method/trích đoạn trong dự án Spring đã có các imports/dependencies**, không phải file Java độc lập:

```java
import java.io.InputStream;
import java.security.interfaces.RSAPrivateKey;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.security.converter.RsaKeyConverters;
import org.springframework.security.saml2.core.Saml2X509Credential;

// Private key RSA PKCS#8 không mã hóa được bảo vệ bằng secret volume.
Resource keyFile = new FileSystemResource(
    "/run/secrets/saml/sp-sign-pkcs8.pem");
Resource certificateFile = new FileSystemResource(
    "/etc/saml/certs/sp-sign.crt");

RSAPrivateKey privateKey;
try (InputStream in = keyFile.getInputStream()) {
    privateKey = RsaKeyConverters.pkcs8().convert(in);
}

X509Certificate certificate;
try (InputStream in = certificateFile.getInputStream()) {
    certificate = (X509Certificate)
        CertificateFactory.getInstance("X.509")
            .generateCertificate(in);
}

Saml2X509Credential signingCredential =
    Saml2X509Credential.signing(privateKey, certificate);
```

Điểm cần hiểu:

- `RsaKeyConverters.pkcs8()` là **converter riêng cho RSA PKCS#8** theo API Spring Security; không tự hiểu mọi loại PKCS#1, EC, encrypted PKCS#8 và HSM key.
- `CertificateFactory` parse **public certificate X.509**, không cần private key để đọc.
- `Saml2X509Credential.signing(...)` biểu diễn mục đích **SP ký thông điệp SAML**. Với **SP giải mã**, sử dụng `Saml2X509Credential.decryption(privateKey, certificate)`.
- Nạp được key/cert chưa chứng minh cặp key khớp; kiểm tra trước khi hệ thống bắt đầu nhận traffic.
- `try-with-resources` đóng stream, nhưng đối tượng private key vẫn tồn tại trong process memory theo vòng đời credential; quản trị host/container và dump/heap tương ứng.

Không tải private key IdP vào SP. SP chỉ cần public certificate IdP đã được provision đáng tin cho **verification**, qua `Saml2X509Credential.verification(idpCert)` hoặc metadata IdP đã kiểm chứng theo chính sách.

### 8.1. Đưa credentials vào RelyingPartyRegistration

Ví dụ tiếp theo sử dụng biến `signingCredential` và `decryptionCredential` đã được tạo từ nguồn an toàn:

```java
RelyingPartyRegistration registration = RelyingPartyRegistrations
    .fromMetadataLocation("file:/etc/saml/idp-metadata.xml")
    .registrationId("corp")
    .entityId("urn:example:portal:prod:sp")
    .signingX509Credentials(
        credentials -> credentials.add(signingCredential))
    .decryptionX509Credentials(
        credentials -> credentials.add(decryptionCredential))
    .build();
```

Đây là **mảnh cấu hình Java trong Spring Security**, cần bean `RelyingPartyRegistrationRepository`, Java imports và phiên bản API tương ứng. `fromMetadataLocation(...)` chỉ là cơ chế nhập metadata; **không đồng nghĩa đã thỏa chính sách xác minh signed metadata**. Khi dùng custom repository thay auto-configuration của Spring Boot, phải bảo đảm filter chain **thực sự tham chiếu đúng repository đó**.

## 9. Đọc PKCS#12 KeyStore bằng Java

Nếu tổ chức cấp `sp-keys.p12` thay vì cặp file PEM, JCA cung cấp `KeyStore.getInstance("PKCS12")`. Một PKCS#12 có thể chứa **PrivateKeyEntry** với alias `sp-signing` và certificate chain.

**Trích đoạn Java dùng trong ứng dụng có keystore đã được provision**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;

char[] storePassword = obtainPasswordFromProtectedSource();
char[] keyPassword = obtainKeyPasswordFromProtectedSource();

KeyStore store = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(
        Path.of("/run/secrets/saml/sp-keys.p12"))) {
    store.load(in, storePassword);
}

Key key = store.getKey("sp-signing", keyPassword);
Certificate certificate = store.getCertificate("sp-signing");

if (!(key instanceof PrivateKey privateKey)
        || !(certificate instanceof X509Certificate x509Certificate)) {
    throw new IllegalStateException(
        "sp-signing must be a PrivateKeyEntry with X509Certificate");
}

Saml2X509Credential credential =
    Saml2X509Credential.signing(privateKey, x509Certificate);
```

**Giới hạn ví dụ:** `obtainPasswordFromProtectedSource()` là tên mô tả việc cấp password từ secret manager/file protected do ứng dụng triển khai, **không phải API JDK**; trích đoạn không chạy độc lập. Trong ứng dụng thật, cần quản lý lỗi `UnrecoverableKeyException`, alias không tồn tại, quyền file và xóa các **char[] bản sao password** khi không cần, trong phạm vi còn kiểm soát được. Nếu PKCS#12 dùng chung store/key password, cả hai biến có thể lấy từ cùng một nguồn bảo mật; không giả định mọi keystore đều cho phép password khác nhau hoặc mọi provider xử lý alias giống nhau.

**Ưu điểm PKCS#12:** nhiều alias, certificate chain, mật khẩu và API KeyStore chuẩn Java. **Hạn chế:** Spring Boot `private-key-location: file:/.../sp-keys.p12` thông thường **không tự giải nghĩa alias `sp-signing` như KeyStore API**. Muốn dùng `.p12`, hãy tải qua KeyStore/provider rồi cung cấp `Saml2X509Credential` cho `RelyingPartyRegistration` (hoặc dùng tích hợp do phiên bản/framework cung cấp được kiểm chứng).

### 9.1. Keystore và truststore khác mục đích, không khác bắt buộc định dạng

- **Keystore** thường chứa **private key của chính ứng dụng**, certificate và chain.
- **Truststore** thường chứa **certificate/public trust anchors của bên khác** để ứng dụng xác minh chúng.
- **PKCS#12** có thể dùng làm **keystore hoặc truststore**; chữ “store” biểu thị chức năng sử dụng, không bắt buộc loại file.
- **Truststore TLS mặc định của JVM** thường gồm nhiều CA tin cậy cho HTTPS. Nó **không tự động là danh sách IdP được phép ký assertion SAML**. SAML trust cần gắn certificate với **IdP Entity ID/registration** và chính sách đã phê duyệt.

Ví dụ IdP certificate công khai có thể được import vào PKCS#12 truststore riêng:

```bash
keytool -importcert -storetype PKCS12 \
  -alias corp-idp-signing \
  -file idp-signing.crt \
  -keystore saml-idp-trust.p12
```

**Chỉ import sau khi nguồn certificate được xác minh** qua metadata/kênh quản trị IdP đáng tin. Nếu import certificate do một response hoặc email chưa kiểm chứng cung cấp, một truststore được bảo vệ rất kỹ vẫn có thể chứa **khóa của kẻ tấn công**.

## 10. Java 17 độc lập: PEM và PKCS#8 round-trip không cần thư viện ngoài

Chương trình này được thiết kế để **biên dịch/chạy bằng JDK 17+**, không cần Spring Security hay OpenSSL. Nó minh họa:

- Tạo RSA keypair test 2048-bit.
- Lấy private key ở dạng **PKCS#8 DER** từ `PrivateKey.getEncoded()`.
- Đóng gói private DER vào **PEM `BEGIN PRIVATE KEY`**.
- Đóng gói public key `SubjectPublicKeyInfo` vào **PEM `BEGIN PUBLIC KEY`**.
- Parse lại bằng `PKCS8EncodedKeySpec` và `X509EncodedKeySpec`.
- Ký/verify một chuỗi dữ liệu giả lập; thay dữ liệu sẽ làm verification thất bại.
- Từ chối dùng một PEM mang header `PUBLIC KEY` như thể nó là `PRIVATE KEY`.

**Phạm vi:** đây chỉ là ví dụ kiểm tra encoding/PKCS#8 và chữ ký RSA. Nó **không tạo X.509 certificate**, không xây PKCS#12 keystore, không ký AuthnRequest XML, không cấu hình SAML federation và **không nên in privatePem ra log**.

Tệp `PemPkcs8Demo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;

public class PemPkcs8Demo {
    static String toPem(String label, byte[] der) {
        String body = Base64.getMimeEncoder(
            64, new byte[] {'\n'}).encodeToString(der);
        return "-----BEGIN " + label + "-----\n" + body
            + "\n-----END " + label + "-----\n";
    }

    static byte[] fromPem(String pem, String label) {
        String header = "-----BEGIN " + label + "-----";
        String footer = "-----END " + label + "-----";
        String cleaned = pem.trim();
        if (!cleaned.startsWith(header) || !cleaned.endsWith(footer)) {
            throw new IllegalArgumentException("Unexpected PEM label");
        }
        String content = cleaned.substring(
            header.length(), cleaned.length() - footer.length());
        return Base64.getMimeDecoder().decode(content);
    }

    static byte[] sign(PrivateKey key, String value) throws Exception {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(key);
        signer.update(value.getBytes(StandardCharsets.UTF_8));
        return signer.sign();
    }

    static boolean verify(PublicKey key, String value, byte[] signed)
            throws Exception {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(value.getBytes(StandardCharsets.UTF_8));
        return verifier.verify(signed);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        String privatePem = toPem("PRIVATE KEY",
            pair.getPrivate().getEncoded());
        String publicPem = toPem("PUBLIC KEY",
            pair.getPublic().getEncoded());

        KeyFactory factory = KeyFactory.getInstance("RSA");
        PrivateKey privateKey = factory.generatePrivate(
            new PKCS8EncodedKeySpec(
                fromPem(privatePem, "PRIVATE KEY")));
        PublicKey publicKey = factory.generatePublic(
            new X509EncodedKeySpec(
                fromPem(publicPem, "PUBLIC KEY")));

        byte[] signature = sign(privateKey, "AuthnRequest");
        System.out.println("privateFormat=" + privateKey.getFormat());
        System.out.println("privateHeader="
            + privatePem.startsWith("-----BEGIN PRIVATE KEY-----"));
        System.out.println("publicHeader="
            + publicPem.startsWith("-----BEGIN PUBLIC KEY-----"));
        System.out.println("validSignature="
            + verify(publicKey, "AuthnRequest", signature));
        System.out.println("tamperingDetected="
            + !verify(publicKey, "ChangedRequest", signature));

        boolean rejected = false;
        try {
            fromPem(publicPem, "PRIVATE KEY");
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("wrongPemLabelRejected=" + rejected);
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac --release 17 PemPkcs8Demo.java
java PemPkcs8Demo
```

Stdout chính xác trong một triển khai JDK 17 với provider RSA thông thường:

```text
privateFormat=PKCS#8
privateHeader=true
publicHeader=true
validSignature=true
tamperingDetected=true
wrongPemLabelRejected=true
```

**Giải thích kết quả:**

- `privateFormat=PKCS#8`: đối tượng private key đã parse mang dạng PKCS#8.
- `privateHeader=true`: chuỗi được đóng gói dưới nhãn **PRIVATE KEY**, đúng cho unencrypted PKCS#8 trong ví dụ.
- `publicHeader=true`: public key có nhãn **PUBLIC KEY**, nhưng **không phải CERTIFICATE**.
- `validSignature=true`: private/public key thuộc cùng cặp RSA.
- `tamperingDetected=true`: chữ ký của “AuthnRequest” không xác minh được trên “ChangedRequest”.
- `wrongPemLabelRejected=true`: ứng dụng không diễn giải public PEM như private PEM.

Đoạn `fromPem` cố tình **chỉ xử lý một block PEM do chương trình tự sinh**, không phải parser PEM production. Không cho dữ liệu file/XML do attacker gửi vào được dùng như một parser có kiểm tra định dạng hoàn chỉnh. Nó không hỗ trợ encrypted PKCS#8, multiple PEM blocks, password, comment tùy ý, certificate chain hoặc thuật toán EC.

Trong production, **không tự in PEM private key** để debug. Nếu key là HSM không export được, `getEncoded()` có thể trả `null` hoặc bị chặn theo provider; đó có thể là một **tính năng bảo mật**, không phải lỗi cần ép xuất key.

## 11. Secret file, biến môi trường, HSM và KMS: chọn đường cấp khóa

Khi triển khai ứng dụng, có nhiều cách đưa vật liệu mật mã đến JVM:

| Cách cấp phát | Ưu điểm | Rủi ro và điều kiện |
| --- | --- | --- |
| Secret file/volume read-only | Tương thích `file:` Resource, dễ phân quyền filesystem | Nếu mount/host bị đọc trộm thì key lộ; cần quyền và rotation |
| PKCS#12 file + password | Một container có alias/chain; dễ dùng JCA KeyStore | Password phải được bảo vệ riêng, file có thể bị copy |
| Environment variable | Dễ dùng orchestration | Có thể lộ qua process inspection, debug dump, logging; multiline PEM có thể lỗi encoding |
| Kubernetes Secret | Tích hợp RBAC và volume projection | Base64 trong manifest **không phải mã hóa**; cần encryption at rest, RBAC, node isolation |
| CSI Secret Store/Vault | Giảm secret lưu trong image, hỗ trợ luồng cấp quyền/rotation | Cần quản lý identity, sync, availability, cache và restart/reload |
| HSM/PKCS#11 | Private key **không xuất được** khỏi thiết bị, hỗ trợ thao tác ký/giải mã | Tích hợp provider, session, thuật toán và hiệu năng; không phải mọi library hỗ trợ trong mọi mode |
| Cloud KMS/remote signer | Dùng IAM và audit để hạn chế thao tác mật mã | KMS API không đương nhiên hỗ trợ XMLDSig/RSA-OAEP hay key type yêu cầu; cần adapter được kiểm chứng |

**Không nhầm “lưu secret” với “thực thi phép ký/giải mã”.** Một secret manager có thể trả file PEM cho ứng dụng, nhưng private key vẫn hiện diện trong memory của JVM. HSM/KMS có thể giữ private key ngoài process và thực hiện phép toán thay, nhưng Spring Security/OpenSAML phải sử dụng được Key/provider thích hợp. Không kỳ vọng `file:/...` tự động gọi HSM.

### 11.1. Tránh những hình thức lộ khóa phổ biến

- Không commit key/certificate chứa private key vào git, kể cả branch nội bộ hoặc “private repo”. Lịch sử git có thể giữ bản cũ sau khi xóa.
- Không đưa secret vào Dockerfile `COPY`, `ENV`, build args, image layers, Helm values public hoặc CI artifacts.
- Không in nội dung key, keystore password, Base64 secret hay full heap dump trong log/traces/ticket.
- Không dùng cùng một khóa production cho dev, UAT, staging.
- Không truyền passphrase trực tiếp như tham số dòng lệnh nếu có thể xuất hiện trong process listing/shell history.
- Không dùng file permission `0777` chỉ để khắc phục `Permission denied`.
- Không giả định TLS cert của reverse proxy có thể dùng làm SAML SP signing certificate; chúng có **vòng đời, chủ sở hữu và trust policy khác nhau**.

## 12. Ví dụ Kubernetes: mount key an toàn cho JVM

Giả sử ứng dụng chạy dưới tài khoản không phải root, có secret đã được cấp phát bằng cơ chế quản trị được phê duyệt.

**Trích đoạn PodSpec** (đặt dưới `spec.template.spec` của Deployment; đây không phải một manifest Kubernetes hoàn chỉnh):

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 2000
  fsGroup: 2000

containers:
  - name: portal
    image: registry.example.test/portal:stable
    volumeMounts:
      - name: saml-key-files
        mountPath: /run/secrets/saml
        readOnly: true

volumes:
  - name: saml-key-files
    secret:
      secretName: portal-saml-keys
      defaultMode: 0440
```

Điều kiện:

- `portal-saml-keys` phải được tạo trước bằng hệ thống quản trị secret được phép; **không** đưa bytes private key vào README/manifest.
- Ví dụ dùng `runAsUser` 10001, group 2000 và `fsGroup` 2000 để mô tả truy cập file có group-read. Quyền thực tế phụ thuộc container runtime, CSI/driver, security policy và ownership của volume; **kiểm tra trong Pod thật**.
- Mount secret ở `/run/secrets/saml`; Spring Boot `file:/run/secrets/saml/sp-sign-pkcs8.pem` phải trỏ tới **đúng key name/file** được project trong volume.
- `defaultMode: 0440` cho phép owner/group đọc; không phải bảo mật hoàn chỉnh nếu process khác chung group có thể truy cập. Dùng RBAC, namespace, node isolation, service account hạn chế và audit.
- Kubernetes Secret dạng Base64 không phải một cơ chế mật mã tự thân; cấu hình **encryption at rest**, quyền API server/etcd và quy trình backup.
- Khi volume được cập nhật, file có thể thay đổi mà Spring Security **không tự tải lại credential đã nạp vào `RelyingPartyRegistration`**. Cần cơ chế reload/rebuild repository, rolling restart hoặc chiến lược cache được thiết kế rõ, đồng thời tránh đổi khóa giữa một SAML flow đang xử lý.

Nếu khóa cần dùng cho nhiều mục đích, giữ **tên file/cấu hình key ring rõ ràng**, không tải mọi secret của namespace vào một container chỉ để dễ truy cập.

### 12.1. Docker và Linux service

Với VM/Linux, chỉ process service được cấp quyền đọc private key. Ví dụ đường dẫn:

```text
/run/secrets/saml/sp-sign-pkcs8.pem
/etc/saml/certs/sp-sign.crt
/etc/saml/idp-metadata.xml
```

Private key đặt ở secret volume/tầng file bảo mật, certificate công khai và metadata ở nơi có thể quản trị/kiểm toán nguồn. Một permission `0400` có thể đúng cho file thuộc owner chính xác; nhưng nếu process chạy user khác thì sẽ gặp lỗi. Cần cấp ownership/group hợp lệ, không hạ quyền sang world-readable.

**Đừng tự coi mount read-only là đã chống được lộ khóa**: nếu process bị compromise và có quyền đọc key, attacker vẫn có thể đọc nó. Read-only chỉ giảm khả năng thay file, còn tính bí mật cần nhiều lớp phòng vệ.

## 13. Kho khóa khi có nhiều IdP và nhiều môi trường

Một ứng dụng có thể có nhiều `RelyingPartyRegistration`:

```text
registration employee:
  SP entityId      = urn:example:portal:prod:sp
  SP signing key   = sp-employee-sign-2026
  SP decryption    = sp-employee-dec-2025 / sp-employee-dec-2026
  IdP verification = idp-employee-signing

registration partner:
  SP entityId      = urn:example:portal:prod:sp
  SP signing key   = sp-partner-sign-2026
  SP decryption    = sp-partner-dec-2026
  IdP verification = idp-partner-signing
```

Việc hai registration cùng SP Entity ID là lựa chọn có thể đúng khi hợp đồng với từng IdP cho phép; **không bắt buộc** chia sẻ private keys. Ngược lại, có thể cố ý tái sử dụng một SP signing key trong nhiều registration nhưng việc ấy phải được duyệt và cấu hình rõ ràng.

**Quy tắc lựa chọn credential:**

1. Xác định registration tin cậy trước, bằng cơ chế Spring Security và các thông tin request/correlation phù hợp.
2. Chọn SP signing/decryption credentials thuộc **registration này**.
3. Khi giải mã `EncryptedAssertion`, chỉ thử private keys trong **key ring được cấp phép**; `KeyName` trong SAML Response là **gợi ý không tin cậy**, không là quyền mở secret.
4. Khi xác minh SAML Response/Assertion, chỉ tin IdP certificate gắn với **IdP/registration được phê duyệt**.
5. Khi dùng keystore nhiều alias, alias phải được map bởi cấu hình quản trị, **không** được lấy thẳng từ HTTP parameter do người dùng tự chỉ.
6. Kiểm tra tenant membership/authorization nghiệp vụ **sau** xác thực, không dùng tên key/cert để suy quyền người dùng.

### 13.1. Không để DEV và PROD chia sẻ private key

Một private key production bị dùng ở môi trường thử nghiệm làm tăng phạm vi rủi ro: người có quyền debug thấp ở DEV có thể đánh cắp khóa mà PROD cũng tin. Nên dùng:

- Tách secret store / namespace / IAM principal / keystore theo môi trường.
- Đặt alias có ý nghĩa, ví dụ `portal-prod-saml-sign-2026`.
- Chặn import nhầm certificate DEV tại IdP PROD.
- Tự động đối chiếu fingerprint và SP Entity ID trong deployment pipeline bằng **danh sách được duyệt**.

## 14. Rotation: cập nhật khóa mà không làm gián đoạn SSO

**Xoay khóa** là công việc của cả SP và IdP, không chỉ thay file `.pem`/ `.p12`.

### 14.1. SP signing key rotation

1. Tạo private key/certificate signing mới bằng quy trình phê duyệt, lưu trong secret store.
2. IdP import/trust **public certificate SP mới** cho SP Entity ID tương ứng, có overlap nếu đối tác hỗ trợ.
3. SP bắt đầu ký AuthnRequest bằng private key mới **sau khi IdP sẵn sàng xác minh**.
4. Xác minh HTTP-Redirect `SigAlg/Signature` hoặc POST XMLDSig với certificate mới.
5. Hết cửa sổ chuyển tiếp, xóa cert/key cũ khỏi nơi tin cậy và backup sống theo chính sách.

Nếu đổi private key trước khi IdP được cập nhật, IdP có thể từ chối AuthnRequest vì chữ ký không khớp. **Không tắt yêu cầu ký để né lỗi rotation**.

### 14.2. SP decryption key rotation

1. Nạp **private key mới tại SP** trước khi IdP chuyển sang mã hóa assertion bằng public certificate mới.
2. IdP bổ sung/đổi sang **SP encryption certificate mới**.
3. SP giữ cả private key cũ và mới trong cửa sổ chuyển tiếp được duyệt nếu cần xử lý ciphertext từ IdP đang dùng cert cũ.
4. Kiểm thử EncryptedAssertion của cả hai certificate, theo dõi lỗi unwrap/decryption.
5. Khi IdP không còn mã hóa bằng cert cũ và các request cũ đã kết thúc, ngừng dùng private key cũ.

Thứ tự này khác với signing: **decryption key mới phải có trước khi IdP gửi ciphertext mới**.

### 14.3. IdP verification certificate rotation

IdP là chủ private key ký assertion. SP cần lấy **public certificate IdP mới** qua metadata/cấu hình đáng tin, hỗ trợ overlap theo chính sách và kiểm tra chữ ký. **Không** tự tin một X.509 certificate mới chỉ vì nó có trong XML Response chưa được xác minh.

### 14.4. Keystore/reload và certificate expiry

Một số Spring Security registration được tạo và giữ trong memory khi ứng dụng khởi động. Thay file `.p12` hoặc secret volume **không đồng nghĩa** registration đang chạy đã nạp key mới. Cần:

- Kiểm tra provider/repository đang cache credential như thế nào.
- Thiết kế rolling restart, refresh/rebuild registration có kiểm soát hoặc cơ chế dynamic keystore đã được kiểm thử.
- Bảo vệ thao tác swap file theo cách atomic, không cho process đọc file đang ghi dở.
- Có health check/tracing an toàn cho trạng thái key hiện hành và mốc hết hạn.
- Tránh công bố cert mới trong metadata trước khi private key mới sẵn sàng.

Certificate expiry, private key rotation và metadata refresh là **ba luồng vận hành liên quan nhưng khác nhau**. Không chỉ sửa ngày hết hạn trong config; certificate là đối tượng đã được ký và quản trị theo chính sách riêng.

## 15. Troubleshooting: lỗi định dạng, trust và triển khai

| Triệu chứng | Nguyên nhân thường gặp | Hướng điều tra an toàn |
| --- | --- | --- |
| `InvalidKeySpecException` khi parse private key | PKCS#1 được đưa vào loader PKCS#8; thuật toán sai hoặc DER hỏng | Xem PEM label/ASN.1 bằng công cụ chuyên dụng, chuyển đúng PKCS#8 |
| `IllegalArgumentException` / “invalid PEM” | File thiếu header/footer, nhầm `PUBLIC KEY` với `PRIVATE KEY`, newline/cấu trúc sai | Kiểm tra loại đối tượng và file được mount, không in key |
| `EncryptedPrivateKeyInfo` không đọc được | Loader chỉ hỗ trợ PKCS#8 không mã hóa hoặc thiếu passphrase/PBE provider | Dùng loader bảo mật có password/keystore phù hợp |
| `NoSuchAlgorithmException` / `InvalidKeyException` | Provider thiếu RSA/EC thuật toán, key type không tương thích | Kiểm tra JDK/provider, key type và policy thuật toán |
| Spring báo không đọc được resource | Sai `file:`/ `classpath:`, path host khác container path | Kiểm tra đường dẫn bên trong process/container |
| `AccessDeniedException` / `Permission denied` | Secret file ownership/group/mode không cho app user đọc | Đối chiếu UID/GID, fsGroup, file mode; không dùng 0777 |
| PKCS#12 có alias nhưng `getKey` trả null | Alias sai hoặc entry là trustedCertEntry | Xem `keytool -list`, chọn đúng `PrivateKeyEntry` |
| `UnrecoverableKeyException` | Sai keystore password/key password hoặc PBE/provider | Kiểm tra secret source và password mapping, không log password |
| File `.p12` gán vào `private-key-location` nhưng Boot không đọc | Property đang mong private-key file, không tự tra alias PKCS#12 | Dùng Java `KeyStore` hoặc tích hợp keystore tương thích |
| Private key và certificate đọc được nhưng không ký/giải mã được | Keypair không khớp, cert IdP đang lưu là cert cũ | Đối chiếu public key fingerprint/cert hiện dùng tại IdP |
| IdP báo AuthnRequest signature invalid | SP signing key/cert mismatch hoặc IdP pin cert khác | Kiểm tra keypair, certificate đã import, algorithm/binding |
| SP không giải mã được EncryptedAssertion | SP decryption key không khớp cert mà IdP dùng | Xem SP encryption cert/fingerprint và key ring trong registration |
| SP báo assertion signature invalid | IdP verification cert/issuer sai | Kiểm tra IdP trusted metadata và verification credential, không lấy cert từ response tùy ý |
| Chứng thư hợp lệ nhưng vẫn bị từ chối | SAML issuer, audience, recipient, key purpose hoặc policy sai | Phân biệt trust SAML với TLS/PKIX và điều kiện federation |
| Sau rotation mới lỗi | Pod chưa reload secret, IdP chưa cập nhật, overlap thiếu | Kiểm tra version/fingerprint trong runtime và kế hoạch chuyển đổi |
| Chỉ lỗi ở Kubernetes | Key permissions, volume projection, service account, fsGroup | Kiểm tra UID, GID, mode và mount path trực tiếp tại Pod |
| Chỉ lỗi trên JVM mới | Provider/algorithm hoặc keystore compatibility khác | Đối chiếu version JDK, KeyStore type, thuật toán PKCS#12 |
| Dùng HSM nhưng `getEncoded()` trả null | Khóa không export được theo chính sách HSM | Dùng signing/decryption provider qua handle, không ép export |
| Lộ secret trong build log | Script `cat` private key, echo environment password | Thu hồi/chuyển key và chặn log; xem đây là sự cố bảo mật |

### 15.1. Quy trình chẩn đoán không tiết lộ khóa

1. Xác nhận `registrationId`, SP Entity ID, IdP Entity ID và **credential purpose** mong đợi.
2. Xem **nhãn PEM/loại keystore** hoặc `keytool -list`; không in nội dung private key.
3. Kiểm tra Java process đọc đúng **container path**, quyền file, owner và secret version.
4. Đối chiếu fingerprint/public key của key và certificate bằng công cụ an toàn.
5. Xác định **lỗi parse**, **lỗi password**, **lỗi signing/decryption** hay **lỗi SAML validation**; không gộp thành “SSO lỗi”.
6. Kiểm tra signing algorithm, XML Encryption transport/content algorithm hoặc JCA provider đúng phiên bản.
7. Kiểm tra IdP đang lưu **public certificate nào**, không chỉ certificate nằm ở SP.
8. Xác định đã reload/restart registration sau rotation chưa.
9. Ghi log chỉ gồm mã lỗi, registration, certificate fingerprint công khai, alias, thuật toán và timestamp ở mức policy cho phép.
10. Không thêm `print(privateKey)`, `cat sp-private.pem`, full heap dump hoặc SAML assertion plaintext vào log để chữa lỗi.

**Tách lớp lỗi:** private key không parse được ⇒ vấn đề định dạng/loader; private key parse được nhưng signature fail ⇒ vấn đề keypair/trust/binding; decrypt được nhưng authentication fail ⇒ vấn đề chữ ký/issuer/audience/conditions SAML. Không xử lý bằng cách tắt signature validation, bỏ encryption policy hoặc chấp nhận bất cứ certificate nào.

## 16. Ma trận kiểm thử thực tế

| Test case | Đầu vào/cấu hình | Kỳ vọng |
| --- | --- | --- |
| PKCS#8 unencrypted hợp lệ | `BEGIN PRIVATE KEY` RSA, PKCS#8 DER | JCA/Spring loader đọc được |
| PKCS#1 traditional | `BEGIN RSA PRIVATE KEY` đưa vào converter PKCS#8 | Từ chối/không parse; cần chuyển đổi |
| Encrypted PKCS#8 | `BEGIN ENCRYPTED PRIVATE KEY` không có passphrase loader | Fail rõ, không tự bỏ mã hóa |
| PEM private/public nhầm | `BEGIN PUBLIC KEY` trong vị trí private key | Từ chối |
| PEM certificate | `BEGIN CERTIFICATE` đúng X.509 | `CertificateFactory` parse được |
| DER certificate | Binary DER cấp đúng chỗ | Loader có hỗ trợ DER đọc được; không giả định tất cả property luôn hỗ trợ mọi input |
| Key/cert khớp | Public key derived từ private = public key trong cert | PASS keypair check |
| Key/cert lệch | Private key SP A, certificate SP B | Fail keypair check trước deploy |
| Keystore đúng alias | PKCS#12 có `PrivateKeyEntry` đúng | `getKey`/ `getCertificate` trả đối tượng phù hợp |
| Alias sai | `sp-signing` không tồn tại | Fail an toàn, không tự chọn alias bất kỳ |
| Sai password | PKCS#12 hoặc encrypted key password sai | Fail, không in secret |
| Private key thiếu quyền đọc | Service user không có quyền | Fail health/startup có thể điều tra; không đổi world-readable |
| Java provider thiếu thuật toán | RSA/EC/HSM mode không được hỗ trợ | Fail với lỗi tương thích, không fallback yếu |
| Signing credential đúng | SP gửi AuthnRequest signed bằng key IdP tin | IdP xác minh thành công |
| SP signing cert cũ | IdP pin certificate khác | IdP từ chối cho đến khi đồng bộ |
| Decryption key cũ/mới | IdP dùng cert mới, SP có cả key cũ và mới | Giải mã bằng key mới; giữ overlap đúng hạn |
| IdP assertion cert thay đổi | SP nhận metadata/trust update hợp lệ | Chỉ nhận assertion ký bằng key được phép |
| Đổi secret volume | Pod đã thấy file mới, repository vẫn cache key cũ | Test nhận ra cần reload/restart |
| Khóa HSM không export | `PrivateKey.getEncoded() == null` | Dùng provider/HSM; không coi là key hỏng |
| Hai registration | IdP A và B dùng key rings riêng | Không mở nhầm khóa/trust của registration khác |
| DEV/PROD | Dùng certificate DEV ở PROD | Từ chối theo policy; không chia sẻ private key |
| SAML response từ IdP lạ | Response có certificate nhúng tùy ý | Không tự trust; từ chối trước tạo Authentication |
| Leak detection | Key xuất hiện trong git/CI artifact/log | Pipeline cảnh báo, thu hồi và xử lý sự cố |

**Kiểm thử định dạng key không thay thế kiểm thử SAML end-to-end**. Sau khi key load thành công, cần chạy với IdP thử nghiệm để xác nhận Signed AuthnRequest, EncryptedAssertion, Response signature validation và các điều kiện nghiệp vụ.

## 17. Checklist triển khai vận hành

- [ ] Đã phân biệt PEM/DER (encoding), PKCS#8/PKCS#1 (cấu trúc), X.509 certificate/SPKI public key, PKCS#12 (container).
- [ ] Private key được cấp theo đúng algorithm và format mà Spring/JCA loader hỗ trợ.
- [ ] Không đưa `BEGIN RSA PRIVATE KEY` nguyên dạng vào loader PKCS#8, không tự đổi PEM header để “chuyển đổi”.
- [ ] Đã xác minh public key của certificate **khớp** với private key tương ứng.
- [ ] SP signing, SP decryption, IdP verification, metadata verification có **credential purpose riêng**, không tráo vai trò.
- [ ] Chọn `file:` resource theo đường dẫn **thực bên trong JVM/container**, tránh nhầm máy host với container.
- [ ] Không nhúng production private key vào classpath/JAR/image/source control.
- [ ] Với PKCS#12, alias/password/entry type/chain được kiểm tra; nếu Boot không hỗ trợ alias location trực tiếp thì dùng Java KeyStore.
- [ ] Password/secret được cấp từ kênh quản trị an toàn, không ghi stdout, exception message hoặc CI artifact.
- [ ] Private key có permissions tối thiểu và runtime identity rõ ràng, kể cả UID/GID/fsGroup cho Kubernetes.
- [ ] Kubernetes Secret được bảo vệ bằng RBAC, encryption at rest và quy trình backup; Base64 không được xem là mật mã.
- [ ] Nếu dùng HSM/PKCS#11/KMS, signing/decryption provider đã được test tương thích với thuật toán và OpenSAML.
- [ ] Đã định nghĩa vòng đời cert/key, lịch rotation, overlap signing/decryption, cutover và rollback.
- [ ] Có kiểm tra actual registration/trust certificate sau reload/rolling restart.
- [ ] Đã thử trường hợp khóa không đúng, certificate không khớp, sai password, key lộ và certificate hết hạn.
- [ ] Sau khi credentials hoạt động, Spring Security vẫn kiểm tra SAML issuer, signature, audience, recipient, thời gian, correlation và replay.
- [ ] Mọi private key/certificate từ IdP hoặc đối tác được tiếp nhận theo quy trình tin cậy; không tự thêm certificate lạ vào truststore vì lỗi SSO.
- [ ] Có monitoring/cảnh báo certificate expiry, secret freshness và lỗi signed/decryption theo registration.

## 18. Câu hỏi tự kiểm tra

**1. File `sp.key` có phải chắc chắn là PKCS#8 không?**

Không. Đuôi file chỉ là quy ước. Xem PEM label và cấu trúc DER; `BEGIN RSA PRIVATE KEY` thường là PKCS#1, còn `BEGIN PRIVATE KEY` thường là PKCS#8 không mã hóa.

**2. PEM và PKCS#8 có phải hai format thay thế nhau?**

Không. PEM là **cách bọc text/encoding**; PKCS#8 là **cấu trúc private key**. Một PKCS#8 có thể được lưu dạng DER binary hoặc PEM Base64.

**3. Vì sao `BEGIN ENCRYPTED PRIVATE KEY` không thể đưa thẳng cho `PKCS8EncodedKeySpec`?**

Vì bytes chứa **EncryptedPrivateKeyInfo**. Cần giải mã đúng bằng password/PBE provider rồi mới lấy PrivateKeyInfo cho KeyFactory. Không phải mọi Spring Boot private-key loader tự làm bước này.

**4. `BEGIN PUBLIC KEY` có tương đương `BEGIN CERTIFICATE`?**

Không. Public key SPKI không mang metadata/chữ ký certificate như X.509. JCA `X509EncodedKeySpec` parse public SPKI, còn `CertificateFactory` parse certificate.

**5. Nếu đã có certificate SP thì có đủ để ký AuthnRequest hoặc giải mã EncryptedAssertion không?**

Không. SP cần **private key tương ứng**, còn IdP cần **public certificate SP** để xác minh chữ ký hoặc mã hóa cho SP.

**6. PKCS#8 khác PKCS#12 thế nào?**

PKCS#8 mô tả private-key information; PKCS#12 là container/keystore có thể lưu private key, certificate chain và alias. Java đọc PKCS#12 qua `KeyStore`.

**7. Spring Boot có tự hiểu `file:/run/secrets/sp-keys.p12` là private key và tự chọn alias không?**

Không nên giả định. `private-key-location` thường nhắm tới file key ở định dạng loader hỗ trợ; PKCS#12 cần KeyStore/provider và chọn alias rõ ràng, trừ khi phiên bản/integration của bạn tài liệu hóa chức năng khác.

**8. Nếu certificate và private key parse được nhưng không khớp public key, giải quyết thế nào?**

Sử dụng cặp khóa/certificate chính xác; không cố bỏ kiểm tra hoặc dùng certificate IdP thay. Kiểm bằng public-key fingerprint và đối chiếu cấu hình tại IdP.

**9. Khóa trong HSM có `getEncoded() == null` thì bị hỏng?**

Không. Nhiều HSM cố ý không cho xuất private key; ứng dụng phải sử dụng JCA provider/handle hoặc crypto service phù hợp.

**10. Cần làm gì khi IdP chuyển sang mã hóa assertion bằng SP certificate mới?**

Private key mới phải được SP nạp **trước** khi IdP phát ciphertext mới. Có giai đoạn overlap khóa cũ/mới nếu được phép, rồi loại khóa cũ sau khi đồng bộ.

**11. Chỉ cần bật HTTPS thì có thể công bố private key SP trong JAR không?**

Không. TLS bảo vệ kênh truyền, không ngăn người có quyền đọc JAR/image hoặc host lấy private key. Key phải được lưu và cấp quyền riêng.

**12. Vì sao một truststore TLS hợp lệ vẫn có thể không đủ cho SAML response verification?**

SAML trust phải gắn **public certificate được phép** với IdP entityID/registration và chính sách xác minh assertion. Việc certificate do CA công khai cấp không chứng minh IdP được quyền phát assertion cho SP của bạn.

## 19. Nguồn tham khảo chính thức

- Spring Security, **SAML 2.0 Login Overview**, phần Credentials, `RsaKeyConverters.pkcs8()`, `Saml2X509Credential`: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **Authenticating SAML Responses**, phần Customizing Decryption: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **Saml2X509Credential API**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2X509Credential.html
- Spring Boot 3.4, **SAML 2.0 Relying Party**, `signing.credentials` và `decryption.credentials`: https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html
- Oracle Java 17, **JCA Reference Guide**, KeyStore, PKCS12, JKS và PKCS11: https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html
- Oracle Java 17, **CertificateFactory API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html
- Oracle Java 17, **PKCS8EncodedKeySpec API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html
- OpenSSL, **openssl-pkcs8** — chuyển đổi PKCS#8 và `-topk8/-nocrypt`: https://docs.openssl.org/master/man1/openssl-pkcs8/
- OpenSSL, **openssl-pkcs12** — đóng gói private key/cert vào PKCS#12: https://docs.openssl.org/master/man1/openssl-pkcs12/
- Kubernetes, **Secrets** — volumes, permissions, RBAC và encryption at rest: https://kubernetes.io/docs/concepts/configuration/secret/

**Ghi nhớ:** PEM là **vỏ text**, PKCS#8 là **cấu trúc private key**, PKCS#12 là **keystore container**, X.509 certificate là **vật liệu công khai gắn public key với danh tính**, còn HSM/PKCS#11 là **mô hình truy cập khóa**. Trong Spring Security SAML2, hãy nạp đúng **SP signing/decryption private key + certificate**, đúng **IdP verification certificate**, bảo vệ khóa trong môi trường triển khai và kiểm thử cả **keypair, cấu hình registration, SAML trust và rotation**.