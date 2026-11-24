# Reauthentication khi hành động nhạy cảm

Một người dùng đã đăng nhập thành công không có nghĩa là mọi yêu cầu trong nhiều giờ tiếp theo đều an toàn như nhau. Khi đổi mật khẩu, xóa phương thức MFA, tạo API key có quyền cao hoặc chuyển tiền đến tài khoản mới, hệ thống thường cần **reauthentication (xác thực lại)** để có bằng chứng mới rằng đúng chủ thể hợp pháp đang thực hiện thao tác. Với hành động rủi ro cao, hệ thống còn có thể yêu cầu **step-up authentication**: nâng mức bảo đảm xác thực so với phiên hiện tại.

Đây là vấn đề đặc biệt quan trọng trong module **Security Token Security Fundamentals**. Một **access token** có thể hợp lệ về chữ ký, issuer, audience và thời hạn nhưng vẫn được phát hành từ phiên đăng nhập quá cũ; một **refresh token** có thể lấy access token mới mà người dùng không nhập lại yếu tố xác thực; một **bearer token** bị đánh cắp có thể bị kẻ khác dùng trong thời gian còn hiệu lực. Hệ thống phải đánh giá cả **độ tin cậy và độ mới của sự kiện xác thực**, cùng quyền thực hiện hành động cụ thể.

Ví dụ xuyên suốt: Lan đã đăng nhập vào ứng dụng tài chính lúc 08:00. Đến 16:00, một yêu cầu đổi tài khoản nhận tiền được gửi từ phiên của Lan. Máy chủ thấy access token còn hạn nhưng chính sách yêu cầu xác thực lại trong 5 phút gần nhất bằng phương thức có mức bảo đảm cao. Yêu cầu phải được tạm dừng để Lan xác thực lại, sau đó mới được xét phân quyền và xác nhận chính giao dịch đang chờ. **Con số 5 phút chỉ là chính sách minh họa**, không phải thời hạn bắt buộc cho mọi hệ thống.

## 1. Authentication, reauthentication, step-up và authorization khác nhau thế nào?

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Authentication (AuthN)** | Chủ thể nào đang được xác thực, bằng chứng nào? | Lan đăng nhập bằng passkey |
| **Reauthentication** | Người dùng có thể đưa ra bằng chứng xác thực **mới** trước khi tiếp tục không? | Yêu cầu dùng lại passkey khi đổi tài khoản nhận tiền |
| **Step-up authentication** | Sự kiện xác thực hiện tại có đạt **mức bảo đảm cao hơn** mà thao tác yêu cầu không? | Phiên đăng nhập bằng mật khẩu cần thêm phương thức chống phishing cho hành động rủi ro |
| **Authorization (AuthZ)** | Chủ thể đã xác thực có quyền làm việc này trên tài nguyên này không? | Lan có quyền sửa thông tin thanh toán của chính doanh nghiệp mình hay không? |
| **Transaction authorization** | Người dùng đã xác nhận **đúng hành động và tham số** đang được thực thi chưa? | Xác nhận chuyển 20 triệu đồng đến số tài khoản X, tránh đổi người nhận sau bước xác thực |

**Reauthentication** nhấn mạnh thời điểm xác thực mới; **step-up** nhấn mạnh mức bảo đảm cần đạt. Một lần xác thực lại có thể đồng thời là step-up nếu dùng phương thức mạnh hơn. Ngược lại, yêu cầu người dùng chỉ nhập lại mật khẩu vẫn có thể chưa đủ khi chính sách đòi xác thực chống phishing.

Reauthentication **không tự cấp quyền mới**. Sau khi Lan xác thực lại, API vẫn phải kiểm quyền theo role, scope, chủ sở hữu, tenant và điều kiện nghiệp vụ. Nếu Lan không có quyền tạo API key quản trị, nhập đúng passkey cũng không biến Lan thành quản trị viên.

## 2. Khi nào một hành động đủ nhạy cảm để yêu cầu xác thực lại?

Chính sách nên dựa trên **mức độ thiệt hại nếu yêu cầu bị chiếm quyền** và tín hiệu rủi ro của phiên, thay vì yêu cầu xác thực lại cho tất cả thao tác. Những nhóm hành động thường đáng xem xét:

| Nhóm hành động | Ví dụ | Rủi ro chính | Biện pháp thường phù hợp |
|---|---|---|---|
| **Thay đổi phương thức đăng nhập** | Đổi mật khẩu, thêm/xóa passkey, tắt MFA, cập nhật số điện thoại khôi phục | Kẻ chiếm phiên có thể khóa chủ tài khoản khỏi hệ thống | Xác thực lại đủ mạnh; thông báo; bảo vệ luồng khôi phục |
| **Thay đổi thông tin nhận tiền** | Thêm tài khoản ngân hàng, đổi địa chỉ thanh toán | Chuyển tài sản sang nơi do kẻ tấn công kiểm soát | Step-up, xác nhận thông tin đích, kiểm gian lận |
| **Giao dịch giá trị cao** | Chuyển tiền, hoàn tiền, phê duyệt khoản chi lớn | Mất tiền, lạm dụng quyền phê duyệt | Xác thực lại và xác nhận gắn với nội dung giao dịch |
| **Cấp quyền hoặc tạo thông tin bí mật** | Cấp role admin, tạo API key, thêm client credential, cấp consent nhạy cảm | Duy trì quyền truy cập lâu dài sau khi chiếm phiên | Step-up, phê duyệt theo chính sách, ghi audit |
| **Trích xuất hoặc xóa dữ liệu** | Xuất dữ liệu hàng loạt, xóa tổ chức, tải bản sao dữ liệu nhạy cảm | Rò rỉ hoặc mất dữ liệu không thể đảo ngược | Xác thực lại, giới hạn phạm vi, kiểm quyền và đôi khi phê duyệt hai người |
| **Phát hiện phiên bất thường** | Thiết bị lạ, thay đổi vị trí đáng ngờ, yêu cầu dồn dập | Token/session có thể đã bị lộ | Đánh giá rủi ro, xác thực lại, khóa hoặc thu hồi khi cần |

Không có một ngưỡng thời gian hoặc danh sách hành động áp dụng giống nhau cho mọi sản phẩm. Ví dụ, hệ thống có thể yêu cầu **sự kiện xác thực trong vòng 10 phút** khi đổi mật khẩu và **xác nhận riêng từng giao dịch** khi chuyển tiền lớn. Đó là lựa chọn chính sách dựa trên rủi ro, không phải mặc định kỹ thuật của JWT, OAuth 2.0 hay OIDC.

### Quyết định dựa trên nhiều yếu tố

Một chính sách đủ rõ nên xét ít nhất:

1. **Mức nhạy cảm của hành động**: đọc hồ sơ, thay quyền, rút tiền hay xóa tenant có tác động khác nhau.
2. **Độ mới của xác thực**: sự kiện xác thực người dùng gần nhất diễn ra lúc nào, và thông tin đó có đáng tin không?
3. **Mức bảo đảm**: phương thức xác thực vừa dùng có đáp ứng yêu cầu của hành động không?
4. **Ngữ cảnh rủi ro**: thiết bị, phiên, dấu hiệu bị chiếm quyền, thay đổi tài khoản đích hoặc tần suất bất thường.
5. **Quyền hiện có**: chủ thể có scope và quyền nghiệp vụ trên tài nguyên cần thao tác không?
6. **Ràng buộc giao dịch**: người dùng có xác nhận chính tài nguyên, giá trị và người nhận của thao tác không?

## 3. Access token mới chưa chắc có xác thực mới

Giả sử Lan đăng nhập lúc 08:00 và nhận access token 15 phút. Client dùng refresh token để xin access token mới ở 15:58:

~~~text
08:00  Lan xác thực bằng passkey
08:00  AS phát hành access token #1
08:15  Access token #1 hết hạn
...
15:58  Client dùng refresh token xin access token #N
16:00  Client yêu cầu đổi tài khoản nhận tiền
~~~

Nếu API chỉ nhìn thấy **iat = 15:58** và **exp = 16:13** rồi kết luận Lan vừa xác thực, đó là một sai lầm. **iat** biểu thị thời điểm token được phát hành, còn **auth_time** (nếu được issuer cung cấp đáng tin cậy theo profile thích hợp) mô tả thời điểm người dùng được xác thực. Làm mới access token thông thường **không tương đương** người dùng nhập lại bằng chứng xác thực.

| Thông tin | Ý nghĩa chính | Có chứng minh người dùng vừa xác thực lại không? |
|---|---|---|
| **iat** | Token được phát hành lúc nào | **Không** |
| **exp** | Token hết hạn lúc nào | **Không** |
| **nbf** | Token chưa có hiệu lực trước thời điểm nào | **Không** |
| **auth_time** | Thời điểm diễn ra sự kiện xác thực người dùng trong ngữ cảnh OIDC | **Có thể là bằng chứng về độ mới**, sau khi kiểm tính tin cậy và ngữ nghĩa của claim |
| **acr** | Lớp/ngữ cảnh bảo đảm xác thực theo định nghĩa của nhà cung cấp | Có thể giúp kiểm mức bảo đảm; **không tự nói xác thực vừa diễn ra** |
| **amr** | Các phương thức xác thực đã được sử dụng theo định nghĩa của nhà cung cấp | Giúp hiểu phương thức; **không đủ để suy thời gian hoặc mọi thuộc tính bảo đảm** |
| **scope** | Phạm vi quyền truy cập được cấp | **Không** |
| **jti** | Định danh token khi có | **Không**; hữu ích cho kiểm chống phát lại trong một số thiết kế |

Trong OIDC, **auth_time** là claim của ID token với ngữ nghĩa được đặc tả; hệ thống có thể truyền ngữ cảnh xác thực tới resource server bằng **access token có profile phù hợp**, **introspection**, hoặc **bản ghi phiên từ dịch vụ danh tính**. Không được giả định mọi access token đều có **auth_time**, **acr** hoặc **amr**, cũng không cho resource API dùng **ID token** thay access token.

### JWT minh họa: token mới, phiên xác thực cũ

Payload sau chỉ mô tả hợp đồng giả định giữa Authorization Server và API; nó không phải một token có thể sử dụng:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user-lan",
  "aud": "payments-api",
  "scope": "beneficiary:update",
  "iat": 1800000000,
  "exp": 1800000900,
  "auth_time": 1799971200,
  "acr": "urn:example:acr:phishing-resistant"
}
~~~

API phải xác minh chữ ký hoặc introspection, issuer, audience, thời hạn, loại token và ngữ nghĩa claims trước khi sử dụng. Token này có thể còn hạn, nhưng **auth_time** đã cũ so với yêu cầu độ mới của hành động. **acr** chỉ có ý nghĩa nếu API và Authorization Server chia sẻ cùng cách định nghĩa và phát hành mức bảo đảm đó. Một chuỗi tự đặt như **urn:example:acr:phishing-resistant** không tạo ra bảo đảm nếu nhà cung cấp chưa thực sự thực thi chính sách tương ứng.

## 4. Mô hình thực thi: API yêu cầu step-up

Xét ứng dụng web gọi **Payments API** để đổi tài khoản nhận tiền. Một cách triển khai gồm các bước:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Lan
    participant App as Ứng dụng web
    participant API as Payments API
    participant AS as Authorization Server / IdP
    participant DB as Kho chính sách và dữ liệu
    U->>App: Yêu cầu đổi tài khoản nhận tiền
    App->>API: Gửi yêu cầu với access token
    API->>API: Xác minh token và quyền cơ bản
    API->>DB: Kiểm chính sách độ mới và mức bảo đảm
    DB-->>API: Yêu cầu xác thực mới và mạnh hơn
    API-->>App: Trả challenge step-up
    App-->>U: Chuyển đến luồng xác thực của AS
    U->>AS: Xác thực lại theo chính sách
    AS-->>App: Authorization code qua redirect
    App->>AS: Đổi code với PKCE và client policy
    AS-->>App: Token/ngữ cảnh xác thực mới
    App->>API: Gửi lại yêu cầu đã được người dùng xác nhận
    API->>API: Kiểm token, độ mới, mức bảo đảm và giao dịch
    API->>DB: Kiểm quyền cuối cùng và cập nhật an toàn
    API-->>App: Thành công hoặc từ chối
~~~

Điểm quan trọng là **resource server quyết định hành động có cần step-up hay không**, còn Authorization Server/IdP chịu trách nhiệm xác thực người dùng và phát hành bằng chứng phù hợp. Client chỉ điều hướng luồng; **client không được tự tuyên bố** xác thực đã đủ mạnh bằng một tham số hoặc cờ giao diện.

### Trả challenge bằng HTTP

Với API dùng OAuth bearer token, một cách chuẩn hóa yêu cầu nâng xác thực là giao thức **OAuth 2.0 Step Up Authentication Challenge** (RFC 9470). Ví dụ minh họa:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="insufficient_user_authentication",
                  acr_values="urn:example:acr:strong",
                  max_age="300"
Cache-Control: no-store
~~~

API đang nói: token đã trình bày không đáp ứng **mức bảo đảm** và/hoặc **độ mới** cần cho thao tác. **acr_values** mô tả mức yêu cầu theo hợp đồng với AS; **max_age** mô tả giới hạn tuổi sự kiện xác thực. Client cần xử lý challenge bằng một luồng được AS hỗ trợ, sau đó thử lại với token/ngữ cảnh được cấp hợp lệ.

Đừng nhầm các tình huống:

- **401 invalid_token**: thiếu token hoặc token không hợp lệ, sai issuer/audience, hết hạn, v.v.
- **401 insufficient_user_authentication**: cần tăng mức hoặc độ mới của xác thực cho hành động đang yêu cầu, nếu dùng cơ chế RFC 9470.
- **403 insufficient_scope/forbidden**: token đã được chấp nhận nhưng không có quyền hành động; xác thực lại không thể thay thế việc cấp quyền đúng.

API dùng session cookie có thể có cách phản hồi riêng để điều hướng người dùng. Dù dùng mã trạng thái nào, **server phải từ chối thao tác nhạy cảm cho đến khi có bằng chứng thỏa chính sách**, và không nhầm challenge xác thực với quyết định phân quyền.

### Yêu cầu xác thực lại với OIDC

Trong một ứng dụng dùng OIDC Authorization Code Flow, client có thể gửi yêu cầu đến AS với các tham số phù hợp:

~~~text
response_type = code
scope = openid [và các scope được phép khác]
client_id = client đã đăng ký
redirect_uri = redirect URI đã đăng ký
state = giá trị ngẫu nhiên chống gắn nhầm response
nonce = giá trị ràng buộc OIDC response khi áp dụng
code_challenge_method = S256
code_challenge = giá trị PKCE hợp lệ
max_age = 0
acr_values = mức bảo đảm mong muốn theo hợp đồng AS
~~~

**max_age=0** yêu cầu AS chủ động xác thực lại người dùng; **prompt=login** cũng có thể yêu cầu đăng nhập lại trong OIDC, tùy hành vi và hỗ trợ của nhà cung cấp. Các tham số yêu cầu **không tự bảo đảm** kết quả đạt mức mong muốn. Với OIDC, khi dùng **max_age**, client phải kiểm **auth_time** trong ID token được phát hành và các kiểm tra ID token thông thường như issuer, audience, chữ ký, nonce khi áp dụng. Nếu cần mức bảo đảm cụ thể, phải kiểm giá trị **acr** mà AS trả về và định nghĩa đã thỏa thuận.

Sau đó, **API chỉ dùng bằng chứng dành cho API**: access token được phát hành lại với ngữ cảnh xác thực được kiểm chứng, thông tin introspection hoặc trạng thái phiên đáng tin cậy. Client **không gửi ID token như bearer access token** để vượt qua kiểm tra step-up.

## 5. Thiết kế chính sách đủ chặt

Một chính sách step-up có thể được diễn đạt thành ba điều kiện độc lập:

~~~text
ALLOW(request) =
    valid_access_token_for_this_api
    AND authorized_principal_for_action_and_resource
    AND acceptable_authentication_context_for_action
    AND transaction_confirmation_if_policy_requires
~~~

Trong đó, kiểm **acceptable_authentication_context** có thể gồm:

~~~text
authentication_time exists and is trusted
AND now - authentication_time <= allowed_authentication_age
AND achieved_authentication_assurance satisfies required_assurance
AND authentication_subject == requesting_subject
AND authentication_context_is_bound_to_current_session_or_client
~~~

Các giá trị trong công thức là **ngữ cảnh nội bộ đã được xác minh**, không phải header tùy ý. Cách đối chiếu mức bảo đảm cần dựa trên chính sách của IdP/AS và profile mà API hiểu. Không so sánh **acr** như một thứ tự chữ cái; các giá trị **amr** cũng không tự tương đương mức bảo đảm.

### Ví dụ bảng chính sách

| Hành động | Độ mới minh họa | Mức xác thực | Điều kiện bổ sung |
|---|---|---|---|
| Xem trang hồ sơ công khai | Không cần xác thực mới | Có thể công khai | Chính sách dữ liệu công khai |
| Đổi tên hiển thị | Phiên hợp lệ | Mức đăng nhập thông thường | Quyền sửa đúng hồ sơ |
| Đổi mật khẩu | Trong 10 phút | Mức bảo đảm theo chính sách bảo vệ tài khoản | Xác minh quyền sở hữu tài khoản và thông báo |
| Xóa phương thức MFA cuối cùng | Trong 5 phút | Bằng chứng mạnh, quy trình phục hồi có kiểm soát | Chống hạ cấp phương thức, thông báo |
| Tạo API key quản trị | Trong 5 phút | Step-up theo chính sách | Role, scope, giới hạn key, audit |
| Chuyển tiền lớn | Mới tại thời điểm chấp thuận | Mức mạnh và phù hợp rủi ro | Xác nhận gắn số tiền, tiền tệ, tài khoản nhận |

Đây là **ví dụ thiết kế**, không phải yêu cầu chuẩn hóa. Việc chọn ngưỡng thời gian và phương thức cần xét đặc thù sản phẩm, quy định áp dụng, khả năng tiếp cận của người dùng và nguy cơ phishing.

## 6. Xác thực lại không đủ để xác nhận giao dịch

Giả sử Lan dùng passkey xác thực lại lúc 16:00. Ngay sau đó, ứng dụng gửi hai yêu cầu:

1. Chuyển **2.000.000 VND** đến tài khoản của đối tác A như Lan vừa xem.
2. Chuyển **200.000.000 VND** đến tài khoản X do kẻ tấn công sửa tham số bằng một phiên đã bị chiếm quyền.

Nếu máy chủ chấp nhận bất kỳ thao tác nào chỉ vì “người dùng đã xác thực lại trong 5 phút”, yêu cầu thứ hai vẫn có thể vượt qua. Xác thực lại chứng minh **độ mới danh tính theo chính sách**; nó không tự bảo đảm người dùng đã kiểm tra **đúng số tiền và người nhận**.

Với hành động rủi ro rất cao, nên bổ sung **transaction authorization**:

- Máy chủ tạo một **giao dịch chờ** với định danh duy nhất và giữ các tham số quan trọng: chủ thể, tenant, hành động, tài nguyên, số tiền, tiền tệ, đích nhận.
- Ứng dụng hiển thị rõ các tham số đó cho người dùng xác nhận bằng kênh đáng tin cậy phù hợp.
- Sau khi xác thực lại hoặc xác nhận, hệ thống lưu **bằng chứng gắn với giao dịch cụ thể**, có thời hạn ngắn và dùng một lần. Bằng chứng có thể là bản ghi phía server hoặc token được ký và kiểm chặt theo mục đích.
- Khi thực thi, máy chủ so khớp nội dung giao dịch đang chờ với bằng chứng đã xác nhận, đánh dấu bằng chứng đã dùng **một cách nguyên tử** và kiểm lại quyền/trạng thái dữ liệu.
- Thay đổi số tiền, người nhận hoặc quyền sở hữu sau khi xác nhận phải làm bằng chứng cũ **không còn phù hợp**; giao dịch mới cần xác nhận mới.

Lưu ý: Một lần WebAuthn/passkey authentication thông thường ràng buộc xác thực với **origin và challenge**, nhưng **không tự động ký xác nhận các tham số chuyển tiền theo nghĩa nghiệp vụ**. Nếu cần xác nhận cụ thể số tiền/người nhận, phải xây dựng thêm cơ chế ràng buộc và hiển thị nội dung giao dịch phù hợp.

## 7. Phác thảo xử lý ở backend

API nên chuẩn hóa việc đánh giá theo các bước: token hợp lệ → quyền trên tài nguyên → độ mới/mức bảo đảm → bằng chứng giao dịch (nếu cần) → cập nhật an toàn.

~~~text
function approveSensitiveChange(request, accessToken, changeId, proof):
    ctx = verifyAccessToken(
        accessToken,
        expectedIssuer = "https://login.example.test",
        expectedAudience = "payments-api",
        expectedPurpose = "access"
    )
    if ctx.invalid:
        return HTTP_401_invalid_token

    change = repository.findPendingChange(changeId)
    if change == null:
        return HTTP_404

    if not policy.mayApprove(ctx.subject, ctx.tenant, change):
        return HTTP_403

    auth = trustedAuthenticationContext(ctx)
    if auth == null:
        return STEP_UP_REQUIRED
    if auth.subject != ctx.subject:
        return STEP_UP_REQUIRED
    if auth.time > now + allowedClockSkew:
        return STEP_UP_REQUIRED
    if now - auth.time > policy.maxAgeFor(change.kind):
        return STEP_UP_REQUIRED
    if not policy.assuranceSatisfies(auth.acr, change.kind):
        return STEP_UP_REQUIRED

    expectedFingerprint = hash(
        change.id, change.owner, change.tenant,
        change.kind, change.destination, change.amount, change.currency,
        change.version
    )

    if policy.requiresTransactionConfirmation(change.kind):
        if not confirmationProof.verify(
            proof,
            subject = ctx.subject,
            session = ctx.trustedSessionId,
            transactionId = change.id,
            fingerprint = expectedFingerprint,
            notExpired = true,
            notPreviouslyUsed = true
        ):
            return HTTP_403_confirmation_required

    database.transaction:
        current = repository.lockAndReload(change.id)
        if current.version != change.version:
            return HTTP_409_change_modified
        if not policy.mayApprove(ctx.subject, ctx.tenant, current):
            return HTTP_403
        if confirmationRequired:
            consumeProofExactlyOnce(proof)
        applySensitiveChange(current)
        audit.record(ctx.subject, ctx.clientId, current.id, auth.time)

    return HTTP_200
~~~

Đây là **mã giả về các ranh giới tin cậy**, không phải hàm có sẵn trong OAuth, OIDC hoặc thư viện Java. Các trường như **trustedSessionId**, **auth.time** và **proof** phải đến từ cơ chế đáng tin của hệ thống. Việc khóa dữ liệu, kiểm phiên bản và tiêu thụ bằng chứng cùng giao dịch giúp tránh **race condition**, **TOCTOU** (kiểm điều kiện một lần rồi dùng dữ liệu đã thay đổi) và phát lại xác nhận.

Nếu ứng dụng không cần xác nhận theo từng giao dịch, vẫn nên ràng buộc trạng thái step-up vào **đúng subject, tenant, phiên/client và thời hạn**, tránh một lần reauthentication ở tài khoản A vô tình nâng quyền phiên tài khoản B. Không chuyển tiếp bằng chứng step-up sang API khác nếu audience hoặc mục đích không khớp.

### Có nên phát hành “step-up token” riêng?

Có hai hướng thường gặp:

| Hướng | Cách hoạt động | Điểm cần lưu ý |
|---|---|---|
| **Phiên hoặc trạng thái step-up phía server** | API/backend đọc trạng thái xác thực mới từ dịch vụ tin cậy, giới hạn theo subject/session và thời gian | Cần bảo vệ phiên, đồng bộ trạng thái/thu hồi, tránh tin cờ frontend |
| **Access token mới có ngữ cảnh xác thực phù hợp** | AS phát hành access token sau step-up; resource server kiểm chính sách theo claims đã được xác minh hoặc introspection | Cần rõ audience, loại token, auth_time, acr, thời hạn, khả năng thu hồi |

Không cần mặc định sáng tạo thêm một loại JWT mới. Nếu dùng token hoặc receipt cho xác nhận giao dịch, nó phải có **mục đích riêng, thời hạn ngắn, ràng buộc tài nguyên/hành động**, kiểm chống phát lại và quy tắc thu hồi rõ ràng. Không dùng **refresh token** làm bằng chứng step-up, vì refresh token thông thường chỉ phục vụ xin access token mới và không chứng minh sự kiện xác thực người dùng vừa diễn ra.

## 8. Các kiểu tấn công mà reauthentication cần tính đến

| Tình huống | Vì sao dễ bị bỏ sót | Hướng phòng vệ |
|---|---|---|
| **Bearer access token bị đánh cắp** | Token còn hạn vẫn qua bước kiểm chữ ký | Yêu cầu sự kiện xác thực mới cho hành động nhạy cảm; giới hạn token, phát hiện bất thường, cân nhắc ràng buộc người gửi |
| **Session cookie bị chiếm** | Đăng nhập trước đó có thể được tái sử dụng | Xác thực lại phía IdP/backend; kiểm CSRF, chống session fixation, ràng buộc trạng thái step-up với phiên |
| **Refresh token bị lộ** | Kẻ tấn công có thể xin access token có iat mới | Bảo vệ và xoay vòng refresh token thích hợp; không coi iat là auth_time |
| **Phishing OTP hoặc MFA fatigue** | Mã một lần/push có thể bị lừa nhập hoặc chấp thuận | Ưu tiên phương thức chống phishing như passkey/WebAuthn phù hợp; hạn chế thử nhiều lần và cảnh báo bất thường |
| **Hạ cấp phương thức MFA** | Kẻ chiếm phiên xóa yếu tố mạnh rồi đăng nhập yếu hơn | Đòi step-up trước khi xóa/đổi MFA; bảo vệ và giám sát đường khôi phục |
| **Front-end bỏ qua màn xác thực lại** | Nếu API chỉ dựa vào UI, kẻ tấn công gọi endpoint trực tiếp | Kiểm chính sách bắt buộc tại backend cho mọi đường vào |
| **Đổi tham số sau xác nhận** | Bằng chứng cho thao tác A được dùng làm thao tác B | Ràng buộc confirmation proof với số tiền, đích, tài nguyên, phiên bản và thời hạn |
| **Dùng lại bằng chứng** | Một receipt/challenge được phát lại để thực thi nhiều lần | Nonce hoặc transaction ID duy nhất, tiêu thụ nguyên tử, idempotency và TTL |
| **OAuth token confusion** | API dùng nhầm ID token hoặc token dành cho dịch vụ khác | Kiểm issuer, audience, token purpose/profile, scope và ngữ cảnh bảo đảm |
| **Cướp phiên sau step-up** | Phiên vừa nâng mức xác thực trở nên có giá trị hơn | Giữ cửa sổ ngắn, tránh nâng quyền toàn cục không cần thiết, giám sát và ràng buộc giao dịch |

**Reauthentication không phải thuốc chữa mọi hình thức chiếm phiên.** Nếu thiết bị đang bị điều khiển hoặc ứng dụng bị XSS, kẻ tấn công có thể tiếp tục hoạt động ngay sau khi người dùng xác thực lại. Vì vậy, hành động nguy cơ cao có thể cần phương thức chống phishing, xác nhận giao dịch cụ thể, đối chiếu gian lận hoặc kênh phê duyệt độc lập theo mức rủi ro.

## 9. Lưu ý trải nghiệm người dùng và khả năng phục hồi

Chính sách quá nghiêm có thể khiến người dùng quen bấm đồng ý mọi yêu cầu, tạo ra hiện tượng **authentication fatigue**. Hệ thống nên:

1. **Giải thích lý do cụ thể** của yêu cầu xác thực lại, chẳng hạn “Xác nhận trước khi thay đổi tài khoản nhận tiền”.
2. **Cho thấy đúng nội dung thao tác** sau khi người dùng quay lại từ IdP; không khôi phục một yêu cầu đã âm thầm thay đổi tham số.
3. **Giữ luồng trong trạng thái chờ an toàn** khi xác thực thất bại hoặc người dùng hủy; không thực hiện thao tác trước.
4. **Hạn chế vòng lặp redirect** nếu AS không hỗ trợ mức bảo đảm yêu cầu. Hệ thống cần phát hiện thiếu khả năng đáp ứng và trả lỗi rõ ràng.
5. **Cung cấp đường khôi phục có kiểm soát** khi người dùng mất passkey/thiết bị MFA; không cho phép dùng quy trình khôi phục yếu để âm thầm bỏ qua chính sách của hành động nhạy cảm.
6. **Thông báo và audit** các thay đổi bảo mật quan trọng bằng cách bảo vệ dữ liệu nhạy cảm trong log. Không ghi mật khẩu, OTP, refresh token hoặc toàn bộ bearer token.

Với các giao dịch tài chính và thay đổi bảo mật, thông báo sau khi hoàn tất giúp phát hiện hoạt động bất thường nhưng **không thay thế** xác thực lại trước hành động.

## 10. Kiểm thử các trường hợp quan trọng

Một hệ thống step-up nên có các bài kiểm thử cấp API và luồng tích hợp cho những tình huống sau:

| Dữ kiện kiểm thử | Kết quả kỳ vọng |
|---|---|
| Access token còn hạn, nhưng **auth_time** quá cũ | Yêu cầu xác thực lại; **không** thực thi thay đổi |
| Access token mới được phát hành bằng refresh token, **iat** gần hiện tại nhưng **auth_time** cũ | Vẫn yêu cầu step-up |
| Có **auth_time** mới nhưng **acr** không đạt yêu cầu đã định | Không thực thi; yêu cầu mức bảo đảm thích hợp |
| API không nhận được bằng chứng auth_time/acr tin cậy cần cho chính sách | Từ chối hoặc yêu cầu step-up; **không suy đoán đạt** |
| Token có audience của một API khác hoặc là ID token | Từ chối vì mục đích token không phù hợp |
| Người dùng xác thực lại thành công nhưng thiếu quyền trên tài nguyên | **403** hoặc từ chối tương đương; không nâng quyền nghiệp vụ |
| Receipt gắn giao dịch A được dùng cho giao dịch B | Từ chối |
| Receipt đã sử dụng, hết hạn, sai subject/tenant/session | Từ chối |
| Giá trị hoặc người nhận bị đổi sau bước xác nhận | Vô hiệu bằng chứng cũ; yêu cầu xác nhận lại |
| Hai request dùng cùng bằng chứng đến đồng thời | Tối đa một thao tác có hiệu lực theo chính sách/idempotency |
| Người dùng hủy reauthentication hoặc provider không đáp ứng ACR | Giữ trạng thái chưa hoàn thành; không tự bỏ qua challenge |
| Client dùng **client_credentials** nhưng gửi một user ID tự khai báo | Không coi đó là bằng chứng người dùng đã xác thực lại |

### Bài tập tình huống

Hệ thống quản trị có endpoint **POST /admin/api-keys**. Người dùng là admin đã đăng nhập lúc 09:00. Đến 17:00, trình duyệt tự làm mới access token, tạo token có **iat=16:59** và **exp=17:14**. API kiểm chữ ký, scope **api-key:create** và thấy token còn hạn nên tạo API key quản trị ngay.

**Câu hỏi 1:** Kiểm tra nào còn thiếu?

**Đáp án:** API chưa đánh giá **độ mới và mức bảo đảm của lần xác thực người dùng** theo chính sách cho thao tác tạo bí mật có quyền cao. **iat=16:59** là thời điểm cấp token, không phải bằng chứng reauthentication lúc 16:59. Cần kiểm **auth_time** hoặc trạng thái tương đương từ nguồn tin cậy và yêu cầu step-up khi không đạt.

**Câu hỏi 2:** Nếu admin xác thực lại thành công nhưng đã bị thu hồi quyền tạo API key, API có được tạo key không?

**Đáp án:** Không. Reauthentication chỉ đáp ứng điều kiện xác thực; **AuthZ vẫn phải kiểm quyền hiện thời** trước khi thực hiện.

**Câu hỏi 3:** Nếu bằng chứng xác nhận được phát hành để tạo API key chỉ có quyền đọc, có thể đổi tham số thành key quản trị trong request cuối không?

**Đáp án:** Không được. API cần ràng buộc bằng chứng, nếu dùng, với **đúng mục đích, quyền, chủ thể và tham số được phê duyệt**; thay đổi phạm vi quyền phải cần quyết định xác nhận mới.

## 11. Checklist triển khai

Trước khi bật một endpoint nhạy cảm trong production, hãy trả lời:

1. Hành động nào **bắt buộc** xác thực lại, với ngưỡng độ mới và mức bảo đảm nào theo chính sách?
2. Dữ liệu **auth_time**, **acr** hoặc ngữ cảnh tương đương đến từ **issuer/IdP đáng tin** hay từ client tự khai báo?
3. API có phân biệt **iat**, **exp**, refresh token và sự kiện xác thực người dùng không?
4. Client có xử lý challenge step-up đúng chuẩn/đúng hợp đồng, kiểm OIDC response và tránh redirect loop không?
5. API có kiểm **issuer, audience, mục đích token, scope, quyền trên tài nguyên và tenant** trước khi thực thi không?
6. Nếu có receipt xác nhận, nó được gắn với **đúng subject/session/giao dịch**, hết hạn nhanh và chống phát lại không?
7. Thao tác được cập nhật **nguyên tử**, kiểm lại dữ liệu trước khi ghi và có bảo vệ idempotency/race condition không?
8. Hệ thống có ghi audit an toàn, thông báo thay đổi quan trọng và thu hồi phiên/token khi nghi ngờ bị chiếm quyền không?
9. Người dùng mất phương thức MFA hoặc AS không hỗ trợ mức yêu cầu có đường xử lý an toàn không?

**Ghi nhớ:** Token hợp lệ không đồng nghĩa lần xác thực người dùng đủ **mới**, đủ **mạnh**, hoặc đã xác nhận **đúng giao dịch**. Reauthentication bảo vệ hành động nhạy cảm khi được thực thi **ở server**, dựa trên ngữ cảnh xác thực đáng tin và luôn kết hợp với phân quyền trên tài nguyên, ràng buộc giao dịch và kiểm soát vòng đời token.
