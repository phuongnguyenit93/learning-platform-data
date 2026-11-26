# connect-src cho fetch, WebSocket và các kết nối phía client

> **Chương:** Chính sách nội dung CSP  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Bài toán: JavaScript được chạy nhưng có thể kết nối đi đâu?

Một ứng dụng dashboard tải JavaScript từ chính origin của trang, sau đó thực hiện các tác vụ:

- Gọi REST API tại `https://api.example.com` bằng `fetch`.
- Nhận thông báo theo thời gian thực qua `wss://events.example.com`.
- Theo dõi tiến độ bằng `EventSource` tại endpoint phát sự kiện.
- Gửi số liệu vận hành khi người dùng rời trang bằng `navigator.sendBeacon`.

Cho phép chạy script từ cùng origin chưa có nghĩa trình duyệt được phép kết nối tới mọi địa chỉ mà script yêu cầu. Trong **Content Security Policy (CSP)**, directive **`connect-src`** kiểm soát các đích kết nối thuộc nhóm này.

Ví dụ, trang HTML của `https://app.example.com` trả về:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Security-Policy: default-src 'none'; script-src 'self'; connect-src 'self' https://api.example.com wss://events.example.com; object-src 'none'; base-uri 'self'
~~~

Theo chính sách đó, script cùng origin được phép tải; các kết nối thuộc phạm vi `connect-src` chỉ được tạo tới nguồn được liệt kê. Một script muốn liên lạc với `https://unknown.example/collect` sẽ bị CSP chặn nếu không có chính sách khác phù hợp.

**Mục tiêu bài học:**

1. Hiểu `connect-src` điều khiển những API kết nối phía client nào và không điều khiển những gì.
2. Thiết kế allowlist chính xác cho REST API, Server-Sent Events, WebSocket và telemetry.
3. Phân biệt `connect-src` với CORS, CSRF, Origin validation của WebSocket và các directive khác.
4. Cấu hình chính sách trên Spring Security Servlet và Reactive/WebFlux.
5. Kiểm thử với browser, MockMvc/WebTestClient, Report-Only và chẩn đoán lỗi tại production.

## 2. connect-src nằm ở đâu trong mô hình CSP?

Một CSP header chứa nhiều directive; từng directive phụ trách một loại tài nguyên hoặc hành vi:

| Hành động trong trang | Directive CSP chủ yếu |
|---|---|
| Tải `<script src="...">` | `script-src-elem` → `script-src` → `default-src` theo fallback |
| Tải stylesheet | `style-src-elem` → `style-src` → `default-src` |
| Tải ảnh bằng `<img>` | `img-src` → `default-src` |
| Gọi `fetch`/`XMLHttpRequest` | **`connect-src`** → `default-src` |
| Mở `WebSocket` | **`connect-src`** → `default-src` |
| Đăng ký `EventSource`/SSE | **`connect-src`** → `default-src` |
| Gửi `navigator.sendBeacon` | **`connect-src`** → `default-src` |
| Gửi ping từ thuộc tính `ping` của liên kết | **`connect-src`** → `default-src` |
| Gửi một HTML form | `form-action`; **không** phải `connect-src` |
| Nhúng trang vào `<iframe>` | `frame-src`; không phải `connect-src` |
| Cho website khác nhúng trang hiện tại | `frame-ancestors`; không phải `connect-src` |
| Điều hướng trực tiếp bằng link/location | Không mặc nhiên chịu `connect-src` |

Các API kết nối mới (chẳng hạn một số trường hợp WebTransport) cũng có thể thuộc phạm vi fetch/connect của CSP tùy browser và đặc tả được hỗ trợ. Bảng trên tập trung vào các hành vi ứng dụng web thường dùng; hãy kiểm chứng trên phiên bản browser mục tiêu khi dùng API mới.

### Cơ chế fallback từ default-src

Khi **không khai báo** `connect-src`, trình duyệt dùng `default-src` làm nguồn dự phòng:

~~~http
Content-Security-Policy: default-src 'self'
~~~

Theo fallback này, các kết nối thuộc phạm vi `connect-src` thường chỉ được phép tới nguồn cùng origin. Nếu khai báo:

~~~http
Content-Security-Policy: default-src 'self'; connect-src https://api.example.com
~~~

thì danh sách dành cho kết nối là `https://api.example.com`: **`'self'` không tự động được cộng vào** `connect-src`. Một `fetch("/api/profile")` về chính origin của trang có thể bị từ chối.

Muốn cho cả hai:

~~~http
Content-Security-Policy: default-src 'self'; connect-src 'self' https://api.example.com
~~~

Một phương pháp thiết kế dễ kiểm soát là bắt đầu bằng `default-src 'none'`, rồi mở nguồn riêng cho từng nhóm mà ứng dụng thực sự cần. Chính sách này có thể làm hỏng frontend đang vận hành nếu chưa kiểm kê đầy đủ, nên nên thử qua Report-Only hoặc môi trường kiểm thử trước.

## 3. Source expression: scheme, host và port đều quan trọng

Giả sử HTML được phát từ `https://app.example.com` và policy là:

~~~http
Content-Security-Policy: connect-src 'self' https://api.example.com wss://events.example.com
~~~

Các trường hợp điển hình:

| Đích kết nối | Kết quả theo policy | Lý do |
|---|---|---|
| `https://app.example.com/api/me` | Được phép | Cùng origin |
| `https://api.example.com/v1/me` | Được phép | Origin API được liệt kê |
| `https://api.example.com:8443/v1/me` | Có thể bị chặn | Port không khớp source expression cho HTTPS mặc định |
| `https://admin.example.com/api` | Bị chặn | Subdomain khác không tự thuộc `'self'` |
| `https://unknown.example/collect` | Bị chặn | Host không được cho phép |
| `wss://events.example.com/stream` | Được phép | WebSocket secure origin được liệt kê |
| `wss://other.example.com/stream` | Bị chặn | WebSocket origin khác |
| `ws://events.example.com/stream` | Không được phép chỉ vì có `wss://...` | Scheme khác; trên HTTPS còn có thể bị mixed content chặn |

Khi browser nhận URL, việc khớp source expression tuân theo quy tắc CSP cho scheme, hostname, port và đường dẫn nếu policy khai báo path. Vì vậy **origin và port phải được xem xét trong cấu hình thực tế**, đặc biệt ở môi trường local với frontend port 3000/5173 và backend port 8080.

### 'self' với WebSocket: không nên dựa vào suy luận

Một điểm dễ mắc lỗi: `'self'` không được mọi browser diễn giải nhất quán là tự bao gồm đích `ws:`/`wss:` tương ứng. Để tránh xung đột tương thích, hãy **khai báo rõ nguồn WebSocket cần thiết**, ví dụ:

~~~http
Content-Security-Policy: connect-src 'self' wss://app.example.com wss://events.example.com
~~~

Nếu ứng dụng triển khai WebSocket ở cổng không mặc định, khai báo đúng host và port. Tránh dùng `connect-src *` để sửa nhanh lỗi WebSocket.

### Tại sao không nên dùng https: hoặc *

~~~http
Content-Security-Policy: connect-src https:
~~~

Chính sách này mở kết nối tới rất nhiều host HTTPS, không chỉ các API ứng dụng quản lý. Một script đã chạy trong trang có thể gửi dữ liệu tới nguồn ngoài rộng hơn đáng kể. `connect-src *` cũng là một allowlist quá rộng cho đa số dashboard, và còn có các chi tiết khác biệt về matching scheme.

Thay vào đó, xác định từng origin cần thiết: API, dịch vụ real-time, observability, payment SDK hoặc endpoint telemetry, rồi khai báo cụ thể. Tăng khả năng review và giảm kênh truyền dữ liệu không mong muốn.

## 4. fetch và XMLHttpRequest: CSP kiểm tra trước những bước bảo vệ khác

Trang web:

~~~javascript
// JavaScript chạy ở https://app.example.com
const response = await fetch("https://api.example.com/profile", {
  credentials: "include"
});

if (!response.ok) {
  throw new Error("API request failed");
}
const profile = await response.json();
~~~

Muốn request thuộc phạm vi này không bị CSP từ chối, tài liệu cần một policy phù hợp:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; connect-src 'self' https://api.example.com
~~~

Tuy nhiên, `connect-src` chỉ trả lời: **tài liệu có được tạo kết nối tới đích này theo CSP hay không?** Nó không bảo đảm API tồn tại, chấp nhận xác thực hoặc cho JavaScript đọc response cross-origin.

Một ví dụ tương tự bằng XHR:

~~~javascript
const xhr = new XMLHttpRequest();
xhr.open("GET", "https://api.example.com/profile");
xhr.withCredentials = true;
xhr.onload = () => console.log(xhr.status);
xhr.send();
~~~

XHR và `fetch` đều chịu kiểm tra `connect-src` của tài liệu. Việc bật `credentials: "include"` hay `withCredentials` còn đặt ra yêu cầu CORS/cookie riêng khi kết nối cross-origin; CSP **không** cho phép cookie, không thay đổi `SameSite` và không tự cấp quyền đọc dữ liệu.

### Các lỗi khác nhau khi cùng gọi một API

| Browser báo gì? | Khả năng nguyên nhân | Nơi cần sửa |
|---|---|---|
| `Refused to connect ... violates Content Security Policy ... connect-src` | Trang không cho đích kết nối | CSP trên **response HTML** |
| Không có `Access-Control-Allow-Origin` phù hợp | API không cấp quyền đọc cross-origin | Cấu hình **CORS ở API** |
| Preflight `OPTIONS` thất bại | API/proxy chưa xử lý đúng CORS preflight | CORS, authentication/filter chain API |
| `401 Unauthorized` | Thiếu/chưa đúng authentication | Security/authentication API |
| `403 Forbidden` với POST | Có thể do CSRF, authorization hoặc nghiệp vụ | Log, CSRF/authorization server |
| `404/500` | Route hoặc lỗi xử lý server | API/service backend |
| `Mixed Content` | Trang HTTPS cố dùng nguồn không an toàn | URL `https:`/`wss:` và cấu hình HTTPS |

Có thể xuất hiện nhiều lớp kiểm tra cùng lúc. Khi một yêu cầu bị CSP chặn sớm, browser có thể không gửi HTTP request tới API, nên không có log API. Vì vậy cần xem DevTools Console **và** Network trước khi khẳng định lỗi nằm ở Spring backend.

## 5. WebSocket: connect-src không thay thế kiểm tra Origin của server

Ứng dụng thông báo thời gian thực:

~~~javascript
const socket = new WebSocket("wss://events.example.com/live");

socket.addEventListener("open", () => {
  console.log("Real-time channel connected");
});

socket.addEventListener("message", event => {
  console.log("Incoming event:", event.data);
});

socket.addEventListener("error", () => {
  console.error("WebSocket connection failed");
});
~~~

Nếu CSP không cho `wss://events.example.com` trong `connect-src`, browser có thể từ chối tạo kết nối. Policy ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; connect-src 'self' wss://events.example.com
~~~

### Hai chiều bảo vệ độc lập

| Cơ chế | Ai quyết định? | Phòng vệ trước điều gì? |
|---|---|---|
| CSP `connect-src` | Trang nguồn và browser | Script của trang đó không được kết nối tùy ý tới WebSocket origin ngoài allowlist |
| Kiểm tra `Origin` khi WebSocket handshake | WebSocket server | Từ chối kết nối phát sinh từ website không được chấp thuận |
| Authentication/authorization của WebSocket | Server | Xác nhận danh tính và quyền dùng kênh/room/message |
| HTTPS/WSS và cookie/session phù hợp | Browser và server | Bảo vệ đường truyền, quản lý phiên và những rủi ro liên quan |

CSP trong **trang của ứng dụng** không kiểm soát CSP của một website độc hại khác. Website đó có thể tự cho phép kết nối đến WebSocket server của bạn. Do đó **WebSocket server vẫn phải kiểm tra Origin** và xác thực/ủy quyền phù hợp; không được coi `connect-src` là biện pháp chống cross-site WebSocket hijacking thay thế kiểm tra phía server.

Một lưu ý quan trọng: WebSocket handshake không dùng cơ chế CORS preflight theo cách `fetch` cross-origin thường dùng. Việc cấu hình CORS cho REST API **không có nghĩa** WebSocket endpoint đã được bảo vệ. Hãy cấu hình danh sách origin được phép cho WebSocket handshake và kiểm tra từng thao tác trên kênh.

### Lỗi triển khai thường gặp

- Local chạy `ws://localhost:8080` nhưng production ở HTTPS cần `wss://...`.
- Frontend chạy ở `https://app.example.com`, socket ở `wss://events.example.com` nhưng policy chỉ có `connect-src 'self'`.
- Reverse proxy chuyển WebSocket upgrade sai hoặc đóng kết nối, không phải lỗi CSP.
- Handshake thành công nhưng server từ chối kết nối do Origin/authentication; cần xem log WebSocket server.
- Kết nối mở được nhưng message bị từ chối do authorization; `connect-src` không bảo vệ permission bên trong channel.

## 6. EventSource, sendBeacon và ping: những kết nối dễ bỏ sót

### 6.1. EventSource / Server-Sent Events

SSE cho phép browser nhận sự kiện theo một HTTP connection kéo dài:

~~~javascript
const updates = new EventSource("https://api.example.com/events", {
  withCredentials: true
});

updates.addEventListener("message", event => {
  console.log("SSE payload:", event.data);
});

updates.addEventListener("error", () => {
  console.warn("SSE disconnected or blocked");
});
~~~

Kết nối này chịu `connect-src`, ví dụ `connect-src 'self' https://api.example.com`. Với SSE cross-origin, còn cần xem **CORS**, credentials và cookie tương ứng. Browser có thể tự kết nối lại khi SSE mất đường truyền; mỗi lần tạo kết nối vẫn phụ thuộc các giới hạn của tài liệu.

Ở backend WebFlux, SSE có thể được triển khai bằng `Flux<ServerSentEvent<T>>` hoặc response `text/event-stream`. Nhưng `connect-src` nằm trên **HTML frontend response**, không phải chỉ trên SSE response được trả từ API.

### 6.2. navigator.sendBeacon

Browser có API gửi dữ liệu nhỏ theo kiểu *fire-and-forget*, thường dùng cho telemetry:

~~~javascript
const payload = JSON.stringify({
  event: "dashboard_closed",
  version: "1.0"
});

navigator.sendBeacon(
  "https://telemetry.example.com/collect",
  new Blob([payload], { type: "application/json" })
);
~~~

Đích của `sendBeacon` chịu `connect-src`. Nếu chỉ có `connect-src 'self' https://api.example.com`, endpoint `https://telemetry.example.com` không được cấp phép. Cần khai báo riêng nếu thực sự cần:

~~~http
Content-Security-Policy: connect-src 'self' https://api.example.com https://telemetry.example.com
~~~

Ngoài CSP, việc gửi dữ liệu cross-origin còn chịu hành vi về request mode, CORS và content type của Beacon API; payload `application/json` có thể có những yêu cầu khác payload đơn giản. Không suy rằng mở `connect-src` bảo đảm browser sẽ gửi thành công hoặc server sẽ nhận dữ liệu. Một số lời gọi `sendBeacon` trả `false` do không thể xếp hàng dữ liệu, chứ không nhất thiết do CSP; cần kiểm tra chính xác Console/Network.

**Quyền riêng tư:** telemetry có thể chứa dữ liệu người dùng hoặc URL nhạy cảm. Việc một origin được CSP cho phép không đồng nghĩa được phép gửi bất kỳ dữ liệu nào đến đó; cần kiểm soát payload, retention và quyền riêng tư trong thiết kế ứng dụng.

### 6.3. Ping khi bấm liên kết

HTML có thuộc tính `ping` trên liên kết để thông báo tới endpoint theo dõi:

~~~html
<a href="/help" ping="https://telemetry.example.com/click">Trợ giúp</a>
~~~

Đích ping thuộc nhóm kết nối chịu `connect-src`. Tuy nhiên, việc bấm link để điều hướng tới `/help` là một hành vi **khác**; `connect-src` không thay thế chính sách điều hướng hoặc `form-action`. Mức hỗ trợ thuộc tính ping và cài đặt riêng tư có thể khác nhau giữa trình duyệt.

### 6.4. Không phải mọi kết nối mạng đều thuộc connect-src

Ví dụ:

~~~html
<img src="https://images.example.com/avatar.png" alt="Avatar">
<form action="https://payments.example.com/checkout" method="post">
  <button type="submit">Thanh toán</button>
</form>
<iframe src="https://docs.example.com/guide"></iframe>
~~~

Ảnh chịu `img-src`, form chịu `form-action`, iframe chịu `frame-src`. Nếu chỉ siết `connect-src`, bạn chưa kiểm soát được những con đường tải hoặc truyền dữ liệu này. Đặc biệt, một dữ liệu nhạy cảm bị ghép vào URL ảnh hoặc đích form có thể bị rò qua nhóm tài nguyên khác nếu policy tương ứng quá rộng.

## 7. Tạo chính sách cho ứng dụng có REST API và real-time

Giả sử kiến trúc:

| Thành phần | Origin / protocol |
|---|---|
| HTML, JavaScript, CSS, ảnh, font | `https://app.example.com` |
| REST API và SSE | `https://api.example.com` |
| WebSocket thông báo | `wss://events.example.com` |
| Telemetry được phê duyệt | `https://telemetry.example.com` |
| Đích gửi HTML form | Cùng origin với trang |
| Website được nhúng dashboard | Không trang nào |

Một CSP khởi đầu:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self' https://api.example.com wss://events.example.com https://telemetry.example.com; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
~~~

Chính sách trên có các giả định:

1. JavaScript và CSS được tải từ tệp cùng origin, không có inline script/style cần nonce hoặc hash.
2. API REST và SSE dùng HTTPS, WebSocket dùng WSS.
3. Không cần object/embed, iframe ngoài hoặc form gửi sang bên thứ ba.
4. Telemetry chỉ gửi tới một origin đã được phê duyệt.
5. Ứng dụng thực sự phát HTML tại `app.example.com`; nếu frontend ở CDN khác, CSP phải được cấu hình trên response HTML tại đó.

### Tạo allowlist từ nhu cầu chứ không từ lỗi Console

Khi frontend báo một kết nối bị chặn, quy trình đúng không phải sao chép bất kỳ host xuất hiện trong thông báo vào CSP:

- Xác minh **tính năng nào** yêu cầu kết nối đó.
- Xác minh **origin đích** là một dịch vụ được phép và có kiểm soát.
- Xác minh **môi trường triển khai** (dev, staging, production), port và protocol có đúng không.
- Cân nhắc liệu request có chứa thông tin nhạy cảm hoặc cookie/authorization header không.
- Chỉ mở chính xác nguồn cần thiết; tạo test để tránh vô tình xóa nguồn quan trọng trong lần cập nhật tiếp theo.

Khi có SDK bên thứ ba, nên kiểm kê toàn bộ các endpoint nó có thể gọi thay vì chỉ quan sát một request lúc trang mới tải. Một tính năng phụ, nhánh lỗi hoặc thao tác thanh toán có thể dùng thêm endpoint khác.

## 8. Spring Security Servlet: cấu hình connect-src

Trong ứng dụng Spring MVC/Servlet, có thể cấu hình CSP qua `HttpSecurity.headers(...).contentSecurityPolicy(...)`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    private static final String CSP_POLICY =
            "default-src 'none'; " +
            "script-src 'self'; " +
            "style-src 'self'; " +
            "img-src 'self'; " +
            "font-src 'self'; " +
            "connect-src 'self' https://api.example.com " +
                "wss://events.example.com https://telemetry.example.com; " +
            "object-src 'none'; " +
            "base-uri 'self'; " +
            "form-action 'self'; " +
            "frame-ancestors 'none'";

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(CSP_POLICY)
            )
        );
        return http.build();
    }
}
~~~

Khi response của trang HTML đi qua security chain tương ứng, Spring Security ghi header `Content-Security-Policy` với chuỗi do ứng dụng cung cấp. Browser mới quyết định việc `fetch`, WebSocket hoặc SSE có bị từ chối theo CSP hay không. Spring Security không tự dò các URL mà frontend gọi để sinh `connect-src`.

### Cấu hình CSP và CORS thuộc các bước độc lập

Một ứng dụng có thể đồng thời:

~~~java
http.cors(cors -> {});
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(CSP_POLICY)
    )
);
~~~

Trong ví dụ này, `http.cors(...)` yêu cầu Spring Security tích hợp cấu hình CORS của ứng dụng theo cơ chế tương ứng; bản thân lời gọi này **không tạo** một allowlist CORS đầy đủ cho API ở origin khác. Khi frontend tại `app.example.com` gọi API ở `api.example.com`, server API phải cho phép origin frontend theo CORS nếu request thuộc phạm vi CORS, còn trang HTML của frontend phải cho phép API trong `connect-src`.

Chú ý **nhiều SecurityFilterChain**: chỉ cấu hình CSP trên chain dành cho `/api/**` không bảo đảm response HTML của `/dashboard` được bảo vệ nếu trang đi qua chain khác. Phải kiểm tra route và response thực nhận ở browser.

## 9. Spring Security Reactive/WebFlux: cùng policy, API cấu hình khác

Với WebFlux, dùng `ServerHttpSecurity` và `SecurityWebFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        String policy =
            "default-src 'none'; " +
            "script-src 'self'; " +
            "style-src 'self'; " +
            "img-src 'self'; " +
            "font-src 'self'; " +
            "connect-src 'self' https://api.example.com " +
                "wss://events.example.com https://telemetry.example.com; " +
            "object-src 'none'; " +
            "base-uri 'self'; " +
            "form-action 'self'; " +
            "frame-ancestors 'none'";

        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(policy)
            )
        );
        return http.build();
    }
}
~~~

Ý nghĩa của `connect-src` phía browser **giống nhau** dù trang được phục vụ qua Servlet hay WebFlux. Khác biệt nằm ở API cấu hình HTTP security chain ở server.

### Nếu WebFlux chỉ trả REST/SSE API

Giả sử:

- `https://app.example.com` trả HTML/JS từ CDN.
- `https://api.example.com` là Spring WebFlux phục vụ REST và SSE.

Đặt CSP trên response JSON hoặc `text/event-stream` của WebFlux **không tự áp dụng chính sách ấy cho trang HTML** ở `app.example.com`. CSP của tài liệu phải xuất trên **response HTML** mà browser đang render. Điều này đặc biệt quan trọng nếu code Spring Security nằm trong repository API còn frontend deploy qua một hệ thống độc lập.

## 10. Report-Only và quy trình triển khai connect-src

Nếu đang chuyển một ứng dụng sang CSP chặt, mở đầu với `Content-Security-Policy-Report-Only` giúp quan sát những kết nối hiện có mà chưa chặn chúng chỉ vì policy thử nghiệm:

~~~http
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; connect-src 'self' https://api.example.com wss://events.example.com; object-src 'none'; report-uri /_csp/report
~~~

Nếu frontend còn gọi `https://old-api.example.net`, browser có thể báo vi phạm `connect-src` trong Console; tài nguyên vẫn có thể được gửi/nhận nếu không bị một CSP thực thi hoặc cơ chế khác chặn.

Quy trình triển khai gợi ý:

1. **Kiểm kê:** liệt kê các endpoint cho fetch/XHR, SSE, WebSocket, sendBeacon, ping và SDK bên thứ ba.
2. **Chạy Report-Only:** thu nhận vi phạm của candidate policy trên những trang HTML và trình duyệt mục tiêu.
3. **Phân loại:** gắn mỗi vi phạm với tính năng, môi trường, phiên bản frontend; loại bỏ endpoint cũ hoặc không được phê duyệt.
4. **Đồng bộ backend:** kiểm tra CORS, xác thực, WebSocket Origin và TLS/WSS riêng.
5. **Bật enforcement có kiểm soát:** thay bằng `Content-Security-Policy` trên response HTML; thử luồng chính và nhánh ít gặp.
6. **Giám sát sau triển khai:** lưu ý request bị CSP chặn có thể không xuất hiện trong access log API; cần dữ liệu browser/report.

Muốn nhận report tự động, cần cấu hình endpoint và cơ chế `report-uri` hoặc Reporting API `report-to` theo browser được hỗ trợ; chỉ thêm header Report-Only không tự tạo server collector. CSP report có thể chứa URL hoặc metadata nhạy cảm, vì vậy endpoint phải hạn chế dữ liệu, validate payload và quản lý lưu giữ.

**Không dùng mọi violation để mở quyền ngay.** Một extension, SDK bị đổi endpoint hoặc một script bị chèn cũng có thể tạo cảnh báo. Trước khi thêm nguồn, hãy xác minh nó thuộc nhu cầu sản phẩm hợp lệ.

## 11. Kiểm thử phía server: xác minh header CSP

### 11.1. Servlet với MockMvc

Giả sử ứng dụng có route HTML `/dashboard` và test dùng Spring Security filters:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

mockMvc.perform(get("/dashboard"))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("connect-src 'self' https://api.example.com")
    ))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("wss://events.example.com")
    ));
~~~

Test chứng minh server trả một policy có source expression đã cấu hình. Nó **không** chứng minh browser đã tải API thành công hoặc WebSocket server đã chấp nhận handshake.

### 11.2. Reactive với WebTestClient

~~~java
// Trong lớp test WebFlux đã cấu hình WebTestClient và route /dashboard.
webTestClient.get()
    .uri("/dashboard")
    .exchange()
    .expectHeader()
    .valueMatches(
        "Content-Security-Policy",
        ".*connect-src 'self' https://api.example.com.*"
    );
~~~

Nếu request `/dashboard` bị redirect đến login, nhận 401/403 hoặc HTML cuối cùng do một server khác trả, cần kiểm tra đúng tài liệu mà browser render. Chỉ nhìn response trung gian có thể dẫn đến kết luận sai về phạm vi CSP.

### 11.3. Nếu kiểm thử Report-Only

Khi cấu hình candidate policy với header `Content-Security-Policy-Report-Only`, test phải xác nhận **đúng tên header** thay vì `Content-Security-Policy`. Một policy Report-Only không tạo hiệu lực chặn chỉ vì bản thân nó; không được dùng một unit test header để kết luận frontend đã an toàn khỏi exfiltration.

## 12. Kiểm thử browser bằng một trang demo

Thiết lập trang có tệp `/js/dashboard.js` cùng origin và CSP:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; connect-src 'self' https://api.example.com wss://events.example.com; object-src 'none'; base-uri 'self'
~~~

Thử từng trường hợp sau trong **môi trường do bạn kiểm soát**:

| Hành vi | Kết quả dự kiến về CSP | Cần xác minh thêm |
|---|---|---|
| `fetch("/api/me")` | Được phép bởi `'self'` | Endpoint, auth, HTTP status |
| `fetch("https://api.example.com/me")` | Được phép bởi source API | CORS, token/cookie, status |
| `fetch("https://unknown.example/collect")` | Bị chặn bởi `connect-src` | Browser Console/Network |
| `new WebSocket("wss://events.example.com/live")` | Được phép theo CSP | Origin/auth/upgrade của WebSocket server |
| `new WebSocket("wss://other.example/live")` | Bị chặn | Policy có đúng endpoint được phê duyệt không |
| `new EventSource("https://api.example.com/events")` | Được phép theo CSP | CORS/SSE endpoint |
| `navigator.sendBeacon("https://telemetry.example.com/collect", ...)` | Bị chặn nếu telemetry chưa được cho phép | Cơ chế Beacon/CORS khi mở nguồn |
| `<img src="https://unknown.example/i.png">` | Không do `connect-src` quyết định; ở policy này có thể bị chặn bởi `default-src 'none'` qua `img-src` | Kiểm tra `img-src`/fallback |
| `<form action="https://unknown.example">` | Không do `connect-src` quyết định | `form-action`; policy mẫu chưa khai báo |

**Quy trình xác minh:**

1. Trong DevTools → Network, mở request **HTML document** và đọc toàn bộ CSP response header.
2. Quan sát Console/Issues khi thử `fetch` hoặc WebSocket đến nguồn ngoài danh sách; tìm thông báo chứa `connect-src`.
3. Đối chiếu Network để xem request có rời browser không. Một lỗi CSP có thể xảy ra trước khi API nhận request.
4. Với API được cho phép, kiểm tra tiếp CORS, preflight, credentials và status; với WebSocket, kiểm tra handshake/Origin và authorization phía server.
5. Thử `sendBeacon`/SSE trong môi trường có endpoint thật do bạn kiểm soát. Browser có thể xử lý API và báo lỗi khác nhau; ghi rõ kết quả của từng browser.
6. Lặp lại trên staging/production khi hostname, port, HTTPS/WSS hoặc proxy khác local.

**Chú ý:** mã nhập thủ công trong DevTools Console không luôn được browser xử lý hoàn toàn giống mã thực sự được tải và chạy trong trang. Để kiểm chứng CSP theo luồng ứng dụng, đặt test case trong file JavaScript cùng origin của trang demo và thử qua UI/Network.

## 13. Chẩn đoán lỗi trong ứng dụng thực tế

| Triệu chứng | Kiểm tra nguyên nhân | Hướng xử lý |
|---|---|---|
| REST API không có log request, browser báo CSP | `connect-src` thiếu host/port/scheme | Mở đúng source expression trên response HTML |
| API xuất CORS header nhưng fetch vẫn bị chặn | CSP của trang ngăn kết nối trước hoặc độc lập với CORS | Kiểm tra Console và `connect-src` |
| CSP cho API nhưng browser báo CORS | API không cấp quyền origin/method/header/credentials phù hợp | Sửa cấu hình CORS ở **API**, không nới CSP |
| WebSocket lỗi khi chuyển sang production HTTPS | Dùng `ws:` thay `wss:` hoặc policy/proxy không phù hợp | Dùng WSS, kiểm tra CSP và reverse proxy |
| WebSocket bị từ chối dù connect-src có WSS host | Server kiểm tra Origin hoặc authentication; upgrade thất bại | Kiểm tra handshake và log WebSocket server |
| Local chạy, staging không chạy | Port và origin khác; CSP hard-code theo môi trường | Quản lý allowlist theo môi trường được review |
| SSE không kết nối | `connect-src`, CORS, endpoint hoặc proxy timeout | Phân lớp chẩn đoán browser/network/server |
| Telemetry dừng sau khi bật CSP | `sendBeacon` hoặc ping gửi đến host chưa cho phép | Kiểm tra endpoint thật; mở đúng origin nếu đã phê duyệt |
| Mở `connect-src` xong vẫn mất ảnh | Ảnh chịu `img-src`, không phải `connect-src` | Sửa directive ảnh |
| Dùng `'self'` nhưng WSS vẫn bị chặn | Khác biệt matching WebSocket của browser | Khai báo rõ `wss://host[:port]` |
| Có CSP ở API nhưng trang không được bảo vệ | Frontend HTML do CDN/service khác cung cấp | Đặt CSP trên **HTML response** |
| CSP trong code đúng nhưng browser vẫn chặn | Nhiều policy thực thi từ Spring/proxy/CDN | Kiểm tra toàn bộ header và mọi policy |
| Report-Only có violation nhưng request vẫn chạy | Report-Only không chặn | Thử enforced CSP có kiểm soát |
| API báo 403 sau POST | Có thể do CSRF/authz hoặc nghiệp vụ, không phải CSP | Đọc response và log Spring Security |

### Đặc biệt: nhiều Content-Security-Policy header

Một response có thể chứa CSP do Spring Security thêm và CSP do reverse proxy/CDN thêm. Trình duyệt áp dụng **tất cả chính sách thực thi**. Ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; connect-src 'self' https://api.example.com
Content-Security-Policy: default-src 'self'; connect-src 'self'
~~~

Trong trường hợp này, API `https://api.example.com` vẫn có thể bị chặn bởi policy thứ hai, mặc dù policy thứ nhất cho phép. Không được giả định header sau ghi đè header trước hoặc lấy một policy duy nhất trong DevTools để phân tích.

### CSP không ngăn được mọi đường rò rỉ dữ liệu

Giới hạn `connect-src` có ích để giảm khả năng script gửi dữ liệu tới một HTTP/WebSocket endpoint ngoài danh sách, nhưng **không đủ** để kết luận dữ liệu sẽ không rò rỉ:

- `img-src` quá rộng có thể cho phép đưa dữ liệu vào URL ảnh.
- `form-action` không được thiết lập có thể để ngỏ đích submit form.
- Script đã được tin cậy có thể dùng endpoint API hợp lệ theo cách không mong muốn.
- Browser extension, client không phải browser và các luồng ngoài phạm vi CSP có mô hình kiểm soát khác.

Vì vậy một chính sách thực tế cần phối hợp `script-src`, `img-src`, `form-action`, `base-uri`, `object-src`, các phòng vệ server và xử lý dữ liệu an toàn. CSP **không thay thế** validation, authorization, CSRF protection, cookie/session bảo mật hoặc CORS.

## 14. Bài thực hành tổng hợp

**Bối cảnh:** Dashboard ở `https://app.example.com` tải JS cùng origin, gọi REST API `https://api.example.com`, mở WebSocket `wss://events.example.com` và có telemetry tại `https://telemetry.example.com`.

1. Viết CSP với `default-src 'none'`, `script-src 'self'` và `connect-src` đúng ba origin cần dùng (bao gồm `'self'` nếu frontend gọi API cùng origin).
2. Thiết lập policy trong Spring Security Servlet, dùng MockMvc kiểm tra CSP header ở **route HTML**.
3. Thử `fetch` tới API hợp lệ và một host không được phép; phân biệt thông báo CSP với lỗi CORS.
4. Thiết lập endpoint WebSocket trong môi trường test; kiểm tra `wss://` trong `connect-src` và việc server xác thực Origin/authorization riêng.
5. Dùng `EventSource` nhận SSE; ghi lại hành vi khi `connect-src` thiếu nguồn API.
6. Dùng `navigator.sendBeacon` tới telemetry; trước tiên quan sát vi phạm khi nguồn chưa được khai báo, sau đó mở nguồn đã phê duyệt.
7. Xóa `connect-src` khỏi policy để thử fallback về `default-src 'none'`; sau đó thêm lại `connect-src 'self' https://api.example.com ...`.
8. Thử một HTML form và một ảnh từ host ngoài để giải thích vì sao `connect-src` không kiểm soát hai hành vi này.
9. Lặp lại cấu hình trên WebFlux bằng `ServerHttpSecurity` và kiểm tra header với WebTestClient.
10. Bật Report-Only để quan sát candidate policy, sau đó thực thi ở môi trường test và ghi các kết quả khác biệt.

**Câu hỏi tự đánh giá:**

1. Khi `connect-src` không xuất hiện, directive nào có thể được dùng làm fallback?
2. `default-src 'self'; connect-src https://api.example.com` có tự cho phép `fetch("/api/me")` không?
3. Vì sao `connect-src 'self'` chưa đủ để bảo đảm WebSocket WSS cùng host được phép trên mọi browser?
4. Nếu CSP đã cho phép API, tại sao browser vẫn có thể báo lỗi CORS?
5. Vì sao WebSocket server không thể chỉ dựa vào CSP trên frontend để chống cross-site WebSocket hijacking?
6. Những API nào ngoài `fetch` và XHR cũng nên được kiểm kê khi thiết kế `connect-src`?
7. Vì sao `connect-src` không thay thế `form-action` và `img-src`?
8. Một request bị CSP chặn nhưng không xuất hiện trong API access log có bất thường không?
9. Khi frontend HTML do CDN phục vụ còn Spring chỉ trả JSON/SSE, CSP cần được xuất ở đâu?
10. Nếu một response có hai CSP thực thi, một policy cho phép API còn policy kia không cho, điều gì xảy ra?

## 15. Ghi nhớ

**`connect-src` giới hạn đích kết nối do tài liệu khởi tạo**, gồm `fetch`/XHR, WebSocket, EventSource/SSE, `sendBeacon` và một số cơ chế ping. Khi directive vắng mặt, `default-src` có thể đóng vai trò fallback; khi `connect-src` đã được khai báo, nguồn trong `default-src` **không tự được cộng thêm**. Hãy liệt kê chính xác scheme, hostname và port cần thiết, đặc biệt với `wss://`.

Trong Spring Security Servlet và Reactive/WebFlux, ứng dụng cấu hình CSP header trên **response HTML**, còn browser thực thi giới hạn. CSP cho phép kết nối không đồng nghĩa API cho phép CORS, người dùng đã được xác thực hoặc WebSocket server chấp nhận Origin. Kiểm thử phải đi từ CSP trên HTML tới Network, CORS, authentication/CSRF, handshake và proxy. `connect-src` là một lớp phòng vệ quan trọng, nhưng cần phối hợp các directive CSP khác và những cơ chế HTTP/session của mô-đun `SPRING_SECURITY_HTTP_PROTECTION`.
