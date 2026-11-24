# Session fixation — Cố định định danh phiên để chiếm quyền đăng nhập

## 1. Vấn đề cốt lõi

**Session fixation** là kiểu tấn công trong đó kẻ tấn công khiến trình duyệt của nạn nhân sử dụng **một định danh phiên (session ID) mà kẻ tấn công đã biết hoặc kiểm soát được**, sau đó chờ nạn nhân đăng nhập. Nếu ứng dụng giữ nguyên định danh đó khi chuyển phiên từ **chưa xác thực** sang **đã xác thực**, kẻ tấn công có thể sử dụng chính session ID ấy để truy cập phiên đăng nhập của nạn nhân.

Điểm nguy hiểm nằm ở **sự chuyển đổi mức tin cậy của phiên**:

- Trước đăng nhập, session ID chỉ gắn với trạng thái khách chưa được xác thực.
- Sau đăng nhập, cùng session ID có thể gắn với danh tính, vai trò và quyền truy cập.
- Nếu ID đã bị một bên khác biết từ trước, ứng dụng vô tình nâng một định danh không còn bí mật thành **chứng cứ truy cập tài khoản**.

Trong mô hình bảo mật token, session ID thường là một **opaque bearer credential**: người sở hữu giá trị cookie phiên có thể gửi nó cho máy chủ để truy cập trạng thái xác thực. Đây không nhất thiết là **JWT**, cũng không đồng nghĩa với **OAuth access token**, **refresh token** hoặc **OIDC ID token**. Tuy nhiên, session fixation và token theft đều minh họa một nguyên tắc chung: **khả năng chứng minh danh tính không thể chỉ dựa vào một giá trị đã bị người khác biết**.

Session fixation thuộc nhóm **Threats** của hệ thống token security vì nó tác động trực tiếp tới vòng đời phiên, phát hành/luân chuyển credential và ranh giới xác thực. Biện pháp quan trọng nhất là **thay session ID khi xác thực thành công hoặc khi mức đặc quyền tăng**, đồng thời vô hiệu hóa ID cũ.

> Một session ID ngẫu nhiên, có độ dài lớn vẫn có thể bị fixation nếu kẻ tấn công lấy được **một ID hợp lệ** rồi khiến nạn nhân sử dụng nó. Entropy cao giúp chống **đoán ID**, không tự chống việc **gắn sẵn ID** vào trình duyệt nạn nhân.

## 2. Phân biệt session ID với các loại token

| Đối tượng | Công dụng | Ai thường xác minh? | Liên quan tới session fixation |
|---|---|---|---|
| **Session ID trong cookie** | Tra cứu phiên đăng nhập ở server hoặc trạng thái phiên tương đương | Ứng dụng web/BFF hoặc session middleware | **Mục tiêu điển hình**: ID được giữ lại sau khi nạn nhân đăng nhập |
| **JWT access token** | Cho phép client gọi API theo audience và quyền được cấp | Resource server | Có nguy cơ bị lấy cắp hoặc replay; không tự đồng nghĩa với fixation của cookie phiên |
| **Opaque access token** | Bearer credential truy cập tài nguyên; metadata được lưu hoặc introspect | Resource server/authorization server | Cần bảo vệ khỏi lộ và dùng lại; có thể bị lạm dụng nếu ứng dụng coi giá trị do bên khác cài sẵn là phiên đã xác thực |
| **Refresh token** | Xin access token mới tại token endpoint | Authorization server | Bị đánh cắp sẽ kéo dài khả năng truy cập; rotation và sender-constraining xử lý rủi ro khác với session ID rotation |
| **OIDC ID token** | Cung cấp thông tin về sự kiện xác thực cho OIDC client | OIDC relying party/client | Không thay thế session ID của ứng dụng; client thường tạo phiên cục bộ sau khi xác minh ID token |
| **OAuth state / OIDC nonce** | Ràng buộc authorization response hoặc ID token với giao dịch đăng nhập | OAuth/OIDC client | Quan trọng để chống login CSRF, code injection và mix-up; không tự giải quyết fixation của session cookie |

Không phải mọi ứng dụng đều có HTTP session. Một API stateless nhận access token qua **Authorization** header có thể không gặp đúng mẫu tấn công session fixation truyền thống. Ngược lại, nhiều hệ thống dùng OAuth/OIDC để đăng nhập nhưng vẫn có **cookie phiên cục bộ**: chính cookie này cần luân chuyển khi phiên được nâng cấp từ khách sang người dùng đã xác thực.

## 3. Cách một cuộc tấn công session fixation diễn ra

Giả sử trang thương mại điện tử tạo session ID **S0** trước khi khách đăng nhập, để lưu giỏ hàng hoặc OAuth transaction.

1. Kẻ tấn công có được **S0 hợp lệ** do ứng dụng phát hành, ví dụ bằng cách tạo một phiên khách của chính họ.
2. Bằng một lỗ hổng khác, kẻ tấn công khiến trình duyệt nạn nhân gửi **S0** cho ứng dụng, chẳng hạn do cookie từ subdomain không đáng tin cậy, cookie injection, XSS hoặc việc ứng dụng chấp nhận session ID trong URL.
3. Nạn nhân vào trang đăng nhập với cookie **S0** và xác thực thành công.
4. Máy chủ **không đổi session ID**; thay vào đó ghi thông tin người dùng vào bản ghi session ứng với **S0**.
5. Kẻ tấn công gửi S0 từ môi trường của mình; nếu hệ thống chỉ dựa vào ID ấy và phiên còn hiệu lực, request được xử lý như phiên của nạn nhân.

~~~mermaid
sequenceDiagram
    participant A as Kẻ tấn công
    participant V as Trình duyệt nạn nhân
    participant S as Ứng dụng web
    A->>S: Tạo phiên khách
    S-->>A: Session ID S0
    A-->>V: Cài sẵn S0 qua điểm yếu khác
    V->>S: Truy cập trang đăng nhập, Cookie S0
    S-->>V: Trang đăng nhập
    V->>S: Gửi thông tin xác thực, Cookie S0
    S->>S: Lỗi: giữ S0 rồi gắn userId vào S0
    S-->>V: Đăng nhập thành công, vẫn dùng S0
    A->>S: Gửi Cookie S0
    S-->>A: Truy cập được phiên đã xác thực
~~~

Điều kiện để cuộc tấn công thành công bao gồm:

- Kẻ tấn công biết hoặc chọn được **một ID mà server sẽ chấp nhận**. Trong hệ thống quản lý session nghiêm ngặt, một chuỗi bất kỳ do kẻ tấn công tự bịa thường không được chấp nhận; do đó kẻ tấn công có thể phải lấy trước một ID hợp lệ.
- Có đường để nạn nhân thực sự dùng ID ấy.
- Server **không làm mất hiệu lực ID cũ** khi đăng nhập.
- Session ID vẫn là credential đủ để server cấp quyền truy cập.

Việc cài sẵn cookie không phải lúc nào cũng khả thi. Các thuộc tính cookie, nguồn gốc trang, trình duyệt, cấu hình miền, HTTPS và cách session middleware xử lý ID lạ đều ảnh hưởng tới khả năng khai thác.

### 3.1. Ví dụ HTTP tối giản

Trước đăng nhập, ứng dụng cấp một cookie phiên:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=S0_RANDOM_OPAQUE_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Khi đăng nhập thành công, ứng dụng **có lỗi** giữ nguyên S0:

~~~text
Trước login:  S0 -> {authenticated: false, cart: [...]}
Sau login:    S0 -> {authenticated: true, userId: "victim-42", cart: [...]}
                    ^
                    ID không đổi; có thể đã bị kẻ khác biết
~~~

Cách xử lý mong muốn là tạo ID mới **S1**, chỉ trao nó cho trình duyệt vừa hoàn tất xác thực, vô hiệu hóa S0:

~~~http
HTTP/1.1 303 See Other
Location: /account
Set-Cookie: __Host-session=S1_NEW_RANDOM_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

~~~text
Trước login:  S0 -> {authenticated: false, ...}

Chuyển đổi:
              S0 -> INVALIDATED
              S1 -> {authenticated: true, userId: "victim-42", ...}

Sau login:
  Cookie S1 -> Có thể truy cập với quyền đã cấp
  Cookie S0 -> Bị từ chối hoặc chỉ trở thành một phiên khách mới độc lập
~~~

Tên cookie **__Host-session** trong ví dụ được dùng để minh họa cookie có tiền tố **__Host-**. Trình duyệt hỗ trợ prefix này yêu cầu cookie có **Secure**, **Path=/** và **không có Domain**, giúp hạn chế khả năng subdomain tự đặt cookie cùng tên cho host chính. Đây là lớp giảm thiểu hữu ích, nhưng **không thay thế việc đổi session ID** sau đăng nhập.

## 4. Session fixation khác các kiểu tấn công lân cận ra sao?

| Kiểu tấn công | Kẻ tấn công làm gì? | Sai sót cốt lõi | Bảo vệ quan trọng |
|---|---|---|---|
| **Session fixation** | Gắn trước ID mình biết cho nạn nhân, chờ nạn nhân đăng nhập | Giữ nguyên session ID qua ranh giới xác thực | Rotate session ID, vô hiệu hóa ID cũ |
| **Session hijacking** | Đánh cắp session ID **sau** khi nạn nhân đã đăng nhập | Session credential bị lộ và được sử dụng lại | HTTPS, cookie security, chống XSS, phát hiện/thu hồi phiên |
| **Session prediction** | Đoán session ID có giá trị | ID không đủ ngẫu nhiên hoặc dễ suy đoán | CSPRNG, entropy đủ cao, ID không tuần tự |
| **Session replay** | Gửi lại credential hoặc request đã quan sát | Credential có thể dùng lại và chưa bị chặn | Kiểm tra hiệu lực, sender-constraining khi áp dụng, phát hiện replay phù hợp |
| **Login CSRF / session swapping** | Khiến nạn nhân đăng nhập vào **tài khoản của kẻ tấn công** | Không ràng buộc luồng đăng nhập với ý định/phiên đúng | CSRF protection, OAuth state, OIDC nonce, kiểm tra giao dịch |
| **OAuth authorization code injection** | Đưa code của một luồng khác vào callback | Không ràng buộc code/response với giao dịch hợp lệ | state, PKCE, issuer identification, OIDC kiểm tra token |

Các tấn công có thể kết hợp. Ví dụ, nếu kẻ tấn công đã cố định được **pre-auth session**, họ có thể có thêm khả năng quan sát dữ liệu giao dịch gắn với session đó trong môi trường riêng; bởi vậy **state** không nên là cơ chế duy nhất được viện dẫn để kết luận rằng mọi vấn đề session đã được khắc phục.

**Logout và session fixation cũng là hai vấn đề khác nhau.** Đổi ID khi login bảo vệ thời điểm nâng cấp quyền; logout cần **vô hiệu hóa session tại server**, xóa cookie tương ứng và xử lý access/refresh token theo chính sách riêng.

## 5. Các con đường khiến nạn nhân nhận session ID do kẻ tấn công biết

### 5.1. Cookie từ subdomain không đáng tin cậy

Một ứng dụng chạy tại **app.example.test** có thể dùng cookie với thuộc tính Domain rộng, ví dụ **Domain=example.test**. Trong một số cấu hình, một subdomain bị chiếm quyền hoặc do bên thứ ba quản lý có thể đặt cookie có phạm vi miền cha. Từ đó xuất hiện nguy cơ **cookie tossing**: trình duyệt gửi nhiều cookie cùng tên hoặc gửi cookie do bên khác đã cài, còn phía server xử lý không nhất quán.

Cần chú ý:

- Cookie cùng tên nhưng khác **Domain/Path** có thể cùng xuất hiện trong request; thứ tự không phải bằng chứng đáng tin cậy về nguồn phát hành.
- Header **Cookie** ở phía server không chứa thông tin Domain/Path ban đầu để dễ phân biệt nguồn.
- Chỉ đọc cookie đầu tiên hoặc cookie cuối cùng theo một quy tắc tùy tiện có thể gây bất nhất và bị khai thác.
- Dùng cookie **host-only**, tránh Domain rộng không cần thiết; nếu phù hợp, áp dụng tiền tố **__Host-** và đặt tên cookie riêng cho từng ứng dụng.
- Không để một subdomain không đáng tin cậy quyết định session credential của ứng dụng bảo mật cao.

### 5.2. Session ID trong URL hoặc tham số do client quyết định

Nếu ứng dụng nhận session ID từ URL, ví dụ:

~~~text
https://app.example.test/home?sid=S0
~~~

thì ID có thể bị lộ trong lịch sử trình duyệt, log, liên kết được chia sẻ và một số đường dẫn referrer. Kẻ tấn công cũng dễ dẫn nạn nhân tới URL đã có **sid** định sẵn.

Ứng dụng không nên dùng URL rewriting mang session ID làm cơ chế quản lý phiên đăng nhập. Khi có yêu cầu HTTP chứa một session ID không hợp lệ hoặc không được server phát hành, **không nâng nó thành phiên hợp lệ** chỉ vì client đã gửi giá trị ấy. Server nên tự tạo ID mới từ bộ sinh số ngẫu nhiên mật mã.

### 5.3. XSS, phản hồi HTTP bị can thiệp, trình duyệt/thiết bị bị chiếm quyền

Nếu ứng dụng có **XSS** hoặc phục vụ nội dung nhạy cảm qua kênh không được TLS bảo vệ, kẻ tấn công có thể có khả năng ghi đè session cookie hoặc thao túng luồng đăng nhập. Thuộc tính **HttpOnly** hạn chế JavaScript đọc/ghi cookie theo đường thông thường của document.cookie, nhưng không chữa mọi biến thể XSS: mã độc vẫn có thể điều khiển request hoặc lạm dụng hành vi ứng dụng. HTTPS cùng **Secure** giúp bảo vệ cookie trên đường truyền, nhưng cần tránh mọi endpoint không an toàn có thể ảnh hưởng tới cookie.

Sự hiện diện của một lỗ hổng cho phép **cài đặt ID** không có nghĩa lúc nào cũng đã xảy ra **đánh cắp phiên**. Điều kiện quyết định fixation là ID ấy được hệ thống giữ lại khi session được xác thực.

## 6. Thiết kế vòng đời session có chống fixation

### 6.1. Các trạng thái cần nhận diện

~~~mermaid
stateDiagram-v2
    [*] --> ANONYMOUS: Cấp session khách S0
    ANONYMOUS --> AUTHENTICATED: Xác thực thành công, đổi S0 thành S1
    ANONYMOUS --> EXPIRED: Hết hạn hoặc hủy
    AUTHENTICATED --> PRIVILEGED: Step-up/MFA thành công, đổi S1 thành S2
    AUTHENTICATED --> REVOKED: Logout/thu hồi
    PRIVILEGED --> REVOKED: Logout/thu hồi
    AUTHENTICATED --> EXPIRED: Idle/absolute timeout
    PRIVILEGED --> EXPIRED: Idle/absolute timeout
    REVOKED --> [*]
    EXPIRED --> [*]
~~~

Session ID mới phải được cấp **ngay tại ranh giới thay đổi quyền**. Những mốc điển hình:

1. **Đăng nhập thành công** từ phiên khách sang phiên đã xác thực.
2. **Step-up authentication hoặc hoàn tất MFA** khi hệ thống nâng mức bảo đảm xác thực, nếu trước đó đã có phiên xác thực một phần.
3. **Nâng vai trò/đặc quyền nhạy cảm**, ví dụ bắt đầu một phiên quản trị hoặc chuyển sang quyền thực hiện thao tác rủi ro cao.
4. **Khôi phục tài khoản/đổi thông tin xác thực quan trọng** khi chính sách quy định phải cấp lại session, yêu cầu đăng nhập lại hoặc thu hồi các phiên cũ.

Không có yêu cầu phải đổi ID trước **mọi request bình thường**; làm vậy dễ gây lỗi đồng thời và tải không cần thiết. Chọn các **mốc chuyển đổi tin cậy rõ ràng** và bảo đảm old ID không còn được dùng với mức quyền mới.

### 6.2. Quy trình rotation an toàn

Một quy trình tổng quát cho session dựa trên server:

1. Kiểm tra thông tin đăng nhập hoặc kết quả OAuth/OIDC callback, xác minh các điều kiện tương ứng.
2. Xác định session hiện hành đã được tạo và đang ở trạng thái nào.
3. **Sinh session ID mới bằng CSPRNG** hoặc yêu cầu session framework thay ID theo cơ chế được hỗ trợ.
4. **Ngừng chấp nhận session ID cũ**; nếu cần duy trì một số dữ liệu chưa nhạy cảm như giỏ hàng, chỉ chuyển dữ liệu có chủ đích sang session mới.
5. Gắn danh tính đã xác minh và mức quyền mới với **ID mới**.
6. Trả cookie mới qua HTTPS với thuộc tính bảo vệ phù hợp; kiểm tra server không vô tình hồi sinh phiên cũ.
7. Thực thi đồng bộ trên các instance; cập nhật và thu hồi session một cách nhất quán.

Một lỗi nguy hiểm là **cấp cookie S1 mới nhưng vẫn giữ S0 tại session store với cùng quyền**. Nạn nhân nhìn thấy cookie mới còn kẻ tấn công tiếp tục sử dụng S0: bề ngoài đã “rotate” nhưng tấn công vẫn thành công.

Trong một hệ thống sử dụng **một Session ID cho nhiều trạng thái**, việc xóa mọi session dữ liệu trước đăng nhập có thể làm mất CSRF token, giỏ hàng hoặc dữ liệu OAuth transaction. Hãy thiết kế rõ dữ liệu nào cần giữ, dữ liệu nào cần xóa và **không mang trạng thái xác thực chưa được xác minh sang phiên mới**. Dựa vào cơ chế đổi ID được framework quản lý thay vì tự sao chép toàn bộ thuộc tính của session.

### 6.3. Nguyên tắc quản lý session ID

- Session ID phải **không dự đoán được**; tạo từ bộ sinh số ngẫu nhiên mật mã, không lấy từ username, timestamp, địa chỉ IP hoặc bộ đếm.
- Chỉ chấp nhận ID **đã phát hành hợp lệ** và thuộc phiên chưa bị vô hiệu hóa; không tin ID tự chọn từ request.
- Không để giá trị ID xuất hiện trong URL, log ứng dụng, telemetry, exception, analytics hoặc error page.
- Cấu hình **idle timeout** và **absolute timeout** phù hợp với độ nhạy nghiệp vụ.
- Xóa hoặc thu hồi bản ghi server-side khi logout và khi phát hiện sự cố; việc trình duyệt xóa cookie chỉ là một phần của quy trình.
- Với hệ thống nhiều instance, việc đổi/thu hồi session phải có hiệu lực xuyên cụm; kiểm thử cache và session store phân tán.
- Dùng **HTTPS** và chính sách chống XSS, CSRF như các lớp bảo vệ bổ trợ.

## 7. Bảo vệ cookie phiên

Ví dụ cookie phiên đăng nhập:

~~~http
Set-Cookie: __Host-session=<OPAQUE_RANDOM_SESSION_ID>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

| Thuộc tính/biện pháp | Mục đích | Điều cần hiểu đúng |
|---|---|---|
| **Secure** | Giới hạn gửi cookie qua kết nối bảo mật | Không thay thế việc bảo vệ mọi trang, endpoint và cấu hình HTTPS |
| **HttpOnly** | Ngăn JavaScript truy cập cookie theo API cookie thông thường | Không loại bỏ XSS hoặc việc mã độc gửi request cùng cookie |
| **SameSite=Lax/Strict/None** | Kiểm soát bối cảnh cross-site gửi cookie | Lựa chọn phải phù hợp luồng đăng nhập, OIDC redirect và yêu cầu CSRF; None cần Secure trong trình duyệt hiện đại |
| **Path** | Giới hạn đường dẫn gửi cookie | Không phải ranh giới bảo mật độc lập trước các đường dẫn khác cùng origin |
| **Domain** | Quy định phạm vi hostname | Ưu tiên **không đặt Domain** để cookie là host-only khi có thể |
| **__Host- prefix** | Yêu cầu Secure, Path=/, không có Domain tại trình duyệt hỗ trợ | Giảm nguy cơ subdomain đặt cookie host chính; không bảo vệ server không rotate ID |
| **Expires/Max-Age** | Điều khiển thời gian cookie tồn tại ở trình duyệt | Server phải tự có timeout và cơ chế thu hồi; cookie còn không có nghĩa session còn |
| **Cache-Control: no-store** cho phản hồi nhạy cảm | Hạn chế cache thông tin xác thực trên đường HTTP | Không bảo vệ cookie bị biết từ trước |

**SameSite không thay thế CSRF token hay các biện pháp xác minh nguồn request phù hợp.** Luồng OAuth/OIDC có thể trở về từ IdP khác site: redirect GET thường phù hợp với nhiều thiết lập Lax, nhưng flow dùng form_post hoặc yêu cầu cross-site đặc thù có thể cần cấu hình khác. Việc đổi chính sách cookie phải đi kèm kiểm thử callback đăng nhập, CSRF và đăng xuất.

Với cookie dùng để **xóa session**, phản hồi xóa phải khớp tên và phạm vi **Domain/Path** của cookie cần xóa. Tuy nhiên, xóa cookie ở client không đủ nếu ID cũ vẫn còn quyền tại server.

## 8. Session fixation trong OAuth 2.0/OIDC

OAuth/OIDC thường có hai lớp phiên:

- **Phiên tại authorization server / OpenID Provider:** giữ trạng thái người dùng đã đăng nhập với IdP.
- **Phiên cục bộ tại OAuth/OIDC client**, ví dụ ứng dụng web hoặc **Backend for Frontend (BFF)**: giữ trạng thái người dùng tại ứng dụng sau khi callback thành công.

Ngoài ra, client có thể có **pre-login transaction** để lưu state, PKCE code_verifier, nonce và issuer dự kiến. Một thiết kế tốt phải bảo vệ cả giao dịch này lẫn phiên hậu đăng nhập.

### 8.1. Lỗ hổng phổ biến: callback hoàn tất nhưng vẫn dùng session khách

Giả sử ứng dụng lưu OAuth transaction trong session khách **S0**:

~~~text
S0 (khách):
  oauth_state = "random-state"
  pkce_code_verifier = "secret-verifier"
  expected_issuer = "https://idp.example.test"
  authenticated = false
~~~

Người dùng hoàn tất đăng nhập ở IdP, trình duyệt quay về callback với authorization code. Client kiểm tra state, đổi code lấy token, xác minh ID token và quyết định đăng nhập người dùng. Nếu client chỉ cập nhật:

~~~text
S0:
  authenticated = true
  principal = "victim-42"
~~~

thì vấn đề fixation vẫn còn. **state đúng, PKCE hợp lệ và ID token được ký đúng không có nghĩa session S0 vốn bí mật**. Tại callback, client cần chuyển sang **session ID mới**, bỏ hoặc đánh dấu đã dùng transaction cũ và chỉ gắn principal đã xác minh với ID mới.

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant C as OAuth/OIDC Client
    participant OP as Authorization Server / OP
    B->>C: GET /login (session khách S0)
    C->>C: Lưu state, PKCE và issuer cho S0
    C-->>B: Redirect authorization endpoint
    B->>OP: Yêu cầu đăng nhập
    OP-->>B: Redirect về callback với code và state
    B->>C: Callback, gửi cookie S0
    C->>C: Kiểm tra state, issuer, transaction
    C->>OP: Đổi code qua token endpoint đã tin cậy
    OP-->>C: Token response
    C->>C: Xác minh ID token nếu dùng OIDC
    C->>C: Rotate S0 → S1, vô hiệu hóa S0
    C->>C: Gắn principal được xác thực vào S1
    C-->>B: Set-Cookie S1 rồi chuyển tới trang đã đăng nhập
~~~

### 8.2. Bảo vệ giao dịch trước callback

Các yếu tố cần kiểm tra độc lập:

1. **state:** giá trị khó đoán, gắn với giao dịch và phiên trình duyệt thích hợp; từ chối state lạ, hết hạn hoặc đã dùng.
2. **PKCE:** code_verifier tương ứng code_challenge của authorization request; chống việc sử dụng authorization code bị chặn trong những điều kiện liên quan.
3. **Issuer identification:** xác nhận authorization response thuộc đúng AS đã chọn, đặc biệt khi client hỗ trợ nhiều AS; RFC 9207 hoặc biện pháp chống mix-up tương đương theo cấu hình.
4. **OIDC nonce và ID token validation:** khi áp dụng, kiểm tra nonce, iss, aud, thời gian và chữ ký ID token.
5. **Session rotation:** sau khi xác thực thành công, đổi session ID cục bộ; không nâng quyền của ID đã tồn tại trước đó.

Nếu ứng dụng **xóa session S0 quá sớm** trước khi đọc state hoặc PKCE verifier, callback có thể thất bại. Thứ tự triển khai phải cho phép hoàn tất xác minh giao dịch, rồi rotate/đưa dữ liệu đã xác thực sang session mới bằng cơ chế an toàn. Không nên vì khó giữ dữ liệu callback mà bỏ rotation.

### 8.3. Login CSRF khác session fixation

**Login CSRF** có thể khiến người dùng bị đăng nhập vào **tài khoản của kẻ tấn công**, dẫn đến hành vi hoặc dữ liệu bị gắn nhầm vào tài khoản đó. **Session fixation** là việc kẻ tấn công biết trước **session credential** rồi dùng nó sau khi nạn nhân đăng nhập. Hai kiểu tấn công khác mục đích, nhưng có thể tận dụng những điểm yếu chung về ràng buộc luồng xác thực và quản lý trạng thái.

Một hệ thống chống fixation vẫn cần **state, PKCE, nonce, CSRF protection** phù hợp. Một hệ thống có state đúng vẫn cần đổi session ID sau đăng nhập.

### 8.4. Access token và refresh token trong BFF

Với kiến trúc BFF, trình duyệt thường chỉ giữ **cookie phiên**, còn BFF lưu access/refresh token server-side. Nếu session bị fixation, kẻ tấn công có thể dùng cookie đã biết để yêu cầu BFF thực hiện thao tác **thay mặt nạn nhân**, kể cả khi refresh token không từng lộ ra trình duyệt.

Do đó:

- Bảo vệ session cookie là bảo vệ **cổng truy cập đến token server-side**.
- Token server-side cần được gắn với đúng session đã xác thực và có phạm vi/khả năng thu hồi riêng.
- Đổi session ID, logout và thu hồi token cần được phối hợp theo chính sách; **đổi cookie không tự thu hồi JWT access token đã phát hành**, cũng như thu hồi refresh token không tự xóa mọi session ứng dụng.

## 9. Triển khai trong Java/Spring Security

### 9.1. Dùng cơ chế session fixation protection của framework

Ở ứng dụng Java Servlet, **HttpServletRequest.changeSessionId()** cho phép đổi ID của session hiện hành. Spring Security hỗ trợ bảo vệ session fixation và có thể dùng cơ chế thay session ID được servlet container hỗ trợ.

Ví dụ cấu hình minh họa cho một ứng dụng Spring Security hiện đại:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/oauth2/**").permitAll()
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId())
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Lưu ý về ví dụ:** đây là cấu hình minh họa cho session-based form login. Ứng dụng dùng OAuth2 Login, filter tùy chỉnh hoặc BFF cần tích hợp cơ chế bảo vệ ở **đường xác thực thực tế**; chỉ gắn đoạn cấu hình mẫu mà không kiểm tra callback và filter đang chạy sẽ không bảo đảm an toàn.

Các điểm cần xác minh trong ứng dụng Spring:

- **Session fixation strategy** được kích hoạt khi một phiên **thực sự chuyển sang trạng thái authenticated**.
- Session ID trước và sau login khác nhau; cookie mới được gửi qua HTTPS.
- ID cũ không còn truy cập được principal đã đăng nhập, kể cả khi request đi tới instance khác.
- Các custom authentication filter/handler không tự đặt SecurityContext vào session theo đường bỏ qua session authentication strategy của framework.
- Nếu có đăng nhập nhiều bước, MFA hoặc step-up, cơ chế đổi session ID tương ứng với **thời điểm nâng quyền**, không chỉ form login ban đầu.
- Kiểm tra CSRF protection, logout, session timeout và concurrent session handling theo chính sách riêng.

Không nên vô hiệu hóa session fixation protection để “giữ nguyên giỏ hàng” hoặc “giữ state OAuth”. Hãy dùng cơ chế migrate dữ liệu **có chọn lọc** hoặc dùng API thay ID an toàn của framework.

### 9.2. Pseudocode cho đường xác thực tùy chỉnh

Khi tự xây dựng hệ thống phiên, luồng xử lý khái niệm:

~~~text
authenticateAndEstablishSession(request, credentials):
    preAuth = validateExistingAnonymousSessionOrCreateFresh(request)
    principal = verifyCredentialsAndMfaIfRequired(credentials)

    if principal == INVALID:
        rejectWithoutAuthentication()

    atomicSessionTransition:
        newSessionId = secureRandomSessionId()
        safeData = selectAllowedUnauthenticatedData(preAuth)
        invalidateOldSession(preAuth.id)
        createAuthenticatedSession(
            id = newSessionId,
            principal = principal,
            data = safeData,
            assuranceLevel = authenticated,
            expiresAt = policyLimit
        )

    setSecureHostOnlyCookie(newSessionId)
    return success
~~~

**Đây là pseudocode**, không phải một recipe tự viết session manager rồi đưa thẳng vào production. Trong Servlet/Spring, dùng session management API sẵn có thường an toàn và ít lỗi hơn. Nếu hệ thống tự quản lý session tại Redis/database, thao tác chuyển quyền phải đảm bảo ID cũ không còn dẫn tới phiên có quyền; thao tác tạo phiên mới, hủy phiên cũ và xử lý request đồng thời phải được thiết kế nhất quán.

### 9.3. Race condition và session store phân tán

Có thể xảy ra hai request gần như đồng thời:

~~~text
T0: Request A bắt đầu login với S0
T1: Request B sử dụng S0 và đọc session trước khi rotation hoàn tất
T2: Login đổi S0 -> S1
T3: Request B cố ghi ngược trạng thái cũ vào session store
~~~

Nếu session store cho phép dữ liệu phiên cũ được ghi lại hoặc hồi sinh, hệ thống có thể tái tạo S0 cùng quyền mới. Cần đảm bảo:

- Old ID được đánh dấu không còn dùng được ở nguồn dữ liệu authoritative.
- Các request cũ không thể **recreate** một phiên đã bị thu hồi chỉ bằng việc ghi dữ liệu stale.
- Bản ghi principal và ID mới được cập nhật theo cơ chế nhất quán có thể kiểm thử.
- Session rotation có hiệu lực với tất cả instance; nếu dùng sticky session cũng phải xử lý khi cân bằng tải thay đổi.
- Không vô tình trả về cookie session cũ từ một request song song hoàn tất muộn, làm trình duyệt ghi đè cookie mới. Cần kiểm thử các cạnh tranh giữa login, API request và callback.

Việc chỉ thay giá trị cookie phía client mà không thay/hủy trạng thái trong Redis/database không phải là session fixation protection đầy đủ.

## 10. Các biện pháp giảm thiểu bổ sung

### 10.1. Ngăn đường cài sẵn session ID

- Không dùng URL parameter hoặc URL rewriting để truyền session ID trong ứng dụng đăng nhập nhạy cảm.
- Tránh cookie **Domain** rộng; dùng host-only và tiền tố **__Host-** khi phù hợp.
- Hạn chế hoặc cách ly subdomain do bên thứ ba quản lý, đặc biệt nếu cùng miền cookie với ứng dụng.
- Bảo vệ ứng dụng khỏi **XSS**, xử lý input/output đúng ngữ cảnh và áp dụng **Content Security Policy** phù hợp.
- Bắt buộc HTTPS và cookie Secure; cân nhắc **HSTS** để giảm nguy cơ hạ cấp HTTP.
- Không tin một session ID được client tự đề xuất mà server chưa từng phát hành.

### 10.2. Giảm tác động nếu session đã bị chiếm

- Dùng timeout phiên hợp lý, đặc biệt đối với tác vụ quản trị.
- Yêu cầu **reauthentication/step-up MFA** cho thao tác nhạy cảm và rotate ID khi nâng assurance level.
- Cho người dùng xem và thu hồi phiên đang hoạt động nếu hệ thống có khả năng này.
- Ghi nhận các dấu hiệu đăng nhập/phiên bất thường, chẳng hạn một session liên tục đổi địa chỉ mạng hoặc thiết bị trong bối cảnh rủi ro; chỉ dùng IP/user-agent làm **tín hiệu**, không coi đó là bằng chứng tuyệt đối.
- Thiết kế thu hồi access/refresh token nếu chúng được lưu trong session, theo điều kiện kiến trúc và thời gian sống token.
- Bảo vệ dữ liệu trong session server-side; không để dữ liệu pre-auth do người dùng tự đặt trở thành claims/quyền hậu auth.

**Sender-constrained access token** như DPoP/mTLS giúp giảm khả năng sử dụng lại một access token bị lộ ở nơi khác, nhưng không tự chữa một **HTTP session cookie** bị fixation. Nếu BFF vẫn chấp nhận cookie S0, kẻ tấn công có thể gọi BFF mà không cần trực tiếp lấy access token DPoP-bound.

## 11. Kiểm thử session fixation

### 11.1. Kiểm thử cơ bản bằng hai trình duyệt

Dùng hai profile trình duyệt hoặc hai HTTP client test độc lập:

1. **Client A** tạo phiên khách và ghi lại ID **S0** do ứng dụng cấp. Không dùng tài khoản thật; kiểm thử trong môi trường được phép.
2. **Client B** được thiết lập gửi S0 như một tình huống giả lập cookie fixation. Xác minh server đang xem nó là phiên khách, chưa có quyền truy cập tài khoản.
3. Client B hoàn tất đăng nhập bằng tài khoản thử nghiệm.
4. Kiểm tra phản hồi login: ID phiên mới **S1 khác S0**.
5. Kiểm tra Client B với S1 có thể truy cập đúng quyền đã cấp.
6. Kiểm tra Client A dùng **S0** để gọi endpoint yêu cầu xác thực: phải bị từ chối hoặc chỉ được đối xử như phiên khách mới không có principal.
7. Đăng xuất Client B; xác minh **S1** bị vô hiệu hóa tại server.

**Điều kiện thành công quan trọng nhất:** sau khi nạn nhân đăng nhập, **S0 không thể truy cập danh tính vừa được xác thực**. Việc cookie hiển thị S1 chỉ là bằng chứng phụ.

### 11.2. Ma trận ca kiểm thử

| Kịch bản | Kỳ vọng |
|---|---|
| Khách S0 đăng nhập thành công | Nhận S1 mới; S0 không có quyền |
| Khách S0 đăng nhập thất bại | Không có session được nâng quyền; phản hồi không lộ credential |
| Session ID tự bịa chưa từng được phát hành | Không được hệ thống nhận làm phiên hợp lệ theo ID tự chọn |
| Hai request dùng S0 đồng thời khi login | Tối đa một đường chuyển quyền hợp lệ; không hồi sinh S0 có principal |
| Đăng nhập OAuth/OIDC từ callback thành công | Transaction được kiểm tra; phiên cục bộ đổi ID trước khi cấp quyền |
| Callback sai state/nonce/issuer | Không có phiên authenticated được tạo |
| Cookie cùng tên với Domain/Path khác nhau | Không bị ứng dụng chọn cookie độc hại ngoài ý muốn |
| Login từ subdomain không đáng tin cậy | Không thể cài/ghi đè cookie host-only bảo mật ở host ứng dụng theo quy tắc trình duyệt |
| Step-up MFA/nâng quyền | Credential phiên được đổi theo chính sách, ID cũ không còn quyền cao |
| Logout | Phiên server-side bị hủy; ID cũ không dùng lại được |
| Nhiều instance sau rotation | Instance khác vẫn từ chối S0 |
| Giỏ hàng trước login | Chỉ dữ liệu được cho phép được giữ sau rotation; không giữ metadata có nguồn không tin cậy |
| Request đang chạy trả cookie cũ sau login | Không vô tình ghi đè S1 hoặc khôi phục quyền cho S0 |

### 11.3. Ví dụ kiểm thử tích hợp khái niệm

~~~java
// Pseudocode: dùng test client độc lập và session store thử nghiệm.
String fixedId = anonymousClient.getSessionId();      // S0

victimClient.setSessionCookie(fixedId);
victimClient.login("demo-user", "test-password");

String rotatedId = victimClient.getSessionId();        // S1
assertNotEquals(fixedId, rotatedId);

assertEquals(200, victimClient.get("/account").status());

attackerClient.setSessionCookie(fixedId);
assertEquals(401, attackerClient.get("/account").status());
// Tùy giao thức/ứng dụng có thể là 302 chuyển login hoặc 403.
// Kết luận cần kiểm tra old ID không giữ quyền authenticated.

victimClient.logout();
assertUnauthenticated(victimClient.get("/account"));
~~~

Dòng **assertEquals(401)** minh họa một trường hợp API; ứng dụng web có thể trả **302** về trang login. Kiểm thử nên xác nhận **không có quyền truy cập trái phép** thay vì cố định một status HTTP áp dụng cho mọi kiến trúc.

Các ca kiểm thử concurrency nên chạy qua **session store thật hoặc mô phỏng đúng tính nhất quán** của môi trường triển khai. Mocks chỉ trả ID khác nhau nhưng không mô hình hóa việc hủy ID cũ sẽ không phát hiện lỗi tái sử dụng S0.

## 12. Giám sát và phản ứng khi phát hiện dấu hiệu fixation

Các sự kiện nên có trong audit log:

- **session_created_anonymous:** cấp session khách.
- **session_rotated_on_authentication:** session ID thay đổi sau xác thực.
- **session_rotated_on_privilege_change:** đổi ID khi nâng quyền/assurance.
- **old_session_id_reuse_rejected:** một ID đã vô hiệu hóa được dùng lại.
- **session_cookie_conflict:** phát hiện request có nhiều cookie phiên cùng tên hoặc định dạng bất thường.
- **session_revoked_on_logout:** session bị thu hồi.
- **oauth_callback_transaction_invalid:** state/issuer/nonce/transaction sai hoặc hết hạn.

Log có thể chứa request ID, tài khoản nội bộ (nếu đã xác thực), thời gian, loại sự kiện, phiên bản ứng dụng, nơi phát sinh và **định danh phiên đã được băm hoặc gắn tag không thể dùng để đăng nhập**. **Không ghi raw session ID, Authorization header, access/refresh token hay OAuth authorization code** vào log.

Khi nhận thấy có session fixation hoặc nghi ngờ bị khai thác:

1. Xác định đường cài sẵn session ID: cookie scope, subdomain, URL, XSS, proxy hay custom login handler.
2. Sửa cơ chế **rotation** và bảo đảm ID cũ bị vô hiệu hóa trên mọi instance.
3. Đánh giá phiên đã bị ảnh hưởng và thu hồi session theo phạm vi rủi ro; cân nhắc thu hồi các OAuth token gắn với phiên nếu cần và khả thi.
4. Kiểm tra cookie flags, thời hạn phiên, event logs và các đường xác thực phụ như OIDC callback, MFA, impersonation hoặc admin elevation.
5. Bổ sung ca kiểm thử cho chính đường khai thác đã tìm thấy, theo dõi sự kiện ID cũ bị dùng lại sau khi triển khai sửa lỗi.

Một request dùng old ID sau rotation **không luôn chứng minh có kẻ tấn công**: nó cũng có thể là request song song, tab cũ hoặc lỗi mạng. Tuy nhiên, old ID phải **không truy cập được principal đã xác thực**; điều tra ngữ cảnh rồi mới xác định mức độ sự cố.

## 13. Các ngộ nhận thường gặp

**“Session ID được sinh ngẫu nhiên mạnh nên không thể bị fixation.”** Sai. Kẻ tấn công có thể dùng ID hợp lệ do server cấp cho chính họ rồi tìm cách gắn ID ấy cho nạn nhân.

**“Ứng dụng đã dùng HTTPS, HttpOnly và SameSite nên khỏi cần đổi ID sau login.”** Sai. Các thuộc tính giảm khả năng lộ hoặc bị lạm dụng cookie, nhưng không sửa lỗi **giữ nguyên ID đã biết khi nâng quyền**.

**“Tạo cookie S1 mới là đủ, không cần xóa S0 ở server.”** Sai. Nếu S0 còn liên kết với principal đã đăng nhập, kẻ tấn công vẫn có thể truy cập.

**“Có OAuth state và PKCE nên không còn session fixation.”** Sai. State và PKCE bảo vệ các phần khác của OAuth flow; session cục bộ vẫn phải được rotate khi hoàn tất xác thực.

**“OIDC ID token đã được xác minh nên session ID cũ có thể giữ nguyên.”** Sai. ID token xác nhận sự kiện xác thực theo OIDC; nó không chứng minh cookie phiên cục bộ chưa bị biết trước.

**“Thay session ID ở mọi HTTP request là giải pháp an toàn nhất.”** Không hẳn. Rotation liên tục có thể gây race condition; điều cần bảo đảm là rotate tại **mốc chuyển đổi tin cậy**, vô hiệu hóa ID cũ và thiết kế session store nhất quán.

**“Logout chỉ cần xóa cookie của trình duyệt.”** Sai. Phải vô hiệu hóa phiên server-side; các OAuth token độc lập có thể cần xử lý thu hồi riêng.

**“Đổi ID khi đăng nhập làm mất toàn bộ dữ liệu khách nên không thể làm.”** Sai. Dữ liệu khách hợp lệ có thể được chuyển có chọn lọc; không nên giữ nguyên session ID chỉ để bảo toàn mọi thuộc tính.

## 14. Câu hỏi tự kiểm tra

1. Session fixation cần những điều kiện gì? Vì sao độ ngẫu nhiên của session ID không đủ để ngăn kiểu tấn công này?
2. Phân biệt session fixation với session hijacking và login CSRF theo **thời điểm kẻ tấn công có credential** và **mục tiêu**.
3. Khi S0 đã biết được nạn nhân dùng để đăng nhập, điều gì phải xảy ra với S0 và S1 tại session store?
4. Lợi ích và giới hạn của cookie host-only, tiền tố **__Host-**, Secure, HttpOnly và SameSite là gì?
5. Vì sao callback OAuth/OIDC có state và PKCE đúng vẫn cần đổi session ID cục bộ?
6. Một BFF giữ refresh token server-side có thể bị ảnh hưởng thế nào nếu cookie phiên bị fixation?
7. Trong hệ thống nhiều instance, những race condition nào có thể vô tình hồi sinh old session ID?
8. Nếu một request dùng S0 ngay sau khi login, vì sao phải từ chối quyền nhưng chưa thể kết luận chắc chắn là tấn công?
9. Viết một kiểm thử chứng minh **old session ID không thể truy cập tài khoản**, thay vì chỉ chứng minh cookie sau login có giá trị khác.
10. Khi nâng quyền từ user sang admin hoặc hoàn tất MFA, cơ chế quản lý session nên kiểm soát thay đổi mức tin cậy như thế nào?

**Ghi nhớ:** Session fixation khai thác việc **nâng quyền của một session ID đã bị biết từ trước**. Để bảo vệ ứng dụng dùng OAuth/OIDC, JWT, opaque token hay cookie phiên truyền thống, hãy xác định rõ **credential nào thực sự cho phép truy cập ứng dụng**, đổi session ID khi xác thực/nâng quyền, vô hiệu hóa ID cũ và kiểm thử hành vi qua các instance. Cookie attributes, OAuth state/PKCE, bảo vệ token và session rotation là những lớp bảo vệ có mục tiêu khác nhau cần phối hợp.

## Tài liệu tham khảo

- **OWASP Session Management Cheat Sheet:** session ID, session fixation, rotation sau thay đổi đặc quyền, cookie attributes và vòng đời session.
- **OWASP Authentication Cheat Sheet:** quản lý phiên sau xác thực và yêu cầu tái xác thực trong các tình huống nhạy cảm.
- **OWASP Cross-Site Request Forgery Prevention Cheat Sheet:** các biện pháp chống CSRF, giới hạn của SameSite và login CSRF.
- **RFC 6265 — HTTP State Management Mechanism:** cú pháp, phạm vi Domain/Path và xử lý HTTP cookie.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** authorization code flow, state và vòng đời credential OAuth.
- **RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients (PKCE):** ràng buộc authorization code với code_verifier.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** đối chiếu issuer của authorization response trong client hỗ trợ nhiều AS.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** các biện pháp hiện đại để bảo vệ OAuth client và token.
- **OpenID Connect Core 1.0:** ID token, nonce và xác minh kết quả xác thực của OpenID Provider.
- **Spring Security Reference — Session Management:** session fixation protection, cấu hình session và tích hợp với cơ chế xác thực.
- **Jakarta Servlet API — HttpServletRequest.changeSessionId():** thao tác đổi ID của HTTP session đang gắn với request.

