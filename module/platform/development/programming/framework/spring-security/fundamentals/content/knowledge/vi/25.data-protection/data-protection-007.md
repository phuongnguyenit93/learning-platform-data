# Không đưa credentials, cookie hoặc token vào URL và thông báo lỗi

## 1. Vì sao dữ liệu xác thực không được đi theo URL?

Thông tin xác thực (credentials) là dữ liệu giúp một bên chứng minh danh tính hoặc sử dụng một quyền truy cập. Ví dụ: mật khẩu, mã phiên (session ID), API key, OAuth access token, refresh token, mã xác thực một lần hoặc khóa bí mật. **Ai có được một số loại dữ liệu này có thể hành động thay người dùng hoặc ứng dụng**, ít nhất trong khoảng thời gian dữ liệu còn hiệu lực.

Hai cách vô tình làm lộ dữ liệu xác thực thường gặp là:

1. **Gắn bí mật vào URL**: `/account?token=...`, `/users/password/abc...`, `https://user:password@example.com`, `/page#access_token=...`.
2. **Đưa bí mật vào lỗi công khai**: trả nguyên `Exception.getMessage()`, URL request, query string, header `Authorization`, cookie, câu SQL hoặc stack trace cho trình duyệt/ứng dụng khách.

HTTPS mã hóa dữ liệu khi truyền giữa các điểm kết nối TLS; **HTTPS không xóa URL khỏi lịch sử trình duyệt, log reverse proxy, hệ thống giám sát, công cụ phân tích hoặc ảnh chụp màn hình**. Tương tự, chỉ ẩn thông báo lỗi ở giao diện không đủ nếu API vẫn gửi bí mật trong JSON, header hoặc redirect.

Mục tiêu của bài học trong phạm vi **Spring Security Servlet và Spring Boot 3.x, Java 17+**:

- Hiểu chính xác URL, header, cookie, body và error response có thể làm lộ những gì.
- Đặt credentials và token vào kênh phù hợp; không biến địa chỉ tài nguyên thành “mật khẩu”.
- Xử lý lỗi có status/mã lỗi ổn định mà không phản chiếu bí mật người gọi hoặc thông tin nội bộ.
- Đánh giá đúng các ngoại lệ giao thức như OAuth 2.0 authorization code và liên kết khôi phục tài khoản.
- Viết kiểm thử dương tính và âm tính để chứng minh URL/response không vô tình chứa bí mật.

## 2. URL rò rỉ thông tin qua những con đường nào?

Xét URL **không nên tạo**:

```text
https://app.example.com/api/orders?access_token=FAKE_TOKEN_ONLY_FOR_DEMO
```

Dù đường truyền sử dụng HTTPS, chuỗi này vẫn có thể bị sao chép vào nhiều nơi:

| Nơi lưu/chia sẻ | Vì sao có nguy cơ? | Cần kiểm soát gì? |
| --- | --- | --- |
| Lịch sử, bookmark và thanh địa chỉ trình duyệt | Người dùng có thể lưu, chia sẻ hoặc chụp ảnh URL đầy đủ. | Không đặt credential trong URL ngay từ thiết kế. |
| Access log của web server, load balancer, gateway, proxy | Request target có thể được ghi kèm path và query. | Cấu hình log không thu query có dữ liệu bí mật; rà soát từng tầng. |
| APM, tracing, metrics, hệ thống báo lỗi | “Full URL”, trace attribute hoặc exception message có thể được thu tự động. | Chỉ ghi route template và dữ liệu cho phép; redaction từ điểm thu thập. |
| Header `Referer` khi chuyển trang/tải tài nguyên | URL nguồn có thể được gửi theo chính sách referrer; mức chi tiết tùy same-origin/cross-origin và header. | Chính sách `Referrer-Policy` phù hợp, nhưng vẫn không đưa bí mật vào URL. |
| JavaScript trên trang và extension trình duyệt | Script có quyền phù hợp có thể đọc `location.href`, `location.search` hoặc `location.hash`. | Giới hạn script bên thứ ba, CSP và dữ liệu trong URL. |
| Chat, email, ticket hỗ trợ và ảnh màn hình | Người dùng có thể dán URL vào môi trường khác. | Dùng correlation ID công khai thay cho URL chứa token khi cần hỗ trợ. |
| Redirect và trang thông báo lỗi | `Location`, `next`, `returnUrl` hoặc lỗi chứa nguyên URL đầu vào có thể tái phát tán token. | Kiểm tra redirect đích và không ghép bí mật vào URL/header/body. |

Cần phân biệt cấu trúc URL:

```text
https://user:pass@host.example.com/orders/SECRET_PATH?token=SECRET_QUERY#SECRET_FRAGMENT
        └user info┘                        └path─────┘ └query─────┘ └fragment────┘
```

- **Userinfo (`user:pass@`)**: lối biểu diễn tài khoản/mật khẩu cũ trong URI; không dùng để chuyển thông tin đăng nhập.
- **Path**: `/reset/TOKEN` cũng có thể xuất hiện trong history, access log, analytics hoặc liên kết chia sẻ. Bỏ token khỏi query nhưng đưa vào path **không giải quyết vấn đề**.
- **Query**: `?token=...`, `?password=...` xuất hiện trong URL request và có nguy cơ bị log/thu thập. Giá trị có thể bị encode nhưng encode **không phải mã hóa**.
- **Fragment (`#...`)**: theo ngữ nghĩa HTTP, trình duyệt **không gửi fragment tới máy chủ trong HTTP request target**; `Referer` cũng không được chứa fragment. Tuy nhiên fragment vẫn hiện trong lịch sử/thanh địa chỉ, có thể bị JavaScript/extension đọc, nên **không phải nơi an toàn để lưu access token**. Luồng OAuth implicit từng dùng fragment cho token; các khuyến nghị hiện đại ưu tiên luồng authorization code kết hợp PKCE.

Quy tắc thực hành: nếu một URL có thể được bookmark, dán vào chat hoặc xuất hiện trên hệ thống log, hãy giả định **nó có thể bị chia sẻ ngoài ý định**. Không dùng URL như kho lưu credentials.

## 3. Đặt từng loại thông tin vào kênh thích hợp

| Loại dữ liệu | Kênh phù hợp trong ứng dụng web/API | Điều cần tránh |
| --- | --- | --- |
| Tên đăng nhập, mật khẩu khi đăng nhập | `POST` với form/body qua HTTPS; server xác thực và áp dụng rate limit. | `GET /login?password=...`, log body, đưa mật khẩu vào redirect. |
| OAuth access token dạng bearer | Header `Authorization: Bearer <token>` qua HTTPS. | `?access_token=...`, path chứa token, gửi token cho sai origin. |
| Refresh token | Kênh token endpoint được giao thức quy định, quản lý lưu trữ an toàn; với browser ưu tiên kiến trúc tránh lộ token cho script không tin cậy. | URL/fragment, localStorage không được đánh giá rủi ro, log/token analytics. |
| Session ID do server quản lý | Cookie với `Secure`, `HttpOnly`, `SameSite` phù hợp, phạm vi `Path`/`Domain` hẹp nhất có thể. | `?jsessionid=...`, `;jsessionid=...` trong path, cookie trong thông báo lỗi. |
| API key của dịch vụ | Header do API định nghĩa (ví dụ `X-API-Key` hoặc `Authorization`), qua HTTPS, giới hạn quyền và xoay vòng. | Query parameter, commit trong mã nguồn, log header nguyên vẹn. |
| CSRF token | Hidden form field hoặc header do framework/ứng dụng quy định. | Đưa token trong URL; hiểu nhầm CSRF token thay thế xác thực. |
| Error/correlation ID | Mã ngẫu nhiên không chứa bí mật trong header hoặc body response. | Dùng access token, session ID hoặc nguyên URL làm “mã hỗ trợ”. |

**Lưu ý:** header và body không phải “vùng chứa an toàn tuyệt đối”. Proxy, debug log, APM hoặc mã frontend vẫn có thể làm lộ `Authorization`, `Cookie`, `Set-Cookie` và body. Chuyển bí mật ra khỏi URL là một bước bắt buộc trong thiết kế, sau đó vẫn cần TLS, lọc log, phân quyền, quản lý vòng đời token và hạn chế script.

### 3.1. Đăng nhập bằng cookie phiên

Ví dụ cách trao đổi phù hợp về mặt vị trí dữ liệu:

```http
POST /login HTTP/1.1
Host: app.example.com
Content-Type: application/x-www-form-urlencoded

username=demo-user&password=FAKE_PASSWORD_FOR_EXAMPLE
```

Sau khi xác thực, server có thể cấp session cookie:

```http
HTTP/1.1 302 Found
Set-Cookie: JSESSIONID=DEMO_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
Location: /dashboard
Cache-Control: no-store
```

Các giá trị trên **chỉ là minh họa giao thức**, không dùng làm thông tin xác thực thật. Cookie session được trình duyệt gửi qua header `Cookie` theo quy tắc cookie; server nên không tự tạo redirect dạng `/dashboard?sid=...`. `Secure` chỉ gửi cookie qua kênh bảo mật theo quy tắc trình duyệt; `HttpOnly` cản JavaScript đọc cookie; `SameSite` góp phần giảm nguy cơ gửi cookie liên site nhưng **không thay thế CSRF** trong mọi trường hợp. Một ứng dụng có thể cần `SameSite=None; Secure` cho luồng cross-site thực sự, sau khi đánh giá rủi ro.

Với session do Servlet container quản lý, cần tránh cơ chế **URL rewriting** có thể chèn `;jsessionid=...` vào link. Dùng cookie-based session tracking khi trình duyệt hỗ trợ cookie, và kiểm tra các URL thực tế sau đăng nhập/chuyển trang. Đổi đường dẫn token từ query sang path hoặc matrix parameter không giúp bảo vệ.

### 3.2. API dùng bearer token

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer FAKE_ACCESS_TOKEN_FOR_EXAMPLE
Accept: application/json
```

Token được đặt ở header do OAuth 2.0 Bearer Token Usage quy định; URL chỉ xác định tài nguyên. Với Spring Security Resource Server, ưu tiên `oauth2ResourceServer(...).jwt(...)` hoặc cấu hình opaque token tương ứng thay vì viết filter tự kiểm tra JWT sơ sài. Server phải xác minh chữ ký hoặc introspection, hạn dùng, issuer, audience, scope/quyền theo loại token. **Mọi token mẫu đều là giả**; không in token thật ra console, log hoặc tài liệu.

Khi một client gửi sai token, không viết lỗi:

```json
{
  "message": "Bearer eyJhbGciOi... bị từ chối",
  "requestUrl": "/api/orders?access_token=eyJhbGciOi..."
}
```

Thay bằng status và mã công khai, đồng thời giữ challenge `WWW-Authenticate` khi cơ chế xác thực yêu cầu. Đối với OAuth Bearer, việc trả mã lỗi/thông tin chuẩn trong challenge phải tuân theo giao thức và chính sách tiết lộ thông tin; tuyệt đối không nhúng giá trị token vào challenge.

### 3.3. Gửi dữ liệu bí mật trong body không có nghĩa là có thể log body

Một request `POST` qua HTTPS có body chứa mật khẩu tránh nhiều bề mặt rò rỉ của URL. Nhưng middleware cấu hình `logRequestBody=true` hoặc exception handler in request body vẫn có thể làm lộ mật khẩu. Đặc biệt tránh ghi raw payload ở endpoint `/login`, `/token`, `/reset-password` hoặc request chứa dữ liệu cá nhân.

Đối với frontend, tránh `window.location = "/api/pay?token=" + accessToken`; nếu cần gửi bearer token đến API, dùng `fetch` với header phù hợp, và bảo đảm đích gọi là origin tin cậy:

```javascript
// accessToken lấy từ cơ chế phiên/token đã được thiết kế an toàn.
// Đây là trích đoạn frontend, không phải hướng dẫn lưu token trong localStorage.
const response = await fetch("https://api.example.com/orders", {
  method: "GET",
  headers: { Authorization: "Bearer " + accessToken }
});

if (response.status === 401) {
  // Giao diện xử lý phiên hết hạn theo hợp đồng API.
}
```

Mã trên chỉ minh họa **vị trí truyền token**; các vấn đề lưu trữ token, XSS, CORS, thời hạn, refresh và lỗi mạng vẫn phải xử lý theo kiến trúc thực tế.

## 4. Những trường hợp giao thức có dữ liệu giống token trong URL

Nguyên tắc “không đưa access/refresh/session token vào URL” không có nghĩa là được tự ý sửa cú pháp những giao thức dùng **mã giao dịch ngắn hạn** trong URL. Phân biệt các trường hợp sau:

### 4.1. OAuth 2.0 Authorization Code với PKCE

Luồng Authorization Code thường chuyển trình duyệt về:

```text
https://client.example.com/login/oauth2/code/provider?code=ONE_TIME_CODE&state=RANDOM_STATE
```

Theo OAuth 2.0, `code` là **authorization code** ngắn hạn, dùng một lần để trao đổi token ở kênh/token endpoint phù hợp; nó **không phải access token** để gọi resource API. Đây là một thành phần giao thức có kiểm soát, không phải giấy phép đặt access token, refresh token, mật khẩu hoặc session ID vào query.

Các yêu cầu bảo vệ gồm:

- Sử dụng **Authorization Code + PKCE** (ưu tiên `S256`), kiểm tra `state` và ngữ cảnh phiên/khởi tạo đăng nhập theo thiết kế chống CSRF.
- Chỉ chấp nhận redirect URI được đăng ký chính xác và dùng HTTPS tại endpoint công khai khi phù hợp.
- Authorization code ngắn hạn, dùng một lần, ràng buộc client và redirect URI theo giao thức; không log `code` hoặc `state` nguyên giá trị trong hệ thống vận hành.
- Sau khi xử lý callback, chuyển người dùng sang URL sạch, tránh để `code` tiếp tục xuất hiện ở màn hình làm việc, link chia sẻ hoặc analytics.
- Không dùng implicit flow trả `access_token` vào fragment như một cách mặc định cho SPA mới.

Mặc dù cơ chế PKCE giảm nguy cơ dùng code bị chặn, code vẫn là dữ liệu nhạy cảm theo ngữ cảnh. Xử lý callback bằng thư viện Spring Security OAuth2 Client giúp tránh tự viết sai bước xác minh. Không chỉnh sửa hợp đồng `/login/oauth2/code/...` chỉ để “URL không có bất kỳ mã nào” rồi phá hỏng login.

### 4.2. Liên kết đặt lại mật khẩu và xác minh email

Email khôi phục tài khoản thường phải chứa **mã khôi phục tạm thời** trong link để người nhận mở trang:

```text
https://app.example.com/reset?code=ONE_TIME_RESET_CODE
```

Đây là ngoại lệ nghiệp vụ cần được bảo vệ nghiêm ngặt, vì người có link trong thời hạn có thể thực hiện thao tác nhạy cảm. Thiết kế nên có:

1. Mã ngẫu nhiên đủ khó đoán, phạm vi sử dụng cụ thể, **thời hạn ngắn**, **dùng một lần**; lưu giá trị băm/xác minh phía server khi phù hợp và vô hiệu hóa sau thành công.
2. HTTPS, rate limit, kiểm toán và không tiết lộ tài khoản tồn tại khi gửi yêu cầu khôi phục.
3. Trang nhận link không tải analytics/script/tài nguyên bên thứ ba không cần thiết; đặt `Referrer-Policy: no-referrer` và `Cache-Control: no-store`.
4. Tránh log URL/code ở CDN, proxy, gateway, APM, JavaScript lỗi hoặc ticket hỗ trợ. Một filter ở cuối request không thể xóa log mà gateway đã ghi trước đó.
5. Có thể đổi code thành một phiên quy trình ngắn hạn, sau đó điều hướng tới URL sạch; dùng `POST` cho thao tác đổi mật khẩu và xác thực code đúng quy trình.
6. Nếu phát hiện link đã lộ, xem code là đã bị xâm phạm: thu hồi, cấp lại và kiểm tra khả năng bị sử dụng trái phép.

**Không** biến reset code thành access token dài hạn. `history.replaceState` chỉ xóa hiển thị URL khỏi thanh địa chỉ sau khi trang đã tải, **không thu hồi được** bản sao có thể đã nằm trong lịch sử trước đó, network log hoặc proxy.

### 4.3. URL ký sẵn (presigned URL)

Một URL ký để tải file trong thời gian giới hạn là **khả năng truy cập dạng bearer**. Nó có thể là yêu cầu của hệ thống lưu trữ hoặc phân phối file, nhưng phải hạn chế thời hạn, quyền/method, tài nguyên, chia sẻ và logging; tránh gửi cho bên không liên quan. Nó **không phải** cơ chế dùng chung để truyền bearer token đăng nhập của người dùng.

## 5. Nguyên tắc thiết kế thông báo lỗi không lộ dữ liệu

Một thông báo lỗi tốt trả lời được: request có thành công không, cần người dùng làm gì tiếp theo, và đội vận hành tra cứu bằng gì. Nó **không cần** trả câu SQL, tên máy chủ, class Java, access token hoặc mật khẩu.

| Lỗi | Không nên trả | Thông báo công khai phù hợp |
| --- | --- | --- |
| Đăng nhập sai | “Không có user `alice@example.com`” hoặc “password `123456` không đúng” | “Tên đăng nhập hoặc mật khẩu không hợp lệ.” |
| Phiên hết hạn/không có xác thực | “Cookie `JSESSIONID=...` đã hết hạn” | 401 + `AUTHENTICATION_REQUIRED`; client đăng nhập lại. |
| Không có quyền | “Bạn thiếu role `FINANCE_ROOT` trong bảng ACL `internal_roles`” | 403 + `ACCESS_DENIED` hoặc chính sách 404 đã thiết kế. |
| Lỗi token | “JWT `eyJ...` invalid signature at line ...” | 401 + mã hợp lệ theo giao thức, không chứa giá trị token. |
| Input không hợp lệ | Trả toàn bộ body chứa mật khẩu/API key | 400 + tên trường và quy tắc kiểm tra **được phép công khai**. |
| Lỗi 500 | `Exception.getMessage()`, stack trace, kết nối DB, raw URL | 500 + `INTERNAL_ERROR` và correlation ID nếu hệ thống hỗ trợ. |
| Lỗi không tìm thấy route | `request.getRequestURL() + "?" + request.getQueryString()` | 404 + thông báo trung tính, không phản chiếu query. |

Ví dụ hợp đồng đơn giản:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
Cache-Control: no-store
```

```json
{
  "code": "INTERNAL_ERROR",
  "message": "Không thể xử lý yêu cầu lúc này."
}
```

Nếu có correlation ID, mã đó nên ngẫu nhiên, không chứa thông tin xác thực hoặc dữ liệu người dùng, và có thể tra trong log đã hạn chế quyền. Không tái sử dụng token, cookie, session ID hoặc nguyên URL làm correlation ID. Một số API dùng `ProblemDetail` theo RFC 9457, có thể thêm mã lỗi công khai dưới thuộc tính mở rộng; nhất quán hợp đồng quan trọng hơn tên trường chính xác của ví dụ này.

### 5.1. Các nguồn rò rỉ từ lỗi mà dễ bỏ sót

- `exception.getMessage()` và `ex.toString()` có thể chứa chuỗi kết nối, đường dẫn file, nội dung query hoặc dữ liệu từ dịch vụ thứ ba.
- `request.getQueryString()` và `request.getRequestURI()` có thể chứa bí mật trong query/path; không phản chiếu trực tiếp vào JSON/HTML, redirect, `Location` hoặc `WWW-Authenticate`.
- `BindingResult`/validation message và body được echo có thể chứa password/API key; chỉ công khai tên trường/quy tắc đã thẩm định.
- `ResponseStatusException` với lý do do client kiểm soát hoặc exception từ API ngoài có thể làm lộ thông tin nếu xử lý lỗi mặc định trả raw message.
- Trang error mặc định/debug, stacktrace và `server.error.include-*` trên môi trường production phải được kiểm tra; không để người dùng kích hoạt hiển thị stack trace.
- Log nội bộ không có nghĩa là an toàn tuyệt đối: cần che `Authorization`, `Cookie`, `Set-Cookie`, password, refresh token, khóa bí mật và request/response body ở điểm thu thập.
- Không in token ra browser console hoặc gửi token tới dịch vụ analytics khi hiển thị trang lỗi.

**Đừng trộn các lỗi bảo mật với lỗi ứng dụng:** lỗi 401 thường do `AuthenticationEntryPoint` xử lý, 403 do `AccessDeniedHandler` hoặc các cơ chế tương ứng; `@RestControllerAdvice` xử lý lỗi MVC nhưng không mặc nhiên bắt exception từ filter. Khi tùy chỉnh JSON cho 401/Bearer, giữ `WWW-Authenticate` theo chuẩn; không lấy “thông báo đẹp” để phá giao thức xác thực.

## 6. Ví dụ Spring Boot 3.x: chặn tham số URL nhạy cảm và trả lỗi không phản chiếu bí mật

Đây là ví dụ **minh họa một lớp kiểm soát bổ sung**: API demo không chấp nhận các tên query parameter `access_token`, `refresh_token`, `id_token`, `password`, `api_key`... và không đưa giá trị request hoặc nội dung exception vào lỗi.

**Giới hạn quan trọng:** filter dưới đây phát hiện một danh sách tên query đã biết. Nó **không thể chứng minh URL luôn sạch**: bí mật có thể nằm dưới tên `q`, path, mã hóa nhiều lần hoặc ở gateway trước khi vào ứng dụng. Trọng tâm vẫn là thiết kế client không tạo URL chứa bí mật, cấu hình log ở mọi tầng và kiểm thử thực tế. Không dùng filter như một “bộ lọc toàn năng” để thay quy tắc thiết kế.

Ví dụ được viết cho **Java 17+, Spring Boot 3.x và Spring Security 6.x**. Tạo dự án Boot có Gradle wrapper, plugin và main class phù hợp; thêm dependency:

```groovy
// Trích đoạn trong build.gradle (Groovy DSL), không phải file build hoàn chỉnh.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tất cả lớp Java dùng package `demo.safeurl`.

### 6.1. Ứng dụng khởi động

Tệp `src/main/java/demo/safeurl/SafeUrlApplication.java`:

```java
package demo.safeurl;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeUrlApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeUrlApplication.class, args);
    }
}
```

### 6.2. Filter chặn tên tham số query nhạy cảm

Tệp `src/main/java/demo/safeurl/SensitiveQueryGuardFilter.java`:

```java
package demo.safeurl;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Set;

public final class SensitiveQueryGuardFilter extends OncePerRequestFilter {

    private static final Set<String> BLOCKED_NAMES = Set.of(
        "access_token", "refresh_token", "id_token", "password",
        "passwd", "client_secret", "api_key", "apikey",
        "authorization", "cookie", "session_id", "jsessionid"
    );

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        // Dùng đường dẫn request bỏ context path, chỉ kiểm tra API demo.
        String uri = request.getRequestURI();
        String contextPath = request.getContextPath();
        String path = uri.substring(contextPath.length());
        return !path.startsWith("/api/public/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {

        String query = request.getQueryString();

        if (query != null) {
            for (String part : query.split("&")) {
                int equalSign = part.indexOf('=');
                String encodedName = equalSign < 0
                        ? part
                        : part.substring(0, equalSign);

                final String decodedName;
                try {
                    decodedName = URLDecoder.decode(
                            encodedName, StandardCharsets.UTF_8
                    ).toLowerCase(Locale.ROOT);
                } catch (IllegalArgumentException malformedEncoding) {
                    // Không đưa URL hoặc exception vào response/log.
                    writeSafeBadRequest(response);
                    return;
                }

                if (BLOCKED_NAMES.contains(decodedName)) {
                    writeSafeBadRequest(response);
                    return;
                }
            }
        }

        chain.doFilter(request, response);
    }

    private static void writeSafeBadRequest(HttpServletResponse response)
            throws IOException {
        response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.getWriter().write(
            "{\"code\":\"SENSITIVE_URL_PARAMETER\","
            + "\"message\":\"Dữ liệu không hợp lệ trong URL.\"}"
        );
    }
}
```

Điểm thiết kế:

1. `getQueryString()` chỉ dùng để **kiểm tra tên tham số**. Filter không nối `query`, `URI` hoặc exception vào log/response.
2. `URLDecoder` xử lý tên đã percent-encode, ví dụ `access%5Ftoken`; vẫn không bảo đảm phát hiện mọi cách mã hóa/đặt tên lạ. Khi tên có percent-encoding sai, trả 400 với nội dung trung tính.
3. Chỉ hoạt động ở `/api/public/**` theo mục đích bài thực hành; không nên chép danh sách tên và path vào production mà không kiểm kê endpoint.
4. `OncePerRequestFilter` dùng ở **Spring Security filter chain**, không phải Servlet filter bean tự đăng ký; tránh `@Component` ở lớp này khi đồng thời dùng `addFilterBefore`.
5. Chặn query có tên nhạy cảm là biện pháp bổ sung; nếu gateway đã ghi full URL trước khi request tới JVM thì filter không xóa được bản log đó.
6. Phản hồi 400 tĩnh với `Cache-Control: no-store` giúp client nhận lỗi nhất quán mà không phơi bí mật. Trong hệ thống thật, cân nhắc dùng bộ viết lỗi dùng chung và bảo đảm tất cả nhánh lỗi có header bảo vệ phù hợp.

### 6.3. Đưa filter vào chain và giữ mặc định bảo vệ

Tệp `src/main/java/demo/safeurl/SecurityConfig.java`:

```java
package demo.safeurl;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                // Các endpoint chỉ phục vụ ví dụ, không phải mẫu mở API production.
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().denyAll()
            )
            .addFilterBefore(
                new SensitiveQueryGuardFilter(), AuthorizationFilter.class
            );

        return http.build();
    }
}
```

`AuthorizationFilter` được thêm khi cấu hình `authorizeHttpRequests`. Đặt custom filter trước mốc này giúp chặn yêu cầu có query nhạy cảm tại API demo; các endpoint khác vẫn tuân theo phân quyền. Khi request không khớp `shouldNotFilter`, filter sẽ bỏ qua logic của mình nhưng các filter khác trong Spring Security chain vẫn hoạt động.

Đoạn code không tắt CSRF, CORS, security headers hoặc nới `anyRequest` cho toàn hệ thống. Vì ví dụ dùng `GET` công khai để kiểm thử việc rò rỉ URL, nó không minh họa thao tác cập nhật dữ liệu có CSRF token. Nếu ứng dụng thật có `POST` được xác thực bằng cookie, cần kiểm thử CSRF độc lập.

### 6.4. Controller mô phỏng lỗi nội bộ và MVC advice ẩn chi tiết

Tệp `src/main/java/demo/safeurl/DemoController.java`:

```java
package demo.safeurl;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/public")
public class DemoController {

    @GetMapping("/search")
    public Map<String, Object> search(
            @RequestParam(defaultValue = "") String q
    ) {
        // Không phản chiếu nguyên query string hoặc nội dung q ra response.
        return Map.of("accepted", !q.isBlank(), "resultCount", 0);
    }

    @GetMapping("/fail")
    public String fail() {
        // Chuỗi kỹ thuật chỉ để chứng minh nó không xuất hiện trong lỗi công khai.
        throw new IllegalStateException(
            "internal-db=private-node; token=INTERNAL_ONLY"
        );
    }
}
```

Tệp `src/main/java/demo/safeurl/PublicErrorAdvice.java`:

```java
package demo.safeurl;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

@RestControllerAdvice
public class PublicErrorAdvice {

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<Map<String, String>> handleUnexpectedError() {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .header(HttpHeaders.CACHE_CONTROL, "no-store")
            .body(Map.of(
                "code", "INTERNAL_ERROR",
                "message", "Không thể xử lý yêu cầu lúc này."
            ));
    }
}
```

Ở đây `@RestControllerAdvice` chỉ xử lý `IllegalStateException` của ví dụ; **không thể kết luận mọi lỗi từ controller, filter, Spring Security hoặc reverse proxy đã được che giấu**. Trong production, hệ thống cần chính sách toàn diện cho lỗi 400, 401, 403, 404, 500 và các exception thực tế, đồng thời loại bỏ thông tin nhạy cảm khỏi log, APM và trang lỗi mặc định.

## 7. Kiểm thử MockMvc: dữ liệu được chấp nhận, bí mật bị chặn, lỗi không bị phản chiếu

Tệp `src/test/java/demo/safeurl/SensitiveUrlTests.java`:

```java
package demo.safeurl;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SensitiveUrlTests {

    private static final String FAKE_SECRET = "FAKE_SECRET_TEST_ONLY_123";

    @Autowired
    MockMvc mvc;

    @Test
    void ordinaryQueryIsAccepted() throws Exception {
        mvc.perform(get("/api/public/search?q=java"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.accepted").value(true))
            .andExpect(jsonPath("$.resultCount").value(0));
    }

    @Test
    void accessTokenInQueryIsRejectedWithoutReflection()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/api/public/search?access_token=" + FAKE_SECRET)
            )
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("SENSITIVE_URL_PARAMETER"))
            .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
            .andReturn();

        String body = result.getResponse().getContentAsString();
        assertFalse(body.contains(FAKE_SECRET));
        assertFalse(body.contains("access_token"));
    }

    @Test
    void percentEncodedSensitiveParameterNameIsRejected()
            throws Exception {
        mvc.perform(
                get("/api/public/search?access%5Ftoken=" + FAKE_SECRET)
            )
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("SENSITIVE_URL_PARAMETER"));
    }

    @Test
    void passwordInQueryIsRejectedWithoutReflection()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/api/public/search?password=" + FAKE_SECRET)
            )
            .andExpect(status().isBadRequest())
            .andReturn();

        assertFalse(result.getResponse().getContentAsString()
                .contains(FAKE_SECRET));
    }

    @Test
    void exceptionDetailsAndQueryAreNotReturnedToClient()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/api/public/fail?note=harmless")
            )
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
            .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
            .andReturn();

        String body = result.getResponse().getContentAsString();
        assertFalse(body.contains("INTERNAL_ONLY"));
        assertFalse(body.contains("private-node"));
        assertFalse(body.contains("IllegalStateException"));
        assertFalse(body.contains("note=harmless"));
    }
}
```

Chạy trong dự án Boot đã cấu hình Gradle wrapper:

```bash
./gradlew test --tests demo.safeurl.SensitiveUrlTests
```

Khi triển khai đúng các lớp và dependency trên, **năm test được thiết kế để PASS**. Đây là kết quả mong đợi của ví dụ, không phải tuyên bố đã chạy bộ test trong tài liệu. Với `@AutoConfigureMockMvc` và `spring-security-test`, MockMvc chạy qua filter chain được cấu hình của ứng dụng.

| Test | Kết quả mong đợi | Điều chứng minh |
| --- | --- | --- |
| `q=java` | 200, JSON hợp lệ | Query thông thường vẫn được dùng, không chặn nhầm mọi tham số. |
| `access_token=FAKE_SECRET` | 400, mã `SENSITIVE_URL_PARAMETER` | Query chứa tên token bị chặn; response không echo giá trị/tên nhạy cảm. |
| `access%5Ftoken=...` | 400 | Tên tham số URL-encoded thông thường vẫn được phát hiện. |
| `password=FAKE_SECRET` | 400, body sạch | Không phản chiếu credential về client. |
| `/fail?note=...` với lỗi nội bộ | 500, `INTERNAL_ERROR`, body sạch | Exception message, tên hệ thống nội bộ và query không xuất hiện trong response. |

Các test **chỉ đánh giá hành vi ứng dụng ở điểm vào MockMvc**. Chúng chưa chứng minh reverse proxy, CDN, browser history, URL path, log file hoặc APM không ghi token. Để xác minh toàn hệ thống cần test với hạ tầng thật và kiểm tra cấu hình thu thập log/trace tại từng tầng.

Có thể chạy chương trình bằng `./gradlew bootRun`, sau đó gọi GET hợp lệ qua HTTPS ở môi trường triển khai tương ứng. Đừng đưa token thật vào lệnh curl, browser hoặc test; ngay cả dòng lệnh có URL cũng có thể bị lưu vào shell history.

## 8. Bảo vệ thông báo lỗi Spring Security và Spring MVC trong sản phẩm

Ví dụ ở trên chủ yếu minh họa **lỗi 400 từ filter và 500 từ MVC**. Đối với ứng dụng có đăng nhập thực, các luồng 401/403 cần được kiểm tra riêng.

### 8.1. Xử lý 401 và 403 đúng nguồn phát sinh

- **401 Unauthorized:** request cần được xác thực mà chưa có hoặc xác thực không hợp lệ. Ở Spring Security Servlet, nhiều tình huống được xử lý qua `AuthenticationEntryPoint`. Dùng thông điệp trung tính; đừng nói token nào đã sai hoặc gửi lại token.
- **403 Forbidden:** request đã xác thực nhưng không đủ quyền, thường qua `AccessDeniedHandler` hoặc cơ chế xử lý tương ứng. Đừng tiết lộ tên role nội bộ/ACL nhạy cảm hoặc dữ liệu tài nguyên mà người gọi không được phép biết.
- **401 Bearer/Basic:** header `WWW-Authenticate` là một phần quan trọng của giao thức, phải giữ challenge hợp lệ. Không nhét `Authorization` gốc, session cookie hay stack trace vào header challenge.

Nếu có nhiều chuỗi `SecurityFilterChain`, kiểm thử mỗi chain. Bộ xử lý lỗi MVC như `@RestControllerAdvice` không mặc nhiên chạy đối với lỗi phát sinh trước `DispatcherServlet`.

### 8.2. Kiểm soát lỗi mặc định và lỗi debug

Ở môi trường production, đánh giá chính sách Spring Boot `server.error.include-message`, `server.error.include-stacktrace`, `server.error.include-exception`, lỗi validation và trang lỗi mặc định. Không mở cơ chế cho client yêu cầu hiển thị stack trace vì mục đích hỗ trợ.

Ví dụ các thuộc tính cần được quyết định rõ trong `application-prod.yml`:

```yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-exception: false
    include-binding-errors: never
```

Đây là một lớp phòng ngừa đối với cơ chế lỗi mặc định của Boot; handler tự viết vẫn có thể làm lộ dữ liệu nếu trả raw exception, URL hoặc body. Các endpoint debug/Actuator cũng phải được bảo vệ và giới hạn dữ liệu. Không giả định bộ thông báo lỗi đã an toàn chỉ vì cấu hình trên.

### 8.3. Bảo vệ URL trong log, trace và alert

Tránh ghi:

```java
// KHÔNG NÊN: có thể ghi cả credential trong query.
log.warn("Request failed: url={}, reason={}",
         request.getRequestURL() + "?" + request.getQueryString(),
         exception.getMessage());
```

Thay bằng các giá trị đã thẩm định như route template, mã lỗi và correlation ID độc lập:

```java
// Minh họa tại nơi đã có các biến routeName, publicCode, correlationId
// được xác minh là không chứa dữ liệu đầu vào nhạy cảm.
log.warn("Request rejected: route={}, code={}, correlationId={}",
         routeName, publicCode, correlationId);
```

Đây là trích đoạn, không phải class Java độc lập: các biến/logger phải được khai báo trong ứng dụng. Nếu `routeName` được lấy bằng cách sao chép raw URL, bạn đã mất lợi ích. Nếu `exception.getMessage()` có chứa secret, việc lưu nó vào log mà không kiểm soát vẫn có rủi ro dù không hiển thị cho client.

Ở gateway và APM, nên dùng **route template** (chẳng hạn `/api/orders/{id}`) thay vì full URL hoặc query string. Nếu vẫn cần một vài query parameter cho vận hành, chỉ cho phép danh sách tham số không nhạy cảm đã được đánh giá; không dùng “thay chuỗi token=...” làm cơ chế duy nhất vì tên và cách encode rất đa dạng.

## 9. Referrer-Policy, Cache-Control và giới hạn của chúng

Một trang có thông tin nhạy cảm thường cần:

```http
Referrer-Policy: no-referrer
Cache-Control: no-store
X-Content-Type-Options: nosniff
```

- `Referrer-Policy: no-referrer` yêu cầu trình duyệt không gửi header `Referer` từ trang đó. Nó giúp giảm một đường rò rỉ URL, **không làm sạch browser history, access log hay mọi script đã đọc URL**.
- `Cache-Control: no-store` yêu cầu các thành phần cache tuân thủ không lưu trữ response; điều đó **không bảo đảm** ứng dụng không ghi log URL hoặc người dùng không sao chép URL.
- `nosniff` giúp kiểm soát cách trình duyệt xử lý kiểu nội dung; nó **không phải** cơ chế che token.
- Content Security Policy (CSP) và giới hạn third-party script giảm bề mặt script đọc dữ liệu; CSP không thay thế thiết kế URL sạch.
- `Secure` và `HttpOnly` áp dụng cho cookie; chúng không bảo vệ token nằm trong query/path/fragment.

Nếu chỉ thay cấu hình header mà vẫn tiếp tục tạo link `?access_token=...`, lỗ hổng nguồn gốc chưa được giải quyết.

## 10. Ma trận kiểm thử chấp nhận cho ứng dụng thực tế

| Hạng mục | Tình huống cần thử | Dấu hiệu đạt |
| --- | --- | --- |
| Đăng nhập | Form login, redirect thành công/thất bại | URL không mang mật khẩu, session ID, refresh/access token; thông báo sai đăng nhập trung tính. |
| Cookie phiên | Response `Set-Cookie` và request tiếp theo | Cookie có thuộc tính phù hợp, không bị phản chiếu vào URL, JSON lỗi hoặc log. |
| Bearer API | Gọi tài nguyên với `Authorization` hợp lệ/sai | Header đúng giao thức; 401/403 không echo token; access token không nằm ở query. |
| Link nội bộ | Điều hướng, email, chia sẻ URL | Không có token/cookie/credential trong `href`, `Location`, canonical URL hoặc query nối thêm. |
| OAuth callback | Authorization Code + PKCE | Code/state được xác minh và xử lý ngắn hạn; không bị dùng như bearer access token, không ghi log nguyên code. |
| Khôi phục tài khoản | Link đúng/hết hạn/đã dùng/replay | Mã dùng một lần, hết hạn phù hợp, không log/analytics/third-party leak; trang có chính sách referrer và cache an toàn. |
| Lỗi 400 | Dữ liệu nhập vào không hợp lệ hoặc tham số URL nhạy cảm | Status/mã công khai đúng; không phản chiếu password, token, cookie, body nhạy cảm. |
| Lỗi 401 và 403 | Không xác thực hoặc thiếu quyền | Thông điệp trung tính và challenge chuẩn; không lộ tên role nội bộ/token gốc. |
| Lỗi 500 | Exception kỹ thuật có chứa dữ liệu nội bộ | Body và header không có stack, query, secret hay class/hạ tầng; log có cơ chế tra cứu an toàn. |
| Proxy/APM/log | Request chứa chuỗi kiểm thử giả với tên tham số nhạy cảm | Không thấy giá trị thử nghiệm trong access log/trace/analytics/ticket/alert ngoài phạm vi được kiểm soát. |
| Browser history/referrer | Mở, điều hướng và chia sẻ trang | Không phát tán URL chứa token; trình duyệt tuân theo policy đã chọn. |
| Code review | Kiểm tra cách xây URL/redirect và bắt exception | Không có ghép credential vào URL; không trả raw `ex.getMessage()` hay `request.getQueryString()`. |

**Kiểm thử rò rỉ log bằng mã giả an toàn:** dùng sentinel như `FAKE_SECRET_TEST_ONLY_123`, xác nhận request bị chặn hoặc xử lý như thiết kế, rồi tìm sentinel trong log/trace của **môi trường thử nghiệm**. Không sử dụng mật khẩu/token thật cho bài kiểm thử này. Nếu sentinel vẫn xuất hiện trong proxy log trước khi filter chặn, phải sửa cấu hình ghi log ở proxy; không thể khắc phục chỉ bằng controller advice.

## 11. Sai lầm phổ biến và cách sửa

1. **“HTTPS rồi thì URL chứa token không sao.”** HTTPS chỉ xử lý một nhóm nguy cơ trên đường truyền; vẫn có history, log, referrer theo chính sách, analytics và người dùng chia sẻ link.
2. **Chuyển `?token=...` thành `/token/...`.** Path vẫn nằm trong URL, bị log/copy. Hãy dùng header/cookie/body theo loại thông tin.
3. **Đặt token ở `#fragment` để “server không thấy”.** JavaScript, extension và history vẫn có thể thấy; không dùng fragment làm nơi mặc định lưu access token.
4. **Đổi access token thành Base64/URL encoding rồi gắn vào link.** Encoding có thể giải mã dễ dàng; không tăng bí mật.
5. **Gửi password qua GET.** Chuyển sang POST body qua HTTPS và chặn log body nhạy cảm; thêm bảo vệ phù hợp với luồng đăng nhập.
6. **Đọc cookie bằng JavaScript cho tiện.** Cookie phiên nên `HttpOnly` nếu JS không cần đọc; không đưa session ID vào URL hoặc console.
7. **Trả `ex.getMessage()` để người dùng báo lỗi dễ hơn.** Dùng mã lỗi/correlation ID và thông điệp công khai; log nội bộ có phân quyền.
8. **Trả nguyên validation payload.** Danh sách lỗi chỉ chứa tên trường/quy tắc cho phép; không echo password, API key, refresh token.
9. **Chỉ che token bằng regex khi log.** Tên tham số, mã hóa, nested JSON, path và header đa dạng; dùng allowlist trường được log và thiết kế không thu dữ liệu nhạy cảm.
10. **Chỉ sửa lỗi Spring MVC.** Security filter, proxy, gateway, error page và OAuth callback có thể có đường xử lý/log khác.
11. **Nhầm OAuth authorization code với bearer access token.** Code trong redirect là một phần giao thức có bảo vệ PKCE, thời hạn ngắn, dùng một lần; access/refresh token không được đặt bừa vào query.
12. **Tạo link reset vĩnh viễn.** Mã khôi phục phải có hạn, bị vô hiệu hóa sau dùng và được bảo vệ khỏi log, referrer, script và chia sẻ.
13. **Tin rằng 5 MockMvc test đã chứng minh toàn bộ hệ thống an toàn.** Cần kiểm tra browser, proxy, APM và log ngoài JVM.
14. **Dùng dữ liệu thật trong test rò rỉ.** Chỉ dùng token giả/chuỗi sentinel, tránh đưa secret thật vào test output và CI logs.

## 12. Bài tập thực hành

Một API có ba URL sau:

```text
GET  /api/orders?access_token=REAL_VALUE
POST /login?password=REAL_VALUE
GET  /reset?code=ONE_TIME_VALUE
```

Hãy phân tích theo từng trường hợp:

- `/api/orders`: chuyển access token sang header `Authorization: Bearer ...` qua HTTPS, kiểm tra client có đúng origin và token có scope/hạn dùng phù hợp; không tạo URL chứa token.
- `/login`: dùng POST form/body qua HTTPS; không chứa password trong query/path/redirect; ngăn log body và xử lý cookie session/CSRF.
- `/reset`: mã một lần trong link có thể là yêu cầu luồng khôi phục, nhưng phải giới hạn thời gian/quyền, không log, hạn chế script, thêm no-referrer/no-store, xử lý hoàn tất và chuyển sang URL sạch.

Sau đó viết kiểm thử: một request hợp lệ được xử lý; một request đặt token giả trong URL bị từ chối; một exception chứa chuỗi `INTERNAL_ONLY` vẫn tạo response 500 không chứa chuỗi đó; và một phép thử môi trường xác nhận gateway/APM không lưu sentinel.

**Tự đánh giá:** người dùng có thể copy URL, gửi ảnh lỗi và nhờ hỗ trợ mà không vô tình chia sẻ một credential còn hiệu lực không? Server có thể chẩn đoán lỗi mà không ghi token hoặc mật khẩu vào log không? Nếu chưa, thiết kế và kiểm thử vẫn cần cải thiện.

## Tài liệu tham khảo

- OWASP — [Information exposure through query strings in URL](https://community.owasp.org/vulnerabilities/Information_exposure_through_query_strings_in_url).
- OAuth 2.0 Security Best Current Practice — [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700).
- OAuth 2.0 Bearer Token Usage — [RFC 6750](https://www.rfc-editor.org/rfc/rfc6750).
- OAuth 2.0 Authorization Code — [RFC 6749](https://www.rfc-editor.org/rfc/rfc6749).
- PKCE — [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636).
- HTTP Semantics (fragment và `Referer`) — [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110).
- Spring Security — [Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html).
- Spring Security — [Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html).
- Spring Boot — [Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html).