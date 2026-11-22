# Chọn phiên bản TLS, thuật toán và chính sách chứng thư còn được hỗ trợ

## 1. Mục tiêu và bối cảnh Java

Khi ứng dụng Java làm HTTPS client, TLS server hoặc kết nối đến một dịch vụ nội bộ, việc “bắt tay TLS thành công” **chưa đủ để chứng minh** kết nối đáp ứng chính sách bảo mật. Cần trả lời đồng thời các câu hỏi: giao thức TLS nào được thương lượng; cipher suite, chữ ký và nhóm trao đổi khóa có còn phù hợp; chứng thư máy chủ có được tin cậy và đúng hostname; và giao thức ứng dụng nào được chọn bởi ALPN.

Java 9 đưa **Application-Layer Protocol Negotiation (ALPN)** vào JSSE để client/server lựa chọn tên giao thức ứng dụng như `h2` và `http/1.1` trong TLS handshake. **TLS 1.3 được đưa vào JDK 11**, tức sự xuất hiện của API ALPN trong Java 9 không có nghĩa Java 9 nguyên bản đã hỗ trợ TLS 1.3. Bài này tập trung vào những nguyên tắc và API **vẫn dùng được trong các JDK hiện hành** (ví dụ Java 17, 21, 25, 27).

Mục tiêu học tập:

1. Chọn **TLS 1.3 ưu tiên**, dùng **TLS 1.2 khi cần tương thích** với bộ thuật toán phù hợp, và loại các phiên bản không còn an toàn.
2. Phân biệt **supported / enabled / negotiated** cho TLS versions và cipher suites.
3. Phân biệt cipher suite TLS 1.2/TLS 1.3 với **signature algorithms, named groups và chứng thư X.509**.
4. Xây dựng chính sách kiểm tra **certificate chain, hostname SAN, thuật toán khóa và truststore**, kể cả revocation nếu có yêu cầu.
5. Dùng **JSSE `SSLParameters`**, quan sát kết quả handshake và xử lý **ALPN** chính xác.
6. Chẩn đoán lỗi mà vẫn duy trì kiểm tra bảo mật, không hạ cấu hình khi thiếu giao điểm an toàn.

**Phạm vi:** TLS/ALPN trên JSSE và HTTPS Java. Chính sách cuối cùng phải dựa vào đúng provider, bản JDK, phía server, proxy/load balancer và yêu cầu của hệ thống. Không sao chép các cài đặt của một runtime cụ thể thành quy tắc chung cho mọi JVM.

## 2. Một kết nối TLS thương lượng những gì?

Một lần handshake cần sự đồng thuận giữa client và server ở nhiều tầng:

```text
Client Java                                     TLS Server
   |                                                |
   |--- ClientHello -------------------------------->|
   |      - phiên bản TLS được hỗ trợ               |
   |      - cipher suites                           |
   |      - nhóm trao đổi khóa, signature schemes   |
   |      - SNI: hostname mong muốn                 |
   |      - ALPN: h2, http/1.1                      |
   |                                                |
   |<-- Chọn phiên bản/cipher/khóa/chứng thư --------|
   |<-- Thương lượng ALPN (nếu có) ------------------|
   |                                                |
   |--- Kiểm tra chain, hostname, mục đích cert ---|
   |--- Hoàn tất handshake ------------------------>|
   |                                                |
   |<============== Dữ liệu ứng dụng ==============>|
```

Sơ đồ chỉ thể hiện các quyết định chính; thứ tự bản tin chi tiết của TLS 1.2 và TLS 1.3 khác nhau.

| Quyết định | Dấu hiệu quan sát được sau handshake | API JSSE |
| --- | --- | --- |
| TLS version | `TLSv1.3` hoặc `TLSv1.2` | `SSLSession.getProtocol()` |
| Cipher suite | Tên bộ thuật toán thực tế | `SSLSession.getCipherSuite()` |
| Chứng thư peer | Chain X.509 được cung cấp | `SSLSession.getPeerCertificates()` |
| Danh tính/trust của peer | Xác minh bởi trust manager + endpoint identification | `SSLParameters.setEndpointIdentificationAlgorithm(...)`, truststore |
| Giao thức ứng dụng | `h2`, `http/1.1` hoặc không thương lượng | `SSLSocket.getApplicationProtocol()` |

**Quan trọng:** lấy được peer certificate chain không tự chứng minh hostname đã được kiểm tra. Phần xác thực phụ thuộc trust manager và cấu hình endpoint identification. ALPN là quyết định của **tầng ứng dụng**, không phải một phiên bản TLS hay thuật toán mật mã.

## 3. Chọn phiên bản TLS đang thích hợp

### 3.1. TLS 1.3 ưu tiên, TLS 1.2 có điều kiện

| Protocol | Lựa chọn cho triển khai mới | Lý do |
| --- | --- | --- |
| `TLSv1.3` | **Ưu tiên** | Thiết kế TLS mới, dùng các cipher suites AEAD hiện đại và đơn giản hóa nhiều thành phần so với TLS 1.2 |
| `TLSv1.2` | **Còn phù hợp khi cần tương thích và kiểm soát thuật toán** | Có thể dùng ECDHE và AES-GCM với xác thực chứng thư đúng; phải tránh các suite cũ/yếu |
| `TLSv1.1` và `TLSv1` | Không dùng cho kết nối mới | Không còn phù hợp với hướng dẫn bảo mật TLS hiện đại |
| SSLv2 / SSLv3 | Không dùng | Các phiên bản SSL không an toàn cho triển khai hiện đại |

IETF RFC 9325 khuyến nghị hỗ trợ và ưu tiên TLS 1.3, đồng thời vẫn mô tả cấu hình TLS 1.2 an toàn cho môi trường cần tương thích. Một dịch vụ **nội bộ** có thể chọn *TLS 1.3 only* nếu mọi client đã đáp ứng; một API public có đối tác hợp lệ dùng TLS 1.2 có thể bật cả hai mà không hạ thấp cipher/certificate policy.

Không nên suy từ “TLS 1.2” rằng kết nối mặc nhiên yếu hoặc từ “TLS 1.3” rằng mọi thứ đã an toàn: endpoint vẫn có thể cấu hình sai trust manager, hostname validation, private keys, chứng thư hoặc quyền truy cập.

### 3.2. Supported, enabled và negotiated khác nhau

- `SSLSocket.getSupportedProtocols()` / `SSLContext.getSupportedSSLParameters().getProtocols()`: các phiên bản mà implementation **nhận biết/có thể hỗ trợ**.
- `SSLSocket.getEnabledProtocols()` / `getDefaultSSLParameters().getProtocols()`: các phiên bản **đang được bật** cho một connection/default context.
- `SSLSession.getProtocol()`: phiên bản **thực sự được thương lượng** sau handshake.

Đối với cipher suites cũng có khác biệt tương tự: `getSupportedCipherSuites()` không đồng nghĩa các suite đều được bật và được cho phép. Một thuật toán có thể xuất hiện trong danh sách supported nhưng bị **`jdk.tls.disabledAlgorithms`** loại khỏi TLS handshake. Việc gọi `setEnabledProtocols()` hay `setEnabledCipherSuites()` không tự vô hiệu hóa chính sách cấm của JDK.

`SSLContext.getInstance("TLS")` là tên context TLS tổng quát; bản thân nó **không khóa** giao thức vào duy nhất TLS 1.3 và không bảo đảm cấu hình giống nhau ở mọi runtime. Đừng kết luận chính sách từ tên context mà không kiểm tra bộ tham số đã bật và kết quả sau handshake.

### 3.3. Lựa chọn tại đúng điểm kết thúc TLS

Nếu kết nối Internet chấm dứt TLS ở **gateway/reverse proxy/load balancer** rồi chuyển HTTP nội bộ sang Java, cấu hình JSSE trong ứng dụng phía sau **không quyết định** TLS handshake giữa người dùng và gateway. Phải đặt chính sách ở chính thành phần kết thúc TLS, đồng thời xem có yêu cầu TLS/mTLS cho hop gateway → ứng dụng hay không. Với nhiều hop, đánh giá từng hop riêng biệt.

## 4. Chọn cipher suites và các thuật toán còn phù hợp

### 4.1. TLS 1.3

Những tên cipher suites phổ biến trong TLS 1.3 gồm:

- `TLS_AES_128_GCM_SHA256`
- `TLS_AES_256_GCM_SHA384`
- `TLS_CHACHA20_POLY1305_SHA256`

Các suite này dùng **AEAD** để vừa mã hóa vừa xác thực dữ liệu. **Tên suite TLS 1.3 không nói loại chứng thư là RSA hay ECDSA**, cũng không chỉ rõ named group trao đổi khóa. Chữ AES-256 không có nghĩa tất cả thành phần kết nối đều đạt mức 256-bit security strength.

Tập suite được hỗ trợ/bật thực tế phụ thuộc provider, CPU, cấu hình và phiên bản JDK. Đối với đa số client HTTP, ưu tiên default an toàn của JDK được cập nhật, chỉ ép allowlist khi có yêu cầu rõ ràng và đã kiểm thử kết nối.

### 4.2. TLS 1.2

Khi cần TLS 1.2, ưu tiên các cipher suites dùng **ECDHE** (trao đổi khóa tạm thời, hỗ trợ forward secrecy) với **AES-GCM**:

- `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`
- `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256`
- `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384`
- `TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384`

Danh sách này là ví dụ các **họ suite phù hợp về thiết kế**; chỉ chọn tên mà server có chứng thư/khóa tương thích, client và server cùng hỗ trợ và provider cho phép. Không nhất thiết mọi runtime có toàn bộ các suite.

Trong chính sách mới, tránh RSA key transport tĩnh `TLS_RSA_WITH_*`, static ECDH, các suite anonymous/NULL, RC4, DES, 3DES, MD5 hoặc chữ ký SHA-1 và các cấu hình CBC lỗi thời. Nhiều thuật toán đã bị vô hiệu trong JDK hiện hành; đừng bật lại chỉ để tương thích với một server chưa được nâng cấp. Với TLS 1.2, cần để ý **forward secrecy**, xác thực peer và các ràng buộc thuật toán trong policy của tổ chức.

### 4.3. Cipher, chữ ký và named groups không phải một cấu hình

| Thành phần | Ví dụ dùng hiện nay | Công dụng |
| --- | --- | --- |
| Cipher suite | `TLS_AES_128_GCM_SHA256` | Bảo vệ nội dung truyền trong TLS 1.3 |
| Signature scheme | RSA-PSS/SHA-256, ECDSA với SHA-256 theo profile phù hợp | Chứng minh quyền sở hữu khóa/chứng thư |
| Named group | `x25519`, `secp256r1` (khi policy/provider cho phép) | Trao đổi khóa/tạo shared secret |
| Khóa chứng thư X.509 | RSA hoặc EC theo ngưỡng an toàn được chấp thuận | Xác thực danh tính của peer |

`x25519` là cơ chế trao đổi khóa, **không phải** một kiểu chữ ký chứng thư. Trong TLS 1.3, việc chọn signature scheme và named group tách khỏi tên cipher suite. Khi provider/JDK hỗ trợ thuật toán/hybrid group mới, chỉ áp dụng nếu chính sách và khả năng tương thích đã được xác minh; không mặc định rằng mọi JDK sẽ có cùng tập thuật toán.

### 4.4. Khi nào tự đặt cipher suite allowlist?

Chỉ đặt allowlist thủ công nếu có yêu cầu từ security baseline/đối tác và người triển khai hiểu:

1. Cipher suites thực sự được provider hỗ trợ và **không bị chặn**.
2. Sự khác nhau giữa tên suite TLS 1.2 và TLS 1.3.
3. Loại khóa/chứng thư, chữ ký và named groups của server.
4. Yêu cầu HTTP/2 qua ALPN và những ràng buộc cipher của giao thức ứng dụng.
5. Khả năng thay đổi khi cập nhật JDK; kiểm thử lại sau mỗi đợt nâng cấp.

Tự chép một danh sách suite từ một JDK cũ dễ phá khả năng thương lượng TLS 1.3 hoặc khiến kết nối không có giao điểm an toàn.

## 5. Java Security: hai lớp ràng buộc thuật toán

Hai thuộc tính bảo mật quan trọng của JSSE/JCA:

| Security property | Áp dụng ở đâu |
| --- | --- |
| `jdk.tls.disabledAlgorithms` | Cấm/hạn chế các TLS protocol versions, cipher suites, cơ chế trao đổi khóa, chữ ký và key sizes không đạt chuẩn |
| `jdk.certpath.disabledAlgorithms` | Cấm/hạn chế thuật toán/khóa trong **đường dẫn chứng thư** khi kiểm tra PKIX/certpath |

**Đây là Java security properties**, thường được quản lý qua `conf/security/java.security` của JDK hoặc cấu hình security properties được runtime hỗ trợ. Phân biệt với **system properties** như `jdk.tls.client.protocols`, `jdk.tls.server.protocols`, `javax.net.ssl.trustStore`. Thêm `-Djdk.tls.disabledAlgorithms=...` không nên được coi là cách bảo đảm thay đổi cùng giá trị mà `Security.getProperty(...)` đọc.

Các giá trị disabledAlgorithms **thay đổi giữa JDK vendors, phiên bản và bản cập nhật**. Không ghi nhớ một chuỗi bị cấm là đúng cho mọi nơi. Nếu một API đã đánh dấu “supported”, security policy vẫn có thể chặn nó khi handshake.

Đoạn Java minh họa cách đọc chính sách đang hiệu lực:

```java
String tlsPolicy = java.security.Security.getProperty(
        "jdk.tls.disabledAlgorithms");
String certPolicy = java.security.Security.getProperty(
        "jdk.certpath.disabledAlgorithms");
```

Đoạn trên cần đặt trong chương trình/phương thức Java, không phải tệp độc lập. Để xem chính sách thực tế phải đọc **giá trị của cả hai property**, cấu hình provider và policy phía đối tác. Không tùy tiện gỡ hạn chế an ninh cho toàn JVM để giải quyết một lỗi TLS của riêng một dịch vụ.

## 6. Chọn chính sách chứng thư X.509

Một client HTTPS cần biết **đang giao tiếp với đúng server** chứ không chỉ cần một kênh mã hóa nào đó. Nếu ứng dụng tắt kiểm tra hostname hoặc dùng trust manager chấp nhận mọi chứng thư, kẻ tấn công có thể tạo TLS handshake hợp lệ với **máy chủ giả**.

### 6.1. Kiểm tra certificate chain

Trust manager/PKIX phải xây dựng và xác minh đường dẫn từ **leaf certificate** qua intermediate CA đến **trust anchor** được chấp thuận. Ngoài chữ ký hợp lệ, cần xét:

- **Validity:** certificate nằm trong khoảng `notBefore` / `notAfter`; đồng hồ server/client phải đúng.
- **Basic constraints:** intermediate/root CA có vai trò CA và ràng buộc path length phù hợp.
- **Key usage / extended key usage:** certificate sử dụng cho đúng mục đích, ví dụ `serverAuth` trên server certificate, `clientAuth` ở chiều mTLS khi cần.
- **Thuật toán chữ ký/khóa:** được cho phép theo security policy; với profile phổ biến, RSA từ 2048 bit hoặc khóa EC ở mức mạnh tương ứng là ngưỡng thực hành, nhưng policy tổ chức có thể nghiêm hơn.
- **Revocation nếu được yêu cầu:** OCSP/CRL phải thực sự được bật, có nguồn kiểm tra, kết nối mạng và quy tắc xử lý khi dịch vụ xác minh không khả dụng.

**Không mặc định rằng mọi JSSE client đều bật kiểm tra thu hồi chứng thư qua OCSP/CRL.** Chỉ `ocsp.enable=true` cũng không tự bảo đảm rằng mọi đường TLS đều đang kiểm tra thu hồi: cần cấu hình revocation checking của trust manager/PKIX và nhà cung cấp tương ứng, kiểm thử bằng chứng thư/đường dẫn phù hợp.

### 6.2. Hostname verification và Subject Alternative Name

Certificate **có thể được ký bởi một CA tin cậy nhưng cấp cho tên khác**. Vì thế, ngoài chain, client còn phải xác minh hostname truy cập trùng danh tính trong **Subject Alternative Name (SAN)** theo quy tắc của HTTPS. Đừng bỏ qua kiểm tra SAN/hostname chỉ vì `getPeerCertificates()` trả về một mảng chứng thư.

Với API HTTPS cấp cao như `java.net.http.HttpClient`, sử dụng cấu hình HTTPS mặc định để được xác thực endpoint. Với **raw `SSLSocket`/`SSLEngine` do ứng dụng tự điều khiển**, hãy bật:

```java
SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
```

Đây là đoạn minh họa cho socket TLS HTTPS đã tạo và cần `import javax.net.ssl.SSLParameters;`. Đặt **trước handshake**. Với giao thức TLS không phải HTTPS, cần một cơ chế kiểm tra định danh peer phù hợp với hợp đồng giao thức riêng; không mặc định mọi giao thức đều dùng quy tắc hostname HTTPS.

**SNI (Server Name Indication)** là tên client gửi tới server để chọn virtual host và chứng thư; **nó không thay cho bước hostname verification** phía client. Gửi đúng SNI vẫn có thể bị MITM nếu trust manager hoặc endpoint check bị vô hiệu.

### 6.3. Truststore và keystore

- **Truststore:** chứa các trust anchors CA/certificate được chấp thuận để xác thực peer.
- **Keystore:** có thể chứa certificate và private key mà server hoặc client mTLS dùng để chứng minh danh tính.
- **TrustManager/PKIX:** thực hiện logic chứng thực đường dẫn (có thể dùng cấu hình riêng).
- **Hostname verification:** kiểm tra đúng danh tính mà ứng dụng yêu cầu, không thể thay bằng việc “CA đã được tin cậy”.

Khi dùng CA nội bộ, xác minh fingerprint của CA qua kênh đáng tin cậy trước khi import vào truststore. Ví dụ lệnh `keytool` (POSIX shell; trên PowerShell dùng từng lệnh một dòng):

```bash
keytool -importcert -alias internal-root \
  -file internal-root.pem \
  -keystore app-truststore.p12 -storetype PKCS12

keytool -list -v \
  -keystore app-truststore.p12 -storetype PKCS12
```

Các lệnh sẽ hỏi mật khẩu khi cần. **Không đặt mật khẩu keystore/truststore vào code, log hay tham số có thể lộ trên process list.** Sử dụng cơ chế secret quản lý bởi môi trường chạy.

Khi đặt `javax.net.ssl.trustStore`, cần nhớ rằng truststore chỉ định có thể **thay thế** truststore mặc định của JDK. Nếu file riêng chỉ chứa private CA, ứng dụng có thể mất khả năng tin cậy public roots. Thiết kế một trust policy hợp nhất có kiểm soát hoặc `SSLContext` riêng cho đối tác nội bộ; đừng tạm thời sử dụng trust-all.

### 6.4. mTLS, gia hạn và thu hồi

Trong **mutual TLS (mTLS)**, phía server cũng xác minh chứng thư client với chain, `clientAuth`, validity, thuật toán và trust policy được định nghĩa riêng. Server có thể yêu cầu client cert qua `SSLParameters.setNeedClientAuth(true)` hoặc cấu hình của framework/proxy. Đây là **xác thực hai chiều**, không thay thế xác minh hostname của server bởi client.

Quản lý chứng thư thực tế cần theo dõi hết hạn, tự động gia hạn, luân chuyển khóa, kế hoạch thay CA và xử lý thu hồi. Nếu có certificate pinning, phải chuẩn bị cho việc xoay khóa và thay intermediate; pinning thủ công thường tạo rủi ro gián đoạn nếu không có quy trình thay thế. Không tin cậy mọi chứng thư chỉ để tránh lỗi khi xoay CA.

## 7. ALPN: lớp giao thức ứng dụng riêng biệt

Trong ALPN, client gửi danh sách các tên giao thức ứng dụng mà nó hiểu; server chọn một giá trị tương thích khi TLS handshake. API Java 9+:

```java
SSLParameters parameters = socket.getSSLParameters();
parameters.setApplicationProtocols(
        new String[] { "h2", "http/1.1" });
socket.setSSLParameters(parameters);

socket.startHandshake();
String protocol = socket.getApplicationProtocol();
```

Đây là đoạn mã **minh họa trong một chương trình có `SSLSocket socket`**, không phải chương trình độc lập. `getApplicationProtocol()` sau handshake trả protocol đã chọn; chuỗi rỗng khi không thương lượng ALPN, hoặc `null` nếu chưa có thông tin/kết quả tùy thời điểm.

| TLS đã chọn | ALPN đã chọn | Ý nghĩa |
| --- | --- | --- |
| `TLSv1.3` | `h2` | HTTP/2 trên TLS 1.3 |
| `TLSv1.3` | `http/1.1` | HTTP/1.1 trên TLS 1.3 |
| `TLSv1.2` | `h2` | HTTP/2 trên TLS 1.2 với profile TLS phù hợp |
| `TLSv1.2` | `http/1.1` | HTTP/1.1 trên TLS 1.2 |

Các tổ hợp trên có thể hợp lệ; **không đảm bảo** server cụ thể sẽ chọn chúng. Đừng đồng nhất ALPN `h2` với TLS 1.3; cũng đừng suy từ `TLSv1.3` rằng ứng dụng tự động dùng HTTP/2.

**Hệ quả quan trọng:** nếu đã thương lượng `h2`, tầng ứng dụng phải thực hiện framing HTTP/2. Không thể gửi text HTTP/1.1 vào raw TLS socket đã chọn `h2`. Với ứng dụng HTTP bình thường, dùng HTTP client/framework hỗ trợ HTTP/2 để nó quản lý ALPN và định dạng bản tin.

**HTTP/3** chạy trên QUIC với TLS 1.3 tích hợp, không tự có khi thêm chuỗi `"h3"` vào `SSLSocket` TCP. Muốn dùng HTTP/3, cần giao thức/transport QUIC tương ứng.

## 8. Ví dụ hoàn chỉnh 1 — xem TLS được JDK hỗ trợ (không cần mạng)

Tệp **`TlsPolicyInspect.java`**, biên dịch được với Java 17+:

```java
import java.security.Security;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;

public class TlsPolicyInspect {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, null);

        SSLParameters supported = context.getSupportedSSLParameters();
        SSLParameters defaults = context.getDefaultSSLParameters();

        System.out.println("Supported: "
                + Arrays.toString(supported.getProtocols()));
        System.out.println("Default enabled: "
                + Arrays.toString(defaults.getProtocols()));
        System.out.println("TLS policy configured: "
                + (Security.getProperty(
                        "jdk.tls.disabledAlgorithms") != null));
        System.out.println("Certpath policy configured: "
                + (Security.getProperty(
                        "jdk.certpath.disabledAlgorithms") != null));
    }
}
```

Chạy:

```bash
javac --release 17 TlsPolicyInspect.java
java TlsPolicyInspect
```

**Stdout không cố định:** danh sách supported, enabled và sự hiện diện của security properties khác nhau theo bản JDK/provider. Ví dụ trên một JDK hiện đại, enabled có thể chứa `[TLSv1.3, TLSv1.2]`. Nếu hai cờ property báo `true`, điều đó **chỉ xác nhận property tồn tại**, không nói rõ mọi thuật toán cụ thể bị cấm hay cho phép.

Chương trình chưa kết nối tới server, do đó không kiểm tra certificate chain, hostname, ALPN hoặc negotiated protocol. Đây là bài kiểm tra **cấu hình runtime đầu vào**, chưa phải kiểm tra kết nối thực tế.

## 9. Ví dụ hoàn chỉnh 2 — TLS handshake an toàn và xem kết quả

Tệp **`TlsHandshakeProbe.java`** chạy với JDK 17+, yêu cầu có kết nối tới HTTPS endpoint và một truststore phù hợp. Chương trình giới hạn TLS 1.3/1.2, bật HTTPS endpoint identification và quảng bá `h2` / `http/1.1`.

```java
import java.net.InetSocketAddress;
import java.net.Socket;
import java.util.Arrays;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSession;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

public class TlsHandshakeProbe {
    public static void main(String[] args) throws Exception {
        String host = args.length > 0 ? args[0] : "example.com";
        int port = args.length > 1 ? Integer.parseInt(args[1]) : 443;

        SSLSocketFactory factory =
                SSLContext.getDefault().getSocketFactory();

        try (Socket tcp = new Socket()) {
            tcp.connect(new InetSocketAddress(host, port), 5000);

            try (SSLSocket tls = (SSLSocket) factory.createSocket(
                    tcp, host, port, true)) {

                tls.setSoTimeout(5000);
                String[] protocols = Arrays.stream(
                        tls.getEnabledProtocols())
                        .filter(p -> p.equals("TLSv1.3")
                                  || p.equals("TLSv1.2"))
                        .toArray(String[]::new);

                if (protocols.length == 0) {
                    throw new SSLException(
                            "No permitted TLS 1.2/1.3");
                }

                SSLParameters parameters = tls.getSSLParameters();
                parameters.setProtocols(protocols);
                parameters.setEndpointIdentificationAlgorithm("HTTPS");
                parameters.setApplicationProtocols(
                        new String[] { "h2", "http/1.1" });
                tls.setSSLParameters(parameters);

                tls.startHandshake();

                SSLSession session = tls.getSession();
                String alpn = tls.getApplicationProtocol();

                System.out.println("TLS=" + session.getProtocol());
                System.out.println("Cipher=" + session.getCipherSuite());
                System.out.println("ALPN=" +
                        (alpn == null || alpn.isEmpty()
                                ? "(none)" : alpn));
                System.out.println("Peer certificates=" +
                        session.getPeerCertificates().length);
            }
        }
    }
}
```

Lệnh:

```bash
javac --release 17 TlsHandshakeProbe.java
java TlsHandshakeProbe example.com 443
```

**Không đưa ra stdout giả cố định**: tên cipher, TLS version, ALPN và số chứng thư phụ thuộc server và runtime. Nếu chain không tin cậy, hostname sai, protocol không chung hoặc thuật toán bị từ chối, handshake phải báo lỗi thay vì âm thầm bỏ qua bước xác thực.

Giải thích:

- `createSocket(tcp, host, port, true)` chuyển hostname mục tiêu cho TLS socket; cấu hình implementation có thể sử dụng hostname đó cho SNI.
- `setEndpointIdentificationAlgorithm("HTTPS")` yêu cầu kiểm tra danh tính hostname theo ngữ nghĩa HTTPS trong quá trình handshake.
- `protocols` chỉ giữ TLS 1.3/1.2 từ các protocol **đã được bật** trên socket; không bật lại TLS cũ và không vượt `disabledAlgorithms`.
- `setApplicationProtocols(...)` chỉ gửi **danh sách ALPN đề xuất**, không đảm bảo server chọn `h2`.
- `getProtocol()` và `getCipherSuite()` xem thông số được thương lượng, không đoán từ `SSLContext("TLS")`.
- Đây là **probe handshake**, chưa có request HTTP. Nếu kết quả ALPN là `h2`, ứng dụng cần HTTP/2 stack mới được trao đổi HTTP chính xác.

Nếu `example.com` không truy cập được từ môi trường thử nghiệm, sử dụng endpoint HTTPS **đã được phép** và có chứng thư hợp lệ để chạy. Tránh sửa code theo hướng “trust-all” chỉ để có stdout.

## 10. Ví dụ hoàn chỉnh 3 — dùng HttpClient cho HTTP/2 qua HTTPS

Trong ứng dụng thực tế, `java.net.http.HttpClient` (ổn định từ Java 11) xử lý HTTP và ALPN, thường phù hợp hơn việc tự xây HTTP/2 trên raw socket. Dưới đây là chương trình **biên dịch được với `--release 17`**, không phụ thuộc API đóng `HttpClient` mới xuất hiện ở các bản Java sau.

Tệp **`ModernHttpsClient.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class ModernHttpsClient {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        System.out.println("HTTP=" + response.version());
        System.out.println("Status=" + response.statusCode());
    }
}
```

Chạy:

```bash
javac --release 17 ModernHttpsClient.java
java ModernHttpsClient
```

**Stdout phụ thuộc mạng/server:** `HTTP_2` hoặc `HTTP_1_1` là phiên bản HTTP thực tế; `statusCode` cũng thay đổi. Yêu cầu `HttpClient.Version.HTTP_2` không đảm bảo peer đồng ý HTTP/2, và kết quả `HTTP_2` không nói rằng transport nhất thiết dùng TLS 1.3.

`HttpClient` quản lý ALPN cho HTTP version mà nó hỗ trợ. Không chỉnh thủ công `SSLParameters.setApplicationProtocols` của HTTP client/framework khi thiếu hướng dẫn chuyên biệt; việc ghi đè có thể làm sai lựa chọn HTTP/2. Nếu framework có cấu hình TLS riêng, hãy đặt version/cipher/trust ở chính API của framework đó.

## 11. mTLS và chứng thư ứng dụng

Ở HTTPS thông thường, client xác thực chứng thư server. Với **mutual TLS**, server đồng thời yêu cầu client cung cấp chứng thư và kiểm tra chain, key usage/extended key usage `clientAuth` và trust policy dành cho danh tính client.

Trong JSSE server, ví dụ `SSLParameters.setNeedClientAuth(true)` biểu đạt nhu cầu bắt buộc client certificate; nhưng trong ứng dụng server thực, cấu hình này thường đặt tại web container, reverse proxy hoặc framework đang sở hữu TLS endpoint. Client mTLS cần keystore chứa **khóa riêng/chứng thư client**; chỉ có truststore để xác minh server là chưa đủ.

Đừng nhầm mTLS với quyền ứng dụng: chứng thư chứng minh một danh tính ở tầng kết nối; quyền truy cập tài nguyên vẫn cần chính sách authorization phù hợp. mTLS cũng không miễn trừ kiểm tra hostname của server phía client.

## 12. Cách triển khai theo môi trường

| Trường hợp | Lựa chọn TLS và thuật toán | Chứng thư/ALPN cần chú ý |
| --- | --- | --- |
| API HTTPS công khai | Ưu tiên TLS 1.3, TLS 1.2 nếu client hợp lệ còn cần | Public CA được tin cậy, SAN đúng, chứng thư/khóa đạt policy; `h2` và `http/1.1` theo khả năng |
| API nội bộ kiểm soát toàn bộ client | Có thể TLS 1.3 only nếu mọi thành phần hỗ trợ | Private CA được quản lý; hostname đúng; xem xét mTLS |
| Đối tác chỉ hỗ trợ TLS 1.2 | TLS 1.2 với ECDHE/AES-GCM, không hạ cipher yếu | Xác nhận chứng thư server phù hợp và ALPN/HTTP version yêu cầu |
| Proxy/gateway termination | Chính sách đặt tại nơi **thực sự bắt tay TLS** | Kiểm tra từng hop, kể cả hop proxy → ứng dụng nếu mã hóa tiếp |
| Microservice có mTLS | TLS 1.3 ưu tiên, TLS 1.2 theo chính sách | ServerAuth/clientAuth, trust policy hai chiều, xoay chứng thư và khóa |

Những profile này là **nguyên tắc**, không thay thế chính sách tổ chức hoặc thử nghiệm thực tế. Điều kiện “còn được hỗ trợ” phải xác nhận qua tài liệu phiên bản driver/provider, config runtime và phía peer.

## 13. Theo dõi, xoay vòng và thu hồi chứng thư

- Theo dõi ngày `notAfter` của tất cả leaf/intermediate có liên quan; tự động hóa gia hạn và thử nghiệm chain sau gia hạn.
- Có kế hoạch đổi khóa riêng và trust anchors khi chứng thư/CA bị thu hồi hoặc lộ khóa; tránh cập nhật toàn bộ client cùng lúc mà không có giai đoạn tương thích có kiểm soát.
- Kiểm tra SAN đúng cho DNS endpoint thực, đặc biệt khi đổi domain, tạo service alias hoặc thay ingress.
- Kiểm tra `keyUsage`, `extendedKeyUsage`, thuật toán ký, độ dài khóa và các giới hạn PKIX trước khi đưa chứng thư vào production.
- Nếu chính sách yêu cầu revocation, cấu hình đầy đủ OCSP/CRL và quy định hành vi khi nguồn thu hồi không truy cập được. Không mặc định revocation tự bật trong mọi JSSE setup.
- Với certificate pinning, cân nhắc tác động khi CA/intermediate/key thay đổi. Chỉ sử dụng khi có bài toán bảo mật rõ ràng và quy trình xoay pin; không pin thủ công như cách chữa lỗi truststore.
- Không lưu private key hoặc mật khẩu vào repository; giới hạn truy cập khóa, theo dõi thay đổi và dùng cơ chế secret của môi trường.

## 14. Chẩn đoán lỗi theo đúng tầng

| Triệu chứng | Tầng cần kiểm tra | Hành động phù hợp |
| --- | --- | --- |
| `protocol_version`, `handshake_failure` | TLS versions/cipher suites không giao nhau | Xem enabled/supported ở cả hai đầu, security properties, nâng cấp peer |
| `no cipher suites in common` | Không chung thuật toán/key/chứng thư/chính sách | Kiểm tra cipher, nhóm trao đổi khóa, signature schemes và certificate |
| `PKIX path building failed` | Chưa xây được chain đến trust anchor được tin cậy | Xem root/intermediate CA, truststore và chain server |
| `No subject alternative DNS name matching ...` | Hostname không khớp SAN | Sửa hostname URL hoặc cấp chứng thư đúng tên |
| `CertificateExpiredException` | Thời hạn chứng thư hoặc đồng hồ không đúng | Gia hạn cert, kiểm tra đồng hồ/chain |
| `Certificates do not conform to algorithm constraints` | Thuật toán chữ ký/độ dài khóa không đạt policy | Thay chứng thư/khóa/provider phù hợp, không bật lại thuật toán yếu |
| `getApplicationProtocol()` rỗng | Không có ALPN chung hoặc server không thương lượng | Xem tên `h2`/`http/1.1`, hỗ trợ server và HTTP stack |
| TLS thành công nhưng HTTP/2 lỗi | Framing HTTP không đúng ALPN đã chọn | Dùng HTTP/2 client/framework thay vì gửi text HTTP/1.1 |
| Nâng cấp JDK xong kết nối đối tác lỗi | Default cipher, truststore hoặc algorithm constraints có thể đã đổi | So sánh config hiệu lực, nâng cấp đối tác, kiểm thử trường hợp bị từ chối |

**Bước chẩn đoán:** xác định nơi kết thúc TLS, ghi JDK/provider, enabled versions/ciphers và security properties, thu thông số negotiated sau handshake, xác minh chain/SAN, thử lại với peer và certificate hợp lệ. Khi sửa, kiểm tra cả các đường **phải thất bại** như hostname sai, CA không tin cậy, TLS cũ và cipher bị cấm.

Để xem handshake trong môi trường kiểm thử của SunJSSE có thể dùng:

```bash
java -Djavax.net.debug=ssl:handshake TlsHandshakeProbe example.com 443
```

Log TLS có thể chứa hostnames, danh sách certificate, thông tin handshake và dữ liệu vận hành nhạy cảm. Chỉ bật có kiểm soát, giới hạn lưu trữ và tắt khi xong. Debug log không thay thế kiểm thử chứng thư hoặc chính sách ứng dụng.

## 15. Những lỗi phổ biến cần tránh

1. **Java 9 có ALPN nên cũng có TLS 1.3:** sai; TLS 1.3 đến ở JDK 11.
2. **`SSLContext("TLS")` tự đảm bảo mọi thứ an toàn:** sai; cần kiểm tra enabled protocols/ciphers và trust/hostname policy.
3. **Thấy `TLSv1` trong supported thì được phép dùng:** sai; có thể bị disabledAlgorithms chặn.
4. **TLS 1.2 chắc chắn không an toàn:** không chính xác; còn có cấu hình TLS 1.2 phù hợp, nhưng phải kiểm soát cipher/cert nghiêm ngặt.
5. **Cipher TLS 1.3 chứa AES-256 nghĩa chứng thư/trao đổi khóa cũng 256 bit:** sai; các thuật toán có vai trò tách biệt.
6. **Truststore có CA tin cậy thì không cần xác minh hostname:** sai; phải kiểm tra SAN/endpoint identity.
7. **SNI là hostname verification:** sai; SNI hỗ trợ server chọn virtual host, chưa xác minh đúng peer.
8. **Một `getPeerCertificates()` thành công đảm bảo hostname đã đúng:** sai nếu client chưa bật endpoint check.
9. **Bật `ocsp.enable` là mọi JSSE client tự kiểm tra revocation:** sai; cần chính sách và cấu hình revocation đầy đủ.
10. **ALPN `h2` buộc TLS là 1.3:** sai; HTTP/2 có thể sử dụng TLS 1.2 với profile tương thích.
11. **Sau ALPN `h2` vẫn gửi HTTP/1.1 text được:** sai; phải dùng framing HTTP/2.
12. **Ép HTTP/2 qua `HttpClient.Version.HTTP_2` là chắc chắn server trả HTTP/2:** sai; kiểm tra version thực tế.
13. **Một đối tác TLS lỗi thì gỡ disabledAlgorithms cho cả JVM:** nguy hiểm; sửa peer/certificate hoặc xử lý ngoại lệ theo quy trình được kiểm soát.
14. **Nhập bất kỳ cert vào truststore hoặc dùng trust-all để hết lỗi:** khiến ứng dụng dễ bị mạo danh máy chủ.
15. **Cứ cập nhật JDK là không cần kiểm thử kết nối:** sai; thay đổi CA, provider và policy có thể ảnh hưởng tính tương thích và hành vi bảo mật.

## 16. Câu hỏi tự kiểm tra

1. **Với Java 17+, nên ưu tiên phiên bản nào?** TLS 1.3, giữ TLS 1.2 nếu có nhu cầu tương thích và cấu hình an toàn.
2. **TLS 1.3 là tính năng có từ Java 9?** Không. Java 9 bổ sung ALPN API; TLS 1.3 có từ JDK 11.
3. **`getSupportedProtocols()` chứng minh phiên bản được phép thương lượng?** Không. Cần xem enabled, disabledAlgorithms và kết quả handshake.
4. **`TLS_AES_128_GCM_SHA256` cho biết server dùng RSA certificate hay ECDSA?** Không; certificate/signature tách khỏi cipher suite TLS 1.3.
5. **Khi TLS 1.2 bắt buộc, một lựa chọn hợp lý là gì?** ECDHE + AES-GCM, certificate đúng và đầy đủ hostname validation.
6. **Trust chain hợp lệ nhưng SAN sai hostname có nên cho qua?** Không; đây là lỗi xác thực máy chủ.
7. **SNI có thay kiểm tra hostname phía client không?** Không.
8. **`jdk.tls.disabledAlgorithms` là system property bình thường?** Không; là Java security property.
9. **Sau handshake, xem TLS version và cipher bằng gì?** `SSLSession.getProtocol()` và `getCipherSuite()`.
10. **Có thể có `TLSv1.3 + http/1.1`?** Có.
11. **ALPN `h2` có nghĩa mình đã có một HTTP/2 parser?** Không; cần HTTP stack xử lý frame.
12. **Với `HttpClient` yêu cầu HTTP/2, xem kết quả ở đâu?** `HttpResponse.version()`.
13. **Dịch vụ nội bộ cần private CA thì làm gì?** Xác minh CA qua kênh tin cậy, quản lý truststore/SSLContext phù hợp, không bật trust-all.
14. **Nếu cần kiểm tra chứng thư bị thu hồi, chỉ cần OS certificate store là đủ?** Không; phải đảm bảo revocation checking được cấu hình và kiểm thử trong đường xác minh thực tế.
15. **Vì sao phải kiểm thử lại sau nâng JDK?** Default protocols, cipher suites, CA và algorithm constraints có thể thay đổi.

## 17. Checklist triển khai cho dịch vụ Java hiện hành

- [ ] Biết đúng thành phần nào thực hiện TLS handshake, không nhầm application với proxy.
- [ ] TLS 1.3 được ưu tiên; TLS 1.2 chỉ khi cần và với cipher an toàn.
- [ ] SSLv3, TLS 1.0/1.1 và cipher cũ không được bật lại.
- [ ] Các suite, chữ ký và named groups được provider hỗ trợ và không vi phạm security properties.
- [ ] Client kiểm tra chain, SAN/hostname, hạn sử dụng, EKU/keyUsage, thuật toán/key size.
- [ ] Có truststore tin cậy, quản lý private CA và mTLS đúng phạm vi.
- [ ] Revocation checking được cấu hình nếu security policy yêu cầu.
- [ ] Không có trust-all manager hoặc hostname verifier chấp nhận tất cả.
- [ ] ALPN chỉ quảng bá protocol ứng dụng mà HTTP stack thực sự xử lý.
- [ ] Log/metric quan sát TLS version, cipher, ALPN và lỗi certificate trên đường kết nối thực.
- [ ] Kiểm thử cả handshake thành công và các trường hợp chính sách phải từ chối.
- [ ] Gia hạn/rotate chứng thư được giám sát, kiểm thử lại sau nâng cấp JDK/provider.

## Tài liệu chuẩn để đối chiếu

- Oracle Java SE 27 — JSSE Reference Guide (TLS, cipher policy, certificate validation, SNI, ALPN): https://docs.oracle.com/en/java/javase/27/security/java-secure-socket-extension-jsse-reference-guide.html
- Oracle Java SE 27 — `SSLParameters`: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/net/ssl/SSLParameters.html
- Oracle Java SE 27 — `SSLSocket`: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/net/ssl/SSLSocket.html
- Oracle Java SE 27 — `SSLSession`: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/net/ssl/SSLSession.html
- OpenJDK JEP 244 — ALPN (Java 9): https://openjdk.org/jeps/244
- OpenJDK JEP 332 — TLS 1.3 (Java 11): https://openjdk.org/jeps/332
- IETF RFC 9325 — Recommendations for Secure Use of TLS and DTLS: https://www.rfc-editor.org/rfc/rfc9325
- IETF RFC 8446 — TLS 1.3: https://www.rfc-editor.org/rfc/rfc8446

**Ghi nhớ:** TLS bảo mật khi **đúng phiên bản, bộ thuật toán được phép, chứng thư/hostname được xác thực và giao thức ứng dụng ALPN được xử lý chính xác**. Kiểm tra hiệu lực trên đúng nơi thực hiện handshake và trên đúng JDK/provider, thay vì suy từ tên API hoặc thông số cấu hình dự kiến.
