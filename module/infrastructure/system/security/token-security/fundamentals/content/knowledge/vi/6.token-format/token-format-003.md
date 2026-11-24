# Claim name và claim value

Hai JWT có thể cùng chứa trường `sub`, `aud` và `exp` nhưng mang ý nghĩa hoặc mức độ an toàn rất khác nhau nếu **tên claim** hoặc **kiểu và giá trị claim** được hiểu sai. Ví dụ, `"tenant_id": "42"` khác `"tenant_id": 42` về kiểu JSON; `"scope": "invoice:read"` khác `"scope": "invoice:read:any"` về quyền; `"aud": "invoice-api"` khác `"aud": "profile-api"` về bên được phép nhận token. Một API bỏ qua các khác biệt này có thể nhận nhầm token hoặc cấp quyền sai.

Trong chương **Token format** của module **Security Token Security Fundamentals**, mục tiêu là hiểu hai thành phần nhỏ nhất của dữ liệu token:

- **Claim name**: tên thuộc tính dùng làm khóa trong tập claims, chẳng hạn `iss`, `sub`, `aud`, `scope`.
- **Claim value**: giá trị gắn với tên đó, có **kiểu dữ liệu và ngữ nghĩa** mà bên phát hành và bên nhận token phải thống nhất.

Đây là nền tảng để phân biệt JWT với opaque token, đọc access token hoặc ID token đúng mục đích, kiểm issuer/audience/scope, xác định chủ thể được đại diện và xây dựng chính sách thu hồi, chống lạm dụng token. **Claim chỉ có thể là đầu vào đáng tin cậy cho quyết định bảo mật sau khi đã xác minh được nguồn gốc và tính hợp lệ của token.**

## 1. Claim là gì trong cấu trúc JWT?

Theo mô hình JSON Web Token (JWT), **JWT Claims Set** là một đối tượng JSON chứa các cặp **tên → giá trị**. Ví dụ payload của một *access token JWT minh họa*:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "invoice-api",
  "exp": 1800003600,
  "iat": 1800000000,
  "jti": "token-8f32",
  "client_id": "accounting-web",
  "scope": "invoice:read invoice:write",
  "https://claims.example.test/tenant_id": "tenant-a"
}
~~~

Trong ví dụ này, `iss` là *claim name*, còn `"https://auth.example.test"` là *claim value* của nó. `exp` có giá trị JSON **number**; `scope` có giá trị JSON **string** gồm nhiều scope tách bằng dấu cách. Tên claim tùy biến dạng URI chỉ minh họa cách đặt tên giảm xung đột; URL đó không nhất thiết phải mở được bằng trình duyệt.

JWT thường có ba phần được mã hóa Base64URL, ngăn bằng dấu chấm:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Trong **JWS Compact Serialization**, ba phần này gồm **header**, **payload claims**, và **chữ ký**. Không phải JWT nào cũng ở dạng ba phần: **JWE** dùng mã hóa có cấu trúc khác. Các trường `alg`, `kid` và `typ` nằm trong **JOSE header** khi được sử dụng, **không phải claim name của payload**. Đọc payload JWT qua Base64URL không xác minh chữ ký và cũng không giải mã bí mật; payload JWS ký thông thường vẫn đọc được.

Với **opaque token**, client hoặc resource server thường không thể tự đọc các claims từ chuỗi token. API có thể lấy thông tin có cấu trúc tương tự qua **token introspection** hoặc dịch vụ tra cứu đáng tin cậy. Không được giả định opaque token nhất thiết chứa JSON hay JWT bên trong.

## 2. Claim name: tên phải có nghĩa và đúng chính tả

Claim name là **chuỗi tên thành viên JSON**. Trong JWT, tên phải **duy nhất trong cùng một Claims Set**. Các tên được so khớp theo chuỗi chính xác; `sub`, `Sub` và `SUB` là ba khóa khác nhau. Tương tự, `tenant_id` và `tenantId` không tự động đồng nghĩa.

### Ba nhóm tên claim trong JWT

| Nhóm | Đặc điểm | Ví dụ |
|---|---|---|
| **Registered Claim Names** | Tên đã đăng ký theo đặc tả JWT; phổ biến và có ý nghĩa được định nghĩa, nhưng không phải mọi JWT đều bắt buộc có tất cả | `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti` |
| **Public Claim Names** | Tên dùng rộng hơn giữa các bên, cần đăng ký hoặc dùng tên có khả năng chống xung đột (*collision-resistant name*) | Tên URI như `https://claims.example.test/tenant_id` |
| **Private Claim Names** | Tên do những bên đã thỏa thuận cùng sử dụng; dễ va chạm khi tích hợp với hệ khác | `tenant_id`, `roles`, `department` khi được định nghĩa riêng |

Theo RFC 7519, hai bên có thể thỏa thuận tên private, nhưng khi token đi qua nhiều issuer/client/API, một tên ngắn như `roles` có thể được hiểu khác nhau. Cách phòng tránh là định nghĩa **hợp đồng claims** rõ ràng hoặc dùng tên công khai chống xung đột. Không phải cứ có tiền tố URL là claim đã được một tổ chức chuẩn hóa hoặc được API tin cậy.

### Những registered claim quan trọng

| Claim name | Ý nghĩa theo JWT | Kiểu JSON mong đợi | Lưu ý khi dùng |
|---|---|---|---|
| `iss` (*issuer*) | Chủ thể phát hành JWT | **string** (StringOrURI) | So sánh với issuer được cấu hình tin cậy |
| `sub` (*subject*) | Chủ thể mà JWT nói tới | **string** (StringOrURI) | Có thể là user hoặc service/client tùy token profile |
| `aud` (*audience*) | Những bên nhận JWT theo dự kiến | **string** hoặc **array of strings** | Resource server cần thấy chính mình trong audience |
| `exp` (*expiration time*) | Mốc hết hạn | **number** (NumericDate) | Không được chấp nhận tại/sau mốc hết hạn, với leeway hợp lý nếu có |
| `nbf` (*not before*) | Mốc sớm nhất JWT có hiệu lực | **number** (NumericDate) | Từ chối khi chưa tới mốc có hiệu lực, trừ sai lệch đồng hồ đã quy định |
| `iat` (*issued at*) | Thời điểm JWT được phát hành | **number** (NumericDate) | Không phải bằng chứng người dùng vừa đăng nhập lại |
| `jti` (*JWT ID*) | Định danh duy nhất theo phạm vi issuer/phát hành | **string** | Có thể hỗ trợ phát hiện phát lại hoặc danh sách thu hồi nếu backend có trạng thái |

Tên **registered** không có nghĩa là “bắt buộc luôn tồn tại”. Những claim nào là bắt buộc phải dựa trên **token profile**, giao thức và hợp đồng của resource server. Chẳng hạn RFC 9068 có quy tắc riêng cho **JWT access token của OAuth 2.0**; OIDC lại có quy tắc riêng cho **ID token**. API không được tự suy toàn bộ yêu cầu của hai loại này chỉ từ bảng registered claim cơ bản.

### Tên chung không bảo đảm ngữ nghĩa chung

`scope`, `client_id`, `roles`, `permissions` hoặc `tenant_id` có thể xuất hiện trong access token nhưng **không đồng nghĩa** với bảy registered claim cơ bản của JWT. `scope` và `client_id` được các profile/giao thức OAuth định nghĩa trong những ngữ cảnh cụ thể; `roles` hay `tenant_id` có thể chỉ là claim tùy biến. Một số nhà cung cấp phát hành `scp` là danh sách scope thay vì `scope` dạng string; API chỉ dùng cách biểu diễn mà **hợp đồng với issuer** cho phép.

## 3. Claim value: JSON có nhiều kiểu, mỗi claim có hợp đồng riêng

Trong JWT, giá trị có thể dùng các kiểu JSON như string, number, boolean, array, object hoặc null. **Việc JSON cho phép một kiểu không có nghĩa kiểu đó hợp lệ cho mọi claim.** Ý nghĩa chuẩn của từng claim quyết định kiểu được phép.

| Kiểu JSON | Ví dụ | Cách hiểu |
|---|---|---|
| **String** | `"sub": "user-123"` | Một chuỗi; `"123"` vẫn là string, không phải number |
| **Number** | `"exp": 1800003600` | Số; với `exp`, `nbf`, `iat` là NumericDate |
| **Boolean** | `"email_verified": true` | Giá trị logic; `"true"` là string khác kiểu |
| **Array** | `"aud": ["invoice-api", "report-api"]` | Danh sách; phần tử cần đúng kiểu mà claim định nghĩa |
| **Object** | `"act": {"sub": "service-a"}` | Đối tượng lồng nhau; chỉ có ý nghĩa theo profile triển khai, ví dụ token exchange |
| **Null** | `"tenant_id": null` | Có khóa nhưng không có giá trị cụ thể; không được coi là tenant hợp lệ |

Một validator nên **từ chối kiểu sai**, thay vì tự ép kiểu. Ví dụ:

~~~json
{
  "sub": 123,
  "exp": "1800003600",
  "aud": 42,
  "email_verified": "true"
}
~~~

JSON trên có cú pháp hợp lệ nhưng **không đúng kiểu giá trị** cho những claim vừa nêu khi áp dụng các đặc tả tương ứng. Việc thư viện vô tình chuyển `123` thành `"123"` hoặc chuỗi thời gian thành số có thể khiến lỗi cấu hình bị che giấu và tạo lỗ hổng khi các service diễn giải khác nhau.

### NumericDate: giây từ Unix epoch, không phải mili giây

Theo JWT, `exp`, `nbf` và `iat` dùng **NumericDate**: số giây tính từ 1970-01-01 00:00:00 UTC, theo quy ước epoch của đặc tả; giá trị có thể có phần thập phân. Trong Java, `Instant.now().toEpochMilli()` trả về **mili giây**, còn `Instant.now().getEpochSecond()` trả về **giây**.

~~~text
1800000000       -> khoảng 1,8 tỷ giây kể từ epoch
1800000000000    -> cùng quy mô mốc thời gian nhưng ở đơn vị mili giây
~~~

Nếu ghi một giá trị mili giây vào claim `exp` mà API hiểu là NumericDate, token có thể bị xem là còn hiệu lực trong thời gian phi lý. Ngược lại, parse số giây như mili giây có thể khiến token hết hạn ngay. Cần kiểm loại dữ liệu, đơn vị, miền giá trị hợp lý và độ lệch đồng hồ nhỏ, có chủ đích.

**`iat` không phải `auth_time`.** Refresh token có thể được dùng để lấy access token mới có `iat` rất gần hiện tại dù người dùng đã xác thực từ nhiều giờ trước. Trong OIDC, `auth_time` có ngữ nghĩa riêng về sự kiện xác thực; dùng thông tin này tại API phải thông qua profile/bằng chứng đáng tin, không tự chép ID token làm access token.

## 4. Các claim có giá trị nhiều cách biểu diễn

### `aud`: một chuỗi hoặc danh sách chuỗi

JWT cho phép audience có **một chuỗi** hoặc **mảng các chuỗi**:

~~~json
{
  "aud": "invoice-api"
}
~~~

~~~json
{
  "aud": ["invoice-api", "report-api"]
}
~~~

Cả hai đều có thể hợp lệ theo dạng claim `aud` của JWT. Resource server Invoice API chỉ nên chấp nhận khi token có audience **chính xác** phù hợp và các điều kiện khác đều đạt. Không kiểm kiểu chứa chuỗi con:

~~~text
expectedAudience = "invoice-api"

"invoice-api" in ["invoice-api", "report-api"]  -> đúng
"invoice-api" == "invoice-api"                 -> đúng
"invoice-api" in ["invoice-api-v2"]            -> sai
substring("invoice-api-v2", "invoice-api")      -> không được dùng
~~~

Việc phát hành token cho nhiều audience làm tăng bề mặt sử dụng token; chỉ cấp cho những resource server thực sự cần thiết. Cùng một claim `scope` không làm token có audience của API khác trở nên hợp lệ.

### `scope`: chuỗi các quyền, không phải tùy ý là mảng

Trong cách biểu diễn `scope` phổ biến của OAuth 2.0 JWT access token theo RFC 9068, giá trị là **một JSON string** chứa các scope tách bằng dấu cách:

~~~json
{
  "scope": "invoice:read invoice:write"
}
~~~

Nếu một nhà cung cấp dùng:

~~~json
{
  "scp": ["invoice:read", "invoice:write"]
}
~~~

thì `scp` là một **hợp đồng khác**, chỉ được hiểu như vậy khi issuer và API đã thống nhất. Không tự động coi mọi array trong `scope` hay mọi chuỗi trong `scp` là hợp lệ. Quan trọng hơn, scope phải được so khớp theo **từng giá trị hoàn chỉnh**, tránh `invoice:read` bị kiểm thành công chỉ vì xuất hiện trong `invoice:read:any`.

Ngay cả khi đã có `invoice:read`, API vẫn phải kiểm **quyền trên từng hóa đơn**, role/permission theo nghiệp vụ và ranh giới tenant. Scope giới hạn quyền được cấp cho token, không phải giấy phép đọc mọi bản ghi.

### `sub`: chủ thể không luôn là người dùng cuối

`sub` mang ý nghĩa “subject” của token. Trong kịch bản có người dùng, nó có thể là `user-123`; trong luồng service-to-service hoặc `client_credentials`, nó có thể đại diện cho client/service theo profile AS triển khai. **Không nhận dạng kiểu chủ thể bằng cách đoán tiền tố chuỗi**, cũng không mặc định token có `sub` là bằng chứng một người dùng đã đăng nhập.

Nếu hệ thống dùng token exchange, claim `act` có thể biểu diễn actor đang hành động thay subject theo RFC 8693. Chỉ diễn giải `act` khi token profile và issuer hỗ trợ; sự xuất hiện của claim không tự cấp quyền delegation.

### `email_verified` và claims danh tính OIDC

OIDC có các claim danh tính như `name`, `email` và `email_verified`. Giá trị `email_verified: true` mô tả điều mà OpenID Provider đã xác minh theo chính sách của họ; nó **không tự chứng minh** chủ thể có role admin hoặc sở hữu tài nguyên của ứng dụng. Những thuộc tính có thể thay đổi như email cũng không nên được dùng làm định danh chủ thể ổn định nếu hệ thống có `sub` phù hợp.

## 5. Nhìn tên giống nhau vẫn có thể là hai hợp đồng khác nhau

Giả sử API chỉ cho người dùng thuộc tenant A xem báo cáo. Hai issuer khác nhau phát hành:

~~~json
{
  "iss": "https://issuer-a.example.test",
  "sub": "user-7",
  "tenant_id": "tenant-a"
}
~~~

~~~json
{
  "iss": "https://issuer-b.example.test",
  "sub": "user-7",
  "tenant_id": "tenant-a"
}
~~~

Hai JSON giống nhau ở `sub` và `tenant_id`, nhưng **không thể tự coi là cùng chủ thể, cùng quyền**. Tên `sub` cần được hiểu trong phạm vi issuer và profile; một API chỉ được chấp nhận issuer đã cấu hình, và phải xác định nguồn xác thực cho `tenant_id`. Không ghép người dùng bằng mỗi `sub` nếu hệ thống hỗ trợ nhiều issuer; tổ hợp **issuer + subject**, cộng với cơ chế ánh xạ danh tính được kiểm soát, thường thích hợp hơn.

Một tên riêng như `role` cũng có thể mang nghĩa “vai trò của ứng dụng client” ở issuer này và “vai trò của người dùng trong tenant” ở issuer khác. Trước khi đặt tên claim tùy biến, cần định nghĩa ai cấp, nguồn dữ liệu ở đâu, thời hạn hiệu lực và bên nào sử dụng.

### Hợp đồng claim mẫu cho hệ thống nhiều tenant

| Tên claim | Nguồn và ý nghĩa mong muốn | Kiểu dữ liệu | Trách nhiệm resource server |
|---|---|---|---|
| `iss` | Authorization Server được tin cậy | string | Đối chiếu chính xác issuer được cấu hình |
| `sub` | Chủ thể đã được issuer xác định | string | Phân giải đúng user/service theo profile |
| `aud` | Resource Server được cấp token | string hoặc array of strings | Kiểm khớp tên API đích |
| `exp` | Thời hạn token | NumericDate | Kiểm còn hiệu lực, không tự kéo dài |
| `client_id` | OAuth client nhận token theo profile | string | Phân biệt client với subject; kiểm quyền client khi cần |
| `scope` | Các quyền cấp cho token | string, theo profile RFC 9068 | Tách scope đúng và kiểm quyền chức năng |
| `https://claims.example.test/tenant_id` | Tenant mà issuer được phép khẳng định | string | Đối chiếu tenant thực và membership hiện hành khi cần |
| `https://claims.example.test/roles` | Vai trò trong ngữ cảnh nghiệp vụ đã định | array of strings | Kiểm vai trò đúng tenant, không cho client tự khai |

Đây là **ví dụ hợp đồng**, không phải yêu cầu mọi JWT phải có các claim tùy biến đó. Để tránh lộ dữ liệu, token chỉ nên mang những claim cần thiết; thông tin quá nhạy cảm hoặc quá hay thay đổi có thể được lấy tại API từ nguồn nội bộ đáng tin cậy.

## 6. Cơ chế kiểm claims theo từng lớp

Trước khi ra quyết định phân quyền, API phải có một **verified token context**. Không nên đưa thẳng đối tượng JSON chưa xác minh vào lớp nghiệp vụ.

~~~mermaid
flowchart TD
    A["Nhận bearer token"] --> B{"Token được API chấp nhận?"}
    B -- "Không" --> X["Từ chối 401"]
    B -- "Có" --> C["Xác minh issuer, chữ ký hoặc introspection"]
    C --> D{"Nguồn gốc và trạng thái hợp lệ?"}
    D -- "Không" --> X
    D -- "Có" --> E["Kiểm loại token, audience và thời gian"]
    E --> F{"Claims bắt buộc đúng kiểu và đúng giá trị?"}
    F -- "Không" --> X
    F -- "Có" --> G["Xây dựng principal và ngữ cảnh đã xác minh"]
    G --> H{"Scope, quyền đối tượng, tenant và chính sách đạt?"}
    H -- "Không" --> Y["Từ chối 403 hoặc 404 theo chính sách"]
    H -- "Có" --> Z["Cho phép hành động cụ thể"]
~~~

Lưu ý thứ tự trên chỉ mô tả **các bước phải hoàn thành**. Với JWT, không được tin và sử dụng claims để cấp quyền trước khi xác minh chữ ký, dù một số thư viện phải đọc header/payload để chọn bộ kiểm định ban đầu. Mọi thuật toán/khóa tin cậy phải đến từ cấu hình đã giới hạn, không phải từ yêu cầu tùy ý trong token.

### Mã giả kiểm giá trị claim

~~~text
function authorizeReadInvoice(bearer, invoiceId):
    token = verifyAccessToken(
        bearer,
        trustedIssuers = ["https://auth.example.test"],
        expectedAudience = "invoice-api",
        allowedAlgorithms = policy.allowedAlgorithms,
        requiredPurpose = "access"
    )
    if token.invalid:
        return HTTP_401

    claims = token.verifiedClaims

    if not isJsonString(claims["sub"]):
        return HTTP_401
    if not isJsonString(claims["scope"]):
        return HTTP_401
    if not isJsonNumber(claims["exp"]):
        return HTTP_401
    if not validNumericDate(claims["exp"]):
        return HTTP_401

    grantedScopes = parseSpaceDelimitedScope(claims["scope"])
    if not grantedScopes.containsExactly("invoice:read"):
        return HTTP_403

    verifiedTenant = getTenantFromTrustedContract(claims)
    if not isJsonString(verifiedTenant):
        return HTTP_401

    invoice = repository.findWithinTenant(invoiceId, verifiedTenant)
    if invoice == null:
        return HTTP_404
    if not policy.canRead(token.verifiedSubject, token.verifiedClient, invoice):
        return HTTP_403_or_404_by_policy

    return HTTP_200_with_allowed_fields
~~~

`verifyAccessToken`, `validNumericDate` và `getTenantFromTrustedContract` là **mã giả**, không phải API tiêu chuẩn. Kiểm issuer, audience, exp/nbf, chữ ký hoặc trạng thái introspection phải diễn ra đầy đủ trong phần xác minh token. Đừng chỉ dựa vào việc tên `exp` có tồn tại; giá trị còn phải hợp lệ và token chưa hết hạn. Nếu tenant không nằm trong hợp đồng token, API có thể lấy tenant/membership từ nguồn quyền nội bộ thay vì ép phải có claim.

Với **Java**, các lỗi kiểu có thể xuất hiện khi ánh xạ JSON vào `Map<String, Object>` và ép kiểu tùy tiện. Ví dụ có thể dùng một bước kiểm rõ ràng:

~~~java
Object tenantValue = verifiedClaims.get("tenant_id");
if (!(tenantValue instanceof String tenantId) || tenantId.isBlank()) {
    throw new InvalidTokenContextException("Invalid tenant claim");
}
// tenantId đã có kiểu String, nhưng vẫn phải kiểm tenant này thuộc
// phạm vi được cấp quyền trên tài nguyên cụ thể trước khi cho phép.
~~~

Đây là ví dụ sử dụng Java 17 và class exception minh họa. Ở hệ thống thật, hãy tận dụng token validator của framework và hợp đồng issuer; không phải tự viết lại thư viện xác minh JWT.

## 7. Những lỗi định dạng có thể dẫn đến lỗi bảo mật

| Lỗi | Ví dụ | Vì sao nguy hiểm | Cách xử lý |
|---|---|---|---|
| **Trùng tên claim** | Hai khóa `scope` trong cùng JSON | Các parser có thể chọn giá trị khác nhau, tạo ra cách hiểu mâu thuẫn | Bên phát hành không tạo duplicate; phía nhận nên từ chối để tránh nhập nhằng |
| **Sai kiểu dữ liệu** | `"exp": "1800003600"` hoặc `"sub": 123` | Ép kiểu tùy tiện có thể làm bỏ qua ràng buộc | Validate schema và từ chối kiểu sai |
| **Sai đơn vị thời gian** | Ghi mili giây vào `exp` | Token tưởng như còn hạn cực lâu hoặc hết hạn sai | Dùng NumericDate theo giây |
| **Sai tên/case** | `Audience` thay vì `aud` | Bên nhận không thấy claim bắt buộc hoặc đọc nhầm | Dùng đúng tên theo hợp đồng, không tự sửa chính tả |
| **So khớp gần đúng** | `aud` hoặc `scope` chứa chuỗi con | Chấp nhận nhầm audience/scope | So khớp phần tử và chuỗi đầy đủ |
| **Tin claims chưa xác minh** | Đọc Base64URL rồi dùng `roles=ADMIN` | Kẻ tấn công sửa payload và tự nhận quyền | Kiểm toàn bộ nguồn gốc và tính toàn vẹn trước khi dùng |
| **Đồng nhất nhiều issuer** | Hai issuer đều có `sub=user-7` | Gộp nhầm tài khoản từ những hệ thống khác | Gắn danh tính với issuer và quy tắc ánh xạ tin cậy |
| **Nhầm ID/access token** | Dùng OIDC ID token có `email_verified` gọi API | Token không dành cho resource server và sai mục đích | Kiểm token profile, audience và loại token |
| **Tin dữ liệu client** | Client tự gửi `tenant_id` trong header | Có thể vượt tenant dù token hợp lệ | Kiểm tenant đã được issuer bảo đảm hoặc nguồn nội bộ |
| **Claims quá nhiều** | Đưa mật khẩu, bí mật, hồ sơ đầy đủ vào JWT | Payload JWS đọc được, dễ lộ qua log/thiết bị | Tối thiểu hóa claims, tránh bí mật trong token |

Ví dụ JSON có khóa lặp:

~~~json
{
  "scope": "invoice:read",
  "scope": "invoice:admin"
}
~~~

RFC 7519 yêu cầu claim names trong JWT Claims Set **duy nhất** và đặt quy tắc cho parser khi gặp trùng. Về bảo mật ứng dụng, **chủ động từ chối dạng nhập nhằng** là chính sách dễ kiểm soát hơn là phụ thuộc vào việc parser chọn khóa đầu hay cuối, đặc biệt khi gateway và resource server có thể dùng thư viện khác nhau.

### Chuỗi Unicode và chuẩn hóa

Claim names là chuỗi JSON nên khác biệt ký tự, hoa/thường, dấu gạch nối, ký tự Unicode nhìn giống nhau hoặc dạng chuẩn hóa có thể tạo ra hai tên khác nhau. Với claim điều khiển quyền, nên dùng tên **ổn định, tài liệu hóa và so khớp chính xác**. Không tự động chuyển `tenantId` thành `tenant_id`, chuyển chữ hoa thành thường hoặc chuẩn hóa Unicode theo những quy tắc không có trong hợp đồng phát hành.

### Claim `jti` có tự chống replay không?

Không. `jti` chỉ là **định danh token**. Muốn phát hiện phát lại, hệ thống phải có cơ chế theo dõi những ID hoặc nonce đã sử dụng và phạm vi thời gian, hoặc dùng token **ràng buộc người gửi** (như DPoP/mTLS) và các quy tắc kiểm chứng phù hợp. Đặc biệt với bearer access token dùng nhiều lần trong thời hạn, việc tự cấm mọi lần xuất hiện lại của cùng `jti` sẽ làm hỏng cách sử dụng bình thường; chống replay phải được thiết kế theo **loại token và thao tác**.

## 8. Tình huống thực hành: một claim bị hiểu nhầm

Invoice API chỉ cho nhân viên xem hóa đơn thuộc tenant của mình. Một access token đã được xác minh hợp lệ có thông tin:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": ["invoice-api", "profile-api"],
  "exp": 1800003600,
  "scope": "invoice:read",
  "https://claims.example.test/tenant_id": "tenant-a"
}
~~~

Request:

~~~http
GET /api/tenants/tenant-b/invoices/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...redacted...
~~~

**Phân tích từng bước:**

1. `iss` đúng nguồn cấu hình và token đã được xác minh: có thể tin các claim trong **phạm vi hợp đồng phát hành**.
2. `aud` là mảng hợp lệ và có `invoice-api`: token đúng đối tượng nhận.
3. `exp` là NumericDate và token còn hiệu lực tại thời điểm xử lý: đạt điều kiện thời hạn.
4. `scope` chứa `invoice:read`: đủ điều kiện **quyền chức năng**, nhưng chưa đủ quyền đối tượng.
5. Claim tenant đáng tin là **tenant-a**; URL lại yêu cầu **tenant-b**: API phải **từ chối** hoặc trả 404 theo chính sách. Không lấy tenant trong URL ghi đè lên tenant từ ngữ cảnh quyền.
6. Kể cả URL được sửa thành tenant-a, API vẫn phải kiểm quyền trên **hóa đơn 42** theo owner, role hoặc quan hệ được phép.

Nếu kẻ tấn công tự thêm `"tenant_id": "tenant-b"` vào **request body**, điều này không thay đổi claims trong token do AS phát hành. Nếu kẻ tấn công sửa payload JWT để đổi tenant mà không có khóa ký hợp lệ, bước xác minh token phải thất bại.

### Tự kiểm tra

| Dữ kiện | Có thể chấp nhận như một claim hợp lệ không? | Giải thích |
|---|---|---|
| `"aud": "invoice-api"` | **Có**, về kiểu JWT | Vẫn cần kiểm issuer, chữ ký, thời gian, mục đích và policy |
| `"aud": ["invoice-api", "profile-api"]` | **Có**, về kiểu JWT | Kiểm phần tử audience chính xác |
| `"aud": "invoice-api-v2"` | **Không** nếu API đòi `invoice-api` | Không cho so khớp chuỗi con |
| `"exp": "1800003600"` | **Không**, về kiểu JWT | NumericDate phải là JSON number |
| `"exp": 1800003600` | **Có**, về kiểu | Vẫn phải kiểm mốc đã hết hạn hay chưa |
| `"scope": "invoice:read:any"` | **Không đủ** cho policy đòi chính xác `invoice:read` | Scope là các giá trị riêng |
| `"scope": ["invoice:read"]` | **Không hợp lệ** nếu contract dùng `scope` dạng string theo RFC 9068 | Không tùy ý thay kiểu |
| `"tenant_id": null` | **Không đủ** làm bằng chứng tenant | Null không phải tenant được phép |
| `"sub": "user-123"` từ issuer lạ | **Không đáng tin** | Tên và giá trị đúng kiểu không thay thế xác minh issuer |

## 9. Thiết kế và kiểm thử hợp đồng claims

Khi tích hợp Authorization Server với nhiều API, nên viết một **schema contract** cho từng loại token, gồm:

1. **Issuer và loại token** được chấp nhận, ví dụ OAuth JWT access token theo profile đã thống nhất; không nhập nhằng với ID token hoặc refresh token.
2. **Tên claim chính xác** (kể cả namespace), claim nào bắt buộc, claim nào tùy chọn.
3. **Kiểu JSON và cấu trúc bên trong**, ví dụ `aud` string hoặc array of strings, `exp` NumericDate, `scope` string.
4. **Ngữ nghĩa và nguồn dữ liệu**, ví dụ `tenant_id` lấy từ quyền thành viên được AS quản lý, không lấy từ giá trị client tự khai.
5. **Quy tắc so khớp**, gồm issuer/audience, scope, role và tenant; mức độ phân biệt hoa/thường, đơn vị thời gian.
6. **Vòng đời và độ mới**, nhất là quyền đã thay đổi, người dùng bị khóa, token bị thu hồi hoặc refresh token bị đánh cắp.
7. **Giới hạn thông tin**, tránh các claim nhạy cảm có thể bị lộ; xác định nguồn tra cứu thay thế khi cần.
8. **Đường xử lý lỗi**, gồm loại token sai, claim thiếu, null, sai kiểu, claim không biết, tên lặp và dữ liệu không hợp lệ.

Đối với API quan trọng, kiểm thử **cả trường hợp thành công lẫn thất bại**:

~~~text
[ ] Token đúng issuer, chữ ký, audience, thời hạn và scope
[ ] Token sai issuer hoặc giả chữ ký
[ ] Token đúng issuer nhưng aud dành cho API khác
[ ] aud dạng string và dạng array (theo contract)
[ ] aud là number/object hoặc array có phần tử sai kiểu
[ ] exp/nbf/iat sai kiểu hoặc sai đơn vị
[ ] scope có giá trị gần giống, thiếu quyền hoặc sai kiểu
[ ] claim name khác chữ hoa/chữ thường
[ ] claim name trùng lặp trong JSON
[ ] tenant, roles, client_id thiếu/sai kiểu/khác hợp đồng
[ ] Token hết hạn, quyền bị thu hồi, subject bị khóa
[ ] ID token hoặc refresh token bị dùng như access token
[ ] Token hợp lệ nhưng tài nguyên thuộc user/tenant khác
~~~

**Ghi nhớ:** *Claim name* cho biết đang nói về thuộc tính nào; *claim value* cho biết giá trị và kiểu của thuộc tính đó. Nhưng **ý nghĩa bảo mật** chỉ xuất hiện khi cả hai được đặt trong **đúng token profile, issuer, audience, chính sách và trạng thái hiệu lực**. Xác minh token trước, kiểm schema và giá trị claims theo hợp đồng, rồi mới dùng ngữ cảnh đã xác minh để ra quyết định phân quyền cụ thể.

### Chuẩn tham khảo

- **RFC 7519 — JSON Web Token (JWT):** JWT Claims Set; registered, public, private names; kiểu của `aud` và NumericDate.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** hợp đồng cho JWT access token, gồm những claim OAuth như `client_id` và `scope`.
- **RFC 6749 — OAuth 2.0:** scope và khung cấp quyền truy cập.
- **RFC 7662 — OAuth 2.0 Token Introspection:** cung cấp ngữ cảnh/trạng thái token từ Authorization Server qua kênh được bảo vệ.
- **OpenID Connect Core 1.0:** ID token và các claims xác thực/danh tính như `auth_time`, `acr`, `email_verified`.
