# Audience riêng cho từng API và ngăn token bị dùng chéo

## 1. Vì sao mỗi API cần audience riêng?

Trong OAuth 2.0, Access Token được cấp để client truy cập một hoặc nhiều tài nguyên theo authorization grant. Khi nhiều API cùng tin một Authorization Server, chữ ký hợp lệ và issuer đúng vẫn chưa đủ để một API chấp nhận token. API còn phải xác minh token có được phát hành cho chính tài nguyên đó hay không.

Claim **aud (audience)** của JWT biểu thị bên nhận mà token được dự định gửi tới. Một API chỉ nên chấp nhận token có audience phù hợp với định danh tài nguyên của chính nó. Nếu API hóa đơn chấp nhận mọi token được ký bởi cùng Identity Provider mà không kiểm tra audience, token dành cho API hồ sơ, API báo cáo hoặc một client khác có thể bị dùng nhầm.

Đây là dạng **audience confusion** hoặc **cross-service token use**: một credential hợp lệ trong ngữ cảnh A bị sử dụng ở ngữ cảnh B. Hệ quả có thể là vượt qua ranh giới dịch vụ, đọc dữ liệu ngoài phạm vi, hoặc gọi API bằng token có quyền được cấp cho một tài nguyên khác.

Nguyên tắc thiết kế:

- Mỗi Resource Server có một hoặc nhiều audience identifier được cấu hình rõ.
- Authorization Server cấp token với audience giới hạn theo tài nguyên mà client được phép truy cập.
- API kiểm tra audience sau khi xác minh bằng chứng mật mã và token profile.
- Không xem issuer, client_id, scope hoặc chữ ký hợp lệ là thứ thay thế cho audience.
- Khi một dịch vụ cần gọi dịch vụ khác, phải xác định rõ token nào dành cho dịch vụ nhận.

Nội dung thuộc module Security - JSON Web Token (JWT), chương Ranh giới dịch vụ. Phạm vi là OAuth/JWT Security tổng quát, không phụ thuộc Java, Spring Security hay một framework cụ thể.

## 2. Audience trong JWT là gì?

RFC 7519 định nghĩa claim **aud** để xác định người nhận mà JWT được dự định gửi tới. Giá trị có thể là:

- Một **StringOrURI**.
- Một mảng gồm các **StringOrURI**.

Nếu một JWT có audience, bên nhận phải xác định mình có được nhận diện trong giá trị aud hay không. Nếu không, token không được chấp nhận cho bên nhận đó.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org/",
  "sub": "user-123",
  "aud": "https://api.example.org/invoices",
  "exp": 1893456900
}
~~~

Token trên được dự định cho API hóa đơn có định danh https://api.example.org/invoices. API hồ sơ không được chấp nhận token này chỉ vì nó cũng tin issuer https://identity.example.org/.

### 2.1. Audience là định danh tài nguyên, không nhất thiết là URL request

Audience thường được biểu diễn bằng URI, nhưng nó là **identifier** theo hợp đồng giữa Authorization Server và Resource Server. Nó không nhất thiết phải là URL của một endpoint HTTP có thể truy cập.

Ví dụ:

~~~text
https://api.example.org/invoices
urn:example:resource:invoice-api
api://invoice-service
~~~

Các giá trị trên chỉ là ví dụ. Tổ chức cần chọn một quy ước ổn định, duy nhất và được cấu hình đồng nhất ở issuer lẫn resource server.

Không nên dùng URL của từng route như /invoices/123, vì audience định danh tài nguyên/API, còn quyền đối với route và đối tượng cụ thể được kiểm tra ở bước authorization.

Không truy cập URL hoặc thực hiện discovery chỉ vì aud chứa một URI. Audience là dữ liệu định danh, không phải chỉ thị để tải tài nguyên hay lấy khóa.

### 2.2. So khớp audience chính xác

StringOrURI trong JWT được so sánh phân biệt chữ hoa/chữ thường và không áp dụng URL canonicalization tùy tiện. Nếu policy cấu hình:

~~~text
https://api.example.org/invoices
~~~

thì không tự coi các giá trị sau là tương đương:

~~~text
https://api.example.org/invoices/
https://API.example.org/invoices
https://api.example.org:443/invoices
https://api.example.org
~~~

Không dùng kiểm tra substring, prefix hoặc chỉ so domain. API cần so khớp theo đúng identifier đã đăng ký. Nếu tổ chức muốn đổi identifier, cần thay đổi cấu hình và phát hành token theo quy trình tương thích.

## 3. Phân biệt aud với iss, sub, client_id và scope

Các claims này mô tả những vai trò khác nhau:

| Claim/thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **iss** | Bên phát hành token | Authorization Server |
| **sub** | Chủ thể mà token nói tới | Người dùng hoặc workload |
| **aud** | Resource Server/bên nhận được dự định | API hóa đơn |
| **client_id** | OAuth client đã yêu cầu token | web-portal |
| **scope** | Phạm vi quyền được cấp theo authorization grant | invoice:read |
| **azp** | Authorized party theo OpenID Connect trong ngữ cảnh áp dụng | Client OIDC được ủy quyền |

Không thay thế audience bằng các trường khác:

- Issuer đúng chỉ chứng minh token đến từ nguồn phát hành được tin cậy; issuer có thể phát hành token cho nhiều API.
- Client ID xác định ứng dụng yêu cầu token, không xác định API được phép nhận token.
- Scope mô tả quyền, không xác định tài nguyên nhận token.
- Subject xác định chủ thể, không xác định nơi token được sử dụng.
- azp có quy tắc riêng trong OpenID Connect; không dùng nó thay cho aud của Access Token.

Ví dụ, client web-portal có thể được cấp invoice:read cho API hóa đơn. Token cần audience của API hóa đơn. Một client khác cũng có thể có scope cùng tên nhưng audience khác; scope không làm hai tài nguyên trở thành một.

## 4. Thiết kế audience riêng cho từng API

Giả sử hệ thống có ba Resource Server:

| API | Audience identifier |
| --- | --- |
| API hóa đơn | https://api.example.org/invoices |
| API hồ sơ | https://api.example.org/profiles |
| API báo cáo | https://api.example.org/reports |

Authorization Server phát hành token theo resource mà client yêu cầu và được phép truy cập. Mỗi API chỉ chấp nhận audience đã cấu hình cho nó.

~~~mermaid
flowchart TD
    C["Client"] --> AS["Authorization Server"]
    AS -->|"Token aud=invoices"| TI["Client giữ token hóa đơn"]
    AS -->|"Token aud=profiles"| TP["Client giữ token hồ sơ"]
    TI -->|"Gửi tới"| I["Invoice API"]
    TP -->|"Gửi tới"| P["Profile API"]
    TP -.->|"Nếu gửi nhầm token hồ sơ"| I
    I --> X["Từ chối: audience mismatch"]
    P --> Y["Tiếp tục validation nếu các bước khác đạt"]
~~~

Sơ đồ minh họa nguyên tắc phân tách. Trong thực tế, client chỉ nhận token cho tài nguyên mà grant, client và policy cho phép; client không được tự đặt audience tùy ý để mở rộng quyền.

### 4.1. Một API có thể có nhiều endpoint

Audience thường đại diện cho toàn bộ Resource Server hoặc một nhóm tài nguyên được quản lý chung. Các endpoint bên trong API có thể dùng cùng audience nhưng vẫn phải kiểm tra scope, role, ownership, tenant và các điều kiện nghiệp vụ.

Ví dụ:

- GET /invoices/123 yêu cầu invoice:read và quyền đọc hóa đơn 123.
- POST /invoices yêu cầu invoice:create.
- DELETE /invoices/123 yêu cầu quyền xóa và điều kiện nghiệp vụ tương ứng.

Token có aud của Invoice API chỉ vượt qua ranh giới **đúng Resource Server**. Nó không tự cấp quyền cho mọi endpoint trong API.

### 4.2. Một API có thể có nhiều audience identifier

Trong quá trình đổi tên, nâng phiên bản hoặc hỗ trợ nhiều địa chỉ logic, một Resource Server có thể phải nhận nhiều identifier. Khi đó:

- Danh sách identifier được cấu hình rõ tại Resource Server.
- Mỗi identifier phải thực sự đại diện cho cùng ranh giới tài nguyên theo policy.
- Thời gian hỗ trợ song song phải có giới hạn.
- Không thêm domain hoặc audience rộng chỉ để làm token cũ tiếp tục hoạt động.
- Có kế hoạch ngừng identifier cũ và quan sát token còn sử dụng.

Việc một API có nhiều audience identifier không có nghĩa một token phải chứa tất cả chúng. Policy cấp token nên chỉ đưa audience cần thiết vào token.

## 5. Token có nhiều audience và rủi ro mở rộng phạm vi

RFC 7519 cho phép aud là mảng. Điều đó hữu ích khi token thực sự được dự định gửi tới nhiều bên nhận. Tuy nhiên, một token chứa nhiều audience có thể được chấp nhận bởi nhiều Resource Server nếu mỗi server kiểm tra membership trong mảng.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org/",
  "aud": [
    "https://api.example.org/invoices",
    "https://api.example.org/reports"
  ],
  "scope": "invoice:read report:read"
}
~~~

Token này có thể được cả hai API chấp nhận nếu policy của chúng cho phép. Khi token bị đánh cắp, phạm vi sử dụng của kẻ tấn công rộng hơn một token chỉ dành cho một API.

### 5.1. Không cấm mảng aud một cách máy móc

Mảng aud không tự động là lỗi. Một số profile hoặc kiến trúc có lý do hợp lệ để một token dành cho nhiều recipient. Tuy nhiên, cần đánh giá:

- Mỗi recipient có thực sự cần nhận cùng credential không?
- Các API có cùng ranh giới tin cậy và mức nhạy cảm không?
- Scope có được giới hạn riêng cho từng tài nguyên không?
- Nếu một API bị xâm phạm, token có thể bị dùng ở API còn lại không?
- Có thể cấp token riêng cho từng resource để giảm blast radius không?

Nếu API yêu cầu chỉ một audience, policy phải kiểm tra đúng một phần tử và từ chối token có thêm recipient ngoài hợp đồng. Nếu profile cho phép nhiều audience, Resource Server phải kiểm tra audience của chính mình và áp dụng các điều kiện profile bổ sung.

### 5.2. Tránh audience quá rộng

Các giá trị như api, backend, all-services hoặc một domain gốc chung có thể làm mất ranh giới giữa nhiều Resource Server. Chỉ dùng identifier rộng nếu nó thực sự đại diện cho một Resource Server duy nhất và mọi thành phần có cùng hợp đồng bảo mật.

Không dùng audience của gateway chung cho mọi microservice rồi để từng service tự chấp nhận token đó. Gateway và service phía sau có thể là hai resource recipient khác nhau.

## 6. Authorization Server cấp audience như thế nào?

OAuth 2.0 Resource Indicators (RFC 8707) cho phép client chỉ ra tài nguyên mà nó muốn truy cập thông qua tham số resource trong authorization request hoặc token request theo profile áp dụng.

Ví dụ:

~~~http
POST /token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=...&
redirect_uri=...&
resource=https%3A%2F%2Fapi.example.org%2Finvoices
~~~

resource là chỉ báo client gửi tới Authorization Server. Nó không phải bằng chứng rằng client được phép truy cập resource đó. Authorization Server phải xác minh client, grant, consent, policy và quyền cấp token trước khi phát hành.

### 6.1. Resource indicator và aud không phải cùng một bước

| Giá trị | Bên sử dụng | Vai trò |
| --- | --- | --- |
| OAuth resource request parameter | Authorization Server | Client yêu cầu token dành cho tài nguyên nào |
| JWT aud claim | Resource Server | Token được phát hành cho bên nhận nào |

Authorization Server có thể dùng resource indicator để quyết định audience và phạm vi token được cấp. Resource Server vẫn phải xác minh aud trong token; không tin tham số resource mà client từng gửi như bằng chứng cho request hiện tại.

### 6.2. Client không được tự mở rộng audience

Client có thể yêu cầu một resource identifier, nhưng Authorization Server cần kiểm tra:

- Resource có nằm trong danh sách được hỗ trợ không?
- Client/grant có quyền yêu cầu resource đó không?
- User consent hoặc policy có cho phép không?
- Scope có hợp lệ với resource đó không?
- Có cần cấp token riêng cho từng resource không?

Nếu client yêu cầu resource ngoài quyền được cấp, Authorization Server phải từ chối hoặc xử lý theo quy tắc giao thức; không phát hành token chỉ vì tham số resource có cú pháp hợp lệ.

## 7. Resource Server phải xác minh audience

Mỗi API cần một policy validation riêng, chứa issuer được tin cậy, audience identifier, allowlist thuật toán, token profile và claims bắt buộc.

Khi nhận Access Token dạng JWT, Resource Server cần:

1. Xác định endpoint/resource context từ cấu hình tin cậy.
2. Chọn policy dành cho API đó.
3. Parse token trong giới hạn và xem header/claims là chưa tin cậy.
4. Xác minh chữ ký hoặc authenticated decryption bằng khóa thuộc issuer được phép.
5. Kiểm tra token profile và loại token.
6. Kiểm tra iss khớp issuer tin cậy.
7. Kiểm tra aud chứa đúng audience identifier của API theo policy.
8. Kiểm tra thời gian, claims bắt buộc và các ràng buộc khác.
9. Kiểm tra scope/permission và quyền đối với tài nguyên cụ thể.

Không tra cứu khóa từ một issuer tùy ý chỉ vì token khai báo iss. Nguồn khóa phải được gắn với issuer đã cấu hình. Audience mismatch phải dẫn tới từ chối, ngay cả khi chữ ký hợp lệ.

### 7.1. Quy tắc kiểm tra aud

Pseudocode:

~~~text
function validateAudience(claims, resourceServerPolicy):
    require claims.aud exists
    require claims.aud is StringOrURI or array of StringOrURI

    expected = resourceServerPolicy.audienceIdentifier

    if resourceServerPolicy.requireSingleAudience:
        require claims.aud is a single StringOrURI
        require claims.aud == expected
    else:
        audiences = normalizeToArrayWithoutChangingValues(claims.aud)
        require expected is an exact member of audiences

    return VALID
~~~

Đây là pseudocode minh họa. Không được “normalize” bằng cách lowercase, bỏ slash, so domain hoặc canonicalize URI. Tên hàm chỉ chuyển dạng chuỗi thành mảng để xử lý; giá trị so khớp vẫn giữ nguyên.

requireSingleAudience là một lựa chọn policy của ứng dụng/profile, không phải yêu cầu chung của mọi JWT. Nếu profile cho phép nhiều recipient, dùng exact membership và các ràng buộc tương ứng.

### 7.2. Không dùng aud thay cho authorization

Audience chỉ xác định Resource Server được nhận token. Sau khi audience hợp lệ, API vẫn phải kiểm tra:

- Scope hoặc quyền cần cho endpoint.
- Subject/client có quyền trên tài nguyên cụ thể không.
- Tenant trong token có khớp tenant context tin cậy không.
- Trạng thái tài khoản, phiên và tài nguyên có còn cho phép thao tác không.
- Các điều kiện nghiệp vụ khác.

Token có aud đúng nhưng thiếu scope vẫn phải bị từ chối cho thao tác yêu cầu scope đó. Token có scope đúng nhưng aud sai cũng phải bị từ chối ngay tại ranh giới Resource Server.

## 8. Ngăn nhầm lẫn giữa Access Token, ID Token và JWT khác

Audience là một ranh giới quan trọng nhưng không phải ranh giới duy nhất. OpenID Connect ID Token thường có audience là client OIDC (client_id), vì ID Token được phát hành để client xác minh kết quả đăng nhập.

Resource Server không được chấp nhận ID Token làm Access Token chỉ vì:

- ID Token có chữ ký hợp lệ.
- Issuer giống với issuer của Access Token.
- Subject và audience có vẻ hợp lý.
- Payload chứa scope hoặc role do một triển khai tùy biến thêm.

Với JWT Access Token theo RFC 9068, Resource Server cần áp dụng đúng profile, bao gồm typ là at+jwt và các claims/quy tắc xác minh của profile. typ giúp phân biệt loại token nhưng vẫn phải kiểm tra chữ ký, issuer, audience và claims.

RFC 8725 khuyến nghị các loại JWT khác nhau có validation rules loại trừ lẫn nhau khi có nguy cơ nhầm lẫn. Có thể kết hợp:

- Audience riêng cho resource.
- Token type/profile riêng.
- Claims bắt buộc riêng.
- Issuer hoặc key policy riêng khi phù hợp.
- Endpoint/validator riêng.

Không dùng một hàm “chữ ký hợp lệ thì chấp nhận” cho mọi JWT trong hệ thống.

## 9. Ranh giới audience trong kiến trúc gateway và microservices

Một gateway thường nhận request từ client rồi chuyển tiếp tới các service nội bộ. Đây là nơi dễ xảy ra lỗi audience:

1. Client nhận token có audience của API Gateway.
2. Gateway xác minh token thành công.
3. Gateway chuyển nguyên bearer token tới Invoice Service.
4. Invoice Service chấp nhận token chỉ vì chữ ký hợp lệ hoặc issuer đúng.

Invoice Service đã nhận token không được phát hành cho nó. Gateway xác minh thành công không tự động biến token thành credential dành cho mọi service phía sau.

### 9.1. Mỗi service xác minh token dành cho chính nó

Nếu client gọi trực tiếp từng service, mỗi service cần audience identifier riêng và validator riêng. Client lấy token tương ứng cho từng API.

~~~text
Client
  |-- token aud=invoice-api --> Invoice API
  |-- token aud=profile-api --> Profile API
  |-- token aud=report-api  --> Reporting API
~~~

Đây là cách phân tách đơn giản và rõ ràng khi client được phép gọi từng Resource Server.

### 9.2. Gateway xác minh rồi chuyển tiếp identity context

Nếu service nội bộ chỉ nhận request từ gateway, có thể thiết kế gateway làm điểm xác minh bên ngoài. Tuy nhiên, gateway phải chuyển tiếp một context nội bộ có integrity protection và được service nhận tin cậy:

- Service chỉ nhận kết nối từ gateway/service identity đã xác thực.
- Gateway xóa các header identity do client tự gửi trước khi thêm context đã xác minh.
- Context được bảo vệ bằng kênh và cơ chế xác thực service-to-service phù hợp.
- Context chỉ chứa claims cần thiết, có audience/service recipient rõ ràng.
- Service vẫn kiểm tra quyền trên hành động và tài nguyên của nó.

Một header như X-User-Id hoặc X-Roles không đáng tin chỉ vì gateway thường là nơi thêm header đó. Nếu client có thể gửi cùng header và gateway không loại bỏ nó, attacker có thể giả mạo identity context.

### 9.3. Token exchange cho downstream API

Nếu Gateway hoặc một service cần gọi Resource Server khác bằng danh tính/ủy quyền đã xác minh, OAuth Token Exchange (RFC 8693) có thể được dùng để xin một token mới dành cho audience/resource đích.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant AS as Authorization Server
    participant I as Invoice API
    C->>G: Token dành cho Gateway
    G->>G: Xác minh token và quyền gọi downstream
    G->>AS: Token Exchange, yêu cầu audience Invoice API
    AS->>AS: Kiểm tra subject token, actor, policy và resource
    AS-->>G: Token mới aud=Invoice API
    G->>I: Request với token dành cho Invoice API
    I->>I: Xác minh issuer, signature, audience và scope
    I-->>G: Response
    G-->>C: Response
~~~

Token Exchange không tự động cấp quyền. Authorization Server phải kiểm tra token nguồn, client/actor, resource đích và policy trước khi phát hành token mới. Token mới phải có audience và quyền phù hợp với dịch vụ nhận.

## 10. Audience theo môi trường, phiên bản và tenant

Audience identifier cần được quản trị nhất quán:

### 10.1. Tách môi trường

Nếu môi trường development, staging và production có ranh giới dữ liệu hoặc khóa khác nhau, không nên dùng một audience rộng khiến token từ môi trường này được chấp nhận ở môi trường khác.

Ví dụ:

~~~text
urn:example:prod:invoice-api
urn:example:staging:invoice-api
~~~

Các identifier trên chỉ minh họa. Điều quan trọng là validator production không chấp nhận token chỉ dành cho staging và ngược lại.

### 10.2. Phiên bản API

Không phải mọi version API đều cần audience riêng. Nếu các version cùng một Resource Server và có cùng ranh giới bảo mật, có thể dùng chung audience rồi kiểm tra scope/route theo policy. Nếu version mới có ranh giới dữ liệu, quyền hoặc mức tin cậy khác, có thể cần identifier riêng.

Không tạo audience theo từng URL route nếu điều đó chỉ lặp lại authorization logic. Chọn ranh giới theo tài nguyên và miền tin cậy, không theo cấu trúc URL một cách máy móc.

### 10.3. Tenant

Không nhất thiết tạo một audience mới cho từng tenant. Thông thường, audience định danh API; tenant được kiểm tra bằng claim/context riêng và phải được đối chiếu với tenant đã xác định từ request hoặc session tin cậy.

Chỉ đưa tenant vào audience nếu mô hình bảo mật thực sự coi mỗi tenant là một Resource Server/recipient riêng. Không dùng aud thay cho tenant authorization.

## 11. Caching và vận hành audience policy

Resource Server có thể cache metadata issuer, JWKS hoặc kết quả validation để giảm độ trễ. Cache cần gắn với policy đúng:

- Issuer và nguồn khóa.
- Audience identifier.
- Token profile và allowlist thuật toán.
- Phiên bản policy.
- Thời điểm hết hạn hoặc giới hạn tuổi của kết quả cache.

Không cache một kết quả “JWT hợp lệ” rồi dùng lại ở API khác. Kết quả xác minh chữ ký có thể dùng chung ở mức kỹ thuật trong một số kiến trúc, nhưng kết luận **token được phép cho audience nào** phải được kiểm tra theo policy của từng Resource Server.

Khi đổi audience identifier hoặc tách một API thành nhiều dịch vụ, cần:

1. Cập nhật cấu hình Authorization Server và Resource Server theo kế hoạch.
2. Có thời gian chuyển đổi nếu cần hỗ trợ token cũ.
3. Giới hạn rõ audience cũ được chấp nhận ở đâu và tới khi nào.
4. Theo dõi token bị từ chối do audience mismatch.
5. Loại bỏ identifier cũ sau khi hết thời gian chuyển đổi.

Không thêm wildcard hoặc audience chung chỉ để xử lý nhanh lỗi tương thích.

## 12. Mã giả validation riêng cho từng API

~~~text
function validateApiAccessToken(rawToken, apiPolicy):
    require apiPolicy is selected from trusted endpoint configuration
    parsed = strictParseJwtWithinLimits(rawToken)

    header = parsed.protectedHeader
    require header.alg in apiPolicy.allowedAlgorithms
    require header.typ matches apiPolicy.requiredAccessTokenType

    key = trustedIssuerKeyResolver.resolve(
        issuer = apiPolicy.trustedIssuer,
        kid = header.kid
    )
    require key is compatible with header.alg
    require verifyJws(rawToken, key, apiPolicy.allowedAlgorithms)

    claims = verifiedClaims(rawToken)
    require claims.iss exactly equals apiPolicy.trustedIssuer
    require validateAudience(claims.aud, apiPolicy)
    require validateTimeClaims(claims, apiPolicy)
    require validateAccessTokenProfile(claims, apiPolicy)

    require requiredScopesArePresent(claims, apiPolicy.requiredScopes)
    require tenantBindingMatchesTrustedContext(claims, apiPolicy)

    return ValidatedTokenContext(
        issuer = claims.iss,
        subject = claims.sub,
        audience = claims.aud,
        resourceServer = apiPolicy.resourceServerId,
        policyId = apiPolicy.id
    )
~~~

Mỗi API gọi validator với policy của chính nó. Không truyền một apiPolicy do client tự chọn và không suy ra audience mong đợi từ claim aud chưa xác minh.

## 13. Ví dụ kiểm tra chéo giữa ba API

Giả sử Authorization Server phát hành:

| Token | aud | Scope |
| --- | --- | --- |
| T1 | https://api.example.org/invoices | invoice:read |
| T2 | https://api.example.org/profiles | profile:read |
| T3 | https://api.example.org/reports | report:read |

Kết quả mong đợi:

| API nhận | T1 | T2 | T3 |
| --- | --- | --- | --- |
| Invoice API | Chấp nhận nếu mọi validation và authorization đạt | Từ chối audience | Từ chối audience |
| Profile API | Từ chối audience | Chấp nhận nếu mọi validation và authorization đạt | Từ chối audience |
| Reporting API | Từ chối audience | Từ chối audience | Chấp nhận nếu mọi validation và authorization đạt |

Bảng giả định mỗi token chỉ có một audience tương ứng. Nếu token có nhiều audience, kết quả phải theo policy recipient đã định nghĩa; không được tự động coi mọi mảng aud là sai hoặc chấp nhận mọi phần tử ngoài phạm vi.

## 14. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Không kiểm tra aud | Token dành cho API khác có thể bị chấp nhận | Mỗi Resource Server kiểm tra audience của chính nó |
| Dùng một aud chung cho toàn bộ backend | Mất ranh giới giữa các dịch vụ | Identifier riêng theo resource/security boundary |
| Coi iss đúng là đủ | Cùng issuer có thể phát hành token cho nhiều API | Kiểm tra cả iss và aud |
| Dùng client_id thay cho aud | Token được cấp cho client có thể bị dùng ở sai Resource Server | Phân biệt client và resource recipient |
| Dùng scope thay cho aud | Quyền đúng tên nhưng dành cho API khác | Kiểm tra audience trước, scope sau |
| So khớp aud bằng substring/domain | Chấp nhận identifier gần giống hoặc sai tài nguyên | So khớp StringOrURI chính xác |
| Coi URI trong aud là URL cần truy cập | Có thể tạo hành vi fetch/discovery ngoài ý muốn | Dùng aud như identifier tĩnh |
| Chấp nhận mảng aud không giới hạn | Token bị đánh cắp có thể dùng ở nhiều API | Cấp audience tối thiểu; policy kiểm soát recipient |
| Gateway xác minh rồi mọi service tin raw token | Downstream nhận token sai audience | Service tự validate hoặc dùng context/token nội bộ được bảo vệ |
| Cache kết quả token valid cho mọi API | Kết quả validation bị dùng sai resource context | Cache theo issuer, audience, profile và policy |
| Coi ID Token là Access Token | Nhầm client audience với API audience | Validator riêng và explicit typing |
| Coi audience đúng là đủ quyền | Token truy cập mọi tài nguyên trong API | Kiểm tra scope, tenant và quyền đối tượng |
| Dùng wildcard để hỗ trợ migration | Audience cũ/mới có thể bị dùng chéo | Chuyển đổi có thời hạn và policy rõ |

## 15. Ma trận kiểm thử audience isolation

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Audience đúng | Token có đúng aud của API | Qua bước audience nếu các validation khác đạt |
| Audience sai | Token có aud của API khác | Từ chối |
| Thiếu aud | Token không có aud trong profile yêu cầu | Từ chối |
| Sai kiểu | aud là object/number hoặc mảng có phần tử sai kiểu | Từ chối |
| Exact match | aud khác slash, case, port hoặc path | Từ chối nếu không đúng identifier đã cấu hình |
| Mảng aud | API hiện tại là một phần tử được phép | Xử lý theo policy multi-audience |
| Mảng mở rộng | Token có thêm API ngoài recipient policy | Từ chối nếu policy yêu cầu single/closed audience |
| Issuer | aud đúng nhưng iss sai | Từ chối |
| Chữ ký | aud đúng nhưng chữ ký sai | Từ chối |
| Token type | ID Token có chữ ký đúng nhưng gửi tới API | Từ chối |
| Scope | aud đúng nhưng thiếu scope | Từ chối thao tác |
| Tenant | aud đúng nhưng tenant mismatch | Từ chối theo tenant policy |
| Gateway | Token dành cho gateway được gửi nguyên tới service khác | Service từ chối audience mismatch |
| Token exchange | Token mới dành cho downstream API | Chấp nhận nếu mọi validation và authorization đạt |
| Cache | Kết quả validate ở API A được dùng tại API B | Không được tái sử dụng kết luận audience |
| Migration | Token dùng audience cũ sau thời hạn chuyển đổi | Từ chối |

Nên có kiểm thử tích hợp chứng minh một token được phát hành cho API A không thể truy cập API B, kể cả khi cả hai API dùng chung issuer, JWKS và signing key.

## 16. Checklist triển khai

1. [ ] Mỗi Resource Server có audience identifier ổn định và được cấu hình tin cậy.
2. [ ] Authorization Server chỉ cấp audience theo resource mà client/grant được phép truy cập.
3. [ ] Phân biệt rõ resource request parameter với JWT aud claim.
4. [ ] Resource Server kiểm tra aud sau khi xác minh chữ ký/decrypt và token profile.
5. [ ] So khớp audience chính xác theo StringOrURI; không substring, prefix hoặc URL normalization tùy tiện.
6. [ ] Không dùng iss, sub, client_id, azp hoặc scope thay cho aud.
7. [ ] Audience rộng/mảng nhiều recipient chỉ được dùng khi có nhu cầu và policy rõ.
8. [ ] API vẫn kiểm tra scope, tenant, subject và quyền trên tài nguyên sau khi aud đạt.
9. [ ] Access Token, ID Token và assertion có validator/profile riêng.
10. [ ] Gateway/downstream có mô hình rõ: mỗi service tự xác minh audience, hoặc nhận identity context/token nội bộ được bảo vệ.
11. [ ] Dùng token exchange khi cần credential mới cho downstream audience.
12. [ ] Cache validation được ràng buộc với issuer, audience, profile và policy version.
13. [ ] Có kế hoạch migration audience cũ/mới với thời hạn cụ thể.
14. [ ] Có negative tests cho cross-API token use, ID Token substitution, audience array và gateway forwarding.

## 17. Tài liệu tiêu chuẩn liên quan

- **RFC 7519 — JSON Web Token (JWT):** claim aud, kiểu StringOrURI và quy tắc recipient validation.
- **RFC 8725 — JSON Web Token Best Current Practices:** audience validation, token substitution và mutually exclusive validation rules.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile Access Token dạng JWT, typ at+jwt và claims dành cho Resource Server.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** tham số resource để client chỉ ra tài nguyên dự định truy cập và hỗ trợ audience restriction.
- **RFC 8693 — OAuth 2.0 Token Exchange:** cấp token mới cho subject/actor/resource đích theo policy.
- **OpenID Connect Core 1.0:** audience của ID Token và quy tắc xác minh dành cho client OIDC.

**Nguyên tắc ghi nhớ:** iss cho biết ai phát hành, client_id cho biết client nào yêu cầu, scope mô tả quyền, còn aud xác định Resource Server được nhận token. Mỗi API phải kiểm tra audience của chính nó sau khi xác minh token. Khi cần gọi dịch vụ khác, hãy cấp hoặc trao đổi credential dành cho audience đích thay vì tái sử dụng token của dịch vụ hiện tại.
