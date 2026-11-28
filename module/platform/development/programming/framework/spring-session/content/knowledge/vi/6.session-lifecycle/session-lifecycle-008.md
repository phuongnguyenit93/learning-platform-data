# Định danh không hợp lệ, phiên không tìm thấy và cookie cũ

Trong ứng dụng dùng Spring Session, trình duyệt thường gửi một cookie chứa session ID ở mỗi request. Spring Session dùng ID đó để tìm dữ liệu phiên trong repository như Redis hoặc JDBC. Khi ID không còn trỏ tới một session hợp lệ, ứng dụng cần xử lý request như một request không có phiên hiện tại và áp dụng chính sách xác thực phù hợp.

Một cookie cũ không nhất thiết có nghĩa ứng dụng bị lỗi. Session có thể đã hết hạn ở máy chủ trong khi cookie vẫn còn trên trình duyệt; người dùng có thể mở lại một tab cũ sau khi đăng xuất; hoặc cookie có thể thuộc một phiên bản triển khai trước. Điều quan trọng là phân biệt tình huống không tìm thấy session với lỗi kết nối repository, tránh tạo session mới ngoài ý muốn và không để một ID cũ tiếp tục được dùng như bằng chứng xác thực.

## 1. Phân biệt các trạng thái của request

Có bốn tình huống thường gặp:

| Tình huống | Dấu hiệu | Cách hiểu |
|---|---|---|
| Không có session ID | Request không gửi cookie hoặc header định danh phiên | Request chưa yêu cầu một session cụ thể |
| Có ID nhưng không tìm thấy session | Cookie chứa ID, nhưng repository không trả session tương ứng | ID có thể đã hết hạn, đã bị xóa, bị thay thế hoặc thuộc namespace/repository khác |
| ID không hợp lệ ở tầng HTTP/cookie | Cookie bị hỏng định dạng, trùng tên hoặc không được gửi đúng phạm vi | Cần kiểm tra cookie resolver và cấu hình trình duyệt |
| Repository không truy cập được | Redis/JDBC phát sinh lỗi kết nối, timeout hoặc lỗi truy vấn | Đây là lỗi hạ tầng; không được coi như session đơn giản là không tồn tại |

Sự khác biệt giữa hai trường hợp ở giữa rất quan trọng. Session ID là một giá trị opaque do hệ thống quản lý. Ứng dụng không nên tự giải mã, đoán cấu trúc hoặc kiểm tra ID bằng quy tắc riêng. Repository mới là nơi xác định ID đó có trỏ tới session đang tồn tại hay không.

**Không tìm thấy session không đồng nghĩa với repository bị lỗi.** Một lần tra cứu trả về null là kết quả bình thường khi session không tồn tại hoặc đã hết hạn. Ngược lại, nếu Redis không kết nối được hoặc câu truy vấn JDBC thất bại, ứng dụng phải xử lý lỗi hạ tầng theo chính sách vận hành. Chuyển mọi lỗi repository thành trạng thái “chưa đăng nhập” có thể che giấu sự cố và tạo hành vi bảo mật khó dự đoán.

## 2. Spring Session xử lý session ID như thế nào?

Trong ứng dụng Servlet, SessionRepositoryFilter bọc request và response. Filter dùng HttpSessionIdResolver để đọc định danh phiên từ request, sau đó dùng SessionRepository để tìm session.

Với resolver dùng cookie, luồng xử lý điển hình là:

1. Trình duyệt gửi cookie phiên cùng request.
2. Spring Session đọc giá trị cookie như một session ID.
3. Repository tìm session bằng ID đó.
4. Nếu session tồn tại và chưa hết hạn, request wrapper cung cấp HttpSession tương ứng.
5. Nếu không tìm thấy, request hiện tại không có session hợp lệ tương ứng với ID đã gửi.
6. Khi ứng dụng gọi getSession() hoặc getSession(true), Servlet request wrapper có thể tạo một session mới theo yêu cầu.
7. Khi session mới được lưu, Spring Session gửi cookie chứa ID mới về trình duyệt.

Sơ đồ:

~~~mermaid
flowchart TD
    A[Request đến cùng cookie phiên] --> B[SessionRepositoryFilter]
    B --> C[HttpSessionIdResolver đọc ID]
    C --> D[SessionRepository.findById]
    D --> E{Tìm thấy session hợp lệ?}
    E -->|Có| F[Request sử dụng session hiện tại]
    E -->|Không| G[Request không có session hợp lệ]
    G --> H{Ứng dụng có yêu cầu tạo session?}
    H -->|Không| I[Tiếp tục như request chưa có session]
    H -->|Có| J[Tạo session mới]
    J --> K[Lưu session và gửi cookie ID mới]
~~~

Hai lời gọi Servlet có hành vi khác nhau:

- request.getSession(false) trả về session hiện tại nếu có; nếu không có session hợp lệ thì trả null, không tạo session mới.
- request.getSession() tương đương request.getSession(true): nếu chưa có session thì tạo một session mới.

Khi chẩn đoán cookie cũ, hãy dùng getSession(false) trước. Gọi getSession() chỉ để kiểm tra có thể tự tạo session mới, ghi dữ liệu xuống repository và làm mất dấu trạng thái ban đầu của request.

### Ví dụ kiểm tra trạng thái mà không tạo session mới

~~~java
@GetMapping("/session/status")
public ResponseEntity<String> sessionStatus(HttpServletRequest request) {
    String requestedId = request.getRequestedSessionId();
    HttpSession session = request.getSession(false);

    if (requestedId == null) {
        return ResponseEntity.ok("Request không gửi session ID");
    }

    if (!request.isRequestedSessionIdValid() || session == null) {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body("Phiên không còn hợp lệ; vui lòng đăng nhập lại");
    }

    return ResponseEntity.ok("Request có session hợp lệ");
}
~~~

Đây là endpoint minh họa cho ứng dụng yêu cầu xác thực. Với trang công khai hoặc luồng khách vãng lai, một session không tồn tại có thể chỉ cần được xem như trạng thái anonymous thay vì trả về 401. Không trả session ID trong body hoặc log; endpoint chẩn đoán chỉ nên hiển thị trạng thái đã được rút gọn.

getRequestedSessionId() cho biết request có mang định danh phiên hay không. isRequestedSessionIdValid() cho biết định danh request có tương ứng với session hợp lệ theo Servlet request hiện tại hay không. Khi dùng Spring Session, các phương thức này hoạt động trên request wrapper của Spring Session; hãy xác minh hành vi bằng integration test với repository thật của ứng dụng.

## 3. Vì sao cookie cũ vẫn được gửi?

Cookie nằm ở trình duyệt, còn session nằm ở máy chủ. Hai bên có vòng đời riêng. Trình duyệt có thể tiếp tục gửi cookie sau khi session đã bị xóa khỏi repository.

Các nguyên nhân phổ biến:

### Session hết hạn ở máy chủ trước cookie

Session có thể hết hạn theo maxInactiveInterval hoặc TTL của Redis/JDBC. Cookie vẫn còn hạn hoặc là session cookie chưa bị đóng trình duyệt. Khi trình duyệt gửi lại ID cũ, repository không còn tìm thấy session.

Đây là tình huống thường gặp nhất khi người dùng để tab mở lâu rồi quay lại. Không nên cố khôi phục dữ liệu xác thực từ cookie cũ; người dùng cần đăng nhập lại nếu endpoint yêu cầu danh tính.

### Người dùng đã đăng xuất ở tab hoặc thiết bị khác

Khi session bị invalidate hoặc bị xóa từ trang quản trị phiên, các tab khác vẫn có thể giữ cookie ID cũ trong bộ nhớ. Request tiếp theo từ tab đó sẽ gửi ID đã bị xóa.

Nếu một người dùng đăng nhập trên nhiều thiết bị, mỗi trình duyệt có thể giữ cookie của session riêng. Đăng xuất một session không nhất thiết xóa cookie trên thiết bị khác; repository phải từ chối ID đã bị xóa khi thiết bị đó gửi request sau này.

### Session ID đã được thay đổi

Sau xác thực, Spring Security có thể áp dụng session fixation protection bằng cách thay đổi session ID. Cookie cũ có thể còn trong một request đang chạy hoặc tab chưa nhận cookie mới. Chỉ ID hiện hành được repository chấp nhận; ứng dụng không nên tự duy trì một bản sao ID cũ.

### Cookie có phạm vi không còn phù hợp

Trình duyệt chỉ gửi cookie theo các thuộc tính như domain, path, secure và SameSite. Cookie có thể không được gửi khi:

- Người dùng truy cập hostname khác với domain cookie.
- Ứng dụng chuyển context path nhưng cookie path vẫn trỏ tới đường dẫn cũ.
- Cookie có thuộc tính Secure nhưng request không đi qua HTTPS theo cách trình duyệt nhận diện.
- Điều hướng cross-site không đáp ứng chính sách SameSite.
- Reverse proxy kết thúc TLS nhưng ứng dụng không nhận biết request gốc là HTTPS.
- Ứng dụng đổi tên cookie hoặc dùng một cookie name mới.

Trường hợp cookie không được gửi khác với trường hợp cookie được gửi nhưng ID không còn tồn tại. Khi không có cookie, request đơn giản là không mang session ID.

### Cookie trùng tên hoặc thuộc ứng dụng khác

Hai ứng dụng trên cùng domain có thể tạo cookie cùng tên nhưng khác path. Trình duyệt có thể gửi nhiều giá trị cùng tên. Nếu resolver chọn giá trị không phù hợp, ứng dụng có thể tra cứu nhầm ID.

Khi triển khai nhiều ứng dụng hoặc nhiều môi trường trên cùng domain, cần phối hợp cookie name, path, domain và Redis namespace/JDBC schema. Không dùng chung cookie name một cách tùy tiện giữa các ứng dụng có kho session độc lập.

## 4. Phân biệt cookie hết hạn và session hết hạn

Cookie có thể có thời hạn do trình duyệt quản lý, ví dụ Max-Age hoặc Expires. Session có thời hạn do repository quản lý. Hai giá trị này cần được thiết kế nhất quán nhưng không đồng nhất.

| Trạng thái cookie | Trạng thái session phía máy chủ | Kết quả thường gặp |
|---|---|---|
| Cookie còn được gửi | Session còn tồn tại | Request tải được session |
| Cookie còn được gửi | Session đã hết hạn/xóa | Repository không tìm thấy session; request không có session hợp lệ |
| Cookie hết hạn và không được gửi | Session còn tồn tại | Request không tham chiếu tới session đó; dữ liệu phía máy chủ có thể còn cho đến TTL/cleanup |
| Cookie bị xóa thủ công | Session còn tồn tại | Tương tự request không có ID; session cũ có thể còn trong repository |
| Cookie mới sau khi đổi ID | Session mới hợp lệ | Request dùng session mới |

Một session cookie thường không có thời hạn lưu cố định ở phía trình duyệt và bị loại bỏ khi phiên trình duyệt kết thúc. Tuy nhiên, trình duyệt có thể khôi phục phiên hoặc giữ dữ liệu qua tính năng khôi phục tab; ứng dụng không nên dựa vào việc đóng cửa sổ để kết thúc session phía máy chủ.

TTL phía máy chủ phải là ranh giới bảo mật cuối cùng. Dù cookie còn được gửi, repository vẫn phải từ chối session đã hết hạn.

## 5. Xử lý session không tìm thấy ở tầng ứng dụng

Ứng dụng cần quyết định rõ điều gì xảy ra khi request không có session hợp lệ. Quyết định phụ thuộc loại endpoint và trạng thái xác thực.

| Loại request | Cách xử lý gợi ý |
|---|---|
| Trang yêu cầu đăng nhập | Chuyển tới trang đăng nhập hoặc trả 401 |
| API yêu cầu xác thực | Trả 401 với thông báo chung, client có thể thực hiện quy trình đăng nhập lại |
| Trang công khai | Tiếp tục như anonymous; chỉ tạo session khi thật sự cần |
| Request có thao tác nghiệp vụ chưa hoàn tất | Yêu cầu xác thực lại và khôi phục luồng từ dữ liệu bền vững nếu có |
| Request dùng session cho giỏ hàng khách | Có thể tạo session mới; nếu cần khôi phục giỏ hàng, tải từ kho nghiệp vụ theo mã tham chiếu đã được xác thực |

Không nên tự động tạo một session mới cho mọi request chỉ vì cookie cũ không còn hợp lệ. Việc tạo session có thể khiến response phát cookie mới, làm tăng dữ liệu repository và gây khó phân biệt request anonymous với request vừa hết hạn. Chỉ tạo session khi chức năng thực sự cần lưu trạng thái.

### Spring Security và invalid session

Spring Security có thể cấu hình chiến lược xử lý session ID được gửi lên nhưng không còn hợp lệ. Ví dụ dùng Java DSL:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .sessionManagement(session -> session
            .invalidSessionUrl("/session-expired")
        );

    return http.build();
}
~~~

Khi dùng invalidSessionUrl, ứng dụng chuyển hướng tới URL được chỉ định. Trang đích phải được cấu hình để không tạo vòng lặp redirect và cần cho phép truy cập khi người dùng chưa xác thực.

Đối với REST API, thường phù hợp hơn khi dùng InvalidSessionStrategy hoặc entry point trả trạng thái 401 và nội dung lỗi có cấu trúc. Không nên chuyển hướng HTML cho client API nếu giao thức của API yêu cầu phản hồi JSON.

Lưu ý: Spring Security có thể phân biệt session không hợp lệ với request chưa đăng nhập dựa trên requested session ID và trạng thái request. Hãy kiểm thử cấu hình với Spring Session filter chạy trước Spring Security. Nếu filter order sai, Spring Security có thể nhìn thấy session của Servlet container thay vì session repository.

### Tránh báo phiên hết hạn sau khi đăng xuất chủ động

Một tình huống dễ gây nhầm là người dùng bấm đăng xuất, session bị invalidate nhưng trình duyệt vẫn giữ cookie cũ. Khi request tiếp theo đến trang đăng nhập, Spring Security có thể nhận ra một requested session ID không còn hợp lệ và điều hướng tới trang “phiên hết hạn”, dù người dùng vừa đăng xuất chủ động.

Giải pháp là xóa cookie đúng tên và phạm vi trong luồng logout, đồng thời kiểm tra resolver của Spring Session đã phát cookie hết hạn hay chưa. Ví dụ cấu hình Spring Security có thể chỉ rõ cookie cần xóa:

~~~java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("SESSION")
);
~~~

SESSION là tên cookie mặc định thường gặp khi dùng Spring Session với cookie resolver mặc định. Nếu ứng dụng cấu hình cookie name khác, phải xóa đúng tên đó. Domain và path của cookie xóa phải khớp với cookie đã được tạo; nếu không, trình duyệt có thể giữ lại cookie cũ.

Không gọi invalidate() một cách mù quáng khi request.getSession(false) trả về null. Servlet có thể ném IllegalStateException nếu cố thao tác trên session đã invalidate. Khi không có session hiện hành, hãy xử lý trạng thái không có session và để resolver/luồng response quản lý cookie theo cách phù hợp.

## 6. Cookie resolver và cấu hình cookie

Spring Session dùng HttpSessionIdResolver để đọc và ghi session ID. Hai kiểu thường gặp là:

- CookieHttpSessionIdResolver: đọc/ghi ID bằng cookie; phù hợp với trình duyệt truyền thống.
- HeaderHttpSessionIdResolver: đọc/ghi ID qua HTTP header; thường dùng trong API client hoặc môi trường không dùng cookie.

Với cookie resolver, DefaultCookieSerializer điều khiển cách cookie được tạo và xóa. Có thể cấu hình cookie serializer để kiểm soát tên, path, domain, Secure, HttpOnly, SameSite và thời hạn.

Ví dụ cấu hình serializer:

~~~java
@Bean
public CookieSerializer cookieSerializer() {
    DefaultCookieSerializer serializer = new DefaultCookieSerializer();
    serializer.setCookieName("SESSION");
    serializer.setCookiePath("/");
    serializer.setUseHttpOnlyCookie(true);
    serializer.setSameSite("Lax");
    return serializer;
}
~~~

Trong cấu hình thực tế, chỉ định domain khi có yêu cầu chia sẻ cookie giữa subdomain. Không đặt domain rộng hơn phạm vi cần thiết. Cookie xác thực nên bật HttpOnly để JavaScript không đọc trực tiếp được giá trị; Secure nên được bật khi chạy HTTPS. SameSite cần được chọn theo luồng điều hướng, SSO và yêu cầu cross-site của ứng dụng.

Nếu TLS kết thúc tại reverse proxy, cấu hình forwarded headers của container/framework phải đúng để ứng dụng nhận biết request gốc là HTTPS. Nếu ứng dụng nghĩ request là HTTP, cookie Secure có thể không được tạo như mong muốn. Không nên bỏ Secure chỉ để né lỗi cấu hình proxy.

Khi đổi cookie name, path hoặc domain, trình duyệt có thể giữ cookie cũ song song với cookie mới. Trong giai đoạn chuyển đổi, hãy có kế hoạch hết hạn cookie cũ với đúng thuộc tính domain/path. Tránh để hai cookie cùng tên và khác path tồn tại lâu dài.

## 7. Xử lý ID không hợp lệ và dữ liệu đầu vào đáng ngờ

Session ID là bearer credential: ai sở hữu ID hợp lệ có thể được xem như đang nắm giữ tham chiếu tới session. Vì vậy:

- Không ghi session ID nguyên vẹn vào log, trace, metric label hoặc thông báo lỗi.
- Không trả session ID trong API response chỉ để debug.
- Không tự giải mã hoặc áp đặt định dạng UUID nếu resolver/repository không quy định ID là UUID.
- Không nối ID trực tiếp vào câu SQL, key Redis hoặc đường dẫn file; dùng API repository và parameter binding.
- Không coi ID khó đoán là cơ chế phân quyền; dữ liệu vẫn phải được kiểm tra quyền ở tầng nghiệp vụ.
- Không cho phép client gửi ID của người khác rồi truy cập dữ liệu chỉ vì repository tìm thấy session.

Nếu cần điều tra, có thể log một dấu vết đã được băm bằng khóa log nội bộ hoặc mã tương quan riêng, kèm loại kết quả như missing, expired hay repository_error. Không dùng hash session ID làm nhãn metric có cardinality không giới hạn; thay vào đó đếm theo trạng thái, repository hoặc nhóm endpoint.

Một cookie bị sửa có thể dẫn tới ID không tìm thấy. Ứng dụng không cần trả về thông báo phân biệt “ID sai định dạng”, “ID không tồn tại” hay “session của người khác”. Phản hồi công khai nên chung chung để không tiết lộ thông tin về session của người dùng khác.

## 8. Phân biệt lỗi repository với session hết hạn

Đây là ranh giới quan trọng trong vận hành nhiều instance:

| Kết quả | Ví dụ | Xử lý |
|---|---|---|
| Repository trả null | ID không tồn tại hoặc session hết hạn | Coi request không có session hợp lệ; áp dụng đăng nhập lại hoặc anonymous |
| Redis timeout/connection refused | Redis không sẵn sàng hoặc mạng lỗi | Ghi nhận lỗi hạ tầng, trả lỗi phù hợp và cảnh báo vận hành |
| JDBC exception | Database mất kết nối, deadlock hoặc schema lỗi | Xử lý theo chính sách lỗi database; không giả vờ người dùng đã logout |
| Deserialize exception | Session được ghi bởi phiên bản khác hoặc dữ liệu bị hỏng | Ghi nhận lỗi dữ liệu/compatibility, xử lý có kiểm soát và điều tra nguyên nhân |
| Lỗi cookie/resolver | Cookie sai phạm vi, trùng tên hoặc không đọc được | Kiểm tra response cookie, request cookie và cấu hình serializer |

Nếu repository tạm thời không truy cập được, không nên tự tạo session anonymous rồi tiếp tục cho phép thao tác nhạy cảm. Hành vi đó có thể che giấu sự cố và tạo ra trạng thái xác thực không nhất quán giữa các instance. Với API bảo mật, trả 5xx khi kho session không khả dụng thường trung thực hơn trả 401; 401 có nghĩa request chưa được xác thực, còn 5xx biểu thị hệ thống không thể xác định trạng thái session do lỗi nội bộ.

Cũng cần phân biệt lỗi deserialize với session không tìm thấy. Session cũ có thể còn trong Redis/JDBC nhưng cấu trúc thuộc tính không tương thích với phiên bản ứng dụng hiện tại. Khi đó, repository không đơn giản trả null; thao tác đọc có thể phát sinh exception. Hãy theo dõi lỗi này trong quá trình rolling deployment và có chiến lược tương thích dữ liệu session.

## 9. Kiểm thử cookie cũ và session không tìm thấy

Kiểm thử controller đơn lẻ chưa đủ để xác nhận hành vi cookie và repository. Cần kết hợp unit test, MockMvc và integration test với Redis/JDBC khi ứng dụng dùng kho chia sẻ.

| Ca kiểm thử | Chuẩn bị | Kết quả cần xác nhận |
|---|---|---|
| Không có cookie | Gửi request không có cookie phiên | getRequestedSessionId() là null; getSession(false) không tạo session |
| Cookie hợp lệ | Tạo session, lấy cookie và gửi lại | Session attribute được đọc đúng |
| Cookie có ID không tồn tại | Gửi cookie chứa ID ngẫu nhiên/đã bị xóa | Request không có session hợp lệ; không rò rỉ ID |
| Session hết hạn ở máy chủ | Tạo session, chờ TTL hoặc giảm interval trong test | Cookie có thể còn được gửi nhưng repository không trả session |
| Đăng xuất rồi dùng tab cũ | Tạo hai request/client cùng giữ cookie, invalidate session ở client thứ nhất | Client thứ hai không thể tiếp tục dùng session đã xóa |
| Cookie sai path/domain | Gửi request đến hostname/context path khác | Xác nhận trình duyệt có gửi cookie theo phạm vi cấu hình |
| Cookie trùng tên | Tạo hai cookie cùng tên khác path | Xác định resolver nhận giá trị nào; loại bỏ cấu hình mơ hồ |
| Repository không khả dụng | Ngắt kết nối Redis/JDBC trong test môi trường | Lỗi hạ tầng được nhận diện riêng, không biến thành “session hết hạn” |
| Đổi session ID sau đăng nhập | Xác thực và kiểm tra cookie response | ID mới được dùng; ID cũ không còn cấp quyền |
| Đăng xuất | Gọi logout và kiểm tra response | Session bị invalidate/xóa và cookie đúng tên/path/domain được hết hạn |

Ví dụ kiểm thử MockMvc có thể tạo một request mang session ID không tồn tại:

~~~java
mockMvc.perform(get("/private")
        .cookie(new Cookie("SESSION", "unknown-session-id")))
    .andExpect(status().isUnauthorized());
~~~

Đây chỉ là minh họa. Kết quả thực tế phụ thuộc endpoint, cấu hình Spring Security, tên cookie và session ID resolver. Với ứng dụng dùng Spring Session, integration test cần chạy cùng filter chain và repository thật hoặc test container tương ứng; MockHttpSession đơn thuần không xác minh TTL, cookie serialization hay hành vi giữa nhiều instance.

Khi kiểm thử hết hạn, nên dùng thời hạn rất ngắn trong profile test hoặc gọi API xóa session trực tiếp thay vì chờ lâu. Với Redis, xác nhận session không còn được tìm thấy qua repository; với JDBC, xác nhận lookup không trả session hợp lệ dù job cleanup có thể chạy sau đó. Đừng chỉ kiểm tra cookie trình duyệt đã mất vì cookie và session phía máy chủ có vòng đời riêng.

## 10. Quy trình chẩn đoán khi người dùng báo bị đăng xuất

Khi người dùng báo “tôi bị đăng xuất ngẫu nhiên”, hãy thu thập tín hiệu theo thứ tự sau:

1. Xác định request có gửi cookie/session header không. Nếu không có, kiểm tra cookie name, domain, path, Secure, SameSite và context path.
2. Nếu có ID, kiểm tra repository có tìm thấy session không. Không ghi ID thô vào log.
3. Nếu repository trả null, so sánh thời điểm tạo, lần truy cập gần nhất, timeout và TTL. Kiểm tra có luồng logout hoặc thao tác quản trị xóa session không.
4. Nếu repository phát sinh exception, điều tra Redis/JDBC, mạng, pool, transaction và lỗi deserialize.
5. Kiểm tra session ID có bị thay đổi sau đăng nhập, đổi quyền hoặc session fixation protection không.
6. So sánh cấu hình cookie, namespace và serializer giữa các instance. Một node cấu hình khác có thể không đọc được session do node khác tạo.
7. Kiểm tra filter order để bảo đảm mọi instance đều chạy Spring Session trước Spring Security và các filter cần session.
8. Xác minh bằng integration test qua nhiều request, nhiều instance và nhiều trạng thái cookie.

Các metric hữu ích gồm số request không có session ID, số request có ID nhưng session không tìm thấy, số lần tạo session mới, số lần invalidate/logout, lỗi kết nối repository, lỗi deserialize và độ trễ lookup. Theo dõi theo trạng thái và instance; tránh gắn session ID vào metric label.

## 11. Nguyên tắc xử lý an toàn

Khi ID không còn hợp lệ, ứng dụng cần xem request như không có session hợp lệ. Nếu chức năng yêu cầu xác thực, hãy yêu cầu người dùng đăng nhập lại; nếu là chức năng công khai, tiếp tục theo luồng anonymous. Khi tạo session mới, chỉ lưu dữ liệu tối thiểu cần thiết và không tự khôi phục quyền hoặc trạng thái xác thực từ cookie cũ.

Cookie cũ có thể được làm sạch khi session bị invalidate hoặc khi ứng dụng chủ động phát response hết hạn cookie với đúng tên, domain và path. Tuy nhiên, không nên giả định rằng mọi lần repository trả null đều tự động xóa cookie cũ; hãy kiểm thử response của resolver trong các tình huống cụ thể. Khi tạo session mới, response có thể thay cookie bằng ID mới; khi chỉ đọc trạng thái bằng getSession(false), request có thể không tạo response cookie mới.

Cuối cùng, hãy giữ ba nguyên tắc nhất quán trong mọi instance:

- Repository là nguồn xác định session còn tồn tại hay không.
- Cookie chỉ là phương tiện gửi session ID từ client; cookie còn hạn không chứng minh session còn hiệu lực.
- Lỗi hạ tầng phải được phân biệt với session hết hạn, để hệ thống không âm thầm hạ cấp trạng thái bảo mật.

Với cách phân biệt này, Spring Session có thể xử lý an toàn các request mang cookie cũ, session đã bị xóa hoặc ID không tìm thấy, đồng thời giúp đội vận hành xác định đúng nguyên nhân khi người dùng gặp lỗi đăng nhập.

## Tài liệu tham khảo

- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [Spring Session — HttpSessionIdResolver API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/HttpSessionIdResolver.html)
- [CookieHttpSessionIdResolver Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/CookieHttpSessionIdResolver.html)
- [DefaultCookieSerializer Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/DefaultCookieSerializer.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)

