# 15.8. SNI để chọn máy chủ ảo và ALPN để chọn giao thức ứng dụng

**SNI (Server Name Indication)** và **ALPN (Application-Layer Protocol Negotiation)** là hai cơ chế mở rộng TLS giải quyết **hai bài toán độc lập**. SNI cho server biết **tên máy chủ mà client muốn kết nối** ngay trong TLS handshake để server chọn cấu hình/chứng thư của máy chủ ảo. ALPN cho client và server **thương lượng giao thức ứng dụng** dùng bên trong kênh bảo mật, ví dụ HTTP/1.1 hay HTTP/2.

Điểm rất quan trọng: **SNI không xác thực danh tính client hoặc cấp quyền cho request**, còn **ALPN không tự cài đặt HTTP/2 hoặc bất kỳ giao thức ứng dụng nào**. Chúng cùng tham gia handshake nhưng phải phối hợp với chọn certificate, kiểm tra hostname/SAN, xây trust path, quản lý TLS session và application protocol handler. Trong Java 21, các API `SSLParameters`, `SNIHostName`, `ExtendedSSLSession`, `X509ExtendedKeyManager` và `SSLSocket` hỗ trợ thực hành cả hai cơ chế.

Bài này nằm trong chủ đề **“15. Nền tảng TLS”** của Java Advanced – Security & Cryptography. Bài lab dùng **TLS 1.3 và Java 21**, dựng một server TLS trên loopback có hai máy chủ ảo, chọn chứng thư theo SNI và thương lượng ALPN; đồng thời giải thích vì sao một kết nối TLS thành công không đồng nghĩa mọi lớp định danh/giao thức đều đã được xử lý an toàn.

## Mục tiêu học tập

Học xong, bạn có thể:

1. Trình bày SNI nằm ở đâu trong `ClientHello`, giúp chọn **virtual host/certificate** thế nào, vì sao thường cần trước HTTP `Host` hoặc HTTP/2 `:authority`.
2. Trình bày ALPN: client **đề xuất danh sách** application protocol IDs, server **chọn một giá trị được đề xuất và có hỗ trợ**, hoặc handshake không thể dùng protocol phù hợp.
3. Phân biệt **TLS protocol version** (ví dụ TLSv1.3), **cipher suite**, **SNI server name**, **ALPN application protocol** và **HTTP Host/:authority**.
4. Dùng `SSLParameters.setServerNames`, `SNIHostName`, `ExtendedSSLSession.getRequestedServerNames`, `SSLParameters.setApplicationProtocols` và `SSLSocket.getApplicationProtocol` trong Java 21.
5. Giải thích `X509ExtendedKeyManager.chooseServerAlias`/`chooseEngineServerAlias` và điều kiện để chọn đúng certificate theo hostname, đúng key type, đúng trust policy.
6. Tạo/tin cậy certificate cho hai host trong lab, bật **endpoint identification** kiểu HTTPS, đối chiếu SAN, quan sát kết quả TLS handshake.
7. Xử lý trường hợp thiếu/SNI không nhận ra, certificate sai hostname, ALPN không có phần tử chung, protocol handler không hỗ trợ giá trị đã chọn; không tự fallback mất an toàn.
8. Nhận ra vấn đề TLS termination ở reverse proxy, bảo mật thông tin tên miền, logging, kiểm thử và sự khác nhau giữa **thương lượng thành công** với **gửi HTTP thực sự**.

## 1. Hai extension giải quyết hai lớp quyết định khác nhau

Giả sử một IP/port `203.0.113.10:443` phục vụ hai domain:

- `blue.example.test` — certificate chứa DNS SAN cho `blue.example.test`.
- `green.example.test` — certificate chứa DNS SAN cho `green.example.test`.

Client kết nối cùng IP nhưng mong muốn **đúng domain**, và có thể sử dụng **HTTP/1.1** hoặc **HTTP/2**. Trước khi TLS được thiết lập, server phải quyết định certificate phù hợp; trước khi gửi application data, đôi bên phải biết chúng cùng nói giao thức ứng dụng nào.

```text
Client                                            TLS server :443
------                                            ---------------
ClientHello
  supported_versions = TLS 1.3
  server_name (SNI) = blue.example.test  --------> chọn virtual host blue
  ALPN = [http/1.1, demo/1]                        chọn certificate blue
  ...                                              chọn ALPN http/1.1
             <------- ServerHello / TLS handshake / certificate blue
Client kiểm chain + certificate hostname blue
             <------- handshake completes (TLS authenticated)
getApplicationProtocol() = "http/1.1"
             <------- application records theo protocol đã chọn
```

Đây là **sơ đồ logic**, không phải biểu diễn chính xác thứ tự byte của TLS 1.3. Trong TLS 1.3, lựa chọn ALPN của server xuất hiện trong `EncryptedExtensions`, còn certificate và Finished nằm trong các handshake messages tương ứng. Không hiểu sơ đồ như thể ALPN được gửi trong ServerHello của TLS 1.3.

| Câu hỏi | **SNI** | **ALPN** |
| --- | --- | --- |
| Mục tiêu | *Server nào trên IP/port này?* | *Giao thức ứng dụng nào chạy trên kênh TLS này?* |
| Bên cung cấp đề xuất | Client cung cấp tên server, thường DNS hostname | Client cung cấp **danh sách** protocol IDs được hỗ trợ |
| Bên quyết định | Server/terminator ánh xạ hostname → cấu hình/certificate/backend | Server chọn một application protocol được client đề xuất và server hỗ trợ |
| Ví dụ | `blue.example.test` | `http/1.1`, `h2` |
| Gắn với | Máy chủ ảo, certificate selection, virtual routing | HTTP/1.1, HTTP/2, các application protocols dùng TLS |
| Không phải | Kiểm tra hostname, client authentication, authorization | TLS version, cipher suite, framework thực thi ứng dụng |
| Java API | `SNIHostName`, `setServerNames`, `getRequestedServerNames`, key manager | `setApplicationProtocols`, `getApplicationProtocol`, protocol selector |

**Cách nhớ:** SNI quyết định **nói chuyện với host nào**; ALPN quyết định **nói bằng ngôn ngữ giao thức ứng dụng nào**. Cả hai là dữ liệu điều phối handshake, **không thay thế kiểm tra chứng thư và bảo mật kênh**.

## 2. SNI: vì sao HTTP Host đến quá muộn?

Trong HTTPS thông thường, thứ tự là:

1. Client mở kết nối TCP tới một IP và cổng.
2. TLS handshake bắt đầu, server cần **trình certificate** và chứng minh sở hữu private key tương ứng.
3. Client kiểm certificate chain, hostname và handshake.
4. Chỉ sau đó HTTP request mới được gửi qua TLS.

HTTP/1.1 `Host` và HTTP/2 `:authority` nằm trong **HTTP layer**, ở bước 4. Server không thể chờ nhận `Host` trong bản tin HTTP **mà chưa hoàn tất TLS** để biết nên trình chứng thư nào ở bước 2. Vì thế SNI được đặt trong `ClientHello`.

### 2.1 Virtual hosting một IP, nhiều chứng thư

```text
                  DNS
                  |
      blue.example.test ---\
                            -> IP:443 -> TLS ingress/virtual hosts
      green.example.test --/                    |
                                         SNI=blue?  -> key+cert blue
                                         SNI=green? -> key+cert green
                                         unknown?   -> reject/default theo policy
```

Server có thể dùng SNI để:

- Chọn **key pair + certificate chain** phù hợp tên host.
- Chọn TLS policy (chẳng hạn chứng thư/thuật toán hoặc yêu cầu mTLS tùy virtual host).
- Chọn tenant, listener, virtual server hoặc chuyển tiếp qua TLS proxy/ingress theo thiết kế.
- Ghi telemetry ở mức hostname (với chính sách riêng về thông tin nhạy cảm).

Không phải cứ có SNI là server buộc đổi certificate. Một **SAN certificate** có thể chứa nhiều DNS names, hoặc wildcard phù hợp policy có thể phục vụ nhiều tên. SNI chỉ là tín hiệu lựa chọn; **tính hợp lệ của chứng thư được client kiểm riêng**.

### 2.2 SNI là đề nghị, không phải danh tính đã xác thực

Client có thể tự điền bất kỳ hostname nào vào SNI; client độc hại có thể gửi tên không tồn tại, tên của tenant khác hoặc không gửi extension. Vì vậy:

- **Không** dùng “client gửi SNI=admin.example.test” làm bằng chứng client thuộc nhóm admin.
- **Không** bỏ qua authorization trên ứng dụng chỉ vì TLS terminator chọn đúng virtual host.
- Không cấp quyền dựa vào SNI nếu không có kiểm soát xác thực độc lập.
- Nếu SNI không hợp lệ/không được hỗ trợ, thiết kế rõ **reject**, default certificate hoặc default tenant. Đừng silently route tenant nhạy cảm sang tenant khác.
- Đối chiếu SNI với HTTP Host/:authority theo đúng proxy policy để tránh hostname/tenant confusion, request smuggling và định tuyến nhầm.

### 2.3 Chuyện gì xảy ra khi client không gửi SNI?

Khả năng thường gặp: client kết nối trực tiếp bằng địa chỉ IP, client cũ không hỗ trợ SNI, hoặc ứng dụng bỏ cấu hình `setServerNames`. Server có thể chọn default certificate, từ chối, hoặc dùng routing khác theo cấu hình; **không có đáp án duy nhất**.

Nếu server chọn certificate `blue.example.test` nhưng client mong `green.example.test`, client có bật hostname verification kiểu HTTPS **phải từ chối** chứng thư không khớp, ngay cả khi CA chain hợp lệ. Việc server “gửi được certificate” không có nghĩa client phải tin nó.

### 2.4 Quy tắc hostname thực tế

- SNI `host_name` dùng tên DNS tương thích định dạng TLS, **không chứa scheme `https://`, port `:443`, URL path hoặc token**.
- `SNIHostName` hỗ trợ tên DNS và xử lý mã hóa/ASCII theo Java API; ứng dụng cần quy ước hostname, IDN/Punycode và normalization cho dữ liệu đầu vào.
- Một địa chỉ IP không phải DNS hostname bình thường cho extension `host_name`; client kết nối IP cần kiểm tra certificate IP SAN theo policy, không mặc định lấy một DNS SNI giả.
- Certificate identity verification phải xét **DNS SAN hoặc IP SAN** theo ứng dụng/giao thức, không chỉ kiểm xem subject CN có vẻ giống.
- Wildcard và hostname dạng quốc tế cần tuân thủ quy tắc xác minh chuẩn, tránh tự so `String.endsWith` để thay TLS hostname verifier.

### 2.5 SNI có “mã hóa” không?

Trong TLS thông thường, tên SNI ở `ClientHello` thường **có thể bị quan sát** bởi thiết bị trên đường truyền; HTTPS mã hóa nội dung ứng dụng không mặc định che giấu tên server. Cơ chế **Encrypted ClientHello (ECH)** có thể bảo vệ thông tin hostname thực bên trong ClientHello trong những triển khai hỗ trợ, nhưng không nên giả định mọi JDK/client/server đều đã triển khai ECH hoặc nó luôn được bật. ALPN cũng không phải cơ chế ẩn danh. Tránh đưa thông tin định danh riêng tư vào tên virtual host hoặc log SNI không kiểm soát.

## 3. ALPN: thương lượng giao thức nào sẽ đi bên trong TLS?

**ALPN** theo RFC 7301 cho phép client cung cấp các identifiers của **application protocols** mà client hỗ trợ. Server lựa chọn **một** identifier phù hợp; lựa chọn này là cam kết dùng giao thức tương ứng trên kết nối đã xác thực.

Ví dụ client đề xuất:

```text
ALPN offered by client = ["demo/1", "http/1.1"]
Server supports        = ["http/1.1", "demo/1"]
Selected               = "http/1.1"
```

Trong bài lab, server có `http/1.1` đầu danh sách ưu tiên, vì thế kết quả là `http/1.1`. Giá trị `demo/1` là protocol ID chỉ để **minh họa negotiation**, **không phải** một chuẩn ứng dụng được triển khai trong bài.

Các giá trị quen thuộc:

- `http/1.1`: HTTP/1.1 qua TLS.
- `h2`: HTTP/2 qua TLS, cần endpoint thực sự có HTTP/2 framing, HPACK, multiplexing và các yêu cầu của giao thức.
- `h3`: HTTP/3 qua QUIC (không phải “HTTP/3 trên `SSLSocket` TCP”); QUIC dùng TLS handshake theo cách tích hợp khác JSSE socket minh họa ở đây.
- Các protocol IDs chuyên dụng khác do giao thức/profile xác định; không được tự giả mạo một ID được đăng ký cho giao thức mà server chưa hỗ trợ.

**Không đồng nhất:** `TLSv1.3` là phiên bản giao thức bảo vệ kênh; `TLS_AES_128_GCM_SHA256` là TLS 1.3 cipher suite; `http/1.1` là application protocol thông qua ALPN. Không thể cho `setApplicationProtocols(new String[]{"TLSv1.3"})` rồi kỳ vọng thương lượng phiên bản TLS.

### 3.1 Server chọn thế nào?

- Client thông báo những protocol IDs **mà nó thật sự có thể nói**.
- Server chỉ chọn một ID trong danh sách client gửi **và** server thực sự hỗ trợ.
- Nếu client và server không có giao thức chung và ALPN được yêu cầu để chọn protocol, RFC 7301 yêu cầu server kết thúc bằng alert **`no_application_protocol`**. Không lén chọn giao thức không được quảng bá.
- Sau khi chọn, endpoint **phải dùng đúng** protocol ID đã thương lượng; không đáp lại `h2` rồi thực tế gửi HTTP/1.1.
- Nếu handshake **không thương lượng ALPN**, `getApplicationProtocol()` có thể là chuỗi trống. Ứng dụng phải có chính sách rõ ràng: khi nào cho phép fallback legacy, khi nào fail-closed.

Không phải “ALPN fail thì tự hạ xuống HTTP/1.1” luôn an toàn. Với server yêu cầu HTTP/2 hoặc application protocol chuyên dụng, **không có ALPN hoặc ALPN sai phải bị từ chối** theo profile.

### 3.2 ALPN không biến một socket thành HTTP/2

`SSLSocket.getApplicationProtocol()` chỉ trả giá trị đã được TLS thương lượng. Phần code gửi/nhận HTTP/1.1, HTTP/2 hoặc protocol ứng dụng phải được framework hoặc ứng dụng thực hiện **sau** handshake. Bài lab của chúng ta chỉ mở TLS và kiểm kết quả ALPN, **không gửi bất kỳ HTTP request nào**; vì vậy không được gọi đó là “HTTP server thực tế”.

Với Java `HttpClient`, server như Netty/Jetty hoặc JSSE-based framework, ALPN thường do stack HTTP/TLS tích hợp quản lý. Không cần tự viết client/server TLS socket trong production chỉ để dùng ALPN.

## 4. Liên hệ SNI – certificate – ALPN – HTTP routing

Một kiến trúc nhiều tenant:

```text
TLS ClientHello
  SNI = blue.example.test
  ALPN offered = [http/1.1, demo/1]
           |
           v
TLS terminator / ingress
  1. Map SNI → vhost blue
  2. Select key + certificate chain của blue
  3. Select ALPN application protocol http/1.1
  4. Complete TLS handshake
           |
           v
Client verifies certificate chain + hostname blue
           |
           v
Application handler for http/1.1 (if implemented)
           |
           v
HTTP Host + route + tenant + authentication/authorization
```

Các bước này có phạm vi riêng:

| Bước | Nguồn dữ liệu | Quyết định | Nếu bỏ kiểm tra |
| --- | --- | --- | --- |
| SNI | ClientHello hostname | Chọn certificate/vhost | Có thể trình nhầm certificate hoặc route nhầm tenant |
| TLS certificate | Certificate server trình | Client tin root nào, cert có khớp hostname không? | MITM/giả server nếu bỏ trust/hostname verification |
| ALPN | Danh sách ứng dụng client + policy server | Chọn đúng handler/protocol | HTTP/1.1/HTTP/2 framing không khớp, lỗi hoặc protocol confusion |
| HTTP Host/:authority | HTTP message sau TLS | Route request đến virtual service | Domain fronting/mismatch/tenant confusion nếu tin mù quáng |
| Authentication | Client credentials, mTLS, session/token | Ai là người gọi? | SNI không chứng minh danh tính người dùng |
| Authorization | Policy ứng dụng | Người gọi được phép làm gì? | TLS bắt tay tốt nhưng vẫn có thể thực thi yêu cầu trái quyền |

### 4.1 TLS được terminate ở đâu?

Ở reverse proxy, ingress hoặc load balancer có thể có các mô hình:

- **TLS termination tại edge:** edge nhận SNI, chọn certificate, thương lượng ALPN rồi giải mã HTTP; kết nối giữa edge và backend là **một hop khác**, phải có chính sách TLS, trust, header và identity riêng.
- **TLS passthrough:** proxy không giải mã handshake/HTTP có thể định tuyến theo SNI nhìn thấy ở ClientHello nếu cấu hình cho phép; backend vẫn trình certificate và làm TLS handshake.
- **TLS re-encryption:** edge kết thúc TLS và tạo TLS mới đến backend, có **SNI/ALPN mới** cho hop backend; không mặc định giữ nguyên tên/cert/client identity ở hai hop.

Không chuyển giá trị HTTP `X-Forwarded-Host` hoặc `Host` do client tự đưa thành nguồn xác thực tenant nếu chưa có chính sách reverse proxy loại bỏ/ghi đè headers không tin cậy. Chứng thực HTTPS ở hop client-edge không tự cung cấp TLS end-to-end đến backend.

### 4.2 Chọn chứng thư trước khi xác minh danh tính server

Server đọc SNI để chọn certificate. Client **không được** lấy tên certificate server gửi rồi thay tên đích cần xác minh. Tên đích phải đến từ URI/target/endpoint mà client **dự định** truy cập; SNI thường được gửi theo chính tên ấy. Nếu server đổi sang cert hợp lệ của domain khác, hostname verification phải fail.

## 5. Java 21 API: SNI và ALPN nằm ở đâu?

| API | Dùng ở đầu nào? | Vai trò |
| --- | --- | --- |
| `SSLParameters.setServerNames(List<SNIServerName>)` | Client | Đặt SNI extension cho handshake |
| `new SNIHostName("blue.example.test")` | Client | Đóng gói DNS hostname dạng SNI |
| `ExtendedSSLSession.getRequestedServerNames()` | Server | Đọc các SNI names client yêu cầu từ handshake/session |
| `X509ExtendedKeyManager.chooseServerAlias(...)` | Server với `SSLSocket` | Chọn alias/cert phù hợp key type, issuers và SNI |
| `X509ExtendedKeyManager.chooseEngineServerAlias(...)` | Server với `SSLEngine` | Như trên nhưng dùng engine cho NIO/framework |
| `SSLParameters.setSNIMatchers(...)` | Server | Có thể ràng buộc tên SNI chấp nhận; không tự thay thế key/cert routing |
| `SSLParameters.setApplicationProtocols(String[])` | Client và server | Đặt danh sách ALPN IDs hỗ trợ (thường theo thứ tự ưu tiên) |
| `SSLSocket.getApplicationProtocol()` | Hai đầu, sau handshake | Trả ID được thương lượng, `""` nếu không dùng ALPN, `null` nếu chưa xác định |
| `SSLSocket.getHandshakeApplicationProtocol()` | Trong handshake | Xem ALPN value đang thương lượng nếu đã có |
| `SSLSocket.setHandshakeApplicationProtocolSelector(...)` | Server | Callback chọn ID trong danh sách client đề xuất |
| `SSLEngine` tương ứng | Framework non-blocking | Có API SNI/ALPN/handshake tương ứng |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Client | Yêu cầu kiểm server identity theo thuật toán endpoint `HTTPS` |
| `TrustManagerFactory` / `KeyManagerFactory` | Client/server | Dùng trust anchors và private keys/certificate chains hợp lệ |

### 5.1 Tên miền SNI do client đặt

Ví dụ minh họa (đoạn này **không độc lập**, giả sử biến `SSLSocket socket` đã được tạo):

```java
SSLParameters p = socket.getSSLParameters();
p.setServerNames(List.of(new SNIHostName("blue.example.test")));
p.setApplicationProtocols(new String[] {"http/1.1"});
p.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(p);
socket.startHandshake();
String protocol = socket.getApplicationProtocol();
```

Với production, client phải cung cấp truststore/trust manager đúng, sử dụng hostname đích tin cậy, không vô hiệu hóa endpoint identification và chỉ advertise ALPN IDs mình có thể implement.

### 5.2 Server nhận SNI trong handshake

Trong `X509ExtendedKeyManager.chooseServerAlias`, có thể lấy `((SSLSocket) socket).getHandshakeSession()` và nếu đó là `ExtendedSSLSession`, đọc `getRequestedServerNames()`. Việc lựa chọn certificate còn phải đáp ứng **keyType, issuers, key algorithm, provider policy**. Không chọn alias mù quáng chỉ vì trùng hostname, rồi bỏ mọi điều kiện mật mã.

Với `SSLEngine`, không có `Socket` để xem SNI; dùng `chooseEngineServerAlias` và `engine.getHandshakeSession()`. Một key manager chỉ override `chooseServerAlias` có thể **không hoạt động đúng** khi framework dùng `SSLEngine`.

### 5.3 ALPN selector tường minh

Ví dụ **minh họa** bên trong server loop trước `startHandshake()`:

```java
connection.setHandshakeApplicationProtocolSelector((socket, offered) ->
        offered.contains("http/1.1") ? "http/1.1" : null);
```

Ở đây `offered` là danh sách ALPN do client quảng bá; `null` báo không chọn được ID. Trong ALPN, provider có thể kết thúc kết nối bằng alert `no_application_protocol`. Selector có thể override danh sách cấu hình tĩnh bằng `setApplicationProtocols`, nên **không** trả giá trị không có trong danh sách client nếu muốn tránh handshake failure. Trong ứng dụng thật, logic selector phải dựa vào capability và policy, không phải “chọn một giá trị cho đẹp log”.

Bài lab dùng `setApplicationProtocols` hai phía để minh họa thứ tự ưu tiên; không dùng callback custom trong chương trình chính.

## 6. Thực hành Java 21: hai virtual hosts, hai chứng thư, một TLS listener

Chúng ta sẽ tạo một **TLS server trên loopback** không cần internet, có hai certificate được cùng một CA lab ký:

```text
server.p12:
  lab-ca    : private key + CA certificate          (chỉ vì lab)
  blue      : private key + leaf SAN blue.example.test + CA chain
  green     : private key + leaf SAN green.example.test + CA chain

trust.p12:
  lab-ca    : TrustedCertificateEntry (chỉ certificate công khai)
```

Trong thực tế phải **tách CA private key** khỏi ứng dụng server và bảo vệ bằng hệ thống PKI/HSM/offline CA phù hợp. Fixture có CA key cùng `server.p12` chỉ để tự tạo chứng thư nhanh trong một thư mục tạm. Tuyệt đối không triển khai file lab lên production.

Client không dùng default trust-all; thay vào đó, `TrustManagerFactory` tin **chỉ CA lab đã chủ đích import**. Client bật endpoint identification `"HTTPS"`, so sánh thêm DNS SAN để dễ đọc output. Server dùng một `X509ExtendedKeyManager` bọc `SunX509` chọn alias **blue hoặc green** theo SNI.

### 6.1 Chuẩn bị JDK và password lab

Dùng JDK 21 hoặc phiên bản mới hơn có hỗ trợ `--release 21` và provider SunJSSE/SunJCE thông thường. Tạo thư mục lab riêng và mở terminal tại đó.

**PowerShell:**

```powershell
$env:TLS_DEMO_PASS = 'LabOnly-SniAlpn42'
```

**Bash:**

```bash
export TLS_DEMO_PASS='LabOnly-SniAlpn42'
```

Đây là **mật khẩu ví dụ công khai**, không phải secret đủ an toàn cho môi trường thật. `keytool` đọc password bằng `-storepass:env TLS_DEMO_PASS`, tránh đưa **giá trị** trực tiếp vào command line. Biến môi trường vẫn có rủi ro bị lộ qua môi trường chạy/log và không thay thế secret manager.

### 6.2 Tạo CA chỉ dùng để ký hai chứng thư test

Chạy một dòng:

```text
keytool -genkeypair -alias lab-ca -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Local Lab CA,O=Training,C=VN" -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -validity 20 -keystore server.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS -keypass:env TLS_DEMO_PASS -noprompt
```

CA có `BasicConstraints CA:TRUE, pathLen:0`, dùng ký leaf trực tiếp. Đây là **self-signed test CA**, không được tin bởi các hệ thống công khai.

### 6.3 Tạo hai virtual host certificates với DNS SAN riêng

```text
keytool -genkeypair -alias blue -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=blue.example.test,O=Training,C=VN" -ext "SAN=dns:blue.example.test" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -signer lab-ca -signerkeypass:env TLS_DEMO_PASS -validity 12 -keystore server.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS -keypass:env TLS_DEMO_PASS -noprompt
keytool -genkeypair -alias green -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=green.example.test,O=Training,C=VN" -ext "SAN=dns:green.example.test" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -signer lab-ca -signerkeypass:env TLS_DEMO_PASS -validity 12 -keystore server.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS -keypass:env TLS_DEMO_PASS -noprompt
```

Với `-signer lab-ca`, `keytool` tạo mỗi leaf do CA lab ký và lưu chain trong cùng PKCS12. Aliases `blue` và `green` là **tên entry nội bộ**, khác với tên host DNS. Trong ví dụ, key manager ánh xạ DNS name sang alias cố định; ánh xạ này do ứng dụng/tenant configuration xác định.

### 6.4 Xuất CA public certificate và tạo truststore cho client

```text
keytool -exportcert -rfc -alias lab-ca -keystore server.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS -file ca.pem
keytool -importcert -alias lab-ca -file ca.pem -keystore trust.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS -noprompt
```

`trust.p12` chứa một `TrustedCertificateEntry` CA lab, không chứa CA private key. Việc import là **quyết định tin cậy chủ động** chỉ cho bài lab. Không import CA này vào system truststore hoặc JDK `cacerts` dùng cho ứng dụng thực.

Kiểm tra cấu trúc:

```text
keytool -list -v -alias blue -keystore server.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS
keytool -list -v -alias green -keystore server.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS
keytool -list -v -alias lab-ca -keystore trust.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS
```

Hai alias `blue`/`green` là `PrivateKeyEntry` chứa leaf tương ứng cùng chain; CA trong truststore là `trustedCertEntry` (cách viết nhãn phụ thuộc JDK). Chỉ đọc metadata, không xuất private key.

## 7. Chương trình chạy đầy đủ `SniAlpnDemo.java`

Ví dụ dùng **TLSv1.3** và `SSLServerSocket` nhận hai kết nối loopback. Socket của client thực sự kết nối địa chỉ loopback; `createSocket(tcp, name, port, true)` đặt **peer hostname logic** thành `blue.example.test` hoặc `green.example.test`. Nhờ đó thử được hostname verification mà **không cần sửa DNS hoặc file hosts** trên máy.

Các điểm sẽ quan sát:

- SNI `blue.example.test` → `SniKeyManager` chọn alias `blue` → certificate SAN blue.
- SNI `green.example.test` → alias `green` → certificate SAN green.
- Client đề xuất `demo/1` trước `http/1.1`; server có thứ tự `http/1.1` trước `demo/1`. Giá trị được chọn là `http/1.1` trong provider SunJSSE đã kiểm thử.
- Client dùng `setEndpointIdentificationAlgorithm("HTTPS")` và CA lab truststore; nếu sai SAN/certificate, handshake không được xem là thành công.
- Server đọc SNI thông qua `ExtendedSSLSession` **sau** handshake và in hai tên đã nhận.
- Server không gửi HTTP; kết quả ALPN chỉ chứng minh **thương lượng tên protocol**, không chứng minh implement HTTP.

Tạo file **`SniAlpnDemo.java`** (tên class public phải khớp file):

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.Principal;
import java.security.PrivateKey;
import java.security.SecureRandom;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import javax.net.ssl.ExtendedSSLSession;
import javax.net.ssl.KeyManager;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SNIHostName;
import javax.net.ssl.SNIServerName;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509ExtendedKeyManager;

public class SniAlpnDemo {
    static final class SniKeyManager extends X509ExtendedKeyManager {
        private final X509ExtendedKeyManager base;
        SniKeyManager(X509ExtendedKeyManager base) { this.base = base; }

        private String aliasFor(List<SNIServerName> requested) {
            for (SNIServerName name : requested) {
                if (name instanceof SNIHostName host) {
                    if ("blue.example.test".equalsIgnoreCase(host.getAsciiName())) return "blue";
                    if ("green.example.test".equalsIgnoreCase(host.getAsciiName())) return "green";
                }
            }
            return null;
        }
        private String selected(String keyType, Principal[] issuers,
                                List<SNIServerName> requested) {
            String required = aliasFor(requested);
            if (required == null) return null; // Do not silently use another cert.
            String[] compatible = base.getServerAliases(keyType, issuers);
            if (compatible == null) return null;
            for (String candidate : compatible) {
                if (candidate.equalsIgnoreCase(required)) return candidate;
            }
            return null;
        }
        @Override public String chooseServerAlias(String type,
                        Principal[] issuers, Socket socket) {
            if (!(socket instanceof SSLSocket ssl)) return null;
            if (!(ssl.getHandshakeSession() instanceof ExtendedSSLSession session))
                return null;
            return selected(type, issuers, session.getRequestedServerNames());
        }
        @Override public String chooseEngineServerAlias(String type,
                        Principal[] issuers, SSLEngine engine) {
            if (!(engine.getHandshakeSession() instanceof ExtendedSSLSession session))
                return null;
            return selected(type, issuers, session.getRequestedServerNames());
        }
        @Override public String[] getClientAliases(String type, Principal[] issuers) {
            return base.getClientAliases(type, issuers);
        }
        @Override public String chooseClientAlias(String[] types,
                        Principal[] issuers, Socket socket) {
            return base.chooseClientAlias(types, issuers, socket);
        }
        @Override public String chooseEngineClientAlias(String[] types,
                        Principal[] issuers, SSLEngine engine) {
            return base.chooseEngineClientAlias(types, issuers, engine);
        }
        @Override public String[] getServerAliases(String type, Principal[] issuers) {
            return base.getServerAliases(type, issuers);
        }
        @Override public X509Certificate[] getCertificateChain(String alias) {
            return base.getCertificateChain(alias);
        }
        @Override public PrivateKey getPrivateKey(String alias) {
            return base.getPrivateKey(alias);
        }
    }

    static KeyStore load(Path path, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream stream = Files.newInputStream(path)) {
            store.load(stream, password);
        }
        return store;
    }

    static SSLContext serverContext(KeyStore identity, char[] password)
            throws Exception {
        KeyManagerFactory kmf = KeyManagerFactory.getInstance("SunX509");
        kmf.init(identity, password);
        X509ExtendedKeyManager delegate = null;
        for (KeyManager manager : kmf.getKeyManagers()) {
            if (manager instanceof X509ExtendedKeyManager extended) {
                delegate = extended;
                break;
            }
        }
        if (delegate == null) throw new IllegalStateException("No X509 key manager");
        SSLContext context = SSLContext.getInstance("TLSv1.3");
        context.init(new KeyManager[]{new SniKeyManager(delegate)},
                     null, new SecureRandom());
        return context;
    }

    static SSLContext clientContext(KeyStore anchors) throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(anchors);
        SSLContext context = SSLContext.getInstance("TLSv1.3");
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    static String requestedHost(SSLSocket socket) {
        if (socket.getSession() instanceof ExtendedSSLSession session) {
            for (SNIServerName n : session.getRequestedServerNames()) {
                if (n instanceof SNIHostName host) return host.getAsciiName();
            }
        }
        return "(missing)";
    }

    static boolean sanMatches(X509Certificate leaf, String name)
            throws Exception {
        Collection<List<?>> sans = leaf.getSubjectAlternativeNames();
        if (sans == null) return false;
        for (List<?> san : sans) {
            if (Integer.valueOf(2).equals(san.get(0))
                    && name.equalsIgnoreCase((String) san.get(1))) return true;
        }
        return false;
    }

    static void connect(SSLContext context, int port, String name)
            throws Exception {
        try (Socket tcp = new Socket(InetAddress.getLoopbackAddress(), port);
             SSLSocket tls = (SSLSocket) context.getSocketFactory()
                     .createSocket(tcp, name, port, true)) {
            SSLParameters parameters = tls.getSSLParameters();
            parameters.setProtocols(new String[]{"TLSv1.3"});
            parameters.setServerNames(List.of(new SNIHostName(name)));
            parameters.setApplicationProtocols(
                    new String[]{"demo/1", "http/1.1"});
            parameters.setEndpointIdentificationAlgorithm("HTTPS");
            tls.setSSLParameters(parameters);
            tls.startHandshake();
            X509Certificate cert =
                    (X509Certificate) tls.getSession().getPeerCertificates()[0];
            System.out.println(name + ": ALPN=" + tls.getApplicationProtocol()
                    + ", certificate SAN matches=" + sanMatches(cert, name));
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException(
                "Usage: java SniAlpnDemo server.p12 trust.p12");
        String env = System.getenv("TLS_DEMO_PASS");
        if (env == null) throw new IllegalStateException("Missing TLS_DEMO_PASS");
        char[] password = env.toCharArray();
        try {
            SSLContext serverCtx = serverContext(load(Path.of(args[0]), password),
                                                 password);
            SSLContext clientCtx = clientContext(load(Path.of(args[1]), password));
            String[] seen = new String[2];
            AtomicReference<Throwable> failure = new AtomicReference<>();
            try (SSLServerSocket listener = (SSLServerSocket)
                    serverCtx.getServerSocketFactory().createServerSocket(
                            0, 2, InetAddress.getLoopbackAddress())) {
                Thread server = new Thread(() -> {
                    try {
                        for (int i = 0; i < 2; i++) {
                            try (SSLSocket connection = (SSLSocket) listener.accept()) {
                                SSLParameters p = connection.getSSLParameters();
                                p.setProtocols(new String[]{"TLSv1.3"});
                                p.setApplicationProtocols(
                                        new String[]{"http/1.1", "demo/1"});
                                connection.setSSLParameters(p);
                                connection.startHandshake();
                                seen[i] = requestedHost(connection);
                            }
                        }
                    } catch (Throwable t) {
                        failure.set(t);
                    }
                });
                server.start();
                connect(clientCtx, listener.getLocalPort(), "blue.example.test");
                connect(clientCtx, listener.getLocalPort(), "green.example.test");
                server.join();
                if (failure.get() != null) throw new Exception(failure.get());
                System.out.println("server SNI: " + String.join(", ", seen));
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

### 7.1 Biên dịch và chạy

Sau khi có `server.p12`, `trust.p12` và `SniAlpnDemo.java` trong thư mục hiện tại:

```text
javac --release 21 -encoding UTF-8 SniAlpnDemo.java
java SniAlpnDemo server.p12 trust.p12
```

**Stdout đã kiểm thử:**

```text
blue.example.test: ALPN=http/1.1, certificate SAN matches=true
green.example.test: ALPN=http/1.1, certificate SAN matches=true
server SNI: blue.example.test, green.example.test
```

Fixture được tạo và chương trình đã được biên dịch bằng `javac --release 21`, chạy thành công với JSSE trong JDK có sẵn. Certificate, serial number, private keys, phiên TLS và session secrets thay đổi giữa các lần chạy nhưng những dòng boolean/ALPN dự kiến vẫn như trên nếu giữ cấu hình. Nếu môi trường dùng provider khác `SunX509` hoặc không hỗ trợ thuật toán, API có thể trả lỗi; xem phần troubleshooting.

### 7.2 Vì sao lại dùng `createSocket(tcp, name, port, true)`?

Kết nối TCP thực tế vào `InetAddress.getLoopbackAddress()` ở port server được cấp ngẫu nhiên. Tên peer logic `blue.example.test` dùng làm **hostname đích để TLS endpoint identification**. Thêm `new SNIHostName(name)` khiến hostname SNI rõ ràng dù kết nối vào loopback. Nhờ đó tránh cài DNS/hosts giả, nhưng **không** nên coi đây là lời khuyên bỏ qua DNS và tự giả hostname trong sản phẩm: tên đích phải đến từ cấu hình tin cậy.

### 7.3 Vì sao `SniKeyManager` phải kiểm cả `keyType`?

Trong JSSE, server certificate selection chịu ràng buộc scheme/key type, provider, issuer constraints và signatures mà hai phía hỗ trợ. Chọn alias đúng hostname nhưng key algorithm **không phù hợp** vẫn có thể làm TLS handshake thất bại hoặc gây policy violation. Wrapper dùng `base.getServerAliases(keyType, issuers)` rồi chỉ trả alias nếu có trong danh sách tương thích.

Wrapper dành cho **bài lab**, không phải bộ chọn certificate production đầy đủ: không có hot reload, wildcard matching, IDN rules, fallback policy, quyền tenant, chain expiration/rotation, logging/monitoring, cache hoặc kiểm thử mọi provider. Trong sản phẩm, ưu tiên capability của TLS server/framework được bảo trì, cấu hình key manager đáng tin và test đầy đủ.

### 7.4 Vì sao server vẫn nhận được SNI sau TLS handshake?

`ExtendedSSLSession.getRequestedServerNames()` cung cấp SNI names đã nhận. Trong `chooseServerAlias`/`chooseEngineServerAlias`, code đọc từ **handshake session** vì quyết định certificate phải được đưa ra *trước* khi handshake hoàn tất. Sau handshake, phương thức `requestedHost` của demo xem thông tin từ established session chỉ để in log.

Nếu không có SNI hoặc không có host được map, wrapper trả `null` thay vì tự chọn certificate của tenant khác. Provider có thể thử các key types khác nhau; nếu không có alias phù hợp thì handshake không được chấp nhận. Một deployment có policy default certificate rõ ràng có thể thiết kế khác, nhưng phải giữ hostname verification và tenant isolation.

### 7.5 Vì sao `getApplicationProtocol()` trả HTTP/1.1?

Client set ALPN list `["demo/1","http/1.1"]`; server set `["http/1.1","demo/1"]`. Với SunJSSE trong lab, server chọn `http/1.1` theo ưu tiên của server. **ALPN không đọc SNI để tự quyết định HTTP routing**; đây là thương lượng protocol IDs độc lập với virtual host selection.

Giá trị `"http/1.1"` **không có nghĩa chương trình đã phục vụ HTTP/1.1**. Lab không có HTTP parser hoặc response; cả hai socket chỉ hoàn thành TLS handshake rồi đóng. Một ứng dụng thật phải tiếp tục dispatch tới **protocol handler** tương ứng. Với HTTP/2, handler phải biết framing/multiplexing và những ràng buộc HTTP/2 TLS theo profile.

### 7.6 Vì sao tin CA lab nhưng vẫn cần xác minh hostname?

`TrustManagerFactory` với `trust.p12` cho client biết **CA nào được tin**. Từ đó JSSE có thể xác minh chain được server trình. Nhưng CA đó có thể cấp cả hai tên blue/green, nên **hostname verification** vẫn phải xác định certificate của **đúng DNS name mà client dự kiến**.

`setEndpointIdentificationAlgorithm("HTTPS")` yêu cầu kiểm identity thích hợp với hostname peer. Hàm `sanMatches` tự so DNS SAN để in boolean chỉ giúp người học quan sát, **không thay thế** hostname verification chuẩn (wildcard, IDN, IP và các quy tắc khác cần chuẩn TLS client).

## 8. Điều gì xảy ra khi cấu hình SNI hoặc ALPN sai?

| Tình huống | Hệ quả điển hình | Cách xử lý đúng |
| --- | --- | --- |
| Client không gửi SNI | Server chọn default hoặc từ chối theo policy; có thể chọn cert không khớp tên đích | Thiết kế default/fail-closed, bật hostname verification phía client |
| SNI là `red.example.test` nhưng server chỉ có blue/green | Không có alias/cert phù hợp trong demo; handshake có thể fail | Không tự route sang tenant khác; báo lỗi handshake an toàn |
| SNI gửi blue nhưng client định kết nối green | Chứng thư blue không khớp peer hostname green | Xác thực hostname lấy từ target, không lấy từ chứng thư được trình |
| Chain đúng root nhưng SAN không khớp | PKIX trust thành công vẫn chưa đủ xác thực endpoint | Bật `HTTPS` endpoint identification |
| Client chỉ đề xuất `h2`, server chỉ hỗ trợ `http/1.1` | ALPN không có giao thức chung, thường fatal `no_application_protocol` | Chỉ chọn ID có chung; từ chối khi profile bắt buộc |
| ALPN ID là `h2` nhưng server chỉ có HTTP/1.1 handler | Phá quy tắc ứng dụng, framing mismatch | Chỉ advertise giao thức được cài đặt và kiểm thử |
| ALPN không được thương lượng, `getApplicationProtocol()==""` | Không có protocol ID đã chọn từ ALPN | Có fallback **chỉ nếu** profile cho phép; còn lại từ chối |
| Giả HTTP Host khác SNI | Có nguy cơ cross-tenant/misdirected request nếu routing mù quáng | Ràng buộc SNI, endpoint, HTTP authority và tenant policy |
| Provider Java thiếu ALPN/SNI APIs hoặc hành vi khác | `UnsupportedOperationException`, handshake error hoặc lựa chọn khác | Kiểm runtime/provider và các khả năng được hỗ trợ |
| Hợp lệ lần đầu, reload cert/rotate key không đồng bộ | Kết nối mới có thể dùng chain cũ/sai, SNI map lỗi | Quy trình cập nhật atomic, kiểm tra từng hostname và rollback |
| Proxy terminate TLS nhưng backend tưởng có cùng SNI | Backend nhận connection TLS mới với peer host/suite khác | Định nghĩa trust và routing riêng cho mỗi TLS hop |
| SSL server chưa load đúng private key/certificate alias | Không chọn được certificate thích hợp | Kiểm tra KeyStore alias/type, key password, chain và key manager |
| Dùng IP address khi client cần domain | Không thể dựa vào SNI DNS mặc định; certificate IP SAN có rule khác | Dùng hostname đích đáng tin hoặc thiết kế identity cho IP |

### 8.1 Nguyên tắc không fallback mất an toàn

Trong một hệ thống nhiều tenant, nếu `SNI=tenant-b` nhưng không tìm được certificate tenant-b, **đừng tự chọn** tenant-a và bỏ qua kiểm certificate name. Nếu ALPN yêu cầu `h2` nhưng server chỉ implement HTTP/1.1, **đừng trả `h2`** rồi gửi dữ liệu HTTP/1.1. Nếu hostname verification thất bại, **đừng tạo trust-all manager** để test rồi giữ lại trong production.

Cơ chế bảo mật phải **fail closed** theo policy. Ngoại lệ có thể được chấp nhận khi có thiết kế explicit, ví dụ một default certificate cho domain legacy được phép, nhưng cần xác định phạm vi và kiểm thử.

## 9. Phân biệt SNI/ALPN với các chức năng TLS khác

### 9.1 SNI không phải chứng thư, chứng thư không phải SNI

SNI chỉ là **tên khách yêu cầu**. Certificate xác nhận một **public key gắn với các DNS names/IP SAN và được CA ký**. Client phải xác minh path tới trust anchor và name thuộc target.

SNI có thể bị client đổi tùy ý; không nên dùng SNI thay client certificate hoặc JWT/session. Mặt khác, một certificate có thể phục vụ nhiều SNI values (SAN multi-domain/wildcard) nên không nhất thiết một alias/host.

### 9.2 ALPN không phải TLS cipher negotiation

TLS cipher suite xác định cơ chế mã hóa/kỹ thuật bảo vệ TLS records; ALPN chọn **ứng dụng** chạy trên những records ấy. TLS 1.3 và HTTP/2 không cùng tầng. Một server có thể hỗ trợ TLS 1.3 nhưng chỉ ứng dụng HTTP/1.1, hoặc chọn HTTP/2 trên TLS 1.3 nếu có handler và profile phù hợp.

### 9.3 ALPN không phải HTTP URL routing

`ALPN=http/1.1` cho biết byte stream sau handshake tuân theo HTTP/1.1; lựa chọn service cụ thể (`/api/v1`) vẫn dựa vào HTTP routing và authorization. `SNI=blue.example.test` có thể ảnh hưởng virtual host, nhưng không thay thế phân tích HTTP Host/:authority và quyền ứng dụng.

### 9.4 ECH, session resumption và HTTP/2 connection reuse

Khi đánh giá hệ thống thật:

- **ECH** có thể che giấu hostname SNI thực; phải xem deployment và client/server support, không dựa vào SNI ngoài plaintext để quyết định danh tính/chính sách trong mọi môi trường.
- **TLS session resumption/PSK** có các ràng buộc về virtual host và application protocol; không mặc định có một full certificate exchange mới ở mọi kết nối được resumed.
- **HTTP/2** có thể multiplex nhiều request/stream và có những quy tắc coalescing/origin; server phải xử lý authority và chứng thư hợp lệ, không chỉ dựa vào SNI của handshake đầu tiên.
- Với reverse proxy đa tenant, cần kiểm thử sự nhất quán giữa original target, SNI, certificate, ALPN, Host/:authority và upstream destination khi reuse/reconnect.

Đây là các vấn đề **thiết kế giao thức và triển khai**; không thể kết luận chỉ từ một giá trị `SSLSession.getProtocol()` hoặc một log SNI.

## 10. Debug và quan sát trong môi trường Java

Khi một kết nối thành công bằng `curl` nhưng Java bị `SSLHandshakeException`, hãy phân loại:

1. **DNS/peer host:** client có đang nối đúng target? Layered socket có truyền đúng peer hostname để endpoint identification?
2. **SNI:** client có gửi `SNIHostName` hợp lệ? Server có nhận tên đó, chọn đúng key alias/cert không?
3. **Chứng thư:** root/intermediate chain có đúng, truststore chứa trust anchor hợp lệ, leaf SAN khớp hostname, thời hạn/algorithm/key usage phù hợp?
4. **ALPN:** client đề xuất IDs nào? Server hỗ trợ/chọn ID nào? Application handler có thực thi protocol đã chọn?
5. **TLS policy:** có TLS version/cipher suite chung không? Client auth/mTLS có yêu cầu thêm certificate phía client không?
6. **Proxy:** TLS kết thúc ở edge hay backend? Có hai TLS hops khác nhau không?
7. **Runtime:** Java version/provider/key manager có hỗ trợ SNI/ALPN theo cách dự kiến không?

Để debug lab, JSSE có các tùy chọn `javax.net.debug`; ví dụ chỉ bật **trong môi trường test cô lập**:

```text
java -Djavax.net.debug=ssl,handshake -cp . SniAlpnDemo server.p12 trust.p12
```

Log handshake có thể rất dài và chứa metadata nhạy cảm (hostname, certificate chain, thông tin cấu hình), nên **không bật rộng rãi trong production**, không sao chép log có secret sang nơi công khai. Debug chỉ nhằm xác định extension/nhánh handshake, không làm thay đổi trust policy.

Khi cần công cụ bên ngoài trong môi trường mà bạn **được quyền kiểm thử**, có thể dùng `openssl s_client` với `-servername` và `-alpn` để quan sát SNI/ALPN từ một server thật. Trong bài lab, listener là cổng loopback ngẫu nhiên và kết thúc sau hai kết nối, nên không phải một server sống để debug thủ công sau khi chương trình hoàn thành.

## 11. Kiểm thử có hệ thống

| Mục kiểm thử | Mong đợi |
| --- | --- |
| SNI blue với certificate blue | Handshake thành công, SAN và hostname blue hợp lệ |
| SNI green với certificate green | Handshake thành công, SAN và hostname green hợp lệ |
| SNI không tồn tại, không có default policy | Không chọn cert/virtual host sai; handshake từ chối |
| Certificate blue dùng cho target green | Hostname verification từ chối |
| Chứng thư ký bởi CA không nằm truststore | PKIX/trust manager từ chối |
| Client ALPN `demo/1,http/1.1`; server ưu tiên `http/1.1` | Chọn `http/1.1` và chỉ chạy HTTP/1.1 handler nếu thực sự tồn tại |
| Client chỉ có `h2`, server chỉ có `http/1.1` | Từ chối theo chính sách ALPN, không chọn protocol lạ |
| Không có ALPN ở một phía | Giá trị không thương lượng theo API; xử lý theo profile, không suy đoán |
| Thay HTTP Host sang tenant khác | Routing/authorization không tự mở quyền chéo tenant |
| Proxy terminate + re-encrypt | Đúng certificate/trust/SNI/ALPN riêng mỗi hop |
| Mỗi alias reload certificate mới | Chọn đúng chain, hostname, key type sau khi rotate |
| Một ứng dụng báo ALPN `h2` nhưng không implement HTTP/2 | Bị test bắt lỗi; không đưa vào production |
| Client dùng IP SAN thay DNS SAN | Kiểm đúng identity policy và case không có DNS SNI |
| KeyManager chỉ xử lý `SSLSocket` nhưng app dùng `SSLEngine` | Phải có `chooseEngineServerAlias` hoặc cấu hình framework đúng |

### 11.1 Bài tập

1. **Vẽ đường đi:** một HTTPS client kết nối `blue.example.test` trên IP chung với green. Tại thời điểm nào SNI được gửi, certificate nào phải được chọn và tại sao HTTP Host không thể dùng để chọn certificate ở đầu handshake?
2. **Nhận diện API:** trong `SniAlpnDemo`, xác định method cấu hình SNI client, method đọc SNI server khi chọn key, method chọn ALPN và method lấy giá trị ALPN cuối cùng.
3. **Thay thứ tự ALPN:** đảo danh sách server từ `["http/1.1","demo/1"]` thành `["demo/1","http/1.1"]` và xem provider chọn gì. Sau đó giải thích vì sao chỉ đổi label không có nghĩa ứng dụng đã hỗ trợ giao thức mới.
4. **SNI không nhận dạng:** nghĩ cách sửa `aliasFor` để xử lý hostname chưa cấu hình. Vì sao chọn default alias theo tên gần giống có thể gây vấn đề tenant isolation?
5. **Endpoint identity:** bỏ `setEndpointIdentificationAlgorithm("HTTPS")` và trả lời rủi ro bảo mật (không khuyến nghị bỏ trong code production). Phân biệt CA chain được tin và tên server đúng target.
6. **Một certificate nhiều SAN:** giả sử blue và green dùng chung một certificate có cả hai SAN; SNI còn có giá trị gì cho routing và policy?
7. **HTTP/2:** nếu client gửi `ALPN=h2`, server phải có thêm các thành phần ứng dụng nào? Nếu server chỉ có HTTP/1.1 handler, kết quả an toàn cần là gì?
8. **Hai TLS hops:** edge chọn cert theo SNI bên ngoài rồi kết nối backend TLS; hãy xác định backend SNI/ALPN, cách xác thực backend và vai trò HTTP Host/:authority.
9. **Quan sát:** trên môi trường test, bật JSSE handshake debug và tìm ClientHello SNI, danh sách ALPN, certificate đã chọn; tránh chia sẻ dữ liệu nhạy cảm trong log.
10. **Privacy:** vì sao TLS 1.3 mã hóa dữ liệu ứng dụng vẫn không nhất thiết giấu được tên SNI? ECH thay đổi điều kiện nào?
11. **Phân quyền:** một request tới hostname `admin.example.test` dùng chứng thư hợp lệ và HTTP/2. Vì sao user vẫn cần authentication và authorization?
12. **Provider portability:** giải thích vì sao `KeyManagerFactory.getInstance("SunX509")` và mapping alias của ví dụ cần kiểm tra nếu chuyển sang một provider khác hoặc HSM.

**Tiêu chí hoàn thành:** bạn có thể tự trả lời ba câu hỏi cho một kết nối HTTPS đa domain: **(1) SNI nào được gửi và certificate/vhost nào được chọn? (2) Client đã kiểm trust anchor + hostname của certificate chưa? (3) ALPN chọn ứng dụng nào và phía server/client có handler thực sự cho ứng dụng ấy không?** Nếu thiếu bất kỳ lớp nào, TLS có thể thành công một phần nhưng chức năng định tuyến hoặc bảo mật ứng dụng vẫn sai.

## 12. Tài liệu chính thức để đối chiếu

- [Java SE 21 – `SSLParameters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setServerNames`, `setApplicationProtocols`, `setSNIMatchers` và `setEndpointIdentificationAlgorithm`.
- [Java SE 21 – `SNIHostName`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SNIHostName.html) và [`SNIServerName`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SNIServerName.html): cấu trúc tên server trong TLS.
- [Java SE 21 – `ExtendedSSLSession`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/ExtendedSSLSession.html): `getRequestedServerNames` và handshake/session metadata.
- [Java SE 21 – `X509ExtendedKeyManager`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/X509ExtendedKeyManager.html): `chooseServerAlias`, `chooseEngineServerAlias`, certificate chain/private key.
- [Java SE 21 – `SSLSocket`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLSocket.html): `getApplicationProtocol`, `getHandshakeApplicationProtocol`, protocol selector, `getHandshakeSession` và handshake behavior.
- [Java SE 21 – `SSLServerSocket`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLServerSocket.html) và [`SSLEngine`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngine.html): TLS server listener và engine non-blocking.
- [Java SE 21 – JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TLS configuration, ALPN, SNI, key/trust managers và debug.
- [RFC 6066](https://www.rfc-editor.org/rfc/rfc6066): TLS Extension Definitions, `server_name` (SNI).
- [RFC 7301](https://www.rfc-editor.org/rfc/rfc7301): ALPN extension, giao thức chọn và alert `no_application_protocol`.
- [RFC 8446](https://www.rfc-editor.org/rfc/rfc8446): TLS 1.3 ClientHello, EncryptedExtensions, certificate và session semantics.
- [RFC 9113](https://www.rfc-editor.org/rfc/rfc9113): HTTP/2 và HTTP/2 over TLS, ALPN `h2`.
