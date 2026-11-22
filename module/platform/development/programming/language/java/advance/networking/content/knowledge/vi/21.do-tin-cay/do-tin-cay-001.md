# Phân loại lỗi DNS, bind, connect, route, read, TLS và lỗi giao thức trong Java Networking

## Mục tiêu

Một lỗi “không gọi được API” có thể xảy ra **trước khi có TCP connection**, **khi thiết lập TCP**, **sau khi TCP đã kết nối**, **trong TLS handshake**, **khi chờ dữ liệu**, hoặc **sau khi đã nhận một HTTP response hợp lệ**. Tất cả đôi khi đều bị viết vào log thành một câu mơ hồ như “network error”, dẫn tới cách khắc phục sai: thử lại liên tục dù máy đang bind trùng port, thay DNS dù server từ chối kết nối, hoặc tăng read timeout khi chứng chỉ TLS không hợp lệ.

Bài học thuộc ngữ cảnh **Độ tin cậy** của Java Networking, có một nhiệm vụ trọng tâm: **phân loại lỗi theo giai đoạn và bằng chứng**, không chỉ theo câu chữ của exception message. Các giai đoạn cần phân biệt:

1. **DNS / phân giải tên** — xác định địa chỉ IP từ hostname.
2. **Bind / chiếm địa chỉ cục bộ** — chọn local IP/port cho listener hoặc socket.
3. **Connect / thiết lập kết nối** — tới remote IP/port và gặp refused/timeout.
4. **Route / đường đi mạng** — local route, gateway, firewall, khả năng reachability.
5. **Read / nhận dữ liệu** — timeout, EOF, reset, dữ liệu bị cắt khi stream đang hoạt động.
6. **TLS / xác thực và thương lượng kênh bảo mật** — trust chain, hostname, certificate, protocol/cipher.
7. **Protocol / nội dung giao thức ứng dụng** — HTTP framing/status/method/header, WebSocket upgrade, payload contract và sai định dạng.

Bạn sẽ học cách đọc **`UnknownHostException`, `BindException`, `ConnectException`, `NoRouteToHostException`, `SocketTimeoutException`, `SSLHandshakeException`, `ProtocolException`, `EOFException`, `HttpConnectTimeoutException`, `HttpTimeoutException`** đúng hoàn cảnh. Có bốn chương trình Java 17+ độc lập: (1) bộ phân loại exception, (2) kiểm thử bind/connect/read bằng loopback, (3) HTTP `503` hợp lệ đối chiếu lỗi `ProtocolException` tại API, (4) kết nối TLS tới một listener chỉ nói HTTP plaintext. Kết quả thực hành đã được biên dịch bằng `javac --release 17` và chạy trên loopback.

**Nguyên tắc cốt lõi:** class exception là **bằng chứng**, không phải lời giải thích duy nhất. Một nguyên nhân có thể tạo nhiều exception tùy OS/JDK/proxy và thời điểm, còn một exception như `SocketTimeoutException` có thể chỉ cả connect lẫn read. Luôn kết hợp **callsite + giai đoạn + nguyên nhân gốc + log server + network context**.

## 1. Bản đồ luồng kết nối: lỗi có thể nằm ở đâu?

Với một client Java gọi HTTPS API, mô hình đơn giản:

```text
URI: https://api.example.test/orders
  │
  ▼
[1] Parse URI / validate cấu hình, proxy và hostname
  │       lỗi syntax/config → IllegalArgumentException, URISyntaxException...
  ▼
[2] DNS / name lookup (origin hoặc proxy hostname tùy cấu hình)
  │       UnknownHostException / lỗi resolver / timeout resolver
  ▼
[3] Bind local socket, chọn local IP và ephemeral port
  │       BindException / SocketException
  ▼
[4] Route + TCP connect tới remote endpoint/proxy
  │       NoRouteToHostException, ConnectException,
  │       SocketTimeoutException / HttpConnectTimeoutException...
  ▼
[5] TLS handshake nếu HTTPS (hoặc sau CONNECT proxy tunnel)
  │       SSLHandshakeException / SSLProtocolException / SSLException;
  │       một số lần mất kết nối vẫn biểu hiện bằng SocketException
  ▼
[6] Gửi HTTP request headers/body
  │       IOException, Broken pipe, Connection reset, timeout...
  ▼
[7] Đọc HTTP response status/headers/body
  │       SocketTimeoutException, premature EOF, malformed protocol;
  │       hoặc HTTP response HỢP LỆ với status 401/404/429/503
  ▼
[8] Validate content và business outcome
          JSON schema error, validation 422, authorization,
          idempotency, server commit/retry ambiguity...
```

Đây là **sơ đồ logic**, không phải cam kết rằng mọi HTTP client thực hiện các bước thành từng hàm riêng biệt. Ví dụ một HTTP client có connection pool **có thể bỏ qua DNS/bind/connect/TLS** ở lần request kế tiếp khi tái sử dụng connection phù hợp. Proxy DNS, HTTP/2 connection reuse và TLS session resumption cũng có thể làm thứ tự quan sát phức tạp hơn.

### Tại sao không chỉ xem dòng cuối stack trace?

`java.net.SocketTimeoutException: Read timed out` nghe giống một lỗi “network chung”, nhưng chỉ dẫn rõ **lệnh đọc đã chờ quá hạn**; chưa đủ biết server có nhận request chưa. Còn `ConnectException: Connection refused` cho thấy thiết lập TCP bị từ chối ở một endpoint, **không nói** DNS đã lỗi. Nếu stack trace bị bọc bởi `ExecutionException`/`CompletionException`, class thực cần xem là **cause bên trong**.

**Một điều quan trọng:** Không phân loại bằng cách tìm substring `"refused"`, `"unreachable"`, `"timed out"` trong `getMessage()` trước khi xét exception type/callsite. Messages phụ thuộc hệ điều hành, ngôn ngữ và triển khai. Dùng `instanceof`, giữ cause chain và bổ sung phase đã được instrument.

## 2. Bảng phân loại nhanh Java 17

| Giai đoạn | Exception/dấu hiệu thường gặp | Có thể có nghĩa | Kiểm tra đầu tiên |
|---|---|---|---|
| DNS | `UnknownHostException` | Không xác định được IP của hostname qua resolver đang dùng | Hostname, DNS resolver, hosts file, proxy lookup |
| Bind | `BindException` | Không bind được local IP/port, thường do port bị chiếm hoặc address không sẵn có | Local IP/port, listener khác, quyền bind |
| Connect | `ConnectException` | Kết nối TCP thất bại, thường là connection refused | Remote host/port và listener, firewall policy |
| Route | `NoRouteToHostException` | Host/network không đến được; route/firewall/ICMP có thể liên quan | Route table, gateway, security groups, VPN |
| Connect-timeout (raw Socket) | `SocketTimeoutException` từ `Socket.connect(addr, timeout)` | Quá hạn chờ connect | Callsite `connect`, SYN/SYN-ACK và network path |
| Read-timeout (raw Socket) | `SocketTimeoutException` từ `InputStream.read()` khi `setSoTimeout` | Chờ dữ liệu quá hạn | Server progress, response framing, SO_TIMEOUT |
| TLS handshake | `SSLHandshakeException` | Client/server không thương lượng/xác minh TLS được | Chain/CA, hostname, protocol, SNI, mTLS, clock |
| TLS khác | `SSLProtocolException` hoặc `SSLException` | Lỗi TLS record/protocol/layer, không nhất thiết chỉ là cert | TLS version, plaintext vs TLS, peer close, logs |
| HTTP connect-timeout | `HttpConnectTimeoutException` | `java.net.http.HttpClient` không thiết lập được connection trong deadline | `connectTimeout`, endpoint và route |
| HTTP request-timeout | `HttpTimeoutException` | Deadline HTTP request hết trước response theo contract | `HttpRequest.timeout`, server/proxy latency |
| HTTP API/protocol | `ProtocolException` hoặc `IOException` khi parse | Vi phạm protocol/config hoặc implementation từ chối | Request method, response syntax, framing, wire trace |
| Read/body không hoàn chỉnh | `EOFException` hoặc `IOException` | Stream kết thúc sớm so với số bytes cần | `Content-Length`/chunked, peer close, proxy |
| HTTP status hợp lệ | `404`, `429`, `503` ... | Server/proxy đã trả HTTP response; **không nhất thiết network error** | `statusCode/getResponseCode`, `Retry-After`, body |
| Business/application | JSON decode, validation, authorization | TCP/TLS/HTTP có thể đều hoạt động tốt | Schema, method, auth, contract, error response |

**Không có một ánh xạ 1:1 vĩnh viễn** từ exception type sang thiết bị hỏng. `NoRouteToHostException` có thể xuất hiện do firewall hoặc route, nhưng firewall cũng có thể **drop** khiến connect timeout hay **reject** tạo refused/ICMP; đôi khi Java chỉ nhận một `SocketException` tổng quát. Bảng này dùng để **định vị nơi kiểm tra trước**, không đưa ra root cause chắc chắn.

## 3. DNS: `UnknownHostException` và lỗi phân giải tên

DNS/ngữ cảnh name resolution chuyển `api.example.test` thành một hay nhiều địa chỉ IPv4/IPv6. Khi Java không xác định được địa chỉ, các API như `InetAddress.getByName(host)` có thể ném `UnknownHostException`.

```java
// Đoạn minh họa, KHÔNG phải chương trình độc lập.
try {
    InetAddress address = InetAddress.getByName(host);
    useAddress(address);
} catch (UnknownHostException resolutionFailed) {
    reportDnsOrNameResolutionFailure(host, resolutionFailed);
}
```

Trong đó `host`, `useAddress` và `reportDnsOrNameResolutionFailure` phải do ứng dụng cung cấp. Đừng chạy ví dụ với tên miền bất kỳ để “thử DNS lỗi” trên mạng công cộng.

### Không kết luận quá mức

`UnknownHostException` nghĩa IP của hostname **không được xác định**, không chứng minh “DNS server thế giới đã down”. Có thể là:

- Gõ sai hostname, thiếu suffix domain, IDN/punycode, tên miền hết hiệu lực.
- File hosts hoặc search domain khác môi trường kỳ vọng.
- DNS resolver/VPN nội bộ không truy cập được, network policy hoặc split-horizon DNS.
- Record A/AAAA không sẵn có, IPv4/IPv6 policy khác nhau.
- DNS cache đã lưu negative result (NXDOMAIN hoặc không có address) trong một khoảng thời gian.
- Client dùng proxy; tên thực sự được phân giải ở **proxy** hoặc **client** tùy kiểu proxy và phương thức gọi.

### Công cụ đối chiếu

Trên host được phép chẩn đoán, so sánh:

```text
hostname input (chính xác, không kèm scheme)
→ resolver được JVM/OS sử dụng
→ A/AAAA records
→ DNS search domain/split DNS
→ IP thực tế client cố connect
```

Trong Windows có thể dùng `Resolve-DnsName`/`nslookup`, Linux có `getent hosts`, `dig` hoặc `resolvectl` tùy distro. Nhưng **kết quả của một công cụ dòng lệnh không nhất thiết giống cache/proxy/runtime của JVM**. Khi debug, ghi địa chỉ đã chọn của request thực tế, không chỉ `ping hostname`.

**Lưu ý bảo mật:** Không khuyến nghị sửa `/etc/hosts`/DNS máy production theo phỏng đoán; thay đổi name resolution có thể chuyển request tới server sai, gây lộ dữ liệu. Kiểm tra trust boundaries, certificates và service discovery.

## 4. Bind: `BindException` là lỗi ở địa chỉ cục bộ

Server thường mở listener:

```java
// Đoạn minh họa, không phải class hoàn chỉnh.
try (ServerSocket server = new ServerSocket()) {
    server.bind(new InetSocketAddress("127.0.0.1", 8080));
    // accept() ở phần triển khai thực tế.
}
```

`BindException` xảy ra khi socket **không gắn được local address/port**. Các nguyên nhân có thể gồm:

- Port 8080 đã bị process khác chiếm và không có cơ chế sharing hợp lệ.
- Cố bind vào local IP không tồn tại trên interface hiện tại.
- Chính sách OS/permission/port reservation hoặc trạng thái kernel ngăn bind.
- Socket binding options, dual-stack IPv6/IPv4 và `SO_REUSEADDR` tương tác khác nhau theo OS.

**Nó không tương đương server từ xa từ chối kết nối.** Lỗi bind xuất hiện tại máy **đang bind local socket**; nếu server không lên listener, client khác có thể nhìn thấy `ConnectException` hoặc timeout khi connect vào port đó.

### Khác `ConnectException` ở đâu?

- `BindException`: local code không thể **sở hữu local endpoint**.
- `ConnectException`: client không thiết lập được TCP connection đến endpoint đã chọn; listener remote không chấp nhận hoặc network từ chối.

Nếu một server fail start vì `BindException`, cần kiểm tra process đang listen, local IP và port, không vội sửa DNS của client. Nếu client chủ động `Socket.bind(localAddress)` trước `connect` thì cũng có thể gặp BindException **tại máy client**.

### Phép thử bind cục bộ

Tạo `ServerSocket A` bind vào `127.0.0.1:0`; OS cấp một port trống. Giữ A mở, tạo `ServerSocket B` bind **chính cùng địa chỉ/port**. Trong cấu hình mặc định của thử nghiệm bên dưới, B ném `BindException`. Đây là một cách kiểm thử an toàn trên loopback, không cần chiếm port dịch vụ đang chạy.

**Không dùng demo để cạnh tranh với port đang phục vụ traffic thật.** Thử nghiệm chỉ dùng port động do chính chương trình tạo, đóng trong `try-with-resources`.

## 5. TCP connect: `ConnectException` và từ chối kết nối

Sau khi có IP, TCP client gọi:

```java
// Đoạn minh họa, chưa có main/giá trị remote cụ thể.
try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress(remoteAddress, remotePort), 3000);
    // Kết nối thành công; sau đó mới gửi/đọc dữ liệu.
}
```

**`ConnectException`** thường mô tả connect failure, đáng chú ý nhất là **connection refused**. Các khả năng cần kiểm tra:

1. Đúng host nhưng **sai port**, không có process đang listen.
2. Service chưa start/crash, chạy ở một container nhưng port chưa được publish.
3. Service chỉ bind `127.0.0.1`, client từ máy khác cố tới public IP.
4. Firewall/security policy **reject** kết nối thay vì drop.
5. Reverse proxy/load balancer chưa nhận request trên port/scheme tương ứng.
6. Endpoint đã đóng connection backlog hoặc limit theo cách tạo lỗi có vẻ tương tự, phụ thuộc OS.

**Connection refused** thường là dấu hiệu tích cực rằng **một câu trả lời từ network stack** đã tới, nhưng không xác định chính xác đó là service chủ đích, firewall hay proxy nào. `ConnectException` không tự chứng minh server application đang chạy hoặc hoàn toàn tắt.

### Connection refused khác connect timeout

```text
Client ─ TCP SYN ─► destination
            ├─ RST/reject phản hồi nhanh → thường ConnectException
            ├─ route bị báo unreachable → có thể NoRouteToHostException
            └─ không nhận phản hồi đủ deadline → connect timeout
```

Mô hình này là giải thích thường gặp, **không áp đặt mapping tuyệt đối** từ packet sang một Java exception duy nhất. SYN retries, policy network, proxy và OS sẽ quyết định.

### Khi nào có thể retry?

Nếu không có TCP connection nào được thiết lập, request **qua connection đó** thường chưa được gửi. Nhưng ở tầng ứng dụng có thể có proxy, retry tự động, nhiều endpoints hoặc requests trước đó đã xử lý. Với workflow có side effect, không lấy riêng một `ConnectException` ra khỏi context để cam kết “chắc chắn chưa có giao dịch”. Cần xem attempt ID, connection ID, body bytes và server logs.

## 6. Route: `NoRouteToHostException` không phải DNS

Sau khi có địa chỉ IP, hệ điều hành cần quyết định **đường đến đích**: interface, gateway, VPN, network namespace, firewall và các route policies. Khi không thể đến endpoint, Java có thể ném `NoRouteToHostException` (một subtype của `SocketException`).

**Khác biệt quan trọng:**

- DNS thành công nhưng **route thất bại** vẫn có thể xảy ra: IP đã biết, nhưng không có đường đi/chặng trung gian không reachable.
- Host có route nhưng **port không listen** thường biểu hiện connect refused.
- Firewall **drop** packets có thể dẫn tới timeout thay vì `NoRouteToHostException`.
- NAT/proxy/VPN cấu hình sai có thể biểu hiện thành nhiều dạng `IOException` khác nhau.

### Câu hỏi điều tra đúng

- Đích là IPv4 hay IPv6? Máy có route tương ứng?
- Truy cập qua VPN hoặc container/VM network namespace nào?
- Security group/firewall chặn theo **source IP**, **destination port** hay protocol?
- Địa chỉ server được DNS trả có reachable từ **nơi chạy JVM** hay chỉ từ laptop người phát triển?
- Nếu đi qua HTTP proxy, chính client nối tới **proxy endpoint** hay tới origin? Lỗi route có thể là route tới proxy.
- Có sự khác biệt giữa gateway default, subnet route hoặc pod/container network?
- Có thiết bị mạng trả ICMP unreachable không hay im lặng drop?

**Không test bằng cách quét toàn mạng ngoài quyền hạn.** Có thể dùng `route print`/`Get-NetRoute` trên Windows, hoặc `ip route`/`ip -6 route` trên Linux và log mạng được phép. `ping` không phải phép kiểm “TCP port 443 reachable” vì ICMP thường bị hạn chế.

## 7. Read: `SocketTimeoutException`, EOF và reset

Giả sử TCP connect thành công, client gửi request, nhưng chưa đọc đủ response. Đây là **giai đoạn đọc**, không còn là giai đoạn connect. Trên `Socket` thường dùng:

```java
// Đoạn minh họa, không phải full runnable program.
socket.setSoTimeout(1500); // Timeout cho thao tác đọc.
int next = socket.getInputStream().read();
// Có thể trả một byte 0..255, -1 khi EOF, hoặc ném exception.
```

Nếu 1,5 giây trôi qua **khi đọc chưa nhận dữ liệu cần thiết**, `read()` có thể ném `SocketTimeoutException`. Điều này không chứng minh server down: server có thể đang xử lý, chờ database, ghi chậm, hoặc đang đợi thêm request body vì client gửi thiếu `Content-Length`.

### Phân biệt ba trường hợp

| Dấu hiệu | Ý nghĩa trực tiếp | Việc cần xét |
|---|---|---|
| `SocketTimeoutException` từ `InputStream.read` | Không đọc được dữ liệu trước SO_TIMEOUT | Deadline, server progress, framing, transport |
| `read() == -1` | EOF: peer đóng chiều gửi sau bytes đã đọc hết | Protocol có mong EOF? Đã đủ body chưa? |
| `EOFException` khi code đòi đúng N bytes | Stream kết thúc trước số bytes mà parser cần | Body bị cắt, peer close, protocol framing |
| `SocketException: Connection reset` hoặc lỗi I/O khác | Transport báo reset/broken connection | Peer/proxy close, half-open, NAT, race |
| `read` trả số dương nhỏ hơn buffer | Một phần bytes có sẵn | **Không** có nghĩa message đã kết thúc |

**TCP là byte stream**, không mang sẵn ranh giới HTTP message. Một lần `read` có thể nhận ít bytes hơn yêu cầu mà không phải lỗi. Trên persistent HTTP/1.1 connection, gọi `readAllBytes()` trực tiếp trên **raw Socket InputStream** có thể chờ TCP EOF mãi trong khi HTTP response đã hoàn thành theo `Content-Length`.

### So sánh `setSoTimeout` và deadline HTTP

`Socket.setSoTimeout(ms)` áp dụng cho thao tác đọc trên socket đó. Nó khác `Socket.connect(endpoint, timeout)`, nơi cùng subtype `SocketTimeoutException` có thể báo **connect timeout**. Cùng class exception, **callsite khác thì phase khác**.

`HttpURLConnection.setReadTimeout(ms)` cũng dùng timeout cho thao tác đọc, trong khi `HttpRequest.Builder.timeout(Duration)` của `java.net.http.HttpClient` quản lý timeout của **HTTP request**, có thể ném `HttpTimeoutException`. Không ghi một metric chung `timeout=true` rồi bỏ mất phase.

### Đóng connection sau partial response

Nếu server đã báo `Content-Length: 100` nhưng client chỉ nhận 60 bytes và peer đóng, HTTP message **không hoàn chỉnh**. Không biến 60 bytes đó thành response thành công. Với `Transfer-Encoding: chunked`, phải đọc tới zero-sized chunk và trailers; EOF trước ranh giới hợp lệ cũng là lỗi.

Một response `204 No Content` hoặc cho `HEAD` lại **không có HTTP message body** theo quy tắc, nên sau headers không có gì để đợi. Muốn phân loại read failure chính xác cần biết **message framing** trước tiên.

## 8. TLS: `SSLHandshakeException`, `SSLProtocolException`, `SSLException`

Với `https://`/`wss://`, sau TCP connect client và server còn phải **thương lượng TLS**. Những lỗi thường gặp:

- **Chứng chỉ không được trust:** chain CA thiếu, truststore JVM thiếu root/intermediate, certificate tự ký không được cấp phép.
- **Hostname verification thất bại:** chứng chỉ không khớp DNS name/SAN của endpoint.
- **Certificate expired/not-yet-valid:** đồng hồ máy khách sai hoặc certificate hết hạn.
- **Protocol/cipher mismatch:** không có version/cipher suite phù hợp, server dùng TLS cũ không còn được cho phép.
- **mTLS:** server yêu cầu client certificate mà client không gửi hoặc gửi sai.
- **SNI/virtual host:** server chọn certificate/context không đúng hostname.
- **Sai scheme/port:** client cố TLS tới port chỉ nói HTTP plaintext, hoặc plain HTTP tới TLS-only port.
- **Proxy/TLS inspection:** một hop trung gian thay certificate/đóng kết nối gây lỗi trust/handshake.

### Phân loại exception

| Java exception | Cách hiểu |
|---|---|
| `SSLHandshakeException` | Client/server **không đàm phán mức bảo mật mong muốn**; TLS connection không sử dụng được |
| `SSLProtocolException` | Lỗi trong hoạt động của TLS protocol |
| `SSLException` | Nhóm lỗi TLS tổng quát; có thể bao gồm các subtype trên |
| `SSLPeerUnverifiedException` | Danh tính peer chưa được xác minh trong ngữ cảnh API tương ứng |
| `SocketException`/`EOFException` khi đang handshake | Peer/network đóng sớm; **không nhất thiết được bọc thành SSLHandshakeException** |

**Điều quan trọng:** nếu Java trả `SSLHandshakeException`, TCP **có thể đã kết nối** thành công. Sửa DNS hay tăng connect timeout thường không giải quyết lỗi certificate. Ngược lại, nếu TCP bị reset trước khi TLS handshake có đủ dữ liệu, runtime có thể chỉ ném `SocketException`, dù người phát triển thấy nó ở `startHandshake()`.

### Không “sửa” bằng cách tắt kiểm tra TLS

Không đặt TrustManager chấp nhận tất cả certificates, không vô hiệu hostname verification, không tự chuyển HTTPS thành HTTP để hết exception. Những thủ thuật đó che root cause và làm lộ credentials/content. Sửa certificate chain/SAN, truststore, đồng hồ, TLS configuration hoặc endpoint scheme đúng.

### Quan sát lớp nào đang dùng TLS?

`javax.net.ssl.SSLSocket` có `startHandshake()` và `SSLContext`, nhưng **Java `HttpClient` hoặc `HttpsURLConnection` thường tự quản lý TLS**. Một ứng dụng HTTPS có thể thấy `SSLHandshakeException` qua `IOException` bọc trong `ExecutionException`/`CompletionException`; cần đọc cause chain. Nếu kết nối đi qua proxy HTTP CONNECT, TLS bắt đầu **sau tunnel**, nên `407 Proxy Authentication Required` xảy ra ở tầng HTTP proxy, chưa phải cert failure.

## 9. Lỗi giao thức: không được gom HTTP 4xx/5xx vào “network failure”

Phân loại một response HTTP phải tách:

1. **Không nhận được response hợp lệ**: transport/TLS hoặc HTTP parser/framing lỗi.
2. **Nhận được HTTP response hợp lệ nhưng status báo lỗi**: `400`, `401`, `403`, `404`, `409`, `429`, `503` ...
3. **HTTP thành công về transport/status nhưng payload không đúng contract**: body JSON sai schema, invalid application envelope, thiếu trường bắt buộc.
4. **Kết quả nghiệp vụ chưa xác định**: timeout/cancel xảy ra sau khi server có thể đã xử lý side effect.

### HTTP `503` không phải lỗi DNS/connect/read

Ví dụ server đã trả:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: text/plain
Content-Length: 10

BACK_LATER
```

Client nhận được **một response HTTP hợp lệ**. `503` báo dịch vụ tạm không xử lý yêu cầu theo semantics HTTP, nhưng các lớp DNS/TCP/TLS/HTTP framing có thể vẫn hoạt động đầy đủ. Không biến status 503 thành `ConnectException` hoặc `UnknownHostException` chỉ vì ứng dụng xem nó là thất bại.

- Với `java.net.http.HttpClient.send(...)`, API có thể trả `HttpResponse` có `statusCode()==503` bình thường.
- Với `HttpURLConnection`, `getResponseCode()` trả `503`; `getInputStream()` có thể ném `IOException` cho HTTP error status, và `getErrorStream()` cho phép đọc error body nếu có.
- HTTP `429` có thể cung cấp `Retry-After`; quyết định retry phải theo status, header, method và idempotency.
- HTTP `401`/`407` là authentication challenge ở origin/proxy; không mặc định coi chúng là TLS handshake failure.
- HTTP `408` hoặc `504` là HTTP statuses từ server/proxy, **không đồng nghĩa** Java `SocketTimeoutException` hoặc `HttpTimeoutException`.

### `ProtocolException` cũng cần ngữ cảnh

`java.net.ProtocolException` là một `IOException` dùng cho lỗi liên quan protocol. Có thể gặp nó **ngay ở client API validation**, ví dụ `HttpURLConnection.setRequestMethod("INVALID_METHOD")`, trước cả khi mạng được gọi. Một HTTP response bị lỗi framing như `Content-Length` xung đột có thể ném `IOException` hoặc subtype khác tùy implementation; **không có bảo đảm mọi HTTP syntax error đều xuất hiện dưới dạng `ProtocolException`**.

Bởi vậy category `PROTOCOL_API` trong chương trình phân loại phía dưới là **điểm khởi đầu**; phải đối chiếu callsite và bytes/protocol state để biết nguyên nhân cụ thể.

## 10. Bảng so sánh timeout theo API

| API Java 17 | Lớp timeout được đo | Ngoại lệ thường thấy | Tác động |
|---|---|---|---|
| `Socket.connect(address, timeoutMillis)` | Thiết lập TCP connect | `SocketTimeoutException` | Connect chưa hoàn tất trong deadline |
| `Socket.setSoTimeout(ms)` + `InputStream.read()` | Một thao tác **read** | `SocketTimeoutException` | Read chờ quá hạn; socket không tự phải đóng theo contract |
| `ServerSocket.setSoTimeout(ms)` + `accept()` | Chờ inbound connection | `SocketTimeoutException` | Không có incoming accepted socket trong thời hạn |
| `HttpURLConnection.setConnectTimeout(ms)` | Connect | `SocketTimeoutException` hoặc `IOException` liên quan | Không phải deadline toàn request |
| `HttpURLConnection.setReadTimeout(ms)` | Read | `SocketTimeoutException` | Không phải tổng deadline cả redirect chain |
| `HttpClient.Builder.connectTimeout(Duration)` | HTTP client connection establishment | `HttpConnectTimeoutException` | Subclass của `HttpTimeoutException` |
| `HttpRequest.Builder.timeout(Duration)` | HTTP request deadline | `HttpTimeoutException` | Không tự chứng minh server rollback |
| `Future.get(timeout, unit)` trên `sendAsync` | Thời gian **thread chờ Future** | `java.util.concurrent.TimeoutException` | Không tự cancel HTTP exchange |
| `CompletableFuture.orTimeout(timeout, unit)` | Trạng thái của Future được gọi | `TimeoutException` làm cause exceptional | Không tự chứng minh network đã dừng |

**Thứ tự `instanceof` rất quan trọng:** `HttpConnectTimeoutException extends HttpTimeoutException`. Nếu classifier kiểm tra `HttpTimeoutException` trước, mọi connect timeout của `HttpClient` sẽ bị gộp nhầm thành `HTTP_REQUEST_TIMEOUT` chung.

**Không phân loại hai loại `TimeoutException` bằng tên ngắn duy nhất.** `java.util.concurrent.TimeoutException` của `Future.get` không phải `java.net.SocketTimeoutException` và cũng không phải `java.net.http.HttpTimeoutException`.

## 11. Java 17+: bộ phân loại exception có xét wrapper và kế thừa

Chương trình đầu tiên xây một classifier có tính **minh họa**: nhận một `Throwable` (kể cả lỗi bọc trong `CompletionException`/`ExecutionException`) và trả về category dựa trên class. Các exception truyền vào đây **được khởi tạo nhân tạo** để kiểm tra mapping deterministic; chương trình **không** giả vờ đã tạo lỗi DNS/route/TLS thật trên Internet.

**Tệp `FailureClassifierDemo.java`:**

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.*;
import java.net.http.*;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import javax.net.ssl.*;

public class FailureClassifierDemo {
    static Throwable unwrap(Throwable error) {
        Throwable current = error;
        for (int i = 0; i < 8; i++) {
            if ((current instanceof CompletionException
                    || current instanceof ExecutionException)
                    && current.getCause() != null) {
                current = current.getCause();
            } else {
                break;
            }
        }
        return current;
    }

    static String phase(Throwable error) {
        Throwable e = unwrap(error);
        if (e instanceof HttpConnectTimeoutException) return "CONNECT_TIMEOUT";
        if (e instanceof HttpTimeoutException) return "HTTP_REQUEST_TIMEOUT";
        if (e instanceof UnknownHostException) return "DNS_OR_NAME";
        if (e instanceof BindException) return "LOCAL_BIND";
        if (e instanceof NoRouteToHostException) return "ROUTE";
        if (e instanceof ConnectException) return "TCP_CONNECT";
        if (e instanceof SocketTimeoutException) return "SOCKET_TIMEOUT_CHECK_CALLSITE";
        if (e instanceof SSLHandshakeException) return "TLS_HANDSHAKE";
        if (e instanceof SSLException) return "TLS_OTHER";
        if (e instanceof ProtocolException) return "PROTOCOL_API";
        if (e instanceof EOFException) return "PREMATURE_EOF";
        if (e instanceof IOException) return "OTHER_IO";
        return "OTHER";
    }

    public static void main(String[] args) {
        IOException[] errors = {
            new UnknownHostException("test"),
            new BindException("test"),
            new ConnectException("test"),
            new NoRouteToHostException("test"),
            new SocketTimeoutException("test"),
            new SSLHandshakeException("test"),
            new SSLException("test"),
            new ProtocolException("test"),
            new EOFException("test"),
            new HttpConnectTimeoutException("test"),
            new HttpTimeoutException("test")
        };
        for (IOException error : errors) {
            System.out.println(error.getClass().getSimpleName()
                    + " -> " + phase(error));
        }
        Throwable wrapped = new CompletionException(
                new ConnectException("test"));
        System.out.println("CompletionException -> " + phase(wrapped));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac --release 17 -encoding UTF-8 FailureClassifierDemo.java
java FailureClassifierDemo
```

**Stdout đã biên dịch/chạy kiểm chứng:**

```text
UnknownHostException -> DNS_OR_NAME
BindException -> LOCAL_BIND
ConnectException -> TCP_CONNECT
NoRouteToHostException -> ROUTE
SocketTimeoutException -> SOCKET_TIMEOUT_CHECK_CALLSITE
SSLHandshakeException -> TLS_HANDSHAKE
SSLException -> TLS_OTHER
ProtocolException -> PROTOCOL_API
EOFException -> PREMATURE_EOF
HttpConnectTimeoutException -> CONNECT_TIMEOUT
HttpTimeoutException -> HTTP_REQUEST_TIMEOUT
CompletionException -> TCP_CONNECT
```

**Phân tích đúng giới hạn classifier:**

- `unwrap` chỉ đi qua hai loại wrappers concurrency cụ thể và giới hạn 8 tầng; **không** tự lột mọi `getCause()` vì có trường hợp lớp exception ngoài chứa thông tin quan trọng (ví dụ TLS/HTTP layer) mà application muốn giữ.
- `HttpConnectTimeoutException` được kiểm tra **trước** `HttpTimeoutException` để không mất phân loại connect phase.
- `NoRouteToHostException` được tách riêng **trước** mọi nhánh `SocketException` tổng quát (đoạn mã không thêm branch SocketException tổng quát).
- `SSLHandshakeException` được kiểm tra **trước** `SSLException` vì nó là subclass.
- `SocketTimeoutException` được trả `SOCKET_TIMEOUT_CHECK_CALLSITE`, **không** ép thành READ: `Socket.connect` và `InputStream.read` đều có thể dùng class này.
- `ProtocolException` được trả `PROTOCOL_API` nhưng vẫn cần xem callsite; malformed HTTP có thể là IOException khác.
- Một `EOFException` chỉ là **dữ liệu đọc kết thúc trước điều kiện mong đợi của parser**. Trong giao thức close-delimited, EOF còn có thể là kết thúc hợp lệ; không đánh dấu mọi EOF thành lỗi.
- Trong production, trả một cấu trúc kết quả có **phase, category, root cause, retryability và operation ID**, thay vì chỉ một String. Không suy ra retry an toàn chỉ từ category.

## 12. Java 17+: ba lỗi socket thật trên loopback

Chương trình thứ hai không giả lập bằng cách `new BindException(...)`. Nó thực hiện **ba tình huống networking cục bộ**:

1. Hai `ServerSocket` cùng muốn bind một IP/port → `BindException`.
2. Connect tới port loopback vừa giải phóng, không có listener → thông thường `ConnectException`, trong môi trường kiểm thử đã xác nhận.
3. Server chấp nhận TCP nhưng cố tình chưa gửi dữ liệu; client đặt `setSoTimeout(120ms)` rồi `read()` → `SocketTimeoutException` từ giai đoạn **read**.

**Tệp `SocketFailureLab.java`:**

```java
import java.io.IOException;
import java.net.*;
import java.util.concurrent.*;

public class SocketFailureLab {
    private static final InetAddress LOOPBACK;
    static {
        try { LOOPBACK = InetAddress.getByName("127.0.0.1"); }
        catch (UnknownHostException impossibleForLiteral) {
            throw new ExceptionInInitializerError(impossibleForLiteral);
        }
    }

    private static String bindConflict() throws Exception {
        try (ServerSocket first = new ServerSocket();
             ServerSocket second = new ServerSocket()) {
            first.bind(new InetSocketAddress(LOOPBACK, 0));
            try {
                second.bind(new InetSocketAddress(
                        LOOPBACK, first.getLocalPort()));
                return "UNEXPECTED_SUCCESS";
            } catch (BindException expected) {
                return expected.getClass().getSimpleName();
            }
        }
    }

    private static String refusedConnect() throws Exception {
        int unusedPort;
        try (ServerSocket reservation = new ServerSocket()) {
            reservation.bind(new InetSocketAddress(LOOPBACK, 0));
            unusedPort = reservation.getLocalPort();
        }
        try (Socket client = new Socket()) {
            try {
                client.connect(new InetSocketAddress(LOOPBACK, unusedPort), 1000);
                return "UNEXPECTED_SUCCESS";
            } catch (ConnectException expected) {
                return expected.getClass().getSimpleName();
            }
        }
    }

    private static String readTimeout() throws Exception {
        CountDownLatch accepted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress(LOOPBACK, 0));
            listener.setSoTimeout(4000);
            Future<?> server = worker.submit(() -> {
                try (Socket peer = listener.accept()) {
                    accepted.countDown();
                    if (!release.await(4, TimeUnit.SECONDS))
                        throw new IllegalStateException("Wait expired");
                } catch (Exception failure) {
                    throw new RuntimeException(failure);
                }
            });
            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(
                        LOOPBACK, listener.getLocalPort()), 2000);
                client.setSoTimeout(120);
                if (!accepted.await(2, TimeUnit.SECONDS))
                    throw new IllegalStateException("Server did not accept");
                try {
                    client.getInputStream().read();
                    return "UNEXPECTED_SUCCESS";
                } catch (SocketTimeoutException expected) {
                    return expected.getClass().getSimpleName();
                }
            } finally {
                release.countDown();
                server.get(3, TimeUnit.SECONDS);
            }
        } finally {
            release.countDown();
            worker.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Bind collision: " + bindConflict());
        System.out.println("Connect to closed port: " + refusedConnect());
        System.out.println("Silent peer read: " + readTimeout());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SocketFailureLab.java
java SocketFailureLab
```

**Stdout đã quan sát trên loopback của môi trường kiểm thử:**

```text
Bind collision: BindException
Connect to closed port: ConnectException
Silent peer read: SocketTimeoutException
```

**Giải thích có giới hạn:**

- `Bind collision` diễn ra **trên máy local** trước khi có remote TCP client nào cần gửi request.
- `Connect to closed port`: chương trình giữ port tạm thời để biết port số nào rồi đóng listener và thử connect. Thông thường OS trả refused, nhưng vẫn có **race cực nhỏ** nếu process khác chiếm ngay port vừa giải phóng hoặc OS/network policy khác. Không dùng kết quả này làm “chứng minh mọi connect thất bại đều refused”.
- `Silent peer read`: server **đã accept thành công** và dùng latch để chờ, không gửi response. Vì vậy timeout xuất hiện từ **read**, không phải connect; `accepted.await` xác nhận phase trước khi test read.
- `setSoTimeout(120)` không đồng nghĩa TCP socket bắt buộc bị đóng sau exception. Application vẫn phải quyết định lifecycle/cleanup.
- Test đóng tài nguyên trong `try-with-resources`, `finally` thả latch và shutdown executor. Timeout và port thử nghiệm chỉ dành cho loopback, không phụ thuộc Internet.
- Trong hệ thống thật, nếu thấy `SocketTimeoutException`, phải xem **stack trace/callsite** trước khi phân loại là connect timeout hay read timeout.

## 13. Java 17+: HTTP 503 là response hợp lệ, không phải lỗi TCP

Chương trình thứ ba dựng một HTTP server loopback trả status `503 Service Unavailable` và body `BACK_LATER`. Sau đó:

- Dùng `HttpURLConnection` đọc `getResponseCode()==503` và body từ `getErrorStream()`.
- Dùng `java.net.http.HttpClient` và `BodyHandlers.ofString()`, nhận `HttpResponse<String>` có status 503.
- Cố cấu hình một request method sai trên `HttpURLConnection` để **nhận `ProtocolException` tại client API**, chứ không phải từ network.

**Tệp `HttpStatusVsProtocolDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpStatusVsProtocolDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0),
                0);
        server.createContext("/unavailable", exchange -> {
            try (exchange) {
                byte[] bytes = "BACK_LATER".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(503, bytes.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            }
        });
        try {
            server.start();
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/unavailable");
            HttpURLConnection legacy = (HttpURLConnection)
                    uri.toURL().openConnection();
            legacy.setConnectTimeout(3000);
            legacy.setReadTimeout(3000);
            try {
                System.out.println("URLConnection status: "
                        + legacy.getResponseCode());
                try (InputStream error = legacy.getErrorStream()) {
                    if (error == null)
                        throw new IllegalStateException("Missing error stream");
                    System.out.println("URLConnection error body: "
                            + new String(error.readAllBytes(),
                                    StandardCharsets.UTF_8));
                }
            } finally {
                legacy.disconnect();
            }

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(3)).GET().build();
            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());
            System.out.println("HttpClient status: " + response.statusCode());

            HttpURLConnection wrongMethod = (HttpURLConnection)
                    uri.toURL().openConnection();
            try {
                wrongMethod.setRequestMethod("INVALID_METHOD");
                System.out.println("Method validation: UNEXPECTED_SUCCESS");
            } catch (ProtocolException expected) {
                System.out.println("Method validation: "
                        + expected.getClass().getSimpleName());
            } finally {
                wrongMethod.disconnect();
            }
        } finally {
            server.stop(0);
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 HttpStatusVsProtocolDemo.java
java HttpStatusVsProtocolDemo
```

**Stdout đã kiểm chứng:**

```text
URLConnection status: 503
URLConnection error body: BACK_LATER
HttpClient status: 503
Method validation: ProtocolException
```

**Điều thí nghiệm chứng minh:**

1. Server đã nhận request và trả HTTP 503 có body. Đây là **application/proxy response**, không phải DNS resolution error, TCP refused hay TLS handshake failure.
2. `HttpURLConnection.getResponseCode()` cho phép kiểm tra status ngay cả khi `getInputStream()` với lỗi HTTP có thể ném `IOException`. Trong demo `getErrorStream()` trả `BACK_LATER`.
3. `HttpClient.send(...)` không ném network exception chỉ vì response status không phải 2xx; caller đọc `statusCode()==503` và quyết định xử lý.
4. `ProtocolException` phát sinh **khi gọi `setRequestMethod` trên object chưa connect** do method không được API chấp nhận. Nó **không** chứng minh server đã gửi malformed HTTP; không nên diễn giải kết quả sai.
5. Với `HttpURLConnection`, `getErrorStream()` có thể trả `null` nếu không có body/error stream; code thật cần kiểm tra và giới hạn body bytes, đóng stream.
6. HTTP 503 có thể có `Retry-After` theo semantics; **không** tự retry POST có side effect nếu API không đảm bảo idempotency.

## 14. Java 17+: TLS client gặp plaintext server

Chương trình thứ tư mô phỏng **nhầm protocol ở cùng endpoint**, một lỗi phổ biến khi client dùng `https://` hoặc `wss://` tới port mà server chỉ gửi HTTP plaintext.

- Một `ServerSocket` loopback chấp nhận TCP connection và viết `HTTP/1.1 200 OK` ở dạng **plaintext**.
- Một `SSLSocket` của Java vẫn mong **TLS records**, nên `startHandshake()` không thể hoàn tất hợp lệ.
- Server giữ socket mở bằng latch trong lúc client xử lý lỗi; nhờ đó thử nghiệm tập trung vào **TLS protocol mismatch**, tránh một trường hợp peer đóng quá sớm khiến Windows báo `SocketException` trước khi JSSE nhận ra HTTP plaintext.

**Tệp `TlsVsPlainTcpDemo.java`:**

```java
import java.io.IOException;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import javax.net.ssl.*;

public class TlsVsPlainTcpDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        CountDownLatch release = new CountDownLatch(1);
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            listener.setSoTimeout(4000);
            Future<?> plainServer = worker.submit(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(4000);
                    peer.getOutputStream().write(
                            "HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
                                    .getBytes(StandardCharsets.US_ASCII));
                    peer.getOutputStream().flush();
                    release.await(4, TimeUnit.SECONDS);
                } catch (Exception error) {
                    throw new RuntimeException(error);
                }
            });
            SSLSocketFactory factory =
                    (SSLSocketFactory) SSLSocketFactory.getDefault();
            try (SSLSocket tls = (SSLSocket) factory.createSocket(
                    "127.0.0.1", listener.getLocalPort())) {
                tls.setSoTimeout(3000);
                try {
                    tls.startHandshake();
                    System.out.println("TLS handshake succeeded: true");
                } catch (IOException expected) {
                    System.out.println("TLS handshake succeeded: false");
                    System.out.println("Exception family: "
                            + (expected instanceof SSLException
                                ? "SSLException" : "other IOException"));
                    System.out.println("Exception subtype: "
                            + expected.getClass().getSimpleName());
                }
            } finally {
                release.countDown();
            }
            plainServer.get(3, TimeUnit.SECONDS);
        } finally {
            release.countDown();
            worker.shutdownNow();
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 TlsVsPlainTcpDemo.java
java TlsVsPlainTcpDemo
```

**Stdout đã kiểm chứng trong môi trường thử nghiệm:**

```text
TLS handshake succeeded: false
Exception family: SSLException
Exception subtype: SSLException
```

**Cảnh báo về khả năng khác biệt runtime:** Nếu peer đóng rất sớm, mạng bị reset hoặc OS/JDK nhận lỗi ở thứ tự khác, phần `IOException` có thể là `SocketException` thay vì `SSLException`, hoặc subtype có thể là `SSLHandshakeException`/`SSLProtocolException`. Điều chắc chắn trong demo là **client không thương lượng TLS thành công với một peer chỉ phát HTTP plaintext**. Không hard-code đúng một subtype làm kết quả mong đợi trong mọi môi trường.

Chương trình **không** kiểm thử certificate chain/hostname mismatch, vì plain server hoàn toàn không có certificate. Để chẩn đoán lỗi chứng chỉ thật, dùng endpoint TLS nội bộ được phép, xem SAN/chain/truststore/time/SNI và TLS debug logs đã kiểm soát; **không tắt trust validation** để “fix”.

## 15. Đọc stack trace và cause chain theo giai đoạn

Xét code bất đồng bộ:

```java
// Snippet minh họa; request/client đã được cấu hình.
CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());

try {
    HttpResponse<String> response = future.get();
} catch (ExecutionException wrapper) {
    Throwable real = wrapper.getCause();
    // Dùng exception type, cause chain và request context để phân loại.
}
```

`get()` thường bọc exceptional completion trong `ExecutionException`; `join()` thường biểu hiện qua `CompletionException`. Không chỉ log `ExecutionException: ...` rồi bỏ `getCause()`. Đồng thời đừng **tháo hết cause đến cùng** mà mất thông tin TLS/HTTP layer: lớp ngoài có thể ghi rõ phase, lớp trong ghi socket error.

### Mẫu triage theo context

```text
1. Operation?   DNS lookup / ServerSocket.bind / Socket.connect /
                 InputStream.read / SSLSocket.startHandshake /
                 HttpClient.send / parse HTTP?
2. Exception?   Exact class + parent cause + suppressed
3. Endpoint?    Origin/proxy hostname, resolved IP, local bind IP,
                 port, scheme http/https, IPv4/IPv6
4. Timeline?    Start/end/connect/read elapsed, timeout values
5. Evidence?    Server access log, TLS logs, packet trace được phép
6. Outcome?     Có HTTP response status? Có business request ID?
7. Recovery?    Fix config, fail fast, retry bounded hoặc reconcile
```

Ví dụ:

| Log quan sát | Cách kết luận có căn cứ |
|---|---|
| `Socket.connect(...,2000)` ném `SocketTimeoutException` | **Connect timeout** tại endpoint đó, chưa chứng minh nguyên nhân firewall |
| `input.read()` ném `SocketTimeoutException` sau TCP connect thành công | **Read timeout**, không phải DNS lỗi |
| `InetAddress.getByName()` ném `UnknownHostException` | **Name resolution** thất bại theo resolver dùng |
| `ServerSocket.bind()` ném `BindException` | **Local bind** thất bại, kiểm tra local IP/port |
| `SSLSocket.startHandshake()` ném `SSLHandshakeException` | **TLS handshake** không hoàn tất, xem cert/negotiation |
| `getResponseCode() == 503` | **Có HTTP response hợp lệ** 503, không phải network transport error |
| `HttpURLConnection.setRequestMethod(...)` ném `ProtocolException` | Lỗi API/protocol method **trước I/O** trong callsite này |
| `HttpClient.sendAsync().join()` ném `CompletionException` | Phải xem **cause** mới biết giai đoạn |
| `readNBytes(100)` chỉ được 40 rồi EOF | **Body chưa đủ** nếu protocol yêu cầu 100 bytes |

### Không tự gán “root cause” bằng một mã duy nhất

Có thể có chain:

```text
CompletionException
    └── SSLHandshakeException
          └── CertificateException / PKIX path building failed
```

Trong ngữ cảnh đó, category nên là `TLS_HANDSHAKE`, nhưng mô tả nguyên nhân chi tiết là **certificate trust chain** sau khi xem cause. Một người chỉ log `IOException` đã bỏ lỡ chẩn đoán hữu ích.

Ngược lại:

```text
IOException: unexpected EOF while reading HTTP body
    └── SocketException: Connection reset
```

Có thể cần ghi đồng thời **phase READ/HTTP_FRAMING** và **transport reset**, không buộc chọn một từ khóa rồi bỏ toàn bộ timeline.

## 16. Khả năng retry: lỗi nào có thể thử lại?

**Không áp một luật “IOException thì retry”**. Độ tin cậy không chỉ là phục hồi kết nối mà còn là **không lặp thao tác kinh doanh**.

| Lỗi / tình huống | Retry gợi ý | Điều kiện quan trọng |
|---|---|---|
| DNS tạm thời không phân giải được | Có thể thử có giới hạn sau kiểm tra resolver | Không retry liên tục mỗi vài ms, không đổi host tùy tiện |
| BindException cho server port cố định | **Không retry ngay cùng cấu hình** | Sửa local port, process conflict, quyền bind |
| ConnectException refused | Retry bounded nếu service dự kiến sắp hoạt động | Kiểm tra deployment/health, backoff/jitter |
| NoRouteToHostException | Thường phải xử lý route/VPN/firewall | Retry không giúp nếu policy chặn cố định |
| Connect timeout | Có thể retry với backoff theo contract | Không nhầm với server-side commit ở attempt khác |
| Read timeout sau POST body | **Outcome nghiệp vụ chưa biết** | Idempotency key, status query, tránh ghi trùng |
| TLS cert/hostname invalid | **Fail fast, sửa bảo mật** | Không tắt TLS validation/đổi HTTPS→HTTP |
| TLS tạm không tương thích do version/cipher | Sửa config/endpoint, không retry mù | Chẩn đoán version/cipher/ALPN/SNI |
| HTTP 401/403 | Thường cần auth/permission, không retry mù | Refresh credentials có giới hạn, đúng scope |
| HTTP 404 | Kiểm tra resource/path, không tự coi transient | Có thể eventual consistency theo contract |
| HTTP 429 | Bounded retry theo `Retry-After` và quota | Giữ method/idempotency và tổng deadline |
| HTTP 503 | Có thể retry theo policy và `Retry-After` | Không làm retry storm; biết endpoint/server outcome |
| Malformed HTTP framing | Không tiếp tục reuse connection mơ hồ | Parser/library version, proxy/backend contract |
| EOF trước body hoàn chỉnh | Request/response chưa hoàn tất | Có thể đã có server side effect |
| JSON schema invalid | Sửa contract/serialization | Không giải quyết bằng retry network vô hạn |

### “Đã kết nối rồi” không đồng nghĩa “đã thực thi”

TCP connect thành công chỉ nói kênh vận chuyển được tạo. Nó không cho biết server nhận đủ body hay đã commit. Ngược lại, **read timeout hoặc connection reset sau khi gửi body** cũng không chứng minh server chưa commit; response có thể đã bị mất sau khi database được ghi.

Khi gọi POST tạo đơn, hãy dùng **một idempotency key ổn định cho cùng logical operation** nếu API công bố contract đó. Server cần thực hiện dedup đúng, có lưu trạng thái và giới hạn retention; **HTTP/TCP không tự cung cấp exactly-once semantics** cho nghiệp vụ.

### Công thức retry có điều kiện

```text
if lỗi cấu hình/vĩnh viễn (bind conflict, invalid cert, bad method):
    fail fast + repair config
else if lỗi transient và request an toàn/đã có idempotency:
    retry có giới hạn + backoff + jitter + tổng deadline
else if server có thể đã commit:
    đánh dấu UNKNOWN + query trạng thái nghiệp vụ
else:
    surface lỗi có ngữ cảnh, không đoán
```

Đây là sơ đồ quyết định, không phải Java runnable code. Không dùng idempotency key mới ở lần retry cùng ý định; làm vậy có thể khiến server coi là giao dịch khác.

## 17. Chính sách timeout, connection pool và circuit breaker

Một hệ thống đáng tin cậy nên tách:

- **Connect timeout** — không đợi TCP connection vô hạn.
- **Read timeout** — không đợi một lần đọc vô hạn.
- **Whole-request deadline** — không cho request kéo dài mãi qua redirects/retries/body.
- **Business deadline** — khoảng thời gian ứng dụng chấp nhận hoàn thành operation.
- **Concurrency limit** — không mở vô hạn connection/threads/futures.
- **Retry budget** — tối đa attempts, tổng elapsed time và traffic amplification.
- **Circuit breaker** — tạm ngừng gọi một dependency lỗi liên tục, có half-open probing.

Nếu chỉ tăng timeout mà không tìm root cause, triệu chứng có thể tệ hơn: request giữ tài nguyên lâu, queue dài, thread exhaustion, retry storm. Một read timeout quá ngắn cũng tạo false positive cho response lâu nhưng hợp lệ. Chọn ngưỡng theo **SLO và đo lường latency thực tế**, không dùng một số cố định cho mọi endpoint.

### Java 17 HttpClient

```java
// Đoạn minh họa, cần imports java.net.http.*, java.net.URI,
// java.time.Duration; không có endpoint thử nghiệm thật ở đây.
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://api.example.test/items"))
        .timeout(Duration.ofSeconds(8))
        .GET()
        .build();

HttpResponse<String> response =
        client.send(req, HttpResponse.BodyHandlers.ofString());
```

`connectTimeout` và `request.timeout` đo các phạm vi khác nhau. `HttpConnectTimeoutException` là subclass của `HttpTimeoutException` và nên phân loại trước. Nếu dùng `sendAsync`, nhớ phân biệt `Future.get(timeout)` (chỉ giới hạn **caller wait**) với HTTP request timeout; việc chờ hết hạn **không tự hủy HTTP exchange**.

### Circuit breaker không giải quyết lỗi chứng chỉ

Nếu mọi yêu cầu đều fail vì TLS certificate hết hạn, circuit breaker có thể giảm tải, nhưng **không sửa certificate**. Cần observability và cảnh báo chủ động về cert expiry, DNS health, port binding, route changes và dependency SLO.

## 18. Bộ công cụ điều tra thực tế theo tầng

Chỉ chạy lệnh trên hệ thống mình quản lý hoặc được phép kiểm tra; ví dụ dưới đây là hướng dẫn chọn công cụ, **không phải kết quả kiểm tra một dịch vụ cụ thể**.

| Muốn biết | Windows/PowerShell | Linux |
|---|---|---|
| Name resolution | `Resolve-DnsName api.example.test`, `nslookup` | `getent hosts api.example.test`, `dig` |
| Port đang listen local | `Get-NetTCPConnection -State Listen` | `ss -ltn` |
| Kiểm tra TCP reachability | `Test-NetConnection host -Port 443` | `nc -vz host 443` nếu có và được phép |
| Route table | `route print`, `Get-NetRoute` | `ip route`, `ip -6 route` |
| HTTPS headers/status | `curl -v --http1.1 https://...` | `curl -v --http1.1 https://...` |
| TLS certificate/negotiation | Công cụ TLS được phê duyệt, ví dụ OpenSSL nếu cài | `openssl s_client -connect host:443 -servername host` |
| Packet diagnostics | Wireshark/capture được phép | `tcpdump`/Wireshark được phép |

**Không đánh đồng:**

- `nslookup` ra IP không chứng minh TCP port 443 mở.
- `ping` không thông chứng minh TCP không thể kết nối.
- `Test-NetConnection` thành công không chứng minh HTTPS certificate đúng hoặc API trả 200.
- `curl -k`/`--insecure` có thể che cert validation lỗi; **không dùng như biện pháp sửa production**.
- Port đang listen không chứng minh backend trả đúng HTTP response.
- TCP packet capture trên HTTPS không tự cho biết payload do TLS đã mã hóa.

### Bản ghi chẩn đoán tối thiểu

```text
timestamp
logicalRequestId / attemptId
scheme + host + port + path template (redact secrets)
localEndpoint / remoteEndpoint / selected address family
proxyRoute / DNS answer age nếu có
operationPhase = DNS | BIND | CONNECT | ROUTE | TLS | WRITE | READ | PROTOCOL
timeoutConfig = connect/read/request/overall
elapsedMs by phase
exceptionClass + causeChain (sanitized)
httpStatus + Retry-After nếu có
bytesSent/bytesReceived (ước lượng, không suy ra peer nhận đủ)
serverTraceId / businessOutcome nếu đã xác minh
```

Không ghi password, Authorization, session cookie, private key, token hoặc toàn body nhạy cảm. Nếu DNS/route có thông tin mạng nội bộ, log theo quyền truy cập phù hợp.

## 19. Bài tập tình huống và đáp án

**Câu 1.** `InetAddress.getByName("backend.internal")` ném `UnknownHostException`. Có chắc backend đang down không?  
**Đáp án:** Không. Chỉ biết name resolution không ra IP theo context resolver. Kiểm tra hostname, DNS/hosts, search domain, VPN, proxy, A/AAAA.

**Câu 2.** Server bind port 8080 ném `BindException`. Có nên tăng client read timeout?  
**Đáp án:** Không. Đây là local bind failure; kiểm tra process/listener trùng port, local IP và quyền bind.

**Câu 3.** Client kết nối `127.0.0.1:9999` nhận `ConnectException: Connection refused`. Có nghĩa DNS lỗi?  
**Đáp án:** Không. Literal IP không cần name lookup; TCP endpoint không chấp nhận connection trong attempt này.

**Câu 4.** DNS đã ra `10.0.0.5` nhưng `Socket.connect` ném `NoRouteToHostException`. Có mâu thuẫn không?  
**Đáp án:** Không. DNS cho biết IP, còn route/reachability là giai đoạn sau.

**Câu 5.** Firewall drop TCP SYN thì có luôn nhận `NoRouteToHostException` không?  
**Đáp án:** Không. Có thể connect timeout; mapping tùy policy/OS và phản hồi ICMP/RST.

**Câu 6.** `SocketTimeoutException` xuất hiện khi `InputStream.read`. Có phải connect timeout?  
**Đáp án:** Không. Callsite là thao tác read sau khi connect; classify `READ_TIMEOUT`.

**Câu 7.** `SocketTimeoutException` xuất hiện khi `Socket.connect(addr, timeout)`. Có phải read timeout?  
**Đáp án:** Không. Callsite là connect; classify `CONNECT_TIMEOUT`.

**Câu 8.** `read() == -1` có luôn là lỗi network?  
**Đáp án:** Không. Đó là EOF, có thể hợp lệ nếu protocol chờ close-delimited body, hoặc là incomplete message nếu vẫn thiếu bytes.

**Câu 9.** Server trả HTTP 503 + body `BACK_LATER`. Java HttpClient đã gặp network exception?  
**Đáp án:** Không phải chỉ vì status 503; đây là HTTP response hợp lệ. Caller phải đọc `statusCode()` và quyết định xử lý.

**Câu 10.** `HttpURLConnection.getInputStream()` ném `IOException` cho status 404. Có thể vẫn có error body không?  
**Đáp án:** Có. `getErrorStream()` có thể trả stream chứa response body, nhưng có thể null và cần đóng.

**Câu 11.** HTTPS certificate hostname không khớp; có nên đổi URL sang HTTP?  
**Đáp án:** Không. Cần sửa certificate/SAN/hostname/trust và TLS configuration, không hạ bảo mật.

**Câu 12.** `SSLHandshakeException` có nghĩa TCP connect chưa thành công?  
**Đáp án:** Không. TLS handshake thường diễn ra **sau** TCP connection; TCP có thể đã hoàn toàn connected.

**Câu 13.** TLS client nối tới server chỉ nói HTTP plaintext. Có thể nhìn thấy `SSLException` không?  
**Đáp án:** Có, nhưng một số runtime/timing có thể cho `SocketException` khi peer đóng/reset trước; cần xem phase và bytes.

**Câu 14.** `ProtocolException` ở `setRequestMethod("INVALID_METHOD")` là lỗi server gửi malformed HTTP?  
**Đáp án:** Không. Đây là validation của API tại client trước network request.

**Câu 15.** `HttpConnectTimeoutException` có được bắt bằng `catch (HttpTimeoutException e)` không?  
**Đáp án:** Có vì nó là subclass; nhưng classifier muốn tách connect timeout phải kiểm tra subtype **trước**.

**Câu 16.** `Future.get(200, MILLISECONDS)` hết thời gian. Có nghĩa `HttpClient.sendAsync` bị cancel?  
**Đáp án:** Không. Chỉ thời gian thread chờ hết; future/exchange có thể vẫn chạy.

**Câu 17.** POST gửi body xong rồi client read timeout. Có thể retry ngay với idempotency key mới?  
**Đáp án:** Không an toàn mặc định. Server có thể đã commit; cần kiểm tra trạng thái hoặc retry cùng logical key theo API contract.

**Câu 18.** Một `ConnectException` ở application đi qua proxy có chắc là lỗi socket nối tới origin không?  
**Đáp án:** Không. Client có thể connect tới proxy, và nơi thất bại cần xác minh từ proxy config và actual endpoint.

**Câu 19.** Công cụ `ping` chạy tốt, nhưng HTTPS vẫn handshake fail. Có bất thường không?  
**Đáp án:** Không. ICMP reachability không xác thực TLS certificate, cipher, SNI hoặc HTTP route.

**Câu 20.** Khi nào lỗi protocol không nên làm connection reuse?  
**Đáp án:** Khi HTTP framing mơ hồ/hỏng, body chưa hoàn chỉnh hoặc state decoder không còn đồng bộ; phải loại connection theo HTTP library/implementation contract.

## 20. Checklist cuối bài và nguồn tham khảo

### Checklist phân loại sự cố

- [ ] Xác định **giai đoạn cụ thể** bằng callsite: resolve, bind, connect, route, TLS, write, read, HTTP parse.
- [ ] Phân biệt local bind IP/port với remote connect IP/port.
- [ ] Không coi `UnknownHostException` là bằng chứng service đã down; kiểm tra resolver/hosts/proxy.
- [ ] Không coi `ConnectException` là DNS lỗi; kiểm tra listener/port và reject policy.
- [ ] Không coi `NoRouteToHostException` là DNS lỗi; kiểm tra route/gateway/VPN/firewall.
- [ ] Không gán mọi `SocketTimeoutException` thành READ; xem `connect` hay `read`.
- [ ] Phân biệt `EOFException` incomplete protocol với EOF kết thúc hợp lệ.
- [ ] Phân biệt `SSLHandshakeException`/`SSLException` với TCP refusal và chứng chỉ; không hạ TLS validation.
- [ ] Với `HttpClient`, kiểm tra `HttpConnectTimeoutException` trước `HttpTimeoutException`.
- [ ] Không biến HTTP 4xx/5xx hợp lệ thành `IOException` ở logic phân loại khi đã có status.
- [ ] Xem `CompletionException/ExecutionException.getCause()` nhưng giữ đầy đủ cause chain.
- [ ] Ghi network/proxy/route và phase elapsed có kiểm soát, không log secrets.
- [ ] Bounded retry và backoff chỉ cho transient failures phù hợp; **không retry POST có side effect mù quáng**.
- [ ] Xác minh business outcome nếu request có thể đã tới server trước timeout/cancel.
- [ ] Đóng `ServerSocket/Socket/InputStream` bằng try-with-resources; giải phóng executor trong finally.
- [ ] Với HTTP/1.1 framing hỏng, không reuse connection không còn đồng bộ.
- [ ] Dùng test cục bộ deterministic để học exception, không phá DNS/firewall/certificate của hệ thống thật.

**Ghi nhớ quan trọng:** Lỗi DNS, bind, connect, route, read, TLS và protocol thuộc **các bước khác nhau của một trao đổi mạng**. Một class exception giúp định hướng, nhưng chỉ **giai đoạn + callsite + nguyên nhân gốc + bằng chứng đối chiếu** mới đủ để chọn cách sửa và retry an toàn.

### Tài liệu chuẩn (Java 17)

- [`UnknownHostException` — không xác định được địa chỉ IP](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/UnknownHostException.html)
- [`BindException` — không bind được địa chỉ/port](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/BindException.html)
- [`ConnectException` — lỗi TCP connect](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ConnectException.html)
- [`NoRouteToHostException` — không đến được endpoint/route](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NoRouteToHostException.html)
- [`SocketTimeoutException` — socket timeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html)
- [`Socket` — `connect`/`setSoTimeout`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [`SSLHandshakeException` và `SSLException` — lỗi TLS](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLHandshakeException.html)
- [`ProtocolException` — lỗi protocol](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProtocolException.html)
- [`HttpTimeoutException` và `HttpConnectTimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html)
- [`HttpURLConnection` — response/status/error stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html)
- [`HttpClient` — HTTP/1.1, HTTP/2 và thời hạn kết nối](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [RFC 9110 — HTTP Semantics, status và retry](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 9112 — HTTP/1.1 message framing](https://www.rfc-editor.org/rfc/rfc9112.html)
