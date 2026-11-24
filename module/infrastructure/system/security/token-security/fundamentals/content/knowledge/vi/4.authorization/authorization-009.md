# Quyền được delegated từ user sang client

Trong OAuth 2.0, **delegated authorization (ủy quyền truy cập theo phạm vi)** cho phép một ứng dụng (**client**) được phép truy cập tài nguyên được bảo vệ của người dùng thông qua **access token**, trong giới hạn mà Authorization Server (AS), người có thẩm quyền và Resource Server (API) chấp nhận. Client không cần thu thập và lưu mật khẩu của người dùng để gọi API bên thứ ba.

Đây là nội dung cốt lõi của phần **Authorization** trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**: nắm đúng mô hình tin cậy và vòng đời token, phân biệt JWT/opaque, access/refresh token, hiểu cách **scope**, **audience**, **claims**, lưu trữ, thu hồi và chống token bị đánh cắp hoặc phát lại ảnh hưởng tới quyền mà client có thể thực sự sử dụng.

Một câu hỏi xuyên suốt bài học là: **“Ứng dụng A được phép làm gì với tài nguyên của người dùng B, tại API C, vào thời điểm này?”** Có access token không đồng nghĩa được truy cập mọi dữ liệu; người dùng đồng ý không đồng nghĩa có quyền vượt chính sách của hệ thống.

## 1. Delegation là gì và vì sao cần?

Giả sử ứng dụng bên thứ ba **ReportReader** cần đọc một số tệp trên dịch vụ **FileBox** để tạo báo cáo. Cách làm cũ, nguy hiểm, là yêu cầu người dùng nhập mật khẩu FileBox trực tiếp vào ReportReader. Khi đó ứng dụng có thể có khả năng sử dụng nhiều quyền hơn cần thiết, mật khẩu khó giới hạn theo API, và việc thu hồi thường phức tạp.

Với OAuth 2.0, ReportReader chuyển người dùng đến **Authorization Server** của FileBox. Sau khi kiểm tra danh tính và quyền, AS có thể hỏi người dùng có cho ReportReader **đọc tệp** hay không. Nếu yêu cầu được cho phép, ReportReader nhận access token dùng cho FileBox API với phạm vi thích hợp. ReportReader không cần biết mật khẩu FileBox.

**Một quyền delegated có ba đặc trưng:**

1. **Có bên được ủy quyền:** client nhận quyền truy cập trong một grant cụ thể.
2. **Có giới hạn:** loại thao tác, tài nguyên, người dùng/tenant, audience và thời hạn đều bị ràng buộc bởi chính sách.
3. **Có thể kết thúc hoặc thay đổi:** token hết hạn, grant bị thu hồi, client bị chặn, người dùng mất quyền hoặc chính sách thay đổi.

Đừng hiểu delegation là “chuyển toàn bộ quyền của user” hay “client trở thành user”. OAuth 2.0 cấp cho client **khả năng truy cập được giới hạn**; việc định danh người dùng, quyết định quyền và thực thi chính sách vẫn được phân chia giữa các hệ thống tin cậy.

## 2. Các vai trò trong luồng delegated authorization

| Thành phần | Trách nhiệm | Không nên mặc định |
|---|---|---|
| **Resource owner / người có thẩm quyền** | Có quyền cho phép hoặc chịu sự kiểm soát của chính sách cấp quyền truy cập tài nguyên | Bất kỳ người đăng nhập nào cũng có quyền ủy quyền mọi dữ liệu |
| **End user** | Có thể là resource owner hoặc người sử dụng tài nguyên do tổ chức quản lý | End user luôn có quyền tự cấp scope vượt quyền của tổ chức |
| **Client** | Ứng dụng muốn sử dụng API được bảo vệ, ví dụ ReportReader | Client được phép toàn bộ quyền của user hoặc có thể tin mình là user |
| **Authorization Server (AS)** | Xác thực khi cần, quản lý grant, quyết định phát hành và thu hồi token | Consent UI là điều kiện đủ để bỏ qua policy |
| **Resource Server (RS)** | API giữ dữ liệu, xác minh token và thực thi quyền với từng tài nguyên | JWT có chữ ký hợp lệ thì thao tác nào cũng được |
| **Browser / user agent** | Điều hướng qua authorization endpoint và callback | Browser tự là nơi tin cậy để giữ mọi bí mật |

Trong một doanh nghiệp, quyền được cấp có thể do **admin consent**, cấu hình quản trị hoặc chính sách tổ chức quyết định. Một người dùng thấy màn hình yêu cầu truy cập không mặc nhiên có thể cấp quyền cho dữ liệu ngoài thẩm quyền của họ.

### Ranh giới tin cậy

~~~mermaid
flowchart LR
    U["Người dùng / người có thẩm quyền"]
    C["Client: ReportReader"]
    AS["Authorization Server"]
    API["Resource Server: FileBox API"]
    DB[("Tệp và ACL/tenant policy")]

    U -->|"Đăng nhập / cho phép khi cần"| AS
    C -->|"Yêu cầu authorization grant"| AS
    AS -->|"Code rồi token có giới hạn"| C
    C -->|"Access token cho API này"| API
    API -->|"Kiểm tra quyền từng đối tượng"| DB
    API -->|"Kết quả được phép"| C
~~~

Người dùng không giao mật khẩu cho client; token cấp cho client phải dành cho API cụ thể. API tiếp tục kiểm tra quyền tài nguyên của chủ thể, chứ không coi grant như lệnh mở khóa toàn bộ kho dữ liệu.

## 3. OAuth delegation khác authentication và impersonation

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Authentication** | Ai vừa chứng minh danh tính với ai? | Lan đăng nhập tại AS của FileBox |
| **Delegated authorization** | Client được phép làm thao tác nào trên tài nguyên nào? | ReportReader được đọc một số tệp của Lan |
| **Authorization enforcement** | Request hiện tại có đủ quyền hay không? | FileBox API chỉ trả tệp Lan được xem |
| **Impersonation** | Một thành phần hành động dưới danh nghĩa chủ thể khác theo cơ chế cho phép | Một hệ thống nội bộ có quyền “đăng nhập thay” đã được kiểm soát riêng |

OAuth 2.0 là **authorization framework**. Một OAuth access token đơn thuần không nhất thiết là bằng chứng người dùng vừa đăng nhập hoặc cung cấp đầy đủ danh tính user cho client. Khi client cần đăng nhập người dùng và nhận thông tin xác thực chuẩn hóa, **OpenID Connect (OIDC)** bổ sung **ID token** và các quy tắc xác minh riêng.

Cũng cần phân biệt hai tình huống:

- **User-delegated access:** ứng dụng truy cập theo một authorization grant gắn với user, theo những ràng buộc đã được cấp. Access token có thể chứa `sub` là user theo profile.
- **Client credentials:** service tự dùng danh tính và quyền của **chính client** để xin token; không có user đang ủy quyền trong lần cấp token đó. Không được suy diễn có user chỉ từ việc token có chữ ký hợp lệ.

## 4. Quyền thực tế là giao của nhiều điều kiện

Nhiều hệ thống sai ở chỗ chỉ kiểm tra `scope` hoặc chỉ đọc `sub`. Một quyết định an toàn cần cân nhắc đồng thời:

- **Quyền nền của user / chủ sở hữu:** người dùng có quyền xem tệp này không?
- **Quyền client được đăng ký:** client có được xin và dùng grant/scope này không?
- **Quyền được ủy quyền trong grant:** resource owner/admin đã cho phép loại hành động nào?
- **Ràng buộc của token:** issuer, audience, scope, loại token, thời hạn, trạng thái thu hồi và sender constraint nếu có.
- **Chính sách Resource Server:** tenant boundary, ACL, quan hệ sở hữu, phân loại dữ liệu và kiểm soát theo ngữ cảnh.

Một mô hình suy nghĩ đơn giản (không phải công thức đầy đủ của mọi authorization engine):

~~~text
Allowed(request) =
    valid_access_token_for_this_API
    AND requested_operation_in_granted_scope
    AND client_allowed_by_policy
    AND user_or_subject_allowed_on_target_resource
    AND organization_and_context_policy_pass
~~~

Ví dụ, ReportReader có scope `files:read` nhưng user chỉ đọc được tệp `file-17`. Khi client gọi `GET /files/file-99` thuộc tenant khác, API phải từ chối dù scope có vẻ đủ. **Scope thường giới hạn loại quyền của token; nó không tự đảm bảo quyền với từng đối tượng dữ liệu.**

### Scope, audience, consent và ACL không phải một

| Cơ chế | Nó ràng buộc điều gì? | Câu hỏi API hoặc AS trả lời |
|---|---|---|
| **Scope** | Thao tác/phạm vi quyền được AS cấp theo hợp đồng API | Token có `files:read` hay `files:write`? |
| **Audience (`aud`)** | Resource Server dự kiến nhận token | Token có dành cho FileBox API này? |
| **Consent/grant** | Việc resource owner/admin/policy cho phép client sử dụng một tập quyền | ReportReader đã được ủy quyền ở cấp cần thiết chưa? |
| **ACL/RBAC/ABAC/ReBAC** | Quyền đối với tài nguyên, vai trò, thuộc tính, quan hệ và ngữ cảnh | Người dùng này được xem tệp cụ thể không? |
| **Token lifetime/state** | Khi nào token còn hiệu lực | Token hết hạn hoặc đã bị thu hồi chưa? |

Tên scope như `files:read` chỉ là ví dụ. Mỗi AS/API phải định nghĩa **ngữ nghĩa chính xác** của scope, quyền cần có, và cách map sang policy. Scope tương tự nhau giữa hai dịch vụ không đồng nghĩa được dùng chéo.

## 5. Authorization Code + PKCE: cách user ủy quyền cho client

Đối với ứng dụng bên thứ ba có người dùng, **Authorization Code flow kết hợp PKCE** là luồng phổ biến. Ví dụ dưới đây minh họa một **public client** (ứng dụng native dùng claimed HTTPS redirect URI mà hệ điều hành định tuyến về app) với `client_id=report-reader`. Nếu client là backend confidential, token endpoint còn yêu cầu xác thực client theo phương thức đã đăng ký.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Lan
    participant C as Client: ReportReader
    participant AS as FileBox Authorization Server
    participant API as FileBox Resource Server

    U->>C: Chọn nhập tệp để tạo báo cáo
    C->>C: Tạo state + code_verifier + code_challenge
    C->>AS: /authorize (client_id, scope, state, PKCE)
    AS->>U: Xác thực nếu cần
    AS->>AS: Kiểm tra client, quyền và policy
    AS->>U: Xin consent khi cần
    U-->>AS: Cho phép đọc theo phạm vi phù hợp
    AS-->>C: Redirect callback với code + state
    C->>C: Kiểm tra state
    C->>AS: /token (code, client_id, code_verifier)
    AS->>AS: Xác minh code, client, redirect, PKCE và grant
    AS-->>C: Access token (+ refresh token nếu cho phép)
    C->>API: GET /files/file-17 + Bearer access token
    API->>API: Kiểm tra token, scope, audience, ACL/tenant
    API-->>C: Trả nội dung tệp được phép
~~~

### 5.1. Client yêu cầu quyền

Client đưa người dùng đến authorization endpoint qua browser/system browser với request minh họa:

~~~http
GET /authorize?response_type=code&client_id=report-reader&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&scope=files%3Aread&state=<RANDOM_STATE>&code_challenge=<S256_CHALLENGE>&code_challenge_method=S256 HTTP/1.1
Host: auth.filebox.example.test
~~~

Một số hệ thống còn hỗ trợ `resource` theo **RFC 8707** để chỉ rõ API dự kiến, ví dụ `https://api.filebox.example.test`. Đây là tham số cần được AS hỗ trợ và kiểm tra theo policy; không giả định mọi AS đều hiểu hoặc chấp nhận.

Ý nghĩa quan trọng:

- `client_id` nhận diện client đã đăng ký, không phải bí mật.
- `redirect_uri` phải đúng với callback đã đăng ký/chấp nhận theo chính sách.
- `scope=files:read` là **yêu cầu quyền**, không phải AS đã chấp thuận quyền.
- `state` phải được client tạo ngẫu nhiên, gắn với transaction và kiểm tra khi callback nhằm ngăn nhầm response/login CSRF.
- `code_challenge` với S256 được tạo từ `code_verifier` bí mật; verifier chỉ gửi tại token endpoint, không gửi ở authorization request.

### 5.2. AS xác thực, đánh giá grant và consent

AS kiểm tra client, redirect URI, request, quyền đã cấp trước đó, yêu cầu xác thực lại, tài khoản/tenant và policy. Nếu người dùng chưa đăng nhập, AS thực hiện authentication trên miền của AS. Nếu consent cần thiết, UI phải mô tả ứng dụng nào yêu cầu quyền gì, với mức cụ thể đủ để người dùng hiểu quyết định.

AS **không nhất thiết luôn hỏi consent mỗi lần**. Grant đã cấp trước, admin consent hoặc policy tổ chức có thể chi phối. Điều bắt buộc là **quyền được phát hành phải hợp lệ theo chính sách**, không phải luôn có một màn hình nút “Đồng ý”.

Nếu user từ chối, AS trả về lỗi authorization thích hợp (ví dụ `access_denied` qua callback theo quy tắc) và không cấp code/token cho yêu cầu bị từ chối. Nếu phạm vi được chấp thuận nhỏ hơn phạm vi xin ban đầu, client phải tuân thủ grant/scope thực tế; không suy ra mình có toàn bộ scope đã yêu cầu.

### 5.3. AS phát hành authorization code và token

Sau khi điều kiện được thỏa, AS chuyển về callback đã đăng ký:

~~~http
HTTP/1.1 302 Found
Location: https://client.example.test/callback?code=<AUTH_CODE>&state=<ORIGINAL_STATE>
~~~

Client kiểm tra `state` tương ứng với authorization transaction đang chờ. Client gửi code tới token endpoint qua TLS:

~~~http
POST /token HTTP/1.1
Host: auth.filebox.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<AUTH_CODE>&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&client_id=report-reader&code_verifier=<ORIGINAL_CODE_VERIFIER>
~~~

AS phải xác nhận authorization code còn hạn, chưa sử dụng, ràng buộc đúng client, redirect URI và PKCE challenge. Code **dùng một lần**, không phải access token. Nếu điều kiện hợp lệ, AS mới cấp token:

~~~json
{
  "access_token": "<OPAQUE_OR_JWT_ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "files:read"
}
~~~

Đây là response minh họa; AS có thể trả refresh token khi chính sách cho phép và client đủ điều kiện. OIDC chỉ bổ sung ID token trong luồng OIDC thích hợp, ví dụ có `openid`; ID token không phải bằng chứng cấp quyền gọi FileBox API.

**Điểm mấu chốt:** client phải dùng quyền **được cấp trong response/token**, không dùng danh sách quyền từng xin trước đó để tự quyết định API call hợp lệ.

## 6. Access token thể hiện quyền delegated thế nào?

**Access token** là hiện vật client trình cho API. Có hai kiểu thường gặp:

| Định dạng | Cách API kiểm tra | Khả năng cập nhật quyền/thu hồi |
|---|---|---|
| **JWT access token** (thường ký JWS) | Xác minh chữ ký, issuer, audience, thời gian, loại token/profile, scope và chính sách quyền | Claims đã ký thường cố định đến hết hạn; muốn thu hồi trước hạn cần trạng thái bổ sung |
| **Opaque access token** | Introspection hoặc cơ chế tra trạng thái được API tin cậy | AS có thể phản ánh quyền/thu hồi hiện tại; cache tại API có thể tạo độ trễ |

JWT và opaque là **định dạng hoặc cách xác minh**, còn delegated access là **mô hình cấp quyền**. Không có quy tắc rằng user-delegated access bắt buộc là JWT; opaque token hoàn toàn có thể biểu diễn cùng grant.

### Minh họa JWT access token có delegation

Giả sử AS phát hành JWT access token theo một profile chấp nhận các claim dưới đây:

~~~json
{
  "iss": "https://auth.filebox.example.test",
  "sub": "user-lan-42",
  "aud": "https://api.filebox.example.test",
  "client_id": "report-reader",
  "scope": "files:read",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000600,
  "jti": "filebox-at-789"
}
~~~

Ví dụ chỉ cho thấy **payload**, không phải JWT đã được ký. Thời gian là Unix seconds minh họa; giá trị trường và cách biểu diễn tùy profile AS.

| Claim | Ý nghĩa trong ví dụ | Sai lầm cần tránh |
|---|---|---|
| `iss` | AS đã phát hành | Chấp nhận issuer bất kỳ miễn chữ ký nào đó hợp lệ |
| `sub` | Chủ thể user theo hợp đồng token này | Mặc định `sub` có cùng ý nghĩa ở mọi grant hoặc mọi issuer |
| `aud` | FileBox API được phép nhận token | Dùng token FileBox cho Billing API |
| `client_id` | Client đã được cấp access token theo profile | Tưởng `client_id` là danh tính người dùng |
| `scope` | Quyền loại thao tác được cấp | Dùng `files:read` để sửa/xóa tệp hoặc đọc tệp tenant khác |
| `exp` / `nbf` | Mốc hết/bắt đầu hiệu lực | Bỏ qua thời gian hoặc tùy tiện gia hạn token ở client |
| `jti` | Định danh riêng của JWT nếu có | Dùng định danh này làm bằng chứng duy nhất rằng token chưa bị thu hồi |

Trong các profile khác, tên field có thể là `scp`, `azp`, claim tùy biến hoặc kết quả introspection. Không tự suy diễn định dạng: API và client phải dùng **hợp đồng token đã cấu hình**, hiểu rõ ý nghĩa actor/subject/client của grant đó.

**JWT ký không mặc định được mã hóa.** Base64url decode chỉ cho biết payload, chưa chứng minh issuer hoặc claims đáng tin; API phải xác minh chữ ký bằng khóa tin cậy và thuật toán cho phép. Không đưa mật khẩu, refresh token hoặc dữ liệu riêng tư không cần thiết vào payload có thể đọc được.

### Khi token là opaque

API có thể gửi token đến introspection endpoint của AS bằng kết nối và client authentication phù hợp:

~~~http
POST /introspect HTTP/1.1
Host: auth.filebox.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <RESOURCE_SERVER_AUTHENTICATION>

token=<OPAQUE_ACCESS_TOKEN>&token_type_hint=access_token
~~~

AS có thể trả trạng thái và các thuộc tính đã cho phép API xem:

~~~json
{
  "active": true,
  "iss": "https://auth.filebox.example.test",
  "sub": "user-lan-42",
  "client_id": "report-reader",
  "aud": "https://api.filebox.example.test",
  "scope": "files:read",
  "exp": 1800000600
}
~~~

`active: true` mới là một phần của quyết định. API vẫn cần kiểm tra audience, scope, subject/client theo profile và quyền trên từng file. Introspection response là dữ liệu từ nguồn đáng tin cậy qua kênh xác thực; không tin response giả hoặc bất kỳ token string nào client tự trình bày.

## 7. Resource Server phải kiểm tra quyền nào?

Giả sử ReportReader gọi:

~~~http
GET /files/file-17 HTTP/1.1
Host: api.filebox.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

API cần xác định:

1. Có access token đúng cách trong `Authorization` không? Nếu thiếu hoặc sai định dạng, trả lỗi authentication thích hợp.
2. Access token có hợp lệ không? Với JWT, xác minh chữ ký/`iss`/`aud`/thời hạn/loại token; với opaque, introspection hoặc trạng thái tương đương. Không tin claims trước khi xác minh.
3. Scope có cho phép **đọc** tệp không? `files:read` có thể đủ cho endpoint GET theo hợp đồng; `files:write` không tự đồng nghĩa có quyền đọc trừ khi API quy định rõ.
4. User/subject được ủy quyền có quyền xem **file-17** tại thời điểm gọi không? Phải kiểm tra ACL/tenant/policy.
5. Client có bị hạn chế tài nguyên, loại dữ liệu hoặc chính sách không? Nếu AS/RS có ràng buộc client/tenant/consent/resource chi tiết, API cũng phải thực thi.
6. Token đã bị thu hồi, bị chặn hoặc bị yêu cầu sender constraint chưa? Nếu thiết kế yêu cầu, kiểm tra trạng thái/bằng chứng sở hữu khóa tương ứng.

Pseudocode diễn giải:

~~~text
function readFile(request, fileId):
    token = extractBearerAccessToken(request.headers)
    if token is missing:
        return 401

    principal = validateAccessToken(
        token,
        expectedIssuer = "https://auth.filebox.example.test",
        expectedAudience = "https://api.filebox.example.test",
        requiredTokenType = "access",
        requiredTimeChecks = true
    )
    if principal invalid:
        return 401

    if "files:read" not in principal.scopes:
        return 403

    file = repository.findById(fileId)
    if file is missing:
        return 404

    if file.tenantId != principal.authorizedTenant:
        return 404  // ví dụ theo chính sách không tiết lộ tài nguyên

    if not accessPolicy.canRead(
        subject = principal.userSubject,
        client = principal.clientId,
        file = file,
        delegationContext = principal.grantContext
    ):
        return 403

    return 200, file.allowedProjection()
~~~

Đây là mã giả, **không** là API cụ thể của thư viện hay ngôn ngữ; `grantContext` và `authorizedTenant` chỉ tồn tại nếu hệ thống phát hành/tra cứu được thông tin đáng tin cậy tương ứng. Nếu token không mang đủ ngữ cảnh, API cần tra policy/trạng thái server hoặc thiết kế ràng buộc thích hợp, không tự tạo dữ liệu thiếu.

Một lỗi kinh điển là **Broken Object Level Authorization (BOLA/IDOR)**: API xác minh JWT và `scope` rồi trả dữ liệu theo ID mà không kiểm tra user/tenant có quyền với đối tượng đó. Delegation có phạm vi phù hợp vẫn không sửa được lỗi này.

### Phản hồi lỗi thường gặp

| Tình huống | Phản hồi phù hợp | Ý nghĩa |
|---|---|---|
| Không có token hoặc token không hợp lệ/hết hạn | `401 Unauthorized` với `WWW-Authenticate: Bearer` khi áp dụng | Client cần credential hợp lệ |
| Token hợp lệ nhưng thiếu `files:read` | Thường `403 Forbidden`, có thể dùng Bearer error `insufficient_scope` | Client không được quyền thao tác |
| Token có scope nhưng file thuộc tenant khác | `403` hoặc `404` theo chính sách hạn chế lộ thông tin | Token hợp lệ không đồng nghĩa quyền trên object |
| Người dùng từ chối cấp quyền tại AS | Authorization response có lỗi như `access_denied` | Client không được tự cấp scope đã bị từ chối |

Lỗi thiếu scope không phải lý do để client refresh token vô hạn. Refresh theo cùng grant không được tự động mở rộng quyền đã cấp.

## 8. Consent và phạm vi ủy quyền phải dễ hiểu và vừa đủ

Trong các hệ thống có màn hình consent, người dùng nên nhận được thông tin rõ ràng: **ứng dụng nào**, **tài nguyên nào**, **thao tác gì**, **trong khoảng thời gian/quyền tiếp tục nào**, và **cách thu hồi** nếu sản phẩm hỗ trợ.

Ví dụ:

| Client yêu cầu | Giải thích cho người dùng | Đánh giá |
|---|---|---|
| `files:read` | “Đọc các tệp bạn chọn hoặc tệp được policy cho phép” | Có thể phù hợp nếu có ràng buộc tệp/nguồn dữ liệu cụ thể |
| `files:write` | “Tạo, thay đổi hoặc xóa tệp” | Không cần cho tính năng chỉ xem hoặc tổng hợp dữ liệu |
| `offline_access` (OIDC khi hỗ trợ) | “Duy trì quyền truy cập khi bạn không mở ứng dụng”, theo policy | Cần giải thích rõ khả năng nhận refresh token và cơ chế thu hồi |
| Quyền quản trị toàn bộ tenant | “Quản lý toàn bộ nội dung của tổ chức” | Chỉ admin/policy có thẩm quyền mới có thể cấp trong phạm vi thích hợp |

Đây là các **scope minh họa**, không phải một danh sách scope chuẩn dùng chung. `offline_access` là scope OIDC có ý nghĩa yêu cầu refresh token và chịu điều kiện của OP/policy; không mặc định rằng xin scope sẽ được cấp refresh token.

**Consent fatigue** xảy ra khi người dùng thường xuyên thấy hộp thoại xin quyền khó hiểu và bấm chấp nhận theo thói quen. Để giảm rủi ro:

- Chỉ yêu cầu quyền cần cho tính năng hiện tại; khi người dùng kích hoạt tác vụ mới mới xin quyền bổ sung (**incremental authorization**) nếu AS hỗ trợ.
- Đưa ra mô tả gần với tác động thực tế; tách quyền đọc và ghi.
- Không đổi tên ứng dụng hoặc dùng logo gây hiểu nhầm danh tính nhà cung cấp; tránh chuyển người dùng tới trang đăng nhập không phải AS đáng tin cậy.
- Cung cấp nơi kiểm tra các ứng dụng đang được cấp quyền, thời điểm cấp và cách thu hồi, theo khả năng của hệ thống.
- Nếu cần giới hạn đến một tệp, thư mục hoặc giao dịch, chỉ scope chung có thể chưa đủ; dùng policy tài nguyên và/hoặc cơ chế ủy quyền chi tiết.

### Ủy quyền chi tiết ngoài scope

Một số AS hỗ trợ **Rich Authorization Requests (RAR, RFC 9396)** với `authorization_details` để mô tả cấu trúc quyền chi tiết hơn một chuỗi scope, ví dụ loại tác vụ, đối tượng và thông số nghiệp vụ. Đây là **tính năng tùy khả năng AS**, phải được AS và RS cùng hiểu; client không thể tự thêm JSON tùy ý rồi coi là quyền đã có.

Ví dụ một tập ràng buộc ở tầng nghiệp vụ:

~~~json
{
  "type": "file_access",
  "actions": ["read"],
  "locations": ["https://api.filebox.example.test/files/file-17"]
}
~~~

Đây là mô hình giải thích ý tưởng, **không phải profile RAR chính thức của FileBox**. Tên trường và giá trị cụ thể phải được định nghĩa trong hợp đồng AS/RS. Ngay cả khi yêu cầu mô tả `file-17`, API vẫn cần đối chiếu quyền thực tế và trạng thái dữ liệu.

## 9. Phân biệt access token, refresh token và ID token khi delegated access

| Token | Được trình cho ai? | Chức năng | Rủi ro khi dùng sai |
|---|---|---|---|
| **Access token** | Resource Server có audience phù hợp | Cho phép client gọi API trong grant/scope hợp lệ | Đưa đến API khác, lộ bearer token, vượt quyền object |
| **Refresh token** | Token endpoint của AS | Xin access token mới trong giới hạn grant/policy | Gửi đến API, bị đánh cắp để duy trì khả năng truy cập |
| **ID token (OIDC)** | Client/Relying Party | Thông tin sự kiện xác thực user cho client | Dùng như access token hoặc nhầm `aud` client thành `aud` API |

**Refresh token** không là “quyền vô hạn”. Nó có thể hết hạn, bị luân phiên (rotation), bị thu hồi khi user gỡ quyền, client không còn tin cậy hoặc policy thay đổi. Một lần refresh phải tuân theo grant đã cấp và điều kiện cấp hiện hành; không được mở rộng scope vượt quyền.

**ID token** chỉ xuất hiện khi luồng có OIDC; trong ví dụ delegated OAuth thuần, client không nhất thiết nhận ID token. API không được chấp nhận ID token có `aud` là client để thay access token có `aud` là Resource Server.

Nếu ứng dụng muốn vừa “Đăng nhập bằng FileBox” vừa “Đọc tệp của bạn”, có thể kết hợp OIDC với OAuth authorization trong một kiến trúc, nhưng hai mục đích và cách kiểm tra cần tách bạch.

## 10. Vòng đời grant, token và quyết định thu hồi

Một delegated grant có thể tồn tại lâu hơn một access token, và việc token hết hạn không nhất thiết chấm dứt quyền ủy quyền đã cấp.

~~~mermaid
stateDiagram-v2
    [*] --> Requested: Client yêu cầu quyền
    Requested --> Denied: User/admin/policy từ chối
    Requested --> Authorized: Grant được phép
    Authorized --> Active: AS phát hành access token
    Active --> Active: Access token mới theo grant còn hợp lệ
    Active --> Suspended: Token hết hạn / chính sách chặn
    Suspended --> Active: Cấp token mới nếu grant hợp lệ
    Authorized --> Revoked: Người có thẩm quyền/AS thu hồi
    Active --> Revoked: Thu hồi grant/refresh token
    Suspended --> Revoked: Thu hồi grant
    Denied --> [*]
    Revoked --> [*]
~~~

Sơ đồ là mô hình khái niệm: thực tế **grant, access token và refresh token có trạng thái riêng**. Hết hạn một access token không đồng nghĩa grant chuyển sang “denied”; thu hồi grant không làm JWT tự biến mất khỏi thiết bị đã giữ bản sao.

Ví dụ:

1. **10:00:** User cho ReportReader quyền `files:read`.
2. **10:01:** AS phát hành access token có hạn 10 phút.
3. **10:08:** ReportReader gọi API; API xác minh token và ACL.
4. **10:09:** Client được phép dùng refresh token còn hiệu lực để nhận access token mới có hạn đến 10:19.
5. **10:11:** Access token ban đầu hết hạn; API từ chối token cũ.
6. **10:12:** User thu hồi quyền trong trang “Connected apps”. AS vô hiệu hóa grant/refresh token theo chính sách; access token mới có thể cần API introspection, denylist hoặc cơ chế phân phối trạng thái để từ chối sớm.
7. **10:15:** Nếu access token mới là JWT tự xác minh, API không tra trạng thái thu hồi và token chưa hết hạn (đến 10:19), một bản sao có thể còn dùng được; thiết kế phải chọn mức trễ thu hồi chấp nhận được.

**Hết hạn (`exp`)** là mốc thời gian của token; **revocation** là hành động hủy hiệu lực theo trạng thái/chính sách. Với opaque token và introspection, AS có thể trả `active:false` sau thu hồi. Nếu API cache introspection, hiệu lực thu hồi có thể bị trễ tới khi cache hết hạn. Với JWT tự xác minh, cần token ngắn hạn, denylist/trạng thái phiên hoặc cơ chế hỗ trợ khác nếu bắt buộc thu hồi gần như tức thời.

### Refresh token rotation và reuse

Nếu AS áp dụng **refresh token rotation**, client gửi refresh token RT1 để nhận access token mới và RT2; RT1 không còn được dùng. Nếu AS thấy RT1 được dùng lại, đây có thể là dấu hiệu replay và chính sách có thể thu hồi cả chuỗi token liên quan. Client cần điều phối các request refresh đồng thời để tránh reuse giả do hai request cùng dùng RT1.

Với public client, AS nên dùng những cơ chế theo chính sách an toàn hiện đại như **refresh rotation hoặc sender-constrained refresh token** khi cấp refresh token. Quyền ủy quyền vẫn bị giới hạn bởi người có thẩm quyền, consent/grant và chính sách.

## 11. Bảo vệ delegated token khỏi bị đánh cắp hoặc phát lại

**Bearer access token** là thông tin mà người đang nắm giữ có thể sử dụng, trong phạm vi server chấp nhận. Vì thế, khi token lộ qua log, XSS, URL, storage hoặc malware, kẻ tấn công có thể gọi API như client cho đến khi token bị hết hạn/chặn.

| Mối đe dọa | Tác động lên delegation | Biện pháp |
|---|---|---|
| **Phishing/consent phishing** | User bị lừa cấp quyền cho client độc hại | Hiển thị nhận diện client rõ, kiểm tra nguồn AS, cảnh báo quyền nhạy cảm, admin policy |
| **Access token leak** | Attacker dùng token trong thời gian còn hiệu lực | HTTPS, không log token, không đưa token vào URL, TTL ngắn, scope/audience tối thiểu |
| **Refresh token leak** | Attacker liên tục xin access token mới nếu chưa bị chặn | Bảo vệ lưu trữ, rotation/reuse detection, sender constraint, thu hồi grant |
| **Replay** | Bản sao bearer token được gửi lại nhiều lần | DPoP/mTLS theo khả năng, kiểm tra trạng thái/định danh nếu áp dụng, giám sát bất thường |
| **Token substitution** | ID token hoặc access token API A được gửi tới API B | Xác minh loại token, issuer, audience, scope, profile |
| **Confused deputy** | Client/API bị lợi dụng dùng quyền của mình cho yêu cầu không được phép | Ràng buộc token với audience, client, subject, resource và hành động; kiểm tra từng hop |
| **BOLA/IDOR** | Client đọc object ngoài quyền dù có scope đọc | ACL/tenant/resource policy trên mỗi request |
| **Overbroad grant** | Ứng dụng chỉ cần đọc nhưng được quyền ghi/xóa | Least privilege, incremental authorization, scope/resource cụ thể |
| **JWT verification bypass** | API chỉ decode payload hoặc chấp nhận thuật toán không an toàn | Xác minh chữ ký với khóa issuer tin cậy, allowlist thuật toán, kiểm tra claims |

### Token lưu ở đâu?

- **Ứng dụng web dùng Backend-for-Frontend:** giữ access/refresh token phía backend, browser giữ cookie phiên `Secure`/`HttpOnly`/`SameSite` phù hợp; chống CSRF/XSS và bảo vệ session.
- **Browser SPA:** ưu tiên giảm khả năng lưu token lâu dài trong JavaScript-accessible storage; token lưu bộ nhớ vẫn bị ảnh hưởng bởi XSS. Cân nhắc BFF để bảo vệ refresh token.
- **Native mobile:** dùng nơi lưu bí mật an toàn theo hệ điều hành (Keychain/Keystore) và luồng đăng nhập với system browser; tránh nhúng client secret như một bí mật thực trong binary.
- **Server-side client:** bảo vệ client credential, khóa và refresh token bằng kho bí mật, giới hạn quyền và mã hóa phù hợp; không đưa thông tin vào source, log, analytics hoặc error report.

**DPoP** và **mTLS** là các cách **sender-constrain** token, buộc request có bằng chứng sở hữu khóa phù hợp. Chúng giúp giảm khả năng dùng một token bị sao chép đơn lẻ, nhưng không thay thế kiểm tra scope, audience, ACL, chính sách hoặc thu hồi.

## 12. Khi API gọi API khác thay mặt user

Giả sử ReportReader gọi FileBox API để đọc tệp, rồi FileBox API cần gọi Search API. Một lỗi thường gặp là **chuyển nguyên access token FileBox sang Search API**, dù token chỉ có `aud` là FileBox. Search API phải từ chối token không dành cho nó.

Các lựa chọn thiết kế gồm:

1. **Tách các quyền và token theo resource:** client xin quyền phù hợp cho từng API; AS phát hành access token có audience phù hợp với API cụ thể.
2. **Delegated token exchange / on-behalf-of theo thiết kế hỗ trợ:** một thành phần tin cậy có thể xin token khác từ AS để gọi downstream API theo **RFC 8693 Token Exchange** hoặc cơ chế tương đương mà AS hỗ trợ. AS phải xác minh subject token, actor/client, mục đích, audience và policy; token mới có quyền phù hợp.
3. **Truy cập bằng danh tính service khi đúng nghiệp vụ:** API có thể sử dụng client credentials của chính nó cho tác vụ nội bộ nếu mô hình quyền cho phép. Không gọi đó là quyền “user đã đồng ý” khi thực chất không có grant của user.

Ví dụ mục tiêu của token thứ hai:

~~~text
Token A: iss = FileBox AS, aud = FileBox API, scope = files:read
Token B: iss = Trusted AS, aud = Search API, scope = index:search

FileBox API -> Search API:
    Không gửi Token A để thay Token B.
    Chỉ gửi Token B khi AS đã cho phép chuyển/trao đổi quyền tương ứng.
~~~

**Token exchange không phải cách tự nâng quyền.** Nếu user chỉ có quyền đọc tệp A, token downstream không được tự trở thành quyền đọc mọi chỉ mục hoặc chỉnh sửa tệp. Cần bảo tồn ngữ cảnh delegation và ràng buộc actor/subject theo profile, với giới hạn do AS và downstream API quyết định.

## 13. Ví dụ quyết định quyền trên tài nguyên

Giả sử Lan sử dụng ReportReader và dịch vụ FileBox có dữ liệu:

| Tệp | Tenant | Quyền của Lan | Ghi chú |
|---|---|---|---|
| `file-17` | `acme` | Đọc | Tệp Lan được chia sẻ |
| `file-18` | `acme` | Đọc và sửa | Tệp Lan sở hữu |
| `file-99` | `other-org` | Không có | Tệp thuộc tenant khác |

AS đã cấp ReportReader access token cho `https://api.filebox.example.test` với scope `files:read`, còn hạn và được API chấp nhận. Quyết định:

| Yêu cầu từ ReportReader | Kết quả | Lý do |
|---|---|---|
| `GET /files/file-17` | Cho phép | Token hợp lệ, đủ scope đọc, user được đọc file |
| `GET /files/file-18` | Cho phép | Token đủ scope đọc, user được đọc file |
| `PATCH /files/file-18` | Từ chối | User có quyền sửa nhưng **client/token chỉ được ủy quyền đọc** |
| `GET /files/file-99` | Từ chối | Token có scope đọc nhưng user/tenant không có quyền |
| `GET /billing/invoices` trên Billing API | Từ chối | Sai audience; token FileBox không dành cho Billing API |
| `GET /files/file-17` sau khi token hết hạn | Từ chối | `exp` đã đến; client cần token hợp lệ mới |
| `GET /files/file-17` sau khi user thu hồi grant | Từ chối **khi API nhận biết được thu hồi** | Mức độ tức thời phụ thuộc cơ chế token/state/cache |

### Những hiểu nhầm cần nhận ra

1. **“User đã login, vậy client được dùng mọi API?”** Không. Login chứng minh danh tính tại một hệ thống; delegated access đòi hỏi grant, scope, audience và policy phù hợp.
2. **“User có quyền admin, vậy token `files:read` sửa được file?”** Không. Quyền user không tự mở rộng scope của token.
3. **“Scope đúng là đủ để GET file của bất kỳ ai?”** Không. Cần ACL, tenant và chính sách dữ liệu.
4. **“ID token có `sub` và chữ ký tốt, vậy API dùng nó để phân quyền?”** Không. ID token dành cho client; API cần access token thích hợp.
5. **“Người dùng thu hồi quyền thì JWT đã cấp tự hết hiệu lực tức thì?”** Không mặc định. Tác dụng phụ thuộc AS/RS và cách kiểm tra trạng thái.
6. **“Đổi refresh token là xin thêm được `files:write`?”** Không. Refresh tuân thủ grant/policy; quyền bổ sung cần được cấp đúng quy trình.

## 14. Checklist triển khai delegated authorization

Khi tích hợp client thứ ba hoặc xây Resource Server nhận access token do AS cấp, kiểm tra:

1. **Đúng luồng:** dùng Authorization Code + PKCE cho ứng dụng người dùng; xác thực confidential client phù hợp; không thu thập mật khẩu tài khoản dịch vụ khác.
2. **Đúng client và callback:** `client_id` được đăng ký, redirect URI được so khớp, `state` gắn với transaction; PKCE verifier được AS kiểm tra.
3. **Đúng người có thẩm quyền:** user/admin/policy có quyền cấp loại truy cập đó; consent có ý nghĩa và không vượt quyền nền.
4. **Đúng scope và resource:** chỉ xin/cấp quyền cần dùng; API hiểu rõ scope, audience và phân quyền object/tenant.
5. **Đúng token:** access token dùng cho API; ID token dùng cho client OIDC; refresh token chỉ đi tới token endpoint.
6. **Đúng kiểm tra bảo mật:** JWT phải xác minh issuer/chữ ký/thuật toán/`aud`/thời gian; opaque phải introspect/tra trạng thái đáng tin cậy.
7. **Đúng lưu trữ và truyền:** HTTPS, `Authorization: Bearer` khi áp dụng, không URL/log token, refresh token được bảo vệ, triển khai sender constraint nếu phù hợp.
8. **Đúng vòng đời:** TTL, refresh rotation, revocation, cache introspection, quyền tenant thay đổi và logout có hành vi rõ ràng.
9. **Đúng theo mỗi request:** kiểm tra hành động, resource ownership, tenant, policy; tránh BOLA/IDOR.
10. **Đúng khi gọi downstream:** không phát tán token sang API có audience khác hoặc tự nâng quyền qua token exchange.

**Ghi nhớ:** delegated authorization trao cho client **một tập quyền đã được phê duyệt có giới hạn** để thao tác với tài nguyên. Quyền thực tế chỉ tồn tại khi **token hợp lệ, client và grant được phép, người dùng/chủ thể có thẩm quyền, API đúng audience và chính sách trên tài nguyên đều chấp nhận**. Bảo vệ delegation phải diễn ra từ lúc user cấp quyền tới khi token hết hạn hoặc grant được thu hồi.

### Tài liệu chuẩn để tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): resource owner, authorization grant, scope, client và token.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): hướng dẫn giảm rủi ro trong OAuth.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): ràng buộc code với client yêu cầu.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): chỉ rõ tài nguyên/API đích.
- [RFC 9396 — Rich Authorization Requests](https://www.rfc-editor.org/rfc/rfc9396): mô tả authorization details có cấu trúc.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token.
- [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009) và [RFC 7662 — Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): thu hồi và xác định trạng thái token.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): trao đổi token khi gọi giữa các service theo chính sách.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): phân biệt OIDC ID token và OAuth access token.
