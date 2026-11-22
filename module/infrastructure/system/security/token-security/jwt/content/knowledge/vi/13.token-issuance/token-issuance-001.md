# Điều kiện xác thực trước khi phát hành JWT

> **Phạm vi:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. Bài viết trình bày nguyên tắc bảo mật chung cho hệ thống phát hành JWT, không phụ thuộc ngôn ngữ lập trình hay framework.

## 1. Vì sao phải xác thực trước khi cấp JWT?

Khi một hệ thống phát hành JSON Web Token (JWT), hệ thống đang đưa ra một **khẳng định có thể kiểm chứng** về một chủ thể (`sub`), bên phát hành (`iss`), đối tượng nhận token (`aud`) và các thông tin/đặc quyền liên quan. Chữ ký số giúp bên nhận phát hiện token bị sửa đổi và xác minh nguồn phát hành; **chữ ký không chứng minh rằng quy trình xác thực ban đầu đã đúng**. Nếu cấp token cho người chưa được xác thực hoặc gán quyền sai, một JWT được ký hợp lệ vẫn có thể tạo ra rủi ro nghiêm trọng.

Cần tách ba quyết định:

1. **Authentication (xác thực):** Bằng chứng nào cho phép hệ thống tin rằng yêu cầu đến từ người dùng, thiết bị hoặc dịch vụ được khai báo?
2. **Authorization (phân quyền):** Chủ thể đã xác thực được phép thực hiện hành động nào, với tài nguyên nào, và được nhận những phạm vi quyền (`scope`) nào?
3. **Token issuance (phát hành token):** Có đủ điều kiện để tạo token mang các claim phù hợp, có thời hạn, đúng đối tượng nhận và được bảo vệ bằng khóa ký hay chưa?

JWT là **định dạng token**, không phải phương thức đăng nhập. Nhiều JWT trong thực tế là JWS được ký, **không được mã hóa**: nội dung payload có thể đọc được sau khi giải mã Base64URL. Không đưa mật khẩu, mã OTP, khóa bí mật hay dữ liệu nhạy cảm không cần thiết vào claim.

Không phải mọi JWT đều đại diện cho người dùng vừa đăng nhập. Token dành cho dịch vụ, thiết bị, công việc máy chủ hoặc phiên được gia hạn có thể dựa trên bằng chứng khác. Điều kiện cốt lõi là **chủ thể và mức tin cậy phải được xác minh bằng cơ chế phù hợp với mục đích phát hành**.

## 2. Các điều kiện cần kiểm tra

| Nhóm điều kiện | Câu hỏi phải trả lời trước khi cấp | Khi không đạt |
| --- | --- | --- |
| Kênh và yêu cầu | Yêu cầu đi qua kênh bảo mật; loại token, luồng và đầu vào có được hỗ trợ? | Từ chối yêu cầu hoặc chuyển sang luồng an toàn |
| Bằng chứng xác thực | Thông tin đăng nhập, chứng thư, mã ủy quyền, assertion hay refresh token có thật sự hợp lệ và còn hiệu lực? | Không phát hành JWT |
| Danh tính/chủ thể | Có xác định được chủ thể đáng tin cậy, đúng loại (người dùng, dịch vụ, thiết bị)? | Không tự tạo `sub` từ dữ liệu chưa xác minh |
| Trạng thái và rủi ro | Chủ thể có bị vô hiệu hóa, khóa, thu hồi phiên hoặc yêu cầu xác thực bổ sung? | Chặn hoặc yêu cầu bước xác thực phù hợp |
| Ứng dụng yêu cầu | Client có được nhận loại token, audience, scope và luồng đang yêu cầu? | Từ chối hoặc điều chỉnh theo chính sách |
| Quyền và claim | Những quyền định đưa vào token có nguồn từ máy chủ tin cậy và được phép cấp? | Loại quyền không hợp lệ hoặc từ chối |
| Chính sách phát hành | `iss`, `sub`, `aud`, thời hạn, khóa ký và thuật toán đã được xác định an toàn? | Không ký/phát hành khi chưa đủ điều kiện |

Các kiểm tra này không nhất thiết là bảy lời gọi tuần tự. Có kiểm tra thực hiện tại cổng API, nhà cung cấp danh tính (Identity Provider), máy chủ ủy quyền hoặc dịch vụ phát hành. Điều quan trọng là **không được bỏ qua điều kiện chỉ vì một thành phần khác đã cung cấp tên người dùng hoặc claim**.

## 3. Xác thực bằng chứng theo từng luồng

### 3.1. Đăng nhập trực tiếp bằng thông tin xác thực

Ví dụ người dùng gửi tên tài khoản và mật khẩu để xin access token:

- Chỉ nhận thông tin xác thực qua kênh TLS được cấu hình đúng; xác thực dữ liệu đầu vào và giới hạn kích thước yêu cầu.
- Tra cứu danh tính từ nguồn tin cậy; kiểm tra mật khẩu với giá trị dẫn xuất đã lưu bằng thuật toán băm mật khẩu chuyên dụng như Argon2id, scrypt hoặc bcrypt, tùy chính sách hệ thống. Không so sánh mật khẩu với bản rõ đã lưu.
- Áp dụng hạn chế thử sai, giám sát bất thường và phản hồi lỗi không tiết lộ tài khoản có tồn tại hay không.
- Nếu tài khoản bật xác thực đa yếu tố (MFA), hoặc chính sách/rủi ro yêu cầu xác thực tăng cường, chỉ coi đăng nhập hoàn tất sau khi bằng chứng bổ sung hợp lệ.
- Xem lại trạng thái tài khoản và những hạn chế có thể thay đổi trong thời gian xác thực, trước thời điểm tạo token.

**Ví dụ:** Người dùng nhập đúng mật khẩu nhưng bước xác thực OTP bắt buộc thất bại. Hệ thống chưa có bằng chứng xác thực đủ mạnh cho phiên đó, nên không được cấp access token có mức quyền đăng nhập đầy đủ.

### 3.2. Đăng nhập liên kết / SSO

Khi hệ thống nhận khẳng định danh tính từ nhà cung cấp bên ngoài, việc “có một token được gửi tới” **chưa đủ** để tin vào danh tính:

- Chỉ tin những nhà cung cấp đã được cấu hình; xác minh chữ ký và thuật toán theo danh sách cho phép, khóa xác minh được gắn với đúng nhà phát hành.
- Kiểm tra các trường bắt buộc của assertion hoặc token nhận vào theo giao thức: chẳng hạn `iss`, `aud`, `exp`, `nbf` nếu có, và `nonce` khi luồng OpenID Connect yêu cầu; kiểm tra trạng thái, tính nhất quán và khả năng sử dụng một lần của mã ủy quyền nếu áp dụng.
- Ánh xạ định danh từ nhà cung cấp bên ngoài sang chủ thể nội bộ bằng quy tắc được kiểm soát. Không mặc định email hoặc tên hiển thị do client cung cấp là định danh đã xác minh.
- Chỉ sau khi thông tin từ nguồn ngoài đã được xác minh, hệ thống mới xét cấp **JWT của chính mình**, với `iss`, `aud` và quyền do chính mình quyết định.

**Ví dụ:** Một ID token được ký đúng nhưng có `aud` dành cho ứng dụng khác. Hệ thống phải từ chối sử dụng token ấy làm bằng chứng đăng nhập vào ứng dụng hiện tại.

### 3.3. Dịch vụ gọi dịch vụ (machine-to-machine)

Không có người dùng đăng nhập cũng có thể phát hành JWT nếu giao thức cho phép và **danh tính ứng dụng/dịch vụ đã được xác thực**. Bằng chứng có thể là bí mật client được bảo vệ đúng cách, chứng thư mTLS, workload identity hay cơ chế xác thực tương đương.

Hệ thống phải xác minh danh tính client, loại grant/luồng được cho phép, phạm vi tài nguyên và quyền được cấp cho **chính dịch vụ đó**. Không gán `sub` của người dùng chỉ vì dịch vụ gửi lên một tên người dùng. Nếu dịch vụ hành động “thay mặt” người dùng, phải có ủy quyền/delegation hợp lệ theo giao thức riêng.

### 3.4. Gia hạn bằng refresh token

Việc đổi refresh token lấy access token mới thường **không yêu cầu nhập lại mật khẩu mỗi lần**, nhưng bản thân refresh token phải được kiểm tra như một bằng chứng được cấp trước đó:

- Kiểm tra tính hợp lệ, thời hạn, trạng thái thu hồi, liên kết với client/phiên và quy định ràng buộc với bên sở hữu (sender-constraining) nếu được áp dụng.
- Áp dụng luân chuyển refresh token (rotation), phát hiện tái sử dụng hoặc cơ chế bảo vệ tương ứng theo mô hình bảo mật.
- Đánh giá lại chính sách liên quan: tài khoản bị khóa, phiên đã bị thu hồi, quyền đã bị giảm, mức rủi ro mới hay yêu cầu đăng nhập lại.
- Không cấp thêm quyền mới chỉ vì bên gọi yêu cầu scope rộng hơn. Thông thường token mới không được vượt quá phạm vi quyền mà grant/phiên hiện tại cho phép.

Refresh token không nhất thiết có định dạng JWT; nó thường là giá trị opaque. **Không kiểm tra refresh token bằng cách mặc định giải mã nó như access JWT**.

## 4. Kiểm tra trạng thái, mức tin cậy và rủi ro

Sau khi bằng chứng đăng nhập hợp lệ, vẫn phải đánh giá chủ thể còn **đủ điều kiện nhận token** hay không. Tùy hệ thống, các điều kiện bao gồm:

- Tài khoản hoặc dịch vụ chưa bị khóa, vô hiệu hóa hay xóa; chính sách tổ chức/khách hàng còn cho phép truy cập.
- Phiên, thiết bị hoặc grant chưa bị thu hồi; yêu cầu chưa vượt hạn mức hay vi phạm chính sách chống lạm dụng.
- Mức xác thực vừa đạt đáp ứng thao tác dự kiến. Quyền nhạy cảm có thể cần **step-up authentication** (ví dụ xác thực lại bằng MFA), ngay cả khi phiên thông thường vẫn hợp lệ.
- Thông tin xác minh bắt buộc cho nghiệp vụ (ví dụ email đã xác nhận trước khi truy cập tính năng cụ thể) được đánh giá theo đúng chính sách; không mặc định mọi hệ thống đều bắt buộc điều kiện ấy.
- Các tín hiệu bất thường như thay đổi thiết bị, địa điểm truy cập, tốc độ đăng nhập hoặc dấu hiệu chiếm đoạt phiên được xử lý theo chính sách rủi ro.

**Trạng thái “đã đăng nhập” không đồng nghĩa “được cấp mọi quyền”.** Hệ thống có thể cho phép xác thực thành công nhưng chỉ cấp token với quyền hạn chế, yêu cầu xác thực bổ sung hoặc từ chối cấp token cho một audience cụ thể.

## 5. Kiểm tra quyền cấp token và các claim trước khi ký

Một yêu cầu phát hành thường có các tham số như loại token, `scope`, `audience`, client và thời lượng. Không lấy nguyên các giá trị bên gọi gửi lên làm nội dung JWT.

| Claim / thông tin | Nguyên tắc xác định |
| --- | --- |
| `iss` (issuer) | Do máy chủ phát hành cấu hình; không nhận giá trị tùy ý từ client |
| `sub` (subject) | Lấy từ định danh đã được xác thực/ánh xạ đáng tin cậy; nên ổn định, không tiết lộ dữ liệu không cần thiết |
| `aud` (audience) | Chỉ định đúng dịch vụ chấp nhận token; phải là audience được chính sách cho phép |
| `iat`, `nbf`, `exp` | Dựa vào đồng hồ máy chủ, thời hạn và giới hạn theo loại token; `nbf` là tùy chọn trong nhiều ngữ cảnh |
| `jti` | Định danh token duy nhất khi cần hỗ trợ theo dõi, chống phát lại hoặc thu hồi |
| `scope` / quyền / role | Lấy từ quyết định phân quyền phía máy chủ; giới hạn bởi quyền của chủ thể, client, grant và tài nguyên |
| `amr` / `acr` (nếu dùng) | Chỉ phản ánh phương thức hoặc mức xác thực đã thực sự đạt, theo đúng ngữ nghĩa của giao thức |

Ví dụ client yêu cầu `orders:read orders:delete` nhưng chỉ được phép đọc đơn hàng: máy chủ có thể chỉ cấp `orders:read` nếu giao thức và chính sách cho phép cấp tập con, hoặc từ chối yêu cầu. **Không tin một trường `role: admin` trong request** để tạo role tương ứng trong JWT.

Trước khi ký cần bảo đảm:

1. Loại token và cấu trúc claim phù hợp giao thức đang áp dụng; **ID token và access token có mục đích khác nhau** và không thể tùy tiện hoán đổi.
2. Thời gian sống được giới hạn theo chính sách và mức rủi ro; đồng hồ máy chủ được đồng bộ. Hạn chế token sống quá lâu vì token đã phát hành có thể vẫn còn hiệu lực sau khi quyền thay đổi.
3. Khóa ký thuộc quyền kiểm soát của issuer, còn dùng được, thuật toán được chọn từ cấu hình cố định/danh sách cho phép; thông tin `kid` không được biến thành đường dẫn hoặc lệnh truy xuất khóa tùy ý.
4. Không đưa bí mật, dữ liệu cá nhân không cần thiết hoặc quyền vượt quá nhu cầu vào payload. Khi cần giữ bí mật claim, sử dụng cơ chế mã hóa thích hợp hoặc không chứa dữ liệu ấy trong token.
5. Cơ chế ghi nhận sự kiện phát hành có đủ thông tin phục vụ kiểm toán (chủ thể, client, thời điểm, kết quả, mã tương quan), nhưng không ghi mật khẩu, OTP, refresh token hoặc JWT nguyên vẹn vào log.

Những điều kiện này là **kiểm tra trước khi phát hành**. Sau khi nhận JWT, resource server **vẫn phải** tự xác minh chữ ký, issuer, audience, thời gian, loại token và chính sách phân quyền ở thời điểm sử dụng.

## 6. Quy trình ra quyết định mẫu

~~~mermaid
flowchart TD
    A["Nhận yêu cầu phát hành"] --> B{"Kênh, client và luồng hợp lệ?"}
    B -- "Không" --> X["Từ chối và ghi nhận an toàn"]
    B -- "Có" --> C["Kiểm chứng bằng chứng xác thực theo luồng"]
    C --> D{"Xác thực đạt yêu cầu?"}
    D -- "Không" --> X
    D -- "Có" --> E["Kiểm tra trạng thái và tín hiệu rủi ro"]
    E --> F{"Cần xác thực bổ sung?"}
    F -- "Có" --> G["Thực hiện step-up / MFA theo chính sách"]
    G --> H{"Đạt?"}
    H -- "Không" --> X
    H -- "Có" --> I["Quyết định quyền, scope, audience"]
    F -- "Không" --> I
    I --> J{"Được phép cấp token?"}
    J -- "Không" --> X
    J -- "Có" --> K["Lập claim, thời hạn, chọn khóa ký"]
    K --> L{"Chính sách token và khóa đạt?"}
    L -- "Không" --> X
    L -- "Có" --> M["Ký JWT, ghi nhận sự kiện, trả token qua kênh an toàn"]
~~~

*Một sơ đồ luồng thể hiện các cổng quyết định; từng hệ thống có thể phân bố kiểm tra giữa các thành phần khác nhau.*

Mã giả dưới đây minh họa **nguyên tắc**, không gắn với thư viện hoặc nền tảng cụ thể:

~~~text
function issueJwt(request, context):
    requireAllowedSecureChannel(context)
    flow   = resolveAndValidateFlow(request)
    client = validateClientForFlow(request, flow)

    proof = verifyCredentialOrGrant(request, flow, client)
    if not proof.valid:
        return reject("authentication_failed")

    subject = resolveTrustedSubject(proof, flow)
    if not subject.eligible:
        return reject("subject_not_eligible")

    if riskPolicy.requiresStepUp(subject, request, proof):
        if not verifyRequiredStepUp(subject, request):
            return reject("additional_authentication_required")

    audience = selectAllowedAudience(client, request, flow)
    scopes = authorizeScopes(subject, client, proof.grant, audience, request)
    if not issuancePolicy.permits(subject, client, audience, scopes):
        return reject("token_not_permitted")

    claims = buildServerControlledClaims(
        issuer = configuredIssuer,
        subject = subject.stableId,
        audience = audience,
        scopes = scopes,
        issuedAt = trustedClock.now(),
        expiresAt = issuancePolicy.expirationFor(flow),
        tokenType = issuancePolicy.tokenTypeFor(flow)
    )

    signingKey = trustedKeyStore.selectActiveSigningKey()
    requireAllowedSignatureAlgorithm(signingKey)
    token = signJwt(claims, signingKey)

    auditIssuanceWithoutLoggingSecrets(subject, client, audience, flow)
    return securelyReturnToken(token)
~~~

Các hàm giả định đã thực thi kiểm tra nội bộ và không cho phép chọn thuật toán/khóa theo dữ liệu không đáng tin cậy từ request. Xử lý lỗi phải hạn chế tiết lộ dữ liệu nhạy cảm; thông tin chi tiết có thể được ghi ở hệ thống giám sát được bảo vệ.

## 7. Ví dụ xuyên suốt

Một người dùng đăng nhập để đọc đơn hàng qua API:

1. Trình khách gửi yêu cầu đăng nhập trên HTTPS. Máy chủ xác minh mật khẩu; nếu phiên thuộc diện phải MFA thì xác minh thêm yếu tố thứ hai.
2. Hệ thống xác định `sub = user-482` từ kho danh tính, xác nhận tài khoản đang hoạt động và không có phiên bị thu hồi.
3. Client yêu cầu access token dùng cho `orders-api` với scope `orders:read`. Máy chủ xác nhận client và người dùng đều được phép truy cập; không tự động gán quyền sửa/xóa đơn hàng.
4. Máy chủ tạo claim phù hợp (ví dụ `iss`, `sub`, `aud`, `iat`, `exp`, `scope`), ký bằng khóa được quản lý và trả token an toàn.
5. Khi gọi `orders-api`, API kiểm tra token và quyền truy cập của chính đối tượng đơn hàng. Việc token có `orders:read` không tự động cho phép xem đơn hàng của mọi người dùng.

Các tình huống dẫn tới kết quả khác nhau:

| Tình huống | Kết quả trước khi cấp JWT | Lý do |
| --- | --- | --- |
| Sai mật khẩu | Từ chối | Không có bằng chứng xác thực hợp lệ |
| Đúng mật khẩu, MFA bắt buộc chưa hoàn tất | Chưa cấp token đăng nhập đầy đủ | Mức xác thực chưa đạt |
| Đăng nhập đúng, tài khoản đã bị vô hiệu hóa | Từ chối | Chủ thể không đủ điều kiện |
| SSO token dành cho client khác | Từ chối | `aud` của bằng chứng xác thực không khớp |
| Dịch vụ có chứng thư hợp lệ và được phép đọc dữ liệu | Có thể cấp token dịch vụ với scope giới hạn | Chủ thể dịch vụ được xác thực và phân quyền |
| Refresh token đã bị thu hồi hoặc bị tái sử dụng trái chính sách | Từ chối và xử lý sự kiện bảo mật | Bằng chứng gia hạn không còn đáng tin |
| Yêu cầu scope vượt quyền được cấp | Giảm scope hoặc từ chối theo chính sách | Đăng nhập thành công không tạo thêm quyền |

## 8. Các sai lầm cần tránh

- **Cấp JWT ngay khi tìm thấy tài khoản** mà chưa xác minh bằng chứng đăng nhập.
- **Dùng tên người dùng, role hoặc audience do client gửi** làm claim đã được xác thực.
- **Tin chữ ký của token ngoài hệ thống mà bỏ qua issuer, audience, thời hạn hoặc loại token.**
- **Coi token đã ký là bí mật được mã hóa** rồi nhét thông tin nhạy cảm vào payload.
- **Cấp refresh/access token mới sau khi phiên đã bị thu hồi**, hoặc cấp lại toàn bộ quyền cũ khi chính sách đã thay đổi.
- **Bỏ qua giới hạn thử sai, MFA hay kiểm soát rủi ro theo chính sách**; hoặc bắt mọi luồng dịch vụ phải có OTP của người dùng dù luồng ấy không có người dùng.
- **Không kiểm tra ở resource server**, vì cho rằng mọi quyền đã được quyết định một lần khi phát hành JWT.

## 9. Tiêu chí kiểm thử tối thiểu

Khi triển khai cổng phát hành token, nên có các bài kiểm tra bảo mật cho ít nhất các nhóm sau:

- **Bằng chứng thất bại:** sai mật khẩu, chữ ký assertion sai, `aud` không hợp lệ, mã/refresh token hết hạn hoặc bị thu hồi → không cấp JWT.
- **Chủ thể/trạng thái thất bại:** tài khoản khóa, client không được phép dùng luồng, phiên bị thu hồi, step-up chưa đạt → không cấp token có quyền tương ứng.
- **Phân quyền:** yêu cầu scope/role/audience vượt quyền → không được nâng quyền; đầu vào giả mạo `sub`, `iss` hoặc `role` không thay đổi claim đáng tin cậy.
- **Chính sách JWT:** token phát hành có `iss`, `sub`, `aud`, thời hạn và loại token đúng; thuật toán/khóa ký không được quyết định tùy ý bởi request.
- **Vận hành:** lỗi không làm lộ trạng thái tài khoản hoặc bí mật; log không chứa token/credential nguyên vẹn; áp dụng rate limit phù hợp và phát hiện sự kiện bất thường.

## 10. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và các registered claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): các thực hành bảo mật khi xây dựng và kiểm tra JWT, đặc biệt xác minh thuật toán, issuer, audience và tách loại token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): cấu trúc JWT access token trong ngữ cảnh OAuth 2.0.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): hướng dẫn bảo vệ các luồng OAuth 2.0, mã ủy quyền và refresh token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): quy tắc xác minh ID token và xác thực liên kết.

**Nguyên tắc kết luận:** JWT chỉ nên được ký và phát hành sau khi hệ thống đã xác minh đầy đủ **bằng chứng của chủ thể**, **điều kiện của client/luồng**, **quyền được cấp** và **chính sách của token**. Mỗi bên nhận JWT vẫn phải tự kiểm tra token và quyền truy cập trong ngữ cảnh của mình.