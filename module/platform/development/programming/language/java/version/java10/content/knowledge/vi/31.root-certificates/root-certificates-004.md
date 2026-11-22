# Phân biệt kho khóa riêng với kho chứng thư tin cậy — chứng thư gốc, Java KeyStore và TLS

## 1. Câu hỏi cốt lõi

Khi cấu hình HTTPS, TLS hoặc mutual TLS (mTLS) cho một ứng dụng Java, ta thường gặp hai tên:

- **Keystore / identity store:** nơi ứng dụng truy cập **khóa riêng** cùng **chuỗi chứng thư xác thực danh tính của chính mình**.
- **Truststore / trust store:** nơi ứng dụng tìm những **chứng thư hoặc trust anchors** mà nó tin cậy để **xác minh danh tính của bên kết nối tới**.

Đây là **sự phân chia theo vai trò bảo mật**, không nhất thiết là hai kiểu file khác nhau. Cả hai thường là **`java.security.KeyStore`** ở định dạng **PKCS#12**. Một file kỹ thuật vẫn có thể chứa đồng thời key entries và trusted certificate entries; Java không tự gán vai trò “kho danh tính” chỉ từ phần mở rộng `.p12`.

Ngữ cảnh của bài là **“Chứng thư gốc”** trong Java 10, với đề mục **“Phân biệt kho khóa riêng với kho chứng thư tin cậy”**. Một mốc liên quan trong **Java 10 — JEP 319: Root Certificates** là OpenJDK được cung cấp một tập chứng thư CA gốc mặc định trong `cacerts`. Tuy nhiên, **các trust anchors thực tế thay đổi theo JDK vendor, bản cập nhật và chính sách quản trị**; không lấy danh sách CA của Java 10 làm danh sách cố định cho Java hiện đại.

**Quy tắc dễ nhớ:**

> **Keystore danh tính:** “Tôi là ai? Tôi có thể chứng minh mình sở hữu private key tương ứng với chứng thư nào?”  
> **Truststore:** “Tôi tin CA/chứng thư nào để xác minh chứng thư của bên kia?”

### Mục tiêu sau bài học

- Phân biệt **private key**, **public key**, **X.509 certificate**, **root CA**, **intermediate CA** và **server/client leaf certificate**.
- Phân biệt `KeyStore.PrivateKeyEntry`, `KeyStore.TrustedCertificateEntry` và vai trò `KeyManager` / `TrustManager`.
- Hiểu **certificate chain** được bên trình danh tính sử dụng và **trust anchor** được bên xác minh chọn.
- Nắm rõ quan hệ giữa kho chứa private key, kho chứng thư gốc và **`cacerts`** mặc định của JDK.
- Biết **PKCS12** là định dạng mặc định và được khuyến nghị từ **JDK 9**, không tiếp tục giới thiệu JKS như lựa chọn mới mặc định.
- Hiểu cấu hình JSSE qua `javax.net.ssl.keyStore`, `javax.net.ssl.trustStore` và các factory tương ứng.
- Hiểu HTTPS thông thường chỉ xác thực server; **mTLS** có cả hai phía trình chứng thư.
- Biết phân biệt **tin CA** với **tin trực tiếp một leaf certificate** và những rủi ro mở rộng trust quá mức.
- Thực hành `keytool` tạo root CA thử nghiệm, sinh server key, ký chứng thư, tạo hai PKCS12 stores khác vai trò.
- Chạy chương trình **Java 17+** thực sự bắt tay TLS trên loopback, bật kiểm tra hostname và in stdout chính xác.
- Biết chẩn đoán `PKIX path building failed`, `UnrecoverableKeyException`, `No subject alternative names` và lỗi cấu hình TLS.
- Quản lý mật khẩu, private key, CA trust, chứng thư hết hạn, khôi phục và rotation theo thực tiễn hiện hành.

**Special Note:** Chỉ sử dụng các kiến thức còn áp dụng trên Java/JSSE hiện đại. Các chuẩn giao thức TLS cũ, thuật toán yếu và thiết lập “trust-all certificates” **không** được xem là cách sửa lỗi production.

## 2. Các thành phần của PKI cần hiểu trước

### 2.1. Khóa riêng và khóa công khai

Trong một cặp khóa bất đối xứng:

- **Private key:** dữ liệu bí mật, cho phép tạo chữ ký hoặc thực hiện các thao tác mật mã theo thuật toán. Phải được bảo vệ.
- **Public key:** khóa có thể được chia sẻ để kiểm tra chữ ký hoặc phục vụ giao thức phù hợp; được nhúng trong chứng thư X.509.

Nếu bạn có một private key RSA và một certificate, **không phải cứ bỏ hai thứ vào cùng file là chúng trở thành một cặp hợp lệ**. Public key trong certificate phải tương ứng với private key và mục đích sử dụng chứng thư phải phù hợp.

**Không bao giờ** xuất private key rồi đưa vào truststore chỉ để “client tin server”. Xác minh server không đòi client sở hữu private key của server hoặc của CA đã ký server.

### 2.2. X.509 certificate là gì?

Chứng thư X.509 có thể chứa:

- **Subject:** thông tin danh tính được chứng nhận.
- **Issuer:** đơn vị phát hành/ký chứng thư.
- **Subject public key:** public key của chủ thể.
- **Validity:** `NotBefore` và `NotAfter`.
- **Signature:** chữ ký của issuer hoặc tự ký trong một số trường hợp.
- **Extensions:** như `BasicConstraints`, `KeyUsage`, `ExtendedKeyUsage`, `SubjectAlternativeName`, certificate policies và những ràng buộc khác.

**Chứng thư không chứa private key**. Một file `server.crt` hoặc `root-ca.cer` thông thường chứa dữ liệu công khai của chứng thư, không phải private key tương ứng.

### 2.3. Chứng thư gốc, chứng thư trung gian và chứng thư cuối

Một chain TLS phổ biến:

~~~text
ROOT CA (chứng thư gốc)
  Subject = Demo Root CA
  được ứng dụng cấu hình làm trust anchor
          |
          | ký hoặc chứng thực CA trung gian
          v
INTERMEDIATE CA
  được phép ký các leaf certificates theo constraints
          |
          | ký chứng thư cuối
          v
END-ENTITY / LEAF CERTIFICATE
  SAN = DNS:api.example.com
  EKU = serverAuth
  Public key của máy chủ
          |
          | Private key khớp public key, chỉ server sở hữu
          v
MÁY CHỦ TLS
~~~

**Root CA certificate** thường là self-signed, nhưng **“self-signed” không tự động có nghĩa “đáng tin”**. Niềm tin xuất phát từ việc người dùng/ứng dụng/nhà quản trị **chấp nhận nó làm trust anchor**, sau khi kiểm tra nguồn gốc và chính sách.

**Intermediate CA** thường không tự động được tin chỉ vì có chữ CA trong tên. Nó được xác nhận thông qua đường chứng thư hợp lệ tới một trust anchor, hoặc được một hệ thống cấu hình tin trực tiếp theo chính sách riêng.

**Leaf certificate** là chứng thư của endpoint đang trình danh tính. Server cần có **private key tương ứng** để chứng minh quyền sử dụng danh tính ấy trong TLS.

### 2.4. Trust anchor không bắt buộc là một self-signed certificate

Java cung cấp lớp **`java.security.cert.TrustAnchor`**, có thể biểu diễn CA đáng tin bằng:

- Một chứng thư X.509 đã được chấp nhận, hoặc
- CA name và public key cùng những constraints liên quan.

Do đó **trust anchor là quyết định cấu hình tin cậy**, không phải phép so sánh xem cert có self-signed không. Một kho truststore có thể chứa **trusted certificates không phải root CA** theo yêu cầu hệ thống; việc đó làm thay đổi phạm vi tin cậy và cần thận trọng.

## 3. So sánh nhanh keystore danh tính và truststore

| Tiêu chí | Keystore danh tính | Truststore |
| --- | --- | --- |
| Mục đích chính | Cung cấp **danh tính và private key của chính JVM** để trình cho peer. | Cung cấp **trust anchors/chứng thư đã tin** để xác minh peer. |
| Dữ liệu cốt lõi | **Private key + certificate chain** tương ứng. | **Public X.509 certificates**, thường là root CA. |
| Kiểu entry điển hình | `PrivateKeyEntry`. | `TrustedCertificateEntry`. |
| Java API thường dùng | `KeyManagerFactory` → `KeyManager[]`. | `TrustManagerFactory` → `TrustManager[]`. |
| Khi phía nào dùng? | Server thông thường; client nếu mTLS/client authentication. | Client khi xác minh server; server nếu mTLS. |
| Có cần private key của CA? | **Không** cho server bình thường: chỉ cần private key của server. | **Không**: chỉ cần root CA **certificate/public key**. |
| Có được gửi qua TLS? | **Certificate chain** có thể được gửi; private key **không được gửi**. | **Không gửi cả truststore** tới peer. |
| Quyền truy cập | Rất nhạy cảm: private key phải bảo vệ bằng mật khẩu, file permissions, HSM khi cần. | Không chứa private key theo cấu hình thường gặp nhưng sửa trust anchors có thể gây nguy cơ giả mạo. |
| File format hay dùng | `.p12` / `PKCS12`. | `.p12` / `PKCS12`, hoặc kho `cacerts` của JDK. |
| Tên file | `server-identity.p12`, `client-identity.p12`... | `client-trust.p12`, `server-trust.p12`... |

**Ngoại lệ quan trọng:** `KeyStore` là API lưu **nhiều loại entry**, không có lớp Java riêng `TrustStore`. Một identity store vẫn có thể giữ thêm một `TrustedCertificateEntry` để xây certificate chain; một file có đuôi `.p12` không bảo đảm chỉ chứa keys hay chỉ chứa trusted certs.

Trong bài lab, `server-identity.p12` có một `PrivateKeyEntry` và một root certificate public entry để hỗ trợ chain building. `client-trust.p12` chỉ có root certificate, **không có private key**. Chính vai trò mỗi store trong `KeyManagerFactory` hoặc `TrustManagerFactory` mới quyết định nó được dùng làm gì.

## 4. Java KeyStore: mô hình các loại entry

API chính là **`java.security.KeyStore`**. Những entry liên quan:

### 4.1. `KeyStore.PrivateKeyEntry`

Chứa **`PrivateKey` và `Certificate[]` chain** tương ứng, với private key là thông tin bí mật. Trong TLS, `KeyManager` có thể chọn một alias thích hợp rồi dùng private key khi handshake cần chứng minh danh tính.

Ví dụ alias:

~~~text
Alias name: server
Entry type: PrivateKeyEntry
Certificate chain length: 2
~~~

Chain có **2** phần tử trong bài lab vì endpoint certificate được ký trực tiếp bởi root CA thử nghiệm. Trong hạ tầng thật, chain thường có **leaf + một hoặc nhiều intermediate CA**, và root không nhất thiết được gửi kèm handshake.

Lưu ý: một private key entry không nhất thiết dùng cho TLS server; nó có thể dùng ký tài liệu, client authentication hoặc mục đích khác, tùy `KeyUsage`/`ExtendedKeyUsage`/ứng dụng.

### 4.2. `KeyStore.TrustedCertificateEntry`

Chứa **một certificate công khai đã được nhập vào truststore như một chứng thư đáng tin**:

~~~text
Alias name: demo-root
Entry type: trustedCertEntry
~~~

Entry này **không chứa private key**. Khi Java xây đường chứng thư theo PKIX, các chứng thư tin cậy có thể được sử dụng như anchors theo cấu hình trust manager/validator.

Không nhầm **trustedCertEntry** với **PrivateKeyEntry có certificate chain**: cả hai đều có chứng thư, nhưng chỉ một bên giữ private key.

### 4.3. `KeyStore.SecretKeyEntry`

`KeyStore` cũng có thể chứa khóa đối xứng trong `SecretKeyEntry`. Kiểu này hữu ích cho một số bài toán mật mã, nhưng **không phải** thứ mà TLS certificate-based `X509KeyManager` cần để trình một server X.509 certificate.

### 4.4. Hai phương thức quan sát an toàn

~~~java
KeyStore store = KeyStore.getInstance("PKCS12");
// Sau khi load đúng file và password:
boolean identityEntry = store.entryInstanceOf(
        "server", KeyStore.PrivateKeyEntry.class);
boolean trustedCertificate = store.entryInstanceOf(
        "demo-root", KeyStore.TrustedCertificateEntry.class);
~~~

Đây là **mảnh mã minh họa**, chưa đủ một chương trình độc lập vì biến `store` cần `load` và exception handling. Phần sau có chương trình Java 17+ đầy đủ, đã chạy.

Các phương thức khác:

- `isKeyEntry(alias)`: alias có key entry.
- `isCertificateEntry(alias)`: alias có trusted certificate entry.
- `getCertificateChain(alias)`: chuỗi chứng thư của key entry khi có.
- `getCertificate(alias)`: chứng thư liên quan alias theo loại entry.
- `getEntry(alias, protection)`: lấy entry với cơ chế bảo vệ thích hợp nếu ứng dụng thật cần truy cập.

**Không in `PrivateKey.getEncoded()`, không đưa private key vào log và không gửi alias/filename bất cẩn nếu chúng chứa thông tin nhạy cảm.**

## 5. TLS 1 chiều: server và client dùng hai vai trò khác nhau

Kịch bản HTTPS phổ biến:

~~~text
         HTTPS CLIENT                              HTTPS SERVER
   +-----------------------+                 +-------------------------+
   | client-trust.p12      |                 | server-identity.p12     |
   | Root CA public cert   |                 | Server private key      |
   | (TrustManager)        |                 | Server cert + chain     |
   +-----------+-----------+                 +------------+------------+
               |                                          |
               |  ClientHello                         ServerHello / Certificate
               |<-----------------------------------------|
               |         server certificate chain          |
               |                                          |
               |  TrustManager verifies path and policy   |
               |  HTTPS hostname verification via SAN    |
               |                                          |
               |  TLS key agreement / handshake completes |
               +------------------------------------------+
~~~

Trong kịch bản này:

1. **Server** cần credentials: private key và certificate chain phù hợp.
2. **Client** cần tập trust anchors để xác minh server.
3. Server **không gửi private key**; nó chứng minh quyền sở hữu bằng các thao tác mật mã trong handshake.
4. Client **không gửi truststore**; nó sử dụng truststore nội bộ.
5. HTTPS còn cần **hostname verification**, thường dựa vào Subject Alternative Name (SAN), bên cạnh certificate chain validation.
6. TLS handshake dùng những cơ chế hiện đại được JDK cho phép; bài không khuyên bật lại các giao thức hoặc thuật toán đã bị vô hiệu hóa.

**Hệ quả:** Cài root certificate công khai vào client truststore có thể giúp client tin **server certificate do CA đó cấp**, nếu chuỗi chứng thư và chính sách xác minh hợp lệ. **Không cần** sao chép `server-identity.p12` có private key từ server sang client.

### 5.1. Vì sao truststore **không** thay thế kiểm tra hostname?

Giả sử một server trình chứng thư hợp lệ do CA đáng tin ký, nhưng SAN của nó là `api.other.example` trong khi client kết nối `payments.example`. **Tin CA không có nghĩa tên máy chủ khớp**.

Trong Java, `X509ExtendedTrustManager` và các cơ chế HTTPS/JSSE có thể thực hiện kiểm tra danh tính endpoint. Với `SSLSocket` tự tạo, có thể cấu hình:

~~~java
SSLParameters p = socket.getSSLParameters();
p.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(p);
socket.startHandshake();
~~~

Đây là **mảnh mã minh họa**, biến `socket` phải là `SSLSocket` đã được thiết lập. Bài lab bên dưới áp dụng cách này trên socket thật. **Không** bỏ qua hostname verification khi hệ thống báo lỗi tên.

### 5.2. Có phải mọi TLS server đều gửi root CA certificate?

**Không.** Server thường gửi **leaf + intermediate certificates** cần thiết để client xây đường tin cậy; root CA thường đã nằm trong truststore của client. Server có thể gửi hoặc bỏ root tùy cấu hình, nhưng điều đó **không làm root trở thành đáng tin** nếu client chưa chọn nó làm trust anchor.

Đừng lấy danh sách certificate server gửi rồi **tự động import tất cả** vào truststore. Phải xác minh nguồn gốc và phạm vi CA cần tin trước.

## 6. Mutual TLS (mTLS): mỗi bên vừa trình danh tính vừa xác minh peer

Với **mTLS**, hai bên cần cả hai vai trò:

| Bên | Identity keystore | Truststore |
| --- | --- | --- |
| **Server** | Private key + certificate chain của server. | Root/intermediate trust anchors để xác minh **client certificate**. |
| **Client** | Private key + certificate chain của client. | Root/intermediate trust anchors để xác minh **server certificate**. |

Sơ đồ:

~~~text
CLIENT                                          SERVER
  client identity key + chain     ---->        server trust manager
  client trust manager            <----        server identity key + chain
       |                                           |
       +-------- TLS mutual authentication --------+
~~~

Trong JSSE:

- Server thường gọi `SSLServerSocket.setNeedClientAuth(true)` hoặc cấu hình tương đương trên `SSLEngine`/framework.
- Client cần `KeyManager` có client identity phù hợp nếu server yêu cầu certificate.
- Server cần `TrustManager` có tập trust anchors chấp nhận client CA.
- Cả hai phía cần kiểm tra đúng **certificate usage**, thời hạn, chính sách và danh tính theo yêu cầu nghiệp vụ.
- Client vẫn phải xác minh server như HTTPS bình thường.

**Không nhầm:** Khi không bật client authentication, client không nhất thiết phải có private-key keystore. Nếu bật mTLS, việc chỉ có truststore **không đủ** để client chứng minh danh tính của mình.

## 7. `KeyManagerFactory` và `TrustManagerFactory` trong JSSE

Java Secure Socket Extension (JSSE) phân tách trách nhiệm bằng hai loại manager:

| API | Nhiệm vụ | Nguồn dữ liệu thường gặp |
| --- | --- | --- |
| **`KeyManagerFactory`** | Tạo `KeyManager` để chọn **private key và certificate chain của chính phía chạy**. | Identity keystore. |
| **`TrustManagerFactory`** | Tạo `TrustManager` để quyết định **có chấp nhận chứng thư bên kia không**. | Truststore. |
| **`SSLContext`** | Dùng managers để tạo socket/engine và thực hiện TLS. | `SSLContext.init(keyManagers, trustManagers, random)`. |
| **`X509ExtendedKeyManager`** | Có thể lựa chọn danh tính theo connection/SNI/signature algorithms. | Key entries phù hợp. |
| **`X509ExtendedTrustManager`** | Có thể xác minh certificate chain trong ngữ cảnh socket/engine và endpoint. | Trust anchors cùng policies. |

Mô hình:

~~~java
KeyManagerFactory kmf =
        KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identityStore, identityKeyPassword);

TrustManagerFactory tmf =
        TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

SSLContext context = SSLContext.getInstance("TLS");
context.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);
~~~

Đây là **mẫu cấu hình**, chưa bao gồm khởi tạo `identityStore`, `trustStore` và `identityKeyPassword`. Phần lab dùng API đầy đủ.

### 7.1. Cấu hình client HTTPS thông thường

Một client chỉ cần xác minh server và không trình client certificate có thể khởi tạo:

~~~java
SSLContext clientContext = SSLContext.getInstance("TLS");
clientContext.init(null, tmf.getTrustManagers(), null);
~~~

Trong ngữ cảnh này, `null` ở vị trí **key managers** nghĩa là không cung cấp các credentials cá nhân qua array đó; **không có nghĩa tắt xác thực server**. Trust managers vẫn làm việc.

### 7.2. Cấu hình server thông thường

Một server HTTPS không yêu cầu client authentication có thể khởi tạo:

~~~java
SSLContext serverContext = SSLContext.getInstance("TLS");
serverContext.init(kmf.getKeyManagers(), null, null);
~~~

Ở đây server có identity key managers; trust manager mặc định có thể được provider chọn, nhưng **không được coi cách gọi này là bật mTLS**. Chỉ khi cấu hình server yêu cầu client auth thì client certificate mới cần được trình và kiểm tra theo quy trình đó.

### 7.3. Không viết TrustManager chấp nhận tất cả chứng thư

Một số ví dụ cũ vô hiệu hóa `checkServerTrusted` và chấp nhận tất cả chứng thư chỉ để “hết PKIX error”. Đây là **lỗi bảo mật**, vì phá vỡ xác thực server và tạo cơ hội man-in-the-middle.

Thực hành đúng là:

1. Xác định chain mà server trình.
2. Kiểm tra chứng thư hợp lệ, SAN, thời hạn, thuật toán và issuer.
3. Xác minh CA public certificate được phép tin.
4. Đưa trust anchor **đúng, đã kiểm chứng** vào truststore hoặc sửa cấu hình PKI.
5. Không bỏ qua hostname validation để làm giao thức “chạy được”.

## 8. Định dạng: PKCS12 và JKS **không phải** tên hai vai trò

Từ **JDK 9**, định dạng **`PKCS12`** là default keystore type của Java/JDK. Oracle Java SE 25 tiếp tục khuyến nghị PKCS12. Nó có thể chứa private keys, certificates và những dạng secret entries mà provider hỗ trợ.

`JKS` là định dạng riêng của Java đã tồn tại từ lâu. Các hệ thống cũ có thể vẫn dùng nó, nhưng không nên **lựa chọn JKS chỉ vì ví dụ Java 8** khi tạo keystore mới.

| Khái niệm | Ví dụ | Cần nhớ |
| --- | --- | --- |
| **Store role** | Identity keystore, truststore. | Xác định **dữ liệu và mục đích sử dụng**. |
| **Store format** | PKCS12, JKS, PKCS11 (provider-backed). | Xác định **cách lưu và truy cập keys/certs**. |
| **File extension** | `.p12`, `.pfx`, `.jks`, `cacerts`. | Chỉ là cách đặt tên; không chắc phản ánh format thực. |
| **Entry type** | PrivateKeyEntry, TrustedCertificateEntry. | Cần kiểm tra bằng `keytool -list -v` hoặc Java `KeyStore` API. |
| **Trust policy** | Root CA nào được tin, hostname nào được chấp nhận. | Không suy ra từ đuôi file. |

### 8.1. Vì sao không kết luận `.jks` có private key còn `.p12` là truststore?

Cả hai định dạng có thể chứa nhiều kiểu entry theo provider. Một số file có đuôi `.jks` thực tế vẫn là PKCS12 do hệ thống đặt tên không chuẩn.

Khi chẩn đoán, dùng:

~~~bash
keytool -list -v -storetype PKCS12 -keystore server-identity.p12
~~~

Công cụ có thể yêu cầu password. Đừng giả định extension là hợp đồng. **Không in nội dung private key** trong issue; `keytool -list` chủ yếu dùng để quan sát entry types, aliases và certificate metadata.

### 8.2. HSM/PKCS11 vẫn phù hợp hiện nay

Trong môi trường có HSM hoặc smartcard, private key có thể được giữ trong **cryptographic token**, và `KeyStore` truy cập thông qua **provider PKCS11** thay vì một file `.p12` thông thường.

Do đó định nghĩa “keystore nhất thiết là file trên đĩa” là quá hẹp. Vai trò vẫn là **cung cấp key material và identity chain**; cách lưu private key phụ thuộc threat model, provider và khả năng của hệ thống.

## 9. Root certificates mặc định của JDK: JEP 319, `cacerts` và `jssecacerts`

### 9.1. Java 10 — JEP 319

**JEP 319 — Root Certificates** bổ sung bộ root CA certificates mặc định cho OpenJDK distributions nhằm giúp Java TLS clients có thể xác minh chuỗi chứng thư của các dịch vụ công khai khi không cung cấp truststore riêng.

Nhưng:

- **JDK 10 không tạo root CA private keys cho ứng dụng.**
- `cacerts` là **kho chứng thư tin cậy**, không phải kho private key của server.
- Danh sách root CA thay đổi theo bản JDK, vendor, update/security policies và nhu cầu tuân thủ.
- Không import một certificate không đáng tin vào `cacerts` chỉ vì gặp lỗi TLS.

### 9.2. Nơi JSSE tìm truststore mặc định

Theo tài liệu **SunJSSE** trong Oracle Java SE 25, khi sử dụng trust manager mặc định và **không** chỉ định `javax.net.ssl.trustStore`:

1. JSSE có thể tìm `java.home/lib/security/jssecacerts` nếu file này tồn tại.
2. Nếu không có, JSSE tìm `java.home/lib/security/cacerts`.
3. Khi không có trust material phù hợp, hành vi mặc định cần được hiểu theo provider; không tự giả định mọi kết nối server certificate đều được chấp nhận.

`jssecacerts` cho phép cấu hình kho tin cậy dành riêng cho JSSE; `cacerts` là kho root certificates thường được phân phối cùng JDK.

Để liệt kê an toàn kho CA do JDK cung cấp:

~~~bash
keytool -list -cacerts
~~~

Lệnh có thể yêu cầu password để kiểm tra store integrity. **Không cần** thay đổi file `cacerts` gốc chỉ để học bài này.

### 9.3. Truststore tường minh **không mặc định cộng thêm** các root trong `cacerts`

Khi đặt:

~~~text
-Djavax.net.ssl.trustStore=client-trust.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

default JSSE trust manager thường dùng **file chỉ định** làm truststore. Đừng giả định nó tự động hợp nhất mọi CA trong `cacerts` với `client-trust.p12`.

**Hệ quả quan trọng:** Một truststore chỉ chứa root CA của nội bộ có thể làm những kết nối tới website bên ngoài bị `PKIX path building failed` vì thiếu public CAs vốn có trong `cacerts`. Muốn tin cả hai tập CA cần chuẩn bị trust material hợp lệ theo chính sách ứng dụng hoặc cấu hình trust managers rõ ràng; **không tự thêm mọi CA tùy tiện**.

### 9.4. Đường dẫn truststore tường minh sai cũng nguy hiểm

Theo tài liệu SunJSSE, nếu `javax.net.ssl.trustStore` đã được đặt nhưng đường dẫn **không tồn tại**, default trust manager có thể được tạo với **empty keystore** thay vì fallback về `cacerts`.

Vì vậy khi gặp `PKIX path building failed`, hãy kiểm tra **file mount/path/permissions** trước khi đổ lỗi certificate của server. Trường hợp này đặc biệt hay gặp trong Docker/Kubernetes khi app start với cấu hình truststore path nhưng volume chưa được mount đúng.

## 10. Phòng lab: tạo CA gốc, server identity và client truststore bằng `keytool`

Bài lab sẽ có các artifact:

~~~text
ca-private.p12          PRIVATE — root CA private key, chỉ dùng để ký trong lab
demo-root.cer           PUBLIC — root CA certificate được export
server-identity.p12     PRIVATE — server private key + signed certificate chain
client-trust.p12        PUBLIC CERTS — trusted root CA certificate, không có private key
server.csr              PUBLIC request — xin phát hành chứng thư server
server-signed.cer       PUBLIC — server leaf certificate do demo root ký
~~~

**Môi trường đã kiểm chứng:** HotSpot/OpenJDK **24.0.2**, chương trình Java tương thích Java 17+, dùng `keytool` sẵn trong JDK.

**Quan trọng về bảo mật:** Tất cả passwords như `DemoOnly123` chỉ phục vụ **phòng lab cục bộ**. Không dùng password này ngoài lab, không copy lệnh chứa mật khẩu vào production/CI logs. `keytool` có thể nhận password theo lời nhắc hoặc cơ chế bảo vệ phù hợp; trong môi trường thật hãy sử dụng secrets management/HSM, phân quyền và chính sách rotation.

### 10.1. Bước 1 — sinh root CA **chỉ cho lab**

Tại một **thư mục trống dành riêng** cho bài học:

~~~bash
keytool -genkeypair -alias demo-root -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=DemoRoot,O=Example" -ext "BC:c=ca:true" -ext "KU:c=keyCertSign,cRLSign" -validity 365 -keystore ca-private.p12 -storetype PKCS12 -storepass DemoOnly123 -keypass DemoOnly123 -noprompt
~~~

Ý nghĩa:

- `-genkeypair`: tạo một cặp RSA public/private keys.
- `-keysize 3072` và `SHA256withRSA`: chọn cấu hình đủ mạnh cho ví dụ hiện đại.
- `-dname`: Subject name của root CA thử nghiệm.
- `BC:c=ca:true`: Basic Constraints cho CA, đánh dấu critical.
- `KU:c=keyCertSign,cRLSign`: KeyUsage dành cho CA ký certificates/CRLs.
- `-keystore ca-private.p12`: nơi chứa **root CA private key**.
- `-storetype PKCS12`: chọn định dạng store.
- `-validity 365`: hiệu lực 365 ngày, chỉ để lab.

**Không copy `ca-private.p12` vào server hoặc client production.** CA private key là một trong những tài sản cần bảo vệ nghiêm ngặt nhất trong PKI.

### 10.2. Bước 2 — export **chứng thư công khai** của root CA

~~~bash
keytool -exportcert -alias demo-root -keystore ca-private.p12 -storetype PKCS12 -storepass DemoOnly123 -rfc -file demo-root.cer
~~~

`demo-root.cer` chứa **root CA certificate** ở dạng PEM nhờ `-rfc`, không chứa private key. Có thể xem thông tin:

~~~bash
keytool -printcert -file demo-root.cer
~~~

Với chứng thư CA thật, luôn kiểm tra **SHA-256 fingerprint** và nguồn công bố qua kênh đáng tin độc lập trước khi thêm vào kho tin cậy. Trong lab, ta tự tạo CA nên biết nguồn của nó.

### 10.3. Bước 3 — sinh server identity keypair

~~~bash
keytool -genkeypair -alias server -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=localhost,O=Example" -ext "SAN=dns:localhost,ip:127.0.0.1" -validity 365 -keystore server-identity.p12 -storetype PKCS12 -storepass DemoOnly123 -keypass DemoOnly123 -noprompt
~~~

Lệnh tạo `PrivateKeyEntry` tên `server` với private key và **chứng thư self-signed tạm thời** (chưa do demo root ký). SAN có cả `DNS:localhost` và `IP:127.0.0.1` để bài lab TLS có thể bật hostname checking với địa chỉ IPv4 loopback.

**Cảnh báo:** `CN=localhost` không thể thay cho SAN trong hướng dẫn TLS hiện đại. Luôn phát hành đúng SAN cho hostname/IP client sẽ kết nối.

### 10.4. Bước 4 — tạo CSR xin CA ký server certificate

~~~bash
keytool -certreq -alias server -keystore server-identity.p12 -storetype PKCS12 -storepass DemoOnly123 -file server.csr
~~~

`server.csr` chứa thông tin yêu cầu và public key/định danh; **không phải private key**. Trong một quy trình PKI thực, CSR sẽ được đưa qua luồng phê duyệt của CA thay vì tự phát hành bằng root key trên máy ứng dụng.

### 10.5. Bước 5 — root CA thử nghiệm ký chứng thư server

~~~bash
keytool -gencert -alias demo-root -keystore ca-private.p12 -storetype PKCS12 -storepass DemoOnly123 -infile server.csr -outfile server-signed.cer -rfc -validity 120 -ext "SAN=dns:localhost,ip:127.0.0.1" -ext "KU:c=digitalSignature,keyEncipherment" -ext "EKU=serverAuth"
~~~

Chứng thư đầu cuối mới có:

- Issuer là `DemoRoot`.
- SAN cho `localhost` và `127.0.0.1`.
- KeyUsage và EKU thích hợp cho **TLS server authentication** trong ví dụ.
- Certificate signature bởi CA private key trong `ca-private.p12`.

**Lưu ý:** Lệnh này ký leaf certificate trong một PKI lab tối giản. Trong production, thông thường nên dùng hệ thống CA quản lý chính sách cấp phát, audit, rotation và revocation, thay vì đặt root private key trong mỗi quy trình build ứng dụng.

### 10.6. Bước 6 — nạp public root vào identity store để xây chain

~~~bash
keytool -importcert -alias demo-root -file demo-root.cer -keystore server-identity.p12 -storetype PKCS12 -storepass DemoOnly123 -noprompt
~~~

Đây là một **public certificate entry** trong server store. **Nó không đưa CA private key vào server identity store.** Mục đích là để `keytool` nhận được CA certificate khi nhập chứng thư server do CA này ký.

Chính bước này minh họa một điểm quan trọng: **identity keystore có thể chứa thêm trusted certificate entry**, dù vai trò chính của nó vẫn là cung cấp `PrivateKeyEntry` của server.

### 10.7. Bước 7 — nhập chứng thư server đã ký vào **đúng alias `server`**

~~~bash
keytool -importcert -alias server -file server-signed.cer -keystore server-identity.p12 -storetype PKCS12 -storepass DemoOnly123 -noprompt
~~~

Vì alias `server` đã là key entry, lệnh này là **certificate reply import**, thay chứng thư tự ký ban đầu bằng chuỗi chứng thư phù hợp. Private key của server **không bị chuyển qua client truststore**.

**Kết quả `keytool -list -v` đã kiểm chứng:**

~~~text
Entry type: PrivateKeyEntry
Certificate chain length: 2
~~~

Lệnh kiểm tra:

~~~bash
keytool -list -v -alias server -keystore server-identity.p12 -storetype PKCS12 -storepass DemoOnly123
~~~

`Certificate chain length: 2` xuất hiện trong lab vì chain gồm server certificate và root CA certificate. Không đòi production TLS server bắt buộc gửi root CA trong handshake; đó là câu hỏi khác với cấu trúc chain nội bộ của key entry.

### 10.8. Bước 8 — tạo **client truststore**, nhập **chỉ chứng thư công khai**

~~~bash
keytool -importcert -alias demo-root -file demo-root.cer -keystore client-trust.p12 -storetype PKCS12 -storepass DemoOnly123 -noprompt
~~~

`client-trust.p12` được tạo mới nếu chưa có. Nó chứa một chứng thư gốc đã được chấp nhận trong lab, **không chứa private key**. Kiểm tra:

~~~bash
keytool -list -v -alias demo-root -keystore client-trust.p12 -storetype PKCS12 -storepass DemoOnly123
~~~

Kết quả loại entry đã kiểm chứng:

~~~text
Entry type: trustedCertEntry
~~~

**Trong production, không dùng `-noprompt` để nhập một chứng thư lấy từ nguồn chưa xác minh.** Khi nhập root CA thật, kiểm tra fingerprint từ một nguồn tin cậy độc lập. Bật `-noprompt` chỉ vì muốn bỏ cảnh báo trust có thể đưa một root CA giả mạo vào truststore.

### 10.9. Vì sao tạo root CA certificate khác tạo root CA private key?

Trong lab:

- `ca-private.p12`: chứa **khóa riêng của CA**, có thể phát hành chứng thư. Cần bảo mật cao.
- `demo-root.cer`: chứa **chứng thư công khai của CA**, dùng để xây niềm tin.
- `server-identity.p12`: chứa **private key của server**, cùng public chain.
- `client-trust.p12`: chứa **root CA certificate** để xác minh server.

**Đừng gửi `ca-private.p12` hoặc `server-identity.p12` cho client chỉ để client tin server.** Client chỉ cần trust anchor phù hợp.

## 11. Chương trình Java 17+ đầy đủ: quan sát entries và bắt tay TLS thật

Để tránh kết luận chỉ từ danh sách file, chúng ta dùng **Java SE APIs** để:

1. Load identity store và truststore dưới dạng PKCS12.
2. Kiểm tra `PrivateKeyEntry` và `TrustedCertificateEntry`.
3. Tạo `KeyManagerFactory` từ identity keystore.
4. Tạo `TrustManagerFactory` từ truststore.
5. Tạo TLS server và TLS client trên **127.0.0.1** trong cùng process.
6. Bật **HTTPS endpoint identification** cho client.
7. Chạy handshake và truyền một byte **42** sau khi client đã xác minh server.

Lưu tên **`KeyStoreRolesDemo.java`**:

~~~java
import java.io.InputStream;
import java.net.InetAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.concurrent.*;
import javax.net.ssl.*;

public class KeyStoreRolesDemo {
    private static KeyStore read(String path, char[] password)
            throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(path))) {
            store.load(in, password);
        }
        return store;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "identity.p12 trust.p12");
        }

        String secret = System.getenv("LAB_STORE_PASSWORD");
        if (secret == null || secret.isBlank()) {
            throw new IllegalStateException("Set LAB_STORE_PASSWORD");
        }
        char[] pass = secret.toCharArray();

        KeyStore identity = read(args[0], pass);
        KeyStore trusted = read(args[1], pass);

        System.out.println("identity.privateKeyEntry=" +
                identity.entryInstanceOf(
                        "server", KeyStore.PrivateKeyEntry.class));
        System.out.println("identity.chainLength=" +
                identity.getCertificateChain("server").length);
        System.out.println("trust.trustedCertEntry=" +
                trusted.entryInstanceOf(
                        "demo-root", KeyStore.TrustedCertificateEntry.class));
        System.out.println("trust.hasPrivateKey=" +
                trusted.isKeyEntry("demo-root"));

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(identity, pass);

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trusted);

        SSLContext serverTls = SSLContext.getInstance("TLS");
        serverTls.init(kmf.getKeyManagers(), null, null);

        SSLContext clientTls = SSLContext.getInstance("TLS");
        clientTls.init(null, tmf.getTrustManagers(), null);

        InetAddress local = InetAddress.getByName("127.0.0.1");

        try (SSLServerSocket listener =
                     (SSLServerSocket) serverTls.getServerSocketFactory()
                             .createServerSocket(0, 1, local)) {
            ExecutorService threads = Executors.newSingleThreadExecutor();
            try {
                Future<Boolean> serverDone = threads.submit(() -> {
                    try (SSLSocket peer =
                                 (SSLSocket) listener.accept()) {
                        peer.startHandshake();
                        peer.getOutputStream().write(42);
                        peer.getOutputStream().flush();
                        return true;
                    }
                });

                try (SSLSocket client =
                             (SSLSocket) clientTls.getSocketFactory()
                                     .createSocket(
                                             local, listener.getLocalPort())) {
                    SSLParameters parameters = client.getSSLParameters();
                    parameters.setEndpointIdentificationAlgorithm("HTTPS");
                    client.setSSLParameters(parameters);

                    client.startHandshake();

                    System.out.println("client.verifiedServer=" +
                            (client.getSession()
                                    .getPeerCertificates().length > 0));
                    System.out.println("client.received=" +
                            client.getInputStream().read());
                }

                System.out.println("server.handshakeCompleted=" +
                        serverDone.get(10, TimeUnit.SECONDS));
            } finally {
                threads.shutdownNow();
            }
        }
    }
}
~~~

### 11.1. Biên dịch và cấu hình password **chỉ cho lab**

~~~bash
javac -encoding UTF-8 KeyStoreRolesDemo.java
export LAB_STORE_PASSWORD='DemoOnly123'
java KeyStoreRolesDemo server-identity.p12 client-trust.p12
~~~

Trên Windows PowerShell:

~~~powershell
javac -encoding UTF-8 KeyStoreRolesDemo.java
$env:LAB_STORE_PASSWORD = 'DemoOnly123'
java KeyStoreRolesDemo server-identity.p12 client-trust.p12
Remove-Item Env:LAB_STORE_PASSWORD
~~~

Mật khẩu được đưa qua biến môi trường **chỉ nhằm tránh hard-code vào mã Java và đơn giản hóa lab**. Biến môi trường cũng không phải một secret store hoàn hảo; trong production nên dùng cơ chế đọc secrets được quản lý, identity/token/HSM và giải pháp phù hợp với threat model. Không lưu mật khẩu vào Git hay log.

**Không chạy chương trình với bộ `server-identity.p12` khác bộ `client-trust.p12` đã tạo**, vì kết quả xác thực sẽ phụ thuộc CA đã ký và truststore thực tế.

### 11.2. Stdout đã kiểm chứng bằng HotSpot/OpenJDK 24.0.2

~~~text
identity.privateKeyEntry=true
identity.chainLength=2
trust.trustedCertEntry=true
trust.hasPrivateKey=false
client.verifiedServer=true
client.received=42
server.handshakeCompleted=true
~~~

Đây là **kết quả đã quan sát thực tế** sau khi thực hiện tám bước `keytool` trên JDK 24.0.2 và chạy chương trình.

Từng dòng:

- `identity.privateKeyEntry=true`: alias `server` có private key entry.
- `identity.chainLength=2`: private key entry chứa chain server + root của lab.
- `trust.trustedCertEntry=true`: alias `demo-root` trong truststore là trusted public certificate.
- `trust.hasPrivateKey=false`: truststore không giữ CA private key.
- `client.verifiedServer=true`: sau `client.startHandshake()` thành công với `TrustManager` riêng và HTTPS endpoint identification, client thấy peer certificate; Boolean này **không phải tự nó thay thế validation**, validation xảy ra trong handshake.
- `client.received=42`: client đọc đúng byte server ghi sau handshake.
- `server.handshakeCompleted=true`: server-side handshake hoàn tất.

### 11.3. Vì sao đây là chứng minh mạnh hơn việc chỉ thấy hai file?

Chương trình đã thực hiện:

1. **Key selection từ identity store** cho server thông qua `KeyManagerFactory`.
2. **Trust path validation** từ client truststore thông qua `TrustManagerFactory`.
3. **Hostname/IP verification** theo thuật toán `HTTPS` và SAN có IP `127.0.0.1`.
4. Gửi byte qua một TLS channel đã được thiết lập thành công.

Chương trình **không truyền root private key** sang client, và **client không truyền truststore** cho server.

**Giới hạn:** Bài lab xác thực **server**, không phải mTLS. Để làm mTLS cần thêm client identity, server truststore và bật required client authentication. Không suy từ thử nghiệm một chiều rằng client cũng đã được server xác minh.

### 11.4. Cleanup dữ liệu thử nghiệm

Sau khi học xong, xóa những artifact lab ở **đúng thư mục test bạn tự tạo** và theo chính sách hệ thống. Đặc biệt `ca-private.p12` và `server-identity.p12` chứa private keys của lab.

**Không đưa lệnh xóa hàng loạt với đường dẫn tự suy đoán** vào script production. Không tải private key thử nghiệm lên repo hoặc kho tài liệu chia sẻ.

## 12. Các System Properties JSSE khi dùng cấu hình mặc định

Nhiều Java frameworks cho phép chỉ định stores bằng file/config riêng. Với **default JSSE SSLContext**, những properties phổ biến:

| Property | Vai trò |
| --- | --- |
| `javax.net.ssl.keyStore` | Đường dẫn identity keystore mặc định. |
| `javax.net.ssl.keyStoreType` | Định dạng/provider type của identity store, như PKCS12. |
| `javax.net.ssl.keyStorePassword` | Password đọc identity store theo provider. |
| `javax.net.ssl.trustStore` | Đường dẫn truststore mặc định. |
| `javax.net.ssl.trustStoreType` | Định dạng/provider type của truststore. |
| `javax.net.ssl.trustStorePassword` | Password để xác minh integrity/đọc truststore. |

Ví dụ **chỉ minh họa đường dẫn và vai trò, chưa có quản lý password**:

~~~bash
java -Djavax.net.ssl.keyStore=server-identity.p12 -Djavax.net.ssl.keyStoreType=PKCS12 -Djavax.net.ssl.trustStore=client-trust.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -jar app.jar
~~~

**Không lấy lệnh này như cấu hình production hoàn chỉnh.** Một TLS server thường chỉ cần identity store; truststore của client phải cấu hình ở **client process**, không nhất thiết chung command line. Lệnh trên chỉ gom tên properties để nhìn sự khác biệt.

**Không truyền password trực tiếp trong `-Djavax.net.ssl.keyStorePassword=...` qua terminal/CI nếu có nguy cơ lộ trong process arguments, logs hoặc tools.** Dùng secret management hoặc API cấu hình an toàn.

### 12.1. Properties có thay đổi SSLContext được tạo thủ công không?

Không nên mặc định. Nếu ứng dụng tạo `SSLContext` thủ công và gọi `init(kmf.getKeyManagers(), tmf.getTrustManagers(), ...)`, chính các managers mà ứng dụng cung cấp sẽ quyết định key/trust material của context đó.

Một số frameworks có **cấu hình TLS riêng**, thậm chí không sử dụng default JSSE system properties. Khi thấy `-Djavax.net.ssl.trustStore` “không có tác dụng”, cần kiểm tra library/framework đang tạo SSLContext ra sao.

### 12.2. `null` trong `TrustManagerFactory.init` là trường hợp khác

Trong SunJSSE, `TrustManagerFactory.init((KeyStore) null)` cho phép dùng cơ chế tìm **default trust material**, thường theo thứ tự truststore system property rồi `jssecacerts`/`cacerts`.

Điều đó **khác** việc tự khởi tạo một `KeyStore` trống và truyền nó vào `TrustManagerFactory.init(emptyStore)`: store trống không mặc định có root CAs của JDK.

Không làm ứng dụng “tin mọi server” bằng cách tạo empty truststore rồi cho rằng Java sẽ tự bỏ qua xác minh.

## 13. Không phải mọi certificate trong truststore đều là root CA

Một truststore có thể chứa:

- Root CA certificates được tổ chức/nhà cung cấp cấp phép tin.
- Một intermediate CA mà tổ chức chọn **tin trực tiếp** theo policy, nhưng làm tăng phạm vi trust anchor.
- Một leaf certificate **được tin trực tiếp** trong một mô hình private/internal hoặc pinning đặc thù (cần quản lý vòng đời và giới hạn cẩn thận).

**Nguy cơ:** Import một certificate từ email không kiểm tra và coi nó là trusted anchor có thể khiến client chấp nhận kẻ giả mạo hoặc một tập chứng thư ngoài phạm vi mong muốn.

Câu hỏi phải đặt trước khi import:

1. Certificate là root CA, intermediate CA hay leaf?
2. Chứng thư được lấy từ nguồn nào?
3. SHA-256 fingerprint đã được đối chiếu **out-of-band** chưa?
4. Chứng thư có ``BasicConstraints`, `KeyUsage` và `ExtendedKeyUsage` phù hợp không?
5. Có nên trust toàn bộ CA hay chỉ một endpoint? Phạm vi rủi ro tương ứng?
6. Chính sách rotation/revocation/expiry sẽ ra sao?
7. Có cần tránh thay thế toàn bộ JDK roots không?
8. Bên nào cần certificate đó — TLS client hay server yêu cầu mTLS?

### 13.1. Truststore không tự thay thế PKIX policy

Java PKIX còn xem xét:

- Certificate signatures và path construction.
- Validity và chain constraints.
- BasicConstraints và KeyUsage.
- ExtendedKeyUsage tương ứng TLS server/client.
- Algorithm restrictions và security properties như `jdk.certpath.disabledAlgorithms`.
- Một số name/policy constraints theo validator/provider.
- Hostname verification khi protocol yêu cầu.
- Revocation checks nếu đã cấu hình và có dữ liệu cần thiết.

**Chú ý:** Theo tài liệu Oracle JSSE, PKIX TrustManagerFactory khi khởi tạo bằng `init(KeyStore)` thường **không bật revocation checking mặc định**. Không phát biểu “chỉ cần root CA trong truststore là Java chắc chắn luôn phát hiện mọi chứng thư bị thu hồi”. Nếu yêu cầu OCSP/CRL, phải cấu hình và kiểm chứng theo policy của tổ chức và runtime.

### 13.2. CA root và “pinning” không đồng nhất

- **CA trust:** tin một CA phù hợp để phát hành chuỗi chứng thư theo constraints.
- **Leaf trust hoặc pinning:** tin một chứng thư/public key cụ thể tùy policy.
- **Intermediate direct trust:** có thể tạo một trust anchor ở giữa chain với phạm vi khác.

Không áp dụng chiến lược import một leaf vào global `cacerts` chỉ để “sửa mọi lỗi TLS”; việc đó có thể tạo chính sách trust khó quản lý khi chứng thư hết hạn/rotation.

## 14. Phân biệt chain gửi qua TLS và các file trên máy

Một server có thể có các file:

~~~text
server.key          private key dạng PEM (bảo mật)
server.crt          leaf certificate
intermediate.crt    intermediate CA cert (public)
server-identity.p12 PKCS12 đóng gói private key + chain
~~~

Trong Java, `server-identity.p12` là một cách lưu credentials. Trong khi đó client dùng:

~~~text
client-trust.p12    root CA public certificates (trust anchors)
~~~

**Private key không được gửi trong TLS.** Thông thường server gửi leaf certificate và các intermediate cần thiết. Client xây path tới **trust anchor của chính client**; truststore bản thân nó không được chuyển cho server.

Một server không gửi intermediate certificate thích hợp có thể khiến client không xây được path dù **root CA đã nằm trong `cacerts`**. Vì vậy không phải mọi `PKIX path building failed` đều được “sửa” bằng cách thêm root mới; đôi khi cần sửa **server certificate chain**.

## 15. Lỗi thường gặp và cách chẩn đoán

| Thông báo/hiện tượng | Khả năng chính | Cách xử lý đúng |
| --- | --- | --- |
| `PKIX path building failed`, `SunCertPathBuilderException` | Không xây được certification path tới trust anchor phù hợp. | Xem chain server gửi, CA nguồn, truststore hiện dùng, intermediate, expiry và policy. |
| `unable to find valid certification path to requested target` | Client không tìm thấy đường chứng thư hợp lệ. | Xác minh root/intermediate và truststore; không trust-all. |
| `No subject alternative names present` | Server certificate thiếu SAN phù hợp. | Phát hành certificate có đúng DNS/IP SAN. |
| `No name matching ... found` | Hostname mong kết nối không có trong SAN. | Sửa SAN hoặc tên endpoint; không tắt hostname verification. |
| `UnrecoverableKeyException` | Password/entry hoặc key material không giải mã đúng. | Kiểm tra store password vs key password, format và alias, secret source. |
| `Keystore was tampered with, or password was incorrect` | Password không đúng, format/keystore integrity issue, hoặc file hỏng. | Kiểm tra đúng file/type/password, backup, không brute-force. |
| `no suitable certificate` / `handshake_failure` | Không có danh tính phù hợp với thuật toán/issuer yêu cầu, hoặc sai mTLS setup. | Kiểm tra key entry, SAN, KU/EKU, clientAuth và signature algorithms. |
| `bad_certificate` | Peer từ chối chứng thư được trình. | Xem lỗi cụ thể phía peer và trust/policy ở peer. |
| TLS chạy trên laptop nhưng fail container | Truststore path/mount/JDK roots khác, secret thiếu hoặc chain khác. | Xác định JVM thực tế và files trong container. |
| `-Djavax.net.ssl.trustStore` không ảnh hưởng | Framework tạo SSLContext riêng hoặc property đặt sai process. | Đọc cấu hình framework và runtime flags. |
| Truststore mới làm các website công khai fail | Explicit truststore thay thế default CA roots. | Lập trust policy tổng hợp đúng, không mặc định hợp nhất. |
| File `.p12` có cert nhưng server không bắt tay | Không có `PrivateKeyEntry` phù hợp. | Dùng `keytool -list -v`; cần private key khớp leaf certificate. |

**Không** xem mọi lỗi TLS là “certificate expired”; lỗi có thể ở chain, hostname, algorithm constraints, key entry, mTLS hoặc việc chọn sai truststore.

### 15.1. Dùng `keytool` để xem entry type

~~~bash
keytool -list -v -keystore server-identity.p12 -storetype PKCS12
keytool -list -v -keystore client-trust.p12 -storetype PKCS12
~~~

Kiểm tra:

- `Entry type: PrivateKeyEntry` có trong identity store?
- Certificate chain có đúng leaf và CA intermediates cần thiết?
- `Entry type: trustedCertEntry` có trong truststore?
- Subject, issuer, SHA-256 fingerprint, validity, SAN, key usage có phù hợp?
- Alias được code/KeyManager chọn có khớp không?

**Không** chia sẻ output chứa đường dẫn bí mật, usernames hoặc thông tin nội bộ không cần thiết.

### 15.2. Bật JSSE diagnostic logging có giới hạn

Ở môi trường kiểm thử được kiểm soát:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager -jar app.jar
~~~

Đây là **mẫu chẩn đoán**; `app.jar` phải tồn tại và app phải dùng JSSE để log có giá trị. Log có thể rất nhiều và làm lộ certificate subjects, paths, endpoints và thông tin cấu hình. **Không bật thường trực ở production**.

Khi đọc, chú ý:

- Trust material nào được nạp?
- Bên nào gửi certificate chain?
- Server có yêu cầu client certificate không?
- Client có key/certificate phù hợp không?
- PKIX/hostname check thất bại tại đâu?
- Có thuật toán/giao thức nào bị vô hiệu hóa theo policy không?

Không lạm dụng debug như cách thu private key. Log TLS bình thường **không được** xuất private keys để tiện chẩn đoán.

## 16. Quy trình xử lý một chứng thư root CA nội bộ

Giả sử ứng dụng Java cần gọi `https://internal.example` với chứng thư do **CA nội bộ** ký. Quy trình vận hành hợp lý:

1. Xác định JVM/JDK vendor/build và **truststore thực tế** của process, không chỉ máy phát triển.
2. Thu chain từ endpoint qua công cụ kiểm tra TLS và đối chiếu với PKI records.
3. Kiểm tra server gửi **leaf + intermediate** phù hợp; xác nhận SAN và expiry.
4. Xác định root CA tổ chức muốn tin, theo policy phê duyệt.
5. Nhận root CA public cert từ nguồn quản trị **đáng tin**, đối chiếu SHA-256 fingerprint qua kênh độc lập.
6. Chuẩn bị truststore riêng hoặc trust policy composite theo cấu hình ứng dụng; không sửa global `cacerts` nếu không có lý do tổ chức.
7. Import CA public certificate, **không import private key**.
8. Mount truststore ở runtime path có quyền phù hợp.
9. Xác nhận truststore đó thực sự được `TrustManager` dùng; lưu ý explicit property có thể thay thế JDK roots.
10. Kiểm tra HTTPS hostname verification và chain validation **không bị vô hiệu hóa**.
11. Thiết lập quy trình CA rotation và certificate expiration monitoring.
12. Kiểm thử lại từ đúng runtime image/container dưới network policy giống production.

**Không** tải certificate từ endpoint đang bị MITM rồi import ngay vào truststore: việc “nhìn thấy certificate trên mạng” **không chứng minh** nó đáng tin.

## 17. Quản lý keys và trust theo nguyên tắc tối thiểu quyền

### 17.1. Private key cần bảo mật cao hơn public certificate

- Private keys có thể cho phép giả mạo danh tính nếu bị đánh cắp.
- Hạn chế quyền đọc vào user/process thực sự cần ký/xác thực.
- Tránh commit `.p12` có private key vào Git, image công khai, ticket hoặc log.
- Dùng secrets manager, HSM/PKCS11 khi phù hợp threat model.
- Có quy trình issuance, expiration, rotation và revoke.
- Không dùng mật khẩu thử nghiệm `DemoOnly123` ở môi trường thật.

### 17.2. Truststore public nhưng **không được sửa tùy ý**

Dù chỉ chứa public certificates, truststore là **nguồn quyết định ai được tin**. Nếu attacker có quyền thêm CA giả, họ có thể khiến ứng dụng chấp nhận chứng thư giả mạo.

Do đó:

- Quyền ghi truststore phải hạn chế.
- Phải có code review/change management cho việc thêm/bỏ trust anchor.
- Có thể pin artifact/version hoặc kiểm tra checksum/signature nguồn gốc.
- Chỉ tin các CA thực sự cần thiết, hạn chế mở rộng attack surface.
- Ghi rõ trách nhiệm cập nhật khi root CA bị loại, expired hoặc thay chính sách.

### 17.3. Rotation đúng đối tượng

| Đối tượng thay đổi | Cần điều chỉnh |
| --- | --- |
| Server leaf certificate mới **cùng CA** | Thay certificate chain trong server identity, có thể giữ truststore client nếu CA vẫn đáng tin. |
| Server keypair mới | Thay **private key + certificate matching chain** trong identity store. |
| Intermediate CA mới | Server thường cần cập nhật intermediate chain, client có thể vẫn tin cùng root. |
| Root CA đổi | Cập nhật truststore theo migration plan có thời gian overlap được phê duyệt. |
| Client identity đổi trong mTLS | Client keystore thay; server trust policy phải tiếp tục chấp nhận issuer/client identity phù hợp. |
| JDK vendor/security update | Đối chiếu danh sách root CA và algorithm restrictions, benchmark/kiểm tra compatibility. |

**Không** coi “thay server private key” và “thêm root CA vào client truststore” là cùng một thao tác.

## 18. Những ngộ nhận phổ biến

| Ngộ nhận | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Keystore và truststore là hai file formats khác nhau.” | Cả hai thường là PKCS12/`KeyStore`. | Khác **vai trò**, không bắt buộc khác format. |
| “Truststore phải có CA private key để xác minh chữ ký.” | Xác minh dùng public key của CA. | Chỉ cần CA certificate/trust anchor phù hợp. |
| “Server cần private key của root CA.” | Server chỉ cần own private key và chain. | Root private key thuộc CA, phải tách biệt. |
| “Client phải tải nguyên `server-identity.p12`.” | File chứa server private key rất nhạy cảm. | Client dùng trusted public root/chain theo policy. |
| “Chứng thư gốc tự ký nào cũng đáng tin.” | Self-signed không tạo niềm tin. | Tin do chọn trust anchor có kiểm chứng. |
| “Keystore chỉ có private keys, truststore chỉ có certificate.” | Cùng một `KeyStore` có thể có cả hai entry types. | Xem `PrivateKeyEntry`/`TrustedCertificateEntry` và managers. |
| “Tên file `.jks` là keystore, `.p12` là truststore.” | Đuôi file không nói mục đích. | PKCS12 dùng được cho cả hai. |
| “JKS là default mới nhất.” | PKCS12 là default từ JDK 9. | Ưu tiên PKCS12 khi tạo store mới. |
| “Thêm root CA của tổ chức vào truststore sẽ tự gộp JDK public roots.” | Explicit truststore thường thay trust material mặc định. | Xác định policy kết hợp nếu cần. |
| “Set sai `javax.net.ssl.trustStore` thì Java sẽ fallback `cacerts`.” | SunJSSE có thể dùng empty truststore khi file tường minh không tồn tại. | Kiểm tra path trước. |
| “Tin CA nghĩa là mọi hostname đều hợp lệ.” | Hostname/SAN là bước xác minh riêng. | Bật HTTPS endpoint identification. |
| “Server trình chứng thư là client đã được xác thực.” | Mặc định HTTPS chỉ xác thực server. | Dùng mTLS nếu cần server verify client. |
| “Đưa cert vào truststore sẽ tự bật mTLS.” | Server phải yêu cầu client cert; client phải có key. | Cấu hình hai chiều rõ ràng. |
| “Certificate chain gửi qua TLS phải có root.” | Root thường đã ở client truststore. | Gửi leaf/intermediates cần thiết, trust anchor nội bộ. |
| “Root trust là đủ, không cần kiểm tra thời hạn/algorithms.” | PKIX có nhiều validation rules. | Đọc validity, KU/EKU, SAN, algorithm policy. |
| “Revocation luôn tự được kiểm tra.” | Default PKIX TrustManager thường không bật revocation check chỉ từ `init(store)`. | Cấu hình OCSP/CRL theo policy. |
| “Gặp `PKIX path building failed` thì tắt trust checks.” | Mất xác thực, nguy cơ MITM. | Sửa chain/truststore/policy đúng cách. |
| “`keytool -noprompt` luôn an toàn.” | Có thể chấp nhận chứng thư chưa kiểm nguồn. | Chỉ tự động import sau khi verify fingerprint ngoài băng. |
| “Password trong `-D...` không ai thấy.” | Process args/log/CI có thể lộ. | Dùng cơ chế quản lý secrets phù hợp. |
| “Một chứng thư self-signed leaf có thể thay root CA cho mọi hệ thống.” | Trust trực tiếp leaf là quyết định phạm vi hẹp và cần rotation. | Chọn trust model phù hợp, không mở rộng trust bừa. |
| “Đổi JDK không ảnh hưởng truststore.” | Root program và algorithm restrictions cập nhật. | Kiểm chứng sau update. |

## 19. Bài tập thực hành có đáp án

### Câu 1 — Server cần giữ gì?

Một server cần chứng minh danh tính `api.example.com`. Dữ liệu quan trọng nhất trong identity store là gì?

**Đáp án:** **Private key của server** và certificate chain phù hợp cho public key đó; không phải root CA private key.

### Câu 2 — Client cần giữ gì?

Một client muốn tin server do root CA nội bộ ký. Có cần private key của CA không?

**Đáp án:** **Không**. Client cần CA **public certificate/trust anchor**, policy hợp lệ và hostname verification. CA private key không được chia sẻ.

### Câu 3 — Entry type

~~~text
Alias: service
Entry type: PrivateKeyEntry
Certificate chain length: 3
~~~

**Đáp án:** Alias này chứa một private key tương ứng với certificate chain gồm ba certs. Đây là một dạng identity entry phù hợp `KeyManager` theo usage/policy.

### Câu 4 — Trust entry

~~~text
Alias: organization-ca
Entry type: trustedCertEntry
~~~

**Đáp án:** Đây là chứng thư công khai được cấu hình đáng tin. Không có private key trong entry đó.

### Câu 5 — Hai file cùng là PKCS12

`server-identity.p12` và `client-trust.p12` cùng có `storetype=PKCS12`. Có mâu thuẫn không?

**Đáp án:** Không. PKCS12 là **format**; identity/trust là **vai trò**.

### Câu 6 — Thêm root vào truststore

Tại sao không nên import root certificate vừa tải được từ endpoint lỗi TLS mà chưa kiểm tra fingerprint?

**Đáp án:** Endpoint có thể đã bị can thiệp/MITM. Chỉ import root CA public certificate được xác minh qua kênh đáng tin độc lập.

### Câu 7 — JEP 319

JEP 319 của Java 10 cung cấp điều gì?

**Đáp án:** Một bộ **root CA certificates mặc định** cho OpenJDK qua `cacerts`. Nó **không** cung cấp private key của những CA này cho ứng dụng Java.

### Câu 8 — Keystore default format

Từ JDK 9, store type mặc định là gì?

**Đáp án:** **PKCS12** (theo Java/JDK provider mặc định); không lấy JKS làm đề xuất tạo mới mặc định.

### Câu 9 — HTTPS hostname

Client tin root CA nhưng kết nối `api.example.com` tới chứng thư chỉ có SAN `DNS:wrong.example`. Có nên cho qua?

**Đáp án:** Không. Cần hostname verification khớp SAN; khắc phục bằng cấp certificate đúng tên hoặc kết nối đúng endpoint.

### Câu 10 — mTLS

Một client đã có truststore với root CA server. Server yêu cầu mTLS. Client còn thiếu gì?

**Đáp án:** **Client private key + certificate chain** phù hợp và cấu hình KeyManager; server cần trust material để xác minh client.

### Câu 11 — Wrong truststore path

App đặt `javax.net.ssl.trustStore=/missing/trust.p12` và báo PKIX error. Có chắc JVM tự chuyển về `cacerts`?

**Đáp án:** Không. SunJSSE có thể tạo empty truststore khi path tường minh không tồn tại. Phải kiểm tra mount/path/quyền và cấu hình runtime.

### Câu 12 — Root CA private key lộ

Có thể chỉ cần cập nhật truststore mà không xử lý CA key compromise?

**Đáp án:** Không. Đây là sự cố PKI nghiêm trọng; cần theo quy trình incident response/revocation/rotation và cập nhật trust anchors có kiểm soát.

### Câu 13 — PKIX lỗi

Một server không gửi intermediate certificate, nhưng client có root CA trong truststore. Có khả năng vẫn bị `PKIX path building failed` không?

**Đáp án:** Có. Client có thể không xây được chain do thiếu intermediate nếu không lấy được qua nguồn khác. Sửa **server chain** trước khi import một root mới.

### Câu 14 — `trust.hasPrivateKey=false`

Dòng này trong lab nói điều gì?

**Đáp án:** Alias `demo-root` trong client truststore không chứa private key; client dùng public root certificate để xác minh server.

### Câu 15 — Rotation

Server đổi leaf certificate nhưng vẫn được CA đáng tin cậy ký. Có bắt buộc thay client truststore?

**Đáp án:** Không nhất thiết. Nếu root/trust anchor và PKIX/hostname/policy vẫn hợp lệ, client truststore có thể giữ nguyên. Server cần identity key/chain cập nhật.

### Câu 16 — Revocation

Truststore chứa đúng root CA thì Java tự kiểm tra OCSP/CRL trong mọi trường hợp?

**Đáp án:** Không. Revocation behavior cần cấu hình xác minh và dữ liệu theo policy; SunJSSE PKIX default qua `init(KeyStore)` thường không bật revocation checking.

### Câu 17 — Java KeyStore API

`TrustManagerFactory` có thể dùng cùng lớp `KeyStore` với `KeyManagerFactory` không?

**Đáp án:** Có. `KeyStore` là abstraction cho dữ liệu keys/certs; **factory và entry types** xác định vai trò mà dữ liệu được sử dụng.

### Câu 18 — Chứng thư server self-signed

Có thể cấu hình client tin trực tiếp leaf self-signed cho lab không?

**Đáp án:** Có thể trong trường hợp được kiểm soát, nhưng điều đó là quyết định trust riêng với hạn chế rotation/policy và không nên dùng để thay thiết kế PKI production. Bài lab hiện tại dùng **root CA riêng ký leaf server**, đúng cấu trúc root trust.

## 20. Checklist triển khai và kiểm tra

- [ ] Tôi biết ai là **TLS client** và ai là **TLS server** trong từng kết nối.
- [ ] Tôi phân biệt **private key**, **public certificate**, **root CA**, intermediate và leaf.
- [ ] Tôi chọn identity store chứa `PrivateKeyEntry` cho phía cần trình chứng thư.
- [ ] Tôi chọn truststore có `TrustedCertificateEntry` phù hợp cho phía cần xác minh peer.
- [ ] Tôi không đưa CA private key vào truststore hoặc copy server identity file sang client.
- [ ] Tôi biết `KeyStore` là API chung, PKCS12 là format, identity/trust là vai trò.
- [ ] Tôi ưu tiên PKCS12 cho store mới và không thiết kế mới dựa vào JKS legacy.
- [ ] Tôi biết `cacerts` chứa một tập root CAs do JDK/vendor quản lý, có liên hệ JEP 319.
- [ ] Tôi kiểm tra `jssecacerts` và `cacerts` khi dùng default SunJSSE trust manager.
- [ ] Tôi không kỳ vọng explicit truststore tự hợp nhất `cacerts`.
- [ ] Tôi kiểm tra đường dẫn `javax.net.ssl.trustStore` không bị sai hoặc thiếu mount.
- [ ] Tôi hiểu `KeyManagerFactory` cung cấp local identity, còn `TrustManagerFactory` xác minh peer.
- [ ] Tôi biết server không gửi private key và client không gửi nguyên truststore qua TLS.
- [ ] Tôi bật hostname/IP verification bằng đúng SAN trong HTTPS client.
- [ ] Tôi kiểm tra KeyUsage, ExtendedKeyUsage, validity và algorithm constraints.
- [ ] Tôi không tự trust-all hoặc tắt hostname checking để “chữa” TLS errors.
- [ ] Tôi xác định có yêu cầu mTLS không, và cung cấp identity + trust ở cả hai phía nếu có.
- [ ] Tôi không coi một self-signed cert tự nhiên đáng tin nếu chưa được chấp nhận.
- [ ] Tôi xác minh SHA-256 fingerprint root CA từ nguồn độc lập trước khi import.
- [ ] Tôi không dùng `-noprompt` với certificates chưa xác minh.
- [ ] Tôi không để passwords/private keys trong source control, logs hoặc process args nếu có thể.
- [ ] Tôi có chính sách CA updates, renewal, revoke và root rotation.
- [ ] Tôi biết PKIX path validation không luôn bao gồm revocation checking tự động.
- [ ] Tôi thử kết nối từ đúng JVM/container có runtime stores và security policies thực tế.
- [ ] Tôi phân biệt đúng lỗi thiếu root, missing intermediate, SAN mismatch, wrong key alias và wrong password.
- [ ] Tôi chỉ sử dụng thuật toán/giao thức TLS hiện hành được runtime cho phép.

## 21. Tài liệu chính thức và kiến thức còn áp dụng

1. [Oracle Java SE 25 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html): `KeyManager`/`TrustManager`, `KeyManagerFactory`/`TrustManagerFactory`, `SSLContext`, các defaults `jssecacerts`/`cacerts`, TLS.
2. [Oracle Java SE 25 — Java PKI Programmer’s Guide](https://docs.oracle.com/en/java/javase/25/security/java-pki-programmers-guide.html): `TrustAnchor`, PKIX path building/validation và trust anchors.
3. [Oracle Java SE 24 — keytool Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html): PKCS12, `-genkeypair`, `-exportcert`, `-certreq`, `-gencert`, `-importcert`, `-list` và các entry types; cú pháp lab đã kiểm chứng trên JDK24.
4. [OpenJDK JEP 319 — Root Certificates](https://openjdk.org/jeps/319): bộ root CA certificates mặc định được đưa vào OpenJDK từ Java 10.
5. [Oracle Java SE 25 — java.security.KeyStore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyStore.html): `PrivateKeyEntry`, `TrustedCertificateEntry`, `SecretKeyEntry` và các phương thức truy vấn.
6. [Oracle Java SE 25 — java.security.cert.TrustAnchor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/cert/TrustAnchor.html): trust anchor là CA đáng tin, không đơn thuần “chứng thư tự ký”.
7. [Oracle Java SE 25 — X509ExtendedTrustManager](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html): chain validation và endpoint identity checks.
8. [Oracle Java SE 25 — javax.net.ssl.SSLParameters](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setEndpointIdentificationAlgorithm("HTTPS")` và TLS configuration.
9. [OpenJDK/JDK Operations — Trust Management](https://ops.java/security/trust/): keystore/truststore, PKCS12 default và quản lý CA roots.
10. [Oracle JDK 9 Release Notes — Default Keystore Type PKCS12](https://www.oracle.com/java/technologies/javase/9-notes.html): mốc thay đổi định dạng mặc định từ JKS sang PKCS12.
11. [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): BasicConstraints, KeyUsage, CA chains và path validation.
12. [Oracle Java SE 25 — JCA Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html): keystore, key management và security provider model.

**Kết luận:** Trong Java/JSSE, **identity keystore** cung cấp **private key và certificate chain** để phía hiện tại chứng minh danh tính; **truststore** cung cấp **public trusted certificates/trust anchors** để xác minh bên kia. Cả hai thường dùng chung API `KeyStore` và format **PKCS12**; không thể phân biệt chỉ bằng đuôi file. **Root CA certificate** có thể được phân phối trong `cacerts` từ JEP 319 Java 10 hoặc trong truststore của tổ chức, nhưng **root CA private key không được trao cho TLS clients/servers chỉ để xác minh**. TLS server gửi chain chứ không gửi private key, còn client dùng truststore riêng và kiểm tra thêm SAN/hostname. Với mTLS, mỗi phía có thể cần cả identity store lẫn truststore. Khi triển khai, ưu tiên PKCS12, bảo vệ secrets, xác minh fingerprint và PKIX/hostname, không dùng trust-all, và kiểm chứng trên đúng runtime JDK hiện đại.