# Origin header: xác minh nguồn khởi tạo kết nối WebSocket

WebSocket bắt đầu bằng một HTTP Upgrade handshake rồi chuyển sang kênh giao tiếp hai chiều. Khi JavaScript trong một trang web mở WebSocket đến máy chủ, trình duyệt gửi header `Origin` để cho máy chủ biết origin của trang đã khởi tạo kết nối.

Máy chủ có thể dùng header này để quyết định trang web nào được phép mở kết nối. Đây là một kiểm soát quan trọng chống Cross-Site WebSocket Hijacking (CSWSH): website độc hại có thể thử mở WebSocket đến một dịch vụ mà người dùng đã đăng nhập, khiến trình duyệt gửi cookie phiên theo quy tắc cookie. Nếu máy chủ chấp nhận kết nối mà không kiểm tra nguồn, website độc hại có thể thao tác trên kết nối đã được xác thực.

`Origin` không phải thông tin xác thực người dùng và cũng không thay thế authorization. Trình duyệt bảo vệ header này khỏi JavaScript thông thường, nhưng chương trình ngoài trình duyệt có thể tự tạo hoặc giả mạo giá trị. Máy chủ cần xác minh origin theo allowlist, xác thực session độc lập và kiểm tra quyền cho từng thao tác.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của `Origin` trong WebSocket opening handshake.
- Xác định origin của trang khởi tạo và phân biệt nó với máy chủ WebSocket đích.
- Đọc dạng serialized origin gồm scheme, hostname và port.
- Phân biệt `Origin` với `Host`, `Referer` và cơ chế CORS.
- Hiểu vì sao browser client gửi `Origin` tự động và JavaScript không thể tự đặt header này.
- Nhận diện `Origin: null`, header bị thiếu và giá trị không hợp lệ.
- Xây dựng allowlist origin chính xác và từ chối handshake không được phép.
- Giải thích cách Origin validation ngăn Cross-Site WebSocket Hijacking.
- Phân biệt browser client với native/non-browser client có thể giả mạo Origin.
- Kết hợp Origin validation với cookie SameSite, authentication, CSRF protection và WSS.
- Kiểm tra header qua DevTools, reverse proxy và các bài test bảo mật.

## 1. Origin header xuất hiện ở đâu trong WebSocket?

WebSocket sử dụng một HTTP request để mở kết nối. Client gửi yêu cầu Upgrade; nếu server chấp nhận, server trả về `101 Switching Protocols` và hai bên bắt đầu trao đổi frame WebSocket.

Ví dụ handshake rút gọn:

~~~http
GET /realtime HTTP/1.1
Host: socket.example.test
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: BASE64_RANDOM_16_BYTE_NONCE
Sec-WebSocket-Version: 13
Origin: https://app.example.test
Cookie: session=...
~~~

Trong ví dụ:

- `Host` là máy chủ nhận kết nối: `socket.example.test`.
- `Origin` là origin của trang đã tạo kết nối: `https://app.example.test`.
- `Cookie` có thể mang session cookie nếu quy tắc cookie cho phép gửi.
- `Sec-WebSocket-Key` tham gia cơ chế xác nhận handshake của WebSocket.
- `Upgrade` và `Connection` yêu cầu chuyển giao thức HTTP sang WebSocket.

`Sec-WebSocket-Key` không phải access token, không xác thực người dùng và không chứng minh Origin được phép. Nó chỉ tham gia phép tính `Sec-WebSocket-Accept` để client xác nhận server đã hiểu WebSocket handshake.

`Origin` là request header trong opening handshake. Nó không phải response header và không được server trả lại để xác nhận origin.

Theo RFC 6455, browser client phải gửi `Origin` trong handshake. Client không phải trình duyệt có thể gửi header này nếu ngữ nghĩa phù hợp, nhưng cũng có thể tự tạo giá trị. Server chỉ nên dùng header này như một tín hiệu về ngữ cảnh browser, không xem nó là bằng chứng danh tính của client.

## 2. Origin là nguồn khởi tạo, không phải địa chỉ đích

Origin của một trang được xác định bởi ba thành phần:

~~~text
scheme + hostname + port
~~~

Ví dụ, trang:

~~~text
https://app.example.test:8443/orders
~~~

có origin:

~~~text
https://app.example.test:8443
~~~

Đường dẫn `/orders` không thuộc origin.

Nếu trang đó mở WebSocket đến:

~~~text
wss://socket.example.test/realtime
~~~

handshake có thể chứa:

~~~http
Host: socket.example.test
Origin: https://app.example.test:8443
~~~

Origin vẫn là origin của trang ứng dụng. Nó không đổi thành `wss://socket.example.test` chỉ vì URL đích dùng WebSocket Secure.

### 2.1 Scheme, hostname và port đều quan trọng

| Trang khởi tạo | Origin được gửi | Quan hệ |
|---|---|---|
| `https://app.example.test` | `https://app.example.test` | Origin HTTPS mặc định |
| `https://app.example.test:8443` | `https://app.example.test:8443` | Port khác là origin khác |
| `http://app.example.test` | `http://app.example.test` | Scheme khác HTTPS |
| `https://admin.example.test` | `https://admin.example.test` | Subdomain khác |
| `https://app.example.test:443` | Thường serialize thành `https://app.example.test` | 443 là port mặc định của HTTPS |

Hai trang chỉ cùng origin khi scheme, hostname và port tương ứng khớp theo quy tắc origin. Khác subdomain, khác scheme hoặc khác port đều tạo origin khác.

### 2.2 Origin không chứa path, query hoặc fragment

Các URL sau có cùng origin:

~~~text
https://app.example.test/home
https://app.example.test/account?tab=profile
https://app.example.test/orders#recent
~~~

Header chỉ mang:

~~~http
Origin: https://app.example.test
~~~

Điều này giúp server đưa ra quyết định dựa trên ranh giới origin mà không cần nhận toàn bộ URL trang nguồn.

### 2.3 Serialization và port mặc định

Origin được serialize theo dạng ASCII. Scheme và hostname được chuẩn hóa theo quy tắc của URL/origin; port mặc định thường không xuất hiện.

Ví dụ:

| Origin logic | Serialized origin thường gặp |
|---|---|
| HTTPS trên port 443 | `https://app.example.test` |
| HTTPS trên port 8443 | `https://app.example.test:8443` |
| HTTP trên port 80 | `http://app.example.test` |
| HTTP trên port 8080 | `http://app.example.test:8080` |

Vì vậy, allowlist nên chứa chuỗi origin chuẩn hóa, không thêm dấu gạch chéo cuối hoặc path. Ví dụ đúng là `https://app.example.test`, không phải `https://app.example.test/`.

## 3. Browser tạo Origin header như thế nào?

Khi code trong một trang gọi WebSocket API:

~~~js
const socket = new WebSocket("wss://socket.example.test/realtime");
~~~

trình duyệt tự tạo opening handshake và thêm `Origin` theo origin của execution context đang gọi API.

JavaScript trong trang không thể ghi đè header này bằng cách truyền một object headers vào constructor. WebSocket constructor nhận URL và tùy chọn subprotocol; nó không cung cấp giao diện tùy ý để thiết lập các request header của handshake.

`Origin` cũng là một forbidden request header trong các API web. Cơ chế này ngăn script thông thường giả mạo origin của trang đang chạy.

### 3.1 Vì sao không thể đặt Origin bằng JavaScript?

Đoạn sau không phải API hợp lệ:

~~~js
// WebSocket constructor không nhận tùy chọn headers.
const socket = new WebSocket("wss://socket.example.test/realtime", {
  headers: {
    Origin: "https://trusted.example.test"
  }
});
~~~

Đoạn đúng để mở kết nối trong trình duyệt:

~~~js
const socket = new WebSocket(
  "wss://socket.example.test/realtime",
  ["chat.v1"]
);
~~~

Trình duyệt tự thêm Origin của trang. Tham số thứ hai là danh sách subprotocol, không phải header tùy ý.

### 3.2 Native client khác browser client

Một chương trình Node.js, ứng dụng desktop, công cụ kiểm thử hoặc thư viện WebSocket ngoài trình duyệt có thể tự tạo header:

~~~http
Origin: https://trusted.example.test
~~~

Nó cũng có thể gửi một origin không tồn tại hoặc giả mạo một origin nằm trong allowlist.

Vì vậy:

- Origin validation bảo vệ tốt trước JavaScript chạy trong browser context.
- Origin không chứng minh client là trình duyệt thật.
- Origin không xác thực user hoặc service account.
- Native client vẫn phải dùng authentication phù hợp như session, token, mTLS hoặc credential của ứng dụng.

Nếu dịch vụ hỗ trợ cả browser và native client, hãy định nghĩa chính sách riêng cho từng loại client. Không bỏ qua authentication chỉ vì native client gửi một Origin có vẻ hợp lệ.

## 4. Phân biệt Origin, Host, Referer và CORS

Các khái niệm này thường xuất hiện cùng handshake nhưng trả lời những câu hỏi khác nhau.

| Thành phần | Cho biết điều gì? | Có dùng làm kiểm soát Origin cho WebSocket không? |
|---|---|---|
| `Host` | Authority của máy chủ nhận request | Không; đây là đích kết nối |
| `Origin` | Origin đã khởi tạo request | Có; server dùng để kiểm tra nguồn browser |
| `Referer` | URL nguồn, có thể chứa path và query | Không nên dùng thay Origin |
| CORS | Quyền đọc response của một số request cross-origin trong browser | Không thay thế Origin validation của WebSocket |

### 4.1 Host xác định server đích

Ví dụ:

~~~http
Host: socket.example.test
Origin: https://app.example.test
~~~

Server đích là `socket.example.test`, còn trang nguồn là `app.example.test`.

Không so sánh Origin với Host như thể chúng phải giống nhau. WebSocket thường được dùng để kết nối frontend và realtime server ở hai hostname khác nhau.

### 4.2 Referer có nhiều thông tin hơn

`Referer` có thể chứa URL đầy đủ của trang nguồn, tùy Referrer-Policy và ngữ cảnh request. Nó có thể bị rút gọn hoặc không xuất hiện.

`Origin` chỉ chứa scheme, hostname và port, không chứa path. Vì vậy, nó phù hợp hơn cho quyết định allowlist theo origin.

Không dùng chuỗi Referer để thay thế kiểm tra Origin. Referer không phải lúc nào cũng có mặt và có thể bị giới hạn bởi chính sách riêng tư.

### 4.3 CORS không phải cơ chế cấp phép WebSocket

WebSocket có thể mở kết nối cross-origin. Opening handshake không dùng quy trình CORS preflight như một số request Fetch/XHR.

Header `Access-Control-Allow-Origin` không phải cơ chế quyết định server có chấp nhận WebSocket handshake hay không. Server phải tự kiểm tra `Origin` và từ chối request không được phép trước khi trả `101 Switching Protocols`.

Ví dụ, thêm:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

không thay thế logic kiểm tra Origin trong handler Upgrade.

CORS và WebSocket Origin validation có mục đích khác nhau. Không cấu hình CORS rồi giả định WebSocket đã được bảo vệ.

## 5. Origin: null và origin opaque

Header có thể mang giá trị:

~~~http
Origin: null
~~~

`null` là dạng serialization của một opaque origin hoặc một số ngữ cảnh mà trình duyệt không cung cấp origin thông thường.

Một số trường hợp có thể tạo opaque origin:

- iframe có thuộc tính `sandbox` nhưng không có `allow-same-origin`.
- Tài liệu được tạo từ URL `data:`.
- Một số tài liệu không có browsing context tạo ra.
- Các ngữ cảnh đặc biệt mà browser cần ẩn origin thật.

Ví dụ iframe sandbox:

~~~html
<iframe
  sandbox="allow-scripts"
  src="https://untrusted.example.test/embed.html">
</iframe>
~~~

Script trong iframe có thể chạy nhưng document có origin opaque. Khi nó tạo request phù hợp, Origin có thể được serialize thành `null`.

### 5.1 Không cho phép null một cách rộng rãi

Không đưa `null` vào allowlist chỉ để làm một iframe hoặc công cụ nhúng hoạt động. Nhiều ngữ cảnh không liên quan có thể serialize thành cùng chuỗi `null`.

Nếu một use case thật sự cần opaque-origin client, hãy thiết kế một cơ chế xác thực riêng và giới hạn năng lực của kết nối. Không coi `Origin: null` là một origin đáng tin cậy.

### 5.2 Phân biệt null với header bị thiếu

Hai trường hợp này khác nhau:

~~~http
Origin: null
~~~

và request không có header `Origin`.

- `null` là một giá trị được gửi rõ ràng.
- Header bị thiếu có thể là native client, công cụ tự tạo request, proxy làm mất header hoặc request không tuân theo browser handshake thông thường.

Với endpoint chỉ dành cho browser, nên từ chối cả giá trị `null` lẫn header bị thiếu, trừ khi có yêu cầu sản phẩm được thiết kế và review riêng.

## 6. Vì sao phải kiểm tra Origin ở server?

Browser cho phép trang mở WebSocket đến một origin khác. Việc có thể tạo kết nối không đồng nghĩa server nên cấp quyền cho mọi trang.

Giả sử người dùng đăng nhập vào:

~~~text
https://bank.example.test
~~~

Browser có session cookie của website này. Sau đó người dùng mở một trang không đáng tin cậy:

~~~text
https://attacker.example
~~~

Trang độc hại có thể chạy:

~~~js
const socket = new WebSocket(
  "wss://bank.example.test/realtime"
);
~~~

Nếu browser gửi cookie phiên đến WebSocket server và server chấp nhận kết nối mà không kiểm tra nguồn, kết nối có thể mang danh tính của người dùng đang đăng nhập.

Đây là nền tảng của Cross-Site WebSocket Hijacking.

## 7. Cross-Site WebSocket Hijacking (CSWSH)

CSWSH là tình huống website độc hại mở một WebSocket đến ứng dụng mà nạn nhân đã đăng nhập. Browser có thể gửi cookie phiên theo quy tắc cookie; server nhận được một kết nối đã xác thực nhưng không nhận diện rằng JavaScript khởi tạo đến từ một origin không đáng tin.

Luồng tấn công khái quát:

~~~text
Người dùng đăng nhập vào app.example.test
             |
             v
Browser có session cookie
             |
             v
Người dùng mở evil.example.test
             |
             v
JavaScript độc hại mở WebSocket
đến wss://app.example.test/realtime
             |
             v
Browser tạo handshake và gửi Origin:
https://evil.example.test
             |
             v
Cookie phiên có thể được gửi theo cookie policy
             |
             v
Server không kiểm tra Origin
             |
             v
Kết nối được chấp nhận với session của nạn nhân
~~~

Nếu server chấp nhận kết nối, trang độc hại có thể gửi message và đọc message qua chính socket do script của nó mở. Same-Origin Policy không tự ngăn việc khởi tạo WebSocket cross-origin; server phải quyết định origin nào được phép.

### 7.1 Origin validation chặn ở thời điểm handshake

Server nên kiểm tra Origin trước khi hoàn tất Upgrade:

- Origin nằm trong allowlist: tiếp tục các bước authentication và authorization.
- Origin không được phép: trả HTTP 403 và đóng kết nối.
- Origin bị thiếu hoặc không hợp lệ: từ chối theo chính sách endpoint.
- Origin là null: từ chối nếu không có use case opaque-origin được phê duyệt.

RFC 6455 khuyến nghị server chỉ phục vụ các website dự kiến phải xác minh Origin và từ chối origin không được chấp nhận bằng HTTP 403.

### 7.2 Cookie SameSite là lớp bảo vệ bổ sung

Cookie có thể được cấu hình:

~~~http
Set-Cookie: session=...; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Hoặc dùng `SameSite=Strict` nếu phù hợp với luồng đăng nhập và điều hướng.

SameSite giúp giới hạn việc browser gửi cookie trong ngữ cảnh cross-site. Tuy nhiên, khái niệm site và origin khác nhau. Hai subdomain có thể khác origin nhưng vẫn cùng site. Vì vậy, cookie SameSite không thay thế allowlist Origin chính xác.

Với cookie `SameSite=None`, browser có thể gửi cookie trong ngữ cảnh cross-site nếu các điều kiện khác cho phép. Không dựa vào mặc định cookie của browser để bảo vệ WebSocket.

### 7.3 Origin không thay thế authentication

Một Origin nằm trong allowlist chỉ cho biết browser context được phép mở kết nối. Server vẫn phải xác thực session hoặc token.

Sau khi handshake thành công, server tiếp tục cần:

- Kiểm tra session còn hiệu lực.
- Xác định user và tenant.
- Kiểm tra quyền cho từng message hoặc action.
- Giới hạn kích thước message và tần suất gửi.
- Đóng connection khi logout hoặc session hết hạn.

Không coi việc kết nối được mở là bằng chứng user có quyền thực hiện mọi hành động.

## 8. Xây dựng allowlist Origin

Allowlist nên chứa chính xác những origin được phép mở WebSocket.

Ví dụ:

~~~js
const allowedOrigins = new Set([
  "https://app.example.test",
  "https://admin.example.test",
  "https://app.example.test:8443"
]);

function isAllowedOrigin(origin) {
  return typeof origin === "string" &&
    allowedOrigins.has(origin);
}
~~~

So sánh chính xác giúp tránh các lỗi như:

- Cho phép mọi subdomain bằng wildcard quá rộng.
- Kiểm tra hostname bằng chuỗi hậu tố và vô tình cho phép tên miền giả.
- Dùng phép chứa chuỗi và chấp nhận hostname giả.
- Chấp nhận origin chỉ vì path hoặc query chứa tên miền tin cậy.
- Cho phép mọi port trong khi chỉ một port được quản lý.

### 8.1 Không dùng substring hoặc wildcard tùy tiện

Ví dụ kiểm tra nguy hiểm:

~~~js
// Không an toàn: phép chứa chuỗi có thể khớp hostname giả.
if (origin.includes("example.test")) {
  allowConnection();
}

// Không an toàn: kiểm tra hậu tố có thể khớp evil-example.test.
if (origin.slice(-12) === "example.test") {
  allowConnection();
}
~~~

Cách phù hợp là so sánh với tập origin đã cấu hình:

~~~js
if (!allowedOrigins.has(origin)) {
  rejectHandshake();
}
~~~

Không tạo allowlist từ dữ liệu do client gửi. Cấu hình allowlist phải thuộc quyền kiểm soát của server.

### 8.2 Origin không có dấu gạch chéo hoặc path

Origin chuẩn không chứa path:

~~~text
https://app.example.test
~~~

Không cấu hình:

~~~text
https://app.example.test/
https://app.example.test/dashboard
https://app.example.test?mode=web
~~~

Những chuỗi đó không phải serialized origin chuẩn trong header.

### 8.3 Kiểm tra port và môi trường

Local development có thể dùng:

~~~text
http://localhost:3000
http://localhost:5173
~~~

Hai port khác nhau là hai origin khác nhau. Không đưa toàn bộ localhost port range vào production allowlist.

Tách cấu hình development, staging và production. Khi deploy frontend sang domain mới, cập nhật allowlist có kiểm soát và kiểm thử origin cũ đã bị loại bỏ hay chưa.

## 9. Từ chối handshake trước khi Upgrade

Origin phải được kiểm tra trước khi server trả `101 Switching Protocols`. Khi handshake chưa thành công, server vẫn có thể trả HTTP status như 403 hoặc 401.

Ví dụ response khi từ chối:

~~~http
HTTP/1.1 403 Forbidden
Connection: close
Content-Length: 0
~~~

Không trả `101` rồi mới kiểm tra Origin trong message đầu tiên nếu mục tiêu là chặn CSWSH tại handshake. Sau khi Upgrade thành công, giao thức đã chuyển sang WebSocket và không còn dùng HTTP 403 cho connection đó.

### 9.1 Node.js với thư viện ws

Ví dụ dưới đây minh họa kiểm tra Origin trong HTTP server Upgrade handler trước khi gọi `handleUpgrade()`. Hàm xác thực session là phần ứng dụng cần tự triển khai.

~~~js
const { WebSocketServer } = require("ws");

const wss = new WebSocketServer({
  noServer: true
});

const allowedOrigins = new Set([
  "https://app.example.test",
  "https://admin.example.test"
]);

function getSingleOrigin(req) {
  const values = [];

  for (let i = 0; i < req.rawHeaders.length; i += 2) {
    if (req.rawHeaders[i].toLowerCase() === "origin") {
      values.push(req.rawHeaders[i + 1]);
    }
  }

  return values.length === 1 ? values[0] : null;
}

function rejectUpgrade(socket, status, reason) {
  if (socket.destroyed) return;

  socket.end(
    "HTTP/1.1 " + status + " " + reason +
    "\r\nConnection: close\r\n\r\n"
  );
}

server.on("upgrade", (req, socket, head) => {
  const origin = getSingleOrigin(req);

  if (!origin || !allowedOrigins.has(origin)) {
    rejectUpgrade(socket, 403, "Forbidden");
    return;
  }

  authenticateSession(req)
    .then(session => {
      if (socket.destroyed) return;

      if (!session) {
        rejectUpgrade(socket, 401, "Unauthorized");
        return;
      }

      wss.handleUpgrade(req, socket, head, ws => {
        wss.emit("connection", ws, req, session);
      });
    })
    .catch(() => {
      rejectUpgrade(socket, 500, "Internal Server Error");
    });
});
~~~

Trong ví dụ:

- `getSingleOrigin()` yêu cầu đúng một Origin header.
- Header bị thiếu, trùng hoặc không nằm trong allowlist sẽ bị từ chối.
- `authenticateSession()` xác thực session độc lập với Origin.
- `handleUpgrade()` chỉ được gọi sau khi Origin và session được chấp nhận.
- `noServer: true` cho phép ứng dụng tự kiểm soát bước Upgrade.

Đây là khung tích hợp. Trong production, cần xử lý timeout xác thực, socket đóng trong lúc chờ, logging an toàn, giới hạn kết nối và authorization cho message.

### 9.2 Xác thực trước khi phát dữ liệu

Ngay cả sau khi handshake được chấp nhận, server chỉ nên gửi dữ liệu riêng tư sau khi đã xác thực và gắn danh tính user vào connection.

Không gửi dữ liệu tài khoản ngay khi socket mở rồi mới chờ client gửi token. Nếu dùng xác thực bằng message đầu tiên, server phải giữ connection ở trạng thái chưa xác thực và chỉ chấp nhận thông điệp xác thực trong giai đoạn đó.

### 9.3 Token và CSRF token

WebSocket constructor trong browser không cho JavaScript tùy ý thêm header Authorization hoặc header CSRF. Nếu thiết kế cần token bổ sung, phải chọn cơ chế tương thích với browser API và giao thức ứng dụng.

Có thể yêu cầu thông điệp xác thực đầu tiên chứa token ngắn hạn hoặc nonce do ứng dụng cấp qua kênh đáng tin cậy. Server không được gửi dữ liệu bảo vệ hoặc thực hiện action trước khi token hợp lệ.

Không đặt access token hoặc refresh token dài hạn vào query string của WebSocket URL. URL có thể xuất hiện trong access log, proxy log hoặc công cụ giám sát.

## 10. Origin header không phải bằng chứng chống giả mạo cho mọi client

Một browser client không thể tự đặt Origin bằng JavaScript thông thường. Nhưng một native client hoặc công cụ HTTP có thể tạo bất kỳ giá trị nào.

Ví dụ một chương trình ngoài trình duyệt có thể gửi:

~~~http
Origin: https://app.example.test
~~~

dù nó không chạy trong trang đó.

Vì vậy:

- Dùng Origin để bảo vệ trước script cross-origin trong browser.
- Dùng session/token/mTLS để xác thực client.
- Không cấp quyền chỉ vì Origin nằm trong allowlist.
- Nếu native client được phép không gửi Origin, xác thực nó qua một luồng riêng.
- Không cho phép header thiếu Origin trở thành đường vòng để bỏ qua authentication.

Nếu endpoint chỉ dành cho browser, từ chối header thiếu hoặc null là chính sách rõ ràng. Nếu endpoint phục vụ cả native client, hãy tách quy tắc và phương thức xác thực theo loại client.

## 11. WSS và Origin giải quyết hai rủi ro khác nhau

Production nên dùng WebSocket Secure:

~~~js
const socket = new WebSocket(
  "wss://socket.example.test/realtime"
);
~~~

`wss://` bảo vệ kênh truyền bằng TLS, giúp chống nghe lén và sửa đổi dữ liệu trên đường truyền.

Origin validation quyết định trang nào được phép khởi tạo kết nối theo chính sách server.

| Kiểm soát | Bảo vệ điều gì? |
|---|---|
| WSS/TLS | Tính bí mật và toàn vẹn của dữ liệu trên đường truyền |
| Origin allowlist | Ngăn browser script từ website không được phép mở kết nối |
| Authentication | Xác định user hoặc client |
| Authorization | Xác định user được làm gì |
| SameSite cookie | Giảm việc gửi cookie trong ngữ cảnh cross-site |
| CSRF token | Xác minh thao tác có bằng chứng chống CSRF theo thiết kế ứng dụng |

Dùng WSS không tự ngăn CSWSH. Một kết nối được mã hóa vẫn có thể là kết nối do website độc hại khởi tạo nếu server chấp nhận Origin đó.

## 12. Reverse proxy và load balancer

WebSocket thường đi qua reverse proxy, ingress hoặc load balancer trước khi đến ứng dụng.

Ví dụ:

~~~text
Browser
  |
  | Upgrade request + Origin
  v
Reverse proxy / ingress
  |
  | Forward Upgrade và request headers
  v
WebSocket application
  |
  | Origin validation + authentication
  v
101 Switching Protocols
~~~

Cần bảo đảm proxy:

- Chuyển tiếp header `Origin` nguyên vẹn.
- Không thay Origin bằng hostname của backend.
- Không xóa header khi chuyển tiếp Upgrade.
- Không tin giá trị Origin do một proxy không được kiểm soát tự thêm.
- Áp dụng chính sách nhất quán nếu Origin được kiểm tra ở edge và application.
- Ghi log kết quả kiểm tra mà không lưu cookie hoặc token.

### 12.1 Forwarded và X-Forwarded-* không thay Origin

`Host`, `Forwarded`, `X-Forwarded-Host` và `X-Forwarded-Proto` mô tả thông tin về request đích và đường đi qua proxy.

Chúng không thay thế Origin của trang khởi tạo.

Không dựng Origin từ `X-Forwarded-Host`. Nếu proxy cần thông tin này, hãy giữ header Origin gốc và chỉ tin proxy trong mạng hạ tầng đã được cấu hình.

### 12.2 Tránh cấu hình khác nhau giữa edge và backend

Nếu edge cho phép origin A nhưng backend cho phép origin B, hành vi sẽ khó dự đoán. Xác định một nguồn cấu hình allowlist và bảo đảm mọi lớp kiểm tra dùng cùng danh sách.

Nếu TLS kết thúc ở proxy, upstream có thể dùng HTTP nội bộ nhưng kết nối public vẫn phải là WSS. Origin header vẫn phản ánh trang nguồn, không phải scheme nội bộ của upstream.

## 13. Logging và giám sát Origin validation

Ghi nhận các trường cần thiết để điều tra:

- Thời điểm handshake.
- Endpoint WebSocket.
- Origin đã nhận, sau khi loại bỏ dữ liệu không cần thiết.
- Kết quả allow/deny.
- Lý do từ chối như missing, null, duplicate hoặc not-allowlisted.
- User/session identifier dạng nội bộ nếu đã xác thực.
- Địa chỉ IP theo chính sách logging.
- Request ID để nối log giữa proxy và backend.

Không ghi session cookie, bearer token, CSRF token hoặc nội dung riêng tư vào log.

Nếu Origin không được chấp nhận, từ chối trước Upgrade và ghi sự kiện bảo mật phù hợp. Theo dõi tần suất origin lạ, request không có Origin và các lần thử handshake bất thường.

## 14. Kiểm thử Origin header

Kiểm thử nên bao gồm origin hợp lệ, origin lạ, null, thiếu header và client không phải trình duyệt.

### 14.1 Kiểm tra từ browser DevTools

1. Mở ứng dụng từ một origin nằm trong allowlist.
2. Tạo WebSocket bằng browser API.
3. Mở DevTools → Network → WS.
4. Chọn request handshake.
5. Xem Request Headers và tìm `Origin`.
6. Xác nhận giá trị là origin của trang hiện tại.
7. Kiểm tra response `101 Switching Protocols` nếu server chấp nhận.

Thử lại từ một domain không được phép. Server phải trả 403 trước khi Upgrade thành công.

### 14.2 Kiểm tra origin khác port

Chạy frontend lab ở hai port:

~~~text
http://localhost:3000
http://localhost:5173
~~~

Đăng ký chỉ một origin trong allowlist. Xác nhận port còn lại bị từ chối dù hostname giống nhau.

Đây là bài test quan trọng vì hostname-only matching sẽ bỏ sót khác biệt port.

### 14.3 Kiểm tra null origin

Tạo một iframe sandbox không có `allow-same-origin` và thử mở WebSocket từ iframe. Quan sát header `Origin: null` nếu browser và ngữ cảnh thử nghiệm tạo giá trị đó.

Server không nên chấp nhận null nếu use case không yêu cầu.

### 14.4 Kiểm tra header bị thiếu và client giả mạo

Dùng một native WebSocket client hoặc công cụ kiểm thử có khả năng tùy chỉnh handshake:

- Gửi request không có Origin.
- Gửi Origin không nằm trong allowlist.
- Gửi Origin giả mạo nằm trong allowlist.
- Gửi header Origin trùng nếu công cụ cho phép.

Kết quả cần chứng minh hai điều:

- Browser-only endpoint từ chối header thiếu, null hoặc không được phép.
- Một Origin hợp lệ do native client giả mạo vẫn không thể bỏ qua authentication.

### 14.5 Ví dụ kiểm thử handshake bằng curl

Có thể dùng curl để gửi một HTTP Upgrade request có Origin tự chọn. Thay placeholder bằng Base64 của 16 byte ngẫu nhiên hợp lệ:

~~~bash
curl --http1.1 -i "https://socket.example.test/realtime" \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: BASE64_RANDOM_16_BYTE_NONCE" \
  -H "Origin: https://evil.example.test"
~~~

Kết quả mong đợi là HTTP 403 trước khi server trả `101 Switching Protocols`. Nếu server trả 101, cần kiểm tra lại vị trí thực hiện Origin validation.

Curl không mô phỏng các giới hạn bảo vệ header của browser. Nó hữu ích để chứng minh rằng client ngoài trình duyệt có thể tự đặt Origin.

## 15. Lỗi triển khai thường gặp

### 15.1 Chấp nhận mọi Origin

Không kiểm tra Origin hoặc cho phép wildcard sẽ mở đường cho website bất kỳ thử kết nối bằng session của người dùng.

Dùng allowlist cụ thể và từ chối mặc định.

### 15.2 So sánh hostname mà bỏ qua scheme và port

`http://app.example.test`, `https://app.example.test` và `https://app.example.test:8443` là các origin khác nhau.

So sánh toàn bộ serialized origin.

### 15.3 Dùng Referer thay Origin

Referer có thể bị rút gọn hoặc vắng mặt. Dùng Origin làm tín hiệu nguồn cho WebSocket handshake.

### 15.4 Dùng CORS header thay Origin validation

`Access-Control-Allow-Origin` không phải cơ chế cho phép WebSocket Upgrade. Kiểm tra Origin ở server trước khi trả 101.

### 15.5 Chấp nhận Origin: null

Null có thể đến từ nhiều opaque origin khác nhau. Không đưa null vào allowlist chung.

### 15.6 Tin Origin từ native client

Native client có thể giả mạo header. Xác thực client độc lập.

### 15.7 Bỏ qua Origin khi header bị thiếu

Nếu endpoint dành cho browser, header thiếu là bất thường. Fail closed thay vì mặc định cho phép.

### 15.8 Chỉ kiểm tra Origin sau khi Upgrade

Khi đã trả 101, handshake HTTP hoàn tất. Hãy từ chối bằng 403 trước khi nâng cấp.

### 15.9 Nghĩ SameSite đủ để bảo vệ

SameSite giảm việc gửi cookie cross-site nhưng không thay thế allowlist Origin. Site và origin là hai khái niệm khác nhau.

### 15.10 Nghĩ WSS ngăn CSWSH

TLS bảo vệ đường truyền. Nó không chứng minh website khởi tạo là website được tin cậy.

### 15.11 Cho phép kết nối rồi mới xác thực message

Không gửi dữ liệu bảo vệ hoặc thực hiện action trước khi authentication và CSRF checks hoàn tất.

### 15.12 Proxy làm mất hoặc thay Origin

Kiểm tra header tại edge và backend. Không dựng Origin từ X-Forwarded-Host.

## 16. Quy trình triển khai

Trước khi đưa WebSocket endpoint vào production:

1. Liệt kê frontend origin được phép kết nối.
2. Chuẩn hóa scheme, hostname và port của từng origin.
3. Cấu hình allowlist ở server.
4. Kiểm tra Origin trên mọi handshake trước Upgrade.
5. Từ chối missing, null, duplicate và origin không được phép theo chính sách.
6. Xác thực session hoặc token độc lập với Origin.
7. Dùng WSS trên kết nối public.
8. Cấu hình cookie Secure, HttpOnly và SameSite phù hợp.
9. Bảo vệ CSRF cho endpoint dùng cookie.
10. Xác thực và phân quyền cho từng message.
11. Đóng connection khi logout hoặc session hết hạn.
12. Kiểm tra reverse proxy giữ nguyên Origin.
13. Kiểm thử browser, native client, null origin và các port khác nhau.
14. Giám sát handshake bị từ chối và điều chỉnh allowlist qua quy trình review.

## 17. Bài thực hành

Thực hiện trên server WebSocket lab do bạn kiểm soát. Không kiểm thử bằng cách gửi request đến dịch vụ của bên thứ ba.

### Bài 1: Quan sát Origin trong handshake

Tạo trang ở `https://app.example.test` và mở kết nối đến `wss://socket.example.test/realtime`. Dùng DevTools xem Host và Origin. Giải thích vì sao hai giá trị khác nhau.

### Bài 2: Xây dựng allowlist

Cho phép `https://app.example.test` và từ chối `https://evil.example.test`. Kiểm tra server trả 101 cho origin hợp lệ và 403 cho origin không hợp lệ.

### Bài 3: Kiểm tra scheme và port

Thử các origin HTTP, HTTPS và port khác nhau. Xác nhận allowlist so sánh toàn bộ origin thay vì chỉ hostname.

### Bài 4: Kiểm tra Origin null

Tạo iframe sandbox không có allow-same-origin. Mở WebSocket và quan sát Origin. Xác nhận server từ chối null.

### Bài 5: Mô phỏng CSWSH

Tạo trang lab ở origin không được phép và thử mở WebSocket đến server lab đã có session cookie. Xác nhận Origin validation từ chối trước Upgrade.

### Bài 6: Giả mạo Origin bằng native client

Dùng công cụ ngoài trình duyệt gửi Origin hợp lệ nhưng không cung cấp session hợp lệ. Xác nhận authentication vẫn từ chối kết nối.

### Bài 7: Kiểm tra reverse proxy

Đặt server sau proxy. Gửi request từ frontend được phép và không được phép. Xác nhận Origin đến backend giữ nguyên và quyết định allow/deny nhất quán.

### Bài 8: Kiểm tra logout và session expiry

Mở WebSocket sau khi đăng nhập, sau đó logout hoặc hết hạn session. Xác nhận server đóng connection và không cho phép tiếp tục thao tác.

## 18. Checklist review Origin header

- [ ] Hiểu Origin là origin của script context tạo kết nối.
- [ ] Phân biệt Origin với Host của server WebSocket.
- [ ] Không dùng Referer hoặc CORS thay thế Origin validation.
- [ ] Chỉ dùng WSS trên production.
- [ ] Có allowlist scheme, hostname và port chính xác.
- [ ] Không dùng substring, suffix hoặc wildcard rộng.
- [ ] Không thêm path hoặc trailing slash vào origin string.
- [ ] Từ chối Origin null trừ khi có use case được phê duyệt.
- [ ] Từ chối Origin bị thiếu hoặc duplicate trên browser-only endpoint.
- [ ] Kiểm tra Origin trước khi trả 101.
- [ ] Trả 403 cho origin không được chấp nhận.
- [ ] Không coi Origin là authentication.
- [ ] Xác thực session/token độc lập.
- [ ] Có kiểm tra authorization ở cấp message.
- [ ] Cookie session có Secure, HttpOnly và SameSite phù hợp.
- [ ] Có CSRF protection cho luồng xác thực bằng cookie.
- [ ] Không lưu token dài hạn trong URL query.
- [ ] Native client có cơ chế authentication riêng.
- [ ] Reverse proxy giữ nguyên Origin và không tự dựng từ forwarded host.
- [ ] Có log an toàn cho handshake bị từ chối.
- [ ] Có test origin hợp lệ, lạ, null, thiếu, khác port và giả mạo.
- [ ] Đóng connection khi logout hoặc session hết hạn.

## 19. Câu hỏi tự kiểm tra

**1. Origin header trong WebSocket cho biết điều gì?**

Nó cho biết origin của context đã khởi tạo kết nối, thường là trang web chứa JavaScript gọi WebSocket API.

**2. Origin khác Host như thế nào?**

Host xác định máy chủ nhận handshake; Origin xác định trang nguồn đã khởi tạo request.

**3. Origin có chứa path hoặc query không?**

Không. Serialized origin chỉ gồm scheme, hostname và port khi khác port mặc định.

**4. Browser có tự gửi Origin không?**

Có. Browser client phải gửi Origin trong WebSocket handshake theo RFC 6455; JavaScript thông thường không thể tự đặt hoặc ghi đè header này.

**5. Native client có thể giả mạo Origin không?**

Có. Chương trình ngoài browser có thể tự tạo header, vì vậy Origin không phải authentication.

**6. CORS có bảo vệ WebSocket handshake không?**

Không theo cơ chế CORS response/preflight thông thường. Server phải tự kiểm tra Origin trước khi Upgrade.

**7. Origin: null có nghĩa là gì?**

Đó là serialized opaque origin hoặc một ngữ cảnh đặc biệt không có origin dạng scheme/host/port. Không nên cho phép null một cách rộng rãi.

**8. CSWSH xảy ra như thế nào?**

Website độc hại mở WebSocket đến server mà người dùng đã đăng nhập; nếu browser gửi cookie và server không kiểm tra Origin, website đó có thể thao tác trên kết nối đã xác thực.

**9. Origin validation có thay authentication không?**

Không. Nó kiểm soát nguồn browser được phép khởi tạo kết nối; server vẫn phải xác thực user và phân quyền từng thao tác.

**10. Khi Origin không được phép, server nên phản hồi thế nào?**

Từ chối handshake bằng HTTP 403 trước khi trả 101 Switching Protocols.

## Ghi nhớ

Origin header cho biết origin của trang đã khởi tạo WebSocket, không phải địa chỉ server đích. Browser tự gửi header này và JavaScript thông thường không thể giả mạo, nhưng native client có thể tự đặt giá trị. Hãy kiểm tra Origin bằng allowlist chính xác trước khi Upgrade, từ chối null hoặc missing theo chính sách, kết hợp authentication và authorization độc lập, dùng WSS và bảo vệ session để ngăn CSWSH.

## Tài liệu tham khảo

- [RFC 6455: The WebSocket Protocol, Sections 4.1, 4.2.2 and 10.1–10.2](https://www.rfc-editor.org/rfc/rfc6455.html)
- [RFC 6454: The Web Origin Concept](https://www.rfc-editor.org/rfc/rfc6454.html)
- [MDN: Origin header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin)
- [MDN: Writing WebSocket servers](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_servers)
- [OWASP: WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html)
