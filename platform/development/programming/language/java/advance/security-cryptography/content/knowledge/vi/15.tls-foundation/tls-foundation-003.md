# 15.3 TLS 1.2, TLS 1.3 và cách đọc cấu hình giao thức khả dụng

## 1. Mục tiêu: “TLS được hỗ trợ” khác “TLS được sử dụng”

**Transport Layer Security (TLS)** bảo vệ dữ liệu khi truyền giữa hai endpoint: đàm phán cơ chế mật mã, xác thực bên liên quan theo chính sách, tạo khóa phiên, mã hóa và kiểm tra tính toàn vẹn bản ghi. Với Java 17+, phần lớn ứng dụng làm việc với TLS qua **JSSE (Java Secure Socket Extension)**: `SSLContext`, `SSLSocket`, `SSLServerSocket`, `SSLEngine`, `SSLParameters`, `SSLSession` và các `KeyManager`/`TrustManager`.

Trong vận hành thường gặp những câu hỏi khác nhau:

1. JDK/provider **biết** những phiên bản TLS nào?
2. Một `SSLContext` hoặc socket **đang cho phép** những phiên bản nào?
3. Java Security policy có **cấm** thuật toán/phiên bản nào không?
4. Peer server/client **chấp nhận** và có thể đàm phán những phiên bản nào?
5. Một kết nối **đã bắt tay thành công thực sự** sử dụng phiên bản và cipher suite nào?

Năm câu trên có thể cho **năm kết quả khác nhau**. Ví dụ trong một runtime SunJSSE đã kiểm thử, `SSLSocket.getSupportedProtocols()` chứa `TLSv1`, `TLSv1.1`, `SSLv3`, nhưng `getEnabledProtocols()` mặc định chỉ có `TLSv1.3` và `TLSv1.2`. **Không** kết luận máy đang cho phép SSLv3/TLS 1.0 vì chúng xuất hiện trong danh sách “supported”.

Các mục tiêu học tập:

- Phân biệt handshake, key schedule và cipher suite của **TLS 1.2** và **TLS 1.3**.
- Đọc đúng supported/enabled/default/disabled/negotiated từ JSSE.
- Hiểu ảnh hưởng của `jdk.tls.disabledAlgorithms`, `jdk.tls.client.protocols`, `jdk.tls.server.protocols`, `https.protocols`, `SSLParameters` và provider.
- Xem protocol/cipher suite thật **sau handshake** với `SSLSession`.
- Chẩn đoán lỗi `protocol_version`, `handshake_failure`, `SSLHandshakeException` mà không tắt các cơ chế bảo vệ.
- Tự chạy hai chương trình Java 17: inventory cấu hình và kết nối TLS 1.2/TLS 1.3 qua loopback có trust/hostname verification.

Bài này tập trung TLS trên TCP qua JSSE; **DTLS**, QUIC/TLS và giao thức ứng dụng HTTP/2, HTTP/3 có ràng buộc riêng. Không dùng thông tin từ một kết nối TLS để tự suy ra trạng thái mọi service trên máy.

## 2. So sánh TLS 1.2 và TLS 1.3

TLS 1.2 là phiên bản theo **RFC 5246**; TLS 1.3 theo **RFC 8446**. Cả hai đều dùng được cho các hệ thống tương thích và được cấu hình đúng, nhưng TLS 1.3 đơn giản hóa nhiều chi tiết và loại bỏ các phương thức mật mã lỗi thời.

| Khía cạnh | TLS 1.2 | TLS 1.3 |
| --- | --- | --- |
| RFC | `5246` | `8446` |
| Handshake đầy đủ thông thường | Thường khoảng **2 RTT** trước application data, phụ thuộc loại handshake | Thường **1 RTT**, hỗ trợ resumption và tùy chọn **0-RTT early data** theo giao thức |
| Trao đổi khóa | Phụ thuộc cipher suite: ECDHE, DHE, RSA key transport lịch sử... | Mô hình (EC)DHE/PSK key schedule được thiết kế lại; loại RSA key transport |
| Cipher suites | Tên thường mang **key exchange + authentication + symmetric encryption + hash/MAC** | Tên chủ yếu mô tả **AEAD + hash**; nhóm key exchange và signature scheme đàm phán riêng |
| Ví dụ cipher suite | `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` | `TLS_AES_128_GCM_SHA256` |
| Encryption cho application data | GCM/ChaCha20-Poly1305 hoặc nhiều cơ chế cũ hơn tùy suite | **AEAD** như AES-GCM hoặc ChaCha20-Poly1305 |
| Key derivation | TLS 1.2 PRF và key block/Finished theo protocol | **HKDF-based key schedule**, bí mật phân tách theo từng pha |
| Forward secrecy | Có với ECDHE/DHE; **không tự có** khi dùng RSA static key transport | Thường có với (EC)DHE; **PSK-only không có cùng tính chất forward secrecy** nếu không có fresh DHE |
| Renegotiation | Có các cơ chế renegotiation cần xử lý an toàn theo version/provider | **Không có TLS 1.2 renegotiation**, có các cơ chế post-handshake như `KeyUpdate` |
| Certificate authentication | Certificate + handshake signatures theo cipher suite/profile | Certificate + signature schemes được đàm phán riêng (như RSA-PSS/ECDSA) |
| Tương thích | Nhiều hệ thống legacy hơn | Có thể cần cập nhật proxy/load balancer/server hoặc mã cứng cipher suites |

**Lưu ý:** 0-RTT early data có **nguy cơ replay**, không phù hợp mọi thao tác (ví dụ giao dịch không idempotent) và **không đồng nghĩa** ứng dụng Java/JSSE bất kỳ cũng hỗ trợ tự động. Không bật 0-RTT chỉ vì client và server hiển thị hỗ trợ TLS 1.3.

### 2.1 Phác họa TLS 1.2 handshake

Một full handshake TLS 1.2 có certificate server và ECDHE điển hình:

```text
Client                                           Server
ClientHello ------------------------------->
                           <--------------- ServerHello
                           <--------------- Certificate
                           <--------------- ServerKeyExchange
                           <--------------- ServerHelloDone
ClientKeyExchange ------------------------->
ChangeCipherSpec / Finished --------------->
                           <--------------- ChangeCipherSpec / Finished
          <======== Protected application data ========>
```

Thông điệp có thể khác tùy cipher suite, client authentication và resumption. Đây là **sơ đồ khái niệm** để so sánh, không phải transcript byte đầy đủ hay mô tả mọi biến thể.

TLS 1.2 cho phép một số cipher suites có key exchange cũ (ví dụ RSA key transport) và cơ chế CBC/SHA-1 lịch sử. **Không nên tái bật các lựa chọn yếu chỉ để tương thích**. Đối với TLS 1.2 còn cần dùng, ưu tiên suites có **ECDHE/DHE + AEAD** được security policy cho phép, và xử lý signature/certificate đúng profile.

### 2.2 Phác họa TLS 1.3 handshake

Full handshake TLS 1.3 với key share:

```text
Client                                           Server
ClientHello + supported_versions
            + key_share -------------------->
                           <--------------- ServerHello + key_share
                           <--------------- EncryptedExtensions
                           <--------------- Certificate
                           <--------------- CertificateVerify
                           <--------------- Finished
Finished ----------------------------------->
          <======== Protected application data ========>
```

Các pha sau `ServerHello` được bảo vệ bằng handshake traffic keys. TLS 1.3 dùng HKDF để tách handshake/application secrets, cho phép forward-secure key exchange khi dùng fresh (EC)DHE và loại bỏ RSA key transport. Trong resumption dùng PSK, số bản tin và bí mật khác; có thể có HelloRetryRequest khi key share đề xuất không phù hợp.

**Đừng hiểu số RTT là cam kết thời gian kết nối:** TCP setup, DNS, proxy, network latency, crypto provider, certificate chain, OCSP, HTTP/2/ALPN, session cache và ứng dụng vẫn ảnh hưởng tốc độ thực tế.

### 2.3 Tên cipher suite của TLS 1.2 so với 1.3

```text
TLS 1.2: TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
                |      |        |          |
           key agreement  cert  AEAD    hash/PRF

TLS 1.3: TLS_AES_128_GCM_SHA256
                  |      |
                AEAD     HKDF hash
```

Với TLS 1.3, **tên cipher suite không xác định nhóm ECDHE/DHE hoặc kiểu chữ ký certificate**. Các thành phần này được thương lượng qua extensions như `supported_groups`, `key_share`, `signature_algorithms` và `signature_algorithms_cert` tùy tình huống. Một server dùng certificate RSA vẫn có thể đàm phán `TLS_AES_128_GCM_SHA256`; không cần một TLS 1.3 suite có chữ “RSA” trong tên.

**Không đưa** một TLS 1.2 suite `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` làm điều kiện duy nhất cho TLS 1.3 và mong kết nối 1.3 thành công. Ngược lại, chỉ cho phép suites có tên TLS 1.3 rồi cố thương lượng TLS 1.2 có thể khiến handshake thất bại.

## 3. “Supported”, “enabled”, “configured” và “negotiated” nghĩa là gì?

Đây là phần quan trọng nhất khi **đọc cấu hình giao thức khả dụng**.

| Mức | Câu hỏi | Java API/thông tin | Ý nghĩa |
| --- | --- | --- | --- |
| **Supported** | Implementation này *biết* phiên bản nào? | `SSLSocket.getSupportedProtocols()`, `SSLEngine.getSupportedProtocols()`, `SSLContext.getSupportedSSLParameters().getProtocols()` | Danh sách implementation hỗ trợ; **có thể gồm protocol đã disabled** |
| **Enabled** | Socket/engine *được cấu hình* thử những phiên bản nào? | `SSLSocket.getEnabledProtocols()`, `SSLEngine.getEnabledProtocols()`, `SSLParameters.getProtocols()` | Phạm vi phép đàm phán từ phía object; chưa chứng minh peer sẽ chấp nhận |
| **Default** | Context/provider *mặc định* cho phép gì trước khi override? | `SSLContext.getDefaultSSLParameters()` hoặc socket/engine mới | Phụ thuộc JDK, provider, role, security/system properties |
| **Security policy** | Có protocol/cipher/algorithm nào bị cấm không? | `Security.getProperty("jdk.tls.disabledAlgorithms")`, `jdk.certpath.disabledAlgorithms` | Có thể **ngăn negotiation** ngay cả khi mã đặt protocol trong enabled |
| **Peer capability** | Đối tác nhận gì? | Server/client settings hoặc handshake trace đã xác thực | Không thể suy từ `getSupportedProtocols` của máy local |
| **Negotiated** | Kết nối **đã handshake** dùng phiên bản nào? | `socket.getSession().getProtocol()`, `getCipherSuite()` | Giá trị thực của **kết nối cụ thể**, chỉ đáng tin khi handshake thành công |

Ví dụ:

```text
SunJSSE supported: [TLSv1.3, TLSv1.2, TLSv1.1, TLSv1, SSLv3, SSLv2Hello]
SunJSSE enabled:   [TLSv1.3, TLSv1.2]
Server enabled:    [TLSv1.2]
Shared usable:     [TLSv1.2]
Negotiated:        TLSv1.2 (chỉ sau khi handshake thành công)
```

Dù client hỗ trợ TLSv1.3 và bật nó, nó vẫn **có thể** thương lượng TLSv1.2 vì server không hỗ trợ/bật TLSv1.3. Nếu server chỉ bật TLSv1.1 và client chỉ bật TLSv1.2/1.3, handshake **không có protocol chung**, nhưng dấu hiệu lỗi cụ thể phụ thuộc implementation.

**Đặc biệt:** nhiều JDK vẫn hiển thị TLSv1/TLSv1.1 trong `getSupportedProtocols()`, trong khi `jdk.tls.disabledAlgorithms` cấm negotiation. Thậm chí `setEnabledProtocols(new String[]{"TLSv1"})` được object chấp nhận không đồng nghĩa handshake với TLSv1 được phép. Không xóa TLSv1/TLSv1.1/SSLv3 khỏi security disabled list chỉ để “làm test pass”.

### Quy tắc kiểm tra đúng thứ tự

1. Đọc **provider/JDK version và security properties**.
2. Đọc **supported** của chính engine đang sử dụng.
3. Đọc **enabled/default** trước khi bắt tay; xem ứng dụng có override bằng `setEnabledProtocols`/`SSLParameters` hoặc system properties không.
4. Kiểm tra **cipher suites, named groups, signature schemes**, key/certificate/trust và peer.
5. Thực hiện **handshake thật** với trust/hostname verification.
6. Sau thành công, đọc `SSLSession.getProtocol()` và `getCipherSuite()` để biết giá trị **thật sự được thương lượng**.

## 4. Các JSSE API dùng để đọc TLS

| API | Mục đích | Lưu ý |
| --- | --- | --- |
| `SSLContext.getInstance("TLS")` | Chọn generic TLS engine/provider | Không có nghĩa “chỉ TLS 1.0”; cần đọc default/supported/actual |
| `SSLContext.init(...)` | Cấp key managers, trust managers, RNG | Cấu hình trust/certificate không thể suy từ tên `TLS` |
| `SSLContext.getSupportedSSLParameters()` | Supported parameters của context | Includes supported protocols/suites nhưng không bảo đảm được negotiate |
| `SSLContext.getDefaultSSLParameters()` | Enabled-by-default parameters trong context | Có thể khác tùy SunJSSE/provider và client/server role |
| `SSLSocket.getSupportedProtocols()` | Protocols implementation có | Danh sách có thể gồm bị disabled |
| `SSLSocket.getEnabledProtocols()` | Protocols được bật trên socket hiện tại | Chỉ trạng thái **trước/cho phép handshake** |
| `SSLSocket.setEnabledProtocols(String[])` | Giới hạn protocols cho socket | Ném `IllegalArgumentException` khi protocol không được implementation hỗ trợ; policy vẫn có thể cấm |
| `SSLParameters.getProtocols()/setProtocols(...)` | Xem/đặt protocol list theo parameter object | Phải áp vào `socket.setSSLParameters(...)` hoặc engine |
| `SSLSocket.getSupportedCipherSuites()` | Danh sách suite implementation biết | Suite yếu có thể xuất hiện nhưng bị policy chặn |
| `SSLSocket.getEnabledCipherSuites()` | Suite list hiện bật | Cần tương thích phiên bản TLS, key algorithm, peer |
| `SSLSocket.startHandshake()` | Khởi động/đợi handshake | Thất bại khi protocol, trust, cipher, cert... không phù hợp |
| `SSLSession.getProtocol()` | **Phiên bản negotiated** | Chỉ xem sau successful handshake |
| `SSLSession.getCipherSuite()` | **Suite negotiated** | Không tự nói toàn bộ nhóm ECDHE hay chính sách danh tính |
| `SSLEngine.getSupportedProtocols()/getEnabledProtocols()` | Tương tự khi dùng NIO/async TLS | Handshake engine cần xử lý state `NEED_WRAP`/`NEED_UNWRAP`/`NEED_TASK` |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Bật identity/hostname verification theo HTTPS trên JSSE | Rất quan trọng với SSLSocket tự tạo; cần trust manager đúng |

`SSLParameters.setProtocols(...)` không tự thay đổi socket/engine đã tồn tại; phải gọi `setSSLParameters(...)` trên đúng đối tượng trước handshake. Chú ý: `getDefaultSSLParameters()` và socket factory không bắt buộc phản ánh **một danh sách chung cho mọi socket ở mọi role**. Dùng chính socket/engine mà ứng dụng thực tế tạo và in `getEnabledProtocols()` để chẩn đoán.

Với `SSLEngine`, các method có cùng khái niệm supported/enabled; nhưng handshake nonblocking yêu cầu điều khiển wrap/unwrap buffer và delegated tasks. Không coi việc tạo `SSLEngine` hoặc đọc enabled protocols là đã thực hiện handshake.

## 5. Chương trình 1 — kiểm kê TLS từ Java mà không kết nối mạng

Lưu thành **`TlsProtocolInventoryDemo.java`**, dùng Java 17 trở lên. Chương trình tạo `SSLContext("TLS")` và một `SSLSocket` **chưa kết nối**, in provider, supported/enabled/default protocols, các cờ TLS 1.2/TLS 1.3 và vài configuration properties. **Không có kết nối mạng và không có phiên bản negotiated** trong chương trình này.

```java
import java.security.Security;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

public final class TlsProtocolInventoryDemo {
    private static boolean has(String[] values, String target) {
        return Arrays.asList(values).contains(target);
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, null);
        SSLParameters defaults = context.getDefaultSSLParameters();
        SSLParameters supported = context.getSupportedSSLParameters();
        SSLSocketFactory factory = context.getSocketFactory();
        try (SSLSocket socket = (SSLSocket) factory.createSocket()) {
            System.out.println("contextProtocol=" + context.getProtocol());
            System.out.println("provider=" + context.getProvider().getName());
            System.out.println("supportedProtocols="
                    + Arrays.toString(socket.getSupportedProtocols()));
            System.out.println("enabledProtocols="
                    + Arrays.toString(socket.getEnabledProtocols()));
            System.out.println("defaultProtocolsFromContext="
                    + Arrays.toString(defaults.getProtocols()));
            System.out.println("supportedProtocolsFromContext="
                    + Arrays.toString(supported.getProtocols()));
            System.out.println("supportsTLS12="
                    + has(socket.getSupportedProtocols(), "TLSv1.2"));
            System.out.println("supportsTLS13="
                    + has(socket.getSupportedProtocols(), "TLSv1.3"));
            System.out.println("enabledTLS12="
                    + has(socket.getEnabledProtocols(), "TLSv1.2"));
            System.out.println("enabledTLS13="
                    + has(socket.getEnabledProtocols(), "TLSv1.3"));
            System.out.println("disabledAlgorithmsPresent="
                    + (Security.getProperty("jdk.tls.disabledAlgorithms") != null));
            System.out.println("clientProtocolsProperty="
                    + System.getProperty("jdk.tls.client.protocols", "(not set)"));
            System.out.println("httpsProtocolsProperty="
                    + System.getProperty("https.protocols", "(not set)"));
            System.out.println("noHandshakePerformed=true");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```powershell
javac --release 17 -encoding UTF-8 TlsProtocolInventoryDemo.java
java TlsProtocolInventoryDemo
```

**Output chính xác trong môi trường SunJSSE được kiểm thử** (không phải kết quả cố định cho mọi máy):

```text
contextProtocol=TLS
provider=SunJSSE
supportedProtocols=[TLSv1.3, TLSv1.2, TLSv1.1, TLSv1, SSLv3, SSLv2Hello]
enabledProtocols=[TLSv1.3, TLSv1.2]
defaultProtocolsFromContext=[TLSv1.3, TLSv1.2]
supportedProtocolsFromContext=[TLSv1.3, TLSv1.2, TLSv1.1, TLSv1, SSLv3, SSLv2Hello]
supportsTLS12=true
supportsTLS13=true
enabledTLS12=true
enabledTLS13=true
disabledAlgorithmsPresent=true
clientProtocolsProperty=(not set)
httpsProtocolsProperty=(not set)
noHandshakePerformed=true
```

### Đọc đúng output

- `contextProtocol=TLS` nói tên engine được yêu cầu, **không phải** `SSLSession` negotiated protocol.
- `supportedProtocols` có những mục cũ: `SSLv3`, `TLSv1`, `TLSv1.1`. Chúng được provider “nhận diện”, **không** có nghĩa được phép đàm phán trong cấu hình mặc định.
- `enabledProtocols=[TLSv1.3,TLSv1.2]` là khả năng đàm phán mặc định của socket ở môi trường test. Sau khi chạy với `-D...`, sửa `java.security`, chọn provider khác hoặc đổi version JDK, danh sách có thể đổi.
- `disabledAlgorithmsPresent=true` **chỉ** nói có một giá trị cấu hình security property. Để đánh giá đầy đủ, phải đọc **nội dung thực** bằng `Security.getProperty("jdk.tls.disabledAlgorithms")` và xem thuật toán/nhóm liên quan; không chỉ kiểm `null`.
- `noHandshakePerformed=true` là lời nhắc `getEnabledProtocols()` **chưa chứng minh** kết nối TLS thật nào thành công.

Không dùng `SSLContext.init(null,null,null)` của chương trình này như “cấu hình trust hoàn chỉnh cho hệ thống thật”. Ở đây context không kết nối mạng, nên không có peer certificate để xác thực.

## 6. Chương trình 2 — xác minh *negotiated protocol* bằng TLS handshake thật

Chương trình thứ hai **tự tạo TLS server và client trên loopback `127.0.0.1`**, thực hiện một handshake chỉ dùng TLS 1.3 và một handshake chỉ dùng TLS 1.2.

Khác với inventory ở phần 5, ví dụ này kiểm tra:

- Server có `KeyManagerFactory` cung cấp certificate và private key từ PKCS12.
- Client có `TrustManagerFactory` tin **duy nhất chứng thư local demo** do bạn tạo, không tắt certificate validation.
- Client gọi `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` để xác minh IP SAN `127.0.0.1` trong certificate, không dùng trust-all `X509TrustManager`.
- Hai phía đặt `setEnabledProtocols(new String[]{version})` trước handshake.
- Sau `startHandshake()`, đọc **`SSLSession.getProtocol()`**, **`getCipherSuite()`** và peer certificate; kiểm tra hai bên đồng thuận phiên bản.

**Chỉ sử dụng trong môi trường học tập.** Private key tự ký là test fixture, password `changeit` dễ đoán, certificate không thuộc public trust store. Kết quả thành công **không xác nhận một server Internet hay service sản phẩm nào**.

### 6.1 Tạo chứng thư test và truststore bằng keytool

Chạy trong **PowerShell**, từ thư mục chứa hai file source Java. Giữ **cùng phiên PowerShell** để dùng lại biến `$t`. Các lệnh tạo tệp chỉ trong `$env:TEMP` của máy:

```powershell
# Thư mục tạm, không đặt key demo vào repository.
$t = Join-Path $env:TEMP ("tls-protocol-lesson-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $t | Out-Null
$pw = "changeit"  # Chỉ dùng cho demo!

# RSA test server certificate 7 ngày, SAN gồm IP và DNS cho loopback.
keytool -genkeypair -alias localserver -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=localhost" -ext "SAN=ip:127.0.0.1,dns:localhost" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -validity 7 -storetype PKCS12 -keystore (Join-Path $t "server.p12") -storepass $pw -keypass $pw -noprompt

# Export public certificate; không export server private key.
keytool -exportcert -alias localserver -keystore (Join-Path $t "server.p12") -storepass $pw -rfc -file (Join-Path $t "server.pem")

# Client chỉ tin certificate của localserver trong demo.
keytool -importcert -alias localserver -file (Join-Path $t "server.pem") -keystore (Join-Path $t "trust.p12") -storetype PKCS12 -storepass $pw -noprompt
```

**Vì sao `127.0.0.1` phải có SAN IP?** Client kết nối bằng IP string và bật endpoint identification algorithm `HTTPS`; kiểm tra danh tính phải khớp **iPAddress SAN**, không chỉ CN trong subject. Nếu bỏ SAN, TLS có thể bị từ chối do hostname/IP mismatch ngay cả khi truststore chứa certificate.

### 6.2 Mã Java hoàn chỉnh

Lưu thành **`LoopbackTlsHandshakeDemo.java`**:

```java
import java.io.InputStream;
import java.net.InetAddress;
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

public final class LoopbackTlsHandshakeDemo {
    private static KeyStore load(Path file, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(file)) {
            store.load(in, password);
        }
        return store;
    }

    private static SSLContext serverContext(Path keyStorePath,
                                            char[] password) throws Exception {
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(load(keyStorePath, password), password);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf.getKeyManagers(), null, new SecureRandom());
        return context;
    }

    private static SSLContext clientContext(Path trustStorePath,
                                            char[] password) throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(load(trustStorePath, password));
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    private static void run(String version, SSLContext server,
                            SSLContext client) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (SSLServerSocket listener = (SSLServerSocket)
                server.getServerSocketFactory().createServerSocket(
                        0, 1, loopback)) {
            listener.setEnabledProtocols(new String[]{version});
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> serverSession = executor.submit(() -> {
                    try (SSLSocket peer = (SSLSocket) listener.accept()) {
                        peer.setEnabledProtocols(new String[]{version});
                        peer.startHandshake();
                        return peer.getSession().getProtocol();
                    }
                });
                try (SSLSocket socket = (SSLSocket)
                        client.getSocketFactory().createSocket(
                                "127.0.0.1", listener.getLocalPort())) {
                    socket.setEnabledProtocols(new String[]{version});
                    SSLParameters params = socket.getSSLParameters();
                    params.setEndpointIdentificationAlgorithm("HTTPS");
                    socket.setSSLParameters(params);
                    socket.startHandshake();

                    String negotiatedClient = socket.getSession().getProtocol();
                    String negotiatedServer =
                            serverSession.get(10, TimeUnit.SECONDS);
                    System.out.println(version + " negotiated="
                            + negotiatedClient);
                    System.out.println(version + " peersAgree="
                            + (version.equals(negotiatedClient)
                            && negotiatedClient.equals(negotiatedServer)));
                    System.out.println(version + " cipherSuiteNonEmpty="
                            + !socket.getSession().getCipherSuite().isBlank());
                    System.out.println(version + " peerCertificatePresent="
                            + (socket.getSession().getPeerCertificates().length > 0));
                }
            } finally {
                executor.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: java LoopbackTlsHandshakeDemo server.p12 trust.p12 password");
        }
        char[] password = args[2].toCharArray();
        try {
            SSLContext server = serverContext(Path.of(args[0]), password);
            SSLContext client = clientContext(Path.of(args[1]), password);
            run("TLSv1.3", server, client);
            run("TLSv1.2", server, client);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Biên dịch và chạy trên Java 17+ (đứng tại thư mục chứa source, `$t` được tạo ở phần trên):

```powershell
javac --release 17 -encoding UTF-8 -d $t LoopbackTlsHandshakeDemo.java
java -cp $t LoopbackTlsHandshakeDemo (Join-Path $t "server.p12") (Join-Path $t "trust.p12") $pw
```

**Output chính xác đã kiểm thử** với runtime SunJSSE có TLS 1.2 và TLS 1.3:

```text
TLSv1.3 negotiated=TLSv1.3
TLSv1.3 peersAgree=true
TLSv1.3 cipherSuiteNonEmpty=true
TLSv1.3 peerCertificatePresent=true
TLSv1.2 negotiated=TLSv1.2
TLSv1.2 peersAgree=true
TLSv1.2 cipherSuiteNonEmpty=true
TLSv1.2 peerCertificatePresent=true
```

**Không in tên cipher suite cụ thể** để tránh tạo một output giả định cố định: selection phụ thuộc provider, policy, certificate, supported groups và phiên bản JDK. Chỉ kiểm `getCipherSuite()` không rỗng; khi chẩn đoán thực, in tên suite negotiated trong môi trường có quyền, sau đó đối chiếu với policy.

### 6.3 Đọc kết quả và bảo đảm an toàn

- `TLSv1.3 negotiated=TLSv1.3` là **giá trị của `SSLSession` sau successful handshake**, khác hẳn dòng `supportedProtocols` hoặc `enabledProtocols` từ inventory.
- `peersAgree=true` chứng minh server và client cùng thấy phiên bản negotiated và khớp phiên bản được cấu hình cho lần test đó.
- `peerCertificatePresent=true` cho biết SSLSession có peer certificate. Trong code, **TrustManagerFactory** đã xác minh trust theo truststore demo và **endpoint identification** được bật. Dòng boolean này **đứng riêng không đủ chứng minh** certificate chain/hostname đúng nếu code không bật các cơ chế đó.
- Demo chỉ chạy trên loopback, không kết nối host bên ngoài. Truststore chỉ tin certificate test được tạo; không import cert từ bên gửi không xác thực vào truststore sản phẩm.
- Server nhận một kết nối trong background thread (không dùng lại engine state giữa các phiên); thread executor kết thúc sau mỗi test. Với server thật, cần timeout, limit request, resource lifecycle và cấu hình TLS quản lý tập trung.
- Nếu runtime có security policy cấm TLS 1.2 hoặc 1.3, một phép test có thể fail; **đó là tín hiệu chính sách của môi trường**, không phải lý do bỏ policy. Hãy kiểm `getEnabledProtocols()` và `jdk.tls.disabledAlgorithms` trước khi chọn testcase tương ứng.

Dọn dẹp dữ liệu test:

```powershell
# Chỉ xóa đúng thư mục demo do phần 6.1 tạo, không dùng cho dữ liệu thật.
if ($t -like (Join-Path $env:TEMP "tls-protocol-lesson-*")) {
    Remove-Item -LiteralPath $t -Recurse -Force
}
```

Xóa file bình thường **không bảo đảm secure erase** khỏi SSD, snapshot, backup; vì vậy chỉ dùng test keys và password mẫu. **Không hardcode password/secret** trong ứng dụng thật.

## 7. Cấu hình JSSE: thứ tự ưu tiên và phạm vi tác động

Java có hai nhóm cấu hình quan trọng:

- **System properties** như `jdk.tls.client.protocols`, `jdk.tls.server.protocols`, `https.protocols`, thường nhận qua `-D...` khi khởi động JVM và tác động theo phạm vi của API/provider.
- **Security properties** như `jdk.tls.disabledAlgorithms` hay `jdk.certpath.disabledAlgorithms`, đọc bằng `java.security.Security.getProperty` và cấu hình trong môi trường `java.security`. Chúng có thể **cấm** protocol/algorithm ngay cả khi application đặt allowed/enabled list.

**Không nhầm `System.getProperty("jdk.tls.disabledAlgorithms")` với `Security.getProperty("jdk.tls.disabledAlgorithms")`.** Giá trị chính sách TLS của Oracle/OpenJDK JSSE là Java Security property, không phải chỉ một system property thông thường.

### 7.1 Những property phải biết

| Property/cấu hình | Phạm vi chính | Cách hiểu đúng |
| --- | --- | --- |
| `jdk.tls.disabledAlgorithms` (**Security**) | JSSE protocol, cipher, key exchange/signature/algorithm restrictions | Có thể chặn TLSv1/TLSv1.1/SSLv3 và thuật toán yếu ngay cả nếu enabled tường minh |
| `jdk.certpath.disabledAlgorithms` (**Security**) | Certificate path verification | Có thể từ chối chain dùng key size/thuật toán yếu dù TLS version có chung |
| `jdk.tls.client.protocols` (**System**) | Default client protocol list của **SunJSSE** | Giới hạn phiên bản dùng cho client defaults; ứng dụng `setEnabledProtocols` tường minh có thể override list nhưng không vượt security restrictions |
| `jdk.tls.server.protocols` (**System**) | Default server protocol list của **SunJSSE**, generic context | Có scope riêng; version-specific context hoặc explicit set có thể bỏ qua setting default |
| `https.protocols` (**System**) | Mặc định của `HttpsURLConnection` | **Không phải** công tắc toàn bộ kết nối TLS/`java.net.http.HttpClient`/Netty/gRPC |
| `jdk.tls.client.cipherSuites` / `jdk.tls.server.cipherSuites` (**System**) | Default cipher suites trong SunJSSE | Không vượt allowed algorithms, certificates, named groups, phiên bản hoặc peer |
| `jdk.tls.namedGroups` (**System**) | Named finite-field/elliptic-curve groups | Có thể làm TLS 1.3/1.2 handshake thất bại nếu peer không có group chung |
| `javax.net.ssl.keyStore` / `javax.net.ssl.trustStore` (System) | Default key/trust material cho một số factory/default managers | Không tự bảo đảm hostname/identity; explicit `SSLContext` có thể dùng store khác |
| `SSLParameters.setProtocols` / `SSLSocket.setEnabledProtocols` | Object/session client/server cụ thể | Xác định list phiên bản trực tiếp; vẫn cần peer + security policy phù hợp |
| `SSLContext.getInstance("TLS")` | JSSE context thuật toán generic | Không có nghĩa một phiên bản đã negotiated; hỗ trợ nhiều TLS versions tùy provider |

**Thứ tự cấu hình cho default enabled list** trong SunJSSE thường có thể hiểu là:

```text
Explicit application setting (socket/engine SSLParameters)
        > relevant SunJSSE system property
        > JSSE provider defaults

Sau đó vẫn chịu ràng buộc của Java Security properties
(ví dụ jdk.tls.disabledAlgorithms, jdk.certpath.disabledAlgorithms),
thuật toán/curve/certificates và peer capabilities.
```

Không nên diễn giải dấu “`>`” là cơ chế bỏ qua chính sách security. Nó chỉ nói **cấu hình enabled/default list** có ưu tiên; **mức cấm** của `jdk.tls.disabledAlgorithms` vẫn áp dụng trong negotiation.

Ví dụ khởi động demo inventory với cấu hình client default **TLSv1.3** (PowerShell):

```powershell
# Demo: cấu hình system property trước khi context được tạo.
java "-Djdk.tls.client.protocols=TLSv1.3" TlsProtocolInventoryDemo
```

Chạy lại bằng terminal/JVM mới và so `enabledProtocols`. **Không** suy mọi application đều dùng same default: chúng có thể tạo riêng `SSLContext`, gọi `setEnabledProtocols`, chạy provider khác hoặc do framework cấu hình. Một số property được JSSE đọc lúc khởi tạo provider/context; đặt giữa lúc ứng dụng đã chạy có thể không cập nhật các context hiện có.

Ví dụ với một `SSLSocket` đã tạo:

```java
// Đoạn minh họa trong phương thức Java, không phải chương trình độc lập.
String[] desired = { "TLSv1.3", "TLSv1.2" };
socket.setEnabledProtocols(desired);
// Đọc lại từ chính socket rồi mới bắt tay.
System.out.println(java.util.Arrays.toString(
        socket.getEnabledProtocols()));
```

Code trên **chưa** kiểm tra handshake. Với server có nhiều client legacy, chọn list theo chính sách khả năng tương thích thật; không bật SSLv3/TLS 1.0/TLS 1.1 hoặc weak cipher vì một lời báo lỗi “no common protocol” nếu không có ngoại lệ bảo mật được duyệt.

### 7.2 Cách đọc nhanh cấu hình JVM bằng CLI

Java JDK cung cấp:

```powershell
# Tóm tắt enabled TLS protocols/suites theo JDK/provider hiện tại.
keytool -showinfo -tls

# Trong môi trường JDK hỗ trợ tùy chọn này:
java -XshowSettings:security:tls -version
```

Lệnh `keytool -showinfo -tls` đã được kiểm thử trên runtime JDK sử dụng trong bài, phần mở đầu:

```text
Enabled Protocols
-----------------
TLSv1.3
TLSv1.2

Enabled Cipher Suites
---------------------
TLS_AES_256_GCM_SHA384
TLS_AES_128_GCM_SHA256
TLS_CHACHA20_POLY1305_SHA256
```

Danh sách còn **nhiều suite phía sau** (đã cố ý chỉ in ba dòng đầu để minh họa, **không coi đây là toàn output CLI**). Lệnh này hữu ích để xem enabled profile ở JDK process nhưng **không xác thực cấu hình cụ thể của mọi ứng dụng** vốn có thể override bằng provider/SSLContext/socket settings.

Nếu muốn xem security property **thực tế** tại runtime mà không sửa policy, trong JShell Java 17:

```java
System.out.println(java.security.Security.getProperty(
        "jdk.tls.disabledAlgorithms"));
System.out.println(java.security.Security.getProperty(
        "jdk.certpath.disabledAlgorithms"));
```

Đây là **đoạn Java trong JShell** hoặc method, không phải lệnh PowerShell độc lập. Không in property đó như một “mật khẩu”; đây là policy cấu hình, nhưng cũng không đưa toàn debug log production ra kênh công khai.

## 8. Đọc cấu hình cipher suites và các extensions liên quan

**Protocol intersection chỉ là điều kiện cần, không đủ.** Hai peer có thể cùng cho TLS 1.3 nhưng vẫn handshake fail vì:

- Không có **cipher suite** chung được phép, hoặc khóa/cipher bị policy chặn.
- Không có **named group/key share** chung: `secp256r1`, `x25519`, `ffdhe2048`... tùy provider và protocol.
- Không có **signature scheme** tương thích certificate/key manager; ví dụ certificate chỉ hỗ trợ thuật toán ký không dùng được ở TLS 1.3.
- Certificate chain không được tin, thiếu intermediate, hết hạn, không đúng SAN/hostname, EKU/KU không phù hợp hoặc bị `jdk.certpath.disabledAlgorithms` từ chối.
- Server yêu cầu client certificate và client chưa cấp đúng chứng thư/private key.
- Lỗi **SNI** routing, **ALPN** (HTTP/2 vs HTTP/1.1), proxy, load balancer hay mTLS policy.
- Unsupported critical extension, revocation failure hoặc policy TLS riêng của framework.

**ALPN không phải TLS protocol version.** Khi HTTP/2 dùng TLS, ứng dụng có thể dùng ALPN chọn `h2`; TLS version như `TLSv1.3` là lớp **khác**. `SSLParameters.setApplicationProtocols(...)` và `SSLSocket.getApplicationProtocol()` phục vụ ALPN, còn `SSLSession.getProtocol()` trả TLS version. SNI chọn danh tính/certificate server theo hostname; không phải nơi đặt TLSv1.2/TLSv1.3.

### 8.1 Tên cipher suite nhìn sao cho đúng?

| Cipher suite | Version chủ yếu | Ý nghĩa |
| --- | --- | --- |
| `TLS_AES_128_GCM_SHA256` | TLS 1.3 | AES-128-GCM AEAD, SHA-256 trong HKDF key schedule |
| `TLS_AES_256_GCM_SHA384` | TLS 1.3 | AES-256-GCM AEAD, SHA-384 |
| `TLS_CHACHA20_POLY1305_SHA256` | TLS 1.3 | ChaCha20-Poly1305 AEAD, SHA-256 |
| `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` | TLS 1.2 | ECDHE key exchange, RSA certificate signature/auth, AES-128-GCM |
| `TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384` | TLS 1.2 | ECDHE, ECDSA authentication, AES-256-GCM |
| `TLS_RSA_WITH_AES_128_CBC_SHA` | Legacy TLS 1.2-era | RSA key transport và CBC; **không dùng** cho cấu hình mới |

Ngay cả khi `getSupportedCipherSuites()` chứa một tên legacy, system policy có thể cấm hoàn toàn. Ưu tiên default an toàn của JDK và hạn chế suites **theo chính sách đã kiểm chứng**; một allow-list tự viết nhưng quá chặt hay không phù hợp certificate có thể ngăn TLS 1.3 dù `enabledProtocols` đúng.

TLS 1.3 sử dụng key schedule khác TLS 1.2; khi troubleshoot không mong thấy `ServerKeyExchange` theo định dạng TLS 1.2 trong TLS 1.3. Một TLS record có `legacy_record_version` hoặc một `ClientHello` có `legacy_version=0x0303` **không có nghĩa** negotiated TLS 1.2: TLS 1.3 dùng `supported_versions` extension để đàm phán version thực tế. Hãy xem `SSLSession.getProtocol()` hoặc handshake trace `supported_versions` và ServerHello đúng ngữ cảnh.

## 9. Chẩn đoán lỗi handshake theo lớp

| Triệu chứng | Khả năng gây ra | Cách kiểm tra |
| --- | --- | --- |
| `SSLHandshakeException: No appropriate protocol` | Không có version/cipher phù hợp, có thứ bị disabled bởi policy | In enabled/supported của **hai phía**, security property và cipher suites |
| `Received fatal alert: protocol_version` | Peer từ chối protocol versions được đề xuất | So TLS versions và server-side policy, không bật giao thức lỗi thời một cách vội vàng |
| `Received fatal alert: handshake_failure` | **Nhiều khả năng**: cipher, key exchange group, sig scheme, certificate, client auth, SNI | Đọc handshake trace và peer config; không kết luận chỉ từ alert |
| `PKIX path building failed` | Truststore thiếu CA/intermediate, chain sai, cert không hợp lệ | Dùng đúng truststore, chain và path validation; không trust-all |
| `No subject alternative names matching ...` | Host/IP không phù hợp SAN | Cấp lại cert đúng DNS/iPAddress SAN hoặc kết nối tới hostname thật |
| `No available authentication scheme` | Server không có certificate/key/algorithm tương thích negotiated settings | Xem KeyManagerFactory, keyStore, key algorithm và sig schemes |
| Handshake dùng TLSv1.2 dù client hỗ trợ TLSv1.3 | Server không enable 1.3, TLS terminator/proxy hoặc policy khác | Xem `SSLSession.getProtocol` ở đúng endpoint và peer config |
| `getSupportedProtocols()` có TLSv1 nhưng handshake không dùng được | TLSv1 nằm trong `jdk.tls.disabledAlgorithms` hoặc bị policy khác cấm | Kiểm tra security property; không sửa policy chỉ vì supported |
| `SSLSession.getProtocol()` chưa có ý nghĩa | Socket chưa handshake hoặc handshake fail | Gọi `startHandshake` và chỉ dùng session khi thành công |
| Java code set `SSLParameters` nhưng kết quả không đổi | Chưa gọi `socket.setSSLParameters(params)`, đặt sau handshake, hoặc dùng socket khác | In params/objects ngay trước handshake |
| HTTPS URL thành công nhưng raw SSLSocket fail | Hai đường đi có trust, hostname, default protocols khác nhau | Đọc cấu hình đúng stack/framework của từng call |
| TLS protocol đúng nhưng HTTP/2 fail | ALPN không đồng ý `h2`, server/application policy | Tách TLS `getProtocol` khỏi ALPN `getApplicationProtocol` |
| Kết nối qua LB/CDN TLS 1.3 nhưng backend cũ | TLS termination và re-encryption diễn ra ở hai connection khác | Kiểm tra từng hop, không dùng kết quả frontend để suy backend |

### Debug JSSE

Trong môi trường thử nghiệm có quyền truy cập:

```powershell
# Ví dụ bật trace JSSE cho chương trình local.
java "-Djavax.net.debug=ssl,handshake" -cp $t LoopbackTlsHandshakeDemo (Join-Path $t "server.p12") (Join-Path $t "trust.p12") $pw
```

Log JSSE có thể rất dài, chứa cấu trúc handshake, certificate metadata, hostname, thông số bảo mật và tùy flags có thể hiện byte nhạy cảm. **Không bật các chế độ dump/key logger trong production hoặc gửi nguyên log công khai**. Chỉ dùng trên test fixtures, lưu vào nơi có quyền phù hợp và xóa sau khi chẩn đoán.

Khi đọc trace, tìm tuần tự: `ClientHello`, `supported_versions`, `ServerHello`, selected cipher suite, `Certificate`/certificate validation, handshake Finished. Không nhầm `legacy_version` với negotiated protocol. Với TLS 1.3, nhiều handshake messages sau ServerHello được bảo vệ; logger có quyền trong process có thể nhìn nhiều hơn packet capture ngoài mạng.

## 10. Cấu hình thực hành theo mô hình bảo mật

**Môi trường mới có client/server hiện đại:** thường cho phép TLS 1.3 và TLS 1.2 theo chính sách tổ chức, với TLS 1.3 được ưu tiên nếu hai phía tương thích. Đừng tắt TLS 1.2 chỉ vì có TLS 1.3 nếu còn peer hợp lệ cần TLS 1.2. Tuy nhiên nếu chính sách yêu cầu **chỉ TLS 1.3**, hãy áp dụng cả client/server và kiểm thử tương thích.

**Có legacy service:** trước tiên kiểm kê endpoint, chứng thư, cipher suites, named groups, load balancer và JDK version; lên lịch upgrade. **Không** tự hạ xuống TLS 1.0/1.1, SSLv3, RC4, 3DES hay cipher suite NULL/anonymous để che lỗi negotiation. Nếu phải duy trì legacy ngoài ý muốn, cần đánh giá rủi ro và cô lập có thời hạn theo chính sách bảo mật.

**Trong code JSSE:** sử dụng generic `SSLContext("TLS")`, để provider/security defaults an toàn làm cơ sở, cấu hình rõ ràng protocols và cipher suites khi có chính sách. Xác minh trust chain, hostname, EKU/KU, key sizes và certificate lifecycle qua trust manager/JSSE. Nếu dùng `HttpClient`/Netty/gRPC/server framework, kiểm tra nơi stack đó cấu hình SSL; **không giả định** mọi `-Dhttps.protocols` đều có tác dụng.

**Giám sát thực tế:** đo negotiated TLS version/cipher suite **trên connections đã thành công**, theo endpoint/hop và khoảng thời gian. Không coi thông tin hỗ trợ do scanner trả về (hoặc JDK source code) là bằng chứng negotiated. Không ghi session secrets hoặc dữ liệu chứng thực nhạy cảm trong telemetry.

**Thay đổi cấu hình:** deploy vào staging, chạy integration handshake tests cả client/server, test protocol intersection và cert trust, quan sát lỗi theo version. Các bản update JDK/security policy có thể thay đổi defaults/disabled list, nên không hardcode một snapshot của một JDK làm “sự thật vĩnh viễn”.

## 11. Các hiểu nhầm cần loại bỏ

**“`SSLContext.getInstance("TLS")` nghĩa là TLS 1.0?”** Không. `"TLS"` là tên generic context có thể hỗ trợ nhiều versions; đọc `getEnabledProtocols` và handshake thực.

**“Supported có TLSv1.1 tức là server cho phép TLSv1.1?”** Không. Supported có thể liệt kê các versions disabled; cấu hình socket, security policy và peer mới quyết định có negotiation hay không.

**“`setEnabledProtocols({"TLSv1"})` sẽ vượt `jdk.tls.disabledAlgorithms`?”** Không. Security restrictions vẫn áp dụng, dù API chấp nhận một tên supported.

**“TLS 1.3 suite `TLS_AES_128_GCM_SHA256` dùng RSA hay ECDHE?”** Tên suite **không mã hóa** thuật toán key agreement/certificate authentication; xem negotiated groups/signature schemes/handshake.

**“TLS 1.3 luôn có forward secrecy bất kể PSK?”** Không. Cơ chế PSK-only không có cùng bảo đảm như fresh (EC)DHE; phải xem mode/protocol thật.

**“TLS 1.3 0-RTT đồng nghĩa truyền mọi request sớm an toàn?”** Không. Early data có rủi ro replay và có thể không được JSSE/app hỗ trợ; giao thức cần bảo vệ/idempotency policy.

**“Sau khi gọi `getEnabledProtocols` có thể ghi negotiated version vào logs?”** Chưa. Chỉ `SSLSession.getProtocol` sau handshake thành công mới là version thực.

**“Chỉ cần TLS 1.3 là khỏi kiểm certificate, hostname?”** Sai. TLS version không thay trust, EKU/KU, SAN/hostname, revocation hoặc policy.

**“`https.protocols` điều khiển mọi kết nối SSL/TLS Java?”** Không. Nó chủ yếu ảnh hưởng `HttpsURLConnection`, không tự áp vào mọi HTTP client, server hay thư viện.

**“Packet TLS record hiển thị 0x0303 chắc negotiated TLS 1.2?”** Không. TLS 1.3 dùng compatibility/legacy fields; phải kiểm `supported_versions` và session.

**“Thất bại handshake chắc do không có TLS 1.3?”** Không. Lỗi cũng có thể do truststore, SAN, cipher suite, named group, signature scheme, SNI, ALPN hoặc client auth.

## 12. Tự kiểm tra

1. **Ba mức protocol quan trọng nhất khi debug?** Supported, enabled và **negotiated**, cộng thêm security restrictions và peer capability.
2. **API Java nào trả negotiated TLS version?** `SSLSession.getProtocol()` sau successful handshake.
3. **`getSupportedProtocols()` có thể chứa protocol bị disabled không?** Có; SunJSSE test hiển thị TLS 1.0/1.1 và SSLv3 dù không enabled.
4. **Security property vô hiệu hóa protocol/suite là gì?** `jdk.tls.disabledAlgorithms`; đọc bằng `Security.getProperty`.
5. **`jdk.tls.client.protocols` có phải `https.protocols` không?** Không; scope khác nhau, property thứ hai tập trung `HttpsURLConnection`.
6. **TLS 1.2 cipher suite khác TLS 1.3 như thế nào?** 1.2 thường chứa key exchange/auth/symmetric/hash; 1.3 chứa AEAD + HKDF hash, nhóm/chữ ký negotiate riêng.
7. **TLS 1.3 có còn RSA key transport không?** Không; RSA certificate/signature vẫn có thể dùng, nhưng không là RSA key transport kiểu cũ.
8. **TLS 1.3 luôn có 0-RTT không?** Không, optional và có rủi ro replay.
9. **Nếu client bật TLSv1.3 và TLSv1.2, server chỉ bật TLSv1.2, có thể negotiate gì?** TLSv1.2 nếu các điều kiện khác đạt.
10. **Nếu cả hai bật TLSv1.3, handshake chắc thành công không?** Không; cipher suites, groups, sig scheme, trust, hostname và policy có thể gây fail.
11. **Tại sao demo bật `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`?** Để xác minh IP/DNS SAN, không chỉ trust certificate.
12. **`SSLSession.getCipherSuite()` cho biết gì?** Cipher suite của kết nối thành công, không thay thế việc hiểu group/signature trong TLS 1.3.
13. **Trường `legacy_version=0x0303` của TLS 1.3 chứng minh TLSv1.2 negotiated?** Không; xem supported_versions/ServerHello và SSLSession.
14. **Có nên gỡ TLSv1 khỏi disabledAlgorithms vì code legacy test fail?** Không mặc định; cần nâng cấp hoặc phê duyệt ngoại lệ an ninh rõ ràng.
15. **Phân biệt ALPN với TLS version?** ALPN chọn application protocol (ví dụ `h2`), TLS version là `TLSv1.2`/`TLSv1.3`.
16. **Có thể lấy protocol thực từ socket chưa kết nối như chương trình inventory?** Không; chỉ có supported/enabled/default, chưa negotiated.
17. **Tại sao không đoán cả hệ thống hỗ trợ TLS theo một SSLContext?** Mỗi client/server/framework/provider/hop có cấu hình riêng.
18. **Hai phía cùng có TLSv1.2 nhưng `SSLHandshakeException` xảy ra, kiểm gì tiếp?** Trust/certificate, cipher suite, named group, signature scheme, security policy, SNI và logs.
19. **Khi nào có `protocol_version` alert?** Khi peer từ chối version được đề xuất hoặc không đàm phán được version phù hợp; không đủ để suy ra toàn bộ nguyên nhân.
20. **Cách xác minh sau deploy?** Integration handshake thật qua đúng endpoint, kiểm session protocol/cipher, certificate identity và chính sách logging/monitoring.

## Tài liệu chính thức

- [Oracle Java 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html)
- [Oracle Java 17 — JDK Providers Documentation, SunJSSE protocols và cipher suites](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html)
- [Oracle Java 17 — Standard Algorithm Names, SSLContext](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html)
- [SSLContext (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [SSLSocket (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html)
- [SSLParameters (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html)
- [SSLSession (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html)
- [SSLEngine (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html)
- [RFC 5246 — TLS 1.2](https://www.rfc-editor.org/rfc/rfc5246.html)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html)
