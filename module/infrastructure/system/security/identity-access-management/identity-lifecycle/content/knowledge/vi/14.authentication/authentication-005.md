# Authentication flow trong IAM: từ yêu cầu đăng nhập đến phiên truy cập hợp lệ

**Authentication flow (luồng xác thực)** là chuỗi bước giúp một hệ thống quyết định **chủ thể đang truy cập có chứng minh được danh tính hoặc quyền kiểm soát phương thức xác thực được tin cậy hay không**. Trong hệ thống doanh nghiệp, luồng này thường đi từ trình duyệt hoặc ứng dụng đến **Identity Provider (IdP)**, đi qua cơ chế mật khẩu, passkey, MFA hoặc liên kết xác thực (**Single Sign-On – SSO**), rồi trở lại ứng dụng với một kết quả xác thực có thể kiểm chứng.

Đối với mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, xác thực không tồn tại độc lập: quyền đăng nhập phải dựa trên một **danh tính và tài khoản hợp lệ trong vòng đời Joiner–Mover–Leaver (JML)**. Khi người dùng mới vào tổ chức, IAM phải xác minh, tạo tài khoản và đăng ký phương thức xác thực. Khi chuyển vai trò, hệ thống có thể cần đánh giá lại rủi ro, thuộc tính và quyền. Khi rời tổ chức, việc vô hiệu hóa account phải kết hợp xử lý **phiên, token, ứng dụng và quyền truy cập tồn dư**.

**Điểm cốt lõi:** **Đăng nhập thành công không có nghĩa người dùng được phép thực hiện mọi hành động**. Authentication trả lời “ai đang xác thực?”, còn authorization (**RBAC/ABAC**) trả lời “chủ thể đó được làm gì với tài nguyên nào, trong điều kiện nào?”.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả từng bước của authentication flow từ yêu cầu truy cập, xác thực tại IdP, xác thực bổ sung đến thiết lập phiên ứng dụng.
2. Phân biệt **identity proofing**, **account provisioning**, **authentication**, **federation/SSO**, **authorization** và **session management**.
3. Hiểu luồng **OpenID Connect (OIDC) Authorization Code + PKCE**, vai trò của `state`, `nonce`, authorization code, ID token và access token.
4. Nhận diện những khác biệt cơ bản giữa luồng OIDC, SAML và tài khoản đăng nhập cục bộ.
5. Giải thích khi nào cần MFA, step-up authentication, passkey và quy trình khôi phục tài khoản.
6. Phân tích rủi ro ở các bước chuyển hướng, kiểm chứng token, quản lý phiên và xử lý lỗi xác thực.
7. Liên hệ kết quả đăng nhập với **IdP, SSO, SCIM, RBAC/ABAC**, tài khoản dịch vụ, kiểm toán và biến cố **Joiner–Mover–Leaver**.

## 2. Các khái niệm cần phân biệt trước khi đọc một luồng

| Khái niệm | Câu hỏi nó giải quyết | Ví dụ |
|---|---|---|
| **Identity proofing** | Có cơ sở gì để tin người đăng ký là đúng cá nhân? | Đối chiếu bằng chứng danh tính với người tham gia onboarding |
| **Identity / account** | Hệ thống quản lý chủ thể và tài khoản nào? | `personId=P-2048` ánh xạ tới `idpUserId=U-88` |
| **Provisioning** | Tài khoản và nhóm đã được tạo/cập nhật tại đích chưa? | SCIM tạo user trong CRM |
| **Authentication** | Lần này chủ thể chứng minh quyền kiểm soát phương thức đăng nhập ra sao? | Người dùng hoàn tất xác thực bằng passkey |
| **Federation / SSO** | Ứng dụng tin cậy kết quả xác thực từ IdP như thế nào? | Ứng dụng dùng OIDC, không tự nhận mật khẩu |
| **Authorization** | Có được xem hoặc sửa dữ liệu cụ thể không? | `finance.read.region_south` theo RBAC/ABAC |
| **Session management** | Trạng thái đăng nhập được duy trì, giới hạn và chấm dứt thế nào? | Cookie phiên ứng dụng hoặc token có thời hạn |
| **Deprovisioning** | Quyền và đường đăng nhập phải được thu hồi khi nào? | Account bị disable; các phiên/token liên quan được xử lý |

Một người có thể **vượt qua authentication** nhưng vẫn không có account ở ứng dụng do provisioning chưa hoàn tất. Người khác có account hoạt động nhưng **bị từ chối authentication** vì cần MFA hoặc tài khoản bị khóa. Một người thứ ba đăng nhập được nhưng **bị từ chối authorization** vì vai trò không cho xem báo cáo.

### 2.1. Ai tham gia một authentication flow?

Trong luồng đăng nhập web qua OIDC, thường có:

- **End user / subject:** Người muốn sử dụng tài nguyên.
- **User agent (browser):** Trình duyệt nhận chuyển hướng và lưu cookie phù hợp; nó không phải nơi đáng tin để giữ bí mật của máy chủ.
- **Relying Party (RP) / client:** Ứng dụng yêu cầu IdP xác thực người dùng và kiểm chứng kết quả.
- **Identity Provider (IdP) / OpenID Provider (OP):** Hệ thống thực hiện xác thực, chính sách MFA và phát hành kết quả xác thực.
- **API / Resource Server:** Thành phần bảo vệ dữ liệu/chức năng và kiểm tra access token cùng quyền nghiệp vụ.
- **IAM / IGA:** Hệ thống quản lý danh tính, vòng đời account, nhóm, entitlement và trạng thái JML; không nhất thiết nằm trực tiếp trên mọi request đăng nhập.

Sự phân chia này có thể thay đổi giữa các nền tảng. Điều quan trọng là **mỗi bên biết mình có thể tin cậy thông tin nào và phải tự kiểm chứng điều gì**.

## 3. Một authentication flow điển hình

Người dùng mở ứng dụng khi chưa có phiên hợp lệ. Ứng dụng phát hiện cần đăng nhập, gửi yêu cầu tới IdP và chờ kết quả qua giao thức tin cậy.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant A as Ứng dụng / RP
    participant I as IdP / OP
    participant R as API / tài nguyên

    U->>B: Mở ứng dụng
    B->>A: Yêu cầu tài nguyên
    A-->>B: Redirect tới IdP (state, nonce, PKCE)
    B->>I: Authorization request
    I->>U: Yêu cầu xác thực khi cần
    U->>I: Chứng minh danh tính (passkey/MFA...)
    I-->>B: Redirect về callback kèm code + state
    B->>A: Gửi code + state tới callback
    A->>A: Kiểm tra state và giao dịch đã khởi tạo
    A->>I: Đổi code lấy token qua kênh bảo vệ + PKCE
    I-->>A: ID token và các token liên quan
    A->>A: Kiểm chứng token, liên kết subject với account
    A-->>B: Tạo phiên ứng dụng có bảo vệ
    B->>A: Yêu cầu chức năng
    A->>R: Request kèm token phù hợp nếu cần
    R->>R: Kiểm tra token và authorization
    R-->>A: Dữ liệu/chức năng được phép hoặc từ chối
    A-->>B: Kết quả phù hợp chính sách
~~~

Sơ đồ là luồng **web server / backend-for-frontend** minh họa. Ứng dụng mobile hoặc public client có cách giữ token và ranh giới tin cậy riêng; phải theo hướng dẫn chính thức của nền tảng và thư viện tương ứng.

### 3.1. Chuỗi logic tối thiểu

1. **Phát sinh nhu cầu xác thực:** Ứng dụng phát hiện chưa có phiên hợp lệ.
2. **Khởi tạo giao dịch:** Ứng dụng sinh dữ liệu liên kết yêu cầu/response và cơ chế bảo vệ luồng.
3. **Chuyển đến IdP:** Trình duyệt đi tới endpoint xác thực được cấu hình tin cậy.
4. **Xác thực người dùng:** IdP kiểm tra authenticator, tình trạng account và chính sách.
5. **MFA / step-up nếu cần:** IdP áp dụng kiểm soát tăng cường theo rủi ro và hành động.
6. **Trả kết quả có thể kiểm chứng:** Ứng dụng nhận authorization code hoặc phản hồi theo giao thức.
7. **Kiểm chứng giao thức và danh tính:** Ứng dụng kiểm tra nguồn phát hành, đối tượng, thời hạn và liên kết với request.
8. **Thiết lập phiên ứng dụng:** Ứng dụng gắn phiên với subject được xác nhận.
9. **Ủy quyền từng hành động:** Hệ thống bảo vệ API/dữ liệu kiểm tra quyền còn hợp lệ.
10. **Duy trì và kết thúc:** Phiên, token, logout, timeout và biến cố JML được xử lý theo chính sách.

Không được bỏ qua bước 7 rồi tin trực tiếp các tham số trên URL hoặc nội dung token chưa được kiểm chứng.

## 4. Luồng OIDC Authorization Code với PKCE

**OpenID Connect (OIDC)** là lớp định danh xây trên OAuth 2.0. Trong đăng nhập web liên kết, **Authorization Code flow có PKCE** là một mẫu quan trọng: trình duyệt nhận một **authorization code ngắn hạn, dùng một lần**, còn việc đổi code lấy token được thực hiện theo yêu cầu của client và khả năng bảo vệ thích hợp.

**OAuth 2.0 tự nó là khung cấp quyền truy cập cho client, không đồng nghĩa một giao thức đăng nhập người dùng.** Với bài toán “ứng dụng xác thực người dùng là ai”, OIDC bổ sung **ID token** và quy tắc kiểm chứng danh tính.

### 4.1. Khởi tạo authorization request

Ứng dụng tạo các giá trị giao dịch:

| Giá trị | Vai trò |
|---|---|
| `client_id` | Định danh client đã đăng ký với IdP |
| `redirect_uri` | Endpoint callback được đăng ký và kiểm soát |
| `response_type=code` | Yêu cầu authorization code |
| `scope=openid` | Thể hiện một yêu cầu OIDC; có thể kèm các scope được phép |
| `state` | Liên kết response với giao dịch đã khởi tạo, giúp chống CSRF/mix-up theo thiết kế |
| `nonce` | Giá trị liên kết ID token với giao dịch xác thực OIDC khi được sử dụng |
| `code_challenge` | Giá trị dẫn xuất từ verifier bí mật của giao dịch để bảo vệ quá trình đổi code |
| `code_challenge_method=S256` | Chỉ phương pháp biến đổi PKCE bằng SHA-256 |

Một yêu cầu minh họa; các chuỗi đã rút gọn và **không phải giá trị bảo mật để sử dụng nguyên xi**:

~~~http
GET /authorize?response_type=code
    &client_id=portal-app
    &redirect_uri=https%3A%2F%2Fportal.example.test%2Fcallback
    &scope=openid%20profile
    &state=RANDOM_STATE_PER_LOGIN
    &nonce=RANDOM_NONCE_PER_LOGIN
    &code_challenge=DERIVED_S256_CHALLENGE
    &code_challenge_method=S256
~~~

Trong HTTP thực tế, các tham số GET được mã hóa trên **một URL hợp lệ**; ví dụ xuống dòng để dễ đọc.

Ứng dụng phải tạo `state`, `nonce` và `code_verifier` **đủ ngẫu nhiên, riêng cho từng giao dịch**, lưu chúng trong ngữ cảnh có bảo vệ phù hợp, không dùng giá trị cố định như trong tài liệu này. `redirect_uri` cần được kiểm soát bằng đăng ký chính xác; không nhận một địa chỉ trả về tùy ý từ đầu vào người dùng.

### 4.2. Xác thực tại IdP

IdP có thể đã có phiên hợp lệ, nên **không nhất thiết yêu cầu người dùng nhập lại thông tin**. Nếu chưa có phiên hoặc chính sách yêu cầu, IdP tiến hành xác thực bằng phương thức được cho phép:

- Mật khẩu kết hợp MFA trong môi trường còn sử dụng mật khẩu.
- Passkey/FIDO2/WebAuthn với cơ chế dựa trên mật mã khóa công khai.
- Khóa bảo mật vật lý hoặc phương thức xác thực mạnh khác.
- Xác thực bổ sung khi tài nguyên/hành động đòi hỏi mức bảo đảm cao hơn.

IdP cũng cần xem trạng thái tài khoản và những tín hiệu chính sách hiện hành: disabled, locked, risk, device, network, phương thức xác thực đã đăng ký và điều kiện thời điểm. **Tài khoản được tạo trong Joiner nhưng chưa đến ngày hiệu lực** không nên được mở quyền truy cập công việc chỉ vì hồ sơ đã tồn tại.

### 4.3. Trả authorization code về ứng dụng

Sau khi xử lý, IdP chuyển trình duyệt về callback đã đăng ký, thường kèm **`code` và `state`**. Ứng dụng phải xác minh `state` với giao dịch đang chờ, kiểm tra lỗi và chỉ tiếp tục khi có đủ điều kiện.

Authorization code:

- Là kết quả trung gian có thời hạn ngắn.
- Được ràng buộc với client/redirect và giao dịch theo quy tắc giao thức.
- Không phải access token hay ID token.
- Phải được đổi theo quy trình bảo vệ thích hợp, không lưu làm token phiên lâu dài.

### 4.4. Đổi code lấy token

Ứng dụng gửi yêu cầu tới token endpoint qua kết nối được bảo vệ, sử dụng `code_verifier` khớp `code_challenge` đã gửi. Confidential client còn phải thực hiện client authentication theo cấu hình và đặc tả áp dụng; public client không giữ được client secret như máy chủ.

~~~http
POST /token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=RECEIVED_ONE_TIME_CODE
&redirect_uri=https%3A%2F%2Fportal.example.test%2Fcallback
&client_id=portal-app
&code_verifier=ORIGINAL_PRIVATE_VERIFIER
~~~

Đây là **hình dạng yêu cầu minh họa**, không bao gồm cơ chế client authentication, transport security hay các yêu cầu triển khai đầy đủ. Ứng dụng nên sử dụng **thư viện OIDC/OAuth đã được kiểm chứng** thay vì tự viết phần mật mã và xử lý token.

### 4.5. Kiểm chứng ID token trước khi tạo phiên

ID token là bằng chứng giao thức về sự kiện xác thực và các claim liên quan. Ứng dụng cần kiểm chứng theo OIDC và cấu hình IdP:

- Chữ ký/token validation theo khóa và thuật toán đã cho phép; không tự tin vào khai báo thuật toán do token cung cấp.
- `iss` – issuer phải là nhà phát hành tin cậy đã cấu hình.
- `aud` – audience phải chứa client phù hợp; xét `azp` khi đặc tả yêu cầu.
- `exp`, `iat` và các giới hạn thời gian liên quan theo chính sách.
- `nonce` – khớp giá trị giao dịch nếu yêu cầu và đã được sử dụng.
- Các thông tin về mức/độ mới xác thực như `auth_time`, `acr`, `amr` **khi chính sách thực sự cần và IdP có hỗ trợ, với ngữ nghĩa đã thống nhất**.

Một payload đã giải mã có thể trông như sau:

~~~json
{
  "iss": "https://idp.example.test",
  "sub": "user-8fd2",
  "aud": "portal-app",
  "exp": 1790003600,
  "iat": 1790000000,
  "nonce": "RANDOM_NONCE_PER_LOGIN",
  "amr": ["fido"]
}
~~~

Đây **chỉ là payload minh họa**, không có chữ ký và **không thể dùng để đăng nhập**. Bản JSON nhìn giống token hợp lệ chưa chứng minh điều gì nếu chưa kiểm chứng giao thức.

**Định danh subject:** Thường dùng cặp **`(iss, sub)`** để ánh xạ người dùng trong OIDC. Không coi email, họ tên hoặc ảnh đại diện là khóa định danh bất biến; các thuộc tính này có thể đổi, không duy nhất hoặc chưa được xác minh theo cách ứng dụng mong đợi.

### 4.6. Access token dùng cho API, không thay thế ID token

| Loại | Được dùng để | Không được mặc định dùng để |
|---|---|---|
| **Authorization code** | Đổi token trong một giao dịch được bảo vệ | Truy cập API trực tiếp |
| **ID token** | RP kiểm chứng thông tin sự kiện xác thực và subject | Làm bearer token gọi API chỉ vì có `sub` |
| **Access token** | Truy cập resource server theo audience/scope/quy tắc | Chứng minh đầy đủ danh tính người dùng trước mọi ứng dụng |
| **Refresh token** | Xin token mới khi client có quyền và chính sách cho phép | Giữ phiên vô thời hạn hoặc chia sẻ cho nhiều ứng dụng |
| **Session cookie** | Duy trì phiên của một ứng dụng | Quyền vượt qua kiểm tra authorization hiện hành |

API phải xác thực access token **đúng loại, đúng issuer, đúng audience, còn hiệu lực** và áp chính sách authorization ở endpoint/tài nguyên. Access token có thể là JWT hoặc token opaque tùy kiến trúc; không suy đoán mọi token đều có thể giải mã tại client.

## 5. Authentication, SSO và quyền ứng dụng là các tầng riêng

Giả sử Minh đã đăng nhập thành công tại IdP. Ứng dụng CRM có thể gặp ba tình huống:

1. **Đã có account và đủ quyền:** CRM ánh xạ subject tới account, xác nhận role/phạm vi và cho phép hành động.
2. **Chưa có account CRM:** IdP xác thực thành công nhưng SCIM/API chưa tạo user, hoặc JIT provisioning không được phép/không thành công. Đây là lỗi **provisioning hoặc account mapping**, không phải lỗi mật khẩu.
3. **Có account nhưng thiếu quyền:** CRM nhận diện Minh đúng nhưng không cho mở dữ liệu vùng khác. Đây là quyết định **authorization** theo RBAC/ABAC.

Do đó:

~~~text
Identity proofing -> Identity / account
                           |
                           v
                    Authentication
                           |
                           v
                   Federation / SSO
                           |
                           v
                    App session
                           |
                           v
              Authorization tại API
               RBAC + ABAC + policy
                           |
                           v
                  Hành động hợp lệ
~~~

Cần giữ **thông báo trạng thái riêng** cho các lỗi khác nhau. Nếu người dùng đã qua SSO nhưng CRM chưa có account, không nên yêu cầu họ đổi mật khẩu như biện pháp mặc định.

## 6. Các phương thức xác thực và vai trò của MFA

**Authenticator** là yếu tố/phương thức giúp người dùng chứng minh quyền kiểm soát danh tính đã được gắn với tài khoản. **Multi-Factor Authentication (MFA)** sử dụng nhiều yếu tố thuộc các nhóm độc lập theo tiêu chí bảo đảm đã áp dụng; việc nhập hai lần cùng một mật khẩu không phải MFA.

| Nhóm yếu tố | Ví dụ | Rủi ro/giới hạn |
|---|---|---|
| **Something you know** | Mật khẩu, PIN trong ngữ cảnh phù hợp | Dễ bị lừa đảo, tái sử dụng hoặc lộ |
| **Something you have** | Khóa bảo mật, thiết bị giữ khóa mật mã, ứng dụng xác thực | Có thể mất hoặc bị chiếm thiết bị; mức chống phishing khác nhau |
| **Something you are** | Sinh trắc dùng để mở khóa authenticator phù hợp | Sai số, quyền riêng tư; thường không phải credential gửi trực tiếp tới máy chủ |

Một passkey dùng **WebAuthn/FIDO2** có thể kết hợp khóa riêng trên thiết bị với xác minh người dùng tại thiết bị (PIN/sinh trắc theo cơ chế authenticator), và hỗ trợ xác thực chống lừa đảo nhờ ràng buộc với nguồn gốc (*origin*). Cần đánh giá loại passkey, bảo vệ thiết bị và chính sách đồng bộ/khôi phục; không mặc định mọi phương thức trên thị trường có cùng mức bảo đảm.

### 6.1. MFA và chống phishing

Không phải mọi hình thức MFA chống phishing như nhau:

- **Passkey/FIDO2/WebAuthn** có đặc tính ràng buộc với origin và thử thách mật mã, thường giúp giảm nguy cơ nhập mã vào trang giả.
- **TOTP** là mã dùng một lần theo thời gian, có thể vẫn bị lừa người dùng nhập vào trang giả hoặc relay.
- **SMS OTP** có rủi ro liên quan chuyển số, SIM-swap, chiếm kênh và phishing; mức phù hợp tùy yêu cầu.
- **Push notification** có thể bị tấn công bằng gửi liên tục hoặc lừa người dùng xác nhận; những cơ chế ràng buộc/ngữ cảnh xác nhận có thể giảm rủi ro tùy triển khai.

**Chọn phương thức theo mức bảo đảm và rủi ro**, không chỉ theo số lần người dùng phải thao tác. Cần xem xét khả năng tiếp cận, thiết bị, quy trình mất authenticator và trách nhiệm hỗ trợ.

### 6.2. Khi nào yêu cầu step-up?

**Step-up authentication** yêu cầu bằng chứng xác thực bổ sung hoặc mới hơn trước khi làm hành động nhạy cảm. Ví dụ:

- Đăng nhập từ thiết bị chưa được quản lý hoặc ngữ cảnh rủi ro cao.
- Truy cập dữ liệu tài chính đặc biệt nhạy cảm.
- Thay đổi authenticator, thông tin khôi phục hoặc mật khẩu.
- Cấp/thu hồi đặc quyền, tạo credential dài hạn.
- Thực hiện thao tác production hoặc phê duyệt nghiệp vụ rủi ro cao.

Step-up **không tự cấp quyền**. Người dùng phải vừa đáp ứng yêu cầu xác thực tăng cường, vừa **có entitlement hợp lệ** cho hành động đó.

## 7. Session management sau khi đăng nhập

Sau khi hoàn thành authentication, ứng dụng thường tạo một **local session** gắn với subject, trạng thái xác thực và ngữ cảnh phù hợp. Session có thể tồn tại độc lập với cookie đăng nhập của IdP.

### 7.1. Cookie phiên cho ứng dụng web

Với ứng dụng web, cách phổ biến là dùng cookie phiên do máy chủ quản lý. Những thuộc tính bảo vệ cần xem xét:

- `Secure`: Cookie chỉ được gửi qua kết nối bảo vệ phù hợp.
- `HttpOnly`: Hạn chế mã JavaScript truy cập cookie; không thay thế chống XSS.
- `SameSite`: Hỗ trợ giảm một số nguy cơ cross-site request; vẫn cần bảo vệ CSRF khi áp dụng.
- Giới hạn `Path`/`Domain`, thời hạn và phạm vi cookie hợp lý.
- Tái tạo/luân chuyển session identifier khi chuyển từ chưa xác thực sang đã xác thực để giảm rủi ro **session fixation**.
- Hủy phiên phía server khi logout/thu hồi, nếu kiến trúc hỗ trợ.

Không nên dùng `localStorage` như lựa chọn mặc định để lưu các token nhạy cảm của ứng dụng web nếu kiến trúc có giải pháp bảo vệ tốt hơn. Thiết kế lưu token phải xét XSS, CSRF, hệ điều hành và mô hình client.

### 7.2. Timeout và độ mới của xác thực

Chính sách có thể quy định:

- **Idle timeout:** Phiên hết hiệu lực khi không hoạt động đủ lâu.
- **Absolute timeout:** Phiên hết hiệu lực sau một khoảng thời gian tối đa kể cả đang hoạt động.
- **Reauthentication:** Yêu cầu xác thực lại khi đã quá lâu hoặc trước hành động nhạy cảm.
- **Session concurrency và device policy:** Quản lý các phiên song song hoặc thiết bị theo rủi ro.

Không có một ngưỡng timeout duy nhất cho mọi tổ chức. Cần cân bằng tính nhạy cảm tài nguyên, rủi ro thiết bị dùng chung, khả năng phục hồi và trải nghiệm người dùng.

### 7.3. Logout không phải lúc nào cũng thu hồi toàn bộ

Người dùng bấm logout ở một ứng dụng có thể chỉ xóa **phiên của ứng dụng đó**, trong khi phiên tại IdP và ứng dụng khác vẫn tồn tại. Một số giao thức hỗ trợ luồng logout liên kết nhưng khả năng, phạm vi và tính tức thời tùy nền tảng.

Khi Leaver, **“logout một lần” không thể được dùng thay thế quá trình thu hồi quyền**. Phải xét tài khoản, phiên, refresh token, access token còn sống, personal token và API key liên quan.

## 8. SAML authentication flow: điểm khác với OIDC

Không phải ứng dụng doanh nghiệp nào cũng hỗ trợ OIDC. **SAML 2.0** phổ biến trong một số hệ thống SSO và dùng các thông điệp/assertion XML theo profile được cấu hình.

Một luồng **SP-initiated SAML** khái niệm:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant SP as Service Provider (ứng dụng)
    participant IDP as SAML IdP

    U->>B: Mở ứng dụng
    B->>SP: Yêu cầu tài nguyên
    SP-->>B: Chuyển hướng với AuthnRequest
    B->>IDP: Gửi yêu cầu xác thực
    IDP->>U: Xác thực / MFA nếu cần
    IDP-->>B: SAML Response
    B->>SP: Gửi Response đến ACS
    SP->>SP: Kiểm tra chữ ký, issuer, condition,\nrecipient, audience, request correlation
    SP-->>B: Thiết lập local session nếu hợp lệ
~~~

Ở SAML, **Service Provider (SP)** không nên tin assertion chỉ vì XML có tên người dùng hợp lý. Cần kiểm chứng chữ ký và vị trí phần tử được ký theo thư viện an toàn, issuer, audience, recipient/destination, thời gian `NotBefore`/`NotOnOrAfter`, `InResponseTo` khi áp dụng, khả năng chống replay và cách ánh xạ subject phù hợp.

So sánh ngắn:

| Nội dung | OIDC | SAML |
|---|---|---|
| Mục tiêu tiêu biểu | Đăng nhập dựa trên giao thức web hiện đại; gắn với OAuth 2.0 | SSO doanh nghiệp qua assertion |
| Thông điệp định danh | ID token và claim theo quy tắc OIDC | SAML assertion trong Response |
| Đường callback | Redirect URI của client | Assertion Consumer Service (ACS) của SP |
| Kiểm tra quan trọng | `iss`, `aud`, chữ ký, thời gian, `nonce` khi áp dụng, trạng thái giao dịch | Chữ ký, issuer, audience, recipient, thời gian, correlation và replay |
| Phiên ứng dụng | Ứng dụng tự quản lý | SP tự quản lý |
| Tạo account ứng dụng | SCIM/API hoặc JIT nếu được hỗ trợ | SCIM/API hoặc JIT nếu được hỗ trợ |

**Cả OIDC và SAML đều không tự giải quyết toàn bộ provisioning, deprovisioning hoặc authorization.** Chọn giao thức phải dựa vào hệ thống tích hợp và chính sách, sử dụng thư viện đã được kiểm chứng.

## 9. Conditional access và quyết định xác thực theo ngữ cảnh

Một IdP có thể yêu cầu MFA bổ sung hoặc chặn đăng nhập dựa trên:

- Trạng thái tài khoản từ nguồn IAM/HR.
- Thiết bị được quản lý hoặc mức tin cậy thiết bị.
- Phương thức xác thực sẵn có và mức bảo đảm cần đạt.
- Dấu hiệu hoạt động bất thường: tốc độ đăng nhập, thay đổi phiên, rủi ro credential.
- Địa chỉ IP, mạng và thông tin địa lý suy luận được.
- Độ nhạy của ứng dụng và hành động.
- Chính sách thời gian hoặc mức đặc quyền của vai trò.

**Địa điểm làm việc chính thức** (do HR hoặc quy trình công việc xác nhận) khác **vị trí suy ra từ IP của phiên**. VPN, proxy và sai số định vị có thể tạo tín hiệu sai. Không nên tự sửa `workLocation` hay quyền dữ liệu khu vực chỉ vì người dùng đang kết nối từ mạng khác.

Một luồng đơn giản:

~~~mermaid
flowchart TD
    A["Authentication request"] --> B{"Account/engagement<br/>còn hợp lệ?"}
    B -->|Không| X["Từ chối và ghi vết"]
    B -->|Có| C["Đánh giá phương thức và<br/>chính sách ngữ cảnh"]
    C --> D{"Đã đáp ứng yêu cầu<br/>xác thực?"}
    D -->|Chưa| E["Yêu cầu MFA / step-up<br/>hoặc phương án phù hợp"]
    E --> F{"Thành công?"}
    F -->|Không| X
    F -->|Có| G["Kết quả authentication hợp lệ"]
    D -->|Có| G
    G --> H["Ứng dụng kiểm chứng kết quả"]
    H --> I["Kiểm tra authorization<br/>RBAC/ABAC tại tài nguyên"]
    I --> J{"Có quyền?"}
    J -->|Có| K["Cho phép trong phạm vi"]
    J -->|Không| Y["Từ chối hành động"]
~~~

Đừng xem phép thử rủi ro hoặc MFA là sự thay thế cho kiểm tra **role, thuộc tính, phân tách nhiệm vụ và trạng thái JML** ở ứng dụng.

## 10. Authentication flow trong Joiner–Mover–Leaver

### 10.1. Joiner: tạo account và đăng ký phương thức xác thực

Quy trình một nhân viên mới có thể gồm:

1. HR hoặc nguồn có thẩm quyền phát biến cố Joiner đã được phê duyệt.
2. IAM xác nhận danh tính đã được proofing theo chính sách, liên kết identity ổn định.
3. Account được tạo trong IdP, gắn trạng thái và mốc hiệu lực đúng.
4. Người dùng kích hoạt account qua kênh được bảo vệ, đăng ký passkey/khóa bảo mật hoặc MFA phù hợp.
5. Ứng dụng nhận account/nhóm qua SCIM/API hoặc cơ chế tích hợp khác.
6. Tại mốc hiệu lực, người dùng thực hiện authentication flow.
7. Ứng dụng kiểm chứng token/assertion và áp authorization theo quyền đã được phê duyệt.

Nếu tạo account trước ngày bắt đầu, hệ thống có thể cho phép một số thao tác kích hoạt theo chính sách, nhưng **không được vô tình mở quyền vào tài nguyên công việc trước thời điểm hợp lệ**.

### 10.2. Mover: vai trò thay đổi dù subject không đổi

Ví dụ, một người chuyển từ Sales sang Finance. `sub` tại IdP có thể giữ nguyên, nên người dùng **vẫn xác thực thành công** với cùng authenticator. Điều đó không có nghĩa mọi quyền Sales cũ được tiếp tục sử dụng.

IAM cần cập nhật nhóm/thuộc tính và quyền hiệu dụng; ứng dụng kiểm tra quyền ở các request tiếp theo. Cần đánh giá **token/phiên có claim cũ, cache role, quyền trực tiếp và thời gian cập nhật**, nhất là khi bỏ quyền nhạy cảm.

Nếu vai trò mới có quyền đặc biệt, tổ chức có thể yêu cầu step-up hoặc enrollment phương thức mạnh hơn, nhưng quyền phải vẫn được cấp/kiểm tra riêng theo chính sách.

### 10.3. Leaver: dừng cả đăng nhập mới và truy cập còn tồn tại

Khi một người rời tổ chức hoặc hợp đồng hết hiệu lực, thường phải:

- Đánh dấu không còn điều kiện hợp lệ tại nguồn và hệ thống IAM.
- Vô hiệu hóa hoặc giới hạn account tại IdP theo chính sách.
- Thu hồi entitlement tại ứng dụng đích thông qua SCIM/API và quy trình thay thế.
- Xử lý phiên IdP, phiên ứng dụng, refresh token, personal token, API key và credential liên quan theo khả năng kỹ thuật.
- Đối soát **khả năng truy cập thực tế** ở các đích bắt buộc, thay vì chỉ nhìn trạng thái `disabled`.
- Ghi bằng chứng thời điểm và kết quả, theo dõi trường hợp lỗi đồng bộ hoặc quyền truy cập tồn dư.

**Đặc biệt:** Nếu access token tự chứa đã được phát hành và API chấp nhận nó đến lúc hết hạn mà không kiểm tra trạng thái mới, việc disable IdP hoặc thu hồi refresh token **có thể chưa vô hiệu hóa token đó ngay**. Chính sách cần định nghĩa giới hạn thời gian và biện pháp chặn phù hợp.

### 10.4. Rejoiner và khôi phục account

Một người quay lại tổ chức có thể còn identity và account cũ. IAM cần xác nhận **đúng chủ thể, quan hệ mới, trạng thái authenticator, recovery và entitlement** trước khi kích hoạt lại. Không được khôi phục vô điều kiện tất cả role, session hoặc token đã có trước lúc Leaver.

## 11. Authentication cho service account và workload

**Tài khoản dịch vụ (service account) và workload identity** không phải con người đăng nhập qua trình duyệt. Vì vậy, không nên buộc một tác vụ không tương tác sử dụng MFA push hay chia sẻ mật khẩu nhân viên.

Các mô hình có thể gặp:

| Mô hình | Ví dụ | Lưu ý IAM |
|---|---|---|
| **Workload identity / federation** | Job cloud lấy danh tính dựa trên môi trường chạy và quan hệ tin cậy | Xác thực workload, kiểm tra issuer/audience và phạm vi |
| **OAuth 2.0 Client Credentials** | Dịch vụ backend lấy access token để gọi API | Đây là ủy quyền client, không phải đăng nhập người dùng |
| **Mutual TLS / certificate** | Dịch vụ chứng minh quyền sở hữu khóa riêng | Quản lý vòng đời chứng thư, chủ sở hữu và revocation |
| **Managed identity của nền tảng** | Workload dùng identity do cloud quản lý | Tránh secret tĩnh nếu nền tảng cho phép |
| **API key/secret tĩnh** | Tích hợp legacy dùng khóa để gọi API | Có owner, giới hạn quyền, rotation và giám sát |

Ví dụ **client credentials**, diễn giải khái niệm:

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Workload / service
    participant T as Authorization Server
    participant A as API

    W->>T: Xác thực client, yêu cầu token theo grant được phép
    T->>T: Kiểm tra danh tính client, chính sách và phạm vi
    T-->>W: Access token cho audience/scope phù hợp
    W->>A: Gọi API với access token
    A->>A: Kiểm chứng token và policy của workload
    A-->>W: Phản hồi được phép hoặc từ chối
~~~

Không dùng kết quả này để khẳng định một **người cụ thể đã đăng nhập**. Mọi service account cần **workload ID, service owner, phạm vi quyền, thời hạn credential và quy trình thu hồi**. Khi người vận hành rời tổ chức, cần xem xét khả năng họ đã tiếp cận secret, chuyển quyền quản trị và xoay vòng/thu hồi credential theo rủi ro, nhưng **không xóa bừa account máy đang phục vụ production**.

## 12. Các lỗi thường gặp trong authentication flow

| Triệu chứng | Khả năng nguyên nhân | Hướng kiểm tra |
|---|---|---|
| Người dùng bị chuyển qua lại IdP và app liên tục | Cấu hình callback/cookie, session, clock, issuer hoặc policy lỗi | Giao dịch redirect, cookie, log IdP/RP, không tiết lộ token |
| `invalid_state` tại callback | Giao dịch bị mất, cookie phiên không nhất quán hoặc dấu hiệu CSRF | Liên kết request–response, scope cookie, xử lý nhiều tab |
| `invalid_grant` khi đổi code | Code hết hạn/đã dùng, verifier sai, redirect/client không khớp | Kiểm tra cấu hình PKCE, transaction và token request |
| Đăng nhập IdP được nhưng app báo chưa có user | Provisioning/SCIM hoặc account mapping lỗi | Kiểm tra user đích, `(iss,sub)` và trạng thái đồng bộ |
| ID token bị từ chối | Sai issuer/audience, chữ ký, thời gian hoặc nonce | Kiểm tra trust/configuration, không tắt validation |
| Người dùng bị hỏi MFA nhiều lần | Chính sách session, browser cookie, thay đổi ngữ cảnh | Phân tích nguyên nhân, không bỏ MFA vô điều kiện |
| Người dùng không còn thiết bị MFA | Mất authenticator | Luồng khôi phục có xác minh lại, thay credential cũ |
| Đăng nhập thành công nhưng API trả 403 | Thiếu entitlement hoặc điều kiện ABAC | Kiểm tra role, scope, tài nguyên và chính sách API |
| User chuyển bộ phận vẫn xem được dữ liệu cũ | Token/claim cache, nhóm cũ hoặc grant trực tiếp | Đối soát quyền hiệu dụng và session/token |
| User nghỉ việc vẫn dùng được API token | Token độc lập hoặc không bị chặn theo trạng thái mới | Revocation/status check, hạn token, kiểm chứng API |
| Service account thất bại sau đổi secret | Workload chưa nhận credential mới | Rotation plan, config, health check |
| SAML assertion bị từ chối | Audience, recipient, signature, clock hoặc correlation | Kiểm chứng profile, metadata và log an toàn |

**Phân biệt lỗi 401 và 403 theo thiết kế ứng dụng:** 401 thường biểu thị yêu cầu cần authentication/credentials hợp lệ; 403 thường thể hiện yêu cầu đã được hiểu nhưng không được phép. Không phải hệ thống nào cũng dùng thông báo hoàn toàn giống nhau, nên hãy kiểm tra trạng thái giao thức và log tương ứng.

### 12.1. Thông báo lỗi không tiết lộ dữ liệu không cần thiết

Trên bề mặt công khai, không nên trả về thông báo giúp phân biệt **email có tồn tại trong tổ chức** hoặc tiết lộ cấu trúc chính sách nội bộ. Với người đã xác thực và được phép xem, ứng dụng có thể cho biết **quyền đang chờ phê duyệt, account chưa provisioning hoặc cần liên hệ hỗ trợ** ở mức chi tiết phù hợp.

Không ghi mật khẩu, token nguyên văn, mã OTP hoặc bí mật client trong log. Đối với lỗi kỹ thuật, dùng **correlation ID**, loại lỗi, bước xử lý và thông tin không nhạy cảm để hỗ trợ truy vết.

## 13. Các mối đe dọa và kiểm soát theo từng bước

| Bước/đối tượng | Mối đe dọa | Kiểm soát thiết kế |
|---|---|---|
| Trang đăng nhập | Phishing, giả IdP, credential stuffing | IdP tin cậy, passkey/FIDO2 khi phù hợp, bảo vệ đăng nhập/rate limiting |
| Khởi tạo giao dịch | CSRF, login mix-up, open redirect | `state`, ràng buộc request, redirect URI đã đăng ký, issuer validation |
| Authorization code | Bị đánh cắp hoặc chèn code | PKCE, code ngắn hạn/dùng một lần, kiểm tra client/redirect |
| ID token | Token giả, sai issuer/audience, replay | Kiểm chữ ký, `iss`/`aud`/`exp`/`nonce` và kiểm tra giao thức |
| API access token | Dùng token sai audience hoặc quá hạn | Kiểm token đúng loại, audience, hiệu lực, scope và authorization |
| Session cookie | Session fixation, XSS, CSRF, đánh cắp session | Secure/HttpOnly/SameSite, session rotation, CSRF protection, CSP/XSS controls |
| MFA | OTP phishing, push fatigue, SIM swap | Chọn authenticator mạnh, confirmation context, bảo vệ recovery |
| Account recovery | Kẻ tấn công chiếm quy trình reset | Xác minh người yêu cầu, nhật ký và kiểm tra biến cố nhạy cảm |
| Provisioning | Đăng nhập được nhưng user đích cấp sai role | SCIM/API readback, mapping và least privilege |
| Leaver | Phiên/token còn sống hoặc tài khoản local chưa thu hồi | Deprovision đa hệ thống, revocation, đối soát quyền hiệu dụng |
| Workload | Secret dài hạn bị lấy từ code/log | Workload identity, secret manager, scope nhỏ, rotation và audit |

Không phải mọi rủi ro đều được chặn bởi một biện pháp duy nhất. Ví dụ **PKCE bảo vệ trao đổi authorization code**, nhưng **không thay thế kiểm tra ID token hay chống XSS** trong ứng dụng.

### 13.1. Chống replay và token misuse

Authorization code chỉ dành cho một giao dịch và có thời hạn ngắn. ID token và access token phải được xử lý theo loại, audience và kênh phù hợp. Với token có thể bị đánh cắp, kiểm soát bổ sung như thời hạn hợp lý, revocation/status checks hoặc proof-of-possession khi được nền tảng hỗ trợ có thể giúp giảm rủi ro.

Không đưa token vào URL, log hoặc công cụ phân tích nếu không có lý do được kiểm soát. Không hiển thị token đầy đủ cho người dùng cuối khi lỗi xác thực.

### 13.2. Đừng bỏ qua quyền ở resource server

Một API nhận access token hợp lệ **vẫn phải quyết định request cụ thể có được phép**. Ví dụ, scope `reports.read` có thể là một điều kiện nhưng chưa đủ để xem **báo cáo của vùng khác**. API phải dùng RBAC/ABAC và nguồn dữ liệu đáng tin cậy để kiểm tra phạm vi thực tế.

## 14. Minh họa xử lý callback an toàn bằng mã giả

Ví dụ dưới đây **không phải thư viện xác thực hoàn chỉnh**. Các hàm giả định đại diện cho các thành phần đã được kiểm chứng; mục đích là chỉ ra **thứ tự kiểm soát**, không khuyến khích tự viết mật mã.

~~~python
def oidc_callback(request, transaction_store, oidc_client, iam):
    # Giao dịch phải được khởi tạo và lưu an toàn từ trước.
    tx = transaction_store.get_for_current_browser_session()

    if tx is None or tx.is_expired:
        return deny("LOGIN_TRANSACTION_NOT_FOUND")

    if not constant_time_equals(request.query.state, tx.state):
        return deny("INVALID_STATE")

    if request.query.error:
        return handle_authentication_error_safely(request.query.error)

    if not request.query.code:
        return deny("MISSING_AUTHORIZATION_CODE")

    tokens = oidc_client.exchange_code(
        code=request.query.code,
        redirect_uri=tx.registered_redirect_uri,
        code_verifier=tx.code_verifier
    )

    # validate_id_token thực hiện đầy đủ kiểm chứng OIDC:
    # chữ ký, issuer, audience, thời gian, nonce và điều kiện liên quan.
    claims = oidc_client.validate_id_token(
        tokens.id_token,
        expected_nonce=tx.nonce
    )

    # Không ánh xạ account chỉ bằng email hoặc display name.
    user = iam.find_identity_by_issuer_and_subject(
        issuer=claims.iss,
        subject=claims.sub
    )

    if user is None or not iam.is_login_allowed_now(user):
        return deny("ACCOUNT_NOT_ELIGIBLE")

    transaction_store.consume(tx)
    session = create_new_protected_application_session(user.id)

    return redirect_to_internal_allowed_destination(session)
~~~

Những kiểm tra còn thiếu trong ví dụ thực tế có thể bao gồm **xác thực client, xác minh luồng và anti-mix-up, an toàn endpoint discovery/redirect, transaction storage, giới hạn thời gian, xử lý ngoại lệ, cookie/CSRF, đăng nhập nhiều tab và chính sách mức xác thực**. Thư viện chuẩn đã kiểm tra nên chịu trách nhiệm các quy tắc giao thức phức tạp.

**Điểm đáng chú ý:** `find_identity_by_issuer_and_subject` giúp liên kết đúng subject, còn `is_login_allowed_now` thể hiện trạng thái IAM/JML. Hai bước này khác với việc **kiểm tra entitlement cho từng thao tác tại API** sau khi phiên được tạo.

## 15. Kịch bản thực hành: nhân viên chuyển bộ phận nhưng giữ phiên cũ

**Bối cảnh:** Thu đang làm Sales, có quyền xem dữ liệu khách hàng miền Bắc. Ngày 01/10, Thu chuyển sang Finance. HR đã cập nhật vai trò, IdP đã đổi nhóm. Thu vẫn đang mở một tab báo cáo từ tuần trước và có access token còn thời hạn.

### Nếu hệ thống chỉ kiểm tra khi login

Thu có thể tiếp tục nhìn dữ liệu Sales cũ cho đến khi phiên/token hết hạn, nếu ứng dụng chỉ tin claim đã cấp ở lần đăng nhập cũ. Tình huống này tạo ra **quyền tồn dư sau Mover**, dù sự kiện HR và nhóm IdP đã đúng.

### Thiết kế phù hợp

1. IAM tính lại quyền theo vai trò Finance và thu hồi quyền Sales không còn hợp lệ.
2. IdP/SCIM/API đồng bộ nhóm và account tới ứng dụng; lỗi được theo dõi.
3. Ứng dụng/API áp chính sách authorization hiện hành với mỗi hành động cần bảo vệ; có cách làm mới hoặc vô hiệu hóa cache entitlement theo giới hạn rủi ro.
4. Với quyền nhạy cảm, tổ chức có thể yêu cầu session refresh/revocation hoặc kiểm tra trạng thái tài khoản, không mặc định đợi token tự hết hạn nếu quá giới hạn chính sách.
5. Thu chỉ được xem dữ liệu Finance theo nhiệm vụ, không được giữ quyền Sales do phiên cũ.
6. Hệ thống ghi log biến cố Mover, quyền thêm/thu hồi và bằng chứng đối soát tại ứng dụng.

**Bài học:** Authentication flow có thể vẫn hợp lệ cho một chủ thể, trong khi **authorization đã thay đổi**. Đừng gắn mọi quyền vào một lần xác thực rồi coi đó là quyền vĩnh viễn.

## 16. Kịch bản thực hành: Leaver với phiên và token tồn dư

**Bối cảnh:** Bình, nhà thầu của dự án A, kết thúc hợp đồng lúc 18:00. IAM disable IdP đúng giờ. Tuy nhiên, Bình còn một phiên ứng dụng quản lý mã nguồn và một personal access token truy cập API.

Một kế hoạch xử lý hợp lệ cần:

1. Xác nhận sự kiện Leaver đến từ nguồn hợp đồng/sponsor có thẩm quyền, đúng identity và mốc hiệu lực.
2. Xác định mọi account đích, nhóm/role và direct grants liên quan đến engagement A.
3. Vô hiệu hóa account/thu hồi entitlement qua IdP, SCIM/API và hệ thống không tích hợp trực tiếp.
4. Xử lý local session và personal access token theo khả năng hệ thống; xác định **thời gian token còn sống** và giới hạn rủi ro.
5. Kiểm tra quyền ở repository và API, không chỉ xem trường `active=false` trong IdP.
6. Đối soát readback, ghi kết quả/ngoại lệ và chỉ đóng Leaver khi các tiêu chí bắt buộc đã đạt.

Nếu Bình còn engagement B hợp lệ, IAM phải xác định **quyền nào thuộc A, quyền nào thuộc B**. Không tự xóa mọi quyền B chỉ vì kết thúc dự án A; cũng không giữ quyền A vì account tổng thể vẫn hoạt động.

## 17. Khả năng quan sát và kiểm toán authentication flow

Một sự kiện đăng nhập nên hỗ trợ điều tra, vận hành và chứng minh chính sách đã được thực thi, nhưng **không làm lộ bí mật**.

| Nhóm thông tin | Ví dụ nên lưu | Không nên lưu |
|---|---|---|
| **Giao dịch** | Correlation ID, thời điểm, client ID, kết quả | Authorization code, access token nguyên văn |
| **Chủ thể** | ID nội bộ, issuer/subject được quản lý phù hợp | Dữ liệu giấy tờ thô nếu không cần |
| **Phương thức** | Loại xác thực hoặc mức bảo đảm theo chính sách | OTP, PIN, mật khẩu, khóa bí mật |
| **Chính sách** | Quyết định MFA/step-up, lý do ở mức phù hợp | Chi tiết nhạy cảm làm lộ logic phòng vệ |
| **Phiên** | Session ID tham chiếu đã bảo vệ/hash và trạng thái | Cookie phiên sử dụng được |
| **Ứng dụng** | Thành công/thất bại, mapping và lỗi provisioning | Client secret, refresh token nguyên văn |
| **JML** | Account active/disabled, biến cố liên quan, mốc hiệu lực | Sao chép toàn bộ hồ sơ HR |
| **Authorization** | Tài nguyên/hành động, quyết định cho phép/từ chối, policy version | Dữ liệu nghiệp vụ nhạy cảm không cần cho log |

### 17.1. Các chỉ số gợi ý

- **Authentication success rate:** Tỷ lệ yêu cầu hợp lệ được hoàn thành; phân tích theo phương thức, ứng dụng và nguyên nhân thất bại.
- **MFA/step-up completion rate:** Tỷ lệ người dùng hoàn thành kiểm soát theo chính sách mà không phải bỏ qua yếu tố bắt buộc.
- **Time to authenticate:** Đo thời gian trải nghiệm, nhưng tách độ trễ IdP, ứng dụng, mạng và người dùng.
- **Account-provisioning mismatch:** Đăng nhập IdP thành công nhưng ứng dụng không có account hoặc mapping.
- **Session/revocation lag:** Thời gian từ biến cố thu hồi đến khi phiên/token không còn cho phép truy cập theo phạm vi.
- **Failed or risky authentication:** Phân tích tín hiệu đáng ngờ và sai báo động, tránh đánh giá theo số sự kiện thô.
- **JML authentication exceptions:** Joiner chưa đủ điều kiện nhưng được đăng nhập, Mover còn role cũ, Leaver có đường truy cập tồn dư.

Không đặt một **SLA hoặc mức MFA chung** cho mọi ứng dụng mà không xét rủi ro và chính sách. Các chỉ số về trải nghiệm phải được đọc cùng các chỉ số **quyền thực tế, kiểm toán và thu hồi**.

## 18. Bài tập tự kiểm tra

### Câu 1 — OIDC xác thực thành công nhưng API trả 403

Người dùng hoàn thành passkey, ứng dụng kiểm chứng ID token hợp lệ, nhưng API báo cáo trả 403.

**Vì sao?** Đăng nhập chứng minh phiên thuộc một subject, nhưng API cần kiểm tra **access token dành cho API và quyền nghiệp vụ** theo RBAC/ABAC. Có thể user chưa được cấp role/phạm vi dữ liệu; không tự coi 403 là lỗi passkey.

### Câu 2 — Nhận code mà không kiểm tra `state`

Một ứng dụng nhận callback chứa authorization code và lập tức đổi token, không kiểm tra giao dịch đã khởi tạo.

**Rủi ro gì?** Có thể phá vỡ liên kết request–response, tạo nguy cơ CSRF/login injection hoặc mix-up tùy cấu hình. Cần xử lý `state` và các biện pháp ràng buộc giao dịch/giao thức theo thư viện đã kiểm chứng.

### Câu 3 — Thay `aud` cho đúng “bằng cách bỏ kiểm tra”

ID token do một IdP phát cho `client-A`, nhưng ứng dụng `client-B` từ chối vì audience không đúng. Người vận hành đề nghị tắt validation.

**Có nên không?** Không. Audience xác định client nhận token; bỏ kiểm tra có thể tạo token substitution. Cần sửa cấu hình client/giao thức và tái kiểm tra, không hạ cấp an toàn.

### Câu 4 — User chuyển vai trò vẫn giữ quyền cũ

HR và IdP đã cập nhật vai trò, nhưng người dùng mở tab cũ vẫn xem dữ liệu trước đây.

**Cần kiểm tra gì?** Quyền hiệu dụng ứng dụng, cache nhóm/claim, access token và session, direct grants, cách API áp RBAC/ABAC và giới hạn thu hồi đã định.

### Câu 5 — Disable IdP là đủ khi Leaver?

Nhân viên đã disabled ở IdP, nhưng app có local session và personal token chưa hết hạn.

**Kết luận?** Chưa đủ. Cần kiểm tra khả năng truy cập và xử lý các đường phiên/token/credential nằm trong phạm vi Leaver, readback ở ứng dụng.

### Câu 6 — Backend job có nên đăng nhập bằng tài khoản người dùng?

Một job đêm cần gọi API nhưng đội vận hành muốn lưu mật khẩu nhân viên vào cấu hình.

**Lựa chọn phù hợp hơn?** Dùng danh tính workload/service account với owner rõ ràng và cơ chế máy đến máy như client credentials, managed/workload identity hoặc cơ chế nền tảng; bảo vệ và giới hạn quyền, không chia sẻ password người dùng.

### Câu 7 — Passkey có thay thế hoàn toàn authorization không?

Một người dùng đăng nhập bằng passkey có xác thực mạnh. Họ có được xem tất cả bảng dữ liệu không?

**Kết luận?** Không. Mức xác thực mạnh hỗ trợ tin vào người đang đăng nhập; **quyền dữ liệu vẫn do RBAC/ABAC, điều kiện và trạng thái JML quyết định**.

## 19. Checklist thiết kế và kiểm tra authentication flow

- [ ] **Nguồn danh tính:** Identity đã được xác minh đủ mức cần thiết và liên kết đúng account?
- [ ] **Trạng thái JML:** Account/engagement còn hiệu lực; Joiner chưa đến hạn hoặc Leaver không được mở truy cập trái chính sách?
- [ ] **Giao thức:** OIDC/SAML được cấu hình đúng trust boundary, issuer, client, redirect/ACS, thuật toán và thư viện phù hợp?
- [ ] **Luồng giao dịch:** `state`, `nonce`, PKCE và correlation được xử lý khi áp dụng; code không bị dùng làm token phiên?
- [ ] **Kiểm chứng kết quả:** Chữ ký, issuer, audience, thời gian, request correlation và quy tắc token/assertion được kiểm tra?
- [ ] **Subject mapping:** Dùng định danh ổn định (ví dụ `iss` + `sub`), không tự liên kết chỉ theo email?
- [ ] **MFA:** Chính sách chọn phương thức đúng mức rủi ro; có khả năng step-up và khôi phục an toàn?
- [ ] **Session:** Cookie/phiên được bảo vệ; timeout, logout, reauthentication, session fixation và CSRF được xét?
- [ ] **API:** Resource server kiểm tra access token đúng đối tượng rồi thực thi RBAC/ABAC cho từng hành động?
- [ ] **Provisioning:** IdP đăng nhập được nhưng account/nhóm ứng dụng chưa có thì báo đúng lỗi; SCIM/API có readback?
- [ ] **Mover:** Quyền/claim cũ, cache và phiên có được xử lý khi vai trò, dự án hoặc site thay đổi?
- [ ] **Leaver:** Các đường đăng nhập, phiên, token và credential liên quan được chặn/thu hồi theo phạm vi và giới hạn thời gian?
- [ ] **Service account:** Workload không dùng mật khẩu người; có owner, identity riêng, quyền tối thiểu và vòng đời credential?
- [ ] **Kiểm toán:** Có correlation ID, quyết định, thời điểm, phương thức và log an toàn nhưng không chứa secret?
- [ ] **Trải nghiệm:** Người dùng biết bước tiếp theo khi MFA thất bại, account chưa được cấp hoặc quyền ứng dụng bị từ chối?
- [ ] **Bằng chứng cuối:** Kết quả đăng nhập và quyền truy cập thực tế đã được kiểm chứng ở những hệ thống cần thiết?

**Ghi nhớ:** **Authentication flow** là quá trình chứng minh quyền kiểm soát danh tính trong một lần đăng nhập và tạo cơ sở tin cậy cho phiên ứng dụng. Một luồng IAM đáng tin cậy phải **kiểm chứng thông điệp OIDC/SAML, áp chính sách xác thực phù hợp, bảo vệ phiên/token và liên kết đúng identity–account**. Đồng thời, hệ thống phải tiếp tục kiểm tra **authorization theo RBAC/ABAC** và phản ứng với biến cố **Joiner–Mover–Leaver**, để tài khoản hợp lệ truy cập đúng nhiệm vụ và quyền cũ không kéo dài sau khi vai trò hoặc quan hệ làm việc kết thúc.
