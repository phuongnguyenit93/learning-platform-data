# Quy tắc xác minh riêng cho từng mục đích sử dụng

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Hợp đồng token  
> **Phạm vi:** Thiết kế quy tắc xác minh JWT theo mục đích ở mức giao thức và hệ thống; không phụ thuộc Java, Spring hay framework cụ thể.

Một hệ thống có thể dùng JWT cho nhiều việc: gọi API, xác nhận đăng nhập, khôi phục mật khẩu, xác minh email hoặc giao tiếp giữa các dịch vụ. Các token này có thể cùng dùng JSON, cùng issuer và thậm chí cùng thuật toán ký, nhưng **không được xác minh bằng một bộ quy tắc chung rồi chấp nhận ở mọi nơi**.

Ví dụ, ID token chứng minh kết quả xác thực cho một ứng dụng OIDC; access token cấp quyền truy cập tài nguyên; password reset token cho phép hoàn tất một quy trình khôi phục cụ thể. Nếu API đơn hàng chỉ kiểm tra chữ ký và issuer, nó có thể nhận nhầm ID token hoặc reset token. Nếu endpoint khôi phục mật khẩu chỉ kiểm tra token chưa hết hạn, nó có thể nhận nhầm access token còn hiệu lực.

Mỗi mục đích cần một **validation profile** (hồ sơ xác minh) riêng. Hồ sơ quy định token nào được chấp nhận, ai phát hành, ai nhận, claim nào bắt buộc, cách xác minh mật mã, thời hạn, quyền và trạng thái nghiệp vụ. Bên nhận phải chọn hồ sơ dựa trên chức năng/điểm tiếp nhận đã cấu hình, rồi kiểm tra toàn bộ điều kiện của chính hồ sơ đó.

## 1. Nguyên tắc xác minh theo mục đích

### 1.1. Mục đích quyết định quy tắc kiểm tra

Trước khi xác minh một JWT, cần trả lời:

1. **Token này đại diện cho điều gì?** Quyền gọi API, kết quả đăng nhập, yêu cầu khôi phục hay một giao dịch?
2. **Ai phát hành?** Issuer nào được tin cậy cho mục đích này?
3. **Ai nhận?** Client, API hoặc endpoint nào được phép dùng token?
4. **Điều kiện nào bắt buộc?** Token type, claim, thuật toán, khóa, thời hạn, scope và ràng buộc bổ sung nào?
5. **Có cần trạng thái bên ngoài không?** Token có thể bị thu hồi, đã sử dụng, bị thay thế hoặc gắn với một yêu cầu cụ thể không?

Một chữ ký hợp lệ chỉ hoàn thành bước bảo vệ mật mã. Nó không chứng minh token đúng mục đích, đúng audience hoặc đủ quyền.

### 1.2. Hồ sơ xác minh là một tập điều kiện thống nhất

Mỗi hồ sơ nên gắn các thuộc tính với nhau:

| Thành phần | Câu hỏi xác minh |
|---|---|
| **Receiver / endpoint** | Token được gửi đến đúng chức năng tiếp nhận? |
| **Issuer (iss)** | Nguồn phát hành có nằm trong danh sách tin cậy của mục đích này? |
| **Audience (aud)** | Token có được cấp cho đúng client hoặc tài nguyên? |
| **Token type / profile** | Đây có đúng loại token mà endpoint hỗ trợ? |
| **Cryptographic policy** | Thuật toán, khóa và serialization có đúng hợp đồng? |
| **Required claims** | Các claim bắt buộc có mặt và đúng kiểu/miền giá trị? |
| **Time policy** | Token đã có hiệu lực, chưa hết hạn và đủ mới? |
| **Authorization** | Scope, quyền, chủ thể và tài nguyên có phù hợp thao tác? |
| **State / replay policy** | Token còn hiệu lực nghiệp vụ, chưa bị thu hồi hoặc sử dụng? |

Không ghép issuer từ hồ sơ A, audience từ hồ sơ B và token type từ hồ sơ C để tạo ra một tổ hợp mà không hồ sơ nào cho phép. Các điều kiện phải cùng thỏa mãn trong **một validation profile**.

### 1.3. Các mục đích phải được phân biệt rõ

| Mục đích | Bên nhận điển hình | Câu hỏi chính |
|---|---|---|
| **Access token** | Resource server / API | Token có cấp quyền gọi API này và thao tác này không? |
| **OIDC ID token** | Relying party / client | Kết quả xác thực có dành cho chính client này và khớp phiên đăng nhập không? |
| **Refresh token** | Authorization server / token endpoint | Có được phép cấp token mới từ thông tin xác thực này không? |
| **Password reset token** | Endpoint khôi phục tài khoản | Token có gắn với yêu cầu khôi phục còn hiệu lực và chưa dùng không? |
| **Email verification token** | Endpoint xác minh địa chỉ email | Token có xác nhận đúng địa chỉ và đúng yêu cầu chưa hoàn tất không? |
| **Service-to-service token** | API của dịch vụ đích | Dịch vụ gọi có danh tính và quyền phù hợp với tài nguyên đích không? |
| **Action / transaction token** | Endpoint xác nhận hành động | Token có gắn đúng giao dịch, dữ liệu và ý định đã được phê duyệt không? |

Không phải mọi loại token đều phải là JWT. Refresh token, mã xác minh email hoặc token khôi phục có thể là opaque token; nguyên tắc phân tách mục đích và kiểm tra trạng thái vẫn áp dụng.

## 2. Quy trình chọn và chạy validation profile

### 2.1. Chọn hồ sơ từ điểm tiếp nhận tin cậy

Điểm tiếp nhận quyết định hồ sơ nào được dùng. Ví dụ:

- Endpoint API đơn hàng chỉ chọn profile access token cho Orders API.
- OIDC client chỉ chọn profile ID token của chính client.
- Token endpoint chọn profile refresh token theo OAuth.
- Endpoint khôi phục mật khẩu chỉ chọn profile recovery.

Không chọn profile dựa hoàn toàn vào claim hoặc header chưa xác minh do token gửi lên. Có thể đọc cấu trúc chưa tin cậy để chọn một ứng viên trong tập profile đã cấu hình, nhưng phải xác minh toàn bộ điều kiện và từ chối nếu không khớp.

### 2.2. Pipeline xác minh chung

Mọi profile có thể dùng một khung xử lý chung, nhưng **các giá trị và điều kiện bắt buộc khác nhau theo mục đích**:

~~~mermaid
flowchart TD
    A[Request đến endpoint] --> B[Chọn validation profile theo endpoint]
    B --> C[Kiểm tra cấu trúc và giới hạn đầu vào]
    C --> D[Kiểm tra dạng token, header và thuật toán được phép]
    D --> E[Chọn khóa từ nguồn tin cậy của issuer]
    E --> F[Xác minh chữ ký hoặc giải mã theo profile]
    F --> G[Kiểm tra iss, aud và token type]
    G --> H[Kiểm tra claims, thời gian và schema]
    H --> I[Kiểm tra trạng thái, replay và ràng buộc giao dịch]
    I --> J[Kiểm tra quyền theo thao tác/tài nguyên]
    J --> K{Tất cả điều kiện của profile đạt?}
    K -->|Không| X[Từ chối]
    K -->|Có| L[Cho phép đúng hành động của profile]
~~~

Trình tự cụ thể có thể khác ở các bước không tạo tác dụng phụ. Không được cấp quyền hoặc thực hiện hành động nghiệp vụ dựa trên claim trước khi hoàn tất xác minh mật mã và các điều kiện cần thiết.

### 2.3. Pseudocode tổng quát

~~~text
validateForEndpoint(endpoint, token, request):
    profile = trustedRegistry.profileFor(endpoint)
    reject nếu profile không tồn tại

    parsed = parseAsUntrusted(token)
    reject nếu cấu trúc hoặc kích thước không hợp lệ
    reject nếu format, alg, typ hoặc header không nằm trong profile

    key = selectKeyFromTrustedSource(profile.issuer, parsed.kid)
    reject nếu khóa không phù hợp profile
    verifySignatureOrDecryptExactlyAsProfileRequires()

    validateIssuerAudienceAndTokenType(profile)
    validateRequiredClaimsAndTypes(profile)
    validateTimeAndFreshness(profile)
    validateStateAndReplayRules(profile, request)
    validateAuthorizationForOperation(profile, request)

    ACCEPT chỉ cho mục đích được profile định nghĩa
~~~

Một token có thể vượt qua xác minh cho profile này nhưng vẫn không hợp lệ ở profile khác. Kết quả xác minh phải gắn với **endpoint, profile, audience và mục đích cụ thể**; không tạo một cờ “JWT hợp lệ ở mọi nơi”.

## 3. Xác minh Access Token tại Resource Server

Access token được cấp để client truy cập một hoặc nhiều tài nguyên theo quyền đã cấp. Resource server cần xác minh token theo profile access token được hai bên thống nhất.

### 3.1. Điều kiện cơ bản

Với OAuth 2.0 JWT Access Token theo RFC 9068, resource server cần kiểm tra các yêu cầu của profile, bao gồm:

- Chữ ký JWS hợp lệ theo thuật toán và khóa được cấu hình tin cậy.
- **iss** khớp authorization server được tin cậy.
- **aud** chứa định danh resource server dự kiến.
- JOSE **typ** theo hồ sơ access token, thường là **at+jwt** hoặc media type tương ứng được profile chấp nhận.
- Các claim bắt buộc của RFC 9068 như **exp**, **iat**, **jti**, **sub**, **client_id** và các quy tắc liên quan.
- Thời hạn và các ràng buộc bổ sung của hệ thống.

Không dùng ID token thay access token. Không chấp nhận access token dành cho API khác chỉ vì cùng issuer.

### 3.2. Kiểm tra quyền

Sau khi token được xác minh, resource server còn phải kiểm tra:

1. **Scope** có bao gồm quyền cần cho endpoint/thao tác không?
2. Chủ thể hoặc client có được phép thực hiện hành động đó không?
3. Tài nguyên cụ thể có thuộc phạm vi truy cập của chủ thể/tenant không?
4. Token có bị thu hồi hoặc bị giới hạn bởi chính sách hiện hành không?

Ví dụ token:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "https://api.orders.example.com",
  "client_id": "storefront-web",
  "scope": "orders:read orders:create",
  "iat": 1794800000,
  "exp": 1794800600,
  "jti": "at-7f19a2"
}
~~~

Payload chỉ minh họa, chưa phải JWT đã ký. Với yêu cầu đọc đơn hàng, API kiểm tra scope **orders:read**, sau đó kiểm tra user-42 có quyền đọc đúng đơn hàng được yêu cầu hay không. Scope không tự cấp quyền trên mọi đơn hàng.

### 3.3. Kết quả

- Token sai chữ ký, issuer, audience, type, claim hoặc thời hạn: từ chối xác thực.
- Token hợp lệ nhưng thiếu scope/quyền: từ chối quyền.
- Token hợp lệ và được phép cho thao tác/tài nguyên cụ thể: tiếp tục xử lý.

## 4. Xác minh OIDC ID Token tại Relying Party

ID token thuộc OpenID Connect. Nó truyền kết quả xác thực về cho client (relying party); mục đích của nó khác access token.

### 4.1. Kiểm tra theo OIDC

Relying party phải áp dụng quy tắc xác minh ID token của OpenID Connect Core, bao gồm các điều kiện phù hợp với flow:

- **iss** khớp issuer đã cấu hình và tin cậy.
- **aud** chứa **client_id** của chính relying party.
- Nếu có nhiều audience, kiểm tra **azp** theo yêu cầu OIDC; khi **azp** có mặt phải xác minh giá trị phù hợp.
- Chữ ký, thuật toán, khóa và các yêu cầu bảo vệ token theo discovery/trust configuration.
- **exp** chưa hết hạn; **iat** hợp lý theo policy.
- **nonce** khớp giá trị client đã tạo và lưu cho authentication request khi flow yêu cầu.
- **auth_time** được kiểm tra khi client yêu cầu xác thực mới qua **max_age** hoặc policy tương ứng.
- Các điều kiện bổ sung như **at_hash** hoặc **c_hash** khi được flow/profile yêu cầu.

Không tự rút gọn kiểm tra OIDC thành “đúng chữ ký và đúng sub”. **sub** định danh chủ thể; nó không chứng minh ID token được phát hành cho đúng client hoặc khớp đúng phiên đăng nhập.

### 4.2. Không gửi ID token tới API như access token

ID token có audience là client ứng dụng; API thường yêu cầu audience của chính API. API phải từ chối ID token khi endpoint cần access token, kể cả khi ID token được ký bởi cùng issuer.

### 4.3. Kết quả

ID token hợp lệ cho client chỉ chứng minh kết quả xác thực theo OIDC trong ngữ cảnh client đó. Nó không tự cấp quyền gọi Orders API, Inventory API hay bất kỳ resource server nào.

## 5. Xác minh Refresh Token tại Authorization Server

Refresh token được dùng để xin access token mới. Trong OAuth, refresh token có thể là chuỗi opaque; không được giả định nó luôn là JWT.

### 5.1. Chỉ token endpoint xử lý refresh token

Resource server không chấp nhận refresh token để gọi API. Authorization server/token endpoint cần kiểm tra:

- Token được phát hành bởi chính authorization server và thuộc client/grant tương ứng.
- Token còn hạn và chưa bị thu hồi.
- Token gắn với đúng client; nếu là public client, áp dụng biện pháp ràng buộc sender hoặc rotation theo chính sách OAuth.
- Grant, user/session và quyền đã cấp vẫn còn hiệu lực.
- Nếu refresh token được xoay vòng, token cũ chưa bị sử dụng lại.
- Scope/resource yêu cầu mới không vượt quá quyền đã được cấp ban đầu và quy tắc giao thức.

### 5.2. Rotation và reuse detection

Khi authorization server áp dụng refresh token rotation, mỗi lần refresh thành công sẽ phát hành token mới và vô hiệu hóa token cũ. Nếu token cũ bị gửi lại, server có thể phát hiện reuse và thu hồi nhóm token/grant liên quan theo chính sách.

Đối với public clients, OAuth Security BCP (RFC 9700) yêu cầu cơ chế bảo vệ refresh token phù hợp, chẳng hạn sender-constrained refresh token hoặc rotation có phát hiện reuse. Chi tiết phụ thuộc loại client và profile OAuth đang áp dụng.

### 5.3. Không nhầm refresh token với access token

Refresh token không có scope để gọi resource API theo cách access token có. Nó là thông tin xác thực dành cho authorization server để yêu cầu cấp access token mới. Dùng refresh token tại API tài nguyên phải bị từ chối.

## 6. Xác minh Password Reset Token

Password reset token là token nghiệp vụ cho phép hoàn tất một yêu cầu khôi phục tài khoản. Đây thường là loại token tự thiết kế; cần một hợp đồng riêng và không nên tái sử dụng access token.

### 6.1. Điều kiện cần kiểm tra

Nếu triển khai dưới dạng JWT, endpoint recovery có thể yêu cầu:

- **iss** là issuer phát hành token khôi phục.
- **aud** là endpoint/dịch vụ recovery cụ thể.
- **typ** hoặc claim purpose theo hợp đồng biểu thị rõ **password_reset**.
- **sub** xác định tài khoản được khôi phục.
- **exp** ngắn và **iat** hợp lý.
- **jti** hoặc request ID liên kết tới yêu cầu khôi phục đang còn hiệu lực.
- Token chưa bị sử dụng, thu hồi hoặc thay thế bởi yêu cầu mới.
- Ràng buộc giao dịch như account ID, recovery request ID hoặc kênh đã xác minh khớp yêu cầu hiện tại.

Claim purpose là quy ước ứng dụng nếu profile không định nghĩa trường chuẩn tương ứng. Phải kiểm tra nó sau khi xác minh chữ ký và các claim tin cậy.

### 6.2. Một lần sử dụng và trạng thái phía server

Chỉ có **exp** không đủ chống phát lại. Sau khi đặt lại mật khẩu thành công, endpoint phải đánh dấu yêu cầu/token đã sử dụng. Nếu người dùng yêu cầu liên kết mới, hệ thống có thể vô hiệu hóa token trước đó.

Token khôi phục nên được tạo ngẫu nhiên đủ mạnh, gắn với một tài khoản và một yêu cầu cụ thể, có thời hạn ngắn và không chứa mật khẩu mới. Mật khẩu mới được gửi qua request riêng trên kênh bảo vệ; không nhét mật khẩu vào JWT.

### 6.3. Kết quả

Token recovery còn hạn nhưng đã sử dụng phải bị từ chối. Access token hoặc ID token được gửi tới endpoint recovery cũng phải bị từ chối dù chữ ký hợp lệ.

## 7. Xác minh Email Verification Token

Email verification token chứng minh quyền kiểm soát một địa chỉ email trong một quy trình cụ thể. Đây cũng là token nghiệp vụ riêng, có thể là JWT hoặc opaque token.

### 7.1. Điều kiện xác minh

Với JWT, endpoint xác minh email có thể yêu cầu:

- Issuer và audience dành riêng cho quy trình xác minh email.
- Loại token hoặc **purpose** rõ ràng, ví dụ **email_verification**.
- Claim định danh người dùng và địa chỉ email cần xác minh, hoặc một request ID liên kết với dữ liệu phía server.
- Thời hạn ngắn theo chính sách.
- **jti** hoặc mã yêu cầu duy nhất.
- Trạng thái email chưa được xác minh và token chưa được dùng/thu hồi.
- Nếu địa chỉ email đã thay đổi sau khi token được phát hành, token cũ không còn được chấp nhận.

Không coi việc token chứa một chuỗi email là bằng chứng đủ. Hệ thống phải xác minh token được phát hành cho đúng yêu cầu và địa chỉ đang chờ xác minh.

### 7.2. Chống replay và thay đổi địa chỉ

Sau khi xác minh thành công, đánh dấu yêu cầu đã hoàn tất. Nếu người dùng đổi địa chỉ email, tạo yêu cầu xác minh mới và vô hiệu hóa token cũ. Không cho phép token cũ xác minh một địa chỉ khác chỉ vì nó cùng thuộc một tài khoản.

## 8. Xác minh Service-to-Service Token

Token giữa các dịch vụ thường đại diện cho một workload/client, không nhất thiết đại diện cho người dùng cuối.

### 8.1. Danh tính máy gọi và bên nhận

Resource server nên xác minh:

- Issuer dành cho môi trường/workload đã tin cậy.
- Audience chính xác của dịch vụ đích.
- Client/service identity theo profile, ví dụ **client_id** hoặc claim định danh workload.
- Token type/profile dành cho access token giữa các dịch vụ.
- Scope/permission tối thiểu cho API đích.
- Thời hạn ngắn và chính sách thu hồi.
- Ràng buộc sender nếu hệ thống yêu cầu, chẳng hạn mTLS hoặc DPoP theo giao thức hỗ trợ.

Không suy ra quyền của người dùng cuối từ danh tính dịch vụ. Nếu dịch vụ gọi API thay mặt người dùng, hợp đồng cần thể hiện rõ mô hình delegated access và phân biệt client với subject.

### 8.2. Token ràng buộc người gửi

Với bearer token, bên nào nắm token đều có thể thử sử dụng token tại đúng audience. Một số hệ thống giảm rủi ro bằng sender-constrained token:

- **mTLS certificate-bound access token** theo RFC 8705 gắn token với chứng thư client.
- **DPoP** theo RFC 9449 gắn việc sử dụng token với bằng chứng sở hữu khóa và từng request.

Khi dùng các cơ chế này, resource server phải xác minh bằng chứng sở hữu theo đúng chuẩn. Chỉ đọc claim **cnf** hoặc kiểm tra có chứng thư/khóa là chưa đủ.

## 9. Xác minh Action hoặc Transaction Token

Một token có thể đại diện cho việc phê duyệt một hành động cụ thể, chẳng hạn xác nhận chuyển tiền, duyệt đơn hoặc chấp thuận thay đổi thông tin bảo mật. Đây là mục đích nhạy cảm và cần gắn chặt token với giao dịch.

### 9.1. Ràng buộc với nội dung giao dịch

Hồ sơ có thể yêu cầu:

- **iss**, **aud** và token type/purpose dành riêng cho action.
- **sub** là người thực hiện hoặc phê duyệt.
- **jti**/transaction ID duy nhất.
- ID đối tượng, số tiền, loại thao tác hoặc hash dữ liệu giao dịch theo schema đã định nghĩa.
- **iat**, **exp** ngắn và **nbf** nếu có lịch kích hoạt.
- Trạng thái giao dịch còn chờ, chưa bị hủy hoặc hoàn tất.
- Bằng chứng xác thực mạnh hoặc xác nhận bổ sung nếu rủi ro yêu cầu.

Token phải gắn với chính xác dữ liệu đã được người dùng phê duyệt. Nếu số tiền, người nhận hoặc nội dung giao dịch thay đổi, token cũ không được tái sử dụng để phê duyệt dữ liệu mới.

### 9.2. Một lần dùng và tính nguyên vẹn của giao dịch

Sau khi thực hiện thành công, đánh dấu token/giao dịch đã tiêu thụ theo cơ chế chống replay. Việc xác minh chữ ký không thay thế kiểm tra trạng thái giao dịch và quyền tại thời điểm commit.

## 10. Ma trận so sánh validation profile

| Điều kiện | Access token | OIDC ID token | Refresh token | Password reset | Email verify | Service-to-service |
|---|---|---|---|---|---|---|
| Bên nhận | Resource server | OIDC client | Authorization server | Recovery endpoint | Verification endpoint | API đích |
| Audience | API/resource | Client ID | Theo contract/token endpoint | Recovery service | Verification service | Service đích |
| Loại token | Access token profile | ID token theo OIDC | Refresh token theo OAuth | Purpose riêng | Purpose riêng | Access token/workload profile |
| Issuer | Authorization server tin cậy | OIDC issuer | Authorization server | Issuer recovery | Issuer verification | Issuer workload/authorization |
| Claim thời gian | exp; iat; nbf khi cần | exp, iat; auth_time khi yêu cầu | Expiry/state theo cơ chế cấp phát | exp ngắn, iat | exp ngắn | exp ngắn, iat |
| Quyền | Scope + quyền tài nguyên | Không thay thế quyền API | Quyền xin token mới | Quyền hoàn tất yêu cầu recovery | Quyền xác minh đúng email | Scope/workload permission |
| Trạng thái/replay | Revocation khi cần | Nonce/session theo OIDC | Rotation/reuse/revocation | Single-use | Single-use | Revocation/sender constraint khi cần |
| Không được dùng thay | ID/refresh/recovery token | Access token | Access token | Access/ID token | Access/reset token | Token của service khác |

Ma trận là hướng dẫn thiết kế; chi tiết cuối cùng phải theo chuẩn/profile và hợp đồng cụ thể. Không phải mọi token đều có cùng claim hoặc cùng cơ chế trạng thái.

## 11. Ví dụ cấu hình nhiều profile

Ví dụ YAML khái niệm:

~~~yaml
validation_profiles:
  orders_access:
    receiver: orders-api
    profile: oauth2-jwt-access-rfc9068
    issuer: "https://id.example.com"
    audience: "https://api.orders.example.com"
    accepted_typ: ["at+jwt", "application/at+jwt"]
    required_scope: "orders:read"
    max_lifetime_seconds: 600

  storefront_id:
    receiver: storefront-web
    profile: openid-connect-id-token
    issuer: "https://id.example.com"
    audience: "storefront-web"
    require_nonce: true
    validate_azp_when_required: true

  account_recovery:
    receiver: account-recovery
    profile: application-password-reset
    issuer: "https://id.example.com"
    audience: "https://account.example.com/recovery"
    required_purpose: "password_reset"
    single_use: true
    max_lifetime_seconds: 900

  email_verification:
    receiver: email-verification
    profile: application-email-verification
    issuer: "https://id.example.com"
    audience: "https://account.example.com/email-verification"
    required_purpose: "email_verification"
    single_use: true
~~~

Đây là cấu hình minh họa, không phải schema của một thư viện. Các profile ứng dụng phải được định nghĩa cụ thể về claim, chữ ký, key source, trạng thái và xử lý lỗi. Các giá trị thời gian là ví dụ, không phải quy tắc RFC bắt buộc.

## 12. Kiểm thử âm tính theo mục đích

| ID | Đầu vào / tình huống | Endpoint | Kết quả mong đợi | Lý do |
|---|---|---|---|---|
| P1 | Access token đúng profile, audience và scope | Orders API | Có thể chấp nhận sau kiểm tra quyền tài nguyên | Đúng mục đích |
| P2 | ID token hợp lệ của web client | Orders API | Từ chối | Sai token type và audience |
| P3 | Access token của Orders API | OIDC client đang xác minh ID token | Từ chối | Access token không phải ID token |
| P4 | Refresh token còn hạn | Orders API | Từ chối | Sai bên nhận/mục đích |
| P5 | Access token còn hạn | Recovery endpoint | Từ chối | Sai purpose |
| P6 | Password reset token đã dùng | Recovery endpoint | Từ chối | Replay/single-use violation |
| P7 | Password reset token còn hạn nhưng gắn account khác | Recovery endpoint | Từ chối | Sai subject/request binding |
| P8 | Email verification token cũ sau khi email thay đổi | Verification endpoint | Từ chối | Token không còn gắn với địa chỉ hiện tại |
| P9 | Service token có audience của inventory API | Orders API | Từ chối | Sai resource audience |
| P10 | Service token đúng audience nhưng thiếu permission | API đích | Từ chối quyền | Thiếu quyền workload |
| P11 | Transaction token đúng chữ ký nhưng số tiền đã thay đổi | Payment endpoint | Từ chối | Giao dịch không còn khớp |
| P12 | Token bất kỳ có chữ ký hợp lệ nhưng issuer không nằm trong profile | Mọi endpoint | Từ chối | Issuer không được phép |
| P13 | Token có purpose không đúng profile | Endpoint recovery/email | Từ chối | Mục đích không khớp |
| P14 | Token còn exp nhưng đã bị thu hồi | Endpoint yêu cầu trạng thái | Từ chối | Revocation |

## 13. Xử lý kết quả và lỗi

Kết quả xác minh cần phân biệt:

- **Invalid token / authentication failure:** chữ ký, issuer, audience, type, claim bắt buộc, thời hạn hoặc profile sai.
- **Insufficient authorization:** token hợp lệ cho API nhưng thiếu scope, role hoặc quyền trên tài nguyên.
- **Invalid workflow state:** token nghiệp vụ hợp lệ về mật mã nhưng yêu cầu đã dùng, bị thu hồi, bị thay thế hoặc không khớp giao dịch.
- **Unsupported profile/feature:** endpoint không hỗ trợ định dạng, thuật toán hoặc extension mà token yêu cầu.
- **Verification dependency unavailable:** không thể hoàn thành kiểm tra trạng thái bắt buộc do dịch vụ phụ thuộc không khả dụng; xử lý theo availability policy đã định.

Với OAuth Bearer, lỗi token không hợp lệ thường được biểu diễn theo **401 / invalid_token** và thiếu scope có thể là **403 / insufficient_scope** theo RFC 6750. Token nghiệp vụ có thể dùng mã phản hồi theo API contract. Không tiết lộ chi tiết khóa, claim nội bộ hoặc token trong thông báo lỗi cho client.

## 14. Checklist thiết kế profile theo mục đích

**Định nghĩa**

- [ ] Mỗi endpoint có profile xác minh được chỉ định rõ.
- [ ] Profile nêu rõ mục đích, issuer, audience, token type và định dạng.
- [ ] Các profile có quy tắc loại trừ lẫn nhau ở những nơi token không được thay thế.
- [ ] Không chọn profile dựa trên claim chưa xác minh.

**Xác minh**

- [ ] Thuật toán và nguồn khóa nằm trong allowlist tin cậy.
- [ ] Claim bắt buộc, kiểu dữ liệu, thời gian và giới hạn được kiểm tra theo profile.
- [ ] Quyền scope/resource được kiểm tra sau xác minh token.
- [ ] Các claim OIDC và điều kiện flow được kiểm tra đúng khi dùng ID token.
- [ ] Refresh token chỉ được xử lý tại authorization server/token endpoint.

**Trạng thái và nghiệp vụ**

- [ ] Token một lần có cơ chế chống replay.
- [ ] Refresh token rotation/reuse được xử lý theo policy.
- [ ] Recovery/email/action token được gắn với đúng tài khoản, yêu cầu hoặc giao dịch.
- [ ] Revocation, introspection và cache được xử lý theo yêu cầu rủi ro.
- [ ] Sender-constrained token được xác minh bằng proof-of-possession khi profile yêu cầu.

**Kiểm thử và vận hành**

- [ ] Có kiểm thử chấp nhận và từ chối cho từng profile.
- [ ] Có ca thử token đúng chữ ký nhưng sai purpose, audience hoặc type.
- [ ] Có ca replay, token đã thu hồi, scope thiếu và dữ liệu giao dịch thay đổi.
- [ ] Log kết quả theo profile/contract mà không ghi token hoặc secret.
- [ ] Thay đổi profile có versioning và rollout tương thích.

**Điều cần nhớ:** Hãy xác minh JWT theo **mục đích của endpoint đang nhận nó**. Access token, ID token, refresh token và token nghiệp vụ có thể cùng là token được bảo vệ bằng mật mã, nhưng mỗi loại có audience, claim, trạng thái và hành động được phép khác nhau. Một token chỉ hợp lệ trong đúng hồ sơ mà nó được phát hành cho.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): Cấu trúc JWT và registered claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Xác minh theo từng loại JWT, explicit typing và ngăn cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Hồ sơ access token dành cho resource server.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token và quy tắc xác minh của relying party.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Access token, refresh token và token endpoint.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): Bảo vệ refresh token, rotation/reuse detection và thực hành OAuth hiện hành.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): Thu hồi token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): Kiểm tra trạng thái token.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): Sender-constrained token bằng mTLS.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): Ràng buộc token với bằng chứng sở hữu khóa theo request.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Sử dụng Bearer token và phản hồi lỗi.
