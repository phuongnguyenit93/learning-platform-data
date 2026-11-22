# Khác biệt về NumericDate, kiểu JSON và xử lý giá trị thiếu

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Liên thông và di trú  
> **Phạm vi:** Khác biệt giữa các implementation khi serialize, parse và xác minh NumericDate, JSON types và claims không hiện diện; tập trung vào hợp đồng liên thông đa ngôn ngữ, không phụ thuộc Java, Spring hay framework cụ thể.

Hai hệ thống có thể cùng tuân thủ định dạng JWT nhưng vẫn không hiểu token giống nhau. Một bên ghi thời gian theo millisecond, bên kia hiểu là second; một bên tự chuyển chuỗi số thành number, bên kia từ chối; một bên coi null giống claim bị thiếu, bên kia báo lỗi; một bên nhận aud dạng chuỗi, bên kia chỉ nhận mảng. Các khác biệt này gây lỗi xác thực ngẫu nhiên, mở rộng cửa sổ chấp nhận token hoặc tạo ra hành vi không nhất quán giữa gateway và resource server.

Muốn liên thông ổn định, cần định nghĩa một **token profile và JSON contract cụ thể**. Contract phải nói rõ claim nào bắt buộc, kiểu dữ liệu nào được chấp nhận, đơn vị thời gian, precision, leeway, cách xử lý giá trị thiếu/null, quy tắc audience và hành vi với JSON không rõ ràng. Đừng dựa vào coercion ngầm hoặc default của từng runtime.

## 1. NumericDate trong JWT

### 1.1. Đơn vị và epoch

RFC 7519 định nghĩa **NumericDate** là số giây kể từ Unix epoch tại **1970-01-01T00:00:00Z**, không tính leap seconds. Giá trị là JSON number.

Các claim thời gian thường gặp:

| Claim | Ý nghĩa | Kiểu theo JWT |
|---|---|---|
| **exp** | Thời điểm token hết hạn | NumericDate |
| **nbf** | Thời điểm sớm nhất token được chấp nhận | NumericDate |
| **iat** | Thời điểm token được phát hành | NumericDate |

NumericDate không phải:

- Unix milliseconds.
- Unix microseconds hoặc nanoseconds.
- Chuỗi ngày giờ ISO 8601.
- Giờ địa phương có timezone.
- Số giây kể từ một epoch tự định nghĩa của ứng dụng.

Ví dụ JSON:

~~~json
{
  "iat": 1794800000,
  "nbf": 1794800000,
  "exp": 1794803600
}
~~~

Các giá trị trên là giây kể từ Unix epoch và chỉ dùng minh họa.

### 1.2. Fractional seconds được phép

NumericDate có thể là số có phần thập phân. Ví dụ:

~~~json
{
  "iat": 1794800000.25,
  "exp": 1794800300.75
}
~~~

Một số implementation chỉ hỗ trợ số nguyên giây; một số khác giữ phần thập phân hoặc chuyển về millisecond. Để liên thông, issuer và verifier phải thống nhất precision.

Nếu không có nhu cầu nghiệp vụ về độ chính xác dưới giây, integer seconds thường đơn giản hơn và giảm khác biệt giữa parser. Đây là lựa chọn profile để tăng khả năng tương thích, không phải khẳng định rằng RFC cấm fractional NumericDate.

Nếu fractional seconds được sử dụng:

- Giữ precision trong suốt quá trình parse, so sánh và serialize.
- Không làm tròn sớm ở một thành phần nhưng giữ phần lẻ ở thành phần khác.
- Xác định rõ cách xử lý tại boundary.
- Có test với giá trị ngay dưới, đúng tại và ngay trên thời điểm hết hạn/bắt đầu hiệu lực.

### 1.3. JSON number không đồng nghĩa mọi runtime có cùng kiểu số

JSON có một loại giá trị number. Runtime có thể ánh xạ nó thành integer, decimal, floating-point hoặc kiểu số tổng quát tùy cú pháp và thư viện parse.

Các biểu diễn sau đều là JSON number:

~~~json
{
  "a": 1700000000,
  "b": 1700000000.0,
  "c": 1.7e9
}
~~~

Chúng có thể biểu diễn cùng giá trị toán học nhưng được parser đưa vào các kiểu nội bộ khác nhau. Contract cần quy định parser phải chấp nhận JSON number hợp lệ và không tự chuyển một JSON string thành number.

### 1.4. Phân biệt seconds và milliseconds

| Giá trị | Ý nghĩa dự định | Có phải NumericDate đúng đơn vị? |
|---:|---|---|
| 1700000000 | Unix seconds | Có |
| 1700000000000 | Unix milliseconds | Không |
| 1700000000000000 | Unix microseconds | Không |
| 1700000000000000000 | Unix nanoseconds | Không |

Nếu issuer dùng millisecond nhưng verifier hiểu là second, token có thể được coi là hết hạn ở một thời điểm rất xa trong tương lai. Nếu issuer dùng second nhưng verifier chia tiếp cho 1000, token có thể bị coi là hết hạn từ lâu.

Không thể phát hiện chắc chắn đơn vị chỉ bằng cách đoán độ lớn của con số. Một giá trị lớn có thể là sai đơn vị, nhưng việc tự động chia hoặc nhân để “sửa” sẽ khiến verifier chấp nhận dữ liệu ngoài contract. Hãy từ chối hoặc xử lý qua một migration path có kiểm soát.

## 2. Precision, range và giới hạn biểu diễn số

### 2.1. Số nguyên an toàn trong floating-point

Một số runtime dùng IEEE 754 binary64 cho JSON number. Kiểu này biểu diễn chính xác mọi số nguyên trong khoảng an toàn đến \(2^{53}-1\), nhưng không biểu diễn chính xác mọi số nguyên lớn hơn.

Unix seconds hiện đại nằm rất xa giới hạn này. Tuy nhiên, timestamp ở đơn vị microsecond/nanosecond hoặc giá trị bất thường rất lớn có thể vượt miền biểu diễn chính xác.

Rủi ro:

- Hai timestamp khác nhau bị làm tròn thành cùng một giá trị.
- So sánh exp/nbf lệch ở boundary.
- Một giá trị bị parse khác nhau giữa hai runtime.
- Serializer ghi lại số đã bị thay đổi do precision loss.

Contract nên giới hạn NumericDate trong miền thời gian nghiệp vụ cần thiết và yêu cầu xử lý số ngoài miền một cách rõ ràng.

### 2.2. Overflow ở kiểu số nguyên hẹp

Một implementation có thể lưu NumericDate vào signed 32-bit integer. Unix seconds vượt giới hạn **2147483647** vào năm 2038 sẽ gây overflow nếu không được xử lý.

Không chỉ kiểm tra năm 2038. Cần kiểm tra:

- Giá trị lớn hơn miền kiểu số đích.
- Giá trị âm.
- Giá trị có phần thập phân khi kiểu đích chỉ nhận integer.
- Phép nhân seconds × 1000 khi chuyển sang millisecond.
- Phép cộng exp + leeway có thể overflow.

Sử dụng kiểu số đủ rộng hoặc decimal/time representation phù hợp, kèm kiểm tra range trước khi chuyển đổi.

### 2.3. Giá trị âm

NumericDate là số giây tương đối với epoch; về mặt biểu diễn, số âm chỉ thời điểm trước epoch. Một profile access token hiện đại thường không có lý do phát hành exp âm, nhưng parser không nên tự suy đoán mọi số âm là lỗi cú pháp.

Phân biệt:

- Giá trị có cú pháp/kiểu NumericDate hợp lệ.
- Giá trị nằm trong miền mà profile cho phép.
- Giá trị thời gian có hợp lệ với chính sách exp/nbf/iat hay không.

Một exp âm thường đã hết hạn đối với thời điểm hiện tại và sẽ bị từ chối ở bước time validation. Nếu profile cấm timestamp âm, quy định đó phải được ghi rõ.

### 2.4. Không làm tròn trước khi xác minh

Ví dụ exp có phần thập phân:

\[
exp = 1700000000.5
\]

Nếu một verifier cắt xuống 1700000000, còn verifier khác giữ 1700000000.5, hai bên có thể đưa ra quyết định khác nhau trong nửa giây quanh boundary.

Để liên thông:

- Chọn precision chung.
- Không truncate/round trước khi so sánh.
- Xác định leeway cùng đơn vị.
- Không chuyển đổi qua nhiều kiểu số không cần thiết.
- Test đúng equality và epsilon theo precision được hỗ trợ.

## 3. JSON type của claims

### 3.1. Không tự ép kiểu

JSON phân biệt rõ number, string, boolean, null, array và object. Một claim có kiểu được chuẩn/profile quy định phải được kiểm tra đúng kiểu đó.

Ví dụ các giá trị sau không tương đương:

~~~json
{
  "exp_number": 1700000000,
  "exp_string": "1700000000",
  "exp_null": null,
  "exp_boolean": false,
  "exp_array": [1700000000],
  "exp_object": {"value": 1700000000}
}
~~~

Chỉ exp_number là JSON number phù hợp kiểu NumericDate. Không tự parse exp_string, không chuyển false thành 0 và không lấy phần tử đầu của array.

### 3.2. Kiểu claim thường gặp

| Claim | Kiểu chuẩn thường dùng | Ví dụ |
|---|---|---|
| **iss** | StringOrURI (JSON string) | "https://id.example.com" |
| **sub** | StringOrURI (JSON string) | "user-42" |
| **aud** | StringOrURI hoặc array StringOrURI | "orders-api" hoặc ["orders-api","billing-api"] |
| **exp** | NumericDate (JSON number) | 1700000300 |
| **nbf** | NumericDate (JSON number) | 1700000000 |
| **iat** | NumericDate (JSON number) | 1700000000 |
| **jti** | StringOrURI (JSON string) | "token-7f19" |

Các claim riêng của ứng dụng cần có schema riêng: tên, kiểu, tính bắt buộc, namespace và semantics. Không dùng một claim lúc là string, lúc là number chỉ vì runtime có thể tự chuyển đổi.

### 3.3. String không được chuẩn hóa tùy tiện

Với issuer và audience, phép so sánh phải theo semantics của profile. JWT định nghĩa StringOrURI và phép so sánh string có phân biệt chữ hoa/thường; không tự lowercase, trim khoảng trắng hoặc normalize URI theo suy đoán.

Ví dụ:

- https://id.example.com khác https://ID.example.com nếu so sánh chuỗi theo quy tắc JWT.
- orders-api khác Orders-API.
- Không bỏ dấu slash cuối hoặc tự giải mã percent-encoding để biến hai giá trị thành một.

Issuer và audience phải được cấu hình thống nhất ở cả bên phát hành và bên xác minh.

## 4. Giá trị thiếu, null, zero và empty

### 4.1. Bốn trạng thái không được đánh đồng

Một JSON object có thể thể hiện các trạng thái khác nhau:

~~~json
{}
~~~

~~~json
{"exp": null}
~~~

~~~json
{"exp": 0}
~~~

~~~json
{"exp": ""}
~~~

Ý nghĩa:

| Trạng thái | Nghĩa dữ liệu | Xử lý với claim NumericDate |
|---|---|---|
| Không có member | Claim absent | Chấp nhận chỉ khi profile cho phép thiếu |
| null | Member có mặt với giá trị null | Sai kiểu; không tự coi là absent |
| 0 | NumericDate bằng epoch | JSON number hợp lệ; đánh giá theo time policy |
| Chuỗi rỗng | String rỗng | Sai kiểu |

false, [] và {} cũng không tương đương với absent. Chúng là các giá trị JSON có kiểu cụ thể và phải bị từ chối nếu không phù hợp claim.

### 4.2. Registered claims không tự động bắt buộc trong mọi JWT

RFC 7519 mô tả registered claims nhưng không bắt buộc mọi JWT phải chứa tất cả các claim đó. Việc claim nào bắt buộc phụ thuộc token profile và contract.

Ví dụ:

- Một profile có thể yêu cầu exp, iat, iss và aud.
- Một token nghiệp vụ khác có thể chỉ yêu cầu một tập claims riêng.
- nbf có thể vắng mặt nếu token có hiệu lực ngay khi được phát hành.

Verifier phải kiểm tra required claims theo profile. Nếu exp bắt buộc mà token không có exp, phải từ chối; không tự gán một thời hạn mặc định.

### 4.3. Absent khác null

Nếu issuer không có giá trị cho claim optional, cách rõ ràng thường là không serialize member đó. Ghi null có nghĩa member hiện diện nhưng không có giá trị JSON thông thường; với claim có kiểu cụ thể như NumericDate, đây là dữ liệu sai kiểu.

Không dùng null để biểu diễn “không giới hạn thời hạn” nếu contract không định nghĩa semantics này. Với access token, thiếu exp hoặc exp null có thể dẫn tới hành vi nguy hiểm nếu một verifier bỏ qua kiểm tra còn verifier khác từ chối.

### 4.4. Zero là giá trị, không phải trạng thái thiếu

Các kiểm tra dựa trên truthiness dễ gây lỗi:

~~~text
if not claims.exp:
    treat exp as missing
~~~

Logic này có thể coi exp: 0 như không có claim. Tương tự, nbf: 0 hoặc iat: 0 cũng là số hợp lệ về kiểu dù thường không phù hợp token hiện đại.

Phải kiểm tra sự hiện diện của member tách biệt với kiểm tra giá trị:

~~~text
if claim "exp" is absent:
    apply required/optional policy
else:
    require JSON number
    validate NumericDate range
    evaluate expiration
~~~

Không dùng truthiness để quyết định claim có tồn tại hay không.

### 4.5. Empty string, empty array và empty object

Giá trị rỗng vẫn là giá trị có mặt:

- iss: "" không phải issuer hợp lệ theo contract.
- sub: "" cần bị từ chối nếu profile yêu cầu subject không rỗng.
- aud: [] không xác định recipient nào; verifier không nên chấp nhận như audience match.
- scope: "" không tương đương scope bị thiếu nếu profile có semantics khác nhau.
- {} trong claim riêng không thể được coi là absent nếu schema không cho phép.

Định nghĩa rõ empty có hợp lệ không cho từng claim; không áp dụng một quy tắc chung cho mọi JSON member.

## 5. Audience dạng string và array

### 5.1. Hai dạng biểu diễn hợp lệ

JWT cho phép aud là một StringOrURI hoặc một array chứa StringOrURI:

~~~json
{
  "aud": "https://api.example.com"
}
~~~

~~~json
{
  "aud": [
    "https://api.example.com",
    "https://reports.example.com"
  ]
}
~~~

Một verifier chỉ nhận string có thể từ chối token hợp lệ dùng array. Một verifier chỉ nhận array có thể từ chối token hợp lệ dùng string. Contract liên thông nên xác định rõ có hỗ trợ cả hai dạng theo JWT hay giới hạn một dạng theo profile.

### 5.2. Cách kiểm tra audience

Nếu resource server có audience mong đợi https://api.example.com:

- Với aud dạng string, so sánh giá trị string theo quy tắc chính xác.
- Với aud dạng array, kiểm tra có ít nhất một phần tử khớp audience được phép.
- Không coi array là một string bằng cách nối các phần tử.
- Không chấp nhận chỉ vì một phần tử có prefix giống audience.
- Không tự normalize host, path hoặc case ngoài contract.

Nếu profile yêu cầu audience cụ thể, thiếu aud hoặc aud không khớp phải bị từ chối.

### 5.3. Kiểm tra kiểu và phần tử array

Các trường hợp:

~~~json
{"aud": 42}
~~~

~~~json
{"aud": ["orders-api", 42]}
~~~

~~~json
{"aud": null}
~~~

~~~json
{"aud": []}
~~~

Không tự chuyển số thành string, bỏ qua phần tử sai kiểu rồi tiếp tục hoặc coi null/empty array là không giới hạn audience. Nếu profile yêu cầu array StringOrURI, phần tử sai kiểu làm token không hợp lệ.

### 5.4. Audience không phải scope

Audience trả lời token dành cho resource server nào. Scope/permission mô tả loại hành động được phép. Token có audience đúng nhưng thiếu scope vẫn phải bị từ chối ở authorization. Token có scope phù hợp nhưng audience sai cũng phải bị từ chối trước đó.

Không dùng một claim thay thế claim còn lại.

## 6. JSON parser khác nhau và nguy cơ parser differential

### 6.1. Duplicate member names

JSON có thể chứa member trùng tên, ví dụ:

~~~json
{
  "iss": "https://trusted.example",
  "iss": "https://attacker.example",
  "aud": "orders-api"
}
~~~

RFC 7519 yêu cầu parser JWT phải từ chối object có claim name trùng hoặc dùng quy tắc giữ member xuất hiện cuối cùng như mô tả trong chuẩn. Các parser có thể có hành vi khác nhau nếu một bên giữ giá trị đầu, bên kia giữ giá trị cuối.

Đối với hệ thống mới, nên từ chối duplicate member ở các vị trí bảo mật để giảm ambiguity. Với hệ thống hiện hữu, cần kiểm tra hành vi của mọi parser tham gia trước khi thay đổi.

Các member nhạy cảm cần test:

- alg, kid, typ trong JOSE header.
- iss, aud, exp, nbf, iat, sub, jti trong claims.
- Claim riêng dùng cho role, tenant, scope hoặc delegation.

### 6.2. Thứ tự member và whitespace

JSON object không mang semantics dựa trên thứ tự member. Tuy nhiên, JWS ký trên byte của encoded protected header và payload, không ký trên một object JSON trừu tượng.

Vì vậy:

- Hai payload JSON có member order khác nhau có thể mang cùng dữ liệu logic nhưng tạo signing input khác nhau.
- Thay whitespace hoặc reserialize payload trước khi verify sẽ làm thay đổi bytes và chữ ký không còn khớp.
- Verifier phải xác minh compact token gốc theo signing input gốc.
- Không decode JSON rồi serialize lại trước khi xác minh chữ ký.

Interoperability không có nghĩa mọi implementation phải serialize JSON giống hệt nhau; nó có nghĩa mỗi bên hiểu đúng token đã được ký theo byte sequence của nó.

### 6.3. Unicode và tên claim

Tên claim và string values phải được xử lý theo quy tắc JSON/JWT. Không tự chuẩn hóa Unicode hoặc đổi chữ hoa/thường ở một lớp mà lớp khác không làm tương tự.

Với claim định danh như iss, sub và aud:

- So sánh theo semantics của profile.
- Tránh tạo hai biểu diễn gần giống nhưng khác code point.
- Nếu ứng dụng yêu cầu normalization, thực hiện ở nơi phát hành và lưu định danh theo một contract thống nhất.
- Không tự normalize dữ liệu token trước khi kiểm tra chữ ký.

### 6.4. JSON number và parser coercion

Các parser có thể:

- Phân biệt integer và decimal.
- Parse exponent notation thành floating-point.
- Chuyển số lớn thành floating-point mất precision.
- JSON number có leading zero ngoài dạng số 0 phải bị từ chối theo grammar JSON; parser permissive chấp nhận extension này sẽ tạo khác biệt liên thông.
- Chuyển kiểu tự động khi ánh xạ vào model.

Không để một parser permissive chấp nhận token mà validator downstream hiểu khác. Hãy test bằng token có JSON number edge cases và xác minh các thành phần đưa ra cùng kết quả.

## 7. Claim schema và profile contract

### 7.1. Lập schema cho từng token profile

Một contract nên định nghĩa:

| Thuộc tính | Nội dung |
|---|---|
| Profile ID | Tên/phiên bản token profile |
| Issuer | Issuer chính xác được tin cậy |
| Audience | Resource server hoặc recipient được phép |
| Required claims | Các claim bắt buộc |
| Optional claims | Claim có thể vắng mặt |
| Claim types | JSON type cho từng claim |
| NumericDate unit | Unix seconds |
| NumericDate precision | Integer seconds hoặc fractional policy |
| Time policy | exp/nbf/iat, leeway, max age |
| Null policy | Null có bị từ chối hay có semantics riêng |
| Duplicate policy | Từ chối duplicate member hoặc quy tắc thống nhất |
| Unknown claims | Bỏ qua, giữ lại hay từ chối theo profile |
| Versioning | Cách thay đổi contract an toàn |

### 7.2. Ví dụ contract khái niệm

~~~yaml
token_profile:
  id: orders-access-v1
  issuer: "https://id.example.com"
  audience:
    accepted:
      - "https://api.orders.example.com"

claims:
  required:
    iss: string
    aud: string_or_array_of_strings
    sub: string
    exp: numeric_date_seconds
    iat: numeric_date_seconds
    jti: string
  optional:
    nbf: numeric_date_seconds
    scope: string

json_policy:
  reject_wrong_claim_types: true
  reject_null_for_typed_claims: true
  reject_duplicate_members: true
  coerce_string_to_number: false
  numeric_date:
    fractional_seconds: false
    max_supported_epoch_seconds: 4102444800

time_policy:
  clock_leeway_seconds: 30
  max_token_age_seconds: 900
~~~

Đây là ví dụ contract nội bộ, không phải schema RFC. max_supported_epoch_seconds, leeway và max age phải được chọn theo vòng đời hệ thống. Việc profile chọn integer seconds là một ràng buộc liên thông bổ sung.

### 7.3. Unknown claim và forward compatibility

JWT cho phép ứng dụng định nghĩa private claims. Verifier thường có thể bỏ qua claim không biết nếu profile không yêu cầu xử lý; tuy nhiên:

- Claim bắt buộc không được thiếu.
- Claim dùng để quyết định quyền phải có schema rõ.
- Không suy diễn quyền từ claim không được định nghĩa.
- Thay đổi kiểu claim phải được xem là thay đổi contract.
- Unknown critical JOSE header không được bỏ qua nếu chuẩn yêu cầu xử lý.

Phân biệt unknown application claim với critical header parameter; chúng không có cùng semantics.

## 8. Pseudocode xác minh liên thông

### 8.1. Kiểm tra member presence và JSON type

~~~text
validateNumericDateClaim(claims, name, required, policy):
    if name is absent:
        if required:
            reject MISSING_REQUIRED_CLAIM
        return ABSENT

    value = claims[name]

    if value is null:
        reject NULL_FOR_NUMERIC_DATE

    if JSON type of value is not number:
        reject INVALID_NUMERIC_DATE_TYPE

    if value is NaN, infinite, out of range, or loses required precision:
        reject INVALID_NUMERIC_DATE_RANGE

    if policy.requires_integer and value has fractional part:
        reject FRACTIONAL_NUMERIC_DATE_NOT_ALLOWED

    return validated NumericDate
~~~

### 8.2. Xác minh thời gian

~~~text
validateTimes(claims, now, profile):
    exp = validateNumericDateClaim(
        claims, "exp", profile.requiresExp, profile.numericDate
    )
    nbf = validateNumericDateClaim(
        claims, "nbf", profile.requiresNbf, profile.numericDate
    )
    iat = validateNumericDateClaim(
        claims, "iat", profile.requiresIat, profile.numericDate
    )

    if exp is present and not (now < exp + profile.leeway):
        reject EXPIRED

    if nbf is present and not (now + profile.leeway >= nbf):
        reject NOT_YET_VALID

    if iat is present:
        reject if iat > now + profile.futureIatTolerance
        reject if profile.maxAge exists and now - iat > profile.maxAge

    validate profile-specific relations among iat, nbf and exp
~~~

Pseudocode minh họa leeway và policy ứng dụng. Ranh giới equality phải được định nghĩa và kiểm thử thống nhất; không sao chép các biểu thức này mà bỏ qua semantics của thư viện đang dùng.

### 8.3. Xác minh audience

~~~text
validateAudience(aud, expectedAudiences):
    if aud is absent:
        reject if audience is required

    if JSON type is string:
        candidates = [aud]
    else if JSON type is array:
        reject if any item is not a string
        candidates = aud
    else:
        reject INVALID_AUDIENCE_TYPE

    reject if candidates is empty
    accept audience check only if an exact allowed value matches
~~~

Đây là logic khái niệm cho contract cho phép cả hai dạng aud. Nếu profile giới hạn một dạng cụ thể, validator phải áp dụng giới hạn đó.

## 9. Khác biệt liên thông thường gặp giữa các implementation

| Khác biệt | Hành vi bên A | Hành vi bên B | Cách xử lý |
|---|---|---|---|
| NumericDate unit | Ghi millisecond | Đọc second | Contract thống nhất Unix seconds |
| Fractional seconds | Giữ decimal | Cắt integer | Chọn precision chung và test boundary |
| JSON number | Integer/decimal parser | Binary64 parser | Giới hạn range và kiểm tra precision |
| String number | Tự coercion | Từ chối | Không coercion; sai type phải reject |
| Missing exp | Bỏ qua | Yêu cầu exp | Profile xác định required claims |
| exp null | Coi như absent | Báo lỗi | Null không thay thế absent |
| exp zero | Truthiness coi như thiếu | Đánh giá là epoch | Kiểm tra presence riêng giá trị |
| aud string | Chấp nhận | Chỉ nhận array | Contract xác định union type hoặc dạng giới hạn |
| aud array | Match phần tử | So sánh toàn mảng như chuỗi | Match từng recipient chính xác |
| Duplicate iss | Lấy member đầu | Lấy member cuối | Từ chối duplicate hoặc thống nhất chuẩn |
| Large timestamp | Integer 64-bit | Integer 32-bit | Chọn miền số chung đủ rộng |
| Unicode string | Normalize | So sánh nguyên dạng | Không tự normalize; thống nhất semantics |
| Whitespace JSON | Parse rồi reserialize | Verify byte gốc | Verify compact token gốc, không reserialize |
| Leeway | 60 giây | 0 giây | Một policy thống nhất và đo skew |

## 10. Quy trình di trú contract an toàn

### 10.1. Inventory token đang phát hành

Trước khi thay đổi validator, thống kê từ dữ liệu đã redacted hoặc test corpus:

- Các issuer và token profile.
- Claim nào đang có mặt.
- Tỷ lệ thiếu exp/iat/nbf.
- NumericDate có phải second hay millisecond.
- Có fractional values không.
- aud đang là string hay array.
- Có claim sai kiểu, null hoặc duplicate không.
- Các thư viện/runtime đang phát hành và xác minh token.

Không thu thập raw token production vào spreadsheet hoặc tài liệu migration. Có thể phân tích metadata đã redacted hoặc dùng test fixture được tạo lại.

### 10.2. Định nghĩa canonical profile

Chọn một contract mới có:

- Required/optional claims.
- JSON types chính xác.
- NumericDate unit/precision/range.
- Null/missing policy.
- Audience semantics.
- Duplicate member policy.
- Leeway và clock policy.
- Token type/version.

Ghi contract thành tài liệu có version và chia sẻ cho mọi producer/consumer.

### 10.3. Tạo conformance corpus

Tạo một bộ token fixture bao gồm:

- Token hợp lệ canonical.
- Token hợp lệ có aud string và array nếu profile hỗ trợ cả hai.
- Boundary exp/nbf.
- Fractional NumericDate nếu được hỗ trợ.
- Missing/null/zero/wrong type.
- Large number và seconds/milliseconds.
- Duplicate member và malformed JSON.
- Issuer/audience/profile mismatch.

Mỗi implementation chạy cùng bộ corpus và tạo kết quả tương đương. Lưu kết quả theo phiên bản thư viện/runtime để phát hiện regression.

### 10.4. Rollout theo producer trước, consumer sau

Một cách triển khai an toàn:

1. Công bố canonical profile và bộ test.
2. Cập nhật producer để phát hành token theo profile mới.
3. Cập nhật consumer để xác minh strict theo profile mới.
4. Trong giai đoạn chuyển tiếp, nếu cần hỗ trợ token cũ, tạo profile legacy riêng với điều kiện, issuer và thời hạn rõ.
5. Không nới lỏng validator mới cho tất cả token chỉ để tương thích dữ liệu cũ.
6. Theo dõi tỷ lệ token legacy, sai kiểu và timestamp bất thường.
7. Ngừng profile legacy sau thời hạn migration đã công bố.

Không tự sửa token cũ bằng cách chuyển millisecond sang second hoặc coercion string trong verifier production. Nếu cần migration, thực hiện qua issuer/flow phát hành lại token mới hoặc adapter có phạm vi hẹp và thời hạn kết thúc rõ.

### 10.5. Tránh dual parser ambiguity

Trong rollout, không để cùng một endpoint thử nhiều parser/semantics một cách tùy tiện cho đến khi một parser chấp nhận. Hãy chọn profile dựa trên trust context đã cấu hình, rồi xác minh bằng một semantics xác định.

Nếu phải hỗ trợ nhiều phiên bản:

- Phân biệt bằng issuer, audience, typ hoặc version claim đã được xác minh theo contract.
- Không dùng claim chưa xác minh để mở rộng trust.
- Không để legacy parser chấp nhận thuật toán hoặc key type mà profile mới cấm.
- Ghi rõ ngày kết thúc hỗ trợ.

## 11. Ma trận kiểm thử NumericDate và JSON types

| ID | Input/tình huống | Kết quả mong đợi |
|---|---|---|
| I01 | exp là JSON number integer seconds, còn hạn | Chấp nhận time check |
| I02 | exp là millisecond timestamp | Từ chối theo profile; không tự chia |
| I03 | exp là string "1700000000" | Từ chối sai JSON type |
| I04 | exp là null | Từ chối null cho NumericDate |
| I05 | exp là boolean false | Từ chối sai type |
| I06 | exp là array/object | Từ chối sai type |
| I07 | exp absent nhưng profile yêu cầu | Từ chối missing required claim |
| I08 | exp absent và profile cho phép optional | Bỏ qua exp check theo contract |
| I09 | exp = 0 | Nhận diện là number hiện diện; đánh giá theo thời gian |
| I10 | exp là fractional seconds | Chấp nhận hoặc từ chối đúng precision policy |
| I11 | exp dùng exponent notation hợp lệ | Parse cùng semantics JSON number |
| I12 | exp vượt miền số hỗ trợ | Từ chối có kiểm soát |
| I13 | exp gây overflow kiểu integer hẹp | Từ chối, không wraparound |
| I14 | exp ở gần giới hạn năm 2038 | Không overflow trong representation |
| I15 | nbf absent | Xử lý theo optional/required policy |
| I16 | nbf null | Từ chối sai type |
| I17 | iat ở tương lai vượt tolerance | Từ chối theo future-time policy |
| I18 | iat vượt maximum age | Từ chối theo profile |
| I19 | aud là string khớp | Chấp nhận audience check |
| I20 | aud là array có một phần tử khớp | Chấp nhận nếu profile hỗ trợ array |
| I21 | aud là number hoặc null | Từ chối sai type |
| I22 | aud array chứa phần tử không phải string | Từ chối |
| I23 | aud là empty array | Từ chối vì không xác định recipient hợp lệ |
| I24 | iss khác case hoặc khác chuỗi cấu hình | Từ chối exact issuer mismatch |
| I25 | Duplicate exp/iss/aud | Từ chối theo duplicate policy |
| I26 | JSON member order/whitespace thay đổi sau khi ký | Chữ ký phải được xác minh trên bytes gốc; reserialize rồi verify phải thất bại |
| I27 | Claim name có case khác | Không coi là cùng claim |
| I28 | Token có unknown optional private claim | Xử lý theo forward-compatibility policy |
| I29 | Token có claim bắt buộc nhưng sai type | Từ chối |
| I30 | Gateway và API parse cùng fixture | Kết quả type/time/audience nhất quán |
| I31 | Issuer cũ phát milliseconds trong giai đoạn migration | Legacy profile chỉ chấp nhận nếu được cấu hình rõ và có thời hạn |
| I32 | Legacy adapter tự chuyển đơn vị cho mọi issuer | Test phải FAIL; không có coercion toàn cục |

## 12. Những lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Khắc phục |
|---|---|---|
| Dùng milliseconds trong JWT | Verifier hiểu token còn hạn quá lâu hoặc sai thời điểm | Phát NumericDate bằng seconds |
| Ép string thành number | Parser khác nhau cho kết quả khác | Strict JSON type validation |
| Coi null như absent | Token sai schema có thể vượt validation | Phân biệt member presence và null |
| Dùng truthiness để kiểm tra claim | Giá trị zero bị coi như thiếu | Kiểm tra presence riêng |
| Dùng integer 32-bit | Overflow khi timestamp vượt miền | Kiểu số đủ rộng và range check |
| Cắt fractional seconds | Boundary lệch giữa verifier | Precision contract và không truncate sớm |
| Bỏ qua aud array | Từ chối token hợp lệ hoặc kiểm tra sai recipient | Hỗ trợ union type theo contract |
| Chuyển array thành string | Audience semantics sai | So sánh từng phần tử |
| Lowercase issuer/audience | Mở rộng trust không đúng | Exact comparison theo profile |
| Parser lấy duplicate member khác nhau | Gateway và API bất đồng | Reject duplicate và dùng parser thống nhất |
| Reserialize JSON trước verify | Signing input thay đổi | Verify token bytes nguyên gốc |
| Không định nghĩa required claims | Một bên chấp nhận token thiếu exp, bên kia từ chối | Profile versioned |
| Coercion để tương thích legacy vô thời hạn | Duy trì dữ liệu mơ hồ | Migration profile có thời hạn |

## 13. Checklist liên thông và di trú

**NumericDate**

- [ ] Dùng Unix epoch seconds theo UTC.
- [ ] Ghi rõ integer hay fractional seconds.
- [ ] Có giới hạn range và precision.
- [ ] Không tự chuyển milliseconds/microseconds.
- [ ] Không overflow khi chuyển đổi hoặc cộng leeway.
- [ ] Test boundary exp/nbf/iat và clock tolerance.

**JSON types và claims**

- [ ] Schema quy định kiểu cho từng claim.
- [ ] Không coercion string/boolean/null thành number.
- [ ] Phân biệt absent, null, zero và empty.
- [ ] Required claims được xác định theo profile.
- [ ] aud string/array được xử lý theo contract.
- [ ] iss, sub, aud được so sánh đúng semantics.
- [ ] Duplicate member có policy nhất quán.

**Parser và chữ ký**

- [ ] Verify compact token gốc, không reserialize trước khi verify.
- [ ] Parser có semantics rõ cho number, duplicate member và Unicode.
- [ ] Gateway, issuer và resource server dùng cùng conformance corpus.
- [ ] Claims chưa xác minh không được dùng để cấp quyền.

**Di trú**

- [ ] Inventory token legacy đã được redacted.
- [ ] Canonical profile có version và owner.
- [ ] Legacy profile có phạm vi, telemetry và ngày kết thúc.
- [ ] Không có coercion/fallback toàn cục.
- [ ] Producer/consumer được rollout theo kế hoạch.
- [ ] Có regression suite chạy sau khi nâng cấp thư viện.

**Điều cần nhớ:** Liên thông JWT phụ thuộc vào việc các bên hiểu cùng một JSON contract. NumericDate dùng giây; JSON number không phải string; absent khác null, zero và empty; aud có thể là string hoặc array theo JWT semantics; duplicate member và precision có thể tạo parser differential. Hãy định nghĩa profile có version, xác minh kiểu nghiêm ngặt, giữ nguyên bytes token khi verify và dùng conformance corpus chung trước khi di trú.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT), Sections 2, 4.1 and 7.2](https://www.rfc-editor.org/rfc/rfc7519): NumericDate, registered claims, audience và parsing JWT.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): JSON number, object member names, string và interoperability.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Validation theo profile, issuer/audience và parser considerations.
- [RFC 9068 — JSON Web Token Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Ví dụ contract access token với required claims.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): Signing input và xác minh trên representation gốc.
- [RFC 3339 — Date and Time on the Internet: Timestamps](https://www.rfc-editor.org/rfc/rfc3339): Timestamp văn bản để phân biệt với NumericDate.
- [RFC 5905 — Network Time Protocol Version 4](https://www.rfc-editor.org/rfc/rfc5905): Đồng bộ thời gian cho các hệ thống phân tán.
