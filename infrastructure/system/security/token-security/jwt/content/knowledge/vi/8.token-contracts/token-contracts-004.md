# Claims bắt buộc, kiểu dữ liệu và giới hạn giá trị

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Hợp đồng token  
> **Phạm vi:** Quy tắc claim và dữ liệu JWT ở mức giao thức/hệ thống, không phụ thuộc Java, Spring hay framework cụ thể.

JWT mang một tập **claims** (các mệnh đề/thuộc tính) được biểu diễn dưới dạng JSON. Chữ ký hợp lệ chỉ chứng minh dữ liệu được bảo vệ theo cơ chế mật mã của token; nó không chứng minh rằng mọi claim đều có mặt, đúng kiểu, nằm trong giới hạn hợp lệ hoặc phù hợp với thao tác đang yêu cầu.

Ví dụ, một API có thể nhận token đã ký đúng nhưng:

- Thiếu **exp**, dù hợp đồng access token yêu cầu thời hạn.
- Có **aud** là một đối tượng JSON thay vì chuỗi hoặc mảng chuỗi.
- Gửi **exp** theo mili giây trong khi JWT NumericDate tính theo giây.
- Có **scope** nhưng giá trị là mảng thay vì chuỗi theo hồ sơ OAuth JWT access token.
- Có **sub** rỗng, **jti** quá dài hoặc thời hạn hiệu lực dài hơn chính sách.

Những trường hợp này phải bị từ chối theo hợp đồng. Bên phát hành và bên nhận cần thống nhất **claim nào bắt buộc, kiểu dữ liệu nào hợp lệ, giá trị được giới hạn ra sao và cách xử lý claim không được nhận diện**.

## 1. Claim trong JWT và yêu cầu theo từng hồ sơ

Payload JWT là một JSON object chứa các cặp tên/giá trị. Tên claim là chuỗi; giá trị có thể là chuỗi, số, boolean, object, array hoặc null theo JSON. Tuy nhiên, **mỗi claim đã đăng ký hoặc được một hồ sơ quy định có kiểu và ý nghĩa riêng**. Không được coi mọi kiểu JSON đều hợp lệ cho mọi claim.

### 1.1. Không phải mọi registered claim đều bắt buộc trong mọi JWT

RFC 7519 định nghĩa các registered claim names như **iss**, **sub**, **aud**, **exp**, **nbf**, **iat** và **jti**. Định nghĩa claim trong RFC không có nghĩa tất cả JWT đều phải chứa tất cả các claim đó. Chúng trở thành bắt buộc khi hồ sơ token hoặc hợp đồng ứng dụng yêu cầu.

| Claim | Kiểu dữ liệu theo định nghĩa | Ý nghĩa | Quy tắc thường được hợp đồng yêu cầu |
|---|---|---|---|
| **iss** | String | Bên phát hành JWT | Bắt buộc; phải khớp chính xác issuer được tin cậy |
| **sub** | String | Chủ thể mà JWT nói đến | Bắt buộc nếu token đại diện người dùng/dịch vụ; không rỗng, có quy tắc định danh rõ |
| **aud** | String hoặc array các string | Bên nhận dự kiến | Bắt buộc; phải chứa chính xác audience của điểm tiếp nhận |
| **exp** | NumericDate (JSON number) | Thời điểm token hết hạn | Thường bắt buộc cho access token; từ chối khi thời điểm hiện tại bằng hoặc sau exp |
| **nbf** | NumericDate (JSON number) | Thời điểm token bắt đầu có hiệu lực | Bắt buộc nếu hồ sơ yêu cầu; từ chối khi chưa đến thời điểm |
| **iat** | NumericDate (JSON number) | Thời điểm token được phát hành | Có thể bắt buộc; dùng để kiểm tra độ mới và tuổi token theo chính sách |
| **jti** | String | Định danh duy nhất của JWT | Bắt buộc khi cần chống phát lại, thu hồi hoặc truy vết từng token |

Các claim chuẩn có thể được bỏ qua nếu hợp đồng không yêu cầu và giao thức không bắt buộc. Ngược lại, khi hợp đồng tuyên bố claim là bắt buộc, token thiếu claim phải bị từ chối, không tự điền giá trị mặc định để “làm cho hợp lệ”.

### 1.2. Yêu cầu phụ thuộc token profile

Một số hồ sơ cụ thể đặt ra tập claim bắt buộc riêng:

| Hồ sơ / loại token | Ví dụ claim bắt buộc hoặc có quy tắc riêng | Ý nghĩa |
|---|---|---|
| JWT nói chung (RFC 7519) | Không có một tập claim nghiệp vụ bắt buộc áp dụng cho mọi JWT | Ứng dụng tự định nghĩa hợp đồng phù hợp |
| OAuth 2.0 JWT Access Token (RFC 9068) | **iss**, **exp**, **aud**, **sub**, **client_id**, **iat**, **jti** và **typ** theo hồ sơ | Resource server phải xác minh các yêu cầu của hồ sơ |
| OpenID Connect ID Token | **iss**, **sub**, **aud**, **exp**, **iat**; **nonce** khi yêu cầu; các điều kiện bổ sung như **azp** theo trường hợp | Relying party kiểm tra theo quy tắc OIDC |
| Token khôi phục mật khẩu tự thiết kế | Ví dụ **iss**, **sub**, **aud**, **exp**, **jti**, **purpose** | Các claim và quy tắc phải được hợp đồng ứng dụng quy định |

Không lấy danh sách claim của một profile rồi áp dụng nguyên xi cho mọi JWT. Chẳng hạn, **client_id** là thành phần bắt buộc của hồ sơ RFC 9068, nhưng không phải registered claim bắt buộc cho mọi JWT theo RFC 7519.

## 2. Kiểu dữ liệu và quy tắc cho từng claim

### 2.1. String: iss, sub, jti, client_id và các định danh

Các claim định danh thường là chuỗi:

- **iss:** so khớp chính xác với định danh issuer trong cấu hình tin cậy.
- **sub:** định danh chủ thể trong phạm vi issuer. Nếu nhiều issuer có thể cấp cùng một giá trị **sub**, cần định danh chủ thể theo ngữ cảnh issuer (thường là cặp **iss + sub**).
- **jti:** định danh token. Nếu dùng để chống phát lại, phải có tính duy nhất đủ mạnh trong phạm vi kiểm soát và được lưu/đối chiếu theo thời hạn phù hợp.
- **client_id:** định danh OAuth client theo hồ sơ có sử dụng claim này.
- **purpose / token_use:** nếu là claim riêng, cần quy định chuỗi hợp lệ, phân biệt chữ hoa/thường và nơi kiểm tra.

Một hợp đồng nên quy định thêm:

1. Chuỗi có được phép rỗng không (thông thường không).
2. Độ dài tối thiểu/tối đa theo nhu cầu.
3. Tập ký tự hoặc định dạng nếu claim có cấu trúc, chẳng hạn URI hoặc mã định danh.
4. Quy tắc so khớp có phân biệt chữ hoa/thường không.
5. Có cho phép khoảng trắng đầu/cuối hay không (thông thường nên từ chối đối với định danh).

Không tự ý lowercase, trim, URL-decode hoặc Unicode-normalize giá trị claim trước khi so khớp nếu giao thức/hợp đồng không quy định. Hai định danh khác nhau không được biến thành một chỉ vì tầng xử lý tự chuẩn hóa dữ liệu.

### 2.2. NumericDate: exp, nbf và iat

**NumericDate** là số JSON biểu diễn số giây từ Unix epoch (1970-01-01T00:00:00Z), theo định nghĩa RFC 7519. Giá trị có thể là số nguyên hoặc số có phần thập phân; hệ thống nên thống nhất độ chính xác được chấp nhận.

~~~json
{
  "iat": 1794800000,
  "nbf": 1794800000,
  "exp": 1794800600
}
~~~

Các giá trị chỉ minh họa định dạng NumericDate. Đơn vị là **giây**, không phải mili giây.

| Claim | Điều kiện thời gian | Hành vi khi không hợp lệ |
|---|---|---|
| **exp** | Thời điểm hiện tại phải nhỏ hơn exp | Từ chối nếu hiện tại bằng hoặc sau exp |
| **nbf** | Thời điểm hiện tại phải bằng hoặc sau nbf | Từ chối nếu hiện tại còn trước nbf |
| **iat** | Không được ở tương lai vượt quá dung sai; tuổi token không vượt giới hạn hợp đồng nếu có | Từ chối khi phát hành trong tương lai bất hợp lý hoặc token quá cũ theo chính sách |

**exp** xác định hạn cuối chấp nhận token. **iat** không thay thế **exp**: biết thời điểm phát hành không tự cho biết token đã hết hạn hay chưa. Nếu hệ thống yêu cầu tuổi token tối đa, phải tính từ **iat** và quy định riêng.

#### Tránh lỗi giây và mili giây

~~~json
{
  "exp": 1794800600
}
~~~

Đây là ví dụ NumericDate theo giây. Nếu bên phát hành gửi timestamp mili giây (ví dụ số có 13 chữ số) trong khi bên nhận hiểu là giây, token có thể bị coi là hợp lệ trong một khoảng thời gian cực dài. Hai phía phải thống nhất đơn vị; bên nhận nên áp dụng giới hạn hợp lý cho thời hạn và giá trị thời gian để phát hiện sai đơn vị.

#### Giới hạn thời gian hiệu lực

Hợp đồng nên định nghĩa:

- **Thời hạn tối đa:** ví dụ access token không sống lâu hơn một khoảng thời gian do chính sách xác định.
- **Clock skew/leeway:** dung sai đồng hồ nhỏ, có giới hạn; không dùng dung sai lớn để bù cho đồng hồ hệ thống sai.
- **Tuổi tối đa theo iat:** nếu cần hạn chế token được phát hành từ quá lâu trước đó.
- **Quan hệ giữa các mốc:** thường yêu cầu **iat ≤ exp**; nếu có **nbf**, kiểm tra mốc này không mâu thuẫn với thời điểm hết hạn và chính sách phát hành.
- **Giá trị cực đoan:** từ chối số âm, số ngoài phạm vi thời gian hệ thống hỗ trợ hoặc giá trị vượt giới hạn ứng dụng.

Leeway là chính sách của bên xác minh; nó không thay đổi giá trị NumericDate trong token. Chẳng hạn, một dung sai 30 giây chỉ là ví dụ minh họa, không phải con số bắt buộc cho mọi hệ thống.

### 2.3. Audience: string hoặc array các string

**aud** có thể là:

~~~json
{ "aud": "https://api.orders.example.com" }
~~~

hoặc:

~~~json
{
  "aud": [
    "https://api.orders.example.com",
    "https://api.reports.example.com"
  ]
}
~~~

Bên nhận phải hỗ trợ đúng các dạng mà hợp đồng cho phép và kiểm tra audience của mình bằng phép so khớp chính xác. Không chấp nhận **aud** là số, boolean, object, mảng rỗng hoặc mảng có phần tử không phải chuỗi. Hợp đồng có thể yêu cầu một audience duy nhất để thu hẹp phạm vi sử dụng.

### 2.4. Boolean, object và array trong claim mở rộng

Claim riêng có thể dùng kiểu JSON khác nếu hợp đồng định nghĩa rõ:

~~~json
{
  "email_verified": true,
  "cnf": {
    "jkt": "base64url-thumbprint"
  },
  "permissions": [
    "orders:read",
    "orders:create"
  ]
}
~~~

Ví dụ trên chỉ minh họa kiểu dữ liệu; **cnf** có cấu trúc và ý nghĩa theo các profile ràng buộc token tương ứng, còn **email_verified** và **permissions** cần được quy định theo giao thức/ứng dụng đang dùng.

Không nên chấp nhận một claim với nhiều kiểu thay thế như boolean true, chuỗi "true", số 1 và chuỗi "1" cùng mang một ý nghĩa. Quy định **một kiểu chuẩn** giúp các bên diễn giải nhất quán và tránh lỗi so sánh.

## 3. Claim mở rộng, tên claim và không gian tên

### 3.1. Registered, public và private claim names

RFC 7519 mô tả ba nhóm tên claim:

- **Registered Claim Names:** tên được đăng ký trong IANA JWT Claims Registry, như **iss**, **sub**, **aud**, **exp**.
- **Public Claim Names:** tên được dùng công khai, cần tránh xung đột; có thể đăng ký hoặc dùng tên collision-resistant, chẳng hạn tên dựa trên URI do tổ chức kiểm soát.
- **Private Claim Names:** tên do các bên thỏa thuận riêng; dễ trùng với claim do bên khác sử dụng.

Ví dụ tên claim riêng:

~~~json
{
  "https://claims.example.com/tenant_id": "tenant-42",
  "https://claims.example.com/token_use": "access"
}
~~~

Tên URI trong ví dụ là một cách tạo không gian tên ít xung đột; nó không có nghĩa bên nhận phải truy cập URI đó. Nếu dùng tên ngắn như **role**, **type**, **user** hoặc **scope_custom**, cần kiểm soát xung đột và định nghĩa một nguồn chuẩn duy nhất.

### 3.2. Quy định schema cho claim riêng

Mỗi claim riêng nên có mô tả tối thiểu:

| Thuộc tính schema | Câu hỏi phải trả lời |
|---|---|
| Tên claim | Tên chính xác, có phân biệt chữ hoa/thường? |
| Kiểu JSON | String, number, boolean, object hay array? |
| Bắt buộc? | Bắt buộc ở token profile/điểm tiếp nhận nào? |
| Miền giá trị | Enum, mẫu định dạng hoặc giới hạn số? |
| Kích thước | Độ dài chuỗi, số phần tử mảng, độ sâu object tối đa? |
| Ý nghĩa bảo mật | Claim có tham gia quyết định xác thực, quyền hoặc ràng buộc token không? |
| Quy tắc tương thích | Khi thêm giá trị mới, bên nhận cũ sẽ xử lý thế nào? |

Ví dụ schema khái niệm:

~~~yaml
claims:
  token_use:
    type: string
    required: true
    allowed_values: ["access"]
    max_length: 16
  tenant_id:
    type: string
    required: true
    min_length: 1
    max_length: 64
  permissions:
    type: array
    required: false
    item_type: string
    max_items: 32
~~~

Đây là ví dụ thiết kế, không phải schema tiêu chuẩn JWT. Với một API, chỉ khai báo những claim thực sự cần thiết; không đưa dữ liệu hồ sơ người dùng hoặc dữ liệu nhạy cảm vào token nếu bên nhận không cần chúng.

### 3.3. Claim không được nhận diện

Không có một quy tắc chung buộc mọi bên nhận phải từ chối mọi claim lạ. Cách xử lý phụ thuộc profile:

- Claim mở rộng không liên quan đến quyết định của bên nhận có thể được bỏ qua nếu hợp đồng cho phép.
- Claim bắt buộc nhưng thiếu, sai kiểu hoặc sai miền giá trị phải làm token bị từ chối.
- Claim mà chính sách bảo mật phụ thuộc vào phải được hiểu và kiểm tra; không được âm thầm bỏ qua khi không parse được.
- Không được diễn giải claim lạ thành quyền mới hoặc tự động cấp quyền dựa trên tên gần giống.

Điều này khác với JOSE header **crit**: extension được đánh dấu critical mà bên nhận không hiểu phải bị từ chối theo quy tắc JOSE. Claim trong payload và critical header có vai trò khác nhau.

## 4. Giới hạn giá trị và kích thước

JWT được truyền qua mạng và thường được parse ở nhiều thành phần. Nếu không giới hạn kích thước, độ sâu và miền giá trị, token có thể tạo áp lực bộ nhớ/CPU hoặc gây sai khác diễn giải giữa các hệ thống.

### 4.1. Giới hạn theo từng claim

Hợp đồng nên quy định các giới hạn cụ thể thay vì chỉ nói “giá trị hợp lệ”:

| Claim / dữ liệu | Giới hạn cần xác định | Ví dụ chính sách |
|---|---|---|
| **iss** | Tập giá trị được phép, độ dài tối đa | Khớp một issuer URI đã cấu hình |
| **sub** | Độ dài, định dạng, tính duy nhất trong phạm vi issuer | Chuỗi định danh không rỗng, tối đa theo schema |
| **aud** | Số audience tối đa, mỗi phần tử là chuỗi, giá trị được phép | Chỉ các audience được đăng ký cho contract |
| **exp / nbf / iat** | Kiểu số, phạm vi thời gian, thời hạn tối đa, dung sai | NumericDate theo giây và không vượt horizon cho phép |
| **jti** | Độ dài, entropy/tính duy nhất, thời gian lưu chống phát lại | Chuỗi định danh theo quy tắc phát hành |
| **scope** | Kiểu, cú pháp, số lượng và độ dài scope | Chuỗi phân tách bằng dấu cách theo OAuth |
| **permissions / roles** | Số phần tử, kiểu phần tử, tập giá trị | Chỉ các permission đã đăng ký |
| Claim object | Số trường, độ sâu, kích thước tổng | Không nhận object lồng quá sâu hoặc không cần thiết |

Các con số cụ thể phải dựa trên giao thức và hệ thống thực tế. Ví dụ, giới hạn aud tối đa 5 phần tử hoặc permissions tối đa 32 phần tử chỉ là lựa chọn minh họa; không phải giới hạn do RFC 7519 đặt ra.

### 4.2. Giới hạn kích thước toàn token

Ngoài giới hạn từng claim, cần quy định:

- Kích thước tối đa của chuỗi compact JWT nhận qua header/request.
- Kích thước tối đa của decoded header, payload và ciphertext.
- Số lượng claim tối đa và độ sâu object/array.
- Số lượng phần tử trong mảng và độ dài từng chuỗi.
- Giới hạn thời gian parse, xác minh chữ ký, giải mã và truy vấn trạng thái chống phát lại.

JWT không tự đặt một giới hạn kích thước chung phù hợp cho mọi ứng dụng. Giới hạn phải tương thích với đường truyền, proxy, gateway, cookie/header và các dịch vụ liên quan. Token vượt ngưỡng nên bị từ chối sớm với phản hồi có kiểm soát.

### 4.3. Cẩn trọng với dữ liệu nhạy cảm và dữ liệu thừa

Payload JWS được mã hóa Base64url nhưng không được mã hóa bí mật. Tránh đưa mật khẩu, secret, dữ liệu thanh toán hoặc thông tin nhạy cảm không cần thiết vào claim. Với JWE, vẫn phải giới hạn kích thước và chỉ giải mã ở bên nhận được phép; mã hóa không loại bỏ rủi ro token bị phát lại hoặc bị sử dụng sai mục đích.

Token càng lớn càng làm tăng băng thông, chi phí parse và nguy cơ bị cắt ở các thành phần trung gian. Ưu tiên claim tối thiểu, có ý nghĩa ổn định và đủ để bên nhận thực hiện kiểm tra.

## 5. Kiểm tra cấu trúc JSON và cách parse nhất quán

### 5.1. Payload phải là JSON object

JWT Claims Set theo RFC 7519 là một JSON object. Bên nhận phải từ chối payload không phải object, JSON sai cú pháp hoặc giá trị không tuân thủ quy tắc của profile.

Ví dụ không hợp lệ cho Claims Set:

~~~json
[
  "user-42",
  "orders:read"
]
~~~

Ví dụ hợp lệ về cấu trúc object, nhưng chưa chắc hợp lệ về hợp đồng:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "https://api.orders.example.com",
  "exp": 1794800600
}
~~~

Ví dụ thứ hai còn phải qua xác minh chữ ký, issuer, audience, thời hạn, token profile và quyền.

### 5.2. Tên claim trùng lặp

JSON có thể được parser xử lý khác nhau khi một object chứa tên thuộc tính lặp lại. RFC 7519 yêu cầu tên claim trong Claims Set phải duy nhất; parser có thể từ chối tên trùng hoặc dùng quy tắc thành viên xuất hiện sau cùng theo cách xử lý được RFC mô tả.

Để tránh hai thành phần diễn giải khác nhau, hợp đồng nên yêu cầu **từ chối JSON có tên claim trùng lặp**. Ví dụ sau phải bị từ chối theo chính sách này:

~~~json
{
  "aud": "https://api.orders.example.com",
  "aud": "https://api.inventory.example.com"
}
~~~

Nếu một tầng chọn giá trị đầu và tầng khác chọn giá trị cuối, quyết định audience có thể khác nhau giữa gateway và API. Không để dữ liệu trùng lặp tạo ra hai cách hiểu.

### 5.3. Kiểu dữ liệu phải được kiểm tra chính xác

Các ví dụ sau không tương đương:

~~~json
{
  "exp": 1794800600,
  "email_verified": true,
  "permissions": ["orders:read"]
}
~~~

~~~json
{
  "exp": "1794800600",
  "email_verified": "true",
  "permissions": "orders:read"
}
~~~

Ví dụ thứ hai đã biến number thành string, boolean thành string và array thành string. Không tự chuyển kiểu để “cứu” token. Việc coercion có thể khiến hai hệ thống đánh giá cùng một token khác nhau.

### 5.4. Parser và xử lý dữ liệu không tin cậy

- Dùng parser JSON và thư viện JOSE đã được kiểm chứng; tránh tự viết thuật toán parse/verify.
- Giới hạn độ dài đầu vào trước khi giải mã/parse và giới hạn độ sâu cấu trúc.
- Từ chối JSON sai cú pháp, kiểu không đúng, số ngoài phạm vi và dữ liệu không hỗ trợ.
- Không dùng claim chưa xác minh để tạo URL truy cập tùy ý, tải tài nguyên hoặc truy vấn nguồn khóa.
- Sau xác minh mật mã, tiếp tục kiểm tra schema và chính sách; chữ ký không thay thế kiểm tra nội dung.
- Nếu token được nhiều gateway/service parse, thống nhất parser policy và quy tắc duplicate member.

## 6. Ví dụ hợp đồng claim cho access token

Ví dụ dưới đây mô tả hợp đồng của API đơn hàng. Đây là schema khái niệm, không phải schema chuẩn của một thư viện:

~~~yaml
contract_id: orders-access-v1
token_profile: oauth2-jwt-access-rfc9068
required_claims:
  iss:
    type: string
    allowed_values:
      - "https://id.example.com"
  sub:
    type: string
    min_length: 1
    max_length: 128
  aud:
    type: string_or_array_of_strings
    must_contain: "https://api.orders.example.com"
    max_audiences: 2
  exp:
    type: numeric_date_seconds
    required: true
    max_lifetime_seconds: 600
  iat:
    type: numeric_date_seconds
    required: true
    max_age_seconds: 600
  jti:
    type: string
    required: true
    max_length: 128
  client_id:
    type: string
    required: true
    allowed_values:
      - "storefront-web"
  scope:
    type: string
    required: true
    syntax: oauth_space_delimited
    max_length: 512
custom_claims:
  tenant_id:
    type: string
    required: true
    min_length: 1
    max_length: 64
  permissions:
    type: array_of_strings
    required: false
    max_items: 32
limits:
  compact_token_max_bytes: 8192
  json_nesting_depth: 8
  duplicate_claim_names: reject
~~~

Các giới hạn số trong ví dụ là **quyết định minh họa của ứng dụng**. Chúng cần được điều chỉnh theo kiến trúc, profile và nhu cầu vận hành. Đối với RFC 9068, phải đáp ứng đầy đủ các claim và quy tắc của hồ sơ; schema ví dụ không thay thế việc đọc tiêu chuẩn.

Một payload minh họa:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "https://api.orders.example.com",
  "client_id": "storefront-web",
  "iat": 1794800000,
  "exp": 1794800600,
  "jti": "at-7f19a2",
  "scope": "orders:read orders:create",
  "tenant_id": "tenant-42",
  "permissions": ["orders:read"]
}
~~~

Payload này chỉ minh họa các claim và kiểu dữ liệu; nó **chưa phải JWT đã ký** và chưa đủ để cấp quyền. API vẫn phải xác minh chữ ký, issuer, audience, loại token, thời gian, scope và quyền truy cập đối tượng đơn hàng cụ thể.

## 7. Luồng kiểm tra claims

~~~mermaid
flowchart TD
    A[Nhận JWT] --> B[Kiểm tra cấu trúc và giới hạn kích thước]
    B --> C{Payload là JSON object hợp lệ?}
    C -->|Không| X[Từ chối]
    C -->|Có| D{Tên claim có trùng?}
    D -->|Có| X
    D -->|Không| E[Xác minh chữ ký hoặc giải mã theo contract]
    E --> F{Bảo vệ mật mã hợp lệ?}
    F -->|Không| X
    F -->|Có| G{Đủ claim bắt buộc?}
    G -->|Không| X
    G -->|Có| H{Đúng kiểu và miền giá trị?}
    H -->|Không| X
    H -->|Có| I{Thời gian và audience hợp lệ?}
    I -->|Không| X
    I -->|Có| J{Scope và quyền tài nguyên hợp lệ?}
    J -->|Không| X
    J -->|Có| K[Chấp nhận cho thao tác tương ứng]
~~~

Pseudocode khái niệm:

~~~text
validateClaims(claims, contract, operation, now):
    reject nếu claims không phải JSON object
    reject nếu có tên claim trùng lặp
    reject nếu kích thước/độ sâu/số claim vượt giới hạn

    for each required claim in contract:
        reject nếu claim bị thiếu
        reject nếu kiểu JSON không đúng schema
        reject nếu giá trị rỗng hoặc ngoài miền cho phép

    kiểm tra iss và aud theo contract
    kiểm tra exp, nbf, iat và giới hạn tuổi/thời hạn
    kiểm tra claim riêng như purpose, tenant_id theo profile
    kiểm tra scope/permissions cho operation
    kiểm tra quyền truy cập tài nguyên cụ thể
    ACCEPT chỉ khi mọi điều kiện đạt
~~~

Luồng đầy đủ phải xác minh chữ ký/giải mã theo hợp đồng trước khi tin claim. Có thể kiểm tra kích thước, cấu trúc và cú pháp JSON trước để từ chối sớm, nhưng không được sử dụng claim chưa xác minh để cấp quyền hoặc tạo tác dụng phụ.

## 8. Các lỗi thường gặp và kết quả mong đợi

| Tình huống | Lỗi thiết kế | Kết quả đúng |
|---|---|---|
| Thiếu **exp** trong profile yêu cầu exp | Cho phép token không có hạn cuối | Từ chối |
| **exp** là chuỗi "1794800600" | Tự chuyển string thành number | Từ chối sai kiểu |
| **exp** dùng mili giây | Diễn giải sai đơn vị thời gian | Từ chối theo kiểm tra phạm vi/thời hạn |
| **aud** là object hoặc array chứa số | Chỉ kiểm tra claim tồn tại | Từ chối sai kiểu |
| **sub** rỗng | Dùng định danh không hợp lệ | Từ chối |
| **iat** nằm quá xa trong tương lai | Không kiểm tra thời điểm phát hành | Từ chối |
| **exp** đã qua | Chỉ xác minh chữ ký | Từ chối hết hạn |
| **nbf** nằm trong tương lai | Bỏ qua thời điểm bắt đầu hiệu lực | Từ chối cho đến khi hợp lệ |
| **scope** là array trong profile yêu cầu string | Coercion kiểu dữ liệu | Từ chối |
| Thiếu **client_id** trong RFC 9068 | Áp dụng quy tắc JWT chung thay cho profile | Từ chối |
| Claim **tenant_id** sai kiểu | Tin claim riêng không có schema | Từ chối |
| Hai claim cùng tên nhưng khác giá trị | Parser các tầng chọn giá trị khác nhau | Từ chối theo chính sách duplicate |
| Token có payload quá lớn | Không giới hạn kích thước | Từ chối trước khi tiêu tốn tài nguyên quá mức |
| Có claim lạ nhưng profile cho phép bỏ qua | Từ chối mọi claim không nhận diện mà không có lý do | Xử lý theo chính sách profile; không cấp quyền từ claim lạ |

## 9. Checklist hoàn thiện hợp đồng claims

**Tính đầy đủ**

- [ ] Xác định rõ token profile và tập claim bắt buộc cho từng điểm tiếp nhận.
- [ ] Phân biệt claim registered của RFC 7519 với claim bắt buộc theo profile như RFC 9068 hoặc OIDC.
- [ ] Không tự thêm mặc định cho claim bắt buộc bị thiếu.

**Kiểu và giá trị**

- [ ] Mỗi claim có kiểu JSON chính xác và miền giá trị rõ ràng.
- [ ] **iss**, **sub**, **aud**, **jti**, **client_id**, **scope** được kiểm tra theo đúng ý nghĩa và profile.
- [ ] **exp**, **nbf**, **iat** dùng NumericDate theo giây và được kiểm tra phạm vi, thứ tự, thời hạn.
- [ ] Có giới hạn độ dài chuỗi, số phần tử mảng, độ sâu object và số claim.
- [ ] Không tự chuyển kiểu, trim hoặc chuẩn hóa định danh ngoài quy tắc đã định nghĩa.

**Parser và giới hạn**

- [ ] Payload là JSON object hợp lệ.
- [ ] Tên claim trùng lặp bị xử lý nhất quán; ưu tiên từ chối.
- [ ] Kích thước compact token, decoded payload và thời gian parse/xác minh có giới hạn.
- [ ] Claim chưa xác minh không được dùng để cấp quyền hoặc tạo tác dụng phụ.

**Vận hành**

- [ ] Bên phát hành và bên nhận dùng cùng schema/version của hợp đồng.
- [ ] Có kiểm thử cho claim thiếu, sai kiểu, ngoài miền, thời gian sai đơn vị và token quá lớn.
- [ ] Có chính sách tương thích khi thêm claim hoặc thêm giá trị enum mới.
- [ ] Không đưa dữ liệu nhạy cảm không cần thiết vào JWT.

**Điều cần nhớ:** Một claim hợp lệ phải **có mặt khi được yêu cầu, đúng kiểu, đúng miền giá trị và đúng ý nghĩa trong token profile**. Chữ ký hợp lệ không làm cho dữ liệu sai schema trở thành dữ liệu đáng tin cậy.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): Claims Set, registered claim names, NumericDate và quy tắc xử lý tên claim.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và các trường khóa.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): Thuật toán JOSE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Thực hành xác minh JWT và phòng tránh nhầm lẫn.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Claim bắt buộc và quy tắc của JWT access token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): Claim và quy tắc xác minh ID token.
- [IANA JSON Web Token Claims Registry](https://www.iana.org/assignments/jwt/jwt.xhtml): Danh mục registered claim names.
