# 16.3 SSLParameters cho protocol, cipher suite, SNI, ALPN và endpoint identification

Một Java client có thể dùng `SSLContext` và `SSLEngine` hoặc `SSLSocket` để tạo kết nối TLS. Tuy nhiên, câu lệnh `SSLContext.getInstance("TLS")` **không tự giải thích** phiên bản TLS nào sẽ được bật, bộ mã (*cipher suite*) nào được chọn, client gửi tên server qua SNI hay không, giao thức ứng dụng được thương lượng qua ALPN thế nào, và đặc biệt client có kiểm tra **chứng thư thực sự thuộc đúng hostname đích** hay không.

Trong JSSE (*Java Secure Socket Extension*), `javax.net.ssl.SSLParameters` là một đối tượng cấu hình cho những điều khoản handshake và xác thực liên quan. Nó bao gồm danh sách protocol, cipher suites, SNI, ALPN, endpoint identification và một số lựa chọn khác. Nhưng cần phân biệt **cấu hình đã được thiết lập** với **kết quả handshake đã thương lượng và xác thực thành công**: `setProtocols` không bảo đảm peer hỗ trợ protocol, `setApplicationProtocols` không có nghĩa đã dùng HTTP/2, `setServerNames` không thay thế kiểm hostname, và `setEndpointIdentificationAlgorithm("HTTPS")` không tự tạo một trust anchor đáng tin.

Bài học dùng **Java 17+** và tập trung đúng năm nhóm:

1. `protocols`: giới hạn phiên bản TLS được phép.
2. `cipherSuites`: giới hạn bộ thuật toán TLS tương thích với phiên bản và chính sách.
3. `serverNames` / **SNI**: thông báo server name để máy chủ chọn cấu hình/certificate thích hợp.
4. `applicationProtocols` / **ALPN**: thương lượng giao thức tầng ứng dụng, ví dụ `h2` hoặc `http/1.1`.
5. `endpointIdentificationAlgorithm`: yêu cầu JSSE kiểm danh tính server, nhất là hostname của kết nối HTTPS.

Mục tiêu là biết **đặt đúng thuộc tính ở đúng phía client/server, trước handshake**, giữ kiểm chứng TLS đầy đủ, xác định giới hạn của APIs và có bài test dương/âm. Ví dụ Java chạy được ở mục 9 không cần mạng để tránh phụ thuộc server công khai và không giả vờ rằng cấu hình thành công đồng nghĩa đã xác thực một TLS peer.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

- Giải thích quan hệ giữa `SSLContext`, `SSLEngine`, `SSLSocket`, `SSLParameters`, `TrustManager` và `KeyManager`.
- Lấy cấu hình từ `getSSLParameters()`, thay đổi đúng các thuộc tính cần thiết, rồi áp dụng bằng `setSSLParameters(...)` **trước khi bắt đầu handshake**.
- Phân biệt `getSupportedProtocols()` với `getEnabledProtocols()` và tránh bật phiên bản TLS cũ chỉ để kết nối.
- Hiểu tên cipher suite trong TLS 1.2 so với TLS 1.3, mối liên hệ với protocol, certificate, signature và key exchange.
- Dùng `SNIHostName` và `SSLParameters.setServerNames(...)` ở **client**, biết server-side `SNIMatcher` không thay chứng thư/hostname validation.
- Dùng `setApplicationProtocols(...)` để đề xuất ALPN và đọc giao thức **đã thương lượng** sau handshake bằng `SSLEngine.getApplicationProtocol()` hoặc `SSLSocket.getApplicationProtocol()`.
- Bật endpoint identification `HTTPS` với socket/engine thích hợp, hiểu `SNI != hostname verification != trust chain validation`.
- Nắm những khác biệt quan trọng giữa `SSLEngine`, `SSLSocket`, `HttpsURLConnection` và `java.net.http.HttpClient`.
- Kiểm tra các trường hợp cấu hình sai, downgrade, ALPN mismatch, SNI sai, certificate SAN sai, CA không tin, mTLS và tác động của TLS connection pooling.

## 2. SSLParameters nằm ở đâu trong JSSE?

Một lớp nhìn tổng quát:

```text
Java application
    |
    +-- java.net.http.HttpClient / HTTPS library
    |       |
    |       +-- JSSE/TLS implementation (tùy library/provider)
    |
    +-- SSLSocket hoặc SSLEngine trực tiếp
            |
            +-- SSLContext
            |      +-- KeyManager (local identity, nếu cần)
            |      +-- TrustManager (peer certificate verification)
            |      +-- SecureRandom / provider
            |
            +-- SSLParameters (cấu hình handshake / endpoint)
                   +-- protocols
                   +-- cipher suites
                   +-- SNI server names
                   +-- ALPN application protocols
                   +-- endpoint identification algorithm
                   +-- client auth / algorithm constraints / các tùy chọn khác
```

`SSLContext` được khởi tạo bằng key managers/trust managers/provider theo chính sách. Một `SSLEngine` hoặc `SSLSocket` được tạo từ context và mang cấu hình sử dụng khi giao tiếp. `SSLParameters` thường là **một đối tượng cấu hình có thể sửa**, không phải “kết quả kiểm tra bảo mật”.

Mẫu thay đổi thường thấy:

```java
// Mã minh họa trong một method; giả sử SSLEngine engine đã tạo.
SSLParameters p = engine.getSSLParameters();
p.setEndpointIdentificationAlgorithm("HTTPS");
engine.setSSLParameters(p); // Áp lại vào engine.
```

Đừng chỉnh `p` rồi quên `setSSLParameters(p)`. Việc có object `p` với dữ liệu mới không có nghĩa engine/socket đã nhận thay đổi.

### Năm câu hỏi phải tách rời

| Câu hỏi | Thuộc tính/API liên quan | Chứng minh được điều gì? |
| --- | --- | --- |
| Tôi cho phép TLS version nào? | `setProtocols` | Những version được cấu hình bật trên endpoint |
| Tôi cho phép thuật toán TLS nào? | `setCipherSuites` | Những suite được cấu hình; chưa chắc peer chọn được |
| Server nên nhận tên đích nào để chọn certificate? | `setServerNames` / SNI | Client gửi tên như một TLS extension khi handshake hỗ trợ |
| Client/server sẽ nói HTTP/2 hay HTTP/1.1? | `setApplicationProtocols` / ALPN | Danh sách đề xuất; giao thức thật chỉ biết sau thương lượng |
| Certificate có đại diện đúng endpoint không? | `setEndpointIdentificationAlgorithm("HTTPS")` | Bật chính sách endpoint identity cho engine/socket phù hợp; còn cần trusted path và handshake thực |

**Không thay thế lẫn nhau:** SNI là thông tin client gửi để server chọn virtual host; ALPN là chọn giao thức ứng dụng; hostname verification là xác thực tên server từ chứng thư. Cả ba có thể dùng cùng một hostname trong ứng dụng HTTPS, nhưng là **ba cơ chế độc lập**.

## 3. Phân biệt supported, enabled, configured và negotiated

Đây là chìa khóa để tránh hiểu sai output của JSSE.

- **Supported:** provider/runtime có triển khai một TLS protocol hoặc cipher suite, thể hiện qua `getSupportedProtocols()` và `getSupportedCipherSuites()`.
- **Enabled:** tập tính năng runtime đang bật cho endpoint đó theo chính sách mặc định và cấu hình đã áp, thể hiện qua `getEnabledProtocols()` và `getEnabledCipherSuites()`.
- **Configured/allowed:** tập mà ứng dụng chủ động đặt qua `SSLParameters`; cần là subset phù hợp với provider và policy.
- **Negotiated:** kết quả peer thực sự thống nhất sau handshake; có thể xem qua `SSLSession.getProtocol()`, `SSLSession.getCipherSuite()` và `getApplicationProtocol()`.

```text
Provider SUPPORTED
       |
       v
Runtime security policy + endpoint defaults
       |
       v
ENABLED / app override via SSLParameters
       |
       v
ClientHello + ServerHello + certificate checks + handshake
       |
       v
NEGOTIATED protocol, cipher suite, ALPN, authenticated peer
```

Một protocol có mặt trong **supported** nhưng không nằm trong **enabled** có thể bị tắt vì đã cũ, nguy hiểm hoặc không phù hợp policy. **Không bật lại chỉ vì nó có mặt trong danh sách supported**. Java 17 thường hỗ trợ TLS 1.2 và 1.3 trên các JSSE provider phổ biến, nhưng danh sách thực tế phụ thuộc vendor/build/provider, security properties, các cài đặt `jdk.tls.disabledAlgorithms` và runtime.

### Cấu hình ưu tiên an toàn

Trong production, nên bắt đầu từ **JSSE defaults đã được quản trị** hoặc một allowlist được review. Nếu có yêu cầu bắt buộc tối thiểu TLS 1.2, hãy kiểm giao của các version cho phép với **enabled protocols** tại runtime cụ thể. Nếu giao rỗng, **fail closed** thay vì ép bật TLS 1.0/1.1.

Không lấy mảng từ `getSupportedProtocols()` rồi đưa nguyên vào `setProtocols(...)`; hành vi đó có thể bật những protocol mà mặc định JDK cố ý loại bỏ.

## 4. Protocol: TLSv1.2, TLSv1.3 và phiên bản handshake

Cách đặt:

```java
// Mã minh họa: chỉ dùng khi các protocol đã được kiểm là enabled và được policy cho phép.
SSLParameters p = engine.getSSLParameters();
p.setProtocols(new String[] { "TLSv1.3", "TLSv1.2" });
engine.setSSLParameters(p);
```

Ở mức ý tưởng, đây là danh sách version **được phép thử thương lượng**. Nó không buộc server phải chọn TLS 1.3; server có thể chỉ hỗ trợ TLS 1.2, hoặc giao các phiên bản có thể rỗng và handshake thất bại.

**TLS 1.3** có thay đổi đáng kể so với TLS 1.2 về quá trình handshake, bộ mã được định nghĩa và cơ chế khóa tạm thời. Đừng suy rằng một cipher suite có tên `TLS_AES_128_GCM_SHA256` dùng được với TLS 1.2 hoặc rằng một tên `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` là TLS 1.3 suite.

### Các thiết lập thường gây rủi ro

- Bật `TLSv1` / `TLSv1.1` / `SSLv3` để “hỗ trợ server cũ” mà không có review chính sách.
- Coi `SSLContext.getInstance("TLS")` là cố định chỉ TLS 1.2/1.3 bất kể provider.
- Đọc `setProtocols` thành “handshake đã dùng TLS 1.3”.
- Xóa TLS 1.2 trên một hệ thống có client/peer chưa hỗ trợ TLS 1.3 mà không có kiểm thử tương thích.
- Cho user request quyết định danh sách protocol/cipher rồi chuyển trực tiếp vào `SSLParameters`.
- Thay global security properties hoặc provider chỉ để làm một kết nối legacy chạy được, vô tình ảnh hưởng toàn bộ JVM.
- Đổi allowlist khi `SSLSocket` đã handshake; kết nối đã thiết lập không tự thương lượng lại theo cấu hình mới.

### Khi nào nên chỉ cho TLSv1.3?

Khi threat model và tất cả peer có thể hỗ trợ, **TLS 1.3 only** có thể là một chính sách hợp lý. Với hệ thống cần tương thích, cho phép TLS 1.2 và 1.3 theo profile mạnh cũng có thể hợp lệ. Cần đo telemetry và có lộ trình loại bỏ TLS cũ; việc chọn protocol là **quyết định security/compliance và compatibility**, không phải đoán dựa trên một bài demo.

## 5. Cipher suites: TLS 1.2 khác TLS 1.3

**Cipher suite** mô tả tổ hợp thuật toán TLS được dùng khi handshake và bảo vệ record. Tuy nhiên, mức thông tin trong tên suite khác nhau theo TLS version.

| Phiên bản | Ví dụ tên suite | Điều cần hiểu |
| --- | --- | --- |
| TLS 1.3 | `TLS_AES_128_GCM_SHA256` | AEAD cipher + hash dùng trong TLS 1.3; thuật toán key exchange và xác thực được thương lượng qua cơ chế khác |
| TLS 1.3 | `TLS_AES_256_GCM_SHA384` | AEAD AES-GCM và hash tương ứng |
| TLS 1.3 | `TLS_CHACHA20_POLY1305_SHA256` | AEAD ChaCha20-Poly1305 nếu provider hỗ trợ |
| TLS 1.2 | `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` | ECDHE key exchange, RSA-based authentication trong profile TLS 1.2, AES-GCM |
| TLS 1.2 | `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256` | ECDHE với ECDSA certificate/authentication trong profile TLS 1.2 |
| TLS 1.2 | `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384` | Profile TLS 1.2 có ECDHE và AES-GCM |

**Đừng diễn giải tên TLS 1.3 suite bằng logic tên TLS 1.2.** Trong TLS 1.3, cipher suite không còn mã hóa tên thuật toán chứng thư RSA/ECDSA hoặc key exchange như TLS 1.2.

### Chọn cipher suite đúng cách

- Bắt đầu với **enabled suites**, không bật toàn bộ supported suites.
- Chỉ giữ suite theo allowlist bảo mật được cập nhật và **tương thích với protocol**.
- Không cố ép một TLS 1.3 suite khi chỉ cho TLS 1.2; có thể dẫn đến “no shared cipher”/handshake failure.
- Với TLS 1.2, key type của certificate và khả năng của server cũng quan trọng. Một suite ECDSA có thể không phù hợp server chỉ triển khai RSA identity, tùy cấu hình và provider.
- Không coi `setCipherSuites(...)` là cơ chế pin certificate hoặc ép peer identity.
- Với đa số ứng dụng HTTPS thông thường, mặc định JSSE/provider được cập nhật và không tự giới hạn cứng một suite thường giúp duy trì compatibility tốt hơn. Chỉ pin danh sách suite khi có yêu cầu cụ thể và đã test cả hai phía.

### Cấu hình cipher suite order

`SSLParameters.setUseCipherSuitesOrder(true)` có ý nghĩa ưu tiên thứ tự suite của **phía server** trong những trường hợp/protocol/provider áp dụng. Nó không bảo đảm server luôn chọn suite đầu nếu không tương thích hoặc không được hỗ trợ. TLS 1.3 và TLS 1.2 có quy tắc thương lượng khác nhau; hãy test negotiated cipher thực tế.

### Cảnh báo mạnh

Không dùng hoặc bật lại cipher suites đã bị chính sách JDK tắt chỉ vì một peer cũ yêu cầu. Các quyết định như bỏ static RSA key exchange trong TLS 1.2, CBC/3DES/RC4 hay thuật toán chữ ký yếu cần theo security policy, không thực hiện bằng cách copy một list cũ từ internet.

## 6. SNI: client thông báo tên server đang muốn kết nối

**SNI** (*Server Name Indication*) là TLS extension cho phép client gửi một server name tới endpoint, thường giúp server/CDN/reverse proxy đang dùng chung IP:port chọn certificate và virtual host tương ứng. Một server có thể phục vụ nhiều hostname trên cùng địa chỉ IP.

Ví dụ:

```text
Shared IP 203.0.113.10:443
   |
   +-- api.example.test    -> certificate A / virtual host A
   |
   +-- admin.example.test  -> certificate B / virtual host B

Client connects to api.example.test
   ClientHello SNI = api.example.test
   Server chooses certificate A
```

**SNI không phải bằng chứng danh tính.** Client có thể nói nó muốn server name `api.example.test`, nhưng TLS client vẫn phải xác minh certificate của server đúng tên ấy và có chain đến trust anchor được phép. Nếu server trả chứng thư cho `admin.example.test`, việc client đã gửi đúng SNI **không** cứu được lỗi hostname mismatch.

### Java client dùng SNIHostName

```java
// Mã minh họa trong method.
String hostname = "api.example.test";
SSLParameters p = engine.getSSLParameters();
p.setServerNames(List.of(new SNIHostName(hostname)));
engine.setSSLParameters(p);
```

Đoạn này cần import `java.util.List` và `javax.net.ssl.SNIHostName`, và giả sử `engine` đã được tạo cho đúng peer. `SNIHostName` biểu diễn host_name SNI; không đưa URL nguyên `https://api.example.test/path`, cổng `:443`, wildcard `*.example.test`, IP literal hoặc chuỗi không hợp lệ vào chỗ tên DNS.

**Trong nhiều HTTPS client JSSE hiện đại, SNI có thể được điền tự động theo hostname đích**. Việc set thủ công chỉ cần khi bạn có lý do và chắc chắn không tạo mâu thuẫn với host mà endpoint identification dùng. Khi kết nối tới một IP nhưng cần xác minh DNS name, phải hiểu rõ API của TLS engine/socket, peerHost, SNI, HTTP Host header và security policy; đừng chỉnh một chuỗi duy nhất để bypass xác thực.

### SNI trên server

Phía server có thể dùng `SSLParameters.setSNIMatchers(...)` hoặc logic TLS stack để quyết định chấp nhận/sắp xếp tên và lựa chọn local identity. Nhưng:

- `SNIMatcher` không cấp certificate cho hostname tự động.
- `setServerNames` là cách client cung cấp danh sách tên, **không phải** cấu hình “tên máy chủ mà server chắc chắn sở hữu”.
- Server thường phải có `KeyManager`/alias selection/certificate chain tương ứng với SNI.
- Nếu server yêu cầu một SNI cụ thể, thiếu/sai SNI có thể bị từ chối theo policy hoặc chọn một virtual host mặc định; hành vi tùy server.
- SNI truyền thống không phải lúc nào được giữ bí mật khỏi quan sát mạng; không chứa token, secret hay dữ liệu nghiệp vụ nhạy cảm trong SNI.
- SNI và HTTP `Host`/`:authority` nên được xử lý nhất quán, không cho Host header giả mạo vượt qua TLS peer/route authorization.

### SNI khác hostname verification

| Cơ chế | Ai chủ động? | Kiểm điều gì? |
| --- | --- | --- |
| SNI | Client gửi tên trong handshake | Giúp server biết virtual host được yêu cầu |
| Certificate SAN | CA/issuer cấp danh tính vào certificate | Danh sách DNS/IP names được certificate khai báo |
| Endpoint identification | Client kiểm chứng certificate đối với peer host kỳ vọng | Xác nhận certificate hợp lệ cho hostname/IP đích |
| HTTP Host / :authority | HTTP client gửi tên của origin | Định tuyến HTTP; không thay TLS xác thực |
| App authorization | Ứng dụng kiểm tra caller/tenant/endpoint | Người dùng có quyền thực hiện tác vụ hay không |

Không kết luận “SNI đúng” khi mới chỉ gọi `getServerNames()`. Đó là kiểm local config; handshake thật phải được thực hiện và endpoint certificate vẫn phải xác thực thành công.

## 7. ALPN: thương lượng HTTP/2, HTTP/1.1 và giao thức khác

**ALPN** (*Application-Layer Protocol Negotiation*) là TLS extension cho client và server chọn giao thức ứng dụng chạy **trên** kết nối TLS. Ví dụ HTTPS client có thể đề xuất:

```text
Client ALPN offers: ["h2", "http/1.1"]
Server ALPN supports: ["http/1.1"]
Negotiated ALPN: "http/1.1"
```

Nếu cả hai bên hỗ trợ và policy cho phép, kết quả có thể là `h2`. ALPN **không tự triển khai HTTP/2**: ứng dụng phải có HTTP/2 framing, stream management, flow control và nội dung protocol. Nếu Java socket raw chỉ set ALPN `h2` mà chương trình vẫn ghi HTTP/1.1 text, kết nối sẽ không vận hành đúng.

### Java đặt ALPN offers

```java
SSLParameters p = engine.getSSLParameters();
p.setApplicationProtocols(new String[] { "h2", "http/1.1" });
engine.setSSLParameters(p);
```

Thứ tự offer có thể mang ý nghĩa ưu tiên tùy TLS stack/server. `setApplicationProtocols` khai báo danh sách ALPN được cấu hình, **chưa phải kết quả thương lượng**. Sau khi handshake hoàn tất:

```java
// Mã minh họa khi handshake thực sự đã thành công.
String selectedProtocol = engine.getApplicationProtocol();
```

Nếu ứng dụng **bắt buộc HTTP/2**, phải kiểm result là `"h2"` trước khi phát HTTP/2 frames. Nếu ứng dụng cho fallback HTTP/1.1 thì phải chuyển sang protocol implementation tương ứng. Khi peer không thương lượng ALPN hoặc trả kết quả không chấp nhận được, hành vi fail/fallback phải theo đặc tả của giao thức, không mặc nhiên coi là `"http/1.1"` cho mọi ứng dụng.

### ALPN server selection

JSSE cung cấp API phía server như `SSLSocket.setHandshakeApplicationProtocolSelector(...)` hoặc biến thể cho `SSLEngine` trong môi trường phù hợp. Server phải chọn **một protocol mà client đề xuất** và server thực sự triển khai, theo policy. Không trả tên arbitrary hoặc chọn `h2` mà ứng dụng không hỗ trợ.

ALPN còn xuất hiện ở TLS-based gRPC, HTTP/2 và nhiều protocol đặc thù. Một service gRPC thường cần kiểm yêu cầu `h2`/HTTP/2; đừng nghĩ đặt tên ALPN là đủ để service lập tức thành gRPC server.

### ALPN không giải quyết certificate trust

Cho dù chọn `h2` thành công, client vẫn phải xác minh chain, hostname, KU/EKU, protocol security và application authorization. Không dùng ALPN output như bằng chứng peer là một service cụ thể.

## 8. Endpoint identification: ràng buộc certificate với hostname đích

**Endpoint identification** là bước kiểm certificate của peer có đại diện cho **định danh dịch vụ được yêu cầu** hay không. Trong HTTPS, đó thường là DNS hostname hoặc IP literal của URL. Đây là lớp bảo vệ riêng với việc certificate được CA đáng tin ký.

Ví dụ:

```text
Requested endpoint: https://payments.example.test
Certificate chain: valid to trusted CA
Leaf SAN: DNS:files.example.test

CA path valid?  yes
Name valid?     no
Result:         reject connection
```

Chỉ tin CA không đủ: một CA đáng tin có thể phát hành chứng thư cho nhiều hostname. Nếu kiểm chain mà bỏ kiểm tên, kẻ tấn công có một certificate hợp lệ cho hostname của họ có thể đưa nó vào một kết nối mà ứng dụng tưởng thuộc hostname khác.

### Java bật HTTPS endpoint identification

```java
SSLParameters p = engine.getSSLParameters();
p.setEndpointIdentificationAlgorithm("HTTPS");
engine.setSSLParameters(p);
```

Thuộc tính `"HTTPS"` yêu cầu dùng thuật toán kiểm định danh HTTPS được JSSE hỗ trợ khi handshake. Điều kiện quan trọng:

- Engine/socket phải có **peer hostname kỳ vọng** được tạo/thiết lập đúng theo API; một `SSLEngine` không biết peer host có thể không có đủ ngữ cảnh để kiểm tên như bạn nghĩ.
- `SSLContext` phải có **trust manager** phù hợp để xác minh chain. Bật hostname check không tự biến một certificate thành đáng tin.
- Kết nối thực sự phải được handshake và trust manager/provider thực hiện validation. Chỉ nhìn `getEndpointIdentificationAlgorithm()` trả `"HTTPS"` là kiểm cấu hình, **không** chứng minh certificate.
- Với HTTP clients cấp cao như `java.net.http.HttpClient`, cơ chế endpoint verification thường được thư viện quản lý. **Không tắt hoặc vô tình ghi đè** các thiết lập nội bộ đó.
- Với raw `SSLSocket`, phải kiểm đúng lúc cấu hình, peer host và TLS context; không giả định mọi socket factory giống nhau.
- Với TLS server kiểm chứng **client certificate mTLS**, identity policy không giống HTTPS server hostname. Cần kiểm chain, KU/EKU clientAuth, mapping certificate identity tới principal và authorization.

### Những điều không nên làm

- `p.setEndpointIdentificationAlgorithm(null)` hoặc `""` để làm một certificate sai tên được chấp nhận.
- Cài `HostnameVerifier` luôn trả true, hoặc `X509TrustManager.checkServerTrusted` luôn rỗng.
- Lấy tên do user cung cấp bất kỳ rồi dùng làm “expected hostname” để chấp nhận certificate của attacker.
- So Subject CN bằng `contains(...)` hoặc `endsWith(...)` thay cho các quy tắc SAN/IDN/wildcard chuẩn.
- Coi SNI hostname là trusted identity mà không đối chiếu certificate.
- Tắt verification khi dùng proxy, service mesh, private CA: phải cấu hình đúng trust anchors, SNI/hostname và endpoint identity mà môi trường yêu cầu.

### SNI, ALPN và endpoint identification trong một luồng

```text
Client knows trusted URL/hostname = api.example.test
    |
    v
SSLParameters:
    protocol allowlist
    cipher suite allowlist
    SNI host = api.example.test
    ALPN offers = ["h2", "http/1.1"]
    endpointIdentificationAlgorithm = "HTTPS"
    |
    v
TLS ClientHello / server selection
    |
    v
Server certificate + agreed TLS version/cipher + ALPN
    |
    v
Trust chain validation + hostname SAN + TLS policy
    |
    +--> reject if any mandatory check fails
    |
    v
Authenticated TLS channel
    |
    v
Application speaks negotiated ALPN protocol
    |
    v
Application still checks authorization/tenant/resource
```

## 9. Chương trình Java 17+ chạy được, không cần kết nối mạng

Chương trình sau chỉ **cấu hình một `SSLEngine` client**, không gọi handshake và không gửi yêu cầu tới một hostname thật. Nó chọn **một protocol đang enabled** từ allowlist `TLSv1.3`/`TLSv1.2`, chọn **một cipher suite đã enabled và phù hợp với version được chọn**, rồi đặt SNI, ALPN và `HTTPS` endpoint identification.

Việc cố ý chọn **một** protocol và **một** suite giúp đọc code và kết quả dễ dàng. Đây **không phải khuyến nghị** production luôn ép một suite; production thường nên dùng allowlist tương thích hoặc defaults bảo mật được quản trị để tránh pin cứng làm giảm khả năng kết nối. Code fail closed nếu runtime không có lựa chọn nào trong list. Kết quả dưới đây chỉ chứng minh config được áp vào engine.

Lưu đúng tên **`SslParametersDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SNIHostName;

public class SslParametersDemo {
    static String choose(String[] preferred, String[] enabled) {
        List<String> candidates = Arrays.asList(enabled);
        for (String value : preferred) {
            if (candidates.contains(value)) return value;
        }
        throw new IllegalStateException("No approved enabled option");
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, null); // Demo: provider default key/trust managers.
        String host = "api.example.test";
        SSLEngine engine = context.createSSLEngine(host, 443);
        engine.setUseClientMode(true);

        String protocol = choose(
                new String[] {"TLSv1.3", "TLSv1.2"},
                engine.getEnabledProtocols());
        String[] preferredSuites = protocol.equals("TLSv1.3")
                ? new String[] {
                    "TLS_AES_128_GCM_SHA256",
                    "TLS_AES_256_GCM_SHA384",
                    "TLS_CHACHA20_POLY1305_SHA256"
                  }
                : new String[] {
                    "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
                    "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
                    "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384"
                  };
        String suite = choose(preferredSuites, engine.getEnabledCipherSuites());

        SSLParameters parameters = engine.getSSLParameters();
        parameters.setProtocols(new String[] {protocol});
        parameters.setCipherSuites(new String[] {suite});
        parameters.setServerNames(List.of(new SNIHostName(host)));
        parameters.setApplicationProtocols(new String[] {"h2", "http/1.1"});
        parameters.setEndpointIdentificationAlgorithm("HTTPS");
        engine.setSSLParameters(parameters);

        SSLParameters applied = engine.getSSLParameters();
        boolean protocolApplied = Arrays.equals(
                new String[] {protocol}, applied.getProtocols());
        boolean suiteApplied = Arrays.equals(
                new String[] {suite}, applied.getCipherSuites());
        boolean sniApplied = Objects.equals(
                List.of(new SNIHostName(host)), applied.getServerNames());
        boolean alpnApplied = Arrays.equals(
                new String[] {"h2", "http/1.1"},
                applied.getApplicationProtocols());

        System.out.println("Client mode: " + engine.getUseClientMode());
        System.out.println("Protocol in enabled allowlist: " +
                Arrays.asList(new String[] {"TLSv1.3", "TLSv1.2"})
                        .contains(protocol));
        System.out.println("Protocol applied: " + protocolApplied);
        System.out.println("Cipher suite applied: " + suiteApplied);
        System.out.println("SNI host applied: " + sniApplied);
        System.out.println("ALPN offers applied: " + alpnApplied);
        System.out.println("Endpoint identification: " +
                applied.getEndpointIdentificationAlgorithm());
        System.out.println("No handshake performed: true");
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 SslParametersDemo.java
java SslParametersDemo
```

**Stdout đã đối chiếu sau khi chạy trên runtime có một trong các protocol/suite tương ứng đang enabled:**

```text
Client mode: true
Protocol in enabled allowlist: true
Protocol applied: true
Cipher suite applied: true
SNI host applied: true
ALPN offers applied: true
Endpoint identification: HTTPS
No handshake performed: true
```

Nếu runtime/provider không enable TLS 1.2/1.3 hoặc không có bất kỳ suite được phép, `choose` ném `IllegalStateException` một cách có chủ đích; đó là **fail closed**, không phải lý do bật suite yếu. Đây là output có điều kiện của môi trường test đã chạy, không cam kết mọi vendor/JDK giống hệt nhau.

### 9.1 Phân tích từng bước

1. `SSLContext.getInstance("TLS")` chọn implementation TLS từ provider. `context.init(null,null,null)` sử dụng key/trust configuration mặc định của provider cho mục đích demo; **nó không xác minh một server cụ thể** và không nên hiểu `null` luôn trỏ đúng file `cacerts` trong mọi runtime.
2. `createSSLEngine(host,443)` tạo engine có peer host/port tham chiếu, quan trọng cho các kiểm tra endpoint và SNI trong một handshake thật. Nó **không** kết nối mạng.
3. `setUseClientMode(true)` thiết lập vai trò TLS client. Cần đặt chế độ trước handshake và trước khi sử dụng những thông số riêng theo client.
4. `getEnabledProtocols()` cung cấp phiên bản đang enabled. `choose` chỉ lấy `TLSv1.3` hoặc `TLSv1.2` từ tập đó, không bừa bãi bật mọi supported protocol.
5. Danh sách cipher được chọn **phụ thuộc protocol**. Đây là ví dụ tối giản để tránh phối TLSv1.3 với TLSv1.2 suite. Một server thực có certificate/key/signature/ALPN và policy riêng nên handshake vẫn có thể thất bại dù local suite đã enabled.
6. `setProtocols` và `setCipherSuites` áp các lựa chọn đã kiểm; `setServerNames` đưa hostname SNI, `setApplicationProtocols` đề xuất `h2`/`http/1.1`, `setEndpointIdentificationAlgorithm("HTTPS")` bật kiểm định danh mong đợi.
7. `engine.setSSLParameters(parameters)` là bước **áp lại**. Sau đó `getSSLParameters()` kiểm những giá trị cục bộ, không kiểm trạng thái server.
8. Các biến boolean xác nhận các thuộc tính được giữ. Không dòng nào trong output là “TLS handshake successful” hay “server trusted”.
9. `No handshake performed: true` là thông báo về thiết kế của chương trình, **không phải một TLS security assertion**. Chương trình không gọi `engine.beginHandshake()`, `wrap` hoặc `unwrap`.

### 9.2 Vì sao không đưa toàn bộ code SSLEngine handshake vào demo?

`SSLEngine` là API nonblocking dành cho các chương trình biết quản lý buffer, I/O, handshake status và delegated tasks. Handshake thật cần vòng `wrap/unwrap`, `NEED_TASK`, `NEED_WRAP`, `NEED_UNWRAP`, timeout/EOF xử lý đúng, và transport peer thực tế. Một ví dụ ngắn mà chỉ gọi `beginHandshake()` rồi in “connected” sẽ **không đúng**.

Để tập trung vào `SSLParameters`, demo chỉ tạo/configure engine và kiểm bằng getters. Với ứng dụng HTTP thật, nên dùng HTTP client/JSSE library đã được kiểm chứng thay vì tự xây handshake machine.

### 9.3 Không nên copy hardcode suite sang production

Ví dụ ưu tiên `TLS_AES_128_GCM_SHA256` nếu dùng TLS 1.3, hoặc một suite ECDHE-GCM phù hợp khi dùng TLS 1.2. Đây là lựa chọn cho demo deterministic. Production cần:

- Không đặt mặc định TLS 1.2 nếu tổ chức bắt buộc TLS 1.3.
- Không ép một RSA/ECDSA suite TLS 1.2 khi server certificate/key không phù hợp.
- Không coi bộ mã có trong provider là đủ để được policy cho phép.
- Không để client tự chọn các mục tiêu bảo mật bất chấp policy.
- Test với server thật, dự phòng thay certificate và cập nhật JDK/root store.

## 10. SSLSocket và handshake thực: cấu hình phải có hiệu lực trước khi gửi

Với `SSLSocket`, bạn cũng có thể gọi `getSSLParameters()`, thay đổi và `setSSLParameters(...)` trước `startHandshake()`. Ví dụ **minh họa bên trong một method** (không phải chương trình độc lập, cần exception handling/import tương ứng và một `SSLContext context` đã được cấu hình đáng tin):

```java
String host = "api.example.test";
int port = 443;

try (SSLSocket socket = (SSLSocket)
        context.getSocketFactory().createSocket(host, port)) {
    SSLParameters p = socket.getSSLParameters();
    p.setServerNames(List.of(new SNIHostName(host)));
    p.setApplicationProtocols(new String[] {"h2", "http/1.1"});
    p.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(p);

    socket.startHandshake(); // Có thể thất bại do CA/SAN/protocol/suite.
    SSLSession session = socket.getSession();
    String negotiatedTls = session.getProtocol();
    String negotiatedCipher = session.getCipherSuite();
    String negotiatedApp = socket.getApplicationProtocol();

    // Chọn đúng implementation của negotiatedApp trước khi trao đổi dữ liệu.
}
```

Đoạn trên **không cấu hình giao diện HTTP/2 hay thực hiện HTTP request**. Nó chỉ cho thấy thông tin sau handshake và nhắc rằng TLS và HTTP là hai tầng khác nhau. Khi kết nối tới một test server thực tế, phải có truststore/CA phù hợp, DNS/SNI/hostname đúng và endpoint identification bật.

### Tại sao nên cấu hình trước handshake?

Handshake thực hiện thương lượng protocol, cipher suite, SNI/ALPN và peer authentication. Nếu sửa `SSLParameters` sau khi đã handshake, không thể mặc nhiên yêu cầu phiên hiện hữu bắt đầu lại hoặc kiểm certificate lần nữa. Trong thực tế, HTTP keep-alive, pooling và TLS session resumption còn làm policy reload phức tạp hơn. Khi policy thay đổi, cần tạo mới SSL contexts/clients hoặc quản lý pool/session theo threat model.

### SSLSocket với custom TrustManager

`SSLParameters` chỉ điều khiển một phần kiểm soát. Trust anchors đến từ `SSLContext`/`TrustManagerFactory`/`X509ExtendedTrustManager` phù hợp. Nếu tự viết `X509TrustManager`, phải hiểu đầy đủ việc JSSE có hay không áp endpoint checks với custom manager: không viết `checkServerTrusted` rỗng và mặc nhiên tin rằng `setEndpointIdentificationAlgorithm("HTTPS")` sẽ “bù lại” việc thiếu chain validation.

Ưu tiên trust manager của provider được quản lý đúng và kho CA được kiểm soát; tránh tự bỏ qua PKIX checks.

## 11. Java HTTP client cấp cao: tránh phá các ràng buộc do thư viện quản lý

`java.net.http.HttpClient` thường đã quản lý nhiều chi tiết TLS, HTTP/2 và hostname verification. Nếu không có yêu cầu đặc biệt, **giữ mặc định an toàn** của JDK và cập nhật runtime/trust policy. Một số API cho phép chỉ định:

```java
// Mã minh họa; giả sử SSLContext context được cấu hình phù hợp.
HttpClient client = HttpClient.newBuilder()
        .sslContext(context)
        .version(HttpClient.Version.HTTP_2)
        .build();
```

Đoạn trên không phải chương trình độc lập, cần import `java.net.http.HttpClient` và context đã tạo. `version(HTTP_2)` là sở thích/chế độ HTTP client ở lớp cao, **không tự chứng minh ALPN đã chọn h2 trên từng kết nối**. HTTP client có thể chọn/điều chỉnh ALPN hoặc fallback theo giao thức/API; kiểm thực tế qua response/client traces khi cần.

**Không nên** tạo một `SSLParameters` chứa mọi thứ rồi truyền bừa vào HTTP client: một số HTTP client quản lý ALPN/hostname verification của riêng nó và có thể thay đổi hoặc bỏ qua những thuộc tính do caller đưa vào. Đọc documentation của **đúng thư viện và phiên bản** được triển khai; kiểm behavior trong integration tests.

### Đừng tắt hostname verification qua global debug flags

Một số người dùng flag nội bộ hoặc custom `HostnameVerifier` luôn true để vượt lỗi certificate sai SAN. Làm vậy có thể xóa bảo đảm identity của HTTPS. Khi gặp vấn đề TLS, hãy sửa CA chain, SAN, URL hostname, SNI, proxy và truststore, không disable verification.

## 12. Cấu hình server khác client ở đâu?

Trên server, `SSLParameters` được áp vào `SSLServerSocket`, `SSLSocket` server-side hoặc `SSLEngine` server-side tùy kiến trúc. Các thuộc tính có thể được hiểu khác:

| Thuộc tính | Client TLS | Server TLS |
| --- | --- | --- |
| `setProtocols` | Những version client sẵn sàng offer | Những version server sẵn sàng accept |
| `setCipherSuites` | Những suite có thể thương lượng | Những suite server có thể chọn |
| `setServerNames` | Tên client gửi qua SNI | **Không** dùng để tuyên bố server sở hữu hostname |
| `setSNIMatchers` | Không thường dùng | Có thể kiểm/giới hạn SNI incoming theo policy |
| `setApplicationProtocols` | Danh sách ALPN client đề xuất | Danh sách ALPN server hỗ trợ |
| `setEndpointIdentificationAlgorithm("HTTPS")` | Dùng khi kiểm server HTTPS | Không phải cơ chế server công bố certificate/hostname |
| `setNeedClientAuth(true)` | Không phải thiết lập HTTPS server identity | Yêu cầu client certificate trong mTLS theo API thích hợp |
| `setWantClientAuth(true)` | Không thay authorization | Yêu cầu chứng thư client một cách tùy chọn theo server policy |
| `setUseCipherSuitesOrder` | Không ép server theo thứ tự client | Có thể thể hiện ưu tiên server trong trường hợp được hỗ trợ |

**Need vs want client auth:** `needClientAuth` thường làm handshake thất bại nếu không có client certificate hợp lệ theo policy; `wantClientAuth` cho phép client không cung cấp certificate trong tình huống được hỗ trợ. Hai cài đặt có tác động qua lại; không bật cả hai và đoán thứ tự override. Khi bật mTLS, server phải có truststore cho client CAs, identity mapping và authorization, chứ không chỉ `setNeedClientAuth(true)`.

### Server lựa chọn certificate theo SNI

Một reverse proxy hoặc Java server có nhiều certificate identities có thể dùng hostname SNI và `X509ExtendedKeyManager`/application server selection policy để chọn certificate/alias. Điều đó đòi hỏi key material/certificate chain đã được cấu hình. `SSLParameters.setSNIMatchers` không tự tạo alias hoặc thay key manager.

Nếu server chỉ có một certificate cho `api.example.test` mà client gửi SNI `admin.example.test`, server có thể chọn certificate default hoặc từ chối. Client vẫn phải kiểm SAN/endpoint identity, không chấp nhận certificate khác tên.

### Server chọn ALPN

Server phải chọn protocol có trong danh sách client gửi và server triển khai. Nếu server chọn `h2`, HTTP stack phải thật sự hiểu HTTP/2; nếu chọn `http/1.1`, dùng HTTP/1.1 parser. Nếu ứng dụng sử dụng TLS cho giao thức khác, chuỗi ALPN phải đúng chuẩn/registry tương ứng, không tự ý đặt tên vô nghĩa.

## 13. Tương tác giữa protocol, cipher suite, certificate và ALPN

Một cấu hình nhìn qua hợp lệ có thể thất bại do những ràng buộc chéo:

```text
Client enabled protocols:      TLSv1.3
Client configured cipher:      TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
Server supports:               TLSv1.3
Result:                        no mutually usable cipher suite for TLSv1.3

Client ALPN offers:            h2
Server ALPN supports:          http/1.1
Result:                        ALPN mismatch / no chosen protocol (policy-dependent)

Client target hostname:        a.example.test
Client SNI:                    b.example.test
Server presents cert:          b.example.test
Result:                        hostname verification must reject a.example.test
```

Từng dòng là **tình huống minh họa**, không phải output của một chương trình Java độc lập. Lỗi cụ thể có thể là `SSLHandshakeException` hoặc hành vi no-application-protocol/fallback tùy TLS version, provider và library; không xem câu chữ exception là contract cố định.

**Mấu chốt:** TLS có nhiều bước kiểm liên kết. Đừng chấp nhận thông điệp “Cipher suite applied: true” trong demo như bằng chứng handshake đã hợp lệ.

### Chữ ký chứng thư và cipher suite

TLS 1.2 suite tên `ECDHE_RSA` thường yêu cầu dạng chứng thư/authentication thích hợp; TLS 1.3 tách lựa chọn suite khỏi cơ chế authentication/signature algorithm và key-share negotiation. Do đó, chuyển từ TLS 1.2 sang TLS 1.3 có thể khiến các kiểm tra config “tên suite có RSA hay không” không còn phản ánh quy trình xác thực. Luôn xét version, certificate algorithm, signature schemes và provider policy.

### Session resumption và cấu hình mới

Nếu ứng dụng đổi trust roots, hostname policy, enabled versions hoặc ALPN, **các kết nối TLS đã thiết lập và sessions được resumption** có thể không lập tức theo policy mới. Trong thay đổi khẩn cấp (ví dụ distrust CA), cần kế hoạch thay client/context, đóng connection pools và kiểm tra các new handshakes/session caches. Không chỉ sửa một object `SSLParameters` rồi tuyên bố toàn cluster đã cập nhật.

## 14. Kiểm thử E2E: phải có cả positive và negative

Một bộ integration test nên phân biệt **configuration unit tests** với **TLS handshake tests**:

| Ca | Cấu hình hoặc dữ liệu đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Config protocol | Set TLSv1.3 enabled theo allowlist | `getSSLParameters` phản ánh cấu hình |
| Config suite | Set suite compatible và enabled | Được áp; **chưa chứng minh handshake** |
| TLS version thực | Client/server chỉ có chung TLSv1.2 | Handshake chọn TLSv1.2 nếu policy cho phép |
| No shared protocol | Client chỉ TLSv1.3, server chỉ TLSv1.2 | Handshake fail, không fallback ra ngoài policy |
| No usable cipher | Protocol chung nhưng suite không giao | Handshake fail |
| SNI đúng | Hai virtual hosts, client gửi tên A | Server chọn certificate/config đúng A nếu hỗ trợ |
| SNI sai | Client gửi tên B trong khi kỳ vọng A | Endpoint identity phải từ chối certificate B cho hostname A |
| SNI không có | Server cần SNI để chọn vhost | Fail hoặc behavior theo policy, không tin certificate sai |
| ALPN h2 | Cả hai hỗ trợ h2 | `getApplicationProtocol()` trả h2 sau handshake thành công |
| ALPN fallback | Client cho h2/http1, server chỉ http1 | Chọn http/1.1 nếu policy/implementation cho phép |
| ALPN mismatch | Không có protocol chung, ứng dụng yêu cầu h2 | Fail closed hoặc không tiến vào ứng dụng trái protocol |
| CA chưa tin | Server cert chain không tới trusted CA | Handshake reject |
| SAN mismatch | Chain hợp lệ cho hostname khác | HTTPS endpoint identification reject |
| Cert expired | Server leaf hết hạn | Handshake reject theo chính sách |
| Invalid KU/EKU | Leaf không cho serverAuth theo policy | TLS server auth reject |
| Client auth required | mTLS server need client cert, client không có | Handshake reject |
| Client certificate lạ | mTLS client có cert từ CA ngoài allowlist | Reject theo server trust policy |
| mTLS authorized? | Certificate hợp lệ nhưng principal không có quyền | TLS có thể pass; application rejects request |
| Downgrade attempt | Peer yêu cầu TLS cũ bị policy tắt | Reject; không tự enable legacy |
| Connection reused | Policy CA thay đổi trong lúc pool mở | Quan sát refresh/reload đúng theo lifecycle |
| Multi-runtime | JDK17/JDK khác nhau | Kiểm supported/enabled/ALPN/endpoint behavior thật |
| Proxy/mesh | TLS termination và SNI routing khác | Kiểm endpoint được xác thực đúng trust boundary |

**Kiểm thử đơn vị `SSLParameters` như mục 9 là cần nhưng không đủ.** Muốn chứng minh bảo mật kết nối, cần lab server có certificate chain/SAN được tạo có kiểm soát, truststore test và kiểm phiên thực sự được thương lượng.

### Tạo lab riêng

Bạn có thể dùng `keytool` tạo CA và leaf dành riêng cho `localhost`/tên test; dùng loopback port hoặc test container. **Không** import CA test vào `cacerts` của JDK sản xuất, không dùng trust-all. Cần kiểm certificate có SAN đúng hostname/loopback dùng, không chỉ `CN`. Với JSSE server có thể dùng `KeyStore`/`KeyManagerFactory`, client dùng `TrustManagerFactory` nạp CA test.

Muốn test ALPN đúng, server phải có implementation chọn `h2`/`http/1.1`, và client phải kiểm `getApplicationProtocol()` sau handshake. Với một server chỉ nói HTTP/1.1, đừng cấu hình ALPN `h2` rồi tuyên bố thành công của TLS đồng nghĩa HTTP/2 hoạt động.

## 15. Những lỗi phổ biến khi dùng SSLParameters

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Lấy toàn bộ `getSupportedProtocols()` để enable | Có thể bật version bị tắt do policy | Lấy allowlist giao với enabled và policy |
| Không xét TLS version khi chọn cipher suite | No shared cipher; cấu hình không tương thích | Dùng suite theo profile phiên bản; test handshake |
| Cố định một suite trong mọi service | Lỗi khi thay certificate hoặc peer policy | Ưu tiên defaults/curated compatible set |
| Chỉ sửa local `SSLParameters` mà quên `setSSLParameters` | Engine/socket chưa nhận thay đổi | Áp lại và kiểm getters |
| Cấu hình sau handshake | Session đã thương lượng trước đó | Cấu hình trước handshake, refresh connection lifecycle |
| Nhầm `setServerNames` là hostname verification | MITM/đồng nhất sai peer | Bật endpoint identification và trust validation |
| Dùng SNI khác URL hostname tùy ý | Server trả certificate sai identity | Ràng buộc SNI, peerHost và endpoint identity theo policy |
| Cho URL nguyên vào `SNIHostName` | Invalid SNI name / lỗi format | Chỉ hostname DNS thích hợp |
| Cho rằng ALPN offers = negotiated result | Gửi HTTP/2 frames tới HTTP/1.1 peer | Đọc negotiated ALPN sau handshake |
| Chỉ set `h2` ALPN nhưng không có HTTP/2 stack | Giao thức ứng dụng lỗi | Tích hợp library thực sự hiểu h2 |
| Tắt endpoint identification để sửa SAN lỗi | Chấp nhận server sai tên | Sửa certificate/URL/SNI/trust |
| Cài trust-all X509TrustManager | Loại bỏ CA/path validation | Trust manager PKIX đáng tin và truststore hẹp |
| Tự map clientAuth cert thành quyền admin | Lỗi authorization mTLS | Validate identity rồi áp RBAC/ABAC |
| Dùng một custom truststore cho mọi client mà không phân scope | Mở rộng hoặc mất public roots | Per-client SSLContext khi cần |
| Thay file truststore mà không reload context/pool | Sử dụng trust anchors cũ | Versioned config, reload và kiểm handshake mới |
| Dựa vào chuỗi exception text | Chẩn đoán sai qua các JDK | Log lý do đã làm sạch và test đúng provider |
| Coi `setSSLParameters` thành công = TLS an toàn | Bỏ qua chứng thư/cipher/ALPN thực | Xác minh qua handshake và negotiated session |
| Mặc định raw SSLEngine tự chạy I/O | Handshake không hoàn thành | Dùng đúng SSLEngine wrap/unwrap/tasks hoặc HTTP client |
| Dùng global debug flags ở production lâu dài | Log lớn, có thể lộ metadata | Bật có kiểm soát, tắt sau chẩn đoán |
| Không kiểm test âm | Không chứng minh boundary | Test CA sai, SAN sai, protocol/suite mismatch, ALPN mismatch |

## 16. Quy trình thiết kế cấu hình production

Một workflow có thể kiểm toán:

1. **Định nghĩa security policy:** TLS versions tối thiểu, cipher profiles, trust anchors, endpoint names, ALPN protocols và mTLS requirements; ghi rõ scope client/server.
2. **Kiểm provider/runtime:** Java version, JSSE provider, `getEnabledProtocols()`, enabled suites, `jdk.tls.disabledAlgorithms`, container image và root store.
3. **Ưu tiên default HTTPS client:** chỉ override khi có yêu cầu cụ thể và đã hiểu sự tương tác với HTTP/2, hostname verification, proxy/mesh.
4. **Nếu dùng raw SSLEngine/SSLSocket:** tạo context với trust/key managers đúng, dùng peer host thực, đặt client/server mode và cấu hình `SSLParameters` **trước handshake**.
5. **Dùng SNI đúng tên:** không dùng SNI như authorization; đối chiếu SAN/hostname của chứng thư.
6. **Đề xuất ALPN phù hợp ứng dụng:** HTTP/2 phải có stack h2; kiểm protocol đã thương lượng trước khi gửi dữ liệu.
7. **Giữ endpoint identification:** với HTTPS dùng thuật toán phù hợp, không bỏ chỉ vì private CA hoặc proxy.
8. **Kiểm cả chiều âm:** server sai hostname, CA không tin, EKU sai, protocol/suite yếu, ALPN mismatch đều phải được xử lý theo policy.
9. **Kiểm real negotiated state:** TLS version/cipher từ `SSLSession`, ALPN từ API sau handshake, peer certificate chain và identity thông qua TLS stack; không tự log secret.
10. **Quan sát và vận hành:** TLS handshake failure rate, protocol/cipher distribution, certificate renewal, truststore version và thay đổi ở server.
11. **Triển khai theo canary:** nhiều JVM/provider/regions, rollback được nhưng không bật lại chính sách yếu đã bị cấm.
12. **Thực hiện rotation/reload có chủ đích:** tạo context/client mới, quản lý session resumption/connection pooling và xử lý distrust CA khi cần.
13. **Đánh giá tương tác HTTP:** proxy, redirect, Alt-Svc, SNI/authority routing và HTTP/2 downgrade theo yêu cầu hệ thống.
14. **Không nhầm TLS authentication với application authorization:** dù TLS thành công, request vẫn phải được xác thực và cấp quyền nghiệp vụ.

### Ví dụ log nên và không nên

Nên (sau khi cân nhắc privacy): TLS version, cipher suite, ALPN negotiated, endpoint hostname, phiên bản trust bundle, loại lỗi handshake đã làm sạch, request/correlation ID. Không nên: private key, session secrets, raw application credentials, plaintext nhạy cảm, debug handshake chi tiết kéo dài hoặc bộ certificate chain chứa dữ liệu không cần cho mục đích giám sát.

## 17. Debug và xác định nguyên nhân handshake fail

Các nhóm lỗi hay gặp:

| Triệu chứng | Hướng kiểm tra |
| --- | --- |
| `SSLHandshakeException: no appropriate protocol` | Protocol allowlist, disabled algorithms, client/server versions |
| `no cipher suites in common` / `handshake_failure` | Giao giữa suites, TLS version, certificate algorithm và provider |
| `PKIX path building failed` | Truststore/CA chain, intermediate thiếu, CA policy, certificate validity |
| `No subject alternative DNS name matching` | SNI/URL host và leaf SAN, endpoint verification |
| ALPN chưa chọn `h2` | Server supported list, client offers, protocol implementations và negotiation |
| `no_application_protocol` alert | ALPN không giao trên peer yêu cầu ALPN và TLS stack báo lỗi |
| TLS thành công nhưng HTTP/2 fail | ALPN/config chưa thực sự có HTTP/2 codec hoặc proxy thay đổi |
| Hành vi khác sau restart | SSLContext/connection pools đã cache config cũ |
| SNI thiếu | Client tạo socket với IP, không set host, hoặc proxy/TLS library thay đổi |
| Certificate đúng nhưng mTLS client bị từ chối | Need/want client auth, client KeyManager, issuer trust và clientAuth EKU |
| Chỉ một JDK fail | Provider/version, truststore, disabledAlgorithms, cipher support khác |

Có thể bật JSSE debug trong môi trường kiểm soát:

```text
-Djavax.net.debug=ssl,handshake,trustmanager
```

Kết quả là log kỹ thuật lớn, có thể chứa hostnames, chứng thư và metadata nhạy cảm; chỉ thu thập khi cần và áp chính sách bảo vệ log. **Không** coi mọi thông điệp debug là bảo đảm protocol negotiation thành công; kiểm ứng dụng và TLS session thực tế.

## 18. Bài tập thực hành

### Bài 1 — Supported vs enabled

Chạy `SslParametersDemo` trên JDK 17. In danh sách `engine.getSupportedProtocols()` và `engine.getEnabledProtocols()` ở lab riêng, so sánh. Có protocol cũ nào supported nhưng không enabled? Giải thích tại sao không được bật lại chỉ để “tối đa compatibility”.

### Bài 2 — Tách protocol và cipher suites

Thay danh sách TLS versions được cho phép thành chỉ `TLSv1.2` trong lab, chọn một suite ECDHE-GCM đang enabled. Thiết lập suite TLS 1.3 để thấy cấu hình có thể không thương lượng được. Không dùng suite yếu để ép test pass.

### Bài 3 — Hai virtual hosts, một IP

Dựng hai TLS virtual hosts `api.example.test` và `admin.example.test` trong lab. Gửi SNI tương ứng, quan sát certificate. Sau đó yêu cầu kết nối tới `api.example.test` nhưng cố đặt SNI `admin.example.test`. Chứng minh endpoint identification vẫn từ chối nếu certificate không đúng hostname được yêu cầu.

### Bài 4 — ALPN và HTTP/2

Dùng server hỗ trợ cả `h2` và `http/1.1`, client offer hai giá trị, log `getApplicationProtocol()` sau handshake. Đổi server thành chỉ hỗ trợ `http/1.1` và kiểm fallback theo protocol policy. Tại sao ứng dụng không được gửi HTTP/2 frames trước khi xác định negotiated ALPN?

### Bài 5 — HTTPS endpoint identity

Tạo CA test và certificate có SAN `service.example.test`, thiết lập trust manager tin CA này. Test kết nối với đúng hostname và hostname khác, cả hai đều có thể đưa ra chain hợp lệ, nhưng chỉ hostname khớp mới được chấp nhận. Không tắt hostname check.

### Bài 6 — Per-client security policy

Một service gọi public API và private mTLS endpoint. Thiết kế hai `SSLContext`, truststores/KeyManagers phù hợp và `SSLParameters` riêng nếu cần. Phân tích SNI, ALPN, serverAuth/clientAuth, endpoint identity và authorization theo từng luồng.

### Bài 7 — Quản lý rollout

Hệ thống đang cho TLS 1.2 và 1.3; muốn dần chuyển sang TLS 1.3 only. Nêu telemetry cần thu, kiểm client compatibility, ALPN/HTTP2, cipher suite, JDK/provider và phương án rollback **không vi phạm** security policy.

### Bài 8 — Handshake state machine

Tạo một client `SSLEngine` thực sự kết nối tới test server qua TCP, xử lý `NEED_WRAP`, `NEED_UNWRAP`, `NEED_TASK` và `FINISHED` với timeout. So sánh với `SSLSocket` và HTTP client cấp cao. Nếu mục tiêu sản phẩm là HTTPS tiêu chuẩn, vì sao nên ưu tiên library hơn tự viết handshake loop?

### Bài 9 — Kiểm thử âm toàn diện

Tạo bảng test cho: CA không tin, certificate SAN sai, EKU chỉ clientAuth, không có shared TLS version, không có shared cipher suite, ALPN chỉ h2 khi server không hỗ trợ, SNI sai, mTLS client không có chứng thư, và connection pool giữ policy cũ. Chỉ rõ ca nào fail ở TLS, ca nào fail ở HTTP hoặc authorization.

**Điều kiện hoàn thành:** bạn biết chính xác giá trị nào thuộc `SSLParameters`, chúng được áp vào engine/socket thế nào, ba cơ chế **SNI – ALPN – hostname verification** khác nhau ở đâu, và tại sao chỉ khi handshake thành công cùng đầy đủ kiểm chứng peer thì mới được xem là có một kênh TLS xác thực.

## 19. Tài liệu tham khảo

- [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setProtocols`, `setCipherSuites`, `setServerNames`, `setApplicationProtocols`, `setEndpointIdentificationAlgorithm`.
- [Java SE 17 — SSLEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html): TLS nonblocking, `getSSLParameters`, `setSSLParameters`, `getApplicationProtocol`.
- [Java SE 17 — SSLSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html): TLS socket, `startHandshake`, `getApplicationProtocol`.
- [Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): key/trust managers và tạo engine/socket.
- [Java SE 17 — SNIHostName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SNIHostName.html): cấu trúc host_name SNI.
- [Java SE 17 — SSLSession](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): negotiated TLS version, cipher suite và peer metadata.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): per-client SSL context, params và HTTP version.
- [Java 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): cấu hình/handshake/trust manager/ALPN và endpoint checks.
- [RFC 6066 — TLS Extensions](https://www.rfc-editor.org/rfc/rfc6066): SNI.
- [RFC 7301 — TLS ALPN Extension](https://www.rfc-editor.org/rfc/rfc7301): ALPN negotiation.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): handshake, TLS 1.3 cipher suites và certificate authentication.
- [RFC 5246 — TLS 1.2](https://www.rfc-editor.org/rfc/rfc5246): TLS 1.2 protocol và cipher suite model.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): khớp danh tính endpoint bằng certificate identifiers.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS protocol choices, certificates và vận hành.
