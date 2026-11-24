# Authentication trong vòng đời hệ thống

> **Chương: Bức tranh tổng thể.** Authentication (xác thực) là quá trình kiểm tra bằng chứng để xác định một chủ thể đang tương tác với hệ thống là ai hoặc đang kiểm soát danh tính nào. Trong một hệ thống thực tế, authentication bắt đầu từ lúc thiết kế cách định danh và cấp credential, tiếp diễn khi đăng nhập và duy trì phiên, rồi xuất hiện trở lại khi đổi thiết bị, liên kết tài khoản, khôi phục truy cập, xử lý sự cố và ngừng cung cấp dịch vụ.

Một màn hình đăng nhập hoạt động không có nghĩa hệ thống đã có kiến trúc xác thực an toàn. Nếu tài khoản có thể bị chiếm qua luồng đặt lại mật khẩu, token bị chấp nhận ở sai API, phiên không bị thu hồi khi nhân viên nghỉ việc hoặc cách đăng nhập dự phòng dễ bị phishing, hệ thống vẫn có điểm yếu nghiêm trọng. Bài học này đặt authentication vào **toàn bộ vòng đời của hệ thống** và kết nối các thành phần: credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản.

## 1. Hai vòng đời diễn ra đồng thời

Khi nói “vòng đời hệ thống”, cần phân biệt hai trục thời gian có liên hệ mật thiết:

1. **Vòng đời sản phẩm và hạ tầng:** xác định yêu cầu → thiết kế và mô hình hóa đe dọa → phát triển → triển khai → vận hành, giám sát → thay đổi, ứng phó sự cố → ngừng dịch vụ.
2. **Vòng đời danh tính và quyền truy cập:** tạo danh tính → xác minh thuộc tính cần thiết → đăng ký phương thức xác thực → đăng nhập → phát hành và sử dụng phiên/token → xác thực lại hoặc đổi credential → khôi phục → vô hiệu hóa/xóa tài khoản.

Một thay đổi ở trục thứ nhất luôn có thể tác động tới trục thứ hai. Ví dụ: khi hệ thống chuyển từ phiên lưu trên máy chủ sang JWT tự chứa, cách thu hồi phiên cũng phải được thiết kế lại; khi thêm đăng nhập qua nhà cung cấp danh tính (Identity Provider, **IdP**), quy trình liên kết danh tính và xử lý tài khoản trùng phải được xem xét.

| Giai đoạn của hệ thống | Câu hỏi authentication cần trả lời | Đầu ra hoặc cơ chế cần có |
| --- | --- | --- |
| Phân tích yêu cầu | Ai đăng nhập? Rủi ro của việc giả mạo là gì? | Loại chủ thể, mức bảo đảm, các hành động nhạy cảm |
| Thiết kế | Ai xác minh bằng chứng? Dữ liệu nào vượt ranh giới tin cậy? | Luồng đăng nhập, kho credential, phiên/token, phục hồi |
| Phát triển và kiểm thử | Có thể bỏ qua bước xác thực hay dùng lại bằng chứng cũ không? | Kiểm thử luồng thành công, thất bại, replay, lạm dụng |
| Triển khai | Bí mật, khóa, chứng chỉ và cấu hình cookie được bảo vệ thế nào? | Quản lý khóa, cấu hình TLS, redirect URI, luân chuyển bí mật |
| Vận hành | Làm sao nhận ra credential stuffing, phishing hoặc chiếm phiên? | Nhật ký, cảnh báo, giới hạn tốc độ, hỗ trợ người dùng |
| Thay đổi/ứng phó sự cố | Đổi phương thức đăng nhập, thu hồi credential, token ra sao? | Kế hoạch di trú, thu hồi, xử lý phiên hiện hữu |
| Ngừng dịch vụ hoặc tài khoản | Quyền truy cập nào phải chấm dứt? | Vô hiệu hóa chủ thể, phiên và credential, chính sách dữ liệu |

### 1.1. Ba câu hỏi xuyên suốt

- **Chủ thể là ai?** Có thể là người dùng cuối, quản trị viên, ứng dụng tự động, dịch vụ nội bộ hoặc thiết bị. Mỗi loại cần cơ chế xác thực phù hợp.
- **Bằng chứng gì được kiểm tra?** Mật khẩu, khóa riêng của passkey, mã OTP, khóa riêng tương ứng chứng chỉ, hoặc một token do bên phát hành đáng tin cậy cấp.
- **Hệ thống được phép tin điều gì sau khi xác thực?** Kết quả xác thực thường chỉ khẳng định chủ thể kiểm soát một credential ở một thời điểm, với mức bảo đảm nhất định. Nó không tự khẳng định chủ thể có mọi quyền truy cập hoặc mọi thông tin hồ sơ đều đúng.

## 2. Làm rõ các khái niệm dễ nhầm

**Identification (khai báo danh tính)** là bước người dùng nói họ là ai, chẳng hạn nhập tên đăng nhập. **Identity proofing (kiểm chứng danh tính ngoài đời)** là quy trình xác minh các thuộc tính danh tính khi nghiệp vụ yêu cầu, chẳng hạn thủ tục định danh khách hàng. **Authentication** kiểm tra bằng chứng kiểm soát một danh tính đã được đăng ký. **Authorization** quyết định chủ thể đã xác thực được phép thực hiện hành động nào trên tài nguyên nào.

Ví dụ, việc người dùng xác minh địa chỉ email chỉ chứng minh họ kiểm soát hộp thư tại thời điểm xác minh; không chứng minh tên thật, tuổi hay tư cách nhân viên. Người dùng đăng nhập thành công có thể được phép xem khóa học mình đăng ký, nhưng không được phép xem dữ liệu học viên khác. Kiểm tra quyền phải diễn ra độc lập ở các API xử lý dữ liệu, kể cả khi phía giao diện đã ẩn nút chức năng.

Các thành phần thường gặp:

| Thuật ngữ | Vai trò | Điều không nên suy diễn |
| --- | --- | --- |
| **Principal / subject** | Chủ thể mà hệ thống gắn danh tính và quyền | Tên hiển thị hoặc email luôn là khóa định danh bất biến |
| **Credential** | Bằng chứng/chất liệu để chứng minh quyền kiểm soát danh tính | Mọi credential đều có cùng khả năng chống phishing |
| **Authenticator** | Vật hoặc phần mềm tạo ra phản hồi xác thực: ứng dụng OTP, khóa bảo mật, passkey | Sở hữu điện thoại đồng nghĩa luôn sở hữu tài khoản |
| **Authentication service / IdP** | Kiểm tra bằng chứng, xây dựng kết quả xác thực, cấp phiên hoặc assertion | Mọi dữ liệu IdP trả về đều có thể tin mà không kiểm tra |
| **Session** | Trạng thái một lần tương tác đã được xác thực | Phiên còn tồn tại nghĩa là quyền không bao giờ đổi |
| **Token** | Chứng thư dữ liệu đại diện cho kết quả hoặc quyền được cấp trong phạm vi xác định | Token hợp lệ về chữ ký là đủ để dùng ở mọi nơi |
| **Relying Party (RP)** | Ứng dụng tin vào kết quả từ IdP, sau khi kiểm tra phù hợp | RP có thể bỏ qua việc kiểm tra issuer, audience và trạng thái tài khoản |

Một tài khoản có thể liên kết với **nhiều credential** (mật khẩu, hai passkey, một khóa bảo mật) và **nhiều phiên** (máy tính, điện thoại). Vì vậy, xóa một credential không nhất thiết xóa tài khoản; đăng xuất ở một thiết bị không mặc nhiên đăng xuất tất cả thiết bị.

## 3. Ranh giới tin cậy: nơi authentication thực sự xảy ra

Trong thiết kế bảo mật, câu hỏi quan trọng là: **đâu là đầu vào chưa được tin, và thành phần nào có thẩm quyền biến đầu vào đó thành một kết luận có thể dùng?**

~~~mermaid
flowchart LR
    U["Trình duyệt / ứng dụng<br/>Vùng không tin cậy"] -->|"TLS + credential / cookie"| G["BFF hoặc API Gateway"]
    G -->|"Yêu cầu xác thực"| A["Authentication Service"]
    A -->|"Đọc verifier / khóa công khai"| D[("Kho tài khoản<br/>và credential")]
    A <-->|"OIDC / SAML, nếu có"| I["IdP ngoài hệ thống"]
    A -->|"Cấp / thu hồi phiên"| S[("Session Store")]
    G -->|"Ngữ cảnh đã kiểm tra"| R["Resource API"]
    R -->|"Kiểm tra quyền theo tài nguyên"| P["Authorization / Policy"]
~~~

*Sơ đồ khái niệm; hệ thống thực tế có thể gộp hoặc tách các dịch vụ. Mọi kết nối và lời khẳng định đi qua ranh giới đều cần cơ chế kiểm chứng riêng.*

Các ranh giới cần đặc biệt chú ý:

1. **Client → server:** trình duyệt, ứng dụng di động và mọi tham số do client gửi có thể bị sửa. Không tin vào header tự khai như X-User-Id, trường role trong request hay việc nút chức năng đã bị ẩn.
2. **Gateway → service nội bộ:** một service không nên tin header danh tính chỉ vì request “đến từ mạng nội bộ”. Cần đường truyền được bảo vệ, xác thực workload và quy tắc rõ ràng về thành phần được phép chèn/chuyển tiếp ngữ cảnh danh tính.
3. **Ứng dụng → IdP ngoài:** chỉ chấp nhận issuer đã cấu hình; xác minh chữ ký/assertion, người nhận, thời hạn, state/nonce khi phù hợp và ánh xạ danh tính chính xác.
4. **Token → Resource API:** API phải kiểm tra token được cấp **cho chính API đó** (audience), từ issuer được tin cậy, đúng loại, còn hạn và đáp ứng chính sách; chữ ký hợp lệ một mình là chưa đủ.
5. **Môi trường vận hành → kho khóa/bí mật:** credential verifier, private key, khóa ký và refresh token không được xuất hiện trong log, mã nguồn hoặc cấu hình công khai.

Quy tắc thiết kế: **mỗi thành phần phải xác minh đúng lời khẳng định mà nó sử dụng**, tại ranh giới nơi dữ liệu đi vào. Nếu BFF xác thực người dùng, Resource API vẫn cần cách đáng tin cậy để nhận và kiểm tra danh tính mà BFF chuyển sang, đồng thời luôn kiểm tra quyền theo nghiệp vụ.

## 4. Giai đoạn phân tích và thiết kế: xác định mức bảo đảm

Không phải mọi thao tác cần cùng mức xác thực. Đọc nội dung khóa học đã mua, đổi địa chỉ email khôi phục, xuất dữ liệu cá nhân và cấp quyền quản trị có tác động rất khác nhau.

### 4.1. Lập bản đồ chủ thể, tài sản và hành động nhạy cảm

Một bản đặc tả hữu ích cần ghi rõ:

- **Ai:** học viên, giảng viên, quản trị viên, bộ phận hỗ trợ, job nền, tích hợp bên thứ ba.
- **Được bảo vệ cái gì:** tài khoản, dữ liệu cá nhân, thông tin thanh toán, khóa API, thông tin lớp học, chức năng đổi vai trò.
- **Trạng thái nào:** mới đăng ký, chưa xác minh, đang hoạt động, đang cần xác thực bổ sung, bị tạm khóa, đang khôi phục, đã vô hiệu hóa.
- **Bằng chứng nào ở mỗi hành động:** đăng nhập cơ bản, MFA, passkey chống phishing, xác thực lại gần đây, xác nhận của quản trị viên hoặc quy trình phê duyệt riêng.
- **Cách thất bại an toàn:** nếu IdP hoặc dịch vụ xác thực gián đoạn, hành động nhạy cảm có bị chặn không; có cơ chế truy cập khẩn cấp đã kiểm soát hay không.

### 4.2. Mô hình hóa đe dọa theo luồng

| Điểm trong vòng đời | Kịch bản tấn công | Kiểm soát thiết kế điển hình |
| --- | --- | --- |
| Đăng ký | Tạo tài khoản hàng loạt, dò email tồn tại | Giới hạn tốc độ, phát hiện tự động hóa, phản hồi hạn chế lộ thông tin |
| Kiểm tra credential | Credential stuffing, thử mật khẩu, lộ cơ sở dữ liệu hash | Mã hóa mật khẩu bằng thuật toán hash chậm có salt, kiểm soát thử sai theo nhiều chiều, MFA |
| MFA | Trang giả mạo lấy OTP, push fatigue, đánh cắp mã dự phòng | Ưu tiên passkey/khóa bảo mật, number matching cho push khi phù hợp, cảnh báo và giới hạn thử |
| Callback SSO | Login CSRF, tráo authorization code, nhầm issuer | Redirect URI chính xác, state, nonce, PKCE, kiểm tra issuer/audience |
| Phiên/token | Session fixation, trộm cookie, replay token | Đổi session ID khi đăng nhập, cookie an toàn, TTL, thu hồi, ràng buộc token khi cần |
| Liên kết tài khoản | Liên kết email trùng làm nhập nhằng danh tính | Xác thực lại các bên, xác minh chủ thể, không tự động gộp chỉ vì email giống |
| Khôi phục | Chiếm tài khoản qua email/điện thoại hoặc nhân viên hỗ trợ | Xác minh đủ mạnh, token một lần, chống enumeration, cảnh báo và quy trình kiểm soát |
| Rời tổ chức | Tài khoản đã nghỉ việc vẫn còn phiên/refresh token | Đồng bộ deprovisioning, vô hiệu hóa chủ thể, thu hồi phiên và credential |

Threat modeling là hoạt động lặp lại: khi thêm passkey, SSO, ứng dụng di động hay tính năng đăng nhập “nhớ tôi”, cần cập nhật luồng dữ liệu và giả định về ranh giới tin cậy.

## 5. Tạo tài khoản và đăng ký credential

Vòng đời của một danh tính thường bắt đầu bằng **account provisioning**: hệ thống cấp một định danh nội bộ ổn định, xác định trạng thái tài khoản và liên kết các phương thức xác thực. Định danh nội bộ nên là khóa bất biến, không lấy email hoặc số điện thoại làm khóa chính vì chúng có thể thay đổi hoặc được tái cấp.

Một luồng đăng ký an toàn theo trình tự:

1. Thu thập tối thiểu thông tin cần thiết; giới hạn hành vi tạo tài khoản tự động theo rủi ro.
2. Tạo tài khoản ở trạng thái phù hợp, chẳng hạn **PENDING_VERIFICATION**, với định danh nội bộ riêng.
3. Nếu cần xác minh email/số điện thoại, gửi thử thách có thời hạn, sử dụng một lần, gắn với tài khoản và mục đích cụ thể; tránh để token lộ qua URL, referrer hoặc log.
4. Đăng ký ít nhất một phương thức xác thực, và khuyến khích thêm phương thức thứ hai hoặc mã khôi phục an toàn.
5. Sau khi các điều kiện hoàn tất, chuyển sang **ACTIVE**; ghi lại sự kiện quan trọng và gửi thông báo xác nhận.

Email được xác minh chỉ nên mang ý nghĩa “đã chứng minh kiểm soát email này trong quy trình tương ứng”. Với môi trường doanh nghiệp, quyền gia nhập một tenant hoặc sở hữu vai trò phải do chính sách của tổ chức quyết định, không dựa vào đuôi email đơn lẻ.

### 5.1. Cách hệ thống lưu verifier

| Phương thức | Bằng chứng khi đăng nhập | Máy chủ nên giữ gì? | Lưu ý vòng đời |
| --- | --- | --- | --- |
| Mật khẩu | Bí mật người dùng biết | Hash mật khẩu bằng Argon2id hoặc thuật toán phù hợp, salt riêng, tham số chi phí được quản lý | Đổi mật khẩu, kiểm tra mật khẩu lộ, thu hồi phiên khi nghi ngờ |
| TOTP | Mã theo thời gian từ secret chung | Secret được bảo vệ và trạng thái chống dùng lại mã trong cửa sổ chấp nhận | Đăng ký lại khi mất thiết bị; bí mật chung có thể bị lộ |
| Passkey / WebAuthn | Chữ ký thử thách bằng khóa riêng gắn với RP ID/origin | Credential ID, khóa công khai và metadata cần thiết | Có thể dùng passkey đồng bộ hoặc gắn thiết bị; cần nhiều đường khôi phục |
| Chứng chỉ client | Chứng minh sở hữu khóa riêng tương ứng chứng chỉ | Chuỗi tin cậy, chính sách tên định danh, trạng thái chứng chỉ | Cấp phát, gia hạn, thu hồi và bảo vệ khóa riêng |
| Mã khôi phục | Chuỗi ngẫu nhiên sử dụng một lần | Bản băm hoặc dạng verifier được bảo vệ, trạng thái đã dùng | Chỉ phát một lần; cấp lại làm vô hiệu các mã cũ theo chính sách |

**Mật khẩu:** không lưu plaintext, mã hóa đảo ngược hoặc hash nhanh thuần túy như SHA-256 để làm kho mật khẩu. Dùng thuật toán password hashing chuyên dụng với salt và tham số phù hợp năng lực hệ thống; nếu dùng pepper thì bảo vệ riêng trong hệ thống quản lý bí mật. Cho phép mật khẩu dài, dùng trình quản lý mật khẩu và kiểm tra mật khẩu đã lộ; không buộc đổi định kỳ một cách máy móc nếu không có dấu hiệu rủi ro hoặc chính sách đặc thù.

**Passkey:** trong WebAuthn, server gửi thử thách mới và kiểm tra chữ ký với khóa công khai đã đăng ký cùng thông tin RP ID/origin, loại thao tác, thử thách và yêu cầu xác minh người dùng. Private key không được gửi tới server. Passkey có khả năng chống phishing tốt vì bằng chứng được ràng buộc với domain/RP hợp lệ; hiệu quả thực tế còn phụ thuộc bảo mật thiết bị, đồng bộ khóa và quy trình khôi phục. Không coi “đã có passkey” là an toàn nếu vẫn tồn tại đường dự phòng yếu hơn.

**Chứng chỉ:** phù hợp trong nhiều trường hợp xác thực thiết bị, workload hoặc người dùng doanh nghiệp. Chỉ sở hữu một tệp chứng chỉ công khai không đủ; phía được xác thực phải chứng minh sở hữu khóa riêng. Thành phần kiểm chứng phải xác minh chuỗi tin cậy, danh tính kỳ vọng, thời hạn, mục đích sử dụng và chính sách thu hồi phù hợp.

## 6. Đăng nhập: từ bằng chứng đến phiên có hiệu lực

Một luồng đăng nhập chuẩn không đơn thuần là so sánh mật khẩu. Nó cần kiểm tra trạng thái tài khoản, nguồn request, giới hạn thử sai, bằng chứng bổ sung và cách phát hành phiên.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client
    participant A as Authentication Service
    participant V as Credential/Verifier Store
    participant S as Session Store
    U->>C: Bắt đầu đăng nhập
    C->>A: Identifier + bằng chứng qua TLS
    A->>A: Kiểm soát lạm dụng, trạng thái, rủi ro
    A->>V: Kiểm tra verifier hoặc public key
    V-->>A: Kết quả đối chiếu
    alt Bằng chứng hợp lệ và đủ mức bảo đảm
        A->>S: Tạo phiên mới, lưu metadata tối thiểu
        A-->>C: Cookie phiên an toàn / kết quả xác thực
        C-->>U: Cho phép vào ứng dụng
    else Cần xác thực bổ sung
        A-->>C: Yêu cầu MFA / step-up
    else Không đạt
        A-->>C: Lỗi chung, ghi nhận thất bại
    end
~~~

Các bước cốt lõi:

1. **Tiếp nhận:** truyền bằng chứng qua TLS; chuẩn hóa identifier theo quy tắc nhất quán, tránh nhập nhằng giữa các tenant.
2. **Chống lạm dụng:** áp dụng giới hạn và đánh giá rủi ro theo tài khoản, nguồn truy cập, thiết bị và hành vi; có chiến lược tránh khiến kẻ tấn công dễ khóa tài khoản nạn nhân.
3. **Kiểm tra bằng chứng:** so khớp password verifier, xác minh chữ ký WebAuthn, TOTP hoặc kết quả IdP theo đúng giao thức.
4. **Đánh giá mức bảo đảm:** MFA/step-up nếu nghiệp vụ, thiết bị hoặc tín hiệu rủi ro yêu cầu; không cho phép bỏ qua bước bổ sung do client gửi cờ tự khai.
5. **Phát hành phiên:** tạo session ID mới đủ ngẫu nhiên, gắn chủ thể, thời điểm, phương thức, mức bảo đảm và thời hạn; thay session ID cũ có nguy cơ fixation.
6. **Ghi nhận:** log sự kiện đăng nhập thành công/thất bại và những thay đổi quan trọng, không ghi mật khẩu, OTP, recovery code hoặc token nguyên dạng.

Pseudocode minh họa ranh giới kiểm chứng:

~~~text
authenticate(request):
    enforce_abuse_controls(request)
    account = lookup_account_with_tenant_scope(request.identifier)
    result = verify_credential_without_leaking_account_existence(account, request.proof)
    if result is not valid or account is not eligible:
        record_security_event("login_failed", minimal_context)
        return generic_failure

    assurance = evaluate_method_and_risk(result, request.context)
    if assurance is insufficient:
        return begin_server_controlled_step_up(account)

    session = create_new_opaque_session(account.id, assurance, bounded_expiry)
    record_security_event("login_succeeded", account.id)
    return set_secure_session_cookie(session)
~~~

Đây là **pseudocode** để thể hiện trách nhiệm thành phần; triển khai cần thiết kế thêm chống CSRF, quy tắc lưu phiên, kiểm tra đầu vào, chống enumeration và chính sách lỗi. Không dựa vào mã giả này như một thư viện xác thực hoàn chỉnh.

### 6.1. MFA và mức chống phishing

MFA kết hợp **các loại yếu tố khác nhau**: điều biết (mật khẩu), điều sở hữu (thiết bị/khóa) và đặc điểm sinh trắc để mở authenticator khi phù hợp. Hai mật khẩu hoặc mật khẩu cộng câu hỏi bí mật vẫn thuộc cùng loại yếu tố kiến thức, không tạo MFA đúng nghĩa.

| Cách xác thực | Ưu điểm | Rủi ro chính |
| --- | --- | --- |
| Mật khẩu | Dễ triển khai, tương thích rộng | Phishing, tái sử dụng, credential stuffing |
| Mật khẩu + SMS OTP | Có thêm rào cản ngoài mật khẩu | SIM swap, phishing OTP, phụ thuộc mạng di động |
| Mật khẩu + TOTP | Không phụ thuộc SMS, triển khai phổ biến | Mã có thể bị phishing theo thời gian thực hoặc bị dùng lại nếu không kiểm soát |
| Push approval | Thao tác thuận tiện | Push fatigue và chấp thuận nhầm; cần ngữ cảnh giao dịch, biện pháp chống spam |
| Passkey / khóa bảo mật FIDO2 | Chống phishing bằng ràng buộc origin/RP; không chia sẻ bí mật có thể dùng lại với server | Rủi ro thiết bị, quy trình thêm/xóa authenticator và recovery |

Nếu hệ thống có các phương thức đăng nhập song song, **mức bảo đảm của tài khoản phụ thuộc cả vào đường yếu nhất cho phép tiếp quản tài khoản**. Ví dụ, sử dụng passkey hằng ngày nhưng cho phép đặt lại tất cả credential bằng một email dễ bị chiếm có thể làm mất ý nghĩa của lớp bảo vệ mạnh.

## 7. Phiên và token: bằng chứng tiếp tục qua nhiều request

Mỗi request đến API không thể yêu cầu người dùng nhập lại mật khẩu. Sau đăng nhập, hệ thống cần cơ chế mang theo kết quả đã được xác minh. Hai mô hình phổ biến là **phiên do server quản lý** và **token do bên phát hành cấp**; chúng có thể cùng tồn tại.

### 7.1. Phiên dựa trên cookie

Server tạo một định danh phiên ngẫu nhiên, lưu thông tin phiên phía server và gửi cookie cho trình duyệt. Các request tiếp theo trình duyệt gửi cookie, server tra trạng thái để quyết định phiên có còn hiệu lực.

Các điểm phải thiết kế:

- Cookie dùng **Secure** để chỉ gửi qua HTTPS; **HttpOnly** để giảm nguy cơ JavaScript đọc cookie; **SameSite** phù hợp với nhu cầu điều hướng và chính sách CSRF. Khi có thao tác thay đổi trạng thái, áp dụng bảo vệ CSRF phù hợp, không chỉ dựa vào SameSite.
- Session ID phải khó đoán và **được cấp lại sau đăng nhập hoặc nâng quyền**; không giữ nguyên identifier đã tồn tại trước xác thực.
- Có thời hạn **không hoạt động** (idle timeout) và **tối đa** (absolute timeout) theo rủi ro; xác thực lại cho hành động nhạy cảm ngay cả khi phiên thường vẫn còn hạn.
- Chặn tiếp tục sử dụng phiên khi tài khoản bị vô hiệu hóa, quyền thay đổi hoặc phát hiện chiếm phiên; hỗ trợ đăng xuất thiết bị hiện tại và có chủ đích đăng xuất mọi thiết bị.
- Không để session ID trong URL hoặc log; bảo vệ session store và kiểm soát truy cập tới dữ liệu phiên.

### 7.2. ID token, access token, refresh token khác nhau thế nào?

| Loại token | Người nhận / công dụng | Kiểm tra tối thiểu và lưu ý |
| --- | --- | --- |
| **ID token** (OpenID Connect) | Cho ứng dụng RP biết kết quả đăng nhập của người dùng với IdP | Xác minh issuer, audience là client, chữ ký, thời gian, nonce khi áp dụng; **không dùng làm access token của API** |
| **Access token** | Cho một resource server/API biết quyền truy cập trong phạm vi được cấp | Kiểm tra issuer, audience, thời hạn, quyền/scope và loại token; có thể là JWT hoặc opaque token |
| **Refresh token** | Client xin access token mới khi hết hạn | Bảo vệ rất chặt, giới hạn thời gian và phạm vi, rotation/phát hiện dùng lại hoặc ràng buộc sender tùy kiến trúc |
| **Session cookie** | Trình duyệt gửi handle tham chiếu phiên do ứng dụng quản lý | Kiểm tra trạng thái phiên trên server, timeout, chống fixation, CSRF và chính sách cookie |

**JWT** là một định dạng token, không phải giao thức authentication hay giải pháp quản lý phiên hoàn chỉnh. Nếu nhận JWT, resource server phải dùng thuật toán từ allowlist, kiểm tra khóa đúng issuer, chữ ký, thời hạn (exp/nbf), audience, issuer và các claim bắt buộc theo chính sách. Không tự tin dữ liệu header như “alg” hoặc “kid” để tải khóa từ nguồn chưa được chấp thuận. Chữ ký hợp lệ cũng không chứng minh token chưa bị đánh cắp; bearer token ai cầm được thường có thể dùng được.

**Replay** là việc dùng lại bằng chứng hợp lệ đã bị sao chép hoặc đã từng sử dụng. Với OTP, cần chính sách hạn chế sử dụng lại trong cùng cửa sổ; với WebAuthn, mỗi yêu cầu cần thử thách mới và xác minh phản hồi tương ứng; với token, giảm cửa sổ lạm dụng bằng TTL, bảo vệ truyền/lưu trữ, theo dõi và cơ chế sender-constrained như DPoP hoặc mTLS khi mức rủi ro phù hợp. Các công nghệ này giải quyết những mặt khác nhau của replay, không thay thế nhau.

### 7.3. Chọn mô hình phiên theo kiến trúc

- Ứng dụng web có backend riêng thường dễ kiểm soát thu hồi bằng **session server-side + cookie**. Mô hình BFF còn giúp hạn chế việc browser trực tiếp giữ access token nếu thiết kế phù hợp.
- Với API phân tán hoặc tích hợp bên thứ ba, **access token có audience/scope rõ ràng** thuận tiện hơn. Nếu dùng JWT tự chứa, cần chiến lược thu hồi, hạn ngắn hoặc kiểm tra bổ sung khi cần.
- Ứng dụng native cần kho lưu trữ an toàn của hệ điều hành cho token/bí mật và luồng đăng nhập phù hợp nền tảng; không hardcode client secret vào ứng dụng phát hành công khai.

Một session còn hạn chỉ xác nhận một ngữ cảnh đăng nhập trước đó. Mỗi API vẫn phải kiểm tra trạng thái tài khoản và **authorization hiện tại** theo thiết kế; việc đã đăng nhập không cho phép bỏ qua quyền truy cập.

## 8. SSO, giao thức liên kết và thay đổi danh tính

Nhiều hệ thống không trực tiếp kiểm tra mật khẩu. Ứng dụng có thể ủy nhiệm authentication cho IdP doanh nghiệp, sau đó nhận kết quả theo OpenID Connect (OIDC) hoặc SAML. Điều này chuyển một phần điểm tin cậy sang IdP và làm xuất hiện các hoạt động liên kết danh tính, thu hồi, đồng bộ trạng thái.

### 8.1. Mô hình OIDC cho ứng dụng web

Trong một luồng Authorization Code với PKCE:

1. Ứng dụng tạo state và PKCE code verifier/challenge, chuyển người dùng tới authorization endpoint của IdP với redirect URI đã đăng ký chính xác.
2. Người dùng xác thực tại IdP; IdP trả authorization code về redirect URI hợp lệ.
3. Ứng dụng kiểm tra state, dùng code verifier đổi code lấy token qua kênh thích hợp; code phải có vòng đời ngắn và chỉ dùng một lần.
4. RP xác minh ID token theo issuer/audience, chữ ký, thời gian và nonce nếu dùng; ánh xạ cặp **issuer + subject** của IdP vào tài khoản nội bộ.
5. Ứng dụng thiết lập phiên riêng; resource API kiểm tra access token đúng đối tượng nhận nếu API nhận token.

**OAuth 2.0** chủ yếu là khuôn khổ ủy quyền truy cập; **OIDC** bổ sung lớp xác thực danh tính. Không coi một OAuth access token do nhà cung cấp phát ra là bằng chứng danh tính đầy đủ nếu chưa có giao thức và phép kiểm tra phù hợp. Với SAML cũng phải kiểm tra chữ ký, audience/recipient, thời gian, InResponseTo và cấu hình nhà phát hành theo bối cảnh.

### 8.2. Liên kết và gỡ liên kết tài khoản

Email trùng nhau ở hai nhà cung cấp không đủ để kết luận là một người hoặc một danh tính nội bộ. Email có thể thay đổi, chưa xác minh, bị thu hồi hoặc tái cấp; IdP khác nhau có namespace khác nhau.

Quy trình liên kết an toàn điển hình: người dùng đang có phiên nội bộ hợp lệ → **xác thực lại gần đây** với phương thức đủ mạnh → xác thực tại IdP cần liên kết → kiểm tra issuer và subject → xác nhận hành động liên kết → ghi audit và thông báo. Nếu hệ thống cho phép gỡ một credential/IdP, cần bảo đảm tài khoản vẫn có đường đăng nhập/khôi phục phù hợp và không mở cửa cho kẻ đã chiếm phiên thay toàn bộ phương thức xác thực.

Trong hệ thống đa tenant, ánh xạ danh tính cần bao gồm **tenant** và chính sách thành viên. Không tự động gán tài khoản vào tenant chỉ vì tên miền email hoặc giá trị subject trông giống nhau.

## 9. Xác thực lại, thay đổi credential và hành động nhạy cảm

Đăng nhập là một sự kiện theo thời điểm; mức tin cậy giảm khi phiên kéo dài hoặc có tín hiệu bất thường. Hệ thống cần quy tắc **step-up authentication** cho việc rút ngắn khoảng cách giữa “đã từng xác thực” và “đủ tin cậy để làm việc này ngay bây giờ”.

Các hành động thường cần xác thực lại gần đây:

- Đổi mật khẩu, thêm/xóa passkey hoặc MFA.
- Thay email/số điện thoại khôi phục, lấy mã khôi phục mới.
- Liên kết tài khoản với IdP hoặc chuyển quyền sở hữu.
- Nâng quyền quản trị, xuất dữ liệu nhạy cảm hoặc thực hiện giao dịch có giá trị lớn.

Ví dụ: một giảng viên đã đăng nhập sáng nay; buổi chiều họ yêu cầu thêm tài khoản quản trị. API quản trị yêu cầu reauthentication với mức bảo đảm phù hợp, ghi nhận thời điểm xác thực và kiểm tra quyền phê duyệt. Client không được tự quyết “đã xác thực lại”; server phải đối chiếu chứng cứ hoặc ngữ cảnh xác thực do thành phần tin cậy cấp.

**Quy trình đổi mật khẩu** nên yêu cầu bằng chứng thích hợp, cập nhật verifier an toàn, thông báo sự kiện và đánh giá thu hồi các phiên/refresh token hiện có. **Quy trình thêm passkey** cũng nhạy cảm ngang với thêm phương thức kiểm soát tài khoản mới; cần xem kỹ quyền của phiên hiện tại và cảnh báo ngoài băng khi phù hợp.

## 10. Khôi phục tài khoản: một con đường authentication riêng

Khôi phục tài khoản xuất hiện khi người dùng mất credential hoặc thiết bị. Đây là **con đường thay đổi ai có thể đăng nhập trong tương lai**, do đó thường có rủi ro cao hơn một lần đăng nhập thông thường.

Một luồng khôi phục có thể gồm:

1. Người dùng yêu cầu khôi phục; phản hồi ở giao diện tránh xác nhận vô tình rằng tài khoản có tồn tại.
2. Server tạo token ngẫu nhiên đủ mạnh, một lần, thời hạn ngắn, gắn với tài khoản và mục đích cụ thể; lưu verifier/token hash thay vì ghi token thô vào log.
3. Người dùng chứng minh quyền kiểm soát kênh khôi phục đã đăng ký hoặc dùng mã khôi phục/credential thứ hai; trường hợp rủi ro cao có thể yêu cầu xác minh thủ công nhiều bước.
4. Sau khi kiểm tra, cho đăng ký lại credential; token cũ bị vô hiệu, phiên nghi ngờ bị thu hồi, tài khoản nhận thông báo về thay đổi.
5. Áp dụng hạn chế tạm thời đối với thao tác nhạy cảm khi chính sách yêu cầu và hỗ trợ báo cáo “đây không phải tôi”.

Phải mô hình hóa cả **khôi phục khi mất thiết bị** và **khôi phục khi kênh email/điện thoại đã bị kẻ khác chiếm**. Không dùng câu hỏi bảo mật có thể đoán hoặc tìm trên mạng làm nền tảng xác thực. Mã gửi qua email không nên được nâng thành bằng chứng bảo đảm cao nếu chính email cũng là điểm yếu của tài khoản.

Đối với tài khoản quản trị hoặc tài khoản có ảnh hưởng lớn, có thể yêu cầu xác minh trực tiếp, người phê duyệt thứ hai, thời gian chờ có thông báo hoặc quy trình đặc biệt. Những biện pháp này phải được thiết kế từ đầu để nhóm hỗ trợ không trở thành đường vòng bỏ qua MFA.

## 11. Thiết bị, dịch vụ và workload cũng có vòng đời xác thực

Authentication không chỉ dành cho con người. Cron job, CI/CD, microservice, máy chủ, thiết bị IoT và agent tự động đều có danh tính và credential.

Ví dụ service A gọi service B:

- Service A cần được cấp **workload identity** đủ hẹp và chứng minh danh tính qua mTLS, token dành cho service hoặc cơ chế danh tính của hạ tầng.
- Service B xác minh issuer/CA, tên workload, audience và trạng thái credential; sau đó **authorization** quyết định A được gọi hành động nào.
- Credential máy phải được cấp phát qua hệ thống quản lý bí mật, có vòng đời ngắn hoặc rotation, giám sát hạn và thu hồi khi workload bị hủy. Không dùng chung API key tĩnh cho mọi service nếu có giải pháp mạnh hơn.

Với mTLS, mỗi bên xác minh chứng chỉ đối tác theo chính sách tin cậy; việc kết nối được mã hóa không tự động cấp quyền nghiệp vụ. Với thiết bị, quá trình đăng ký thiết bị, thay thiết bị và mất thiết bị quan trọng như đăng ký user credential: server cần phân biệt danh tính thiết bị, danh tính người dùng và quyền truy cập.

## 12. Vận hành, thay đổi và ứng phó sự cố

Hệ thống authentication cần được vận hành như một dịch vụ bảo mật liên tục, không phải tính năng hoàn thành một lần.

### 12.1. Nhật ký và tín hiệu giám sát

Các sự kiện nên quan sát gồm: đăng nhập thành công/thất bại, tỷ lệ thử sai theo tài khoản và nguồn, challenge MFA bị từ chối liên tiếp, thêm/xóa credential, liên kết IdP, reset tài khoản, tạo/thu hồi phiên, cấp quyền quản trị, lỗi xác minh token, chứng chỉ gần hết hạn, bất thường về sử dụng refresh token.

Mỗi sự kiện nên có mã tương quan, thời điểm, loại hành động, trạng thái, phương thức, chủ thể (nếu xác định được) và bối cảnh tối thiểu phục vụ điều tra. **Không log password, OTP, recovery code, session ID nguyên dạng hoặc access/refresh token nguyên dạng.** Giới hạn người được đọc log và tuân thủ thời hạn lưu dữ liệu phù hợp.

Chỉ số vận hành hữu ích bao gồm tỷ lệ đăng nhập thành công theo phương thức, tỷ lệ người dùng không hoàn tất MFA, xu hướng khôi phục tài khoản, các đợt thất bại bất thường, độ trễ xác minh và tỷ lệ lỗi của IdP. Khi điều chỉnh chống bot hay rate limit, theo dõi cả số người dùng hợp lệ bị chặn để tránh gây ra DoS gián tiếp.

### 12.2. Luân chuyển khóa, cập nhật phương thức và thay đổi kiến trúc

- **Khóa ký token:** kế hoạch rotation cần khoảng chuyển tiếp có kiểm soát; resource server nhận khóa mới từ nguồn tin cậy, từ chối thuật toán và issuer ngoài cấu hình, không giữ khóa cũ vô hạn.
- **Chứng chỉ TLS/client:** theo dõi hạn, tự động gia hạn hợp lý, kiểm tra chain/identity khi thay CA, có quy trình xử lý khóa riêng bị lộ.
- **Mật khẩu/verifier:** nâng thông số thuật toán hoặc phương pháp hash theo lộ trình tương thích; xử lý tái mã hóa verifier an toàn khi đăng nhập hoặc yêu cầu thiết lập lại khi cần.
- **Di trú session/token:** xác định phiên cũ còn hoạt động được bao lâu, cách thu hồi, ảnh hưởng tới ứng dụng di động, người dùng nhiều thiết bị và tích hợp bên thứ ba.
- **Thêm SSO/passkey:** kiểm thử đường rút lui và recovery; phân biệt chuyển tài khoản cũ, tài khoản mới và trạng thái đăng nhập giữa nhiều hệ thống.

### 12.3. Ví dụ phản ứng khi nghi ngờ credential bị lộ

Một nhóm vận hành phát hiện nhiều lần đăng nhập sai vào tài khoản giảng viên, tiếp theo là đăng nhập thành công từ thiết bị lạ và yêu cầu thêm phương thức MFA.

Hành động có thể gồm: tăng mức kiểm tra rủi ro và hạn chế hành động nhạy cảm; yêu cầu xác thực lại bằng phương thức đã đăng ký trước đó; tạm thời thu hồi các phiên/refresh token đáng ngờ; xác minh thay đổi credential, kiểm tra log thay đổi quyền; thông báo người sở hữu và hỗ trợ khôi phục theo quy trình. Sau sự cố, rà soát vì sao kẻ tấn công có thể đi qua các ranh giới và bổ sung kiểm thử hồi quy.

Việc **vô hiệu hóa tài khoản** phải tác động tới những nơi danh tính được sử dụng: session store, refresh token, access token còn hạn (bằng biện pháp phù hợp), thiết bị đã tin cậy, khóa API và ủy quyền cho ứng dụng bên ngoài. Một cờ “disabled” trong bảng users sẽ không đủ nếu các API vẫn chấp nhận bearer token cũ mà không có chiến lược thu hồi.

## 13. Ví dụ xuyên suốt: nền tảng học tập

Giả sử một nền tảng có học viên, giảng viên và quản trị viên. Học viên được đăng nhập bằng passkey hoặc mật khẩu + MFA; giảng viên có thể kết nối IdP của trường; quản trị viên phải dùng phương thức chống phishing cho thao tác quản trị.

| Thời điểm | Tình huống | Quyết định bảo mật cần có |
| --- | --- | --- |
| Ngày đầu tiên | Học viên đăng ký email | Tạo internal user ID, xác minh email, chống đăng ký tự động |
| Sau đăng ký | Học viên thêm passkey trên laptop | Yêu cầu phiên đủ tin cậy; lưu public key/credential ID và ghi audit |
| Mỗi ngày | Học viên vào lớp học từ trình duyệt | Cấp session cookie an toàn, kiểm tra trạng thái phiên và quyền với từng lớp |
| Đổi thiết bị | Học viên dùng passkey đồng bộ hoặc credential dự phòng | Kiểm tra đúng RP/origin, tránh hạ mức bảo đảm qua đường dự phòng |
| Liên kết trường | Giảng viên kết nối SSO qua OIDC | Kiểm tra issuer + subject, state/PKCE, xác thực lại trước khi link |
| Nâng quyền | Giảng viên được giao vai trò quản trị | Kiểm tra authorization của người cấp quyền và yêu cầu step-up cho thao tác nhạy cảm |
| Mất điện thoại | Học viên yêu cầu khôi phục | Dùng kênh khôi phục đã đăng ký, token một lần, thông báo, quản lý phiên cũ |
| Rời trường | Tài khoản giảng viên bị vô hiệu hóa | Thu hồi quyền trong tenant, phiên, refresh token và các credential thích hợp |
| Phát hiện sự cố | Access token bị lộ trong log | Loại bỏ nguồn lộ, thu hồi theo kiến trúc token, luân chuyển khóa khi cần, điều tra phạm vi |

Hệ thống phải lưu riêng **bằng chứng xác thực** và **quyền nghiệp vụ**. Một học viên được xác thực thành công không thể truy cập endpoint chấm điểm chỉ bằng cách thay đường dẫn từ /students sang /teachers. Ngược lại, khi một giảng viên mất quyền ở lớp học, phiên của họ không mặc nhiên phải bị xóa, nhưng yêu cầu với lớp đó phải bị từ chối ngay theo chính sách quyền cập nhật.

### 13.1. Hình dung máy trạng thái tài khoản

~~~mermaid
stateDiagram-v2
    [*] --> Pending: Tạo danh tính
    Pending --> Active: Hoàn tất xác minh/đăng ký
    Active --> Recovery: Mất credential
    Recovery --> Active: Khôi phục hợp lệ
    Active --> Restricted: Rủi ro hoặc chính sách
    Restricted --> Active: Xác minh bổ sung/giải tỏa
    Active --> Disabled: Deprovision
    Restricted --> Disabled: Deprovision
    Recovery --> Disabled: Deprovision
    Disabled --> [*]: Kết thúc vòng đời theo chính sách
~~~

Đây là **mô hình minh họa**, không phải tập trạng thái bắt buộc. Trạng thái tài khoản và trạng thái phiên phải được quản lý riêng: một tài khoản Active có thể có nhiều session; Disabled phải khiến các phiên/token liên quan không còn sử dụng được theo cơ chế mà hệ thống đã chọn. “Restricted” có thể ngăn thao tác rủi ro nhưng vẫn cho phép một luồng khôi phục được kiểm soát.

## 14. Checklist thiết kế và kiểm thử theo vòng đời

Trước khi phát hành một luồng authentication, nhóm triển khai nên trả lời được những câu hỏi sau:

1. **Thiết kế:** chủ thể, tài sản, ranh giới tin cậy, issuer/audience và mức bảo đảm yêu cầu có được mô tả rõ không?
2. **Đăng ký:** email/số điện thoại có được hiểu đúng như thuộc tính đã xác minh tại một thời điểm, hay bị nhầm với danh tính vĩnh viễn?
3. **Credential:** password verifier có được lưu an toàn; passkey/WebAuthn có xác minh challenge, origin/RP; certificate có kiểm tra danh tính và thời hạn không?
4. **Đăng nhập:** có chống credential stuffing, enumeration và bypass MFA; response lỗi có làm lộ tài khoản tồn tại không?
5. **SSO:** redirect URI, state, PKCE, issuer, subject và audience có được kiểm tra, kể cả khi IdP trả kết quả bất thường không?
6. **Phiên:** session ID có đổi sau login/nâng quyền; cookie an toàn; có idle/absolute expiry; logout và logout all devices có hiệu lực đúng không?
7. **Token:** API từ chối ID token dùng sai mục đích, token sai audience/issuer, token hết hạn, token sửa chữ ký hoặc loại thuật toán không được phép không?
8. **Hành động nhạy cảm:** thêm credential, đổi kênh khôi phục và nâng quyền có đòi hỏi recent authentication phù hợp không?
9. **Recovery:** token reset có một lần/thời hạn/mục đích; kênh hỗ trợ có thể bị lợi dụng để vượt MFA không?
10. **Vận hành:** quy trình rotate khóa, xử lý credential lộ, deprovision, thu hồi phiên, kiểm soát log và diễn tập sự cố đã được kiểm tra chưa?

### Bài tập tình huống

Một ứng dụng cho phép: (a) đăng nhập bằng passkey; (b) khôi phục tài khoản bằng link email; (c) đổi email khôi phục từ bất kỳ phiên đang mở nào; (d) access token JWT có hạn một giờ và không có cơ chế thu hồi ngay khi tài khoản bị khóa.

**Yêu cầu:** vẽ sơ đồ ranh giới tin cậy, chỉ ra ít nhất ba con đường chiếm tài khoản hoặc tiếp tục truy cập trái phép, rồi đề xuất điều chỉnh theo thứ tự ưu tiên.

Gợi ý đối chiếu:

- Đường khôi phục qua email có đủ mạnh so với passkey không? Nếu email bị chiếm, attacker có thể thay authenticator?
- Kẻ chiếm một phiên cũ có thể đổi email, rồi bắt đầu khôi phục để sở hữu tài khoản lâu dài không? Cần reauthentication/step-up và thông báo ở điểm nào?
- Khi khóa tài khoản, API có tiếp tục nhận JWT cũ cho tới hết hạn không? Có thể giới hạn TTL, kiểm tra trạng thái hoặc cơ chế thu hồi theo mức rủi ro?
- Log và cảnh báo nào giúp phát hiện việc thêm credential lạ, đổi recovery channel và dùng token sau khi vô hiệu hóa?

## 15. Những nguyên tắc cần giữ khi hệ thống trưởng thành

Authentication không phải một hàm trả về true/false rồi kết thúc. Đó là tập quyết định bảo mật có thời hạn và ngữ cảnh, trải từ lúc gắn credential vào một danh tính đến khi thu hồi mọi khả năng sử dụng danh tính ấy.

**Nhớ ba điểm cốt lõi:**

- **Kiểm chứng tại ranh giới tin cậy:** không dùng dữ liệu do client tự khai để thay thế bằng chứng do thành phần có thẩm quyền xác minh.
- **Đường yếu nhất quyết định an toàn của tài khoản:** phishing, replay, liên kết danh tính hoặc khôi phục yếu có thể phá hỏng cả cơ chế đăng nhập mạnh.
- **Mỗi kết quả xác thực có vòng đời:** phiên, token, khóa, chứng chỉ và trạng thái tài khoản cần thời hạn, theo dõi, thay đổi và khả năng thu hồi phù hợp.

Khi các nguyên tắc này được đưa vào thiết kế, kiểm thử, triển khai, vận hành và ngừng dịch vụ, hệ thống mới có thể duy trì xác thực an toàn trong suốt vòng đời thực tế của nó.
