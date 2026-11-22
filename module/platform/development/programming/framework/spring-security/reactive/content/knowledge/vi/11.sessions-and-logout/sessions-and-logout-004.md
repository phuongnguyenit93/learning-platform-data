# Cấu hình Secure, HttpOnly, SameSite và thời hạn cookie phiên

## 1. Bối cảnh: cookie phiên giữ vai trò gì trong WebFlux?

Ứng dụng Spring WebFlux có thể tạo `WebSession` để giữ trạng thái giữa các HTTP request. Server quản lý dữ liệu phiên, còn trình duyệt thường giữ một **cookie chứa session ID**. Với Spring Security Reactive, một số cơ chế xác thực tương tác, CSRF token hoặc thành phần nghiệp vụ có thể sử dụng WebSession. Vì vậy, cấu hình cookie phiên thuộc phần thiết kế **phiên và đăng xuất**, chứ không chỉ là trang trí HTTP header.

Một phản hồi có thể chứa:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=opaque-session-id; Path=/; Max-Age=1800; Secure; HttpOnly; SameSite=Lax
~~~

Trong đó:
- `SESSION=opaque-session-id` là **định danh phiên**, không phải bản thân password, user object hay các quyền.
- `Secure` hạn chế gửi cookie qua kết nối không bảo mật (thông thường chỉ qua HTTPS).
- `HttpOnly` hạn chế JavaScript của trang đọc cookie qua `document.cookie`.
- `SameSite` chi phối gửi cookie trong những tình huống yêu cầu same-site/cross-site.
- `Max-Age` là tuổi thọ **cookie phía trình duyệt**.
- `server.reactive.session.timeout` chi phối thời hạn không hoạt động của **WebSession phía server**, không đồng nghĩa với Max-Age.

Các thuộc tính này **không thay thế** authentication, authorization, chống CSRF, chống XSS, HTTPS hoặc việc vô hiệu hóa session khi đăng xuất. Chúng là những lớp kiểm soát khác nhau.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt cookie phiên với WebSession và security context.
2. Chọn `Secure`, `HttpOnly`, `SameSite=Strict/Lax/None` dựa trên luồng browser.
3. Hiểu `Max-Age` / `Expires`, session cookie, `maxIdleTime` và absolute session lifetime.
4. Cấu hình đúng **Spring Boot Reactive** qua `server.reactive.session.*`; không nhầm cấu hình Servlet.
5. Tự cấu hình `CookieWebSessionIdResolver` khi có nhu cầu đặc biệt.
6. Viết ví dụ Java 17+ WebFlux + Spring Security Reactive với CSRF token, cookie flags và session invalidation.
7. Kiểm tra `Set-Cookie`, thử timeout/invalidation và hiểu logout của Spring Security khác với việc chỉ xóa cookie.
8. Nhận diện rủi ro khi đặt cookie Domain/Path, HTTPS qua reverse proxy, dùng SameSite=None hoặc đánh đồng client-side TTL với thời hạn đăng nhập.

## 2. Một session gồm hai phía: ID cookie và dữ liệu server

Luồng khái niệm:

~~~text
Browser                                       Spring WebFlux server
   |                                                  |
   | POST /session/start (+ CSRF, authentication)      |
   |------------------------------------------------->|
   |                         WebSession được tạo/start |
   |                         Session store lưu dữ liệu |
   |                                                  |
   | Set-Cookie: SESSION=<opaque-id>; ...              |
   |<-------------------------------------------------|
   |                                                  |
   | GET /session/state                                |
   | Cookie: SESSION=<opaque-id>                       |
   |------------------------------------------------->|
   |                         Tìm session theo ID        |
   |                         Đọc dữ liệu đã lưu         |
   |                                                  |
   | 200 + trạng thái phiên                             |
   |<-------------------------------------------------|
~~~

Cookie có thể chỉ chứa **ID khó đoán**; nó không cần chứa toàn bộ profile hay SecurityContext. Điều này có hai hệ quả:

- Nếu attacker chiếm được **session ID đang còn hiệu lực** và server chấp nhận ID đó, họ có thể có khả năng **chiếm phiên** trong một thiết kế session-based login. Vì thế cookie phải được bảo vệ khi truyền, khi lưu, khi ghi log và khi hết hiệu lực.
- Nếu server đã **invalidate/expire** session thì một cookie cũ còn tồn tại **không tự làm hồi sinh** dữ liệu đã bị xóa. Browser có thể tiếp tục gửi ID cũ trong khoảng thời gian cookie còn tồn tại, nhưng server phải từ chối hoặc coi là phiên không hợp lệ.

### 2.1. WebSession khác SecurityContext

| Thành phần | Trách nhiệm |
| --- | --- |
| `WebSession` | Giữ session ID, attributes, creation/access time, thời hạn idle và vòng đời phiên WebFlux |
| `WebSessionStore` / Spring Session | Lưu/truy xuất dữ liệu phiên ở bộ nhớ, Redis hoặc nơi lưu được cấu hình |
| `CookieWebSessionIdResolver` | Ghi/đọc **session ID cookie** từ request/response |
| `ServerSecurityContextRepository` | Chiến lược tải/lưu **SecurityContext** cho Spring Security Reactive |
| `WebSessionServerSecurityContextRepository` | Một implementation lưu SecurityContext vào WebSession |
| `NoOpServerSecurityContextRepository` | Không lưu/tải SecurityContext qua repository giữa các request |
| `ReactiveSecurityContextHolder` | Cho phép downstream đọc security context của reactive subscription hiện tại |
| `ServerCsrfTokenRepository` | Quản lý CSRF token; có thể sử dụng WebSession riêng |

Không phải ứng dụng nào có cookie `SESSION` cũng đang dùng **session login**. Ví dụ API dùng Basic trên từng request vẫn có thể tạo WebSession chỉ để giữ CSRF token hoặc dữ liệu khác. Ngược lại, API JWT stateless có thể không tạo WebSession nào, dù Spring Security vẫn có SecurityContext cho request hiện tại.

Cookie flags là chính sách ở **lớp vận chuyển ID**. Logout phải xử lý cả tính hợp lệ của **dữ liệu session phía server** và trạng thái authentication phù hợp.

## 3. Thuộc tính Secure

`Secure` instructs trình duyệt không gửi cookie qua kết nối HTTP không bảo mật; cookie được gửi trong ngữ cảnh HTTPS phù hợp. Đây là kiểm soát quan trọng để không làm lộ session ID qua đường truyền không mã hóa.

Ví dụ:

~~~http
Set-Cookie: SESSION=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

**Không nhầm `Secure` với việc mã hóa cookie.** Cookie value vẫn là một chuỗi dữ liệu bình thường; TLS bảo vệ kênh truyền khi kết nối HTTPS. `Secure` không ngăn JavaScript trong origin sử dụng browser để gửi request có cookie, không ngăn XSS, không thay thế HSTS và không đảm bảo server xử lý session đúng.

### 3.1. Cấu hình production

Trong Spring Boot cho WebFlux:

~~~yaml
server:
  reactive:
    session:
      cookie:
        secure: true
~~~

Với production, hãy cung cấp HTTPS toàn tuyến theo trust boundary thích hợp, dùng HSTS khi hệ thống sẵn sàng, và cấu hình TLS termination/reverse proxy nhất quán. Nếu TLS kết thúc ở load balancer rồi HTTP chạy trong mạng nội bộ, đó vẫn cần là một mạng và đường tin cậy có kiểm soát; hãy tránh đưa ứng dụng ra Internet bằng HTTP.

**Thận trọng với reverse proxy:** nếu framework tự xác định độ bảo mật dựa trên scheme của request và reverse proxy báo sai, cookie có thể thiếu Secure. Việc đặt tường minh `secure: true` cho production giảm phụ thuộc vào suy đoán đó. Nếu cần xử lý `Forwarded` hoặc `X-Forwarded-*`, chỉ tin headers được **proxy đáng tin cậy** chuẩn hóa; không chấp nhận giá trị giả mạo trực tiếp từ client.

### 3.2. Local HTTP: vì sao cần profile riêng?

Demo `http://localhost:8080` thường không có TLS. Nếu cookie luôn bật Secure, trình duyệt/công cụ có thể không gửi cookie như bạn kỳ vọng trong luồng HTTP; một số browser có ngoại lệ dành cho localhost, nhưng không nên xây dựng test dựa vào ngoại lệ đó.

Cách kiểm chứng dễ hiểu là:
- **Production:** `secure: true` và HTTPS bắt buộc.
- **Local profile chạy HTTP:** `secure: false` chỉ để thí nghiệm.
- **Test production:** kiểm tra `Set-Cookie` có Secure trên response HTTPS/môi trường mock phù hợp.

Không copy local profile sang môi trường công khai hoặc tắt Secure để “chữa” lỗi proxy production.

## 4. Thuộc tính HttpOnly

`HttpOnly` yêu cầu browser không cho các API JavaScript thông thường như `document.cookie` đọc giá trị cookie. Điều này giúp giảm khả năng session ID bị đánh cắp trực tiếp qua một đoạn script độc hại trong trang.

Ví dụ:

~~~http
Set-Cookie: SESSION=opaque-id; Path=/; Secure; HttpOnly
~~~

**Điều HttpOnly KHÔNG làm:**
- Không ngăn browser tự gửi cookie cùng những request HTTP hợp lệ.
- Không ngăn JavaScript cùng origin gọi `fetch("/api/transfer", ...)` khiến browser gửi cookie.
- Không thay thế phòng chống XSS: một script độc hại có thể thực hiện hành vi trái phép mà không cần đọc cookie.
- Không giải quyết CSRF: website khác có thể gây ra request và browser có thể tự kèm cookie nếu chính sách SameSite/CSRF không ngăn.
- Không mã hóa hay ký cookie.

**Khuyến nghị:** cookie chứa ID phiên đăng nhập nên để `HttpOnly=true`. Nếu SPA cần đọc CSRF token từ một cookie riêng, có trường hợp **cookie CSRF token** cần `HttpOnly=false` theo thiết kế. Điều đó **không** có nghĩa phải tắt HttpOnly của **session ID cookie**.

## 5. Thuộc tính SameSite: Strict, Lax và None

`SameSite` là tín hiệu cho browser về việc có gửi cookie khi request được phát sinh trong ngữ cảnh **cross-site** hay không. Nó làm giảm bề mặt của một số kiểu CSRF dựa trên cookie, nhưng **không phải cơ chế kiểm soát quyền truy cập** và không thay thế CSRF token khi threat model đòi hỏi.

| Giá trị | Hành vi browser ở mức khái quát | Phù hợp khi | Rủi ro/đánh đổi |
| --- | --- | --- | --- |
| `Strict` | Hạn chế gửi cookie trong request cross-site | Ứng dụng nội bộ/nhạy cảm, luồng không cần cookie khi đi từ site khác vào | Người dùng từ link/email/IdP redirect có thể tạm “mất session” |
| `Lax` | Cho phép một số điều hướng top-level cross-site với safe method, thường GET; hạn chế nhiều POST/subresource cross-site | Nhiều website truyền thống muốn cân bằng bảo vệ và điều hướng | Không chặn mọi CSRF; GET phải không có side effects |
| `None` | Cho phép gửi cookie trong ngữ cảnh cross-site theo chính sách browser | Khi có nhu cầu cross-site được phê duyệt, ví dụ một số embedding/SSO | **Phải đi kèm Secure** trên browser hiện đại; có thể vẫn bị chính sách chặn third-party cookie |

**Same-site khác same-origin.** Hai subdomain khác origin nhưng có thể thuộc cùng một site theo định nghĩa của browser. Vì vậy, SameSite không thay kiểm soát origin, CORS, CSRF token, kiểm soát subdomain và chính sách cách ly của ứng dụng.

### 5.1. Lựa chọn mặc định có chủ đích

Đối với một ứng dụng browser thông thường:
- Bắt đầu đánh giá với `SameSite=Lax`.
- Nếu yêu cầu bảo mật cao và không cần đăng nhập/session trong luồng cross-site, cân nhắc `Strict`.
- Chỉ dùng `None` khi luồng cross-site thực sự bắt buộc; khi đó `Secure=true`, HTTPS và các biện pháp CSRF/CORS phải được thiết kế kỹ.
- Đừng dựa vào “mặc định của browser”. Khai báo rõ policy mà sản phẩm hỗ trợ, rồi kiểm tra response thật.

Khi sử dụng OAuth2/OIDC Login hoặc SSO qua redirect/cross-site POST, phải kiểm thử cookie cần thiết cho state/nonce và flow của IdP. `Strict` hoặc thay đổi cấu hình SameSite thiếu kế hoạch có thể làm gián đoạn xác thực. Từng loại cookie có thể cần policy riêng; không nên ép mọi cookie dùng một quy tắc nếu luồng thực tế khác nhau.

### 5.2. SameSite có thay CSRF token không?

Không. Đặc biệt:
- `Lax` vẫn cho phép một số request điều hướng từ site khác; endpoint GET gây side effects là lỗi nghiêm trọng.
- Những origin cùng site nhưng khác subdomain có thể nằm ngoài phạm vi bảo vệ mà bạn kỳ vọng.
- Browser behaviors, exception và kiến trúc login có thể khác nhau.
- Khi dùng `SameSite=None`, cookie có thể được gửi trong nhiều ngữ cảnh cross-site hơn.
- XSS trong origin tin cậy có thể gửi request cùng quyền người dùng.

Spring Security WebFlux có `CsrfWebFilter` và `ServerCsrfTokenRepository` để bảo vệ các HTTP methods unsafe nếu ứng dụng dùng authentication tự động gửi qua browser.

## 6. Domain, Path, Name và cookie prefixes

Ngoài ba flag cốt lõi, scope của session cookie cần được giới hạn.

- `Domain`: nếu không khai báo, cookie thường là **host-only**, giảm chia sẻ ngoài ý muốn cho subdomain. Đặt `Domain=.example.test` có thể mở phạm vi đến nhiều subdomain; dấu chấm đầu thường không còn ý nghĩa bảo mật đặc biệt trên browser hiện đại.
- `Path`: giới hạn đường dẫn browser gửi cookie. Path **không phải** biên phân quyền/bảo mật vững chắc giữa các ứng dụng chung host; không nên dùng nó thay authentication và authorization.
- `Name`: WebFlux thường dùng `SESSION` cho cookie session, nhưng có thể được đổi. Đừng nhầm với `JSESSIONID` thường thấy ở Servlet.
- Prefix `__Host-` (khi chủ định dùng): yêu cầu `Secure`, `Path=/` và **không có Domain**, giúp ràng buộc cookie với host tốt hơn trên browser hỗ trợ.
- Prefix `__Secure-`: yêu cầu `Secure`, nhưng không tự áp yêu cầu Path/Domain như `__Host-`.

Đừng đặt Domain rộng chỉ vì frontend và API có subdomain khác nhau: cùng một host cho endpoint auth hoặc thiết kế BFF có thể giảm nhu cầu chia sẻ session cookie. Nếu cần cross-origin, phải xử lý CORS, credentials và CSRF theo yêu cầu riêng.

**Cảnh báo “cookie shadowing”:** hai cookie trùng tên nhưng khác Domain/Path có thể được browser gửi cùng lúc. Ứng dụng hoặc proxy có thể chọn cookie không mong muốn. Khi đổi scope/name, cần kế hoạch xử lý cookie cũ và xác minh chính xác request header.

## 7. Max-Age, Expires, session cookie và thời hạn server

Có **ít nhất hai đồng hồ** độc lập:

1. **Cookie lifetime phía browser**: `Max-Age` / `Expires` kiểm soát browser lưu/gửi ID trong bao lâu.
2. **Session validity phía server**: `WebSession.getMaxIdleTime()` hoặc cấu hình store quyết định khoảng không hoạt động trước khi session bị coi là hết hạn.

**Không đồng nhất chúng.** Một cookie có thể chưa hết hạn trong browser nhưng server đã xóa session. Ngược lại, server có thể còn dữ liệu phiên nhưng browser đã xóa cookie nên client không còn ID để truy cập nó.

### 7.1. Max-Age và Expires

- `Max-Age=1800` yêu cầu cookie có thời hạn 1.800 giây, tính từ lúc được phát hành/thiết lập theo cách browser xử lý.
- `Max-Age=0` thường yêu cầu browser xóa cookie.
- Giá trị Max-Age âm hoặc không đặt có thể biểu thị **session cookie**, thường bị xóa khi browser session kết thúc; session restore có thể khiến cookie tiếp tục tồn tại tùy browser.
- `Expires` là một mốc thời gian tuyệt đối phía client.
- Khi cả `Max-Age` và `Expires` xuất hiện, `Max-Age` được ưu tiên theo chuẩn cookie hiện đại.

“Session cookie” (không có expiration cố định ở browser) **khác** “session của server chỉ có hiệu lực đến khi đóng tab”. Browser có thể khôi phục session, và server có timeout riêng. Không dùng “đóng browser” làm biện pháp logout chắc chắn.

### 7.2. Thời hạn không hoạt động — idle timeout

Trong Spring WebFlux:

~~~java
// API minh họa:
WebSession session = ...;
session.setMaxIdleTime(Duration.ofMinutes(10));
Duration maxIdleTime = session.getMaxIdleTime();
~~~

`maxIdleTime` là khoảng thời gian không hoạt động tối đa giữa các lần truy cập session được coi là hợp lệ theo store. Đây không phải một “absolute lifetime kể từ lúc login” bất kể hoạt động.

Ví dụ:
- 10:00 server lưu session.
- 10:08 browser gửi request có session ID hợp lệ: access time được cập nhật theo cơ chế session store.
- 10:15 session có thể vẫn hợp lệ vì mới 7 phút kể từ access, nếu policy idle = 10 phút.
- Nếu đến 10:30 không có access nào nữa, server có thể coi session hết hạn; chính xác thời điểm xóa vật lý còn tùy store/cleanup.

Không lấy thời gian vật lý mà session được dọn khỏi Redis/database làm bằng chứng duy nhất về thời điểm nó **không còn được chấp nhận**.

### 7.3. Absolute expiration là chính sách riêng

Nhiều hệ thống cần giới hạn tối đa từ lúc đăng nhập, ví dụ 8 giờ bất kể người dùng có hoạt động. `server.reactive.session.timeout` thường biểu diễn **idle timeout**, không mặc nhiên tạo absolute lifetime.

Muốn absolute lifetime cần một cơ chế riêng: lưu timestamp tạo phiên/đăng nhập, áp dụng chính sách ở request và invalidate khi quá hạn, hoặc dùng hệ thống session/token hỗ trợ absolute TTL tương ứng. Nếu dùng refresh/remember-me, phải phân biệt thời hạn của session, cookie, refresh token và access token.

### 7.4. Vì sao Max-Age không phải thời hạn authentication?

Ví dụ:
- Cookie `Max-Age=30m`.
- `WebSession` idle timeout = 10m.
- Browser không dùng session trong 11 phút.

Browser có thể vẫn gửi cookie ID nhưng server coi session hết hạn. Hành vi phù hợp là yêu cầu xác thực lại hoặc tạo session mới theo chính sách, **không** chấp nhận dữ liệu authentication cũ chỉ vì cookie chưa hết Max-Age.

Ngược lại, tăng cookie Max-Age không kéo dài tuổi thọ WebSession phía server. Mọi báo cáo “thời hạn đăng nhập” phải chỉ rõ đồng hồ nào đang được nói tới.

## 8. Cấu hình Spring Boot Reactive bằng application.yml

Spring Boot có nhóm thuộc tính **`server.reactive.session.*`** dành cho ứng dụng WebFlux. Đây là ví dụ chính sách cụ thể để học:

~~~yaml
server:
  port: 8080
  reactive:
    session:
      timeout: 10m
      cookie:
        name: SESSION
        path: /
        secure: true
        http-only: true
        same-site: lax
        max-age: 30m

spring:
  application:
    name: secure-session-cookie-demo
~~~

Ý nghĩa:
- `timeout: 10m`: WebSession idle timeout 10 phút.
- `cookie.max-age: 30m`: trình duyệt giữ cookie tối đa 30 phút theo quy tắc cookie, **không phải** server session 30 phút.
- `secure: true`: chỉ gửi cookie trong bối cảnh bảo mật thích hợp; production cần HTTPS.
- `http-only: true`: chặn việc đọc session ID bằng JavaScript thông thường.
- `same-site: lax`: hạn chế một số request cross-site nhưng vẫn hỗ trợ nhiều luồng điều hướng top-level.
- `path: /`: cookie được gửi cho các request trên toàn host theo Path; chỉ dùng khi chủ định.
- `name: SESSION`: tên cookie, không phải ID hoặc giá trị cụ thể.

**Giá trị 10m và 30m chỉ minh họa**; sản phẩm cần chọn timeout theo rủi ro, mục đích sử dụng, nhạy cảm của dữ liệu, khả năng hỗ trợ người dùng và quy định nội bộ.

### 8.1. Đúng namespace Reactive, không phải Servlet

Trong WebFlux:

~~~properties
server.reactive.session.timeout=10m
server.reactive.session.cookie.secure=true
server.reactive.session.cookie.http-only=true
server.reactive.session.cookie.same-site=lax
server.reactive.session.cookie.max-age=30m
~~~

Không dùng `server.servlet.session.cookie.*` để kỳ vọng cấu hình WebSession của WebFlux. Namespace Servlet thuộc ứng dụng Servlet/MVC; mặc dù cùng là Spring Boot, hai stack có loại session và component khác nhau.

### 8.2. Local profile để chạy HTTP trên máy cá nhân

Đặt `src/main/resources/application-local.yml`:

~~~yaml
server:
  reactive:
    session:
      cookie:
        secure: false
~~~

Chạy với profile `local` **chỉ khi test qua HTTP localhost**. Trong môi trường staging/production phải dùng HTTPS và đảm bảo `secure: true`, không kích hoạt profile `local` ngoài máy phát triển.

**Thứ tự cấu hình:** profile-specific property override giá trị ở `application.yml`. Sau khi deploy, luôn kiểm tra header `Set-Cookie` thực tế, vì bean custom `WebSessionIdResolver` hoặc Spring Session integration có thể thay đổi behavior.

### 8.3. Những thuộc tính khác

Spring Boot Reactive còn có các lựa chọn như `cookie.domain`, `cookie.path`, `cookie.name`. Không đặt Domain nếu chỉ cần host-only. Không dùng giá trị cookie name chứa dữ liệu riêng tư hoặc thông tin người dùng.

Khi dùng Spring Session (ví dụ Redis), kiểm tra tài liệu/config cụ thể vì session store, expiration và cookie ID resolver có thể do Spring Session tự cấu hình. Cấu hình session cho Servlet Redis và Reactive Redis **không phải cùng một hướng dẫn**.

## 9. Cấu hình Java qua CookieWebSessionIdResolver

Trong một ứng dụng Spring WebFlux thuần hoặc khi cần chính sách resolver tùy biến, có thể tạo một bean `WebSessionIdResolver`:

~~~java
// Đoạn cấu hình minh họa để đặt trong một @Configuration riêng.
// Không thêm bean này đồng thời với ví dụ Boot nếu chỉ cần property binding.

@Bean
WebSessionIdResolver webSessionIdResolver() {
    CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();

    resolver.setCookieName("SESSION");
    resolver.setCookieMaxAge(Duration.ofMinutes(30));

    resolver.addCookieInitializer(builder ->
            builder.path("/")
                   .secure(true)
                   .httpOnly(true)
                   .sameSite("Lax"));

    return resolver;
}
~~~

Imports cần có khi đặt trong class:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;
~~~

`setCookieMaxAge` điều khiển Max-Age của session ID cookie; `addCookieInitializer` cho phép cấu hình các thuộc tính `ResponseCookie`. **Không** có nghĩa `setCookieMaxAge(Duration.ofMinutes(30))` tự đổi `WebSession.getMaxIdleTime()`.

Nếu khai báo bean resolver, đừng vừa kỳ vọng những property `server.reactive.session.cookie.*` khác ghi đè nó lại, vừa không kiểm tra header: trong nhiều cấu hình, bean tùy biến sẽ thay auto-configured resolver. Chọn một nguồn cấu hình rõ ràng và xác minh giá trị thực tế.

## 10. Demo Java 17+ runnable: session cookie, CSRF và invalidation

Ví dụ này chạy bằng **Spring Boot 3.5.7, Java 17, Gradle**, Spring WebFlux và Spring Security Reactive. Nó mô phỏng việc tạo/dùng/xóa `WebSession`, đồng thời làm rõ rằng **HTTP Basic được kiểm tra lại mỗi request** trong ví dụ và không được lưu bằng WebSession.

Ta cố tình dùng:
- HTTP Basic với user giả lập cho các endpoint bảo vệ.
- `NoOpServerSecurityContextRepository` để authentication không lưu giữa các request.
- CSRF protection mặc định cho POST.
- WebSession chỉ giữ một marker `demoActive` và CSRF token.
- Cookie flags tại `application.yml`.
- `POST /demo/session/end` để gọi `WebSession.invalidate()`.

Do đó đây là **demo cookie/session lifecycle**, không phải ví dụ form-login session authentication đầy đủ. Phần riêng sau sẽ giải thích logout của Spring Security.

Cấu trúc:

~~~text
secure-session-cookie-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── SessionController.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-local.yml
    └── test/java/demo/
        └── SessionCookieTest.java
~~~

### 10.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'secure-session-cookie-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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

`spring-boot-starter-webflux` cung cấp WebFlux/Netty theo mặc định, `spring-boot-starter-security` thêm security chain, `spring-security-test` hỗ trợ CSRF test và authentication mock.

Spring Boot 3.5.7 là bản có thật dùng để minh họa API. Với dự án production, luôn cập nhật theo nhánh được hỗ trợ cùng các security patches được duyệt; không xem việc chọn bản minh họa này là khuyến nghị giữ nguyên mãi mãi.

### 10.2. Hai file cấu hình cookie

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  reactive:
    session:
      timeout: 10m
      cookie:
        name: SESSION
        path: /
        secure: true
        http-only: true
        same-site: lax
        max-age: 30m
~~~

`src/main/resources/application-local.yml`:

~~~yaml
server:
  reactive:
    session:
      cookie:
        secure: false
~~~

Không đổi `http-only: true` trong local profile: JavaScript không có lý do phải đọc **session ID**. Local chỉ tắt Secure vì sử dụng HTTP localhost trong bài thí nghiệm.

### 10.3. DemoApplication

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.4. Security configuration: Basic auth nhưng không lưu authentication vào WebSession

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}localpass")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }
}
~~~

Giải thích:
- Mọi endpoint của demo đều yêu cầu Basic authentication, kể cả endpoint cấp CSRF token.
- `NoOpServerSecurityContextRepository` không giữ SecurityContext cho request kế tiếp. Bản thân WebSession vẫn có thể tồn tại cho marker/CSRF.
- `csrf(Customizer.withDefaults())` duy trì CSRF protection cho POST.
- `{noop}` chỉ để học local; trong sản phẩm thật phải dùng PasswordEncoder mạnh và quản lý user/password an toàn.
- Demo sử dụng HTTP Basic thay vì login form để không phải triển khai trình tự form login trong cùng ví dụ. Việc xóa WebSession **không** làm browser quên HTTP Basic credentials.

### 10.5. Controller với start/state/end và token

`src/main/java/demo/SessionController.java`:

~~~java
package demo;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@RestController
public class SessionController {

    @GetMapping(path = "/demo/session/state",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> state(ServerWebExchange exchange) {
        return exchange.getSession()
                .map(session -> Boolean.TRUE.equals(
                        session.getAttribute("demoActive"))
                        ? "active" : "absent");
    }

    @PostMapping(path = "/demo/session/start",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> start(ServerWebExchange exchange) {
        return exchange.getSession()
                .map(session -> {
                    session.getAttributes()
                            .put("demoActive", Boolean.TRUE);
                    return "started";
                });
    }

    @PostMapping(path = "/demo/session/end",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> end(ServerWebExchange exchange) {
        return exchange.getSession()
                .flatMap(WebSession::invalidate)
                .thenReturn("ended");
    }

    @GetMapping("/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token attribute is unavailable"));
        }

        return token.map(value -> Map.of(
                "headerName", value.getHeaderName(),
                "token", value.getToken()));
    }
}
~~~

**Giải thích vòng đời:**
- `state` chỉ kiểm tra marker. Nếu session không có marker, trả `absent`. Nó không cố tạo session đăng nhập.
- `start` thêm attribute `demoActive`. Theo hợp đồng WebSession, việc thêm attribute làm session được coi là đã bắt đầu; framework lưu nó khi response được commit, do đó có thể phát session ID cookie.
- `end` gọi `invalidate()` và đợi Publisher hoàn thành rồi mới trả `ended`. Không xóa thủ công một string cookie để giả làm logout.
- `csrf` lấy `Mono<CsrfToken>` mà security filter cung cấp qua exchange attribute. Trong Spring Security 6.x, token được phát ra có thể được masking bởi request handler; client phải gửi lại đúng giá trị cấp ra.
- Không có `block()` hay `subscribe()` thủ công trong WebFlux controller.

**Đây chưa phải “logout khỏi HTTP Basic”** vì Basic credentials nằm ở browser/client. `end` chỉ xóa phiên WebSession minh họa; các endpoint vẫn yêu cầu Basic credentials trên request mới. Để có logout tài khoản thật với session-based authentication, cần cấu hình Spring Security Logout và vô hiệu authentication/session tương ứng.

## 11. Chạy demo và xem Set-Cookie

Chạy trong thư mục chứa `build.gradle`:

~~~bash
gradle bootRun --args='--spring.profiles.active=local'
~~~

Với Gradle Wrapper, thay `gradle` bằng `./gradlew` trên Linux/macOS hoặc `gradlew.bat` trên Windows. Lệnh dùng HTTP localhost, nên **local profile** đã vô hiệu Secure. Trong production sẽ không dùng profile này.

Mở terminal khác có `curl` và `jq`:

~~~bash
# 1. GET /csrf: lấy token và lưu WebSession cookie vào jar.
curl -i -u learner:localpass \
  -c session-cookies.txt \
  http://localhost:8080/csrf

# 2. Lấy JSON token vào file + ghi lại cookie.
curl -sS -u learner:localpass \
  -b session-cookies.txt -c session-cookies.txt \
  http://localhost:8080/csrf > csrf.json

# 3. Chuẩn bị tên header + token do server cấp.
HEADER="$(jq -r '.headerName' csrf.json)"
TOKEN="$(jq -r '.token' csrf.json)"

# 4. Bắt đầu phiên demo với CSRF token và cookie jar hiện tại.
curl -i -u learner:localpass \
  -b session-cookies.txt -c session-cookies.txt \
  -H "$HEADER: $TOKEN" \
  -X POST http://localhost:8080/demo/session/start

# 5. Đọc trạng thái đã lưu trong WebSession.
curl -i -u learner:localpass \
  -b session-cookies.txt \
  http://localhost:8080/demo/session/state

# 6. Invalidate WebSession, vẫn dùng Basic + CSRF token.
curl -i -u learner:localpass \
  -b session-cookies.txt -c session-cookies.txt \
  -H "$HEADER: $TOKEN" \
  -X POST http://localhost:8080/demo/session/end

# 7. Request mới: marker phiên không còn.
curl -i -u learner:localpass \
  -b session-cookies.txt \
  http://localhost:8080/demo/session/state
~~~

**Kết quả kỳ vọng khi cookie/token còn hợp lệ:**

| Thao tác | HTTP | Kết quả |
| --- | --- | --- |
| GET `/csrf` có Basic đúng | `200 OK` | JSON gồm `headerName`, `token`; có thể phát cookie phiên khi token được lưu |
| POST `/demo/session/start` có CSRF + Basic | `200 OK` | Body `started` |
| GET `/demo/session/state` cùng cookie | `200 OK` | Body `active` |
| POST `/demo/session/end` có CSRF + Basic | `200 OK` | Body `ended` |
| GET `/demo/session/state` sau invalidate | `200 OK` | Body `absent` |

**Vì sao sau invalidate vẫn 200?** Bởi ví dụ yêu cầu Basic trên **mỗi** request; client vẫn gửi `-u learner:localpass`. Đó là authentication mới của request, **không phải** WebSession cũ còn giá trị. Marker `demoActive` đã mất, đúng mục đích của thí nghiệm.

### 11.1. Kiểm tra cookie local

Ở profile local, header có thể giống:

~~~http
Set-Cookie: SESSION=<opaque-id>; Path=/; Max-Age=1800; HttpOnly; SameSite=Lax
~~~

`Secure` **không xuất hiện** vì local profile đặt `secure: false`. Dữ liệu session ID là ngẫu nhiên, không có giá trị stdout cố định. Header và thứ tự attributes có thể thay đổi; kiểm tra bằng cookie parser hoặc tìm các thuộc tính cần có, không so sánh toàn chuỗi chính xác.

### 11.2. Kiểm tra cấu hình production

Trong test/HTTPS hoặc môi trường production không bật local profile, cookie cần có `Secure`:

~~~http
Set-Cookie: SESSION=<opaque-id>; Path=/; Max-Age=1800; Secure; HttpOnly; SameSite=Lax
~~~

Nếu có `Max-Age=1800` nhưng server idle timeout là 10 phút, đừng kết luận “người dùng đăng nhập được 30 phút”. Đây là hai đồng hồ khác nhau.

### 11.3. Thiếu CSRF token trên POST

Thử:

~~~bash
curl -i -u learner:localpass \
  -b session-cookies.txt \
  -X POST http://localhost:8080/demo/session/start
~~~

Với CSRF protection mặc định, POST không có token hợp lệ thường nhận **403 Forbidden**, dù HTTP Basic đúng. Đừng disable CSRF để “chữa” 403 trong ứng dụng browser.

### 11.4. Chú ý môi trường Windows PowerShell

Các lệnh chứa `$(jq ...)` là cú pháp shell kiểu Bash; trên Windows PowerShell không dùng trực tiếp như vậy. Có thể dùng WSL/Git Bash hoặc PowerShell `ConvertFrom-Json` để lấy hai trường JSON. Nội dung bài không phụ thuộc hệ điều hành, nhưng cú pháp shell cần tương thích với terminal thực tế.

Không dùng credentials thật trong shell history hoặc log. Chỉ dùng user/password demo trên máy cá nhân để quan sát hành vi.

## 12. Kiểm thử cookie flags với WebTestClient

`WebTestClient` kết hợp `spring-security-test` có thể kiểm tra response của ứng dụng WebFlux mà không cần dùng browser. Test dưới đây cố ý dùng profile mặc định (`application.yml`, `Secure=true`), không dùng profile local, để kiểm tra cấu hình sản xuất của cookie.

`src/test/java/demo/SessionCookieTest.java`:

~~~java
package demo;

import java.util.List;
import java.util.Locale;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SessionCookieTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void sessionCookieHasIntendedSecurityAttributes() {
        EntityExchangeResult<String> result =
                client.mutateWith(csrf())
                        .post().uri("/demo/session/start")
                        .headers(h -> h.setBasicAuth(
                                "learner", "localpass"))
                        .exchange()
                        .expectStatus().isOk()
                        .expectBody(String.class)
                        .isEqualTo("started")
                        .returnResult();

        List<String> setCookieValues = result.getResponseHeaders()
                .get(HttpHeaders.SET_COOKIE);

        assertTrue(setCookieValues != null
                && !setCookieValues.isEmpty());

        String cookie = setCookieValues.stream()
                .filter(value -> value.startsWith("SESSION="))
                .findFirst().orElseThrow();

        String lower = cookie.toLowerCase(Locale.ROOT);
        assertTrue(lower.contains("secure"));
        assertTrue(lower.contains("httponly"));
        assertTrue(lower.contains("samesite=lax"));
        assertTrue(lower.contains("max-age=1800"));
        assertTrue(lower.contains("path=/"));
    }

    @Test
    void stateEndpointRejectsAnonymousRequest() {
        client.get().uri("/demo/session/state")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void startWithoutCsrfIsForbidden() {
        client.post().uri("/demo/session/start")
                .headers(h -> h.setBasicAuth(
                        "learner", "localpass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kỳ vọng:** các test kiểm tra `Secure`, `HttpOnly`, `SameSite=Lax`, `Max-Age=1800`, `Path=/`, cùng kết quả 401/403 phù hợp. Các giá trị `SESSION` trong `Set-Cookie` không được so sánh cố định vì session ID ngẫu nhiên. Đây là mã kiểm thử hướng dẫn, **không phải khẳng định đã chạy test trên máy người học**.

**Giới hạn của unit/integration mock:** việc test nhìn thấy `Secure` không chứng minh reverse proxy production đã cung cấp HTTPS đúng, và test không chứng minh browser gửi cookie đúng theo SameSite trong mọi tình huống. Cần kiểm thử network/browser thật, TLS termination và cookie policy ở môi trường deployment.

Nếu một môi trường Spring Session thay resolver hoặc cookie writer, test có thể cho thấy hành vi khác: đó là lý do nên kiểm tra `Set-Cookie` trên **ứng dụng triển khai thực tế**, không chỉ nhìn YAML.

## 13. Session timeout, ghi đè runtime và logout

### 13.1. Thay idle timeout cho một WebSession riêng

Nếu nghiệp vụ muốn phiên có thời gian idle ngắn hơn mặc định:

~~~java
// Snippet minh họa bên trong một reactive handler:
return exchange.getSession()
        .map(session -> {
            session.setMaxIdleTime(Duration.ofMinutes(5));
            session.getAttributes().put("sensitiveFlow", Boolean.TRUE);
            return "started-sensitive-flow";
        });
~~~

Cần import `java.time.Duration`; đây là đoạn ghép vào method xử lý request, không phải một Java class độc lập. Chỉnh `maxIdleTime` của session không làm thay đổi `Max-Age` của cookie đã cấp và không tạo absolute timeout.

### 13.2. Đăng xuất phải xử lý cả server và client

Trong **session-based authentication**, logout phù hợp thường:
1. Xác định request logout hợp lệ, có CSRF protection khi cần.
2. Xóa/vô hiệu security context theo cơ chế authentication.
3. **Invalidate WebSession** hoặc loại bỏ trạng thái session authentication ở store phù hợp.
4. Yêu cầu browser xóa session cookie bằng `Set-Cookie` có cùng Name/Domain/Path và `Max-Age=0` khi cần.
5. Xem thêm token remember-me, refresh token, các phiên song song và trạng thái ở identity provider theo chính sách.
6. Tránh cache các response nhạy cảm; logout không thể “thu hồi” mọi dữ liệu đã hiển thị/cached trước đó.

Spring Security Reactive cung cấp logout trong `ServerHttpSecurity`. Khi dùng luồng WebFlux login thực sự, có thể bật/customize:

~~~java
// Snippet cấu hình; cần đưa vào SecurityWebFilterChain thực.
return http
        .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
        .formLogin(Customizer.withDefaults())
        .logout(Customizer.withDefaults())
        .build();
~~~

Luồng logout mặc định Spring Security WebFlux cần được hiểu qua handler và matcher của phiên bản triển khai; **khi CSRF đang bật, không nên mở GET /logout để thực hiện xóa session**. POST logout cần token phù hợp. Nếu custom logout URL, kiểm thử CSRF, status/redirect và việc invalidation bằng browser hoặc WebTestClient.

### 13.3. Cookie deletion và server-side invalidation khác nhau

Một response xóa cookie có thể giống:

~~~http
Set-Cookie: SESSION=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

Đây là chỉ dẫn client xóa cookie theo Name/Domain/Path tương ứng. Nhưng:
- Nếu chỉ xóa cookie mà session ID **vẫn hợp lệ** trên server, kẻ đã giữ ID trước đó có thể tiếp tục dùng ID. Vì vậy phải invalidate/revoke phía server.
- Nếu chỉ invalidate session mà client còn cookie, browser có thể gửi ID cũ nhưng server không được chấp nhận lại.
- Nếu Path/Domain của cookie xóa **không khớp** cookie đã tạo, browser có thể giữ cookie cũ; đây là lỗi cấu hình thường gặp.
- Cookie clearing cũng không thể khiến browser quên **HTTP Basic credentials** đã cache; WebSession logout và Basic logout là vấn đề khác.
- Ở một thiết kế JWT stateless, xóa cookie hay WebSession không tự thu hồi token đã phát, nếu token vẫn hợp lệ và tiếp tục được gửi.

### 13.4. Session fixation

Nếu ứng dụng hỗ trợ đăng nhập chuyển từ anonymous sang authenticated session, cần bảo vệ trước **session fixation**: attacker cố khiến nạn nhân dùng session ID do attacker biết trước, rồi lợi dụng sau khi nạn nhân đăng nhập.

`WebSession.changeSessionId()` cho phép sinh session ID mới cho một session hiện có. Trong Spring Security, hãy kiểm tra session fixation protection thực tế của phiên bản/flow được dùng; không tự thêm một cách thay ID ngẫu nhiên ở sai thời điểm khiến CSRF, form flow hoặc context bị mất. Phần đáng nhớ là **rotate ID tại các ranh giới tăng quyền phù hợp**, không dùng cookie flags để thay biện pháp này.

### 13.5. Concurrent sessions và absolute policy

Một người có thể có nhiều thiết bị/browser. Xóa một WebSession **không mặc nhiên** đăng xuất tất cả thiết bị. Nếu yêu cầu logout-all, cần một cơ chế liệt kê/thu hồi mọi phiên hoặc token theo policy (ví dụ Spring Session với store đủ metadata, token revocation hoặc hệ thống identity quản lý tập trung).

Idle timeout có thể được kéo dài bằng hoạt động. Nếu bảo mật yêu cầu login lại tối đa sau N giờ, phải thêm **absolute lifetime** độc lập. Cookie Max-Age không phải công cụ đáng tin cậy duy nhất cho yêu cầu này.

## 14. HTTPS reverse proxy, Spring Session Redis và triển khai nhiều instance

### 14.1. Reverse proxy

Sơ đồ:

~~~text
Browser --HTTPS--> Load Balancer / Reverse Proxy --(trusted hop)--> WebFlux
             ^                                           |
             |                                           v
             +----------- Set-Cookie: ... Secure ... ----+
~~~

Đừng coi request nội bộ proxy-to-app qua HTTP là lý do bỏ `Secure` ở browser cookie. Nếu app tự suy đoán scheme qua headers, proxy cần xử lý/ghi đè `Forwarded` / `X-Forwarded-Proto` đúng cách; đừng tin header của client public. Có thể phải đặt `server.forward-headers-strategy` theo cấu trúc hạ tầng thực tế và chỉ bật khi trusted proxy đã được thiết kế.

**Quan sát quan trọng** là response thực tế từ origin public tới browser phải có flags đúng và HTTPS ổn định, không có mixed-content hoặc HTTP redirect gây rò session ID.

### 14.2. Nhiều instance và session store

Nếu WebSession lưu in-memory trong một instance, request bị định tuyến tới instance khác có thể không truy cập được dữ liệu session (trừ khi có sticky sessions). Với scale-out, có thể sử dụng Spring Session WebFlux + Redis hoặc store reactive tương đương.

Spring Session cung cấp tích hợp `WebSession` cho Redis và cơ chế cookie resolver. Khi dùng Spring Session:
- Phân biệt **TTL trong Redis**, `WebSession.maxIdleTime`, **cookie Max-Age** và absolute login TTL.
- Đảm bảo logout/invalidate xóa phiên trong shared store.
- Xác minh cập nhật hoạt động/expiration theo implementation cụ thể.
- Không dùng hướng dẫn `HttpSession`/Servlet thay thế cho `WebSession`/Reactive.
- Kiểm tra bean `WebSessionIdResolver` hiện hành; custom resolver có thể ảnh hưởng property binding mặc định.

**Không đặt session ID hoặc raw cookie vào metrics labels/logs.** Để trace một lỗi, dùng correlation ID độc lập, không phải token/ID xác thực.

### 14.3. Triển khai cookie ở subdomain hoặc cross-site

Với frontend `app.example.test` và API `api.example.test`:
- Đừng vội đặt `Domain=.example.test` cho session cookie; việc này mở khả năng cookie tới nhiều subdomain.
- Cân nhắc host-only cookie cùng mô hình Backend-for-Frontend hoặc reverse proxy cùng origin.
- Nếu thực sự cần cross-origin/cross-site, làm rõ CORS allowlist, `credentials` mode của browser, CSRF token, SameSite và third-party cookie policies.
- `SameSite=None` yêu cầu `Secure` trên browser hiện đại nhưng **không bảo đảm** browser sẽ cho third-party cookie đi qua vì có thể có chính sách chặn bổ sung.
- Kiểm tra OAuth2/OIDC redirect flow trên những browser được hỗ trợ nếu login liên quan đến nhiều site.

## 15. Những sai lầm điển hình

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Dùng `server.servlet.session.cookie.*` trong WebFlux | Tên thuộc cấu hình Servlet | Dùng `server.reactive.session.cookie.*` |
| Đặt `Secure=false` trên production HTTPS vì proxy nội bộ HTTP | Lộ ID nếu client đi qua kênh không an toàn | Giữ `Secure=true`, cấu hình proxy/TLS đúng |
| Nghĩ `HttpOnly` ngăn CSRF | Browser vẫn gửi cookie tự động | Kết hợp CSRF token và SameSite đúng policy |
| Nghĩ `HttpOnly` chống được mọi XSS | XSS vẫn có thể thực hiện request có cookie | Phòng chống XSS, CSP, output encoding |
| Dùng `SameSite=None` nhưng không bật Secure | Cookie có thể bị browser từ chối | Dùng `Secure` + HTTPS và đánh giá third-party policy |
| Dùng `SameSite=Strict` mà không test SSO | Flow redirect có thể mất cookie | Test IdP redirect; chọn policy theo use case |
| Tắt CSRF vì đã đặt `SameSite=Lax` | Lax không chặn mọi yêu cầu giả mạo | Giữ CSRF khi dùng browser ambient credentials |
| Hiểu `Max-Age=30m` nghĩa session chắc chắn sống 30m | Server có idle/absolute timeout riêng | Thiết kế/test các đồng hồ riêng |
| Đặt cookie 12h và không có server expiration | Token phiên dễ được lạm dụng lâu | Cấu hình idle và absolute expiry phù hợp |
| Xóa browser cookie nhưng để server session hợp lệ | ID cũ có thể vẫn bị replay | Invalidate/revoke phía server |
| Invalidate phiên nhưng Basic credentials vẫn còn | Basic browser cache khác WebSession | Thiết kế flow logout phù hợp |
| Tự logout bằng GET | GET có thể bị kích hoạt cross-site | Dùng POST và CSRF |
| JavaScript đọc session ID vì muốn đọc CSRF token | Mất bảo vệ HttpOnly cho session | Tách CSRF-token cookie/endpoint khỏi session cookie |
| Domain quá rộng | Cookie đi tới subdomain không cần thiết | Ưu tiên host-only và Path/Domain tối thiểu |
| Tin client-supplied Forwarded headers | Có thể bị lừa về scheme/origin | Chỉ tin trusted reverse proxy |
| Chỉ kiểm thử YAML, không xem Set-Cookie | Bean/proxy/version có thể làm khác | Kiểm tra HTTP headers thực tế |
| Log SESSION ID hoặc ghi vào URL | Rò rỉ bearer-like session identifier | Redact token, URL/trace không chứa session ID |
| Đổi session store không xem Redis TTL | Session hết hạn/sống quá kỳ vọng | Đồng bộ policy và quan sát store |

## 16. Checklist triển khai và kiểm chứng

### Cookie phía client
- [ ] Cookie **session ID** có `Secure` khi chạy HTTPS production.
- [ ] `HttpOnly` bật cho session ID.
- [ ] `SameSite` được chọn có lý do: Strict/Lax/None, bao gồm luồng SSO và browser compatibility.
- [ ] `Path` và `Domain` tối thiểu; ưu tiên host-only nếu không cần chia sẻ subdomain.
- [ ] `Max-Age` hoặc session-cookie lifetime đúng với policy, không nhầm server timeout.
- [ ] Cookie cũ cùng tên/path/domain không gây shadowing khi migration.
- [ ] Browser DevTools xác nhận response `Set-Cookie` và request `Cookie` như dự kiến.
- [ ] Không lộ session ID trong console/log/query/analytics.

### Session phía server
- [ ] `server.reactive.session.timeout` có giá trị idle timeout hợp lý.
- [ ] Khi cần absolute lifetime, có policy thực thi và kiểm thử riêng.
- [ ] Invalidate session thực sự xóa state ở WebSession store/Redis, kể cả nhiều instance.
- [ ] Tại ranh giới authentication/privilege phù hợp, kiểm tra session fixation/rotation.
- [ ] Multi-device logout và token revocation được thiết kế riêng nếu yêu cầu.
- [ ] Không suy luận “stateless” chỉ từ việc không thấy cookie hoặc việc dùng no-op SecurityContextRepository.

### Security và vận hành
- [ ] CSRF protection còn phù hợp với các thao tác unsafe của browser.
- [ ] GET/HEAD không có side effects.
- [ ] HTTPS và trusted proxy/forwarded headers đúng.
- [ ] Phân quyền tài nguyên được thực thi độc lập với session cookie flags.
- [ ] Local profile `secure:false` không bao giờ được deploy lên hệ thống công khai.
- [ ] Chạy kiểm thử Spring Security/WebFlux và browser thật; test các browser được hỗ trợ.
- [ ] Có monitoring an toàn cho login failure, expired session và logout, không ghi session IDs.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `Secure` có mã hóa nội dung cookie không?

> Không. Nó hạn chế gửi cookie qua kênh HTTP không bảo mật; cần HTTPS/TLS để bảo vệ đường truyền.

**Câu 2.** `HttpOnly` ngăn JavaScript cùng origin thực hiện request có cookie không?

> Không. Nó hạn chế đọc cookie bằng JavaScript thông thường; browser vẫn có thể gửi cookie trong request.

**Câu 3.** `SameSite=Lax` có thay CSRF token được không?

> Không. Lax chỉ hạn chế một số tình huống cross-site và vẫn có ngoại lệ/giới hạn; cần CSRF protection theo threat model.

**Câu 4.** Vì sao `SameSite=None` thường phải có `Secure`?

> Browser hiện đại yêu cầu cookie None đi kèm Secure; với HTTPS vẫn có thể bị chính sách third-party cookie chặn.

**Câu 5.** Nếu cookie `Max-Age=30m` nhưng WebSession idle timeout 10 phút, sau 15 phút không hoạt động request có thể còn session không?

> Cookie có thể vẫn được gửi, nhưng server phải coi WebSession hết hạn nếu vượt idle timeout theo store; không được chấp nhận ID cũ để khôi phục authentication.

**Câu 6.** Spring Boot WebFlux dùng namespace cấu hình nào?

> `server.reactive.session.*`; không phải `server.servlet.session.*`.

**Câu 7.** Tại sao `NoOpServerSecurityContextRepository` không đủ để nói “không có session”?

> Vì CSRF token repository, controller và thành phần WebFlux khác vẫn có thể tạo WebSession.

**Câu 8.** Vì sao xóa cookie phía browser mà không invalidate session server là chưa đủ cho logout?

> Vì session ID bị sao chép trước đó vẫn có thể được server chấp nhận nếu phiên chưa bị thu hồi.

**Câu 9.** Một browser tiếp tục gửi HTTP Basic sau `WebSession.invalidate()`. Có phải invalidate lỗi?

> Không nhất thiết. Basic credentials có thể vẫn nằm trong cache của browser; chúng độc lập với WebSession.

**Câu 10.** `Max-Age` và `maxIdleTime` khác nhau thế nào?

> Max-Age là thời hạn lưu/gửi cookie phía client; maxIdleTime là thời gian idle trước khi WebSession phía server bị coi là hết hạn.

**Câu 11.** Khi nào nên dùng `CookieWebSessionIdResolver.addCookieInitializer`?

> Khi cần tùy chỉnh session ID cookie theo chính sách đặc thù hoặc không dùng auto-configuration phù hợp, và phải kiểm tra conflict với Spring Boot/Spring Session.

**Câu 12.** Tại sao không nên đặt `Domain=.example.test` chỉ để tiện dùng cho mọi subdomain?

> Vì phạm vi cookie mở rộng, có thể làm tăng nguy cơ bị lạm dụng bởi subdomain yếu hoặc không đáng tin; ưu tiên host-only và cách ly origin.

## 18. Tổng kết

Trong Spring Security Reactive, **cookie phiên là phương tiện vận chuyển session ID**, còn WebSession/SecurityContext và session store quyết định những dữ liệu hoặc quyền liên quan còn hợp lệ hay không.

Năm quy tắc cần nhớ:

1. **Production HTTPS:** đặt `Secure=true` cho cookie session ID.
2. **Không cho script đọc ID:** giữ `HttpOnly=true` cho session cookie.
3. **Giới hạn cross-site có chủ đích:** thường bắt đầu từ `SameSite=Lax`, đánh giá Strict/None theo nhu cầu SSO/iframe/cross-site thật.
4. **Quản lý hai thời hạn:** cookie `Max-Age` và server `maxIdleTime` là hai đồng hồ khác nhau; absolute login lifetime cần policy riêng.
5. **Logout thật phải revoke phiên:** invalidate server-side state, xóa cookie đúng scope khi cần, và xử lý riêng Basic/JWT/refresh token hoặc các phiên thiết bị khác.

Đối với Spring Boot WebFlux, dùng `server.reactive.session.cookie.*` và `server.reactive.session.timeout`, kiểm tra `Set-Cookie` trên môi trường thực, và tiếp tục bảo vệ CSRF/XSS, authorization, TLS và session fixation như các lớp riêng.

### Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Common Application Properties, nhóm `server.reactive.session`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Framework Javadoc — `WebSession`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/server/WebSession.html
- Spring Framework Javadoc — `CookieWebSessionIdResolver`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html
- Spring Session Reference — WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- Spring Session Reference — Common Configurations: https://docs.spring.io/spring-session/reference/configuration/common.html
- Spring Security — WebFlux CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- MDN — Set-Cookie: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie
- RFC 6265bis — HTTP State Management Mechanism (draft/current evolution): https://httpwg.org/http-extensions/draft-ietf-httpbis-rfc6265bis.html