# Step-up authentication

Người dùng đăng nhập thành công **không có nghĩa mọi thao tác tiếp theo đều được phép thực hiện với cùng mức bảo đảm xác thực**. Việc xem lịch sử giao dịch có thể chỉ cần một phiên đăng nhập hợp lệ, nhưng đổi tài khoản nhận tiền, xóa khóa API hoặc xuất dữ liệu cá nhân hàng loạt có thể đòi hỏi người dùng **xác thực lại gần thời điểm thao tác** và/hoặc dùng **phương thức xác thực mạnh hơn**. Cách nâng yêu cầu xác thực theo ngữ cảnh như vậy được gọi là **step-up authentication**.

Trong module bảo mật token, step-up là mắt xích nối **chính sách rủi ro**, **xác thực người dùng**, **OAuth 2.0/OpenID Connect (OIDC)** và **kiểm tra token ở resource server/API**. Cần hiểu ai yêu cầu nâng mức xác thực, hệ thống định danh đã thực hiện điều gì, và bằng chứng nào cho phép API tin rằng yêu cầu đã được đáp ứng.

## 1. Step-up authentication là gì?

**Step-up authentication** là quy trình yêu cầu một **sự kiện xác thực người dùng** đáp ứng điều kiện cao hơn hoặc mới hơn so với bằng chứng hiện tại, trước khi cho phép thao tác nhạy cảm. Điều kiện có thể là:

1. **Độ mạnh/phương thức xác thực (authentication strength/context):** ví dụ chính sách yêu cầu người dùng xác thực theo một ngữ cảnh có chống giả mạo/phishing resistance, nhưng phiên hiện tại chỉ dựa trên mật khẩu.
2. **Độ mới (authentication recency):** ví dụ người dùng đã đăng nhập bằng passkey nhưng lần xác thực chủ động gần nhất cách đây nhiều giờ; thao tác nhạy cảm đòi hỏi xác thực trong vòng 5 phút.
3. **Kết hợp cả hai:** ví dụ chuyển khoản giá trị lớn cần phương thức được chấp nhận theo chính sách của tổ chức **và** lần xác thực mới diễn ra trong 5 phút.

Step-up thường **không thay thế lần đăng nhập ban đầu**. Người dùng có thể vẫn giữ phiên bình thường để đọc dữ liệu ít nhạy cảm, nhưng phải vượt qua một yêu cầu bổ sung trước khi thực hiện hành động rủi ro cao.

### 1.1. Ví dụ xuyên suốt: thay đổi tài khoản nhận tiền

Giả sử người dùng Linh đăng nhập lúc 08:00 bằng mật khẩu + OTP và đang xem ứng dụng:

- Lúc 10:00, Linh xem danh sách giao dịch: ứng dụng kiểm tra access token, scope và quyền trên tài khoản. Nếu hợp lệ, thao tác được cho phép.
- Lúc 10:05, Linh đổi tài khoản ngân hàng nhận tiền: API yêu cầu ngữ cảnh xác thực có mức bảo đảm phù hợp và lần xác thực chủ động **không quá 300 giây**.
- Client chuyển Linh đến hệ thống định danh để thực hiện bước xác thực theo yêu cầu; hệ thống phát hành token mới mang/tham chiếu thông tin về sự kiện xác thực vừa thực hiện.
- API kiểm tra **token mới**, mức xác thực, thời điểm xác thực và quyền thay đổi tài khoản; chỉ khi tất cả điều kiện đạt thì mới ghi thay đổi.

Điểm quan trọng: **chỉ hiện một màn hình nhập OTP chưa đủ để chứng minh API phải cho phép**. API cần nhận và kiểm tra **bằng chứng đáng tin cậy từ bên xác thực**, gắn với user, client, token và chính sách cụ thể.

### 1.2. So sánh các khái niệm gần nhau

| Khái niệm | Mục tiêu | Có luôn là step-up không? |
| --- | --- | --- |
| **Login / user authentication** | Xác định người đang đăng nhập | Không; đây có thể là mức xác thực ban đầu |
| **Reauthentication** | Yêu cầu người dùng xác thực chủ động lần nữa | Có thể: thường dùng khi cần **độ mới** |
| **Multi-factor authentication (MFA)** | Kết hợp yếu tố xác thực độc lập theo chính sách | Có thể: dùng làm step-up nếu nâng mức so với bằng chứng trước |
| **Step-up authentication** | Đáp ứng yêu cầu cao hơn/mới hơn cho thao tác nhất định | Có thể đạt bằng MFA, passkey, reauth hoặc cơ chế được policy chấp nhận |
| **Authorization / phân quyền** | Quyết định user có được thao tác trên tài nguyên không | Không; vẫn phải kiểm tra riêng sau khi step-up |
| **Consent** | Người dùng chấp thuận chia sẻ quyền/dữ liệu trong ngữ cảnh nhất định | Không; chấp thuận quyền không tự chứng minh người đó vừa được xác thực mạnh |
| **Transaction confirmation** | Xác nhận ý định cho đúng giao dịch và các thông số cụ thể | Có thể bổ sung step-up, nhưng step-up không tự ràng buộc với nội dung giao dịch |

Ví dụ: người dùng đã đăng nhập bằng passkey mạnh cách đây 30 giây có thể **không cần làm thêm MFA**, nếu bằng chứng hiện tại đáp ứng mọi điều kiện. Ngược lại, người dùng nhập lại mật khẩu có thể đáp ứng yêu cầu “xác thực mới” nhưng **vẫn chưa đạt** yêu cầu “chống phishing” nếu chính sách đòi hỏi phương thức mạnh hơn.

## 2. Quyết định khi nào phải step-up

Không nên áp một mức MFA nặng như nhau lên mọi request. Hệ thống chọn chính sách dựa trên **mức nhạy cảm của hành động**, **giá trị tài sản**, **bối cảnh rủi ro** và **mức bảo đảm hiện tại**.

| Hành động | Rủi ro cần xét | Ví dụ chính sách minh họa |
| --- | --- | --- |
| Đọc trang thông tin công khai | Thấp | Không cần đăng nhập |
| Xem đơn hàng của chính mình | Trung bình | Session/access token hợp lệ, quyền sở hữu đơn hàng |
| Đổi email đăng nhập hoặc phương thức khôi phục | Cao | Xác thực lại gần đây; tăng mức nếu cần |
| Tạo/xuất API key, thay quyền quản trị | Cao | Xác thực mạnh và mới; kiểm tra quyền quản trị |
| Chuyển khoản nhiều tiền | Rất cao | Xác thực mạnh, mới; xác nhận thông số giao dịch và kiểm soát gian lận |
| Tải hàng loạt dữ liệu nhạy cảm | Cao | Step-up và giới hạn phạm vi xuất dữ liệu |

Đây là **ví dụ thiết kế**, không phải ngưỡng mặc định của một tiêu chuẩn. Tổ chức phải tự xác định chính sách cho lĩnh vực của mình; các giá trị như “5 phút”, “AAL2” hoặc “phải dùng passkey” chỉ có ý nghĩa khi được định nghĩa nhất quán giữa identity provider, client và API.

Ngoài loại thao tác, hệ thống có thể xem xét thiết bị mới, thay đổi IP bất thường, dấu hiệu session bị chiếm quyền, vị trí địa lý khác thường hoặc hành vi tự động. Những tín hiệu này **không nên tự biến thành bằng chứng danh tính**; chúng giúp ra quyết định có cần step-up, chặn hay điều tra thêm. Một số sự cố nghiêm trọng nên **từ chối thao tác** thay vì chỉ yêu cầu thêm OTP.

## 3. Ai làm gì trong mô hình OAuth 2.0/OIDC?

Một kiến trúc phân biệt rõ bốn vai trò:

- **End user:** người cần chứng minh danh tính khi được yêu cầu.
- **Client:** website, BFF, SPA hoặc ứng dụng mobile nhận challenge và đưa người dùng qua luồng xác thực.
- **Authorization Server/OpenID Provider (AS/OP):** bên thực sự xác thực người dùng theo policy, sau đó phát hành hoặc cập nhật bằng chứng xác thực/token.
- **Resource Server (RS/API):** bên sở hữu tài nguyên, đánh giá rủi ro cho thao tác và kiểm tra access token có đáp ứng độ mạnh/độ mới cần thiết hay không.

~~~mermaid
flowchart LR
    U["Người dùng"] -->|"Thực hiện thao tác nhạy cảm"| C["Client / BFF"]
    C -->|"Access token hiện tại"| RS["Resource Server / API"]
    RS -->|"Yêu cầu ACR và/hoặc độ mới"| C
    C -->|"Authorization request + acr_values/max_age"| OP["Authorization Server / OP"]
    OP -->|"Yêu cầu user xác thực phù hợp"| U
    U -->|"Xác thực chủ động"| OP
    OP -->|"Token mới với bằng chứng xác thực"| C
    C -->|"Gọi lại với access token phù hợp"| RS
    RS -->|"Kiểm tra policy + quyền"| RS
~~~

**API có quyền đặt yêu cầu cho tài nguyên của mình**, nhưng thường **không tự kiểm chứng yếu tố MFA của người dùng**. OP có trách nhiệm thực thi nghi thức xác thực và tạo thông tin đáng tin cậy về kết quả. API cần **xác minh** thông tin đó trước khi quyết định quyền; client chỉ vận chuyển yêu cầu và credential.

Step-up **không giống client authentication**. Backend chứng minh `client_id` và `client_secret` tại token endpoint chỉ cho AS biết client nào đang gọi; nó **không chứng minh user vừa thực hiện MFA**. Tương tự, OAuth client dùng PKCE giúp bảo vệ authorization code nhưng **PKCE không thay đổi mức bảo đảm đăng nhập của user**.

## 4. Bằng chứng xác thực: `acr`, `amr` và `auth_time`

Các thông tin dưới đây xuất hiện trong OIDC và có thể được đưa vào **JWT access token** hoặc **metadata introspection** theo profile/thỏa thuận giữa AS và RS.

| Trường | Ý nghĩa | Dùng thế nào trong step-up? |
| --- | --- | --- |
| **`acr`** (Authentication Context Class Reference) | Định danh ngữ cảnh/lớp bảo đảm của sự kiện xác thực | API so với giá trị/nhóm giá trị được chính sách cho phép |
| **`amr`** (Authentication Methods References) | Danh sách phương thức đã dùng, như mật khẩu, OTP, phương thức phần cứng… theo định nghĩa của issuer | Dữ liệu bổ trợ hoặc chính sách chi tiết; không tự suy ra assurance level chỉ từ một chuỗi |
| **`auth_time`** | Thời điểm người dùng **được xác thực**, thường là Unix time (giây UTC) | So sánh với thời điểm hiện tại để kiểm tra độ mới |
| **`iat`** | Thời điểm **token được phát hành** | Dùng trong validation/vòng đời token; **không thay cho `auth_time`** |
| **`exp`** | Thời điểm token **hết hạn** | Dùng kiểm tra hiệu lực token; **không chứng minh người dùng vừa xác thực** |
| **`scope`** | Những phạm vi quyền được cấp cho token | Cần để phân quyền, nhưng **không có nghĩa đã step-up** |
| **`aud`** | Đối tượng nhận token hợp lệ | Chống đưa token của API khác vào API hiện tại |

### 4.1. Phân biệt độ mạnh và độ mới

Hai đại lượng thường độc lập:

~~~text
Token A:
  acr       = urn:example:acr:phishing-resistant
  auth_time = 08:00

Token B:
  acr       = urn:example:acr:password
  auth_time = 10:02

Thao tác 10:05 yêu cầu:
  acr thuộc {urn:example:acr:phishing-resistant}
  auth_time trong vòng 300 giây

=> Token A: đúng độ mạnh, nhưng xác thực quá cũ.
=> Token B: đủ mới, nhưng sai ngữ cảnh xác thực.
=> Cả hai đều chưa đáp ứng chính sách.
~~~

Các giá trị `urn:example:acr:...` ở đây **chỉ là tên minh họa**. `acr` không có thang điểm số chung để mọi hệ thống so sánh “lớn hơn” hoặc “nhỏ hơn”. AS và RS phải thống nhất chính xác **giá trị nào đại diện ngữ cảnh nào, được phép cho thao tác nào**.

### 4.2. `auth_time` không phải `iat`

Người dùng đăng nhập chủ động lúc 08:00, sau đó client dùng refresh token xin access token mới lúc 10:00:

~~~json
{
  "auth_time": 1795395600,
  "iat": 1795402800,
  "exp": 1795403700
}
~~~

Trong ví dụ minh họa, `iat - auth_time = 7200` giây: token mới được cấp **không đồng nghĩa người dùng vừa xác thực lại**. Nếu API yêu cầu lần xác thực không quá 300 giây, token đó **không đạt**, dù `exp` còn xa.

Các mốc thời gian trong ví dụ chỉ mô phỏng quan hệ, không nhằm chỉ thời gian hiện hành. Khi triển khai, so sánh trên giá trị Unix time từ nguồn tin cậy, kiểm tra token còn hạn và giới hạn độ lệch đồng hồ hợp lý.

### 4.3. `amr` không tự động chứng minh MFA đạt chuẩn mong muốn

Nếu một token có `amr: ["pwd", "otp"]`, điều đó thường gợi ý mật khẩu và một yếu tố OTP đã được dùng. Tuy nhiên, mức bảo đảm còn phụ thuộc cách đăng ký yếu tố, khả năng chống phishing, chống đánh cắp OTP, khôi phục tài khoản, quản lý khóa và chính sách OP. API **không nên tự quy đổi mọi sự kết hợp `pwd` + `otp` thành một ACR cố định** nếu chưa có hợp đồng/định nghĩa rõ từ OP.

Với tác vụ nhạy cảm cao, cân nhắc phương thức chống phishing như WebAuthn/passkey phù hợp. Cũng cần xem xét cách tài khoản khôi phục khi người dùng mất thiết bị; đường khôi phục yếu có thể trở thành lối đi vòng quanh step-up.

## 5. Yêu cầu step-up từ OIDC client

Trong OIDC, client có thể yêu cầu xác thực mạnh hơn/mới hơn trong **authorization request**. Các tham số liên quan là:

- **`acr_values`**: danh sách giá trị ACR mong muốn, cách nhau bằng dấu cách, theo thứ tự ưu tiên. OP có thể chọn cách đáp ứng theo hỗ trợ và chính sách.
- **`max_age`**: số giây tối đa cho phép kể từ lần xác thực **chủ động** gần nhất. Nếu vượt ngưỡng, OP phải cố gắng xác thực lại user theo OIDC.
- **`prompt=login`**: yêu cầu OP thúc đẩy đăng nhập lại. Khi cần **bằng chứng thời điểm**, `max_age` phù hợp hơn vì khi sử dụng nó, ID token trả về **phải có `auth_time`**.
- **`claims`**: trong cấu hình OIDC phù hợp, có thể yêu cầu claim `acr` như một *essential claim* với các giá trị chấp nhận cụ thể; cách OP đáp ứng hoặc xử lý lỗi cần theo profile đã thống nhất.

Ví dụ một authorization request được mã hóa trên URL (các giá trị `state`, `nonce`, PKCE đều là placeholder):

~~~http
GET /authorize?response_type=code&client_id=payments-web&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&scope=openid%20payments.write&state=<random-state>&nonce=<random-nonce>&code_challenge=<challenge>&code_challenge_method=S256&acr_values=urn%3Aexample%3Aacr%3Aphishing-resistant&max_age=300 HTTP/1.1
Host: auth.example.com
~~~

Khi xử lý response, client phải:

1. Kiểm tra `state`, ràng buộc authorization code với phiên bắt đầu yêu cầu; đổi code bằng `code_verifier` gốc và client authentication nếu là confidential client.
2. Kiểm tra **ID token** theo quy tắc OIDC: issuer, audience (đúng client), chữ ký/thuật toán phù hợp, hạn, `nonce` nếu dùng và các ràng buộc khác.
3. Xác minh `auth_time` có trong ID token khi đã yêu cầu `max_age`, cùng độ mới và `acr` thực tế theo chính sách của client nếu cần.
4. Có được **access token dành cho API** và bảo đảm API nhận được thông tin xác thực tương ứng theo profile đã thống nhất. Không gửi ID token thay access token để gọi resource API.

**Chỉ gửi `acr_values` không đủ để bảo đảm step-up thành công.** Trong OIDC Core, `acr_values` là yêu cầu ưu tiên; OP có thể trả về mức ngữ cảnh không đúng mong muốn tùy đặc tả/chính sách. Bên cần bảo vệ tài nguyên **phải xác minh kết quả thực tế** và từ chối nếu không đạt. Trong các triển khai theo RFC 9470, hành vi khuyến nghị là AS từ chối yêu cầu nếu không đáp ứng được ACR cần thiết, giúp tránh vòng lặp thử lại.

## 6. API chủ động yêu cầu step-up: RFC 9470

Khi mức xác thực hiện tại không đủ, **OAuth 2.0 Step Up Authentication Challenge Protocol (RFC 9470)** cung cấp cách để resource server nói rõ yêu cầu tới client qua header `WWW-Authenticate`.

Ví dụ API nhận access token **hợp lệ** nhưng chưa đủ mạnh và chưa đủ mới:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="insufficient_user_authentication",
  acr_values="urn:example:acr:phishing-resistant",
  max_age="300"
Content-Type: application/json

{"error":"step_up_required"}
~~~

Ý nghĩa:

- **`401` + `insufficient_user_authentication`**: yêu cầu này cần sự kiện user authentication đáp ứng điều kiện cao hơn/mới hơn, dù access token có thể chưa hết hạn.
- **`acr_values`**: một hoặc nhiều ACR API yêu cầu; các giá trị phải được cấu hình thống nhất giữa AS và RS.
- **`max_age`**: thời gian xác thực chủ động tối đa, tính bằng giây. Giá trị `"0"` thể hiện yêu cầu xác thực mới ngay lúc xử lý.
- Client nhận challenge, bắt đầu **authorization request tương tác với user**, xin token mới rồi gọi lại API.

Phải phân biệt rõ với các lỗi khác:

| Trạng thái | Response/challenge thường gặp | Client nên làm gì? |
| --- | --- | --- |
| Token thiếu, sai, hết hạn | `401` / `invalid_token` theo giao thức | Khôi phục phiên/làm mới token theo chính sách |
| Token đúng nhưng **user authentication** chưa đạt | `401` / `insufficient_user_authentication` theo RFC 9470 | Khởi động luồng step-up với `acr_values`/`max_age` |
| Token có scope không đủ | Thường `403` / `insufficient_scope` với Bearer theo RFC 6750 | Xin quyền phù hợp nếu được phép; step-up đơn thuần không cấp scope |
| Principal không được quyền trên tài nguyên | Thường `403 Forbidden` | Thông báo từ chối; không retry tự động để vượt phân quyền |
| API phát hiện rủi ro cao nghiêm trọng | Theo policy: từ chối, tạm khóa hoặc điều tra | Không coi MFA là biện pháp giải quyết mọi nguy cơ |

Mã lỗi `insufficient_user_authentication` thuộc **thử thách xác thực**. Nó không đồng nghĩa access token có scope thiếu. RFC 9470 cho phép biểu đạt cả yêu cầu scope khi cần, nhưng hệ thống vẫn phải tách bạch **độ mạnh xác thực** với **quyền được cấp**.

### 6.1. Luồng tương tác đầy đủ

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Client / BFF
    participant API as Payments API
    participant OP as Authorization Server / OP
    U->>C: Xác nhận thay đổi tài khoản nhận tiền
    C->>API: POST /beneficiary + access token hiện tại
    API->>API: Validate token, scope, ownership, chính sách step-up
    API-->>C: 401 insufficient_user_authentication + acr_values/max_age
    C->>OP: Authorization request: state, PKCE, acr_values, max_age
    OP->>U: Yêu cầu phương thức/reauth phù hợp
    U-->>OP: Hoàn thành xác thực
    OP-->>C: Authorization code
    C->>OP: Đổi code lấy token theo luồng OAuth/OIDC
    OP-->>C: Access token mới, ID token (nếu OIDC)
    C->>API: POST /beneficiary + access token mới
    API->>API: Kiểm tra lại token, ACR, auth_time, scope, resource, risk
    API-->>C: Chấp nhận hoặc từ chối
    C-->>U: Hiển thị kết quả giao dịch
~~~

Trong triển khai thực tế, client cần gắn challenge với phiên và hành động đang chờ để tránh thao tác nhầm. Khi callback hoàn tất, phía server phải **kiểm tra lại trạng thái và điều kiện giao dịch** trước khi thực hiện: ví dụ tài khoản nguồn, người thụ hưởng, số tiền, quyền của user và tín hiệu gian lận có thể đã thay đổi.

### 6.2. API lấy thông tin `acr` và `auth_time` từ đâu?

API phải dựa vào **bằng chứng được xác thực** từ AS. Hai cách phổ biến:

**Cách A — JWT access token theo profile đã thống nhất.** API kiểm tra chữ ký, `iss`, `aud`, `exp`, `nbf` khi có, loại token, scope, rồi đọc `acr`/`auth_time` nếu issuer đưa chúng vào access token. Ví dụ payload minh họa:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/payments",
  "client_id": "payments-web",
  "scope": "beneficiary.write",
  "iat": 1795402800,
  "exp": 1795403400,
  "acr": "urn:example:acr:phishing-resistant",
  "auth_time": 1795402740
}
~~~

Đây **chỉ là payload minh họa** chứ không phải JWT đã ký. Giá trị `acr` là ví dụ do hệ thống định nghĩa. API **không được chỉ decode JSON rồi tin claim**; phải xác minh toàn bộ token theo cấu hình tin cậy.

**Cách B — Opaque access token + introspection (RFC 7662).** API xác minh trạng thái active và metadata của token qua kênh bảo mật với AS; RFC 9470 định nghĩa cách thể hiện `acr` và `auth_time` trong response introspection:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com",
  "aud": "https://api.example.com/payments",
  "sub": "user-42",
  "client_id": "payments-web",
  "scope": "beneficiary.write",
  "exp": 1795403400,
  "acr": "urn:example:acr:phishing-resistant",
  "auth_time": 1795402740
}
~~~

Nếu access token không có `acr`/`auth_time` và introspection cũng không cung cấp, API **không thể tự suy ra** mức xác thực của user từ `iat`, tên client, cookie hoặc email. Cần thống nhất cách phát hành/truyền các thuộc tính với AS hoặc chọn cơ chế kiểm tra trạng thái tin cậy khác; ở thao tác nhạy cảm, **không suy đoán thành đạt**.

## 7. Kiểm tra chính sách tại API: ví dụ Java

Giả sử API chỉ chấp nhận thao tác `beneficiary.write` của chính chủ tài khoản khi token thỏa cả hai điều kiện:

- `acr` nằm trong danh sách ngữ cảnh chấp nhận, ví dụ `urn:example:acr:phishing-resistant`.
- `auth_time` cách thời điểm xử lý không quá 300 giây.

Đoạn code sau **chỉ minh họa logic chính sách**; `VerifiedToken` phải là kết quả của lớp bảo mật đã kiểm tra chữ ký/introspection, issuer, audience, expiry và loại token, không được tạo trực tiếp từ request hoặc JSON chưa xác minh:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Set;

enum Decision { ALLOW, FORBIDDEN, STEP_UP }

record VerifiedToken(
    String subject,
    Set<String> scopes,
    String acr,
    Instant authTime
) {}

final class BeneficiaryPolicy {
    private static final String REQUIRED_SCOPE = "beneficiary.write";
    private static final Set<String> ACCEPTED_ACR =
        Set.of("urn:example:acr:phishing-resistant");
    private static final Duration MAX_AUTH_AGE = Duration.ofMinutes(5);

    static Decision evaluate(
        VerifiedToken token,
        String accountOwnerId,
        Instant now
    ) {
        // Token signature/issuer/audience/expiry đã được kiểm tra
        // bởi authentication middleware trước khi gọi hàm này.
        if (!token.scopes().contains(REQUIRED_SCOPE)) {
            return Decision.FORBIDDEN;
        }
        if (!token.subject().equals(accountOwnerId)) {
            return Decision.FORBIDDEN;
        }

        if (!ACCEPTED_ACR.contains(token.acr())) {
            return Decision.STEP_UP;
        }
        Instant authTime = token.authTime();
        if (authTime == null || authTime.isAfter(now)) {
            return Decision.STEP_UP;
        }
        if (Duration.between(authTime, now).compareTo(MAX_AUTH_AGE) > 0) {
            return Decision.STEP_UP;
        }
        return Decision.ALLOW;
    }
}
~~~

Nếu hệ thống cho phép độ lệch đồng hồ, phải định nghĩa giới hạn nhỏ và nhất quán, không chấp nhận tùy ý `auth_time` ở tương lai. Ở bước thực thi, cần kiểm tra thêm tenant, trạng thái tài khoản, quyền cập nhật người thụ hưởng, chống giao dịch lặp và tính hợp lệ của các trường giao dịch. Thao tác có dữ liệu nhạy cảm nên được bảo vệ trước **cả việc đọc và thay đổi** thông tin theo nhu cầu thực tế.

Một số điểm triển khai quan trọng:

1. **Validate token trước khi lấy principal:** cùng một claim `acr` có thể xuất hiện trong token giả hoặc token của issuer khác.
2. **Khóa chính sách ở server:** client không quyết định `requiresStepUp=false`, không tự gửi `mfaVerified=true` để được tin.
3. **Không “nâng quyền” tất cả token:** nếu phát token có mức cao, nên giới hạn scope, audience, thời hạn và bảo vệ như credential nhạy cảm.
4. **Không tự retry vô hạn:** nếu AS không hỗ trợ ACR hoặc user không thể đáp ứng, báo lỗi rõ ràng, không liên tục redirect.
5. **Không bỏ qua kiểm tra quyền:** sau khi step-up thành công, quyền sở hữu hoặc policy có thể vẫn từ chối.

## 8. Session, cookie, access token và refresh token trong step-up

### 8.1. Session ứng dụng không tự tăng mức vì đã thấy màn hình MFA

Với web app dùng **server-side session**, ứng dụng có thể lưu bằng chứng đã xác thực lại ở **session store**, ví dụ `lastStrongAuthAt` và `assuranceContext`, nhưng chỉ cập nhật sau khi xác nhận kết quả từ OP/IdP qua kênh tin cậy. Khi xử lý request, server đối chiếu thời điểm, user, chính sách và trạng thái session.

Ví dụ session store:

~~~text
session_id       = <random-id>
user_id          = user-42
assurance_context= urn:example:acr:phishing-resistant
strong_auth_time = 10:05:00 UTC
session_expiry   = ...
~~~

**Cookie `HttpOnly` không mang “sức mạnh xác thực” tự động**. Cookie chỉ giúp trình duyệt gửi định danh session hoặc token. Nếu chỉ lưu cờ `stepUpDone=true` trong `localStorage`, cookie không có ký xác thực hoặc request body, attacker có thể sửa cờ để vượt qua UI. **Quyết định cuối cùng phải ở server**, từ bằng chứng đáng tin cậy và thời hạn phù hợp.

Sau khi nâng mức quyền/session, cần cân nhắc **đổi session ID** để giảm session fixation, bảo vệ cookie bằng `Secure`, `HttpOnly`, `SameSite` và phòng XSS/CSRF theo kiến trúc. Kết thúc phiên hoặc logout phải vô hiệu hóa bằng chứng/session liên quan theo chính sách.

### 8.2. Access token cũ và mới có thể cùng tồn tại

Step-up có thể khiến AS cấp **access token mới** với thông tin xác thực mạnh/mới hơn. Token cũ có thể vẫn còn hiệu lực cho API ít nhạy cảm, tùy chính sách. Không mặc định token cũ bị thu hồi ngay khi user step-up.

Nếu cần hạn chế “nâng quyền” kéo dài, hệ thống có thể cấp token được giới hạn audience/scope và thời gian, hoặc thêm chính sách phía API. **`exp` 5 phút không thay thế yêu cầu `auth_time` 5 phút**: token mới từ refresh token có thể được phát hành hôm nay cho một phiên xác thực của nhiều giờ trước.

### 8.3. Refresh token không làm mới sự kiện xác thực người dùng

Client gửi refresh token để xin access token mới **không đồng nghĩa người dùng đã xác thực chủ động lần nữa**. Theo cơ chế truyền thông tin xác thực của RFC 9470, `acr` và `auth_time` mô tả sự kiện xác thực, không tự thay đổi chỉ vì token được làm mới.

Vì vậy, khi nhận `insufficient_user_authentication`, client không nên chỉ thực hiện vòng lặp:

~~~text
API báo cần step-up
  -> refresh access token
  -> API vẫn báo cần step-up
  -> refresh lại vô hạn  (SAI)
~~~

Hướng xử lý đúng là điều hướng qua **authorization/user authentication flow** có `acr_values`/`max_age` phù hợp, sau đó kiểm tra token mới và thử lại có kiểm soát.

### 8.4. ID token và access token giữ vai trò khác nhau

- **OIDC client** dùng **ID token** để xác minh kết quả user authentication cho ứng dụng, gồm `aud` hướng tới client; nếu yêu cầu `max_age`, kiểm tra `auth_time`.
- **Resource server** dùng **access token** dành cho API đó để kiểm tra quyền và bằng chứng step-up được truyền theo profile. Không gửi ID token cho API rồi coi đó là access token.
- **Authorization server** nhận refresh token hoặc authorization code theo luồng đúng; refresh token không dùng trực tiếp để gọi API.

## 9. Các rủi ro đặc thù và cách giảm thiểu

### 9.1. Step-up fatigue và social engineering

Nếu ứng dụng yêu cầu quá nhiều lần xác thực, người dùng có thể có xu hướng duyệt thông báo MFA theo thói quen hoặc mất cảnh giác với yêu cầu bất thường. Chính sách cần cân bằng mức rủi ro và thời hạn; không dùng push approval vô hạn khi không cần. Với hành động nguy hiểm, xác thực chống phishing và **hiển thị rõ nội dung cần xác nhận** có thể tốt hơn thông báo “Approve?” chung chung.

### 9.2. Phishing/MFA relay và token theft

OTP bị kẻ tấn công dụ nhập có thể bị chuyển tiếp theo thời gian thực. **Step-up bằng OTP không bảo đảm chống phishing**. WebAuthn/passkey với ràng buộc origin và xác thực bên dựa dẫm có thể tăng sức chống giả mạo khi triển khai đúng.

Ngay cả access token được cấp sau step-up vẫn có thể là **bearer token**, có khả năng bị đánh cắp và phát lại cho đến khi hết hạn hoặc bị thu hồi. Cần HTTPS, giới hạn quyền/thời gian token, không ghi token vào log, bảo vệ chỗ lưu token, phát hiện bất thường; có thể cân nhắc token ràng buộc bên gửi bằng DPoP hoặc mTLS khi phù hợp.

### 9.3. Thay thông số giao dịch sau khi step-up

Giả sử user step-up để chuyển 2 triệu đồng cho người thụ hưởng A, nhưng request sau callback đã đổi thành 200 triệu cho B. Nếu API chỉ kiểm tra `acr` và `auth_time`, sự kiện xác thực không tự chứng minh user **đồng ý với nội dung giao dịch mới**.

Để chống thao tác thay đổi ngoài ý muốn:

- Lưu **transaction intent** phía server (user, người nhận, số tiền, đơn vị tiền tệ, expiry), gắn định danh khó đoán và kiểm tra lại khi thực hiện.
- Ràng buộc luồng callback với request ban đầu bằng state/nonce/PKCE tương ứng; không nhận ID giao dịch từ input không được xác thực.
- Với giao dịch giá trị cao, cân nhắc **transaction confirmation/transaction signing** ràng buộc rõ các thuộc tính giao dịch, cùng kiểm soát chống sửa đổi hoặc replay.
- Dùng idempotency key, một lần thực hiện đối với thao tác nhạy cảm và ghi audit trail phù hợp.

**Step-up xác nhận người đang thực hiện hành động** theo chính sách; **transaction binding** bảo vệ việc xác nhận đúng **hành động cụ thể**. Hai lớp này bổ trợ nhau.

### 9.4. Lộ chi tiết rủi ro và lạm dụng challenge

Challenge có thể tiết lộ ACR cần thiết cho một tài nguyên, gián tiếp bộc lộ mức nhạy cảm của tài khoản hoặc endpoint. API nên giới hạn thông tin trả về khi caller chưa được xác thực đầy đủ và không làm lộ phân loại người dùng nhạy cảm. Bên nhận challenge cũng cần kiểm soát nguồn phát, giới hạn lần thử và ngăn bên độc hại ép người dùng liên tục xác thực.

### 9.5. Đường khôi phục yếu và session đã bị chiếm

Step-up có thể bị vô hiệu nếu người tấn công chỉ cần chọn “không còn thiết bị xác thực” rồi đi qua đường khôi phục yếu, hoặc có sẵn session OP bị chiếm và cách vượt yêu cầu xác thực. Cần thiết kế khôi phục tài khoản với mức đảm bảo tương xứng, kiểm tra đăng ký/thay đổi yếu tố, khóa phiên/token nghi vấn và có biện pháp xử lý khi user không thể đạt chính sách.

## 10. Quan sát vận hành và kiểm thử

Nên ghi nhận các sự kiện bảo mật **không chứa credential**: user/client ID theo chính sách dữ liệu, loại thao tác, lý do yêu cầu step-up, giá trị ACR được yêu cầu và được đáp ứng, kết quả, thời điểm xác thực, request/transaction ID và các tín hiệu rủi ro đã chuẩn hóa. Tránh log OTP, passkey assertion thô, access/refresh token, session ID hoặc thông tin nhận dạng không cần thiết.

Các trường hợp kiểm thử tối thiểu:

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Access token hợp lệ, scope đủ, ACR và `auth_time` đạt | API tiếp tục kiểm tra ownership/policy rồi cho phép |
| Scope đủ nhưng ACR thấp | `401 insufficient_user_authentication` với ACR yêu cầu |
| ACR đạt nhưng `auth_time` quá cũ | `401` yêu cầu xác thực mới, ví dụ `max_age` |
| Token vừa refresh nhưng `auth_time` cũ | Vẫn yêu cầu step-up |
| Token JWT đã bị sửa claims `acr` hoặc `auth_time` | Chữ ký không hợp lệ, từ chối |
| Access token sai `aud`/issuer hoặc ID token gửi thay access token | Từ chối trước khi đánh giá step-up |
| Không có `auth_time` ở thao tác đòi độ mới | Fail closed: yêu cầu bằng chứng hợp lệ |
| Client thiếu scope hoặc user không sở hữu tài nguyên | Từ chối quyền, không coi step-up là cách vượt quyền |
| AS trả token không đáp ứng ACR yêu cầu | Client/API không cho phép; kết thúc retry có kiểm soát |
| User hủy step-up hoặc MFA thất bại | Không thay đổi tài nguyên; không tạo bằng chứng elevated |
| Callback bị đổi `state`, PKCE sai hoặc replay code | Từ chối callback/token exchange |
| Step-up hoàn tất nhưng số tiền/người thụ hưởng bị thay | Từ chối hoặc yêu cầu xác nhận lại theo transaction policy |
| Hai request song song, một request chưa step-up | Chỉ request có credential/bằng chứng hợp lệ được thực hiện |
| Logout/thu hồi session hoặc refresh token | Các lần dùng credential cũ bị xử lý theo cơ chế thu hồi đã thiết kế |

Trong observability, tỷ lệ step-up thất bại cao có thể do yếu tố xác thực không khả dụng, ACR cấu hình không khớp giữa AS và API, sai đồng hồ hoặc vòng lặp refresh/redirect. Kiểm tra cả **mức độ bảo vệ** lẫn **độ tin cậy của hành trình người dùng**.

## 11. Sai lầm thường gặp

| Phát biểu | Vì sao sai? |
| --- | --- |
| “Có MFA khi login thì mọi thao tác luôn đủ mạnh.” | Mức xác thực có thể không phù hợp với thao tác; `auth_time` có thể đã quá cũ. |
| “Token có `exp` còn 5 phút nghĩa là user vừa xác thực.” | `exp` nói về hạn token, không phải lần xác thực chủ động. |
| “`iat` mới sau refresh chứng minh step-up.” | Refresh token có thể cấp access token mới mà không có user interaction. |
| “Đưa `prompt=login` là xong, khỏi kiểm tra phản hồi.” | Phải kiểm tra ID token và bằng chứng xác thực; `max_age` giúp có `auth_time`. |
| “API có thể tin `mfaVerified=true` trong request.” | Client có thể tự khai giá trị; phải dùng bằng chứng được xác thực. |
| “Chỉ cần tăng scope để nâng độ bảo đảm.” | Scope cấp **quyền**, ACR/`auth_time` mô tả **ngữ cảnh và độ mới xác thực**. |
| “ID token OIDC dùng trực tiếp gọi API step-up.” | API cần access token đúng audience và profile. |
| “Step-up thành công nghĩa là được sửa mọi tài nguyên.” | Vẫn phải kiểm tra ownership, role, tenant, limit và transaction intent. |
| “Step-up luôn giải quyết token bị đánh cắp.” | Elevated bearer token cũng có thể bị replay nếu không được bảo vệ. |
| “Step-up và xác nhận giao dịch là một.” | Xác thực người và xác nhận đúng thông số giao dịch là hai yêu cầu khác nhau. |

## 12. Checklist thiết kế trước khi triển khai

1. **Phân loại hành động:** thao tác nào cần chỉ login, thao tác nào cần ACR cao hơn, thao tác nào cần reauthentication mới, thao tác nào phải bị chặn hẳn?
2. **Định nghĩa ACR rõ ràng:** thống nhất giữa OP, client và API; không xem mọi giá trị `amr` như mức assurance tương đương.
3. **Định nghĩa độ mới:** chọn `max_age` theo rủi ro, kiểm tra `auth_time`; có quy tắc xử lý đồng hồ sai, claim vắng mặt và phiên hết hạn.
4. **Chọn luồng:** dùng Authorization Code + PKCE cho yêu cầu tương tác phù hợp; confidential client thêm client authentication; không để refresh thay reauthentication.
5. **Định nghĩa challenge API:** dùng `401 insufficient_user_authentication` cùng `acr_values`/`max_age` theo RFC 9470 khi thích hợp; tách khỏi lỗi scope/quyền.
6. **Truyền bằng chứng đáng tin cậy:** JWT access token có xác minh đầy đủ hoặc opaque token introspection đã được bảo vệ; không lấy ID token client đưa thẳng cho API.
7. **Thu hẹp khả năng lạm dụng:** token hạn ngắn/đúng audience và scope, bảo vệ cookie/session, chống XSS/CSRF, giới hạn replay và rate limiting.
8. **Ràng buộc thao tác nhạy cảm:** kiểm tra lại user, tài nguyên, số tiền/người nhận, idempotency và transaction intent sau callback.
9. **Thiết kế fallback an toàn:** nếu OP không hỗ trợ ACR, user không đáp ứng hoặc token không có bằng chứng, từ chối rõ ràng thay vì tự nới chính sách.
10. **Kiểm thử luồng lỗi và vận hành:** ACR không đạt, `auth_time` cũ, token sai audience, loop challenge, concurrent request, session bị thu hồi và yếu tố khôi phục tài khoản.

## 13. Tài liệu tham khảo

- [RFC 9470 — OAuth 2.0 Step Up Authentication Challenge Protocol](https://www.rfc-editor.org/rfc/rfc9470): chuẩn challenge `insufficient_user_authentication`, `acr_values`, `max_age` và truyền thông tin xác thực cho API.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `acr`, `amr`, `auth_time`, `max_age`, `acr_values`, `prompt`, ID token và kiểm tra token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token, thông tin định danh và validation.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): cơ chế kiểm tra trạng thái và metadata token opaque.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): header `Authorization`, `WWW-Authenticate`, `invalid_token` và `insufficient_scope`.

**Ghi nhớ:** Step-up đặt thêm điều kiện về **độ mạnh và/hoặc độ mới của việc xác thực người dùng**, không tự tạo thêm quyền. Resource server phải kiểm tra access token và các bằng chứng đáng tin cậy như `acr`, `auth_time` trong đúng ngữ cảnh; authorization server thực hiện xác thực; client điều phối luồng; quyền trên tài nguyên vẫn phải được kiểm tra riêng ngay trước khi thực hiện thao tác nhạy cảm.
