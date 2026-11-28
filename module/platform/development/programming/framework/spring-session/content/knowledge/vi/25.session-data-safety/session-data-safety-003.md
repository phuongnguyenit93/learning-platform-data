# Chống session fixation, đánh cắp phiên và sử dụng lại định danh đã thu hồi

Spring Session lưu trạng thái phiên phía máy chủ trong Redis, JDBC hoặc một kho dữ liệu được hỗ trợ, để nhiều instance có thể khôi phục cùng phiên. Client thường chỉ giữ session ID trong cookie hoặc header. Ai chiếm được ID hợp lệ có thể thử sử dụng phiên dưới danh tính của người dùng cho đến khi phiên hết hạn hoặc bị thu hồi.

Ba rủi ro cần phân biệt:

- **Session fixation:** kẻ tấn công khiến nạn nhân sử dụng một session ID mà kẻ tấn công đã biết; nạn nhân đăng nhập nhưng ID không được đổi, khiến kẻ tấn công có thể dùng lại ID đó.
- **Session hijacking:** kẻ tấn công lấy được ID của một phiên đang hoạt động, ví dụ qua XSS, truyền tải không an toàn, log hoặc thiết bị bị xâm nhập.
- **Replay định danh đã thu hồi:** client hoặc kẻ tấn công gửi lại cookie/session ID cũ sau logout, hết hạn, đổi ID hoặc thu hồi phiên.

Biện pháp trọng tâm là đổi ID sau xác thực hoặc nâng quyền, bảo vệ ID khi truyền và lưu trữ, invalidate phiên ở phía server khi kết thúc, và kiểm thử rằng ID cũ không thể khôi phục phiên đã bị thu hồi. Spring Session quản lý lưu trữ và vòng đời session; Spring Security hỗ trợ bảo vệ session fixation trong luồng xác thực.

## 1. Session ID là bearer credential

Session ID là giá trị định danh để server tìm session tương ứng. Nếu client gửi ID hợp lệ, server có thể khôi phục session cùng các thuộc tính và SecurityContext đã lưu. Vì vậy, quyền sử dụng session gắn với việc sở hữu ID.

Không coi session ID là thông tin vô hại chỉ vì nó không phải mật khẩu. Người có ID có thể được server nhận diện như người dùng của phiên đó. Cần bảo vệ ID tương tự credential:

- Chỉ truyền qua HTTPS.
- Không đưa vào URL, query string hoặc fragment.
- Không ghi vào application log, access log, trace, analytics hoặc error report.
- Không gửi qua email, chat hoặc telemetry.
- Không lưu ở nơi JavaScript dễ đọc nếu có thể dùng cookie HttpOnly.
- Không tự tạo ID từ username, timestamp, số thứ tự hoặc dữ liệu đoán được.

Spring Session và Servlet container chịu trách nhiệm tạo ID theo implementation được cấu hình. Không tự thay thế bằng ID có entropy thấp. Nếu tùy chỉnh ID generator, phải dùng nguồn ngẫu nhiên mật mã phù hợp, đủ entropy và kiểm thử khả năng va chạm cũng như tương thích giữa các instance.

Session ID không phải bằng chứng độc lập rằng người dùng vẫn được phép truy cập. Server còn phải kiểm tra session còn tồn tại, chưa hết hạn, chưa bị thu hồi và SecurityContext/authorities vẫn hợp lệ theo chính sách hiện tại.

## 2. Session fixation xảy ra như thế nào?

Trong một cuộc tấn công fixation, kẻ tấn công tìm cách khiến browser của nạn nhân sử dụng một session ID mà kẻ tấn công đã biết. Nạn nhân đăng nhập trong session đó. Nếu ứng dụng giữ nguyên ID qua bước xác thực, kẻ tấn công có thể gửi lại ID đã biết và tiếp tục dùng phiên đã được xác thực.

~~~mermaid
sequenceDiagram
    participant A as Attacker
    participant V as Victim browser
    participant S as Application
    A->>V: Cài hoặc ép browser dùng session ID đã biết
    V->>S: Request với session ID đó
    S-->>V: Session chưa xác thực
    V->>S: Đăng nhập bằng credential hợp lệ
    Note over S: Nếu không đổi ID, session cũ trở thành session đã xác thực
    A->>S: Gửi lại session ID đã biết
    S-->>A: Có thể khôi phục phiên đã xác thực
~~~

Điểm bảo vệ là thay đổi định danh ở ranh giới xác thực. Sau khi đăng nhập thành công, ID trước xác thực không được tiếp tục dùng để khôi phục phiên đã xác thực. Việc đổi ID phải được thực hiện phía server bằng session fixation protection của Spring Security hoặc API session tương ứng.

## 3. Bật session fixation protection trong Spring Security Servlet

Với ứng dụng Servlet, Spring Security cung cấp session fixation protection trong cấu hình session management. Trên Servlet 3.1 trở lên, chiến lược mặc định thường là đổi session ID bằng API của container khi xác thực thành công.

Có thể khai báo tường minh:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/login", "/assets/**").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                    .sessionFixation(fixation -> fixation.changeSessionId()))
            .build();
}
~~~

Các chiến lược thường gặp:

| Chiến lược | Hành vi | Khi cân nhắc |
|---|---|---|
| changeSessionId | Đổi ID của session hiện tại, giữ session và attributes | Lựa chọn phổ biến trên Servlet container hỗ trợ Servlet 3.1+ |
| migrateSession | Tạo session mới và chuyển attributes từ session cũ | Tương thích với một số môi trường/container cũ hoặc yêu cầu migration |
| newSession | Tạo session mới, không chuyển attributes ứng dụng thông thường | Khi muốn bắt đầu một session sạch sau xác thực |
| none | Không áp dụng session fixation protection | Tránh dùng trừ khi có lý do đặc biệt và biện pháp thay thế đã được chứng minh |

Với Spring Session, request được bọc để các thao tác session đi qua repository. Khi Spring Security gọi chiến lược đổi ID, Spring Session phải cập nhật định danh trong repository để ID cũ không còn trỏ đến session đã xác thực. Không tự viết logic chỉ đổi cookie ở client; nếu repository phía server vẫn ánh xạ ID cũ đến session, lỗ hổng vẫn còn.

Không tắt session fixation protection chỉ vì ứng dụng dùng Redis/JDBC thay cho session container mặc định. Spring Session vẫn cần phối hợp với Spring Security để thay đổi định danh trong kho dùng chung.

## 4. Đổi ID khi nâng quyền hoặc xác thực lại

Đăng nhập không phải ranh giới duy nhất có thể làm thay đổi mức độ tin cậy. Ứng dụng có thể cần đổi session ID sau:

- Xác thực đa yếu tố thành công.
- Người dùng thực hiện step-up authentication trước thao tác nhạy cảm.
- Chuyển từ tài khoản ẩn danh sang tài khoản đã đăng nhập.
- Đổi tài khoản trong cùng browser.
- Hoàn tất quy trình xác nhận danh tính hoặc khôi phục tài khoản.
- Nâng quyền quản trị theo một luồng đã được xác thực bổ sung.

Với Servlet API, session ID có thể được đổi bằng request API:

~~~java
request.changeSessionId();
~~~

Chỉ gọi trong luồng server-side đã xác thực và sau khi kiểm tra container/Spring Session đang quản lý request đó. Nếu Spring Security đã thực hiện fixation protection trong authentication flow, không cần gọi thêm một lần tùy tiện. Với custom authentication filter, phải phối hợp session authentication strategy, SecurityContextRepository và chính sách lưu context của phiên bản Spring Security đang dùng.

Với WebFlux, WebSession có API reactive:

~~~java
return exchange.getSession()
        .flatMap(session -> session.changeSessionId())
        .thenReturn(ResponseEntity.noContent().build());
~~~

Publisher đổi ID phải được nối vào reactive chain và hoàn tất trước khi response được gửi. Không gọi subscribe riêng rồi trả response ngay, vì client có thể nhận response trước khi repository cập nhật định danh.

## 5. Session hijacking: những đường rò rỉ thường gặp

Kẻ tấn công có thể chiếm session ID qua nhiều đường:

| Nguồn rò rỉ | Rủi ro | Kiểm soát |
|---|---|---|
| HTTP không mã hóa | Người trên đường truyền đọc cookie/header | HTTPS toàn bộ, redirect HTTP sang HTTPS và HSTS |
| XSS | JavaScript độc hại đọc dữ liệu hoặc thực hiện request trong browser | Output encoding, CSP, kiểm soát script, cookie HttpOnly |
| Log hoặc tracing | ID bị sao chép vào hệ thống quan sát có nhiều người truy cập | Redact cookie/header và không log session ID |
| URL/query string | ID lọt vào history, referrer, proxy log và analytics | Chỉ truyền qua cookie hoặc header chuyên dụng |
| Thiết bị dùng chung | Cookie còn tồn tại sau khi người dùng rời thiết bị | Logout, xóa cookie, timeout và chính sách thiết bị |
| Extension/malware | Phần mềm trên máy người dùng đọc hoặc sử dụng phiên | Bảo vệ endpoint, step-up authentication và thu hồi phiên |
| Backup/export Redis hoặc database | Dữ liệu session bị lộ từ bản sao lưu | Mã hóa, giới hạn quyền, quản lý secret và retention |

Cookie HttpOnly ngăn JavaScript đọc trực tiếp giá trị cookie qua API trình duyệt, nhưng không ngăn XSS thực hiện request thay mặt người dùng khi browser tự gửi cookie. Vì vậy, HttpOnly không thay thế chống XSS, CSRF hoặc kiểm tra quyền phía server.

## 6. Bảo vệ cookie chứa session ID

Với browser client, cookie thường là cách phù hợp để mang session ID. Có thể cấu hình Spring Session thông qua CookieSerializer:

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

Tên cookie trong ví dụ phải khớp với cấu hình xóa cookie khi logout và với mọi instance trong cụm. Chọn SameSite theo luồng điều hướng thực tế. Nếu cần cookie cross-site, có thể phải dùng SameSite=None cùng Secure; khi đó cần đánh giá CSRF và CORS cẩn thận.

| Thuộc tính | Tác dụng |
|---|---|
| Secure | Browser chỉ gửi cookie qua kết nối HTTPS |
| HttpOnly | JavaScript không đọc trực tiếp giá trị cookie |
| SameSite | Hạn chế một số request cross-site tự động mang cookie |
| Path | Giới hạn đường dẫn mà browser gửi cookie |
| Domain | Quyết định host/subdomain nhận cookie |
| Max-Age/Expires | Quy định thời gian cookie tồn tại ở client |

Không đặt Domain quá rộng cho toàn bộ subdomain nếu không cần. Cookie trùng tên nhưng khác Path/Domain có thể gây hành vi khó đoán khi xóa hoặc thay đổi session. Cookie lifetime cũng khác server-side session timeout: cookie còn ở browser không có nghĩa session trong repository vẫn tồn tại.

Khi ứng dụng chạy sau reverse proxy/load balancer, cấu hình forwarded headers và cách xác định request HTTPS phải chính xác. Nếu server hiểu nhầm request bên ngoài là HTTP, cookie Secure hoặc redirect có thể hoạt động sai. Không tin forwarded header từ mọi nguồn; chỉ chấp nhận header do proxy tin cậy ghi đè.

## 7. Cookie hay header resolver?

Spring Session dùng HttpSessionIdResolver để đọc và ghi session ID. Cookie resolver phù hợp với browser; header resolver thường được dùng cho client API có cơ chế quản lý credential riêng.

Không truyền session ID trong URL vì URL thường xuất hiện trong browser history, access log, referrer và hệ thống giám sát. Nếu dùng header, không lưu ID trong query string và phải bảo vệ storage phía client. Đặc biệt, lưu bearer session ID trong localStorage làm tăng khả năng bị lấy cắp khi có XSS.

Không cho phép cùng một request mang nhiều session ID mâu thuẫn mà không có quy tắc rõ ràng. Các proxy, gateway và middleware cần chuyển tiếp đúng cookie/header đã chọn, đồng thời redact giá trị khỏi log.

## 8. Logout phải thu hồi phía server

Xóa cookie ở browser chỉ làm client quên định danh. Nếu session vẫn tồn tại trong Redis/JDBC, một bản sao cookie bị đánh cắp vẫn có thể được gửi lại. Logout cần invalidate session phía server để repository không còn khôi phục được ID đó.

Ví dụ cấu hình logout Servlet:

~~~java
http.logout(logout -> logout
        .invalidateHttpSession(true)
        .clearAuthentication(true)
        .deleteCookies("SESSION"));
~~~

Tên cookie SESSION phải khớp CookieSerializer đang dùng. Nếu cookie có Path hoặc Domain tùy chỉnh, thao tác xóa phải phát cookie hết hạn với thuộc tính tương ứng để browser loại đúng cookie. Spring Security logout handler thực hiện việc kết thúc session và xóa context; Spring Session phản ánh invalidate vào repository dùng chung.

Không chỉ gọi JavaScript xóa cookie rồi coi logout đã hoàn tất. Cũng không chỉ xóa SecurityContext trong bộ nhớ của request mà bỏ session repository. Sau logout, thử gửi lại chính session ID cũ bằng một HTTP client độc lập; server phải coi phiên đó là không tồn tại hoặc không hợp lệ.

Với WebFlux, WebSession.invalidate() trả Mono<Void> và cần được nối vào chuỗi response. Với Spring Security WebFlux, ưu tiên logout handler được framework cấu hình và kiểm tra rằng WebSession bị invalidate ở phía repository.

## 9. Sử dụng lại định danh đã thu hồi

Một session ID đã bị invalidate, hết hạn hoặc thay bằng ID mới phải không còn khôi phục được phiên cũ. Việc client vẫn giữ cookie không làm ID sống lại.

Các trường hợp cần kiểm tra:

- Sau logout, gửi lại cookie cũ.
- Sau session expiration, gửi lại cookie cũ.
- Sau session fixation protection, gửi ID trước đăng nhập.
- Sau đổi ID khi nâng quyền, gửi ID cũ.
- Sau thu hồi tất cả phiên của một principal, gửi lại ID của từng phiên.
- Sau khi đổi mật khẩu hoặc khóa tài khoản, gửi ID được tạo trước sự kiện đó.

Với Spring Session JDBC, repository kiểm tra thời điểm hết hạn khi tìm session và xóa phiên đã hết hạn theo luồng truy cập; cleanup job định kỳ dọn dữ liệu vật lý còn sót. Với Redis, key TTL và repository logic quyết định khả năng khôi phục. Không được nhầm dữ liệu còn tồn tại tạm thời trong bảng/index phụ với một session còn hiệu lực.

Khi triển khai nhiều instance, tất cả node phải dùng cùng repository/namespace và chính sách resolver. Nếu một node đọc từ cache hoặc replica có dữ liệu cũ sau khi thu hồi, có thể có khoảng thời gian node đó nhìn thấy session cũ. Với yêu cầu bảo mật cao, session lookup và kiểm tra thu hồi phải có consistency phù hợp; tránh đọc trạng thái xác thực từ replica eventual-consistent nếu điều đó cho phép dùng lại ID đã bị thu hồi.

## 10. Xử lý request đồng thời khi logout hoặc đổi ID

Một request có thể đã khôi phục session trước khi request khác thực hiện logout hoặc đổi ID. Request đầu tiên có thể vẫn đang chạy trong khi session bị invalidate. Không nên giả định thao tác thu hồi sẽ dừng ngay mọi request đã bắt đầu.

Với thao tác nhạy cảm, kiểm tra trạng thái tài khoản, quyền hoặc session version ở service boundary trước khi commit giao dịch. Nếu cần thu hồi ngay trên toàn hệ thống, có thể dùng credential/session version hoặc revocation marker trong kho dữ liệu có consistency phù hợp. Mọi request phải so sánh version được xác thực với version hiện hành theo chính sách.

Không giữ một bản session object trong cache cục bộ lâu hơn request và không tự lưu lại session snapshot cũ sau khi logout. Kiểm thử race giữa request đang xử lý và request logout/rotate ID. Xác định rõ giao dịch nào đã được phép hoàn tất trước thời điểm thu hồi và giao dịch nào phải bị từ chối.

## 11. Session fixation protection không thay thế bảo vệ chống hijacking

Đổi ID sau đăng nhập ngăn kẻ tấn công dùng một ID đã biết trước xác thực để chiếm phiên sau đăng nhập. Nhưng nếu ID mới bị đánh cắp sau khi đăng nhập, kẻ tấn công vẫn có thể thử dùng nó. Do đó, cần kết hợp:

- Session fixation protection.
- HTTPS và cookie Secure.
- HttpOnly và SameSite phù hợp.
- Chống XSS và CSRF.
- Timeout không hoạt động và thời hạn tuyệt đối nếu cần.
- Logout/invalidate server-side.
- Thu hồi session khi đổi mật khẩu, khóa tài khoản hoặc phát hiện rủi ro.
- Step-up authentication cho thao tác nhạy cảm.
- Giám sát đăng nhập bất thường và giới hạn truy cập.

Không dựa vào việc đổi ID liên tục để thay thế kiểm soát XSS hoặc TLS. Rotation làm giảm giá trị của ID cũ nhưng không ngăn kẻ tấn công sử dụng ID mới nếu họ đã chiếm được nó.

## 12. Thời hạn không hoạt động và thời hạn tuyệt đối

Session inactivity timeout giới hạn thời gian không có hoạt động được ghi nhận. Nó hữu ích để thu hồi phiên bỏ quên, nhưng không giới hạn tổng thời gian tồn tại nếu người dùng liên tục hoạt động.

Với hệ thống có yêu cầu bảo mật cao, có thể cần absolute session lifetime: sau một khoảng thời gian kể từ lúc xác thực, người dùng phải xác thực lại dù session vẫn có hoạt động. Cần lưu thời điểm xác thực ban đầu ở server-side session hoặc một kho đáng tin cậy và kiểm tra ở mỗi request theo chính sách.

Không dùng timestamp do client gửi làm thời điểm xác thực. Nếu session được tạo lại hoặc ID được đổi, giữ hoặc cập nhật mốc absolute lifetime theo quy tắc rõ ràng; tránh vô tình reset thời hạn tuyệt đối chỉ vì một thao tác refresh.

## 13. Thu hồi nhiều session khi tài khoản thay đổi trạng thái

Khi người dùng đổi mật khẩu, bị khóa, mất quyền hoặc yêu cầu logout mọi thiết bị, ứng dụng cần xác định các session của principal và invalidate chúng. Repository indexed hỗ trợ tra cứu theo principal khi được cấu hình và populate index đúng cách.

Quy trình có thể gồm:

1. Ghi thay đổi tài khoản hoặc credential version vào nguồn dữ liệu chuẩn.
2. Tìm các session gắn với principal bằng repository index hoặc session registry.
3. Invalidate/xóa từng session.
4. Phát sự kiện thu hồi nếu các thành phần khác cần đóng WebSocket hoặc dọn trạng thái phụ.
5. Kiểm tra request mới không thể khôi phục session cũ.

Nếu số lượng session lớn, thực hiện thu hồi theo batch và theo dõi tiến độ. Trong thời gian thu hồi chưa hoàn tất, credential/session version có thể được dùng như một hàng rào bổ sung ở mỗi request. Không chỉ dựa vào một job nền chạy sau vài phút nếu yêu cầu là khóa tài khoản ngay lập tức.

## 14. Bảo vệ kho session và dữ liệu backup

Redis/JDBC chứa session data và có thể chứa SecurityContext, principal, CSRF token hoặc dữ liệu cá nhân. Kẻ có quyền ghi vào kho session có thể cố tạo hoặc sửa trạng thái phiên. Bảo vệ backend:

- Đặt Redis/database trong mạng riêng, không mở trực tiếp ra Internet.
- Dùng TLS cho kết nối khi môi trường yêu cầu.
- Cấp ACL/role tối thiểu cho tài khoản ứng dụng.
- Tách quyền runtime và quyền quản trị/migration.
- Quản lý secret qua secret manager, không commit password vào source.
- Mã hóa backup và giới hạn người có quyền restore/export.
- Giới hạn quyền truy cập console, shell và công cụ quản trị.
- Theo dõi thay đổi bất thường ở keyspace/bảng session.

Không xem mã hóa cookie là giải pháp thay thế bảo vệ repository. Cookie chỉ mang định danh; dữ liệu session thực tế vẫn cần được bảo vệ tại backend.

## 15. Kiểm thử session fixation và replay

Kiểm thử cần dùng HTTP client có thể giữ và gửi lại cookie theo chủ đích. Browser test đơn thuần đôi khi tự thay cookie mới nên không chứng minh ID cũ đã bị thu hồi.

| Kịch bản | Cách thực hiện | Kết quả cần xác nhận |
|---|---|---|
| Fixation qua login | Tạo session trước login, ghi lại ID A, đăng nhập, lấy ID B | ID thay đổi theo chính sách; A không khôi phục được context đã xác thực |
| Session attributes | Đặt dữ liệu tạm trước login rồi xác thực | Attributes được giữ hoặc loại bỏ theo chiến lược change/migrate/new đã chọn |
| Logout replay | Đăng nhập, sao chép ID, logout, gửi lại ID cũ bằng client khác | Server từ chối hoặc coi session là không tồn tại |
| Expiration replay | Tạo session timeout ngắn, đợi hết hạn, gửi lại ID | Session không được khôi phục |
| ID rotation | Gọi step-up authentication hoặc đổi ID | ID cũ không còn truy cập phiên mới |
| Nhiều instance | Tạo session ở A, logout/rotate ở B, replay ID cũ vào A | Tất cả node đều từ chối ID cũ |
| Cookie flags | Kiểm tra Set-Cookie | Có Secure, HttpOnly, SameSite, Path và Domain phù hợp |
| Cookie deletion | Logout với cookie Path/Domain tùy chỉnh | Browser nhận cookie hết hạn đúng thuộc tính |
| Request đồng thời | Giữ một request đang chạy, logout từ request khác | Hành vi commit/rollback tuân thủ chính sách thu hồi |
| Đổi mật khẩu | Thu hồi phiên hiện tại và các phiên khác | Không session cũ nào tiếp tục xác thực |
| Header resolver | Gửi ID cũ qua header sau revoke | Resolver không khôi phục session đã xóa |
| Replica/cache | Thu hồi ở primary rồi đọc qua node khác | Không có đường đọc stale cho phép replay theo yêu cầu bảo mật |

Ví dụ kiểm thử Servlet với MockMvc có thể xác minh response sau login và logout, nhưng để chứng minh replay ID cũ cần lấy đúng cookie trước và sau xác thực rồi gửi lại thủ công. Khi dùng Spring Session Redis/JDBC, integration test nên dùng backend cùng loại với production và ít nhất hai application instance hoặc context.

## 16. Ví dụ kiểm thử replay bằng HTTP client

Một kịch bản test khái niệm:

~~~text
1. Gửi GET /public để server tạo session trước đăng nhập.
2. Lưu cookie session ban đầu A.
3. Gửi POST /login với credential hợp lệ và cookie A.
4. Đọc Set-Cookie mới, gọi là B.
5. Xác nhận B khác A nếu session fixation protection được bật.
6. Gửi request đã xác thực với B và xác nhận thành công.
7. Gọi POST /logout với B.
8. Gửi lại request bảo vệ bằng B trong một HTTP client mới.
9. Xác nhận request không còn Authentication của phiên cũ.
10. Gửi lại A và xác nhận A cũng không thể khôi phục phiên đã xác thực.
~~~

Không chỉ so sánh chuỗi A và B. Điều quan trọng là kiểm tra server-side: ID A không được ánh xạ tới SecurityContext đã xác thực, và ID B sau logout không được khôi phục. Cookie có thể thay đổi do nhiều lý do; repository state mới là bằng chứng về việc thu hồi.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Session ID không đổi sau login | Session fixation protection bị tắt hoặc custom auth flow bỏ qua strategy | Kiểm tra session management và authentication success flow |
| ID cũ vẫn khôi phục phiên đã đăng nhập | Chỉ đổi cookie phía client, repository vẫn giữ ánh xạ cũ | Dùng API/strategy đổi ID của server và kiểm thử repository |
| Logout xong ID cũ vẫn dùng được | Chỉ xóa cookie hoặc chỉ clear context trong request | Invalidate session server-side và xác minh bằng replay |
| Cookie không bị xóa | Tên, Path hoặc Domain khi delete không khớp cookie ban đầu | Đồng bộ CookieSerializer và logout cookie clearing |
| Cookie bị gửi qua HTTP | Thiếu Secure hoặc proxy nhận diện HTTPS sai | Bật HTTPS, Secure và cấu hình forwarded headers tin cậy |
| JavaScript đọc được cookie session | Thiếu HttpOnly | Bật HttpOnly; đồng thời sửa XSS |
| Cross-site request mang cookie ngoài ý muốn | SameSite/CSRF policy không phù hợp | Chọn SameSite và CSRF protection theo luồng thực tế |
| Một node vẫn chấp nhận session đã revoke | Node dùng store/namespace khác hoặc đọc cache/replica stale | Đồng nhất repository và kiểm tra consistency của đường đọc |
| Session sống quá lâu dù người dùng không hoạt động | Timeout quá dài hoặc heartbeat/request nền làm mới last access | Đánh giá inbound activity, inactivity timeout và absolute lifetime |
| Session cũ sống sau đổi mật khẩu | Chưa thu hồi mọi phiên hoặc chưa kiểm tra credential version | Dùng indexed lookup/revocation và kiểm tra version |

## 18. Nguyên tắc triển khai

- Bật session fixation protection và đổi ID sau xác thực; không dùng chiến lược none nếu chưa có biện pháp thay thế được chứng minh.
- Đổi ID ở các ranh giới nâng quyền hoặc step-up authentication khi chính sách yêu cầu.
- Để Spring Security/Spring Session thực hiện rotation phía server, không chỉ sửa cookie phía client.
- Bảo vệ session ID bằng HTTPS, Secure, HttpOnly, SameSite và không đưa ID vào URL/log.
- Chống XSS và CSRF; cookie flags không thay thế các biện pháp này.
- Logout phải invalidate session trong repository và xóa cookie đúng tên/Path/Domain.
- Kiểm thử phát lại ID cũ sau login, rotation, logout, expiration và revoke.
- Dùng cùng repository/namespace và đường đọc có consistency phù hợp trên mọi instance.
- Thu hồi session khi đổi mật khẩu, khóa tài khoản hoặc thay đổi quyền quan trọng.
- Xử lý request đang chạy đồng thời với logout/rotation theo chính sách rõ ràng.
- Bảo vệ Redis/JDBC, backup, secret và quyền quản trị.
- Không log session ID, cookie, token hoặc SecurityContext.

## Tài liệu tham khảo

- [Spring Security – Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Session – HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [Spring Session – Customizing the Cookie](https://docs.spring.io/spring-session/reference/configuration/common.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP Session Fixation](https://owasp.org/www-community/attacks/Session_fixation)

Spring Session cung cấp khả năng lưu và thu hồi session dùng chung; Spring Security cung cấp cơ chế bảo vệ session fixation và kiểm soát xác thực. Khi ID được đổi ở ranh giới xác thực, cookie được bảo vệ, logout invalidate ở phía server và mọi instance kiểm tra cùng trạng thái session có thẩm quyền, ID cũ không thể tiếp tục mở lại phiên đã bị thu hồi. Kiểm thử replay bằng chính ID cũ là cách xác nhận quan trọng nhất rằng các lớp bảo vệ đang hoạt động cùng nhau.
