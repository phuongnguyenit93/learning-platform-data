# 16.2 Khởi tạo SSLContext từ khóa riêng, chuỗi chứng thư và tập CA tin cậy

Trong **JSSE (Java Secure Socket Extension)**, đối tượng **`javax.net.ssl.SSLContext`** là nơi ứng dụng kết hợp hai nhóm thông tin hoàn toàn khác nhau:

1. **Danh tính của chính ứng dụng (local identity):** **private key** và **chuỗi chứng thư X.509** tương ứng, để phía Java có thể chứng minh mình sở hữu private key khi TLS handshake yêu cầu. Nguồn thường là **identity keystore**.
2. **Các CA/chứng thư mà ứng dụng chấp nhận tin cậy (peer trust):** tập **trust anchors** dùng để kiểm tra chứng thư của phía bên kia, thường được cấp phát qua **truststore** và `TrustManagerFactory`.

Hai nhóm dữ liệu được đưa vào `SSLContext` qua **`KeyManagerFactory`** và **`TrustManagerFactory`**. Tên gọi “SSLContext” là tên API lịch sử: trong chương trình hiện đại, dùng **TLS**, không bật SSLv2/SSLv3 hoặc TLS cổ không còn được phép theo chính sách.

Bài này hướng dẫn đầy đủ mô hình private key → certificate chain → `KeyManager`, trust anchors → `TrustManager`, các bước gọi `SSLContext.init(...)`, cấu hình socket và endpoint identification; có **bộ lệnh `keytool` tạo CA demo, server certificate do CA ký, truststore**, cùng **chương trình Java 17+** đã kiểm thử bắt tay TLS 1.3 qua loopback. Cuối bài phân tích mTLS, thay chứng thư, mật khẩu kho/khóa, lỗi handshake và các lỗi bảo mật phổ biến.

> **Ghi nhớ:** `KeyManager` quyết định **“tôi trình bày danh tính và private key nào?”**; `TrustManager` quyết định **“tôi có tin certificate chain của peer hay không?”**. Chúng không thể thay thế nhau.

## 1. Bốn thành phần cần phân biệt trước khi viết code

| Thành phần | Bản chất | Ai giữ | Vai trò trong TLS |
| --- | --- | --- | --- |
| **Private key** | Khóa bí mật bất đối xứng, chẳng hạn RSA hoặc EC | Chỉ bên sở hữu danh tính, hoặc HSM/KMS của bên đó | Thực hiện phép ký/chứng minh sở hữu khóa trong TLS handshake |
| **Leaf certificate** | X.509 certificate mang public key và định danh DNS/IP/SAN | Có thể công bố | Ràng buộc public key với danh tính theo thông tin do CA xác nhận |
| **Certificate chain** | Leaf rồi CA trung gian tương ứng; có thể gồm root tùy kho/format | Có thể gửi qua TLS; không phải secret | Cho phép peer xây đường dẫn đến CA mà **peer** đã tin từ trước |
| **Trusted CA/root** | Trust anchor được ứng dụng chấp thuận theo chính sách | Nằm trong truststore hoặc nguồn tin cậy được cấu hình | Là điểm kết thúc đường dẫn xác minh của certificate **peer** |

### 1.1. “Có certificate” không có nghĩa “có private key”

File `server.crt` hoặc `server.pem` thường chứa **certificate công khai**, không tự chứa private key. Khi ứng dụng cần làm TLS server và trình bày danh tính, `KeyManagerFactory` cần lấy được **private key khớp với public key của leaf certificate**, kèm chain phù hợp. Nếu chỉ nạp một trusted certificate vào `KeyStore` bằng `setCertificateEntry(...)`, ứng dụng không tự trở thành TLS server có danh tính tương ứng.

### 1.2. Root CA trong chuỗi khác root CA trong truststore

Ví dụ:

```text
                              SERVER                          CLIENT
             +--------------------------------+    +-------------------------+
             | Identity Keystore (PKCS12)     |    | Truststore (PKCS12)     |
             |   Alias: service               |    |  TrustedCertEntry: ca   |
             |     PrivateKey (secret)        |    |   Root CA certificate   |
             |     Leaf: CN=localhost         |    +------------+------------+
             |     Issuer: Demo Root CA       |                 |
             |     Chain: [leaf, Root CA]     |                 |
             +----------------+---------------+                 |
                              |                                 |
                     KeyManagerFactory                   TrustManagerFactory
                              |                                 |
                          KeyManager                       TrustManager
                              |                                 |
                              +------------+--------------------+
                                           |
                                SSLContext.init(...)
                                           |
                             SSLSocket / SSLServerSocket
```

Trong **sản phẩm**, chuỗi certificate gửi trên TLS thường gồm **leaf + intermediate**, còn **root trust anchor** được peer giữ độc lập và thông thường không cần gửi. Fixture của bài có chain **2 chứng thư [leaf, root]** vì chỉ dùng một CA demo ký trực tiếp, giúp thấy đầy đủ mối liên hệ. Việc root có mặt trong chain phía server **không làm client tự tin root đó**: client vẫn phải có root trong truststore đã cấp phát trước.

### 1.3. Identity keystore và truststore đều có thể là `KeyStore`

`java.security.KeyStore` là API trừu tượng để giữ keys/certificates. Không có hai class Java riêng tên “IdentityKeyStore” và “TrustKeyStore”:

- **Identity keystore** thường có `PrivateKeyEntry` và certificate chain của chính ứng dụng.
- **Truststore** thường có `TrustedCertificateEntry` cho CA được tin. Nó **không cần** private key của CA đó.
- Cả hai có thể dùng định dạng `PKCS12`; tên `.p12`/`.jks` không phải bằng chứng tuyệt đối về kiểu.
- `KeyStore` cũng có thể đại diện HSM/PKCS11, nơi private key không xuất ra byte.
- Java hiện đại thường dùng `PKCS12` làm keystore type mặc định, nhưng nên chọn rõ loại khi viết bài học và kiểm tra provider.

Một `PKCS12` chứa CA certificate do ứng dụng **tự nhập từ nguồn không đáng tin** không biến CA đó thành đáng tin về mặt nghiệp vụ. **Đầu vào truststore phải được xác minh và phê duyệt độc lập**.

## 2. Toàn bộ đường đi từ certificate/key đến SSLContext

Có hai factory quan trọng của JSSE:

```text
[identity key file + certificate chain]       [approved trusted CA certificates]
             |                                               |
       KeyStore identity                               KeyStore trusted
             |                                               |
       KeyManagerFactory                              TrustManagerFactory
       init(identity, keyPass)                         init(trusted)
             |                                               |
          KeyManager[]                                  TrustManager[]
             |                                               |
             +-------------------+---------------------------+
                                 |
          SSLContext.getInstance("TLS")
          SSLContext.init(keyManagers, trustManagers, SecureRandom)
                                 |
                +----------------+---------------+
                |                                |
        getSocketFactory()              getServerSocketFactory()
        SSL client socket               SSL server socket
                |                                |
        SSLParameters/handshake/peer certificate validation
```

### 2.1. `KeyStore.load` — đọc kho, chưa phải lấy key

```java
KeyStore identity = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("server.p12"))) {
    identity.load(in, storePassword);
}
```

Đây là **trích đoạn minh họa**, cần các `import` và biến `storePassword`. `storePassword` thường dùng khi nạp/bảo vệ tính toàn vẹn của kho theo provider và format. **Nạp thành công không có nghĩa** đã khôi phục được private key dưới alias mong muốn.

Kiểm tra nội dung cần dùng:

```java
boolean hasKey = identity.isKeyEntry("service");
Certificate[] chain = identity.getCertificateChain("service");
```

Nếu `hasKey == false`, alias đó có thể không tồn tại hoặc chỉ là certificate entry. Nếu `chain == null`, không có certificate chain thích hợp cho alias; không gọi `chain.length` trước khi kiểm tra trong code production.

### 2.2. `KeyManagerFactory.init` — phục hồi private key identity

```java
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identity, keyPassword);
KeyManager[] managers = kmf.getKeyManagers();
```

`keyPassword` là **mật khẩu bảo vệ private key entry** theo keystore type/provider. Nó **có thể khác** `storePassword`. Một số công cụ PKCS12, đặc biệt nhiều phiên bản `keytool`, có thể yêu cầu hoặc giả định hai mật khẩu giống nhau. Hãy dựa trên cách tạo file/provider thực tế, không coi hai khái niệm là một.

`KeyManagerFactory.getDefaultAlgorithm()` lựa chọn thuật toán key manager mặc định của môi trường; tránh hardcode tên provider/algorithm không cần thiết. `kmf.init(...)` có thể ném `UnrecoverableKeyException` khi keypass không đúng dù `KeyStore.load(...)` vừa thành công.

**Lưu ý quan trọng:** overload `KeyManagerFactory.init(KeyStore, char[])` cung cấp **một key password**. Với nhiều private-key entries được bảo vệ bằng các mật khẩu khác nhau, provider/framework có thể cần `KeyStore.Builder`/`KeyStoreBuilderParameters`, cấu hình alias hoặc nhiều context/keystore riêng. Không tự giả định mọi entry sẽ mở được.

### 2.3. `TrustManagerFactory.init` — danh sách CA tin cậy

```java
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);
TrustManager[] managers = tmf.getTrustManagers();
```

Trích đoạn này dùng `trustStore` đã được nạp và **chứa trust anchors được phê duyệt**. Factory tạo trust manager phù hợp provider, thường có `X509TrustManager`/`X509ExtendedTrustManager` thực hiện kiểm tra certificate chain theo chính sách PKIX/JSSE.

- **Không** lấy mọi certificate server vừa gửi và gọi `setCertificateEntry` để “tạo CA tin cậy” tức thời.
- **Không** thay `tmf.init(trustStore)` bằng một `X509TrustManager` tự chế trả về mà không kiểm tra: đó là **trust-all**, vô hiệu hóa xác thực peer.
- Nếu truyền `null` thay truststore cho `TrustManagerFactory.init((KeyStore)null)`, provider thường dùng **nguồn trust mặc định của môi trường**; không có nghĩa “không kiểm tra certificate”.
- Nếu truyền một truststore rỗng, thông thường handshake tới certificate không có trust anchor phù hợp sẽ thất bại.

### 2.4. `SSLContext.init` — nơi ghép hai tập manager

```java
SSLContext context = SSLContext.getInstance("TLS");
context.init(kmf.getKeyManagers(), tmf.getTrustManagers(),
             new SecureRandom());
```

Đây là đoạn kết hợp trọng tâm. Phương thức:

```text
SSLContext.init(KeyManager[] km, TrustManager[] tm, SecureRandom random)
```

Ý nghĩa:

- **`km`:** cung cấp credential của **local endpoint** khi TLS cần trình bày danh tính. TLS server thông thường cần server identity; TLS client chỉ cần client identity khi server yêu cầu **mTLS/client certificate**.
- **`tm`:** kiểm tra **peer certificate chain** khi có peer authentication. TLS client cần trust CA của server; mTLS server cũng phải tin CA của client.
- **`random`:** nguồn ngẫu nhiên mật mã cho provider JSSE, thường có thể là `new SecureRandom()` hoặc provider tự quản lý nguồn thích hợp. Không dùng `java.util.Random` thay thế.
- **`SSLContext.getInstance("TLS")`:** chọn một họ TLS được provider hỗ trợ; **không tự buộc** các socket chỉ dùng TLS 1.3. Phiên bản giao thức, cipher suites, endpoint ID và client-auth là chính sách cấu hình **trên socket/engine/SSLParameters** hoặc tầng HTTP framework.

`context.init(...)` **không mở cổng mạng, chưa gửi certificate, chưa bắt tay TLS**. Handshake chỉ xảy ra khi dùng `SSLSocket`/`SSLEngine` với kết nối thật.

## 3. Phân biệt ba cách khởi tạo thường gặp

### 3.1. TLS server một chiều (server authentication)

Server có private key + certificate chain. Client xác minh certificate server qua CA.

```text
SERVER: init(KeyManager[server identity], TrustManager[optional peer CA], random)
CLIENT: init(null, TrustManager[server CA], random)
```

Ở một chiều, server **không bắt buộc** phải có truststore dành cho client certificates nếu nó không yêu cầu client-auth; một trust manager được cấu hình phía server có thể không được dùng trong handshake đó. Client có truststore để xác thực server.

### 3.2. Mutual TLS — mTLS

Server **và** client đều sở hữu private key + certificate chain, và cả hai đều có danh sách CA tin cậy để xác thực peer.

```text
SERVER: init(KeyManager[server identity], TrustManager[trusted client CA], random)
CLIENT: init(KeyManager[client identity], TrustManager[trusted server CA], random)
SERVER: setNeedClientAuth(true) / cấu hình SSLEngine tương đương
```

**Chỉ cấu hình trust manager phía server không tự bật mTLS.** Server phải yêu cầu client certificate qua `SSLServerSocket.setNeedClientAuth(true)` hoặc `SSLParameters.setNeedClientAuth(true)` ở tầng framework. Client phải có key manager với certificate/key tương ứng.

Một số ứng dụng có thể dùng `setWantClientAuth(true)`, nghĩa là yêu cầu nhưng có thể cho phép không có client certificate; nó **không tương đương** yêu cầu bắt buộc. Nếu nghiệp vụ đòi hỏi client authentication, hãy dùng `needClientAuth` và kiểm tra ánh xạ identity/quyền.

### 3.3. Client chỉ cần xác thực HTTPS server

Một HTTPS client không có client certificate có thể khởi tạo:

```java
SSLContext clientContext = SSLContext.getInstance("TLS");
clientContext.init(null, tmf.getTrustManagers(), new SecureRandom());
```

**`km == null`** không phải “không xác thực server”; trách nhiệm kiểm tra server nằm ở **trust manager**. Trái lại, cấu hình `TrustManager[]` kiểu trust-all mới làm nguy hiểm quá trình peer authentication.

**`tm == null`** trong `SSLContext.init` cho phép provider dùng trust manager mặc định; điều đó **khác** đưa vào một array trust manager tùy chỉnh với logic cho phép tất cả.

## 4. Khởi tạo identity keystore từ private key và certificate chain

Trường hợp phổ biến nhất là đọc một **PKCS12 chứa sẵn private key và chain**. Nhưng về mặt API, ứng dụng cũng có thể đã có một `PrivateKey` và `Certificate[]` được parse/khôi phục hợp lệ, rồi tạo một `KeyStore` trong bộ nhớ:

```java
// Fragment minh họa, KHÔNG phải chương trình độc lập.
// privateKey: PrivateKey ứng với public key của leaf.
// chain: Certificate[] có thứ tự [leaf, issuer, ...].
// storePassword/keyPassword: char[] từ secret manager hoặc nguồn an toàn.

KeyStore identity = KeyStore.getInstance("PKCS12");
identity.load(null, storePassword);
identity.setKeyEntry("service", privateKey, keyPassword, chain);

KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identity, keyPassword);
```

### 4.1. Yêu cầu với certificate chain

Chuỗi certificate cần có thứ tự từ **leaf** tới CA cấp trên. Nếu có các CA trung gian, mỗi chứng thư phải do CA ở vị trí tiếp theo ký và đáp ứng BasicConstraints, KeyUsage, thuật toán, validity, path-length, name constraints và policy.

Ví dụ:

```text
chain[0] = Leaf:       Subject=CN=api.example, Issuer=CN=Intermediate
chain[1] = Intermediate: Subject=CN=Intermediate, Issuer=CN=Root
# Root thường được client tin riêng trong truststore.
```

**Không** lấy một danh sách chứng thư bất kỳ và nối thành chain theo thứ tự tên. **Không** lấy cert của CA không tin rồi tự thêm vào truststore chỉ để TLS không báo lỗi.

Private key phải **khớp public key của leaf**. `KeyStore.setKeyEntry` có thể chấp nhận một số dữ liệu ở cấp API nhưng điều đó chưa bảo đảm handshake được; nên kiểm tra operation thật và validate đầu vào qua quy trình phát hành chứng thư.

### 4.2. Nếu private key ở file PEM

Một file PEM private key có thể ở dạng **PKCS#8**, **encrypted PKCS#8**, dạng chuyên biệt của thuật toán, hoặc dạng do một công cụ xuất. Không thể đơn giản gọi `Base64.getDecoder()` trên một blob PEM bất kỳ rồi truyền cho `SecretKeySpec`:

- `SecretKeySpec` dành cho **khóa đối xứng**, không phải `PrivateKey` RSA/EC.
- Nếu là PKCS#8 chưa mã hóa, sau khi parse đúng DER có thể dùng `PKCS8EncodedKeySpec` + `KeyFactory` của thuật toán tương ứng.
- Nếu là encrypted PKCS#8, cần giải mã bằng password/PBE phù hợp và provider; không log key bytes.
- Với HSM/PKCS11, private key có thể chỉ tồn tại dưới dạng **key handle không xuất được**, không nên chuyển thành file PEM.
- Việc parse PEM/certificate **không thay** kiểm tra khóa/certificate chain và nguồn trust.

Vì bài này tập trung **JSSE**, ví dụ chạy được sẽ dùng PKCS12 do `keytool` phát hành, tránh viết parser PEM/private-key tùy tiện.

## 5. Tạo truststore từ CA đã được phê duyệt

Trong code, chỉ khi đã có một `X509Certificate trustedCa` nhận từ **kênh cấp phát tin cậy** và kiểm chứng fingerprints/chính sách, ứng dụng mới nên đưa nó vào truststore:

```java
// Fragment: trustedCa đã được xác minh ngoài bối cảnh code này.
KeyStore trustStore = KeyStore.getInstance("PKCS12");
trustStore.load(null, trustStorePassword);
trustStore.setCertificateEntry("approved-ca", trustedCa);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);
```

`setCertificateEntry` không cần private key của CA và **không** cần keypass riêng cho CA certificate. Nhưng **đưa certificate vào truststore là hành động cấp quyền tin cậy**, vì nó có thể cho phép chấp nhận tất cả leaf certificates hợp lệ theo CA đó và chính sách kiểm tra tương ứng.

### 5.1. CA nào nên tin?

- Với hệ thống nội bộ, truststore có thể chỉ có **CA nội bộ được ủy quyền**, không cần nhập toàn bộ CAs công cộng.
- Với HTTPS công cộng, truststore mặc định của JDK/hệ điều hành có thể đã có tập CA được quản lý; không tự sao chép danh sách CA từ một website không xác thực.
- Với mTLS, server có thể cần CA nội bộ chuyên ký **client certificates**, khác tập CA dành cho server.
- Với Certificate Pinning, nên hiểu việc pin đúng định danh/khóa và kế hoạch rotation; pin sai có thể gây outage khi đổi chứng thư.

**Truststore nhỏ** có thể giảm phạm vi tin cậy nhưng tăng nhu cầu vận hành CA rotation. **Truststore quá rộng** có thể mở rộng những issuer mà ứng dụng chấp nhận ngoài yêu cầu nghiệp vụ. Cân nhắc theo môi trường và mức rủi ro.

### 5.2. Trust store không thay hostname verification

Certificate chain có thể được một CA đã tin ký hợp lệ **nhưng mang SAN của một dịch vụ khác**. TLS client phải kiểm tra danh tính endpoint dựa trên **hostname hoặc IP đang kết nối**, không chỉ xác thực CA. Với `SSLSocket`, bật:

```java
SSLParameters params = socket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
socket.startHandshake();
```

Đây là fragment; `socket` là `SSLSocket` đang được cấu hình **trước handshake**. Tên `"HTTPS"` điều khiển quy tắc xác minh endpoint phù hợp với tên DNS/IP mà client cung cấp khi tạo socket/SSLEngine. **Không** dùng `""` hoặc bỏ thuộc tính này để lách lỗi certificate “không khớp hostname”.

Với HTTP client API cấp cao (ví dụ `HttpClient`), nhiều bước endpoint identification được framework xử lý theo hợp đồng riêng; đừng cấu hình thủ công gây xung đột hoặc vô hiệu hóa kiểm tra đã có.

## 6. Dựng CA thử nghiệm, certificate chain và truststore bằng `keytool`

Để thấy rõ **private key + certificate chain + CA tin cậy**, ta tạo ba kho/tệp trong một **thư mục test tạm, trống**:

```text
ca.p12       = CA demo, chứa private key của CA (chỉ dùng cấp chứng thư)
ca.pem       = public certificate của CA demo
server.p12   = private key server + chain [server leaf, demo CA]
server.csr   = certificate signing request (CSR) của server
server.crt   = leaf certificate do demo CA ký
trust.p12    = trusted certificate entry chứa demo CA, không có CA private key
```

**Cảnh báo:** các lệnh bên dưới dùng mật khẩu mẫu `demo-changeit` dưới dạng command-line để ai cũng tái hiện được trong môi trường cô lập. **Không làm vậy với production secret**: tham số command-line có thể lộ qua shell history, process list, CI logs. Tạo fixture ở thư mục test, không commit private key/PKCS12, xóa sau khi kiểm thử; production dùng secret manager, prompt và quy trình phát hành chứng thư được kiểm soát.

Các lệnh dưới đây chạy một dòng trên Bash, PowerShell hoặc CMD khi `keytool` của JDK ở `PATH`. Chạy theo đúng thứ tự trong **thư mục trống**.

### 6.1. Bước 1 — tạo CA demo

```bash
keytool -genkeypair -alias ca -keyalg RSA -keysize 2048 -validity 30 -dname "CN=Demo Local CA,O=Learning" -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -storetype PKCS12 -keystore ca.p12 -storepass demo-changeit -keypass demo-changeit -noprompt

keytool -exportcert -rfc -alias ca -keystore ca.p12 -storepass demo-changeit -file ca.pem
```

- `ca.p12` chứa **private key CA**, tuyệt đối không đưa vào ứng dụng client/server hoặc chia sẻ lên network.
- `ca.pem` chỉ chứa **CA public certificate**, dùng để xác thực chữ ký leaf và nhập truststore test.
- `BasicConstraints: CA=true` và `KeyUsage: keyCertSign,cRLSign` giúp chứng thư có mục đích CA phù hợp trong demo.
- CA tự tạo này **không** được trình duyệt/JDK mặc định tin. Chỉ ứng dụng test chủ động import nó mới tin.

### 6.2. Bước 2 — tạo identity key và CSR của server

```bash
keytool -genkeypair -alias service -keyalg RSA -keysize 2048 -validity 30 -dname "CN=localhost,O=Learning" -ext "SAN=dns:localhost,ip:127.0.0.1" -storetype PKCS12 -keystore server.p12 -storepass demo-changeit -keypass demo-changeit -noprompt

keytool -certreq -alias service -keystore server.p12 -storepass demo-changeit -file server.csr -ext "SAN=dns:localhost,ip:127.0.0.1"
```

`server.p12` trước khi nhập chứng thư CA có một private key và certificate tự ký tạm. `server.csr` đưa public key và thông tin đề xuất để CA phát hành **leaf certificate chính thức cho demo**. SAN phải có **`DNS:localhost`** để client kết nối với tên `localhost` và kiểm tra hostname. SAN `IP:127.0.0.1` phục vụ kiểm tra khi client dùng địa chỉ IP trực tiếp.

Chỉ có `CN=localhost` **không** phải lý do để bỏ qua SAN; các TLS stacks hiện đại ưu tiên/đòi SAN để xác minh tên endpoint.

### 6.3. Bước 3 — CA ký leaf certificate

```bash
keytool -gencert -alias ca -keystore ca.p12 -storepass demo-changeit -infile server.csr -outfile server.crt -rfc -validity 30 -ext "SAN=dns:localhost,ip:127.0.0.1" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -ext "BC:critical=ca:false"
```

Các extension có ý nghĩa:

- **SAN:** ràng buộc chứng thư server với tên hoặc IP dự kiến.
- **KeyUsage:** phục vụ các thao tác TLS cho phép theo thuật toán và protocol.
- **ExtendedKeyUsage: `serverAuth`:** certificate được cấp cho mục đích chứng thực TLS server.
- **BasicConstraints: `ca:false`:** leaf không có vai trò CA.

CA certificate của demo và leaf đều có hạn `30 ngày` để giảm tuổi thọ fixture. Thời hạn dùng công cụ vẫn phụ thuộc lịch/đồng hồ máy; nếu hết hạn, hãy tạo fixture mới.

### 6.4. Bước 4 — lắp chain cho server và truststore cho client

```bash
keytool -importcert -alias root-ca -file ca.pem -keystore server.p12 -storepass demo-changeit -noprompt

keytool -importcert -alias service -file server.crt -keystore server.p12 -storepass demo-changeit -noprompt

keytool -importcert -alias root-ca -file ca.pem -keystore trust.p12 -storetype PKCS12 -storepass demo-changeit -noprompt
```

**Thứ tự quan trọng:** import CA certificate vào `server.p12` **trước** khi import certificate reply cho alias `service` để `keytool` có thể dựng chuỗi. Sau khi hoàn thành:

- `server.p12` alias `service` là **PrivateKeyEntry** có chain `[server leaf, CA]`.
- `trust.p12` alias `root-ca` là **TrustedCertificateEntry** không có private key.
- Client tin CA demo vì ta **chủ động** đưa CA vào truststore test; đây là hành động cấu hình tin cậy, không phải hệ quả tự nhiên của certificate server.

Kiểm tra certificate chain bằng:

```bash
keytool -list -v -alias service -keystore server.p12 -storepass demo-changeit
```

Trong output mong đợi có **`Certificate chain length: 2`**. Đừng dùng mỗi lệnh `-list` làm bằng chứng handshake hoàn chỉnh: còn phải kiểm tra private key truy cập được, trust anchor, SAN, EKU và TLS handshake thực tế.

### 6.5. Vì sao không dùng CA self-signed leaf luôn?

Một server có thể dùng certificate tự ký trong một số môi trường test và client tin pin trực tiếp. Nhưng khi học chủ đề **“khóa riêng, chuỗi chứng thư và CA tin cậy”**, việc dùng **CA demo ký leaf** cho thấy rõ các ranh giới:

- CA ký leaf **không** trao private key CA cho server.
- Server trình bày **private key server** và **certificate chain**; client không cần private key server.
- Client chỉ nắm **CA public certificate** làm điểm tin cậy.
- Một certificate leaf do CA demo ký vẫn phải có SAN phù hợp và chưa hết hạn.

## 7. Java 17+ runnable: khởi tạo hai SSLContext và bắt tay TLS 1.3

Chương trình **`JsseSslContextDemo.java`** là một minh họa đầy đủ, sử dụng các file từ mục 6. Nó:

1. Nạp `server.p12` bằng `KeyStore.load`; kiểm tra alias `service` có key entry và chain hai chứng thư.
2. Nạp `trust.p12` có một trusted CA certificate.
3. Khởi tạo `KeyManagerFactory` từ identity keystore; `TrustManagerFactory` từ truststore; ghép vào **server SSLContext**.
4. Khởi tạo **client SSLContext** chỉ từ truststore (không có private key client vì đây là **one-way TLS**).
5. Mở `SSLServerSocket` trên địa chỉ loopback `127.0.0.1` và port được hệ điều hành chọn; dùng `SSLSocket` client, thiết lập `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` rồi bắt tay **TLS 1.3**.
6. Trao đổi một byte giá trị `41` rồi server trả về `42`, chứng minh hai phía có kênh TLS thực sự, không chỉ tạo được `SSLContext`.

Không cần internet, DNS bên ngoài hay một server public. Server chạy một task nội bộ để chấp nhận **một** kết nối, sau đó đóng socket/Executor. File chỉ dùng cho test; không triển khai thành một server nhận nhiều client.

### 7.1. Mã nguồn hoàn chỉnh: `JsseSslContextDemo.java`

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class JsseSslContextDemo {
    private static KeyStore loadPkcs12(Path file, char[] password)
            throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(file)) {
            store.load(in, password);
        }
        return store;
    }

    private static SSLContext createServerContext(KeyStore identity,
            char[] privateKeyPassword, KeyStore trustStore) throws Exception {
        KeyManagerFactory keys = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        keys.init(identity, privateKeyPassword);

        TrustManagerFactory trust = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        trust.init(trustStore);

        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(keys.getKeyManagers(), trust.getTrustManagers(),
                new SecureRandom());
        return ctx;
    }

    private static SSLContext createClientContext(KeyStore trustStore)
            throws Exception {
        TrustManagerFactory trust = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        trust.init(trustStore);

        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(null, trust.getTrustManagers(), new SecureRandom());
        return ctx;
    }

    private static void exchangeOnce(SSLContext serverContext,
            SSLContext clientContext) throws Exception {
        try (SSLServerSocket listener = (SSLServerSocket) serverContext
                .getServerSocketFactory()
                .createServerSocket(0, 20,
                        InetAddress.getByName("127.0.0.1"))) {
            listener.setEnabledProtocols(new String[]{"TLSv1.3"});
            listener.setSoTimeout(10_000);

            ExecutorService workers = Executors.newSingleThreadExecutor();
            Future<String> serverJob = workers.submit(() -> {
                try (SSLSocket peer = (SSLSocket) listener.accept()) {
                    peer.setEnabledProtocols(new String[]{"TLSv1.3"});
                    peer.setSoTimeout(10_000);
                    peer.startHandshake();
                    int value = peer.getInputStream().read();
                    peer.getOutputStream().write(value + 1);
                    peer.getOutputStream().flush();
                    return peer.getSession().getProtocol();
                }
            });

            try {
                // Socket TCP đi đến 127.0.0.1, nhưng danh tính TLS là localhost.
                try (Socket tcp = new Socket("127.0.0.1",
                        listener.getLocalPort());
                     SSLSocket tls = (SSLSocket) clientContext
                             .getSocketFactory()
                             .createSocket(tcp, "localhost",
                                     listener.getLocalPort(), true)) {
                    tls.setEnabledProtocols(new String[]{"TLSv1.3"});
                    tls.setSoTimeout(10_000);
                    SSLParameters parameters = tls.getSSLParameters();
                    parameters.setEndpointIdentificationAlgorithm("HTTPS");
                    tls.setSSLParameters(parameters);

                    tls.startHandshake();
                    tls.getOutputStream().write(41);
                    tls.getOutputStream().flush();
                    int response = tls.getInputStream().read();

                    System.out.println("client protocol: "
                            + tls.getSession().getProtocol());
                    System.out.println("response 42: " + (response == 42));
                }
                System.out.println("server protocol: "
                        + serverJob.get(10, TimeUnit.SECONDS));
            } finally {
                workers.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java JsseSslContextDemo server.p12 trust.p12");
        }
        String demoValue = System.getenv("JSSE_DEMO_PASSWORD");
        if (demoValue == null || demoValue.isEmpty()) {
            throw new IllegalArgumentException(
                    "Set JSSE_DEMO_PASSWORD for the local fixture");
        }
        char[] password = demoValue.toCharArray();
        try {
            KeyStore identity = loadPkcs12(Path.of(args[0]), password);
            KeyStore trustStore = loadPkcs12(Path.of(args[1]), password);

            System.out.println("identity key entry: "
                    + identity.isKeyEntry("service"));
            System.out.println("identity chain length: "
                    + identity.getCertificateChain("service").length);
            System.out.println("trusted CA entries: " + trustStore.size());

            SSLContext server = createServerContext(
                    identity, password, trustStore);
            SSLContext client = createClientContext(trustStore);
            exchangeOnce(server, client);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

**Mật khẩu demo:** phần code lấy password từ biến môi trường `JSSE_DEMO_PASSWORD`, không đặt secret trực tiếp trong Java source. Biến môi trường **không phải kho bí mật an toàn mặc định**: nó vẫn có thể bị lộ qua công cụ debug, process dump hoặc runtime tùy hệ điều hành. Bài chỉ dùng password mẫu trong môi trường local; sản phẩm dùng secret manager/credential provider phù hợp. `String demoValue` không được xóa khỏi Java heap bởi `Arrays.fill(char[])`, vì Java `String` immutable; đây là hạn chế của demo.

### 7.2. Biên dịch và chạy bằng Bash/Linux/macOS

Sau khi tạo fixture ở cùng thư mục với file Java:

```bash
javac -encoding UTF-8 JsseSslContextDemo.java
export JSSE_DEMO_PASSWORD=demo-changeit
java JsseSslContextDemo server.p12 trust.p12
unset JSSE_DEMO_PASSWORD
```

### 7.3. Biên dịch và chạy bằng PowerShell/Windows

```powershell
javac -encoding UTF-8 JsseSslContextDemo.java
$env:JSSE_DEMO_PASSWORD = "demo-changeit"
java JsseSslContextDemo server.p12 trust.p12
Remove-Item Env:JSSE_DEMO_PASSWORD
```

**Không chạy trên host public**: đây là loopback TLS test, không thực hiện authorization. Đừng commit `server.p12` hoặc `ca.p12` lên repository. Nếu runtime không hỗ trợ TLS 1.3, chương trình sẽ lỗi ở bước `setEnabledProtocols`/handshake; bài này yêu cầu **Java 17+ có provider hỗ trợ TLSv1.3**, không tự fallback sang TLS cũ.

### 7.4. Stdout kỳ vọng đã kiểm thử

```text
identity key entry: true
identity chain length: 2
trusted CA entries: 1
client protocol: TLSv1.3
response 42: true
server protocol: TLSv1.3
```

Mã được **biên dịch với `javac --release 17`** và chạy trên JDK tương thích: server chain có 2 certificates, truststore có 1 CA, client thực hiện handshake TLS 1.3 với endpoint identification `HTTPS`, và byte response bằng `42`. Đây là kết quả của fixture mới được tạo đúng các bước; nếu certificate hết hạn hoặc bị tạo khác cấu trúc, số lượng chain/điều kiện handshake có thể thay đổi.

### 7.5. Giải thích đoạn code trọng tâm

**`loadPkcs12`:** tách nạp file khỏi logic TLS, dùng `try-with-resources` để đóng stream, không dùng `FileInputStream` bị quên close. Nhận `char[]` password theo vai trò nạp kho. Dùng một password demo cho hai file không biến chúng thành cùng một loại kho.

**`createServerContext`:** dùng **server identity** để tạo key managers, dùng **truststore** để tạo trust managers. Trong one-way TLS, trust manager phía server được cài sẵn để chuẩn bị cho mTLS nhưng không bắt buộc được gọi khi server không yêu cầu client certificate.

**`createClientContext`:** truyền `null` cho `keyManagers` vì client **không có identity certificate** trong one-way TLS. Client vẫn **có trust manager** của CA demo để xác minh chain server.

**`SSLContext.getInstance("TLS")`:** chọn TLS provider; `setEnabledProtocols(new String[]{"TLSv1.3"})` trên socket giới hạn profile TLS cho demo. Production phải theo khả năng tương thích và chính sách, không mở TLS cũ để sửa lỗi thiếu tin cậy.

**Socket lớp ngoài và hostname:** client mở kết nối TCP tới `127.0.0.1`, sau đó bọc bằng `SSLSocketFactory.createSocket(tcp, "localhost", port, true)` để danh tính TLS mong muốn là `localhost`. Certificate có SAN DNS:localhost, và `setEndpointIdentificationAlgorithm("HTTPS")` yêu cầu xác minh tên này. Nếu bỏ tên đích hoặc bỏ kiểm tra endpoint ID trong một raw `SSLSocket` app, có thể chấp nhận certificate của host khác dù CA đáng tin.

**`startHandshake()`:** tại đây mới thực hiện handshake và certificate validation. Nếu chain không hợp lệ, CA không được tin hoặc SAN không khớp, handshake phải thất bại theo chính sách mặc định; không xử lý lỗi bằng trust-all.

**Đọc/ghi 41→42:** chỉ để chứng minh sau handshake có một kênh ứng dụng đã được bảo vệ bởi TLS. Không có logic kiểm tra quyền người dùng, chống replay cấp ứng dụng hoặc xác thực client trong ví dụ.

**Timeouts:** `setSoTimeout(10_000)` giới hạn hoạt động socket đọc/accept theo API; trong production còn cần connect timeout, handshake-timeout phù hợp, deadline tổng thể, giới hạn concurrency và xử lý exception/retry.

**`Arrays.fill`:** giảm thời gian tồn tại của mảng password tạm; không đảm bảo xóa hết bản sao password ở môi trường/heap, cũng không thay thế secret management.

## 8. Ba điểm bảo mật mà demo cố ý không bỏ qua

### 8.1. SSLContext chỉ chuẩn bị chính sách, không xác minh endpoint ngay lập tức

Nhiều người tạo `SSLContext` thành công rồi cho rằng certificate chain đã được kiểm tra. Thực tế:

```text
SSLContext.init(...)       => Factory/manager configuration accepted
SSLSocket.startHandshake  => Protocol negotiation + certificate validation
Application authorization => Quyết định user/service có được làm nghiệp vụ?
```

`SSLContext.init` không kết nối đến host nào nên không biết hostname thực tế cần xác minh. Nó cũng không tự ép TLS 1.3. **Sai CA, sai SAN hoặc sai key entry có thể chỉ lộ ra khi khởi tạo manager hoặc handshake**, không nhất thiết ngay tại `SSLContext.getInstance`.

### 8.2. Tập tin certificate chain không tự là truststore

Khi server gửi một chain [leaf, intermediate], client sẽ dùng nó làm **candidate path**, nhưng **root phải đã nằm trong trust policy của client**. Nếu client tự nhận một root do server cung cấp và nâng thành trust anchor, attacker có thể gửi một CA tự tạo rồi ký một leaf giả.

Tương tự, việc nhập **CA demo** ở mục 6 vào `trust.p12` chỉ có ý nghĩa trong sandbox. Đừng nhập CA này vào truststore thực tế của hệ thống học tập, website public hay ứng dụng khách hàng.

### 8.3. JSSE trust manager kiểm tra chain; hostname phải được xử lý phù hợp

Trust manager mặc định dựa trên chuẩn JSSE/PKIX, nhưng **hostname verification không phải lúc nào cũng tự bật khi sử dụng raw `SSLSocket` hoặc `SSLEngine`**. Bài đã bật `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` ở phía client trước handshake.

Nếu ứng dụng dùng HTTP client cấp cao, framework có thể đã thực hiện bước này; vẫn cần kiểm thử và **không vô hiệu hóa verifier** chỉ để tránh lỗi SAN.

## 9. Khi nào cần thêm client certificate cho mTLS?

Trong **mTLS**, server không chỉ xác minh user/password hoặc bearer token; nó yêu cầu client chứng minh sở hữu một private key có certificate chain được tin theo **client-CA policy**.

Bổ sung cần thiết:

1. Tạo **client key pair + client certificate chain**, với SAN/EKU phù hợp `clientAuth` theo chính sách.
2. Cấp **client identity keystore** cho client và gọi `KeyManagerFactory.init(clientIdentity, clientKeyPassword)`.
3. Cấp **CA phát hành client certificate** vào **server truststore**. Nếu CA server và CA client khác nhau, cần các truststore phù hợp hai phía.
4. Khởi tạo client context bằng **cả** `keyManagers` và `trustManagers`, server context cũng có cả hai.
5. Bật **`needClientAuth`** ở socket/server socket/SSL engine hoặc framework; nếu không bật, server có thể không yêu cầu certificate client dù đã cấu hình trust manager.

Fragment minh họa server:

```java
// Sau khi có serverContext đã cấu hình và SSLServerSocket đã tạo:
serverSocket.setNeedClientAuth(true);
```

Fragment minh họa client:

```java
KeyManagerFactory clientKeys = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
clientKeys.init(clientIdentityKeyStore, clientKeyPassword);

TrustManagerFactory serverCaTrust = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
serverCaTrust.init(trustStoreOfServerCAs);

SSLContext clientContext = SSLContext.getInstance("TLS");
clientContext.init(clientKeys.getKeyManagers(),
                   serverCaTrust.getTrustManagers(),
                   new SecureRandom());
```

Các đoạn này **không phải chương trình độc lập**; giả định đã có đúng keystore/truststore. **Đừng bật `needClientAuth(true)` vào demo one-way phía trên mà không chuẩn bị client identity**, vì server có thể từ chối client không có certificate, đó là hành vi đúng.

### 9.1. mTLS chỉ xác thực vật liệu khóa; quyền nghiệp vụ còn riêng

Ngay cả khi TLS báo client certificate hợp lệ, ứng dụng còn phải ánh xạ certificate sang identity được ủy quyền theo **SAN/subject/public key** và chính sách lifecycle/tenant. Một CA đáng tin có thể cấp nhiều certificate cho nhiều service hoặc người dùng; **không có nghĩa mọi certificate do CA đó ký đều có quyền gọi mọi API**.

Cần xem xét:

- `ExtendedKeyUsage clientAuth` khi yêu cầu;
- Chain đến đúng **client CA** và revocation/expiry policy;
- Danh tính service cụ thể (SPIFFE ID/SAN hoặc quy ước nội bộ có kiểm soát);
- Quyền endpoint/method, tenant và các ràng buộc ở tầng ứng dụng.

### 9.2. Khác biệt giữa `needClientAuth` và `wantClientAuth`

| Cấu hình | Ý nghĩa | Hệ quả |
| --- | --- | --- |
| `setNeedClientAuth(true)` | Bắt buộc có client authentication | Client không có certificate hợp lệ phải bị từ chối theo giao thức/chính sách |
| `setWantClientAuth(true)` | Muốn client authentication nếu có | Có thể cho phép client không trình bày certificate, không đủ cho yêu cầu bắt buộc |
| Không bật client auth | One-way TLS thường gặp | Server trình bày identity; client xác minh server |

Một số framework tạo lại `SSLParameters` hoặc quản lý handshake theo cách riêng; hãy xác minh các cài đặt có hiệu lực trong runtime thực tế, không chỉ nhìn config file.

## 10. Định dạng kho và chuỗi chứng thư khi tích hợp với Java

### 10.1. PKCS12/JKS/JCEKS/PKCS11

| Loại | Vai trò thường gặp | Lưu ý |
| --- | --- | --- |
| `PKCS12` | Identity/truststore dạng file, có thể chứa private key/certificates | Khả năng thuật toán PBE/entry-password khác nhau theo provider và công cụ |
| `JKS` | Keystore Java legacy | Không tự chọn JKS mới chỉ để có keypass riêng; cần xem mức bảo vệ/khả năng tương thích |
| `JCEKS` | Legacy store có hỗ trợ secret keys | Không phải câu trả lời mặc định cho TLS identity; cần policy bảo mật |
| `PKCS11` | KeyStore-like view của token/HSM | Private key có thể non-exportable; PIN/provider handles thay cho password file |
| `KeyStore.getDefaultType()` | Type mặc định của runtime | Có thể khác do security properties; xác định type rõ khi cần interoperability |

Nhiều hệ thống dùng certificate dưới PEM nhưng private key trong HSM: vẫn có thể tạo `KeyManager` qua provider phù hợp. **Không bắt buộc export private key ra PKCS12** để dùng JSSE nếu provider hỗ trợ private-key operations trong thiết bị.

### 10.2. Độ dài/thuật toán khóa không thay chuỗi tin cậy

Nếu leaf RSA-2048 có chain hợp lệ nhưng CA không được tin, TLS không tự chấp nhận chỉ vì RSA key dài 2048 bit. Nếu leaf dùng RSA-3072 nhưng SAN là `other.example` trong khi client kết nối `localhost`, endpoint identification vẫn phải từ chối. Tính đúng của TLS identity gồm **public/private key match, certificate chain, trust anchor, validity, key usage/EKU, thuật toán và tên endpoint**.

### 10.3. Không nạp nhầm file

`ca.p12` chứa private key CA dùng phát hành, **không phải** identity store của server. `trust.p12` chứa CA certificate, **không phải** keystore chứa server private key. Nếu chỉ nhìn tên file và nạp nhầm `ca.p12` vào server identity, ứng dụng có thể trình bày certificate không phù hợp hoặc vô tình cho code server quyền truy cập private key CA — một sự cố nghiêm trọng.

**Chỉ private key của service** được cấp cho service đó; root CA private key phải được giữ theo quy trình CA/HSM với quyền cực hạn chế.

## 11. Khởi tạo SSLContext trong thư viện HTTP/framework

### 11.1. Java `HttpClient` (Java 11+)

Với `java.net.http.HttpClient`, có thể chuyển SSLContext tùy chỉnh vào builder:

```java
// Fragment minh họa, không phải chương trình độc lập:
HttpClient client = HttpClient.newBuilder()
        .sslContext(clientContext)
        .build();
```

`clientContext` ở đây phải dùng trust managers mong muốn. `HttpClient` quản lý connection/hostname validation theo JSSE và hợp đồng API riêng; không bật “insecure hostname verifier” để bỏ qua lỗi chứng thư. Không lấy `serverContext` có private key CA test và dùng cho client production.

### 11.2. Spring Boot, Tomcat, Jetty và các framework khác

Framework thường có các trường cấu hình tương đương:

- Keystore path/type, **store password**, alias và **key password**;
- Truststore path/type/password;
- Client authentication mode;
- Protocol/cipher-suites policy;
- Certificate reload/rotation settings.

Tên thuộc tính và hành vi mặc định khác nhau theo **framework version**. Đừng copy một tập YAML bất kỳ rồi cho rằng mọi framework đều hiểu. Cách xác minh là chạy handshake thật, kiểm tra certificate chain, SAN, TLS version, client-auth policy và hành vi sau khi rotate.

### 11.3. Default SSLContext và system properties

Java có các system properties như `javax.net.ssl.keyStore`, `javax.net.ssl.keyStorePassword`, `javax.net.ssl.trustStore`, `javax.net.ssl.trustStorePassword` ảnh hưởng đến **một số default JSSE configurations**. Tuy nhiên:

- Một `SSLContext` tự khởi tạo qua `kmf/tmf` **không đương nhiên** sử dụng các system properties nếu bạn đã truyền explicit key/trust managers.
- `SSLContext.getDefault()` là context mặc định của tiến trình; sửa system properties trong runtime sau khi context/connection pool đã khởi tạo **không đảm bảo** mọi socket tự cập nhật.
- Dùng nhiều trust policies cho các tenant/service thì thường nên **tạo các context độc lập và quản lý lifecycle rõ**, tránh thay system properties global liên tục.

## 12. Chẩn đoán lỗi SSLContext, key manager và handshake

| Vị trí/lỗi | Nguyên nhân phổ biến | Cách kiểm tra |
| --- | --- | --- |
| `KeyStore.load` báo `IOException` | Sai storepass, file hỏng, format/PBE không tương thích | Type/provider, đường dẫn, storepass, backup |
| `KeyManagerFactory.init` ném `UnrecoverableKeyException` | Sai key password hoặc không đọc được entry | Alias, keypass, provider, key entry |
| `identity.isKeyEntry(alias) == false` | Alias sai hoặc chỉ là certificate entry | `keytool -list -v`, kiểm tra entry type |
| `getCertificateChain(alias) == null` | Không có chain phù hợp | Tái nhập leaf/intermediate đúng thứ tự, kiểm tra key match |
| `SSLContext.init` không tạo được manager | Không tương thích provider/algorithm, tham số không hợp lệ | JDK security providers, private key handle, key/trust manager type |
| `SSLHandshakeException: PKIX path building failed` | Không có đường tin cậy đến CA trong truststore, thiếu intermediate, ràng buộc PKIX khác | Truststore, CA approved, chain, EKU/validity, algorithm constraints |
| `SSLHandshakeException` với hostname/SAN mismatch | Certificate server không hợp tên/địa chỉ client kết nối | SAN DNS/IP, endpoint ID, cách tạo socket, SNI |
| Handshake không có certificate phù hợp | Server không có key entry hoặc không chọn được certificate/key type | `KeyManager`, alias, thuật toán TLS, certificate chain |
| mTLS báo thiếu client certificate | Client không gửi identity hoặc server cần clientAuth mà truststore không khớp | Client key manager, server trust CA và `needClientAuth` |
| `protocol_version` / `handshake_failure` | Không có TLS protocol/cipher suite trùng nhau, chính sách không phù hợp | EnabledProtocols, JDK version, crypto policy |
| `certificate_expired` | Certificate ngoài `notBefore/notAfter` | Kiểm tra đồng hồ UTC, phát hành lại bằng CA đúng |
| Truststore có CA nhưng vẫn từ chối | Sai SAN/EKU/algorithm/policy, chain sai, revocation | Đọc nguyên nhân PKIX và kiểm thử từng ràng buộc |
| Test demo báo `Connection refused` | Socket server chưa mở, bị chặn loopback/firewall hoặc port sai | Loopback support, port, timeout; không tắt TLS để sửa lỗi TCP |

### 12.1. Biết lỗi xuất hiện ở bước nào

Cách đọc log theo quá trình:

```text
1) KeyStore.load(identity)      -> Đọc file/mật khẩu kho
2) KeyManagerFactory.init(...)  -> Mở private key entries
3) TrustManagerFactory.init(...) -> Chuẩn bị trust anchors
4) SSLContext.init(...)         -> Ghép managers
5) SSLSocket.startHandshake()   -> Chọn giao thức, certificate chain,
                                   peer validation, key proof
6) Application request          -> Authorization và logic nghiệp vụ
```

Nếu dừng tại bước 1 hoặc 2, lỗi không nhất thiết liên quan certificate của remote peer. Nếu dừng tại bước 5, cần xét **trust path, hostname, protocol, key usage, algorithm constraints, client-auth và revocation policy**. Không chỉ thử thay một chuỗi password rồi coi đã sửa mọi vấn đề.

### 12.2. Debug TLS nhưng không tiết lộ secrets

JDK cung cấp debug log của JSSE, ví dụ property `javax.net.debug=ssl,handshake` trong môi trường test. Debug log có thể chứa **certificate details, hostnames, SNI và metadata kết nối** nên cần phân quyền và retention, không đẩy trực tiếp lên hệ thống log public. **Tuyệt đối không log private key bytes, mật khẩu kho/keypass hoặc secret TLS**.

Không bật log bí mật khóa phiên kiểu `SSLKEYLOGFILE` hoặc options tương đương trên production mà không có kiểm soát nghiêm ngặt; các tệp khóa phiên có thể giúp giải mã traffic TLS và phải được bảo vệ như secret nếu được dùng cho mục đích phân tích được ủy quyền.

### 12.3. Những kiểm thử âm nên có

- Thay truststore bằng một truststore không chứa demo CA: **handshake phải thất bại** vì không có trust anchor thích hợp.
- Dùng một hostname khác `localhost` khi endpoint identification vẫn bật: **phải bị từ chối** nếu SAN không bao gồm tên đó.
- Nhập một server certificate hết hạn hoặc không có EKU phù hợp: **bị từ chối** theo PKIX/JSSE policy.
- Dùng private-key password sai: khởi tạo `KeyManagerFactory` phải thất bại nếu entry protection yêu cầu password riêng.
- Bật `needClientAuth(true)` nhưng client không có identity: mTLS phải thất bại theo policy.
- Dùng TLS version/cipher suite không có điểm chung: handshake thất bại; không được fallback sang protocol cũ không an toàn chỉ để test chạy.

Các ca âm là **kỳ vọng bảo mật cần kiểm tra**, không phải stdout cố định của chương trình một chiều. Kiểu exception có thể khác theo provider/JDK.

## 13. Quản lý vòng đời SSLContext, chứng thư và CA

### 13.1. Khi private key hoặc certificate được rotate

Có thể có nhiều thay đổi độc lập:

1. **Đổi store password:** thay credential bảo vệ kho, không nhất thiết đổi private key/certificate.
2. **Đổi key password:** thay thông tin bảo vệ entry, không đổi vật liệu khóa nếu không tạo key mới.
3. **Gia hạn/đổi certificate:** cùng private key có thể nhận certificate mới theo chính sách, nhưng vẫn cần chain/SAN/EKU cập nhật.
4. **Rotate private key:** tạo keypair mới và certificate tương ứng; không dùng chain cũ không khớp.
5. **Rotate CA/trust anchors:** client/server truststores phải có kế hoạch chuyển tiếp đúng nguồn, không tự “trust mọi CA” để tránh downtime.

**`SSLContext` đã init không tự biết file PKCS12 trên disk đã thay đổi.** Một số framework có reload hỗ trợ, nhưng JSSE context tạo bằng code thông thường không phải live watcher mặc định. Cần build context mới với kho/cert mới, kiểm tra rồi chuyển traffic/connection pool theo cơ chế an toàn.

### 13.2. Hai giai đoạn thay CA

Ví dụ CA server đổi từ A sang B:

- Chuẩn bị: client truststore được cập nhật để **tin B** theo quy trình đã phê duyệt; có thể tạm tin A và B trong cửa sổ chuyển tiếp.
- Thay server identity bằng leaf+chain do B phát hành.
- Kiểm thử handshake và hostname với ứng dụng thật.
- Sau cửa sổ chuyển tiếp phù hợp: loại A khi không còn cần thiết, thu hẹp trust policy.

Không đơn giản thay CA bên server trước khi client biết CA B, vì handshake sẽ thất bại, và cũng không giữ trust anchors cũ vô hạn khi không còn được phép.

### 13.3. Private key bị lộ

Nếu raw private key server bị lộ, **thay mật khẩu `.p12` không làm khóa đó an toàn trở lại**. Phải rotate keypair/certificate, thu hồi chứng thư bị ảnh hưởng theo PKI, đánh giá dữ liệu/phiên kết nối và cập nhật server/client theo incident response. Private key CA bị lộ có phạm vi ảnh hưởng lớn hơn, có thể cần thay trust anchor và toàn bộ chuỗi cấp phát liên quan.

### 13.4. Revocation checking không tự bảo đảm theo mọi cấu hình

TLS dùng chain validation qua `TrustManager`/PKIX, nhưng việc **CRL/OCSP revocation checking** có được bật và hoạt động thế nào phụ thuộc **JDK/provider/configuration**. Đừng mặc định rằng vì đã có truststore và `SSLContext.init` nên mọi chứng thư thu hồi đều bị phát hiện ngay.

Nếu ứng dụng có yêu cầu revocation nghiêm, cấu hình PKIX revocation checker/OCSP/CRL và network/cache policy rõ ràng. Cân nhắc fail-closed/soft-fail theo mô hình rủi ro và kiểm thử với certificates thật sự bị thu hồi.

## 14. Những lỗi tư duy phổ biến

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “SSLContext chỉ cần private key.” | Thiếu chain identity và trust policy | Key manager từ private key + chain; trust manager từ CA được phê duyệt |
| “Đưa CA vào server identity keystore là client đã tin CA.” | Client có truststore độc lập | Cấp CA đúng cho client truststore |
| “Đưa leaf của server vào truststore mỗi lần kết nối.” | Tự động nâng dữ liệu ngoài thành tin cậy, dễ bị MITM | Tin CA/pin qua kênh được xác thực và policy |
| “`KeyStore.load` thành công là TLS đã sẵn sàng.” | Chưa lấy key, chưa handshake | Kiểm tra alias/chain/keypass và chạy TLS |
| “`storepass` luôn bằng `keypass`.” | Vai trò khác, tool/provider có giới hạn | Cấu hình đúng từng bước, ghi rõ khi dùng chung |
| “Chỉ cần `TrustManagerFactory` là server có danh tính.” | Trust manager xác minh peer, không chứng minh local identity | `KeyManagerFactory` và private key/certificate chain |
| “`KeyManagerFactory` xác minh CA của server remote.” | Key manager quản local identity | Client trust manager xác minh remote chain |
| “`SSLContext.getInstance("TLS")` luôn ép TLS 1.3.” | Chỉ chọn TLS context/provider | Chọn protocol policy trên socket/engine |
| “Raw `SSLSocket` luôn tự kiểm tra hostname.” | Endpoint identification có thể phải bật tường minh | `setEndpointIdentificationAlgorithm("HTTPS")` |
| “Certificate CN đúng là đủ, không cần SAN.” | Quy tắc hiện đại dùng SAN | Cấp certificate có SAN DNS/IP đúng |
| “Trust-all manager để sửa `PKIX path building failed`.” | Vô hiệu hóa xác thực, dễ MITM | Sửa truststore/chain/hostname đúng nguồn |
| “mTLS chỉ cần server có truststore.” | Server có thể không yêu cầu client certificate | Bật `needClientAuth` và cấp client identity |
| “Mọi CA ký client cert đều cho phép gọi mọi API.” | Authentication khác authorization | Ánh xạ SAN/identity và quyền cụ thể |
| “Sau rotate file `.p12`, SSLContext cũ tự đổi.” | Context/connection pool không tự reload | Rebuild và swap context an toàn |
| “Nếu TLS hoạt động thì CA root private key phải ở server.” | Server chỉ cần private key leaf | CA private key nằm ở CA/HSM, truststore chỉ cần public cert |
| “Tin tất cả CAs sẽ tránh outage.” | Mở rộng trust ngoài yêu cầu | Quản trị anchors theo scope và chính sách |

## 15. Checklist trước khi triển khai SSLContext

1. **Danh tính:** private key service có được cấp và bảo vệ đúng không? Leaf certificate có public key khớp, SAN DNS/IP đúng?
2. **Chain:** `getCertificateChain(alias)` có leaf rồi intermediate đúng thứ tự, không thiếu issuer cần thiết? Chứng thư còn hiệu lực và đủ KeyUsage/EKU?
3. **Store/key password:** `KeyStore.load` dùng storepass, `KeyManagerFactory.init` dùng keypass phù hợp provider? Không hardcode/log?
4. **CA trust:** tập CA đã được xác minh nguồn, scope hợp lý, không tự import certificates từ peer?
5. **Factory:** dùng `KeyManagerFactory` cho local identity, `TrustManagerFactory` cho peer trust, ghép đúng vào `SSLContext.init`?
6. **TLS protocol:** chỉ bật TLS version/cipher suites được policy phê duyệt, không cho phép fallback không an toàn?
7. **Endpoint ID:** với raw JSSE client, đã cấu hình hostname verification đúng tên đích và kiểm tra SAN chưa?
8. **mTLS:** nếu cần, client có key manager, server có trust manager đúng client CA và bật `needClientAuth(true)` chưa?
9. **Authorization:** có kiểm tra service/user identity và quyền nghiệp vụ sau TLS handshake, không coi một CA hợp lệ là toàn quyền?
10. **Thử nghiệm:** handshake thực giữa client/server đã thành công; các ca thiếu CA, sai SAN, sai keypass, thiếu client cert có thất bại đúng cách?
11. **Vận hành:** rotation, reload context, trust anchor overlap, backup/restore, revocation policy và audit được kiểm tra?
12. **Bảo vệ môi trường:** không lưu private key/`.p12` có bí mật vào source control, không đưa CA private key vào runtime và không log TLS secrets?

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Muốn dựng HTTPS server từ `server.p12`, gọi `KeyStore.load` bằng storepass là đã đủ chưa?  
**Trả lời:** **Chưa.** Cần key manager recover private key bằng keypass, certificate chain hợp lệ, `SSLContext.init`, cấu hình socket và handshake thật.

**Câu 2.** Server đã có chain [leaf, intermediate, root]. Client không tin root, có thể tin server chỉ vì root được gửi cùng chain không?  
**Trả lời:** **Không.** Root trust anchor phải được client cấp phát đáng tin **từ trước**, không tự nâng root do server gửi thành CA được tin.

**Câu 3.** `KeyManagerFactory` và `TrustManagerFactory` khác nhau thế nào?  
**Trả lời:** `KeyManagerFactory` chuẩn bị **private key + certificate chain local identity**; `TrustManagerFactory` chuẩn bị bộ **quy tắc/tập CA** để xác minh chứng thư của **peer**.

**Câu 4.** TLS client không dùng client certificate thì có thể gọi `SSLContext.init(null, tm, random)` không?  
**Trả lời:** **Có.** `null` key managers nghĩa không cung cấp local client identity ở cấu hình này; trust managers vẫn kiểm tra server certificate.

**Câu 5.** TLS server đã cài trust manager của client CA. Đã tự thành mTLS chưa?  
**Trả lời:** **Chưa.** Server còn phải yêu cầu client authentication (`needClientAuth`), client có key manager đúng và phải đáp ứng certificate policy.

**Câu 6.** Một server certificate có CA chain hợp lệ nhưng SAN chỉ là `wrong.example`, client đang đến `localhost`. Nên xử lý sao?  
**Trả lời:** **Từ chối** khi hostname verification bật đúng; chữ ký CA hợp lệ không thay thế kiểm tra danh tính endpoint.

**Câu 7.** Chuyển từ server certificate do CA A ký sang CA B ký mà không cập nhật client truststore, chuyện gì có thể xảy ra?  
**Trả lời:** Handshake có thể thất bại vì không có trust anchor B. Cần kế hoạch overlap và rotation tin cậy giữa hai phía.

**Câu 8.** Nếu biết private key của demo CA, có nên nhập nó vào `trust.p12` của client không?  
**Trả lời:** **Không.** Truststore chỉ cần **public CA certificate**. CA private key phải được bảo vệ bởi hệ thống CA.

**Câu 9.** `SSLContext.getInstance("TLS")` có đảm bảo kết nối luôn dùng TLS 1.3 và xác minh hostname chưa?  
**Trả lời:** **Không.** Cần cấu hình protocol/SSLParameters hoặc dùng framework có default được kiểm tra. Demo chủ động bật TLS 1.3 và endpoint identification.

**Câu 10.** Sau khi thay file `server.p12` trên disk, một `SSLContext` đã init tự dùng certificate mới trong mọi kết nối không?  
**Trả lời:** **Không thể giả định.** Cần lifecycle/reload context và connection pools theo framework/provider.

**Câu 11.** Nếu certificate server hết hạn, có thể sửa bằng cách cho `TrustManager` bỏ qua ngày hết hạn không?  
**Trả lời:** **Không.** Phải phát hành/rotate certificate hợp lệ, kiểm tra đồng hồ và chain; không bỏ kiểm tra bảo mật.

**Câu 12.** Trong demo, `server.p12` có chain length 2 và `trust.p12` có một CA. Vì sao kết quả không có nghĩa đây là bộ certificate production an toàn?  
**Trả lời:** CA được tự tạo trong sandbox, khóa/mật khẩu là fixture demo, scope chỉ localhost và thời hạn ngắn. Production cần PKI/trust distribution, secret management, authorization, revocation, vận hành và kiểm thử phù hợp.

### Tài liệu tham khảo

- [Java SE 21 — SSLContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLContext.html): `getInstance`, `init` và socket factories.
- [Java SE 21 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): nạp local identities/khóa riêng.
- [Java SE 21 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): tạo trust managers từ KeyStore.
- [Java SE 21 — SSLParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification và client-auth.
- [Java SE 21 — Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TLS handshake, managers, truststores, SSLContext.
- [Java SE 21 — keytool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): tạo keypair, CSR, ký certificate, nhập chain, xuất/import CA.
- [RFC 5280 — X.509 Public Key Infrastructure](https://www.rfc-editor.org/rfc/rfc5280): certificate path validation, key usage và X.509 policy.

### Ghi nhớ

**`SSLContext` được cấu hình bằng hai hướng độc lập: `KeyManagerFactory` cho private key + certificate chain của chính ứng dụng, `TrustManagerFactory` cho các CA mà ứng dụng đã tin để xác minh peer.** Một chuỗi certificate gửi từ server không tự tạo trust anchor; một truststore không cung cấp server private key; tạo `SSLContext` không thay thế handshake, hostname verification hay authorization. Hãy kiểm thử luồng **nạp kho → phục hồi khóa → TLS handshake → endpoint identity → nghiệp vụ** bằng certificate và CA đúng chính sách, đồng thời bảo vệ key, password và cơ chế rotation.
