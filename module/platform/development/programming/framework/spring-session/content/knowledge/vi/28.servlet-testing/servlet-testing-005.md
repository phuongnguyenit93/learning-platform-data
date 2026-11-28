# Kiểm tra thuộc tính, đổi định danh, invalidate và cookie không hợp lệ

## Mục tiêu bài học

Spring Session thay cách lưu trữ HttpSession để phiên có thể tồn tại ngoài bộ nhớ của một instance Spring, chẳng hạn trong Redis hoặc JDBC. Khi kiểm thử Servlet session, cần xác minh dữ liệu thuộc tính được lưu và khôi phục đúng, định danh phiên được đổi đúng thời điểm, thao tác invalidate làm phiên mất hiệu lực và cookie không hợp lệ không thể khôi phục trạng thái xác thực.

Một test chỉ kiểm tra response thành công chưa đủ. Cần theo dõi Session ID qua các request, gửi lại cookie từ client, kiểm tra trạng thái sau khi đổi ID hoặc invalidate và xác minh hành vi khi client gửi một ID không tồn tại hoặc đã hết hạn.

Sau bài học, bạn có thể:

- Kiểm thử tạo session, đọc, cập nhật, liệt kê và xóa thuộc tính.
- Xác minh thuộc tính còn nguyên sau request kế tiếp và sau khi đổi Session ID.
- Phân biệt đổi ID bằng Servlet API với invalidate rồi tạo session mới.
- Kiểm thử Spring Security session fixation protection ở luồng đăng nhập.
- Xác minh ID cũ không còn tải được session sau khi đổi định danh.
- Kiểm thử invalidate, cookie hết hạn và repository không còn phiên hoạt động.
- Kiểm tra cookie thiếu, ID không tồn tại, ID hết hạn và giá trị cookie sai định dạng.
- Phân biệt hành vi của Servlet container, Spring Session và Spring Security.
- Viết integration test bằng MockMvc với filter chain thật và repository Redis/JDBC.
- Tránh log Session ID, cookie hoặc thuộc tính nhạy cảm trong test và CI.

## 1. Các lớp cần kiểm thử

Một request Servlet đi qua nhiều thành phần trước khi controller nhận được HttpSession:

1. Client gửi cookie hoặc header chứa Session ID.
2. Spring Session filter phân giải định danh và tải session từ repository.
3. Request wrapper cung cấp giao diện HttpSession cho ứng dụng.
4. Spring Security có thể tải SecurityContext từ session.
5. Controller hoặc service đọc và thay đổi thuộc tính.
6. Khi request kết thúc, Spring Session lưu thay đổi và cập nhật cookie nếu cần.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as SessionRepositoryFilter
    participant R as Redis/JDBC Repository
    participant S as Spring Security
    participant A as Servlet Controller

    C->>F: Request + SESSION cookie
    F->>R: Tìm session theo ID
    R-->>F: Session hoặc không tìm thấy
    F->>S: Request đã bọc HttpSession
    S->>A: Chuyển request
    A->>A: Đọc/đặt/xóa thuộc tính
    A-->>S: Response
    S-->>F: Hoàn tất filter chain
    F->>R: Lưu hoặc xóa session
    F-->>C: Response + Set-Cookie nếu cần
~~~

Mỗi lớp có thể tạo ra lỗi khác nhau:

| Lớp | Điều cần xác minh |
|---|---|
| Servlet API | Hành vi getSession, getAttribute, setAttribute, removeAttribute, changeSessionId, invalidate |
| Spring Session | Đọc/ghi repository, cập nhật ID, xóa phiên, expiration |
| Spring Security | Khôi phục SecurityContext, session fixation protection, logout |
| Cookie resolver | Tên cookie, giá trị, Path, Domain, Secure, HttpOnly, SameSite |
| Client/test harness | Giữ cookie giữa request và gửi lại đúng cookie mới nhất |

Test tốt cần biết đang xác minh lớp nào. Ví dụ, cookie bị trình duyệt từ chối vì Secure khác với server từ chối một Session ID không tồn tại.

## 2. Chuẩn bị môi trường kiểm thử Servlet

Để kiểm tra tích hợp Spring Session, hãy dùng application context có cấu hình Servlet filter thật. Với Spring Boot, một cấu hình phổ biến là:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class SessionServletIntegrationTests {
    // Tests use the real application filter chain.
}
~~~

**@SpringBootTest** nạp application context đầy đủ. **@AutoConfigureMockMvc** tạo MockMvc với các filter đã được đăng ký trong ứng dụng, bao gồm Spring Session và Spring Security nếu cấu hình hiện diện.

Nếu dùng **@WebMvcTest**, auto-configuration của repository hoặc filter có thể không đầy đủ. Khi đó test có thể vô tình chạy với mock session thay vì Spring Session repository. Hãy kiểm tra filter chain và dependency thực tế.

Không nên dùng **MockMvcBuilders.standaloneSetup** cho bài test cần xác minh Spring Session nếu chưa đăng ký đúng filter. Standalone setup không tự bảo đảm toàn bộ filter của ứng dụng được nạp.

### Dùng repository thật khi kiểm tra persistence

Có thể dùng Redis test instance hoặc Testcontainers cho Redis; với JDBC, dùng database cùng hệ quản trị production hoặc Testcontainers. Cả hai cách giúp test kiểm tra serialization, expiration và thao tác repository thật.

Một test với mock repository chỉ chứng minh logic mock. Nó không chứng minh Spring Session Redis/JDBC thực sự lưu thuộc tính, đổi ID hoặc xóa session đúng cách.

## 3. Tạo một session và kiểm tra thuộc tính

Servlet API cho phép tạo session khi cần bằng **request.getSession(true)** hoặc **request.getSession()**. Sau đó, ứng dụng có thể đặt thuộc tính:

~~~java
HttpSession session = request.getSession(true);

session.setAttribute("theme", "dark");
session.setAttribute("locale", "vi");
session.setAttribute("cartCount", 3);
~~~

Một test nên xác minh:

- Session được tạo khi request yêu cầu tạo.
- Response phát cookie Session ID theo resolver đang cấu hình.
- Các thuộc tính có đúng tên và giá trị.
- Các thuộc tính có thể đọc được trong request tiếp theo.
- Session ID không bị thay đổi ngoài ý muốn.
- Thuộc tính không xuất hiện trong session khác.

Ví dụ, nếu dùng cookie resolver mặc định của Spring Session Servlet, cookie thường có tên **SESSION**. Tuy nhiên, ứng dụng có thể cấu hình tên khác. Test nên dùng tên cookie đã được cấu hình trong ứng dụng thay vì hard-code mặc định ở nhiều nơi.

### Kiểm tra đọc thuộc tính

Trong request tiếp theo, gửi lại cookie nhận được từ response tạo session:

~~~http
GET /test/session/attributes HTTP/1.1
Host: localhost
Cookie: SESSION=<session-id>
~~~

Controller đọc thuộc tính từ session hiện tại. Test xác minh **theme=dark**, **locale=vi** và **cartCount=3**. Nếu request không gửi cookie, server sẽ không khôi phục session đó.

### Phân biệt getSession và getSession(false)

- **getSession()** tương đương yêu cầu lấy session hiện tại hoặc tạo mới nếu chưa có.
- **getSession(true)** cho phép tạo mới nếu chưa có.
- **getSession(false)** chỉ trả session hiện tại nếu đã tồn tại; không tạo session mới.

Khi kiểm thử cookie không hợp lệ hoặc session đã invalidate, dùng **getSession(false)** để quan sát xem server có tải được session hay không. Nếu controller gọi **getSession()**, nó có thể tạo một session mới và làm test hiểu nhầm rằng cookie cũ vẫn hợp lệ.

## 4. Kiểm tra setAttribute, removeAttribute và tên thuộc tính

Các thao tác thuộc tính cần được kiểm thử độc lập:

~~~java
session.setAttribute("theme", "dark");
session.setAttribute("cartCount", 3);

Object theme = session.getAttribute("theme");

session.removeAttribute("theme");
~~~

Sau khi request hoàn tất, request tiếp theo phải thấy **cartCount** còn tồn tại và **theme** đã bị xóa.

Một số quy tắc cần lưu ý:

- Tên thuộc tính phân biệt chính xác theo chuỗi tên mà ứng dụng sử dụng.
- **getAttribute(name)** trả về null nếu không có thuộc tính.
- **removeAttribute(name)** xóa thuộc tính khỏi session.
- Theo Servlet API, đặt thuộc tính với giá trị null có hiệu ứng loại bỏ thuộc tính.
- **getAttributeNames()** liệt kê các tên thuộc tính đang có.

Không nên chỉ kiểm tra object trong cùng request, vì dữ liệu vẫn có thể nằm trong object đang ở bộ nhớ của request mà chưa được repository lưu đúng.

### Kiểm tra qua request độc lập

Một test theo hướng end-to-end:

1. Gửi request tạo session và đặt nhiều thuộc tính.
2. Lấy cookie từ response.
3. Gửi request thứ hai với cookie đó để đọc thuộc tính.
4. Gửi request thứ ba để xóa một thuộc tính.
5. Gửi request thứ tư để xác minh thuộc tính đã mất và thuộc tính khác vẫn còn.

Mỗi request phải hoàn tất trước khi gửi request kế tiếp trong test tuần tự. Khi kiểm tra cạnh tranh, cần một test riêng dùng request song song và điều khiển thứ tự thực thi.

## 5. Kiểm tra thuộc tính có thể serialize

Spring Session Redis/JDBC thường cần chuyển thuộc tính session sang dạng lưu trữ. Object không tương thích serializer có thể khiến request lỗi khi lưu hoặc khi tải lại từ repository.

Với JDK serialization, object thường cần triển khai **Serializable** và các object lồng bên trong cũng cần tương thích:

~~~java
public class CartSnapshot implements Serializable {

    private static final long serialVersionUID = 1L;

    private final int itemCount;

    public CartSnapshot(int itemCount) {
        this.itemCount = itemCount;
    }

    public int getItemCount() {
        return itemCount;
    }
}
~~~

Ví dụ lưu thuộc tính:

~~~java
session.setAttribute("cart", new CartSnapshot(3));
~~~

Không phải mọi ứng dụng đều dùng JDK serialization. Redis có thể được cấu hình serializer khác; JDBC repository cũng có cơ chế chuyển đổi dữ liệu tùy phiên bản. Test phải dùng đúng serializer production.

Nên có các trường hợp:

- Giá trị đơn giản như String, Integer, Boolean.
- DTO ứng dụng được hỗ trợ bởi serializer.
- Object lồng nhau.
- Giá trị không thể serialize.
- Dữ liệu session cũ được tạo từ version ứng dụng trước.

Nếu serialization thất bại, test phải phát hiện rõ lỗi và xác minh ứng dụng không âm thầm coi dữ liệu chưa lưu là đã lưu.

Không lưu password, access token thô, dữ liệu thanh toán hoặc object lớn không cần thiết trong session.

## 6. Kiểm tra đổi định danh bằng Servlet API

Servlet API cung cấp **HttpServletRequest.changeSessionId()** để thay Session ID của session hiện tại mà không cần tạo một session object mới.

Ví dụ:

~~~java
HttpSession session = request.getSession(false);

if (session == null) {
    throw new IllegalStateException("No active session");
}

String oldId = session.getId();
String newId = request.changeSessionId();
~~~

Với Spring Session Servlet, request wrapper chuyển thao tác đổi ID đến repository. Response resolver sẽ phát định danh mới theo cấu hình cookie/header.

Một test cần xác minh:

1. Tạo session và lưu thuộc tính.
2. Ghi nhận Session ID cũ.
3. Gọi **changeSessionId()**.
4. Xác minh ID mới khác ID cũ.
5. Lấy cookie mới từ response.
6. Gửi request tiếp theo bằng cookie mới.
7. Xác minh thuộc tính cũ vẫn được giữ.
8. Gửi request mới bằng ID cũ.
9. Xác minh ID cũ không còn tải được phiên đã đổi định danh.

### Đổi ID giữ lại session attributes

**changeSessionId()** thay định danh của session hiện tại. Nó không có ý nghĩa tương đương với invalidate rồi tạo một session hoàn toàn mới.

Các thuộc tính của session hiện tại thường được giữ lại. Vì vậy, sau khi đổi ID, request mới với cookie mới vẫn có thể đọc **theme**, **locale** hoặc dữ liệu session hợp lệ đã lưu trước đó.

Test cần xác minh cả hai điều: ID đã thay đổi và thuộc tính cần giữ vẫn còn.

### Cookie cũ sau khi đổi ID

Sau khi đổi ID, client phải dùng cookie mới. Nếu client tiếp tục gửi ID cũ trong request mới, repository không nên khôi phục session đã xác thực bằng ID đó.

Một request đã bắt đầu và tải session trước thời điểm đổi ID là tình huống khác: request đang chạy có thể vẫn giữ snapshot đã tải. Test ID cũ cần gửi request mới sau khi thao tác đổi ID đã hoàn tất, không dùng request đang chạy dở làm bằng chứng.

## 7. Kiểm tra session fixation protection khi đăng nhập

Trong ứng dụng dùng Spring Security, session fixation protection thường được áp dụng sau khi authentication thành công. Chiến lược **changeSessionId** thay định danh session hiện tại theo Servlet API.

Luồng test nên mô phỏng:

1. Client truy cập trang login hoặc endpoint tạo session ẩn danh.
2. Ghi nhận cookie trước xác thực nếu session đã được tạo.
3. Gửi credential hợp lệ.
4. Lấy cookie từ response login.
5. Xác minh Session ID mới khác ID trước login khi chiến lược đổi ID được áp dụng.
6. Dùng cookie mới truy cập endpoint yêu cầu authentication.
7. Dùng cookie cũ gửi request mới và xác minh không truy cập được phiên đã xác thực.

Nếu ứng dụng dùng **migrateSession** hoặc **newSession**, hành vi về session object và thuộc tính có thể khác. Test phải khớp với chiến lược đang cấu hình.

Không giả định mọi login flow đều tạo session trước đăng nhập. Một số cấu hình chỉ tạo session khi cần. Nếu không có cookie trước login, test không thể so sánh ID cũ/mới; khi đó hãy kiểm tra session sau login được tạo và lưu đúng.

### Phân biệt đổi ID và tạo session mới

| Hành vi | Định danh | Thuộc tính |
|---|---|---|
| changeSessionId | Thay ID của session hiện tại | Giữ thuộc tính hiện tại |
| migrateSession | Tạo session mới và migrate thuộc tính theo chiến lược | Chuyển các thuộc tính cũ |
| newSession | Tạo session mới | Không chuyển thuộc tính ứng dụng cũ theo hành vi chiến lược |
| invalidate rồi getSession(true) | Hủy session cũ, sau đó tạo session mới nếu cần | Session mới bắt đầu với tập thuộc tính mới |

Test cần ghi rõ chiến lược nào đang được kiểm tra để không nhầm một hành vi hợp lệ với lỗi.

## 8. Kiểm tra invalidate

Servlet API **HttpSession.invalidate()** kết thúc session hiện tại. Sau khi invalidate:

- Session không còn được dùng cho request mới.
- Các thuộc tính session bị loại bỏ.
- Những thao tác tiếp tục sử dụng session object đã invalidate có thể ném **IllegalStateException**.
- Spring Session repository phải xóa hoặc đánh dấu session không còn hợp lệ theo implementation.
- Cookie resolver có thể phát Set-Cookie để xóa cookie phía client.

Ví dụ:

~~~java
HttpSession session = request.getSession(false);

if (session != null) {
    session.invalidate();
}
~~~

Không gọi **invalidate()** rồi tiếp tục đọc thuộc tính từ session object đó như thể session còn hoạt động.

### Kiểm tra repository sau invalidate

Một test nên:

1. Tạo session và lưu thuộc tính.
2. Ghi nhận cookie Session ID.
3. Gửi request invalidate bằng cookie đó.
4. Xác minh response yêu cầu xóa cookie.
5. Gửi request mới với ID cũ.
6. Xác minh session không còn được tải.
7. Xác minh endpoint được bảo vệ không khôi phục Authentication.

Nếu test chỉ kiểm tra cookie đã bị xóa ở client, nó chưa chứng minh dữ liệu server đã bị vô hiệu hóa. Giữ một bản sao ID cũ trong biến test để gửi lại sau logout/invalidate.

Bản sao ID chỉ tồn tại trong bộ nhớ test, không ghi vào log hoặc báo cáo.

### Kiểm tra session object sau invalidate

Trong một test unit hoặc controller test có kiểm soát, có thể xác minh thao tác trên session object đã invalidate gây **IllegalStateException** theo Servlet API. Không nên dùng điều này làm assertion duy nhất cho Spring Session repository vì nó không chứng minh request tiếp theo không thể tải lại session.

## 9. Kiểm tra cookie không hợp lệ

Cookie session chứa một định danh do server cấp. Server không được tin rằng mọi giá trị client gửi đều đại diện cho một session hợp lệ.

Các trường hợp cần kiểm tra:

| Trường hợp | Ý nghĩa |
|---|---|
| Không có cookie | Request không cung cấp Session ID |
| Cookie có ID ngẫu nhiên không tồn tại | ID hợp lệ về cú pháp nhưng repository không tìm thấy |
| Cookie chứa ID đã hết hạn | Session không còn hợp lệ theo expiration policy |
| Cookie cũ sau changeSessionId | Định danh cũ không còn trỏ đến phiên hiện hành |
| Cookie cũ sau invalidate | Phiên đã bị hủy |
| Cookie sai định dạng | Container, proxy hoặc resolver có thể từ chối trước khi repository tra cứu |
| Cookie giả mạo chữ ký | Chỉ áp dụng nếu ứng dụng dùng resolver/cơ chế ký cookie riêng |

Cách kiểm thử ổn định nhất là gửi một ID ngẫu nhiên nhưng có cú pháp cookie hợp lệ và chắc chắn không tồn tại trong repository. Không phụ thuộc vào việc mọi Servlet container xử lý cùng một chuỗi ký tự sai định dạng giống nhau.

### Unknown ID không được tạo thành session đã xác thực

Nếu request gửi cookie có ID không tồn tại, **getSession(false)** phải trả null. Nếu controller gọi **getSession(true)**, Servlet API có thể tạo một session mới; đó không có nghĩa ID cũ đã được chấp nhận.

Vì vậy, endpoint kiểm tra trong test nên quan sát session mà không tự tạo mới:

~~~java
HttpSession session = request.getSession(false);

if (session == null) {
    return Map.of("exists", false);
}

return Map.of(
        "exists", true,
        "theme", String.valueOf(session.getAttribute("theme"))
);
~~~

Với endpoint bảo vệ bởi Spring Security, request dùng ID không tồn tại phải được xử lý như request chưa xác thực: thường trả 401 cho API hoặc redirect đến login cho web form, tùy cấu hình entry point.

Không chấp nhận 200 với dữ liệu của người dùng trước đó.

## 10. Cookie sai định dạng và khác biệt Servlet container

Có hai loại lỗi khác nhau:

1. Giá trị cookie được parse thành công nhưng không tương ứng với session nào.
2. Header Cookie sai cú pháp hoặc chứa ký tự không hợp lệ khiến proxy/container từ chối request.

Loại thứ nhất phù hợp để kiểm thử logic Spring Session. Loại thứ hai có thể cho kết quả khác nhau giữa Tomcat, Jetty, Undertow, reverse proxy và phiên bản HTTP stack.

Không viết một assertion chung rằng mọi cookie chứa ký tự đặc biệt đều phải tạo 401. Một số container có thể từ chối request với 400 trước khi Spring Session filter chạy.

Nếu cần kiểm tra parser behavior:

- Chạy test trên đúng Servlet container production.
- Gửi raw Cookie header qua HTTP client phù hợp.
- Xác minh request có đến ứng dụng hay bị proxy/container chặn.
- Kiểm tra log và response status ở tầng tiếp nhận.
- Không dùng chuỗi control character hoặc payload gây lỗi parser ngoài phạm vi test an toàn.

Với kiểm thử repository, ưu tiên unknown ID có cú pháp hợp lệ.

## 11. Cookie attributes và Set-Cookie

Spring Session có thể cấu hình cookie thông qua **CookieSerializer**, ví dụ dùng **DefaultCookieSerializer**.

Ví dụ cấu hình:

~~~java
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
~~~

Tên cookie và các thuộc tính cần khớp policy ứng dụng. Cấu hình **Secure=true** phù hợp với production HTTPS; test local HTTP có thể không gửi cookie Secure theo cách trình duyệt thật hoạt động. Có thể kiểm tra header Set-Cookie riêng và chạy một test HTTPS để xác minh client behavior.

Các thuộc tính thường cần xác minh:

- **Name**: đúng tên resolver mong đợi.
- **Path**: cookie chỉ được gửi trong phạm vi path cần thiết.
- **Domain**: chỉ đặt khi cần chia sẻ cookie giữa host phù hợp.
- **Secure**: chỉ gửi qua HTTPS.
- **HttpOnly**: ngăn JavaScript đọc cookie qua API cookie thông thường.
- **SameSite**: kiểm soát một số ngữ cảnh gửi cookie cross-site.
- **Max-Age/Expires**: chính sách vòng đời cookie nếu được cấu hình.

Không nên kiểm tra header bằng một chuỗi cố định quá chặt nếu thứ tự attribute hoặc cách format thay đổi giữa Servlet container. Parse Set-Cookie hoặc kiểm tra từng thuộc tính cần thiết.

### Cookie khi đổi ID

Sau **changeSessionId()**, response cần cung cấp định danh mới. Test kiểm tra:

- Cookie mới có tên đúng.
- Giá trị khác ID cũ.
- Path/Domain/Secure/HttpOnly/SameSite vẫn theo cấu hình.
- Client gửi cookie mới trong request tiếp theo.

Nếu header Set-Cookie không xuất hiện như kỳ vọng, kiểm tra resolver và cách response được commit. Đừng giả định cookie mới luôn xuất hiện ngay tại dòng code gọi changeSessionId; Spring Session có thể ghi cookie trong quá trình commit response.

### Cookie khi invalidate

Khi session bị invalidate, resolver thường gửi cookie hết hạn với cùng tên và phạm vi cookie. Test có thể kiểm tra **Max-Age=0** hoặc Expires trong quá khứ theo format resolver.

Phạm vi cookie khi xóa phải khớp cookie đã tạo. Nếu cookie ban đầu có Path hoặc Domain khác, một Set-Cookie xóa với phạm vi không khớp có thể không xóa cookie trong browser.

Dù cookie phía client còn tồn tại do response bị mất, server vẫn phải từ chối ID đã invalidate khi repository không còn session hợp lệ.

## 12. Ví dụ test fixture chỉ dùng trong môi trường test

Một controller test-only có thể tạo, đọc, đổi ID và invalidate session. Không expose endpoint chẩn đoán này trong production.

~~~java
@RestController
@RequestMapping("/__test/session")
@Profile("test")
class SessionProbeController {

    @PostMapping("/attributes")
    Map<String, Object> create(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute("theme", "dark");
        session.setAttribute("locale", "vi");
        session.setAttribute("cartCount", 3);

        return Map.of(
                "exists", true,
                "id", session.getId()
        );
    }

    @GetMapping("/attributes")
    Map<String, Object> read(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            return Map.of("exists", false);
        }

        return Map.of(
                "exists", true,
                "theme", String.valueOf(session.getAttribute("theme")),
                "locale", String.valueOf(session.getAttribute("locale")),
                "cartCount", session.getAttribute("cartCount")
        );
    }

    @PostMapping("/change-id")
    Map<String, String> changeId(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            throw new IllegalStateException("No active session");
        }

        String oldId = session.getId();
        String newId = request.changeSessionId();

        return Map.of("oldId", oldId, "newId", newId);
    }

    @PostMapping("/invalidate")
    Map<String, Boolean> invalidate(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            return Map.of("invalidated", false);
        }

        session.invalidate();
        return Map.of("invalidated", true);
    }
}
~~~

Fixture trên nhằm minh họa các thao tác Servlet API. Trong ứng dụng thực tế:

- Chỉ bật controller bằng profile test.
- Không trả Session ID trong endpoint production.
- Có thể cho phép route test trong security configuration test profile.
- Nếu CSRF đang bật, các POST test cần gửi CSRF token hợp lệ.
- Cookie name phải lấy theo cấu hình ứng dụng.
- Không dùng fixture này thay cho test đăng nhập thật với Spring Security.

## 13. Ví dụ MockMvc kiểm tra thuộc tính và đổi ID

Với MockMvc đã nạp Spring Session filter:

~~~java
@Test
void attributesSurviveSessionIdChange() throws Exception {
    MvcResult created = mockMvc.perform(
            post("/__test/session/attributes").with(csrf())
        )
        .andExpect(status().isOk())
        .andReturn();

    Cookie oldCookie = created.getResponse().getCookie("SESSION");
    assertThat(oldCookie).isNotNull();

    MvcResult changed = mockMvc.perform(
            post("/__test/session/change-id")
                .cookie(oldCookie)
                .with(csrf())
        )
        .andExpect(status().isOk())
        .andReturn();

    Cookie newCookie = changed.getResponse().getCookie("SESSION");
    assertThat(newCookie).isNotNull();
    assertThat(newCookie.getValue()).isNotEqualTo(oldCookie.getValue());

    mockMvc.perform(
            get("/__test/session/attributes").cookie(newCookie)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.exists").value(true))
        .andExpect(jsonPath("$.theme").value("dark"))
        .andExpect(jsonPath("$.locale").value("vi"))
        .andExpect(jsonPath("$.cartCount").value(3));
}
~~~

Ví dụ giả định cookie tên SESSION và response phát cookie mới khi tạo/đổi session. Nếu ứng dụng dùng tên khác hoặc header resolver, điều chỉnh helper theo cấu hình đó.

Không phải mọi cấu hình test đều tự gửi cookie như trình duyệt. Test phải chủ động lấy cookie từ response và gắn vào request tiếp theo.

### Xác minh ID cũ không còn hoạt động

Sau khi đổi ID, gửi request mới bằng cookie cũ:

~~~java
mockMvc.perform(
        get("/__test/session/attributes").cookie(oldCookie)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.exists").value(false));
~~~

Endpoint probe dùng **getSession(false)** nên không tạo session mới khi ID cũ không còn hợp lệ. Nếu test dùng endpoint có gọi **getSession()**, nó có thể tạo session mới và assertion cần phân biệt session mới với session cũ.

## 14. Ví dụ MockMvc kiểm tra invalidate

Luồng test:

1. Tạo session.
2. Giữ cookie session hợp lệ.
3. Gửi POST invalidate với CSRF token nếu được yêu cầu.
4. Kiểm tra response cookie hết hạn.
5. Gửi request tiếp theo với bản sao cookie cũ.
6. Xác minh server không tải lại session.

~~~java
@Test
void invalidatedSessionCannotBeLoadedAgain() throws Exception {
    MvcResult created = mockMvc.perform(
            post("/__test/session/attributes").with(csrf())
        )
        .andExpect(status().isOk())
        .andReturn();

    Cookie oldCookie = created.getResponse().getCookie("SESSION");
    assertThat(oldCookie).isNotNull();

    MvcResult invalidated = mockMvc.perform(
            post("/__test/session/invalidate")
                .cookie(oldCookie)
                .with(csrf())
        )
        .andExpect(status().isOk())
        .andReturn();

    String setCookie = invalidated.getResponse()
            .getHeader("Set-Cookie");

    assertThat(setCookie).contains("Max-Age=0");

    mockMvc.perform(
            get("/__test/session/attributes").cookie(oldCookie)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.exists").value(false));
}
~~~

Đây là khung minh họa. Cookie serializer hoặc container có thể format expiration theo cách khác; trong test hoàn chỉnh nên parse header và xác minh cookie cùng name/path được hết hạn thay vì phụ thuộc nguyên văn một chuỗi nếu implementation khác.

Điều quan trọng là request mới dùng ID cũ không tải được session. Cookie expiration chỉ là tín hiệu để client xóa cookie; repository invalidation mới là điều server phải bảo đảm.

## 15. Kiểm tra cookie không tồn tại và ID không tồn tại

Test không cookie:

~~~java
mockMvc.perform(get("/__test/session/attributes"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.exists").value(false));
~~~

Test unknown ID:

~~~java
Cookie unknown = new Cookie("SESSION", "unknown-session-id-123");

mockMvc.perform(
        get("/__test/session/attributes").cookie(unknown)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.exists").value(false));
~~~

Giá trị **unknown-session-id-123** chỉ là ví dụ có cú pháp cookie thông thường và không được tạo trong repository test. Trong test thực tế, tạo một chuỗi ngẫu nhiên chắc chắn chưa tồn tại.

Không dùng ID của một session khác làm unknown ID vì nó có thể là session hợp lệ và gây nhiễm chéo test.

### Kiểm tra endpoint bảo vệ

Nếu có API yêu cầu authentication, gửi unknown ID đến API đó:

~~~java
mockMvc.perform(
        get("/api/me").cookie(unknown)
    )
    .andExpect(status().isUnauthorized());
~~~

Assertion 401 phù hợp với API dùng authentication entry point trả unauthorized. Ứng dụng form login có thể redirect 302 đến trang login. Hãy xác minh đúng policy của security chain.

Không tắt authorization chỉ để test endpoint trả 200. Một cookie không hợp lệ phải được xử lý như request chưa xác thực.

## 16. Kiểm tra session hết hạn

Session có thể hết hạn theo idle timeout hoặc TTL repository. Khi hết hạn, request mới dùng cookie cũ không được khôi phục trạng thái session đã hết hiệu lực.

Để test ổn định:

- Cấu hình timeout ngắn trong profile test.
- Tạo session và lưu một thuộc tính đánh dấu.
- Chờ expiration theo cơ chế test có kiểm soát hoặc dùng clock/test support nếu implementation hỗ trợ.
- Gửi request mới bằng cookie cũ.
- Xác minh **getSession(false)** không trả session hoạt động.
- Với endpoint bảo vệ, xác minh request cần xác thực lại.

Không dùng sleep dài tùy tiện trong CI nếu có thể tránh. TTL thực tế và cleanup scheduler có thể chạy bất đồng bộ. Repository có thể kiểm tra expiration ngay khi tải dù key vật lý chưa được cleanup.

Không nhầm cookie còn tồn tại trong client với session còn hợp lệ ở server. Cookie chỉ mang định danh; server/repository quyết định định danh đó còn ánh xạ tới session hợp lệ hay không.

## 17. Kiểm tra thuộc tính sau nhiều request và nhiều instance

Nếu dùng Redis/JDBC, test nên xác minh thuộc tính sau request đi đến instance khác:

1. Tạo session và đặt thuộc tính tại instance A.
2. Lấy cookie từ response A.
3. Gửi request đến instance B bằng cookie đó.
4. Đọc và xác minh thuộc tính.
5. Cập nhật thuộc tính tại B.
6. Gửi request mới đến A và xác minh giá trị theo chính sách save/flush mode.
7. Đổi ID hoặc invalidate tại một node.
8. Gửi ID cũ đến node còn lại và xác minh trạng thái.

Trong test nhiều node, không để sticky session tự động giữ mọi request ở A. Gọi trực tiếp từng cổng hoặc ghi node identifier trong test fixture để chứng minh request thực sự đi đến đúng instance.

Cùng Session ID không đồng nghĩa hai request dùng chung object Java. Mỗi request có thể tải một snapshot riêng; các bài test cập nhật đồng thời cần xử lý race condition riêng.

## 18. Những lỗi thường gặp trong test

**Dùng MockHttpSession rồi kết luận Redis/JDBC đã lưu dữ liệu.**  
MockHttpSession không tự chứng minh Spring Session repository được gọi. Dùng application context và filter thật với repository test.

**Không gửi cookie giữa các request.**  
Mỗi request không có cookie có thể tạo session mới hoặc trở thành request ẩn danh. Lưu cookie từ response và gửi lại rõ ràng.

**Dùng getSession() trong endpoint kiểm tra invalid ID.**  
Lệnh này có thể tạo session mới, làm test tưởng ID cũ còn hợp lệ. Dùng getSession(false).

**Chỉ kiểm tra cookie bị xóa sau invalidate.**  
Cookie bị xóa phía client không chứng minh repository đã xóa session. Gửi lại bản sao ID cũ để xác minh server từ chối.

**Kiểm tra ID mới nhưng quên thuộc tính.**  
Đổi ID phải được xác minh cả định danh lẫn dữ liệu cần giữ. Đọc thuộc tính qua request tiếp theo bằng cookie mới.

**Kiểm tra ID cũ ngay trong request đang chạy.**  
Request đã tải session trước khi ID đổi có thể còn snapshot. Hãy gửi request mới sau khi thao tác đổi ID hoàn tất.

**Giả định mọi cookie sai định dạng đều trả 401.**  
Container hoặc proxy có thể trả 400 trước khi Spring Session xử lý. Dùng unknown ID hợp lệ về cú pháp cho test repository.

**Dùng cookie name mặc định trong mọi test.**  
Ứng dụng có thể đổi tên cookie. Đọc từ cấu hình hoặc dùng helper tập trung.

**Test chỉ chạy với mock repository.**  
Mock không xác minh serialization, TTL, key namespace hoặc invalidation thật. Bổ sung integration test với Redis/JDBC.

**Log cookie hoặc Session ID để debug.**  
Đây là dữ liệu có thể dùng để truy cập session. Chỉ log trạng thái và correlation ID đã được che.

## 19. Checklist kiểm thử trước khi phát hành

### Thuộc tính

- Tạo session bằng request phù hợp.
- Đọc lại thuộc tính trong request mới.
- Kiểm tra set, remove và danh sách attribute names.
- Kiểm tra object serialize được.
- Kiểm tra object không tương thích serializer bị phát hiện.
- Kiểm tra thuộc tính sau khi đổi ID.
- Kiểm tra thuộc tính không bị rò sang session khác.

### Định danh và invalidate

- Đổi ID bằng Servlet API.
- Xác minh ID mới khác ID cũ.
- Xác minh cookie/header mới được gửi.
- Xác minh thuộc tính cần giữ vẫn tồn tại.
- Xác minh ID cũ không tải được session trong request mới.
- Invalidate session.
- Xác minh cookie hết hạn theo resolver.
- Xác minh repository không còn trả session hợp lệ.
- Xác minh logout và security context không còn hiệu lực.

### Cookie

- Không có cookie.
- Unknown Session ID.
- ID đã hết hạn.
- ID cũ sau đổi ID.
- ID cũ sau invalidate.
- Cookie name, Path, Domain và SameSite.
- Secure và HttpOnly.
- Cookie sai cú pháp theo đúng Servlet container production.
- Custom signed/encrypted cookie nếu ứng dụng có dùng.

### Môi trường

- Spring Session filter được nạp trong test.
- Spring Security filter chain được nạp.
- Repository Redis/JDBC thật được dùng cho integration test.
- Test chạy qua nhiều instance khi triển khai nhiều nút.
- Không phụ thuộc sticky session ngoài ý muốn.
- Không ghi Session ID hoặc cookie vào log/CI artifact.

## 20. Tự kiểm tra

1. Vì sao test thuộc tính cần gửi cookie qua nhiều request?
2. Khác biệt giữa getSession() và getSession(false) là gì?
3. Vì sao test invalid cookie nên dùng unknown ID có cú pháp hợp lệ?
4. changeSessionId() giữ lại điều gì và thay đổi điều gì?
5. Vì sao cần kiểm tra thuộc tính sau khi đổi ID?
6. Vì sao request mới dùng ID cũ cần bị từ chối sau khi đổi ID?
7. invalidate() có ý nghĩa gì đối với session repository?
8. Vì sao xóa cookie phía client chưa chứng minh session bị vô hiệu hóa phía server?
9. Session fixation protection được kiểm tra như thế nào trong login flow?
10. Vì sao MockHttpSession không đủ để chứng minh Redis/JDBC persistence?
11. Cookie Secure có thể gây khác biệt gì giữa test HTTP và production HTTPS?
12. Vì sao cookie sai cú pháp có thể tạo 400 thay vì 401?
13. Làm thế nào kiểm tra session hết hạn mà không phụ thuộc sleep dài?
14. Vì sao không được log Session ID hoặc cookie trong CI?

### Gợi ý trả lời

1. Vì mỗi request là một lần tải session riêng; cookie là cách client chỉ định session cần khôi phục.
2. getSession() tạo session nếu chưa có; getSession(false) chỉ trả session hiện tại và không tạo mới.
3. Vì parser behavior với cookie malformed khác nhau giữa container/proxy; unknown ID hợp lệ kiểm tra được repository ổn định hơn.
4. Nó thay Session ID của session hiện tại và giữ các thuộc tính hiện có theo semantics của Servlet/Spring Session.
5. Để chứng minh dữ liệu cần giữ vẫn được tải qua repository bằng định danh mới.
6. Vì định danh cũ không còn đại diện cho session đã đổi ID; request mới không được khôi phục trạng thái cũ.
7. Session bị kết thúc, thuộc tính không còn được dùng và repository phải làm cho ID đó không còn tải được như phiên hợp lệ.
8. Client có thể xóa cookie nhưng server vẫn còn session; cần gửi lại bản sao ID cũ và xác minh repository không khôi phục session.
9. Tạo session trước login nếu có, đăng nhập, xác minh ID mới, truy cập bằng ID mới và từ chối ID cũ.
10. MockHttpSession có thể bỏ qua SessionRepositoryFilter và repository thật.
11. Client/browser thường không gửi Secure cookie qua HTTP; cần kiểm tra thuộc tính Set-Cookie và chạy HTTPS test phù hợp.
12. Servlet container hoặc reverse proxy có thể từ chối header trước khi Spring Session xử lý.
13. Dùng timeout ngắn, clock/test support nếu có và xác minh repository khi tải; tránh dựa vào cleanup vật lý hoàn tất tức thì.
14. Vì Session ID có thể là credential bearer cho phiên đang hoạt động.

## Kết luận

Kiểm thử Spring Session Servlet cần xác minh cả dữ liệu, định danh và vòng đời cookie. Thuộc tính phải được lưu và đọc lại qua request mới; changeSessionId phải tạo định danh mới nhưng giữ dữ liệu cần thiết; invalidate phải làm session không còn tải được và cookie được hết hạn theo resolver. Cookie không có, unknown ID, ID hết hạn hoặc ID cũ sau đổi/invalidate phải được xử lý như session không hợp lệ.

Dùng MockMvc với application context và filter chain thật cho kiểm thử Servlet, sau đó bổ sung integration test với Redis/JDBC repository thực tế. Luôn dùng getSession(false) khi quan sát session không tồn tại, giữ bản sao ID cũ trong bộ nhớ test để kiểm tra server-side invalidation và phân biệt lỗi parser của container với ID không có trong repository. Không log Session ID hoặc cookie. Những assertion này giúp phát hiện lỗi mà test chỉ kiểm tra status code hoặc response cookie sẽ bỏ sót.

