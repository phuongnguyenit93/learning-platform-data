# nonce, auth_time, acr, amr trong ngữ cảnh OIDC

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** OAuth và OIDC. Bài viết tập trung vào ngữ nghĩa và cách kiểm tra các claim trong OpenID Connect (OIDC), áp dụng độc lập với ngôn ngữ lập trình, thư viện hoặc framework.

## 1. Bốn giá trị, bốn mục đích bảo mật

Trong OIDC, ID Token là JWT chứa thông tin về kết quả xác thực của End-User dành cho client. Ngoài các claim nền tảng như `iss`, `sub`, `aud`, `exp` và `iat`, OIDC còn sử dụng các giá trị giúp client liên kết response với yêu cầu xác thực và đánh giá ngữ cảnh đăng nhập.

- **`nonce`:** liên kết ID Token nhận được với một Authentication Request cụ thể và giảm nguy cơ replay ID Token.
- **`auth_time`:** cho biết thời điểm End-User thực sự được xác thực.
- **`acr`:** cho biết Authentication Context Class mà OpenID Provider (OP) xác nhận đã đạt được.
- **`amr`:** liệt kê các phương thức xác thực được sử dụng trong quá trình xác thực.

Chúng không thể thay thế cho nhau:

| Giá trị | Câu hỏi được trả lời | Ngữ nghĩa chính |
| --- | --- | --- |
| `nonce` | ID Token này có gắn với đúng yêu cầu đăng nhập đang chờ không? | Giá trị đối chiếu giữa request và ID Token |
| `auth_time` | Người dùng được xác thực vào thời điểm nào? | Thời điểm xác thực, không phải thời điểm phát hành token |
| `acr` | Ngữ cảnh/mức bảo đảm xác thực nào được OP xác nhận? | Lớp ngữ cảnh xác thực theo thỏa thuận |
| `amr` | Những phương thức nào đã được dùng? | Danh sách tham chiếu phương thức xác thực |

Một ID Token có chữ ký hợp lệ vẫn phải được kiểm tra theo toàn bộ quy tắc OIDC: issuer, audience, thời hạn, chữ ký, nonce khi áp dụng và các điều kiện khác của flow. Việc nhìn thấy `acr` hoặc `amr` trong payload không tự động chứng minh client có thể tin chúng trước khi xác minh chữ ký và issuer.

Các giá trị này chủ yếu được xem xét trong ID Token và ngữ cảnh xác thực OIDC. Không mặc định coi chúng là claim authorization cho API hoặc tự sao chép sang access token nếu profile của hệ thống không định nghĩa rõ ngữ nghĩa đó.

## 2. nonce: liên kết ID Token với Authentication Request

### 2.1. Ý nghĩa của nonce

`nonce` là giá trị do client tạo và gửi trong Authentication Request. OP trả lại giá trị đó trong claim `nonce` của ID Token nếu request có chứa nonce. Client so sánh giá trị nhận được với giá trị đã gửi để xác nhận ID Token gắn với giao dịch xác thực đang xử lý.

OIDC Core quy định: nếu client gửi `nonce` trong Authentication Request, ID Token phải chứa claim `nonce` với giá trị tương ứng. So sánh có phân biệt chữ hoa/chữ thường; không tự chuẩn hóa, đổi encoding hoặc cắt khoảng trắng trước khi so sánh.

Nonce giúp giảm nguy cơ kẻ tấn công phát lại một ID Token hợp lệ từ phiên hoặc giao dịch khác. Nếu ID Token bị đánh cắp, chữ ký hợp lệ vẫn không đủ để chứng minh nó thuộc yêu cầu đăng nhập hiện tại.

### 2.2. Tạo và quản lý nonce an toàn

Client nên tạo nonce riêng cho từng Authentication Request bằng nguồn ngẫu nhiên mật mã (CSPRNG):

- Dùng giá trị khó đoán, đủ entropy; 128 bit ngẫu nhiên trở lên là lựa chọn thực tế phổ biến.
- Không dùng timestamp, counter đơn giản, username, email hoặc giá trị do người dùng cung cấp.
- Không tái sử dụng nonce giữa các lần đăng nhập hoặc các transaction độc lập.
- Lưu nonce gắn với transaction/session đang chờ để callback tra cứu đúng giá trị.
- Đặt thời hạn lưu ngắn theo thời gian sống của Authentication Request.
- Xóa hoặc đánh dấu đã tiêu thụ sau khi xác minh thành công; không dùng lại cho response khác.
- Không ghi nonce nguyên vẹn vào log thông thường.

Nonce không cần mang ý nghĩa nghiệp vụ. Nó chỉ cần khó đoán trong phạm vi giao dịch và được đối chiếu chính xác.

### 2.3. Kiểm tra nonce khi nhận ID Token

Sau khi xác minh chữ ký và các điều kiện cơ bản của ID Token, client cần:

1. Xác định Authentication Request tương ứng với response.
2. Lấy nonce đã lưu cho transaction đó.
3. Nếu request đã gửi nonce, yêu cầu ID Token phải có claim `nonce`.
4. So sánh chính xác giá trị ID Token với giá trị đã lưu.
5. Từ chối response nếu claim thiếu hoặc khác nhau.
6. Tiêu thụ nonce để response không thể được dùng lại cho transaction khác.

Không chấp nhận nonce thiếu bằng cách tự tạo giá trị mặc định. Không chấp nhận token có nonce khác chỉ vì issuer và chữ ký đều hợp lệ.

### 2.4. nonce khác state và PKCE

Ba giá trị thường xuất hiện cùng lúc trong Authorization Code Flow, nhưng phục vụ các lớp bảo vệ khác nhau:

| Cơ chế | Mục tiêu chính |
| --- | --- |
| `state` | Liên kết request với callback và bảo vệ luồng điều hướng khỏi CSRF; phải được kiểm tra theo transaction |
| `nonce` | Liên kết ID Token với Authentication Request, giảm replay/nhầm response |
| PKCE (`code_verifier` / `code_challenge`) | Ràng buộc việc đổi authorization code với client đã khởi tạo giao dịch, giảm code interception |

Không dùng một giá trị thay cho cả ba chỉ để giảm số biến. Có thể tạo chúng bằng cùng một CSPRNG, nhưng nên tạo giá trị độc lập và lưu theo đúng vai trò. PKCE không thay thế nonce khi flow/profile cần kiểm tra nonce; nonce cũng không thay thế state hoặc PKCE.

### 2.5. nonce trong các flow OIDC

Yêu cầu nonce phụ thuộc flow và response type. OIDC Core quy định nonce là tham số tùy chọn trong Authentication Request nói chung, nhưng có các flow/response type mà nonce là bắt buộc, đặc biệt khi ID Token được trả trực tiếp từ Authorization Endpoint. Client phải tuân thủ yêu cầu của flow và profile cụ thể.

Một thực hành tốt là tạo và gửi nonce trong các luồng OIDC mà client cần ràng buộc ID Token với đúng Authentication Request. Nếu request không gửi nonce và flow cho phép bỏ qua, client không được giả định rằng ID Token sẽ có nonce.

## 3. auth_time: thời điểm xác thực thực sự

### 3.1. Ý nghĩa của auth_time

`auth_time` là NumericDate thể hiện thời điểm End-User được xác thực. Đây là thời điểm xác thực người dùng, không phải thời điểm OP phát hành ID Token.

Phân biệt:

- `auth_time`: thời điểm người dùng thực sự được xác thực.
- `iat`: thời điểm ID Token được phát hành.
- `exp`: thời điểm ID Token hết hạn.

Ví dụ: người dùng đăng nhập bằng mật khẩu và MFA lúc 09:00. Đến 09:20, client thực hiện một yêu cầu xác thực im lặng trong phiên SSO còn hoạt động và OP phát hành ID Token mới. Khi không có một lần xác thực người dùng mới, `iat` có thể là 09:20 nhưng `auth_time` vẫn phản ánh lần xác thực lúc 09:00.

Nếu issuer cập nhật `auth_time` thành thời điểm phát hành mỗi khi cấp ID Token, client có thể hiểu nhầm một phiên cũ là vừa xác thực mới. Điều này làm suy yếu các chính sách yêu cầu xác thực gần đây.

### 3.2. Yêu cầu max_age

Client có thể gửi tham số `max_age` trong Authentication Request để yêu cầu OP bảo đảm lần xác thực của End-User không cũ hơn một khoảng thời gian tính bằng giây.

- `max_age` là giới hạn tuổi của lần xác thực, không phải TTL của ID Token.
- Khi `max_age` được gửi, ID Token phải chứa `auth_time`.
- Giá trị `auth_time` phải phản ánh thời điểm xác thực thực tế.
- Client phải kiểm tra tuổi xác thực theo `auth_time`, có tính đến clock skew nhỏ theo chính sách.
- `max_age=0` tương đương yêu cầu xác thực lại bằng `prompt=login` theo OIDC Core.

Ví dụ: client gửi `max_age=300` để yêu cầu người dùng đã xác thực trong vòng 5 phút. Nếu ID Token có `auth_time` cách thời điểm hiện tại 12 phút, client không được coi điều kiện này đã đạt chỉ vì `iat` mới được tạo vài giây trước.

### 3.3. Kiểm tra auth_time

Sau khi xác minh chữ ký và các claim cơ bản, client cần:

- yêu cầu `auth_time` nếu request đã gửi `max_age`;
- xác minh giá trị là NumericDate hợp lệ;
- từ chối giá trị nằm trong tương lai vượt quá clock skew cho phép;
- kiểm tra tuổi xác thực không vượt `max_age` cộng khoảng sai lệch đồng hồ nhỏ;
- không dùng `iat` thay thế `auth_time`.

Mã giả:

~~~text
function validateAuthenticationAge(claims, request, now, policy):
    if request.maxAge was sent:
        require claims.auth_time exists

    if claims.auth_time exists:
        require isValidNumericDate(claims.auth_time)
        require claims.auth_time <= now + policy.clockSkew

    if request.maxAge was sent:
        age = now - claims.auth_time
        require age <= request.maxAge + policy.clockSkew

    return ACCEPT
~~~

Đây là mô hình kiểm tra khái niệm. Cần xử lý giá trị tương lai, giá trị sai kiểu và quy tắc leeway nhất quán; không nới clock skew quá lớn để che lỗi đồng bộ thời gian.

### 3.4. auth_time và prompt=login

`prompt=login` yêu cầu OP thực hiện xác thực lại người dùng. Client có thể dùng nó khi cần buộc người dùng đăng nhập lại, ví dụ trước một thao tác nhạy cảm.

Client vẫn phải xác minh ID Token và các claim liên quan. Không tự gán `auth_time` bằng thời điểm gửi request hoặc nhận response. OP phải phát hành giá trị phản ánh sự kiện xác thực thực tế.

Cũng cần phân biệt reauthentication với step-up authentication: xác thực lại có thể dùng cùng phương thức trước đó, còn step-up yêu cầu ngữ cảnh hoặc mức bảo đảm cao hơn. Client cần dùng thêm `acr`/`amr` và chính sách issuer nếu muốn đánh giá mức bảo đảm.

## 4. acr: Authentication Context Class Reference

### 4.1. Ý nghĩa

`acr` (Authentication Context Class Reference) là claim mô tả lớp ngữ cảnh xác thực mà OP xác nhận đã đạt được. Giá trị là một chuỗi do OP và bên sử dụng thống nhất, thường có thể là URI/URN hoặc identifier theo profile.

Ví dụ minh họa:

~~~json
{
  "acr": "urn:example:loa:2"
}
~~~

Giá trị trên chỉ là tên lớp do một hệ thống giả định định nghĩa. OIDC không quy định một thang `acr` toàn cầu mà mọi OP đều phải dùng giống nhau.

`acr` không phải role, permission hoặc scope. Một mức xác thực cao không đồng nghĩa người dùng có quyền quản trị; ngược lại, một người dùng có role quản trị không có nghĩa phiên hiện tại đã đạt mức xác thực cao.

### 4.2. Yêu cầu acr_values

Client có thể gửi `acr_values` trong Authentication Request. Đây là chuỗi các giá trị ACR được phân tách bằng khoảng trắng, sắp xếp theo thứ tự ưu tiên mà client mong muốn OP sử dụng.

Ví dụ:

~~~text
acr_values=urn:example:loa:2 urn:example:loa:1
~~~

Tham số này thể hiện ngữ cảnh xác thực mong muốn. Client không được mặc định rằng OP chắc chắn đã đáp ứng chỉ vì request chứa `acr_values`. Sau khi nhận ID Token, client phải đọc và đánh giá claim `acr` thực tế theo trust agreement và policy.

Nếu ứng dụng yêu cầu một mức xác thực tối thiểu cho thao tác nhạy cảm, cần có hợp đồng rõ ràng về các ACR mà OP hỗ trợ và cách ánh xạ từng giá trị sang chính sách nội bộ.

### 4.3. Yêu cầu acr như Essential Claim

OIDC hỗ trợ yêu cầu claim qua tham số `claims`. Client có thể yêu cầu `acr` là Essential Claim trong ID Token, có thể kèm tập giá trị được chấp nhận.

Ví dụ cấu trúc khái niệm:

~~~json
{
  "id_token": {
    "acr": {
      "essential": true,
      "values": [
        "urn:example:loa:2",
        "urn:example:loa:3"
      ]
    }
  }
}
~~~

Khi `acr` được yêu cầu là Essential Claim, OP phải trả claim `acr` trong ID Token; nếu có danh sách giá trị yêu cầu, giá trị trả về phải đáp ứng ràng buộc đã yêu cầu theo OIDC. Client vẫn cần xác minh ID Token và kiểm tra giá trị trả về theo policy. Không được âm thầm hạ yêu cầu nếu OP không đáp ứng.

### 4.4. Không suy luận thứ bậc ACR từ tên

Một lỗi phổ biến là giả định chuỗi có số lớn hơn luôn biểu thị assurance cao hơn, ví dụ `loa:3` chắc chắn mạnh hơn `loa:2`. Điều này chỉ đúng nếu hợp đồng giữa client và OP định nghĩa rõ thứ bậc đó.

Nên duy trì bảng ánh xạ tin cậy:

| ACR do OP phát hành | Cách client diễn giải |
| --- | --- |
| `urn:example:loa:1` | Mức xác thực cơ bản theo hợp đồng |
| `urn:example:loa:2` | Mức xác thực tăng cường theo hợp đồng |
| `urn:example:loa:3` | Mức xác thực mạnh theo hợp đồng |
| Giá trị không biết | Không tự suy diễn; từ chối hoặc áp dụng chính sách hạn chế |

Các giá trị chỉ minh họa. Client cần xác định issuer nào được phép phát hành ACR, ý nghĩa của từng giá trị, bằng chứng xác thực tương ứng, quy trình khôi phục tài khoản và cách xử lý khi OP thay đổi chính sách.

## 5. amr: Authentication Methods References

### 5.1. Ý nghĩa

`amr` là claim mô tả các phương thức xác thực được sử dụng. Trong OIDC, đây thường là một mảng các chuỗi identifier. RFC 8176 định nghĩa một số giá trị AMR tiêu chuẩn để các bên có thể dùng chung cách biểu diễn.

Ví dụ:

~~~json
{
  "amr": ["pwd", "otp"]
}
~~~

Ví dụ trên cho biết OP báo cáo đã sử dụng phương thức mật khẩu và OTP. Nó không tự chứng minh các phương thức này độc lập, chống phishing hoặc đáp ứng một mức assurance cụ thể trong mọi chính sách.

Một số giá trị AMR thường gặp theo RFC 8176:

| Giá trị | Ý nghĩa khái quát |
| --- | --- |
| `pwd` | Xác thực bằng mật khẩu |
| `otp` | One-Time Password |
| `sms` | Xác nhận qua SMS |
| `hwk` | Bằng chứng sử dụng khóa được bảo vệ bằng phần cứng |
| `swk` | Bằng chứng sử dụng khóa được bảo vệ bằng phần mềm |
| `mfa` | Xác thực sử dụng nhiều hơn một yếu tố |
| `fpt` | Nhận diện dấu vân tay |
| `face` | Nhận diện khuôn mặt |
| `pin` | Xác thực bằng PIN |

Đây là các identifier tham khảo; giá trị AMR có thể được mở rộng theo thỏa thuận. Cần kiểm tra cách OP sử dụng các giá trị, đặc biệt với identifier riêng.

### 5.2. AMR không phải ACR

`amr` mô tả phương thức được sử dụng; `acr` mô tả lớp ngữ cảnh xác thực được xác nhận. Chúng liên quan nhưng trả lời hai câu hỏi khác nhau.

Ví dụ:

- `amr` có thể cho biết mật khẩu và OTP đã được sử dụng.
- `acr` có thể xác định kết quả đó đạt một lớp assurance đã thỏa thuận.
- Client dùng `acr` để quyết định phiên có đáp ứng mức bảo đảm yêu cầu không; `amr` giúp hiểu phương thức thực tế và áp dụng quy tắc chi tiết.

Không tự xây dựng một mức ACR chỉ bằng cách đếm số phần tử trong AMR. Hai phương thức có thể thuộc cùng một yếu tố, có mức chống phishing khác nhau hoặc được OP triển khai với chất lượng khác nhau.

### 5.3. Cẩn trọng khi diễn giải MFA

Sự xuất hiện của nhiều giá trị trong `amr` không tự động chứng minh MFA theo tiêu chuẩn của tổ chức. Ví dụ, mật khẩu và một mã gửi qua SMS có thể được xem là hai phương thức trong một số hệ thống, nhưng mức bảo đảm phụ thuộc threat model, khả năng chiếm đoạt kênh SMS, quy trình khôi phục và cách xác minh.

Khi policy yêu cầu MFA hoặc xác thực chống phishing:

- xác định chính xác yếu tố và phương thức nào được chấp nhận;
- tin cậy issuer đã công bố ngữ nghĩa AMR;
- không suy ra factor independence chỉ từ số lượng giá trị;
- không coi mọi OTP hoặc mọi biometric có cùng mức assurance;
- ưu tiên kiểm tra `acr` đã được ánh xạ và thỏa thuận khi cần mức bảo đảm cụ thể;
- nếu AMR thiếu hoặc có giá trị không biết, xử lý theo policy thay vì tự mặc định đạt yêu cầu.

## 6. Kết hợp nonce, auth_time, acr và amr trong một giao dịch

Một giao dịch OIDC có thể dùng cả bốn giá trị:

1. Client tạo `state`, `nonce` và PKCE verifier/challenge riêng.
2. Client gửi Authentication Request, có thể kèm `max_age`, `acr_values` hoặc `claims` để yêu cầu thông tin/mức xác thực.
3. OP xác thực người dùng theo chính sách và phát hành ID Token.
4. Client xác minh chữ ký, issuer, audience, thời gian và các điều kiện OIDC của flow.
5. Client đối chiếu `nonce` với giá trị đã lưu.
6. Nếu có `max_age`, client kiểm tra `auth_time`.
7. Client kiểm tra `acr` và `amr` theo yêu cầu bảo đảm của ứng dụng.
8. Chỉ khi tất cả điều kiện bắt buộc đạt, client mới tạo phiên ứng dụng hoặc cho phép bước nghiệp vụ tiếp theo.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant C as OIDC Client
    participant OP as OpenID Provider
    participant U as End-User

    C->>C: Tạo state, nonce, PKCE verifier
    C->>OP: Authentication Request (nonce, max_age, acr_values)
    OP->>U: Xác thực / step-up theo policy
    U->>OP: Bằng chứng xác thực
    OP->>C: Authorization Response / ID Token
    C->>C: Xác minh chữ ký, iss, aud, exp, iat
    C->>C: So sánh nonce với transaction
    C->>C: Kiểm tra auth_time nếu có max_age
    C->>C: Đánh giá acr và amr theo policy
    C->>C: Tạo phiên nếu mọi điều kiện đạt
~~~

Sơ đồ mô tả luồng khái niệm; chi tiết response phụ thuộc Authorization Code, Implicit, Hybrid hoặc profile đang triển khai.

## 7. Yêu cầu và kiểm tra các claim qua Authentication Request

Các tham số có liên quan nhưng không đồng nghĩa:

| Request parameter | Mục đích | Kết quả cần kiểm tra |
| --- | --- | --- |
| `nonce` | Liên kết ID Token với request | Claim `nonce` trong ID Token phải khớp nếu đã gửi |
| `max_age` | Giới hạn tuổi lần xác thực | ID Token phải có `auth_time` và tuổi không vượt ngưỡng |
| `prompt=login` | Yêu cầu xác thực lại | Kiểm tra kết quả và `auth_time` thực tế |
| `acr_values` | Nêu các ACR mong muốn theo thứ tự ưu tiên | Kiểm tra `acr` được trả về |
| `claims` | Yêu cầu claim cụ thể/Essential Claim | Kiểm tra claim được trả về đúng ràng buộc |

Ví dụ Authentication Request minh họa:

~~~text
response_type=code
scope=openid profile
client_id=dashboard
redirect_uri=https://client.example.net/callback
state=<random-state>
nonce=<random-nonce>
code_challenge=<pkce-challenge>
code_challenge_method=S256
max_age=300
acr_values=urn:example:loa:2 urn:example:loa:1
~~~

Đây là ví dụ khái niệm, không chứa giá trị thật. Client phải gửi request theo quy tắc URL/form encoding của giao thức và dùng giá trị ngẫu nhiên độc lập cho state, nonce và PKCE verifier.

Nếu cần yêu cầu `acr` hoặc `amr` cụ thể trong ID Token, có thể dùng `claims` theo OIDC. Với `auth_time`, `max_age` là cơ chế request quan trọng để yêu cầu giới hạn tuổi xác thực. Không yêu cầu claim mà ứng dụng không có chính sách sử dụng.

## 8. Quy trình xác minh ID Token và ra quyết định

Không kiểm tra bốn giá trị này trước khi xác minh token.

### 8.1. Xác minh nền tảng ID Token

- Kiểm tra JWS/JWE theo profile và thuật toán được phép.
- Xác minh chữ ký bằng khóa gắn với OP/issuer tin cậy.
- Kiểm tra `iss` chính xác.
- Kiểm tra `aud` chứa Client ID dự kiến.
- Kiểm tra `azp` khi quy tắc OIDC yêu cầu hoặc có nhiều audience.
- Kiểm tra `exp`, `iat` và các claim thời gian theo chính sách.
- Kiểm tra các ràng buộc của flow như `c_hash` hoặc `at_hash` khi áp dụng.
- Chỉ sau đó mới sử dụng claim để đánh giá phiên.

### 8.2. Kiểm tra nonce

- Nếu Authentication Request đã gửi nonce, claim phải có và khớp chính xác.
- Nonce phải thuộc đúng transaction đang chờ.
- Transaction phải còn hiệu lực và nonce chưa bị tiêu thụ.
- Từ chối ID Token có nonce thiếu, khác hoặc được dùng lại trái quy tắc.

### 8.3. Kiểm tra tuổi xác thực

- Nếu đã gửi `max_age`, `auth_time` phải hiện diện.
- Tính tuổi xác thực từ thời gian hiện tại trừ `auth_time`.
- Kiểm tra không nằm trong tương lai ngoài clock skew.
- Từ chối nếu tuổi xác thực vượt `max_age` cộng leeway nhỏ theo policy.
- Không thay `auth_time` bằng `iat`.

### 8.4. Kiểm tra assurance và phương thức

- Nếu policy yêu cầu ACR, claim `acr` phải có và thuộc tập giá trị được tin cậy.
- Nếu yêu cầu AMR cụ thể, kiểm tra mảng `amr` theo allowlist và ngữ nghĩa issuer đã công bố.
- Không tự xếp hạng ACR hoặc AMR không được định nghĩa.
- Nếu claim bắt buộc thiếu hoặc giá trị không biết, từ chối hoặc yêu cầu xác thực lại/step-up theo policy.
- Không biến claim xác thực thành quyền truy cập API; authorization vẫn là bước riêng.

## 9. Ví dụ thực tế

### 9.1. Đăng nhập thông thường và chống replay ID Token

Client tạo nonce ngẫu nhiên và gửi trong Authentication Request. OP xác thực người dùng, phát hành ID Token chứa nonce tương ứng. Client xác minh chữ ký và đối chiếu nonce với transaction đang chờ. Nếu kẻ tấn công phát lại ID Token từ một giao dịch trước, nonce không khớp với transaction hiện tại nên response bị từ chối.

### 9.2. Yêu cầu xác thực gần đây cho thao tác nhạy cảm

Một ứng dụng quản lý tài khoản yêu cầu người dùng xác nhận thay đổi phương thức thanh toán. Client gửi `max_age=180`. Nếu OP chỉ dùng phiên SSO đã xác thực từ 30 phút trước, OP phải thực hiện xác thực lại phù hợp hoặc không thể đáp ứng yêu cầu. Client kiểm tra `auth_time` trong ID Token; `iat` mới không đủ để chứng minh người dùng vừa xác thực.

### 9.3. Yêu cầu mức assurance cụ thể

Ứng dụng cần một mức xác thực đã được tổ chức phê duyệt trước khi cho phép thay đổi thông tin khôi phục. Client gửi `acr_values` hoặc yêu cầu `acr` là Essential Claim với các giá trị được chấp nhận. Sau khi nhận ID Token, client kiểm tra `acr` theo bảng ánh xạ của OP. Nếu OP trả ACR không đáp ứng, ứng dụng yêu cầu step-up hoặc từ chối thao tác.

### 9.4. Đánh giá phương thức xác thực

ID Token có `amr` là `["pwd", "sms"]`. Ứng dụng không nên tự kết luận đây là mức assurance cao chỉ vì có hai phần tử. Policy phải biết SMS được đánh giá thế nào, phương thức có độc lập không, issuer có được tin cậy không và thao tác có yêu cầu phương thức chống phishing hay không.

### 9.5. Phiên SSO cũ nhưng token mới

Người dùng xác thực lúc 08:00. Lúc 08:45, một client khác yêu cầu ID Token qua SSO mà không yêu cầu xác thực mới. Token được phát hành lúc 08:45 có `iat` mới nhưng `auth_time` vẫn là 08:00. Nếu client yêu cầu `max_age=600` (10 phút), token không đáp ứng điều kiện và không được dùng để hoàn tất thao tác nhạy cảm.

## 10. Mã giả kiểm tra bốn giá trị

~~~text
function validateOidcAuthenticationContext(
    verifiedIdToken,
    authTransaction,
    clientPolicy,
    currentTime
):
    claims = verifiedIdToken.claims

    require verifiedIdToken.signatureValid
    require claims.iss == clientPolicy.trustedIssuer
    require clientPolicy.clientId in claims.aud
    require claims.exp > currentTime - clientPolicy.clockSkew

    if authTransaction.nonce was sent:
        require claims.nonce exists
        require exactStringMatch(
            claims.nonce,
            authTransaction.expectedNonce
        )
        require authTransaction.isPending
        consumeNonce(authTransaction)

    if authTransaction.maxAge was sent:
        require claims.auth_time exists
        require isValidNumericDate(claims.auth_time)
        require claims.auth_time <= currentTime + clientPolicy.clockSkew

        authenticationAge = currentTime - claims.auth_time
        require authenticationAge <= (
            authTransaction.maxAge + clientPolicy.clockSkew
        )

    if clientPolicy.requiredAcr exists:
        require claims.acr exists
        require claims.acr in clientPolicy.acceptedAcrValues

    if clientPolicy.requiredAmr exists:
        require claims.amr exists
        require claims.amr is an array of strings
        require clientPolicy.requiredAmr is satisfied by trustedAmrPolicy(
            issuer = claims.iss,
            returnedAmr = claims.amr
        )

    return AUTHENTICATION_CONTEXT_ACCEPTED
~~~

Mã giả minh họa cách tổ chức policy. Việc xác minh ID Token phải thực hiện đầy đủ theo OIDC Core và flow cụ thể trước khi gọi hàm này. So sánh nonce cần khớp chính xác và gắn với transaction đang chờ; không bỏ qua việc kiểm tra trạng thái hoặc thời hạn của transaction.

## 11. Lỗi thường gặp và cách phòng tránh

| Lỗi | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Không gửi nonce khi flow/profile yêu cầu | Thiếu liên kết request–ID Token | Tạo nonce và tuân thủ yêu cầu flow |
| Gửi nonce nhưng không kiểm tra claim trả về | ID Token replay hoặc response nhầm transaction | So sánh chính xác và tiêu thụ nonce |
| Dùng state thay nonce | Nhầm mục tiêu CSRF với ID Token replay binding | Dùng state và nonce độc lập |
| Dùng nonce cố định hoặc tái sử dụng | Kẻ tấn công có thể replay token trong nhiều transaction | Sinh nonce mới cho từng request |
| Coi `iat` là thời điểm xác thực | Phiên SSO cũ bị hiểu thành đăng nhập mới | Dùng `auth_time` |
| Gửi `max_age` nhưng bỏ qua `auth_time` | Không thực thi yêu cầu xác thực gần đây | Từ chối nếu claim thiếu hoặc quá cũ |
| Tự đặt `auth_time` bằng thời điểm nhận token | Giả mạo tuổi xác thực | Chỉ tin giá trị từ ID Token đã xác minh |
| Coi ACR là role hoặc scope | Nhầm assurance với authorization | Tách authentication context và quyền |
| Xếp hạng ACR bằng cách đọc số trong chuỗi | Tin sai giá trị không có hợp đồng | Dùng mapping do issuer/client thỏa thuận |
| Coi hai AMR entries luôn là MFA mạnh | Đánh giá sai tính độc lập và chất lượng yếu tố | Áp dụng policy AMR/ACR rõ ràng |
| Coi thiếu AMR là đã xác thực một yếu tố | Suy luận không có bằng chứng | Xử lý claim thiếu theo policy |
| Tin claim trước khi xác minh chữ ký/issuer | Dữ liệu giả mạo có thể ảnh hưởng quyết định | Xác minh toàn bộ ID Token trước |

## 12. Quyền riêng tư và lưu trữ

Các claim về thời điểm và phương thức xác thực có thể tiết lộ hành vi người dùng, thiết bị hoặc mức bảo đảm bảo mật. Client và OP cần:

- chỉ yêu cầu `auth_time`, `acr`, `amr` khi ứng dụng có nhu cầu;
- không đưa dữ liệu xác thực chi tiết hơn cần thiết vào ID Token;
- không log toàn bộ ID Token hoặc nonce nguyên vẹn;
- giới hạn thời gian lưu transaction chứa nonce;
- bảo vệ kho session/transaction và ràng buộc nonce với đúng browser/session;
- giới hạn quyền đọc audit và dữ liệu xác thực;
- không chia sẻ AMR/ACR cho bên không cần biết;
- tuân thủ chính sách lưu trữ và quyền riêng tư áp dụng.

Nonce là dữ liệu liên kết giao dịch; auth_time/ACR/AMR là dữ liệu ngữ cảnh xác thực. Không dùng chúng làm telemetry công khai hoặc nhãn metric có cardinality cao.

## 13. Checklist triển khai

**Nonce:**

- [ ] Tạo nonce bằng CSPRNG, mới cho mỗi Authentication Request.
- [ ] Lưu nonce gắn với transaction/session và có thời hạn.
- [ ] Gửi nonce trong request khi flow/profile yêu cầu hoặc policy chọn dùng.
- [ ] Nếu đã gửi nonce, xác minh ID Token phải có nonce và khớp chính xác.
- [ ] Tiêu thụ nonce sau khi xác minh; không tái sử dụng.
- [ ] Phân biệt nonce với state và PKCE.

**Authentication time:**

- [ ] Phân biệt `auth_time` với `iat` và `exp`.
- [ ] Nếu gửi `max_age`, yêu cầu và kiểm tra `auth_time`.
- [ ] Kiểm tra NumericDate, tương lai và tuổi xác thực với clock skew nhỏ.
- [ ] Không giả lập xác thực mới bằng cách phát hành ID Token mới.
- [ ] Dùng `prompt=login`/step-up đúng mục đích.

**Assurance và methods:**

- [ ] Có mapping ACR theo issuer và policy được thỏa thuận.
- [ ] Kiểm tra ACR thực tế, không chỉ dựa vào giá trị request.
- [ ] Hiểu ngữ nghĩa AMR của issuer và identifier được sử dụng.
- [ ] Không suy luận MFA hoặc assurance chỉ bằng cách đếm AMR.
- [ ] Không dùng ACR/AMR thay cho authorization.

**ID Token và vận hành:**

- [ ] Xác minh chữ ký, issuer, audience, thời gian và flow trước khi tin claim.
- [ ] Kiểm tra `azp`, `c_hash`, `at_hash` khi quy tắc OIDC yêu cầu.
- [ ] Từ chối claim bắt buộc thiếu hoặc không đáp ứng policy.
- [ ] Không log token/nonce nguyên vẹn; bảo vệ dữ liệu xác thực.
- [ ] Có test replay, stale authentication, ACR không đạt và AMR thiếu/sai.

## 14. Tài liệu tham khảo

- [OpenID Connect Core 1.0 — Authentication Request](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest): tham số nonce, max_age, prompt, acr_values và claims.
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken): ngữ nghĩa ID Token và các claim auth_time, nonce, acr.
- [OpenID Connect Core 1.0 — Claim Requests](https://openid.net/specs/openid-connect-core-1_0.html#ClaimsParameter): yêu cầu Essential Claim và giá trị claim.
- [RFC 8176 — Authentication Method Reference Values](https://www.rfc-editor.org/rfc/rfc8176): các giá trị AMR tiêu chuẩn.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): nền tảng Authorization Code Flow và các vai trò OAuth.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): PKCE và cách ràng buộc authorization code với client.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): các thực hành bảo vệ OAuth 2.0 hiện hành.

**Ghi nhớ:** `nonce` ràng buộc ID Token với Authentication Request; `auth_time` cho biết lần xác thực thực sự xảy ra khi nào; `acr` mô tả lớp ngữ cảnh xác thực đã thỏa mãn; `amr` mô tả phương thức đã sử dụng. Hãy xác minh chữ ký và issuer trước, sau đó mới kiểm tra từng giá trị theo yêu cầu flow và policy. Đừng dùng thời điểm phát hành thay thời điểm xác thực, đừng nhầm assurance với quyền truy cập và đừng coi state/PKCE là bản thay thế của nonce.

