# Registered, public và private claim

Một JWT có thể chứa dữ liệu như `sub`, `exp`, `scope`, `tenant_id` hoặc `https://example.com/claims/department`. Nhìn qua, tất cả đều là các cặp khóa–giá trị JSON. Nhưng **nguồn định nghĩa tên, kiểu dữ liệu và ngữ nghĩa** của từng claim khác nhau; nếu một API hiểu sai chúng, hệ thống có thể xác thực nhầm danh tính, chấp nhận token dành cho ứng dụng khác hoặc cấp quyền quá mức.

Trong chương **Claims** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài này giải thích ba nhóm tên claim theo RFC 7519: **registered**, **public** và **private**. Trọng tâm là cách chọn tên, đọc đúng hợp đồng, xác minh claims khi dùng JWT trong xác thực/phân quyền và OAuth 2.0/OpenID Connect (OIDC), đồng thời hạn chế lộ dữ liệu và rủi ro token bị đánh cắp hoặc phát lại.

Sau khi học, bạn có thể:

- Phân biệt **JWT Claim Name**, giá trị claim, nhóm registered/public/private và quan hệ giữa chúng với registry IANA.
- Giải thích đúng ngữ nghĩa của `iss`, `sub`, `aud`, `exp`, `nbf`, `iat` và `jti`.
- Quyết định khi nào sử dụng tên claim chuẩn, tên public chống xung đột hoặc private claim theo hợp đồng riêng.
- Tách claims định danh, claims của OAuth access token, claims OIDC ID token và claims phân quyền theo nghiệp vụ.
- Viết logic kiểm tra schema, nguồn phát hành, audience, thời hạn và quyền; tránh nhầm JWT đã giải mã với JWT đã xác minh.
- Nhận diện các lỗi thường gặp: đụng tên claim, dùng `role`/`tenant_id` không có hợp đồng, nhận ID token làm access token, tin claims do client tự gửi hoặc đưa dữ liệu nhạy cảm vào JWT.

## 1. Claim là gì và được dùng ở đâu?

Một **claim** là một phát biểu (statement) được biểu diễn dưới dạng cặp **tên–giá trị** trong **JWT Claims Set**, tức JSON object đóng vai trò payload của JWT. Ví dụ:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "exp": 1795000900,
  "scope": "orders.read",
  "tenant_id": "store-a"
}
```

Từng claim mang một ý nghĩa khác nhau:

- `iss` nói **ai là bên phát hành**; `aud` nói token **dành cho bên nhận nào**.
- `sub` định danh **chủ thể** theo ngữ cảnh issuer; không nhất thiết là email hoặc user ID toàn cục.
- `exp` quy định **thời điểm hết hạn**.
- `scope` trong hợp đồng OAuth access token thường diễn tả **phạm vi quyền** mà token được cấp.
- `tenant_id` có thể là thuộc tính riêng của hệ thống đa tenant; bản thân RFC 7519 không chuẩn hóa tên hay ý nghĩa của claim này.

**Tên claim và giá trị claim là hai thứ khác nhau.** Việc đặt tên `roles` không tự biến giá trị thành quyền chuẩn, và việc một JSON object có trường `exp` không chứng minh nó đã được phát hành bởi issuer tin cậy. Ý nghĩa và tính đáng tin phụ thuộc vào **hợp đồng giữa issuer và bên tiêu thụ** cộng với xác minh token đúng cách.

JWT có thể được ký (JWS) hoặc mã hóa (JWE); JWT ký compact thông dụng có ba phần phân tách bằng dấu chấm, còn JWT mã hóa compact có năm phần. Với JWS, payload được mã hóa Base64URL để biểu diễn, **không được bảo mật nội dung bằng mã hóa**. Bất kỳ ai giữ token ký thông thường đều có thể đọc payload, dù không sửa được mà vẫn giữ chữ ký hợp lệ.

## 2. Ba nhóm tên claim trong RFC 7519

RFC 7519 `4 chia **JWT Claim Names** thành ba nhóm. Nhóm này phân biệt **cách một tên được xác định và quản lý**, không xếp hạng độ tin cậy hay quyền của token.

| Nhóm | Nguồn định nghĩa và phạm vi sử dụng | Ví dụ | Điều cần nhớ |
| --- | --- | --- | --- |
| **Registered Claim Names** | Bảy tên được JWT định nghĩa trực tiếp trong RFC 7519 `4.1 | `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti` | Ngữ nghĩa đã được chuẩn hóa; việc claim nào bắt buộc tùy profile/hợp đồng |
| **Public Claim Names** | Tên do các bên định nghĩa công khai, nên **đăng ký trong IANA JWT Claims Registry** hoặc dùng tên chống xung đột (collision-resistant) | `https://example.com/claims/department`; tên được đặc tả/đăng ký bởi chuẩn mở rộng | Tránh đụng tên và mô tả rõ kiểu/ý nghĩa |
| **Private Claim Names** | Tên riêng theo thỏa thuận giữa bên phát hành và bên tiêu thụ, không cần là một chuẩn dùng chung | `tenant_id`, `internal_roles`, `subscription_plan` nếu hệ thống tự quy ước | Có thể đụng tên; chỉ có ý nghĩa khi các bên cùng hiểu hợp đồng |

**Phân biệt tinh tế:** RFC 7519 gọi bảy tên ở `4.1 là *Registered Claim Names*. Ngoài bảy tên ấy, **IANA JWT Claims Registry** còn có thể đăng ký các claim được định nghĩa bởi tiêu chuẩn khác (ví dụ claims dùng cho OAuth/OIDC). Vì vậy không nên hiểu “có trong IANA” đồng nghĩa “thuộc đúng bảy Registered Claim Names của `4.1”. Một tên được chuẩn hóa bên ngoài RFC 7519 có thể thuộc tập tên public theo cách phân loại bài học, dù được ghi trong registry IANA.

RFC 7519 không yêu cầu mọi JWT phải mang cả bảy registered claims. Tuy nhiên **profile sử dụng token cụ thể có thể đặt yêu cầu mạnh hơn**. Ví dụ một JWT access token theo profile RFC 9068 có các yêu cầu riêng mà một JWT dùng cho mục đích khác không nhất thiết có.

### Nhóm claim có nói claim “an toàn” hơn không?

Không. `exp` thuộc nhóm registered vẫn có thể bị giả mạo trong JWT không có chữ ký tin cậy. Một private claim `tenant_id` có thể rất quan trọng nếu API và authorization server có hợp đồng rõ ràng, nhưng cũng có thể bị diễn giải sai nếu API nhận claim từ issuer khác. **Độ tin cậy đến từ xác minh issuer/token và chính sách nghiệp vụ**, không phải nhãn registered, public hay private.

## 3. Registered claims: bảy tên và ngữ nghĩa

| Claim | Tên đầy đủ | Ý nghĩa | Kiểu dữ liệu theo RFC 7519 | Ví dụ |
| --- | --- | --- | --- | --- |
| `iss` | Issuer | Bên phát hành JWT | `StringOrURI` | `https://auth.example.com` |
| `sub` | Subject | Chủ thể mà JWT nói đến | `StringOrURI` | `user-42` |
| `aud` | Audience | Những bên nhận mà JWT hướng tới | Một string hoặc mảng string | `https://api.example.com/orders` |
| `exp` | Expiration Time | Từ thời điểm này JWT không còn được chấp nhận | `NumericDate` | `1795000900` |
| `nbf` | Not Before | Thời điểm sớm nhất token có thể được chấp nhận | `NumericDate` | `1795000000` |
| `iat` | Issued At | Thời điểm JWT được phát hành | `NumericDate` | `1795000000` |
| `jti` | JWT ID | Định danh duy nhất của JWT theo mục đích phát hành | String | `5f6b...` |

Trong RFC 7519, `StringOrURI` là JSON string; khi chứa dấu hai chấm (`:`), giá trị phải tuân theo cú pháp URI. **Không được tự ý chuẩn hóa, đổi chữ hoa/thường hoặc sửa URI khi so khớp issuer/audience** nếu hợp đồng định danh đòi chính xác. Các token thuộc issuer khác nhau có thể cùng `sub=user-42` nhưng nói về hai chủ thể khác nhau.

### 3.1. `iss` — issuer

`iss` trả lời: **Ai khẳng định những claims này?** Resource server phải tin issuer theo cấu hình trước, xác minh chữ ký với khóa tin cậy gắn với issuer đó và so sánh `iss` theo hợp đồng. Không chỉ lấy `iss` từ token chưa xác minh rồi tự động tin mọi JWKS URL do token trỏ tới.

Ví dụ API chỉ tin `https://login.company.example`; token chứa `iss=https://random.example` phải bị từ chối dù chữ ký có hợp lệ với khóa do hệ thống lạ cung cấp.

### 3.2. `sub` — subject

`sub` là **định danh chủ thể**, không mặc định là email, tên đăng nhập hoặc user ID dạng số. Trong token người dùng, `sub` có thể là ID ổn định của người dùng tại issuer. Với một số loại token S2S, `sub` có thể nói về client/workload theo token profile, không phải con người.

Khi liên kết danh tính giữa nhiều issuer, cần đối chiếu cặp **(issuer, subject)** hoặc cơ chế định danh liên kết được tổ chức chấp thuận. Không nối dữ liệu hai người chỉ vì cả hai token có cùng `sub`. Nếu muốn hiển thị email, có thể dùng claim email riêng nhưng **email không thay thế định danh ổn định**, vì email có thể đổi hoặc tái sử dụng.

### 3.3. `aud` — audience

`aud` xác định bên nhận được token hướng tới. Một API chỉ được chấp nhận token khi **chính API đó nằm trong audience hợp lệ** theo hợp đồng token. Theo RFC 7519, khi có nhiều audience, claim có thể là **mảng string**; với một audience duy nhất, JWT có thể dùng string.

```json
{
  "aud": ["https://api.example.com/orders", "https://api.example.com/invoices"]
}
```

Một verifier chỉ chấp nhận `aud` dạng string có thể từ chối token hợp lệ ở dạng mảng nếu profile cho phép. Ngược lại, parser lỏng lẻo nhận chuỗi `"orders invoices"` như danh sách audience mà không có đặc tả có thể mắc lỗi. Thiết kế an toàn nên **hỗ trợ đúng dạng được profile cho phép và so khớp exact identifiers**.

Không nên phát token có audience rộng không cần thiết, vì nó mở rộng phạm vi bên có thể chấp nhận bản sao token. Với OAuth Resource Indicators (RFC 8707), client có thể yêu cầu tài nguyên đích; authorization server quyết định cách ánh xạ request thành audience của access token.

### 3.4. `exp`, `nbf`, `iat` — thời gian

Ba claims này dùng kiểu **NumericDate**: số biểu thị số giây kể từ epoch Unix 1970-01-01T00:00:00Z, theo định nghĩa RFC, không phải mili-giây JavaScript. Có thể là số không nguyên trong cú pháp NumericDate, dù nhiều hệ thống sử dụng giây nguyên.

- `exp`: thời điểm hiện tại **phải trước** thời điểm hết hạn; tức token hết hiệu lực khi `now >= exp` (trừ biên lệch đồng hồ nhỏ được policy cho phép).
- `nbf`: token **chưa được chấp nhận trước** thời điểm `nbf`; nghĩa là `now >= nbf`.
- `iat`: thời điểm phát hành; hữu ích khi kiểm tra token được phát hành quá xa trong tương lai/quá cũ theo chính sách. **Không đồng nghĩa thời điểm người dùng vừa đăng nhập hoặc vừa hoàn thành MFA**.

Ví dụ:

```json
{
  "iat": 1795000000,
  "nbf": 1795000000,
  "exp": 1795000900
}
```

Nếu thời gian hiện tại lớn hơn hoặc bằng `1795000900`, token hết hiệu lực theo `exp`. Backend thường cấu hình **clock skew nhỏ và có giới hạn** để xử lý sai lệch đồng hồ, tránh cho phép token quá hạn lâu. Cũng phải giới hạn **tuổi thọ tối đa** nếu policy yêu cầu, vì một token có `exp` rất xa vẫn không phù hợp nguyên tắc đặc quyền tối thiểu.

### 3.5. `jti` — định danh JWT

`jti` là identifier dành cho JWT, thường giúp audit, phát hiện dùng lại trong những giao thức yêu cầu một lần, hoặc đối chiếu denylist. RFC yêu cầu cách sinh `jti` giảm xác suất trùng và tránh trùng giữa issuers nếu được sử dụng trong phạm vi nhiều issuer.

Sự hiện diện của `jti` **không tự động chống replay**. Resource server phải có chính sách hoặc trạng thái để từ chối `jti` bị thu hồi/đã dùng, hoặc dùng cơ chế ràng buộc khóa như DPoP/mTLS theo trường hợp. Nhiều access token bearer hợp lệ được phép dùng lặp lại trong TTL; không thể cứ thấy cùng `jti` lần thứ hai là từ chối mọi request nếu giao thức không thiết kế như vậy.

## 4. Public claim: tên có thể chia sẻ mà không đụng nhau

**Public Claim Names** hữu ích khi một claim được nhiều service, tổ chức hoặc nhà cung cấp cùng sử dụng. Theo RFC 7519 `4.2, người định nghĩa nên:

1. **Đăng ký tên trong IANA JSON Web Token Claims Registry** theo quy trình phù hợp, hoặc
2. Dùng **Collision-Resistant Name** – tên tạo bằng không gian tên có khả năng tránh xung đột, thường dựa trên URI/namespace mà bên định nghĩa kiểm soát.

Ví dụ bên phát hành kiểm soát namespace `https://example.com/claims/`:

```json
{
  "https://example.com/claims/department": "operations",
  "https://example.com/claims/cost_center": "cost-center-17"
}
```

Tên claim là **một chuỗi JSON nguyên vẹn**. `https://example.com/claims/department` không có nghĩa resource server phải GET URL đó để đọc giá trị, cũng không phải URL API đích. URI trong tên là cách biểu diễn namespace, thường **không cần truy cập mạng**. Các bên cần thống nhất owner của namespace, tên chính xác, kiểu dữ liệu, ý nghĩa, phiên bản và chính sách bảo mật.

Một số hệ thống chọn URI có cấu trúc như `urn:example:claims:department` hoặc dùng domain tổ chức kiểm soát. Cách đặt tên cụ thể phải tránh đụng với chuẩn và giữa các đội nhóm. Không dùng tên tùy ý trông giống domain của bên khác hoặc “chiếm” những prefix mà mình không quản lý.

### Public có đồng nghĩa với “mọi người được xem” không?

**Không.** “Public” ở đây nói về **khả năng định nghĩa tên và tránh xung đột**, không phải phân loại bảo mật của **giá trị**. Một public claim có thể mang thông tin nhạy cảm, và không nên phát hành rộng chỉ vì tên của nó thuộc namespace công khai.

### Public claim có bắt buộc phải là URI?

Không tuyệt đối. RFC cho phép **đăng ký tên trong IANA registry** hoặc dùng tên collision-resistant. URI/URL namespace là một kỹ thuật phổ biến để đạt tính collision-resistant; tên đã đăng ký có thể là chuỗi ngắn theo đặc tả. Không tự biến mọi tên ngắn thành public claim chuẩn.

## 5. Private claim: thỏa thuận riêng giữa issuer và consumer

**Private Claim Names** là các tên do bên phát hành và bên tiêu thụ đồng thuận dùng trong một hệ thống hoặc liên kết cụ thể. Chúng tiện lợi nhưng có nguy cơ **collision** khi trộn token từ các issuer, thư viện hoặc hệ thống khác nhau.

Ví dụ:

```json
{
  "tenant_id": "tenant-a",
  "roles": ["sales-agent", "order-viewer"],
  "feature_flags": ["new-checkout"],
  "employee_level": 3
}
```

Nếu đây là claims do tổ chức tự đặt và chưa có đặc tả/namespace công khai áp dụng, có thể xem chúng là **private claims theo hợp đồng nội bộ**. Trong hệ thống khác, cùng tên `roles` có thể là string, mảng, hoặc các giá trị có ngữ nghĩa hoàn toàn khác.

Ví dụ xung đột:

| Issuer/hợp đồng | `roles` | Ý nghĩa |
| --- | --- | --- |
| Authorization server A | `["admin"]` | Quyền quản trị của chính hệ thống A |
| Authorization server B | `["admin"]` | Người quản trị giao diện khách hàng của hệ thống B |
| Client tự khai | `["admin"]` | Dữ liệu không đáng tin do client gửi |

Nếu API trộn các claims mà không xác minh issuer, audience và semantics, một `admin` của hệ thống B có thể bị hiểu là quyền quản trị của hệ thống A. **Tên claim giống nhau không có nghĩa quyền giống nhau.**

Khi private claim bắt đầu được chia sẻ cho nhiều đối tác hoặc nhiều product team, nên cân nhắc **đưa về namespace collision-resistant** hoặc chuẩn hóa hợp đồng rõ ràng để giảm rủi ro chuyển đổi.

### Private claim có được dùng để phân quyền không?

Có, **nếu** API chỉ tin claim từ issuer được ủy quyền phát hành và cả hai bên thống nhất schema, kiểu, ngữ nghĩa, trạng thái hiệu lực và cơ chế thay đổi. Tuy nhiên:

- `roles` hay `permissions` không tự thay thế kiểm tra quyền trên từng đối tượng (owner, tenant, dữ liệu hiện hành).
- Role bị thu hồi có thể vẫn xuất hiện trong JWT chưa hết hạn; cần TTL/tra cứu policy/trạng thái phiên phù hợp.
- Đặc quyền tối thiểu yêu cầu chỉ đưa quyền cần thiết vào token dành cho API đó.
- Không cho client tự đưa `X-Role: admin` hoặc `tenant_id` rồi dùng như quyền hệ thống.

## 6. Claim chuẩn từ OAuth/OIDC có thuộc bảy registered claims không?

Đây là nguồn nhầm lẫn phổ biến. Một JWT access token hoặc OIDC ID token thường có **nhiều hơn bảy claim chuẩn của RFC 7519**. Các claims mở rộng có thể được đặc tả trong RFC hoặc tài liệu OIDC và đăng ký trong IANA, nhưng **không vì thế trở thành một trong bảy claims `4.1 của RFC 7519**.

| Claim | Ngữ cảnh thường gặp | Ai định nghĩa/ý nghĩa thực tế | Có thuộc bảy RFC 7519 `4.1 không? |
| --- | --- | --- | --- |
| `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti` | JWT nói chung | RFC 7519 | **Có** |
| `scope` | OAuth JWT access token | Profile/hợp đồng access token; thường là chuỗi scope cách nhau bằng dấu cách | Không |
| `client_id` | OAuth access token | Định danh OAuth client theo profile token | Không |
| `auth_time` | OIDC ID token | Thời điểm người dùng được xác thực | Không |
| `amr` | OIDC ID token | Phương thức xác thực đã dùng, mảng reference values | Không |
| `acr` | OIDC ID token | Ngữ cảnh/lớp đảm bảo xác thực theo hợp đồng | Không |
| `nonce` | OIDC ID token | Liên kết authentication response với yêu cầu client theo quy tắc OIDC | Không |
| `cnf` | Sender-constrained token | Thông tin khóa/chứng chỉ xác nhận bên gửi theo profile áp dụng | Không |
| `roles`, `tenant_id` | Hệ thống nghiệp vụ tùy biến | Có thể là private hoặc namespace public tùy hợp đồng | Không, trừ khi có chuẩn riêng cho tên cụ thể |

Vì vậy, câu hỏi “`scope` là registered hay private?” cần **xác định đang nói về `4.1 của RFC 7519, registry IANA, hay hợp đồng token OAuth**. `scope` không thuộc bảy tên RFC `4.1, nhưng là claim có ngữ nghĩa được chuẩn hóa trong ngữ cảnh token profile liên quan; không nên coi nó như một trường private có thể tự định nghĩa lại tùy ý nếu hệ thống tuân theo profile đó.

OIDC ID token thường dùng `aud` là **OIDC client ID**; OAuth access token dùng `aud` là **resource server/API**. Các claims giống tên nhưng **loại token và đối tượng nhận khác nhau**, nên API không được dùng ID token để thay access token.

## 7. Ví dụ JWT access token kết hợp nhiều nhóm claim

Payload minh họa (giả định authorization server phát hành JWT access token theo hợp đồng cho Orders API):

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "exp": 1795000900,
  "nbf": 1795000000,
  "iat": 1795000000,
  "jti": "f42e7120-8fa2-47f1-9f11-cdd31e9fb640",
  "client_id": "orders-web-client",
  "scope": "orders.read orders.update",
  "https://example.com/claims/tenant": "tenant-a",
  "internal_roles": ["sales-agent"]
}
```

Đọc theo nhóm:

1. **Registered (`4.1):** `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`.
2. **Chuẩn mở rộng/hợp đồng OAuth:** `client_id` và `scope` (không thuộc bảy tên `4.1).
3. **Public dạng collision-resistant:** `https://example.com/claims/tenant`.
4. **Private theo hợp đồng:** `internal_roles`.

Ví dụ header JWT access token ký JWS:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-01"
}
```

`typ` là **JOSE header parameter**, không phải claim trong payload. Giá trị `at+jwt` được profile JWT access token dùng để tách loại token; API vẫn phải xác minh **chữ ký, issuer, audience, thời hạn và policy**, không tin `typ` khi chưa xác minh toàn bộ token. `kid` giúp chọn khóa trong tập khóa đáng tin đã cấu hình, **không phải giấy phép tải khóa tùy ý** từ URL do token tự đề xuất.

Ngay cả token có `scope=orders.update` và `internal_roles=["sales-agent"]`, API cũng phải kiểm tra đơn hàng thực tế có thuộc user/tenant hợp lệ và thao tác sửa trường có được phép không. Claims là **đầu vào cho quyết định phân quyền**, không tự thay thế policy nghiệp vụ.

## 8. Ví dụ ID token OIDC: cùng claims, mục đích khác

Payload ID token minh họa:

```json
{
  "iss": "https://login.example.com",
  "sub": "user-42",
  "aud": "orders-web-client",
  "exp": 1795000900,
  "iat": 1795000000,
  "auth_time": 1794999900,
  "amr": ["pwd", "otp"],
  "acr": "urn:example:assurance:mfa",
  "nonce": "random-nonce-bound-to-client-request"
}
```

OIDC client xác minh ID token theo hợp đồng OIDC và luồng được dùng, gồm chữ ký, `iss`, `aud`/client ID, `exp`, `iat`, `nonce` khi áp dụng và các yêu cầu profile khác. `auth_time` là thời điểm người dùng được xác thực, **không đồng nghĩa** `iat` là thời điểm ID token được phát hành. `amr` liệt kê phương thức xác thực theo định nghĩa tương ứng; `acr` chỉ có ý nghĩa assurance khi client và OP thống nhất quy ước.

Đặc biệt, resource server `https://api.example.com/orders` **không phải audience** trong ví dụ ID token. Dù token có `sub` và `amr` đúng, API Orders không được nhận ID token làm bearer access token. Nếu API cần biết MFA đủ mới, hệ thống phải truyền ngữ cảnh từ thành phần đáng tin bằng access token claims theo hợp đồng, tra cứu phiên hoặc cơ chế phù hợp; không tin client tự gửi `{"mfa": true}`.

## 9. Cách đặt tên public/private claim để không gây hiểu nhầm

Thiết kế claim mới nên bắt đầu từ **câu hỏi nghiệp vụ và bên tiêu thụ**: API nào đọc, cần giá trị này để làm gì, ai có quyền phát hành, mức nhạy cảm và khả năng thay đổi.

Một hợp đồng claim tốt mô tả:

| Thuộc tính | Ví dụ |
| --- | --- |
| **Tên canonical** | `https://example.com/claims/tenant` |
| **Chủ sở hữu định nghĩa** | Nhóm identity/platform quản lý namespace |
| **Kiểu JSON** | String |
| **Ý nghĩa** | Tenant mà token đại diện trong hợp đồng Orders API |
| **Giá trị hợp lệ** | ID tenant ổn định theo chuẩn định danh nội bộ |
| **Issuer được phép phát hành** | `https://auth.example.com` |
| **Audience được phép sử dụng** | `https://api.example.com/orders` |
| **Tính bắt buộc** | Bắt buộc cho endpoint tenant-specific, không nhất thiết cho mọi token |
| **Quy tắc lỗi** | Thiếu/sai kiểu/sai tenant thì từ chối, không tự suy đoán |
| **Bảo mật và phiên bản** | Không đặt dữ liệu nhạy cảm, quy tắc thay đổi schema đã thống nhất |

### Nên chọn tên nào?

- Nếu một claim chuẩn trong **profile mà hệ thống tuân thủ** đã đáp ứng nhu cầu, dùng đúng tên và semantics chuẩn.
- Nếu claim được chia sẻ giữa nhiều tổ chức/sản phẩm, cân nhắc đăng ký/khai thác namespace public chống collision.
- Nếu chỉ dùng nội bộ giữa issuer và một vài service, private claim có thể đơn giản hơn, nhưng cần **contract** và kiểm tra chặt.
- Đừng tự tái định nghĩa `sub` thành tenant ID, `aud` thành role, `exp` thành thời gian tính bằng mili-giây hay `scope` thành một object nếu profile yêu cầu chuỗi.
- Tránh đưa phiên bản vào tên mỗi khi có thay đổi nhỏ nếu có cách duy trì tương thích; khi ngữ nghĩa thực sự đổi, phải quản lý migration giữa issuer và consumer.

### Đụng tên claim trong hệ thống đa issuer

Giả sử issuer A định nghĩa `department` là **mã phòng ban số**, issuer B định nghĩa `department` là **tên phòng ban string**. Gateway trộn claim vào cùng mô hình đối tượng rồi gọi API có thể đưa ra quyết định sai. Biện pháp:

1. Xác minh **issuer và token profile** trước khi ánh xạ claims.
2. Tạo mapping theo từng issuer, chuyển sang **internal principal model** có schema rõ ràng.
3. Chỉ cho phép trường hợp định nghĩa đã thống nhất; từ chối dữ liệu bất thường thay vì ép kiểu tùy tiện.
4. Dùng namespace public khi cần chia sẻ hợp đồng trên nhiều hệ thống.

## 10. Xác minh claim: đọc JSON chỉ là bước đầu

Một JWT được giải mã từ Base64URL **chưa đáng tin**. Client có thể tự tạo chuỗi ba phần, đặt `role=admin` và `exp` còn xa. API chỉ được dùng claims sau khi **kiểm tra token theo nguồn đáng tin và profile sử dụng**.

Với JWT access token, quy trình kiểm tra điển hình:

1. **Chọn hợp đồng:** API chỉ chấp nhận loại **access token** của các issuer đã cấu hình; không chấp nhận ID token hoặc refresh token.
2. **Xác minh mật mã:** xác minh JWS signature bằng khóa hợp lệ của issuer, chọn thuật toán theo **allowlist** đã cấu hình; không chấp nhận `alg=none` hoặc khóa từ header tùy ý.
3. **Xác minh nguồn:** so khớp `iss` chính xác với issuer tin cậy; chọn JWKS đã được cấu hình/liên kết an toàn.
4. **Xác minh người nhận:** `aud` chứa định danh đúng của API, trong kiểu và hình dạng profile cho phép.
5. **Xác minh thời gian:** `exp`, `nbf`, `iat` theo profile; xử lý clock skew nhỏ, TTL tối đa và thời điểm tương lai bất thường theo policy.
6. **Xác minh schema:** kiểu dữ liệu, sự hiện diện các claim bắt buộc, độ dài/số phần tử, namespace, duplicate keys và phiên bản hợp đồng.
7. **Xác minh quyền:** scope/role/custom claims theo hợp đồng issuer–API và **quyền trên object/tenant** dựa trên dữ liệu hiện hành.
8. **Xác minh điều kiện bổ sung:** sender-constrained proof (DPoP/mTLS) nếu token bị ràng buộc, denylist/session state nếu cần thu hồi nhanh.

Mã giả minh họa:

```text
function authorizeReadOrder(request, orderId):
    token = readBearerToken(request.headers.Authorization)

    claims = trustedJwtLibrary.verify(
        token,
        issuer = "https://auth.example.com",
        audience = "https://api.example.com/orders",
        allowedAlgorithms = ["RS256"],
        expectedTokenType = "at+jwt",
        jwks = configuredTrustedJwks
    )
    if claims is invalid:
        return 401 Unauthorized

    if !isString(claims.sub):
        return 401 Unauthorized
    if !isNumericDate(claims.exp):
        return 401 Unauthorized
    if !isString(claims.scope):
        return 401 Unauthorized

    grantedScopes = splitScopeString(claims.scope)
    if "orders.read" not in grantedScopes:
        return 403 Forbidden

    tenant = claims["https://example.com/claims/tenant"]
    if !isTrustedTenantIdentifier(tenant):
        return 403 Forbidden

    order = loadOrder(orderId)
    if order is missing:
        return 404 Not Found

    if !policy.canReadOrder(claims.sub, tenant, order):
        return 403 Forbidden  # hoặc 404 để tránh lộ sự tồn tại

    return 200 OK with allowedFields(order)
```

Đây là **pseudocode**: thư viện JWT thực tế phải bảo đảm giải mã JSON, kiểm tra chữ ký, cấu hình khóa và thực thi policy theo profile. Hãy **từ chối khi dữ liệu không đúng hợp đồng**; không tự biến `scope` object thành string hoặc chấp nhận `exp` dưới dạng thời gian mili-giây nếu profile quy định NumericDate.

### 10.1. Kiểu JSON và duplicate keys

Những điều dễ bị bỏ qua:

| Sai dạng | Rủi ro |
| --- | --- |
| `"exp": "1795000900"` (string) | Parser không thống nhất; không đúng NumericDate |
| `"aud": 123` | Sai kiểu, có thể bị ép thành string ngoài ý muốn |
| `"scope": ["orders.read"]` khi hợp đồng yêu cầu string | Thư viện A chấp nhận, dịch vụ B từ chối hoặc hiểu khác |
| `"roles": "admin"` khi API yêu cầu mảng | Kiểm tra phần tử sai, nhầm phân quyền |
| Cùng key `"tenant_id"` xuất hiện hai lần trong JSON | Các parser có thể chọn giá trị đầu/cuối khác nhau |
| Claim chứa mảng/JSON lồng nhau rất lớn | Gây tốn CPU/bộ nhớ hoặc quá tải log |

RFC 7519 yêu cầu tên claim trong JWT Claims Set là **duy nhất**; parser phải từ chối duplicate claim names hoặc tuân theo hành vi nhận giá trị cuối như quy tắc xử lý JSON được RFC cho phép. Về thực hành bảo mật, hệ thống nên **từ chối payload có duplicate keys** nếu thư viện hỗ trợ, nhằm tránh các thành phần diễn giải khác nhau.

Không dùng dữ liệu từ token **chưa xác minh** làm thông tin để quyết định quyền, kể cả `kid`/`jku` trong header. Những trường này chỉ có thể được xử lý trong **giới hạn khóa, issuer và thuật toán đã cấu hình đáng tin**.

## 11. Claims và phân quyền: scope, role, tenant không tự động tương đương

Một lỗi phổ biến là lấy mọi claim có vẻ nói về quyền rồi gộp thành quyết định “allow”. Thực tế chúng có chức năng khác nhau:

| Nguồn thông tin | Nó nói điều gì? | Nó không nói điều gì? |
| --- | --- | --- |
| `scope=orders.read` | Access token có quyền yêu cầu đọc Orders API theo hợp đồng | Không cho phép xem đơn của mọi người |
| `roles=["manager"]` | Issuer đã gán role theo semantics của hệ thống | Không bảo đảm role còn hiệu lực hoặc có quyền ở tenant khác |
| `tenant_id=tenant-a` | Token được ràng buộc với tenant theo hợp đồng nội bộ | Không chứng minh user được truy cập mọi object trong tenant |
| `sub=user-42` | Chủ thể của token | Không xác minh user đã hoàn thành MFA vừa mới đây |
| `amr=["pwd","otp"]` | OP tuyên bố phương thức xác thực theo ngữ cảnh OIDC | Không tự cấp scope `payments.refund` |

**Access token** mang quyền yêu cầu thao tác tại resource server; **ID token** truyền kết quả xác thực tới OIDC client; **refresh token** dùng tại authorization server để xin token mới. JWT/opaque là cách biểu diễn, không phải loại quyền. Nếu dùng opaque token, API có thể lấy các thuộc tính tương đương từ **introspection** đáng tin, rồi vẫn phải kiểm tra quyền đối tượng.

Với hệ thống đa tenant, API nên kiểm tra ba điều kiện: **token hợp lệ cho API**, **scope/permission cho hành động**, **quan hệ của chủ thể với object/tenant tại thời điểm yêu cầu**. Không bao giờ thay thế điều kiện thứ ba bằng claim `tenant_id` do client gửi tùy ý trong query/body/header.

## 12. Privacy, tối thiểu dữ liệu và vòng đời claim

Vì JWT ký thường **đọc được**, nên đưa ít thông tin nhất cần thiết vào payload. Token có thể đi qua browser, mobile app, gateway, proxy, telemetry hoặc các service; càng nhiều người nhận được token thì càng nhiều nơi có thể nhìn thấy claims.

**Không đưa** mật khẩu, OTP, refresh token, API key, số giấy tờ, thông tin thanh toán hoặc dữ liệu cá nhân nhạy cảm không cần thiết vào JWT chỉ vì có chữ ký. Với claim cần bảo mật nội dung, cân nhắc **JWE**, opaque token, hoặc tra cứu dữ liệu qua backend tin cậy theo nguyên tắc tối thiểu; JWE giúp giữ bí mật payload với bên không có khóa giải mã nhưng không tự quyết định quyền hay vòng đời.

Những thay đổi quan trọng trong vòng đời:

- **User bị khóa hoặc xóa quyền:** `roles`/`permissions` trong JWT đã cấp có thể trở nên cũ. TTL ngắn, kiểm tra policy hiện hành, denylist hoặc introspection có thể được dùng theo yêu cầu thu hồi.
- **Email đổi:** `email` trong token có thể không còn đúng. Không dùng email làm định danh duy nhất cho phân quyền.
- **Tenant membership đổi:** `tenant_id` và role có thể không phản ánh quan hệ hiện tại. Với thao tác nhạy cảm, phải đối chiếu dữ liệu mới.
- **Client đổi quyền OAuth:** scope đã cấp cho token cũ có thể còn hiệu lực đến hạn nếu không có cơ chế thu hồi.
- **Logout hoặc reset mật khẩu:** thu hồi refresh token/phiên không tự động làm mọi JWT access token tự chứa hết hiệu lực ngay; API cần chiến lược trạng thái/TTL.

Đừng ghi JWT nguyên dạng vào log hay URL/query string. Có thể log một identifier hoặc metadata tối thiểu đã đánh giá độ nhạy cảm (issuer, audience, sự kiện validate, kết quả policy, correlation ID) mà không lộ token hoặc thông tin cá nhân ngoài nhu cầu.

### Vì sao `jti` không thay thế tính duy nhất và kiểm soát replay?

Kẻ tấn công có bản sao access token bearer hợp lệ có thể sử dụng lại nó trong thời hạn token còn được API chấp nhận. `jti` cho phép hệ thống **nhận diện** token, nhưng để **chặn replay** phải có policy và trạng thái đối chiếu phù hợp, hoặc sender-constrained token (DPoP/mTLS) ràng buộc yêu cầu với khóa/chứng chỉ. Kể cả với DPoP, hệ thống còn phải kiểm tra proof và xử lý nonce/time/replay theo profile; không chỉ đọc `cnf` rồi cho phép.

## 13. Case study: xung đột claim trong hệ thống nhiều API

Giả sử công ty triển khai các dịch vụ `orders-api`, `billing-api` và `hr-api`. Đội Identity phát hành access token với claims `iss`, `sub`, `aud`, `exp`, `scope` và một số trường tự định nghĩa.

### Tình huống A: nhận nhầm role từ issuer khác

`hr-api` muốn chấp nhận role `admin` của hệ thống nhân sự, nhưng nhận JWT của một issuer bên thứ ba với `roles=["admin"]`. Nếu API chỉ đọc `roles` mà không so issuer/audience và không ánh xạ hợp đồng, người dùng có thể được quyền quản trị sai. **Sửa:** validate token và issuer, chỉ dùng role từ nguồn được ủy quyền; map role rõ ràng và áp dụng policy object-level.

### Tình huống B: sai kiểu audience

JWT có `aud=["orders-api","billing-api"]` theo profile cho phép. Một API so sánh `claims.aud == "orders-api"` có thể từ chối nhầm. Một API khác bỏ qua `aud` lại cho phép token dành cho `hr-api`. **Sửa:** dùng thư viện/profile kiểm tra audience có thể xử lý đúng string/array và chỉ chấp nhận định danh của API mục tiêu.

### Tình huống C: namespace private trùng nhau

Issuer A dùng `department=42` với ý nghĩa “mã tổ chức”; issuer B dùng `department="marketing"`. Gateway chuyển claims sang cùng đối tượng rồi code downstream thực hiện so sánh quyền sai. **Sửa:** contract theo issuer, validate kiểu dữ liệu, dùng collision-resistant name cho claims dùng liên hệ nhiều bên.

### Tình huống D: quyền đã thay đổi nhưng JWT vẫn còn hạn

Một nhân viên bị chuyển khỏi `tenant-a`, nhưng access token tự chứa vẫn có `tenant_id=tenant-a`, `roles=["manager"]`. Nếu API chỉ tin token còn hạn mà không có cơ chế áp dụng thay đổi quyền, người đó có thể tiếp tục thao tác đến `exp`. **Sửa:** TTL hợp lý, kiểm tra membership/policy hiện hành hoặc cơ chế thu hồi nhanh cho tài nguyên nhạy cảm.

### Tình huống E: ID token bị chấp nhận bởi API

Client có OIDC ID token với `aud=orders-web-client` và access token có `aud=orders-api`. API vô tình kiểm tra chữ ký ID token rồi đọc `sub` để cho phép đọc dữ liệu. **Sửa:** resource server yêu cầu access token đúng token profile/type và audience; không sử dụng ID token để gọi API.

## 14. Bảng quyết định khi thiết kế claim mới

| Câu hỏi | Nếu “có” | Hành động nên làm |
| --- | --- | --- |
| Một chuẩn/profile đang sử dụng đã định nghĩa claim này? | Có | Dùng đúng tên, kiểu và semantics của chuẩn |
| Claim chỉ phục vụ 1–2 service nội bộ có cùng hợp đồng? | Có | Private claim có thể phù hợp; ghi contract |
| Claim cần chia sẻ qua nhiều đội, đối tác hoặc issuers? | Có | Xem xét IANA registration hoặc collision-resistant namespace |
| Giá trị chứa thông tin cá nhân/nhạy cảm? | Có | Loại bỏ nếu không cần; cân nhắc opaque/JWE/backend lookup |
| Claim sẽ dùng cho phân quyền? | Có | Xác định issuer tin cậy, audience, TTL và policy trên object |
| Giá trị có thể thay đổi nhanh như role/membership? | Có | Tránh coi claim là trạng thái vĩnh viễn; thiết kế TTL/revocation/tra cứu |
| Tên claim có thể bị hiểu khác ở hệ thống khác? | Có | Định danh namespace, schema, version và kiểm tra chặt |

Trước khi xuất bản một hợp đồng claim, nên ghi lại **tên canonical, owner, kiểu JSON, ý nghĩa, giá trị hợp lệ, nguồn phát hành, audience, quy tắc bắt buộc/tùy chọn, thay đổi phiên bản, chính sách lỗi và bảo mật dữ liệu**. Đặt tên chuẩn là bước đầu; quản lý hợp đồng mới giúp các service không hiểu sai token.

## 15. Những hiểu nhầm cần loại bỏ

| Hiểu nhầm | Sự thật |
| --- | --- |
| “Registered claim là bắt buộc trong mọi JWT.” | RFC 7519 `4.1 định nghĩa bảy tên; profile ứng dụng quyết định claim nào bắt buộc. |
| “Claim nào có trong IANA cũng thuộc bảy `4.1.” | IANA còn có claims từ các chuẩn mở rộng; phải phân biệt phạm vi. |
| “Public claim nghĩa là giá trị không nhạy cảm.” | Public mô tả không gian tên, không đánh giá độ nhạy cảm của dữ liệu. |
| “Private claim không dùng để phân quyền được.” | Có thể dùng theo hợp đồng đáng tin, nhưng phải validate và kiểm tra object policy. |
| “`roles=["admin"]` là chuẩn chung giữa mọi nhà cung cấp.” | Ý nghĩa role phụ thuộc issuer và hợp đồng. |
| “`sub` luôn là ID người dùng toàn cầu.” | Subject thường có phạm vi issuer; với S2S có thể không phải con người. |
| “`iat` mới có nghĩa người dùng vừa MFA.” | `iat` là thời điểm token phát hành, khác `auth_time` OIDC. |
| “JWT ký có payload bí mật.” | JWS không mã hóa payload; ai giữ token có thể đọc claims. |
| “Có `jti` là token không bị phát lại.” | Cần policy/trạng thái hoặc bằng chứng ràng buộc người gửi. |
| “Có scope đọc là được đọc mọi dữ liệu.” | API còn phải kiểm tra owner, tenant và policy tài nguyên. |

## 16. Checklist review JWT claims

Khi triển khai issuer, gateway hoặc resource server:

1. **Token loại gì?** JWT access token, OIDC ID token hay một loại token nghiệp vụ khác? Audience và verifier có đúng không?
2. **Nguồn định nghĩa claim nào?** Bảy registered RFC 7519, chuẩn mở rộng/IANA, public namespace hay private contract?
3. **Kiểu và ngữ nghĩa có cố định không?** `aud` string/array, thời gian NumericDate, scope string, role kiểu đã thống nhất?
4. **Issuer có đáng tin không?** Chữ ký, thuật toán allowlist, JWKS đã cấu hình, `iss` chính xác, chống token confusion?
5. **Audience có chính xác không?** API chỉ nhận token dành cho nó, không dùng ID token để thay access token?
6. **Thời hạn có hợp lý không?** `exp`, `nbf`, `iat`, TTL tối đa, clock skew và xử lý token hết hạn?
7. **Custom claims có được kiểm soát không?** Namespace, owner, định dạng, giá trị, version và fallback khi thiếu?
8. **Claims quyền có đủ điều kiện không?** Đã đối chiếu scope/role với object policy, tenant và dữ liệu hiện hành chưa?
9. **Token có lộ dữ liệu không?** JWT ký có chứa secret, email/PII không cần thiết hay token được ghi log/URL?
10. **Thu hồi và replay đã có chiến lược?** Logout, đổi role, mất token, `jti` và sender-constrained proof được xử lý theo chính sách?
11. **Kiểm thử âm tính đã đủ chưa?** Sai issuer, sai audience, token type, duplicate keys, sai kiểu, hết hạn, custom claim lạ, thiếu quyền và sai tenant?

**Kết luận của bài:** registered, public và private là **cách phân loại tên claim**, không phải các mức đặc quyền. API phải hiểu đúng contract của từng tên, **xác minh JWT trước khi tin giá trị**, giới hạn audience/thời hạn/quyền và luôn kiểm tra chính sách với tài nguyên thực tế. Khi đó, claims mới hỗ trợ mô hình tin cậy của OAuth 2.0/OIDC thay vì trở thành nguồn nhầm lẫn và leo thang quyền.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `4.1 Registered Claim Names, `4.2 Public Claim Names, `4.3 Private Claim Names, NumericDate và validation.
- [IANA — JSON Web Token Claims Registry](https://www.iana.org/assignments/jwt/jwt.xhtml): danh sách tên claim đã đăng ký và tham chiếu đặc tả.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): kiểm tra thuật toán, loại token, issuer/audience, cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và các claims liên quan OAuth.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): mô hình ủy quyền và scope.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): định danh tài nguyên đích.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): tra cứu metadata/trạng thái access token.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): liên kết token với khóa người gửi.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `auth_time`, `amr`, `acr`, `nonce` và quy tắc ID token.
