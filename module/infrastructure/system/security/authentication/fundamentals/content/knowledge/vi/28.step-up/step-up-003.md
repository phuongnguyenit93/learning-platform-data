# Re-authentication

## 1. Re-authentication là gì?

**Re-authentication (xác thực lại)** là việc yêu cầu người dùng chứng minh lại quyền kiểm soát credential sau khi một phiên đăng nhập đã được tạo. Hệ thống thực hiện bước này khi cần bằng chứng xác thực mới hơn, chẳng hạn trước khi đổi thông tin bảo mật, xem dữ liệu nhạy cảm, thêm passkey, thay đổi phương thức recovery hoặc thực hiện thao tác có tác động lớn.

Khi đăng nhập ban đầu, ứng dụng thường tạo session để người dùng không phải nhập credential ở mọi request. Session có thể tồn tại trong nhiều phút hoặc nhiều giờ. Trong thời gian đó, thiết bị có thể bị bỏ quên, session cookie có thể bị đánh cắp hoặc người đang sử dụng máy có thể không còn là chủ tài khoản. Re-authentication tạo một điểm kiểm tra mới trước khi tiếp tục thao tác nhạy cảm.

Ví dụ: nhân viên đã đăng nhập cổng doanh nghiệp bằng passkey từ đầu buổi sáng. Buổi chiều, họ muốn thay đổi tài khoản nhận lương. Ứng dụng yêu cầu xác thực lại bằng passkey hoặc phương thức step-up đã được tổ chức phê duyệt, rồi mới cho phép thay đổi.

Re-authentication không nhất thiết là đăng xuất rồi đăng nhập lại toàn bộ ứng dụng. Nó có thể là một challenge mới trong session hiện tại, một lần xác thực mới tại Identity Provider (IdP) hoặc một bước xác minh bổ sung. Điều quan trọng là server phải xác minh được bằng chứng mới, gắn nó với đúng session và thao tác, rồi áp dụng chính sách quyền tương ứng.

## 2. Re-authentication, initial authentication và step-up khác nhau thế nào?

Các thuật ngữ này có quan hệ nhưng không đồng nghĩa:

| Khái niệm | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Initial authentication** | Tạo bằng chứng đăng nhập để bắt đầu session. | Đăng nhập bằng passkey. |
| **Re-authentication** | Xác minh lại người dùng sau một khoảng thời gian hoặc trước một hành động. | Yêu cầu passkey assertion mới trước khi đổi email recovery. |
| **Step-up authentication** | Nâng mức bảo đảm của lần xác thực/session để đáp ứng policy cao hơn. | Session ban đầu dùng password được yêu cầu thêm security key. |
| **Authorization** | Quyết định chủ thể có được phép thực hiện hành động trên tài nguyên cụ thể không. | Kiểm tra người dùng có quyền sửa tài khoản nhận lương hay không. |
| **Session renewal** | Gia hạn hoặc cấp lại session/token theo cơ chế hệ thống. | Refresh access token. |

Re-authentication có thể dùng cùng phương thức đã dùng lúc đăng nhập hoặc dùng một phương thức mạnh hơn. Nếu chỉ cần chứng minh người dùng vẫn đang kiểm soát credential, xác thực lại bằng cùng passkey có thể đủ. Nếu hành động đòi hỏi mức bảo đảm cao hơn, policy cần step-up bằng phương thức hoặc ngữ cảnh xác thực mạnh hơn.

**Refresh token không tự chứng minh người dùng vừa xác thực lại.** Việc cấp access token mới từ refresh token thường không có tương tác người dùng và không làm mới thời điểm xác thực ban đầu. Tương tự, mở lại một trang, nhập lại mật khẩu chỉ ở giao diện hoặc bấm nút xác nhận không phải bằng chứng re-authentication nếu server không xác minh một challenge mới.

## 3. Vì sao cần xác thực lại?

Session giúp trải nghiệm thuận tiện nhưng tạo ra một khoảng thời gian mà ứng dụng dựa vào bằng chứng xác thực đã xảy ra trong quá khứ. Re-authentication thu hẹp khoảng thời gian đó cho những hành động có rủi ro cao.

Các mục tiêu chính:

- **Giảm rủi ro session bị chiếm:** người lấy được session cookie không nhất thiết có credential cần để xác thực lại.
- **Kiểm tra sự hiện diện của chủ thể:** yêu cầu một tương tác mới trước hành động nhạy cảm.
- **Nâng mức bảo đảm:** yêu cầu phương thức chống phishing hoặc xác minh người dùng cục bộ khi policy cần.
- **Giảm tác động của thiết bị dùng chung:** session còn mở không đồng nghĩa người đang ngồi trước thiết bị là chủ tài khoản.
- **Tạo bằng chứng gần thời điểm giao dịch:** hỗ trợ kiểm soát thao tác quan trọng, dù re-authentication đơn thuần không chứng minh người dùng đã hiểu hoặc đồng ý với mọi chi tiết giao dịch.
- **Tuân thủ chính sách:** đáp ứng yêu cầu về thời gian xác thực tối đa, phân tách nhiệm vụ hoặc kiểm soát truy cập đặc quyền.

Re-authentication không loại bỏ XSS, malware hoặc session theft. Nếu attacker điều khiển trình duyệt đang có session, họ có thể gây ra nhiều hành động thay người dùng. Nếu attacker cũng kiểm soát credential hoặc kênh recovery, bước xác thực lại có thể bị vượt qua. Vì vậy cần kết hợp session security, authorization, chống phishing, giám sát và thu hồi.

## 4. Khi nào nên yêu cầu re-authentication?

Policy nên dựa trên mức độ nhạy cảm và hậu quả của hành động, không chỉ dựa trên một bộ đếm thời gian chung.

| Hành động | Chính sách có thể áp dụng |
| --- | --- |
| Xem trang thông tin thông thường | Dùng session hiện tại trong thời hạn bình thường. |
| Xem thông tin cá nhân hoặc tài chính nhạy cảm | Yêu cầu xác thực gần đây hoặc step-up theo mức rủi ro. |
| Đổi mật khẩu, email hoặc số điện thoại recovery | Re-authentication bằng factor độc lập, sau đó thông báo thay đổi. |
| Thêm hoặc xóa passkey/security key | Re-authentication mạnh; đánh giá việc xóa factor cuối cùng. |
| Tạo API key hoặc certificate mới | Step-up, giới hạn scope và audit. |
| Thay đổi quyền quản trị hoặc phân quyền người dùng | Step-up và có thể yêu cầu phê duyệt độc lập. |
| Chuyển tiền hoặc xác nhận giao dịch giá trị cao | Re-authentication/step-up cộng xác nhận giao dịch theo policy. |
| Thu hồi mọi session hoặc thay đổi recovery | Xác thực mạnh, có thể thêm kiểm soát ngoài băng. |

Các trigger khác có thể gồm session đã quá tuổi, thiết bị thay đổi đáng kể, dấu hiệu đăng nhập bất thường, hành động từ vị trí/risk context khác thường hoặc phát hiện credential/session có nguy cơ bị lộ.

Không nên yêu cầu xác thực lại cho mọi thao tác nhỏ. Nếu người dùng phải liên tục xác minh, họ có thể tìm cách né quy trình, chấp nhận prompt một cách máy móc hoặc chọn phương thức dự phòng yếu hơn. Mỗi trigger cần có lý do và mức bảo đảm cụ thể.

## 5. Freshness và assurance là hai chiều khác nhau

Một policy re-authentication thường cần đánh giá ít nhất hai câu hỏi:

1. **Freshness:** bằng chứng xác thực gần đây đến mức nào?
2. **Assurance:** phương thức và ngữ cảnh xác thực có đáp ứng mức bảo đảm cần thiết không?

Một người có thể vừa xác thực bằng mật khẩu cách đây 30 giây. Bằng chứng đó mới, nhưng có thể không đủ mạnh cho hành động đòi hỏi chống phishing. Ngược lại, một passkey mạnh được dùng từ hôm trước có thể có assurance tốt nhưng không còn đủ mới cho thao tác đặc quyền.

| Tình huống | Freshness | Assurance | Kết quả có thể |
| --- | --- | --- | --- |
| Password vừa nhập | Cao | Phụ thuộc mật khẩu và policy; dễ bị phishing hơn passkey. | Đủ cho một số thao tác, chưa chắc đủ cho thao tác đặc quyền. |
| Passkey với user verification vừa hoàn tất | Cao | Có thể cao và chống phishing theo WebAuthn. | Phù hợp nhiều hành động nhạy cảm nếu policy chấp nhận. |
| Session được refresh bằng refresh token | Không làm mới xác thực người dùng | Không tăng assurance | Không đáp ứng yêu cầu re-authentication chỉ bằng việc refresh. |
| Passkey đã dùng từ lâu | Thấp theo giới hạn thời gian | Phương thức vẫn có thể mạnh | Có thể cần assertion mới. |
| OTP vừa nhập | Cao | Phụ thuộc loại OTP và rủi ro phishing/relay | Có thể chưa đủ cho hành động cần phishing resistance. |

Policy nên biểu diễn riêng thời gian xác thực tối đa và mức assurance yêu cầu. Không dùng một trường `last_activity_at` để đại diện cho cả hai.

## 6. Thiết kế freshness policy

Một cách phổ biến là đặt **maximum authentication age**: thời gian tối đa kể từ lần xác thực thực sự gần nhất mà một hành động được phép tiếp tục.

Ví dụ minh họa:

~~~text
Đọc thông tin hồ sơ:
  max_auth_age = 8 giờ

Đổi phương thức recovery:
  max_auth_age = 5 phút
  required_assurance = phishing-resistant

Thay đổi quyền quản trị:
  max_auth_age = 2 phút
  required_assurance = hardware-backed hoặc policy tương đương
~~~

Các con số chỉ là ví dụ, không phải ngưỡng bắt buộc. Tổ chức cần chọn theo rủi ro, độ nhạy cảm, loại thiết bị và tiêu chuẩn áp dụng.

Server nên lưu ít nhất:

- `auth_time`: thời điểm xác thực người dùng thực sự được thực hiện và xác minh.
- `last_reauth_at`: thời điểm server chấp nhận một lần re-authentication cho session.
- `auth_method` hoặc `amr`: phương thức đã được sử dụng nếu có dữ liệu đáng tin.
- `acr`/assurance level: ngữ cảnh hoặc mức bảo đảm do issuer xác nhận, nếu có.
- `session_created_at` và `last_activity_at`: thời điểm tạo session và hoạt động gần nhất.
- `credential_id` hoặc authentication event ID nếu cần truy vết factor đã dùng.

Thời điểm phải do server xác minh hoặc lấy từ token/assertion đã được xác minh. Không tin `auth_time`, `last_reauth_at` hoặc assurance level do browser gửi trong request body.

## 7. Re-authentication qua OpenID Connect

Với ứng dụng dùng OpenID Connect (OIDC), Relying Party (RP) có thể yêu cầu OpenID Provider (OP) xác thực người dùng lại thay vì chỉ sử dụng session SSO hiện có.

### 7.1. Tham số `max_age`

OIDC định nghĩa tham số `max_age` trong Authentication Request. Giá trị là số giây tối đa kể từ lần xác thực chủ động của người dùng. Nếu thời gian kể từ lần xác thực đó vượt quá `max_age`, OP phải chủ động xác thực lại người dùng. Khi RP yêu cầu `max_age`, ID Token phải có claim `auth_time` để RP đánh giá thời điểm xác thực.

Ví dụ yêu cầu xác thực không cũ hơn 5 phút:

~~~http
GET /authorize?
  response_type=code&
  client_id=payroll-portal&
  redirect_uri=https%3A%2F%2Fpayroll.example.test%2Fcallback&
  scope=openid%20profile&
  max_age=300&
  state=random-state&
  nonce=random-nonce&
  code_challenge=BASE64URL_CHALLENGE&
  code_challenge_method=S256
~~~

`max_age=0` tương đương yêu cầu xác thực ngay theo quy tắc OIDC. RP vẫn phải xác minh ID Token và kiểm tra `auth_time`; không chỉ tin việc browser đã được chuyển qua trang đăng nhập.

### 7.2. Tham số `prompt=login`

`prompt=login` yêu cầu OP hiển thị luồng đăng nhập và chủ động xác thực người dùng, ngay cả khi OP có thể đang giữ session SSO. Đây là tín hiệu yêu cầu tương tác xác thực mới.

Tuy nhiên, prompt hiển thị không tự chứng minh người dùng đã dùng phương thức đủ mạnh. RP cần kiểm tra kết quả xác thực, `auth_time` và assurance context nếu hành động có yêu cầu cụ thể. Nếu OP chỉ yêu cầu nhập lại một mật khẩu dễ bị phishing, kết quả có thể mới nhưng chưa đáp ứng policy chống phishing.

### 7.3. Kiểm tra `auth_time`, `acr` và `amr`

Sau callback, RP phải xác minh ID Token theo OIDC: chữ ký, issuer, audience, thời hạn, nonce và các kiểm tra liên quan. Khi dùng `max_age`, RP đọc `auth_time` đã được xác minh và so với đồng hồ server:

~~~text
now = server_time()
auth_age = now - verified_id_token.auth_time

accept only if:
  auth_age >= -allowed_clock_skew
  auth_age <= required_max_age + allowed_clock_skew
~~~

`acr` (Authentication Context Class Reference) có thể cho biết ngữ cảnh/mức xác thực mà OP khẳng định. RP có thể yêu cầu một giá trị qua `acr_values`, nhưng phải kiểm tra `acr` thực tế được trả về có nằm trong các mức chấp nhận hay không.

`amr` (Authentication Methods References) có thể mô tả phương thức đã dùng, ví dụ password, OTP hoặc phương thức khác theo hệ thống. Giá trị và cách diễn giải cần theo profile/issuer đã thỏa thuận; không tự suy ra một mức assurance chỉ từ một chuỗi `amr` không được kiểm chứng.

Không phải mọi OP đều hỗ trợ cùng mức `acr` hoặc `amr`. Nếu OP không thể đáp ứng mức yêu cầu, RP nên từ chối hành động nhạy cảm hoặc đưa ra phương án được policy phê duyệt, thay vì âm thầm hạ yêu cầu.

### 7.4. Luồng OIDC re-authentication

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant RP as Ứng dụng / RP
    participant OP as OpenID Provider
    U->>RP: Chọn thao tác nhạy cảm
    RP->>RP: Kiểm tra auth_time và assurance hiện tại
    RP-->>U: Chuyển tới OP với max_age / prompt=login
    U->>OP: Xác thực lại theo policy của OP
    OP-->>RP: Authorization response / code
    RP->>OP: Đổi code bằng PKCE
    OP-->>RP: Token response + ID Token
    RP->>RP: Xác minh ID Token, auth_time và acr/amr
    RP->>RP: Gắn kết quả với session và hành động đang chờ
    RP-->>U: Tiếp tục hoặc từ chối thao tác
~~~

RP phải giữ `state` và ràng buộc callback với session/flow đã bắt đầu. Dùng PKCE cho Authorization Code Flow và `nonce` khi áp dụng OIDC authentication. Không chấp nhận callback chỉ vì có `code` hoặc `state` hợp lệ mà bỏ qua việc xác minh token.

## 8. Re-authentication trong SAML 2.0

Với SAML 2.0, Service Provider (SP) có thể gửi `AuthnRequest` với thuộc tính `ForceAuthn="true"` để yêu cầu Identity Provider thực hiện xác thực trực tiếp thay vì chỉ dựa vào session đăng nhập hiện có.

SP cũng có thể yêu cầu một ngữ cảnh xác thực qua `RequestedAuthnContext` và `AuthnContextClassRef`, tùy thỏa thuận giữa SP và IdP. Sau khi nhận `Response`, SP cần xác minh chữ ký, issuer, audience, destination, thời gian, `InResponseTo` và điều kiện hiệu lực. Nếu policy dựa vào độ mới, SP cần kiểm tra `AuthnInstant` trong `AuthnStatement`; nếu dựa vào mức assurance, cần kiểm tra `AuthnContext` thực tế được trả về.

`ForceAuthn` yêu cầu IdP xác thực lại theo giao thức, nhưng không tự đảm bảo phương thức được dùng là passkey, MFA hoặc phishing-resistant. SP và IdP phải thống nhất ngữ nghĩa `AuthnContext` và cách xác minh kết quả.

## 9. Re-authentication trực tiếp bằng passkey/WebAuthn

Ứng dụng có thể yêu cầu một WebAuthn assertion mới trong session hiện tại. Browser gọi `navigator.credentials.get()` với challenge mới; authenticator dùng credential đã đăng ký để tạo assertion.

Với thao tác cần xác minh người dùng cục bộ, server có thể đặt `userVerification: "required"` trong request options. Khi xác minh response, server phải kiểm tra:

- Challenge mới khớp với flow và session đang chờ.
- Origin và RP ID hash đúng.
- Credential ID thuộc đúng tài khoản và vẫn Active.
- Chữ ký assertion hợp lệ với public key đã đăng ký.
- Cờ UP/UV đáp ứng policy.
- Challenge còn hạn, chưa dùng và được tiêu thụ đúng một lần.

UV (User Verification) cho biết authenticator đã thực hiện cơ chế xác minh người dùng cục bộ theo khả năng của nó, ví dụ PIN hoặc sinh trắc học. RP không nhận dữ liệu sinh trắc học thô và không được suy diễn UV thành identity proofing hoặc bằng chứng về ý định đối với nội dung giao dịch.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant A as Authenticator
    participant S as Server
    U->>S: Yêu cầu thao tác nhạy cảm
    S->>S: Tạo challenge gắn session và action
    S-->>B: PublicKeyCredentialRequestOptions (UV required)
    B->>A: navigator.credentials.get()
    A->>A: Xác minh người dùng và ký assertion
    A-->>B: Assertion
    B->>S: Assertion + challenge context
    S->>S: Xác minh challenge, origin, RP ID, chữ ký, UP/UV
    S->>S: Ghi nhận re-authentication mới
    S-->>U: Cho phép tiếp tục theo policy
~~~

Một assertion mới chứng minh credential đã được sử dụng trong flow đó. Nó không tự ràng buộc người dùng vào nội dung nghiệp vụ mà họ không nhìn thấy. Với giao dịch cần xác nhận người nhận/số tiền, giao diện phải trình bày rõ chi tiết và server phải ràng buộc quyết định với đúng transaction record; nếu cần bằng chứng ký giao dịch, phải dùng thiết kế transaction confirmation phù hợp, không chỉ đổi challenge WebAuthn tùy ý.

## 10. Luồng re-authentication an toàn trong ứng dụng

Một luồng tổng quát:

~~~mermaid
flowchart TD
    A["Người dùng yêu cầu hành động"] --> B["Server tải session và policy"]
    B --> C{"Auth time còn mới và assurance đủ?"}
    C -->|Có| H["Kiểm tra authorization trên tài nguyên"]
    C -->|Không| D["Tạo re-auth flow gắn session + action"]
    D --> E["Yêu cầu credential phù hợp"]
    E --> F{"Bằng chứng mới hợp lệ?"}
    F -->|Không| G["Từ chối / giới hạn thử / fallback được duyệt"]
    F -->|Có| I["Cập nhật auth context và xoay session ID"]
    I --> J["Kiểm tra lại policy và authorization"]
    J --> H
    H --> K["Thực hiện hành động"]
~~~

Trình tự triển khai:

1. Nhận request thực hiện hành động nhạy cảm và xác định resource/action.
2. Tải session từ kho tin cậy; kiểm tra account, tenant, trạng thái session và quyền hiện tại.
3. Đánh giá freshness và assurance theo policy của hành động.
4. Nếu chưa đủ, tạo re-authentication transaction có ID ngẫu nhiên, thời hạn ngắn và ràng buộc với session, principal, tenant, action.
5. Yêu cầu phương thức phù hợp; không để client tự chọn mức assurance thấp hơn.
6. Xác minh bằng chứng ở server và kiểm tra challenge chưa được dùng.
7. Cập nhật auth context, thời điểm re-auth và assurance đã xác minh.
8. Xoay session ID hoặc cấp step-up context riêng; vô hiệu hóa ID cũ theo thiết kế session.
9. Kiểm tra authorization lần nữa trên tài nguyên và trạng thái hiện tại.
10. Thực hiện hành động và ghi audit event.

Không thực hiện hành động chỉ vì endpoint re-authentication trả về thành công. Endpoint nghiệp vụ vẫn phải kiểm tra session/step-up context, quyền, tenant, trạng thái giao dịch và các điều kiện cần thiết.

## 11. Gắn re-authentication với session

Server nên lưu auth context ở phía server hoặc trong token đã được xác minh, tùy kiến trúc. Một session record minh họa:

~~~json
{
  "sessionId": "opaque-random-session-id",
  "principalId": "user-42",
  "tenantId": "tenant-a",
  "authTime": "2026-11-22T10:00:00Z",
  "lastReauthAt": "2026-11-22T11:45:00Z",
  "assurance": "phishing-resistant",
  "amr": ["webauthn"],
  "credentialRef": "credential-record-9",
  "stepUpUntil": "2026-11-22T11:50:00Z",
  "sessionVersion": 12
}
~~~

Đây là cấu trúc ứng dụng minh họa, không phải schema chuẩn. Cần phân biệt:

- `authTime`: thời điểm xác thực thực sự đã được issuer hoặc ứng dụng xác minh.
- `lastReauthAt`: thời điểm server chấp nhận một lần xác thực lại.
- `stepUpUntil`: thời điểm context nâng quyền tạm thời hết hiệu lực.
- `sessionVersion`: hỗ trợ thu hồi hoặc vô hiệu hóa session cũ.

Không cập nhật `authTime` chỉ vì người dùng có hoạt động, refresh token, tải trang hoặc gia hạn cookie. Chỉ cập nhật khi một bằng chứng xác thực mới đã được xác minh.

### 11.1. Xoay session ID sau re-authentication

Khi xác thực lại thành công hoặc thay đổi mức quyền, nên cân nhắc tạo session ID mới và vô hiệu hóa ID cũ. Điều này giúp giảm rủi ro session fixation và tránh việc kẻ tấn công tiếp tục dùng một session ID được tạo trước khi mức assurance thay đổi.

Nếu hệ thống dùng step-up context riêng, cần ràng buộc nó với session hiện tại, principal, action hoặc resource, thời hạn và một lần sử dụng khi phù hợp. Không lưu một cờ `isReauthenticated=true` lâu dài rồi dùng cho mọi hành động trong tương lai.

### 11.2. Phạm vi và thời hạn step-up

Một lần re-authentication có thể chỉ đủ cho một hành động hoặc một khoảng thời gian ngắn. Ví dụ, xác thực lại để thay email không nên tự động cho phép tạo API key quản trị trong 30 phút nếu policy của hai hành động khác nhau.

Có thể thiết kế step-up context:

- Gắn với một hành động hoặc nhóm hành động cụ thể.
- Giới hạn thời gian hiệu lực.
- Giới hạn tenant và resource.
- Ghi lại assurance/factor đã xác minh.
- Tiêu thụ một lần cho thao tác đặc biệt.
- Thu hồi khi session hoặc tài khoản bị thu hồi.

## 12. Re-authentication và xác nhận giao dịch

Re-authentication xác minh người dùng vừa chứng minh quyền kiểm soát credential. **Transaction confirmation** xác nhận người dùng chấp thuận một nội dung nghiệp vụ cụ thể. Hai việc cần được phân biệt.

Ví dụ, người dùng xác thực lại bằng passkey trước khi chuyển tiền. Nếu số tiền hoặc người nhận thay đổi sau khi xác thực, server không nên dùng kết quả re-auth cũ để cho phép giao dịch mới.

Một thiết kế an toàn cần:

1. Tạo transaction record phía server với người nhận, số tiền, đơn vị tiền và trạng thái.
2. Hiển thị chi tiết giao dịch rõ ràng cho người dùng trước bước xác nhận.
3. Ràng buộc challenge/approval với transaction ID và phiên bản nội dung giao dịch.
4. Kiểm tra nội dung không thay đổi giữa lúc hiển thị, xác thực và thực thi.
5. Dùng cơ chế xác nhận phù hợp với mức rủi ro; nếu cần ký giao dịch, thiết kế phải cung cấp khả năng xác nhận nội dung theo mô hình tin cậy được đánh giá.
6. Chống replay và xử lý idempotency để không tạo giao dịch trùng.

Chỉ yêu cầu nhập lại mật khẩu rồi thực hiện một giao dịch không giải quyết được việc người dùng có nhìn thấy hoặc chấp thuận đúng nội dung hay không.

## 13. Risk-based re-authentication

Không phải mọi session cần cùng một chính sách. Risk engine có thể xem xét nhiều tín hiệu:

- Thời gian kể từ lần xác thực thực sự.
- Loại credential và mức assurance đã xác minh.
- Thiết bị có được quản lý hoặc đăng ký hay không.
- Vị trí và mạng ở mức tín hiệu rủi ro, không dùng IP làm bằng chứng danh tính.
- Hành vi bất thường, tốc độ thao tác hoặc thay đổi mẫu sử dụng.
- Thay đổi mật khẩu, recovery method, factor hoặc trạng thái tài khoản gần đây.
- Tài nguyên và hậu quả của hành động đang yêu cầu.

Một quyết định mẫu:

| Tình huống | Hành động |
| --- | --- |
| Session mới, passkey UV, thao tác ít rủi ro | Tiếp tục nếu authorization cho phép. |
| Session cũ, thao tác nhạy cảm | Yêu cầu re-authentication mới. |
| Session mới nhưng chỉ password, hành động cần chống phishing | Yêu cầu step-up bằng phương thức phù hợp. |
| Thiết bị mới và thay đổi recovery | Step-up mạnh, thông báo và có thể review. |
| Dấu hiệu chiếm session | Tạm dừng thao tác, thu hồi session hoặc chuyển incident response. |
| Không có factor phù hợp | Từ chối hành động hoặc chuyển quy trình recovery/proofing đã được phê duyệt. |

Không nên tự động hạ mức bảo đảm chỉ vì người dùng không có thiết bị phù hợp. Với hành động có rủi ro cao, từ chối tạm thời có thể an toàn hơn một fallback yếu.

## 14. Trải nghiệm người dùng và phương thức dự phòng

Re-authentication cần dễ hiểu và đúng thời điểm:

- Nói rõ vì sao cần xác thực lại, ví dụ “Xác minh lại trước khi thay đổi thông tin recovery”.
- Giữ người dùng trong đúng luồng và đúng website; không yêu cầu nhập credential trên trang không rõ nguồn gốc.
- Ưu tiên passkey hoặc security key khi policy yêu cầu chống phishing.
- Cho phép hủy thao tác mà không làm session bình thường bị mất ngoài ý muốn.
- Thông báo nếu lần xác thực không đáp ứng yêu cầu, nhưng không tiết lộ chi tiết giúp attacker dò policy.
- Hạn chế số lần thử và áp dụng cooldown phù hợp để chống brute force.
- Cung cấp phương thức dự phòng có mức bảo đảm tương xứng, không mặc định SMS hoặc câu hỏi bảo mật là phương án tương đương.

Nếu người dùng mất factor mạnh, fallback nên đi qua recovery/identity proofing có kiểm soát. Nhân viên hỗ trợ không nên có quyền bỏ qua step-up chỉ bằng thông tin dễ tìm hoặc một cuộc gọi không được xác minh.

Không nên ghi lại password, OTP, assertion, private key hoặc session token trong log để hỗ trợ debug. Log chỉ nên có mã flow, kết quả, factor type, policy ID và thông tin cần thiết cho audit.

## 15. Các mối đe dọa và cách phòng tránh

| Mối đe dọa | Tác động | Kiểm soát |
| --- | --- | --- |
| Session theft | Attacker dùng session cũ để thực hiện thao tác. | Re-authentication cho hành động nhạy cảm, session protection và revoke. |
| Session fixation | Attacker giữ session ID cũ sau khi quyền được nâng. | Xoay session ID sau authentication/step-up và vô hiệu hóa ID cũ. |
| Phishing re-authentication | Người dùng nhập lại mật khẩu/OTP trên trang giả. | Ưu tiên passkey/WebAuthn hoặc factor chống phishing. |
| Replay challenge/assertion | Bằng chứng cũ được gửi lại. | Challenge ngẫu nhiên, ngắn hạn, gắn flow/session và dùng một lần. |
| Callback substitution | Kết quả xác thực bị gắn với session hoặc action khác. | State, nonce, PKCE, session binding và transaction ID. |
| Downgrade fallback | Attacker ép người dùng dùng phương thức yếu hơn. | Policy server-side, allowlist assurance và audit fallback. |
| CSRF trên endpoint nhạy cảm | Website khác kích hoạt re-auth hoặc hành động. | CSRF protection, SameSite, Origin checks và POST cho state change. |
| XSS | Script độc hại điều khiển session đang mở. | CSP, output encoding, dependency hygiene, HttpOnly và step-up theo action. |
| Stale assurance | Cờ xác thực mạnh cũ được dùng vô thời hạn. | Freshness policy và step-up context có expiry/scope. |
| Recovery bypass | Attacker dùng kênh recovery yếu để vượt re-auth. | Proofing, phê duyệt, thông báo và kiểm soát ngoại lệ. |

### 15.1. Không biến re-authentication thành một oracle

Thông báo lỗi quá chi tiết có thể tiết lộ tài khoản có factor nào, session còn hiệu lực hay người dùng đã đăng ký passkey. Phản hồi tới client nên đủ để người dùng biết bước tiếp theo nhưng không tiết lộ dữ liệu nội bộ không cần thiết.

### 15.2. Chống replay và race condition

Challenge phải được tiêu thụ nguyên tử. Nếu hai request đồng thời gửi cùng assertion, chỉ một request được phép hoàn tất flow. Khi re-auth thành công, action đang chờ cũng cần được xử lý theo trạng thái idempotent để retry không gây tác động nghiệp vụ trùng.

## 16. Ví dụ pseudocode phía server

Đoạn mã khái niệm minh họa cách kiểm tra freshness và assurance trước một thao tác:

~~~ts
async function authorizeSensitiveAction(sessionId, action, resource) {
  const session = await sessionStore.load(sessionId);
  if (!session || session.status !== "active") {
    throw new UnauthorizedError();
  }

  const policy = await policyEngine.getPolicy(action, resource);
  const now = Date.now();
  const authAgeMs = now - session.authTime;

  const freshEnough =
    authAgeMs >= -policy.clockSkewMs &&
    authAgeMs <= policy.maxAuthAgeMs + policy.clockSkewMs;

  const assuranceEnough =
    policy.acceptedAssurance.includes(session.assurance);

  if (!freshEnough || !assuranceEnough) {
    return createBoundReauthChallenge({
      principalId: session.principalId,
      tenantId: session.tenantId,
      sessionId: session.id,
      action,
      resourceId: resource.id,
      expiresInSeconds: 180
    });
  }

  return executeWithAuthorization(session, action, resource);
}
~~~

Sau khi challenge được hoàn tất, server cần xác minh bằng chứng theo giao thức, kiểm tra challenge chưa dùng, cập nhật auth context và xoay session ID. Pseudocode trên không thay thế xác minh chữ ký, OIDC/SAML token validation, WebAuthn assertion verification hoặc authorization thực tế.

## 17. Ví dụ: thay đổi email recovery

Một người dùng đăng nhập vào ứng dụng bằng password từ đầu ngày. Buổi chiều họ muốn thay email recovery.

**Policy:**

- Thay email recovery cần xác thực trong vòng 5 phút.
- Phương thức phải đạt assurance đã được policy chấp nhận.
- Sau khi thay đổi, hệ thống gửi thông báo tới email cũ và email mới theo quy trình đã xác minh.

**Luồng:**

1. Server kiểm tra session và thấy `auth_time` đã quá 5 phút.
2. Server tạo re-auth transaction gắn với principal, session và action `change-recovery-email`.
3. Ứng dụng yêu cầu passkey assertion mới với user verification theo policy.
4. Server xác minh challenge, origin, RP ID, chữ ký, UP/UV và trạng thái credential.
5. Server ghi nhận `last_reauth_at`, xoay session ID và tạo step-up context chỉ dùng cho hành động thay email.
6. Server kiểm tra lại quyền và xác nhận email mới theo quy trình.
7. Nếu email thay đổi thành công, audit event và thông báo bảo mật được phát.

Nếu người dùng không có passkey, hệ thống chuyển sang quy trình recovery đã được phê duyệt hoặc từ chối tạm thời. Không tự động hạ xuống câu hỏi bảo mật chỉ để hoàn tất thao tác.

## 18. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi refresh token là re-authentication | Thời điểm xác thực không được làm mới. | Chỉ cập nhật auth time sau khi xác minh bằng chứng người dùng mới. |
| Dựa vào `last_activity_at` | Hoạt động thông thường bị hiểu nhầm là xác thực gần đây. | Lưu auth time và activity time riêng. |
| Gửi `prompt=login` nhưng không kiểm tra kết quả | Có thể chấp nhận token không đáp ứng freshness/assurance. | Xác minh ID Token, `auth_time`, `acr`/`amr` theo policy. |
| Tin `acr_values` đã được đáp ứng chỉ vì đã yêu cầu | OP có thể trả context khác hoặc không hỗ trợ. | Kiểm tra `acr` thực tế và từ chối nếu không đạt. |
| Re-auth bằng password yếu cho mọi thao tác | Vẫn dễ bị phishing hoặc credential stuffing. | Chọn factor theo rủi ro; ưu tiên phương thức phishing-resistant. |
| Dùng cờ `reauthenticated=true` vô thời hạn | Assurance cũ được tái sử dụng không giới hạn. | Gắn step-up context với thời hạn, action/resource và session. |
| Không xoay session ID | Session fixation hoặc session cũ tiếp tục được dùng sau step-up. | Xoay ID và vô hiệu hóa ID trước đó. |
| Chỉ ẩn nút ở frontend | API vẫn có thể bị gọi trực tiếp. | Kiểm tra freshness, assurance và authorization ở server. |
| Fallback yếu hơn mà không có policy | Attacker ép downgrade. | Định nghĩa allowlist assurance và quy trình recovery riêng. |
| Coi re-auth là xác nhận nội dung giao dịch | Người dùng có thể xác thực nhưng không chấp thuận nội dung thực tế. | Ràng buộc confirmation với transaction details/version. |
| Không giới hạn challenge và attempt | Brute force, replay hoặc abuse endpoint. | Challenge ngắn hạn, one-time, rate limit và audit. |
| Không xử lý đồng thời | Cùng một challenge có thể được dùng nhiều lần. | Consume challenge nguyên tử và idempotency cho action. |

## 19. Checklist thiết kế re-authentication

Trước khi đưa re-authentication vào production, hãy kiểm tra:

1. Hành động nào cần xác thực lại và hậu quả nếu attacker thực hiện thành công là gì?
2. Policy có tách freshness khỏi assurance không?
3. `auth_time`, `last_reauth_at`, session activity và token issue time có được lưu riêng không?
4. Thời điểm xác thực có đến từ bằng chứng/token đã xác minh thay vì client tự khai không?
5. OIDC có dùng `max_age`/`prompt=login` phù hợp và kiểm tra `auth_time`, `acr`/`amr` thực tế không?
6. SAML có dùng `ForceAuthn`/`RequestedAuthnContext` khi phù hợp và kiểm tra `AuthnInstant`/`AuthnContext` trả về không?
7. WebAuthn có challenge mới, session binding, origin/RP ID validation, signature verification và UV theo policy không?
8. Challenge có ngắn hạn, dùng một lần và được tiêu thụ nguyên tử không?
9. Kết quả re-auth có gắn với đúng principal, tenant, session, action và resource không?
10. Session ID có được xoay sau xác thực lại hoặc nâng quyền không?
11. Step-up context có scope và expiry rõ ràng, tránh tái sử dụng vô hạn không?
12. API nghiệp vụ có kiểm tra lại authorization và trạng thái tài nguyên ở server không?
13. Giao dịch nhạy cảm có xác nhận nội dung riêng, không nhầm re-auth với transaction approval không?
14. Fallback/recovery có mức bảo đảm phù hợp, chống downgrade và có audit không?
15. Có rate limit, CSRF protection, replay prevention, logging an toàn và thông báo bảo mật không?
16. Có kiểm thử session cũ, refresh token, clock skew, token thiếu `auth_time`, `acr` không đạt, callback sai, replay và race condition không?

**Kết luận:** Re-authentication tạo bằng chứng xác thực mới trước khi tiếp tục một hành động nhạy cảm; step-up nâng mức bảo đảm khi policy đòi hỏi phương thức mạnh hơn. Hệ thống phải đánh giá riêng độ mới và assurance, xác minh kết quả ở server, gắn challenge với session/action và giới hạn thời gian sử dụng kết quả. OIDC `max_age`/`prompt=login`, SAML `ForceAuthn` và WebAuthn assertion mới là những cơ chế có thể hỗ trợ luồng này khi được kiểm tra đúng. Re-authentication vẫn cần đi cùng authorization, quản lý session/token, transaction confirmation và recovery an toàn.
