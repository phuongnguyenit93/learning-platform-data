# Thiết lập thời hạn phù hợp mức rủi ro

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Cấp phát token. Bài viết trình bày nguyên tắc bảo mật JWT dùng chung, không phụ thuộc ngôn ngữ lập trình, thư viện hoặc framework.

## 1. Vì sao thời hạn token phải gắn với mức rủi ro?

JWT thường được dùng như một credential: bên sở hữu token có thể trình token để chứng minh quyền truy cập theo những điều kiện đã được issuer ký xác nhận. Nếu token bị lộ, người khác có thể sử dụng nó cho đến khi token hết hạn hoặc bị hệ thống phát hiện và từ chối bằng cơ chế thu hồi/kiểm tra bổ sung.

**Thời hạn càng dài, khoảng thời gian token bị đánh cắp có thể bị lạm dụng càng lớn.** Thời hạn quá ngắn lại làm tăng số lần làm mới token, tải lên authorization server, độ phức tạp vận hành và khả năng gián đoạn trải nghiệm. Vì vậy, không nên đặt một giá trị TTL duy nhất cho mọi loại token và mọi thao tác.

Khi chọn thời hạn, cần cân bằng ít nhất bốn yếu tố:

1. **Mức độ thiệt hại nếu token bị sử dụng trái phép:** token có thể đọc dữ liệu công khai, xem dữ liệu cá nhân, sửa dữ liệu hay chuyển tiền?
2. **Khả năng token bị lộ và phát hiện:** token đi qua trình duyệt, thiết bị di động, service-to-service hay môi trường máy chủ; có thể bị ghi log, lưu trữ hoặc phát lại không?
3. **Khả năng thu hồi và kiểm tra trạng thái:** resource server có thể kiểm tra phiên, trạng thái grant hoặc danh sách thu hồi theo thời gian thực không?
4. **Mức độ xác thực và bối cảnh phiên:** người dùng đã xác thực bằng phương thức nào, lần xác thực gần nhất khi nào, thiết bị/phiên có đáng tin cậy không và thao tác có yêu cầu xác thực tăng cường không?

Thời hạn phải là một phần của **chính sách phát hành theo loại token, audience, quyền và ngữ cảnh**, không phải một con số tùy ý do client gửi lên.

## 2. Các claim thời gian trong JWT

JWT sử dụng NumericDate cho những claim thời gian chuẩn. NumericDate biểu diễn số giây kể từ Unix epoch (1970-01-01T00:00:00Z); không nhầm giây với mili giây.

| Claim | Ý nghĩa | Cách áp dụng |
| --- | --- | --- |
| `iat` (Issued At) | Thời điểm token được phát hành | Do issuer tạo từ đồng hồ đáng tin cậy; có thể dùng để kiểm tra token quá cũ hoặc phục vụ kiểm toán |
| `exp` (Expiration Time) | Thời điểm token hết hạn | Bên nhận không được chấp nhận token tại hoặc sau thời điểm này, có thể áp dụng clock-skew nhỏ theo chính sách |
| `nbf` (Not Before) | Thời điểm token bắt đầu có hiệu lực | Nếu hiện tại còn trước thời điểm này, token chưa được chấp nhận |

### 2.1. Tính thời gian sống (TTL)

Thời gian sống được xác định bằng:

\[
TTL = exp - iat
\]

Ví dụ: issuer phát hành lúc 10:00:00 UTC, `exp` là 10:15:00 UTC thì TTL là 15 phút.

`iat` không tự động khiến JWT hết hạn và cũng không thay thế `exp`. Nếu chính sách yêu cầu token không được quá cũ, bên nhận cần có quy tắc max-age riêng dựa trên `iat` hoặc claim xác thực phù hợp. Tương tự, `nbf` không phải là thời điểm hết hạn; nó chỉ xác định thời điểm bắt đầu hiệu lực.

### 2.2. Quy tắc tạo và kiểm tra

- Dùng đồng hồ hệ thống được đồng bộ đáng tin cậy; tạo timestamp ở phía issuer.
- Tạo `exp` từ TTL của chính sách đã chọn, không lấy thời gian hết hạn do client đề xuất.
- Kiểm tra kiểu và miền giá trị: NumericDate hợp lệ, `exp` sau `iat`, `nbf` không mâu thuẫn với các claim thời gian khác.
- Bên nhận phải xác minh chữ ký trước khi tin các claim thời gian.
- Chỉ cho phép một khoảng sai lệch đồng hồ (clock skew/leeway) nhỏ, được cấu hình thống nhất giữa issuer và resource server.
- Không kéo dài leeway để che giấu đồng hồ hệ thống không đồng bộ; cần sửa nguồn thời gian.
- Nếu profile token quy định claim thời gian bắt buộc, thiếu claim phải dẫn tới từ chối.

Ví dụ payload minh họa:

~~~json
{
  "iss": "https://auth.example.net",
  "sub": "user-84",
  "aud": "https://api.example.net/orders",
  "iat": 1900000000,
  "nbf": 1900000000,
  "exp": 1900000900,
  "scope": "orders:read"
}
~~~

Payload có `exp - iat = 900` giây, tương đương 15 phút. Các số thời gian chỉ mang tính minh họa; hệ thống phải tính từ đồng hồ thực và chính sách của mình.

## 3. Phân biệt thời hạn token với thời hạn phiên

Hai khái niệm này không giống nhau:

- **Token lifetime:** khoảng thời gian một token cụ thể được resource server chấp nhận.
- **Session lifetime:** khoảng thời gian phiên xác thực/ủy quyền của người dùng hoặc client còn được phép tồn tại theo chính sách.

Một phiên dài có thể sử dụng nhiều access token ngắn hạn. Khi access token hết hạn, client có thể xin token mới bằng refresh token hoặc cơ chế gia hạn khác, nếu phiên/grant còn hợp lệ.

Ví dụ:

- Người dùng đăng nhập lúc 09:00.
- Access token thứ nhất có TTL 10 phút và hết hạn lúc 09:10.
- Refresh token còn hợp lệ; client thực hiện refresh rotation và nhận access token thứ hai.
- Phiên có giới hạn tuyệt đối đến 17:00; việc refresh lúc 16:55 không được tự động kéo giới hạn tuyệt đối sang ngày tiếp theo.

Nên định nghĩa ít nhất hai giới hạn phiên:

1. **Idle timeout:** thời gian tối đa không có hoạt động hợp lệ trước khi phiên phải kết thúc hoặc yêu cầu xác thực lại.
2. **Absolute timeout:** thời gian tối đa kể từ khi phiên được tạo, bất kể có hoạt động hay refresh token hay không.

Có thể có thêm giới hạn theo tuổi của lần xác thực gần nhất (authentication age), mức bảo đảm xác thực (`acr`/`amr` theo giao thức) hoặc yêu cầu xác thực lại trước một thao tác nhạy cảm.

**Không để refresh token biến thành một phiên vô hạn.** Nếu chính sách có sliding expiration, mỗi lần gia hạn có thể cập nhật idle timeout nhưng vẫn phải tôn trọng absolute timeout và các điều kiện thu hồi.

## 4. Đánh giá rủi ro trước khi chọn TTL

Thời hạn phù hợp phụ thuộc vào bối cảnh. Một ma trận đánh giá hữu ích gồm:

| Yếu tố | Rủi ro thấp hơn | Rủi ro cao hơn |
| --- | --- | --- |
| Quyền | Chỉ đọc dữ liệu ít nhạy cảm | Quản trị, sửa/xóa, thanh toán, xuất dữ liệu lớn |
| Audience | Một API giới hạn, phạm vi hẹp | Nhiều API hoặc dịch vụ có quyền rộng |
| Chủ thể | Workload đã xác thực và kiểm soát tốt | Phiên người dùng trên thiết bị có nguy cơ bị chiếm đoạt |
| Client/storage | Máy chủ bảo vệ credential tốt | Trình duyệt/thiết bị có nguy cơ XSS, malware hoặc lưu trữ không an toàn |
| Khả năng thu hồi | Có kiểm tra trạng thái/thu hồi hiệu quả | JWT được xác minh offline, không có kênh thu hồi tức thời |
| Dữ liệu | Thông tin ít nhạy cảm | Dữ liệu cá nhân, tài chính, bí mật hoặc dữ liệu được quản lý nghiêm ngặt |
| Bằng chứng xác thực | Xác thực mới, mạnh và phù hợp thao tác | Phiên cũ, xác thực yếu hoặc không đáp ứng yêu cầu hiện tại |

Không nên dùng một tín hiệu đơn lẻ như địa chỉ IP để quyết định TTL. Địa chỉ IP có thể thay đổi hợp lệ, dùng chung hoặc bị giả mạo ở một số tầng mạng. Hệ thống đánh giá rủi ro nên kết hợp nhiều tín hiệu đã được kiểm chứng, có quy tắc giải thích được và tránh tạo ra phân biệt đối xử không phù hợp.

### 4.1. Bảng chính sách minh họa

Bảng dưới đây là ví dụ về **định hướng tương đối**, không phải thời hạn bắt buộc do JWT hoặc OAuth quy định:

| Ngữ cảnh | Định hướng thời hạn access token | Kiểm soát bổ sung |
| --- | --- | --- |
| API đọc thông tin ít nhạy cảm | Có thể dài hơn nhóm quyền cao, nhưng vẫn giới hạn rõ | Audience hẹp, scope chỉ đọc, theo dõi bất thường |
| API nghiệp vụ thông thường | Ngắn đến trung bình theo mức độ nhạy cảm | Refresh có kiểm soát, kiểm tra quyền trên tài nguyên |
| API quản trị hoặc thay đổi cấu hình quan trọng | Ngắn | Step-up authentication, scope hẹp, audit và kiểm tra trạng thái |
| Thanh toán/chuyển tiền hoặc thao tác tác động lớn | Rất ngắn hoặc cấp token giao dịch chuyên biệt | Xác nhận giao dịch, ràng buộc ngữ cảnh, chống phát lại |
| Service-to-service | Theo quyền workload, mức độ bảo vệ credential và khả năng thu hồi | Audience cụ thể, workload identity, credential rotation |
| Token dùng một lần (reset/verify) | Rất ngắn và chỉ dùng một lần | Purpose binding, nonce/jti, lưu trạng thái đã sử dụng |

Trong thực tế, một tổ chức có thể thử nghiệm các mốc như 5–10 phút cho thao tác đặc quyền, 10–15 phút cho access token người dùng thông thường hoặc 15–30 phút cho một số API nội bộ ít nhạy cảm. Các con số này chỉ là **điểm khởi đầu để đánh giá**, không phải mặc định an toàn cho mọi hệ thống. Cần điều chỉnh theo threat model, khả năng refresh/thu hồi, môi trường client, yêu cầu vận hành và quy định áp dụng.

## 5. Chọn thời hạn theo loại token

Không nên áp dụng cùng một TTL cho tất cả JWT hoặc token trong hệ thống.

### 5.1. Access token

Access token cho phép client truy cập resource server. Với bearer access token, người sở hữu token có thể sử dụng token trong thời hạn hiệu lực; vì vậy, token ngắn hạn giúp giảm cửa sổ lạm dụng nếu bị lộ.

- Chọn TTL theo độ nhạy cảm của audience và scope.
- Giữ audience hẹp; không bù cho audience quá rộng bằng cách chỉ giảm TTL.
- Token có quyền quản trị hoặc giao dịch quan trọng nên ngắn hơn token chỉ đọc, đồng thời có step-up hoặc kiểm tra bổ sung.
- Không phát hành access token mới nếu refresh grant, phiên hoặc quyền đã bị thu hồi.
- Không để client tự chọn `exp` hoặc yêu cầu TTL vượt giới hạn chính sách.

### 5.2. Refresh token

Refresh token cho phép xin access token mới mà không phải thực hiện lại toàn bộ đăng nhập. Nó thường có thời hạn dài hơn access token và có giá trị cao vì có thể duy trì quyền truy cập trong thời gian dài.

Cần thiết lập:

- **Idle lifetime:** refresh token/phiên không được sử dụng trong khoảng thời gian quy định sẽ hết hiệu lực.
- **Absolute lifetime:** giới hạn tối đa kể từ lúc grant/phiên được tạo.
- **Rotation:** sau khi sử dụng, cấp refresh token mới và vô hiệu hóa token cũ theo mô hình được chọn.
- **Reuse detection:** phát hiện refresh token cũ đã bị dùng lại; tùy chính sách, có thể thu hồi cả token family/grant liên quan.
- **Client binding / sender constraint:** ràng buộc refresh token với client hoặc bằng chứng sở hữu khi giao thức và môi trường hỗ trợ.
- **Reauthentication:** yêu cầu người dùng xác thực lại khi vượt authentication age hoặc trước thao tác có rủi ro cao.

Refresh token không bắt buộc phải là JWT; giá trị opaque thường giúp máy chủ quản lý trạng thái, thu hồi và rotation trực tiếp hơn. Nếu dùng JWT làm refresh token, vẫn phải kiểm tra trạng thái grant, thu hồi và reuse theo chính sách; chỉ dựa vào `exp` là chưa đủ.

### 5.3. ID token

ID token trong OpenID Connect mang thông tin xác thực về người dùng cho client. Nó có audience và quy tắc xác minh riêng; không được sử dụng như access token cho resource server.

Thời hạn cần đủ để client hoàn tất giao dịch xác thực và xử lý kết quả theo giao thức. Client phải xác minh issuer, audience, chữ ký, thời gian và các ràng buộc như nonce khi áp dụng. Không dùng ID token dài hạn như cơ chế thay thế session management.

### 5.4. Token dùng một lần và token theo mục đích

Token reset mật khẩu, xác minh email, kích hoạt thiết bị hoặc xác nhận một thao tác nhạy cảm cần:

- TTL ngắn phù hợp với cơ hội sử dụng và độ nhạy cảm;
- ràng buộc đúng chủ thể, mục đích, giao dịch hoặc client;
- định danh duy nhất hoặc nonce để chống phát lại;
- trạng thái đã sử dụng/đã thu hồi được kiểm tra tại máy chủ;
- không được chấp nhận ở API hoặc luồng token khác.

Một token đã hết hạn hoặc đã sử dụng phải bị từ chối ngay cả khi chữ ký vẫn hợp lệ.

## 6. Thời hạn thích ứng theo rủi ro

Một chính sách nâng cao có thể điều chỉnh TTL dựa trên ngữ cảnh phát hành. Ví dụ:

- Phiên mới xác thực mạnh, audience hẹp, chỉ đọc: có thể áp dụng TTL chuẩn của API.
- Phiên đã tồn tại lâu hoặc mức xác thực không đáp ứng thao tác: yêu cầu step-up/reauthentication; không chỉ kéo dài hoặc rút ngắn TTL để thay thế việc xác thực.
- Thao tác quản trị hoặc giao dịch quan trọng: cấp quyền rất hẹp, thời hạn ngắn, ràng buộc giao dịch và xác nhận bổ sung.
- Thiết bị hoặc phiên có tín hiệu rủi ro cao: từ chối cấp token, thu hồi phiên hoặc yêu cầu xác thực lại tùy chính sách.
- Workload có credential sắp hết hạn hoặc có dấu hiệu bị lộ: giảm quyền, xoay credential và thu hồi grant/token liên quan.

Có thể mô hình hóa chính sách:

~~~text
function determineTokenPolicy(context):
    require context.clientIsAllowed
    require context.authenticationOrGrantIsValid

    risk = riskEngine.evaluate(
        subject = context.subject,
        client = context.client,
        audience = context.audience,
        requestedScopes = context.requestedScopes,
        authenticationAge = context.authenticationAge,
        deviceAndSessionSignals = context.verifiedSignals
    )

    if risk.isCritical:
        return DENY

    if risk.requiresStepUp:
        return REQUIRE_ADDITIONAL_AUTHENTICATION

    policy = tokenPolicy.for(
        tokenType = context.tokenType,
        audience = context.audience,
        scopeClass = risk.scopeClass
    )

    ttl = min(
        policy.configuredTtl,
        risk.maximumAllowedTtl
    )

    require ttl > 0
    require ttl <= policy.absoluteMaximumTtl

    return policy.withLifetime(ttl)
~~~

Điểm quan trọng: rủi ro cao không phải lúc nào cũng có nghĩa là “cấp token ngắn hơn”. Nếu bằng chứng xác thực không đáng tin hoặc có dấu hiệu chiếm đoạt, hành động đúng có thể là **từ chối cấp token hoặc yêu cầu xác thực lại**.

## 7. Refresh, thu hồi và giới hạn của JWT tự chứa

JWT có thể được xác minh offline bằng chữ ký, nên resource server không nhất thiết phải hỏi issuer mỗi lần. Điều này giúp giảm phụ thuộc mạng nhưng cũng khiến việc thu hồi tức thời khó hơn: token đã ký có thể tiếp tục được chấp nhận đến `exp` nếu bên nhận không kiểm tra trạng thái bên ngoài.

Các chiến lược thường được kết hợp:

| Chiến lược | Tác dụng | Giới hạn |
| --- | --- | --- |
| Access token ngắn hạn | Giới hạn cửa sổ sử dụng sau khi lộ | Không thu hồi tức thời |
| Token introspection / kiểm tra trạng thái | Resource server biết token/grant còn hoạt động không | Thêm độ trễ và phụ thuộc dịch vụ |
| Denylist theo `jti` | Từ chối token cụ thể đã bị thu hồi | Cần lưu trữ và đồng bộ trạng thái tới khi token hết hạn |
| Session/grant version | Vô hiệu hóa token theo phiên hoặc grant | Resource server phải kiểm tra version/trạng thái |
| Thu hồi refresh token family | Ngăn cấp access token mới từ grant bị lộ | Access token đã phát hành vẫn có thể còn hiệu lực |
| Xoay khóa ký khẩn cấp | Vô hiệu hóa token ký bằng khóa bị xâm phạm nếu loại bỏ khóa khỏi trust set | Ảnh hưởng diện rộng, có thể làm gián đoạn token hợp lệ |

Không nên dùng thay khóa ký như phương pháp thu hồi thường ngày; đây là biện pháp xử lý sự cố khóa bị xâm phạm hoặc tình huống đặc biệt. Với nhu cầu thu hồi một token, grant hoặc phiên, cơ chế trạng thái/denylist phù hợp hơn.

### 7.1. Tính nhất quán khi refresh

Khi nhiều yêu cầu refresh đồng thời dùng cùng một refresh token đã được rotation, hệ thống cần xử lý race condition. Nếu hai request cùng thành công, có thể tạo ra hai nhánh token family hoặc khiến phát hiện reuse nhầm một yêu cầu hợp lệ.

Cần thiết kế thao tác rotation có tính nguyên tử hoặc cơ chế đồng bộ tương đương:

1. Xác minh token hiện tại và trạng thái grant.
2. Đánh dấu token cũ đã dùng và tạo token mới trong một thao tác nhất quán.
3. Nếu token cũ được dùng lại sau khi rotation đã hoàn tất, xử lý theo chính sách reuse detection.
4. Có cơ chế idempotency/điều phối phù hợp để retry mạng không vô tình tạo nhiều nhánh refresh.
5. Ghi nhận sự kiện mà không log refresh token nguyên vẹn.

## 8. Ví dụ: chính sách thời hạn cho một nền tảng đa API

Một hệ thống có ba resource server:

- **Profile API:** cho phép đọc thông tin hồ sơ.
- **Orders API:** cho phép đọc và cập nhật đơn hàng.
- **Admin API:** cho phép thay đổi cấu hình và phân quyền.

Chính sách minh họa:

| Token / ngữ cảnh | TTL minh họa | Điều kiện khác |
| --- | --- | --- |
| Access token Profile API | 15 phút | Scope đọc, audience riêng |
| Access token Orders API | 10 phút | Scope theo đơn hàng và tenant |
| Access token Admin API | 5 phút | Step-up, scope hẹp, audit bắt buộc |
| Refresh token phiên người dùng | Theo idle và absolute timeout, ví dụ 8 giờ idle / 7 ngày absolute | Rotation, reuse detection, reauthentication theo rủi ro |
| Token xác nhận giao dịch | Ví dụ 2 phút và chỉ dùng một lần | Ràng buộc mã giao dịch, nonce, kiểm tra trạng thái đã dùng |

Các mốc trên chỉ là ví dụ để minh họa cách tách chính sách. Tổ chức cần chọn thời hạn dựa trên đánh giá rủi ro, khả năng bảo vệ token ở client, khả năng thu hồi và yêu cầu tuân thủ. Một hệ thống không nên sao chép bảng này mà chưa đánh giá kiến trúc và threat model của mình.

Luồng hoạt động:

1. Người dùng xác thực và nhận access token cho Profile API.
2. Khi cần cập nhật đơn hàng, client xin token cho Orders API; authorization server tính lại scope và TTL theo audience, grant và chính sách.
3. Khi người dùng mở Admin API, hệ thống yêu cầu step-up authentication nếu lần xác thực trước không đủ mới/mạnh.
4. Khi access token hết hạn, client chỉ được refresh nếu refresh token còn hiệu lực, chưa bị thu hồi và phiên vẫn đáp ứng idle/absolute timeout.
5. Nếu refresh token bị phát hiện tái sử dụng, hệ thống thu hồi token family/grant theo chính sách và yêu cầu xác thực lại.

## 9. Mã giả phát hành token với thời hạn do máy chủ kiểm soát

~~~text
function issueJwt(request, verifiedContext):
    profile = tokenProfiles.require(request.tokenType)
    require clientPolicy.permits(verifiedContext.client, profile)

    grant = grantStore.verifyActive(verifiedContext.grant)
    require grant.isActive

    subject = identityStore.resolveVerifiedSubject(verifiedContext)
    audience = resourcePolicy.resolveAllowedAudience(
        verifiedContext.client,
        request.resource,
        grant
    )
    scopes = policyEngine.authorize(
        subject,
        verifiedContext.client,
        audience,
        grant,
        request.requestedScopes
    )

    context = buildRiskContext(
        subject,
        verifiedContext.client,
        audience,
        scopes,
        verifiedContext.authenticationTime,
        verifiedContext.assurance
    )

    decision = determineTokenPolicy(context)
    require decision == ALLOW

    now = trustedClock.epochSeconds()
    ttl = min(
        decision.ttl,
        profile.maximumTtl,
        grant.remainingAbsoluteLifetime
    )
    require ttl > 0

    claims = {
        "iss": issuerConfig.identifier,
        "sub": subject.stableId,
        "aud": audience.identifier,
        "iat": now,
        "exp": now + ttl,
        "jti": secureIdGenerator.next(),
        "scope": scopes.allowed
    }

    profile.validateClaims(claims)
    return jwtSigner.sign(claims, issuerConfig.activeKey)
~~~

Issuer phải đảm bảo `grant.remainingAbsoluteLifetime` được tính từ trạng thái grant đáng tin cậy. Với loại token không dùng grant/phiên người dùng, áp dụng giới hạn vòng đời tương ứng của client hoặc workload.

## 10. Xác minh thời hạn tại resource server

Ví dụ logic xác minh thời gian:

~~~text
function validateTokenTime(claims, trustedClock, policy):
    now = trustedClock.epochSeconds()
    leeway = policy.maximumClockSkewSeconds

    require claims.exp exists
    require claims.exp is a valid NumericDate

    if claims.iat exists:
        require claims.iat <= now + leeway
        require claims.exp > claims.iat
        require now - claims.iat <= policy.maximumTokenAgeSeconds + leeway

    if claims.nbf exists:
        require claims.nbf is a valid NumericDate
        require now + leeway >= claims.nbf

    require now < claims.exp + leeway
    return ACCEPT
~~~

Dòng kiểm tra max-age chỉ áp dụng khi chính sách đặt giới hạn tuổi token và `iat` có mặt/được yêu cầu. Cách tính leeway cần nhất quán với thư viện và profile; không được cộng leeway nhiều lần hoặc cho phép token sống thêm một khoảng lớn ngoài chính sách. Điều kiện cốt lõi của RFC 7519 là token không được chấp nhận tại hoặc sau `exp`, với ngoại lệ nhỏ cho sai lệch đồng hồ mà bên nhận có thể cho phép.

## 11. Kiểm thử các ranh giới thời gian và tình huống rủi ro

Các trường hợp tối thiểu:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Hiện tại trước `nbf` vượt quá leeway | Từ chối vì token chưa có hiệu lực |
| Hiện tại đúng hoặc sau `exp` theo quy tắc leeway | Từ chối token hết hạn |
| `exp` trước hoặc bằng `iat` | Từ chối token sai cấu trúc/chính sách |
| `iat` ở tương lai vượt quá clock skew | Từ chối |
| TTL yêu cầu vượt max TTL của profile | Giới hạn theo chính sách hoặc từ chối |
| Token có scope đặc quyền nhưng dùng TTL của scope đọc | Từ chối hoặc áp dụng policy TTL ngắn hơn |
| Refresh token đã hết idle timeout | Từ chối refresh |
| Refresh token còn idle nhưng vượt absolute timeout | Từ chối refresh |
| Refresh token đã rotation bị dùng lại | Phát hiện reuse và xử lý token family/grant |
| Phiên bị thu hồi nhưng access JWT chưa hết hạn | Từ chối nếu resource server có kiểm tra trạng thái/thu hồi theo thiết kế |
| Đồng hồ issuer/resource server lệch lớn | Cảnh báo và khắc phục đồng bộ thời gian; không nới leeway tùy tiện |
| Token reset password được gửi tới API nghiệp vụ | Từ chối do sai token type/audience/purpose |

Ngoài kiểm thử đơn vị, cần kiểm tra tích hợp giữa issuer và các resource server để bảo đảm cùng hiểu NumericDate, clock skew, TTL tối đa và quy tắc token type. Dùng thời gian giả lập trong kiểm thử để kiểm tra chính xác thời điểm sát ranh giới `nbf` và `exp`.

## 12. Những sai lầm cần tránh

- Dùng một TTL dài cố định cho mọi loại JWT, bất kể quyền và audience.
- Cho client tự gửi `exp`, TTL hoặc thời gian sống tối đa.
- Dùng thời hạn access token để thay thế idle timeout và absolute timeout của phiên.
- Cho refresh token có thể gia hạn vô hạn bằng sliding expiration.
- Chỉ dựa vào `exp` mà không có phương án thu hồi khi token/grant bị xâm phạm.
- Cấu hình clock skew quá lớn để che lỗi đồng bộ thời gian.
- Cấp token ngắn hơn cho một phiên có dấu hiệu bị chiếm đoạt nhưng vẫn bỏ qua yêu cầu xác thực lại hoặc từ chối.
- Dùng cùng một token cho access, ID, reset password và giao dịch nhạy cảm.
- Rotation refresh token nhưng không xử lý reuse, retry và yêu cầu đồng thời.
- Giả định thu hồi refresh token sẽ tự động vô hiệu hóa access token đã được phát hành trước đó.

## 13. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa `iat`, `nbf`, `exp` và NumericDate.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): các thực hành xác minh JWT, tách loại token và giảm rủi ro sử dụng sai mục đích.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và các claim bắt buộc theo profile.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ refresh token, rotation, phát hiện reuse và các biện pháp bảo mật OAuth.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): quy tắc xác minh ID token, thời gian và ngữ cảnh xác thực.

**Ghi nhớ:** Thời hạn token phải phản ánh mức rủi ro của quyền, audience, chủ thể, client và khả năng thu hồi. Access token nên có vòng đời giới hạn phù hợp; refresh token phải chịu idle/absolute timeout, rotation và kiểm soát reuse; phiên đăng nhập có giới hạn riêng. `exp` là một hàng rào quan trọng, nhưng không thay thế phân quyền, xác thực lại và cơ chế thu hồi.

