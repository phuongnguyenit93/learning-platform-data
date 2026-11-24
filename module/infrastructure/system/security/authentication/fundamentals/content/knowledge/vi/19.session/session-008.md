# Session fixation (Cố định phiên)

> **Chương:** Session  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Hiểu cách kẻ tấn công khiến nạn nhân sử dụng một session ID mà attacker đã biết, sau đó lợi dụng việc ứng dụng giữ nguyên ID đó sau đăng nhập để chiếm phiên đã xác thực. Người học biết xoay vòng và vô hiệu hóa session ID tại các ranh giới xác thực, đặc quyền và khôi phục.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **session fixation** và phân biệt nó với session hijacking, session prediction và CSRF.
2. Mô tả chuỗi tấn công từ việc attacker biết hoặc áp đặt session ID trước đăng nhập đến lúc nạn nhân xác thực và attacker sử dụng phiên.
3. Xác định các ranh giới tin cậy trong vòng đời phiên: anonymous, pending authentication, authenticated, elevated privilege và logged out.
4. Thiết kế việc tạo mới, xoay vòng và vô hiệu hóa session ID sau đăng nhập, MFA, step-up, đổi quyền và các thao tác nhạy cảm.
5. Bảo vệ cookie phiên bằng HTTPS, Secure, HttpOnly, SameSite, phạm vi host/domain và các cấu hình phù hợp.
6. Sử dụng cơ chế chống session fixation có sẵn của Java Servlet/Spring Security thay vì tự quản lý session ID tùy tiện.
7. Xây dựng kiểm thử chứng minh session ID cũ không còn được chấp nhận sau khi trạng thái xác thực thay đổi.

## 1. Session fixation là gì?

**Session fixation (cố định phiên)** là kiểu tấn công trong đó attacker biết hoặc khiến nạn nhân sử dụng một session identifier do attacker kiểm soát hoặc đã biết trước. Nạn nhân đăng nhập thành công, nhưng ứng dụng tiếp tục sử dụng cùng session ID đó thay vì cấp một ID mới. Attacker sau đó trình lại ID đã biết và có thể truy cập phiên của nạn nhân.

Session ID thường được gửi qua cookie, ví dụ:

~~~http
Cookie: JSESSIONID=opaque-session-value
~~~

Giá trị này là một tham chiếu bí mật tới trạng thái phiên ở server. Nếu ứng dụng giữ nguyên session ID từ trạng thái anonymous sang trạng thái authenticated, người biết ID đó trước đăng nhập có thể được hưởng quyền mới mà không cần biết mật khẩu, OTP hay passkey của nạn nhân.

Điểm cốt lõi của session fixation là **danh tính và quyền của phiên thay đổi nhưng session identifier không thay đổi**. Biện pháp quan trọng nhất là cấp một session ID mới và làm cho ID cũ mất hiệu lực khi chuyển qua ranh giới xác thực hoặc đặc quyền.

### Ví dụ trực quan

1. Attacker biết session ID là **S-123** trong trạng thái chưa đăng nhập.
2. Attacker khiến browser của nạn nhân gửi cookie chứa **S-123**.
3. Nạn nhân đăng nhập thành công.
4. Ứng dụng gắn trạng thái authenticated vào session **S-123** mà không đổi ID.
5. Attacker gửi **S-123** tới ứng dụng.
6. Server tìm thấy phiên đã đăng nhập và chấp nhận request của attacker.

Các giá trị trong ví dụ chỉ để minh họa, không phải session ID thực. Trong hệ thống an toàn, ID được dùng trước đăng nhập không được trở thành ID của phiên đã xác thực.

## 2. Phân biệt session fixation với các lỗi phiên khác

Các vấn đề về phiên có thể dẫn đến cùng kết quả là truy cập trái phép, nhưng điểm khởi đầu khác nhau.

| Vấn đề | Cách xảy ra | Dấu hiệu phân biệt |
| --- | --- | --- |
| **Session fixation** | Attacker biết/áp đặt ID trước đăng nhập; ứng dụng giữ ID sau khi nạn nhân xác thực. | ID đã biết trước được nâng từ anonymous thành authenticated. |
| **Session hijacking** | Attacker lấy được ID của một phiên đã xác thực. | Phiên bị đánh cắp sau khi đã có quyền. |
| **Session prediction** | Attacker đoán hoặc suy ra ID phiên hợp lệ do ID được sinh yếu. | ID có cấu trúc hoặc entropy không đủ. |
| **CSRF** | Browser gửi request ngoài ý muốn kèm cookie tự động. | Nạn nhân bị lợi dụng để thực hiện hành động; attacker không nhất thiết biết session ID. |
| **Session replay** | Một thông điệp hoặc token phiên bị ghi lại rồi trình lại. | Bằng chứng cũ được tái sử dụng. |

Các lỗi này có thể kết hợp. Ví dụ, attacker có thể cố định ID trước đăng nhập rồi dùng chính ID đó như một phiên bị chiếm sau khi nạn nhân đăng nhập. Tuy nhiên, kiểm soát chống fixation không thay thế việc chống XSS, CSRF, token theft hoặc dự đoán session ID.

## 3. Mô hình hóa ranh giới tin cậy của phiên

Phiên thường bắt đầu ở trạng thái anonymous rồi thay đổi khi người dùng xác thực. Một ứng dụng có thể có các trạng thái:

- **Anonymous:** chưa có danh tính được xác thực; có thể giữ giỏ hàng hoặc lựa chọn giao diện.
- **Pending authentication:** đã vượt qua một phần luồng, ví dụ password đúng nhưng MFA chưa xong.
- **Authenticated:** tất cả yêu cầu xác thực của chính sách đã đạt.
- **Elevated:** đã step-up hoặc được cấp ngữ cảnh đủ mạnh cho thao tác đặc quyền.
- **Logged out/revoked:** phiên không còn được chấp nhận.

Session ID là chìa khóa tham chiếu tới trạng thái server. Nếu cùng một ID đi qua các trạng thái có quyền tăng dần, người biết ID từ trạng thái yếu có thể hưởng quyền của trạng thái mạnh.

~~~mermaid
stateDiagram-v2
    [*] --> Anonymous
    Anonymous --> PendingAuthentication: Bắt đầu đăng nhập
    PendingAuthentication --> Authenticated: Xác minh đủ credential và MFA
    Authenticated --> Elevated: Step-up / xác thực lại
    Elevated --> Authenticated: Hết thời hạn nâng quyền
    Authenticated --> LoggedOut: Đăng xuất / thu hồi
    Elevated --> LoggedOut: Đăng xuất / thu hồi
    LoggedOut --> [*]
~~~

Sơ đồ mô tả trạng thái logic. **Mỗi lần chuyển sang mức tin cậy hoặc quyền cao hơn cần đánh giá việc xoay session ID**, đặc biệt anonymous → authenticated và pending MFA → authenticated. Khi hạ quyền hoặc logout, server phải cập nhật trạng thái và vô hiệu hóa phiên/credential tương ứng.

### Ranh giới tin cậy cần kiểm tra

| Ranh giới | Dữ liệu/trạng thái thay đổi | Kiểm soát |
| --- | --- | --- |
| Anonymous → pending login | Client bắt đầu transaction xác thực. | Session anonymous không được có quyền truy cập dữ liệu riêng tư. |
| Pending login → authenticated | Credential/MFA được xác minh. | Xoay session ID; vô hiệu hóa ID trước đó. |
| Authenticated → elevated | Step-up hoặc xác thực lại đạt. | Xoay ID hoặc cập nhật binding phiên theo framework và chính sách. |
| Đổi mật khẩu/credential | Trạng thái bảo mật tài khoản thay đổi. | Đánh giá và thu hồi các phiên cũ, xoay phiên hiện tại nếu còn hợp lệ. |
| Logout/revoke | Phiên bị kết thúc. | Vô hiệu hóa trạng thái server và xóa cookie phía client. |

## 4. Chuỗi tấn công session fixation

Một cuộc tấn công thường có ba giai đoạn: **attacker chuẩn bị ID**, **nạn nhân đăng nhập bằng ID đó**, rồi **attacker sử dụng lại ID**.

~~~mermaid
sequenceDiagram
    autonumber
    actor A as Attacker
    actor V as Nạn nhân
    participant B as Browser
    participant App as Ứng dụng
    A->>App: Tạo hoặc lấy session anonymous S
    App-->>A: Session ID S
    A->>V: Khiến browser dùng session ID S
    V->>B: Mở trang đăng nhập
    B->>App: Request với cookie S
    App-->>B: Trang đăng nhập
    V->>B: Nhập credential hợp lệ
    B->>App: Login request với S
    App->>App: Xác minh credential thành công
    App->>App: Giữ nguyên S và gắn trạng thái authenticated
    App-->>B: Đăng nhập thành công với S
    A->>App: Request mới với cookie S
    App-->>A: Trả dữ liệu theo phiên authenticated
~~~

Sơ đồ thể hiện trường hợp ứng dụng dễ bị lỗi. Trong luồng an toàn, sau khi xác thực thành công, server phải tạo **session ID mới S2**, vô hiệu hóa S và chỉ gửi S2 cho browser của nạn nhân. Request dùng S cũ phải bị từ chối hoặc chỉ còn là anonymous nếu hệ thống chủ động duy trì một phiên anonymous mới riêng biệt.

### Attacker có thể biết hoặc áp đặt session ID bằng cách nào?

Các khả năng phụ thuộc ứng dụng, domain và cấu hình:

- Ứng dụng chấp nhận session ID trong URL hoặc tham số request, khiến attacker gửi link có ID đã biết.
- Cookie không được giới hạn domain hợp lý; một subdomain bị kiểm soát có thể cố gắng đặt cookie cho domain cha.
- Kênh HTTP không được chuyển hướng/bảo vệ đúng cách hoặc có thể bị can thiệp trên mạng.
- Ứng dụng chấp nhận session identifier do client tùy ý cung cấp mà không thay ID sau xác thực.
- XSS hoặc lỗ hổng ở một thành phần khác cho phép attacker thao tác cookie/session.
- Người dùng sử dụng một liên kết hoặc môi trường đăng nhập do attacker kiểm soát.

Không phải mọi ứng dụng đều cho phép attacker áp đặt cookie. Nhưng nếu ID có thể bị biết trước và được giữ nguyên sau đăng nhập, hệ thống có rủi ro fixation.

## 5. Điều kiện để cuộc tấn công thành công

Một kịch bản fixation thường cần đồng thời:

1. Attacker biết hoặc có thể khiến nạn nhân sử dụng một session ID cụ thể.
2. Ứng dụng chấp nhận ID đó trước đăng nhập.
3. Nạn nhân đăng nhập hoặc hoàn thành xác thực trong session đó.
4. Ứng dụng giữ nguyên ID khi nâng trạng thái xác thực.
5. Attacker có thể trình lại ID tới server và phiên vẫn còn hiệu lực.
6. Không có biện pháp bổ sung ràng buộc phiên với thiết bị/khóa hoặc phát hiện sử dụng bất thường đủ để chặn.

Chỉ sinh session ID ngẫu nhiên không giải quyết hoàn toàn fixation. CSPRNG giúp ngăn đoán ID mới, nhưng attacker có thể đã biết một ID hợp lệ do chính server tạo trước đó. **Xoay ID khi thay đổi trạng thái tin cậy** mới là kiểm soát trực tiếp.

## 6. Phòng chống cốt lõi: xoay session ID sau xác thực

Sau khi người dùng xác thực thành công, server phải cấp một session identifier mới, khó đoán và vô hiệu hóa ID cũ.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant S as Session service
    U->>B: Mở trang đăng nhập
    B->>S: Request với session anonymous S1
    S-->>B: Trang đăng nhập
    U->>B: Trình credential và hoàn tất MFA
    B->>S: Authentication result với S1
    S->>S: Xác minh credential và chính sách
    S->>S: Tạo session ID mới S2
    S->>S: Vô hiệu hóa S1 hoặc tách trạng thái anonymous
    S-->>B: Set-Cookie với S2
    B->>S: Request tiếp theo với S2
    S-->>B: Chấp nhận phiên authenticated
    Note over S: Request dùng S1 không được nhận quyền authenticated
~~~

### Yêu cầu kỹ thuật

- Session ID mới phải được sinh bằng CSPRNG của framework/runtime.
- ID cũ không được ánh xạ tới trạng thái authenticated sau khi xoay.
- Không chấp nhận đồng thời cả ID cũ và mới như hai phiên cùng quyền, trừ khi có một cơ chế chuyển tiếp được thiết kế rõ và không thể bị attacker khai thác.
- Không sao chép dữ liệu nhạy cảm hoặc quyền đã nâng từ session cũ một cách mù quáng.
- Cookie mới phải được gửi qua HTTPS và có thuộc tính phù hợp.
- Việc xoay phải được thực hiện ở server-side auth boundary, không dựa vào JavaScript tự đổi một giá trị trong browser.

### Xoay ID khác với chỉ đổi cookie

Nếu server chỉ gửi cookie mới nhưng vẫn chấp nhận ID cũ cho cùng trạng thái authenticated, attacker vẫn có thể sử dụng ID đã biết. Cần cập nhật **trạng thái phiên ở server** để ID cũ không còn quyền.

Tương tự, xóa cookie cũ ở browser nạn nhân không ảnh hưởng cookie attacker đã lưu. Server phải vô hiệu hóa ID cũ hoặc đảm bảo nó chỉ trỏ tới một phiên anonymous không có quyền.

## 7. Xoay phiên ở các thời điểm nào?

Đăng nhập là điểm quan trọng nhất, nhưng không phải điểm duy nhất mà mức tin cậy hoặc quyền có thể thay đổi.

| Sự kiện | Hành động phiên nên cân nhắc | Lý do |
| --- | --- | --- |
| Đăng nhập thành công | Bắt buộc cấp session ID mới và vô hiệu hóa ID anonymous cũ. | Chặn việc nâng một ID attacker đã biết thành phiên authenticated. |
| Hoàn tất MFA sau pending state | Xoay ID khi chuyển sang phiên đầy đủ. | ID ở giai đoạn password-only không được trở thành phiên MFA đầy đủ. |
| Step-up/reauthentication | Xoay hoặc cập nhật binding phiên theo cơ chế framework. | Ngữ cảnh xác thực và quyền sử dụng phiên đã thay đổi. |
| Chuyển sang vai trò/đặc quyền cao | Xoay ID và kiểm tra lại quyền. | Hạn chế attacker giữ ID ở trạng thái quyền thấp nhưng được nâng quyền. |
| Đổi mật khẩu hoặc authenticator | Đánh giá các phiên hiện tại; thu hồi phiên khác và xoay phiên đang dùng nếu được giữ lại. | Credential cũ có thể đã bị lộ. |
| Khôi phục tài khoản | Cấp phiên mới theo quy trình recovery; thu hồi ID và token trước đó theo policy. | Recovery là ranh giới tin cậy đặc biệt nhạy cảm. |
| Đăng xuất | Vô hiệu hóa phiên server-side và xóa cookie. | Chấm dứt quyền truy cập. |

Việc xoay ở mỗi sự kiện phải phù hợp với framework và trải nghiệm sản phẩm. Điều bắt buộc là **không giữ một ID đã biết trước đăng nhập làm ID của phiên authenticated**. Đối với thao tác khác, cần xác định rõ liệu có chuyển quyền hoặc thay đổi ngữ cảnh bảo mật hay không.

## 8. Cookie phiên an toàn

Session ID thường được truyền trong cookie. Một cấu hình cookie tốt giảm nguy cơ đọc, sửa, gửi nhầm domain hoặc gửi qua kênh không an toàn.

Ví dụ:

~~~http
Set-Cookie: __Host-session=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Các thuộc tính:

| Thuộc tính | Tác dụng | Giới hạn |
| --- | --- | --- |
| **Secure** | Chỉ gửi cookie qua kết nối HTTPS. | Cần HTTPS trên toàn bộ luồng; không tự bảo vệ khỏi XSS. |
| **HttpOnly** | JavaScript không đọc cookie qua API thông thường như document.cookie. | XSS vẫn có thể gửi request thay người dùng trong browser. |
| **SameSite=Lax/Strict** | Giảm một số request cross-site tự động gửi cookie. | Không thay thế toàn bộ CSRF protection và không trực tiếp sửa lỗi fixation. |
| **Path=/** | Giới hạn đường dẫn cookie ở root trong ví dụ. | Path không phải ranh giới bảo mật mạnh giữa ứng dụng cùng host. |
| **Không có Domain** | Tạo host-only cookie. | Cần kiểm tra các cookie cùng tên và subdomain theo cấu hình ứng dụng. |
| **Prefix __Host-** | Trình duyệt yêu cầu Secure, Path=/ và không có Domain. | Chỉ hữu ích khi trình duyệt hỗ trợ và server cấu hình đúng. |

Đối với session cookie, nên tránh thuộc tính Domain rộng như .example.test nếu không thực sự cần chia sẻ cookie giữa subdomain. Cookie domain rộng có thể làm tăng nguy cơ cookie injection/tossing từ subdomain yếu hơn.

### Cookie flags không thay thế session rotation

Secure, HttpOnly và SameSite là các lớp bảo vệ quan trọng, nhưng không ngăn được mọi dạng fixation. Nếu ứng dụng vẫn giữ nguyên session ID sau login, attacker có thể sử dụng ID đã biết bất kể cookie có HttpOnly hay SameSite.

## 9. Không truyền session ID trong URL

Một số ứng dụng cũ dùng URL rewriting, ví dụ:

~~~text
https://app.example.test/account;jsessionid=ABC123
~~~

Cách này làm session ID có thể xuất hiện trong:

- Browser history.
- Access log, proxy log và monitoring.
- Referrer header khi chuyển sang website khác.
- Link được copy, gửi qua email/chat hoặc chụp màn hình.
- Analytics và hệ thống quan sát request.

Nếu attacker có được ID từ URL, họ có thể tìm cách dùng lại phiên. URL rewriting cũng có thể làm việc cố định session ID dễ hơn nếu ứng dụng chấp nhận ID do client cung cấp.

**Khuyến nghị:** dùng cookie phiên bảo vệ qua HTTPS; tắt URL-based session tracking nếu không có yêu cầu tương thích thực sự. Không đưa session ID vào query parameter, path, fragment hoặc form hidden như một phương thức mặc định.

## 10. Sinh session ID và bảo vệ trạng thái server

Session ID cần được tạo từ CSPRNG, đủ entropy và không chứa thông tin có thể đoán như user ID, timestamp, role hoặc số thứ tự.

Các nguyên tắc:

- Dùng session manager của framework/container đã được kiểm chứng.
- Không tự sinh ID bằng Random, timestamp hoặc hash dữ liệu công khai.
- Session ID nên là giá trị opaque, không chứa PII hay quyền dưới dạng có thể đọc.
- Server lưu trạng thái phiên và kiểm tra trạng thái active/revoked.
- Giới hạn thời gian idle và absolute timeout theo rủi ro.
- Bảo vệ session store, cache, replica và backup.
- Không cho client tự chọn subject, role hoặc trạng thái authenticated qua cookie payload không được xác minh.

Session ID có entropy cao giúp chống session prediction. Nhưng nếu attacker đã biết ID trước login, entropy không ngăn fixation; server vẫn phải xoay ID.

## 11. Java Servlet: dùng cơ chế đổi session ID

Trong Java Servlet 3.1 trở lên, API **HttpServletRequest.changeSessionId()** cho phép container thay session ID hiện tại trong khi giữ lại session và các thuộc tính của nó theo hành vi container.

Ví dụ minh họa sau chỉ gọi đổi ID **sau khi xác thực đã thành công**:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

public final class LoginSessionHandler {

    public void onAuthenticationSuccess(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            session = request.getSession(true);
        }

        // Chỉ gọi sau khi server đã xác minh đầy đủ credential
        // và các yếu tố MFA bắt buộc.
        request.changeSessionId();

        // Ghi ngữ cảnh xác thực server-side sau khi xoay ID.
        session.setAttribute("authenticated", Boolean.TRUE);
        session.setAttribute("authenticationMethod", "passkey");
    }
}
~~~

Đây là ví dụ khái niệm. Trong code thực tế:

- Chỉ đặt trạng thái authenticated sau khi toàn bộ chính sách xác thực đạt.
- Không dùng thuộc tính session do client tự gửi để quyết định quyền.
- Kiểm tra hành vi của container, session store và framework đang dùng.
- Với dự án dùng package javax.servlet cũ, tên package khác với jakarta.servlet; chọn theo phiên bản ứng dụng.
- Không gọi changeSessionId() trước khi xác thực rồi cho rằng đã chống fixation.

### Cách thay thế: invalidate và tạo session mới

Nếu nền tảng không hỗ trợ đổi ID, có thể hủy session cũ rồi tạo session mới, nhưng cần cẩn trọng với dữ liệu cần giữ:

~~~java
HttpSession oldSession = request.getSession(false);

if (oldSession != null) {
    oldSession.invalidate();
}

HttpSession newSession = request.getSession(true);
newSession.setAttribute("authenticated", Boolean.TRUE);
~~~

Chỉ chuyển các dữ liệu anonymous không nhạy cảm thật sự cần thiết, như lựa chọn ngôn ngữ hoặc giỏ hàng đã được kiểm tra. Không sao chép mọi thuộc tính từ session cũ vì có thể giữ lại dữ liệu hoặc trạng thái do attacker kiểm soát. Cũng cần xử lý request đồng thời, cookie cũ và trạng thái server-side để ID cũ không còn hợp lệ.

## 12. Spring Security và framework quản lý session

Với ứng dụng Spring Security, nên sử dụng cơ chế **session fixation protection** do framework cung cấp. Cấu hình và hành vi mặc định phụ thuộc phiên bản Spring Security, Servlet container và loại ứng dụng.

Một cấu hình theo phong cách DSL có thể biểu diễn ý định:

~~~java
http
    .sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.changeSessionId())
    );
~~~

Đây là ví dụ cấu hình khái niệm; cần kiểm tra API đúng với phiên bản Spring Security của dự án. Một số phiên bản/container hỗ trợ changeSessionId, trong khi các chiến lược khác có thể tạo session mới hoặc migrate một số thuộc tính.

Khi review framework:

- Xác nhận session fixation protection thực sự được bật.
- Hiểu chiến lược đang dùng: đổi ID, tạo session mới hay migrate session.
- Kiểm tra điều gì xảy ra khi xác thực qua form login, custom authentication filter, OAuth2/OIDC login và MFA riêng.
- Không tắt cơ chế bảo vệ chỉ để giữ session attribute mà không đánh giá rủi ro.
- Kiểm thử ID trước và sau login bằng browser hoặc integration test.
- Kiểm tra logout, concurrent session và distributed session store.

**Không nên tự viết bộ quản lý session chỉ để thay thế một tính năng mà framework đã hỗ trợ.** Hãy dùng cơ chế chuẩn, xác minh phiên bản và viết test ở ranh giới xác thực thực tế.

## 13. Session fixation trong luồng MFA và SSO

### 13.1 MFA nhiều bước

Giả sử người dùng nhập mật khẩu đúng, server tạo trạng thái pending MFA. Nếu attacker biết session ID ở bước này và ứng dụng giữ nguyên ID sau khi MFA hoàn tất, attacker có thể nhận phiên đã xác thực đầy đủ.

Luồng an toàn:

1. Tạo hoặc dùng transaction pending có quyền rất hạn chế.
2. Xác minh mật khẩu và đánh dấu primary factor đã đạt ở server.
3. Xác minh MFA trong cùng transaction, đúng subject và còn hạn.
4. Khi mọi yếu tố đạt, xoay session ID.
5. Vô hiệu hóa ID pending hoặc tách nó khỏi phiên authenticated.
6. Chỉ sau đó mới cấp quyền truy cập thông thường.

Không để session pending MFA gọi API riêng tư, thay credential hoặc thêm authenticator.

### 13.2 SSO/OIDC

Trong luồng SSO, ứng dụng có thể tạo session trước khi chuyển hướng tới IdP. Sau callback thành công, ứng dụng phải thiết lập phiên authenticated theo cách chống fixation.

Cần kiểm tra:

- State ràng buộc callback với transaction do RP khởi tạo.
- Nonce được xác minh nếu OIDC flow yêu cầu.
- Authorization code được đổi đúng client, redirect URI và PKCE verifier.
- ID token được xác minh chữ ký, issuer, audience, thời hạn và nonce.
- Session ID của ứng dụng được xoay khi kết quả xác thực được chấp nhận.
- Callback không cho phép attacker gắn một kết quả xác thực vào session khác.

State và nonce bảo vệ các phần khác nhau của luồng OIDC; chúng không thay thế việc xoay session ID tại ứng dụng.

## 14. Logout, thu hồi và phiên phân tán

Sau logout, server phải đánh dấu phiên không còn hiệu lực. Chỉ xóa cookie phía browser không đủ vì attacker có thể đã sao chép cookie trước đó.

Các bước thường cần:

1. Xác định phiên hiện tại từ cookie đã kiểm chứng.
2. Đánh dấu session ID revoked/invalid ở session store.
3. Xóa hoặc hết hạn cookie ở browser với đúng tên, Path và Domain đã dùng.
4. Thu hồi refresh token hoặc token liên quan nếu luồng sử dụng chúng.
5. Không chấp nhận ID cũ từ request tiếp theo.
6. Ghi audit phù hợp, không ghi raw session ID.

Với hệ thống nhiều instance:

- Tất cả node phải nhìn thấy trạng thái phiên và trạng thái thu hồi nhất quán theo yêu cầu.
- Cache không được giữ quyền của ID cũ lâu hơn chính sách cho phép.
- Khi xoay ID, cần xử lý request đồng thời và replication.
- Sticky session không thay thế việc chia sẻ trạng thái hoặc invalidation an toàn.
- Nếu session ID bị lộ, cần có khả năng thu hồi phiên cụ thể và các phiên liên quan theo chính sách.

### Logout không nhất thiết xóa mọi dấu vết browser

Server phải vô hiệu hóa phiên trước; sau đó cookie được xóa bằng Set-Cookie hết hạn với cùng thuộc tính định danh. Dữ liệu cache phía client và các token khác cần được xử lý riêng. Không dựa vào việc người dùng đóng tab hoặc browser để kết thúc phiên.

## 15. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Giữ nguyên session ID sau login | ID attacker biết trước được nâng thành authenticated. | Xoay ID và vô hiệu hóa ID cũ sau xác thực. |
| Chỉ đổi cookie ở browser | Server vẫn chấp nhận ID cũ. | Cập nhật trạng thái session store và thu hồi ID cũ. |
| Bật HttpOnly rồi cho rằng đã chống fixation | HttpOnly không ngăn ID bị biết trước hoặc giữ nguyên. | Kết hợp rotation, cookie flags và kiểm soát vòng đời. |
| Dùng session ID trong URL | ID có thể rò qua log/history/referrer và bị cố định. | Dùng cookie bảo vệ; tắt URL rewriting nếu có thể. |
| Cho phép cookie Domain quá rộng | Subdomain yếu có thể ảnh hưởng cookie của domain cha. | Dùng host-only cookie và cân nhắc prefix __Host-. |
| Không xoay sau MFA | ID pending có thể trở thành phiên đầy đủ. | Xoay khi MFA hoàn tất và vô hiệu hóa trạng thái pending. |
| Migrate mọi session attribute | Dữ liệu do attacker kiểm soát có thể đi vào phiên authenticated. | Chỉ chuyển dữ liệu cần thiết, đã xác thực và không nhạy cảm. |
| Tự sinh ID bằng timestamp/Random | Có nguy cơ session prediction. | Dùng session manager/CSPRNG của nền tảng. |
| Logout chỉ xóa cookie | ID đã sao chép vẫn có thể được server chấp nhận. | Revoke server-side và hết hạn cookie. |
| Chỉ kiểm thử giao diện | Không phát hiện server vẫn chấp nhận ID cũ. | Test session ID và trạng thái trên server/API. |

## 16. Kiểm thử session fixation

Kiểm thử cần chứng minh **session ID thay đổi** và **ID cũ không còn quyền authenticated**.

### 16.1 Kịch bản kiểm thử chính

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Anonymous → authenticated | Ghi cookie trước login, hoàn tất login, so sánh cookie sau login. | ID mới khác ID cũ. |
| Dùng lại ID cũ | Gửi request API bằng cookie trước login. | Không nhận dữ liệu hoặc quyền của phiên đã xác thực. |
| Pending MFA → authenticated | Ghi ID trước khi hoàn tất MFA rồi so sánh sau MFA. | ID được xoay khi full authentication đạt; ID pending không có quyền đầy đủ. |
| Step-up | Ghi ID trước và sau step-up. | Chính sách xoay/binding được thực hiện; ID cũ không được hưởng quyền nâng. |
| Cookie injection qua subdomain | Kiểm tra cookie cùng tên và phạm vi domain trong môi trường thử. | Cookie session nhạy cảm không bị subdomain không tin cậy ghi đè theo cấu hình. |
| URL rewriting | Thử session ID trong URL/path/query nếu ứng dụng hỗ trợ. | Không chấp nhận session identifier từ URL trong cấu hình an toàn. |
| Logout | Lưu cookie trước logout rồi trình lại. | Server từ chối ID đã revoke. |
| Nhiều node | Login qua node A, gửi ID cũ tới node B. | Node B cũng từ chối ID cũ theo trạng thái chia sẻ. |
| Đăng nhập SSO | So sánh session trước redirect và sau callback. | Session authenticated dùng ID mới. |
| Thay đổi mật khẩu/credential | Dùng phiên cũ sau sự kiện bảo mật. | Phiên được xử lý theo policy; phiên bị thu hồi không còn truy cập. |

### 16.2 Ví dụ kiểm thử tích hợp

Giả mã test:

~~~text
anonymousCookie = GET /login -> capture SESSION_ID_1

loginResponse = POST /login
    Cookie: SESSION_ID_1
    credentials: valid

authenticatedCookie = capture cookie from loginResponse

assert authenticatedCookie.id != SESSION_ID_1

oldSessionResponse = GET /api/me
    Cookie: SESSION_ID_1

assert oldSessionResponse is not authenticated

newSessionResponse = GET /api/me
    Cookie: authenticatedCookie.id

assert newSessionResponse identifies the expected subject
~~~

Đây là giả mã; test thực tế cần dùng tài khoản thử, framework/container đang triển khai và kiểm tra cả session store. Chỉ kiểm tra hai cookie khác nhau là chưa đủ: cần xác nhận ID cũ không còn truy cập được dữ liệu authenticated.

### 16.3 Bằng chứng kiểm thử cần lưu

- Session ID trước login và sau login ở dạng test-only hoặc giá trị đã che/hash.
- Kết quả xác minh ID cũ không còn authenticated.
- Kết quả xác minh ID mới ánh xạ đúng subject.
- Trạng thái sau MFA/step-up.
- Kết quả logout và revoke trên tất cả node liên quan.
- Log không chứa session ID rõ trong môi trường production.

Không đưa cookie hoặc session ID thật vào ticket, báo cáo hoặc ảnh chụp màn hình.

## 17. Tự kiểm tra

**Câu 1.** Session fixation khác session hijacking ở điểm nào?

**Đáp án:** Fixation bắt đầu khi attacker biết hoặc áp đặt session ID trước lúc nạn nhân đăng nhập và ứng dụng giữ ID đó sau đăng nhập. Hijacking là attacker lấy một ID của phiên đã xác thực. Hai lỗi có thể kết hợp nhưng khác thời điểm và nguyên nhân.

**Câu 2.** Vì sao session ID ngẫu nhiên vẫn có thể bị fixation?

**Đáp án:** Attacker không nhất thiết phải đoán ID. Họ có thể biết một ID anonymous hợp lệ do server tạo rồi khiến nạn nhân sử dụng nó. Nếu server giữ ID sau login, tính ngẫu nhiên không ngăn được tấn công.

**Câu 3.** Biện pháp cốt lõi sau khi đăng nhập thành công là gì?

**Đáp án:** Cấp session ID mới bằng cơ chế an toàn và vô hiệu hóa ID cũ ở server. Phiên authenticated chỉ được gắn với ID mới.

**Câu 4.** HttpOnly có ngăn session fixation không?

**Đáp án:** Không. HttpOnly hạn chế JavaScript đọc cookie, nhưng không đảm bảo ID đã biết trước sẽ được xoay sau login. Cần session rotation và các biện pháp cookie phù hợp.

**Câu 5.** Vì sao không nên truyền session ID trong URL?

**Đáp án:** URL có thể xuất hiện trong browser history, access log, proxy log, referrer và liên kết được chia sẻ. Attacker có thể lấy hoặc cố định ID từ những nơi này.

**Câu 6.** Khi password đã đúng nhưng MFA chưa hoàn tất, session nên có quyền gì?

**Đáp án:** Chỉ quyền tối thiểu để hoàn tất MFA. Khi toàn bộ chính sách đạt, server xoay ID và tạo phiên authenticated đầy đủ.

**Câu 7.** Vì sao không nên migrate tất cả thuộc tính của anonymous session sang authenticated session?

**Đáp án:** Một số thuộc tính có thể do attacker hoặc client kiểm soát. Chỉ chuyển dữ liệu cần thiết, đã kiểm tra và không mang quyền hoặc trạng thái nhạy cảm.

**Câu 8.** Nếu server gửi cookie mới nhưng vẫn chấp nhận cookie cũ, đã chống fixation chưa?

**Đáp án:** Chưa. Attacker vẫn có thể dùng cookie cũ. Server phải vô hiệu hóa ID cũ hoặc bảo đảm nó không còn ánh xạ tới trạng thái authenticated.

**Câu 9.** Vì sao cần kiểm thử trên nhiều node khi session store phân tán?

**Đáp án:** Một node có thể đã cập nhật ID nhưng node khác còn cache trạng thái cũ. Cần xác minh ID cũ bị từ chối nhất quán theo yêu cầu hệ thống.

**Câu 10.** Khi logout, xóa cookie phía browser có đủ không?

**Đáp án:** Không. Server phải thu hồi phiên; cookie attacker đã sao chép vẫn có thể được trình lại nếu session store còn chấp nhận.

## Ghi nhớ

**Session fixation** xảy ra khi attacker biết hoặc khiến nạn nhân dùng một session ID trước đăng nhập, rồi ứng dụng giữ nguyên ID đó sau khi xác thực thành công. Attacker có thể trình lại ID đã biết để sử dụng phiên của nạn nhân. Đây là vấn đề về **vòng đời và chuyển trạng thái của session**, khác với việc đánh cắp một phiên đã xác thực.

Biện pháp cốt lõi là **xoay session ID ở ranh giới tin cậy** — đặc biệt sau login và khi hoàn tất MFA — đồng thời vô hiệu hóa ID cũ ở server. Dùng session manager/framework đã được kiểm chứng, cookie Secure/HttpOnly/SameSite và host-only phù hợp, không truyền ID trong URL, bảo vệ session store và thu hồi phiên khi logout hoặc có sự cố. Kiểm thử phải chứng minh cả ID mới hợp lệ lẫn ID cũ không còn quyền authenticated.
