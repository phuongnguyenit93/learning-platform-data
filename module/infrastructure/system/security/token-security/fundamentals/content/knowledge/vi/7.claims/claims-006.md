# Issued-at, expiration và not-before

## 1. Ba mốc thời gian trả lời ba câu hỏi khác nhau

Trong chương **Claims** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, ba claim thời gian thường gặp của JSON Web Token (JWT) là:

| Claim | Tên đầy đủ | Câu hỏi nó trả lời | Tác dụng chính |
|---|---|---|---|
| `iat` | **Issued At** | Token được phát hành vào lúc nào? | Ghi lại thời điểm phát hành; có thể hỗ trợ giới hạn tuổi token, phát hiện dữ liệu thời gian bất thường |
| `nbf` | **Not Before** | Từ lúc nào token **mới được phép** sử dụng? | Ngăn token được chấp nhận trước thời điểm bắt đầu hiệu lực |
| `exp` | **Expiration Time** | Từ lúc nào token **không còn được phép** sử dụng? | Giới hạn thời gian token được chấp nhận |

Ba claim này kết hợp để mô tả vòng đời sử dụng token, nhưng **không đồng nghĩa**:

- Token **đã được phát hành** không có nghĩa nó **đã bắt đầu có hiệu lực**.
- Token **chưa hết hạn** không có nghĩa nó **được phép sử dụng ngay**.
- Token **đang nằm trong khoảng thời gian hợp lệ** cũng chưa chắc **được phép truy cập API**, vì API còn phải xác minh chữ ký/nguồn gốc, issuer, audience, loại token, scope và quyền trên tài nguyên.

Chẳng hạn, Authorization Server có thể phát hành token lúc 10:00 (`iat`), đặt token chỉ được dùng từ 10:05 (`nbf`) và hết hạn lúc 10:15 (`exp`). Từ 10:00 đến trước 10:05, token đã tồn tại nhưng **chưa sử dụng được**.

**Mục tiêu bài học:** đọc đúng ba claim, xác định các điều kiện biên, xử lý lệch đồng hồ, áp dụng chúng trong OAuth 2.0/OIDC, và nhận diện vì sao token hết hạn, thu hồi hoặc bị phát lại là những vấn đề liên quan nhưng **khác nhau**.

## 2. NumericDate: đơn vị và mốc thời gian chuẩn

Theo [RFC 7519](https://www.rfc-editor.org/rfc/rfc7519), `iat`, `nbf` và `exp` sử dụng kiểu **NumericDate**: số giây tính từ **1970-01-01T00:00:00Z (UTC)** theo quy ước POSIX time, không tính giây nhuận theo cách biểu diễn này.

Một số đặc điểm cần nhớ:

1. Đơn vị chuẩn của NumericDate là **giây**, không phải mili giây.
2. Giá trị là **số** JSON; RFC cho phép giá trị **không nguyên**, dù nhiều hệ thống thực tế dùng số giây nguyên.
3. Mốc thời gian là thời điểm tuyệt đối theo UTC; múi giờ cục bộ chỉ ảnh hưởng cách **hiển thị**.
4. Các giá trị thời gian trong payload **chưa đáng tin** nếu JWT chưa được xác minh theo đúng issuer, chữ ký và các quy tắc liên quan.

Ví dụ:

~~~json
{
  "iat": 1893492000,
  "nbf": 1893492000,
  "exp": 1893492900
}
~~~

Các mốc trên tương ứng:

| Claim | NumericDate | UTC |
|---|---:|---|
| `iat` | `1893492000` | 2030-01-01 10:00:00Z |
| `nbf` | `1893492000` | 2030-01-01 10:00:00Z |
| `exp` | `1893492900` | 2030-01-01 10:15:00Z |

Token có khoảng thời gian sống theo lịch phát hành là `exp - iat = 900` giây, tức **15 phút**. Đây chỉ là ví dụ; thời gian sống phù hợp phụ thuộc chính sách và mức rủi ro của hệ thống.

### 2.1. Sai đơn vị: lỗi rất phổ biến

~~~javascript
// Minh họa JavaScript: Date.now() trả về mili giây.
const nowMilliseconds = Date.now();
const nowSeconds = Math.floor(nowMilliseconds / 1000);

// NumericDate là giây.
const isExpired = nowSeconds >= payload.exp;
~~~

Nếu so sánh thẳng `Date.now()` với `exp` theo giây, access token có thể bị đánh giá **đã hết hạn ngay**. Ngược lại, nếu hệ thống ghi timestamp mili giây vào claim chuẩn `exp`, token có thể bị coi còn hiệu lực trong một khoảng thời gian cực dài.

Không sửa lỗi bằng cách đoán đơn vị theo độ dài chuỗi khi xác minh một token không đáng tin. Tốt nhất là **phát hành và kiểm tra đúng NumericDate theo hợp đồng**, giới hạn định dạng đầu vào và từ chối các giá trị bất thường.

### 2.2. Thời gian tương đối và thời gian tuyệt đối

Các dữ liệu sau khác nhau:

~~~text
iat        = 1893492000      # mốc tuyệt đối UTC, theo giây
exp        = 1893492900      # mốc tuyệt đối UTC, theo giây
expires_in = 900             # khoảng thời gian tương đối, theo giây
~~~

Trong phản hồi token OAuth 2.0, `expires_in` thông thường cho client biết access token còn hiệu lực bao lâu kể từ khi phản hồi được tạo. Nó **không phải một claim JWT `exp`**, dù Authorization Server có thể dùng chúng để biểu diễn cùng chính sách thời gian. Resource server phải dựa vào cơ chế xác minh token được cấu hình, không tin `expires_in` do client tự gửi.

## 3. `iat`: token được phát hành khi nào?

**Issued At (`iat`)** xác định thời điểm token được phát hành. RFC 7519 cho phép bên nhận sử dụng claim này để xác định **tuổi token**.

Ví dụ, Authorization Server phát hành token lúc 10:00:

~~~json
{
  "iat": 1893492000
}
~~~

Lúc 10:08, nếu thời gian đã được kiểm tra đúng, token đã được phát hành khoảng **8 phút** trước đó.

### 3.1. `iat` không tự tạo hiệu lực

Điểm dễ nhầm:

- `iat=10:00` **không có nghĩa** token được phép sử dụng kể từ 10:00; `nbf` có thể là 10:05.
- `iat=10:00` **không cho biết** khi nào token hết hạn; cần `exp` hoặc chính sách thời hạn khác được xác định.
- `iat` **không phải** thời điểm người dùng nhập mật khẩu hoặc hoàn thành xác thực. Trong OIDC, `auth_time` là claim có ý nghĩa riêng về thời gian xác thực người dùng khi được phát hành.
- `iat` **không tự chứng minh** token còn hoạt động, chưa bị thu hồi hoặc được cấp quyền trên một tài nguyên cụ thể.

### 3.2. Có nên từ chối token với `iat` ở tương lai?

RFC 7519 không đặt một phép so sánh thời gian bắt buộc cho `iat` giống như đối với `exp` và `nbf`. Tuy nhiên, hệ thống có thể **bổ sung policy**: nếu `iat` lớn hơn thời gian hiện tại quá mức lệch đồng hồ cho phép, token là dữ liệu thời gian đáng ngờ và nên bị từ chối.

Ví dụ:

~~~text
now = 10:00:00
iat = 11:00:00
clockSkewAllowed = 30 giây

=> DENY theo policy vì iat cách hiện tại 1 giờ.
~~~

Nếu hai máy chỉ lệch nhau vài giây, cho phép mức tolerance nhỏ đã cấu hình có thể tránh từ chối nhầm. **Không tăng độ lệch cho phép lên nhiều phút/giờ chỉ để che lỗi đồng bộ đồng hồ**.

### 3.3. `iat` giúp kiểm soát tuổi token

Một API nhạy cảm có thể đặt chính sách **tuổi tối đa** cho token, ví dụ không chấp nhận access token được phát hành quá lâu trước thời điểm request. Khi có cả `iat` và `exp`, API cũng có thể kiểm tra **lifetime được cấp**:

~~~text
maxAllowedLifetime = 15 phút
issuedAt           = 10:00
expiresAt          = 12:00

=> DENY theo policy: issuer đã cấp token sống 2 giờ,
   vượt thời lượng mà API cho phép đối với loại token này.
~~~

Chỉ kiểm tra `exp` có thể khiến một JWT sống quá lâu vẫn được chấp nhận. Nhưng policy thời lượng phải phù hợp issuer, audience và loại grant; **không phải mọi loại token đều phải có cùng TTL**.

## 4. `exp`: thời điểm token hết hiệu lực

**Expiration Time (`exp`)** quy định mốc mà tại đó hoặc sau đó JWT **không được chấp nhận để xử lý**.

Theo điều kiện chuẩn, không xét lệch đồng hồ:

~~~text
Nếu now < exp  => chưa hết hạn.
Nếu now >= exp => hết hạn, phải từ chối.
~~~

**Ranh giới là phép so sánh nghiêm ngặt.** Tại đúng thời điểm `exp`, token đã hết hạn, không phải vẫn còn hợp lệ trong giây đó.

Ví dụ với `exp=10:15:00`:

| Thời điểm nhận request (UTC) | Kiểm tra `exp` khi không có leeway | Kết quả điều kiện hết hạn |
|---|---|---|
| 10:14:59 | `now < exp` | Chưa hết hạn |
| 10:15:00 | `now == exp` | **Hết hạn** |
| 10:15:01 | `now > exp` | **Hết hạn** |

Việc chưa hết hạn **chưa đủ** để cho phép request: token có thể còn bị từ chối vì sai issuer, sai audience, thiếu scope, chưa đến `nbf`, đã bị thu hồi hoặc không đủ quyền nghiệp vụ.

### 4.1. Không sửa thủ công `exp` của JWT

Với JWT được ký, thay payload `exp` rồi ghép lại các phần của chuỗi sẽ làm **chữ ký không còn hợp lệ**. Client không thể gia hạn một access token có chữ ký chỉ bằng cách sửa con số hoặc giải mã rồi mã hóa lại payload.

Để tiếp tục truy cập, client phải nhận token mới qua **luồng cấp token hợp lệ**, chẳng hạn làm mới token ở Authorization Server khi có refresh token còn hợp lệ hoặc thực hiện lại luồng ủy quyền khi cần.

### 4.2. `exp` không tương đương thu hồi

`exp` cung cấp **giới hạn thời gian**. Một token có thể cần bị thu hồi **trước mốc đó** khi người dùng đăng xuất, tài khoản bị khóa, quyền thay đổi hoặc credential bị nghi ngờ lộ.

Với JWT access token được resource server xác minh **offline**, issuer có thể thu hồi refresh token nhưng JWT access token đã phát hành vẫn được chấp nhận đến `exp` nếu resource server **không có** cơ chế kiểm tra trạng thái bổ sung.

Với opaque access token được kiểm tra qua **introspection**, thay đổi trạng thái có thể được nhìn thấy sớm hơn, phụ thuộc thời gian cache và hợp đồng giữa Authorization Server với resource server.

**Hết hạn là điều kiện thời gian; thu hồi là thay đổi trạng thái.** Cần thiết kế cả hai khi nghiệp vụ yêu cầu.

## 5. `nbf`: token chưa được dùng trước thời điểm nào?

**Not Before (`nbf`)** xác định mốc mà trước đó JWT **không được chấp nhận để xử lý**.

Theo điều kiện chuẩn, không xét lệch đồng hồ:

~~~text
Nếu now < nbf  => chưa có hiệu lực, phải từ chối.
Nếu now >= nbf => đã tới thời điểm bắt đầu hiệu lực.
~~~

Ví dụ:

~~~json
{
  "iat": 1893492000,
  "nbf": 1893492300,
  "exp": 1893492900
}
~~~

Authorization Server đã **phát hành** token vào 10:00, nhưng token chỉ **bắt đầu được sử dụng** từ 10:05 và **hết hạn** vào 10:15.

| Thời điểm | Kết quả `nbf` (không có leeway) | Kết quả `exp` | Kết luận thời gian |
|---|---|---|---|
| 10:04:59 | Chưa đến `nbf` | Chưa hết hạn | **DENY** |
| 10:05:00 | Đã đến `nbf` | Chưa hết hạn | Có thể được chấp nhận theo thời gian |
| 10:14:59 | Đã đến `nbf` | Chưa hết hạn | Có thể được chấp nhận theo thời gian |
| 10:15:00 | Đã đến `nbf` | Hết hạn | **DENY** |

Các trường hợp sử dụng `nbf` có thể gồm token được chuẩn bị để bắt đầu hiệu lực ở thời điểm đã hẹn, token trao cho công việc chỉ được phép chạy từ một mốc xác định hoặc tình huống cần phân biệt phát hành và hiệu lực. **Không nên dùng `nbf` thay scheduler hay hệ thống phân quyền nghiệp vụ**: token có hiệu lực theo thời gian vẫn phải kiểm tra action/resource.

### 5.1. `nbf` không cần trùng `iat`

- `iat < nbf`: token đã phát hành trước khi được phép dùng, là trường hợp hợp lệ tùy chính sách.
- `iat = nbf`: token có thể dùng ngay từ thời điểm phát hành.
- `iat > nbf`: có thể xuất hiện theo cách issuer định nghĩa hoặc do lỗi đồng hồ; cần xem xét policy và tính hợp lý. Không tự suy diễn một thứ tự bắt buộc cho mọi JWT nếu hợp đồng token không quy định.

**Trường hợp `nbf >= exp`** không có khoảng thời gian hiệu lực bình thường khi không xét skew và nên bị từ chối theo policy vì các mốc mâu thuẫn.

## 6. Nhìn ba claim trên cùng một trục thời gian

~~~mermaid
flowchart LR
    A["10:00:00<br/>iat: phát hành"] --> B["10:05:00<br/>nbf: bắt đầu hiệu lực"]
    B --> C["10:15:00<br/>exp: hết hạn"]
    A -. "Chưa được sử dụng" .-> B
    B -. "Có thể sử dụng nếu các kiểm tra khác đạt" .-> C
    C --> D["Sau 10:15:00<br/>Không chấp nhận"]
~~~

*Trục thời gian minh họa, tất cả là UTC và chưa tính leeway.*

Để đánh giá khoảng hợp lệ về thời gian khi cả `nbf` và `exp` hiện diện:

~~~text
timeAllowed = (now >= nbf) AND (now < exp)
~~~

Khi chỉ có `exp`, việc không có `nbf` có nghĩa **không có ràng buộc not-before từ claim đó**, chứ không có nghĩa token được miễn kiểm tra issuer, chữ ký và chính sách khác. Khi có `iat`, nó mô tả thời điểm phát hành, **không tự thay thế** `nbf`.

### 6.1. Tại sao "token còn 5 phút" có thể gây hiểu nhầm?

Một client đọc `exp` và thấy token chưa hết hạn. Nhưng token có thể:

1. Chưa đến `nbf`.
2. Bị issuer/resource server thu hồi.
3. Có audience dành cho API khác.
4. Thiếu scope cho hành động.
5. Không còn quyền trên đối tượng vì membership/ownership đã thay đổi.

Do đó, trên UI có thể hiển thị thời gian token dự kiến còn lại, nhưng **API phải tự xác minh** token và phân quyền. Không đặt niềm tin vào đếm ngược do trình duyệt tính.

## 7. Clock skew (lệch đồng hồ) và leeway

Trong hệ thống phân tán, thời gian của Authorization Server, API Gateway, các resource server và client **có thể lệch nhau** vài giây. Ngay cả khi chúng sử dụng NTP hoặc hệ thống đồng bộ thời gian khác, vẫn có sai số, độ trễ mạng và thời điểm xử lý khác nhau.

RFC 7519 cho phép bên xác minh sử dụng **mức leeway nhỏ** để tính đến clock skew, thường ở mức **không quá vài phút**, tùy môi trường. Đó là **quyền cấu hình**, không phải yêu cầu phải bỏ qua lỗi hết hạn.

Giả sử hệ thống cho phép leeway `L = 30 giây`. Có thể hình dung phép kiểm tra thời gian:

~~~text
Chấp nhận điều kiện not-before nếu:
    now + L >= nbf

Chấp nhận điều kiện expiration nếu:
    now - L < exp
~~~

Với NumericDate thực, cần xử lý đúng kiểu số và biên theo thư viện; biểu thức trên dùng để giải thích cửa sổ dung sai. **Leeway cũng làm rộng khoảng chấp nhận**: có thể cho token được dùng sớm tối đa 30 giây trước `nbf` hoặc muộn tối đa 30 giây sau `exp`.

| Trường hợp | Không leeway | Leeway 30 giây |
|---|---|---|
| Còn 20 giây mới đến `nbf` | DENY | Có thể PASS điều kiện `nbf` |
| Đã qua `exp` 20 giây | DENY | Có thể PASS điều kiện `exp` |
| Còn 2 phút mới đến `nbf` | DENY | DENY |
| Đã qua `exp` 2 phút | DENY | DENY |

**Hạn chế leeway** theo threat model, đồng bộ đồng hồ máy chủ và giám sát độ lệch. Không dùng giá trị vài giờ chỉ để giúp ứng dụng xử lý kém. Với những nghiệp vụ yêu cầu mốc cứng, cần đặt tolerance và chính sách xử lý phù hợp hơn.

### 7.1. Lệch đồng hồ và độ trễ mạng

Giả sử token có `nbf=10:00:00`. Issuer phát hành đúng, nhưng API chạy đồng hồ chậm 12 giây. Khi request đến, API nghĩ hiện tại là `09:59:48` và có thể từ chối token mới nếu kiểm tra cứng. Một leeway nhỏ giúp tránh lỗi do chênh lệch không đáng kể.

Ngược lại, nếu API chạy nhanh 20 giây, nó có thể từ chối sớm token sắp `exp`. Client chủ động lấy token mới **trước** khi chạm expiry có thể cải thiện trải nghiệm, nhưng không thay thế việc resource server xác minh token.

### 7.2. Không để client quyết định thời gian đáng tin

Đồng hồ trình duyệt hoặc điện thoại có thể bị người dùng chỉnh sửa và không thuộc ranh giới tin cậy của resource server. Client dùng đồng hồ của nó để **dự đoán khi nào nên refresh**, còn **quyết định chấp nhận credential** phải được resource server thực hiện bằng thời gian hệ thống đáng tin cậy của nó.

## 8. Kiểm tra thời gian trong chuỗi xác minh JWT

Không nên viết logic kiểu "decode Base64, lấy exp và kiểm tra, nếu còn hạn thì tin". Payload JWT có thể được đọc mà không cần khóa ký; kẻ tấn công có thể tự tạo `exp` xa trong tương lai.

Một resource server cần thực hiện những nhóm kiểm tra sau, theo profile và hợp đồng với issuer:

1. **Xác thực token:** với signed JWT, giới hạn thuật toán ký được phép và xác minh chữ ký bằng khóa của issuer đã cấu hình tin cậy; với opaque token, dùng cơ chế kiểm tra/introspection đáng tin.
2. **Xác minh ngữ cảnh:** `iss` phải khớp issuer được phép; `aud` phải chỉ API hiện tại; token phải đúng loại (không nhận OIDC ID token làm access token).
3. **Xác minh thời gian:** `exp` chưa qua, `nbf` đã đến; `iat` và thời lượng sống phải phù hợp policy/profile.
4. **Xác minh quyền:** scope, client/principal type, tenant, role/permissions và quyền trên **resource/action cụ thể**.
5. **Xử lý trạng thái:** kiểm tra revocation/active, session hoặc policy quyền động khi kiến trúc yêu cầu.

Các bước có thể được thư viện tích hợp trong một pipeline; thứ tự liệt kê nhằm nhấn mạnh **không sử dụng claims chưa xác thực làm căn cứ cấp quyền**. `kid` trong header chỉ hỗ trợ chọn khóa trong tập khóa đáng tin, không phải nguồn tin cậy độc lập.

### 8.1. Không phải JWT nào cũng yêu cầu ba claim

**RFC 7519** mô tả `iat`, `nbf`, `exp` là các claim đăng ký, nhưng **không bắt buộc tất cả JWT phải có đủ cả ba**. Việc claim nào là bắt buộc phụ thuộc **profile token, use case và contract của issuer/resource server**.

Ví dụ:

| Token/profile | Quy tắc thời gian cần lưu ý |
|---|---|
| **JWT nói chung (RFC 7519)** | `exp`, `nbf`, `iat` là các claim tùy chọn theo chuẩn JWT cơ sở; ứng dụng có thể quy định chặt hơn |
| **JWT OAuth 2.0 access token theo RFC 9068** | Profile có yêu cầu các claim như `exp`, `iat` cùng những claim bắt buộc khác; `nbf` không bắt buộc |
| **OIDC ID token** | Có các claim như `exp`, `iat` bắt buộc theo OIDC; client xác minh các điều kiện OIDC, không dùng ID token để gọi resource server |
| **Opaque access token** | Resource server không đọc JWT NumericDate; kiểm tra thời hạn/trạng thái theo introspection hoặc hợp đồng phía issuer |
| **Refresh token** | Thường là secret không cần giải mã; hiệu lực/thu hồi do Authorization Server quản lý, không giả định có JSON claims `iat/nbf/exp` đọc được |

Nếu resource server yêu cầu JWT access token theo RFC 9068, việc thiếu `exp` hoặc `iat` không thể được bỏ qua chỉ vì một thư viện JWT tổng quát chấp nhận claim tùy chọn. **Phải xác minh theo đúng profile**, không chỉ theo kiểm tra mặc định của một parser bất kỳ.

### 8.2. Các bất biến nên kiểm tra theo chính sách

Với JWT access token có cả ba claim, những ràng buộc thường hữu ích:

~~~text
exp hiện diện và có kiểu NumericDate hợp lệ
iat hiện diện nếu token profile yêu cầu
now < exp (có leeway nhỏ nếu được cấu hình)
now >= nbf nếu nbf hiện diện (có leeway nhỏ nếu được cấu hình)
iat <= now + allowedFutureSkew  (nếu policy yêu cầu)
exp > iat                     (nếu profile dùng iat để kiểm tra TTL)
nbf < exp                     (nếu nbf có mặt)
exp - iat <= maximumTokenTTL  (nếu policy giới hạn thời gian sống)
~~~

**Phân biệt quy tắc chuẩn với policy tùy chọn:** điều kiện thời gian của `exp` và `nbf` xuất phát từ ý nghĩa JWT; các ràng buộc như `iat` ở tương lai, `exp > iat` hay TTL tối đa là **quy tắc ứng dụng/profile bổ sung**. Khi thiếu claim bắt buộc, loại không đúng, hoặc thời gian quá vô lý, resource server nên từ chối theo contract.

## 9. Ví dụ Java: đọc NumericDate và kiểm tra policy

### 9.1. Chuyển NumericDate sang `Instant`

~~~java
import java.time.Instant;

long issuedAtSeconds = 1893492000L;
Instant issuedAt = Instant.ofEpochSecond(issuedAtSeconds);

System.out.println(issuedAt); // 2030-01-01T10:00:00Z
~~~

`Instant` biểu diễn mốc tuyệt đối nên không phụ thuộc timezone trình bày. Cẩn thận với `System.currentTimeMillis()` vì nó trả **mili giây**; nếu so sánh với claim seconds, cần chuyển đơn vị hoặc dùng trực tiếp `Instant.now()`.

### 9.2. Ví dụ validator thời gian mang tính khái niệm

~~~java
import java.time.Duration;
import java.time.Instant;

// Pseudocode: VerifiedClaims chỉ tồn tại SAU bước xác minh
// chữ ký, issuer, audience và token profile phù hợp.
boolean timePolicyAllows(VerifiedClaims claims, Instant now) {
    Instant exp = claims.expiration();
    Instant nbf = claims.notBefore(); // có thể null nếu profile cho phép
    Instant iat = claims.issuedAt();  // profile này yêu cầu iat
    Duration skew = Duration.ofSeconds(30);
    Duration maxTtl = Duration.ofMinutes(15);

    if (exp == null || iat == null) return false;
    if (!now.minus(skew).isBefore(exp)) return false;
    if (nbf != null && now.plus(skew).isBefore(nbf)) return false;

    // Các kiểm tra dưới đây là policy bổ sung.
    if (iat.isAfter(now.plus(skew))) return false;
    if (!exp.isAfter(iat)) return false;
    if (nbf != null && !nbf.isBefore(exp)) return false;
    if (Duration.between(iat, exp).compareTo(maxTtl) > 0) return false;

    return true;
}
~~~

**Đây là pseudocode để học, không phải một validator JWT production hoàn chỉnh**. Hàm giả định claims đã được thư viện xác thực, kiểu dữ liệu thời gian đã được kiểm tra, và chính sách yêu cầu `iat` cùng TTL 15 phút. Hệ thống thật cần dùng thư viện JWT/OAuth được duy trì, tránh tự xây parser/chữ ký/clock logic.

Với các profile hoặc đường đi khác, cách áp `iat`, TTL, clock skew, xử lý null và metadata sẽ khác. Không được nhận token bằng cách đơn thuần gọi hàm trên một payload do client tự giải mã.

### 9.3. Spring Security Resource Server kiểm tra `exp` và `nbf`

Spring Security cung cấp **`JwtTimestampValidator`** để kiểm tra thời gian JWT và cho phép cấu hình clock skew. Ví dụ khái niệm:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

// Validator tích hợp vào chuỗi xác minh JwtDecoder của resource server.
JwtTimestampValidator timestampValidator =
    new JwtTimestampValidator(Duration.ofSeconds(30));
~~~

Để triển khai đầy đủ, cần kết hợp timestamp validator với kiểm tra issuer, audience, token type và các claim bắt buộc theo profile. **Không thay thế toàn bộ chuỗi validator hiện có chỉ bằng timestamp validator.** Nếu cấu hình `issuer-uri`, hãy xác nhận phiên bản và cấu hình của hệ thống đang kiểm tra **audience của API**; issuer và thời gian đúng không tự đồng nghĩa audience đúng.

Ví dụ mô hình cấu hình:

~~~text
TrustedIssuer:
    https://login.example.com/realms/shop
ExpectedAudience:
    https://orders.example.com
AcceptedTokenProfile:
    OAuth2 JWT access token (ví dụ RFC 9068)
ClockSkewTolerance:
    30 seconds
MaximumAccessTokenTTL:
    theo policy của Orders API
~~~

Sau khi xác thực token, một endpoint vẫn phải kiểm tra quyền trên tài nguyên:

~~~java
// Pseudocode minh họa; verifiedJwt đã qua JwtDecoder/validators.
Order getOrder(VerifiedJwt verifiedJwt, String orderId) {
    requireScope(verifiedJwt, "orders:read");
    Order order = orderRepository.findById(orderId);
    requireOwnershipOrDelegatedAccess(verifiedJwt.principal(), order);
    return order;
}
~~~

**`exp`/`nbf` giải quyết khoảng hiệu lực của credential, không giải quyết ownership.**

## 10. Token hết hạn, thu hồi và phát lại: ba cơ chế khác nhau

### 10.1. Hết hạn

Token hết hạn vì **thời gian hiện tại đạt đến hoặc vượt `exp`**, hoặc vì thời hạn trong hệ thống introspection đã kết thúc. Đây là điều kiện thường được kiểm tra ở mọi request.

### 10.2. Thu hồi

Token bị thu hồi vì issuer hoặc hệ thống vận hành thay đổi trạng thái trước khi hết hạn, ví dụ người dùng bị khóa hoặc cần ứng cứu sự cố.

Đối với signed JWT được kiểm tra offline, resource server cần cơ chế trạng thái bổ sung như kiểm tra session/token version, denylist theo `jti` hoặc kiến trúc có introspection nếu yêu cầu thu hồi tức thời. Đối với opaque access token, introspection có thể cung cấp kết quả `active=false`, tùy cache.

`iat` có thể hỗ trợ một chính sách như **không nhận token phát hành trước mốc đổi mật khẩu hoặc mốc hủy phiên**, nếu dữ liệu phiên và chủ thể được kiểm tra tin cậy; tuy nhiên **chỉ có `iat` không tự tạo chức năng thu hồi**.

### 10.3. Phát lại (replay)

Người tấn công lấy được bearer access token còn hạn và gửi lại token đó trong khoảng cho phép. Việc `iat`, `nbf`, `exp` hoàn toàn hợp lệ **không phân biệt được** bên gửi có phải chủ thể được phép sử dụng credential hay không.

Biện pháp giảm rủi ro:

- Dùng HTTPS/TLS, không ghi access token/refresh token vào log, URL hoặc analytics.
- Giới hạn audience, scope và TTL để giảm phạm vi/tần suất lạm dụng.
- Bảo vệ refresh token, giới hạn đời sống/rotation và phát hiện reuse khi chính sách áp dụng.
- Khi phù hợp, dùng **sender-constrained access token**, chẳng hạn **DPoP (RFC 9449)** hoặc **mTLS certificate-bound access token (RFC 8705)**, giúp giảm khả năng token bị đánh cắp được sử dụng bởi bên không giữ khóa/chứng chỉ tương ứng.
- Với tác vụ nhạy cảm, có thể dùng nonce, `jti` hoặc cơ chế chống replay riêng theo protocol và threat model. **Chỉ xuất hiện `jti` không tự ngăn replay**; phải có trạng thái/kiểm tra sử dụng tương ứng.

**Chữ ký JWT** bảo vệ tính toàn vẹn và nguồn phát hành theo khóa đáng tin; nó **không mã hóa** payload mặc định và cũng không chứng minh người đang cầm bearer token là người dùng gốc.

## 11. Các tình huống đặc biệt trong hệ thống phân tán

### 11.1. Request tới đúng lúc token hết hạn

Token còn hạn khi client bắt đầu gửi request, nhưng đến khi API xác minh thì đã đúng `exp`. Nếu không có leeway, API phải từ chối. Client nên chủ động làm mới token **trước một khoảng dự phòng**; resource server vẫn giữ quyền quyết định cuối cùng.

Không nên kéo dài expiry thủ công ở frontend hoặc áp dụng những leeway khác nhau không kiểm soát giữa các service. Nếu một request xử lý lâu sau khi đã được xác thực, cần chính sách riêng về **quyền còn hiệu lực trong quá trình chạy** và các hành động downstream, thay vì mặc định mọi tác vụ kéo dài đều phải dùng lại access token đã hết hạn.

### 11.2. API Gateway và nhiều microservice

Một gateway có thể xác minh token lúc nhận request, sau đó chuyển request sang Orders API. Nếu Orders API tin hoàn toàn vào header caller gửi hoặc vào kết quả xác minh không có ràng buộc giữa các service, có thể xuất hiện lỗi trust boundary.

Cần thống nhất:

- Issuer và audience mà từng resource server chấp nhận.
- Clock skew và nguồn đồng hồ tin cậy.
- Cách chuyển identity context nội bộ có tính toàn vẹn và xác thực nguồn.
- Chính sách kiểm tra lại token/ủy quyền ở từng hop khi hệ thống yêu cầu.
- TTL của các kết quả introspection, session và authorization cache.

Nếu Orders API gọi Billing API, token của Orders API **không tự phù hợp audience của Billing API**. Cần token downstream đúng recipient và policy, chẳng hạn qua client credentials hoặc token exchange/on-behalf-of khi được hỗ trợ.

### 11.3. Queue và scheduled job

Không nên đưa bearer token có TTL ngắn vào queue rồi hy vọng nó vẫn còn hợp lệ khi worker chạy vài giờ sau. Một job cần lưu ngữ cảnh yêu cầu đã được bảo vệ, danh tính và quyền phù hợp, rồi thực hiện lại các kiểm tra cần thiết ở thời điểm xử lý.

`nbf` có thể giới hạn thời điểm credential bắt đầu có hiệu lực, nhưng **không thay lịch thực thi của scheduler**. Một job được hẹn 10:05 không có nghĩa cứ sau 10:05 là tự có quyền đọc mọi tài liệu.

### 11.4. Caching và dữ liệu quyền động

Một cache quyết định "token active" hoặc "principal được phép" có thể làm hệ thống tiếp tục chấp nhận quyền đã thu hồi. Cache phải có TTL và khóa phù hợp với token/principal/resource/action/tenant, cùng chiến lược invalidation khi quyền thay đổi.

Cache không được **bỏ qua mốc `exp`**. Nếu kết quả introspection được cache, thời gian sống cache không nên khiến token hết hạn bị coi là active quá giới hạn chính sách.

## 12. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
|---|---|---|
| Coi `iat` là lúc bắt đầu hiệu lực | Token có thể có `nbf` muộn hơn | Kiểm tra `nbf` độc lập |
| Chấp nhận token tại `now == exp` | Vi phạm điều kiện hết hạn nghiêm ngặt | `now < exp`, có leeway được cấu hình riêng nếu cần |
| Coi `exp` ở tương lai là đủ | Token có thể sai issuer/audience/scope hoặc chưa đến `nbf` | Xác minh toàn bộ token profile và quyền nghiệp vụ |
| So sánh mili giây với NumericDate giây | Hết hạn sai hoặc tồn tại quá lâu | Dùng số giây UTC hoặc `Instant` đúng |
| Chỉ Base64-decode JWT rồi đọc thời gian | Payload có thể bị giả mạo | Xác minh chữ ký và issuer trước khi tin claims |
| Để clock skew nhiều giờ | Mở rộng cửa sổ token bị dùng sớm/muộn | NTP, cảnh báo sai lệch, leeway nhỏ |
| Nhận JWT không có `exp` khi profile bắt buộc | Token có thể không có điểm hết hạn được kiểm soát | Thực thi claims bắt buộc theo profile |
| Dùng `iat` như bằng chứng đăng nhập mới | `iat` là lúc phát hành token, không phải `auth_time` | Dùng cơ chế OIDC/policy xác thực phù hợp |
| Tưởng thu hồi refresh token cũng thu hồi JWT access token offline | Token cũ vẫn có thể hoạt động tới `exp` | Thiết kế kiểm tra trạng thái, TTL và chiến lược revoke |
| Coi token có `jti` thì không phát lại được | Bearer token còn hạn có thể bị dùng lại | Thiết kế chống replay/sender-constrained phù hợp |
| Gia hạn bằng cách sửa `exp` trong JWT | Chữ ký token không còn hợp lệ | Xin token mới qua Authorization Server |
| Chỉ kiểm tra thời gian ở frontend | Client kiểm soát đồng hồ và dữ liệu gửi | Resource server tự kiểm tra ở ranh giới tin cậy |

## 13. Ma trận kiểm thử điều kiện biên

Giả sử policy yêu cầu `iat` và `exp`, `nbf` tùy chọn, clock skew bằng **0** để nhìn rõ ranh giới. Với các hàng có `nbf`, áp dụng `now >= nbf && now < exp`. Những điều kiện khác (chữ ký, issuer, audience, scope) được giả định đã đạt.

| `iat` | `nbf` | `exp` | `now` | Kỳ vọng |
|---|---|---|---|---|
| 10:00 | 10:00 | 10:15 | 10:00:00 | **PASS** điều kiện thời gian |
| 10:00 | 10:05 | 10:15 | 10:04:59 | **DENY** vì chưa tới nbf |
| 10:00 | 10:05 | 10:15 | 10:05:00 | **PASS** điều kiện thời gian |
| 10:00 | 10:00 | 10:15 | 10:14:59 | **PASS** điều kiện thời gian |
| 10:00 | 10:00 | 10:15 | 10:15:00 | **DENY** vì đã tới exp |
| 10:00 | Không có | 10:15 | 10:05:00 | **PASS** nếu profile cho phép thiếu nbf |
| 10:00 | 10:20 | 10:15 | 10:10:00 | **DENY** vì nbf sau exp, mốc mâu thuẫn |
| 11:00 | 10:00 | 10:15 | 10:05:00 | **DENY** theo policy iat tương lai |
| Không có | 10:00 | 10:15 | 10:05:00 | **DENY** nếu profile yêu cầu iat |
| 10:00 | 10:00 | Không có | 10:05:00 | **DENY** nếu profile yêu cầu exp |

Thực hiện thêm các kiểm thử **leeway 30 giây**:

- Request trước `nbf` **20 giây**: có thể được chấp nhận theo chính sách dung sai.
- Request trước `nbf` **40 giây**: phải bị từ chối theo dung sai 30 giây.
- Request sau `exp` **20 giây**: có thể được chấp nhận theo dung sai.
- Request sau `exp` **40 giây**: phải bị từ chối.

Nên có test cho token được phát hành với **giây thay vì mili giây**, thời gian dạng chuỗi sai kiểu, số cực lớn/không hợp lý, trường thiếu, khác múi giờ hiển thị, nhiều issuer và giá trị `iat` ở tương lai.

Với OAuth Bearer, token hết hạn hoặc chưa có hiệu lực thường dẫn đến **401 Unauthorized** với lỗi `invalid_token` khi phù hợp; token đã xác thực nhưng thiếu scope hoặc quyền trên resource thường là **403 Forbidden**. Mã lỗi chi tiết phụ thuộc API contract, nhưng không được dùng lỗi thời gian như một cách cấp quyền mặc định.

## 14. Tình huống suy luận

### Tình huống 1: phát hành trước, dùng sau

Một JWT có `iat=10:00`, `nbf=10:10`, `exp=11:00`. Lúc 10:03, chữ ký đúng và user có quyền trên dữ liệu.

**Có thể cho phép request không?** Không, nếu không có leeway đủ lớn (và không nên có leeway 7 phút chỉ để vượt quy tắc). Token chưa bắt đầu có hiệu lực.

### Tình huống 2: hết hạn đúng giây

JWT có `exp=10:15:00`. API kiểm tra vào `10:15:00`.

**Token còn hợp lệ không?** Không theo quy tắc JWT cơ sở, vì tại thời điểm `exp` token đã hết hạn. Nếu hệ thống có leeway nhỏ thì cần xét theo cấu hình và giới hạn cụ thể.

### Tình huống 3: `iat` trong tương lai

API nhận token có `iat` đi trước thời gian hệ thống 6 giờ, nhưng `nbf` và `exp` lại nằm trong khoảng hiện tại.

**Nên làm gì?** Không tin ngay chỉ vì `nbf`/`exp` phù hợp. Nếu profile/policy yêu cầu tính hợp lý của iat, hãy từ chối giá trị tương lai vượt mức skew cho phép và điều tra lỗi đồng hồ hoặc phát hành token sai.

### Tình huống 4: người dùng vừa đổi mật khẩu

JWT access token được phát hành trước khi đổi mật khẩu, `exp` còn 5 phút. Issuer đã thu hồi refresh token.

**Token access cũ có bị từ chối tự động không?** Không nhất thiết. Resource server kiểm tra JWT offline có thể tiếp tục nhận token đến `exp` nếu không có cơ chế thu hồi hoặc session version bổ sung.

### Tình huống 5: token bị đánh cắp

Kẻ tấn công lấy được bearer access token có chữ ký đúng, `nbf` đã đến và `exp` chưa qua.

**Chỉ ba claim thời gian có đủ ngăn truy cập trái phép không?** Không. Chúng giới hạn cửa sổ thời gian nhưng không chứng minh bên đang cầm bearer token. Cần phòng chống lộ token, giới hạn quyền và cân nhắc cơ chế chống replay hoặc ràng buộc bên gửi phù hợp.

### Tình huống 6: API đọc `exp` nhưng bỏ qua `aud`

JWT có `exp` tương lai và `scope=orders:read`, nhưng `aud` là Payments API.

**Orders API có thể nhận token không?** Không. `exp` còn hiệu lực không cấp quyền dùng token tại resource server sai audience.

### Tình huống 7: cùng mốc NumericDate ở hai múi giờ

API tại Việt Nam hiển thị thời điểm `2030-01-01T10:00:00Z` thành `17:00` cùng ngày theo UTC+7.

**Claim có cần thay đổi thành số giây của giờ địa phương không?** Không. NumericDate đại diện **một thời điểm tuyệt đối**; timezone chỉ là cách hiển thị, không được cộng thêm 7 giờ vào con số epoch.

## 15. Ghi nhớ

Hãy tách ba câu hỏi:

1. **`iat` — Token được phát hành khi nào?** Dùng để hiểu tuổi token và áp các policy bổ sung, không tự định nghĩa bắt đầu hiệu lực hay hết hạn.
2. **`nbf` — Từ lúc nào được dùng?** Trước `nbf`, token chưa hợp lệ về thời gian; tại hoặc sau `nbf`, đã vượt điều kiện bắt đầu.
3. **`exp` — Đến lúc nào phải ngừng chấp nhận?** Tại đúng `exp` hoặc sau đó, token hết hạn theo kiểm tra chuẩn.

Với token có đủ `nbf` và `exp`, điều kiện thời gian khi không có leeway là **`nbf <= now < exp`**. Khi bật leeway, cửa sổ chấp nhận có thể được nới ra nhỏ có kiểm soát.

Trong OAuth 2.0/OIDC, cần hiểu **JWT/opaque** là cách biểu diễn và kiểm tra token, còn **access/ID/refresh token** là các loại credential có mục đích khác nhau. Ba claim thời gian chỉ là **một lớp bảo vệ** trong chuỗi kiểm tra issuer, chữ ký hoặc active state, audience, loại token, scope, quyền trên resource, thu hồi và chống đánh cắp/phát lại.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT), Sections 2 and 4.1.4–4.1.6](https://www.rfc-editor.org/rfc/rfc7519): NumericDate, expiration (`exp`), not-before (`nbf`) và issued-at (`iat`).
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): các claim bắt buộc và quy tắc xác minh JWT access token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `exp`, `iat`, `auth_time` và cách client kiểm tra ID token.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): vòng đời access token, `expires_in`, refresh token và vai trò Authorization Server.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): gửi bearer access token và thông báo lỗi token không hợp lệ.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): active state và các thuộc tính token được Authorization Server công bố.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh JWT an toàn.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ access token/refresh token và giới hạn vòng đời.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained token để giảm rủi ro replay.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình resource server và JWT validation.
