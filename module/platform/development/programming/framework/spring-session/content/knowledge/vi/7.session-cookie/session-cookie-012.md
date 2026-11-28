# Tùy chỉnh cookie của WebFlux qua WebSessionIdResolver riêng

Spring Session hỗ trợ quản lý phiên cho ứng dụng Servlet và ứng dụng reactive dùng Spring WebFlux. Với WebFlux, trạng thái phiên được biểu diễn bằng `WebSession`; cơ chế chuyển session ID giữa trình duyệt và máy chủ do `WebSessionIdResolver` đảm nhiệm.

Khi dùng cookie mặc định, ứng dụng có thể cần đổi tên cookie, đường dẫn, thuộc tính bảo mật hoặc chính sách hết hạn. Nếu yêu cầu phức tạp hơn, có thể cung cấp một resolver riêng để tự định nghĩa cách đọc session ID từ request, gửi ID về client và xóa cookie khi phiên kết thúc.

Resolver chỉ vận chuyển session ID. Nó không lưu dữ liệu phiên, không thay thế repository và không tự xác thực người dùng. Spring Session vẫn cần một reactive session repository phù hợp để lưu `WebSession` ở phía máy chủ.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt `WebSession` của WebFlux với `HttpSession` của Servlet.
- Giải thích vai trò của `WebSessionIdResolver` trong vòng đời phiên.
- Cấu hình `CookieWebSessionIdResolver` để tùy chỉnh cookie.
- Viết resolver riêng để đọc, phát hành và hết hạn cookie session.
- Chọn thuộc tính `HttpOnly`, `Secure`, `SameSite`, `Path`, `Domain` và `Max-Age` phù hợp.
- Kiểm thử cookie trong request/response và khi chạy nhiều instance.

## 1. WebSession và WebSessionIdResolver

Trong ứng dụng Servlet, Spring Session tích hợp qua `HttpSession` và `SessionRepositoryFilter`. Trong ứng dụng WebFlux, API phiên là `WebSession`; request được xử lý theo mô hình reactive và repository phải hỗ trợ `ReactiveSessionRepository`.

Resolver cookie không quyết định loại repository. Hãy chọn repository tương thích với WebFlux và mô hình reactive. Repository JDBC tiêu chuẩn của Spring Session dành cho Servlet là API đồng bộ, không thể thay trực tiếp cho `ReactiveSessionRepository`; nếu hệ thống bắt buộc dùng JDBC, cần một tích hợp reactive phù hợp và phải đánh giá việc truy cập JDBC blocking.

`WebSessionIdResolver` là một SPI có ba trách nhiệm:

| Phương thức | Trách nhiệm |
|---|---|
| `resolveSessionIds(ServerWebExchange exchange)` | Đọc session ID từ request và trả về danh sách ID tìm được |
| `setSessionId(ServerWebExchange exchange, String id)` | Ghi session ID vào response khi phiên cần được nhận diện ở request tiếp theo |
| `expireSession(ServerWebExchange exchange)` | Gửi chỉ thị để client loại bỏ session ID, thường bằng cách hết hạn cookie |

Resolver không tạo phiên trong repository. Khi WebFlux cần một phiên, thành phần quản lý phiên sử dụng resolver để tìm ID trong request, sau đó truy cập repository để tải phiên. Nếu không có phiên phù hợp và nghiệp vụ cần phiên mới, Spring Session tạo `WebSession` và resolver phát session ID ra response.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant W as WebFlux
    participant I as WebSessionIdResolver
    participant R as Reactive Session Repository
    B->>W: Request kèm cookie session
    W->>I: resolveSessionIds(exchange)
    I-->>W: Danh sách session ID
    W->>R: Tìm phiên theo ID
    R-->>W: WebSession hoặc không tìm thấy
    W->>W: Xử lý handler reactive
    alt Phiên mới hoặc cần phát ID
        W->>I: setSessionId(exchange, id)
        I-->>B: Response có Set-Cookie
    else Phiên bị kết thúc
        W->>I: expireSession(exchange)
        I-->>B: Response xóa cookie
    end
~~~

`ServerWebExchange` là ngữ cảnh chứa request và response của WebFlux. Resolver đọc cookie từ request và thêm cookie vào response thông qua exchange. Không dùng `HttpServletRequest`, `HttpServletResponse` hoặc `HttpSession` trong resolver WebFlux.

## 2. Dùng CookieWebSessionIdResolver có sẵn

Trong phần lớn ứng dụng, `CookieWebSessionIdResolver` đã đáp ứng nhu cầu. Cung cấp một bean `WebSessionIdResolver` để thay đổi tên cookie và các thuộc tính:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
public class WebSessionCookieConfiguration {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();

        resolver.setCookieName("APPSESSION");
        resolver.addCookieInitializer(cookie -> cookie
                .path("/")
                .httpOnly(true)
                .secure(true)
                .sameSite("Lax"));

        return resolver;
    }
}
~~~

Cookie trong ví dụ có tên `APPSESSION`, được gửi cho các đường dẫn dưới `/`, không cho JavaScript đọc, chỉ được gửi qua HTTPS và dùng chính sách SameSite Lax. Có thể điều chỉnh tên và thuộc tính theo domain, kiến trúc frontend và yêu cầu xác thực.

`addCookieInitializer` áp dụng thuộc tính lên cookie builder mà resolver sử dụng. Nếu chỉ cần đổi tên cookie hoặc thêm vài thuộc tính chuẩn, hãy ưu tiên resolver có sẵn vì nó đã xử lý việc đọc ID, phát ID và xóa cookie theo hợp đồng Spring Session.

Nếu cần cookie có thời hạn lưu ở trình duyệt, có thể cấu hình `Max-Age` thông qua cookie initializer, tùy phiên bản Spring Framework/Spring Session:

~~~java
resolver.addCookieInitializer(cookie -> cookie
        .path("/")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .maxAge(Duration.ofHours(2)));
~~~

Đoạn cấu hình minh họa cookie có thời hạn hai giờ. Cần import `java.time.Duration` và xác minh API builder trong phiên bản Spring Framework của dự án. Cookie lifetime không thay thế TTL của session trong repository; hai chính sách cần được thiết kế cùng nhau.

## 3. Khi nào cần resolver riêng?

Hãy cân nhắc triển khai `WebSessionIdResolver` riêng khi ứng dụng có yêu cầu mà resolver mặc định không biểu đạt được:

- Đọc session ID từ cookie có định dạng đặc thù do hệ thống cũ quy định.
- Phát hành hoặc hết hạn nhiều cookie liên quan đến một phiên.
- Dùng tên cookie khác nhau theo tenant hoặc miền ứng dụng.
- Nhận diện phiên qua header thay vì cookie.
- Có quy tắc chuyển đổi hoặc tương thích định dạng ID trong giai đoạn migration.

Không nên tự viết resolver chỉ để thay tên cookie. Resolver tự viết phải xử lý cả ba phương thức, cookie hết hạn, path/domain, response đã commit và request không có cookie. Một lỗi nhỏ có thể khiến người dùng mất phiên sau mỗi request hoặc cookie cũ không bị xóa.

## 4. Cài đặt resolver riêng

Ví dụ dưới đây đọc cookie `APPSESSION`, trả về ID nếu có giá trị, phát cookie khi Spring Session yêu cầu và hết hạn đúng cookie đó khi phiên kết thúc.

~~~java
import java.time.Duration;
import java.util.Collections;
import java.util.List;

import org.springframework.http.HttpCookie;
import org.springframework.http.ResponseCookie;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.session.WebSessionIdResolver;

public final class AppCookieWebSessionIdResolver
        implements WebSessionIdResolver {

    private static final String COOKIE_NAME = "APPSESSION";
    private final boolean secure;

    public AppCookieWebSessionIdResolver(boolean secure) {
        this.secure = secure;
    }

    @Override
    public List<String> resolveSessionIds(ServerWebExchange exchange) {
        HttpCookie cookie = exchange.getRequest()
                .getCookies()
                .getFirst(COOKIE_NAME);

        if (cookie == null || cookie.getValue().isEmpty()) {
            return Collections.emptyList();
        }

        return Collections.singletonList(cookie.getValue());
    }

    @Override
    public void setSessionId(ServerWebExchange exchange, String id) {
        ResponseCookie cookie = ResponseCookie.from(COOKIE_NAME, id)
                .path("/")
                .httpOnly(true)
                .secure(secure)
                .sameSite("Lax")
                .build();

        exchange.getResponse().addCookie(cookie);
    }

    @Override
    public void expireSession(ServerWebExchange exchange) {
        ResponseCookie expiredCookie =
                ResponseCookie.from(COOKIE_NAME, "")
                        .path("/")
                        .httpOnly(true)
                        .secure(secure)
                        .sameSite("Lax")
                        .maxAge(Duration.ZERO)
                        .build();

        exchange.getResponse().addCookie(expiredCookie);
    }
}
~~~

Resolver nhận `secure` từ cấu hình để dùng HTTPS trong production và HTTP trong môi trường phát triển cục bộ. Không tắt `Secure` trong production chỉ để xử lý lỗi cookie. Khi triển khai sau reverse proxy, hãy cấu hình HTTPS ở proxy và ứng dụng nhất quán; không suy luận scheme từ header do client tùy ý gửi nếu proxy chưa được tin cậy.

Đăng ký resolver:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
public class CustomWebSessionCookieConfiguration {

    @Bean
    WebSessionIdResolver webSessionIdResolver(
            @Value("${app.session.cookie.secure:true}") boolean secure) {
        return new AppCookieWebSessionIdResolver(secure);
    }
}
~~~

Cấu hình production:

~~~yaml
app:
  session:
    cookie:
      secure: true
~~~

Trong local development chỉ dùng HTTP, có thể đặt `secure: false` cho profile phát triển. Đặt `secure: true` trong staging và production chạy HTTPS.

Đây là ví dụ tối giản. Trong hệ thống thực tế, cần kiểm thử và cấu hình cookie theo môi trường. Nếu Java baseline cũ, `Collections.emptyList()` và `Collections.singletonList()` giúp không phụ thuộc `List.of`.

## 5. Ý nghĩa của từng thuộc tính cookie

Cookie session chứa session ID có thể dùng để truy cập trạng thái phía máy chủ. Vì vậy, cookie cần được bảo vệ như thông tin xác thực dạng bearer token: ai sở hữu giá trị hợp lệ có thể có khả năng tiếp tục phiên.

| Thuộc tính | Tác dụng | Khuyến nghị |
|---|---|---|
| `HttpOnly` | Ngăn JavaScript thông thường đọc cookie qua `document.cookie` | Bật `true` cho cookie session để giảm nguy cơ đánh cắp qua XSS |
| `Secure` | Chỉ gửi cookie qua kết nối HTTPS | Bật trong staging/production; chỉ tắt ở môi trường HTTP local có kiểm soát |
| `SameSite` | Kiểm soát việc gửi cookie trong request cross-site | Chọn `Lax` hoặc `Strict` nếu phù hợp; dùng `None` khi thực sự cần cross-site và bắt buộc có `Secure` |
| `Path` | Giới hạn các đường dẫn mà trình duyệt gửi cookie | Thường dùng `/` nếu toàn bộ ứng dụng cần phiên |
| `Domain` | Chỉ định host hoặc miền con nhận cookie | Thường bỏ qua để cookie là host-only; chỉ đặt domain chung khi có nhu cầu chia sẻ rõ ràng |
| `Max-Age` / `Expires` | Quy định thời gian cookie tồn tại ở trình duyệt | Phối hợp với TTL server-side; không xem đây là cơ chế thay thế timeout phiên |

### 5.1. HttpOnly và Secure

`HttpOnly` giảm khả năng JavaScript đọc trực tiếp session cookie. Nó không ngăn XSS thực hiện request thay người dùng trong trình duyệt, vì trình duyệt vẫn tự đính kèm cookie phù hợp. Do đó, ứng dụng vẫn cần phòng chống XSS và CSRF.

`Secure` bảo đảm cookie chỉ được gửi qua HTTPS. Trong production, toàn bộ luồng đăng nhập và phiên nên chạy trên HTTPS. Nếu TLS kết thúc ở load balancer hoặc reverse proxy, cần cấu hình proxy và ứng dụng nhất quán để response cookie luôn mang thuộc tính Secure.

### 5.2. SameSite và CSRF

`SameSite=Lax` thường là lựa chọn cân bằng cho ứng dụng web thông thường. `Strict` hạn chế mạnh hơn việc gửi cookie trong điều hướng cross-site, nhưng có thể ảnh hưởng liên kết từ website khác hoặc luồng đăng nhập liên kết. `None` cho phép gửi cookie trong ngữ cảnh cross-site và yêu cầu `Secure`.

Nếu frontend và backend ở hai site khác nhau, trình duyệt có thể cần cookie `SameSite=None; Secure`. Request phía client cũng cần bật gửi credentials và server cần cấu hình CORS cho origin cụ thể cùng credentials. Không dùng wildcard origin với credentials.

SameSite chỉ là một lớp giảm thiểu CSRF. Với cookie được trình duyệt tự động gửi, ứng dụng vẫn cần cơ chế chống CSRF phù hợp như token, kiểm tra Origin/Referer hoặc biện pháp khác theo kiến trúc. Không tắt CSRF chỉ vì cookie đã có SameSite.

### 5.3. Path và Domain

Cookie `Path=/` được gửi tới các endpoint trong toàn bộ host. Nếu ứng dụng chỉ phục vụ dưới một context path riêng, có thể giới hạn path tương ứng, nhưng cần bảo đảm mọi endpoint cần phiên đều nằm trong phạm vi đó.

Khi không chỉ định `Domain`, cookie là host-only và chỉ được gửi tới host đã phát hành nó. Đặt `Domain=example.com` có thể làm cookie được gửi tới nhiều subdomain. Điều này tăng phạm vi tin cậy: một subdomain yếu hơn có thể tạo ra rủi ro cho cookie dùng chung. Chỉ chia sẻ domain khi các subdomain được quản lý cùng mức bảo mật.

Nếu dùng tên cookie có tiền tố `__Host-`, trình duyệt yêu cầu cookie có `Secure`, `Path=/` và không có `Domain`. Ví dụ `__Host-APPSESSION` phù hợp khi ứng dụng chạy HTTPS trên một host và muốn cookie host-only. Hãy bảo đảm các điều kiện này được đáp ứng ở mọi môi trường nơi cookie được sử dụng.

## 6. Phân biệt cookie lifetime và session timeout

Cookie là phương tiện để client gửi session ID. Repository mới là nơi quản lý trạng thái phiên phía máy chủ. Vì vậy, có hai đồng hồ khác nhau:

1. **Cookie lifetime:** thời gian trình duyệt giữ cookie theo `Max-Age` hoặc `Expires`. Nếu không đặt, cookie thường là session cookie theo phiên trình duyệt.
2. **Session timeout:** thời gian repository cho phép phiên tồn tại hoặc không hoạt động trước khi hết hạn.

Một cookie còn hạn vẫn có thể mang session ID đã hết hạn ở Redis hoặc JDBC. Ngược lại, repository có thể còn dữ liệu phiên nhưng trình duyệt đã xóa cookie, khiến người dùng không còn ID để truy cập phiên đó.

Ví dụ, cookie có `Max-Age` 8 giờ trong khi server-side timeout là 30 phút. Sau 30 phút không hoạt động, cookie vẫn được gửi nhưng repository có thể không còn phiên; request mới phải được xử lý như chưa đăng nhập. Nếu cookie hết hạn sau 10 phút trong khi phiên server còn 30 phút, dữ liệu phiên có thể vẫn tồn tại cho tới khi repository dọn dẹp.

Hãy chọn chính sách dựa trên yêu cầu bảo mật và trải nghiệm:

- Cookie session ngắn hạn và timeout server ngắn cho các luồng nhạy cảm.
- Cookie persistent chỉ khi người dùng thực sự cần duy trì đăng nhập qua lần đóng/mở trình duyệt.
- TTL server-side là giới hạn có thẩm quyền đối với trạng thái phiên.
- Logout phải thu hồi phiên trong repository và gửi cookie hết hạn cho client.

## 7. Xóa cookie đúng cách khi phiên kết thúc

Để trình duyệt xóa cookie, response phải phát một cookie cùng tên với giá trị rỗng và thời hạn bằng không hoặc ngày hết hạn trong quá khứ. Thuộc tính định danh cookie phải khớp, đặc biệt là `Path` và `Domain`.

Ví dụ:

~~~java
ResponseCookie expired = ResponseCookie.from("APPSESSION", "")
        .path("/")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .maxAge(Duration.ZERO)
        .build();

exchange.getResponse().addCookie(expired);
~~~

Nếu cookie ban đầu được phát với `Path=/app` hoặc `Domain=example.com`, cookie hết hạn cần dùng cùng phạm vi đó. Nếu path/domain khác nhau, trình duyệt có thể giữ lại cookie cũ và tiếp tục gửi nó trong request.

Trong ứng dụng dùng Spring Session, khi `WebSession` bị invalidate hoặc kết thúc theo luồng quản lý phiên, Spring Session gọi `expireSession` trên resolver để xóa ID ở client. Không chỉ xóa cookie ở trình duyệt mà bỏ qua repository; nếu session ID vẫn còn hợp lệ trong kho dữ liệu, người có bản sao cookie cũ có thể tiếp tục dùng phiên.

## 8. Định dạng session ID và giới hạn bảo mật

Session ID nên là giá trị ngẫu nhiên, khó đoán, không chứa thông tin người dùng hoặc dữ liệu nghiệp vụ. Cookie chỉ mang ID tham chiếu; không nhúng access token, mật khẩu, email hoặc đối tượng `WebSession` vào cookie.

Resolver tùy chỉnh nên:

- Giữ nguyên session ID do Spring Session cấp phát; không tự tạo ID dựa trên timestamp, user ID hoặc số thứ tự.
- Không ghi session ID nguyên vẹn vào log.
- Không giải mã hoặc diễn giải ID nếu không có hợp đồng định dạng rõ ràng.
- Không chấp nhận nhiều định dạng ID tùy tiện trong giai đoạn migration.
- Trả về danh sách rỗng nếu cookie không tồn tại hoặc giá trị rỗng.
- Giữ tên cookie, Path và Domain nhất quán giữa phát hành và hết hạn.

Cookie có giới hạn kích thước tại trình duyệt, proxy và server. Session ID nên ngắn gọn; đừng dùng cookie để truyền toàn bộ trạng thái phiên. Nếu cần dữ liệu bổ sung, lưu trong repository hoặc API riêng có kiểm soát quyền.

## 9. Cấu hình nhiều môi trường và nhiều instance

Tất cả instance WebFlux phục vụ cùng một ứng dụng phải dùng cùng:

- Tên cookie và cách đọc session ID.
- `Path`, `Domain`, `SameSite`, `Secure` và chính sách cookie.
- Cấu hình resolver và định dạng ID.
- Reactive session repository, namespace và serializer.
- Chính sách timeout và logout.

Nếu một instance phát cookie `APPSESSION` nhưng instance khác chỉ đọc `SESSION`, người dùng có thể liên tục bị mất phiên khi load balancer chuyển request. Nếu một node dùng `SameSite=None` và node khác phát `Lax`, hành vi trình duyệt có thể thay đổi theo node.

Khi đổi tên cookie hoặc định dạng ID, hãy lập kế hoạch migration:

1. Triển khai phiên bản có thể đọc cả cookie cũ và cookie mới nếu cần duy trì phiên hiện tại.
2. Phát cookie mới sau khi xác thực ID cũ và tải được phiên hợp lệ.
3. Chọn thời gian hỗ trợ song song dựa trên timeout phiên.
4. Ngừng đọc cookie cũ sau khi phiên cũ hết hạn hoặc đã được chuyển đổi.
5. Xóa cookie cũ bằng đúng tên, Path và Domain đã phát hành trước đó.

Nếu chấp nhận buộc người dùng đăng nhập lại, có thể chọn migration đơn giản hơn: đổi tên cookie, thu hồi phiên cũ theo kế hoạch và phát cookie mới khi người dùng đăng nhập lại. Không thay resolver ở một phần instance mà không có cơ chế tương thích trong giai đoạn rolling deployment.

## 10. Kiểm thử WebSessionIdResolver

Resolver là thành phần ở ranh giới HTTP nên cần kiểm thử cả việc đọc request lẫn ghi response.

### 10.1. Kiểm thử resolveSessionIds

Các trường hợp cần có:

| Request | Kết quả mong đợi |
|---|---|
| Không có cookie `APPSESSION` | Danh sách rỗng |
| Cookie có ID hợp lệ | Danh sách chứa đúng ID |
| Cookie rỗng | Danh sách rỗng |
| Cookie không liên quan | Không ảnh hưởng kết quả |
| Cookie có ID đã hết hạn ở repository | Resolver vẫn có thể trả ID; repository quyết định phiên có tồn tại hay không |

Resolver không thể tự biết một ID có phiên tương ứng trong Redis hay JDBC hay không. Nó chỉ đọc giá trị từ request; bước kiểm tra tính tồn tại thuộc về session repository.

### 10.2. Kiểm thử setSessionId và expireSession

Với `MockServerWebExchange`, có thể xác minh response cookie:

~~~java
@Test
void setSessionIdWritesProtectedCookie() {
    MockServerWebExchange exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/").build());

    WebSessionIdResolver resolver =
            new AppCookieWebSessionIdResolver(true);

    resolver.setSessionId(exchange, "opaque-session-id");

    ResponseCookie cookie =
            exchange.getResponse().getCookies().getFirst("APPSESSION");

    assertNotNull(cookie);
    assertEquals("opaque-session-id", cookie.getValue());
    assertTrue(cookie.isHttpOnly());
    assertTrue(cookie.isSecure());
    assertEquals("/", cookie.getPath());
    assertEquals("Lax", cookie.getSameSite());
}

@Test
void expireSessionWritesCookieWithZeroMaxAge() {
    MockServerWebExchange exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/").build());

    WebSessionIdResolver resolver =
            new AppCookieWebSessionIdResolver(true);

    resolver.expireSession(exchange);

    ResponseCookie cookie =
            exchange.getResponse().getCookies().getFirst("APPSESSION");

    assertNotNull(cookie);
    assertEquals("", cookie.getValue());
    assertEquals(Duration.ZERO, cookie.getMaxAge());
}
~~~

Các import và constructor mock có thể khác đôi chút theo phiên bản Spring Framework. Hãy dùng API kiểm thử của phiên bản dự án đang quản lý bởi Spring Boot BOM.

### 10.3. Integration test với repository thật

Kiểm thử tích hợp nên bao gồm:

1. Request đầu tiên chưa có cookie; ứng dụng tạo WebSession khi nghiệp vụ cần và phát cookie theo resolver.
2. Request tiếp theo gửi cookie; repository tải đúng phiên và handler đọc được thuộc tính.
3. Logout hoặc invalidate phiên; response phát cookie hết hạn và repository không còn phiên hoạt động.
4. Gửi lại cookie cũ; ứng dụng không khôi phục phiên đã thu hồi.
5. Chạy qua hai instance cùng dùng repository; cookie do instance A phát được instance B đọc.
6. Thử các môi trường HTTPS, cross-site và domain/path thực tế.

Đừng chỉ kiểm tra object `ResponseCookie` trong unit test. Hãy dùng HTTP client có cookie jar hoặc browser automation để xác minh trình duyệt nhận và gửi cookie theo đúng chính sách.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Mỗi request đều tạo phiên mới | Resolver không đọc đúng tên cookie hoặc cookie không được gửi lại | Kiểm tra cookie name, Path, Domain, Secure, SameSite và request tiếp theo |
| Logout xong trình duyệt vẫn gửi cookie cũ | `expireSession` không phát cookie hết hạn hoặc Path/Domain không khớp | Xóa cookie với cùng tên, Path và Domain |
| Cookie không được lưu trên HTTPS sau reverse proxy | Thuộc tính Secure hoặc cấu hình TLS/proxy không đúng | Bảo đảm HTTPS theo kiến trúc và luôn phát Secure trong production |
| Frontend khác site không gửi cookie | SameSite Lax/Strict hoặc client không bật credentials | Chỉ dùng SameSite=None; Secure khi cần cross-site, cấu hình CORS và credentials cụ thể |
| Cookie bị JavaScript đọc | Thiếu HttpOnly | Bật HttpOnly và xử lý XSS ở tầng ứng dụng |
| Một số instance đọc được phiên, instance khác không | Resolver, cookie name hoặc repository khác nhau giữa node | Đồng bộ cấu hình và kiểm thử rolling deployment |
| Cookie bị trùng tên nhưng tồn tại nhiều bản | Thay Path hoặc Domain mà không xóa cookie cũ | Gửi cookie hết hạn theo từng phạm vi cũ trước khi ngừng hỗ trợ |

## 12. Checklist trước khi đưa resolver vào production

- [ ] Ứng dụng dùng WebFlux và `WebSession`, không nhầm với Servlet `HttpSession`.
- [ ] Resolver triển khai đúng ba phương thức của `WebSessionIdResolver`.
- [ ] Chỉ dùng resolver riêng khi resolver mặc định không đáp ứng yêu cầu.
- [ ] Cookie session có `HttpOnly` và `Secure` trong production.
- [ ] `SameSite` phù hợp luồng điều hướng và kiến trúc frontend/backend.
- [ ] `Path` và `Domain` nhất quán giữa phát hành và hết hạn cookie.
- [ ] Cookie lifetime được phân biệt với TTL server-side.
- [ ] Logout vừa thu hồi session ở repository vừa hết hạn cookie ở client.
- [ ] Session ID là opaque, ngẫu nhiên và không chứa dữ liệu nhạy cảm.
- [ ] Các instance dùng cùng resolver, repository và cấu hình cookie.
- [ ] Có unit test và integration test cho đọc, phát hành, hết hạn cookie.
- [ ] Không ghi cookie hoặc session ID nguyên vẹn vào log.

`WebSessionIdResolver` là điểm mở rộng giúp ứng dụng WebFlux kiểm soát cách session ID đi qua HTTP. Với nhu cầu thông thường, hãy cấu hình `CookieWebSessionIdResolver` có sẵn; khi cần định dạng hoặc chính sách đặc thù, triển khai resolver riêng và xử lý nhất quán cả đọc ID, phát hành cookie lẫn hết hạn cookie. Kết hợp cấu hình cookie an toàn với repository reactive dùng chung và kiểm thử trên nhiều instance sẽ giúp phiên hoạt động ổn định trong môi trường production.
