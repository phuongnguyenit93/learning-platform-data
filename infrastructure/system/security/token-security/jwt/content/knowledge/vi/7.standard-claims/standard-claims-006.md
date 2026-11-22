# `iat`: Thời điểm phát hành JWT và chính sách tuổi tối đa

## 1. `iat` biểu thị điều gì?

Trong JSON Web Token (JWT), **`iat` (Issued At)** là *registered claim* xác định thời điểm token được phát hành. Claim này cho biết token được tạo ra vào lúc nào theo đồng hồ của bên phát hành.

Theo [RFC 7519, mục 4.1.6](https://www.rfc-editor.org/rfc/rfc7519#section-4.1.6), giá trị `iat` là một `NumericDate`. Claim này có thể được dùng để xác định tuổi của JWT. Bản thân `iat` không làm token bắt đầu có hiệu lực, không đặt thời điểm hết hạn và cũng không chứng minh rằng người dùng vừa xác thực tại thời điểm đó.

Ví dụ payload:

```json
{
  "iss": "https://identity.example.com/",
  "sub": "user-7821",
  "aud": "https://api.example.com/inventory",
  "iat": 1893452400,
  "exp": 1893456000
}
```

Trong ví dụ, `iat` ghi nhận thời điểm phát hành; `exp` đặt thời điểm hết hạn. Hai claim trả lời hai câu hỏi khác nhau:

- `iat`: Token được phát hành lúc nào?
- `exp`: Token không còn được chấp nhận từ thời điểm nào?

`iat` giúp bên nhận đánh giá token mới hay cũ theo một chính sách tuổi tối đa. Điều này có thể hữu ích khi hệ thống muốn giới hạn thời gian một token được sử dụng, kể cả khi `exp` được đặt xa hơn.

## 2. `iat` sử dụng NumericDate

Giá trị `iat` phải là **NumericDate** theo định nghĩa tại [RFC 7519, mục 2](https://www.rfc-editor.org/rfc/rfc7519#section-2). NumericDate là số giây tính từ Unix epoch:

```text
1970-01-01T00:00:00Z
```

Đây là mốc UTC, bỏ qua giây nhuận. NumericDate có thể là số nguyên hoặc số không nguyên để biểu diễn phần lẻ của giây.

Ví dụ:

```json
{
  "iat": 1893452400
}
```

Một số dạng dữ liệu cần phân biệt:

| Giá trị JSON | Đánh giá | Lý do |
| --- | --- | --- |
| `1893452400` | Hợp lệ về kiểu | NumericDate dạng số nguyên, đơn vị giây |
| `1893452400.5` | Hợp lệ về kiểu | NumericDate có phần lẻ của giây |
| `"1893452400"` | Không hợp lệ | Chuỗi JSON, không phải giá trị số |
| `null` | Không hợp lệ | Không phải NumericDate |
| `true` | Không hợp lệ | Boolean không phải NumericDate |
| `{ "seconds": 1893452400 }` | Không hợp lệ | Object không phải NumericDate |

Không tự ép chuỗi thành số và không tự đoán đơn vị dựa trên độ lớn. Một giá trị phát hành nhầm theo mili giây vẫn có kiểu JSON là number; chỉ kiểm tra kiểu dữ liệu không thể xác định chắc chắn lỗi đơn vị. Bên phát hành và bên nhận phải thống nhất NumericDate theo giây, kiểm thử dữ liệu và có thể áp dụng giới hạn hợp lý theo chính sách. Không âm thầm chia cho 1.000 theo phỏng đoán.

Nếu đồng hồ của hệ thống cung cấp thời gian theo mili giây, cần chuyển về giây trước khi so sánh:

```text
nowEpochSeconds = currentUnixTimeMilliseconds / 1000
```

Không so sánh trực tiếp `iat` theo giây với thời gian hiện tại theo mili giây. Cũng cần giữ đủ độ chính xác nếu hệ thống dùng NumericDate có phần lẻ của giây.

## 3. `iat` là thời điểm phát hành, không phải thời điểm xác thực người dùng

Đây là khác biệt quan trọng khi sử dụng JWT trong hệ thống đăng nhập.

`iat` cho biết **token hiện tại được phát hành khi nào**. Nó không nhất thiết cho biết:

- Người dùng đã nhập mật khẩu hoặc hoàn tất xác thực lúc nào.
- Người dùng đã thực hiện MFA lúc nào.
- Phiên đăng nhập bắt đầu lúc nào.
- Người dùng đã tương tác gần nhất với ứng dụng lúc nào.

Ví dụ, người dùng đăng nhập lúc 08:00 và nhận refresh token. Đến 10:00, client dùng refresh token để xin access token mới. Access token mới có `iat` gần 10:00, dù lần xác thực người dùng gần nhất vẫn diễn ra lúc 08:00.

Nếu hệ thống cần xác minh **độ mới của lần xác thực**, phải sử dụng thông tin phù hợp với giao thức. Trong OpenID Connect, claim `auth_time` biểu thị thời điểm người dùng được xác thực; khi yêu cầu xác thực gần đây bằng `max_age`, client kiểm tra `auth_time` theo quy tắc của OpenID Connect. Không dùng `iat` thay thế `auth_time`.

| Thông tin | Ý nghĩa | Không nên diễn giải thành |
| --- | --- | --- |
| `iat` | Thời điểm token được phát hành | Thời điểm người dùng đăng nhập hoặc MFA |
| `auth_time` (OpenID Connect) | Thời điểm người dùng được xác thực | Thời điểm access token hiện tại được tạo |
| Thời điểm bắt đầu phiên | Theo mô hình quản lý phiên của hệ thống | Thời điểm phát hành của mọi token trong phiên |
| Thời điểm hoạt động gần nhất | Lần tương tác được hệ thống ghi nhận | Thời điểm phát hành token |

Phân biệt các mốc này giúp tránh một lỗi thiết kế: refresh access token mới rồi xem người dùng như vừa xác thực lại, dù refresh có thể không yêu cầu người dùng nhập lại thông tin xác thực.

## 4. `iat` có bắt buộc trong mọi JWT không?

Ở cấp JWT tổng quát, `iat` là một registered claim **tùy chọn**. RFC 7519 không yêu cầu mọi JWT phải chứa claim này. Nếu claim có mặt, nó phải mang giá trị NumericDate hợp lệ.

Tuy nhiên, profile hoặc giao thức cụ thể có thể yêu cầu `iat`. Ví dụ:

- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068) đưa `iat` vào tập claim bắt buộc của JWT access token theo profile này.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html#IDToken) yêu cầu ID token có claim `iat` và quy định cách xác minh ID token.

Do đó, chính sách bên nhận cần xác định rõ:

| Tình huống | Hành vi phù hợp |
| --- | --- |
| JWT không có `iat`, profile không yêu cầu claim này và không áp dụng max-age | Không áp dụng kiểm tra dựa trên `iat`; tiếp tục các kiểm tra khác |
| Profile hoặc chính sách max-age yêu cầu `iat` nhưng token thiếu claim | Từ chối |
| `iat` có mặt và là NumericDate hợp lệ | Có thể áp dụng kiểm tra thời gian theo profile/chính sách |
| `iat` có mặt nhưng sai kiểu dữ liệu | Từ chối token không hợp lệ |
| `iat` nằm trong tương lai vượt quá dung sai được phép | Từ chối theo chính sách kiểm tra thời gian |

Không nên âm thầm coi token thiếu `iat` là token vừa được phát hành. Nếu không có thời điểm phát hành, hệ thống không thể tính tuổi token từ claim này.

## 5. Tính tuổi token từ `iat`

Khi `iat` và thời gian hiện tại dùng cùng đơn vị NumericDate, tuổi token có thể được tính:

\[
\text{tokenAge} = \text{now} - \text{iat}
\]

Trong đó:

- `now`: thời gian hiện tại tại bên xác minh, tính bằng giây từ Unix epoch.
- `iat`: thời điểm phát hành được ghi trong JWT, cũng tính bằng giây.
- `tokenAge`: thời gian đã trôi qua kể từ khi token được phát hành.

Ví dụ:

```text
iat = 1893452400
now = 1893453000

tokenAge = 1893453000 - 1893452400
         = 600 seconds
         = 10 minutes
```

Nếu `now` nhỏ hơn `iat`, kết quả tuổi token là số âm. Điều này có thể xảy ra khi đồng hồ lệch hoặc giá trị `iat` nằm trong tương lai. Hệ thống không nên bỏ qua trường hợp này; cần có chính sách xử lý timestamp tương lai và clock skew.

Tuổi token là thời gian kể từ khi token được phát hành, không phải thời gian còn lại trước khi token hết hạn. Thời gian còn lại theo `exp` được tính từ `exp - now`; hai phép tính phục vụ hai chính sách khác nhau.

## 6. Chính sách tuổi tối đa (Maximum Token Age)

RFC 7519 cho phép dùng `iat` để xác định tuổi JWT, nhưng **không tự định nghĩa một giá trị tuổi tối đa chung cho mọi token**. Bên nhận hoặc profile cần quy định ngưỡng phù hợp với mục đích sử dụng.

Ví dụ, API có thể đặt chính sách: access token không được cũ hơn 15 phút tại thời điểm xử lý request. Khi đó:

\[
\text{now} - \text{iat} \leq \text{maxAge}
\]

Với `maxAge = 900` giây:

| Tuổi token | Kết quả theo chính sách max-age | Giải thích |
| --- | --- | --- |
| 899 giây | Chấp nhận bước max-age | Chưa vượt giới hạn |
| 900 giây | Chấp nhận bước max-age | Đúng giới hạn tối đa nếu chính sách dùng `<=` |
| 901 giây | Từ chối | Đã vượt giới hạn |

Ranh giới trên là ví dụ về chính sách được chọn. Hệ thống có thể quy định cách xử lý khác, nhưng phải diễn đạt rõ và dùng nhất quán giữa các thành phần.

### Vì sao cần max-age nếu đã có `exp`?

`exp` và max-age giới hạn hai khía cạnh khác nhau:

- `exp` là thời điểm hết hạn tuyệt đối do bên phát hành ghi trong token.
- Max-age là giới hạn tuổi token mà bên nhận hoặc profile áp dụng khi xử lý.

Ví dụ token được phát hành lúc 08:00, có `exp` lúc 12:00, nhưng API chỉ chấp nhận token có tuổi tối đa 15 phút. Lúc 08:20, token chưa đến `exp` nhưng đã vượt max-age nên API từ chối.

Max-age có thể là một ràng buộc chặt hơn `exp`. Khi cả hai được áp dụng, token phải đồng thời chưa hết hạn theo `exp` và chưa vượt tuổi tối đa theo `iat`.

### Chọn ngưỡng max-age

Không có một ngưỡng phù hợp cho mọi ứng dụng. Cần xem xét:

- Loại token và tài nguyên mà token có thể truy cập.
- Mức độ nhạy cảm của dữ liệu và thao tác.
- Thời hạn `exp` mà issuer đặt.
- Tần suất client có thể lấy token mới.
- Cách refresh token và khả năng thu hồi token.
- Độ lệch đồng hồ giữa issuer và các bên nhận.
- Yêu cầu xác thực mới hoặc xác thực đa yếu tố của nghiệp vụ.

Không nên đặt max-age quá ngắn khiến client liên tục phải xin token mới, nhưng cũng không nên đặt quá dài chỉ để giảm số lần refresh. Hãy xác định ngưỡng theo mô hình đe dọa và kiểm thử trong điều kiện vận hành thực tế.

## 7. Xử lý `iat` nằm trong tương lai và clock skew

Đồng hồ bên phát hành và bên nhận có thể lệch nhau. Vì vậy, một token hợp lệ có thể có `iat` hơi lớn hơn `now` theo đồng hồ của bên nhận.

Gọi:

- `iat`: thời điểm phát hành trong token.
- `now`: thời gian hiện tại tại bên nhận.
- `L`: dung sai clock skew không âm, tính bằng giây.

Một chính sách thường dùng để kiểm tra timestamp tương lai là:

\[
\text{iat} \leq \text{now} + L
\]

Nếu `iat` lớn hơn `now + L`, token có thời điểm phát hành ở tương lai vượt quá dung sai cho phép và nên bị từ chối theo chính sách này.

Ví dụ `now = 1893452400`, `L = 30` giây:

| `iat` | Kết quả kiểm tra tương lai | Giải thích |
| --- | --- | --- |
| `1893452370` | Chấp nhận bước kiểm tra tương lai | Phát hành trước thời gian hiện tại |
| `1893452400` | Chấp nhận bước kiểm tra tương lai | Trùng thời gian hiện tại |
| `1893452430` | Chấp nhận trong dung sai | Tương lai đúng 30 giây |
| `1893452431` | Từ chối theo chính sách | Tương lai vượt quá dung sai |

RFC 7519 định nghĩa ý nghĩa của `iat`, nhưng không quy định một phép kiểm tra timestamp tương lai duy nhất cho mọi ứng dụng. Ngưỡng `L` và hành vi từ chối phải được xác định bởi profile hoặc chính sách triển khai. Leeway nên nhỏ; đồng bộ đồng hồ vẫn là biện pháp chính.

### Kết hợp max-age và clock skew

Một chính sách minh họa có thể yêu cầu:

1. `iat` không được nằm trong tương lai quá `L` giây.
2. Tuổi token không vượt quá `maxAge`, có thể cộng một dung sai nhỏ nếu chính sách cho phép.

Biểu diễn:

\[
\text{iat} \leq \text{now} + L_{future}
\]

\[
\text{now} - \text{iat} \leq \text{maxAge} + L_{age}
\]

`L_future` và `L_age` có thể là cùng một cấu hình hoặc hai giá trị riêng. Không nên mặc định cộng leeway nhiều lần ở nhiều tầng xác minh. Việc nới max-age cũng kéo dài tuổi token được chấp nhận, nên chỉ dùng khi cần thiết.

## 8. `iat` trong vòng đời access token và refresh token

Trong hệ thống sử dụng access token và refresh token, mỗi lần issuer phát hành một access token mới, `iat` của token mới phản ánh thời điểm phát hành mới đó.

Ví dụ:

| Sự kiện | Thời điểm | `iat` của access token |
| --- | --- | --- |
| Người dùng xác thực và nhận access token A | 08:00 | 08:00 |
| Client dùng refresh token xin access token B | 09:00 | 09:00 |
| Client tiếp tục refresh và nhận access token C | 10:00 | 10:00 |

Nếu max-age chỉ dựa trên `iat`, token C có tuổi gần bằng 0 tại thời điểm phát hành, dù phiên đăng nhập hoặc lần xác thực ban đầu đã tồn tại từ 08:00. Vì vậy:

- Max-age của **token** giới hạn tuổi kể từ lần phát hành token hiện tại.
- Max-age của **phiên** giới hạn thời gian kể từ khi phiên bắt đầu theo mô hình của hệ thống.
- Freshness của **lần xác thực người dùng** giới hạn thời gian kể từ lần xác thực thực sự.

Ba chính sách này không tương đương. Nếu cần giới hạn tuổi phiên hoặc yêu cầu người dùng xác thực lại sau một khoảng thời gian, hệ thống cần dữ liệu phiên hoặc claim phù hợp như `auth_time` trong OpenID Connect, thay vì chỉ kiểm tra `iat` của access token mới.

`iat` cũng không tự thu hồi token cũ khi issuer phát hành token mới. Nếu token cũ chưa hết hạn và chưa bị thu hồi, nó có thể vẫn được chấp nhận nếu vượt qua các kiểm tra khác. Muốn vô hiệu hóa sớm cần cơ chế thu hồi hoặc trạng thái phiên phù hợp.

## 9. `iat` không thay thế `nbf`, `exp` và `jti`

Các claim này có thể xuất hiện cùng nhau nhưng có vai trò riêng:

| Claim | Ý nghĩa | Câu hỏi được trả lời |
| --- | --- | --- |
| `iat` | Thời điểm phát hành | Token được tạo khi nào? |
| `nbf` | Thời điểm bắt đầu hiệu lực | Token được chấp nhận từ khi nào? |
| `exp` | Thời điểm hết hạn | Token không còn được chấp nhận từ khi nào? |
| `jti` | Định danh JWT | Token cụ thể này có ID nào? |
| `auth_time` (OpenID Connect) | Thời điểm người dùng được xác thực | Người dùng xác thực lần gần nhất khi nào? |

Ví dụ:

```json
{
  "iat": 1893452400,
  "nbf": 1893452460,
  "exp": 1893456000,
  "jti": "token-9f2a7c"
}
```

Token được phát hành tại `iat`, chưa được sử dụng trước `nbf`, hết hạn tại `exp` và có định danh `jti` để tham chiếu. `iat` không phải ID duy nhất và không thay thế `jti` trong denylist hoặc hệ thống theo dõi token.

## 10. Xác minh `iat` an toàn

Với JWS, payload JWT thường có thể được giải mã Base64URL mà không cần khóa. Kẻ tấn công có thể tự tạo payload hoặc sửa `iat` để làm token trông mới hơn. Vì vậy, một giá trị `iat` hợp lý **không chứng minh token được phát hành tại thời điểm đó**.

Bên nhận phải xác minh bảo vệ mật mã theo định dạng và profile, giới hạn thuật toán và khóa theo cấu hình tin cậy, rồi mới dùng claims để đánh giá tuổi token. Không chấp nhận JWT chỉ vì đã giải mã được payload hoặc vì `iat` nằm trong khoảng mong đợi.

Quy trình tổng quát:

1. Kiểm tra cấu trúc JWT và xác minh chữ ký/MAC hoặc cơ chế bảo vệ mật mã tương ứng.
2. Đọc claims từ token đã xác minh.
3. Xác nhận `iat` có mặt nếu profile hoặc chính sách max-age yêu cầu.
4. Kiểm tra `iat` là NumericDate hợp lệ, không ép kiểu tùy tiện.
5. Lấy thời gian hiện tại từ nguồn đồng hồ đáng tin cậy, cùng đơn vị giây.
6. Kiểm tra timestamp tương lai theo clock-skew tolerance đã cấu hình.
7. Nếu có max-age, tính tuổi token và so sánh với ngưỡng.
8. Tiếp tục kiểm tra `exp`, `nbf`, issuer, audience, token type và quyền.
9. Chỉ chấp nhận token nếu tất cả điều kiện bắt buộc đều đạt.

Giả mã minh họa:

```text
REQUIRE_IAT = true
MAX_TOKEN_AGE_SECONDS = 900
CLOCK_SKEW_SECONDS = 30

function issuedAtIsAcceptable(claims, now):
    if claims.iat is missing:
        return not REQUIRE_IAT

    if claims.iat is not a valid NumericDate:
        return false

    if claims.iat > now + CLOCK_SKEW_SECONDS:
        return false

    tokenAge = now - claims.iat

    if tokenAge > MAX_TOKEN_AGE_SECONDS + CLOCK_SKEW_SECONDS:
        return false

    return true

function validateRequest(token):
    claims = verifyTokenAndReadClaims(token)

    if verification failed:
        reject("invalid token")

    now = trustedCurrentUnixTimeInSeconds()

    if not issuedAtIsAcceptable(claims, now):
        reject("missing, future-dated or too-old iat")

    if not expirationNotBeforeIssuerAudienceAndOtherChecksPass(claims, now):
        reject("token does not satisfy validation policy")

    accept(claims)
```

Đây là giả mã mô tả chính sách, không phải API của một thư viện cụ thể. Ví dụ yêu cầu `iat` và đặt max-age 15 phút; với JWT tổng quát, có thể không bắt buộc `iat` nếu không áp dụng chính sách cần claim này. Trong thực tế, nên dùng thư viện JWT được duy trì tốt và cấu hình rõ claim bắt buộc, max-age, clock skew, issuer, audience, thuật toán và khóa.

## 11. Các lỗi thường gặp khi sử dụng `iat`

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Coi `iat` là thời điểm đăng nhập | Đánh giá sai độ mới của xác thực người dùng | Dùng `auth_time` hoặc dữ liệu phiên phù hợp |
| Coi `iat` là thời điểm bắt đầu hiệu lực | Token được chấp nhận trước `nbf` | Kiểm tra `nbf` độc lập |
| Coi `iat` là thời điểm hết hạn | Không có ranh giới kết thúc rõ ràng | Dùng `exp` và/hoặc chính sách max-age |
| Không kiểm tra tuổi token dù chính sách yêu cầu | Token cũ vẫn được chấp nhận nếu `exp` còn xa | Tính `now - iat` và so với max-age |
| Tự coi token thiếu `iat` là vừa phát hành | Bỏ qua giới hạn tuổi token | Từ chối khi profile/max-age yêu cầu `iat` |
| Chấp nhận `iat` ở tương lai không giới hạn | Timestamp bất hợp lý có thể làm sai tính tuổi | Đặt giới hạn future skew và đồng bộ đồng hồ |
| Đọc `iat` từ payload chưa xác minh | Kẻ tấn công có thể sửa thời điểm phát hành | Chỉ tin claims sau xác minh mật mã |
| So sánh giây với mili giây | Tính tuổi token sai nghiêm trọng | Dùng NumericDate theo giây ở cả hai phía |
| Ép chuỗi hoặc kiểu dữ liệu khác thành số | Dữ liệu sai định dạng có thể vượt kiểm tra | Kiểm tra NumericDate nghiêm ngặt |
| Làm mới access token rồi coi phiên vừa được xác thực | Vượt chính sách tuổi phiên hoặc freshness của xác thực | Tách token age, session age và authentication age |
| Dùng `iat` thay cho `jti` để thu hồi | Không có định danh riêng cho từng token | Dùng `jti` hoặc cơ chế định danh token thích hợp |

## 12. Tình huống thực tế

Một API quản lý kho chấp nhận access token có `exp` sau 60 phút, nhưng chính sách nội bộ yêu cầu token được phát hành không quá 15 phút trước mỗi request. Chính sách này giúp giảm thời gian một access token bị lộ có thể được sử dụng.

Token được cấp lúc 08:00:

```json
{
  "iss": "https://identity.example.com/",
  "sub": "warehouse-operator-17",
  "aud": "https://api.example.com/inventory",
  "iat": 1893452400,
  "exp": 1893456000,
  "scope": "inventory.read inventory.update"
}
```

Với max-age 15 phút và không có dung sai tuổi:

- Lúc 08:10: tuổi token là 10 phút; đạt bước max-age.
- Lúc 08:15: tuổi token đúng 15 phút; đạt nếu chính sách cho phép bằng ngưỡng.
- Lúc 08:16: tuổi token là 16 phút; bị từ chối do vượt max-age, dù `exp` vẫn còn ở tương lai.

Client có thể xin access token mới thông qua luồng refresh được phép. Token mới sẽ có `iat` mới. Nếu nghiệp vụ còn yêu cầu người dùng vừa xác thực hoặc vừa hoàn tất MFA, hệ thống phải kiểm tra thời điểm xác thực thực tế thay vì chỉ dựa vào `iat` mới của access token.

## 13. Kịch bản kiểm thử `iat`

Giả sử profile yêu cầu `iat`, chính sách max-age là 900 giây và clock-skew tolerance là 30 giây. Nên kiểm thử tối thiểu:

| Trường hợp | Kỳ vọng | Mục tiêu |
| --- | --- | --- |
| `iat` là NumericDate hợp lệ, tuổi token nhỏ hơn 900 giây | Chấp nhận bước max-age | Token còn mới |
| Tuổi token đúng 900 giây | Chấp nhận nếu chính sách dùng `<=` | Ranh giới max-age |
| Tuổi token lớn hơn 900 giây và ngoài dung sai | Từ chối | Token quá cũ |
| `iat` nằm trong tương lai nhưng không quá 30 giây | Chấp nhận bước kiểm tra future skew nếu chính sách cho phép | Clock skew nhỏ |
| `iat` nằm trong tương lai hơn 30 giây | Từ chối | Timestamp tương lai bất hợp lý |
| `iat` bị thiếu khi profile yêu cầu | Từ chối | Claim bắt buộc |
| `iat` bị thiếu khi profile không yêu cầu và không có max-age | Không từ chối vì riêng `iat` | Claim tùy chọn |
| `iat` là chuỗi, boolean, object hoặc `null` | Từ chối | Kiểm tra kiểu NumericDate |
| `iat` được phát hành nhầm theo mili giây | Xử lý theo hợp đồng và giới hạn thời gian đã cấu hình | Không tự đoán đơn vị |
| `iat` trông hợp lệ nhưng chữ ký không hợp lệ | Từ chối toàn bộ token | Không tin claims chưa xác minh |
| `iat` mới nhưng `exp` đã hết hạn | Từ chối toàn bộ token | Kiểm tra expiration độc lập |
| `iat` mới nhưng issuer hoặc audience sai | Từ chối toàn bộ token | Tuổi token không thay thế kiểm tra nguồn và recipient |
| Access token mới sau refresh nhưng `auth_time` cũ | Đánh giá theo chính sách freshness xác thực riêng | Không nhầm token age với authentication age |

Nên kiểm thử cả đồng hồ bên nhận chạy nhanh và chậm, max-age bằng 0 hoặc ở mức tối đa theo cấu hình, leeway bằng 0, và lỗi lấy thời gian. Khi không có đồng hồ đáng tin cậy, hệ thống không được mặc định rằng token còn mới.

## 14. Nguyên tắc cần ghi nhớ

1. `iat` xác định thời điểm JWT được phát hành; nó không tự đặt thời điểm bắt đầu hoặc kết thúc hiệu lực.
2. `iat` sử dụng NumericDate, tính bằng giây từ Unix epoch UTC; không phải mili giây hay chuỗi ngày giờ.
3. `iat` là claim tùy chọn trong JWT tổng quát, nhưng profile hoặc chính sách max-age có thể bắt buộc claim này.
4. Có thể tính tuổi token bằng `now - iat` và so sánh với max-age do profile hoặc ứng dụng quy định.
5. Kiểm tra timestamp tương lai và clock skew theo chính sách rõ ràng; không chấp nhận `iat` tương lai không giới hạn.
6. `iat` là thời điểm phát hành token, không phải thời điểm người dùng xác thực; OpenID Connect dùng `auth_time` cho mốc xác thực.
7. `iat` không thay thế `nbf`, `exp`, `jti`, issuer, audience hoặc kiểm tra quyền.
8. Chỉ dùng `iat` sau khi xác minh bảo vệ mật mã; payload có thể đọc được không phải bằng chứng về thời điểm phát hành.

### Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT), mục 2 và 4.1.6](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa NumericDate và claim `iat`.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh chữ ký, thuật toán, khóa và claims theo ngữ cảnh.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): các claim bắt buộc và quy tắc cho JWT access token.
- [OpenID Connect Core 1.0, mục 2, 3.1.2.1 và 3.1.3.7](https://openid.net/specs/openid-connect-core-1_0.html): `iat`, `auth_time`, `max_age` và xác minh ID token.

**Kết luận:** `iat` ghi nhận thời điểm JWT được phát hành và có thể dùng để tính tuổi token. Muốn giới hạn tuổi tối đa, bên nhận phải xác minh token trước, kiểm tra `iat` là NumericDate hợp lệ, áp dụng ngưỡng max-age cùng chính sách clock skew, đồng thời phân biệt tuổi token với tuổi phiên và độ mới của lần xác thực người dùng.
