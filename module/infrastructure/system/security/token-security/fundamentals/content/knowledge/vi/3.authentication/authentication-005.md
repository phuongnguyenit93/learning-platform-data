# Multi-factor authentication và token assurance

Một người dùng đăng nhập thành công bằng mật khẩu và mã OTP, sau đó nhận access token để gọi API chuyển tiền. Câu hỏi quan trọng là: **API có thể kết luận token này đủ an toàn để chuyển tiền chỉ vì tài khoản đã từng dùng MFA không?** Không nhất thiết. API cần biết lần xác thực diễn ra như thế nào, từ bao giờ, có đáp ứng chính sách cho hành động hiện tại không; đồng thời token phải hợp lệ, dành cho đúng API và được bảo vệ khỏi đánh cắp hoặc phát lại.

**Multi-factor authentication (MFA)** tăng độ tin cậy rằng người đang xác thực kiểm soát các yếu tố cần thiết. **Token assurance** trong bài này là cách đánh giá **mức độ đáng tin của bằng chứng xác thực và token được dùng trong một quyết định truy cập**: nguồn phát hành, tính toàn vẹn, tính đúng mục đích, thời điểm xác thực, phương thức xác thực và những rủi ro sau khi cấp token. “Token assurance” không phải tên của một claim JWT chuẩn hoặc một cấp độ bảo đảm thống nhất được mọi hệ thống tự động hiểu giống nhau.

Bài thuộc phần **Authentication** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**: tập trung vào MFA, cách thể hiện mức bảo đảm xác thực trong OAuth 2.0/OpenID Connect (OIDC), liên hệ access/refresh token dạng JWT hoặc opaque, và điều kiện để API tin và cấp quyền cho một request cụ thể.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt các yếu tố xác thực và nhận biết trường hợp có hai bước nhưng chưa phải MFA.
- So sánh mật khẩu + TOTP, SMS OTP, push MFA và passkey/WebAuthn theo khả năng chống phishing và giới hạn của từng phương thức.
- Giải thích sự khác biệt giữa **mức bảo đảm xác thực của phiên đăng nhập**, **tính hợp lệ của token** và **quyền sử dụng tài nguyên**.
- Hiểu vai trò của các claim OIDC `acr`, `amr`, `auth_time`; phân biệt với `iat`, `iss`, `aud`, `exp`, `scope`.
- Xây dựng luồng **step-up authentication** khi thao tác nhạy cảm yêu cầu MFA mạnh hoặc lần xác thực mới hơn.
- Tránh nhầm lẫn “đã bật MFA” với “token không thể bị đánh cắp hoặc phát lại”.

## 2. MFA là gì và tại sao cần nhiều yếu tố?

Xác thực nhằm trả lời câu hỏi “bên yêu cầu đang chứng minh quyền kiểm soát danh tính nào?”. MFA kết hợp **ít nhất hai yếu tố thuộc các nhóm độc lập**.

| Nhóm yếu tố | Ý nghĩa | Ví dụ |
|---|---|---|
| **Something you know** — điều bạn biết | Bí mật mà người dùng ghi nhớ | Mật khẩu, mã PIN do người dùng biết |
| **Something you have** — thứ bạn sở hữu/kiểm soát | Thiết bị hoặc bộ xác thực chứng minh quyền sở hữu | Khóa bảo mật FIDO2, thiết bị sinh mã OTP, khóa riêng trong authenticator |
| **Something you are** — đặc điểm sinh trắc | Đặc điểm cơ thể dùng trong quy trình xác thực | Vân tay, khuôn mặt, khi được ràng buộc với authenticator phù hợp |

Ví dụ **mật khẩu + TOTP từ ứng dụng xác thực** có thể cung cấp hai yếu tố: kiến thức mật khẩu và quyền kiểm soát thiết bị/secret TOTP đã đăng ký. Nhưng **mật khẩu + câu hỏi bảo mật** chủ yếu vẫn là hai bằng chứng cùng nhóm “điều biết”; có hai màn hình nhập không làm thành MFA.

**Không phải mọi mã gửi qua email hoặc SMS đều cho cùng mức bảo đảm.** Email có thể được truy cập ngay trong cùng phiên trên thiết bị đã bị chiếm quyền; SMS có thể bị chuyển SIM (SIM swap), can thiệp hạ tầng hoặc lừa người dùng cung cấp mã. Độ độc lập của yếu tố, cách đăng ký thiết bị, xác thực giao dịch và khả năng khôi phục tài khoản đều ảnh hưởng đến mức bảo đảm thực tế.

### 2.1. 2FA, MFA và xác thực nhiều bước

- **2FA (two-factor authentication)**: đúng hai nhóm yếu tố độc lập.
- **MFA**: từ hai nhóm yếu tố trở lên; trong nhiều sản phẩm, “2FA” và “MFA” được dùng gần nghĩa nhưng cần kiểm xem có thực sự độc lập không.
- **Two-step verification**: hai bước xác minh; không bảo đảm hai nhóm yếu tố khác nhau.
- **Passwordless authentication**: không dùng mật khẩu truyền thống; **có thể** đạt mức bảo đảm đa yếu tố khi authenticator mật mã kết hợp sở hữu khóa với **user verification** bằng PIN hoặc sinh trắc, nhưng không phải mọi lần đăng nhập passwordless đều mặc nhiên tương đương MFA.

Một vân tay được dùng **để mở khóa cục bộ** trên điện thoại chưa có nghĩa sinh trắc học được gửi tới Authorization Server. Chẳng hạn, WebAuthn thường dùng dấu hiệu xác minh người dùng trên thiết bị để cho phép ký thử thách bằng khóa riêng; phía máy chủ kiểm bằng khóa công khai, không cần nhận dữ liệu vân tay.

### 2.2. Mục tiêu an ninh của MFA

Khi mật khẩu bị lộ từ phishing hoặc rò rỉ cơ sở dữ liệu, kẻ tấn công vẫn phải vượt qua yếu tố còn lại. Tuy nhiên, MFA không tự ngăn mọi nguy cơ:

- OTP nhập vào website giả có thể được chuyển tiếp ngay sang website thật.
- Người dùng có thể bấm chấp thuận nhầm các yêu cầu push liên tiếp (*MFA fatigue*).
- Phiên đăng nhập hoặc bearer token bị đánh cắp **sau khi MFA hoàn tất** có thể bị tái sử dụng.
- Khôi phục tài khoản yếu có thể cho phép kẻ tấn công vô hiệu hóa hoặc thay đổi MFA.

Vì vậy, mức assurance phải tính cả **sức mạnh phương thức xác thực và cách bảo vệ phiên/token sau đó**.

## 3. Độ mạnh của các phương thức MFA

| Phương thức | Đặc điểm | Rủi ro đáng chú ý | Hướng dùng phù hợp |
|---|---|---|---|
| **Mật khẩu + SMS OTP** | Dễ triển khai, có thể dùng trên nhiều loại điện thoại | SIM swap, chuyển tiếp mã/phishing, phụ thuộc kênh viễn thông | Phương án dự phòng hoặc khi chính sách chấp nhận mức bảo vệ này |
| **Mật khẩu + TOTP** | Mã sinh từ secret, thay đổi theo thời gian; không cần sóng di động | Có thể bị phishing chuyển tiếp theo thời gian thực; secret bị sao chép hoặc lưu không an toàn | Phổ biến cho ứng dụng thông thường nếu được triển khai đúng |
| **Mật khẩu + push MFA** | Người dùng xác nhận yêu cầu trên ứng dụng/thiết bị đã đăng ký | Push fatigue, nhấn chấp thuận nhầm; kiểu push không ràng buộc đúng ngữ cảnh | Nên có number matching, chi tiết yêu cầu và giới hạn tần suất |
| **FIDO2/WebAuthn với xác minh người dùng** | Authenticator dùng khóa mật mã và ràng buộc với nguồn gốc website (origin) | Thiết bị, đồng bộ và quy trình khôi phục cần chính sách chặt chẽ | Ưu tiên cho truy cập nhạy cảm, nhu cầu chống phishing |
| **Khóa bảo mật chuyên dụng** | Có thể bảo vệ khóa bằng phần cứng và thực hiện xác minh người dùng theo năng lực thiết bị | Mất khóa, cơ chế dự phòng kém, cấu hình yêu cầu UV không đúng | Phù hợp tài khoản đặc quyền và yêu cầu assurance cao |

**Phishing-resistant MFA** là thuộc tính cần kiểm tra dựa trên **giao thức và cách triển khai**, không dựa vào nhãn “MFA”. FIDO2/WebAuthn có cơ chế ràng buộc xác thực với origin của dịch vụ; mã TOTP hay SMS thường không có ràng buộc tương đương nên vẫn có thể bị chuyển tiếp.

WebAuthn có hai khái niệm dễ nhầm:

- **User presence (UP)**: có tương tác của người dùng, ví dụ chạm khóa bảo mật.
- **User verification (UV)**: authenticator xác minh người dùng bằng PIN, sinh trắc hoặc cơ chế tương ứng.

Nếu chính sách yêu cầu sự kết hợp yếu tố sở hữu và yếu tố thứ hai, máy chủ phải kiểm **đúng thuộc tính UV** và chính sách loại authenticator. Chỉ nhìn thấy thao tác “chạm khóa” không đủ để suy ra đã có xác minh đa yếu tố.

## 4. Ba mức tin cậy cần tách riêng

Giả sử AS vừa phát hành một JWT access token hợp lệ. Có ba câu hỏi riêng biệt:

| Tầng | Câu hỏi | Ví dụ điều kiện |
|---|---|---|
| **Authentication assurance** | Người dùng/chủ thể được xác thực bằng cơ chế nào, ở mức bảo đảm nào, lúc nào? | MFA đã hoàn thành? Phương thức có chống phishing? Lần xác thực gần nhất cách đây bao lâu? |
| **Token validity / trust** | Token có đúng do issuer tin cậy cấp, dành cho API này, còn hiệu lực và chưa bị sửa không? | Chữ ký hoặc introspection, `iss`, `aud`, `exp`, loại token, trạng thái thu hồi |
| **Authorization** | Với chủ thể và bằng chứng đang có, request này có được thực hiện trên tài nguyên cụ thể không? | Scope, role, tenant, quyền sở hữu, mức rủi ro nghiệp vụ |

**Một tầng đạt không suy ra hai tầng còn lại cũng đạt.**

- Người dùng đăng nhập bằng FIDO2 rất mạnh nhưng access token có `aud` dành cho `payments-api` không hợp lệ để dùng tại `orders-api`.
- Access token đúng chữ ký và `scope: transfer:write` vẫn có thể thiếu mức xác thực hoặc độ mới mà API chuyển tiền yêu cầu.
- Người dùng có MFA đúng chính sách nhưng không có quyền xem tài khoản của người khác thì vẫn phải bị từ chối.

Bên **Authorization Server / OpenID Provider (AS/OP)** quyết định cấp token theo kết quả xác thực và chính sách của mình. **Resource Server (API)** xác minh token và áp dụng điều kiện truy cập của API. **OIDC Client** xác minh ID token được OP cấp cho chính client. Không được lấy “đăng nhập bằng MFA” làm cớ để bỏ kiểm token hoặc kiểm quyền.

### 4.1. Không tồn tại claim JWT chuẩn tên là “mfa=true” áp dụng chung

Hệ thống có thể tự thiết kế một claim tùy biến, nhưng ứng dụng phải thống nhất **ai đặt giá trị, ý nghĩa của giá trị, thời hạn có hiệu lực và điều kiện chấp nhận**. Tránh diễn giải tùy tiện các claim:

- `mfa_enabled: true` có thể chỉ nói **tài khoản đã đăng ký MFA**, không nói lần đăng nhập hiện tại đã qua MFA.
- `mfa_verified: true` không cho biết phương thức nào, từ lúc nào, hay có chống phishing không nếu thiếu hợp đồng dữ liệu.
- `iat` cho biết **token được phát hành khi nào**, không chứng minh người dùng vừa thực hiện MFA lúc đó.
- `scope` cho biết phạm vi ủy quyền, **không phải** mức bảo đảm danh tính.
- `jti` giúp định danh token; riêng việc có `jti` **không chống phát lại**.

Trong OAuth 2.0, access token có thể là JWT tự chứa hoặc opaque token phải introspect. Cả hai đều có thể biểu đạt **ngữ cảnh assurance** nếu AS và API có hợp đồng rõ ràng; không thể đo mức bảo đảm chỉ bằng định dạng token.

## 5. Biểu diễn assurance trong OpenID Connect

OIDC định nghĩa một số claim dùng để diễn đạt ngữ cảnh xác thực trong **ID token**. Đây là bằng chứng dành cho **OIDC Client**, chứ ID token không thay thế access token của API.

| Claim | Diễn giải | Điều không thể tự suy ra |
|---|---|---|
| `acr` — Authentication Context Class Reference | Định danh **lớp/ngữ cảnh xác thực** theo chính sách issuer và hệ thống liên quan | Không tự có thứ tự “cao/thấp”; giá trị chỉ có ý nghĩa theo hợp đồng |
| `amr` — Authentication Methods References | Danh sách tham chiếu các phương thức đã tham gia xác thực | Không tự chứng minh đã chống phishing hoặc đúng mức AAL |
| `auth_time` | Mốc thời gian người dùng được xác thực ở OP (NumericDate, giây từ Unix epoch) | Không tương đương `iat`; không bảo đảm mọi lần phát hành token đều có xác thực lại |
| `iat` | Thời gian phát hành token | Không phải thời gian MFA |
| `iss` | Nguồn phát hành token | Không phải danh tính người dùng |
| `aud` | Bên nhận token được chỉ định | ID token thường dành cho client; access token cần audience của API |

Ví dụ **payload ID token minh họa** được OP cấp cho OIDC client `bank-web`:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "bank-web",
  "iat": 1893452500,
  "exp": 1893453100,
  "auth_time": 1893452400,
  "acr": "urn:example:authn:strong",
  "amr": ["pwd", "otp"]
}
~~~

Giá trị `urn:example:authn:strong` do hệ thống ví dụ định nghĩa; nó **không phải** tên cấp bảo đảm được toàn bộ nhà cung cấp danh tính hiểu như nhau. `amr` gồm `pwd` và `otp` có thể phản ánh mật khẩu cộng phương thức OTP, nhưng chưa đủ để khẳng định xác thực chống phishing. Cần xem chính sách của issuer, phương thức thực tế và ngữ nghĩa đã ký kết.

### 5.1. `acr`, `amr` và `auth_time` bổ trợ cho nhau

- `acr` diễn đạt **ngữ cảnh/mức bảo đảm đã đạt theo chính sách OP**.
- `amr` giúp giải thích **các phương thức được sử dụng**; một phương thức có thể có nhiều yếu tố bên trong.
- `auth_time` giúp kiểm **độ mới (freshness)** của sự kiện xác thực.

Ví dụ API yêu cầu “phương thức được issuer đánh giá là mạnh **và** xác thực cách đây không quá 5 phút”. Một token có `acr` phù hợp nhưng `auth_time` quá cũ vẫn không đủ. Một token có `auth_time` mới nhưng chỉ dùng phương thức yếu cũng không đủ.

Cần lưu ý ba claim này là thông tin về một **sự kiện xác thực**; chúng không thay thế kiểm trạng thái phiên, phát hiện nguy cơ, kiểm quyền và bảo vệ bearer token.

### 5.2. AAL theo NIST và `acr` là hai khái niệm khác nhau

Khung **Authenticator Assurance Level (AAL)** của NIST SP 800-63B là tập mức yêu cầu về quy trình và authenticator. Các mức AAL có yêu cầu về bằng chứng xác thực, sức mạnh cơ chế, khả năng chống tấn công và vận hành. **Không thể biến token thành “AAL cao” chỉ bằng cách thêm claim**.

`acr` trong OIDC là **một giá trị ngữ cảnh**. Chỉ khi OP có tài liệu/cam kết ánh xạ giá trị `acr` sang chính sách xác thực cụ thể thì client hoặc Resource Server mới có thể dùng mapping đó để yêu cầu mức bảo đảm phù hợp. Không nên tự suy ra `acr = "2"` tức AAL2, hoặc `acr = "3"` tức AAL3 trong mọi hệ thống.

## 6. Luồng đăng nhập MFA, phát hành token và kiểm tra API

Sơ đồ dùng ứng dụng ngân hàng với Authorization Code + PKCE, OP kiêm AS và Resource Server là API ngân hàng.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as OIDC Client (bank-web)
    participant AS as OP / Authorization Server
    participant API as Banking Resource Server
    U->>C: Bắt đầu đăng nhập
    C->>AS: Authorization Code + PKCE (state, nonce nếu cần)
    AS->>U: Xác thực bằng yếu tố thứ nhất
    AS->>U: Thực hiện MFA theo chính sách
    U-->>AS: Hoàn tất thử thách MFA
    AS->>AS: Ghi ngữ cảnh phương thức và auth_time
    AS-->>C: Authorization code
    C->>AS: Đổi code với code_verifier
    AS-->>C: Access token + ID token (+ refresh token nếu cấp)
    C->>C: Xác minh ID token theo OIDC
    C->>API: Bearer access token
    API->>API: Xác minh token, audience, scope và chính sách assurance
    API-->>C: Kết quả cấp quyền hoặc từ chối
~~~

Các bước đáng chú ý:

1. AS/OP là nơi **thực thi và đánh giá MFA**, theo phương pháp xác thực và chính sách của mình; client không được tùy ý tự tuyên bố người dùng đã đạt MFA.
2. Trong OIDC, client nhận **ID token dành cho mình** và kiểm các điều kiện của ID token (issuer, audience, chữ ký, thời gian, nonce/azp khi áp dụng).
3. API nhận **access token dành cho API** và xác minh độc lập: issuer, audience, chữ ký nếu JWT hoặc introspection nếu opaque, thời hạn, scope và quyền.
4. Nếu API cần thông tin assurance, AS phải cung cấp **thông tin được xác thực và định nghĩa ngữ nghĩa rõ ràng cho Resource Server**; không chuyển nguyên ID token sang API rồi dùng như access token.

### 6.1. Mang thông tin assurance đến API bằng cách nào?

Có nhiều mô hình hợp lệ, tùy kiến trúc:

| Mô hình | Cách Resource Server nhận thông tin | Điều kiện tin cậy |
|---|---|---|
| **JWT access token có claim assurance** | AS đưa các claim đã thỏa thuận vào access JWT | API kiểm chữ ký, issuer, audience, token profile rồi mới dùng claim |
| **Opaque access token + introspection** | AS trả thông tin assurance qua endpoint introspection | API xác thực đúng AS, dùng kênh bảo mật, kiểm `active` và ngữ nghĩa metadata |
| **Gateway / session service đáng tin cậy** | Thành phần kiểm chứng upstream truyền ngữ cảnh xuống service | Kết nối nội bộ được xác thực; header do client ngoài không thể giả mạo; service còn kiểm quyền nghiệp vụ |

Ví dụ **payload access token** được AS và API thống nhất sử dụng:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": ["banking-api"],
  "scope": "accounts:read transfer:create",
  "client_id": "bank-web",
  "iat": 1893452500,
  "exp": 1893453100,
  "auth_time": 1893452400,
  "acr": "urn:example:authn:strong",
  "amr": ["pwd", "otp"]
}
~~~

Đây là **ví dụ về hợp đồng claim của hệ thống**, không có nghĩa mọi JWT OAuth access token bắt buộc chứa `acr`, `amr`, `auth_time`. Cũng không có nghĩa access token đã biết là JWT sẽ an toàn để lộ cho JavaScript hoặc client không tin cậy.

Nếu API không có bằng chứng assurance tin cậy, nó nên coi yêu cầu **chưa thỏa điều kiện bảo đảm**, thay vì suy đoán từ `iat`, `scope` hoặc việc tài khoản bật MFA.

## 7. Step-up authentication: yêu cầu xác thực mạnh hơn khi cần

Không phải mọi hành động đều cần cùng mức xác thực. Ví dụ:

- Xem danh sách giao dịch: access token hợp lệ, scope đọc phù hợp.
- Chuyển một khoản tiền lớn: yêu cầu lớp xác thực mạnh và **sự kiện xác thực gần đây**, ngoài scope chuyển tiền và quyền với tài khoản nguồn.
- Thay đổi phương thức MFA, reset mật khẩu hoặc xuất khóa API: yêu cầu chính sách xác minh bổ sung, có thể cần xác thực lại bằng phương thức chống phishing.
- Đăng nhập từ bối cảnh rủi ro cao: yêu cầu điều kiện mạnh hơn theo đánh giá rủi ro.

**Step-up** là quá trình yêu cầu xác thực thêm hoặc xác thực lại để đáp ứng chính sách của một hành động cụ thể.

### 7.1. Luồng step-up cho thao tác chuyển tiền

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Client
    participant API as Transfer API
    participant AS as Authorization Server / OP
    C->>API: POST /transfers + access token hiện tại
    API->>API: Kiểm token và quyền; assurance chưa đủ
    API-->>C: 401: insufficient_user_authentication (yêu cầu ACR/freshness)
    C->>AS: Bắt đầu authorization request với acr_values/max_age phù hợp
    AS->>U: Xác thực thêm hoặc xác thực lại theo chính sách
    U-->>AS: Hoàn tất thử thách
    AS-->>C: Authorization code qua redirect
    C->>AS: Đổi code (PKCE, xác thực client nếu cần)
    AS-->>C: Access token mới với ngữ cảnh assurance phù hợp
    C->>API: Gửi lại POST /transfers với token mới
    API->>API: Kiểm token, assurance, scope, ownership và giao dịch
    API-->>C: Thành công hoặc từ chối theo chính sách
~~~

Theo **RFC 9470** (OAuth 2.0 Step Up Authentication Challenge Protocol), Resource Server có thể dùng HTTP `401` cùng `WWW-Authenticate` Bearer challenge để nêu yêu cầu xác thực người dùng chưa đủ. Ví dụ minh họa:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="insufficient_user_authentication", acr_values="urn:example:authn:strong", max_age="300"
Cache-Control: no-store
~~~

Client sau đó có thể yêu cầu xác thực tại AS/OP qua authorization endpoint:

~~~http
GET /authorize?
  response_type=code&
  client_id=bank-web&
  redirect_uri=https%3A%2F%2Fbank.example.com%2Fcallback&
  scope=openid%20transfer%3Acreate&
  state=opaque-state&
  code_challenge=encoded-challenge&
  code_challenge_method=S256&
  acr_values=urn%3Aexample%3Aauthn%3Astrong&
  max_age=300
~~~

Đây là **đoạn minh họa đã xuống dòng cho dễ đọc**, không phải URL dùng trực tiếp. Client phải tạo và xác minh `state`/PKCE đúng chuẩn; `nonce` cần thiết tùy kiểu luồng và chính sách OIDC. `acr_values` là **yêu cầu/ưu tiên về ngữ cảnh xác thực**; không bảo đảm OP nhất định đã thỏa. Client và API cần **kiểm kết quả thực tế** trong bằng chứng nhận được. `max_age=300` biểu thị giới hạn độ tuổi xác thực theo OIDC; API cũng phải kiểm độ mới theo nguồn dữ liệu đã tin cậy.

**Phân biệt mã lỗi:** token thiếu/hỏng thường dẫn tới `401` (ví dụ `invalid_token`); khi cần step-up theo RFC 9470, dùng `401` với `insufficient_user_authentication`; nếu token hợp lệ nhưng thiếu quyền/scope, Resource Server có thể dùng `403` với `insufficient_scope` theo OAuth Bearer. Triển khai cần thống nhất hành vi với client để tránh vòng lặp xác thực vô hạn.

### 7.2. Cách kiểm tra độ mới

Giả sử chính sách yêu cầu xác thực mạnh trong vòng 5 phút. Khi đó:

~~~text
request_time = trusted_server_clock.now()
access = verifyAccessToken(request.bearer, trustedIssuer, audience="banking-api")

if access.invalid:
    return 401 invalid_token

if not access.hasScope("transfer:create"):
    return 403 insufficient_scope

if not trustedAssurancePolicy.meetsRequiredClass(access.acr, "strong"):
    return 401 insufficient_user_authentication

if access.auth_time is missing:
    return 401 insufficient_user_authentication

if request_time - access.auth_time > 300 seconds:
    return 401 insufficient_user_authentication

if not businessPolicy.canTransfer(access.subject, request.sourceAccount):
    return 403 forbidden

if not riskPolicy.allowsTransfer(request, access):
    return reject_or_additional_verification

return executeTransferIdempotently(request)
~~~

Đây là **pseudocode**, không phải thư viện bảo mật dùng trực tiếp. Trong hệ thống thật còn cần xử lý `auth_time` tương lai bất thường, sai lệch đồng hồ hợp lý, chống phát lại giao dịch, hạn mức, kiểm tình trạng tài khoản và các điều kiện dành riêng cho giao dịch.

**Sai lầm phổ biến:** token vừa được refresh có `iat` cách đây 5 giây, nhưng `auth_time` của lần đăng nhập là 8 giờ trước. Nếu chỉ so thời gian `iat`, API sẽ kết luận sai rằng vừa có MFA. **Refresh token grant không tự chứng minh người dùng vừa xác thực lại.** AS phải thể hiện đúng thời điểm xác thực trong ngữ cảnh cấp token.

### 7.3. Khi nào cần gắn bảo đảm với giao dịch?

“Vừa qua MFA” có thể chưa đủ cho lệnh chuyển tiền lớn hoặc thay đổi người thụ hưởng. Một hệ thống có thể yêu cầu người dùng xem và xác nhận **đích nhận, số tiền hoặc hành động cụ thể**, và ràng buộc bằng chứng xác nhận với chính giao dịch đó. Đây là **transaction authorization/confirmation**, không tự phát sinh từ claim `acr` chung của phiên.

Nếu giao dịch được gửi lại sau step-up, API phải tránh thực thi trùng. Có thể dùng idempotency key, trạng thái giao dịch một lần và kiểm tra dữ liệu được ký/xác nhận khi kiến trúc yêu cầu. Không được coi `jti` của access token là khóa chống trùng cho từng lệnh chuyển tiền.

## 8. Token vẫn có thể bị đánh cắp sau MFA

MFA làm khó việc **đăng nhập trái phép**, nhưng token đã phát hành có vòng đời riêng. Sơ đồ rủi ro:

~~~mermaid
flowchart LR
    A[Người dùng xác thực bằng MFA] --> B[Authorization Server cấp access token]
    B --> C[Client giữ access token]
    C --> D[Client gửi token đến API]
    C -. XSS hoặc lộ log .-> E[Kẻ tấn công lấy bearer token]
    E --> F[Kẻ tấn công phát lại token]
    F --> D
    D --> G{Token hợp lệ và đủ quyền?}
    G -->|Có, không ràng buộc người gửi| H[Request có thể được chấp nhận]
    G -->|Không| I[Từ chối]
~~~

Điều này xảy ra vì **bearer token** về cơ bản được sử dụng bởi bên nào đang cầm token. Chữ ký JWT xác nhận nội dung token không bị sửa và nguồn phát hành đã được tin; chữ ký **không chứng minh người gửi request hiện tại chính là người vừa hoàn tất MFA**.

Các biện pháp có quan hệ bổ trợ:

| Biện pháp | Giảm rủi ro gì? | Giới hạn |
|---|---|---|
| **Access token TTL ngắn** | Giảm thời gian token rò rỉ còn dùng được | Vẫn có cửa sổ bị lạm dụng trước `exp` |
| **Audience và scope tối thiểu** | Giới hạn API và thao tác token được dùng | Không thay kiểm quyền tài nguyên cụ thể |
| **Refresh token rotation** | Phát hiện/hạn chế việc tái dùng refresh token bị đánh cắp | Không chặn được access token bị dùng trước khi hết hạn |
| **Thu hồi/introspection/denylist** | Có thể vô hiệu hóa sớm token hoặc phiên | JWT tự xác minh không tự biết thu hồi; cache có thể làm trễ |
| **DPoP hoặc mTLS sender-constrained token** | Ràng buộc token với bằng chứng sở hữu khóa của bên gửi | Cần kiểm proof/khóa, hạn chế replay và bảo vệ khóa theo đúng giao thức |
| **Phương thức MFA chống phishing** | Giảm việc đánh cắp bằng chứng đăng nhập | Không bảo đảm token/phiên sau đăng nhập không bị lấy cắp |
| **Chính sách step-up / giao dịch** | Hạn chế thực hiện thao tác nhạy cảm từ phiên cũ hoặc yếu | Cần cơ chế gắn assurance với sự kiện và ngữ cảnh đang xét |
| **TLS, lưu trữ an toàn, CSP và chống XSS** | Giảm khả năng lộ token qua mạng/trình duyệt | Cần cấu hình và kiểm soát xuyên suốt đường đi |

Với DPoP, client tạo proof mật mã gắn với request; Resource Server kiểm chữ ký proof, ràng buộc khóa, phương thức/URL request, thời gian, `jti` và các điều kiện liên quan như nonce khi áp dụng. Chỉ thêm `cnf` vào token nhưng API không kiểm bằng chứng sở hữu khóa sẽ không tạo ra ràng buộc thực sự.

Với mTLS, Resource Server kiểm chứng liên kết token với chứng chỉ client theo profile tương ứng. Không nên coi hai cơ chế trên là kết quả tự động của MFA: **chúng giải quyết rủi ro ở giai đoạn sử dụng token**, khác với giai đoạn xác thực người dùng.

## 9. Thiết kế vòng đời assurance: phát hành, refresh, thu hồi và phục hồi

### 9.1. Lúc phát hành token

Authorization Server nên có nguồn dữ liệu đáng tin cậy về:

1. Người dùng hoặc client nào đã xác thực, thông qua grant nào.
2. Phương thức xác thực thực tế và bằng chứng đi kèm, cùng chính sách ánh xạ thành assurance class.
3. Thời điểm xác thực đủ yêu cầu và thời gian còn được coi là mới.
4. Audience, scope được cấp, TTL, trạng thái phiên và các ràng buộc token nếu có.

Resource Server không nên tự dựng assurance từ thông tin do client đưa trong body/header request (ví dụ `mfa=true` hoặc `x-auth-level: strong`).

### 9.2. Lúc refresh token

Một refresh token có thể tồn tại lâu hơn access token. Lúc đổi refresh token, AS cần kiểm token còn hợp lệ, được dùng bởi client phù hợp, chưa bị thu hồi và tuân thủ rotation/sender binding. **Không nâng mức assurance chỉ vì refresh thành công**; chỉ cấp hoặc duy trì assurance dựa trên chính sách và sự kiện xác thực đã kiểm chứng.

Ví dụ nếu yêu cầu của API là “MFA trong 5 phút gần đây”, thì sau 30 phút kể từ lần MFA, client phải **step-up** cho thao tác đó dù vừa nhận access token mới từ refresh grant.

### 9.3. Lúc thu hồi, đăng xuất và khóa tài khoản

- **Logout** kết thúc phiên ứng dụng hoặc phiên tại OP theo cơ chế được hỗ trợ; không được mặc định mọi JWT đã cấp đều bị vô hiệu hóa ngay.
- **Thu hồi refresh token** hạn chế việc xin access token tiếp theo, nhưng không bảo đảm access token trước đó bị từ chối ngay.
- **Trạng thái quyền và rủi ro thay đổi** (khóa người dùng, mất thiết bị MFA, nâng/hạ quyền, nghi ngờ account takeover) có thể đòi hỏi introspection, danh sách thu hồi, TTL ngắn hoặc các kiểm tra trạng thái bổ sung.
- **Thay đổi yếu tố MFA** phải có xác minh đủ mạnh, thông báo bảo mật và cơ chế giám sát; không được cho người nắm phiên yếu có thể lặng lẽ xóa yếu tố mạnh.

### 9.4. Quy trình mất thiết bị và khôi phục tài khoản

Một kẻ tấn công có thể không phá được WebAuthn nhưng chiếm tài khoản bằng đường “Tôi mất thiết bị”. Bởi vậy, assurance toàn hệ thống phụ thuộc quy trình **đăng ký authenticator mới, reset MFA, recovery codes và hỗ trợ người dùng**:

- Recovery codes nên là mã một lần, sinh đủ ngẫu nhiên, được bảo vệ và có cơ chế vô hiệu hóa sau sử dụng.
- Đăng ký khóa/thiết bị mới nên yêu cầu bước xác minh đủ mạnh và tạo audit event rõ ràng.
- Với tài khoản đặc quyền hoặc hành động nhạy cảm, nên đánh giá rủi ro kỹ hơn và cân nhắc trì hoãn/kiểm duyệt khi đổi MFA.
- Không để đường khôi phục yếu làm mất ý nghĩa của yêu cầu MFA mạnh tại đăng nhập.

## 10. Ví dụ chính sách cho hệ thống ngân hàng

Bảng quyết định minh họa. Mức `normal`, `strong` và `phishing-resistant` là **nhãn chính sách nội bộ**, phải được ánh xạ tới sự kiện xác thực và authenticator cụ thể tại AS; không phải chuẩn chung.

| Hành động | Token và quyền | Assurance yêu cầu | Điều kiện bổ sung |
|---|---|---|---|
| `GET /accounts` | Access token đúng `aud=banking-api`, `accounts:read` | `normal` | Chỉ xem tài khoản có quyền |
| `POST /transfers` số tiền thấp | Access token `transfer:create` | `strong` | `auth_time` trong 10 phút, hạn mức, kiểm chủ tài khoản |
| `POST /transfers` số tiền cao | Access token `transfer:create` | `phishing-resistant` | Xác thực mới và xác nhận giao dịch theo chính sách |
| `POST /mfa/reset` | Access token đúng đối tượng API và scope | `phishing-resistant` hoặc quy trình recovery riêng | Kiểm tra rủi ro và bảo vệ thay đổi yếu tố |
| `GET /admin/audit` | Access token `audit:read` | `strong` | Role admin, tenant và nguồn truy cập phù hợp |

Để thực hiện, API cần được cung cấp **ngữ cảnh assurance có nguồn gốc từ AS**. Ví dụ cấu hình chính sách *minh họa*, không phải cú pháp của một framework cụ thể:

~~~yaml
resourceServer:
  issuer: https://login.example.com
  audience: banking-api
  acceptedTokenPurpose: access_token

assuranceMapping:
  normal:
    issuerAcrValues: ["urn:example:authn:normal"]
  strong:
    issuerAcrValues: ["urn:example:authn:strong"]
  phishingResistant:
    issuerAcrValues: ["urn:example:authn:phishing-resistant"]

routes:
  "GET /accounts":
    scope: accounts:read
    requiredAssurance: normal
  "POST /transfers":
    scope: transfer:create
    requiredAssurance: strong
    maxAuthAgeSeconds: 300
    additionalChecks: [accountOwnership, transactionRisk, idempotency]
~~~

**Cảnh báo khi diễn giải mapping:** Đừng dùng so sánh chuỗi để suy ra `phishing-resistant > strong > normal`. Phải có chính sách do AS và API cùng hiểu, với quy tắc rõ về quan hệ giữa các lớp xác thực. Hệ thống có thể có các lớp **không so sánh trực tiếp được**: ví dụ phương thức chống phishing nhưng quá cũ vẫn không đáp ứng chính sách “xác thực gần đây”.

## 11. Các tình huống đánh giá đúng/sai

Giả sử API `banking-api` yêu cầu issuer `https://login.example.com`. Endpoint chuyển tiền cần `transfer:create`, lớp `strong` và `auth_time` không quá 5 phút.

| Tình huống | API nên xử lý | Lý do |
|---|---|---|
| JWT đúng issuer, audience, chữ ký; có scope; `acr=strong` và `auth_time` cách đây 2 phút | **Có thể tiếp tục kiểm quyền và giao dịch** | Đạt điều kiện token và assurance sơ bộ; vẫn phải kiểm quyền trên tài khoản nguồn |
| JWT cùng issuer nhưng `aud=orders-api` | **Từ chối** | Token không được cấp cho API ngân hàng |
| Chỉ gửi ID token có `amr=["pwd","otp"]` | **Từ chối** | ID token dành cho OIDC Client; API cần access token |
| Access token đúng scope nhưng thiếu bằng chứng assurance tin cậy | **Yêu cầu step-up/từ chối** | Không thể tự suy diễn MFA từ scope |
| `acr=strong`, `auth_time` cách đây 2 giờ; `iat` cách đây 30 giây do refresh | **Yêu cầu step-up** | Thời gian phát hành token không phải thời gian xác thực |
| `amr=["pwd","otp"]`, nhưng API yêu cầu xác thực chống phishing | **Không tự coi là đạt** | OTP có thể bị phishing; cần mapping chính sách phương thức thực tế |
| Tài khoản đã đăng ký MFA nhưng chỉ đăng nhập bằng mật khẩu | **Không coi là đạt MFA** | Đăng ký yếu tố không chứng minh đã sử dụng trong sự kiện xác thực |
| Token hợp lệ và MFA mới, nhưng không có quyền với tài khoản nguồn | **Từ chối** | Authorization/ownership là kiểm tra riêng |
| Access token bị đánh cắp ngay sau khi MFA | **Có thể bị phát lại nếu là bearer token** | MFA không tự ràng buộc token với người đang gửi request |
| DPoP-bound token nhưng API bỏ kiểm DPoP proof | **Triển khai sai chính sách** | Thiếu kiểm proof làm vô hiệu mục tiêu ràng buộc người gửi |

### Bài tập 1 — Phân loại yếu tố

Cho các cặp dưới đây, hãy đánh giá có thể coi là MFA đúng nghĩa không:

1. Mật khẩu + câu hỏi “Tên thú cưng đầu tiên?”.
2. Mật khẩu + ứng dụng TOTP đã đăng ký trên thiết bị độc lập.
3. Đăng nhập bằng passkey có user verification, khóa riêng trong authenticator.
4. Nhấn “Approve” khi điện thoại nhận hàng chục yêu cầu push lạ.

**Gợi ý:** (1) không đủ hai nhóm yếu tố; (2) thường đạt hai nhóm yếu tố nếu triển khai và đăng ký đúng; (3) có thể đạt xác thực mật mã đa yếu tố tùy cơ chế và chính sách, cần kiểm UV; (4) có nguy cơ MFA fatigue và chấp thuận nhầm, không thể lấy thao tác bấm làm bằng chứng assurance đáng tin trong mọi bối cảnh.

### Bài tập 2 — Thiết kế thử nghiệm âm tính

Viết các trường hợp kiểm thử API chuyển tiền:

- Sai chữ ký, sai issuer, sai audience, hết hạn, token sai mục đích.
- Có scope nhưng không có quyền với tài khoản nguồn.
- `acr` thiếu, `acr` không được công nhận, `auth_time` thiếu/quá cũ.
- Refresh access token mới nhưng không thực hiện lại MFA.
- Hết hạn phiên/thu hồi; token vừa bị lộ; yêu cầu chuyển tiền được gửi lại sau step-up.
- Thay yếu tố MFA bằng quy trình recovery yếu.

Ở mỗi trường hợp, phân biệt **token invalid**, **insufficient scope**, **insufficient user authentication** và **business authorization denied**, rồi kiểm xem client có thể xử lý thông báo đúng hay không.

## 12. Checklist triển khai an toàn

- [ ] Đã xác định nguồn phát hành token và nơi thực thi MFA; không tin cờ MFA do client tự gửi.
- [ ] Có chính sách chọn authenticator, mức chống phishing, yêu cầu UV và trường hợp khôi phục tài khoản.
- [ ] Đã định nghĩa chính xác giá trị `acr`/`amr`, đơn vị và nguồn `auth_time`, mapping giữa issuer và API.
- [ ] API kiểm access token đúng `iss`, `aud`, `exp`, chữ ký/JWKS hoặc introspection, trạng thái và loại token.
- [ ] Không dùng ID token thay access token; không nhầm `iat` của token refresh với thời điểm MFA.
- [ ] Có quy tắc yêu cầu step-up cho thao tác nhạy cảm, độ mới của xác thực và điều kiện chống lặp vòng chuyển hướng.
- [ ] Scope, role, tenant, quyền sở hữu tài nguyên và risk check vẫn được thực hiện sau khi assurance đạt.
- [ ] Token được lưu và truyền an toàn; bảo vệ chống XSS, log leak, phishing và token replay.
- [ ] Refresh token rotation/sender binding, TTL, revoke và cơ chế logout đã được thiết kế theo rủi ro.
- [ ] Đã kiểm thử request token thiếu/không hợp lệ, assurance thiếu/quá cũ, recovery yếu và token bị phát lại.
- [ ] Log sự kiện xác thực/step-up đủ để điều tra nhưng không ghi mật khẩu, OTP, access/refresh token hoặc dữ liệu nhạy cảm.

**Ghi nhớ:** MFA tăng độ tin cậy đối với **sự kiện xác thực**; token assurance giúp API đánh giá **bằng chứng đã được issuer xác nhận và còn phù hợp với request hiện tại hay không**. Một access token vẫn phải được kiểm đúng issuer, audience, thời hạn, phạm vi và quyền; với thao tác nhạy cảm, API cần assurance và freshness phù hợp. **MFA mạnh không tự biến bearer token thành token chống đánh cắp hoặc chống phát lại.**

### Tài liệu chuẩn để đọc sâu

- **OpenID Connect Core 1.0** — `acr`, `amr`, `auth_time`, `max_age` và xác minh ID token.
- **RFC 8176** — Authentication Method Reference Values (`amr`).
- **RFC 9470** — OAuth 2.0 Step Up Authentication Challenge Protocol.
- **RFC 6749** — The OAuth 2.0 Authorization Framework.
- **RFC 6750** — OAuth 2.0 Bearer Token Usage.
- **RFC 9068** — JWT Profile for OAuth 2.0 Access Tokens.
- **RFC 7662** — OAuth 2.0 Token Introspection.
- **RFC 9449** — OAuth 2.0 Demonstrating Proof of Possession (DPoP).
- **RFC 9700** — Best Current Practice for OAuth 2.0 Security.
- **NIST SP 800-63B** — Digital Identity Guidelines: Authentication and Authenticator Management.
- **W3C Web Authentication (WebAuthn)** — xác thực khóa công khai, origin binding, user presence và user verification.
