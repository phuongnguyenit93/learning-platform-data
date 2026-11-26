# Khác biệt thực thi same-origin đối với WebSocket

## Mở đầu: Vì sao Fetch bị CORS chặn nhưng WebSocket vẫn có thể kết nối?

Một frontend hoạt động ở `https://app.example.com` và một API ở `https://api.example.com`. Khi JavaScript gọi `fetch("https://api.example.com/api/me")`, trình duyệt áp dụng **Same-Origin Policy (SOP)** và cơ chế **Cross-Origin Resource Sharing (CORS)** để quyết định JavaScript có được đọc phản hồi khác origin hay không.

Nhưng khi cùng JavaScript thực hiện:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws");
~~~

trình duyệt **không thực hiện quy trình CORS của Fetch** với preflight `OPTIONS` và kiểm tra `Access-Control-Allow-Origin` trên phản hồi. Nó có thể thử bắt tay WebSocket tới máy chủ khác origin. Nếu server chấp nhận handshake, script có thể trao đổi và đọc các message nhận qua kết nối đó.

Đây không phải lỗi của trình duyệt. Giao thức WebSocket có cơ chế đưa thông tin **`Origin`** vào handshake để **server quyết định** có chấp nhận các trang web nguồn đó hay không. Điều này tạo ra một ranh giới trách nhiệm khác biệt:

- **HTTP Fetch CORS:** server phát response CORS headers; browser kiểm soát việc chia sẻ response cho JavaScript và khi nào được gửi actual request sau preflight.
- **Native WebSocket:** browser có thể thử kết nối cross-origin; server phải chủ động kiểm tra `Origin`, authentication và các yêu cầu bảo vệ handshake. Sau khi kết nối mở, message-layer security còn phải kiểm tra quyền truy cập dữ liệu.
- **Client ngoài browser:** có thể tạo WebSocket connection và tự đặt `Origin`; không bị SOP/CORS của browser ràng buộc. Origin không thể thay thế authentication.

Bài thuộc chương **WebSocket và STOMP** của `SPRING_SECURITY_HTTP_PROTECTION`. Trong bối cảnh Spring Security bảo vệ HTTP, trình duyệt, session, CSRF, CORS, security headers, CSP, HSTS và HTTP firewall, việc hiểu chính xác ranh giới này giúp tránh **Cross-Site WebSocket Hijacking (CSWSH)** và nhầm lẫn giữa lỗi CORS HTTP, lỗi WebSocket handshake và lỗi STOMP authorization.

### Mục tiêu học tập

Kết thúc bài, người học có thể:

1. Phân biệt **same-origin**, **same-site**, chính sách CORS của Fetch và Origin validation tại WebSocket handshake.
2. Đọc được HTTP handshake `GET Upgrade` và hiểu vai trò của `Origin`, `Sec-WebSocket-Key`, HTTP 101.
3. Giải thích vì sao native WebSocket không dùng preflight OPTIONS hay ACAO như Fetch.
4. Nhận diện CSWSH khi browser tự gửi cookie phiên vào handshake của một trang không tin cậy.
5. Cấu hình `setAllowedOrigins(...)` / `setAllowedOriginPatterns(...)` cho Spring WebSocket/STOMP một cách thận trọng.
6. Bảo vệ HTTP handshake **và** STOMP CONNECT/SEND/SUBSCRIBE bằng Spring Security.
7. Hiểu hạn chế browser WebSocket API với HTTP headers, cookie và bearer token.
8. Đối chiếu SockJS fallback và WebFlux native WebSocket.
9. Kiểm thử browser ở hai origin, client ngoài browser, proxy, CSP và quyền đối tượng sau khi kết nối thành công.

Tất cả hostname `example.com`/`example.org` trong bài là ví dụ, không phải địa chỉ dịch vụ đang tồn tại.

## 1. Cùng origin không đồng nghĩa cùng site

### 1.1. Origin được xác định bằng scheme, host, port

Với các URL HTTP(S) thông thường, origin là bộ ba **scheme + host + port**. Path và query không phải thành phần origin.

| Hai địa chỉ | Same-origin? | Lý do |
| --- | --- | --- |
| `https://app.example.com/a` và `https://app.example.com/b` | Có | Cùng scheme, host, port mặc định |
| `https://app.example.com` và `https://api.example.com` | Không | Khác host |
| `https://app.example.com` và `http://app.example.com` | Không | Khác scheme |
| `https://app.example.com` và `https://app.example.com:8443` | Không | Khác port |
| `https://app.example.com` và `https://app.example.com.evil.example.org` | Không | Khác hostname hoàn toàn |
| `http://localhost:3000` và `http://localhost:8080` | Không | Khác port |

Với native WebSocket, URL thường dùng `ws://` hoặc `wss://`. Khi script trên `https://app.example.com` mở `wss://api.example.com/ws`, header `Origin` của browser phản ánh **origin trang đang chạy JavaScript** — thường là `https://app.example.com` — chứ **không** phải chuỗi `wss://api.example.com`.

Đây là lý do một allowlist cho handshake thường chứa **HTTP(S) frontend origins**, ví dụ `https://app.example.com`, dù endpoint sử dụng `wss://`.

### 1.2. Same-site dựa trên site, không dựa trên origin

Cookie `SameSite` dùng khái niệm **site**, thường gắn với scheme và registrable domain. Ví dụ `https://app.example.com` và `https://api.example.com`:

- Khác origin nên Fetch thông thường chịu SOP/CORS.
- Thường **same-site**, vì cùng scheme HTTPS và cùng registrable domain `example.com`.

Điểm quan trọng khi thiết kế session:

- Một trang cùng site nhưng khác origin **không tự động đáng tin cậy**.
- User-controlled subdomain hoặc subdomain bị chiếm có thể vẫn same-site.
- Cookie `SameSite=Lax` có thể được browser gửi trong request same-site phù hợp; nó không chứng minh trang khởi tạo là frontend chính thức.
- `HttpOnly` ngăn script đọc cookie trực tiếp, **không** cấm browser tự đính cookie vào request khi các điều kiện gửi cookie được đáp ứng.

Do vậy, **cookie SameSite không thay thế Origin allowlist hoặc bảo vệ CSRF/message security của WebSocket**.

### 1.3. So sánh hai ranh giới

~~~text
Cùng origin?    Được quyết định bằng scheme + host + port.
Cùng site?      Liên quan đến scheme + registrable domain.
CORS Fetch?     Browser kiểm tra response headers và preflight khi cần.
WebSocket?      Browser có thể thử kết nối khác origin; server kiểm tra Origin.
Authentication? Kiểm tra client/user là ai, không dựa trên Origin.
Authorization?  Kiểm tra quyền thao tác và dữ liệu, kể cả sau HTTP 101.
~~~

Một thiết kế an toàn phải xem mỗi ranh giới như một câu hỏi khác nhau.

## 2. Fetch CORS thực thi ở browser như thế nào?

Giả sử JavaScript ở `https://evil.example.org` muốn đọc dữ liệu cá nhân tại API:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});

const body = await response.json();
~~~

Nếu API **không** cấp CORS quyền đọc cho `https://evil.example.org`, trình duyệt từ chối chia sẻ response cho JavaScript. Với request đơn giản, HTTP request vẫn có thể đã tới server. Với request cần preflight, browser có thể dừng trước actual request nếu OPTIONS thất bại.

Một actual response hợp lệ khi có credentials cho frontend được tin cậy có thể gồm:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"username":"alice"}
~~~

Browser ở `https://evil.example.org` sẽ không được đọc body dựa vào ACAO trên, vì origin của nó không khớp.

### 2.1. Preflight là tính năng của CORS cho HTTP requests, không phải kiểm tra login

Ví dụ actual Fetch `PUT` JSON:

~~~javascript
fetch("https://api.example.com/api/profile", {
  method: "PUT",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ displayName: "Lan" })
});
~~~

Browser thường hỏi quyền trước:

~~~http
OPTIONS /api/profile HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Chính sách CORS cho HTTP API kiểm tra Origin/method/headers rồi trả `Access-Control-Allow-*` phù hợp. Preflight thường không mang cookie hoặc token của actual request. Sau đó actual PUT vẫn phải chịu authentication, CSRF và authorization.

**Đừng chuyển quy trình OPTIONS này sang WebSocket.** Một browser `new WebSocket(...)` không phát CORS preflight tương đương và cũng không cần ACAO để quyết định cho script đọc WebSocket messages khi connection đã được chấp nhận.

### 2.2. CORS không phải cơ chế xác thực

Một HTTP client ngoài browser có thể gửi:

~~~bash
curl -i "https://api.example.com/api/me" \
  -H "Origin: https://app.example.com"
~~~

Client này không tự áp dụng SOP/CORS, và có thể tự khai Origin. Spring CORS processor vẫn có thể kiểm tra Origin và từ chối request tại server khi có policy, nhưng không được coi `Origin` là bằng chứng đăng nhập hay quyền xem dữ liệu.

Điều tương tự còn quan trọng hơn ở WebSocket: **Origin validation là một lớp giảm nguy cơ từ website độc hại trong browser, không phải cơ chế nhận diện client**.

## 3. Native WebSocket handshake mang những thông tin gì?

### 3.1. Bắt tay qua HTTP/1.1

Khi browser chạy:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws");
~~~

một handshake HTTP/1.1 điển hình có dạng:

~~~http
GET /ws HTTP/1.1
Host: api.example.com
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Origin: https://app.example.com
Cookie: SESSION=<session-id-if-browser-allows>
~~~

Nếu server chấp nhận, response là:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <value-derived-from-request-key>
~~~

Đây là mẫu phổ biến với HTTP/1.1. Một số triển khai WebSocket có thể dùng các cơ chế khác như extended CONNECT trên HTTP/2, do đó không xem chính xác các dòng Upgrade/101 là duy nhất trong mọi hạ tầng.

Các trường cần phân biệt:

| Trường | Ý nghĩa | Có thay authentication không? |
| --- | --- | --- |
| `Host` | Host máy chủ đích của handshake | Không |
| `Origin` | Origin trang khởi tạo script theo browser | Không |
| `Sec-WebSocket-Key` | Giá trị cho cơ chế bắt tay WebSocket, giúp xác minh server hiểu handshake | Không; **không phải** token đăng nhập |
| `Sec-WebSocket-Version` | Phiên bản giao thức WebSocket | Không |
| `Cookie` | Browser gửi theo chính sách cookie khi phù hợp | Có thể cung cấp dữ liệu xác thực, nhưng phải được server kiểm tra |
| `Sec-WebSocket-Protocol` | Danh sách subprotocols muốn thương lượng | Không tự là token/role đáng tin cậy |

**HTTP 101 chỉ chứng minh handshake ở tầng giao thức đã được chấp nhận.** Nó không chứng minh STOMP CONNECT được chấp nhận, càng không chứng minh client có quyền nhận tất cả các topic.

### 3.2. Browser không tự chặn vì khác origin

Khác với Fetch, browser có thể thử mở native WebSocket tới server khác origin. Nếu server cho phép handshake từ `https://evil.example.org`, JavaScript ở trang đó có thể gửi/nhận frame trên connection đã mở.

Response 101 thường **không cần** `Access-Control-Allow-Origin` để browser tiếp tục dùng `WebSocket`. Bảo vệ phụ thuộc vào việc server có kiểm tra Origin, cookie/session, token và quyền message hay không.

Tuy nhiên, browser vẫn có các lớp chặn **khác** CORS:

- CSP `connect-src` có thể không cho JavaScript kết nối tới một WebSocket URL.
- Mixed-content/TLS restrictions có thể ngăn một trang HTTPS sử dụng WebSocket không bảo mật `ws://`.
- Browser cookie policy có thể khiến phiên không được gửi.
- Network, certificate và proxy có thể làm handshake thất bại.

**Không đồng nhất những lỗi này với CORS Fetch.** Khi console nói WebSocket connection failed, cần kiểm tra CSP, TLS, Origin, HTTP authentication và gateway trước khi sửa ACAO.

### 3.3. Origin từ browser đáng dùng, nhưng không đáng tin như user identity

Script thông thường không thể tự đặt một giá trị `Origin` tùy ý cho `new WebSocket(...)`. Đây là lý do server có thể dùng Origin validation để chống những trang web độc hại cố dùng phiên người dùng.

Ngược lại, một WebSocket client do chương trình tự viết có thể cố ý đặt Origin bằng bất kỳ chuỗi nào. Một allowlist Origin không đủ để bảo vệ API khỏi non-browser clients.

## 4. So sánh thực thi same-origin: Fetch và WebSocket

| Khía cạnh | Fetch/XHR HTTP | Native WebSocket |
| --- | --- | --- |
| Lệnh browser | `fetch(url, options)` | `new WebSocket(url)` |
| Khác origin có thể phát request? | Có, nhưng bị CORS/SOP ràng buộc; có thể preflight | Có thể thử handshake cross-origin |
| Browser có tự làm preflight OPTIONS? | Có khi method/headers không safelisted | **Không theo quy trình Fetch CORS** |
| Server phát ACAO/ACAC để browser cho JS đọc? | Cần khi cross-origin response hợp lệ | **Không phải cơ chế native WebSocket áp dụng** |
| Browser gửi Origin? | Thường có trong CORS requests | Thường gửi trong WebSocket handshake do browser tạo |
| Ai đánh giá Origin cho quyền bắt tay? | CORS processor/server và browser kiểm tra CORS response | **WebSocket server/handshake handler** |
| Cookie có tự đính kèm? | Theo `credentials` và cookie policy | Browser tự quyết định theo cookie policy; JS WebSocket không có `credentials` option như Fetch |
| JavaScript đặt arbitrary HTTP request header? | Có thể đặt nhiều headers theo Fetch rules | **Không** trong WebSocket constructor |
| Sau khi kết nối hoàn tất | Mỗi HTTP request được xử lý độc lập | Một connection có thể mang nhiều frames/messages |
| Bảo vệ thao tác nghiệp vụ | HTTP authentication/authorization/CSRF | Authentication handshake/CONNECT + authorization từng message |
| Client ngoài browser có bị SOP kiểm soát? | Không | Không |
| Nếu server cấp Origin quá rộng | Có thể lộ response qua CORS, đặc biệt với credentials | Có thể cho website lạ đọc/gửi WebSocket frames với phiên người dùng nếu được đính kèm |

**Kết luận trọng tâm:** ranh giới same-origin của browser không tạo một “lá chắn mặc định giống nhau” cho mọi giao thức. WebSocket được thiết kế để giao tiếp giữa origins, nên trách nhiệm từ chối origins không tin cậy nằm ở phía server.

## 5. Cross-Site WebSocket Hijacking (CSWSH)

### 5.1. Kịch bản nguy cơ

Alice đã đăng nhập vào `https://api.example.com` và có một session cookie. Cô mở một website khác, do attacker kiểm soát, tại `https://evil.example.org`. Trang này chạy:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws");

socket.onopen = () => {
  // Nếu handshake được server chấp nhận,
  // trang không tin cậy có thể nói giao thức ứng dụng.
  socket.send("request-private-data");
};

socket.onmessage = event => {
  // Đây sẽ là vấn đề nếu backend gửi thông tin riêng của Alice
  // mà không bảo vệ Origin, session và quyền ở message layer.
  console.log(event.data);
};
~~~

Nếu cookie của Alice được browser gửi tới endpoint và server không kiểm tra Origin, trang độc hại có thể dùng kênh WebSocket với ngữ cảnh Alice. Trong trường hợp ứng dụng dùng STOMP, attacker còn cần gửi frames phù hợp, ví dụ CONNECT/SUBSCRIBE; thiếu CSRF CONNECT/message authorization sẽ làm rủi ro tăng.

Đây là **Cross-Site WebSocket Hijacking**: website không tin cậy cố lợi dụng browser và session của nạn nhân để thiết lập một kênh hai chiều.

### 5.2. Các điều kiện cần phân biệt

Không phải lần thử nào của attacker cũng thành công. Kịch bản phụ thuộc:

- Browser có gửi cookie phiên hay không: `SameSite`, Domain/Path, `Secure` và chính sách browser.
- HTTP handshake có yêu cầu authentication đúng không.
- Server có kiểm tra `Origin` và từ chối origin lạ không.
- STOMP CONNECT có yêu cầu CSRF token/identity đúng không.
- SEND/SUBSCRIBE và business service có phân quyền theo user/object/tenant không.
- Server có phát dữ liệu nhạy cảm tới destination/subscription mà client không có quyền không.

Việc một tầng chặn được attack không có nghĩa các tầng còn lại có thể bỏ hết. Thiết kế an toàn dùng **defense in depth**.

### 5.3. Vì sao SameSite chưa phải giải pháp đầy đủ?

Một subdomain như `https://usercontent.example.com` có thể chạy JavaScript do user tạo. Nó khác origin với `https://api.example.com` nhưng thường same-site.

Nếu cookie phiên vẫn được gửi trong ngữ cảnh same-site, SameSite không chặn thao tác chỉ vì trang bắt nguồn từ subdomain khác. **Origin allowlist** phải chỉ bao gồm các frontend thực sự tin cậy; không tự mở `https://*.example.com` nếu có bất kỳ subdomain do khách hàng kiểm soát, preview không tin cậy hoặc nguy cơ subdomain takeover.

## 6. Spring WebSocket/STOMP kiểm soát Origin ở handshake

Trong Spring WebSocket Message Broker trên stack Servlet, cấu hình endpoint bằng `WebSocketMessageBrokerConfigurer`.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class WebSocketEndpointConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

### 6.1. Ba lựa chọn Origin policy

**Chính sách chỉ cho cùng origin:** các endpoint Spring WebSocket mặc định thường hạn chế origins về cùng origin, trừ khi được cấu hình mở rộng. Hãy kiểm tra cấu hình cụ thể của version/stack và endpoint được đăng ký; không coi mặc định này là authentication.

**Chính sách allowlist rõ ràng:**

~~~java
registry.addEndpoint("/ws")
    .setAllowedOrigins(
        "https://app.example.com",
        "https://admin.example.com"
    );
~~~

Chỉ đưa vào những frontend được tin cậy để chạy JavaScript và nhận dữ liệu của WebSocket. Việc frontend admin được phép ở handshake **không** tự cấp quyền admin ở STOMP.

**Chính sách pattern có kiểm soát:**

~~~java
registry.addEndpoint("/ws")
    .setAllowedOriginPatterns("https://*.trusted-ui.example.com");
~~~

Pattern có thể hữu ích khi hạ tầng thực sự kiểm soát toàn bộ subdomain thuộc namespace đó. Nhưng đây là **mở rộng ranh giới tin cậy**: mọi website khớp pattern có thể thử kết nối.

Không dùng `setAllowedOrigins("*")` hoặc pattern bao trùm các domain do người khác quản lý cho ứng dụng dùng session cookies. Nếu cần cấu hình tenant/custom domain, phải xác minh quyền sở hữu domain và duy trì registry tin cậy, không tự suy ra từ suffix.

### 6.2. Những điều cấu hình trên làm và không làm

| Cấu hình | Có tác dụng | Không thay thế |
| --- | --- | --- |
| `registry.addEndpoint("/ws")` | Định nghĩa HTTP handshake endpoint | Login, Origin allowlist, authorization |
| `setAllowedOrigins(...)` | Giới hạn browser origins được chấp nhận khi bắt tay | Authentication token/session |
| `setAllowedOriginPatterns(...)` | Cho phép origins khớp pattern | Đánh giá mức tin cậy thật của tất cả subdomain |
| `setApplicationDestinationPrefixes("/app")` | Định tuyến client messages tới application handlers | Phân quyền từng SEND |
| `enableSimpleBroker("/topic", "/queue")` | Phát messages tới subscriptions | Phân quyền từng SUBSCRIBE hoặc bảo mật broker bên ngoài |
| `setUserDestinationPrefix("/user")` | Hỗ trợ user destinations | Ownership checks và đúng user routing |

**Không nhầm `setAllowedOrigins` ở WebSocket endpoint với `allowedOrigins` của CORS HTTP API.** Chúng có thể cùng dùng danh sách frontend, nhưng hoạt động tại **hai cơ chế khác nhau**.

### 6.3. Không dùng so khớp origin bằng chuỗi con

Các cách so khớp thủ công như sau rất dễ sai:

~~~java
// Anti-pattern: host giả có thể chứa đúng chuỗi này.
boolean allowed = origin.contains("app.example.com");

// Anti-pattern: chuỗi bắt đầu đúng nhưng host có hậu tố nguy hiểm.
boolean allowed2 = origin.startsWith("https://app.example.com");
~~~

`https://app.example.com.evil.example.org` không phải `https://app.example.com`. Dùng API allowlist chính xác của Spring, cùng test khác scheme, khác port, hostname giả và Origin `null`.

## 7. HTTP authentication tại handshake: ranh giới thứ nhất

Origin validation giảm rủi ro trang web lạ, nhưng server vẫn phải xác định **client/user là ai**.

Ví dụ Spring Security Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HandshakeHttpSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/ws", "/ws/**").authenticated()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .build();
    }
}
~~~

Với session login, browser có thể mang session cookie trên `GET /ws` nếu cookie policy cho phép. Spring Security nhận diện principal trên handshake rồi truyền ngữ cảnh phù hợp vào WebSocket session/STOMP.

**Giới hạn của đoạn code:**

- `authenticated()` chỉ quyết định kết nối HTTP có thể bắt tay hay không.
- `SecurityFilterChain` không kiểm tra tự động từng STOMP SEND hoặc SUBSCRIBE sau HTTP 101.
- Code chưa cấu hình cơ chế đăng nhập, token/resource server hoặc endpoint thực tế. Đây là **mẫu ranh giới**, không phải ứng dụng triển khai hoàn chỉnh.
- Nếu dự án dự kiến xác thực token **chỉ** trong STOMP CONNECT, `authenticated()` tại handshake sẽ chặn client trước khi token được kiểm tra. Phải chọn kiến trúc nhất quán.
- HTTP CSRF protection thông thường không được xem là thay thế CSRF ở STOMP CONNECT.

### 7.1. Browser WebSocket constructor không có credentials option

Khác với Fetch:

~~~javascript
fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

WebSocket không có cách gọi:

~~~javascript
// KHÔNG có WebSocket option này:
new WebSocket("wss://api.example.com/ws", {
  credentials: "include"
});
~~~

Browser quản lý việc gửi cookie trên handshake theo chính sách cookie, không bằng Fetch credentials mode mà JavaScript truyền vào constructor. Vì vậy nếu WebSocket kết nối thất bại do thiếu phiên, cần điều tra **Cookie, SameSite, Secure, Domain/Path, third-party-cookie restrictions và HTTP authentication**, thay vì thêm một option không tồn tại.

### 7.2. Browser không đặt được Authorization header tùy ý trên handshake

Không thể dùng trực tiếp:

~~~javascript
// KHÔNG được WebSocket API chuẩn hỗ trợ:
new WebSocket("wss://api.example.com/ws", {
  headers: {
    Authorization: "Bearer <token>"
  }
});
~~~

Browser WebSocket constructor hỗ trợ URL và danh sách subprotocols, **không hỗ trợ một object headers tùy ý** như Fetch.

Các phương án cần thiết kế rõ ràng:

- Dùng session cookie, xác thực trên HTTP handshake.
- Nếu dùng STOMP, gửi access token trong **STOMP CONNECT native header**, rồi có interceptor xác thực token và gắn principal trước bước message authorization.
- Nếu sử dụng kênh cấp vé kết nối ngắn hạn riêng, phải thiết kế one-time ticket, TTL, binding và chính sách log/transport cẩn thận.
- Tránh đưa access token dài hạn vào URL query vì URL dễ xuất hiện trong log, tracing hoặc cấu hình proxy.
- Không dùng `Sec-WebSocket-Protocol` hoặc một native header do client khai báo làm bằng chứng danh tính nếu server chưa **thực sự xác minh** token.

## 8. STOMP CONNECT không phải HTTP Upgrade

Sau khi HTTP handshake trả 101, ứng dụng dùng STOMP thường trao đổi frame `CONNECT`:

~~~text
CONNECT
accept-version:1.2
host:api.example.com
X-CSRF-TOKEN:<csrf-token>

^@
~~~

Tiếp theo là `SEND`/`SUBSCRIBE`:

~~~text
SUBSCRIBE
id:sub-1
destination:/user/queue/updates

^@
~~~

~~~text
SEND
destination:/app/orders.lookup
content-type:application/json

{"orderId":1001}
^@
~~~

`^@` biểu diễn NUL kết thúc frame STOMP. Những STOMP headers này nằm **bên trong WebSocket frames**, không phải HTTP request headers. Browser vẫn không áp dụng CORS Fetch lên nội dung frame.

### 8.1. CSRF trên STOMP CONNECT

Với Spring Security WebSocket Messaging sử dụng `@EnableWebSocketSecurity`, cơ chế bảo vệ CONNECT yêu cầu CSRF token hợp lệ trên inbound STOMP CONNECT theo chính sách Spring Security tương ứng. Điều này quan trọng vì browser có thể tự gửi cookie phiên khi handshake cross-origin.

Một frontend có thể lấy token qua endpoint HTTP được bảo vệ:

~~~java
import java.util.Map;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfTokenResource {

    @GetMapping("/api/csrf")
    Map<String, String> getToken(
        @RequestAttribute("_csrf") CsrfToken csrfToken
    ) {
        return Map.of(
            "headerName", csrfToken.getHeaderName(),
            "token", csrfToken.getToken()
        );
    }
}
~~~

Endpoint trên là **ví dụ ứng dụng tự triển khai**, không phải endpoint có sẵn ở mọi Spring Boot app. Nếu frontend khác origin, HTTP API `/api/csrf` phải có CORS policy **riêng** cho origin tin cậy và xác thực phiên. Với CSRF token deferred/masked hay custom request handler, cách trả token cần được kiểm tra theo cấu hình cụ thể.

Frontend dùng `@stomp/stompjs`:

~~~javascript
import { Client } from "@stomp/stompjs";

async function connectRealtime() {
  const response = await fetch(
    "https://api.example.com/api/csrf",
    { credentials: "include" }
  );

  if (!response.ok) {
    throw new Error("Không lấy được CSRF token");
  }

  const { token, headerName } = await response.json();

  const client = new Client({
    brokerURL: "wss://api.example.com/ws",
    connectHeaders: {
      [headerName]: token
    },
    onConnect: () => {
      client.subscribe("/user/queue/updates", frame => {
        console.log("Realtime event:", frame.body);
      });
    },
    onStompError: frame => {
      console.error("STOMP lỗi:", frame.headers.message);
    }
  });

  client.activate();
  return client;
}
~~~

`connectHeaders` là **STOMP native headers**; nó không làm browser thêm arbitrary HTTP headers cho handshake. Đoạn mã minh họa giả định đã có session hợp lệ và CSRF endpoint hoạt động, chưa xử lý reconnect sau token rotation hoặc logout.

### 8.2. Vì sao chỉ kiểm tra Origin vẫn chưa đủ?

Một STOMP client không phải browser có thể giả `Origin` và gửi CONNECT. Một attacker chạy XSS trong frontend đáng tin cậy cũng phát sinh từ **đúng Origin**. Do vậy:

- Cần authentication theo token/session được server xác minh.
- STOMP CONNECT cần yêu cầu bảo vệ CSRF tương ứng khi dùng browser-managed credentials.
- Mỗi SEND/SUBSCRIBE cần destination authorization.
- Những lệnh có object/tenant ID phải được service phân quyền theo principal.
- Logout/revocation cần kiểm soát connection đã mở.

**Origin validation là lớp phòng vệ quan trọng nhưng không thể đứng một mình.**

## 9. Phân quyền message ở Spring Security: ranh giới thứ hai

Trong Spring WebSocket Messaging, message authorization áp dụng cho **inbound messages** từ client. Một mẫu deny-by-default:

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
class StompInboundSecurity {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
        MessageMatcherDelegatingAuthorizationManager.Builder messages
    ) {
        return messages
            .nullDestMatcher().authenticated()
            .simpSubscribeDestMatchers("/app/**").denyAll()
            .simpSubscribeDestMatchers(
                "/user/queue/updates",
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

Giải thích:

- `nullDestMatcher().authenticated()` bao gồm các message không có destination tương ứng, như CONNECT khi principal đã được xác minh.
- Chặn `SUBSCRIBE` vào `/app/**`, vì đó thường là nơi client gửi command tới handler.
- Cho phép subscription vào **những destination được chỉ định**, không mở `/topic/**` vô điều kiện.
- Chỉ cho SEND vào `/app/orders.lookup` khi principal có role USER.
- Các MESSAGE/SUBSCRIBE khác bị từ chối; **client không được SEND trực tiếp vào broker `/topic/**`**.
- Không coi những matcher trên là permission cho từng order ID/tenant; service phải kiểm tra thêm.

### 9.1. Không cấp quyền chỉ bằng prefix

Một lỗ hổng dễ mắc:

~~~java
// Không nên làm nếu /topic/orders/* chứa dữ liệu riêng tư:
messages.simpSubscribeDestMatchers("/topic/orders/*")
    .authenticated();
~~~

Alice có role USER nhưng không sở hữu order của Bob. Nếu rule chỉ yêu cầu authenticated, Alice có thể thử subscribe vào topic của Bob. Cần per-object authorization tại inbound subscribe và/hoặc mô hình user destinations được kiểm soát, đồng thời kiểm tra đúng dữ liệu trước khi phát.

### 9.2. Business service phải đối chiếu principal và object

~~~java
import java.security.Principal;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

record OrderLookup(long orderId) {}
record OrderView(long orderId, String status) {}

interface OrderQueryService {
    // Implementation phải xác minh order thuộc quyền của username/tenant.
    OrderView findAuthorizedOrder(String username, long orderId);
}

@Controller
class OrderMessageController {

    private final OrderQueryService orders;
    private final SimpMessagingTemplate messaging;

    OrderMessageController(
        OrderQueryService orders,
        SimpMessagingTemplate messaging
    ) {
        this.orders = orders;
        this.messaging = messaging;
    }

    @MessageMapping("/orders.lookup")
    void lookup(@Payload OrderLookup input, Principal principal) {
        OrderView result = orders.findAuthorizedOrder(
            principal.getName(), input.orderId()
        );

        messaging.convertAndSendToUser(
            principal.getName(),
            "/queue/updates",
            result
        );
    }
}
~~~

Đây là **mã minh họa kiến trúc**, không phải một hệ thống order hoàn chỉnh. `OrderQueryService` phải thực thi quyền thật theo principal và dữ liệu sở hữu ở server. `convertAndSendToUser` hỗ trợ routing tới user destination, nhưng vẫn cần kiểm tra object/tenant trước khi gửi.

### 9.3. HTTP 101 không có nghĩa CONNECT hoặc SEND được phép

Tách ba assertion:

~~~text
HTTP handshake:    101 Switching Protocols?
STOMP handshake:   Có CONNECTED sau CONNECT với token hợp lệ?
Business message:  Có thể SEND/SUBSCRIBE đúng destination và đúng quyền object?
~~~

Một kết nối thành công ở tầng trước **không** cấp quyền tự động cho tầng sau. Nếu STOMP security từ chối CONNECT, client có thể nhận ERROR hoặc connection bị đóng tùy cấu hình; không suy diễn chỉ từ việc HTTP 101.

## 10. Cookie, session và origin ở WebSocket: thực hành với same-site

### 10.1. Ví dụ hai subdomain cùng site

Trang `https://app.example.com` kết nối tới `wss://api.example.com/ws`:

- Khác origin theo SOP.
- Thường same-site khi xét site của cookie.
- Browser có thể gửi host-only cookie dành cho `api.example.com` tới endpoint này, dù script ở `app.example.com` không được đọc cookie đó bằng `document.cookie`.
- Server vẫn cần Origin allowlist; cùng site không đồng nghĩa frontend được tin cậy.

Một cookie ví dụ:

~~~http
Set-Cookie: SESSION=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

`HttpOnly` ngăn JS lấy ID phiên trực tiếp, nhưng không ngăn một handshake hợp lệ mang cookie. `SameSite=Lax` là lớp giảm rủi ro cross-site; với subdomain same-site không tin cậy, cần Origin validation và các lớp khác.

### 10.2. Tại sao cross-site có thể không gửi cookie?

Một trang `https://external-partner.example.org` mở `wss://api.example.com/ws` trong browser. Nếu cookie phiên API không được gửi vì `SameSite` hoặc chính sách third-party cookie, server có thể trả 401 dù origin đã được cấu hình cho phép.

Không sửa bằng cách bật `SameSite=None` hoặc mở wildcard Origin ngay lập tức. Hãy xác định rõ:

1. Có yêu cầu hỗ trợ frontend cross-site thực sự không?
2. Authentication nên dùng session cookie hay ticket/token dành cho realtime?
3. Browser, proxy và session store hỗ trợ mô hình nào?
4. Khi cấp quyền cho partner origin, có cho JavaScript ở đó đọc dữ liệu/subscribe topic riêng tư không?
5. Có biện pháp CSRF CONNECT, message authorization và logout/revocation tương ứng không?

Với session cookie cross-site, những lựa chọn `SameSite=None; Secure` và các hạn chế cookie bên thứ ba vẫn có thể tác động. CORS của HTTP API **không** buộc browser gửi cookie ở WebSocket handshake.

### 10.3. Origin không phải principal

Nếu browser hoặc HTTP client gửi `Origin: https://admin.example.com`, điều đó **không chứng minh caller có role ADMIN**. Origin nói về nguồn script trong browser, không phải quyền tài khoản.

Một người dùng thường đang ở chính frontend admin cũng phải chịu login và role checks ở server. Một HTTP client có thể giả Origin trong request WebSocket. Kiểm tra identity và authorization độc lập là bắt buộc.

## 11. WebSocket connection dài hạn tạo rủi ro riêng

Fetch thường tạo nhiều request độc lập; server có thể kiểm tra authentication/authorization trên từng HTTP request. WebSocket giữ một connection mở lâu, và nhiều message dùng chung ngữ cảnh.

Điều gì xảy ra khi:

- User logout khỏi website trong khi WebSocket vẫn mở?
- Phiên bị thu hồi hoặc token hết hạn?
- Role ADMIN bị gỡ trong lúc user đang subscribe?
- User rời một tenant/phòng chat nhưng vẫn nghe topic cũ?
- Client gửi quá nhiều frames hoặc payload quá lớn?
- Backend triển khai nhiều instance và WebSocket proxy đổi route?

Một hệ thống nhạy cảm cần thiết kế:

1. **Xác thực kết nối:** xác minh phiên/token tại handshake hoặc CONNECT theo mô hình đã chọn.
2. **Phân quyền từng hành động:** SEND/SUBSCRIBE phải được kiểm tra theo principal, destination và object.
3. **Phân quyền khi phát dữ liệu:** không phát message tới user/session/topic đã mất quyền.
4. **Thu hồi:** đóng connection, hủy subscription, hoặc kiểm tra lại quyền khi cần.
5. **Giới hạn tài nguyên:** giới hạn kích thước message, số subscription, tốc độ SEND, thời gian không hoạt động và heartbeats.
6. **Audit:** phân biệt handshake rejected, STOMP CONNECT failed, SUBSCRIBE denied và business permission denied.

Nếu một client gửi Origin hợp lệ nhưng spam messages, Origin validation không giúp chống lạm dụng. Rate limiting, quotas và giới hạn kích thước là những lớp bổ sung.

## 12. SockJS fallback: không gom chung với native WebSocket

Spring WebSocket/STOMP có thể bật SockJS fallback:

~~~java
registry.addEndpoint("/ws")
    .setAllowedOrigins("https://app.example.com")
    .withSockJS();
~~~

SockJS có thể chọn native WebSocket hoặc những transport dự phòng như XHR streaming/polling, tùy client và môi trường.

**Khác biệt bảo mật:**

- **Native WebSocket:** handshake dùng cơ chế WebSocket; không thực thi Fetch CORS preflight/ACAO.
- **SockJS dùng XHR/fallback:** các HTTP requests có thể chịu CORS và CSRF HTTP tương ứng, bao gồm preflight/response headers ở transport thích hợp.
- **STOMP CONNECT:** vẫn là bước messaging riêng, cần CSRF CONNECT và message security theo thiết kế.
- **Origin restrictions:** cấu hình origins có thể ảnh hưởng những SockJS transports được hỗ trợ; cần test chính xác các transport ứng dụng thực sự dùng.

Nếu SockJS XHR POST bị CSRF HTTP từ chối trong khi native WebSocket hoạt động, đừng tắt toàn bộ CSRF ứng dụng. Chỉ thiết kế ngoại lệ cho những transport paths cần thiết khi framework/phiên bản yêu cầu, giữ bảo vệ cho API POST khác và STOMP CONNECT.

### 12.1. CORS Fetch thành công không chứng minh SockJS hay WebSocket an toàn

Một app có thể trả đúng ACAO cho `/api/**` nhưng `/ws` lại cho phép mọi Origin. Ngược lại, WebSocket chỉ cho app origin nhưng SockJS fallback bị gateway từ chối OPTIONS vì không forward request headers.

Hãy kiểm thử **native WebSocket và những fallback thực dùng** riêng, từ origin được phép và không được phép.

## 13. WebFlux native WebSocket: không có STOMP message broker mặc định

Spring WebFlux cung cấp `WebSocketHandler` và `WebSocketSession`; không đồng nghĩa với cấu hình STOMP broker Servlet `@EnableWebSocketMessageBroker`.

Ở WebFlux:

- `ServerHttpSecurity` có thể bảo vệ HTTP handshake route.
- Cần Origin validation ở handshake, ví dụ một `WebFilter` hoặc cơ chế được tích hợp vào adapter/handler.
- `WebSocketHandler` phải kiểm tra từng text/binary message, principal và quyền object.
- `CorsWebFilter`/`ServerHttpSecurity.cors(...)` không tự biến thành kiểm tra Origin/message authorization cho native WebSocket.
- Nếu triển khai STOMP trên một giải pháp Reactive riêng, phải xác minh security cho giao thức và broker cụ thể; không mặc định có chính sách `@EnableWebSocketSecurity` Servlet.

### 13.1. HTTP handshake security với ServerHttpSecurity

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveWebSocketSecurity {

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

Đoạn code trên minh họa **HTTP route authorization**, chưa xác thực danh tính cụ thể hoặc kiểm tra Origin/message. Với bearer token được đưa **chỉ** bên trong WebSocket messages, authenticated HTTP handshake cần một mô hình khác để không chặn trước khi nhận token.

### 13.2. Một Origin guard minh họa cho WebFlux

~~~java
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.WebFilter;

@Configuration
class ReactiveWebSocketOriginGuard {

    private static final Set<String> ALLOWED =
        Set.of("https://app.example.com");

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter originGuard() {
        return (exchange, chain) -> {
            if (!"/ws".equals(exchange.getRequest().getPath().value())) {
                return chain.filter(exchange);
            }

            String origin = exchange.getRequest()
                .getHeaders().getOrigin();

            if (origin == null || !ALLOWED.contains(origin)) {
                exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }

            return chain.filter(exchange);
        };
    }
}
~~~

Đây là **policy minh họa** cho route chỉ phục vụ browser WebSocket. Nó từ chối Origin vắng mặt theo thiết kế; một service cần hỗ trợ non-browser clients phải có mô hình riêng đã xác thực, không chỉ bỏ toàn bộ kiểm tra. Ứng dụng thật phải đánh giá path rewrite, handshake detection, multiple WebFilters, trusted proxy headers và canonicalization của Origin.

**Không** dùng `origin.contains("example.com")` hoặc coi Origin như authentication. Guard kiểm soát nguồn script; security chain kiểm soát danh tính; handler/service kiểm soát quyền từng message.

### 13.3. Phân quyền mỗi message trong WebFlux

~~~java
import java.security.Principal;
import reactor.core.publisher.Mono;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.reactive.socket.WebSocketHandler;

interface RealtimeCommandService {
    Mono<Void> authorizeAndHandle(
        Principal principal,
        String messageText
    );
}

class ReactiveRealtimeHandler {

    static WebSocketHandler secure(RealtimeCommandService commands) {
        return session -> session.getHandshakeInfo()
            .getPrincipal()
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Unauthenticated")))
            .flatMap(principal ->
                session.receive()
                    .concatMap(message ->
                        commands.authorizeAndHandle(
                            principal, message.getPayloadAsText()
                        ))
                    .then()
            );
    }
}
~~~

`RealtimeCommandService` phải parse/validate nội dung, áp dụng giới hạn kích thước, role/ownership/tenant checks và các quy tắc nghiệp vụ. Đây là skeleton để minh họa điểm kiểm tra, **chưa phải** một ứng dụng WebFlux có route/handler registration hoàn chỉnh.

Nếu handler cần trả response, thêm luồng `session.send(...)` có kiểm soát backpressure và kiểm tra dữ liệu trước khi phát cho client. Đừng để mọi message tự do gọi một chức năng nhạy cảm chỉ vì HTTP handshake đã được xác thực.

## 14. Ma trận kiểm thử same-origin, Origin và message layer

### 14.1. Kiểm thử handshake

| Mã | Nguồn gọi và điều kiện | Kỳ vọng | Bảo vệ nào được kiểm chứng? |
| --- | --- | --- | --- |
| H1 | Browser ở `https://app.example.com`, session hợp lệ | Handshake `/ws` được chấp nhận | HTTP auth + Origin allowlist |
| H2 | Browser ở `https://evil.example.org`, session thử nghiệm hợp lệ nếu cookie policy cho phép | Handshake bị từ chối bởi Origin policy | Chặn cross-origin browser không tin cậy |
| H3 | Origin `http://app.example.com` | Bị từ chối | Scheme là thành phần origin |
| H4 | Origin `https://app.example.com:8443` | Bị từ chối nếu không khai báo port này | Port là thành phần origin |
| H5 | Origin `https://app.example.com.evil.example.org` | Bị từ chối | Không so khớp hostname tiền tố |
| H6 | Origin `null`/opaque origin | Mặc định không được cấp quyền | Không mở null Origin tùy tiện |
| H7 | Origin đúng nhưng chưa login | Handshake bị HTTP Security chặn nếu policy yêu cầu auth | Origin không thay login |
| H8 | Non-browser client giả Origin đúng nhưng thiếu auth | Bị authentication từ chối | Origin không phải danh tính |
| H9 | Cùng origin nhưng session bị thu hồi | Bị authentication từ chối | Same-origin không thay session validation |

**Lưu ý về H2:** nếu cookie không được browser gửi vì SameSite/third-party policy, handshake có thể bị chặn bởi **authentication** trước khi kiểm tra Origin. Để khẳng định Origin policy thực sự hoạt động, cần test có ngữ cảnh auth hợp lệ phù hợp hoặc một integration test kiểm tra trực tiếp Origin validation.

### 14.2. Kiểm thử STOMP sau handshake

| Mã | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| M1 | HTTP 101, STOMP CONNECT có CSRF hợp lệ và principal đúng | Nhận CONNECTED |
| M2 | HTTP 101, CONNECT thiếu/sai CSRF khi có bảo vệ | CONNECT không được chấp nhận |
| M3 | CONNECTED, SEND `/app/orders.lookup` với role USER | Qua matcher, còn phải kiểm tra order ownership |
| M4 | SEND trực tiếp `/topic/public` | Bị từ chối theo MESSAGE policy |
| M5 | SUBSCRIBE `/topic/private` ngoài allowlist | Bị từ chối |
| M6 | Alice SEND yêu cầu đọc order của Bob | Không phát dữ liệu Bob |
| M7 | User mất role/session khi connection còn mở | Có cơ chế thu hồi/revalidate theo chính sách |
| M8 | Client gửi message oversized hoặc quá nhiều subscription | Bị giới hạn/từ chối phù hợp |

Hãy kiểm tra **không có side effect** hoặc dữ liệu riêng tư bị phát nhầm, thay vì chỉ xác nhận một frame ERROR. Đây là phần rất dễ bị bỏ sót khi kiểm thử WebSocket.

## 15. Thực nghiệm: browser, curl và STOMP client

### 15.1. Hai trang browser khác origin

Tạo hai trang thử nghiệm trên những domain mà nhóm sở hữu:

- `https://app.example.com/ws-test.html`.
- `https://evil.example.org/ws-test.html`.

Cùng đoạn script:

~~~html
<button id="open">Kết nối WebSocket</button>
<pre id="output"></pre>

<script>
  const output = document.querySelector("#output");

  document.querySelector("#open").addEventListener("click", () => {
    const socket = new WebSocket("wss://api.example.com/ws");

    socket.onopen = () => {
      output.textContent += "WebSocket open\n";
    };

    socket.onmessage = (event) => {
      output.textContent += "Message: " + event.data + "\n";
    };

    socket.onerror = () => {
      output.textContent += "WebSocket error\n";
    };

    socket.onclose = (event) => {
      output.textContent += "Closed: " + event.code + "\n";
    };
  });
</script>
~~~

Đây chỉ là test **handshake/native WebSocket**, không tự gửi STOMP CONNECT. Nếu server yêu cầu STOMP và đóng kết nối vì không nhận CONNECT trong thời gian quy định, cần dùng thư viện STOMP để test đầy đủ.

**Điều cần quan sát:**

1. Tại trang app hợp lệ, browser có gửi `Origin: https://app.example.com` không?
2. Server trả HTTP 101 hay 401/403?
3. Tại trang evil, server từ chối handshake do Origin hay do thiếu session?
4. Có CSP `connect-src` cấm `wss://api.example.com` trước khi handshake không?
5. WebSocket messages có đi qua các bước xác thực/phân quyền ở message layer không?

Không dùng session hoặc dữ liệu production của người dùng thật để thực nghiệm với trang không tin cậy.

### 15.2. Curl chỉ quan sát một phần HTTP handshake

~~~bash
curl -i --http1.1 "https://api.example.com/ws" \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Origin: https://evil.example.org"
~~~

Lệnh này hỗ trợ kiểm tra request route và phản ứng của server/proxy đối với Origin, **nhưng curl không tự trở thành một STOMP client hoàn chỉnh**. Nếu không có cookie/token, 401 có thể đến từ HTTP auth trước Origin policy. Với một server/proxy phiên bản khác, lỗi handshake có thể là 400/403 vì yêu cầu thiếu điều kiện giao thức.

Không diễn giải HTTP 101 từ một công cụ HTTP như bằng chứng STOMP CONNECT/SEND/SUBSCRIBE được phép.

### 15.3. Non-browser WebSocket client có thể giả Origin

Một test quan trọng là sử dụng một WebSocket client chuyên dụng có thể tùy chỉnh HTTP handshake headers, thử:

- Origin giả là `https://app.example.com` nhưng không có token/session.
- Origin lạ nhưng có credential thử nghiệm hợp lệ, để xác minh Origin policy.
- Origin hợp lệ, authenticated, nhưng STOMP CONNECT thiếu CSRF token.
- CONNECT hợp lệ rồi SEND/SUBSCRIBE trái quyền.
- Message có object ID của user khác.

Kết quả mong đợi: **authentication/authorization phải đứng vững bất kể client tự khai Origin thế nào**. Client ngoài browser không thực thi SOP, nên đây là test phân biệt rất có giá trị.

### 15.4. Integration test với Spring WebSocketStompClient

Khi ứng dụng dùng STOMP broker Servlet, `WebSocketStompClient` kết hợp `StandardWebSocketClient` có thể mô phỏng handshake và STOMP frames trong integration test. Cấu trúc bài test nên gồm:

~~~text
Given:
  - Spring Boot test server đang chạy trên random port.
  - Một tài khoản test authenticated với session/ticket hợp lệ.
  - CSRF token test được cấp theo đúng repository/session.
  - WebSocketStompClient có khả năng thiết lập handshake và STOMP CONNECT.

When:
  1) Handshake với Origin hợp lệ, principal hợp lệ.
  2) STOMP CONNECT với CSRF native header phù hợp.
  3) SUBSCRIBE destination /user/queue/updates.
  4) SEND destination /app/orders.lookup, orderId do user sở hữu.

Then:
  - CONNECTED thành công.
  - Message phản hồi đúng user, đúng order, không gửi dữ liệu user khác.

Negative tests:
  - Origin ngoài allowlist: handshake không mở.
  - Thiếu CSRF CONNECT: không CONNECTED.
  - SEND tới /topic/**: bị deny.
  - SUBSCRIBE tới private destination: bị deny.
  - orderId của user khác: không có data leak/side effect.
~~~

Đây là **test design**, không giả là mã test đã chạy trong dự án cụ thể. Cần xử lý kết quả bất đồng bộ, timeout, STOMP ERROR/close events và chính sách reconnect. `MockMvc` chỉ kiểm tra được một phần HTTP routing/security; nó không thay thế WebSocket upgrade + STOMP frame test.

## 16. Lỗi thường gặp và cách phân loại

| Triệu chứng | Nguyên nhân cần xét | Hướng chẩn đoán |
| --- | --- | --- |
| Fetch HTTP trả lỗi CORS, nhưng WebSocket vẫn mở | Hai giao thức có cơ chế Origin khác nhau | Kiểm tra `http.cors(...)` riêng và WebSocket endpoint Origin policy riêng |
| WebSocket từ evil origin mở được | Endpoint cho origin quá rộng hoặc bỏ Origin guard | Kiểm tra `setAllowedOrigins`, pattern và gateway |
| WebSocket handshake 403 | Origin không được phép, auth/CSRF HTTP ở transport đặc biệt hoặc gateway chặn | Xem HTTP request/response trước STOMP |
| Handshake 401 | Không có session/token hoặc security matcher yêu cầu auth | Kiểm tra cookie policy và HTTP SecurityFilterChain |
| HTTP 101 rồi STOMP CONNECT thất bại | CSRF native header thiếu/sai, principal hoặc interceptor | Quan sát STOMP CONNECT/ERROR và token nguồn |
| HTTP 101, CONNECTED, SEND bị từ chối | Inbound message authorization | Kiểm tra `simpDestMatchers`, role và type |
| Client nhận message của user khác | Routing sai, topic/subscription quá rộng, thiếu object authorization | Kiểm tra `convertAndSendToUser`, ACL/tenant trước phát |
| Browser không gửi cookie dù Origin đúng | SameSite/Secure/Domain/Path/third-party policy | DevTools Cookies, request headers và login state |
| Frontend báo CSP `connect-src` | CSP frontend chặn WebSocket URL | Chỉ cho `wss://api.example.com` khi thật sự tin cậy |
| HTTPS frontend mở `ws://` bị chặn | Mixed content/TLS | Dùng `wss://` và cấu hình proxy TLS |
| Browser chỉ hoạt động direct, lỗi qua reverse proxy | Gateway không forward upgrade/route/Origin | Kiểm tra Upgrade, Connection, TLS termination, path |
| Browser thành công nhưng tool non-browser vẫn truy cập sai | Origin bị xem nhầm là authentication | Bắt xác thực/authorization thật; kiểm tra Origin chỉ là lớp bổ sung |
| `null` Origin được phép bất ngờ | Policy quá rộng hoặc custom Origin guard sai | Reject opaque Origin trừ khi có yêu cầu rất đặc biệt, đã được kiểm soát |
| SockJS fallback lỗi dù native WS tốt | CORS/CSRF trên XHR fallback khác | Kiểm tra transport, OPTIONS/POST, cookie và endpoint |
| Logout nhưng WebSocket vẫn nhận dữ liệu | Session đang sống, chưa thu hồi subscription/connection | Đóng hoặc revalidate quyền và khi phát dữ liệu |
| Một số subdomain “nội bộ” truy cập được không mong muốn | Pattern `*.example.com` quá rộng | Rà soát quyền quản lý từng hostname |
| Broker nhận SEND trực tiếp tới `/topic/**` | Message rules không chặn đích broker | Deny client MESSAGE tới broker destinations |
| Origin đúng nhưng user không có quyền object | CORS không thay server authorization | Kiểm tra principal + object ID/tenant trong service |

### 16.1. Chẩn đoán theo ba mốc

~~~text
A. Chưa có kết nối WebSocket:
   HTTP TLS/proxy -> CSP -> Origin validation -> HTTP authentication.

B. Đã mở WebSocket nhưng chưa dùng được STOMP:
   CONNECT native headers -> CSRF token -> principal/message security.

C. CONNECTED nhưng command/subscription thất bại:
   SEND/SUBSCRIBE type + destination -> role -> object/tenant ACL
   -> routing server -> lifecycle/revocation.
~~~

**Không sửa lỗi tại mốc A bằng cách tắt authorization ở mốc C**, và không dùng CORS HTTP headers để “sửa” một STOMP CONNECT thiếu CSRF token.

## 17. Checklist trước khi triển khai

- [ ] Đã phân biệt SOP/CORS của Fetch và native WebSocket Origin handshake.
- [ ] WebSocket endpoint có allowlist Origin cụ thể; không mặc định tin cậy mọi subdomain same-site.
- [ ] Test origin đúng, origin lạ, khác scheme/port, hostname giả và `Origin: null`.
- [ ] HTTP handshake route được authentication phù hợp; không coi Origin là principal.
- [ ] Browser gửi cookie theo chính sách mong muốn và không lộ session ID trong URL/log.
- [ ] Nếu xác thực token ở STOMP CONNECT, đã thiết kế interceptor và thứ tự kiểm tra rõ ràng.
- [ ] STOMP CONNECT bảo vệ CSRF khi dùng Spring Security Messaging với phiên browser.
- [ ] CORS HTTP cho endpoint lấy CSRF token được cấu hình riêng, chỉ cho frontend đáng tin cậy.
- [ ] Inbound MESSAGE/SUBSCRIBE deny by default; không cho client SEND trực tiếp vào broker destinations.
- [ ] Role/ownership/tenant được kiểm tra trên server ở handler/service, không tin ID/role từ payload.
- [ ] Session/logout/role changes có chiến lược thu hồi hoặc revalidate connections/subscriptions.
- [ ] CSP `connect-src` cho phép đúng các endpoint `wss://` cần thiết; HTTPS/TLS/HSTS không bị phá.
- [ ] Gateway chuyển tiếp WebSocket handshake/proxy headers đúng, không tự bỏ Origin validation.
- [ ] SockJS fallback, nếu bật, được test riêng về HTTP CORS/CSRF.
- [ ] WebFlux native WebSocket có Origin guard + HTTP authentication + per-message authorization.
- [ ] Có test browser từ origin được phép và bị chặn, cùng test non-browser có thể tự đặt Origin.
- [ ] Test được dữ liệu **không bị lộ** khi SUBSCRIBE/SEND trái quyền, không chỉ có frame ERROR.
- [ ] Có giới hạn message size, send rate, số subscription và kiểm soát kết nối không hoạt động.

## 18. Câu hỏi vận dụng có giải thích

**Tình huống 1 — Fetch bị CORS chặn.** `fetch()` từ `evil.example.org` không đọc được `/api/me`, nhưng `new WebSocket("wss://api.example.com/ws")` vẫn báo open. Có mâu thuẫn không?

**Giải thích:** Không. Native WebSocket không thực thi Fetch CORS preflight/ACAO. Server WebSocket phải kiểm tra Origin độc lập và bảo vệ handshake/message.

**Tình huống 2 — Cùng site.** `usercontent.example.com` do khách hàng quản lý khác origin với `api.example.com` nhưng cùng site. Cookie `SameSite=Lax` có luôn ngăn kết nối đó dùng session không?

**Giải thích:** Không. SameSite không phải ranh giới tin cậy giữa subdomains cùng site. Cần Origin allowlist cụ thể và chống CSWSH/CSRF message.

**Tình huống 3 — Origin giả.** Non-browser WebSocket client gửi `Origin: https://app.example.com`. Server có thể tin đây là user của app không?

**Giải thích:** Không. Client ngoài browser có thể tự đặt Origin; cần xác thực token/session, role, object-level authorization.

**Tình huống 4 — Handshake 101.** Backend trả HTTP 101. Có phải STOMP SEND tới `/topic/admin` sẽ được chấp nhận?

**Giải thích:** Không. 101 chỉ là kết quả handshake. STOMP CONNECT có thể bị CSRF chặn, SEND/SUBSCRIBE có message authorization riêng.

**Tình huống 5 — Thêm ACAO.** WebSocket handshake từ trang evil bị từ chối. Dev thử thêm `Access-Control-Allow-Origin: *` vào response. Việc này có giải quyết đúng không?

**Giải thích:** Không. ACAO không phải cơ chế native WebSocket yêu cầu. Cần xem Origin allowlist, authentication, proxy và bảo vệ message; không mở wildcard tùy tiện.

**Tình huống 6 — Browser không có Authorization header.** SPA có bearer token và muốn đưa token vào HTTP Authorization khi gọi `new WebSocket(...)`. Cách làm phổ biến đúng là gì?

**Giải thích:** WebSocket API trong browser không cho đặt arbitrary HTTP headers. Chọn xác thực bằng cookie đã bảo vệ hoặc thiết kế xác thực token tại STOMP CONNECT với interceptor xác minh thật; tránh đưa token dài hạn vào query.

**Tình huống 7 — CSRF CONNECT.** Browser mở socket nhưng STOMP CONNECT bị từ chối dù Origin đúng. Cần kiểm tra gì?

**Giải thích:** Token CSRF có nằm trong **STOMP native CONNECT header** của đúng session, repository/request handler có phù hợp, và principal được xác thực chưa.

**Tình huống 8 — Subscribe topic riêng tư.** Alice được SUBSCRIBE `/topic/orders/2002` của Bob chỉ vì đã login. Lỗi ở đâu?

**Giải thích:** Thiếu object/tenant authorization cho SUBSCRIBE và có thể thiếu kiểm tra routing khi phát dữ liệu. CORS/Origin không bảo vệ ownership.

**Tình huống 9 — CSP chặn.** Console báo vi phạm `connect-src` cho `wss://api.example.com/ws`. Đây có chắc là WebSocket Origin policy sai không?

**Giải thích:** Không. CSP frontend có thể chặn kết nối trước khi handshake. Chỉ bổ sung endpoint tin cậy vào CSP, đồng thời giữ server Origin/auth/message security.

**Tình huống 10 — SockJS khác native.** Native WebSocket hoạt động nhưng SockJS XHR POST bị 403. Có phải browser WebSocket bỗng dùng preflight CORS không?

**Giải thích:** Không. SockJS fallback dùng HTTP/XHR transport có thể chịu CORS/HTTP CSRF riêng. Xác định transport thực tế và bảo vệ CONNECT riêng.

**Tình huống 11 — Logout.** User logout HTTP nhưng socket vẫn nhận message từ topic cá nhân. Thay `setAllowedOrigins(...)` có giải quyết không?

**Giải thích:** Không. Cần cơ chế lifecycle, session revocation, hủy subscription/đóng connection và kiểm tra quyền khi phát dữ liệu.

**Tình huống 12 — WebFlux.** Ứng dụng WebFlux đã cấu hình `ServerHttpSecurity.pathMatchers("/ws").authenticated()`. Có tự được STOMP SEND/SUBSCRIBE authorization như Servlet không?

**Giải thích:** Không. WebFlux native WebSocketHandler không tự là STOMP broker. Phải parse, validate và phân quyền mỗi message, hoặc tích hợp một STOMP giải pháp riêng có security tương ứng.

---

**Ghi nhớ:** **Fetch CORS và native WebSocket thực thi ranh giới same-origin khác nhau.** Trình duyệt không dùng preflight OPTIONS/ACAO để cho JavaScript sử dụng WebSocket đã được server chấp nhận; server phải kiểm tra **Origin ngay ở handshake** để chống CSWSH. Origin validation không phải authentication, cookie SameSite không đồng nghĩa same-origin, và HTTP 101 không cấp quyền cho mọi STOMP frame. Với Spring Security, hãy bảo vệ **HTTP handshake, STOMP CONNECT/CSRF, SEND/SUBSCRIBE và quyền object/tenant**; ở WebFlux native, bảo vệ handshake và **từng message** trong handler/service.
