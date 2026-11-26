# SockJS fallback và nhu cầu iframe cùng origin

## 1. Tình huống mở đầu: WebSocket chạy, fallback lại bị chặn bởi iframe

Một ứng dụng quản lý đơn hàng cho phép nhân viên nhận trạng thái giao dịch theo thời gian thực. Frontend chạy trên `https://app.example.com` và backend Spring chạy sau một reverse proxy. Ở những trình duyệt hiện đại, ứng dụng mở native WebSocket và STOMP `CONNECT` bình thường. Nhưng trong một trình duyệt cũ hoặc môi trường mạng buộc SockJS chọn transport dự phòng, console xuất hiện:

~~~text
Refused to display 'https://api.example.com/ws/iframe.html'
in a frame because it set 'X-Frame-Options' to 'deny'.
~~~

Một môi trường khác đã đổi sang `X-Frame-Options: SAMEORIGIN` nhưng vẫn bị từ chối: trang cha ở `https://app.example.com`, còn tài liệu iframe ở `https://api.example.com`. Hai URL đó **khác origin** dù đều nằm dưới `example.com`.

Có ba kết luận quan trọng:

1. SockJS là cơ chế cung cấp **transport dự phòng**, không phải hệ thống authentication hay authorization.
2. Một số **legacy iframe-based transports** cần trình duyệt tải tài liệu iframe do SockJS server phục vụ; chính sách chống clickjacking `X-Frame-Options` và CSP có thể chặn tài liệu đó.
3. Đổi header toàn ứng dụng thành cho phép mọi iframe, tắt CSRF hoặc mở wildcard Origin không phải cách sửa an toàn. Phải chọn **transport thực sự cần hỗ trợ**, xác định origin của trang cha và tài liệu iframe, sau đó chỉ nới chính sách tại đúng ranh giới.

Bài học thuộc chương **WebSocket và STOMP** của dịch vụ học tập **SPRING_SECURITY_HTTP_PROTECTION**. Dịch vụ hướng đến thực hành các lớp phòng vệ HTTP và trình duyệt với Spring Security: CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session cho cả Servlet lẫn Reactive. Trọng tâm bài này là **SockJS fallback và nhu cầu iframe cùng origin**; các phần STOMP `CONNECT`, CSRF và phân quyền SEND/SUBSCRIBE được dùng để đặt iframe transport đúng trong kiến trúc bảo mật tổng thể.

### Kết quả học tập

Sau bài, người học có thể:

1. Giải thích tại sao SockJS có nhiều transport và trường hợp nào dùng iframe.
2. Phân biệt origin của trang cha, iframe HTML, URL SockJS, script bên trong iframe và backend nội bộ.
3. Giải thích `X-Frame-Options: DENY`, `SAMEORIGIN`, CSP `frame-ancestors`, `frame-src`, `script-src` và `connect-src`.
4. Hiểu vì sao `SAMEORIGIN` không cho trang `app.example.com` nhúng iframe từ `api.example.com`.
5. Thiết kế cùng-origin qua reverse proxy hoặc loại bỏ nhu cầu iframe fallback cho những browser không cần legacy transport.
6. Cấu hình Spring WebSocket/STOMP SockJS, `setClientLibraryUrl` và security headers đúng phạm vi.
7. Nhận diện tình huống cấu hình `allowedOrigins` cụ thể ảnh hưởng việc dùng iframe transports.
8. Không đánh đồng iframe transport với HTTP CORS/XHR, HTTP CSRF hay STOMP CONNECT CSRF.
9. Kiểm thử đường đi fallback, session cookie, CSP, Origin và message authorization theo từng lớp.
10. Chẩn đoán sự cố trong DevTools và triển khai hardening mà không làm yếu bảo vệ clickjacking cho phần còn lại của ứng dụng.

Tên miền, endpoint và đường dẫn tài nguyên trong bài là ví dụ. SockJS chọn transport và tạo URL phụ thuộc phiên bản, browser và cấu hình; đừng coi một URL minh họa là hợp đồng vĩnh viễn của mọi phiên bản.

## 2. SockJS giải quyết vấn đề gì?

### 2.1. Native WebSocket và kịch bản cần fallback

Native WebSocket tạo kết nối hai chiều trên transport đã nâng cấp từ HTTP. Khi hoạt động bình thường:

~~~text
Browser
  -> GET /ws (WebSocket handshake)
  <- 101 Switching Protocols
  -> STOMP CONNECT
  <- STOMP CONNECTED
  -> STOMP SEND hoặc SUBSCRIBE
  <- STOMP MESSAGE
~~~

Nhưng một số trình duyệt cũ, proxy hoặc mạng doanh nghiệp không hỗ trợ WebSocket đầy đủ, hoặc môi trường áp đặt hạn chế kết nối. SockJS cố cung cấp API gần tương đương WebSocket bằng cách chọn transport phù hợp.

Các họ transport thường được nhắc đến:

| Họ transport | Ý tưởng | Có nhất thiết cần iframe? |
| --- | --- | --- |
| Native WebSocket | Kết nối WebSocket thật | Không |
| XHR streaming | Server gửi dữ liệu qua HTTP response dài hạn | Thông thường không phải iframe transport |
| XHR polling | Client lặp HTTP requests để nhận dữ liệu | Thông thường không phải iframe transport |
| EventSource hoặc biến thể HTTP | Nhận dữ liệu qua một cơ chế streaming khác khi được hỗ trợ | Phụ thuộc browser/biến thể |
| Legacy iframe-based transport | Dùng một iframe hỗ trợ kênh giao tiếp dự phòng trong browser cũ | **Có** |
| JSONP và những legacy transports khác | Workaround tương thích browser lịch sử | Phụ thuộc khả năng, thường không nên ưu tiên |

Không phải bản SockJS, browser hay ứng dụng nào cũng bật toàn bộ transports. Trong thực tế hiện đại, đa số trình duyệt có native WebSocket; hãy kiểm tra **transport đang được chọn**, thay vì mặc định mọi lỗi SockJS đều liên quan iframe.

### 2.2. SockJS và STOMP có trách nhiệm khác nhau

**SockJS** cung cấp phương tiện chuyên chở dữ liệu khi WebSocket không dùng được. **STOMP** định nghĩa frames như `CONNECT`, `SEND`, `SUBSCRIBE` chạy trên phương tiện đó.

Ví dụ:

~~~text
                         +-- WebSocket transport ------+
                         |                             |
STOMP frames -------------+-- XHR streaming/polling ----+--> Spring STOMP broker
                         |                             |
                         +-- iframe-based fallback ----+
~~~

Thay transport không đồng nghĩa thay quyền. Dù dùng native WebSocket hay HTTP/iframe fallback, backend vẫn cần bảo vệ:

- HTTP requests và cookies phù hợp transport.
- Origin và CORS ở nơi framework áp dụng.
- STOMP CONNECT authentication/CSRF theo security policy.
- SEND/SUBSCRIBE authorization và business object/tenant ACL.

### 2.3. Một SockJS endpoint có nhiều HTTP paths

Với base endpoint `/ws`, có thể quan sát các request dạng:

~~~text
GET  /ws/info
GET  /ws/<server-id>/<session-id>/websocket
GET  /ws/<server-id>/<session-id>/xhr_streaming
POST /ws/<server-id>/<session-id>/xhr_send
GET  /ws/iframe.html
...
~~~

Các đường dẫn trên mang tính **minh họa**; tên file iframe hoặc HTTP method của mỗi transport có thể khác giữa các phiên bản. Khi debug, hãy lấy URL và HTTP method **thực tế trong DevTools**. Không viết một rule bảo mật chỉ dựa vào tên URL mà không xác minh route của framework đang sử dụng.

## 3. Iframe fallback hoạt động thế nào?

### 3.1. Vì sao một transport cần iframe?

Một số browser cũ không hỗ trợ các API cross-origin/streaming hiện đại theo cách SockJS cần. SockJS dùng một tài liệu iframe làm môi trường trung gian để chạy đoạn mã hỗ trợ transport, sau đó phối hợp truyền nhận với trang cha theo cơ chế của thư viện.

Ví dụ logic:

~~~mermaid
flowchart TD
    A["Frontend app.example.com"] --> B["SockJS lựa chọn transport"]
    B --> C{"Native WebSocket sử dụng được?"}
    C -- "Có" --> D["WebSocket trực tiếp"]
    C -- "Không" --> E{"XHR / transport thông thường phù hợp?"}
    E -- "Có" --> F["HTTP streaming/polling"]
    E -- "Không; legacy iframe có hỗ trợ" --> G["Tải SockJS iframe document"]
    G --> H["Browser kiểm tra X-Frame-Options / CSP"]
    H --> I{"Frame được phép?"}
    I -- "Không" --> J["Transport thất bại trước STOMP"]
    I -- "Có" --> K["Tải script trong iframe, khởi tạo fallback"]
    K --> L["STOMP frames đi qua transport"]
~~~

Sơ đồ mô tả điểm kiểm soát quan trọng; việc SockJS chọn transport có thể diễn ra với nhiều fallback attempts và không đảm bảo đi đúng một nhánh trong mọi bản thư viện.

### 3.2. Có ít nhất bốn origin cần kiểm tra

| Đối tượng | Ví dụ | Tại sao quan trọng? |
| --- | --- | --- |
| **Trang cha** | `https://app.example.com/dashboard` | Trang đang nhúng iframe |
| **Tài liệu iframe** | `https://api.example.com/ws/iframe.html` | Response chịu `X-Frame-Options` và CSP `frame-ancestors` |
| **SockJS client script trong iframe** | `https://api.example.com/assets/sockjs.min.js` | Phải tải được, phù hợp `script-src`/resource integrity policy |
| **HTTP/WebSocket transport endpoint** | `https://api.example.com/ws` hoặc `wss://api.example.com/ws` | Chịu authentication, Origin policy, CORS với XHR, cookies và proxy |

Với `X-Frame-Options: SAMEORIGIN`, hai origin đầu tiên cần thỏa chính sách same-origin của trình duyệt. Cùng site hoặc cùng registrable domain **không đủ**.

### 3.3. Không phải cứ SockJS là có iframe

Nếu DevTools chỉ thấy `GET /ws/info`, `websocket` hoặc `xhr_streaming` mà **không** có tài liệu iframe nào được tải, điều chỉnh `X-Frame-Options` thường không sửa lỗi transport đó.

Ví dụ HTTP 403 tại `POST /ws/.../xhr_send` có thể là HTTP CSRF hoặc CORS. Ví dụ STOMP `ERROR` sau khi transport mở lại có thể là CSRF CONNECT hoặc message authorization. Đừng làm yếu chính sách framing khi iframe không hề được dùng.

## 4. “Cùng origin” nghĩa chính xác là gì?

Một origin web về cơ bản gồm **scheme + host + port**. Đường dẫn URL không phải thành phần định danh origin.

| Trang cha | Iframe URL | So sánh | Kết quả `SAMEORIGIN` |
| --- | --- | --- | --- |
| `https://app.example.com/home` | `https://app.example.com/ws/iframe.html` | Cùng scheme, host, port mặc định | Cho phép theo điều kiện XFO |
| `https://app.example.com/home` | `https://api.example.com/ws/iframe.html` | Khác host | **Chặn** |
| `https://app.example.com/home` | `http://app.example.com/ws/iframe.html` | Khác scheme | **Chặn** |
| `https://app.example.com/home` | `https://app.example.com:8443/ws/iframe.html` | Khác port | **Chặn** |
| `http://localhost:3000` | `http://localhost:8080/ws/iframe.html` | Khác port | **Chặn** |
| `https://app.example.com:443` | `https://app.example.com/ws/iframe.html` | Port mặc định tương đương | Cùng origin |
| `https://app.example.com/home` | `https://app.example.com/other/iframe.html` | Chỉ khác path | Cùng origin |

**Same-site ≠ same-origin.** Một cookie `SameSite=Lax` có thể hoạt động giữa các subdomain cùng site tùy ngữ cảnh, nhưng `X-Frame-Options: SAMEORIGIN` không dựa vào tiêu chí same-site.

Một reverse proxy có thể giúp trình duyệt thấy cả frontend và SockJS iframe dưới **cùng public origin**, dù ứng dụng backend chạy trên host/port nội bộ khác nhau. Đây là mô hình nên ưu tiên khi thật sự phải dùng iframe fallback.

## 5. X-Frame-Options: DENY và SAMEORIGIN

### 5.1. Spring Security mặc định chống clickjacking

Spring Security Servlet thường thêm response header:

~~~http
X-Frame-Options: DENY
~~~

`DENY` yêu cầu trình duyệt không hiển thị response trong frame/iframe. Đây là một biện pháp chống **clickjacking** có lợi cho phần lớn HTML pages, đặc biệt trang quản trị và form có thao tác quan trọng.

Nhưng nếu một SockJS legacy transport yêu cầu browser render tài liệu iframe do server tạo, `DENY` sẽ chặn transport **trước khi** STOMP CONNECT.

### 5.2. SAMEORIGIN là nới lỏng có giới hạn

~~~http
X-Frame-Options: SAMEORIGIN
~~~

`SAMEORIGIN` cho phép framing khi đáp ứng quan hệ same-origin theo trình duyệt; nó **không** có nghĩa “cho các subdomain thuộc example.com”, “cho những origin có CORS” hoặc “cho mọi iframe từ các trang đã login”.

Thay `DENY` bằng `SAMEORIGIN` cũng là thay đổi policy clickjacking. Vì vậy chỉ áp dụng cho vùng tài nguyên thật sự cần được frame, hoặc cho một security chain **đã giới hạn phạm vi**, thay vì mặc định mở mọi trang admin.

### 5.3. Khi app và API khác origin, SAMEORIGIN không giúp được

Giả sử frontend ở `https://app.example.com` và iframe được tải từ `https://api.example.com`. Response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html
X-Frame-Options: SAMEORIGIN
~~~

vẫn **không** cho phép trang cha nhúng iframe vì hai host khác nhau. Thêm:

~~~http
Access-Control-Allow-Origin: https://app.example.com
~~~

cũng **không** làm hai origin trở nên giống nhau và không vượt XFO. CORS kiểm soát truy cập HTTP response theo cơ chế khác, không phải giấy phép render iframe.

### 5.4. Không dùng ALLOW-FROM làm lời giải hiện đại

Cú pháp `X-Frame-Options: ALLOW-FROM <origin>` có lịch sử hỗ trợ không nhất quán/đã lỗi thời ở các trình duyệt hiện đại. Không nên dựa vào nó để vừa có clickjacking protection vừa hỗ trợ cross-origin SockJS iframe.

Nếu bắt buộc cho một origin khác nhúng frame trong browser hiện đại, cân nhắc **CSP `frame-ancestors`** với allowlist rất hẹp và loại bỏ XFO xung đột trên **đúng tài liệu frame**, nhưng cần nghiên cứu kỹ tương thích của các browser/legacy iframe transports. Với browser cũ vốn cần iframe fallback, giải pháp này có thể không khả thi; cùng-origin proxy hoặc bỏ iframe là lựa chọn an toàn hơn.

## 6. CSP: frame-ancestors khác frame-src và connect-src

Chỉ kiểm tra `X-Frame-Options` là chưa đủ khi ứng dụng có Content Security Policy (CSP).

### 6.1. Chính sách của tài liệu iframe: frame-ancestors

Response của tài liệu iframe có thể mang:

~~~http
Content-Security-Policy: frame-ancestors 'self'
~~~

Nó nói **những trang cha/origin tổ tiên nào** được phép nhúng tài liệu. Nếu có:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

thì tài liệu iframe sẽ không thể được frame, kể cả khi `X-Frame-Options: SAMEORIGIN`. Trình duyệt có thể áp dụng tương tác CSP/XFO khác nhau theo mức hỗ trợ, nhưng không nên dựa vào một header để vô hiệu header bảo vệ kia.

Với mô hình same-origin, tài liệu iframe có thể dùng `frame-ancestors 'self'`; những trang nghiệp vụ nhạy cảm khác nên tiếp tục có `frame-ancestors 'none'` nếu không cần embedding.

### 6.2. Chính sách của trang cha: frame-src

CSP trên frontend điều khiển những iframe mà trang **được phép tải**:

~~~http
Content-Security-Policy: frame-src 'self'
~~~

Nếu iframe SockJS ở cùng `https://app.example.com`, điều kiện này phù hợp. Nếu iframe ở `https://api.example.com`, frontend phải cho phép frame-src tới host đó **và** iframe response phải cho phép bị frame. Chỉ sửa `frame-src` trên frontend **không vượt** XFO/CSP `frame-ancestors` của backend.

### 6.3. Chính sách network: connect-src

CSP trên frontend còn có thể hạn chế kết nối WebSocket và Fetch:

~~~http
Content-Security-Policy: connect-src 'self' wss://api.example.com
~~~

`connect-src` liên quan đến WebSocket/Fetch và nhiều kết nối script tạo. Nó không cấp phép nhúng iframe; `frame-src`/`frame-ancestors` giải quyết chuyện đó.

Nếu frontend và SockJS đều được reverse proxy dưới origin `https://app.example.com`, `connect-src 'self'` có thể đủ cho các kết nối same-origin trong môi trường trình duyệt tương thích, nhưng phải **kiểm thử thực tế cách browser áp dụng `'self'` với WebSocket ws/wss**; khi cần, liệt kê rõ endpoint `wss://app.example.com`. Không mở `connect-src *` chỉ vì một lỗi CSP.

### 6.4. Script trong iframe: script-src và client library URL

SockJS iframe có thể tải một bản SockJS client library để triển khai fallback. Nếu iframe page có CSP:

~~~http
Content-Security-Policy: script-src 'self'
~~~

mà library được tải từ CDN bên ngoài, browser có thể chặn script. Đây là lỗi khác với `X-Frame-Options`: **iframe có thể được nhúng nhưng script bên trong không chạy**.

Cấu hình `setClientLibraryUrl` cho SockJS server để dùng một bản thư viện được host ở public origin phù hợp, đồng thời đảm bảo frontend, iframe và CSP tin cậy đúng tài nguyên.

### 6.5. Bảng xác định header nào cần sửa

| Lỗi quan sát | Header/policy liên quan | Response cần xem |
| --- | --- | --- |
| “X-Frame-Options DENY” | `X-Frame-Options` | **Tài liệu iframe** |
| “X-Frame-Options SAMEORIGIN” nhưng khác host | `X-Frame-Options` và origin cha/iframe | **Tài liệu iframe** và URL trang cha |
| “frame-ancestors 'none'” | CSP `frame-ancestors` | **Tài liệu iframe** |
| “frame-src blocks ...” | CSP `frame-src` | **Trang cha** |
| “script-src blocks SockJS library” | CSP `script-src` | **Tài liệu iframe** |
| “connect-src blocks websocket/fetch” | CSP `connect-src` | Trang tạo kết nối |
| XHR fallback báo CORS | ACAO/ACAC/allowed methods/headers | **HTTP transport requests** |
| SockJS transport POST bị 403 | HTTP CSRF/auth/gateway | **POST của transport** |
| STOMP CONNECT bị ERROR | Messaging CSRF/auth | **STOMP frame/server logs** |

## 7. Khi nào nên thực sự hỗ trợ iframe fallback?

Iframe SockJS transport chủ yếu phục vụ những browser/khả năng tương thích lịch sử. Trước khi nới framing policy, hãy đặt các câu hỏi:

1. Có bao nhiêu người dùng đang dùng browser không hỗ trợ native WebSocket/XHR fallback hiện đại?
2. Sản phẩm có hợp đồng tương thích trình duyệt rất cũ hay không?
3. Hạ tầng proxy có đang chặn Upgrade, và có thể sửa proxy thay vì dùng iframe không?
4. SockJS đang thực sự chọn transport `iframe-*` hay vẫn dùng `websocket`/`xhr-*`?
5. Có chính sách CSP, clickjacking và cookie nào bắt buộc không thể nới?
6. Có thể phục vụ tất cả SockJS endpoints qua public same-origin reverse proxy không?
7. Việc duy trì legacy transport có mở thêm rủi ro bảo mật/chi phí vận hành lớn hơn giá trị tương thích không?

**Quyết định theo bằng chứng:** nếu chỉ phục vụ browser hiện đại, ưu tiên native WebSocket và XHR fallback khi thực sự cần, giữ `X-Frame-Options: DENY` cho các HTML pages không cần iframe. Đừng mở toàn hệ thống chỉ để khắc phục một giả định không có test.

### 7.1. Ba chiến lược kiến trúc

| Phương án | Phù hợp khi | Bảo mật và chi phí |
| --- | --- | --- |
| **A. Không cần iframe** | Browser hiện đại, native WebSocket/XHR đủ | Giữ DENY; ít rủi ro hơn |
| **B. Same-origin reverse proxy** | Thực sự cần iframe fallback và có thể kiểm soát public routing | Cho frame hẹp với SAMEORIGIN; cần proxy/session/CSP chính xác |
| **C. Cross-origin iframe có kiểm soát** | Môi trường hiện đại được kiểm thử đầy đủ, có yêu cầu embedding chính đáng | CSP `frame-ancestors` allowlist hẹp; khả năng tương thích legacy và Spring SockJS restrictions có thể khiến giải pháp không dùng được |

Với mục tiêu **hỗ trợ legacy iframe**, phương án B thường dễ lập luận bảo mật hơn C.

## 8. Mô hình same-origin reverse proxy khuyến nghị

### 8.1. Frontend và SockJS dưới cùng public origin

Thay vì:

~~~text
Trang:   https://app.example.com/dashboard
SockJS:  https://api.example.com/ws
Iframe:  https://api.example.com/ws/iframe.html  (khác origin)
~~~

đặt reverse proxy cùng origin:

~~~text
Trang:   https://app.example.com/dashboard
SockJS:  https://app.example.com/ws
Iframe:  https://app.example.com/ws/iframe.html  (cùng origin)
Backend: http://internal-spring:8080/ws        (không lộ cho browser)
~~~

Browser so sánh **public URL**, không so sánh host nội bộ của Spring server. Proxy định tuyến `/ws/**` về SockJS endpoint và vẫn bảo toàn các HTTP/WebSocket semantics cần thiết.

### 8.2. Sơ đồ deployment

~~~mermaid
flowchart LR
    B["Browser<br/>https://app.example.com"] --> P["Reverse proxy HTTPS<br/>app.example.com"]
    P --> UI["Frontend HTML/JS<br/>/"]
    P --> JS["SockJS client library<br/>/assets/sockjs.min.js"]
    P --> WS["Spring Servlet<br/>/ws và /ws/**"]
    WS --> ST["Spring Security HTTP + STOMP"]
    ST --> SVC["Business service / broker"]
~~~

Mô hình này tạo sự thống nhất cho cookie scope, iframe origin và frontend CSP, nhưng **không tự tạo authentication**, CSRF hoặc message authorization. Các lớp đó vẫn cần cấu hình.

### 8.3. Những điều proxy cần giữ đúng

- Hỗ trợ HTTP/1.1 WebSocket Upgrade hoặc cơ chế WebSocket được hỗ trợ trên đường truyền.
- Forward HTTP methods, URLs, paths và cookies của SockJS transports chính xác.
- Không biến `/ws/iframe.html` thành trang lỗi HTML mang XFO/CSP khác dự kiến.
- Không cache token/session-specific responses hoặc STOMP messages.
- Không ghi session IDs, bearer/CSRF tokens trong logs.
- Nếu cần forwarded headers, chỉ tin proxy đáng tin cậy và cấu hình Spring phù hợp; đừng tin `X-Forwarded-Host` do client tự khai.
- Bảo đảm WebSocket base URL và generated SockJS URLs dùng public scheme/host/path chính xác.
- Chia sẻ session store hoặc cấu hình sticky routing nếu nhiều backend nodes và transport cần duy trì state.
- Duy trì HTTPS/WSS trên public path, HSTS khi hợp lý; không để mixed-content iframe/HTTP fallback.

**CORS không phải giải pháp cho việc browser nhìn thấy hai host khác origin.** Reverse proxy cung cấp một public origin thống nhất, thay vì cố dùng ACAO để vượt XFO.

## 9. Spring WebSocket: đăng ký endpoint và SockJS library cùng origin

### 9.1. Mẫu cấu hình endpoint Servlet/STOMP

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class RealtimeSockJsConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        // Browser truy cập /ws dưới cùng public origin với frontend.
        registry.addEndpoint("/ws")
            // Không mở wildcard origins để "sửa" iframe.
            // Mặc định Spring SockJS chỉ cho same-origin theo policy.
            .withSockJS()
            // Library phục vụ trên public origin của SockJS iframe.
            .setClientLibraryUrl("/assets/sockjs.min.js");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Mã trên mô tả mục đích: browser và iframe nhìn thấy cùng public origin, SockJS client library URL trỏ đến file **được phục vụ thật**. File `/assets/sockjs.min.js` không tự tồn tại chỉ vì gọi `setClientLibraryUrl`; ứng dụng hoặc reverse proxy phải phục vụ phiên bản thư viện đã kiểm soát tại đường dẫn đó.

### 9.2. setClientLibraryUrl làm gì, không làm gì?

Trong cấu hình SockJS Servlet, `setClientLibraryUrl` chỉ định URL SockJS client library dùng bên trong một số iframe-based transports. Điều này khác với việc frontend import thư viện `sockjs-client` trong bundle ứng dụng.

Cần kiểm tra:

- URL tải được từ **ngữ cảnh tài liệu iframe** (relative URL được resolve theo iframe URL/origin).
- Library version tương thích Spring/SockJS client đang dùng; tài nguyên có kiểm soát, không tùy tiện sử dụng phiên bản CDN cũ.
- CSP `script-src` của iframe cho phép URL đó.
- Không bị auth redirect tới login HTML thay vì JavaScript.
- Content type phù hợp và không bị proxy rewrite/cache sai.
- Không gây xung đột XFO/CSP framing trên tài liệu iframe.

Nếu không cần iframe fallback, không nhất thiết phải tùy chỉnh URL chỉ vì đang sử dụng SockJS.

### 9.3. Tại sao tài liệu nói library cần cùng origin?

Trong mô hình `SAMEORIGIN`, iframe document được phép nằm trong frame chỉ khi origin phù hợp trang cha. Với các fallback dựa vào iframe, library/iframe phải được bố trí để framework hoạt động theo same-origin assumptions và CSP của site.

Dùng một library từ CDN bên ngoài có thể gặp CSP/script restrictions hoặc security policy khác. Host bản thư viện đã được kiểm soát dưới public origin nhất quán giúp giảm phụ thuộc bên ngoài, dễ hardening và quan sát.

**Không đánh đồng:** đặt `clientLibraryUrl` same-origin **không thể tự biến** một iframe HTML đang đến từ `api.example.com` thành cùng origin với trang `app.example.com`. Origin của iframe document vẫn do **URL tài liệu iframe** quyết định.

### 9.4. Không đặt allowedOrigins = "*" để cố giữ iframe

Ví dụ rủi ro:

~~~java
// Không khuyến nghị trong ứng dụng xử lý session/user data riêng:
registry.addEndpoint("/ws")
    .setAllowedOrigins("*")
    .withSockJS();
~~~

Wildcard làm rộng những website browser có thể thử kết nối, tăng bề mặt CSWSH khi có ambient session cookies. Nó không tạo authentication/CSRF, không chữa CSP `frame-ancestors` và không phải lựa chọn an toàn cho dữ liệu riêng.

## 10. Allowed origins có thể ảnh hưởng iframe transports

### 10.1. Hạn chế tương thích quan trọng của Spring SockJS

Trong Spring SockJS, các cơ chế giới hạn allowed origins **có liên hệ với việc bật/tắt iframe transports**, vì iframe transport legacy có những hạn chế xác minh Origin đáng tin cậy. Với cấu hình chỉ cho **một tập origins cụ thể**, Spring có thể **vô hiệu iframe-based transports** thay vì cấp quyền cho chúng mà không thể kiểm soát nguồn đầy đủ.

Đừng kết luận:

> “Tôi đã thêm `.setAllowedOrigins("https://app.example.com")`, vậy iframe fallback chắc chắn sẽ hoạt động từ app.example.com.”

Điều đó có thể sai. Hãy đối chiếu **Spring Framework/SockJS version**, cấu hình `allowedOrigins`/`allowedOriginPatterns` và danh sách transports thực tế. Một số legacy iframe transports không thể dùng chỉ bằng cách thêm whitelist.

### 10.2. So sánh policy

| Policy | Tác dụng dự kiến | Hệ quả với iframe |
| --- | --- | --- |
| Same-origin mặc định của SockJS | Giới hạn browser origins cùng source endpoint | Có thể giữ khả năng dùng iframe fallback khi điều kiện framing khác thỏa |
| `setAllowedOrigins("https://trusted.example.com")` | Chỉ cho origins cụ thể | Iframe transports có thể bị hạn chế/vô hiệu trong Spring SockJS |
| `setAllowedOriginPatterns(...)` | Hỗ trợ matching theo patterns | Vẫn phải xác minh giới hạn iframe của phiên bản, không nên giả định được phép |
| `setAllowedOrigins("*")` | Mở rộng phạm vi truy cập origin | Không phù hợp để chữa lỗi legacy iframe trong app có dữ liệu riêng |

Ngay cả khi SockJS **cho chọn iframe transport**, browser vẫn kiểm tra `X-Frame-Options` và CSP. Đó là **hai bộ điều kiện độc lập**.

### 10.3. Nên làm gì trong ứng dụng multi-origin?

Nếu frontend và API không cùng origin:

1. Xác định có thực sự cần legacy iframe-based transports không.
2. Nếu không cần, dùng native WebSocket/XHR fallback theo browser support policy, giữ Origin allowlist cụ thể.
3. Nếu cần iframe, cân nhắc đưa SockJS endpoint **dưới public origin của frontend** qua reverse proxy/BFF.
4. Kiểm tra Spring SockJS allowed-origin restriction không vô hiệu transport đang cần.
5. Không bỏ Origin checks chỉ để “kích hoạt” iframe.
6. Test đúng browser/transport; một browser hiện đại thành công với websocket không chứng minh iframe hoạt động.

## 11. Cấu hình X-Frame-Options bằng Spring Security Servlet

### 11.1. Thay đổi toàn cục là giải pháp dễ nhưng không tối ưu

Một mẫu Spring Security phổ biến để cho same-origin framing là:

~~~java
http.headers(headers ->
    headers.frameOptions(frame -> frame.sameOrigin())
);
~~~

Nó có thể thích hợp khi **toàn bộ phạm vi chain** thật sự cần same-origin framing. Nhưng nếu đây là default chain cho mọi URL, thay đổi đó sẽ mở khả năng frame cho **mọi trang** trong phạm vi, kể cả trang quản trị trước kia được `DENY`.

Một thiết kế thận trọng hơn là **scope header policy** cho SockJS path/iframe resource, giữ strict policy ở các trang khác.

### 11.2. Mẫu SecurityFilterChain giới hạn SockJS path

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SockJsHttpSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain sockJsChain(HttpSecurity http)
            throws Exception {
        return http
            // Scope cả base endpoint và transport paths.
            .securityMatcher("/ws", "/ws/**")
            .authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated()
            )
            // Chỉ nới framing trong phạm vi chain này.
            .headers(headers ->
                headers.frameOptions(frame -> frame.sameOrigin())
            )
            .build();
    }
}
~~~

**Lưu ý rất quan trọng:**

- Đây là **một phần** của HTTP Security, không phải toàn bộ cấu hình login/session cho project. Cần các `SecurityFilterChain` khác bảo vệ các URLs nằm ngoài `/ws`, nếu không ứng dụng có thể vô tình không bảo vệ HTTP routes còn lại.
- Rule `authenticated()` giả định SockJS endpoint phục vụ user đã login; nếu ứng dụng có public/anonymous transport, phải thiết kế HTTP policy riêng, không copy mù.
- Việc scope bằng `/ws/**` có thể rộng hơn **chỉ iframe HTML**, nhưng vẫn hẹp hơn toàn ứng dụng. Nếu cần giữ `DENY` cho những transport paths không phải iframe, phải dùng header writer/matcher chuyên biệt đã kiểm chứng theo version.
- Cấu hình này **không tự thêm CSP `frame-ancestors`**; nếu ứng dụng đã đặt CSP global, cần cấu hình cho phép đúng tài liệu iframe.
- Cấu hình này **không tự giải quyết HTTP CSRF của SockJS POST fallback**, hoặc token CSRF trong STOMP CONNECT.
- Không tuyên bố iframe sẽ hoạt động chỉ từ đoạn code này; còn cần cùng-origin, library và allowed origins/transport compatibility.

### 11.3. Bảo vệ phần còn lại của ứng dụng

Ví dụ phần còn lại có thể sử dụng chain riêng, với chính sách `DENY` cho framing:

~~~java
// Minh họa bổ sung trong cùng project; cần ghép đúng authentication.
@Bean
@Order(2)
SecurityFilterChain restOfApp(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(org.springframework.security.config.Customizer.withDefaults())
        .headers(headers ->
            headers.frameOptions(frame -> frame.deny())
        )
        .build();
}
~~~

Khi có nhiều chains, **chỉ chain khớp đầu tiên** xử lý một request. Đây là lý do cần test path matching của `/ws`, `/ws/**`, `/login` và các HTTP APIs.

### 11.4. CSP cần được kiểm soát trên đúng response

Nếu ứng dụng dùng CSP, một phân vùng chính sách hợp lý là:

~~~text
Trang nghiệp vụ nhạy cảm:
  X-Frame-Options: DENY
  Content-Security-Policy: frame-ancestors 'none'; ...

SockJS iframe document ở same-origin (nếu cần):
  X-Frame-Options: SAMEORIGIN
  Content-Security-Policy: frame-ancestors 'self'; script-src 'self'; ...

Frontend parent:
  Content-Security-Policy: frame-src 'self';
  Content-Security-Policy: connect-src 'self' wss://app.example.com; ...
~~~

Đây là **policy sketch**, không phải một header CSP hoàn chỉnh dùng nguyên văn cho mọi ứng dụng. Các directives phải hợp nhất trong response đúng cách, không vô tình đặt nhiều policies xung đột. CSP của frontend và CSP của iframe là **hai HTTP responses** độc lập.

## 12. Session cookie, SameSite và iframe transports

### 12.1. Same-origin giúp đơn giản hóa cookie, không tạo auth

Khi frontend và SockJS HTTP endpoints cùng public origin, browser thường có thể gửi cookie session phù hợp theo `Domain`/`Path`/`Secure`/`SameSite`. Điều này giảm phức tạp so với third-party iframe cookies, nhưng **server vẫn phải xác thực session**.

Ví dụ:

~~~http
Set-Cookie: SESSION=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- `HttpOnly` ngăn JavaScript đọc cookie nhưng không ngăn browser gửi cookie.
- `Secure` yêu cầu kênh bảo mật phù hợp.
- `SameSite` kiểm soát hành vi gửi cookie theo site context, **không** xác minh WebSocket Origin.
- `Path`/`Domain` phải phù hợp với public path thật sau reverse proxy.
- Thay đổi origin của public endpoint có thể làm cookie trước kia không còn được gửi; phải test login/handshake.

### 12.2. Cross-origin iframe còn chịu cookie restrictions

Nếu frontend `app.example.com` frame API `api.example.com`, ngoài XFO/CSP còn có thể gặp:

- Browser third-party cookie policies.
- Cookie `SameSite` không phù hợp khi frontend và iframe thật sự cross-site.
- Session store/affinity khác giữa HTTP requests.
- Login redirect trong iframe dẫn tới blocked frame hoặc navigation khác mong muốn.
- Khác biệt giữa cookie trên XHR fallback và cookie trên native WebSocket handshake.

Vì vậy cấu hình CORS đúng chưa chứng minh login/session hoạt động qua iframe. **Không** vô hiệu hóa HttpOnly, SameSite hoặc xác thực HTTP chỉ để phục vụ một transport legacy.

### 12.3. SessionCookieNeeded trong SockJS

Một số cấu hình SockJS có thể công bố thuộc tính `cookie_needed` thông qua `/info` để client lựa chọn transport tương thích việc dùng cookies. Ví dụ khái niệm:

~~~json
{
  "websocket": true,
  "cookie_needed": true,
  "origins": ["*:*"]
}
~~~

Đây là **thông tin protocol/capability**, không phải phản hồi cấp quyền cho mọi Origin, không phải Spring Security principal, và cũng không có nghĩa mọi response sẽ cho CORS wildcard. Trường `origins` trong thông tin SockJS không được dùng để kết luận security allowlist thực tế.

Một API cấu hình như `setSessionCookieNeeded(boolean)` có thể thay đổi cách SockJS thông báo nhu cầu cookie. Nó **không tự phát session cookie, không bật authentication và không thay csrf/messaging authorization**. Nếu hệ thống dùng session login, đừng đặt false chỉ để buộc client chọn transport dễ hơn mà không đánh giá hệ quả.

## 13. HTTP CORS cho XHR fallback khác framing policy

### 13.1. XHR fallback cần CORS khi khác origin

Nếu browser ở `https://app.example.com` dùng XHR transport tới `https://api.example.com/ws`, CORS có thể được áp dụng trên các HTTP requests. Response phù hợp có thể chứa:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Nếu browser gửi credentialed requests, không thể dùng `Access-Control-Allow-Origin: *` để cho JavaScript đọc credentialed responses. Một preflight OPTIONS **có thể** xuất hiện tùy method/headers của transport, không phải mọi SockJS request đều chắc chắn có preflight.

Spring SockJS có thể tự phát các CORS response headers cho transport tương ứng; nếu gateway và `CorsFilter` cũng phát ACAO/ACAC, có thể xảy ra header trùng hoặc chính sách xung đột. Cần quyết định layer sở hữu policy và kiểm tra response thực tế.

### 13.2. Iframe không được mở bởi CORS

Một tài liệu iframe bị:

~~~http
X-Frame-Options: DENY
~~~

vẫn không thể nhúng chỉ nhờ:

~~~http
Access-Control-Allow-Origin: https://app.example.com
~~~

Vì ACAO không thay đổi quan hệ same-origin giữa parent/iframe và không bãi bỏ XFO.

### 13.3. Origin validation không chứng minh user identity

Một non-browser client có thể tự khai `Origin`. Origin allowlist giúp giới hạn website chạy script trong browser, không thay xác thực bằng session/bearer token hay quyền theo user/object.

Nếu ứng dụng có cookies tự gửi, giữ Origin check chặt cùng CSRF CONNECT và authorization để giảm nguy cơ Cross-Site WebSocket Hijacking (CSWSH).

## 14. HTTP CSRF của SockJS POST và CSRF trong STOMP CONNECT

### 14.1. Hai phép kiểm tra khác nhau

Trong SockJS XHR fallback có thể có HTTP POST, ví dụ:

~~~http
POST /ws/000/abc/xhr_send HTTP/1.1
Host: app.example.com
Cookie: SESSION=<alice-session>
Content-Type: text/plain

["<encoded-SockJS-message>"]
~~~

Spring Security Servlet `CsrfFilter` có thể từ chối request POST này nếu nó không chứa HTTP CSRF token theo request matcher. Đó là lỗi **HTTP transport**, không phải trực tiếp là STOMP CONNECT CSRF.

Bên trong transport, client còn gửi:

~~~text
CONNECT
X-CSRF-TOKEN:<valid-session-token>

^@
~~~

Spring Security Messaging với `@EnableWebSocketSecurity` yêu cầu token hợp lệ ở **STOMP CONNECT** theo protection mặc định tương ứng; đây là phép kiểm tra riêng trên client inbound channel.

### 14.2. Không tắt CSRF toàn ứng dụng để sửa SockJS

Phản ví dụ:

~~~java
// Không phải biện pháp khuyến nghị để sửa một SockJS transport.
http.csrf(csrf -> csrf.disable());
~~~

Nếu thật sự cần exception cho HTTP POST transport, giới hạn **đúng request matcher của SockJS transport**, bảo đảm namespace không chứa HTTP API nghiệp vụ, và tiếp tục bảo vệ các POST/PUT/PATCH/DELETE khác. Đừng bỏ STOMP CONNECT CSRF.

### 14.3. Phân loại một lỗi 403

| Quan sát | Tầng kiểm tra khả dĩ |
| --- | --- |
| HTTP `POST /ws/.../xhr_send` trả 403 | HTTP CSRF, CORS, authentication, gateway |
| HTTP `GET /ws/iframe.html` bị 403 | HTTP auth, matcher hoặc ứng dụng |
| Iframe HTTP 200 nhưng browser không render | XFO hoặc CSP `frame-ancestors`/`frame-src` |
| Iframe render nhưng script không chạy | CSP `script-src`, client library URL/content type |
| Transport mở rồi STOMP CONNECT bị `ERROR` | CSRF CONNECT, principal, token verifier, protocol |
| CONNECTED nhưng SEND/SUBSCRIBE bị từ chối | Message authorization/ACL |

Không sửa một lỗi framing bằng cách tắt CSRF. Cũng không sửa CONNECT CSRF bằng việc mở iframe cho mọi origin.

## 15. @EnableWebSocketSecurity vẫn cần cho SEND và SUBSCRIBE

Một SockJS transport không làm message trở nên đáng tin hơn. Sau khi STOMP CONNECT thành công, client có thể gửi lệnh hoặc đăng ký các topics mà không được phép nếu message authorization thiếu.

### 15.1. Mẫu cấu hình inbound message security

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
class RealtimeMessageSecurity {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
        MessageMatcherDelegatingAuthorizationManager.Builder messages
    ) {
        return messages
            .nullDestMatcher().authenticated()
            .simpSubscribeDestMatchers("/app/**").denyAll()
            .simpSubscribeDestMatchers(
                "/user/queue/order-results",
                "/topic/public"
            ).authenticated()
            .simpDestMatchers("/app/orders.lookup").hasRole("USER")
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()
            .anyMessage().denyAll()
            .build();
    }
}
~~~

### 15.2. Tại sao gửi trực tiếp broker nguy hiểm?

Client gửi:

~~~text
SEND
destination:/topic/public

{"message":"SYSTEM: Dữ liệu đã được phê duyệt"}
^@
~~~

Nếu broker phát payload mà không qua `@MessageMapping` và service kiểm tra quyền, attacker có thể giả mạo thông báo của hệ thống. Policy trên cho phép SEND vào `/app/orders.lookup` theo role, còn MESSAGE/SEND tới broker `/topic/**` bị deny.

### 15.3. SUBSCRIBE cũng cần ACL theo object

Một user Alice có thể thử:

~~~text
SUBSCRIBE
id:orders-of-bob
destination:/topic/orders/2002

^@
~~~

Nếu topic mang dữ liệu riêng, `authenticated()` cho `/topic/orders/**` là quá rộng. Cần kiểm tra Alice có quyền với order 2002 khi SUBSCRIBE và/hoặc ngay trước lúc server phát. User destinations không tự sửa lỗi business ACL.

### 15.4. Outbound và session lifecycle

Inbound security không tự bảo vệ mọi server-side publish. Khi user logout, role bị thu hồi hoặc rời tenant, một SockJS/WebSocket session cũ có thể còn tồn tại; cần cơ chế thu hồi connection/subscriptions hoặc revalidate quyền theo dữ liệu hiện thời. Không coi CONNECT hợp lệ lúc ban đầu là quyền vĩnh viễn.

## 16. Client SockJS và STOMP: cấu hình và quan sát transport

### 16.1. Frontend same-origin

Trong mô hình reverse proxy, client dùng URL public cùng origin:

~~~javascript
import SockJS from "sockjs-client";
import { Client } from "@stomp/stompjs";

const client = new Client({
  webSocketFactory: () =>
    new SockJS("https://app.example.com/ws"),

  reconnectDelay: 3000,

  // Với session-based Spring Messaging, CONNECT thường cần
  // native CSRF header. Lấy giá trị từ HTTP endpoint đúng phiên.
  connectHeaders: {
    "X-CSRF-TOKEN": csrfToken
  },

  onConnect: () => {
    client.subscribe("/user/queue/order-results", message => {
      console.log("Kết quả:", message.body);
    });
  },

  onStompError: frame => {
    console.error("STOMP ERROR:", frame.headers.message);
  }
});

client.activate();
~~~

`csrfToken` là giá trị **ứng dụng phải lấy/cấp**, không phải biến SockJS tự sinh. `webSocketFactory` quyết định cách mở SockJS transport; `connectHeaders` tạo **STOMP native headers**, không phải arbitrary HTTP headers trên mỗi XHR/iframe request.

### 16.2. HTTP endpoint cấp token cho phiên

Ví dụ một Spring MVC controller:

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
    ResponseEntity<Map<String, String>> token(
        @RequestAttribute("_csrf") CsrfToken csrf
    ) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", csrf.getHeaderName(),
                "token", csrf.getToken()
            ));
    }
}
~~~

Endpoint `/api/csrf` do **ứng dụng tự tạo** và phải được bảo vệ theo chính sách login; không tự tồn tại trong Spring Boot. Frontend dùng `fetch("/api/csrf", {credentials: "same-origin"})` trong mô hình public same-origin và truyền `headerName`/`token` tương ứng vào STOMP CONNECT.

Khi session đổi sau login/logout, cần làm mới token và reconnect; không giữ token cũ vô thời hạn.

### 16.3. Quan sát transport trong browser

Trong DevTools → Network, tìm:

- `GET /ws/info` để xem SockJS discovery.
- `/ws/.../websocket` hoặc Upgrade để xác định native WebSocket.
- `/ws/.../xhr_streaming`, `/xhr_send`, `/xhr` để xác định HTTP fallback.
- Tài liệu `/ws/iframe...html` nếu iframe transport thực sự được dùng.
- Các request tải `sockjs.min.js` bên trong iframe.
- STOMP `CONNECT`/`CONNECTED`/`ERROR` trong công cụ hiển thị frames/payload phù hợp transport.

Nếu browser chỉ chọn native WebSocket, test đó **chưa chứng minh** iframe fallback có thể được nhúng.

### 16.4. Ép một transport để kiểm thử có giới hạn

SockJS client hỗ trợ một số tùy chọn giới hạn transports tùy version, ví dụ minh họa:

~~~javascript
// Kiểm thử HTTP XHR fallback trong môi trường hỗ trợ:
const sock = new SockJS(
  "https://app.example.com/ws",
  null,
  { transports: ["xhr-polling"] }
);
~~~

Đoạn này giúp thử **XHR fallback**, không phải phép thử iframe. Để kiểm tra iframe-based transports, cần browser/runtime thực sự hỗ trợ loại iframe transport đang xét và phiên bản SockJS phù hợp. Việc ép một transport lỗi thời trên Chrome hiện đại có thể thất bại vì transport **không được hỗ trợ**, không phải do XFO.

Không khẳng định một test XHR polling thành công cũng chứng minh iframe HTML framing thành công.

## 17. Kiểm thử bảo mật cho iframe same-origin

### 17.1. Ma trận xác định quyết định frame

| Mã | Trang cha | Iframe response | Kỳ vọng |
| --- | --- | --- | --- |
| F1 | `https://app.example.com` | Iframe `https://app.example.com/ws/iframe...` + XFO SAMEORIGIN + CSP cho same-origin | Frame được phép nếu browser/transport hỗ trợ |
| F2 | `https://evil.example.net` | Cùng iframe app + XFO SAMEORIGIN | Bị chặn |
| F3 | `https://app.example.com` | Iframe `https://api.example.com/ws/iframe...` + XFO SAMEORIGIN | Bị chặn vì khác origin |
| F4 | Cùng-origin | Iframe + XFO DENY | Bị chặn |
| F5 | Cùng-origin | Iframe + CSP frame-ancestors 'none' | Bị chặn |
| F6 | Cùng-origin | Iframe cho frame nhưng parent CSP frame-src 'none' | Bị parent CSP chặn |
| F7 | Cùng-origin | Frame được phép, script-src không cho URL library | Frame tải nhưng library có thể không chạy |
| F8 | Cùng-origin | Iframe cùng origin nhưng library URL 404 hoặc redirect login | Fallback lỗi do library |
| F9 | Khác-origin | Parent CORS/ACAO mở nhưng iframe XFO SAMEORIGIN | Vẫn bị chặn |
| F10 | Cùng-origin | Specific allowed origins khiến iframe transport bị framework vô hiệu | Không có iframe transport để test framing |

F1 chỉ là **điều kiện cho phép framing**, chưa bảo đảm STOMP CONNECT, authentication và mọi fallback behavior thành công. Các browser/transport cũ cần được kiểm tra bằng ma trận môi trường hỗ trợ thực.

### 17.2. Kiểm thử clickjacking regression

Khi đổi XFO/CSP để SockJS iframe chạy, hãy kiểm tra các trang khác:

| Tài nguyên | Chính sách mong muốn |
| --- | --- |
| SockJS iframe document được yêu cầu | SAMEORIGIN hoặc CSP allowlist đúng phạm vi |
| Trang quản trị `/admin` | Vẫn DENY / frame-ancestors 'none' nếu không cần frame |
| Form thay đổi mật khẩu | Vẫn chống framing/clickjacking |
| Trang thanh toán hoặc dữ liệu riêng | Không bị mở rộng embedding ngoài ý định |
| API JSON không cần iframe | Không cần nới framing chỉ để có SockJS |

Một test chỉ chứng minh iframe hoạt động nhưng làm trang admin bị nhúng từ site lạ là **thất bại bảo mật**.

### 17.3. Kiểm thử các lớp sau framing

Sau khi browser tải được iframe/transport, test:

1. HTTP session cookie được gửi và backend nhận đúng principal.
2. STOMP CONNECT có native CSRF token đúng.
3. CONNECT thiếu/sai token bị từ chối.
4. SEND chỉ được vào `/app/**` commands hợp lệ.
5. SUBSCRIBE không vào protected topics của user khác.
6. Không có dữ liệu người khác bị phát qua broker.
7. Session logout/revoke không tiếp tục cho quyền trái ý định.
8. Không có token trong URL, logs và iframe script console.

**“Iframe hiển thị được” không đồng nghĩa “Realtime đã được bảo vệ”.**

## 18. Kiểm thử Spring integration: header, transport và STOMP

### 18.1. Test HTTP header riêng khỏi test STOMP

Có thể dùng `MockMvc` để kiểm tra HTTP response headers cho các URLs mà security chains quản lý. Ví dụ skeleton:

~~~java
// Pseudocode cấu trúc test HTTP headers:
mockMvc.perform(get("/ws/info").with(user("alice")))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "X-Frame-Options", "SAMEORIGIN"
    ));

// Test trang admin / sensitive page vẫn DENY:
mockMvc.perform(get("/admin").with(user("admin")))
    .andExpect(header().string(
        "X-Frame-Options", "DENY"
    ));
~~~

Đây **không phải** test độc lập đã chạy. Cần imports, test configuration, handler mappings và actual auth setup. Response của SockJS iframe HTML phải được kiểm tra **trực tiếp** nếu muốn xác nhận chính xác CSP/XFO trên tài liệu iframe. Một GET `/ws/info` có XFO SAMEORIGIN chưa chứng minh iframe document mang header tương đương trong mọi đường đi.

### 18.2. Test browser thực cho frame policy

Với Playwright/Selenium hoặc kiểm tra thủ công trong các browser được sản phẩm hỗ trợ:

~~~text
Given:
  Frontend tại https://app.example.com.
  SockJS endpoint cùng public origin /ws.
  SockJS iframe transport được hỗ trợ/bật trong môi trường test.
  SockJS iframe response có XFO SAMEORIGIN.
  CSP iframe frame-ancestors 'self' và script-src phù hợp.
  Frontend CSP cho frame-src 'self'.

When:
  Browser thực sự chọn iframe fallback.
Then:
  Tài liệu iframe được tải, không bị XFO/CSP chặn.
  Library bên trong iframe trả 200 + type hợp lệ.
  SockJS transport sẵn sàng để STOMP CONNECT.
  Principal và CSRF CONNECT được kiểm tra đúng.

Negative:
  Parent từ origin không tin cậy.
Then:
  Iframe bị frame policy chặn; không có data leak.
~~~

Một headless browser hiện đại có thể không hỗ trợ legacy iframe transport nên test phải mô tả **môi trường thực sự có transport**, không chỉ thêm option `transports:["iframe-*"]` rồi giả định.

### 18.3. STOMP integration vẫn cần sau fallback

Dùng `WebSocketStompClient` với server thật để test STOMP CONNECT/SEND/SUBSCRIBE trên native WebSocket. Nhưng `WebSocketStompClient` không mô phỏng đầy đủ các browser iframe fallback và CSP restrictions.

Với iframe, cần browser integration/harness đúng transport. Với HTTP/SockJS XHR, cần test các HTTP transport requests, cookie và CSRF rules. Kết hợp nhiều tầng test thay vì lấy một kết quả CONNECTED native để kết luận tất cả transports đều an toàn.

### 18.4. Kiểm tra fallback qua proxy và nhiều backend nodes

Nếu reverse proxy cân bằng tải, kiểm tra:

- SockJS requests cùng session được route đúng state hoặc có shared session mechanism.
- HTTP paths giữ nguyên URL/method, Origin và Cookie.
- CORS/XFO/CSP không bị gateway thêm trùng hoặc override.
- Sticky sessions nếu cần, không dựa vào load balancer route ngẫu nhiên làm phiên không ổn định.
- Session/token repository cùng ngữ cảnh ở HTTP API và WebSocket/SockJS.
- Protocol Upgrade hoạt động ở route native; HTTP fallback không bị 404.
- Library URL có sẵn ở mọi node/public route.

## 19. Troubleshooting: từ lỗi frame tới lỗi STOMP

| Triệu chứng | Nguyên nhân có thể | Điều cần kiểm tra |
| --- | --- | --- |
| Native WebSocket chạy, legacy fallback không | Fallback iframe/XHR không được cấu hình | Network transport được chọn và browser support |
| “X-Frame-Options DENY” | Spring Security header mặc định | Response iframe HTML, scoped SAMEORIGIN nếu cần |
| “SAMEORIGIN” nhưng iframe vẫn bị chặn | Parent và iframe khác scheme/host/port | So public origin chính xác |
| Đã đổi ACAO nhưng iframe vẫn bị chặn | CORS không vượt XFO | XFO/CSP framing policies |
| CSP “frame-ancestors 'none'” | CSP trên iframe response cấm embedding | Đúng document response; đổi policy hẹp |
| CSP “frame-src blocked” | CSP của trang cha không cho iframe URL | Parent frame-src |
| Iframe tải nhưng không chạy | Script URL sai hoặc script-src chặn | setClientLibraryUrl, library response, script-src |
| Thấy CDN SockJS library bị chặn | CSP script-src chỉ self | Host library cùng public origin |
| iframe URL 302 về login | HTTP auth/redirect tại iframe path | Session cookie/path, SecurityFilterChain |
| /ws/info OK nhưng iframe transport vắng mặt | Framework version / allowed origins hạn chế | Transport configuration, browser hỗ trợ |
| Explicit allowedOrigins khiến iframe bị vô hiệu | Spring SockJS restrictions | Kiểm tra policy/version, cân nhắc same-origin route |
| XHR fallback báo CORS error | ACAO/ACAC/preflight/gateway | HTTP transport response, duplicate CORS |
| XHR POST /xhr_send trả 403 | HTTP CSRF hoặc authentication | CSRF HTTP matcher, cookies |
| Iframe OK nhưng CONNECT bị ERROR | CSRF STOMP CONNECT/token/principal | Native CONNECT headers |
| HTTP 101 nhưng không CONNECTED | STOMP auth/CSRF issue | Frames, messaging logs |
| CONNECTED nhưng SEND bị deny | Message matcher/role | MESSAGE vs SUBSCRIBE rules |
| CONNECTED nhưng SUBSCRIBE admin bị deny | Subscription ACL | Role/destination |
| Nhận data của user khác | Object/tenant ACL hoặc outbound routing sai | Service, broker, subscriptions |
| Cookie không xuất hiện trên fallback | Cookie scope/third-party browser policy | Domain/Path/SameSite/Secure, public origin |
| Frame từ localhost:3000 tới localhost:8080 bị chặn | Khác port nên khác origin | Proxy cùng port hoặc test đúng policy |
| Browser mixed content warning | HTTPS page gọi HTTP iframe/transport | Dùng HTTPS/WSS public paths |
| Sau logout socket vẫn nhận dữ liệu | Lifecycle/revocation thiếu | Close/revalidate sessions và subscriptions |
| XFO SAMEORIGIN xuất hiện trên /admin | Header scoped chain quá rộng | SecurityFilterChain matcher ordering |
| Proxy thêm CSP/XFO không giống Spring | Header bị override/trùng ở gateway | Response cuối cùng trên browser |

### 19.1. Quy trình chẩn đoán theo tầng

~~~mermaid
flowchart TD
    A["SockJS kết nối thất bại"] --> B{"Transport thực sự là gì?"}
    B -- "Native WebSocket" --> C["HTTP Upgrade, Origin, TLS, Cookie"]
    B -- "XHR fallback" --> D["HTTP CORS/CSRF, Cookie, proxy paths"]
    B -- "Iframe legacy" --> E{"Iframe document tải được?"}
    E -- "Không" --> F["XFO DENY/SAMEORIGIN, frame-ancestors, frame-src"]
    E -- "Có" --> G{"SockJS library tải/chạy được?"}
    G -- "Không" --> H["script-src, setClientLibraryUrl, 404/redirect"]
    G -- "Có" --> I["Tiếp tục kiểm tra transport HTTP và STOMP"]
    C --> I
    D --> I
    I --> J{"STOMP CONNECTED?"}
    J -- "Không" --> K["CSRF CONNECT, Principal, token verifier"]
    J -- "Có" --> L["SEND/SUBSCRIBE, object ACL, outbound routing"]
~~~

Không sửa một lỗi ở frame bằng cách tắt authentication; cũng không sửa lỗi ở STOMP CONNECT bằng cách nới toàn bộ `X-Frame-Options`.

## 20. Quyết định kiến trúc: bảo vệ tốt hơn bằng cách giảm legacy surface

### 20.1. Khi chỉ phục vụ browser hiện đại

Nếu dữ liệu sử dụng và hợp đồng hỗ trợ browser xác nhận không cần iframe transport:

- Có thể ưu tiên native WebSocket.
- Khi cần HTTP fallback, chỉ hỗ trợ những transports thực sự cần và tương thích với bảo mật.
- Giữ default framing policy nghiêm ngặt cho các HTML pages.
- Đơn giản hóa public origins, CORS và CSRF để giảm trường hợp góc.
- Có telemetry về transport success/fallback rate trước khi quyết định bỏ một transport.

**Ít transports hơn** có thể làm hệ thống dễ kiểm chứng an toàn hơn, nhưng hãy căn cứ yêu cầu sản phẩm, không xóa SockJS một cách mù quáng nếu môi trường vận hành vẫn phụ thuộc fallback.

### 20.2. Khi bắt buộc hỗ trợ browser cũ

Dùng một public same-origin path qua reverse proxy nếu có thể. Giới hạn XFO/CSP cho iframe document, host library cùng origin, giữ session authentication/CSRF và kiểm thử browser thực sự hỗ trợ legacy iframe.

Phải chấp nhận rằng một số yêu cầu hiện đại (ví dụ strict origin allowlist, CSP, chặn third-party cookies) có thể **không tương thích** với legacy iframe. Khi không thể cân bằng, cần công bố browser support policy thay vì tắt lớp bảo vệ trung tâm.

### 20.3. Không coi SockJS là giải pháp bảo mật

SockJS giúp **khả năng kết nối**, không bảo đảm:

- Chống CSRF hay CSWSH.
- Xác thực user.
- Bảo vệ SEND/SUBSCRIBE.
- Chống clickjacking.
- Đúng CORS/CSP trên mọi transport.
- Thu hồi socket khi session hết hạn.
- Multi-tenant isolation.
- Giới hạn lưu lượng và tài nguyên.

Từng lớp có cấu hình và kiểm thử riêng.

## 21. Đối chiếu Servlet SockJS và WebFlux native

### 21.1. Servlet + Spring STOMP/SockJS

Đường đi bài này được xây trên:

~~~text
Spring MVC/Servlet
  -> WebSocketMessageBrokerConfigurer
  -> StompEndpointRegistry.addEndpoint("/ws").withSockJS()
  -> SockJS transport selection
  -> HTTP security headers/cookies/CORS/CSRF ở fallback
  -> STOMP CONNECT security
  -> SEND/SUBSCRIBE AuthorizationManager + service ACL
~~~

XFO/CSP của legacy iframe chủ yếu là vấn đề **Servlet SockJS iframe HTML response + browser framing policy**.

### 21.2. WebFlux native WebSocket

WebFlux native cung cấp `WebSocketHandler`/`WebSocketSession`, không tự đồng nghĩa Spring Servlet `@EnableWebSocketMessageBroker`/`withSockJS()` và STOMP `CONNECT`.

Ví dụ HTTP handshake security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveHandshakeSecurity {

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/ws").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Nếu WebFlux application **tự cung cấp** iframe-based fallback bằng một thư viện khác, vẫn phải kiểm soát browser origin, XFO/CSP, session cookies và authorization của protocol đó. Không sao chép trực tiếp `StompEndpointRegistry.withSockJS()` vào native WebFlux rồi giả định hệ thống sẽ có các transports/security interceptors giống Servlet.

### 21.3. Native WebFlux message-level authorization

Một native handler có thể lấy principal từ handshake:

~~~java
import java.security.Principal;

import reactor.core.publisher.Mono;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.reactive.socket.WebSocketHandler;

interface RealtimeReactiveService {
    // Parse, validate và phân quyền từng message/object.
    Mono<Void> authorizeAndHandle(
        Principal principal,
        String payload
    );
}

class SecureReactiveWebSocketHandler {

    static WebSocketHandler create(RealtimeReactiveService service) {
        return session -> session.getHandshakeInfo()
            .getPrincipal()
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Unauthenticated")))
            .flatMap(principal ->
                session.receive()
                    .concatMap(frame ->
                        service.authorizeAndHandle(
                            principal, frame.getPayloadAsText()
                        ))
                    .then()
            );
    }
}
~~~

Đây là skeleton chưa có handler mapping, outbound send/backpressure, rate limits hoặc origin guard. WebFlux native không mặc định có `CsrfChannelInterceptor` của STOMP Servlet khi không dùng STOMP.

## 22. Checklist production

- [ ] Xác nhận sản phẩm **thực sự cần** iframe fallback thay vì chỉ native WebSocket/XHR.
- [ ] Đã quan sát transport hiện hành qua Network, không suy diễn từ tên “SockJS”.
- [ ] Origin của trang cha và iframe HTML được so chính xác theo scheme, host, port.
- [ ] Nếu dùng `SAMEORIGIN`, iframe HTML và trang cha thực sự cùng public origin.
- [ ] Không dùng CORS `Access-Control-Allow-Origin` để cố vượt XFO.
- [ ] Không dùng `X-Frame-Options: ALLOW-FROM` như giải pháp cross-origin hiện đại.
- [ ] Trang nhạy cảm không cần frame vẫn giữ XFO DENY hoặc CSP frame-ancestors 'none'.
- [ ] XFO SAMEORIGIN chỉ áp dụng vào phạm vi SockJS phù hợp, không mở rộng ngoài ý định.
- [ ] CSP trên **iframe response** có `frame-ancestors` đúng policy.
- [ ] CSP trên **parent response** có `frame-src` cho đúng iframe origin.
- [ ] CSP `script-src` cho phép SockJS client library được phục vụ ở origin tin cậy.
- [ ] CSP `connect-src` cho phép đúng HTTP/WSS endpoints cần thiết.
- [ ] `setClientLibraryUrl`, nếu dùng, trỏ tới asset thực tế đúng version và public path.
- [ ] SockJS `allowedOrigins`/patterns không vô hiệu iframe transports mà sản phẩm cần hỗ trợ.
- [ ] Không nới Origin wildcard để sửa lỗi iframe hoặc legacy browser.
- [ ] Nếu dùng proxy cùng origin, kiểm tra forwarded headers, WebSocket Upgrade, path rewrites và cookies.
- [ ] Session cookie có `Secure`, `HttpOnly`, `SameSite`/Domain/Path phù hợp với public origin.
- [ ] Không dựa vào `cookie_needed` của SockJS /info để suy ra authentication/allowlist.
- [ ] HTTP CORS/CSRF trên SockJS XHR fallback được phân biệt với STOMP CONNECT CSRF.
- [ ] Không tắt toàn bộ HTTP CSRF khi chỉ một SockJS transport POST bị 403.
- [ ] STOMP CONNECT phải có principal/CSRF hợp lệ theo security policy.
- [ ] SEND/SUBSCRIBE có `AuthorizationManager<Message<?>>` deny-by-default.
- [ ] Private topics cần object/tenant ACL; server không phát dữ liệu riêng lên public topic.
- [ ] Logout/session expiry/role revocation có close/revalidate socket/subscriptions.
- [ ] Có rate limits, connection quotas, frame size, idle timeout và logging redaction.
- [ ] Test iframe framing **với browser hỗ trợ legacy transport**, không dùng test native WS thay thế.
- [ ] Negative tests chứng minh iframe từ origin lạ bị chặn và trang admin không bị nới clickjacking policy.
- [ ] WebFlux native không bị nhầm với Spring Servlet SockJS/STOMP integration.

## 23. Câu hỏi vận dụng và lời giải

**Tình huống 1 — DENY.** Native WebSocket hoạt động nhưng browser cũ báo iframe bị `X-Frame-Options: DENY`. Có phải STOMP token sai?

**Đáp án:** Không nhất thiết. Transport iframe bị chặn **trước STOMP CONNECT**. Kiểm tra response iframe, browser transport và chỉ cho phép framing hẹp khi thật sự cần.

**Tình huống 2 — SAMEORIGIN nhưng vẫn lỗi.** Trang `https://app.example.com` nhúng iframe `https://api.example.com/ws/iframe.html` với XFO SAMEORIGIN. Có được không?

**Đáp án:** Không. Hai host khác nên khác origin. CORS cũng không khiến chúng cùng origin. Cân nhắc reverse proxy để iframe có public URL cùng origin hoặc loại bỏ iframe fallback.

**Tình huống 3 — Cùng site.** `https://shop.example.com` và `https://api.example.com` cùng site. SAMEORIGIN có cho nhúng không?

**Đáp án:** Không. Same-site không đồng nghĩa same-origin. XFO SAMEORIGIN xét scheme/host/port.

**Tình huống 4 — Localhost.** Trang `http://localhost:3000` và iframe `http://localhost:8080` có cùng origin không?

**Đáp án:** Không, vì khác port. Dev proxy về cùng cổng public hoặc test đúng chính sách để tái hiện production.

**Tình huống 5 — CORS wildcard.** Backend thêm `Access-Control-Allow-Origin: *` nhưng iframe vẫn bị DENY. Nguyên nhân?

**Đáp án:** CORS không thay XFO; hơn nữa wildcard CORS có thể sai/không an toàn khi gửi credentials. Kiểm tra frame policy thay vì mở CORS.

**Tình huống 6 — CSP frame-ancestors.** XFO đã SAMEORIGIN, nhưng iframe response còn `frame-ancestors 'none'`. Có hoạt động không?

**Đáp án:** Không. CSP ngăn embedding. Chính sách phải được điều chỉnh hẹp trên đúng iframe response theo trust boundary.

**Tình huống 7 — Parent frame-src.** Iframe cho phép same-origin nhưng frontend CSP có `frame-src 'none'`. Cần sửa gì?

**Đáp án:** Parent CSP phải cho đúng iframe URL/origin; chỉ sửa iframe response không đủ.

**Tình huống 8 — Script-src.** Iframe đã tải nhưng browser chặn SockJS client từ CDN. Có phải XFO sai?

**Đáp án:** Không. Đây là `script-src`/URL library. Có thể dùng `setClientLibraryUrl` trỏ tới asset được host đúng origin, version và CSP.

**Tình huống 9 — ClientLibraryUrl.** Đặt library cùng origin với API có tự sửa iframe HTML khác origin với frontend không?

**Đáp án:** Không. XFO SAMEORIGIN phụ thuộc origin **iframe document** so với parent; script URL không đổi origin tài liệu iframe.

**Tình huống 10 — Allowed origin cụ thể.** Đã khai `setAllowedOrigins("https://app.example.com")` nhưng legacy iframe transport không được dùng. Vì sao?

**Đáp án:** Spring SockJS có hạn chế iframe transports khi giới hạn allowed origins cụ thể vì khó xác minh Origin trên legacy iframe. Kiểm tra version/transport configuration và cân nhắc cùng-origin deployment thay vì mở wildcard.

**Tình huống 11 — XHR hoạt động.** Forced `xhr-polling` test PASS. Có thể tuyên bố iframe fallback PASS không?

**Đáp án:** Không. XHR fallback không phải iframe transport. Cần browser/harness hỗ trợ iframe thật và kiểm tra XFO/CSP/script.

**Tình huống 12 — /info công bố cookie_needed.** `/ws/info` trả `cookie_needed:true`. Có nghĩa user đã authenticated chưa?

**Đáp án:** Không. Đây là thông tin SockJS dùng khi chọn transport. Authentication vẫn phải xảy ra qua HTTP/Spring Security.

**Tình huống 13 — CSRF POST.** XHR fallback `POST /ws/.../xhr_send` bị 403 trước CONNECT. Có phải `CsrfChannelInterceptor` từ chối?

**Đáp án:** Chưa chắc; HTTP `CsrfFilter`, authentication, CORS hoặc proxy có thể chặn transport POST. Tách kiểm tra HTTP và messaging.

**Tình huống 14 — Tắt HTTP CSRF.** Dev muốn disable HTTP CSRF toàn project để fallback chạy. Có phù hợp không?

**Đáp án:** Không. Chỉ xem xét exception cực hẹp cho transport cần thiết, tiếp tục bảo vệ REST/form POST/PUT và giữ STOMP CONNECT CSRF.

**Tình huống 15 — CONNECTED nhưng không nhận kết quả.** Iframe đã hoạt động và STOMP CONNECTED, nhưng `SUBSCRIBE /topic/orders/2002` bị deny. Lỗi iframe không?

**Đáp án:** Không. Đây là subscription/object authorization. Frame transport hoạt động đúng nhưng user không có quyền nghe order đó.

**Tình huống 16 — Trang admin bị frame.** Sau khi đổi XFO SAMEORIGIN toàn cục, trang admin cũng có thể bị same-origin iframe nhúng. Cần làm gì?

**Đáp án:** Scope policy vào SockJS iframe/transport path phù hợp, giữ DENY hoặc frame-ancestors 'none' cho trang nhạy cảm không cần embedding, và test regression.

**Tình huống 17 — Proxy sửa host.** Public frontend và iframe cùng `app.example.com` nhưng backend tự tạo URLs chứa `internal-spring:8080`. Điều tra?

**Đáp án:** Kiểm tra public URL mapping, forwarded headers chỉ từ trusted proxy, đường dẫn SockJS, cookie scope và library URL. Browser đánh giá public origin của resource được tải, không dựa host nội bộ.

**Tình huống 18 — Browser cũ và CSP modern.** Nhóm dùng CSP `frame-ancestors` để cho một origin khác nhúng iframe, kỳ vọng hỗ trợ mọi browser rất cũ. Có chắc không?

**Đáp án:** Không. Browser legacy có thể không hỗ trợ CSP hiện đại; ngoài ra XFO và giới hạn allowed origins của SockJS vẫn ảnh hưởng. Cùng-origin proxy hoặc điều chỉnh browser support là hướng đáng cân nhắc.

**Tình huống 19 — WebFlux native.** Một ứng dụng chỉ dùng WebFlux `WebSocketHandler` có tự nhận được SockJS iframe transports từ `@EnableWebSocketSecurity` không?

**Đáp án:** Không. Native WebFlux không tự là Spring Servlet SockJS/STOMP. Nếu ứng dụng tự triển khai fallback, cần bảo vệ frame/cookie/Origin và message protocol theo stack thực tế.

**Tình huống 20 — Nguy cơ rò rỉ dữ liệu.** Iframe hoạt động, SEND/SUBSCRIBE bị kiểm soát tốt, nhưng server tự phát order riêng lên `/topic/public`. Có an toàn không?

**Đáp án:** Không. Outbound routing và business ACL vẫn phải bảo đảm dữ liệu được phát đúng user/tenant; SockJS/XFO không giải quyết lỗi này.

---

**Ghi nhớ:** **SockJS iframe fallback là nhu cầu tương thích transport, không phải lý do bỏ phòng vệ clickjacking.** Với `X-Frame-Options: SAMEORIGIN`, **trang cha và tài liệu iframe phải thật sự cùng origin (scheme, host, port)**; cùng site, CORS đúng hay cùng DNS root đều không đủ. Khi buộc hỗ trợ legacy iframe, ưu tiên **public same-origin reverse proxy**, chỉ nới XFO/CSP ở những responses cần thiết, host SockJS iframe library đúng origin và kiểm tra Spring allowed-origin/transport restrictions. Khi không cần iframe, giữ DENY cho nội dung nhạy cảm và ưu tiên transports hiện đại. Luôn tách **iframe/CSP, HTTP CORS/CSRF, STOMP CONNECT CSRF, SEND/SUBSCRIBE authorization và object/tenant ACL**, vì sửa đúng một tầng không bảo vệ thay các tầng còn lại.
