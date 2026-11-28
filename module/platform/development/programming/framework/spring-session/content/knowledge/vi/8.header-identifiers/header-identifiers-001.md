# HttpSessionIdResolver và tách cơ chế truyền định danh khỏi kho lưu

## Mục tiêu bài học

Trong ứng dụng Spring Session Servlet, Session ID cần được truyền từ client đến máy chủ để tìm lại phiên tương ứng. Cơ chế truyền ID có thể là cookie hoặc HTTP header, trong khi dữ liệu session được lưu ở Redis, JDBC hoặc một repository khác.

`HttpSessionIdResolver` là abstraction tách hai việc đó. Nó xử lý cách đọc ID từ request và cách gửi hoặc xóa ID trong response. Repository chịu trách nhiệm tạo, tìm, lưu và xóa dữ liệu phiên.

Sau bài học, bạn có thể:

- Giải thích vì sao cơ chế truyền Session ID nên độc lập với nơi lưu dữ liệu session.
- Mô tả vai trò của `HttpSessionIdResolver`, `SessionRepositoryFilter` và `SessionRepository`.
- Phân biệt cookie resolver và header resolver.
- Chọn resolver phù hợp với trình duyệt, mobile app hoặc API client.
- Cấu hình resolver mà không phải thay đổi controller hay repository.
- Nhận biết giới hạn khi hỗ trợ nhiều nguồn định danh.
- Kiểm thử việc tải cùng một session qua các request và repository khác nhau.

## 1. Hai câu hỏi khác nhau khi quản lý session

Khi xử lý một request có trạng thái, ứng dụng cần trả lời hai câu hỏi:

1. Client gửi Session ID ở đâu và response trả ID mới bằng cách nào?
2. Với Session ID đó, dữ liệu session được lưu và truy xuất ở đâu?

Đây là hai trách nhiệm độc lập.

**Cơ chế truyền định danh** là phần giao tiếp giữa client và server. Ví dụ:

- Trình duyệt gửi cookie có tên `SESSION`.
- Mobile app gửi header `X-Auth-Token`.
- Một API client gửi header `Authorization: Bearer ...`.

**Kho lưu session** là nơi lưu dữ liệu phiên, ví dụ:

- Redis lưu dữ liệu session trong key/value có TTL.
- JDBC lưu dữ liệu session trong bảng quan hệ.
- Repository tùy chỉnh lưu dữ liệu theo cơ chế riêng.

Một Session ID có thể được truyền qua cookie hoặc header mà không làm thay đổi repository. Nếu ứng dụng chuyển dữ liệu session từ Redis sang JDBC, client vẫn có thể gửi cùng loại cookie hoặc header, miễn là các instance mới tiếp tục hiểu cùng định dạng ID và dữ liệu session được chuyển đổi hoặc lưu trong repository mới.

| Câu hỏi | Thành phần phụ trách | Ví dụ |
|---|---|---|
| Đọc Session ID từ request | Resolver | Cookie hoặc header |
| Gửi Session ID trong response | Resolver | Set-Cookie hoặc response header |
| Tìm session theo ID | Repository | Redis hoặc JDBC |
| Lưu thay đổi của session | Repository | Ghi key Redis hoặc row JDBC |
| Bọc request để ứng dụng dùng HttpSession | Filter | SessionRepositoryFilter |

Tách trách nhiệm giúp ứng dụng thay đổi cách client truyền ID mà không phải viết lại logic lưu session.

## 2. HttpSessionIdResolver là gì?

`HttpSessionIdResolver` là interface của Spring Session trong package `org.springframework.session.web.http`. Nó xác định cách lấy Session ID từ request và cách gửi chỉ thị định danh trong response.

Các thao tác chính:

| Phương thức | Trách nhiệm |
|---|---|
| `resolveSessionIds(request)` | Đọc các Session ID mà client gửi trong request |
| `setSessionId(request, response, sessionId)` | Gửi Session ID về client khi một phiên mới được tạo hoặc ID được thay đổi |
| `expireSession(request, response)` | Yêu cầu client xóa hoặc ngừng sử dụng định danh phiên |

Resolver làm việc ở tầng HTTP. Nó không cần biết dữ liệu session nằm ở Redis hay JDBC, không thực hiện câu lệnh SQL và cũng không gọi Redis để tìm thuộc tính.

Ví dụ, khi dùng header resolver, resolver chỉ đọc header rồi trả chuỗi ID cho filter. Filter chuyển ID đó cho repository. Repository mới là thành phần tìm dữ liệu phiên.

### Resolver không phải cơ chế xác thực

Resolver chỉ giúp ứng dụng nhận diện phiên. Việc request có một ID hợp lệ không tự chứng minh người gửi có quyền truy cập tài nguyên.

Một Session ID bị đánh cắp có thể được dùng để tiếp tục phiên nếu repository vẫn còn lưu phiên đó. Vì vậy, ID phải được xem như bí mật dạng bearer và được bảo vệ bằng HTTPS, kiểm soát truy cập và chính sách lưu trữ phù hợp.

Xác thực và phân quyền vẫn do Spring Security hoặc logic bảo mật của ứng dụng đảm nhiệm. Resolver không thay thế authentication filter, authorization rule hay kiểm tra quyền sở hữu dữ liệu.

## 3. SessionRepositoryFilter kết nối resolver với repository

Trong ứng dụng Servlet, Spring Session tích hợp qua `SessionRepositoryFilter`. Filter này bọc request và response để ứng dụng tiếp tục dùng Servlet API như `HttpSession`, trong khi việc quản lý session được chuyển đến Spring Session.

Luồng xử lý khái quát:

1. Client gửi request có cookie hoặc header chứa Session ID.
2. `SessionRepositoryFilter` gọi `HttpSessionIdResolver` để đọc ID.
3. Filter yêu cầu `SessionRepository` tìm session theo ID.
4. Nếu repository tìm thấy session, filter cung cấp session đó qua request wrapper.
5. Controller hoặc filter tiếp theo truy cập session qua `request.getSession(false)` hoặc `request.getSession()`.
6. Khi ứng dụng tạo session mới, resolver gửi ID mới trong response.
7. Khi session bị invalidate, resolver gửi chỉ thị xóa định danh về client và repository xử lý việc xóa dữ liệu.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as SessionRepositoryFilter
    participant I as HttpSessionIdResolver
    participant R as SessionRepository
    participant A as Servlet Application

    C->>F: Request + cookie/header
    F->>I: resolveSessionIds(request)
    I-->>F: Session ID
    F->>R: findById(id)
    R-->>F: Session hoặc không tìm thấy
    F->>A: Wrapped request và HttpSession
    A->>A: Đọc hoặc cập nhật thuộc tính
    A-->>F: Kết thúc xử lý
    F->>R: Lưu hoặc xóa session
    F->>I: setSessionId / expireSession
    I-->>C: Cookie hoặc response header
~~~

Tên phương thức trong sơ đồ biểu diễn trách nhiệm của các thành phần; chi tiết lưu và flush phụ thuộc repository và cấu hình Spring Session.

### Vai trò của SessionRepository

`SessionRepository` là abstraction lưu trữ session. Repository cung cấp các thao tác cốt lõi như:

- Tạo session mới.
- Tìm session theo ID.
- Lưu session hoặc các thay đổi của nó.
- Xóa session theo ID.

Repository không cần biết ID đến từ cookie hay header. Khi nhận ID, nó chỉ xử lý việc tìm dữ liệu phiên.

Đó là lý do cùng một resolver có thể hoạt động với nhiều repository khác nhau. Chuyển từ Redis sang JDBC không bắt buộc phải thay đổi cookie name hoặc header name.

## 4. CookieHttpSessionIdResolver

`CookieHttpSessionIdResolver` là resolver sử dụng cookie để truyền Session ID. Đây là lựa chọn phổ biến cho ứng dụng web có trình duyệt làm client.

Khi một session mới được tạo, response thường chứa header `Set-Cookie`:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=opaque-session-id; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

Trong request tiếp theo, trình duyệt gửi lại cookie:

~~~http
GET /account HTTP/1.1
Host: app.example
Cookie: SESSION=opaque-session-id
~~~

Resolver đọc cookie, trả Session ID cho filter và filter tìm session trong repository.

### Cookie serializer

`CookieHttpSessionIdResolver` sử dụng `CookieSerializer` để quyết định tên cookie và các thuộc tính của nó. Spring Session cung cấp `DefaultCookieSerializer` để cấu hình những thuộc tính phổ biến.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class SessionCookieConfiguration {

    @Bean
    public CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer =
                new DefaultCookieSerializer();

        serializer.setCookieName("SESSION");
        serializer.setCookiePath("/");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");

        return serializer;
    }
}
~~~

Các thuộc tính cần cân nhắc:

| Thuộc tính | Ý nghĩa |
|---|---|
| Cookie name | Tên cookie mang Session ID |
| Path | Phạm vi URL mà trình duyệt gửi cookie |
| Domain | Phạm vi host được phép nhận cookie |
| HttpOnly | Ngăn JavaScript đọc cookie qua API cookie thông thường |
| Secure | Chỉ gửi cookie qua HTTPS |
| SameSite | Điều chỉnh việc gửi cookie trong ngữ cảnh cross-site |
| Max-Age | Thời hạn cookie ở trình duyệt, độc lập với timeout phía server |

Trong production, cookie session nên được truyền qua HTTPS và bật `Secure`. `HttpOnly` giúp giảm khả năng JavaScript lấy trực tiếp cookie, nhưng không loại bỏ lỗ hổng XSS. `SameSite` hỗ trợ giảm một số tình huống CSRF nhưng không thay thế toàn bộ cơ chế bảo vệ CSRF.

Cookie có domain hoặc path quá rộng làm tăng phạm vi request gửi định danh. Chỉ cấu hình chia sẻ cookie giữa subdomain khi ứng dụng thật sự cần điều đó.

### Khi nào nên dùng cookie resolver?

Cookie resolver phù hợp khi:

- Client chính là trình duyệt.
- Muốn trình duyệt tự lưu và gửi Session ID.
- Ứng dụng dùng luồng web truyền thống hoặc frontend web cần cookie session.
- Có thể cấu hình CSRF, SameSite, CORS và credentials phù hợp.

Vì trình duyệt tự động gửi cookie, ứng dụng phải đánh giá nguy cơ CSRF. Nếu frontend và backend khác origin, cần cấu hình CORS và credentials cẩn thận; cookie cross-site có thể cần `SameSite=None` cùng `Secure`.

## 5. HeaderHttpSessionIdResolver

`HeaderHttpSessionIdResolver` sử dụng HTTP header để truyền Session ID. Cách này phù hợp với client chủ động tạo request và tự quản lý định danh, chẳng hạn mobile app hoặc một số API client.

Spring Session cung cấp các factory method phổ biến:

- `HeaderHttpSessionIdResolver.xAuthToken()` dùng header `X-Auth-Token`.
- `HeaderHttpSessionIdResolver.bearerAuth()` dùng header `Authorization` theo định dạng Bearer.

Ví dụ cấu hình bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.HeaderHttpSessionIdResolver;
import org.springframework.session.web.http.HttpSessionIdResolver;

@Configuration
public class SessionResolverConfiguration {

    @Bean
    public HttpSessionIdResolver httpSessionIdResolver() {
        return HeaderHttpSessionIdResolver.xAuthToken();
    }
}
~~~

Client gửi request:

~~~http
GET /api/profile HTTP/1.1
Host: api.example
X-Auth-Token: opaque-session-id
~~~

Khi session mới được tạo, resolver có thể trả ID trong response header tương ứng. Client cần đọc header đó, lưu ID an toàn và gửi lại ở request sau.

Nếu dùng Bearer resolver:

~~~http
GET /api/profile HTTP/1.1
Host: api.example
Authorization: Bearer opaque-session-id
~~~

Cần phân biệt rõ: với Bearer resolver, chuỗi trong header được dùng làm Session ID. Nó không tự trở thành OAuth access token hoặc JWT. Nếu API đồng thời hỗ trợ OAuth/JWT và Spring Session, cần định nghĩa rõ header nào thuộc cơ chế nào để tránh xung đột.

### Khi nào nên dùng header resolver?

Header resolver phù hợp khi:

- Mobile app tự quản lý vòng đời credential.
- API client cần gửi ID tường minh trong từng request.
- Service-to-service client có cơ chế lưu và truyền Session ID riêng.
- Giao thức API đã quy định header định danh phiên.

Client phải bảo vệ Session ID trong bộ nhớ hoặc secure storage. Không ghi header này vào log, analytics hay URL.

## 6. Resolver và repository có thể thay đổi độc lập

Điểm quan trọng nhất của abstraction là resolver không bị gắn cứng với repository.

Ví dụ cùng một ứng dụng có thể dùng:

| Client truyền ID | Repository | Resolver |
|---|---|---|
| Trình duyệt gửi cookie SESSION | Redis | Cookie resolver |
| Trình duyệt gửi cookie SESSION | JDBC | Cookie resolver |
| Mobile app gửi X-Auth-Token | Redis | Header resolver |
| Mobile app gửi X-Auth-Token | JDBC | Header resolver |

Khi đổi Redis sang JDBC, nếu Session ID và cấu trúc dữ liệu được di chuyển hoặc tương thích, client không cần biết nơi lưu đã thay đổi. Khi đổi từ cookie sang header, repository vẫn có thể giữ nguyên.

Tuy nhiên, việc đổi repository không tự động di chuyển dữ liệu. Nếu chuyển từ Redis sang JDBC, cần có kế hoạch migration hoặc chấp nhận người dùng phải tạo phiên mới. Resolver chỉ giữ giao thức truyền ID; nó không sao chép dữ liệu session giữa hai kho.

Tương tự, thay cookie resolver bằng header resolver sẽ làm thay đổi hợp đồng API của client. Client phải biết đọc và gửi ID theo kênh mới. Đây là thay đổi giao thức cần được triển khai đồng bộ.

### Thay đổi repository mà không đổi client

Giả sử ứng dụng ban đầu dùng Redis:

~~~text
Browser
  |
  | Cookie: SESSION=abc
  v
CookieHttpSessionIdResolver
  |
  v
SessionRepositoryFilter
  |
  v
RedisSessionRepository
~~~

Sau này ứng dụng dùng JDBC:

~~~text
Browser
  |
  | Cookie: SESSION=abc
  v
CookieHttpSessionIdResolver
  |
  v
SessionRepositoryFilter
  |
  v
JdbcIndexedSessionRepository
~~~

Resolver vẫn đọc cookie SESSION. Chỉ repository thay đổi. Để cookie cũ tiếp tục hoạt động, dữ liệu session có ID tương ứng phải tồn tại trong repository mới và các instance cần dùng cấu hình tương thích.

### Thay đổi resolver mà không đổi repository

Một API có thể chuyển từ cookie sang header trong khi vẫn giữ Redis:

~~~text
Mobile Client
  |
  | X-Auth-Token: abc
  v
HeaderHttpSessionIdResolver
  |
  v
SessionRepositoryFilter
  |
  v
RedisSessionRepository
~~~

Dữ liệu vẫn nằm trong Redis. Client và server chỉ thay đổi cách trao đổi ID. Nếu chuyển đổi từng bước, cần có giai đoạn tương thích hoặc endpoint phiên bản mới để client cũ không bị mất phiên đột ngột.

## 7. Điều gì xảy ra khi không có ID hoặc ID không tìm thấy?

Resolver có thể không tìm thấy Session ID trong request. Một số tình huống:

| Request | Kết quả |
|---|---|
| Không có cookie/header | Không có ID để tải session |
| Có ID nhưng repository không tìm thấy | Không khôi phục được session |
| ID thuộc session đã hết hạn | Không có session hợp lệ để trả về |
| ID hợp lệ và session tồn tại | Filter cung cấp session cho ứng dụng |
| Ứng dụng gọi getSession(false) khi không có session | Trả về null |
| Ứng dụng gọi getSession() khi không có session | Tạo session mới nếu được phép |

Ví dụ:

~~~java
@GetMapping("/session/status")
public String status(HttpServletRequest request) {
    HttpSession session = request.getSession(false);

    if (session == null) {
        return "No active session";
    }

    return "Session loaded";
}
~~~

Endpoint trên chỉ kiểm tra session hiện có. Nó không tạo phiên mới khi client chưa gửi ID hợp lệ.

Không nên để một ID không tồn tại được hiểu như một session hợp lệ. Repository phải tìm được dữ liệu tương ứng. Nếu cần xác thực, ứng dụng còn phải kiểm tra trạng thái authentication và quyền truy cập.

## 8. Hỗ trợ nhiều kênh định danh: cần chính sách rõ ràng

Một số hệ thống muốn hỗ trợ cookie cho trình duyệt và header cho mobile client. Có thể tạo resolver tùy chỉnh hoặc chọn resolver theo từng ứng dụng, nhưng không nên đọc nhiều nguồn ID một cách tùy tiện.

Giả sử một request đồng thời chứa:

~~~http
Cookie: SESSION=session-A
X-Auth-Token: session-B
~~~

Nếu ứng dụng không quy định nguồn nào có ưu tiên, có thể xảy ra việc tải session khác với mong đợi của client hoặc tạo ra lỗi khó chẩn đoán.

Một chính sách dễ vận hành:

- Ứng dụng web chỉ dùng cookie resolver.
- API mobile chỉ dùng header resolver.
- Nếu một ứng dụng phải hỗ trợ cả hai, xác định rõ client type hoặc route và chọn một resolver phù hợp.
- Nếu nhiều ID xuất hiện cùng lúc, từ chối request hoặc áp dụng quy tắc ưu tiên được tài liệu hóa.
- Không đưa Session ID vào query parameter để làm nguồn thứ ba.

Không nên giả định có thể khai báo hai bean `HttpSessionIdResolver` và Spring Session sẽ tự kết hợp chúng. Một application context thường cần một resolver được chọn cho filter. Nếu muốn resolver tổng hợp, phải tự thiết kế và kiểm thử quy tắc của nó.

## 9. Tự viết resolver khi giao thức có yêu cầu riêng

Chỉ nên viết resolver tùy chỉnh khi các triển khai cookie/header có sẵn không đáp ứng được hợp đồng giao tiếp của client.

Một resolver tùy chỉnh cần thực hiện ba việc:

1. Đọc Session ID từ request theo quy tắc giao thức.
2. Trả ID về response khi session mới được tạo hoặc định danh thay đổi.
3. Gửi chỉ thị hết hạn để client xóa hoặc ngừng sử dụng ID.

Ví dụ, một API nội bộ có thể yêu cầu header tên riêng. Trước khi viết resolver mới, hãy kiểm tra liệu `HeaderHttpSessionIdResolver` đã hỗ trợ header name tùy chỉnh trong phiên bản dự án hay chưa. Nếu có, sử dụng triển khai sẵn giúp giảm mã cần bảo trì.

Khi viết custom resolver, cần xác định:

- Header name có phân biệt hoa thường hay không theo quy tắc HTTP.
- Xử lý header lặp hoặc nhiều giá trị như thế nào.
- Có trim khoảng trắng hay từ chối giá trị sai định dạng không.
- Response gửi ID mới ở header nào.
- Response logout biểu thị xóa ID như thế nào để client hiểu.
- Proxy và gateway có chuyển tiếp header đó không.
- Cách che header nhạy cảm trong log.

Resolver tùy chỉnh không nên truy cập Redis/JDBC trực tiếp. Nếu nó vừa đọc header vừa tìm session trong database, hai trách nhiệm sẽ bị trộn và việc thay repository sẽ trở nên khó khăn.

## 10. Thay ID và kết thúc phiên

Resolver cũng tham gia vào việc cập nhật định danh ở phía client.

### Thay ID sau khi đăng nhập

Sau khi người dùng xác thực thành công, ứng dụng thường cần đổi Session ID để phòng chống session fixation. Servlet API có phương thức `request.changeSessionId()`. Spring Session tích hợp với request wrapper và resolver để gửi ID mới về client.

Ví dụ minh họa:

~~~java
@PostMapping("/login/complete")
public String completeLogin(HttpServletRequest request) {
    HttpSession session = request.getSession();

    // Thực tế cần xác thực người dùng trước thao tác này.
    request.changeSessionId();

    session.setAttribute("authenticated", true);
    return "Login completed";
}
~~~

Trong ứng dụng dùng Spring Security, nên để session fixation protection của Spring Security xử lý theo cấu hình phù hợp. Không tự tạo cơ chế đổi ID chồng lấn với framework.

### Đăng xuất và expire ID

Khi logout, ứng dụng invalidate session:

~~~java
@PostMapping("/logout")
public String logout(HttpServletRequest request) {
    HttpSession session = request.getSession(false);

    if (session != null) {
        session.invalidate();
    }

    return "Logged out";
}
~~~

Filter và resolver phối hợp để xóa hoặc vô hiệu hóa định danh phía client. Với cookie, response thường gửi cookie có cùng tên/path/domain nhưng giá trị rỗng hoặc thời hạn hết hiệu lực theo cách serializer triển khai. Với header, client cần đọc response theo hợp đồng của resolver và xóa ID đã lưu.

Xóa ID phía client không thay thế việc xóa session trong repository. Ngược lại, invalidate ở server cũng nên đi kèm chỉ thị để client ngừng gửi ID cũ.

## 11. Bảo mật và vận hành

Dù ID được truyền bằng cookie hay header, Session ID vẫn là thông tin nhạy cảm.

- Dùng HTTPS trên mọi kết nối có Session ID.
- Không ghi Session ID vào access log, application log, trace hoặc analytics.
- Không truyền Session ID trong URL vì URL có thể xuất hiện trong history, referrer và log.
- Với cookie, cấu hình Secure, HttpOnly, SameSite, path và domain phù hợp.
- Với header, lưu ID trong secure storage của client và kiểm soát việc chuyển tiếp qua proxy.
- Nếu trình duyệt gửi custom header cross-origin, cấu hình CORS cho đúng origin, header và method; response header chứa ID có thể cần được expose cho JavaScript.
- Nếu dùng cookie, triển khai CSRF protection phù hợp vì trình duyệt tự động gửi cookie.
- Giới hạn quyền truy cập vào kho session và dùng TTL phù hợp.

Resolver không tự mã hóa hoặc ký Session ID. ID cần được tạo bởi Spring Session hoặc cơ chế bảo mật phù hợp, đủ ngẫu nhiên và khó đoán. Không tự tạo ID bằng timestamp, số thứ tự hoặc dữ liệu cá nhân.

Trong môi trường nhiều instance, tất cả instance cần dùng resolver tương thích. Với cookie resolver, cookie name/path/domain và serializer cần thống nhất. Với header resolver, header name và định dạng giá trị cần thống nhất. Repository, namespace và serializer dữ liệu session cũng phải tương thích.

## 12. Kiểm thử sự tách biệt giữa resolver và repository

Kiểm thử nên chứng minh hai lớp trách nhiệm có thể thay đổi độc lập.

### Kiểm thử cùng resolver với repository khác nhau

Với cùng cookie resolver:

1. Tạo session bằng repository Redis.
2. Lấy cookie từ response và gửi request tiếp theo.
3. Chạy một test khác với repository JDBC nhưng giữ cookie name và cơ chế resolver.
4. Xác minh client vẫn gửi cùng dạng cookie để tải session.
5. Nếu cần giữ nguyên ID sau migration, kiểm tra dữ liệu tương ứng đã được chuyển sang repository mới.

Test này kiểm tra tính độc lập giao thức, nhưng việc migration dữ liệu cần được kiểm tra riêng.

### Kiểm thử cùng repository với resolver khác nhau

Với cùng repository Redis:

1. Cấu hình cookie resolver và tạo session.
2. Kiểm tra request tiếp theo có thể tải phiên bằng cookie.
3. Cấu hình header resolver trong application context test khác.
4. Tạo session mới, lấy header response và gửi lại trong request tiếp theo.
5. Xác minh repository vẫn đọc/ghi dữ liệu session đúng.

Không nên dùng hai resolver cùng lúc trong một application context trừ khi custom resolver tổng hợp đã được thiết kế rõ.

### Ví dụ khung MockMvc cho header resolver

~~~java
MvcResult created = mockMvc.perform(post("/api/session/create"))
        .andExpect(status().isOk())
        .andReturn();

String sessionId =
        created.getResponse().getHeader("X-Auth-Token");

mockMvc.perform(get("/api/session/status")
        .header("X-Auth-Token", sessionId))
    .andExpect(status().isOk());
~~~

Tên header phải khớp với resolver đã cấu hình. Test đầy đủ nên xác minh response tạo ID, request sau tải được thuộc tính đã lưu, logout làm session không còn hợp lệ và response hướng dẫn client xóa ID.

## 13. Những nhầm lẫn thường gặp

**“Resolver là nơi lưu session.”**  
Resolver chỉ đọc và gửi Session ID. Repository mới lưu dữ liệu session.

**“Đổi Redis sang JDBC thì phải đổi cookie name.”**  
Không. Resolver và repository độc lập. Cookie có thể giữ nguyên nếu dữ liệu session và cấu hình tương thích.

**“Header resolver tự xác thực Bearer token.”**  
Không. Bearer resolver dùng giá trị header làm Session ID. Authentication và authorization là trách nhiệm khác.

**“Có thể khai báo nhiều resolver bean và Spring Session tự chọn theo request.”**  
Không nên giả định như vậy. Filter cần resolver được cấu hình. Muốn kết hợp nhiều nguồn cần một chính sách và custom resolver được kiểm thử rõ.

**“Session ID không tìm thấy thì request luôn bị từ chối.”**  
Resolver chỉ cung cấp ID. Nếu repository không tìm thấy session, request không có session hiện tại; ứng dụng có thể xử lý endpoint công khai hoặc tạo session mới nếu gọi getSession.

**“Xóa cookie là logout hoàn chỉnh.”**  
Cần invalidate session ở repository để ID cũ không còn dùng được, đồng thời gửi chỉ thị xóa ID về client.

## 14. Tự kiểm tra

1. `HttpSessionIdResolver` tách trách nhiệm nào khỏi `SessionRepository`?
2. Vì sao cùng một cookie resolver có thể dùng với Redis và JDBC?
3. `CookieHttpSessionIdResolver` và `HeaderHttpSessionIdResolver` khác nhau ở đâu?
4. Khi dùng header resolver, client cần làm gì sau khi response tạo session?
5. Vì sao resolver không phải cơ chế xác thực?
6. Nếu request gửi cả cookie ID A và header ID B, ứng dụng cần làm gì?
7. Vì sao không nên đưa Session ID vào URL?
8. Khi logout, vì sao cần vừa invalidate session ở server vừa yêu cầu client xóa ID?
9. Khi nào nên viết custom resolver?
10. Cần kiểm thử gì để chứng minh resolver và repository độc lập?

### Gợi ý trả lời

1. Resolver xử lý cách đọc/gửi ID qua HTTP; repository xử lý dữ liệu session theo ID.
2. Vì repository không phụ thuộc ID được gửi bằng cookie hay header.
3. Cookie resolver đọc và gửi cookie; header resolver đọc và gửi HTTP header.
4. Đọc response header, lưu ID an toàn và gửi lại trong các request tiếp theo.
5. Resolver chỉ nhận diện session; ứng dụng vẫn phải xác thực và kiểm tra quyền.
6. Quy định rõ nguồn ưu tiên hoặc từ chối request có ID xung đột.
7. URL dễ xuất hiện trong browser history, referrer và access log.
8. Invalidate làm session phía server không còn hợp lệ; expire ID giúp client ngừng gửi định danh cũ.
9. Khi hợp đồng giao thức riêng không được resolver có sẵn đáp ứng.
10. Giữ nguyên resolver khi thay repository, và giữ nguyên repository khi thay resolver trong các test context riêng.

## Kết luận

`HttpSessionIdResolver` tách cơ chế truyền Session ID khỏi nơi lưu dữ liệu session. Trong ứng dụng Servlet, `SessionRepositoryFilter` dùng resolver để đọc ID từ request và gửi ID hoặc chỉ thị hết hạn trong response; `SessionRepository` thực hiện việc tạo, tìm, lưu và xóa phiên.

Cookie resolver phù hợp với trình duyệt, còn header resolver phù hợp với client chủ động quản lý request. Cùng một resolver có thể dùng với Redis hoặc JDBC, và cùng một repository có thể được truy cập bằng các resolver khác nhau trong những ứng dụng được cấu hình riêng. Giữ hai trách nhiệm độc lập giúp thay đổi hạ tầng và giao thức dễ kiểm soát, đồng thời cần bảo vệ Session ID, thống nhất cấu hình giữa các instance và kiểm thử đầy đủ các luồng tạo, tải, đổi ID và logout.

