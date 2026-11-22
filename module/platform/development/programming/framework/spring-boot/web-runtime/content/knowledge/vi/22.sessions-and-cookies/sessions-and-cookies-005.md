# Phân biệt cookie do máy chủ quản lý với cookie do ứng dụng tự tạo

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Phiên và cookie

## 1. Hiểu đúng hai loại cookie trong một ứng dụng web

Trong HTTP, **cookie** là cặp tên–giá trị kèm những thuộc tính phạm vi, thời hạn và an toàn. Phản hồi máy chủ có thể gửi header **Set-Cookie**; trình duyệt quyết định lưu cookie rồi gửi lại những cặp phù hợp trong header **Cookie** ở các request sau.

Trong Spring Boot chạy trên **Servlet stack**, hai trường hợp hay gặp là:

1. **Cookie phiên do Servlet container hoặc cơ chế quản lý phiên phát hành**, thường là **JSESSIONID**: chứa **session ID** dùng để tra cứu trạng thái **HttpSession** phía máy chủ. Ứng dụng thường tạo/đọc HttpSession; container quản lý việc phát và nhận ID theo cơ chế session tracking.
2. **Cookie tùy chỉnh do mã ứng dụng chủ động tạo**, ví dụ **ui_theme=dark**, **locale=vi** hoặc một token có cơ chế xác thực riêng: ứng dụng quyết định tên, giá trị, lúc phát hành, thời hạn, phạm vi, cách kiểm tra và lúc xóa. Cookie này **không tự trở thành HttpSession** chỉ vì nó được trả từ cùng một server.

**Điểm phân biệt là quyền sở hữu ngữ nghĩa và vòng đời.** Cả hai đều là HTTP cookie, đều thường được browser lưu và gửi tự động theo Domain/Path/Secure/SameSite; từ phía trình duyệt không có hai giao thức cookie riêng. Cụm từ "cookie do máy chủ quản lý" trong bài này chỉ cookie gắn với **cơ chế session tracking** của Servlet/Spring Session; không có nghĩa dữ liệu không đi qua browser hay application cookie chỉ được tạo ở JavaScript.

### Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **session ID** với **nội dung HttpSession**, và chứng minh JSESSIONID không chứa toàn bộ object của người dùng.
- Đọc các header **Set-Cookie** và **Cookie**, nhận ra tên/giá trị nào do framework/container sinh và cái nào do controller/service sinh.
- Tạo demo Spring Boot 3.x + Java 17+ vừa dùng **HttpSession** vừa phát cookie **ui_theme** riêng, rồi kiểm thử bằng curl và cookie jar.
- Cấu hình cookie phiên qua **server.servlet.session.cookie.***; cấu hình cookie tùy chỉnh qua **ResponseCookie** hoặc Servlet **Cookie**.
- Phân biệt **thời hạn cookie trong browser** và **thời hạn dữ liệu session trên server**.
- Chọn **HttpOnly, Secure, SameSite, Path, Domain, Max-Age** phù hợp và xử lý logout, xóa cookie, HTTPS, proxy, session fixation và triển khai nhiều instance.

## 2. HTTP gửi/nhận cookie ra sao?

Ví dụ một server trả hai cookie trong cùng một response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=<opaque-id>; Path=/; HttpOnly; SameSite=Lax
Set-Cookie: ui_theme=dark; Path=/demo; Max-Age=604800; SameSite=Lax
Content-Type: text/plain

OK
~~~

Đây là **mẫu minh họa**, không phải ID thật hoặc cam kết về thứ tự thuộc tính. **Mỗi cookie phải được phát bằng một header Set-Cookie riêng**; không nối các Set-Cookie thành một header phân tách bằng dấu phẩy.

Sau đó, khi trình duyệt yêu cầu một URL có path phù hợp và cookie chưa hết hạn, request có thể chứa:

~~~http
GET /demo/session/status HTTP/1.1
Host: example.test
Cookie: JSESSIONID=<opaque-id>; ui_theme=dark
~~~

Những điều cần đọc chính xác:

- **Set-Cookie** là header response từ server về browser. **Cookie** là header request browser gửi lên server. Request Cookie **chỉ gửi tên–giá trị**, không lặp lại các thuộc tính HttpOnly/Secure/Path/Max-Age.
- **JSESSIONID** và **ui_theme** có thể đồng thời được gửi trong một request, nhưng mỗi giá trị có mục đích khác nhau.
- Browser không biết **JSESSIONID** tương ứng account nào hoặc **ui_theme** có được kiểm tra hợp lệ hay không. Các ý nghĩa đó thuộc server/application.
- Browser dùng các thuộc tính cookie và chính sách bảo mật của chính nó để quyết định lưu/gửi; client HTTP ngoài browser có thể tự đặt header **Cookie** bất kỳ. **Không tin giá trị cookie chỉ vì nó đến qua header.**
- Nếu request đến **/public** thay vì **/demo**, cookie có **Path=/demo** không nên được browser gửi theo quy tắc path matching. Cookie **Path=/** có phạm vi rộng hơn.

Tương tự, JavaScript được phép tạo cookie của ứng dụng bằng **document.cookie** nếu cookie không bị hạn chế; nhưng một cookie từ JavaScript không biến thành session được Servlet container quản lý nếu server không cấu hình cơ chế đó. Vì vậy phân loại theo **vai trò**, không chỉ theo "ai gọi Set-Cookie".

## 3. Cookie phiên do Servlet container quản lý

### 3.1. HttpSession nằm ở đâu?

Khi Spring MVC controller thực hiện:

~~~java
HttpSession session = request.getSession(true);
session.setAttribute("displayName", "learner");
~~~

**HttpSession** chứa các attribute logic của phiên, được quản lý phía server (mặc định thường nằm trong bộ nhớ của Servlet container khi không có session store ngoài). Browser không được nhận đối tượng Java hoặc toàn bộ attribute. Browser thường nhận một **ID opaque**:

~~~text
Browser                        Spring Boot Servlet container
   | POST /demo/session/start            |
   |------------------------------------>|
   |                          tạo HttpSession S123
   |                          session["displayName"] = "learner"
   |<-- Set-Cookie: JSESSIONID=<id> ------|
   |                                     |
   | GET /demo/session/status            |
   | Cookie: JSESSIONID=<id>             |
   |------------------------------------>|
   |                    lookup ID -> HttpSession S123
   |                    đọc attribute displayName
   |<-- active:learner -------------------|
~~~

Chuỗi **S123**, **<id>** chỉ minh họa. ID thật do cơ chế session tạo, cần khó đoán. **Không đưa user ID, mật khẩu hoặc quyền truy cập vào chuỗi JSESSIONID một cách thủ công.**

### 3.2. Ai tạo và quản lý cookie đó?

Trong ứng dụng Spring Boot MVC với embedded Tomcat mặc định, khi có **HttpSession** mới cần được theo dõi bằng cookie, Servlet container phát cookie phiên (thông thường tên **JSESSIONID**). Ứng dụng chỉ nên thao tác với **HttpSession API**, thay vì tự gọi **response.addCookie(new Cookie("JSESSIONID", ...))** để giả lập session.

Những API quan trọng:

- **request.getSession()** hoặc **request.getSession(true)**: lấy session hiện có hoặc tạo session mới nếu chưa có.
- **request.getSession(false)**: chỉ lấy session hiện có, trả **null** khi không có; hữu ích khi kiểm tra mà không vô tình tạo session.
- **session.setAttribute("key", value)** / **getAttribute(...)**: lưu/truy xuất dữ liệu phiên ở server.
- **session.invalidate()**: vô hiệu hóa session phía server.
- **request.changeSessionId()**: thay session ID của session hiện có; thường áp dụng sau khi nâng mức xác thực để phòng **session fixation** (Spring Security có cơ chế bảo vệ riêng khi được cấu hình).
- **session.setMaxInactiveInterval(seconds)**: thay idle timeout riêng cho session; không đồng nghĩa với cookie Max-Age.

Cần đọc đúng chữ **"thường"**: cookie tên **JSESSIONID** là thông lệ của Servlet container, nhưng có thể đổi tên hoặc dùng **Spring Session** với cơ chế lưu/resolve session khác (ví dụ cookie mặc định **SESSION** khi Spring Session dùng cookie resolver tương ứng). Không hardcode giả thiết tên cookie khi cấu hình dự án thay đổi.

### 3.3. Cookie JSESSIONID không mang dữ liệu đăng nhập

Giả sử **session.setAttribute("cart", someCart)**. Browser vẫn chỉ mang ID. Cart ở server, hoặc trong session store được cấu hình. Nếu người khác chiếm được ID còn hiệu lực, họ **có thể chiếm phiên** dù không nhìn thấy cart trong cookie. Vì vậy session ID phải được bảo vệ như một credential.

Một số cookie tự thiết kế khác có thể chứa **token đã ký/JWT** hoặc thông tin mã hóa, nghĩa là server xác minh dữ liệu chứa trong cookie thay vì lookup HttpSession. **Đó là một mô hình khác**, có quy tắc expiry, revocation, rotation, CSRF và quản lý khóa riêng; không tự coi bất kỳ chuỗi cookie nào là token xác thực an toàn.

## 4. Cookie do ứng dụng chủ động tạo

Ví dụ người dùng chọn chủ đề tối:

~~~http
Set-Cookie: ui_theme=dark; Path=/demo; Max-Age=604800; SameSite=Lax
~~~

Ứng dụng đặt tên **ui_theme**, giới hạn chỉ nhận **dark/light**, chọn thời gian lưu 7 ngày và đọc cookie trong controller. Không có HttpSession nào buộc phải được tạo chỉ để ghi cookie này.

Một số mục đích phù hợp:

| Cookie tùy chỉnh | Nội dung dự kiến | Có cần tra cứu HttpSession? | Lưu ý |
| --- | --- | --- | --- |
| **ui_theme=dark** | Tùy chọn giao diện ít nhạy cảm | Không | Có thể đọc bằng JS nếu không gắn HttpOnly; validate allowlist. |
| **locale=vi** | Ngôn ngữ người dùng muốn dùng | Không | Client sửa được; chỉ coi là gợi ý giao diện. |
| **consent=accepted** | Một trạng thái tùy chọn | Không nhất thiết | Nếu là bằng chứng pháp lý/kiểm toán, cần ghi nhận phía server theo yêu cầu nghiệp vụ. |
| **cart_ref=<id>** | Khóa tham chiếu giỏ hàng | Có thể tra cứu database/service riêng | Không mặc nhiên xem ID là quyền truy cập. |
| **refresh_token=<opaque-token>** | Credential dài hạn | Không nhất thiết là HttpSession | Cần bảo vệ nghiêm ngặt, rotation/revocation, HTTPS, HttpOnly và phòng CSRF. |

**Phát cookie bằng application không đồng nghĩa lưu dữ liệu ở server.** Giá trị có thể nằm hoàn toàn trong browser, làm khóa tra cứu server-side khác hoặc chứa token đã ký/mã hóa. Thiết kế phải xác định rõ trust boundary.

**Không đưa thông tin bí mật, quyền hạn, mật khẩu, dữ liệu riêng tư dạng rõ hoặc object Java serialize vào cookie**. Client có thể xem/chỉnh payload (trừ các rào cản hỗ trợ hạn chế script) và có thể giả lập header bằng công cụ HTTP. Chữ ký bảo đảm tính toàn vẹn khi triển khai đúng, nhưng **không tự che giấu nội dung**; mã hóa mới nhằm bảo mật nội dung, và cả hai vẫn cần quản lý khóa/vòng đời.

## 5. Bảng so sánh trực tiếp

| Tiêu chí | Session cookie do container/framework quản lý | Cookie tùy chỉnh do ứng dụng tạo |
| --- | --- | --- |
| Ví dụ tên | **JSESSIONID**, đôi khi **SESSION** hoặc tên được cấu hình | **ui_theme**, **locale**, **auth_token**... |
| Ai quyết định giá trị? | Cơ chế session tạo ID opaque | Application quyết định chuỗi/ID/token |
| Ý nghĩa | Gắn request vào **session server-side** | Tùy nghiệp vụ: preference, tracking, token, tham chiếu... |
| Dữ liệu chính nằm ở đâu? | **HttpSession**/session store ở server; cookie chỉ chứa ID | Có thể chính trong cookie hoặc một kho server khác |
| Cách tạo | **getSession(true)** hoặc framework cần phiên; container/session resolver phát cookie | **HttpServletResponse.addCookie** hoặc **ResponseCookie** + Set-Cookie |
| Cách đọc | **getSession(false)** và session attributes | **@CookieValue**, **request.getCookies()**, hoặc Cookie header |
| Cách xóa | **invalidate()** phía server; xóa browser cookie là bước riêng khi cần | Gửi lại Set-Cookie cùng name/scope với **Max-Age=0**, và xóa state server nếu có |
| Thời hạn | **Session idle timeout** riêng và **cookie expiry** riêng | Do app đặt Max-Age/Expires, thêm TTL server nếu cần |
| Bảo mật | ID là bí mật; cần Secure/HttpOnly/SameSite/TLS, session fixation/CSRF protection | Phụ thuộc giá trị; token cần mức bảo vệ tương đương credential |
| Đổi sang cluster | Cần session store chung hoặc cơ chế phù hợp | Phụ thuộc nơi app lưu/kiểm tra state |
| Được browser gửi tự động? | Có, khi cookie match các quy tắc | Cũng có, khi cookie match các quy tắc |

**Không đánh đồng "session cookie" về thời hạn với "cookie dành cho HttpSession".** Một custom cookie **không có Expires/Max-Age** là browser-session cookie về thời hạn, dù không liên quan HttpSession. Ngược lại, cookie dùng để định danh HttpSession **có thể được cấu hình Max-Age lâu hơn một phiên browser**; server-side session vẫn có thể hết hạn trước.

## 6. Những thuộc tính cookie cần kiểm soát

| Thuộc tính | Cách hoạt động | Dùng như thế nào |
| --- | --- | --- |
| **Name=Value** | Định danh và giá trị cookie được lưu/gửi. | Dùng tên riêng, tránh đè tên cookie session; chỉ ghi dữ liệu nhỏ, đã validate. |
| **Path** | Giới hạn đường dẫn request mà browser gửi cookie theo rule path matching. | **/** cho cookie cần trên toàn app, **/demo** cho demo; Path không phải hàng rào bảo mật dữ liệu. |
| **Domain** | Nếu có: có thể cho cookie đi tới domain chỉ định và subdomain hợp lệ. | Mặc định bỏ Domain để được **host-only cookie**, tránh chia sẻ ngoài ý muốn. |
| **Secure** | Chỉ gửi trên kết nối HTTPS theo quy tắc browser (localhost có ngoại lệ cục bộ). | **true** cho cookie nhạy cảm ở production HTTPS. Không thay thế cấu hình TLS. |
| **HttpOnly** | Ngăn JavaScript thông thường đọc cookie qua **document.cookie**. | **true** cho session ID/token không cần JavaScript; không ngăn JS gửi request kèm cookie. |
| **SameSite=Strict** | Chỉ gửi theo bối cảnh same-site nghiêm ngặt. | Bảo vệ mạnh nhưng có thể ảnh hưởng một số luồng điều hướng/xác thực. |
| **SameSite=Lax** | Hạn chế nhiều tình huống cross-site; vẫn cho một số điều hướng top-level an toàn. | Lựa chọn thường phù hợp với nhiều ứng dụng truyền thống, không thay thế CSRF token. |
| **SameSite=None** | Cho phép cross-site theo chính sách của browser. | Browser yêu cầu **Secure**; vẫn chịu chính sách chặn third-party cookies. |
| **Max-Age** | Tuổi thọ tương đối theo giây; **0** yêu cầu hết hạn ngay. | Thường dùng cho cookie lưu tùy chọn; cần phân biệt với session idle timeout. |
| **Expires** | Thời điểm hết hạn tuyệt đối. | Có thể dùng thay Max-Age; khi cả hai có mặt, Max-Age có ưu tiên. |

### Host-only, Domain và Path

Nếu server ở **app.example.test** gửi:

~~~http
Set-Cookie: ui_theme=dark; Path=/demo; SameSite=Lax
~~~

Không có **Domain**, cookie thuộc host **app.example.test**, không tự được gửi tới **api.example.test**. Cookie chỉ đi theo những request path match **/demo**, chẳng hạn **/demo/theme**, không phải **/health**.

Nếu khai báo **Domain=example.test**, các subdomain phù hợp có thể cùng nhận cookie; điều này mở rộng phạm vi và rủi ro cookie injection/session fixation giữa subdomain. Domain chỉ được đặt thành domain hiện tại hoặc parent domain hợp lệ, không tùy ý sang tên miền của người khác.

**Path không phải cơ chế phân quyền.** Nhiều ứng dụng trên cùng origin có thể tác động tới dữ liệu trình duyệt theo các khả năng của mình; luôn bảo vệ API bằng xác thực/phân quyền phía server.

### Cookie prefix

Browser hỗ trợ prefix có thể từ chối cookie dùng sai ràng buộc:

- **__Secure-**: yêu cầu Secure và secure origin.
- **__Host-**: yêu cầu Secure, **Path=/** và **không có Domain**, giúp thu hẹp phạm vi về host phát hành.

Ví dụ **__Host-session** hoặc **__Host-auth** có thể giúp giảm nguy cơ cấu hình sai khi hệ thống dùng HTTPS; nhưng bạn phải đặt đúng tất cả thuộc tính. Prefix **không thay thế** việc xác thực token hoặc session ở server.

### HttpOnly, Secure, SameSite không thay thế nhau

- **HttpOnly** giảm khả năng script lấy cookie, nhưng **XSS vẫn có thể gửi request theo quyền người dùng**. Phải sửa XSS và duy trì kiểm soát ủy quyền.
- **Secure** giảm rủi ro cookie đi trên HTTP; vẫn phải dùng **HTTPS/TLS** thực sự ở đường client tới điểm kết thúc TLS và kiểm tra proxy.
- **SameSite** là một lớp hỗ trợ chống **CSRF**, không thay thế CSRF token/Origin validation cho những hành động state-changing có yêu cầu bảo vệ.
- **CORS** kiểm soát quyền truy cập response cross-origin, không phải cơ chế ngăn browser gửi mọi cookie. Với fetch cross-origin phải xét **credentials**, CORS allow-credentials, SameSite và chính sách browser đồng thời.

## 7. Demo chạy được: Spring Boot 3.x, Java 17+, Servlet MVC

### 7.1. Điều kiện và dependency

Sử dụng project Spring Boot 3.x chạy Java 17+ có Gradle wrapper, plugin Spring Boot và Maven Central đã cấu hình. Thêm **spring-boot-starter-web**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Demo sử dụng REST controller trên embedded Tomcat mặc định; **không thêm spring-boot-starter-security** trong demo này để các lệnh curl thử không cần thực hiện đăng nhập/CSRF. Khi có Spring Security trên hệ thống thật, bạn phải cấu hình authentication, authorization và CSRF phù hợp với API.

### 7.2. application.properties: chỉ chỉnh cookie phiên

Tạo **src/main/resources/application.properties**:

~~~properties
server.port=8080

# State HttpSession het han sau 20 phut khong hoat dong
server.servlet.session.timeout=20m

# Cau hinh cookie dinh danh HttpSession (Servlet stack)
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.path=/
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax

# Trong production HTTPS, bat them:
# server.servlet.session.cookie.secure=true

# Khong dat max-age: browser-session cookie theo mac dinh cookie
# server.servlet.session.cookie.max-age=7d
~~~

Các thuộc tính **server.servlet.session.cookie.*** quản lý cookie phiên do môi trường Servlet/session framework phát. Chúng **không tự áp dụng cho mọi cookie** mà controller tự thêm. Spring Boot 3.3 còn hỗ trợ **server.servlet.session.cookie.domain** và **max-age** khi có nhu cầu tương ứng.

Ví dụ dùng **HTTP localhost** để kiểm thử thuận tiện. Trên production, sử dụng HTTPS và đặt **Secure=true** cho session cookie. Đừng copy một cấu hình Secure=false hoặc bỏ hẳn TLS vào môi trường thật. Nếu TLS được terminate ở reverse proxy, cần xác minh đúng effective scheme/forwarded headers từ proxy đáng tin trước khi phụ thuộc thuộc tính request để chọn Secure.

**server.servlet.session.timeout** là timeout **idle của state phía server**. **server.servlet.session.cookie.max-age** là tuổi thọ của cookie **trong browser**. Hai giá trị độc lập: browser có thể tiếp tục gửi ID hết hiệu lực sau khi server đã xóa session, và cookie có thể hết hạn trong khi state server vẫn chưa timeout.

### 7.3. Java: một session cookie tự sinh và một custom cookie

Tạo file **src/main/java/com/example/cookielab/CookieLabApplication.java**:

~~~java
package com.example.cookielab;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import java.time.Duration;
import java.util.Set;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CookieLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CookieLabApplication.class, args);
    }
}

@RestController
class CookieLabController {
    private static final Set<String> THEMES = Set.of("dark", "light");

    @PostMapping("/demo/session/start")
    public String startSession(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute("label", "learner");
        return "session-started";
    }

    @GetMapping("/demo/session/status")
    public String sessionStatus(HttpServletRequest request) {
        // Khong tao session moi khi chi muon kiem tra.
        HttpSession session = request.getSession(false);
        if (session == null) {
            return "no-active-session";
        }
        return "active:" + session.getAttribute("label");
    }

    @PostMapping("/demo/session/end")
    public String endSession(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return "session-invalidated";
    }

    @PostMapping("/demo/theme/{theme}")
    public ResponseEntity<String> setTheme(
            @PathVariable("theme") String theme,
            HttpServletResponse response
    ) {
        if (!THEMES.contains(theme)) {
            return ResponseEntity.badRequest().body("invalid-theme");
        }

        ResponseCookie preference = ResponseCookie.from("ui_theme", theme)
                .path("/demo")
                .httpOnly(false) // Chi la tuy chon UI, khong phai credential.
                .secure(false)   // Chi de thu tren HTTP localhost.
                .sameSite("Lax")
                .maxAge(Duration.ofDays(7))
                .build();

        // addHeader de khong ghi de Set-Cookie khac trong response.
        response.addHeader(HttpHeaders.SET_COOKIE, preference.toString());
        return ResponseEntity.ok("theme-saved");
    }

    @GetMapping("/demo/theme")
    public String readTheme(
            @CookieValue(name = "ui_theme", required = false) String theme
    ) {
        // Cookie do client gui len: validate lai du da do app phat.
        return theme != null && THEMES.contains(theme) ? theme : "default";
    }

    @PostMapping("/demo/theme/delete")
    public String deleteTheme(HttpServletResponse response) {
        ResponseCookie expired = ResponseCookie.from("ui_theme", "")
                .path("/demo")
                .httpOnly(false)
                .secure(false) // Giong scope demo khi phat cookie.
                .sameSite("Lax")
                .maxAge(Duration.ZERO)
                .build();

        response.addHeader(HttpHeaders.SET_COOKIE, expired.toString());
        return "theme-deleted";
    }
}
~~~

**Độ đúng của ví dụ:**

- File có **một public class CookieLabApplication** cùng tên; **CookieLabController** package-private trong cùng package, được Spring component scan.
- **startSession** gọi **getSession(true)** rồi lưu attribute. **Không có dòng nào tự sinh JSESSIONID bằng ResponseCookie**; việc này do cơ chế session Servlet thực hiện.
- **sessionStatus** dùng **getSession(false)** để xem session mà không tạo mới; nếu người dùng chưa có phiên hợp lệ, trả **no-active-session**.
- **endSession** vô hiệu hóa **HttpSession**. Nó không xóa **ui_theme**; custom preference có vòng đời riêng.
- **setTheme** chỉ chấp nhận **dark/light**, dùng **ResponseCookie** để thiết lập **SameSite=Lax**, **Path=/demo**, **Max-Age 7 ngày**, và **HttpOnly=false** vì đây là tùy chọn UI không nhạy cảm có thể cần client đọc. Với token/credential, không dùng mẫu này mà phải thiết kế bảo vệ riêng.
- **secure(false)** được viết rõ chỉ để thử trên **http://localhost**. Trên production HTTPS, chuyển thành **secure(true)** và đặt session cookie Secure ở cấu hình server.
- **response.addHeader(Set-Cookie, ...)** cho phép nhiều Set-Cookie header cùng tồn tại khi cần. Tránh **setHeader** để không vô tình ghi đè một cookie khác đã được framework phát trong cùng response.
- **readTheme** không tin cookie nhận vào: người dùng có thể sửa giá trị, vì vậy hàm kiểm tra allowlist trước khi sử dụng.
- **deleteTheme** phát cookie với **cùng name và Path** cùng domain scope, **Max-Age=0**. Nếu cookie ban đầu có **Domain**, cần gửi lệnh xóa cùng Domain tương ứng; nếu đổi path/domain, bạn có thể tạo thêm một cookie khác thay vì xóa bản cũ.

**Cơ chế ứng dụng tự tạo khác:** có thể dùng **jakarta.servlet.http.Cookie** và **HttpServletResponse.addCookie(...)**; khi muốn khai báo SameSite rõ ràng, **ResponseCookie** của Spring là một lựa chọn thuận tiện. Không cần tự thêm chuỗi Set-Cookie bằng nối text không kiểm soát.

### 7.4. Chạy ứng dụng

Từ project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell/cmd có thể dùng **gradlew.bat bootRun**. Giữ server chạy và mở terminal khác để thử lệnh curl.

### 7.5. Thử bằng cookie jar: nhìn hai vòng đời độc lập

Bắt đầu bằng một file cookie jar mới, ví dụ **cookies.txt** (không dùng lại cookie jar của một lần test cũ).

**A. Tạo session ở server:**

~~~bash
curl -si -c cookies.txt -X POST \
  http://localhost:8080/demo/session/start
~~~

Body response:

~~~text
session-started
~~~

Header response thường chứa một **Set-Cookie: JSESSIONID=<ID>** kèm các thuộc tính phiên theo cấu hình. ID thay đổi và không thể đoán trước; đường dẫn/cách sắp xếp thuộc tính có thể khác tùy container. **-c cookies.txt** ghi cookie jar trên đĩa của curl.

**B. Gửi lại JSESSIONID để đọc state server:**

~~~bash
curl -si -b cookies.txt \
  http://localhost:8080/demo/session/status
~~~

Body response kỳ vọng:

~~~text
active:learner
~~~

**-b cookies.txt** gửi các cookie phù hợp từ jar. Điều này chứng minh ID cho phép tìm lại HttpSession, không chứng minh label nằm bên trong cookie.

**C. Tạo cookie tùy chỉnh nhưng giữ cookie phiên:**

~~~bash
curl -si -b cookies.txt -c cookies.txt -X POST \
  http://localhost:8080/demo/theme/dark
~~~

Body:

~~~text
theme-saved
~~~

Header **Set-Cookie** có thể nhìn thấy:

~~~http
Set-Cookie: ui_theme=dark; Path=/demo; Max-Age=604800; SameSite=Lax
~~~

Dòng này minh họa các attribute chính; framework có thể sinh thêm **Expires** và thay đổi thứ tự. **-b** đọc jar hiện có, **-c** cập nhật jar sau response.

**D. Đọc custom cookie:**

~~~bash
curl -si -b cookies.txt http://localhost:8080/demo/theme
~~~

Body kỳ vọng:

~~~text
dark
~~~

**E. Invalidate HttpSession nhưng không động tới preference:**

~~~bash
curl -si -b cookies.txt -X POST \
  http://localhost:8080/demo/session/end

curl -si -b cookies.txt \
  http://localhost:8080/demo/session/status

curl -si -b cookies.txt \
  http://localhost:8080/demo/theme
~~~

Ba body phản hồi theo thứ tự:

~~~text
session-invalidated
no-active-session
dark
~~~

**Chú ý:** sau invalidate, browser/curl **có thể vẫn giữ JSESSIONID trong jar**. ID đó không còn trỏ tới state hợp lệ. Không nên tuyên bố invalidate() tự bảo đảm browser đã xóa cookie; cần kiểm chứng nếu yêu cầu logout phải xóa mọi dấu vết phía client.

**F. Xóa cookie tùy chỉnh:**

~~~bash
curl -si -b cookies.txt -c cookies.txt -X POST \
  http://localhost:8080/demo/theme/delete

curl -si -b cookies.txt \
  http://localhost:8080/demo/theme
~~~

Body sau khi xóa:

~~~text
default
~~~

Header của lệnh xóa có **Max-Age=0** với name/path tương ứng. Cookie này độc lập với session: xóa **ui_theme** không yêu cầu hủy HttpSession.

**G. Gửi cookie giả để thấy server không tin dữ liệu client:**

~~~bash
curl -si -H "Cookie: ui_theme=superadmin" \
  http://localhost:8080/demo/theme
~~~

Body kỳ vọng:

~~~text
default
~~~

Nếu tùy chỉnh UI không được validate như demo, giá trị ngoài allowlist có thể gây lỗi hoặc mở đường cho nhánh xử lý sai. Với thông tin phân quyền, chỉ kiểm tra allowlist vẫn chưa đủ; quyết định quyền phải dựa trên cơ chế authentication/authorization hợp lệ ở server.

## 8. Vòng đời: idle timeout khác cookie expiry

Giả sử server có:

~~~properties
server.servlet.session.timeout=20m
~~~

và custom cookie:

~~~http
Set-Cookie: ui_theme=dark; Max-Age=604800; Path=/demo
~~~

Nếu người dùng không gửi request trong 30 phút:

- **HttpSession** có thể đã timeout do server-side idle interval 20 phút, nên một JSESSIONID được gửi lại không còn dẫn tới session cũ.
- **ui_theme** vẫn có thể còn trong browser vì nó có Max-Age 7 ngày, và browser vẫn gửi trong phạm vi Path/Domain phù hợp.
- Nếu bạn đặt **server.servlet.session.cookie.max-age=7d**, điều đó chỉ kéo dài **tuổi thọ cookie chứa ID**; không tự kéo dài session state hoặc giữ user đăng nhập 7 ngày.
- Ngược lại, tăng **server.servlet.session.timeout** không buộc browser lưu cookie phiên sau khi browser thực sự bỏ cookie đó. Một số browser có session restore nên cookie không Max-Age đôi khi tồn tại qua lần đóng/mở; không dùng chuyện đóng browser làm biện pháp logout bảo mật duy nhất.

**Logout đúng** trong hệ thống xác thực có thể gồm invalidate server-side session, xóa authentication context, thu hồi token server-side nếu có, thiết lập cookie hết hạn đúng scope và dọn các state client được phép. Nếu hệ thống dùng Spring Security, ưu tiên cơ chế logout/session management của Spring Security và cấu hình cookie tương thích, tránh tự chắp vá một endpoint logout giả.

## 9. Ai điều khiển cookie trong Spring Boot và Spring Security?

### 9.1. Servlet container và Spring Boot

Khi chỉ dùng Servlet MVC và HttpSession, container thực hiện **session tracking**. Spring Boot cung cấp các thuộc tính:

~~~properties
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
server.servlet.session.timeout=20m
~~~

Đây là ví dụ **cấu hình production có HTTPS**, không dùng nguyên xi cho bài thử HTTP localhost. Nếu muốn dùng đường dẫn app tùy chỉnh, domain hoặc thời hạn cookie, xem **server.servlet.session.cookie.path**, **domain**, **max-age** theo tài liệu của phiên bản Boot và kiểm tra behavior từ container thực.

**Spring Boot 3.3** cũng hỗ trợ cấu hình SameSite của session cookie qua **server.servlet.session.cookie.same-site** trên các embedded Servlet server được hỗ trợ. Với cookie khác do application thêm vào HttpServletResponse, dùng **ResponseCookie** hoặc **CookieSameSiteSupplier** theo tài liệu tương ứng, thay vì cho rằng một cờ session SameSite sẽ tự áp vào mọi cookie.

### 9.2. Spring Session

Khi dùng **Spring Session** với Redis/JDBC hay một SessionRepository khác, **HttpSession API** có thể vẫn dùng như cũ nhưng dữ liệu session được lưu trong store dùng chung thay vì chỉ ở memory của một Tomcat instance. Cookie resolver của Spring Session có thể phát cookie với tên/cách quản lý khác (thường **SESSION** trong cấu hình mặc định của một số setup). Vì thế **không hardcode "mọi session luôn là JSESSIONID"** khi môi trường tích hợp thay đổi.

Session store nhiều instance giúp request được phục vụ ở các replica khác nhau, nhưng vẫn phải bảo vệ cookie ID, cấu hình TTL, phiên bản serialization, secret, retention và chính sách logout. Cookie chỉ mang ID không giải quyết tự động mọi vấn đề HA hoặc consistency.

### 9.3. Spring Security

Spring Security có thể dùng HttpSession để giữ **SecurityContext** của người dùng trên Servlet stack, đồng thời áp dụng các chiến lược bảo vệ session fixation, CSRF và logout. Nhưng **SecurityContext không phải chính bản thân JSESSIONID**. Browser vẫn gửi ID; server dùng ID để tìm session và thông tin xác thực khi thích hợp.

Một hệ thống stateless có thể dùng Bearer token hoặc signed token trong cookie mà không cần HttpSession, nhưng điều đó không tự an toàn hơn. Cookie chứa authentication token vẫn có nguy cơ CSRF vì browser tự gửi; cần bảo vệ phù hợp, quản lý expiry, revocation và chống replay. **HttpOnly** bảo vệ việc đọc qua script, không ngăn mọi request do script thực hiện.

## 10. HTTPS, reverse proxy, SameSite và cross-site request

Trong production:

~~~text
Browser -- HTTPS --> CDN / Ingress / Reverse proxy
                                 |
                                 +--> HTTP hoặc HTTPS --> Spring Boot
~~~

Cookie **Secure** phải phù hợp với đường **browser đến endpoint public**, không đơn giản với việc Spring Boot thấy kết nối nội bộ HTTP hay HTTPS. Nếu tính thuộc tính Secure bằng **request.isSecure()**, cần xác minh forwarding scheme từ một proxy đáng tin, cấu hình forward headers đúng và không tin header X-Forwarded-* từ client tùy ý. Cách dễ kiểm soát cho session cookie production khi luôn có HTTPS là **server.servlet.session.cookie.secure=true**.

Một số lỗi dễ thấy:

- Web app chạy sau reverse proxy HTTPS nhưng response Set-Cookie lại thiếu Secure hoặc cấu hình SameSite=None mà không có Secure; browser có thể từ chối cookie.
- Backend cookie có **Domain=internal.local** trong khi browser gọi **app.example.com**; browser không gửi được cookie theo host public.
- App nằm dưới **/portal** nhưng cookie Path hoặc reverse proxy path rewriting không khớp với URL browser đang truy cập.
- Frontend ở origin khác gọi API bằng fetch mà quên **credentials** hoặc server CORS không cho credentials; response chứa Set-Cookie nhưng browser không lưu/gửi như mong đợi.
- Browser chặn third-party cookie hoặc giới hạn cross-site tracking dù ứng dụng đặt **SameSite=None; Secure**. Không giả định thuộc tính này vượt mọi chính sách của user agent.

**SameSite không đồng nghĩa SameOrigin.** Hai origin khác nhau có thể là same-site trong một số trường hợp; ngược lại khác scheme có thể được tính cross-site theo quy tắc hiện đại. Khi thiết kế SSO/iframe/redirect, phải kiểm tra site boundary, method điều hướng, chính sách cookie browser và quy trình authentication thật.

## 11. Những lỗi thiết kế và cách nhận ra

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Controller gọi getSession(false) luôn null | Chưa tạo session, browser không gửi cookie, sai Domain/Path/Secure/SameSite, session đã timeout. | Quan sát Set-Cookie, Cookie header, server-side session lookup và cookie jar. |
| Mỗi request lại có JSESSIONID mới | Session không được giữ ở client, domain/path/proxy không khớp hoặc session store không nhất quán. | Kiểm tra cookie acceptance, HTTPS, các instance, sticky routing/session store. |
| Dùng cookie ui_theme nhưng login mất sau restart | ui_theme không phải authentication session; HttpSession có thể mất khi server restart. | Xác định state nằm ở đâu, cấu hình session store nếu cần. |
| Logout rồi browser vẫn gửi JSESSIONID | invalidate() là thao tác server-side, browser chưa chắc tự xóa cookie. | Kiểm chứng session đã vô hiệu, xóa đúng cookie scope nếu yêu cầu, dùng logout chuẩn. |
| Xóa ui_theme rồi vẫn có | Xóa sai Path/Domain hoặc tồn tại nhiều cookie cùng tên khác scope. | Quan sát storage tab và Set-Cookie; gửi Max-Age=0 với scope phù hợp. |
| JavaScript không đọc được JSESSIONID | HttpOnly đang hoạt động. | Đây là hành vi bảo vệ mong muốn, không tắt HttpOnly cho session ID. |
| API cross-site không lưu cookie | Thiếu credentials, CORS, SameSite=None;Secure hoặc browser policy. | Kiểm browser network, cookie blocked reason, CORS/SameSite. |
| Session hết hạn trước browser cookie | Idle timeout server ngắn hơn cookie Max-Age. | Phân biệt TTL server/session với expiry của cookie. |
| Một server login được, server khác không | Session state chỉ ở memory một node. | Session store chung hoặc topology/affinity phù hợp, quan sát TTL. |
| Cookie chứa role=ADMIN bị sửa bằng curl | App tin dữ liệu do client kiểm soát. | Không dùng cookie plaintext làm nguồn quyết định phân quyền. |
| Set-Cookie tùy chỉnh làm mất session cookie | Response dùng setHeader ghi đè header trước đó. | Dùng addHeader cho nhiều Set-Cookie, kiểm response thật. |
| XSS lấy được token trong custom cookie | HttpOnly bị tắt hoặc token nằm trong nơi JS đọc được. | Token nhạy cảm dùng HttpOnly/Secure/TLS, chống XSS và CSRF. |

## 12. Thực hành test và quan sát chính xác

Các kiểm thử có giá trị nên có cả ở mức controller và HTTP thật:

1. **Chưa có cookie:** gọi **GET /demo/session/status** ở client mới → **no-active-session** và không chủ động tạo session chỉ vì kiểm tra.
2. **Tạo session:** **POST /demo/session/start** → **Set-Cookie JSESSIONID** (với Servlet container/session tracking qua cookie); gửi lại ID → **active:learner**.
3. **Custom cookie:** **POST /demo/theme/dark** → **Set-Cookie ui_theme**, kiểm **Path, Max-Age, SameSite**; gọi GET theme → **dark**.
4. **Vòng đời độc lập:** invalidate session, kiểm status không active nhưng theme vẫn **dark**; sau đó xóa theme và kiểm **default**.
5. **Cookie giả:** gửi **ui_theme=superadmin** và kiểm code vẫn chọn **default**; không bao giờ dùng cookie role=ADMIN làm quyền thật.
6. **Cookie hết hạn:** kiểm **Max-Age=0** thực sự khiến browser xóa đúng cookie theo name/domain/path. Trường hợp có hai cookie cùng tên ở hai Path khác nhau cần xử lý riêng.
7. **TLS/proxy:** trên public HTTPS xác nhận session cookie có **Secure/HttpOnly/SameSite**; thử trong DevTools Network/Application, không chỉ đọc property file.
8. **Multi-replica:** xác minh HttpSession/sessions hoạt động khi request đi qua node khác; cần session store chung nếu topology đòi hỏi.
9. **Bảo mật:** kiểm POST state-changing có cơ chế CSRF phù hợp khi dùng cookie auth, session ID được rotate khi nâng mức xác thực và được invalidate khi logout.

**MockMvc** có thể test controller, việc gọi HttpSession và response cookie header, nhưng **không đại diện đầy đủ browser cookie jar, TLS termination, cookie blocking policy hay proxy**. Muốn kiểm Secure/SameSite/Domain/Path thật, dùng browser và HTTP client qua đúng endpoint triển khai.

**Đừng in nguyên giá trị session ID hoặc token vào log, screenshot hay tài liệu công khai.** Nếu log cần phục vụ debug, chỉ ghi thông tin request/correlation ID không phải credential và tuân thủ chính sách bảo mật của hệ thống.

## 13. Câu hỏi tình huống

**Tình huống A.** Một controller đặt **session.setAttribute("userId", 42)** rồi server gửi **JSESSIONID=abc...**. Browser có thể lấy userId=42 trực tiếp từ nội dung JSESSIONID không? **Không.** Cookie chỉ là ID của session; state ở server/session store. Không có phép ánh xạ trực tiếp từ chuỗi opaque sang userId nếu không lookup server.

**Tình huống B.** Người dùng đóng tab rồi mở lại trang vẫn thấy **ui_theme=dark**, nhưng phải đăng nhập lại. Có mâu thuẫn không? **Không.** Custom cookie còn hạn 7 ngày; HttpSession có thể hết hạn/hủy hoặc browser không còn session cookie.

**Tình huống C.** Lập trình viên thấy **SameSite=Lax** rồi bỏ CSRF protection cho mọi POST. Có an toàn tuyệt đối không? **Không.** SameSite là defense in depth, không thay mọi kiểm tra CSRF, origin, authorization và chính sách hành động state-changing.

**Tình huống D.** Một service đặt **server.servlet.session.cookie.max-age=7d** nhưng timeout server vẫn 20 phút. Sau 2 giờ idle, browser gửi ID cũ thì có còn login không? **Thông thường không**, session server đã hết hạn; có thể được tạo session mới nếu handler chủ động tạo. Cookie dài hạn không làm state sống lại.

**Tình huống E.** App gọi **response.addHeader("Set-Cookie", "ui_theme=dark; ...")** cùng response container phát JSESSIONID. Browser lưu được cả hai không? **Có thể**, nếu cả hai Set-Cookie hợp lệ và phù hợp chính sách browser. Dùng **addHeader** giữ các header riêng; dùng **setHeader** dễ ghi đè nếu không chủ động quản lý.

**Tình huống F.** Cookie **ui_theme=dark; Path=/demo** không đến endpoint **/health**. Có phải server đã xóa cookie? **Không**, có thể do scope Path không match. Kiểm browser storage và request path.

**Tình huống G.** Server có **JSESSIONID** nhưng app dùng Spring Session Redis, có thể khẳng định state nằm ở RAM Tomcat không? **Không**, HttpSession API có thể được backed bởi SessionRepository bên ngoài; kiểm cấu hình thực tế.

## 14. Tự kiểm tra kiến thức

1. **JSESSIONID chứa điều gì?** — Thông thường là opaque session identifier, không phải toàn bộ session attributes.
2. **Gọi getSession(false) có tạo session không?** — Không.
3. **Tắt HttpOnly có giúp server quản lý session tốt hơn không?** — Không; chỉ làm cookie dễ bị JS đọc hơn.
4. **Custom cookie luôn persistent?** — Không; không có Max-Age/Expires thì là browser-session cookie.
5. **Cookie quản lý session luôn tên JSESSIONID?** — Không; tên có thể đổi hoặc dùng Spring Session.
6. **Invalidate HttpSession có tự xóa mọi custom cookie không?** — Không; vòng đời custom cookie độc lập.
7. **Path=/demo là phân quyền?** — Không; đó chỉ là phạm vi browser gửi cookie.
8. **Secure có thay thế HTTPS không?** — Không; cần TLS thực tế và cấu hình proxy đúng.
9. **Max-Age 7d có thay server session timeout 20m không?** — Không; hai khái niệm độc lập.
10. **Có thể tin role=admin từ Cookie header không?** — Không; client có thể giả mạo hoặc sửa giá trị.
11. **Xóa cookie cần match những yếu tố gì?** — Name, Path và Domain scope tương ứng, cộng chính sách browser phù hợp.
12. **SameSite=None có cần Secure?** — Có, theo cơ chế trình duyệt hiện đại.
13. **Vì sao một HTTP response cần nhiều Set-Cookie header?** — Mỗi cookie được đặt riêng; gộp bằng dấu phẩy làm sai cú pháp và có thể phá parser.
14. **Khi nào cân nhắc Spring Session?** — Khi yêu cầu quản lý state session qua nhiều instance/nguồn lưu, có chính sách TTL và HA tương ứng.

## 15. Nguồn tham khảo

- **Spring Boot 3.3 – Common Application Properties:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/ (server.servlet.session.cookie.*, timeout, tracking).
- **Spring Boot 3.3 – Servlet Web Applications / SameSite Cookies:** https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html (cấu hình SameSite cho session cookie và cookie khác).
- **Spring Framework 6.1 – ResponseCookie API:** https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/http/ResponseCookie.html (builder, httpOnly, secure, sameSite, path, maxAge).
- **Jakarta Servlet – HttpSession API:** https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpsession (session attributes, timeout, invalidate).
- **Spring Session Reference:** https://docs.spring.io/spring-session/reference/ (session repository và cookie session tracking).
- **Spring Security – Session Management:** https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html (session fixation, logout và cấu hình phiên).
- **MDN – Set-Cookie:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie (HTTP cookie attributes, browser rules).
- **MDN – Secure cookie configuration:** https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies (Secure, HttpOnly, SameSite và prefix).
