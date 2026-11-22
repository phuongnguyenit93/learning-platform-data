# NumericDate: Giây tính từ Unix Epoch và lỗi nhầm mili giây

## 1. NumericDate là gì?

Trong JSON Web Token (JWT), các claim thời gian như `exp`, `nbf` và `iat` sử dụng kiểu giá trị **NumericDate**. Đây là một giá trị số biểu diễn số giây đã trôi qua kể từ mốc:

```text
1970-01-01T00:00:00Z
```

Mốc này được gọi là **Unix Epoch**. Theo [RFC 7519, mục 2](https://www.rfc-editor.org/rfc/rfc7519#section-2), NumericDate là số giây tính từ Unix Epoch theo UTC đến thời điểm cần biểu diễn, bỏ qua giây nhuận. Cách tính tương đương quy ước POSIX Seconds Since the Epoch, trong đó mỗi ngày được tính đúng 86.400 giây; RFC cũng cho phép biểu diễn giá trị không nguyên.

Ví dụ:

```json
{
  "iat": 1700000000,
  "nbf": 1700000060,
  "exp": 1700003600
}
```

Các giá trị trên đều tính bằng **giây**, không phải mili giây. Chúng lần lượt biểu diễn thời điểm phát hành, thời điểm bắt đầu có hiệu lực và thời điểm hết hạn.

Điểm cần nhớ: **NumericDate là cách biểu diễn một thời điểm, không phải một quy tắc xác thực hoàn chỉnh**. Ý nghĩa và cách kiểm tra từng claim vẫn phụ thuộc vào claim đó và profile JWT đang sử dụng.

## 2. Unix Epoch và cách đọc một NumericDate

Unix Epoch là mốc thời gian tuyệt đối tại 00:00:00 UTC ngày 1 tháng 1 năm 1970. NumericDate đo khoảng cách theo giây từ mốc đó.

Ví dụ:

| NumericDate | Thời điểm UTC tương ứng |
| --- | --- |
| `0` | `1970-01-01T00:00:00Z` |
| `1` | `1970-01-01T00:00:01Z` |
| `86400` | `1970-01-02T00:00:00Z` |
| `1700000000` | `2023-11-14T22:13:20Z` |

Vì mỗi ngày được tính là 86.400 giây, phép tính cơ bản là:

\[
\text{NumericDate} = \text{số giây từ Unix Epoch đến thời điểm UTC}
\]

Và khi cần chuyển ngược về thời điểm:

\[
\text{UTC DateTime} = \text{Unix Epoch} + \text{NumericDate seconds}
\]

NumericDate không lưu tên múi giờ hoặc offset. Nó biểu diễn một thời điểm tuyệt đối. Ví dụ, cùng một thời điểm có thể được hiển thị là `2023-11-14T22:13:20Z` ở UTC hoặc một giờ địa phương có offset khác; giá trị NumericDate vẫn giống nhau.

Khi chuyển một ngày giờ địa phương thành NumericDate, trước hết phải xác định đúng múi giờ và offset tại thời điểm đó, sau đó quy đổi về UTC. Không được bỏ thông tin múi giờ rồi coi giờ địa phương là UTC.

## 3. NumericDate là số giây, không phải mili giây

Đây là lỗi tích hợp phổ biến nhất khi tạo hoặc xác minh JWT. Nhiều hệ thống thời gian cung cấp timestamp theo mili giây, trong khi NumericDate của JWT sử dụng giây.

Quan hệ giữa hai đơn vị:

\[
1\ \text{second} = 1000\ \text{milliseconds}
\]

Do đó:

\[
\text{epochSeconds} = \frac{\text{epochMilliseconds}}{1000}
\]

Ví dụ cùng một thời điểm:

| Đơn vị | Giá trị |
| --- | ---: |
| Unix timestamp theo giây | `1700000000` |
| Unix timestamp theo mili giây | `1700000000000` |

Khi tạo JWT, nếu nguồn thời gian trả về mili giây, phải chuyển về giây trước khi ghi vào claim NumericDate. Khi xác minh, cũng phải bảo đảm `now` và giá trị claim cùng đơn vị.

### Hậu quả khi nhầm đơn vị

Giả sử thời điểm dự kiến là `1700000000` giây nhưng bên phát hành ghi `1700000000000` vào `exp` do quên chia cho 1.000. Bên nhận so sánh thời gian hiện tại tính bằng giây với giá trị `exp` lớn hơn rất nhiều, khiến token có thể được xem là chưa hết hạn trong một khoảng thời gian cực dài.

Các trường hợp khác:

| Claim | Lỗi dùng mili giây thay giây | Hậu quả thường gặp khi bên nhận mong đợi giây |
| --- | --- | --- |
| `exp` | Giá trị lớn hơn dự kiến 1.000 lần | Token có thể được chấp nhận lâu bất thường |
| `nbf` | Giá trị lớn hơn dự kiến 1.000 lần | Token có thể bị xem là chưa đến thời điểm hiệu lực trong thời gian rất dài |
| `iat` | Giá trị lớn hơn thời gian hiện tại theo giây | Token có thể bị xem là phát hành ở tương lai hoặc tuổi token âm rất lớn |

Lỗi ngược lại cũng nguy hiểm: nếu bên xác minh dùng `now` theo mili giây nhưng claim là giây, `now` có thể lớn hơn `exp` hàng nghìn lần và token bị từ chối ngay lập tức.

Không dùng số chữ số làm quy tắc xác định đơn vị. Số chữ số thay đổi theo thời đại và kiểu timestamp; một con số lớn vẫn có thể là NumericDate hợp lệ về kiểu nhưng sai theo hợp đồng tích hợp. Bên phát hành và bên nhận phải thống nhất đơn vị, kiểm thử giá trị thực tế và áp dụng giới hạn hợp lý theo chính sách. Không tự động chia hoặc nhân 1.000 dựa trên phỏng đoán.

## 4. Kiểu dữ liệu JSON của NumericDate

NumericDate được biểu diễn bằng **JSON number**. Ví dụ hợp lệ về dạng số:

```json
{
  "iat": 1700000000,
  "nbf": 1700000060.5,
  "exp": 1700003600
}
```

RFC 7519 cho phép giá trị không nguyên, vì vậy phần lẻ của giây có thể được biểu diễn. Tuy nhiên, bên phát hành và bên nhận cần thống nhất độ chính xác thực tế mà hệ thống hỗ trợ.

Những ví dụ sai kiểu:

```json
{
  "iat": "1700000000",
  "nbf": "2023-11-14T22:14:20Z",
  "exp": null
}
```

| Giá trị | Đánh giá | Giải thích |
| --- | --- | --- |
| `1700000000` | Hợp lệ về kiểu | JSON number, biểu diễn giây |
| `1700000000.5` | Hợp lệ về kiểu | JSON number có phần lẻ |
| `"1700000000"` | Sai kiểu | Chuỗi số không phải JSON number |
| `"2023-11-14T22:13:20Z"` | Sai kiểu | Chuỗi ISO 8601 không phải NumericDate |
| `null` | Sai kiểu | Không phải số |
| `true` | Sai kiểu | Boolean không phải số |
| `[]` hoặc `{}` | Sai kiểu | Array/object không phải số |

Không nên ép kiểu tùy tiện từ chuỗi, boolean hoặc object sang số. Nếu claim có mặt nhưng sai kiểu, cách xử lý an toàn là từ chối token theo quy tắc định dạng/profile, thay vì cố diễn giải một giá trị mơ hồ.

## 5. Số nguyên, phần lẻ của giây và độ chính xác

NumericDate không bắt buộc chỉ là số nguyên. Giá trị như `1700000000.25` biểu diễn một thời điểm có phần lẻ 250 mili giây sau mốc `1700000000`.

```json
{
  "iat": 1700000000.25
}
```

Trong nhiều hệ thống, độ chính xác đến giây là đủ. Khi đó, bên phát hành có thể dùng số nguyên giây. Nếu dùng phần lẻ, hai bên cần bảo đảm quá trình serialize, parse và so sánh không làm mất độ chính xác theo cách ảnh hưởng đến quyết định tại ranh giới thời gian.

Không tự ý làm tròn trước khi so sánh. Ví dụ, làm tròn một thời điểm `exp` lên giây kế tiếp có thể kéo dài thời gian chấp nhận; làm tròn xuống có thể khiến token bị từ chối sớm hơn. Quy tắc làm tròn, nếu có, phải là một phần rõ ràng của hợp đồng dữ liệu và chính sách.

### Giới hạn của kiểu số

JSON định nghĩa number, nhưng các ngôn ngữ và bộ phân tích JSON có thể lưu số theo kiểu nội bộ khác nhau. Một số môi trường dùng số dấu phẩy động IEEE 754; một số môi trường hỗ trợ số nguyên 64-bit hoặc kiểu số thập phân.

Các lưu ý:

- Với timestamp hiện đại tính bằng giây, giá trị thường nằm trong phạm vi mà các kiểu số phổ biến biểu diễn chính xác.
- Số nguyên rất lớn có thể vượt giới hạn chính xác của kiểu số dấu phẩy động; khi đó các giây liền kề có thể bị biểu diễn thành cùng một giá trị.
- Kiểu số nguyên 32-bit có dấu không đủ cho mọi timestamp hiện đại và có thể gặp vấn đề năm 2038.
- Không ép NumericDate vào kiểu số nguyên 32-bit nếu cần hỗ trợ thời gian hiện tại và tương lai.
- Cần kiểm tra giá trị hữu hạn và phạm vi hợp lý theo chính sách; tránh overflow, infinity hoặc giá trị không biểu diễn được sau khi parse.

Đối với hệ thống cần hỗ trợ khoảng thời gian rộng hoặc độ chính xác cao, hãy chọn kiểu dữ liệu và thư viện JSON có phạm vi phù hợp, đồng thời kiểm thử round-trip từ phát hành đến xác minh.

## 6. Giá trị âm và thời điểm trước Unix Epoch

Về mặt định nghĩa, NumericDate là số giây từ Unix Epoch đến một thời điểm UTC. Vì vậy, số âm có thể biểu diễn thời điểm trước `1970-01-01T00:00:00Z`.

Ví dụ về mặt số học:

| NumericDate | Thời điểm UTC |
| --- | --- |
| `-1` | `1969-12-31T23:59:59Z` |
| `0` | `1970-01-01T00:00:00Z` |
| `1` | `1970-01-01T00:00:01Z` |

Tuy nhiên, việc một giá trị NumericDate âm có được chấp nhận trong một loại token cụ thể hay không còn phụ thuộc vào profile và chính sách ứng dụng. Ví dụ, một access token được phát hành trong thời hiện đại thường không có lý do hợp lệ để mang `iat` trước Unix Epoch. Hệ thống có thể từ chối giá trị như vậy theo chính sách, nhưng cần phân biệt quy tắc đó với định nghĩa cơ bản của NumericDate.

Không áp dụng kiểm tra `value >= 0` như thể đó là định nghĩa chung của NumericDate. Hãy xác định phạm vi thời gian hợp lệ theo loại claim, profile và nghiệp vụ.

## 7. Giây trong ngày và việc bỏ qua leap seconds

RFC 7519 quy định NumericDate bỏ qua **leap seconds** (giây nhuận). Theo quy ước POSIX được RFC tham chiếu, mỗi ngày được tính là đúng 86.400 giây.

Điều này có nghĩa NumericDate không phải đồng hồ thiên văn ghi nhận từng giây nhuận. Các hệ thống JWT thông thường không cộng thêm một giây vào phép tính NumericDate khi gặp ngày có leap second.

Vì vậy:

- Dùng quy tắc Unix/POSIX time nhất quán khi tạo và xác minh token.
- Không tự chèn hoặc trừ giây nhuận vào giá trị NumericDate.
- Không chuyển đổi timestamp bằng cách giả định mọi ngày giờ địa phương đều có cùng offset UTC.
- Để thư viện thời gian chuẩn xử lý quy đổi UTC và múi giờ, thay vì tự tính bằng số ngày/tháng lịch.

## 8. NumericDate được sử dụng trong những claim nào?

Trong JWT chuẩn, ba registered claim thời gian thường gặp sử dụng NumericDate:

| Claim | Tên đầy đủ | Ý nghĩa | Điều kiện thời gian cơ bản |
| --- | --- | --- | --- |
| `iat` | Issued At | Thời điểm token được phát hành | Có thể dùng để tính tuổi token; bản thân claim không tự đặt max-age |
| `nbf` | Not Before | Thời điểm token bắt đầu có hiệu lực | Không chấp nhận trước `nbf`; tại `nbf` đã đạt điều kiện |
| `exp` | Expiration Time | Thời điểm token hết hạn | Không chấp nhận tại hoặc sau `exp` |

Ví dụ một JWT có đủ ba claim:

```json
{
  "iat": 1700000000,
  "nbf": 1700000060,
  "exp": 1700003600
}
```

Không có leeway, điều kiện thời gian có thể biểu diễn:

\[
\text{nbf} \leq \text{now} < \text{exp}
\]

`iat` ghi nhận thời điểm phát hành; nó không thay thế `nbf` hoặc `exp`. Max-age dựa trên `iat` là chính sách bổ sung do profile hoặc ứng dụng quy định.

### Ba claim thời gian đều có thể tùy chọn

Ở cấp JWT tổng quát, `iat`, `nbf` và `exp` là các registered claim tùy chọn. Một profile hoặc giao thức cụ thể có thể bắt buộc một hay nhiều claim. Ví dụ, profile JWT access token trong RFC 9068 yêu cầu các claim thời gian tương ứng theo quy định của profile. Bên nhận phải tuân theo profile đã chọn thay vì giả định mọi JWT đều có cùng tập claim.

## 9. Leeway và clock skew không phải một phần của NumericDate

NumericDate chỉ biểu diễn thời điểm. Nó không chứa thông tin về độ lệch đồng hồ hoặc dung sai xác minh.

Đồng hồ của issuer và bên nhận có thể lệch nhau. RFC 7519 cho phép bên xử lý áp dụng một khoảng dung sai nhỏ, thường không quá vài phút, khi kiểm tra `exp` và `nbf`.

Với leeway `L` không âm:

**Kiểm tra `nbf`:**

\[
\text{now} + L \geq \text{nbf}
\]

**Kiểm tra `exp`:**

\[
\text{now} < \text{exp} + L
\]

Leeway có thể làm token được chấp nhận sớm hơn `nbf` hoặc muộn hơn `exp`, tùy ranh giới đang kiểm tra. Nó là chính sách tại bên xác minh, không làm thay đổi giá trị NumericDate trong token.

Đối với `iat`, hệ thống có thể đặt chính sách riêng để từ chối thời điểm phát hành nằm quá xa trong tương lai hoặc giới hạn tuổi token. RFC định nghĩa cách biểu diễn `iat`, còn ngưỡng future skew và max-age phải đến từ profile hoặc chính sách ứng dụng.

Không cộng leeway nhiều lần ở các tầng xác minh. Hãy thống nhất đơn vị giây, cấu hình rõ ràng và đồng bộ đồng hồ bằng nguồn thời gian đáng tin cậy.

## 10. Quy trình tạo và xác minh NumericDate

Một quy trình tổng quát có thể thực hiện như sau.

### Khi phát hành JWT

1. Lấy thời điểm hiện tại từ nguồn đồng hồ đáng tin cậy.
2. Chuyển thời gian về Unix timestamp theo giây UTC.
3. Tính các mốc `iat`, `nbf`, `exp` theo chính sách và loại token.
4. Ghi các giá trị dưới dạng JSON number, không phải chuỗi hoặc timestamp mili giây.
5. Serialize payload và bảo vệ token bằng cơ chế mật mã phù hợp.
6. Kiểm thử token sau khi serialize để xác nhận các giá trị không bị đổi đơn vị hoặc mất độ chính xác.

### Khi xác minh JWT

1. Kiểm tra cấu trúc và xác minh chữ ký/MAC hoặc cơ chế bảo vệ mật mã tương ứng.
2. Đọc claims từ token đã xác minh.
3. Kiểm tra kiểu dữ liệu và phạm vi NumericDate theo profile.
4. Lấy thời gian hiện tại theo giây, cùng quy ước Unix Epoch.
5. Áp dụng quy tắc thời gian cho `nbf`, `exp`, `iat` và max-age nếu được yêu cầu.
6. Tiếp tục kiểm tra issuer, audience, token type, quyền và trạng thái thu hồi.
7. Chỉ chấp nhận token nếu tất cả điều kiện bắt buộc đều đạt.

Giả mã minh họa việc chuyển đổi và kiểm tra:

```text
function toNumericDate(epochMilliseconds):
    return epochMilliseconds / 1000

function validateNumericDate(value):
    if value is not a JSON number:
        return false

    if value is not finite:
        return false

    if value is outside the supported policy range:
        return false

    return true

function validateJwtTimeClaims(claims, nowEpochSeconds, leewaySeconds):
    if claims.exp is required and missing:
        return false

    if claims.exp exists:
        if not validateNumericDate(claims.exp):
            return false
        if nowEpochSeconds >= claims.exp + leewaySeconds:
            return false

    if claims.nbf exists:
        if not validateNumericDate(claims.nbf):
            return false
        if nowEpochSeconds + leewaySeconds < claims.nbf:
            return false

    return true
```

Đây là giả mã mô tả ý tưởng, không phải API của thư viện cụ thể. Phần `supported policy range` phải được hệ thống định nghĩa; không tự ý đặt một giới hạn chung cho mọi loại JWT. Ví dụ cũng chỉ minh họa hai claim `exp` và `nbf`; nếu áp dụng `iat`, cần bổ sung kiểm tra NumericDate, timestamp tương lai và max-age theo chính sách.

## 11. Lỗi thường gặp khi làm việc với NumericDate

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Ghi mili giây vào claim cần giây | Token có thời hạn hoặc thời điểm bắt đầu sai lệch rất lớn | Chuyển về giây trước khi serialize |
| So sánh giây với mili giây | Token bị chấp nhận quá lâu hoặc từ chối ngay | Chuẩn hóa cả hai vế về giây |
| Ghi timestamp dưới dạng chuỗi | Claim sai kiểu JSON | Ghi JSON number |
| Ghi ISO 8601 string vào `exp`, `nbf` hoặc `iat` | Không tuân thủ kiểu NumericDate | Chuyển thời điểm UTC sang số giây |
| Dùng giờ địa phương mà bỏ timezone | Timestamp sai lệch theo offset | Xác định timezone rồi chuyển về UTC |
| Tự cộng giây nhuận | Timestamp không còn theo quy ước NumericDate | Bỏ qua leap seconds theo RFC/POSIX |
| Làm tròn không nhất quán | Ranh giới chấp nhận thay đổi | Thống nhất độ chính xác và quy tắc làm tròn |
| Dùng kiểu số 32-bit cho timestamp hiện đại | Có thể tràn số hoặc lỗi năm 2038 | Dùng kiểu số có phạm vi phù hợp |
| Parse số lớn bằng kiểu dấu phẩy động không đủ chính xác | Mất độ chính xác ở thời điểm xa | Chọn kiểu số và parser phù hợp, kiểm thử round-trip |
| Tự ép kiểu hoặc sửa đơn vị theo phỏng đoán | Token sai định dạng được diễn giải không nhất quán | Từ chối dữ liệu sai và sửa hợp đồng phát hành |
| Tin NumericDate từ payload chưa xác minh | Kẻ tấn công có thể sửa claim thời gian | Xác minh bảo vệ mật mã trước khi tin claims |
| Cho rằng mọi JWT đều bắt buộc có đủ `iat`, `nbf`, `exp` | Từ chối nhầm token hợp lệ theo profile khác | Tuân theo profile và chính sách đã chọn |

## 12. Kịch bản thực tế: lỗi mili giây làm token không hết hạn

Một authorization server tạo access token có thời hạn 15 phút. Nguồn thời gian của hệ thống trả về mili giây nhưng bên phát hành ghi trực tiếp giá trị đó vào `exp`:

```json
{
  "iat": 1700000000000,
  "exp": 1700000900000
}
```

Resource server lại đọc `now` theo NumericDate chuẩn, tức số giây. Khi so sánh `now` với `exp`, giá trị `exp` lớn hơn rất nhiều so với thời gian hiện tại theo giây. Token có thể tiếp tục vượt qua kiểm tra hết hạn trong thời gian không đúng với dự kiến 15 phút.

Giá trị đúng theo giây cho cùng thời điểm phải là:

```json
{
  "iat": 1700000000,
  "exp": 1700000900
}
```

Nếu hai bên cùng dùng mili giây thì có thể vô tình hoạt động trong một hệ thống đóng, nhưng dữ liệu đó không tuân thủ NumericDate của JWT. Một bên tích hợp khác dùng thư viện chuẩn sẽ diễn giải giá trị theo giây và có thể tạo ra kết quả nghiêm trọng. Hãy tuân thủ đơn vị chuẩn ngay tại bên phát hành và kiểm thử tương thích giữa các hệ thống.

## 13. Kịch bản kiểm thử NumericDate

Nên có các trường hợp kiểm thử sau cho từng claim thời gian:

| Trường hợp | Kỳ vọng | Mục tiêu |
| --- | --- | --- |
| NumericDate là số nguyên giây hợp lệ | Parse thành công | Dạng số nguyên |
| NumericDate có phần lẻ của giây | Parse theo độ chính xác được hỗ trợ | Dạng không nguyên |
| Giá trị là chuỗi số | Từ chối | Không ép kiểu chuỗi |
| Giá trị là ISO 8601 string | Từ chối | Đúng kiểu JSON number |
| Giá trị là `null`, boolean, array hoặc object | Từ chối | Kiểm tra kiểu nghiêm ngặt |
| Nguồn thời gian mili giây được chuyển sang giây | Giá trị đúng bằng thời điểm kỳ vọng | Kiểm tra quy đổi đơn vị |
| Mili giây bị ghi trực tiếp vào claim | Phát hiện qua kiểm thử hợp đồng/giới hạn hợp lý | Ngăn lỗi đơn vị |
| Đồng hồ và claim dùng cùng đơn vị giây | So sánh đúng | Tránh sai lệch đơn vị |
| Ngày giờ có timezone khác UTC được quy đổi đúng | Cùng thời điểm cho cùng NumericDate | Kiểm tra timezone |
| Giá trị nằm trước Unix Epoch | Xử lý theo định nghĩa và chính sách | Kiểm tra timestamp âm |
| Giá trị có phần lẻ qua serialize/parse | Không mất độ chính xác ngoài quy định | Kiểm tra round-trip |
| Timestamp vượt phạm vi kiểu số đang dùng | Từ chối hoặc xử lý theo chính sách rõ ràng | Tránh overflow/precision loss |
| `exp` đúng ranh giới | Từ chối tại hoặc sau `exp` nếu không có leeway | Kiểm tra semantics claim |
| `nbf` đúng ranh giới | Chấp nhận tại hoặc sau `nbf` nếu không có leeway | Kiểm tra semantics claim |
| `iat` nằm trong tương lai | Xử lý theo future-skew policy | Kiểm tra timestamp phát hành |

Kiểm thử tích hợp nên tạo token ở một thành phần và xác minh ở thành phần khác, thay vì chỉ kiểm thử hàm chuyển đổi riêng lẻ. Điều này giúp phát hiện khác biệt parser, độ chính xác và đơn vị giữa các nền tảng.

## 14. Nguyên tắc cần ghi nhớ

1. NumericDate là số giây từ Unix Epoch `1970-01-01T00:00:00Z` theo UTC, bỏ qua leap seconds.
2. NumericDate là JSON number; không phải chuỗi số hoặc chuỗi ngày giờ ISO 8601.
3. NumericDate dùng giây, trong khi nhiều API thời gian cung cấp mili giây; cần chuyển đổi rõ ràng bằng phép chia cho 1.000.
4. NumericDate có thể là số nguyên hoặc số không nguyên; cần thống nhất độ chính xác và cách làm tròn.
5. Không dùng giờ địa phương nếu chưa xác định timezone và chuyển về UTC.
6. Chọn kiểu số có phạm vi và độ chính xác phù hợp; tránh số nguyên 32-bit, overflow và mất chính xác.
7. NumericDate chỉ biểu diễn thời điểm; `iat`, `nbf` và `exp` có quy tắc sử dụng khác nhau.
8. Leeway là chính sách của bên xác minh, không nằm trong giá trị NumericDate.
9. Chỉ sử dụng claim thời gian sau khi xác minh bảo vệ mật mã và tuân theo profile JWT tương ứng.

### Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT), mục 2 và 4.1.4–4.1.6](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa NumericDate và các claim thời gian `exp`, `nbf`, `iat`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): các claim và quy tắc thời gian trong profile JWT access token.
- [RFC 3339 — Date and Time on the Internet: Timestamps](https://www.rfc-editor.org/rfc/rfc3339): định dạng ngày giờ có timezone thường dùng khi trao đổi dữ liệu thời gian.
- [The Open Group Base Specifications — POSIX Seconds Since the Epoch](https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/V1_chap04.html): quy ước thời gian POSIX được RFC 7519 tham chiếu.

**Kết luận:** NumericDate biểu diễn thời điểm bằng số giây kể từ Unix Epoch UTC. Khi tạo và xác minh JWT, phải dùng JSON number đúng đơn vị giây, xử lý nhất quán timezone và độ chính xác, tránh nhầm mili giây, rồi áp dụng đúng quy tắc riêng của `iat`, `nbf` và `exp`.
