# Token expiration: kiểm soát thời hạn token và phiên đăng nhập

Token expiration giới hạn khoảng thời gian một credential được phép sử dụng để truy cập tài nguyên. Trong ứng dụng web, access token thường có thời hạn ngắn; refresh token có thể được dùng để xin access token mới; còn phiên đăng nhập của ứng dụng hoặc identity provider có thể có thời hạn idle và absolute riêng.

Các mốc này liên quan với nhau nhưng không đồng nhất. Access token hết hạn không nhất thiết buộc người dùng đăng nhập lại nếu refresh token và phiên đăng nhập còn hợp lệ. Ngược lại, cookie vẫn nằm trong trình duyệt cũng không có nghĩa token hoặc session phía server còn được chấp nhận.

Thiết kế an toàn cần xác định rõ ai kiểm tra thời hạn, loại token nào được gia hạn, cách thu hồi credential, cách xử lý nhiều request cùng hết hạn và cách thông báo cho người dùng. Đồng hồ trên máy khách chỉ phục vụ giao diện; server mới là nơi quyết định token còn hợp lệ hay không.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt thời hạn access token, refresh token, cookie và phiên đăng nhập.
- Giải thích các claim `exp`, `iat`, `nbf` trong JWT.
- Phân biệt JWT có thể xác minh cục bộ với opaque token cần tra cứu phía server.
- Xác minh chữ ký, issuer, audience và thời hạn trước khi chấp nhận JWT.
- Hiểu clock skew và cách áp dụng leeway có giới hạn.
- Thiết kế access token ngắn hạn và refresh token có rotation.
- Nhận diện refresh token reuse và xử lý token family bị lộ.
- Phân biệt expiration với revocation và logout.
- Lựa chọn browser storage/cookie phù hợp với threat model.
- Xử lý đồng thời nhiều request hoặc nhiều tab cùng cần refresh.
- Thiết kế idle timeout, absolute timeout và yêu cầu xác thực lại.
- Kiểm thử các trường hợp token hết hạn, bị thu hồi, sai audience và refresh thất bại.

## 1. Token expiration giải quyết vấn đề nào?

Access token là credential mà client gửi đến API để chứng minh quyền truy cập. Nếu token bị đánh cắp, kẻ tấn công có thể sử dụng token trong thời gian token còn hiệu lực, trừ khi server có cơ chế thu hồi hoặc kiểm tra bổ sung.

Giới hạn thời hạn giúp giảm khoảng thời gian một token bị lộ còn có thể sử dụng. Tuy nhiên, thời hạn ngắn hơn làm tăng số lần refresh và yêu cầu xử lý tốt hơn khi mạng gián đoạn hoặc nhiều request cùng hết hạn.

Luồng cơ bản:

~~~text
Người dùng đăng nhập
       |
       v
Authorization server cấp access token
và có thể cấp refresh token
       |
       v
Client gọi API bằng access token
       |
       v
Access token hết hạn
       |
       v
Client gửi refresh request
       |
       +---- Refresh hợp lệ -> access token mới
       |
       +---- Refresh hết hạn/thu hồi -> yêu cầu đăng nhập lại
~~~

Token expiration không phải một bộ đếm chỉ chạy ở giao diện. Client có thể dự đoán thời điểm để tránh request thất bại, nhưng server phải kiểm tra token tại mỗi request được bảo vệ.

### 1.1 Vì sao không dùng access token vô thời hạn?

Token dài hạn làm tăng rủi ro khi:

- Token bị lộ qua XSS, log, extension hoặc thiết bị bị xâm nhập.
- Người dùng đăng xuất nhưng token vẫn được chấp nhận.
- Quyền của user hoặc tenant thay đổi.
- Session bị thu hồi hoặc phát hiện hoạt động bất thường.
- Một credential cũ bị sao chép sang thiết bị khác.

Thời hạn ngắn giới hạn thời gian sử dụng token bị lộ, nhưng không thay thế bảo mật storage, XSS prevention, revocation hoặc authorization.

### 1.2 Không có một con số lifetime phù hợp cho mọi ứng dụng

Thời hạn phụ thuộc vào:

- Mức độ nhạy cảm của dữ liệu.
- Loại client và khả năng bảo vệ credential.
- Có refresh token hay không.
- Có introspection hoặc revocation nhanh không.
- Yêu cầu UX và khả năng kết nối.
- Mức độ rủi ro khi token bị đánh cắp.
- Yêu cầu tuân thủ và chính sách tổ chức.

Không mặc định mọi access token phải sống đúng 5, 15 hoặc 60 phút. Hãy đặt lifetime dựa trên threat model, sau đó kiểm thử refresh, logout và thu hồi.

## 2. Các loại thời hạn cần phân biệt

| Thành phần | Điều gì hết hạn? | Ai kiểm tra? |
|---|---|---|
| Access token | Quyền dùng token để gọi API | Resource server/API |
| Refresh token | Quyền xin access token mới | Authorization server |
| Session cookie | Cookie được trình duyệt gửi | Browser và server session |
| Server session | Phiên đăng nhập phía server | Application/identity server |
| ID token | Assertion về lần xác thực người dùng | OIDC client theo mục đích của ID token |
| Authorization code | Mã đổi token, thường chỉ dùng một lần và có thời hạn ngắn | Authorization server |

Không dùng ID token làm access token chỉ vì nó có chữ ký và có claim `exp`. Hai loại token có audience và mục đích khác nhau.

### 2.1 Access token expiration

Khi access token hết hạn, resource server phải từ chối request được xác thực bằng token đó. Với OAuth Bearer token, API có thể trả HTTP 401 và thông tin `WWW-Authenticate` tương ứng, ví dụ lỗi `invalid_token`.

Client có thể thử refresh nếu còn refresh credential hợp lệ. Nếu refresh không thành công, người dùng cần đăng nhập lại hoặc thực hiện quy trình xác thực bổ sung.

### 2.2 Refresh token expiration

Refresh token được gửi đến authorization server để xin access token mới. Nó có thể có:

- Absolute lifetime: thời điểm hết hạn cố định tính từ lúc cấp.
- Inactivity/idle lifetime: hết hạn sau một khoảng không sử dụng.
- Rotation: mỗi lần refresh thành công cấp refresh token mới và vô hiệu hóa token cũ.
- Revocation: bị vô hiệu hóa trước thời hạn do logout, reuse detection hoặc quyết định bảo mật.

Không phải mọi hệ thống đều có đủ các cơ chế trên. Chính sách cần được định nghĩa ở authorization server.

### 2.3 Session expiration

Phiên đăng nhập có thể còn hiệu lực sau khi một access token hết hạn. Ví dụ, browser session vẫn hợp lệ và server có thể cấp token mới qua refresh endpoint.

Ngược lại, session có thể bị thu hồi trong khi access token JWT cũ chưa đến `exp`. Nếu API chỉ xác minh chữ ký và thời hạn mà không có revocation check, token cũ có thể tiếp tục được chấp nhận đến khi hết hạn.

### 2.4 Cookie expiration không phải token revocation

Cookie `Expires` hoặc `Max-Age` quyết định browser giữ và gửi cookie trong khoảng thời gian nào. Nó không tự xóa token khỏi database phía server và cũng không bảo đảm server đã thu hồi session.

Xóa cookie ở browser là cần thiết cho logout UX, nhưng server vẫn phải vô hiệu hóa session hoặc refresh token tương ứng.

## 3. Thời gian trong JWT: exp, iat và nbf

JWT có thể chứa các registered claims mô tả thời điểm token được tạo, bắt đầu có hiệu lực và hết hạn.

### 3.1 exp — expiration time

`exp` là NumericDate: số giây kể từ Unix epoch UTC. Nếu claim có mặt, token không được chấp nhận tại hoặc sau thời điểm expiration theo quy tắc JWT.

Ví dụ payload:

~~~json
{
  "iss": "https://identity.example.test/",
  "aud": "api://orders",
  "sub": "user-123",
  "iat": 1795340000,
  "nbf": 1795340000,
  "exp": 1795340900,
  "jti": "token-id-7f3a"
}
~~~

`exp` ở đây là thời điểm hết hạn, không phải số giây lifetime. `exp - iat` cho biết khoảng thời gian từ lúc phát hành đến lúc hết hạn nếu cả hai claim hợp lệ và cùng dùng NumericDate.

JWT specification không bắt buộc mọi JWT đều phải có `exp`. Nhưng ứng dụng dùng JWT làm access token nên quy định profile/token contract yêu cầu expiration và từ chối token thiếu claim đó.

### 3.2 iat — issued at

`iat` cho biết thời điểm token được phát hành. Server có thể dùng nó để:

- Kiểm tra token không được phát hành trong tương lai quá mức cho phép.
- Giới hạn tuổi tối đa của token.
- Điều tra token cũ hoặc phát hiện token được phát hành trước một mốc bảo mật.
- Hỗ trợ chính sách session hoặc credential rotation.

`iat` không tự làm token hết hạn. Nếu token có `iat` nhưng không có `exp`, server không thể suy ra lifetime nếu profile không định nghĩa rõ quy tắc đó.

### 3.3 nbf — not before

`nbf` cho biết token chưa được chấp nhận trước một thời điểm. Trước `nbf`, token chưa có hiệu lực; từ thời điểm đó trở đi, các điều kiện xác minh khác vẫn phải hợp lệ.

`nbf` hữu ích khi token được tạo trước nhưng chỉ được phép sử dụng sau một mốc thời gian. Không dùng nó thay thế `exp`.

### 3.4 jti — JWT ID

`jti` là định danh token. Nó có thể hỗ trợ:

- Denylist/revocation.
- Phát hiện token lặp trong một số giao thức.
- Correlation trong audit log nếu được xử lý an toàn.

`jti` không tự thu hồi token. Server cần lưu trạng thái hoặc dùng một cơ chế khác để biết token có bị thu hồi hay không.

## 4. Kiểm tra JWT expiration đúng cách

JWT payload thường chỉ được Base64URL encode, không được mã hóa. Người nhận có thể đọc claim mà không cần secret. Chỉ đọc payload không chứng minh token hợp lệ.

Server phải xác minh chữ ký hoặc cơ chế bảo vệ tương ứng trước khi tin claim.

### 4.1 Các bước kiểm tra

Với JWT access token, resource server thường cần:

1. Chọn key đáng tin cậy từ cấu hình hoặc JWKS đã được kiểm soát.
2. Chỉ cho phép thuật toán ký được cấu hình.
3. Xác minh chữ ký.
4. Kiểm tra `iss` khớp issuer mong đợi.
5. Kiểm tra `aud` chứa đúng resource server.
6. Yêu cầu `exp` theo token profile và kiểm tra thời hạn.
7. Kiểm tra `nbf` nếu có.
8. Kiểm tra `iat` và tuổi token theo policy.
9. Kiểm tra loại token và các claim quyền cần thiết.
10. Thực hiện authorization cho resource/action cụ thể.

Không chấp nhận thuật toán chỉ vì token tự khai báo trong header `alg`. Không dùng thuật toán `none` hoặc một key không đúng loại.

### 4.2 Ví dụ xác minh bằng thư viện jose

Ví dụ Node.js sử dụng thư viện `jose`. `publicKey` phải được lấy từ nguồn key đáng tin cậy và được quản lý theo issuer:

~~~js
import { jwtVerify } from "jose";

async function verifyAccessToken(token, publicKey) {
  const { payload, protectedHeader } = await jwtVerify(
    token,
    publicKey,
    {
      algorithms: ["RS256"],
      issuer: "https://identity.example.test/",
      audience: "api://orders",
      requiredClaims: ["exp", "iat", "iss", "aud"],
      clockTolerance: 5
    }
  );

  if (protectedHeader.typ !== "at+jwt") {
    throw new Error("Unexpected token type");
  }

  if (typeof payload.sub !== "string" || !payload.sub) {
    throw new Error("Missing subject");
  }

  return payload;
}
~~~

Ví dụ dùng profile JWT access token với `typ: at+jwt`. Nếu hệ thống dùng một token profile khác, hãy tuân theo profile đó. `clockTolerance: 5` là ví dụ leeway 5 giây, không phải con số bắt buộc cho mọi hệ thống.

Thư viện phải xác minh chữ ký, issuer, audience, thời hạn và claim bắt buộc. Không viết lại JWT verifier bằng vài phép split/Base64 decode.

### 4.3 Opaque access token

Opaque token là chuỗi không mang claim JWT có thể kiểm tra cục bộ. Resource server thường xác minh nó bằng cách:

- Gọi introspection endpoint của authorization server.
- Tra cứu token trong session/store nội bộ.
- Dùng gateway hoặc middleware có trạng thái token.

Authorization server trả trạng thái như `active` cùng metadata phù hợp. Khi token hết hạn hoặc bị thu hồi, introspection có thể phản ánh trạng thái mới tùy cache và thiết kế.

Opaque token không có `exp` để client tự đọc. Client thường nhận lifetime qua trường `expires_in` trong token response.

### 4.4 Không tin đồng hồ của browser

Browser clock có thể sai, bị người dùng chỉnh hoặc lệch múi giờ. Server phải dùng clock đồng bộ và quyết định token hợp lệ.

Client có thể dùng `expires_in` và thời điểm nhận response để chủ động refresh sớm. Đây chỉ là tối ưu UX; server vẫn là nguồn quyết định.

## 5. Clock skew và leeway

Các máy trong hệ thống có thể lệch đồng hồ vài giây. Nếu authorization server và resource server không đồng bộ, token có thể bị từ chối sớm hoặc được chấp nhận muộn ngoài dự kiến.

### 5.1 Leeway có giới hạn

Server có thể áp dụng một khoảng dung sai nhỏ cho `exp` và `nbf` để xử lý clock skew. Khoảng này cần:

- Được cấu hình tập trung.
- Nhỏ hơn nhiều so với token lifetime.
- Thống nhất giữa các API.
- Có metric để phát hiện lệch đồng hồ.
- Được kiểm thử tại ranh giới thời hạn.

Không đặt leeway vài phút hoặc vài giờ chỉ để che lỗi đồng hồ. Leeway quá lớn kéo dài thời gian token có thể được chấp nhận.

### 5.2 Dùng UTC và NumericDate

JWT NumericDate dùng giây kể từ Unix epoch. Trong JavaScript, `Date.now()` trả milliseconds.

Ví dụ:

~~~js
const nowInSeconds = Math.floor(Date.now() / 1000);
const remainingSeconds = payload.exp - nowInSeconds;

if (remainingSeconds <= 0) {
  console.log("Token đã hết hạn theo đồng hồ client");
}
~~~

Đây chỉ là dự đoán phía client. Không dùng đoạn kiểm tra này để cấp quyền truy cập hoặc thay xác minh phía server.

### 5.3 Refresh sớm có kiểm soát

Client có thể refresh trước thời điểm hết hạn một khoảng ngắn để giảm request thất bại do network latency hoặc clock skew. Không refresh liên tục mỗi lần component render.

Một cách tiếp cận là giữ `expires_at` trong memory dựa trên `expires_in`, dùng timer hoặc kiểm tra trước request, rồi refresh một lần khi cần. Khi tab bị suspend, timer có thể chạy muộn; vì vậy vẫn phải xử lý 401 từ server.

## 6. Access token lifetime và refresh token lifetime

Access token thường có lifetime ngắn hơn refresh token. Refresh token được bảo vệ chặt hơn và dùng để xin credential mới.

~~~text
Access token A
   | dùng gọi API
   | hết hạn
   v
Refresh token R1
   | gửi đến authorization server
   | hợp lệ và chưa bị dùng
   v
Access token B + Refresh token R2
   |
   | R1 bị vô hiệu hóa
   v
Tiếp tục gọi API bằng B
~~~

### 6.1 Access token

Access token nên:

- Có audience giới hạn cho resource server cần dùng.
- Chứa scope/permission tối thiểu.
- Có expiration rõ ràng.
- Không chứa dữ liệu nhạy cảm không cần thiết.
- Được truyền qua TLS.
- Không xuất hiện trong URL, log hoặc analytics.

Access token là bearer credential nếu bất kỳ ai nắm giữ nó đều có thể dùng. Vì vậy, thời hạn ngắn chỉ giảm cửa sổ rủi ro, không làm token an toàn nếu bị lưu trữ hoặc truyền sai cách.

### 6.2 Refresh token

Refresh token có quyền lực lớn hơn vì nó có thể cấp access token mới. Hãy:

- Bảo vệ nó như credential đăng nhập.
- Không lưu trong `localStorage` hoặc `sessionStorage` nếu có thể tránh.
- Không đưa vào URL query hoặc fragment.
- Dùng rotation hoặc sender-constrained refresh token cho public clients theo OAuth Security Best Current Practice.
- Giới hạn absolute lifetime và inactivity lifetime.
- Thu hồi token family khi phát hiện reuse theo policy.
- Gắn refresh token với client/session/user và phạm vi phù hợp.

### 6.3 Trường expires_in

OAuth token response thường có `expires_in`, là thời gian sống của access token tính bằng giây kể từ lúc cấp.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "REFRESH_TOKEN_VALUE"
}
~~~

`expires_in` là metadata lifetime. Nếu access token là JWT, nó cũng có thể có `exp`; client không nên giả định mọi access token đều là JWT hoặc tự suy diễn claim nếu token opaque.

Token response chứa credential nên cần `Cache-Control: no-store` và không được ghi vào cache HTTP dùng chung.

## 7. Refresh token rotation và reuse detection

Refresh token rotation thay refresh token cũ bằng một token mới sau mỗi lần sử dụng thành công.

Server có thể quản lý một token family:

~~~text
Family F
  |
  +-- R1 (đã dùng, revoked)
          |
          +-- R2 (đã dùng, revoked)
                  |
                  +-- R3 (đang hoạt động)
~~~

Nếu attacker giữ bản sao R1 và dùng lại sau khi R1 đã được xoay, server phát hiện reuse. Vì server không thể biết chắc ai đang giữ bản sao hợp lệ, policy có thể thu hồi token family để chặn attacker tiếp tục dùng descendant token.

### 7.1 Quy trình rotation

Một refresh transaction an toàn thường thực hiện:

1. Xác minh refresh token còn tồn tại và chưa hết hạn.
2. Xác minh token chưa bị revoke hoặc dùng trước đó.
3. Xác minh client/session/user và các ràng buộc liên quan.
4. Tạo access token mới.
5. Tạo refresh token mới với entropy cao.
6. Lưu trạng thái token mới và đánh dấu token cũ đã dùng trong một transaction nguyên tử.
7. Trả token mới cho client và gửi refresh cookie mới nếu dùng cookie.

Nếu hai request dùng cùng refresh token đồng thời, server phải xử lý race theo một policy rõ ràng. Hai transaction cùng thành công với hai descendant độc lập sẽ làm mất ý nghĩa rotation.

### 7.2 Reuse detection

Khi refresh token cũ đã bị dùng lại:

- Ghi nhận sự kiện bảo mật.
- Thu hồi token family hoặc session liên quan theo policy.
- Yêu cầu xác thực lại.
- Thông báo phù hợp nếu phát hiện hành vi bất thường.
- Không ghi raw refresh token vào log.

Không chỉ từ chối token cũ rồi để token descendant tiếp tục hoạt động nếu policy yêu cầu revoke family.

### 7.3 Public clients và sender-constrained tokens

Ứng dụng browser/mobile thường là public client: không thể giữ client secret lâu dài một cách đáng tin cậy.

OAuth Security Best Current Practice yêu cầu public client dùng refresh token rotation hoặc sender-constrained refresh token để phát hiện/phòng replay. DPoP là một cơ chế sender-constraining có thể ràng buộc token với key của client; mTLS thường phù hợp hơn với client có khả năng quản lý certificate.

Không nhúng client secret vào JavaScript bundle và coi đó là bí mật. Người dùng có thể tải bundle và đọc giá trị này.

## 8. Token expiration khác revocation như thế nào?

Expiration là thời điểm token tự mất hiệu lực theo policy. Revocation là hành động chủ động làm token hoặc session không còn được chấp nhận trước thời hạn.

| Cơ chế | Tác động |
|---|---|
| `exp` | Token hết hiệu lực sau thời điểm quy định |
| Refresh token rotation | Token cũ bị vô hiệu hóa khi được thay thế |
| Token revocation | Authorization server đánh dấu token không còn hợp lệ |
| Introspection | Resource server hỏi trạng thái token |
| Denylist theo `jti` | API từ chối token ID đã bị thu hồi |
| Session invalidation | Hủy phiên đăng nhập phía server |
| Signing key rotation | Thay đổi key được tin cậy; không nhất thiết thu hồi từng token ngay lập tức |

### 8.1 JWT stateless có giới hạn revocation

Nếu API chỉ xác minh chữ ký và `exp`, một JWT đã cấp có thể vẫn hợp lệ đến khi hết hạn dù user đã logout.

Các lựa chọn:

- Giữ access token lifetime ngắn để giới hạn cửa sổ còn hiệu lực.
- Dùng denylist theo `jti` đến khi token tự hết hạn.
- Dùng introspection hoặc session version check.
- Dùng opaque token có trạng thái phía server.
- Thu hồi refresh token để ngăn cấp token mới.

Mỗi lựa chọn có chi phí về latency, cache, availability và độ phức tạp. Đừng gọi một JWT là “revoked ngay lập tức” nếu API không có cơ chế kiểm tra trạng thái đó.

### 8.2 Logout cần xử lý server và browser

Một luồng logout tốt thường:

1. Gửi request logout đến server.
2. Thu hồi refresh token hoặc server session.
3. Xóa refresh cookie bằng cùng cookie name/path/domain attributes.
4. Xóa access token khỏi memory.
5. Xóa dữ liệu UI/cache nhạy cảm phù hợp.
6. Thông báo các tab khác rằng session đã kết thúc.
7. Điều hướng đến trạng thái signed-out.

Nếu access token JWT vẫn còn hiệu lực và API không kiểm tra revocation, token đó có thể còn dùng được đến `exp`. Nói rõ giới hạn này trong thiết kế session.

## 9. Idle timeout và absolute timeout

Token lifetime không phải toàn bộ session policy.

### 9.1 Idle timeout

Idle timeout kết thúc session nếu không có hoạt động hợp lệ trong một khoảng thời gian. Mục đích là giảm rủi ro khi người dùng bỏ quên thiết bị đang đăng nhập.

Cần định nghĩa hoạt động nào được tính là activity. Không để background polling hoặc request tự động kéo dài session vô hạn nếu user không thực sự tương tác.

### 9.2 Absolute timeout

Absolute timeout giới hạn tổng thời gian session kể từ lần xác thực ban đầu, bất kể có hoạt động liên tục hay không.

Ví dụ:

~~~text
Login at T0
  |
  +-- Idle timeout: kết thúc sau một khoảng không hoạt động
  |
  +-- Absolute timeout: kết thúc tại T0 + lifetime cố định
~~~

Refresh token rotation không nên tự động kéo dài absolute session vô hạn. Server cần giữ thời điểm xác thực ban đầu hoặc mốc absolute expiry độc lập.

### 9.3 Reauthentication cho hành động nhạy cảm

Một session còn hoạt động không có nghĩa mọi thao tác đều được phép mà không xác thực lại. Với hành động rủi ro cao như đổi email, đổi password, thêm phương thức MFA, tạo API key hoặc thanh toán lớn, có thể yêu cầu step-up authentication.

Dựa trên `auth_time` hoặc metadata xác thực phù hợp để xác định lần xác thực gần nhất, không chỉ dựa vào `iat` của access token vừa refresh.

## 10. Token expiration trong browser

Cách lưu token ảnh hưởng khả năng đánh cắp và refresh.

### 10.1 localStorage và sessionStorage

Token trong Web Storage có thể được đọc bởi JavaScript cùng origin. Nếu ứng dụng có XSS, mã độc có thể đọc access token hoặc refresh token và gửi ra ngoài.

`sessionStorage` giới hạn vòng đời theo tab trong nhiều trường hợp, nhưng vẫn có thể bị JavaScript cùng origin đọc. Nó không phải ranh giới chống XSS.

Không lưu refresh token dài hạn trong Web Storage chỉ để đơn giản hóa refresh.

### 10.2 Memory storage

Giữ access token trong memory giúp giảm persistence sau reload và tránh token tự động được ghi vào disk qua Web Storage. Nhưng XSS đang chạy trong trang vẫn có thể đọc hoặc sử dụng token khi nó còn trong memory.

Memory storage là một biện pháp giảm bề mặt lưu trữ, không phải bảo vệ tuyệt đối.

### 10.3 HttpOnly cookie

Cookie có thể đặt các thuộc tính:

~~~http
Set-Cookie: __Host-refresh=RANDOM_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1209600
~~~

Ý nghĩa:

- `Secure`: chỉ gửi qua secure transport.
- `HttpOnly`: JavaScript không đọc được cookie.
- `SameSite=Lax`: giảm gửi cookie trong một số ngữ cảnh cross-site.
- `Path=/`: cookie áp dụng cho host path root.
- `__Host-`: yêu cầu Secure, Path=/ và không có Domain attribute.

HttpOnly cookie giúp giảm nguy cơ đánh cắp trực tiếp token qua JavaScript, nhưng XSS vẫn có thể thực hiện request cùng origin khiến browser tự gửi cookie. Vì vậy vẫn cần CSP, output encoding, Trusted Types và các biện pháp chống XSS.

### 10.4 Cookie tự động gửi nên cần CSRF protection

Cookie authentication có rủi ro CSRF vì browser tự gắn cookie vào request phù hợp.

Với refresh/logout endpoint dùng cookie, cần thiết kế:

- SameSite phù hợp.
- CSRF token hoặc cơ chế anti-CSRF tương đương.
- Kiểm tra Origin/Referer theo policy server.
- Chỉ nhận method và content type dự kiến.
- Không thay đổi trạng thái bằng GET.
- Không cho phép CORS credentials rộng tùy tiện.

HttpOnly không chống CSRF. SameSite là một lớp bảo vệ, nhưng site và origin là hai khái niệm khác nhau.

### 10.5 Backend for Frontend (BFF)

BFF giữ OAuth access/refresh token ở server. Browser chỉ giữ một session cookie an toàn trỏ đến BFF.

~~~text
Browser
  |
  | HttpOnly session cookie
  v
BFF / application server
  |
  | Access token + refresh token
  v
Authorization server / API
~~~

Ưu điểm:

- OAuth token không cần xuất hiện trong JavaScript.
- Refresh token được bảo vệ trong server-side storage.
- BFF có thể quản lý rotation, revocation và session timeout.
- Browser có mô hình cookie session quen thuộc.

BFF vẫn cần CSRF protection, session fixation prevention, authorization và bảo vệ server-side token store.

## 11. Cookie expiry và server token expiry phải đồng bộ

Cookie `Max-Age` chỉ kiểm soát thời gian browser giữ cookie. Server phải kiểm tra refresh token hoặc session expiry độc lập.

Ví dụ:

~~~http
Set-Cookie: __Host-refresh=...; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=604800
~~~

Cookie có thể bị browser xóa sau bảy ngày. Nhưng nếu server đã revoke refresh token sau một ngày, cookie còn tồn tại cũng không giúp refresh thành công.

Ngược lại, nếu cookie hết hạn trước refresh token, browser không còn gửi credential đó dù server-side record vẫn còn. Đây có thể là hành vi mong muốn để giới hạn thời gian lưu credential trên thiết bị.

### 11.1 Xóa cookie phải dùng đúng scope

Khi xóa cookie, response cần dùng cùng tên và phạm vi Path/Domain tương ứng để browser xóa đúng cookie. Cookie có prefix `__Host-` không được có Domain và phải dùng Path=/.

Ví dụ:

~~~http
Set-Cookie: __Host-refresh=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0
~~~

Việc xóa cookie phía browser cần đi kèm server revocation. Đừng chỉ đặt cookie rỗng rồi coi session đã bị thu hồi.

## 12. Xử lý refresh trong ứng dụng browser

Một access token hết hạn có thể làm nhiều request cùng lúc nhận 401. Nếu mỗi request tự refresh, nhiều refresh token rotation có thể chạy song song và tạo reuse detection ngoài ý muốn.

### 12.1 Single-flight trong một tab

Client có thể chia sẻ một Promise refresh giữa các request trong cùng tab:

~~~js
let refreshPromise = null;

async function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = fetch("/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "X-CSRF-Token": readCsrfToken()
      }
    })
      .then(async response => {
        if (!response.ok) {
          throw new Error("Refresh failed: " + response.status);
        }

        const body = await response.json();
        return body.access_token;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
}
~~~

`readCsrfToken()` là hàm ứng dụng lấy anti-CSRF token theo thiết kế. Ví dụ giả định refresh cookie là HttpOnly và browser tự gửi cookie cùng origin.

Access token mới chỉ nên giữ trong memory theo policy của ứng dụng. Không gửi refresh token qua JavaScript.

### 12.2 Chỉ retry request một lần

Sau khi API trả 401 vì access token hết hạn, client có thể refresh rồi thử lại request một lần. Nếu request vẫn thất bại, dừng và xử lý lỗi. Không tạo vòng lặp refresh vô hạn.

Không refresh tự động với mọi 401 nếu response là lỗi credential khác hoặc session đã bị revoke. Không refresh chỉ vì 403; 403 thường có nghĩa đã xác thực nhưng không đủ quyền.

Với request có body stream hoặc thao tác không idempotent, cần bảo đảm request có thể được replay an toàn. Dùng idempotency key cho các thao tác tạo giao dịch hoặc thay đổi trạng thái quan trọng.

### 12.3 Nhiều tab cùng refresh

Single-flight chỉ giải quyết concurrency trong một JavaScript context. Hai tab có thể cùng dùng một refresh cookie.

Có thể dùng Web Locks API để serialize refresh trong cùng origin nếu trình duyệt hỗ trợ, hoặc thiết kế cơ chế điều phối khác. `BroadcastChannel` có thể thông báo rằng session đã được cập nhật hoặc đã logout; không broadcast access token hay refresh token qua channel.

Server vẫn phải xử lý race an toàn vì tab có thể bị suspend, lock có thể không được hỗ trợ hoặc request có thể đến trùng do retry mạng.

### 12.4 Không broadcast token giữa các tab

Không gửi token qua:

- `BroadcastChannel`.
- `localStorage` events.
- URL query/fragment.
- `postMessage` đến window không được xác thực.
- Analytics hoặc error tracking.

Nếu các tab cần biết session thay đổi, chỉ gửi tín hiệu không chứa credential như `session-updated` hoặc `signed-out`. Tab nhận tín hiệu tự gọi API phù hợp để lấy trạng thái.

## 13. Phản hồi API khi token hết hạn

Với Bearer token, API thường dùng HTTP 401 cho request không có credential hợp lệ. Header `WWW-Authenticate` có thể mô tả lỗi.

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
Content-Type: application/json

{
  "error": "invalid_token"
}
~~~

### 13.1 401 và 403

| Status | Ý nghĩa thường gặp | Hành động client |
|---|---|---|
| 401 | Thiếu hoặc credential không hợp lệ/hết hạn | Kiểm tra loại lỗi; refresh một lần nếu đủ điều kiện |
| 403 | Đã xác thực nhưng không được phép | Hiển thị lỗi quyền; không tự refresh vô hạn |
| 429 | Bị giới hạn tần suất | Tôn trọng Retry-After |
| 5xx | Lỗi server | Retry theo policy riêng, không coi là token expiry |

API có thể dùng status/body cụ thể theo contract. Client không nên đoán mọi 401 đều là access token hết hạn.

### 13.2 Không cache token response

Token endpoint và refresh endpoint nên trả `Cache-Control: no-store`. Không để service worker cache token response hoặc API response chứa credential.

Nếu ứng dụng dùng service worker, cấu hình fetch handler để bỏ qua cache cho auth/token endpoints và không đưa response chứa token vào Cache Storage.

## 14. Logout, thu hồi và thay đổi quyền

### 14.1 Logout ở một thiết bị

Server thu hồi refresh token/session tương ứng. Access token còn hiệu lực có thể vẫn được chấp nhận nếu API không có revocation check, vì vậy lifetime ngắn giúp giới hạn thời gian còn lại.

### 14.2 Logout tất cả thiết bị

Có thể thu hồi mọi refresh token family hoặc session của user. Nếu access token JWT vẫn được kiểm tra stateless, cần thêm cơ chế như session version, `jti` denylist hoặc introspection để có hiệu lực ngay.

### 14.3 Đổi mật khẩu hoặc phát hiện xâm nhập

Các sự kiện như đổi password, reset MFA, phát hiện refresh token reuse hoặc account compromise có thể yêu cầu revoke các session khác.

Chính sách phải xác định rõ token nào bị thu hồi, thời điểm có hiệu lực và cách API nhận biết. Đừng chỉ đổi password rồi giả định mọi access token cũ tự mất hiệu lực.

### 14.4 Thay signing key

Key rotation là hoạt động vận hành quan trọng, nhưng không phải cách thu hồi từng token. Nếu resource server vẫn tin public key cũ, JWT ký bằng key đó có thể còn hợp lệ cho đến `exp`.

Khi key bị compromise, cần quy trình khẩn cấp để loại key khỏi trust set, refresh JWKS/cache, revoke session/refresh token liên quan và theo dõi request bất thường.

## 15. Các lỗi triển khai thường gặp

### 15.1 Chỉ decode JWT rồi tin exp

Payload có thể bị sửa nếu chưa xác minh chữ ký. Hãy dùng thư viện JWT chuẩn và xác minh toàn bộ token profile.

### 15.2 Không yêu cầu exp

Một JWT có thể hợp lệ về chữ ký nhưng thiếu expiration nếu profile cho phép. Access token contract nên yêu cầu `exp` và server phải từ chối token thiếu claim.

### 15.3 Dùng clock của browser để cấp quyền

Người dùng có thể chỉnh đồng hồ. Server phải là nơi quyết định expiration.

### 15.4 Leeway quá lớn

Dung sai lớn kéo dài hiệu lực token. Đồng bộ clock thay vì tăng leeway vô hạn.

### 15.5 Lưu refresh token trong localStorage

XSS có thể đọc và lấy refresh token dài hạn. Ưu tiên BFF hoặc HttpOnly cookie theo thiết kế CSRF an toàn.

### 15.6 Chỉ xóa token phía client khi logout

JWT có thể còn được API chấp nhận. Thu hồi server-side refresh/session và hiểu rõ thời gian còn hiệu lực của access token.

### 15.7 Refresh token không rotation hoặc không ràng buộc

Refresh token dài hạn bị đánh cắp có thể dùng để duy trì quyền truy cập. Dùng rotation hoặc sender-constrained token cho public clients.

### 15.8 Nhiều request refresh cùng lúc

Rotation có thể xem refresh token dùng lại là dấu hiệu compromise. Dùng single-flight, điều phối tab và transaction nguyên tử phía server.

### 15.9 Refresh mọi lỗi 401/403

Không refresh khi thiếu quyền hoặc lỗi credential khác. Phân loại response theo API contract.

### 15.10 Cookie hết hạn nhưng server không revoke

Cookie expiry không phải server-side revocation. Cần xóa cookie và thu hồi session/token.

### 15.11 Không có absolute timeout

Refresh liên tục có thể kéo dài session mãi. Giữ mốc xác thực ban đầu và áp dụng absolute lifetime độc lập.

### 15.12 Token xuất hiện trong log

Không log Authorization header, refresh token, cookie hoặc token response. Redact trước khi gửi telemetry.

## 16. Quy trình thiết kế Token expiration

Khi thiết kế hệ thống:

1. Liệt kê loại credential: access token, refresh token, session cookie, ID token.
2. Chọn opaque hay JWT theo nhu cầu kiểm tra và revocation.
3. Định nghĩa lifetime và required claims cho từng loại.
4. Xác định idle timeout và absolute timeout của session.
5. Chọn refresh rotation hoặc sender-constrained token cho public client.
6. Thiết kế reuse detection và token family revocation.
7. Xác định cách logout, password change và account compromise thu hồi token.
8. Chọn storage browser theo threat model: BFF, HttpOnly cookie hoặc memory.
9. Bảo vệ cookie bằng Secure, HttpOnly, SameSite và scope phù hợp.
10. Bảo vệ refresh endpoint khỏi CSRF.
11. Xử lý concurrent refresh trong tab, giữa các tab và phía server.
12. Quy định response 401/403 và retry behavior.
13. Không cache hoặc log token response.
14. Kiểm thử clock skew, expiration boundary, refresh reuse và logout.
15. Theo dõi metric refresh failure, reuse detection và session expiry mà không ghi credential.

## 17. Bài thực hành

Thực hiện trên authorization server và API lab do bạn kiểm soát. Dùng token giả lập; không đưa token thật vào log hoặc tài liệu.

### Bài 1: Kiểm tra JWT exp

Tạo JWT lab có `iat`, `nbf` và `exp`. Gọi API trước và sau thời điểm hết hạn. Xác nhận server chấp nhận trước `exp` và từ chối tại/sau `exp`.

### Bài 2: Kiểm tra claim thiếu hoặc sai

Tạo token thiếu `exp`, sai `iss`, sai `aud`, `nbf` trong tương lai và chữ ký không hợp lệ. Xác nhận verifier từ chối từng trường hợp.

### Bài 3: Mô phỏng clock skew

Cấu hình test clock của verifier lệch vài giây. So sánh kết quả khi không có leeway và khi có leeway nhỏ. Xác nhận leeway không kéo dài token quá mức policy.

### Bài 4: Access token hết hạn, refresh còn hiệu lực

Cấp access token lifetime ngắn và refresh token còn hợp lệ. Xác nhận client refresh một lần, nhận access token mới và retry request ban đầu an toàn.

### Bài 5: Refresh token rotation

Dùng R1 để lấy R2. Thử dùng lại R1. Xác nhận server phát hiện reuse và áp dụng policy revoke token family.

### Bài 6: Hai request refresh đồng thời

Gửi hai refresh request cùng lúc từ một tab hoặc hai tab. Xác nhận client điều phối request và server cập nhật token family nguyên tử, không tạo hai descendant token hoạt động ngoài policy.

### Bài 7: Cookie và CSRF

Kiểm tra cookie có Secure, HttpOnly, SameSite và scope phù hợp. Thử refresh từ cross-site request và xác nhận anti-CSRF policy từ chối.

### Bài 8: Logout và revocation

Logout một session, thử refresh lại và gọi API bằng access token cũ. Ghi nhận khác biệt giữa refresh revocation và access token JWT còn hiệu lực.

### Bài 9: Idle và absolute timeout

Giữ một session hoạt động liên tục để kiểm tra idle timeout không bị background polling kéo dài ngoài policy. Xác nhận absolute timeout vẫn kết thúc session.

### Bài 10: Nhiều tab và trạng thái UI

Mở hai tab cùng session. Refresh ở một tab, logout ở tab còn lại. Xác nhận tab kia nhận tín hiệu session state mà không trao đổi token qua BroadcastChannel.

## 18. Checklist review Token expiration

- [ ] Mỗi loại token có lifetime và mục đích riêng.
- [ ] Access token có expiration theo token profile.
- [ ] JWT verifier kiểm tra chữ ký và thuật toán được phép.
- [ ] Kiểm tra issuer, audience, exp, nbf, iat và token type.
- [ ] Không tin JWT chỉ vì payload decode được.
- [ ] Clock skew được đo và leeway nhỏ, có giới hạn.
- [ ] Opaque token được introspect/tra cứu theo thiết kế.
- [ ] Refresh token có absolute và inactivity policy phù hợp.
- [ ] Public client dùng refresh rotation hoặc sender-constrained token.
- [ ] Refresh rotation cập nhật token family nguyên tử.
- [ ] Có reuse detection và xử lý token family.
- [ ] Access/refresh token không nằm trong URL hoặc log.
- [ ] Refresh token không được lưu trong Web Storage nếu có thể tránh.
- [ ] Cookie có Secure, HttpOnly, SameSite và scope phù hợp.
- [ ] Refresh/logout endpoint có CSRF protection.
- [ ] Cookie expiry không bị nhầm với server revocation.
- [ ] Logout thu hồi session/refresh token phía server.
- [ ] Đã hiểu access JWT cũ có thể còn hiệu lực đến exp nếu không có revocation check.
- [ ] Có idle timeout và absolute timeout độc lập.
- [ ] Client chỉ refresh một lần cho lỗi hết hạn phù hợp.
- [ ] Không tự refresh vô hạn với 401/403.
- [ ] Concurrent refresh được xử lý trong tab, giữa tab và server.
- [ ] Không broadcast token qua BroadcastChannel.
- [ ] Token endpoint response dùng Cache-Control: no-store.
- [ ] Đã kiểm thử expiry boundary, clock skew, reuse, logout và multi-tab.

## 19. Câu hỏi tự kiểm tra

**1. Access token expiration có bắt buộc người dùng đăng nhập lại ngay không?**

Không. Nếu refresh token và session còn hợp lệ, client có thể xin access token mới mà không yêu cầu người dùng nhập credential lại.

**2. `exp` trong JWT là gì?**

NumericDate biểu thị thời điểm token hết hạn. Token không được chấp nhận tại hoặc sau thời điểm đó, có thể áp dụng leeway nhỏ theo policy.

**3. `iat` có tự làm token hết hạn không?**

Không. `iat` là thời điểm phát hành; server có thể dùng nó để giới hạn tuổi token theo policy riêng.

**4. `nbf` có nghĩa gì?**

Token chưa được chấp nhận trước thời điểm `nbf`. Sau thời điểm đó, các kiểm tra khác vẫn phải hợp lệ.

**5. Vì sao không thể chỉ decode JWT để kiểm tra exp?**

Payload không được bảo vệ bởi việc decode. Server phải xác minh chữ ký, issuer, audience và các claim trước khi tin nội dung.

**6. Opaque token được kiểm tra expiration như thế nào?**

Server tra cứu trạng thái hoặc gọi introspection endpoint; client thường nhận lifetime qua `expires_in`.

**7. Refresh token rotation giúp gì?**

Mỗi lần refresh cấp token mới và vô hiệu hóa token cũ, giúp phát hiện token cũ bị sử dụng lại.

**8. Vì sao cần idle timeout và absolute timeout?**

Idle timeout kết thúc session khi không hoạt động; absolute timeout giới hạn tổng thời gian session dù người dùng hoạt động liên tục.

**9. HttpOnly cookie có ngăn CSRF không?**

Không. HttpOnly ngăn JavaScript đọc cookie, nhưng browser vẫn tự gửi cookie; cần SameSite và anti-CSRF controls.

**10. Logout có luôn làm JWT access token mất hiệu lực ngay không?**

Không. Nếu API chỉ xác minh chữ ký và exp, JWT cũ có thể còn hợp lệ đến khi hết hạn. Cần revocation/introspection/denylist hoặc session version nếu muốn hiệu lực sớm.

## Ghi nhớ

Token expiration giới hạn thời gian credential có thể được sử dụng, nhưng access token, refresh token, cookie và server session có các vòng đời riêng. Server phải xác minh thời hạn và chữ ký; refresh token cần rotation hoặc sender constraint; logout cần revocation phía server; browser cần storage và CSRF policy phù hợp. Hãy xử lý clock skew, concurrent refresh, idle/absolute timeout và UX khi session kết thúc như một phần của cùng thiết kế.

## Tài liệu tham khảo

- [RFC 7519: JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html)
- [RFC 9068: JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html)
- [RFC 6749: The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html)
- [RFC 6750: OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html)
- [RFC 7009: OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html)
- [RFC 7662: OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html)
- [RFC 9700: Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [RFC 9449: OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html)
- [MDN: Set-Cookie header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [OWASP: Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP: OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
