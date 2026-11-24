# SSO và MFA: kết hợp đăng nhập một lần với xác thực đa yếu tố trong vòng đời danh tính IAM

## 1. Tại sao cần học SSO và MFA cùng nhau?

**Single Sign-On (SSO)** cho phép người dùng xác thực thông qua một nhà cung cấp danh tính đáng tin cậy rồi sử dụng kết quả xác thực để truy cập nhiều ứng dụng mà không phải nhập lại thông tin đăng nhập ở từng ứng dụng. **Multi-Factor Authentication (MFA)** yêu cầu bằng chứng xác thực từ ít nhất hai yếu tố độc lập theo thiết kế, nhằm giảm khả năng người khác đăng nhập chỉ vì biết một bí mật như mật khẩu.

Hai khái niệm **bổ trợ nhưng không tương đương**:

- **SSO** trả lời: *Ứng dụng nào được tin vào kết quả xác thực từ đâu, và phiên đăng nhập được dùng lại như thế nào?*
- **MFA** trả lời: *Chủ thể phải chứng minh quyền kiểm soát danh tính bằng những yếu tố nào, với mức bảo đảm nào?*
- **Authorization** trả lời: *Sau khi xác thực, chủ thể được thực hiện hành động nào trên tài nguyên nào?*

Ví dụ, Hà đăng nhập vào cổng doanh nghiệp qua Identity Provider (**IdP**) bằng passkey. Sau khi xác thực, Hà có thể vào email và nền tảng quản lý công việc thông qua SSO. Nhưng khi mở chức năng chuyển tiền hoặc quản lý khóa bí mật, ứng dụng có thể yêu cầu **xác thực tăng cường (step-up)** theo chính sách, ngay cả khi Hà đã có phiên SSO hợp lệ.

Một cấu hình SSO chỉ sử dụng mật khẩu không tự trở thành MFA. Ngược lại, một ứng dụng không tích hợp SSO vẫn có thể tự dùng MFA, nhưng tổ chức sẽ khó quản trị và đối soát một cách tập trung. Trong module quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, cả hai cần gắn với dữ liệu nhân sự, cấp phát tài khoản, rà soát quyền, vô hiệu hóa phiên và ngăn quyền truy cập tồn dư.

**Mục tiêu bài học:** hiểu kiến trúc SSO–MFA, các giao thức liên quan, vị trí áp dụng chính sách, điều kiện kiểm chứng mức xác thực, step-up, tình huống lỗi, vòng đời authenticator và cách xác minh hiệu lực thu hồi khi người dùng thay đổi hoặc kết thúc quan hệ làm việc.

## 2. Các thành phần cần phân biệt

| Thành phần | Vai trò | Không nên nhầm với |
| --- | --- | --- |
| **Human/workload identity** | Chủ thể được tổ chức quản trị | Tài khoản riêng của từng ứng dụng |
| **Identity Provider (IdP)** | Xác minh danh tính, quản lý phương thức xác thực và phát hành kết quả đăng nhập theo cấu hình | Nơi quyết định mọi quyền cục bộ trong ứng dụng |
| **Relying Party (RP)/Service Provider (SP)** | Ứng dụng dựa vào kết quả xác thực từ IdP | Thành phần luôn có quyền tin mọi claim do client đưa đến |
| **Authenticator** | Phương tiện chứng minh quyền kiểm soát danh tính: password, OTP, passkey, security key… | Access token hoặc session ứng dụng |
| **Authentication session** | Trạng thái xác thực duy trì tại IdP hoặc ứng dụng | Bản thân quyền truy cập vĩnh viễn |
| **Assertion/ID token** | Bằng chứng xác thực được IdP gửi tới ứng dụng theo giao thức phù hợp | OAuth access token dùng cho API |
| **Access token** | Credential để yêu cầu API/resource server xử lý truy cập | Bằng chứng đã thực hiện MFA ở thời điểm hiện tại |
| **IAM/IGA** | Quản lý vòng đời, liên kết danh tính, chính sách và phê duyệt quyền | Giao thức xác thực SSO |
| **SCIM/provisioning** | Đồng bộ user/group và trạng thái tài khoản tới ứng dụng hỗ trợ | Giao thức tự động đăng ký MFA hoặc hủy tất cả session/token |

Một người có thể có phiên hợp lệ tại IdP, phiên riêng tại ứng dụng A, một access token gọi API B và các quyền trong ứng dụng C. Những đối tượng này **không tự động cùng hết hiệu lực** khi một lớp thay đổi trạng thái.

## 3. Kiến trúc cơ bản: SSO dùng xác thực của IdP, MFA bảo vệ thời điểm xác thực

~~~mermaid
flowchart TD
    HR["HRIS / nguồn bảo trợ<br/>Quan hệ làm việc và ngày hiệu lực"] --> IAM["IAM/IGA<br/>Liên kết identity và chính sách JML"]
    IAM --> IDP["IdP<br/>Account, MFA policy, session SSO"]
    IAM --> GOV["Phê duyệt role và entitlement"]
    IDP --> AUTH["Authenticator<br/>Passkey, security key, OTP…"]
    IDP -->|"OIDC / SAML"| A["Ứng dụng A: RP/SP"]
    IDP -->|"OIDC / SAML"| B["Ứng dụng B: RP/SP"]
    IAM -->|"SCIM / API nếu hỗ trợ"| A
    IAM -->|"SCIM / API nếu hỗ trợ"| B
    GOV --> POL["RBAC / ABAC và policy engine"]
    A --> POL
    B --> POL
    POL --> RES["API / tài nguyên<br/>Kiểm tra quyền hiệu lực"]
    A --> REC["Đối soát account / session / entitlement"]
    B --> REC
    REC --> IAM
~~~

Ví dụ, người dùng đã hoàn thành MFA tại IdP khi truy cập ứng dụng A. Khi chuyển sang B, IdP có thể nhận ra phiên SSO đang hoạt động và phát hành kết quả xác thực mới **nếu các yêu cầu của B đã được đáp ứng**. Nếu B đòi mức bảo đảm cao hơn hoặc phiên quá cũ, IdP phải thực hiện bước xác thực cần thiết trước khi chấp nhận.

**SSO không bảo đảm mọi ứng dụng được bảo vệ bởi MFA theo cùng cách.** Điều đó phụ thuộc cấu hình tin cậy liên kết, chính sách IdP, yêu cầu của ứng dụng, mức xác thực đã đạt, thời điểm xác thực và các đường đăng nhập thay thế còn tồn tại.

## 4. Luồng OIDC: ứng dụng dựa vào kết quả xác thực từ IdP

**OpenID Connect (OIDC)** là lớp nhận dạng dựa trên OAuth 2.0, thường dùng để ứng dụng (RP) xác thực người dùng thông qua IdP/OpenID Provider. Với ứng dụng web, **Authorization Code Flow kết hợp PKCE** là một lựa chọn phổ biến tùy loại client và hướng dẫn nền tảng.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant RP as Ứng dụng / RP
    participant OP as OpenID Provider / IdP
    participant MFA as Authenticator
    U->>RP: Mở ứng dụng
    RP->>OP: Yêu cầu xác thực, scope và tham số bảo vệ
    OP->>OP: Kiểm tra phiên SSO và chính sách cho RP
    alt Cần xác thực/MFA bổ sung
        OP->>MFA: Tạo thử thách theo chính sách
        MFA-->>OP: Bằng chứng hợp lệ
    else Phiên hiện tại đáp ứng yêu cầu
        OP->>OP: Dùng lại trạng thái xác thực thích hợp
    end
    OP-->>RP: Authorization code qua redirect
    RP->>OP: Đổi code tại token endpoint với kiểm soát client/PKCE
    OP-->>RP: ID token và token khác theo grant
    RP->>RP: Kiểm tra issuer, audience, chữ ký, nonce/claims và session
    RP-->>U: Tạo phiên ứng dụng
    U->>RP: Yêu cầu tài nguyên
    RP->>RP: Kiểm tra quyền truy cập thực tế
~~~

Ứng dụng phải xác minh thông điệp và token theo yêu cầu giao thức: **issuer, audience, chữ ký, thời hạn, nonce khi áp dụng, state/chống CSRF, liên kết response với yêu cầu**. Không tin giá trị role, tên người dùng hoặc tổ chức do trình duyệt tự sửa trong request.

**ID token** thể hiện kết quả xác thực của người dùng đối với RP. **Access token** dùng để gọi resource server theo audience/scope và chính sách của API; không nên dùng ID token như access token. Việc nhận ID token hợp lệ cũng không đủ để kết luận người dùng được quyền xem mọi dữ liệu ứng dụng.

## 5. Luồng SAML: IdP và Service Provider

Trong **Security Assertion Markup Language (SAML)**, ứng dụng đóng vai **Service Provider (SP)**, IdP phát hành **SAML assertion/response** mang thông tin xác thực theo liên kết tin cậy đã cấu hình. Một luồng SP-initiated điển hình:

1. Người dùng truy cập SP, SP chuyển yêu cầu xác thực tới IdP.
2. IdP kiểm tra phiên và áp dụng chính sách xác thực/MFA.
3. IdP phát hành SAML Response chứa assertion theo cấu hình liên kết.
4. SP kiểm tra chữ ký theo cấu hình, issuer, audience, recipient/destination, thời hạn, InResponseTo khi áp dụng và điều kiện chống replay.
5. SP tạo session cục bộ và **tự thực thi authorization** đối với tài nguyên.

SAML có thể biểu diễn **Authentication Context** thông qua AuthnContextClassRef hoặc cơ chế liên quan, nhưng **ý nghĩa mức bảo đảm phải được hai bên thống nhất**. Một chuỗi AuthnContext không đủ chứng minh MFA đã được thực hiện theo tiêu chí mong muốn nếu IdP/SP không có hợp đồng cấu hình và kiểm chứng thích hợp.

Không đánh đồng **SAML Single Logout**, logout tại IdP và thu hồi tất cả phiên ứng dụng: khả năng thực thi và phạm vi kết thúc phiên phụ thuộc từng SP và triển khai.

## 6. MFA thực sự chứng minh điều gì?

Các yếu tố xác thực thường được phân loại thành:

| Yếu tố | Ví dụ | Điểm cần kiểm tra |
| --- | --- | --- |
| **Điều người dùng biết** | Mật khẩu, passphrase | Bí mật có bị lộ, tái sử dụng, phishing hoặc brute-force không |
| **Điều người dùng sở hữu** | Security key, thiết bị chứa khóa, thiết bị OTP | Binding đúng identity, trạng thái bị mất/thu hồi |
| **Đặc điểm của người dùng** | Vân tay, khuôn mặt dùng trong cơ chế phù hợp | Chống giả mạo và cách verifier xác nhận kết quả |

**MFA yêu cầu các factor phù hợp và độc lập**. Hai câu hỏi bí mật không trở thành MFA chỉ vì xuất hiện trên hai màn hình. Hai ứng dụng tạo OTP từ hai seed khác nhau cũng không mặc nhiên đại diện cho hai loại yếu tố.

Các phương thức thường gặp:

- **Password + TOTP:** phổ biến, nhưng OTP có thể bị phishing và chuyển tiếp theo thời gian thực.
- **Password + SMS/voice OTP:** dễ tiếp cận hơn trong một số môi trường, nhưng chịu rủi ro chuyển số, SIM swap và phishing.
- **Password + push approval:** có thể bị MFA fatigue/push bombing; number matching giúp giảm bấm nhầm nhưng không tự tạo khả năng chống phishing.
- **FIDO2/WebAuthn và passkey:** dùng khóa bất đối xứng và ràng buộc với RP/origin; có thể chống phishing khi verifier kiểm tra đầy đủ giao thức.
- **Smart card/certificate:** có thể phù hợp với những trường hợp yêu cầu kiểm soát khóa và thiết bị, tùy cấu hình PKI và chính sách.

**MFA không đồng nghĩa phishing-resistant MFA.** Nếu tài khoản quản trị cần chống phishing, chỉ có password + OTP không đủ căn cứ để công bố đã đạt yêu cầu.

## 7. Phishing-resistant authentication: WebAuthn và passkeys

Với **WebAuthn**, authenticator giữ khóa riêng; RP lưu khóa công khai được liên kết với credential. Trong phiên đăng nhập, authenticator ký challenge và dữ liệu ngữ cảnh, còn RP xác minh **challenge, RP ID, origin, chữ ký, credential ID và trạng thái liên quan**. Trang giả mạo ở origin khác không thể tự lấy bằng chứng hợp lệ cho RP thật nếu các điều kiện được kiểm tra đúng.

**Passkey** là cách triển khai credential WebAuthn thân thiện với người dùng, có thể **ràng buộc thiết bị** hoặc **được đồng bộ** tùy authenticator/nền tảng. Khả năng đồng bộ, quản lý thiết bị, user verification và khôi phục cần được đánh giá theo chính sách của tổ chức.

Hai cờ cần phân biệt:

- **User presence (UP):** có tín hiệu người dùng tương tác với authenticator.
- **User verification (UV):** authenticator xác minh người dùng cục bộ, có thể bằng PIN hoặc sinh trắc học.

UP **không tự đồng nghĩa** UV. Một lần WebAuthn dùng quyền sở hữu khóa nhưng không yêu cầu UV không nên mặc định được gán nhãn đã thực hiện MFA nhiều yếu tố. Phải đánh giá loại authenticator, điều kiện UV và cách verifier kiểm tra.

WebAuthn giảm rủi ro phishing nhưng **không tự thu hồi phiên/token khi nhân viên nghỉ việc**, cũng không thay thế kiểm soát RBAC/ABAC hay quy trình khôi phục an toàn.

## 8. Làm thế nào ứng dụng biết mức xác thực từ SSO?

Ứng dụng cần phân biệt **“IdP đã xác thực ai?”** với **“IdP đã xác thực bằng phương thức nào, khi nào, và đã đủ mức bảo đảm cho hành động này chưa?”**.

Với OIDC, tùy IdP và hợp đồng tích hợp, những tín hiệu có thể bao gồm:

| Tín hiệu | Thông tin thường thể hiện | Cần cẩn trọng |
| --- | --- | --- |
| **sub** | Định danh chủ thể tại issuer | Phải xét cả issuer; không đồng nghĩa email |
| **iss / aud** | Nguồn phát hành và đối tượng nhận token | Cần kiểm tra chính xác, không dùng token của RP khác |
| **auth_time** | Thời điểm người dùng được xác thực, theo định nghĩa giao thức | Không có nghĩa sự kiện MFA mới nhất xảy ra đúng lúc đó trong mọi triển khai |
| **amr** | Thông tin về phương thức xác thực đã sử dụng | Giá trị, độ chi tiết và khả năng cung cấp khác nhau theo IdP |
| **acr** | Ngữ cảnh/lớp bảo đảm xác thực theo thỏa thuận | Giá trị chỉ có nghĩa khi RP và IdP thống nhất chính sách |
| **exp / iat** | Hạn và thời điểm phát hành token | Token mới phát hành không nhất thiết đồng nghĩa người dùng vừa thực hiện MFA lại |

RP **không tự suy** rằng token có claim MFA nghĩa là mọi yêu cầu của RP đã đạt. Cần có **hợp đồng assurance**: IdP cấu hình profile nào, RP yêu cầu ra sao, giá trị nào tương ứng phương thức và mức bảo đảm đã được kiểm tra.

Với SAML, SP có thể sử dụng **AuthnContext** cùng các thuộc tính có thỏa thuận. Phải kiểm tra chữ ký và điều kiện assertion thay vì chỉ đọc một chuỗi class reference không được kiểm chứng.

### Hạn chế của việc dùng claim cũ

Một token được phát hành trước khi người dùng chuyển vai trò có thể chứa nhóm hoặc thuộc tính cũ. Claim MFA cũng không chứng minh **quyền hiện tại** trên tài nguyên. Nếu ứng dụng cần đánh giá độ mới, phải có cơ chế yêu cầu xác thực lại và cập nhật authorization tại thời điểm phù hợp.

## 9. Step-up authentication và xác thực lại theo độ mới

**Step-up authentication** là việc yêu cầu xác thực bổ sung hoặc đạt mức bảo đảm cao hơn khi người dùng thực hiện hành động có rủi ro tăng. **Reauthentication** có thể yêu cầu chứng minh lại để bảo đảm phiên đủ mới, ngay cả khi đã dùng phương thức phù hợp từ trước.

Ví dụ:

| Hành động | Yêu cầu minh họa | Lý do |
| --- | --- | --- |
| Đọc bảng tin nội bộ | Phiên SSO hợp lệ theo chính sách | Tài nguyên thông thường |
| Đọc báo cáo tài chính nhạy cảm | MFA phù hợp và phiên đủ mới | Tài nguyên nhạy cảm |
| Thay đổi quyền của người khác | Xác thực chống phishing và phê duyệt | Đặc quyền IAM |
| Xuất dữ liệu khách hàng số lượng lớn | Step-up, kiểm tra vai trò và ngữ cảnh | Hạn chế rủi ro lạm dụng |
| Thêm authenticator mới | Xác minh chủ thể và step-up/recovery an toàn | Ngăn chiếm quyền thông qua enrollment |
| Sửa thông tin khôi phục | Xác thực lại theo rủi ro, có audit | Bảo vệ đường phục hồi |

Với OIDC, RP có thể yêu cầu điều kiện xác thực lại qua những tham số phù hợp như **max_age**, và có thể yêu cầu mức xác thực qua **acr_values** nếu IdP hỗ trợ và định nghĩa rõ. Không phải IdP nào cũng thực hiện một giá trị acr theo cùng cách; RP cần **kiểm tra kết quả** và từ chối nếu chưa đạt chính sách.

**prompt=login** có thể khiến IdP yêu cầu người dùng đăng nhập lại theo hỗ trợ của nhà cung cấp, nhưng **không tự bảo đảm MFA hoặc phishing resistance**. Đăng nhập lại chỉ với mật khẩu không thay thế một yêu cầu xác thực đa yếu tố.

### Mã giả đánh giá step-up

~~~text
authorizeSensitiveAction(session, resource, action):
    requireValidSessionAndIdentity(session)
    requireCurrentEmploymentOrSponsorship(session.identity)

    permission = evaluateRBACandABAC(
        identity=session.identity,
        resource=resource,
        action=action,
        time=now()
    )
    if not permission.allowed:
        return DENY

    requiredAssurance = policy.requiredAssurance(resource, action)
    verifiedAssurance = trustedIdPAssurance(session)
    if not assuranceMeetsPolicy(verifiedAssurance, requiredAssurance):
        return STEP_UP_REQUIRED

    if not authenticationFreshEnough(session, policy):
        return REAUTHENTICATION_REQUIRED

    return ALLOW
~~~

Mã giả chỉ minh họa trách nhiệm; không có nghĩa cứ có một claim là có thể quyết định cho phép. Hệ thống thật phải liên kết phiên đúng chủ thể, chống replay, chống session fixation và áp dụng quy tắc ủy quyền ở backend.

## 10. Phiên SSO và phiên ứng dụng là hai lớp khác nhau

Một người đăng nhập lần đầu qua IdP có thể duy trì **phiên IdP**. Mỗi RP/SP thường cũng có **phiên ứng dụng riêng**. Thời gian sống, cách gia hạn và logout của các phiên không nhất thiết giống nhau.

| Đối tượng | Do ai kiểm soát? | Rủi ro vòng đời |
| --- | --- | --- |
| Phiên SSO tại IdP | IdP | Người bị khóa account vẫn có thể có phiên đang chờ bị thu hồi theo triển khai |
| Cookie/session của ứng dụng | RP/SP | Không tự mất hiệu lực chỉ vì logout IdP |
| Refresh token | Authorization server và client theo grant | Có thể cấp access token mới nếu chưa bị revoke |
| Access token JWT | Resource server kiểm tra | Có thể còn được chấp nhận đến hạn nếu chỉ kiểm tra chữ ký và exp |
| PAT/API key ứng dụng | Ứng dụng đích | Có thể độc lập với MFA/SSO |
| SAML assertion | IdP phát hành, SP tiêu thụ theo điều kiện | Không nên bị replay hoặc dùng sai audience |

**Single Logout (SLO)** hoặc các cơ chế logout của OIDC có thể hỗ trợ kết thúc phiên ở những bên tham gia khi được cấu hình đúng, nhưng **không nên giả định mọi ứng dụng hỗ trợ hay mọi access token lập tức hết hiệu lực**.

Tổ chức phải hiểu: logout thông thường, khóa account, revoke refresh token, terminate session, thu hồi quyền và chặn JWT tại API là **những thao tác khác nhau**, dù cùng xuất hiện trong Leaver hoặc ứng phó sự cố.

## 11. Chính sách MFA tập trung tại IdP và ngoại lệ tại ứng dụng

Một lợi ích của SSO là quản lý **authentication policy tập trung**. Ví dụ các chính sách dựa trên loại nhân sự, nhóm rủi ro, ứng dụng, mức đặc quyền hoặc trạng thái thiết bị có thể được IdP đánh giá trước khi phát hành kết quả xác thực.

Tuy nhiên, cần có **kiểm kê ứng dụng** và kiểm tra thực tế:

1. Ứng dụng có bắt buộc chuyển xác thực qua IdP không?
2. Có **đường login cục bộ**, mật khẩu cũ hoặc tài khoản admin riêng bỏ qua IdP không?
3. Ứng dụng có kiểm chứng được mức MFA mà IdP tuyên bố không?
4. Có luồng đăng nhập API, mobile, desktop hoặc legacy protocol **không đi qua chính sách tập trung** không?
5. Khi bị từ chối do thiếu assurance, ứng dụng có thực hiện step-up an toàn hay chỉ cho phép bỏ qua?
6. Có cơ chế theo dõi và hết hạn **ngoại lệ MFA** với chủ sở hữu và phê duyệt không?

### Sai lầm: “Đã bật MFA trên IdP nên mọi tài khoản đều có MFA”

Một tài khoản ứng dụng có thể tồn tại từ trước khi tích hợp SSO và vẫn đăng nhập trực tiếp bằng mật khẩu. Một tài khoản break-glass hoặc bot có thể có cơ chế riêng. **Bật chính sách IdP không chặn được đường truy cập không qua IdP**; các đường này cần được vô hiệu hóa, bảo vệ tương đương hoặc quản trị ngoại lệ cụ thể.

## 12. MFA fatigue, OTP phishing và các rủi ro còn lại

**MFA fatigue** xảy ra khi người dùng nhận nhiều yêu cầu push và bị thao túng hoặc mệt mỏi dẫn tới chấp thuận nhầm. **OTP phishing** xảy ra khi mã dùng một lần bị lừa lấy hoặc bị chuyển tiếp theo thời gian thực.

| Kiểm soát | Giá trị | Giới hạn |
| --- | --- | --- |
| Push **number matching** | Giảm khả năng bấm Approve theo phản xạ | Không tự chống phishing nếu người dùng bị dẫn dụ |
| Giới hạn request / cooldown | Giảm push bombing, kiểm soát retry | Cần tránh khóa nhầm người dùng theo kiểu denial of service |
| Hiển thị ngữ cảnh | Giúp nhận diện giao dịch không mong đợi | IP/vị trí có thể sai; tên ứng dụng cần đáng tin |
| Nút Deny/Report | Phát hiện và phản ứng sớm | Cần SOC/IAM xử lý tín hiệu |
| Phishing-resistant WebAuthn | Ràng buộc xác thực với RP/origin | Phải bảo vệ recovery, binding và session |
| Đánh giá rủi ro đăng nhập | Nhận diện hành vi khác thường | Không thay thế chính sách cơ bản hoặc quyền tại API |

Người dùng chỉ nên chấp thuận MFA khi **chính mình khởi tạo** đăng nhập và ngữ cảnh phù hợp. Nếu xuất hiện push không mong đợi, cần từ chối và báo cáo theo kênh đã biết; không đọc số number matching cho người gọi tự nhận là nhân viên hỗ trợ.

## 13. Joiner: cấp danh tính, đăng ký MFA và xác nhận SSO sẵn sàng

**Joiner** bắt đầu từ nguồn có thẩm quyền như **HRIS** hoặc hệ thống bảo trợ đối tác. Quy trình thực tế phải kiểm tra danh tính, tạo account và gắn authenticator đúng chủ thể:

1. HRIS xác nhận **workerId/employmentId, trạng thái, ngày bắt đầu, organization và người quản lý**; đối tác có thể dùng nguồn bảo trợ riêng.
2. IAM liên kết person–identity–account theo **ID ổn định**, không chỉ email hoặc tên.
3. IdP tạo account/chuẩn bị đăng nhập; chưa kích hoạt quá sớm trước ngày hiệu lực.
4. Chọn loại authenticator theo chính sách: passkey/security key, TOTP hoặc phương thức khác được duyệt.
5. **Authenticator enrollment/binding** phải có bước chứng minh quyền kiểm soát và kiểm tra đúng account.
6. Tạo phương án khôi phục an toàn và authenticator dự phòng khi chính sách yêu cầu; tránh phát tán seed OTP, mã khôi phục hoặc private key.
7. Thiết lập SSO trust tới các ứng dụng phù hợp; provisioning user/group bằng SCIM/API nếu hỗ trợ.
8. Kiểm tra **MFA policy applied**, mức đảm bảo/độ mới khi ứng dụng cần và quyền hiệu lực ở hệ thống đích.
9. Phân biệt **technical readiness**, người dùng đã kích hoạt MFA và **business sign-off** khi đóng Joiner.

Ví dụ, tài khoản đã provision ở IdP nhưng nhân viên chưa đăng ký authenticator bắt buộc: có thể sẵn sàng về kỹ thuật một phần, **không được coi là đã đạt điều kiện đăng nhập có MFA**. Phải lưu trạng thái chờ rõ ràng và không cấp truy cập nhạy cảm trái chính sách.

### Bootstrap lần đầu có thể là điểm yếu

Không gửi mật khẩu dùng chung cho mọi nhân viên. Không cho thêm authenticator chỉ bằng email chưa được xác minh. Lời mời đăng ký, liên kết kích hoạt và kênh khôi phục cần có hạn, đối chiếu đúng chủ thể và được ghi kiểm toán. Nếu tạo account trước ngày nhận việc, quyền tạm thời chỉ nên phục vụ nhu cầu onboarding được duyệt.

## 14. Mover: thay vai trò có thể thay mức MFA bắt buộc

Khi **Mover**, nhân viên đổi phòng ban, organization, dự án hoặc mức đặc quyền. Quy trình không được chỉ cập nhật nhóm rồi bỏ qua **mức xác thực cần thiết của vai trò mới**.

| Thay đổi | Tác động tới SSO/MFA | Hành động phù hợp |
| --- | --- | --- |
| Nhân viên thường thành quản trị cloud | Cần mức assurance cao hơn | Đăng ký phishing-resistant authenticator, xác minh trước khi cấp quyền admin |
| Chuyển vào bộ phận tài chính | Có ứng dụng/transaction nhạy cảm | Xác minh chính sách IdP và step-up tại RP |
| Chuyển organization/tenant | Có thể đổi chính sách và phạm vi ứng dụng | Đồng bộ account/nhóm, kiểm tra ranh giới tenant |
| Bàn giao dự án cũ sang mới | Token/claim và entitlement cũ có thể còn hạn | Thu hồi quyền cũ, làm mới trạng thái phiên khi cần |
| Rời vai trò đặc quyền | Đặc quyền không còn căn cứ | Thu hồi admin role, session/token liên quan và rà soát account riêng |

Không nên giả định một lần MFA bằng OTP của tháng trước đủ cho hành động quản trị hôm nay. Cần xét **phương thức, assurance, độ mới và chính sách**. Ngược lại, không bắt người dùng thực hiện MFA ở mỗi lần bấm nút khi điều đó không tương xứng rủi ro và làm tăng MFA fatigue.

## 15. Leaver: khóa đăng nhập chưa đủ để xóa quyền tồn dư

**Leaver** thường do nguồn nhân sự/bảo trợ phát tín hiệu về kết thúc quan hệ làm việc hoặc quyết định khẩn cấp. IAM cần xác định chính xác person, employment, identity, account và mốc hiệu lực, sau đó thu hồi truy cập theo chính sách:

1. Chặn xác thực mới tại IdP và các account liên quan theo thời điểm được phê duyệt.
2. Thu hồi hoặc vô hiệu hóa authenticator/binding phù hợp, gồm phương thức recovery có thể tạo đường đăng nhập mới.
3. Thu hồi **IdP session và refresh token/grant** theo khả năng.
4. Thông báo/kết thúc **session riêng của RP/SP** qua logout hoặc API hỗ trợ.
5. Với **access token JWT đã phát hành**, xác định cách resource server chặn trước hạn: introspection, denylist, security epoch, policy recheck hoặc giới hạn TTL được chấp nhận.
6. Deactivate account và cập nhật group/role qua **SCIM/API**; rà soát local login, PAT, API key, ACL và quyền trực tiếp.
7. Đối soát tại ứng dụng đích: **người đã rời tổ chức không còn quyền hiệu lực**, trừ quan hệ còn hợp lệ hoặc ngoại lệ đã phê duyệt.
8. Lưu bằng chứng theo từng hệ thống và giao xử lý các mục chưa được xác minh.

**SCIM deactivation không phải token revocation**, và **logout tại IdP không tự chứng minh ứng dụng đã đóng phiên**. Nếu chỉ dựa trên trạng thái user ở IdP để đánh dấu Leaver hoàn tất, tổ chức có thể bỏ sót quyền truy cập tồn dư.

### Nhiều quan hệ làm việc và rehire

Nếu một người có hai hợp đồng hợp lệ và chỉ kết thúc hợp đồng A, cần **tính lại quyền gắn từng quan hệ** trước khi khóa identity dùng chung. Khi được tuyển lại, không tự phục hồi mọi role, refresh token hay phiên đã có ở giai đoạn trước; Joiner mới cần xác minh và cấp lại theo chính sách hiện hành.

## 16. Recovery và thay authenticator: mặt trái của SSO tập trung

Khi nhiều ứng dụng dựa vào một IdP, **khâu khôi phục account** trở nên đặc biệt nhạy cảm. Nếu kẻ tấn công thêm được authenticator của họ vào IdP, có thể mở được nhiều ứng dụng thông qua SSO.

Một quy trình an toàn cần:

- Xác minh danh tính theo mức rủi ro, không chỉ dựa trên họ tên, email, số điện thoại hoặc dữ liệu HR dễ lộ.
- Yêu cầu step-up hoặc quy trình identity proofing được duyệt khi thêm, xóa, thay authenticator.
- Có cơ chế dùng authenticator dự phòng phù hợp; tránh một đường fallback yếu hơn hoàn toàn so với MFA đang yêu cầu.
- Giới hạn quyền helpdesk, phê duyệt riêng cho tài khoản đặc quyền khi cần.
- Gửi thông báo độc lập khi credential hoặc phương thức recovery bị thay đổi.
- Đánh giá session/token và hành vi bất thường nếu nghi có chiếm quyền; chỉ đổi mật khẩu không đủ.
- Lưu dấu vết actor, nguồn, quyết định, thời điểm và kết quả mà không ghi seed OTP, recovery code, private key.

**SSO giúp tập trung kiểm soát nhưng cũng tập trung rủi ro**. Vì vậy phải bảo vệ quy trình recovery, credential và quyền của người quản trị IdP ngang với tầm quan trọng của các tài nguyên mà IdP mở đường truy cập.

## 17. RBAC/ABAC: xác thực thành công không phải giấy phép truy cập mọi nơi

Sau khi IdP phát hành assertion hoặc token, ứng dụng vẫn cần **authorization**:

- **Role-Based Access Control (RBAC):** xét role được cấp và phê duyệt cho chủ thể.
- **Attribute-Based Access Control (ABAC):** xét thuộc tính chủ thể, tài nguyên, hành động, ngữ cảnh và mốc hiệu lực.
- **Tenant/organization isolation:** đảm bảo quyền thuộc đúng phạm vi tổ chức và tài nguyên.
- **Least privilege:** tránh dùng nhóm SSO làm điều kiện tự cấp quyền quản trị mọi ứng dụng.

Mã giả minh họa:

~~~text
ALLOW identity READ financialReport IF:
    identity.currentEmployment == ACTIVE
    AND authenticatedByTrustedIdP(identity.session)
    AND sessionAssuranceMeetsPolicy(identity.session, financialReport)
    AND hasRole(identity, "FinancialAnalyst", financialReport.organizationId)
    AND resourceInApprovedScope(financialReport, identity)
    AND noHigherPriorityDeny(identity, financialReport)
ELSE DENY
~~~

Độ mạnh MFA không thay cho **role hợp lệ**. Một người đăng nhập bằng security key vẫn không được đọc báo cáo của tổ chức khác nếu không có entitlement; ngược lại người có entitlement cần bị từ chối khi không đáp ứng mức xác thực của tài nguyên.

**Kiểm soát phải chạy ở backend/API/resource server**, không chỉ ẩn nút trên giao diện. Token mang claim role cũ cũng có thể không phản ánh thay đổi Mover/Leaver; cần cơ chế đánh giá lại quyền theo độ mới bắt buộc.

## 18. Service account và workload identity có nên dùng SSO/MFA?

**SSO và MFA push/passkey chủ yếu giải quyết xác thực tương tác của con người.** Một bot CI/CD hoặc dịch vụ chạy nền không nên phụ thuộc vào nhân viên bấm Approve mỗi lần gọi API.

Với workload, nên dùng phương thức phù hợp như:

| Phương thức | Bối cảnh | Kiểm soát cần có |
| --- | --- | --- |
| **Workload identity federation** | Job/ứng dụng nhận credential qua danh tính môi trường thực thi đáng tin cậy | Xác thực issuer, audience, subject, quyền và TTL |
| **Client credentials / khóa riêng** | Service-to-service access | Owner, scope, lưu khóa an toàn, luân chuyển và thu hồi |
| **Certificate/mTLS** | Xác thực workload hoặc kênh truyền | Quản trị PKI, hạn, thu hồi, bảo vệ private key |
| **Managed identity** | Workload chạy trong nền tảng cloud hỗ trợ | Cấp quyền tối thiểu và tách môi trường/ứng dụng |

Người phụ trách một service account **không nên dùng PAT cá nhân thay credential máy** để bot hoạt động lâu dài. Khi người đó chuyển công tác hoặc nghỉ việc, cần chuyển owner, thu hồi credential cá nhân, đánh giá role/secret workload. Không tự xóa workload sản xuất hợp lệ chỉ vì người owner rời tổ chức.

Sự khác nhau này cũng giải thích vì sao chỉ số “tất cả account đều bật MFA push” không phải mục tiêu phù hợp với danh tính máy. Thay vào đó phải chứng minh **mọi loại chủ thể dùng cơ chế xác thực thích hợp với rủi ro và vòng đời của chính nó**.

## 19. Cấu hình và bằng chứng kiểm toán SSO–MFA

Để biết một giao dịch thực sự đáp ứng yêu cầu MFA và quyền, cần liên kết các lớp sự kiện:

| Nhóm bằng chứng | Nội dung |
| --- | --- |
| Nguồn identity | person/worker/employment ID, trạng thái, ngày hiệu lực, nguồn có thẩm quyền |
| Phiên IdP | Subject, client, thời điểm xác thực, phương thức/mức đảm bảo đã kiểm chứng |
| RP/SP | Kết quả xác minh assertion, phiên ứng dụng, audience/issuer, transaction ID |
| MFA authenticator | Loại, binding, trạng thái, kết quả challenge, UV khi áp dụng |
| Authorization | Role/entitlement, quyết định ABAC và phạm vi tài nguyên |
| Provisioning | Kết quả SCIM/API, trạng thái account và group thực tế |
| JML | Mốc kích hoạt/thu hồi, owner, phê duyệt và trạng thái ngoại lệ |
| Đối soát | Kết quả kiểm tra quyền hiệu lực và session/token ở đích |

Ví dụ bản ghi metadata **minh họa**, không phải schema chuẩn của OIDC hay SAML:

~~~json
{
  "eventId": "sso-mfa-event-2026-144",
  "identityRef": "iam-id-482",
  "idpAccountRef": "idp-user-482",
  "relyingParty": "finance-portal",
  "authenticationTransactionRef": "auth-txn-991",
  "authenticatorType": "webauthn",
  "userVerification": "verified",
  "assurancePolicy": "phishing-resistant-required",
  "authenticationVerifiedAt": "2026-11-23T09:30:00+07:00",
  "relyingPartySessionCreated": true,
  "authorizationDecision": "ALLOW_READ_REPORT",
  "resourceScope": "org-a-finance-report",
  "auditStatus": "RECORDED"
}
~~~

Ví dụ không lưu ID token, access token, cookie, recovery code, mật khẩu, seed OTP hoặc private key. Trường assurance phải phản ánh **bằng chứng đáng tin và hợp đồng chính sách**, không được tự gán dựa trên tên phương thức.

Đối với một hành động đặc quyền, log nên liên kết **yêu cầu step-up, chứng cứ hoàn tất và quyết định quyền**. Việc một RP tạo session không chứng minh các hệ thống khác đã nhận hoặc thu hồi phiên cùng lúc.

## 20. Giám sát, KPI và kiểm thử trong vận hành

Một số chỉ số thực tế:

| Chỉ số | Ý nghĩa |
| --- | --- |
| **SSO coverage** | Tỷ lệ ứng dụng/tài khoản bắt buộc đã tích hợp SSO đúng chính sách |
| **MFA policy coverage** | Tỷ lệ đối tượng cần MFA đã được áp dụng chính sách và thực thi ở các đường login |
| **Phishing-resistant coverage** | Tỷ lệ tài khoản/phiên rủi ro cao thực sự dùng phương thức chống phishing |
| **Authenticator binding failures** | Số lần đăng ký/đổi phương thức lỗi hoặc thiếu bằng chứng |
| **Step-up success / policy bypass** | Giao dịch nhạy cảm đã đạt mức assurance yêu cầu, trường hợp bỏ qua sai |
| **Unexpected MFA challenges** | Yêu cầu push bị từ chối/báo đáng ngờ, tín hiệu MFA fatigue |
| **Local-login bypass count** | Đường xác thực không qua IdP/MFA tập trung |
| **Stale sessions after Leaver** | Phiên ứng dụng còn hiệu lực sau mốc phải thu hồi |
| **Time to effective deprovisioning** | Độ trễ từ sự kiện HR đến khi target từ chối quyền thực tế |
| **Unverified applications** | Số ứng dụng chưa thể chứng minh account/session/quyền đúng |

Kiểm thử nên bao gồm cả **trường hợp cho phép và từ chối**:

1. Người dùng hợp lệ đăng nhập và ứng dụng nhận đúng danh tính, đúng mức MFA.
2. Ứng dụng nhạy cảm từ chối phiên SSO chỉ có mật khẩu khi yêu cầu MFA cao hơn.
3. RP nhận assertion/token sai issuer, audience, signature, nonce hoặc quá hạn phải từ chối.
4. Local login không được vượt qua chính sách trung tâm nếu không có ngoại lệ được duyệt.
5. Sau Mover, tài khoản không còn quyền dự án cũ dù token/claim trước đó còn được lưu.
6. Sau Leaver, IdP không cấp xác thực mới; ứng dụng đích từ chối các đường truy cập thuộc phạm vi đã thu hồi.
7. Authenticator bị mất hoặc thay thế không còn đăng nhập được bằng binding đã thu hồi.
8. Luồng recovery được kiểm soát và không trở thành con đường cấp quyền tự do.

Không có một ngưỡng phiên, độ trễ hoặc tần suất MFA hợp lý cho mọi hệ thống. Tổ chức cần xác định **mức rủi ro, SLA và yêu cầu trải nghiệm** theo dữ liệu và vai trò công việc.

## 21. Tình huống thực hành: SSO hợp lệ nhưng MFA chưa đủ

**Bối cảnh:** Minh làm nhân viên chăm sóc khách hàng, đăng nhập vào IdP doanh nghiệp bằng mật khẩu và TOTP. Từ ngày 01/12, Minh được chuyển sang nhóm vận hành hạ tầng. Ứng dụng quản trị cloud đã tích hợp OIDC SSO và yêu cầu **phương thức chống phishing, phiên đủ mới và quyền cloud-admin đã được phê duyệt**.

Ngày đầu sau Mover, Minh mở ứng dụng cloud. Nhờ phiên SSO còn hợp lệ, IdP có thể không yêu cầu nhập lại mật khẩu. Nhưng ứng dụng **không được chỉ nhìn vào trạng thái SSO thành công rồi cho phép**.

### Phân tích từng bước

1. **HRIS/IGA:** xác nhận Minh đổi vai trò, ngày hiệu lực, role cloud-admin đã duyệt và quyền cũ phải thu hồi.
2. **Ứng dụng/RP:** xác định chính sách đòi phishing-resistant MFA và mức độ mới của xác thực cho hành động quản trị.
3. **IdP:** phiên hiện tại chỉ chứng minh mật khẩu + TOTP theo hợp đồng assurance. Nếu chưa đạt điều kiện mới, phải yêu cầu **step-up** với authenticator phù hợp.
4. **Minh:** hoàn thành WebAuthn với security key/passkey được đăng ký đúng identity và đáp ứng yêu cầu UV khi chính sách quy định.
5. **RP:** kiểm tra kết quả OIDC, assurance theo hợp đồng và độ mới trước khi cấp phiên/hành động nhạy cảm.
6. **Ứng dụng cloud:** tiếp tục kiểm tra role, organization, hành động và tài nguyên theo RBAC/ABAC; MFA mạnh không tự tạo role admin.
7. **Kiểm toán:** ghi phương thức, policy, mốc xác thực, cấp/thu hồi quyền và kết quả kiểm tra ở đích mà không lưu token thật.

### Tình huống biến thể

**Trường hợp A – Minh chưa đăng ký security key:** giữ quyền admin chưa sử dụng được và hướng dẫn enrollment có xác minh. Không hạ chính sách cho tất cả nhân viên để Minh vào ngay.

**Trường hợp B – Minh còn đăng nhập local bằng password trong ứng dụng:** xem đây là đường bypass; vô hiệu hoặc bảo vệ tương đương theo chính sách.

**Trường hợp C – Minh rời nhóm quản trị sau hai tháng:** thu hồi role và phiên/token có quyền cũ, đối soát tại cloud. Không chỉ bỏ Minh khỏi nhóm ở IdP.

**Trường hợp D – Minh nghỉ việc:** thực hiện Leaver trên account, authenticator, session IdP, RP/SP, token, tài khoản cục bộ và quyền API; chỉ đóng khi có bằng chứng hoặc ngoại lệ được ghi rõ.

### Câu hỏi tự kiểm tra

**Câu 1:** Người dùng đã MFA một lần ở IdP thì mọi ứng dụng SSO có tự đạt MFA không?

**Trả lời:** Không. Ứng dụng phải biết mức bảo đảm và độ mới theo chính sách; có thể cần step-up.

**Câu 2:** Number matching có đồng nghĩa phishing-resistant MFA?

**Trả lời:** Không. Đây là biện pháp giảm phê duyệt push nhầm, nhưng không thay thế ràng buộc mật mã với RP/origin của WebAuthn.

**Câu 3:** Claim acr có thể tự diễn giải thành “đã dùng passkey” không?

**Trả lời:** Không nếu IdP và RP chưa thống nhất giá trị/kiểm chứng. Một chuỗi claim chỉ có ý nghĩa trong hợp đồng assurance đã định nghĩa.

**Câu 4:** SCIM đặt account inactive có xóa mọi session của ứng dụng không?

**Trả lời:** Không mặc nhiên. Cần kiểm tra khả năng session/token revocation riêng ở đích.

**Câu 5:** Workload có cần nhân viên bấm MFA push trước mỗi API call?

**Trả lời:** Không nên. Workload cần credential máy, danh tính và quyền riêng phù hợp, không phụ thuộc xác thực tương tác của người.

## 22. Checklist thiết kế SSO kết hợp MFA

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| IdP/RP/SP đã định nghĩa quan hệ tin cậy? | Issuer, audience, signing keys, redirect/ACS và cấu hình đã duyệt |
| Giao thức OIDC/SAML có được xác minh đúng? | Signature, issuer, audience, state, nonce/InResponseTo, validity và chống replay theo ngữ cảnh |
| Có phân biệt SSO với MFA không? | Chính sách factor, authenticator và assurance cho từng lớp |
| Chính sách MFA áp dụng vào những đường login nào? | Web, mobile, desktop, local/fallback, admin |
| Ứng dụng nhạy cảm có kiểm chứng mức bảo đảm? | amr/acr/auth_time hoặc AuthnContext theo hợp đồng tích hợp |
| Có step-up và yêu cầu phiên đủ mới? | Giao dịch nhạy cảm bị từ chối khi chỉ có assurance thấp |
| Có sử dụng phishing-resistant MFA khi cần? | WebAuthn kiểm tra RP/origin/challenge, UV theo policy |
| Khâu binding/recovery có đủ bảo vệ? | Identity proofing, phê duyệt, audit và xử lý mất thiết bị |
| Joiner đã đăng ký authenticator đúng người? | Nguồn HR, account mapping, evidence enrollment và trạng thái kích hoạt |
| Mover có làm thay đổi chính sách xác thực/quyền? | Đánh giá lại assurance, role, token và entitlement cũ |
| Leaver có chặn cả phiên và quyền đích? | IdP, RP/SP, refresh/access token, SCIM, local ACL và readback |
| Có quản trị identity máy riêng? | Workload owner, client credential/federation, TTL và scope |
| Có phát hiện MFA fatigue/phishing? | Push anomaly, number matching nếu áp dụng, SOC workflow |
| RBAC/ABAC có được thực thi tại backend? | Quyền đúng chủ thể, hành động, tài nguyên và tenant |
| Có bằng chứng kiểm toán và đối soát? | Từng target, mốc thời gian, trạng thái quyền thực tế và ngoại lệ |

## 23. Tổng kết

**SSO và MFA** giải quyết **hai vấn đề khác nhau nhưng phải phối hợp**: SSO cho phép ứng dụng sử dụng kết quả xác thực từ IdP, còn MFA nâng mức chắc chắn rằng chủ thể thật sự kiểm soát danh tính. Một phiên SSO hợp lệ không tự chứng minh đã đáp ứng MFA hoặc yêu cầu **phishing resistance** của mọi ứng dụng; cần chính sách rõ, tín hiệu assurance được xác minh và **step-up** khi hành động nhạy cảm đòi hỏi.

Trong vòng đời **Joiner–Mover–Leaver**, **HRIS/nguồn bảo trợ** cung cấp căn cứ về quan hệ làm việc; **IAM/IGA** quản lý identity, phê duyệt và quyền; **IdP/SSO** tổ chức xác thực; **SCIM** giúp đồng bộ user/group; **RBAC/ABAC và resource server** thực thi quyền thực tế; còn **service/workload identity** dùng credential máy được quản trị riêng. Xác minh account, authenticator, phiên, token và entitlement tại từng hệ thống đích là bước quyết định để giảm **quyền truy cập tồn dư**, đồng thời duy trì trải nghiệm đăng nhập thuận tiện và có kiểm soát.
