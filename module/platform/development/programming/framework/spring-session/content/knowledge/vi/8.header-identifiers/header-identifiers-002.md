# HeaderHttpSessionIdResolver và trao đổi định danh phiên qua HTTP header

Spring Session cần một cách nhận diện phiên hiện tại trong mỗi HTTP request. Với trình duyệt truyền thống, cách phổ biến là gửi session ID qua cookie. Với ứng dụng REST, ứng dụng di động hoặc client JavaScript tự quản lý thông tin xác thực, có thể truyền session ID trong HTTP header. Spring Session cung cấp HeaderHttpSessionIdResolver để thực hiện cách trao đổi này.

Resolver chỉ quyết định **đọc session ID từ header request và ghi session ID vào header response**. Nó không tự xác thực người dùng, không cấp quyền truy cập và cũng không thay thế repository lưu phiên. Repository vẫn có thể là Redis hoặc JDBC; SessionRepositoryFilter vẫn kết nối Servlet API với repository. Phần khác biệt nằm ở cách client gửi và nhận định danh phiên.

## 1. Vai trò của HttpSessionIdResolver

Trong Servlet integration, Spring Session dùng giao diện HttpSessionIdResolver để trừu tượng hóa cách truyền session ID giữa client và server. Giao diện này có ba thao tác chính:

| Phương thức | Nhiệm vụ |
|---|---|
| resolveSessionIds(request) | Đọc một hoặc nhiều session ID từ request hiện tại |
| setSessionId(request, response, sessionId) | Gửi session ID về client khi cần tạo hoặc cập nhật định danh |
| expireSession(request, response) | Thông báo cho client rằng định danh phiên cần được loại bỏ |

CookieHttpSessionIdResolver thực hiện các thao tác đó bằng cookie. HeaderHttpSessionIdResolver thực hiện bằng HTTP header.

Khi dùng header, client thường gửi một header trong request, chẳng hạn X-Auth-Token, chứa session ID. Server đọc giá trị đó rồi dùng repository để tìm phiên. Nếu request tạo một phiên mới, Spring Session có thể ghi session ID vào header của response để client lưu lại và sử dụng cho các request tiếp theo.

Header resolver không lưu dữ liệu phiên. Nó cũng không biến session ID thành JWT hoặc access token theo chuẩn OAuth. Giá trị header chỉ là định danh để Spring Session tìm phiên trong repository.

## 2. Header mặc định và cách tạo resolver

HeaderHttpSessionIdResolver cung cấp factory method xAuthToken() để dùng header mặc định X-Auth-Token (tên header HTTP không phân biệt chữ hoa, chữ thường). Có thể dùng một header riêng bằng factory method header(String).

Ví dụ cấu hình Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.HeaderHttpSessionIdResolver;
import org.springframework.session.web.http.HttpSessionIdResolver;

@Configuration
public class SessionIdConfiguration {

    @Bean
    public HttpSessionIdResolver httpSessionIdResolver() {
        return HeaderHttpSessionIdResolver.xAuthToken();
    }
}
~~~

Nếu muốn tên header rõ nghĩa với API nội bộ, có thể chọn tên tùy chỉnh:

~~~java
@Bean
public HttpSessionIdResolver httpSessionIdResolver() {
    return HeaderHttpSessionIdResolver.header("X-Session-Id");
}
~~~

Khi Spring Session phát hiện bean HttpSessionIdResolver, resolver đó được dùng để trao đổi ID phiên trong Servlet integration. Vì vậy, cần xác nhận bean đã nằm trong application context và được cấu hình cùng SessionRepositoryFilter.

Ví dụ trên chọn một resolver cho ứng dụng. Khi chuyển từ cookie sang header, client hiện tại phải được cập nhật để gửi và nhận header mới. Không nên cho rằng Spring Session tự động đọc cả cookie lẫn header chỉ vì cả hai kiểu resolver đều có trong thư viện. Nếu thật sự cần hỗ trợ song song nhiều kiểu client, cần thiết kế một resolver kết hợp có quy tắc ưu tiên và xử lý xung đột rõ ràng.

## 3. Quy trình trao đổi session ID

Quy trình có thể chia thành hai chiều: server phát ID và client gửi lại ID.

### 3.1. Server phát ID khi tạo phiên

Ở request đầu tiên, client chưa có session ID nên không gửi header định danh. Một endpoint gọi request.getSession() có thể làm Servlet session mới được tạo. Spring Session lưu phiên qua repository và resolver ghi ID vào response header.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/api")
public class SessionController {

    @GetMapping("/session")
    public Map<String, Object> getSession(HttpServletRequest request) {
        HttpSession session = request.getSession();

        Integer visits = (Integer) session.getAttribute("visits");
        visits = visits == null ? 1 : visits + 1;
        session.setAttribute("visits", visits);

        return Map.of(
            "sessionCreated", session.isNew(),
            "visits", visits
        );
    }
}
~~~

Khi client gọi endpoint lần đầu, response có thể gồm:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Auth-Token: <session-id>
~~~

Giá trị session-id là minh họa, không phải chuỗi cố định. Session ID thực tế do Spring Session/repository tạo ra và phải được xem như một bí mật xác thực.

### 3.2. Client gửi lại ID trong request sau

Sau khi nhận header response, client lưu ID theo chính sách bảo mật của nền tảng. Mỗi request tiếp theo gửi lại cùng header:

~~~http
GET /api/session HTTP/1.1
Host: api.example.test
X-Auth-Token: <session-id>
~~~

HeaderHttpSessionIdResolver đọc giá trị header và cung cấp ID cho Spring Session. SessionRepositoryFilter dùng ID đó để tìm phiên trong Redis hoặc JDBC. Controller nhận được cùng ngữ cảnh HttpSession và có thể đọc thuộc tính visits đã lưu ở request trước.

Nếu ID không tồn tại, sai định dạng theo repository hoặc phiên đã hết hạn, request sẽ không khôi phục được phiên cũ. Ứng dụng có thể tạo phiên mới nếu endpoint gọi getSession() và chính sách cho phép. Với endpoint chỉ kiểm tra phiên hiện tại, dùng getSession(false) để tránh vô tình tạo phiên mới.

### 3.3. Luồng tổng thể

    Client chưa có session ID
             |
             | GET /api/session
             v
    Spring Session filter
             |
             | Không tìm thấy ID trong request
             v
    Controller tạo HttpSession
             |
             v
    SessionRepository (Redis / JDBC)
             |
             | Lưu dữ liệu phiên
             v
    Response: X-Auth-Token: <session-id>
             |
             v
    Client lưu session ID
             |
             | Request sau gửi X-Auth-Token
             v
    Spring Session filter đọc header
             |
             | Tải phiên theo ID
             v
    Controller tiếp tục dùng cùng HttpSession

Điểm quan trọng là response header phải được client đọc và giữ lại. Nếu client không nhận hoặc không gửi lại ID, server không thể liên kết các request đó với cùng phiên.

## 4. Cấu hình client

Client phải thực hiện hai việc: đọc session ID từ response header và gửi nó trong header của request kế tiếp. Ví dụ JavaScript với Fetch API:

~~~javascript
let sessionId = null;

async function callSessionApi() {
    const headers = {};

    if (sessionId) {
        headers["X-Auth-Token"] = sessionId;
    }

    const response = await fetch("/api/session", {
        method: "GET",
        headers
    });

    const returnedId = response.headers.get("X-Auth-Token");

    if (returnedId !== null) {
        if (returnedId.length === 0) {
            sessionId = null;
        } else {
            sessionId = returnedId;
        }
    }

    if (!response.ok) {
        throw new Error("Session API request failed");
    }

    return response.json();
}
~~~

Ví dụ này giữ ID trong bộ nhớ của trang để minh họa quy trình. Ứng dụng thực tế cần chọn nơi lưu trữ phù hợp với threat model:

- Ứng dụng di động nên cân nhắc kho lưu trữ bảo mật của hệ điều hành.
- Ứng dụng chạy trong trình duyệt nên hạn chế thời gian tồn tại của ID và cân nhắc rủi ro XSS nếu JavaScript có thể đọc giá trị.
- Không ghi session ID vào URL, query string, analytics, log hoặc dữ liệu telemetry.
- Không đưa ID vào mã nguồn, cấu hình tĩnh hay dữ liệu có thể chia sẻ công khai.

Header resolver gửi session ID dạng giá trị thô. Không tự thêm tiền tố Bearer trừ khi ứng dụng có một giao thức riêng và resolver được viết để xử lý giao thức đó. HeaderHttpSessionIdResolver không tự phân tích JWT hoặc thực hiện OAuth token validation.

## 5. CORS khi client chạy ở origin khác

Nếu trình duyệt gọi API ở origin khác, custom header như X-Auth-Token thường làm request phát sinh CORS preflight. Server phải cho phép client gửi header đó và cho phép JavaScript đọc header trong response.

Ví dụ cấu hình CORS khái niệm:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.test"));
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(List.of("Content-Type", "X-Auth-Token"));
    config.setExposedHeaders(List.of("X-Auth-Token"));
    config.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

Hai thiết lập thường bị nhầm:

| Thiết lập CORS | Tác dụng |
|---|---|
| allowedHeaders | Cho phép trình duyệt gửi header X-Auth-Token trong request |
| exposedHeaders | Cho phép JavaScript đọc header X-Auth-Token trong response |

Nếu chỉ cho phép allowedHeaders, server có thể nhận request nhưng JavaScript không đọc được ID mới từ response. Nếu chỉ expose response header, request preflight có thể bị từ chối vì header request chưa được cho phép.

Chỉ cho phép các origin, method và header cần thiết. Không dùng wildcard origin một cách tùy tiện, nhất là khi ứng dụng có cấu hình credentials hoặc dữ liệu phiên nhạy cảm. Cấu hình CORS cần phối hợp đúng thứ tự với Spring Security để preflight được xử lý phù hợp.

## 6. Đăng xuất và xóa định danh ở client

Khi người dùng đăng xuất, ứng dụng phải vô hiệu hóa phiên ở phía server. Việc chỉ xóa biến sessionId trong JavaScript không làm bản ghi phiên trong Redis hoặc JDBC biến mất.

Ví dụ endpoint minh họa:

~~~java
@PostMapping("/logout")
public ResponseEntity<Void> logout(HttpServletRequest request) {
    HttpSession session = request.getSession(false);

    if (session != null) {
        session.invalidate();
    }

    return ResponseEntity.noContent().build();
}
~~~

Khi phiên bị invalidate, Spring Session có thể gọi expireSession của resolver. Với HeaderHttpSessionIdResolver, response được thiết lập header tương ứng với giá trị rỗng để báo client loại bỏ ID đã lưu. Client cần xử lý response này và xóa ID cũ.

Luồng logout:

1. Client gửi request logout kèm X-Auth-Token.
2. Server khôi phục phiên hiện tại.
3. Ứng dụng hoặc Spring Security xóa SecurityContext và invalidate phiên.
4. Spring Session xóa phiên khỏi repository theo cơ chế của repository.
5. Resolver ghi header hết hạn với giá trị rỗng.
6. Client nhận response và xóa session ID khỏi bộ nhớ hoặc kho lưu trữ bảo mật.

Trong ứng dụng có Spring Security, nên dùng logout flow của Spring Security để phối hợp xóa SecurityContext, invalidate session và các handler cần thiết. Endpoint minh họa phía trên chỉ làm rõ vai trò invalidate; không phải một thay thế đầy đủ cho cấu hình logout bảo mật.

Nếu response logout không đến được client, client có thể vẫn giữ ID cũ. Request tiếp theo phải bị từ chối vì phiên đã bị xóa hoặc vô hiệu hóa ở server. Không dựa vào việc client đã xóa ID để đảm bảo thu hồi phiên.

## 7. Thay đổi session ID sau xác thực

Session fixation là rủi ro khi kẻ tấn công biết hoặc ép nạn nhân dùng một session ID trước khi đăng nhập. Sau khi xác thực thành công, cơ chế bảo vệ của Spring Security có thể thay đổi session ID để ngăn việc tiếp tục dùng định danh cũ.

Với header resolver, client phải cập nhật giá trị session ID khi server phát ID mới trong response. Nếu client tiếp tục gửi ID cũ, nó có thể mất trạng thái xác thực hoặc bị xem là chưa đăng nhập.

Do đó, sau login hoặc bất kỳ thao tác nào thay đổi session ID:

- Đọc header session ID từ response.
- Thay thế ID cũ bằng ID mới trong kho client.
- Không giữ đồng thời ID cũ và ID mới như hai credential có hiệu lực.
- Kiểm thử request kế tiếp thực sự dùng ID mới.
- Nếu response bị lỗi hoặc bị proxy loại bỏ header, xử lý như một lỗi đồng bộ phiên và yêu cầu client xác thực lại theo chính sách.

Không tự triển khai việc đổi ID bằng cách tạo chuỗi ngẫu nhiên trong client. Việc cấp và xoay vòng session ID phải do Spring Session/Spring Security hoặc cơ chế server tin cậy thực hiện.

## 8. Header session ID là một credential nhạy cảm

Ai sở hữu session ID còn hiệu lực có thể có khả năng sử dụng phiên đó. Vì vậy, session ID trong header cần được bảo vệ như một bearer credential.

Các yêu cầu cơ bản:

- Chỉ truyền qua HTTPS.
- Dùng session ID ngẫu nhiên, đủ độ khó đoán và do server quản lý.
- Không ghi giá trị header vào access log, application log, trace hoặc công cụ giám sát.
- Cấu hình reverse proxy, API gateway và WAF để không lưu hoặc hiển thị header nhạy cảm.
- Không đưa session ID vào URL hoặc nội dung lỗi.
- Thu hồi phiên phía server khi logout, khóa tài khoản hoặc phát hiện lộ ID.
- Giới hạn quyền truy cập vào kho phiên và mã hóa đường truyền đến Redis/JDBC khi môi trường yêu cầu.

Custom header có thể giảm một số rủi ro CSRF kiểu form truyền thống vì trình duyệt bên ngoài không thể tự đặt tùy ý custom header trong một form HTML thông thường. Tuy nhiên, điều đó không biến header resolver thành một cơ chế chống CSRF hoàn chỉnh. XSS có thể đọc hoặc sử dụng ID nếu ứng dụng để JavaScript truy cập; CORS quá rộng cũng có thể mở đường cho trang khác gửi request hoặc đọc response. Hãy áp dụng CSRF policy phù hợp với cách client giữ credential và cấu hình origin.

Nếu session ID được giữ trong localStorage, bất kỳ script chạy cùng origin có thể đọc nó. Với ứng dụng nhạy cảm, cần cân nhắc kỹ giữa header-based session và cookie HttpOnly do trình duyệt tự quản lý. Header resolver phù hợp khi client cần chủ động quản lý ID; cookie thường phù hợp hơn khi muốn trình duyệt tự gửi credential mà JavaScript không đọc được.

## 9. Không nhầm header resolver với xác thực và phân quyền

HeaderHttpSessionIdResolver chỉ giúp xác định phiên. Sau khi phiên được khôi phục, ứng dụng vẫn phải kiểm tra trạng thái xác thực và quyền truy cập.

| Thành phần | Trách nhiệm |
|---|---|
| HeaderHttpSessionIdResolver | Đọc/ghi session ID qua HTTP header |
| SessionRepositoryFilter | Kết nối Servlet request/response với Spring Session |
| SessionRepository (Redis/JDBC) | Lưu và tải dữ liệu phiên |
| Spring Security | Khôi phục Authentication, xác thực và kiểm tra quyền |
| Controller/service | Thực hiện nghiệp vụ sau khi quyền truy cập được xác nhận |

Một request có header X-Auth-Token không mặc nhiên hợp lệ. ID có thể sai, đã hết hạn, đã bị thu hồi hoặc thuộc một phiên không có quyền truy cập endpoint. Ứng dụng cần bảo vệ các route theo chính sách authorization và không dùng sự hiện diện của header làm điều kiện cấp quyền.

Nếu ứng dụng dùng bearer JWT stateless, đó là mô hình xác thực khác. Không nên dùng session ID của Spring Session như thể nó là JWT: session ID là khóa tra cứu dữ liệu trạng thái phía server, trong khi JWT mang các claim được ký và có quy tắc xác minh riêng.

## 10. Tích hợp với nhiều instance và kho phiên dùng chung

Header resolver không thay đổi nguyên tắc triển khai phân tán. Nếu request đầu tiên đến instance A và request tiếp theo đến instance B, B phải đọc được cùng phiên từ kho dữ liệu dùng chung.

Để điều đó hoạt động:

- Tất cả instance dùng cùng loại repository hoặc cấu hình tương thích.
- Các instance kết nối cùng Redis cluster hoặc cùng cơ sở dữ liệu phiên.
- Namespace và serialization tương thích.
- Tên header và cách xử lý ID thống nhất.
- Load balancer và reverse proxy chuyển tiếp custom header nguyên vẹn.
- Không có instance nào vô tình dùng session cục bộ của Servlet container trong khi instance khác dùng Spring Session.

Sticky session ở load balancer không thay thế repository dùng chung. Sticky routing có thể giữ request ở cùng instance trong một thời gian, nhưng khi instance restart hoặc client được chuyển sang instance khác, session cục bộ sẽ không được chia sẻ.

Khi kiểm thử nhiều instance, hãy tạo phiên qua instance A, lấy session ID trong response, rồi gửi request có header đó qua instance B. Nếu B khôi phục được thuộc tính phiên, luồng trao đổi ID và repository chia sẻ đang phối hợp đúng.

## 11. Lỗi thường gặp khi dùng HeaderHttpSessionIdResolver

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Request đầu tiên không nhận được session ID | Endpoint không tạo phiên hoặc response header bị lọc | Kiểm tra getSession(), response header và proxy |
| Request sau tạo phiên mới mỗi lần | Client không gửi lại header hoặc tên header sai | Kiểm tra request thực tế và cấu hình resolver |
| JavaScript không đọc được ID response | Thiếu Access-Control-Expose-Headers | Kiểm tra CORS response |
| Preflight bị từ chối | Header chưa được cho phép trong Access-Control-Allow-Headers | Kiểm tra allowedHeaders và OPTIONS |
| Logout xong client vẫn gửi ID cũ | Client không xử lý header rỗng hoặc response logout không được nhận | Kiểm tra expireSession response và logic xóa ID |
| Sau login bị mất phiên | Client chưa thay ID cũ bằng ID mới sau session fixation protection | Kiểm tra header response ngay sau xác thực |
| Chỉ một số instance tìm thấy phiên | Repository, namespace hoặc resolver giữa các instance không đồng nhất | Kiểm tra cấu hình chia sẻ và proxy header forwarding |
| Server nhận header nhưng xác thực thất bại | ID sai/hết hạn hoặc SecurityContext không được khôi phục | Kiểm tra repository, filter order và Spring Security |

Khi điều tra, hãy quan sát cả hai chiều HTTP. Một response có header session ID không chứng minh client đã gửi lại đúng giá trị; một request có header cũng không chứng minh repository còn bản ghi phiên tương ứng.

## 12. Kiểm thử end-to-end

Nên kiểm thử luồng trao đổi đầy đủ thay vì chỉ kiểm tra bean resolver được tạo.

1. Gửi request không có session header đến endpoint tạo phiên.
2. Xác nhận response trả về session ID trong đúng header.
3. Gửi request thứ hai với session ID đó.
4. Xác nhận server đọc được thuộc tính đã lưu ở request đầu tiên.
5. Gửi một ID ngẫu nhiên không hợp lệ và xác nhận không được truy cập tài nguyên yêu cầu xác thực.
6. Đăng nhập, kiểm tra session ID có thay đổi theo chiến lược session fixation hay không, rồi gửi request tiếp theo bằng ID mới.
7. Logout và xác nhận response gửi header rỗng theo resolver, client xóa ID và server không còn khôi phục phiên cũ.
8. Với client cross-origin, kiểm tra preflight, allowedHeaders và exposedHeaders.
9. Với nhiều instance, tạo phiên ở A rồi dùng cùng header gọi B.
10. Kiểm tra log, trace và proxy để bảo đảm session ID không bị ghi lại.

Có thể dùng MockMvc cho kiểm thử nhanh các request/response header. Với CORS, reverse proxy, load balancer và nhiều instance, nên có kiểm thử tích hợp qua hạ tầng gần với môi trường triển khai.

## 13. Khi nào nên chọn header thay cho cookie?

| Tình huống | Gợi ý |
|---|---|
| Trình duyệt truyền thống, muốn cookie HttpOnly và tự động gửi cookie | Cookie resolver thường đơn giản hơn |
| Ứng dụng di động tự quản lý credential | Header resolver có thể phù hợp |
| API client không có cookie jar hoặc không muốn quản lý cookie | Header resolver là lựa chọn trực tiếp |
| SPA cần JavaScript chủ động quản lý session ID | Header resolver dùng được nhưng cần đánh giá rủi ro XSS và CORS |
| Nhiều loại client cùng dùng một backend | Cần quy ước resolver thống nhất hoặc resolver kết hợp được thiết kế rõ ràng |
| Hệ thống stateless dùng JWT | Không cần dùng HeaderHttpSessionIdResolver chỉ để vận chuyển JWT |

Chọn header không làm session an toàn hơn một cách tự động. Quyết định phụ thuộc khả năng quản lý credential của client, mô hình CORS, rủi ro XSS/CSRF, chính sách cookie và yêu cầu vận hành.

## Kết luận

HeaderHttpSessionIdResolver cho phép Spring Session nhận session ID từ HTTP request header và gửi ID về client qua response header. Factory xAuthToken() dùng header X-Auth-Token; factory header(...) cho phép chọn tên riêng. Client phải đọc ID từ response, gửi lại trong request tiếp theo và xóa ID khi nhận thông báo hết hạn. Resolver chỉ đảm nhiệm vận chuyển định danh; repository vẫn lưu phiên, còn Spring Security vẫn chịu trách nhiệm xác thực và phân quyền. Khi triển khai, cần bảo vệ session ID như credential nhạy cảm, cấu hình CORS đúng, cập nhật ID sau session fixation protection và kiểm thử luồng qua nhiều instance.
