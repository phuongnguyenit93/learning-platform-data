# `nbf`: Thời điểm JWT bắt đầu có hiệu lực

## 1. `nbf` biểu thị điều gì?

Trong JSON Web Token (JWT), **`nbf` (Not Before)** là *registered claim* xác định thời điểm trước đó token **không được chấp nhận để xử lý**. Bên nhận chỉ được chấp nhận token theo điều kiện thời gian này khi thời gian hiện tại đã đến hoặc vượt qua mốc `nbf`.

Theo [RFC 7519, mục 4.1.5](https://www.rfc-editor.org/rfc/rfc7519#section-4.1.5), claim `nbf` xác định thời điểm mà JWT bắt đầu có hiệu lực. Nếu thời gian hiện tại của bên xử lý còn trước mốc này, token chưa được phép sử dụng. Bên xác minh có thể cho phép một khoảng dung sai nhỏ để xử lý sai lệch đồng hồ giữa các hệ thống.

Ví dụ payload:

```json
{
  "iss": "https://identity.example.com/",
  "sub": "user-7821",
  "aud": "https://api.example.com/inventory",
  "nbf": 1893452460,
  "exp": 1893456000
}
```

Trong ví dụ, token chỉ được chấp nhận từ thời điểm `1893452460` trở đi theo quy tắc `nbf` (nếu không có leeway). Trước mốc đó, token vẫn bị xem là chưa có hiệu lực, kể cả khi chữ ký hợp lệ và các claim khác đúng.

`nbf` giúp bên nhận trả lời câu hỏi: **“Token này đã đến thời điểm được phép sử dụng chưa?”** Claim này đặc biệt hữu ích khi token được tạo trước một thời điểm nhưng chỉ được phép sử dụng từ một thời điểm xác định trong tương lai.

## 2. `nbf` sử dụng NumericDate

Giá trị `nbf` phải là **NumericDate** theo định nghĩa tại [RFC 7519, mục 2](https://www.rfc-editor.org/rfc/rfc7519#section-2). NumericDate biểu diễn số giây tính từ Unix epoch:

```text
1970-01-01T00:00:00Z
```

Đây là mốc thời gian UTC, bỏ qua giây nhuận. NumericDate có thể là số nguyên hoặc số không nguyên để biểu diễn phần lẻ của giây.

Ví dụ:

```json
{
  "nbf": 1893452460
}
```

Một số dạng dữ liệu cần phân biệt:

| Giá trị JSON | Đánh giá | Lý do |
| --- | --- | --- |
| `1893452460` | Hợp lệ về kiểu | NumericDate dạng số nguyên, đơn vị giây |
| `1893452460.5` | Hợp lệ về kiểu | NumericDate có phần lẻ của giây |
| `"1893452460"` | Không hợp lệ | Chuỗi JSON, không phải giá trị số |
| `null` | Không hợp lệ | Không phải NumericDate |
| `true` | Không hợp lệ | Boolean không phải NumericDate |
| `{ "seconds": 1893452460 }` | Không hợp lệ | Object không phải NumericDate |

Không tự ép chuỗi thành số và không tự đoán đơn vị dựa trên độ lớn của giá trị. Một số được tạo nhầm từ mili giây vẫn có kiểu JSON là number; chỉ kiểm tra kiểu không thể xác định chắc chắn lỗi đơn vị. Hai bên cần thống nhất NumericDate theo giây, kiểm thử dữ liệu phát hành và có thể áp dụng giới hạn thời gian hợp lý theo chính sách. Không âm thầm chia cho 1.000 dựa trên phỏng đoán.

Nếu đồng hồ hiện tại của hệ thống được cung cấp theo mili giây, phải chuyển về giây trước khi so sánh:

```text
nowEpochSeconds = currentUnixTimeMilliseconds / 1000
```

Không so sánh trực tiếp `nbf` theo giây với thời gian hiện tại theo mili giây. Cũng cần giữ đủ độ chính xác nếu hệ thống sử dụng NumericDate có phần lẻ của giây.

## 3. Ranh giới bắt đầu hiệu lực: trước, đúng tại và sau `nbf`

Không sử dụng leeway, quy tắc cơ bản là:

\[
\text{currentTime} \geq \text{nbf}
\]

Khác với `exp`, ranh giới của `nbf` là bao gồm chính thời điểm được khai báo:

| Thời gian hiện tại | Kết quả theo `nbf` | Giải thích |
| --- | --- | --- |
| `nbf - 1` giây | Từ chối | Vẫn còn trước thời điểm bắt đầu |
| Đúng `nbf` | Chấp nhận bước kiểm tra `nbf` | Đã đến thời điểm hiệu lực |
| `nbf + 1` giây | Chấp nhận bước kiểm tra `nbf` | Đã qua thời điểm bắt đầu |

Ví dụ với `nbf = 1893452460`:

```text
now = 1893452459  -> chưa có hiệu lực
now = 1893452460  -> đã có hiệu lực theo nbf
now = 1893452461  -> đã có hiệu lực theo nbf
```

Điều này có nghĩa `nbf` không phải “giây cuối cùng phải chờ”. Nó là mốc mà từ đó token có thể được chấp nhận theo điều kiện này. Token vẫn cần vượt qua các điều kiện khác như chữ ký, issuer, audience, expiration, token type và quyền.

## 4. Clock skew và leeway cho `nbf`

Đồng hồ của authorization server và resource server có thể lệch nhau. Chẳng hạn, issuer tạo token với `nbf` là 10:00:00 UTC, nhưng đồng hồ API đang chậm 20 giây. API có thể tiếp tục từ chối token trong một khoảng ngắn sau khi token đã đến thời điểm hiệu lực theo đồng hồ của issuer.

RFC 7519 cho phép bên xác minh áp dụng một khoảng dung sai nhỏ để xử lý sai lệch đồng hồ. Gọi:

- `nbf`: thời điểm bắt đầu hiệu lực trong JWT.
- `now`: thời gian hiện tại tại bên xác minh.
- `L`: leeway không âm, tính bằng giây.

Điều kiện chấp nhận `nbf` có leeway có thể biểu diễn:

\[
\text{now} + L \geq \text{nbf}
\]

Khi `L = 0`, hệ thống yêu cầu `now >= nbf`. Khi `L > 0`, hệ thống có thể chấp nhận token sớm hơn mốc `nbf` tối đa `L` giây theo đồng hồ của bên xác minh.

Ví dụ `nbf = 1893452460`, `L = 30` giây:

| Thời gian hiện tại | Kết quả kiểm tra `nbf` | Giải thích |
| --- | --- | --- |
| `1893452429` | Từ chối | `now + 30` vẫn nhỏ hơn `nbf` |
| `1893452430` | Chấp nhận trong leeway | `now + 30` bằng `nbf` |
| `1893452459` | Chấp nhận trong leeway | Đã nằm trong cửa sổ dung sai |
| `1893452460` | Chấp nhận | Đã đến đúng `nbf` |
| `1893452461` | Chấp nhận | Đã qua `nbf` |

Leeway có hai mặt: nó giảm lỗi do đồng hồ lệch nhưng cũng làm token được chấp nhận sớm hơn thời điểm bắt đầu do issuer công bố. Vì vậy:

- Chỉ đặt leeway nhỏ, có lý do vận hành rõ ràng; RFC 7519 nói khoảng này thường không quá vài phút.
- Đồng bộ đồng hồ bằng nguồn thời gian đáng tin cậy và giám sát độ lệch.
- Dùng chính sách nhất quán giữa các resource server.
- Không tăng leeway lớn để che giấu đồng hồ không được đồng bộ.
- Ghi nhận rằng leeway làm thay đổi ranh giới chấp nhận thực tế tại bên xác minh.

Không diễn giải leeway là issuer đã thay đổi `nbf`. Claim vẫn giữ nguyên mốc do issuer khai báo; leeway là dung sai mà bên nhận quyết định áp dụng khi kiểm tra.

## 5. `nbf` có bắt buộc trong mọi JWT không?

Ở cấp JWT tổng quát, `nbf` là một registered claim **tùy chọn**. RFC 7519 không yêu cầu mọi JWT phải chứa claim này. Khi `nbf` xuất hiện, bên xử lý phải áp dụng quy tắc thời gian của claim; nếu claim không xuất hiện, không có ràng buộc bắt đầu hiệu lực nào được cung cấp bởi `nbf`.

Tuy nhiên, một profile, giao thức hoặc chính sách ứng dụng có thể yêu cầu claim này. Nếu hợp đồng tích hợp quy định `nbf` bắt buộc, token thiếu claim phải bị từ chối. Không được mặc định rằng `nbf` luôn tồn tại hoặc tự tạo một giá trị thay thế khi claim bị thiếu.

| Tình huống | Hành vi phù hợp |
| --- | --- |
| JWT không có `nbf`, profile không yêu cầu claim này | Không áp dụng điều kiện not-before; tiếp tục các kiểm tra khác |
| Profile hoặc chính sách yêu cầu `nbf` nhưng token thiếu claim | Từ chối |
| `nbf` có mặt và là NumericDate hợp lệ ở tương lai | Chưa chấp nhận cho tới khi đạt điều kiện thời gian |
| `nbf` có mặt nhưng sai kiểu dữ liệu | Từ chối token không hợp lệ |
| `nbf` có mặt và đã ở quá khứ | Điều kiện `nbf` đạt, nhưng token vẫn cần qua mọi kiểm tra khác |

Với access token hoặc token dùng cho tài nguyên nhạy cảm, việc có bắt buộc `nbf` hay không cần dựa trên profile và yêu cầu nghiệp vụ. Không nên thêm claim chỉ để có vẻ an toàn nếu hệ thống không có nhu cầu trì hoãn hiệu lực; cũng không nên bỏ qua claim khi bên phát hành đã sử dụng nó để giới hạn thời điểm.

## 6. Phân biệt `nbf` với `iat` và `exp`

Ba claim thời gian có liên quan nhưng không thể thay thế cho nhau:

| Claim | Tên | Ý nghĩa | Điều kiện thời gian thường dùng |
| --- | --- | --- | --- |
| `iat` | Issued At | Thời điểm token được phát hành | Ghi nhận thời điểm phát hành; chính sách có thể giới hạn token quá cũ hoặc thời điểm phát hành bất hợp lý |
| `nbf` | Not Before | Thời điểm token bắt đầu được chấp nhận | `now >= nbf` (có thể áp dụng leeway) |
| `exp` | Expiration Time | Thời điểm token hết hạn | `now < exp` (có thể áp dụng leeway) |

Ví dụ:

```json
{
  "iat": 1893452400,
  "nbf": 1893452460,
  "exp": 1893456000
}
```

Trong ví dụ:

- `iat` cho biết token được phát hành lúc `1893452400`.
- `nbf` cho biết token chưa được chấp nhận trước `1893452460`.
- `exp` cho biết token hết hạn tại hoặc sau `1893456000`.

Do đó, token được tạo trước nhưng có thể được lên lịch để bắt đầu hiệu lực sau đó. `iat` không tự động cho phép sử dụng token; token phát hành lúc 09:00 nhưng có `nbf` lúc 10:00 vẫn chưa được chấp nhận lúc 09:30.

Không được nhầm `iat` với `nbf`: `iat` ghi nhận thời điểm phát hành, còn `nbf` đặt ra ranh giới bắt đầu chấp nhận. Cũng không được nhầm `nbf` với `exp`: một claim đặt mốc bắt đầu, claim còn lại đặt mốc kết thúc.

## 7. Kết hợp `nbf` với `exp`: khoảng hiệu lực của token

Khi JWT chứa cả `nbf` và `exp`, hai claim cùng xác định một khoảng thời gian sử dụng. Không có leeway, điều kiện thời gian có thể biểu diễn:

\[
\text{nbf} \leq \text{now} < \text{exp}
\]

Đầu khoảng được bao gồm (`now = nbf` được chấp nhận theo `nbf`), còn cuối khoảng không được bao gồm (`now = exp` bị từ chối theo `exp`).

Ví dụ:

```json
{
  "nbf": 1893452460,
  "exp": 1893456000
}
```

| Thời gian hiện tại | Kết quả xét hai claim |
| --- | --- |
| `1893452459` | Từ chối: chưa đến `nbf` |
| `1893452460` | Chấp nhận bước kiểm tra thời gian: đúng `nbf` |
| `1893454200` | Chấp nhận bước kiểm tra thời gian: nằm trong khoảng hiệu lực |
| `1893455999` | Chấp nhận bước kiểm tra thời gian: trước `exp` |
| `1893456000` | Từ chối: đã đến `exp` |

Nếu `nbf` bằng hoặc lớn hơn `exp`, không có khoảng hiệu lực thông thường nào thỏa mãn cả hai điều kiện khi không có leeway. Bên phát hành nên tránh tạo token có khoảng thời gian rỗng hoặc đảo ngược; bên nhận có thể từ chối các trường hợp này theo chính sách định dạng và tính nhất quán của token.

Khi có leeway, điều kiện thường được kiểm tra riêng cho từng claim:

\[
\text{now} + L_{nbf} \geq \text{nbf}
\]

\[
\text{now} < \text{exp} + L_{exp}
\]

`L_nbf` và `L_exp` là dung sai cho từng ranh giới; một số hệ thống dùng chung một cấu hình leeway. Không nên vô tình cộng leeway hai lần hoặc diễn giải một giá trị dung sai theo đơn vị khác nhau ở các thành phần.

## 8. Các trường hợp sử dụng `nbf`

`nbf` hữu ích khi bên phát hành cần tạo token trước thời điểm sử dụng nhưng muốn trì hoãn thời điểm token được chấp nhận.

### Token được kích hoạt theo lịch

Một hệ thống lập lịch có thể tạo token cho một phiên làm việc bắt đầu lúc 08:00 ngày hôm sau. Token được phát hành trước để phân phối hoặc chuẩn bị, nhưng `nbf` đặt tại thời điểm bắt đầu phiên. Resource server từ chối token trước mốc đó.

### Quyền truy cập theo cửa sổ thời gian

Một tài nguyên có thể chỉ được truy cập trong một khoảng thời gian đã định. Bên phát hành đặt `nbf` ở đầu khoảng và `exp` ở cuối khoảng. Resource server kiểm tra cả hai claim để bảo đảm token không được dùng trước hoặc sau cửa sổ đã cấp.

### Quy trình phê duyệt có hiệu lực trong tương lai

Một quyết định cấp quyền có thể được duyệt hôm nay nhưng chỉ có hiệu lực từ ngày mai. Token đại diện cho quyền đó có thể chứa `nbf` trong tương lai. Việc tạo token sớm không có nghĩa quyền đã có thể sử dụng ngay.

Các ví dụ này chỉ mô tả cách dùng claim thời gian. `nbf` không tự kiểm tra lịch làm việc, trạng thái phê duyệt, vị trí, thiết bị hoặc điều kiện nghiệp vụ khác. Nếu các điều kiện đó thay đổi, hệ thống vẫn cần cơ chế cập nhật hoặc thu hồi quyền phù hợp.

## 9. `nbf` không thay thế xác minh mật mã và authorization

Payload của JWT có thể được đọc mà không cần xác minh chữ ký. Với JWS, phần payload thường chỉ được mã hóa Base64URL, không được mã hóa bí mật. Vì vậy, kẻ tấn công có thể tạo hoặc sửa một payload để khai báo `nbf` đã ở trong quá khứ.

Ví dụ payload chưa xác minh:

```json
{
  "sub": "user-7821",
  "nbf": 1
}
```

Việc `nbf` có giá trị nhỏ không chứng minh issuer thực sự cấp token với thời điểm đó. Bên nhận phải xác minh bảo vệ mật mã của JWT theo định dạng và profile, giới hạn thuật toán và khóa theo cấu hình tin cậy, rồi mới sử dụng claims để ra quyết định.

Ngoài ra, `nbf` chỉ là một ràng buộc thời gian. Token đã đến `nbf` không đồng nghĩa người dùng được phép thực hiện mọi hành động. Bên nhận vẫn phải kiểm tra:

- `iss`: token đến từ issuer được tin cậy.
- `aud`: token được cấp cho đúng tài nguyên nhận.
- `exp`: token chưa hết hạn.
- Token type/profile: token được dùng đúng mục đích.
- Scope, role hoặc quyền nghiệp vụ: chủ thể được phép thực hiện hành động cụ thể.
- Trạng thái thu hồi hoặc phiên đăng nhập nếu hệ thống yêu cầu khả năng vô hiệu hóa sớm.

Một token có chữ ký hợp lệ và `nbf` đã đạt vẫn có thể bị từ chối vì issuer sai, audience sai, đã hết hạn hoặc không đủ quyền.

## 10. Quy trình kiểm tra `nbf` an toàn

Một resource server có thể áp dụng quy trình tổng quát sau:

1. Kiểm tra cấu trúc JWT và xác minh chữ ký/MAC hoặc cơ chế bảo vệ mật mã tương ứng.
2. Chỉ đọc claims từ token đã được xác minh.
3. Nếu profile yêu cầu `nbf`, xác nhận claim tồn tại.
4. Nếu claim có mặt, xác nhận giá trị là NumericDate hợp lệ.
5. Lấy thời gian hiện tại từ đồng hồ đáng tin cậy, cùng đơn vị giây.
6. Kiểm tra điều kiện `now + leeway >= nbf` theo chính sách đã cấu hình.
7. Kiểm tra `exp`, issuer, audience, token type và các điều kiện khác.
8. Chỉ chấp nhận token nếu toàn bộ chính sách bắt buộc đều đạt.

Giả mã minh họa:

```text
REQUIRE_NBF = false
CLOCK_SKEW_LEEWAY_SECONDS = 30

function notBeforeSatisfied(claims, nowEpochSeconds):
    if claims.nbf is missing:
        return not REQUIRE_NBF

    if claims.nbf is not a valid NumericDate:
        return false

    return nowEpochSeconds + CLOCK_SKEW_LEEWAY_SECONDS >= claims.nbf

function validateRequest(token):
    claims = verifyTokenAndReadClaims(token)

    if verification failed:
        reject("invalid token")

    now = trustedCurrentUnixTimeInSeconds()

    if not notBeforeSatisfied(claims, now):
        reject("token is not active yet or required nbf is missing")

    if not expirationIssuerAudienceAndOtherChecksPass(claims, now):
        reject("token does not satisfy validation policy")

    accept(claims)
```

Đây là giả mã mô tả chính sách, không phải API của một thư viện cụ thể. Ví dụ đặt `REQUIRE_NBF = false` để minh họa JWT tổng quát, nơi claim này tùy chọn. Với profile hoặc ứng dụng bắt buộc `nbf`, đặt chính sách tương ứng và từ chối token thiếu claim. Trong thực tế nên dùng thư viện JWT được duy trì tốt, cấu hình rõ leeway và các điều kiện xác minh thay vì tự xây dựng bộ phân tích và xác minh mật mã.

## 11. Lỗi thường gặp khi xử lý `nbf`

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chấp nhận token trước `nbf` | Token được sử dụng sớm hơn thời điểm issuer cho phép | Kiểm tra `now >= nbf` hoặc quy tắc leeway đã định nghĩa |
| Dùng `now > nbf` thay vì `now >= nbf` | Từ chối sai token tại đúng thời điểm bắt đầu | Dùng ranh giới bao gồm `nbf` theo RFC |
| Nhầm `nbf` với `iat` | Cho rằng token phát hành là dùng được ngay | Phân biệt thời điểm phát hành và thời điểm bắt đầu hiệu lực |
| Nhầm `nbf` với `exp` | Đảo ngược quy tắc thời gian | `nbf` là cận dưới, `exp` là cận trên không bao gồm |
| Đọc `nbf` từ payload chưa xác minh | Kẻ tấn công có thể sửa thời điểm bắt đầu | Xác minh bảo vệ mật mã trước khi tin claims |
| So sánh giây với mili giây | Token bị từ chối hoặc chấp nhận sai | Chuẩn hóa thời gian về NumericDate tính bằng giây |
| Chấp nhận chuỗi hoặc kiểu dữ liệu tùy ý | Dữ liệu sai định dạng có thể vượt kiểm tra | Kiểm tra NumericDate nghiêm ngặt |
| Leeway quá lớn | Token có thể được chấp nhận quá sớm | Chỉ dùng dung sai nhỏ, có kiểm soát |
| Bỏ qua `nbf` dù profile yêu cầu | Token chưa đến thời điểm hiệu lực vẫn được sử dụng | Tuân thủ yêu cầu profile và từ chối khi thiếu hoặc chưa đạt |
| Coi `nbf` đã đạt là đủ quyền | Chủ thể có thể truy cập vượt quyền | Kiểm tra audience, scope, role và chính sách nghiệp vụ riêng |
| Không kiểm tra quan hệ `nbf` và `exp` | Có thể phát hành token có khoảng hiệu lực rỗng hoặc đảo ngược | Kiểm tra tính nhất quán theo profile và chính sách |

## 12. Tình huống thực tế

Một nhà cung cấp dịch vụ tổ chức phiên truy cập kho hàng từ 09:00 đến 11:00 UTC. Token được phát hành lúc 08:30 UTC để thiết bị có thể tải trước, nhưng chỉ được dùng khi phiên bắt đầu:

```json
{
  "iss": "https://identity.example.com/",
  "sub": "warehouse-operator-17",
  "aud": "https://api.example.com/inventory",
  "iat": 1893486600,
  "nbf": 1893488400,
  "exp": 1893495600,
  "scope": "inventory.read inventory.update"
}
```

Resource server xác minh token và áp dụng `nbf` cùng `exp`:

- Trước 09:00 UTC: token bị từ chối vì chưa đến `nbf`.
- Từ 09:00 đến trước 11:00 UTC: điều kiện thời gian đạt; các kiểm tra issuer, audience và quyền vẫn phải đạt.
- Tại hoặc sau 11:00 UTC: token bị từ chối do `exp`.

Việc thiết bị đã tải token lúc 08:30 không làm thay đổi thời điểm hiệu lực. Nếu lịch phiên bị hủy lúc 08:45, `nbf` cũng không tự biết sự kiện hủy; hệ thống cần thu hồi token hoặc kiểm tra trạng thái phiên nếu cần ngăn token được sử dụng lúc 09:00.

## 13. Kịch bản kiểm thử `nbf`

Giả sử hệ thống hỗ trợ `nbf` tùy chọn và cấu hình leeway bằng 30 giây. Nên kiểm thử tối thiểu:

| Trường hợp | Kỳ vọng | Mục tiêu |
| --- | --- | --- |
| `nbf` là NumericDate hợp lệ trong tương lai, chưa tới leeway | Từ chối | Token chưa có hiệu lực |
| `now + L` nhỏ hơn `nbf` một giây | Từ chối | Kiểm tra ranh giới dưới |
| `now + L` đúng bằng `nbf` | Chấp nhận bước `nbf` | Kiểm tra ranh giới bao gồm |
| `now` đúng bằng `nbf`, leeway bằng 0 | Chấp nhận bước `nbf` | Đúng thời điểm bắt đầu |
| `now` lớn hơn `nbf` | Chấp nhận bước `nbf` | Đã đến thời điểm hiệu lực |
| `nbf` bị thiếu và profile không yêu cầu | Không từ chối vì riêng `nbf` | Claim tùy chọn |
| `nbf` bị thiếu nhưng profile yêu cầu | Từ chối | Claim bắt buộc theo profile |
| `nbf` là chuỗi, boolean, object hoặc `null` | Từ chối | Kiểm tra kiểu NumericDate |
| `nbf` có giá trị xa bất thường do phát hành nhầm theo mili giây | Xử lý theo giới hạn thời gian và hợp đồng phát hành đã cấu hình | Không thể xác định lỗi đơn vị chỉ từ kiểu number; không tự chuyển đổi |
| `nbf` đúng nhưng chữ ký không hợp lệ | Từ chối toàn bộ token | Không tin claims chưa xác minh |
| `nbf` đúng nhưng `exp` đã qua | Từ chối toàn bộ token | Kiểm tra cận trên độc lập |
| `nbf` lớn hơn hoặc bằng `exp` | Từ chối theo chính sách nhất quán | Không có khoảng hiệu lực thông thường |
| `nbf` đúng nhưng issuer hoặc audience sai | Từ chối toàn bộ token | `nbf` không thay thế các kiểm tra khác |

Nên kiểm thử cả trường hợp đồng hồ xác minh chạy nhanh và chậm, leeway bằng 0, leeway tối đa theo cấu hình và lỗi lấy thời gian. Nếu không thể lấy thời gian đáng tin cậy, hệ thống không được mặc định coi điều kiện `nbf` đã đạt.

## 14. Nguyên tắc cần ghi nhớ

1. `nbf` xác định thời điểm trước đó JWT không được chấp nhận; không có leeway, token chỉ đạt điều kiện khi `now >= nbf`.
2. `nbf` sử dụng NumericDate, tính bằng giây từ Unix epoch UTC; không phải mili giây hay chuỗi ngày giờ.
3. `nbf` là claim tùy chọn trong JWT tổng quát; profile hoặc chính sách ứng dụng có thể bắt buộc claim này.
4. Tại đúng thời điểm `nbf`, token đã đạt điều kiện not-before; đây là ranh giới bao gồm.
5. Leeway có thể cho phép token được chấp nhận sớm hơn `nbf`; chỉ cấu hình dung sai nhỏ và có kiểm soát.
6. `iat` là thời điểm phát hành, `nbf` là thời điểm bắt đầu hiệu lực, `exp` là thời điểm hết hạn.
7. Khi có cả `nbf` và `exp`, cần bảo đảm khoảng hiệu lực nhất quán và kiểm tra hai ranh giới độc lập.
8. Chỉ sử dụng claims sau khi xác minh bảo vệ mật mã; `nbf` không thay thế issuer, audience, token type hoặc kiểm tra quyền.

### Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT), mục 2 và 4.1.5](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa NumericDate và claim `nbf`.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh chữ ký, thuật toán, khóa và claims theo ngữ cảnh.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và các yêu cầu kiểm tra claim.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): quy tắc xác minh ID token theo giao thức OpenID Connect.

**Kết luận:** `nbf` đặt ra thời điểm sớm nhất mà JWT có thể được chấp nhận. Bên nhận phải kiểm tra NumericDate trên claims đã xác minh, áp dụng đúng ranh giới `now >= nbf` cùng leeway nhỏ nếu cần, rồi tiếp tục kiểm tra expiration, issuer, audience, loại token và quyền.
