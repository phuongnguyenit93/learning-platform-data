# `exp`: Thời điểm hết hạn và ranh giới chấp nhận JWT

## 1. `exp` xác định điều gì?

Trong JSON Web Token (JWT), **`exp` (expiration time)** là *registered claim* xác định thời điểm mà token hết hạn. Claim này đặt ra giới hạn cuối cùng cho khoảng thời gian token được phép sử dụng.

Theo [RFC 7519, mục 4.1.4](https://www.rfc-editor.org/rfc/rfc7519#section-4.1.4), một JWT **không được chấp nhận để xử lý tại hoặc sau thời điểm hết hạn** ghi trong `exp`. Khi kiểm tra claim này, thời gian hiện tại phải nhỏ hơn thời điểm hết hạn. Bên xác minh có thể cho phép một khoảng sai lệch đồng hồ nhỏ (*clock-skew leeway*), thường không quá vài phút.

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

Trong ví dụ, `exp` là mốc thời gian kết thúc hiệu lực của token. Nếu không cấu hình leeway, token được chấp nhận khi thời gian hiện tại còn nhỏ hơn `1893456000`; từ đúng mốc đó trở đi, token đã hết hạn.

`exp` giúp bên nhận trả lời câu hỏi: **“Token này còn nằm trong khoảng thời gian được phép sử dụng không?”** Đây là một điều kiện quan trọng để giới hạn thời gian rủi ro nếu token bị lộ.

## 2. `exp` dùng kiểu dữ liệu NumericDate

Giá trị `exp` phải là **NumericDate** theo định nghĩa trong [RFC 7519, mục 2](https://www.rfc-editor.org/rfc/rfc7519#section-2). NumericDate là một giá trị số biểu diễn số giây tính từ:

```text
1970-01-01T00:00:00Z
```

Đây là Unix epoch theo UTC, bỏ qua giây nhuận. NumericDate có thể là số nguyên hoặc số không nguyên; giá trị không nguyên biểu diễn phần lẻ của giây.

Ví dụ:

```json
{
  "exp": 1893456000
}
```

Giá trị trên là số giây, không phải mili giây. Một số lỗi định dạng thường gặp:

| Giá trị | Đánh giá | Lý do |
| --- | --- | --- |
| `1893456000` | Hợp lệ về kiểu | NumericDate dạng số nguyên, đơn vị giây |
| `1893456000.5` | Hợp lệ về kiểu | NumericDate có phần lẻ của giây |
| `"1893456000"` | Không hợp lệ | Chuỗi JSON, không phải giá trị số |
| `1893456000000` | Có thể là sai đơn vị | Con số thường xuất phát từ mili giây; không được tự đoán và chuyển đổi |
| `null` | Không hợp lệ | Không phải NumericDate |
| `true` | Không hợp lệ | Boolean không phải NumericDate |
| `{ "seconds": 1893456000 }` | Không hợp lệ | Object không phải NumericDate |

Không tự động ép chuỗi thành số hoặc đoán đơn vị dựa trên độ lớn của giá trị. Bên phát hành phải tạo claim đúng định dạng, bên nhận phải kiểm tra kiểu dữ liệu nghiêm ngặt.

Lưu ý: một con số lớn do bên phát hành nhầm mili giây vẫn là một giá trị JSON dạng số; chỉ nhìn kiểu dữ liệu không thể chứng minh người tạo token đã nhầm đơn vị. Hai bên cần thống nhất NumericDate theo giây, kiểm thử dữ liệu phát hành và có thể đặt giới hạn hợp lý theo chính sách của hệ thống. Bên nhận không nên tự chia cho 1.000 dựa trên phỏng đoán.

### Tránh nhầm giây với mili giây

Nhiều nền tảng cung cấp thời gian hiện tại dưới dạng mili giây, trong khi NumericDate dùng giây. Khi so sánh, hai giá trị phải cùng đơn vị:

```text
nowEpochSeconds = currentUnixTimeMilliseconds / 1000
```

Đây chỉ là phép chuyển đổi đơn vị minh họa. Cần giữ độ chính xác phù hợp nếu hệ thống sử dụng NumericDate có phần lẻ của giây. Không so sánh trực tiếp `exp` tính bằng giây với đồng hồ tính bằng mili giây vì kết quả sẽ sai lệch rất lớn.

## 3. Ranh giới hết hạn: trước, đúng tại và sau `exp`

Quy tắc cốt lõi của RFC 7519 là:

\[
\text{currentTime} < \text{exp}
\]

Nếu không sử dụng leeway, ranh giới được hiểu như sau:

| Thời gian hiện tại | Kết quả | Giải thích |
| --- | --- | --- |
| `exp - 1` giây | Chưa hết hạn | Thời gian hiện tại còn trước mốc `exp` |
| Đúng `exp` | Hết hạn | Điều kiện “phải nhỏ hơn `exp`” không còn đúng |
| `exp + 1` giây | Hết hạn | Đã vượt qua mốc hết hạn |

Điểm dễ nhầm là **`exp` không phải giây cuối cùng mà token còn được dùng**. Nó là mốc bắt đầu trạng thái hết hạn. Với leeway bằng 0, phép kiểm tra tương đương `now >= exp` thì từ chối.

Ví dụ với `exp = 1893456000`:

```text
now = 1893455999  -> còn hiệu lực theo exp
now = 1893456000  -> hết hạn
now = 1893456001  -> hết hạn
```

Các kết quả trên chỉ xét điều kiện `exp`; token vẫn phải vượt qua các kiểm tra chữ ký, issuer, audience, loại token, quyền và những chính sách khác.

## 4. Clock skew và khoảng dung sai (leeway)

Thời gian trên máy phát hành token và máy xác minh có thể không hoàn toàn giống nhau. Ví dụ, authorization server đã phát hành token theo đồng hồ của nó, nhưng đồng hồ của API đang chạy nhanh hơn vài chục giây. API có thể kết luận token hết hạn sớm hơn dự kiến.

RFC 7519 cho phép bên triển khai dùng một khoảng dung sai nhỏ để xử lý chênh lệch đồng hồ. Gọi:

- `exp`: thời điểm hết hạn trong JWT.
- `now`: thời gian hiện tại tại bên xác minh.
- `L`: leeway không âm, tính bằng giây.

Quy tắc kiểm tra expiration có leeway có thể biểu diễn:

\[
\text{now} < \text{exp} + L
\]

Khi `L = 0`, quy tắc trở về ranh giới chuẩn `now < exp`. Khi `L > 0`, hệ thống chấp nhận một khoảng thời gian ngắn sau `exp` để bù sai lệch đồng hồ.

Ví dụ `exp = 1893456000`, `L = 60` giây:

| Thời gian hiện tại | Kết quả kiểm tra expiration | Giải thích |
| --- | --- | --- |
| `1893455999` | Chấp nhận theo `exp` | Trước mốc hết hạn |
| `1893456000` | Chấp nhận trong leeway | Đúng `exp`, nằm trong khoảng dung sai |
| `1893456059` | Chấp nhận trong leeway | Còn trước `exp + 60` |
| `1893456060` | Từ chối | Đã tới ranh giới `exp + L` |
| `1893456061` | Từ chối | Đã vượt ranh giới dung sai |

Leeway là một đánh đổi bảo mật: nó giảm lỗi do đồng hồ lệch nhưng đồng thời kéo dài khoảng thời gian token có thể được chấp nhận. Vì vậy:

- Chỉ đặt leeway nhỏ, có lý do vận hành rõ ràng; RFC nói khoảng này thường không quá vài phút.
- Dùng một chính sách nhất quán giữa các thành phần xác minh.
- Không dùng leeway lớn để che giấu hệ thống đồng hồ không được đồng bộ.
- Tính đến việc leeway có thể cho phép token tiếp tục được chấp nhận sau `exp` theo đồng hồ của bên phát hành.
- Theo dõi và đồng bộ đồng hồ của các máy bằng cơ chế thời gian tin cậy.

Không được mô tả token có leeway là “hết hạn đúng tại `exp` nhưng vẫn hợp lệ”. Chính xác hơn, `exp` vẫn là thời điểm hết hạn do bên phát hành khai báo; leeway là ngoại lệ do bên xác minh áp dụng cho ranh giới chấp nhận.

## 5. `exp` có bắt buộc trong mọi JWT không?

Ở cấp JWT tổng quát, `exp` là một registered claim **tùy chọn**. RFC 7519 không yêu cầu mọi JWT đều phải chứa claim này. Tuy nhiên, một giao thức, profile token hoặc chính sách ứng dụng có thể bắt buộc phải có `exp`.

Ví dụ:

- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068) yêu cầu claim `exp` trong JWT access token tuân theo profile này.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html#IDToken) yêu cầu ID token có `exp` và quy định client xác minh thời hạn của ID token.

Đối với access token dùng để bảo vệ API, việc yêu cầu `exp` thường là chính sách an toàn và dễ dự đoán. Nếu ứng dụng bắt buộc có `exp`, token thiếu claim phải bị từ chối. Không được âm thầm coi token không có `exp` là không bao giờ hết hạn.

Chính sách cần phân biệt rõ:

| Tình huống | Hành vi phù hợp |
| --- | --- |
| Profile quy định `exp` bắt buộc nhưng token thiếu claim | Từ chối |
| Ứng dụng quy định `exp` bắt buộc nhưng token thiếu claim | Từ chối |
| JWT tổng quát không có profile yêu cầu `exp` | Xử lý theo chính sách được định nghĩa rõ; cân nhắc không chấp nhận token không có giới hạn thời gian |
| `exp` có mặt nhưng sai kiểu hoặc không hợp lệ | Từ chối |

## 6. Phân biệt `exp` với `iat` và `nbf`

Ba claim thời gian thường xuất hiện cùng nhau nhưng có ý nghĩa khác nhau:

| Claim | Tên | Ý nghĩa | Điều kiện thời gian thường dùng |
| --- | --- | --- | --- |
| `iat` | Issued At | Thời điểm token được phát hành | Dùng để ghi nhận thời điểm phát hành và áp dụng chính sách liên quan |
| `nbf` | Not Before | Token chưa được chấp nhận trước thời điểm này | `now >= nbf` (có thể có leeway theo chính sách) |
| `exp` | Expiration Time | Token hết hạn tại hoặc sau thời điểm này | `now < exp` (có thể có leeway theo chính sách) |

Ví dụ:

```json
{
  "iat": 1893452400,
  "nbf": 1893452460,
  "exp": 1893456000
}
```

Token trong ví dụ được phát hành tại `iat`, chỉ được chấp nhận từ `nbf` trở đi và hết hạn tại `exp`. Khoảng thời gian có thể sử dụng theo các claim này nằm giữa `nbf` và `exp`, sau khi áp dụng leeway nếu có.

`iat` không tự động làm token hết hạn và không thay thế `exp`. `nbf` không phải thời điểm phát hành. Một token có `exp` hợp lệ nhưng `nbf` nằm trong tương lai vẫn chưa được chấp nhận. Ngược lại, token đã qua `nbf` nhưng vượt `exp` vẫn phải bị từ chối.

Nếu đồng thời có `iat`, `nbf` và `exp`, ứng dụng có thể kiểm tra thêm tính hợp lý của quan hệ thời gian theo profile hoặc chính sách, chẳng hạn không chấp nhận khoảng hiệu lực bị đảo ngược. Đây là quy tắc kiểm tra bổ sung; không nên gán cho riêng `exp` những ý nghĩa của claim khác.

## 7. Thời hạn token và vòng đời sử dụng

`exp` giới hạn thời gian chấp nhận của một token cụ thể. Bên phát hành thường quyết định thời hạn khi tạo token, dựa trên loại token, độ nhạy của tài nguyên và mức rủi ro chấp nhận được.

### Thời hạn ngắn và dài

| Thời hạn | Lợi ích | Đánh đổi |
| --- | --- | --- |
| Ngắn | Giảm khoảng thời gian token bị lộ có thể bị tái sử dụng; thay đổi quyền được phản ánh sớm hơn khi cấp token mới | Client cần lấy token mới thường xuyên hơn; phụ thuộc vào dịch vụ cấp token |
| Dài | Giảm tần suất làm mới token, thuận tiện cho một số luồng sử dụng | Token bị lộ có thể bị sử dụng lâu hơn; thay đổi quyền không tự động phản ánh vào token đã phát hành |

Không có một thời hạn chung phù hợp cho mọi hệ thống. Hãy xác định thời hạn theo mô hình đe dọa, độ nhạy dữ liệu, trải nghiệm người dùng, tần suất làm mới và khả năng thu hồi token.

### Hết hạn không đồng nghĩa với thu hồi ngay lập tức

Với JWT tự chứa (self-contained), API có thể xác minh token mà không cần hỏi lại authorization server ở mỗi request. Khi token chưa hết hạn và mọi kiểm tra khác đều đạt, token vẫn có thể được chấp nhận ngay cả khi trạng thái tài khoản hoặc quyền của người dùng đã thay đổi, trừ khi hệ thống có cơ chế kiểm tra bổ sung.

Do đó, **`exp` không phải cơ chế thu hồi token tức thời**. Nếu cần chặn token trước thời điểm hết hạn, hệ thống có thể cân nhắc các cơ chế như:

- Danh sách từ chối (denylist) theo `jti` hoặc định danh token, được kiểm tra tại bên nhận.
- Introspection hoặc truy vấn trạng thái token tới authorization server.
- Phiên bản token hoặc phiên đăng nhập, cho phép vô hiệu hóa các token cũ theo chính sách.
- Sự kiện thu hồi và cơ chế đồng bộ trạng thái giữa các thành phần.
- Thời hạn access token ngắn để giới hạn cửa sổ rủi ro khi không có cơ chế thu hồi tức thời.

Mỗi cơ chế có chi phí về trạng thái, độ trễ, tính sẵn sàng và độ phức tạp vận hành. Chọn theo yêu cầu thu hồi thực tế; không giả định chỉ cần đặt `exp` là giải quyết được mọi tình huống logout hoặc khóa tài khoản.

### Hết hạn access token và refresh token

Khi access token hết hạn, client thường cần xin một access token mới thông qua luồng cấp phát được phép. Nếu hệ thống sử dụng refresh token, refresh token là một credential riêng với thời hạn, audience/phạm vi, quy tắc lưu trữ và chính sách thu hồi riêng.

Không tự gia hạn một JWT đã hết hạn bằng cách sửa `exp` trong payload. Mọi token mới phải được bên phát hành cấp và bảo vệ mật mã theo quy trình hợp lệ. Việc refresh cũng có thể bị từ chối nếu phiên đăng nhập hoặc refresh token đã hết hạn hay bị thu hồi.

## 8. Xác minh `exp` an toàn

Claim `exp` nằm trong payload JWT. Với JWS, payload thường có thể được giải mã Base64URL để đọc mà không cần khóa xác minh. Vì vậy, một chuỗi `exp` nhìn có vẻ hợp lệ **không chứng minh token thực sự được phát hành với thời điểm đó**.

Trước khi tin claims, bên nhận phải xác minh bảo vệ mật mã theo định dạng và profile đang dùng, ví dụ chữ ký hoặc MAC của JWS, hay cơ chế mã hóa kèm xác thực tính toàn vẹn của JWE. Đồng thời phải giới hạn thuật toán và khóa theo cấu hình tin cậy. Không chấp nhận token chỉ vì đã giải mã được payload.

Quy trình tổng quát:

1. Kiểm tra cấu trúc và xác minh bảo vệ mật mã của JWT.
2. Đọc claims đã xác minh.
3. Xác nhận `exp` có mặt nếu profile hoặc chính sách yêu cầu.
4. Kiểm tra `exp` là NumericDate hợp lệ, không ép kiểu tùy tiện.
5. Lấy thời gian hiện tại từ nguồn đồng hồ đáng tin cậy, cùng đơn vị giây.
6. So sánh với `exp` theo leeway đã cấu hình.
7. Tiếp tục kiểm tra issuer, audience, `nbf`, loại token và quyền.
8. Chỉ chấp nhận request nếu mọi điều kiện bắt buộc đều đạt.

Giả mã minh họa:

```text
REQUIRE_EXP = true
CLOCK_SKEW_LEEWAY_SECONDS = 30

function isNotExpired(claims, nowEpochSeconds):
    if claims.exp is missing:
        return not REQUIRE_EXP

    if claims.exp is not a valid NumericDate:
        return false

    effectiveDeadline = claims.exp + CLOCK_SKEW_LEEWAY_SECONDS

    return nowEpochSeconds < effectiveDeadline

function validateRequest(token):
    claims = verifyTokenAndReadClaims(token)

    if verification failed:
        reject("invalid token")

    now = trustedCurrentUnixTimeInSeconds()

    if not isNotExpired(claims, now):
        reject("token expired or missing required exp")

    if not issuerAudienceAndOtherTimeChecksPass(claims, now):
        reject("token does not satisfy validation policy")

    accept(claims)
```

Đây là giả mã mô tả chính sách, không phải API của một thư viện cụ thể. Trong hệ thống thực tế, nên dùng thư viện JWT được duy trì tốt và cấu hình rõ leeway, yêu cầu claim, issuer, audience, thuật toán và khóa. Tránh tự xây dựng toàn bộ bộ phân tích JWT và cơ chế xác minh mật mã nếu không có nhu cầu chuyên biệt.

## 9. Đồng hồ và các lỗi vận hành thường gặp

Kiểm tra `exp` phụ thuộc vào thời gian hiện tại của bên xác minh. Một số tình huống thường gặp:

| Vấn đề | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Đồng hồ máy xác minh chạy nhanh | Token bị từ chối trước thời điểm dự kiến | Đồng bộ đồng hồ và đặt leeway nhỏ nếu cần |
| Đồng hồ máy xác minh chạy chậm | Token có thể được chấp nhận lâu hơn theo thời gian thực | Đồng bộ đồng hồ, theo dõi độ lệch và giới hạn leeway |
| So sánh giây với mili giây | Token bị coi là quá hạn hoặc còn hiệu lực bất thường | Chuẩn hóa đơn vị về NumericDate tính bằng giây |
| Dùng giờ địa phương thay UTC | Kết quả thay đổi theo timezone hoặc cấu hình máy | Dùng Unix time/UTC tuyệt đối |
| Chuyển `exp` thành chuỗi hoặc ép kiểu không kiểm soát | Sai định dạng có thể lọt qua hoặc gây lỗi | Kiểm tra kiểu số theo chuẩn |
| Leeway quá lớn | Token tiếp tục được chấp nhận lâu sau `exp` | Chỉ dùng dung sai nhỏ, có kiểm soát |
| Token không có `exp` nhưng vẫn được chấp nhận mặc định | Token có thể không có giới hạn thời gian | Định nghĩa rõ claim bắt buộc và từ chối khi thiếu |
| Tin `exp` từ payload chưa xác minh | Người tấn công có thể sửa thời điểm hết hạn | Chỉ dùng claims sau xác minh bảo vệ mật mã |

Thời gian hệ thống nên được đồng bộ với nguồn tin cậy và được giám sát. Leeway không thay thế vận hành đồng hồ chính xác.

## 10. Tình huống thực tế

Một API quản lý kho chỉ chấp nhận access token có thời hạn 10 phút. Authorization server cấp token với `iat` và `exp`:

```json
{
  "iss": "https://identity.example.com/",
  "sub": "warehouse-operator-17",
  "aud": "https://api.example.com/inventory",
  "iat": 1893452400,
  "exp": 1893453000,
  "scope": "inventory.read inventory.update"
}
```

API xác minh chữ ký, issuer và audience, sau đó kiểm tra thời hạn. Khi đồng hồ hiện tại vượt ranh giới expiration theo chính sách, API từ chối token và yêu cầu client thực hiện quy trình lấy token mới nếu còn đủ điều kiện.

Nếu token bị sao chép ở phút thứ hai, kẻ giữ token chỉ có thể thử sử dụng nó trong khoảng thời gian còn lại trước khi hết hạn, trừ khi token bị thu hồi sớm hoặc có kiểm tra bổ sung. Khi token hết hạn, việc sửa riêng trường `exp` không giúp token hợp lệ vì chữ ký không còn khớp với payload đã bị thay đổi.

Ví dụ này cho thấy thời hạn ngắn làm giảm cửa sổ sử dụng token bị lộ, nhưng không loại bỏ nhu cầu bảo vệ token, xác minh chữ ký, kiểm tra audience và xây dựng cơ chế thu hồi phù hợp.

## 11. Kịch bản kiểm thử `exp`

Giả sử ứng dụng yêu cầu `exp` và cấu hình leeway bằng 30 giây. Nên kiểm tra tối thiểu:

| Trường hợp | Kỳ vọng | Mục tiêu |
| --- | --- | --- |
| `exp` là NumericDate hợp lệ, thời gian hiện tại còn trước deadline hiệu lực | Chấp nhận bước expiration | Token còn trong thời gian được phép |
| `now` đúng bằng `exp`, leeway bằng 0 | Từ chối | Kiểm tra ranh giới chính xác |
| `now` lớn hơn `exp`, leeway bằng 0 | Từ chối | Token đã hết hạn |
| `now` nằm trong khoảng leeway sau `exp` | Chấp nhận bước expiration nếu chưa tới `exp + L` | Kiểm tra dung sai đồng hồ |
| `now` đúng bằng `exp + L` | Từ chối | Ranh giới leeway cũng là điều kiện nghiêm ngặt |
| `now` lớn hơn `exp + L` | Từ chối | Đã vượt thời hạn và dung sai |
| `exp` bị thiếu trong profile yêu cầu claim | Từ chối | Claim bắt buộc |
| `exp` là chuỗi, boolean, object hoặc `null` | Từ chối | Kiểm tra kiểu NumericDate |
| `exp` được phát hành nhầm theo mili giây và nằm ngoài giới hạn thời gian hợp lý của hệ thống | Từ chối theo chính sách đã cấu hình | Không tự đoán đơn vị; kiểm tra hợp đồng và dữ liệu phát hành |
| `exp` đúng nhưng chữ ký sai | Từ chối toàn bộ token | Không tin claims chưa xác minh |
| `exp` đúng nhưng `nbf` nằm trong tương lai | Từ chối toàn bộ token | Kiểm tra thời điểm bắt đầu hiệu lực |
| `exp` đúng nhưng issuer hoặc audience sai | Từ chối toàn bộ token | Expiration không thay thế các kiểm tra khác |

Nên kiểm thử cả đồng hồ lệch nhanh và chậm, leeway bằng 0, leeway ở mức cấu hình tối đa và hành vi khi hệ thống không lấy được thời gian đáng tin cậy. Không để lỗi lấy thời gian khiến ứng dụng mặc định chấp nhận token.

## 12. Nguyên tắc cần ghi nhớ

1. `exp` xác định mốc hết hạn của JWT; không có leeway thì token phải bị từ chối khi `now >= exp`.
2. `exp` sử dụng NumericDate, tính bằng giây từ Unix epoch UTC; không phải mili giây hay chuỗi ngày giờ.
3. `exp` là claim tùy chọn trong JWT tổng quát, nhưng profile hoặc chính sách ứng dụng có thể bắt buộc claim này.
4. Leeway chỉ nên nhỏ và có kiểm soát; nó mở rộng ranh giới chấp nhận thực tế của token.
5. Chỉ kiểm tra `exp` sau khi xác minh bảo vệ mật mã và tin cậy claims.
6. `exp` khác `iat` và `nbf`; mỗi claim đảm nhiệm một mốc thời gian riêng.
7. Hết hạn không đồng nghĩa với thu hồi tức thời; nếu cần vô hiệu hóa sớm phải có cơ chế bổ sung.
8. Đồng bộ đồng hồ, kiểm tra đơn vị và kiểm thử chính xác tại ranh giới để tránh chấp nhận token ngoài thời hạn.

### Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT), mục 2 và 4.1.4](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa NumericDate và claim `exp`.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh JWT, khóa, thuật toán và claims theo ngữ cảnh.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): yêu cầu `exp` trong profile JWT access token.
- [OpenID Connect Core 1.0, mục 2 và 3.1.3.7](https://openid.net/specs/openid-connect-core-1_0.html#IDToken): thời hạn và xác minh ID token.

**Kết luận:** `exp` đặt ra thời điểm JWT không còn được chấp nhận. Bên nhận phải kiểm tra NumericDate trên claims đã xác minh, so sánh với đồng hồ đáng tin cậy theo ranh giới nghiêm ngặt và chỉ áp dụng leeway nhỏ khi thực sự cần xử lý clock skew.
