# 16.1 Vai trò của SSLContext, KeyManagerFactory và TrustManagerFactory

**JSSE** (*Java Secure Socket Extension*) là tầng API bảo mật TLS/SSL trong Java, dùng những đối tượng như `SSLContext`, `SSLSocket`, `SSLServerSocket`, `SSLEngine`, `KeyManager` và `TrustManager`. Ba lớp thường xuyên xuất hiện khi cấu hình HTTPS hoặc mTLS là **`SSLContext`**, **`KeyManagerFactory`** và **`TrustManagerFactory`**. Chúng liên quan với nhau nhưng thực hiện **ba trách nhiệm khác nhau**:

- **`KeyManagerFactory`**: từ **identity keystore** chứa private key và certificate chain của ứng dụng, tạo các **KeyManager** để chọn và sử dụng **danh tính của chính bên mình** trong TLS.
- **`TrustManagerFactory`**: từ **truststore/trust policy**, tạo các **TrustManager** để quyết định có thể **tin certificate của bên đối tác** hay không.
- **`SSLContext`**: là **ngữ cảnh TLS đã cấu hình** gồm key managers, trust managers, nguồn ngẫu nhiên và TLS provider; nó tạo `SSLSocketFactory`, `SSLServerSocketFactory`, `SSLEngine`, và ngữ cảnh phiên TLS. Nó không tự sinh chứng chỉ hoặc thay thế quyết định trust.

Bài này mở đầu nhóm **16. JSSE** của Java Advance – security-cryptography. Trọng tâm là **phân biệt đúng trách nhiệm** của ba đối tượng và xác định ai giữ private key, ai kiểm certificate của peer, ai tạo socket/engine cho handshake. Để tự kiểm chứng mà không cần tạo chứng thư, mục 9 có một chương trình Java 17+ độc lập minh họa SSLContext và SSLEngine trước handshake. Việc dựng CA, certificate chain và TLS loopback được học chuyên sâu ở bài 16.2; việc buộc hoặc đề nghị client certificate được kiểm chứng bằng ma trận need/want ở bài 16.5.

> **Phạm vi:** mọi sơ đồ, snippets và phép thử trong bài nhằm làm rõ trách nhiệm JSSE; việc khởi tạo SSLContext thành công **chưa chứng minh** một phiên thực tế đã xác minh CA, SAN/hostname, client certificate hoặc authorization. Các lab chứng thư tự ký ở những bài chuyên sâu chỉ áp dụng trong môi trường thử nghiệm và phải giữ ranh giới tin cậy riêng.

## 1. Sơ đồ tổng thể: ba trách nhiệm trong JSSE

```text
                      ỨNG DỤNG JAVA
                            |
                            v
                   +----------------+
                   |   SSLContext   |
                   | protocol="TLS" |
                   +----------------+
                     ^            ^
                     |            |
     "Tôi là ai?"    |            |    "Tôi tin ai?"
                     |            |
      KeyManagerFactory          TrustManagerFactory
       (identity keystore)        (truststore / policy)
               |                          |
        KeyManager[]                 TrustManager[]
               |                          |
      PrivateKeyEntry             TrustedCertificateEntry
       - private key                 - CA/peer cert tin cậy
       - leaf certificate           - trust anchor policy
       - certificate chain
                     |            |
                     +------+-----+
                            |
                  SSLContext.init(km, tm, random)
                            |
              +-------------+-------------+
              |             |             |
      SSLSocketFactory  SSLServerSocket  SSLEngine
                            |
                       TLS handshake
                       + protected data
```

**Cách nhớ nhanh:**

| Câu hỏi trong TLS | Ai chịu trách nhiệm? | API chính |
| --- | --- | --- |
| **Bên mình trình bày certificate nào?** | `KeyManager` chọn local identity và sử dụng private key tương ứng | `KeyManagerFactory`, `X509KeyManager`/`X509ExtendedKeyManager` |
| **Certificate peer có đáng tin không?** | `TrustManager` kiểm tra chain/trust policy/điều kiện liên quan | `TrustManagerFactory`, `X509TrustManager`/`X509ExtendedTrustManager` |
| **Các manager đó được dùng khi tạo kết nối thế nào?** | `SSLContext` nhận managers rồi cấp socket/engine có cấu hình TLS | `SSLContext.getInstance`, `init`, `getSocketFactory`, `createSSLEngine` |
| **TLS client dùng hostname `localhost` hay `api.example.com`?** | Endpoint identity phải được kiểm tra theo cấu hình/giao thức | `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` trên socket/engine khi phù hợp |
| **Server yêu cầu certificate từ client hay không?** | Server socket/engine cấu hình client authentication | `setNeedClientAuth(true)`, `setWantClientAuth(true)` hoặc `SSLParameters` |
| **Record nào được mã hóa bằng key phiên?** | TLS provider/engine quản lý handshake, key schedule và record encryption | `SSLSocket`, `SSLEngine` — không tự xử lý bằng `Cipher` trong app |

Lưu ý: cả **TLS client lẫn TLS server** đều có thể dùng **KeyManager** và **TrustManager**. Khác biệt không nằm ở chữ “client/server”, mà ở việc **bên nào cần chứng minh danh tính của mình** và **bên nào cần xác minh peer**. Với **mTLS**, cả hai phía làm **cả hai việc**.

## 2. KeyStore và truststore là nguồn dữ liệu, không phải TLS manager

Trước khi cấu hình JSSE phải tách **file/kho lưu trữ** khỏi **đối tượng quản lý hành vi TLS**.

| Đối tượng | Chức năng | Có private key không? | Có thực thi trust decision không? |
| --- | --- | --- | --- |
| **`KeyStore`** | API JCA chứa entry dưới alias, có thể dựa trên PKCS#12, JKS, HSM, OS store | Có thể có | Không tự động; phụ thuộc dữ liệu và API sử dụng |
| **Identity keystore** | Một `KeyStore` được dùng làm nguồn **private key + certificate chain của ứng dụng** | Thường **có** | Không phải mục đích chính |
| **Truststore** | Một `KeyStore` được dùng chứa **certificate/CA được phép tin** | Thường **không cần** | Bản thân file không ra quyết định; **TrustManager** thực thi chính sách |
| **`KeyManager`** | Chọn local alias/certificate chain và dùng private key theo yêu cầu của handshake | Được cấp quyền dùng key | Không có nhiệm vụ xác thực peer |
| **`TrustManager`** | Xác minh certificate chain peer theo chính sách | Không cần private key peer | **Có**, khi thực hiện kiểm tra trong handshake |
| **`CertStore`** | Nguồn **certificate/CRL ứng viên** cho PKIX path building/revocation | Không | Không phải trust anchor tự thân |

**Java không có class JCA tiêu chuẩn `TrustStore`.** Từ “truststore” mô tả **vai trò** của một `KeyStore`, thường chứa `KeyStore.TrustedCertificateEntry`. Một certificate nằm trong truststore theo alias không có nghĩa mọi client/SSLContext trong JVM đều sử dụng file đó: chỉ các trust managers được cấu hình với store ấy (hoặc logic default tương ứng) mới dùng nó.

### 2.1 Các KeyStore.Entry quan trọng

| Entry type | Nội dung | Tác dụng |
| --- | --- | --- |
| `KeyStore.PrivateKeyEntry` | Private key + X.509 certificate chain | TLS server/client có certificate để chứng minh quyền sở hữu private key |
| `KeyStore.TrustedCertificateEntry` | Certificate được operator đưa vào tập tin cậy | Cung cấp trust anchor/peer certificate cho trust policy |
| `KeyStore.SecretKeyEntry` | Secret key đối xứng (ví dụ AES) | Phục vụ ứng dụng mật mã khác; **không** trở thành TLS certificate identity |

Ví dụ một file `identity.p12` chỉ có certificate nhập bằng `keytool -importcert`, **không có private key**, thì không thể cho server chứng minh nắm private key. Ngược lại, file `trust.p12` chứa CA certificate không phải là nơi server phải lấy private key khi làm TLS.

`KeyStore.isKeyEntry(alias)`, `isCertificateEntry(alias)` và `entryInstanceOf(alias,...)` giúp kiểm tra đúng loại. `getCertificate(alias)` có thể trả certificate của **PrivateKeyEntry** *hoặc* certificate-only entry, nên không đủ để kết luận alias là trusted certificate entry.

## 3. KeyManagerFactory: biến identity store thành KeyManager

Mục đích của `KeyManagerFactory` là **khởi tạo một hay nhiều `KeyManager` từ vật liệu xác thực local**. Với X.509 TLS, `X509KeyManager` hoặc `X509ExtendedKeyManager` có thể:

- Liệt kê alias local phù hợp với **loại key** và yêu cầu của peer;
- Chọn certificate chain tương ứng khi server/client cần trình bày danh tính;
- Cung cấp private key **được phép sử dụng** để TLS chứng minh quyền sở hữu trong handshake;
- Lựa chọn key khác theo SNI, key type hoặc ngữ cảnh socket/engine nếu provider và cấu hình hỗ trợ.

Một luồng điển hình:

```text
identity.p12
  |
  | alias "server"
  | PrivateKeyEntry:
  |   private RSA/EC key
  |   certificate chain: leaf -> intermediate...
  v
KeyStore.load(input, storePassword)
  |
  v
KeyManagerFactory.getInstance(
    KeyManagerFactory.getDefaultAlgorithm())
  |
  +-- init(identityStore, keyPassword)
  |
  +-- getKeyManagers() -> KeyManager[]
  |
  v
SSLContext.init(keyManagers, trustManagers, random)
  |
  v
Khi TLS cần local certificate:
  KeyManager chọn key/certificate phù hợp
```

### 3.1 Đoạn Java thiết yếu

```java
// Minh họa nằm trong method có imports/throws phù hợp.
// identity và keyPassword đã được cấp an toàn trước đó.
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identity, keyPassword);
KeyManager[] keyManagers = kmf.getKeyManagers();
```

`KeyManagerFactory.getDefaultAlgorithm()` đọc cấu hình mặc định/provider theo JDK (thường liên quan security property `ssl.KeyManagerFactory.algorithm`). **Không hardcode tên provider-specific** nếu ứng dụng không có yêu cầu tương ứng. Nếu chính sách buộc một provider (ví dụ HSM), hãy kiểm tra rõ thuật toán, provider và key capability trước khi khởi tạo.

**Không nhầm `KeyManagerFactory` với `KeyPairGenerator` hoặc `KeyFactory`:**

- `KeyPairGenerator` **sinh** cặp key mới;
- `KeyFactory` chuyển **biểu diễn** key/key spec;
- `KeyManagerFactory` chuẩn bị **cách JSSE sử dụng identity keys đã có** trong handshake.

### 3.2 Store password và key password

```java
// Minh họa, không phải chương trình độc lập.
KeyStore ks = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("identity.p12"))) {
    ks.load(in, storePassword);
}
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(ks, keyPassword);
```

`storePassword` dùng để mở/kiểm tra kho theo type/provider. `keyPassword` dùng để lấy **private-key entries**. Hai password **có thể trùng**, đặc biệt trong ví dụ PKCS#12 để tương thích, nhưng **không được giả định luôn phải trùng** với mọi key store/provider. Nếu password đúng cho `load` nhưng `kmf.init` thất bại, cần kiểm tra key protection, alias và provider thay vì đổi sang chế độ TLS thiếu xác thực.

Trong production, password không nên hardcode như mẫu lab, không ghi trên command line/hệ thống log không bảo vệ, và không lưu private key trong repo.

### 3.3 Tên alias không phải danh tính TLS tự động

Alias `server` chỉ là **nhãn cục bộ**. Certificate mà peer kiểm tra có SAN, subject, issuer, key usage/EKU, validity, signature, trust chain và các chính sách khác. Đổi alias thành `api.example.com` **không tự sửa SAN**. Khi có nhiều private keys trong một store, key manager/provider có thể chọn alias dựa trên handshake; nếu cần chọn alias đặc biệt, cấu hình `X509ExtendedKeyManager`/framework đúng cách và kiểm thử SNI, key type, signature algorithms.

## 4. TrustManagerFactory: biến trust policy thành TrustManager

`TrustManagerFactory` khởi tạo **các `TrustManager` dùng để đánh giá chứng chỉ đối tác**. Đối với X.509, đối tượng thường là `X509TrustManager` hoặc `X509ExtendedTrustManager`.

```text
trusted-roots-and-peers.p12
  |
  | TrustedCertificateEntry: CA/peer cert được chấp thuận
  v
KeyStore.load(input, storePassword)
  |
  v
TrustManagerFactory.getInstance(
    TrustManagerFactory.getDefaultAlgorithm())
  |
  +-- init(trustStore)
  |
  +-- getTrustManagers() -> TrustManager[]
  |
  v
SSLContext.init(keyManagers, trustManagers, random)
  |
  v
Khi TLS peer trình bày certificate chain:
  TrustManager kiểm tra trust/path/constraints theo cấu hình
  => reject handshake nếu không đạt
```

### 4.1 Đoạn Java thiết yếu

```java
// Minh họa, không phải chương trình độc lập.
// trustStore là KeyStore đã load và được operator quản lý.
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);
TrustManager[] trustManagers = tmf.getTrustManagers();
```

**`TrustManagerFactory.init(trustStore)` khác `KeyManagerFactory.init(identity, password)`:** `TrustManagerFactory` không cần private key của peer. Nó làm việc với certificates/trust anchors. Không đổi hai loại factory cho nhau vì cùng dùng `KeyStore`.

Trong Java có overload `TrustManagerFactory.init(ManagerFactoryParameters)` dành cho một số cấu hình nâng cao như `CertPathTrustManagerParameters` để truyền `PKIXBuilderParameters` theo provider hỗ trợ. Đó là cách quản lý trust policy phức tạp hơn; không phải mọi dự án phải sử dụng. Trọng tâm bài này là luồng `init(KeyStore)` thường gặp.

### 4.2 Trust manager và hostname verification

Có **hai câu hỏi khác nhau** khi client kết nối `https://api.example.com`:

1. *Certificate chain có dẫn đến CA/peer key đáng tin theo chính sách và thuật toán không?*
2. *Certificate đích có thực sự **dành cho hostname api.example.com** và mục đích sử dụng đúng không?*

PKIX chain trust là nền tảng của câu hỏi thứ nhất; **endpoint identification** đảm bảo phần định danh của câu hỏi thứ hai trong TLS client được cấu hình đúng.

Khi tự tạo `SSLSocket` hoặc `SSLEngine`, cần cân nhắc tường minh:

```java
// Minh họa: socket là SSLSocket ở client mode.
SSLParameters params = socket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
socket.startHandshake();
```

Đây là **đoạn minh họa**, không phải full class. `"HTTPS"` là tên thuật toán endpoint identification tiêu chuẩn phù hợp ngữ cảnh HTTPS/TLS client. Một HTTP client cấp cao có thể đã thực hiện kiểm tra hostname, trong khi `SSLSocket`/ `SSLEngine` cấp thấp phải được cấu hình đúng để không bỏ sót. **Đừng tự coi kiểm tra chain là đủ thay thế so khớp SAN/hostname.**

### 4.3 Truststore là danh sách trust anchors, không phải kho tất cả certificate

Một `CertStore` có thể cung cấp **intermediate certificates và CRLs ứng viên** để xây/kiểm tra path PKIX. Chúng không tự trở thành trust anchors khi được tải về. Thêm một intermediate vào truststore như **trusted CA** chỉ để “chữa PKIX path building failed” có thể làm rộng phạm vi tin cậy hơn dự kiến. Trước khi thêm certificate vào truststore, cần xác minh nguồn/fingerprint, mục đích và phạm vi chấp thuận.

**TrustManager không tự chống replay ở tầng nghiệp vụ.** TLS hỗ trợ bảo vệ bản tin trong phiên, nhưng việc một HTTP request nghiệp vụ bị gửi lại theo cách hợp lệ cần xử lý ở lớp ứng dụng, ví dụ idempotency key, authorization, anti-replay theo hợp đồng giao thức.

## 5. SSLContext: phối hợp managers và tạo TLS engines

`SSLContext` là **ngữ cảnh giao thức TLS** do provider triển khai. Nó chứa cấu hình logic cho cách TLS socket/engine có thể sử dụng local credentials, trust decisions, randomness, các giao thức và phiên.

```text
SSLContext context = SSLContext.getInstance("TLS");
context.init(
    KeyManager[] localIdentityManagers,
    TrustManager[] peerTrustManagers,
    SecureRandom randomSource
);

Từ context:
  context.getSocketFactory()        -> SSLSocketFactory (client)
  context.getServerSocketFactory()  -> SSLServerSocketFactory (server)
  context.createSSLEngine(...)      -> SSLEngine (TLS engine không ràng buộc socket)
  context.getDefaultSSLParameters() -> parameters mặc định của context
  context.getSupportedSSLParameters()-> khả năng hỗ trợ
```

API căn bản:

```java
// Minh họa trong method đã tạo keyManagers và trustManagers.
SSLContext context = SSLContext.getInstance("TLS");
context.init(keyManagers, trustManagers, new SecureRandom());

SSLSocketFactory clients = context.getSocketFactory();
SSLServerSocketFactory servers = context.getServerSocketFactory();
SSLEngine engine = context.createSSLEngine("api.example.com", 443);
```

**`getInstance("TLS")` chưa có nghĩa đã cấu hình truststore hoặc đã bắt đầu handshake.** Phải gọi `init` (trừ `SSLContext.getDefault()` vốn đã sẵn sàng theo contract), sau đó tạo socket/engine và **thực hiện handshake**. Mỗi socket/engine có trạng thái kết nối riêng; `SSLContext` có thể được dùng để tạo nhiều kết nối.

### 5.1 Những hiểu nhầm về init

| Lời gọi | Nghĩa đúng |
| --- | --- |
| `SSLContext.getInstance("TLS")` | Chọn một implementation TLS; chưa kết nối và thường cần `init`. |
| `context.init(kms, tms, random)` | Thiết lập managers và nguồn ngẫu nhiên cho context; **chưa xác minh bất cứ server certificate nào**. |
| `context.init(null, null, null)` | Yêu cầu JSSE/provider dùng cơ chế/default managers và random phù hợp; **không có nghĩa bỏ qua trust validation**. Chi tiết nguồn default phụ thuộc JDK/provider/config. |
| `SSLContext.getDefault()` | Lấy context mặc định đã dùng được; có thể phản ánh system properties, provider, hoặc context được đặt bởi `setDefault`. |
| `SSLContext.setDefault(ctx)` | Đổi default context cho các lời gọi sau có sử dụng default; **không buộc mọi thư viện/khách hàng đang có context riêng chuyển đổi**. |
| `context.getSupportedSSLParameters()` | Tham số **có thể hỗ trợ**, không phải chắc chắn đang bật cho mọi socket. |
| `context.getDefaultSSLParameters()` | Giá trị mặc định của context/provider, cần kiểm tra/chính sách trước khi kết luận bảo mật. |

**Phân biệt default với an toàn:** nếu `tm` là `null`, SSLContext dùng default trust manager theo contract/provider; điều này **không đồng nghĩa tin mọi certificate**. Đừng tự tạo `X509TrustManager` với `checkServerTrusted` rỗng để tránh `SSLHandshakeException`. Nếu default truststore không chấp thuận CA nội bộ, hãy quản lý truststore riêng và xác minh nguồn certificate.

Đối với `KeyManager` `null` trên một context client, hành vi không nhất thiết giống “ứng dụng đã có certificate”. Đặc biệt, **server TLS cần private key/certificate identity** để thực hiện handshake X.509 thông thường; chỉ tạo `SSLContext` và không đưa key manager thích hợp không khiến server tự có certificate.

### 5.2 SSLContext không phải KeyStore

Khi xây một `SSLContext` từ `identity.p12` và `trust.p12`:

```text
identity.p12 -- KeyManagerFactory -> KeyManager[] --+
                                                    |
trust.p12    -- TrustManagerFactory -> TrustManager[]+--> SSLContext
                                                    |
                        new SecureRandom() ---------+
                                                    |
                                                   TLS
```

`SSLContext` **không phải file** `.p12`, không lưu private key ra đĩa bằng `store`, không duy trì danh sách CA như một `KeyStore` mới và không tự sinh keypair hay chứng chỉ. Nó là công cụ **kết nối chính sách và nguồn credential vào TLS provider**.

## 6. TLS một chiều và mTLS: ai cần factory nào?

### 6.1 TLS server authentication (thường gọi “one-way TLS”)

Trong trường hợp client HTTPS kiểm tra server nhưng server **không yêu cầu certificate từ client**:

```text
SERVER                                   CLIENT
  |                                        |
  | Identity KeyStore                      | Truststore
  | Private key + certificate chain        | Trusted CA/peer certificate
  |         |                              |          |
  | KeyManagerFactory                      | TrustManagerFactory
  |         |                              |          |
  | KeyManager[]                           | TrustManager[]
  |         |                              |          |
  +----- SSLContext -----------------------+----- SSLContext
  |                                        |
  | ---- server certificate/handshake ---> |
  |                                        |
  |          client validates chain + hostname
  |                                        |
  +------ encrypted TLS records <--------->+
```

- **Server** cần **KeyManagerFactory** với identity key để trình bày chứng chỉ.
- **Client** cần **TrustManagerFactory** với truststore để kiểm tra server; identity key manager phía client có thể không cần.
- Server có thể đã khởi tạo trust manager nhưng **không sử dụng nó để xác thực client** nếu không yêu cầu client certificate.

### 6.2 Mutual TLS — mTLS

Trong **mTLS**, ngoài server authentication, server yêu cầu và xác minh certificate của client:

```text
SERVER                                           CLIENT
  Identity key + KeyManager                    Identity key + KeyManager
  Truststore + TrustManager                    Truststore + TrustManager
            |                                            |
   server certificate/possession  ------------> xác minh server
            |                                            |
   xác minh client certificate  <------------ client certificate/possession
            |                                            |
           +-------------- TLS secure session -----------+
```

Cả hai phía đều cần nguồn identity/trust tương ứng, dù **không bắt buộc chung một CA**. Với mTLS, server bật `setNeedClientAuth(true)` để **bắt buộc** client certificate; `setWantClientAuth(true)` chỉ **yêu cầu nếu có** theo contract, không tương đương bắt buộc.

Quan trọng: mTLS chứng minh bên tham gia handshake có credential được tin theo chính sách, **không tự cấp quyền nghiệp vụ**. Ứng dụng vẫn phải ánh xạ certificate identity (SAN, subject, SPIFFE ID hoặc thuộc tính đã phê duyệt) sang tài khoản/role/tenant và kiểm tra authorization.

### 6.3 So sánh trong một bảng

| Tình huống | Server KeyManager | Server TrustManager | Client KeyManager | Client TrustManager |
| --- | --- | --- | --- | --- |
| HTTPS/TLS server auth | **Có**: server identity | Không cần để xác thực client nếu không yêu cầu client cert | Có thể `null` | **Có**: CA/peer cho server |
| mTLS | **Có** | **Có**: CA/peer cho client | **Có**: client identity | **Có**: CA/peer cho server |
| TLS client chỉ nói chuyện với server public CA | Không thuộc bên client | Không thuộc bên client | Thường không cần client identity | Dùng default trust hoặc truststore được kiểm soát |
| Server xác thực client bằng cơ chế khác (OAuth/session) | **Có** để server auth | Không cần client cert nếu không dùng mTLS | Có thể `null` | **Có** để kiểm tra TLS server |

Không bật mTLS chỉ vì có `TrustManagerFactory` ở server: phải cấu hình **server socket/engine** yêu cầu client authentication và client phải có identity credential phù hợp.

## 7. Ma trận quyết định: thành phần nào cần được cấu hình?

Đặt câu hỏi trước khi viết code: **bên nào phải trình identity**, **bên nào phải xác minh peer**, và **ai điều khiển handshake**? Bảng dưới dùng TLS X.509 thông dụng, không thay thế chính sách của provider hoặc framework cụ thể.

| Tình huống | Local key managers | Peer trust managers | Hành động tiếp theo |
| --- | --- | --- | --- |
| Java client gọi HTTPS public API, không có client cert | Thường không cần client identity | Tin public CA phù hợp | HTTP client cần thực hiện hostname identification và handshake. |
| Java server có HTTPS certificate | Cần private key + leaf/chain phù hợp | Tùy chính sách xác thực client | SSLServerSocket/engine có server credentials, chưa mặc nhiên bật mTLS. |
| Java client gọi internal API bằng mTLS | Cần client private key + certificate chain | Tin đúng CA/peer của server | Cấu hình client SSLContext rồi kiểm server name khi handshake. |
| Java server bắt buộc mTLS | Cần server private key + certificate chain | Cần trust policy cho client certs | Đặt needClientAuth trước handshake và ánh xạ peer identity thành principal. |

**Ví dụ chẩn đoán nhanh:** client nhận `PKIX path building failed` dù server có private key hợp lệ. Trước tiên kiểm **trust policy phía client**, chain server thực gửi và CA có được chấp thuận hay không; đưa thêm private key vào client thường không giải quyết nguyên nhân này. Ngược lại, khi server không tìm thấy certificate/private key dùng được, cần kiểm **KeyManagerFactory, alias, chain, key password** và sự tương thích với handshake.

**Biên trách nhiệm:** trust manager xác minh certificate theo chính sách, nhưng ứng dụng phải kiểm soát endpoint identity theo TLS client stack và authorization của nghiệp vụ. Có truststore không làm server tự bắt buộc client certificate. Mỗi lời gọi chỉ có ý nghĩa trong vai trò của nó.

## 8. Bài thực hành suy luận trước khi dùng TLS loopback

Hãy tự giải ba tình huống, nêu rõ **dữ liệu đầu vào → manager được tạo → điều kiện để handshake thành công → bằng chứng cần kiểm**:

1. **Một chiều:** server có `server-identity.p12` chứa private key và SAN `localhost`; client có `server-trust.p12` chỉ chứa public certificate tin cậy. Bên nào chạy `KeyManagerFactory.init`, bên nào chạy `TrustManagerFactory.init`, và client kiểm hostname ở thời điểm nào?
2. **mTLS:** client được cấp `client-identity.p12`, server thêm CA client vào truststore và đặt `needClientAuth(true)`. Khác biệt nào xuất hiện khi client không có certificate, có certificate đúng CA hoặc có certificate sai CA?
3. **Thay CA:** một team thêm CA mới chỉ cho partner API. Vì sao nên cấu hình `SSLContext` riêng cho partner thay vì nhập CA đó vào truststore toàn JVM, và phải test những kết nối nào?

Đối với mỗi tình huống, một `SSLContext` được tạo thành công là **điểm bắt đầu**, không phải kết luận bảo mật. Xác minh bằng handshake thật, peer certificate, endpoint identity và negative tests. Bài 16.2 triển khai cấu hình keystore/CA và handshake đầy đủ; bài 16.5 kiểm chứng bốn trường hợp client authentication; bài 16.11 hướng dẫn đọc nguyên nhân thất bại. Bài này giữ việc **giải thích trách nhiệm** và ví dụ Java độc lập về trạng thái trước handshake ở phần tiếp theo.

## 9. Ví dụ Java 17+ độc lập: SSLContext và SSLEngine chưa phải handshake

Để thấy **SSLContext không tự kết nối mạng**, chạy chương trình thứ hai **không cần bất kỳ file `.p12` nào**. Ta tạo context, init với default managers do provider chọn, tạo một `SSLEngine` và chỉ định đây là client HTTPS — **không gọi beginHandshake, không truyền bytes qua mạng**.

Lưu thành **`JsseParametersDemo.java`**:

```java
import java.security.SecureRandom;
import javax.net.ssl.*;

public final class JsseParametersDemo {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, new SecureRandom());

        SSLEngine engine = context.createSSLEngine("localhost", 443);
        engine.setUseClientMode(true);

        SSLParameters params = engine.getSSLParameters();
        params.setEndpointIdentificationAlgorithm("HTTPS");
        engine.setSSLParameters(params);

        System.out.println(
                "Context protocol: " + context.getProtocol());
        System.out.println(
                "Engine client mode: " + engine.getUseClientMode());
        System.out.println(
                "HTTPS endpoint check configured: "
                        + "HTTPS".equals(
                                engine.getSSLParameters()
                                        .getEndpointIdentificationAlgorithm()));
        System.out.println(
                "No network handshake performed: true");
    }
}
```

```bash
javac -encoding UTF-8 JsseParametersDemo.java
java JsseParametersDemo
```

Stdout:

```text
Context protocol: TLS
Engine client mode: true
HTTPS endpoint check configured: true
No network handshake performed: true
```

Điều chương trình **đã làm**: khởi tạo một `SSLContext`, tạo `SSLEngine`, đặt client mode và cấu hình endpoint verification. Điều **chưa làm**: không nhận certificate, không kiểm tra chain, không validate hostname thực tế, không trao đổi key phiên và không mã hóa record. **`SSLContext.init` + `SSLParameters` không thay thế handshake**.

### 9.1 Vì sao SSLEngine tồn tại nếu đã có SSLSocket?

`SSLSocket` là TLS giao tiếp qua socket và thuận tiện cho I/O blocking. `SSLEngine` cung cấp **TLS engine không gắn cứng vào một Socket**; ứng dụng/framework điều khiển việc `wrap`/`unwrap` các `ByteBuffer` và vận chuyển bytes qua NIO/network layer do mình quản lý.

```text
SSLSocket:
  TCP socket + TLS engine + streams (I/O blocking interface)

SSLEngine:
  TLS handshake + record processing
             |
         application-managed buffers/network transport
```

Cả hai dùng các **managers từ SSLContext**, nhưng `SSLEngine` đòi hỏi state machine/handshake tasks/buffer management phức tạp. **Không** gọi `SSLEngine.wrap` một lần rồi coi như kết nối đã hoàn tất. Framework như Netty có thể quản lý phần này, nhưng vẫn cần cấu hình trust, hostname và identity đúng.

## 10. Vai trò các factory trong TLS handshake

Một TLS handshake thành công có nhiều bước. Sơ đồ sau là **luồng khái niệm**, không phản ánh mọi message TLS 1.2/1.3:

```text
CLIENT                                                   SERVER
   |                                                        |
   | ClientHello (versions, ciphers, key share, SNI...)      |
   |------------------------------------------------------->|
   |                                                        |
   |                                  server chọn chính sách TLS
   |<---------------------- ServerHello / certificate / proof
   |                                                        |
   | TrustManager(client):                                   |
   |  - chain tới CA/peer tin cậy?                            |
   |  - certificate/path/algorithm policy?                    |
   | SSLParameters/endpoint:                                  |
   |  - hostname/SAN khớp không?                              |
   |                                                        |
   |      [Nếu mTLS: server yêu cầu client certificate]       |
   |                                                        |
   | KeyManager(client):                                     |
   |   chọn client identity/certificate/private key          |
   |------------------------------------------------------->|
   |                                                        |
   |                           TrustManager(server):
   |                             client certificate hợp lệ?
   |                                                        |
   |<================= authenticated TLS records ===========>|
```

**Chi tiết đúng vai trò:**

- `KeyManager` hỗ trợ chứng minh **private key của local identity** khi protocol yêu cầu; không tự quyết định peer đáng tin.
- `TrustManager` đưa ra quyết định **peer certificate có chấp nhận được** theo cấu hình, nhưng cần bảo đảm endpoint identification và policy ứng dụng không bị bỏ qua.
- `SSLContext` cấp tài nguyên TLS provider, session cache, factories/engines và cấu hình; nó không tự phát chứng chỉ, quản lý root CA hay chọn route TCP.
- TLS provider còn thực hiện **key exchange, key schedule, record encryption, transcript integrity**, không cần app tự phối `Cipher`/ `KeyAgreement` cho từng record.
- **TLS 1.3** và **TLS 1.2** khác về thông điệp/kỹ thuật; không gắn các dòng sơ đồ trên với thứ tự packet bất biến của một phiên bản.

## 11. Cấu hình client authentication đúng nơi

### 11.1 need và want khác nhau

| Cài đặt server | Hành vi |
| --- | --- |
| `setNeedClientAuth(true)` | Yêu cầu client trình bày certificate được chấp nhận, nếu không thì handshake thất bại theo policy |
| `setWantClientAuth(true)` | Server **muốn** có client certificate và kiểm tra nếu được trình bày, nhưng **không bắt buộc** như need |
| Không yêu cầu client cert | Chỉ có server authentication theo cấu hình thông thường |
| Có TrustManager server nhưng không bật client auth | **Chưa tạo mTLS**: server không tự yêu cầu client certificate chỉ do có truststore |

Một công cụ test mTLS đúng phải thử cả **client có identity hợp lệ**, **client không gửi certificate**, và **client gửi certificate không được trust**. Nếu server đặt `want` và client không có certificate mà handshake vẫn thành công, điều đó **có thể đúng theo contract** — không nên đọc thành lỗi TrustManager.

### 11.2 Certificate identity khác authorization

Khi server TrustManager chấp thuận một client certificate, app vẫn phải quyết định client được phép **gọi API nào**, tenant nào, và bằng chứng identity có áp dụng cho endpoint đó không. Không tự ánh xạ `CN=admin` hoặc alias file `admin` thành quyền admin; nên dùng danh tính đã xác thực theo chính sách (SAN/URI/SPIFFE ID/fingerprint pinning hoặc PKI policy) và các quy tắc authorization tách biệt.

## 12. Default JSSE và custom SSLContext

Hệ thống Java có **cấu hình mặc định** và **context do ứng dụng dựng riêng**. Đừng nhầm chúng.

### 12.1 SSLContext.getDefault()

`SSLContext.getDefault()` trả về một context đã sẵn sàng. Nếu chưa có context được đặt bằng `setDefault`, lần đầu có thể tạo một implementation `"Default"` theo JDK/provider. Có thể có system properties như:

```text
javax.net.ssl.keyStore
javax.net.ssl.keyStoreType
javax.net.ssl.keyStorePassword

javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
javax.net.ssl.trustStorePassword
```

Các thuộc tính là một phần của cấu hình JSSE theo provider phù hợp; không mặc nhiên mọi HTTP client, Netty config, HSM hoặc custom SSLContext đều sử dụng chúng. **`-Djavax.net.ssl.trustStore` không có nghĩa mọi context trong process sẽ tự thay trust managers**, đặc biệt nếu framework truyền trust manager tường minh.

Trong implementation SunJSSE, mặc định truststore có thể tham chiếu đến `jssecacerts`, rồi `cacerts` theo quy tắc khi không chỉ định đường dẫn; chi tiết phụ thuộc JDK/distribution. Một path truststore được cấu hình sai/không tồn tại có thể dẫn tới tập trust rỗng hoặc handshake lỗi, không an toàn để trông chờ tự động fallback.

### 12.2 Vì sao nên dùng context riêng cho trust domain?

Ví dụ một ứng dụng gọi API công khai và API nội bộ:

```text
HTTPS public endpoint  ---> SSLContext dùng public CA trust policy
HTTPS internal API     ---> SSLContext dùng dedicated internal CA trust policy
mTLS to partner        ---> SSLContext có client identity + partner trust policy
```

Điều này giảm **blast radius** khi thêm một CA. Việc sửa file `cacerts` toàn JVM hoặc gọi `SSLContext.setDefault` để hỗ trợ một đối tác có thể tác động nhiều kết nối không liên quan. Tốt hơn là cấu hình context/truststore đúng scope mà thư viện HTTP thực sự sử dụng, rồi test.

### 12.3 Không đánh đồng default với provider-independent

`KeyManagerFactory.getDefaultAlgorithm()` và `TrustManagerFactory.getDefaultAlgorithm()` có thể khác theo JDK/provider/security properties. `SSLContext.getInstance("TLS")` cũng phụ thuộc provider đã đăng ký. Khi ứng dụng yêu cầu HSM/FIPS hoặc một trust implementation cụ thể, phải kiểm tra **provider thực tế, thuật toán được hỗ trợ, cỡ khóa, cipher suites và chứng nhận compliance** — không kết luận chỉ dựa trên việc API xuất hiện.

## 13. Certificate chain, PKIX và hostname trong TrustManager

Khi peer trình bày certificate chain, TrustManager của JSSE thường có logic dựa trên **X.509/PKIX** và truststore:

```text
Peer leaf -> intermediate(s) -> trust anchor được chấp thuận
                |
                +-- signature checks
                +-- validity and algorithm constraints
                +-- basic/key usage/extended key usage phù hợp
                +-- certificate policies, name constraints nếu áp dụng
                +-- revocation theo cấu hình/policy
                +-- endpoint identity/hostname theo TLS client configuration
```

**Đừng tự kết luận provider đã thực hiện mọi mục** từ một cặp `SSLContext + TrustManagerFactory`. JSSE APIs/provider, hostname algorithm, revocation settings, algorithm constraints, TLS role và custom trust managers quyết định điều gì được thực thi. Với HTTPS, hostname/SAN phải khớp endpoint; với mTLS, client certificate cần được mapping vào một identity/authorization policy rõ ràng.

### 13.1 Nếu chỉ import intermediate vào truststore thì sao?

Một intermediate là **mắt xích của chain**, không nhất thiết phải được cấu hình như một **trusted CA anchor**. Nếu thêm thẳng intermediate làm anchor, ứng dụng có thể vô tình mở rộng quyền tin cậy. Khi không tìm đủ chain, hướng đúng thường là:

- Kiểm tra server đã gửi **leaf + intermediate** phù hợp hay chưa;
- Tìm nguồn intermediate đáng tin cậy và cung cấp cho path builder/provider theo chính sách;
- Giữ trust anchors trong truststore được quản lý;
- Xác minh issuer/subject, signature, key usage, SAN, certificate path và thời hạn;
- Không tắt kiểm tra chứng chỉ hoặc hostname để qua handshake.

### 13.2 Revocation không tự bật chỉ vì có truststore

CRL và OCSP là các cơ chế kiểm tra certificate bị thu hồi. `TrustManagerFactory.init(trustStore)` không có nghĩa một hệ thống đã chọn được **revocation policy hoàn chỉnh** cho mọi loại certificate. Cần đánh giá `PKIXRevocationChecker`, provider defaults, CRL/OCSP source, stapling, cache, timeout và hành vi fail-open/fail-closed theo threat model. Không copy một dòng `setRevocationEnabled(false)` từ unit test PKIX vào hệ thống thật mà không có lý do.

## 14. SSLParameters: chính sách của từng connection

Ngoài managers của context, một socket/engine còn có **cấu hình phiên**: protocol/cipher suites, endpoint identification, SNI, ALPN và client auth.

| Thuộc tính | API ví dụ | Ghi chú |
| --- | --- | --- |
| Endpoint identification | `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Dành cho client TLS cần xác minh hostname theo hợp đồng HTTPS |
| TLS protocols | `SSLParameters.setProtocols(...)` / socket `setEnabledProtocols` | Kiểm tra default và policy; không tự bật SSLv3/TLSv1.0 |
| Cipher suites | `SSLParameters.setCipherSuites(...)` | Chỉ chọn suites được provider hỗ trợ và chính sách chấp thuận |
| Client certificate bắt buộc | `SSLServerSocket.setNeedClientAuth(true)` / `SSLParameters.setNeedClientAuth(true)` | Cấu hình phía server để yêu cầu mTLS |
| Client certificate tùy chọn | `setWantClientAuth(true)` | Không tương đương yêu cầu cứng |
| Server Name Indication | `SSLParameters.setServerNames(...)` | Giúp server chọn virtual host/cert khi client gửi SNI; không thay thế hostname verification |
| ALPN | `SSLParameters.setApplicationProtocols(...)` | Đàm phán giao thức ứng dụng như HTTP/2 khi stack hỗ trợ |
| Socket/Engine | `SSLSocket.setSSLParameters(...)`, `SSLEngine.setSSLParameters(...)` | Áp dụng tham số trước handshake |

**Không nên hardcode mọi protocol/cipher trong một bài nhập môn**: tập supported và default thay đổi theo JDK/provider/security updates. Chọn từ chính sách bảo mật tổ chức, tránh thuật toán đã bị loại bỏ, kiểm thử interop. Nên dùng TLS 1.3 hoặc TLS 1.2 được cấu hình an toàn theo chính sách khi tương thích; không tự bật TLS cũ chỉ vì đối tác handshake thất bại.

## 15. Xử lý lỗi: phân biệt KeyManager, TrustManager và SSLContext

| Triệu chứng / Exception | Khâu có thể gây ra | Hướng xử lý |
| --- | --- | --- |
| `KeyStoreException`, `IOException` khi load PKCS#12 | Identity/truststore file sai path, hỏng, password/type không đúng | Kiểm tra path, loại store, quyền và password, không log bí mật |
| `UnrecoverableKeyException` khi `KeyManagerFactory.init` | Key password không đúng/entry không truy cập được | Phân biệt key password với store password và quyền HSM |
| `NoSuchAlgorithmException` khi tạo factory/context | Provider/JDK không hỗ trợ thuật toán yêu cầu | Kiểm tra security providers và tên algorithm |
| `KeyManagementException` khi `SSLContext.init` | Manager/config/provider không thể khởi tạo | Giữ cause, fail fast và không fallback trust-all |
| `SSLHandshakeException: PKIX path building failed` | Client/server TrustManager không tìm được path hợp lệ đến anchor theo chính sách | Kiểm tra **truststore hiệu dụng**, chain, intermediate, root, thời hạn, usages, algorithm constraints |
| `SSLHandshakeException: No subject alternative ...` | Endpoint identification/SAN không khớp hostname/IP | Cấp certificate đúng SAN và dùng hostname đúng; không bỏ hostname verification |
| `SSLHandshakeException: bad_certificate` / `certificate_unknown` | Peer certificate không được chấp thuận hoặc không phù hợp | Kiểm tra role, CA, chain, EKU, mTLS policy; tránh đoán dựa trên alert đơn lẻ |
| `handshake_failure` / `no cipher suites in common` | Không thống nhất protocol, cipher, key type, signature scheme hoặc identity | Kiểm tra JDK/provider, enabled protocols, server certificate và peer requirements |
| `SSLPeerUnverifiedException` khi đọc peer cert | Chưa có authenticated peer/session phù hợp hoặc peer không cung cấp cert | Chỉ dùng sau handshake và theo role; không coi là lỗi CA duy nhất |
| `SSLException: Connection reset` / `SocketTimeoutException` | Mạng, firewall, timeout, peer đóng hoặc kết nối treo | Tách lỗi transport với lỗi certificate; có timeout và retry chính sách |
| `IllegalStateException` của `SSLEngine`/TLS API | Gọi handshake/engine sai mode/state hoặc reinit không đúng | Tuân thủ state machine, không tự bỏ qua handshake |

### 15.1 Quy trình chẩn đoán gọn

1. **Tách phía lỗi:** client từ chối server hay server từ chối client?
2. **Kiểm tra role:** identity keystore có `PrivateKeyEntry` đúng alias/chain không? Truststore có CA/peer được chấp thuận không?
3. **Kiểm tra đúng runtime:** ứng dụng dùng custom SSLContext hay default? Có system properties bị override trong framework/container không?
4. **Xem chain:** leaf/intermediate/trust anchor, expiration, SAN, EKU, key usage, algorithm policy.
5. **Kiểm tra hostname:** client kết nối tên nào? Certificate có SAN tương ứng? IP literal khác DNS name.
6. **Kiểm tra mTLS:** server có `needClientAuth` hay chỉ `wantClientAuth`? Client có key manager không?
7. **Kiểm tra protocols/cipher suites:** TLS 1.2/1.3, provider, key type, signature algorithms, disabled algorithms.
8. **Ghi log có kiểm soát:** `-Djavax.net.debug=ssl,handshake` trong môi trường test; tránh đưa secret hoặc thông tin nhạy cảm lên nơi công khai.

**Lỗi PKIX không phải lúc nào cũng do thiếu private key.** Nếu client không tin certificate server, đó thường là luồng **TrustManager**; nếu server không có local certificate phù hợp, đó thường là luồng **KeyManager**. Phân loại đúng sẽ giúp không “sửa” nhầm bằng cách import hàng loạt CA vào JDK `cacerts`.

## 16. Nguyên tắc an toàn khi tùy chỉnh Manager

### 16.1 Không tạo trust-all X509TrustManager

Một anti-pattern hay gặp:

```java
// ANTI-PATTERN minh họa, KHÔNG dùng.
// Đây là một method, không phải class độc lập:
public void checkServerTrusted(
        java.security.cert.X509Certificate[] chain, String authType) {
    // Không kiểm tra gì -> chấp nhận certificate giả mạo.
}
```

Nếu muốn trust một CA nội bộ, hãy xác thực CA đó và **khởi tạo `TrustManagerFactory` từ truststore có đúng CA**. Không dùng empty implementation của `checkServerTrusted`, không đặt `HostnameVerifier` luôn `true` hoặc bỏ qua certificate errors. Cách “chữa nhanh” ấy vô hiệu hóa xác thực TLS và mở cửa cho MITM.

### 16.2 Hạn chế tự viết KeyManager và TrustManager

Tùy chỉnh `X509ExtendedKeyManager` có thể cần khi chọn alias theo SNI, tenant hoặc key store đặc biệt. Tùy chỉnh `X509ExtendedTrustManager` có thể cần với pinning/PKIX policy riêng. Khi làm điều đó:

- Tái sử dụng chain/path verification tiêu chuẩn, không chỉ so sánh subject string;
- Duy trì kiểm tra endpoint identity và chính sách cipher/algorithm đúng role;
- Bảo đảm mọi overload dùng `SSLSocket` và `SSLEngine` đều được triển khai đúng;
- Không chấp nhận certificate thiếu trust anchor vì “app đã tự kiểm tra fingerprint” khi fingerprint chưa được quản lý đáng tin;
- Đặt tests cho public CA, internal CA, certificate rotation, wrong hostname, expired, revoked, wrong EKU, attacker/self-signed và TLS provider khác.

### 16.3 HSM và private key không export được

Một key manager có thể sử dụng **private key handle** từ HSM/PKCS#11 provider mà không trích raw key bytes. `PrivateKey.getEncoded() == null` không nhất thiết là lỗi; đó có thể là chính sách **non-extractable**. Không cố export key chỉ để đẩy vào `.p12`. Cần cấu hình đúng keystore type/provider, permissions và khả năng thao tác ký theo TLS stack.

## 17. Tình huống tự kiểm tra

**Tình huống A — Client gọi HTTPS nhưng báo `PKIX path building failed`.**  
**Đáp:** Thường bắt đầu từ **TrustManager/TrustManagerFactory** và truststore hiệu dụng của client: root/intermediate có hợp lệ không, SAN/hostname và algorithm constraints ra sao. Không import private key vào client hoặc tắt cert verification.

**Tình huống B — Server có `trust.p12` nhưng không có `identity.p12`, muốn trình bày certificate.**  
**Đáp:** Truststore không có private key. Server cần local identity/key manager phù hợp. `SSLContext` không tự sinh certificate.

**Tình huống C — Server có trust manager chứa CA của client nhưng client không hề gửi certificate.**  
**Đáp:** Trust manager có sẵn **không kích hoạt mTLS**. Server phải bật yêu cầu client authentication (`needClientAuth`), và client phải có KeyManager/certificate đúng chính sách.

**Tình huống D — Client gọi `context.init(null, null, null)`. Có phải vừa “trust all certificates” không?**  
**Đáp:** Không. `null` yêu cầu default behavior do implementation/provider/JDK xác định; **không** có nghĩa bỏ qua xác thực peer. Kiểm tra default trust path nếu không đáp ứng policy.

**Tình huống E — `SSLContext` đã init thành công, vậy hostname đã được xác minh?**  
**Đáp:** Không. Chưa có peer certificate hoặc handshake. Hostname/endpoint identification áp dụng khi thực hiện handshake theo cấu hình client.

**Tình huống F — `KeyManagerFactory.init(store, pass)` thành công nhưng server vẫn không có certificate phù hợp.**  
**Đáp:** Xem alias/private-key entry/chain, certificate validity/usage, key type/signature algorithms, SNI và TLS provider. Khởi tạo factory không bảo đảm mọi handshake sẽ tìm được identity đúng.

**Tình huống G — `TrustManagerFactory` dùng truststore chỉ có public CA, không có private key. Có thiếu thông tin không?**  
**Đáp:** Không. Để kiểm tra chữ ký certificate chain của peer, **không cần private key của CA/peer**; chỉ dùng public certificate/trust anchors và policy.

**Tình huống H — Đã tin root CA nhưng URL `https://wrong.example` không trùng SAN của leaf.**  
**Đáp:** Phải từ chối nếu endpoint identity theo HTTPS không khớp. Chain trust và hostname là hai kiểm tra khác nhau.

**Tình huống I — Mọi dịch vụ trong process đều dùng default SSLContext; muốn thêm CA chỉ cho một partner.**  
**Đáp:** Nên tạo/customize **SSLContext riêng** cho trust domain của partner nếu client library hỗ trợ, thay vì mở rộng `cacerts` toàn JVM.

**Tình huống J — mTLS client certificate hợp lệ nhưng caller muốn thao tác thuộc tenant khác.**  
**Đáp:** mTLS chỉ là bước xác thực credential; cần **authorization ở tầng ứng dụng** gắn identity đã xác thực với quyền/tenant.

## 18. Checklist trước khi đưa JSSE vào production

- Xác định rõ **TLS server auth** hay **mTLS**; bên nào cần local private key, bên nào cần trust policy.
- Cung cấp identity `KeyStore` có `PrivateKeyEntry` và certificate chain phù hợp; tránh dùng certificate-only alias như identity.
- Cung cấp truststore đúng scope; chỉ tin CA/peer đã xác minh nguồn và được chấp thuận.
- `KeyManagerFactory.init(identity, keyPassword)`; `TrustManagerFactory.init(trustStore)`; `SSLContext.init(km, tm, random)` đúng vai trò.
- Bật **HTTPS endpoint identification** ở low-level TLS client nếu framework chưa đảm bảo; không bỏ SAN/hostname checks.
- Với mTLS, server cấu hình **needClientAuth** phù hợp, và ứng dụng ánh xạ client certificate vào authorization policy.
- Sử dụng TLS versions/cipher suites và thuật toán khóa đáp ứng chính sách của runtime hiện tại; không fallback yếu.
- Kiểm tra revocation, chain, EKU/key usage, certificate expiry, rotation, trust anchor changes và provider compatibility.
- Không hardcode private key/password, không log secret/handshake secrets, không import certificate chưa tin chỉ để chữa lỗi.
- Có thử nghiệm **tích cực** (server/client hợp lệ) và **tiêu cực** (sai CA, hostname, expired, missing private key, mTLS client không có cert).
- Kiểm thử trên đúng JDK, JSSE provider, OS/container và HTTP client được triển khai; không suy ra toàn bộ từ unit test `SSLContext.init`.
- Tách context theo trust domain khi hợp lý; quản trị CA root và private key theo quy trình bảo mật riêng.

## Tài liệu chính thức

1. [Java SE 17 — `SSLContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): `getInstance`, `init`, socket factories, `SSLEngine`, default context và parameters.
2. [Java SE 17 — `KeyManagerFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): tạo `KeyManager` từ local identity keystore.
3. [Java SE 17 — `TrustManagerFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): tạo `TrustManager` từ truststore hoặc parameters.
4. [Java SE 17 — `SSLSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html), [`SSLServerSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLServerSocket.html), [`SSLEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html): TLS handshake với socket hoặc engine độc lập transport.
5. [Java SE 17 — `SSLParameters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification, client auth, protocols, cipher suites và SNI.
6. [Java SE 17 — `KeyStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): loại entry và load/alias/password.
7. [Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): mô hình key/trust manager, default keystore/truststore và TLS configuration.
8. [Java SE 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): tạo và export/import certificate của lab.
9. [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html): các vai trò xác thực, key schedule và bảo vệ record trong TLS 1.3.
10. [RFC 5280 — X.509 PKIX](https://www.rfc-editor.org/rfc/rfc5280.html): certificate path, validity, certificate policies và trust anchors.

**Kết luận:** Hãy nhớ ba hướng tác động khác nhau: **KeyManagerFactory = cung cấp local identity/private-key credentials**, **TrustManagerFactory = xác minh certificate/trust của peer**, còn **SSLContext = ngữ cảnh phối hợp managers và TLS provider để tạo socket/engine**. Một kết nối an toàn còn đòi hỏi TLS handshake hoàn chỉnh, hostname/endpoint identity đúng, CA/trust anchors được quản lý, và **authorization riêng** khi dùng mTLS.