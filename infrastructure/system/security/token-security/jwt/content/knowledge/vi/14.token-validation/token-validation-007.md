# Kiểm tra typ và ngăn dùng nhầm loại token

## 1. Vì sao phải phân biệt loại JWT?

JWT chỉ mô tả một cách biểu diễn các claims được bảo vệ bằng cơ chế JOSE. Nhiều hệ thống dùng cùng định dạng JWT cho những mục đích rất khác nhau: access token để gọi API, ID token để client nhận kết quả xác thực, JWT assertion để xác thực client hoặc trao đổi token, token nội bộ giữa các dịch vụ và những profile chuyên biệt khác.

Các token này có thể cùng được phát hành bởi một issuer, cùng dùng một thuật toán và thậm chí cùng được ký bằng một khóa. Vì vậy, **chữ ký hợp lệ không đủ để chứng minh token phù hợp với nơi đang nhận nó**. Nếu API chấp nhận một JWT hợp lệ nhưng được cấp cho mục đích khác, hệ thống có thể rơi vào lỗi **cross-JWT confusion** (nhầm lẫn giữa các loại JWT).

Ví dụ điển hình là một resource server nhận ID token dành cho ứng dụng khách đăng nhập rồi diễn giải nó như access token. ID token có thể được ký đúng bởi identity provider, nhưng audience và ý nghĩa của nó hướng tới client; nó không tự động cấp quyền gọi API.

Mục tiêu của bài này là giúp thiết kế quy tắc phân loại và xác minh sao cho:

- Mỗi endpoint chỉ nhận đúng loại token đã được định nghĩa.
- Header **typ** được dùng đúng vai trò như một chỉ dấu loại nội dung.
- Mỗi loại token có tập quy tắc xác minh riêng và không thể thay thế lẫn nhau.
- Issuer, audience, claims, khóa và ngữ cảnh cùng ràng buộc token với đúng mục đích.

Nội dung thuộc Security - JSON Web Token (JWT), áp dụng chung cho mọi ngôn ngữ và nền tảng, không phụ thuộc Java hoặc Spring Security.

## 2. typ là gì và có giới hạn gì?

Trong JOSE header, tham số **typ** (type) chỉ loại nội dung được biểu diễn bởi JWT/JWS/JWE. Nó giúp bên nhận biết token thuộc profile nào và có thể từ chối sớm một loại không phù hợp.

Ví dụ:

~~~json
{
  "alg": "RS256",
  "kid": "issuer-signing-key-2026",
  "typ": "at+jwt"
}
~~~

Trong **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens**, access token dạng JWT dùng typ là **at+jwt** (profile cũng quy định dạng media type tương ứng). Giá trị này giúp resource server nhận diện access token theo profile OAuth đã chọn.

Tuy nhiên, typ có những giới hạn quan trọng:

1. Trước khi xác minh mật mã, typ chỉ là dữ liệu do người gửi tự khai báo. Kẻ tấn công có thể tự tạo token với typ mong muốn.
2. typ không chứng minh issuer, audience, thời gian hoặc quyền truy cập.
3. Một giá trị chung như JWT hoặc application/jwt không phân biệt được nhiều mục đích token khác nhau nếu hệ thống dùng nhiều profile.
4. Không phải mọi JWT đều bắt buộc có typ cụ thể. Profile hoặc hợp đồng ứng dụng quyết định typ nào bắt buộc, tùy chọn hoặc không được chấp nhận.
5. Cần so khớp theo quy tắc của profile; không tự ý bỏ tiền tố, đổi chữ hoa/thường hoặc diễn giải giá trị gần giống thành tương đương.

Với JWS Compact, protected header là một phần của signing input nên typ được bảo vệ bởi chữ ký sau khi verify thành công. Với JWE Compact, protected header được bảo vệ theo cơ chế xác thực mã hóa. Dù vậy, trước khi phép mật mã thành công, ứng dụng vẫn phải xem typ là chưa tin cậy.

**typ là một lớp phân loại, không phải bằng chứng xác thực độc lập.**

## 3. Các loại token thường gặp và mục đích của chúng

| Loại token | Bên sử dụng chính | Mục đích | Nơi thường xác minh |
| --- | --- | --- | --- |
| OAuth access token | Resource server/API | Trình bày quyền truy cập tài nguyên | API nhận token |
| OpenID Connect ID token | OpenID Connect client | Truyền kết quả xác thực người dùng cho client | Client đã khởi tạo luồng đăng nhập |
| Client assertion | Authorization server | Xác thực client theo profile assertion | Authorization server |
| JWT bearer assertion | Authorization server hoặc dịch vụ trao đổi token | Trình bày một assertion theo hợp đồng cụ thể | Endpoint chấp nhận assertion |
| JWT nội bộ giữa dịch vụ | Dịch vụ nhận đã đăng ký | Trao đổi danh tính hoặc dữ liệu theo profile nội bộ | Dịch vụ nhận cụ thể |
| Refresh token dạng JWT (nếu hệ thống chọn) | Authorization server/token endpoint | Xin cấp access token mới theo chính sách phiên | Token endpoint, không phải resource API |
| DPoP proof JWT | Resource server hoặc authorization server | Chứng minh quyền sở hữu khóa cho một request theo DPoP | Điểm kiểm tra DPoP |

Không phải mọi refresh token đều là JWT; nhiều hệ thống dùng chuỗi opaque để quản lý phiên và thu hồi. Bảng trên chỉ mô tả trường hợp một hệ thống chủ động thiết kế loại token tương ứng. Một token chỉ nên được dùng tại điểm tiếp nhận và mục đích mà profile của nó quy định.

## 4. Phân biệt access token và ID token

Đây là nhầm lẫn phổ biến nhất trong các hệ thống kết hợp OAuth 2.0 và OpenID Connect.

| Tiêu chí | Access token | ID token |
| --- | --- | --- |
| Mục đích | Cho phép client gọi resource server trong phạm vi được cấp | Truyền thông tin xác thực về người dùng cho OpenID Connect client |
| Audience | Resource server hoặc tài nguyên được cấp quyền | Client có audience là client_id theo OIDC |
| Nơi tiêu thụ | API/resource server | Client OIDC đã thực hiện authentication flow |
| Claims thường gặp | iss, sub, aud, exp, iat, scope hoặc claims quyền theo profile | iss, sub, aud, exp, iat, nonce khi được yêu cầu và các claims OIDC khác |
| Quy tắc xác minh | Theo OAuth access-token profile và policy của resource server | Theo OpenID Connect Core, gồm các ràng buộc client, nonce và luồng xác thực |
| Có thể thay thế nhau? | Không | Không |

Một ID token hợp lệ không có nghĩa resource server có thể chấp nhận nó. ID token được phát hành để client xác minh người dùng đã đăng nhập; access token được phát hành để gọi tài nguyên. Dù cả hai có chữ ký đúng và cùng issuer, chúng có audience và quy tắc sử dụng khác nhau.

### 4.1. Ví dụ nhầm audience

Giả sử:

- Client OIDC có định danh: **web-portal-123**.
- API hóa đơn có audience: **https://api.example.org/invoices**.
- Identity provider phát hành ID token cho web-portal-123.
- Identity provider cũng phát hành access token cho API hóa đơn.

ID token có thể mang audience là web-portal-123. Nếu API hóa đơn chỉ chấp nhận access token có audience của API, ID token phải bị từ chối dù chữ ký hợp lệ.

Không được giải quyết bằng cách chấp nhận bất kỳ audience nào thuộc cùng identity provider hoặc cùng domain. Resource server phải xác minh đúng audience của chính nó.

### 4.2. Không dùng ID token để lấy quyền API

Claims trong ID token mô tả kết quả xác thực theo OIDC; chúng không mặc nhiên là scope hoặc quyền truy cập tài nguyên. API không nên diễn giải các claims như email, name hoặc nhóm trong ID token thành quyền gọi endpoint.

Nếu API cần thông tin người dùng, nó có thể nhận access token đã được xác minh và dùng claims được profile cho phép, hoặc truy xuất dữ liệu qua một giao thức được thiết kế riêng. Không dùng ID token làm bearer credential chỉ vì nó có sub và chữ ký.

## 5. Explicit typing và giá trị typ

RFC 8725 khuyến nghị sử dụng explicit typing khi phù hợp để giảm nhầm lẫn giữa các loại JWT. Ý tưởng là làm cho mục đích token được thể hiện rõ trong JOSE header và được validator kiểm tra.

### 5.1. Dùng typ cụ thể theo profile

Nếu một profile quy định typ bắt buộc, issuer phải phát hành đúng giá trị và bên nhận phải kiểm tra chính xác. Ví dụ:

~~~text
OAuth 2.0 JWT Access Token profile (RFC 9068):
    typ = at+jwt
~~~

Đối với profile riêng, tổ chức có thể định nghĩa media type hoặc giá trị typ riêng theo quy tắc đặt tên được quản trị. Cần tránh dùng một typ chung cho các token có mục đích khác nhau.

Không tự phát minh một giá trị typ rồi coi nó là tiêu chuẩn liên giao thức. Nếu giá trị riêng được dùng, cả issuer và tất cả bên nhận phải có hợp đồng rõ ràng về ý nghĩa, cách so khớp và quy trình thay đổi.

### 5.2. typ phải được kiểm tra cùng policy

Một endpoint chỉ nhận access token theo RFC 9068 có thể yêu cầu typ là at+jwt, nhưng vẫn phải xác minh:

- Issuer khớp issuer tin cậy.
- Audience chứa định danh resource server.
- Chữ ký hợp lệ bằng khóa của issuer.
- Thuật toán nằm trong allowlist.
- Claims bắt buộc và thời gian hợp lệ.
- Các điều kiện profile OAuth access token được đáp ứng.

Nếu typ đúng nhưng chữ ký sai, token bị từ chối. Nếu chữ ký đúng nhưng typ hoặc audience sai, token cũng bị từ chối.

### 5.3. Không dựa vào typ chung để phân biệt mọi token

Giá trị application/jwt có thể mô tả một nội dung JWT ở mức tổng quát, nhưng không nhất thiết phân biệt access token, ID token, assertion hoặc token nội bộ. Khi nhiều loại token cùng tồn tại, cần thêm các ràng buộc mutually exclusive như audience riêng, issuer/policy riêng, claims bắt buộc khác nhau hoặc khóa ký riêng.

## 6. Mutually exclusive validation rules

RFC 8725 khuyến nghị các loại JWT khác nhau phải có quy tắc xác minh loại trừ lẫn nhau khi chúng có thể bị nhầm lẫn. Điều này có nghĩa một token hợp lệ cho profile A không được vô tình vượt qua validator của profile B.

Một cách thiết kế là xác định validator riêng cho từng loại:

| Validator | Điều kiện phân biệt bắt buộc |
| --- | --- |
| Access token validator | Audience của resource server, typ/profile access token, issuer và claims quyền theo hợp đồng |
| ID token validator | Audience là client OIDC, kiểm tra nonce/azp và các quy tắc OIDC theo flow |
| Client assertion validator | Audience là authorization server/token endpoint, issuer/subject/client binding và thời hạn assertion |
| Internal service token validator | Issuer, audience, token type và claims riêng của dịch vụ nhận |
| DPoP proof validator | typ dpop+jwt theo DPoP, ràng buộc HTTP method/URI, thời gian, jti và public key proof |

Một validator có thể dùng chung thư viện hoặc hàm mật mã, nhưng **quy tắc chấp nhận token phải được tách biệt**. Không tạo một hàm tổng quát kiểu “JWT signature valid thì chấp nhận mọi endpoint”.

### 6.1. Các ranh giới có thể kết hợp

Để làm cho các profile loại trừ lẫn nhau, có thể kết hợp:

1. **typ riêng:** mỗi loại token có giá trị type được quy định rõ.
2. **audience riêng:** access token dành cho API; ID token dành cho client; assertion dành cho authorization server.
3. **issuer và policy riêng:** issuer hoặc profile nào được chấp nhận tại endpoint nào.
4. **Claims bắt buộc riêng:** mỗi profile có cấu trúc và quy tắc claims riêng.
5. **Thuật toán/khóa riêng:** khi phù hợp, tách khóa ký giữa các loại token để giảm khả năng một token dùng nhầm ở validator khác.
6. **Endpoint riêng:** không dùng chung điểm nhận cho những loại credential có ý nghĩa khác nhau nếu không cần thiết.

Không nhất thiết phải tách tất cả các yếu tố trong mọi hệ thống. Tuy nhiên, cần có đủ ranh giới để một token không thể vượt qua validator của loại khác chỉ vì cùng issuer và cùng chữ ký.

### 6.2. Vì sao chỉ kiểm tra chữ ký là chưa đủ?

Giả sử cùng issuer ký cả ID token và access token bằng một khóa RSA. Kẻ tấn công lấy được một ID token hợp lệ và gửi tới API. Nếu API chỉ kiểm tra chữ ký rồi đọc sub, token sẽ được chấp nhận dù nó không được cấp cho API.

Validator đúng phải kiểm tra cả audience và token profile. Với access token theo RFC 9068, typ at+jwt và các điều kiện profile giúp phân biệt rõ hơn. Với ID token, client phải áp dụng đầy đủ quy tắc OIDC thay vì chỉ xác minh chữ ký.

## 7. Các loại JWT khác cần validator riêng

### 7.1. Client assertion

Trong một số profile OAuth, client dùng JWT assertion để xác thực với authorization server. Assertion có thể có iss và sub gắn với client, aud hướng tới authorization server/token endpoint và thời hạn ngắn.

Resource server không nên chấp nhận client assertion như access token. Hai loại token có mục đích và audience khác nhau. Validator assertion cần kiểm tra đúng client binding, audience và quy tắc chống replay theo profile.

### 7.2. JWT bearer assertion

JWT bearer assertion được sử dụng trong một số luồng trao đổi token. Nó được gửi tới token endpoint theo một hợp đồng riêng; không tự động trở thành bearer token để gọi API.

Validator phải biết assertion được phát hành bởi ai, dành cho endpoint nào, có thời hạn bao lâu và có được phép sử dụng một lần hay không. Nếu assertion có jti và chính sách chống replay, hệ thống cần lưu trạng thái sử dụng trong khoảng thời gian phù hợp.

### 7.3. Token nội bộ giữa các dịch vụ

Một tổ chức có thể định nghĩa JWT nội bộ cho giao tiếp service-to-service. Không nên dùng cùng một typ/audience/claims với access token công khai nếu hai loại có đặc quyền hoặc ranh giới tin cậy khác nhau.

Ví dụ token dành cho service báo cáo chỉ nên có audience và scope được dịch vụ báo cáo hiểu. Một service khác không được nhận token đó chỉ vì nó cũng tin issuer nội bộ.

### 7.4. DPoP proof JWT

DPoP sử dụng một JWT proof riêng, có typ là dpop+jwt theo profile. Proof được ràng buộc với phương thức HTTP, URI, thời gian, jti và khóa công khai của client. Đây không phải access token và không thể thay thế access token.

Khi endpoint yêu cầu DPoP, cần validator riêng cho proof và kiểm tra ràng buộc giữa proof với access token theo RFC 9449. Không chấp nhận một JWT tùy ý có chữ ký như DPoP proof.

## 8. cty và nested JWT: phân biệt lớp ngoài với lớp trong

Tham số **cty** (content type) trong JOSE header có thể chỉ loại nội dung bên trong, ví dụ một JWT lồng trong JWE hoặc JWS. Nó khác với typ:

| Trường | Vai trò |
| --- | --- |
| typ | Mô tả loại token/nội dung đang được biểu diễn ở lớp hiện tại |
| cty | Mô tả loại nội dung nằm bên trong payload của lớp hiện tại |

Ví dụ, một JWT được ký rồi mã hóa có thể có JWE bên ngoài và JWS bên trong. Bên nhận cần giải mã lớp ngoài theo policy JWE, sau đó xác minh lớp JWS bên trong theo policy issuer tương ứng. Không để cty tự kích hoạt parser hoặc validator bất kỳ.

Mỗi lớp cần có loại serialization, thuật toán, nguồn khóa, token profile và giới hạn độ sâu được định nghĩa trước. Nếu lớp trong là access token, vẫn phải kiểm tra audience/resource server của lớp trong; việc lớp ngoài đã giải mã thành công không tự động làm lớp trong đáng tin cậy.

## 9. Quy trình phân loại và xác minh token

Luồng sau minh họa cách chọn validator từ endpoint, sau đó xác minh đúng profile:

~~~mermaid
flowchart TD
    A["Nhận request và token chưa tin cậy"] --> B["Xác định endpoint/resource từ cấu hình tin cậy"]
    B --> C["Chọn token profile được endpoint chấp nhận"]
    C --> D["Parse header có giới hạn"]
    D --> E{"typ có phù hợp profile?"}
    E -- "Không" --> X["Từ chối"]
    E -- "Có" --> F["Chọn issuer policy, thuật toán và nguồn khóa"]
    F --> G["Verify JWS hoặc authenticated decrypt JWE"]
    G --> H{"Bằng chứng mật mã hợp lệ?"}
    H -- "Không" --> X
    H -- "Có" --> I["Chạy validator riêng của profile"]
    I --> J{"iss, aud, thời gian, claims và binding hợp lệ?"}
    J -- "Không" --> X
    J -- "Có" --> K["Tạo ngữ cảnh token đã xác minh"]
    K --> L["Kiểm tra quyền trên hành động/tài nguyên"]
~~~

Thứ tự có thể thay đổi một phần theo profile JOSE, nhưng policy phải được chọn từ endpoint/ngữ cảnh tin cậy. typ có thể được kiểm tra sơ bộ để từ chối sớm; chỉ sau xác minh mật mã mới được xem nó là header đã được bảo vệ.

## 10. Mã giả cho validator access token và ID token

Đoạn mã giả dưới đây thể hiện hai validator tách biệt. Các hàm mật mã phải dùng thư viện JOSE/OIDC phù hợp:

~~~text
function validateAccessToken(rawToken, resourceServerPolicy):
    parsed = strictParseJwtWithinLimits(rawToken)
    header = parsed.protectedHeader

    require header.typ == resourceServerPolicy.requiredAccessTokenType
    require header.alg in resourceServerPolicy.allowedAlgorithms
    key = resolveTrustedIssuerKey(resourceServerPolicy.issuer, header.kid)
    require verifyJws(rawToken, key, resourceServerPolicy.allowedAlgorithms)

    claims = verifiedClaims(rawToken)
    require claims.iss exactly equals resourceServerPolicy.issuer
    require claims.aud contains resourceServerPolicy.resourceAudience
    require validateAccessTokenProfileClaims(claims, resourceServerPolicy)
    return ValidatedAccessToken(claims)

function validateIdToken(rawToken, oidcClientContext):
    parsed = strictParseJwtWithinLimits(rawToken)
    header = parsed.protectedHeader

    require header.alg in oidcClientContext.allowedIdTokenAlgorithms
    key = resolveTrustedProviderKey(oidcClientContext.issuer, header.kid)
    require verifyJws(rawToken, key, oidcClientContext.allowedIdTokenAlgorithms)

    claims = verifiedClaims(rawToken)
    require claims.iss exactly equals oidcClientContext.issuer
    require claims.aud contains oidcClientContext.clientId
    require validateOidcNonceAndAzpRules(claims, oidcClientContext)
    require validateIdTokenTimeAndFlowRules(claims, oidcClientContext)
    return ValidatedIdToken(claims)
~~~

Mã giả chỉ minh họa ranh giới. Validator ID token phải thực hiện đầy đủ quy tắc OpenID Connect Core phù hợp với flow, bao gồm các điều kiện về nonce, azp khi áp dụng, thời gian và các ràng buộc khác. Không dùng đoạn mã rút gọn này như một triển khai OIDC hoàn chỉnh.

## 11. Những lỗi thiết kế thường gặp

| Lỗi | Vì sao nguy hiểm | Biện pháp |
| --- | --- | --- |
| Chấp nhận mọi JWT có chữ ký hợp lệ | Token của profile khác có thể được dùng nhầm | Validator riêng theo token profile |
| Chỉ kiểm tra typ | Kẻ tấn công có thể tự khai typ mong muốn | Xác minh chữ ký, issuer, audience và claims |
| Chấp nhận typ chung cho nhiều loại token | Không phân biệt access token, ID token và assertion | Explicit typing hoặc ranh giới validation khác |
| Resource server nhận ID token | Token dành cho client, không phải API | Kiểm tra audience và access-token profile |
| Dùng một validator cho access token và client assertion | Nhầm mục đích và audience | Tách validator và endpoint |
| Chỉ kiểm tra issuer, bỏ qua audience | Token dành cho API khác có thể bị chấp nhận | Audience riêng cho resource server |
| Dùng chung khóa nhưng không tách quy tắc | Chữ ký đúng có thể che giấu token sai mục đích | Mutually exclusive validation rules |
| Tin cty để xử lý nội dung tùy ý | Có thể kích hoạt parser/validator ngoài dự kiến | Nested profile và giới hạn lớp đã cấu hình |
| Dùng token_use không chuẩn như quy tắc phổ quát | Các issuer khác nhau có thể diễn giải khác | Chỉ dùng claim riêng khi profile quy định rõ |

## 12. Ma trận kiểm thử chống nhầm loại token

Giả sử một hệ thống có API hóa đơn, client OIDC và token endpoint. Ma trận sau giúp xác nhận token của một profile không được chấp nhận ở profile khác:

| Token đầu vào | API hóa đơn | OIDC client callback | Token endpoint assertion |
| --- | --- | --- | --- |
| Access token đúng audience API, đúng typ/profile | Có thể chấp nhận sau toàn bộ kiểm tra | Từ chối như ID token | Từ chối như assertion |
| ID token đúng audience client, nonce hợp lệ | Từ chối | Có thể chấp nhận sau toàn bộ OIDC validation | Từ chối |
| Client assertion đúng audience token endpoint | Từ chối | Từ chối | Có thể chấp nhận sau assertion validation |
| Access token đúng chữ ký nhưng audience sai | Từ chối | Từ chối | Từ chối |
| Token typ đúng nhưng chữ ký sai | Từ chối | Từ chối | Từ chối |
| JWT chung typ application/jwt, không có profile phân biệt | Từ chối nếu endpoint yêu cầu profile rõ | Từ chối nếu thiếu điều kiện OIDC | Từ chối nếu không đáp ứng assertion profile |
| Token ký bởi issuer không được policy cho phép | Từ chối | Từ chối | Từ chối |

Nên kiểm thử cả trường hợp issuer dùng chung một khóa cho nhiều loại token. Đây là cách chứng minh validator thực sự dựa trên audience/profile/claims thay vì chỉ dựa vào chữ ký.

## 13. Quan sát vận hành

Các chỉ số hữu ích:

- Số token bị từ chối vì typ không phù hợp.
- Số audience mismatch theo endpoint.
- Số token đúng chữ ký nhưng sai profile.
- Số trường hợp ID token được gửi tới resource server.
- Số assertion hoặc DPoP proof được gửi nhầm endpoint.
- Số lỗi issuer, nonce, azp, thời gian hoặc claim bắt buộc.

Log nên ghi mã lỗi và policy ID, không ghi toàn bộ JWT hoặc claims nhạy cảm. Nếu cần điều tra, có thể ghi loại profile dự kiến và loại lỗi đã chuẩn hóa, nhưng phải tránh tin các giá trị typ/iss chưa xác minh như sự thật.

## 14. Checklist triển khai

1. [ ] Xác định rõ từng loại JWT và endpoint nào được phép nhận.
2. [ ] Dùng typ cụ thể theo profile khi profile quy định; không coi typ là bằng chứng độc lập.
3. [ ] Có validator riêng cho access token, ID token, assertion, token nội bộ và DPoP proof nếu hệ thống hỗ trợ.
4. [ ] Các validator có quy tắc loại trừ lẫn nhau, đặc biệt về audience, issuer, claims và loại token.
5. [ ] Resource server kiểm tra audience của chính tài nguyên đó.
6. [ ] ID token được xác minh theo OIDC client context, bao gồm nonce/azp khi áp dụng.
7. [ ] Client assertion và JWT bearer assertion chỉ được nhận tại endpoint/profile tương ứng.
8. [ ] typ/cty được xử lý theo policy; nested JWT có giới hạn và validator riêng cho từng lớp.
9. [ ] Không dùng claim tùy biến như token_use làm tiêu chuẩn toàn cục nếu profile không định nghĩa.
10. [ ] Có negative test chứng minh token của profile A không vượt qua validator của profile B.
11. [ ] Claims chỉ được sử dụng sau khi bằng chứng mật mã và toàn bộ validation rules thành công.
12. [ ] Authorization vẫn được thực hiện riêng theo tài nguyên và hành động.

## 15. Tài liệu tiêu chuẩn liên quan

- **RFC 8725 — JSON Web Token Best Current Practices:** explicit typing, mutually exclusive validation rules và phòng cross-JWT confusion.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile JWT access token, bao gồm typ at+jwt và các điều kiện xác minh cho resource server.
- **RFC 7519 — JSON Web Token (JWT):** cấu trúc JWT và JOSE header/claims liên quan.
- **RFC 7515 — JSON Web Signature (JWS):** protected header và chữ ký.
- **OpenID Connect Core 1.0:** ID token, audience, nonce, azp và quy tắc xác minh theo authentication flow.
- **RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants:** JWT bearer assertion và client authentication.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** DPoP proof JWT và ràng buộc với request.

**Nguyên tắc ghi nhớ:** Một JWT có thể hợp lệ về mật mã nhưng sai mục đích. Hãy chọn validator theo ngữ cảnh tin cậy, dùng typ/profile, issuer, audience và claims để tạo các quy tắc loại trừ lẫn nhau. Chỉ chấp nhận token sau khi nó vượt qua đúng validator dành cho loại token đó.
