# Giới hạn môi trường WebSocket, proxy và chính sách Origin

Khi đưa RSocket tới trình duyệt, WebSocket thường là transport phù hợp vì JavaScript trong browser không được mở TCP socket tùy ý. Tuy nhiên, kết nối WebSocket chịu các giới hạn của Browser WebSocket API, chính sách bảo mật của trang, cookie, reverse proxy và load balancer. Một kết nối chạy tốt trên ứng dụng Java native có thể thất bại khi chạy trong browser hoặc sau khi triển khai qua ingress.

Trong module `INTEGRATION_REALTIME_RSOCKET`, RSocket vẫn giữ nguyên các interaction model Request-Response, Fire-and-Forget, Request-Stream và Request-Channel khi chạy trên WebSocket. Điều cần thiết kế riêng là handshake HTTP Upgrade, xác thực và kiểm tra `Origin`, TLS, timeout của proxy, giới hạn buffer ở browser và vòng đời kết nối dài. Bài viết này giải thích các giới hạn đó và cách kiểm thử trong môi trường thật.

## 1. Browser kết nối RSocket qua WebSocket như thế nào?

JavaScript trong trình duyệt không thể dùng API WebSocket để tạo TCP socket thô tới một host/port tùy ý. Browser cung cấp WebSocket API để mở một kết nối hai chiều qua HTTP Upgrade; sau khi handshake thành công, hai bên trao đổi WebSocket frames. RSocket JavaScript client đóng gói frame RSocket bên trong WebSocket message.

```text
Browser application
       |
       | RSocket JS client
       v
Browser WebSocket API
       |
       | HTTP/1.1 Upgrade hoặc cơ chế WebSocket được hạ tầng hỗ trợ
       v
Reverse proxy / ingress / load balancer
       |
       v
RSocket server WebSocket endpoint
       |
       v
RSocket protocol và Spring message handlers
```

Sau khi kết nối được thiết lập, route, payload, metadata, stream ID và backpressure của RSocket vẫn hoạt động theo giao thức RSocket. WebSocket chỉ là lớp vận chuyển. Ví dụ, Request-Channel vẫn có hai hướng payload; việc đổi từ TCP sang WebSocket không biến channel thành một HTTP request-response thông thường.

## 2. Giới hạn của Browser WebSocket API

Browser WebSocket API được thiết kế cho trang web, vì vậy một số khả năng mà client Java/native thường có không được phơi bày cho JavaScript:

- Không có API để tùy ý thêm HTTP handshake header như `Authorization` vào `new WebSocket(...)`.
- JavaScript không thể tự chọn hoặc điều khiển TCP socket, proxy tunnel hay TLS socket ở mức thấp.
- JavaScript không thể gửi WebSocket control frame Ping hoặc tự đọc Pong; browser quản lý các control frame này.
- API không cung cấp backpressure nhận dữ liệu theo kiểu `Subscription.request(n)`; message event có thể tiếp tục được đưa vào hàng đợi khi ứng dụng xử lý chậm.
- `WebSocket.send()` đưa dữ liệu vào hàng đợi gửi của browser; `bufferedAmount` cho biết số byte đang chờ gửi nhưng không phải xác nhận server đã nhận.
- Khi handshake thất bại, JavaScript thường chỉ nhận sự kiện lỗi/đóng ở mức khái quát, không đọc được đầy đủ HTTP status và response body như một HTTP client thông thường.

Vì vậy, không nên bê nguyên cấu hình client Java sang browser. Đặc biệt, cách gửi bearer token trong custom `Authorization` header không dùng được trực tiếp với Browser WebSocket API.

### 2.1. Theo dõi hàng đợi gửi ở browser

`bufferedAmount` giúp ứng dụng biết lượng dữ liệu đã đưa vào WebSocket nhưng chưa được browser gửi đi. Có thể đặt high-water mark và tạm dừng producer khi hàng đợi lớn:

```javascript
const socket = new WebSocket("wss://api.example.com/rsocket");
socket.binaryType = "arraybuffer";

const HIGH_WATER_BYTES = 1024 * 1024;

function canSendMore() {
  return socket.readyState === WebSocket.OPEN
    && socket.bufferedAmount < HIGH_WATER_BYTES;
}

function publishBinaryFrame(frame) {
  if (!canSendMore()) {
    return false; // producer cần chờ hoặc áp dụng chính sách giới hạn
  }

  socket.send(frame);
  return true;
}
```

Đây là ví dụ minh họa quản lý hàng đợi ở WebSocket thuần; trong ứng dụng RSocket, RSocket JS client sẽ quản lý việc encode frame và gửi dữ liệu. Không gọi `socket.send()` trực tiếp để gửi frame tùy ý vào một kết nối đang do RSocket client sở hữu. Ứng dụng nên điều tiết producer theo API của RSocket client, theo dõi buffer nếu thư viện cho phép và đặt giới hạn cho hàng đợi nghiệp vụ.

`bufferedAmount` không phải số byte đã được server nhận hoặc xử lý. Khi socket đóng, dữ liệu trong hàng đợi có thể không được gửi; vì vậy vẫn cần idempotency và cơ chế đối soát cho command quan trọng.

### 2.2. Backpressure khi nhận dữ liệu

Browser WebSocket API phát message event và không cung cấp demand nhận theo từng phần tử. RSocket có flow control ở tầng giao thức, nhưng lớp WebSocket/browser vẫn có thể tích lũy message trong hàng đợi nếu JavaScript xử lý chậm hoặc tab bị treo nền.

Với feed tốc độ cao, cần:

- Giới hạn tốc độ phát từ server và dùng `REQUEST_N` phù hợp với khả năng tiêu thụ.
- Tránh decode hoặc render toàn bộ message ngay trên main thread nếu xử lý nặng.
- Gom cập nhật UI theo frame animation hoặc batch nhỏ.
- Giới hạn buffer phía ứng dụng và quy định rõ khi đầy: bỏ trạng thái cũ, giữ latest, giảm tốc độ hoặc ngắt subscription.
- Không dùng chính sách drop cho command hoặc sự kiện cần xử lý đầy đủ.

RSocket demand giúp điều tiết số payload ở tầng protocol; nó không tự thay thế mọi giới hạn bộ nhớ của browser, JavaScript runtime hoặc thư viện WebSocket.

## 3. HTTPS page phải dùng WSS

Một trang web được tải qua HTTPS thường không được phép mở kết nối WebSocket không mã hóa `ws://` vì đây là mixed content. Khi trang chạy trên HTTPS, hãy dùng `wss://` để mã hóa WebSocket bằng TLS.

```javascript
// Trang HTTPS: dùng WSS
const endpoint = "wss://api.example.com/rsocket";

// Không dùng trong trang HTTPS production:
// const endpoint = "ws://api.example.com/rsocket";
```

Khi triển khai WSS, cần kiểm tra:

- Chứng thư TLS còn hạn, đúng hostname và có chain được browser tin cậy.
- Reverse proxy có cấu hình TLS/SNI đúng cho hostname công khai.
- Browser có thể truy cập cổng công khai, thường là `443`.
- Proxy chuyển tiếp kết nối WebSocket tới backend bằng scheme/port nội bộ phù hợp.
- Nếu TLS kết thúc tại proxy, đoạn proxy → backend cũng cần được bảo vệ theo mô hình tin cậy của hạ tầng.

Không tắt xác minh chứng thư trong production để xử lý lỗi handshake. Hãy sửa certificate, hostname, trust chain hoặc cấu hình TLS của proxy.

## 4. Chính sách Content Security Policy

Ngay cả khi endpoint WebSocket hợp lệ và TLS đúng, Content Security Policy (CSP) của trang vẫn có thể chặn kết nối. Chỉ thị `connect-src` kiểm soát các đích mà trang được phép kết nối bằng những API như `fetch`, `XMLHttpRequest`, EventSource và WebSocket.

Ví dụ CSP chỉ cho phép kết nối tới API cùng miền và endpoint realtime:

```http
Content-Security-Policy: default-src 'self'; connect-src 'self' https://api.example.com wss://api.example.com;
```

Trong cấu hình thực tế, `connect-src` cần bao gồm đúng origin WebSocket được browser sử dụng. Không mở rộng thành wildcard nếu không có yêu cầu rõ ràng. Khi CSP chặn, browser console thường hiển thị thông báo vi phạm policy; đây là lỗi phía trang, không nhất thiết là lỗi RSocket server.

Ngoài CSP, cần kiểm tra sandbox iframe, extension/privacy settings và chính sách mạng của doanh nghiệp. Những lớp này có thể hạn chế WebSocket ngay cả khi server đang hoạt động bình thường.

## 5. Origin là gì và vì sao server phải kiểm tra?

Khi browser mở WebSocket, nó gửi header `Origin` cho biết origin của trang khởi tạo kết nối, gồm scheme, host và port khi khác mặc định. Ví dụ:

```http
GET /rsocket HTTP/1.1
Host: api.example.com
Upgrade: websocket
Connection: Upgrade
Origin: https://app.example.com
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: ...
```

Origin giúp server quyết định trang nào được phép mở kết nối tới endpoint. Nếu một website độc hại khiến browser của người dùng mở WebSocket tới dịch vụ nội bộ trong khi browser tự đính kèm cookie phiên, kẻ tấn công có thể thực hiện Cross-Site WebSocket Hijacking (CSWSH) nếu server không kiểm tra Origin và xác thực phù hợp.

### 5.1. Origin không phải cơ chế xác thực

`Origin` cho biết trang nào khởi tạo kết nối; nó không chứng minh người dùng là ai. Client không phải browser có thể tự tạo hoặc giả mạo header Origin. Vì vậy:

- Dùng allowlist Origin để hạn chế website browser được phép kết nối.
- Dùng authentication để xác định principal.
- Dùng authorization để kiểm tra principal có quyền gọi route/tài nguyên hay không.
- Không xem Origin hợp lệ là bằng chứng người dùng đã đăng nhập.
- Không xem Origin bị thiếu là đáng tin cậy; định nghĩa rõ chính sách cho native client và browser client.

### 5.2. Dùng allowlist chính xác

Server nên so khớp origin theo danh sách được cấu hình, ví dụ:

```text
https://app.example.com
https://admin.example.com
https://staging.example.com
```

Khi so khớp, cần xét scheme, hostname và port. `https://app.example.com` khác `http://app.example.com`, `https://app.example.com:8443` và `https://evil-example.com`. Không dùng phép so chuỗi kiểu `endsWith("example.com")` mà không kiểm tra ranh giới hostname; cách đó có thể chấp nhận nhầm `notexample.com`.

Không phản chiếu mọi Origin nhận được thành Origin được phép. Không dùng wildcard cho endpoint xác thực bằng cookie. Với Origin `null` (có thể xuất hiện trong một số ngữ cảnh sandbox/opaque origin), mặc định nên từ chối trừ khi có trường hợp sử dụng được đánh giá và kiểm soát rõ.

### 5.3. WebSocket không dùng CORS giống fetch

WebSocket handshake không tuân theo quy trình CORS preflight giống `fetch()` hoặc XMLHttpRequest. Browser gửi `Origin`, nhưng việc server trả `Access-Control-Allow-Origin` không thay thế kiểm tra Origin ở endpoint WebSocket.

Vì vậy, chỉ cấu hình CORS cho REST API không đủ để bảo vệ WebSocket. Cần cấu hình kiểm tra Origin riêng ở WebSocket server hoặc reverse proxy trước khi chấp nhận Upgrade. Nếu dùng Spring, hãy xác minh cơ chế Origin validation của đúng WebSocket/RSocket endpoint đang chạy; không giả định CORS filter HTTP thông thường sẽ tự bảo vệ mọi đường WebSocket.

## 6. Xác thực khi browser không gửi được custom Authorization header

Browser WebSocket API không cho ứng dụng JavaScript thêm tùy ý header `Authorization` vào handshake. Có một số lựa chọn phổ biến; mỗi lựa chọn có ràng buộc riêng.

### 6.1. Cookie bảo mật

Nếu browser và endpoint có quan hệ domain/site phù hợp, cookie có thể được browser tự gửi trong WebSocket handshake theo quy tắc cookie. Cookie phiên nên có các thuộc tính phù hợp:

- `Secure` để chỉ gửi qua kết nối bảo mật.
- `HttpOnly` để JavaScript không đọc trực tiếp cookie.
- `SameSite` phù hợp với mô hình same-site/cross-site của ứng dụng.
- `Domain` và `Path` càng hẹp càng tốt.

Cookie tự động gửi làm tăng yêu cầu chống CSWSH. Server phải kiểm tra Origin, xác thực cookie và phân quyền sau khi kết nối. `SameSite` là lớp bảo vệ bổ sung; không thay thế Origin validation và các biện pháp chống CSRF phù hợp.

### 6.2. Credential trong RSocket SETUP metadata

Một lựa chọn khác là hoàn tất WebSocket handshake trước, sau đó gửi thông tin xác thực trong metadata của RSocket SETUP. RSocket server xác thực SETUP trước khi cho phép các request nghiệp vụ tiếp tục.

```text
Browser                     WebSocket endpoint             RSocket server
   |                                |                             |
   |---- HTTP Upgrade ------------>|                             |
   |<--- 101 Switching Protocols --|                             |
   |                                |                             |
   |---- RSocket SETUP + auth metadata -------------------------->|
   |<--- SETUP response / error ----------------------------------|
   |                                |                             |
   |---- request frames sau khi setup thành công ---------------->|
```

Credential trong SETUP metadata không phải HTTP handshake header. RSocket JavaScript client cần hỗ trợ encoding authentication metadata tương ứng với server. Chỉ gửi token qua WSS; server phải xác thực token và không ghi raw metadata vào log. Cần giới hạn tài nguyên và thời gian cho kết nối WebSocket chưa xác thực để tránh client mở nhiều socket rồi không gửi SETUP hợp lệ.

### 6.3. Token trong query string: tránh nếu có thể

Một số hệ thống đưa token vào URL query vì browser cho phép truyền URL khi tạo WebSocket. Cách này có nguy cơ rò rỉ qua access log của proxy, log server, APM, lịch sử URL hoặc công cụ chẩn đoán. Token trong URL cũng có thể bị sao chép vào ticket và telemetry.

Ưu tiên cookie bảo mật hoặc authentication metadata trong RSocket SETUP. Nếu kiến trúc bắt buộc dùng token query, token phải ngắn hạn, dùng một lần, giới hạn audience và quyền, không ghi query vào log, và phải có cơ chế chống replay. Không dùng access token dài hạn trong URL.

### 6.4. Sec-WebSocket-Protocol không phải nơi chứa secret

Browser cho phép chọn subprotocol trong tham số thứ hai của `new WebSocket(url, protocols)`. Subprotocol dùng để thương lượng giao thức ứng dụng, không nên dùng làm nơi truyền bearer token hoặc password. Giá trị này xuất hiện trong handshake và có thể được proxy/log thu thập.

## 7. Reverse proxy phải hỗ trợ WebSocket Upgrade

WebSocket thường bắt đầu bằng HTTP Upgrade. Reverse proxy cần chuyển tiếp đúng yêu cầu nâng cấp và giữ kết nối hai chiều sau khi server chấp nhận. Với HTTP/1.1, handshake thành công thường trả `101 Switching Protocols`.

Các yêu cầu chính:

- Hỗ trợ `Upgrade: websocket` và `Connection: Upgrade`.
- Dùng HTTP version phù hợp ở chặng proxy → backend; nhiều cấu hình phổ biến dùng HTTP/1.1.
- Chuyển tiếp đúng `Host` và `Origin` theo chính sách bảo mật.
- Giữ nguyên `Sec-WebSocket-Key`, `Sec-WebSocket-Version` và các header thương lượng cần thiết.
- Chuyển tiếp đúng path, ví dụ `/rsocket`, không rewrite thành path khác ngoài dự kiến.
- Không đóng kết nối chỉ vì HTTP request ban đầu đã trả `101`; tunnel phải tồn tại cho tới khi một phía đóng hoặc timeout có chủ đích.
- Cấu hình timeout đọc/ghi đủ dài cho kết nối realtime và có chính sách graceful drain.

### 7.1. Ví dụ cấu hình Nginx

Đoạn cấu hình minh họa cho một endpoint WebSocket:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name api.example.com;

    location /rsocket {
        proxy_pass http://rsocket_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

Đây là ví dụ nền tảng, cần điều chỉnh upstream, TLS, Origin validation, path và timeout theo môi trường. `proxy_read_timeout`/`proxy_send_timeout` là giới hạn ở proxy; giá trị dài không thay thế heartbeat và quản lý kết nối nhàn rỗi. Không dùng cấu hình trên như một policy bảo mật hoàn chỉnh nếu chưa thêm kiểm tra Origin và authentication.

### 7.2. Proxy và load balancer có thể đóng socket nhàn rỗi

WebSocket là kết nối dài. Proxy, NAT hoặc load balancer có thể đóng kết nối nếu không thấy dữ liệu trong một khoảng thời gian. Khi đó, client có thể nhận close/error dù RSocket server vẫn hoạt động.

Hãy phối hợp:

- RSocket KEEPALIVE interval/Max Lifetime.
- Heartbeat ở tầng ứng dụng nếu browser client cần tín hiệu riêng.
- Idle timeout của reverse proxy, ingress, load balancer và NAT.
- Timeout và chính sách reconnect của client.

RSocket KEEPALIVE là frame của giao thức RSocket được truyền bên trong WebSocket message. Nó khác WebSocket control Ping/Pong. JavaScript browser không tự phát control Ping, nhưng browser quản lý phản hồi control frame theo triển khai WebSocket. Hãy xác minh RSocket JS client gửi KEEPALIVE đều đặn và proxy coi lưu lượng đó là activity. Chọn khoảng KEEPALIVE ngắn hơn idle timeout hạ tầng với khoảng dự phòng hợp lý.

## 8. Path, Origin và route là ba khái niệm khác nhau

Khi triển khai qua proxy, cần phân biệt ba lớp địa chỉ:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| WebSocket URL/path | `wss://api.example.com/rsocket` | Chọn endpoint WebSocket qua HTTP Upgrade. |
| Origin | `https://app.example.com` | Cho biết trang browser khởi tạo kết nối để server áp dụng allowlist. |
| RSocket route | `devices.status.get` | Chọn message handler cho từng tương tác sau SETUP. |

Proxy rewrite path không nên vô tình thay đổi route metadata. Route nằm trong frame RSocket bên trong WebSocket; nó không phải URL path. Origin cũng không phải địa chỉ server mà client kết nối tới.

## 9. Load balancing và session affinity

Một WebSocket connection thường được giữ trên một backend trong suốt vòng đời socket. Khi kết nối mới được mở, load balancer có thể chọn backend khác. Nếu server lưu state RSocket session hoặc Resume buffer trong memory cục bộ, việc reconnect tới node khác có thể khiến Resume thất bại.

Các lựa chọn kiến trúc:

- Dùng session affinity/sticky routing để reconnect tới node giữ session state, nếu hạ tầng và cơ chế định tuyến hỗ trợ.
- Dùng resume store hoặc session state chia sẻ nếu implementation hỗ trợ và đã kiểm chứng tính nhất quán.
- Chấp nhận tạo session mới sau disconnect và khôi phục nghiệp vụ bằng snapshot, sequence/cursor và idempotency.
- Khi deploy phiên bản mới, drain kết nối WebSocket có thời gian; không xóa backend đang giữ session trước khi client có cơ hội reconnect hoặc được thông báo.

Sticky session không tự bảo đảm Resume hoạt động nếu process đã restart hoặc buffer đã hết hạn. Ngược lại, nếu ứng dụng không bật Resume và có thể tạo session mới an toàn, affinity có thể không cần thiết. Hãy chọn theo mô hình lưu state thực tế.

## 10. Giới hạn message, fragmentation và dữ liệu lớn

WebSocket message có thể bị giới hạn kích thước bởi browser, proxy, gateway hoặc server. RSocket có thể phân mảnh payload theo cấu hình giao thức, nhưng tất cả tầng trên đường truyền vẫn phải cho phép kích thước tương ứng.

Các nguyên tắc:

- Đặt giới hạn payload ở server và gateway; không cho phép message vô hạn.
- Kiểm thử payload lớn qua đúng proxy và TLS termination đang dùng.
- Dùng streaming thay vì gửi một message khổng lồ nếu dữ liệu có thể truyền thành nhiều phần.
- Không giả định browser sẽ có đủ memory để decode hoặc giữ nhiều binary message lớn cùng lúc.
- Với dữ liệu nhị phân, cấu hình `binaryType` phù hợp với client library; không chuyển dữ liệu lớn thành Base64 nếu không cần.
- Khi nhận dữ liệu nhanh, giới hạn số phần tử đang chờ xử lý và giải phóng buffer theo ownership contract của thư viện.

## 11. Kiểm thử Origin, proxy và browser thực tế

Kiểm thử trên localhost không đủ để chứng minh kết nối sẽ hoạt động sau khi deploy. Nên có ma trận kiểm thử:

1. Trang HTTPS kết nối tới WSS với certificate hợp lệ.
2. Trang HTTPS cố kết nối tới `ws://`; xác nhận browser chặn mixed content.
3. Origin nằm trong allowlist; handshake được chấp nhận.
4. Origin ngoài allowlist hoặc `Origin: null`; handshake bị từ chối theo policy.
5. Hai website khác nhau cùng gửi cookie; xác nhận cookie policy và Origin validation ngăn CSWSH.
6. Cookie hết hạn hoặc SETUP token không hợp lệ; xác nhận server từ chối trước khi cho phép route nghiệp vụ.
7. CSP `connect-src` thiếu endpoint; xác nhận browser console báo vi phạm policy.
8. Proxy không chuyển tiếp Upgrade hoặc sai path; xác nhận lỗi handshake được nhận diện.
9. Kết nối nhàn rỗi lâu hơn idle timeout; xác nhận KEEPALIVE/heartbeat giữ kết nối hoặc client reconnect theo policy.
10. Backend restart hoặc load balancer chọn node khác; xác nhận Resume hoặc khôi phục session mới theo thiết kế.
11. Subscriber xử lý chậm và server phát tốc độ cao; xác nhận queue/buffer có giới hạn.
12. Kiểm tra trên các browser mục tiêu (Chrome, Firefox, Safari và browser di động) cùng mạng doanh nghiệp/VPN nếu sản phẩm hỗ trợ.

Khi điều tra lỗi, thu thập thời điểm handshake, URL path đã loại query nhạy cảm, Origin đã chuẩn hóa, HTTP status/close code nếu hạ tầng cung cấp, backend node, trace ID và thời điểm disconnect. Không ghi cookie, token, raw authentication metadata hoặc toàn bộ query string vào log.

## 12. Các lỗi thường gặp

- **Cố đặt Authorization header trong browser WebSocket:** Browser API không hỗ trợ custom handshake headers; dùng cookie bảo mật hoặc auth metadata trong RSocket SETUP.
- **Chỉ cấu hình CORS:** WebSocket cần kiểm tra Origin riêng; CORS response header không thay thế allowlist.
- **Tin Origin là danh tính:** Origin không phải authentication và có thể bị client native giả mạo.
- **Cho phép mọi Origin:** Có thể tạo điều kiện cho CSWSH khi cookie được gửi tự động.
- **Dùng token dài hạn trong query:** Token có thể xuất hiện trong proxy/access log và công cụ giám sát.
- **Trang HTTPS kết nối `ws://`:** Browser chặn mixed content; dùng `wss://`.
- **Proxy thiếu Upgrade/Connection:** Handshake không chuyển thành WebSocket tunnel.
- **Idle timeout proxy quá ngắn:** Kết nối bị đóng dù server vẫn khỏe; phối hợp KEEPALIVE/heartbeat.
- **Không giới hạn buffer browser:** Tab xử lý chậm có thể tích lũy message và tăng memory.
- **Giả định reconnect tới node nào cũng Resume được:** Session state có thể chỉ nằm trên node cũ.

## 13. Checklist triển khai

- Dùng `wss://` cho trang HTTPS và xác minh TLS certificate/hostname.
- CSP `connect-src` cho phép đúng WebSocket endpoint.
- Server kiểm tra Origin bằng allowlist chính xác; không phản chiếu Origin tùy ý.
- Origin validation, authentication và authorization là các bước riêng.
- Chọn cookie bảo mật hoặc authentication metadata trong SETUP; tránh token query dài hạn.
- Reverse proxy chuyển tiếp WebSocket Upgrade, path và timeout đúng.
- KEEPALIVE/heartbeat phù hợp với idle timeout của proxy/NAT/load balancer.
- Giới hạn payload, buffer gửi/nhận và tốc độ producer.
- Có chính sách reconnect/Resume và session affinity phù hợp với nơi lưu session state.
- Kiểm thử trên browser thật, qua ingress thật và với Origin hợp lệ/không hợp lệ.
- Log/trace không chứa cookie, token, raw metadata hoặc query nhạy cảm.

## 14. Kết luận

Browser truy cập RSocket qua WebSocket vì JavaScript không mở TCP socket tùy ý và Browser WebSocket API không cho thêm custom handshake header. Với trang HTTPS, dùng WSS; cấu hình CSP `connect-src`; xác thực bằng cookie bảo mật hoặc metadata trong RSocket SETUP. Server phải kiểm tra Origin bằng allowlist để giảm nguy cơ CSWSH, đồng thời thực hiện authentication và authorization độc lập. Reverse proxy cần hỗ trợ Upgrade, giữ kết nối dài và có timeout phù hợp với KEEPALIVE/heartbeat. Cuối cùng, giới hạn buffer/payload, tính tới load balancing và kiểm thử trên browser cùng hạ tầng thực tế trước khi triển khai.
