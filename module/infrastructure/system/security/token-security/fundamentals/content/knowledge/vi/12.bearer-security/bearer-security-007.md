# Giới hạn thời gian sống

## 1. Vì sao bearer token phải có thời hạn?

**Bearer token** là credential mà bên đang nắm giữ có thể trình cho resource server (RS) để sử dụng những quyền token đại diện. Khác token ràng buộc với khóa của người gửi, bearer token thông thường **không yêu cầu chứng minh quyền sở hữu private key** khi gọi API. Vì vậy, một access token bị lộ có thể bị sao chép và phát lại cho đến khi nó không còn được RS chấp nhận.

Trong module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, giới hạn thời gian sống là một biện pháp quan trọng để giảm ảnh hưởng của **token theft**, **token replay** và quyền truy cập tồn tại quá lâu. Bài thuộc chương **Bearer security**, tập trung trả lời:

- Access token nên có thời gian sống ra sao và vì sao không có một TTL cố định đúng cho mọi hệ thống?
- `exp`, `nbf`, `iat` trong JWT có ý nghĩa gì; sai lệch đồng hồ ảnh hưởng đến xác minh thế nào?
- Refresh token, phiên đăng nhập và access token khác nhau thế nào về thời hạn?
- JWT tự xác minh và opaque token dùng introspection có khả năng thu hồi trước hạn khác nhau ra sao?
- Làm sao cấu hình, kiểm thử và giám sát TTL đúng trong ứng dụng Java/Spring Security?

**Tình huống xuyên suốt:** API `orders-api` chấp nhận bearer access token do `https://auth.example.test` cấp, với audience `orders-api` và scope `orders.read`. Nếu token này bị ghi nhầm vào log, kẻ đọc được log có thể phát lại trong khoảng thời gian token còn hiệu lực. Giảm TTL từ hàng giờ xuống vài phút có thể thu hẹp khoảng thời gian lạm dụng, nhưng không ngăn kẻ tấn công dùng token **ngay sau khi lấy được**, và không thay thế kiểm tra issuer, audience, scope hay quyền trên đơn hàng cụ thể.

> **Nguyên tắc:** Cấp bearer token ngắn hạn theo rủi ro thực tế, chỉ dành cho đúng resource và quyền cần thiết; thiết kế riêng cơ chế gia hạn và thu hồi. “Token còn hạn” chưa đủ để cấp quyền.

## 2. Những loại thời hạn dễ bị nhầm

| Khái niệm | Ý nghĩa | Ví dụ | Cảnh báo |
| --- | --- | --- | --- |
| **Access token TTL** | Khoảng thời gian access token được dự kiến chấp nhận | 5 phút kể từ lúc phát hành | Là giới hạn thời gian, không phải bằng chứng quyền hợp lệ |
| **JWT `exp`** | Mốc thời gian token phải bị từ chối sau đó, xét chính sách sai lệch đồng hồ | Unix time dạng NumericDate | Giá trị do client tự khai không đáng tin nếu JWT chưa xác minh |
| **JWT `nbf`** | Mốc token chưa được chấp nhận trước đó | Token bắt đầu có hiệu lực sau thời điểm phát hành | Không phải thời hạn hết hạn |
| **JWT `iat`** | Thời điểm token được phát hành | AS phát hành lúc 10:00 | Không tự thay thế `exp` |
| **Refresh token lifetime** | Khoảng thời gian refresh credential có thể xin access token mới | Vài giờ/ngày theo AS policy | Refresh token bị lộ có thể gây phiên truy cập kéo dài |
| **Idle timeout** | Hết hiệu lực sau khoảng không hoạt động, nếu hệ thống theo dõi trạng thái | Session hết hạn sau 30 phút không dùng | JWT tự chứa không mặc nhiên có idle timeout |
| **Absolute lifetime** | Thời gian tối đa kể từ điểm bắt đầu, bất kể hoạt động | Phiên tối đa 8 giờ | Không được kéo dài vô hạn chỉ nhờ gia hạn |
| **Client credential lifetime** | Thời hạn secret, khóa hoặc chứng chỉ dùng để xác thực client | Khóa được rotate theo lịch | Không đồng nghĩa TTL access token được cấp |
| **Consent/grant lifetime** | Thời gian ủy quyền/grant của người dùng hoặc tổ chức còn hiệu lực | Grant tồn tại đến khi bị rút | Consent tồn tại không đồng nghĩa access token hiện tại còn hạn |

Ba lớp trạng thái thường phải được quản lý độc lập:

~~~mermaid
flowchart LR
    A["Client credential / user session"] --> B["AS xác thực và đánh giá grant"]
    B --> C["Refresh token / grant nếu được cấp"]
    B --> D["Access token ngắn hạn"]
    C -->|"Xin access token mới theo policy"| D
    D -->|"Bearer token"| E["Resource server"]
    E --> F{"Chữ ký/introspection + iss + aud + thời gian + scope + ACL?"}
    F -->|"Đúng"| G["Cho phép"]
    F -->|"Sai"| H["Từ chối"]
~~~

Client có thể cần xin access token mới **nhiều lần** trong suốt một phiên hợp lệ. Ngược lại, access token còn hiệu lực về thời gian có thể bị từ chối sớm hơn do thu hồi, thay đổi quyền, audience sai hoặc issuer không còn được tin cậy.

### 2.1. TTL của access token khác TTL của refresh token

Access token được trình tới RS và có thể đi qua API Gateway, backend, client SDK hoặc log nếu hệ thống sai cấu hình. **Refresh token** thường chỉ được trình tới token endpoint của AS và có thể giúp xin các access token mới. Vì tác động của refresh token bị lộ có thể kéo dài, refresh token cần chính sách mạnh về lưu trữ, binding, rotation hoặc sender constraint và **giới hạn thời hạn riêng**.

Đặc biệt, với OAuth 2.0 `client_credentials`, client thường **không cần refresh token**: khi access token hết hạn, client xác thực lại với AS. Theo RFC 6749, refresh token **SHOULD NOT** được cấp trong grant này.

### 2.2. Không dùng thời hạn phiên để thay `exp`

Một browser còn cookie phiên không có nghĩa bearer access token cũ của nó vẫn dùng được; ngược lại, người dùng đã logout phía client không bảo đảm access token bị sao chép trước đó đã vô hiệu ngay tại RS. Token, cookie phiên, grant và các token trong cache có vòng đời khác nhau, cần chính sách gắn kết rõ ràng nếu muốn logout có hiệu lực sớm.

## 3. Giới hạn thời gian giúp giảm rủi ro như thế nào?

Giả sử một bearer token được cấp lúc 10:00 với TTL 10 phút, và kẻ tấn công lấy được token lúc 10:07. Nếu RS chỉ dựa vào token còn hạn, **cửa sổ lạm dụng còn khoảng 3 phút**; nếu token sống 24 giờ, nguy cơ có thể kéo dài nhiều giờ.

Đối với token có mốc phát hành `t_issued`, hết hạn `t_exp` và bị lộ ở `t_stolen`, có thể ước lượng thời gian còn lại:

\[
W_{\text{remaining}}=\max(0,\ t_{\text{exp}}-t_{\text{stolen}})
\]

Đây là mô hình đơn giản **chưa tính clock skew được phép, cache trạng thái, độ trễ thu hồi, proof-of-possession hoặc policy riêng**. Nếu RS chấp nhận một khoảng leeway sau `exp`, cửa sổ chấp nhận thực tế có thể nhỉnh hơn thời hạn danh nghĩa.

### 3.1. TTL ngắn làm được gì?

1. Thu hẹp thời gian bearer token bị đánh cắp còn có giá trị.
2. Giới hạn khoảng quyền cũ có thể tiếp tục tồn tại trong JWT tự xác minh sau khi vai trò của user thay đổi.
3. Giảm thời gian RS phải chấp nhận một khóa ký đã nghỉ phát hành, trong chiến lược JWKS rotation được thiết kế đúng.
4. Giảm giá trị của bản sao token lọt vào log, bộ nhớ đệm, crash dump hoặc bên thứ ba.

### 3.2. TTL ngắn không làm được gì?

1. Không chặn token bị đánh cắp **được sử dụng ngay**.
2. Không bảo vệ credential/token khỏi XSS, SSRF, log leak hoặc client bị xâm nhập.
3. Không biến token sai `aud` hoặc thiếu `scope` thành hợp lệ.
4. Không thu hồi refresh token bị đánh cắp.
5. Không ngăn request trái phép nếu RS bỏ qua object-level authorization.
6. Không tự chống replay của access token bearer còn hạn.

Vì vậy phải kết hợp TTL với **TLS, bảo mật nơi lưu, audience/scope hẹp, token validation, revocation, monitoring** và, khi cần, **sender-constrained tokens** như DPoP hoặc certificate-bound mTLS.

## 4. JWT thời gian: exp, nbf, iat và NumericDate

Theo RFC 7519, `exp`, `nbf` và `iat` dùng kiểu **NumericDate**: số giây kể từ Unix epoch (1970-01-01T00:00:00Z), không phải mili-giây của `System.currentTimeMillis()`. NumericDate có thể biểu diễn số với phần lẻ; một profile riêng có thể yêu cầu giá trị nguyên giây.

Ví dụ payload **minh họa, chưa phải JWT đã ký**:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1795400000,
  "nbf": 1795400000,
  "exp": 1795400300,
  "jti": "token-example-001"
}
~~~

Tại đây, chênh lệch `exp - iat = 300` giây, tức TTL danh nghĩa **5 phút**. Các mốc chỉ minh họa cấu trúc; verifier phải so thời gian thực tại lúc kiểm tra, không coi ví dụ là token có thể sử dụng.

| Claim | Điều kiện cần kiểm tra | Lỗi điển hình |
| --- | --- | --- |
| `exp` | Thời gian hiện tại phải **trước** mốc hết hạn, xét leeway có kiểm soát | Nhận token hết hạn do chỉ kiểm tra chữ ký |
| `nbf` | Chưa được dùng token trước thời điểm có hiệu lực, xét leeway | Bỏ qua token `nbf` trong tương lai |
| `iat` | Thời điểm phát hành hợp lý theo token profile; nếu dùng để tính maximum TTL, cần có mặt và đúng kiểu | Nhầm mili-giây thành giây hoặc chấp nhận `iat` tùy ý trong tương lai |
| `exp - iat` | Không vượt TTL tối đa theo **policy riêng của RS**, nếu profile yêu cầu kiểm tra này | AS lỗi cấp JWT có thời hạn quá dài |
| `auth_time` (OIDC, nếu áp dụng) | Thời điểm end-user được xác thực theo profile OIDC | Nhầm thời điểm authentication với thời điểm phát hành access token |

**Quan trọng:** `exp` và `nbf` là claims tùy chọn trong JWT chung theo RFC 7519, nhưng **OAuth JWT access token profile RFC 9068 yêu cầu `exp` và các claims cụ thể**. Resource server có thể yêu cầu `exp` và `iat` dù định dạng JWT tổng quát không bắt buộc chúng. Không coi “claim tùy chọn ở chuẩn tổng quát” là lý do chấp nhận access token không có hạn.

### 4.1. Vì sao không chỉ kiểm tra `exp`?

Giả sử AS hoặc thành phần phát hành bị cấu hình sai, tạo JWT còn hạn 10 năm. Nếu RS chỉ xem “`exp` nằm trong tương lai” thì sẽ chấp nhận token quá dài. Ngoài việc kiểm tra `exp`, RS có thể thực thi:

~~~text
require iat is present (theo contract access token)
require exp is present
require iat <= exp
require exp - iat <= maxAccessTokenTtl
require iat <= now + maxAllowedClockSkew
require nbf <= now + maxAllowedClockSkew (nếu có)
require now < exp + maxAllowedClockSkew
~~~

Các điều kiện trên là **policy bổ sung** để giới hạn TTL, không tự thay thế xác minh chữ ký, issuer, audience và token profile. Nếu `iat` là giá trị chưa được ký/xác minh, kiểm tra này không đáng tin. RS nên dùng thư viện JOSE/JWT và các validator có giới hạn rõ ràng thay vì tự đọc payload Base64url rồi tin claims.

### 4.2. Sai đơn vị giây và mili-giây

Trong Java:

~~~java
Instant now = Instant.now();
long epochSeconds = now.getEpochSecond(); // Đơn vị giây
long epochMillis = System.currentTimeMillis(); // Đơn vị mili-giây
~~~

Nếu một hệ thống gán nhầm `epochMillis` cho `exp` kiểu NumericDate, token có thể trông như hết hạn rất xa trong tương lai. Lỗi ngược lại có thể khiến token hết hạn ngay. Chọn kiểu `Instant`/`Duration` trong code và dùng thư viện chuyển đổi claims để tránh tính toán sai đơn vị.

### 4.3. Không suy diễn TTL từ client

Client có thể nhận `expires_in` trong token response:

~~~json
{
  "access_token": "<access-token>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

`expires_in` giúp **client** lên lịch tái lấy token; nó không thể được client gửi lại để yêu cầu RS chấp nhận token lâu hơn. RS phải kiểm tra `exp` đã ký (JWT) hoặc trạng thái/thời gian do AS cung cấp qua introspection (opaque). Trong hệ thống sử dụng JWT, client không nên tự sửa `exp` rồi kỳ vọng chữ ký vẫn hợp lệ.

## 5. Clock skew và khoảng dung sai kiểm tra thời gian

Authorization server, resource server, gateway và client có thể có độ lệch đồng hồ nhỏ. Đặc tả JWT cho phép bên xác minh dùng **leeway nhỏ** để bù sai lệch; thư viện thường cung cấp cấu hình `clockSkew` hoặc `JwtTimestampValidator`.

Ví dụ:

~~~text
AS phát hành:              10:00:00
JWT exp:                   10:05:00
RS đồng hồ nhanh 20 giây:  10:05:20 (cùng thời điểm thực tế 10:05:00)
Leeway RS:                 30 giây
~~~

Leeway giúp giảm việc từ chối token hợp lệ gần ranh giới giờ. Tuy nhiên, mỗi giây leeway sau `exp` cũng có thể mở rộng **thời gian thực tế token được chấp nhận**. Cấu hình leeway nên nhỏ và có căn cứ; đồng bộ đồng hồ bằng NTP/giám sát clock drift thay vì mở leeway vài phút hoặc vài giờ cho tiện.

### 5.1. Hai lỗi logic phải tránh

- **Cho phép quá hạn bằng cách cộng leeway nhiều lần:** Một gateway chấp nhận `exp + 60s`, backend lại tự gia hạn thêm 60 giây dựa trên token mới xây từ claims. Các lớp phải thống nhất policy, không tạo hiệu ứng cộng dồn.
- **Lấy thời gian của client làm nguồn tin:** Client tự gửi `X-Client-Time` hoặc một claim chưa ký rồi RS dùng nó để đánh giá `exp`. Mốc so sánh phải là đồng hồ của thành phần tin cậy xác minh token.

Để tránh tình trạng token mới cấp đã bị RS coi là “quá tương lai”, cũng nên kiểm tra `iat` hợp lý, `nbf` và độ lệch thời gian giữa AS–RS. Leeway không làm mất yêu cầu `exp` bắt buộc của access token profile.

### 5.2. Kịch bản ranh giới

Nếu `exp = 10:05:00` và leeway bằng 0, token không được chấp nhận tại hoặc sau 10:05:00 (theo đồng hồ verifier). Nếu leeway 30 giây, verifier có thể chấp nhận trong khoảng dung sai theo cách thư viện áp dụng. **Đừng viết kiểm thử hardcode ranh giới mà không biết cách thư viện xử lý dấu bằng (`<`/`<=`)**; kiểm thử cần sử dụng clock cố định và kiểm tra chính sách chính xác.

## 6. Chọn thời gian sống theo mô hình rủi ro

Không có RFC nào quy định mọi OAuth access token phải sống chính xác **5, 10 hay 15 phút**. Chính sách TTL là lựa chọn kiến trúc theo mức độ nhạy cảm của tài nguyên, xác thực client, khả năng AS/RS, độ trễ thu hồi và trải nghiệm người dùng.

Các câu hỏi cần trả lời trước khi cấu hình:

1. Token có thể dùng để **đọc dữ liệu công khai, dữ liệu cá nhân hay chuyển tiền**?
2. Token chỉ dành cho **một audience** hay có giá trị ở nhiều API? Scope có hẹp hay quá rộng?
3. Client là backend bảo vệ được credential hay browser/mobile dễ bị mất thiết bị/XSS?
4. Nếu token bị lộ, hệ thống có thể **thu hồi ngay tại RS** hay chỉ chờ `exp`?
5. Có DPoP/mTLS sender constraint và kiểm tra replay proof đúng cách không?
6. AS có chịu được việc xin token thường xuyên không? Client có cache và single-flight không?
7. Đồng hồ có đồng bộ không? Có đủ dung sai cho request hợp lệ trong lúc truyền qua mạng?
8. Chính sách đăng xuất, thay mật khẩu, hạ quyền và khóa tài khoản cần có hiệu lực nhanh đến mức nào?

### 6.1. Bảng quyết định minh họa

| Bối cảnh | Ví dụ TTL access token để bắt đầu đánh giá | Kiểm soát đi kèm |
| --- | --- | --- |
| API nhạy cảm, giao dịch quan trọng | Khoảng 1–5 phút | Step-up phù hợp, audience/scope hẹp, phát hiện bất thường, revocation hoặc sender constraint nếu cần |
| API nghiệp vụ có đăng nhập | Khoảng 5–15 phút | Authorization Code + PKCE/BFF khi phù hợp, refresh rotation, object-level authorization |
| Backend-to-backend với workload identity được bảo vệ | Khoảng 5–15 phút | Client authentication/federation, cache an toàn, quyền service tối thiểu |
| Tác vụ batch có thể kết nối lại AS | Khoảng vài phút đến vài chục phút theo rủi ro | Client credentials, renewal sớm, retry có giới hạn, AS rate limit |
| Thiết bị không thường xuyên có mạng | Cần phân tích riêng, đôi khi thời hạn dài hơn | Quyền rất hẹp, local key protection, chính sách offline và revocation hạn chế |

**Đây chỉ là ví dụ để thảo luận thiết kế, không phải ngưỡng bắt buộc hay khuyến cáo thời lượng cố định của RFC.** Với ứng dụng có yêu cầu thu hồi tức thì, rút TTL xuống 1 phút vẫn có thể **chưa đạt SLA** vì token bị lộ vẫn dùng được ngay trong 1 phút ấy.

### 6.2. Cân bằng ba chi phí

Giảm TTL thường đem lại:

| Khía cạnh | TTL ngắn | TTL dài |
| --- | --- | --- |
| Cửa sổ token bị lộ có thể phát lại | Ngắn hơn | Dài hơn |
| Tần suất client xin token mới | Cao hơn | Thấp hơn |
| Phụ thuộc khả năng sẵn sàng AS khi token hết hạn | Thường cao hơn | Thường thấp hơn |
| Độ trễ cập nhật quyền khi chỉ dựa vào claims tự chứa | Thường ngắn hơn | Thường dài hơn |
| Áp lực lên token endpoint, JWKS/introspection/cache | Có thể tăng tùy cơ chế | Có thể giảm tùy cơ chế |

AS có thể cấp token hàng loạt hiệu quả nếu client có cache hợp lý; ngược lại, TTL ngắn mà mỗi API call đều đổi token là cấu hình vận hành kém. **Không tối ưu TTL chỉ dựa trên một số liệu**, chẳng hạn giảm mọi token xuống 30 giây mà không tính network latency, tải AS và clock skew.

### 6.3. Scope, audience và TTL phải được xem cùng nhau

Một token `aud=orders-api`, chỉ có `orders.read`, hết hạn sau vài phút có phạm vi tác động nhỏ hơn token dùng được ở nhiều API, có `admin` và sống 24 giờ. Nhưng ngay cả token hẹp vẫn phải kiểm tra quyền truy cập từng đơn hàng.

Thực hành:

- Cấp access token **riêng cho resource đích**, tránh một token giá trị ở nhiều nơi khi không cần.
- Cấp scope tối thiểu và chỉ trong khoảng cần thực hiện tác vụ.
- Với quyền nhạy cảm, AS có thể áp TTL ngắn hơn hoặc yêu cầu xác thực/ủy quyền mạnh hơn theo policy.
- RS **không chỉ tin TTL**: tiếp tục xác minh chữ ký/introspection, issuer, audience, loại token và quyền nghiệp vụ.

## 7. Phát hành access token với thời hạn phù hợp

Authorization server là nơi đưa ra quyết định cấp token: xác thực client/user, kiểm tra consent/grant, giới hạn scope và audience, chọn TTL rồi ký JWT hoặc tạo opaque token với trạng thái được quản lý. Client **có thể xin** một thời hạn cụ thể nếu AS hỗ trợ extension, nhưng không được tự quyết định `exp` chỉ bằng tham số do mình gửi.

Một pipeline phát hành về mặt logic:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant P as Issuance policy
    participant RS as orders-api
    C->>AS: Xin token cho orders-api, scope=orders.read
    AS->>AS: Xác thực client/user và grant
    AS->>P: Tính scope, audience, TTL theo risk/policy
    P-->>AS: aud=orders-api; scope=orders.read; TTL=300s
    AS->>AS: Phát hành JWT (iat, nbf, exp) hoặc opaque + expiry state
    AS-->>C: access_token, token_type, expires_in
    C->>RS: Authorization: Bearer <access-token>
    RS->>RS: Verify và kiểm tra exp/active + quyền
    RS-->>C: 200 hoặc từ chối 401/403
~~~

### 7.1. Bất biến cần giữ khi phát hành

Với JWT access token, AS cần bảo đảm:

~~~text
issuer = issuer đã được đăng ký và bảo vệ khóa ký
audience = resource client được cấp phép truy cập
scope = quyền đã được policy cho phép
issued_at = thời điểm phát hành từ đồng hồ tin cậy
expires_at = issued_at + ttl đã được policy phê duyệt
not_before = mốc hợp lệ nếu profile yêu cầu
token_type/profile = OAuth access token, không phải ID token
~~~

Nếu AS hỗ trợ nhiều profile/token type, phải tránh phát hành ID token có audience của API chỉ vì cấu hình tiện lợi. ID token OIDC phục vụ client xác thực end-user, còn access token phục vụ resource server. Nếu là opaque token, AS quản lý `expires_at` trong token store và trả metadata phù hợp qua introspection khi RS yêu cầu.

### 7.2. Java: diễn tả TTL bằng Duration, không bằng phép cộng đơn vị mơ hồ

~~~java
Duration tokenTtl = Duration.ofMinutes(5);
Instant issuedAt = clock.instant();
Instant expiresAt = issuedAt.plus(tokenTtl);

if (!expiresAt.isAfter(issuedAt)) {
    throw new IllegalArgumentException("Invalid token TTL");
}

// Các Instant này phải được AS đưa vào token/store đáng tin
// sau khi chính sách issuer, audience, scope đã được xác thực.
~~~

Đoạn Java chỉ minh họa tính mốc thời gian; nó **không phát hành JWT** hoặc cấp quyền. AS cần kiểm tra TTL tối thiểu/tối đa, serialize đúng NumericDate và bảo vệ signing key/opaque token store theo kiến trúc.

### 7.3. Spring Authorization Server: policy TTL theo client

Với Spring Authorization Server (phiên bản hỗ trợ API được minh họa), một `RegisteredClient` có thể cấu hình TTL:

~~~java
TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build();

RegisteredClient client = RegisteredClient.withId(
            UUID.randomUUID().toString())
        .clientId("orders-worker")
        .clientSecret(passwordEncoder.encode(clientSecret))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("inventory.read")
        .tokenSettings(tokenSettings)
        .build();
~~~

Ví dụ giả định `passwordEncoder`/`clientSecret` và các imports tương ứng đã được cấu hình. **Không hardcode client secret thật**; tải secret từ secret manager. `TokenSettings.accessTokenTimeToLive` quy định thời hạn token trong policy của client ở authorization server, nhưng không tự tạo hạn mức cho mọi client khác, không thay thế quyết định audience và không tự buộc resource server kiểm tra token đúng cách.

Với một client sử dụng grant có refresh token, `TokenSettings` có thể cấu hình riêng `refreshTokenTimeToLive` và `reuseRefreshTokens` khi phiên bản Spring Authorization Server hỗ trợ. Không áp ví dụ refresh token vào client credentials chỉ vì có thuộc tính cấu hình: RFC 6749 không khuyến nghị cấp refresh token cho grant này. Quy trình rotation/revocation phải được thiết kế và kiểm thử theo AS cụ thể.

## 8. Gia hạn trước khi hết hạn, nhưng không vô hạn

Khi access token gần hết hạn, client có thể:

- Gọi token endpoint với **refresh token** nếu AS đã cấp refresh token theo grant/policy.
- Thực hiện lại `client_credentials` với client secret/private key/workload identity thích hợp.
- Thực hiện lại authorization flow nếu grant đã hết hạn, refresh token bị thu hồi hoặc AS yêu cầu user xác thực lại.

**Client không được “gia hạn” JWT bằng cách đổi `exp` trong payload.** Thay đổi đó sẽ làm chữ ký không còn hợp lệ. Chỉ AS có thẩm quyền mới phát hành token mới, hoặc cung cấp cơ chế được định nghĩa rõ để thay đổi trạng thái opaque token.

### 8.1. Renewal sớm có kiểm soát

Ví dụ access token có TTL 300 giây, client có thể chủ động xin token mới khi còn khoảng 30 giây trước `exp`, tùy mạng và hệ thống. Đây là **khoảng dự phòng phía client**, không phải quyền để RS chấp nhận token đã hết hạn.

~~~text
access_token_expires_at = 10:05:00
renewal_lead_time       = 00:00:30
client_target_renewal   = 10:04:30
resource_server_expiry  = 10:05:00 (cộng leeway nhỏ nếu policy cho phép)
~~~

Khi hàng nghìn instance cùng nhận token có thời hạn giống nhau, nên dùng jitter để giảm **thundering herd** trên token endpoint. Client cũng cần cache và single-flight để nhiều request đồng thời không phát sinh hàng loạt token request.

### 8.2. Refresh-token rotation và race condition

Nếu refresh token được rotate theo chuỗi:

~~~text
RT-1 --refresh--> RT-2 --refresh--> RT-3
~~~

Hai request đồng thời với `RT-1` có thể khiến AS coi request thứ hai là replay, tùy chính sách phát hiện reuse, và có thể thu hồi token family. Hãy thiết kế:

1. **Single-flight:** một phiên/grant chỉ có một refresh operation đang chạy.
2. **Phân vùng đúng:** không dùng refresh token Alice để gia hạn phiên Bob hoặc tenant khác.
3. **Atomic update:** lưu access token và refresh token mới như một cặp; có version/CAS để tránh ghi đè bằng RT cũ.
4. **Recovery:** khi response bị mất sau khi AS commit rotation, không retry mù quáng bằng RT cũ; tuân thủ recovery policy hoặc yêu cầu đăng nhập lại khi cần.
5. **Revocation:** khi phát hiện token bị đánh cắp, revoke grant/RT theo cơ chế AS hỗ trợ và kiểm soát access token còn hạn.

Theo OAuth Security BCP (RFC 9700), refresh token cho public client phải được bảo vệ bằng biện pháp phát hiện replay thích hợp như **refresh token rotation hoặc sender-constrained refresh token**. Một access token sống ngắn không đủ an toàn nếu refresh token có thể bị đánh cắp và dùng liên tục để mint access token mới.

### 8.3. Sliding session và absolute expiration

Một phiên có thể có **idle timeout**: nếu người dùng hoạt động, hệ thống cập nhật lần sử dụng cuối và cho phép tiếp tục trong phạm vi policy. Nhưng gia hạn theo hoạt động không nên tạo phiên không bao giờ hết hạn.

Ví dụ:

~~~text
Login:              09:00
Session idle limit:  30 phút không hoạt động
Absolute limit:      17:00 cùng ngày
Access token TTL:   5 phút mỗi lần cấp
~~~

Nếu Alice vẫn hoạt động lúc 16:59, hệ thống có thể cấp access token ngắn hạn theo chính sách còn hiệu lực, nhưng phải định nghĩa chuyện gì xảy ra tại absolute limit: không được để một refresh operation kéo dài khả năng xin token đến ngày hôm sau chỉ vì có request mỗi 10 phút. Absolute session lifetime là **policy ứng dụng/AS**, không phải claim JWT tiêu chuẩn áp dụng tự động.

Trong OIDC, `auth_time` và `max_age` có thể phục vụ yêu cầu về độ mới của xác thực end-user: `max_age` là tham số authorization request; `auth_time` mô tả lúc end-user thực sự xác thực. **Không dùng `iat` của access token mới để kết luận Alice vừa đăng nhập/MFA lại**; một refresh token có thể cấp access token mới mà không có sự kiện xác thực người dùng mới.

## 9. JWT và opaque: hết hạn, thu hồi và cache

TTL và khả năng thu hồi không giống nhau. Cùng một hạn 5 phút nhưng JWT xác minh offline và opaque introspection có thể phản ứng khác khi AS thu hồi token sau 1 phút.

| Đặc điểm | JWT access token xác minh cục bộ | Opaque access token dùng introspection |
| --- | --- | --- |
| Kiểm tra hết hạn | Verifier đọc `exp` từ JWT đã xác minh chữ ký | AS/RS xác định `active` và `exp` từ trạng thái đáng tin |
| Liên hệ AS ở mỗi request | Không nhất thiết; có thể cache JWKS | Có thể gọi introspection hoặc dùng cache hợp lệ |
| Thu hồi trước hạn | Cần denylist, trạng thái bổ sung hoặc chiến lược khác | AS có thể trả `active:false` nếu đã revoke |
| Ảnh hưởng cache | JWT vẫn còn hạn dù AS thay đổi quyền nếu RS không tra trạng thái | Cache `active:true` có thể khiến token đã revoke tiếp tục được chấp nhận |
| Khi AS/JWKS/introspection lỗi | Phụ thuộc khóa đã cache và policy; không tin issuer/key lạ | Không fail open khi không có kết quả xác minh hợp lệ |
| Giới hạn bắt buộc | `iss`, chữ ký, `aud`, `exp`/profile, scope, object policy | Nguồn introspection tin cậy, `active`, resource binding, scope, object policy |

### 9.1. Ví dụ về độ trễ thu hồi

AS cấp bearer access token lúc 10:00, hết hạn 10:05. Đến 10:01 token bị lộ và bị revoke.

- **JWT offline:** RS chỉ xác minh chữ ký/`exp` có thể vẫn chấp nhận tới 10:05 (cộng leeway nếu có) nếu không có cơ chế thu hồi bổ sung.
- **Opaque online:** RS gọi AS và nhận `active:false` có thể từ chối ngay sau khi trạng thái revoke được cập nhật.
- **Opaque với cache:** RS giữ bản introspection `active:true` trong 60 giây có thể tiếp tục chấp nhận trong thời gian cache còn hiệu lực. TTL cache cần được giới hạn bởi thời gian hết hạn và **SLA thu hồi**.

Vì thế yêu cầu “revocation phải có hiệu lực tối đa 5 giây” không thể chỉ được giải quyết bằng “đặt access token TTL 5 phút”. Cần thiết kế cơ chế trạng thái và giới hạn cache tương ứng.

### 9.2. Cache introspection không được vượt thời hạn token

Nếu RS cache phản hồi introspection, TTL của cache về nguyên tắc cần không vượt:

\[
TTL_{\text{cache}} \leq \min(TTL_{\text{policy}},\ t_{\text{exp}}-t_{\text{now}})
\]

Khi `exp` không được trả hoặc policy không cho phép cache, RS phải có giới hạn riêng được AS/RS thỏa thuận; đừng suy đoán token còn sống vô thời hạn. Nếu AS đã thu hồi token, cache `active:true` cũ vẫn là vấn đề cần quản trị. Không cache lỗi mạng thành “active” và không chấp nhận token khi không thể xác minh trạng thái theo policy.

### 9.3. Thu hồi client credential và logout

Xoay vòng secret/private key của OAuth client **không tự động** hủy access token đã cấp bằng credential đó. Logout user hoặc xóa token khỏi bộ nhớ browser cũng không bảo đảm một bản sao ở nơi khác không còn dùng được. Cần phân biệt:

- Thu hồi **client credential** để ngăn xin token tương lai.
- Thu hồi **refresh token/grant** để ngăn tiếp tục gia hạn.
- Thu hồi **access token** hiện có (introspection/denylist, status API, key changes theo thiết kế).
- Thay đổi **quyền nghiệp vụ** để chặn hoạt động ngay cả khi JWT còn hạn.

### 9.4. Key rotation và thời hạn token

Đối với JWT ký bất đối xứng, khi AS rotate signing key, JWT đã được ký bằng khóa cũ vẫn có thể còn hạn. Nếu RS xóa public key cũ khỏi JWKS cache quá sớm, token hợp lệ bị từ chối; nếu khóa ký bị compromise, tiếp tục tin khóa cũ có thể nguy hiểm.

Chiến lược thông thường là:

1. Công bố khóa mới trước khi chuyển sang ký bằng khóa mới, phù hợp khả năng cache/JWKS refresh.
2. Cho RS lấy khóa mới qua JWKS tin cậy, với `kid` chọn trong key set của đúng issuer.
3. Theo dõi access token dài nhất còn hạn cộng khoảng clock skew/cache để quyết định khi nào có thể loại khóa cũ **trong tình huống rotation bình thường**.
4. Với **key compromise**, xử lý khẩn cấp khác rotation thông thường: ngừng tin khóa bị lộ, thu hồi hoặc vô hiệu token bị ảnh hưởng theo policy, dù có thể làm gián đoạn phiên.

**Đừng nhầm “đổi key ký” với “thu hồi mọi JWT ngay”**. TTL, JWKS cache và trạng thái khóa cần được phối hợp; resource server phải fail closed nếu không thể xác minh chữ ký từ khóa tin cậy.

## 10. Cách lưu token và giảm rủi ro khi TTL không thể quá ngắn

Giới hạn thời gian sống nên được đặt trong **defense in depth**, không phải “giải pháp chữa mọi rủi ro”:

| Nơi token xuất hiện | Nguy cơ lộ token | Kiểm soát phù hợp |
| --- | --- | --- |
| HTTP giữa client và API | Bị nghe lén, gửi nhầm host hoặc proxy | HTTPS/TLS, xác thực host, `Authorization: Bearer` đúng endpoint |
| Query string/URL | URL bị ghi log, browser history, analytics | Không đưa bearer token vào URL |
| Reverse proxy và API Gateway | Header `Authorization` bị đưa vào access log/tracing | Redact token, bảo vệ log và đường gateway–backend |
| Browser JavaScript | XSS/dependency độc hại đọc token | Hạn chế token ở JS, cân nhắc BFF và cookie/session phù hợp |
| Cookie phiên | Session hijacking hoặc CSRF | `HttpOnly`, `Secure`, `SameSite` và CSRF defense đúng ngữ cảnh |
| Backend memory, crash dump | Core dump/diagnostics chứa token | Giới hạn truy cập, thời gian lưu và nội dung telemetry |
| Secret store/database | Refresh token hoặc client secret bị lộ | Mã hóa lưu trữ, least privilege, rotation, audit |
| CI/CD và container | Token/secret bị commit vào repo hoặc image | Secret scanning, secret manager, tránh in environment dump |

**Chú ý:** Cookie có `HttpOnly` giảm khả năng JavaScript đọc trực tiếp nhưng **không tự ngăn CSRF** vì cookie có thể được trình duyệt gửi tự động. Việc dùng BFF/cookie cần kiểm soát session, CSRF, XSS và CORS đúng thiết kế. TTL vẫn cần thiết đối với bearer session cookie nếu chỉ cần giữ giá trị cookie là có thể sử dụng phiên.

### 10.1. Khi cần chống replay ngay trong thời hạn hợp lệ

Nếu ứng dụng giao dịch có nguy cơ token bị sao chép rất cao, chỉ dùng bearer TTL 1 phút vẫn tạo ra cửa sổ một phút có thể bị lạm dụng. Có thể cân nhắc:

- **DPoP (RFC 9449):** access token ràng buộc với public key của client; mỗi request có proof ký bằng private key tương ứng. RS phải kiểm tra binding, method/URI, `iat`/`jti`/`ath` và nonce/replay policy khi áp dụng.
- **mTLS certificate-bound tokens (RFC 8705):** access token ràng buộc với chứng chỉ của client; RS phải xác minh client chứng minh sở hữu private key phù hợp qua mTLS và so binding token–chứng chỉ.

Hai cơ chế này giảm khả năng sử dụng **token bị sao chép đơn thuần**, nhưng không thay thế TTL, audience, scope, object-level authorization hoặc bảo vệ private key. Nếu attacker chiếm cả token và khả năng ký proof, họ vẫn có thể lạm dụng.

## 11. Java/Spring Security: xác minh thời hạn ở resource server

Một API Java nhận JWT bearer token nên dùng Spring Security Resource Server và thư viện JOSE/JWT được bảo trì. **Không tự tách chuỗi JWT, Base64-decode payload rồi tin `exp`**: attacker có thể sửa payload khi chưa xác minh chữ ký.

### 11.1. Cấu hình issuer đáng tin

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

`issuer-uri` cho framework biết issuer được tin cậy và thường giúp cấu hình JWKS. Tuy nhiên **issuer và chữ ký đúng chưa đủ**: API phải kiểm tra `aud`, thời hạn, access-token profile và scope/permission. Nếu API có TTL tối đa ngắn hơn chính sách AS, cần thêm validator giới hạn `exp - iat`.

### 11.2. Validator cho `exp`, `nbf`, audience và TTL tối đa

Ví dụ Spring Security 6.x với token JWT ký RS256, issuer đã biết, audience `orders-api`, dung sai thời gian 30 giây và TTL tối đa 10 phút:

~~~java
@Configuration
@EnableWebSecurity
class OrdersSecurityConfiguration {
    private static final String ISSUER =
            "https://auth.example.test";
    private static final String JWKS_URI =
            "https://auth.example.test/oauth2/jwks";
    private static final Duration MAX_TTL = Duration.ofMinutes(10);
    private static final Duration SKEW = Duration.ofSeconds(30);

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(JWKS_URI)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        JwtTimestampValidator timestampValidator =
                new JwtTimestampValidator(SKEW);

        OAuth2TokenValidator<Jwt> policyValidator = jwt -> {
            Instant issued = jwt.getIssuedAt();
            Instant expiry = jwt.getExpiresAt();

            if (!jwt.getAudience().contains("orders-api")) {
                return invalid("Wrong access token audience");
            }
            if (issued == null || expiry == null
                    || !expiry.isAfter(issued)) {
                return invalid("Missing or inconsistent token times");
            }
            if (Duration.between(issued, expiry).compareTo(MAX_TTL) > 0) {
                return invalid("Access token TTL exceeds policy");
            }
            if (issued.isAfter(Instant.now().plus(SKEW))) {
                return invalid("Issued-at is too far in the future");
            }
            return OAuth2TokenValidatorResult.success();
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        new JwtIssuerValidator(ISSUER),
                        timestampValidator,
                        policyValidator));
        return decoder;
    }

    private static OAuth2TokenValidatorResult invalid(String reason) {
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", reason, null));
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll());
        http.oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

**Ý nghĩa và giới hạn ví dụ:**

1. `JwtTimestampValidator` dùng leeway cho `exp`/`nbf` theo hành vi của thư viện.
2. Policy bổ sung **yêu cầu cả `iat` và `exp`** rồi giới hạn TTL tối đa; đây là yêu cầu **riêng của API**. Không phải mọi profile JWT tổng quát đều bắt buộc `iat`.
3. `JwtIssuerValidator` yêu cầu issuer đáng tin; `aud` là kiểm tra độc lập, tránh token dành cho API khác được chấp nhận.
4. `MAX_TTL=10 phút` là ngưỡng minh họa, không phải khuyến cáo mặc định cho mọi hệ thống.
5. Kiểm tra `SCOPE_orders.read` là bước phân quyền route; service/domain layer vẫn phải kiểm tra quyền đối với **đơn hàng cụ thể**.
6. Ví dụ chưa áp kiểm tra `typ=at+jwt` hoặc mọi yêu cầu profile JWT access token; nếu AS dùng RFC 9068 hoặc profile riêng, phải bổ sung validation tương ứng.
7. Khi kiểm thử thời gian, cần **tiêm một Clock cố định** cho policy validator và timestamp validator theo API hỗ trợ của phiên bản Spring Security; tránh phụ thuộc thời gian thật trong test.

Các class/import cần được chọn theo bản Spring Security đang dùng. Đừng copy ví dụ thành production mà không kiểm tra hành vi decoder, lựa chọn algorithm, JWKS cache và validator mặc định của phiên bản.

### 11.3. Với opaque token, RS vẫn phải kiểm tra TTL và trạng thái

Ví dụ cấu hình Spring Security sử dụng introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: EXTERNAL_SECRET_REFERENCE
~~~

`EXTERNAL_SECRET_REFERENCE` chỉ là placeholder; secret thật phải được lấy từ cơ chế bảo vệ credential thích hợp, không hardcode trong repo. Với opaque token, resource server chỉ tin **introspection endpoint do mình cấu hình** và metadata của AS đã xác thực. Nếu response introspection có:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1795400000,
  "exp": 1795400300
}
~~~

thì API vẫn phải kiểm tra `active`, ràng buộc resource/audience và scope/authorization. Các trường ngoài `active` trong RFC 7662 có thể tùy chọn theo AS, nên **không áp cấu trúc phản hồi ví dụ cho mọi AS**. Nếu AS không trả `exp`, phải có hợp đồng bảo đảm thời hạn và cache phù hợp; không dùng `active:true` làm giấy phép vô thời hạn. Nếu không thể introspect khi cần, phải **fail closed**.

### 11.4. HTTP 401 và 403 khi token hết hạn

Khi bearer token hết hạn hoặc không hợp lệ, resource server thường trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
Cache-Control: no-store
~~~

Khi token hợp lệ, audience đúng nhưng thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders.write"
Cache-Control: no-store
~~~

Client có thể xin access token mới khi `invalid_token` là do token hết hạn và grant còn hợp lệ; không retry vô hạn cùng token cũ. Với `insufficient_scope`, chỉ lấy token mới cùng quyền không tự giúp; phải có ủy quyền scope hợp lệ. Khi AS/introspection gặp sự cố hạ tầng, cần phân biệt lỗi vận hành với token invalid cho mục đích giám sát, nhưng **không cấp quyền khi không có bằng chứng xác minh hợp lệ**.

## 12. Bộ kiểm thử thời gian sống và bảo mật token

Để kiểm thử `exp`/`nbf` chính xác, hãy dùng **clock giả có thể điều khiển** và token được ký bằng **khóa test** của issuer test. Không đưa access token thật, refresh token hoặc private key production vào testcase/log. Với opaque token, dùng mock AS/introspection có trạng thái điều khiển được.

| ID | Trường hợp | Kết quả mong đợi |
| --- | --- | --- |
| T01 | JWT đã ký đúng, `exp` trong tương lai, audience/scope đúng | Có thể qua validation thời gian, tiếp tục authorization |
| T02 | JWT hết hạn rõ ràng, ngoài leeway | Từ chối `invalid_token` |
| T03 | JWT đúng ngay ranh giới `exp` với leeway bằng 0 | Tuân thủ quy tắc `exp` và chính sách kiểm tra dấu bằng |
| T04 | JWT gần `exp`, lệch đồng hồ trong giới hạn | Kết quả đúng theo leeway đã cấu hình |
| T05 | JWT hết hạn quá leeway dù chỉ 1 giây | Từ chối |
| T06 | `nbf` nằm tương lai ngoài leeway | Từ chối |
| T07 | `nbf` nằm tương lai nhưng trong leeway | Xử lý đúng policy, không mở rộng quá giới hạn |
| T08 | JWT thiếu `exp` khi API yêu cầu | Từ chối |
| T09 | JWT thiếu `iat` khi chính sách giới hạn `exp - iat` yêu cầu | Từ chối |
| T10 | `exp`, `iat` là JSON string hoặc boolean | Từ chối sai kiểu dữ liệu theo token profile |
| T11 | `exp` là Unix milliseconds gán vào NumericDate | Phát hiện TTL vượt policy và từ chối |
| T12 | `exp <= iat` | Từ chối dữ liệu thời gian không nhất quán |
| T13 | `exp - iat` vượt MAX_TTL dù token còn hạn | Từ chối |
| T14 | `iat` nằm tương lai vượt skew policy | Từ chối |
| T15 | Token đúng thời gian nhưng `aud=payments-api` | Từ chối vì sai audience |
| T16 | Token đúng thời gian và audience nhưng thiếu `orders.read` | Từ chối phân quyền (thường 403) |
| T17 | Token đúng mọi claims nhưng chữ ký sai | Từ chối trước cấp quyền |
| T18 | Opaque token `active:false` dù client nói chưa hết `expires_in` | Từ chối |
| T19 | Opaque token đã revoke, cache introspection vẫn `active:true` | Đo độ trễ thu hồi; cache TTL không vượt SLA đã định |
| T20 | Introspection timeout và không có kết quả tin cậy | Không cấp quyền |
| T21 | Client xin token mới trước hạn với single-flight | Không tạo đợt POST trùng không cần thiết |
| T22 | Hai tab cùng refresh token được rotate | Phối hợp tránh gửi lại RT cũ, lưu token mới nguyên tử |
| T23 | User logout nhưng access token đã bị sao chép | Kiểm thử cơ chế thu hồi thực tế, không mặc định logout chặn ngay |
| T24 | Token sống dài, khóa ký đã bị rotate bình thường | Xử lý key cũ theo thời hạn hợp lệ và JWKS policy |
| T25 | Signing key bị compromise | Thực thi quy trình khẩn cấp, không giữ tin khóa cũ chỉ vì token còn hạn |
| T26 | Client có DPoP/mTLS token hợp lệ nhưng proof/binding sai | Từ chối dù `exp` còn hạn |
| T27 | Token `exp` đúng nhưng object thuộc tenant khác | Từ chối theo domain policy |
| T28 | Absolute session lifetime đã hết nhưng refresh token được gửi lại | Không cấp token mới trái session/grant policy |

### 12.1. Test dương và âm phải đi cùng nhau

Nếu mọi token đều bị từ chối vì cấu hình JWKS sai, test “token hết hạn bị từ chối” có thể **xanh giả**. Hãy tạo hai token giống nhau về issuer, chữ ký, audience, scope và policy, chỉ khác `exp`/`nbf`; một token hợp lệ qua validation thời gian, token còn lại bị từ chối.

Với ranh giới thời gian, dùng thời điểm giả cố định:

~~~text
now = 2026-11-23T10:00:00Z
skew = 30 giây

case valid:   iat = 09:59:00, exp = 10:04:00
case expired: iat = 09:45:00, exp = 09:58:00
case future:  iat = 10:10:00, nbf = 10:10:00, exp = 10:15:00
~~~

Nếu policy MAX_TTL là 10 phút, ví dụ expired còn **vi phạm cả MAX_TTL** (`09:45 → 09:58 = 13 phút`); để cô lập đúng lỗi `exp`, hãy chọn mốc `iat=09:50:00` và `exp=09:58:00` (TTL 8 phút) trong test triển khai. Một test tốt phải tránh nhiều điều kiện cùng sai khi muốn chứng minh **một validator cụ thể** đang hoạt động.

### 12.2. Kiểm thử vận hành ngoài mã HTTP

- Đo số lần gọi token endpoint trên mỗi request nghiệp vụ; kiểm tra cache và renewal jitter.
- Theo dõi tỉ lệ `401 invalid_token` gần `exp`, sai lệch đồng hồ AS–RS và sự cố JWKS refresh.
- Xác minh token không xuất hiện trong URL, proxy log, error response, traces hoặc metrics label.
- Khi revoke, đo từ thời điểm AS commit revocation tới lúc **mọi RS ngừng chấp nhận**, nhất là RS dùng introspection cache.
- Kiểm tra thời hạn của khóa cũ và token phát hành trước rotation; phân biệt kịch bản bình thường với key compromise.
- Kiểm tra client không dùng ID token hoặc refresh token để gọi resource API khi access token hết hạn.

## 13. Ba tình huống thiết kế

### Tình huống A: Access token 5 phút nhưng dashboard bị XSS

Dashboard chạy trong browser lưu access token ở nơi JavaScript đọc được. XSS đánh cắp token ngay sau khi AS phát hành; `orders-api` chỉ yêu cầu bearer.

**Đánh giá:** TTL 5 phút giới hạn cửa sổ lạm dụng nhưng không ngăn truy cập trái phép ngay lúc token bị lộ. Cần khắc phục XSS, giảm quyền token, không đưa token vào log, cân nhắc BFF/cookie session an toàn và sender constraint nếu hệ thống hỗ trợ. API vẫn phải kiểm tra audience và quyền đơn hàng.

### Tình huống B: JWT dài hạn và quyền user đã bị rút

Alice bị xóa khỏi nhóm bán hàng lúc 10:00. JWT `orders.read` của Alice hết hạn lúc 15:00; RS xác minh JWT offline và chỉ dựa vào scope.

**Đánh giá:** Có cửa sổ quyền cũ kéo dài đến hết hạn nếu không có kiểm tra trạng thái bổ sung. Đặt TTL ngắn hơn làm giảm cửa sổ, nhưng nếu tổ chức yêu cầu ngừng truy cập ngay thì phải kiểm tra quyền tại API hoặc dùng cơ chế thu hồi/denylist/introspection. Không nên chỉ giảm TTL rồi tuyên bố đã đạt “revoke tức thời”.

### Tình huống C: 500 Pod đồng loạt xin token mỗi phút

AS giới hạn access token TTL 60 giây cho `inventory-api`. Mỗi Pod tự xin token mới ngay khi tới hạn, không cache và không jitter; AS tăng tải đột biến.

**Đánh giá:** TTL 60 giây chưa chắc cần thiết với workload được bảo vệ tốt; trước hết xác định threat model. Dùng client credentials hoặc workload federation với cache/single-flight, renewal trước hạn và jitter; đặt TTL cân bằng với khả năng AS, latency và rủi ro. Không tăng TTL vô hạn chỉ để giảm tải.

## 14. Checklist trước khi đưa TTL policy vào production

1. **Phạm vi token:** Token dành đúng issuer, audience, client, subject/tenant và scope? Có tránh token đa audience/quyền quá rộng không?
2. **TTL policy:** Đã xác định thời hạn access token dựa trên rủi ro, SLA thu hồi và tải AS? Có giới hạn maximum TTL khi RS cần không?
3. **Claims:** JWT có `exp` đúng NumericDate, `iat`/`nbf` đúng contract, ký số và profile đúng mục đích?
4. **Clock:** Các node AS/RS có đồng bộ thời gian? Leeway có nhỏ, được kiểm thử ở ranh giới và không bị cộng dồn?
5. **Client renewal:** Client có dùng `expires_in` để gia hạn sớm, cache, jitter và single-flight? Có tránh retry token request vô hạn?
6. **Refresh/session:** Refresh token có thời hạn/rotation hoặc binding phù hợp? Có idle và absolute limits khi cần?
7. **Revocation:** Khi đổi role, logout, user bị khóa hoặc token/secret bị lộ, AS và RS vô hiệu token nhanh đến mức nào?
8. **Cache:** JWKS và introspection cache có TTL phù hợp, giới hạn bởi `exp` và SLA thu hồi?
9. **Sender protection:** API rủi ro cao có cần DPoP/mTLS? RS có xác minh proof/binding thực sự không?
10. **Security hygiene:** Không ghi token vào log/URL, luôn TLS, lưu credential trong kho được bảo vệ, có incident-response runbook?
11. **Testing/monitoring:** Có test `exp`/`nbf`/`iat`, clock skew, cross-audience, key rotation, concurrent refresh và đo thời gian thu hồi thực tế?

### Câu hỏi tự kiểm tra

**1. JWT được ký đúng nhưng đã hết `exp`. Có thể chấp nhận vì chữ ký vẫn hợp lệ không?**

Không. Kiểm tra chữ ký và thời gian là hai điều kiện độc lập. Hết hạn ngoài dung sai hợp lệ phải bị từ chối.

**2. Access token sống 5 phút có bảo đảm kẻ đánh cắp không thể dùng token không?**

Không. Kẻ tấn công có thể phát lại ngay trong khoảng hiệu lực. TTL chỉ làm giảm thời gian sử dụng sau khi lộ.

**3. Refresh token giúp lấy access token mới, vậy tại sao còn cần giới hạn thời hạn refresh token?**

Vì refresh token có thể kéo dài phiên truy cập. Nếu bị lộ và dùng được vô hạn, access token ngắn hạn không còn giới hạn rủi ro dài hạn; cần rotation/binding, expiry và revocation phù hợp.

**4. Token đã bị revoke ở AS có nhất thiết bị từ chối ngay bởi RS chỉ xác minh JWT offline không?**

Không. Nếu RS không tra trạng thái/denylist, token còn hợp lệ về chữ ký và `exp` có thể được dùng tới hết hạn.

**5. Có nên đặt clock skew 10 phút để giảm lỗi 401 không?**

Không nên nếu không có lý do chặt chẽ. Dung sai lớn làm rộng cửa sổ chấp nhận token; cần đồng bộ đồng hồ và sửa vấn đề renewal/độ trễ trước.

**6. `auth_time` trong OIDC có giống `iat` của access token vừa refresh không?**

Không. `auth_time` là lúc người dùng được xác thực; `iat` là lúc token đó được phát hành. Refresh token có thể tạo access token mới mà không xác thực lại user.

**7. Access token còn hạn nhưng `aud` là API khác thì sao?**

Resource server phải từ chối. TTL đúng không bù cho lỗi sai audience, scope hoặc loại token.

## Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `exp`, `nbf`, `iat`, NumericDate và leeway.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims và profile access token, gồm thời hạn, issuer và audience.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): `expires_in`, grant types, access/refresh token và client credentials.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): rủi ro bearer, truyền access token và lỗi `invalid_token`.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token tại authorization server.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái `active` và metadata token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo vệ OAuth, refresh token và giảm token replay.
- [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705): certificate-bound access tokens.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): proof-of-possession cho access token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `auth_time`, `max_age` và ngữ nghĩa xác thực end-user.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT validation và resource-server configuration.
- [Spring Authorization Server — Core Model / TokenSettings](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): phát hành token và thiết lập TTL theo client.

**Điểm cần nhớ:** **Giới hạn thời gian sống** thu hẹp cửa sổ bearer token bị đánh cắp có thể được sử dụng, nhưng không làm token miễn nhiễm với replay. Hệ thống an toàn phải cấp **access token ngắn hạn theo rủi ro**, xác minh `exp`/`nbf`/`iat` và audience/scope đúng, đặt clock skew nhỏ, quản lý refresh/session theo chính sách riêng, thiết kế thu hồi thực tế cho JWT hoặc opaque, bảo vệ token khi truyền/lưu và đo thời gian chấp nhận token trong vận hành.
