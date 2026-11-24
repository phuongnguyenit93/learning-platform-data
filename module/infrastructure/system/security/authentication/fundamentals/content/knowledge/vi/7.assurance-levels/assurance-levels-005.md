# Step-up assurance — Nâng mức bảo đảm xác thực khi cần

**Step-up assurance** là việc yêu cầu và xác minh **mức bảo đảm xác thực cao hơn** khi ngữ cảnh hoặc hành động đòi hỏi độ tin cậy lớn hơn mức của phiên hiện tại. Người dùng có thể đã đăng nhập thành công để xem hồ sơ, nhưng trước khi đổi phương thức khôi phục, xuất dữ liệu nhạy cảm hoặc phê duyệt thanh toán, hệ thống cần kiểm tra thêm bằng chứng xác thực phù hợp. Quyết định step-up phải xuất phát từ chính sách rủi ro và được thực thi ở phía máy chủ.

Trong phạm vi nền tảng authentication, step-up kết nối kiến thức về **credential, mật khẩu, MFA, passkey, chứng chỉ, phiên, token, liên kết danh tính và recovery**. Thiết kế đúng giúp nâng độ bảo đảm cho thao tác nhạy cảm, giảm tác động của phishing, replay, đánh cắp phiên và lạm dụng đăng nhập, đồng thời tránh làm người dùng phải xác thực mạnh ở mọi thao tác không cần thiết.

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **assurance**, **step-up authentication**, **reauthentication**, **MFA**, **authorization** và **risk-based authentication**.
2. Chỉ ra vì sao một phiên đã đăng nhập vẫn có thể không đủ độ tin cậy cho hành động nhạy cảm.
3. Xác định **chính sách yêu cầu mức bảo đảm** theo hành động, tài nguyên, độ nhạy cảm và thời điểm xác thực.
4. Vẽ luồng step-up với **trust boundary**, chứng cứ xác thực, giao dịch chờ và xác nhận cuối cùng.
5. Thực hiện kiểm tra phía máy chủ với dữ liệu phiên, thời gian xác thực và thuộc tính phương thức xác thực đã được kiểm chứng.
6. Hiểu vai trò của các claim **auth_time, acr, amr** và yêu cầu **max_age, prompt, acr_values** trong kịch bản OpenID Connect.
7. Thiết kế chống bypass, downgrade, replay, CSRF, session hijacking và lạm dụng khôi phục; đề xuất ca kiểm thử cụ thể.

## 2. Assurance là gì?

**Assurance** là mức độ tin cậy có căn cứ vào một khẳng định hay kết quả kiểm tra. Với xác thực, câu hỏi chính là: “Ta có căn cứ mạnh đến đâu để tin rằng chủ thể đang truy cập kiểm soát authenticator đã được ghi danh cho tài khoản?”. Không nên gộp các loại bảo đảm thành một con số duy nhất.

| Loại bảo đảm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Identity assurance** (thường gắn với IAL) | Danh tính số được gắn với người/thực thể ngoài đời đáng tin đến mức nào? | Đã xác minh thông tin định danh khi mở tài khoản theo quy trình phù hợp. |
| **Authentication assurance** (thường gắn với AAL) | Chủ thể vừa chứng minh quyền kiểm soát authenticator với mức bảo đảm nào? | Đăng nhập mật khẩu, TOTP hoặc WebAuthn có user verification. |
| **Federation assurance** (thường gắn với FAL) | Ứng dụng có thể tin tưởng kết quả liên kết danh tính nhận từ bên khác đến mức nào? | Liên kết OIDC/SAML với các cơ chế bảo vệ assertion/token phù hợp. |
| **Authorization** | Tài khoản được phép làm hành động gì? | Chỉ quản trị viên mới được thêm quản trị viên khác. |
| **Transaction assurance** | Người dùng có chủ ý chấp thuận đúng thao tác và đúng nội dung nhạy cảm không? | Xác nhận lại người nhận và số tiền của một giao dịch. |

Các nhãn IAL/AAL/FAL thường được dùng khi tham chiếu họ tiêu chuẩn **NIST SP 800-63**. Các mức và yêu cầu kỹ thuật chính xác phụ thuộc **phiên bản tiêu chuẩn và chính sách áp dụng**. Không tự suy rằng cứ có MFA là đạt mọi mức AAL, hoặc cứ dùng passkey là được cấp một mức cố định trong mọi môi trường.

**Điểm quan trọng:** step-up authentication có thể tăng mức tin cậy đối với việc **ai đang kiểm soát credential tại thời điểm kiểm tra**, nhưng không tự làm tăng chất lượng identity proofing, không thêm quyền cho tài khoản và không chứng minh người dùng đã đọc, hiểu hoặc đồng ý với chi tiết giao dịch. Các yêu cầu đó cần kiểm soát riêng.

## 3. Step-up khác những khái niệm gần nó thế nào?

| Khái niệm | Hành vi | Liên hệ với step-up |
| --- | --- | --- |
| Đăng nhập ban đầu | Xác thực để bắt đầu phiên. | Có thể dùng mức bảo đảm vừa đủ cho tác vụ thông thường. |
| **Reauthentication** | Yêu cầu chứng minh lại danh tính trong một phiên đang hoạt động. | Chỉ làm mới tính gần đây nếu vẫn dùng cùng mức yếu; không nhất thiết nâng assurance. |
| **Step-up authentication** | Xác minh thêm hoặc thay thế bằng phương thức đáp ứng mức yêu cầu cao hơn. | Là một trường hợp có mục đích của xác thực lại/nâng xác thực. |
| **MFA** | Kiểm tra các loại yếu tố độc lập hoặc dùng authenticator có khả năng đa yếu tố đáp ứng chính sách. | Một cách thường dùng để đạt yêu cầu step-up, nhưng cần xét khả năng chống phishing và mức bảo đảm thực tế. |
| **Risk-based/adaptive authentication** | Dùng tín hiệu rủi ro để quyết định cho qua, chặn hoặc yêu cầu xác thực mạnh hơn. | Là cơ chế **ra quyết định** khi nào step-up; tín hiệu IP/vị trí không tự trở thành yếu tố xác thực. |
| **Step-up authorization** | Sau khi được xác thực, hệ thống cho phép một hành động vốn đòi hỏi điều kiện cao hơn. | Chỉ xảy ra nếu chính sách **phân quyền và độ bảo đảm** đều đạt; step-up không tự cấp quyền. |

**Ví dụ:** Sinh viên đang xem bài học sau khi đăng nhập bằng mật khẩu. Khi muốn đổi email khôi phục, ứng dụng yêu cầu xác thực bằng passkey có user verification. Việc kiểm tra passkey có thể giúp đạt chính sách bảo đảm cao hơn. Ngược lại, yêu cầu nhập lại **chính mật khẩu** chỉ cải thiện bằng chứng về tính gần đây, không giải quyết được rủi ro mật khẩu đã bị phishing.

## 4. Tại sao cần step-up?

### 4.1. Phiên đang hoạt động không phải chứng minh vĩnh viễn

Cookie hoặc access token duy trì ngữ cảnh đăng nhập sau một lần xác thực. Theo thời gian, thiết bị có thể bị bỏ quên, phiên bị đánh cắp hoặc người dùng bị chuyển sang môi trường kém tin cậy. Một request có token hợp lệ **chưa đủ** để chấp thuận thao tác thay đổi quyền hoặc chuyển tài sản.

### 4.2. Giá trị tài sản thay đổi theo từng hành động

Cùng một tài khoản có thể đọc lịch học, tải tài liệu, đổi mật khẩu, xóa dữ liệu hoặc cấp quyền người khác. Mỗi hành động có tác động khác nhau nếu bị thực hiện trái phép. Step-up cho phép **mức bảo vệ tương xứng với mức rủi ro** mà không bắt mọi thao tác phải dùng cùng một luồng xác thực phức tạp.

### 4.3. Đánh giá rủi ro tại thời điểm yêu cầu

Ngay cả thao tác thông thường cũng có thể trở nên rủi ro nếu xuất hiện tín hiệu như đăng nhập mới từ thiết bị lạ, mẫu truy cập bất thường, nhiều lần thử thất bại, thay đổi credential gần đây hoặc hành vi nghi ngờ bị chiếm phiên. Các tín hiệu nên được đánh giá cẩn trọng, có giới hạn lỗi và quy trình hỗ trợ; tín hiệu rủi ro **không phải bằng chứng danh tính thứ hai**.

## 5. Chọn mục tiêu assurance cho từng hành động

Không có một bảng mức bắt buộc dùng cho mọi sản phẩm. Bảng dưới đây là **chính sách minh họa** cho một nền tảng học tập giả định tên **StudyHub**; sản phẩm thật cần định nghĩa yêu cầu theo mức độ thiệt hại, chuẩn áp dụng và khả năng của authenticator.

| Hành động | Mức rủi ro minh họa | Điều kiện đề xuất | Lý do |
| --- | --- | --- | --- |
| Xem khóa học đã đăng ký | Thấp | Phiên hợp lệ, phân quyền đúng | Tránh gây gián đoạn không cần thiết. |
| Xem thông tin hồ sơ thông thường | Thấp/vừa | Phiên hợp lệ; step-up nếu tín hiệu rủi ro cao | Rủi ro tăng theo loại dữ liệu và thiết bị. |
| Đổi mật khẩu hoặc thêm passkey | Cao | Xác thực gần đây với phương thức đủ mạnh; cảnh báo thay đổi | Ngăn đối thủ duy trì quyền kiểm soát tài khoản. |
| Đổi email/số điện thoại khôi phục | Cao | Step-up theo chính sách; kiểm chứng kênh mới, cân nhắc cảnh báo kênh cũ | Đường recovery có thể quyết định an toàn lâu dài. |
| Xuất dữ liệu cá nhân nhạy cảm | Cao | Step-up gần đây, hạn chế quyền và kiểm tra mục đích | Giảm thiệt hại nếu phiên bị chiếm. |
| Sửa điểm hoặc cấp quyền quản trị | Rất cao | Phương thức chống phishing phù hợp; xác thực gần đây; kiểm tra quyền độc lập | Tác động lớn, khả năng bị nhắm mục tiêu cao. |
| Xác nhận chuyển tiền hoặc thay người nhận | Rất cao | Xác thực mạnh và xác nhận đúng **chi tiết giao dịch** | Cần chống thay đổi nội dung sau khi người dùng chấp thuận. |

### 5.1. Chính sách là một tập điều kiện

Đừng chỉ lưu một biến kiểu “assurance = 2” rồi cho qua mọi thao tác. Yêu cầu thực tế có thể gồm:

~~~text
Policy for CHANGE_RECOVERY_EMAIL:
  accountRole in permittedRoles
  session is active and not revoked
  authenticatedSubject == targetAccount
  requiredAuthenticator = phishing_resistant_and_user_verified
  reauthenticationAge <= configuredFreshnessWindow
  enrolledCredentialTrusted = true
  riskDecision != block
  explicitConfirmationOfNewAddress = true
~~~

Tên chính sách và ngưỡng thời gian là **ví dụ thiết kế**, không phải tên claim hay thời hạn do chuẩn quy định. Phương thức xác thực, điều kiện sử dụng và tính gần đây phải được xác minh qua dữ liệu đáng tin cậy. Khi yêu cầu thay đổi theo rủi ro, máy chủ phải áp dụng chính sách mới lúc **thực thi**, không chỉ lúc mở màn hình.

### 5.2. Phân biệt ba câu hỏi “đủ mạnh”

1. **Đúng người/tài khoản?** Credential được gắn đúng account ID, subject và issuer, không chỉ trùng email.
2. **Đúng mức bảo đảm?** Authenticator/phương thức có đáp ứng điều kiện cụ thể: nhiều yếu tố, chống phishing, có xác minh người dùng, bảo vệ khóa?
3. **Đủ gần đây và đúng giao dịch?** Thời điểm xác thực còn phù hợp, chưa bị thu hồi và việc chấp thuận liên quan tới thao tác đang thực hiện?

Trả lời được một hoặc hai câu chưa chứng minh câu còn lại.

## 6. Thiết kế luồng step-up từ đầu đến cuối

StudyHub cho giảng viên sửa thông tin tài khoản bằng phiên đã đăng nhập. Khi đổi email khôi phục, máy chủ yêu cầu xác thực lại bằng phương thức mạnh hơn.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Trình duyệt
    participant A as Ứng dụng/API
    participant V as Verifier hoặc IdP
    participant S as Session/operation store
    U->>B: Yêu cầu đổi email khôi phục
    B->>A: Gửi yêu cầu với phiên và dữ liệu mới
    A->>A: Kiểm tra phiên, quyền, chính sách và rủi ro
    A->>S: Lưu pending operation gắn với user/phiên/chi tiết
    A-->>B: Yêu cầu step-up phù hợp
    B->>V: Thực hiện challenge xác thực mạnh
    V-->>A: Kết quả có thể kiểm chứng
    A->>A: Kiểm tra kết quả, mức đảm bảo, tính gần đây
    A->>S: Tải pending operation và kiểm tra còn hiệu lực
    A-->>B: Hiển thị chi tiết cần xác nhận cuối
    U->>B: Xác nhận thay đổi
    B->>A: Xác nhận operation ID và token chống CSRF
    A->>A: Kiểm tra lại quyền, policy, nội dung, freshness
    A->>S: Thực thi một lần, ghi audit và hoàn tất
    A-->>B: Trả kết quả
~~~

Sơ đồ phân biệt **xác thực thêm** với **thực thi hành động**. Trong thực tế, giao dịch có thể được hoàn tất ngay sau step-up nếu policy cho phép; với thao tác nhạy cảm, nên ràng buộc nội dung và yêu cầu người dùng xác nhận lại những trường quan trọng trước khi thực thi.

### 6.1. Những ranh giới tin cậy bắt buộc nhận diện

- **Browser/client ↔ application:** client có thể bị sửa, gửi request giả, replay hay thay ID đối tượng. Không tin client khai báo “đã step-up”.
- **Application ↔ verifier/authenticator:** chỉ chấp nhận bằng chứng đúng audience/origin, challenge, chữ ký, trạng thái credential và ngữ cảnh giao dịch.
- **Application ↔ session/operation store:** trạng thái pending và mức bảo đảm phải được bảo vệ, ràng buộc với đúng account, phiên và thao tác; hỗ trợ hết hạn và dùng một lần.
- **Application ↔ external IdP (nếu có):** chỉ tin issuer đã cấu hình; xác minh token theo giao thức, mapping claim và mức bảo đảm thực được trả về.
- **Application ↔ resource service:** dịch vụ thực thi cần kiểm tra quyền và chính sách, không chỉ tin màn hình phía trước đã hiển thị hộp thoại step-up.

### 6.2. Trạng thái cần biểu diễn

~~~mermaid
stateDiagram-v2
    [*] --> SessionValid: Đăng nhập thông thường
    SessionValid --> StepUpRequired: Yêu cầu thao tác nhạy cảm
    StepUpRequired --> Pending: Tạo giao dịch chờ
    Pending --> Verified: Challenge hợp lệ, đạt policy
    Pending --> Rejected: Sai / hết hạn / bị hủy
    Verified --> Committed: Recheck và xác nhận hợp lệ
    Verified --> Rejected: Thay đổi nội dung / quá hạn
    Committed --> SessionValid: Tiếp tục phiên
    Rejected --> SessionValid: Thao tác chưa thực thi
~~~

Trạng thái **Verified** không tự cấp thêm vai trò quản trị. Nó chỉ ghi nhận thông tin xác thực đã được kiểm chứng. Nếu người dùng yêu cầu thao tác mới, ứng dụng phải quyết định có được dùng lại thông tin step-up đó hay bắt đầu một giao dịch mới, dựa vào độ nhạy cảm, thời hạn và yêu cầu gắn với giao dịch.

## 7. Lưu mức bảo đảm và độ mới của xác thực ở đâu?

Thông tin đáng tin cậy có thể được quản lý tại **session store** hoặc xác minh từ token đã ký bởi một nguồn tin cậy. Mô hình session tham chiếu thường giúp thay đổi và thu hồi trạng thái tức thời đơn giản hơn.

Ví dụ dữ liệu **khái niệm** phía máy chủ:

~~~json
{
  "sessionId": "<opaque-random-id>",
  "subject": "account-42",
  "createdAt": "<timestamp>",
  "lastAuthenticationAt": "<timestamp>",
  "lastStrongAuthenticationAt": "<timestamp-or-null>",
  "verifiedMethods": ["password", "webauthn_uv"],
  "assurancePolicyId": "studyhub-sensitive-v1",
  "revoked": false
}
~~~

Đây là cấu trúc minh họa, **không phải chuẩn token**. Giá trị như `verifiedMethods` phải được tạo từ kết quả kiểm tra thật tại verifier; không bao giờ chép nguyên một trường do trình duyệt tự gửi. Tùy chính sách, cần lưu cả identifier của credential, mức bảo vệ và thời điểm xác thực để không nhầm một TOTP thông thường với authenticator chống phishing.

**Freshness** là thời gian từ lần xác thực phù hợp gần nhất tới thời điểm kiểm tra. Mỗi thao tác có thể yêu cầu cửa sổ freshness khác nhau; giới hạn này được cấu hình trong policy và kiểm tra bằng đồng hồ đáng tin cậy phía máy chủ. Đăng nhập gần đây bằng mật khẩu **không được coi là step-up mạnh** nếu hành động đòi hỏi WebAuthn có user verification.

Không nên coi một lần step-up thành công là lý do nâng toàn bộ phiên lên quyền cao vĩnh viễn. Có thể:

1. Lưu kết quả xác thực mạnh với **thời hạn ngắn** trong session và đánh giá lại ở từng API nhạy cảm.
2. Lưu **authorization grant gắn với một operation ID**, hết hạn và tiêu thụ một lần cho hành động đặc biệt nhạy cảm.
3. Kết hợp cả hai: freshness cho nhóm tác vụ vừa, operation binding và xác nhận nội dung cho tác vụ rất cao.

Khi đổi mật khẩu, xóa credential, phát hiện chiếm quyền hoặc logout, phải xem xét **thu hồi hiệu lực step-up và phiên**. Nếu access token tự chứa vẫn tồn tại sau thay đổi, hệ thống cần chiến lược TTL ngắn, introspection/revocation hoặc phát hành token theo ngữ cảnh phù hợp; chỉ xóa cookie phía client không thu hồi mọi token đang lưu hành.

## 8. Chọn phương thức thực sự đạt mục tiêu

| Phương thức step-up | Có thể giúp gì? | Giới hạn cần nhớ |
| --- | --- | --- |
| Nhập lại mật khẩu | Xác minh lại một bí mật, cải thiện freshness | Không làm tăng số yếu tố; vẫn bị phishing hoặc dùng mật khẩu rò rỉ. |
| Mật khẩu + TOTP | Bổ sung bằng chứng từ authenticator riêng khi ghi danh và kiểm tra đúng | Mã nhập tay có thể bị phishing hoặc chuyển tiếp thời gian thực. |
| SMS/email OTP | Kiểm tra kênh liên lạc được đăng ký | Có rủi ro SIM swap, tài khoản email bị chiếm, phishing; không mặc nhiên phù hợp mức cao. |
| Push phê duyệt | Tạo bước chấp thuận trên thiết bị đã đăng ký | Chống push fatigue, xác nhận nhầm; nếu cần, hiển thị chi tiết hoặc số đối chiếu. |
| WebAuthn/FIDO2 với UV | Chữ ký mật mã gắn với relying party/origin và xác minh người dùng tại authenticator; thường phù hợp chống phishing | Phải kiểm tra challenge, RP ID, origin, chữ ký, UV, credential policy, phiên và recovery. |
| Khóa/chứng chỉ client trên thiết bị được quản lý | Chứng minh kiểm soát private key; có thể phù hợp với máy hoặc môi trường doanh nghiệp | Chính sách thiết bị, vòng đời chứng chỉ và xác thực người dùng cuối là các vấn đề riêng. |

Một **passkey có xác minh người dùng** có thể thực hiện thao tác gồm nhiều bằng chứng trong một lần tương tác. Không nên suy số yếu tố từ số bước màn hình. Ngược lại, mật khẩu + CAPTCHA hoặc mật khẩu + kiểm tra IP vẫn không tự thành MFA.

**Phishing-resistant** và **multi-factor** là hai thuộc tính có liên quan nhưng khác nhau. Một phương thức có nhiều yếu tố vẫn có thể để mã bị lấy qua trang giả. Khi tài khoản quản trị hoặc hành động có hậu quả lớn, nên cân nhắc yêu cầu phương thức chống phishing, đồng thời bảo vệ phiên và đường khôi phục.

## 9. Step-up với OpenID Connect (OIDC)

Khi ứng dụng sử dụng đăng nhập liên kết, verifier có thể nằm ở **OpenID Provider (OP/IdP)**. Ứng dụng cần yêu cầu, nhận và **xác minh** thông tin mức bảo đảm từ IdP; một chuyển hướng tới trang đăng nhập **không tự chứng minh** đã đạt mức yêu cầu.

Các khái niệm quan trọng:

| Tham số/claim | Ý nghĩa thực hành | Điều không nên suy diễn |
| --- | --- | --- |
| `max_age` (request) | Yêu cầu giới hạn tuổi của xác thực tại OP, thúc đẩy xác thực lại khi quá hạn. | Chỉ yêu cầu freshness, không tự chọn authenticator mạnh hơn. |
| `prompt=login` (request) | Yêu cầu OP hiển thị tương tác đăng nhập lại. | Không tự bảo đảm MFA hoặc AAL cao hơn. |
| `acr_values` (request) | Nêu các lớp/ngữ cảnh xác thực mong muốn theo chính sách giữa các bên. | Không có ý nghĩa chung giữa mọi IdP nếu chưa thống nhất giá trị và quy tắc. |
| `auth_time` (ID token claim) | Thời điểm người dùng được xác thực tại OP. | Không chứng minh phương thức đủ mạnh nếu thiếu các bằng chứng/chính sách khác. |
| `acr` (ID token claim) | Lớp ngữ cảnh xác thực đã được IdP khẳng định. | Chỉ hữu ích khi RP hiểu và tin được mapping `acr` của đúng IdP. |
| `amr` (ID token claim) | Các phương thức được dùng trong xác thực. | Danh sách phương thức không thay thế việc xác minh ngữ nghĩa chính sách và mức đảm bảo. |

Ví dụ minh họa **yêu cầu** khi StudyHub chuyển tới OP:

~~~text
GET /authorize?
  response_type=code
  &client_id=<registered-client>
  &redirect_uri=<registered-redirect-uri>
  &scope=openid
  &state=<unpredictable-state>
  &nonce=<unpredictable-nonce>
  &code_challenge=<pkce-challenge>
  &code_challenge_method=S256
  &max_age=<policy-freshness-in-seconds>
  &acr_values=<agreed-strong-context>
~~~

Đây là **mẫu khái niệm**; tên và giá trị thật phải được URL-encode, cấu hình theo OP và thư viện giao thức đúng chuẩn. Không tự gửi các placeholder trên vào production.

Sau callback, RP cần:

1. Kiểm tra `state`, redirect URI đã đăng ký, ràng buộc PKCE và thực hiện code exchange an toàn.
2. Xác minh ID token theo OIDC: chữ ký/khóa tin cậy, `iss`, `aud`, `exp`, `iat` và các điều kiện áp dụng như `nonce`, `azp`; không dùng access token làm bằng chứng đăng nhập thay ID token.
3. Kiểm tra `sub` gắn đúng account đã bắt đầu step-up, tránh **account switching**; không dựa vào email trùng để tự liên kết.
4. Kiểm tra `auth_time` theo freshness policy và `acr`/`amr` theo mapping đã thống nhất. Nếu OP không cung cấp hoặc không đạt thông tin bắt buộc, **không cấp quyền thực hiện**; yêu cầu phương thức khác hoặc từ chối rõ ràng.
5. Ràng buộc kết quả step-up với **đúng phiên và giao dịch chờ** trước khi thực thi hành động.

Lưu ý: mức `acr_values` yêu cầu có thể là **gợi ý** hoặc không được OP đáp ứng, tùy đặc tả, cấu hình và cách triển khai. RP phải dựa trên **kết quả đã kiểm chứng**, không dựa trên giá trị mình từng gửi. Nếu cần yêu cầu claim thiết yếu hoặc chính sách đặc thù, phải thỏa thuận và kiểm thử với IdP.

## 10. Pseudocode: kiểm tra step-up tại máy chủ

Ví dụ sau minh họa một API đổi email khôi phục. Những hàm như `policyFor` và `verifyAuthenticator` đại diện cho các thành phần đã được triển khai an toàn và kiểm thử; đây không phải mã sẵn dùng cho production.

~~~text
POST /accounts/me/recovery-email/change
  session = requireActiveSession(request)
  assertAuthorized(session.subject, "change_recovery_email")
  validateRequestAndCsrf(request)
  policy = policyFor("change_recovery_email", session, riskSignals)

  if not satisfiesAssurance(session, policy):
      op = createPendingOperation(
          actor=session.subject,
          sessionId=session.id,
          action="change_recovery_email",
          targetAccount=session.subject,
          newAddress=request.newAddress,
          expiresAt=now+shortDuration,
          nonce=randomHighEntropyValue,
          status="pending"
      )
      return requireStepUp(op.id, policy.requiredAuthenticator)

  // Nếu đã đủ điều kiện, vẫn kiểm tra yêu cầu, quyền và chính sách tại đây.
  continueWithValidatedAction(request, session)

POST /step-up/complete
  session = requireActiveSession(request)
  op = findPendingOperation(request.operationId)
  assert op exists and notExpired and status=="pending"
  assert op.actor==session.subject and op.sessionId==session.id
  verified = verifyFreshAuthenticatorResponse(request.proof, op)
  assert verified and meetsPolicy(verified, policyFor(op.action))
  recordVerifiedAssurance(session, verified)
  markOperationVerified(op)
  return displayDetailsForFinalConfirmation(op)

POST /step-up/confirm
  session = requireActiveSession(request)
  op = lockPendingOperation(request.operationId)
  assert op.actor==session.subject and op.sessionId==session.id
  assert op.status=="verified" and notExpired
  validateRequestAndCsrf(request)
  assertAuthorized(session.subject, op.action, op.targetAccount)
  assert meetsCurrentPolicy(session, op, currentRiskSignals)
  assert confirmedDetailsMatchImmutableOperation(request, op)
  executeAtomicallyAndMarkConsumed(op)
  auditSensitiveChange(op)
~~~

Các bất biến cần giữ:

- **Giao dịch chờ** được lưu phía server và không cho client sửa trực tiếp account ID, loại hành động hoặc nội dung đã chấp thuận. Có thể lưu dữ liệu nhạy cảm dạng mã hóa/tối thiểu hóa theo yêu cầu.
- **Challenge/chứng cứ** gắn với request xác thực, dùng một lần hoặc có chống replay, hết hạn, không được tái sử dụng giữa tài khoản hoặc phiên khác.
- **Thao tác cuối cùng** phải kiểm tra lại authorization và policy; khóa/transaction hoặc cơ chế tương đương giúp chặn thực thi lặp khi hai request đồng thời.
- **Nội dung giao dịch** không được thay ngầm sau step-up. Với mức rủi ro rất cao, người dùng cần xác nhận đúng người nhận/số tiền/đối tượng; xác thực WebAuthn chung không tự chứng minh đồng ý các chi tiết nếu ứng dụng không ràng buộc chúng vào luồng phê duyệt.
- **Audit log** chỉ lưu metadata cần thiết, kết quả, thời gian, credential identifier theo chính sách; không ghi mật khẩu, secret, token dùng một lần hoặc giá trị nhạy cảm không cần thiết.

## 11. Phòng chống bypass và tấn công đặc thù

| Tấn công/lỗi thiết kế | Ví dụ | Kiểm soát |
| --- | --- | --- |
| **Chỉ kiểm tra ở giao diện** | Ẩn nút “Đổi email” sau màn MFA, nhưng API chấp nhận request trực tiếp. | Bắt buộc kiểm tra mức bảo đảm tại API thực thi và mọi lối vào tương đương. |
| **Tin cờ do client gửi** | Client gửi `stepUpPassed: true`. | Dùng phiên/token đã xác minh từ server/IdP đáng tin cậy. |
| **Downgrade phương thức** | Luồng yêu cầu passkey mạnh nhưng cho fallback mật khẩu đơn lẻ. | Ràng buộc policy với danh sách phương thức chấp nhận; từ chối fallback yếu hoặc chuyển qua recovery bảo đảm tương xứng. |
| **Step-up quá hạn** | Xác thực mạnh hôm trước vẫn dùng cho đổi credential hôm nay. | Kiểm tra `auth_time`/thời điểm xác thực mạnh theo freshness của từng tác vụ. |
| **Phishing thời gian thực** | OTP bị nhập vào trang giả và chuyển tiếp. | Ưu tiên phương thức chống phishing như WebAuthn khi rủi ro cao. |
| **Replay challenge/assertion** | Dùng lại chứng cứ xác thực đã thành công. | Challenge mới, khó đoán, kiểm tra đúng ngữ cảnh; tiêu thụ hoặc ngăn dùng lại. |
| **Thay đổi giao dịch sau xác thực** | Step-up cho tài khoản A rồi đổi request để sửa tài khoản B. | Bind operation với actor, target, phiên, nội dung, mục đích; recheck lúc commit. |
| **TOCTOU / race condition** | Hai request cùng dùng một pending operation hợp lệ. | Trạng thái một lần, atomic compare-and-set/transaction. |
| **Chiếm phiên** | Kẻ tấn công có cookie và lợi dụng step-up đã làm trước đó. | Giới hạn freshness/scope; bảo vệ session, chống XSS/CSRF, step-up theo giao dịch nhạy cảm. |
| **IdP account switching** | Callback step-up xác thực tài khoản bên ngoài khác người đang đăng nhập. | Kiểm tra `issuer + subject`, session và liên kết danh tính. |
| **Fallback/recovery yếu** | Hỗ trợ tắt MFA sau một cuộc gọi không xác minh đủ. | Chính sách recovery tương xứng, cảnh báo và kiểm toán thao tác hỗ trợ. |
| **Phát lộ dữ liệu qua log/URL** | Token/operation secret bị ghi vào analytics hoặc referrer. | Sử dụng HTTPS, giảm dữ liệu trên URL, mask log, hạn chế TTL, chính sách referrer phù hợp. |

**Bảo vệ session vẫn thiết yếu:** cookie nên có Secure, HttpOnly và SameSite phù hợp; phòng CSRF bằng cơ chế riêng khi cần; chống XSS; xoay session ID khi đăng nhập hoặc thay đổi mức đặc quyền phù hợp. Step-up không thay thế phân quyền, xác thực ở API, kiểm tra input và quản lý token.

## 12. Độ an toàn của recovery quyết định hiệu quả step-up

Giả sử quản trị viên dùng passkey chống phishing để duyệt thay đổi quyền, nhưng chỉ cần một email reset là có thể xóa passkey và thêm authenticator mới. Đối thủ chiếm email có thể vòng qua biện pháp step-up. Vì thế:

1. **Ghi danh authenticator mới** cần xác minh bằng phương thức hiện hữu đủ mạnh hoặc quy trình recovery riêng có độ bảo đảm tương xứng.
2. **Đổi kênh khôi phục** là hành động nhạy cảm; cân nhắc xác minh kênh mới, thông báo kênh cũ, trì hoãn thay đổi và giới hạn các thao tác rủi ro cao sau recovery.
3. **Mất tất cả thiết bị** không nên buộc người dùng phải dùng lối tắt không được bảo vệ; cần quy trình chứng minh thay thế phù hợp, hỗ trợ có kiểm soát và nhật ký để điều tra.
4. **Phục hồi thành công** có thể đòi hỏi thu hồi session cũ, tái ghi danh yếu tố và đánh giá lại các pending operation.
5. **Không “nâng bảo đảm” bằng chính recovery vừa bị nghi ngờ** nếu nó không đáp ứng điều kiện của hành động mục tiêu.

Đường khôi phục thường là chỗ kẻ tấn công chọn khi đường đăng nhập chính đã đủ mạnh. Mô hình đe dọa phải bao gồm cả help desk, thiết bị dự phòng và kênh thông báo.

## 13. Thiết kế trải nghiệm và vận hành

Step-up thất bại nhiều khi do **tính khả dụng** hoặc chính sách không rõ ràng hơn là thuật toán mật mã. Những quyết định dưới đây giúp cân bằng:

- **Giải thích mục đích xác thực lại:** “Xác nhận bằng passkey để thay đổi email khôi phục”, tránh yêu cầu MFA mơ hồ.
- **Giữ ngữ cảnh:** lưu biểu mẫu hoặc giao dịch chờ phía server; sau khi xác thực thành công, người dùng quay về đúng tác vụ, không phải nhập lại dữ liệu.
- **Giảm lặp lại vô lý:** áp dụng cửa sổ freshness hợp lý cho nhóm thao tác vừa, nhưng dùng xác nhận gắn giao dịch với tác vụ có hậu quả cao.
- **Hỗ trợ thiết bị và khả năng tiếp cận:** có phương thức đã ghi danh dự phòng, quy trình hỗ trợ và hướng dẫn khi chuyển thiết bị; không hạ chính sách âm thầm chỉ vì một thiết bị không hỗ trợ.
- **Có lựa chọn khi thất bại:** thông báo thân thiện, giới hạn thử, cung cấp đường recovery đã đánh giá bảo mật; tránh làm lộ việc account hoặc credential có tồn tại.
- **Đo hiệu quả thực tế:** tỷ lệ hoàn tất step-up, tỷ lệ bỏ dở, nguyên nhân lỗi, phân bố phương thức, false positive, yêu cầu hỗ trợ, hành vi bất thường và thời gian khôi phục.

Nên ghi sự kiện khi **yêu cầu step-up, xác minh thành công/thất bại, sử dụng hoặc hết hạn pending operation, thay đổi credential và recovery**, nhưng tránh đưa dữ liệu nhạy cảm vào log. Dùng cảnh báo theo mức rủi ro, có tính đến lỗi mạng, thiết bị mất kết nối và tình huống nhiều tab.

## 14. Bài thực hành: step-up cho StudyHub

**Bối cảnh:** StudyHub phục vụ sinh viên, giảng viên và quản trị viên. Đăng nhập ban đầu cho phép xem nội dung học. Giảng viên sửa điểm, quản trị viên thêm người vào nhóm admin, mỗi người dùng có thể thay đổi kênh khôi phục của chính mình.

### 14.1. Bảng chính sách do người học hoàn thiện

| Hành động | Quyền yêu cầu | Mức bảo đảm mong muốn | Freshness | Ràng buộc giao dịch |
| --- | --- | --- | --- | --- |
| Sinh viên xem bài học | Chủ tài khoản hoặc người được cấp quyền | Phiên thông thường | Theo chính sách phiên | Resource ID và phân quyền mỗi request. |
| Giảng viên sửa điểm | Giảng viên được phân công cho lớp | Xác thực mạnh hơn phiên chỉ dùng mật khẩu | Mới theo ngưỡng rủi ro | Đúng học viên, môn học và điểm. |
| Người dùng đổi email khôi phục | Chủ tài khoản | Phương thức đủ mạnh, ưu tiên chống phishing | Gần thời điểm thay đổi | Địa chỉ mới đã xác nhận; operation một lần. |
| Quản trị viên thêm admin | Quản trị viên có quyền cấp quyền | Phương thức chống phishing theo chính sách cao | Rất gần thời điểm thao tác | Tài khoản đích, vai trò cấp, xác nhận cuối. |
| Tạo phiên mới sau recovery | Chủ tài khoản đã hoàn thành recovery phù hợp | Dựa trên mức bảo đảm recovery và authenticator còn lại | Tại thời điểm recovery | Không tự động cấp quyền nhạy cảm nếu chưa đủ assurance. |

Nhiệm vụ là chọn **một ngưỡng thời gian rõ ràng cho từng hành động**, giải thích vì sao chọn ngưỡng đó và lập kế hoạch xử lý khi thiết bị mạnh không có mặt. Các ngưỡng do nhóm thiết kế quyết định theo rủi ro, không sao chép máy móc từ ví dụ.

### 14.2. Bộ ca kiểm thử chấp nhận

| Ca kiểm thử | Kết quả phải có |
| --- | --- |
| Người dùng có phiên hợp lệ nhưng assurance chưa đủ gọi thẳng API sửa điểm | API yêu cầu step-up hoặc từ chối; không thay đổi điểm. |
| Client tự thêm `stepUpPassed=true` | Server bỏ qua cờ giả; vẫn kiểm tra bằng chứng tin cậy. |
| Xác thực lại chỉ bằng mật khẩu trong luồng yêu cầu WebAuthn UV | Không được chấp thuận nếu policy yêu cầu UV/phương thức chống phishing. |
| IdP trả `acr` thấp hơn mức ứng dụng yêu cầu | RP không coi step-up đã đạt. |
| IdP trả kết quả cho `sub` khác account hiện tại | RP từ chối, không chuyển tài khoản âm thầm. |
| `auth_time` quá cũ dù token còn hiệu lực | Hành động nhạy cảm bị từ chối hoặc yêu cầu xác thực lại. |
| Challenge hoặc magic link dùng lại | Không được chấp nhận lần hai. |
| Operation ID được dùng ở phiên/tài khoản khác | Từ chối vì sai ràng buộc. |
| Sau step-up, client sửa email đích trước khi commit | Dữ liệu thay đổi bị từ chối hoặc yêu cầu xác nhận giao dịch mới. |
| Hai request commit đồng thời cùng operation | Tối đa một lần thực thi thành công. |
| Người dùng mất kết nối rồi thử lại | Thao tác không thực thi hai lần; có phản hồi trạng thái rõ ràng. |
| Session bị thu hồi hoặc account mất quyền trước commit | Không thực thi dù challenge trước đó đã thành công. |
| Đổi authenticator hoặc hoàn tất recovery | Thao tác nhạy cảm cũ được đánh giá lại theo chính sách và trạng thái phiên mới. |
| Phiên sinh viên có xác thực mạnh nhất gọi API admin | API vẫn từ chối vì thiếu **quyền**. |

### 14.3. Những câu hỏi kiểm tra thiết kế

1. Nếu kẻ tấn công lấy được **cookie phiên nhưng không có passkey**, thao tác nào bị chặn?
2. Nếu lấy được **mật khẩu và mã TOTP qua trang giả**, bước nào vẫn có nguy cơ bị qua mặt?
3. Nếu IdP đưa `acr` khác giá trị yêu cầu, ứng dụng dựa vào bằng chứng nào để quyết định?
4. Nếu người dùng xác thực thành công cho **đổi email A**, liệu client có thể thay thành **email B** hay không?
5. Nếu một lần step-up được dùng cho **hai request đồng thời**, làm sao bảo đảm không thực thi hai lần?
6. Nếu recovery qua email yếu hơn step-up bằng passkey, điều gì xảy ra khi mất thiết bị?
7. Cần theo dõi chỉ số gì để giảm false positive mà vẫn duy trì policy?

**Tiêu chí hoàn thành:** Người học có thể trình bày chính sách mức bảo đảm, vẽ chính xác trust boundary, chỉ ra dữ liệu đáng tin, giải thích lúc cần xác thực lại và viết ca kiểm thử chứng minh việc **chặn hành động chưa đủ assurance**. Họ cũng phải phân biệt được việc nâng assurance với cấp quyền và chứng minh chủ ý chấp thuận giao dịch.

## 15. Kiến thức nên đọc tiếp

- **NIST SP 800-63**: khái niệm identity, authentication và federation assurance; kiểm tra phiên bản áp dụng trước khi diễn giải yêu cầu AAL/IAL/FAL cụ thể.
- **OpenID Connect Core**: các yêu cầu và claim như `max_age`, `auth_time`, `acr`, `amr`, `nonce`; cách xác minh ID token và ngữ cảnh liên kết.
- **W3C WebAuthn và FIDO2**: challenge, origin/RP ID, user presence/user verification và xác thực chống phishing.
- **OWASP Authentication, Session Management, Forgot Password Cheat Sheets và ASVS**: kiểm soát xác thực lại, quản lý phiên, credential lifecycle và cách chuyển thiết kế thành yêu cầu kiểm thử.

Khi triển khai thật, chọn policy theo tài sản và rủi ro của chính hệ thống, xác minh cách IdP/authenticator báo mức bảo đảm, và kiểm thử cả **luồng thành công, thất bại, tấn công phát lại, phiên bị chiếm, recovery và quyền truy cập**.
