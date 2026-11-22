# Cookie và cấu hình thời hạn, Secure, HttpOnly, SameSite trong Spring MVC

## 1. Mục tiêu và bối cảnh

HTTP về cơ bản là giao thức **stateless**: server không tự ghi nhớ người dùng giữa hai request chỉ nhờ HTTP. **Cookie** là một cơ chế để server hướng dẫn trình duyệt lưu một cặp tên–giá trị kèm các thuộc tính, rồi trình duyệt tự quyết định khi nào gửi cặp đó trong request tiếp theo. Ứng dụng Spring MVC có thể dùng cookie cho session identifier, tùy chọn giao diện, locale, ghi nhận sự đồng ý của người dùng hoặc những thông tin trạng thái khác.

Bài này tập trung vào **vòng đời và phạm vi cookie**, đặc biệt là `Max-Age`/`Expires`, `Secure`, `HttpOnly`, `SameSite`, và cách cấu hình, đọc, xóa trong **Spring MVC Servlet stack**.

Học xong, bạn có thể:

1. Phân biệt header **`Set-Cookie` của response** và **`Cookie` của request**, cookie session và cookie có thời hạn.
2. Giải thích `Max-Age`, `Expires`, `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite=Strict/Lax/None` và giới hạn của từng cơ chế.
3. Dùng `ResponseCookie`, `ResponseEntity`, `@CookieValue` để đặt, đọc và xóa cookie trong controller Spring MVC.
4. Cấu hình các thuộc tính của **session cookie** do Servlet container / Spring Boot quản lý mà không nhầm với cookie tùy chỉnh.
5. Hiểu quan hệ giữa cookie, HTTPS, CSRF, XSS, CORS, third-party cookie policy, session timeout, và kiểm thử bằng `MockMvc`.
6. Nhận diện các cấu hình không an toàn: `SameSite=None` thiếu `Secure`, bỏ `HttpOnly` cho session ID, `Domain` quá rộng hoặc giữ cookie nhạy cảm quá lâu.

Ví dụ ứng dụng chạy theo **Java 17+, Spring Framework 6.x, Spring Boot 3.x**. Trình duyệt có thể áp dụng chính sách cookie khác nhau theo phiên bản, thiết lập quyền riêng tư và ngữ cảnh first-party/third-party; server gửi `Set-Cookie` **không có nghĩa** trình duyệt chắc chắn lưu hoặc gửi lại cookie đó.

## 2. Cookie di chuyển qua HTTP như thế nào?

Một response hướng dẫn client tạo cookie:

~~~http
HTTP/1.1 204 No Content
Set-Cookie: view_pref=compact; Path=/api/prefs; Max-Age=604800; Secure; HttpOnly; SameSite=Lax
~~~

Ở các request sau, nếu điều kiện trình duyệt thỏa mãn, client gửi:

~~~http
GET /api/prefs/current HTTP/1.1
Host: example.com
Cookie: view_pref=compact
~~~

Những điều quan trọng:

- `Set-Cookie` là **response header** để tạo, thay đổi hoặc hết hạn cookie. Để gửi nhiều cookie, server thường dùng **nhiều header `Set-Cookie` riêng**, không gộp tùy tiện thành một header cách nhau bằng dấu phẩy.
- `Cookie` là **request header**, chỉ mang các cặp tên–giá trị, ví dụ `Cookie: theme=dark; lang=vi`. Nó **không gửi lại** `Max-Age`, `Secure`, `HttpOnly`, `Path` hoặc `SameSite`.
- Cookie không nằm trong JSON body. Một endpoint có thể gửi body JSON và `Set-Cookie` cùng lúc; cũng có thể trả HTTP 204 không có body mà vẫn đặt cookie qua header.
- `@CookieValue` đọc cookie từ request **hiện tại**, không đọc `Set-Cookie` đang được tạo cho response. Để đọc cookie vừa đặt, cần request tiếp theo của client, hoặc truyền giá trị theo luồng nghiệp vụ ngay tại server.
- Cookie được quản lý bởi client theo các ràng buộc scope, thời hạn, chính sách browser và người dùng. Header `Set-Cookie` xuất hiện trong `curl -i` chỉ chứng minh server đã gửi nó; **chưa chứng minh browser đã chấp nhận**.

### Phân biệt cookie với server-side session

Cookie `JSESSIONID` thường chứa một **định danh session**, còn dữ liệu session chính được lưu ở phía server (memory, Redis hoặc một session repository). Cookie `JSESSIONID` không tự chứa toàn bộ object `HttpSession`. Một session ID có thể hết hiệu lực ở server ngay cả khi trình duyệt còn cookie; ngược lại cookie session có thể biến mất khi browser kết thúc trong khi server chưa hết session timeout.

Không đặt password, dữ liệu bí mật dạng plaintext hoặc toàn bộ object người dùng vào cookie chỉ vì cookie nằm trong trình duyệt. Người dùng và môi trường client có nhiều cách quan sát/sửa cookie; một cookie có `HttpOnly` không phải kho dữ liệu bí mật ở phía server.

## 3. Các thuộc tính trong `Set-Cookie`

| Thuộc tính | Tác dụng | Lưu ý |
| --- | --- | --- |
| `name=value` | Định danh và giá trị cookie | Không tin là dữ liệu server chưa bị sửa; kiểm tra khi nhận |
| `Max-Age=604800` | Thời hạn theo **giây** tính từ lúc nhận; 604800 = 7 ngày | `Max-Age=0` làm cookie hết hạn ngay |
| `Expires=...` | Thời điểm hết hạn theo ngày GMT | Nếu có cả `Max-Age`, client hiện đại ưu tiên `Max-Age` |
| `Path=/api` | Giới hạn request path mà browser gửi cookie | Không phải ranh giới bảo mật cô lập các path |
| `Domain=example.com` | Cho phép cookie áp dụng cho domain và subdomain phù hợp | Bỏ `Domain` thường an toàn hơn: cookie host-only |
| `Secure` | Chỉ gửi qua kết nối bảo mật HTTPS (ngoại lệ localhost tùy browser) | Không tự mã hóa cookie đang lưu trên thiết bị |
| `HttpOnly` | Ngăn JavaScript `document.cookie` đọc/chỉnh cookie | Không chặn browser gửi cookie trong `fetch` hoặc form request |
| `SameSite=Strict` | Hạn chế cookie về các request cùng site | Mạnh hơn nhưng có thể ảnh hưởng luồng mở link từ site khác |
| `SameSite=Lax` | Cho phép cùng site và một số điều hướng top-level cross-site an toàn | Không thay thế CSRF token |
| `SameSite=None` | Cho phép cookie trong ngữ cảnh cross-site đủ điều kiện | **Cần `Secure`**; browser vẫn có thể chặn third-party cookie |
| `Partitioned` | Tùy chọn cookie có storage phân vùng trong browser hỗ trợ | Cần `Secure`; chính sách browser khác nhau |

Không phải trình duyệt nào cũng giữ cookie trong thời gian cam kết nếu người dùng xóa cookie, trình duyệt giới hạn dung lượng/số lượng, private mode kết thúc, hoặc chính sách tracking protection can thiệp. Thời hạn **không phải lời hứa lưu trữ tuyệt đối**.

### Một cookie không có `Domain` là gì?

Ví dụ server `api.example.com` gửi:

~~~http
Set-Cookie: pref=vi; Path=/; Secure; SameSite=Lax
~~~

Vì **không có `Domain`**, đây thường là **host-only cookie**: chỉ host `api.example.com` nhận cookie, không tự mở rộng tới `www.example.com`.

Nếu thêm `Domain=example.com`, cookie có thể được gửi cả tới `example.com` và các subdomain phù hợp. Domain quá rộng có thể làm tăng rủi ro một subdomain bị chiếm quyền hoặc không đáng tin cậy thao túng cookie. Không thể đặt `Domain` tùy ý thành domain khác không liên quan hoặc public suffix như `com`.

`Path` điều khiển việc trình duyệt gửi cookie theo đường dẫn, nhưng **không cô lập quyền đọc dữ liệu giữa các ứng dụng cùng origin** như một biện pháp bảo mật độc lập. Cần quản lý origin, domain, quyền ứng dụng và trust boundary hợp lý.

## 4. Cấu hình thời hạn: session cookie, `Max-Age` và `Expires`

### 4.1. Session cookie

Khi không có `Expires` và `Max-Age`, cookie thường được xem là **session cookie**, theo vòng đời browser session. Không giả định nó chắc chắn biến mất ngay khi đóng một tab: một số browser có chế độ restore session và phục hồi các session cookie. “Session cookie” cũng khác với “server-side session timeout”.

### 4.2. Persistent cookie

~~~http
Set-Cookie: theme=dark; Path=/; Max-Age=2592000; Secure; SameSite=Lax
~~~

`2592000` giây tương ứng 30 ngày (30 × 24 × 60 × 60). `Max-Age` là số giây tương đối, không phải millisecond. Nếu server ghi `Max-Age=30` để biểu diễn 30 ngày, cookie chỉ tồn tại khoảng 30 giây.

Với `Expires`, server chỉ định ngày giờ hết hạn; có thể xuất hiện sai lệch đồng hồ client/server. Nếu có cả hai, `Max-Age` có độ ưu tiên theo semantics cookie phổ biến. Spring `ResponseCookie` cung cấp `maxAge(Duration.ofDays(...))` để tránh nhầm đơn vị.

### 4.3. Xóa cookie

~~~http
Set-Cookie: theme=; Path=/; Max-Age=0; Secure; SameSite=Lax
~~~

`Max-Age=0` yêu cầu cookie hết hạn ngay. **Tên, `Path` và `Domain` scope phải tương thích với cookie cũ**. Nếu cookie cũ tạo `Path=/api/prefs` mà xóa bằng `Path=/`, browser có thể vẫn giữ cookie cũ vì đó là một identity khác.

Để thay/loại bỏ cookie một cách nhất quán, duy trì cùng cấu hình scope giữa lúc tạo và xóa. Cookie xóa không cần giữ nguyên value cũ, nhưng các thuộc tính liên quan bảo mật/scope nên nhất quán cho tính dễ hiểu. Nếu có nhiều cookie trùng tên ở các path hoặc domain khác nhau, cần xem xét từng cookie cụ thể.

### 4.4. Hết hạn cookie không đồng nghĩa logout bảo mật

Xóa cookie giúp browser không gửi session ID nữa, nhưng **logout đáng tin còn phải vô hiệu session/token phía server** khi hệ thống dùng session. Đối với session ID do Spring Security quản lý, nên sử dụng logout/session-management của Spring Security, không chỉ tự gửi `Set-Cookie: JSESSIONID=; Max-Age=0` và tưởng đã thu hồi quyền.

Một opaque session identifier tồn tại tại server có thể bị sử dụng lại nếu đã rò rỉ và chưa bị thu hồi, dù user xóa cookie từ một browser.

## 5. `Secure`: bảo vệ khi truyền cookie

`Secure` hướng dẫn browser chỉ gửi cookie qua `https:` (ngoại lệ thường gặp là `localhost` trong môi trường phát triển). Đây là thuộc tính cần thiết cho session/authentication cookie khi triển khai HTTPS.

~~~http
Set-Cookie: session_ref=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nó giúp tránh browser gửi cookie nhạy cảm qua HTTP thường, nhưng **không**:
- Bảo vệ hoàn toàn trước XSS nếu ứng dụng vẫn có script injection.
- Mã hóa giá trị cookie khi lưu trên ổ đĩa client.
- Xác thực quyền truy cập hoặc ngăn replay của token bị lộ.
- Tự chuyển HTTP site thành HTTPS, hay tự sửa cấu hình reverse proxy.

Dùng HTTPS trên toàn ứng dụng, ưu tiên HSTS ở production khi thích hợp, bảo vệ traffic giữa reverse proxy/backend theo kiến trúc. Nếu app đứng sau load balancer TLS termination, cấu hình proxy và trusted forwarding đúng để framework biết request gốc là HTTPS; không tin header `X-Forwarded-Proto` từ client không đáng tin.

Nếu đang dùng `Secure=true` tại `http://localhost:8080`, kết quả browser có thể phụ thuộc chính sách localhost và browser. Ví dụ thực hành bên dưới kiểm tra **server gửi thuộc tính đúng** qua `curl -i`/MockMvc; để kiểm tra browser gửi cookie tự động, dùng HTTPS trong môi trường phù hợp.

## 6. `HttpOnly`: hạn chế JavaScript chạm cookie

Cookie có `HttpOnly` thường không xuất hiện trong `document.cookie` và không được sửa bằng JavaScript thường trong trang:

~~~http
Set-Cookie: session_ref=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cơ chế này giảm một số rủi ro **đọc/đánh cắp session cookie qua XSS**, nhưng không loại bỏ XSS. Script độc hại chạy trong origin có thể:
- Gửi request `fetch` tới backend mà trình duyệt đính cookie HttpOnly đủ điều kiện.
- Đọc những thông tin mà UI/API cho phép script truy cập.
- Thực hiện thao tác bất hợp pháp trong phiên người dùng nếu server thiếu kiểm soát quyền/CSRF.

Với **session ID**, `HttpOnly=true` thường là lựa chọn mặc định mong muốn. Với **tùy chọn giao diện** mà client JavaScript thật sự phải đọc bằng `document.cookie`, có thể cân nhắc cookie không HttpOnly (vì không chứa bí mật) hoặc truyền giá trị qua HTML/API được phép, sau đó lưu ở cơ chế phù hợp. Không vô hiệu hóa HttpOnly trên authentication cookie chỉ để frontend “lấy token cho tiện”.

`HttpOnly` khác với CORS: CORS quy định JavaScript trang web khác có thể đọc response hay không, nhưng không phải cơ chế tổng quát chặn browser gửi cookie. Cookie và credential policy của browser cần được kiểm tra riêng.

## 7. `SameSite`: Strict, Lax, None

`SameSite` giới hạn khi browser gắn cookie vào request theo **site** của request so với site gây ra request. “Site” thường là **scheme + registrable domain** (schemeful same-site), không đồng nghĩa với **origin** (scheme + host + port). Ví dụ `https://app.example.com` và `https://api.example.com` có thể khác origin nhưng vẫn same-site; `http://example.com` và `https://example.com` có thể khác site theo schemeful rule.

| Giá trị | Request same-site | Điều hướng top-level cross-site GET | Cross-site fetch/form POST thông thường |
| --- | --- | --- | --- |
| `Strict` | Có, nếu scope/other rules khớp | Thường không gửi | Không gửi |
| `Lax` | Có | Thường gửi với safe top-level navigation | Thường không gửi |
| `None` | Cho phép theo scope | Có thể gửi | Có thể gửi nếu `Secure` và các chính sách browser cho phép |

Giải thích:

- **`Strict`**: phù hợp thao tác nhạy cảm khi UX chấp nhận việc cookie không đính vào request điều hướng từ website khác. Ví dụ người dùng mở link được gửi từ site khác có thể phải thực hiện một bước cùng site tiếp theo để phiên được dùng.
- **`Lax`**: cân bằng UX và một phần phòng chống CSRF; cho phép một số top-level navigation an toàn như GET. Không cho phép giả định mọi request GET đều vô hại: API phải bảo đảm **GET không tạo thay đổi trạng thái nguy hiểm**.
- **`None`**: không chặn theo SameSite, dùng cho trường hợp cần cookie trong một số ngữ cảnh cross-site (chẳng hạn embedded widget). Browser hiện đại **yêu cầu `Secure`** đi kèm; third-party cookie blocking/partitioning và privacy settings vẫn có thể ngăn cookie.
- **Bỏ thuộc tính**: nhiều browser áp dụng mặc định kiểu Lax, nhưng có khác biệt/ngoại lệ như grace period cho cookie mới tạo và thay đổi chính sách qua thời gian. Nếu ứng dụng có yêu cầu bảo mật rõ ràng, hãy **đặt SameSite tường minh**.

**Quan trọng:** `SameSite=Lax` không thay thế **CSRF protection**. Server cần CSRF token hoặc biện pháp kiểm soát request giả mạo phù hợp với authentication mechanism; Spring Security cung cấp CSRF protection khi được cấu hình. Cross-site top-level GET vẫn có thể mang cookie Lax, nên GET/HEAD phải được thiết kế theo safe semantics.

### Cross-origin `fetch` không hoàn toàn đồng nghĩa cross-site

Một frontend ở `https://app.example.com` gọi `https://api.example.com` là **cross-origin**, vì host khác. Nhưng trong nhiều cấu hình, hai origin này vẫn **same-site**. Khi browser xử lý cookie:
- `SameSite` liên quan **site**.
- `Domain`, `Path`, `Secure`, expiry liên quan scope cookie.
- `fetch` dùng `credentials` và CORS liên quan cách request gửi credentials và JavaScript được đọc response.
- Chính sách chặn cookie bên thứ ba còn phụ thuộc browser.

Vì vậy không nên đổi cookie sang `SameSite=None` chỉ vì thấy thông báo “CORS error”. Trước tiên cần xác định hai site có thật sự cross-site không và điểm chặn là credentials/CORS/cookie scope hay CSRF.

## 8. API Spring MVC tạo cookie: `ResponseCookie` và `ResponseEntity`

Trong **Spring Framework 6.x**, class `org.springframework.http.ResponseCookie` có builder để khai báo:
- `path(String)`, `domain(String)` khi thực sự cần.
- `maxAge(Duration)` hoặc `maxAge(long seconds)`.
- `secure(boolean)`, `httpOnly(boolean)`, `sameSite(String)`.

Ví dụ khai báo:

~~~java
ResponseCookie cookie = ResponseCookie.from("view_pref", "compact")
        .path("/api/prefs")
        .maxAge(Duration.ofDays(7))
        .secure(true)
        .httpOnly(true)
        .sameSite("Lax")
        .build();

String headerValue = cookie.toString();
~~~

Đây là **đoạn minh họa bên trong method**: cần import `ResponseCookie` và `Duration`. `toString()` tạo **giá trị** thích hợp cho header `Set-Cookie`, không phải một URL hay JSON body.

Để gửi header, dùng:

~~~java
return ResponseEntity.noContent()
        .header(HttpHeaders.SET_COOKIE, cookie.toString())
        .build();
~~~

Với method có kiểu trả về `ResponseEntity<Void>`, kết quả là **HTTP 204 No Content** kèm `Set-Cookie` và **không có body**. `ResponseEntity` là lựa chọn tiện lợi khi cần điều khiển status và headers cùng lúc.

Nếu gửi nhiều cookie, dùng **hai giá trị header** `Set-Cookie`, ví dụ:

~~~java
return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, first.toString())
        .header(HttpHeaders.SET_COOKIE, second.toString())
        .body("ok");
~~~

Đây là đoạn minh họa, cần có hai `ResponseCookie` là `first` và `second`; API `header` bổ sung các giá trị header. Không tự nối `first + "," + second` thành một chuỗi vì cú pháp `Set-Cookie` có các đặc điểm riêng, nhất là khi có `Expires`.

### Đọc cookie trong controller bằng `@CookieValue`

~~~java
@GetMapping("/current")
public String current(
        @CookieValue(name = "view_pref", required = false) String pref) {
    return pref == null ? "missing" : pref;
}
~~~

Đây là handler minh họa trong `@RestController`, cần import. `@CookieValue` tìm cookie theo tên trên **request**:
- Mặc định `required=true`; cookie bắt buộc thiếu có thể dẫn tới lỗi HTTP 400.
- `required=false` cho phép thiếu cookie và tham số `String` nhận `null`.
- `defaultValue="..." ` có thể dùng để đặt fallback, đồng thời ngụ ý không yêu cầu bắt buộc.
- Có thể lấy `jakarta.servlet.http.Cookie` khi cần object Cookie của Servlet, nhưng **request Cookie không cho bạn biết chắc chắn** thuộc tính `SameSite`/`HttpOnly` đã được browser lưu, vì browser không gửi những thuộc tính đó trong `Cookie` request header.

Dữ liệu cookie do client kiểm soát. Nếu cookie chứa lựa chọn chỉ nhận `compact` hoặc `comfortable`, hãy **validate allowlist** ở server; không tin cookie để xác định role, user ID hoặc quyền truy cập.

## 9. Ví dụ hoàn chỉnh Java 17+ / Spring Boot 3.x

Tạo project bằng Spring Initializr: Java 17+, Spring Boot 3.x, Maven, **Spring Web** và **Spring Boot Starter Test**. Package của project là `com.example.demo`. Bài chỉ sử dụng cookie tùy chọn giao diện, **không tạo authentication/session system**.

Cấu trúc:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/PreferenceCookieController.java
src/test/java/com/example/demo/PreferenceCookieControllerTest.java
~~~

### 9.1. Lớp khởi động

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.2. Controller tạo, đọc, xóa cookie

**`src/main/java/com/example/demo/PreferenceCookieController.java`**

~~~java
package com.example.demo;

import java.time.Duration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/prefs")
public class PreferenceCookieController {

    private static final String COOKIE_NAME = "view_pref";
    private static final String COOKIE_PATH = "/api/prefs";

    @PostMapping("/compact")
    public ResponseEntity<Void> chooseCompact() {
        ResponseCookie cookie = ResponseCookie.from(COOKIE_NAME, "compact")
                .path(COOKIE_PATH)
                .maxAge(Duration.ofDays(7))
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax")
                .build();

        return ResponseEntity.noContent()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .build();
    }

    @GetMapping(value = "/current",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String current(
            @CookieValue(name = COOKIE_NAME, required = false)
            String value) {

        if (value == null) {
            return "view_pref=missing";
        }

        // Cookie do client điều khiển: không tin giá trị tùy ý.
        if (!value.equals("compact") && !value.equals("comfortable")) {
            return "view_pref=invalid";
        }

        return "view_pref=" + value;
    }

    @DeleteMapping
    public ResponseEntity<Void> clear() {
        ResponseCookie expired = ResponseCookie.from(COOKIE_NAME, "")
                .path(COOKIE_PATH)
                .maxAge(Duration.ZERO)
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax")
                .build();

        return ResponseEntity.noContent()
                .header(HttpHeaders.SET_COOKIE, expired.toString())
                .build();
    }
}
~~~

**Cách hoạt động:**

1. `POST /api/prefs/compact` gửi HTTP 204 và `Set-Cookie: view_pref=compact; ... Max-Age=604800; Secure; HttpOnly; SameSite=Lax`. Đây là cookie tồn tại tối đa khoảng 7 ngày theo hướng dẫn `Max-Age`.
2. `Path=/api/prefs` có nghĩa browser gửi cookie cho request hợp lệ thuộc đường dẫn này; nó không tự gửi cho mọi endpoint của website.
3. `Secure(true)` giữ semantics an toàn đối với production HTTPS. Với demo chạy `http://localhost:8080`, browser cụ thể có thể áp dụng exception localhost; test trực tiếp header không phụ thuộc việc browser quyết định lưu.
4. `HttpOnly(true)` cho thấy thuộc tính bảo vệ cookie khỏi các API truy cập cookie bằng JavaScript. Đây là **ví dụ cấu hình**; nếu UI JavaScript thực sự cần đọc một preference cookie không bí mật, thiết kế có thể dùng một cơ chế khác hoặc cân nhắc `HttpOnly=false` **chỉ cho cookie không chứa credential**.
5. `SameSite("Lax")` đặt chính sách gửi cookie tường minh. Nó không khiến cross-site request trở nên an toàn một cách tuyệt đối.
6. `GET /api/prefs/current` đọc `@CookieValue` và validate giá trị. Thiếu cookie trả text `view_pref=missing`; cookie hợp lệ trả `view_pref=compact` hoặc `view_pref=comfortable`.
7. `DELETE /api/prefs` gửi `Max-Age=0` với **cùng tên và Path** để yêu cầu xóa cookie. Xóa phía browser không có nghĩa vô hiệu hóa session server, nhưng ví dụ này chỉ là cookie preference, không dùng session.
8. Cả POST và DELETE dùng 204 không body; header `Set-Cookie` vẫn hợp lệ. Status không nhất thiết phải là 200 để browser xử lý cookie.

Trong hệ thống thực, nếu endpoint thay đổi state và authentication dùng cookie, cần có cơ chế phòng CSRF thích hợp. Ví dụ không thêm Spring Security để tập trung vào cookie mechanics.

### 9.3. Gọi bằng curl

Chạy:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows: `mvnw.cmd spring-boot:run`. Nếu không có Maven Wrapper, dùng `mvn spring-boot:run` sau khi cài Maven.

Gửi lệnh tạo cookie và quan sát header:

~~~bash
curl -i -X POST "http://localhost:8080/api/prefs/compact"
~~~

Bạn sẽ thấy status **204 No Content**, và một `Set-Cookie` tương đương:

~~~http
Set-Cookie: view_pref=compact; Path=/api/prefs; Max-Age=604800; Expires=...; Secure; HttpOnly; SameSite=Lax
~~~

`Expires` nếu được Spring tự bổ sung sẽ phụ thuộc thời điểm thực thi; dấu `...` ở đây chỉ là **minh họa**, không phải một giá trị date hợp lệ để copy vào response. Thứ tự attribute không phải API contract chính; kiểm tra những thuộc tính cần thiết.

`curl` trong ví dụ không tự bảo đảm cookie Secure được gửi trên HTTP ở các lệnh sau. Để **minh họa chính xác cách controller đọc `Cookie` request**, chủ động gửi header giả lập:

~~~bash
curl -i "http://localhost:8080/api/prefs/current"   -H "Cookie: view_pref=compact"
~~~

Response body kỳ vọng:

~~~text
view_pref=compact
~~~

Không gửi cookie:

~~~bash
curl -i "http://localhost:8080/api/prefs/current"
~~~

Body:

~~~text
view_pref=missing
~~~

Gửi một giá trị ngoài allowlist:

~~~bash
curl -i "http://localhost:8080/api/prefs/current"   -H "Cookie: view_pref=admin"
~~~

Body:

~~~text
view_pref=invalid
~~~

Yêu cầu xóa:

~~~bash
curl -i -X DELETE "http://localhost:8080/api/prefs"
~~~

Status kỳ vọng **204**, header `Set-Cookie` chứa `view_pref=; Path=/api/prefs; Max-Age=0` cùng các flag `Secure`, `HttpOnly`, `SameSite=Lax`. Trên trình duyệt, kiểm tra bằng DevTools **Application/Storage → Cookies** và **Network → Response Headers / Request Cookies**. Với `HttpOnly`, không đợi `document.cookie` đọc được cookie.

Các lệnh multiline dùng dấu `\` của Linux/macOS/Git Bash. Trên Windows PowerShell, dùng `curl.exe` với cú pháp quote/nối dòng đúng; một dòng thường ít gặp lỗi hơn.

## 10. Kiểm thử `Set-Cookie` và `@CookieValue` với MockMvc

Thêm dependency `spring-boot-starter-test` và tệp **`src/test/java/com/example/demo/PreferenceCookieControllerTest.java`**:

~~~java
package com.example.demo;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PreferenceCookieController.class)
class PreferenceCookieControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createCookieWithSevenDayExpiryAndSecurityFlags()
            throws Exception {

        MvcResult result = mockMvc.perform(
                        post("/api/prefs/compact"))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""))
                .andReturn();

        String header = result.getResponse()
                .getHeader(HttpHeaders.SET_COOKIE);

        assertNotNull(header);
        assertTrue(header.contains("view_pref=compact"));
        assertTrue(header.contains("Path=/api/prefs"));
        assertTrue(header.contains("Max-Age=604800"));
        assertTrue(header.contains("Secure"));
        assertTrue(header.contains("HttpOnly"));
        assertTrue(header.contains("SameSite=Lax"));
    }

    @Test
    void readCookieIfPresentAndHandleMissingCookie()
            throws Exception {

        mockMvc.perform(get("/api/prefs/current")
                        .cookie(new Cookie("view_pref", "compact")))
                .andExpect(status().isOk())
                .andExpect(content().string("view_pref=compact"));

        mockMvc.perform(get("/api/prefs/current"))
                .andExpect(status().isOk())
                .andExpect(content().string("view_pref=missing"));
    }

    @Test
    void refuseUnknownCookieValue() throws Exception {
        mockMvc.perform(get("/api/prefs/current")
                        .cookie(new Cookie("view_pref", "admin")))
                .andExpect(status().isOk())
                .andExpect(content().string("view_pref=invalid"));
    }

    @Test
    void clearCookieUsesMatchingPathAndZeroAge()
            throws Exception {

        MvcResult result = mockMvc.perform(delete("/api/prefs"))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""))
                .andReturn();

        String header = result.getResponse()
                .getHeader(HttpHeaders.SET_COOKIE);

        assertNotNull(header);
        assertTrue(header.contains("view_pref="));
        assertTrue(header.contains("Path=/api/prefs"));
        assertTrue(header.contains("Max-Age=0"));
        assertTrue(header.contains("Secure"));
        assertTrue(header.contains("HttpOnly"));
        assertTrue(header.contains("SameSite=Lax"));
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Các test khẳng định **server phát header đúng** và `@CookieValue` bind giá trị request đúng. `MockMvc` **không mô phỏng toàn bộ trình duyệt**: nó không tự enforce cookie `Secure` trên HTTP, không thử third-party cookie blocking, không đánh giá CSRF policy của browser, cũng không bảo đảm `SameSite` đã được một browser cụ thể chấp nhận. Những đặc tính đó cần browser/integration tests trên HTTPS và ngữ cảnh cross-site thực sự.

Nếu ứng dụng sản phẩm có Spring Security, test POST/DELETE có thể yêu cầu CSRF token và authentication. Bổ sung `spring-security-test` rồi dùng `with(csrf())` theo chính sách của project, không tắt CSRF để qua test.

## 11. Session cookie do Spring Boot quản lý: cấu hình khác cookie tự tạo

Ứng dụng dùng Servlet session hoặc Spring Security có thể thấy cookie `JSESSIONID`. **Đừng thay đổi `JSESSIONID` thủ công trong controller như cách tạo `view_pref`** nếu cookie đó thuộc container/session management của framework.

Với **Spring Boot 3.x**, có thể cấu hình session cookie trong `src/main/resources/application.properties`:

~~~properties
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
server.servlet.session.timeout=30m
~~~

Ý nghĩa:
- `http-only=true`, `secure=true`, `same-site=lax` điều khiển những thuộc tính mà container dùng để tạo session cookie.
- `path=/` mở rộng cookie cho các route trong host, phù hợp khi session được dùng toàn ứng dụng; có thể thu hẹp theo cấu trúc app.
- `server.servlet.session.timeout=30m` là **thời gian timeout session phía server**, không phải thời gian cookie tồn tại phía browser.
- Nếu muốn cookie tồn tại theo `Max-Age` xác định, Boot còn có `server.servlet.session.cookie.max-age` và các thuộc tính tương ứng. Cần xét với chính sách timeout/invalidation để tránh hiểu sai rằng cookie còn tức session còn.
- Khi chạy HTTPS thật, `Secure=true` là thiết lập phù hợp. Ở local HTTP, cookie `Secure` có thể gây khó kiểm thử tùy browser; dùng profile phát triển được kiểm soát nếu cần, không đưa cấu hình kém an toàn vào production.

Nếu ứng dụng không thực sự tạo session, nó không nhất thiết phát `JSESSIONID`. Việc đặt property **không tự tạo một session**.

### Cookie ngoài session: `CookieSameSiteSupplier` của Spring Boot

Spring Boot 3.x hỗ trợ `CookieSameSiteSupplier` đối với một số cookie thêm qua `HttpServletResponse` của servlet stack. Ví dụ minh họa:

~~~java
import org.springframework.boot.web.servlet.server.CookieSameSiteSupplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CookiePolicyConfig {

    @Bean
    public CookieSameSiteSupplier demoCookies() {
        return CookieSameSiteSupplier.ofLax()
                .whenHasNameMatching("myapp.*");
    }
}
~~~

Class trên là **ví dụ cấu hình bổ sung**, không cần thêm vào project controller ở phần 9. Nó có thể dùng để đặt SameSite cho các cookie tên khớp khi đi qua cơ chế `response.addCookie(...)` được Boot hỗ trợ. Đừng giả định supplier luôn viết lại các giá trị `Set-Cookie` đã được tự tạo trực tiếp bằng `ResponseEntity.header` hoặc mọi response từ proxy; kiểm tra đường xuất cookie cụ thể của hệ thống.

### `jakarta.servlet.http.Cookie` và `HttpServletResponse.addCookie`

Cách Servlet truyền thống:

~~~java
Cookie cookie = new Cookie("view_pref", "compact");
cookie.setPath("/api/prefs");
cookie.setMaxAge(604800);
cookie.setSecure(true);
cookie.setHttpOnly(true);
response.addCookie(cookie);
~~~

Đây là đoạn minh họa trong method có `HttpServletResponse response`, với import `jakarta.servlet.http.Cookie`. Trong Servlet API phù hợp, một số implementation còn hỗ trợ `setAttribute("SameSite", "Lax")`; khả năng serialize `SameSite` phụ thuộc Servlet version/container/Boot policy. Khi cần điều khiển rõ `SameSite` một cách portable trong Spring MVC 6.x, `ResponseCookie` và `Set-Cookie` header thường dễ đọc và dễ test hơn.

**Đừng dùng `javax.servlet.http.Cookie` trong Spring Boot 3.x**, vì nhánh này dựa trên **Jakarta Servlet** (`jakarta.servlet.*`).

## 12. Session và bảo mật: CSRF, XSS, session fixation

### CSRF với cookie authentication

Nếu website dùng session cookie để xác thực, browser sẽ tự gửi cookie ở những request thỏa điều kiện scope và chính sách cookie. Attacker có thể tìm cách khiến browser của nạn nhân gửi một request làm thay đổi dữ liệu. **SameSite=Lax/Strict giảm một số đường tấn công CSRF nhưng không thay thế CSRF protection**.

Các nguyên tắc:
1. HTTP GET/HEAD không nên thực hiện thay đổi trạng thái nguy hiểm.
2. Đối với state-changing POST/PUT/PATCH/DELETE gắn với cookie authentication, dùng CSRF token/kiểm soát phù hợp Spring Security và threat model.
3. Kiểm tra Origin/Referer và Content-Type khi thích hợp là biện pháp bổ sung, không thay token khi ứng dụng thực sự cần.
4. Không coi CORS là “tường chống CSRF”: một request có thể được gửi mà không cần JavaScript đọc response, nhất là qua HTML form/cơ chế điều hướng.

### XSS và `HttpOnly`

`HttpOnly` ngăn script đọc session cookie qua `document.cookie`, nhưng script bị injection vẫn có thể tương tác với website trong quyền của user. Cần encode output, tránh unsafe DOM sinks, có CSP phù hợp và giảm phạm vi cookie.

### Session fixation và rotation

Sau khi người dùng đăng nhập, cần áp dụng cơ chế **session fixation protection** như thay đổi session ID; Spring Security có session management tương ứng. Không tạo session ID dự đoán được hoặc giữ lại một ID do attacker kiểm soát. Khi logout, hủy session/token phía server và xóa cookie liên quan theo cơ chế framework.

### Prefix `__Secure-` và `__Host-`

Một số browser có quy tắc kiểm tra theo tên cookie:

~~~http
Set-Cookie: __Secure-session=abc; Secure; HttpOnly; Path=/; SameSite=Lax
Set-Cookie: __Host-session=abc; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

- `__Secure-`: yêu cầu `Secure` và nguồn thiết lập HTTPS trong browser hỗ trợ.
- `__Host-`: ngoài `Secure`, yêu cầu `Path=/` và **không có `Domain`**, giúp giới hạn cookie ở host.
- Prefix là lớp phòng vệ bổ sung, **không thay authorization/session invalidation**.
- Tên và cookie value ở trên là placeholder mô tả header, không phải session identifier nên dùng thật.

## 13. Cross-origin frontend, CORS và third-party cookie

Ví dụ một ứng dụng frontend tại `https://app.example.com` gọi API `https://api.example.com`:

~~~javascript
const response = await fetch("https://api.example.com/api/prefs/current", {
  method: "GET",
  credentials: "include"
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}

console.log(await response.text());
~~~

`credentials: "include"` cho phép trình duyệt gửi credentials với cross-origin request theo điều kiện; **không ép** gửi cookie bị `SameSite`, `Secure`, `Domain`, `Path` hoặc browser privacy policy chặn. Để JavaScript đọc response cross-origin, backend cần CORS thích hợp, ví dụ `Access-Control-Allow-Origin` đúng origin cụ thể và `Access-Control-Allow-Credentials: true` khi cho phép credentials. Không dùng `Access-Control-Allow-Origin: *` kết hợp với credentialed requests.

Nếu frontend và API thuộc **hai site khác nhau**, có thể cần `SameSite=None; Secure` cho cookie cross-site, nhưng **nhiều browser chặn third-party cookies** hoặc yêu cầu phương án khác. Không đổi sang `None` một cách máy móc: xác định trước liệu hai origin có cùng registrable domain/scheme (same-site) hay không, và có thể thiết kế lại luồng với same-site backend hoặc token-based API khi thích hợp.

Một response `Set-Cookie` có thể hiện trong Network panel nhưng bị browser đánh dấu “blocked” do chính sách `SameSite`, `Secure`, domain, browser privacy, prefix, cookie size hoặc CORS/credentials. Hãy đọc lý do block trong DevTools, đừng chỉ kiểm tra status 200.

JavaScript frontend **không đọc trực tiếp header `Set-Cookie` bằng `response.headers.get("set-cookie")`** trong browser như một header thông thường: đây là **forbidden response-header name** đối với Fetch exposure. Browser xử lý Set-Cookie qua cookie store theo policy.

## 14. Nhiều cookie, giới hạn kích thước và chính sách lưu

Cookies được gửi trong các request phù hợp, vì vậy dữ liệu lớn trong cookie gây overhead mạng và có thể bị browser/proxy từ chối. Trình duyệt có giới hạn kích thước cho từng cookie và số cookie theo domain, nhưng chi tiết khác nhau theo browser/version; tránh lưu JSON object lớn, danh sách quyền hoặc file trong cookie.

Cần:
- Chỉ lưu giá trị nhỏ và cần thiết; dùng server-side state nếu dữ liệu phức tạp.
- Đặt tên rõ ràng, tránh nhiều cookie cùng tên ở các path/domain làm server đọc nhầm giá trị.
- Dùng `Path` hẹp khi thích hợp; tránh `Domain` quá rộng.
- Chọn `Max-Age` đủ ngắn với dữ liệu nhạy cảm và không vượt quá thời hạn phiên phía server.
- Không ghi full `Cookie` hoặc `Set-Cookie` chứa token vào application logs, analytics hay tracing không được kiểm soát.
- Với authentication token, cân nhắc rotation/revocation, ký hoặc mã hóa giá trị khi appropriate; cookie flag **không chứng minh tính toàn vẹn hay chống sửa đổi**.
- Không dựa vào thứ tự cookie khi nhiều cookie cùng tên trong request; server nên thiết kế tránh trùng tên và scope mơ hồ.

Các trình duyệt ngày càng có các tính năng như **Partitioned cookies (CHIPS)** trong những bối cảnh nhúng. Spring Framework 6.2 hỗ trợ `ResponseCookie.ResponseCookieBuilder#partitioned(boolean)`; nhưng nếu ứng dụng đang dùng phiên bản 6.0/6.1, cần đối chiếu API trước khi sử dụng. Đối với cookie partitioned, browser hỗ trợ yêu cầu `Secure` và có các quy tắc partitioning riêng. Bài này tập trung `SameSite` cơ bản, không coi CHIPS là thay thế kiểm soát CSRF.

## 15. Các lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Browser không lưu cookie | `Secure` trên HTTP, SameSite None thiếu Secure, Domain không hợp lệ, third-party policy | Kiểm tra DevTools blocked reason và HTTPS |
| `@CookieValue` nhận null | Browser không gửi cookie do Path/Domain/Secure/expiry/SameSite | Kiểm tra `Cookie` request header, không chỉ `Set-Cookie` response |
| Xóa cookie nhưng vẫn thấy lại | Sai Path/Domain hoặc có cookie cùng tên scope khác | So lại identity lúc tạo/xóa; kiểm tra từng cookie |
| Cookie “7 ngày” chỉ sống 7 giây | Truyền nhầm `maxAge` đơn vị hoặc số giây | Dùng `Duration.ofDays(7)` |
| Cookie bị mất sau khi browser restart | Không có Max-Age/Expires, hoặc browser privacy policy | Đặt thời hạn phù hợp và chấp nhận việc user có thể xóa |
| Session ID còn cookie nhưng server báo hết phiên | Session server timeout/invalidation độc lập | Phân biệt session timeout với cookie expiry |
| JS không đọc `document.cookie` | Cookie có `HttpOnly` | Đúng với session cookie; không tắt nếu là credential |
| Cross-site embed không có cookie | SameSite Lax/Strict, third-party cookie policy, credentials/CORS | Xác minh site/origin và thiết kế authentication phù hợp |
| `SameSite=None` không hoạt động | Thiếu Secure, dùng HTTP, browser chặn tracking | Bật HTTPS và xác minh chính sách trình duyệt |
| API dùng cookie nhưng vẫn có CSRF | Chỉ dựa vào SameSite hoặc endpoint GET có side effects | Bảo vệ CSRF và phương thức HTTP đúng semantics |
| Session cookie không đổi theo property | Cookie do thành phần khác tạo, config không thuộc runtime | Kiểm tra `JSESSIONID` thuộc container hay Spring Session, profile/config |
| Có hai header Set-Cookie bị gộp | Proxy/framework tùy chỉnh combine headers không đúng | Gửi từng Set-Cookie header riêng |
| Thông tin nhạy cảm lộ ở log | Logging trực tiếp Cookie/Set-Cookie headers | Redact credentials và áp dụng log policy |

### Debug có hệ thống

1. **Response:** có thực sự gửi `Set-Cookie` không? Tên/giá trị/Path/Domain/Max-Age/flags là gì?
2. **Browser storage:** cookie được chấp nhận hay bị block? Nguyên nhân browser nêu là gì?
3. **Request tiếp theo:** `Cookie` header có cặp tên–giá trị mong đợi không?
4. **Spring controller:** `@CookieValue` có đúng tên, `required`, conversion không?
5. **Session backend:** nếu là session cookie, session ID còn hợp lệ không? Logout/rotation/timeout đã diễn ra chưa?
6. **Cross-origin:** fetch credentials, CORS, SameSite, schemeful site và third-party policy có phù hợp không?
7. **Security:** kiểm tra CSRF/XSS/session management; không tăng phạm vi cookie bừa bãi chỉ để “sửa lỗi không gửi”.

## 16. Tự kiểm tra kiến thức

**Câu 1. `Set-Cookie` và `Cookie` khác nhau thế nào?**

`Set-Cookie` là response header hướng dẫn browser lưu hoặc cập nhật cookie cùng các attributes. `Cookie` là request header chỉ gửi lại cặp tên–giá trị của những cookie đủ điều kiện.

**Câu 2. `HttpOnly=true` có ngăn browser tự gửi cookie trong `fetch` không?**

Không. `HttpOnly` hạn chế JavaScript trực tiếp đọc/chỉnh cookie; browser vẫn có thể đính cookie vào request hợp lệ, tùy `credentials`, SameSite, Secure, scope và browser policy.

**Câu 3. Vì sao `SameSite=None` cần `Secure`?**

Browser hiện đại yêu cầu kết hợp này để cho phép cookie trong các ngữ cảnh cross-site được phép. Dù đủ hai thuộc tính, browser vẫn có thể chặn third-party cookie.

**Câu 4. Cookie được đặt `Max-Age=3600` tồn tại khoảng bao lâu?**

Khoảng một giờ, vì đơn vị là **giây**. Client vẫn có thể xóa sớm. Không nhầm với `server.servlet.session.timeout` của server-side session.

**Câu 5. Vì sao chỉ xóa `JSESSIONID` cookie chưa chắc là logout an toàn?**

Vì session/token còn cần được vô hiệu hóa phía server; session ID đã rò rỉ có thể vẫn có hiệu lực. Sử dụng Spring Security logout/session management.

**Câu 6. `SameSite=Lax` có thay thế CSRF token không?**

Không. Nó hạn chế một số cross-site request nhưng không loại bỏ mọi tình huống giả mạo hoặc sai thiết kế phương thức HTTP.

**Câu 7. Muốn xóa cookie có `Path=/api/prefs` thì chỉ cần `Max-Age=0; Path=/`?**

Không chắc. Xóa cookie cần cùng tên và phạm vi path/domain tương thích với cookie gốc. Nên đặt lại đúng `Path=/api/prefs`.

**Câu 8. `Secure` có phải là mã hóa giá trị cookie ở ổ cứng không?**

Không. Nó giới hạn truyền qua HTTPS trong browser hỗ trợ, không bảo đảm dữ liệu lưu client được mã hóa và không thay server-side authorization.

## 17. Checklist triển khai production

1. Phân loại rõ cookie **session/authentication** và cookie **preference**. Không tự viết session management nếu Spring Security đã sở hữu việc đó.
2. Chọn `Max-Age`/session timeout theo nghiệp vụ; hiểu cookie expiry và server-side session expiry khác nhau.
3. Với cookie nhạy cảm, sử dụng HTTPS và `Secure`, `HttpOnly`, `SameSite=Lax` hoặc `Strict` nếu phù hợp luồng; không chọn `None` nếu không cần cross-site.
4. Bỏ `Domain` nếu không cần subdomain share; đặt `Path` hạn chế theo nhu cầu. Cân nhắc prefix `__Host-`/ `__Secure-` trong môi trường HTTPS.
5. Luôn validate cookie khi nhận; không sử dụng dữ liệu cookie client kiểm soát để cấp quyền.
6. Khi xóa, dùng đúng tên, domain, path và `Max-Age=0`; nếu là authentication session, vô hiệu phiên phía server.
7. Kiểm thử cả HTTP response `Set-Cookie` và request `Cookie`, URL path khác nhau, expiry, CSRF/CORS và browser acceptance trong HTTPS thực tế.
8. Kiểm soát logging, số lượng và dung lượng cookie; không đưa credential vào URL hoặc log.
9. Nếu triển khai cross-site iframe/SPA, phân biệt **same-site** với **same-origin**, kiểm tra policy bên thứ ba và CORS credential, không sửa bằng cách tắt toàn bộ ràng buộc bảo mật.
10. Đối với session cookie, cấu hình qua `server.servlet.session.cookie.*` và Spring Security theo đúng chủ sở hữu cookie, không sao chép code tạo cookie preference để thay `JSESSIONID`.

## Tài liệu chính thức

- [Spring Framework 6.2 — `ResponseCookie.ResponseCookieBuilder` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/http/ResponseCookie.ResponseCookieBuilder.html)
- [Spring Framework — `@CookieValue` trong Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/cookievalue.html)
- [Spring Boot 3.5 — Servlet Web Applications / SameSite Cookies](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot 3.5 — Application Properties (session cookie)](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [MDN — Set-Cookie HTTP header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
