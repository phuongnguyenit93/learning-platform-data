# Chẩn đoán chuyển hướng lặp, mất phiên và cookie không được gửi trong Spring Security WebFlux

## 1. Bài toán và mục tiêu chẩn đoán

Trong ứng dụng **Spring Security reactive** (Spring WebFlux), ba triệu chứng dưới đây thường xuất hiện cùng nhau nhưng có thể bắt nguồn từ những tầng khác nhau:

1. **Chuyển hướng lặp (redirect loop):** trình duyệt đi từ trang được bảo vệ đến `/login` rồi quay lại trang được bảo vệ, hoặc lặp giữa ứng dụng và Identity Provider (IdP), cuối cùng báo `ERR_TOO_MANY_REDIRECTS`.
2. **Mất phiên (session lost):** người dùng vừa đăng nhập thành công nhưng request kế tiếp lại bị coi là anonymous; hoặc vào được một lần rồi bị đăng xuất sau khi chuyển node/redeploy/qua gateway.
3. **Cookie không được gửi:** response đã có `Set-Cookie` nhưng request tiếp theo không mang `Cookie`; hoặc cookie được gửi nhưng server không lấy ra được phiên đúng.

**Mục tiêu** là khoanh vùng chính xác sự cố nằm ở **phát cookie, trình duyệt lưu cookie, trình duyệt gửi cookie, server tra cứu phiên, khôi phục Authentication hay xác định đích redirect**. Không nên chữa mọi trường hợp bằng `permitAll()`, tắt CSRF, tắt `Secure` hay mở CORS cho tất cả origin: những thay đổi đó có thể che lỗi nhưng làm yếu bảo mật.

Phạm vi kiến thức tập trung vào **Spring Boot 3.3 / Spring Security 6.x / WebFlux**. Servlet `HttpSession`, `SecurityContextHolder` thread-local, `HttpSecurity` và `CookieSerializer` dành cho Servlet không phải các công cụ chính của WebFlux. Ở WebFlux ta thường kiểm tra `WebSession`, `ServerSecurityContextRepository`, `ReactiveSecurityContextHolder`, `ServerHttpSecurity` và `SecurityWebFilterChain`.

## 2. Mô hình luồng đăng nhập cần hình dung

Một luồng **form login có session** hợp lệ có thể diễn ra như sau (status chỉ mang tính minh họa; cơ chế tùy cấu hình):

```text
Trình duyệt                         Spring Security WebFlux
    | GET /private
    |------------------------------>|
    | 302 Location: /login          |  Chưa xác thực; có thể lưu saved request
    |<------------------------------|
    | GET /login                    |
    |------------------------------>|
    | 200 trang đăng nhập + CSRF    |
    |<------------------------------|
    | POST /login (user, pass, CSRF, Cookie: SESSION=...)
    |------------------------------>|
    | 302 Location: /private        |  Xác thực OK, lưu SecurityContext trong WebSession
    | Set-Cookie: SESSION=...       |  Session ID có thể đổi để chống session fixation
    |<------------------------------|
    | GET /private; Cookie: SESSION=...
    |------------------------------>|
    | 200 nội dung được bảo vệ      |  Khôi phục Authentication từ session
    |<------------------------------|
```

**Điều phải chứng minh:** trình duyệt gửi đúng cookie **sau lần đăng nhập cuối**, session được tìm thấy trên server và `Authentication` được khôi phục khi xử lý `GET /private`. Một response `302` không tự nó chứng minh login đã thành công. Một cookie có mặt trong request cũng không chứng minh session phía server còn tồn tại.

Với **OAuth2 Login/OIDC**, luồng khác: `/oauth2/authorization/{registrationId}` → IdP → `/login/oauth2/code/{registrationId}` → lưu authentication → route đích. WebFlux thường dùng phiên để lưu authorization request và giá trị `state` nhằm đối chiếu callback. Nếu mất cookie ở callback, vòng đăng nhập có thể bắt đầu lại.

Với **Resource Server chỉ dùng Bearer token**, chính sách thường là xác thực lại token trên mỗi request và không cần form-login session. Nếu SPA tự chuyển đến login mỗi khi nhận `401`, sự cố có thể nằm ở Authorization header, token storage hoặc logic redirect phía client, chứ không phải `WebSession`.

## 3. Phân loại lỗi theo chuỗi bằng chứng

Không bắt đầu bằng suy đoán “session timeout”. Hãy xác định **điểm đứt đầu tiên**:

| Bằng chứng khi theo dõi một chuỗi request | Lớp có khả năng lỗi | Câu hỏi tiếp theo |
| --- | --- | --- |
| Response login không có `Set-Cookie` dù ứng dụng phải tạo session | Session chưa khởi tạo/lưu; chain/login handler khác dự kiến | Login có thực sự thành công? SecurityContext đã được lưu chưa? |
| Có `Set-Cookie` nhưng DevTools báo **blocked/rejected** | Thuộc tính cookie, HTTPS hoặc chính sách browser | `Secure`, `SameSite`, Domain/Path/Expiry sai chỗ nào? |
| Cookie lưu trong browser nhưng request kế tiếp **không có Cookie** | Quy tắc gửi cookie, request cross-origin, redirect đổi host | Đích request có cùng host/path/scheme? `credentials` có đúng? |
| Browser gửi `Cookie: SESSION=...` nhưng server tạo session mới | Session store, cân bằng tải, TTL, cookie name hoặc resolver | Request tới instance nào? Session còn trong store không? |
| Session tìm được nhưng vẫn anonymous | SecurityContext repository, custom filter, login flow, Reactor Context | Authentication đã được save/load đúng không? Có dùng `NoOpServerSecurityContextRepository`? |
| Authentication có nhưng vẫn `302`/`403` | Authorization, matcher, request cache, entry point | Quy tắc nào từ chối? Redirect target có bị bảo vệ không? |
| Chỉ lỗi sau IdP callback | OAuth2 state/redirect URI/session cookie | Callback có dùng cùng phiên đã khởi tạo trước khi sang IdP? |
| Chỉ lỗi sau qua ingress/proxy hoặc trên HTTPS | Forwarded headers, scheme, host, path, cookie security | `Location` đang trả về HTTP/internal hostname sai không? |

**Chẩn đoán bằng thứ tự thời gian**, không chỉ xem response cuối. Nếu trình duyệt tự theo 8 lần `302`, một bản ghi cuối `ERR_TOO_MANY_REDIRECTS` không cho biết redirect đầu tiên nào sai.

## 4. Dùng DevTools để tìm redirect và cookie bị chặn

Trên Chrome/Edge/Firefox, mở Developer Tools và thực hiện:

1. Vào **Network**, bật **Preserve log** và tái hiện lỗi từ một tab sạch. Bật ghi network trước khi nhấn Login; nếu dùng cửa sổ ẩn danh cần nhớ chính sách cookie/privacy có thể khác.
2. Lọc `Doc`/`Fetch/XHR` và status `301`/`302`/`303`/`307`/`308`. Với mỗi lần chuyển hướng, ghi **method, request URL (bỏ query nhạy cảm), status, Location, host, scheme, path**.
3. Trong response của request khởi tạo/lưu phiên, xem `Set-Cookie`; trong request kế tiếp, xem `Cookie`. Đừng chỉ kiểm tra bảng Storage: việc lưu được cookie không có nghĩa cookie đã được đính kèm mọi request.
4. Ở tab **Application/Storage → Cookies** và **Network → Cookies**, xem thuộc tính `Name`, `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`, `Expires/Max-Age`. Một số browser hiển thị **Blocked Reason** giải thích vì sao cookie không được chấp nhận hoặc gửi đi.
5. Đối với request cross-origin, xem thêm `Origin`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials` và request `OPTIONS` preflight. Kiểm tra JS `fetch`/XHR có bật gửi credentials hay chưa.
6. So sánh trước/sau redirect: browser có đang đổi từ `https://app.example.org` sang `http://app.example.org`, sang `internal-service:8080`, sang domain khác, hoặc mất prefix `/app` không?

**Không dán raw `Cookie`, `Set-Cookie`, `Authorization`, mã `code`, `state`, `id_token` hay full HAR lên ticket/chat.** Session cookie là credential; các URL OAuth2 callback còn có giá trị ngắn hạn nhạy cảm. Khi chia sẻ bằng chứng, thay giá trị bằng marker như `<redacted>` và giữ nguyên tên thuộc tính, domain, path, status và thứ tự hop.

### 4.1. Bảng ghi sự kiện tối thiểu

Lập một bảng thực nghiệm cho đúng một lần thử đăng nhập:

| Lần | Phương thức & route | Status → Location (che query) | Set-Cookie? | Cookie gửi đi? | Instance/store |
| --- | --- | --- | --- | --- | --- |
| 1 | `GET /private` | `302 /login` | có thể có | không | node A |
| 2 | `GET /login` | `200` | có/không | có/không | node A |
| 3 | `POST /login` | `302 /private` | thường có/có thể đổi ID | có | node A |
| 4 | `GET /private` | `200` mong đợi | không bắt buộc | có | node A/B |

Đây là **mẫu nhật ký mong đợi**, không phải HTTP output cố định. Nếu lỗi diễn ra ở hop 4, so sánh ID phiên **theo dấu đã băm an toàn ở server** và instance nhận request; không xuất bản giá trị cookie thật. Spring Security có thể đổi session ID sau xác thực để chống session fixation — thay đổi này bình thường, hãy dùng cookie **mới nhất** mà server cấp.

### 4.2. Quan sát HTTP bằng curl

Có thể kiểm tra response redirect đầu tiên mà không tự theo redirect:

```bash
# Chỉ xem response headers; thay host bằng môi trường thử nghiệm của bạn.
curl -sS -D - -o /dev/null --max-redirs 0 \
  https://app.example.org/private
```

Dùng cookie jar khi cần mô phỏng trình duyệt giữ session (file jar là dữ liệu nhạy cảm, chỉ dùng trong máy thử nghiệm, xóa an toàn sau khi kiểm tra):

```bash
# Bắt đầu session và lưu các cookie server cấp.
curl -sS -D - -o /dev/null -c session-cookies.txt \
  https://app.example.org/private

# Request kế tiếp gửi lại cookie phù hợp với chính sách curl.
curl -sS -D - -o /dev/null \
  -b session-cookies.txt -c session-cookies.txt \
  https://app.example.org/private
```

Lệnh trên **không thực hiện đăng nhập**; nếu chưa đăng nhập, kết quả `302` là bình thường. Với form login, cần lấy CSRF token hợp lệ từ HTML/form và POST username/password cùng cookie qua TLS; nếu không, `403` có thể là CSRF rejection, không phải mất phiên. Curl không mô phỏng đầy đủ chính sách SameSite, CORS, third-party cookie hay redirect behavior của browser. Vì vậy **curl hoạt động còn trình duyệt lỗi** là tín hiệu quan trọng cho nhóm nguyên nhân browser/cross-site.

Không dùng `curl -k` để “sửa” TLS trong chẩn đoán thật; lỗi chứng chỉ có thể là nguyên nhân browser không chấp nhận luồng.

## 5. Hiểu đúng cookie của WebFlux

Cookie của WebSession thường chỉ mang **mã định danh phiên**, không chứa toàn bộ `Authentication`; phía server cần tìm session theo mã đó. Tên mặc định thường là `SESSION` trong WebFlux/Spring Session, nhưng **phải kiểm tra response thực tế** vì ứng dụng có thể đổi tên qua `WebSessionIdResolver` hoặc cấu hình Boot.

| Thuộc tính | Khi nào browser từ chối/không gửi | Cách xác minh và hướng sửa |
| --- | --- | --- |
| `Domain` | Cookie bị đặt cho domain không hợp lệ hoặc không khớp host request | Kiểm tra host thực sau proxy; ưu tiên host-only cookie khi chỉ dùng một host. |
| `Path` | Cookie `Path=/app` không gửi tới `/login/oauth2/code` ngoài `/app` | Đối chiếu path của *mọi* request callback/API; chọn path đúng phạm vi. |
| `Secure` | Cookie Secure chỉ gửi qua HTTPS (một số ngoại lệ browser với localhost) | Dùng HTTPS chuẩn từ browser đến reverse proxy; môi trường HTTP local cần cấu hình thử nghiệm riêng. |
| `HttpOnly` | `document.cookie` không đọc được cookie, nhưng browser **vẫn có thể tự gửi** | Đây là bảo vệ mong muốn cho session cookie; không tắt chỉ để debug. |
| `SameSite=Strict` | Chặn cookie trong nhiều luồng chuyển từ site khác, kể cả OAuth2 callback cross-site | Phân tích navigation/callback; `Lax` thường phù hợp top-level GET, nhưng không đủ cho mọi flow POST/iframe. |
| `SameSite=Lax` | Cross-site `fetch` hoặc iframe thường không được gửi cookie | Phân biệt top-level navigation với XHR; cấu hình theo luồng thực tế. |
| `SameSite=None` | Browser hiện đại yêu cầu `Secure`; vẫn có thể bị chặn bởi chính sách third-party cookie | Dùng HTTPS, xác minh chính sách browser; đừng xem None là cách né toàn bộ privacy policy. |
| `Expires`/`Max-Age` | Cookie hết hạn, `Max-Age=0` xóa cookie hoặc client clock lệch | Quan sát cả cookie được *thay mới/xóa* trong response cuối. |
| Tên cookie | Hai ứng dụng chung tên trên cùng host/path có thể ghi đè | Kiểm tra từng `Set-Cookie` và phạm vi Domain/Path; dùng tên/path rõ ràng. |
| Dung lượng/giới hạn | Cookie hoặc tổng header quá lớn bị browser/proxy từ chối | Đo kích thước header, tránh lưu token/claims lớn vào cookie session. |

**Site không đồng nghĩa origin.** `https://app.example.org` và `https://api.example.org` khác origin nhưng thường cùng site theo quy tắc schemeful site; chúng vẫn cần CORS cho JavaScript cross-origin nhưng SameSite có thể xử lý khác hẳn `https://another-company.org`. Ngược lại, đổi `http` sang `https` có thể làm thay đổi cách browser xét site. Hãy kiểm tra **thực tế trong DevTools**, không suy luận từ tên miền gần giống nhau.

### 5.1. Cấu hình cookie đúng namespace của Spring Boot WebFlux

Ví dụ sản phẩm dùng HTTPS ở trình duyệt, session-cookie chỉ phục vụ cùng site:

```yaml
# application.yml - ví dụ cho môi trường chạy qua HTTPS được tin cậy
server:
  reactive:
    session:
      timeout: 30m
      cookie:
        name: SESSION
        path: /
        http-only: true
        secure: true
        same-site: lax
```

Những key cần nhớ: `server.reactive.session.cookie.name`, `path`, `domain`, `secure`, `http-only`, `same-site` và `server.reactive.session.timeout`. **Không dùng** `server.servlet.session.cookie.same-site` cho ứng dụng WebFlux, vì key Servlet không điều khiển cookie reactive.

Đặt `secure: true` cho HTTPS production. Khi chạy HTTP plain ở máy local, cookie Secure có thể không được gửi theo chính sách browser; cấu hình local phải được phân tách theo profile và không đưa chính sách thử nghiệm lên production.

Không đặt `domain: .example.org` theo thói quen nếu ứng dụng chỉ ở một hostname; cookie chia sẻ cho nhiều subdomain mở rộng phạm vi nhận credential. Domain không được tùy ý chọn một tên không thuộc host trả cookie.

### 5.2. Tùy biến bằng `CookieWebSessionIdResolver` khi cần

Có thể thay cơ chế viết cookie của WebFlux bằng bean `WebSessionIdResolver` (đoạn dưới độc lập về mặt class, dùng trong dự án Spring WebFlux đã có dependencies):

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
public class SessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();
        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(cookie -> cookie
                .path("/")
                .httpOnly(true)
                .secure(true)
                .sameSite("Lax"));
        return resolver;
    }
}
```

Cấu hình này dành cho HTTPS; **không đồng thời viết thêm một resolver khác** với tên/path không tương thích. Trong ứng dụng dùng Spring Session WebFlux, resolver cũng quyết định cách đọc/ghi cookie session. Hãy lựa chọn **một** nơi làm nguồn cấu hình cookie (properties Boot hoặc bean resolver phù hợp), rồi xác minh `Set-Cookie` thực tế vì bean tùy biến có thể thay đổi hành vi auto-configuration.

## 6. Chẩn đoán redirect loop của form login

Với một trang bảo vệ `/private`, hành vi hợp lệ là anonymous được dẫn đến `/login` rồi đăng nhập. Những lỗi kinh điển:

### 6.1. Trang đăng nhập cũng bị bảo vệ

Ví dụ rule lỗi:

```java
// SAI: trang đăng nhập tự bị yêu cầu authentication.
http.authorizeExchange(rules ->
        rules.anyExchange().authenticated())
    .formLogin(form -> form.loginPage("/signin"));
```

Nếu `GET /signin` cũng cần authentication và entry point lại redirect tới `/signin`, chuỗi có thể thành `/signin → /signin → ...`. Cấu hình phù hợp:

```java
// Đoạn thuộc một @Bean SecurityWebFilterChain của WebFlux.
return http
        .authorizeExchange(rules -> rules
                .pathMatchers("/signin", "/assets/**", "/public/**")
                .permitAll()
                .anyExchange().authenticated())
        .formLogin(form -> form.loginPage("/signin"))
        .build();
```

Với trang login **tùy biến**, ứng dụng phải tự phục vụ `GET /signin` và bảo đảm form POST tới đúng **login processing endpoint**, mang credential và CSRF token. Đoạn DSL trên là **cấu hình minh họa**, không tự tạo controller/HTML `/signin`. Nếu muốn login page mặc định do Spring Security tạo, dùng `formLogin(Customizer.withDefaults())` và kiểm tra `GET /login`.

### 6.2. Sai entry point hoặc match sai security chain

Khi có nhiều `SecurityWebFilterChain`, chain có `@Order` ưu tiên hơn được chọn trước nếu `securityMatcher(...)` khớp. Chain API mong đợi `401` có thể bị chain browser áp redirect `302`, hoặc trang login/callback rơi vào chain khác.

Hãy đối chiếu **hai loại matcher**:

- `securityMatcher(...)` chọn **chain** áp dụng cho request.
- `authorizeExchange(...).pathMatchers(...)` chọn **quy tắc** bên trong chain đã được chọn.

Quy tắc `anyExchange().authenticated()` đặt trước `pathMatchers("/login").permitAll()` có thể nuốt route public hoặc làm rule không thể truy cập. Sắp xếp các matcher cụ thể trước `anyExchange`, và đảm bảo chain catch-all không đứng trước chain chuyên biệt.

### 6.3. Đăng nhập đã thành công nhưng redirect quay lại login

Khi `POST /login` thành công, Spring Security có thể redirect tới saved request (đường dẫn người dùng yêu cầu trước khi đăng nhập) thông qua `ServerRequestCache`, chẳng hạn `WebSessionServerRequestCache`. Nếu cookie/session không đi cùng request tiếp theo hoặc SecurityContext không được lưu, endpoint sẽ tiếp tục coi người dùng anonymous và redirect trở lại `/login`.

Chẩn đoán nên tách:

1. `POST /login` có thành công thật không hay trả `/login?error`? Có nhận được cookie mới nếu session thay ID không?
2. `GET /private` sau redirect có gửi cookie đúng không?
3. Backend có tìm thấy đúng `WebSession` không?
4. `ReactiveSecurityContextHolder` trong request mới có authentication không?
5. Saved request/redirect target có trỏ tới URL đã di chuyển, host khác, route bảo vệ sai hoặc chính `/login` không?

Lỗi `POST /login` bị `403` thường cần kiểm tra **CSRF token** trước khi kết luận mất phiên. Đặc biệt, một trang login tự viết cần include token và giữ cookie/session trên POST. Không tắt CSRF toàn ứng dụng để làm flow “có vẻ hoạt động”.

### 6.4. Redirect HTTP ↔ HTTPS hoặc host qua proxy

Chuỗi `https://app.example.org/... → http://app.example.org/... → https://...` thường liên quan reverse proxy/ingress thiếu thông tin scheme gốc. Nếu redirect tạo Location chứa `http://10.x.x.x:8080` hoặc hostname nội bộ, proxy có thể chưa truyền đúng forwarded headers hoặc server chưa được cấu hình tin cậy. Xem mục 9 để sửa đúng lớp.

## 7. Phân biệt WebSession với SecurityContext

Trong WebFlux, những khái niệm cần tách rõ:

- `WebSession` quản lý dữ liệu gắn với session ID, thường được đọc qua cookie `SESSION`.
- `WebSessionIdResolver` đọc session ID từ request và ghi/xóa cookie vào response.
- `WebSessionServerSecurityContextRepository` lưu/đọc `SecurityContext` trong `WebSession`, và có thể đổi session ID khi lưu authentication để chống **session fixation**.
- `ServerSecurityContextRepository` là SPI cho cách lưu/khôi phục SecurityContext giữa request. `NoOpServerSecurityContextRepository` cố ý **không lưu** context; hợp lý với một số API stateless, nhưng không phải cấu hình thay thế bừa bãi cho form login.
- `ReactiveSecurityContextHolder` truy cập SecurityContext trong **Reactor Context** của chuỗi xử lý; không mặc định dùng ThreadLocal như Servlet.
- `WebSessionServerRequestCache` giữ thông tin saved request để redirect sau login. Nó không thay thế chỗ lưu Authentication.

Một session có thể **đang tồn tại nhưng không có SecurityContext hợp lệ**. Ngược lại, một request dùng Bearer JWT có thể có `Authentication` trong Reactor Context dù **không có session cookie**; điều đó bình thường với mô hình stateless.

### 7.1. Lỗi custom authentication chỉ gắn context tạm thời

Một custom `WebFilter` có thể tạo `Authentication`, đưa vào Reactor Context cho request hiện tại nhưng **không lưu** vào `ServerSecurityContextRepository`. Request tiếp theo sẽ mất authentication. Nếu yêu cầu browser login dựa session, hãy sử dụng cơ chế auth của Spring Security hoặc triển khai đầy đủ lưu context thành công; đừng tự tạo WebFilter “giả đăng nhập”.

Ví dụ thể hiện **chỉ thao tác đọc** trong reactive controller:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> authenticatedUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
}
```

Đây là method fragment, chưa phải chương trình độc lập; chỉ trả về giá trị khi subscriber có SecurityContext hợp lệ. Không kết luận “mất session” từ việc `SecurityContextHolder.getContext()` cho anonymous/null trong thread khác: đó có thể chỉ là đọc sai API trong WebFlux.

### 7.2. Session có thể hết hạn hoặc bị mất trong hệ nhiều instance

Nếu khi đứng trên node A đăng nhập được, nhưng lần gọi kế tiếp cân bằng tải sang node B lại anonymous, hãy kiểm tra session store:

- Với session trong memory của ứng dụng, node B thường không thấy session tạo trên node A. Sticky sessions có thể giảm triệu chứng nhưng không xử lý triệt để restart, scale, failover.
- Với **Spring Session reactive + Redis/MongoDB**, các instance có thể chia sẻ session, nhưng cần xác minh `ReactiveSessionRepository` thực sự đã được cấu hình, kết nối store hoạt động, namespace/TTL thống nhất và không có lỗi serialize/eviction.
- Session timeout khác **cookie expiry**: cookie vẫn còn nhưng bản ghi session ở Redis đã hết hạn sẽ tạo request anonymous.
- Logout có thể làm vô hiệu session; flow logout hoặc cookie xóa từ response khác có thể gây “mất phiên” mà không liên quan timeout.
- Session ID đổi sau đăng nhập là cơ chế chống fixation. Khi theo dấu, kiểm tra ID mới nhất trên browser được trả về, không mặc định so sánh với ID trước login.

Spring Boot 3.3 có auto-configuration reactive Spring Session cho Redis/MongoDB khi có dependency và connection factory phù hợp; không nhầm với `@EnableRedisHttpSession` dành cho Servlet. Ví dụ bổ sung dependency khi chủ động dùng shared reactive Redis sessions:

```groovy
dependencies {
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
}
```

Đây là **đoạn thêm vào build Gradle đã được cấu hình Spring Boot/BOM**, không phải dự án build hoàn chỉnh. Cần kiểm tra bean `ReactiveSessionRepository`/`WebSessionManager` khi chạy thực tế, xác minh cấu hình Redis và kiểm thử đổi instance. Đối với Spring Session, `spring.session.timeout` điều khiển timeout của repository theo cấu hình Boot; đối với WebFlux session mặc định, `server.reactive.session.timeout` là thuộc tính tương ứng. Phải xem cấu hình nào đang hoạt động trong runtime, tránh thay một key rồi kết luận session đã được kéo dài.

## 8. Ví dụ WebFlux nhỏ để tái hiện và kiểm tra redirect

Ví dụ này dùng **Spring Boot 3.3 + Java 17+ + Gradle có Spring Boot plugin/dependency management**. Đây là ứng dụng tối thiểu có form login, `WebSession` và route bảo vệ. Không cần IdP bên ngoài để học cách quan sát `302`/cookie.

### 8.1. Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tránh đồng thời mang vào `spring-boot-starter-web` khi mục tiêu là WebFlux, vì Spring Boot thông thường ưu tiên stack MVC nếu có cả hai.

### 8.2. Tệp `src/main/java/demo/SessionDiagnosticsApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class SessionDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionDiagnosticsApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(rules -> rules
                        .pathMatchers("/public/**", "/login").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetails() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}local-demo-password")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @RestController
    static class DemoRoutes {

        @GetMapping("/public/ping")
        Mono<String> ping() {
            return Mono.just("pong");
        }

        @GetMapping("/private/whoami")
        Mono<String> whoami() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(ctx -> "hello " +
                            ctx.getAuthentication().getName());
        }
    }
}
```

Đây là **một tệp Java hoàn chỉnh trong một project Spring Boot đã khai báo dependency như trên**. Tên public class phải trùng tên file. `{noop}` là plaintext password encoder cho demo cục bộ; không dùng trong môi trường thật. Không xóa CSRF protection; với form login mặc định, Spring Security cung cấp form và CSRF token cần thiết.

Chạy từ root project:

```bash
./gradlew bootRun
```

Thực hiện trong trình duyệt:

1. Truy cập `http://localhost:8080/public/ping` → body `pong`.
2. Truy cập `http://localhost:8080/private/whoami` khi chưa đăng nhập → chuyển tới trang login.
3. Dùng tài khoản `learner` / `local-demo-password` trong form đăng nhập mặc định.
4. Sau đăng nhập, route `/private/whoami` trả `hello learner`. Theo dõi response `Set-Cookie` và request `Cookie` trong Network.
5. Xóa **riêng cookie session của localhost** trong DevTools và tải lại route bảo vệ → chuyển về login. Đây là tái hiện có chủ đích của “mất thông tin session”, không phải lỗi bảo mật.
6. Nếu thay `server.reactive.session.cookie.path` bằng path không bao phủ `/private` hoặc bật `secure: true` trên HTTP local, dùng DevTools quan sát browser không gửi cookie thích hợp. Chỉ thử trên profile local và hoàn nguyên để tránh khóa phiên thực.

Lưu ý: Spring Security có thể chỉ tạo/set cookie khi có session được sử dụng/lưu. Không nhất thiết mỗi response `GET /login` đều có `Set-Cookie`; cần xem **toàn bộ chuỗi** thay vì yêu cầu cookie xuất hiện trên mọi hop.

### 8.3. Kiểm thử HTTP mức tích hợp

Tệp `src/test/java/demo/SessionDiagnosticsApplicationTests.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SessionDiagnosticsApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousRequestRedirectsButLoginPageIsReachable() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");

        client.get().uri("/private/whoami")
                .exchange()
                .expectStatus().is3xxRedirection();

        client.get().uri("/login")
                .exchange()
                .expectStatus().isOk();
    }
}
```

Chạy `./gradlew test`. Test chứng minh đường công khai, redirect ở route bảo vệ và trang login có thể truy cập. **Nó chưa chứng minh session persistence sau form submit**. Để test sự cố thực tế, bổ sung bài test end-to-end có cùng cookie jar, CSRF token hợp lệ, POST login, GET route bảo vệ, và (nếu có) chạy qua ingress/multi-instance. Không dùng `mockUser` làm bằng chứng cookie được lưu: `mockUser` giúp test authorization nhưng không thể thay thế kiểm thử login/session thật.

## 9. Reverse proxy, ingress và forwarded headers

Ứng dụng ở phía sau gateway có thể nhận HTTP nội bộ trong khi user truy cập HTTPS công khai:

```text
Browser: https://app.example.org/private
      |
      v HTTPS
Ingress / Load balancer (TLS termination)
      |
      v HTTP
Spring WebFlux: http://service:8080/private
```

Nếu backend tin rằng base URL là `http://service:8080`, redirect URL hoặc OAuth2 `redirect_uri` có thể sai scheme/host/path. Các dấu hiệu:

- `Location` trỏ về host nội bộ, cổng `8080` hoặc giao thức `http`.
- Callback OIDC trả về HTTP thay vì HTTPS, IdP từ chối `redirect_uri` hoặc user bị dẫn đi sai host.
- Cookie `Secure` không được gửi trong một hop HTTP do **browser** thực sự đổi URL sang HTTP; lưu ý cookie Secure vẫn được gửi từ browser khi **URL public là HTTPS**, dù kết nối **proxy → backend** là HTTP.
- Ingress rewrite prefix `/app` không nhất quán: browser đi `/app/login` nhưng backend trả `Location: /login`, khiến path/cookie không khớp.

Spring Boot cho phép cấu hình đọc forwarded headers (chỉ bật khi ingress/proxy đáng tin cậy và quản lý headers đúng cách):

```yaml
server:
  forward-headers-strategy: framework
```

Trong WebFlux, chiến lược framework dùng cơ chế `ForwardedHeaderTransformer`; proxy cần cung cấp `Forwarded` hoặc `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port` và nếu thích hợp `X-Forwarded-Prefix` chính xác. Có thể dùng `native` khi server và môi trường hỗ trợ đầy đủ; kiểm tra output redirect thật thay vì áp key máy móc.

**Ranh giới tin cậy:** ứng dụng không được tin raw forwarded headers từ Internet. Reverse proxy phải loại/ghi đè headers do client tự gửi, rồi đặt headers của proxy đáng tin; nếu không, attacker có thể thao túng host/redirect. Chỉ thay đổi strategy sau khi xác định kiến trúc deployment và test scheme/host/prefix dưới ingress thực tế.

## 10. OAuth2 Login/OIDC: state, callback và phiên

Một luồng Authorization Code thường có các bước:

```text
GET /oauth2/authorization/oidc
  -> lưu OAuth2AuthorizationRequest + state vào WebSession
  -> 302 đến IdP /authorize

IdP đăng nhập và redirect browser về:
GET /login/oauth2/code/oidc?code=<redacted>&state=<redacted>
  -> trình duyệt gửi cookie session trước đó
  -> ứng dụng đối chiếu state, đổi code lấy token
  -> lưu Authentication / SecurityContext
  -> 302 về trang được bảo vệ
```

Đường dẫn mặc định có thể thay đổi theo `ClientRegistration` và cấu hình login/callback. Với Spring Security WebFlux, một implementation liên quan là `WebSessionOAuth2ServerAuthorizationRequestRepository`; nó lưu authorization request trong `WebSession`. Vì vậy **callback OAuth2 đến bằng session khác** sẽ không tìm thấy authorization request ban đầu và có thể báo lỗi state/correlation. Đừng tắt kiểm tra `state` để vượt lỗi; đó là cơ chế bảo vệ CSRF cho OAuth2 authorization.

Kiểm tra tuần tự:

1. Request bắt đầu OAuth2 login đã có/tạo session chưa? Browser lưu cookie tương ứng chưa?
2. IdP đang redirect về **đúng** `https://<public-host>/login/oauth2/code/{registrationId}`, đúng route/prefix và đúng registrationId không?
3. Ở request callback, browser có đính kèm cookie session trước đó không? Nếu không, đối chiếu `SameSite`, `Secure`, Domain/Path và loại redirect: top-level GET khác `response_mode=form_post`.
4. Nếu callback có cookie nhưng vẫn lỗi, kiểm tra backend tìm được session và authorization request/state không; nếu chạy nhiều instance, kiểm tra shared session store.
5. Sau khi IdP callback thành công và user được redirect về ứng dụng, kiểm tra cookie **sau login** (có thể rotate), sau đó kiểm tra `SecurityContext` ở request tiếp theo.

`SameSite=Lax` thường cho phép cookie trong top-level cross-site **GET navigation** (ví dụ IdP redirect callback GET), nhưng có thể không gửi trong cross-site **POST callback** hoặc iframe. `SameSite=None; Secure` có thể cần khi kiến trúc thực sự cross-site, song vẫn chịu chính sách chặn third-party cookies; đừng thay đổi đại trà nếu chưa có dữ liệu từ browser.

Một lỗi khác: frontend liên tục thực hiện `window.location.assign("/oauth2/authorization/oidc")` khi API trả `401`, kể cả trên login callback hoặc route public. Đây là **vòng redirect ở client**, cần sửa điều kiện điều hướng/route allowlist, không thể giải bằng thay cookie backend.

## 11. SPA, CORS và `fetch(credentials)`

Giả sử frontend tại `https://app.example.org` gọi API có session tại `https://api.example.org`. Đây là **cross-origin**, dù có thể là same-site. Để browser gửi cookie trên cross-origin `fetch`, cần cấu hình đúng cả client và server.

Frontend:

```javascript
const response = await fetch(
  "https://api.example.org/private/whoami",
  {
    method: "GET",
    credentials: "include"
  }
);

if (response.ok) {
  console.log(await response.text());
}
```

Với `fetch`, mặc định `credentials: "same-origin"` **không gửi cookie tới origin khác**. `credentials: "include"` cho phép tham gia cơ chế cookie, nhưng **không vượt qua Domain, Path, Secure, SameSite hay chính sách browser**. Nếu dùng Axios, cấu hình tương ứng là `withCredentials: true` cho request cần cookie.

Backend WebFlux cần cho phép origin rõ ràng và credentialed CORS. Ví dụ khi API này thật sự phải phục vụ frontend nói trên:

```java
package demo;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfiguration {

    @Bean
    CorsWebFilter corsWebFilter() {
        CorsConfiguration policy = new CorsConfiguration();
        policy.setAllowedOrigins(
                List.of("https://app.example.org"));
        policy.setAllowedMethods(
                List.of("GET", "POST", "OPTIONS"));
        policy.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        policy.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", policy);

        return new CorsWebFilter(source);
    }
}
```

Đây là một class có thể biên dịch khi project có `spring-boot-starter-webflux`. Khi ứng dụng đã có CORS ở security chain/`WebFluxConfigurer`/gateway, hãy kiểm tra và **không cấu hình lặp hai lớp trả headers xung đột**.

Những điểm bắt buộc:

- `Access-Control-Allow-Origin` cần phù hợp origin cụ thể, **không dùng `*` với `Access-Control-Allow-Credentials: true`.
- Preflight `OPTIONS` thường không có session/authentication. Nó phải được xử lý đúng thứ tự CORS trước khi policy auth vô tình từ chối.
- Browser không cho JavaScript đọc `Set-Cookie` response header; việc `response.headers.get("Set-Cookie")` cho `null` **không chứng minh server không gửi cookie**. Xem Network/Storage DevTools.
- CORS response OK **không bảo đảm browser sẽ gửi cookie**; vẫn cần `credentials` và cookie attributes hợp lệ.
- Nếu SPA dùng session cookie để xác thực các method thay đổi dữ liệu, cần thiết kế/kiểm tra **CSRF token** và nguồn nhận token; `credentials: "include"` không thay cho CSRF protection.
- Với third-party context, browser có thể chặn cookie dù `SameSite=None; Secure` và CORS đều đúng. Cần phân tích kiến trúc same-site, chính sách browser và các phương án dựa trên top-level navigation thay vì nới lỏng toàn bộ security.

## 12. Dùng log/metrics để xác định đúng lớp lỗi

Trong môi trường thử nghiệm, có thể tạm bật:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.web.server.session: DEBUG
```

Các log cụ thể tùy phiên bản và logger; bật `TRACE` hoặc log request/response toàn bộ có thể vô tình in thông tin nhạy cảm. Không ghi raw Cookie, Authorization, form password, OAuth2 code/state, session ID vào log. Nếu cần correlation giữa gateway và backend, dùng request ID/tracing ID không chứa credential. Nếu cần so sánh session ID, chỉ lưu fingerprint đã băm/HMAC theo chính sách bảo mật và retention hạn chế.

Ví dụ **một WebFilter chẩn đoán tạm thời** chỉ in bucket route, có cookie mang tên `SESSION` hay không, status và tín hiệu Reactor; nó không đọc hoặc log giá trị cookie:

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.server.WebFilter;

@Configuration
class SafeSessionProbeConfig {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeSessionProbeConfig.class);

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter sessionProbe() {
        return (exchange, chain) -> {
            String path = exchange.getRequest().getPath().value();

            // Gộp route vào nhóm cố định; không log raw path/query chứa PII.
            String bucket = path.startsWith("/login")
                    ? "login" : path.startsWith("/oauth2")
                    ? "oauth2" : path.startsWith("/private")
                    ? "private" : "other";

            boolean hasSessionCookie =
                    exchange.getRequest().getCookies()
                            .containsKey("SESSION");

            return chain.filter(exchange).doFinally(signal -> {
                var status = exchange.getResponse().getStatusCode();
                LOG.debug(
                        "bucket={} status={} sessionCookiePresent={} signal={}",
                        bucket,
                        status == null ? "unset" : status.value(),
                        hasSessionCookie,
                        signal);
            });
        };
    }
}
```

Giải thích:

1. `@Order(Ordered.HIGHEST_PRECEDENCE)` giúp probe quan sát sớm request; bảo đảm không sửa response hoặc authentication.
2. `doFinally` chạy khi request reactive complete/error/cancel. Nếu status vẫn chưa được set hoặc response đã bị abort, thông tin có thể không đầy đủ; cần kết hợp access log từ proxy.
3. `sessionCookiePresent=true` chỉ có nghĩa request có cookie **đúng tên**; nó không chứng minh session ID hợp lệ, session tồn tại hay SecurityContext được khôi phục.
4. Buckets chỉ có vài giá trị ổn định, giảm nguy cơ rò dữ liệu từ path động. Tắt probe khi điều tra xong; không biến nó thành log chứa user ID/session ID.
5. Nếu ứng dụng đổi tên cookie, cập nhật probe theo tên thực tế được trả về trong `Set-Cookie`.

Ở backend/Gateway, tập hợp metrics: tổng số redirect theo source/target đã chuẩn hóa, tỷ lệ `401`/`403`, login success/failure, session create/expire/evict, lỗi Redis hoặc session repository, phân bố traffic qua instance, tỷ lệ request có session cookie, và số OAuth2 state mismatch. Một chuỗi nhiều `302` trên cùng trace là tín hiệu cần điều tra, nhưng chỉ đếm redirect không xác định nguyên nhân nếu thiếu cookie/session context.

## 13. Ma trận thử nghiệm tái hiện và phân biệt nguyên nhân

Chọn một tài khoản/test client được phép, một route public, một route protected, một browser profile sạch, và cố định môi trường (localhost, staging qua HTTPS, staging qua gateway). Bảng sau mô tả các ca chính:

| Kịch bản | Điều kỳ vọng | Nếu khác thì xem |
| --- | --- | --- |
| Anonymous `GET /private` | Redirect tới trang login hoặc `401` theo entry point | Chain order, authentication entry point, route policy |
| Anonymous `GET /login` | Hiển thị login page thành công | Login route bị bảo vệ, custom page chưa có controller |
| Login đúng, có CSRF token | Login thành công; có redirect và context được lưu | Auth failure, CSRF, saved request, SecurityContext repo |
| Request kế tiếp cùng browser | Cookie mới nhất được gửi; truy cập thành công | Domain/Path/Secure/SameSite, request mode, session store |
| Xóa session cookie rồi reload | Trở lại trạng thái anonymous theo policy | Test thực sự đang dựa session hay Bearer token khác |
| Mở một tab khác cùng origin | Session được dùng lại khi cookie hợp lệ | Browser profile, partitioned storage, token local to tab |
| Redirect từ IdP về callback GET | State được đối chiếu, authentication thành công | Cookie callback, redirect URI, state repository, shared store |
| Callback OAuth2 POST cross-site nếu sản phẩm dùng | Cookie policy phù hợp flow, state vẫn đúng | `SameSite=Lax/Strict`, browser third-party policy |
| SPA gọi API cross-origin | Request gửi cookie nếu được phép; CORS đúng | `credentials: include`, CORS allowCredentials/allowedOrigins |
| Sau khi chuyển giữa node A/B | Session còn hiệu lực với shared store | Node-local memory session, TTL, namespace, serialization |
| Sau timeout có chủ đích | Session hết hạn và yêu cầu login lại | Timeout repo/cookie khác nhau, eviction |
| HTTPS qua proxy, prefix `/app` | Redirect và cookie giữ đúng host/scheme/prefix | X-Forwarded-* và rewrite Location/Path |
| Form POST thiếu CSRF | Bị từ chối theo security policy | Đừng gọi đây là mất session khi GET vẫn hoạt động |

Đối với mỗi ca, quan sát **request đầu**, **request callback/login POST**, **request đầu tiên sau khi thành công**, rồi so sánh cookie và user-authenticated ở các chặng. Dùng test tích hợp trên cùng ingress để phát hiện vấn đề TLS/forwarded headers mà test nội bộ localhost bỏ qua.

## 14. Quy trình sửa lỗi có kiểm chứng

**Bước 1 — Tách loại luồng đăng nhập.** Xác nhận đây là form login session, OAuth2/OIDC browser login, SPA dùng session cookie hay API Bearer token. Ghi route được bảo vệ, URL login/callback và policy entry point.

**Bước 2 — Bắt toàn bộ chuỗi redirect.** Dùng DevTools Preserve log và theo dõi status/Location; tìm request đầu tiên có sai scheme, host, prefix, route hoặc trạng thái xác thực.

**Bước 3 — Xác minh cookie theo ba chặng.** Server đã gửi `Set-Cookie` chưa? Browser có lưu không? Request tiếp theo có gửi không? Nếu không gửi, tìm nguyên nhân cụ thể ở Domain/Path/Secure/SameSite/credentials/privacy policy, rồi mới sửa cấu hình nhỏ nhất.

**Bước 4 — Kiểm tra session backend.** Nếu cookie có mặt, xác minh resolver nhận đúng tên, session store tìm thấy phiên và session chưa hết hạn. Kiểm tra node, Redis/MongoDB hoặc local memory, timeout, logout, rotation.

**Bước 5 — Kiểm tra SecurityContext.** Nếu session còn nhưng anonymous, xác minh login flow và `ServerSecurityContextRepository`; rà soát custom filters, `NoOpServerSecurityContextRepository` và Reactor Context.

**Bước 6 — Kiểm tra chính sách/security chain.** Nếu auth có hiệu lực nhưng vẫn redirect, đối chiếu `@Order`, `securityMatcher`, `pathMatchers`, endpoint login/callback public và handler cho `401`/`403`.

**Bước 7 — Đối chiếu proxy/IdP.** Nếu chỉ lỗi bên ngoài máy local, sửa `Forwarded` headers ở trusted proxy, `server.forward-headers-strategy`, public redirect URI và cookie Path/Domain. Nếu chỉ lỗi khi IdP callback, kiểm tra state/session correlation trước khi đụng tới policy.

**Bước 8 — Test lại toàn bộ hành vi.** Đăng nhập mới, refresh, mở tab khác, logout, hết hạn, đổi instance, redirect OAuth2, cross-origin requests; so sánh status, cookie và authentication qua từng hop. Sau mỗi thay đổi chỉ chạy lại kịch bản liên quan rồi mở rộng regression; tránh sửa nhiều biến cùng lúc.

## 15. Những cách “sửa nhanh” dễ làm tình hình tệ hơn

- **Tắt CSRF toàn ứng dụng** vì form login POST trả `403`: che sự cố token, tăng rủi ro cho ứng dụng dùng cookie.
- **Dùng `permitAll()` cho cả endpoint protected** để hết redirect loop: loại bỏ kiểm soát truy cập thay vì sửa nguyên nhân.
- **Tắt `Secure` trên production HTTPS** chỉ vì backend kết nối với proxy bằng HTTP: cookie Secure chỉ phụ thuộc vào giao thức mà browser nhìn thấy, không phải giao thức nội bộ sau TLS termination.
- **Dùng `SameSite=None` mọi nơi** mà không có `Secure`/HTTPS và đánh giá browser third-party policy: browser có thể từ chối cookie, phạm vi truyền cookie cũng rộng hơn.
- **Đặt `Access-Control-Allow-Origin: *` cùng `Access-Control-Allow-Credentials: true`:** browser từ chối credentialed CORS; đồng thời cho phép origin quá rộng nếu dùng cấu hình sai.
- **Dựa vào `document.cookie` để kết luận session cookie vắng mặt:** `HttpOnly` cố tình chặn JS đọc cookie.
- **Bật Spring Session rồi bỏ qua kiểm chứng actual bean/store:** dependency không đảm bảo mọi request dùng shared reactive repository đúng cấu hình.
- **Lấy `SecurityContextHolder` thread-local để xác định user ở WebFlux:** có thể đo nhầm do thread đổi; dùng Reactor Context.
- **Log toàn bộ request headers/HAR để debug:** rò session ID, OAuth2 state/code và credential.
- **Bỏ kiểm tra `state` OAuth2 hoặc chuyển tiếp code/token qua URL debug:** phá cơ chế bảo vệ và mở đường tấn công.
- **Dựa vào curl để khẳng định browser SameSite/CORS không lỗi:** curl không thực thi đầy đủ chính sách browser.
- **So sánh ID phiên trước và sau login bắt buộc giống nhau:** Spring Security có thể cố ý đổi ID để chống session fixation.

## 16. Tiêu chí kết luận và tài liệu đọc tiếp

Chỉ kết luận đã xử lý được lỗi khi có **bằng chứng đầy đủ**: request đăng nhập hợp lệ, response đúng redirect, cookie mới nhất được browser chấp nhận, request kế tiếp gửi cookie đúng host/path/scheme, server tìm được session, SecurityContext được khôi phục, route protected trả kết quả đúng và luồng hoạt động ổn định qua HTTPS/ingress/instance thật. Với OAuth2, phải chứng minh callback đối chiếu `state` hợp lệ; với SPA, phải chứng minh credentialed CORS và CSRF vẫn đúng. Những lần đổi session ID có chủ đích không được tính là lỗi.

Tài liệu chính thức để tra cứu API và cấu hình:
- [Spring Security — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html)
- [Spring Security — Reactive OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html)
- [Spring Security — WebSessionServerSecurityContextRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html)
- [Spring Boot 3.3 — Common Application Properties (reactive session)](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
- [Spring Framework — CORS cho WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html)
- [Spring Boot 3.3 — Spring Session reactive](https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html)
- [Spring Session — WebSession integration](https://docs.spring.io/spring-session/reference/web-session.html).