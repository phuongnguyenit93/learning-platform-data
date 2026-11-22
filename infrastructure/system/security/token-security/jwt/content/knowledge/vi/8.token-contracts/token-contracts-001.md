# Xác định mục đích và bên được quyền sử dụng token

> **Phạm vi:** Security – JSON Web Token (JWT) · **Chương:** Hợp đồng token. Nội dung áp dụng cho các hệ thống sử dụng JWT nói chung, không phụ thuộc ngôn ngữ lập trình hay framework.

Một JWT có chữ ký hợp lệ **không đồng nghĩa** với việc mọi hệ thống tin cậy bên phát hành đều được phép sử dụng JWT đó. Token có thể được phát hành để truy cập API đơn hàng, xác nhận đăng nhập tại một ứng dụng, khôi phục tài khoản hoặc xác minh địa chỉ email. Nếu các bên nhận chỉ kiểm tra chữ ký mà bỏ qua **token được tạo để làm gì** và **ai được phép tiếp nhận token**, token dùng đúng ở ngữ cảnh này có thể bị chấp nhận sai ở ngữ cảnh khác.

Một **hợp đồng token (token contract)** xác định trước điều kiện phát hành, bên nhận hợp lệ, mục đích, quyền hạn và quy tắc kiểm tra. Đây là ranh giới tin cậy cần được cả bên phát hành lẫn bên tiếp nhận tuân thủ.

## 1. Mục tiêu của hợp đồng token

Sau bài học, người đọc cần có thể:

- Phân biệt **bên phát hành**, **chủ thể**, **bên nhận**, **ứng dụng gọi** và **quyền hạn** của token.
- Gắn mỗi loại token với một mục đích cụ thể và các bên được phép sử dụng.
- Thiết kế quy tắc xác thực để JWT đúng chữ ký nhưng sai mục đích hoặc sai bên nhận vẫn bị từ chối.
- Nhận biết và phòng tránh việc sử dụng nhầm token giữa các API, ứng dụng và quy trình nghiệp vụ.

### 1.1. Năm câu hỏi phải trả lời

| Câu hỏi | Yếu tố trong hợp đồng | Ví dụ |
|---|---|---|
| Ai phát hành token? | **Issuer** – claim **iss** | Máy chủ định danh tại https://id.example.com |
| Token nói về ai hoặc thực thể nào? | **Subject** – claim **sub** | Người dùng user-42 hoặc một tài khoản dịch vụ |
| Bên nào được tiếp nhận token? | **Audience** – claim **aud** | API đơn hàng https://api.orders.example.com |
| Token được phát hành để làm gì? | **Token type / purpose** – header **typ**, claim mục đích theo hợp đồng, hoặc hồ sơ token cụ thể | Truy cập API; khôi phục mật khẩu |
| Token cho phép thao tác gì? | **Scopes / permissions** và chính sách phía dịch vụ | orders:read, orders:create |

**Mục đích khác quyền hạn:** “Token này là access token cho API đơn hàng” là mục đích và ngữ cảnh sử dụng; “được đọc đơn hàng” là quyền cụ thể bên trong ngữ cảnh đó. Kiểm tra quyền không thay thế việc kiểm tra mục đích.

**Bên nhận khác chủ thể:** **sub** cho biết token nói về ai; **aud** cho biết token hướng tới dịch vụ hay ứng dụng nào. Một JWT có **sub** hợp lệ không có nghĩa là mọi API đều được phép nhận token đó.

## 2. Các trường thể hiện ranh giới sử dụng

### 2.1. Issuer: chỉ tin bên phát hành đã định danh

Claim **iss** là định danh của bên phát hành. Bên nhận phải có danh sách issuer được tin cậy theo cấu hình, kiểm tra chữ ký bằng khóa phù hợp với issuer đó, rồi đối chiếu giá trị **iss** thực tế.

Không tự động tin một issuer, URL lấy khóa hoặc thuật toán chỉ vì chúng xuất hiện trong JWT chưa được xác minh. Giá trị **iss**, **kid** và các trường header có thể được đọc trước để tìm ứng viên khóa **trong tập cấu hình được phép**, nhưng chỉ trở thành dữ liệu đáng tin sau khi quy trình xác minh hoàn tất.

### 2.2. Audience: xác định đúng bên được phép tiếp nhận

Claim chuẩn **aud** trong JWT mô tả các bên nhận dự kiến. Theo RFC 7519, giá trị có thể là một chuỗi hoặc một mảng chuỗi.

Ví dụ, dịch vụ đơn hàng chấp nhận token chỉ khi **aud** chứa định danh của chính dịch vụ:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "https://api.orders.example.com"
}
~~~

API kho vận có định danh **https://api.inventory.example.com** phải từ chối token trên, dù token được ký bởi cùng một issuer mà API kho vận tin cậy. Không được bỏ qua audience chỉ vì hai API thuộc cùng một tổ chức.

Khi thiết kế audience:

- Dùng định danh **ổn định, rõ ràng và thống nhất** giữa nơi phát hành và nơi kiểm tra (URI hoặc mã tài nguyên theo quy ước).
- So khớp **chính xác** với audience được cấu hình. Không dựa vào phép chứa chuỗi, tiền tố tên miền hay mẫu khớp rộng.
- Nếu **aud** có nhiều giá trị, dịch vụ chỉ được nhận khi định danh của mình thực sự có mặt; chính sách vẫn phải kiểm tra mục đích và quyền. Với hệ thống có độ nhạy cảm cao, cân nhắc phát hành token riêng cho từng tài nguyên để giảm phạm vi lộ lọt.
- Đừng dùng **aud** để biểu diễn danh sách người dùng, vai trò hay từng thao tác được phép. Đó là các khái niệm khác.

### 2.3. Purpose / token type: ngăn các loại JWT bị tráo đổi

JWT không có một claim chuẩn duy nhất mang tên “purpose” áp dụng bắt buộc cho mọi hệ thống. Mục đích thường được xác định bằng **hồ sơ token**, **typ** ở JOSE header và/hoặc một claim riêng có quy ước nhất quán, ví dụ **token_use: "access"** hay **purpose: "password_reset"**.

- **typ** phân biệt loại đối tượng JWT. Ví dụ, hồ sơ JWT access token của OAuth 2.0 (RFC 9068) dùng **at+jwt** hoặc **application/at+jwt**. Chuỗi chung chung **JWT** không đủ phân biệt access token với mọi JWT khác.
- **token_use** hoặc **purpose** là claim do hệ thống quy ước, **không phải tên claim mục đích được RFC 7519 chuẩn hóa**. Nếu sử dụng, bên phát hành và bên nhận phải thống nhất chính xác ý nghĩa, giá trị và nơi kiểm tra.
- Mỗi loại token cần **quy tắc kiểm tra riêng biệt**. Không có nghĩa là mọi loại token đều buộc phải có cùng giá trị **typ** hoặc cùng một claim tự định nghĩa; phải theo hợp đồng và chuẩn áp dụng cho từng loại.

Không coi một chuỗi **purpose** tự khai là đủ bảo mật. Nó chỉ có giá trị khi nằm trong token đã được xác minh chữ ký, issuer, audience, thời hạn và các điều kiện khác.

### 2.4. Chủ thể, ứng dụng gọi và quyền

Các trường sau bổ sung ngữ cảnh nhưng không thay thế **iss**, **aud** và mục đích:

| Trường / khái niệm | Công dụng | Điều không nên suy ra |
|---|---|---|
| **sub** | Nhận diện người dùng hoặc thực thể mà token nói đến | Không phải định danh API nhận token |
| **client_id** | Nhận diện OAuth client trong hồ sơ/token có quy định trường này | Không tự chứng minh client đang cầm token là chủ thể hợp lệ |
| **azp** | Bên được ủy quyền trong một số ngữ cảnh, nổi bật là OpenID Connect ID token | Không thay thế **aud** |
| **scope** | Quyền được cấp, thường là chuỗi các scope cách nhau bởi dấu cách trong OAuth | Không quyết định token thuộc API nào khi thiếu **aud** |
| **roles / permissions** | Quyền theo mô hình của ứng dụng, nếu có | Không mặc nhiên có hiệu lực ở mọi dịch vụ |
| **tenant_id** (nếu dùng) | Phạm vi tổ chức/khách hàng trong hệ thống đa thuê bao | Không thay thế kiểm tra tài nguyên hoặc **aud** |
| **cnf** (nếu dùng) | Thông tin để ràng buộc token với một khóa/thiết bị theo hồ sơ hỗ trợ | Không có ý nghĩa nếu bên nhận không xác minh bằng chứng sở hữu |

Các trường nghiệp vụ như **roles**, **permissions**, **tenant_id**, **purpose** cần được định nghĩa rõ trong hợp đồng; tên trường và kiểu dữ liệu không tự tạo thành chuẩn chung.

## 3. Phân loại token theo mục đích và bên sử dụng

| Loại token | Mục đích chính | Bên nhận được phép dùng | Điều kiện cần chú ý |
|---|---|---|---|
| **Access token** | Gọi API hoặc truy cập tài nguyên được bảo vệ | Resource server/API có **aud** phù hợp | Issuer, chữ ký, audience, thời hạn, hồ sơ loại token, scope/quyền |
| **ID token** (OpenID Connect) | Truyền thông tin xác thực người dùng cho ứng dụng khách | Client ứng dụng có **client_id** phù hợp với **aud**, theo quy tắc OIDC | Không dùng trực tiếp thay access token tại API; kiểm tra **nonce**, **azp** và điều kiện OIDC khác khi áp dụng |
| **Refresh token** | Xin access token mới từ máy chủ ủy quyền | Authorization server/token endpoint theo thiết kế | Có thể là chuỗi opaque hoặc JWT; không được API tài nguyên chấp nhận như access token |
| **Password reset token** | Chứng minh quyền thực hiện quy trình đặt lại mật khẩu | Điểm xử lý khôi phục tài khoản được chỉ định | Đúng purpose, thời hạn ngắn, sử dụng một lần, ràng buộc yêu cầu khôi phục |
| **Email verification token** | Xác nhận quyền kiểm soát địa chỉ email | Điểm xác minh email được chỉ định | Đúng purpose, đúng email/quy trình, chống phát lại |
| **Service-to-service access token** | Một dịch vụ gọi dịch vụ khác | API đích được ghi trong **aud** | Danh tính máy gọi, scope dành cho máy, kiểm soát theo môi trường và tài nguyên |

**Lưu ý:** Không phải token nào cũng là JWT. Việc chọn JWT, token opaque hay mã dùng một lần phụ thuộc yêu cầu thu hồi, bảo mật, vận hành và giao thức. Bảng mô tả **hợp đồng sử dụng**; nó không yêu cầu biến mọi loại token thành JWT.

### 3.1. Ví dụ hợp đồng access token cho API đơn hàng

Header JOSE minh họa:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "issuer-key-2026-01"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "https://api.orders.example.com",
  "client_id": "storefront-web",
  "token_use": "access",
  "scope": "orders:read orders:create",
  "iat": 1794800000,
  "nbf": 1794800000,
  "exp": 1794803600,
  "jti": "token-7f19"
}
~~~

Đây chỉ là **header và payload JSON minh họa**, không phải JWT đã được ký. Các giá trị thời gian chỉ nhằm biểu diễn dạng NumericDate (số giây từ Unix epoch), không phải token thực để sử dụng. Hồ sơ OAuth JWT access token có các yêu cầu riêng; trường **token_use** ở đây là **quy ước bổ sung của hệ thống**, không phải trường bắt buộc của RFC 9068.

API đơn hàng kiểm tra ít nhất:

1. Chữ ký, thuật toán và khóa được chấp nhận theo cấu hình issuer.
2. **iss** đúng issuer được tin cậy.
3. **aud** chứa chính xác định danh API đơn hàng.
4. Loại token phù hợp hợp đồng: ở ví dụ này, **typ = at+jwt** và **token_use = access**.
5. **exp**, **nbf** và các giới hạn thời gian phù hợp.
6. Endpoint cần **orders:read** hay **orders:create** thì token phải có scope tương ứng; đồng thời kiểm tra người dùng có được truy cập **đơn hàng cụ thể** hay không.

Điểm cuối là thiết yếu: token có scope **orders:read** không có nghĩa người dùng được đọc đơn hàng của bất kỳ ai.

### 3.2. Ví dụ hợp đồng khôi phục mật khẩu

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "https://account.example.com/recovery",
  "purpose": "password_reset",
  "exp": 1794800900,
  "jti": "reset-request-912"
}
~~~

Điểm khôi phục tài khoản chỉ chấp nhận token được phát hành cho **recovery**, có **purpose = password_reset**, chưa hết hạn và **jti** tương ứng với yêu cầu đang còn hiệu lực/chưa sử dụng. Sau khi đặt lại mật khẩu thành công, hệ thống vô hiệu hóa yêu cầu để chống tái sử dụng.

API đơn hàng phải từ chối token này ngay cả khi issuer và chữ ký hợp lệ, vì **aud** và **purpose** đều không thuộc hợp đồng access token. Nếu hệ thống thực tế chọn token opaque cho việc khôi phục, nguyên tắc ràng buộc mục đích và một lần sử dụng vẫn giữ nguyên.

## 4. Thiết kế hợp đồng ở bên phát hành và bên nhận

Quy trình cần nhất quán từ lúc phát hành đến lúc kiểm tra:

~~~mermaid
flowchart LR
    R[Ứng dụng yêu cầu token] --> I[Bên phát hành kiểm tra yêu cầu]
    I --> C[Chọn loại token, audience, phạm vi quyền]
    C --> S[Ký token theo hợp đồng]
    S --> U[Bên gọi chuyển token tới đích]
    U --> V[Bên nhận kiểm tra chữ ký, issuer, audience, loại, thời hạn]
    V --> A{Đúng hợp đồng?}
    A -->|Không| X[Từ chối]
    A -->|Có| P[Kiểm tra scope và quyền trên tài nguyên]
    P --> D{Được phép thao tác?}
    D -->|Có| O[Thực hiện yêu cầu]
    D -->|Không| X
~~~

### 4.1. Bên phát hành cần quyết định trước

1. **Loại token:** access, ID, khôi phục, xác minh email hay loại khác.
2. **Bên nhận:** định danh audience chính xác; không mặc định đặt audience quá rộng để “dùng chung toàn hệ thống”.
3. **Mục đích:** kiểu token/hồ sơ và claim riêng nếu sử dụng; không dùng cùng một bộ quy tắc cho những mục đích không tương thích.
4. **Danh tính và quyền:** subject, client, scope hoặc permissions tối thiểu cần thiết.
5. **Vòng đời:** thời gian bắt đầu và hết hạn, yêu cầu thu hồi/chống phát lại, ràng buộc người dùng hay giao dịch khi cần.
6. **Cách ký:** thuật toán và khóa theo chính sách; kế hoạch luân chuyển khóa.

Trong OAuth 2.0, client có thể yêu cầu tài nguyên đích bằng **resource indicator**; authorization server chịu trách nhiệm quyết định audience thực tế sẽ gắn vào access token. Resource server phải kiểm tra **aud** của token nhận được, không xem tham số yêu cầu từ client là bằng chứng thay thế.

### 4.2. Bên nhận phải có chính sách kiểm tra độc lập

Ví dụ hợp đồng logic cho API đơn hàng:

~~~yaml
token_contract: orders-api-access
trusted_issuers:
  - https://id.example.com
allowed_algorithms:
  - RS256
expected_audience: https://api.orders.example.com
accepted_token_types:
  - at+jwt
required_private_claim:
  token_use: access
required_for_get_order:
  scope: orders:read
additional_authorization:
  - user_can_access_requested_order
~~~

Đây là **cấu hình minh họa mang tính khái niệm**, không phải cú pháp của một thư viện hoặc chuẩn cấu hình. Giá trị cần lấy từ hợp đồng thực tế của hệ thống. Nếu một hồ sơ token không định nghĩa **token_use** thì không tự thêm điều kiện đó mà không sửa hợp đồng phát hành.

Một quy trình xác minh độc lập với công nghệ có dạng:

~~~text
verifyForOperation(token, operation, policy):
    parsed = parseUntrusted(token)
    reject nếu thuật toán/loại header không nằm trong chính sách
    chọn khóa ứng viên CHỈ từ issuer/nguồn khóa đã được cấu hình tin cậy
    xác minh chữ ký và tiêu chuẩn cấu trúc JWT
    yêu cầu iss khớp chính xác issuer được phép
    yêu cầu aud chứa chính xác định danh bên nhận
    yêu cầu exp, nbf và các ràng buộc thời gian hợp lệ
    yêu cầu token type và purpose đúng với hợp đồng
    yêu cầu các scope/quyền cho operation
    kiểm tra quyền đối với đối tượng tài nguyên cụ thể
    nếu có điều kiện nào sai: từ chối; ngược lại: tiếp tục
~~~

Nếu có nhiều issuer, bộ kiểm tra có thể dùng dữ liệu JWT **chưa tin cậy** để chọn ứng viên **trong một tập issuer và khóa đã cho phép sẵn**; không được tải khóa từ URL tùy ý do token cung cấp. Giới hạn thuật toán theo cấu hình và ràng buộc mỗi khóa với đúng thuật toán và issuer. Không chấp nhận **alg = none** hoặc tự động chuyển từ xác minh chữ ký bất đối xứng sang khóa đối xứng theo chỉ dẫn không tin cậy.

## 5. Vì sao chỉ kiểm tra chữ ký là chưa đủ?

### 5.1. Token thay thế sai ngữ cảnh (cross-JWT confusion)

Giả sử một tổ chức có ba bên: ứng dụng web, API đơn hàng và dịch vụ khôi phục tài khoản. Cả ba cùng tin một máy chủ phát hành token.

| Token được đưa tới | Tình huống | Kết quả đúng | Lý do |
|---|---|---|---|
| API đơn hàng | Access token có **aud = API đơn hàng**, đúng loại, đủ scope | Có thể chấp nhận sau khi kiểm tra quyền tài nguyên | Đúng bên nhận, đúng mục đích |
| API kho vận | Access token có **aud = API đơn hàng** | **Từ chối** | Sai audience |
| API đơn hàng | ID token có **aud = client ứng dụng web** | **Từ chối** | ID token dành cho client; sai audience/loại token |
| API đơn hàng | Password reset token được ký hợp lệ | **Từ chối** | Sai mục đích và bên nhận |
| Điểm khôi phục mật khẩu | Access token của API đơn hàng | **Từ chối** | Không phải token khôi phục |
| API đơn hàng | Đúng access token nhưng thiếu **orders:create** khi tạo đơn | **Từ chối** | Không đủ quyền cho thao tác |
| API đơn hàng | Đúng token và scope, nhưng yêu cầu đơn hàng của người khác | **Từ chối** nếu không có quyền đặc biệt | Kiểm soát tài nguyên cụ thể |

Vấn đề xuất hiện nếu bên nhận chỉ xác thực “chữ ký này của issuer đáng tin” và không đặt các kiểm tra **aud**, loại token, mục đích và quyền theo ngữ cảnh. Đây là một dạng nhầm lẫn giữa các loại JWT; RFC 8725 khuyến nghị quy tắc xác minh riêng cho từng loại và sử dụng kiểu token tường minh khi thích hợp.

### 5.2. Audience rộng và sử dụng lại token giữa dịch vụ

Giả sử tất cả dịch vụ đều chấp nhận **aud = company-api**. Khi một access token bị lộ tại dịch vụ ít nhạy cảm, phạm vi nơi nó có thể được đưa vào thử lại sẽ lớn hơn. Cách giảm rủi ro là phát hành token theo tài nguyên đích, giới hạn scope và thời hạn, và chỉ dùng nhiều audience khi có lý do cùng chính sách kiểm tra chặt chẽ.

Trong mô hình đa thuê bao, **aud** vẫn xác định API; quyền truy cập dữ liệu thuộc tenant nào cần thêm kiểm tra tenant và quyền trên đối tượng. Không suy ra “đúng API” là “được truy cập mọi tenant”.

### 5.3. Bearer token bị sử dụng bởi người đang giữ token

Audience chỉ giới hạn **dịch vụ được phép nhận token**, không tự chứng minh **ai đang cầm token**. Với bearer token, một người lấy được token có thể thử dùng nó ở đúng API đích cho đến khi hết hạn hoặc bị vô hiệu hóa.

Vì vậy cần bảo vệ đường truyền và nơi lưu token, sử dụng TLS, tránh đưa token vào URL/log, giới hạn thời gian sống và phạm vi quyền. Với nguy cơ chiếm dụng cao, cân nhắc token ràng buộc người gửi bằng cơ chế phù hợp như mTLS hoặc DPoP; khi đó API phải xác minh bằng chứng sở hữu theo đúng giao thức, không chỉ đọc claim **cnf**.

## 6. Xử lý các trường hợp dễ nhầm

**Một token có thể có nhiều audience không?** Có. RFC 7519 cho phép **aud** là mảng. Tuy nhiên mỗi bên nhận vẫn phải kiểm tra mình có trong danh sách; quyền và mục đích phải áp dụng hợp lệ cho bên đó. Việc một token phục vụ quá nhiều API có thể làm tăng tác động khi bị lộ.

**Dùng scope thay cho audience được không?** Không. **scope = orders:read** thể hiện quyền, còn **aud = https://api.orders.example.com** xác định API đích. Nếu chỉ kiểm tra scope, một dịch vụ khác có thể nhận nhầm token được phát hành cho nơi không liên quan.

**ID token có thể dùng làm Bearer access token cho API không?** Không theo hợp đồng OpenID Connect thông thường. ID token dùng cho client xác minh kết quả đăng nhập; resource server phải nhận access token dành cho mình. Nếu một hệ thống xây dựng giao thức riêng thì phải định nghĩa và bảo vệ một hợp đồng riêng, không mặc định tái sử dụng ID token.

**Chỉ cần đặt typ là đã xác định đúng mục đích?** Chưa đủ. **typ** hỗ trợ phân loại nhưng vẫn cần chữ ký, issuer, audience, thời hạn và các claim nghiệp vụ liên quan. Với nhiều hồ sơ cũ, **typ = JWT** quá chung; có thể cần claim mục đích riêng và các quy tắc xác minh loại trừ lẫn nhau.

**Nếu cùng issuer và cùng sub thì hai token có thể thay thế nhau?** Không. Chúng có thể khác audience, loại token, scope, thời hạn và ràng buộc giao dịch. Mỗi JWT phải được xét theo **toàn bộ hợp đồng**, không chỉ danh tính người dùng.

**Có thể giải mã payload để quyết định trước có tin token không?** Có thể đọc header/payload chưa xác minh cho mục đích định tuyến hoặc chọn ứng viên kiểm tra trong danh sách tin cậy. Tuy nhiên không được cấp quyền, thiết lập phiên đăng nhập hoặc gọi tới nguồn khóa tùy ý dựa trên các giá trị đó trước khi xác minh.

## 7. Checklist thiết kế và kiểm tra

Một hợp đồng token tốt cần trả lời được các câu hỏi sau:

- [ ] Mỗi loại token có tên, mục đích, bên phát hành và bên nhận rõ ràng?
- [ ] Bên nhận kiểm tra **iss**, **aud** và loại token đúng theo hợp đồng, thay vì chỉ kiểm tra chữ ký?
- [ ] Thuật toán, nguồn khóa và issuer được giới hạn bằng cấu hình tin cậy; có quy trình luân chuyển khóa?
- [ ] **exp**, **nbf** và chính sách thời gian sống được kiểm tra? Có giới hạn dung sai đồng hồ thích hợp?
- [ ] Scope, quyền trên tài nguyên, tenant và danh tính client được kiểm tra theo từng thao tác cần thiết?
- [ ] Token một lần hoặc gắn với quy trình nhạy cảm có cơ chế chống phát lại/thu hồi và trạng thái giao dịch?
- [ ] Có bài kiểm thử âm tính cho **sai audience**, **sai purpose**, **ID token thay access token**, **scope thiếu**, **token hết hạn**?
- [ ] Payload không chứa dữ liệu bí mật không cần thiết? JWT ký thông thường chỉ **mã hóa biểu diễn Base64url**, không che giấu nội dung.
- [ ] Các bên phát hành và tiếp nhận cùng dùng một tài liệu hợp đồng, nhất quán ở môi trường thử nghiệm và sản xuất?

Có thể dùng bộ ca kiểm thử tối thiểu sau:

~~~text
ACCEPT: access token -> API đơn hàng, đúng issuer/aud/type/thời hạn/scope/quyền tài nguyên
REJECT: token cùng issuer nhưng aud thuộc API khác
REJECT: ID token của client được gửi tới API đơn hàng
REJECT: password reset token được gửi tới API đơn hàng
REJECT: access token đúng aud nhưng thiếu scope cho thao tác
REJECT: access token đúng scope nhưng truy cập tài nguyên không thuộc quyền
REJECT: token hết hạn, chưa có hiệu lực, sai chữ ký hoặc thuật toán ngoài danh sách
REJECT: token một lần đã dùng lại tại điểm xác nhận nhạy cảm
~~~

## 8. Ghi nhớ

**Chữ ký trả lời “token có được phát hành toàn vẹn bởi nguồn đáng tin không?”; hợp đồng trả lời tiếp “token này được phát hành cho bên nào, dùng vào việc gì và cho phép hành động nào?”.** Chỉ khi tất cả điều kiện đúng, hệ thống mới có cơ sở tiếp tục xử lý yêu cầu.

Đối với JWT dùng chung giữa nhiều thành phần, cần tách bạch:

- **iss**: nguồn phát hành được tin cậy.
- **aud**: đúng bên tiếp nhận.
- **typ / token_use / purpose**: đúng loại và mục đích theo hồ sơ đã thỏa thuận.
- **sub / client_id / azp**: các vai trò danh tính khác nhau, tùy giao thức.
- **scope / permissions / chính sách tài nguyên**: hành động cụ thể được phép thực hiện.

**Tài liệu tham khảo chuẩn:** [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519), [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725), [RFC 9068 – JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068), [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html). Các trường bổ sung như **token_use** hoặc **purpose** trong ví dụ là lựa chọn thiết kế của hệ thống, cần được quy định tường minh trong hợp đồng triển khai.
