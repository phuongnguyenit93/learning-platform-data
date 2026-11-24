# Handshake: thiết lập kết nối WebSocket và xác minh an toàn

## 1. WebSocket handshake là gì?

**WebSocket handshake** là bước bắt đầu một kết nối WebSocket. Browser gửi yêu cầu mở kết nối tới server, hai phía thương lượng việc chuyển từ HTTP sang giao thức WebSocket, xác nhận các tham số bắt tay và chỉ bắt đầu trao đổi frame khi handshake thành công.

Trong ứng dụng browser, code thường tạo kết nối bằng:

~~~js
const socket = new WebSocket("wss://realtime.example.test/chat");
~~~

Lời gọi này không gửi một HTTP request thông thường để lấy JSON. Browser bắt đầu một quy trình mở WebSocket, thường dùng HTTP/1.1 Upgrade hoặc cơ chế Extended CONNECT khi kết nối qua HTTP/2 hay HTTP/3. Sau khi handshake thành công, kết nối trở thành kênh hai chiều tồn tại lâu hơn một request/response thông thường.

Handshake có ý nghĩa bảo mật vì đây là thời điểm server quyết định có chấp nhận một client kết nối hay không. Server cần xác minh endpoint, origin của trang, session hoặc cơ chế xác thực, subprotocol được yêu cầu và các giới hạn tài nguyên trước khi cho phép client sử dụng kênh.

Bài học thuộc chương **WebSocket** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module phân tích ranh giới bảo mật giữa browser, origin, cookie và ứng dụng web; nghiên cứu Same-Origin Policy, CORS, XSS, CSRF, CSP, Trusted Types và security headers. Bài này tập trung vào handshake: cấu trúc request/response, HTTP Upgrade, WebSocket key/accept, Origin validation, subprotocol, extension, WSS/TLS, cookie authentication, Cross-Site WebSocket Hijacking và cách kiểm tra handshake thực tế.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả quá trình mở WebSocket từ browser tới server.
2. Đọc request và response handshake của HTTP/1.1.
3. Giải thích vai trò của Upgrade, Connection, Sec-WebSocket-Key, Sec-WebSocket-Version và Sec-WebSocket-Accept.
4. Phân biệt HTTP/1.1 Upgrade với HTTP/2 và HTTP/3 Extended CONNECT.
5. Hiểu vai trò của WSS, TLS, hostname và certificate.
6. Xác minh Origin ở server và phân biệt Origin validation với authentication.
7. Phân biệt WebSocket handshake với CORS và preflight.
8. Hiểu cookie, SameSite và nguy cơ Cross-Site WebSocket Hijacking.
9. Thương lượng subprotocol và extension an toàn.
10. Cấu hình reverse proxy và timeout cho kết nối WebSocket.
11. Chẩn đoán handshake thất bại bằng DevTools và server logs.
12. Xây dựng checklist kiểm tra trước khi đưa WebSocket endpoint vào production.

## 2. Luồng mở kết nối

Một WebSocket connection thường bắt đầu từ một trang web đang chạy trong browser:

~~~js
const socket = new WebSocket("wss://realtime.example.test/events");
~~~

Ở mức khái quát, các bước là:

~~~mermaid
sequenceDiagram
    participant P as Trang web
    participant B as Browser
    participant S as WebSocket server
    P->>B: new WebSocket(wss URL)
    B->>B: Kiểm tra URL và browser policy
    B->>S: Opening handshake qua TLS/HTTP
    S->>S: Kiểm tra handshake, Origin và xác thực
    alt Handshake hợp lệ
        S-->>B: Chấp nhận và thương lượng protocol
        B->>P: Phát open event
        P->>S: Gửi WebSocket message
        S-->>P: Gửi WebSocket message
    else Handshake bị từ chối
        S-->>B: HTTP error hoặc từ chối kết nối
        B->>P: Phát error/close theo kết quả
    end
~~~

Browser che giấu nhiều chi tiết của opening handshake khỏi JavaScript. Ứng dụng tạo WebSocket object, đăng ký event và nhận trạng thái kết nối; browser tự xây dựng các header dành riêng cho handshake.

### 2.1. Handshake xảy ra trước khi có WebSocket message

Trước khi handshake hoàn tất, client và server vẫn đang trao đổi ở lớp HTTP transport/handshake. Chỉ sau khi nâng cấp thành công, hai phía mới trao đổi WebSocket frame.

Không gửi dữ liệu ứng dụng như chat message hoặc subscription trước khi socket phát open. Nếu handshake thất bại, các event message không thể được dùng như thể kết nối đã sẵn sàng.

### 2.2. Handshake không phải xác thực người dùng hoàn chỉnh

Một handshake thành công chứng minh hai phía đã thiết lập được WebSocket protocol theo cơ chế tương ứng. Nó không tự chứng minh user được phép đọc mọi channel, room hoặc record.

Server vẫn phải xác thực danh tính, kiểm tra authorization cho từng thao tác và giới hạn những channel mà session hiện tại được phép subscribe.

## 3. URL ws:// và wss://

WebSocket dùng hai scheme URL:

| Scheme | Ý nghĩa | Transport thông thường |
| --- | --- | --- |
| ws:// | WebSocket không mã hóa ở tầng transport | HTTP/1.1 Upgrade trên kết nối không TLS hoặc Extended CONNECT qua HTTP không TLS nếu môi trường hỗ trợ. |
| wss:// | WebSocket qua TLS | HTTPS/TLS và WebSocket handshake được bảo vệ bằng TLS. |

Ví dụ:

~~~js
const socket = new WebSocket("wss://realtime.example.test/chat");
~~~

Trong production, trang HTTPS nên dùng WSS. Một kết nối ws không mã hóa có thể bị nghe lén hoặc sửa đổi trên đường truyền và thường bị browser chặn khi khởi tạo từ secure page như mixed content.

### 3.1. Port mặc định

URL ws thường dùng port 80 khi không chỉ định port; wss thường dùng port 443. Có thể chỉ định port riêng:

~~~js
const socket = new WebSocket("wss://realtime.example.test:8443/chat");
~~~

Port là một phần của origin. Nếu ứng dụng dùng nhiều port, cần cấu hình allowlist và routing tương ứng; không coi cùng hostname là cùng origin trong mọi trường hợp.

### 3.2. URL path và query

Path thường xác định endpoint hoặc loại dịch vụ:

~~~js
const socket = new WebSocket(
  "wss://realtime.example.test/ws/notifications"
);
~~~

Query có thể truyền thông tin định tuyến hoặc một ticket ngắn hạn, nhưng URL thường xuất hiện trong access log, proxy log, monitoring và công cụ debug. Không đặt password, access token dài hạn hoặc session secret vào query string.

## 4. HTTP/1.1 opening handshake

Với HTTP/1.1, browser thường gửi một GET request có các header yêu cầu nâng cấp giao thức. Ví dụ minh họa:

~~~http
GET /chat HTTP/1.1
Host: realtime.example.test
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example.test
Sec-WebSocket-Protocol: chat.v2
~~~

Request thực tế có thể có thêm cookie, header do browser quản lý và các extension được thương lượng. Giá trị key trong ví dụ là giá trị minh họa từ mẫu giao thức; browser tạo key cho handshake thực tế.

Các thành phần quan trọng:

- GET: method của opening handshake HTTP/1.1.
- Host: hostname đích theo HTTP/1.1.
- Upgrade: yêu cầu chuyển sang websocket.
- Connection: Upgrade: đánh dấu header Upgrade là hop-by-hop và yêu cầu chuyển giao thức.
- Sec-WebSocket-Key: nonce Base64 do client tạo cho handshake.
- Sec-WebSocket-Version: phiên bản WebSocket protocol; giá trị phổ biến hiện nay là 13.
- Origin: origin của trang khởi tạo kết nối trong browser.
- Sec-WebSocket-Protocol: danh sách subprotocol client muốn dùng, nếu có.

### 4.1. Vì sao có Upgrade và Connection?

HTTP/1.1 Upgrade cho phép hai phía thương lượng chuyển kết nối hiện tại sang một giao thức khác. Header Upgrade nêu giao thức muốn chuyển; Connection: Upgrade đánh dấu yêu cầu chuyển giao thức trên connection đó.

Các header Connection và Upgrade là hop-by-hop trong HTTP/1.1. Reverse proxy phải xử lý và chuyển đổi chúng đúng cách; không nên coi chúng là header end-to-end được tự động chuyển nguyên vẹn qua mọi proxy.

### 4.2. Sec-WebSocket-Version

Sec-WebSocket-Version cho server biết phiên bản protocol client yêu cầu. Browser hiện đại sử dụng version 13 theo RFC 6455.

Nếu server không hỗ trợ version được yêu cầu, server có thể từ chối và thông báo các version được hỗ trợ theo quy tắc protocol. Không tự thay version trong JavaScript; browser quản lý header này.

### 4.3. Sec-WebSocket-Key

Sec-WebSocket-Key là một nonce được mã hóa Base64. Theo RFC 6455, giá trị này biểu diễn 16 byte ngẫu nhiên.

Key không phải password, bearer token hoặc secret xác thực người dùng. Nó tham gia vào phép tính Sec-WebSocket-Accept để server chứng minh response thuộc quy trình WebSocket handshake, giúp tránh nhầm một response HTTP thông thường với response chấp nhận WebSocket.

## 5. HTTP/1.1 response: 101 Switching Protocols

Nếu server chấp nhận opening handshake HTTP/1.1, response điển hình là:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
Sec-WebSocket-Protocol: chat.v2
~~~

Các thành phần:

- 101 Switching Protocols: server chấp nhận chuyển giao thức.
- Upgrade: websocket: xác nhận protocol đích.
- Connection: Upgrade: xác nhận chuyển đổi connection.
- Sec-WebSocket-Accept: giá trị phản hồi được tính từ key của client.
- Sec-WebSocket-Protocol: subprotocol được server chọn nếu hai phía đã thương lượng.

Sau response hợp lệ, kết nối HTTP/1.1 được nâng thành WebSocket. Các byte tiếp theo thuộc framing của WebSocket, không còn là một chuỗi HTTP request/response thông thường.

### 5.1. 101 không có nghĩa mọi cấu hình bảo mật đều đúng

Server có thể trả 101 nhưng vẫn có lỗi ở lớp ứng dụng, ví dụ chấp nhận Origin không tin cậy, gắn session sai user hoặc cho phép subscribe vào channel trái phép.

Kiểm tra handshake phải bao gồm Origin, authentication, subprotocol và authorization policy, không chỉ nhìn status 101.

### 5.2. Response phải khớp protocol đã yêu cầu

Server không được tự chọn một subprotocol tùy ý mà client không đề nghị. Nếu response có Sec-WebSocket-Protocol, giá trị phải là một protocol đã được client gửi trong danh sách yêu cầu.

Browser có thể từ chối handshake nếu response không tuân thủ quy tắc thương lượng.

## 6. Tính Sec-WebSocket-Accept

Server tính Sec-WebSocket-Accept từ giá trị Sec-WebSocket-Key nhận được bằng cách nối key với GUID cố định của WebSocket, tính SHA-1 trên chuỗi byte kết quả rồi Base64 encode digest.

GUID theo RFC 6455:

~~~text
258EAFA5-E914-47DA-95CA-C5AB0DC85B11
~~~

Công thức khái quát:

~~~text
Sec-WebSocket-Accept =
  Base64(SHA-1(Sec-WebSocket-Key + GUID))
~~~

Ví dụ Node.js minh họa phép tính:

~~~js
import { createHash } from "node:crypto";

function computeWebSocketAccept(key) {
  const guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

  return createHash("sha1")
    .update(key + guid, "ascii")
    .digest("base64");
}

console.log(
  computeWebSocketAccept("dGhlIHNhbXBsZSBub25jZQ==")
);
// s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
~~~

Đây là ví dụ minh họa phía server. Trong production, nên dùng thư viện WebSocket đã được kiểm thử để xử lý handshake, framing, masking, control frame và edge case.

### 6.1. SHA-1 ở đây không phải chữ ký bảo mật

Việc dùng SHA-1 trong phép tính accept không có nghĩa WebSocket đang dùng SHA-1 để xác thực user hoặc bảo vệ tính toàn vẹn của dữ liệu ứng dụng. Giá trị accept là phép xác nhận protocol handshake theo RFC.

Bảo mật dữ liệu truyền tải của WSS đến từ TLS; xác thực user và quyền truy cập do cơ chế authentication/authorization của ứng dụng thực hiện.

### 6.2. Không tự triển khai handshake chỉ bằng cách so sánh key

Server cần kiểm tra đầy đủ phương thức, header, version, key format, Origin, subprotocol và các điều kiện protocol. Chỉ tính đúng accept không làm một endpoint trở nên an toàn.

## 7. HTTP/2 và HTTP/3: Extended CONNECT

HTTP/2 và HTTP/3 không dùng cơ chế HTTP/1.1 Connection: Upgrade như trên. Các connection-specific header như Connection và Upgrade không được dùng trong HTTP/2/3 theo cách của HTTP/1.1.

WebSocket có thể được khởi tạo qua **Extended CONNECT**:

- HTTP/2 dùng cơ chế được định nghĩa trong RFC 8441.
- HTTP/3 dùng cơ chế được định nghĩa trong RFC 9220.

Trong Extended CONNECT, client dùng pseudo-header :method với giá trị CONNECT và :protocol với giá trị websocket, cùng :scheme, :authority, :path và các header WebSocket cần thiết theo RFC. Client/server cần thương lượng hỗ trợ Extended CONNECT bằng SETTINGS_ENABLE_CONNECT_PROTOCOL trước khi dùng cơ chế này.

Ví dụ khái quát về trường thông tin HTTP/2:

~~~text
:method: CONNECT
:protocol: websocket
:scheme: https
:authority: realtime.example.test
:path: /chat
sec-websocket-version: 13
origin: https://app.example.test
~~~

Đây là biểu diễn logic các field, không phải cú pháp HTTP/1.1 dạng văn bản trên wire. HTTP/2/3 dùng framing và header compression riêng. **Sec-WebSocket-Key và Sec-WebSocket-Accept không được dùng trong Extended CONNECT**; cơ chế CONNECT và response status 200 thay cho phép bắt tay 101 của HTTP/1.1. Subprotocol và extension vẫn có thể được thương lượng bằng các header tương ứng nếu cần.

### 7.1. Status thành công khác HTTP/1.1

Với HTTP/1.1, server chấp nhận Upgrade bằng status 101. Với Extended CONNECT trên HTTP/2 hoặc HTTP/3, response thành công dùng status 200 theo cơ chế tương ứng; response không gửi Sec-WebSocket-Accept.

Vì vậy, không kết luận WebSocket handshake thất bại chỉ vì Network panel không hiển thị 101 khi kết nối được thiết lập qua HTTP/2/3.

### 7.2. Browser API che giấu transport

Code JavaScript vẫn có thể dùng:

~~~js
const socket = new WebSocket("wss://realtime.example.test/chat");
~~~

Browser và hạ tầng chọn transport/protocol phù hợp theo khả năng hỗ trợ. Ứng dụng không tự viết pseudo-header hoặc chuyển HTTP/1.1 Upgrade thành Extended CONNECT trong JavaScript.

Reverse proxy, load balancer và WebSocket server cần hỗ trợ đúng cơ chế HTTP version mà hạ tầng sử dụng.

## 8. Origin header trong handshake

Khi browser khởi tạo WebSocket từ một trang, browser gửi Origin để chỉ origin của trang khởi tạo. Ví dụ:

~~~http
Origin: https://app.example.test
~~~

Origin gồm scheme, host và port. Server dùng header này để quyết định trang nào được phép mở kết nối tới endpoint.

Đây là một kiểm soát quan trọng vì WebSocket có thể được mở từ một trang khác origin. Server không nên giả định chỉ vì client biết URL endpoint thì nó được phép kết nối.

### 8.1. Allowlist Origin chính xác

Ví dụ server-side pseudocode:

~~~js
const allowedOrigins = new Set([
  "https://app.example.test",
  "https://admin.example.test"
]);

function isAllowedOrigin(origin) {
  return allowedOrigins.has(origin);
}
~~~

Kiểm tra exact origin đã parse và chuẩn hóa theo định dạng Origin. Không dùng kiểm tra chuỗi kiểu endsWith("example.test") vì giá trị như attacker-example.test hoặc example.test.attacker.invalid có thể vượt qua logic sai.

Nếu cần subdomain pattern, parse URL và kiểm tra hostname theo ranh giới domain chính xác, đồng thời kiểm tra scheme và port.

### 8.2. Không phản chiếu Origin tùy tiện

Không trả lời hoặc chấp nhận mọi Origin chỉ vì header có mặt. Không dùng Origin từ request làm allowlist động. So sánh với danh sách tin cậy được cấu hình ở server.

Nếu ứng dụng không hỗ trợ browser origin null, từ chối giá trị null. Trường hợp file URL, sandbox hoặc opaque origin cần được đánh giá riêng thay vì chấp nhận chung.

### 8.3. Origin không phải danh tính user

Origin cho biết trang browser khởi tạo kết nối thuộc origin nào. Nó không chứng minh người dùng đã đăng nhập, không xác định tenant và không cấp quyền vào room.

Một client không phải browser có thể tự tạo header Origin. Vì vậy, Origin validation là kiểm soát chống kết nối từ trang web không tin cậy trong browser threat model; nó không thay authentication.

## 9. WebSocket khác CORS như thế nào?

WebSocket opening handshake không đi qua CORS Fetch flow giống fetch() hoặc XMLHttpRequest. Browser không thực hiện CORS preflight OPTIONS cho WebSocket handshake và server không dùng Access-Control-Allow-Origin để cấp quyền đọc WebSocket theo cách của Fetch.

Tuy nhiên, điều đó không có nghĩa WebSocket không có ranh giới bảo mật:

- Browser gửi Origin trong handshake.
- Server cần kiểm tra Origin bằng allowlist.
- Cookie có thể được gửi theo cookie policy của browser.
- Authentication và authorization vẫn cần.
- CSP connect-src có thể giới hạn endpoint WebSocket từ trang.

### 9.1. Không dùng Access-Control-Allow-Origin để bảo vệ WebSocket

Thêm header:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

không thay cho kiểm tra Origin trong WebSocket handshake. Server phải tự xác minh Origin trước khi chấp nhận kết nối.

### 9.2. SOP không đồng nghĩa browser chặn mọi WebSocket cross-origin

Một trang có thể thử mở WebSocket tới origin khác. Khả năng được kết nối phụ thuộc server chấp nhận hay từ chối handshake và các policy browser liên quan.

Vì thế, server phải có allowlist Origin và authentication. Đừng cho rằng SOP tự động chặn mọi kết nối WebSocket khác origin như cách script bị hạn chế đọc response Fetch.

### 9.3. CSP connect-src vẫn có liên quan

Document có thể dùng CSP:

~~~http
Content-Security-Policy: default-src 'self'; connect-src 'self' wss://realtime.example.test
~~~

connect-src giới hạn endpoint mà trang được phép kết nối. Đây là lớp kiểm soát phía browser; server vẫn phải xác minh Origin và user.

## 10. Cross-Site WebSocket Hijacking (CSWSH)

**Cross-Site WebSocket Hijacking** xảy ra khi một website độc hại mở WebSocket tới server của ứng dụng nạn nhân trong browser đã đăng nhập, và server chấp nhận kết nối dựa vào cookie session mà không xác minh Origin thích hợp.

Một luồng tấn công khái quát:

~~~mermaid
sequenceDiagram
    participant V as Người dùng đã đăng nhập
    participant A as Trang độc hại
    participant B as Browser
    participant S as WebSocket server
    V->>B: Đăng nhập app.example.test
    V->>B: Mở attacker.example.test
    A->>B: new WebSocket(wss://app.example.test/ws)
    B->>S: Handshake kèm cookie nếu cookie policy cho phép
    Note over S: Server không kiểm tra Origin
    S-->>B: Chấp nhận kết nối
    A->>S: Gửi message qua socket
    S-->>A: Có thể trả dữ liệu của phiên nạn nhân
~~~

Kẻ tấn công có thể dùng quyền session của browser để thực hiện hành động hoặc đọc dữ liệu mà user được phép truy cập, tùy API WebSocket của server.

### 10.1. Kiểm tra Origin là biện pháp quan trọng

Server cần so sánh Origin với allowlist cho ứng dụng. Với browser client, từ chối origin không được phép trước khi nâng cấp kết nối.

Không chỉ kiểm tra Referer; header Origin là tín hiệu phù hợp hơn cho WebSocket opening handshake. Không chấp nhận mọi Origin để “hỗ trợ nhiều frontend” mà không có danh sách tin cậy.

### 10.2. SameSite cookie giúp giảm rủi ro nhưng không thay kiểm tra Origin

SameSite có thể hạn chế cookie trong một số cross-site context. Tuy nhiên, hành vi phụ thuộc browser, cookie configuration, site relationship và các trường hợp đặc biệt. Hai subdomain cùng site nhưng khác origin có thể vẫn thuộc same-site context.

Do đó, SameSite là lớp phòng vệ bổ sung. Hãy kết hợp Origin allowlist, authentication và authorization server-side.

### 10.3. Không cho phép hành động trước authentication

Nếu xác thực diễn ra qua message đầu tiên sau khi socket mở, server phải đặt connection ở trạng thái unauthenticated và không cho phép subscribe, đọc dữ liệu hoặc thực hiện action trước khi xác thực thành công.

Đặt timeout ngắn cho giai đoạn xác thực, giới hạn message size và đóng socket nếu client không xác thực hoặc gửi message sai protocol.

## 11. Authentication trong browser WebSocket

WebSocket constructor trong browser có dạng:

~~~js
new WebSocket(url, protocols);
~~~

API không cung cấp tùy chọn headers tùy chỉnh giống fetch(). Script không thể tự đặt Authorization, Cookie, Origin, Host hoặc các Sec-WebSocket-* handshake headers bị browser quản lý.

Vì vậy, thiết kế authentication phải phù hợp với browser API và cookie policy.

### 11.1. Session cookie

Một lựa chọn là dùng cookie session được thiết lập qua HTTPS:

~~~http
Set-Cookie: session=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Browser có thể gửi cookie phù hợp trong handshake theo cookie scope và privacy policy. Server cần:
- Xác minh session còn hiệu lực.
- Kiểm tra Origin.
- Xác định user/tenant từ session phía server.
- Áp dụng authorization cho mỗi message/action.
- Hết hạn hoặc đóng connection khi session bị revoke.

Không coi cookie đã gửi là bằng chứng đủ để bỏ qua kiểm tra Origin hoặc quyền tài nguyên.

### 11.2. Ticket ngắn hạn

Một kiến trúc khác là cấp ticket dùng một lần hoặc thời hạn rất ngắn qua HTTPS sau khi xác thực user, rồi dùng ticket để mở WebSocket.

Nếu ticket được truyền trong query string, phải hiểu URL có thể xuất hiện trong access log, proxy log, telemetry và DevTools. Dùng ticket:
- Có thời hạn rất ngắn.
- Chỉ dùng một lần.
- Gắn với user, audience và endpoint cụ thể.
- Không cấp quyền rộng hơn nhu cầu.
- Redact query trong logs.
- Thu hồi hoặc đánh dấu đã dùng sau khi handshake thành công.

Không đặt access token dài hạn hoặc refresh token trong query string.

### 11.3. Token trong subprotocol không phải lựa chọn mặc định

Một số hệ thống dùng Sec-WebSocket-Protocol để mang thông tin xác thực vì browser cho phép truyền danh sách subprotocol. Cách này làm lẫn thương lượng protocol với credential và có thể khiến token xuất hiện trong log hoặc tooling.

Chỉ cân nhắc khi có thiết kế protocol rõ, token ngắn hạn và log redaction. Không coi subprotocol là cơ chế xác thực được browser cung cấp sẵn.

### 11.4. Xác thực qua message đầu tiên

Client có thể mở socket rồi gửi message auth:

~~~js
socket.addEventListener("open", () => {
  socket.send(JSON.stringify({
    type: "AUTH",
    token: shortLivedToken
  }));
});
~~~

Server phải giữ socket ở trạng thái chưa xác thực cho đến khi xác minh token. Không xử lý các message nghiệp vụ trước đó; giới hạn thời gian, kích thước và số lần auth thất bại.

Token vẫn được truyền qua WebSocket connection nên cần WSS. Tránh log message payload chứa token và không dùng token dài hạn.

## 12. Subprotocol negotiation

Subprotocol cho phép hai phía thống nhất giao thức ứng dụng chạy trên WebSocket. Client có thể đề nghị một hoặc nhiều protocol:

~~~js
const socket = new WebSocket(
  "wss://realtime.example.test/chat",
  ["chat.v2", "chat.v1"]
);
~~~

Browser gửi danh sách trong Sec-WebSocket-Protocol. Server chọn tối đa một protocol mà client đã đề nghị và phản hồi bằng cùng header.

Sau khi mở:

~~~js
socket.addEventListener("open", () => {
  console.log("Subprotocol:", socket.protocol);
});
~~~

Nếu không có subprotocol được chọn, socket.protocol có thể là chuỗi rỗng.

### 12.1. Dùng subprotocol để version hóa message

Ví dụ:
- chat.v1: message schema cũ.
- chat.v2: message schema mới.
- notifications.v1: notification event format.

Server cần validate message theo protocol đã chọn. Không chỉ dựa vào tên subprotocol để cấp quyền user hoặc tenant.

### 12.2. Server không được tự chọn protocol ngoài danh sách

Nếu client yêu cầu chat.v1 và chat.v2, server có thể chọn một trong các giá trị đó. Không tự trả một protocol khác chưa được client đề nghị.

Nếu không có protocol tương thích, từ chối handshake theo thiết kế server thay vì âm thầm dùng schema không tương thích.

## 13. Extension negotiation

WebSocket extensions mở rộng cách framing hoặc truyền dữ liệu. Extension thường được đề nghị qua Sec-WebSocket-Extensions.

Một extension phổ biến là permessage-deflate, cho phép nén message:

~~~http
Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits
~~~

Server có thể thương lượng các tham số được hỗ trợ và trả extension đã chọn. Không được tự bật extension ngoài danh sách client đề nghị.

### 13.1. Compression và side-channel

Nén có thể giảm băng thông nhưng cũng cần đánh giá rủi ro khi secret và dữ liệu do attacker kiểm soát cùng tham gia một context nén. Trong một số mô hình, kích thước dữ liệu nén có thể tiết lộ thông tin.

Với message chứa token/secret, đánh giá việc tắt compression hoặc cấu hình no-context-takeover phù hợp. Không bật compression chỉ vì tiết kiệm băng thông mà không hiểu dữ liệu nào được nén cùng nhau.

### 13.2. Giới hạn extension

Chỉ bật extension thực sự cần. Kiểm tra thư viện server, proxy và browser tương thích. Extension không thay authentication, authorization hoặc TLS.

## 14. WSS và TLS trong handshake

WSS bảo vệ kết nối WebSocket bằng TLS. Trước khi dữ liệu WebSocket được trao đổi, browser thiết lập TLS tới hostname đích và xác minh certificate theo quy tắc browser.

Các yếu tố cần kiểm tra:

- Certificate còn hạn và có SAN khớp hostname.
- Certificate chain được browser tin cậy.
- TLS configuration phù hợp.
- DNS và SNI dẫn tới endpoint đúng.
- Reverse proxy không downgrade kết nối ngoài dự kiến.
- Redirect và endpoint URL đều dùng WSS trong production.

### 14.1. WSS bảo vệ đường truyền, không xác thực user

TLS xác thực server endpoint và bảo vệ tính bí mật/toàn vẹn trên đường truyền. Nó không chứng minh người dùng đã đăng nhập hoặc được phép subscribe channel.

Authentication và authorization vẫn là trách nhiệm của ứng dụng.

### 14.2. Không downgrade về ws

Nếu WSS handshake lỗi do certificate hoặc cấu hình TLS, không tự động fallback sang ws. Sửa certificate, hostname, proxy hoặc endpoint. Fallback không mã hóa có thể làm lộ session và nội dung realtime.

## 15. Cookie và credential trong handshake

Browser có thể đính kèm cookie phù hợp với URL WebSocket theo cookie store và các chính sách browser. WebSocket API không có thuộc tính credentials để developer chọn same-origin/include/omit như Fetch.

Cookie có thể bị ảnh hưởng bởi:
- Domain và Path.
- Secure.
- SameSite.
- Expiration.
- Partitioning và third-party cookie restrictions.
- Browser privacy settings.

Không giả định cookie luôn được gửi chỉ vì user đang đăng nhập ở tab khác. Kiểm tra cookie scope và chính sách thực tế.

### 15.1. Cookie HttpOnly

HttpOnly ngăn JavaScript trang đọc cookie bằng document.cookie. Browser vẫn có thể tự gửi cookie trong handshake phù hợp.

HttpOnly giảm khả năng XSS đánh cắp trực tiếp session cookie, nhưng XSS vẫn có thể tạo WebSocket cùng origin trong session của user nếu không có biện pháp khác. Phòng vệ XSS và authorization server-side vẫn cần thiết.

### 15.2. Session hết hạn khi socket đang mở

Handshake chỉ xác minh session tại thời điểm mở kết nối. Session có thể hết hạn hoặc bị revoke trong lúc WebSocket vẫn tồn tại.

Server cần chiến lược:
- Kiểm tra session khi xử lý message nhạy cảm.
- Đóng socket khi session bị revoke hoặc user logout.
- Giới hạn thời gian sống connection nếu phù hợp.
- Revalidate quyền khi user đổi tenant/role.
- Không để connection sống mãi với quyền cũ sau khi account bị khóa.

## 16. Handshake validation ở server

Một server-side validation pipeline có thể theo thứ tự:

1. Parse request target và kiểm tra endpoint.
2. Xác minh phương thức/handshake theo transport HTTP đang dùng.
3. Kiểm tra WebSocket version và key.
4. Kiểm tra Origin bằng allowlist đối với browser client.
5. Xác thực session hoặc ticket.
6. Xác định subprotocol và extension được phép.
7. Áp dụng rate limit và giới hạn kết nối.
8. Chỉ nâng cấp khi mọi điều kiện cần thiết đã đạt.
9. Khởi tạo connection state ở mức quyền tối thiểu.
10. Ghi log kết quả không chứa credential.

Thứ tự triển khai thực tế tùy thư viện và proxy. Điều quan trọng là không nâng cấp trước rồi mới phát hiện Origin hoặc session không hợp lệ nếu có thể từ chối ngay ở handshake.

### 16.1. Origin allowlist phải theo môi trường

Development, staging và production có thể có frontend origin khác nhau. Quản lý allowlist bằng cấu hình theo môi trường, review thay đổi và không dùng wildcard rộng trong production.

Nếu có nhiều tenant custom domain, cần xác minh domain đã được đăng ký và liên kết với tenant ở server; không tin một Origin bất kỳ chỉ vì nó có TLS.

### 16.2. Không dùng Host thay Origin

Host hoặc :authority xác định đích server nhận request; Origin xác định trang browser khởi tạo kết nối. Hai field có mục đích khác nhau.

Server cần kiểm tra routing/host và Origin độc lập. Không dùng Host để suy luận trang nào được phép mở socket.

## 17. Reverse proxy và load balancer

WebSocket thường đi qua reverse proxy, ingress hoặc load balancer. Cấu hình sai có thể làm handshake trả 400/426/502 hoặc socket bị đóng ngay sau khi mở.

Với HTTP/1.1, proxy cần hỗ trợ Upgrade và chuyển đổi các header hop-by-hop đúng cách. Ví dụ cấu hình khái quát trong Nginx:

~~~nginx
location /ws/ {
    proxy_pass http://websocket_backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 3600s;
}
~~~

Đây là ví dụ cấu hình tối thiểu cho một topology cụ thể; cần kiểm tra TLS termination, trusted proxy, header forwarding, timeout và phiên bản HTTP thực tế.

### 17.1. HTTP/2 và HTTP/3 proxying

Khi client tới proxy bằng HTTP/2 hoặc HTTP/3, WebSocket có thể dùng Extended CONNECT. Proxy phải hỗ trợ RFC 8441/RFC 9220 tương ứng và chuyển tiếp đúng tới upstream.

Không thêm Connection: Upgrade vào HTTP/2/3 request. Những header connection-specific kiểu HTTP/1.1 không hợp lệ ở HTTP/2/3.

### 17.2. Trusted forwarded headers

Nếu TLS kết thúc tại proxy, backend có thể nhận thông tin scheme/host gốc qua forwarded headers. Chỉ tin header do proxy được cấu hình tin cậy ghi lại; không tin giá trị client tùy ý gửi.

Không dùng X-Forwarded-For hoặc header tương tự như bằng chứng xác thực user.

### 17.3. Timeout và idle connection

WebSocket có thể tồn tại lâu hơn HTTP request thông thường. Proxy và load balancer cần idle timeout phù hợp. Nếu timeout quá ngắn, socket có thể đóng dù ứng dụng không lỗi.

Ping/pong heartbeat giúp phát hiện kết nối chết và giữ trạng thái hoạt động tùy hạ tầng. Không gửi heartbeat quá dày gây tải không cần thiết.

## 18. Handshake status và lỗi thường gặp

Một số status có thể xuất hiện khi handshake bị từ chối:

| Status | Nguyên nhân có thể |
| --- | --- |
| 101 | HTTP/1.1 handshake được chấp nhận và nâng cấp. |
| 200 | Có thể là thành công với Extended CONNECT trên HTTP/2/3. |
| 400 | Request hoặc handshake không hợp lệ. |
| 401 | Chưa xác thực hoặc credential không hợp lệ. |
| 403 | Origin, user hoặc policy bị từ chối. |
| 404 | Sai path hoặc endpoint không tồn tại. |
| 426 | Server yêu cầu protocol upgrade theo cấu hình; cần đọc response cụ thể. |
| 429 | Rate limit hoặc giới hạn kết nối. |
| 502/503/504 | Proxy/upstream lỗi hoặc không sẵn sàng. |

Status phụ thuộc server và proxy; không phải mọi implementation đều dùng cùng mã cho mọi lỗi.

### 18.1. Browser JavaScript không luôn thấy status handshake

WebSocket API thường phát error/close khi handshake thất bại nhưng không cung cấp đầy đủ response headers/body cho JavaScript như Fetch. DevTools Network và server/proxy logs là nơi phù hợp để điều tra.

Không dựa vào một chuỗi error event tổng quát để kết luận nguyên nhân là CORS.

### 18.2. Close code sau khi handshake

Sau khi WebSocket đã mở, kết nối có thể đóng bằng close frame và close code. Close code thuộc giai đoạn WebSocket protocol sau handshake; nó khác HTTP status của opening handshake.

Không nhầm HTTP 403 lúc bắt tay với WebSocket close code 1008 sau khi kết nối đã thiết lập.

## 19. Browser WebSocket API và giới hạn custom headers

Trong browser, API cơ bản:

~~~js
const socket = new WebSocket(
  "wss://realtime.example.test/events",
  ["events.v1"]
);
~~~

WebSocket constructor không có tham số headers tùy chỉnh. Script không thể đặt trực tiếp:
- Authorization.
- Cookie.
- Origin.
- Host.
- Connection.
- Upgrade.
- Sec-WebSocket-Key.
- Sec-WebSocket-Version.

Browser tự tạo và kiểm soát các header dành riêng cho handshake. Không dùng thư viện frontend với giả định nó có thể thêm custom handshake header trong browser nếu nền tảng không cho phép.

### 19.1. Native client khác browser client

Ứng dụng native hoặc server-side WebSocket client có thể cung cấp API header tùy chỉnh, tùy thư viện. Nhưng server không được áp dụng cùng một trust assumption cho mọi client.

Tách chính sách browser Origin với authentication chung. Native client có thể không gửi Origin hoặc có thể tự đặt Origin; header đó không phải bằng chứng xác thực.

### 19.2. Không chuyển token vào URL chỉ vì thiếu custom header

Không có Authorization header tùy chỉnh trong browser WebSocket API không có nghĩa phải dùng access token dài hạn trong query string. Ưu tiên session cookie an toàn hoặc ticket một lần, thời hạn ngắn, scope hẹp và có log redaction.

## 20. CSP và WebSocket endpoint

Content Security Policy directive connect-src kiểm soát những endpoint trang được phép kết nối, bao gồm WebSocket.

Ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; connect-src 'self' https://api.example.test wss://realtime.example.test
~~~

Nếu thiếu endpoint WSS trong connect-src, browser có thể chặn kết nối trước khi handshake tới server.

Không mở rộng connect-src thành wildcard chỉ để sửa lỗi. Liệt kê đúng scheme và host cần thiết. Kiểm tra CSP violation trong Console.

### 20.1. CSP không thay server Origin validation

CSP là policy browser áp dụng cho document. Client khác hoặc request được tạo ngoài browser không bị CSP của trang đó kiểm soát.

Server vẫn phải xác minh Origin, session và quyền trên handshake. Hai lớp này bổ sung cho nhau.

## 21. Handshake, CSRF và authorization

WebSocket handshake là một HTTP-based opening request và có thể mang cookie session. Nếu server chấp nhận cookie mà không kiểm tra Origin, một website khác có thể mở socket trong browser của user đã đăng nhập.

Do đó:
- Kiểm tra Origin allowlist.
- Dùng cookie SameSite phù hợp.
- Xác thực session/ticket.
- Không cho thao tác nghiệp vụ trước khi authentication hoàn tất.
- Kiểm tra authorization theo từng message/action.
- Đóng socket khi session bị revoke.
- Giới hạn rate và số connection.

CSRF token truyền qua HTTP form/fetch không tự động bảo vệ WebSocket. Nếu thiết kế cần token chống CSWSH, phải xác định cách cấp và xác minh token riêng, đồng thời vẫn kiểm tra Origin.

## 22. Rate limit và resource protection tại handshake

Handshake là điểm có thể bị lạm dụng để tạo nhiều kết nối hoặc tiêu tốn tài nguyên. Server cần kiểm soát:

- Số connection đồng thời theo IP, user, tenant và endpoint.
- Tốc độ mở connection.
- Timeout khi handshake hoặc authentication chưa hoàn tất.
- Kích thước header và URL.
- Message size sau khi socket mở.
- Số lần auth thất bại.
- Idle connection và heartbeat.
- Hành vi reconnect tự động của client.

Rate limit theo IP một mình có thể ảnh hưởng người dùng sau NAT; kết hợp user/session và giới hạn tổng phù hợp.

### 22.1. Không log credential

Log handshake nên ghi endpoint, status, Origin đã chuẩn hóa, subprotocol, correlation ID và lý do từ chối ở mức an toàn. Không log Cookie, Authorization, ticket hoặc token query đầy đủ.

Nếu cần điều tra ticket, dùng identifier không có quyền truy cập thay cho giá trị ticket.

## 23. Ví dụ browser client có xử lý lifecycle

Ví dụ client:

~~~js
const socket = new WebSocket(
  "wss://realtime.example.test/events",
  ["events.v1"]
);

socket.addEventListener("open", () => {
  console.log("WebSocket đã mở:", socket.protocol);
});

socket.addEventListener("message", (event) => {
  // Parse theo schema đã định nghĩa; coi payload là dữ liệu không tin cậy.
  handleRealtimeMessage(event.data);
});

socket.addEventListener("error", () => {
  // Browser không cung cấp đầy đủ chi tiết HTTP handshake qua event này.
  showConnectionError();
});

socket.addEventListener("close", (event) => {
  console.log("WebSocket đóng:", event.code, event.wasClean);
});
~~~

Trong ứng dụng thật:
- Không log payload nhạy cảm.
- Validate schema và kích thước message.
- Xử lý reconnect có backoff/jitter.
- Không gửi command trước khi auth state sẵn sàng.
- Xử lý session expiration và logout.
- Kiểm tra socket.protocol có đúng subprotocol mong muốn.

### 23.1. Reconnect không phải handshake thành công

Khi socket đóng, client có thể thử kết nối lại. Mỗi lần reconnect tạo một handshake mới và cần xác thực lại session, Origin, rate limit và authorization.

Không giả định reconnect tự kế thừa quyền từ socket cũ. Token/ticket một lần có thể đã hết hạn hoặc đã được sử dụng.

## 24. DevTools: kiểm tra opening handshake

Trong Chrome/Chromium DevTools:

1. Mở Network.
2. Chọn bộ lọc WS nếu browser cung cấp.
3. Tạo kết nối WebSocket từ trang.
4. Chọn request tới endpoint.
5. Kiểm tra URL, status và request/response headers.
6. Với HTTP/1.1, tìm Upgrade, Connection, Sec-WebSocket-Key, Sec-WebSocket-Version, Origin và Sec-WebSocket-Accept.
7. Kiểm tra Sec-WebSocket-Protocol và Sec-WebSocket-Extensions nếu có.
8. Xem tab Messages/Frames sau khi kết nối mở.
9. Đối chiếu thời điểm lỗi với server/proxy logs.
10. Không sao chép cookie, ticket hoặc token vào screenshot/ticket hỗ trợ.

Nếu transport là HTTP/2/3, panel có thể hiển thị handshake khác HTTP/1.1 và không có 101. Kiểm tra protocol negotiated và tài liệu browser/proxy khi cần.

### 24.1. Phân biệt handshake error với frame error

- Handshake error: socket chưa mở; kiểm tra HTTP status, Origin, TLS, proxy và authentication.
- Frame/message error: socket đã mở; kiểm tra framing, schema, size, close code và application protocol.
- Network disconnect: kiểm tra proxy timeout, mạng, heartbeat và reconnect.

Phân loại đúng giai đoạn giúp tránh sửa sai lớp.

## 25. Thực hành A — Đọc HTTP/1.1 handshake

Dùng server WebSocket lab và trang HTTPS cùng origin hoặc origin được allowlist. Mở DevTools → Network → WS.

Quan sát request và response handshake. Ghi lại:
- URL và method.
- Upgrade/Connection.
- Sec-WebSocket-Key.
- Sec-WebSocket-Version.
- Origin.
- Sec-WebSocket-Accept.
- Subprotocol được chọn.

Giải thích vì sao 101 xuất hiện trong HTTP/1.1 và vì sao accept không phải token xác thực user. Chỉ dùng dữ liệu test.

## 26. Thực hành B — Từ chối Origin không tin cậy

Cấu hình server lab chỉ chấp nhận:

~~~text
https://app.example.test
~~~

Mở trang lab từ một origin khác và thử tạo WebSocket tới server. Xác minh server từ chối trước khi nâng cấp.

Thử các giá trị gần giống để kiểm tra parser:
- https://app.example.test.attacker.invalid
- https://attacker-app.example.test
- http://app.example.test
- https://app.example.test:8443
- null

Không dùng kiểm tra endsWith hoặc wildcard tùy tiện. Không đưa endpoint production vào bài thử.

## 27. Thực hành C — Cookie và CSWSH trong môi trường lab

Dùng hai origin lab:
- Ứng dụng có cookie session.
- Trang test khác origin.

Trong môi trường tài khoản giả, kiểm tra cookie có được gửi theo policy browser hay không và server có từ chối Origin ngoài allowlist không.

Thử bỏ Origin validation trên server lab để quan sát rủi ro, sau đó khôi phục allowlist. Không thực hiện với tài khoản thật hoặc website bên thứ ba.

Ghi nhận sự khác nhau giữa:
- Cookie SameSite.
- Origin allowlist.
- Authentication session.
- Authorization cho message.

## 28. Thực hành D — Proxy và WSS

Cấu hình reverse proxy staging cho endpoint WebSocket qua WSS. Kiểm tra:
1. TLS certificate và hostname.
2. HTTP/1.1 Upgrade forwarding nếu dùng H1.
3. Extended CONNECT nếu hạ tầng dùng H2/H3 và có hỗ trợ.
4. Origin được chuyển tiếp nguyên vẹn.
5. Timeout và heartbeat.
6. Kết nối không bị fallback sang ws.
7. Handshake thất bại được log không chứa credential.

So sánh lỗi khi thiếu Upgrade forwarding, sai path, Origin bị từ chối và certificate không hợp lệ. Dùng server và tài khoản staging.

## 29. Checklist review WebSocket handshake

- [ ] Dùng wss:// trong production.
- [ ] Certificate hợp lệ, SAN khớp hostname và chain được browser tin cậy.
- [ ] Không fallback từ WSS xuống WS.
- [ ] Endpoint, path, host và port được cấu hình rõ.
- [ ] HTTP/1.1 handshake xử lý đúng GET, Upgrade, Connection và version.
- [ ] Sec-WebSocket-Key được kiểm tra theo protocol; không dùng nó làm credential.
- [ ] Sec-WebSocket-Accept được tính đúng theo RFC 6455.
- [ ] Hiểu HTTP/2 RFC 8441 và HTTP/3 RFC 9220 dùng Extended CONNECT, không dùng H1 Upgrade headers.
- [ ] Không giả định mọi handshake thành công đều phải trả 101.
- [ ] Kiểm tra Origin bằng exact allowlist ở server.
- [ ] Không phản chiếu Origin tùy ý hoặc dùng endsWith không an toàn.
- [ ] Không coi Origin là authentication.
- [ ] Không dùng Access-Control-Allow-Origin thay Origin validation.
- [ ] Hiểu WebSocket không dùng CORS preflight như Fetch.
- [ ] Cấu hình CSP connect-src đúng endpoint WSS.
- [ ] Kiểm tra cookie Domain, Path, Secure, HttpOnly và SameSite.
- [ ] Phòng vệ Cross-Site WebSocket Hijacking.
- [ ] Không xử lý message nghiệp vụ trước authentication.
- [ ] Xác minh authorization cho từng channel/action.
- [ ] Chọn subprotocol từ danh sách client đề nghị.
- [ ] Chỉ bật extension cần thiết và đánh giá compression side-channel.
- [ ] Không đặt access token dài hạn trong URL hoặc subprotocol.
- [ ] Nếu dùng ticket, giới hạn thời gian, một lần, audience và redaction log.
- [ ] Revalidate session và đóng socket khi logout/revoke.
- [ ] Proxy hỗ trợ Upgrade hoặc Extended CONNECT theo transport.
- [ ] Chỉ tin forwarded headers từ proxy tin cậy.
- [ ] Có timeout, rate limit, connection limit và message-size limit.
- [ ] Debug riêng handshake status với WebSocket close code.
- [ ] Không log cookie, ticket, Authorization hoặc payload nhạy cảm.
- [ ] Kiểm tra bằng DevTools và server logs trong staging.

## 30. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “WebSocket luôn trả HTTP 101.” | **Sai** | HTTP/1.1 Upgrade dùng 101; Extended CONNECT trên HTTP/2/3 dùng status 200. |
| “Sec-WebSocket-Key là password.” | **Sai** | Đây là nonce cho phép tính accept trong handshake. |
| “Sec-WebSocket-Accept xác thực user.” | **Sai** | Nó xác nhận quy trình protocol handshake, không cấp danh tính hoặc quyền. |
| “WebSocket dùng CORS preflight như Fetch.” | **Sai** | WebSocket handshake không dùng CORS preflight flow. |
| “Access-Control-Allow-Origin bảo vệ WebSocket.” | **Sai** | Server cần kiểm tra Origin trực tiếp trong handshake. |
| “SOP tự chặn mọi kết nối WebSocket cross-origin.” | **Sai** | Server phải quyết định chấp nhận Origin nào; browser có thể thử mở kết nối. |
| “Origin chứng minh user đã đăng nhập.” | **Sai** | Origin nhận diện trang khởi tạo, không xác thực user. |
| “Origin header không thể giả mạo trong mọi client.” | **Sai** | Native/non-browser client có thể tự tạo header; không dùng nó thay authentication. |
| “SameSite cookie đủ để chống mọi CSWSH.” | **Sai** | SameSite là lớp bổ sung; cần Origin allowlist và xác thực server. |
| “HttpOnly ngăn XSS sử dụng WebSocket.” | **Sai** | XSS có thể tạo socket và browser tự gửi cookie phù hợp. |
| “Browser WebSocket constructor cho phép set Authorization header.” | **Sai** | Browser API không có tham số custom headers. |
| “Đưa token vào query là an toàn vì dùng WSS.” | **Sai** | URL vẫn có thể xuất hiện trong logs và tooling. |
| “Subprotocol là cơ chế authentication.” | **Sai** | Nó thương lượng application protocol, không tự xác thực user. |
| “skip compression luôn làm handshake lỗi.” | **Sai** | Compression extension là tùy chọn thương lượng. |
| “TLS chứng minh user được phép vào room.” | **Sai** | TLS bảo vệ transport; server vẫn cần authorization. |
| “Handshake 101 nghĩa mọi message sau đó đều hợp lệ.” | **Sai** | Server phải validate message, quyền và giới hạn sau khi mở. |
| “Unregister proxy hoặc đổi DNS sẽ đóng mọi socket ngay lập tức.” | **Sai** | Connection đang mở có vòng đời riêng; cần close/revoke và timeout. |

## 31. Tổng kết

WebSocket handshake là bước thương lượng để chuyển từ HTTP sang kết nối hai chiều. Với HTTP/1.1, browser gửi GET cùng Upgrade, Connection, Sec-WebSocket-Key và Sec-WebSocket-Version; server chấp nhận bằng 101 Switching Protocols và Sec-WebSocket-Accept được tính theo RFC 6455. Với HTTP/2 và HTTP/3, WebSocket có thể dùng Extended CONNECT nên response thành công là 200 thay vì 101.

Handshake cũng là ranh giới bảo mật quan trọng. Server cần kiểm tra Origin bằng allowlist, xác thực session hoặc ticket, thương lượng subprotocol/extension hợp lệ và giới hạn tài nguyên. WebSocket không dùng CORS preflight như Fetch, vì vậy Access-Control-Allow-Origin không thay Origin validation. Cookie SameSite và HttpOnly giúp giảm một số rủi ro nhưng không thay authentication, authorization và phòng vệ CSWSH.

Ba nguyên tắc cần nhớ:

1. **Xác minh handshake theo protocol:** phân biệt HTTP/1.1 Upgrade với HTTP/2/3 Extended CONNECT; kiểm tra key/version/accept và subprotocol đúng chuẩn.
2. **Xác minh nguồn và danh tính riêng biệt:** allowlist Origin để chống kết nối từ trang không tin cậy, đồng thời xác thực session/ticket và kiểm tra quyền cho từng message.
3. **Bảo vệ toàn bộ đường truyền và hạ tầng:** dùng WSS, cấu hình proxy đúng transport, quản lý cookie/timeout/rate limit và không ghi credential vào log.

Khi review một WebSocket endpoint, hãy hỏi: **browser đang dùng HTTP/1.1 Upgrade hay Extended CONNECT, response status có phù hợp, Origin có nằm trong allowlist, session đã được xác thực, cookie có được gửi theo policy mong muốn, subprotocol/extension nào được thương lượng, proxy có chuyển tiếp đúng và server có giới hạn quyền trước khi xử lý message không?** Trả lời rõ các câu hỏi này giúp thiết lập WebSocket an toàn ngay từ bước handshake.
