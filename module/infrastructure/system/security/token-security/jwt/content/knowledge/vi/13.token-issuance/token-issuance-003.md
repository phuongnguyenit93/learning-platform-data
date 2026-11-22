# Chọn issuer, audience và subject đúng ngữ cảnh

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Cấp phát token. Bài viết áp dụng cho hệ thống bảo mật JWT nói chung, không phụ thuộc ngôn ngữ lập trình, thư viện hay framework.

## 1. Ba claim xác định ai phát hành, ai nhận và token nói về ai

Một JWT có thể mang nhiều loại thông tin, nhưng ba claim `iss`, `aud` và `sub` trả lời ba câu hỏi nền tảng:

- **Issuer (`iss`):** Ai phát hành token và chịu trách nhiệm cho những khẳng định trong token?
- **Audience (`aud`):** Bên nhận hoặc dịch vụ nào được phép xử lý token?
- **Subject (`sub`):** Token đang nói về chủ thể nào?

Ba vai trò này liên quan với nhau nhưng không thể thay thế cho nhau. Client khởi tạo yêu cầu, issuer ký token, resource server nhận access token, còn subject có thể là người dùng hoặc chính một dịch vụ. Trong một luồng delegated, client và subject thường là hai thực thể khác nhau.

Ví dụ: ứng dụng bảng điều khiển (`dashboard`) yêu cầu issuer phát hành access token cho API đơn hàng (`orders-api`) thay mặt người dùng `user-84`.

| Thành phần | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| Client | `dashboard` | Ứng dụng gửi yêu cầu token |
| Issuer | `https://auth.example.net` | Hệ thống xác thực/ủy quyền phát hành token |
| Audience | `https://api.example.net/orders` | API đơn hàng được phép nhận token |
| Subject | `user-84` | Người dùng mà token đại diện |

Nếu nhầm `dashboard` thành audience, API có thể không nhận diện đúng token dành cho nó. Nếu gán `sub` thành tên client trong khi token đại diện cho người dùng, hệ thống sẽ nhầm danh tính người thực hiện với ứng dụng thay mặt họ.

**Ghi chú về chuẩn:** RFC 7519 định nghĩa `iss`, `sub` và `aud` là registered claims nhưng không bắt buộc mọi JWT đều phải có cả ba. Profile hoặc giao thức cụ thể có thể quy định chúng là bắt buộc. Khi phát hành và xác minh, phải tuân theo profile của loại token đang dùng thay vì áp đặt một quy tắc giống nhau cho mọi JWT.

## 2. Chọn issuer (`iss`): xác định đúng bên phát hành

`iss` xác định principal đã phát hành JWT. Giá trị này thường là một URI định danh issuer, nhưng định dạng cụ thể phụ thuộc profile và thỏa thuận giữa issuer với bên nhận. Theo JWT, giá trị `iss` có kiểu StringOrURI và phép so sánh có phân biệt chữ hoa/chữ thường.

### 2.1. Chọn issuer từ cấu hình tin cậy

Issuer phải được xác định từ miền bảo mật và cấu hình phát hành mà hệ thống kiểm soát:

- Mỗi authorization server, identity provider hoặc security realm được tin cậy cần có định danh issuer rõ ràng.
- Mỗi môi trường (development, staging, production) cần dùng cấu hình issuer phù hợp; không dùng token của môi trường thử nghiệm tại môi trường thật.
- Nếu hệ thống có nhiều tenant hoặc nhiều IdP, duy trì danh sách issuer đã đăng ký và quy tắc ánh xạ tenant/realm tương ứng.
- Giá trị issuer được đưa vào token phải do cấu hình phía máy chủ quyết định, không nhận trực tiếp từ query parameter, request body, header tùy ý hoặc dữ liệu do client tự khai.

Ví dụ cấu hình:

| Security realm | Issuer được cấu hình |
| --- | --- |
| Khách hàng nội bộ | `https://identity.example.net/internal` |
| Đối tác đã liên kết | `https://identity.example.net/partners` |
| Môi trường kiểm thử | `https://identity-test.example.net` |

Bảng chỉ là ví dụ. Một triển khai có thể dùng một issuer chung cho nhiều tenant, hoặc dùng issuer riêng cho từng miền bảo mật. Quyết định này phải phản ánh ranh giới tin cậy, vòng đời khóa và chính sách xác thực thực tế.

### 2.2. Không để request tự chọn issuer tùy ý

Giả sử request chứa:

~~~json
{
  "issuer": "https://unknown.example.org",
  "subject": "admin"
}
~~~

Issuer không được lấy nguyên từ request để ký token. Nếu cho client chọn issuer, hệ thống có thể phát hành token dưới danh nghĩa một miền bảo mật không được phép, hoặc tạo đường dẫn khiến bên nhận tải khóa từ máy chủ không đáng tin.

Trong hệ thống đa issuer, thông tin định tuyến có thể giúp chọn một issuer **trong danh sách đã cấu hình**, nhưng vẫn phải kiểm tra quyền của client/tenant và xác minh token theo cấu hình của issuer đó. Không dùng giá trị chưa xác minh làm URL tùy ý để truy cập metadata hoặc JWKS.

### 2.3. Issuer gắn với khóa và chính sách xác minh

Issuer chịu trách nhiệm quản lý khóa ký, thuật toán được phép, metadata và vòng đời token. Bên nhận cần liên kết issuer với nguồn khóa tin cậy:

1. Cấu hình issuer và endpoint metadata/JWKS thông qua kênh quản trị đáng tin cậy.
2. Chỉ cho phép thuật toán chữ ký phù hợp; không để header JWT tùy ý quyết định thuật toán.
3. Khi luân chuyển khóa, hỗ trợ nhận diện khóa đang dùng và khóa cũ trong khoảng chuyển tiếp theo chính sách.
4. Kiểm tra `iss` trong payload đã xác minh chữ ký phải khớp chính xác issuer mong đợi.

Header `kid` chỉ là định danh gợi ý để chọn khóa trong tập khóa đã tin cậy. Nó không phải bằng chứng rằng khóa thuộc issuer nào. Không biến `kid`, `jku` hoặc `x5u` do token không đáng tin cung cấp thành đường dẫn, URL hoặc lệnh tải tài nguyên tùy ý.

## 3. Chọn audience (`aud`): chỉ định đúng bên nhận token

`aud` xác định những recipient mà JWT hướng tới. Với access token, audience thường là resource server hoặc API sẽ kiểm tra token. Đây là thông tin quan trọng để ngăn token được cấp cho một dịch vụ lại bị sử dụng ở dịch vụ khác.

### 3.1. Phân biệt client và resource server

OAuth có các vai trò khác nhau:

- **Client:** ứng dụng yêu cầu hoặc sử dụng token để truy cập tài nguyên.
- **Authorization server / issuer:** xác thực hoặc ủy quyền và phát hành token.
- **Resource server:** API hoặc dịch vụ nhận access token và bảo vệ tài nguyên.

Vì vậy, `aud` của access token thường xác định API đích; `client_id` nhận diện ứng dụng client. Hai giá trị có thể khác nhau và không được hoán đổi tùy tiện.

Ví dụ:

~~~json
{
  "client_id": "dashboard",
  "aud": "https://api.example.net/orders"
}
~~~

Ở đây `dashboard` là client; `orders-api` là audience. API không nên chấp nhận token chỉ vì `client_id` khớp tên ứng dụng của nó.

Trong OpenID Connect, ID token có audience là client nhận kết quả xác thực (thường là client ID). Điều này khác với access token hướng tới resource server. **Không dùng ID token thay access token** chỉ vì cả hai đều có cấu trúc JWT.

### 3.2. Chọn audience theo tài nguyên đích

Audience phải xác định rõ dịch vụ nhận token. Có thể dùng URI, tên định danh hoặc một chuỗi theo profile đã thống nhất. Điều cần thiết là giá trị duy nhất, ổn định và được issuer cùng resource server hiểu giống nhau.

| Yêu cầu | Audience nên được quyết định như thế nào |
| --- | --- |
| Đọc đơn hàng | Chọn định danh của Orders API |
| Gọi dịch vụ thanh toán | Chọn định danh của Payments API |
| Gọi nhiều API trong một hệ thống | Chỉ dùng nhiều audience nếu profile và kiến trúc cho phép, mỗi API phải hiểu rõ quyền của mình |
| Yêu cầu gửi audience tùy ý | So khớp với danh sách resource/client được phép; từ chối giá trị không được cấp |
| Token dùng cho một ứng dụng đăng nhập | Tuân theo profile ID token, trong đó audience xác định client nhận ID token |

Không chọn audience dựa trên URL tùy ý trong request, host header chưa được tin cậy hoặc địa chỉ do người dùng nhập. Nên ánh xạ một mã tài nguyên đã đăng ký tới audience cấu hình phía máy chủ.

### 3.3. Một audience hay nhiều audience?

Theo JWT, `aud` có thể là một StringOrURI hoặc một mảng các giá trị StringOrURI. Nếu token dành cho nhiều recipient, mỗi recipient được liệt kê phải có thể nhận diện chính mình trong audience.

Tuy nhiên, một access token có quá nhiều audience có thể mở rộng nơi token được chấp nhận. Thực hành tốt thường là cấp token cho **một resource server hoặc một nhóm recipient được thiết kế rõ ràng**, với scope chỉ đủ cho mục tiêu đó.

Bên nhận phải xác minh audience của chính mình bằng quy tắc rõ ràng:

- Token không có `aud` trong khi profile yêu cầu → từ chối.
- Audience không chứa định danh resource server mong đợi → từ chối.
- Không so khớp bằng tiền tố, chuỗi con hoặc wildcard như `https://api.example.net` khớp mọi API cùng domain.
- Nếu profile quy định nhiều audience hoặc authorized party, kiểm tra thêm các ràng buộc tương ứng; không bỏ qua chỉ vì có một audience trùng.

## 4. Chọn subject (`sub`): xác định đúng chủ thể được đại diện

`sub` xác định chủ thể mà JWT nói tới. Trong token người dùng, subject thường là định danh người dùng. Trong token machine-to-machine, subject có thể là ứng dụng, service account hoặc workload. Subject không nhất thiết là người đã nhấn nút hoặc client đã gửi request.

### 4.1. Dùng định danh ổn định trong phạm vi issuer

`sub` cần đại diện cho một principal đã được xác minh và có ngữ nghĩa ổn định theo profile. Không nên mặc định dùng email, tên hiển thị, số điện thoại hoặc username có thể thay đổi làm subject.

Với danh tính liên kết, cách định danh an toàn thường là cặp:

`(iss, sub)`

Bởi vì hai issuer khác nhau có thể phát hành cùng một chuỗi `sub` cho hai chủ thể khác nhau. Ngay cả khi một hệ thống hiện tại tình cờ có subject duy nhất toàn cục, bên nhận vẫn nên hiểu subject trong namespace của issuer đã xác minh.

Ví dụ:

| Issuer | Subject | Danh tính được phân biệt |
| --- | --- | --- |
| `https://idp-a.example` | `482` | Chủ thể 482 trong miền IdP A |
| `https://idp-b.example` | `482` | Chủ thể 482 trong miền IdP B |

Hai cặp trên không mặc định là cùng một người. Muốn liên kết chúng phải có quy trình account linking được xác minh và kiểm soát.

### 4.2. Subject trong các mô hình token khác nhau

| Mô hình | Subject có thể đại diện cho | Điều cần xác minh |
| --- | --- | --- |
| Người dùng đăng nhập | Người dùng đã xác thực | Danh tính đã được ánh xạ vào namespace của issuer; tài khoản còn hoạt động |
| Client credentials | Client application hoặc service identity | Client đã được xác thực; profile access token xác định subject là client khi client hành động thay mặt chính nó |
| Workload / thiết bị | Workload hoặc thiết bị | Chứng thư, workload identity hoặc bằng chứng thiết bị hợp lệ; không giả mạo người dùng |
| Delegated access | Người dùng/tài nguyên chủ thể mà client hành động thay mặt | Quyền ủy quyền hợp lệ; client/actor được biểu diễn theo profile phù hợp |
| Token exchange | Subject theo token được đổi hoặc ngữ cảnh ủy quyền mới | Kiểm tra quan hệ delegation, actor và giới hạn quyền của token mới |

Đối với JWT access token theo RFC 9068, `sub` là claim bắt buộc. Khi client dùng client credentials để hành động thay mặt chính nó, subject xác định client application; khi client hành động thay mặt resource owner, subject xác định resource owner. `client_id` nhận diện client trong cả hai trường hợp.

### 4.3. Phân biệt subject với actor/client

Trong luồng delegated, có thể có ba thực thể:

- **Subject:** chủ thể hoặc tài nguyên mà quyền đang được áp dụng.
- **Client:** ứng dụng nhận grant hoặc yêu cầu token.
- **Actor:** thực thể thực sự hành động thay mặt subject trong chuỗi delegation.

Ví dụ, người dùng `user-84` cấp quyền cho ứng dụng `dashboard` truy cập Orders API. `sub` có thể là `user-84`, `client_id` là `dashboard`; nếu có chuỗi actor/delegation, claim chuyên biệt như `act` có thể được dùng theo profile phù hợp.

Không gán `sub` thành client chỉ vì client gửi request. Cũng không gán subject thành người dùng cuối nếu bằng chứng chỉ xác thực được workload. Mỗi claim phải phản ánh đúng mô hình ủy quyền.

## 5. Chọn issuer, audience và subject theo một ngữ cảnh thống nhất

Ba claim phải nhất quán với nhau và với loại token. Một quyết định phát hành có thể được mô tả bằng bộ câu hỏi:

| Câu hỏi | Claim / cấu hình liên quan | Nguồn quyết định |
| --- | --- | --- |
| Ai có thẩm quyền phát hành token này? | `iss` | Cấu hình issuer / security realm |
| Dịch vụ nào được phép nhận token? | `aud` | Resource registry, client grant và chính sách |
| Token đại diện cho principal nào? | `sub` | Ngữ cảnh xác thực và identity mapping |
| Client nào đã yêu cầu token? | `client_id` hoặc claim theo profile | Client authentication / grant |
| Token thuộc loại nào? | `typ` và profile validation | Chính sách token và giao thức |
| Token có quyền gì? | `scope` hoặc claim quyền riêng | Policy engine / authorization decision |

Một token hợp lệ về chữ ký vẫn có thể sai ngữ cảnh nếu:

- Issuer hợp lệ nhưng không được resource server tin cậy.
- Audience trỏ đến API khác.
- Subject thuộc issuer khác hoặc không phải principal đã xác thực.
- Token loại ID token được đưa vào API đang yêu cầu access token.
- Subject và tenant không khớp, hoặc client không có grant cho audience đó.

## 6. Quy trình quyết định khi phát hành

~~~mermaid
flowchart TD
    A["Nhận yêu cầu token"] --> B["Xác định loại token và security realm"]
    B --> C["Chọn issuer từ cấu hình tin cậy"]
    C --> D["Xác thực client / grant / bằng chứng chủ thể"]
    D --> E{"Có principal hợp lệ?"}
    E -- "Không" --> X["Từ chối phát hành"]
    E -- "Có" --> F["Ánh xạ subject đúng namespace issuer"]
    F --> G["Chọn resource server đích"]
    G --> H{"Client và grant được phép audience?"}
    H -- "Không" --> X
    H -- "Có" --> I["Tính scope và ràng buộc tenant"]
    I --> J["Tạo iss, sub, aud và claim theo profile"]
    J --> K["Kiểm tra type, thời hạn, khóa và claim"]
    K --> L{"Payload phù hợp?"}
    L -- "Không" --> X
    L -- "Có" --> M["Ký JWT và trả qua kênh an toàn"]
~~~

Quy trình cần được áp dụng theo từng loại token:

1. **Xác định profile trước:** access token, ID token, token trao đổi hay JWT nội bộ có bộ quy tắc riêng. Không tạo payload rồi mới đoán nó thuộc loại token nào.
2. **Chọn issuer:** xác định security realm/authorization server từ cấu hình và ngữ cảnh được xác minh.
3. **Xác minh principal:** kiểm tra bằng chứng xác thực, client, grant và trạng thái; ánh xạ subject từ nguồn có thẩm quyền.
4. **Chọn audience:** xác định resource server dựa trên tài nguyên mà client được phép truy cập; giới hạn danh sách audience.
5. **Tính quyền:** quyết định scope/permission trong ngữ cảnh subject, client, audience, tenant và grant.
6. **Tạo và kiểm tra claim:** sinh claim hệ thống từ cấu hình và đồng hồ tin cậy; kiểm tra payload đúng profile, không chứa dữ liệu do client tự ghi đè.
7. **Ký token:** chỉ ký bằng khóa được issuer quản lý và thuật toán cho phép.

## 7. Xác minh issuer, audience và subject ở bên nhận

Bên nhận phải tự xác minh token theo cấu hình của chính nó. Không được tin ba claim chỉ vì chúng xuất hiện trong payload.

### 7.1. Quy tắc xác minh

Với một API dự kiến nhận access token:

- **Loại token:** kiểm tra token thuộc profile access token mà API hỗ trợ; dùng quy tắc phân biệt loại token và tránh chấp nhận ID token.
- **Chữ ký:** xác minh chữ ký với khóa gắn với issuer tin cậy, thuật toán nằm trong allowlist và quy tắc khóa phù hợp.
- **Issuer:** kiểm tra `iss` khớp chính xác một issuer mà API chấp nhận.
- **Audience:** kiểm tra `aud` chứa đúng định danh API; nếu không khớp thì từ chối.
- **Subject:** xác minh `sub` hiện diện và có định dạng/namespace phù hợp với profile; khi tra cứu chủ thể, dùng kết hợp issuer và subject.
- **Thời gian:** xác minh `exp`, `nbf` nếu có, và xử lý clock skew trong giới hạn nhỏ được cấu hình.
- **Quyền:** xác minh scope/permission và kiểm tra quyền trên tài nguyên cụ thể, bao gồm tenant/owner khi cần.

Thứ tự kỹ thuật có thể khác tùy thư viện, nhưng mọi bước phải hoàn tất trước khi tin token. Nếu dùng `iss` chưa xác minh để chọn cấu hình khóa trong hệ thống đa issuer, chỉ được dùng nó như **chỉ mục tra cứu trong danh sách issuer đã đăng ký**; sau đó phải xác minh chữ ký và so sánh lại `iss` chính xác. Không tải metadata/JWKS từ URL tùy ý trong token.

### 7.2. Tránh nhầm lẫn giữa các loại JWT

Một hệ thống có thể dùng JWT cho nhiều mục đích: ID token, access token, email verification, password reset hoặc token nội bộ. Nếu các loại token dùng chung cách xác minh lỏng lẻo, một token được phát hành cho mục đích này có thể bị chấp nhận sai ở mục đích khác.

Các biện pháp:

- Dùng profile, claim và quy tắc xác minh tách biệt; chỉ chấp nhận token đúng loại.
- Dùng header `typ` phù hợp profile khi profile quy định (ví dụ access token theo RFC 9068 sử dụng `at+jwt`).
- Tách audience, issuer hoặc khóa khi cần để các loại token có thể được phân biệt rõ.
- Không coi mọi JWT đã ký là bằng chứng có thể dùng cho mọi API hoặc mọi thao tác.

## 8. Ví dụ thực tế

### 8.1. Người dùng truy cập Orders API

Người dùng đăng nhập qua issuer nội bộ, dashboard xin access token cho Orders API:

~~~json
{
  "iss": "https://auth.example.net",
  "sub": "user-84",
  "aud": "https://api.example.net/orders",
  "client_id": "dashboard",
  "scope": "orders:read",
  "iat": 1900000000,
  "exp": 1900000900
}
~~~

- Issuer là identity/authorization server đã cấu hình.
- Subject là người dùng đã được xác minh trong namespace của issuer.
- Audience là Orders API, không phải dashboard.
- Client ID xác định ứng dụng yêu cầu token.
- Scope chỉ cho phép đọc đơn hàng; API vẫn phải kiểm tra người dùng có quyền đọc đơn hàng cụ thể hay không.

### 8.2. Dịch vụ gọi dịch vụ

Một billing worker đã xác thực bằng workload identity yêu cầu token cho Payments API:

~~~json
{
  "iss": "https://workload-auth.example.net",
  "sub": "billing-worker",
  "aud": "https://api.example.net/payments",
  "client_id": "billing-worker",
  "scope": "payments:charge",
  "iat": 1900000000,
  "exp": 1900000300
}
~~~

Trong ví dụ này, subject là service identity. Không gắn tên người dùng giả định vào `sub` vì không có người dùng cuối trong luồng. Payments API phải xác minh issuer, audience, token type, thời gian và quyền của workload.

### 8.3. Token dành cho API khác

Nếu một access token có `aud` là `https://api.example.net/payments` được gửi tới Orders API, Orders API phải từ chối token dù chữ ký hợp lệ và `sub` tồn tại. Audience sai có nghĩa token không được phát hành cho resource server đó.

### 8.4. Subject trùng chuỗi nhưng issuer khác

Hai IdP có thể cùng dùng `sub` là `12345`. Nếu hệ thống chỉ tra cứu `sub` mà bỏ qua `iss`, một tài khoản có thể bị ánh xạ nhầm sang tài khoản của miền khác. Khóa tra cứu danh tính phải bao gồm issuer và subject hoặc một định danh nội bộ đã được ánh xạ an toàn.

## 9. Mã giả phát hành và xác minh

Mã giả sau minh họa logic độc lập công nghệ cho access token:

~~~text
function issueAccessToken(request, verifiedContext):
    profile = tokenProfiles.require("access_token")
    client = clientRegistry.requireAuthenticatedClient(verifiedContext.client)

    issuer = trustedIssuerConfig.forSecurityRealm(
        verifiedContext.trustedRealm
    )

    subject = identityMapping.resolve(
        issuer.id,
        verifiedContext.authenticatedPrincipal
    )
    require subject.active

    audience = resourceRegistry.requireAllowedAudience(
        client,
        request.resource
    )

    scopes = policyEngine.authorize(
        subject,
        client,
        audience,
        verifiedContext.grant,
        request.requestedScopes
    )

    now = trustedClock.epochSeconds()
    claims = {
        "iss": issuer.identifier,
        "sub": subject.stableIdentifier,
        "aud": audience.identifier,
        "client_id": client.identifier,
        "iat": now,
        "exp": now + profile.allowedLifetime,
        "scope": scopes.allowedValues
    }

    profile.validateClaims(claims)
    return issuer.signer.sign(claims, profile.allowedAlgorithm)
~~~

Bên nhận:

~~~text
function validateAccessToken(token, apiConfig):
    profile = tokenProfiles.require("access_token")
    header, untrustedClaims = parseWithoutTrusting(token)

    issuerConfig = trustedIssuerRegistry.findAllowed(
        untrustedClaims.iss
    )
    require issuerConfig exists

    verifySignature(
        token,
        issuerConfig.trustedKeys,
        profile.allowedAlgorithms
    )

    claims = readVerifiedClaims(token)
    require claims.iss == issuerConfig.identifier
    require claims.aud contains apiConfig.audience
    require profile.acceptsType(header.typ)
    require currentTime < claims.exp
    require claims.nbf is absent or currentTime >= claims.nbf
    require profile.acceptsSubject(claims.sub)

    return authorizationPolicy.check(
        subject = (claims.iss, claims.sub),
        client = claims.client_id,
        audience = apiConfig.audience,
        scopes = claims.scope
    )
~~~

Đây là mô hình khái niệm. Trong triển khai thực tế, cần dùng thư viện JWT đã được kiểm chứng, tuân thủ profile chính xác, kiểm soát clock skew và xử lý lỗi an toàn. Không tự viết thuật toán mật mã hoặc tự giải mã rồi tin payload.

## 10. Các lỗi thiết kế thường gặp

| Lỗi | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Lấy `iss` từ request hoặc host header | Giả mạo miền phát hành, chọn nhầm khóa | Dùng issuer cấu hình và danh sách tin cậy |
| Không xác minh `iss` sau khi kiểm tra chữ ký | Chấp nhận token từ issuer khác | So sánh chính xác issuer theo cấu hình |
| Bỏ qua `aud` | Token của API A bị dùng ở API B | Mỗi resource server xác minh audience của mình |
| Dùng client ID làm audience của access token | Nhầm client với resource server | Tách `client_id` và `aud` theo vai trò |
| Dùng email làm `sub` | Subject đổi hoặc trùng, liên kết nhầm tài khoản | Dùng định danh ổn định trong namespace issuer |
| Chỉ tra cứu `sub` mà không xét issuer | Trộn danh tính từ các IdP | Dùng cặp `(iss, sub)` |
| Gán service identity vào token delegated như thể là người dùng | Sai chủ thể và sai ngữ nghĩa quyền | Xác định subject, client và actor theo profile |
| Chấp nhận mọi JWT có chữ ký hợp lệ | Token reset password/ID token bị dùng làm access token | Tách token type, audience và validation rules |
| Dùng wildcard hoặc so khớp chuỗi con cho audience | API ngoài dự kiến chấp nhận token | So khớp định danh audience chính xác |
| Để token có quá nhiều audience | Mở rộng bề mặt chấp nhận token | Cấp audience tối thiểu theo resource |

## 11. Checklist trước khi phát hành và chấp nhận JWT

**Ở issuer:**

- [ ] Issuer lấy từ cấu hình bảo mật đã đăng ký; realm/tenant được xác minh.
- [ ] Subject được ánh xạ từ principal đã xác thực; xác định rõ là người dùng, client hay workload.
- [ ] Audience là resource server được client/grant cho phép.
- [ ] Client ID, subject và actor (nếu có) không bị nhầm lẫn.
- [ ] Loại token và profile được xác định trước khi dựng payload.
- [ ] Claims không bị request ghi đè; thời hạn và khóa ký tuân thủ chính sách.
- [ ] Chỉ đưa audience và quyền tối thiểu cần thiết vào token.

**Ở resource server:**

- [ ] Chỉ tin issuer nằm trong danh sách đã cấu hình.
- [ ] Xác minh chữ ký, thuật toán, khóa và loại token.
- [ ] So sánh `iss` chính xác và kiểm tra `aud` có định danh API.
- [ ] Kiểm tra `sub` theo namespace issuer; không tra cứu subject đơn lẻ khi có nhiều issuer.
- [ ] Xác minh thời hạn và các claim bắt buộc của profile.
- [ ] Kiểm tra scope/permission và quyền trên tài nguyên cụ thể.

## 12. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa registered claims `iss`, `sub`, `aud` và quy tắc so sánh.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh issuer/audience, phân biệt loại token và phòng chống JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile access token JWT, bao gồm ngữ nghĩa `iss`, `sub`, `aud` và `client_id`.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): issuer và audience của ID token, subject identifier, authorized party và xác minh ID token.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): ngữ nghĩa subject token, actor token và delegation trong token exchange.

**Ghi nhớ:** `iss` xác định miền phát hành đáng tin cậy; `aud` giới hạn nơi token được chấp nhận; `sub` xác định principal mà token đại diện trong namespace của issuer. Chọn đúng cả ba giúp ngăn nhầm lẫn danh tính, nhầm resource server và sử dụng JWT sai mục đích.

