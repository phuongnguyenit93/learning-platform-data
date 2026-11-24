# Scope trong OAuth 2.0 và OpenID Connect: giới hạn quyền truy cập theo vòng đời danh tính IAM

## 1. Scope là gì và giải quyết vấn đề nào?

Trong **OAuth 2.0**, **scope** là cách diễn đạt **phạm vi truy cập mà client yêu cầu hoặc được authorization server cấp**, thường xuất hiện như một tập các chuỗi định danh quyền. Mục tiêu là tránh một ứng dụng phải nhận quyền không giới hạn chỉ để thực hiện một số thao tác cụ thể trên API.

Ví dụ, ứng dụng tổng hợp báo cáo chỉ cần đọc dữ liệu có thể xin scope **reports:read** thay vì cả **reports:write** và **reports:admin**. Authorization server quyết định có cấp scope được yêu cầu hay không theo chính sách, grant, tài khoản và cấu hình client. Sau đó, **resource server (API)** phải kiểm tra scope **cùng với các điều kiện ủy quyền khác** trước khi cho phép thao tác.

Scope đặc biệt quan trọng đối với quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**:

- **Joiner:** ứng dụng và account mới chỉ được cấp phạm vi tối thiểu cho nhiệm vụ đã duyệt.
- **Mover:** quyền theo vai trò cũ cần bị rút lại; scope hoặc grant cũ có thể vẫn tồn tại nếu không được đánh giá lại.
- **Leaver:** ngăn cấp token mới, thu hồi grant/refresh token, xử lý access token đang còn hạn và đối soát quyền ở API.

Trong hệ thống **Identity and Access Management (IAM)**, scope kết nối OAuth/OIDC với **Identity Provider (IdP), Single Sign-On (SSO), SCIM, RBAC/ABAC, tài khoản dịch vụ và audit**. Tuy nhiên, cần nhớ nguyên tắc cốt lõi:

> **Token có scope cần thiết chỉ là một điều kiện cho phép xem xét truy cập; không phải giấy phép truy cập mọi tài nguyên cùng loại.**

## 2. Phân biệt scope, role, entitlement, claim và audience

Các khái niệm sau thường xuất hiện cùng nhau nhưng giải quyết những câu hỏi khác nhau.

| Khái niệm | Trả lời câu hỏi | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **Scope** | Client/token được giới hạn yêu cầu những thao tác API nào? | **reports:read** | Không tự chỉ ra người dùng được đọc báo cáo nào |
| **Role (RBAC)** | Chủ thể giữ trách nhiệm/quyền theo vai trò nào? | **Analyst**, **FinanceAdmin** | Cần ánh xạ role sang quyền thật trên tài nguyên |
| **Entitlement** | Chủ thể được cấp quyền cụ thể nào tại hệ thống đích? | Đọc workspace Atlas | Có thể tồn tại ngoài OAuth token |
| **Attribute (ABAC)** | Thuộc tính nào ảnh hưởng quyết định? | organizationId, projectId, employmentStatus | Phải lấy từ nguồn đáng tin cậy và đủ mới |
| **Claim** | Token/response mang thông tin gì? | sub, aud, iss, exp, scope | Claim chỉ đáng tin khi token được xác minh và đúng ngữ cảnh |
| **Audience** | Token dành cho API/resource server nào? | https://api.example.invalid | Scope không thay thế kiểm tra audience |
| **Consent/approval** | Ai đồng ý hoặc phê duyệt client được sử dụng quyền? | Phê duyệt đọc báo cáo | Không tự chứng minh tài nguyên đang cho phép truy cập |
| **Policy decision** | Request hiện tại có được phép không? | Allow/Deny cho report-42 | Cần kiểm tra tại điểm bảo vệ tài nguyên |

Ví dụ, người dùng Lan có role Analyst của organization A, còn token mang scope **reports:read**. API vẫn phải từ chối yêu cầu đọc một báo cáo thuộc organization B nếu Lan không có membership hoặc entitlement tương ứng. Cùng scope có thể được dùng để gọi API cho nhiều tài nguyên, nhưng **quyền theo từng tài nguyên** phải do lớp authorization quyết định.

## 3. Bốn vai trò chính trong OAuth 2.0

| Vai trò | Trách nhiệm |
| --- | --- |
| **Resource owner** | Chủ thể có quyền cho phép truy cập tài nguyên theo mô hình và chính sách |
| **Client** | Ứng dụng yêu cầu được cấp quyền truy cập |
| **Authorization server** | Xác thực/áp dụng chính sách, quản lý grant và phát hành token |
| **Resource server** | API lưu hoặc phục vụ tài nguyên, thực thi kiểm tra token và quyền truy cập |

Trong trường hợp người dùng doanh nghiệp, resource owner thường là người dùng theo mô hình OAuth, nhưng **quyền phê duyệt tài nguyên có thể thuộc tổ chức hoặc chủ tài nguyên**. Người dùng không thể tự cấp cho client quyền họ vốn không có. Trong một luồng **client credentials**, client có thể hành động dưới danh tính máy; không phải lúc nào cũng có một người dùng hiện diện để consent.

~~~mermaid
flowchart LR
    U["Người dùng / resource owner"] -->|"Xác thực, consent khi cần"| AS["Authorization Server / IdP"]
    C["OAuth client"] -->|"Yêu cầu scope và grant"| AS
    AS -->|"Phát hành access token với phạm vi được cấp"| C
    C -->|"Gọi API bằng access token"| API["Resource Server / API"]
    API --> V["Xác minh token, audience, scope, RBAC/ABAC"]
    V --> D{"Cho phép?"}
    D -->|"Có"| R["Tài nguyên được phép"]
    D -->|"Không"| X["403 / lỗi phù hợp"]
    HR["HRIS / nguồn bảo trợ"] --> IAM["IAM/IGA: vòng đời, entitlement"]
    IAM --> AS
    IAM --> V
~~~

Sơ đồ là mô hình trách nhiệm. Trong một sản phẩm cụ thể, IdP và authorization server có thể cùng nằm trên một nền tảng, còn policy engine có thể ở gateway, service hoặc cả hai.

## 4. Cú pháp scope và cách authorization server cấp quyền

Trong OAuth 2.0, một giá trị scope thường là **danh sách chuỗi phân cách bằng dấu cách**. Tên từng scope do authorization server/resource server định nghĩa; chuẩn OAuth không quy định nghĩa chung cho mọi chuỗi như **read** hay **admin**.

Ví dụ, tập scope yêu cầu:

~~~text
reports:read reports:export
~~~

Trong truy vấn URL, dấu cách cần được **URL-encode**, ví dụ:

~~~text
scope=reports%3Aread%20reports%3Aexport
~~~

Những nguyên tắc quan trọng:

1. **Tên scope có phân biệt chữ hoa/thường** theo đặc tính chuỗi, do đó **reports:read** và **Reports:Read** không nên tự xem là tương đương.
2. **Thứ tự các scope không mang ý nghĩa phân quyền**; so sánh tập giá trị theo định nghĩa của authorization server.
3. **Client yêu cầu không có nghĩa chắc chắn được cấp.** Authorization server có thể cấp ít hơn, từ chối hoặc yêu cầu phê duyệt theo chính sách.
4. **Scope có thể được bỏ qua khi yêu cầu**, nếu authorization server định nghĩa phạm vi mặc định; không suy đoán phạm vi mặc định có an toàn.
5. Nếu phạm vi được cấp khác phạm vi yêu cầu, phản hồi cấp token cần cho client biết giá trị scope được cấp theo quy tắc giao thức.
6. Mỗi API phải có **hợp đồng scope rõ ràng**. Không tự suy tên scope từ HTTP method hay tên đường dẫn.

### Phạm vi yêu cầu khác phạm vi được cấp

Ví dụ client yêu cầu:

~~~text
requested: reports:read reports:export
granted:   reports:read
~~~

Client không được giả định mình có quyền xuất báo cáo chỉ vì đã yêu cầu. Nếu cần quyền xuất, nó phải xử lý trạng thái thiếu quyền, xin grant hợp lệ hoặc thông báo tính năng chưa được cấp; **không tự lặp việc gọi API với cùng token như thể scope đã đổi**.

## 5. Thiết kế tên scope: đủ rõ nhưng không quá rộng

Scope nên phản ánh **khả năng của API** hoặc phạm vi quyền mà client cần, với ngữ nghĩa được tài liệu hóa.

| Thiết kế | Ví dụ | Nhận xét |
| --- | --- | --- |
| Phân tách đọc/ghi | **documents:read**, **documents:write** | Dễ áp dụng nguyên tắc quyền tối thiểu |
| Phân tách thao tác rủi ro cao | **payments:approve** | Nên có điều kiện role, phê duyệt và step-up bổ sung |
| Phân tách tài nguyên chức năng | **users:read**, **audit:read** | Tránh scope chung quá rộng như **all** |
| Scope đặc quyền rộng | **admin** | Khó kiểm soát phạm vi nếu không gắn API, tenant, chính sách rõ |
| Scope rất chi tiết | **report:42:read** | Có thể gây bùng nổ scope; thường quyền đối tượng nên do policy/entitlement quản lý |
| Scope theo ngữ cảnh dự án | **project:read** | Vẫn phải kiểm tra người dùng được phép xem project nào |

**Không có một quy tắc bắt buộc về dấu hai chấm, dấu chấm hay tiền tố** cho tên scope riêng của API. Tổ chức nên thống nhất naming convention, version, phân quyền người được tạo scope mới, chủ sở hữu API và chính sách migration khi thay đổi ngữ nghĩa.

Một tập scope quá thô dễ gây **overprivilege**; một tập scope chi tiết tới từng đối tượng lại có thể làm token lớn, quản trị rối và khó thu hồi đồng bộ. Thiết kế thường hiệu quả khi dùng **scope giới hạn hành động cấp client**, còn **RBAC/ABAC và entitlement** giới hạn chủ thể, tài nguyên và ngữ cảnh.

## 6. Authorization Code + PKCE: scope được yêu cầu ở đâu?

Với ứng dụng tương tác sử dụng OIDC, **Authorization Code Flow kết hợp PKCE** là lựa chọn thường được khuyến nghị cho nhiều loại client. Phạm vi được yêu cầu tại authorization endpoint, còn authorization server xác minh client, người dùng và chính sách trước khi cấp code/token.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant App as Client / ứng dụng
    participant AS as Authorization Server / IdP
    participant API as Resource Server
    User->>App: Mở chức năng xem báo cáo
    App->>AS: Authorization request với scope, state, PKCE
    AS->>User: Xác thực / consent nếu cần
    AS->>AS: Kiểm tra quyền yêu cầu và chính sách
    AS-->>App: Authorization code qua redirect hợp lệ
    App->>AS: Đổi code kèm code_verifier và client auth nếu cần
    AS-->>App: Token và scope thực sự được cấp
    App->>API: GET báo cáo kèm access token
    API->>API: Xác minh token, audience, scope, tenant và quyền
    API-->>App: Dữ liệu được phép hoặc lỗi truy cập
~~~

Ví dụ minh họa authorization request (host và các giá trị giả, không dùng nguyên văn):

~~~http
GET /authorize?response_type=code&client_id=report-client
  &redirect_uri=https%3A%2F%2Fapp.example.invalid%2Fcallback
  &scope=openid%20profile%20reports%3Aread
  &state=STATE_PLACEHOLDER
  &nonce=NONCE_PLACEHOLDER
  &code_challenge=CHALLENGE_PLACEHOLDER
  &code_challenge_method=S256 HTTP/1.1
Host: login.example.invalid
~~~

Các dòng request được xuống dòng để dễ đọc; khi gửi thật, query phải được mã hóa và truyền đúng chuẩn HTTP. **state**, **nonce** và **code_challenge** cần được tạo/kiểm chứng đúng theo giao thức. Client không được nhúng client secret vào URL.

**PKCE** bảo vệ quá trình đổi authorization code, **không thay thế kiểm tra scope hay authorization tại API**. Scope **openid** khiến yêu cầu trở thành OIDC authentication request; các scope khác tùy registration/chính sách có thể được cấp hoặc từ chối.

## 7. Scope trong OIDC: openid, profile, email và offline_access

Trong **OpenID Connect**, một số scope có ý nghĩa tiêu chuẩn cho yêu cầu xác thực và **claims**:

| Scope OIDC | Ý nghĩa chính | Điều không nên suy diễn |
| --- | --- | --- |
| **openid** | Yêu cầu xử lý theo OIDC, nhận thông tin xác thực/ID token theo luồng hỗ trợ | Không tự cấp quyền vào API doanh nghiệp |
| **profile** | Yêu cầu nhóm claims hồ sơ chuẩn được hỗ trợ | Không đảm bảo mọi claim đều tồn tại hoặc luôn mới |
| **email** | Yêu cầu claims liên quan email | email_verified chỉ có nghĩa theo nguồn và quy tắc verifier; không thay ID ổn định |
| **address** | Yêu cầu claims địa chỉ theo OIDC | Không tự cho phép đọc toàn bộ dữ liệu địa chỉ ngoài phạm vi được cấp |
| **phone** | Yêu cầu claims liên quan số điện thoại | Không chứng minh quyền sở hữu số ở thời điểm hiện tại trong mọi tình huống |
| **offline_access** | Yêu cầu khả năng nhận refresh token để tiếp tục truy cập khi người dùng không hiện diện | Không bảo đảm refresh token luôn được cấp; còn phụ thuộc consent, policy và client |

**openid** là scope đặc biệt của OIDC. Nếu không có **openid**, một authorization request OAuth thông thường **không tự trở thành OIDC login** chỉ vì client muốn đọc tên hoặc email.

Các scope hồ sơ như **profile/email** liên quan việc yêu cầu thông tin người dùng; chúng **không phải role RBAC**, không đồng nghĩa có quyền truy cập báo cáo tài chính hay quản lý nhân sự.

### Có scope không có nghĩa mọi claim xuất hiện trong ID token

Vị trí claim trong **ID token**, **UserInfo response** hoặc nơi khác phụ thuộc quy tắc OIDC, request và nhà cung cấp. Không viết logic “đã yêu cầu profile thì ID token chắc chắn có department, manager và mọi trường nhân sự”. Các trường nội bộ như departmentId hoặc employmentStatus cần hợp đồng claim mapping và nguồn có thẩm quyền rõ ràng.

Nếu dùng **offline_access**, authorization server phải thực hiện các điều kiện chính sách/consent tương ứng; OIDC có quy tắc đặc thù cho việc xin offline access, ví dụ yêu cầu consent rõ trong những trường hợp áp dụng. Client không thể tự giả định rằng thêm chuỗi **offline_access** sẽ được cấp refresh token vô hạn.

## 8. Scope không phải audience: tránh dùng nhầm token giữa các API

**Audience (aud)** xác định token dành cho **resource server nào**. **Scope** giới hạn hành động trong ngữ cảnh được cấp. Cả hai cần được kiểm tra.

Giả sử có:

- API báo cáo: **https://reports.example.invalid**
- API nhân sự: **https://hr.example.invalid**
- Scope chung tên **read**

Một token được cấp cho API báo cáo không thể mặc nhiên dùng ở API nhân sự chỉ vì cùng có chuỗi scope **read**. API nhân sự phải từ chối nếu **audience không đúng**; authorization server cũng cần tránh phát hành token có phạm vi resource rộng ngoài nhu cầu.

| Kiểm tra | Vì sao cần |
| --- | --- |
| **iss** | Token do đúng authorization server đáng tin cậy phát hành |
| **aud / resource binding** | Token thực sự dành cho API hiện tại |
| **exp, nbf, iat khi phù hợp** | Token đang trong khoảng hiệu lực |
| **Signature hoặc introspection** | Xác thực token theo loại token/cơ chế AS |
| **scope** | Token có khả năng API cần hay không |
| **sub / client identity** | Xác định chủ thể hoặc client đang hành động |
| **tenant/resource/role/ABAC** | Chủ thể có quyền truy cập tài nguyên cụ thể hay không |
| **revocation/policy freshness** | Quyền hoặc grant chưa bị thu hồi sau Mover/Leaver |

Với kiến trúc có nhiều resource server, có thể cân nhắc **resource indicators** theo OAuth 2.0 (RFC 8707) nếu authorization server hỗ trợ, để chỉ rõ API đích lúc yêu cầu quyền. Không tự suy rằng một scope tên giống nhau chứng minh token hợp lệ cho mọi audience.

## 9. Scope được thể hiện trong access token như thế nào?

OAuth 2.0 không yêu cầu mọi access token đều là JWT. Có hai mô hình thường gặp:

1. **Opaque access token:** API kiểm tra token qua authorization server hoặc cơ chế trạng thái; phạm vi được cấp có thể được truy vấn bằng **token introspection** khi hỗ trợ.
2. **Self-contained access token**, chẳng hạn JWT: API có thể xác minh chữ ký và đọc claims liên quan theo token profile/hợp đồng của issuer.

Ví dụ JSON **payload minh họa**, không phải token có chữ ký và không đủ dùng để xác thực:

~~~json
{
  "iss": "https://login.example.invalid",
  "sub": "iam-user-482",
  "aud": "https://reports.example.invalid",
  "client_id": "report-client",
  "scope": "reports:read reports:export",
  "exp": 1796086800,
  "iat": 1796083200
}
~~~

Trong hệ sinh thái thực tế, có nền tảng dùng claim **scope** dạng chuỗi, có nền tảng dùng tên khác như **scp** hoặc biểu diễn dưới dạng array theo profile riêng. Không tự coi mọi token có claim scope giống nhau; API phải tuân theo **hợp đồng token profile của issuer** và xác minh đầy đủ trước khi đọc claim.

**Đọc được một chuỗi JSON không có nghĩa token đáng tin**. Không dùng decode JWT ở client làm bằng chứng phân quyền; resource server phải kiểm tra chữ ký hoặc introspection, issuer, audience và điều kiện khác theo thiết kế.

## 10. Resource server phải kiểm tra scope như thế nào?

API là nơi thực thi quyết định cuối cùng cho từng request. Một quy tắc tối thiểu:

~~~text
authorize(request):
    token = extractBearerOrBoundAccessToken(request)
    validation = validateToken(
        token,
        trustedIssuer,
        expectedAudience,
        validityAndRevocationPolicy
    )
    if not validation.valid:
        return UNAUTHORIZED

    requiredScope = scopeContractFor(request.route, request.method)
    if not validation.grantedScopes.contains(requiredScope):
        return FORBIDDEN_INSUFFICIENT_SCOPE

    identity = resolveSubjectOrWorkload(validation)
    resource = resolveTargetResource(request)
    if not policy.allows(
        identity,
        resource,
        request.action,
        currentRoleAndAttributes(identity),
        request.tenantContext
    ):
        return FORBIDDEN

    return ALLOW
~~~

Mã giả chỉ biểu diễn trách nhiệm, không phải một thư viện OAuth cụ thể. Nếu endpoint yêu cầu **nhiều scope** hoặc **một trong các scope**, quy tắc AND/OR phải được tài liệu hóa rõ. Không dùng phép so sánh substring như “read nằm trong reports:read-all” để kết luận đã có scope; cần phân tích thành **các giá trị scope riêng biệt**.

### Lỗi thiếu scope

Khi token hợp lệ nhưng thiếu scope, resource server có thể phản hồi **403 Forbidden** cùng thông tin **insufficient_scope** theo cơ chế Bearer token (RFC 6750), nếu phù hợp với chính sách tránh lộ thông tin:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="reports", error="insufficient_scope", scope="reports:read"
~~~

**401 Unauthorized** thường phù hợp khi thiếu/không hợp lệ thông tin xác thực, còn **403 Forbidden** phù hợp khi đã xác thực nhưng không đủ quyền. Thực tế cần tuân theo profile API và cân nhắc không tiết lộ quá nhiều về tài nguyên nhạy cảm.

## 11. Scope, consent, admin approval và quyền được cấp

Một client có thể yêu cầu scope tại authorization endpoint, nhưng việc cấp còn phụ thuộc:

- Client đã được **đăng ký** để dùng scope đó chưa?
- Authorization server có cho phép loại client/grant này xin scope đó không?
- Người dùng đã được xác thực theo mức phù hợp chưa?
- Chủ thể có quan hệ lao động và **entitlement** đáp ứng điều kiện không?
- Có cần **user consent**, **administrator consent**, chủ tài nguyên duyệt hay phê duyệt tổ chức không?
- Consent/grant trước đây có còn hiệu lực, có cần xin lại khi scope thay đổi không?
- Scope có điều kiện thời gian, môi trường, tenant hoặc ràng buộc pháp lý nào không?

Không phải mọi quy trình OAuth đều có màn hình “Allow/Deny” cho người dùng. Với ứng dụng nội bộ, doanh nghiệp có thể cấu hình **admin approval** hoặc chính sách cấp quyền tập trung. Với **client credentials**, không có người dùng tương tác ở thời điểm cấp token; authorization server cấp quyền cho client/workload theo chính sách.

**Consent không phải authorization cuối cùng trên dữ liệu.** Người dùng có thể đồng ý cho ứng dụng yêu cầu **reports:read**, nhưng nếu tài khoản của họ chỉ được phép xem Dự án Atlas thì API vẫn phải chặn truy vấn báo cáo thuộc Dự án Nova.

## 12. Least privilege và scope creep

**Least privilege** là cấp phạm vi tối thiểu đủ cho chức năng đã phê duyệt. **Scope creep** xuất hiện khi ứng dụng tích lũy hoặc giữ nhiều scope hơn nhu cầu hiện tại.

| Dấu hiệu | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Client xin scope **admin** để đọc dữ liệu | Truy cập quá rộng khi token bị lộ | Thay bằng scope đọc riêng, tách ứng dụng |
| Một token dùng cho nhiều API không liên quan | Tăng phạm vi ảnh hưởng | Ràng buộc audience/resource và tách grant |
| Scope cũ vẫn còn sau khi ứng dụng đổi tính năng | Quyền không còn nhu cầu | Rà soát grant, giảm scope và revoke |
| Refresh token sống lâu với scope rộng | Token mới có thể được cấp lâu dài | Chính sách hạn, rotation/revocation và review |
| Cấp scope theo nhóm người dùng mà không xét role mới | Mover vẫn có quyền cũ | Tính lại entitlement và quyền hiệu lực |
| Scope giống nhau giữa tenant | Rủi ro dữ liệu xuyên tenant | Kiểm tra tenant tại resource server |

Một ứng dụng chỉ cần đọc báo cáo trong 10 phút không nhất thiết nên giữ **offline_access** và refresh token dài hạn. Nếu sản phẩm cần xử lý nền, nên đánh giá đúng grant, phạm vi và danh tính workload thay vì tự xin refresh token rộng để tránh tương tác của người dùng.

## 13. Scope và RBAC: quyền theo vai trò không tự nằm trong scope

**RBAC (Role-Based Access Control)** quyết định entitlement theo role và phạm vi tổ chức. Scope giới hạn những gì client/token được phép **yêu cầu** từ API.

Ví dụ:

| Chủ thể | Role | Scope trên token | Resource | Kết quả |
| --- | --- | --- | --- | --- |
| Lan | Analyst tại organization A | reports:read | Report A-01 | Có thể cho phép nếu đủ điều kiện khác |
| Lan | Analyst tại organization A | reports:read | Report B-09 | Từ chối nếu không thuộc phạm vi Lan được duyệt |
| Lan | Analyst tại organization A | reports:write | Report A-01 | Không tự được phép sửa nếu role không có quyền viết |
| Minh | FinanceAdmin tại organization A | reports:read | Report A-01 | Chỉ đọc theo scope; role admin không tự mở quyền ngoài scope token |

Một quyết định truy cập có thể mô tả là:

~~~text
ALLOW = token_valid
    AND audience_matches
    AND required_scope_granted
    AND subject_has_required_role_or_entitlement
    AND resource_is_in_authorized_tenant
    AND ABAC_conditions_satisfied
    AND no_higher_priority_deny
~~~

Không nên **mã hóa mọi role thành scope** rồi mặc định client nào có scope cũng sở hữu role đó. Role của con người, scope của client và entitlement tại tài nguyên cần được quản trị với nguồn có thẩm quyền riêng và kiểm chứng giao nhau tại API.

## 14. Scope và ABAC: điều kiện thay đổi theo thời gian

**ABAC (Attribute-Based Access Control)** xét thuộc tính của chủ thể, tài nguyên, hành động và ngữ cảnh. Các thuộc tính quan trọng trong IAM có thể gồm:

- Employment status và loại quan hệ lao động từ **HRIS** hoặc nguồn bảo trợ.
- Department, job code, project assignment và organization theo nguồn có thẩm quyền.
- Nhãn dữ liệu, độ nhạy tài nguyên, chủ sở hữu, tenant và mục đích xử lý.
- Mốc hiệu lực, trạng thái phê duyệt, điều kiện thiết bị hoặc độ mới của phiên.

**Scope không thay thế ABAC.** Token mang **documents:read** không tự chứng minh người dùng còn ở Dự án Atlas hôm nay chỉ vì họ được cấp token hôm qua. Khi HR cập nhật Mover hoặc Leaver, resource server phải có chiến lược đánh giá lại trạng thái quyền hoặc thu hồi token phù hợp.

Đặc biệt, nếu access token là **JWT tự chứa và được xác minh offline**, các claim như department hoặc role có thể **cũ cho tới khi token hết hạn**. Nếu yêu cầu thu hồi nhanh, cần dùng introspection, denylist, security epoch, policy recheck hoặc TTL đã được đánh giá rủi ro; không coi việc IdP cập nhật claim là bằng chứng mọi API đã đổi quyền.

## 15. Scope và organization/tenant isolation

Trong ứng dụng đa tenant, một token có scope **invoices:read** chưa đủ để quyết định được đọc hóa đơn thuộc tenant nào.

Ví dụ request:

~~~http
GET /organizations/org-b/invoices/42 HTTP/1.1
Host: billing.example.invalid
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
~~~

API cần thực hiện **tất cả** kiểm tra phù hợp:

1. Token có hợp lệ và dành đúng API billing không?
2. Scope được cấp có cho phép đọc hóa đơn không?
3. Identity hoặc workload có membership/entitlement **đang hiệu lực** tại **org-b** không?
4. Hóa đơn 42 có thực sự thuộc org-b và được phép truy cập không?
5. Có điều kiện ABAC/approval hoặc chính sách dữ liệu nào giới hạn hành động không?
6. Token hoặc phiên có bị thu hồi, thay đổi quyền hoặc hết hạn không?

**org-b lấy từ URL là dữ liệu do client yêu cầu**, không phải bằng chứng client có quyền với org-b. Cần đối chiếu với định danh đã xác minh và dữ liệu tài nguyên ở backend. Một client đang hoạt động tại tenant A không được đổi URL sang tenant B rồi tự nhận quyền chỉ vì có scope **invoices:read**.

## 16. Scope cho user-delegated access và client credentials khác nhau thế nào?

### 16.1. Quyền ủy quyền có người dùng

Với Authorization Code Flow, client nhận access token sau khi người dùng xác thực và quyền được chấp thuận theo chính sách. Token hoặc bản ghi grant thường liên quan tới **chủ thể người dùng** và **client**. Resource server cần kiểm tra cả **scope của client/token** và **quyền hiệu lực của người dùng**.

Ví dụ: ứng dụng điện thoại được cấp scope **tasks:read**, nhưng người dùng chỉ được phép xem task của dự án đang tham gia. Nếu người dùng rời dự án, API phải ngăn truy cập những task đó dù token còn mang scope.

### 16.2. Client credentials cho workload

Trong luồng **client credentials**, ứng dụng máy xác thực dưới danh tính **client/workload**, không thay mặt một nhân viên đang đăng nhập. Authorization server có thể cấp scope phù hợp với client đã được đăng ký; resource server phải kiểm tra quyền của **workload identity**, môi trường, audience và tài nguyên.

| Thuộc tính | User-delegated access | Client credentials |
| --- | --- | --- |
| Chủ thể trung tâm | Người dùng và client được ủy quyền | Client/workload |
| Yếu tố xác thực | Người dùng có thể dùng IdP/SSO/MFA | Credential máy: secret, khóa riêng, mTLS, federation… |
| Căn cứ cấp scope | Grant, consent/chính sách, entitlement người dùng | Client registration, policy và quyền workload |
| Vòng đời | JML và trạng thái consent/grant | Vòng đời ứng dụng, owner, môi trường và secret |
| Điểm cần thu hồi | Account, refresh token, session, grant và entitlement | Client/grant, credential máy, token và quyền workload |

Không dùng MFA push của nhân viên làm yêu cầu bắt buộc cho mỗi API call của bot. Tài khoản dịch vụ cần **owner rõ, scope tối thiểu, credential được bảo vệ, vòng đời độc lập** và chính sách thu hồi khi ứng dụng hoặc nhiệm vụ kết thúc.

## 17. Scope trong Joiner lifecycle

Khi **Joiner**, IAM tiếp nhận identity từ HRIS/nguồn bảo trợ, xác minh chủ thể và chuẩn bị account. Scope cần được xét ở **cả phía client và phía người dùng**:

1. **Xác minh nguồn:** HR hoặc sponsor xác nhận người/nhà thầu, organization, ngày bắt đầu và nhiệm vụ.
2. **Liên kết identity:** dùng personId, workerId, employmentId và identityId phù hợp, không gộp theo email đơn thuần.
3. **Xác định ứng dụng cần dùng:** những OAuth client nào thực sự cần truy cập API để phục vụ công việc?
4. **Cấp theo quyền tối thiểu:** chỉ cho client xin các scope đã được đăng ký; chỉ cho người dùng hành động trên tài nguyên có entitlement.
5. **Áp dụng xác thực và phê duyệt:** IdP/SSO/MFA hoặc admin approval nếu tài nguyên có yêu cầu.
6. **Provisioning:** đồng bộ user/group qua SCIM/API nếu ứng dụng hỗ trợ; phân biệt provisioning với scope grant.
7. **Kiểm chứng:** đọc lại account, group, grant và kết quả quyền hiệu lực tại API.
8. **Theo dõi mốc hiệu lực:** nếu tạo account trước ngày vào làm, tránh dùng account/grant quá sớm hoặc vượt thời hạn.

**Ví dụ:** nhân viên mới được cấp quyền đọc báo cáo Dự án Atlas. Client báo cáo có scope **reports:read**, nhân viên có role Analyst trong Atlas, API chỉ cho truy cập báo cáo Atlas sau khi hai lớp điều kiện cùng đạt.

Một hệ thống ghi “SSO thành công” hoặc “SCIM tạo account thành công” **chưa đủ** để chứng minh scope hoặc quyền hiệu lực đã được cấu hình đúng.

## 18. Scope trong Mover lifecycle: tránh quyền tích lũy

**Mover** xảy ra khi người dùng đổi vai trò, phòng ban, dự án hoặc organization. Quyền trước đó có thể trở nên không phù hợp, trong khi token và consent/grant cũ vẫn còn hiệu lực.

Ví dụ, Lan chuyển từ nhóm phân tích Dự án Atlas sang nhóm vận hành Nova. IAM cần:

- Xác minh thay đổi từ nguồn có thẩm quyền và mốc bắt đầu hiệu lực.
- Rà soát role/entitlement cũ và mới theo RBAC/ABAC.
- Thu hồi **quyền Atlas**, không chỉ thêm Nova.
- Đánh giá grant OAuth và scope mà client đang có; những scope đặc quyền hoặc grant không còn nhu cầu phải bị giảm/thu hồi theo khả năng.
- Xử lý **refresh token** có thể tiếp tục cấp token với quyền cũ, và access token/JWT còn hạn có claim cũ.
- Đối soát API, nhóm, ACL trực tiếp và các phiên ứng dụng.

Nếu scope **reports:read** vẫn phù hợp cho Nova, không nhất thiết phải xóa scope đó khỏi client; API cần tính lại **dự án được phép**. Ngược lại, nếu Lan không còn chức năng xuất dữ liệu, scope **reports:export** hoặc grant liên quan không được để tồn tại nếu không còn căn cứ.

**Không đồng nhất “scope trong token” với “quyền tổ chức tại thời điểm hiện tại”.** Nếu người dùng còn một employment hợp lệ khác, không tự vô hiệu toàn bộ danh tính khi chỉ kết thúc quan hệ của một dự án hoặc pháp nhân.

## 19. Scope trong Leaver lifecycle: revocation và residual access

Khi HRIS hoặc nguồn bảo trợ xác nhận **Leaver**, tổ chức cần chặn mọi đường truy cập xuất phát từ quan hệ làm việc đã kết thúc.

| Đối tượng | Hành động cần xem xét | Bằng chứng cần đọc lại |
| --- | --- | --- |
| IdP account | Khóa đăng nhập theo thời điểm hiệu lực | Trạng thái và khả năng xác thực mới |
| OAuth grant/consent | Thu hồi ủy quyền không còn hợp lệ | Grant không còn cấp được quyền mới |
| Refresh token | Revoke theo client/identity/grant | Không còn dùng để xin access token mới |
| Access token | Chặn ở resource server trước hạn nếu chính sách yêu cầu | API từ chối token/quyền đã thu hồi |
| SSO/application session | Kết thúc phiên tại IdP/RP/SP | Phiên không còn được chấp nhận |
| Group/role/entitlement | Thu hồi theo RBAC/ABAC và nguồn HR | Quyền hiệu lực tại ứng dụng |
| PAT/API key cục bộ | Thu hồi bằng cơ chế sản phẩm | Credential không còn được sử dụng |
| Workload do Leaver sở hữu | Chuyển owner và đánh giá secret/scope | Không còn credential cá nhân tồn dư |

**RFC 7009** mô tả cơ chế yêu cầu authorization server thu hồi token; phạm vi xử lý grant/access/refresh token tùy hệ thống. **RFC 7662** mô tả token introspection, có thể hỗ trợ resource server hỏi trạng thái token. Với JWT offline, cần cơ chế chặn riêng hoặc giới hạn TTL được chấp nhận. **Revoke refresh token không bảo đảm mọi access token cũ lập tức vô hiệu**.

**SCIM deactivation** cập nhật account/user/group nếu ứng dụng hỗ trợ, **không tự chứng minh token hoặc phiên ứng dụng đã bị thu hồi**. Đóng Leaver phải dựa trên bằng chứng tại những hệ thống đích bắt buộc, không chỉ trạng thái hồ sơ HR.

## 20. Các rủi ro bảo mật thường gặp với scope

| Rủi ro | Tình huống | Kiểm soát |
| --- | --- | --- |
| **Scope quá rộng** | Client chỉ đọc dữ liệu nhưng được admin | Thiết kế scope nhỏ, phê duyệt và rà soát định kỳ |
| **Client xin quyền vượt nhu cầu** | Client thêm scope nhạy cảm khi nâng cấp | Registration/consent/admin approval, diff và alert |
| **Scope escalation qua cấu hình sai** | Authorization server cấp scope không nằm trong policy client | Enforce allowed scopes tại authorization server |
| **Audience confusion** | Token của API A được dùng ở API B | Kiểm tra aud, issuer, resource binding |
| **Tenant isolation bypass** | Scope read nhưng truy cập dữ liệu tenant khác | RBAC/ABAC, tenant check tại backend |
| **Client trust nhầm** | Ứng dụng dùng claim từ token không xác minh | Signature/introspection, iss/aud/exp, PKCE và client binding |
| **Overprivileged refresh token** | Client tiếp tục xin token có scope rộng | Token/grant lifecycle, rotation/revocation, review |
| **Token replay** | Bearer token bị sao chép sử dụng lại | TLS, bảo vệ lưu trữ, token TTL, sender-constrained tokens khi hỗ trợ |
| **Stale scopes/roles sau Mover** | JWT còn quyền cũ | Re-evaluate policy, revoke, epoch hoặc kiểm tra trạng thái |
| **Quyền tồn dư sau Leaver** | IdP disabled nhưng PAT/SaaS vẫn active | Đối soát tất cả target và credential |
| **Lộ dữ liệu qua claims quá rộng** | Client được cấp profile không cần thiết | Data minimization, chính sách OIDC claims và audit |

OAuth 2.0 là **khung ủy quyền**, không tự thay thế mô hình xác thực an toàn hoặc kiểm soát đặc quyền. Trong OIDC, cần kiểm tra luồng đăng nhập và binding kết quả xác thực; ở API cần kiểm tra **scope và authorization thực tế**.

## 21. Xử lý lỗi và kiểm chứng phạm vi

Các lỗi thường gặp:

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Authorization request bị **invalid_scope** | Scope không tồn tại, không được client/AS cho phép hoặc cú pháp sai | Kiểm tra registration và cấu hình authorization server |
| Token được cấp ít scope hơn yêu cầu | Authorization server áp chính sách thu hẹp | Đọc phạm vi granted, điều chỉnh tính năng/consent đúng quy trình |
| API báo **insufficient_scope** | Token hợp lệ nhưng thiếu quyền API yêu cầu | Xin scope phù hợp theo phê duyệt; không tự nâng quyền |
| API báo **invalid_token** | Token hết hạn, sai audience/issuer hoặc bị thu hồi tùy cơ chế | Kiểm tra phát hành, thời hạn, validation, không lộ token |
| Có scope nhưng vẫn 403 | Role/entitlement/tenant/ABAC không đạt | Kiểm tra authorization đích, không coi scope là toàn quyền |
| Scope đúng nhưng truy cập nhầm tenant | API thiếu kiểm tra resource ownership | Sửa kiểm soát backend/tenant, rà soát quyền đã truy cập |
| Mover đã xóa nhóm nhưng token cũ còn dùng được | Token tự chứa hoặc cache chính sách chưa cập nhật | Thiết kế revocation/policy freshness |
| Leaver vẫn gọi được PAT | PAT ngoài IdP/OAuth grant trung tâm | Thu hồi tại SaaS/DevOps và xác minh |

**Không log nguyên access token, refresh token, ID token, authorization code, client secret hay session cookie** để debug scope. Dùng ID giao dịch, mã token đã được bảo vệ, claim/metadata đã lọc và trạng thái xác minh.

## 22. Kiểm toán và quan sát scope trong vận hành

Một quyết định truy cập nên truy ngược được từ **nguồn nhân sự → identity → client registration/grant → token → API → tài nguyên**.

Ví dụ bản ghi kiểm toán minh họa, không phải schema chuẩn:

~~~json
{
  "eventId": "oauth-access-2026-091",
  "identityRef": "iam-user-482",
  "clientId": "report-client",
  "authorizationServer": "https://login.example.invalid",
  "resourceServer": "https://reports.example.invalid",
  "requestedScopes": ["reports:read", "reports:export"],
  "grantedScopes": ["reports:read"],
  "requestedAction": "READ",
  "resourceRef": "org-a/report-42",
  "roleCheck": "PASSED",
  "tenantCheck": "PASSED",
  "scopeCheck": "PASSED",
  "authorizationDecision": "ALLOW",
  "occurredAt": "2026-11-23T09:30:00+07:00"
}
~~~

Không phải mọi truy cập đều cần ghi lại toàn bộ nội dung token hoặc dữ liệu người dùng. Có thể ghi **tham chiếu identity, client, API, tập scope cần thiết và đã cấp, policy version, loại quyết định, mốc thời gian, correlation ID** đủ cho điều tra. Log cần phân quyền truy cập và giới hạn lưu giữ theo chính sách.

Các chỉ số hữu ích:

- **Overprivileged clients:** số client có scope rộng hơn nhu cầu đã được đánh giá.
- **Unused/stale grants:** grant không còn được dùng hoặc có owner/phê duyệt hết hiệu lực.
- **Scope request denial rate:** tỷ lệ yêu cầu scope bị từ chối do chính sách/cấu hình.
- **Insufficient-scope responses:** tín hiệu client cấu hình sai hoặc được cấp ít hơn nhu cầu.
- **Scope drift after Mover:** quyền client/token hoặc entitlement không còn phù hợp vai trò mới.
- **Residual access after Leaver:** quyền/API còn chấp nhận sau mốc cần thu hồi.
- **Unverified target access:** API/ứng dụng chưa có bằng chứng kiểm tra quyền hiệu lực.

Một tỷ lệ lỗi thấp không tự chứng minh an toàn: API không kiểm tra scope sẽ không tạo lỗi **insufficient_scope** ngay cả khi đang có lỗ hổng. Cần kết hợp **kiểm thử cho phép/từ chối, rà soát cấu hình và audit hành vi**.

## 23. Tình huống thực hành: đọc báo cáo qua một ứng dụng bên thứ ba

**Bối cảnh:** Doanh nghiệp triển khai ứng dụng tổng hợp báo cáo cho nhân viên. IdP hỗ trợ OIDC/OAuth; ứng dụng có client ID **report-client**, xin **openid profile reports:read reports:export**. Nhân viên An thuộc organization A, role Analyst, chỉ được đọc báo cáo trong Dự án Atlas. Tính năng export chưa được chủ dữ liệu phê duyệt.

### Bước 1: Phạm vi được cấp

Authorization server kiểm tra client registration, policy và phê duyệt, sau đó chỉ cấp:

~~~text
openid profile reports:read
~~~

Đây là ví dụ minh họa; trong triển khai thực cần phân biệt scopes gắn với OIDC identity request và những scope thực sự xuất hiện/được cấp cho access token API. Client không nên giả định nhận **reports:export** chỉ vì đã yêu cầu nó.

### Bước 2: Gọi API báo cáo

Ứng dụng gửi access token hợp lệ tới Reports API. API kiểm tra **issuer/audience/thời hạn/scope**, sau đó kiểm tra An còn là Analyst trong organization A và report thuộc Dự án Atlas. Nếu thỏa mọi điều kiện, request đọc báo cáo được cho phép.

### Bước 3: Cố mở báo cáo Dự án Nova

Scope **reports:read** vẫn có trong token, nhưng An không có entitlement dự án Nova. API phải **từ chối**, không cho phép chỉ vì cùng API hoặc client đã có consent.

### Bước 4: Chức năng export

Client chưa được cấp **reports:export**. API export phải từ chối vì thiếu scope. Kể cả khi sau đó được cấp scope, vẫn cần kiểm tra An có quyền export tài nguyên cụ thể và đáp ứng approval/step-up nếu chính sách yêu cầu.

### Bước 5: An chuyển công tác và sau đó nghỉ việc

Khi An **Mover** sang Dự án Nova, IAM tính lại entitlement, cập nhật nhóm và quyền, kiểm tra token/grant cũ. Scope **reports:read** có thể vẫn tồn tại nếu còn nhu cầu, nhưng API phải áp dụng ranh giới dự án mới.

Khi An **Leaver**, IAM chặn đăng nhập, thu hồi grant/refresh token liên quan và xử lý session/access token tại hệ thống đích. SCIM giúp deprovision account nhưng không thay thế xác minh API không còn chấp nhận quyền cũ.

### Câu hỏi tự kiểm tra

**Câu 1:** Có scope **reports:read** thì có được đọc báo cáo mọi organization?

**Trả lời:** Không. API phải kiểm tra audience, role/entitlement, tenant, tài nguyên và điều kiện ABAC.

**Câu 2:** Scope **openid** có tự cho quyền gọi Reports API?

**Trả lời:** Không. Nó là phạm vi đặc biệt để yêu cầu xử lý OIDC; API cần scope riêng và quyền truy cập thực tế.

**Câu 3:** Client yêu cầu bốn scope và chỉ được cấp ba, client có thể dùng cả bốn không?

**Trả lời:** Không. Phải dùng tập scope **được cấp** và xử lý tính năng còn thiếu theo chính sách.

**Câu 4:** Người dùng đồng ý scope **reports:export** thì có thể xuất mọi dữ liệu?

**Trả lời:** Không. Consent không nâng entitlement của người dùng hoặc bypass policy của tài nguyên.

**Câu 5:** Xóa role IdP sau Mover có khiến mọi JWT cũ mất scope ngay không?

**Trả lời:** Không mặc nhiên. Cần hiểu cách API kiểm tra token và chính sách thu hồi/quyền hiệu lực.

## 24. Checklist thiết kế scope trong IAM

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Mỗi scope có mô tả ngữ nghĩa, resource owner và mục đích? | Scope catalog và API contract |
| Scope có tuân theo least privilege không? | Tách read/write/admin, tránh quyền rộng không cần thiết |
| Client có được xin scope đó không? | Client registration, allowed grants, chính sách AS |
| Scope được cấp có khớp với yêu cầu/approval? | Requested vs granted, consent/admin approval khi cần |
| Có phân biệt scope với audience? | Resource server kiểm tra đúng aud/issuer và phạm vi API |
| Có phân biệt scope với role/entitlement? | RBAC/ABAC tại backend/resource server |
| Có cô lập tenant/organization không? | Membership, ownership và policy theo tài nguyên |
| OIDC scopes có bị dùng sai thành role không? | openid/profile/email là scope identity, không phải business entitlement |
| offline_access có hợp lệ và cần thiết không? | Chính sách grant, consent, refresh token lifecycle |
| Có kiểm tra scope thực tế trong token hợp lệ? | JWT profile hoặc introspection được cấu hình đúng |
| Có chống scope escalation và grant drift? | Allowed scopes, review khi đổi client/version/role |
| Joiner có cấp đúng quyền ban đầu? | Identity proofing, client policy, access readback |
| Mover có thu hồi quyền/claim/grant cũ? | Recompute effective access, revoke/recheck |
| Leaver có chặn token và phiên? | IdP, grant, refresh/access token, session và API verify |
| Workload có scope và owner riêng? | Client credentials/federation, TTL, quyền tối thiểu |
| Có audit và đối soát residual access? | Source event, token metadata, API decision, exception owner |

## 25. Tổng kết

**Scope** là công cụ cốt lõi của **OAuth 2.0** để mô tả **phạm vi quyền mà client yêu cầu và được cấp**. Trong **OpenID Connect**, các scope như **openid, profile, email, offline_access** có ý nghĩa riêng đối với nhận dạng, claims và khả năng truy cập ngoại tuyến. Không nên nhầm **scope với role, entitlement, claim, audience hay consent**, và cũng không được coi scope là quyết định truy cập cuối cùng đối với mọi tài nguyên.

Trong vòng đời **Joiner–Mover–Leaver**, **HRIS/nguồn bảo trợ** cung cấp trạng thái công việc; **IAM/IGA** quản trị identity và quyền; **IdP/Authorization Server** kiểm tra chính sách và cấp token; **SSO/OIDC** hỗ trợ đăng nhập; **SCIM** hỗ trợ user/group provisioning; **RBAC/ABAC và resource server** kiểm tra quyền theo tài nguyên. **Client/workload identities** cần scope và grant riêng với owner, hạn và thu hồi rõ ràng. Chỉ khi xác minh cả **scope đã cấp, audience, chính sách tài nguyên và trạng thái token/phiên tại hệ thống đích**, tổ chức mới có thể áp dụng quyền tối thiểu và giảm **quyền truy cập tồn dư** một cách đáng tin cậy.
