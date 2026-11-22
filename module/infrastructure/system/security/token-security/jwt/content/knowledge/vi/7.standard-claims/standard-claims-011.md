# Phân biệt claim chuẩn của JWT với claim riêng của từng giao thức

## 1. JWT là định dạng chứa claims, không tự định nghĩa toàn bộ ý nghĩa của chúng

JSON Web Token (JWT) là một định dạng biểu diễn claims dưới dạng JSON và bảo vệ chúng bằng cơ chế như chữ ký/MAC của JWS hoặc mã hóa của JWE. JWT cung cấp cấu trúc để mang thông tin; **ý nghĩa cụ thể của từng claim còn phụ thuộc vào chuẩn JWT, giao thức hoặc profile đang sử dụng và hợp đồng giữa bên phát hành với bên nhận**.

Ví dụ, hai token đều có thể chứa:

```json
{
  "sub": "user-42",
  "role": "admin"
}
```

Nhưng nếu một hệ thống định nghĩa `role` là quyền quản trị toàn bộ tổ chức, còn hệ thống khác định nghĩa nó là quyền quản trị một dự án, cùng một tên claim không có nghĩa hai giá trị mang cùng phạm vi quyền. Bên nhận không được tự suy diễn ý nghĩa chỉ từ tên claim.

Khi đọc một JWT, cần xác định ba lớp thông tin:

1. **Claim được định nghĩa bởi JWT:** ý nghĩa chung trong chuẩn JWT, ví dụ `iss`, `sub`, `aud`, `exp`.
2. **Claim được định nghĩa bởi giao thức/profile:** ý nghĩa được quy định trong một chuẩn sử dụng JWT, ví dụ `auth_time` trong OpenID Connect hoặc `client_id` trong JWT access token profile.
3. **Claim riêng của ứng dụng/tích hợp:** ý nghĩa do các bên thống nhất, ví dụ `tenant_id`, `roles`, `department`.

Các lớp này có thể cùng xuất hiện trong một payload. Điều quan trọng là biết chuẩn nào chịu trách nhiệm định nghĩa ý nghĩa và quy tắc xác minh cho từng claim.

## 2. Các nhóm tên claim trong RFC 7519

[RFC 7519, mục 4](https://www.rfc-editor.org/rfc/rfc7519#section-4) chia claim name thành ba nhóm: registered claim names, public claim names và private claim names.

### Registered Claim Names

Đây là các tên claim được định nghĩa trong chuẩn JWT hoặc được đăng ký trong hệ thống đăng ký claim tương ứng. Những tên cốt lõi được RFC 7519 định nghĩa gồm:

| Claim | Ý nghĩa tổng quát |
| --- | --- |
| `iss` | Issuer – bên phát hành JWT |
| `sub` | Subject – chủ thể mà JWT nói đến |
| `aud` | Audience – đối tượng nhận dự kiến |
| `exp` | Expiration Time – thời điểm hết hạn |
| `nbf` | Not Before – thời điểm bắt đầu có hiệu lực |
| `iat` | Issued At – thời điểm phát hành |
| `jti` | JWT ID – định danh JWT cụ thể |

Các claim này có ý nghĩa chung được chuẩn hóa để nhiều hệ thống có thể hiểu thống nhất. Tuy nhiên, **registered không đồng nghĩa với bắt buộc**. Ở cấp JWT tổng quát, RFC 7519 xem các claim này là tùy chọn; một profile hoặc ứng dụng có thể yêu cầu một hay nhiều claim phải có mặt.

Ví dụ, một JWT tối giản vẫn có thể không chứa `iat` hoặc `jti` nếu profile mà nó tuân theo không yêu cầu. Ngược lại, một profile access token cụ thể có thể yêu cầu các claim này.

### Public Claim Names

Public claim names là tên được sử dụng công khai và cần được đặt theo cách giảm nguy cơ xung đột. RFC 7519 khuyến nghị dùng tên có tính **collision-resistant**, chẳng hạn tên gắn với namespace do tổ chức kiểm soát hoặc URI mà tổ chức sở hữu.

Ví dụ minh họa:

```json
{
  "https://claims.example.com/tenant_id": "tenant-17",
  "https://claims.example.com/risk_level": "high"
}
```

Tên dạng URI ở đây giúp tránh đụng tên với claim do tổ chức khác định nghĩa. Nó không có nghĩa bên nhận được phép tự truy cập URI đó hoặc tin claim chỉ vì chuỗi trông giống URL.

### Private Claim Names

Private claim names là tên do các bên phát hành và nhận thống nhất để trao đổi dữ liệu riêng. Chúng không có cơ chế namespace chống xung đột như public claim names.

Ví dụ:

```json
{
  "tenant_id": "tenant-17",
  "roles": ["reviewer", "approver"],
  "department": "finance"
}
```

Các tên như `tenant_id`, `roles`, `department` chỉ có ý nghĩa theo hợp đồng của hệ thống phát hành và nhận. Nếu nhiều tổ chức hoặc nhiều giao thức cùng dùng một tên cho ý nghĩa khác nhau, có thể xảy ra xung đột hoặc hiểu nhầm.

| Nhóm tên | Ai xác định ý nghĩa? | Mục tiêu chính | Ví dụ |
| --- | --- | --- | --- |
| Registered | Chuẩn JWT hoặc đặc tả đã đăng ký | Có ý nghĩa chuẩn hóa | `iss`, `sub`, `aud`, `exp` |
| Public | Tổ chức/chuẩn công khai có namespace chống xung đột | Tránh đụng tên giữa các bên | `https://claims.example.com/tenant_id` |
| Private | Các bên tích hợp thống nhất | Trao đổi dữ liệu riêng | `tenant_id`, `roles` |

## 3. Phân biệt “registered claim” với “claim của giao thức”

Hai khái niệm này không phải lúc nào cũng loại trừ nhau.

- **Registered claim** nói về trạng thái tên claim được chuẩn hóa/đăng ký và định nghĩa trong hệ sinh thái JWT.
- **Protocol-defined claim** nói về nơi quy định ý nghĩa và cách dùng claim trong một giao thức cụ thể.

Một claim có thể được định nghĩa bởi giao thức và đồng thời có tên trong IANA JWT Claims Registry. Việc một tên xuất hiện trong registry không có nghĩa mọi loại JWT đều phải chứa claim đó hoặc áp dụng cùng một quy tắc nghiệp vụ.

Ví dụ, OpenID Connect định nghĩa `auth_time` cho ID Token. Một hệ thống chỉ xử lý JWT access token theo profile khác không được tự hiểu `auth_time` như một điều kiện chung bắt buộc của mọi JWT. Ngược lại, một client OpenID Connect phải tuân thủ cách diễn giải `auth_time` trong OpenID Connect khi claim này được yêu cầu.

Do đó, khi gặp claim chưa quen, hãy hỏi:

1. Tên claim có được JWT core định nghĩa không?
2. Tên claim có được đăng ký trong IANA JWT Claims Registry không, và registry dẫn tới đặc tả nào?
3. Giao thức/profile hiện tại có định nghĩa claim này không?
4. Claim là bắt buộc, tùy chọn hay chỉ bắt buộc trong một điều kiện cụ thể?
5. Bên nhận cần xác minh giá trị bằng quy tắc nào?

Không phân loại claim chỉ bằng cách nhìn tên hoặc đoán rằng nó “trông có vẻ chuẩn”.

## 4. Claim chuẩn của JWT không đồng nghĩa với claim bắt buộc

RFC 7519 định nghĩa ý nghĩa của các registered claims nhưng không bắt buộc mọi JWT phải chứa tất cả chúng. Tính bắt buộc được quyết định bởi profile, giao thức hoặc hợp đồng triển khai.

Ví dụ:

| Bối cảnh | Quy tắc về claim |
| --- | --- |
| JWT tổng quát theo RFC 7519 | `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti` đều là claim tùy chọn ở cấp định dạng tổng quát |
| JWT access token theo RFC 9068 | Profile yêu cầu một tập claim cụ thể, bao gồm `iss`, `exp`, `aud`, `sub`, `client_id`, `iat`, `jti` |
| OpenID Connect ID Token | Bắt buộc có `iss`, `sub`, `aud`, `exp`, `iat`; một số claim khác được yêu cầu theo điều kiện của giao thức |
| JWT nội bộ của ứng dụng | Yêu cầu phụ thuộc hợp đồng và chính sách của hệ thống |

Một validator không nên áp dụng một danh sách claim cố định cho mọi JWT. Trước hết phải biết token thuộc loại nào, được phát hành theo profile nào và tài nguyên nào sẽ nhận token.

## 5. Ví dụ: claim trong JWT access token theo OAuth 2.0

[RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068) quy định một profile để biểu diễn OAuth 2.0 access token bằng JWT. Profile này sử dụng các claim JWT cốt lõi và bổ sung quy tắc cho ngữ cảnh access token.

Các claim bắt buộc trong profile bao gồm:

| Claim | Vai trò trong profile access token |
| --- | --- |
| `iss` | Authorization server phát hành token |
| `exp` | Thời điểm access token hết hạn |
| `aud` | Resource server hoặc tài nguyên dự kiến nhận token |
| `sub` | Chủ thể của access token |
| `client_id` | Client đã yêu cầu token |
| `iat` | Thời điểm token được phát hành |
| `jti` | Định danh access token |

Ví dụ minh họa:

```json
{
  "iss": "https://as.example.com/",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "client_id": "orders-web-client",
  "iat": 1893452400,
  "exp": 1893456000,
  "jti": "at-9f82d1",
  "scope": "orders.read orders.write"
}
```

Trong ví dụ:

- `iss`, `sub`, `aud`, `iat`, `exp`, `jti` là các registered claims JWT cốt lõi.
- `client_id` được profile access token quy định để xác định OAuth client.
- `scope` biểu diễn phạm vi quyền theo cách profile và authorization server thống nhất; nó không phải một trong bảy registered claims cốt lõi của RFC 7519.

Profile còn quy định cách nhận diện loại token qua JOSE header `typ`, thường dùng giá trị `at+jwt` hoặc media type tương ứng theo RFC 9068. `typ` nằm trong header, không phải payload claim.

### Vì sao không thể chỉ kiểm tra chữ ký?

Một JWT có chữ ký hợp lệ vẫn có thể không phải access token dành cho API hiện tại. Resource server cần xác minh đúng issuer, audience, loại token, thời hạn và các claim bắt buộc theo RFC 9068. Một ID Token của OpenID Connect hoặc JWT nội bộ khác không được chấp nhận làm access token chỉ vì cùng được ký bởi một hệ thống tin cậy.

## 6. Ví dụ: claim trong OpenID Connect ID Token

OpenID Connect (OIDC) là một giao thức xác thực xây dựng trên OAuth 2.0. ID Token là JWT chứa các claims về sự kiện xác thực và chủ thể được xác thực.

Theo [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html#IDToken), các claim bắt buộc của ID Token gồm:

| Claim | Ý nghĩa trong ID Token |
| --- | --- |
| `iss` | OpenID Provider phát hành ID Token |
| `sub` | Subject Identifier của người dùng |
| `aud` | Client ID của bên nhận dự kiến; có thể có nhiều audience theo quy tắc OIDC |
| `exp` | Thời điểm ID Token hết hạn |
| `iat` | Thời điểm ID Token được phát hành |

Các claim khác có thể được yêu cầu tùy điều kiện:

| Claim | Ý nghĩa | Khi nào cần chú ý? |
| --- | --- | --- |
| `auth_time` | Thời điểm người dùng thực sự được xác thực | Phải có khi request dùng `max_age`; client xác minh độ mới của lần xác thực |
| `nonce` | Giá trị liên kết ID Token với Authentication Request | Nếu request gửi `nonce`, ID Token phải trả lại giá trị phù hợp để client đối chiếu |
| `acr` | Authentication Context Class Reference | Diễn tả ngữ cảnh/phương pháp mức xác thực theo quy ước OIDC/OP |
| `amr` | Authentication Methods References | Mô tả các phương thức xác thực đã dùng |
| `azp` | Authorized party | Dùng trong các trường hợp OIDC quy định, đặc biệt khi có nhiều audience |
| `at_hash` | Hash của access token liên quan | Được xác minh trong các luồng OIDC áp dụng |

Ví dụ minh họa:

```json
{
  "iss": "https://id.example.com/",
  "sub": "user-42",
  "aud": "client-123",
  "exp": 1893456000,
  "iat": 1893452400,
  "auth_time": 1893452100,
  "nonce": "n-0S6_WzA2Mj",
  "acr": "urn:example:loa:2",
  "amr": ["pwd", "otp"]
}
```

`auth_time` không giống `iat`: ID Token có thể được phát hành sau lần xác thực người dùng. Nếu client yêu cầu xác thực mới bằng `max_age`, chỉ kiểm tra `iat` không đủ để chứng minh người dùng vừa xác thực.

Các claim OIDC không phải là yêu cầu chung cho mọi JWT. Một resource server chỉ xử lý access token không được mặc định yêu cầu `nonce` hoặc `auth_time` theo quy tắc ID Token.

## 7. Ví dụ: claim trong DPoP proof JWT

Demonstrating Proof of Possession (DPoP), được định nghĩa trong [RFC 9449](https://www.rfc-editor.org/rfc/rfc9449), dùng một JWT proof để chứng minh client đang sở hữu khóa riêng tương ứng với khóa công khai được khai báo trong proof.

DPoP proof là một loại JWT có quy tắc riêng. Các claim quan trọng gồm:

| Claim | Vai trò trong DPoP proof |
| --- | --- |
| `jti` | Định danh duy nhất của proof; hỗ trợ phát hiện proof bị phát lại |
| `htm` | HTTP method của request được proof ràng buộc |
| `htu` | HTTP URI của request được proof ràng buộc theo quy tắc DPoP |
| `iat` | Thời điểm tạo proof |
| `ath` | Hash access token, được yêu cầu khi proof gửi cùng access token đến resource server |
| `nonce` | Challenge do authorization server hoặc resource server cung cấp trong các trường hợp áp dụng |

Ví dụ rút gọn:

```json
{
  "jti": "dpop-proof-7a91",
  "htm": "POST",
  "htu": "https://api.example.com/orders",
  "iat": 1893452400,
  "ath": "base64url-access-token-hash",
  "nonce": "server-provided-nonce"
}
```

DPoP còn quy định JOSE header của proof, bao gồm `typ: dpop+jwt`, thuật toán bất đối xứng được hỗ trợ và thông tin khóa công khai phù hợp. Đây là header parameters, không phải payload claims.

Điểm quan trọng: `jti` trong một DPoP proof nhận diện proof cụ thể, trong khi `jti` trong access token nhận diện access token. Một access token có thể được dùng qua nhiều request, còn proof cần được tạo và xác minh theo quy tắc riêng cho từng request. Không áp dụng chính sách one-time-use của proof lên access token chỉ vì cả hai đều có claim `jti`.

## 8. Claim chuẩn, claim mở rộng và claim riêng của ứng dụng

Không phải mọi claim không nằm trong bảy claim cốt lõi đều là claim tự tạo tùy ý. Có thể phân biệt theo nguồn định nghĩa:

| Ví dụ | Nguồn định nghĩa | Phạm vi sử dụng |
| --- | --- | --- |
| `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti` | RFC 7519 | JWT tổng quát |
| `client_id`, `scope` trong JWT access token | RFC 9068/profile OAuth | JWT access token theo profile |
| `auth_time`, `nonce`, `acr`, `amr`, `azp` | OpenID Connect Core | OIDC ID Token và luồng xác thực OIDC tương ứng |
| `htm`, `htu`, `ath` trong proof | RFC 9449 | DPoP proof JWT |
| `cnf` | RFC 7800 và các profile sử dụng confirmation claim | Ràng buộc token với khóa hoặc thông tin xác nhận |
| `roles`, `groups`, `tenant_id`, `department` | Hợp đồng ứng dụng hoặc profile riêng | Chỉ các bên đã thống nhất mới diễn giải |

Một claim mở rộng có thể được chuẩn hóa trong một RFC hoặc giao thức mà không trở thành yêu cầu chung của mọi JWT. Ví dụ, `auth_time` có ý nghĩa rõ trong OIDC; một hệ thống không dùng OIDC không được tự gán cho nó cùng ngữ nghĩa nếu không có hợp đồng tương ứng.

### Ví dụ claim `roles`

Payload:

```json
{
  "sub": "user-42",
  "roles": ["admin", "auditor"]
}
```

Tên `roles` tự nó không xác định:

- `admin` quản trị toàn hệ thống hay chỉ một tenant.
- Role được kế thừa hay gán trực tiếp.
- Role có hiệu lực trên mọi API hay chỉ một tài nguyên.
- Bên nhận phải kết hợp role với `aud`, `scope` hoặc policy nào.

Các bên phải định nghĩa schema, kiểu dữ liệu, phạm vi, cách cập nhật và cách xử lý khi claim thiếu hoặc không hợp lệ. Nếu claim có ý nghĩa bảo mật, cần xác minh nó từ issuer tin cậy và ràng buộc với đúng loại token/audience.

## 9. Phân biệt payload claims với JOSE header parameters

JWT được bảo vệ bằng JOSE có header riêng và payload chứa claims. Một số tên nhìn giống thông tin của token nhưng nằm ở header, không phải payload.

Ví dụ JWS:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-01"
}
```

Đây là JOSE header:

| Header parameter | Mục đích |
| --- | --- |
| `alg` | Thuật toán bảo vệ mật mã được khai báo trong header; verifier vẫn phải áp dụng allowlist thuật toán riêng |
| `typ` | Loại nội dung/token theo ngữ cảnh JOSE/profile, ví dụ `at+jwt` hoặc `dpop+jwt` |
| `kid` | Gợi ý định danh khóa để lựa chọn khóa trong tập khóa tin cậy |

Chúng không phải payload claims. Ngược lại, `iss`, `sub`, `aud`, `exp`, `iat`, `jti` thường nằm trong payload claims.

Không nhầm `typ` với claim `type` do ứng dụng tự định nghĩa. `typ` là JOSE header parameter; `type` trong payload chỉ có ý nghĩa nếu một profile hoặc ứng dụng quy định.

Header cũng không tự tạo ra niềm tin. Không chọn thuật toán hoặc nguồn khóa tùy ý chỉ vì token tự khai báo `alg`, `kid`, `jku` hay `x5u`; xác minh theo cấu hình và chính sách tin cậy của verifier.

## 10. Cách xác định claim nào cần được kiểm tra

Một validator nên bắt đầu từ loại token và tài nguyên nhận, không bắt đầu bằng việc chấp nhận mọi JWT có chữ ký hợp lệ.

Quy trình tham khảo:

1. **Xác định token type/profile:** access token theo RFC 9068, OIDC ID Token, DPoP proof hay JWT nội bộ.
2. **Xác định issuer và đối tượng nhận kỳ vọng:** cấu hình tin cậy phải đến từ hệ thống quản trị, không lấy từ claim chưa xác minh để tự tạo trust.
3. **Xác minh bảo vệ mật mã:** kiểm tra chữ ký/MAC hoặc JWE theo thuật toán và khóa được phép.
4. **Kiểm tra các claim bắt buộc của profile:** không dùng một danh sách chung cho tất cả loại JWT.
5. **Kiểm tra kiểu và ngữ nghĩa:** `aud` có thể là chuỗi hoặc mảng theo JWT; `scope` có định dạng theo profile; `roles` phải theo schema ứng dụng.
6. **Kiểm tra ngữ cảnh:** token có dành cho API/client hiện tại không, token có đúng loại và đúng mục đích không.
7. **Xử lý claim không biết:** bỏ qua hay từ chối theo profile/hợp đồng; không tự cấp quyền dựa trên claim chưa hiểu.
8. **Áp dụng authorization:** claims đã xác minh là đầu vào cho quyết định quyền, không tự thay thế chính sách kiểm soát truy cập.

### Ví dụ ma trận validator

| Loại token | Kiểm tra cốt lõi | Claim/đặc điểm đặc thù cần xem xét |
| --- | --- | --- |
| JWT tổng quát của ứng dụng | Issuer, chữ ký, thời gian, audience theo hợp đồng | Claim riêng do ứng dụng định nghĩa |
| OAuth JWT access token | Profile RFC 9068, issuer, audience, thời hạn, token type | `client_id`, `jti`, `scope`, `cnf` nếu có |
| OIDC ID Token | OIDC Core, issuer, audience/client ID, thời gian, chữ ký | `nonce`, `auth_time`, `azp`, `acr`, `amr` theo điều kiện |
| DPoP proof JWT | RFC 9449, proof signature/key, method, URI, thời gian | `jti`, `htm`, `htu`, `ath`, `nonce` theo trường hợp |

## 11. Cách thiết kế claim riêng an toàn

Khi ứng dụng cần thêm thông tin ngoài claim đã được chuẩn hóa, cần thiết kế hợp đồng rõ ràng.

### Chọn tên có namespace

- Với claim công khai hoặc cần chia sẻ giữa nhiều tổ chức, ưu tiên tên collision-resistant theo hướng dẫn RFC 7519.
- Với claim private, chỉ dùng khi các bên kiểm soát và thống nhất hợp đồng; tránh trùng với tên chuẩn hoặc tên của giao thức khác.
- Không tái sử dụng tên claim chuẩn để gán ý nghĩa khác.

### Định nghĩa schema và ngữ nghĩa

Với mỗi claim riêng, cần xác định:

- Kiểu dữ liệu: string, number, boolean, array hoặc object.
- Ý nghĩa và đơn vị của giá trị.
- Phạm vi: subject, tenant, client, resource hay toàn hệ thống.
- Nguồn dữ liệu và bên có quyền phát hành.
- Claim bắt buộc hay tùy chọn trong từng token profile.
- Quy tắc xác minh, giá trị hợp lệ và hành vi khi thiếu/sai kiểu.
- Phiên bản schema và cách tương thích khi thay đổi.

Ví dụ một hợp đồng claim:

```json
{
  "https://claims.example.com/tenant_id": "tenant-17",
  "https://claims.example.com/roles": ["invoice-reader", "invoice-approver"],
  "https://claims.example.com/permissions_version": 4
}
```

Hợp đồng cần định nghĩa rõ `tenant_id` thuộc issuer nào, role có phạm vi tenant hay toàn cục, và `permissions_version` được dùng ra sao. Không suy diễn quyền chỉ từ tên trường.

### Không đưa dữ liệu nhạy cảm không cần thiết

Payload JWS thường có thể đọc được bởi bất kỳ ai có token; Base64URL không phải mã hóa bí mật. Chỉ đưa các claims cần thiết cho bên nhận và tránh đưa mật khẩu, khóa bí mật, dữ liệu cá nhân quá mức hoặc thông tin không cần thiết. Nếu cần bảo mật nội dung, phải dùng cơ chế mã hóa phù hợp và vẫn đánh giá rủi ro lưu trữ/truyền token.

## 12. Xử lý claim không biết hoặc không hỗ trợ

Một JWT có thể chứa claim mở rộng mà verifier chưa biết. Hành vi đúng phụ thuộc vào giao thức và vai trò của claim đó.

- Nếu claim chỉ mang thông tin bổ sung không ảnh hưởng quyết định bảo mật, verifier có thể bỏ qua theo hợp đồng/profile.
- Nếu claim là bắt buộc theo profile, thiếu claim phải bị từ chối.
- Nếu hệ thống cần claim để xác định tenant, audience, quyền hoặc ràng buộc khóa mà không hiểu được claim, không được tiếp tục xử lý như thể điều kiện đã đạt.
- Nếu hai bên dùng cùng tên claim nhưng khác schema/ý nghĩa, cần versioning hoặc namespace để tránh diễn giải nhầm.
- Không tự coi claim không biết là quyền bổ sung, cũng không tự ánh xạ một giá trị lạ sang role quen thuộc.

JWT không có một cơ chế payload claim tổng quát khiến mọi claim lạ tự động trở thành “critical”. Vì vậy, profile phải định nghĩa rõ claim nào là thiết yếu và verifier phải biết cách xử lý khi không hỗ trợ chúng. Cơ chế `crit` của JOSE áp dụng cho header parameters theo quy tắc JOSE, không phải một cách đánh dấu tùy ý cho mọi payload claim.

## 13. Ngăn nhầm lẫn giữa các loại JWT

Một hệ thống có thể dùng nhiều loại JWT: access token, ID Token, DPoP proof, assertion nội bộ hoặc token trao đổi giữa dịch vụ. Tất cả có thể dùng chung cấu trúc JWT và một số claim tên giống nhau, nhưng mục đích khác nhau.

Rủi ro xuất hiện khi verifier chỉ kiểm tra chữ ký rồi dùng một JWT cho sai ngữ cảnh. Ví dụ:

- API nhận ID Token như access token.
- Client dùng access token như bằng chứng đăng nhập người dùng.
- Resource server nhận DPoP proof như access token.
- JWT của một issuer hoặc audience được dùng tại tài nguyên khác.

Các biện pháp:

1. Dùng profile rõ ràng cho từng loại token.
2. Kiểm tra `typ` ở JOSE header khi profile yêu cầu.
3. Ràng buộc issuer, audience và tập khóa với đúng loại token.
4. Xác minh các claim bắt buộc và điều kiện riêng của profile.
5. Không tái sử dụng một validator lỏng cho tất cả JWT chỉ vì chúng có chung định dạng.
6. Nếu dùng cùng issuer cho nhiều loại token, vẫn phải phân biệt token type, audience và ngữ nghĩa claims.

Đây là một phần của nguyên tắc **explicit typing** và phân tách ngữ cảnh token trong [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).

## 14. Ví dụ tổng hợp: cùng một claim name nhưng khác bối cảnh

| Claim | Trong JWT tổng quát | Trong giao thức/profile | Điều verifier cần làm |
| --- | --- | --- | --- |
| `sub` | Chủ thể của JWT | OIDC: subject identifier của người dùng; RFC 9068: subject của access token | Diễn giải trong phạm vi issuer và profile |
| `aud` | Đối tượng nhận dự kiến | OIDC ID Token: client; access token: resource server/API | So khớp với đúng loại recipient của token |
| `iat` | Thời điểm phát hành | OIDC ID Token/access token: thời điểm phát hành token tương ứng | Không nhầm với thời điểm người dùng đăng nhập (`auth_time`) |
| `jti` | ID của JWT | Access token: ID của token; DPoP: ID của proof | Áp dụng replay/revocation theo đúng đối tượng |
| `nonce` | Không phải một trong bảy registered claims cốt lõi của RFC 7519 | OIDC: liên kết ID Token với Authentication Request; DPoP: challenge theo giao thức | Kiểm tra theo giao thức và đúng luồng |
| `scope` | Không phải claim cốt lõi của RFC 7519 | OAuth JWT access token: phạm vi quyền được biểu diễn theo profile | Không coi scope là audience hoặc tự động cấp quyền ngoài policy |
| `roles` | Không có ngữ nghĩa chung được RFC 7519 định nghĩa | Thường do ứng dụng/nhà cung cấp định nghĩa | Kiểm tra schema, issuer, phạm vi và mapping đã thống nhất |

Điểm quan trọng là không diễn giải claim độc lập khỏi token type. Cùng tên `sub` hoặc `aud` có thể xuất hiện trong nhiều loại token nhưng bên nhận kỳ vọng khác nhau.

## 15. Checklist khi tích hợp một loại JWT mới

Trước khi chấp nhận JWT từ một issuer hoặc giao thức mới, hãy xác định:

| Câu hỏi | Điều cần làm rõ |
| --- | --- |
| Token thuộc loại nào? | Access token, ID Token, DPoP proof hay JWT riêng |
| Đặc tả nào định nghĩa token? | RFC, OIDC Core, profile hoặc hợp đồng ứng dụng |
| Issuer nào được tin cậy? | Giá trị `iss` kỳ vọng và nguồn khóa tin cậy |
| Audience nào được chấp nhận? | Định danh resource server hoặc client theo profile |
| Claim nào bắt buộc? | Danh sách claim, kiểu dữ liệu và điều kiện bắt buộc |
| Claim nào chỉ tùy chọn? | Hành vi khi thiếu claim và khi có giá trị không hỗ trợ |
| Claim nào là protocol-specific? | Quy tắc ngữ nghĩa và validation theo giao thức |
| Claim riêng có namespace không? | Tránh xung đột tên và định nghĩa schema |
| Header parameters nào cần kiểm tra? | `typ`, `alg`, `kid` và quy tắc JOSE liên quan |
| Unknown claims được xử lý thế nào? | Bỏ qua hay từ chối theo profile và vai trò bảo mật |
| Quyền được quyết định ra sao? | Ánh xạ claims sang authorization policy đã định nghĩa |
| Token có thể bị nhầm với loại khác không? | Kiểm tra explicit typing, issuer, audience và mục đích |

## 16. Nguyên tắc cần ghi nhớ

1. JWT là định dạng chứa claims; không phải mọi claim đều được định nghĩa bởi RFC 7519.
2. RFC 7519 phân biệt registered, public và private claim names.
3. Bảy registered claims cốt lõi là `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`; chúng tùy chọn trong JWT tổng quát trừ khi profile yêu cầu.
4. “Registered claim” và “protocol-defined claim” mô tả hai khía cạnh khác nhau; một claim giao thức có thể đồng thời được đăng ký.
5. OAuth JWT access token, OIDC ID Token và DPoP proof có tập claim và quy tắc riêng; không dùng chung một validator lỏng.
6. JOSE header parameters như `alg`, `typ`, `kid` không phải payload claims.
7. Claim riêng cần namespace, schema, ý nghĩa, kiểu dữ liệu và chính sách xác minh rõ ràng.
8. Không suy diễn ý nghĩa hoặc quyền chỉ từ tên claim; cùng tên có thể có phạm vi khác nhau giữa các profile.
9. Xử lý claim lạ theo giao thức; claim thiết yếu không hiểu được phải dẫn đến từ chối thay vì bỏ qua.
10. Xác minh bảo vệ mật mã, issuer, audience, token type và các claim bắt buộc trước khi sử dụng claims cho authorization.

### Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT), mục 4 và 10.1](https://www.rfc-editor.org/rfc/rfc7519): registered, public, private claim names và đăng ký claim.
- [IANA — JSON Web Token Claims Registry](https://www.iana.org/assignments/jwt/jwt.xhtml#claims): danh mục tên claim đã đăng ký và đặc tả tham chiếu.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claim và quy tắc riêng của JWT access token.
- [OpenID Connect Core 1.0, mục 2 và 3.1.3.7](https://openid.net/specs/openid-connect-core-1_0.html#IDToken): ID Token và các claim xác thực OIDC.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): claim và header của DPoP proof JWT.
- [RFC 7800 — Proof-of-Possession Key Semantics for JSON Web Tokens](https://www.rfc-editor.org/rfc/rfc7800): confirmation claim `cnf` và ràng buộc token với khóa.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): explicit typing, phân tách ngữ cảnh và thực hành xác minh JWT.

**Kết luận:** Claim chuẩn của JWT cung cấp ngữ nghĩa chung cho định dạng token; claim của giao thức/profile bổ sung ý nghĩa và điều kiện sử dụng trong một luồng cụ thể; claim riêng của ứng dụng cần hợp đồng rõ ràng để tránh xung đột và hiểu nhầm. Luôn xác định loại token và đặc tả áp dụng trước khi quyết định claim nào bắt buộc, cách xác minh và cách dùng chúng cho authorization.
