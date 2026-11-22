# Tham số subject_token, subject_token_type và requested_token_type

## 1. Bối cảnh: vì sao cần trao đổi token?

Trong hệ thống Spring Boot sử dụng **Spring Security** và **Spring Authorization Server** để xây dựng **OAuth 2.0/OpenID Connect Authorization Server**, một dịch vụ thường nhận access token từ bên ngoài nhưng lại cần gọi một dịch vụ khác với **phạm vi quyền, đối tượng nhận token hoặc ngữ cảnh tin cậy khác**.

Ví dụ, ứng dụng đặt phòng sử dụng ba thành phần:

- `booking-web`: client đã lấy access token cho người dùng Lan.
- `booking-api`: Resource Server nhận token có audience là Bookings API.
- `payment-api`: API nội bộ cần token chỉ dành cho việc xem trạng thái thanh toán.

`booking-api` không nên lấy nguyên access token dùng cho chính nó rồi chuyển tiếp cho `payment-api` nếu audience không phù hợp. Một phương án là **OAuth 2.0 Token Exchange**, chuẩn hóa trong **RFC 8693**. `booking-api`, khi đóng vai OAuth client, trình một token hiện có cho Authorization Server (AS) và yêu cầu phát hành một token khác phù hợp với đích sử dụng.

Trong Token Exchange, ba tham số rất quan trọng:

- **`subject_token`**: token đầu vào đại diện cho chủ thể mà bên yêu cầu thực hiện trao đổi thay mặt.
- **`subject_token_type`**: định danh loại **token đầu vào**, để AS biết ý nghĩa và cách xác minh.
- **`requested_token_type`**: loại **token đầu ra mong muốn**, là tham số tùy chọn, không phải bằng chứng rằng client được phép nhận mọi loại token.

Bài học thuộc chương **Token Exchange** và giải thích chi tiết các tham số này trong bối cảnh thiết kế, cấu hình, bảo mật, kiểm thử và vận hành Authorization Server bằng Spring Security và Spring Authorization Server.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu đúng tham số nào bắt buộc, tham số nào tùy chọn theo RFC 8693.
2. Giải thích sự khác nhau giữa **danh tính/chức năng token** và **định dạng kỹ thuật token**.
3. Viết được Token Exchange Request dùng `application/x-www-form-urlencoded`.
4. Giải thích vì sao `subject_token` không thay thế việc xác thực OAuth client.
5. Kiểm tra chính xác `issued_token_type` và `token_type` trong phản hồi.
6. Phân biệt trao đổi token theo kiểu impersonation với delegation có actor.
7. Thiết lập registered client và nắm được các điểm xử lý Token Exchange của Spring Authorization Server.
8. Thiết kế chính sách audience/resource/scope, TTL và thu hồi token.
9. Kiểm thử các trường hợp thiếu tham số, sai token type, sai audience, token hết hạn và yêu cầu nâng quyền.

## 2. Tổng quan luồng RFC 8693

Token Exchange dùng **Token Endpoint** của OAuth 2.0 với grant type cố định:

```text
urn:ietf:params:oauth:grant-type:token-exchange
```

Nó không phải redirect flow, không sinh authorization code và không yêu cầu trình duyệt đi qua trang login/consent ở chính thời điểm trao đổi.

```mermaid
sequenceDiagram
    participant W as booking-web
    participant B as booking-api / OAuth client
    participant AS as Authorization Server / STS
    participant P as payment-api / Resource Server

    W->>B: Gọi Bookings API với access token đầu vào
    B->>B: Kiểm tra token dùng để gọi chính B
    B->>AS: POST /oauth2/token<br/>client authentication + token-exchange grant<br/>subject_token + subject_token_type<br/>requested_token_type + audience/scope
    AS->>AS: Xác thực client; kiểm tra token đầu vào và policy
    AS->>AS: Quyết định loại token, audience, scope, TTL
    AS-->>B: Token mới + issued_token_type + token_type
    B->>P: Gọi Payment API với access token mới
    P->>P: Xác minh issuer, audience, hạn và quyền
    P-->>B: Trả dữ liệu được phép
```

Ví dụ này giả định AS được cấu hình để tin token đầu vào và cho client `booking-api` trao đổi token sang một token giới hạn quyền dành cho `payment-api`. RFC định nghĩa giao thức trao đổi, **không tự cấp quyền trao đổi cho mọi client**.

### 2.1. Nhìn ở góc độ Authorization Server

AS phải trả lời ít nhất bốn câu hỏi:

1. **Ai đang gửi request?** OAuth client được xác thực hoặc nhận diện theo phương thức đã đăng ký.
2. **`subject_token` là gì?** Token có thật, còn hiệu lực, được issuer đáng tin phát hành và đại diện cho chủ thể nào?
3. **Client có được phép trao đổi token này không?** Kiểm tra grant registration, ràng buộc token/client/tenant và chính sách impersonation/delegation.
4. **Có thể phát token loại nào, cho audience/resource và scope nào?** Kết quả phải tuân thủ chính sách, không đơn giản sao chép mọi quyền từ input.

Không nên bỏ bất kỳ câu hỏi nào chỉ vì client trình một JWT có chữ ký hợp lệ.

## 3. Tham số Token Exchange Request: bắt buộc và tùy chọn

Theo RFC 8693 `2.1, các tham số chính gồm:

| Tham số | RFC 8693 | Chức năng |
|---|---|---|
| `grant_type` | **Bắt buộc** | Có giá trị `urn:ietf:params:oauth:grant-type:token-exchange` |
| `subject_token` | **Bắt buộc** | Token đại diện chủ thể mà client đang yêu cầu trao đổi thay mặt |
| `subject_token_type` | **Bắt buộc** | URI định danh loại token được truyền trong `subject_token` |
| `requested_token_type` | **Tùy chọn** | URI mô tả loại token đầu ra mong muốn |
| `resource` | Tùy chọn | URI tài nguyên/đích sử dụng token mới |
| `audience` | Tùy chọn | Định danh logic của bên nhận token mới |
| `scope` | Tùy chọn | Phạm vi quyền muốn có ở token đầu ra |
| `actor_token` | Tùy chọn | Token đại diện bên đang hành động thay mặt subject |
| `actor_token_type` | Có điều kiện | **Bắt buộc khi có `actor_token`**; không được gửi nếu không có `actor_token` |

Bảng này mô tả **hợp đồng chuẩn RFC**. Một Authorization Server cụ thể có thể giới hạn danh sách token type, target, audience hoặc yêu cầu thêm thông tin theo chính sách. “Tùy chọn trong RFC” không có nghĩa mọi server phải hỗ trợ mọi tổ hợp.

### 3.1. Ba tham số trọng tâm liên hệ với nhau ra sao?

Có thể hình dung request hỏi AS:

> Tôi là client đã được xác thực. Đây là **subject_token** mang loại **subject_token_type**. Tôi muốn nhận một token loại **requested_token_type** để sử dụng theo target/scope đã yêu cầu, nếu chính sách cho phép.

```mermaid
flowchart TD
    IN["subject_token<br/>giá trị token đầu vào"]
    INTYPE["subject_token_type<br/>URI mô tả loại input"]
    OUTTYPE["requested_token_type<br/>URI loại output mong muốn"]
    AUTH["Client authentication<br/>+ registered grant"]
    POLICY["Kiểm tra token đầu vào<br/>+ policy audience/scope/actor"]
    ISSUED["Token được cấp<br/>access_token field"]
    TYPE["issued_token_type<br/>loại token THỰC TẾ"]
    METHOD["token_type<br/>cách sử dụng token"]

    IN --> POLICY
    INTYPE --> POLICY
    OUTTYPE --> POLICY
    AUTH --> POLICY
    POLICY -->|"Được phép"| ISSUED
    ISSUED --> TYPE
    ISSUED --> METHOD
```

**Không được nhầm:** `requested_token_type` nằm trong **request**; `issued_token_type` nằm trong **response**. Client phải đọc thông tin đầu ra thực tế, không mặc nhiên coi mong muốn đã được chấp nhận.

## 4. `subject_token`: token đầu vào đại diện cho ai?

`subject_token` là **giá trị security token hiện có** mà client đưa cho AS. Theo RFC 8693, nó đại diện cho danh tính của bên mà request đang được thực hiện thay mặt; chủ thể (*subject*) của token đầu ra thông thường có liên hệ với chủ thể của token đầu vào.

Trong ví dụ:

```text
subject_token = ACCESS_TOKEN_DANH_CHO_BOOKING_API
```

Đây là **placeholder**, không phải token thật. Khi có người dùng Lan, token đầu vào có thể chứa/biểu diễn `sub=user-42`. AS có thể xét phát token cho `payment-api` với cùng subject nhưng quyền được điều chỉnh cho API đích.

### 4.1. Subject là ai, client là ai?

Ba vai trò có thể khác nhau:

| Vai trò | Trong ví dụ | Ý nghĩa |
|---|---|---|
| **Subject** | `user-42` (Lan) | Danh tính mà quyền truy cập cuối cùng liên quan |
| **Requesting client** | `booking-api` khi gọi Token Endpoint | Thành phần thực hiện token exchange và cần được AS cho phép |
| **Target/Resource Server** | `payment-api` | Bên nhận và kiểm tra token mới |

Không nên thay `sub` trong token mới bằng `client_id` chỉ vì `booking-api` đang gọi Token Endpoint. Nếu ứng dụng muốn token đại diện **chỉ cho client**, đó là use case khác và phải được mô hình hóa rõ theo chính sách.

### 4.2. `subject_token` không phải client secret

Client có thể xác thực bằng:

- `client_secret_basic`;
- `private_key_jwt`;
- mTLS;
- hoặc phương thức phù hợp với loại client và chính sách AS.

Token đầu vào ở `subject_token` **không tự chứng minh client có quyền trao đổi**. Kẻ tấn công có thể có được một bearer token từ nơi khác; nếu AS cho bất kỳ client nào dùng token đó để xin token cho một audience mới, hệ thống dễ trở thành điểm nâng quyền.

### 4.3. Kiểm tra giá trị subject token

AS cần xác minh bằng quy trình tương ứng với loại token và issuer đáng tin:

- Token có cấu trúc phù hợp `subject_token_type` không?
- Issuer và chữ ký có đáng tin? Nếu opaque, có cơ chế introspection hoặc tra trạng thái được phép không?
- `exp`, `nbf`, trạng thái thu hồi và các ràng buộc khác có hợp lệ?
- Token được phát hành cho audience/resource nào, có được phép dùng làm input exchange không?
- Token thuộc subject, tenant, client hoặc trust domain nào?
- Có thể chứng minh requesting client được quyền đổi token đó không?
- Token có bị ràng buộc chứng chỉ/khóa hoặc cơ chế sender-constrained cần xác minh không?

**Một JWT decode được không đồng nghĩa hợp lệ.** Không chỉ Base64-decode payload để lấy `sub` rồi cấp token mới. Việc kiểm tra phải dựa trên trust/validation thực sự, có chống nhầm issuer và audience.

### 4.4. Subject token có bắt buộc là access token không?

**Theo RFC, không.** `subject_token` là security token theo loại đã khai báo; các profile có thể dùng JWT, access token, ID token hoặc dạng khác nếu server hỗ trợ.

**Theo implementation, có thể bị giới hạn.** Ví dụ một phiên bản Spring Authorization Server có thể chỉ xử lý một tập token type được converter/provider mặc định hỗ trợ. Đừng suy ra mọi token type xuất hiện trong RFC đều được Spring xử lý sẵn.

Đặc biệt, **ID token OIDC không được dùng làm Bearer token gọi API**. Nếu một hệ thống muốn nhận ID token làm `subject_token` trong luồng exchange, cần thiết kế trust, audience, replay, consent/policy và khả năng hỗ trợ riêng; không coi đó là hành vi tự động hoặc được phép ở mọi AS.

## 5. `subject_token_type`: định danh loại token đầu vào

Tham số `subject_token_type` **bắt buộc** và có giá trị là **URI định danh token type**. Một số giá trị chuẩn quan trọng:

```text
urn:ietf:params:oauth:token-type:access_token
urn:ietf:params:oauth:token-type:refresh_token
urn:ietf:params:oauth:token-type:id_token
urn:ietf:params:oauth:token-type:jwt
urn:ietf:params:oauth:token-type:saml1
urn:ietf:params:oauth:token-type:saml2
```

Các URI này không phải URL phải gọi qua HTTP; chúng là **định danh kiểu** đã được chuẩn hóa.

### 5.1. `access_token` và `jwt` khác nhau căn bản

Đây là chỗ dễ nhầm nhất trong Token Exchange.

| Giá trị `subject_token_type` | Điều đang được khai báo | Không khẳng định |
|---|---|---|
| `urn:ietf:params:oauth:token-type:access_token` | Đây là OAuth access token theo ngữ nghĩa của hệ thống phát hành | Token phải có định dạng opaque |
| `urn:ietf:params:oauth:token-type:jwt` | Đây là token **định dạng JWT** | JWT đó chắc chắn là OAuth access token |
| `urn:ietf:params:oauth:token-type:id_token` | Đây là OIDC ID token | Token dùng trực tiếp làm credential API |
| `urn:ietf:params:oauth:token-type:refresh_token` | Đây là OAuth refresh token | Token được phép đưa vào exchange trong deployment hiện tại |

**Access token là một loại credential theo chức năng. JWT là một định dạng biểu diễn token.** Access token có thể chính là một JWT; khai báo `access_token` vẫn có thể đúng, nếu AS hiểu input là OAuth access token của hệ thống phát hành và có cơ chế xác minh phù hợp.

Ngược lại, một JWT được ký bởi một issuer tin cậy có thể là ID token hoặc JWT assertion dành cho mục đích khác, không mặc nhiên là access token.

### 5.2. Tại sao không đoán type từ dấu chấm trong token?

JWT thường có ba phần phân tách bằng dấu chấm, nhưng:

- Có dấu chấm không chứng minh issuer đáng tin hoặc chữ ký hợp lệ.
- Không phải mọi JWT đều là access token.
- Một access token có thể opaque, không parse được tại client.
- Ý nghĩa dùng `access_token` hay `jwt` tùy trust contract và profile của AS.

Client phải khai báo **type đúng theo hợp đồng với AS**. Server phải kiểm tra type được hỗ trợ và chứng minh input thuộc loại đã khai báo; không chỉ tin chuỗi `subject_token_type` do caller gửi.

### 5.3. Khi `subject_token_type` không khớp input

Giả sử client gửi:

```text
subject_token      = OPAQUE_ACCESS_TOKEN
subject_token_type = urn:ietf:params:oauth:token-type:jwt
```

Nếu AS chỉ xử lý JWT cho type `jwt`, input opaque không thể xác minh theo nhánh đó. AS phải **từ chối hoặc áp dụng xử lý hợp lệ theo profile**; không được đoán/đổi type để cấp token vô điều kiện.

Ngược lại, nếu input là JWT access token của chính AS, khai báo `access_token` có thể là lựa chọn đúng dù chuỗi token trông giống JWT.

## 6. `requested_token_type`: yêu cầu loại token đầu ra

`requested_token_type` là **tùy chọn** trong RFC 8693. Nó mô tả loại security token mà client **muốn AS phát hành**.

Ví dụ:

```text
requested_token_type=urn:ietf:params:oauth:token-type:access_token
```

Ý nghĩa: client xin **OAuth access token** ở đầu ra. Đây là yêu cầu thường gặp khi một dịch vụ cần token để gọi Resource Server khác.

### 6.1. Nếu bỏ qua `requested_token_type` thì sao?

RFC 8693 không quy định một kiểu đầu ra mặc định chung cho mọi Authorization Server. Khi tham số bị bỏ qua, loại token được phát hành do **AS quyết định**, có thể dựa trên target resource/audience và chính sách triển khai.

Vì thế:

- Không suy ra thiếu `requested_token_type` tương đương bắt buộc `access_token` theo RFC.
- Không suy ra server sẽ phát JWT chỉ vì input là JWT.
- Không suy ra server bắt buộc cấp đúng loại đã yêu cầu.
- Phải kiểm tra **`issued_token_type`** trong response để biết kết quả thực tế.

Một triển khai Spring có thể chọn access token như loại đầu ra hỗ trợ mặc định. Đây là **khả năng implementation**, không phải quy tắc chung của RFC.

### 6.2. Xin `jwt` có đồng nghĩa xin JWT access token không?

**Không nhất thiết.** Theo RFC, `urn:ietf:params:oauth:token-type:jwt` nói về **định dạng JWT**, còn `...:access_token` nói về **ngữ nghĩa OAuth access token**.

| Request | Ý định | Hành vi cần xác minh |
|---|---|---|
| `requested_token_type=...:access_token` | Muốn access token để truy cập tài nguyên | AS có thể phát JWT access token hoặc opaque access token theo chính sách |
| `requested_token_type=...:jwt` | Muốn token có cấu trúc JWT | Server/profile có hỗ trợ đầu ra JWT theo ngữ nghĩa mong muốn không? |
| `requested_token_type=...:id_token` | Muốn ID token OIDC | Không có nghĩa AS phải phát ID token ngoài OIDC authentication context phù hợp |
| Không gửi `requested_token_type` | Cho AS chọn | Kiểm tra `issued_token_type` và chính sách profile |

Một hệ thống cần token JWT **để gọi API** thường vẫn nên thiết kế dưới ngữ nghĩa OAuth **access token**, đồng thời cấu hình định dạng access token phía AS và hợp đồng Resource Server. Không cố ép loại `jwt` chỉ để phân biệt opaque/JWT nếu AS không hỗ trợ profile đó.

### 6.3. Yêu cầu không phải ủy quyền

Request:

```text
requested_token_type=urn:ietf:params:oauth:token-type:access_token
```

không có nghĩa client được phép nhận token đó. AS còn phải quyết định client nào được trao đổi, input token nào đáng tin, target nào hợp lệ, các scope nào được cấp và token output có làm tăng quyền trái chính sách không.

## 7. So sánh ba tham số trên cùng một ví dụ

Giả sử `booking-api` có một access token đã nhận ở incoming request và cần token mới dành cho `payment-api`:

| Tham số | Ví dụ giá trị | Vai trò |
|---|---|---|
| `subject_token` | `ACCESS_TOKEN_FOR_BOOKING_API` | **Token đầu vào** mang ngữ cảnh user |
| `subject_token_type` | `urn:ietf:params:oauth:token-type:access_token` | Loại **đầu vào** |
| `requested_token_type` | `urn:ietf:params:oauth:token-type:access_token` | Loại **đầu ra mong muốn** |
| `audience` | `https://payments.example.com` | Bên dự kiến nhận token mới |
| `scope` | `payments.status.read` | Quyền mong muốn ở token mới |

Kết quả hợp lệ không đơn giản là sao chép token đầu vào. AS có thể tạo access token mới:

```text
issued_token_type = urn:ietf:params:oauth:token-type:access_token
sub               = user-42           (nếu chính sách giữ subject)
aud               = https://payments.example.com
scope             = payments.status.read
exp               = thời điểm AS quyết định
```

AS cần kiểm tra rằng `booking-api` thực sự có quyền yêu cầu token cho `payment-api`, token đầu vào được phép trao đổi, và người dùng/tenant có quyền liên quan tới `payments.status.read`. **Không được tự tăng scope chỉ vì client thêm nó vào form.**

## 8. HTTP request chuẩn theo RFC 8693

Ví dụ Token Exchange Request bằng `application/x-www-form-urlencoded`. Dữ liệu trong body là **ví dụ giá trị đã được biểu diễn dễ đọc**; khi gửi thực tế phải URL-encode các ký tự đặc biệt:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=ACCESS_TOKEN_FOR_BOOKING_API
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=https%3A%2F%2Fpayments.example.com
&scope=payments.status.read
```

Các dấu xuống dòng trong body chỉ để dễ đọc; form thực tế được gửi như một chuỗi URL-encoded. Ví dụ sử dụng **confidential client** với `client_secret_basic`; cách xác thực client phụ thuộc registration. Không đưa client secret hoặc subject token thật vào URL query, browser history, Git hay log.

### 8.1. Từng tham số thuộc bước nào?

```text
grant_type
  -> Chọn giao thức token exchange (RFC 8693).

Authorization: Basic ...
  -> Xác thực requesting OAuth client.

subject_token + subject_token_type
  -> Mô tả credential ĐẦU VÀO để AS xác minh.

requested_token_type
  -> Bày tỏ loại credential ĐẦU RA mong muốn.

audience / resource / scope
  -> Bày tỏ đích nhận và quyền của token mới.
```

Chỉ có `subject_token` không đủ để AS biết nó cần được xác minh như OAuth access token hay JWT loại khác; `subject_token_type` được chuẩn yêu cầu để làm rõ điều này.

### 8.2. Tham số `resource` so với `audience`

RFC 8693 cho phép client chỉ rõ target bằng:

- `resource`: URI thể hiện service/resource dự kiến sử dụng token.
- `audience`: định danh logic cho bên nhận token.
- Có thể có **nhiều** `resource` và/hoặc `audience` trong một request nếu server/profile hỗ trợ.

Tuy nhiên, **nhiều đích không có nghĩa nhiều quyền được cấp mặc định**. AS phải xác định token mới có thể được dùng ở những đích nào, giới hạn scope, áp dụng policy và từ chối các target không được phép.

Một thực hành an toàn là xin token cho **một audience cụ thể** khi hệ thống không cần token đa audience. Resource Server phải xác minh `aud`/target thích hợp để chống dùng token sai nơi (*token substitution*).

## 9. Phản hồi Token Exchange và `issued_token_type`

Phản hồi thành công cho trường hợp phát **OAuth Bearer access token** có thể là:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "NEW_ACCESS_TOKEN_FOR_PAYMENTS",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "payments.status.read"
}
```

Theo RFC 8693:

- **`access_token`**: trường response **bắt buộc** mang token được phát hành. Tên trường có lịch sử từ OAuth và có thể vẫn được dùng ngay cả khi token được phát hành không mang ngữ nghĩa access token.
- **`issued_token_type`**: trường **bắt buộc** mô tả loại token **thực tế** mà AS cấp.
- **`token_type`**: trường **bắt buộc** mô tả cách sử dụng token, ví dụ `Bearer` nếu đó là OAuth Bearer access token.
- **`expires_in`**: thông tin thời hạn, tùy trường hợp và cách triển khai.
- **`scope`**: phạm vi quyền thực sự được cấp nếu response cung cấp.
- **`refresh_token`**: không được mặc nhiên kỳ vọng; còn tùy loại exchange và chính sách.

### 9.1. `issued_token_type` khác `token_type`

Đây là hai trường khác nhau:

| Trường response | Ví dụ | Trả lời |
|---|---|---|
| `issued_token_type` | `urn:ietf:params:oauth:token-type:access_token` | “AS đã cấp loại **security token** nào?” |
| `token_type` | `Bearer` | “Credential được sử dụng theo **cơ chế truy cập** nào?” |

Khi AS phát một **JWT không phải OAuth access token**, RFC có ví dụ `issued_token_type=...:jwt` và `token_type=N_A`. Không được gửi token đó đến API dưới dạng Bearer chỉ vì response field chứa tên `access_token`.

### 9.2. Token mới có bắt buộc cùng hạn với token cũ?

Không. Token đầu ra có thể có TTL và claims khác do chính sách AS quyết định. RFC không đặt ràng buộc mặc định rằng thời hạn output luôn bằng phần thời gian còn lại của input.

Một thiết kế an toàn thường cân nhắc **giới hạn TTL output theo rủi ro, nguồn subject token và target**, tránh cấp output quá dài cho input ngắn hạn hoặc ít tin cậy. Nhưng đó là **quy tắc chính sách cần triển khai/kiểm thử**, không phải mệnh đề đồng nhất thời hạn do RFC ép buộc.

## 10. Subject token khác actor token: impersonation và delegation

RFC 8693 hỗ trợ cả tình huống **impersonation** và **delegation**.

### 10.1. Impersonation (mô tả ở mức khái niệm)

Client trình token của một subject và xin token mới biểu diễn subject đó ở một trust context/target khác. Token đầu ra có thể chỉ mang thông tin subject, tùy chính sách.

**Rủi ro:** Nếu client tùy ý trao đổi token của user bất kỳ rồi nhận quyền không được phép, Token Exchange trở thành lỗ hổng giả mạo danh tính/nâng quyền. Cần chính sách rõ client nào được impersonate subject nào và cho target nào.

### 10.2. Delegation với actor

Khi cần biểu diễn **bên đang hành động thay mặt subject**, request có thể chứa:

```text
actor_token      = TOKEN_CUA_BOOKING_API
actor_token_type = urn:ietf:params:oauth:token-type:access_token
```

`actor_token_type` là **bắt buộc khi có actor_token**, và **không được đưa vào khi thiếu actor_token**, theo RFC.

Token JWT đầu ra có thể sử dụng claim `act` để ghi current actor, ví dụ minh họa:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://payments.example.com",
  "scope": "payments.status.read",
  "act": {
    "sub": "booking-api"
  }
}
```

**Đây là payload minh họa**, không phải JWT đã ký hoàn chỉnh. `act` phải đến từ thông tin đã được AS xác thực và policy chấp nhận. Không nên lấy `act.sub` từ form body do client tự khai mà coi là actor thật.

Các hệ thống có chuỗi delegation nhiều bước cần quản lý claims và lịch sử actor theo RFC. Resource Server chỉ nên dùng những claim/actor có ý nghĩa cho policy hiện tại; không coi cả lịch sử actor là quyền truy cập độc lập.

### 10.3. Ba tham số chính vẫn có vai trò riêng

Dù có hay không `actor_token`:

- `subject_token` vẫn mô tả **subject đầu vào**.
- `subject_token_type` vẫn mô tả **loại token đầu vào**.
- `requested_token_type` vẫn mô tả **loại token đầu ra mong muốn**.

Không nhầm `subject_token_type` với `actor_token_type`; chúng có thể khác nhau và phải được xác minh theo loại tương ứng.

## 11. Chính sách bảo mật: tránh nâng quyền và token substitution

Token Exchange hữu ích nhất khi giúp giảm hoặc điều chỉnh quyền cho một target cụ thể. Các kiểm tra không thể thiếu:

| Quyết định | Câu hỏi cụ thể |
|---|---|
| **Client authorization** | Requesting client có được đăng ký Token Exchange Grant không? |
| **Subject trust** | Token đầu vào do issuer đáng tin cấp, còn hạn và không bị thu hồi? |
| **Subject binding** | Client có được phép trao đổi token của subject đó không? |
| **Token type** | `subject_token_type` có tương thích giá trị thực và profile được hỗ trợ không? |
| **Requested type** | AS có hỗ trợ và cho phép loại đầu ra mong muốn? |
| **Audience/resource** | Target có được phép theo client, subject, tenant và policy không? |
| **Scope attenuation** | Scopes mới có nằm trong quyền tối đa được phép không? |
| **TTL and revocation** | Token mới sống bao lâu; xử lý thu hồi token gốc như thế nào? |
| **Delegation** | Nếu có actor, actor có được phép đại diện cho subject không? |

Một điều kiện thiết kế thường gặp:

```text
output_scopes ⊆ allowed_for_subject
output_scopes ⊆ allowed_for_requesting_client
output_scopes ⊆ allowed_for_target_resource
```

Đây là **invariant chính sách minh họa**, không phải phép lấy giao được RFC tự thực hiện cho mọi hệ thống. Trong một số use case, scope giữa các audience có tên khác nhau; khi đó cần **mapping chính sách minh bạch**, không thể so sánh chuỗi đơn giản.

### 11.1. Audience của input và audience của output

Một token đầu vào phát cho `booking-api` có thể được trao đổi thành token đầu ra phát cho `payment-api` khi AS có chính sách cho phép.

- `booking-api` phải xác minh incoming token được phép dùng để gọi nó.
- AS phải xác minh việc exchange từ ngữ cảnh đó sang `payment-api` được cho phép.
- `payment-api` phải chỉ chấp nhận token phù hợp audience của chính nó.

Không nên để `payment-api` chấp nhận trực tiếp token có audience `booking-api` để “tiết kiệm một bước”, vì có thể làm mất ranh giới truy cập và mở ra lỗi token substitution.

### 11.2. Không dùng Token Exchange để nâng quyền tùy ý

Ví dụ yêu cầu đáng nghi:

```text
subject_token       = token chỉ có bookings.read
requested scope     = payments.admin
requested audience  = https://payments.example.com
```

AS phải đối chiếu client/subject/tenant/target policy. Không được cấp `payments.admin` chỉ vì caller điền scope đó và có `subject_token` hợp lệ.

Nếu sản phẩm có trường hợp chuyển quyền giữa API với danh mục scope khác nhau, việc mapping phải được định nghĩa trong policy và audit được.

## 12. Input token và output token có cùng vòng đời không?

**Không mặc định.** Theo RFC 8693, việc token exchange thông thường **không làm thay đổi hiệu lực** của `subject_token` hoặc `actor_token` nếu loại token không có quy tắc one-time-use riêng.

Ngoài ra, một lần exchange thường **không tạo mối liên kết chặt chẽ** giữa input và output token. Điều đó có nghĩa:

- Thu hồi input token **không tự bảo đảm** mọi output token lập tức không còn hiệu lực.
- Gia hạn input token **không tự gia hạn** output token đã cấp.
- Input token còn hạn **không bảo đảm** output token được cấp hoặc còn hạn.
- Output token có thể có `exp`, audience và scope riêng.
- Nếu sản phẩm yêu cầu propagation của revocation, phải thiết kế cơ chế liên kết hoặc kiểm tra trạng thái riêng.

### 12.1. Ví dụ trục thời gian

| Thời điểm giả định | Sự kiện | Kết quả |
|---|---|---|
| 09:00 | Client nhận subject access token cho `booking-api` | Token gốc có hạn riêng |
| 09:02 | `booking-api` exchange sang token cho `payment-api` | Token mới có TTL riêng |
| 09:04 | Subject token bị thu hồi | AS từ chối các exchange mới dựa trên input bị thu hồi nếu kiểm tra trạng thái |
| 09:05 | `payment-api` nhận output token đã phát trước đó | Có thể vẫn chấp nhận nếu token mới còn hạn và không có revocation propagation |
| 09:07 | Output token hết hạn hoặc bị revoke | Resource Server phải từ chối theo cơ chế tương ứng |

Các mốc chỉ là ví dụ. Không nên hứa với người dùng “thu hồi token gốc sẽ cắt tất cả quyền từ exchange ngay lập tức” nếu hệ thống chưa triển khai linkage/revocation thực sự.

## 13. Spring Authorization Server hỗ trợ Token Exchange ra sao?

Spring Authorization Server hiện đại có các thành phần xử lý **OAuth 2.0 Token Exchange Grant** theo RFC 8693 tại Token Endpoint. Trong dòng thư viện Spring Authorization Server 1.5.x, các thành phần tiêu biểu gồm:

- `OAuth2TokenExchangeAuthenticationConverter`: đọc HTTP form request và tạo đối tượng authentication chứa tham số Token Exchange.
- `OAuth2TokenExchangeAuthenticationToken`: mang dữ liệu `subjectToken`, `subjectTokenType`, `requestedTokenType`, actor token, resources, audiences, scopes và additional parameters.
- `OAuth2TokenExchangeAuthenticationProvider`: provider xử lý grant theo những khả năng được hỗ trợ.
- `OAuth2TokenEndpointConfigurer`: cung cấp hook mở rộng converters/providers và handlers.
- `OAuth2AuthorizationService` / `OAuth2TokenGenerator`: phục vụ trạng thái authorization và tạo token theo mô hình framework.

**Quan trọng về phiên bản:** Spring Authorization Server 1.x và các thế hệ Spring Security tích hợp Authorization Server có thể khác nhau về package, signature và danh sách tính năng. Cần đọc tài liệu/API của **đúng phiên bản dependency** trước khi sao chép cấu hình.

### 13.1. RFC rộng hơn khả năng built-in của một phiên bản

RFC 8693 định nghĩa nhiều `subject_token_type` và `requested_token_type`, nhưng **không có nghĩa converter/provider mặc định của Spring hỗ trợ tất cả**.

Ví dụ, dòng Spring Authorization Server 1.5.x có các hạn chế đã được ghi nhận về việc nhận `id_token` làm subject token hoặc phát ID token làm output trong Token Exchange. Hành vi thường tập trung vào trao đổi token để cấp **access token**. Nếu cần nhận token ngoại hệ thống, SAML, ID token hoặc phát JWT với semantics khác, phải xác minh hỗ trợ theo phiên bản, thiết kế trust và bổ sung extension hoặc profile riêng khi thật sự cần.

**Không thay một tham số type để “lách” giới hạn API.** Đặc biệt, không gắn nhãn `access_token` cho ID token chỉ vì cả hai là JWT.

### 13.2. Đăng ký client được phép exchange

Ví dụ `booking-api` là confidential OAuth client được phép gọi Token Exchange Grant:

```java
String tokenExchangeGrant =
    "urn:ietf:params:oauth:grant-type:token-exchange";

RegisteredClient bookingApiClient = RegisteredClient
    .withId("booking-api-registration-id")
    .clientId("booking-api")
    .clientSecret(passwordEncoder.encode(secretFromSecureStore))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        new AuthorizationGrantType(tokenExchangeGrant))
    .scope("payments.status.read")
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
```

Đoạn Java minh họa **registered client policy**, không phải một Authorization Server hoàn chỉnh. Tên grant ở dạng URI chuẩn giúp tránh phụ thuộc vào sự có mặt của một hằng số ở mọi phiên bản thư viện.

Phải có thêm repository, issuer, JWK, authentication chain, token generator, authorization service và chính sách Token Exchange thực tế. Việc đăng ký grant **chỉ cho phép client gửi request thuộc grant đó**; không đồng nghĩa có quyền đổi mọi input token sang mọi audience/scope.

### 13.3. Phân biệt parsing, validation và token issuance

```mermaid
flowchart TD
    REQ["POST /oauth2/token<br/>Token Exchange Request"]
    AUTH["Client Authentication Filter<br/>Xác minh requesting client"]
    CONV["OAuth2TokenExchangeAuthenticationConverter<br/>Đọc form parameters"]
    OBJ["OAuth2TokenExchangeAuthenticationToken<br/>subject/actor/target/scopes"]
    PROVIDER["OAuth2TokenExchangeAuthenticationProvider<br/>và policy/trust"]
    TOKEN["OAuth2TokenGenerator<br/>Tạo token được cho phép"]
    STORE["OAuth2AuthorizationService<br/>Quản lý trạng thái"]
    RESP["OAuth2 Token Response<br/>issued_token_type/token_type"]

    REQ --> AUTH --> CONV --> OBJ --> PROVIDER
    PROVIDER --> TOKEN --> STORE --> RESP
```

Sơ đồ khái quát luồng xử lý; thứ tự và cách phối hợp filter/provider tùy implementation và phiên bản. Các endpoint mặc định có thể cấu hình khác nhau với Authorization Server SecurityFilterChain.

- **Converter** xác định request có đúng dạng và những parameter cơ bản được truyền ra sao.
- **Provider/policy** xác minh client/grant/input token, đánh giá audience/resource/scope và quyết định cấp token.
- **Token generator** tạo token phù hợp.
- **Response handler** trả phản hồi OAuth/RFC 8693.
- **Resource Server** vẫn tự kiểm tra token mới khi nó được sử dụng.

Không viết servlet filter để chỉ đọc chuỗi `subject_token` rồi ký JWT mới, vì cách đó dễ bỏ qua trust validation, client authentication và grant authorization.

## 14. Truy cập ba tham số trong mô hình Spring

Ở phạm vi **Spring Authorization Server 1.5.x**, `OAuth2TokenExchangeAuthenticationToken` cho phép đọc trực tiếp:

```java
// Ví dụ bên trong một thành phần xử lý đã nhận object này.
// Không tự dựng authentication từ request chưa được xác minh.
void inspectExchange(OAuth2TokenExchangeAuthenticationToken exchange) {

    String subjectToken = exchange.getSubjectToken();
    String subjectType = exchange.getSubjectTokenType();
    String requestedType = exchange.getRequestedTokenType();

    Set<String> audiences = exchange.getAudiences();
    Set<String> resources = exchange.getResources();
    Set<String> scopes = exchange.getScopes();

    // subjectToken là credential nhạy cảm:
    // KHÔNG log hoặc xuất nó ra response.
    // Quyết định cấp token thuộc provider/policy tin cậy.
}
```

Đây là **minh họa API model**, không phải một provider độc lập hoặc bằng chứng `subjectToken` đã được xác minh. Chỉ khi các lớp xử lý phù hợp hoàn tất trust/policy checks, hệ thống mới được phát token.

### 14.1. Tùy biến Token Endpoint có kiểm soát

`OAuth2TokenEndpointConfigurer` công bố các điểm mở rộng như:

```java
// Hình thức tích hợp hook, cần ghép vào SecurityFilterChain thật.
OAuth2AuthorizationServerConfigurer authorizationServer =
    OAuth2AuthorizationServerConfigurer.authorizationServer();

http
    .securityMatcher(authorizationServer.getEndpointsMatcher())
    .with(authorizationServer, as -> as
        .tokenEndpoint(endpoint -> endpoint
            .authenticationProvider(customExchangePolicyProvider)));
```

`customExchangePolicyProvider` là **provider nghiệp vụ do ứng dụng triển khai**. Chỉ bổ sung provider khi có lý do rõ và hiểu thứ tự xử lý. Provider phải dùng cơ chế xác thực, trust store, token generator, authorization service và OAuth error semantics phù hợp; không tự bỏ qua provider mặc định hoặc trả token thủ công.

Nếu provider mặc định đã nhận cùng loại authentication trước provider mới, việc thêm một provider vào danh sách có thể **không thực thi policy như mong muốn**. Cần kiểm tra thứ tự danh sách/provider matching và dùng hook phù hợp của phiên bản đang dùng, hoặc tích hợp policy ở lớp được framework hỗ trợ.

### 14.2. Token customizer không thay thế validation

`OAuth2TokenCustomizer<JwtEncodingContext>` có thể bổ sung claim cho **JWT access token** theo context đã được framework cấp. Nhưng nó không phải nơi xác thực `subject_token` hoặc quyết định client có được phép impersonate subject khác không.

Nếu cần claim `act` hoặc provenance:

- Chính sách phải xác minh actor thực sự trước khi cấp.
- Claims phải được dẫn xuất từ thông tin tin cậy sau validation.
- Resource Server phải biết cách diễn giải claim đó.
- Không copy toàn bộ JWT input thành claims mới hay log input token.

Việc thêm claim `exchange=true` không chứng minh security policy Token Exchange đã đúng.

## 15. Client gọi Token Exchange bằng Spring Boot

Client có thể gọi Token Endpoint qua HTTP library an toàn, Spring Security OAuth2 Client hoặc grant provider phù hợp phiên bản. Phần quan trọng ở bài này là **truyền đúng ba tham số** và đọc response đúng.

Ví dụ `RestClient` theo kiểu blocking:

```java
@Service
public class TokenExchangeGateway {

    private final RestClient tokenClient;

    public TokenExchangeGateway(RestClient.Builder builder) {
        this.tokenClient = builder
            .baseUrl("https://auth.example.com")
            .build();
    }

    public Map<String, Object> exchange(
            String clientId,
            String clientSecret,
            String incomingAccessToken) {

        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("grant_type",
            "urn:ietf:params:oauth:grant-type:token-exchange");
        form.add("subject_token", incomingAccessToken);
        form.add("subject_token_type",
            "urn:ietf:params:oauth:token-type:access_token");
        form.add("requested_token_type",
            "urn:ietf:params:oauth:token-type:access_token");
        form.add("audience", "https://payments.example.com");
        form.add("scope", "payments.status.read");

        return tokenClient.post()
            .uri("/oauth2/token")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .headers(headers ->
                headers.setBasicAuth(
                    clientId, clientSecret, StandardCharsets.UTF_8))
            .body(form)
            .retrieve()
            .body(new ParameterizedTypeReference<Map<String, Object>>() {});
    }
}
```

Đây là **snippet minh họa form body**. Ứng dụng thực cần import, HTTP client timeout, TLS, xử lý lỗi, retry có giới hạn, credential từ secret manager và DTO response có validation. Không hard-code client secret trong source và không log `incomingAccessToken`.

**Giới hạn thực tế:** Client API của Spring Security có thể cung cấp `TokenExchangeOAuth2AuthorizedClientProvider` hoặc grant-specific support trên phiên bản phù hợp. Khi dùng các abstraction đó, cần cấu hình nguồn `subject_token` và chính sách cache đúng; đừng giả định client library tự lấy một token tùy ý từ thread local.

### 15.1. Đừng lấy `subject_token` từ input không đáng tin

Nếu `booking-api` nhận bearer token từ incoming request, nó phải xác minh token phù hợp Resource Server policy trước khi quyết định trao đổi. Không lấy một JWT tự khai từ form field không có xác thực rồi chuyển cho AS như bằng chứng subject hợp lệ.

Khi trao đổi qua backend, phải giữ token bí mật trong memory/transaction thích hợp. Không đặt nó vào URL, query parameter, tracking event, form HTML công khai hoặc log HTTP chưa redaction.

## 16. Lỗi thường gặp và mã lỗi cần phân biệt

RFC 8693 quy định phản hồi lỗi Token Exchange tuân theo OAuth 2.0 Token Endpoint.

**Điểm đặc biệt:** Nếu request không hợp lệ hoặc `subject_token`/`actor_token` không hợp lệ, không được chấp nhận theo policy, RFC 8693 `2.2.2 yêu cầu lỗi **`invalid_request`**. Khi AS không muốn/không thể cấp token cho target `resource` hoặc `audience` được yêu cầu, mã **`invalid_target`** nên được dùng.

Các lỗi khác của OAuth có thể áp dụng tùy trường hợp, ví dụ `invalid_client` hoặc `unauthorized_client`.

| Tình huống | Nhóm lỗi kỳ vọng | Lưu ý |
|---|---|---|
| Thiếu `subject_token` | `invalid_request` | Thiếu tham số bắt buộc |
| Thiếu `subject_token_type` | `invalid_request` | Không suy đoán type từ chuỗi token |
| Trùng tham số không hợp lệ / form sai | `invalid_request` | Không lấy tùy tiện phần tử đầu/cuối |
| Subject token hết hạn/không tin cậy | `invalid_request` theo RFC 8693 | Có thể có mô tả chung, tránh lộ chi tiết trust internals |
| Actor token invalid | `invalid_request` | Nếu gửi actor token phải có actor token type |
| Có `actor_token_type` nhưng không có actor token | `invalid_request` | Tổ hợp không được phép |
| Target audience/resource không được hỗ trợ | `invalid_target` thường phù hợp | Cân nhắc chính sách trả lỗi để tránh enumeration |
| Client auth sai | `invalid_client` | Độc lập subject token |
| Client không được dùng grant | `unauthorized_client` hoặc lỗi theo contract framework | Grant phải được registered client cho phép |
| Yêu cầu token type không hỗ trợ | Lỗi theo RFC/profile/implementation | Không tự cấp loại gần giống |
| Scope vượt quyền | `invalid_scope` hoặc lỗi policy phù hợp | Không âm thầm nâng quyền |
| Token mới sai `aud`/`scope` | Không phải lỗi exchange ở client nếu đã phát | Resource Server phải từ chối và cảnh báo cấu hình |

**Hành vi trả mã lỗi cụ thể của Spring Authorization Server cần được kiểm thử trên phiên bản triển khai.** RFC yêu cầu chung không đồng nghĩa mọi chi tiết error của mọi version giống nhau. Khi phát hiện khác biệt, cần phân biệt compliance requirement với behavior của thư viện và quyết định extension/test phù hợp.

### 16.1. Response lỗi không được rò token đầu vào

Ví dụ lỗi an toàn:

```json
{
  "error": "invalid_request",
  "error_description": "Token exchange request is not acceptable"
}
```

Không trả raw `subject_token`, stack trace, nội dung JWT claim nhạy cảm, JWK cache details hoặc lý do “token thuộc user X không được phép” cho client không đủ quyền biết. Lưu correlation ID và lý do chi tiết ở audit/log bảo mật **đã redaction**.

## 17. Ma trận kiểm thử cho ba tham số

### 17.1. Test cú pháp và hợp đồng RFC

| Ca kiểm thử | Request | Kỳ vọng |
|---|---|---|
| Hợp lệ tối thiểu | `grant_type`, `subject_token`, `subject_token_type`, client auth hợp lệ | AS xử lý hoặc từ chối theo policy, không do thiếu tham số |
| Thiếu `subject_token` | Chỉ có type | `invalid_request` |
| Token rỗng | `subject_token=` | Bị từ chối |
| Thiếu `subject_token_type` | Có token nhưng không có type | `invalid_request` |
| Type không được hỗ trợ | `subject_token_type` là URI lạ | Không phát token |
| Type sai ngữ nghĩa | Opaque token khai `jwt` | Không bỏ qua validation |
| Không gửi requested type | Bỏ `requested_token_type` | AS quyết định output theo policy; client đọc `issued_token_type` |
| Requested type là access token | Xin `...:access_token` | Nếu hỗ trợ và policy cho phép, cấp access token |
| Requested type là ID token | Xin `...:id_token` | Không được mặc nhiên phát ID token; test hỗ trợ thực tế |
| Trùng required param | Gửi hai `subject_token` | Bị từ chối theo quy tắc request parsing |
| Actor token không type | Có `actor_token`, thiếu type | `invalid_request` |
| Type actor không có actor | Chỉ có `actor_token_type` | `invalid_request` |

### 17.2. Test trust và policy

| Ca kiểm thử | Điều kiện | Kỳ vọng |
|---|---|---|
| Subject token hết hạn | `exp` đã qua | Từ chối |
| Subject token giả chữ ký | JWT giả mạo | Từ chối |
| Subject token do issuer lạ cấp | Trust source không cho phép | Từ chối |
| Token bị thu hồi | AS/introspection đánh dấu invalid | Từ chối theo policy |
| Client không được exchange | Grant chưa đăng ký | Từ chối |
| Client khác trao token của user | Không có binding/policy phù hợp | Từ chối |
| Cross-tenant | Caller/subject thuộc tenant không tương thích | Từ chối |
| Audience target không được phép | Xin `https://admin.example.com` | `invalid_target` hoặc lỗi phù hợp |
| Scope vượt quyền | Xin scope nhạy cảm hơn input/policy | Không cấp vượt quyền |
| Target hợp lệ | Xin token có audience Payment API | Output chỉ có audience/scope được phép |
| Delegation actor giả mạo | Actor token không tin cậy | Không chấp nhận `act` |
| Source token bị revoke sau exchange | Output đã cấp vẫn còn hạn | Kiểm tra revocation propagation theo thiết kế |
| Output token hết hạn | Dùng token quá `exp` | Resource Server từ chối |

### 17.3. Kiểm tra phản hồi

Với exchange thành công, xác minh:

1. `access_token` có giá trị và được giữ bí mật.
2. `issued_token_type` **hiện diện** và đúng loại output thực sự phát.
3. `token_type` phản ánh cách sử dụng token, ví dụ `Bearer`.
4. `expires_in` và claims expiration nhất quán với chính sách.
5. `scope` và `aud` không vượt mức đã cho phép.
6. Nếu có claim `act` thì thông tin actor được xác minh và hợp đồng RS sử dụng đúng.
7. Access token mới được API đích chấp nhận, **không được API khác chấp nhận nếu audience không phù hợp**.
8. Client không ghi subject token hoặc token output vào log.

## 18. Test với Spring Security và Spring Authorization Server

Một chiến lược kiểm thử thực tế gồm ba lớp:

### 18.1. Unit test converter/policy

- Truyền form hợp lệ và kiểm tra `OAuth2TokenExchangeAuthenticationToken` chứa đúng `getSubjectToken()`, `getSubjectTokenType()`, `getRequestedTokenType()`.
- Truyền thiếu/nhầm token type để kiểm tra converter từ chối theo hợp đồng.
- Dùng policy test với subject/client/target giả lập để xác minh scope attenuation.
- Kiểm tra không bao giờ chấp nhận input token chưa kiểm tra chữ ký hoặc trạng thái.
- Kiểm tra provider không cấp token khi requesting client chưa được xác thực.

### 18.2. Integration test Token Endpoint

Gửi HTTP `POST /oauth2/token` qua đúng `SecurityFilterChain` với client credential, subject token và RFC token type URIs. Kiểm tra:

- Client authentication được xử lý trước cấp token.
- Granted client có `token-exchange` trong registration.
- Token được phát hành có `issued_token_type` phù hợp.
- `invalid_request`/`invalid_target` và OAuth error response phù hợp.
- Khi đổi `subject_token` thành token của issuer khác, AS từ chối.
- Nhiều instance có authorization state/JWK/trust policy nhất quán.

Đừng chỉ gọi service generate JWT rồi kết luận Token Exchange hoạt động; các lỗi form parsing, client authentication và token endpoint error handling sẽ bị bỏ qua.

### 18.3. End-to-end Resource Server

Tạo subject token hợp lệ cho `booking-api`, đổi token cho `payment-api`, rồi chứng minh:

1. `booking-api` nhận input đúng audience dành cho mình.
2. AS chỉ cấp output khi policy cho phép.
3. `payment-api` chấp nhận output đúng audience/scope và từ chối input gốc nếu audience sai.
4. Một API thứ ba từ chối output token nếu không thuộc audience.
5. Revocation/expiry diễn ra đúng theo thiết kế đã công bố.

## 19. Vận hành: logging, cache và thu hồi

Token Exchange có **hai credential nhạy cảm trong một quy trình**: input token và output token. Cần tránh làm lộ cả hai.

### 19.1. Thông tin nên đo

| Metric hoặc audit | Mục đích |
|---|---|
| Token exchange QPS theo client | Theo dõi lưu lượng và lạm dụng |
| Error rate `invalid_request`/`invalid_target` | Phát hiện type/target không hợp lệ |
| Tỷ lệ exchange theo subject token type | Xác định profile được sử dụng |
| Target audience/resource được yêu cầu | Phát hiện target bất thường, giới hạn label cardinality |
| Token issuance latency | Giám sát hiệu năng AS |
| JWT verification/introspection failure | Kiểm tra trust của input token |
| Policy-denied exchanges | Phát hiện nâng quyền hoặc cross-tenant |
| Revocation propagation delay | Đo khoảng tồn dư khi yêu cầu cắt quyền |
| Client credential rotation events | Kiểm soát client authentication |

Không đưa raw `subject_token`, `access_token`, client secret, ID token hay private key vào log/traces/metrics/audit.

### 19.2. Cache token trao đổi có an toàn không?

Token output thường có audience/scope/subject riêng. Nếu cache:

- Key phải phân biệt requesting client, subject, audience/resource, scope, token type và tenant khi cần.
- Không dùng token output của subject A cho subject B.
- Không dùng token dành cho Payment API cho Bookings API.
- Cache TTL không vượt `exp`; cân nhắc hạn của input token và chính sách thu hồi.
- Không coi output token còn hạn là bằng chứng input token hiện vẫn hợp lệ nếu sản phẩm yêu cầu revocation propagation.
- Tránh cache raw subject token trong storage không có bảo vệ.

Vì use case nhạy cảm, có thể ưu tiên không cache nếu lưu lượng thấp; khi cache, thiết kế redaction, encryption, concurrency và cleanup rõ ràng.

### 19.3. Incident response

Khi subject token/credential exchange bị lộ:

1. Ngăn credential/client bị xâm nhập yêu cầu exchange mới.
2. Thu hồi subject token và xác định token output đã phát từ input tương ứng nếu có cơ chế liên kết/audit.
3. Quyết định vô hiệu hóa output token hoặc chờ TTL theo yêu cầu an toàn.
4. Kiểm tra Resource Server có thực thi revocation/introspection/audience đúng.
5. Điều tra audit theo correlation ID, client, subject đã pseudonymize và target; không dùng raw token.
6. Đưa quy trình kiểm soát trust/target/scope và kiểm thử regression vào kế hoạch phục hồi.

**RFC 8693 không tự bảo đảm input/output revocation propagation.** Nếu sản phẩm cần khả năng “ngắt toàn bộ chuỗi token ngay”, hãy thiết kế riêng dữ liệu liên kết và điểm kiểm tra hiệu lực.

## 20. Những nhầm lẫn thường gặp

**“`subject_token` là mật khẩu của client.”** Sai. Nó là token đầu vào đại diện subject; client authentication là bước riêng.

**“`subject_token_type` là format JWT hay opaque do nhìn chuỗi.”** Sai. Type URI biểu diễn ngữ nghĩa token, có trường hợp diễn tả format; `access_token` và `jwt` không tương đương.

**“JWT access token phải khai `subject_token_type=jwt`.”** Không nhất thiết. Nếu AS xử lý theo ngữ nghĩa OAuth access token, `...:access_token` có thể là loại đúng dù token có định dạng JWT.

**“`requested_token_type` bắt buộc.”** Sai. RFC 8693 quy định tùy chọn, nhưng AS có thể giới hạn theo policy/profile.

**“Bỏ requested type tức là chắc chắn phát access token.”** Sai theo RFC. Quyết định thuộc Authorization Server; luôn kiểm tra `issued_token_type`.

**“`issued_token_type` và `token_type` là một.”** Sai. Một trường chỉ loại security token, trường kia chỉ cách sử dụng nó.

**“Có `subject_token` hợp lệ thì được xin token cho mọi audience.”** Sai. AS phải kiểm tra quyền client, subject, tenant và target.

**“Đổi token tạo scope mới theo tham số client gửi.”** Sai. Scope output phải được policy cho phép; không được tự nâng quyền.

**“Token exchange tự hủy input token.”** Sai. RFC không yêu cầu ảnh hưởng đó mặc định.

**“Thu hồi input token tự thu hồi mọi output token.”** Sai. Cần cơ chế propagation/linked revocation riêng.

**“Có thể dùng ID token OIDC như access token nếu cả hai đều là JWT.”** Sai. ID token có audience và mục đích khác; mọi exchange từ ID token phải theo profile và trust policy được hỗ trợ, không mặc nhiên.

**“RFC hỗ trợ token type nào thì Spring built-in hỗ trợ tất cả.”** Sai. Cần kiểm tra phiên bản converter/provider và các giới hạn implementation.

## 21. Checklist thiết kế Token Exchange

- [ ] `grant_type` có đúng URI RFC 8693?
- [ ] `subject_token` và `subject_token_type` được yêu cầu, đọc và kiểm tra?
- [ ] `subject_token_type` phản ánh đúng **ngữ nghĩa/format** theo contract của issuer?
- [ ] `requested_token_type` được xem là yêu cầu tùy chọn, không phải quyền?
- [ ] `issued_token_type` và `token_type` của response được xử lý đúng?
- [ ] Requesting client được xác thực và đã đăng ký token-exchange grant?
- [ ] AS xác minh trust issuer, signature/introspection, expiry và ràng buộc của input?
- [ ] Policy kiểm tra subject/client/tenant và không cho nâng quyền trái phép?
- [ ] `audience`/`resource` và `scope` của output được hạn chế rõ?
- [ ] Actor/delegation nếu có được xác minh và ghi `act` đúng?
- [ ] Đã phân biệt token input và output TTL, cache, revocation?
- [ ] Đã kiểm tra token types built-in được Spring hỗ trợ trên phiên bản thực tế?
- [ ] Có test thiếu tham số, sai type, invalid token, invalid target, cross-tenant và scope escalation?
- [ ] Resource Server chặn token sai audience và scope?
- [ ] Logs/traces/audit không chứa credential đầu vào/đầu ra?

### Kiến thức cốt lõi

Trong OAuth 2.0 Token Exchange:

- **`subject_token`** là **security token đầu vào** đại diện cho subject.
- **`subject_token_type`** là URI **bắt buộc**, mô tả loại token đầu vào để AS xác minh đúng.
- **`requested_token_type`** là URI **tùy chọn**, mô tả loại token đầu ra mà client mong muốn.
- **`issued_token_type`** trong phản hồi mới cho biết **loại token thực sự được cấp**.

Token Exchange là một quyết định authorization mới, không phải thao tác chuyển định dạng token đơn thuần. Spring Authorization Server cung cấp pipeline Token Endpoint để xử lý grant nhưng vẫn cần chính sách trust, target, scope, client identity, token lifecycle và kiểm thử đầy đủ trước khi sử dụng trong hệ thống production.

## Tài liệu tham khảo

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8693 `2.1 — Request](https://www.rfc-editor.org/rfc/rfc8693#section-2.1)
- [RFC 8693 `2.2 — Response](https://www.rfc-editor.org/rfc/rfc8693#section-2.2)
- [RFC 8693 `3 — Token Type Identifiers](https://www.rfc-editor.org/rfc/rfc8693#section-3)
- [RFC 8693 `4 — JSON Web Token Claims](https://www.rfc-editor.org/rfc/rfc8693#section-4)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — OAuth2TokenExchangeAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationToken.html)
- [Spring Security — OAuth 2.0 Client Authorization Grants](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
