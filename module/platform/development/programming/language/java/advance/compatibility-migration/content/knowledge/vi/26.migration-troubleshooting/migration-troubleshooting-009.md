# Lỗi bắt tay TLS, thuật toán bị vô hiệu hóa và truststore không khớp

Trong **Java Advance Compatibility Migration**, một ứng dụng có thể hoạt động tốt trên JDK cũ nhưng thất bại ngay khi nâng lên JDK mới với `SSLHandshakeException`, `PKIX path building failed`, `No appropriate protocol` hoặc `Algorithm constraints check failed`. Những thông báo này thường bị gọi chung là “lỗi SSL”, rồi được sửa tạm bằng cách bỏ kiểm tra certificate hoặc mở lại TLS cũ. Đây là hướng xử lý nguy hiểm: **các lỗi có thể xuất hiện ở những giai đoạn hoàn toàn khác nhau trong TLS handshake và cần biện pháp khắc phục khác nhau**.

Ví dụ, cùng là kết nối `https://api.partner.example`, nhưng lỗi có thể xuất phát từ:

- Client Java và server không còn protocol/cipher suite chung.
- JDK mới vô hiệu hóa thuật toán hoặc kích thước khóa không đạt chính sách.
- Server không gửi đủ intermediate certificates.
- Truststore ứng dụng không chứa trust anchor phù hợp.
- Ứng dụng dùng truststore khác JDK mà developer đang kiểm tra.
- Hostname không trùng Subject Alternative Name (SAN) của certificate.
- Server yêu cầu **mutual TLS (mTLS)** nhưng client không gửi certificate thích hợp.
- Proxy, load balancer hoặc service mesh trả certificate khác theo hostname/SNI.
- Container mới dùng JDK/truststore/security provider khác môi trường cũ.

Bài này thuộc nhóm **Chẩn đoán lỗi**, hướng dẫn xác định chính xác vị trí handshake thất bại, đọc JSSE debug log, kiểm tra `java.security` policy, phân biệt keystore với truststore, phân tích certificate chain và dựng quy trình khắc phục an toàn trên JDK mục tiêu.

> Nguyên tắc: **không tắt certificate validation, hostname verification hoặc disabled-algorithm constraints để làm một kết nối “xanh”**. Hãy sửa protocol, certificate, truststore hoặc thành phần tích hợp thực sự không đáp ứng yêu cầu.

## 1. TLS handshake làm những gì?

TLS là giao thức giúp client và server thiết lập kênh truyền có xác thực và mã hóa. HTTPS sử dụng TLS để bảo vệ giao tiếp HTTP.

Với một kết nối HTTPS, quy trình khái quát:

```text
Java application / JSSE client
            |
            |  1. TCP connect
            v
TLS server / gateway / reverse proxy
            |
            |  2. ClientHello:
            |     TLS versions, cipher suites,
            |     SNI, supported groups,
            |     signature algorithms, ALPN...
            |
            |  3. ServerHello:
            |     protocol và tham số đàm phán
            |
            |  4. Server certificate chain
            |
            |  5. Client xác minh:
            |     certificate path, trust anchor,
            |     validity, key usage, algorithms,
            |     hostname / endpoint identity
            |
            |  6. Nếu mTLS: client cũng xuất trình
            |     certificate và chứng minh có private key
            |
            |  7. Key establishment / Finished
            v
         TLS session
            |
            v
        HTTP request
```

Đây là sơ đồ khái niệm, không phải thứ tự chính xác của mọi thông điệp TLS 1.2 và TLS 1.3. TLS 1.3 có định dạng và quy trình handshake khác TLS 1.2, trong đó nhiều thông điệp sau ServerHello đã được mã hóa. Điều quan trọng là xác định **giai đoạn lỗi**.

### 1.1. Handshake fail không giống lỗi HTTP

Nếu TLS handshake thất bại, ứng dụng thường **chưa gửi được HTTP request** và sẽ không nhận HTTP status `401`, `403` hay `500` theo cách thông thường.

Ngược lại, HTTP 401 sau handshake thành công có thể là lỗi authorization/application token chứ không phải vấn đề certificate trust.

### 1.2. Các lớp xác minh có thể xảy ra đồng thời

Một certificate chain phải đáp ứng nhiều kiểm tra:

- **Trust:** có đường dẫn tới một trust anchor được chấp nhận không?
- **Validity:** certificate còn hiệu lực về mặt thời gian không?
- **Identity:** certificate có phù hợp hostname/endpoint không?
- **Usage:** Key Usage/Extended Key Usage có phù hợp TLS server hoặc client không?
- **Algorithm:** chữ ký, public key size/curve có đáp ứng security policy không?
- **Revocation:** nếu môi trường bật kiểm tra thu hồi, trạng thái OCSP/CRL có hợp lệ không?

Chúng là các điều kiện riêng. **Import CA vào truststore không tự sửa certificate hết hạn hoặc thuật toán yếu**.

## 2. Ba nhóm nguyên nhân cốt lõi

| Nhóm | Dấu hiệu điển hình | Phạm vi kiểm tra | Hướng xử lý chính |
|---|---|---|---|
| Protocol/cipher negotiation | `protocol_version`, `handshake_failure`, `No appropriate protocol` | TLS versions, cipher suites, signature schemes, supported groups | Nâng TLS stack ở client/server, chọn cấu hình chung được phép |
| Thuật toán/khóa bị hạn chế | `Algorithm constraints check failed`, cảnh báo key size/signature | `jdk.tls.disabledAlgorithms`, `jdk.certpath.disabledAlgorithms`, certificate/key | Cấp lại certificate/key, thay thuật toán hoặc provider được hỗ trợ |
| Truststore/certificate path | `PKIX path building failed`, `unable to find valid certification path` | Truststore thực tế, chain, CA, intermediates, hostname | Cấu hình truststore/chain đúng, kiểm chứng CA qua kênh tin cậy |

Ngoài ba nhóm chính, mTLS tạo thêm **chiều xác thực client**. Một lỗi do server không tin client certificate không nên được xử lý bằng cách sửa truststore mà client dùng để tin server.

### 2.1. Triệu chứng một lỗi có thể thay đổi sau khi “sửa tạm”

Ví dụ server chỉ dùng TLS 1.0 và certificate đã hết hạn:

1. JDK mới chặn TLS 1.0, nên handshake fail ngay ở negotiation.
2. Quản trị viên bật TLS 1.2 cho server.
3. Client đi xa hơn trong handshake rồi báo certificate expired.

Điều này không có nghĩa nâng TLS 1.2 tạo ra lỗi certificate; nó cho thấy **nhiều lớp vấn đề tồn tại đồng thời**.

## 3. Cần xác định đúng JDK và đường kết nối

Trước khi điều tra truststore, phải biết **JVM thật sự mở kết nối**.

### 3.1. Build JVM khác runtime JVM

Một hệ thống có thể có:

```text
Developer IDE:      JDK 21
Gradle daemon:      JDK 17
Java compiler:      JDK 21, --release 11
JUnit test worker:  JDK 17
Production image:   JDK 11
```

Khi lỗi phát sinh trong production, `java -version` trên laptop không cho biết chính sách TLS của process production.

Chạy trong **đúng container/process/environment**:

```bash
java -version
```

Ghi:

- JDK vendor/distribution.
- Full version và update.
- `java.home` được ứng dụng sử dụng.
- Application server hoặc launcher.
- Container image digest.
- Custom runtime image nếu dùng `jlink`.
- Các JVM system properties có liên quan.

### 3.2. JVM không nhất thiết truy cập thẳng tới server đích

Một request có thể đi qua:

```text
Java client
    |
    v
Corporate outbound proxy
    |
    v
Service mesh egress
    |
    v
Public API gateway / load balancer
    |
    v
Backend service
```

TLS có thể được kết thúc tại nhiều điểm; certificate mà Java nhìn thấy có thể là certificate do proxy/gateway cung cấp, không phải certificate của backend.

Cần ghi:

- Hostname và port thực sự.
- DNS resolution.
- SNI hostname.
- Proxy settings và `HTTPS_PROXY`/cấu hình client library.
- Load balancer hoặc service mesh.
- Có TLS termination / re-encryption ở đâu.
- Endpoint của test có giống production không.

Không chép nguyên production certificates, passwords hoặc private keys vào bug report công khai.

## 4. JSSE và các loại trust material

Java thường triển khai TLS qua **Java Secure Socket Extension (JSSE)**. Các lớp liên quan thuộc Java SE, ví dụ:

```java
javax.net.ssl.SSLContext
javax.net.ssl.SSLSocket
javax.net.ssl.SSLHandshakeException
javax.net.ssl.TrustManager
javax.net.ssl.KeyManager
```

Dù ứng dụng chuyển từ Java EE sang Jakarta EE, **`javax.net.ssl.*` vẫn là Java SE API**, không đổi thành `jakarta.net.ssl.*`.

### 4.1. Truststore: client tin ai?

Truststore chứa chứng chỉ/trust anchors mà một phía dùng để xác minh chứng chỉ của phía kia.

Đối với HTTPS thông thường:

```text
Java HTTPS client
  |
  +--> Truststore của client:
         CA gốc hoặc trust anchor được phê duyệt
         dùng xác minh certificate chain của server
```

Java không cần có certificate riêng của server trong truststore nếu server certificate có chain hợp lệ đến một CA mà truststore đã tin cậy.

### 4.2. Keystore: mình là ai?

Keystore thường chứa private key và certificate chain của **chính bên kết nối**.

Với mTLS:

```text
Client keystore:
  private key của client
  client certificate và chain cần gửi

Client truststore:
  CA/trust anchor để xác minh server
```

Phía server cũng có hai vai trò:

```text
Server keystore:
  private key + server certificate/chain

Server truststore (khi mTLS):
  trust anchors để xác minh client certificates
```

Một file PKCS#12 có thể chứa cả key entries và trusted certificates, nhưng **vai trò logic vẫn khác nhau**. Đặt property sai mục đích có thể gây lỗi khó hiểu.

### 4.3. Default truststore không phải lúc nào cũng giống hệ điều hành

Trong nhiều JDK/JSSE cấu hình thông thường, mặc định JVM dùng các truststore liên quan đến runtime như `jssecacerts` nếu tồn tại theo quy tắc lựa chọn, hoặc `cacerts` của JDK.

Một số vendor/provider có tích hợp trust với OS hoặc cấu hình riêng. Không nên giả định rằng:

- Chrome truy cập thành công nên Java phải truy cập được.
- CA đã import vào Windows Certificate Store nên mọi JVM tự dùng CA đó.
- CA đã thêm vào JDK trên máy developer cũng có trong container.
- Nâng JDK nhưng truststore `cacerts` tự giữ mọi CA nội bộ cũ.

Phải xác định **TrustManagerFactory và truststore thực tế của process gây lỗi**.

## 5. Các property cấu hình truststore và keystore

Những system properties JSSE phổ biến:

| Property | Vai trò |
|---|---|
| `javax.net.ssl.trustStore` | Đường dẫn truststore dùng bởi default JSSE trust managers trong cấu hình phù hợp |
| `javax.net.ssl.trustStoreType` | Kiểu truststore, ví dụ `PKCS12`, `JKS` |
| `javax.net.ssl.trustStorePassword` | Password để mở/kiểm tra truststore khi cần |
| `javax.net.ssl.keyStore` | Đường dẫn keystore chứa key/certificate của chính client |
| `javax.net.ssl.keyStoreType` | Kiểu keystore |
| `javax.net.ssl.keyStorePassword` | Password keystore khi cần |
| `https.protocols` | Protocols dùng bởi một số HTTPS client implementations, phạm vi tùy API |
| `jdk.tls.client.protocols` | Chỉ định default client protocols cho JSSE trong ngữ cảnh hỗ trợ |

Ví dụ client sử dụng một truststore dành riêng cho ứng dụng:

```bash
java \
  -Djavax.net.ssl.trustStore=/etc/my-app/truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar my-app.jar
```

Thông thường còn cần cơ chế cấp password an toàn cho file nếu truststore cần password. **Không đưa password vào shell command, history, CI logs hoặc tài liệu mẫu như giá trị thật.**

### 5.1. Custom truststore có thể làm mất trust anchors mặc định

Nếu ứng dụng đặt:

```text
-Djavax.net.ssl.trustStore=/etc/my-app/partners.p12
```

và file chỉ chứa một CA nội bộ, một số HTTPS kết nối tới public services có thể bắt đầu báo `PKIX path building failed`.

Lý do: cấu hình một custom truststore theo default JSSE trust management **không tự động bảo đảm hợp nhất** nội dung với `cacerts` mặc định.

Cần thiết kế truststore ứng dụng chứa đầy đủ trust anchors được phê duyệt hoặc cấu hình một trust management strategy rõ ràng. Không viết `X509TrustManager` chấp nhận mọi certificate để “merge nhanh”.

### 5.2. Sai đường dẫn hoặc loại store

Ví dụ:

```text
javax.net.ssl.trustStore=/opt/old-jdk/lib/security/cacerts
```

Nhưng container không có file đó. JSSE có thể thất bại khi khởi tạo trust material hoặc sử dụng danh sách trust anchors không như kỳ vọng tùy implementation/cấu hình.

Cần kiểm tra:

- File có tồn tại trong **container/process filesystem** không?
- Process user có quyền đọc không?
- File có đúng JKS/PKCS12 format không?
- Password có hợp lệ không?
- Truststore có những aliases/trust anchors nào?
- Ứng dụng có dùng custom `SSLContext` bỏ qua system properties không?

### 5.3. Đặt system property quá muộn có thể không hiệu lực

Một thư viện HTTP có thể đã khởi tạo và cache `SSLContext` hoặc `SSLSocketFactory` trước khi ứng dụng gọi:

```java
System.setProperty("javax.net.ssl.trustStore", "...");
```

Khi đó thay property sau startup chưa chắc cập nhật trust managers đã tạo. Ưu tiên cấu hình từ **thời điểm khởi động** hoặc tạo explicit `SSLContext` theo thư viện đang dùng, rồi khởi tạo lại client khi đổi cấu hình.

Không thử sửa late property rồi kết luận JVM bỏ qua truststore nếu chưa xác định lifecycle.

## 6. Kiểm tra security policies trong JDK đang chạy

Ngoài truststore, JDK kiểm soát một số thuật toán/giao thức qua security properties thường nằm trong `java.security`, ở JDK hiện đại hay đặt dưới `conf/security`.

Các property quan trọng:

| Security property | Kiểm soát điển hình |
|---|---|
| `jdk.tls.disabledAlgorithms` | Thuật toán, protocol và ràng buộc khi JSSE/TLS đàm phán |
| `jdk.certpath.disabledAlgorithms` | Ràng buộc khi xác thực certificate path |
| `jdk.security.legacyAlgorithms` | Gắn nhãn legacy trong một số công cụ/ngữ cảnh; không đồng nghĩa cấm tuyệt đối |
| `jdk.jar.disabledAlgorithms` | Chính sách chữ ký JAR, **không phải property xử lý handshake HTTPS** |
| `crypto.policy` | Chính sách độ mạnh JCE, khác algorithm constraints của certpath/TLS |

### 6.1. Đọc đúng giá trị có hiệu lực bằng Java

```java
import java.security.Security;

public final class JdkSecuritySnapshot {
    public static void main(String[] args) {
        print("jdk.tls.disabledAlgorithms");
        print("jdk.certpath.disabledAlgorithms");
        print("jdk.security.legacyAlgorithms");
        print("crypto.policy");
    }

    private static void print(String key) {
        System.out.println(key + " = " + Security.getProperty(key));
    }
}
```

Chạy bằng **đúng runtime JDK gây lỗi**:

```bash
javac JdkSecuritySnapshot.java
java JdkSecuritySnapshot
```

Nếu compiler không có trong runtime image rút gọn, có thể compile trước bằng JDK tương thích rồi chạy class đó trên image cần khảo sát. Không yêu cầu sửa image production chỉ để compile công cụ chẩn đoán.

### 6.2. Vì sao `Security.getProperty` khác `System.getProperty`?

Security properties có cơ chế nạp riêng, thường dùng:

```java
Security.getProperty("jdk.tls.disabledAlgorithms");
```

Trong khi các JVM system properties như đường dẫn truststore thường dùng:

```java
System.getProperty("javax.net.ssl.trustStore");
```

Đừng đọc nhầm một loại rồi kết luận property không tồn tại.

### 6.3. Một constraint có thể đi kèm điều kiện

Cấu hình disabled algorithms có thể chứa biểu thức như:

```text
RSA keySize < 2048
```

Đây là **ví dụ dạng cú pháp**, không khẳng định mọi JDK đặt ngưỡng này cho mọi loại key hoặc usage. Một số constraints còn xét trust anchor, usage hoặc thời điểm.

Cần lưu **vendor, full JDK update và security properties thực tế**, bởi các bản vá JDK có thể siết mặc định mà không đổi major version.

## 7. TLS version cũ và `No appropriate protocol`

TLS 1.0 và TLS 1.1 đã lỗi thời và bị vô hiệu hóa theo mặc định trong nhiều JDK cập nhật hiện đại. Server chỉ hỗ trợ những protocol này có thể không còn tương thích với Java client mới.

Ví dụ lỗi:

```text
javax.net.ssl.SSLHandshakeException:
    Received fatal alert: protocol_version
```

hoặc:

```text
javax.net.ssl.SSLHandshakeException:
    No appropriate protocol
    (protocol is disabled or cipher suites are inappropriate)
```

Không thể chắc chắn server chỉ hỗ trợ TLS 1.0 chỉ từ message. Cũng có thể không có cipher suites chung, cấu hình client vô tình loại TLS 1.2/1.3 hoặc server/proxy trả alert do policy.

### 7.1. Các bước điều tra

1. Xác định endpoint sau proxy, hostname và port.
2. Kiểm tra default enabled protocols của JSSE client và chính sách `jdk.tls.disabledAlgorithms`.
3. Kiểm tra supported protocols/ciphers của server hoặc TLS terminator.
4. So sánh handshake log để xem `ClientHello`, `ServerHello` hoặc fatal alert.
5. Nâng TLS stack của bên quá cũ theo chính sách hỗ trợ.
6. Kiểm tra lại certificate, trust chain và key sizes sau khi negotiation đã thành công.

### 7.2. Chỉ bật protocol trong code không vượt policy

Ví dụ:

```java
sslSocket.setEnabledProtocols(new String[] { "TLSv1.2" });
```

Đây là cấu hình enabled protocols cho socket, **không buộc JSSE bỏ qua** `jdk.tls.disabledAlgorithms`. Nếu protocol hoặc thuật toán bị chặn, phải giải quyết security policy và khả năng tương tác của cả hai phía.

### 7.3. Vì sao không mở lại TLS 1.0 toàn cục?

Hạ policy của JVM có thể làm yếu các kết nối khác vốn đang dùng TLS hiện đại. Nếu đối tác chưa thể nâng, cần một kế hoạch chuyển tiếp được đánh giá rủi ro, cô lập network/process, giám sát và thời hạn thay thế, không âm thầm bật TLS cũ cho toàn hệ thống.

Một gateway chuyển đổi có thể giới hạn vùng rủi ro, nhưng đoạn kết nối legacy vẫn sử dụng protocol yếu; nó không bỗng trở thành an toàn.

## 8. Cipher suites, signature algorithms và supported groups

Handshake không chỉ thống nhất TLS version. Client và server cần đàm phán các tham số phù hợp: cipher suites, key-exchange groups và signature schemes, tùy TLS version.

### 8.1. TLS 1.2 so với TLS 1.3

Trong TLS 1.2, cipher suite names thường thể hiện nhiều thành phần như key exchange, authentication và encryption. Trong TLS 1.3, cipher suite chủ yếu xác định AEAD/hash; signature scheme và key establishment được thương lượng ở extensions riêng.

Ví dụ TLS 1.3 cipher suite:

```text
TLS_AES_128_GCM_SHA256
```

Không nên suy rằng chỉ cần có cipher suite trên thì server certificate RSA/ECDSA hay named group nào cũng được chấp nhận. Cần kiểm tra signature algorithms và supported groups nếu handshake fail ở giai đoạn đó.

### 8.2. Thiết bị cũ chỉ hỗ trợ cipher yếu

Một gateway lâu năm có thể chỉ hỗ trợ RC4, 3DES hoặc cipher suite đã bị chính sách hiện đại vô hiệu hóa. Nâng client Java có thể làm lộ lỗi không có cipher chung.

Hướng bền vững là nâng TLS endpoint, certificate/key và lựa chọn cipher an toàn được cả hai phía hỗ trợ, không ép client khôi phục cipher yếu.

### 8.3. `handshake_failure` không chỉ ra một nguyên nhân duy nhất

Alert `handshake_failure` có thể do:

- Không có cipher/protocol chung.
- Signature scheme không tương thích.
- Client certificate bắt buộc nhưng không thích hợp.
- Server configuration lỗi.
- Policy của proxy, WAF hoặc load balancer.
- Khác biệt SNI/ALPN hoặc TLS extension negotiation.

Phải đọc **handshake timeline và server logs** trước khi sửa.

## 9. Certificate path, trust anchors và intermediate CA

Một server thường cung cấp chain:

```text
Leaf certificate: api.partner.example
               |
               v
Intermediate CA: Partner Issuing CA
               |
               v
Root CA / trust anchor: Partner Root CA
```

Client cần xây dựng được path hợp lệ tới một trust anchor mà nó chấp nhận.

### 9.1. Server không nhất thiết gửi root CA

Trong TLS thực tế, server thường gửi leaf và intermediate certificates; root CA có thể được bỏ qua vì client đã có root trong truststore.

Vì vậy, “server không gửi root” không tự chứng minh chain bị thiếu. Ngược lại, **thiếu intermediate** thường khiến client không xây được path, đặc biệt nếu intermediate không có sẵn từ nguồn khác theo implementation.

### 9.2. Truststore phải chứa đúng trust anchor

Nếu server chuyển CA mới, một JDK cũ hoặc custom truststore nội bộ có thể chưa có root phù hợp.

Ví dụ:

```text
Ứng dụng A:
  Truststore A có Root CA mới -> pass

Ứng dụng B:
  Truststore B chỉ có Root CA cũ -> PKIX fail
```

Thay Java source không nhất thiết liên quan. Phải cập nhật trust material qua kênh đáng tin cậy và thử lại.

### 9.3. Không import bừa leaf certificate

Import thẳng leaf certificate để “tin cậy server” có thể tạo dạng trust/pinning không mong muốn, giảm khả năng tự động rotate certificate và bỏ qua quy trình CA được phê duyệt.

Đối với kết nối đối tác, cần chọn rõ một trong các chính sách:

- Tin cậy public CA hợp lệ từ truststore được quản lý.
- Tin cậy private enterprise CA được xác minh.
- Dùng certificate/public key pinning nếu được thiết kế có quản lý rotation và fallback.

Không lấy certificate vừa nhận từ một endpoint chưa được xác minh rồi tự động thêm vào truststore. Điều đó có thể hợp thức hóa certificate do một attacker hoặc proxy không được phê duyệt cung cấp.

## 10. `PKIX path building failed`: cách phân tích

Lỗi thường gặp:

```text
javax.net.ssl.SSLHandshakeException:
    PKIX path building failed:
    sun.security.provider.certpath.SunCertPathBuilderException:
    unable to find valid certification path to requested target
```

Đây là dấu hiệu **certificate path builder không tìm được đường hợp lệ tới trust anchor** trong ngữ cảnh đó. Không thể kết luận ngay vì thiếu root CA; còn có thể do intermediate bị thiếu hoặc ràng buộc path.

### 10.1. Những câu hỏi cần trả lời

- Java process đang dùng truststore nào?
- Truststore có CA root/intermediate được phê duyệt không?
- Server gửi những certificates nào với SNI hostname đang sử dụng?
- Certificate chain có đúng thứ tự và issuer/subject linkage không?
- Các CA có được đánh dấu đúng Basic Constraints/Key Usage không?
- Certificate có expired/not yet valid không?
- Có constraints về key size/signature không?
- Có revocation policy được bật không?
- Proxy có thay certificate chain không?

### 10.2. `unable to find valid certification path` khác algorithm constraints

Nếu nested cause có:

```text
java.security.cert.CertPathValidatorException:
    Algorithm constraints check failed ...
```

nên điều tra key size/signature và `jdk.certpath.disabledAlgorithms`.

Nếu nested cause nói:

```text
unable to find valid certification path to requested target
```

nên ưu tiên kiểm tra chain và trust anchors. Hai điều kiện có thể cùng tồn tại; cần đọc đúng dấu hiệu.

### 10.3. Dùng đúng truststore khi so sánh môi trường

Một developer có thể thử bằng `keytool` của JDK 21, trong khi ứng dụng production dùng JDK 11 và custom truststore khác. Hai kết quả khác nhau là điều có thể xảy ra.

Nên đặt đường dẫn và alias của truststore trong báo cáo, không chỉ ghi “đã import CA”.

## 11. Thuật toán bị vô hiệu hóa trong certificate chain

JDK mới có thể từ chối một certificate sử dụng chữ ký hoặc public key không đáp ứng policy hiện tại.

Các trường hợp legacy:

- RSA key quá ngắn.
- Chữ ký SHA-1 bị hạn chế trong một ngữ cảnh cụ thể.
- DSA/EC parameters hoặc curves không được hỗ trợ.
- Intermediate CA có signature algorithm yếu.
- TLS signature scheme không tương thích giữa hai đầu.

### 11.1. Key size cần đánh giá theo thuật toán

Không so sánh AES-256, RSA-256 và EC P-256 chỉ bằng số bit. RSA 1024 bit không còn phù hợp cho nhiều mục đích bảo mật hiện đại; RSA 2048/3072 bit hoặc EC trên named curve được hỗ trợ thường được cân nhắc theo chính sách và nhu cầu tương tác.

**Ngưỡng cụ thể phải đọc từ policy của JDK và tiêu chuẩn tổ chức.** Không giả định một security property có giá trị giống nhau ở mọi vendor/update.

### 11.2. SHA-1 có thể còn hiện diện ở API nhưng bị chặn ở một usage

Java có thể vẫn cung cấp:

```java
java.security.MessageDigest.getInstance("SHA-1");
```

để xử lý dữ liệu legacy, trong khi certpath validator giới hạn certificate signatures SHA-1 theo điều kiện riêng.

**Thuật toán có implementation không đồng nghĩa được phép trong TLS certificate validation.**

### 11.3. Đổi truststore không tự sửa khóa yếu

Nếu leaf hoặc intermediate certificate có key/signature không đạt policy, chỉ import thêm issuer CA có thể chưa giải quyết được. Cần tạo key pair phù hợp, cấp lại certificate/chain hoặc nâng endpoint.

### 11.4. Đừng sửa toàn bộ `java.security` để qua test

Việc hạ `jdk.certpath.disabledAlgorithms` hoặc `jdk.tls.disabledAlgorithms` có thể làm yếu các kết nối khác cùng JVM. Nếu cần ngoại lệ tạm thời vì hệ thống legacy chưa nâng được, phải có phê duyệt, phân vùng riêng, audit và ngày loại bỏ.

## 12. Hostname verification và chứng chỉ sai danh tính

Một kết nối có thể có chain được tin cậy nhưng vẫn bị từ chối vì certificate không dành cho hostname mà client đang gọi.

Ví dụ:

```text
URL gọi:      https://orders.partner.example
Certificate:  DNS:api.partner.example
```

Nếu SAN không có tên phù hợp, HTTPS client đúng chuẩn phải từ chối endpoint identity.

Thông báo có thể dạng:

```text
No subject alternative DNS name matching
orders.partner.example found.
```

hoặc exception khác bao bọc lỗi endpoint identification.

### 12.1. Trust CA không thay hostname match

Thêm certificate vào truststore không làm SAN đổi theo hostname. Cần sửa URL/SNI hoặc cấp lại certificate có SAN phù hợp.

### 12.2. Kết nối bằng IP dễ phát sinh mismatch

Nếu certificate có DNS name `api.partner.example` nhưng client kết nối:

```text
https://10.0.0.25
```

hostname verification theo IP có thể thất bại nếu certificate không chứa IP SAN phù hợp.

Không tắt hostname verification. Dùng DNS hostname đúng hoặc cấp certificate bao gồm danh tính endpoint được sử dụng.

### 12.3. SNI và virtual hosts

Khi một IP phục vụ nhiều TLS sites, client gửi **Server Name Indication (SNI)** để server/gateway chọn certificate và cấu hình tương ứng.

Nếu app dùng IP hoặc custom TLS client không gửi SNI phù hợp, server có thể trả default certificate thuộc hostname khác.

Trong debug cần kiểm tra:

- Hostname được truyền cho `SSLSocket`/HTTP client.
- SNI extension trong `ClientHello`.
- Certificate thực sự server gửi.
- Proxy/load balancer chọn virtual host nào.

Không kết luận server cấu hình sai chỉ từ một lệnh thử không có SNI.

## 13. mTLS: phía client cũng cần certificate riêng

Trong **mutual TLS**, server xác thực client bằng certificate ngoài việc client xác thực server.

```text
Client Java                            Server
    |                                    |
    |<------ Server certificate ----------|
    | Validate server using truststore   |
    |                                    |
    |------- Client certificate --------->|
    |   lấy từ client keystore            |
    |                                    |
    |<------ Server validates client -----|
    |   bằng server-side trust config     |
```

Một lỗi mTLS có thể xuất hiện trên phía client với alert:

```text
Received fatal alert: bad_certificate
```

hoặc:

```text
Received fatal alert: unknown_ca
```

Thông báo alert nhìn từ client **có thể cho biết server đã từ chối client certificate**, chứ không nhất thiết client không tin server.

### 13.1. Các mục cần kiểm tra ở client

- Keystore có `PrivateKeyEntry` với client key/certificate phù hợp không?
- Alias/key selection có đúng identity mong muốn không?
- Certificate chain của client có đầy đủ cần thiết không?
- Key password/keystore password và type có đúng không?
- Certificate có clientAuth EKU và Key Usage phù hợp không?
- Key algorithm/signature được TLS server hỗ trợ không?
- Client có gửi certificate khi server yêu cầu không?
- Đường đi qua proxy có thay đổi nơi mTLS diễn ra không?

### 13.2. Các mục cần kiểm tra ở server

- Server có tin CA phát hành client certificate không?
- Server có giới hạn acceptable issuers/client identities không?
- Server có chính sách key size, signature algorithm hoặc revocation khác không?
- Certificate mapping sang user/service identity có đúng không?
- Truststore server đã rotate CA chưa?

### 13.3. Hai truststores phục vụ hai hướng khác nhau

Trong mTLS:

- Client truststore **tin server**.
- Server truststore **tin client**.

Sửa truststore client để chứa client CA không tự giải quyết việc server từ chối client certificate. Phải xác định **bên nào đang phát fatal alert và validator nào đang fail**.

## 14. Bật log TLS đúng cách

JSSE cung cấp logging hỗ trợ điều tra handshake.

Ví dụ:

```bash
java \
  -Djavax.net.debug=ssl,handshake \
  -jar my-app.jar
```

Để xem thêm certificate path debug:

```bash
java \
  -Djavax.net.debug=ssl,handshake \
  -Djava.security.debug=certpath \
  -jar my-app.jar
```

Tùy JDK version, có thể dùng thêm các debug categories để phân tích trust manager/key manager và certificate messages. Hãy chọn mức log phù hợp để không tạo quá nhiều dữ liệu.

### 14.1. Log cần tập trung vào những gì?

- `ClientHello`: protocol/cipher lists, SNI, groups/signature schemes.
- `ServerHello`: negotiated protocol/cipher.
- Certificate chain server gửi.
- CertificateRequest nếu mTLS.
- Những dòng trust manager/certpath và algorithm constraints.
- Fatal alert được gửi hay nhận.
- Nested Java exception và thời điểm xảy ra.
- Hostname/endpoint hiện tại.
- TLS terminator hoặc proxy đã tham gia handshake nào.

### 14.2. Đọc chiều của fatal alert

Phân biệt:

```text
Received fatal alert: ...
```

với:

```text
Fatal ... / Produced fatal alert ...
```

Một alert **nhận từ peer** thường gợi ý peer đã từ chối một bước handshake. Không tự suy rằng truststore Java client có vấn đề nếu server là bên gửi alert.

### 14.3. Bảo mật thông tin trong log

Debug TLS có thể chứa hostname, certificate metadata, cấu hình hệ thống và chi tiết giao tiếp nội bộ. Không ghi hoặc chia sẻ passwords/private keys, session secrets hay token. Không bật logging quá chi tiết kéo dài trong production.

Nếu phải lấy log production, có owner, phạm vi, retention policy và quy trình redaction.

## 15. Kiểm tra certificate server bằng `keytool`

Java JDK cung cấp `keytool`.

### 15.1. Kiểm tra certificate ở file

```bash
keytool -printcert -file server.crt
```

Các trường quan trọng:

- Subject / Issuer.
- Serial number và SHA-256 fingerprint.
- Valid from/to.
- Signature algorithm.
- Subject public key algorithm và key size.
- SAN DNS/IP.
- Basic Constraints, Key Usage, Extended Key Usage.

### 15.2. Kiểm tra TLS endpoint

```bash
keytool -printcert -sslserver api.partner.example:443
```

Lệnh dùng network để lấy thông tin certificate từ endpoint mà nó quan sát được. Kết quả phụ thuộc SNI, proxy, load balancer và đường mạng, nên cần chạy từ môi trường gần với application.

Đừng xem kết quả trên laptop là certificate mà container production chắc chắn nhìn thấy.

### 15.3. Kiểm tra truststore ứng dụng

```bash
keytool -list -v \
  -keystore /etc/my-app/truststore.p12 \
  -storetype PKCS12
```

Công cụ có thể nhắc password nếu cần. Không ghi password trực tiếp trong command shell.

Xác định:

- Alias dự kiến có tồn tại không?
- Entry là trusted certificate hay private key entry?
- Fingerprint có đúng CA đã được phê duyệt không?
- Chứng chỉ còn hạn không?
- Có đúng store path mà JVM sử dụng không?

### 15.4. Kiểm tra JDK default CA store

Có thể dùng tính năng `keytool -list -cacerts` trên JDK hỗ trợ:

```bash
keytool -list -cacerts
```

Nhớ rằng lệnh sử dụng **JDK đang chứa `keytool`**, có thể khác JDK của application process. Đối chiếu đường dẫn `java.home` và lệnh `keytool` trên PATH.

## 16. Kiểm tra TLS bằng OpenSSL: hữu ích nhưng không thay JSSE

Nếu môi trường có OpenSSL:

```bash
openssl s_client \
  -connect api.partner.example:443 \
  -servername api.partner.example \
  -showcerts
```

Lệnh có thể hiển thị chain được server gửi cùng thông tin negotiation. `-servername` giúp yêu cầu đúng SNI virtual host.

Có thể chủ động thử protocol cụ thể theo khả năng OpenSSL/server:

```bash
openssl s_client \
  -connect api.partner.example:443 \
  -servername api.partner.example \
  -tls1_2
```

và:

```bash
openssl s_client \
  -connect api.partner.example:443 \
  -servername api.partner.example \
  -tls1_3
```

### 16.1. Giới hạn của kết quả OpenSSL

OpenSSL và JSSE:

- Có thể dùng trust stores khác nhau.
- Có cipher/support policy khác.
- Có signature/groups/hostname verification defaults khác.
- Có cấu hình proxy/SNI khác.
- Có behavior và phiên bản khác.

Vì vậy, **OpenSSL handshake thành công không chứng minh Java client sẽ thành công**. Nó chủ yếu giúp xác định capability và chain của server.

### 16.2. Kiểm tra hostname/CA với chính sách đúng

Nếu dùng OpenSSL để xác thực chain, cần chỉ định CA bundle/phương thức verification và hostname phù hợp theo bản OpenSSL đang sử dụng. Không xem việc tool in certificates hoặc kết nối TCP thành công là bằng chứng trust validation đã pass.

Trong kết luận migration, ưu tiên **test bằng JSSE client và truststore thực của ứng dụng**.

## 17. Java diagnostic client dùng JSSE mặc định

Một chương trình độc lập có thể thực hiện handshake và in negotiated protocol/cipher, trong khi vẫn áp dụng trust và hostname verification.

```java
import java.util.List;
import javax.net.ssl.SNIHostName;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSession;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

public final class TlsProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java TlsProbe <dns-host> <port>");
        }

        String host = args[0];
        int port = Integer.parseInt(args[1]);

        SSLSocketFactory factory =
                (SSLSocketFactory) SSLSocketFactory.getDefault();

        try (SSLSocket socket =
                (SSLSocket) factory.createSocket(host, port)) {

            SSLParameters parameters = socket.getSSLParameters();

            // Yêu cầu kiểm tra endpoint identity theo HTTPS.
            parameters.setEndpointIdentificationAlgorithm("HTTPS");

            // Chỉ dùng DNS host ở ví dụ này.
            parameters.setServerNames(List.of(new SNIHostName(host)));
            socket.setSSLParameters(parameters);

            socket.startHandshake();

            SSLSession session = socket.getSession();
            System.out.println("Protocol: " + session.getProtocol());
            System.out.println("Cipher suite: " + session.getCipherSuite());
            System.out.println("Peer: " + session.getPeerPrincipal());
        }
    }
}
```

Ví dụ sử dụng Java 11+ APIs. Chạy với đúng JDK và JVM properties của application:

```bash
javac TlsProbe.java
java \
  -Djavax.net.debug=ssl,handshake \
  TlsProbe api.partner.example 443
```

### 17.1. Giới hạn của probe

- Probe này dùng default `SSLSocketFactory`; nếu ứng dụng dùng custom `SSLContext`, custom provider hoặc HTTP client cấu hình riêng, kết quả có thể khác.
- Probe không thực hiện HTTP request/ALPN negotiation đầy đủ như mọi HTTP client.
- Probe giả định DNS hostname hợp lệ cho SNI; không dùng nguyên mẫu với IP hoặc các hostname không hợp lệ.
- Probe không tự mang client certificate nếu keystore/KeyManager chưa được cấu hình thích hợp.
- Đây là công cụ chẩn đoán, không phải bài kiểm thử đầy đủ cho proxy, HTTP/2, auth hoặc mTLS.

**Không xóa `setEndpointIdentificationAlgorithm("HTTPS")` để cho phép certificate sai hostname khi đánh giá HTTPS.** Nếu client thực tế áp dụng endpoint identification khác, phải mô tả khác biệt trong kết luận.

## 18. Kiểm tra config đang dùng, nhưng không in password

Một Java diagnostic có thể in thông tin cấu hình không nhạy cảm:

```java
import java.security.Security;

public final class TlsRuntimeSnapshot {
    public static void main(String[] args) {
        printSystem("java.version");
        printSystem("java.vendor");
        printSystem("java.home");
        printSystem("javax.net.ssl.trustStore");
        printSystem("javax.net.ssl.trustStoreType");
        printSystem("javax.net.ssl.keyStore");
        printSystem("javax.net.ssl.keyStoreType");

        printSecurity("jdk.tls.disabledAlgorithms");
        printSecurity("jdk.certpath.disabledAlgorithms");
    }

    private static void printSystem(String name) {
        System.out.println(name + " = " +
                System.getProperty(name, "<not set>"));
    }

    private static void printSecurity(String name) {
        System.out.println(name + " = " + Security.getProperty(name));
    }
}
```

Không in `javax.net.ssl.trustStorePassword` hoặc `javax.net.ssl.keyStorePassword`, kể cả ở môi trường test nếu log được lưu lâu dài.

### 18.1. `trustStore` không set không có nghĩa không có truststore

Khi `javax.net.ssl.trustStore` không được khai báo, JSSE có thể áp dụng logic tìm truststore mặc định. Vì vậy dòng:

```text
javax.net.ssl.trustStore = <not set>
```

không có nghĩa client chấp nhận mọi certificate hoặc không xác thực CA.

### 18.2. Custom SSLContext có thể không sử dụng các property này

Một HTTP client library có thể nạp truststore trong code:

```java
SSLContext context = ...
```

hoặc sử dụng một security provider riêng. Trong trường hợp đó, JVM system property chỉ cho biết cấu hình môi trường, chưa chứng minh context thực tế dùng store nào. Cần xem cách client được tạo.

## 19. Thao tác truststore đúng cách và an toàn

Khi đã xác nhận một private CA hợp lệ chưa có trong truststore, có thể cân nhắc thêm CA certificate đã được xác minh:

```bash
keytool -importcert \
  -alias approved-partner-ca \
  -file approved-partner-ca.crt \
  -keystore /etc/my-app/truststore.p12 \
  -storetype PKCS12
```

Công cụ có thể yêu cầu password và xác nhận trust. Ví dụ giả định đường dẫn và CA certificate đã được tổ chức phê duyệt.

### 19.1. Xác minh fingerprint từ nguồn tin cậy

Trước khi import, kiểm tra fingerprint SHA-256 của CA từ một kênh độc lập và đáng tin cậy:

```bash
keytool -printcert -file approved-partner-ca.crt
```

Không tự động nhập một certificate lấy ngay từ kết nối đang bị lỗi trust mà không xác minh bên ngoài; đây là lỗi tin cậy vòng tròn.

### 19.2. Hạn chế sửa `cacerts` toàn JDK

Nếu ứng dụng cần tin cậy một CA nội bộ, ưu tiên application-owned trust material hoặc giải pháp quản lý certificate của tổ chức. Sửa `cacerts` global có thể:

- Ảnh hưởng mọi ứng dụng dùng chung runtime.
- Bị mất khi thay container image/JDK update.
- Khó audit ai đã thêm CA.
- Khó tái hiện trên CI và production.

Việc cập nhật truststore phải nằm trong quy trình triển khai và quản lý certificate, không thao tác thủ công trên một container đang chạy rồi bỏ quên.

### 19.3. Certificate rotation cần có cửa sổ tương thích

Khi CA đối tác đổi, nên phối hợp:

1. Phát hành truststore hỗ trợ CA mới trước khi server đổi certificate, nếu chính sách cho phép.
2. Kiểm tra toàn bộ JVM instances đã nhận trust material mới.
3. Chuyển server certificate/chain theo lịch.
4. Theo dõi handshake failures.
5. Chỉ loại CA cũ sau khi không còn endpoint hợp lệ cần nó.

Nếu root cũ bị thu hồi vì sự cố bảo mật, lịch trình phải theo đánh giá rủi ro; không giữ trust cũ chỉ để thuận tiện rollback.

## 20. Tình huống A: Java 8 kết nối được, Java 17 báo lỗi protocol

Giả sử:

```text
Java client JDK 8 (bản cũ) ---- TLS 1.0 ----> Device gateway
Java client JDK 17 ---------- X -----------> Device gateway
```

Cách điều tra:

1. Ghi full JDK 8/17 update và security properties, không chỉ major version.
2. Bật JSSE handshake logging trên JDK 17.
3. Xem có `ClientHello` nào được gửi và protocol/ciphers đề xuất.
4. Kiểm tra server capability từ cấu hình hoặc OpenSSL.
5. Xác định nó có thể bật TLS 1.2/1.3 và cipher hiện đại hay không.
6. Nâng endpoint/firmware/proxy trước.
7. Chạy lại Java client trên JDK mục tiêu.
8. Sau negotiation, kiểm tra tiếp certificate chain/hostname.

**Không hạ JDK hoặc bật lại TLS 1.0 global làm cách xử lý mặc định.** Nếu thiết bị chưa thể thay, cần có giải pháp cô lập được đánh giá rủi ro.

## 21. Tình huống B: Server cấp lại chứng chỉ, Java báo PKIX

Giả sử server vừa đổi từ CA nội bộ A sang CA nội bộ B:

```text
Server leaf mới -> Intermediate B -> Root B

Client truststore cũ:
  Root A
```

JVM chưa tin Root B, nên certificate path builder không tìm được đường hợp lệ.

Cách xử lý:

1. Xác định đúng truststore của Java process.
2. Kiểm tra server chain ở hostname/SNI tương ứng.
3. Xác minh Root B và Intermediate B qua kênh tin cậy.
4. Cập nhật trust material được phê duyệt trong release/container config.
5. Reload/restart client khi cần theo lifecycle SSLContext.
6. Kiểm tra server hostname SAN, validity, usage và algorithm policy.
7. Test đầy đủ trên cả staging và production deployment path.

Không tự import từng leaf certificate vào `cacerts` của mọi máy.

## 22. Tình huống C: Chain đúng nhưng RSA key quá ngắn

Giả sử:

```text
Server:
  Certificate public key: RSA 1024 bit

Client JDK mới:
  CertPathValidatorException:
    Algorithm constraints check failed...
```

Một số policy hiện đại từ chối RSA 1024 bit trong ngữ cảnh TLS/certpath. Trường hợp này:

- Thêm root CA có thể không khắc phục.
- Đổi keystore password không liên quan.
- `TrustManager` luôn true sẽ vô hiệu hóa xác thực và nguy hiểm.
- Hạ disabled-algorithm policy toàn cục làm tăng rủi ro.

Cách đúng thường là **tạo key pair mới, cấp lại certificate với key size/algorithm đáp ứng chính sách, cấu hình full chain và kiểm thử hai đầu**.

Ví dụ lệnh tạo key pair để minh họa:

```bash
keytool -genkeypair \
  -alias tls-server \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -storetype PKCS12 \
  -keystore server-keystore.p12 \
  -validity 365
```

Lệnh tạo certificate tự ký ban đầu theo cách `keytool` hoạt động; nó không tự trở thành certificate production được tin cậy. Cần CSR, CA, SAN, usage và quy trình phát hành phù hợp.

## 23. Tình huống D: Java client mTLS báo `bad_certificate`

Một ứng dụng gọi API ngân hàng qua mTLS. Sau khi chuyển sang container mới, outbound call nhận:

```text
javax.net.ssl.SSLHandshakeException:
    Received fatal alert: bad_certificate
```

Có thể server đã từ chối certificate của client. Kiểm tra:

1. Client process có load đúng keystore PKCS12/JKS không?
2. Keystore có private key entry và chain không?
3. Alias được chọn có đúng business identity không?
4. Có key password/permissions hoặc HSM token lỗi không?
5. Certificate có hết hạn, bị revoke hoặc không có clientAuth EKU không?
6. Server có tin CA của client và chấp nhận signature algorithms không?
7. Có proxy terminator nào làm thay đổi mTLS flow không?
8. Server log xác thực client nói gì?

**Đừng sửa truststore tin server khi bằng chứng cho thấy server không tin client identity.**

### 23.1. Keystore và truststore có thể cùng ở một PKCS12 file

Điều đó hợp lệ khi được thiết kế, nhưng các properties và KeyManager/TrustManager vẫn phải sử dụng đúng entries. Một file có `trustedCertEntry` mà không có `PrivateKeyEntry` không đủ để chứng minh client sở hữu private key phục vụ mTLS.

## 24. Tình huống E: Browser và curl thành công nhưng Java thất bại

Một người dùng thử:

```text
Chrome: PASS
curl: PASS
Java: SSLHandshakeException
```

Những khả năng cần xem:

- Browser/curl dùng OS truststore hoặc CA bundle khác JVM.
- `curl` đang dùng proxy khác Java.
- JVM có custom truststore thiếu public CA.
- JSSE security policy khác TLS library của curl.
- Java HTTP client không gửi cùng SNI/ALPN/protocol.
- Java process trong container có DNS route khác.
- Client sử dụng certificate mTLS riêng mà browser không dùng.

Cách điều tra:

1. Ghi chính xác host/port/route của cả ba clients.
2. Kiểm tra certificate chain quan sát được qua từng đường.
3. So sánh trust anchors và TLS protocols.
4. Thử bằng Java JSSE probe với default/cấu hình client thực.
5. Kết luận dựa trên log Java và server, không dựa vào việc browser hiển thị ổ khóa.

## 25. Tình huống F: Chỉ một container pod lỗi sau nâng image

Giả sử 9/10 pods kết nối API được, pod mới sau rollout báo PKIX.

Điều tra theo biến khác biệt:

- Image digest và JDK update.
- Truststore file mounted vào container.
- Kubernetes Secret/ConfigMap version và mount path.
- File permissions, symbolic links và read-only mounts.
- Environment variables và JVM flags.
- Service mesh sidecar/proxy configuration.
- Thời điểm process khởi động và SSLContext cache.
- DNS resolution, egress policy và node network.

Có thể một pod vẫn chạy bản cũ có truststore chứa CA mới do workaround thủ công, còn image mới sạch không có certificate đó. Cần đưa trust material vào **configuration được quản lý**, không “sửa” từng pod.

## 26. Quy trình chẩn đoán có thứ tự

### Bước 1 — Ghi exception đầy đủ

Không chỉ lưu dòng `SSLHandshakeException`. Cần:

- Stack trace và nested causes.
- Fatal alert direction.
- Time, release version và endpoint.
- Java process/runtime JDK version.
- Có proxy hoặc mTLS không.

### Bước 2 — Xác định handshake đã đi tới đâu

Từ JSSE debug:

- Không có TCP connection: điều tra network/DNS trước.
- Chưa có ServerHello: protocol/cipher/SNI/gateway.
- Đã nhận certificate: trust chain, hostname, algorithm, usage.
- Đã có CertificateRequest: mTLS client identity.
- Đã hoàn thành TLS mà HTTP lỗi: chuyển sang application/auth diagnostics.

Đây là hướng phân loại, không phải mô hình handshake đầy đủ cho mọi TLS version.

### Bước 3 — Chụp security properties

Đọc `jdk.tls.disabledAlgorithms`, `jdk.certpath.disabledAlgorithms`, vendor/update. Không chỉnh policy trước khi có bằng chứng.

### Bước 4 — Kiểm tra truststore thực tế

Xác định path/type và CA entries mà TrustManager đang dùng. Xác nhận không bị custom truststore làm mất roots mặc định.

### Bước 5 — Kiểm tra server certificate chain

Dùng `keytool`, OpenSSL và server-side configuration. Chú ý SNI, proxy, SAN, intermediates, key size, validity.

### Bước 6 — Kiểm tra client identity nếu mTLS

Đọc client keystore, private key alias, client chain, EKU và server trust policy. Tách lỗi server trust và client trust.

### Bước 7 — Sửa đúng bên

- TLS negotiation lỗi: nâng server/client TLS stack.
- Weak certificate/key: rotate key và cấp lại certificate.
- Trust anchor thiếu: cập nhật truststore được phê duyệt.
- Missing intermediate: sửa chain server gửi.
- Hostname mismatch: sửa DNS/URL hoặc SAN.
- Client certificate bị từ chối: sửa mTLS keystore, chain hoặc server trust mapping.
- Proxy/SNI sai: sửa routing hoặc hostname handling.

### Bước 8 — Kiểm thử bằng JVM và artifact thật

Chạy trên đúng runtime image, proxy path và HTTP client của sản phẩm. Một JDK probe đơn giản giúp khoanh vùng, nhưng integration test mới xác nhận toàn bộ luồng hoạt động.

### Bước 9 — Ghi lại trạng thái sau sửa

Lưu JDK version, security properties, endpoint, issuer/fingerprints (không lưu secrets), truststore version, negotiated protocol và test outcome.

## 27. Bảng tra nhanh lỗi thường gặp

| Log/exception | Định hướng ban đầu | Không nên kết luận vội |
|---|---|---|
| `Received fatal alert: protocol_version` | Peer từ chối protocol | Chắc chắn chỉ do TLS 1.0 |
| `No appropriate protocol` | Protocol/cipher bị tắt hoặc không phù hợp | Chỉ cần set `TLSv1.2` trong code |
| `handshake_failure` | Không có tham số phù hợp hoặc peer policy | Chỉ do certificate root |
| `PKIX path building failed` | Không xây được trust path | Chắc chắn chỉ thiếu root CA |
| `unable to find valid certification path` | Truststore/chain/certpath | Import leaf bừa là đủ |
| `Algorithm constraints check failed` | Key/signature/policy không đạt | Thêm CA luôn sửa được |
| `certificate expired` | Validity không hợp lệ | Chỉ cần đổi truststore |
| `No subject alternative DNS name matching` | Endpoint identity/SAN mismatch | Tắt hostname verification |
| `Received fatal alert: bad_certificate` | Peer không chấp nhận cert/handshake step | Chỉ có client truststore sai |
| `Received fatal alert: unknown_ca` | Peer không tin CA của cert nhận được | Chắc chắn Java thiếu root server |
| `UnrecoverableKeyException` | Private key/password/keystore issue | Chỉ do certificate server |
| `Keystore was tampered with, or password was incorrect` | Store/password/type hoặc file | Chỉ do TLS protocol |
| `NoSuchAlgorithmException` | Provider/algorithm availability | Mọi thuật toán cùng tên bị cấm trong TLS |
| `SSLPeerUnverifiedException` | Peer identity chưa được xác thực | Chắc chắn lỗi CA |
| `Connection reset` trước TLS complete | Network/proxy/server đóng socket | Chỉ có truststore sai |

Bảng này là **hướng điều tra**, không phải ánh xạ một lỗi sang đúng một nguyên nhân. Cần đọc nguyên stack trace và handshake log.

## 28. Những workaround nguy hiểm cần tránh

### 28.1. TrustManager tin mọi certificate

Một ví dụ anti-pattern thường thấy:

```java
@Override
public void checkServerTrusted(
        java.security.cert.X509Certificate[] chain,
        String authType) {
    // KHÔNG LÀM: chấp nhận mọi certificate.
}
```

Nếu ứng dụng không xác minh chain, người tấn công có thể dễ hơn trong việc giả mạo endpoint. Không dùng cách này trong production, kể cả “chỉ để tạm chạy migration”.

### 28.2. Tắt hostname verification

Một anti-pattern khác là cấu hình `HostnameVerifier` luôn trả true. Nó làm một certificate hợp lệ cho hostname khác có thể được chấp nhận cho endpoint không đúng.

Cần cấp certificate đúng SAN hoặc gọi đúng hostname, không bỏ kiểm tra identity.

### 28.3. Bật lại thuật toán yếu trên toàn JVM

Hạ `jdk.tls.disabledAlgorithms` hoặc `jdk.certpath.disabledAlgorithms` để vượt qua một server legacy có thể làm suy yếu nhiều kết nối khác. Chỉ cân nhắc ngoại lệ trong môi trường được cô lập, có phê duyệt security và hạn chót loại bỏ.

### 28.4. Nhúng password/private key vào source

Không:

- Commit keystore password vào repository.
- Gửi private key qua chat/log để debug.
- Ghi secrets trong command-line arguments dùng lâu dài.
- Copy production keystore sang laptop không kiểm soát.
- Đưa CA/private key chưa xác minh vào image.

Dùng secret management và quyền filesystem phù hợp.

### 28.5. “Sửa” bằng cách quay lại JDK rất cũ vô thời hạn

Downgrade có thể giúp khoanh vùng regression, nhưng bỏ toàn bộ bản vá bảo mật để giữ giao thức yếu không phải lộ trình migration bền vững.

## 29. Kiểm thử hồi quy sau khi sửa TLS

Sau khi endpoint kết nối được, cần chứng minh thay đổi không chỉ sửa một đường thử.

### 29.1. Ma trận môi trường

| Môi trường | Cần xác nhận |
|---|---|
| Developer | JDK và truststore thực, không chỉ browser |
| CI | Runtime/toolchain đúng, test network path |
| Staging | Proxy/gateway và certificates tương đương production |
| Production canary | Tỷ lệ handshake failures và latency, mTLS identities |
| Production full | Tất cả pods/regions có trust material nhất quán |
| Failover | Alternative endpoint/certificate/CA chain |
| Renewal window | Certificate rotation và truststore rollout |

### 29.2. Test cả negative cases

- Certificate không được tin cậy phải bị từ chối.
- Hostname không khớp phải bị từ chối.
- Certificate hết hạn phải bị từ chối.
- Client mTLS không có certificate phù hợp phải bị từ chối.
- Server chỉ hỗ trợ protocol bị cấm không được tự động downgrade.
- Truststore sai hoặc thiếu CA phải báo lỗi có thể chẩn đoán.

Nếu tất cả kết nối đều “pass” kể cả certificate sai, rất có thể cơ chế validation đã bị vô hiệu hóa.

### 29.3. Monitor theo phiên bản

Theo dõi:

- SSL/TLS handshake failure count và loại lỗi.
- PKIX/certpath errors.
- mTLS reject rate.
- Endpoint-specific failures.
- JDK/container image version.
- TLS negotiated protocol/cipher nếu có telemetry được phê duyệt.
- Certificate expiration alerts.
- Error rate/latency của API sau handshake.

Một sự cố handshake xảy ra theo vùng/instance có thể chỉ ra truststore hoặc proxy mismatch trên một phần fleet.

## 30. Checklist trước khi đóng sự cố

- [ ] Đã xác nhận đúng JVM, JDK vendor/update và runtime image của process lỗi.
- [ ] Đã phân biệt lỗi TCP/network với TLS handshake và HTTP response.
- [ ] Đã xác định hostname, port, SNI, proxy và điểm TLS termination.
- [ ] Đã đọc toàn bộ nested causes và fatal alert direction.
- [ ] Đã phân biệt protocol/cipher negotiation, certpath policy và truststore mismatch.
- [ ] Đã ghi `jdk.tls.disabledAlgorithms` và `jdk.certpath.disabledAlgorithms` có hiệu lực.
- [ ] Đã xem TLS versions, cipher suites, signature schemes và supported groups phù hợp.
- [ ] Đã kiểm tra certificate chain leaf/intermediates/trust anchor đúng endpoint.
- [ ] Đã xem SAN, validity, Key Usage/EKU và key sizes/signatures.
- [ ] Đã xác định truststore JSSE thực sự dùng, gồm custom SSLContext nếu có.
- [ ] Đã xem keystore/private key và server trust policy nếu ứng dụng dùng mTLS.
- [ ] Đã kiểm tra JDK/cacerts của container, không chỉ máy developer.
- [ ] Đã xác minh CA fingerprint qua nguồn tin cậy trước khi import.
- [ ] Đã tránh TrustManager permissive, disable hostname verification và mở lại TLS yếu.
- [ ] Đã kiểm thử JSSE/HTTP client thực tế sau khi sửa.
- [ ] Đã kiểm thử negative cases để xác nhận bảo mật vẫn được thực thi.
- [ ] Đã cập nhật trust material trong deploy configuration có version, không sửa thủ công từng pod.
- [ ] Đã có kế hoạch certificate rotation và theo dõi ngày hết hạn.
- [ ] Đã ghi test evidence, logs đã redaction và kết quả canary/production.
- [ ] Đã có rollback/roll-forward phù hợp với security policy.

## 31. Kết luận

Lỗi `SSLHandshakeException` sau khi nâng JDK không phải một vấn đề duy nhất. Nó có thể đến từ việc **không còn protocol/cipher chung**, **key/signature không đáp ứng security properties**, **truststore không có CA hoặc chain không đầy đủ**, **hostname/SNI không khớp** hay **mTLS client identity bị server từ chối**. Cùng một exception bề ngoài có thể xuất phát từ nhiều giai đoạn khác nhau của TLS handshake.

Trong Java Advance Compatibility Migration, chẩn đoán hiệu quả bắt đầu từ **đúng JVM và đúng endpoint**, sau đó đọc JSSE handshake log, phân tích fatal alert và nested cause, xác định security policy, kiểm tra certificate chain/truststore/keystore và thử lại bằng client cùng runtime thực tế. Khi tìm được nguyên nhân, hãy cập nhật TLS endpoint, cấp lại certificate/key hoặc cấu hình trust anchors được phê duyệt, thay vì bỏ qua những cơ chế xác thực mà JDK mới đang bảo vệ. Mục tiêu không chỉ là kết nối thành công, mà là **kết nối thành công với đúng danh tính, đúng chuỗi tin cậy và mức bảo mật phù hợp**.
