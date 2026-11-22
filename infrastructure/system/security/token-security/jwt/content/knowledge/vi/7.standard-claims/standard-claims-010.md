# Quan hệ và kiểm tra tính hợp lệ giữa các mốc thời gian trong JWT

## 1. Vì sao cần kiểm tra các mốc thời gian cùng nhau?

JSON Web Token (JWT) có thể chứa nhiều claim thời gian, thường gặp nhất là:

- `iat` (*Issued At*): thời điểm token được phát hành.
- `nbf` (*Not Before*): thời điểm token bắt đầu được chấp nhận.
- `exp` (*Expiration Time*): thời điểm token hết hạn.

Mỗi claim trả lời một câu hỏi riêng. Khi xuất hiện cùng nhau, chúng tạo thành bối cảnh thời gian của token. Chỉ kiểm tra từng giá trị riêng lẻ có thể bỏ sót một tổ hợp vô lý, ví dụ token hết hạn trước cả thời điểm được phép sử dụng, hoặc token khai báo được phát hành sau thời điểm hết hạn.

Ví dụ, một token có `nbf` là 10:00 UTC nhưng `exp` là 09:00 UTC không có khoảng thời gian nào để sử dụng theo hai claim này. Một token có `iat` ở tương lai quá xa so với đồng hồ bên nhận cũng cần được xem xét, vì giá trị thời gian có thể phản ánh lỗi đồng hồ hoặc dữ liệu phát hành sai.

Việc kiểm tra cần kết hợp ba lớp:

1. **Ý nghĩa chuẩn của từng claim:** `nbf` là cận bắt đầu, `exp` là cận kết thúc, `iat` ghi nhận thời điểm phát hành.
2. **Tính nhất quán giữa các claim:** các mốc phải tạo thành một khoảng thời gian hợp lý theo loại token và profile.
3. **Thời gian tại bên nhận:** đồng hồ đáng tin cậy, đơn vị thống nhất và leeway được cấu hình rõ ràng.

## 2. Ý nghĩa và quy tắc cơ bản của từng claim

Ba claim này sử dụng **NumericDate**: số giây tính từ Unix Epoch `1970-01-01T00:00:00Z` theo quy ước UTC/POSIX, bỏ qua leap seconds. Giá trị được biểu diễn bằng JSON number, có thể là số nguyên hoặc số không nguyên.

| Claim | Ý nghĩa | Điều kiện cơ bản khi claim có mặt |
| --- | --- | --- |
| `iat` | Thời điểm token được phát hành | Ghi nhận thời điểm phát hành; ứng dụng có thể dùng để kiểm tra thời điểm tương lai hoặc tuổi token |
| `nbf` | Thời điểm token bắt đầu có hiệu lực | Không chấp nhận token trước `nbf`; tại đúng `nbf` đã đạt điều kiện |
| `exp` | Thời điểm token hết hạn | Không chấp nhận token tại hoặc sau `exp` |

Theo [RFC 7519](https://www.rfc-editor.org/rfc/rfc7519), các claim này là tùy chọn ở cấp JWT tổng quát. Profile hoặc giao thức cụ thể có thể yêu cầu một hay nhiều claim. Nếu claim có mặt, giá trị phải đúng kiểu NumericDate và bên nhận phải xử lý theo ý nghĩa của nó.

### Ranh giới khi không có leeway

Với thời gian hiện tại `now`:

**`nbf`:**

\[
\text{now} \geq \text{nbf}
\]

**`exp`:**

\[
\text{now} < \text{exp}
\]

**Tuổi token dựa trên `iat` (nếu ứng dụng áp dụng max-age):**

\[
\text{tokenAge} = \text{now} - \text{iat}
\]

`iat` tự nó không đặt một ranh giới bắt đầu hoặc kết thúc hiệu lực. RFC 7519 nói claim này có thể được dùng để xác định tuổi JWT; ngưỡng tuổi tối đa và chính sách từ chối `iat` nằm trong tương lai cần được profile hoặc ứng dụng quy định.

## 3. Quy tắc RFC và quy tắc nhất quán của ứng dụng

Điểm quan trọng khi thiết kế validator là phân biệt yêu cầu được RFC quy định với các điều kiện bổ sung do hệ thống đặt ra.

RFC 7519 định nghĩa ý nghĩa và cách xử lý từng claim thời gian, nhưng không đặt ra một bộ bất đẳng thức bắt buộc duy nhất cho mọi tổ hợp `iat`, `nbf` và `exp`. Profile JWT hoặc hợp đồng tích hợp có thể quy định chặt chẽ hơn.

Ví dụ các kiểm tra nhất quán thường được một ứng dụng chọn:

| Kiểm tra | Mục đích | Tính chất |
| --- | --- | --- |
| `nbf < exp` khi cả hai claim được dùng để giới hạn cửa sổ hiệu lực | Bảo đảm tồn tại khoảng thời gian có thể sử dụng token | Quy tắc nhất quán hợp lý cho token có cửa sổ hiệu lực |
| `iat < exp` khi yêu cầu token có tuổi thọ dương | Bảo đảm thời điểm hết hạn nằm sau thời điểm phát hành | Chính sách ứng dụng/profile; RFC JWT tổng quát không đặt một quy tắc thứ tự phổ quát cho mọi token |
| `iat <= now + futureSkew` | Phát hiện thời điểm phát hành nằm quá xa trong tương lai | Chính sách kiểm tra đồng hồ của bên nhận |
| `now - iat <= maxAge` | Giới hạn tuổi token tại thời điểm xử lý | Chính sách max-age, không phải mặc định bắt buộc của mọi JWT |
| `exp - iat <= maxLifetime` | Giới hạn thời lượng tối đa được issuer cấp | Chính sách vòng đời token/profile |

Không được trình bày các điều kiện bổ sung này như thể mọi JWT theo RFC 7519 đều bắt buộc phải tuân thủ chúng. Hãy ghi rõ profile và chính sách đang áp dụng, đặc biệt khi tích hợp nhiều issuer hoặc nhiều loại token.

## 4. Khoảng hiệu lực khi có `nbf` và `exp`

Nếu token có cả `nbf` và `exp`, hai claim tạo thành một khoảng thời gian chấp nhận. Không có leeway:

\[
\boxed{\text{nbf} \leq \text{now} < \text{exp}}
\]

Đầu khoảng được bao gồm: tại đúng `nbf`, token đã đạt điều kiện Not Before. Cuối khoảng không được bao gồm: tại đúng `exp`, token đã hết hạn.

Ví dụ:

```json
{
  "nbf": 1700000060,
  "exp": 1700003600
}
```

| `now` | Kết quả xét `nbf` và `exp` | Giải thích |
| --- | --- | --- |
| `1700000059` | Từ chối | Chưa đến `nbf` |
| `1700000060` | Chấp nhận bước kiểm tra thời gian | Đúng `nbf` và còn trước `exp` |
| `1700001800` | Chấp nhận bước kiểm tra thời gian | Nằm trong khoảng hiệu lực |
| `1700003599` | Chấp nhận bước kiểm tra thời gian | Vẫn trước `exp` |
| `1700003600` | Từ chối | Đã đến `exp` |

### Khi `nbf` bằng hoặc lớn hơn `exp`

Nếu `nbf = exp`, không tồn tại thời điểm nào thỏa mãn đồng thời `now >= nbf` và `now < exp`. Nếu `nbf > exp`, khoảng thời gian còn bị đảo ngược. Với token mà hai claim này cùng xác định cửa sổ hiệu lực, ứng dụng nên từ chối tổ hợp như vậy ngay cả khi leeway có thể tạo ra một khoảng chấp nhận số học.

Leeway không nên được dùng để che giấu một khoảng hiệu lực được phát hành sai. Hãy kiểm tra tính nhất quán của các mốc do issuer khai báo trước khi áp dụng dung sai cho sai lệch đồng hồ.

## 5. Quan hệ giữa `iat` và `nbf`

`iat` ghi nhận lúc token được phát hành; `nbf` xác định lúc token bắt đầu được chấp nhận. Hai mốc này không nhất thiết phải bằng nhau.

### Token được phát hành và sử dụng ngay

Nếu token có hiệu lực ngay khi phát hành, `nbf` có thể bị bỏ qua hoặc được đặt bằng/nhỏ hơn `iat`:

```json
{
  "iat": 1700000000,
  "nbf": 1700000000,
  "exp": 1700003600
}
```

### Token được phát hành trước nhưng có hiệu lực trong tương lai

Một token có thể được tạo trước để phân phối hoặc chuẩn bị, nhưng chỉ được chấp nhận từ thời điểm sau đó:

```json
{
  "iat": 1700000000,
  "nbf": 1700000600,
  "exp": 1700003600
}
```

Khoảng từ `iat` đến `nbf` là thời gian token đã được phát hành nhưng chưa được phép sử dụng. Đây là trường hợp hợp lý khi ứng dụng hỗ trợ token được kích hoạt theo lịch.

### `nbf` nằm trước `iat`

Ví dụ:

```json
{
  "nbf": 1699999900,
  "iat": 1700000000,
  "exp": 1700003600
}
```

Token đã qua mốc Not Before tại thời điểm phát hành, vì vậy điều kiện `nbf` đã đạt khi token được tạo. Tổ hợp này không mâu thuẫn về mặt thời gian, dù `nbf` có thể không cần thiết nếu token luôn được phát hành sau khi đã có hiệu lực.

Không nên áp dụng quy tắc `iat <= nbf` như một điều kiện phổ quát cho mọi JWT. Nếu profile của ứng dụng yêu cầu token phải được phát hành trước thời điểm bắt đầu hiệu lực, hãy áp dụng quy tắc đó như một ràng buộc riêng.

## 6. Quan hệ giữa `iat` và `exp`

`iat` cho biết lúc phát hành, `exp` đặt giới hạn hết hạn. Với token có thời hạn dương, một chính sách phổ biến là yêu cầu:

\[
\text{iat} < \text{exp}
\]

Điều này giúp tránh token có thời điểm hết hạn nằm trước hoặc đúng thời điểm phát hành. Tuy nhiên, cần ghi rõ đây là quy tắc nhất quán do profile hoặc ứng dụng chọn; không nên nhầm nó với một phép kiểm tra thứ tự được RFC 7519 quy định chung cho mọi loại JWT.

### `exp` trước `iat`

```json
{
  "iat": 1700003600,
  "exp": 1700000000
}
```

Theo chính sách yêu cầu token có thời hạn dương, token này phải bị từ chối vì đã hết hạn trước khi được phát hành.

### `exp` bằng `iat`

```json
{
  "iat": 1700000000,
  "exp": 1700000000
}
```

Token không có khoảng sử dụng dương theo hai mốc này. Nếu hệ thống yêu cầu token phải có một cửa sổ sử dụng, hãy từ chối trường hợp `exp <= iat`.

### Giới hạn tuổi thọ khai báo

Nếu ứng dụng đặt `maxLifetime`, có thể kiểm tra:

\[
\text{exp} - \text{iat} \leq \text{maxLifetime}
\]

Đây là **thời lượng được cấp khi phát hành**, không phải tuổi token hiện tại. Ví dụ, token có `iat` lúc 08:00 UTC và `exp` lúc 09:00 UTC có tuổi thọ khai báo là 60 phút. Khi request đến lúc 08:10 UTC, tuổi hiện tại của token mới là 10 phút.

## 7. Phân biệt token age và declared lifetime

Hai phép tính thường bị nhầm lẫn:

| Khái niệm | Công thức | Ý nghĩa |
| --- | --- | --- |
| Token age | `now - iat` | Token đã được phát hành bao lâu tại thời điểm xác minh |
| Declared lifetime | `exp - iat` | Khoảng thời gian issuer đã cấp từ lúc phát hành đến lúc hết hạn |
| Remaining lifetime | `exp - now` | Thời gian còn lại trước mốc hết hạn theo đồng hồ hiện tại |

Ví dụ:

```text
iat = 1700035200  # 08:00 UTC
exp = 1700038800  # 09:00 UTC
now = 1700035800  # 08:10 UTC

tokenAge = now - iat
         = 600 seconds

declaredLifetime = exp - iat
                 = 3600 seconds

remainingLifetime = exp - now
                  = 3000 seconds
```

Ba giá trị phục vụ các chính sách khác nhau:

- Max-age giới hạn `tokenAge`.
- Max-lifetime giới hạn `declaredLifetime`.
- `exp` xác định mốc hết hạn tuyệt đối; `remainingLifetime` chỉ cho biết còn bao lâu theo thời gian hiện tại.

Một token có thể chưa vượt max-age nhưng có declared lifetime quá dài. Ngược lại, token có declared lifetime một giờ vẫn có thể đã quá cũ nếu được phát hành từ nhiều giờ trước và `exp` bị đặt sai hoặc không được kiểm tra.

## 8. Xử lý `iat` nằm trong tương lai

Do issuer và verifier có thể lệch đồng hồ, `iat` có thể lớn hơn `now` một khoảng nhỏ. Ứng dụng nên đặt giới hạn future skew rõ ràng thay vì chấp nhận mọi giá trị.

Gọi `L_future` là dung sai thời gian tương lai:

\[
\text{iat} \leq \text{now} + L_{future}
\]

Nếu `iat` lớn hơn `now + L_future`, token có timestamp phát hành ở tương lai vượt quá dung sai và nên bị từ chối theo chính sách này.

Ví dụ `now = 1700000000`, `L_future = 30` giây:

| `iat` | Kết quả |
| --- | --- |
| `1699999970` | Chấp nhận bước kiểm tra timestamp tương lai |
| `1700000000` | Chấp nhận, trùng `now` |
| `1700000030` | Chấp nhận trong dung sai |
| `1700000031` | Từ chối vì vượt dung sai |

RFC 7519 định nghĩa `iat` là thời điểm phát hành và cho phép dùng nó để xác định tuổi JWT; nó không bắt buộc một giá trị future skew chung cho mọi ứng dụng. Ngưỡng dung sai phải phù hợp với đồng hồ, profile và rủi ro của hệ thống.

## 9. Leeway và cách kết hợp các điều kiện

RFC 7519 cho phép bên xử lý áp dụng một khoảng dung sai nhỏ để xử lý clock skew, thường không quá vài phút. Leeway là cấu hình của verifier, không phải một claim và không thay đổi mốc thời gian trong JWT.

Gọi:

- `L_nbf`: leeway cho `nbf`.
- `L_exp`: leeway cho `exp`.
- `L_future`: dung sai timestamp tương lai của `iat` theo chính sách ứng dụng.

Các điều kiện minh họa:

\[
\text{now} + L_{nbf} \geq \text{nbf}
\]

\[
\text{now} < \text{exp} + L_{exp}
\]

\[
\text{iat} \leq \text{now} + L_{future}
\]

Khi dùng chung một `L` cho `nbf` và `exp`, cửa sổ chấp nhận theo hai claim có thể biểu diễn:

\[
\text{nbf} - L \leq \text{now} < \text{exp} + L
\]

Điều này cho thấy leeway có thể chấp nhận token sớm hơn `nbf` và muộn hơn `exp`. Tuy nhiên, **không dùng leeway để hợp thức hóa thứ tự claim sai**. Nếu profile yêu cầu `nbf < exp`, vẫn phải kiểm tra điều kiện đó trên các giá trị gốc trước khi áp dụng dung sai.

Không nên cộng leeway hai lần, ví dụ thư viện đã áp dụng dung sai cho `exp` rồi ứng dụng lại tự cộng thêm cùng một khoảng. Hãy đọc rõ chính sách và hành vi validator đang sử dụng.

## 10. Claim tùy chọn, claim bắt buộc và tổ hợp thiếu dữ liệu

Ở cấp JWT tổng quát, `iat`, `nbf`, `exp` là các registered claim tùy chọn. Khi một claim vắng mặt, bên nhận không có mốc thời gian tương ứng để kiểm tra. Profile hoặc ứng dụng có thể yêu cầu claim đó phải có.

| Tổ hợp claim | Điều có thể kiểm tra | Lưu ý |
| --- | --- | --- |
| Chỉ có `iat` | Thời điểm phát hành, future skew, max-age nếu chính sách yêu cầu | Không có cận bắt đầu hoặc kết thúc từ `nbf`/`exp` |
| Chỉ có `nbf` | Token đã đến thời điểm bắt đầu chưa | Không có cận hết hạn từ `exp` |
| Chỉ có `exp` | Token đã hết hạn chưa | Không có mốc bắt đầu hoặc tuổi token từ `iat` |
| Có `iat` và `exp` | Future `iat`, max-age, max-lifetime, expiration | Không có `nbf` để trì hoãn hiệu lực |
| Có `iat` và `nbf` | Future `iat`, thời điểm bắt đầu hiệu lực | Không có `exp` để xác định hạn cuối |
| Có `nbf` và `exp` | Cửa sổ hiệu lực và thứ tự hai mốc | Có thể kiểm tra `nbf < exp` |
| Có cả ba | Có thể kiểm tra toàn bộ mốc, tuổi token và cửa sổ hiệu lực | Phải áp dụng đúng profile và chính sách |

Nếu profile yêu cầu `exp` nhưng token thiếu claim, phải từ chối theo profile. Không tự coi token thiếu `exp` là không bao giờ hết hạn nếu chính sách bảo mật yêu cầu thời hạn hữu hạn. Tương tự, không tự gán `iat = now` hoặc `nbf = now` khi claim bị thiếu.

## 11. Các mẫu quan hệ thời gian thường gặp

Các ví dụ dưới đây dùng cùng một đơn vị NumericDate và giả định thời gian hiện tại là `now = 1700000100`.

| Mẫu | `iat` | `nbf` | `exp` | Đánh giá theo ví dụ |
| --- | ---: | ---: | ---: | --- |
| Token đã có hiệu lực | `1700000000` | `1700000000` | `1700003600` | Hợp lý; `now` nằm trong cửa sổ |
| Token được lên lịch | `1700000000` | `1700000600` | `1700003600` | Hợp lý; hiện tại còn trước `nbf` |
| `nbf` trước lúc phát hành | `1699999900` | `1700000000` | `1700003600` | Hợp lý; `nbf` đã đạt khi phát hành |
| Token hết hạn | `1699990000` | `1699990000` | `1700000000` | Không còn hợp lệ tại `now` |
| Cửa sổ rỗng | `1700000000` | `1700003600` | `1700003600` | Từ chối theo chính sách cửa sổ không rỗng |
| Cửa sổ đảo ngược | `1700000000` | `1700004000` | `1700003600` | Từ chối |
| Hết hạn trước khi phát hành | `1700004000` | `1700004000` | `1700003600` | Từ chối theo chính sách chronology |
| `iat` ở tương lai | `1700000200` | `1700000200` | `1700003600` | Từ chối nếu vượt future-skew tolerance |

Các đánh giá “từ chối theo chính sách chronology” là quy tắc nhất quán ứng dụng. Hãy đối chiếu với profile thực tế trước khi triển khai để tránh áp đặt một điều kiện không thuộc hợp đồng token.

## 12. Quy trình xác minh tổng thể

Một validator nên xử lý thời gian trong bối cảnh xác minh token hoàn chỉnh:

1. Xác định loại token và profile dự kiến từ cấu hình đáng tin cậy.
2. Kiểm tra cấu trúc JWT và xác minh chữ ký/MAC hoặc cơ chế bảo vệ mật mã tương ứng bằng thuật toán, khóa được phép.
3. Chỉ sử dụng claims đã được xác minh cho quyết định tin cậy.
4. Kiểm tra sự hiện diện của các claim bắt buộc theo profile.
5. Kiểm tra `iat`, `nbf`, `exp` nếu có mặt đều là NumericDate hợp lệ, cùng đơn vị giây và trong phạm vi hệ thống hỗ trợ.
6. Lấy `now` từ wall clock đáng tin cậy theo Unix time; xác nhận đồng hồ ở trạng thái vận hành chấp nhận được.
7. Kiểm tra timestamp tương lai của `iat` theo future-skew policy nếu được áp dụng.
8. Kiểm tra quan hệ nhất quán giữa các mốc theo profile/chính sách, ví dụ `nbf < exp` và `iat < exp` khi yêu cầu tuổi thọ dương.
9. Kiểm tra `nbf`, `exp`, max-age và max-lifetime với leeway đã cấu hình, tránh áp dụng dung sai hai lần.
10. Kiểm tra issuer, audience, token type, quyền và trạng thái thu hồi.
11. Chỉ chấp nhận token nếu mọi điều kiện bắt buộc đều đạt.

### Giả mã minh họa

```text
REQUIRE_IAT = true
REQUIRE_NBF = false
REQUIRE_EXP = true

MAX_TOKEN_AGE_SECONDS = 900
MAX_DECLARED_LIFETIME_SECONDS = 3600
FUTURE_IAT_SKEW_SECONDS = 30
NBF_LEEWAY_SECONDS = 30
EXP_LEEWAY_SECONDS = 30

function isNumericDate(value):
    return value is a finite JSON number

function validateTimeClaims(claims, now):
    if REQUIRE_IAT and claims.iat is missing:
        return false
    if REQUIRE_NBF and claims.nbf is missing:
        return false
    if REQUIRE_EXP and claims.exp is missing:
        return false

    for claim in [claims.iat, claims.nbf, claims.exp]:
        if claim exists and not isNumericDate(claim):
            return false

    if claims.iat exists:
        if claims.iat > now + FUTURE_IAT_SKEW_SECONDS:
            return false

        if now - claims.iat > MAX_TOKEN_AGE_SECONDS:
            return false

    if claims.nbf exists and claims.exp exists:
        if claims.nbf >= claims.exp:
            return false

    if claims.iat exists and claims.exp exists:
        if claims.exp <= claims.iat:
            return false
        if claims.exp - claims.iat > MAX_DECLARED_LIFETIME_SECONDS:
            return false

    if claims.nbf exists:
        if now + NBF_LEEWAY_SECONDS < claims.nbf:
            return false

    if claims.exp exists:
        if now >= claims.exp + EXP_LEEWAY_SECONDS:
            return false

    return true
```

Đây là giả mã minh họa một chính sách cụ thể, không phải quy tắc bắt buộc của mọi JWT hoặc API của thư viện. Ví dụ đặt `iat` và `exp` bắt buộc, `nbf` tùy chọn, đồng thời áp dụng max-age, max-lifetime và leeway riêng. Một hệ thống khác phải điều chỉnh các giá trị và điều kiện theo profile mà nó hỗ trợ. Trong thực tế, thư viện có thể đã kiểm tra `exp`/`nbf`; cần tránh kiểm tra trùng lặp hoặc nới thời gian ngoài dự kiến.

## 13. Lỗi thường gặp khi kiểm tra quan hệ thời gian

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ kiểm tra `exp`, bỏ qua `nbf` | Token được dùng trước thời điểm được phép | Kiểm tra cận bắt đầu khi claim có mặt hoặc được yêu cầu |
| Chỉ kiểm tra `nbf`, bỏ qua `exp` | Token đã hết hạn vẫn có thể được chấp nhận | Kiểm tra cận kết thúc độc lập |
| Coi `iat` là thời điểm bắt đầu hiệu lực | Token lên lịch có thể bị xử lý sai | Dùng `nbf` cho cận bắt đầu |
| Coi `iat` là thời điểm hết hạn | Không có giới hạn kết thúc đúng nghĩa | Dùng `exp` hoặc max-age rõ ràng |
| Không kiểm tra `nbf < exp` khi hai claim xác định cửa sổ | Chấp nhận token có khoảng hiệu lực rỗng/đảo ngược | Kiểm tra tính nhất quán trước khi áp dụng leeway |
| Không kiểm tra `iat` tương lai theo chính sách | Timestamp phát hành sai có thể làm sai tuổi token | Đặt future-skew tolerance |
| Nhầm token age với declared lifetime | Chọn sai chính sách thời hạn | Phân biệt `now - iat` với `exp - iat` |
| Coi mọi quan hệ claim là yêu cầu RFC | Từ chối nhầm token thuộc profile khác | Phân biệt quy tắc chuẩn và chính sách ứng dụng |
| Dùng leeway để bù một khoảng claim sai | Token bất hợp lý vẫn được chấp nhận | Kiểm tra chronology trên giá trị gốc |
| Cộng leeway ở thư viện rồi cộng lần nữa trong ứng dụng | Kéo dài cửa sổ chấp nhận ngoài dự kiến | Xác định rõ tầng chịu trách nhiệm kiểm tra |
| So sánh giây với mili giây | Kết quả thời gian sai nghiêm trọng | Dùng NumericDate theo giây cho mọi phép tính |
| Tin claims trước khi xác minh mật mã | Kẻ tấn công có thể sửa timestamp để vượt kiểm tra | Xác minh token trước khi tin claims |
| Tự gán thời điểm hiện tại cho claim bị thiếu | Che giấu lỗi phát hành và bỏ qua profile | Từ chối khi claim bắt buộc bị thiếu |

## 14. Tình huống thực tế

Một dịch vụ phê duyệt tài liệu phát hành token trước khi phiên phê duyệt bắt đầu. Token có thời điểm phát hành lúc 08:00 UTC, chỉ bắt đầu được chấp nhận lúc 09:00 UTC và hết hạn lúc 10:00 UTC:

```json
{
  "iss": "https://identity.example.com/",
  "sub": "reviewer-42",
  "aud": "https://api.example.com/approvals",
  "iat": 1700035200,
  "nbf": 1700038800,
  "exp": 1700042400
}
```

Resource server áp dụng chính sách:

- `iat` phải không nằm trong tương lai vượt quá dung sai và tuổi token phải nằm trong max-age.
- `nbf < exp` để bảo đảm có cửa sổ hiệu lực.
- Trước `nbf`, token bị từ chối dù chữ ký hợp lệ.
- Từ `nbf` đến trước `exp`, điều kiện thời gian đạt; issuer, audience và quyền vẫn phải đạt.
- Tại hoặc sau `exp` theo leeway, token bị từ chối.

Nếu người quản lý dời phiên phê duyệt sang ngày khác, việc sửa riêng `nbf` trong payload sẽ làm chữ ký không còn hợp lệ. Issuer phải phát hành token mới với các mốc nhất quán và `jti` mới nếu profile yêu cầu định danh token.

## 15. Kịch bản kiểm thử quan hệ thời gian

Nên kiểm thử cả giá trị riêng lẻ, quan hệ giữa claim và ranh giới thời gian:

| Trường hợp | Kỳ vọng | Mục tiêu |
| --- | --- | --- |
| `nbf < now < exp` | Đạt bước kiểm tra cửa sổ | Token nằm trong khoảng hiệu lực |
| `now = nbf` và `now < exp` | Đạt bước thời gian | Ranh giới đầu được bao gồm |
| `now = exp` với leeway bằng 0 | Từ chối | Ranh giới cuối không được bao gồm |
| `now < nbf` ngoài leeway | Từ chối | Token chưa có hiệu lực |
| `now >= exp + leeway` | Từ chối | Hết cửa sổ chấp nhận |
| `nbf = exp` | Từ chối theo chính sách cửa sổ không rỗng | Khoảng hiệu lực rỗng |
| `nbf > exp` | Từ chối | Khoảng hiệu lực đảo ngược |
| `iat < nbf < exp` | Có thể chấp nhận theo chính sách | Token được lên lịch |
| `nbf <= iat < exp` | Có thể chấp nhận theo chính sách | Token đã có hiệu lực khi phát hành |
| `iat = exp` | Từ chối nếu yêu cầu tuổi thọ dương | Không có lifetime |
| `iat > exp` | Từ chối theo chính sách chronology | Hết hạn trước phát hành |
| `iat` vượt `now + futureSkew` | Từ chối | Timestamp tương lai bất hợp lý |
| `now - iat` vượt max-age | Từ chối | Token quá cũ |
| `exp - iat` vượt max-lifetime | Từ chối | Issuer cấp lifetime quá dài |
| Một claim thời gian là chuỗi hoặc object | Từ chối | Kiểm tra NumericDate |
| Một claim bắt buộc bị thiếu | Từ chối | Tuân thủ profile |
| Claims có quan hệ hợp lý nhưng chữ ký sai | Từ chối toàn bộ token | Không tin payload chưa xác minh |
| Clock skew nằm trong leeway | Xử lý theo chính sách dung sai | Kiểm tra clock skew |
| Leeway được áp dụng ở cả thư viện và ứng dụng | Phát hiện nếu tổng dung sai vượt cấu hình | Ngăn cộng dung sai hai lần |

Nên chạy các trường hợp tại đúng ranh giới, trước một giây, sau một giây và tại ranh giới leeway. Với NumericDate có phần lẻ, kiểm thử cả độ chính xác và quy tắc làm tròn.

## 16. Nguyên tắc cần ghi nhớ

1. `iat` ghi nhận thời điểm phát hành; `nbf` là cận bắt đầu; `exp` là cận kết thúc.
2. Không có leeway, cửa sổ sử dụng khi có cả `nbf` và `exp` là `nbf <= now < exp`.
3. Nếu `nbf` và `exp` cùng xác định cửa sổ hiệu lực, ứng dụng nên từ chối `nbf >= exp`.
4. `iat` có thể trước hoặc sau `nbf` tùy token được phát hành để sử dụng ngay hay được lên lịch; không áp đặt một thứ tự phổ quát nếu profile không yêu cầu.
5. `iat < exp`, max-age và max-lifetime là các chính sách nhất quán hữu ích nhưng cần được xác định rõ theo profile/ứng dụng.
6. Phân biệt token age (`now - iat`) với declared lifetime (`exp - iat`) và remaining lifetime (`exp - now`).
7. Xử lý timestamp tương lai và leeway theo chính sách nhỏ, rõ ràng; không dùng dung sai để che giấu dữ liệu thời gian sai.
8. Phân biệt claim tùy chọn của JWT tổng quát với claim bắt buộc của profile.
9. Kiểm tra kiểu NumericDate, đơn vị giây và độ chính xác trước khi so sánh.
10. Chỉ tin claims sau khi xác minh bảo vệ mật mã; tiếp tục kiểm tra issuer, audience, token type và quyền.

### Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT), mục 2 và 4.1.4–4.1.6](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa NumericDate và các claim thời gian `exp`, `nbf`, `iat`.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh JWT, khóa, thuật toán và claims theo ngữ cảnh.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và các yêu cầu claim cụ thể.
- [OpenID Connect Core 1.0, mục 3.1.3.7](https://openid.net/specs/openid-connect-core-1_0.html#IDToken): quy tắc xác minh ID token và các claim thời gian.

**Kết luận:** Tính hợp lệ về thời gian của JWT cần xem xét `iat`, `nbf` và `exp` cùng nhau. Bên nhận phải kiểm tra ranh giới của từng claim, xác nhận các mốc tạo thành một khoảng hợp lý theo profile, áp dụng leeway có kiểm soát và phân biệt rõ quy tắc RFC với chính sách bổ sung của ứng dụng.
