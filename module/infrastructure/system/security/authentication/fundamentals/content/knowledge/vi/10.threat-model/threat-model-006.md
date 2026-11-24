# Session hijacking — Chiếm quyền phiên xác thực

## 1. Session hijacking là gì?

**Session hijacking** (chiếm quyền phiên) là hành vi kẻ tấn công lấy được hoặc sử dụng trái phép thông tin đại diện cho một phiên đã xác thực, từ đó gửi yêu cầu dưới danh nghĩa người dùng hợp lệ. Trong nhiều ứng dụng web, thông tin này là **session ID** nằm trong cookie. Với kiến trúc token, nó có thể là access token, refresh token hoặc một credential phiên khác.

Ví dụ: một nhân viên đăng nhập cổng nội bộ bằng mật khẩu và MFA. Server tạo phiên và gửi cookie \`sid\` cho trình duyệt. Nếu kẻ tấn công sao chép được cookie còn hiệu lực từ thiết bị nhiễm mã độc, họ có thể gửi cookie đó tới server và được xem như đang sử dụng phiên của nhân viên. Kẻ tấn công có thể không cần biết mật khẩu hoặc mã MFA.

Đây là chủ đề thuộc chương **Threat model** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Việc học credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản phải bao gồm cả giai đoạn **sau đăng nhập**. Xác thực mạnh giúp thiết lập phiên đáng tin hơn; bảo vệ phiên giúp duy trì sự tin cậy ấy trong suốt thời gian sử dụng.

Phân biệt ba khái niệm:

| Khái niệm | Điều gì bị tấn công? | Ví dụ |
| --- | --- | --- |
| **Credential theft** | Bằng chứng đăng nhập ban đầu. | Lấy mật khẩu hoặc secret TOTP. |
| **Session hijacking** | Trạng thái/credential đại diện cho phiên đã xác thực. | Sao chép cookie session ID hoặc bearer access token. |
| **Session fixation** | Khiến nạn nhân đăng nhập bằng một session ID mà kẻ tấn công đã biết. | Kẻ tấn công đặt trước ID phiên, nạn nhân đăng nhập mà server không đổi ID. |

Session fixation có thể dẫn đến chiếm quyền phiên nhưng cơ chế tấn công khác với việc đánh cắp một phiên đã tồn tại. Cả hai đều cần được xem xét khi thiết kế vòng đời session.

**Bất biến bảo mật:** chỉ người đang kiểm soát hợp lệ phiên mới được dùng phiên đó; session ID/token phải khó đoán, được bảo vệ khi truyền và lưu trữ, có thời hạn, có thể thu hồi và chỉ đại diện cho đúng phạm vi quyền đã cấp.

## 2. Vì sao chiếm phiên nguy hiểm?

Session thường là một **bearer credential**: bên nào nắm giữ giá trị hợp lệ có thể sử dụng nó, trừ khi hệ thống bổ sung cơ chế chứng minh quyền kiểm soát khóa hoặc ràng buộc khác. Vì thế, việc đánh cắp session có thể vượt qua các bước bảo vệ ở màn hình đăng nhập:

- Kẻ tấn công có thể sử dụng phiên đã qua MFA mà không cần nhập lại OTP.
- Mật khẩu dài, passkey chống phishing hoặc quy trình xác minh IdP không cứu được phiên đã bị đánh cắp nếu ứng dụng không bảo vệ token/cookie.
- Một phiên có quyền cao có thể cho phép xem dữ liệu, thay đổi credential, tạo API key, thêm thiết bị hoặc thực hiện giao dịch.
- Nếu refresh token bị lộ, kẻ tấn công có thể duy trì quyền truy cập sau khi access token ngắn hạn hết hạn, tùy cơ chế rotation và thu hồi.
- Đăng xuất chỉ xóa cookie ở trình duyệt có thể không vô hiệu hóa bản sao cookie đã bị lấy trước đó nếu server vẫn chấp nhận session.

**Xác thực và phiên là hai giai đoạn khác nhau.** Xác thực xác minh bằng chứng tại một thời điểm; phiên duy trì trạng thái sau đó. Cả hai cần chính sách riêng và phải liên kết bằng quyết định server đã kiểm chứng.

## 3. Tài sản, đối thủ và ranh giới tin cậy

### Tài sản cần bảo vệ

- Session ID, access token, refresh token, cookie xác thực và dữ liệu khóa dùng để chứng minh quyền kiểm soát token.
- Tài khoản người dùng, thông tin cá nhân, hồ sơ doanh nghiệp, giao dịch và API nhạy cảm.
- Các thao tác quản lý danh tính: đổi mật khẩu, thêm/xóa passkey, bật/tắt MFA, thay email, liên kết IdP và khôi phục tài khoản.
- Trạng thái session phía server: chủ sở hữu, tenant, thời hạn, mức bảo đảm xác thực, trạng thái thu hồi và quyền liên quan.

### Đối thủ và năng lực

Kẻ tấn công có thể:

1. Nghe lén mạng không được bảo vệ hoặc khai thác cấu hình TLS sai.
2. Khai thác XSS, mã độc, extension độc hại hoặc thiết bị đã bị xâm nhập để đọc hay sử dụng thông tin phiên.
3. Lừa người dùng vào trang giả hoặc gửi liên kết khiến trình duyệt phát sinh yêu cầu ngoài ý muốn.
4. Đoán, tái sử dụng, chiếm trước hoặc phát lại session ID/token do hệ thống tạo yếu hoặc quản lý sai.
5. Đọc token từ URL, log, analytics, crash report, backup hoặc kho lưu trữ client không phù hợp.
6. Lợi dụng phiên đã hết hạn ở client nhưng chưa bị thu hồi ở server, hoặc token bị sao chép trước khi người dùng đăng xuất.

Không nên giả định kẻ tấn công luôn kiểm soát được toàn bộ thiết bị. Threat model cần phân biệt khả năng **đọc cookie**, **thực hiện request cùng origin**, **đọc local storage**, **nghe lén mạng**, và **điều khiển thiết bị** vì mỗi năng lực đòi hỏi biện pháp khác nhau.

### Sơ đồ ranh giới tin cậy

~~~mermaid
flowchart LR
    U["Người dùng"]
    B["Trình duyệt / ứng dụng<br/>môi trường client"]
    N["Kênh mạng<br/>TLS"]
    W["Web/API server<br/>kiểm tra session"]
    D[("Session store<br/>trạng thái và thu hồi")]
    R["Tài nguyên / API<br/>kiểm tra quyền"]
    X["Kẻ tấn công<br/>mạng, XSS, malware,<br/>token leak"]
    U --> B
    B -->|"Cookie / token"| N
    N --> W
    W <--> D
    W -->|"Chỉ sau khi xác minh"| R
    X -.->|"Đánh cắp / sử dụng phiên"| B
    X -.->|"Nghe lén nếu kênh yếu"| N
    X -.->|"Khai thác ứng dụng"| W
~~~

Server là nơi quyết định session có hợp lệ và được phép truy cập tài nguyên hay không. Client có thể lưu cookie/token, nhưng không được tự tuyên bố \`authenticated=true\`, tự đổi chủ session hoặc tự cấp vai trò. Mọi request tới tài nguyên phải được kiểm tra trên server.

## 4. Các con đường chiếm quyền phiên thường gặp

| Con đường | Cách xảy ra | Tác động | Biện pháp chính |
| --- | --- | --- | --- |
| **Nghe lén mạng (sidejacking)** | Cookie/token bị truyền qua HTTP hoặc cấu hình TLS yếu, cho phép quan sát trên đường truyền. | Kẻ tấn công sao chép bearer credential. | HTTPS toàn bộ, HSTS, cấu hình TLS phù hợp, không mixed content. |
| **XSS** | Script độc hại chạy trong origin của ứng dụng, đọc dữ liệu client có thể truy cập hoặc thực hiện request thay người dùng. | Lấy token trong storage hoặc thao tác bằng phiên đang mở. | Output encoding, xử lý input, CSP, giảm script bên thứ ba, HttpOnly cookie. |
| **Malware/extension độc hại** | Phần mềm trên thiết bị đọc cookie, profile trình duyệt, bộ nhớ hoặc điều khiển request. | Có thể lấy và dùng phiên hợp lệ. | Bảo vệ endpoint, giảm thời hạn, thu hồi phiên, xác thực lại hành động nhạy cảm. |
| **Session fixation** | Nạn nhân bị buộc sử dụng ID phiên mà kẻ tấn công đã biết. | Kẻ tấn công dùng ID đó sau khi nạn nhân đăng nhập. | Tạo ID mới sau đăng nhập/nâng quyền, không nhận session ID do client tùy chọn. |
| **Session ID yếu/dễ đoán** | ID ngắn, tuần tự hoặc sinh từ PRNG không an toàn. | Đoán được phiên người khác. | CSPRNG, entropy đủ lớn, không chứa dữ liệu định danh có thể suy ra. |
| **Token leakage** | Token xuất hiện trong URL, log, Referer, analytics, crash report hoặc repo. | Bên nhận được token có thể sử dụng. | Không đặt token trong URL, lọc log, bảo vệ secret, hạn chế referrer và telemetry. |
| **CSRF** | Trình duyệt tự gửi cookie tới website đích khi người dùng mở trang do kẻ tấn công kiểm soát. | Thực hiện hành động dưới phiên nạn nhân dù kẻ tấn công không biết cookie. | CSRF token, SameSite phù hợp, kiểm tra Origin/Referer và xác minh ý định. |
| **Refresh token theft** | Refresh token bị lấy từ storage hoặc thiết bị. | Kẻ tấn công đổi token để duy trì truy cập. | Rotation, phát hiện reuse, thu hồi token family, lưu trữ an toàn. |
| **Logout không thu hồi** | Server vẫn chấp nhận ID đã bị xóa khỏi trình duyệt. | Bản sao phiên vẫn hoạt động. | Thu hồi phía server hoặc danh sách chặn/trạng thái session phù hợp. |

**CSRF và session hijacking không đồng nghĩa.** Trong CSRF, kẻ tấn công thường không cần biết giá trị cookie: trình duyệt nạn nhân tự gửi cookie theo quy tắc của nó. CSRF lợi dụng phiên hiện có để thực hiện hành động; hijacking theo nghĩa hẹp là chiếm được khả năng sử dụng phiên. Hai rủi ro có thể cùng tồn tại và cần các kiểm soát khác nhau.

## 5. Session fixation và session ID an toàn

Session ID là một định danh ngẫu nhiên để server tra trạng thái session. Nó cần được tạo bởi **cryptographically secure random number generator (CSPRNG)**, có entropy đủ lớn và không chứa thông tin có thể đoán như user ID, timestamp, số thứ tự hoặc email.

Ví dụ một session ID an toàn phải trông như một giá trị ngẫu nhiên không có ý nghĩa; không nên tự tạo bằng cách nối \`userId + currentTime\` hoặc hash một dữ liệu dễ dự đoán.

### Vòng đời session cơ bản

~~~mermaid
stateDiagram-v2
    [*] --> Anonymous
    Anonymous --> Authenticated: Credential được xác minh
    Authenticated --> Rotated: Đăng nhập / nâng quyền
    Rotated --> Active: Session ID mới được phát hành
    Active --> Reauthenticated: Xác thực lại
    Reauthenticated --> Active: Gia hạn theo chính sách
    Active --> Expired: Hết idle/absolute TTL
    Active --> Revoked: Logout / sự cố / quản trị thu hồi
    Expired --> [*]
    Revoked --> [*]
~~~

Các quy tắc quan trọng:

- Tạo session ID mới sau khi đăng nhập thành công; không giữ ID ẩn danh trước đăng nhập làm ID đã xác thực.
- Xoay ID khi thay đổi mức đặc quyền hoặc sau sự kiện nhạy cảm theo chính sách, để giảm rủi ro session fixation.
- Hủy hoặc đánh dấu ID cũ không còn hiệu lực ở server; chỉ đổi cookie phía client là chưa đủ.
- Không cho client chỉ định session ID tùy ý hoặc tái sử dụng ID đã bị thu hồi.
- Khi logout, thu hồi session phía server và xóa cookie phía client; thực hiện cả hai.

Session ID phải được xem như **bí mật bearer**. Không ghi giá trị thô vào log, không đưa vào URL và không hiển thị trong giao diện hỗ trợ. Nếu cần truy vết, dùng mã tham chiếu nội bộ không có khả năng xác thực.

## 6. Bảo vệ cookie phiên trên web

Với ứng dụng web dùng cookie, một cấu hình thường gặp:

~~~http
Set-Cookie: __Host-session=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Các thuộc tính có ý nghĩa:

| Thuộc tính | Tác dụng | Lưu ý |
| --- | --- | --- |
| **Secure** | Chỉ gửi cookie qua HTTPS. | Phải dùng TLS cho toàn bộ luồng xác thực và tài nguyên cần bảo vệ. |
| **HttpOnly** | Không cho JavaScript thông thường đọc cookie qua \`document.cookie\`. | Giảm khả năng XSS đánh cắp giá trị cookie; XSS vẫn có thể gửi request cùng origin và thao tác bằng phiên. |
| **SameSite=Lax/Strict/None** | Kiểm soát một số trường hợp cookie được gửi trong ngữ cảnh cross-site. | \`None\` cần \`Secure\`; chọn theo luồng SSO và tích hợp thực tế. SameSite không thay thế mọi CSRF protection. |
| **Path=/** | Cookie áp dụng cho toàn ứng dụng theo path. | Không dùng Path như ranh giới bảo mật mạnh. |
| **__Host- prefix** | Trình duyệt hỗ trợ yêu cầu Secure, Path=/ và không có Domain. | Hạn chế một số kiểu cookie injection từ subdomain; cần kiểm tra hỗ trợ và cấu hình. |

Không nên đặt session cookie ở domain quá rộng nếu không cần. Subdomain yếu có thể trở thành bề mặt tấn công nếu cookie được chia sẻ cho toàn domain. Với các luồng OIDC/SAML có chuyển hướng cross-site, cần kiểm tra tương thích SameSite và cấu hình cookie tạm thời phù hợp; không tắt bảo vệ toàn cục chỉ để làm một callback hoạt động.

### Cookie và CSRF

Cookie thường được trình duyệt tự động gửi kèm request phù hợp. Vì vậy, endpoint thay đổi trạng thái như đổi email, chuyển tiền, thêm passkey hoặc xóa MFA cần bảo vệ CSRF khi kiến trúc dựa vào cookie:

- Dùng CSRF token được kiểm tra phía server và gắn với phiên/giao dịch.
- Kiểm tra Origin (và Referer khi phù hợp) theo danh sách nguồn tin cậy.
- Dùng SameSite phù hợp như một lớp giảm rủi ro.
- Tránh GET cho thao tác thay đổi trạng thái; không dựa vào việc nút giao diện bị ẩn.
- Yêu cầu xác thực lại/step-up cho thao tác nhạy cảm.

**HttpOnly không ngăn CSRF.** Nó giới hạn JavaScript đọc giá trị cookie, còn trình duyệt vẫn có thể tự gửi cookie theo quy tắc cookie. **SameSite cũng không giải quyết XSS**: script chạy cùng origin có thể thao tác trong phiên.

## 7. XSS, token trong trình duyệt và ứng dụng di động

### 7.1. XSS và lưu token

Nếu ứng dụng lưu access token hoặc refresh token trong \`localStorage\`, mọi script chạy được trong origin có thể đọc chúng. XSS do lỗi output encoding, dependency bên thứ ba hoặc script bị chèn có thể lấy token và gửi ra ngoài.

Một số nguyên tắc:

- Tránh lưu bearer token dài hạn trong \`localStorage\` hoặc \`sessionStorage\` khi có kiến trúc an toàn hơn.
- Với web app có backend, mô hình **Backend for Frontend (BFF)** có thể giữ token ở server và dùng cookie phiên bảo vệ cho trình duyệt.
- Nếu dùng cookie HttpOnly, vẫn phải chống XSS vì script độc hại có thể thực hiện hành động trong phiên và đọc dữ liệu mà trang được phép truy cập.
- Áp dụng output encoding theo ngữ cảnh, kiểm tra input, Content Security Policy (CSP), hạn chế inline script và kiểm soát thư viện/third-party script.
- Không đưa token vào query string, fragment được xử lý không an toàn, log, analytics, URL redirect hoặc thông báo lỗi.
- Đặt Referrer-Policy phù hợp và tránh trang có token trong URL liên kết tới bên thứ ba.

Không có một lựa chọn lưu trữ duy nhất đúng cho mọi ứng dụng. Cần xem kiến trúc SPA/BFF, khả năng chống CSRF, yêu cầu SSO, cách triển khai backend và mức nhạy cảm dữ liệu.

### 7.2. Ứng dụng di động

Ứng dụng di động nên lưu credential/token trong vùng lưu trữ bảo mật của nền tảng như **Keychain** hoặc **Android Keystore** theo khả năng thiết bị, không lưu plaintext trong file, log hoặc shared preferences không bảo vệ. Cần xem xét backup/restore, root/jailbreak, màn hình debug, clipboard, deep link và thông báo push.

Việc dùng secure storage không loại bỏ mọi rủi ro: mã độc có thể điều khiển thiết bị đang mở khóa, token có thể bị lộ qua log hoặc ứng dụng có thể xử lý deep link sai. Vẫn cần TTL, rotation, thu hồi và kiểm tra quyền ở server.

## 8. Bảo vệ access token và refresh token

Access token và refresh token có mức độ nhạy cảm khác nhau:

| Loại | Mục đích | Nếu bị đánh cắp |
| --- | --- | --- |
| **Access token** | Gọi API trong phạm vi và thời hạn được cấp. | Kẻ tấn công có thể gọi API như bearer token cho phép. |
| **Refresh token** | Xin access token mới. | Có thể duy trì truy cập lâu hơn hoặc tạo chuỗi token mới. |
| **ID token OIDC** | Chứa thông tin xác thực dành cho RP. | Có thể bị lạm dụng nếu RP xử lý sai; không nên dùng thay access token để gọi API. |
| **Session cookie** | Đại diện cho phiên ứng dụng. | Có thể cho phép sử dụng trực tiếp phiên nếu server chấp nhận. |

Các biện pháp thường dùng:

1. Giới hạn thời gian sống access token theo rủi ro và nhu cầu; không coi TTL ngắn là đủ nếu token có thể được refresh không giới hạn.
2. Bảo vệ refresh token hơn access token, giới hạn client/audience/scope và lưu ở nơi thích hợp.
3. Dùng **refresh token rotation**: mỗi lần refresh thành công, token cũ bị vô hiệu hóa và token mới được cấp.
4. Phát hiện **reuse** token cũ đã bị xoay vòng; có thể thu hồi cả token family hoặc phiên liên quan theo chính sách.
5. Có endpoint/cơ chế thu hồi và quy trình phản ứng khi token bị lộ; không chỉ xóa token khỏi client.
6. Với hệ thống phù hợp, cân nhắc **sender-constrained token** như OAuth mTLS hoặc DPoP để token gắn với khóa của bên gửi.

### Sender-constrained token

Bearer token có thể bị sử dụng bởi bên nào sao chép được nó. Sender-constrained token bổ sung bằng chứng rằng request được ký hoặc thiết lập bởi bên sở hữu khóa liên quan. Ví dụ:

- **mTLS-bound access token:** token được ràng buộc với chứng chỉ client; API kiểm tra kết nối TLS và chứng chỉ tương ứng.
- **DPoP:** client gửi proof có chữ ký cho request; server kiểm tra khóa, phương thức/URI, thời gian, định danh proof và các ràng buộc theo đặc tả.

Các cơ chế này làm giảm giá trị của việc chỉ sao chép chuỗi token, nhưng **không cứu được khóa riêng bị chiếm** hoặc thiết bị bị kiểm soát hoàn toàn. Chúng cũng không thay thế kiểm tra issuer, audience, thời hạn, scope và quyền trên tài nguyên.

## 9. Session timeout, xoay vòng và thu hồi

Một session nên có ít nhất hai khái niệm thời hạn:

- **Idle timeout:** hết hạn sau một khoảng thời gian không có hoạt động hợp lệ.
- **Absolute timeout:** hết hạn sau một tổng thời gian tối đa kể từ khi phiên được tạo, kể cả khi vẫn có hoạt động.

Thời hạn phụ thuộc mức nhạy cảm, thiết bị, loại ứng dụng và yêu cầu vận hành. Một trang đọc thông tin công khai và cổng quản trị giao dịch tài chính không nhất thiết có cùng TTL.

### Khi nào nên xoay session ID?

- Sau đăng nhập thành công.
- Sau khi nâng quyền hoặc hoàn tất step-up.
- Sau thay đổi credential hoặc các thao tác nhạy cảm khi chính sách yêu cầu.
- Khi phát hiện bất thường cần chuyển sang phiên mới sau xác thực lại.

Khi xoay, server cần **vô hiệu hóa ID cũ** và xử lý các request đang chạy một cách nhất quán. Không cho phép cả ID cũ lẫn mới tiếp tục sống vô hạn chỉ để tránh lỗi client.

### Thu hồi phiên

Server cần có cách thu hồi theo:

- Một session cụ thể (đăng xuất thiết bị hiện tại).
- Tất cả session của một tài khoản (nghi chiếm tài khoản, đổi mật khẩu hoặc yêu cầu người dùng).
- Một nhóm token/refresh-token family (phát hiện refresh token reuse).
- Tài khoản bị vô hiệu hóa hoặc nhân viên rời tổ chức.

Với JWT access token tự chứa, xóa cookie hoặc xóa bản ghi client không làm JWT mất hiệu lực trước \`exp\` nếu API chỉ kiểm tra chữ ký và thời hạn. Muốn thu hồi sớm có thể cần TTL ngắn, introspection, denylist, version/session claim được kiểm tra hoặc cơ chế phù hợp kiến trúc. Mỗi lựa chọn có chi phí về độ trễ, khả năng mở rộng và tính sẵn sàng.

**Logout phải có tác động phía server.** Xóa cookie ở trình duyệt là cần thiết để thiết bị đó ngừng gửi phiên, nhưng bản sao token đã bị đánh cắp vẫn có thể hoạt động nếu chưa thu hồi.

## 10. Phát hiện và phản ứng với dấu hiệu chiếm phiên

Không có tín hiệu đơn lẻ nào chứng minh chắc chắn session đã bị chiếm. Có thể kết hợp:

- Địa chỉ IP/ASN hoặc vị trí thay đổi bất thường trong thời gian ngắn.
- User agent, thiết bị hoặc ngữ cảnh client thay đổi đáng kể.
- Hai hoạt động không thể đồng thời hợp lý theo mô hình dịch vụ.
- Hành vi truy cập dữ liệu/endpoint khác thường, tăng tốc độ hoặc thay đổi quyền.
- Refresh token reuse, nhiều request từ nhiều nguồn với cùng phiên, hoặc token bị sử dụng sau khi người dùng đã logout.
- Thao tác nhạy cảm xảy ra ngay sau một lần đăng nhập hoặc thiết lập MFA bất thường.

IP, vị trí và fingerprint thiết bị là **tín hiệu rủi ro**, không phải bằng chứng danh tính tuyệt đối. Người dùng có thể đổi mạng, dùng VPN, roaming hoặc nhiều thiết bị. Nếu ràng buộc cứng vào IP/user agent, có thể khóa nhầm người dùng hợp lệ và vẫn không ngăn được kẻ tấn công cùng mạng/thiết bị.

### Khi có dấu hiệu đáng tin cậy

1. Đánh giá mức chắc chắn và phạm vi session/token có thể bị ảnh hưởng.
2. Thu hồi session hoặc token family liên quan; nếu không xác định được phạm vi, cân nhắc thu hồi tất cả phiên của tài khoản.
3. Yêu cầu đăng nhập lại và step-up bằng credential còn đáng tin cậy; nếu nghi credential gốc cũng bị lộ, thực hiện thay đổi/thu hồi credential.
4. Kiểm tra thay đổi gần đây: thêm passkey, đổi email, bật/tắt MFA, tạo API key, liên kết IdP, đổi thông tin khôi phục.
5. Thông báo cho chủ tài khoản qua kênh phù hợp và cung cấp cách xem/đăng xuất thiết bị.
6. Lưu dấu vết điều tra mà không lưu token/session ID thô; xử lý thiết bị bị xâm nhập nếu có căn cứ.

**Không phải mọi session anomaly đều cần reset mật khẩu.** Nếu chỉ một cookie phiên bị lộ nhưng credential gốc còn an toàn, thu hồi phiên và xác thực lại có thể đủ. Nếu có dấu hiệu phishing/credential theft hoặc kẻ tấn công đã thay phương thức xác thực, cần xử lý rộng hơn theo phạm vi sự cố.

## 11. Mã giả: kiểm tra và thu hồi session ở server

Ví dụ dưới đây minh họa logic kiểm tra session cookie; đây là **mã giả**, không thay thế thư viện/session middleware đã được kiểm thử.

~~~text
authorizeRequest(request):
    sessionId = readSessionCookie(request)
    if sessionId is missing:
        return unauthenticated()

    session = sessionStore.lookupBySecureHash(sessionId)
    if session is missing:
        return unauthenticated()

    if session.revoked or session.absoluteExpired or session.idleExpired:
        return unauthenticated()

    if not session.account.active:
        revokeSessionAtomically(session.id)
        return unauthenticated()

    if riskSignalsRequireStepUp(request, session):
        return stepUpRequired()

    if not permissionPolicy.allows(
        session.accountId,
        request.resource,
        request.action
    ):
        return forbidden()

    updateLastActivitySafely(session)
    return continueRequestAs(session.account)

logout(sessionId):
    sessionStore.revokeAtomically(sessionId)
    clearCookieWithSameAttributes()
    auditWithoutRawSessionId("session_revoked")
    return success()
~~~

Lưu session ID dạng hash ở server có thể giảm tác động nếu session store bị đọc trái phép, tùy thiết kế và entropy của ID. Khi tra cứu, hệ thống cần dùng cơ chế an toàn và quản lý TTL/trạng thái nhất quán. Nếu dùng opaque random ID có entropy cao, hash không thay thế việc bảo vệ database, nhưng có thể là lớp giảm thiểu hữu ích.

Đối với JWT tự chứa, cách xử lý khác: API xác minh chữ ký, issuer, audience, thời hạn và trạng thái thu hồi/introspection nếu kiến trúc yêu cầu. Không thể giả định có thể tra \`sessionStore.lookupBySecureHash\` cho mọi JWT.

## 12. Tình huống thực tế: cookie bị lấy qua XSS

Một nhân viên đăng nhập cổng quản trị bằng passkey. Ứng dụng tạo cookie phiên có \`Secure\` và \`SameSite=Lax\`, nhưng thiếu \`HttpOnly\`. Một lỗi XSS trong trang báo cáo cho phép script không tin cậy chạy cùng origin và đọc \`document.cookie\`. Kẻ tấn công gửi cookie ra máy chủ của họ rồi dùng nó gọi API.

### Phân tích theo chuỗi tấn công

| Bước | Điều xảy ra | Điểm kiểm soát có thể cắt chuỗi |
| --- | --- | --- |
| 1. XSS xuất hiện | Dữ liệu người dùng được render như HTML/script không an toàn. | Output encoding, sanitizer phù hợp, CSP, kiểm soát dependency. |
| 2. Script chạy cùng origin | Trình duyệt cấp quyền origin của ứng dụng cho script. | Ngăn XSS; giảm script bên thứ ba và quyền của trang. |
| 3. Script đọc cookie | Cookie không có HttpOnly nên đọc được bằng JavaScript. | HttpOnly ngăn đọc giá trị cookie trực tiếp. |
| 4. Kẻ tấn công dùng cookie | Server chấp nhận bearer session ID còn hiệu lực. | TTL, phát hiện bất thường, thu hồi phía server, step-up thao tác nhạy cảm. |
| 5. Kẻ tấn công truy cập dữ liệu | API chỉ kiểm tra session mà không giới hạn quyền theo resource. | Authorization ở mỗi API, tenant/resource scoping, audit. |

**Nếu cookie có HttpOnly**, bước 3 có thể bị chặn: JavaScript thông thường không đọc được giá trị cookie. Tuy nhiên, XSS vẫn có thể gửi request cùng origin và đọc response mà trang được phép truy cập, nên bước 4/5 có thể vẫn xảy ra dưới dạng **session riding**. HttpOnly là lớp giảm thiểu, không thay thế sửa XSS.

### Thiết kế giảm thiểu

- Vá lỗi XSS ở nơi dữ liệu được đưa vào DOM; encode đúng ngữ cảnh và tránh API render HTML không an toàn.
- Bật CSP phù hợp, giảm inline script và giới hạn nguồn script; xem xét Trusted Types khi nền tảng hỗ trợ.
- Đặt cookie \`Secure; HttpOnly; SameSite\` phù hợp; dùng prefix \`__Host-\` nếu tương thích.
- Dùng session TTL hợp lý, thu hồi nhanh khi có sự cố; không cho phiên có quyền quá rộng.
- Yêu cầu xác thực lại cho thao tác thêm credential, thay kênh khôi phục, xuất dữ liệu hoặc giao dịch nhạy cảm.
- Giám sát request bất thường và có chức năng đăng xuất/thu hồi từng thiết bị.

**Bài học:** passkey chống phishing ở bước đăng nhập, nhưng không tự bảo vệ ứng dụng khỏi XSS hoặc đánh cắp cookie sau đăng nhập. Các lớp kiểm soát giải quyết các điểm khác nhau trong vòng đời.

## 13. Kiểm thử threat model cho session hijacking

Trước khi phát hành, kiểm tra các kịch bản:

| Kiểm thử | Kết quả mong đợi |
| --- | --- |
| Đoán session ID hoặc gửi ID tuần tự | Không thể dự đoán phiên hợp lệ; ID sai bị từ chối. |
| Đặt session ID trước đăng nhập rồi yêu cầu nạn nhân đăng nhập | Server phát hành ID mới và vô hiệu hóa ID cũ. |
| Gửi cookie qua HTTP | Cookie Secure không được gửi; HTTP được chuyển hướng/chặn theo chính sách. |
| JavaScript đọc cookie HttpOnly | Không lấy được giá trị cookie qua API JavaScript thông thường. |
| Script XSS gửi request cùng origin | Kiểm tra CSP/XSS và xác nhận thao tác nhạy cảm có step-up/CSRF phù hợp; HttpOnly không được xem là đủ. |
| Gửi request thay đổi trạng thái từ origin không tin cậy | CSRF token/Origin/SameSite chặn request theo chính sách. |
| Logout rồi phát lại cookie cũ | Server từ chối session đã thu hồi. |
| Dùng session sau idle/absolute timeout | Bị từ chối và yêu cầu xác thực lại. |
| Dùng refresh token cũ sau rotation | Phát hiện reuse và xử lý token family theo chính sách. |
| JWT sai chữ ký, issuer, audience hoặc hết hạn | API từ chối; không giải mã payload rồi tin. |
| Session hợp lệ nhưng truy cập tenant/resource khác | API từ chối do phân quyền. |
| Giả lập IP/UA thay đổi hợp lệ | Không khóa cứng chỉ vì một tín hiệu; đánh giá rủi ro tổng hợp. |

Kiểm thử cần bao gồm cả **positive case**: người dùng hợp lệ đổi mạng, mở nhiều tab, sử dụng SSO, refresh token đúng cách và đăng xuất. Một biện pháp chống chiếm phiên gây mất phiên liên tục có thể làm giảm an toàn thực tế nếu người dùng tìm cách né hoặc tắt nó.

## 14. Danh sách rà soát khi thiết kế phiên

- [ ] Session ID/token được tạo bằng cơ chế ngẫu nhiên mật mã hoặc giao thức phát hành an toàn, không thể đoán và không chứa thông tin nhạy cảm.
- [ ] ID phiên được đổi sau đăng nhập và các lần nâng quyền phù hợp; session fixation được kiểm soát.
- [ ] Cookie web dùng HTTPS, Secure, HttpOnly, SameSite và phạm vi Domain/Path phù hợp.
- [ ] Toàn bộ luồng sử dụng TLS; có HSTS và tránh mixed content.
- [ ] Token không xuất hiện trong URL, log, analytics, crash report hoặc kho client không phù hợp.
- [ ] XSS được giảm thiểu bằng encoding, CSP và quản lý script/dependency; HttpOnly không bị xem là giải pháp XSS hoàn chỉnh.
- [ ] Endpoint dựa vào cookie bảo vệ CSRF; thao tác nhạy cảm có xác thực lại/step-up.
- [ ] Có idle timeout, absolute timeout, xoay vòng và thu hồi session phía server.
- [ ] Refresh token được bảo vệ, rotation/reuse detection và cơ chế thu hồi được kiểm thử.
- [ ] API xác minh phiên/token, issuer/audience/thời hạn/chữ ký khi phù hợp, rồi kiểm tra quyền ở từng resource.
- [ ] Có khả năng xem/thu hồi phiên theo thiết bị và phản ứng khi nghi chiếm tài khoản.
- [ ] Log đủ điều tra nhưng không chứa session ID, cookie, access token, refresh token hoặc khóa bí mật thô.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một người dùng đã đăng nhập bằng passkey và MFA. Vì sao kẻ tấn công lấy được cookie phiên vẫn có thể truy cập tài khoản?

**Gợi ý:** Cookie đại diện cho phiên đã xác thực; server có thể chấp nhận bearer credential mà không yêu cầu lặp lại passkey/MFA ở mọi request.

**Câu 2.** HttpOnly có ngăn được XSS hoàn toàn không?

**Gợi ý:** Không. Nó ngăn JavaScript đọc cookie, nhưng script cùng origin vẫn có thể thực hiện request bằng cookie tự động được trình duyệt gửi.

**Câu 3.** Vì sao CSRF không nhất thiết là session hijacking?

**Gợi ý:** CSRF lợi dụng trình duyệt tự gửi cookie của nạn nhân; kẻ tấn công không nhất thiết biết hoặc sở hữu giá trị cookie.

**Câu 4.** Tại sao xóa cookie ở trình duyệt chưa đủ để logout an toàn?

**Gợi ý:** Bản sao cookie đã bị đánh cắp vẫn còn dùng được nếu server chưa thu hồi session.

**Câu 5.** Nếu IP của người dùng thay đổi giữa hai request, có nên lập tức thu hồi session không?

**Gợi ý:** IP là tín hiệu rủi ro, không phải bằng chứng tuyệt đối. Cần kết hợp nhiều tín hiệu và chính sách phù hợp để tránh khóa nhầm.

**Câu 6.** Refresh token rotation giúp ích gì khi token bị sao chép?

**Gợi ý:** Token cũ bị vô hiệu hóa sau khi dùng; nếu phát hiện token cũ bị dùng lại, server có thể phát hiện khả năng bị sao chép và thu hồi token family.

## 16. Ghi nhớ

**Session hijacking là chiếm khả năng sử dụng một phiên đã được xác thực.** Nó có thể xảy ra qua nghe lén mạng, XSS, malware, session fixation, token leakage hoặc quản lý logout/thu hồi yếu. Để giảm rủi ro, hệ thống cần bảo vệ session ID và token khi tạo, truyền, lưu trữ và sử dụng; xoay vòng sau đăng nhập/nâng quyền; đặt thời hạn hợp lý; thu hồi phía server; chống XSS/CSRF; kiểm tra quyền trên từng API; và có quy trình phát hiện, phản ứng sự cố. MFA và passkey bảo vệ bước đăng nhập, còn bảo vệ phiên duy trì sự tin cậy sau bước đó.
