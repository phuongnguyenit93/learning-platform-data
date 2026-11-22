# iss, aud, typ hoặc claims bắt buộc bị thiếu và không khớp

> **Chương:** Kiểm thử bảo mật  
> **Phạm vi:** Security – JSON Web Token (JWT), thuộc module SECURITY_TOKEN_SECURITY_JWT. Bài viết tập trung kiểm thử các điều kiện xác minh issuer, audience, token type và claims bắt buộc trong các profile JWT; áp dụng độc lập với ngôn ngữ lập trình và framework.

## 1. Vì sao phải kiểm thử claims và token profile?

Một JWT có thể có cấu trúc đúng, chữ ký hợp lệ và vẫn không phù hợp với API đang nhận nó.

Ví dụ, Billing API nhận một token:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": "inventory-api",
  "scope": "invoice:read",
  "exp": 1800000300
}
~~~

Token có thể được issuer ký hợp lệ và chưa hết hạn. Tuy nhiên:

- **iss** có thể không phải issuer mà Billing API tin cậy.
- **aud** dành cho Inventory API, không phải Billing API.
- Token có thể thuộc một loại khác, chẳng hạn ID Token thay vì access token.
- Một claim mà profile của Billing API yêu cầu có thể bị thiếu.
- Claim có thể tồn tại nhưng sai kiểu dữ liệu hoặc sai giá trị.

Nếu API chỉ kiểm tra chữ ký và expiration, token có thể bị chấp nhận sai ngữ cảnh. Điều này dẫn đến cross-JWT confusion, token substitution hoặc chấp nhận credential của một hệ thống/ứng dụng khác.

**Mục tiêu của kiểm thử** là chứng minh rằng một token chỉ được chấp nhận khi đồng thời thỏa mãn:

1. Được xác minh theo thuật toán và khóa tin cậy.
2. Được phát hành bởi issuer phù hợp.
3. Được dành cho đúng resource server.
4. Thuộc đúng loại token/profile.
5. Có đủ claims bắt buộc với kiểu dữ liệu và giá trị hợp lệ.
6. Thỏa mãn các điều kiện thời gian và chính sách bổ sung của profile.

Không thể suy ra một JWT hợp lệ chỉ từ việc giải mã được payload. Claims chỉ được tin cậy sau khi hoàn tất bước xác minh mật mã và các điều kiện xác minh theo profile.

## 2. Phân biệt quy tắc JWT chung và quy tắc của profile

Một nhầm lẫn thường gặp là cho rằng mọi registered claim của JWT đều bắt buộc phải xuất hiện trong mọi token.

RFC 7519 quy định tập claims chung và ý nghĩa của chúng, nhưng không bắt mọi JWT phải chứa **iss**, **aud**, **sub**, **exp** hoặc các claim khác. Tập claim cần có để một token được xem là hợp lệ phụ thuộc vào ngữ cảnh ứng dụng và profile sử dụng JWT.

Vì vậy, trước khi viết test, phải có một **validation contract** xác định rõ:

- Profile nào đang được kiểm thử.
- Claim nào bắt buộc, claim nào tùy chọn.
- Kiểu dữ liệu của từng claim.
- Giá trị hoặc tập giá trị được chấp nhận.
- Quy tắc so sánh và chuẩn hóa.
- Điều kiện thời gian và clock-skew.
- Các header parameter bắt buộc.
- Quy tắc phân biệt profile với các loại JWT khác.

Ví dụ, theo RFC 9068, JWT access token profile yêu cầu các claims **iss**, **exp**, **aud**, **sub**, **client_id**, **iat** và **jti**. Profile này cũng yêu cầu **typ** trong JOSE header để thể hiện đây là JWT access token. Các yêu cầu đó không có nghĩa mọi JWT theo RFC 7519 đều phải có đủ những trường này.

| Ngữ cảnh | Quy tắc |
|---|---|
| JWT tùy chỉnh nội bộ | Ứng dụng phải tự công bố claim bắt buộc và điều kiện kiểm tra. |
| JWT access token theo RFC 9068 | Có bộ claims bắt buộc riêng và yêu cầu **typ** ở JOSE header. |
| OpenID Connect ID Token | Phải tuân thủ các yêu cầu claim và validation của OpenID Connect Core. |
| JWT sự kiện bảo mật hoặc token chuyên dụng | Áp dụng profile tương ứng, không dùng quy tắc access token một cách máy móc. |

### 2.1. Lập manifest cho profile trước khi kiểm thử

Một manifest mẫu:

~~~yaml
profile: billing-api-access-token
expected_issuer: https://identity.example.test
expected_audience: https://billing.example.test
accepted_typ:
  - at+jwt
  - application/at+jwt
required_claims:
  iss:
    type: string
  aud:
    type: string-or-array-of-strings
  sub:
    type: string
  exp:
    type: numeric-date
  iat:
    type: numeric-date
  jti:
    type: string
  client_id:
    type: string
optional_claims:
  - scope
  - tenant_id
  - authz_ver
~~~

Đây là manifest minh họa cho một profile access token cụ thể. Tập claim và giá trị thực tế phải lấy từ hợp đồng phát hành/tiêu thụ token của hệ thống.

Manifest giúp test có tiêu chí rõ ràng. Nếu không xác định profile, nhóm kiểm thử có thể đánh dấu nhầm một claim tùy chọn là lỗi hoặc bỏ sót một claim bắt buộc.

## 3. Quy trình xác minh cần được kiểm thử

Một pipeline xác minh có thể được mô hình hóa như sau:

~~~mermaid
flowchart TD
    A["Nhận JWT"] --> B["Parse cấu trúc và header ở trạng thái chưa tin cậy"]
    B --> C["Chọn cấu hình issuer/key từ trust allowlist"]
    C --> D["Kiểm tra thuật toán và xác minh chữ ký"]
    D -->|Fail| X["Từ chối: invalid_token"]
    D -->|Pass| E["Xác minh issuer và token profile"]
    E -->|Fail| X
    E --> F["Kiểm tra required claims và kiểu dữ liệu"]
    F -->|Fail| X
    F --> G["Kiểm tra audience và thời gian"]
    G -->|Fail| X
    G --> H["Tạo principal đã xác minh"]
    H --> I["Tiếp tục authorization"]
~~~

Các điểm cần chú ý:

- Header và payload có thể được parse trước để định tuyến hoặc chuẩn bị xử lý, nhưng dữ liệu đó vẫn chưa đáng tin.
- Không dùng **iss** chưa xác minh để tự động tải metadata hoặc khóa từ một URL bất kỳ do token cung cấp.
- Chỉ chọn issuer/key từ cấu hình hoặc danh sách trust đã được quản lý.
- **typ** nằm trong JOSE header, được bảo vệ bởi chữ ký của JWS; chỉ dựa vào giá trị đó sau khi xác minh token.
- Chỉ tạo principal hoặc thực hiện authorization sau khi mọi điều kiện xác minh bắt buộc đã thành công.

Thứ tự nội bộ có thể khác tùy thư viện và kiến trúc. Điều quan trọng là không để claim chưa xác minh trở thành căn cứ tin cậy, và không để một bước xác minh bị bỏ qua.

## 4. Kiểm thử iss – Issuer bị thiếu hoặc không khớp

### 4.1. Vai trò của iss

Claim **iss** xác định principal phát hành JWT. Resource server cần biết issuer nào được tin cậy và token đang được xác minh có đúng do issuer đó phát hành hay không.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": "billing-api",
  "exp": 1800000300
}
~~~

**iss** là registered claim nhưng RFC 7519 không bắt buộc mọi JWT phải chứa nó. Nếu profile yêu cầu issuer, token thiếu **iss** phải bị từ chối.

### 4.2. Các trường hợp âm cần kiểm thử

| Test case | Giá trị iss | Kết quả mong đợi khi profile yêu cầu issuer cụ thể |
|---|---|---|
| ISS-01 | Claim bị thiếu | Từ chối. |
| ISS-02 | null | Từ chối do sai kiểu dữ liệu. |
| ISS-03 | Chuỗi rỗng | Từ chối do không phải issuer hợp lệ theo profile. |
| ISS-04 | Số hoặc boolean | Từ chối. |
| ISS-05 | Issuer khác | Từ chối. |
| ISS-06 | Issuer đúng nhưng khác chữ hoa/thường | Từ chối nếu không bằng giá trị được cấu hình theo quy tắc so sánh. |
| ISS-07 | Issuer có dấu / cuối khác với cấu hình | Từ chối nếu hai identifier không bằng nhau. |
| ISS-08 | Issuer dùng scheme khác, ví dụ HTTP thay vì HTTPS | Từ chối. |
| ISS-09 | Issuer có port hoặc path khác | Từ chối. |
| ISS-10 | Issuer không nằm trong trust allowlist | Từ chối. |

Theo RFC 7519, giá trị **iss** là chuỗi StringOrURI có phân biệt chữ hoa/thường. Các giá trị StringOrURI được so sánh như chuỗi, không tự động biến đổi hoặc canonicalize. Nếu hệ thống muốn dùng một quy tắc canonicalization riêng, quy tắc đó phải được định nghĩa rõ và áp dụng nhất quán ở cả bên phát hành lẫn bên xác minh.

Ví dụ, không nên tự coi hai giá trị sau là giống nhau nếu cấu hình không quy định như vậy:

~~~text
https://identity.example.test
https://identity.example.test/
~~~

Cũng không dùng phép so sánh dạng:

~~~text
issuer.endsWith("example.test")
issuer.contains("identity")
issuer.startsWith("https://identity")
~~~

Các phép so sánh lỏng có thể cho phép issuer giả mạo hoặc issuer ngoài phạm vi tin cậy đi qua.

### 4.3. Kiểm thử nhiều issuer

Nếu một resource server chấp nhận nhiều issuer, mỗi issuer phải có cấu hình tin cậy riêng:

| Issuer | Key set | Audience hợp lệ | Profile |
|---|---|---|---|
| Identity A | JWKS A | billing-api | access-token-v1 |
| Identity B | JWKS B | partner-billing | partner-access-v1 |

Các test quan trọng:

- Token của issuer A được ký bằng key A và có **iss** A: chấp nhận nếu các điều kiện còn lại hợp lệ.
- Token của issuer A nhưng khai báo **iss** B: từ chối.
- Token khai báo issuer A nhưng ký bằng key không thuộc issuer A: từ chối.
- Token của issuer không có trong allowlist: từ chối.
- Issuer A bị gỡ khỏi cấu hình trust: token mới của A phải bị từ chối sau khi thay đổi có hiệu lực.
- Key rotation của issuer A không được làm resource server vô tình chấp nhận issuer khác.

Không được lấy **jku**, **x5u** hoặc URL tùy ý trong token để tự tìm khóa của issuer. Key discovery phải đi qua cấu hình và metadata được tin cậy.

### 4.4. Phân biệt lỗi issuer với lỗi chữ ký

Nếu test tạo token có **iss** sai nhưng đồng thời ký bằng một khóa không được tin cậy, validator có thể từ chối ngay ở bước chữ ký. Test đó chưa chứng minh bước kiểm tra issuer hoạt động.

Để cô lập test issuer:

1. Dùng khóa test hợp lệ của issuer dự kiến.
2. Tạo JWT có chữ ký hợp lệ.
3. Thay **iss** thành issuer khác.
4. Gửi token đến validator của profile đang kiểm thử.
5. Xác minh token bị từ chối vì issuer mismatch.

Một test riêng mới kiểm tra trường hợp chữ ký không được tạo bởi khóa của issuer tin cậy.

## 5. Kiểm thử aud – Audience bị thiếu hoặc không khớp

### 5.1. Vai trò của aud

Claim **aud** xác định recipient hoặc resource server mà JWT hướng đến. Mỗi principal xử lý token phải tự nhận diện mình bằng một giá trị trong audience.

RFC 7519 cho phép:

- Một audience được biểu diễn bằng chuỗi.
- Nhiều audience được biểu diễn bằng mảng chuỗi.

Nếu claim **aud** có mặt nhưng resource server không tìm thấy định danh của mình trong đó, JWT phải bị từ chối. Nếu profile yêu cầu **aud**, việc thiếu claim cũng phải bị từ chối.

### 5.2. Các trường hợp âm cần kiểm thử

Giả sử Billing API mong đợi audience:

~~~text
https://billing.example.test
~~~

| Test case | Giá trị aud | Kết quả mong đợi |
|---|---|---|
| AUD-01 | Claim bị thiếu | Từ chối nếu profile yêu cầu. |
| AUD-02 | null | Từ chối. |
| AUD-03 | Chuỗi rỗng | Từ chối. |
| AUD-04 | Số hoặc boolean | Từ chối do sai kiểu. |
| AUD-05 | Object JSON | Từ chối. |
| AUD-06 | Mảng rỗng | Từ chối theo profile. |
| AUD-07 | Một audience khác | Từ chối. |
| AUD-08 | Mảng chỉ chứa audience khác | Từ chối. |
| AUD-09 | Mảng có Billing API và một audience khác | Xử lý theo policy cho phép nhiều audience. |
| AUD-10 | Chuỗi gần giống, chỉ khác path | Từ chối. |
| AUD-11 | Chuỗi chỉ chứa tên service như billing | Từ chối nếu không phải identifier được cấu hình. |
| AUD-12 | Audience khác chữ hoa/thường | Từ chối nếu không bằng identifier theo quy tắc so sánh. |
| AUD-13 | Mảng chứa phần tử không phải chuỗi | Từ chối. |
| AUD-14 | Mảng có phần tử trùng lặp | Xử lý theo quy tắc profile; nên phát hiện cấu trúc không chuẩn nếu có yêu cầu. |

### 5.3. Kiểm thử chính xác identifier

Không dùng kiểm tra substring:

~~~text
expected_audience in token.aud_text
~~~

Ví dụ, nếu Billing API mong đợi:

~~~text
https://billing.example.test
~~~

các giá trị sau không được tự động chấp nhận:

~~~text
https://billing.example.test.attacker.invalid
https://billing.example.test/admin
https://other.example.test/billing
billing
~~~

Phải kiểm tra audience theo đúng identifier đã cấu hình và quy tắc của profile. Không tự ý bỏ path, port hoặc scheme khi so sánh.

### 5.4. Kiểm thử audience dạng mảng

Ví dụ token:

~~~json
{
  "aud": [
    "https://billing.example.test",
    "https://reporting.example.test"
  ]
}
~~~

Billing API có thể nhận token nếu profile cho phép nhiều audience và identifier của nó có mặt trong mảng.

Tuy nhiên, nếu policy yêu cầu token chỉ dành cho một resource server, mảng nhiều audience phải bị từ chối. Đây là yêu cầu của profile/policy, không phải quy tắc chung của mọi JWT.

Test cần xác minh cả hai lớp:

- Resource server có xuất hiện chính xác trong **aud** không?
- Số lượng và tập audience có phù hợp với policy không?

RFC 9068 yêu cầu resource server xác minh **aud** chứa resource indicator tương ứng với chính nó. Không được chấp nhận token chỉ vì token được cùng issuer ký.

### 5.5. Kiểm thử cross-resource token substitution

Tạo hai token đều có chữ ký hợp lệ:

~~~json
{
  "iss": "https://identity.example.test",
  "aud": "inventory-api",
  "sub": "user-123",
  "exp": 1800000300
}
~~~

và:

~~~json
{
  "iss": "https://identity.example.test",
  "aud": "billing-api",
  "sub": "user-123",
  "exp": 1800000300
}
~~~

Kết quả mong đợi:

- Inventory API chấp nhận token có audience Inventory nếu các điều kiện khác đạt.
- Billing API từ chối token chỉ dành cho Inventory.
- Inventory API từ chối token chỉ dành cho Billing.
- Không có service nào bỏ kiểm tra audience vì issuer giống nhau.

Đây là test quan trọng để phát hiện việc sử dụng một access token ở sai resource server.

## 6. Kiểm thử typ – Token type bị thiếu hoặc sai

### 6.1. typ là header parameter, không phải claim

**typ** nằm trong JOSE header:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "key-2026-01"
}
~~~

Nó không nằm trong JWT Claims Set. Không được nhầm:

- JOSE header **typ**: mô tả loại nội dung JWT.
- Claim payload có tên **typ**: một claim riêng do ứng dụng/profile định nghĩa nếu có.
- OAuth response **token_type**: mô tả cách client sử dụng access token, ví dụ Bearer.

Ba giá trị này không thể thay thế lẫn nhau.

### 6.2. typ không bắt buộc với mọi JWT

RFC 7519 định nghĩa **typ** là header parameter tùy chọn. RFC 8725 khuyến nghị dùng explicit typing cho các ứng dụng JWT mới và khuyến nghị các loại JWT khác nhau phải có quy tắc xác minh loại trừ lẫn nhau.

Vì vậy, test phải dựa vào profile:

- JWT tổng quát không yêu cầu **typ**: không tự động đánh dấu thiếu **typ** là lỗi.
- JWT access token theo RFC 9068: phải kiểm tra **typ** là **at+jwt** hoặc **application/at+jwt**.
- Profile riêng có token type tùy chỉnh: kiểm tra đúng các giá trị đã công bố.

### 6.3. Test matrix cho typ

Giả sử API sử dụng RFC 9068:

| Test case | JOSE header | Kết quả mong đợi |
|---|---|---|
| TYP-01 | Không có **typ** | Từ chối. |
| TYP-02 | **typ** là null | Từ chối. |
| TYP-03 | **typ** là số hoặc object | Từ chối. |
| TYP-04 | **typ** là JWT | Từ chối theo profile access token. |
| TYP-05 | **typ** là application/jwt | Từ chối theo profile access token. |
| TYP-06 | **typ** là at+jwt | Chấp nhận nếu các điều kiện khác hợp lệ. |
| TYP-07 | **typ** là application/at+jwt | Chấp nhận nếu các điều kiện khác hợp lệ. |
| TYP-08 | **typ** là media type không liên quan | Từ chối. |
| TYP-09 | **typ** chỉ gần giống at+jwt | Từ chối. |
| TYP-10 | **typ** đúng nhưng chữ ký sai | Từ chối. |

Media type name và subtype không phân biệt chữ hoa/thường theo quy tắc media type. Khi kiểm thử **typ**, cần áp dụng đúng quy tắc so sánh media type và các giá trị mà profile chấp nhận; không mở rộng sang phép so sánh gần đúng, prefix hoặc substring.

### 6.4. Ngăn nhầm ID Token thành Access Token

ID Token và JWT access token có thể có cấu trúc tương tự, cùng issuer hoặc cùng khóa ký. Nếu resource server chỉ kiểm tra chữ ký, **iss**, **sub** và **exp**, ID Token có thể bị sử dụng nhầm như access token.

Với profile RFC 9068:

- Access token phải có **typ** phù hợp.
- **aud** phải dành cho resource server.
- Các required claims phải đầy đủ.
- Validation rules phải phân biệt access token với ID Token.

Test quan trọng:

1. Tạo ID Token hợp lệ theo OpenID Connect.
2. Gửi ID Token đến endpoint yêu cầu access token.
3. Xác minh resource server từ chối.
4. Kiểm tra lỗi đến từ profile/type/audience validation, không chỉ do token bị hỏng.
5. Gửi access token hợp lệ đến cùng endpoint và xác minh được chấp nhận.

Không chỉ dựa vào một dấu hiệu duy nhất nếu profile còn có các điều kiện phân biệt khác. RFC 8725 yêu cầu validation rules của các loại JWT khác nhau phải loại trừ lẫn nhau.

## 7. Kiểm thử required claims bị thiếu

### 7.1. Required claims phụ thuộc profile

Một claim chỉ trở thành bắt buộc khi profile hoặc ứng dụng quy định nó là bắt buộc.

Ví dụ, với RFC 9068 JWT access token profile:

| Claim | Yêu cầu của RFC 9068 |
|---|---|
| **iss** | Required |
| **exp** | Required |
| **aud** | Required |
| **sub** | Required |
| **client_id** | Required |
| **iat** | Required |
| **jti** | Required |
| **scope** | Không phải claim bắt buộc trong mọi token; phụ thuộc authorization request và profile |
| **typ** | Header parameter bắt buộc của profile, không phải payload claim |

Với profile khác, tập required claims có thể khác. Không sao chép danh sách RFC 9068 sang một JWT tùy chỉnh mà không có quyết định thiết kế.

### 7.2. Kiểm thử từng claim bị thiếu

Tạo một token baseline hợp lệ, sau đó loại bỏ từng claim một:

| Test case | Claim bị loại bỏ | Kết quả mong đợi nếu claim là required |
|---|---|---|
| REQ-01 | **iss** | Từ chối. |
| REQ-02 | **aud** | Từ chối. |
| REQ-03 | **sub** | Từ chối. |
| REQ-04 | **exp** | Từ chối. |
| REQ-05 | **iat** | Từ chối. |
| REQ-06 | **jti** | Từ chối. |
| REQ-07 | **client_id** | Từ chối. |
| REQ-08 | Claim tùy chỉnh mà profile yêu cầu | Từ chối. |
| REQ-09 | Claim tùy chọn | Chấp nhận nếu không có quy tắc khác yêu cầu. |

Nguyên tắc quan trọng: chỉ bỏ một claim trong mỗi test. Nếu cùng lúc bỏ **iss**, **aud** và **sub**, validator có thể từ chối ở một bước sớm và test không chứng minh được từng điều kiện riêng lẻ.

### 7.3. Phân biệt missing, null, empty và wrong type

Các trường hợp này khác nhau và nên có test riêng:

~~~json
{}
~~~

~~~json
{
  "sub": null
}
~~~

~~~json
{
  "sub": ""
}
~~~

~~~json
{
  "sub": 123
}
~~~

Nếu **sub** là required string:

- Missing: không có claim.
- Null: có key nhưng giá trị JSON null, không phải string.
- Empty: là string nhưng có thể không hợp lệ theo semantic rule.
- Number: sai kiểu dữ liệu.

Không nên chỉ kiểm tra containsKey("sub"). Cần kiểm tra kiểu dữ liệu và điều kiện nội dung theo profile.

## 8. Kiểm thử claim có mặt nhưng sai kiểu hoặc sai giá trị

### 8.1. Kiểm tra kiểu dữ liệu

Một profile cần xác định kiểu dữ liệu của claim. Ví dụ:

| Claim | Kiểu thường dùng theo chuẩn/profile | Ví dụ sai |
|---|---|---|
| **iss** | StringOrURI | 123, true, object |
| **aud** | String hoặc array of strings | Number, object, array chứa number |
| **sub** | StringOrURI | Number, array |
| **exp** | NumericDate | "1800000300" dạng string, boolean |
| **nbf** | NumericDate nếu có | String hoặc object |
| **iat** | NumericDate | "yesterday" |
| **jti** | String | Array hoặc object |
| **client_id** | String | Number hoặc null |
| **scope** | String theo profile OAuth thông dụng | Object hoặc array nếu profile không cho phép |
| **roles** | Theo schema của profile | String nếu profile yêu cầu array |

Không tự suy luận kiểu dữ liệu từ tên claim. Hãy dựa vào RFC hoặc hợp đồng profile thực tế.

### 8.2. Kiểm tra semantic constraints

Một giá trị có thể đúng kiểu nhưng vẫn sai về ý nghĩa:

- **iss** là string nhưng không phải issuer tin cậy.
- **aud** là array string nhưng không chứa resource server hiện tại.
- **sub** là string rỗng hoặc không thuộc namespace được chấp nhận.
- **exp** là NumericDate nhưng đã hết hạn.
- **iat** là NumericDate nhưng nằm trong tương lai quá giới hạn cho phép.
- **jti** là string nhưng trùng lặp trong một ngữ cảnh mà hệ thống yêu cầu định danh duy nhất.
- **tenant_id** đúng định dạng nhưng tenant không tồn tại hoặc không thuộc phạm vi tin cậy.
- **authz_ver** là số nhưng thấp hơn version hiện tại hoặc ngoài miền giá trị được phép.

Cần phân biệt lỗi schema với lỗi policy. Sai kiểu là lỗi cấu trúc/validation; một giá trị đúng kiểu nhưng không được phép là lỗi kiểm tra profile hoặc authorization context.

### 8.3. Kiểm thử claims tùy chỉnh

Ví dụ profile yêu cầu:

~~~json
{
  "tenant_id": "tenant-42",
  "authz_ver": 7,
  "roles": [
    "invoice-reader"
  ]
}
~~~

Test nên bao gồm:

- **tenant_id** bị thiếu.
- **tenant_id** là null hoặc chuỗi rỗng.
- **tenant_id** sai format.
- **tenant_id** là tenant không được phép.
- **authz_ver** bị thiếu.
- **authz_ver** là số âm hoặc sai kiểu.
- **roles** là string thay vì array.
- **roles** chứa phần tử không phải string.
- Role không nằm trong vocabulary của profile.
- Claim hợp lệ về cấu trúc nhưng không phù hợp trạng thái hiện tại của chủ thể.

Nếu claim tùy chỉnh là tùy chọn, test token không có claim đó phải xác nhận hệ thống vẫn xử lý đúng theo thiết kế.

## 9. Kiểm thử các claim thời gian trong bộ required claims

**exp**, **nbf** và **iat** thường là nguồn lỗi khi kiểm thử claim thiếu hoặc sai kiểu.

### 9.1. exp

Nếu profile yêu cầu **exp**:

- Missing: từ chối.
- Null: từ chối.
- String thay vì NumericDate: từ chối.
- Token đã hết hạn: từ chối.
- Token còn hạn: chấp nhận nếu các điều kiện khác đạt.
- Token hết hạn đúng ranh giới: kiểm tra quy tắc thời gian và leeway được cấu hình.

Thời điểm hiện tại phải trước thời điểm **exp**. Clock-skew leeway, nếu có, phải nhỏ và được định nghĩa rõ. Không để mỗi thành phần dùng một giá trị leeway khác nhau.

### 9.2. nbf

Nếu profile yêu cầu **nbf**, test:

- Missing.
- Null.
- Sai kiểu NumericDate.
- **nbf** nằm trong tương lai.
- **nbf** nằm trong quá khứ.
- Ranh giới **nbf** bằng thời gian hiện tại.
- Token có clock skew trong phạm vi cho phép và vượt quá phạm vi cho phép.

Nếu **nbf** không bắt buộc, việc thiếu claim không tự động là lỗi.

### 9.3. iat

Nếu profile yêu cầu **iat**, test:

- Missing hoặc null.
- String thay vì NumericDate.
- Giá trị tương lai vượt giới hạn cho phép.
- Giá trị quá cũ nếu profile đặt maximum token age.
- **iat** lớn hơn **exp**.
- Thời gian phát hành không phù hợp với thời điểm cấp credential.

RFC 7519 định nghĩa **iat** là thời điểm phát hành; việc áp dụng giới hạn tuổi tối đa hoặc quy tắc tương quan giữa các claim là chính sách của profile.

## 10. Kiểm thử claims trùng lặp và JSON bất thường

JWT Claims Set là JSON object. Tên claim trong một Claims Set phải duy nhất. RFC 7519 yêu cầu parser từ chối JWT có claim name trùng lặp hoặc sử dụng parser chỉ trả về member trùng lặp cuối cùng.

Ví dụ payload không nên có:

~~~json
{
  "iss": "https://identity.example.test",
  "aud": "billing-api",
  "aud": "inventory-api",
  "sub": "user-123",
  "exp": 1800000300
}
~~~

Nếu các thành phần trong hệ thống parse JSON khác nhau, một bên có thể nhìn thấy **aud** đầu tiên còn bên kia nhìn thấy **aud** cuối cùng. Điều này tạo ra sự khác biệt trong quyết định xác minh.

Test nên bao gồm:

- Duplicate **iss**.
- Duplicate **aud**.
- Duplicate **typ** trong JOSE header.
- Duplicate claim tùy chỉnh.
- JSON không hợp lệ.
- Unicode hoặc escaping bất thường trong issuer/audience.
- JSON number vượt miền số mà parser hỗ trợ.
- Array lồng nhau hoặc object ở nơi profile yêu cầu string.

Nên thống nhất parser và chính sách duplicate member. Trong môi trường bảo mật cao, từ chối JSON có duplicate claim name giúp tránh hành vi khác nhau giữa các thành phần.

## 11. Kiểm thử cross-JWT confusion

Cross-JWT confusion xảy ra khi token được phát hành cho một mục đích lại được chấp nhận trong ngữ cảnh khác.

Ví dụ:

- ID Token bị gửi đến API thay cho access token.
- JWT dùng cho một service bị gửi đến service khác.
- JWT dành cho môi trường staging được gửi đến production.
- Token có issuer hợp lệ nhưng thuộc một profile khác.
- Token dành cho một luồng xác thực bị dùng như credential của một luồng khác.

RFC 8725 khuyến nghị validation rules của các loại JWT do cùng issuer phát hành phải loại trừ lẫn nhau. Các cách phân biệt có thể kết hợp:

- Explicit **typ**.
- Required claims khác nhau.
- Giá trị claim khác nhau.
- Header parameter khác nhau.
- Key khác nhau.
- Audience khác nhau.
- Issuer khác nhau.

### 11.1. Ma trận cross-profile

| Token đầu vào | Endpoint mong đợi | Kết quả |
|---|---|---|
| Access token profile A | Resource A | Chấp nhận nếu hợp lệ. |
| Access token profile A | Resource B | Từ chối nếu audience không khớp. |
| ID Token | Resource API | Từ chối theo access-token profile. |
| Token ký bởi issuer staging | Production API | Từ chối. |
| Token có **typ** của Security Event Token | API access token | Từ chối. |
| Token thiếu claim phân biệt profile | Endpoint yêu cầu profile cụ thể | Từ chối. |
| Token đúng issuer nhưng sai required claim set | Endpoint profile khác | Từ chối. |

Không dựa vào một dấu hiệu duy nhất nếu profile có thể được phân biệt bằng nhiều điều kiện. Ví dụ, **typ** đúng nhưng audience sai vẫn phải bị từ chối.

## 12. Tạo test fixture đúng cách

### 12.1. Dùng token baseline hợp lệ

Bắt đầu bằng một token được ký bằng test key tin cậy và thỏa mãn toàn bộ profile:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": "https://billing.example.test",
  "client_id": "billing-web",
  "iat": 1800000000,
  "exp": 1800000300,
  "jti": "test-token-001",
  "scope": "invoice:read"
}
~~~

JOSE header:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "test-key-01"
}
~~~

Đây là fixture minh họa theo hướng RFC 9068. Các thời điểm cần được tạo tương đối với clock cố định của test để không phụ thuộc thời gian thực.

### 12.2. Re-sign token khi kiểm thử claim

Đây là nguyên tắc quan trọng nhất khi kiểm thử claim validator.

Nếu sửa payload sau khi ký mà không ký lại, chữ ký sẽ sai. Validator có thể từ chối ở bước signature verification trước khi chạm đến **iss**, **aud** hoặc required claims.

Để kiểm thử claim validation:

1. Tạo baseline token hợp lệ.
2. Thay đổi đúng một claim hoặc header parameter.
3. Ký lại bằng test key được validator tin cậy.
4. Gửi token đến endpoint.
5. Xác minh lỗi thuộc điều kiện đang kiểm thử.

Ví dụ:

- Kiểm thử **aud** mismatch: tạo token có chữ ký hợp lệ nhưng audience khác.
- Kiểm thử thiếu **iss**: tạo token có chữ ký hợp lệ nhưng payload không có **iss**.
- Kiểm thử sai **typ**: tạo token có chữ ký hợp lệ nhưng JOSE header chứa type khác.
- Kiểm thử thiếu **client_id**: ký lại token sau khi loại claim này.

Tạo một test riêng cho token bị sửa sau khi ký để kiểm tra signature verification. Không dùng test signature failure thay cho test claim failure.

### 12.3. Cố định clock trong test

Không sử dụng timestamp ngẫu nhiên hoặc phụ thuộc thời gian thực cho mọi test. Dùng clock giả lập/cố định để tạo các trường hợp:

- Token còn hạn.
- Token vừa hết hạn.
- Token chưa đến **nbf**.
- **iat** ở tương lai.
- Token vượt maximum age.
- Token nằm sát ranh giới clock-skew.

Điều này giúp test có thể lặp lại và không flaky.

## 13. Mã giả kiểm thử validation profile

Mã giả sau minh họa các bước kiểm tra. Đây là logic khái niệm, không phải API của thư viện cụ thể.

~~~text
function validate_token_for_profile(token, profile):
    parsed = parse_compact_token(token)

    # Chỉ dùng cấu hình issuer/key đã được tin cậy.
    issuer_config = profile.trusted_issuers.lookup_candidate(parsed.untrusted_issuer)

    if issuer_config is null:
        reject("invalid_token")

    verify_allowed_algorithm(parsed.header.alg, issuer_config.allowed_algorithms)
    verify_signature(parsed, issuer_config.trusted_keys)

    # Sau khi xác minh chữ ký mới tin claims/header.
    require_string(parsed.claims.iss)
    require_exact_issuer(parsed.claims.iss, profile.expected_issuer)

    require_accepted_typ(parsed.header.typ, profile.accepted_typ)

    for claim in profile.required_claims:
        require_present(parsed.claims, claim.name)
        require_type(parsed.claims[claim.name], claim.type)
        require_semantics(parsed.claims[claim.name], claim.constraints)

    require_audience_contains_expected(
        parsed.claims.aud,
        profile.expected_audience
    )

    validate_temporal_claims(parsed.claims, profile.clock_policy)

    return verified_principal(parsed.claims)
~~~

Các hàm kiểm tra phải xử lý trường hợp thiếu claim, null, sai kiểu và sai giá trị. Không để việc truy cập thuộc tính hoặc ép kiểu tự động biến một token sai cấu trúc thành token hợp lệ.

Đối với multi-issuer, candidate lookup phải bị giới hạn trong trust configuration. Không tải khóa hoặc discovery metadata từ issuer tùy ý lấy trong token.

## 14. Kiểm thử kết quả HTTP và hành vi bên ngoài

Một token không hợp lệ phải bị từ chối nhất quán.

Với OAuth Bearer access token, RFC 6750 định nghĩa lỗi **invalid_token**. Với profile RFC 9068, các lỗi xác minh bắt buộc cũng phải được xử lý theo hướng **invalid_token**.

| Trường hợp | Kết quả thường mong đợi |
|---|---|
| Chữ ký không hợp lệ | HTTP 401, **invalid_token**. |
| **iss** thiếu hoặc sai | HTTP 401, **invalid_token**. |
| **aud** thiếu hoặc sai | HTTP 401, **invalid_token**. |
| **typ** không phù hợp profile | HTTP 401, **invalid_token**. |
| Required claim thiếu hoặc sai kiểu | HTTP 401, **invalid_token**. |
| Token hết hạn | HTTP 401, **invalid_token**. |
| Token hợp lệ nhưng scope không đủ | HTTP 403, **insufficient_scope** theo Bearer token usage nếu áp dụng. |
| Token hợp lệ nhưng principal không được phép truy cập object | Từ chối theo authorization policy, thường là 403 hoặc 404 tùy API. |

Không tiết lộ chi tiết nội bộ như issuer nào được tin cậy, audience nào đang được cấu hình, tên claim nội bộ bị thiếu, key ID hợp lệ, cấu trúc token hoặc giá trị claim nhạy cảm, hay token nào gần khớp với profile.

Có thể ghi reason code nội bộ như:

~~~text
JWT_ISSUER_MISMATCH
JWT_AUDIENCE_MISMATCH
JWT_TYPE_MISMATCH
JWT_REQUIRED_CLAIM_MISSING
~~~

Log không được chứa raw JWT.

### 14.1. Kiểm tra không có side effect

Khi token bị từ chối, xác minh:

- Không tạo session hoặc principal đã xác thực.
- Không chạy nghiệp vụ.
- Không truy vấn dữ liệu nhạy cảm vượt quá mức cần thiết cho validation.
- Không tạo job hoặc message.
- Không cập nhật audit/business state như một request hợp lệ.
- Không cache kết quả xác thực sai thành trạng thái hợp lệ.
- Không trả dữ liệu từ cache của request trước.

## 15. Ma trận kiểm thử tổng hợp

| Nhóm | Test case tiêu biểu | Kết quả |
|---|---|---|
| Issuer | Thiếu, null, sai type, sai URL, issuer ngoài allowlist | Từ chối |
| Issuer comparison | Sai slash, path, scheme, port hoặc case theo profile | Từ chối |
| Issuer-key binding | **iss** khai báo issuer A nhưng chữ ký không thuộc key A | Từ chối |
| Audience | Thiếu, null, sai type, audience khác resource | Từ chối |
| Audience array | Có đúng expected audience hoặc chỉ chứa audience khác | Theo policy; chỉ chấp nhận khi đúng identifier và profile |
| Audience matching | Prefix, substring hoặc URL gần giống | Từ chối |
| Token type | **typ** thiếu hoặc sai profile | Từ chối nếu profile yêu cầu |
| Token type confusion | ID Token gửi đến access-token endpoint | Từ chối |
| Required claims | Mỗi claim bắt buộc bị loại bỏ riêng lẻ | Từ chối |
| Claim type | Number/string/object/array/null sai schema | Từ chối |
| Claim semantics | Giá trị rỗng, sai namespace, ngoài miền hoặc không còn hợp lệ | Từ chối |
| Temporal | **exp**, **nbf**, **iat** thiếu/sai/ngoài giới hạn | Theo profile; từ chối khi vi phạm |
| Duplicate claims | **iss**, **aud** hoặc claim khác xuất hiện hai lần | Từ chối hoặc xử lý đúng chính sách parser đã công bố |
| Cross-profile | Token của issuer/profile/resource khác | Từ chối |
| Signature isolation | Claim sai nhưng chữ ký hợp lệ | Từ chối ở claim validation |
| Signature tampering | Payload bị sửa sau khi ký | Từ chối ở signature validation |
| Error handling | Invalid token so với insufficient scope | Phân biệt đúng 401 và 403 |
| Side effects | Token sai được gửi đến endpoint ghi dữ liệu | Không có side effect |

## 16. Kiểm thử tự động và kiểm thử property-based

Ngoài test case cố định, có thể tạo test tự động sinh các biến thể của claim:

- Sinh chuỗi issuer gần giống issuer hợp lệ.
- Sinh audience dưới dạng string, array, array rỗng và array chứa phần tử sai type.
- Sinh giá trị claim null, empty, number, boolean, object và nested array.
- Sinh các tổ hợp required claims bị thiếu.
- Sinh **typ** hợp lệ, không hợp lệ và không có.
- Sinh token của profile khác nhưng dùng cùng issuer.
- Sinh token có claim duplicate để kiểm tra parser.

Property quan trọng cần giữ:

1. Thay issuer bằng một giá trị không được tin cậy không bao giờ làm token được chấp nhận.
2. Xóa một required claim không bao giờ làm token được chấp nhận.
3. Thay audience thành resource khác không bao giờ làm token được chấp nhận ở resource server hiện tại.
4. Đổi token type sang profile khác không bao giờ làm token được chấp nhận.
5. Sai kiểu dữ liệu không được tự động chuyển thành giá trị hợp lệ.
6. Chữ ký không hợp lệ luôn bị từ chối, bất kể claims có vẻ hợp lệ.
7. Một token hợp lệ cho resource A không tự động hợp lệ cho resource B.

Fuzzing parser và property-based testing giúp tìm ra các trường hợp mà bộ test ví dụ chưa bao phủ. Tuy nhiên, kết quả sinh tự động vẫn cần được đối chiếu với validation contract để tránh tạo test không đúng yêu cầu profile.

## 17. Những lỗi kiểm thử thường gặp

| Lỗi | Vì sao không đủ | Cách cải thiện |
|---|---|---|
| Chỉ test token sai chữ ký | Validator dừng trước khi kiểm tra claim | Re-sign token sai claim bằng test key tin cậy |
| Cho rằng **iss** và **aud** luôn bắt buộc trong mọi JWT | RFC 7519 để yêu cầu phụ thuộc ngữ cảnh | Viết manifest theo profile |
| Kiểm tra **aud** bằng substring | Có thể chấp nhận resource identifier giả hoặc gần giống | So sánh đúng identifier |
| Chỉ test **aud** dạng string | Bỏ sót token dùng audience array | Test cả string và array |
| Coi **typ** là payload claim | Kiểm tra sai vị trí | Kiểm tra JOSE header |
| Bắt mọi JWT phải có **typ: JWT** | Có thể xung đột profile access token | Áp dụng type theo profile cụ thể |
| Chấp nhận ID Token vì cùng issuer và chữ ký | Gây cross-JWT confusion | Mutually exclusive validation rules |
| Chỉ kiểm tra claim tồn tại | Bỏ qua null, empty và sai kiểu | Kiểm tra presence, type và semantics |
| Test thiếu nhiều claim cùng lúc | Không biết điều kiện nào thực sự từ chối | Loại bỏ từng claim riêng |
| Tự fetch issuer URL trong token | Tạo trust-on-first-use hoặc SSRF risk | Dùng allowlist và metadata tin cậy |
| Bỏ qua duplicate JSON member | Parser có thể hiểu claim khác nhau | Thống nhất parser, reject duplicate nếu phù hợp |
| Chỉ kiểm tra response status | Có thể vẫn tạo side effect | Kiểm tra database, queue, cache và audit |
| Trả chi tiết claim lỗi cho client | Làm lộ cấu hình và profile | External error chung, internal reason code |
| Không cố định clock | Test thời gian không ổn định | Dùng controllable clock |

## 18. Checklist hoàn thiện bộ test

- [ ] Đã xác định profile JWT và validation contract.
- [ ] Đã phân biệt claim bắt buộc, claim tùy chọn và header parameter bắt buộc.
- [ ] Đã có test **iss** thiếu, null, sai type, sai giá trị và issuer không tin cậy.
- [ ] Đã kiểm tra issuer-key binding.
- [ ] Đã có test **aud** thiếu, sai type, sai identifier và audience array.
- [ ] Đã kiểm tra chính xác audience của từng resource server.
- [ ] Đã phân biệt **typ** trong JOSE header với claim payload và OAuth **token_type**.
- [ ] Đã kiểm tra **typ** theo profile, bao gồm trường hợp thiếu và sai loại.
- [ ] Đã có test cross-JWT confusion, đặc biệt ID Token so với access token.
- [ ] Đã loại bỏ từng required claim riêng biệt.
- [ ] Đã kiểm tra null, empty, wrong type và sai semantic value.
- [ ] Đã kiểm thử **exp**, **nbf**, **iat** và clock-skew nếu profile sử dụng.
- [ ] Đã kiểm tra duplicate claim names và parser behavior.
- [ ] Token fixture sai claim vẫn có chữ ký hợp lệ để test đúng validation layer.
- [ ] Có test riêng cho signature tampering.
- [ ] Đã kiểm tra HTTP error mapping và không tiết lộ thông tin nội bộ.
- [ ] Đã xác minh không có side effect khi token bị từ chối.
- [ ] Có test multi-issuer, multi-audience và key rotation khi hệ thống hỗ trợ.
- [ ] Có regression test cho mọi lỗi claim/profile đã phát hiện.
- [ ] Test dùng test keys và fixture giả, không dùng production token.

## 19. Câu hỏi tự kiểm tra

1. Vì sao không thể mặc định **iss**, **aud** và **sub** là bắt buộc trong mọi JWT?
2. **iss** có kiểu dữ liệu và quy tắc so sánh như thế nào?
3. Khi một resource server nhận JWT có **aud** dạng array, nó phải kiểm tra điều gì?
4. Vì sao kiểm tra audience bằng substring là nguy hiểm?
5. **typ** nằm ở đâu và khác claim payload như thế nào?
6. Theo RFC 9068, access token JWT phải có **typ** nào?
7. Vì sao ID Token có thể bị nhầm thành access token nếu chỉ xác minh chữ ký?
8. Required claims của RFC 9068 gồm những claim nào?
9. Vì sao cần test missing, null, empty và wrong type riêng biệt?
10. Tại sao test claim mismatch phải tạo token có chữ ký hợp lệ?
11. Làm thế nào để kiểm tra **iss** mismatch mà không bị dừng ở signature validation?
12. Duplicate claim names có thể gây khác biệt validation giữa các thành phần ra sao?
13. Khi token không hợp lệ, nên phân biệt **invalid_token** và **insufficient_scope** như thế nào?
14. Làm sao chứng minh token sai không gây side effect?

## 20. Tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): registered claims, tính tùy chọn theo ngữ cảnh, **iss**, **aud**, **exp**, **nbf**, **iat**, **jti**, JOSE **typ**, duplicate claim names và string comparison rules.
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): explicit typing (§3.11), mutually exclusive validation rules (§3.12), cross-JWT confusion và các yêu cầu xác minh an toàn.
- [RFC 9068 – JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): required claims, **typ** header và validation requirements cho JWT access token.
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): xử lý lỗi **invalid_token** và **insufficient_scope**.
- [OpenID Connect Core 1.0 – ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation): yêu cầu xác minh ID Token trong OpenID Connect.
