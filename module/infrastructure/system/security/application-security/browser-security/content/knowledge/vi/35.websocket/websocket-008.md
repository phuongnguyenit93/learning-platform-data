# WebSocket abuse: nhận diện và phòng chống lạm dụng kết nối thời gian thực

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Mô tả WebSocket handshake, kết nối ws/wss và vòng đời kết nối lâu dài.
2. Giải thích vì sao Same-Origin Policy và CORS không tự bảo vệ server khỏi Cross-Site WebSocket Hijacking (CSWSH).
3. Xác minh Origin bằng allowlist chính xác và phân biệt kiểm tra Origin với xác thực người dùng.
4. Thiết kế xác thực bằng session, cookie hoặc ticket ngắn hạn mà không làm lộ credential trong URL/log.
5. Kiểm tra quyền trên từng message, validate schema, kích thước và loại dữ liệu.
6. Phòng injection, DOM XSS, replay, message flooding và resource exhaustion.
7. Giới hạn số kết nối, tốc độ message, kích thước frame, hàng đợi và thời gian idle.
8. Thiết kế heartbeat, reconnect, session revocation và xử lý message idempotent.
9. Kết hợp CSP connect-src, TLS, reverse proxy, logging và monitoring để bảo vệ WebSocket endpoint.
10. Kiểm thử các kịch bản lạm dụng trong môi trường staging bằng DevTools và công cụ kiểm thử có kiểm soát.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế. WebSocket mở một kênh giao tiếp hai chiều tồn tại lâu dài, vì vậy cần bảo vệ cả handshake, từng message và toàn bộ vòng đời kết nối.

## 1. WebSocket và bề mặt tấn công

WebSocket là giao thức giao tiếp hai chiều giữa client và server trên một kết nối lâu dài. Sau bước handshake, hai phía có thể gửi message qua lại mà không cần tạo một HTTP request mới cho mỗi lần trao đổi.

Ứng dụng thường dùng WebSocket cho:

- Chat và thông báo thời gian thực.
- Dashboard và cập nhật trạng thái liên tục.
- Game nhiều người chơi.
- Giao dịch hoặc dữ liệu thị trường có tần suất cập nhật cao.
- Công cụ cộng tác, chỉnh sửa đồng thời và giám sát thiết bị.

Một kết nối WebSocket có thể tồn tại lâu hơn một HTTP request thông thường. Điều này tạo ra một số rủi ro riêng:

- Cookie hoặc session có thể hết hạn trong khi socket vẫn đang mở.
- Quyền người dùng có thể thay đổi sau khi handshake.
- Một client có thể gửi message liên tục hoặc payload quá lớn.
- Server phải giữ bộ nhớ, file descriptor, queue và trạng thái cho từng kết nối.
- Kết nối có thể bị giữ mở bởi client chậm hoặc client không còn hoạt động.
- XSS có thể sử dụng quyền của trang để mở socket và gửi message.
- Một trang độc hại có thể thử mở socket tới dịch vụ khác bằng cookie của nạn nhân.

Không chỉ kiểm tra handshake. Mỗi message và mỗi thao tác nghiệp vụ qua socket đều phải được xem là một request cần xác thực, authorization, validation và giới hạn tài nguyên.

## 2. WebSocket handshake hoạt động thế nào?

Trong HTTP/1.1, client thường bắt đầu bằng request Upgrade:

    GET /realtime HTTP/1.1
    Host: socket.example.test
    Upgrade: websocket
    Connection: Upgrade
    Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
    Sec-WebSocket-Version: 13
    Origin: https://app.example.test

Server chấp nhận handshake bằng response tương ứng:

    HTTP/1.1 101 Switching Protocols
    Upgrade: websocket
    Connection: Upgrade
    Sec-WebSocket-Accept: ...

Sau khi handshake thành công, hai bên trao đổi WebSocket frame trên kết nối đó.

Browser có thể khởi tạo kết nối bằng:

    const socket = new WebSocket(
      "wss://socket.example.test/realtime"
    );

URL ws:// không mã hóa transport. Production nên dùng wss:// để bảo vệ dữ liệu và credential trên đường truyền bằng TLS.

### Handshake không phải đăng nhập

HTTP 101 chỉ cho biết server đồng ý chuyển giao thức. Nó không chứng minh người gửi là người dùng hợp lệ hoặc có quyền truy cập channel.

Server phải xác thực trước khi cho phép thao tác nghiệp vụ. Nếu kiến trúc xác thực sau khi socket mở, kết nối phải ở trạng thái chưa xác thực, có timeout ngắn và chỉ được gửi message xác thực đã định nghĩa. Không xử lý message nghiệp vụ trước khi xác thực hoàn tất.

### WebSocket và HTTP/2

WebSocket không phải lúc nào cũng dùng HTTP/1.1 Upgrade. Trên một số kiến trúc HTTP/2, kết nối có thể được thiết lập qua extended CONNECT theo cơ chế hỗ trợ của browser, server và proxy. Không hard-code giả định mọi handshake đều là GET với status 101 khi quan sát hạ tầng nhiều giao thức.

## 3. CSWSH: Cross-Site WebSocket Hijacking

Cross-Site WebSocket Hijacking (CSWSH) xảy ra khi một website do attacker kiểm soát mở WebSocket tới dịch vụ của nạn nhân và browser tự gửi cookie/session phù hợp trong handshake. Nếu server chấp nhận kết nối mà không xác minh Origin và không có CSRF defense thích hợp, trang attacker có thể giao tiếp qua socket dưới danh tính phiên của nạn nhân.

Ví dụ tình huống:

1. Người dùng đăng nhập vào app.example.test.
2. Browser có session cookie hợp lệ cho socket.example.test hoặc domain phù hợp.
3. Người dùng mở trang attacker.example.
4. JavaScript trên trang attacker tạo WebSocket tới dịch vụ realtime của ứng dụng.
5. Nếu cookie được gửi và server không xác minh Origin, kết nối có thể được chấp nhận bằng session của người dùng.
6. Trang attacker có thể gửi message và đọc các message mà server trả về qua socket.

### Vì sao Same-Origin Policy không đủ?

Same-Origin Policy hạn chế script đọc dữ liệu của origin khác qua nhiều API. Tuy nhiên, WebSocket có cơ chế riêng: browser cho phép trang mở kết nối tới WebSocket endpoint cross-origin. Server phải quyết định có chấp nhận Origin gửi tới hay không.

Khi handshake thành công, trang đã mở socket có thể đọc message nhận được trên chính socket đó. Vì vậy, không được giả định Same-Origin Policy sẽ tự chặn CSWSH.

### Vì sao CORS không bảo vệ WebSocket?

WebSocket handshake không dùng cơ chế CORS preflight/response như Fetch hoặc XHR thông thường. Server không thể dựa vào Access-Control-Allow-Origin để thay cho việc kiểm tra Origin.

- Không có CORS preflight OPTIONS tiêu chuẩn cho WebSocket handshake.
- Access-Control-Allow-Origin không phải biện pháp kiểm soát nguồn WebSocket.
- Browser gửi Origin trong handshake; server phải tự xác minh.
- Server vẫn phải xác thực session và authorization.

CORS policy của HTTP API có thể vẫn cần thiết cho các endpoint khác, nhưng không thay thế Origin validation trên WebSocket endpoint.

## 4. Xác minh Origin bằng allowlist chính xác

Browser gửi header Origin trong WebSocket handshake. Server nên so sánh với danh sách origin được phép.

Ví dụ:

    const allowedOrigins = new Set([
      "https://app.example.test",
      "https://admin.example.test"
    ]);

    function isAllowedOrigin(origin) {
      return typeof origin === "string" &&
        allowedOrigins.has(origin);
    }

So sánh exact origin gồm scheme, host và port. Không chỉ kiểm tra hostname kết thúc bằng example.test.

### Các cách kiểm tra nguy hiểm

Không dùng kiểm tra suffix đơn giản:

    origin.endsWith("example.test")

Vì attacker có thể dùng hostname như:

    https://example.test.attacker.invalid

Không dùng contains:

    origin.includes("example.test")

Không chấp nhận mọi Origin:

    Access-Control-Allow-Origin: *

Header trên không phải cách xác minh WebSocket Origin.

Không phản chiếu Origin bất kỳ từ request vào response hoặc allowlist. Nếu server trả lại origin mà client vừa gửi mà không kiểm tra, attacker có thể tự cho mình vào danh sách được phép.

### Origin null và Origin bị thiếu

Một số browsing context có thể gửi Origin là null, ví dụ document có opaque origin. Request từ non-browser client cũng có thể không gửi Origin.

Đối với endpoint dành cho browser app:

- Từ chối Origin null trừ khi có use case cụ thể đã được đánh giá.
- Từ chối Origin thiếu nếu protocol của ứng dụng yêu cầu browser Origin.
- Không tự động cho phép null để hỗ trợ iframe sandbox hoặc file URL.
- Nếu có native client, thiết kế cơ chế xác thực riêng thay vì nới lỏng browser Origin allowlist.

### Origin validation không phải authentication

Origin header là tín hiệu về nguồn khởi tạo trong browser. Non-browser client có thể tự tạo hoặc giả mạo header này. Vì vậy:

- Origin allowlist giúp phòng CSWSH từ browser.
- Session/token xác thực danh tính client.
- Authorization quyết định client được làm gì.
- Rate limit và quota kiểm soát mức sử dụng.

Không dùng Origin làm bằng chứng duy nhất rằng client là người dùng hoặc ứng dụng hợp lệ.

## 5. Xác thực WebSocket an toàn

Browser WebSocket API không cung cấp tham số tùy ý để đặt Authorization header như nhiều HTTP client. Do đó, cần chọn một mô hình xác thực phù hợp.

### Mô hình 1: session cookie

Nếu web app và WebSocket endpoint dùng cookie session, server có thể xác thực session trong handshake:

- Cookie nên có Secure và HttpOnly.
- Dùng SameSite phù hợp với kiến trúc và luồng điều hướng.
- Cookie nên giới hạn Domain/Path ở mức cần thiết.
- Server phải xác minh Origin allowlist trước khi chấp nhận socket.
- Server phải kiểm tra session còn hiệu lực.
- Không dựa vào cookie có mặt là đủ; phải xác minh session ở backend.

HttpOnly ngăn JavaScript đọc trực tiếp cookie, nhưng không ngăn XSS thực hiện thao tác qua phiên của người dùng. Phòng XSS vẫn là yêu cầu riêng.

### Mô hình 2: ticket ngắn hạn, dùng một lần

Nếu WebSocket endpoint tách origin hoặc không thể dùng session cookie theo thiết kế:

1. Browser gọi HTTPS endpoint đã xác thực để xin ticket.
2. Server tạo ticket ngẫu nhiên, thời hạn rất ngắn và dùng một lần.
3. Ticket được ràng buộc với user, audience, mục đích và có thể với channel.
4. Browser dùng ticket để mở WebSocket.
5. WebSocket server xác minh ticket và đánh dấu đã sử dụng trước khi cấp quyền.

Ticket phải có entropy đủ mạnh, TTL ngắn, audience rõ ràng và không tái sử dụng. Nếu ticket xuất hiện trong query string, reverse proxy, server, APM và access log có thể ghi lại URL; cần redaction ở mọi lớp logging và ưu tiên cơ chế không để credential lâu dài trong URL.

### Tránh token dài hạn trong query string

Không nên dùng:

    wss://socket.example.test/realtime?access_token=LONG_LIVED_TOKEN

URL có thể bị ghi vào:

- Access log của reverse proxy.
- Log của WebSocket server.
- APM và tracing.
- Error report hoặc debug output.
- Hệ thống giám sát kết nối.

Nếu buộc phải dùng ticket trong URL, chỉ dùng ticket ngắn hạn, một lần, giới hạn audience và redaction log. Không dùng refresh token hoặc bearer token dài hạn.

### Subprotocol không phải cơ chế xác thực

WebSocket có header Sec-WebSocket-Protocol để thương lượng subprotocol:

    const socket = new WebSocket(
      "wss://socket.example.test/realtime",
      ["shop-events-v2"]
    );

Server chỉ nên chọn subprotocol trong danh sách client đã yêu cầu và server thực sự hỗ trợ. Không dùng tên subprotocol làm secret hoặc bằng chứng authorization. Giá trị này có thể xuất hiện trong handshake/log và không thay thế xác thực.

### Xác thực sau khi mở socket

Một số hệ thống gửi auth message đầu tiên sau khi kết nối:

    socket.send(JSON.stringify({
      type: "authenticate",
      ticket: oneTimeTicket
    }));

Nếu chọn cách này:

- Kết nối ở trạng thái unauthenticated.
- Chỉ chấp nhận message authenticate trước khi hết deadline.
- Giới hạn kích thước và số lần thử.
- Không phát dữ liệu riêng tư trước khi xác thực thành công.
- Đánh dấu ticket dùng một lần ở server.
- Đóng socket nếu xác thực thất bại hoặc quá thời gian.

Ticket vẫn có thể bị JavaScript cùng origin đọc nếu XSS xảy ra. Ưu tiên session architecture giảm credential trong JavaScript khi có thể.

## 6. Cookie, SameSite và CSRF defense

Browser có thể gửi cookie phù hợp trong WebSocket handshake. Vì thế, nếu server dựa vào cookie session mà không xác minh Origin, CSWSH có thể xảy ra.

### SameSite giúp giảm rủi ro nhưng không thay Origin validation

SameSite kiểm soát việc gửi cookie trong ngữ cảnh same-site/cross-site theo quy tắc cookie. Nó là một lớp phòng vệ hữu ích, nhưng:

- Cần đánh giá domain/site boundary thực tế.
- Subdomain cùng site không nhất thiết là cùng origin.
- Các luồng triển khai và browser privacy policy có thể khác nhau.
- Cookie có thể cần SameSite=None; Secure cho một số tích hợp cross-site.
- Không nên coi SameSite là lớp duy nhất chống CSWSH.

Biện pháp mạnh ở server là xác minh Origin exact allowlist trong handshake và xác thực session.

### Không có CSRF token mặc định trong WebSocket

WebSocket protocol không tự cung cấp CSRF token cho ứng dụng. Nếu dùng cookie session, hãy thiết kế cơ chế chống CSWSH:

1. Kiểm tra Origin trong handshake.
2. Xác thực session ở server.
3. Từ chối Origin lạ, null hoặc thiếu theo policy.
4. Không phát dữ liệu trước khi xác thực hoàn tất.
5. Kiểm tra quyền cho từng channel và message.
6. Dùng ticket ngắn hạn hoặc nonce gắn session nếu kiến trúc cần thêm lớp xác minh.

Custom header CSRF không thể được đặt tùy ý qua browser WebSocket constructor. Không sao chép máy móc giải pháp X-CSRF-Token của XHR sang WebSocket.

## 7. Authorization trên từng message

Một socket đã xác thực không có nghĩa mọi message đều hợp lệ. Người dùng có thể có quyền đọc một channel nhưng không có quyền publish, hoặc quyền có thể thay đổi trong lúc kết nối vẫn mở.

Ví dụ message:

    {
      "type": "subscribe",
      "channel": "orders:customer-123"
    }

Không tin channel do client gửi. Server phải xác minh user hiện tại có quyền đọc đúng tài nguyên đó.

### Không tin userId, role hoặc tenantId từ client

Ví dụ không an toàn:

    {
      "type": "delete-order",
      "userId": "admin",
      "role": "administrator",
      "orderId": "123"
    }

Client có thể sửa mọi field trong message. Server phải lấy user identity, role và tenant từ session/token đã xác minh, sau đó kiểm tra quyền sở hữu orderId ở backend.

### Kiểm tra quyền trên từng loại hành động

| Message | Kiểm tra cần có |
| --- | --- |
| subscribe | User có quyền đọc channel/resource không? |
| publish | User có quyền gửi dữ liệu vào channel không? |
| update | User có quyền sửa đúng object và field không? |
| delete | User có quyền xóa object không? |
| admin action | Role và policy phía server có cho phép không? |
| presence | User có được phép xem danh sách thành viên không? |

Không dựa vào việc client đã subscribe thành công để cho phép mọi hành động trên channel.

### Revalidate quyền và session

Với socket tồn tại lâu:

- Theo dõi session expiration và revoke.
- Đóng socket khi user logout.
- Cập nhật hoặc thu hồi channel subscription khi role thay đổi.
- Kiểm tra quyền tại thời điểm xử lý message nhạy cảm.
- Có giới hạn tuổi tối đa của kết nối nếu cần.

Không chỉ xác thực một lần lúc handshake rồi giữ quyền vô thời hạn.

## 8. Validate message và giới hạn payload

Mọi message từ client là input không tin cậy. Không parse rồi tin toàn bộ object.

Ví dụ message schema:

    {
      "type": "chat.send",
      "version": 1,
      "messageId": "a1b2c3",
      "roomId": "room-42",
      "text": "Xin chào"
    }

Server nên kiểm tra:

- Message là JSON hợp lệ nếu protocol yêu cầu JSON.
- Root value là object đúng kiểu.
- type nằm trong allowlist.
- version được hỗ trợ.
- Field bắt buộc có đúng kiểu và giới hạn.
- Không chấp nhận field không biết nếu protocol yêu cầu strict schema.
- messageId có định dạng và độ dài hợp lệ.
- roomId tồn tại và user có quyền.
- text có giới hạn độ dài và được xử lý như text không tin cậy.

### Giới hạn kích thước message

Đặt giới hạn tối đa ở nhiều lớp:

- Reverse proxy/gateway.
- WebSocket server library.
- Parser ứng dụng.
- Giới hạn riêng cho từng message type.

Không đợi parse toàn bộ payload rất lớn rồi mới kiểm tra. Từ chối frame/message vượt ngưỡng càng sớm càng tốt. Đối với binary message, kiểm tra byte length trước khi decode hoặc cấp phát buffer bổ sung.

### Không dùng eval hoặc dynamic code

Không thực thi message như JavaScript:

    eval(message.data);

Không chuyển message thành câu lệnh SQL, shell command hoặc template HTML bằng nối chuỗi. Dùng parser có cấu trúc, parameterized query và allowlist thao tác.

### Versioning và unknown message

Định nghĩa version protocol và chính sách tương thích:

- Từ chối message version không hỗ trợ.
- Từ chối type không nhận diện hoặc trả lỗi protocol chung.
- Không gửi stack trace hoặc thông tin nội bộ về client.
- Log mã lỗi và correlation ID để điều tra.
- Không để client ép server xử lý fallback quá rộng.

## 9. Injection và XSS qua message

Chat message, tên người dùng, thông báo và payload từ WebSocket đều là dữ liệu không tin cậy. Một message hợp lệ về JSON vẫn có thể chứa HTML hoặc JavaScript độc hại.

Ví dụ không an toàn:

    socket.onmessage = (event) => {
      chatLog.innerHTML += event.data;
    };

Nếu attacker gửi:

    <img src=x onerror=alert(1)>

thì việc nối message vào innerHTML có thể tạo DOM XSS.

Ưu tiên tạo node và gán textContent:

    socket.addEventListener("message", (event) => {
      const item = document.createElement("li");
      item.textContent = String(event.data);
      chatLog.append(item);
    });

Nếu protocol dùng JSON:

    socket.addEventListener("message", (event) => {
      let message;

      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }

      if (message.type !== "chat.message") return;
      if (typeof message.text !== "string") return;
      if (message.text.length > 2000) return;

      const item = document.createElement("li");
      item.textContent = message.text;
      chatLog.append(item);
    });

Nếu cần rich text, dùng sanitizer đã được duy trì và cấu hình allowlist tối thiểu. CSP và Trusted Types là lớp phòng vệ bổ sung, không thay output encoding theo context.

### Injection ở backend

WebSocket message thường đi vào business logic, database, search engine hoặc command handler. Server phải:

- Dùng parameterized query.
- Không ghép message vào SQL hoặc shell command.
- Validate enum, ID và numeric range.
- Giới hạn số phần tử trong array/object.
- Kiểm tra quyền trước khi truy cập object.
- Tránh log message nguyên văn nếu có thể chứa secret hoặc dữ liệu cá nhân.

## 10. DoS và resource exhaustion

WebSocket giữ tài nguyên lâu dài. Attacker có thể khai thác bằng cách mở nhiều kết nối, giữ kết nối idle, gửi message nhanh hoặc gửi payload lớn.

### Giới hạn kết nối

Áp dụng quota theo nhiều chiều:

- Số kết nối đồng thời theo IP.
- Số kết nối theo user/session.
- Số kết nối theo tenant.
- Số kết nối tổng của instance/cluster.
- Tốc độ tạo handshake.

Không chỉ rate limit theo IP vì nhiều người dùng có thể chung NAT/proxy. Kết hợp identity đã xác thực và giới hạn toàn hệ thống.

### Giới hạn message rate

Ví dụ policy minh họa:

    perConnection:
      messagesPerSecond: 20
      burst: 40
      maxMessageBytes: 65536

Các con số phải dựa trên traffic hợp lệ và capacity thực tế. Giới hạn khác nhau cho message chat, presence, typing indicator và binary upload.

Khi vượt ngưỡng:

- Từ chối message hoặc đóng kết nối theo policy.
- Áp dụng cooldown/backoff.
- Log sự kiện có giới hạn, tránh log flood.
- Không trả lỗi chi tiết giúp attacker dò ngưỡng nội bộ.

### Slow consumer và backpressure

Một client chậm có thể khiến server tích lũy queue message. Nếu queue không giới hạn, attacker có thể gây cạn bộ nhớ.

Biện pháp:

- Giới hạn số byte và số message trong outbound queue.
- Theo dõi tốc độ gửi và tốc độ tiêu thụ.
- Bỏ message có thể thay thế như presence/typing khi quá tải.
- Đóng kết nối slow consumer khi vượt ngưỡng.
- Không broadcast payload lớn tới hàng nghìn socket mà không có fan-out strategy.

Ở browser, WebSocket.bufferedAmount cho biết số byte đang chờ gửi:

    if (socket.bufferedAmount > 512 * 1024) {
      pauseSending();
    } else {
      socket.send(payload);
    }

Client-side check giúp tránh tự làm nghẽn browser nhưng không thay giới hạn queue và rate ở server.

### Giới hạn frame và compression

Đặt giới hạn frame/message size, số fragment và thời gian nhận payload. Nếu bật per-message compression, đánh giá rủi ro CPU/memory amplification và cấu hình thư viện để tránh payload nén nhỏ nhưng giải nén rất lớn.

Không bật compression chỉ vì tiết kiệm băng thông. Với dữ liệu có secret và nội dung attacker kiểm soát cùng một compression context, cần đánh giá rủi ro side-channel trước khi bật.

## 11. Heartbeat, idle timeout và reconnect

Kết nối có thể bị mất do mạng di động, NAT, proxy hoặc thiết bị chuyển trạng thái sleep. Server cần phát hiện connection chết và giải phóng tài nguyên.

### Ping/Pong control frame

WebSocket protocol có Ping và Pong control frame. Server có thể gửi Ping và mong Pong trong thời hạn; nếu không nhận, server đóng kết nối.

Browser JavaScript WebSocket API không cung cấp hàm để tự gửi Ping control frame hoặc lắng nghe Pong control frame trực tiếp. Browser xử lý Pong ở tầng protocol. Nếu ứng dụng cần heartbeat do client chủ động, có thể định nghĩa application message riêng.

### Application heartbeat

Ví dụ:

    socket.send(JSON.stringify({
      type: "heartbeat",
      sentAt: Date.now()
    }));

Server nên:

- Chỉ chấp nhận heartbeat đúng schema.
- Không xem heartbeat là xác thực hoặc gia hạn session vô hạn.
- Áp dụng giới hạn tần suất.
- Không echo message không giới hạn.
- Theo dõi thời gian idle và đóng kết nối quá hạn.

### Reconnect có backoff và jitter

Không reconnect liên tục trong vòng lặp không giới hạn. Dùng exponential backoff, jitter và số lần thử tối đa:

    function reconnectDelay(attempt) {
      const base = 500;
      const cap = 30000;
      const exponential = Math.min(cap, base * (2 ** attempt));
      return Math.floor(exponential * (0.5 + Math.random()));
    }

Reconnect phải:

- Dừng khi người dùng logout hoặc chủ động đóng.
- Không retry vô hạn khi server từ chối xác thực.
- Làm mới ticket/session đúng cách.
- Giới hạn số kết nối mới mỗi client.
- Không gửi lại thao tác có side effect nếu chưa có idempotency.

## 12. Replay, duplicate message và ordering

Kết nối có thể đứt sau khi server xử lý message nhưng trước khi client nhận ACK. Client không biết thao tác đã thành công hay chưa và có thể gửi lại sau reconnect.

Ví dụ client gửi:

    {
      "type": "payment.create",
      "messageId": "order-attempt-8f31",
      "amount": 100
    }

Nếu gửi lại cùng messageId, server nên có cơ chế idempotency để không tạo giao dịch trùng. Server phải lưu trạng thái xử lý theo user/tenant và operation, không chỉ tin messageId do client tự đặt.

Biện pháp:

- Dùng messageId duy nhất theo operation.
- Ghi nhận kết quả đã xử lý ở backend.
- Trả ACK có correlation ID.
- Kiểm tra quyền và trạng thái nghiệp vụ trước khi thực hiện.
- Có sequence/version nếu cần ordering.
- Loại bỏ duplicate trong cửa sổ thời gian được định nghĩa.
- Không dùng timestamp client làm nguồn sự thật cho thứ tự hoặc thời gian giao dịch.

WebSocket giữ thứ tự frame trên một kết nối, nhưng reconnect tạo kết nối mới và ứng dụng phải tự xử lý message pending, duplicate và ordering giữa các phiên.

## 13. Đóng kết nối và quản lý session

WebSocket có trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| CONNECTING | Đang handshake |
| OPEN | Kết nối đã mở |
| CLOSING | Đang đóng |
| CLOSED | Đã đóng |

Đóng kết nối:

    socket.close(1000, "Normal closure");

Một số close code chuẩn:

| Code | Ý nghĩa |
| --- | --- |
| 1000 | Normal closure |
| 1001 | Going away |
| 1002 | Protocol error |
| 1003 | Unsupported data |
| 1008 | Policy violation |
| 1009 | Message too big |
| 1011 | Unexpected server condition |

Không gửi close reason chứa secret, token, dữ liệu cá nhân hoặc stack trace. Ứng dụng có thể định nghĩa close code riêng trong dải cho phép, nhưng phải tuân theo giới hạn protocol và không dùng các code dành riêng cho control frame.

### Logout và revoke session

Khi user logout:

1. Kết thúc hoặc revoke session ở backend.
2. Tìm và đóng các socket gắn với session/user.
3. Xóa subscription và state server-side.
4. Không cho socket cũ tiếp tục publish hoặc subscribe.
5. Thông báo các tab liên quan cập nhật giao diện.

Không dựa vào việc browser xóa cookie để tự đóng socket đang mở. Cookie được gửi trong handshake; sau khi kết nối đã tồn tại, việc cookie bị xóa không tự động thu hồi kết nối.

### Session hết hạn khi socket vẫn OPEN

Server cần cơ chế kiểm tra session expiration/revocation:

- Timer tới thời điểm hết hạn.
- Revalidate trước thao tác nhạy cảm.
- Đóng socket khi token/session bị revoke.
- Giới hạn thời gian sống của kết nối.
- Thu hồi channel khi quyền thay đổi.

## 14. CSP, TLS và hạ tầng reverse proxy

### CSP connect-src

Content Security Policy directive connect-src giới hạn các đích mà trang có thể kết nối, gồm WebSocket:

    Content-Security-Policy: default-src 'self'; connect-src 'self' wss://socket.example.test

Khai báo wss:// rõ ràng cho WebSocket endpoint cần thiết. Hỗ trợ mapping giữa 'self' và ws/wss có khác biệt lịch sử giữa browser; không dựa duy nhất vào 'self' nếu muốn cấu hình tương thích rõ ràng.

CSP giới hạn kết nối từ trang. Nó không thay xác thực, Origin validation hoặc authorization ở server.

### TLS và wss

Production nên dùng wss://:

- Mã hóa dữ liệu trên đường truyền.
- Xác thực server qua certificate.
- Giảm nguy cơ nghe lén và sửa đổi message trên mạng.
- Tránh mixed content khi trang HTTPS kết nối endpoint không mã hóa.

TLS không bảo vệ khỏi XSS, CSWSH, user trái phép hoặc logic server yếu.

### Reverse proxy

Reverse proxy/load balancer phải hỗ trợ WebSocket upgrade hoặc cơ chế extended CONNECT tương ứng. Cần cấu hình:

- Chuyển tiếp đúng Upgrade/Connection khi dùng HTTP/1.1.
- Giữ đúng Host và thông tin scheme/origin đáng tin cậy.
- Không để client giả mạo forwarded header mà backend tin trực tiếp.
- Timeout phù hợp với heartbeat và idle policy.
- Giới hạn request/handshake rate và kích thước header.
- Giới hạn số connection trên mỗi upstream/instance.
- Chuyển tiếp close và lỗi đúng cách.

Không dùng X-Forwarded-For hoặc X-Forwarded-Proto từ client trực tiếp làm dữ liệu tin cậy. Chỉ tin forwarded header do proxy được kiểm soát ghi đè.

## 15. Logging, monitoring và phát hiện abuse

Log đủ để điều tra nhưng không ghi toàn bộ message hoặc credential một cách mặc định.

Nên ghi:

- Thời điểm kết nối và đóng.
- Kết quả Origin validation.
- User/session/tenant ID nội bộ đã được xác minh, ở dạng phù hợp với chính sách log.
- Subprotocol được chọn.
- Số message, byte gửi/nhận và thời lượng kết nối.
- Close code và nhóm nguyên nhân.
- Số lần auth fail, rate limit, schema violation.
- Correlation ID cho thao tác nghiệp vụ.

Không ghi:

- Cookie hoặc session token.
- Ticket hoặc bearer token.
- Nội dung chat riêng tư nếu không có nhu cầu và cơ sở phù hợp.
- Payload chứa thông tin thanh toán hoặc dữ liệu nhạy cảm.
- Toàn bộ query string có thể chứa credential.

### Chỉ số nên theo dõi

- Active connections và handshake rate.
- Tỷ lệ handshake bị từ chối theo Origin.
- Authentication failure rate.
- Message rate theo user, IP, tenant và connection.
- Kích thước message/frame.
- Queue depth và buffered bytes phía server.
- Slow consumer và số kết nối idle bị đóng.
- CPU/memory, event loop lag và file descriptor.
- Tỷ lệ reconnect và close code.
- Tỷ lệ message bị từ chối do schema/authorization.

Đặt alert theo baseline thực tế. Một đợt tăng kết nối có thể là traffic hợp lệ, nhưng kết hợp với auth fail, message flood hoặc queue tăng nhanh có thể báo hiệu abuse.

## 16. Kiểm thử WebSocket abuse trong staging

Chỉ chạy các bài thử dưới đây trên hệ thống local/staging do bạn kiểm soát, với tài khoản thử nghiệm và giới hạn tải đã thống nhất. Không flood endpoint production hoặc dịch vụ của bên thứ ba.

### Bước 1 — Quan sát handshake

1. Mở Chrome DevTools → Network.
2. Chọn bộ lọc WS.
3. Mở chức năng realtime trong ứng dụng.
4. Chọn kết nối và xem Request URL, Request Headers, Response Headers.
5. Xác nhận scheme là wss trên HTTPS.
6. Kiểm tra Origin và subprotocol được thương lượng.
7. Quan sát Messages để hiểu protocol, nhưng không ghi hoặc chia sẻ payload nhạy cảm.

### Bước 2 — Thử Origin không hợp lệ

Trong staging, mở trang test từ một origin không nằm trong allowlist và thử tạo socket tới endpoint.

Kết quả mong đợi:

- Server từ chối handshake.
- Không có dữ liệu riêng tư được gửi.
- Log ghi nhận Origin bị từ chối mà không ghi credential.
- Không phản chiếu Origin lạ thành giá trị được phép.

Thử thêm Origin null hoặc thiếu nếu môi trường cho phép. Xác nhận server áp dụng policy đã định nghĩa.

### Bước 3 — Thử CSWSH

Tạo một trang lab trên origin khác, đăng nhập bằng tài khoản test ở ứng dụng rồi mở trang lab. Trang lab thử tạo WebSocket tới endpoint.

Kết quả mong đợi: server từ chối vì Origin không nằm trong allowlist, dù browser có thể gửi cookie phù hợp. Xác nhận không thể subscribe hoặc đọc message riêng tư.

### Bước 4 — Thử message validation

Gửi các message test:

- JSON sai cú pháp.
- type không tồn tại.
- thiếu field bắt buộc.
- field sai kiểu.
- roomId không thuộc user.
- message vượt giới hạn kích thước.
- message version không hỗ trợ.

Kết quả mong đợi: server từ chối an toàn, không crash, không lộ stack trace và không thực hiện side effect.

### Bước 5 — Thử rate limit và slow consumer

Trong môi trường có quota nhỏ:

1. Gửi message nhanh hơn rate limit đã cấu hình.
2. Mở số kết nối thử nghiệm tới giới hạn.
3. Giả lập client không đọc message hoặc đọc chậm.
4. Quan sát queue depth và hành vi close/throttle.
5. Xác nhận các client hợp lệ khác vẫn hoạt động.

Không tạo tải vượt ngưỡng staging đã thống nhất. Kiểm thử phải có giới hạn thời gian, số client và điểm dừng rõ ràng.

### Bước 6 — Thử session revoke

1. Đăng nhập user test.
2. Mở WebSocket và subscribe channel được phép.
3. Logout hoặc revoke session ở backend.
4. Xác nhận socket bị đóng hoặc mọi message tiếp theo bị từ chối.
5. Xác nhận user khác không nhận dữ liệu của session cũ.

### Ma trận kiểm thử

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Origin hợp lệ | Origin exact allowlist, session hợp lệ | Handshake được chấp nhận |
| Origin lạ | Origin không nằm trong allowlist | Handshake bị từ chối |
| Origin null | Browser gửi opaque origin | Bị từ chối theo policy mặc định |
| Origin thiếu | Client không gửi Origin | Bị từ chối ở endpoint browser-only |
| CSWSH | Trang khác origin mở socket với cookie phù hợp | Server từ chối handshake |
| Session hết hạn | Cookie/session không còn hợp lệ | Không tạo kết nối có quyền |
| Session revoke khi OPEN | Revoke sau handshake | Socket đóng hoặc message bị từ chối ngay |
| Unauthorized channel | User subscribe room của user khác | Không cấp subscription |
| Spoof userId/role | Client gửi role admin hoặc userId khác | Server bỏ qua identity client và từ chối quyền |
| Message sai schema | JSON/type/field không hợp lệ | Từ chối an toàn |
| Message quá lớn | Vượt max payload | Từ chối hoặc đóng theo policy |
| Message flood | Vượt rate limit | Throttle/close và ghi nhận sự kiện |
| Slow consumer | Outbound queue vượt ngưỡng | Giới hạn queue hoặc đóng client |
| Duplicate message | Gửi lại cùng idempotency key | Không lặp side effect |
| XSS payload | Message chứa HTML test | UI hiển thị text, không thực thi |
| CSP chặn endpoint | connect-src không cho phép wss host | Browser chặn kết nối |

## 17. Xử lý sự cố WebSocket abuse

Khi phát hiện kết nối bất thường hoặc lạm dụng:

1. Xác định endpoint, thời gian, Origin, user/session/tenant và connection ID.
2. Tạm giảm rate, chặn Origin độc hại hoặc thu hẹp endpoint theo quy trình vận hành.
3. Thu hồi session/ticket bị lộ và đóng các socket liên quan.
4. Kiểm tra auth failure, message type, channel subscription và volume.
5. Xác minh có dữ liệu riêng tư bị gửi tới Origin trái phép hay không.
6. Kiểm tra reverse proxy, WAF, load balancer và log để tìm nguồn handshake/message.
7. Kiểm tra XSS hoặc dependency compromise ở frontend nếu socket bị sử dụng từ trang hợp lệ.
8. Sửa Origin allowlist, authorization, schema, quota hoặc queue limit theo nguyên nhân.
9. Xác nhận logout/revoke đóng socket và không còn subscription cũ.
10. Thêm regression test cho kịch bản abuse đã xảy ra.

Nếu token/ticket xuất hiện trong log, cần coi là credential có khả năng bị lộ: redact log, revoke ticket/session liên quan và điều tra các hệ thống log/APM có bản sao.

Không chỉ chặn IP rồi coi sự cố đã kết thúc. Attacker có thể đổi IP hoặc dùng nhiều nguồn; cần sửa nguyên nhân ở xác thực, Origin, authorization và giới hạn tài nguyên.

## 18. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ SOP tự chặn WebSocket cross-origin | Trang độc hại có thể mở socket nếu server chấp nhận | Xác minh Origin tại handshake |
| Dùng CORS header thay Origin validation | CSWSH vẫn có thể xảy ra | Kiểm tra Origin exact allowlist |
| Chỉ kiểm tra Origin, không xác thực session | Client giả mạo Origin có thể kết nối | Origin là lớp CSWSH; authentication là lớp riêng |
| Cho phép mọi subdomain bằng suffix check | Attacker kiểm soát domain có thể lọt allowlist | So sánh exact scheme/host/port |
| Chấp nhận Origin null vô điều kiện | Opaque-origin context có thể truy cập socket | Từ chối mặc định hoặc đánh giá use case riêng |
| Đặt token dài hạn trong query string | Credential xuất hiện trong log/APM | Session cookie hoặc one-time short-lived ticket |
| Nghĩ HttpOnly ngăn XSS sử dụng socket | XSS vẫn có thể hành động qua phiên | Phòng XSS, kiểm tra Origin và authorization |
| Xác thực một lần rồi tin mọi message | User có thể thao tác ngoài quyền | Authorization từng message và revalidate session |
| Tin userId/role từ payload | IDOR và privilege escalation | Lấy identity từ session server |
| Cache hoặc queue message không giới hạn | Memory exhaustion | Bounded queue, payload cap và backpressure |
| Cho phép reconnect vô hạn | Connection storm | Exponential backoff, jitter và cap |
| Retry thao tác có side effect không có idempotency | Giao dịch trùng | Message ID và idempotency phía server |
| Render message bằng innerHTML | DOM XSS | textContent hoặc sanitizer |
| Log toàn bộ message và URL | Lộ token và dữ liệu riêng tư | Structured log, redaction và data minimization |
| Dùng ping JS như control frame | Hiểu sai browser WebSocket API | Server Ping/Pong protocol; app heartbeat là message riêng |
| Nghĩ logout xóa cookie là socket tự đóng | Socket cũ vẫn sống | Revoke session và chủ động đóng socket |

## 19. Câu hỏi củng cố

**Câu 1.** Vì sao WebSocket có thể bị CSWSH dù Same-Origin Policy đang bật?

**Giải đáp:** Browser cho phép trang mở kết nối WebSocket cross-origin. Nếu cookie được gửi và server không xác minh Origin, trang độc hại có thể dùng socket dưới session của nạn nhân.

**Câu 2.** CORS có bảo vệ WebSocket handshake không?

**Giải đáp:** Không. WebSocket handshake không dùng CORS preflight/Access-Control-Allow-Origin như Fetch/XHR. Server phải tự xác minh Origin.

**Câu 3.** Origin allowlist có thay authentication không?

**Giải đáp:** Không. Origin giúp xác định nguồn browser để phòng CSWSH; non-browser client có thể giả mạo Origin. Server vẫn cần session/token hợp lệ.

**Câu 4.** Vì sao không nên đặt access token dài hạn trong query string?

**Giải đáp:** URL có thể xuất hiện trong access log, proxy, APM và telemetry. Nếu cần ticket qua URL, ticket phải ngắn hạn, dùng một lần và được redaction.

**Câu 5.** Sau khi handshake thành công, có cần authorization cho từng message không?

**Giải đáp:** Có. Quyền phụ thuộc channel, object và hành động; session hoặc role có thể bị thu hồi trong khi socket còn mở.

**Câu 6.** Browser JavaScript có thể gửi Ping control frame không?

**Giải đáp:** Không qua WebSocket API thông thường. Server có thể gửi Ping và browser xử lý Pong ở tầng protocol; ứng dụng có thể tạo heartbeat message riêng.

**Câu 7.** Vì sao phải giới hạn outbound queue?

**Giải đáp:** Client chậm có thể làm server tích lũy message, gây cạn bộ nhớ. Cần backpressure và đóng slow consumer khi vượt ngưỡng.

**Câu 8.** Logout có tự đóng WebSocket đang OPEN không?

**Giải đáp:** Không. Server phải revoke session, đóng socket và xóa subscription gắn với session đó.

## 20. Tổng kết

WebSocket là kênh hai chiều lâu dài, vì vậy bảo mật phải bao phủ handshake, từng message và vòng đời kết nối. Rủi ro CSWSH xuất hiện khi browser gửi cookie trong handshake cross-origin nhưng server không xác minh Origin. CORS không thay thế kiểm tra Origin cho WebSocket; Same-Origin Policy cũng không tự ngăn việc mở socket cross-origin.

Hãy dùng wss, allowlist Origin exact, xác thực session hoặc ticket ngắn hạn, authorization trên từng message, schema validation và giới hạn payload/rate/connection/queue. Không tin userId hoặc role từ client, không render message bằng innerHTML, không để credential dài hạn trong URL/log và không retry side effect nếu thiếu idempotency.

Với kết nối lâu dài, cần heartbeat, idle timeout, bounded queue, reconnect có backoff, session revocation và đóng socket khi logout. Kết hợp CSP connect-src, reverse proxy đúng cấu hình, logging có redaction và kiểm thử CSWSH/DoS trong staging để giảm nguy cơ lạm dụng.

## Tài liệu tham khảo

1. [WHATWG — WebSockets Standard](https://websockets.spec.whatwg.org/): handshake, origin, protocol và WebSocket API.
2. [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455): frame, handshake, control frame, Ping/Pong và close code.
3. [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html): Origin validation, authentication, authorization, DoS và logging.
4. [MDN — The WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API): browser WebSocket API, event và bufferedAmount.
5. [MDN — CSP connect-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/connect-src): giới hạn endpoint WebSocket mà trang có thể kết nối.
6. [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): cookie, CSRF defense và kiểm tra Origin.
