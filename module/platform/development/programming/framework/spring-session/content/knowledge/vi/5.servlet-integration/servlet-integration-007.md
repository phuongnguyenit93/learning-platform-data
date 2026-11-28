# Tải phiên từ định danh được gửi trong yêu cầu

## Mục tiêu bài học

Trong ứng dụng Servlet dùng Spring Session, mỗi request cần cung cấp một cách để máy chủ nhận ra phiên làm việc tương ứng. Thông tin này thường được gửi bằng cookie, nhưng một số client API có thể gửi Session ID qua HTTP header. Thành phần chọn cách đọc và trả Session ID được gọi là bộ phân giải định danh phiên (session ID resolver).

Sau bài học, bạn có thể:

- Mô tả cách Spring Session tìm Session ID trong một HTTP request.
- Hiểu vai trò của `SessionRepositoryFilter` và `HttpSessionIdResolver`.
- Phân biệt cách truyền Session ID qua cookie và header.
- Cấu hình `CookieHttpSessionIdResolver`, `HeaderHttpSessionIdResolver` và cookie serializer.
- Hiểu điều gì xảy ra khi request không có ID, có ID không hợp lệ hoặc phiên đã hết hạn.
- Thiết kế cách truyền Session ID an toàn cho trình duyệt, mobile app và API client.
- Kiểm thử việc tải, tiếp tục, thay ID và kết thúc session qua nhiều request.

## 1. Vì sao request cần gửi Session ID?

HTTP xử lý từng request riêng biệt. Khi ứng dụng cần giữ trạng thái giữa nhiều request, máy chủ phải có cách xác định request hiện tại thuộc phiên nào.

Ví dụ, một người dùng thêm sản phẩm vào giỏ hàng rồi mở trang giỏ hàng. Request thêm sản phẩm tạo hoặc cập nhật dữ liệu phiên. Request đọc giỏ hàng cần mang theo một định danh để máy chủ tìm lại đúng dữ liệu đó.

Trong mô hình server-side session, trình duyệt thường chỉ gửi một chuỗi định danh, còn dữ liệu phiên được lưu tại repository như Redis hoặc JDBC.

~~~text
Request 1                              Request 2
POST /cart/items                       GET /cart
Cookie: SESSION=opaque-id              Cookie: SESSION=opaque-id
       |                                      |
       v                                      v
Spring Session                         Spring Session
       |                                      |
       +--------------+  +--------------------+
                      v  v
                Session Repository
                 SESSION -> data
~~~

Session ID là chìa khóa tra cứu, không phải bản thân dữ liệu session. Máy chủ nhận ID, tra cứu repository và khôi phục ngữ cảnh tương ứng trước khi chuyển request vào controller.

Nếu request không có Session ID, ứng dụng vẫn có thể xử lý endpoint stateless. Chỉ khi mã ứng dụng hoặc framework yêu cầu tạo session, một session mới mới được tạo. Nếu request gửi một ID không tồn tại hoặc phiên đã hết hạn, máy chủ không nên xem ID đó là bằng chứng cho một phiên hợp lệ.

## 2. Luồng tải session trong Spring Session Servlet

Spring Session tích hợp với Servlet thông qua `SessionRepositoryFilter`. Filter này bọc request và response để các thành phần ứng dụng tiếp tục sử dụng API Servlet như `HttpSession`, trong khi việc đọc và lưu phiên được chuyển đến `SessionRepository`.

Luồng khái quát:

1. Trình duyệt hoặc client gửi request có cookie hoặc header chứa Session ID.
2. `SessionRepositoryFilter` gọi `HttpSessionIdResolver` để lấy một hoặc nhiều ID ứng viên từ request.
3. Filter yêu cầu repository tìm session tương ứng với từng ID.
4. Nếu tìm thấy, session được gắn vào request wrapper để ứng dụng truy cập qua `request.getSession(false)` hoặc `request.getSession()`.
5. Nếu không tìm thấy session, `getSession(false)` trả về `null`. Nếu ứng dụng gọi `getSession()`, một session mới có thể được tạo.
6. Khi session mới được tạo, resolver ghi Session ID vào response bằng cookie hoặc header.
7. Khi session bị invalidate, resolver có thể phát hành chỉ thị xóa định danh ở client.

Sơ đồ sequence:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as SessionRepositoryFilter
    participant I as HttpSessionIdResolver
    participant R as SessionRepository
    participant A as Servlet Application

    C->>F: HTTP request + cookie/header
    F->>I: resolveSessionIds(request)
    I-->>F: Danh sách Session ID
    F->>R: findById(id)
    R-->>F: Session hoặc không tìm thấy
    F->>A: Wrapped request / HttpSession
    A->>A: Đọc hoặc cập nhật thuộc tính
    A-->>F: Kết thúc xử lý
    F->>R: Lưu hoặc xóa session
    F->>I: setSessionId / expireSession
    I-->>C: Cookie hoặc response header
~~~

Tên API trong sơ đồ mô tả trách nhiệm chính của các thành phần. Chi tiết thời điểm lưu phụ thuộc repository và cấu hình flush/save của Spring Session.

### Hai trường hợp truy cập Servlet thường gặp

`request.getSession(false)` chỉ trả về session hiện có; nếu request không mang ID hợp lệ hoặc repository không tìm thấy phiên, kết quả là `null`. Cách này hữu ích khi chỉ muốn kiểm tra session mà không tạo mới.

`request.getSession()` trả về session hiện có hoặc tạo session mới nếu chưa có. Nếu endpoint gọi phương thức này trong mọi request, kể cả endpoint không cần trạng thái, ứng dụng có thể tạo nhiều session không cần thiết và gửi thêm cookie.

Ví dụ:

~~~java
@GetMapping("/profile/session-status")
public String sessionStatus(HttpServletRequest request) {
    HttpSession session = request.getSession(false);

    if (session == null) {
        return "No active session";
    }

    return "Session is available";
}
~~~

Endpoint trên không tạo phiên mới chỉ để kiểm tra trạng thái. Đây là một lựa chọn phù hợp cho endpoint chỉ cần quan sát phiên hiện có, tùy chính sách của ứng dụng.

## 3. HttpSessionIdResolver là gì?

`HttpSessionIdResolver` là abstraction xác định cách đọc Session ID từ request và cách gửi hoặc xóa ID trong response.

Các thao tác cốt lõi gồm:

| Phương thức | Trách nhiệm |
|---|---|
| `resolveSessionIds(request)` | Đọc danh sách Session ID từ request |
| `setSessionId(request, response, sessionId)` | Gửi định danh phiên về client khi cần |
| `expireSession(request, response)` | Yêu cầu client xóa định danh phiên |

Nhờ abstraction này, logic nghiệp vụ không cần tự đọc header hay phân tích cookie. Ứng dụng tiếp tục dùng `HttpSession`, còn resolver chịu trách nhiệm trao đổi định danh.

Spring Session có các triển khai phổ biến:

- `CookieHttpSessionIdResolver`: lấy ID từ cookie và gửi ID bằng cookie trong response.
- `HeaderHttpSessionIdResolver`: lấy ID từ HTTP header và gửi ID trong response header.
- Resolver tùy chỉnh: dùng khi giao thức client có yêu cầu riêng và có lý do rõ ràng để thay đổi cơ chế mặc định.

Trong cấu hình Servlet thông thường, Spring Session dùng cookie resolver theo mặc định. Cookie mặc định thường có tên `SESSION`, có thể thay đổi bằng cookie serializer. Tên cookie của Servlet container mặc định như `JSESSIONID` không nên được giả định là tên cookie của Spring Session.

### Resolver không phải repository

Hai thành phần này có trách nhiệm khác nhau:

- Resolver biết **client gửi ID ở đâu** và **response trả ID bằng cách nào**.
- Repository biết **ID tương ứng với dữ liệu session nào** và cách đọc/ghi dữ liệu đó trong Redis, JDBC hoặc kho khác.

Ví dụ, thay cookie resolver bằng header resolver không làm dữ liệu session chuyển từ Redis sang JDBC. Repository vẫn giữ nguyên; chỉ phương tiện truyền Session ID thay đổi.

## 4. Tải session từ cookie

Cookie là lựa chọn phổ biến cho trình duyệt. Máy chủ gửi header `Set-Cookie`, trình duyệt lưu cookie và tự động gửi lại trong các request phù hợp với domain, path, thời hạn và chính sách bảo mật.

Ví dụ response khi tạo session:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=opaque-session-id; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

Request sau gửi lại cookie:

~~~http
GET /cart HTTP/1.1
Host: shop.example
Cookie: SESSION=opaque-session-id
~~~

Spring Session đọc cookie thông qua `CookieHttpSessionIdResolver`, sau đó dùng ID để tìm session trong repository.

Cookie có ưu điểm là trình duyệt tự quản lý việc gửi lại định danh. Ứng dụng web không cần tự thêm Session ID vào từng request bằng JavaScript. Tuy nhiên, vì trình duyệt tự động gửi cookie, ứng dụng phải quan tâm đến CSRF và các thuộc tính cookie.

### Cấu hình cookie serializer

`CookieHttpSessionIdResolver` sử dụng một `CookieSerializer` để quyết định chi tiết cookie. Có thể tùy chỉnh bằng `DefaultCookieSerializer`.

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class SessionCookieConfig {

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

Một số lựa chọn cần cân nhắc:

| Thuộc tính | Ý nghĩa và quyết định |
|---|---|
| Cookie name | Tên cookie chứa Session ID; chọn tên ổn định, tránh trùng cookie khác |
| Path | Phạm vi đường dẫn mà trình duyệt gửi cookie |
| Domain | Phạm vi host; chỉ đặt domain rộng khi thực sự cần chia sẻ giữa subdomain |
| HttpOnly | Ngăn JavaScript đọc cookie bằng API cookie thông thường |
| Secure | Chỉ gửi cookie qua HTTPS |
| SameSite | Điều chỉnh gửi cookie trong ngữ cảnh cross-site |
| Max-Age | Thời gian cookie được giữ ở trình duyệt; độc lập với TTL phía server |

Ví dụ trên bật `Secure`, phù hợp với môi trường HTTPS production. Trong môi trường local chỉ chạy HTTP, cookie Secure có thể không được gửi như mong đợi. Nên dùng profile cấu hình riêng cho local và production, đồng thời bảo đảm production luôn sử dụng HTTPS.

Không nên đặt `Domain` thành domain cha rộng hơn mức cần thiết. Cookie được chia sẻ quá rộng có thể làm tăng phạm vi các subdomain có thể nhận định danh phiên.

### Cookie expiration và session timeout khác nhau

Cookie có `Max-Age` hoặc `Expires` quyết định trình duyệt giữ cookie trong bao lâu. Session timeout quyết định repository giữ dữ liệu phiên trong bao lâu, hoặc bao lâu không có hoạt động trước khi phiên hết hạn.

Hai thời hạn này có thể khác nhau:

- Cookie còn tồn tại nhưng session đã hết hạn ở Redis/JDBC: client gửi ID cũ, repository không tìm thấy phiên.
- Session vẫn còn ở repository nhưng cookie đã bị xóa khỏi trình duyệt: trình duyệt không còn ID để truy cập phiên đó.
- Trình duyệt đóng và xóa session cookie: dữ liệu phía server có thể vẫn tồn tại đến khi TTL hoặc cơ chế dọn dẹp xóa nó.

Do đó, không dùng Max-Age của cookie để thay thế chính sách timeout ở server.

## 5. Tải session từ HTTP header

Một số client không phải trình duyệt, chẳng hạn mobile application hoặc thiết bị tích hợp, muốn tự quản lý Session ID. Khi đó có thể truyền ID qua HTTP header.

`HeaderHttpSessionIdResolver` là triển khai dùng header. Spring Session cung cấp các factory method phổ biến:

- `HeaderHttpSessionIdResolver.xAuthToken()`: dùng header `X-Auth-Token`.
- `HeaderHttpSessionIdResolver.bearerAuth()`: dùng header `Authorization` với định dạng Bearer.

Ví dụ chọn `X-Auth-Token`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.HeaderHttpSessionIdResolver;
import org.springframework.session.web.http.HttpSessionIdResolver;

@Configuration
public class SessionIdResolverConfig {

    @Bean
    public HttpSessionIdResolver httpSessionIdResolver() {
        return HeaderHttpSessionIdResolver.xAuthToken();
    }
}
~~~

Client gửi request:

~~~http
GET /api/cart HTTP/1.1
Host: api.example
X-Auth-Token: opaque-session-id
~~~

Khi cần tạo session mới, resolver có thể trả Session ID trong response header tương ứng. Client phải đọc header phản hồi, lưu ID một cách an toàn và gửi lại trong request tiếp theo.

Nếu dùng Bearer resolver, request có dạng:

~~~http
GET /api/cart HTTP/1.1
Host: api.example
Authorization: Bearer opaque-session-id
~~~

Cần hiểu rõ ý nghĩa: với resolver này, chuỗi Bearer đang được dùng như Session ID của Spring Session. Nó không tự biến thành OAuth access token hoặc JWT. Ứng dụng phải phân biệt session ID với token xác thực do hệ thống khác phát hành.

### Khi nào chọn header resolver?

Header resolver phù hợp với client chủ động quản lý request, ví dụ:

- Mobile app lưu Session ID trong vùng lưu trữ an toàn của hệ điều hành.
- Service-to-service client có cơ chế quản lý credential riêng.
- API client cần gửi định danh phiên trong header theo hợp đồng API.

Header resolver không tự xác thực người dùng. Việc tìm thấy session chỉ cho biết repository có dữ liệu phiên tương ứng; authorization và kiểm tra quyền vẫn cần được thực hiện ở tầng bảo mật ứng dụng.

### Cookie resolver và header resolver là hai lựa chọn giao thức

Một ứng dụng nên xác định rõ client gửi Session ID bằng cách nào. Nếu chấp nhận nhiều nguồn ID, phải quy định thứ tự ưu tiên và xử lý trường hợp request gửi các ID mâu thuẫn. Việc dùng đồng thời cookie, header và query parameter mà không có quy tắc rõ ràng có thể tạo ra hành vi khó dự đoán.

Đối với một API chỉ dành cho mobile client, có thể chọn header resolver. Đối với ứng dụng web dùng trình duyệt, cookie resolver thường thuận tiện hơn và phù hợp với cách trình duyệt quản lý cookie.

## 6. Điều gì xảy ra khi request thiếu ID hoặc ID không hợp lệ?

Một request có thể rơi vào một trong các trường hợp sau:

| Trạng thái request | Kết quả tải session |
|---|---|
| Không có cookie/header chứa ID | Không có session hiện tại |
| Có ID nhưng repository không tìm thấy | Không khôi phục được session |
| Session đã hết hạn | ID không còn trỏ đến session hợp lệ |
| ID hợp lệ và session tồn tại | Khôi phục session tương ứng |
| Ứng dụng gọi getSession khi không có session | Tạo session mới theo cấu hình |
| Ứng dụng gọi getSession(false) khi không có session | Trả về null |

Không nên xem việc client gửi một chuỗi có hình dạng giống Session ID là đủ để tin cậy nó. Repository phải tìm thấy session tương ứng. ID ngẫu nhiên, khó đoán và được bảo vệ là điều kiện quan trọng để giảm nguy cơ chiếm quyền phiên.

### Request mang ID cũ

Ví dụ người dùng đã đăng xuất, nhưng trình duyệt vẫn gửi cookie cũ do cookie chưa được xóa hoặc response xóa cookie không được nhận. Repository không còn session tương ứng nên request không khôi phục được phiên đã đăng xuất.

Nếu endpoint sau đó gọi `getSession()`, ứng dụng có thể tạo một session mới và gửi ID mới. Điều này không có nghĩa phiên cũ được khôi phục.

### Request có nhiều ID

Interface resolver cho phép trả về danh sách ID. Một resolver tùy chỉnh có thể hỗ trợ nhiều nguồn hoặc nhiều ID ứng viên, nhưng cần xác định hành vi rõ ràng khi có nhiều giá trị. Nếu request đồng thời gửi cookie ID A và header ID B, không nên để kết quả phụ thuộc vào thứ tự không được tài liệu hóa.

Một chính sách an toàn, dễ hiểu thường là chỉ chấp nhận một kênh định danh cho một loại client. Nếu bắt buộc hỗ trợ nhiều kênh, hãy xác định thứ tự ưu tiên, từ chối xung đột hoặc ghi nhận sự kiện chẩn đoán mà không log giá trị bí mật.

## 7. Tạo, thay đổi và xóa Session ID

Resolver không chỉ đọc ID. Nó còn phối hợp với filter để gửi ID mới khi session được tạo và xóa dấu vết ID khi session bị hủy.

### Tạo session mới

Khi request chưa có session và ứng dụng gọi `getSession()`, Spring Session tạo session qua repository. Khi lưu session, resolver gửi ID mới về client:

- Cookie resolver gửi `Set-Cookie`.
- Header resolver gửi ID trong response header được cấu hình.

Client phải giữ ID mới để sử dụng ở request sau.

### Thay đổi Session ID

Sau khi xác thực thành công, ứng dụng thường cần thay Session ID để phòng chống session fixation. Servlet API có phương thức `request.changeSessionId()` trên các container hỗ trợ Servlet tương ứng. Spring Session tích hợp với request wrapper để cập nhật định danh và resolver gửi ID mới về client.

Ví dụ:

~~~java
@PostMapping("/login/complete")
public String completeLogin(HttpServletRequest request) {
    HttpSession session = request.getSession();

    // Sau khi xác thực thành công, đổi ID để chống session fixation.
    request.changeSessionId();

    session.setAttribute("authenticated", true);
    return "Login completed";
}
~~~

Ví dụ chỉ minh họa thời điểm đổi ID. Trong ứng dụng thật, việc xác thực phải được thực hiện bởi Spring Security hoặc cơ chế xác thực đáng tin cậy; không đặt thuộc tính authenticated chỉ dựa trên input client.

Nếu dùng Spring Security, hãy để session fixation protection của framework thực hiện theo cấu hình phù hợp. Tránh đổi ID thủ công chồng lấn với chiến lược đã được cấu hình.

### Hủy session

Khi đăng xuất, ứng dụng hủy session hiện tại:

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

Sau khi session bị invalidate, resolver được dùng để yêu cầu client xóa cookie hoặc header ID theo giao thức. Với header-based client, ứng dụng cần bảo đảm client xử lý response và xóa ID đã lưu ở phía client.

Không nên chỉ xóa cookie mà bỏ qua việc invalidate session phía server. Nếu repository vẫn giữ phiên hợp lệ, người có bản sao Session ID có thể tiếp tục sử dụng nó.

## 8. Bảo mật khi nhận Session ID từ request

Session ID là một bí mật dạng bearer: ai có được ID và gửi lại đúng cách có thể có khả năng tiếp tục phiên. Bảo vệ kênh truyền và nơi lưu ID là yêu cầu bắt buộc.

### Với cookie

- Bật `Secure` để chỉ gửi cookie qua HTTPS.
- Bật `HttpOnly` để JavaScript không đọc cookie qua API thông thường.
- Chọn `SameSite` phù hợp với luồng điều hướng và tích hợp cross-site.
- Dùng path và domain hẹp nhất đáp ứng yêu cầu.
- Bảo vệ request thay đổi trạng thái bằng CSRF token hoặc cơ chế phòng vệ phù hợp.
- Không đưa Session ID vào URL hoặc log.

Cookie tự động được trình duyệt gửi kèm request, vì vậy ứng dụng dùng cookie session cần đánh giá CSRF. `SameSite` hỗ trợ giảm rủi ro trong một số tình huống nhưng không thay thế mọi biện pháp CSRF.

### Với header

- Luôn truyền qua HTTPS.
- Không ghi header chứa Session ID vào access log, trace hoặc telemetry công khai.
- Lưu Session ID trong secure storage của client khi có thể.
- Không nhúng ID vào query string để thay thế header.
- Kiểm tra chính sách CORS nếu client chạy trong trình duyệt ở origin khác.
- Hạn chế quyền truy cập vào header ở proxy, gateway và hệ thống quan sát.

Custom header thường khiến trình duyệt thực hiện CORS preflight trong request cross-origin. Cấu hình CORS phải cho phép đúng origin, method và header cần thiết. Không bật wildcard credentials một cách tùy tiện.

### Session ID không phải quyền truy cập

Một session hợp lệ không có nghĩa người dùng được quyền đọc mọi tài nguyên. Ứng dụng vẫn cần xác minh danh tính, kiểm tra quyền, kiểm tra tenant và quyền sở hữu dữ liệu trên từng request. Session chỉ cung cấp ngữ cảnh để framework hoặc ứng dụng tìm lại trạng thái xác thực và các thuộc tính liên quan.

## 9. Filter order và proxy trong môi trường triển khai

`SessionRepositoryFilter` cần chạy trước những filter hoặc thành phần khác có thể truy cập `HttpSession`. Nếu một filter tùy chỉnh đọc session trước khi Spring Session bọc request, thành phần đó có thể tương tác với session của Servlet container thay vì repository Spring Session.

Khi dùng Spring Boot auto-configuration, framework thường đăng ký filter theo thứ tự phù hợp. Nếu tự đăng ký filter hoặc thay đổi thứ tự filter, cần kiểm tra thứ tự thực tế trong Servlet filter chain.

Trong hệ thống có reverse proxy hoặc API gateway, cần kiểm tra:

- Proxy có chuyển tiếp header Session ID hay không.
- Header có bị đổi chữ hoa/thường, loại bỏ hoặc ghi đè không.
- Cookie có được giữ nguyên qua domain/path mapping không.
- TLS được kết thúc ở proxy hay tại application server.
- Log của proxy có vô tình ghi cookie hoặc header bí mật không.

Nếu TLS kết thúc tại load balancer, ứng dụng cần cấu hình forwarded headers và secure cookie phù hợp với topology. Không nên tắt Secure cookie chỉ để xử lý cấu hình proxy chưa chính xác.

## 10. Kiểm thử tải session qua định danh request

Kiểm thử nên xác minh cả request và response. Một test chỉ kiểm tra controller trả về HTTP 200 chưa đủ chứng minh session đã được tải đúng.

### Kiểm thử bằng cookie

Quy trình:

1. Gửi request đầu tiên tạo session.
2. Lấy cookie Session ID trong response.
3. Gửi request tiếp theo với cookie đó.
4. Xác minh thuộc tính đã lưu trong request trước.
5. Invalidate session.
6. Gửi lại ID cũ và xác minh phiên không còn được khôi phục.

Ví dụ khung MockMvc:

~~~java
MvcResult createResult = mockMvc.perform(post("/cart/items"))
        .andExpect(status().isOk())
        .andReturn();

Cookie sessionCookie =
        createResult.getResponse().getCookie("SESSION");

mockMvc.perform(get("/cart")
        .cookie(sessionCookie))
    .andExpect(status().isOk());
~~~

Tên cookie cần khớp với cấu hình serializer của ứng dụng. Trong test, nên lấy cookie từ response thay vì tự đoán giá trị Session ID.

### Kiểm thử bằng header

Khi cấu hình `HeaderHttpSessionIdResolver.xAuthToken()`, test cần:

1. Gửi request tạo session.
2. Lấy header `X-Auth-Token` trong response.
3. Gửi lại giá trị header trong request tiếp theo.
4. Xác minh session được khôi phục.
5. Hủy session và xác minh resolver trả chỉ thị hết hạn hoặc client không còn dùng ID cũ.

Ví dụ khung:

~~~java
MvcResult createResult = mockMvc.perform(post("/api/cart/items"))
        .andExpect(status().isOk())
        .andReturn();

String sessionId =
        createResult.getResponse().getHeader("X-Auth-Token");

mockMvc.perform(get("/api/cart")
        .header("X-Auth-Token", sessionId))
    .andExpect(status().isOk());
~~~

Tên header phải khớp resolver đã cấu hình. Không sử dụng header này đồng thời với cookie resolver trong cùng test nếu mục tiêu là kiểm tra riêng từng giao thức.

### Kiểm thử session qua hai instance

Để xác minh định danh được gửi trong request tải được cùng session ở nhiều instance:

1. Gửi request tạo session đến instance A.
2. Lấy cookie hoặc header chứa ID.
3. Gửi request đến instance B với cùng ID.
4. Xác minh B đọc được thuộc tính do A ghi.
5. Hủy session ở một instance.
6. Gửi lại ID cũ đến instance còn lại và xác minh repository không còn trả session đó.

Test này cần hai application instance dùng cùng repository và cùng cấu hình resolver. Nếu mỗi instance có cookie name, namespace hoặc serializer khác nhau, kết quả có thể thất bại dù Redis/JDBC vẫn hoạt động.

## 11. Ví dụ cấu hình resolver cho Servlet

Ví dụ dưới đây minh họa chọn cookie resolver mặc định và tùy chỉnh cookie serializer. Khi dùng Spring Boot auto-configuration, bean serializer có thể được dùng để cấu hình cookie của Spring Session.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class ServletSessionConfiguration {

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

Nếu muốn dùng header resolver, khai báo resolver bean thay vì dựa vào cookie resolver mặc định:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.HeaderHttpSessionIdResolver;
import org.springframework.session.web.http.HttpSessionIdResolver;

@Configuration
public class ApiSessionConfiguration {

    @Bean
    public HttpSessionIdResolver httpSessionIdResolver() {
        return HeaderHttpSessionIdResolver.xAuthToken();
    }
}
~~~

Hai cấu hình trên minh họa hai lựa chọn giao thức. Không đăng ký cả hai class cấu hình cùng lúc nếu ứng dụng không có chính sách xử lý nhiều nguồn ID được thiết kế và kiểm thử rõ ràng.

## 12. Những lỗi thường gặp

**Request có cookie nhưng controller không thấy session.**  
Kiểm tra cookie có đúng tên, domain, path và môi trường HTTPS không. Kiểm tra resolver, filter order, repository và TTL.

**Session ID được gửi trong header nhưng server vẫn tạo session mới.**  
Kiểm tra header name và resolver bean đã được đăng ký đúng chưa. Xác minh proxy/gateway có chuyển tiếp header không và client có gửi đúng ID không.

**Cookie bị mất khi gọi API khác domain.**  
Kiểm tra SameSite, Secure, domain, path, CORS và tùy chọn gửi credentials của client. Cross-site cookie thường cần cấu hình riêng và HTTPS.

**Đăng xuất nhưng request sau vẫn dùng được session.**  
Kiểm tra ứng dụng đã invalidate session ở repository chưa, response đã xóa định danh client chưa và có nhiều repository hoặc instance dùng namespace khác nhau không.

**Dùng getSession trong endpoint chỉ đọc trạng thái.**  
Điều này có thể tạo session mới ngoài ý muốn. Nếu chỉ kiểm tra phiên hiện tại, dùng getSession(false).

**Header resolver bị hiểu nhầm là xác thực token.**  
Resolver chỉ chuyển Session ID giữa client và server. Xác thực và phân quyền vẫn phải được cấu hình riêng.

**Session ID xuất hiện trong log.**  
Cấu hình redaction cho cookie và header nhạy cảm ở ứng dụng, proxy, gateway, tracing và hệ thống giám sát.

## 13. Tự kiểm tra

1. Thành phần nào đọc Session ID từ request trong Spring Session Servlet?
2. `HttpSessionIdResolver` có những trách nhiệm chính nào?
3. Vì sao cookie resolver phù hợp với trình duyệt?
4. Khi dùng header resolver, client cần làm gì sau khi nhận response tạo session?
5. `getSession(false)` khác `getSession()` như thế nào khi request không có ID hợp lệ?
6. Vì sao không nên đưa Session ID vào query string hoặc URL?
7. Session timeout ở repository khác Max-Age của cookie ở điểm nào?
8. Vì sao một session hợp lệ không tự chứng minh người dùng có quyền truy cập tài nguyên?
9. Khi nào cần kiểm tra thứ tự `SessionRepositoryFilter` trong filter chain?
10. Cần xác minh những gì khi session được tạo ở instance A và tải ở instance B?

### Gợi ý trả lời

1. `SessionRepositoryFilter` gọi resolver để đọc ID, sau đó dùng repository tìm session.
2. Đọc ID từ request, gửi ID mới trong response và yêu cầu client xóa ID khi phiên kết thúc.
3. Trình duyệt tự lưu và gửi cookie theo domain, path và chính sách cookie.
4. Client đọc header phản hồi, lưu Session ID an toàn và gửi lại trong request tiếp theo.
5. `getSession(false)` trả `null` nếu không có session; `getSession()` có thể tạo session mới.
6. URL dễ xuất hiện trong browser history, access log, referrer và telemetry.
7. Max-Age điều khiển thời hạn cookie phía client; session timeout điều khiển vòng đời dữ liệu phiên phía server.
8. Session chỉ là ngữ cảnh; authorization vẫn phải kiểm tra ở phía server.
9. Khi filter tùy chỉnh hoặc thành phần khác có thể truy cập session trước Spring Session.
10. Cùng repository, resolver, cookie/header, namespace và serializer; sau đó xác minh thuộc tính đọc được ở instance B.

## Kết luận

Trong ứng dụng Servlet, Spring Session tải phiên bằng cách đọc Session ID từ request thông qua `HttpSessionIdResolver`. `SessionRepositoryFilter` phối hợp với resolver và repository để khôi phục `HttpSession` trước khi ứng dụng xử lý request. Cookie là lựa chọn mặc định phổ biến cho trình duyệt; header resolver phù hợp với client chủ động quản lý định danh.

Việc chọn kênh truyền cần nhất quán giữa các client và instance. Cookie phải có thuộc tính bảo mật và cơ chế CSRF phù hợp; header phải được bảo vệ qua HTTPS và không xuất hiện trong log. Khi tạo, thay đổi hoặc hủy session, resolver phải cập nhật định danh ở response để client tiếp tục sử dụng đúng phiên. Kiểm thử cần giữ cùng cookie hoặc header qua nhiều request và xác minh cả tình huống nhiều instance dùng chung repository.

