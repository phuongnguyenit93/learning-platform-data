# Kiểm tra lược đồ claims trước khi ký

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Cấp phát token. Bài viết áp dụng cho hệ thống JWT nói chung, không phụ thuộc ngôn ngữ lập trình, thư viện hay framework.

## 1. Vì sao phải kiểm tra claims trước khi ký?

Payload JWT là một tập claim được biểu diễn dưới dạng JSON object. Khi issuer ký token, issuer xác nhận rằng những claim trong payload là nội dung mà mình chịu trách nhiệm phát hành. Chữ ký bảo vệ tính toàn vẹn của dữ liệu sau khi ký; nó **không kiểm tra claim có đúng kiểu, đúng ý nghĩa, đủ điều kiện hay phù hợp với loại token hay không**.

Một JWT có chữ ký hợp lệ vẫn có thể sai nếu payload:

- thiếu claim bắt buộc theo profile;
- dùng sai kiểu dữ liệu, chẳng hạn `exp` là chuỗi thay vì NumericDate;
- chứa scope hoặc role vượt quá quyền được cấp;
- có `aud` không phù hợp với resource server;
- có thời gian mâu thuẫn, ví dụ `exp` sớm hơn `iat`;
- trộn claim của ID token, access token và token dùng một lần;
- chứa trường tùy ý do client gửi, dữ liệu quá lớn hoặc thông tin nhạy cảm không cần thiết.

**Kiểm tra lược đồ (schema validation)** là bước xác minh payload và protected header tuân thủ cấu trúc, kiểu dữ liệu, miền giá trị và các ràng buộc ngữ nghĩa đã định nghĩa cho loại token cụ thể trước khi ký. Đây là một cổng chất lượng và bảo mật trong quy trình phát hành.

Cần phân biệt:

- **Schema validation:** dữ liệu có cấu trúc và giá trị hợp lệ theo hợp đồng token hay không?
- **Authentication:** bằng chứng danh tính hoặc grant có hợp lệ hay không?
- **Authorization:** chủ thể/client có được cấp quyền yêu cầu hay không?
- **Cryptographic signing:** payload/header có được ký bằng khóa và thuật toán được phép hay không?

Các bước này bổ trợ nhau. Schema hợp lệ không chứng minh người dùng đã đăng nhập; người dùng đăng nhập thành công cũng không làm cho một payload sai schema trở nên hợp lệ.

## 2. Định nghĩa schema theo từng loại token

Không nên dùng một schema chung cho tất cả JWT. Mỗi loại token có mục đích, bên nhận và quy tắc xác minh khác nhau. Trước khi xây dựng payload, issuer cần xác định **token profile** và chọn schema tương ứng.

| Loại token | Mục đích | Schema cần quan tâm |
| --- | --- | --- |
| OAuth 2.0 access token dạng JWT | Cho resource server quyết định truy cập API | Issuer, subject, audience, thời gian, client, scope/permission và profile access token |
| OpenID Connect ID token | Truyền kết quả xác thực tới client | Issuer, subject, audience/client, thời gian, nonce khi áp dụng, auth time và các claim xác thực |
| JWT assertion | Đóng vai trò assertion trong một giao thức/luồng ủy quyền | Issuer, subject, audience, thời hạn ngắn, định danh assertion và các ràng buộc giao thức |
| JWT nội bộ | Trao đổi dữ liệu xác thực/ủy quyền giữa các thành phần | Schema riêng được các bên thống nhất, audience và loại token rõ ràng |
| Token dùng một lần | Xác minh một hành động cụ thể | Subject, purpose, audience, expiry, định danh duy nhất và trạng thái đã dùng nếu yêu cầu |

Ví dụ, access token theo RFC 9068 có profile riêng và yêu cầu các claim nhất định. ID token theo OpenID Connect có ngữ nghĩa khác. Không lấy schema của loại này áp vào loại kia chỉ vì cả hai đều có dạng ba phần của JWT.

### 2.1. Hợp đồng schema phải rõ ràng

Với mỗi token profile, cần mô tả:

1. **Required claims:** các claim bắt buộc phải xuất hiện.
2. **Optional claims:** claim được phép có nhưng không bắt buộc.
3. **Forbidden claims:** claim không được phép xuất hiện trong profile hoặc audience đó.
4. **Types:** kiểu JSON chính xác cho từng claim.
5. **Formats and ranges:** định dạng, miền giá trị, độ dài, số phần tử và giới hạn.
6. **Semantic constraints:** quan hệ logic giữa các claim.
7. **Header constraints:** thuật toán, loại nội dung, key ID và tham số JOSE được chấp nhận.
8. **Versioning:** cách thay đổi schema mà không phá vỡ bên nhận hiện tại.

Schema nên được quản lý như cấu hình bảo mật có phiên bản, được review và triển khai có kiểm soát. Không để client gửi schema hoặc định nghĩa trường claim tùy ý cho issuer.

## 3. Kiểm tra registered claims

RFC 7519 định nghĩa các registered claim names phổ biến. Không phải claim nào cũng bắt buộc trong mọi JWT; profile cụ thể quyết định yêu cầu.

| Claim | Kiểu theo JWT | Kiểm tra schema và ngữ nghĩa |
| --- | --- | --- |
| `iss` | StringOrURI (JSON string) | Giá trị phải khớp issuer cấu hình; không rỗng nếu profile yêu cầu |
| `sub` | StringOrURI (JSON string) | Định danh chủ thể ổn định, đúng namespace và độ dài cho phép |
| `aud` | StringOrURI hoặc mảng StringOrURI | Chỉ chứa recipient được cấp phép; không rỗng và đúng audience profile |
| `exp` | NumericDate (JSON number) | Thời điểm hết hạn hợp lệ; phải sau `iat` nếu có |
| `nbf` | NumericDate (JSON number) | Thời điểm bắt đầu hiệu lực; phải phù hợp với `exp` và chính sách |
| `iat` | NumericDate (JSON number) | Thời điểm phát hành từ đồng hồ tin cậy; không bất hợp lý ở tương lai |
| `jti` | JSON string | Định danh token đúng định dạng và namespace nếu profile sử dụng |

Một số điểm cần chú ý:

- NumericDate là số giây kể từ Unix epoch, không phải chuỗi ngày giờ hoặc số mili giây.
- JSON number có thể biểu diễn số nguyên hoặc số thập phân; profile có thể yêu cầu số nguyên để đơn giản hóa so sánh.
- `aud` có thể là chuỗi hoặc mảng theo JWT; nếu profile yêu cầu một dạng cụ thể, schema phải cố định dạng đó.
- `iss` và `sub` là chuỗi theo ngữ nghĩa StringOrURI; không tự ý chuẩn hóa chữ hoa/thường làm thay đổi định danh.
- Nếu profile yêu cầu claim nhưng claim vắng mặt, phải từ chối phát hành thay vì tự điền một giá trị mặc định có ý nghĩa bảo mật.

## 4. Kiểm tra claim riêng và claim quyền

Các claim riêng (private claims) hoặc claim theo profile có thể biểu diễn scope, role, tenant, client, phương thức xác thực hoặc ngữ cảnh nghiệp vụ. Vì tên claim không tự quy định kiểu và ngữ nghĩa, issuer phải định nghĩa hợp đồng rõ ràng.

Ví dụ:

| Claim | Kiểu/định dạng được chọn | Quy tắc |
| --- | --- | --- |
| `scope` | Chuỗi theo cú pháp scope của profile | Chỉ chứa quyền đã được policy engine cấp |
| `roles` | Mảng chuỗi | Mỗi role nằm trong allowlist và thuộc đúng subject/tenant |
| `tenant_id` | Chuỗi định danh | Subject có membership hợp lệ tại tenant được chọn |
| `client_id` | Chuỗi định danh client | Lấy từ client đã xác thực, không lấy từ body tùy ý |
| `amr` | Mảng chuỗi theo profile | Chỉ phản ánh phương thức xác thực thực sự đã dùng |
| `acr` | Chuỗi mức bảo đảm xác thực | Giá trị thuộc tập mức được issuer công bố |
| `auth_time` | NumericDate | Thời điểm xác thực của subject theo ngữ nghĩa giao thức |
| `purpose` | Chuỗi enum nội bộ | Chỉ nhận các mục đích được định nghĩa cho token dùng một lần |

### 4.1. Allowlist và nguồn tạo claim

Không đưa toàn bộ profile người dùng hoặc request body vào payload bằng cách sao chép tự động. Hãy tạo claim từ một **allowlist theo token profile và audience**:

- Claim nhận diện subject được lấy từ ngữ cảnh đã xác thực.
- Quyền lấy từ quyết định authorization phía máy chủ.
- Audience lấy từ resource registry và grant.
- Thời gian lấy từ đồng hồ và chính sách issuer.
- Client lấy từ client authentication.
- Claim tùy chọn chỉ được thêm khi có nguồn tin cậy và bên nhận có nhu cầu.

Một trường `role` do client gửi không được biến thành claim quyền. Nếu schema chỉ cho phép `roles` thuộc enum nhất định, issuer vẫn phải xác minh người dùng có quyền đó trước khi thêm vào payload.

### 4.2. Tránh va chạm tên claim

Tên claim riêng có thể trùng với registered claim hoặc tên được profile khác sử dụng. Nên:

- dùng tên có namespace hoặc URI khi cần tránh va chạm giữa nhiều tổ chức;
- ghi rõ kiểu và ý nghĩa của claim trong hợp đồng;
- không thay đổi ngữ nghĩa của registered claim;
- không dùng cùng tên claim cho các kiểu dữ liệu hoặc ý nghĩa khác nhau giữa các audience.

## 5. Kiểm tra protected header

Schema validation không chỉ áp dụng cho payload. Protected header của JWS cũng cần được kiểm tra theo chính sách.

| Header parameter | Kiểm tra |
| --- | --- |
| `alg` | Bắt buộc nằm trong allowlist; tương thích với loại khóa và profile |
| `kid` | Chuỗi có giới hạn; tra cứu trong key set tin cậy; không phải URL/path tùy ý |
| `typ` | Nếu profile sử dụng, phải khớp loại token mong đợi |
| `cty` | Nếu dùng nested JWT hoặc nội dung lồng, phải đúng quy tắc profile |
| `crit` | Mọi extension được đánh dấu critical phải được hỗ trợ; nếu không hiểu phải từ chối |
| `jku` / `x5u` | Không tự động tin URL do token cung cấp; chỉ dùng khi profile và trust configuration cho phép rõ ràng |

Không cho phép header tùy ý ghi đè cấu hình thuật toán hoặc chọn khóa. Header ban đầu là dữ liệu chưa xác minh; issuer tạo header từ cấu hình của mình, verifier chỉ sử dụng nó trong phạm vi các lựa chọn đã tin cậy.

### 5.1. Header và payload phải nhất quán

Ví dụ, nếu protected header khai báo `typ` là access token, payload phải tuân thủ schema access token. Không được phát hành token có header biểu thị một loại nhưng payload mang claim của loại khác.

Với nested JWT hoặc JWE, phải xác định rõ lớp ngoài và lớp trong, content type, thuật toán và cách xác minh từng lớp. Không bỏ qua kiểm tra của lớp ngoài chỉ vì payload bên trong có chữ ký hợp lệ.

## 6. Kiểm tra kiểu dữ liệu, định dạng và giới hạn

JSON phân biệt string, number, boolean, null, array và object. Một schema an toàn phải kiểm tra đúng kiểu, không chuyển đổi ngầm để “cố làm cho hợp lệ”.

| Lỗi dữ liệu | Ví dụ sai | Quy tắc |
| --- | --- | --- |
| NumericDate thành chuỗi | `"exp": "1900000900"` | Từ chối nếu profile yêu cầu JSON number |
| Boolean thành chuỗi | `"email_verified": "true"` | Từ chối; không ép chuỗi thành boolean |
| Scope thành object | `"scope": {"read": true}` | Từ chối nếu profile quy định scope là chuỗi |
| Audience rỗng | `"aud": []` | Từ chối nếu không có recipient hợp lệ |
| Role không thuộc enum | `"roles": ["superuser"]` | Từ chối hoặc loại bỏ theo policy; không cấp quyền |
| Chuỗi vượt giới hạn | Claim chứa hàng MB dữ liệu | Từ chối theo giới hạn kích thước |
| Giá trị null | `"sub": null` | Không chấp nhận cho claim bắt buộc |

Cần định nghĩa:

- độ dài tối đa của chuỗi;
- số lượng phần tử tối đa trong array;
- kiểu dữ liệu và miền giá trị số;
- enum/allowlist cho claim có tập giá trị hữu hạn;
- quy tắc Unicode và ký tự điều khiển;
- giới hạn tổng payload và header;
- quy tắc xử lý trường null, trường thiếu và trường không được biết.

Không nhất thiết từ chối mọi claim tùy chỉnh không được schema biết tới trong mọi profile. Tuy nhiên, với profile bảo mật có allowlist chặt, chỉ nên phát hành những claim đã được định nghĩa. Nếu cho phép extension, phải có namespace, quy tắc xử lý và giới hạn rõ ràng.

## 7. Kiểm tra ràng buộc giữa các claims

Một số lỗi chỉ phát hiện được khi so sánh nhiều claim với nhau. Schema không nên chỉ kiểm tra từng trường độc lập.

| Ràng buộc | Kiểm tra |
| --- | --- |
| Thời gian | `exp` phải sau `iat`; `nbf` không được mâu thuẫn với `exp`; TTL không vượt chính sách |
| Issuer | `iss` phải thuộc cấu hình issuer đang phát hành |
| Subject | `sub` phải gắn với principal đã xác thực hoặc client/workload theo profile |
| Audience | `aud` phải là resource/client được grant cho phép |
| Client và subject | Quan hệ giữa `client_id` và `sub` phải đúng mô hình client credentials hoặc delegation |
| Tenant và quyền | `tenant_id` phải khớp membership và scope/role được cấp |
| Token type | Header `typ` và cấu trúc payload phải cùng profile |
| Authentication claims | `amr`/`acr`/`auth_time` phải phản ánh bằng chứng xác thực thực tế |
| Token purpose | Claim purpose, audience, scope và thời hạn phải phù hợp với loại token |

Ví dụ: một token có `scope` là `orders:refund` nhưng `aud` trỏ tới Profile API. Schema có thể xác nhận cả hai trường đúng kiểu, nhưng ràng buộc ngữ nghĩa phải phát hiện quyền đó không phù hợp với audience. Tương tự, một subject thuộc `tenant-a` không được nhận scope từ membership của `tenant-b`.

## 8. Xử lý claim trùng lặp và JSON không rõ ràng

JSON object về mặt thực tế có thể được parser xử lý khác nhau nếu một tên member xuất hiện nhiều lần. Ví dụ:

~~~json
{
  "sub": "user-84",
  "scope": "orders:read",
  "scope": "admin"
}
~~~

Nếu các thành phần xử lý JSON không thống nhất, issuer, gateway và resource server có thể hiểu payload khác nhau. RFC 7519 yêu cầu parser JWT phải xử lý tên claim trùng lặp theo một trong các cách: từ chối đối tượng có tên trùng hoặc chỉ sử dụng giá trị xuất hiện cuối cùng. Để giảm ambiguity, hệ thống nên **từ chối JSON có member trùng lặp** khi xây dựng và xác minh JWT.

Các biện pháp khác:

- Dùng serializer JSON đã được kiểm chứng; không tự nối chuỗi JSON từ dữ liệu đầu vào.
- Không để dữ liệu do client gửi ghi đè claim hệ thống đã tạo.
- Phát hiện trùng tên sau khi chuẩn hóa cấu trúc dữ liệu trước serialization.
- Giới hạn độ sâu object, kích thước payload và số lượng member.
- Tránh parser có hành vi khác nhau giữa các tầng; thống nhất thư viện hoặc kiểm thử tương thích.

## 9. Quy trình validate trước khi ký

Một pipeline tham khảo:

~~~mermaid
flowchart TD
    A["Xác định token profile và audience"] --> B["Thu thập claims từ nguồn tin cậy"]
    B --> C["Lọc theo allowlist của profile"]
    C --> D["Kiểm tra required / optional / forbidden"]
    D --> E["Kiểm tra kiểu, format và giới hạn"]
    E --> F["Kiểm tra ràng buộc giữa claims"]
    F --> G["Kiểm tra protected header và token type"]
    G --> H{"Schema và policy đều đạt?"}
    H -- "Không" --> X["Từ chối phát hành, ghi lỗi an toàn"]
    H -- "Có" --> I["Serialize JSON không trùng member"]
    I --> J["Ký bằng khóa và thuật toán cấu hình"]
    J --> K["Trả JWT qua kênh an toàn"]
~~~

Trình tự triển khai:

1. Chọn schema phiên bản phù hợp với loại token, issuer và audience.
2. Thu thập dữ liệu từ nguồn có thẩm quyền; không lấy nguyên payload do client đề xuất.
3. Xây dựng object claim mới theo allowlist.
4. Kiểm tra required, optional và forbidden claims.
5. Kiểm tra kiểu, định dạng, miền giá trị, kích thước và Unicode.
6. Kiểm tra ràng buộc liên trường và quyết định authorization.
7. Tạo protected header theo cấu hình thuật toán, khóa và token type.
8. Serialize bằng JSON serializer an toàn; từ chối member trùng lặp.
9. Ký JWT bằng khóa phù hợp.
10. Ghi audit về profile/schema version, issuer, audience, kết quả; không ghi token hoặc secret nguyên vẹn.

## 10. Ví dụ schema minh họa cho access token

Ví dụ dưới đây là hợp đồng nội bộ đơn giản, không thay thế profile OAuth/JWT cụ thể. Nó mô tả access token cho Orders API.

| Claim | Required? | Kiểu | Ràng buộc |
| --- | --- | --- | --- |
| `iss` | Có | String | Bằng issuer cấu hình |
| `sub` | Có | String | ID ổn định đã xác minh |
| `aud` | Có | String | Đúng Orders API |
| `iat` | Có | Integer NumericDate | Do issuer tạo |
| `exp` | Có | Integer NumericDate | Sau `iat`, TTL trong giới hạn |
| `jti` | Có theo profile minh họa | String | ID token mới, định dạng hợp lệ |
| `client_id` | Có | String | Client đã xác thực |
| `scope` | Có | String | Chỉ scope được cấp |
| `tenant_id` | Khi thao tác đa tenant | String | Subject còn membership |
| `email` | Không | String | Chỉ thêm khi API có nhu cầu |

Payload hợp lệ minh họa:

~~~json
{
  "iss": "https://auth.example.net",
  "sub": "user-84",
  "aud": "https://api.example.net/orders",
  "iat": 1900000000,
  "exp": 1900000900,
  "jti": "token-id-random",
  "client_id": "dashboard",
  "scope": "orders:read",
  "tenant_id": "tenant-a"
}
~~~

Một payload sai schema:

~~~json
{
  "iss": "https://unknown.example.org",
  "sub": null,
  "aud": [],
  "iat": "1900000000",
  "exp": 1899990000,
  "jti": "",
  "client_id": "unregistered-client",
  "scope": "orders:read orders:refund",
  "tenant_id": "tenant-b",
  "role": "superadmin"
}
~~~

Các lỗi có thể phát hiện:

- Issuer không khớp cấu hình.
- Subject null.
- Audience rỗng/sai kiểu theo schema.
- `iat` là chuỗi.
- `exp` trước `iat`.
- `jti` rỗng.
- Client không được xác minh.
- Scope chứa quyền chưa được cấp.
- Tenant không khớp membership.
- Claim `role` không thuộc allowlist nếu profile không định nghĩa.

## 11. Mã giả kiểm tra schema claims

Mã giả minh họa cách tách schema validation khỏi quá trình ký:

~~~text
function validateClaimsForSigning(claims, header, context):
    profile = tokenProfiles.require(
        tokenType = context.tokenType,
        version = context.schemaVersion
    )

    require claims is a JSON object
    require noDuplicateMemberNames(claims)

    require hasRequiredClaims(claims, profile.requiredClaims)
    require containsNoForbiddenClaims(claims, profile.forbiddenClaims)
    require allClaimsAreAllowed(claims, profile.allowedClaims)

    for each claim in claims:
        rule = profile.schema[claim.name]
        require rule.acceptsJsonType(claim.value)
        require rule.acceptsFormatAndRange(claim.value)
        require rule.acceptsLengthAndCardinality(claim.value)

    require claims.iss == context.configuredIssuer
    require claims.sub == context.verifiedSubject
    require audienceIsAllowed(claims.aud, context.allowedAudiences)
    require timeClaimsAreConsistent(claims, context.tokenPolicy)
    require authorizationClaimsAreGranted(claims, context.policyDecision)
    require tenantAndSubjectAreConsistent(claims, context.membership)

    require header.alg in context.allowedAlgorithms
    require header.kid == context.activeSigningKey.kid
    require header.typ is acceptedBy profile

    serialized = safeJsonSerialize(claims, rejectDuplicateNames = true)
    require serialized.length <= profile.maximumPayloadBytes

    return VALID
~~~

Khi schema không đạt, issuer phải dừng phát hành và trả lỗi an toàn. Không tự xóa các claim sai rồi ký tiếp nếu việc loại bỏ có thể làm thay đổi ý nghĩa quyền; cần quyết định rõ claim nào là tùy chọn và claim nào bắt buộc.

## 12. Quản lý phiên bản schema và tương thích

Schema token có thể thay đổi theo thời gian khi thêm claim, thay đổi policy hoặc nâng cấp profile. Cần quản lý thay đổi có chủ đích:

- **Additive optional claim:** thường ít phá vỡ hơn nếu bên nhận bỏ qua claim không biết, nhưng phải bảo đảm không làm thay đổi ngữ nghĩa hiện tại.
- **New required claim:** verifier cũ có thể từ chối token mới; cần triển khai verifier hỗ trợ trước khi issuer bắt đầu phát hành.
- **Change type or meaning:** là thay đổi không tương thích; nên tạo token profile/version mới hoặc namespace claim mới.
- **Remove claim:** kiểm tra mọi consumer còn phụ thuộc trước khi ngừng phát hành.
- **Unknown claim:** mỗi profile phải quy định rõ chấp nhận hay từ chối; với claim ảnh hưởng quyền, không được tự suy luận ý nghĩa.

Không nhất thiết thêm `schema_version` vào mọi JWT. Có thể quản lý version ở cấu hình issuer/profile hoặc dùng token type/namespace riêng nếu giao thức yêu cầu. Nếu thêm version claim, phải định nghĩa cách verifier xử lý giá trị không biết.

Quy trình triển khai schema mới:

1. Công bố schema/profile và cập nhật resource server.
2. Kiểm thử token mới với tất cả consumer liên quan.
3. Chuyển issuer sang phát hành theo schema mới.
4. Duy trì xác minh schema cũ trong thời gian token cũ còn hợp lệ.
5. Ngừng hỗ trợ schema cũ sau khi hết thời gian chuyển tiếp theo chính sách.

## 13. Kiểm thử schema và giám sát

Các trường hợp kiểm thử tối thiểu:

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Required | Thiếu `iss`, `sub` hoặc claim bắt buộc | Không ký |
| Type | `exp` là string, `sub` là null, `aud` sai kiểu | Không ký |
| Format | NumericDate âm/không hợp lệ, ID sai định dạng | Từ chối theo schema |
| Range | TTL quá lớn, scope quá dài, array quá nhiều phần tử | Không ký hoặc xử lý theo giới hạn đã định nghĩa |
| Semantic | `exp` trước `iat`, tenant không khớp subject | Không ký |
| Authorization | Claim role/scope vượt quyền | Không ký payload vượt quyền |
| Header | `alg` ngoài allowlist, `kid` không phải khóa active | Không ký |
| Ambiguity | JSON có tên member trùng | Từ chối |
| Type confusion | ID token bị tạo theo schema access token hoặc ngược lại | Từ chối |
| Size | Payload/header vượt giới hạn | Từ chối |
| Versioning | Consumer chưa hỗ trợ schema mới | Không rollout issuer trước khi consumer sẵn sàng |

Nên theo dõi:

- tỷ lệ lỗi schema theo profile và schema version;
- claim thường xuyên thiếu hoặc sai kiểu;
- số lần từ chối do scope/audience/tenant không phù hợp;
- payload vượt giới hạn hoặc có member trùng;
- sự khác biệt schema giữa issuer và resource server;
- lỗi phát hành sau khi rollout phiên bản mới.

Log chỉ nên ghi tên rule, profile, phiên bản schema, mã tương quan và kết quả. Tránh log toàn bộ payload nếu có dữ liệu cá nhân hoặc quyền nhạy cảm; tuyệt đối không log secret hay token nguyên vẹn.

## 14. Những sai lầm cần tránh

- Chỉ kiểm tra JSON parse được mà không xác minh schema và ngữ nghĩa.
- Dùng một schema chung cho access token, ID token, assertion và token dùng một lần.
- Coi claim đúng kiểu là claim đáng tin; bỏ qua nguồn dữ liệu và quyết định authorization.
- Tự động sao chép request/profile vào payload.
- Ép kiểu dữ liệu sai để làm schema pass.
- Dùng default value cho claim quyền hoặc danh tính khi thiếu dữ liệu.
- Không kiểm tra ràng buộc giữa `iss`, `sub`, `aud`, thời gian, scope và tenant.
- Chấp nhận member JSON trùng lặp khiến parser khác nhau hiểu payload khác nhau.
- Không giới hạn kích thước và số phần tử claim.
- Cho protected header chọn thuật toán hoặc nguồn khóa tùy ý.
- Thay đổi schema mà không kiểm tra tương thích với verifier.
- Nghĩ rằng schema hợp lệ đồng nghĩa JWT đã an toàn; vẫn phải ký và xác minh đúng cách.

## 15. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa JWT claims, registered claim names, NumericDate và xử lý tên claim trùng lặp.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): phân biệt loại token, xác minh issuer/audience và kiểm soát thuật toán.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile và yêu cầu claim cho JWT access token.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): cú pháp JSON và lưu ý về tên member trùng lặp.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): claim và quy tắc xác minh ID token.
- [JSON Schema](https://json-schema.org/): cách mô tả cấu trúc và ràng buộc dữ liệu JSON; cần kết hợp với các quy tắc ngữ nghĩa và authorization của profile.

**Ghi nhớ:** Trước khi ký JWT, hãy xác định đúng profile, kiểm tra required/optional/forbidden claims, kiểu và miền giá trị, ràng buộc liên trường, protected header và giới hạn dữ liệu. Schema hợp lệ là điều kiện cần để phát hành token nhất quán; nó phải đi cùng xác thực, phân quyền, quản lý khóa và xác minh ở bên nhận.

