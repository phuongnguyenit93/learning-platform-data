# Authentication

**WebSocket không tự cung cấp cơ chế xác thực người dùng.** Một kết nối WebSocket bắt đầu bằng HTTP opening handshake, sau đó được nâng cấp thành kênh hai chiều. Ứng dụng phải xác định người dùng ở bước handshake hoặc xác thực bằng một thông điệp đầu tiên sau khi kết nối được mở.

Trong browser, WebSocket handshake có thể tự gửi cookie phù hợp với URL đích. Đây là cách phổ biến để dùng session hiện có, nhưng cũng tạo nguy cơ **Cross-Site WebSocket Hijacking (CSWSH)**: một trang độc hại có thể mở socket tới ứng dụng đang đăng nhập của nạn nhân và browser tự gửi cookie. Server phải kiểm tra chính xác header Origin trên mọi handshake, xác thực session và chỉ cho phép các origin đã tin cậy.

Nếu dùng token với WebSocket API của browser, constructor chỉ nhận URL và danh sách subprotocol; nó không cho JavaScript tùy ý đặt header Authorization. Một lựa chọn phù hợp là gửi token ngắn hạn trong thông điệp xác thực đầu tiên qua WSS. Trước khi xác thực thành công, server chỉ nhận thông điệp authentication, không gửi dữ liệu được bảo vệ và không xử lý lệnh nghiệp vụ. Sau khi kết nối đã xác thực, server vẫn phải kiểm tra quyền cho từng message, subscription và tài nguyên.

Bài học thuộc chương **WebSocket** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung phân tích ranh giới giữa browser, origin, cookie và ứng dụng web; tập trung vào xác thực ở handshake, cookie/session, token, Origin validation, CSWSH và authorization trong kết nối dài hạn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao WebSocket không có authentication protocol tích hợp sẵn.
2. Mô tả HTTP opening handshake và xác định thời điểm ứng dụng phải xác thực.
3. So sánh xác thực bằng cookie/session ở handshake với token trong message đầu tiên.
4. Giải thích giới hạn của WebSocket constructor trong browser và lý do không thể tự đặt header Authorization.
5. Phân tích CSWSH khi browser tự gửi cookie trong WebSocket handshake.
6. Kiểm tra Origin bằng allowlist chính xác và hiểu giới hạn của Origin với non-browser client.
7. Phân biệt Origin validation, CORS, browser permission và authentication.
8. Thiết kế trạng thái unauthenticated/authenticated, timeout, token expiry và logout cho socket dài hạn.
9. Kiểm tra authorization theo từng message, subscription và tài nguyên thay vì tin rằng kết nối đã xác thực là đủ.
10. Dùng Node.js và thư viện ws để thực hành handshake validation, message authentication và role-based authorization.

## 2. WebSocket authentication bắt đầu ở đâu?

WebSocket mở một kết nối bằng HTTP request có các header nâng cấp giao thức. Với HTTP/1.1, request thường có dạng:

~~~http
GET /socket HTTP/1.1
Host: app.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example.com
Cookie: session=...
~~~

Nếu server chấp nhận handshake, nó trả response 101 Switching Protocols và hai bên bắt đầu trao đổi WebSocket frames. Với browser, cookie phù hợp với endpoint có thể được gửi trong request này. Header Origin cho biết origin của document đã tạo kết nối.

WebSocket protocol không định nghĩa tài khoản, mật khẩu, bearer token, session hoặc role. Các giá trị đó thuộc về cơ chế authentication của ứng dụng. Server có thể xác thực ngay trong HTTP handshake trước khi gửi 101, hoặc mở kết nối trước rồi yêu cầu một message authentication trước khi cho phép hoạt động.

### 2.1. Hai thời điểm xác thực

| Cách xác thực | Thời điểm | Ưu điểm | Điều cần kiểm soát |
| --- | --- | --- | --- |
| Handshake authentication | Trước response 101 | Từ chối sớm, không tạo socket chưa xác thực | Cookie/session hoặc credential phải có sẵn trong handshake |
| First-message authentication | Sau response 101, trước message nghiệp vụ | Phù hợp browser token vì WebSocket API không cho đặt custom Authorization header | Không gửi dữ liệu protected trước auth; giới hạn thời gian và tài nguyên chờ |

Không có lựa chọn duy nhất cho mọi ứng dụng. Nếu website đã dùng cookie session an toàn, xác thực session trong handshake thường đơn giản. Nếu browser client lấy access token từ một flow riêng, xác thực bằng message đầu tiên qua WSS có thể phù hợp hơn.

### 2.2. Authentication và authorization là hai việc khác nhau

- **Authentication (xác thực):** kết nối này thuộc về ai? Ví dụ user ID, session ID hoặc service identity.
- **Authorization (ủy quyền):** danh tính đó được làm gì trên tài nguyên cụ thể? Ví dụ được subscribe phòng chat nào, đọc đơn hàng nào hoặc gọi lệnh quản trị nào.

Một socket đã xác thực không có nghĩa mọi message gửi qua socket đều hợp lệ. Server phải lấy principal từ trạng thái đã xác thực của connection và kiểm tra quyền cho từng hành động. Không tin userId, tenantId hoặc role do client tự gửi trong JSON message.

## 3. Xác thực bằng cookie và session ở handshake

Nếu ứng dụng đã có đăng nhập bằng cookie session, browser thường tự gửi cookie khi mở WebSocket tới host/path phù hợp. Server đọc cookie trong HTTP upgrade request, tìm session ở phía server và chỉ gọi handleUpgrade khi session hợp lệ.

Ví dụ cookie session:

~~~http
Set-Cookie: __Host-session=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Các thuộc tính có ý nghĩa:

- **Secure:** chỉ gửi cookie qua kết nối bảo mật.
- **HttpOnly:** JavaScript trang không đọc trực tiếp giá trị cookie.
- **SameSite=Lax hoặc Strict:** giảm việc browser gửi cookie trong ngữ cảnh cross-site; đây là lớp phòng vệ bổ sung cho CSWSH.
- **__Host- prefix:** yêu cầu Secure, Path=/ và không có Domain attribute trong browser hỗ trợ, giúp giới hạn cookie ở host hiện tại.
- **Opaque session ID:** giá trị ngẫu nhiên, khó đoán; dữ liệu danh tính và quyền được lưu phía server.

Không dùng cookie chứa role hoặc thông tin nhạy cảm mà server tin trực tiếp. Cookie nên là session identifier; server tra session và lấy principal từ kho dữ liệu đáng tin cậy.

### 3.1. Luồng xác thực cookie

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as WebSocket server
    participant A as Session store
    B->>S: HTTP Upgrade + Cookie + Origin
    S->>S: Kiểm tra Origin allowlist
    S->>A: Tra session từ cookie
    A-->>S: Session hợp lệ và principal
    alt Session hợp lệ
        S-->>B: 101 Switching Protocols
        B->>S: WebSocket message
        S->>S: Kiểm tra quyền của principal
        S-->>B: Response được phép
    else Session không hợp lệ
        S-->>B: 401/403 và đóng handshake
    end
~~~

### 3.2. Ví dụ đọc session trước khi upgrade

Đoạn mã dưới đây là pseudocode phía server; hàm getSession() phải tra session store thật và kiểm tra expiry/revocation:

~~~js
server.on('upgrade', async (request, socket, head) => {
  const origin = request.headers.origin;

  if (!ALLOWED_ORIGINS.has(origin)) {
    rejectUpgrade(socket, 403, 'Forbidden');
    return;
  }

  try {
    const sessionId = readCookie(request.headers.cookie, '__Host-session');
    const session = sessionId
      ? await getSession(sessionId)
      : null;

    if (!session || session.expiresAt <= Date.now()) {
      rejectUpgrade(socket, 401, 'Unauthorized');
      return;
    }

    wss.handleUpgrade(request, socket, head, (ws) => {
      attachPrincipal(ws, session.user);
      wss.emit('connection', ws, request);
    });
  } catch {
    rejectUpgrade(socket, 503, 'Service Unavailable');
  }
});
~~~

Không gửi response 101 trước khi kiểm tra session nếu ứng dụng muốn xác thực hoàn toàn ở handshake. Với thư viện ws, nên kiểm tra trong HTTP server upgrade event trước handleUpgrade; không dùng callback verifyClient cũ khi thư viện khuyến nghị xử lý ở upgrade event.

### 3.3. Cookie không tự chứng minh request đến từ trang hợp lệ

Cookie được browser gửi tự động theo quy tắc cookie. Nếu server chỉ kiểm tra cookie mà không kiểm tra Origin, một trang độc hại có thể khởi tạo WebSocket tới endpoint và tận dụng session của nạn nhân.

Đây là khác biệt quan trọng so với việc client tự gắn bearer token vào một message: cookie là credential ambient, browser có thể đính kèm mà JavaScript của trang gọi không cần đọc được giá trị cookie.

## 4. Cross-Site WebSocket Hijacking (CSWSH)

**CSWSH** là tấn công trong đó trang ở origin không tin cậy mở một WebSocket tới ứng dụng mục tiêu trong khi browser của nạn nhân tự gửi credential, thường là cookie session. Nếu server chấp nhận kết nối và cho phép trao đổi dữ liệu, JavaScript trên trang độc hại có thể tương tác với socket đã xác thực.

### 4.1. Kịch bản tấn công

~~~mermaid
sequenceDiagram
    participant V as Browser của nạn nhân
    participant M as Trang độc hại
    participant A as WebSocket ứng dụng
    Note over V,A: Nạn nhân đã đăng nhập, browser lưu session cookie
    V->>M: Mở trang attacker.example
    M->>V: JavaScript tạo WebSocket tới wss://app.example.com/socket
    V->>A: Handshake kèm cookie phù hợp và Origin attacker.example
    A->>A: Server chỉ kiểm tra cookie, bỏ qua Origin
    A-->>V: 101 Switching Protocols
    M->>A: Gửi message qua socket
    A-->>M: Dữ liệu tài khoản qua socket
~~~

JavaScript của attacker không cần đọc cookie HttpOnly. Browser tự gửi cookie trong handshake. Nếu server không xác minh Origin và chấp nhận session, trang độc hại có thể gửi message và đọc message trả về qua WebSocket object.

### 4.2. Kiểm tra Origin bằng allowlist chính xác

Server phải xác thực header Origin trên mỗi handshake browser:

~~~js
const ALLOWED_ORIGINS = new Set([
  'https://app.example.com',
  'https://admin.example.com',
]);

function isAllowedOrigin(origin) {
  return typeof origin === 'string' &&
    ALLOWED_ORIGINS.has(origin);
}
~~~

So sánh chính xác cả scheme, hostname và port. Không dùng:

~~~js
origin.includes('example.com')
origin.endsWith('example.com')
origin.startsWith('https://app.example.com')
~~~

Các cách kiểm tra lỏng có thể chấp nhận origin giả như:

- https://app.example.com.attacker.test
- https://attacker-app.example.com
- https://app.example.com:8443
- http://app.example.com

Origin có scheme, host và port; port mặc định có thể được chuẩn hóa theo quy tắc URL. Hãy parse và so sánh theo allowlist đã chuẩn hóa khi cần hỗ trợ nhiều môi trường, thay vì tự viết regex phỏng đoán.

### 4.3. Origin không phải authentication

Browser tự đặt Origin cho WebSocket handshake và JavaScript trong trang không thể tùy ý ghi đè header này. Điều đó làm Origin hữu ích để chống CSWSH.

Tuy nhiên, một chương trình ngoài browser như command-line client hoặc server-to-server client có thể tự gửi một Origin giả. Vì vậy:

- Origin allowlist bảo vệ endpoint browser khỏi trang web không tin cậy.
- Session, token, mTLS hoặc credential khác xác thực danh tính client.
- Authorization kiểm tra quyền của danh tính đó trên từng thao tác.

Với endpoint chỉ dành cho browser, có thể từ chối handshake thiếu Origin hoặc có Origin là null. Nếu cần hỗ trợ native client, hãy thiết kế cơ chế authentication riêng và không xem Origin do client đó gửi là bằng chứng tin cậy.

### 4.4. SameSite cookie là lớp phòng vệ bổ sung

Đặt cookie session với SameSite=Lax hoặc Strict giúp browser hạn chế gửi cookie trong request cross-site và giảm nguy cơ CSWSH. Hãy kiểm tra hành vi trên browser mục tiêu và kiến trúc đăng nhập thực tế; không dùng SameSite làm biện pháp duy nhất.

Origin validation vẫn cần thiết vì:

- Một số ứng dụng có cookie hoặc credential khác không chịu cùng chính sách.
- Native client có thể tự tạo header Origin.
- Lỗi cấu hình cookie hoặc thay đổi luồng đăng nhập có thể làm mất lớp SameSite.
- Allowlist Origin thể hiện rõ những website nào được phép mở socket.

### 4.5. CORS không thay thế Origin validation

WebSocket opening handshake không sử dụng CORS preflight như một request fetch thông thường. Việc thêm Access-Control-Allow-Origin vào response không thay thế kiểm tra Origin phía server.

Server phải tự kiểm tra Origin trước khi nâng cấp. Không phản chiếu mọi Origin nhận được vào allowlist hoặc trả về một header CORS rộng rồi coi socket đã an toàn.

## 5. Xác thực bằng message đầu tiên

Browser WebSocket API có constructor:

~~~js
new WebSocket(url)
new WebSocket(url, protocols)
~~~

Constructor cho phép cung cấp URL và subprotocol, nhưng không có tham số để đặt custom request headers như Authorization. Vì vậy, code browser không thể viết:

~~~js
// Không phải API hợp lệ của browser WebSocket:
new WebSocket(url, {
  headers: {
    Authorization: 'Bearer ...',
  },
});
~~~

Một số thư viện WebSocket cho Node.js hoặc native client có thể hỗ trợ custom handshake headers. Đó là khả năng của thư viện/client, không phải khả năng chuẩn của browser WebSocket constructor.

### 5.1. Luồng first-message authentication

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as WebSocket server
    participant I as Identity/token service
    B->>S: Opening handshake qua WSS + Origin
    S->>S: Kiểm tra Origin và giới hạn kết nối
    S-->>B: 101 Switching Protocols
    Note over B,S: Connection state = AUTH_PENDING
    B->>S: Message authenticate với access token
    S->>I: Xác minh token, expiry, audience, revocation
    I-->>S: Principal hợp lệ
    S->>S: Connection state = AUTHENTICATED
    S-->>B: Message authenticated
    B->>S: Message nghiệp vụ
    S->>S: Kiểm tra authorization
    S-->>B: Response được phép
~~~

Trong trạng thái AUTH_PENDING, server không gửi dữ liệu tài khoản, event riêng tư hoặc kết quả subscription. Chỉ message authentication được phép đi qua.

### 5.2. Client gửi token trong message đầu tiên

~~~js
const socket = new WebSocket('wss://app.example.com/socket');

socket.addEventListener('open', () => {
  socket.send(JSON.stringify({
    type: 'authenticate',
    token: shortLivedAccessToken,
  }));
});

socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data);

  if (message.type === 'authenticated') {
    console.log('WebSocket đã xác thực');
    return;
  }

  handleApplicationMessage(message);
});
~~~

Token phải được truyền qua WSS, có thời hạn ngắn và audience phù hợp với WebSocket service. Không đưa access token vào URL query string vì URL có thể xuất hiện trong access log, monitoring, trace hoặc công cụ chẩn đoán. Cũng không ghi token trong message log.

### 5.3. State machine phía server

~~~text
CONNECTING
    |
    v
AUTH_PENDING ---- auth hợp lệ ----> AUTHENTICATED
    |                                  |
    | auth sai                         | logout / expiry / revoke
    | timeout                          |
    v                                  v
CLOSED <--------------------------- CLOSED
                                       ^
                                       |
                           policy violation / idle timeout
~~~

Server nên áp dụng các quy tắc:

- Đặt thời hạn ngắn cho AUTH_PENDING, ví dụ vài giây.
- Giới hạn số connection chưa xác thực theo IP và các tín hiệu phù hợp.
- Giới hạn kích thước message ngay từ WebSocket server.
- Từ chối message nghiệp vụ trước khi auth thành công.
- Đóng socket nếu token sai, hết hạn hoặc không đúng audience.
- Không phát dữ liệu protected trước khi auth hoàn tất.
- Không cho client gửi nhiều message authenticate để dò token.

### 5.4. Không dùng query string để chứa bearer token

Tránh:

~~~js
new WebSocket(
  'wss://app.example.com/socket?access_token=' +
  encodeURIComponent(accessToken)
);
~~~

Query string có thể bị ghi vào reverse proxy log, access log, APM trace, URL capture hoặc báo cáo lỗi. TLS không ngăn URL bị ghi ở các hệ thống kết thúc TLS.

Nếu hạ tầng bắt buộc phải xác thực ngay ở handshake và không thể dùng cookie, có thể thiết kế một vé kết nối ngắn hạn, dùng một lần, được cấp qua HTTPS đã xác thực và bị giới hạn audience/scope. Đây vẫn là credential trong URL nếu truyền qua query; cần đánh giá khả năng lộ log, redact tại mọi tầng và ưu tiên first-message authentication khi phù hợp.

### 5.5. Không biến subprotocol thành nơi giấu token

Tham số protocols của WebSocket constructor dùng để thương lượng subprotocol qua Sec-WebSocket-Protocol. Đây là nơi khai báo giao thức ứng dụng như chat.v1 hoặc events.v2, không phải header Authorization tùy biến. Không nhét bearer token vào tên subprotocol; nó có thể xuất hiện trong log/diagnostic và làm sai mục đích thương lượng giao thức.

## 6. Token, session và kết nối dài hạn

WebSocket có thể tồn tại lâu hơn HTTP request đã mở nó. Một session có thể hết hạn, người dùng có thể logout, quyền có thể bị thu hồi hoặc tài khoản bị khóa trong khi socket vẫn đang mở.

### 6.1. Kiểm tra expiry và revocation

Khi xác thực, server lưu principal và session/token reference gắn với connection. Server cần có cách phát hiện:

- Session hết hạn.
- Access token hết hạn hoặc bị thu hồi.
- Người dùng logout.
- Tài khoản bị khóa hoặc đổi mật khẩu theo chính sách.
- Role hoặc membership trong tenant thay đổi.
- Phiên đăng nhập bị đánh dấu rủi ro hoặc cần xác thực lại.

Không chỉ kiểm tra token một lần rồi để socket sống vô hạn. Có thể revalidate theo chu kỳ hoặc dùng sự kiện revoke từ session service để đóng các connection liên quan.

### 6.2. Logout phải đóng các socket liên quan

Khi người dùng logout, server nên tìm và đóng các WebSocket connection gắn với session đó. Có thể duy trì map từ session ID/user ID tới tập connection đang hoạt động. Khi session bị revoke, gửi close frame với mã phù hợp và xóa liên kết.

Ví dụ:

~~~js
function closeConnectionsForSession(sessionId) {
  const sockets = connectionsBySession.get(sessionId);

  if (!sockets) return;

  for (const socket of sockets) {
    socket.close(1008, 'Session expired');
  }

  connectionsBySession.delete(sessionId);
}
~~~

Không gửi session ID hoặc token trong close reason. Close reason có thể xuất hiện trong client log hoặc telemetry.

### 6.3. Token refresh và re-authentication

Với token ngắn hạn, server và client cần một giao thức refresh rõ ràng:

1. Server thông báo token sắp hết hạn mà không gửi thông tin nhạy cảm không cần thiết.
2. Client lấy token mới qua HTTPS bằng flow authentication chuẩn.
3. Client gửi message reauthenticate qua WSS.
4. Server xác minh token mới, kiểm tra cùng principal hoặc chính sách chuyển danh tính.
5. Server thay credential reference và thời điểm expiry trên connection.
6. Nếu refresh thất bại hoặc quá hạn, server đóng socket.

Không cho phép một connection đang thuộc user A đổi sang user B chỉ bằng cách gửi token mới nếu sản phẩm không có flow đổi danh tính được thiết kế rõ ràng.

### 6.4. Ping/pong không phải authentication

Ping/pong frame giúp phát hiện kết nối chết hoặc mạng không còn hoạt động. Chúng không chứng minh user còn đăng nhập hoặc token còn hiệu lực. Heartbeat và session revalidation giải quyết hai vấn đề khác nhau.

## 7. Authorization cho từng message

Sau khi authentication thành công, server nên gắn principal vào đối tượng connection hoặc context do server quản lý:

~~~js
ws.principal = {
  userId: session.userId,
  tenantId: session.tenantId,
  roles: session.roles,
  sessionId: session.id,
};
~~~

Đây là dữ liệu server lấy từ session/token đã xác minh. Không chấp nhận message như:

~~~json
{
  "type": "delete_order",
  "userId": "admin",
  "role": "administrator",
  "orderId": "order-123"
}
~~~

và dùng userId/role do client gửi làm căn cứ quyền. Client chỉ nên gửi hành động cùng identifier của tài nguyên; server tự lấy danh tính và kiểm tra quyền.

### 7.1. Kiểm tra quyền ở từng hành động

~~~js
function handleMessage(ws, message) {
  const principal = ws.principal;

  if (message.type === 'subscribe_order') {
    const order = getOrder(message.orderId);

    if (!order || !canReadOrder(principal, order)) {
      ws.send(JSON.stringify({
        type: 'error',
        code: 'FORBIDDEN',
      }));
      return;
    }

    subscribeConnectionToOrder(ws, order.id);
    return;
  }

  if (message.type === 'admin_delete_user') {
    if (!principal.roles.includes('admin')) {
      ws.send(JSON.stringify({
        type: 'error',
        code: 'FORBIDDEN',
      }));
      return;
    }

    deleteUserAccordingToPolicy(message.targetUserId, principal);
  }
}
~~~

Ví dụ chỉ minh họa cấu trúc. Hàm canReadOrder() phải kiểm tra tenant, ownership, trạng thái tài nguyên và các điều kiện nghiệp vụ cần thiết. Việc có role admin cũng không tự động cho phép thao tác trên mọi tenant nếu hệ thống có ranh giới tenant.

### 7.2. Subscription cũng là một hành động được phân quyền

Một client không được subscribe tùy ý tới:

- Phòng chat của người dùng khác.
- Kênh quản trị hoặc audit.
- Event stream của tenant khác.
- Đơn hàng, tài khoản hoặc tài nguyên mà user không có quyền đọc.

Kiểm tra quyền lúc subscribe và cân nhắc kiểm tra lại khi quyền bị thu hồi. Nếu server phát broadcast theo channel, danh sách subscriber phải được xây dựng từ subscription đã được authorize.

### 7.3. Không tin dữ liệu do client tự nhận là identity

Không dùng các trường userId, email, role, tenantId, isAdmin trong payload làm identity. Những trường đó có thể được sửa bằng DevTools hoặc một WebSocket client tùy chỉnh.

Lấy principal từ context đã xác thực. Nếu message chứa tenantId hoặc resource ID, server phải xác minh tài nguyên thuộc tenant mà principal được phép truy cập.

## 8. WSS, handshake và các biện pháp bổ sung

### 8.1. Dùng WSS trong production

~~~js
const socket = new WebSocket('wss://app.example.com/socket');
~~~

WSS mã hóa và bảo vệ tính toàn vẹn dữ liệu trên đường truyền bằng TLS. Không dùng ws:// cho dữ liệu đăng nhập, session, token hoặc message production trên mạng không tin cậy.

Nếu trang được tải qua HTTPS, browser thường chặn kết nối ws:// như mixed content. Hãy cấu hình endpoint WSS và reverse proxy đúng cách.

### 8.2. Handshake không thay thế kiểm tra message

Handshake thành công chỉ cho biết server đồng ý nâng cấp kết nối. Nó không xác minh mọi message sau đó và không chứng minh client được phép truy cập mọi tài nguyên.

Server vẫn cần:

- Parse message an toàn và xử lý JSON lỗi.
- Allowlist các message type.
- Kiểm tra schema, kiểu dữ liệu, kích thước và encoding.
- Rate limit theo user, IP, connection và action.
- Đặt giới hạn payload và backpressure.
- Xác minh quyền trước khi đọc/ghi dữ liệu.
- Không render message như HTML không tin cậy ở client.

### 8.3. Close code phù hợp

| Code | Ý nghĩa thường dùng |
| --- | --- |
| 1000 | Normal Closure |
| 1003 | Unsupported Data |
| 1008 | Policy Violation, có thể dùng cho auth/policy failure |
| 1009 | Message Too Big |
| 1011 | Internal Error |

Không đặt token, cookie, session ID hoặc chi tiết nội bộ vào close reason.

## 9. Thực hành: WebSocket authentication bằng Node.js

Bài lab dùng **Node.js 18 trở lên** và package ws. Lab minh họa:

- Chỉ chấp nhận Origin chính xác là http://localhost:3000.
- Từ chối handshake từ origin khác hoặc thiếu Origin.
- Xác thực token trong message đầu tiên sau khi socket mở.
- Không cho phép message nghiệp vụ trước khi authentication thành công.
- Áp dụng timeout, payload limit và role authorization cho message.

Token demo được hard-code để dễ thực hành; chỉ dùng local lab. Ứng dụng thật cần token ngắn hạn, chữ ký/issuer/audience/expiry được xác minh hoặc session store đáng tin cậy.

### 9.1. Tạo thư mục lab và cài package

~~~bash
mkdir websocket-auth-lab
cd websocket-auth-lab
npm init -y
npm install ws
~~~

### 9.2. Tạo file server.mjs

~~~js
import { createServer } from 'node:http';
import { WebSocket, WebSocketServer } from 'ws';

const PORT = 3000;
const ALLOWED_ORIGINS = new Set([
  'http://localhost:3000',
]);

const DEMO_TOKENS = new Map([
  ['demo-user-token', {
    userId: 'user-100',
    role: 'user',
  }],
  ['demo-admin-token', {
    userId: 'admin-1',
    role: 'admin',
  }],
]);

const AUTH_TIMEOUT_MS = 5000;
const MAX_PAYLOAD = 16 * 1024;

const html = `<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WebSocket authentication lab</title>
</head>
<body>
  <h1>WebSocket authentication</h1>
  <label>
    Demo token
    <select id="token">
      <option value="demo-user-token">User</option>
      <option value="demo-admin-token">Admin</option>
      <option value="invalid-token">Invalid token</option>
    </select>
  </label>
  <button id="connect">Connect and authenticate</button>
  <button id="profile">Get profile</button>
  <button id="admin">Admin action</button>
  <button id="close">Close</button>
  <pre id="log">Disconnected</pre>
  <script>
    let socket;
    const log = document.querySelector('#log');
    function write(value) {
      log.textContent += '\\n' + value;
    }

    document.querySelector('#connect').addEventListener('click', () => {
      if (socket && socket.readyState <= WebSocket.OPEN) {
        write('Socket is already connecting or open.');
        return;
      }

      socket = new WebSocket('ws://localhost:3000/socket');

      socket.addEventListener('open', () => {
        write('Handshake accepted. Sending authentication message.');
        socket.send(JSON.stringify({
          type: 'authenticate',
          token: document.querySelector('#token').value,
        }));
      });

      socket.addEventListener('message', (event) => {
        write('Server: ' + event.data);
      });

      socket.addEventListener('close', (event) => {
        write('Closed: ' + event.code + ' ' + event.reason);
      });

      socket.addEventListener('error', () => {
        write('WebSocket error. Inspect Network and server console.');
      });
    });

    document.querySelector('#profile').addEventListener('click', () => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'get_profile' }));
      }
    });

    document.querySelector('#admin').addEventListener('click', () => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'admin_action' }));
      }
    });

    document.querySelector('#close').addEventListener('click', () => {
      socket?.close(1000, 'User closed');
    });
  </script>
</body>
</html>`;

const server = createServer((request, response) => {
  if (request.url === '/') {
    response.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    response.end(html);
    return;
  }

  response.writeHead(404);
  response.end('Not found');
});

const wss = new WebSocketServer({
  noServer: true,
  maxPayload: MAX_PAYLOAD,
  perMessageDeflate: false,
});

function rejectUpgrade(socket, status, reason) {
  socket.end(
    'HTTP/1.1 ' + status + ' ' + reason + '\\r\\n' +
    'Connection: close\\r\\n' +
    'Content-Length: 0\\r\\n\\r\\n'
  );
}

server.on('upgrade', (request, socket, head) => {
  const url = new URL(request.url, 'http://localhost:3000');
  const origin = request.headers.origin;

  if (url.pathname !== '/socket') {
    rejectUpgrade(socket, 404, 'Not Found');
    return;
  }

  if (!ALLOWED_ORIGINS.has(origin)) {
    rejectUpgrade(socket, 403, 'Forbidden');
    return;
  }

  wss.handleUpgrade(request, socket, head, (ws) => {
    wss.emit('connection', ws, request);
  });
});

wss.on('connection', (ws) => {
  let principal = null;

  const authTimer = setTimeout(() => {
    if (!principal && ws.readyState === WebSocket.OPEN) {
      ws.close(1008, 'Authentication timeout');
    }
  }, AUTH_TIMEOUT_MS);

  ws.on('message', (raw, isBinary) => {
    if (isBinary) {
      ws.close(1003, 'Text messages only');
      return;
    }

    let message;
    try {
      message = JSON.parse(raw.toString());
    } catch {
      ws.close(1008, 'Invalid message');
      return;
    }

    if (!message || typeof message !== 'object' ||
        typeof message.type !== 'string') {
      ws.close(1008, 'Invalid message shape');
      return;
    }

    if (!principal) {
      if (message.type !== 'authenticate' ||
          typeof message.token !== 'string') {
        ws.close(1008, 'Authentication required');
        return;
      }

      const identity = DEMO_TOKENS.get(message.token);
      if (!identity) {
        clearTimeout(authTimer);
        ws.close(1008, 'Authentication failed');
        return;
      }

      principal = Object.freeze({ ...identity });
      clearTimeout(authTimer);

      ws.send(JSON.stringify({
        type: 'authenticated',
        userId: principal.userId,
        role: principal.role,
      }));
      return;
    }

    if (message.type === 'get_profile') {
      ws.send(JSON.stringify({
        type: 'profile',
        userId: principal.userId,
        message: 'Profile trả về theo principal đã xác thực.',
      }));
      return;
    }

    if (message.type === 'admin_action') {
      if (principal.role !== 'admin') {
        ws.send(JSON.stringify({
          type: 'error',
          code: 'FORBIDDEN',
        }));
        return;
      }

      ws.send(JSON.stringify({
        type: 'admin_result',
        message: 'Admin action được cho phép.',
      }));
      return;
    }

    ws.send(JSON.stringify({
      type: 'error',
      code: 'UNKNOWN_MESSAGE',
    }));
  });

  ws.on('close', () => {
    clearTimeout(authTimer);
  });
});

server.listen(PORT, () => {
  console.log('Open http://localhost:3000');
});
~~~

### 9.3. Chạy lab

~~~bash
node server.mjs
~~~

Mở http://localhost:3000. Chọn User hoặc Admin rồi nhấn Connect and authenticate.

### 9.4. Quan sát kết quả

| Thử nghiệm | Kết quả mong đợi |
| --- | --- |
| Origin localhost:3000 và token user hợp lệ | Handshake được chấp nhận; server gửi authenticated |
| User gọi get_profile | Server trả profile của user đã xác thực |
| User gọi admin_action | Server trả FORBIDDEN |
| Admin gọi admin_action | Server cho phép |
| Token không hợp lệ | Socket đóng với policy violation sau khi nhận auth message |
| Không gửi auth message | Server đóng socket sau timeout |
| Origin khác hoặc không có Origin | Server từ chối trước response 101 |
| Gửi message nghiệp vụ trước auth | Server đóng socket vì authentication required |

### 9.5. Thử Origin không hợp lệ

Để kiểm tra CSWSH defense, chạy một trang thử nghiệm từ origin khác, ví dụ một static server ở port 3001, rồi tạo WebSocket tới localhost:3000. Browser sẽ tự gửi Origin http://localhost:3001. Server lab phải trả 403 trước khi nâng cấp.

Không dùng một WebSocket client tùy chỉnh có thể tự đặt Origin để kết luận browser protection hoạt động; chương trình ngoài browser có thể giả mạo header này. Bài kiểm tra CSWSH cần được thực hiện bằng browser thật từ origin không được phép.

### 9.6. Giới hạn lab

- Token demo được hard-code và không có expiry/revocation; không dùng trong production.
- Lab dùng ws://localhost để học handshake; production phải dùng WSS.
- Lab xác thực bằng first message nên server vẫn mở socket trong tối đa vài giây trước khi auth timeout.
- Origin allowlist chỉ có localhost:3000 và cố ý từ chối client không có Origin.
- Ví dụ role authorization đơn giản; ứng dụng thực tế phải kiểm tra tenant, ownership và quyền trên từng tài nguyên.
- Không có database, session store, token issuer hoặc refresh flow trong lab.

## 10. Kiểm tra authentication và CSWSH trong DevTools

### 10.1. Network panel

Trong DevTools → Network, lọc WS và chọn request kết nối:

- Request URL và endpoint.
- Status 101 nếu handshake thành công.
- Request headers như Origin, Cookie, Sec-WebSocket-Protocol.
- Response headers của handshake.
- Messages/Frames sau khi kết nối.

Cookie có thể bị ẩn một phần trong DevTools tùy browser và quyền riêng tư. Không copy session cookie hoặc token vào báo cáo lỗi.

### 10.2. Kiểm tra handshake bị từ chối

Nếu server từ chối trước upgrade, browser có thể chỉ hiển thị lỗi kết nối chung. Xem log server để xác định handshake bị từ chối do Origin, session hoặc policy. Không trả chi tiết session tồn tại/không tồn tại cho client không tin cậy.

### 10.3. Kiểm tra CSWSH

Trong một browser đã đăng nhập ứng dụng:

1. Mở một trang từ origin không nằm trong allowlist.
2. Tạo WebSocket tới endpoint ứng dụng.
3. Quan sát Origin do browser tự gửi.
4. Xác minh server từ chối trước response 101.
5. Lặp lại với origin hợp lệ và kiểm tra authentication bình thường.

Chỉ kiểm tra status kết nối là chưa đủ. Nếu socket đã mở, thử xem server có gửi dữ liệu protected trước auth hay cho phép message nghiệp vụ khi chưa xác thực không.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ WebSocket tự xác thực user | Server có thể chấp nhận socket ẩn danh | Thiết kế authentication ở handshake hoặc first message |
| Chỉ kiểm tra cookie | Có thể bị CSWSH từ trang độc hại | Kiểm tra Origin chính xác trên mọi browser handshake |
| Tin Origin là danh tính | Native client có thể giả mạo header | Xác thực bằng session/token hoặc credential thực |
| Dùng CORS header thay Origin validation | Handshake vẫn có thể được chấp nhận từ origin lạ | Tự kiểm tra Origin ở server trước upgrade |
| Dùng substring cho allowlist | Origin giả có thể vượt qua kiểm tra | So sánh chính xác scheme, host và port |
| Đặt bearer token trong query string | Token có thể lọt vào access log và trace | Gửi token trong first message qua WSS hoặc dùng cookie session |
| Đặt token trong subprotocol | Lẫn credential với protocol negotiation và có thể lộ log | Dùng subprotocol đúng mục đích, xác thực bằng cơ chế riêng |
| Tin browser có thể đặt Authorization header | WebSocket constructor không hỗ trợ custom headers | Dùng cookie session hoặc first-message authentication |
| Gửi event protected ngay sau 101 | Client chưa auth có thể đọc dữ liệu | Chỉ gửi dữ liệu sau khi principal được xác thực |
| Chỉ phân quyền lúc handshake | User có thể gọi action hoặc subscribe ngoài quyền | Authorization cho từng message, channel và resource |
| Không xử lý session expiry | Socket còn hoạt động sau logout hoặc revoke | Revalidate, đóng socket và quản lý connection theo session |
| Ghi toàn bộ message vào log | Token, session và dữ liệu cá nhân bị lộ | Log metadata/sự kiện, redact payload nhạy cảm |

## 12. Checklist triển khai WebSocket authentication

1. **Dùng WSS:** mã hóa handshake và mọi frame trong production.
2. **Chọn điểm xác thực:** session cookie ở handshake hoặc token ngắn hạn trong first message.
3. **Kiểm tra Origin:** dùng allowlist chính xác scheme/host/port; từ chối Origin lạ và chính sách rõ ràng cho Origin thiếu/null.
4. **Không coi Origin là credential:** xác thực session/token độc lập.
5. **Bảo vệ cookie:** Secure, HttpOnly, SameSite và host-only khi phù hợp.
6. **Chống CSWSH:** kết hợp Origin allowlist với SameSite và CSRF control phù hợp.
7. **Không để token trong URL:** tránh query string và không dùng subprotocol làm nơi chứa bearer token.
8. **Giới hạn AUTH_PENDING:** timeout, rate limit và payload limit.
9. **Không gửi dữ liệu trước auth:** chỉ nhận message authenticate trước khi principal được gắn vào socket.
10. **Xác minh token đầy đủ:** chữ ký/issuer/audience/expiry/revocation theo hệ thống identity.
11. **Authorization từng message:** kiểm tra role, tenant, ownership, subscription và resource.
12. **Xử lý session dài hạn:** expiry, refresh, revoke và logout phải tác động đến socket.
13. **Giới hạn tài nguyên:** max payload, số connection, rate limit, idle timeout và backpressure.
14. **Log an toàn:** ghi Origin, principal ID, auth result, close code và violation; không ghi token/cookie/message nhạy cảm.
15. **Kiểm thử browser thật:** thử Origin hợp lệ, origin độc hại, thiếu Origin, session expired và message chưa auth.

## 13. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “WebSocket có cơ chế đăng nhập riêng.” | WebSocket protocol không định nghĩa user authentication; ứng dụng tự tích hợp session/token. |
| “Browser WebSocket cho đặt header Authorization.” | Constructor chuẩn chỉ nhận URL và optional subprotocol. |
| “Cookie HttpOnly ngăn CSWSH.” | HttpOnly ngăn JavaScript đọc cookie; browser vẫn có thể tự gửi cookie trong handshake. |
| “Origin hợp lệ chứng minh user đã đăng nhập.” | Origin chỉ giúp xác định trang khởi tạo trong browser; session/token mới xác thực danh tính. |
| “CORS bảo vệ WebSocket handshake.” | Phải kiểm tra Origin ở server; CORS response header không thay thế kiểm tra đó. |
| “SameSite là lớp bảo vệ duy nhất cần có.” | SameSite là defense-in-depth; vẫn phải kiểm tra Origin và session. |
| “Sau 101 thì mọi message đều đáng tin.” | Message vẫn là input không tin cậy; cần parse, validate và authorize từng action. |
| “Role trong JSON do client gửi có thể dùng để phân quyền.” | Principal và quyền phải lấy từ server-side session/token đã xác thực. |
| “Socket sống thì session còn hợp lệ.” | Session có thể hết hạn hoặc bị revoke trong khi socket vẫn mở. |
| “Ping/pong chứng minh user còn đăng nhập.” | Ping/pong chỉ kiểm tra kết nối; session validation là việc riêng. |

## 14. Câu hỏi tự đánh giá

**Câu 1.** WebSocket authentication được thực hiện ở đâu?

**Gợi ý trả lời:** Ứng dụng có thể xác thực trước 101 trong HTTP handshake hoặc sau khi socket mở bằng message đầu tiên; WebSocket protocol không tự xác thực user.

**Câu 2.** Vì sao cookie session có thể gây CSWSH?

**Gợi ý trả lời:** Browser có thể tự gửi cookie trong handshake tới server; trang độc hại có thể tạo socket bằng session của nạn nhân nếu server không kiểm tra Origin.

**Câu 3.** Vì sao phải so sánh Origin chính xác?

**Gợi ý trả lời:** Kiểm tra substring hoặc suffix lỏng có thể chấp nhận domain giả, scheme hoặc port khác.

**Câu 4.** Origin có thay thế authentication không?

**Gợi ý trả lời:** Không. Non-browser client có thể giả mạo Origin; session/token mới xác minh danh tính.

**Câu 5.** Vì sao browser token client thường xác thực bằng first message?

**Gợi ý trả lời:** WebSocket constructor chuẩn không cho JavaScript đặt custom Authorization header; message đầu tiên qua WSS là một cách truyền token mà không đưa token vào URL.

**Câu 6.** Server cần làm gì trước khi message authentication thành công?

**Gợi ý trả lời:** Chỉ nhận message authentication, giới hạn thời gian/tài nguyên và không gửi dữ liệu protected hoặc xử lý lệnh nghiệp vụ.

**Câu 7.** Vì sao cần authorization từng message?

**Gợi ý trả lời:** Authentication chỉ xác định danh tính; mỗi hành động, subscription và tài nguyên có thể yêu cầu quyền khác nhau.

**Câu 8.** Logout ảnh hưởng tới WebSocket đang mở thế nào?

**Gợi ý trả lời:** Server phải revoke session và đóng các connection gắn với session đó; không chờ client tự đóng.

## Tài liệu tham khảo

- OWASP — [WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html).
- OWASP — [Web Security Testing Guide: Testing WebSockets](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/11-Client-side/09-WebSockets/).
- MDN — [Writing WebSocket servers](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_servers).
- MDN — [WebSocket() constructor](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/WebSocket).
- MDN — [WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API).
- IETF — [RFC 6455: The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455).
- CWE — [CWE-1385: Missing Origin Validation in WebSockets](https://cwe.mitre.org/data/definitions/1385.html).
