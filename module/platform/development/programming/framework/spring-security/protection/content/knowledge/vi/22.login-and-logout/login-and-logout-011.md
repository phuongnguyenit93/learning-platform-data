# Phối hợp xóa cookie, session, cache và trạng thái frontend

Đăng xuất trong ứng dụng web không chỉ là chuyển người dùng về trang đăng nhập. Một phiên có thể hiện diện đồng thời trong **Spring Security**, kho **HTTP session**, cookie của trình duyệt, cơ chế **remember-me**, cache HTTP và trạng thái của ứng dụng frontend. Nếu chỉ xóa một lớp, người dùng có thể nhìn thấy thông tin cũ, một tab khác vẫn dùng phiên, hoặc hệ thống tự đăng nhập trở lại.

Bài học thuộc chương **Đăng nhập và đăng xuất** của **SPRING_SECURITY_HTTP_PROTECTION**. Trọng tâm là phối hợp các lớp phòng vệ HTTP và trình duyệt trong Spring Security cho cả Servlet và Reactive, quan sát kết quả trên trình duyệt, kiểm thử các đường đi đăng xuất và chẩn đoán sai khác giữa trạng thái phía máy chủ với frontend.

## 1. Xác định đúng thứ cần xóa

Trước khi thiết kế luồng đăng xuất, cần phân biệt các lớp trạng thái và bên có quyền thu hồi chúng.

| Lớp trạng thái | Ví dụ | Bên có quyền xử lý | Kỳ vọng sau đăng xuất |
|---|---|---|---|
| Ngữ cảnh bảo mật | Authentication trong SecurityContext | Spring Security | Yêu cầu tiếp theo không còn được nhận là người dùng cũ |
| Phiên HTTP | HttpSession, WebSession, session trong Redis | Máy chủ hoặc session store | Session ID cũ không còn mở được phiên đã xác thực |
| Cookie xác thực | JSESSIONID, SESSION, remember-me, cookie ứng dụng | Máy chủ gửi Set-Cookie; trình duyệt lưu | Cookie phù hợp được hết hạn; thông tin xác thực liên quan bị vô hiệu |
| Token đăng nhập | Access token, refresh token, opaque token | Máy chủ phát hành/token store và client | Token có thể thu hồi đã bị thu hồi; token tự chứa có chính sách hết hạn hoặc danh sách chặn phù hợp |
| Cache HTTP | HTML, JSON hồ sơ, dữ liệu API riêng tư | Máy chủ/proxy/trình duyệt | Phản hồi nhạy cảm không được lưu lại để tái sử dụng |
| Trạng thái frontend | Store, bộ nhớ JS, localStorage, sessionStorage, IndexedDB | Ứng dụng frontend | Không giữ dữ liệu người dùng hoặc thông tin xác thực cũ |
| Cache do Service Worker quản lý | Cache Storage, bản sao phản hồi offline | Service Worker/frontend | Các entry riêng tư được loại khỏi vùng cache ứng dụng |
| Trạng thái ngoài ứng dụng | Phiên của IdP/OIDC, những thiết bị và tab khác | IdP, hệ thống quản lý phiên, client khác | Được xử lý theo phạm vi đăng xuất đã công bố |

**Phân biệt ba thao tác:** *xóa cookie* loại bỏ dữ liệu mà trình duyệt gửi; *hủy session* làm máy chủ từ chối phiên cũ; *xóa dữ liệu frontend* loại bỏ dữ liệu đang hiển thị hoặc lưu cục bộ. Ba thao tác bổ trợ nhau. Một cookie session đã bị xóa vẫn không bảo đảm phiên trên Redis đã bị hủy, và một session đã bị hủy vẫn không tự dọn hồ sơ lưu trong localStorage.

### Xác định phạm vi trước khi triển khai

- **Đăng xuất tab hiện tại:** yêu cầu backend hủy phiên đang dùng và xóa dữ liệu ứng dụng trong tab này.
- **Đăng xuất toàn bộ tab trên cùng origin:** cần phát tín hiệu để các tab còn lại xóa store và điều hướng; tín hiệu trình duyệt chỉ giúp đồng bộ giao diện, còn xác thực thực sự do backend quyết định.
- **Đăng xuất mọi thiết bị:** cần nghiệp vụ thu hồi tất cả phiên/token của tài khoản; mặc định hủy HttpSession hiện tại không làm việc này.
- **Đăng xuất khỏi SSO:** phải xét riêng phiên của nhà cung cấp danh tính (IdP); logout tại ứng dụng không đồng nghĩa logout khỏi IdP.

## 2. Thứ tự xử lý đăng xuất với phiên cookie

Đối với ứng dụng dùng session và cookie, luồng thường gồm:

1. Frontend chặn thao tác mới và che dữ liệu nhạy cảm trong lúc yêu cầu đang thực hiện.
2. Trình duyệt gửi **POST /logout** kèm cookie hiện tại và CSRF token hợp lệ khi CSRF đang bật.
3. Spring Security xóa SecurityContext, vô hiệu hóa phiên HTTP hiện tại và chạy các LogoutHandler được cấu hình, bao gồm xử lý remember-me nếu cơ chế này được dùng.
4. Máy chủ gửi chỉ dẫn hết hạn những cookie riêng của ứng dụng và phản hồi thành công, chẳng hạn **204 No Content** cho SPA.
5. Chỉ sau khi nhận phản hồi thành công, frontend xác nhận đã đăng xuất: xóa store và vùng lưu trữ liên quan, thông báo cho các tab cùng origin, rồi điều hướng bằng thao tác thay thế lịch sử.
6. Khi người dùng quay lại trang bảo vệ, backend luôn kiểm tra xác thực mới; dữ liệu cũ không được phục vụ từ cache riêng tư.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant F as Frontend / trình duyệt
    participant S as Spring Security
    participant D as Session store
    U->>F: Chọn đăng xuất
    F->>F: Che dữ liệu và khóa thao tác nhạy cảm
    F->>S: POST /logout + cookie + CSRF
    S->>S: Xử lý LogoutHandler, xóa SecurityContext
    S->>D: Vô hiệu hóa session hiện tại
    S-->>F: 204 + Set-Cookie hết hạn (nếu có)
    F->>F: Xóa state và dữ liệu riêng tư
    F->>F: Thông báo các tab cùng origin
    F-->>U: Điều hướng về màn hình đăng nhập
~~~

Nếu kết nối bị ngắt, frontend có thể chưa biết server đã hủy phiên hay chưa. Lúc này cần **ẩn dữ liệu nhạy cảm, báo trạng thái chưa xác nhận và cho phép thử lại**; không được thông báo đăng xuất thành công chỉ vì đã xóa localStorage. Nếu nhiều request đang chạy song song, API bảo vệ vẫn phải kiểm tra phiên tại thời điểm xử lý từng request. Request đã hoàn tất trước khi phiên bị hủy không thể được “thu hồi” chỉ bằng thao tác logout sau đó.

## 3. Cấu hình Spring Security Servlet

Trong ứng dụng Servlet dùng form login và HttpSession, Spring Security cung cấp bộ xử lý logout thông qua **LogoutFilter**. Khi CSRF được bật (mặc định trong cấu hình thông dụng), request thực hiện logout là POST. Với giao diện HTML, biểu mẫu có thể chứa trường CSRF do framework sinh ra; với SPA, frontend gửi token qua header phù hợp với CsrfTokenRepository hiện hành.

Ví dụ sau dùng Spring Security kiểu cấu hình lambda, trả về HTTP 204 để frontend kiểm soát điều hướng. Cookie **UI_HINT** là ví dụ cookie riêng của ứng dụng đã được tạo với Path=/ và không mang vai trò xác thực.

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.HttpStatusReturningLogoutSuccessHandler;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .addLogoutHandler((request, response, authentication) -> {
                    ResponseCookie expiredHint = ResponseCookie
                        .from("UI_HINT", "")
                        .path("/")
                        .httpOnly(true)
                        .secure(true)
                        .sameSite("Lax")
                        .maxAge(Duration.ZERO)
                        .build();
                    response.addHeader(
                        HttpHeaders.SET_COOKIE,
                        expiredHint.toString()
                    );
                })
                .logoutSuccessHandler(
                    new HttpStatusReturningLogoutSuccessHandler(
                        HttpStatus.NO_CONTENT
                    )
                )
                .permitAll());

        return http.build();
    }
}
~~~

Các điểm cần hiểu khi vận dụng:

- **invalidateHttpSession(true)** vô hiệu hóa HttpSession của request hiện tại, bao gồm dữ liệu liên quan trong session store được cấu hình đúng. Spring Security xử lý xóa SecurityContext trong quy trình logout; **clearAuthentication(true)** làm rõ yêu cầu đó.
- **LogoutHandler** bổ sung thao tác cần hoàn thành trước khi phản hồi thành công, ví dụ hết hạn cookie ứng dụng hoặc thu hồi refresh token phía server. Không viết tác vụ có khả năng ném lỗi không xử lý vào handler nếu điều đó làm hỏng phản hồi logout.
- **HttpStatusReturningLogoutSuccessHandler** trả 204, thích hợp cho ứng dụng gọi logout qua fetch. Nếu dùng MVC điều hướng phía máy chủ, có thể chọn **logoutSuccessUrl("/login?logout")** thay cho success handler trả 204.
- **permitAll()** cho phép truy cập endpoint logout theo chính sách ủy quyền. Điều đó không bỏ qua kiểm tra CSRF: POST logout không có token hợp lệ vẫn có thể bị chặn với 403.
- Chỉ hết hạn cookie **UI_HINT** vì ví dụ đã biết phạm vi Path của cookie này. Với **JSESSIONID**, có thể cân nhắc deleteCookies("JSESSIONID"), nhưng việc xóa cookie session phụ thuộc Path/Domain và servlet container; vô hiệu hóa session phía server mới là điểm kiểm soát bắt buộc.

Khi cấu hình **remember-me**, Spring Security có thể đăng ký bộ dọn remember-me trong luồng logout. Cần kiểm tra cơ chế remember-me đang dùng có xóa cookie và, với persistent token, xóa bản ghi token trên server. Nếu cookie remember-me còn hiệu lực, một request sau logout có thể âm thầm xác thực lại dù HttpSession cũ đã bị hủy.

### Cookie hết hạn phải đúng phạm vi

Để xóa một cookie bằng Set-Cookie, máy chủ gửi cùng **tên**, **Path** và **Domain** tương ứng với cookie đã tạo, cùng **Max-Age=0** hoặc Expires ở quá khứ. Domain không khai báo (host-only) khác với cookie được tạo bằng Domain cụ thể. Secure, HttpOnly và SameSite cần được cấu hình nhất quán với chính sách cookie, nhưng không thay thế cho việc khớp tên/Path/Domain. Cookie phân vùng có thể còn yêu cầu xử lý đúng partition key.

Ví dụ HTTP khi cookie ứng dụng ban đầu có Path=/:

~~~http
HTTP/1.1 204 No Content
Set-Cookie: UI_HINT=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Không cố xóa cookie **HttpOnly** bằng JavaScript: trình duyệt cố ý không cho mã JavaScript đọc hoặc sửa cookie loại này. Máy chủ phải gửi Set-Cookie hết hạn. Ngược lại, việc gửi Set-Cookie hết hạn không thu hồi phiên hoặc token phía server nếu phiên/token đó vẫn hợp lệ.

## 4. Cache HTTP và dữ liệu trang riêng tư

Logout không thể đảm bảo “thu hồi” nội dung người dùng đã nhìn thấy hoặc đã tải xuống. Vì vậy, với HTML chứa dữ liệu cá nhân, JSON của API đã xác thực và phản hồi khác có thông tin nhạy cảm, cần thiết lập chính sách cache **ngay khi phục vụ dữ liệu**.

| Header hoặc cơ chế | Ý nghĩa thực tế |
|---|---|
| Cache-Control: no-store | Yêu cầu cache tuân thủ chuẩn không lưu phản hồi; là lựa chọn chính cho nội dung riêng tư nhạy cảm |
| Cache-Control: no-cache | Cho phép lưu nhưng phải xác thực lại trước khi tái sử dụng; **không đồng nghĩa** không lưu |
| Cache-Control: private | Cho phép cache riêng của trình duyệt lưu; không đủ khi muốn tránh lưu thông tin nhạy cảm |
| Pragma: no-cache, Expires: 0 | Chủ yếu hỗ trợ tương thích với thành phần cũ; không thay thế no-store |
| Clear-Site-Data | Yêu cầu trình duyệt xóa một số dữ liệu site sau phản hồi; có khác biệt về hỗ trợ và phạm vi tác động |

Spring Security Servlet thường đã đặt các header chống cache cho phản hồi qua filter chain của nó. Tuy nhiên, cần **kiểm tra header thực tế** khi có controller tự gán Cache-Control, reverse proxy, CDN, tải file, hoặc API nằm ngoài security filter chain. Một ví dụ chủ động ở controller là:

~~~java
@GetMapping("/api/me")
ResponseEntity<UserDto> currentUser(Authentication authentication) {
    UserDto profile = userService.load(authentication.getName());
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(profile);
}
~~~

Đoạn controller chỉ minh họa vị trí thiết lập header; UserDto và userService là thành phần nghiệp vụ của ứng dụng. Trong hệ thống có proxy/CDN, phải xác minh chúng không cache nhầm phản hồi theo cookie/Authorization. Chính sách cache áp dụng cho phản hồi nhạy cảm tại thời điểm truy xuất, không đợi tới khi người dùng nhấn đăng xuất.

### Khi nào dùng Clear-Site-Data?

Với ứng dụng có một origin riêng biệt, có thể cân nhắc bổ sung header **Clear-Site-Data** trên phản hồi logout thông qua HeaderWriterLogoutHandler:

~~~java
// Các import liên quan:
// HeaderWriterLogoutHandler
// ClearSiteDataHeaderWriter
// static import ClearSiteDataHeaderWriter.Directive.*;

.addLogoutHandler(new HeaderWriterLogoutHandler(
    new ClearSiteDataHeaderWriter(CACHE, STORAGE, COOKIES)
))
~~~

Đây là **một lựa chọn mở rộng**, không phải điều kiện để logout hợp lệ. Chỉ bật sau khi kiểm tra mức hỗ trợ của trình duyệt mục tiêu và tác động tới những ứng dụng dùng chung origin/domain. Chỉ thị **COOKIES** có thể có tác động rộng đến cookie liên quan tới domain; **STORAGE** có thể xóa dữ liệu của chức năng offline hoặc ứng dụng khác cùng origin; **CACHE** có thể làm tăng tải lại tài nguyên. Không coi header này là phương án thay thế cho invalidation session, revoke token hoặc tự quản lý cache riêng tư của frontend.

### Nút Back, bfcache và lịch sử điều hướng

Một số trình duyệt có thể khôi phục trang từ **back-forward cache (bfcache)** khi người dùng nhấn Back. Trang đã khôi phục có thể tạm hiển thị trạng thái giao diện cũ dù request API mới đã bị từ chối. Nên:

- Dùng **location.replace(...)** sau khi logout thành công để tránh giữ màn hình hiện tại như một bước điều hướng thông thường.
- Xóa dữ liệu nhạy cảm trong store và đồng bộ tới tab khác; không dựa hoàn toàn vào no-store để dọn mọi dạng bộ nhớ của trang.
- Khi trang được phục hồi (ví dụ sự kiện **pageshow** với persisted=true), kiểm tra lại trạng thái xác thực, dọn state nếu phiên không hợp lệ, và điều hướng về trang đăng nhập.
- Luôn bảo vệ API phía server: một trang cũ còn hiển thị không được có quyền gọi API bảo vệ bằng phiên đã hủy.

## 5. Đồng bộ frontend khi đăng xuất

Với SPA, thứ tự và kết quả request quan trọng hơn việc gọi hàng loạt lệnh xóa dữ liệu. Ví dụ dưới đây giả định server đã cấu hình trả **204**, và template trang đã xuất CSRF token cùng tên header vào hai thẻ meta. Tên key lưu trữ chỉ là ví dụ, cần thay bằng danh sách key của ứng dụng thực tế.

~~~html
<meta name="_csrf" content="TOKEN_DO_SERVER_RENDER">
<meta name="_csrf_header" content="X-CSRF-TOKEN">
~~~

~~~javascript
let currentUser = null;
let accessTokenInMemory = null;
let logoutInProgress = false;

const authChannel = typeof BroadcastChannel !== "undefined"
    ? new BroadcastChannel("app-auth")
    : null;

function clearClientAuthState() {
    currentUser = null;
    accessTokenInMemory = null;

    localStorage.removeItem("app:user");
    sessionStorage.removeItem("app:private-form");

    // Với React/Vue/Angular: reset auth store, query cache và router state.
    // Nếu có IndexedDB/Cache Storage riêng tư: xóa các entry thuộc app.
}

authChannel?.addEventListener("message", (event) => {
    if (event.data?.type === "LOGGED_OUT") {
        clearClientAuthState();
        window.location.replace("/login");
    }
});

async function logout() {
    if (logoutInProgress) return;
    logoutInProgress = true;

    // Tầng UI cần che dữ liệu nhạy cảm và khóa thao tác ngay tại đây.
    const csrfToken = document.querySelector(
        'meta[name="_csrf"]'
    )?.content;
    const csrfHeader = document.querySelector(
        'meta[name="_csrf_header"]'
    )?.content;

    try {
        if (!csrfToken || !csrfHeader) {
            throw new Error("Thiếu CSRF token cho yêu cầu logout");
        }

        const response = await fetch("/logout", {
            method: "POST",
            credentials: "same-origin",
            headers: { [csrfHeader]: csrfToken }
        });

        if (response.status !== 204) {
            throw new Error("Logout HTTP " + response.status);
        }

        clearClientAuthState();
        authChannel?.postMessage({ type: "LOGGED_OUT" });
        window.location.replace("/login?logout");
    } catch (error) {
        clearClientAuthState();
        // Hiển thị lỗi và hành động thử lại; chưa xác nhận server đã logout.
        throw error;
    } finally {
        logoutInProgress = false;
    }
}
~~~

Mã mẫu minh họa hợp đồng giữa backend và frontend; cần nối vào UI thật để che dữ liệu, hiển thị lỗi và dọn store/cache theo framework đang dùng. Nếu request thất bại hoặc mất kết nối, ứng dụng có thể tự xóa dữ liệu cục bộ nhằm hạn chế lộ dữ liệu, nhưng phải giữ trạng thái **“chưa xác nhận server đã đăng xuất”** và cung cấp cách thử lại. Không chuyển sang thông báo “đăng xuất thành công” chỉ vì giao diện đã rỗng.

**CSRF token:** tên header phải lấy từ cấu hình thực tế. Với CookieCsrfTokenRepository, header thường là **X-XSRF-TOKEN**; với repository khác có thể là **X-CSRF-TOKEN**. Token có thể được làm mới sau đăng nhập/đăng xuất. Frontend phải lấy token mới theo cơ chế mà backend công bố trước lần đăng nhập hoặc request thay đổi trạng thái tiếp theo. Không tắt CSRF chỉ để request logout “chạy được”.

**Nhiều tab:** BroadcastChannel giúp những tab cùng origin cập nhật ngay sau logout. Nếu không hỗ trợ, có thể sử dụng sự kiện storage với một key tín hiệu hoặc kiểm tra lại phiên khi tab được focus. Đồng bộ tab là trải nghiệm người dùng, không thay thế vô hiệu hóa phiên phía server. Các tab trên origin khác không nhận được BroadcastChannel.

**Service Worker và bộ nhớ dài hạn:** nếu ứng dụng chủ động cache API riêng tư, cần định danh cache theo mục đích, xóa entry liên quan khi logout và tránh cache lại phản hồi nhạy cảm từ đầu. Tránh xóa vô điều kiện toàn bộ localStorage, IndexedDB hay Cache Storage trên origin dùng chung vì có thể phá dữ liệu hợp lệ của chức năng hoặc ứng dụng khác.

## 6. Triển khai tương ứng cho WebFlux / Reactive

Trong Spring Security Reactive, ứng dụng dùng **SecurityWebFilterChain**, **WebSession** và các kiểu **ServerLogoutHandler**. Không dùng SecurityContextHolder hoặc HttpSession kiểu Servlet để quản lý trạng thái phiên của WebFlux. Cần chủ động xác minh security context đã được xóa và WebSession đã bị vô hiệu hóa với cách lưu context/session hiện hành.

Ví dụ bên dưới phối hợp một handler xóa security context với handler hủy WebSession hiện tại, rồi trả HTTP 204:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.HttpStatusReturningServerLogoutSuccessHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.ServerLogoutHandler;
import org.springframework.web.server.WebSession;

@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    ServerLogoutHandler clearContext = new SecurityContextServerLogoutHandler();
    ServerLogoutHandler invalidateSession = (exchange, authentication) ->
        exchange.getExchange().getSession().flatMap(WebSession::invalidate);

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/login", "/assets/**").permitAll()
            .anyExchange().authenticated())
        .formLogin(Customizer.withDefaults())
        .logout(logout -> logout
            .logoutHandler((exchange, authentication) ->
                clearContext.logout(exchange, authentication)
                    .then(invalidateSession.logout(exchange, authentication)))
            .logoutSuccessHandler(
                new HttpStatusReturningServerLogoutSuccessHandler(
                    HttpStatus.NO_CONTENT
                )
            ))
        .build();
}
~~~

Với ứng dụng có **ServerSecurityContextRepository** tùy chỉnh, handler xóa security context phải sử dụng đúng repository đang giữ phiên. Kiểm thử request tiếp theo bằng cookie session cũ để xác minh không thể khôi phục Authentication. Phần dọn cookie riêng và trạng thái SPA vẫn cần thực hiện theo hợp đồng tương tự Servlet; các API Reactive dùng **ServerWebExchange** và response cookie tương ứng.

Không tự viết handler chỉ hủy WebSession rồi vô tình thay thế handler xóa SecurityContext. Nếu tự xây dựng logout pipeline, cả hai việc đều phải được bao phủ. Trên WebFlux, CSRF và quy tắc POST logout vẫn cần được kiểm tra theo cấu hình cụ thể.

## 7. Những trường hợp logout cần xử lý thêm

### Phiên nằm trong Redis hoặc nhiều node

Khi dùng **Spring Session** với Redis hay kho phân tán, hủy phiên hiện tại phải tác động tới chính kho phiên được các node sử dụng. Kiểm thử đi qua hai node: logout ở node A, sau đó dùng session cookie cũ gọi API ở node B. Nếu API ở B vẫn thành công, cần kiểm tra cấu hình shared session repository, hiệu lực xóa session và cache nội bộ; xóa cookie trên trình duyệt chưa đủ.

### JWT, opaque token, refresh token

Ứng dụng **stateless dùng Bearer token** có thể không sử dụng HttpSession. Khi ấy, invalidateHttpSession không thể làm JWT đã phát hành mất hiệu lực. Logout cần thu hồi refresh token ở nơi lưu token, vô hiệu opaque token nếu hệ thống hỗ trợ, và chọn thời hạn sống/danh sách chặn hoặc cơ chế thu hồi thích hợp cho access token. JWT tự chứa thường vẫn có thể được xác thực đến khi hết hạn nếu không có biện pháp thu hồi bổ sung. Xóa token khỏi bộ nhớ frontend chỉ khiến client hiện tại ngừng gửi token.

### SSO/OIDC

Logout cục bộ và logout tại **Identity Provider** là hai nghiệp vụ khác nhau. Với OIDC, có thể dùng luồng RP-initiated logout (chẳng hạn **OidcClientInitiatedLogoutSuccessHandler** trong cấu hình thích hợp), front-channel/back-channel logout nếu nhà cung cấp hỗ trợ. Cần xác định trước có chủ đích kết thúc chỉ phiên ứng dụng hay phiên đăng nhập một lần của cả hệ thống, tránh làm người dùng mất phiên ở ứng dụng khác ngoài dự kiến.

### Frontend và backend khác origin

Nếu SPA và API ở hai origin, fetch có thể cần **credentials: "include"**; backend phải cấu hình CORS với origin cụ thể và cho phép credentials khi cần. Cookie cross-site có thể cần SameSite=None và Secure. CORS không thay thế CSRF: cần cơ chế cấp và xác minh CSRF token tương thích với kiến trúc. Cookie do một origin sở hữu phải được hết hạn tại phạm vi được phép của origin/domain đó.

### Đăng xuất khỏi mọi thiết bị

Hủy session hiện tại không tự thu hồi session của điện thoại, máy tính khác hoặc refresh token đã cấp. Nếu sản phẩm có chức năng “đăng xuất trên mọi thiết bị”, backend cần duyệt và vô hiệu các session/token gắn với tài khoản, xử lý eventual consistency nếu kho phân tán, và kiểm thử trên nhiều client độc lập.

## 8. Kiểm thử theo từng lớp

Chỉ nhìn thấy trang đăng nhập sau logout là chưa đủ. Nên kiểm thử hành vi qua HTTP, session store và trình duyệt:

| Tình huống | Cách thử | Kết quả mong đợi |
|---|---|---|
| Logout hợp lệ | Đăng nhập, POST /logout với CSRF và cookie hợp lệ | Phản hồi 204 theo ví dụ; session bị hủy; cookie riêng được cho hết hạn |
| Thiếu CSRF | POST /logout khi CSRF bật nhưng bỏ token | Request bị từ chối (thông thường 403); phiên không bị hủy ngoài ý muốn |
| Tái sử dụng session cũ | Ghi lại cookie session, logout, gửi lại cookie tới API bảo vệ | Không truy cập được với danh tính cũ; mã 401/302 tùy cơ chế đăng nhập |
| Remember-me | Đăng nhập với remember-me, logout, mở request mới | Không tự đăng nhập lại bằng token remember-me còn sót |
| Nội dung riêng tư | Mở profile trước và sau logout, kiểm tra Network | Phản hồi riêng tư có no-store; API không trả hồ sơ bằng phiên đã hủy |
| Hai tab | Mở cùng tài khoản ở hai tab; logout ở tab A | Tab B dọn state/điều hướng, và request có phiên cũ bị server từ chối |
| Back/bfcache | Đăng xuất rồi nhấn Back hoặc khôi phục tab | UI không duy trì hiển thị dữ liệu riêng tư; xác thực được kiểm tra lại |
| Request thất bại | Ngắt mạng đúng lúc logout | UI che dữ liệu, báo logout chưa xác nhận và cho phép thử lại |
| Session phân tán | Đăng nhập qua node A, logout A, gọi API node B với cookie cũ | Node B không chấp nhận phiên đã hủy |
| Bearer/OIDC | Thử refresh token cũ hoặc khởi tạo SSO mới sau logout | Hành vi đúng với phạm vi thu hồi token và IdP đã thiết kế |

Với **MockMvc**, có thể bắt đầu bằng kiểm thử CSRF và status của endpoint đã cấu hình:

~~~java
mockMvc.perform(post("/logout"))
    .andExpect(status().isForbidden());

mockMvc.perform(post("/logout").with(csrf()))
    .andExpect(status().isNoContent());
~~~

Hai lệnh trên chỉ chứng minh quy tắc request/response của endpoint, **không tự chứng minh session cũ đã bị hủy**. Để kiểm tra thực chất, hãy đăng nhập bằng một phiên thật, giữ cookie/session ID, logout và thử dùng lại định danh đó để truy cập tài nguyên bảo vệ. Với WebFlux, làm điều tương tự bằng WebTestClient và WebTestClient security test helpers tương ứng.

Khi kiểm thử trên browser DevTools, quan sát **Network → Headers** của logout, những phản hồi API chứa dữ liệu riêng tư, **Application/Storage → Cookies**, Local Storage và Cache Storage. Lưu ý công cụ DevTools hiển thị trạng thái cookie cuối cùng; để tìm lỗi Path/Domain, cần kiểm tra cả giá trị **Set-Cookie** ban đầu và giá trị được gửi khi logout.

## 9. Chẩn đoán các biểu hiện thường gặp

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Gọi logout bị 403 | Thiếu CSRF token, header sai tên, token cũ | Kiểm tra CsrfTokenRepository và tên header/token hiện tại; gửi POST hợp lệ |
| Trang đã chuyển về login nhưng API vẫn truy cập được | Logout chỉ điều hướng frontend; phiên/token server còn hiệu lực | Bảo đảm request tới LogoutFilter/LogoutWebFilter và cơ chế thu hồi phiên/token thực sự chạy |
| Cookie vẫn còn trong browser | Xóa sai Path/Domain; cookie session do container quản lý; cookie được phát lại | So sánh Set-Cookie khi tạo/xóa; kiểm tra request response sau logout |
| Tự đăng nhập lại ngay sau logout | Remember-me hoặc phiên SSO/IdP vẫn còn | Thu hồi persistent token/điều chỉnh phạm vi logout IdP theo yêu cầu |
| Back hiển thị hồ sơ cũ | Store/bfcache/SPA history còn dữ liệu | Dọn store, replace history, tái xác thực khi phục hồi; bảo vệ API ở server |
| Tab khác vẫn hiển thị dữ liệu | Không có BroadcastChannel/storage event hoặc tab không lắng nghe | Đồng bộ logout và kiểm tra lại phiên khi tab được focus |
| Logout thành công trên node A nhưng node B vẫn cho vào | Session store không đồng nhất, TTL/replication hay cache xác thực còn lệch | Kiểm tra session repository phân tán và invalidation qua nhiều node |
| Sau logout một ứng dụng khác mất dữ liệu | Clear-Site-Data phạm vi quá rộng hoặc xóa toàn bộ origin storage | Chỉ xóa key/cache có namespace ứng dụng; cân nhắc lại phạm vi header |

### Bài thực hành tích hợp

Giả sử ứng dụng bán hàng dùng Spring MVC, session Redis, cookie UI_HINT, frontend SPA và hai tab mở đồng thời. Yêu cầu nghiệp vụ: khi đăng xuất ở bất kỳ tab nào, mọi tab ở cùng origin ngừng hiển thị đơn hàng cũ, session ID cũ không gọi được API, nhưng dữ liệu ngoại tuyến không nhạy cảm vẫn được giữ.

Một cách triển khai hợp lý là: dùng Spring Security logout để hủy session Redis và xóa SecurityContext; trả 204 và hết hạn cookie UI_HINT đúng Path; bật no-store cho API đơn hàng; dọn duy nhất store và cache chứa dữ liệu đơn hàng; phát BroadcastChannel để các tab cập nhật; sau đó kiểm thử lại session ID cũ trên một node khác. Không dùng Clear-Site-Data: "storage" nếu còn cần giữ dữ liệu ngoại tuyến hợp lệ trên cùng origin.

**Tiêu chí hoàn thành:** sau logout, request mới từ cả tab A lẫn tab B đều không truy cập được API bảo vệ bằng phiên cũ; không tab nào còn hiển thị hồ sơ/đơn hàng cũ; thông tin đã cache không quay lại khi nhấn Back; cơ chế remember-me và SSO có hành vi đúng phạm vi đã chọn; và lỗi mạng khi logout được thông báo rõ ràng thay vì hiển thị thành công giả.
