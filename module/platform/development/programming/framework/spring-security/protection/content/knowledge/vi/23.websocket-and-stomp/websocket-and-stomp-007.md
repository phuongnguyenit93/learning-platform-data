# Truyền token bằng STOMP headers

## 1. Bài toán: browser không gửi được mọi HTTP header, nhưng STOMP có native headers

Một hệ thống realtime dùng frontend `https://app.example.com` và backend `wss://api.example.com/ws`. API HTTP xác thực bằng access token (ví dụ JWT) và Spring WebSocket Message Broker nhận lệnh thông qua STOMP. Lập trình viên thử truyền token như Fetch:

~~~javascript
// Sai với WebSocket API của trình duyệt: constructor không nhận object headers.
new WebSocket("wss://api.example.com/ws", {
  headers: {
    Authorization: "Bearer <access-token>"
  }
});
~~~

Cú pháp đó **không thuộc WebSocket constructor chuẩn của browser**. HTTP `GET Upgrade` không có `Authorization` do JavaScript tự thêm bằng object trên. Thế nhưng thư viện STOMP có thể gửi **native headers bên trong STOMP `CONNECT` frame** sau khi WebSocket transport đã mở:

~~~text
CONNECT
accept-version:1.2
host:api.example.com
Authorization:Bearer <verified-access-token>

^@
~~~

Đây là một cách thiết kế **xác thực ở lớp messaging**: server cần đọc native header, xác minh token thật, gắn `Authentication` vào STOMP session, rồi bảo vệ `SEND`/`SUBSCRIBE`. Nó **không phải tính năng tự động** chỉ nhờ client gửi chuỗi `Authorization`.

Có một loại token khác cũng thường được truyền trong STOMP `CONNECT`: **CSRF token**. Nó giúp chống nguy cơ browser dùng cookie phiên ngoài ý muốn, và **không phải** access token để xác định principal. Bài sẽ chỉ ra sự khác biệt, đặc biệt khi ứng dụng bật `@EnableWebSocketSecurity` và CSRF tại CONNECT.

Bài thuộc chương **WebSocket và STOMP** của **SPRING_SECURITY_HTTP_PROTECTION**. Phạm vi môn học bao gồm các lớp phòng vệ HTTP và trình duyệt — CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, session — với Spring Security Servlet và Reactive. Ở đây ta tập trung vào **truyền token qua STOMP headers**, theo luồng Servlet/STOMP và đối chiếu với WebFlux native WebSocket.

### Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt HTTP headers của handshake và STOMP native headers ở `CONNECT`/`SEND`/`SUBSCRIBE`.
2. Nêu sự khác nhau giữa access token, session cookie, CSRF token và STOMP `login`/`passcode`.
3. Sử dụng `@stomp/stompjs` hoặc SockJS để truyền token bằng `connectHeaders`.
4. Cài đặt đúng ý tưởng xác thực token ở `ChannelInterceptor#preSend` trên client inbound channel.
5. Hiểu `StompHeaderAccessor#setUser(...)`, propagation của principal và **thứ tự interceptor trước Spring Security authorization**.
6. Chọn kiến trúc nhất quán giữa authenticated HTTP handshake và bearer-authenticated STOMP CONNECT.
7. Xử lý đúng CSRF CONNECT khi `@EnableWebSocketSecurity` được bật; không mặc định JWT làm tắt CSRF.
8. Phân quyền `SEND`/`SUBSCRIBE` deny-by-default và kiểm tra quyền object/tenant trong service.
9. Quản lý token hết hạn, refresh/reconnect, logs, SockJS HTTP fallback và kết nối dài hạn.
10. Kiểm thử cả token đúng/sai, Origin giả, quyền subscribe, logout/thu hồi và trường hợp WebFlux không có STOMP.

Tên miền `example.com` và các token trong bài chỉ dùng minh họa. Đoạn code cần được đặt trong Spring Boot/Spring Security project có dependencies đúng phiên bản và có bộ test tích hợp trước khi triển khai production.

## 2. Token nào được truyền ở lớp nào?

Bốn dạng dữ liệu thường bị gọi chung là “token” nhưng khác chức năng:

| Giá trị | Chỗ truyền điển hình | Tác dụng | Không được dùng thay |
| --- | --- | --- | --- |
| **Session cookie** `SESSION`/`JSESSIONID` | Cookie trên HTTP handshake; browser gửi theo cookie policy | Để HTTP Security xác thực session và tạo principal | Không thay CSRF và quyền trên object |
| **Access token** (ví dụ JWT bearer) | HTTP `Authorization: Bearer ...` ở non-browser handshake **hoặc** STOMP native `Authorization` trong CONNECT | Cho backend xác minh danh tính, scopes/authorities | Không mặc nhiên thay CSRF CONNECT |
| **CSRF token** | STOMP native header, thường `X-CSRF-TOKEN` ở CONNECT; cũng có thể dùng cho HTTP requests tương ứng | Chống sử dụng credentials do browser tự gửi trong ngữ cảnh không mong muốn | Không xác thực user/role và không tự cấp ACL |
| **STOMP login/passcode** | STOMP native headers `login`, `passcode` | Một phần giao thức STOMP/broker relay khi phù hợp | Không phải Spring Security application authentication mặc định |

Hai kiến trúc có thể đều tồn tại nhưng **không được trộn ngẫu nhiên**:

**Mô hình A — HTTP inheritance:** người dùng login qua HTTP, cookie phiên được gửi trên handshake, Spring Security xác thực principal rồi Spring Messaging kế thừa principal ấy. Client vẫn có thể cần gửi CSRF token native ở STOMP CONNECT, nhưng **không cần bearer token để xác thực lại** nếu server quyết định chỉ dùng HTTP session.

**Mô hình B — bearer trong STOMP CONNECT:** browser không có session phù hợp hoặc app chủ động dùng token-only. HTTP handshake có thể chưa xác thực; client gửi bearer token trong CONNECT, custom interceptor kiểm chứng và gắn principal trước khi message authorization chạy. Thiết kế này phải xử lý rõ **CSRF CONNECT mặc định, Origin, quyền khi chưa authenticated, rate limits, token expiry và reconnect**.

**Quan trọng:** truyền token là một hành động giao thức, còn xác thực là một phép kiểm tra server-side. Một frame chứa `Authorization: Bearer abc` chỉ là dữ liệu client tự khai cho đến khi token đã được verifier chấp nhận.

## 3. Thứ tự xử lý: GET Upgrade rồi mới STOMP CONNECT

### 3.1. HTTP WebSocket handshake

Browser chạy:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws");
~~~

Với HTTP/1.1, handshake phổ biến:

~~~http
GET /ws HTTP/1.1
Host: api.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example.com
Cookie: SESSION=<cookie-if-present-and-allowed>
~~~

Nếu server chấp nhận:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <handshake-value>
~~~

Header `Origin` là origin của **trang chạy JavaScript**, không phải danh tính người dùng. Với session-cookie authentication, HTTP `SecurityFilterChain` thường xác thực ngay tại bước này. Với bearer-only CONNECT, có thể chưa có authenticated principal trong handshake.

### 3.2. STOMP CONNECT bên trong WebSocket frame

Sau HTTP 101, thư viện STOMP gửi:

~~~text
CONNECT
accept-version:1.2
host:api.example.com
Authorization:Bearer <access-token>
X-CSRF-TOKEN:<csrf-token-if-required>

^@
~~~

`^@` biểu thị byte NUL kết thúc STOMP frame. Các dòng `Authorization` và `X-CSRF-TOKEN` là **STOMP native headers**, không phải HTTP headers. Tại bước CONNECT, một token verifier có thể xác minh bearer token và một thành phần Spring Security Messaging có thể kiểm tra CSRF token theo policy.

Nếu được chấp nhận, client có thể nhận:

~~~text
CONNECTED
version:1.2

^@
~~~

Nếu CONNECT bị từ chối, client có thể nhận `ERROR`/close; **không phải một HTTP 401/403 mới** sau 101.

### 3.3. Luồng tổng thể

~~~mermaid
sequenceDiagram
    participant UI as Browser STOMP client
    participant HTTP as Spring HTTP / Handshake
    participant AUTH as Token ChannelInterceptor
    participant SEC as Messaging Security
    participant APP as Handler / Broker
    UI->>HTTP: GET /ws + Upgrade + Origin (+ Cookie nếu có)
    HTTP->>HTTP: HTTP Security, Origin, TLS/proxy
    HTTP-->>UI: 101 WebSocket established
    UI->>AUTH: STOMP CONNECT + native Authorization
    AUTH->>AUTH: Verify token, create Authentication, setUser
    AUTH->>SEC: CONNECT với principal đã xác thực
    SEC->>SEC: CSRF CONNECT theo policy + authorization
    alt token sai hoặc CONNECT không hợp lệ
        SEC-->>UI: ERROR / close
    else CONNECT hợp lệ
        SEC-->>UI: CONNECTED
        UI->>SEC: SEND /app/orders.lookup
        SEC->>SEC: MESSAGE + destination + authority
        SEC->>APP: Principal + orderId
        APP->>APP: Ownership/tenant permission
        UI->>SEC: SUBSCRIBE /user/queue/order-results
        SEC->>SEC: SUBSCRIBE authorization
        APP-->>UI: MESSAGE chỉ tới subscription/user hợp lệ
    end
~~~

Sơ đồ là luồng logic. Thứ tự thực tế của CSRF và authorization interceptors phụ thuộc cấu hình/version; điều bắt buộc khi authentication tại CONNECT là **principal phải được thiết lập trước khi các bước phụ thuộc vào authentication đánh giá quyền**.

### 3.4. Các điểm không được suy diễn

- HTTP 101 **không đồng nghĩa** STOMP CONNECT đã authenticated.
- STOMP CONNECTED **không đồng nghĩa** mọi SEND/SUBSCRIBE được phép.
- Access token hợp lệ **không đồng nghĩa** user sở hữu mọi order hoặc thuộc mọi tenant.
- Một token đã hợp lệ tại CONNECT **không đồng nghĩa** connection được cấp quyền mãi mãi sau khi token hết hạn hoặc user bị thu hồi.
- Origin hợp lệ **không đồng nghĩa** browser hay client là user ADMIN.

## 4. Vì sao không dùng HTTP Authorization từ JavaScript WebSocket?

### 4.1. Browser WebSocket API có giới hạn có chủ đích

API chuẩn của browser nhận URL và danh sách subprotocol:

~~~javascript
const socket = new WebSocket(
  "wss://api.example.com/ws",
  ["v12.stomp"]
);
~~~

Đối số thứ hai **không phải HTTP request headers**. Không có object `headers`, `credentials: "include"` hoặc `Authorization` tùy ý như HTTP Fetch.

Điều đó khác với:

~~~javascript
await fetch("https://api.example.com/api/orders", {
  headers: { Authorization: "Bearer <access-token>" }
});
~~~

Browser quản lý việc gửi cookie trên handshake theo `Domain`, `Path`, `Secure`, `SameSite` và privacy restrictions. Khi dùng STOMP token-auth trong browser, phải có một transport trước, sau đó gửi token **bên trong STOMP CONNECT**.

### 4.2. Non-browser clients có thể khác

Một Java, Node.js hoặc command-line WebSocket client có thể hỗ trợ custom HTTP handshake headers, bao gồm `Authorization`. Nếu server xác thực ở HTTP handshake, non-browser client có thể gửi bearer token ngay tại HTTP layer; nó không phải lúc nào cũng cần bearer trong STOMP CONNECT.

**Không đồng nhất hai cơ chế:** token ở HTTP Authorization được HTTP security filters xử lý; token ở STOMP CONNECT cần messaging interceptor/verifier hoặc một cơ chế tích hợp riêng. Chúng có thể dùng cùng JWT issuer, nhưng khác thời điểm và principal propagation.

### 4.3. Đừng thay bằng token query string

Phản ví dụ:

~~~javascript
// Không khuyến nghị đặt access token dài hạn trong URL.
new WebSocket(
  "wss://api.example.com/ws?access_token=<bearer-token>"
);
~~~

URL có thể xuất hiện trong gateway/access logs, APM traces, diagnostics và bản ghi giám sát. Nếu hệ thống thực sự cần một vé kết nối qua URL, hãy cân nhắc **short-lived, one-time, audience/connection-bound ticket** với redaction nghiêm ngặt thay vì JWT access token dài hạn.

Một workaround khác là dùng `Sec-WebSocket-Protocol` làm nơi nhét token; header này chủ yếu dùng thương lượng subprotocol, có semantics và logging riêng. Không coi đây là phương án an toàn mặc định nếu chưa thiết kế và kiểm chứng đầy đủ. STOMP native CONNECT headers là cơ chế tự nhiên khi ứng dụng thực sự dùng STOMP.

## 5. STOMP native headers: cách xây frame và đọc dữ liệu

STOMP cung cấp các lệnh `CONNECT`, `SEND`, `SUBSCRIBE`, `UNSUBSCRIBE` và `DISCONNECT`. Mỗi frame có command, native headers, dòng trống và body nếu có.

### 5.1. Authorization nên nằm ở CONNECT để thiết lập principal

~~~text
CONNECT
accept-version:1.2
host:api.example.com
Authorization:Bearer eyJ...<redacted>

^@
~~~

Server cần xác minh token ngay khi nhận CONNECT trước khi tin user/session. Không chỉ gắn token vào mọi `SEND` mà vẫn để CONNECT anonymous; cách đó có thể làm những SUBSCRIBE/frames khác trượt qua bảo vệ nếu policy thiếu.

Với một hệ thống chọn token-auth ở CONNECT, thiết kế nên quy định rõ:

- Header name chính xác, ví dụ `Authorization`.
- Scheme chính xác, ví dụ `Bearer ` rồi tới token.
- Không nhận header trùng lặp hoặc format bất thường.
- Verifier trả về Spring Security `Authentication` có authorities đã được mapping.
- Lỗi thiếu/sai token bị từ chối trước business handler.
- Những frame sau CONNECT dùng principal đã xác minh, **không** lấy username từ frame mới.

### 5.2. CSRF token ở CONNECT là token khác

~~~text
CONNECT
accept-version:1.2
Authorization:Bearer <access-token-if-this-architecture-uses-it>
X-CSRF-TOKEN:<csrf-token-when-required>

^@
~~~

`Authorization` dùng cho xác thực user/token-based scopes. `X-CSRF-TOKEN` dùng cho lớp CSRF của STOMP CONNECT nếu tích hợp Spring Security yêu cầu. **Không lấy access token bỏ vào trường CSRF rồi giả định sẽ hợp lệ.** Cũng không coi CSRF token là bằng chứng user đã có `ROLE_ADMIN`.

Với session-based HTTP authentication, CONNECT có thể chỉ cần CSRF native header, vì principal đã được kế thừa từ HTTP handshake; bearer header là tùy thiết kế, không mặc định bắt buộc cả hai.

### 5.3. `login`, `passcode` không tự là Spring Security identity

Ví dụ:

~~~text
CONNECT
login:admin
passcode:123456

^@
~~~

Không có nghĩa ứng dụng đã xác thực `admin`. Những trường này có thể được dùng cho giao thức/broker relay theo cấu hình, nhưng Spring Security application principal vẫn phải đến từ HTTP authentication hoặc một verifier chuyên biệt. Không bao giờ cấp role bằng cách lấy trực tiếp STOMP `login` hay `userId`.

### 5.4. Token trong SEND/SUBSCRIBE: không được tự tin nếu không verify

Client có thể thêm một native header khác vào SEND:

~~~text
SEND
destination:/app/orders.lookup
Authorization:Bearer <some-token>
content-type:application/json

{"orderId":1001}
^@
~~~

Nhưng nếu server chỉ xác thực token ở CONNECT, header ở SEND không được tự xác minh hoặc đổi principal; đó vẫn là dữ liệu do client khai. Có thể thiết kế hệ thống xác thực lại từng message, nhưng phải làm **có chủ đích**, bảo đảm các loại frames đều được áp dụng policy đúng, và không cho client tự thay danh tính giữa các messages.

## 6. Frontend với @stomp/stompjs: gửi token bằng connectHeaders

Giả sử frontend có một access-token manager đã kiểm soát login/refresh, với hàm `getValidAccessToken()`. Hàm đó là **giao diện ứng dụng minh họa**, không phải API mặc định của `@stomp/stompjs`.

### 6.1. Kết nối bearer-token ở CONNECT

~~~javascript
import { Client } from "@stomp/stompjs";

// Ứng dụng tự triển khai hàm lấy token hợp lệ.
// Không log token hoặc đưa token vào URL.
async function getValidAccessToken() {
  return await authSession.getAccessToken();
}

async function openStompConnection() {
  const token = await getValidAccessToken();

  const client = new Client({
    brokerURL: "wss://api.example.com/ws",
    connectHeaders: {
      Authorization: "Bearer " + token
    },

    // Tùy chính sách, cần refresh token cho lần CONNECT mới.
    reconnectDelay: 3000,

    onConnect: () => {
      client.subscribe(
        "/user/queue/order-results",
        message => {
          const order = JSON.parse(message.body);
          console.log("Order result:", order);
        }
      );

      client.publish({
        destination: "/app/orders.lookup",
        body: JSON.stringify({ orderId: 1001 })
      });
    },

    onStompError: frame => {
      console.error("STOMP connection or message rejected",
        frame.headers.message);
    },

    onWebSocketClose: event => {
      console.warn("WebSocket closed", event.code);
    }
  });

  client.activate();
  return client;
}
~~~

Đoạn code minh họa cách `connectHeaders` chuyển header sang STOMP CONNECT. Nó **không** tự thực hiện authentication ở backend và **không** bảo đảm CSRF CONNECT mặc định của Spring Security đã được đáp ứng. `authSession` cần được hiện thực trong app, có TTL/revocation chính xác. Không lưu access token trong console logs.

### 6.2. Token không nên bị đóng băng qua reconnect

Một điểm dễ lỗi là lấy token một lần khi khởi tạo `Client`, sau đó client tự reconnect hàng giờ. JWT có thể đã hết hạn nhưng CONNECT vẫn dùng chuỗi cũ.

Khi phiên bản `@stomp/stompjs` đang dùng hỗ trợ `beforeConnect` bất đồng bộ, có thể refresh headers:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "wss://api.example.com/ws",
  reconnectDelay: 3000
});

client.beforeConnect = async () => {
  const token = await authSession.getAccessToken();

  client.connectHeaders = {
    Authorization: "Bearer " + token
  };
};

client.onConnect = () => {
  client.subscribe("/user/queue/order-results", frame => {
    console.log(frame.body);
  });
};

client.activate();
~~~

Hãy kiểm tra API `beforeConnect` đúng phiên bản thư viện. Trong production cần xử lý thêm `getAccessToken()` thất bại, refresh token có race, retry/backoff, logout và ngắt vòng reconnect vô hạn khi credentials đã bị thu hồi.

**Nếu Spring Security Messaging yêu cầu CSRF ở CONNECT**, `beforeConnect` cũng phải lấy và gắn **CSRF token hợp lệ** theo cấu hình. Không chỉ có bearer token rồi mặc nhiên CONNECTED.

### 6.3. Tránh retry liên tục khi sai credential

Nếu token bị thu hồi, một client reconnect mỗi vài giây có thể tạo bão kết nối/nhật ký:

~~~text
CONNECT với token sai
  -> ERROR / close
  -> auto-reconnect
  -> CONNECT với cùng token sai
  -> ERROR / close
  -> ...
~~~

Nên xác định lỗi credential không thể phục hồi và dừng client hoặc chuyển tới login/refresh flow, thay vì tiếp tục kết nối bằng token lỗi. Backend cũng cần rate limit các handshake/CONNECT thất bại.

## 7. Truyền cả CSRF token qua STOMP CONNECT

Ở nhiều ứng dụng Spring Security dùng session cookie, token quan trọng nhất cần thêm vào STOMP CONNECT là **CSRF token**. Nó không phải JWT bearer.

### 7.1. HTTP endpoint cấp CSRF token có kiểm soát

Một Spring MVC controller minh họa:

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfTokenController {

    @GetMapping("/api/csrf")
    ResponseEntity<Map<String, String>> csrf(
        @RequestAttribute("_csrf") CsrfToken csrfToken
    ) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", csrfToken.getHeaderName(),
                "token", csrfToken.getToken()
            ));
    }
}
~~~

Ứng dụng **tự triển khai** endpoint này; Spring không tự phát URL `/api/csrf` cho mọi project. Nó phải được bảo vệ bằng authentication/session phù hợp, HTTP CORS chỉ cho frontend tin cậy nếu khác origin, và không cache ở CDN/shared proxy.

Với Spring Security hiện đại, cần kiểm tra `CsrfTokenRepository`, `CsrfTokenRequestHandler` và cách deferred/masked tokens hoạt động. Token được cấp cho frontend và token Spring Messaging xác minh ở CONNECT phải phù hợp **đúng phiên/ngữ cảnh**.

### 7.2. Client mang CSRF native header

~~~javascript
import { Client } from "@stomp/stompjs";

async function connectWithSessionCsrf() {
  const response = await fetch(
    "https://api.example.com/api/csrf",
    { credentials: "include" }
  );

  if (!response.ok) {
    throw new Error("Chưa xác thực hoặc không lấy được CSRF token");
  }

  const { headerName, token } = await response.json();

  const client = new Client({
    brokerURL: "wss://api.example.com/ws",
    connectHeaders: {
      [headerName]: token
    },

    onConnect: () => {
      client.subscribe(
        "/user/queue/order-results",
        frame => console.log(frame.body)
      );
    }
  });

  client.activate();
  return client;
}
~~~

`connectHeaders` chứa **STOMP native headers**, không phải HTTP headers của browser. Trong mô hình session, Spring HTTP Security xác thực principal từ cookie trên handshake; STOMP CONNECT dùng CSRF token để bảo vệ bước messaging.

### 7.3. Nếu kiến trúc thực sự dùng cả bearer và CSRF

Một client có thể thiết lập:

~~~javascript
const headers = {
  Authorization: "Bearer " + accessToken,
  [csrfHeaderName]: csrfToken
};

client.connectHeaders = headers;
~~~

Nhưng **điều kiện thiết kế** phải rõ: access token được verifier dùng để xác thực user; CSRF token thuộc đúng repository/session mà Spring Security Messaging dùng; HTTP handshake có policy phù hợp; thứ tự interceptors cho phép cả hai kiểm tra thành công. Không ghép token của hai user hoặc hai phiên khác nhau và đợi framework tự “hiểu”.

### 7.4. CSRF token không thay role hay object permission

Một CONNECT hợp lệ với CSRF token đúng không có nghĩa:

- `SUBSCRIBE /topic/admin` được phép.
- `SEND /topic/private` được phép.
- User Alice được quyền xem order 2002 của Bob.
- Session còn quyền sau khi logout hoặc role bị thu hồi.

Phân quyền inbound messages và authorization ở service là những bước tiếp theo.

## 8. SockJS + STOMP: cùng native headers, khác transport

Nếu server có:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
        .setAllowedOrigins("https://app.example.com")
        .withSockJS();
}
~~~

thì frontend dùng `sockjs-client` như sau:

~~~javascript
import SockJS from "sockjs-client";
import { Client } from "@stomp/stompjs";

function newSockJsStompClient(token) {
  return new Client({
    webSocketFactory: () =>
      new SockJS("https://api.example.com/ws"),
    connectHeaders: {
      Authorization: "Bearer " + token
    }
  });
}
~~~

Ở SockJS, URL dùng `https://`/`http://`, còn native WebSocket client dùng `wss://`/`ws://`. Dù SockJS chọn WebSocket hay XHR fallback, `connectHeaders` **vẫn** là native STOMP headers bên trong luồng message.

### 8.1. SockJS không làm JavaScript tự đặt HTTP Authorization được

Một số SockJS transports được xây từ browser XHR hoặc các fallback cơ chế cũ; không nên giả định một trường `connectHeaders.Authorization` được gắn vào mọi HTTP request `/ws/**`. Nó nằm trong STOMP CONNECT frame, còn HTTP authentication, CORS, cookie và CSRF của transport vẫn được xử lý **riêng**.

Điều này đặc biệt quan trọng khi backend có rule `/ws/**` phải `authenticated()` ở HTTP layer: nếu không có session cookie và bearer token chỉ tới lúc CONNECT, HTTP route có thể bị từ chối trước. Hãy chọn chiến lược HTTP handshake/transport phù hợp token-only nếu cần, và giới hạn chỉ WebSocket/SockJS paths được kiểm soát.

### 8.2. HTTP XHR POST của SockJS có CSRF riêng

Một số transport fallback dùng requests như:

~~~text
GET  /ws/info
GET  /ws/<server-id>/<session-id>/xhr_streaming
POST /ws/<server-id>/<session-id>/xhr_send
~~~

HTTP `CsrfFilter` có thể từ chối POST `xhr_send` nếu nó không mang HTTP CSRF token theo cấu hình hiện tại. Đó là **CSRF HTTP transport**, khác với **CSRF ở STOMP CONNECT**.

Nếu framework/transport cần exception, chỉ loại trừ **đúng những transport HTTP paths** sau khi xác minh; không tắt toàn bộ CSRF của REST API. Phải tiếp tục kiểm tra STOMP CONNECT và SEND/SUBSCRIBE.

### 8.3. CORS/SockJS headers cũng không đồng nghĩa Origin của native WebSocket

XHR fallback có thể chịu `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials` và preflight OPTIONS. Native WebSocket không sử dụng Fetch CORS preflight/ACAO theo cùng cơ chế. Spring SockJS có thể phát CORS headers cho transport tương ứng; reverse proxy hoặc HTTP CORS filters cấu hình chồng chéo có thể làm response sai.

Nếu SockJS XHR báo CORS nhưng native WebSocket chạy, đừng sửa native STOMP token verifier trước khi kiểm tra transport HTTP. Ngược lại, nếu HTTP transport 200 nhưng CONNECT bị từ chối, cần đọc STOMP frame/CSRF/token authentication.

## 9. Servlet/STOMP server: đăng ký endpoint và Origin policy

Một cấu hình Spring WebSocket Message Broker cơ bản:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class StompEndpointConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry endpoints) {
        endpoints.addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry broker) {
        broker.setApplicationDestinationPrefixes("/app");
        broker.setUserDestinationPrefix("/user");
        broker.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

`addEndpoint("/ws")` là điểm bắt tay HTTP. `setAllowedOrigins(...)` bảo vệ website nguồn khi browser mở WebSocket, không phải role của user. `/app` dành cho client commands vào handler; `/topic` và `/queue` dành cho broker phát dữ liệu.

**Không dùng wildcard Origin chỉ vì app đang gửi bearer token**. Một trang khác origin có thể thử kết nối; dù verifier từ chối token sai, việc giới hạn trusted browser origins vẫn giảm bề mặt tấn công và hỗ trợ chống CSWSH ở các luồng cookie/session.

## 10. Chọn HTTP SecurityFilterChain nhất quán với loại token

### 10.1. Nếu kế thừa HTTP session principal

Một mô hình dùng session/form login:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SessionHandshakeSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/ws", "/ws/**").authenticated()
                .requestMatchers("/api/csrf").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

HTTP Spring Security xác thực session trên `GET /ws` rồi Spring WebSocket kế thừa principal. STOMP client chủ yếu cần CSRF native header cho CONNECT theo Spring Messaging policy.

Điều kiện: browser gửi cookie và backend có session store/login mechanism tương ứng; `/api/csrf` có HTTP CORS đúng nếu frontend/API khác origin.

### 10.2. Nếu bearer token chỉ đến trong STOMP CONNECT

Đây là một **kiến trúc khác**. Nếu vẫn yêu cầu HTTP `/ws` `authenticated()` nhưng client không có cookie/HTTP bearer, handshake sẽ nhận 401/redirect trước khi STOMP CONNECT được truyền. Với native-only endpoint `/ws`, HTTP layer có thể cho phép một **handshake chưa authenticated nhưng có kiểm soát** để verifier xác thực trên CONNECT.

Phác thảo một **chain hẹp chỉ áp dụng vào handshake endpoint**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BearerConnectHandshakeSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain wsHandshakeChain(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher("/ws")
            .authorizeHttpRequests(auth -> auth
                // Chỉ là bước transport, KHÔNG cấp quyền message.
                .anyRequest().permitAll())
            .build();
    }
}
~~~

**Cảnh báo kiến trúc quan trọng:**

- Đây chỉ là **phác thảo một phần**, không phải cấu hình production đầy đủ. Mọi HTTP API khác cần security chains riêng; không để default chain vô tình mở quyền.
- HTTP GET handshake có thể mở anonymous, nhưng **không được chấp nhận STOMP SEND/SUBSCRIBE hay phát dữ liệu riêng cho đến khi CONNECT bearer token đã được xác minh**.
- Phải có Origin allowlist, TLS, giới hạn handshake/connections và rate limits trước/đúng thời điểm này.
- Nếu bật SockJS, các paths `/ws/**` còn chứa HTTP transport requests với cookie/CORS/CSRF khác; không được mở `permitAll("/ws/**")` hoặc tắt HTTP CSRF theo kiểu bao trùm mà chưa phân tích.
- Cấu hình Spring Security WebSocket Messaging có thể **vẫn yêu cầu CSRF ở CONNECT**. Cho handshake anonymous không tự giải quyết việc CSRF token xuất phát từ nguồn nào. Phải đánh giá và kiểm thử policy đúng phiên bản/framework/threat model; không suy luận JWT tự tắt CSRF.
- Nếu ứng dụng có nhiều `SecurityFilterChain`, phải kiểm tra thứ tự matcher và entry points đúng request thực tế.

### 10.3. Một ranh giới ẩn: token-only có thể không có HTTP session CSRF

Trong token-only model không có session cookie, `CsrfTokenRepository` dạng HTTP session có thể chưa có token gắn session để client lấy trước CONNECT. Khi dùng `@EnableWebSocketSecurity`, yêu cầu kiểm tra CSRF ở CONNECT vẫn cần được giải quyết rõ theo cấu hình bảo mật được hỗ trợ.

**Đừng áp dụng mù quáng một snippet "JWT-only + @EnableWebSocketSecurity" rồi cho rằng CONNECT sẽ hoạt động không cần CSRF.** Hãy lựa chọn:

1. Thiết kế HTTP/session hoặc token repository có nguồn CSRF tương thích nếu muốn bảo vệ CONNECT theo mặc định.
2. Hoặc dùng một cơ chế cấu hình/tích hợp security phù hợp được Spring Security version hỗ trợ khi threat model thực sự không dùng ambient cookie credentials — có review và test âm/dương.
3. Trong cả hai trường hợp phải giữ authentication đúng, Origin validation, message deny-by-default, ownership ACL và revocation.

Không tắt mọi HTTP CSRF hoặc vô hiệu hóa cả message authorization chỉ để vượt lỗi CONNECT.

## 11. Server-side ChannelInterceptor xác thực native bearer token

Đây là phần quyết định sự an toàn của kiến trúc bearer tại STOMP CONNECT. Native header do client khai là dữ liệu chưa tin cậy; interceptor phải **xác minh thật**, sau đó gắn principal đúng cách trước messaging authorization.

### 11.1. Hợp đồng verifier

Tạo một service có trách nhiệm:

~~~java
import org.springframework.security.core.Authentication;

interface StompAccessTokenVerifier {

    // Chỉ trả về Authentication đã xác thực khi token thật sự hợp lệ.
    // Thiếu/sai/expired/revoked token -> ném AuthenticationException.
    Authentication verifyBearerHeader(String authorizationHeader);
}
~~~

Một implementation JWT cần thực hiện hoặc cấu hình:

- Xác minh chữ ký với key material phù hợp, thuật toán cho phép; không tin `alg` do token tự đề xuất một cách không kiểm soát.
- Xác minh `iss` (issuer), `aud` (audience) của tài nguyên realtime, `exp`, `nbf` và thời gian hệ thống.
- Xác minh token có đúng mục đích **access token**/scope phù hợp, không chấp nhận ID token hoặc refresh token làm access token.
- Xử lý user bị khóa, token bị thu hồi, thay đổi quyền, tenant membership theo mức độ rủi ro.
- Map JWT claims thành Spring Security authorities một cách có kiểm soát; không nhận role text tự khai trong STOMP frame.
- Không log token; lỗi được trả về dạng tổng quát và audit metadata tối thiểu.
- Chặn token trống, token không có `Bearer ` đúng format, token quá dài và native header trùng lặp.

Nếu dùng Spring Security OAuth2 Resource Server, `JwtDecoder` và `JwtAuthenticationConverter` là các khối hỗ trợ, nhưng cần **cấu hình JWT validators phù hợp**; việc có decoder không tự chứng minh audience/tenant/scope đã được kiểm tra đúng mục tiêu realtime.

### 11.2. Interceptor gắn Authentication tại CONNECT

~~~java
import java.util.List;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;

final class BearerConnectInterceptor implements ChannelInterceptor {

    private final StompAccessTokenVerifier tokens;

    BearerConnectInterceptor(StompAccessTokenVerifier tokens) {
        this.tokens = tokens;
    }

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(
                message, StompHeaderAccessor.class
            );

        if (accessor == null
                || !StompCommand.CONNECT.equals(accessor.getCommand())) {
            return message;
        }

        // STOMP native header; KHÔNG phải HTTP Authorization.
        List<String> values =
            accessor.getNativeHeader("Authorization");

        if (values == null || values.size() != 1) {
            throw new BadCredentialsException(
                "Missing or ambiguous STOMP credentials"
            );
        }

        // Chỉ trả Authentication khi verifier đã xác minh token.
        Authentication verified =
            tokens.verifyBearerHeader(values.get(0));

        if (verified == null || !verified.isAuthenticated()) {
            throw new BadCredentialsException(
                "Invalid STOMP credentials"
            );
        }

        accessor.setUser(verified);
        return message;
    }
}
~~~

Đoạn code cho thấy **điểm xác thực**, không phải implementation đầy đủ của JWT verifier. `getNativeHeader` cho phép phát hiện multiple values; lấy giá trị đầu tiên trong khi bỏ qua phần còn lại có thể tạo sự mơ hồ giữa các tầng xử lý.

`StompHeaderAccessor#setUser(authentication)` giúp Spring Messaging gắn principal đã xác minh với STOMP session để message authorization/handlers nhìn thấy đúng người. Nó **không làm Spring HTTP SecurityFilterChain chạy lại** trên CONNECT, và không tự giải quyết CSRF CONNECT.

### 11.3. Đăng ký interceptor trước Spring Security Messaging

Ví dụ Spring Servlet Messaging:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
class ConnectAuthenticationChannelConfiguration
        implements WebSocketMessageBrokerConfigurer {

    private final StompAccessTokenVerifier tokens;

    ConnectAuthenticationChannelConfiguration(
        StompAccessTokenVerifier tokens
    ) {
        this.tokens = tokens;
    }

    @Override
    public void configureClientInboundChannel(
        ChannelRegistration registration
    ) {
        registration.interceptors(
            new BearerConnectInterceptor(tokens)
        );
    }
}
~~~

Giá trị order trên là **một mẫu định hướng thường dùng** để đăng ký custom CONNECT authentication interceptor trước Spring Security messaging interceptors. Thứ tự thực tế cần kiểm chứng với Spring/Security version và những configurers có sẵn. Không cài thêm nhiều interceptors tự thay principal sau authorization.

Nếu interceptor chạy **sau** message authorization, Spring có thể đánh giá `CONNECT` hoặc `SEND` khi principal còn anonymous, khiến CONNECT thất bại hoặc hành vi không nhất quán. Test phải xác nhận thứ tự đúng bằng **một CONNECT token hợp lệ và một CONNECT token sai** trước khi đưa hệ thống vào production.

### 11.4. Authentication tại CONNECT ảnh hưởng những frame sau

Khi CONNECT được xác minh và principal được gắn:

~~~text
CONNECT Authorization:Bearer valid
     -> Authentication alice (ROLE_USER)
     -> CONNECTED

SEND /app/orders.lookup
     -> Message security thấy principal alice
     -> Controller nhận Principal alice
     -> Business service xác minh Alice có quyền orderId

SUBSCRIBE /topic/admin
     -> Message security từ chối nếu alice không có ROLE_ADMIN
~~~

Một user không được tự đổi principal bằng cách gửi `username:bob` ở SEND. Token hết hạn sau khi CONNECT cũng cần thiết kế revalidate/reconnect/close; không trông chờ interceptor chỉ bắt CONNECT tự xử lý sự kiện token expiry sau nhiều giờ.

## 12. Spring Security message authorization phải bảo vệ cả CONNECT/SEND/SUBSCRIBE

Một ứng dụng có thể bật Spring Security WebSocket Messaging và khai báo:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
class StompInboundAuthorization {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
        MessageMatcherDelegatingAuthorizationManager.Builder messages
    ) {
        return messages
            .nullDestMatcher().authenticated()

            .simpSubscribeDestMatchers("/app/**")
                .denyAll()

            .simpSubscribeDestMatchers(
                "/user/queue/order-results",
                "/topic/public"
            ).authenticated()

            .simpDestMatchers("/app/orders.lookup")
                .hasRole("USER")

            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()

            .anyMessage().denyAll()
            .build();
    }
}
~~~

### 12.1. Vì sao rule này cần cho token-auth?

Token verifier chỉ biết token có hợp lệ và gắn authorities gì. Nó **không biết** mọi STOMP destination có được phép hay không. Message authorization:

- Buộc principal tồn tại khi xử lý control frames không có destination trong ví dụ.
- Chỉ cho client SUBSCRIBE vào những destinations được phê duyệt.
- Chỉ cho SEND vào application destination có role phù hợp.
- Không cho client SEND trực tiếp vào broker `/topic/**`, tránh giả mạo messages.
- Deny các MESSAGE/SUBSCRIBE còn lại và deny-by-default.

Matcher được xét theo thứ tự; không đặt `simpDestMatchers("/topic/**").authenticated()` trước rule deny MESSAGE, vì nó có thể cấp quyền gửi trực tiếp vào broker.

### 12.2. CSRF CONNECT vẫn là kiểm tra độc lập

Trong Spring Security Messaging với `@EnableWebSocketSecurity`, CSRF CONNECT là một lớp riêng. `nullDestMatcher().authenticated()` chứng minh principal đã được xác minh, **không** thay `CsrfChannelInterceptor` hoặc kiểm tra token CSRF phù hợp.

Một thiết kế bearer-only không dùng cookie có thể có threat model CSRF khác, nhưng **không có nghĩa** `@EnableWebSocketSecurity` tự nhận ra và bỏ CSRF. Phải xem cấu hình Spring Security version, cách repository/handler cấp token và thực nghiệm CONNECT thật; nếu thay đổi chính sách phải được review có chủ đích.

### 12.3. Role không phải quyền trên object

`hasRole("USER")` chỉ cho phép user gửi lệnh vào `/app/orders.lookup`. Nó không quyết định user có quyền đọc order cụ thể nào. Service còn phải kiểm tra principal, orderId, tenant, scope/membership và trạng thái quyền hiện tại.

### 12.4. Inbound protection không tự bảo vệ outbound routing

Spring Security Messaging tập trung kiểm tra **client inbound channel**. Nếu server phát nhầm nội dung Bob vào `/topic/public` hoặc dùng sai user destination, inbound authorization không tự sửa lỗi.

Với dữ liệu riêng, cần bảo vệ `SUBSCRIBE`, kiểm tra quyền trước publish và route đúng user/session/tenant.

## 13. Controller và quyền nghiệp vụ sau khi token được xác minh

Ví dụ `@MessageMapping` nhận principal từ messaging context:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

record OrderLookup(long orderId) {}
record OrderSummary(long orderId, String state) {}

interface OrderService {
    // Implementation thực phải từ chối khi không đúng user/tenant.
    OrderSummary findVisibleOrder(String username, long orderId);
}

@Controller
class OrderRealtimeController {

    private final OrderService orders;
    private final SimpMessagingTemplate messaging;

    OrderRealtimeController(
        OrderService orders,
        SimpMessagingTemplate messaging
    ) {
        this.orders = orders;
        this.messaging = messaging;
    }

    @MessageMapping("/orders.lookup")
    void lookup(@Payload OrderLookup input, Principal principal) {
        String username = principal.getName();

        OrderSummary result = orders.findVisibleOrder(
            username, input.orderId()
        );

        messaging.convertAndSendToUser(
            username,
            "/queue/order-results",
            result
        );
    }
}
~~~

Nếu Alice được xác thực bằng bearer token nhưng gửi `{"orderId":2002}` của Bob, `findVisibleOrder` phải từ chối. Không lấy userId từ payload để thay principal. Server phải kiểm tra quyền với dữ liệu thực, không chỉ URI/destination.

### 13.1. User destination không phải dữ liệu công khai

Client Alice subscribe:

~~~text
SUBSCRIBE
id:sub-1
destination:/user/queue/order-results

^@
~~~

`/user` hỗ trợ user-based destinations trong Spring Messaging. Nhưng một user có thể có nhiều WebSocket sessions; server cần quyết định có phát tới **tất cả sessions của user** hay chỉ một session và kiểm thử multi-node routing.

Nếu dùng external broker relay, còn phải bảo vệ kết nối tới broker, broker ACLs, tenant routing và logging. Header `login`/`passcode` mà relay dùng không thay authentication của ứng dụng.

### 13.2. Không cấp quyền bằng Origin

Cả Alice và Bob có thể kết nối từ `https://app.example.com`. Một client non-browser còn có thể giả `Origin: https://app.example.com`. Do đó đừng dùng Origin để xác minh user hoặc gán role ADMIN. Token verifier và business ACL quyết định các quyền đó.

## 14. Token expiry, refresh, logout và thu hồi trong WebSocket dài hạn

Đây là hạn chế quan trọng của **chỉ xác thực tại CONNECT**.

### 14.1. JWT hết hạn sau khi CONNECT

Giả sử JWT của Alice hết hạn lúc 10:00 nhưng STOMP session được thiết lập lúc 09:50. Nếu server chỉ xác minh JWT khi CONNECT và giữ principal trong socket, token hết hạn **không tự động đóng WebSocket hoặc hủy subscriptions**.

Các lựa chọn:

- Giới hạn thời gian tồn tại connection bằng TTL của token/session.
- Đóng connection khi token hết hạn và yêu cầu CONNECT mới với token hợp lệ.
- Revalidate authorities/permissions ở những SEND/SUBSCRIBE nhạy cảm.
- Khi phát dữ liệu riêng, kiểm tra membership/ACL hiện tại hoặc thu hồi subscriptions bị mất quyền.
- Dùng revocation event để đóng sessions thuộc user/token bị thu hồi.
- Theo dõi token ID/expiry trong session state được quản lý an toàn, tránh logs chứa token thô.

### 14.2. Refresh không nên gửi token mới tùy tiện trong SEND

Một số nhóm thử gửi:

~~~text
SEND
destination:/app/auth.refresh
Authorization:Bearer <new-access-token>

^@
~~~

rồi cho rằng Spring Messaging tự đổi principal. **Không đúng** nếu app không thiết kế một protocol reauthentication có kiểm chứng. Khuyến nghị đơn giản hơn: refresh token bằng luồng authentication HTTP phù hợp, rồi **reconnect STOMP** với bearer mới, đóng connection cũ. Nếu cần reauth-in-place, phải kiểm tra toàn diện tính nguyên tử, bảo mật phiên, replay và thứ tự messages.

### 14.3. Logout

Một luồng logout phù hợp:

1. Frontend hủy subscriptions/deactivate STOMP client.
2. Application thu hồi session/access/refresh tokens theo chiến lược đang dùng.
3. Backend thu hồi hoặc đóng WebSocket connections cũ nếu cần bảo đảm không tiếp tục nhận dữ liệu.
4. Frontend xóa trạng thái identity, không auto-reconnect bằng token đã thu hồi.
5. Service kiểm tra quyền hiện thời ở những thao tác/publish nhạy cảm.

Chỉ gọi logout HTTP **không mặc nhiên** làm một WebSocket có principal cũ biến mất ngay trên mọi topology. Spring Session có tích hợp quản lý session WebSocket ở những cấu hình thích hợp, cần kiểm thử chứ không giả định.

### 14.4. Nhiều tab và nhiều server nodes

Một user có thể mở nhiều WebSocket sessions với tokens khác nhau. Một load balancer có thể chuyển SockJS HTTP fallback requests giữa backend nodes. Phải đảm bảo:

- Session store/affinity phù hợp.
- Token verifier đồng nhất key/issuer/audience trên nodes.
- Revocation/role changes được phát tán.
- `SimpUserRegistry` và user destinations được route phù hợp với broker/cluster.
- Không phát nhầm dữ liệu khi user thay tenant giữa các tabs.

## 15. Bảo mật token trong logs và hạ tầng

### 15.1. TLS và hạn chế logging

Dùng `wss://` và `https://` cho production, certificate hợp lệ, proxy route đúng và HSTS khi phù hợp. Không bật raw STOMP frame logging ở mức ghi toàn bộ `CONNECT` trong production vì frame có thể chứa bearer/CSRF tokens.

Redact:

- `Authorization` native STOMP header.
- `X-CSRF-TOKEN` và các custom security headers.
- HTTP `Cookie`/`Set-Cookie`.
- Query strings chứa token/vé kết nối.
- Nội dung order/chat/message riêng tư.
- Kết quả token introspection/JWT claims không cần thiết.

Logs có thể ghi message type, correlation ID, user ID nội bộ phù hợp, destination và lý do từ chối đã được làm sạch; không ghi token thô.

### 15.2. Giới hạn tài nguyên và abuse

Native WebSocket có thể được mở cross-origin nếu server cho phép. Với token-only handshake chưa authenticated, có khả năng attacker tạo nhiều connections trước CONNECT. Cần:

- Handshake/connection rate limiting theo IP/network/user khi xác thực được.
- Timeout cho kết nối không gửi CONNECT hợp lệ.
- Giới hạn số connections/threads/session resources.
- Giới hạn frame payload size và STOMP header size.
- Giới hạn số SUBSCRIBE và tốc độ SEND/CONNECT/reconnect.
- Backpressure/send buffers/heartbeat/idle close.
- Từ chối unknown destinations và malformed native headers.

Những biện pháp này **không thay token verification** nhưng giúp bảo vệ availability.

### 15.3. CSP và CORS có trách nhiệm khác

- CSP `connect-src` ở frontend kiểm soát trang đó được gọi HTTP/WebSocket destinations nào. Nó **không** là server-side authorization.
- HTTP CORS cho endpoint lấy CSRF/access token quyết định JavaScript khác origin có được đọc response không.
- Native WebSocket handshake **không dùng Fetch CORS preflight/ACAO**; dùng Origin validation của WebSocket endpoint.
- SockJS XHR fallback có thể chịu HTTP CORS/CSRF.
- HTTP firewall xử lý malformed HTTP handshakes; không là JWT/STOMP token verifier.

## 16. Reactive/WebFlux native WebSocket: không tự có STOMP CONNECT

Spring WebFlux native cung cấp `WebSocketHandler`/`WebSocketSession` cho text/binary frames. Nó **không mặc định là STOMP Message Broker Servlet**. Nếu ứng dụng WebFlux chỉ dùng native WebSocket, không thể đặt `@EnableWebSocketSecurity` rồi mong nó tự đọc `Authorization` trong một CONNECT frame không tồn tại.

### 16.1. HTTP handshake security bằng ServerHttpSecurity

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveWebSocketHttpSecurity {

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/ws").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Cấu hình này giả định authentication đã có trên HTTP handshake (ví dụ session cookie hoặc non-browser bearer). Browser WebSocket constructor không tự thêm Authorization HTTP header; nếu token chỉ trong first message, route `authenticated()` có thể chặn handshake trước. Cần chọn mô hình nhất quán như Servlet.

### 16.2. Origin guard và message security là các lớp riêng

Với WebFlux, triển khai Origin guard ở handshake/`WebFilter`/adapter phù hợp. Một native handler nên nhận principal từ handshake khi HTTP authentication được sử dụng:

~~~java
import java.security.Principal;

import reactor.core.publisher.Mono;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.reactive.socket.WebSocketHandler;

interface RealtimeMessageService {
    Mono<Void> validateAuthorizeAndHandle(
        Principal principal, String payload
    );
}

class SecureNativeWebSocketHandler {

    static WebSocketHandler create(RealtimeMessageService service) {
        return session -> session.getHandshakeInfo()
            .getPrincipal()
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Unauthenticated")))
            .flatMap(principal ->
                session.receive()
                    .concatMap(frame ->
                        service.validateAuthorizeAndHandle(
                            principal, frame.getPayloadAsText()
                        ))
                    .then()
            );
    }
}
~~~

Mã là khung minh họa, chưa có `HandlerMapping`/adapter, outbound sending, backpressure hoặc parsing. Khi app cần **first-message token authentication** thay vì HTTP principal, phải xây protocol riêng: chỉ sau khi verifier hoàn thành mới cho các message khác đi qua. Không dùng một JSON field `userId` tự khai làm principal.

### 16.3. Phân biệt ba lựa chọn trong Reactive

| Trường hợp | Cơ chế xác thực |
| --- | --- |
| WebFlux native + session login | Principal từ HTTP handshake; verify cookie/session bằng Reactive Security |
| WebFlux native + token trong first message | Tự xây message token verification + gating/CSRF strategy + Origin guard |
| STOMP over một giải pháp Reactive bên ngoài | Theo thư viện/broker cụ thể; không sao chép nguyên `WebSocketMessageBrokerConfigurer` Servlet |

`CorsWebFilter` và HTTP security không tự kiểm tra quyền từng text/binary frame sau khi socket mở.

## 17. Ma trận kiểm thử token trong STOMP headers

### 17.1. Handshake/Origin

| Mã | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| H1 | Origin app, session hợp lệ với HTTP-inheritance model | Handshake được chấp nhận |
| H2 | Origin evil, cùng session hợp lệ | Bị Origin policy từ chối |
| H3 | HTTP-inheritance model, không có session | HTTP authentication từ chối |
| H4 | Token-only model, Origin app, HTTP handshake chưa có auth | Transport có thể mở nếu policy cho phép; không cấp quyền message |
| H5 | Non-browser giả Origin app, không bearer hợp lệ | Không vượt CONNECT authentication |
| H6 | CSP chặn `wss://api.example.com` | Browser có thể không gửi handshake; không coi là JWT lỗi |
| H7 | Gateway không hỗ trợ Upgrade | Không lên transport; không tới CONNECT |

### 17.2. Token verifier trên CONNECT

| Mã | Native Authorization header | Kỳ vọng |
| --- | --- | --- |
| T1 | `Bearer <valid-access-token>` đúng issuer/audience/scope | Xác thực principal, sau đó CONNECT phụ thuộc CSRF/policy |
| T2 | Thiếu header | Bị token-auth interceptor từ chối |
| T3 | `Bearer ` trống hoặc không đúng format | Bị từ chối |
| T4 | Token sai chữ ký | Bị từ chối |
| T5 | Token hết `exp` hoặc chưa tới `nbf` | Bị từ chối |
| T6 | `iss` không tin cậy | Bị từ chối |
| T7 | `aud` sai service realtime | Bị từ chối |
| T8 | JWT ID token/refresh token thay access token | Bị từ chối theo token-use policy |
| T9 | Token hợp lệ nhưng scope không đủ | CONNECT hoặc SEND/SUBSCRIBE bị từ chối tùy rule |
| T10 | Hai native `Authorization` headers | Bị từ chối do format mơ hồ |
| T11 | Client gửi `login:admin` nhưng bearer là Alice | Principal không đổi thành admin |
| T12 | Token từ phiên/user Bob trong connection Alice khi có binding policy | Bị từ chối theo chính sách binding; không tin client-provided ID |
| T13 | Token đã bị thu hồi | Bị từ chối theo revocation policy |
| T14 | HTTP 101 thành công nhưng token CONNECT sai | Không nhận CONNECTED; không xử lý business message |
| T15 | Bearer hợp lệ, thiếu CSRF khi Spring Messaging yêu cầu | CONNECT bị CSRF layer từ chối |

### 17.3. Sau CONNECT

| Mã | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| M1 | `SEND /app/orders.lookup` của Alice với role USER | Được kiểm tra object ACL |
| M2 | Client `SEND /topic/public` trực tiếp | Deny |
| M3 | Client `SUBSCRIBE /topic/admin` không role ADMIN | Deny |
| M4 | Alice gửi `{"orderId":2002}` của Bob | Service từ chối, không phát data Bob |
| M5 | Alice tự khai `username:bob` ở SEND | Principal vẫn Alice |
| M6 | Token Alice hết hạn sau CONNECT | Revocation/revalidate/reconnect policy có tác dụng |
| M7 | Logout/đổi tenant trong socket còn mở | Không tiếp tục nhận dữ liệu trái quyền |
| M8 | Client CONNECT liên tục với token sai | Rate limit và resource controls hoạt động |

**Assertion quan trọng:** một test âm phải chứng minh **không có data leak, không có side effect** và không chỉ dựa vào frame `ERROR`.

## 18. Integration tests với Spring WebSocketStompClient

Một bộ test đúng nên chạy HTTP/WebSocket server thật và sử dụng `WebSocketStompClient` cùng `StandardWebSocketClient` cho stack Servlet/STOMP.

### 18.1. Phân biệt các công cụ

| Công cụ | Test tốt | Không thay thế |
| --- | --- | --- |
| `MockMvc` | HTTP authentication, CORS, endpoint CSRF, HTTP matchers | WebSocket Upgrade + STOMP CONNECT/SEND/SUBSCRIBE end-to-end |
| `WebSocketStompClient` | HTTP handshake thật, native STOMP CONNECT headers, CONNECTED/ERROR, SEND/SUBSCRIBE | Browser CSP/SOP/cookie-specific behavior |
| Browser DevTools | Origin, Cookie, handshake status, frames, CSP errors | Server-side authorization assertions |
| Non-browser WebSocket client | Custom Origin/HTTP headers, malformed STOMP frames | Browser SOP |
| Unit tests token verifier | JWT signature/issuer/audience/expiry/scopes | Interceptor wiring/order |
| Service ACL tests | BOLA/IDOR/tenant ownership | Transport và CONNECT flow |

### 18.2. Chuẩn bị kết nối kiểm thử

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

// Skeleton cho một integration test có test server thực:
WebSocketStompClient client = new WebSocketStompClient(
    new StandardWebSocketClient()
);

WebSocketHttpHeaders httpHeaders = new WebSocketHttpHeaders();
httpHeaders.setOrigin("https://app.example.com");

// Chỉ cần cookie với mô hình HTTP session.
httpHeaders.add(HttpHeaders.COOKIE, "SESSION=" + testSessionCookie);

StompHeaders connectHeaders = new StompHeaders();
connectHeaders.add("Authorization", "Bearer " + testAccessToken);

// Nếu Spring Security Messaging yêu cầu CSRF CONNECT:
connectHeaders.add(testCsrfHeaderName, testCsrfToken);

// client.connectAsync(uri, httpHeaders, connectHeaders, sessionHandler);
// Chờ CONNECTED / ERROR / closed và assert trong timeout.
~~~

Các `testSessionCookie`/`testAccessToken`/`testCsrfToken` phải được setup test cấp đúng; **không phải** giá trị copy cứng. Với bearer-only token model, HTTP handshake có thể không có cookie; với session model, có thể không cần `Authorization` STOMP. Skeleton chưa phải test chạy độc lập và method overload/handler details phụ thuộc phiên bản Spring.

### 18.3. Test thứ tự ChannelInterceptor

Test rất quan trọng:

~~~text
Given:
  - Spring WebSocket endpoint /ws đang hoạt động.
  - BearerConnectInterceptor được đăng ký trên inbound channel.
  - @EnableWebSocketSecurity + message AuthorizationManager đang bật.
  - Token verifier trả Alice ROLE_USER cho token đúng.
  - Có CONNECT CSRF setup phù hợp với policy thực tế.

Positive:
  1) Handshake với Origin hợp lệ.
  2) STOMP CONNECT có native bearer đúng.
  3) Verify CONNECTED và server nhận principal Alice.
  4) SEND /app/orders.lookup cho order Alice.
  5) Verify handler nhìn thấy Alice và trả đúng dữ liệu.

Negative:
  A) CONNECT không có bearer -> từ chối.
  B) CONNECT bearer sai -> từ chối, không có Authentication.
  C) CONNECT có bearer trùng header -> từ chối.
  D) CONNECT đúng bearer nhưng CSRF thiếu khi bật -> từ chối.
  E) CONNECT đúng, SEND /topic/public -> từ chối.
  F) CONNECT đúng, Alice hỏi order Bob -> không trả dữ liệu.
  G) Token hết hạn, revoked, sai audience/issuer -> từ chối.

Acceptance:
  - Auth interceptor chạy trước authorization.
  - Không có SEND/SUBSCRIBE được thực thi trước verified CONNECT.
  - Không có data leak/side effect khi bị deny.
~~~

**Đừng chỉ assert HTTP 101.** HTTP 101 có thể thành công rồi CONNECT bị từ chối. Test cũng phải tránh race trong việc kiểm tra các message được phép/bị từ chối.

### 18.4. Test browser hai origins

Tại hai frontend test origins do nhóm sở hữu, dùng STOMP client và quan sát:

1. HTTP `GET /ws` có `Origin` chính xác, cookie nếu có.
2. Có CSP `connect-src` hoặc TLS lỗi trước khi request tới server không.
3. HTTP handshake thành công hay bị Origin/HTTP auth từ chối.
4. STOMP CONNECT frame có `Authorization` native và CSRF native header nếu cần.
5. Có CONNECTED khi token đúng, ERROR/close khi token sai.
6. Sau CONNECT, SEND/SUBSCRIBE đúng policy và dữ liệu route đúng user.
7. Browser ở origin lạ không thể vượt Origin allowlist ngay cả khi token bị client lộ/truyền nhầm.

Không dùng tài khoản/dữ liệu production và không chia sẻ token thô khi chụp DevTools.

## 19. Những lỗi dễ gặp và cách xử lý

| Triệu chứng | Nơi cần điều tra | Hướng xử lý |
| --- | --- | --- |
| HTTP handshake 401/302, token chỉ ở STOMP CONNECT | HTTP Security yêu cầu authenticated trước CONNECT | Chọn kiến trúc handshake nhất quán, không tùy tiện mở API khác |
| Browser không gắn HTTP Authorization | WebSocket constructor không hỗ trợ arbitrary headers | Dùng STOMP native `connectHeaders` với verifier ở server |
| HTTP 101 nhưng không CONNECTED | Bearer verifier/CSRF CONNECT/message policy | Đọc STOMP frame và reason, không chỉ HTTP |
| Client có native Authorization nhưng Principal null | ChannelInterceptor chưa đăng ký/chạy sai thứ tự | Xem `configureClientInboundChannel` và `setUser` |
| Client có token sai vẫn CONNECTED | Verifier không từ chối hoặc policy thiếu | Kiểm tra signature/issuer/audience/exp và negative tests |
| Token hợp lệ nhưng thiếu role | Claims-to-authorities mapping sai | Kiểm tra scope/role conversion, không lấy role tự khai |
| JWT dùng sai `aud` nhưng vẫn pass | Decoder validators chưa đủ | Thêm audience validation cho realtime API |
| CONNECT có duplicate headers và app chọn header đầu | Format mơ hồ | Reject duplicates và oversized native headers |
| CONNECT bearer đúng nhưng CSRF fail | `@EnableWebSocketSecurity` CONNECT CSRF vẫn bật | Lấy/gửi token đúng hoặc thiết kế CSRF strategy được review |
| Token bị ẩn qua masking/deferred CSRF mismatch | HTTP repository/handler khác ngữ cảnh Messaging | Test đúng session/token format |
| Reconnect gửi JWT cũ rồi lặp lỗi | Token được tạo lúc constructor, không refresh | Sử dụng `beforeConnect` và dừng khi credential revoked |
| SockJS XHR POST 403, native WS tốt | HTTP CSRF transport hoặc gateway | Xem SockJS URLs/CORS và exception rất hẹp |
| Fetch `/api/csrf` lỗi CORS | HTTP CORS khác WebSocket Origin policy | ACAO/ACAC đúng frontend; không mở wildcard |
| Browser CSP `connect-src` chặn WSS | Frontend CSP | Chỉ thêm endpoint tin cậy vào connect-src |
| Kết nối từ website lạ được chấp nhận | WebSocket Origin allowlist thiếu/rộng | Siết `setAllowedOrigins` và negative test |
| Non-browser giả Origin app được cấp admin data | Dùng Origin thay auth/ACL | Token verifier và object permissions server-side |
| Client SEND `/topic/admin` rồi broker phát | Message matcher destination-only quá rộng | Cấm inbound MESSAGE tới broker |
| Alice nhận order Bob dù JWT hợp lệ | Thiếu business object ACL | Kiểm tra ownership/tenant trước gửi |
| Sau logout websocket vẫn hoạt động | Token auth chỉ tại CONNECT, thiếu revocation | Đóng/revalidate sessions và subscription |
| External broker logs chứa token | Logging CONNECT/STOMP frames | Redact native headers, TLS, broker ACL |
| WebFlux native không nhận CONNECT token | Không có STOMP protocol/broker | Thiết kế native first-message auth hoặc HTTP auth phù hợp |

### 19.1. Chẩn đoán theo bốn mốc

~~~mermaid
flowchart TD
    A["Realtime client thất bại"] --> B{"HTTP handshake được chấp nhận?"}
    B -- "Không" --> C["TLS/CSP/Origin/Cookie/HTTP Security"]
    B -- "Có" --> D{"STOMP CONNECTED?"}
    D -- "Không" --> E["Native Authorization, verifier, interceptor order, CSRF CONNECT"]
    D -- "Có" --> F{"SEND/SUBSCRIBE được phép?"}
    F -- "Không" --> G["Message type, destination, role, matcher order"]
    F -- "Có nhưng dữ liệu sai" --> H["Principal, object/tenant ACL, outbound routing, revocation"]
~~~

Không sửa một lỗi ở CONNECT bằng cách tắt mọi HTTP CSRF hoặc `@EnableWebSocketSecurity`. Không sửa một lỗi thiếu cookie ở handshake bằng cách mở `setAllowedOrigins("*")`.

## 20. Checklist triển khai production

- [ ] Chọn rõ mô hình: **HTTP session inheritance** hay **bearer authentication ở STOMP CONNECT**.
- [ ] Browser WebSocket không thể thêm arbitrary HTTP headers; STOMP `connectHeaders` là native protocol headers.
- [ ] Không đưa JWT/session ID dài hạn vào WebSocket URL hoặc `Sec-WebSocket-Protocol` một cách tùy tiện.
- [ ] WebSocket endpoint kiểm tra Origin chính xác, không dùng wildcard với dữ liệu riêng.
- [ ] HTTP handshake security có matcher/path/entry point đúng kiến trúc.
- [ ] Bearer CONNECT verifier từ chối missing/expired/invalid/revoked token, sai issuer/audience/token type.
- [ ] Header `Authorization` ở STOMP CONNECT có format đúng và không chấp nhận duplicates.
- [ ] JWT authorities/roles/scopes được map từ verified claims, không lấy từ `login`/payload.
- [ ] `ChannelInterceptor` chạy trước Spring Security messaging authorization và gọi `setUser` chỉ sau verification.
- [ ] `@EnableWebSocketSecurity`/`AuthorizationManager<Message<?>>` được dùng đúng Spring Servlet/STOMP stack.
- [ ] CSRF CONNECT được giải quyết rõ theo phiên bản/security config, kể cả token-only model.
- [ ] Nếu session-based, token CSRF được cấp qua HTTP endpoint có authentication, CORS và cache policy an toàn.
- [ ] SEND/SUBSCRIBE deny by default; chặn client publish trực tiếp `/topic/**`.
- [ ] Service kiểm tra object/tenant ACL theo server principal trước khi phát dữ liệu.
- [ ] Session/token expiry, logout, role revocation có chiến lược close/reconnect/revalidate.
- [ ] Client làm mới token trên reconnect và không lặp vô hạn với credential bị từ chối.
- [ ] SockJS fallback được kiểm thử CORS, HTTP CSRF, cookie và paths riêng.
- [ ] CSP `connect-src`, TLS/WSS, HSTS và HTTP firewall không bị nới rộng để che lỗi token.
- [ ] Có giới hạn connection, CONNECT rate, subscriptions, frame size, heartbeat và send buffering.
- [ ] External broker relay có TLS/credentials/ACL và logging redaction riêng.
- [ ] WebFlux native có HTTP/first-message auth và per-message authorization tương ứng, không giả định có STOMP.
- [ ] Có integration tests cả token sai/trùng/expired và dữ liệu không được phát khi bị từ chối.
- [ ] Logging không chứa raw bearer/CSRF/session tokens hoặc payload riêng tư không cần thiết.

## 21. Câu hỏi vận dụng và giải thích

**Tình huống 1 — Browser không gửi được HTTP Authorization.** SPA thử truyền object `headers` vào `new WebSocket` rồi thất bại. Sửa thế nào khi backend dùng STOMP?

**Giải thích:** WebSocket constructor của browser không nhận arbitrary HTTP headers. Dùng STOMP client `connectHeaders` để gửi bearer ở native CONNECT, và server cần interceptor verifier đúng.

**Tình huống 2 — Có native Authorization đã đủ?** Client gửi `Authorization:Bearer ...` trong CONNECT, Spring tự xác thực user không?

**Giải thích:** Không mặc định. Native header chỉ là client data; phải có verifier xác minh token và `StompHeaderAccessor#setUser(Authentication)` đúng thứ tự.

**Tình huống 3 — Auth HTTP không phù hợp.** Handshake `/ws` yêu cầu authenticated nhưng client chỉ gửi bearer ở CONNECT, dẫn tới 401. Vì sao?

**Giải thích:** HTTP request được xử lý trước CONNECT. Cần chọn kiến trúc nhất quán: HTTP session/token-auth ngay handshake, hoặc cho transport handshake hẹp và xác thực CONNECT trước mọi message.

**Tình huống 4 — JWT có thay CSRF không?** `@EnableWebSocketSecurity` bật, CONNECT có bearer đúng nhưng không có CSRF. Có chắc CONNECT được phép?

**Giải thích:** Không. CONNECT CSRF mặc định của Spring Messaging có thể vẫn yêu cầu token riêng; phải cấu hình/test phù hợp version và threat model.

**Tình huống 5 — Client gửi token ở SEND.** Một client CONNECT anonymous rồi thêm Authorization vào SEND, mong có quyền admin. Có an toàn không?

**Giải thích:** Không nếu backend không có thiết kế per-message reauthentication và gating. Thông thường xác thực CONNECT và chặn mọi SEND/SUBSCRIBE trước đó.

**Tình huống 6 — login:admin.** Một STOMP client gửi `login:admin` và `passcode:123`. Có trở thành principal ADMIN của Spring không?

**Giải thích:** Không mặc định. Các native headers đó không thay HTTP authentication hoặc token verifier application-side.

**Tình huống 7 — Thứ tự interceptor.** Token verifier chạy sau Spring Security authorization. Điều gì có thể xảy ra?

**Giải thích:** Authorization xét message khi principal chưa được gắn, dẫn tới từ chối sai hoặc trạng thái thiếu nhất quán. Authentication interceptor cần chạy trước, có integration tests xác nhận.

**Tình huống 8 — Trùng Authorization.** Frame CONNECT có hai native `Authorization` headers. Server đọc giá trị đầu và bỏ qua giá trị sau. Rủi ro gì?

**Giải thích:** Cách xử lý không thống nhất giữa tầng có thể gây mơ hồ hoặc bypass. Nên từ chối duplicate headers, giới hạn kích thước và kiểm tra format.

**Tình huống 9 — JWT sai audience.** Token chữ ký đúng và chưa hết hạn, nhưng `aud` dành cho service khác. Có được CONNECTED không?

**Giải thích:** Không nên. Token verifier phải kiểm tra audience dành cho realtime API, cùng issuer, expiry, token type và scopes.

**Tình huống 10 — Reconnect với token cũ.** Client lấy JWT một lần rồi tự reconnect sau một giờ. Tại sao CONNECT lỗi lặp?

**Giải thích:** Token có thể hết hạn/thu hồi. Làm mới token trước mỗi CONNECT; dừng reconnect vô hạn khi không thể xác thực lại.

**Tình huống 11 — SockJS dùng XHR.** Native WebSocket hoạt động nhưng SockJS `xhr_send` bị HTTP 403. Có phải bearer STOMP header bị sai?

**Giải thích:** Có thể là HTTP CSRF/CORS của fallback transport, trước khi STOMP CONNECT được xử lý. Tách kiểm tra HTTP transport với messaging layer.

**Tình huống 12 — Lộ token qua log.** Đội vận hành bật debug log toàn bộ CONNECT frames để tra cứu. Vấn đề gì?

**Giải thích:** Bearer/CSRF tokens có thể bị lộ. Redact native headers và chỉ ghi metadata/lỗi không nhạy cảm.

**Tình huống 13 — XSS trong frontend.** Server chỉ cho Origin app. Nếu frontend bị XSS thì Origin policy có chặn script lấy token gửi CONNECT không?

**Giải thích:** Không; script độc hại chạy ngay trong Origin được tin cậy. Cần chống XSS, CSP, token handling, server-side authorization và thu hồi.

**Tình huống 14 — CONNECTED nhưng lộ dữ liệu.** Alice authenticated bằng bearer đúng, sau đó đọc được order Bob. Lỗi ở đâu?

**Giải thích:** Thiếu object/tenant authorization và/hoặc subscription/outbound isolation. Token verification không cấp quyền đọc mọi object.

**Tình huống 15 — Token hết hạn trên connection cũ.** JWT hết hạn sau khi Alice CONNECTED nhưng socket vẫn nhận messages. Có mặc nhiên bị Spring đóng ngay không?

**Giải thích:** Không nên giả định. Cần close/reconnect/revalidate/revocation policy cho socket dài hạn.

**Tình huống 16 — WebFlux native.** Handler WebFlux chỉ đọc JSON frames, không dùng STOMP. Có thể copy `@EnableWebSocketSecurity` để nó đọc Authorization CONNECT không?

**Giải thích:** Không. Native WebFlux không có STOMP CONNECT mặc định. Cần HTTP auth hoặc thiết kế first-message token verification và per-message authorization riêng.

**Tình huống 17 — Client tự khai role.** CONNECT bearer Alice hợp lệ nhưng SEND body có `{"role":"ADMIN"}`. Có được tin role ADMIN đó không?

**Giải thích:** Không. Authorities phải được mapping từ token đã xác minh hoặc server-side account/ACL; payload từ client không được nâng quyền.

**Tình huống 18 — Origin giả từ non-browser.** HTTP WebSocket client gửi `Origin: https://app.example.com` rồi CONNECT bằng token sai. Có được xử lý không?

**Giải thích:** Không. Origin giúp chống trang browser không tin cậy; client ngoài browser giả được header. CONNECT authentication/ACL phải chặn độc lập.

---

**Ghi nhớ:** **STOMP native headers nằm trong STOMP `CONNECT` frame sau WebSocket handshake, không phải HTTP request headers.** Browser không thể tự thêm HTTP `Authorization` bằng `new WebSocket`, nhưng STOMP client có thể truyền `Authorization: Bearer ...` qua `connectHeaders`. Để thật sự xác thực, server phải **verify token, tạo `Authentication` và gọi `StompHeaderAccessor#setUser(...)` trước Spring Security message authorization**. CSRF token ở CONNECT là một cơ chế khác với access token, không được tự bỏ khi dùng JWT. Luôn bảo vệ Origin, HTTP transport, SEND/SUBSCRIBE, quyền object/tenant, thời hạn token, SockJS fallback, logs và lifecycle kết nối; WebFlux native cần pipeline tương đương riêng nếu không dùng STOMP.
