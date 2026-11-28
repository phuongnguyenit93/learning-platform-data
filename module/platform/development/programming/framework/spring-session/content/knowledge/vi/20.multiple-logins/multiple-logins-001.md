# Phiên theo người dùng, theo trình duyệt và theo thiết bị

Một người dùng có thể đăng nhập cùng lúc trên máy tính cá nhân, điện thoại, máy tính bảng và nhiều trình duyệt. Spring Session lưu mỗi phiên HTTP trong một repository dùng chung như Redis hoặc JDBC; Spring Security khôi phục danh tính đã xác thực và áp dụng chính sách truy cập cho từng request. Để quản lý nhiều lần đăng nhập đúng cách, cần phân biệt ba góc nhìn: phiên thuộc về người dùng nào, phiên được sử dụng qua browser profile nào và phiên được gắn nhãn cho thiết bị nào.

Một session ID nhận diện một phiên cụ thể, không nhận diện chắc chắn một người dùng vật lý hay một thiết bị. Các tab trong cùng browser profile thường chia sẻ cookie và do đó dùng chung phiên. Hai browser profile khác nhau trên cùng máy thường có cookie jar riêng và có thể tạo hai phiên độc lập. Một người dùng có thể có nhiều phiên; một phiên cũng có thể được dùng trên nhiều thiết bị nếu credential bị sao chép. Vì vậy, ứng dụng phải thiết kế việc liệt kê, giới hạn và thu hồi phiên dựa trên principal và metadata đáng tin cậy, thay vì suy ra thiết bị chỉ từ session ID.

## 1. Phân biệt user, browser profile, device và session

Các khái niệm liên quan nhưng không đồng nhất:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| User / principal | Danh tính tài khoản đã xác thực | Tài khoản có mã nội bộ U-1042 |
| Browser profile | Không gian cookie và storage của một profile trình duyệt | Chrome profile cá nhân, Firefox profile công việc |
| Device | Thiết bị vật lý hoặc client ứng dụng | Laptop, điện thoại, tablet |
| Session | Một ngữ cảnh HTTP stateful được server lưu | Phiên đăng nhập có session ID riêng |
| Session ID | Credential định danh phiên được gửi qua cookie/header | Giá trị cookie SESSION |
| Device metadata | Thông tin mô tả client gắn với một phiên | Nhãn “Laptop công việc”, loại client “web” |

Một tài khoản có thể có nhiều session ID cùng lúc. Mỗi session thường có thời điểm tạo, thời điểm truy cập gần nhất, timeout và thuộc tính riêng. Session có thể tồn tại trước khi đăng nhập, ví dụ để lưu giỏ hàng ẩn danh; do đó session không mặc nhiên đồng nghĩa với phiên đăng nhập.

Một browser profile có thể mở nhiều tab. Các tab cùng origin và cùng cookie scope thường gửi cùng cookie session. Việc mở tab mới không tự tạo một phiên độc lập. Nếu người dùng đăng xuất trong một tab, các tab còn lại thường cũng mất phiên khi gửi request tiếp theo vì cookie đã bị xóa hoặc session phía server đã bị invalidate.

Cùng một thiết bị nhưng dùng profile khác hoặc browser khác thường có cookie jar riêng, do đó có thể có session độc lập. Ngược lại, nếu người dùng sao chép cookie hoặc dùng chung profile trên nhiều thiết bị, cùng một session ID có thể được gửi từ nhiều nơi. Session ID không phải bằng chứng về phần cứng.

## 2. Một người dùng có thể có nhiều phiên đăng nhập

Trong mô hình stateful authentication, Spring Security lưu SecurityContext của người dùng trong HttpSession. Khi người dùng đăng nhập từ browser profile khác, ứng dụng thường tạo hoặc sử dụng một session khác, với session ID khác.

Ví dụ:

| Người dùng | Client | Session ID | Thời điểm tạo |
|---|---|---|---|
| alice | Laptop / Chrome profile A | S-A | 08:10 |
| alice | Phone / app mobile | S-B | 09:25 |
| alice | Laptop / Firefox profile B | S-C | 10:40 |

Cả ba phiên có thể cùng thuộc principal alice, nhưng có vòng đời và trạng thái độc lập. Logout phiên S-B không nhất thiết làm mất S-A hoặc S-C. Muốn đăng xuất tất cả thiết bị, ứng dụng phải tìm và thu hồi tất cả phiên của principal.

Một phiên đăng nhập thường được tạo hoặc trở thành phiên đã xác thực sau khi authentication thành công. Spring Security có thể thay đổi session ID để phòng session fixation. Ứng dụng cần để framework thực hiện việc đổi ID và để client nhận cookie/header mới. Không tự gán cùng một session ID cho nhiều thiết bị hoặc tự tạo ID từ user ID.

## 3. Các tab và browser profile chia sẻ phiên ra sao?

Cookie được trình duyệt quản lý theo các thuộc tính như host/domain, path, Secure và SameSite. Các tab thuộc cùng profile dùng chung cookie jar. Do đó, nếu cookie SESSION có cùng phạm vi, request từ các tab thường gửi cùng session ID.

| Thao tác của người dùng | Hành vi thường thấy |
|---|---|
| Mở thêm tab trong cùng profile | Dùng cùng cookie và session hiện tại |
| Mở cửa sổ mới cùng profile | Thường dùng cùng cookie jar và session |
| Mở cửa sổ riêng tư/incognito | Dùng kho cookie riêng biệt trong phiên riêng tư |
| Mở browser khác | Thường có cookie jar riêng |
| Dùng profile khác trong cùng browser | Cookie jar tách biệt |
| Xóa cookie hoặc dữ liệu site | Client mất session ID; server-side session có thể còn đến khi hết hạn |
| Sao chép cookie sang client khác | Có thể sử dụng cùng session nếu server chấp nhận ID |

Đây là hành vi phổ biến của browser, nhưng chi tiết phụ thuộc browser, profile, chế độ riêng tư và cấu hình cookie. Ứng dụng không nên dựa vào số tab để đếm số phiên đăng nhập.

Nếu yêu cầu là “mỗi thiết bị chỉ có một phiên”, hãy định nghĩa rõ “thiết bị” trong sản phẩm. Một lựa chọn thực tế là mỗi browser profile hoặc mỗi cài đặt mobile app có một device registration ID riêng. Đây là khái niệm do ứng dụng quản lý; nó không tự động được cung cấp bởi HttpSession.

## 4. Tìm tất cả phiên theo principal

Để liệt kê phiên của một người dùng, repository cần hỗ trợ tìm theo chỉ mục principal. Spring Session cung cấp FindByIndexNameSessionRepository và hằng số PRINCIPAL_NAME_INDEX_NAME cho mục đích này.

Ví dụ truy vấn:

~~~java
Map<String, ? extends Session> findUserSessions(
        FindByIndexNameSessionRepository<? extends Session> repository,
        String principalName) {

    return repository.findByIndexNameAndIndexValue(
            FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
            principalName
    );
}
~~~

Map trả về có session ID làm key và Session làm value. Ứng dụng có thể đọc thời điểm tạo, thời điểm truy cập gần nhất, thời gian không hoạt động tối đa và các thuộc tính metadata đã lưu.

Chỉ mục principal thường được xây dựng từ thông tin Authentication trong session bằng PrincipalNameIndexResolver hoặc resolver tương ứng của repository. Trong cấu hình thông thường, principal name gắn với Authentication.getName(). Nếu ứng dụng dùng principal tùy chỉnh, username có thể thay đổi hoặc nhiều tenant có thể trùng username, cần xác định một định danh ổn định và duy nhất.

Không dùng display name hoặc email có thể đổi làm khóa quản lý lâu dài nếu hệ thống có một user ID bất biến. Có thể tùy chỉnh IndexResolver để lập chỉ mục theo định danh chuẩn, nhưng cần bảo đảm các instance cùng dùng một quy tắc và dữ liệu đã được lưu tương thích.

## 5. Cấu hình SessionRegistry dùng chung giữa nhiều instance

Spring Security có SessionRegistry để hỗ trợ quản lý phiên và kiểm soát số lần đăng nhập đồng thời. SessionRegistryImpl mặc định lưu thông tin trong bộ nhớ của một JVM. Trong triển khai nhiều instance, registry cục bộ của node A không tự biết các phiên chỉ được tạo trên node B.

Spring Session cung cấp SpringSessionBackedSessionRegistry để dựa vào FindByIndexNameSessionRepository. Nhờ đó, việc tìm phiên theo principal dựa trên repository dùng chung thay vì danh sách chỉ tồn tại trong một JVM.

Ví dụ cấu hình bean:

~~~java
@Bean
SpringSessionBackedSessionRegistry<? extends Session> sessionRegistry(
        FindByIndexNameSessionRepository<? extends Session> sessionRepository) {
    return new SpringSessionBackedSessionRegistry<>(sessionRepository);
}
~~~

Sau đó dùng registry trong cấu hình Spring Security:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        SessionRegistry sessionRegistry) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .sessionManagement(session -> session
            .maximumSessions(3)
            .sessionRegistry(sessionRegistry)
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Ví dụ minh họa giới hạn ba phiên đồng thời cho mỗi principal. Cần xác minh repository đang dùng triển khai FindByIndexNameSessionRepository và index principal thực sự được cập nhật khi Authentication được lưu. Không phải mọi implementation SessionRepository đều hỗ trợ truy vấn theo principal.

Nếu dùng SessionRegistryImpl cục bộ, cần xem xét HttpSessionEventPublisher để registry nhận biết session bị hủy và loại bỏ thông tin tương ứng. Khi dùng SpringSessionBackedSessionRegistry, trạng thái được đọc từ repository; hãy theo tài liệu tích hợp của phiên bản Spring Session/Spring Security đang chạy thay vì sao chép cấu hình event của registry cục bộ một cách máy móc.

## 6. Chính sách khi vượt giới hạn đăng nhập

Spring Security cho phép giới hạn số phiên đồng thời bằng maximumSessions. Khi đạt giới hạn, ứng dụng cần quyết định từ chối lần đăng nhập mới hay cho phép đăng nhập mới và làm phiên cũ hết hiệu lực.

Ví dụ cho phép đăng nhập mới và đánh dấu phiên cũ hết hiệu lực:

~~~java
http.sessionManagement(session -> session
    .maximumSessions(2)
    .maxSessionsPreventsLogin(false)
);
~~~

Ví dụ từ chối lần đăng nhập mới khi đã đủ số phiên:

~~~java
http.sessionManagement(session -> session
    .maximumSessions(2)
    .maxSessionsPreventsLogin(true)
);
~~~

Ý nghĩa sản phẩm cần được giải thích rõ:

| Chính sách | Khi đã đủ số phiên | Trải nghiệm |
|---|---|---|
| Cho login mới | Phiên cũ có thể bị đánh dấu expired theo chiến lược registry | Thiết bị mới vào được, thiết bị cũ bị yêu cầu xác thực lại ở request sau |
| Ngăn login mới | Authentication mới bị từ chối | Người dùng phải đăng xuất một phiên cũ trước |
| Không giới hạn | Không áp dụng concurrency limit | Thuận tiện nhưng cần chính sách thu hồi và giám sát riêng |

Khi dùng giới hạn phiên, cần cấu hình SessionRegistry tương thích và kiểm thử hành vi khi request được xử lý trên nhiều instance. Đừng giả định cấu hình maximumSessions với registry trong bộ nhớ sẽ tự tạo giới hạn toàn cụm.

Nếu cần thông báo thân thiện như “Bạn đã đăng nhập trên ba thiết bị”, hãy xử lý kết quả vượt giới hạn bằng authentication failure/expired strategy phù hợp. Không hiển thị session ID hoặc dữ liệu nhạy cảm trong thông báo.

## 7. Gắn metadata trình duyệt và thiết bị vào session

Spring Session không tự xác định phần cứng của client. Ứng dụng có thể lưu metadata mô tả client trong session sau khi đăng nhập thành công, ví dụ:

- Loại client: web, Android, iOS hoặc desktop.
- Nhãn do người dùng đặt: “Laptop công ty”, “Điện thoại cá nhân”.
- Thời điểm đăng ký phiên.
- User-Agent đã được rút gọn thành browser/OS family.
- Thông tin khu vực gần đúng nếu sản phẩm thực sự cần và có chính sách riêng.

Ví dụ lưu metadata:

~~~java
public void attachClientMetadata(
        HttpSession session,
        String clientType,
        String deviceLabel,
        String userAgentSummary) {

    session.setAttribute("client.type", clientType);
    session.setAttribute("client.label", sanitizeLabel(deviceLabel));
    session.setAttribute("client.userAgent", userAgentSummary);
    session.setAttribute("client.registeredAt", Instant.now());
}
~~~

Hãy gọi logic này sau khi xác thực thành công hoặc trong authentication success handler phù hợp. Nếu Spring Security thay đổi session ID khi login, kiểm tra metadata có được giữ qua chiến lược session fixation đã cấu hình hay không. Không giả định mọi thuộc tính tùy chỉnh luôn được chuyển trong mọi chiến lược.

Nhãn thiết bị do client gửi chỉ là mô tả để người dùng nhận biết; cần giới hạn độ dài, loại bỏ ký tự điều khiển và không dùng nó làm căn cứ cấp quyền. User-Agent có thể bị giả mạo hoặc thay đổi khi browser cập nhật. Không xem nó là định danh thiết bị duy nhất.

## 8. Device registration ID và giới hạn của fingerprint

Nếu sản phẩm cần nhận diện một cài đặt ứng dụng hoặc browser profile qua nhiều lần đăng nhập, có thể tạo một device registration record riêng. Record có thể có ID ngẫu nhiên do server cấp, được lưu ở client trong kho phù hợp và liên kết với tài khoản sau khi xác thực.

Mô hình ví dụ:

    User account
       |
       +-- Device registration D-01
       |       |
       |       +-- Session S-101
       |       +-- Session S-102 (nếu chính sách cho phép)
       |
       +-- Device registration D-02
               |
               +-- Session S-201

Định danh device registration khác session ID:

- Device registration có thể tồn tại qua nhiều phiên đăng nhập.
- Session ID thường thay đổi khi logout, hết hạn hoặc session fixation protection.
- Một device registration có thể có nhiều session theo chính sách.
- Xóa device registration có thể kéo theo thu hồi tất cả session liên kết.

Không nên tạo fingerprint xâm lấn từ canvas, font, plugin, độ phân giải màn hình hoặc các đặc điểm phần cứng để nhận diện thiết bị. Fingerprint có thể sai, dễ thay đổi, khó giải thích và ảnh hưởng quyền riêng tư. Nếu cần device registration, hãy dùng ID ngẫu nhiên có mục đích rõ ràng, thông báo cho người dùng và cho phép họ xóa thiết bị đã đăng ký.

Không dùng device ID làm credential duy nhất để xác thực. Người dùng có thể sao chép hoặc mất thiết bị; xác thực vẫn cần dựa trên cơ chế đăng nhập/token phù hợp.

## 9. Hiển thị danh sách phiên và thiết bị đã đăng nhập

Một trang “Thiết bị đang đăng nhập” thường cần hiển thị thông tin dễ hiểu thay vì session ID:

| Trường hiển thị | Nguồn phù hợp |
|---|---|
| Tên thiết bị | Metadata do người dùng đặt hoặc device registration |
| Loại client | Metadata ứng dụng |
| Browser/OS | User-Agent đã phân tích ở mức khái quát |
| Đăng nhập lúc | Thời điểm tạo session hoặc device registration |
| Hoạt động gần nhất | Session.getLastAccessedTime() |
| Hết hạn sau | Session.getMaxInactiveInterval() kết hợp last access |
| Phiên hiện tại | So sánh session ID hiện tại với ID trong kết quả |
| Hành động | Logout phiên này hoặc thu hồi phiên khác |

Ví dụ service tạo dữ liệu hiển thị từ repository:

~~~java
Map<String, ? extends Session> sessions =
        sessionRepository.findByIndexNameAndIndexValue(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                principalName
        );

List<SessionSummary> summaries = sessions.values().stream()
        .map(session -> new SessionSummary(
                session.getId(),
                session.getCreationTime(),
                session.getLastAccessedTime(),
                session.getMaxInactiveInterval(),
                session.getAttribute("client.label"),
                session.getAttribute("client.type")
        ))
        .toList();
~~~

Đây là mã minh họa; SessionSummary cần được định nghĩa theo ứng dụng và không nên trả session ID đầy đủ về giao diện nếu không cần. Với thao tác logout một phiên cụ thể, server cần xác minh phiên đó thuộc principal hiện tại trước khi xóa.

Nếu repository trả về nhiều phiên, thứ tự có thể không phải thứ tự đăng nhập. Hãy sắp xếp theo lastAccessedTime hoặc creationTime trong service. Các phiên hết hạn hoặc dữ liệu index cũ cần được xử lý theo semantics của repository.

## 10. Logout một phiên, một thiết bị hoặc tất cả thiết bị

Ba hành động này khác nhau:

- Logout phiên hiện tại: invalidate HttpSession đang gắn với request.
- Logout một phiên khác: xóa session ID cụ thể sau khi xác minh quyền sở hữu.
- Logout tất cả thiết bị: tìm toàn bộ session của principal hoặc device registrations rồi thu hồi chúng.

Ví dụ thu hồi một phiên cụ thể sau khi đã xác minh phiên thuộc principal:

~~~java
public void revokeSession(
        String principalName,
        String targetSessionId) {

    Map<String, ? extends Session> sessions =
            sessionRepository.findByIndexNameAndIndexValue(
                    FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                    principalName
            );

    if (sessions.containsKey(targetSessionId)) {
        sessionRepository.deleteById(targetSessionId);
    }
}
~~~

Ví dụ thu hồi tất cả phiên của một principal:

~~~java
public void revokeAllSessions(String principalName) {
    Map<String, ? extends Session> sessions =
            sessionRepository.findByIndexNameAndIndexValue(
                    FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                    principalName
            );

    for (String sessionId : sessions.keySet()) {
        sessionRepository.deleteById(sessionId);
    }
}
~~~

Các ví dụ cần được gọi từ service có kiểm tra quyền. Không nhận principalName tùy ý từ request body để xóa phiên của người khác; lấy principal hiện tại từ SecurityContext hoặc xác minh quyền quản trị. Không cho phép người dùng truyền một session ID bất kỳ rồi xóa mà không kiểm tra ownership.

Với logout phiên hiện tại, dùng logout flow của Spring Security và invalidateHttpSession theo cấu hình. Việc xóa cookie chỉ dọn credential ở client; repository phải xóa phiên phía server để thu hồi thực sự.

## 11. Logout theo device registration

Nếu ứng dụng có bảng device registration riêng, có thể liên kết session với device ID. Khi người dùng chọn “Đăng xuất thiết bị này”, service tìm tất cả session gắn với device registration và xóa chúng. Khi chọn “Xóa thiết bị”, service có thể đánh dấu registration bị revoked rồi thu hồi các session liên quan.

Mô hình dữ liệu gợi ý:

| Bảng/collection | Trường | Mục đích |
|---|---|---|
| UserDevice | deviceId, userId, label, clientType, createdAt, revokedAt | Danh sách client đã đăng ký |
| DeviceSessionLink (nếu cần) | deviceId, sessionId, createdAt | Liên kết device với từng session |
| Spring Session repository | session ID, principal index, attributes | Trạng thái phiên HTTP |

Không nhất thiết phải tạo bảng liên kết riêng nếu metadata session đủ đáp ứng. Nhưng nếu device registration phải tồn tại qua nhiều lần đăng nhập và cần trạng thái revoked độc lập với session, một record nghiệp vụ riêng sẽ rõ ràng hơn.

Khi xóa device, không chỉ xóa record mà bỏ các session đang hoạt động. Nên đánh dấu revoked trước, chặn việc tạo phiên mới từ device đó theo policy, rồi thu hồi session hiện có. Nếu request đang chạy, nó có thể đã tải session trước thời điểm thu hồi; với thao tác nhạy cảm, cần kiểm tra trạng thái device/account ở các điểm authorization quan trọng.

## 12. Quản lý phiên đồng thời và giới hạn theo tài khoản

Giới hạn số phiên theo principal hữu ích khi sản phẩm có yêu cầu “tối đa N thiết bị đăng nhập”. Spring Security maximumSessions thường giới hạn số session của principal. Tuy nhiên, “số session” và “số device” không luôn giống nhau.

Ví dụ một browser profile có thể tạo nhiều session qua các lần đăng nhập, trong khi một device registration có thể liên kết nhiều session. Nếu yêu cầu là tối đa ba browser profile, giới hạn số session có thể gần đúng nhưng không bảo đảm chính xác. Nếu yêu cầu là một device registration chỉ có một session hoạt động, cần kiểm tra device ID và thu hồi session cũ theo logic nghiệp vụ.

Một số mô hình:

| Yêu cầu | Cách triển khai |
|---|---|
| Tối đa 3 phiên cho một tài khoản | Spring Security maximumSessions + shared SessionRegistry |
| Chỉ một phiên cho tài khoản | maximumSessions(1), quyết định từ chối login mới hay hết hiệu lực phiên cũ |
| Tối đa 1 session cho mỗi device registration | Tìm session theo principal và device ID, thu hồi session cũ |
| Logout mọi thiết bị | Tìm tất cả session theo principal và xóa |
| Chỉ hiển thị danh sách thiết bị | Principal index + metadata đã kiểm duyệt |
| Thu hồi khi tài khoản bị khóa | Đánh dấu account disabled/revoked và xóa session; kiểm tra trạng thái tài khoản theo policy |

Không dùng IP address làm device ID hoặc khóa giới hạn. Người dùng có thể đổi mạng, dùng VPN, đi qua NAT hoặc mạng di động; nhiều người cũng có thể chung một IP.

## 13. Xử lý race condition khi nhiều login đồng thời

Hai login cùng một tài khoản có thể xảy ra gần như đồng thời trên hai instance. Cả hai request có thể truy vấn số phiên hiện tại trước khi phiên mới được lưu, rồi cùng kết luận rằng còn chỗ. Nếu giới hạn là hai, kết quả có thể tạm thời vượt giới hạn.

Shared SessionRegistry giúp các node nhìn cùng dữ liệu, nhưng không tự biến chuỗi “đếm rồi tạo phiên” thành một transaction nguyên tử trên mọi repository. Hành vi cụ thể phụ thuộc Spring Security, repository và cách session được lưu.

Nếu giới hạn là yêu cầu bảo mật hoặc cấp phép nghiêm ngặt:

- Kiểm thử hai hoặc nhiều login song song qua các instance khác nhau.
- Dùng một cơ chế đồng bộ/claim theo account nếu repository không bảo đảm thao tác nguyên tử.
- Có thể dùng database constraint hoặc distributed coordination phù hợp với hạ tầng.
- Sau khi xác thực thành công, xác nhận session được index theo principal.
- Có tác vụ đối soát để phát hiện vượt giới hạn và áp dụng policy.
- Xác định rõ thứ tự ưu tiên khi thu hồi phiên: phiên cũ nhất, ít hoạt động nhất hay phiên do người dùng chọn.

Không dùng SessionRegistry làm distributed lock trừ khi implementation cam kết semantics đó. Registry được thiết kế để tra cứu và hỗ trợ concurrency control; không nên suy ra mọi thao tác là transaction nguyên tử giữa các node.

## 14. Expiration, last access và dữ liệu phiên cũ

Mỗi session có timeout riêng. Một người dùng có thể có nhiều session với thời điểm truy cập và thời hạn khác nhau. Một phiên đang hoạt động không có nghĩa mọi phiên khác của cùng người dùng cũng được gia hạn.

Danh sách thiết bị nên hiển thị lastAccessedTime và trạng thái phù hợp, nhưng cần hiểu repository cập nhật thời điểm này khi nào. Một session có thể hết hạn ở server trước khi browser xóa cookie. Cookie còn tồn tại không làm session hết hạn sống lại.

Repository index cũng cần được xử lý theo cơ chế của implementation. Redis, JDBC và các repository khác có cách dọn session hết hạn và phát sự kiện khác nhau. Nếu trang thiết bị cần dữ liệu chính xác, hãy xác minh session còn tồn tại và chưa hết hạn trước khi hiển thị hoặc cho phép thu hồi.

Không lưu device registry chỉ trong session nếu sản phẩm cần danh sách thiết bị tồn tại sau khi session hết hạn. Metadata trong session biến mất cùng session; record thiết bị cần vòng đời riêng.

## 15. Bảo mật và quyền riêng tư của danh sách phiên

Trang quản lý phiên là chức năng nhạy cảm vì nó cho phép xem và thu hồi các credential đang hoạt động.

Các nguyên tắc:

- Chỉ người dùng đã xác thực mới xem được phiên của chính họ.
- Tài khoản quản trị chỉ được xem phiên người khác theo quyền và mục đích rõ ràng.
- Không trả session ID đầy đủ ra giao diện nếu không cần.
- Không ghi cookie, session ID hoặc raw authorization header vào log.
- Không coi User-Agent, IP hoặc device label là bằng chứng xác thực.
- Giới hạn dữ liệu nhận dạng thiết bị và thời gian lưu theo chính sách riêng tư.
- Bảo vệ endpoint revoke bằng CSRF nếu dùng cookie session.
- Xác minh ownership của session trước khi xóa.
- Khi tài khoản bị khóa hoặc nghi ngờ bị chiếm quyền, có thể yêu cầu thu hồi tất cả phiên.
- Ghi audit event về hành động thu hồi nhưng tránh lưu credential thô.

IP address có thể hữu ích cho cảnh báo đăng nhập bất thường, nhưng không nên dùng làm định danh thiết bị cố định. Nếu lưu IP, hãy xác định thời hạn, mục đích và quy tắc truy cập dữ liệu.

## 16. Kiểm thử nhiều phiên qua nhiều trình duyệt và instance

Một bộ kiểm thử tốt cần mô phỏng nhiều cookie jar độc lập. Dùng cùng một cookie jar cho mọi request chỉ kiểm tra một phiên; không chứng minh được quản lý nhiều đăng nhập.

Các tình huống nên kiểm thử:

1. Đăng nhập alice trong browser profile A và ghi nhận session A.
2. Đăng nhập alice trong browser profile B với cookie jar riêng và xác nhận session B khác session A.
3. Mở hai tab trong profile A và xác nhận cả hai dùng cùng session A.
4. Đăng nhập cùng principal từ mobile client và xác nhận phiên thứ ba được tìm thấy theo principal.
5. Truy vấn principal index và xác nhận danh sách chứa các session đang hoạt động.
6. Kiểm tra metadata device label/type hiển thị đúng nhưng không làm lộ session ID.
7. Logout session B và xác nhận A, C vẫn hoạt động.
8. Logout tất cả phiên alice và xác nhận các ID đã thu hồi không khôi phục Authentication.
9. Kiểm tra maximumSessions khi đạt giới hạn theo cả hai chính sách.
10. Gửi hai login đồng thời qua hai instance để phát hiện vượt giới hạn.
11. Kiểm tra session ID rotation sau login và xác nhận browser dùng cookie mới.
12. Để một session hết hạn và xác nhận danh sách thiết bị không xem nó là active.
13. Thu hồi session của user khác và xác nhận request bị từ chối do ownership check.
14. Kiểm tra session registry khi instance restart hoặc node khác xử lý request.
15. Kiểm tra log/audit không chứa session ID hoặc credential.

Với Spring Security có thể dùng MockMvc và các request session/cookie riêng để kiểm tra filter chain. Với Redis/JDBC, cần integration test dùng repository thật hoặc môi trường tương thích. Với browser profile, có thể dùng hai cookie jar độc lập trong test client hoặc hai browser context. Với nhiều instance, định tuyến request đến node A và B để xác nhận registry và repository dùng chung.

## 17. Chẩn đoán sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Hai tab cùng browser được tính thành hai thiết bị | Đếm tab hoặc tạo session mới ngoài ý muốn | Kiểm tra cookie jar và endpoint tạo session |
| Hai browser profile dùng chung một phiên | Cookie được chia sẻ/sao chép hoặc domain/path scope quá rộng | Kiểm tra browser storage và cookie attributes |
| Một user đăng nhập trên node A nhưng không xuất hiện ở node B | Registry cục bộ hoặc repository/index không dùng chung | Kiểm tra SpringSessionBackedSessionRegistry và principal index |
| Session không xuất hiện trong danh sách principal | Authentication chưa được lưu hoặc resolver không trích principal | Kiểm tra SecurityContext và IndexResolver |
| Logout một thiết bị làm logout tất cả | Service xóa theo principal thay vì session ID | Kiểm tra target session ownership và deleteById |
| Logout tất cả nhưng một phiên vẫn hoạt động | Có login đồng thời hoặc session mới được tạo trong lúc thu hồi | Kiểm tra race và account-level revocation |
| Giới hạn session bị vượt | Registry không chia sẻ hoặc check/create không nguyên tử | Kiểm thử concurrency giữa các node |
| Thiết bị hiển thị sai tên | Tin User-Agent hoặc label client như định danh cứng | Dùng device registration ID và cho phép người dùng đổi nhãn |
| Phiên hết hạn vẫn hiện trong UI | Dữ liệu index/metadata chưa được đối soát | Xác minh repository và timeout trước khi hiển thị |

Khi điều tra, tách bốn câu hỏi: principal có được xác định đúng không; repository có tìm đủ session không; metadata client có đáng tin ở mức mô tả không; thao tác revoke có xác minh ownership và xóa đúng session không.

## 18. Quy trình thiết kế chức năng quản lý thiết bị

Khi xây dựng trang “Các phiên đăng nhập”, nên làm theo trình tự:

1. Chọn định danh principal bất biến và duy nhất.
2. Xác nhận repository triển khai FindByIndexNameSessionRepository và principal index được cập nhật.
3. Dùng SpringSessionBackedSessionRegistry nếu cần concurrency control chia sẻ giữa nhiều instance.
4. Xác định sản phẩm đếm session, browser profile hay device registration.
5. Lưu metadata tối thiểu sau khi đăng nhập thành công.
6. Liệt kê session theo principal và tạo DTO hiển thị đã loại bỏ credential nhạy cảm.
7. Xây dựng endpoint revoke một phiên với ownership check.
8. Xây dựng endpoint revoke all sessions và xử lý login đồng thời.
9. Nếu cần quản lý thiết bị dài hạn, lưu device registration riêng khỏi HttpSession.
10. Kiểm thử cookie jar độc lập, nhiều tab, nhiều instance, session fixation, expiration và logout.
11. Theo dõi số session theo principal, lỗi index, số lần revoke và login bị từ chối.
12. Xác định chính sách khi tài khoản đổi mật khẩu, bị khóa hoặc phát hiện đăng nhập bất thường.

Nếu chỉ cần giới hạn số lần đăng nhập, Spring Security concurrency control có thể đủ. Nếu cần danh sách thiết bị dài hạn, nhãn người dùng, revoke theo thiết bị hoặc cảnh báo đăng nhập, nên có model device registration riêng và dùng Spring Session như lớp lưu trạng thái phiên.

## Kết luận

Phiên theo người dùng được xác định qua principal index; phiên theo browser profile phụ thuộc cookie jar; còn phiên theo thiết bị cần metadata hoặc device registration do ứng dụng quản lý. Một người dùng có thể có nhiều session ID, nhiều tab trong cùng profile thường dùng chung session, và session ID không phải định danh phần cứng. Hãy dùng FindByIndexNameSessionRepository để tìm phiên theo principal, SpringSessionBackedSessionRegistry cho concurrency control nhiều instance, xác minh ownership trước khi revoke, và tách device registration khỏi session nếu cần quản lý thiết bị lâu dài. Kiểm thử nhiều cookie jar, session fixation, logout riêng lẻ/toàn bộ và login đồng thời để bảo đảm hành vi đúng trong môi trường phân tán.
