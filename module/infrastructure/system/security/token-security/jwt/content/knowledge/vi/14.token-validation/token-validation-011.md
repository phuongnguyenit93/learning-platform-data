# Chỉ sử dụng claims sau khi hoàn tất toàn bộ kiểm tra

## 1. Vì sao phải có một ranh giới rõ ràng trước khi sử dụng claims?

JWT mang theo các claims như issuer, subject, audience, thời gian, scope, role hoặc tenant. Những dữ liệu này thường ảnh hưởng trực tiếp đến danh tính và quyền truy cập trong ứng dụng. Tuy nhiên, việc đọc được payload hoặc parse được JSON không có nghĩa các claims đã đáng tin cậy.

Trước khi hoàn tất xác minh, token vẫn là dữ liệu do bên gửi cung cấp. Kẻ tấn công có thể tạo payload với subject của người khác, tự thêm role quản trị, thay audience, sửa thời hạn hoặc khai báo tenant khác. Nếu một thành phần trong hệ thống đọc payload rồi sử dụng ngay, các bước bảo vệ phía sau có thể trở nên vô nghĩa.

Một JWT chỉ được phép tạo ra ngữ cảnh claims có thể sử dụng sau khi tất cả kiểm tra bắt buộc theo policy đã thành công, bao gồm:

- Đầu vào và serialization đúng định dạng, nằm trong giới hạn tài nguyên.
- Policy xác minh được chọn từ ngữ cảnh tin cậy.
- Thuật toán và nguồn khóa được phép; khóa phù hợp với thuật toán và mục đích.
- Chữ ký JWS được xác minh hoặc JWE được giải mã xác thực thành công.
- Token profile và loại token phù hợp endpoint.
- Issuer, audience, subject, thời gian và claims bắt buộc hợp lệ.
- Trạng thái thu hồi, replay hoặc ràng buộc client/tenant/phiên đạt yêu cầu nếu policy bật.
- Mọi lớp nested JWT được xác minh đầy đủ theo đúng thứ tự.

Sau đó, ứng dụng mới được tạo một đối tượng ngữ cảnh đã xác minh (validated token context) và chuyển nó tới bước authorization. Việc này tạo ra một ranh giới rõ giữa dữ liệu thô từ bên ngoài và dữ liệu đã được xác minh theo chính sách.

Nội dung thuộc Security - JSON Web Token (JWT), áp dụng chung cho mọi ngôn ngữ và nền tảng, không phụ thuộc Java hoặc Spring Security.

## 2. Parse được không đồng nghĩa với đã xác minh

Một thư viện có thể đọc header và payload mà chưa kiểm tra chữ ký. Các thao tác decode, parse, deserialize hoặc lấy claims từ token chỉ cho biết dữ liệu có thể được diễn giải theo một cấu trúc.

| Trạng thái | Điều đã hoàn tất | Có được dùng claims để xác định danh tính/quyền? |
| --- | --- | --- |
| Token vừa nhận | Chưa có kiểm tra | Không |
| Đã decode Base64URL | Đã đọc được byte | Không |
| Đã parse header/payload | Đã đọc được JSON và claims | Không |
| Đã chọn được khóa | Đã tìm thấy ứng viên khóa | Không |
| Chữ ký hợp lệ hoặc JWE authenticated decryption thành công | Bằng chứng mật mã đạt | Chưa; còn phải kiểm tra profile và claims |
| Claims và mọi kiểm tra bắt buộc đạt | Token phù hợp policy đã chọn | Có thể tạo validated token context |
| Authorization đạt | Chủ thể được phép thực hiện hành động cụ thể | Có thể thực hiện thao tác theo quyền |

Không dùng payload chưa xác minh để:

- Xác định người dùng đang đăng nhập.
- Gán role, scope hoặc quyền quản trị.
- Chọn tenant hoặc truy cập dữ liệu tenant.
- Chọn issuer, nguồn JWKS hoặc thuật toán được phép.
- Quyết định token còn hiệu lực hoặc chưa bị thu hồi.
- Tạo bản ghi audit nói rằng một chủ thể cụ thể đã thực hiện hành động.
- Chuyển danh tính hoặc quyền sang dịch vụ khác.

Có thể parse sơ bộ một số trường để thực hiện bước kỹ thuật được policy cho phép, chẳng hạn đọc alg/kid để tìm ứng viên khóa trong tập khóa đã tin cậy. Nhưng các giá trị này vẫn chưa được xem là danh tính hoặc quyền, và không được làm thay đổi chính sách tin cậy.

## 3. Toàn bộ validation pipeline trước khi tạo context

Một luồng tổng thể có thể được chia thành các giai đoạn. Thứ tự cụ thể có thể khác một phần tùy JWS/JWE và token profile, nhưng không được bỏ qua bước bắt buộc.

~~~mermaid
flowchart TD
    A["Nhận request và JWT thô"] --> B["Trích xuất đúng một token, kiểm tra giới hạn"]
    B --> C["Chọn policy từ endpoint/resource context tin cậy"]
    C --> D["Parse JOSE header nghiêm ngặt"]
    D --> E["Kiểm tra alg, typ, crit và chọn khóa tin cậy"]
    E --> F["Verify JWS hoặc authenticated decrypt JWE"]
    F --> G{"Bằng chứng mật mã hợp lệ?"}
    G -- "Không" --> X["Từ chối"]
    G -- "Có" --> H["Xác minh nested JWT nếu có"]
    H --> I["Kiểm tra token profile và claims"]
    I --> J["Kiểm tra thời gian, issuer, audience và subject"]
    J --> K["Kiểm tra jti, revocation và binding nếu policy yêu cầu"]
    K --> L{"Tất cả kiểm tra bắt buộc đạt?"}
    L -- "Không" --> X
    L -- "Có" --> M["Tạo validated token context"]
    M --> N["Authorization theo hành động và tài nguyên"]
    N --> O{"Được phép?"}
    O -- "Không" --> Y["Từ chối thao tác"]
    O -- "Có" --> P["Thực hiện thao tác"]
~~~

### 3.1. Xác minh đầu vào

Trước khi thực hiện mật mã, kiểm tra nguồn nhận token, số lượng token, định dạng Compact/JSON Serialization mà endpoint hỗ trợ, kích thước tổng và kích thước từng thành phần. Từ chối header trùng hoặc nguồn token mơ hồ theo policy.

Không cắt ngắn, tự sửa, nối hoặc chuẩn hóa token lỗi để cố tiếp tục. Phải giữ nguyên chuỗi gốc cần thiết cho việc xác minh JWS.

### 3.2. Chọn policy và nguồn khóa

Policy phải được chọn từ endpoint, resource, tenant/client context đã xác thực hoặc registry tin cậy. Header chưa xác minh chỉ được dùng để đối chiếu allowlist và tìm khóa trong kho đã gắn với issuer.

Không để claims chưa xác minh tạo issuer mới, chọn audience bất kỳ, mở URL trong jku/x5u hoặc mở rộng thuật toán.

### 3.3. Xác minh mật mã

Với JWS, thư viện phải xác minh chữ ký/MAC trên đúng signing input gốc. Không parse JSON rồi serialize lại để xác minh một chuỗi khác.

Với JWE, chỉ sử dụng plaintext sau khi quá trình authenticated decryption hoàn tất và authentication tag hợp lệ. Nếu profile yêu cầu chữ ký issuer bên trong JWE, phải tiếp tục xác minh JWS lồng.

### 3.4. Kiểm tra claims và trạng thái

Sau khi bằng chứng mật mã thành công, kiểm tra iss, aud, sub, exp, nbf, iat, typ/profile, kiểu dữ liệu, claims bắt buộc và ràng buộc ngữ cảnh. Nếu policy yêu cầu, kiểm tra jti, session, denylist, introspection, DPoP hoặc mTLS binding.

Chỉ khi toàn bộ bước bắt buộc đạt mới tạo context đã xác minh. Không trả context từng phần trong khi một kiểm tra quan trọng vẫn đang chờ.

## 4. Định nghĩa validated token context

Validated token context là một biểu diễn nội bộ của danh tính và claims đã được xác minh. Nó không phải JWT mới, không phải payload thô và không phải bản sao tùy tiện của mọi trường trong token.

Context nên chứa những dữ liệu mà các bước sau thực sự cần:

| Thành phần | Nội dung có thể chứa | Nguồn |
| --- | --- | --- |
| Validation policy | Policy ID và phiên bản policy đã áp dụng | Registry cấu hình tin cậy |
| Issuer | Issuer đã được xác minh và khớp policy | Claim iss sau xác minh |
| Subject | Subject đã xác minh theo issuer/profile | Claim sub sau xác minh |
| Audience | Audience đã được kiểm tra cho resource server | Claim aud sau xác minh |
| Token profile | Loại token đã được xác minh theo profile | Header và claims sau xác minh |
| Thời gian | iat, exp, nbf đã kiểm tra nếu có | Claims sau xác minh |
| Client/tenant/session | Các binding đã được kiểm tra | Claims kết hợp với ngữ cảnh tin cậy |
| Scope/permissions | Giá trị được profile cho phép sử dụng | Claims sau xác minh |
| Trạng thái | Kết quả kiểm tra revocation/replay/binding nếu áp dụng | Kho trạng thái và validator |
| Assurance | ACR/AMR hoặc thông tin xác thực đã kiểm tra nếu profile yêu cầu | Claims OIDC/profile và policy |

Ví dụ biểu diễn logic:

~~~json
{
  "validation": {
    "policyId": "invoices-api-access-token",
    "policyVersion": 7,
    "cryptographicVerification": "passed",
    "claimsValidation": "passed",
    "revocationCheck": "passed"
  },
  "identity": {
    "issuer": "https://identity.example.org/",
    "subject": "user-123"
  },
  "resource": {
    "audience": "https://api.example.org/invoices",
    "tenant": "tenant-blue"
  },
  "authorizationInput": {
    "scopes": ["invoice:read"]
  },
  "time": {
    "issuedAt": 1893456000,
    "expiresAt": 1893456900
  }
}
~~~

Đây là ví dụ minh họa, không phải schema chuẩn. Context thực tế nên là đối tượng nội bộ có cấu trúc rõ, bất biến sau khi tạo và không chứa raw bearer token nếu không có nhu cầu cụ thể.

### 4.1. Context phải gắn với policy đã áp dụng

Chỉ lưu issuer và subject đôi khi chưa đủ để hiểu phạm vi xác minh. Nên giữ policy ID/profile và audience/resource đã được kiểm tra để tránh downstream diễn giải cùng claims theo một mục đích khác.

Nếu policy thay đổi, cần biết context được tạo theo phiên bản nào. Với request dài hoặc thao tác nhạy cảm, có thể cần kiểm tra lại trạng thái hiện hành hoặc ràng buộc policy version.

### 4.2. Không cho phép tạo context tùy tiện

Chỉ một thành phần có trách nhiệm validation mới được tạo context đã xác minh. Không cung cấp constructor hoặc API công khai cho phép business logic tạo context bằng cách truyền vào issuer, subject, role hoặc claims do caller tự khai.

Các trường như cryptographicVerification = passed chỉ được gán sau khi thư viện trả kết quả thành công. Không dùng một boolean mặc định true hoặc một đối tượng có thể được điền dần từ payload thô.

## 5. Chỉ đưa claims đã xác minh vào danh tính

Sau khi validation thành công, hệ thống có thể tạo principal/identity context. Cần diễn giải claims theo đúng issuer và profile.

### 5.1. Định danh subject

Không mặc định sub luôn là username, email hoặc người dùng cuối. Nó có thể đại diện cho người dùng, client, workload hoặc một thực thể khác.

Trong hệ thống nhiều issuer, định danh nội bộ nên gắn issuer với subject hoặc qua một mapping đã xác minh:

~~~text
identity_key = trusted_issuer + verified_subject
~~~

Không gộp hai subject giống chuỗi từ hai issuer thành một danh tính nếu chưa có quy trình liên kết tài khoản đáng tin cậy.

### 5.2. Diễn giải scope và role

Scope, role, permission hoặc group không có cùng semantics trong mọi issuer. Một giá trị admin do issuer A phát hành không nhất thiết tương đương admin của issuer B. Tương tự, scope invoice:read không tự cấp quyền đọc mọi hóa đơn trong mọi tenant.

Chỉ ánh xạ claims quyền khi:

- Issuer được phép phát hành claim đó.
- Token profile định nghĩa rõ semantics.
- Audience phù hợp với resource server.
- Giá trị và kiểu dữ liệu đã được kiểm tra.
- Policy ứng dụng xác định cách chuyển claim thành quyền.

Không đọc role từ JWT chưa xác minh, cũng không tự động biến mọi claim có tên role/permissions thành quyền thực thi.

### 5.3. Claims tùy biến

Với tenant_id, department, account_status hoặc claims riêng khác, cần kiểm tra schema, namespace, issuer authority và quan hệ với ngữ cảnh request.

Ví dụ, tenant trong token phải khớp tenant context đã được xác định độc lập nếu policy yêu cầu. Không để claim tenant chưa xác minh quyết định tenant database hoặc vùng dữ liệu cần truy cập.

## 6. Tách claims validation khỏi authorization

Một context đã xác minh chỉ trả lời token nói gì và token có phù hợp policy xác minh hay không. Nó không tự trả lời mọi yêu cầu truy cập.

| Giai đoạn | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication/token validation | Token có được phát hành bởi issuer tin cậy, dành cho API và còn hợp lệ không? | iss/aud/exp/chữ ký đạt |
| Identity resolution | Token đại diện cho chủ thể nào trong miền issuer? | identity key = iss + sub |
| Authorization | Chủ thể có được phép thực hiện hành động trên tài nguyên này không? | Có invoice:read và quyền với invoice cụ thể |
| Business validation | Thao tác có hợp lệ theo trạng thái nghiệp vụ hiện tại không? | Hóa đơn đã khóa hoặc đã thanh toán không thể sửa |

Ví dụ: token có scope invoice:read vẫn có thể không được phép đọc hóa đơn thuộc tenant khác hoặc hóa đơn mà subject không có quan hệ truy cập. Authorization cần kết hợp context đã xác minh với policy và trạng thái tài nguyên hiện hành.

Không dùng một claim role=admin để bỏ qua kiểm tra quyền trên tài nguyên, tenant hoặc hành động cụ thể.

## 7. Không parse lại JWT ở downstream

Một lỗi kiến trúc thường gặp là gateway đã xác minh token nhưng sau đó chuyển raw JWT tới nhiều dịch vụ, mỗi dịch vụ tự decode payload theo cách riêng rồi tin các claims mà không thực hiện đầy đủ validation.

Điều này tạo ra nhiều cách diễn giải và nhiều ranh giới tin cậy:

- Gateway có thể xác minh issuer/audience, nhưng service phía sau lại bỏ qua audience.
- Một service có thể lấy role từ payload trước verify.
- Các parser có thể xử lý duplicate JSON member khác nhau.
- Một dịch vụ có thể dùng JWKS cache hoặc policy cũ.
- Header do client gửi có thể bị nhầm với metadata nội bộ do gateway tạo.

Có hai mô hình phổ biến:

### 7.1. Mỗi dịch vụ tự xác minh token

Gateway chuyển tiếp bearer token; từng resource server xác minh chữ ký, issuer, audience, profile và claims theo policy riêng của mình.

Mô hình này phù hợp khi mỗi service là một resource server độc lập. Token phải có audience phù hợp với service nhận; không mặc định một access token dành cho gateway cũng dành cho tất cả service phía sau.

### 7.2. Gateway chuyển tiếp identity context nội bộ

Gateway xác minh token rồi tạo một context nội bộ hoặc assertion nội bộ được bảo vệ. Service phía sau chỉ tin context đó khi:

- Kênh gateway-to-service được xác thực và giới hạn nguồn gửi.
- Context có integrity protection hoặc được truyền qua cơ chế tin cậy đã thiết kế.
- Các header do client tự gửi có cùng tên đã bị loại bỏ/ghi đè ở gateway.
- Context xác định issuer, subject, audience/resource, policy và claims cần thiết.
- Service phía sau kiểm tra context phù hợp với endpoint và quyền của nó.

Không gửi một header như X-User-Role hoặc X-Authenticated-User qua mạng rồi tin nó chỉ vì tên header. Cần chứng minh ai tạo, bảo vệ tính toàn vẹn và ngăn client giả mạo.

## 8. Chuyển tiếp claims và nguyên tắc tối thiểu

Không nên chuyển tất cả claims trong JWT tới mọi thành phần. Claims có thể chứa thông tin cá nhân, dữ liệu nhạy cảm hoặc quyền không liên quan tới service nhận.

Khi tạo context hoặc token nội bộ:

- Chỉ giữ claims cần cho mục đích cụ thể.
- Giữ issuer/subject và policy provenance cần thiết để diễn giải.
- Chuyển scope/permission theo audience và service nhận.
- Không chuyển refresh token, raw bearer token hoặc private data nếu không cần.
- Không nâng quyền khi chuyển đổi token hoặc ánh xạ claims.
- Giới hạn thời gian sống của assertion/context nội bộ.
- Bảo vệ kênh truyền và xác thực service gửi/nhận.

Nếu downstream cần một token riêng, dùng token exchange hoặc cơ chế phát hành credential dành cho audience đó thay vì tái sử dụng access token có phạm vi rộng.

## 9. Tránh dùng claims chưa xác minh trong log, cache và xử lý lỗi

Claims chưa xác minh vẫn là dữ liệu do người gửi kiểm soát. Việc ghi chúng vào log, cache hoặc metric trước khi verify có thể gây:

- Log injection qua chuỗi chứa ký tự điều khiển.
- Gán nhầm sự kiện cho subject hoặc tenant giả.
- Cache poisoning nếu khóa cache lấy từ sub/tenant chưa xác minh.
- Tạo bản ghi revocation/replay giả.
- Làm sai lệch thống kê bảo mật hoặc audit.

Trước khi xác minh, log nên dùng request ID, endpoint ID, kích thước token và mã lỗi tổng quát. Không ghi raw token, Authorization header hoặc payload.

Sau khi xác minh, vẫn cần giới hạn dữ liệu log theo nguyên tắc tối thiểu. Claims như email, nhóm, tenant, scope hoặc dữ liệu cá nhân không nên được ghi toàn bộ nếu không cần cho audit.

Cache cũng phải được thiết kế theo policy và issuer. Không dùng sub đơn lẻ làm khóa toàn cục. Không cache một kết quả xác minh thành công vô thời hạn; trạng thái thời gian, revocation, key rotation và policy có thể thay đổi.

## 10. Xử lý lỗi và trạng thái một phần

Validation pipeline phải có kết quả rõ ràng: thành công hoàn toàn hoặc từ chối. Không trả một context có subject đã xác minh nhưng revocation check đang lỗi, hoặc claims hợp lệ nhưng audience chưa được kiểm tra.

| Tình huống | Kết quả |
| --- | --- |
| Chỉ parse được payload | Chưa có identity context |
| Chữ ký sai hoặc tag JWE sai | Từ chối |
| Chữ ký đúng nhưng issuer/audience sai | Từ chối |
| Claims đúng nhưng token hết hạn | Từ chối |
| Token đúng profile nhưng đã bị thu hồi | Từ chối |
| Policy yêu cầu revocation nhưng store không khả dụng | Xử lý theo failure policy; với yêu cầu bắt buộc/nhạy cảm, từ chối |
| Token hợp lệ nhưng authorization không đạt | Từ chối thao tác |
| Tất cả validation đạt nhưng business rule không đạt | Từ chối theo quy tắc nghiệp vụ |

Không dùng fail-open để biến lỗi kiểm tra thành thành công. Nếu một kiểm tra là tùy chọn, policy phải nói rõ từ trước; không được quyết định bỏ qua nó tùy theo lỗi runtime.

## 11. Mã giả tạo context chỉ sau khi validation hoàn tất

Đoạn mã giả mô tả một luồng JWS access token. Các hàm mật mã phải sử dụng thư viện JOSE phù hợp:

~~~text
function authenticateRequest(request):
    endpoint = resolveTrustedEndpoint(request)
    policy = trustedPolicyRegistry.select(endpoint)
    require policy exists

    rawToken = extractExactlyOneAllowedToken(request)
    require rawToken satisfies size and syntax limits

    parsed = strictParseJws(rawToken)
    header = parsed.protectedHeader
    require header.alg in policy.allowedAlgorithms
    require header.typ matches policy.requiredTokenType

    key = trustedKeyResolver.resolve(
        issuer = policy.issuer,
        kid = header.kid,
        algorithm = header.alg
    )
    require key is compatible with policy
    require joseLibrary.verifyJws(rawToken, key, policy.allowedAlgorithms)

    claims = parseVerifiedClaims(rawToken)
    require validateIssuer(claims.iss, policy)
    require validateAudience(claims.aud, policy)
    require validateSubjectAndRequiredClaims(claims, policy)
    require validateTimeClaims(claims, policy, trustedServerClock)
    require validateTokenProfile(claims, header, policy)

    if policy.checkRevocation:
        require revocationStore.isAvailable
        require not revocationStore.isRevoked(claims.iss, policy.profile, claims.jti)

    if policy.requireClientOrTenantBinding:
        require validateBindings(claims, request.trustedContext, policy)

    context = createImmutableValidatedTokenContext(
        policyId = policy.id,
        policyVersion = policy.version,
        issuer = claims.iss,
        subject = claims.sub,
        audience = claims.aud,
        profile = policy.profile,
        permittedClaims = selectClaimsAllowedByPolicy(claims, policy)
    )

    return context

function handleRequest(request):
    tokenContext = authenticateRequest(request)
    require authorizationPolicy.allows(
        tokenContext,
        action = request.action,
        resource = request.resource
    )
    return executeBusinessOperation(request)
~~~

Đối với JWE, thay bước verify JWS bằng authenticated decryption theo allowlist alg/enc; chỉ parse plaintext sau khi tag hợp lệ. Nếu token nested, xác minh từng lớp theo policy. Nếu policy không yêu cầu revocation hoặc binding, các bước đó không cần thực hiện; nhưng nếu đã được đánh dấu bắt buộc thì không được bỏ qua khi gặp lỗi.

## 12. Kiểm thử ranh giới claims đã xác minh

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Decode/parse | Payload có sub=admin nhưng chữ ký sai | Không tạo identity context |
| Signature | Chữ ký đúng, iss sai | Từ chối |
| Audience | Chữ ký đúng, aud dành cho API khác | Từ chối |
| Profile | typ đúng nhưng token profile/claims sai | Từ chối |
| Time | exp đã qua hoặc iat bất hợp lý | Từ chối |
| Revocation | Token đã bị thu hồi | Từ chối |
| Store failure | Revocation store bắt buộc nhưng không truy cập được | Áp dụng failure policy, không tự coi active |
| Binding | cnf/client/tenant mismatch | Từ chối |
| Nested | JWE ngoài hợp lệ nhưng JWS trong sai | Từ chối toàn bộ |
| Context | Một bước validation chưa hoàn tất | Không có context có thể sử dụng |
| Authorization | Context hợp lệ nhưng thiếu quyền trên tài nguyên | Từ chối thao tác |
| Downstream | Client tự gửi header identity giả | Gateway loại bỏ/ghi đè; service chỉ tin context nội bộ được bảo vệ |
| Logging | Token giả chứa chuỗi điều khiển hoặc claim nhạy cảm | Không gây log injection, không ghi raw token |

Nên có kiểm thử kiến trúc chứng minh chỉ validation component mới tạo được validated context. Các thành phần nghiệp vụ không nên có đường đi thay thế bằng cách decode raw JWT.

## 13. Checklist triển khai

1. [ ] Parse/decode được phân biệt rõ với verify/decrypt; không dùng payload thô để tạo danh tính.
2. [ ] Policy được chọn từ endpoint/resource và ngữ cảnh tin cậy.
3. [ ] Thuật toán, nguồn khóa và key type được kiểm tra trước khi thực hiện mật mã.
4. [ ] JWS được xác minh trên signing input gốc; JWE chỉ cung cấp plaintext sau authenticated decryption thành công.
5. [ ] Nested JWT được xác minh đầy đủ từng lớp nếu profile sử dụng.
6. [ ] Token type/profile, issuer, audience, subject, thời gian và claims bắt buộc đều đạt.
7. [ ] jti, revocation, session, replay và binding được kiểm tra khi policy yêu cầu.
8. [ ] Không tạo context một phần khi còn kiểm tra bắt buộc chưa hoàn tất.
9. [ ] Validated token context có policy ID/version, issuer, subject, audience và profile.
10. [ ] Context được tạo bởi validation component, có cấu trúc rõ và không bị sửa tùy tiện.
11. [ ] Claims được ánh xạ theo semantics của issuer/profile; không mặc định role/scope có cùng ý nghĩa giữa các issuer.
12. [ ] Authorization được thực hiện riêng cho hành động và tài nguyên.
13. [ ] Downstream không decode raw token rồi tự tin claims; identity context nội bộ được bảo vệ.
14. [ ] Log/cache không dùng claims chưa xác minh và không lưu raw token/secret.
15. [ ] Mọi lỗi ở bước bắt buộc đều từ chối; không có fail-open ngầm.
16. [ ] Có kiểm thử âm cho từng bước và kiểm thử rằng context không xuất hiện khi validation chưa hoàn tất.

## 14. Tài liệu tiêu chuẩn liên quan

- **RFC 7519 — JSON Web Token (JWT):** JWT Claims Set và registered claims.
- **RFC 7515 — JSON Web Signature (JWS):** signing input và xác minh chữ ký.
- **RFC 7516 — JSON Web Encryption (JWE):** authenticated encryption và giải mã.
- **RFC 8725 — JSON Web Token Best Current Practices:** xác minh JWT, issuer/audience, explicit typing và phòng token confusion.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** quy tắc validation access token và claims theo profile.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra trạng thái token.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** ràng buộc token với proof-of-possession.

**Nguyên tắc ghi nhớ:** Claims chỉ trở thành đầu vào đáng tin cậy sau khi toàn bộ validation policy đã đạt. Hãy tạo một validated token context rõ ràng tại ranh giới xác minh, chuyển đúng những claims cần thiết vào authorization và business logic, đồng thời không để bất kỳ thành phần nào quay lại tin payload thô.
