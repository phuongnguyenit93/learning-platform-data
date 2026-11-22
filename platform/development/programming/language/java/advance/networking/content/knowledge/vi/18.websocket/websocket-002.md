# ws, wss, opening handshake và vai trò của HttpClient trong Java WebSocket

## Mục tiêu bài học

WebSocket tạo một kênh giao tiếp **hai chiều, lâu dài** giữa client và server. Với WebSocket theo RFC 6455, kết nối bắt đầu từ một **HTTP/1.1 opening handshake**, nhưng sau khi được chấp nhận, các bên trao đổi **WebSocket frames**, không tiếp tục gửi các HTTP request/response thông thường trên cùng kênh đã nâng cấp. Java 17 có **WebSocket client** ngay trong module `java.net.http`, tích hợp thông qua `HttpClient.newWebSocketBuilder()`; lập trình viên không phải tự tạo `Sec-WebSocket-Key`, tính `Sec-WebSocket-Accept` hoặc đọc từng frame trong ứng dụng thông thường.

Bài học tập trung vào bốn câu hỏi cốt lõi:

1. **`ws://` và `wss://` khác gì nhau?** Tại sao `wss` dùng TLS, mặc định port 443, còn `ws` không bảo vệ bytes trên đường truyền?
2. **Opening handshake thực sự diễn ra thế nào?** HTTP GET, `Upgrade: websocket`, `Connection: Upgrade`, `Sec-WebSocket-Key`, `Sec-WebSocket-Version: 13`, response `101 Switching Protocols` và phép kiểm `Sec-WebSocket-Accept`.
3. **`HttpClient` có vai trò gì?** Cách dùng `newWebSocketBuilder().buildAsync(uri, listener)` và các trách nhiệm của HTTP client, WebSocket builder, đối tượng WebSocket và Listener.
4. **Sau handshake, điều gì thay đổi?** Message text/binary, masking, fragment, Ping/Pong, Close, flow control `request(n)`, hoàn tất Future và phân biệt kết quả gửi bytes với phản hồi nghiệp vụ.

Có **ba chương trình Java 17+ độc lập**, đã biên dịch/chạy kiểm chứng: tính giá trị `Sec-WebSocket-Accept` theo vector RFC 6455; mở WebSocket loopback, handshake 101, trao đổi text và đóng 1000; và thử từ chối handshake bằng HTTP 403 hoặc giá trị Accept sai. Ví dụ thực hành dùng `ws` ở **localhost** để không cần certificate; triển khai thực tế nên ưu tiên `wss`.

## 1. WebSocket là gì và nó không phải gì?

HTTP truyền thống thường được dạy qua vòng `request → response`. Nếu browser/client cần cập nhật liên tục, ứng dụng có thể poll nhiều HTTP requests hoặc dùng Server-Sent Events. WebSocket giải bài toán khác: **giữ một kết nối hai chiều**, để **cả client lẫn server đều có thể chủ động gửi message** sau khi kết nối được thiết lập.

```text
HTTP request/response tuần tự:
Client ─── GET /messages ───► Server
Client ◄─── HTTP 200 ──────── Server
Client ─── GET /messages ───► Server
Client ◄─── HTTP 200 ──────── Server

WebSocket:
Client ─── HTTP opening handshake ───► Server
Client ◄─── 101 Switching Protocols ─ Server
       ╔════ WebSocket connection ════╗
Client ─── text/binary frame ────────► Server
Client ◄─── text/binary frame ──────── Server
Client ◄─── ping? / updates ───────── Server
Client ─── pong? / commands ────────► Server
       ╚════ Close handshake ═════════╝
```

Từ thời điểm handshake hợp lệ thành công:

- **Không còn dùng HTTP status line/headers cho từng message WebSocket**; dữ liệu ứng dụng nằm trong WebSocket frames.
- **Không có việc mỗi lần gửi WebSocket text phải mở một HTTP connection mới.**
- WebSocket sử dụng một **kết nối TCP** dưới dạng cơ bản của RFC 6455; TLS có thể được thêm qua `wss`.
- WebSocket không tự định nghĩa schema JSON, quyền chat, xác nhận transaction, quyền subscribe, idempotency hay cách đặt message ID. Đó là **protocol của ứng dụng** đặt trên WebSocket.
- “Gửi thành công” ở API `sendText` không bằng “server đã xử lý lệnh kinh doanh”; nếu cần, ứng dụng phải tự có message ID và ACK.

WebSocket thường phù hợp realtime dashboard, chat, collaborative editing, game event và luồng cập nhật trạng thái. Nhưng không phải API nào cũng cần WebSocket: một request CRUD đơn lẻ qua HTTPS thường đơn giản, dễ cache/monitor hơn.

### Phân biệt các thuật ngữ

| Khái niệm | Cấp độ | Điều nó quản lý |
|---|---|---|
| TCP connection | Vận chuyển | Byte stream giữa các endpoint |
| TLS (với `wss`) | Bảo vệ vận chuyển | Mã hóa, integrity và xác thực endpoint theo cấu hình |
| HTTP opening handshake | Thiết lập giao thức | Đề nghị/đồng ý chuyển từ HTTP sang WebSocket |
| WebSocket frame | Đóng khung | Opcode, length, mask, payload, FIN |
| WebSocket message | Ứng dụng/giao thức | Text hoặc binary, có thể gồm nhiều frames |
| Application message | Nghiệp vụ | JSON command, event, request ID, ACK... do app tự định nghĩa |

Một WebSocket **message** không đồng nghĩa một lần `onText`: API có thể giao **fragment** qua nhiều callbacks, dùng boolean `last` để chỉ đoạn cuối.

## 2. `ws://` và `wss://`: scheme, port, TLS

RFC 6455 định nghĩa hai URI schemes:

```text
ws://host[:port]/path?query
wss://host[:port]/path?query
```

| Thuộc tính | `ws://` | `wss://` |
|---|---|---|
| Kết nối bảo vệ bằng TLS? | Không | **Có** |
| Cổng mặc định nếu URI không ghi port | **80** | **443** |
| Mã hóa dữ liệu trên chặng transport | Không có TLS mặc định | TLS cho chặng được thiết lập |
| Chứng chỉ TLS và hostname verification | Không áp dụng ở transport `ws` | Cần kiểm tra trust/hostname certificate |
| Dùng cho production có credentials/dữ liệu nhạy cảm | Không nên qua mạng không đáng tin | **Nên dùng**, cùng auth/authorization |
| URI minh họa | `ws://127.0.0.1:9000/chat` | `wss://api.example.test/realtime` |

**Điểm rất quan trọng:** `wss` dùng **TLS**, không phải “WebSocket có JSON encryption riêng”. TLS handshake xảy ra **trước** HTTP/WebSocket opening handshake trên kết nối bảo mật. Các header handshake, messages và frames sau đó đi bên trong TLS.

```text
ws:
TCP connect → HTTP GET Upgrade → HTTP 101 → WebSocket frames → Close

wss:
TCP connect → TLS handshake, certificate/hostname validation
            → HTTP GET Upgrade bên trong TLS
            → HTTP 101 bên trong TLS
            → WebSocket frames bên trong TLS → Close
```

Nếu TLS kết thúc tại reverse proxy/load balancer, chặng browser→proxy được bảo vệ bởi `wss`; proxy→backend có thể dùng HTTP/WebSocket qua mạng nội bộ hoặc TLS riêng, tùy cấu hình. Không tự nói “toàn bộ đường đi được mã hóa end-to-end” nếu chưa xác minh tất cả các chặng.

### URI path, query và fragment

- `ws://example.test/chat?room=java` hợp lệ về cấu trúc, và `/chat?room=java` tham gia request target/resource name của handshake.
- **Không có fragment `#section` trong WebSocket URI** theo RFC 6455; fragment không phải dữ liệu gửi tới server.
- Không đưa access token dài hạn/secret vào query string nếu có thể tránh vì URL dễ lọt vào logs/analytics. Ưu tiên credential flow hoặc cơ chế auth do backend định nghĩa.
- `ws`/`wss` là **WebSocket schemes**, không dùng `http`/`https` thay thế trực tiếp khi gọi `WebSocket.Builder.buildAsync`.
- Đừng mặc định một endpoint `https://api.../rest` cũng tự hỗ trợ `wss://api.../rest`; server/proxy phải cấu hình route và protocol upgrade đúng.

### Mixed content và browser

Trang web tải bằng **HTTPS** thường không được phép thiết lập insecure WebSocket `ws://` tới endpoint không an toàn theo chính sách bảo mật browser. `wss://` là lựa chọn chuẩn trên trang HTTPS. Java desktop/server-side `HttpClient` không phải browser nên không mặc nhiên có cùng chính sách mixed-content và cookie-origin; ứng dụng Java phải tự áp dụng chính sách kết nối phù hợp.

## 3. Opening handshake HTTP/1.1: client gửi gì?

WebSocket theo RFC 6455 mở đầu bằng một **HTTP/1.1 GET request** đề nghị nâng cấp connection:

```http
GET /chat HTTP/1.1
Host: example.test
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Sec-WebSocket-Protocol: chat.v1, chat.v0

```

Trong bản wire thật, các dòng được kết thúc bởi `\r\n` (CRLF) và có **một dòng trống** kết thúc phần headers. Giá trị `Sec-WebSocket-Key` trong ví dụ là **vector chuẩn RFC**, không phải khóa phiên hoặc password của người dùng. Trên kết nối thực, client phải tạo một nonce mới đủ ngẫu nhiên theo RFC.

**Các thành phần:**

1. **`GET /chat HTTP/1.1`**: classic HTTP/1.1 opening handshake yêu cầu nâng cấp giao thức cho resource `/chat`. Nó không phải POST gửi một body JSON để “mở socket”.
2. **`Host`**: cho server/proxy biết host và port đích theo HTTP/1.1.
3. **`Upgrade: websocket`**: đề nghị chuyển sang giao thức websocket.
4. **`Connection: Upgrade`**: chỉ rõ `Upgrade` là tùy chọn hop-by-hop của kết nối HTTP/1.1; proxy phải xử lý chuyển tiếp phù hợp, không coi header hop-by-hop là end-to-end mặc định.
5. **`Sec-WebSocket-Key`**: nonce 16 bytes được Base64 encode; dùng trong cơ chế chứng minh server hiểu handshake.
6. **`Sec-WebSocket-Version: 13`**: WebSocket protocol version theo RFC 6455; không phải HTTP/1.3 hay Java version 13.
7. **`Sec-WebSocket-Protocol`** (tùy chọn): các subprotocol ứng dụng client đề xuất theo thứ tự ưu tiên.
8. **`Origin`** (tùy client/bối cảnh): browser gửi để server có thể áp dụng origin policy; Java non-browser client không tự động chịu cùng browser-origin rules.

Header field names trong HTTP không phân biệt hoa/thường. `Connection` là danh sách token, không nhất thiết chỉ có đúng một từ `Upgrade`. Vì vậy khi kiểm chứng request, parser nên kiểm tra token case-insensitive, thay vì so sánh toàn chuỗi cứng nhắc.

### `Sec-WebSocket-Key` có phải authentication token?

**Không.** Nó không phải chứng chỉ, password, session key, OAuth token hay secret. RFC 6455 dùng nonce kết hợp giá trị `Sec-WebSocket-Accept` để kiểm tra response đến từ một peer biết WebSocket protocol và không đơn thuần là một HTTP server/proxy trả nội dung nhầm lẫn. **Không được dùng Key/Accept làm cơ chế xác thực người dùng hay bí mật mã hóa.**

Nếu cần user authentication, hãy dùng TLS, cookie/session/token hoặc cơ chế hợp lệ của ứng dụng và xác minh permission tại server. Về bảo mật trình duyệt, `Origin` là một lớp kiểm soát quan trọng nhưng **không thay authentication/authorization**.

## 4. Server phản hồi: `101 Switching Protocols` và Accept

Khi server đồng ý, response classic handshake có dạng:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
Sec-WebSocket-Protocol: chat.v1

```

**`101 Switching Protocols`** không đồng nghĩa “bất kỳ 101 nào cũng thành công”. Client phải xác minh các header bắt buộc, protocol/version constraints và `Sec-WebSocket-Accept` được tạo đúng từ key nó đã gửi.

RFC 6455 chỉ rõ:

```text
clientKey = giá trị text của Sec-WebSocket-Key
GUID      = 258EAFA5-E914-47DA-95CA-C5AB0DC85B11

Sec-WebSocket-Accept =
  Base64( SHA-1( ASCII(clientKey + GUID) ) )
```

**Quan trọng:** nối **chuỗi Base64 của Sec-WebSocket-Key**, không nối 16 raw bytes đã decode. Với ví dụ chuẩn:

```text
Sec-WebSocket-Key:    dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

SHA-1 ở đây là phép biến đổi **do chuẩn giao thức quy định**, không dùng để lưu password và không thay thế TLS. Không có lý do phát minh “SHA-256 phiên bản mạnh hơn” cho `Sec-WebSocket-Accept`; làm thế sẽ phá tương thích WebSocket RFC 6455.

### Khi nào handshake chưa hoàn thành?

- Server trả `403 Forbidden` (không cho phép), `401 Unauthorized` (yêu cầu auth), `404 Not Found`, `400 Bad Request` hoặc status khác **101**: không có WebSocket connection theo classic RFC 6455.
- Server trả 101 nhưng thiếu `Upgrade`/`Connection` phù hợp, `Sec-WebSocket-Accept` sai hoặc subprotocol không hợp lệ: client phải **từ chối handshake**.
- TLS handshake thất bại (đối với `wss`) trước khi tới HTTP request: không có WebSocket connection.
- Proxy chặn/mất các hop-by-hop headers hoặc không chuyển tiếp upgrade: handshake có thể thất bại.
- Server redirect qua 3xx: không tự coi redirect thành công như WebSocket; hành vi follow phụ thuộc client implementation/policy và URI đích.

Sau khi HTTP opening handshake được chấp thuận, những bytes tiếp theo trên connection đó phải được **giải mã theo WebSocket framing**, không gửi HTTP request thứ hai như HTTP/1.1 keep-alive thông thường. Với WebSocket qua HTTP/2, RFC 8441 định nghĩa cơ chế **extended CONNECT** khác classic 101/Upgrade; **không áp đặt 101 của HTTP/1.1 lên mọi biến thể hạ tầng**. Bài này trình bày classic WebSocket handshake và Java 17 client.

## 5. Java 17+: tính `Sec-WebSocket-Accept` theo vector RFC

Tạo file **`WebSocketAcceptKeyDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;

public class WebSocketAcceptKeyDemo {
    public static void main(String[] args) throws Exception {
        String clientKey = "dGhlIHNhbXBsZSBub25jZQ==";
        String guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
        byte[] sha1 = MessageDigest.getInstance("SHA-1").digest(
                (clientKey + guid).getBytes(StandardCharsets.US_ASCII));
        String accept = Base64.getEncoder().encodeToString(sha1);
        System.out.println("Decoded key bytes: "
                + Base64.getDecoder().decode(clientKey).length);
        System.out.println("Sec-WebSocket-Accept: " + accept);
        System.out.println("Matches RFC 6455 example: "
                + accept.equals("s3pPLMBiTxaQ9kYGzzhZRbK+xOo="));
    }
}
```

Lệnh chạy:

```bash
javac --release 17 -encoding UTF-8 WebSocketAcceptKeyDemo.java
java WebSocketAcceptKeyDemo
```

**Stdout đã biên dịch/chạy kiểm chứng:**

```text
Decoded key bytes: 16
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
Matches RFC 6455 example: true
```

Phân tích:

1. `Base64.getDecoder().decode(clientKey)` cho ra 16 bytes; đây là chiều dài nonce đã encode trong `Sec-WebSocket-Key`.
2. Ghép **chuỗi key** với GUID, mã hóa ASCII rồi băm `SHA-1`.
3. Base64-encode 20-byte hash để tạo Accept theo RFC; chương trình được kiểm chứng khớp vector tiêu chuẩn.
4. Đây là **thí nghiệm học thuật về handshake**, không phải code nên tự nhúng vào một Java WebSocket client đang dùng `HttpClient`: thư viện đã làm việc này.
5. Không lưu trữ `clientKey` thành API key, không đánh dấu user đã đăng nhập vì Accept khớp, và không coi SHA-1 này như encryption của `wss`.

## 6. Subprotocol, extensions và Origin: ba cơ chế khác nhau

### 6.1. `Sec-WebSocket-Protocol` chọn một subprotocol ứng dụng

WebSocket chỉ cung cấp **transport frames và message types**. Hai bên cần biết payload mang ý nghĩa gì (JSON commands, STOMP, GraphQL transport, custom binary). Client có thể đề nghị:

```http
Sec-WebSocket-Protocol: chat.v2, chat.v1
```

Server **chỉ được chọn một subprotocol** trong danh sách được offer (hoặc không chọn), ví dụ:

```http
Sec-WebSocket-Protocol: chat.v1
```

Java:

```java
// Trích đoạn minh họa; 'client' là HttpClient đã được tạo.
WebSocket.Builder builder = client.newWebSocketBuilder()
        .subprotocols("chat.v2", "chat.v1");
// Sau buildAsync(...), ws.getSubprotocol() trả protocol đã thương lượng.
```

`subprotocols(mostPreferred, lesserPreferred...)` nhận các identifiers theo thứ tự ưu tiên. Sau khi kết nối, `WebSocket.getSubprotocol()` cho biết giá trị được chọn. Không tự ép server chọn preferred đầu tiên; server có thể chọn một protocol khác được client offer hoặc không chọn gì.

**Subprotocol không tự xác thực user.** Một subprotocol tên `admin.v1` không làm client có quyền admin; authorization vẫn phải kiểm tra phía server.

### 6.2. `Sec-WebSocket-Extensions` thương lượng tính năng

Extensions thay đổi cách một số frames được diễn giải, ví dụ extension nén message. Server không được tự trả một extension không có trong offer/không được client hỗ trợ. Khi có extension, frame parser cần tuân thủ RSV bits và quy tắc extension. **Không tự set RSV bit hoặc giả định mọi peer đều hỗ trợ nén**. Java 17 `WebSocket.Builder` không cung cấp một API phổ quát giống `subprotocols` để tự ý bật mọi WebSocket extension; đừng bịa `builder.extensions(...)`.

### 6.3. `Origin` và chính sách bảo mật browser

Browser thường gửi `Origin` trong opening handshake để WebSocket server đánh giá site phát sinh kết nối. WebSocket **không hoạt động như XHR chịu chính sách CORS theo cùng cách**; server cần kiểm tra Origin thích hợp để giảm nguy cơ **cross-site WebSocket hijacking** khi ứng dụng dùng cookies/session tự động của browser.

- Nếu server chỉ cho phép UI từ `https://app.example.test`, kiểm tra Origin theo allowlist, đồng thời yêu cầu auth/authorization.
- **Origin có thể bị giả bởi non-browser client**, vì vậy không được dùng Origin làm identity proof.
- Java `HttpClient` là non-browser client; đừng kỳ vọng nó tự mô phỏng đầy đủ cookie/Origin policy của browser.
- Nếu ứng dụng dùng token riêng, giới hạn token scope, TTL và tránh đưa secrets trong URI query/log.
- Với `wss`, kiểm tra TLS certificate, hostname, trust store và các proxy/TLS termination points.

## 7. Vai trò chính xác của `HttpClient` trong Java 17

Các class cần nhớ thuộc module **`java.net.http`** (có từ Java 11):

- `java.net.http.HttpClient`: cấu hình HTTP client; từ đó lấy `WebSocket.Builder`.
- `java.net.http.WebSocket.Builder`: cấu hình opening handshake, optional headers, connect timeout và subprotocols.
- `java.net.http.WebSocket`: một WebSocket connection đã xây thành công; gửi text/binary/ping/pong/close, xem trạng thái input/output.
- `java.net.http.WebSocket.Listener`: nhận open, text/binary, ping/pong, close, error callbacks.

**Đường đi đúng:**

```java
// Trích đoạn minh họa; imports URI, Duration, HttpClient, WebSocket.
HttpClient client = HttpClient.newHttpClient();

CompletableFuture<WebSocket> opening = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .subprotocols("chat.v1")
        .buildAsync(URI.create("wss://api.example.test/ws"), listener);

WebSocket socket = opening.join();
```

Đây là **đoạn minh họa không độc lập**: `listener` phải được định nghĩa, endpoint ví dụ phải tồn tại và certificate hợp lệ; cần xử lý exceptional completion, timeout, cleanup. Không chạy URI ví dụ rồi đoán kết quả network.

**Điều Java làm giúp bạn:**

1. Dùng URI scheme `ws`/`wss` để mở transport phù hợp và TLS khi cần.
2. Tạo classic opening handshake theo protocol; quản lý headers bắt buộc và nonce ngẫu nhiên.
3. Kiểm tra response 101, token headers, Accept, subprotocol/extension constraints theo implementation.
4. Sau handshake, mã hóa/giải mã WebSocket frames, **mask** frames từ client và kiểm soát frame protocol.
5. Dispatch `WebSocket.Listener` callbacks, quản lý demand qua `request(n)`.
6. Hỗ trợ `sendText`, `sendBinary`, `sendPing`, `sendPong`, `sendClose`, `abort`.

**Điều Java KHÔNG tự làm thay ứng dụng:**

- Định nghĩa format JSON/schema hoặc quyết định ai được subscribe vào topic nào.
- Cấp quyền truy cập dựa chỉ vào Sec-WebSocket-Key hoặc subprotocol.
- Bảo đảm server đã áp dụng một business command khi `sendText` future completed.
- Auto reconnect với backoff, resume cursor và dedup phù hợp nghiệp vụ.
- Tự quyết định heartbeat period/liveness policy ở tầng ứng dụng.
- Cung cấp một WebSocket server production chỉ bằng `HttpClient`. `java.net.http.WebSocket` là **client API**, không phải WebSocket server listener được host mặc định.

### Vì sao không dùng `HttpClient.send()` cho WebSocket?

`client.send(HttpRequest, BodyHandler)` / `sendAsync` dùng cho **HTTP request–response**, không cung cấp `WebSocket.Listener`, framing, ping/pong và close handshake tự động cho một kết nối đã upgrade. Không tự đặt `Upgrade: websocket` lên `HttpRequest` rồi mong `send(...)` trả một đối tượng WebSocket.

Thay vào đó, sử dụng **`client.newWebSocketBuilder().buildAsync(...)`**. Cùng `HttpClient` có thể dùng chung cấu hình liên quan proxy, authenticator, SSL context tùy implementation, nhưng một **WebSocket connection đã mở không phải một HTTP request thông thường**.

### Không tự ghi các reserved handshake headers

`WebSocket.Builder.header(name, value)` cho phép thêm các HTTP headers phù hợp trong handshake, nhưng Javadoc nói rõ **những headers được giao thức WebSocket định nghĩa là không hợp lệ để thêm theo cách này**. Không thủ công `header("Sec-WebSocket-Key",...)`, `header("Sec-WebSocket-Accept",...)`, `header("Upgrade",...)` để “ép” handshake.

```java
// Minh họa cách cấu hình hợp lệ về mặt cấu trúc;
 // endpoint và authorization phải theo contract ứng dụng.
WebSocket.Builder builder = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .header("X-Trace-Id", "trace-123")
        .subprotocols("chat.v1");
```

Đây là snippet chứ không phải chương trình độc lập; `client`/imports phải khai báo. Không đưa password/access token vào `X-Trace-Id`. Nếu server cần login, dùng credentials/cookies/auth đúng protocol và chỉ gửi qua `wss`.

## 8. `WebSocket.Builder.buildAsync` trả Future của opening handshake

Chữ ký:

```java
CompletableFuture<WebSocket> buildAsync(URI uri,
        WebSocket.Listener listener);
```

Khi **kết nối thành công**, future hoàn tất bằng `WebSocket` đã mở. Khi thất bại, nó hoàn tất exceptional. Các lỗi cần biết theo Java 17 Javadoc:

| Trường hợp | Dấu hiệu/lỗi có thể thấy | Hướng xử lý |
|---|---|---|
| Server HTTP trả 403/401/404 thay vì 101 | `WebSocketHandshakeException`; response status có thể lấy từ exception | Xác thực/quyền, URI/route |
| Server HTTP 101 nhưng Accept/header sai | `WebSocketHandshakeException` | Sửa server/proxy handshake, không bỏ kiểm tra |
| Timeout establishing/opening handshake | `HttpTimeoutException` với builder connect timeout | Kiểm tra TCP/TLS/proxy/handshake và deadline |
| DNS/TCP refused, TLS validation hoặc I/O lỗi | `IOException` hoặc nguyên nhân liên quan | Kiểm tra address, cert, TLS, proxy, port |
| Sai URI/header/subprotocol argument | `IllegalArgumentException` | Sửa cấu hình theo API |
| Thread chờ `Future.get` bị interrupt | `InterruptedException` tại thread chờ | Restore interrupt/policy shutdown riêng |

**`WebSocket.Builder.connectTimeout` chỉ đặt thời hạn thiết lập WebSocket connection**, không phải “giới hạn tối đa một WebSocket chỉ được sống 5 giây”. Sau khi mở, cần timeout/heartbeat/idle policy riêng nếu ứng dụng yêu cầu.

Khi dùng `buildAsync(...).get(timeout, unit)`, thời hạn từ `get` **chỉ giới hạn việc thread chờ Future** — nó không tự chứng minh handshake/network đã bị hủy nếu caller bị `TimeoutException`. Đừng lẫn `WebSocket.Builder.connectTimeout` với `CompletableFuture.get(timeout)`.

### Phân loại exceptional future đúng

`buildAsync` trả Future. Khi dùng `get`, lỗi thường được gói trong `ExecutionException`:

```java
// Đoạn minh họa, biến 'opening' là CompletableFuture<WebSocket>.
try {
    WebSocket socket = opening.get(5, TimeUnit.SECONDS);
} catch (ExecutionException failed) {
    Throwable cause = failed.getCause();
    if (cause instanceof WebSocketHandshakeException rejected) {
        int status = rejected.getResponse().statusCode();
        // Ghi nhận status và metadata được phép; không log secrets.
    }
}
```

`getResponse()` cho phép kiểm tra HTTP response gây lỗi handshake; nó **không cấp cho ứng dụng một WebSocket đã kết nối**. Các chương trình hoàn chỉnh ở phần sau minh họa cả đường thành công và từ chối.

## 9. Sau handshake: WebSocket frames, masking và message

WebSocket không gửi “raw text” trực tiếp mà không đóng khung. Frame cơ bản có:

```text
FIN | RSV1..3 | opcode | MASK | payload length | [mask key] | payload bytes
```

- **FIN**: frame cuối của message hay không; message text/binary có thể được chia nhiều fragments.
- **Opcode**: `0x1` = text, `0x2` = binary, `0x0` = continuation, `0x8` = close, `0x9` = ping, `0xA` = pong.
- **Payload length**: 7 bits hoặc dạng mở rộng 16/64 bits khi cần; phải đọc đúng số bytes, không lấy số lần socket read làm ranh giới.
- **MASK**: theo RFC 6455, **tất cả client→server frames phải masked**. Server→client frames **không masked**. Mask key 4 bytes dùng XOR; masking **không phải encryption** và không bảo vệ secrets thay TLS.
- **RSV bits** phải bằng 0 nếu không có extension cho phép sử dụng chúng.
- **Control frames** như ping/pong/close không được fragment và payload dài tối đa 125 bytes.

```text
Client text message "HELLO":
client -> server: FIN=1, opcode=1, MASK=1, payloadLength=5,
                  4-byte mask key, 5 masked bytes

Server echo:
server -> client: FIN=1, opcode=1, MASK=0, payloadLength=10,
                  UTF-8 bytes "ECHO:HELLO"

Close:
client -> server: FIN=1, opcode=8, MASK=1, payload status 1000
server -> client: FIN=1, opcode=8, MASK=0, payload status 1000
```

**Một WebSocket message khác một frame.** Một message lớn có thể bị fragment; listener `onText(..., last)` có thể được gọi nhiều lần. Không giải mã/cắt một JSON object riêng ở mỗi callback nếu `last=false` và protocol của ứng dụng dự kiến ghép cả message.

## 10. Java 17+: mở WebSocket loopback, handshake và trao đổi thực tế

Chương trình này minh họa đồng thời **cả vai trò HttpClient và các byte tối thiểu của server-side RFC handshake**. Một `ServerSocket` cục bộ đóng vai WebSocket server học tập: nó nhận HTTP GET Upgrade, tính `Sec-WebSocket-Accept`, trả `101`, nhận **masked text frame**, gửi **unmasked text echo**, rồi hoàn tất Close handshake.

Ứng dụng client dùng chính **`HttpClient.newWebSocketBuilder()`** của JDK 17, không phải socket raw client. Nó mở URI `ws://127.0.0.1:port/chat`, đề nghị subprotocol `demo.chat`, gửi `HELLO`, nhận `ECHO:HELLO` và đóng normal status `1000`.

**Đây không phải WebSocket server production.** Server demo chỉ đọc frame ngắn (payload tối đa 125 bytes), một message text và một Close frame; nó không hỗ trợ fragmented messages, extended lengths, Ping/Pong tùy thời điểm, extension compression, nhiều clients hoặc TLS. Mục tiêu là nhìn rõ handshake/masking và kiểm chứng API client, **không** xây server Internet.

**Tệp `WebSocketLoopbackDemo.java`:**

```java
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class WebSocketLoopbackDemo {
    private record Frame(int opcode, boolean masked, byte[] payload) {}
    private record Evidence(boolean correctRequest, boolean upgradeHeaders,
                            boolean version13, boolean validKey, String text) {}

    private static String line(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        for (;;) {
            int c = in.read();
            if (c < 0) throw new EOFException("Header ended unexpectedly");
            if (c == '\r') {
                if (in.read() != '\n') throw new IOException("Expected CRLF");
                return b.toString(StandardCharsets.US_ASCII);
            }
            if (c == '\n' || b.size() >= 8192)
                throw new IOException("Invalid/oversized line");
            b.write(c);
        }
    }

    private static Map<String, String> headers(InputStream in) throws IOException {
        Map<String, String> result = new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
        for (int count = 0; count < 32; count++) {
            String l = line(in);
            if (l.isEmpty()) return result;
            int p = l.indexOf(':');
            if (p <= 0) throw new IOException("Invalid header");
            String name = l.substring(0, p).trim();
            String value = l.substring(p + 1).trim();
            result.merge(name, value, (a, b) -> a + ", " + b);
        }
        throw new IOException("Too many headers");
    }

    private static boolean token(String value, String name) {
        if (value == null) return false;
        for (String part : value.split(",")) {
            if (part.trim().equalsIgnoreCase(name)) return true;
        }
        return false;
    }

    private static Frame readClientFrame(InputStream in) throws IOException {
        int b0 = in.read(), b1 = in.read();
        if (b0 < 0 || b1 < 0) throw new EOFException("No frame");
        if ((b0 & 0x80) == 0) throw new IOException("Fragmented demo frame");
        boolean masked = (b1 & 0x80) != 0;
        int length = b1 & 0x7f;
        if (length >= 126 || length > 125 || !masked)
            throw new IOException("Expected short masked frame");
        byte[] mask = in.readNBytes(4);
        byte[] data = in.readNBytes(length);
        if (mask.length != 4 || data.length != length)
            throw new EOFException("Incomplete frame");
        for (int i = 0; i < data.length; i++)
            data[i] ^= mask[i % 4];
        return new Frame(b0 & 0x0f, masked, data);
    }

    private static void sendUnmasked(OutputStream out, int opcode, byte[] data)
            throws IOException {
        if (data.length > 125) throw new IllegalArgumentException("Demo limit");
        out.write(0x80 | opcode);
        out.write(data.length);
        out.write(data);
        out.flush();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            listener.setSoTimeout(5000);

            Future<Evidence> server = worker.submit(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(5000);
                    InputStream in = peer.getInputStream();
                    OutputStream out = peer.getOutputStream();
                    boolean correct = line(in).equals("GET /chat HTTP/1.1");
                    Map<String, String> h = headers(in);
                    boolean upgrade = token(h.get("Upgrade"), "websocket")
                            && token(h.get("Connection"), "Upgrade");
                    boolean v13 = "13".equals(h.get("Sec-WebSocket-Version"));
                    String key = h.get("Sec-WebSocket-Key");
                    byte[] decoded = Base64.getDecoder().decode(key);
                    boolean validKey = decoded.length == 16;

                    byte[] digest = MessageDigest.getInstance("SHA-1").digest(
                            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                                    .getBytes(StandardCharsets.US_ASCII));
                    String accept = Base64.getEncoder().encodeToString(digest);
                    String response = "HTTP/1.1 101 Switching Protocols\r\n"
                            + "Upgrade: websocket\r\n"
                            + "Connection: Upgrade\r\n"
                            + "Sec-WebSocket-Accept: " + accept + "\r\n"
                            + "Sec-WebSocket-Protocol: demo.chat\r\n\r\n";
                    out.write(response.getBytes(StandardCharsets.US_ASCII));
                    out.flush();

                    Frame text = readClientFrame(in);
                    if (text.opcode() != 1 || !text.masked())
                        throw new IOException("Expected masked text frame");
                    String message = new String(text.payload(), StandardCharsets.UTF_8);
                    sendUnmasked(out, 1, ("ECHO:" + message)
                            .getBytes(StandardCharsets.UTF_8));

                    Frame close = readClientFrame(in);
                    if (close.opcode() != 8)
                        throw new IOException("Expected close frame");
                    sendUnmasked(out, 8, new byte[] { 0x03, (byte) 0xE8 });
                    return new Evidence(correct, upgrade, v13, validKey, message);
                }
            });

            CountDownLatch textReceived = new CountDownLatch(1);
            CountDownLatch closeReceived = new CountDownLatch(1);
            AtomicReference<String> echo = new AtomicReference<>("");
            AtomicInteger closeStatus = new AtomicInteger(-1);
            AtomicReference<Throwable> callbackError = new AtomicReference<>();
            WebSocket.Listener clientListener = new WebSocket.Listener() {
                private final StringBuilder parts = new StringBuilder();

                @Override public void onOpen(WebSocket socket) {
                    socket.request(1);
                }
                @Override public CompletionStage<?> onText(
                        WebSocket socket, CharSequence data, boolean last) {
                    parts.append(data);
                    if (last) {
                        echo.set(parts.toString());
                        textReceived.countDown();
                    }
                    socket.request(1);
                    return CompletableFuture.completedFuture(null);
                }
                @Override public CompletionStage<?> onClose(
                        WebSocket socket, int code, String reason) {
                    closeStatus.set(code);
                    closeReceived.countDown();
                    return CompletableFuture.completedFuture(null);
                }
                @Override public void onError(WebSocket socket, Throwable error) {
                    callbackError.set(error);
                    textReceived.countDown();
                    closeReceived.countDown();
                }
            };

            URI uri = URI.create("ws://127.0.0.1:"
                    + listener.getLocalPort() + "/chat");
            WebSocket socket = HttpClient.newHttpClient().newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .subprotocols("demo.chat")
                    .buildAsync(uri, clientListener).get(5, TimeUnit.SECONDS);
            try {
                socket.sendText("HELLO", true).get(3, TimeUnit.SECONDS);
                if (!textReceived.await(3, TimeUnit.SECONDS) || callbackError.get() != null)
                    throw new IllegalStateException("No echo", callbackError.get());
                socket.sendClose(WebSocket.NORMAL_CLOSURE, "").get(3, TimeUnit.SECONDS);
                if (!closeReceived.await(3, TimeUnit.SECONDS) || callbackError.get() != null)
                    throw new IllegalStateException("No close", callbackError.get());
                Evidence info = server.get(3, TimeUnit.SECONDS);
                System.out.println("Request GET /chat HTTP/1.1: " + info.correctRequest());
                System.out.println("Upgrade headers: " + info.upgradeHeaders());
                System.out.println("WebSocket version 13: " + info.version13());
                System.out.println("Key is 16 bytes: " + info.validKey());
                System.out.println("Negotiated subprotocol: " + socket.getSubprotocol());
                System.out.println("Server received masked text: " + info.text());
                System.out.println("Client received text: " + echo.get());
                System.out.println("Close status: " + closeStatus.get());
            } finally {
                socket.abort();
            }
        } finally {
            worker.shutdownNow();
        }
    }
}
```

**Biên dịch và chạy với JDK 17+:**

```bash
javac --release 17 -encoding UTF-8 WebSocketLoopbackDemo.java
java WebSocketLoopbackDemo
```

**Stdout đã kiểm chứng trên TCP loopback:**

```text
Request GET /chat HTTP/1.1: true
Upgrade headers: true
WebSocket version 13: true
Key is 16 bytes: true
Negotiated subprotocol: demo.chat
Server received masked text: HELLO
Client received text: ECHO:HELLO
Close status: 1000
```

### Giải thích từng giai đoạn

1. Server demo bind `127.0.0.1` với port 0 nên hệ điều hành cấp một port cục bộ tạm thời; hai phía dùng **cùng địa chỉ IPv4 loopback** và không truyền dữ liệu ra mạng công cộng.
2. `HttpClient.newHttpClient().newWebSocketBuilder()` tạo builder; `.subprotocols("demo.chat")` đề nghị một subprotocol.
3. `buildAsync(...)` tạo HTTP GET opening handshake và kiểm tra HTTP response. Server demo đọc request line và header fields, kiểm tra token `Upgrade`/`Connection`, version 13, chiều dài key 16 bytes.
4. Server tạo `Sec-WebSocket-Accept` bằng công thức chuẩn và gửi `HTTP/1.1 101 Switching Protocols` cùng `Sec-WebSocket-Protocol: demo.chat`.
5. JDK client chấp nhận handshake và hoàn tất `CompletableFuture<WebSocket>`; `WebSocket.getSubprotocol()` trả `demo.chat` đã thương lượng.
6. Trong `onOpen`, listener gọi `socket.request(1)` để cho phép một receive callback. Không có yêu cầu demand thì `onText` có thể không được gọi, dù bytes đã đến.
7. `sendText("HELLO", true)` gửi **một message text hoàn chỉnh**. Client tự tạo frame được mask đúng chuẩn; server demo đọc mask key rồi XOR dữ liệu để khôi phục `HELLO`.
8. Server gửi frame unmasked `ECHO:HELLO`. Client `onText` ghép các fragments vào `StringBuilder` và dùng `last` để biết message hoàn tất; test gọi latch sau khi đã có đủ message.
9. `sendClose(1000,"")` gửi Close frame cho server. Server nhận và gửi Close frame status 1000; listener `onClose` quan sát status, latch cho phép main kết thúc.
10. `socket.abort()` trong `finally` là defensive cleanup của **test**; graceful path đã dùng Close handshake trước đó. Trong production không nên coi `abort` đồng nghĩa đóng orderly.
11. `readClientFrame` cố ý từ chối frame lớn/fragmented và **không phải parser đầy đủ**. Một server công khai phải dùng implementation WebSocket production hỗ trợ protocol validation và giới hạn tài nguyên.

Một chi tiết kỹ thuật: `MessageDigest.getInstance("SHA-1")` trong server demo chỉ dành cho thuật toán handshake theo RFC, không cấp thêm bảo mật cho `ws`. Muốn mã hóa network data, dùng `wss` với TLS.

## 11. Java 17+: handshake thất bại và kiểm tra response

Không phải server HTTP nào cũng sẵn sàng nâng cấp sang WebSocket. Program thứ ba mở loopback raw server và cố tình tạo **hai trường hợp lỗi**:

1. Server trả `HTTP/1.1 403 Forbidden` thay vì 101 — handshake chưa được chấp nhận.
2. Server trả `101 Switching Protocols` nhưng `Sec-WebSocket-Accept` sai — **trạng thái 101 tự nó chưa đủ** để client tin đây là WebSocket.

`buildAsync(...)` phải hoàn tất exceptional. Java 17 cung cấp `WebSocketHandshakeException.getResponse()` giúp xem status code của HTTP response bị từ chối, thay vì trả một socket đã mở.

**Tệp `WebSocketHandshakeFailureDemo.java`:**

```java
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class WebSocketHandshakeFailureDemo {
    private static void consumeHeaders(InputStream in) throws IOException {
        int matched = 0, total = 0;
        while (matched < 4) {
            int b = in.read();
            if (b < 0 || ++total > 16384) throw new IOException("Bad request");
            if (b == "\r\n\r\n".charAt(matched)) {
                matched++;
            } else {
                matched = b == '\r' ? 1 : 0;
            }
        }
    }

    private static int attempt(HttpClient client, URI uri) throws Exception {
        try {
            WebSocket connected = client.newWebSocketBuilder()
                    .buildAsync(uri, new WebSocket.Listener() {}).get(4, TimeUnit.SECONDS);
            connected.abort();
            return -1;
        } catch (ExecutionException failed) {
            Throwable cause = failed.getCause();
            if (cause instanceof WebSocketHandshakeException handshake)
                return handshake.getResponse().statusCode();
            throw new IllegalStateException("Unexpected error", cause);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            listener.setSoTimeout(4000);
            Future<?> server = executor.submit(() -> {
                try {
                    for (int i = 0; i < 2; i++) {
                        try (Socket peer = listener.accept()) {
                            peer.setSoTimeout(4000);
                            consumeHeaders(peer.getInputStream());
                            String reply = i == 0
                                    ? "HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                                    : "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                                    + "Connection: Upgrade\r\nSec-WebSocket-Accept: invalid-value\r\n\r\n";
                            peer.getOutputStream().write(
                                    reply.getBytes(StandardCharsets.US_ASCII));
                            peer.getOutputStream().flush();
                        }
                    }
                } catch (IOException error) {
                    throw new UncheckedIOException(error);
                }
            });
            URI uri = URI.create("ws://127.0.0.1:"
                    + listener.getLocalPort() + "/protected");
            HttpClient client = HttpClient.newHttpClient();
            int forbidden = attempt(client, uri);
            int invalidAccept = attempt(client, uri);
            server.get(4, TimeUnit.SECONDS);
            System.out.println("Rejected status: " + forbidden);
            System.out.println("Invalid accept rejected: " + (invalidAccept == 101));
            System.out.println("No usable WebSocket created: "
                    + (forbidden == 403 && invalidAccept == 101));
        } finally {
            executor.shutdownNow();
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 WebSocketHandshakeFailureDemo.java
java WebSocketHandshakeFailureDemo
```

**Stdout đã kiểm chứng trên JDK 17-compatible runtime:**

```text
Rejected status: 403
Invalid accept rejected: true
No usable WebSocket created: true
```

Đừng đọc dòng `Invalid accept rejected: true` thành “101 là một HTTP error code”. Ý nó là **HTTP 101 đã được server gửi**, nhưng **client phát hiện Accept sai và từ chối**. Điều đó xác nhận việc nâng cấp WebSocket còn đòi hỏi **headers hợp lệ**, không chỉ status code.

Trong thực tế, nếu `WebSocketHandshakeException` chứa `401`/`403`, hãy kiểm tra auth/permissions, Origin, cookies, token, route và proxy. Nếu HTTP 101 sai, hãy kiểm tra compatibility server/client, cặp key/accept, subprotocol/extensions và các hop trung gian có sửa header không. Không tắt xác thực handshake để “cho chạy được”.

## 12. Sử dụng `WebSocket.Listener` đúng: `onOpen`, `request(n)` và fragments

Java 17 `WebSocket.Listener` nhận các callbacks:

| Callback | Khi được gọi | Ứng dụng nên làm gì? |
|---|---|---|
| `onOpen(WebSocket)` | Sau khi WebSocket được mở | Chuẩn bị state và gọi `request(n)` để nhận callbacks |
| `onText(WebSocket, CharSequence, boolean last)` | Nhận một phần hoặc toàn bộ text message | Ghép text fragments, kiểm tra kích thước và `last`, yêu cầu thêm demand |
| `onBinary(WebSocket, ByteBuffer, boolean last)` | Nhận binary data | Đọc/copy đúng buffer bytes, lưu state và xét `last` |
| `onPing(WebSocket, ByteBuffer)` | Nhận Ping control | JDK hỗ trợ auto Pong; có thể ghi metric/liveness |
| `onPong(WebSocket, ByteBuffer)` | Nhận Pong | Cập nhật liveness/RTT nếu ứng dụng có heartbeat |
| `onClose(WebSocket, int code, String reason)` | Nhận Close và kết thúc chiều nhận | Chuyển state CLOSED, cleanup, không tiếp tục gửi data message |
| `onError(WebSocket, Throwable)` | Lỗi ở kênh WebSocket/handler | Log/context, fail pending operations, cleanup |

### `request(n)` là demand cho số lần **receive callback**

WebSocket giữ counter cho những receive method invocations còn được phép xảy ra. Khi mở mới, counter bằng 0. `webSocket.request(1)` cho phép **thêm một** callback nhận dữ liệu; nếu listener không tăng demand, text/binary messages có thể không được dispatch tới application dù I/O stack đang hoạt động.

```java
// Đoạn minh họa; không phải standalone class.
@Override public void onOpen(WebSocket ws) {
    ws.request(1);
}

@Override public CompletionStage<?> onText(
        WebSocket ws, CharSequence fragment, boolean last) {
    // Parse/accumulate fragments theo context của connection.
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
```

**Một `request(1)` không có nghĩa “một message đầy đủ”**: Javadoc đếm receive method invocations, một message có thể tạo nhiều onText/onBinary callbacks do fragmentation. `onOpen` và `onError` không tính là receive methods. Sau `onClose`/`onError`, API không tiếp tục gọi các listener methods nữa.

### Khi callback xử lý chậm

Mỗi receive method trả một `CompletionStage<?>`. Nếu xử lý được hoàn thành ngay, trả `CompletableFuture.completedFuture(null)` là phù hợp. Nếu phải xử lý bất đồng bộ, có thể trả stage thực sự hoàn tất sau khi state/buffer đã được xử lý theo chính sách; tránh block event-loop/dispatcher thread. Đồng thời cân nhắc **khi nào gọi `request(n)`** để không tạo backlog không giới hạn.

**Đừng gọi `request(Long.MAX_VALUE)` chỉ để che lỗi**, nếu application không kiểm soát memory và buffer/queue. Giới hạn message size, queue size, tốc độ client và slow-consumer policy phù hợp.

### Fragmented text

Ứng dụng không nên coi mỗi `onText` là một JSON document. Khi `last=false`, đó là fragment; có thể cần append vào `StringBuilder` rồi parse khi `last=true`. Với message lớn, giới hạn tích lũy bytes/chars để chống memory exhaustion. Trong ví dụ loopback, `HELLO` và `ECHO:HELLO` rất nhỏ nhưng listener vẫn sử dụng boolean `last`.

## 13. Gửi text/binary, Ping/Pong và Close

### 13.1. Gửi text hoặc binary

```java
// Đoạn minh họa: 'ws' là WebSocket đã kết nối.
CompletableFuture<WebSocket> sent =
        ws.sendText("hello", true);

// Với binary:
ByteBuffer buffer = ByteBuffer.wrap(new byte[] {1, 2, 3});
CompletableFuture<WebSocket> binarySent =
        ws.sendBinary(buffer, true);
```

Lệnh `sendText`/`sendBinary` **khởi tạo send operation** và trả `CompletableFuture<WebSocket>` cho operation đó. **Hoàn tất Future không chứng minh remote application đã đọc/commit**. Nếu cần biết server xử lý thành công, protocol của ứng dụng phải có **response/ACK correlation**.

Boolean `last` quyết định có phải fragment cuối của text/binary message. Nếu `last=false`, có thể gửi continuation data sau đó đúng loại. Không phát hai send operations xung đột khi operation trước còn pending; Javadoc có thể trả exceptional future với `IllegalStateException` nếu gửi không đúng thứ tự/trạng thái.

Không sửa `CharSequence` hoặc `ByteBuffer` nguồn khi send Future đang pending. Với binary, buffer có mutable position/limit và payload; xử lý ownership để tránh race.

### 13.2. Ping/Pong

```java
// Đoạn minh họa, yêu cầu imports java.nio.ByteBuffer.
ws.sendPing(ByteBuffer.wrap(new byte[] {0x01}));
```

WebSocket `Ping` dùng kiểm tra liveness hoặc độ trễ tùy ứng dụng. WebSocket JDK **tự xử lý received Ping** bằng cách gửi Pong theo giao thức; listener vẫn có thể nhận `onPing` nếu demand cho phép. Không nhầm Ping/Pong control frames với JSON heartbeat của business protocol.

Nếu đo RTT, gắn correlation payload nhỏ và theo dõi thời hạn pong; đồng thời xử lý proxy/server/load balancer idle timeout. **Không coi sự vắng mặt một lần Pong duy nhất là bằng chứng chắc chắn user offline**, vì scheduling, network và policy có thể ảnh hưởng.

### 13.3. Close có thứ tự và abort

```java
// Đoạn minh họa:
ws.sendClose(WebSocket.NORMAL_CLOSURE, "")
        .whenComplete((ignored, error) -> {
            // Ghi nhận kết quả gửi Close và cleanup app state.
        });

// Khi không thể graceful cleanup, có thể:
ws.abort();
```

`sendClose(1000,"")` khởi tạo một Close frame bình thường. JDK WebSocket tự phản hồi Close nhận được theo contract, và `onClose` được gọi khi peer gửi Close. `abort()` đóng input/output đột ngột, không phải một Close handshake êm đẹp; chỉ dùng khi lỗi/force deadline cần cleanup.

**Mã `1000`** = normal closure. Mã `1006` thường được dùng làm trạng thái quan sát “abnormal closure”, **không được gửi trên wire** như một Close code. Việc connection TCP bị cắt mà không có Close handshake phải được log là bất thường và xử lý pending requests phù hợp.

### 13.4. Nguồn dữ liệu và ACK nghiệp vụ

Ví dụ client gửi `{"action":"charge","amount":100}` qua WebSocket. `sendText` complete chỉ nói send operation hoàn tất ở phía client/JDK. Server có thể chưa parse, chưa commit hoặc connection có thể đứt trước khi response tới. Cần message ID, server dedup/idempotency và ACK theo business contract. **WebSocket không có exactly-once business delivery** mặc định.

## 14. `wss` trong production: TLS, proxy, routing và deployment

Một endpoint production thường có:

```text
Java WebSocket client
     |
     | wss://realtime.example.test/chat
     | DNS → TCP 443 → TLS
     v
Reverse proxy / Load balancer (TLS terminator hoặc passthrough)
     |
     | HTTP/1.1 Upgrade + Connection headers được giữ đúng
     v
WebSocket backend
     |
     | 101 Switching Protocols
     v
Long-lived bidirectional connection
```

Các điều cần kiểm tra:

1. **Certificate trust:** TLS certificate hợp lệ, hostname khớp, chain được trust; không vô hiệu SSL hostname verification chỉ để nối thành công.
2. **Proxy Upgrade:** reverse proxy cần cho phép upgrade WebSocket và chuyển đúng `Upgrade`/`Connection` trên chặng HTTP/1.1 tương ứng. Không copy hop-by-hop fields vô điều kiện qua nhiều lớp HTTP; proxy phải tự áp dụng semantics.
3. **Idle timeout:** connection lâu dài có thể bị cắt bởi load balancer/firewall sau thời gian idle; dùng Ping/Pong/heartbeat theo chính sách backend và infrastructure.
4. **Sticky sessions/state:** nếu backend giữ session in-memory, reconnect có thể vào node khác. Có thể dùng shared session store, routing, resume token hoặc pub/sub service; không giả định cùng server ở reconnect.
5. **Origin/auth checks:** validate Origin cho browser client, xác thực session/token và quyền subscribe trên server. `wss` mã hóa transport nhưng không thay authorization.
6. **Resource limits:** mỗi connection giữ file descriptor, buffer, thread/event-loop resources. Giới hạn concurrent connections, per-user rate, message size, queue và session lifetime.
7. **Certificate rotation/reload:** WebSocket connection đã mở có lifecycle dài; plan rotation/reconnection khi cần, không mặc định mọi phiên hiện tại cập nhật TLS ngay lập tức.
8. **Metrics:** handshake success/failure, status 101/403/401, TLS errors, active connections, bytes/messages, ping RTT, close codes, reconnect counts, failed authorization.

### `wss` và proxy authentication

`HttpClient` có cấu hình proxy và authenticator; Java WebSocket builder dùng client đó làm nguồn cấu hình. Nhưng các loại `401` origin, `407` proxy và `403` authorization cần được phân biệt. Nếu server trả HTTP `401` trước khi upgrade, đây vẫn là quá trình HTTP handshake chưa thành công. Đừng tự biến mọi response `401` thành “WebSocket đã kết nối nhưng user thiếu quyền”.

### `wss` không phải “WebSocket port 443 luôn”

Cổng mặc định của `wss` là 443 nhưng URI có thể chỉ port cụ thể, ví dụ `wss://test.example.test:8443/ws`. Điều quan trọng là scheme/TLS/proxy route và certificate đúng, không phải con số port duy nhất.

## 15. Thất bại thường gặp khi mở WebSocket

| Hiện tượng | Lớp cần kiểm tra | Hướng xử lý |
|---|---|---|
| `buildAsync` failed với HTTP 404 | URL/route | Sai path `/ws`, host, vhost hoặc API chưa bật WebSocket |
| HTTP 403 | Origin/ACL/auth | Allowlist, token/permission, session, reverse proxy policy |
| HTTP 401 | Auth challenge | Credentials, cookies, realm, TLS; không coi là 101 |
| HTTP 400 / 426 | Version/headers/proxy | `Upgrade`, `Connection`, version 13, handshake syntax |
| HTTP 101 nhưng handshake exception | Invalid Accept/subprotocol/extension | Kiểm tra key/Accept và header negotiation |
| `SSLHandshakeException` trên `wss` | TLS/certificates | Truststore, hostname, SNI, cert expiry và backend TLS |
| TCP connection refused | Network/listener | DNS, port, firewall, service chạy chưa |
| Handshake timeout | TCP/TLS/proxy/server | `WebSocket.Builder.connectTimeout`, network trace, proxy latency |
| Handshake thành công nhưng không có `onText` | Listener demand | Đã gọi `request(n)` chưa? Có onError/onClose không? |
| Client gửi text mà server không nhận được ứng dụng | Framing/app handler | WebSocket path, opcode, payload format, auth, business routing |
| `sendText` future complete nhưng không thấy ACK | Thiếu app-level ACK | Thiết kế correlation ID và status reply |
| Connection sống vài phút rồi mất | Idle timeout, NAT/proxy | Ping/Pong policy, reconnect và resume |
| Browser không kết nối được `ws` từ HTTPS page | Mixed-content policy | Dùng `wss` hợp lệ |
| `1006` trong telemetry | Abnormal close | TCP reset, proxy idle, TLS/network error |
| Multiple `onText` cho một message | Fragmentation | Ghép tới `last=true`, áp dụng size limit |
| Unexpected `IllegalStateException` ở send | Concurrent/pending send hoặc state sai | Serialize sends, kiểm tra close/output state |
| Slow subscriber gây memory tăng | Demand/queue/backpressure | Bounded queue, request(n) hợp lý, drop/close policy |
| Phải viết WebSocket server bằng Java 17 | Nhầm vai trò `HttpClient` | Dùng framework/server implementation hỗ trợ WebSocket |

### Quy trình chẩn đoán tối thiểu

1. **Xem URI:** là `ws` hay `wss`, đúng host/port/path/query chưa?
2. Với `wss`, **tách TLS**: certificate/hostname/ALPN/proxy đã đúng chưa?
3. **Xem HTTP handshake:** có status 101, Upgrade/Connection và Accept hợp lệ không?
4. **Xem subprotocol:** client đề nghị gì, server chọn gì, có hợp lệ không?
5. Nếu handshake xong, **không tiếp tục debug như HTTP response body**; chuyển sang WebSocket frame/message, Listener và demand.
6. **Xem onOpen/request(n)/onText/onError/onClose**, tránh bug client không request receive callbacks.
7. Nếu không có business response, kiểm tra **application protocol, authentication, message ID và ACK**, không chỉ network frame.
8. Kiểm tra **Close code**, Ping/Pong/idle timeout và tài nguyên proxy/firewall khi lỗi chỉ xảy ra sau thời gian chạy.

Không log trực tiếp `Authorization`/cookie/token hoặc payload nhạy cảm. Log request/connection IDs và status/class lỗi để phục vụ đối chiếu.

## 16. Thiết kế client WebSocket production bằng Java 17

Một client thực tế cần quản lý vòng đời thay vì chỉ gọi `buildAsync` rồi bỏ object:

```text
DISCONNECTED
    |
    | validate URI, credentials, config
    v
CONNECTING
    |
    | newWebSocketBuilder().buildAsync(...)
    |    ├── failure → FAILED (diagnose handshake/TLS)
    v
OPEN
    |
    | onOpen -> request(n)
    | subscribe/authorize app-level, send/receive messages
    | track message ids, bounded outbound queue, heartbeat
    |
    ├── recoverable network failure
    |        -> retry with backoff, fresh auth, resume cursor
    |
    └── requested stop
          -> sendClose(1000,...)
          -> wait close handshake with deadline
          -> abort only when forced, cleanup state
```

**Không tự động reconnect vô hạn không giới hạn**: nếu server trả HTTP `403` vì không có quyền, retry mỗi 10 ms là vô ích và gây tải. Phân loại handshake rejection vs transient network error, giới hạn attempts và backoff jitter; khi refresh credential, tránh gửi token hết hạn liên tục.

**Đừng tưởng reconnect tự mang lại state trước đó**: subscriptions, in-flight messages và cursor có thể mất khi TCP/WebSocket connection đổi. Nếu ứng dụng cần resume, server phải cung cấp resume token, last-event ID hoặc cơ chế query/snapshot. Với lệnh có side effect, retry cùng message cần idempotency/correlation theo contract.

**Dùng `CompletableFuture` đúng:** `buildAsync` future hoàn tất khi WebSocket được tạo, không phải khi mọi messages tương lai hoàn tất. `sendText` future hoàn tất cho **send operation**, không phải ACK. `onClose` phản ánh close peer gửi; `onError` phản ánh lỗi; cả hai nên tiến trình cleanup nhưng tránh double-complete request registry.

**Không block lâu trong callback.** Với JSON lớn, việc decode business data, ghi DB hoặc gọi blocking API trong WebSocket.Listener có thể ảnh hưởng dispatch/backpressure. Tách xử lý nặng sang executor riêng có bounded queue và lifecycle.

### Mẫu hành vi an toàn (pseudocode)

```text
connect():
    validate ws/wss URI + allowed origins/hosts + auth configuration
    opening = client.newWebSocketBuilder()
                    .connectTimeout(handshakeDeadline)
                    .subprotocols(expectedProtocol)
                    .buildAsync(uri, listener)
    on success -> state OPEN; send subscribe/auth message nếu protocol yêu cầu
    on failure -> classify TLS / HTTP handshake / network; retry theo policy

onOpen(socket):
    socket.request(1)

onText(fragment, last):
    append with maxMessageBytes
    if last:
        decode/validate application envelope
        correlate messageId; update business state
    request next fragment when consumer capacity available

sendCommand(command):
    assign stable id and enqueue in bounded queue
    ws.sendText(serialize(command), true)
    on send error -> mark transport failure (business outcome unknown)
    await app ACK if API requires confirmation

stop():
    stop accepting new outbound commands
    ws.sendClose(1000, "")
    wait for close with deadline; abort if necessary
    fail/reconcile in-flight commands
```

Đây là thuật toán mô tả, **không phải Java code độc lập**, vì việc quản lý state machine, queue, authentication và timeout của mỗi ứng dụng khác nhau.

## 17. Tự kiểm tra kiến thức

**Câu 1.** `ws://` và `wss://` khác nhau ở yếu tố cốt lõi nào?  
**Đáp án:** `wss` chạy WebSocket qua TLS để bảo vệ chặng transport và mặc định dùng port 443; `ws` không có TLS và mặc định port 80.

**Câu 2.** WebSocket có phải bắt đầu bằng HTTP request/response mãi trong suốt session?  
**Đáp án:** Không. Classic RFC 6455 bắt đầu bằng HTTP/1.1 GET Upgrade và 101; sau đó trao đổi WebSocket frames trên connection đã nâng cấp.

**Câu 3.** `Sec-WebSocket-Key` là password/chìa khóa mã hóa TLS?  
**Đáp án:** Không. Đó là nonce dùng kiểm tra opening handshake; không thay user authentication/TLS.

**Câu 4.** Công thức `Sec-WebSocket-Accept` là gì?  
**Đáp án:** Base64 của SHA-1 hash trên **chuỗi Base64 Sec-WebSocket-Key nối GUID** `258EAFA5-E914-47DA-95CA-C5AB0DC85B11`.

**Câu 5.** Server trả HTTP 101 nhưng `Sec-WebSocket-Accept` sai. Java client nên làm gì?  
**Đáp án:** Từ chối opening handshake; `buildAsync` hoàn tất exceptional (có thể là `WebSocketHandshakeException`).

**Câu 6.** Java 17 mở client WebSocket qua `HttpClient.send(HttpRequest)` hay API nào?  
**Đáp án:** Qua `HttpClient.newWebSocketBuilder().buildAsync(uri, listener)`. `send/sendAsync` là HTTP request-response API.

**Câu 7.** `WebSocket.Builder.header("Sec-WebSocket-Key", "...")` có phải cách tự chọn Key?  
**Đáp án:** Không. WebSocket protocol headers là nhóm reserved và builder không cho set thủ công theo API; HTTP client tự tạo Key.

**Câu 8.** Sau `buildAsync` thành công, gọi `sendText("hello",true)`; Future completed có nghĩa server đã commit một lệnh?  
**Đáp án:** Không. Future phản ánh send operation phía WebSocket API, không phải ACK nghiệp vụ.

**Câu 9.** Listener đã mở nhưng `onText` không đến, trong khi server đã gửi dữ liệu. Cần xem gì?  
**Đáp án:** Kiểm tra `onOpen` đã gọi `request(n)` chưa và state onError/onClose, rồi mới xem network/protocol.

**Câu 10.** `onText(ws, data, false)` có nên parse ngay như một JSON message hoàn chỉnh?  
**Đáp án:** Không mặc định. `last=false` nghĩa chưa phải fragment cuối, cần ghép đúng context và giới hạn kích thước.

**Câu 11.** Client→server frames có bắt buộc masking không, và mask có mã hóa bí mật không?  
**Đáp án:** Bắt buộc MASK=1 và dùng mask key XOR theo RFC 6455; masking không phải encryption, nên secrets cần `wss`.

**Câu 12.** `Sec-WebSocket-Protocol` server trả tên không nằm trong danh sách client đề nghị có hợp lệ?  
**Đáp án:** Không. Subprotocol phải nằm trong offer hợp lệ; Java client có thể từ chối handshake không hợp lệ.

**Câu 13.** Vì sao browser gửi `Origin` nhưng server không được dùng Origin làm bằng chứng nhận dạng user?  
**Đáp án:** Origin dùng để đánh giá nguồn kết nối browser; non-browser client có thể giả header. Cần auth/authorization riêng.

**Câu 14.** `WebSocket.Builder.connectTimeout(5s)` có nghĩa WebSocket tự đóng sau 5 giây?  
**Đáp án:** Không. Nó giới hạn thiết lập kết nối/handshake, không phải session lifetime.

**Câu 15.** `wss://example.test` dùng certificate không khớp hostname. Nên vô hiệu certificate validation để chạy không?  
**Đáp án:** Không. Phải sửa certificate/truststore/hostname, không hạ bảo mật để che lỗi.

**Câu 16.** Khi WebSocket đã đóng bất thường, client reconnect có tự nhận lại toàn bộ messages bị lỡ?  
**Đáp án:** Không. Cần resume cursor/replay history/application ACK riêng nếu nghiệp vụ yêu cầu.

**Câu 17.** `sendClose(1000,"")` khác `abort()` ra sao?  
**Đáp án:** `sendClose` cố thực hiện orderly close handshake; `abort` đóng đột ngột, thường dành cho lỗi/force cleanup.

**Câu 18.** Nếu server trả `401`/`403` trong opening handshake, có một WebSocket để gửi message sửa lỗi không?  
**Đáp án:** Không. Handshake chưa hoàn tất; client xử lý HTTP handshake/auth failure rồi khởi tạo kết nối mới khi đã đủ điều kiện.

**Câu 19.** `wss` qua proxy TLS termination có bảo đảm backend leg cũng dùng TLS không?  
**Đáp án:** Không. Phải kiểm tra cấu hình từng chặng; HTTPS/WSS ngoài cùng không tự bảo đảm backend encrypted.

**Câu 20.** Khi nào cần implement `WebSocket server` bằng framework khác Java `HttpClient`?  
**Đáp án:** Khi server phải nhận nhiều WebSocket connections, quản lý upgrade, authentication, frames, resource limits và app protocol. `java.net.http.WebSocket` của Java 17 là client API.

## 18. Tóm tắt và tài liệu chuẩn

- `ws` là WebSocket không có TLS; `wss` dùng TLS. Cổng mặc định lần lượt **80** và **443**; port có thể được chỉ định khác.
- Classic RFC 6455: **HTTP/1.1 GET Upgrade → server HTTP 101 hợp lệ → WebSocket frames**. Header `Sec-WebSocket-Accept` phải được tính chính xác từ `Sec-WebSocket-Key` và GUID.
- `Sec-WebSocket-Key`/Accept **không phải authentication hoặc encryption**.
- Java 17 dùng **`HttpClient.newWebSocketBuilder().buildAsync(uri, listener)`**; `HttpClient.send/sendAsync` không phải API để tự xử lý WebSocket session.
- `WebSocket.Builder` quản lý handshake configuration, optional headers và subprotocols; `WebSocket` gửi text/binary/ping/pong/close; `WebSocket.Listener` nhận callbacks.
- **`request(n)` là demand cho callbacks**, không phải gửi một HTTP request và không cam kết n messages hoàn chỉnh.
- Client frames **phải mask**, server frames **không mask**; mask không thay TLS.
- `sendText` hoàn tất không phải business ACK; kết nối lâu dài cần resource limits, heartbeat, reconnect, timeout và correlation/idempotency riêng.
- Handshake thất bại bởi HTTP 403/401/404, TLS error, 101 sai Accept hoặc lỗi proxy; không bỏ kiểm tra để “ép connect”.
- Bài thực hành dùng loopback `ws` để thấy rõ handshake; **production dùng `wss`** và kiểm soát TLS, Origin, authentication, subprotocol và authorization.

### Tài liệu tham khảo

- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html), đặc biệt Sections 3–5, 7 và 10.
- [RFC 8441 — Bootstrapping WebSockets with HTTP/2](https://www.rfc-editor.org/rfc/rfc8441.html), cơ chế extended CONNECT khác HTTP/1.1 Upgrade.
- [Java 17 `HttpClient` — tạo WebSocket Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Java 17 `WebSocket.Builder` — `header`, `connectTimeout`, `subprotocols`, `buildAsync`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html).
- [Java 17 `WebSocket` — `sendText`, `request`, `sendClose`, `abort`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html).
- [Java 17 `WebSocket.Listener` — callbacks, fragments và demand](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html).
- [Java 17 `WebSocketHandshakeException` — failed handshake HTTP response](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocketHandshakeException.html).
