# Tránh đưa định danh vào URL, nhật ký hoặc dữ liệu có thể bị chia sẻ

Session ID là định danh bí mật cho phép server tìm lại trạng thái của một phiên. Trong nhiều hệ thống, ai có được session ID hợp lệ có thể sử dụng nó để tiếp tục phiên của người dùng cho đến khi phiên hết hạn hoặc bị thu hồi. Vì vậy, session ID cần được xử lý như một bearer credential: người giữ được giá trị có thể có quyền sử dụng phiên.

Một lỗi phổ biến là đưa session ID vào query string, path, log request hoặc dữ liệu chẩn đoán. Những nơi này thường được lưu lại, sao chép, đồng bộ hoặc chuyển qua nhiều hệ thống. Một URL chứa session ID có thể xuất hiện trong lịch sử trình duyệt, access log, hệ thống analytics, header `Referer`, ảnh chụp màn hình hoặc ticket hỗ trợ. Bài học này giải thích các đường rò rỉ thường gặp, cách truyền định danh an toàn bằng cookie hoặc header, cách che dữ liệu trong log và tracing, cũng như cách kiểm thử để bảo đảm session ID không lọt vào dữ liệu có thể chia sẻ.

## 1. Phân biệt session ID với các loại định danh khác

Không phải mọi ID trong ứng dụng đều có cùng mức độ nhạy cảm. Cần phân biệt rõ mục đích và quyền mà một giá trị đại diện:

| Loại định danh | Ví dụ | Có thể dùng để tiếp tục phiên? | Cách xử lý |
| --- | --- | --- | --- |
| Session ID | Giá trị cookie `SESSION` hoặc header `X-Auth-Token` do Spring Session phát hành | Có, thường hoạt động như bearer credential | Bí mật; không đưa vào URL, log hoặc nội dung chia sẻ |
| Access token | Bearer token trong `Authorization` | Thường có quyền truy cập API theo scope/thời hạn | Bí mật; bảo vệ như credential và che trong log |
| Correlation ID / Request ID | `X-Request-Id: req-8f...` | Không; chỉ liên kết các log/request | Có thể ghi log nếu không chứa dữ liệu bí mật và không được dùng làm credential |
| User ID | `user-204` | Thường không tự xác thực người dùng | Vẫn có thể là dữ liệu cá nhân hoặc dữ liệu nội bộ; chỉ chia sẻ khi cần |
| Session label nội bộ | `checkout-flow` | Không; chỉ mô tả loại luồng | Có thể ghi log nếu không chứa thông tin nhạy cảm |

Session ID thường là chuỗi ngẫu nhiên khó đoán, nhưng tính khó đoán không làm nó trở nên công khai. Nếu server chấp nhận session ID như bằng chứng sở hữu phiên, người khác lấy được ID có thể chiếm quyền phiên. Không dùng session ID làm khóa tra cứu công khai hoặc mã tham chiếu để người dùng gửi cho bộ phận hỗ trợ.

Correlation ID được tạo riêng cho từng request có thể giúp ghép log giữa gateway, ứng dụng và service. Nó không được dùng thay session ID, access token hoặc thông tin xác thực. Khi hỗ trợ điều tra, hãy cung cấp correlation ID đã được tạo ngẫu nhiên thay vì yêu cầu người dùng gửi cookie hoặc session ID.

## 2. Vì sao không đặt session ID trong URL?

Không truyền session ID trong query string hoặc path, ví dụ:

```text
https://app.example.com/account?sessionId=abc123...
https://app.example.com/session/abc123.../account
```

URL có nhiều cơ hội bị lưu lại và chia sẻ ngoài ý muốn:

- **Lịch sử và bookmark:** trình duyệt lưu URL đã truy cập; người dùng có thể bookmark hoặc đồng bộ lịch sử qua nhiều thiết bị.
- **Access log và proxy:** web server, reverse proxy, load balancer, CDN và WAF thường ghi request line, trong đó có path và query string.
- **Analytics và giám sát:** công cụ đo lường, error reporting, session replay hoặc APM có thể thu thập URL đầy đủ.
- **Header `Referer`:** khi trang có URL chứa session ID tải tài nguyên hoặc điều hướng sang trang khác, URL nguồn có thể được gửi trong `Referer`, tùy `Referrer-Policy` và quy tắc trình duyệt.
- **Liên kết được chia sẻ:** URL có thể được sao chép vào chat, email, ticket, tài liệu hoặc ảnh chụp màn hình.
- **Hệ thống tìm kiếm và link preview:** một số công cụ có thể thu thập hoặc hiển thị URL được gửi đến chúng.

Ngay cả khi website dùng HTTPS, URL vẫn có thể xuất hiện trong log và lịch sử ở các điểm cuối TLS hoặc hệ thống quan sát. HTTPS bảo vệ dữ liệu trên đường truyền giữa các điểm kết nối, nhưng không ngăn server, proxy hay trình duyệt lưu URL.

### 2.1. Tránh cả URL rewriting

Một số Servlet container hỗ trợ URL rewriting bằng cách thêm `;jsessionid=...` vào path khi không dùng cookie. Ví dụ:

```text
https://app.example.com/catalog;jsessionid=abc123...
```

Đây vẫn là đưa định danh phiên vào URL và tạo ra các rủi ro tương tự query string. Với ứng dụng dùng session cookie, ưu tiên phương thức tracking bằng cookie. Nếu dùng Spring Session với resolver qua header, hãy để resolver nhận ID từ header thay vì tự xây dựng URL chứa ID. Không gọi `response.encodeURL(...)` với mục đích phát tán session ID trong liên kết.

Đường dẫn và query string cũng có thể bị lưu trong browser history, proxy log hoặc `Referer`; chuyển session ID từ query sang path không giải quyết được vấn đề.

## 3. Truyền session ID bằng cookie cho trình duyệt

Với ứng dụng web tương tác qua trình duyệt, cookie thường là cách phù hợp nhất để mang session ID. Trình duyệt tự gửi cookie theo domain, path, thời hạn, `Secure` và `SameSite`. JavaScript phía client không cần đọc session ID nếu cookie được đặt `HttpOnly`.

Spring Session dùng `CookieSerializer` để kiểm soát cookie. Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class SessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("SESSION");
        serializer.setCookiePath("/");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");
        return serializer;
    }
}
```

Cookie có thể được phát hành dưới dạng:

```http
Set-Cookie: SESSION=...; Path=/; Secure; HttpOnly; SameSite=Lax
```

Các thuộc tính quan trọng:

- `HttpOnly`: ngăn JavaScript đọc cookie qua `document.cookie`; giảm khả năng mã script lấy trực tiếp session ID khi xảy ra XSS. XSS vẫn có thể thực hiện request dưới quyền người dùng trong trang bị chiếm quyền.
- `Secure`: chỉ gửi cookie qua HTTPS. Trong production nên bật và cấu hình proxy/TLS sao cho ứng dụng nhận biết request HTTPS đúng.
- `SameSite`: giới hạn cookie trong ngữ cảnh cross-site theo nhu cầu ứng dụng; chọn `Lax`, `Strict` hoặc `None` sau khi kiểm tra luồng đăng nhập và tích hợp.
- `Path` và `Domain`: giới hạn phạm vi cookie. Không đặt domain rộng hơn mức cần thiết.

Không đưa cookie vào URL hoặc response body để JavaScript tự lưu. Không bật URL rewriting chỉ để hỗ trợ trình duyệt tắt cookie; nếu cần hỗ trợ client đặc biệt, thiết kế resolver riêng với kênh truyền an toàn và threat model rõ ràng.

## 4. Dùng header cho client phù hợp

Một số client không phải trình duyệt, ứng dụng native hoặc tích hợp service-to-service có thể cần gửi session ID qua HTTP header. Spring Session cung cấp `HttpSessionIdResolver` và `HeaderHttpSessionIdResolver` cho kiểu tích hợp này.

Ví dụ dùng header `X-Auth-Token`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.HeaderHttpSessionIdResolver;
import org.springframework.session.web.http.HttpSessionIdResolver;

@Configuration
public class SessionIdResolverConfiguration {

    @Bean
    HttpSessionIdResolver httpSessionIdResolver() {
        return HeaderHttpSessionIdResolver.xAuthToken();
    }
}
```

Với resolver này, client gửi session ID trong request header:

```http
GET /api/profile HTTP/1.1
Host: api.example.com
X-Auth-Token: <session-id>
```

Spring Session đọc ID từ header đã cấu hình và dùng repository để tìm session. Khi tạo session, resolver cũng có thể phát định danh qua response header tương ứng. Client cần lưu giá trị này trong bộ nhớ an toàn và gửi lại trong các request tiếp theo.

Header không tự động trở thành vùng an toàn. Reverse proxy, API gateway, WAF, APM agent hoặc middleware ghi request headers có thể ghi lại `X-Auth-Token`. Cần cấu hình redaction ở mọi lớp có thể thu thập header đó. Luôn dùng HTTPS và không ghi giá trị header vào log ứng dụng.

`X-Auth-Token` trong ví dụ là session ID, không phải một access token độc lập được cấp theo OAuth. Nếu hệ thống đã dùng `Authorization: Bearer` cho Spring Security OAuth2 Resource Server, không dùng chung header đó cho session ID vì dễ nhầm lẫn cơ chế xác thực và chính sách thu hồi. Chọn một header riêng, đặt tên rõ và giới hạn nơi chấp nhận.

### 4.1. Cookie hay header: chọn theo loại client

| Client | Kênh thường phù hợp | Lưu ý |
| --- | --- | --- |
| Website truyền thống | Cookie `HttpOnly; Secure; SameSite=...` | Trình duyệt tự quản lý; cần CSRF protection phù hợp |
| SPA cùng site với backend | Cookie `HttpOnly` thường là lựa chọn tốt | JavaScript không cần đọc session ID; cấu hình CSRF token cho request unsafe |
| Native mobile app hoặc desktop client | Header qua HTTPS có thể phù hợp | Bảo vệ token trong secure storage; không ghi header vào log |
| Service-to-service | Credential riêng hoặc cơ chế xác thực service phù hợp; header nếu dùng session cần được quản lý như secret | Xem xét OAuth2 client credentials/mTLS thay vì chia sẻ session người dùng |
| CLI hoặc integration client | Header qua HTTPS | Không đặt ID trong command-line URL; tránh lưu token trong shell history |

Không chuyển tất cả ứng dụng sang header chỉ vì dễ debug. Với browser, cookie `HttpOnly` thường giảm nhu cầu để JavaScript cầm session ID. Header-based session ID phù hợp khi client có khả năng quản lý secret và request header được kiểm soát.

### 4.2. Header tùy chỉnh và CORS

Nếu browser gửi header tùy chỉnh đến API cross-origin, trình duyệt có thể thực hiện CORS preflight. Server cần cho phép đúng origin và header cần thiết, ví dụ:

```http
Access-Control-Allow-Origin: https://client.example.com
Access-Control-Allow-Methods: GET, POST, PUT, DELETE
Access-Control-Allow-Headers: Content-Type, X-Auth-Token
Vary: Origin
```

Chỉ cho phép origin tin cậy và header thực sự cần. Không dùng wildcard một cách tùy tiện. Nếu client dùng cookie cross-origin thì còn phải xử lý `credentials`, `Access-Control-Allow-Credentials` và SameSite; đó là luồng khác với custom header. Dù header không tự động được gửi như cookie, XSS trong origin được phép vẫn có thể đọc token từ nơi lưu phía client và gửi nó đi.

## 5. Nhật ký không được chứa session ID

Log thường được tập trung vào hệ thống bên ngoài, lưu nhiều ngày hoặc chia sẻ với nhiều nhóm vận hành. Nếu session ID lọt vào log, người có quyền đọc log có thể có được credential còn hiệu lực. Không ghi toàn bộ request/response headers khi chưa lọc các trường nhạy cảm.

Các trường cần được che hoặc loại bỏ:

| Nguồn | Trường cần bảo vệ |
| --- | --- |
| Request headers | `Cookie`, `X-Auth-Token`, `Authorization`, và mọi header chứa session/access token |
| Response headers | `Set-Cookie`, header trả session ID hoặc token |
| URL | Query parameters và path segments có tên như `session`, `sid`, `token`, `auth`, `access_token` |
| Request/response body | Trường token, session ID, credential hoặc dữ liệu nhạy cảm được gửi nhầm trong payload |
| Exception/debug dump | Object request/session, header map, cookie collection hoặc context chứa credential |
| Trace/span/baggage | Tag hoặc baggage có chứa session ID, token hoặc định danh người dùng nhạy cảm |

Ví dụ cấu hình access log cần tránh ghi header cookie và token. Với reverse proxy hoặc gateway, dùng danh sách trường được phép ghi (allowlist) thay vì ghi toàn bộ header. Nếu công cụ hỗ trợ redaction, cấu hình che giá trị trước khi log được gửi đến hệ thống tập trung. Redaction cần áp dụng cả ở môi trường production lẫn môi trường staging có dữ liệu gần giống production.

Trong code ứng dụng, ghi log metadata cần thiết thay vì dump request:

```java
log.info("Session request handled: method={}, path={}, requestId={}",
        request.getMethod(), request.getRequestURI(), requestId);
```

Ví dụ này vẫn cần bảo đảm `requestURI` không có session ID trong path và không ghi query string nhạy cảm. Nếu path có thể chứa mã bí mật hoặc dữ liệu cá nhân, chỉ ghi route template như `/accounts/{accountId}` thay vì URL thực tế.

Không nên viết:

```java
log.debug("Request headers: {}", Collections.list(request.getHeaderNames()));
log.debug("Cookie: {}", request.getHeader("Cookie"));
log.debug("Session id: {}", request.getSession().getId());
```

Header names tự thân thường không chứa giá trị secret, nhưng dump toàn bộ headers hoặc request object rất dễ làm lộ credential. Nếu cần chẩn đoán cookie, ghi trạng thái có/không hoặc tên cookie đã allowlist, tuyệt đối không ghi value.

## 6. Ngăn định danh lọt vào tracing, analytics và dữ liệu chia sẻ

Ngoài log ứng dụng, session ID có thể bị thu thập bởi:

- **Distributed tracing:** instrumentation tự động thu thập HTTP attributes hoặc header. Cấu hình loại trừ `Cookie`, `Set-Cookie`, `X-Auth-Token`, `Authorization` và các header tùy chỉnh chứa secret.
- **APM và error reporting:** công cụ có thể chụp request headers, URL, breadcrumb, exception context hoặc biến môi trường. Bật chế độ scrub/redact và kiểm tra dữ liệu thực tế đã gửi.
- **Analytics và session replay:** không gửi session ID, cookie hoặc token thành event property, URL parameter hay custom dimension.
- **Ticket hỗ trợ và chat:** yêu cầu người dùng gửi correlation ID hoặc timestamp, không yêu cầu họ dán cookie, header xác thực hoặc URL chứa token.
- **Ảnh chụp màn hình và video:** che tab URL, DevTools request headers, cookie storage và mọi vùng có thể hiện credential trước khi chia sẻ.
- **Shell history và script:** không đặt token thật trực tiếp trong command line, URL hoặc biến được echo ra terminal. Dùng secret store hoặc input bảo mật phù hợp với công cụ.

Với tracing, nên dùng request ID ngẫu nhiên để nối các span. Không đưa session ID vào `traceId`, `spanId`, baggage hoặc metric label. Các giá trị dùng làm nhãn metric có thể bị nhân bản theo từng phiên, làm tăng cardinality và tạo thêm một bản sao của secret trong hệ thống giám sát.

`Referer` cần được hiểu đúng: trình duyệt không tự gửi request headers của trang trước trong `Referer`, nhưng có thể gửi URL nguồn. Vì vậy, session ID trong URL có thể rò rỉ qua `Referer`, còn session ID trong cookie/header có thể rò rỉ qua hệ thống ghi request headers. Cần bảo vệ cả hai nhóm đường đi.

## 7. Kiểm soát URL, cache và chia sẻ response

Không đặt session ID trong URL là bước đầu. Cũng cần kiểm soát dữ liệu trang được cache hoặc chia sẻ:

- Với response chứa dữ liệu riêng theo session, dùng chính sách cache phù hợp, thường là `Cache-Control: no-store` cho nội dung nhạy cảm cần tránh lưu ở browser/proxy cache.
- Cấu hình CDN/reverse proxy không cache response đã xác thực hoặc response có `Set-Cookie` trừ khi có chính sách cache riêng được kiểm thử.
- Không nhúng session ID vào link tải xuống, link reset, URL callback hoặc tham số analytics. Với link một lần, tạo token riêng có scope, thời hạn ngắn và cơ chế thu hồi, không tái sử dụng session ID.
- Chọn `Referrer-Policy` phù hợp để hạn chế URL nguồn bị gửi ra ngoài. Đây là lớp giảm rò rỉ URL, không phải lý do để đặt secret vào URL.
- Khi chia sẻ response lỗi hoặc trang debug, loại bỏ header `Set-Cookie`, cookie và thông tin session trước khi đính kèm.

Ví dụ response cho trang chứa thông tin tài khoản:

```http
Cache-Control: no-store
Pragma: no-cache
Referrer-Policy: strict-origin-when-cross-origin
```

`no-store` hướng dẫn cache không lưu response; `Referrer-Policy` giới hạn thông tin URL nguồn trong điều hướng cross-origin. Các header này không thay thế việc giữ session ID khỏi URL và log.

## 8. Vòng đời bảo vệ session ID

Session ID cần được bảo vệ trong toàn bộ vòng đời, không chỉ ở thời điểm phát hành:

1. **Tạo phiên:** dùng ID ngẫu nhiên đủ mạnh do Spring Session/repository sinh. Không tự tạo ID từ user ID, email, timestamp hoặc số tăng dần.
2. **Sau xác thực:** bảo đảm session ID được thay đổi theo cơ chế chống session fixation của Spring Security hoặc chính sách tương ứng. Không tiếp tục tin ID được cấp trước khi người dùng đăng nhập.
3. **Truyền ID:** dùng cookie bảo mật cho browser hoặc header qua HTTPS cho client phù hợp. Không dùng query string, path hoặc URL rewriting.
4. **Ghi nhận hoạt động:** log correlation ID, loại request và kết quả xử lý; không log session ID hay credential.
5. **Đăng xuất:** invalidate session ở server và xóa cookie đúng tên/domain/path; với header-based client, xóa token khỏi secure storage phía client.
6. **Thu hồi khi có sự cố:** nếu nghi ngờ session ID bị lộ, xóa phiên tương ứng hoặc thu hồi tất cả phiên bị ảnh hưởng, đồng thời kiểm tra log/APM/ticket để xác định nơi dữ liệu đã xuất hiện.

Session ID là bearer secret; chỉ xóa cookie phía browser không thu hồi session ở repository. Ngược lại, invalidate session trên server nhưng không xóa cookie sẽ khiến client tiếp tục gửi ID cũ, dù server phải từ chối phiên đó. Hai bước cần được phối hợp.

## 9. Kiểm thử để phát hiện rò rỉ định danh

Nên dùng một session ID giả có dấu nhận diện duy nhất trong test, ví dụ `TEST-SESSION-DO-NOT-USE-7f3a`, và xác nhận chuỗi này không xuất hiện trong các đầu ra có thể lưu hoặc chia sẻ.

Các kịch bản kiểm thử:

1. Gửi request với cookie session giả lập và xác nhận access log không chứa giá trị cookie.
2. Gửi request với header `X-Auth-Token` giả lập và xác nhận log ứng dụng, gateway, WAF và APM không ghi giá trị header.
3. Kiểm tra response tạo session: session ID chỉ xuất hiện ở cookie hoặc header resolver đã chọn, không nằm trong body, URL redirect hoặc query string.
4. Kiểm tra redirect, liên kết trong trang, email và callback không chứa session ID.
5. Kiểm tra `Referer` khi tải tài nguyên cùng site và điều hướng cross-site; URL không chứa secret nên không thể rò rỉ ID qua nguồn tham chiếu.
6. Kiểm tra trace/span attributes, baggage, metric labels, analytics events và error reports không có session ID hoặc token.
7. Kiểm tra quy trình hỗ trợ: correlation ID được cung cấp thay cho cookie hoặc session ID.
8. Thử logout và xác minh session bị invalidate, cookie bị xóa hoặc header token phía client bị loại bỏ.

Ví dụ kiểm tra log trong integration test có thể dùng một appender test để thu các dòng log, sau đó khẳng định marker không xuất hiện:

```java
String fakeSessionId = "TEST-SESSION-DO-NOT-USE-7f3a";

// Gửi request test với fakeSessionId qua cookie hoặc header.
// Thu log từ appender test và kiểm tra:
assertThat(capturedLogs).doesNotContain(fakeSessionId);
```

Đây là minh họa cho cách kiểm tra; cần kết nối appender và HTTP test client theo framework test của dự án. Không dùng session ID thật trong test fixture, vì log test có thể được lưu trong CI artifact hoặc chia sẻ với đội phát triển.

## 10. Những lỗi thường gặp

- **Đặt session ID trong query string để debug:** URL bị lưu trong history, access log, analytics và có thể xuất hiện trong `Referer`.
- **Chuyển ID từ query sang path:** vẫn là URL và vẫn có các đường rò rỉ tương tự.
- **Cho rằng HTTPS bảo vệ URL khỏi log:** HTTPS bảo vệ đường truyền, không ngăn browser, proxy hoặc server ghi URL.
- **Che ID trong log ứng dụng nhưng quên gateway/APM:** mọi lớp thu thập request đều cần chính sách redaction.
- **Dùng header rồi cho rằng không thể rò rỉ:** header có thể bị ghi lại bởi middleware, tracing hoặc proxy.
- **Ghi toàn bộ request/response để tiện debug:** có thể làm lộ `Cookie`, `Set-Cookie`, `Authorization` và custom token headers.
- **Dùng session ID làm correlation ID:** người đọc log có thể có được credential; correlation ID phải độc lập và không có quyền xác thực.
- **Yêu cầu người dùng gửi cookie trong ticket:** biến kênh hỗ trợ thành nơi lưu secret có thể bị chia sẻ rộng.
- **Chỉ xóa cookie khi logout:** session phía server có thể vẫn còn hiệu lực cho đến khi hết hạn.

## 11. Checklist triển khai

Trước khi phát hành, xác nhận:

- [ ] Session ID được coi là bearer credential và được sinh bằng cơ chế ngẫu nhiên an toàn.
- [ ] Browser dùng cookie `HttpOnly`, `Secure` và `SameSite` phù hợp.
- [ ] Client đặc biệt dùng header resolver qua HTTPS, có chính sách lưu trữ và thu hồi rõ ràng.
- [ ] Không có session ID trong query string, path, URL rewriting, redirect hoặc link chia sẻ.
- [ ] Access log, application log, proxy, gateway, WAF, APM và tracing đã che các header/cookie nhạy cảm.
- [ ] Response chứa dữ liệu riêng được cache theo chính sách phù hợp; không phát tán `Set-Cookie` trong báo cáo.
- [ ] Correlation ID độc lập với session ID và được dùng để hỗ trợ điều tra.
- [ ] CSRF protection được duy trì với xác thực dựa trên cookie.
- [ ] Session ID được thay đổi sau xác thực theo cơ chế chống session fixation.
- [ ] Logout invalidate session và xóa cookie/token phía client.
- [ ] Có test marker giả để phát hiện session ID trong log, trace, analytics và artifact CI.

## 12. Tự kiểm tra kiến thức

Bạn đã nắm được nội dung nếu có thể giải thích:

- Vì sao session ID cần được bảo vệ như bearer credential?
- Những nơi nào có thể lưu URL chứa session ID và vì sao `Referer` làm tăng rủi ro?
- Vì sao cookie `HttpOnly; Secure` thường phù hợp cho browser?
- Khi nào `HeaderHttpSessionIdResolver` phù hợp và vì sao header vẫn cần redaction?
- Correlation ID khác session ID như thế nào?
- Cần che những header và trường nào trong access log, APM và tracing?
- Vì sao HTTPS, CORS hoặc việc xóa cookie đơn lẻ không đủ để giải quyết toàn bộ rủi ro?
- Làm thế nào kiểm thử để phát hiện session ID bị ghi vào dữ liệu có thể chia sẻ?

Định danh phiên chỉ nên xuất hiện trong kênh truyền được kiểm soát và ở nơi thật sự cần để server nhận ra phiên. Với trình duyệt, cookie bảo mật thường là lựa chọn phù hợp; với client đặc biệt, header resolver có thể đáp ứng yêu cầu nếu được bảo vệ như secret. URL, log, tracing, analytics và ticket hỗ trợ nên dùng correlation ID hoặc metadata không có quyền xác thực, không dùng session ID.
