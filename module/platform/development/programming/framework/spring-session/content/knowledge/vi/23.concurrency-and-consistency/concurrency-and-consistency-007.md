# Đổi định danh, xóa và gia hạn phiên khi có yêu cầu đồng thời

Trong ứng dụng Spring Session, nhiều request có thể cùng sử dụng một HttpSession. Một request có thể đổi session ID sau khi đăng nhập, request khác đang cập nhật giỏ hàng, request thứ ba thực hiện logout và một tác vụ cleanup có thể đang xử lý phiên hết hạn. Những thao tác này có thể chồng lấn khi chúng chạy trên các thread hoặc instance khác nhau.

Spring Session cung cấp API thống nhất để tạo, tải, lưu và xóa Session, đồng thời tích hợp với Servlet HttpSession. Tuy nhiên, việc dùng một repository chia sẻ không tự làm cho mọi chuỗi thao tác trên cùng một phiên trở thành nguyên tử. Cần hiểu rõ thứ tự thao tác, khả năng của repository, và cách ứng dụng xử lý request đang bay khi một phiên bị đổi ID, thu hồi hoặc gia hạn.

Bài học tập trung vào ba thao tác có ảnh hưởng trực tiếp đến tính nhất quán: đổi định danh phiên, xóa phiên và gia hạn thời gian sống. Mục tiêu là bảo đảm session ID cũ không còn được chấp nhận sau khi xoay vòng, logout không bị request cũ làm sống lại phiên, và hoạt động hợp lệ không bị cleanup xóa nhầm.

## 1. Vì sao các thao tác session có thể chạy đồng thời?

Trình duyệt thường gửi nhiều request song song. Ví dụ, khi một trang tải dữ liệu hồ sơ, giỏ hàng và thông báo, các request có thể cùng mang một cookie SESSION. Load balancer có thể chuyển chúng đến cùng một instance hoặc nhiều instance khác nhau.

Các tình huống phổ biến:

- Hai request cùng đọc một session rồi cập nhật hai thuộc tính khác nhau.
- Request đăng nhập đổi session ID trong khi request cũ vẫn đang xử lý.
- Người dùng logout trong khi một request ghi session chưa hoàn tất.
- Request đang hoạt động gia hạn timeout đúng lúc tác vụ cleanup tìm phiên hết hạn.
- Hai request cùng gia hạn session hoặc cùng gọi invalidate.
- Một instance tải session, instance khác xóa session, rồi instance đầu tiên lưu snapshot cũ.

Luồng ví dụ:

    Request A                 Request B
       |                         |
       | findById(S1)             | findById(S1)
       |                         |
       | đổi ID thành S2          | cập nhật cart
       | save                     | save
       |                         |
       +-----------+-------------+
                   |
             Repository dùng chung

Kết quả cuối cùng phụ thuộc vào cách repository triển khai lưu thay đổi, cách nó xử lý ID và thời điểm mỗi thao tác đến kho dữ liệu. Không thể suy ra tính nguyên tử chỉ từ việc cả hai request dùng cùng một SessionRepository.

## 2. Những loại định danh cần phân biệt

Khi đổi hoặc thu hồi session, cần phân biệt session ID với các định danh nghiệp vụ khác:

| Định danh | Vai trò | Có thay đổi khi xoay vòng session ID? |
|---|---|---|
| Session ID | Client gửi qua cookie/header để server tìm phiên | Có |
| Principal/user ID | Nhận diện tài khoản đã xác thực | Không |
| Session record ID nội bộ | Khóa lưu trữ nội bộ của repository, nếu implementation có | Phụ thuộc schema/implementation |
| Device registration ID | Định danh một cài đặt ứng dụng hoặc browser profile theo nghiệp vụ | Không nhất thiết |
| Request/correlation ID | Theo dõi một request cụ thể | Mỗi request có thể khác |

Session ID là bearer credential. Người có ID còn hiệu lực có thể sử dụng phiên tương ứng. Vì vậy, khi cần thay đổi ID sau xác thực hoặc nghi ngờ lộ credential, phải bảo đảm ID cũ không còn khôi phục được phiên.

Không dùng user ID làm session ID, không đưa session ID vào URL và không ghi session ID đầy đủ vào log.

## 3. Đổi session ID trong ứng dụng Servlet

Servlet API cung cấp HttpServletRequest.changeSessionId() để thay đổi ID của session hiện tại mà không cần tạo một session mới. Spring Session tích hợp với Servlet API qua SessionRepositoryFilter, vì vậy request wrapper có thể chuyển thao tác đổi ID đến session repository.

Ví dụ:

~~~java
@PostMapping("/account/rotate-session")
public ResponseEntity<Void> rotateSession(HttpServletRequest request) {
    HttpSession session = request.getSession(false);

    if (session == null) {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
    }

    request.changeSessionId();

    return ResponseEntity.noContent().build();
}
~~~

Đoạn mã minh họa API Servlet; trong ứng dụng thực tế, việc đổi ID sau đăng nhập nên được thực hiện bởi Spring Security session fixation protection hoặc cơ chế xác thực tương ứng. Không tạo một chuỗi ngẫu nhiên rồi tự ghi đè cookie.

Sau khi ID được đổi:

- Client phải nhận session ID mới trong response.
- Request tiếp theo cần gửi ID mới.
- ID cũ không được tiếp tục khôi phục phiên đã xoay vòng.
- Các thuộc tính session cần giữ phải tiếp tục gắn với phiên mới theo semantics của repository.
- Các request đang dùng ID cũ cần được xử lý theo chính sách bảo mật của ứng dụng.

Nếu ứng dụng dùng Spring Security, hãy giữ session fixation protection được bật và xác minh chiến lược phù hợp với Servlet container và phiên bản Spring Security.

## 4. Session fixation protection và đổi ID sau xác thực

Session fixation xảy ra khi kẻ tấn công khiến nạn nhân sử dụng một session ID mà kẻ tấn công đã biết trước. Nếu ứng dụng giữ nguyên ID đó sau khi nạn nhân đăng nhập, kẻ tấn công có thể tìm cách tiếp tục dùng phiên đã được xác thực.

Spring Security có session fixation protection. Với Servlet API hiện đại, chiến lược có thể đổi session ID hiện tại; các chiến lược khác có thể tạo session mới và chuyển các thuộc tính hợp lệ.

Ví dụ cấu hình tường minh:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .sessionManagement(session -> session
            .sessionFixation(fixation -> fixation.changeSessionId())
        )
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Không cần gọi changeSessionId() thủ công trong controller sau khi Spring Security đã thực hiện session fixation protection. Đổi ID nhiều lần không cần thiết có thể gây khó khăn cho client và làm tăng khả năng response song song ghi đè cookie của nhau.

Sau đăng nhập, cần kiểm thử cookie mới thực sự được trả về và request tiếp theo dùng ID mới. Cũng cần kiểm tra các thuộc tính session cần giữ như giỏ hàng hoặc locale, cùng các thuộc tính nhạy cảm không nên được giữ qua ranh giới xác thực.

## 5. Request song song có thể tạo ra race khi xoay vòng ID

Giả sử browser gửi hai request cùng cookie S1:

1. Request A hoàn tất xác thực và đổi S1 thành S2.
2. Request B đã tải session theo S1 trước khi A đổi ID.
3. Request B tiếp tục cập nhật thuộc tính rồi lưu snapshot cũ.
4. Response A và B có thể đến browser theo thứ tự khác với thứ tự xử lý.

Có hai nhóm rủi ro:

- **Rủi ro phía repository:** request cũ có thể ghi dữ liệu sau thao tác đổi ID. Hành vi cụ thể phụ thuộc repository và cách implementation xử lý Session đã tải trước đó.
- **Rủi ro phía client:** response cũ có thể chứa Set-Cookie hoặc thông tin resolver không còn phù hợp, đến sau response đã phát ID mới.

Không giả định mọi repository đều tự động giải quyết mọi race giữa request cũ và request mới. Cần kiểm thử với implementation đang dùng và tránh phát sinh request song song trong giai đoạn đăng nhập/đổi ID nếu client có thể điều phối.

Với thao tác xác thực, có thể khóa các hành động nhạy cảm ở client cho đến khi response login hoàn tất. Ở server, bảo đảm ID cũ bị từ chối sau rotation và không để request cũ khôi phục quyền xác thực đã bị thay đổi.

## 6. Không tự sửa session ID trong kho dữ liệu

Không nên tự cập nhật cookie hoặc sửa key Redis/cột JDBC để đổi session ID. Repository có thể cần cập nhật metadata, index, expiration, thuộc tính liên quan và các cấu trúc nội bộ khác.

Với JDBC, schema có thể có khóa chính nội bộ và SESSION_ID là định danh client. Với Redis, session ID thường tham gia vào key hoặc namespace của dữ liệu session. Cách lưu cụ thể thuộc implementation.

Hãy dùng Servlet API, Spring Security hoặc API repository được hỗ trợ. Không viết SQL cập nhật SESSION_ID, không rename Redis key bằng lệnh tùy tiện và không tự phát Set-Cookie. Thao tác thủ công có thể làm dữ liệu phụ không nhất quán hoặc khiến ID cũ vẫn tồn tại.

## 7. Xóa phiên qua HttpSession và SessionRepository

Trong ứng dụng Servlet, cách thông thường để kết thúc phiên hiện tại là gọi HttpSession.invalidate() hoặc dùng logout flow của Spring Security.

Ví dụ:

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

Spring Session filter chuyển thao tác invalidate đến repository để xóa phiên. Với Spring Security, nên dùng LogoutFilter và logout handlers để đồng thời xóa SecurityContext, invalidate session, xóa cookie và chạy các bước logout bổ sung.

Khi thao tác trực tiếp với repository, có thể gọi deleteById(sessionId). Cách này phù hợp với service quản trị session hoặc tác vụ thu hồi đã xác minh quyền sở hữu. Không dùng deleteById() tùy tiện từ controller nhận session ID do client cung cấp.

deleteById() là thao tác xóa theo ID. Nếu session đã không còn, nhiều implementation xử lý như no-op; hãy xác minh hợp đồng của repository cụ thể. Ứng dụng nên thiết kế logout có thể gọi lại an toàn, nhưng vẫn phải ghi nhận kết quả và audit theo yêu cầu.

## 8. Race giữa logout và request đang xử lý

Một trong những race quan trọng nhất là logout đồng thời với một request đã tải session:

    Request A: GET /account
       |
       +--> tải session S1
       |
       +--> xử lý nghiệp vụ
       |
       +--> chuẩn bị lưu thay đổi

    Request B: POST /logout
       |
       +--> invalidate S1
       |
       +--> repository xóa S1

Nếu Request A lưu session sau khi Request B xóa, kết quả phụ thuộc semantics của repository. Một implementation có thể cập nhật lại record hoặc tạo dữ liệu mới theo cách lưu của nó; implementation khác có thể phát hiện trạng thái không còn hợp lệ. Không có bảo đảm chung rằng thao tác delete luôn thắng mọi save đang bay.

Vì vậy, logout phải được xem là thu hồi credential và quyền truy cập, không chỉ là xóa một object. Với thao tác nhạy cảm, cần có cơ chế kiểm tra trạng thái thu hồi ở server và không dựa hoàn toàn vào một snapshot session đã tải trước đó.

Các hướng thiết kế:

- Dùng session ID rotation/revocation theo API hỗ trợ.
- Với yêu cầu nghiêm ngặt, lưu trạng thái thu hồi hoặc credential version ở nguồn dữ liệu có thẩm quyền.
- Kiểm tra trạng thái tài khoản/session trước khi thực hiện side effect nhạy cảm.
- Dùng optimistic version hoặc cơ chế đồng bộ riêng nếu repository cần bảo đảm thứ tự.
- Giới hạn thời gian request và xử lý các request đã bắt đầu trước logout.
- Kiểm thử race delete/save trên đúng repository và phiên bản triển khai.

Không nên hứa với người dùng rằng logout có thể hủy ngược một thao tác đã được server chấp nhận và thực hiện trước khi thu hồi hoàn tất. Các nghiệp vụ như chuyển tiền cần có transaction và authorization riêng.

## 9. Gia hạn session là gì?

Session thường hết hạn sau một khoảng thời gian không hoạt động. Mỗi session có thời điểm truy cập gần nhất và max inactive interval. Thời điểm hết hạn logic thường được xác định từ hai giá trị này.

Trong Servlet API, có thể đặt timeout:

~~~java
HttpSession session = request.getSession();
session.setMaxInactiveInterval(30 * 60);
~~~

Giá trị tính bằng giây; 30 phút tương ứng 1800 giây. Với Spring Boot, timeout có thể được cấu hình ở property Spring Session hoặc annotation phù hợp với repository.

Gia hạn có thể diễn ra theo hai cách:

- **Sliding expiration:** request hợp lệ cập nhật lastAccessedTime; thời điểm hết hạn trượt theo hoạt động mới nhất.
- **Absolute lifetime:** phiên có tuổi thọ tối đa tính từ creationTime, không được kéo dài vô hạn chỉ vì có request liên tục.

Spring Session hỗ trợ max inactive interval. Nếu nghiệp vụ cần absolute lifetime, ứng dụng cần bổ sung policy dựa trên creationTime hoặc một mốc hết hạn tuyệt đối được lưu riêng.

## 10. Cookie Max-Age không phải server-side session TTL

Cookie session ID và dữ liệu session có hai thời hạn độc lập:

| Thành phần | Điều khiển |
|---|---|
| Cookie Max-Age/Expires | Trình duyệt giữ định danh phiên trong bao lâu |
| HttpSession maxInactiveInterval | Server xem phiên không hoạt động trong bao lâu là hết hạn |
| Redis key TTL / JDBC expiry metadata | Cơ chế lưu trữ và dọn dữ liệu của repository |
| Absolute session lifetime | Chính sách bổ sung của ứng dụng nếu cần |

Cookie còn tồn tại không có nghĩa session server còn hợp lệ. Session còn tồn tại trong kho cũng không giúp client khôi phục nếu browser đã mất cookie chứa ID.

Khi gia hạn session, hãy xác định cả timeout server và cookie policy. Không kéo dài cookie vô hạn để thay cho việc gia hạn session. Không dùng thời điểm key/row bị xóa vật lý làm nguồn quyết định duy nhất về tính hợp lệ; repository cần kiểm tra expiration logic.

## 11. Race giữa gia hạn và cleanup

Giả sử session S1 gần hết hạn:

1. Request A tải S1 khi nó còn hợp lệ.
2. Cleanup job hoặc TTL monitor xác định S1 đã hết hạn và xóa dữ liệu.
3. Request A cập nhật lastAccessedTime hoặc maxInactiveInterval.
4. Request A lưu lại session.

Nếu cleanup và save không được phối hợp nguyên tử, kết quả có thể là phiên bị xóa dù vừa có hoạt động hợp lệ, hoặc dữ liệu phiên được ghi lại sau khi đã hết hạn. Chi tiết phụ thuộc repository, cách tính expiration và cơ chế cleanup.

Một nguyên tắc an toàn là không gia hạn một session đã hết hạn chỉ vì một request cũ vẫn giữ object Session trong bộ nhớ. Trước khi chấp nhận thao tác gia hạn, cần bảo đảm session vẫn hợp lệ theo thời gian và trạng thái thu hồi hiện tại.

Đối với kho dữ liệu có TTL tự động như Redis, việc gia hạn thường cần cập nhật TTL của key cùng dữ liệu session. Với JDBC, repository lưu expiry metadata và cleanup job xóa các hàng hết hạn. Cơ chế này không giống nhau, do đó cần kiểm thử riêng.

## 12. Gia hạn khi request đang chạy lâu

Một request có thể bắt đầu khi session còn hạn nhưng xử lý lâu hơn timeout. Ví dụ người dùng gửi yêu cầu xuất báo cáo, server xử lý 40 phút trong khi session timeout là 30 phút.

Không nên mặc định một request đang chạy sẽ luôn giữ session sống. Điều đó phụ thuộc thời điểm Spring Session cập nhật lastAccessedTime, repository và filter lifecycle. Nếu request cần thao tác kéo dài, cân nhắc:

- Tách job dài thành background task có workflow ID.
- Không dựa vào HttpSession làm nguồn trạng thái lâu dài.
- Dùng credential/service authorization phù hợp cho worker.
- Khi client cần tiếp tục, yêu cầu xác thực lại nếu session đã hết hạn.
- Nếu cần heartbeat, thiết kế endpoint có giới hạn tần suất và kiểm tra quyền.

Không tạo heartbeat tự động vô hạn chỉ để tránh timeout. Điều đó làm giảm hiệu quả của idle timeout và có thể giữ session bị đánh cắp sống lâu hơn.

## 13. Hai request cùng cập nhật thuộc tính session

Một race khác xảy ra khi hai request cùng tải session và cập nhật cùng một thuộc tính:

    Ban đầu: cartCount = 1

    Request A đọc cartCount = 1
    Request B đọc cartCount = 1

    Request A ghi cartCount = 2
    Request B ghi cartCount = 2

    Kết quả cuối: cartCount = 2
    Kết quả mong muốn nếu cả hai thêm một sản phẩm: cartCount = 3

Đây là lost update. Dù repository có lưu trữ chia sẻ, phép đọc-sửa-ghi không tự trở thành atomic.

Không dùng session attribute như bộ đếm phân tán hoặc nguồn dữ liệu nghiệp vụ cần độ chính xác cao. Nếu cần cập nhật số lượng, số dư hoặc trạng thái workflow đồng thời, hãy dùng database transaction, atomic operation hoặc service chuyên dụng.

Session phù hợp hơn với trạng thái giao diện nhỏ, tùy chọn tạm thời và dữ liệu có thể chấp nhận cập nhật cuối cùng thắng nếu được thiết kế rõ.

## 14. SessionRepository không cung cấp một hợp đồng CAS chung

API SessionRepository chuẩn cung cấp create, find, save và delete. Nó không định nghĩa một phương thức compare-and-set tổng quát kiểu “chỉ lưu nếu phiên bản hiện tại vẫn là version đã đọc”.

Do đó, không nên giả định:

- Mọi repository có optimistic locking.
- Save luôn kiểm tra phiên bản cũ.
- Delete luôn thắng một save đồng thời.
- Hai thay đổi thuộc tính khác nhau luôn được merge đúng.
- Gia hạn TTL luôn nguyên tử với kiểm tra expiry.
- Mọi event expiration được phát đúng một lần.

Một implementation cụ thể có thể có cơ chế atomic update, optimistic locking hoặc transaction riêng. Hãy đọc tài liệu và kiểm tra mã nguồn đúng phiên bản trước khi dựa vào khả năng đó.

Nếu cần CAS hoặc fencing token, có thể phải xây dựng lớp điều phối nghiệp vụ hoặc repository tùy chỉnh. Không tự thêm cột version hoặc Redis script vào schema mặc định mà không có migration, kiểm thử và kế hoạch tương thích.

## 15. Chiến lược kiểm soát cập nhật đồng thời

Chọn chiến lược theo yêu cầu dữ liệu:

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Last write wins | Ghi sau cùng quyết định giá trị | Thuộc tính UI đơn giản, ít rủi ro |
| Optimistic locking | Lưu version và chỉ cập nhật nếu version chưa đổi | Dữ liệu cần phát hiện lost update |
| Pessimistic/distributed lock | Một request giữ quyền cập nhật trong khoảng ngắn | Chuỗi thao tác cần tuần tự hóa |
| Atomic store operation | Một lệnh nguyên tử ở Redis/database | Bộ đếm hoặc thay đổi đơn giản |
| Domain transaction | Cập nhật dữ liệu nghiệp vụ bằng transaction | Tiền, đơn hàng, tồn kho, trạng thái quan trọng |
| Idempotent command | Lặp lại cùng command không tạo side effect thứ hai | Retry và message redelivery |

Không dùng distributed lock cho mọi lần ghi session. Lock cần timeout, lease, xử lý chủ sở hữu chết, fencing token và quy tắc tránh deadlock. Nếu chỉ cần cập nhật một giá trị nghiệp vụ, atomic operation hoặc transaction chuyên biệt thường đơn giản và đáng tin cậy hơn.

## 16. Khác biệt cần lưu ý giữa Redis và JDBC

Redis và JDBC có cách lưu session khác nhau:

| Khía cạnh | Spring Session Redis | Spring Session JDBC |
|---|---|---|
| Dữ liệu | Key/hash hoặc cấu trúc Redis theo implementation | Hàng trong bảng session và bảng attributes |
| Hết hạn | Redis TTL và metadata expiration | Expiry metadata cùng cleanup job |
| Cập nhật | Có thể ghi delta/field theo flush/save policy | Có câu SQL cập nhật metadata và attributes |
| Xóa | Xóa key và dữ liệu phụ theo implementation | Xóa hàng cha và dữ liệu thuộc tính theo schema |
| Cạnh tranh | Phụ thuộc thao tác Redis, flush mode và repository | Phụ thuộc transaction, câu SQL, khóa và isolation |
| Quan sát | TTL, keyspace và metric Redis | Query, index, lock, transaction và cleanup metrics |

Không kết luận Redis luôn atomic hơn JDBC hoặc JDBC luôn an toàn hơn Redis. Atomicity của một lệnh đơn không tự bảo đảm chuỗi load-modify-save là nguyên tử. Với JDBC, transaction chỉ bảo vệ những thao tác tham gia cùng transaction manager và connection scope; nó không tự bao trùm request khác trên node khác.

Với Redis, một Lua script có thể gom kiểm tra version và cập nhật trong một thao tác nguyên tử, nhưng repository mặc định không nhất thiết thực hiện đúng logic nghiệp vụ mà ứng dụng cần. Nếu tùy chỉnh, phải bảo đảm tương thích với format dữ liệu Spring Session.

## 17. Không để request cũ làm sống lại phiên đã bị thu hồi

Một yêu cầu bảo mật quan trọng là session đã logout hoặc bị revoke không được sống lại chỉ vì request cũ vẫn giữ object Session.

Các biện pháp có thể áp dụng tùy mức độ yêu cầu:

- Kiểm tra session còn tồn tại và chưa hết hạn trước thao tác nhạy cảm.
- Lưu credential version hoặc session generation ở nguồn dữ liệu có thẩm quyền.
- Khi logout toàn bộ thiết bị, tăng account/session version để request cũ bị từ chối.
- Dùng tombstone/revocation record có TTL dài hơn session để nhận biết ID đã bị thu hồi.
- Dùng optimistic version hoặc atomic conditional update trong repository tùy chỉnh.
- Giới hạn request song song ở các luồng login/logout nhạy cảm.
- Kiểm tra account status và quyền hiện tại tại service layer.

Tombstone không phải tính năng mặc định của mọi Spring Session repository; đây là mẫu thiết kế bổ sung khi hệ thống cần bảo đảm revoke mạnh hơn. Cần xác định thời gian giữ tombstone, cách dọn và cách tránh ID cũ được tái sử dụng.

Đối với ứng dụng thông thường, invalidate session và repository semantics có thể đáp ứng yêu cầu. Đối với hệ thống có rủi ro cao, cần kiểm thử rõ race delete/save và cân nhắc cơ chế revocation riêng.

## 18. Gia hạn nhưng vẫn giới hạn absolute lifetime

Sliding expiration có thể khiến phiên tiếp tục tồn tại vô hạn nếu người dùng hoặc client liên tục gửi request. Nhiều ứng dụng cần giới hạn tuổi thọ tuyệt đối để yêu cầu đăng nhập lại sau một khoảng thời gian tối đa.

Có thể lưu thời điểm tạo hoặc absolute expiry trong thuộc tính session, hoặc trong một record bảo mật riêng. Khi request đến, kiểm tra cả:

- Idle timeout: thời gian kể từ lần hoạt động hợp lệ gần nhất.
- Absolute timeout: thời gian kể từ khi phiên được tạo hoặc xác thực gần nhất.
- Reauthentication age: thời gian kể từ lần xác thực mạnh gần nhất.

Ví dụ chính sách:

- Idle timeout: 30 phút.
- Absolute lifetime: 12 giờ.
- Giao dịch nhạy cảm: yêu cầu xác thực lại nếu lần xác thực mạnh gần nhất quá 10 phút.

Các giá trị trên chỉ là minh họa. Chọn thời hạn theo rủi ro, quy định và trải nghiệm sản phẩm. Đừng chỉ dựa vào TTL của Redis hoặc cleanup job để thực hiện absolute lifetime; phải kiểm tra policy khi request sử dụng session.

## 19. Xử lý client khi session ID được đổi hoặc bị xóa

Client cần phản ứng đúng với response sau rotation hoặc logout:

- Khi server phát cookie mới, browser phải lưu ID mới theo đúng domain/path.
- Request tiếp theo cần dùng ID mới.
- Khi server invalidate session, client cần xóa cookie hoặc credential tương ứng.
- Nếu request nhận 401/unauthorized do session hết hạn, client có thể chuyển sang luồng đăng nhập.
- Không tự thử lại vô hạn bằng session ID cũ.
- Không lưu session ID vào localStorage nếu có thể dùng HttpOnly cookie.

Với nhiều request song song, response có thể đến sai thứ tự. Nếu hai response cùng đặt cookie, response đến sau có thể ghi đè cookie đã được cập nhật bởi response trước. Hãy tránh gửi các request phụ thuộc session trong khi login/logout/rotation đang hoàn tất; có thể điều phối phía client hoặc yêu cầu refresh state sau thao tác bảo mật.

Không dùng sticky session để giải quyết lỗi cookie response ordering. Sticky routing không thay thế quản lý ID và không ngăn response đến sai thứ tự.

## 20. Quy trình thao tác an toàn

Khi đổi ID, xóa hoặc gia hạn session, nên xác định rõ trạng thái và thứ tự:

**Đổi ID**

1. Xác thực thành công hoặc xác định lý do cần rotation.
2. Gọi API Servlet/Spring Security được hỗ trợ.
3. Bảo đảm repository lưu ID mới.
4. Trả cookie/header mới cho client.
5. Kiểm tra ID cũ không còn khôi phục được phiên.
6. Kiểm thử request cũ đang bay và response đến sai thứ tự.

**Xóa phiên**

1. Xác minh principal và quyền thu hồi.
2. Invalidate session hoặc dùng repository API theo đúng trường hợp.
3. Xóa SecurityContext và credential phía client.
4. Thu hồi remember-me token/device token nếu policy yêu cầu.
5. Xử lý request đang bay và ngăn session cũ được dùng cho thao tác nhạy cảm.
6. Ghi audit event không chứa session ID thô.

**Gia hạn phiên**

1. Xác minh session còn hợp lệ và chưa bị revoke.
2. Cập nhật timeout/last access theo API và policy.
3. Bảo đảm repository áp dụng TTL/expiry mới.
4. Không vượt absolute lifetime.
5. Không gia hạn chỉ vì một tác vụ nền không liên quan.
6. Kiểm thử race với cleanup và request khác.

## 21. Kiểm thử đồng thời có chủ đích

Kiểm thử tuần tự không phát hiện được nhiều race. Cần tạo các request đồng thời với điểm đồng bộ rõ ràng, chẳng hạn dùng latch/barrier trong test để điều khiển thứ tự load, update, delete và save.

Các trường hợp nên có:

1. Hai request cùng đọc session rồi sửa cùng một thuộc tính.
2. Hai request sửa hai thuộc tính khác nhau.
3. Một request gọi changeSessionId trong khi request khác đang lưu session cũ.
4. Hai response rotation/logout đến client theo thứ tự ngược.
5. Logout xảy ra sau khi request khác đã tải session nhưng trước khi request đó save.
6. Cleanup xóa session đúng lúc request cập nhật lastAccessedTime.
7. Gia hạn timeout cạnh tranh với expiration.
8. Hai request cùng gọi invalidate.
9. Hai instance cùng tải và cập nhật một session.
10. Session ID cũ được gửi sau rotation.
11. Session ID đã bị xóa được dùng lại trong request sau.
12. Kiểm tra absolute timeout dù có hoạt động liên tục.
13. Kiểm tra retry sau lỗi mạng khi save có thể đã thành công ở store.
14. Kiểm tra event expiration/deletion được phát và xử lý đúng số lần theo semantics repository.

Dùng Redis/JDBC repository thật hoặc môi trường integration tương thích với production. Mock repository hữu ích để ép thứ tự thread nhưng không chứng minh transaction, TTL và atomicity của database/store.

## 22. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Logout xong phiên xuất hiện lại | Request cũ save snapshot sau delete | Tái hiện race delete/save; kiểm tra revocation/version |
| Đổi ID xong client vẫn gửi ID cũ | Response mới bị mất hoặc response cũ ghi đè cookie | Kiểm tra Set-Cookie và thứ tự response |
| Session hết hạn dù người dùng đang hoạt động | Last access không được cập nhật hoặc request không đi qua filter | Kiểm tra filter chain và repository update |
| Session sống lâu hơn policy | Background save/heartbeat liên tục gia hạn idle timeout | Kiểm tra nguồn gọi save và absolute lifetime |
| Hai cập nhật cùng thuộc tính bị mất một | Lost update do load-modify-save | Dùng transaction, atomic update hoặc optimistic locking |
| Redis key đã hết TTL nhưng request cũ ghi lại | Request cũ save sau expiration | Kiểm tra repository semantics và kiểm soát stale write |
| JDBC cleanup xóa phiên vừa hoạt động | Cleanup và update expiry không được phối hợp như kỳ vọng | Kiểm tra SQL, transaction và thời điểm cleanup |
| Một node thấy session, node khác không thấy | Cấu hình namespace/store khác hoặc consistency lag | Kiểm tra cấu hình và topology |
| ID cũ vẫn truy cập được sau rotation | Repository/client path không hoàn tất rotation hoặc ID cũ còn tồn tại | Kiểm tra changeSessionId và lookup cũ |
| Gia hạn cookie nhưng server vẫn yêu cầu login | Cookie Max-Age dài hơn session TTL | Kiểm tra hai thời hạn độc lập |

Khi điều tra, thu thập timestamp, node ID, operation type và correlation ID. Không ghi session ID đầy đủ. Nếu cần đối chiếu, dùng hash có kiểm soát hoặc dấu vết đã che.

## 23. Checklist trước khi triển khai nhiều instance

- [ ] Tất cả instance dùng chung SessionRepository và namespace.
- [ ] Session fixation protection được bật và có chiến lược rotation rõ.
- [ ] Session ID cũ không thể khôi phục sau rotation.
- [ ] Logout invalidate phía server, không chỉ xóa cookie.
- [ ] Request đang bay sau logout được xử lý theo policy đã định.
- [ ] Gia hạn idle timeout không vượt absolute lifetime.
- [ ] Cookie Max-Age không bị nhầm với server-side TTL.
- [ ] Repository semantics cho concurrent save/delete đã được kiểm tra.
- [ ] Không dùng session làm nguồn dữ liệu chuẩn cho cập nhật nghiệp vụ quan trọng.
- [ ] Có optimistic locking/atomic operation nếu cần chống lost update.
- [ ] Cleanup và TTL được kiểm thử khi request gia hạn đồng thời.
- [ ] Client xử lý rotation và response đến sai thứ tự.
- [ ] Có integration test chạy trên Redis/JDBC thực tế.
- [ ] Log và trace không chứa session ID hoặc cookie.
- [ ] Có metric cho session lookup miss, expiration, revoke, save failure và concurrent conflict.

## Kết luận

Đổi định danh, xóa và gia hạn session là các thao tác có thể cạnh tranh khi nhiều request hoặc instance cùng sử dụng một phiên. Hãy dùng changeSessionId hoặc session fixation protection để xoay vòng ID, invalidate/logout để thu hồi phiên, và cấu hình idle timeout cùng absolute lifetime rõ ràng. SessionRepository cung cấp hợp đồng lưu trữ chung nhưng không định nghĩa một cơ chế compare-and-set hay transaction nguyên tử cho mọi chuỗi load-modify-save. Vì vậy, cần kiểm thử race giữa rotation, delete, save, cleanup và TTL trên repository thực tế; dùng atomic operation, optimistic locking hoặc revocation state bổ sung khi yêu cầu nghiệp vụ đòi hỏi; và không để request cũ làm sống lại credential đã bị thu hồi.

## Tài liệu tham khảo

- Spring Session Reference: https://docs.spring.io/spring-session/reference/
- SessionRepository API: https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/SessionRepository.html
- Spring Session HttpSession Integration: https://docs.spring.io/spring-session/reference/http-session.html
- Spring Security Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Servlet HttpServletRequest API: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletrequest
