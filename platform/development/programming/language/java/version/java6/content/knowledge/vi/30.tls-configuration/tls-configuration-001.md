# SSLParameters và gom cấu hình cho một endpoint

## 1. Vì sao cần SSLParameters khi một ứng dụng Java dùng TLS?

Khi một ứng dụng Java tạo kết nối TLS, chúng ta thường cần đồng thời quyết định: **những phiên bản TLS nào được chấp nhận**, **cipher suites nào được phép**, **server identity nào phải được xác minh**, có dùng **SNI/ALPN** không và server có **yêu cầu chứng chỉ client (mTLS)** hay không. Nếu rải các thao tác cấu hình vào nhiều handler, chúng dễ bị không nhất quán: endpoint A chỉ dùng TLS 1.3 nhưng endpoint B vô tình hỗ trợ giao thức cũ; endpoint C có truststore hợp lệ nhưng quên kiểm tra hostname.

**`javax.net.ssl.SSLParameters`** gom các tham số **đàm phán TLS của một endpoint** vào một đối tượng. Đây là API được giới thiệu từ **Java 6 (Since: 1.6)** và **vẫn hiện hành trong Java SE 26**. Các ứng dụng hiện đại nên dùng nó cùng `SSLContext` và những đối tượng kết nối như `SSLSocket`, `SSLServerSocket`, `SSLEngine` hoặc các HTTP clients/servers có hỗ trợ cấu hình JSSE.

**Phân biệt quan trọng:** `SSLParameters` **không chứa private key, certificate chain hoặc truststore**. Chúng thuộc `SSLContext`, `KeyManagerFactory` và `TrustManagerFactory`. SSLParameters chỉ mô tả một phần **policy của handshake**. Một kết nối được coi an toàn khi **identity/trust đúng, hostname được kiểm tra, algorithms phù hợp, constraints/expiry/revocation xử lý đúng** và ứng dụng triển khai trên đúng endpoint.

~~~text
        KeyStore / keys                    TrustStore / trusted anchors
                |                                    |
                v                                    v
       KeyManagerFactory                   TrustManagerFactory
                \                                    /
                 \                                  /
                  +---------- SSLContext ----------+
                                |                  |
                                |                  +--> SSLServerSocket / SSLSocketFactory
                                |                  +--> SSLEngine
                                |
                  SSLParameters mới cho TỪNG endpoint
                                |
           +--------------------+-----------------------+
           |                    |                       |
     protocols/ciphers    hostname/SNI/ALPN        clientAuth policy
           |                    |                       |
           +--------------------+-----------------------+
                                |
                  apply BEFORE TLS handshake
                                |
                                v
                   TLS handshake + peer validation
                                |
                                v
             SSLSession negotiated protocol/cipher/identity
~~~

### Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt `SSLContext`, `SSLParameters` và `SSLSession`, cũng như **key material** với **TLS handshake policy**.
2. So sánh `getDefaultSSLParameters()` và `getSupportedSSLParameters()`, không tự bật thuật toán chỉ vì provider báo supported.
3. Chọn TLS 1.3 hoặc TLS 1.2 khi có yêu cầu tương thích đã được duyệt; tránh **SSLv3/TLS 1.0/1.1** và các cipher suites bị cấm bởi policy.
4. Áp dụng một cấu hình nhất quán bằng `SSLSocket.setSSLParameters`, `SSLServerSocket.setSSLParameters` và `SSLEngine.setSSLParameters` **trước handshake**.
5. Dùng `setEndpointIdentificationAlgorithm("HTTPS")` ở client mode để xác minh hostname, không nhầm SNI với hostname verification.
6. Cấu hình `setServerNames(...)` bằng `SNIHostName`, và `setApplicationProtocols(...)` cho ALPN khi endpoint hỗ trợ.
7. Phân biệt `setNeedClientAuth(true)`, `setWantClientAuth(true)` và no-client-auth; biết mTLS cần cả client key và server trust.
8. Hiểu vì sao `HttpClient.Builder.sslParameters(...)` có thể **bỏ qua một số tham số như application protocol list** và HTTPS client không được vô hiệu hóa hostname checks.
9. Gom policy cho từng endpoint thành đối tượng cấu hình tạo **SSLParameters mới**, tránh reuse state mutable giữa các connections.
10. Chạy hai chương trình Java 17+ gồm kiểm thử policy và **TLS 1.3 loopback handshake thật**, có SAN, truststore, ALPN và negative hostname test.

## 2. Các API và nguồn gốc phiên bản

| API | Module/package | Vai trò |
| --- | --- | --- |
| `SSLParameters` | `java.base/javax.net.ssl` | Gom protocol/cipher/identity/SNI/ALPN/client-auth policy |
| `SSLContext` | `java.base/javax.net.ssl` | Context tạo TLS sockets/engines, kết hợp key/trust material |
| `KeyManagerFactory` | `java.base/javax.net.ssl` | Cung cấp identity private key + certificate chain |
| `TrustManagerFactory` | `java.base/javax.net.ssl` | Cung cấp trust managers cho kiểm chứng peer certificate |
| `SSLSocket` | `java.base/javax.net.ssl` | TLS trên TCP ở client/server mode |
| `SSLServerSocket` | `java.base/javax.net.ssl` | TLS listening socket; parameters áp dụng cho **newly accepted** connections |
| `SSLEngine` | `java.base/javax.net.ssl` | TLS với non-blocking, transport-agnostic buffers |
| `SSLSession` | `java.base/javax.net.ssl` | Giao thức, cipher suite, peer/session thông tin sau handshake |
| `SNIHostName` | `java.base/javax.net.ssl` | TLS Server Name Indication kiểu hostname |
| `SNIMatcher` | `java.base/javax.net.ssl` | Server-side nhận diện/giới hạn SNI nếu cần |
| `HttpsURLConnection` | `java.base/javax.net.ssl` | HTTPS API với xác minh hostname mặc định |
| `HttpClient.Builder.sslParameters` | `java.net.http` | Cấu hình SSLParameters cho Java HttpClient (có tham số được implementation quản lý) |
| `HttpsConfigurator` / `HttpsParameters` | `jdk.httpserver` | Cấu hình từng HTTPS connection của JDK HttpsServer |
| `keytool` | JDK utility | Tạo/import/export keys và certificates cho thử nghiệm |

### 2.1. “API từ Java 6” không đồng nghĩa mọi method có từ Java 6

`SSLParameters` có từ Java 6. Tuy nhiên:

- `setEndpointIdentificationAlgorithm("HTTPS")`: có từ **Java 7**.
- `setServerNames(...)` / `SNIHostName`: được dùng từ **Java 8**.
- `setApplicationProtocols(...)` / ALPN: có từ **Java 9**.
- `java.net.http.HttpClient`: có từ **Java 11**.
- Một số setters như `setSignatureSchemes` hoặc `setNamedGroups` có availability phụ thuộc JDK version; **không mặc định mọi JDK 17 đều có method mới**.

Bài dùng **Java 17+** để ví dụ có thể compile/run trên JDK được hỗ trợ. Không cung cấp cách dùng TLS/SSL cũ làm khuyến nghị cho ứng dụng mới; legacy cipher/protocol lists chỉ được nhắc để **giải thích vì sao phải loại bỏ**.

## 3. SSLContext chứa gì, SSLParameters không chứa gì?

`SSLContext` đại diện cho một TLS provider context được khởi tạo với:

- `KeyManager[]`: chọn private key/certificate khi endpoint cần trình bày chứng chỉ (server TLS hoặc client mTLS).
- `TrustManager[]`: kiểm tra chứng chỉ của peer, thông thường từ truststore hoặc PKIX/enterprise policy.
- `SecureRandom`: nguồn ngẫu nhiên cho TLS engine theo provider.

~~~java
SSLContext context = SSLContext.getInstance("TLS");
context.init(keyManagers, trustManagers, new SecureRandom());
~~~

**Đoạn trích:** `keyManagers` và `trustManagers` phải được dựng trước; null có nghĩa provider dùng lựa chọn mặc định phù hợp, **không phải “trust tất cả certificate”**. Trường hợp training chỉ kiểm tra API có thể dùng context không có server keys, nhưng để **chạy TLS server thật** phải có private key + certificate. Client muốn kiểm chứng self-signed cert trong môi trường test cần trust anchor được cấu hình riêng, không được đặt trust-all manager.

### 3.1. SSLParameters là chính sách, không phải trust anchor

~~~java
SSLParameters params = context.getDefaultSSLParameters();
params.setProtocols(new String[] {"TLSv1.3"});
params.setCipherSuites(new String[] {"TLS_AES_128_GCM_SHA256"});
~~~

**Đoạn trích:** cấu hình trên nói về **TLS version và cipher-suite policy**, không tạo keys, không đọc truststore và không tự bật TLS khi chưa apply lên socket/engine. Một endpoint có certificate hết hạn hoặc không khớp hostname vẫn phải bị từ chối, dù version/cipher suite đều đúng.

### 3.2. SSLSession phản ánh handshake thực tế

Sau `startHandshake()` trên `SSLSocket`:

~~~java
String negotiatedTls = socket.getSession().getProtocol();
String negotiatedCipher = socket.getSession().getCipherSuite();
String negotiatedAlpn = socket.getApplicationProtocol();
~~~

Đây là **đoạn trích**, socket phải đã handshake thành công. `SSLParameters.getProtocols()` cho biết **danh sách được cho phép**, còn `SSLSession.getProtocol()` cho biết **phiên bản thật sự đã đàm phán**. Đừng ghi log “đã kết nối TLS 1.3” chỉ vì params cho phép TLS 1.3.

## 4. Default khác supported: kiểm soát đúng TLS algorithms

`SSLContext.getDefaultSSLParameters()` chứa các lựa chọn **được bật mặc định** theo provider và JDK security policy; `getSupportedSSLParameters()` chứa tập **provider nhận biết/hỗ trợ về mặt kỹ thuật**. Một protocol/cipher suite có thể supported nhưng **không enabled**, và những chính sách `jdk.tls.disabledAlgorithms`/`jdk.certpath.disabledAlgorithms` có thể cấm nó khi handshake dù application cố cấu hình.

### 4.1. Đừng lấy mọi supported cipher để “tăng tương thích”

~~~java
SSLParameters supported = context.getSupportedSSLParameters();
// Phản ví dụ: cho phép toàn bộ supported suites một cách mù quáng.
params.setCipherSuites(supported.getCipherSuites());
~~~

Đây là **phản ví dụ**, không phải hướng production. Supported có thể rộng hơn enabled và không phù hợp với security policy. Lựa chọn an toàn hơn là **explicit allowlist**, giao với default-enabled/supported, kiểm tra fail-closed nếu không có giao.

### 4.2. Lựa chọn minh họa TLS 1.3

~~~java
private static void requireEnabled(SSLContext context,
                                   String protocol, String cipher) {
    SSLParameters defaults = context.getDefaultSSLParameters();
    SSLParameters supported = context.getSupportedSSLParameters();
    if (!Arrays.asList(defaults.getProtocols()).contains(protocol)
            || !Arrays.asList(supported.getProtocols()).contains(protocol)
            || !Arrays.asList(defaults.getCipherSuites()).contains(cipher)
            || !Arrays.asList(supported.getCipherSuites()).contains(cipher)) {
        throw new IllegalArgumentException("TLS policy not enabled/supported");
    }
}
~~~

**Đoạn trích:** cần `java.util.Arrays` và `SSLContext/SSLParameters`. Ví dụ chọn **`TLSv1.3`** và **`TLS_AES_128_GCM_SHA256`** vì chúng được bật ở OpenJDK 24 thử nghiệm, **không phải ép toàn bộ ứng dụng chỉ dùng cipher đó**. Production cần policy linh hoạt có allowlist cho nhiều cipher suites an toàn, đáp ứng client compatibility và yêu cầu tuân thủ.

### 4.3. Không dùng fallback nguy hiểm

Nếu peer chỉ hỗ trợ TLS 1.0/1.1, đừng tự giảm xuống giao thức cũ để tránh exception. Nên từ chối handshake và yêu cầu cập nhật peer. Với yêu cầu tương thích TLS 1.2 thực tế, chọn các cipher suites AEAD hiện hành, tắt các algorithms không an toàn theo JDK/provider và kiểm thử interoperability. **Không vô hiệu hóa `jdk.tls.disabledAlgorithms` chỉ để thành công một kết nối không phù hợp**.

### 4.4. Security properties và provider policy có thể thắng code

TLS security là tổng hợp của:

- protocol/cipher suite được SSLParameters cho phép;
- những algorithms provider thực sự hỗ trợ;
- JDK `java.security` properties như `jdk.tls.disabledAlgorithms`;
- certificate validity, PKIX trust, key usage, certificate path constraints;
- options của TLS client/server, authentication và endpoint identity;
- TLS termination / proxy behavior và JDK provider được deploy.

Nếu policy fail-closed ngay khi thiếu TLS 1.3/cipher suite yêu cầu, hệ thống không nên tự tìm cách bật SSLv3 hoặc cipher yếu.

## 5. Các getter/setter SSLParameters quan trọng

| Thuộc tính | Getter/setter | Ý nghĩa và lưu ý |
| --- | --- | --- |
| TLS protocols | `getProtocols/setProtocols` | Danh sách versions được phép, ví dụ TLSv1.3 |
| Cipher suites | `getCipherSuites/setCipherSuites` | Danh sách cipher suites cho handshake |
| Endpoint identity | `getEndpointIdentificationAlgorithm/setEndpointIdentificationAlgorithm` | Client kiểm tra peer hostname; dùng `"HTTPS"` |
| Client auth bắt buộc | `getNeedClientAuth/setNeedClientAuth` | Server **từ chối** client không có certificate hợp lệ khi bật |
| Client auth mong muốn | `getWantClientAuth/setWantClientAuth` | Server yêu cầu nhưng có thể chấp nhận client không có cert |
| SNI names | `getServerNames/setServerNames` | Client gửi hostname mong muốn trong ClientHello |
| SNI matcher | `getSNIMatchers/setSNIMatchers` | Server-side chọn/kiểm tra tên từ ClientHello |
| ALPN protocols | `getApplicationProtocols/setApplicationProtocols` | Danh sách application protocols được quảng bá/chọn |
| Cipher order | `getUseCipherSuitesOrder/setUseCipherSuitesOrder` | Ưu tiên cipher order của local side theo provider |
| Algorithm constraints | `getAlgorithmConstraints/setAlgorithmConstraints` | Bổ sung constraints trên những security constraints của runtime |
| Packet size | `getMaximumPacketSize/setMaximumPacketSize` | Giới hạn/nhắc tối đa TLS/DTLS packet size, không phải quota request body |
| Signature schemes/named groups | `getSignatureSchemes/setSignatureSchemes`, `getNamedGroups/setNamedGroups` | Chỉ dùng nếu JDK/provider phiên bản đang chạy hỗ trợ |

**Có null defaults:** một `new SSLParameters()` không nhất thiết có `protocols`/`cipherSuites` được set; `getProtocols()` và `getCipherSuites()` có thể trả `null` trong đối tượng chưa populated. `context.getDefaultSSLParameters()` phù hợp làm nền tảng cho cấu hình endpoint, để tránh vô tình xóa các defaults khác.

### 5.1. SSLParameters là mutable

~~~java
SSLParameters template = context.getDefaultSSLParameters();
template.setProtocols(new String[]{"TLSv1.3"});
socket.setSSLParameters(template);
template.setProtocols(new String[]{"TLSv1.2"});
~~~

**Đoạn trích:** thay đổi template **không nên được dùng làm cách sửa socket đã cấu hình**. Các method set/get thường sao chép danh sách/mảng ở biên API, socket/engine có cấu hình của chính nó; hãy **tạo SSLParameters riêng** và apply cho endpoint mới, không share mutable template giữa các threads.

### 5.2. Gom cấu hình mà không trộn responsibilities

Một thiết kế tốt có thể có:

- `TlsIdentityConfig`: alias/keystore/key manager, certificate lifecycle.
- `TlsTrustConfig`: trust anchors/certificate pinning nếu thực sự cần, PKIX/revocation.
- `TlsHandshakePolicy`: allowlisted protocols/ciphers, SNI/ALPN, clientAuth/hostname verification.
- `EndpointConfig`: endpoint hostname/port, server/client role, timeouts, allowed application protocols.

**SSLParameters chỉ biểu diễn handshake policy của một endpoint, không thay toàn bộ các cấu hình khác.** Áp dụng một hàm tạo policy mới từ cấu hình bất biến, tránh lấy một `SSLParameters` global rồi sửa theo request.

## 6. Hostname verification: yếu tố chống kết nối nhầm máy

### 6.1. Raw SSLSocket và SSLEngine không tự kiểm tra hostname theo mặc định

Với client TLS dựa trên `SSLSocket` hoặc `SSLEngine` tự quản lý, dù certificate chain được trust manager chấp nhận, bạn vẫn phải yêu cầu **peer hostname phù hợp chứng chỉ**. Oracle JSSE guide cảnh báo việc quên endpoint verification có thể khiến kết nối tới server khác vẫn được tin chỉ vì chứng chỉ của nó được trust.

~~~java
SSLParameters params = socket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
socket.startHandshake();
~~~

Đây là **đoạn trích**. `"HTTPS"` là tên chuẩn của endpoint identification algorithm, giúp JSSE kiểm tra host identity trong handshake. **Đặt trước `startHandshake()`**, không bắt đầu truyền sensitive data khi chưa verify.

### 6.2. Hostname phải match SAN

Giả sử client kết nối tới `api.example.com` thì certificate cần có `subjectAltName DNS:api.example.com`, hoặc một SAN wildcard hợp lệ theo rule. Với **IP literal** `127.0.0.1`, certificate nên có `iPAddress SAN:127.0.0.1`; CN không thay SAN IP check.

Trong local TLS demo, certificate được tạo có cả **DNS:localhost** và **IP:127.0.0.1**. Kết nối tới IP loopback được xác minh bằng `setEndpointIdentificationAlgorithm("HTTPS")`; negative test dùng `wrong.example.test` và **bị handshake từ chối**.

### 6.3. SNI không thay hostname verification

**SNI** (*Server Name Indication*) cho phép client nói server name muốn tới ngay trong TLS ClientHello, để một IP chạy nhiều virtual host/certificates. Ví dụ:

~~~java
SSLParameters params = socket.getSSLParameters();
params.setServerNames(List.of(new SNIHostName("api.example.com")));
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
~~~

**Đoạn trích**, import `javax.net.ssl.SNIHostName` và `java.util.List`. Việc server nhận SNI chỉ giúp chọn identity/virtual host; **không chứng minh chứng chỉ trả về thật sự thuộc host đó**. SNI có thể lộ hostname ở ClientHello nếu không có ECH, và không phải cơ chế authentication.

Ở TLS client, cần phân biệt:
- Host đích mà ứng dụng kỳ vọng xác minh;
- SNI hostname mà client quảng bá;
- địa chỉ IP dùng để kết nối TCP;
- hostname/certificate identity thực tế sau handshake.

Chúng có thể khác nhau vì DNS, reverse proxies hay virtual hosting, nhưng phải phù hợp với **trust policy**; đừng tự miễn hostname check chỉ vì đang kết nối theo IP.

### 6.4. HttpsURLConnection/HttpClient có những mặc định riêng

`HttpsURLConnection` thực hiện HTTPS hostname verification mặc định. **Không** dùng `setDefaultHostnameVerifier((host, session) -> true)` hoặc custom TrustManager trust-all trong production.

`java.net.http.HttpClient` cũng có HTTPS TLS identity checks và own implementation policies. Khi bạn gọi `HttpClient.Builder.sslParameters(...)`, đừng dựa vào việc đặt `EndpointIdentificationAlgorithm` rỗng/null để vô hiệu hóa hostname validation; ứng dụng cần giữ HTTPS authentication hoạt động. Với raw `SSLSocket`/`SSLEngine`, phải cấu hình rõ theo ví dụ.

## 7. Client authentication: want và need trong TLS server

Server TLS thông thường chỉ yêu cầu **server certificate**, còn client xác thực bằng HTTP cookies/tokens/headers. Với **mutual TLS (mTLS)**, server cũng xác minh **client certificate**. `SSLParameters` có:

~~~java
SSLParameters serverParams = context.getDefaultSSLParameters();
serverParams.setNeedClientAuth(true); // Bắt buộc client certificate.
~~~

Nếu client không cung cấp certificate phù hợp với trust anchors của server, handshake sẽ không hoàn tất.

~~~java
SSLParameters serverParams = context.getDefaultSSLParameters();
serverParams.setWantClientAuth(true); // Muốn có, nhưng có thể không có.
~~~

**Need** và **Want** không phải hai flags hoạt động song song độc lập: gọi `setNeedClientAuth(true)` có thể override want mode trước đó; gọi `setWantClientAuth(true)` lại thay đổi need mode. Hãy chọn **một** policy rõ ràng.

### 7.1. NeedClientAuth không tự tạo hoặc tin client certificate

Để mTLS hoạt động thật cần:

- Server có `KeyManagerFactory` cung cấp **server key/certificate**, và `TrustManagerFactory` kiểm tra client certificates theo CA/trust policy của tổ chức.
- Client có `KeyManagerFactory` cung cấp **client key/certificate**, và `TrustManagerFactory` kiểm tra server certificate.
- Có certificate profile thích hợp (KeyUsage/ExtendedKeyUsage), path validity, revocation khi policy yêu cầu, rotation và authorization mapping (client identity → role/scope).
- Dù mTLS handshake thành công, application vẫn phải kiểm tra request authorization.

**Demo TLS loopback ở mục 11 không bật mTLS**, vì chỉ thử server certificate + hostname verification. `TlsPolicyParametersDemo` chứng minh cấu hình `NeedClientAuth=true` trong một policy object, không giả vờ đã thực hiện mTLS handshake.

### 7.2. WantClientAuth không phù hợp nếu client cert là điều kiện bắt buộc

Nếu production API yêu cầu mTLS, đừng chỉ đặt `wantClientAuth(true)` rồi coi một client không có certificate vẫn đã xác thực. Đặt `needClientAuth(true)` hoặc enforce cả application certificate policy khi một topology proxy/TLS terminator khác xử lý mTLS.

## 8. ALPN: thương lượng giao thức ứng dụng

**ALPN** (*Application-Layer Protocol Negotiation*) là extension để hai phía thống nhất protocol ở tầng ứng dụng chạy trên TLS, ví dụ `h2` hoặc `http/1.1`.

~~~java
SSLParameters client = socket.getSSLParameters();
client.setApplicationProtocols(new String[]{"h2", "http/1.1"});
socket.setSSLParameters(client);
socket.startHandshake();
System.out.println(socket.getApplicationProtocol());
~~~

Đây là đoạn trích, không phải file độc lập. `getApplicationProtocol()` sau handshake phản ánh **protocol đã chọn**, không chỉ phần tử đầu trong cấu hình; nó có thể rỗng nếu không thương lượng, tùy provider/peer.

### 8.1. ALPN không đổi SSL protocol version

`getApplicationProtocol()=="h2"` nói về **HTTP/2**, còn `getSession().getProtocol()=="TLSv1.3"` nói về **TLS version**. Chúng là hai lớp khác nhau. Không gọi `setApplicationProtocols(new String[]{"TLSv1.3"})`, vì TLSv1.3 không phải application protocol name.

### 8.2. Phải có tầng application thật sự hiểu ALPN

Chỉ vì socket thương lượng `h2` không có nghĩa handler của bạn biết nói HTTP/2. Một raw TLS socket gửi text lines tùy ý **không được** quảng bá `h2` trừ khi triển khai HTTP/2 framing. Trong demo mục 11, hai phía thương lượng **`lesson/1`** — một protocol giả định riêng cho bài lab — và trao đổi `ping/pong`. Không tuyên bố nó là chuẩn công nghiệp.

### 8.3. Java HttpClient quản lý ALPN nội bộ

Javadoc `HttpClient.Builder.sslParameters(SSLParameters)` ghi rằng một số tham số do HTTP client implementation quản lý, ví dụ **application protocol list**, **có thể bị bỏ qua**. Khi dùng Java HttpClient:

~~~java
HttpClient client = HttpClient.newBuilder()
    .sslContext(trustedContext)
    .sslParameters(clientTlsParameters)
    .version(HttpClient.Version.HTTP_2)
    .build();
~~~

Đây là đoạn trích; `trustedContext` và `clientTlsParameters` phải khởi tạo trước. `version(HTTP_2)` là preferred HTTP version, **không bắt buộc** server phải dùng HTTP/2; implementation còn chịu negotiation/constraints. Không dựa vào `clientTlsParameters.setApplicationProtocols` để override nội bộ HTTP client.

## 9. Cách apply SSLParameters đúng endpoint

### 9.1. SSLSocket (client)

~~~java
try (SSLSocket socket = (SSLSocket)
        clientContext.getSocketFactory().createSocket(host, port)) {
    SSLParameters params = clientContext.getDefaultSSLParameters();
    params.setProtocols(new String[]{"TLSv1.3"});
    params.setEndpointIdentificationAlgorithm("HTTPS");
    params.setServerNames(List.of(new SNIHostName(host)));
    socket.setSSLParameters(params);
    socket.startHandshake();
    // Chỉ xử lý sensitive application data sau handshake thành công.
}
~~~

**Đoạn trích**, các biến `clientContext`, `host`, `port` đã có, và client context phải được cấu hình trust đúng. Nếu `host` là IP literal, `SNIHostName` không chấp nhận dạng IP như hostname SNI; chỉ đặt SNI khi có **DNS hostname hợp lệ**, và kiểm tra SAN IP nếu endpoint truy cập qua IP.

### 9.2. SSLServerSocket (server)

~~~java
SSLServerSocket server = (SSLServerSocket)
        serverContext.getServerSocketFactory().createServerSocket(8443);
SSLParameters params = serverContext.getDefaultSSLParameters();
params.setProtocols(new String[]{"TLSv1.3"});
params.setNeedClientAuth(true); // Chỉ bật nếu server có client trust và yêu cầu mTLS.
server.setSSLParameters(params);
try (SSLSocket client = (SSLSocket) server.accept()) {
    client.startHandshake();
    // Xử lý request...
}
~~~

**Đoạn trích**, không phải server đầy đủ: phải đóng `server` bằng try-with-resources và quản lý thread/timeout/concurrency; `serverContext` cần key manager. Theo Javadoc, `SSLServerSocket.setSSLParameters` áp dụng policy cho **những kết nối được accept mới**, không retroactively cấu hình các sockets đã accept/handshake.

### 9.3. SSLEngine (client/server)

~~~java
SSLEngine engine = context.createSSLEngine("api.example.com", 443);
engine.setUseClientMode(true);
SSLParameters params = engine.getSSLParameters();
params.setProtocols(new String[]{"TLSv1.3"});
params.setEndpointIdentificationAlgorithm("HTTPS");
engine.setSSLParameters(params);
~~~

**Đoạn trích**, không phải SSLEngine handshake runnable. Với `SSLEngine`, ứng dụng phải thực hiện `wrap/unwrap`, xử lý `NEED_TASK`, buffer expansion, connection close và event loop. Đặt policy trước khi handshake; đừng nhầm việc cấu hình SSLEngine với **đã kết nối thành công**.

### 9.4. HttpsServer: HttpsConfigurator cho từng connection

`com.sun.net.httpserver.HttpsServer` dùng `HttpsConfigurator`. Theo Javadoc, override `configure(HttpsParameters)` và gọi **`HttpsParameters.setSSLParameters`**:

~~~java
httpsServer.setHttpsConfigurator(new HttpsConfigurator(serverContext) {
    @Override
    public void configure(HttpsParameters exchange) {
        SSLParameters params = getSSLContext().getDefaultSSLParameters();
        params.setProtocols(new String[]{"TLSv1.3"});
        params.setCipherSuites(new String[]{"TLS_AES_128_GCM_SHA256"});
        params.setNeedClientAuth(true); // Chỉ khi muốn và đã cấu hình mTLS.
        exchange.setSSLParameters(params);
    }
});
~~~

Đây là **đoạn trích**, cần imports `com.sun.net.httpserver.*` và `javax.net.ssl.*`, và biến `httpsServer/serverContext` sẵn có. Tạo **một SSLParameters mới cho mỗi configure()** thay vì sửa shared static object. Nếu chỉ muốn server-auth TLS, không cần setNeedClientAuth(true).

Không coi một `HttpsServer` tối giản là thay thế đầy đủ reverse proxy/HTTP framework production: vẫn cần TLS certificate lifecycle, request limits, authorization, timeouts, logging, HTTP security policy và monitoring.

### 9.5. Phân biệt HTTP client và HTTP server

Một application có thể cùng lúc vận hành **inbound HTTPS endpoint** và **outbound HTTPS client**. Hai vai trò cần policy **khác nhau**:
- Inbound server: server private key, cert chain, protocol/cipher policy, có thể require clientAuth, SNI matchers theo deployment.
- Outbound client: trust anchors cho server, hostname verification, SNI cho DNS name, connection deadline, ALPN/HTTP version theo client implementation.
- Không dùng cùng một SSLParameters mutable object rồi đặt `needClientAuth` khi làm client và `endpointIdentificationAlgorithm(null)` khi làm server; điều này dễ gây lỗi và không diễn đạt rõ security boundary.

## 10. Java 17+ runnable: policy SSLParameters và SSLEngine

Chương trình `TlsPolicyParametersDemo.java` chứng minh **không cần mở socket**:
- `SSLContext.getDefaultSSLParameters()` và `getSupportedSSLParameters()` được kiểm tra để chỉ nhận TLS 1.3 và AES-128-GCM.
- Tạo client policy có HTTPS hostname verification, SNI `api.example.com` và ALPN ưu tiên `h2`.
- Áp dụng lên `SSLEngine` client mode; thay đổi policy object sau đó không tự đổi engine configuration.
- Tạo một server policy với `setNeedClientAuth(true)`.
- Từ chối cipher suite giả `TLS_FAKE_CIPHER_NOT_SUPPORTED` theo explicit validation.
- **Chương trình này chỉ kiểm tra cấu hình**, chưa kiểm chứng handshake/certificate. Chương trình thứ hai mới làm handshake thật.

### 10.1. File TlsPolicyParametersDemo.java

~~~java
import java.security.SecureRandom;
import java.util.*;
import javax.net.ssl.*;

public final class TlsPolicyParametersDemo {
    static final String PROTOCOL = "TLSv1.3";
    static final String CIPHER = "TLS_AES_128_GCM_SHA256";

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static void requireEnabled(SSLContext context, String protocol, String cipher) {
        SSLParameters enabled = context.getDefaultSSLParameters();
        SSLParameters supported = context.getSupportedSSLParameters();
        if (!Arrays.asList(enabled.getProtocols()).contains(protocol)
                || !Arrays.asList(supported.getProtocols()).contains(protocol)
                || !Arrays.asList(enabled.getCipherSuites()).contains(cipher)
                || !Arrays.asList(supported.getCipherSuites()).contains(cipher)) {
            throw new IllegalArgumentException("TLS policy not enabled/supported");
        }
    }

    static SSLParameters clientPolicy(SSLContext context) {
        requireEnabled(context, PROTOCOL, CIPHER);
        SSLParameters params = context.getDefaultSSLParameters();
        params.setProtocols(new String[] { PROTOCOL });
        params.setCipherSuites(new String[] { CIPHER });
        params.setEndpointIdentificationAlgorithm("HTTPS");
        params.setServerNames(List.of(new SNIHostName("api.example.com")));
        params.setApplicationProtocols(new String[] { "h2", "http/1.1" });
        return params;
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, new SecureRandom());

        SSLParameters policy = clientPolicy(context);
        check(Arrays.equals(policy.getProtocols(), new String[] { PROTOCOL }),
                "not TLS 1.3 only");
        check(Arrays.equals(policy.getCipherSuites(), new String[] { CIPHER }),
                "cipher not restricted");
        check("HTTPS".equals(policy.getEndpointIdentificationAlgorithm()),
                "hostname verification missing");
        check(((SNIHostName) policy.getServerNames().get(0))
                .getAsciiName().equals("api.example.com"), "wrong SNI");
        check(policy.getApplicationProtocols()[0].equals("h2"), "ALPN");

        SSLEngine engine = context.createSSLEngine("api.example.com", 443);
        engine.setUseClientMode(true);
        engine.setSSLParameters(policy);
        policy.setProtocols(new String[] { "TLSv1.2" });
        check(Arrays.equals(engine.getSSLParameters().getProtocols(),
                new String[] { PROTOCOL }), "policy leaked through copy");

        SSLParameters server = context.getDefaultSSLParameters();
        server.setProtocols(new String[] { PROTOCOL });
        server.setCipherSuites(new String[] { CIPHER });
        server.setNeedClientAuth(true);
        check(server.getNeedClientAuth() && !server.getWantClientAuth(),
                "mTLS required policy");

        boolean invalid = false;
        try {
            requireEnabled(context, PROTOCOL, "TLS_FAKE_CIPHER_NOT_SUPPORTED");
        } catch (IllegalArgumentException expected) {
            invalid = true;
        }
        check(invalid, "unsupported suite must fail closed");

        System.out.println("tls13-enabled=true");
        System.out.println("cipher-enabled=true");
        System.out.println("client-hostname-check=HTTPS");
        System.out.println("client-sni=api.example.com");
        System.out.println("client-alpn-first=h2");
        System.out.println("engine-effective-protocol=" + engine.getSSLParameters().getProtocols()[0]);
        System.out.println("per-endpoint-policy-isolated=true");
        System.out.println("server-mtls-required=" + server.getNeedClientAuth());
        System.out.println("unsupported-suite-rejected=" + invalid);
        System.out.println("tests=PASS");
    }
}
~~~

### 10.2. Biên dịch/chạy và stdout thực tế

~~~bash
javac -encoding UTF-8 --release 17 TlsPolicyParametersDemo.java
java TlsPolicyParametersDemo
~~~

Đã chạy thành công trên **OpenJDK 24** với target Java 17:

~~~text
tls13-enabled=true
cipher-enabled=true
client-hostname-check=HTTPS
client-sni=api.example.com
client-alpn-first=h2
engine-effective-protocol=TLSv1.3
per-endpoint-policy-isolated=true
server-mtls-required=true
unsupported-suite-rejected=true
tests=PASS
~~~

**Diễn giải:** `engine-effective-protocol=TLSv1.3` ở đây nghĩa là **engine.getSSLParameters().getProtocols() cho phép TLS 1.3**, **không** phải SSLSession đã đàm phán; chương trình chưa gọi handshake. `server-mtls-required=true` cũng chỉ là flag ở SSLParameters server, **không chứng minh client certificate đã được kiểm tra**. Ví dụ thứ hai giải quyết phần TLS handshake thực tế.

## 11. Java 17+ runnable: TLS loopback, truststore và hostname test

Chương trình `TlsEndpointLoopbackDemo.java` là một integration test tự chạy bằng JDK:

- Chứng chỉ **self-signed RSA 3072-bit**, chỉ dùng nội bộ bài lab, có **SAN DNS:localhost** và **SAN IP:127.0.0.1**, EKU serverAuth.
- Server có `identity.p12` chứa private key + certificate chain.
- Client có **trust.p12 riêng** import certificate dùng trong lab, không dùng trust-all manager.
- Server bind `127.0.0.1`, port `0` do OS chọn.
- Cả server/client chỉ cho **TLSv1.3** + `TLS_AES_128_GCM_SHA256`, thương lượng ALPN `lesson/1`.
- Client bật endpoint identification algorithm `HTTPS` và SNI `localhost`.
- Kết nối hợp lệ gửi `ping`, server đáp `pong`.
- Kết nối thứ hai cố tình dùng hostname `wrong.example.test`, phải bị `SSLHandshakeException` từ chối.
- Server chạy trên worker thread và chấp nhận hai connections; ở negative test, việc client chủ động từ chối certificate có thể khiến server bị `SSLException` **hoặc `SocketException`**. Code xử lý `IOException` của kết nối thứ hai là lỗi dự kiến; **không** bỏ qua lỗi ở kết nối đầu tiên.
- Tất cả sockets/executor được close; certificate/keystores demo phải được xóa sau test.

**Cảnh báo bắt buộc:** mật khẩu `changeit` được hardcode chỉ cho fixture, **tuyệt đối không copy vào production**. Self-signed certificate do bài lab tự tạo không phải một public CA; importing nó vào truststore là một **pin/trust anchor test rõ ràng**, không có nghĩa nên trust bất kỳ certificate nào ngoài Internet.

### 11.1. Tạo chứng chỉ và truststore trong thư mục test

Dùng JDK `keytool` (PowerShell hoặc terminal hỗ trợ chạy command-line programs). Mở một **thư mục mới, riêng cho thử nghiệm**, không để credentials trong repository:

~~~powershell
keytool -genkeypair -alias endpoint -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=localhost, OU=Training, O=Local Test, C=VN" -validity 2 -storetype PKCS12 -keystore identity.p12 -storepass changeit -keypass changeit -ext "SAN=dns:localhost,ip:127.0.0.1" -ext "EKU=serverAuth" -noprompt
keytool -exportcert -alias endpoint -keystore identity.p12 -storepass changeit -rfc -file server-cert.pem
keytool -importcert -alias endpoint -file server-cert.pem -keystore trust.p12 -storetype PKCS12 -storepass changeit -noprompt
~~~

Chứng chỉ có hiệu lực **2 ngày**, chỉ để kiểm thử; đừng chạy demo với certificate đã hết hạn. `identity.p12` có **private key**, cần giữ riêng và xóa sau test. `trust.p12` chứa public certificate làm trust anchor riêng cho local fixture.

**Vì sao tách identity và trust?** Server phải chứng minh mình sở hữu private key; client phải tin đúng certificate/CA để xác minh peer. Nếu chỉ gọi `SSLContext.init(null,null,...)` trên client, self-signed certificate chưa được tin có thể khiến handshake thất bại dù hostname đúng. **Không giải quyết bằng trust-all**; import đúng test cert theo phương pháp trên.

### 11.2. File TlsEndpointLoopbackDemo.java

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.*;
import javax.net.ssl.*;

public final class TlsEndpointLoopbackDemo {
    static final String PROTOCOL = "TLSv1.3";
    static final String CIPHER = "TLS_AES_128_GCM_SHA256";
    static final String APPLICATION = "lesson/1";

    static void check(boolean condition, String detail) {
        if (!condition) throw new AssertionError(detail);
    }

    static KeyStore openStore(Path path, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(path)) {
            store.load(in, password);
        }
        return store;
    }

    static SSLContext serverContext(Path identity, char[] password) throws Exception {
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(openStore(identity, password), password);
        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(kmf.getKeyManagers(), null, new SecureRandom());
        return ssl;
    }

    static SSLContext clientContext(Path trust, char[] password) throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(openStore(trust, password));
        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(null, tmf.getTrustManagers(), new SecureRandom());
        return ssl;
    }

    static SSLParameters tlsPolicy(SSLContext context) {
        SSLParameters supported = context.getSupportedSSLParameters();
        SSLParameters enabled = context.getDefaultSSLParameters();
        if (!Arrays.asList(supported.getProtocols()).contains(PROTOCOL)
                || !Arrays.asList(enabled.getProtocols()).contains(PROTOCOL)
                || !Arrays.asList(supported.getCipherSuites()).contains(CIPHER)
                || !Arrays.asList(enabled.getCipherSuites()).contains(CIPHER)) {
            throw new IllegalStateException("TLS 1.3 AES-128-GCM not enabled");
        }
        SSLParameters p = context.getDefaultSSLParameters();
        p.setProtocols(new String[]{PROTOCOL});
        p.setCipherSuites(new String[]{CIPHER});
        p.setApplicationProtocols(new String[]{APPLICATION});
        return p;
    }

    static SSLParameters clientParameters(SSLContext context, String sniHost) {
        SSLParameters p = tlsPolicy(context);
        p.setEndpointIdentificationAlgorithm("HTTPS");
        p.setServerNames(List.of(new SNIHostName(sniHost)));
        return p;
    }

    static void runServer(SSLServerSocket server) throws Exception {
        for (int i = 0; i < 2; i++) {
            try (SSLSocket connection = (SSLSocket) server.accept()) {
                connection.setSoTimeout(4000);
                try {
                    connection.startHandshake();
                    if (i == 0) {
                        BufferedReader reader = new BufferedReader(
                                new InputStreamReader(connection.getInputStream(),
                                        StandardCharsets.UTF_8));
                        BufferedWriter writer = new BufferedWriter(
                                new OutputStreamWriter(connection.getOutputStream(),
                                        StandardCharsets.UTF_8));
                        check("ping".equals(reader.readLine()), "expected ping");
                        writer.write("pong\n");
                        writer.flush();
                    }
                } catch (IOException handshakeFailure) {
                    if (i == 0) throw handshakeFailure;
                    // During a rejected client hostname check, the peer can abort TCP.
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2)
            throw new IllegalArgumentException("identity.p12 trust.p12");
        char[] password = "changeit".toCharArray(); // Test-only password!
        SSLContext serverContext = serverContext(Path.of(args[0]), password);
        SSLContext clientContext = clientContext(Path.of(args[1]), password);

        try (SSLServerSocket listener = (SSLServerSocket)
                serverContext.getServerSocketFactory().createServerSocket(
                        0, 10, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(5000);
            SSLParameters serverPolicy = tlsPolicy(serverContext);
            serverPolicy.setNeedClientAuth(false);
            listener.setSSLParameters(serverPolicy);
            ExecutorService executor = Executors.newSingleThreadExecutor();
            Future<?> serverTask = executor.submit(() -> {
                try {
                    runServer(listener);
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            });

            try {
                int port = listener.getLocalPort();
                try (SSLSocket client = (SSLSocket)
                        clientContext.getSocketFactory().createSocket(
                                "127.0.0.1", port)) {
                    client.setSoTimeout(4000);
                    client.setSSLParameters(clientParameters(clientContext, "localhost"));
                    client.startHandshake();
                    String version = client.getSession().getProtocol();
                    String suite = client.getSession().getCipherSuite();
                    String alpn = client.getApplicationProtocol();
                    check(PROTOCOL.equals(version), "TLS version");
                    check(CIPHER.equals(suite), "cipher");
                    check(APPLICATION.equals(alpn), "ALPN");
                    check("HTTPS".equals(client.getSSLParameters()
                            .getEndpointIdentificationAlgorithm()), "endpoint-id");
                    BufferedWriter writer = new BufferedWriter(
                            new OutputStreamWriter(client.getOutputStream(),
                                    StandardCharsets.UTF_8));
                    writer.write("ping\n");
                    writer.flush();
                    BufferedReader reader = new BufferedReader(
                            new InputStreamReader(client.getInputStream(),
                                    StandardCharsets.UTF_8));
                    check("pong".equals(reader.readLine()), "echo reply");
                    System.out.println("tls-protocol=" + version);
                    System.out.println("cipher-suite=" + suite);
                    System.out.println("alpn=" + alpn);
                    System.out.println("endpoint-identification=HTTPS");
                    System.out.println("round-trip=pong");
                }

                boolean wrongHostRejected = false;
                try (Socket transport = new Socket("127.0.0.1", port);
                        SSLSocket bad = (SSLSocket)
                                clientContext.getSocketFactory().createSocket(
                                        transport, "wrong.example.test", port, true)) {
                    bad.setSoTimeout(4000);
                    bad.setSSLParameters(clientParameters(
                            clientContext, "wrong.example.test"));
                    bad.startHandshake();
                } catch (SSLHandshakeException expected) {
                    wrongHostRejected = true;
                }
                check(wrongHostRejected, "wrong hostname should fail handshake");
                serverTask.get(8, TimeUnit.SECONDS);
                System.out.println("wrong-hostname-rejected=" + wrongHostRejected);
                System.out.println("tests=PASS");
            } finally {
                executor.shutdownNow();
                executor.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
    }
}
~~~

### 11.3. Biên dịch và chạy

Từ thư mục chứa `TlsEndpointLoopbackDemo.java`, `identity.p12` và `trust.p12`:

~~~powershell
javac -encoding UTF-8 --release 17 TlsEndpointLoopbackDemo.java
java TlsEndpointLoopbackDemo identity.p12 trust.p12
~~~

**Stdout chính xác** trên OpenJDK 24, target Java 17:

~~~text
tls-protocol=TLSv1.3
cipher-suite=TLS_AES_128_GCM_SHA256
alpn=lesson/1
endpoint-identification=HTTPS
round-trip=pong
wrong-hostname-rejected=true
tests=PASS
~~~

### 11.4. Đọc đúng kết quả

- `tls-protocol=TLSv1.3` là phiên bản **thực sự đã negotiated**, không chỉ danh sách được phép.
- `cipher-suite=TLS_AES_128_GCM_SHA256` lấy từ `SSLSession` sau handshake.
- `alpn=lesson/1` là protocol layer do hai endpoints chọn từ ALPN.
- `endpoint-identification=HTTPS` xác nhận client bật hostname verification.
- `round-trip=pong` chứng minh application bytes truyền qua TLS socket đã hoàn tất.
- `wrong-hostname-rejected=true` chứng minh certificate có SAN localhost/127.0.0.1 **không chấp nhận** hostname `wrong.example.test`. Đây là negative test quan trọng: truststore đúng **không đủ** nếu hostname sai.
- `tests=PASS` chỉ xác minh JDK/provider đã thử và fixture này. Không coi demo self-signed/test password là production TLS configuration.

### 11.5. Vì sao negative test có thể báo exception ở phía server?

Khi client đã nhận certificate nhưng kiểm tra hostname thất bại, nó có thể **gửi TLS alert hoặc đóng TCP**. Server đang handshake/ghi response có thể nhận `SSLException` hoặc `SocketException`. Đây là hiệu ứng phụ của việc phía client **chủ động từ chối kết nối không đúng identity**; không mặc định là bug của SSLParameters. Chương trình test chỉ bỏ qua IOException ở **kết nối thứ hai được cố ý tạo để thất bại**; kết nối đầu tiên vẫn fail-fast.

### 11.6. Xóa khóa sau test

Sau khi đã kiểm thử, xóa `identity.p12`, `trust.p12` và `server-cert.pem` khỏi thư mục thử nghiệm, vì identity chứa **private key**. Không commit keystore hay mật khẩu demo, không dùng certificate tự ký hai ngày tuổi làm trust anchor cho production systems.

## 12. Thiết kế một EndpointTlsPolicy dùng được trong ứng dụng

### 12.1. Tách cấu hình bất biến khỏi SSLParameters mutable

Trong production, có thể biểu diễn policy bằng một `record` bất biến (Java 17+), ví dụ:

~~~java
public record EndpointTlsPolicy(
        String[] protocols,
        String[] cipherSuites,
        boolean requireClientCertificate,
        String expectedHost,
        String[] applicationProtocols) {
    public EndpointTlsPolicy {
        protocols = protocols.clone();
        cipherSuites = cipherSuites.clone();
        applicationProtocols = applicationProtocols.clone();
    }

    @Override public String[] protocols() {
        return protocols.clone();
    }
    @Override public String[] cipherSuites() {
        return cipherSuites.clone();
    }
    @Override public String[] applicationProtocols() {
        return applicationProtocols.clone();
    }

    public SSLParameters newClientParameters(SSLContext context) {
        SSLParameters p = context.getDefaultSSLParameters();
        p.setProtocols(protocols());
        p.setCipherSuites(cipherSuites());
        p.setEndpointIdentificationAlgorithm("HTTPS");
        if (expectedHost != null && !expectedHost.isBlank()) {
            p.setServerNames(List.of(new SNIHostName(expectedHost)));
        }
        p.setApplicationProtocols(applicationProtocols());
        return p;
    }

    public SSLParameters newServerParameters(SSLContext context) {
        SSLParameters p = context.getDefaultSSLParameters();
        p.setProtocols(protocols());
        p.setCipherSuites(cipherSuites());
        p.setNeedClientAuth(requireClientCertificate);
        p.setApplicationProtocols(applicationProtocols());
        return p;
    }
}
~~~

Đây là **mẫu thiết kế (code snippet)**, không phải lớp runnable đã được kiểm thử độc lập: cần imports `javax.net.ssl.*`, `java.util.List`, validation constructor và security policy đầy đủ. Đặc biệt với IP literal, không tạo `SNIHostName(IP)`; expectedHost ở snippet cần là DNS name phù hợp nếu dùng SNI. **Phải validate protocol/cipher allowlist** khi xây/áp dụng policy, không tin arrays từ untrusted JSON mà không kiểm tra; `TlsPolicyParametersDemo` minh họa validation.

Vì Java arrays mutable, mẫu `record` này **clone input/getter arrays** thay vì lộ arrays gốc. Mỗi `newClientParameters/newServerParameters` trả **một object riêng**, hạn chế race khi nhiều endpoints/threads.

### 12.2. Trách nhiệm không nằm trong record

Policy object trên **không đọc keystore/truststore, không xác thực chứng chỉ, không kiểm tra expiry/revocation, không cấu hình TCP timeouts**. Những nhiệm vụ đó thuộc SSLContext, PKI/cert lifecycle và tầng application/transport. Do vậy **đừng cố gom tất cả TLS settings trong mỗi SSLParameters object**.

### 12.3. Một cấu hình cho hai roles có thể nguy hiểm

Nếu outbound client và inbound server dùng cùng giá trị `requireClientCertificate` mà không phân biệt role, code có thể bật/tắt sai mTLS. Tốt hơn phân chia:
- `ClientTlsPolicy`: hostname verification **bắt buộc**, SNI DNS host, trust config, ALPN/HTTP client behavior.
- `ServerTlsPolicy`: server identities, need/want/no clientAuth, server SNI policy, ALPN app protocols.
- `EndpointTlsPolicy` shared immutable algorithm allowlists khi thật sự giống nhau.

**Không bao giờ tự động unset endpoint identification algorithm cho client**, kể cả khi đang chạy integration tests; dùng truststore cert test và SAN đúng.

## 13. Những vấn đề vận hành quan trọng

### 13.1. Handshake timeout, connect timeout và read timeout

`SSLParameters` không có một “TLS handshake timeout” chung cho tất cả transports. Với raw `SSLSocket`, dùng connect timeout của transport và `setSoTimeout`/deadline theo thiết kế ứng dụng; với asynchronous `SSLEngine`, event loop phải có timer/cancellation riêng; với Java `HttpClient` dùng `connectTimeout` và request timeout phù hợp, hiểu cách implementation tính thời gian handshake.

Không dùng `setMaximumPacketSize` làm request-size limit; nó liên quan packet-size expectations của TLS/DTLS, **không giới hạn HTTP body memory**.

### 13.2. Certificate/key rotation

Khi server thay certificate, cần đổi key material/SSLContext hoặc strategy alias selection phù hợp với provider và connection lifecycle. Một SSLParameters object không chứa certificate nên **không tự reload certificates**. Quản lý trust anchors và certificate expiry/revocation theo PKI policy, cảnh báo trước hạn, graceful migration và rollback an toàn.

### 13.3. SNI và reverse proxy

Nếu HTTPS được terminate ở reverse proxy/load balancer, ứng dụng Java phía sau có thể **không trực tiếp nhận TLS**. Trong trường hợp đó, SSLParameters trên socket nội bộ không thay thế TLS policy của proxy. Với end-to-end TLS, cần cấu hình cả proxy → backend, certificates và trust/hostname verification ở từng hop.

### 13.4. Logging bảo mật

Có thể log **negotiated TLS protocol**, cipher suite, ALPN, certificate identity fingerprints đã được chuẩn hóa hoặc trust decision (không log private key/session secrets). Tránh log đầy đủ TLS session tickets, HTTP Authorization, credential values. Dùng `javax.net.debug=ssl,handshake` chỉ trong môi trường test/troubleshooting được kiểm soát; debug logs có thể chứa dữ liệu vận hành nhạy cảm và cực lớn.

### 13.5. Cipher suite “an toàn” cũng cần policy cập nhật

Đừng hardcode một cipher suite duy nhất rồi coi đó là thông lệ vĩnh viễn. TLSv1.3 mang sẵn lựa chọn các cipher suites AEAD mạnh; Java runtimes có thể thêm/bỏ defaults do lỗ hổng, provider changes hoặc compliance. Nên pin **policy**, không pin một kết quả benchmark cũ; kiểm thử tương thích khi JDK/certificate policies thay đổi.

## 14. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ tạo `new SSLParameters` mà không apply | Socket/engine không dùng cấu hình mới | `setSSLParameters` **trước handshake** |
| Cấu hình sau `startHandshake()` | Không thay handshake đã hoàn thành | Tạo connection mới với policy đúng |
| Coi getSupported == enabled | Có thể chọn legacy/disabled algorithms | Dùng default-enabled + explicit allowlist |
| Cho toàn bộ supported ciphers | Mở rộng bề mặt tấn công | Chỉ allowlisted modern suites |
| Bật TLS 1.0/1.1 để hết lỗi | Dùng giao thức lỗi thời | Upgrade peer; TLS 1.2/1.3 theo policy |
| Gọi `SSLContext.getInstance("TLS")` rồi tin mặc định là policy đầy đủ | Chưa biết enabled algorithms/keys/trust/hostname | Cấu hình policy có kiểm chứng |
| Tạo trust-all X509TrustManager | Chấp nhận certificate giả | Dùng TrustManagerFactory/PKIX trust |
| Chỉ kiểm tra certificate chain, không kiểm tra hostname | Dễ bị spoofing/MITM | `setEndpointIdentificationAlgorithm("HTTPS")` |
| Dùng SNI như chứng nhận danh tính | SNI chỉ là hostname được request | Endpoint hostname validation |
| SNI bằng IP literal | `SNIHostName` không nhận IP host name | Dùng DNS hostname hoặc bỏ SNI khi chỉ có IP |
| Certificate thiếu SAN IP | Kết nối qua IP bị hostname mismatch | Certificate có SAN đúng hoặc dùng DNS |
| Tưởng ALPN chọn TLS version | Nhầm tầng application và TLS | Dùng getApplicationProtocol vs SSLSession.getProtocol |
| Quảng bá h2 nhưng app không implement HTTP/2 | Sai application protocol contract | Chỉ quảng bá protocol thực hỗ trợ |
| HttpClient sslParameters ALPN không có hiệu lực | HTTP client có internal ALPN policy | Để HttpClient quản lý ALPN/HTTP version |
| Bật `wantClientAuth` nhưng coi mTLS bắt buộc | Client có thể không có cert | `needClientAuth` + trust client CA |
| Bật `needClientAuth` nhưng server không có trust client CA | Handshake fail | Cấu hình server TrustManagerFactory |
| Bật mTLS nhưng không map cert → permission | Handshake đúng nhưng lộ quyền | Business authorization riêng |
| Share SSLParameters mutable qua nhiều threads | Race/role config lẫn nhau | Immutable policy, fresh SSLParameters |
| Chỉnh SSLServerSocket sau accept | Sockets cũ không đổi | Apply policy trước accept |
| Tưởng SSLParameters thay truststore | Vẫn trust sai/không có identity | Tách SSLContext KeyManager/TrustManager |
| Bỏ qua JDK disabledAlgorithms | Vô tình yêu cầu forbidden algorithms | Fail closed, cập nhật policy |
| Bỏ qua handshake timeout/DoS limits | Connections treo hoặc quá tải | Deadlines, connection limits, quotas |
| Hardcode `changeit` ở production | Lộ private key | Secret manager/keystore passwords bảo vệ |
| Dùng self-signed demo cert ở production | Không có CA/trust governance | PKI đúng, rotation/revocation |
| Tưởng TLS socket là HTTP | App framing sai | Layer application protocol rõ |
| Log toàn bộ javax.net.debug ở production | Tiết lộ thông tin, log flood | Tracing có kiểm soát |

## 15. Checklist integration tests cho TLS endpoint

| Test | Điều cần xác minh |
| --- | --- |
| Context default vs supported | Default-enabled bị giới hạn theo policy |
| Allowlist TLSv1.3 | Chỉ TLS 1.3 thành công trong fixture |
| Cipher allowlist | Negotiated cipher đúng |
| Unsupported cipher | Fail-closed trước socket/handshake |
| TLSv1.2 legacy peer | Kết nối bị từ chối nếu policy TLSv1.3-only |
| Server certificate đúng SAN | Client raw SSLSocket verify true |
| Server certificate sai hostname | Handshake fail |
| Server certificate chưa trusted | Handshake fail |
| Server certificate hết hạn | Handshake fail |
| Chain validity/key usages | Policy PKIX thích hợp |
| SNI đúng DNS name | Server có thể chọn đúng virtual identity |
| SNI khác expected host | Không được thay hostname check |
| ALPN có common protocol | Negotiated app protocol đúng |
| ALPN không có common protocol | Handshake/application behavior rõ |
| App không hỗ trợ h2 | Không quảng bá h2 |
| NeedClientAuth server | Client thiếu/không trusted cert bị từ chối |
| WantClientAuth server | Hành vi optional rõ, không coi anonymous là mTLS |
| Config trước/ sau handshake | Chỉ before-handshake affect current connection |
| SSLServerSocket params | Áp dụng cho connections mới, không retroactively |
| SSLEngine params | Buffers/tasks/handshake/timers đúng |
| HttpClient.Builder.sslParameters | Không giả định override internal ALPN |
| HttpsConfigurator callback | Mỗi HTTPS connection nhận policy mới |
| Concurrent endpoint setup | Không race mutable SSLParameters |
| Multiple endpoints | Client/server roles khác nhau |
| Rotated certificate | Không mất trust/identity |
| JDK upgrade | Security properties and cipher sets revalidated |
| Slow handshake | Deadline/connection quotas |
| TLS session reuse | Identity/policy constraints vẫn đúng |
| Loopback test output | Protocol/cipher/ALPN/session check đúng |
| Cleanup | Sockets/executor, keystore demo dọn sau test |

### 15.1. Dựa vào handshake, không chỉ kiểm tra getters

Một test chỉ kiểm tra `params.getProtocols()` sẽ không phát hiện server không support TLS 1.3, certificate sai SAN hoặc truststore thiếu CA. Vì vậy bài này có **hai mức test**: một chương trình xác minh policy object/SSLEngine state và một chương trình thật sự mở TLS connection rồi kiểm tra `SSLSession`, ALPN, data round-trip và wrong hostname.

### 15.2. Không thay thử nghiệm production bằng self-signed lab

Demo chỉ bind localhost; production phải test với certificate chain đúng, DNS/SNI nhiều hostnames, load balancer, OCSP/revocation/pinning policy, mTLS client certificates và key rotation. Self-signed test chứng minh **mechanics** của JSSE, không chứng minh trust governance ngoài đời.

## 16. Câu hỏi tự đánh giá

**1.** `SSLParameters` và `SSLContext` khác nhau ra sao?

**Đáp án:** SSLContext chứa provider context, key/trust managers; SSLParameters chứa handshake policy của một endpoint.

**2.** `getSupportedSSLParameters` có nghĩa mọi algorithm nên được bật?

**Đáp án:** Không. Supported có thể bao gồm algorithms không enabled và bị security policy cấm.

**3.** Đặt `setProtocols({"TLSv1.3"})` đủ chứng minh handshake TLS 1.3 thành công chưa?

**Đáp án:** Chưa. Phải handshake rồi xem `SSLSession.getProtocol()`.

**4.** Tại sao raw SSLSocket client phải set endpoint identification algorithm?

**Đáp án:** Để đối chiếu hostname kỳ vọng với certificate peer, tránh chấp nhận một server khác dù chain được trust.

**5.** `SNIHostName` chứng minh server identity không?

**Đáp án:** Không. SNI chỉ gửi tên host mong muốn tới server, không xác minh certificate.

**6.** Khi kết nối bằng IP 127.0.0.1, certificate cần gì?

**Đáp án:** SAN kiểu IP address cho 127.0.0.1, hoặc dùng DNS name có SAN phù hợp nếu kết nối bằng DNS.

**7.** ALPN khác TLS protocol như thế nào?

**Đáp án:** ALPN chọn application protocol như h2/http/1.1; TLS protocol là TLSv1.2/TLSv1.3.

**8.** `setNeedClientAuth(true)` có nghĩa server đã có truststore client không?

**Đáp án:** Không. Cần TrustManagerFactory với client trust anchors; client cũng cần certificate/key phù hợp.

**9.** `setWantClientAuth(true)` có bắt buộc mTLS không?

**Đáp án:** Không. Đây là optional request, client có thể không cung cấp certificate.

**10.** `SSLServerSocket.setSSLParameters` có áp dụng cho sockets đã accept không?

**Đáp án:** Không, Javadoc nêu nó áp dụng cho **newly accepted connections**.

**11.** `HttpClient.Builder.sslParameters` có đảm bảo ALPN custom được dùng không?

**Đáp án:** Không. Javadoc cho phép internal parameters như application protocol list bị bỏ qua.

**12.** Vì sao SSLParameters nên tạo mới cho mỗi endpoint?

**Đáp án:** Nó mutable; dùng fresh object từ immutable policy giảm race và sai role/client/server.

**13.** Truststore chứa self-signed localhost certificate chứng minh gì?

**Đáp án:** Chỉ rằng fixture client đã trust đúng test certificate; không tạo public CA hoặc production trust.

**14.** Có nên bỏ HTTPS hostname check cho test certificate self-signed không?

**Đáp án:** Không. Import test cert đúng truststore và tạo SAN đúng; giữ endpoint identification bật.

**15.** Nếu provider không hỗ trợ TLS 1.3 của policy, nên tự fallback TLS 1.0 không?

**Đáp án:** Không. Fail closed và cập nhật peer/requirements, không bật giao thức lỗi thời.

**16.** Mỗi lần sửa SSLParameters sau handshake có cập nhật kết nối không?

**Đáp án:** Không nên coi như vậy. Tạo endpoint/connection mới và kiểm chứng handshake mới.

### Bài tập thực hành

1. Chạy `TlsPolicyParametersDemo`, giải thích mọi stdout line.
2. Đổi cipher giả thành một cipher không được default-enabled và xác nhận policy fail-closed.
3. So sánh default-enabled và supported protocols/ciphers của JDK trong môi trường kiểm thử; không dùng toàn bộ supported làm policy.
4. Tạo DNS SAN certificate và thử nối theo DNS host, so với IP SAN.
5. Thử certificate thiếu IP SAN cho 127.0.0.1, xác nhận hostname verification fail.
6. Đổi SNI sang một DNS name khác nhưng giữ peer identity expected; kiểm thử và giải thích vì sao phải phân biệt SNI với hostname check.
7. Đổi `APPLICATION` từ `lesson/1` sang một giá trị không chung giữa client/server, kiểm tra ALPN behavior.
8. Thêm một TLS 1.2 suite allowlisted nếu business yêu cầu tương thích, test kết nối từng version.
9. Dựng server mTLS **riêng** với client certificate, TrustManagerFactory, needClientAuth=true và negative test không có client cert.
10. Đổi needClientAuth thành wantClientAuth, kiểm tra khác biệt và security implications.
11. Tạo `HttpsServer` với `HttpsConfigurator`, áp dụng SSLParameters trong callback cho mỗi connection.
12. Dùng Java HttpClient và custom SSLParameters, ghi nhận ALPN/HTTP version negotiated thay vì giả định custom ALPN được dùng.
13. Viết immutable policy class có defensive copies, validate protocol/cipher allowlists.
14. Tạo 100 endpoints song song bằng policy class, đảm bảo không race SSLParameters.
15. Viết deadline/timeout tests cho connect/handshake/data read.
16. Test certificate rotation và PKIX truststore updates mà không trust-all.
17. Đo handshake latency, connection reuse, TLS session tickets nhưng không log secrets.
18. Chạy suite trên JDK 17/21/26 hoặc provider khác, kiểm tra policy default thay đổi.
19. Thử proxy TLS termination để xem cấu hình ở từng TLS hop được quản lý ở đâu.
20. Viết health/report cho negotiated TLS versions/cipher suites và cảnh báo protocol yếu.

## 17. Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — SSLParameters](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLParameters.html): full policy API, Since Java 6, methods/versions.
- [Oracle Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): Java 17 target method availability.
- [Oracle Java SE 26 — SSLContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLContext.html): keys/trust/default/supported parameters.
- [Oracle Java SE 26 — SSLSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSocket.html): setSSLParameters, startHandshake, getSession.
- [Oracle Java SE 26 — SSLServerSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLServerSocket.html): server parameters for newly accepted connections.
- [Oracle Java SE 26 — SSLEngine](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLEngine.html): non-blocking TLS machinery.
- [Oracle Java SE 26 — SSLSession](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSession.html): negotiated protocol/cipher.
- [Oracle Java SE 26 — SNIHostName](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SNIHostName.html): DNS hostname in SNI.
- [Oracle Java SE 26 — SNIMatcher](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SNIMatcher.html): server-side SNI matching.
- [Oracle Java SE 26 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): private key/cert chains.
- [Oracle Java SE 26 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): trust anchors/certificate validation.
- [Oracle Java SE 26 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): sslContext, sslParameters and implementation-managed ALPN.
- [Oracle Java SE 26 — HttpsConfigurator](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html): per-connection configure.
- [Oracle Java SE 26 — HttpsParameters](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsParameters.html): apply SSLParameters to HTTPS endpoint.
- [Oracle Java SE 26 — Security Developer's Guide / JSSE Reference Guide](https://docs.oracle.com/en/java/javase/26/security/): endpoint identification, trust and TLS configuration.
- [Oracle Java SE 26 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html): protocol/algorithm names.
- [Oracle JDK 26 — keytool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html): PKCS12 test certificates/trust anchors.
- [IETF RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html): security and negotiation.
- [IETF RFC 7301 — TLS Application-Layer Protocol Negotiation](https://www.rfc-editor.org/rfc/rfc7301.html): ALPN semantics.

**Ghi nhớ:** `SSLParameters` giúp gom **protocols, cipher suites, endpoint identification, SNI, ALPN và client-auth** cho **một endpoint**, nhưng không chứa private keys/truststores và không thay `SSLContext`. Hãy cấu hình **trước handshake**, tạo đối tượng policy mới cho từng role/endpoint, không bật mọi supported suites, **luôn xác minh hostname ở raw TLS clients**, không đánh đồng SNI với server authentication, và kiểm tra **phiên bản/cipher đã negotiated** qua `SSLSession`. Với Java HttpClient, ALPN có thể do implementation quản lý. Hai chương trình đã cho thấy cấu hình TLS 1.3 và từ chối hostname sai khi handshake thật — không cần hạ cấp giao thức hay trust-all certificate để tạo test thành công.
