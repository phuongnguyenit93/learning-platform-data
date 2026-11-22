# Thời hạn phiên, mất hiệu lực phiên và trải nghiệm khi phiên hết hạn

## 1. Vì sao thời hạn phiên là cả bài toán bảo mật lẫn trải nghiệm?

Trong ứng dụng Spring Security **reactive/WebFlux** có đăng nhập biểu mẫu, việc đăng nhập thành công không có nghĩa người dùng được xác thực vĩnh viễn. Hệ thống cần quyết định **phiên có hiệu lực bao lâu**, khi nào phải **mất hiệu lực**, và cách trình duyệt hoặc API phản ứng khi phiên không còn được chấp nhận.

Một phiên sống quá lâu làm tăng rủi ro khi cookie bị đánh cắp hoặc người dùng bỏ máy không khóa. Ngược lại, phiên quá ngắn gây mất dữ liệu chưa lưu, gián đoạn thao tác và nhiều lần đăng nhập lại. Giải pháp đúng không chỉ là đặt một con số “30 phút”; còn phải hiểu *idle timeout*, lưu trữ phiên, logout/invalidate, session cookie, CSRF, phản hồi 302/401/403 và cách thông báo rõ ràng cho người dùng.

Sau bài này, bạn có thể:
- Phân biệt `WebSession`, `SecurityContext`, Reactor Context và cookie định danh phiên.
- Hiểu **thời hạn không hoạt động (idle timeout)** so với **thời hạn tuyệt đối (absolute lifetime)** và **thời gian sống cookie**.
- Cấu hình timeout cho ứng dụng Spring Boot WebFlux và nhận biết khác biệt khi dùng Spring Session.
- Giải thích `WebSession.invalidate()`, logout Spring Security và việc thu hồi hàng loạt phiên.
- Thiết kế màn hình cảnh báo, chuyển hướng đến login, lưu bản nháp an toàn và xử lý request API khi phiên hết hạn.
- Chạy ví dụ Java 17+ với Spring Boot 3.3, kiểm tra tình huống login, reuse cookie, invalidation, logout và phân quyền.
- Xác định các tình huống test cần có mà không đòi test phải “ngủ” chờ timeout trong CI.

## 2. Các đối tượng liên quan: đừng gộp mọi thứ thành “session”

~~~text
Browser                                  Spring WebFlux + Spring Security
┌────────────────────┐                   ┌─────────────────────────────────┐
│ Cookie SESSION=... │ ── HTTP request ─►│ WebSessionManager / SessionStore│
│ Không chứa password│                   │   └── WebSession                  │
└────────────────────┘                   │       ├── id                    │
                                         │       ├── lastAccessTime        │
                                         │       ├── maxIdleTime           │
                                         │       └── attributes            │
                                         │            └── SecurityContext │
                                         │                  └──Authentication
                                         └────────────────┬────────────────┘
                                                          │
                                         Reactor Context theo subscription
                                                          │
                                            Authorization / handler
~~~

| Đối tượng | Vai trò | Phạm vi |
| --- | --- | --- |
| **Session cookie** | Mang session ID để server tìm lại phiên; giá trị là bí mật cần bảo vệ | Browser ↔ server qua nhiều HTTP request |
| **`WebSession`** | Lưu trạng thái server-side, có `id`, thời điểm truy cập và thời hạn không hoạt động | Có thể tồn tại giữa request, tùy session store |
| **`SecurityContext`** | Lưu `Authentication` đại diện danh tính hiện tại | Được Spring Security nạp/lưu bằng repository phù hợp |
| **`WebSessionServerSecurityContextRepository`** | Lưu/tải SecurityContext trong WebSession | Khi sử dụng mô hình session-based |
| **Reactor Context** | Truyền SecurityContext dọc pipeline reactive, không phụ thuộc một ThreadLocal cố định | Subscription/reactive execution của request |
| **`ServerSecurityContextRepository`** | Trừu tượng cho nơi nạp/lưu authentication state | Có thể là WebSession hoặc `NoOpServerSecurityContextRepository` |
| **Spring Session** | Có thể thay WebSession store bằng Redis hoặc backend dùng chung | Tùy dependency/cấu hình, hữu ích cho nhiều instance |

### 2.1. Phiên WebFlux không phải `HttpSession` của Servlet

WebFlux dùng `org.springframework.web.server.WebSession` và `ServerWebExchange.getSession()`, không phải mặc định `jakarta.servlet.http.HttpSession` hoặc `HttpServletRequest` của Spring MVC.

Trong code reactive:

~~~java
Mono<WebSession> sessionMono = exchange.getSession();
~~~

Đây mới là publisher để truy cập session. Sau khi `flatMap` hoặc `map`, có thể gọi `session.getMaxIdleTime()`, `session.getCreationTime()`, `session.getLastAccessTime()`, `session.invalidate()`.

**Lấy một WebSession qua `getSession()` không tự động tạo một session cookie gửi đi.** Theo hợp đồng Spring Framework, session mới chỉ được *start* tường minh bằng `start()` hoặc ngầm qua việc thêm attribute, rồi được lưu phù hợp. Vì vậy không nên thêm một attribute giả vào mọi request chỉ để “đo session”: hành vi đó có thể tạo session không cần thiết.

### 2.2. Reactor Context không giúp đăng nhập tồn tại qua request mới

Khi request đang xử lý, dùng:

~~~java
Mono<String> currentName =
    ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName);
~~~

Đoạn trên là **minh họa** trong class có import `Mono`, `ReactiveSecurityContextHolder` và `Authentication`. Publisher lấy danh tính trong subscription hiện tại; khi browser gửi request kế tiếp, WebFlux phải **nạp lại security context** (thường từ WebSession) hoặc xác thực lại một token/cơ chế khác.

Sai lầm thường gặp là tưởng một `ReactiveSecurityContextHolder` “toàn cục” luôn còn giữ principal sau khi tab bị đóng, session đã hết hạn hoặc server khởi động lại.

## 3. Thời hạn không hoạt động, thời hạn tuyệt đối và thời hạn cookie

### 3.1. Idle timeout: khoảng cách từ hoạt động cuối cùng

`WebSession` có các API:

~~~java
Instant lastAccess = session.getLastAccessTime();
Duration idleLimit = session.getMaxIdleTime();
boolean expired = session.isExpired();
~~~

Quy tắc logic:

~~~text
expiresByIdle ≈ lastAccessTime + maxIdleTime
Nếu không có hoạt động hợp lệ để gia hạn trước mốc này:
  phiên không còn được session store chấp nhận.
~~~

- `maxIdleTime` là **khoảng không hoạt động tối đa** giữa lần truy cập cuối và khi phiên được xem là hết hạn.
- Khi session được truy cập ở request hợp lệ, session store có thể cập nhật `lastAccessTime`; đó là bản chất của timeout theo trạng thái hoạt động, không phải đồng hồ tuyệt đối tính từ lúc login.
- Khi request mới mang cookie của một session đã hết hạn, session manager thường không trả lại session cũ mà xử lý như phiên mới/chưa xác thực.
- Browser có thể còn giữ cookie cũ; **cookie tồn tại không bảo đảm session hợp lệ**.

Ví dụ idle timeout **15 phút**:
- 09:00 login, 09:10 có request truy cập session → mốc idle có thể lùi đến khoảng 09:25.
- Sau đó không có hoạt động, 09:27 người dùng nhấn Save → server xem session đã hết hạn.
- Trang HTML đang mở từ 09:10 vẫn nhìn thấy dữ liệu cũ cho tới khi client có request, redirect hoặc chính UI cập nhật. Server **không tự đẩy thông báo lên tab** chỉ vì hết giờ.

*Ví dụ trên là minh họa thời gian, không phải cam kết mọi request đều làm mới phiên như nhau.* Một reverse proxy, cache, WebSocket, background polling hoặc cách truy cập session thực tế có thể khiến hoạt động được tính khác dự kiến. Phải kiểm tra với stack, session store và lưu lượng thật.

### 3.2. Absolute lifetime: giới hạn tính từ lúc đăng nhập

Một chính sách bảo mật có thể yêu cầu: “Dù người dùng hoạt động liên tục, sau 8 giờ phải đăng nhập lại”. Đó là **absolute lifetime** hoặc *maximum authentication age*, **khác** với idle timeout.

`WebSession.getCreationTime()` thể hiện lúc session được tạo, nhưng **không luôn trùng thời điểm login**: một session ẩn danh có thể được tạo trước vì CSRF, saved request hoặc dữ liệu khác. Nếu chính sách là “8 giờ từ khi xác thực thành công”, hãy lưu **trusted authentication time** riêng, dùng phương án policy/reauthentication phù hợp và kiểm tra trên server.

Không coi `getMaxIdleTime()` là giải pháp tự động cho absolute lifetime. Session được giữ sống bằng truy cập thường xuyên có thể kéo dài vượt mốc tuyệt đối nếu bạn không đặt thêm chính sách.

### 3.3. Cookie lifetime không phải server-side session lifetime

Ví dụ cookie browser `Max-Age=3600` nói cookie có thể được giữ trong browser bao lâu. Nó không buộc backend giữ session 3600 giây, cũng không cam kết session backend chưa bị thu hồi.

| Hạn chế | Được kiểm soát tại | Ý nghĩa |
| --- | --- | --- |
| Idle timeout | `WebSession.maxIdleTime` / session store | Khi nào session server không còn hiệu lực do không hoạt động |
| Absolute login age | Policy authentication tùy ứng dụng/IdP | Buộc đăng nhập lại dù vẫn hoạt động |
| Cookie `Max-Age` / `Expires` | Session ID resolver, response cookie | Browser giữ định danh bao lâu |
| JWT `exp` | Token verifier theo clock/claim | Khi nào Bearer token không được chấp nhận |
| Logout/invalidate | Server logout handler/session store | Chủ động chấm dứt phiên trước timeout |

**Tránh nhầm lẫn:** `server.reactive.session.cookie.max-age` là cấu hình cookie của Boot; không thay cho `server.reactive.session.timeout`. `server.servlet.session.timeout` thuộc Servlet, không phải tham số cần dùng cho WebFlux.

## 4. Cấu hình timeout trong Spring Boot WebFlux

### 4.1. Cấu hình dành cho WebFlux thông thường

Với Spring Boot **3.3.13** và WebFlux dùng WebSession mặc định, đặt trong `src/main/resources/application.properties`:

~~~properties
# Timeout không hoạt động của WebSession: 2 phút (chỉ để demo).
server.reactive.session.timeout=2m

# Cookie chỉ để minh họa; không phải cơ chế timeout trên server.
server.reactive.session.cookie.http-only=true
server.reactive.session.cookie.same-site=lax
~~~

Trong ứng dụng dùng HTTPS ở production, nên bật `server.reactive.session.cookie.secure=true` khi reverse proxy và cấu hình HTTPS phù hợp; **không đặt `secure=true` trong demo local HTTP**, vì cookie Secure có thể không được browser gửi trên kết nối HTTP theo chính sách trình duyệt. Có thể thêm domain/path tùy deployment, nhưng phải cân nhắc cookie isolation và SameSite/CSRF trước khi đổi.

Cấu hình mặc định của `server.reactive.session.timeout` trong Spring Boot 3.3 là **30 phút** khi không ghi đè. Đặt `2m` ở đây để người học dễ thử hành vi hết hạn; không phải khuyến nghị thời hạn cố định cho mọi hệ thống.

**Cách kiểm tra thực tế**: trong handler chỉ dành cho người dùng đã đăng nhập, có thể đọc `session.getMaxIdleTime().toSeconds()`. Nếu kết quả không như cấu hình, hãy kiểm tra có `Spring Session`/custom `WebSessionManager`/custom session store đang thay thế mặc định hay không.

### 4.2. Với Spring Session/WebFlux dùng Redis hoặc store khác

Khi thêm Spring Session cho WebFlux, một `WebSessionManager` khác có thể dùng `ReactiveSessionRepository`. Ứng dụng nhiều instance có thể nhờ đó chia sẻ trạng thái session, thay vì mất phiên khi request chuyển node.

Spring Boot/Spring Session cung cấp `spring.session.timeout` để cấu hình timeout ở trường hợp Spring Session được auto-configure. **Không giả định** `server.reactive.session.timeout` luôn thắng mọi repository tùy biến; đọc cấu hình, precedence thực tế và xem `getMaxIdleTime()` hoặc metadata store.

Không nhầm hướng dẫn dùng `@EnableRedisHttpSession` (Servlet) với `@EnableRedisWebSession` (reactive). Với Spring Session auto-configuration, việc thêm annotation thủ công có thể khiến Boot back off. Chỉ cấu hình repository theo đúng cách app đang dùng, không bật trùng nhiều cơ chế quản lý session.

### 4.3. Thay max idle timeout cho một phiên cụ thể

API WebFlux:

~~~java
exchange.getSession()
    .doOnNext(session ->
        session.setMaxIdleTime(Duration.ofMinutes(15)))
    .then();
~~~

Đây là **đoạn minh họa**, không phải endpoint hoàn chỉnh. `setMaxIdleTime` thay timeout **cho session đó**, còn repository quyết định cách lưu. Hãy dùng trong trường hợp có yêu cầu chính sách phân biệt phiên, không thay đổi tùy tiện ở mọi request.

Lưu ý `.then()` trên `Mono` trả `Mono<Void>` để framework thực thi; đừng gọi `block()` trong event loop. Một phiên cần chính sách thời gian tồn tại tuyệt đối vẫn phải có xử lý riêng.

## 5. Khi nào một phiên “mất hiệu lực”?

Các sự kiện khác nhau có thể làm mất khả năng dùng lại danh tính:

| Sự kiện | Cơ chế điển hình | Kỳ vọng của request kế tiếp |
| --- | --- | --- |
| Không hoạt động quá `maxIdleTime` | Session store coi WebSession expired | Không tải được authentication cũ, phải xác thực lại |
| User chủ động logout | Spring Security logout handler xóa context, tùy cấu hình invalidate WebSession | Cookie/session cũ không còn dùng đăng nhập được |
| Code gọi `WebSession.invalidate()` | Xóa toàn bộ trạng thái phiên khỏi store | Phải đăng nhập lại để có session authenticated mới |
| Session store mất dữ liệu, restart app dùng in-memory store | Không còn bản ghi session cũ | Có thể bị xem là anonymous |
| Account bị vô hiệu hóa/đổi mật khẩu/thu hồi quyền | **Không nhất thiết tự invalidate mọi session** | Cần thiết kế thu hồi/refresh quyền và session phù hợp |
| Thay session ID | `WebSession.changeSessionId()` | ID cũ bị thay đổi; session có thể vẫn hợp lệ dưới ID mới |
| Token JWT hết hạn | Kiểm tra `exp`/decoder của resource server | Bị từ chối token; không phải WebSession tự hết hạn |

### 5.1. `WebSession.invalidate()`

`WebSession.invalidate()` trả `Mono<Void>` và là API **chủ động làm session hiện tại mất hiệu lực**. Nó xóa session khỏi storage theo hợp đồng, khác với chỉ xóa một attribute.

~~~java
Mono<Void> invalidateCurrentSession(ServerWebExchange exchange) {
    return exchange.getSession()
        .flatMap(WebSession::invalidate);
}
~~~

Phương thức trên là **minh họa** trong class có import `ServerWebExchange`, `WebSession` và `Mono`. Không dùng `session.getAttributes().clear()` như phương án thay thế hoàn toàn: xóa attributes khác với invalidate session, thay session ID/cookie, và không bao quát logout integration.

**Cảnh báo:** `invalidate()` trong request đang xử lý không thể “thu hồi” tất cả response vốn đã được gửi. Authentication hiện tại cũng có thể vẫn tồn tại trong Reactor Context của **request đang chạy**. Điều quan trọng là **request kế tiếp** không khôi phục được context cũ. Với hệ thống có thao tác nhạy cảm chạy lâu, phải thiết kế kiểm tra hủy quyền/phiên gần biên commit và xử lý race condition.

### 5.2. Logout của Spring Security reactive

Với Spring Security WebFlux, GET `/logout` thường hiện trang xác nhận; POST `/logout` có CSRF token hợp lệ mới thực hiện logout theo flow mặc định.

Theo tài liệu Spring Security reactive:
- Logout mặc định xóa thông tin khỏi `ServerCsrfTokenRepository` và `ServerSecurityContextRepository`, rồi redirect về login.
- Nếu muốn **invalidate toàn bộ WebSession** một cách tường minh, cấu hình `WebSessionServerLogoutHandler`.
- Khi tùy biến logout handler, cần giữ bước xóa `SecurityContext`, không chỉ xóa cookie ở trình duyệt.
- Việc logout trên ứng dụng **không đồng nghĩa** logout khỏi tất cả SSO Identity Providers, tất cả thiết bị hoặc thu hồi mọi JWT; các cơ chế đó cần tích hợp riêng.

Ví dụ:

~~~java
DelegatingServerLogoutHandler logoutHandler =
    new DelegatingServerLogoutHandler(
        new SecurityContextServerLogoutHandler(),
        new WebSessionServerLogoutHandler()
    );

http.logout(logout ->
    logout.logoutHandler(logoutHandler));
~~~

Đây là đoạn cấu hình minh họa ở cấp `ServerHttpSecurity`, không phải chương trình độc lập. Hai handler lần lượt xử lý xóa security context và invalidate WebSession. Dự án hoàn chỉnh bên dưới dùng cùng cấu hình.

### 5.3. `changeSessionId()` không phải invalidate

`WebSession.changeSessionId()` trả `Mono<Void>`, dùng để sinh ID mới cho **cùng một phiên**. Nó có thể là một phần bảo vệ **session fixation** lúc login. Nhưng gọi thay ID không xóa authentication/attributes và **không phải logout**.

Khi cấu hình session fixation protection, hãy để cơ chế Spring Security/Framework được hỗ trợ quản lý và kiểm thử cookie cũ/mới; tránh tự sinh session ID, đưa ID vào URL hoặc log.

## 6. Trải nghiệm khi phiên hết hạn: browser khác API

### 6.1. Trình duyệt dùng form login

Với `formLogin` và trang HTML protected:
1. User login và được lưu context vào WebSession.
2. Người dùng mở `/account` và xem nội dung.
3. Sau khoảng không hoạt động vượt timeout, session server hết hiệu lực.
4. Người dùng click link hoặc reload protected URL; Spring Security không khôi phục được `Authentication`.
5. Authentication entry point của form login thường đưa người dùng sang trang đăng nhập (HTTP 302).
6. Sau khi login lại, saved request có thể được phục hồi tùy cách cấu hình; **không đảm bảo** mọi POST bị thất bại tự động được gửi lại an toàn.

**Trang đang hiển thị không tự biến mất** khi backend hết session; timeout thường được phát hiện khi có request mới. Điều này quan trọng với form dài hoặc màn hình quản trị đang mở.

### 6.2. Fetch/AJAX/SPA: không suy ra từ body HTML

Nếu một API vốn trả JSON nhưng bị form-login entry point chuyển hướng 302 tới `/login`, browser `fetch` có thể tự theo redirect và cuối cùng nhận **200 với body HTML**. Frontend nếu gọi `response.json()` có thể báo lỗi parse thay vì thông báo “Phiên hết hạn”.

Trong một ứng dụng kết hợp browser + API, hãy thiết kế riêng:
- HTML navigation: redirect tới login phù hợp.
- API `/api/**`: trả **401 Unauthorized** có body JSON an toàn khi thiếu/hết authentication; `403 Forbidden` khi đã đăng nhập nhưng thiếu quyền.
- Dùng entry point hoặc các security chains/exception handlers được cấu hình tương ứng, tránh để frontend đoán từ `Location`/text của trang HTML.
- Không sử dụng trạng thái 419 “Session Expired” không chuẩn như một giả định mặc định của Spring Security.

Ví dụ hợp đồng JSON do **ứng dụng tự định nghĩa** (không phải Spring Security tự sinh):

~~~json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Phiên đăng nhập không còn hợp lệ."
}
~~~

Nếu muốn phân biệt **chưa từng login** với **session trước đây đã hết hạn**, backend cần thêm tín hiệu có độ tin cậy thích hợp. Không suy luận chắc chắn “timeout” chỉ từ mã 401: cookie có thể bị xóa, tài khoản bị logout, browser chặn cookie hoặc session store có sự cố. Tránh tiết lộ nguyên nhân nhạy cảm trong API response.

### 6.3. UX countdown: server luôn là nguồn sự thật

Có thể hiện thông báo:

> “Bạn có thể cần đăng nhập lại nếu không còn hoạt động. Hãy lưu thay đổi trước khi phiên kết thúc.”

Nhưng đồng hồ trên frontend thường **chỉ là dự báo**. Nó không biết chính xác `lastAccessTime` server, các request từ tab khác, heartbeat hoặc xử lý store. Vì vậy:
- Không hiển thị giây đếm ngược như một sự thật bảo đảm nếu không có cơ chế đồng bộ server-side.
- Không gửi heartbeat liên tục chỉ để giữ session mãi mãi mà không có yêu cầu nghiệp vụ/consent rõ ràng.
- Khi có hoạt động khác, thông điệp có thể không còn chính xác; cân nhắc hiển thị mốc dự kiến kèm ý “có thể”.
- Với ứng dụng nhiều tab, đồng bộ trạng thái đăng xuất/hết phiên qua sự kiện client phù hợp, nhưng **backend vẫn kiểm quyền ở mọi request**.
- Nếu sản phẩm có thời hạn tuyệt đối, giao diện phải thể hiện chính sách riêng; hoạt động người dùng không làm kéo dài mốc tuyệt đối.

### 6.4. Giữ dữ liệu chưa lưu đúng cách

Những thao tác nhạy cảm/biểu mẫu dài cần chiến lược trước khi timeout:

- Autosave ở server **khi phiên vẫn hợp lệ**, trong giới hạn quyền và yêu cầu người dùng.
- Với draft phía client, chỉ lưu thông tin được phép, hạn chế lưu PII/credentials vào `localStorage`. Có thể dùng bộ nhớ tạm hoặc encrypted storage phù hợp chính sách nhưng không xem encryption client là giải pháp tuyệt đối cho XSS.
- Khi request Save trả 401, dừng việc coi là “lưu thành công”; giữ nội dung ở trạng thái chưa lưu, thông báo rõ và cho login lại.
- Sau login lại, xác nhận owner/tenant của draft trước khi gửi lại.
- Không tự replay một POST thanh toán/đặt hàng chỉ vì login lại: nguy cơ thao tác trùng, double-submit; dùng idempotency key và xác nhận cần thiết.
- Tránh giữ secret/form password trong log, history hoặc URL.

### 6.5. Chuyển hướng an toàn sau khi login lại

Nếu UI muốn trở lại trang đang xem, chỉ dùng đường dẫn nội bộ đã kiểm tra. Không chấp nhận tùy ý `returnUrl=https://attacker.example` từ query rồi redirect, vì có thể tạo **open redirect**. Đảm bảo route trở về hợp lệ với user mới được xác thực; **không mở lại dữ liệu của user trước** nếu đã thay tài khoản.

## 7. Dự án chạy được: WebFlux, form login, timeout và invalidation

Ví dụ Java **17+**, Gradle 8.x, **Spring Boot 3.3.13** với Spring Security reactive. Phiên bản được cố định phục vụ minh họa API; trong production hãy dùng phiên bản đang được hỗ trợ và chạy test tương ứng.

Ý tưởng:
- Trang `/public` cho anonymous.
- `/account` và `/api/session-info` yêu cầu đăng nhập.
- `/admin` yêu cầu `ROLE_ADMIN`.
- `POST /demo/invalidate` giúp **mô phỏng chủ động mất session** cho mục đích học mà không cần chờ 2 phút; URL này **không được giữ ở production**.
- `POST /logout` sử dụng logout Spring Security và invalidate WebSession.
- Cấu hình idle timeout 2 phút; test kiểm tra **cấu hình timeout** và **hiệu quả invalidation**, không đánh tráo hai điều đó thành test clock expiry.
- Tất cả POST có CSRF protection; không tắt CSRF để “chạy được”.

### 7.1. Cấu trúc

~~~text
webflux-session-lifecycle/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── SessionLifecycleApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/
    │       └── application.properties
    └── test/java/demo/
        └── SessionLifecycleTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-session-lifecycle'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Vì đây là WebFlux, không thêm `spring-boot-starter-web` chỉ để có login page. Spring Security WebFlux dùng `ServerHttpSecurity`/`SecurityWebFilterChain`, không dùng `HttpSecurity`/`HttpSession` của Servlet.

### 7.2. Cấu hình phiên

`src/main/resources/application.properties`:

~~~properties
# Demo: quá 2 phút không hoạt động thì session bị coi là hết hạn.
server.reactive.session.timeout=2m

# Cookie session; dùng HTTPS + cookie Secure trong triển khai thật.
server.reactive.session.cookie.http-only=true
server.reactive.session.cookie.same-site=lax
~~~

`src/main/java/demo/SessionLifecycleApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionLifecycleApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig: form login, authorities và logout thật sự xóa phiên

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http,
                                   ReactiveAuthenticationManager manager) {

        DelegatingServerLogoutHandler logoutHandler =
            new DelegatingServerLogoutHandler(
                new SecurityContextServerLogoutHandler(),
                new WebSessionServerLogoutHandler()
            );

        return http
            .authenticationManager(manager)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            // Tập trung vào luồng form login + session; không dùng Basic.
            .httpBasic(basic -> basic.disable())
            .logout(logout -> logout.logoutHandler(logoutHandler))
            .build();
    }
}
~~~

**Giải thích:**
1. `ReactiveUserDetailsService` cung cấp hai tài khoản demo với BCrypt hash và authorities `ROLE_USER`/`ROLE_ADMIN`. Không sử dụng mật khẩu này trong production.
2. Manager xác minh mật khẩu; Spring Security form login thiết lập Authentication và dùng repository phù hợp cho session login.
3. `/public` là public. `/account` và `/api/session-info` được bảo vệ bởi `anyExchange().authenticated()`; `/admin` yêu cầu `ROLE_ADMIN`.
4. `formLogin(...)` cho phép Spring Security xử lý `POST /login`, không cần tự viết controller nhận password.
5. `httpBasic(...disable())` tránh pha hành vi 401 của HTTP Basic vào minh họa redirect form login. Đây là quyết định của demo.
6. `logoutHandler` giữ cả thao tác xóa security context và invalidate WebSession. Không giả định logout framework mặc định luôn invalidate **toàn bộ** WebSession nếu chưa cấu hình như thế.
7. **CSRF vẫn bật**. POST `/logout` và POST `/demo/invalidate` phải có CSRF token hợp lệ; `GET /logout` không phải logout trực tiếp.
8. `@EnableWebFluxSecurity` xác định hạ tầng security reactive, không tự thay việc định nghĩa rules.

### 7.4. DemoController: đọc trạng thái an toàn và chủ động invalidate

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@RestController
class DemoController {

    // Không trả session ID/cookie cho client.
    public record SessionInfo(long maxIdleSeconds) {}

    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/account")
    Mono<String> account() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .map(Authentication::getName)
            .map(name -> "Hello " + name);
    }

    @GetMapping("/admin")
    Mono<String> adminOnly() {
        return Mono.just("admin-only");
    }

    @GetMapping("/api/session-info")
    Mono<SessionInfo> sessionInfo(ServerWebExchange exchange) {
        return exchange.getSession()
            .map(s -> new SessionInfo(s.getMaxIdleTime().toSeconds()));
    }

    // CHỈ PHỤC VỤ DEMO/TEST: mô phỏng một WebSession đã mất hiệu lực
    // ngay, không phải endpoint production.
    @PostMapping("/demo/invalidate")
    Mono<String> invalidateSession(ServerWebExchange exchange) {
        return exchange.getSession()
            .flatMap(WebSession::invalidate)
            .thenReturn("session-invalidated");
    }
}
~~~

Lưu ý:
- `/api/session-info` chỉ trả **cấu hình giới hạn idle** (120 giây trong demo), **không** là số giây còn lại; request gọi endpoint này có thể được tính như một lần hoạt động.
- Không trả `session.getId()`, raw cookie, CSRF token hoặc object `Authentication` trong DTO.
- `/demo/invalidate` phải ở sau authentication và CSRF; nó cố ý kết thúc WebSession, không phải một URL logout production. Request vừa gọi nó vẫn có thể có authentication trong Reactor Context cho tới khi kết thúc, nhưng request tiếp theo không dùng được session cũ.
- Trong production, dùng Spring Security logout để đảm bảo các thao tác cleanup/redirect/middleware được thực hiện đầy đủ.
- Không dùng `session.invalidate().subscribe()` trong controller; trả lại `Mono` để WebFlux điều phối.

## 8. Chạy bằng trình duyệt và quan sát trạng thái phiên

Yêu cầu JDK 17+, Gradle 8.x, kết nối tải dependencies lần đầu. Từ thư mục dự án:

~~~bash
gradle bootRun
~~~

Hoặc `./gradlew bootRun` (Unix/macOS) / `gradlew.bat bootRun` (Windows) nếu có Gradle Wrapper.

Thử theo trình tự:
1. Mở `http://localhost:8080/public` → body `public`.
2. Mở `http://localhost:8080/account` trong trình duyệt chưa đăng nhập → thường được redirect tới `/login`.
3. Đăng nhập bằng `reader` / `reader-pass` trên trang do Spring Security sinh. Trình duyệt tự mang CSRF token của form hợp lệ.
4. Quay tới `/account` cùng session cookie → body `Hello reader`.
5. Mở `/api/session-info` → JSON với `maxIdleSeconds` là `120`.
6. Mở `/admin` khi đang là reader → HTTP **403** vì thiếu `ROLE_ADMIN`.
7. Để trình duyệt **không gửi thêm request tương tác session** trong hơn hai phút. Sau đó reload `/account` → phải đăng nhập lại trong cấu hình mặc định, trừ khi môi trường có request nền hoặc session store/cấu hình khác làm thay đổi hành vi.
8. Login lại, thử `POST /logout` bằng form có CSRF hợp lệ. Session đang dùng phải mất quyền truy cập protected URL.
9. Nếu muốn mô phỏng mất hiệu lực **ngay**, gửi POST `/demo/invalidate` có CSRF hợp lệ khi đang đăng nhập, rồi thử `/account`. URL demo không dùng cho production.

**Chú ý:** 2 phút chỉ là thời gian **không hoạt động**. Liên tục refresh `/account` hoặc gọi `/api/session-info` có thể gia hạn thời gian; vì vậy khi đo timeout cần ngừng mọi request.

### 8.1. Về tên cookie và cách kiểm tra bằng DevTools

WebFlux in-memory session resolver mặc định thường dùng cookie `SESSION`. Trong Network tab, có thể quan sát `Set-Cookie` và cookie gửi đi ở request tiếp theo, nhưng:
- Tên cookie có thể bị đổi bởi config/reverse proxy/session store.
- **Không chép giá trị cookie vào ảnh chụp màn hình/ticket/log**: session ID là credential có giá trị.
- Cookie `HttpOnly` vẫn được trình duyệt gửi tự động; JavaScript không cần đọc ID.
- Xóa cookie browser có thể khiến client mất khả năng tìm session, nhưng **không chắc đã vô hiệu session server-side**. Để logout đúng cần gọi logout/invalidation phía server.

### 8.2. Vì sao curl POST /logout thường trả 403?

Khi CSRF bật, một request đơn giản như:

~~~bash
curl -i -X POST http://localhost:8080/logout
~~~

không có CSRF token hoặc session authentication hợp lệ nên **không phải phép thử logout đúng**. Hãy dùng browser form có token do Spring Security cung cấp, hoặc dùng `WebTestClient` cùng `spring-security-test` như mục sau. Không tắt CSRF để “sửa” một phép thử thiếu điều kiện.

## 9. Kiểm thử tích hợp: session còn hiệu lực và mất hiệu lực

Ta sẽ kiểm tra hành vi thực tế bằng Spring Security Test + `WebTestClient`, không chờ thật 120 giây trong mọi test. Tương tự bài toán production, nên có test cấu hình thời hạn riêng và test hậu quả của invalidation/logout riêng.

`src/test/java/demo/SessionLifecycleTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SessionLifecycleTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    // Trả về ID session để kiểm tra ở test, KHÔNG log hoặc trả qua API thật.
    private String loginAndGetCookie(String username, String password) {
        EntityExchangeResult<Void> login = client.mutateWith(csrf())
            .post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", username)
                .with("password", password))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectBody().isEmpty();

        ResponseCookie cookie = login.getResponseCookies().getFirst("SESSION");
        assertThat(cookie).as("session cookie after login").isNotNull();
        return cookie.getValue();
    }

    @Test
    void anonymousCanVisitPublicButIsRedirectedFromAccount() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");

        client.get().uri("/account")
            .header(HttpHeaders.ACCEPT, MediaType.TEXT_HTML_VALUE)
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueMatches("Location", ".*/login.*");
    }

    @Test
    void loginPersistsAuthenticationForNextRequest() {
        String session = loginAndGetCookie("reader", "reader-pass");

        client.get().uri("/account")
            .cookie("SESSION", session)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("Hello reader");
    }

    @Test
    void configuredMaxIdleTimeIsNotRemainingSeconds() {
        String session = loginAndGetCookie("reader", "reader-pass");

        client.get().uri("/api/session-info")
            .cookie("SESSION", session)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.maxIdleSeconds").isEqualTo(120);
    }

    @Test
    void logoutInvalidatesSessionAndOldCookieNoLongerAuthenticates() {
        String session = loginAndGetCookie("reader", "reader-pass");

        client.mutateWith(csrf())
            .post().uri("/logout")
            .cookie("SESSION", session)
            .exchange()
            .expectStatus().is3xxRedirection();

        client.get().uri("/account")
            .cookie("SESSION", session)
            .header(HttpHeaders.ACCEPT, MediaType.TEXT_HTML_VALUE)
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void explicitInvalidationAlsoRemovesAccessOnNextRequest() {
        String session = loginAndGetCookie("reader", "reader-pass");

        client.mutateWith(csrf())
            .post().uri("/demo/invalidate")
            .cookie("SESSION", session)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("session-invalidated");

        client.get().uri("/account")
            .cookie("SESSION", session)
            .header(HttpHeaders.ACCEPT, MediaType.TEXT_HTML_VALUE)
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void csrfIsRequiredToInvalidateViaPost() {
        String session = loginAndGetCookie("reader", "reader-pass");

        client.post().uri("/demo/invalidate")
            .cookie("SESSION", session)
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/account")
            .cookie("SESSION", session)
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void validSessionStillNeedsTheRightRole() {
        String reader = loginAndGetCookie("reader", "reader-pass");
        client.get().uri("/admin")
            .cookie("SESSION", reader)
            .exchange()
            .expectStatus().isForbidden();

        String admin = loginAndGetCookie("admin", "admin-pass");
        client.get().uri("/admin")
            .cookie("SESSION", admin)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-only");
    }
}
~~~

**Lý giải các test:**
- `bindToApplicationContext` + `springSecurity()` dựng WebFlux Security WebFilters trong mock server; không cần chạy server mạng thật cho những test này.
- `mutateWith(csrf())` là hỗ trợ test gắn CSRF token hợp lệ; **không disable CSRF**.
- Sau POST login thành công, test lấy cookie `SESSION` của phiên demo rồi gửi lại trên GET request tiếp theo.
- Test logout gửi POST cùng cookie và CSRF; sau đó thử lại **cookie cũ** để kiểm tra không còn authentication.
- Test explicit invalidation có cùng kết quả trên request tiếp theo mà không cần ngủ chờ 2 phút.
- Test thiếu CSRF bảo đảm không có cách kết thúc phiên bằng POST không được bảo vệ trong demo.
- Test role kiểm tra session hợp lệ **không** đồng nghĩa có quyền ADMIN.
- Nếu đổi session resolver tên cookie, phải điều chỉnh test theo cấu hình thực tế. Không hard-code giả định rằng mọi triển khai WebFlux dùng `SESSION`.

Chạy:

~~~bash
gradle test
~~~

Nếu có Gradle Wrapper, dùng `./gradlew test` / `gradlew.bat test`. Kỳ vọng **bảy** phương thức test pass và exit code Gradle bằng 0; stdout/log chi tiết tùy môi trường. Mã được biên soạn để có thể chạy với những dependency liệt kê, nhưng kết quả cuối cùng vẫn phải được xác nhận bằng việc chạy test trong dự án thực tế.

### 9.1. Vì sao đây chưa phải test “hết hạn theo đồng hồ”?

Test `configuredMaxIdleTimeIsNotRemainingSeconds` kiểm tra tham số giới hạn **120 giây**. Test `explicitInvalidation...` chứng minh trạng thái session **đã bị invalidate** làm mất quyền đăng nhập ở request sau.

Chúng **không** chứng minh rằng session sẽ tự hết hạn chính xác sau 120 giây trong môi trường production. Muốn kiểm thử thời gian thật:
- Cấu hình một test profile dùng timeout rất ngắn và session store độc lập, hoặc dùng clock có thể điều khiển trong implementation của store.
- Đảm bảo không có background request làm mới `lastAccessTime`.
- Kiểm tra request ngay trước và sau mốc timeout có biên sai số hợp lý, tránh sleep cố định làm CI chập chờn.
- Nếu dùng Redis, kiểm tra thêm TTL, chênh lệch thời gian, cleanup và hoạt động khi node chuyển.
- Không suy ra “đã test timeout” chỉ từ một lần gọi `invalidate()`.

## 10. Quy trình xử lý khi session thực sự hết hạn

### 10.1. Với server-rendered HTML

~~~text
GET /account + session cookie cũ
    └── SessionStore không tìm được context hợp lệ
          └── Chưa xác thực
                └── Form login entry point
                      └── 302 /login
                            └── User đăng nhập lại
                                  └── GET /account được cấp phép nếu có quyền
~~~

Hành vi redirect cụ thể tùy `ServerAuthenticationEntryPoint`, success handler và saved request. **Không** mặc định sẽ đến một trang `/session-expired`; đó là UX tùy biến cần tự xây.

### 10.2. Với API/SPA

Quy trình khuyến nghị ở phía client:
1. Nhận HTTP **401** từ API theo hợp đồng đã định nghĩa.
2. Đánh dấu phiên phía UI là không hợp lệ, ngừng gọi những API cần auth với credentials cũ.
3. Hiển thị thông báo lịch sự: “Phiên đăng nhập đã kết thúc. Vui lòng đăng nhập lại để tiếp tục.”
4. Giữ dữ liệu chưa lưu **trong bộ nhớ an toàn** nếu chính sách cho phép, không lưu password/token vào bộ nhớ lâu dài.
5. Chuyển tới login theo URL nội bộ đã kiểm tra, không nhận redirect tùy ý từ bên ngoài.
6. Sau login, xác nhận user/tenant hiện tại phù hợp với bản nháp trước khi gửi lại.
7. Nếu request có tác động không idempotent, yêu cầu xác nhận hoặc cơ chế chống gửi trùng.

Phân biệt **401** (thiếu/chưa hợp lệ authentication) với **403** (đã auth nhưng thiếu quyền, hoặc CSRF filter từ chối). Không dùng thông báo “Phiên hết hạn” cho mọi 403.

### 10.3. Thiết kế cảnh báo trước hết phiên

Nếu muốn cảnh báo sau khoảng 10 phút không tương tác:
- Có thể theo dõi hoạt động **trong tab** và hiển thị lời nhắc dự đoán; không khẳng định chính xác backend còn bao nhiêu giây.
- Có thể cung cấp API “session status” chỉ cho user đang auth, nhưng việc gọi API cũng có thể được tính là hoạt động và vô tình **gia hạn** idle timeout. Cần đánh giá trước khi triển khai polling.
- Nút “Tiếp tục phiên” phải thực hiện một request hợp lệ, được server xác thực, không chỉ reset biến đếm ở client.
- Với ứng dụng ngân hàng/quản trị dữ liệu nhạy cảm, không cho phép gia hạn vô hạn nếu có **absolute lifetime**; yêu cầu reauthentication khi cần.
- Nếu mở nhiều tab hoặc thiết bị, đồng bộ UI để tránh một tab hiển thị user cũ sau logout ở tab khác.

## 11. Vấn đề sản xuất: nhiều instance, cập nhật quyền và sự cố mạng

### 11.1. Môi trường nhiều server

Nếu dùng in-memory WebSession store:
- Redeploy/restart instance có thể làm mất phiên.
- Request tới node khác không nhất thiết có bản ghi phiên tương ứng.
- Sticky session chỉ giảm một phần triệu chứng, không thay mô hình lưu phiên bền vững.

Với nhiều instance, cân nhắc Spring Session WebFlux và `ReactiveSessionRepository` backed by Redis hoặc store thích hợp. Đánh giá timeout, TTL, độ trễ, retry, khả năng mất kết nối, security của Redis và xóa phiên khi logout. Nếu repository lỗi, phải chọn chính sách **fail closed** cho tài nguyên nhạy cảm thay vì tự cấp quyền vì store không đọc được.

### 11.2. Logout một thiết bị khác logout mọi thiết bị

`WebSession.invalidate()` giải quyết **phiên hiện tại**. Nhu cầu “đăng xuất tất cả thiết bị” đòi hệ thống quản lý liên kết account ↔ session IDs hoặc session index và quyền thu hồi; không thể đạt được chỉ bằng `getSession().invalidate()` trên request hiện tại.

Tương tự, đổi mật khẩu hoặc disable account không chắc tự xóa mọi security context đã có trong session. Nếu policy yêu cầu thu hồi ngay, phải chủ động invalidation hoặc kiểm chứng lại trạng thái/authority ở các thao tác được bảo vệ.

### 11.3. OAuth2/OIDC, JWT và WebSocket

- OAuth2/OIDC login có thể có **phiên ứng dụng** lẫn **phiên ở Identity Provider**. Logout local không nhất thiết khiến IdP logout; phải dùng cơ chế OIDC logout/back-channel khi cần và đã được cấu hình.
- JWT stateless có `exp` và cơ chế verify riêng. `WebSession.invalidate()` không thu hồi token Bearer đã phát; cần TTL ngắn, revoke list/token introspection hoặc thiết kế token riêng.
- WebSocket có vòng đời kết nối riêng. Session hết hạn khi không có HTTP request **không luôn tự đóng một kết nối WebSocket đang mở**. Với hành động nhạy cảm, kiểm tra authorization tại message boundary và thiết kế reconnect/revocation policy.

### 11.4. Khác biệt giữa lỗi mạng và hết phiên

Người dùng bấm Lưu mà request timeout mạng không chứng minh session đã hết hạn. Tránh logout user ngay khi có một lỗi 500/503 hoặc mất mạng tạm thời. Frontend cần tách:
- 401 rõ ràng theo hợp đồng API → yêu cầu xác thực lại.
- 403 → thiếu quyền hoặc CSRF (phải phân loại).
- 5xx/network timeout → có thể retry an toàn/idempotent hoặc thông báo sự cố, không coi chắc chắn là session expired.
- Redirect HTML từ form entry point → xử lý ở luồng navigation, không giả định là JSON API.

## 12. Sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Dùng `server.servlet.session.timeout` cho WebFlux | Thuộc Servlet stack, có thể không tác dụng | Dùng `server.reactive.session.timeout` cho WebFlux Boot mặc định |
| Coi cookie `Max-Age` là idle timeout backend | Cookie có thể còn nhưng session server đã hết hạn | Phân biệt cookie TTL và WebSession maxIdleTime |
| Coi maxIdleTime là thời hạn tuyệt đối từ lúc login | Request hoạt động có thể gia hạn idle timeout | Thiết kế thêm absolute authentication age |
| Tự tạo session ở mỗi GET công khai để đo người dùng | Lãng phí session, có thể tạo cookie không cần | Chỉ tạo/lưu session khi thực sự có state |
| Đặt JavaScript timer bằng 30 phút rồi coi nó là sự thật | Các tab/request/store có trạng thái riêng | Coi timer là dự báo; server quyết định |
| Poll heartbeat 5 giây vô hạn | Giữ session sống ngoài ý muốn | Chỉ dùng khi nghiệp vụ có quy tắc explicit và có giám sát |
| Xóa cookie browser để “logout” | Bản ghi server vẫn có thể tồn tại | POST logout có CSRF, xóa context/invalidate session |
| Chỉ thay session ID để chấm dứt phiên | `changeSessionId` không xóa dữ liệu | `invalidate` hoặc logout chuẩn |
| Tự gọi `subscribe()` với `invalidate()` | Rời vòng đời request và có thể chưa hoàn thành | Trả `Mono` qua WebFlux |
| Lấy `SecurityContextHolder` ThreadLocal trong WebFlux | Không đảm bảo cùng thread | Dùng `ReactiveSecurityContextHolder` |
| Tưởng 403 luôn là session hết hạn | 403 có thể do thiếu quyền hoặc CSRF | Phân biệt authN/authZ/CSRF |
| Tưởng 302 luôn là login thành công | Redirect có thể là mời đăng nhập hay báo lỗi | Kiểm tra Location, session, request sau |
| Dùng form login mặc định cho JSON API nhưng parse response như JSON | Fetch có thể theo 302 tới HTML | Dành entry point 401 + JSON cho API |
| Đẩy bản nháp thanh toán lại ngay sau login | Nguy cơ double charge/duplicate action | Idempotency key, xác nhận và kiểm soát giao dịch |
| Tự động replay một POST lỗi do timeout | Trạng thái POST trước có thể đã commit | Kiểm tra idempotency/trạng thái backend |
| Assume logout local cũng revoke JWT/IdP sessions | Hệ thống xác thực ngoài có lifecycle khác | Thiết kế revoke/token logout/SSO logout riêng |
| Gửi session ID trong log/URL | Lộ quyền truy cập | Cookie HttpOnly/Secure/SameSite phù hợp, TLS, lọc log |
| Quên test sau invalidate | Có thể vẫn tải lại authentication cũ | Gửi lại cookie cũ và assert protected route bị chặn |

## 13. Bài tập và đáp án

1. **`WebSession.getMaxIdleTime()` đo gì?** Khoảng không hoạt động tối đa từ lần truy cập gần nhất trước khi session hết hạn, không phải số giây còn lại tại thời điểm gọi.
2. **Phiên 15 phút idle, request ở phút 10 có thể gây điều gì?** Cập nhật lastAccessTime và lùi mốc hết hạn, nếu store tính request đó là hoạt động hợp lệ.
3. **Đặt `server.reactive.session.cookie.max-age=1h` có đảm bảo session sống 1h không?** Không. Đó là thời hạn cookie ở browser, khác session backend.
4. **Cấu hình Boot WebFlux 3.3 đúng để idle timeout 10 phút?** `server.reactive.session.timeout=10m` nếu dùng WebFlux session manager mặc định.
5. **Vì sao `server.servlet.session.timeout` không đúng với bài này?** Nó thuộc stack Servlet/`HttpSession`.
6. **Phân biệt `WebSession.invalidate()` và `changeSessionId()`?** Invalidate làm mất hiệu lực session; changeSessionId chỉ đổi ID của phiên có thể vẫn hợp lệ.
7. **Sau logout một tab, WebSession của thiết bị khác có tự hết hạn không?** Không nhất thiết. Logout toàn thiết bị cần cơ chế server-side riêng.
8. **Vì sao cần `WebSessionServerLogoutHandler` khi muốn xóa cả WebSession?** Vì logout mặc định tập trung xóa security context/CSRF; muốn invalidate WebSession toàn bộ phải cấu hình rõ như tài liệu reactive.
9. **Phiên hết nhưng trình duyệt vẫn thấy trang cũ, có mâu thuẫn không?** Không. Server kiểm tra khi request tới; HTML cũ vẫn nằm trong bộ nhớ/tab.
10. **Với form login, request protected khi anonymous thường nhận gì?** Redirect tới login, thường 302; tùy entry point.
11. **API JSON có nên trả trang login HTML khi session hết?** Không phù hợp; nên định nghĩa 401 JSON và xử lý ở client.
12. **HTTP 403 có nghĩa “session expired” không?** Không. Có thể đã đăng nhập nhưng thiếu role hoặc bị CSRF.
13. **Gọi `/api/session-info` liên tục có thể làm gì?** Bản thân request có thể cập nhật activity và gia hạn idle timer.
14. **Dùng JWT stateless, gọi `WebSession.invalidate()` có revoke token không?** Không.
15. **Tại sao test invalidation chưa phải test expiry theo thời gian?** Invalidation là thu hồi chủ động; chưa xác nhận idle clock vượt ngưỡng và store nhận diện hết hạn.
16. **Có nên tự gửi lại POST đặt hàng sau login?** Không trừ khi bảo đảm idempotency/kiểm soát duplicate, và user đồng ý khi cần.
17. **Muốn giới hạn tổng 8 giờ bất kể hoạt động cần gì?** Chính sách absolute lifetime/reauthentication dựa trên thời điểm xác thực tin cậy, không chỉ maxIdleTime.
18. **Vì sao cần Redis hoặc session store dùng chung cho cluster?** Để request giữa các node có thể truy cập cùng trạng thái phiên, hạn chế mất đăng nhập do đổi instance.
19. **Có nên log cookie `SESSION` để debug?** Không. Nó là bí mật có thể bị tái sử dụng để chiếm phiên.
20. **Nếu logout bị 403, điều gì cần kiểm tra trước khi tắt CSRF?** HTTP method, CSRF token, cookie của session, domain/path và cấu hình login/logout.

## 14. Checklist thiết kế và vận hành

- [ ] Quyết định rõ idle timeout, absolute authentication age và cookie policy **riêng biệt**.
- [ ] Chọn timeout theo rủi ro sản phẩm, loại thiết bị, thời gian hoàn thành công việc và yêu cầu compliance.
- [ ] Dùng `WebSession`/`ServerWebExchange` đúng stack reactive, không áp cấu hình Servlet.
- [ ] Bảo đảm session repository và authentication repository nhất quán.
- [ ] Form login dùng HTTPS, CSRF protection và session fixation defense phù hợp.
- [ ] Logout theo POST hợp lệ, xóa SecurityContext và invalidate WebSession khi yêu cầu.
- [ ] Không trả session ID, credentials, raw token hoặc password trong response/logs.
- [ ] UI có thông báo rõ ràng khi auth không hợp lệ, không đánh đồng network error với logout.
- [ ] API trả 401 có hợp đồng JSON; HTML navigation có redirect hợp lý.
- [ ] Có chiến lược bảo vệ bản nháp/saving flow trước và sau timeout.
- [ ] Không tự động replay giao dịch nhạy cảm; có idempotency.
- [ ] Kiểm thử cookie cũ sau invalidate/logout, CSRF, thiếu quyền, timeouts, nhiều tab và nhiều instance.
- [ ] Có kế hoạch xóa/revoke các phiên cũ khi reset password hoặc disable account.
- [ ] Với session lưu tập trung, kiểm tra TTL và failure policy của Redis/store.
- [ ] Giám sát số phiên, tỷ lệ auth failure/401, lỗi session store nhưng không thu thập bí mật.
- [ ] Với SSO/OIDC/JWT/WebSocket, định nghĩa cách logout/revoke cho từng cơ chế độc lập.

## 15. Tài liệu chính thức

- Spring Boot 3.3 — Common Application Properties (`server.reactive.session.timeout`, session cookies, Spring Session): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Spring Session Integration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html
- Spring Framework 6.1 — `WebSession` API (`invalidate`, `getMaxIdleTime`, `getLastAccessTime`): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebSession.html
- Spring Security — Reactive Logout và `WebSessionServerLogoutHandler`: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html
- Spring Security — Reactive WebFlux Configuration: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security — WebFlux CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Reactive WebTestClient CSRF: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Session — WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html

**Ghi nhớ:** Phiên WebFlux hết hiệu lực chủ yếu do **không hoạt động đủ lâu** (`maxIdleTime`), bị **invalidate/logout chủ động**, hoặc không còn trong session store. Cookie và UI timer không quyết định người dùng còn được xác thực. Cần thiết kế **server policy, security context, API behavior và trải nghiệm lưu dữ liệu/login lại** như những phần nhất quán của cùng một vòng đời phiên.
