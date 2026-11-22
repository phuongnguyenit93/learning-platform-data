# Thay header, payload hoặc chữ ký và xác minh kết quả từ chối

## 1. Mục tiêu của kiểm thử mutation JWT

JSON Web Token (JWT) thường được truyền dưới dạng compact serialization. Với JWT ký bằng JSON Web Signature (JWS), nội dung header và payload được bảo vệ bởi chữ ký. Nếu một thành phần bị thay đổi sau khi token được ký, chữ ký phải không còn hợp lệ và verifier phải từ chối token.

Kiểm thử mutation (thay đổi có chủ đích) tạo ra các token dựa trên một fixture hợp lệ, sau đó sửa một phần của token để xác minh hệ thống có phát hiện và từ chối hay không. Các nhóm mutation chính:

- **Header mutation:** sửa thuật toán, key ID, token type hoặc tham số JOSE.
- **Payload mutation:** sửa issuer, audience, thời gian, subject, scope hoặc claims nghiệp vụ.
- **Signature mutation:** thay, cắt cụt hoặc làm hỏng chữ ký.
- **Serialization mutation:** sửa dấu phân tách, Base64URL, JSON hoặc cấu trúc compact token.

Mục tiêu không chỉ là nhận một HTTP error. Test phải chứng minh token bị từ chối trước khi hệ thống tạo principal đã xác thực, cấp quyền, trả dữ liệu được bảo vệ hoặc thực hiện side effect.

Nguyên tắc cốt lõi:

> **Với JWS, mọi thay đổi đối với protected header hoặc payload đều làm thay đổi signing input. Nếu chữ ký cũ được giữ nguyên, verifier phải từ chối token.**

Bài này thuộc phạm vi Security chung của JSON Web Token (JWT). Ví dụ tập trung vào JWS access token, nhưng phương pháp kiểm thử có thể áp dụng cho mọi hệ thống dùng JWT. Nếu hệ thống hỗ trợ JWT mã hóa (JWE), cần kiểm thử authentication tag và quy trình giải mã theo profile riêng.

## 2. Hiểu đúng cấu trúc JWT trước khi mutation

### 2.1. Compact JWS có ba segment

Một signed JWT theo JWS Compact Serialization có dạng:

~~~text
BASE64URL(protected-header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Ví dụ token minh họa:

~~~text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0wMSIsInR5cCI6ImF0K2p3dCJ9
.
eyJpc3MiOiJodHRwczovL2lkZW50aXR5LmV4YW1wbGUudGVzdCIsInN1YiI6InVzZXItNTE0IiwiYXVkIjoiaHR0cHM6Ly9hcGkuZXhhbXBsZS50ZXN0L2JpbGxpbmciLCJleHAiOjE5MDAwMDAzMDAsInNjb3BlIjoiaW52b2ljZTpyZWFkIn0
.
<signature-bytes>
~~~

Ví dụ chỉ minh họa hình dạng token; segment chữ ký không phải chữ ký thật.

### 2.2. Signing input là gì?

Với JWS Compact Serialization thông thường, signing input được tạo từ hai segment đã mã hóa:

\[
M = BASE64URL(UTF8(protected\ header)) \; || \; "." \; || \; BASE64URL(payload)
\]

Chữ ký được tính trên chính chuỗi byte M theo thuật toán và khóa tương ứng. Verifier không đơn giản parse JSON rồi so sánh nội dung đã giải mã.

Hệ quả quan trọng:

- Sửa một ký tự trong protected header segment làm signing input thay đổi.
- Sửa một ký tự trong payload segment làm signing input thay đổi.
- Đổi thứ tự JSON member, khoảng trắng hoặc cách biểu diễn JSON cũng có thể làm byte segment thay đổi.
- Giữ nguyên chữ ký cũ sau các thay đổi trên phải dẫn tới signature verification failure.

Không được tái serialize JSON rồi xác minh chữ ký trên một biểu diễn khác với signing input của compact token.

### 2.3. Mutation không giống tạo token mới hợp lệ

Có hai loại test cần tách biệt:

1. **Tamper test:** sửa token đã ký nhưng giữ chữ ký cũ. Test xác minh integrity check có phát hiện thay đổi không.
2. **Policy test:** tạo một token mới có chữ ký hợp lệ bằng test key nhưng chứa alg, issuer, audience, typ hoặc claims không được policy cho phép. Test xác minh verifier có thực thi policy sau khi chữ ký hợp lệ không.

Ví dụ, đổi aud trong payload mà giữ signature cũ là tamper test. Tạo một token được ký hợp lệ với aud trỏ tới API khác là audience policy test. Cả hai đều cần thiết; chỉ làm tamper test không chứng minh audience validation hoạt động.

## 3. Chuẩn bị test fixture an toàn

Trước khi tạo mutation, cần có một token chuẩn đã được xác minh là hợp lệ với đúng endpoint và môi trường kiểm thử.

### 3.1. Fixture hợp lệ

Một fixture cho Billing API có thể có:

~~~json
{
  "header": {
    "alg": "RS256",
    "kid": "test-signing-key-01",
    "typ": "at+jwt"
  },
  "payload": {
    "iss": "https://identity.test.example",
    "sub": "user-514",
    "aud": "https://api.test.example/billing",
    "client_id": "test-client",
    "iat": 1900000000,
    "exp": 1900000300,
    "jti": "test-access-token-001",
    "scope": "invoice:read"
  }
}
~~~

Đây là cấu trúc dữ liệu minh họa, không phải một token đã ký. Fixture thật phải được tạo bằng khóa test chuyên dụng và phải vượt qua validator trong môi trường test.

### 3.2. Điều kiện của fixture

- Issuer nằm trong trust registry của môi trường test.
- Khóa công khai tương ứng đã được cấu hình hoặc công bố trong JWKS test.
- Thuật toán nằm trong allowlist.
- Audience đúng endpoint đang kiểm thử.
- Token type và claims đáp ứng profile.
- Thời hạn còn hiệu lực tại thời điểm test.
- Scope đủ cho một thao tác kiểm thử có thể quan sát kết quả.
- Dữ liệu không chứa thông tin hoặc credential production.

### 3.3. Positive control

Luôn gửi fixture gốc trước khi chạy mutation:

~~~text
Valid fixture
    -> signature valid
    -> issuer/audience/type valid
    -> required claims valid
    -> request được xử lý theo authorization policy
~~~

Nếu fixture gốc không được chấp nhận, các mutation test không có giá trị vì test có thể đang đo một cấu hình sai hoặc token đã hết hạn.

### 3.4. Dùng khóa test riêng

Không dùng private signing key production để tạo token test hoặc token lỗi. Dùng issuer/test key riêng, dữ liệu giả và resource test có thể reset. Bảo vệ private test key phù hợp với môi trường; không commit secret vào repository.

## 4. Quy tắc đánh giá kết quả từ chối

Khi token bị sửa, kết quả mong đợi thường là authentication failure. Với OAuth Bearer token, RFC 6750 mô tả phản hồi 401 Unauthorized cùng challenge error invalid_token trong trường hợp token không hợp lệ. API có thể có response contract riêng, nhưng phải bảo đảm không biến credential sai thành request được xác thực.

Không chỉ kiểm tra status code. Cần xác minh:

- Request không được gắn principal đã xác thực.
- Authorization layer không nhận claims chưa xác minh.
- Không trả dữ liệu được bảo vệ.
- Không tạo hoặc cập nhật dữ liệu nghiệp vụ.
- Không phát event hoặc gọi downstream với danh tính giả.
- Không ghi token nguyên vẹn hoặc secret vào log.
- Không cache kết quả xác thực thành công cho token đã bị sửa.
- Không fallback sang validator yếu hơn khi verifier báo lỗi.

Nếu API trả 401, response body hoặc WWW-Authenticate nên tuân theo contract của hệ thống. Không phụ thuộc vào thông báo lỗi chi tiết; thông tin nội bộ có thể được ghi bằng reason code an toàn.

## 5. Header mutation: thay protected header

Protected header là phần đầu tiên của JWS compact token. Các giá trị ở đây ảnh hưởng đến cách verifier chọn thuật toán, khóa và profile.

### 5.1. Thay alg nhưng giữ nguyên signature

Token gốc:

~~~json
{
  "alg": "RS256",
  "kid": "test-signing-key-01",
  "typ": "at+jwt"
}
~~~

Header bị sửa:

~~~json
{
  "alg": "HS256",
  "kid": "test-signing-key-01",
  "typ": "at+jwt"
}
~~~

Giữ nguyên payload và signature của token gốc.

Kết quả mong đợi:

- Verifier từ chối vì HS256 không thuộc allowlist nếu profile chỉ cho RS256.
- Dù thư viện có hỗ trợ HS256, không được tự chuyển public key RSA thành HMAC secret.
- Không được thử nhiều thuật toán tùy ý cho đến khi có một cách xác minh thành công.
- Không tạo principal hoặc thực hiện request.

Test này có thể bị từ chối ngay ở algorithm allowlist trước khi kiểm tra chữ ký. Để kiểm tra riêng integrity, cũng cần mutation khác không thay alg, chẳng hạn đổi một bit của header segment nhưng vẫn giữ alg hợp lệ.

### 5.2. Đổi alg thành none

Thay alg bằng none và giữ nguyên signature cũ phải bị từ chối. Tuy nhiên, test này chưa đủ để chứng minh verifier cấm unsecured JWT, vì chữ ký cũ vốn không phù hợp với header đã sửa.

Tạo thêm một test fixture unsigned theo cấu trúc JWS phù hợp với alg none, rồi gửi tới endpoint yêu cầu signed access token. Kết quả bắt buộc là từ chối theo policy, kể cả khi parser có thể đọc được payload.

Không bật chế độ unsecured JWT trong validator access token production.

### 5.3. Thay kid

Đổi kid từ test-signing-key-01 thành unknown-key-99 nhưng giữ nguyên signature.

Các kết quả có thể xảy ra:

- Verifier không tìm thấy key và từ chối.
- Verifier refresh JWKS theo cơ chế có giới hạn rồi vẫn từ chối.
- Verifier từ chối signature vì key được chọn không đúng.

Test cần xác minh không có key fallback tùy tiện, không fetch URL từ token và không chấp nhận key thuộc issuer khác. Không yêu cầu mọi implementation phải trả cùng một error reason nếu contract chỉ quy định từ chối.

### 5.4. Thay typ

Đổi typ từ at+jwt sang một loại khác, ví dụ dpop+jwt hoặc JWT profile không được endpoint chấp nhận.

Khi giữ signature cũ, token phải bị từ chối do chữ ký không còn khớp hoặc do profile validation. Để kiểm tra riêng typ policy, tạo token test được ký hợp lệ nhưng typ sai.

Endpoint nhận access token không được nhầm DPoP proof, ID Token hoặc JWT nghiệp vụ thành access token.

### 5.5. Thêm hoặc sửa crit

JOSE header có thể chứa crit để đánh dấu extension quan trọng. Test các trường hợp:

- Thêm crit với extension verifier không hỗ trợ.
- Khai báo crit nhưng thiếu extension tương ứng.
- Thay đổi extension được khai báo.
- Đưa một member không hợp lệ vào crit.

Token có chữ ký cũ sẽ fail integrity. Token được ký hợp lệ nhưng chứa critical extension không được hỗ trợ vẫn phải bị từ chối. Verifier không được bỏ qua extension mà crit yêu cầu xử lý.

### 5.6. Thêm jku hoặc x5u

Thêm URL khóa vào header, ví dụ URL trỏ tới host không được tin cậy hoặc địa chỉ private. Khi signature cũ được giữ nguyên, token phải bị từ chối. Quan trọng hơn, xác minh rằng server không tạo outbound request tới URL đó.

Test riêng token được ký hợp lệ nhưng chứa jku/x5u ngoài policy. Verifier phải từ chối hoặc xử lý đúng profile đã phê duyệt; không tự động fetch URL do token cung cấp.

### 5.7. Thay đổi thứ tự member hoặc cách biểu diễn header

Đổi thứ tự JSON member hoặc khoảng trắng trong header, sau đó Base64URL-encode lại nhưng giữ nguyên signature cũ.

Ngay cả khi JSON sau giải mã có ý nghĩa tương đương, encoded protected header đã thay đổi nên signing input khác. Verifier phải từ chối signature cũ.

Không canonicalize header rồi xác minh trên một chuỗi khác với signing input thực tế của JWS.

## 6. Payload mutation: thay claims

Payload chứa claims được ứng dụng sử dụng sau khi xác minh chữ ký. Mọi thay đổi payload segment trong một JWS đã ký đều phải làm signature cũ mất hiệu lực.

### 6.1. Thay issuer

Payload gốc:

~~~json
{
  "iss": "https://identity.test.example",
  "sub": "user-514"
}
~~~

Payload bị sửa:

~~~json
{
  "iss": "https://attacker.test.example",
  "sub": "admin"
}
~~~

Giữ nguyên signature cũ. Token phải bị từ chối.

Để kiểm tra issuer policy riêng, tạo một token có chữ ký hợp lệ từ test issuer B rồi gửi tới endpoint chỉ tin issuer A. API phải từ chối vì issuer không được cấu hình, kể cả khi chữ ký của issuer B hợp lệ theo key riêng của B.

### 6.2. Thay audience

Đổi aud từ Billing API sang Documents API nhưng giữ signature cũ. Token phải bị từ chối.

Sau đó tạo một token ký hợp lệ với audience chỉ dành cho Documents API và gửi tới Billing API. Billing API phải từ chối vì recipient không khớp.

Đừng chỉ dùng token có chữ ký sai để kết luận audience check hoạt động. Signature failure có thể khiến validator dừng trước bước audience.

### 6.3. Thay subject

Đổi sub từ user-514 sang admin hoặc một user khác. Với signature cũ, token phải bị từ chối. Test signed-valid riêng có thể xác minh API chỉ chấp nhận subject do issuer phát hành và ánh xạ đúng principal.

Không kiểm tra bằng cách chỉ quan sát tên user trong log. Cần xác minh không có dữ liệu hoặc hành động được thực hiện dưới subject đã bị sửa.

### 6.4. Thay scope, role hoặc permission

Ví dụ payload gốc:

~~~json
{
  "scope": "invoice:read",
  "roles": ["viewer"],
  "permissions": ["invoice.read"]
}
~~~

Payload bị sửa:

~~~json
{
  "scope": "invoice:read invoice:approve invoice:delete",
  "roles": ["administrator"],
  "permissions": ["invoice.read", "invoice.approve", "invoice.delete"]
}
~~~

Giữ signature cũ; token phải bị từ chối. Không được dùng claims đã decode để cấp thêm quyền trước khi signature verification thành công.

Tạo thêm token được ký hợp lệ nhưng scope/role vượt grant hoặc sai policy để kiểm tra authorization riêng. Chữ ký hợp lệ không tự làm permission được cấp.

### 6.5. Thay exp, nbf hoặc iat

Các test mutation có thể:

- Đẩy exp về tương lai xa.
- Đổi exp thành giá trị đã hết hạn.
- Đẩy nbf về quá khứ hoặc tương lai.
- Thay iat thành thời điểm tương lai.
- Thay kiểu NumericDate thành string hoặc object.

Giữ signature cũ thì token phải fail integrity. Với token test được ký hợp lệ, verifier còn phải áp dụng time policy và từ chối các giá trị sai hoặc ngoài cửa sổ clock skew.

Không chỉ test một giá trị hết hạn; cần test cả kiểu dữ liệu và biên thời gian.

### 6.6. Thêm claim quyền hoặc tenant

Thử thêm tenant_id, owner_id, account_status, authz_version hoặc claim tùy chỉnh có thể làm tăng quyền. Giữ signature cũ phải bị từ chối.

Token signed-valid riêng cần được đánh giá theo schema và source-of-truth policy. Claim tùy chỉnh không được tự trở thành quyền nếu issuer/profile không định nghĩa nó hoặc resource server không có quy tắc sử dụng rõ.

### 6.7. Xóa claim bắt buộc

Xóa iss, aud, exp, sub hoặc claim bắt buộc theo profile. Với signature cũ, token fail integrity. Với token được ký hợp lệ nhưng thiếu claim, verifier phải từ chối ở bước required-claim validation.

Test này xác minh cả hai lớp: integrity và profile completeness.

## 7. Signature mutation: thay chữ ký

Để kiểm tra signature verification trực tiếp, giữ nguyên protected header và payload, chỉ sửa signature segment.

### 7.1. Flip một bit

Giải mã signature segment thành bytes, thay đổi một bit rồi Base64URL-encode lại. Giữ header và payload nguyên vẹn.

Kết quả mong đợi:

- Chữ ký không còn khớp signing input.
- Verifier từ chối token.
- Không tạo principal hoặc chạy authorization.

Đây là test cơ bản nhất cho việc verifier thật sự kiểm tra chữ ký.

### 7.2. Thay bằng chữ ký của token khác

Tạo token A và token B bằng cùng issuer/key/algorithm nhưng payload khác nhau. Lấy signature của B ghép với header/payload của A.

Verifier phải từ chối. Chữ ký hợp lệ cho message B không hợp lệ cho message A.

Test này giúp phát hiện lỗi ghép nhầm segment hoặc verifier chỉ kiểm tra rằng signature có cấu trúc hợp lệ mà không xác minh đúng signing input.

### 7.3. Dùng chữ ký từ key khác

Tạo token bằng một key test khác nhưng cùng thuật toán. Thay signature của token gốc bằng signature từ key khác.

Verifier chỉ được chấp nhận key nằm trong trust store đúng issuer/profile. Signature từ key không được tin phải bị từ chối.

### 7.4. Cắt cụt hoặc làm rỗng signature

Các trường hợp:

- Signature segment rỗng.
- Signature bị cắt giữa chừng.
- Signature thiếu byte.
- Signature chỉ có ký tự Base64URL hợp lệ nhưng độ dài không hợp lệ với thuật toán.
- Signature chứa ký tự ngoài Base64URL alphabet.

Verifier phải từ chối token malformed hoặc signature invalid. Không được diễn giải signature rỗng như token không cần chữ ký nếu profile yêu cầu signed JWT.

### 7.5. Thay toàn bộ signature bằng dữ liệu ngẫu nhiên

Dùng bytes ngẫu nhiên có độ dài tương tự chữ ký thật. Điều này kiểm tra verifier không chỉ kiểm tra độ dài hoặc định dạng mà thực sự xác minh mật mã.

Không sử dụng signature giả tạo có thể vô tình hợp lệ; fixture nên được tạo có kiểm soát và có seed/test vector được quản lý.

## 8. Serialization mutation: làm hỏng compact token

Ngoài việc sửa JSON hoặc chữ ký, cần kiểm tra parser đối với cấu trúc compact serialization.

### 8.1. Thay dấu phân tách

JWS compact cần đúng số segment và dấu chấm phân tách. Test:

- Bỏ dấu chấm giữa header và payload.
- Bỏ dấu chấm giữa payload và signature.
- Thêm segment thứ tư.
- Thêm dấu chấm ở đầu hoặc cuối.
- Ghép hai token thành một chuỗi.

Token phải bị từ chối như malformed input.

### 8.2. Base64URL không hợp lệ

Test:

- Ký tự ngoài alphabet Base64URL.
- Padding hoặc cách mã hóa không được profile/parser chấp nhận.
- Segment rỗng ngoài trường hợp profile cho phép.
- Encoding bị cắt giữa chừng.
- Nhiều biểu diễn không canonical nếu parser có quy tắc canonical.

Verifier phải có hành vi nhất quán và không để các thành phần khác nhau parse cùng một token theo cách khác nhau.

### 8.3. JSON malformed

Test header/payload:

- JSON thiếu dấu ngoặc hoặc dấu nháy.
- Member có kiểu không hợp lệ.
- JSON lồng quá sâu.
- Số quá lớn hoặc không thể biểu diễn an toàn.
- Member trùng lặp như iss hoặc alg.
- Unicode escape hoặc UTF-8 malformed.

Parser nên từ chối JSON nhập nhằng hoặc malformed. Không để một parser xác minh chữ ký và parser khác đọc claims theo cách khác.

### 8.4. Duplicate JSON member

Ví dụ payload:

~~~json
{
  "iss": "https://identity.test.example",
  "iss": "https://attacker.test.example",
  "aud": "https://api.test.example/billing"
}
~~~

Các parser có thể khác nhau trong việc chọn giá trị đầu tiên hay cuối cùng. Test cần xác minh hệ thống từ chối member trùng hoặc áp dụng một quy tắc thống nhất được profile cho phép.

Với JWS đã ký, mutation này cũng làm signature cũ mất hiệu lực. Để kiểm tra parser behavior riêng, cần token test được ký hợp lệ chứa duplicate member, nếu thư viện cho phép tạo fixture như vậy.

## 9. Phân biệt tamper tests và policy tests

Đây là điểm quan trọng để kết quả test có ý nghĩa.

| Mục tiêu | Cách tạo token | Kết quả mong đợi |
| --- | --- | --- |
| Phát hiện header bị sửa | Sửa header segment, giữ signature cũ | Reject do integrity hoặc policy. |
| Phát hiện payload bị sửa | Sửa payload segment, giữ signature cũ | Reject do integrity. |
| Phát hiện signature bị sửa | Giữ header/payload, sửa signature | Reject do signature verification. |
| Cấm thuật toán ngoài allowlist | Tạo token test ký hợp lệ bằng thuật toán không được phép | Reject do algorithm policy. |
| Cấm issuer khác | Tạo token ký hợp lệ bởi issuer test khác | Reject do issuer trust. |
| Cấm audience khác | Tạo token ký hợp lệ nhưng aud dành cho API khác | Reject do audience policy. |
| Cấm token type khác | Tạo token ký hợp lệ với typ/profile khác | Reject do token profile. |
| Bắt buộc claim | Tạo token ký hợp lệ nhưng thiếu claim | Reject do required-claim policy. |
| Kiểm tra NumericDate | Tạo token ký hợp lệ nhưng exp/nbf/iat sai | Reject do time/type validation. |
| Bảo vệ parser | Tạo compact serialization malformed | Reject trước khi dùng claims. |

Nếu mọi test chỉ sửa payload và giữ signature cũ, chúng có thể đều bị từ chối tại bước signature. Khi đó không thể kết luận issuer, audience, scope hoặc required-claim validation đã hoạt động.

## 10. Test matrix cho header, payload và signature

### 10.1. Header mutation matrix

| ID | Mutation | Cách tạo | Kết quả mong đợi |
| --- | --- | --- | --- |
| H-01 | Sửa alg | Thay RS256 thành HS256, giữ signature | Reject; không fallback thuật toán. |
| H-02 | alg = none | Thay header hoặc tạo unsigned fixture | Reject theo signed-token policy. |
| H-03 | Sửa kid | Đổi sang key ID không tồn tại | Reject; không chọn key tùy tiện. |
| H-04 | kid của issuer khác | Chọn key ID trùng ở issuer khác | Không dùng chéo key; reject. |
| H-05 | Sửa typ | at+jwt thành dpop+jwt | Reject sai profile. |
| H-06 | Unknown crit | Thêm extension critical không hỗ trợ | Reject. |
| H-07 | jku ngoài trust | Thêm URL attacker-controlled | Reject; không fetch URL. |
| H-08 | x5u ngoài trust | Thêm URL private/không tin cậy | Reject; không fetch URL. |
| H-09 | Private JWK material | Thêm tham số private vào jwk | Reject theo header/key policy. |
| H-10 | Header JSON reorder | Encode lại JSON với thứ tự khác | Signature cũ phải fail. |

### 10.2. Payload mutation matrix

| ID | Mutation | Cách tạo | Kết quả mong đợi |
| --- | --- | --- | --- |
| P-01 | Sửa iss | Thay issuer | Reject. |
| P-02 | Sửa aud | Thay resource server | Reject. |
| P-03 | Sửa sub | Thay subject | Reject. |
| P-04 | Thêm scope | Thêm invoice:delete | Reject với signature cũ; signed-valid policy test cũng phải kiểm tra grant. |
| P-05 | Nâng role | viewer thành administrator | Reject với signature cũ; signed-valid token phải tuân policy role. |
| P-06 | Thay tenant | company-a thành company-b | Reject. |
| P-07 | Kéo dài exp | Đẩy expiration ra xa | Reject với signature cũ; signed-valid token phải theo lifetime policy. |
| P-08 | Thay nbf/iat | Giá trị tương lai hoặc sai kiểu | Reject. |
| P-09 | Xóa required claim | Bỏ aud/sub/exp | Reject. |
| P-10 | Sai kiểu claim | exp là string, aud là object | Reject. |
| P-11 | Duplicate member | Lặp iss hoặc aud | Reject cấu trúc nhập nhằng. |
| P-12 | JSON reorder/whitespace | Encode lại payload | Signature cũ phải fail. |

### 10.3. Signature mutation matrix

| ID | Mutation | Cách tạo | Kết quả mong đợi |
| --- | --- | --- | --- |
| S-01 | Flip bit | Đổi một bit của signature bytes | Reject. |
| S-02 | Random signature | Thay bằng bytes ngẫu nhiên | Reject. |
| S-03 | Signature token khác | Ghép signature từ token B vào token A | Reject. |
| S-04 | Wrong key | Dùng signature từ key không tin cậy | Reject. |
| S-05 | Truncated | Cắt ngắn signature | Reject. |
| S-06 | Empty | Xóa signature segment | Reject. |
| S-07 | Invalid Base64URL | Đưa ký tự không hợp lệ vào signature | Reject malformed. |
| S-08 | Wrong algorithm/key pairing | Signature/key không tương thích | Reject. |

## 11. Kiểm tra side effect và ranh giới xác thực

Một token sai phải bị từ chối trước khi nó có thể ảnh hưởng đến nghiệp vụ.

### 11.1. Không tạo principal từ claims chưa xác minh

Test có thể quan sát:

- Request context không có authenticated principal.
- Không có user/role/permission được lấy từ payload đã sửa.
- Không có tenant context được thiết lập từ claims giả.
- Không có audit event ghi nhận hành động thành công dưới subject đã sửa.

### 11.2. Không thực hiện side effect

Chọn một endpoint test có thể quan sát, ví dụ tạo một bản ghi thử nghiệm. Gửi token bị mutation và xác minh:

- Không có bản ghi mới.
- Không có thay đổi trạng thái.
- Không có message được publish.
- Không có job hoặc downstream request được kích hoạt.
- Không có file/object được tạo hoặc xóa.

Không chỉ kiểm tra response; phải kiểm tra trạng thái sau request.

### 11.3. Không dùng fallback yếu

Kiểm tra các đường xử lý:

- JWT validation failure không fallback sang decode-only.
- JWKS lookup failure không dùng key tùy ý.
- Signature failure không tiếp tục bằng claims cache cũ.
- Token type mismatch không thử validator của profile khác.
- Exception không bị bắt rồi bỏ qua.

### 11.4. Không ghi credential vào log

Log có thể ghi reason code, endpoint, issuer profile dự kiến, correlation ID và kết quả validation. Không ghi raw JWT, refresh token, private key hoặc toàn bộ Authorization header.

## 12. Test với nhiều verifier và nhiều instance

Một hệ thống có thể có API Gateway, nhiều resource server, nhiều region và nhiều phiên bản thư viện. Mutation tests nên xác minh mọi verifier áp dụng cùng hợp đồng.

### 12.1. So sánh kết quả giữa các thành phần

Gửi cùng một bộ fixture tới:

- API Gateway nếu nó thực hiện token validation.
- Resource server trực tiếp.
- Các phiên bản đang chạy song song trong quá trình rollout.
- Các region/instance có cache JWKS riêng.

Token bị sửa phải bị từ chối ở mọi điểm xác minh. Nếu Gateway từ chối nhưng backend chấp nhận khi được gọi trực tiếp, trust boundary đang có lỗ hổng.

### 12.2. Không dựa vào Gateway như lớp bảo vệ duy nhất

Nếu backend có thể được gọi trực tiếp hoặc nhận request từ một mạng khác, backend cần tự xác minh token hoặc chỉ tin một assertion nội bộ được bảo vệ bằng cơ chế service identity và network policy rõ ràng.

### 12.3. Kiểm thử cache và key rotation

- Token được ký bằng key hiện tại.
- Token được ký bằng key cũ còn trong overlap.
- Token dùng kid lạ.
- JWKS vừa thay đổi.
- Một instance có cache cũ trong khi instance khác đã refresh.
- Key bị thu hồi khẩn cấp.

Token bị mutation không được chấp nhận chỉ vì một instance đang giữ trạng thái cache sai hoặc fallback không an toàn.

## 13. Fuzzing và property-based testing

Mutation thủ công kiểm tra các trường hợp đã biết. Fuzzing tạo nhiều biến thể để tìm lỗi parser, lỗi ranh giới hoặc khác biệt giữa các thư viện.

### 13.1. Fuzz từng segment

Đối với compact JWS:

- Header segment: thay byte, thêm/bớt ký tự, JSON malformed, member trùng.
- Payload segment: thay byte, thay encoding, JSON sâu, số lớn, claim sai kiểu.
- Signature segment: cắt cụt, đổi byte, độ dài sai, Base64URL malformed.
- Separators: thêm/bớt dấu chấm hoặc thay vị trí segment.

Giới hạn số lượng, kích thước và thời gian chạy để tránh làm quá tải môi trường test.

### 13.2. Property-based assertions

Một số thuộc tính có thể kiểm tra:

~~~text
For every valid signed fixture T:
    mutateProtectedHeader(T) -> reject
    mutatePayload(T)         -> reject
    mutateSignature(T)       -> reject

For every rejected token:
    authenticatedPrincipal == absent
    protectedResourceReturned == false
    businessSideEffectCount == unchanged
~~~

Thuộc tính này giả định mutation thật sự thay đổi byte signing input hoặc signature và không vô tình tạo ra một token khác được ký hợp lệ. Nếu mutation chỉ đổi cách biểu diễn mà parser chuẩn hóa trước khi verify, cần kiểm tra lại harness để bảo đảm đang sửa compact serialization thực tế.

### 13.3. Differential testing

Nếu hệ thống có nhiều thư viện hoặc phiên bản verifier, chạy cùng bộ token trên từng implementation và so sánh:

- Accept/reject.
- Issuer/audience/type interpretation.
- Claim type parsing.
- Duplicate JSON member behavior.
- Base64URL behavior.
- Critical header handling.

Khác biệt kết quả phải được điều tra. Không tự chọn kết quả permissive nhất.

## 14. Test JWE riêng với JWS

JWT có thể được bảo vệ bằng JWS, JWE hoặc cấu trúc nested JWT. Không áp dụng nguyên xi test signature cho mọi loại compact token.

### 14.1. JWS

JWS Compact Serialization thường có ba segment:

~~~text
protected-header.payload.signature
~~~

Mutation protected header hoặc payload làm signing input thay đổi. Mutation signature làm chữ ký không hợp lệ.

### 14.2. JWE

JWE Compact Serialization có năm segment:

~~~text
protected-header.encrypted-key.iv.ciphertext.authentication-tag
~~~

JWE sử dụng authenticated encryption theo cấu hình. Mutation protected header, encrypted key, IV, ciphertext hoặc authentication tag phải dẫn tới lỗi giải mã/xác thực theo thuật toán và profile.

Không gọi lỗi JWE là signature verification failure nếu token chỉ được mã hóa và không có JWS bên trong.

### 14.3. Nested JWT

Nếu JWE chứa JWS:

1. Xác minh cấu trúc và giải mã lớp JWE theo policy.
2. Xác minh JWS bên trong.
3. Áp dụng token profile, issuer, audience và claims.

Test mutation từng lớp riêng và test kết hợp. Không bỏ qua chữ ký lớp trong chỉ vì lớp ngoài giải mã thành công.

## 15. Xây dựng test harness

Test harness nên tạo token, mutation segment và gửi request theo một cách lặp lại được.

### 15.1. Các thành phần

- **Fixture builder:** tạo token hợp lệ bằng test issuer/key.
- **Segment parser:** tách compact serialization đúng định dạng.
- **Mutation operators:** sửa header, payload, signature hoặc separator.
- **Policy fixture builder:** tạo token được ký hợp lệ nhưng sai một policy cụ thể.
- **HTTP client:** gửi request tới endpoint test.
- **State observer:** kiểm tra principal, database, event và downstream side effects.
- **Result reporter:** ghi test ID, mutation, status và reason code an toàn.

### 15.2. Tách mutation operator và policy fixture builder

Mutation operator giữ signature cũ để kiểm tra integrity. Policy fixture builder ký lại token bằng test key để kiểm tra các bước validation phía sau signature.

Không dùng một hàm mutation vừa sửa payload vừa ký lại mà gọi kết quả đó là tamper test. Khi ký lại, test đã thay đổi mục tiêu: nó đang kiểm tra policy của issuer/token profile.

### 15.3. Giữ test deterministic

- Dùng fixture và test key có version.
- Dùng clock cố định hoặc controllable clock.
- Dùng resource test có trạng thái xác định.
- Đặt tên mutation ID ổn định.
- Reset state giữa các test.
- Tránh dùng token đã hết hạn trước khi test bắt đầu.
- Ghi lại issuer, audience và profile dự kiến của fixture, không ghi secret.

### 15.4. Kiểm soát retry và rate limit

Mutation tests có thể tạo nhiều token lỗi. Dùng môi trường test riêng, giới hạn tốc độ và tránh kích hoạt hệ thống khóa tài khoản hoặc cảnh báo production. Nếu test reuse/replay, reset family/session sau mỗi case.

## 16. Pseudocode: tạo mutation và xác minh từ chối

Ví dụ logic ở mức khái niệm:

~~~text
function runTamperSuite(validToken, endpoint):
    assert endpoint.accepts(validToken) == EXPECTED_VALID_RESULT

    original = splitJwsCompact(validToken)
    assert original.segmentCount == 3

    cases = [
        mutateHeaderByte(original),
        mutatePayloadByte(original),
        mutateSignatureByte(original),
        truncateSignature(original),
        replaceSignatureFromAnotherToken(original),
        corruptBase64Url(original.header),
        corruptBase64Url(original.payload),
        corruptBase64Url(original.signature)
    ]

    for each case in cases:
        response = endpoint.send(case.compactToken)
        assert response.isAuthenticationFailure
        assert noAuthenticatedPrincipal(case.requestId)
        assert noProtectedDataReturned(case.requestId)
        assert noBusinessSideEffect(case.requestId)

    return PASS
~~~

Ví dụ policy test riêng:

~~~text
function runSignedPolicySuite(testIssuer, endpoint):
    cases = [
        signWithDisallowedAlgorithm(testIssuer),
        signWithWrongIssuer(testIssuer),
        signWithWrongAudience(testIssuer),
        signWithWrongTokenType(testIssuer),
        signWithoutRequiredClaim(testIssuer),
        signWithWrongClaimType(testIssuer),
        signWithExpiredTimeClaims(testIssuer)
    ]

    for each token in cases:
        response = endpoint.send(token)
        assert response.isAuthenticationFailure
        assert noAuthenticatedPrincipal(token.requestId)
        assert noBusinessSideEffect(token.requestId)

    return PASS
~~~

Đây là pseudocode minh họa. Trong triển khai thực tế, test harness cần phân biệt malformed token, signature failure và policy rejection để biết đúng lớp nào đã được kiểm tra.

## 17. Phân loại lỗi và quan sát kết quả

Không phải mọi token bị từ chối đều có cùng nguyên nhân. Có thể phân loại nội bộ:

| Nhóm | Ví dụ | Điều cần xác minh |
| --- | --- | --- |
| MALFORMED | Sai số segment, Base64URL lỗi, JSON malformed | Parser từ chối trước khi dùng claims. |
| UNSUPPORTED_ALGORITHM | alg ngoài allowlist hoặc none | Không fallback sang thuật toán khác. |
| KEY_SELECTION_FAILURE | kid không tồn tại, key sai issuer | Không lấy key ngoài trust store. |
| SIGNATURE_INVALID | Signature bị sửa hoặc ghép sai | Không tạo principal. |
| INVALID_ISSUER | iss không khớp | Exact issuer validation hoạt động. |
| INVALID_AUDIENCE | aud không dành cho API | Recipient validation hoạt động. |
| INVALID_TYPE | typ/profile không đúng | Validator chuyên biệt hoạt động. |
| MISSING_CLAIM | Claim bắt buộc không có | Required-claim policy hoạt động. |
| INVALID_CLAIM_TYPE | NumericDate hoặc claim sai kiểu | Schema validation hoạt động. |
| EXPIRED/NOT_YET_VALID | exp/nbf không hợp lệ | Time validation hoạt động. |
| UNSUPPORTED_CRITICAL_HEADER | crit chứa extension không hỗ trợ | Critical header không bị bỏ qua. |

### 17.1. Public response và internal reason code

Caller chỉ cần biết credential không hợp lệ theo contract. Log nội bộ có thể ghi nhóm lỗi, test ID, endpoint profile và correlation ID. Không phản hồi raw parser exception hoặc thông tin key store cho caller.

### 17.2. Không khẳng định nguyên nhân từ status code đơn lẻ

Một token sửa payload nhưng giữ signature cũ có thể bị từ chối ở signature verification trước khi verifier kiểm tra aud. Nếu test chỉ nhìn 401, không thể kết luận audience check đã chạy.

Để kiểm tra một policy cụ thể, tạo token có chữ ký hợp lệ nhưng vi phạm đúng policy đó, hoặc dùng instrumentation/test hook chỉ trong môi trường kiểm thử để quan sát validation stage.

## 18. Những lỗi thường gặp khi viết mutation tests

| Sai lầm | Vì sao test không đủ | Cách khắc phục |
| --- | --- | --- |
| Chỉ kiểm tra HTTP 401 | Không biết request có tạo side effect trước khi bị từ chối không. | Kiểm tra principal, response data và trạng thái nghiệp vụ. |
| Dùng fixture gốc đã hết hạn | Test luôn fail dù mutation không được phát hiện. | Positive control và clock cố định. |
| Chỉ dùng token có chữ ký sai để test mọi policy | Signature failure có thể dừng pipeline trước issuer/audience/type checks. | Thêm signed-valid policy fixtures. |
| Sửa JSON sau khi decode nhưng không thay compact segment | Token gửi đi có thể vẫn là token gốc. | Mutation encoded segment thật. |
| Canonicalize JSON trước khi verify | Có thể xác minh sai signing input. | Verify đúng byte compact serialization. |
| Dùng production key trong test | Tăng nguy cơ lộ private signing key. | Test issuer và key riêng. |
| Chỉ test một byte signature | Không bao phủ malformed, wrong-key và segment confusion. | Dùng matrix đa dạng. |
| Chỉ test một instance | Replay/cache hoặc verifier khác có thể hành xử khác. | Test các instance/region và đường gọi trực tiếp. |
| Bỏ qua JWE/nested JWT đang hỗ trợ | Có thể còn lỗ hổng ở lớp mã hóa hoặc chữ ký bên trong. | Tách test theo từng serialization/profile. |
| Không kiểm tra log | Token có thể bị ghi vào log trong lúc test lỗi. | Kiểm tra log không chứa raw credential. |
| Dùng response error chi tiết làm contract | Thư viện nâng cấp có thể đổi thông báo. | Assert nhóm kết quả và security invariant. |

## 19. Checklist kiểm thử

Trước khi kết luận JWT mutation testing đạt yêu cầu, hãy xác nhận:

1. **Positive control:** fixture hợp lệ được endpoint chấp nhận trước khi mutation.
2. **Header integrity:** sửa protected header và giữ signature cũ dẫn tới từ chối.
3. **Payload integrity:** sửa payload và giữ signature cũ dẫn tới từ chối.
4. **Signature verification:** flip bit, randomize, truncate và thay signature đều bị từ chối.
5. **Algorithm policy:** token ký hợp lệ bằng thuật toán ngoài allowlist bị từ chối.
6. **Key selection:** unknown kid hoặc key issuer khác không được fallback.
7. **Issuer/audience:** token ký hợp lệ nhưng sai iss/aud bị từ chối.
8. **Token profile:** typ sai hoặc token thuộc profile khác bị từ chối.
9. **Required claims:** thiếu claim hoặc sai kiểu bị từ chối.
10. **JOSE header:** crit không hỗ trợ và URL khóa không tin cậy bị xử lý đúng.
11. **Serialization:** sai segment, Base64URL, JSON và duplicate member bị từ chối.
12. **No side effect:** token sai không tạo principal, trả dữ liệu hoặc thay đổi trạng thái.
13. **No fallback:** verifier không decode-only hoặc fail-open khi lỗi.
14. **Multi-instance:** các verifier và region có hành vi thống nhất.
15. **JWE/nested JWT:** nếu hỗ trợ, từng lớp được kiểm thử theo đúng cơ chế.
16. **Logging:** không ghi raw JWT, Authorization header hoặc secret.
17. **Repeatability:** test có thể chạy lại với fixture, clock và state xác định.

## 20. Ghi nhớ trọng tâm

- JWS compact có ba segment; signing input là encoded protected header, dấu chấm và encoded payload.
- Sửa protected header hoặc payload nhưng giữ signature cũ phải làm chữ ký không hợp lệ.
- Sửa signature segment phải bị phát hiện bằng xác minh mật mã, không chỉ bằng kiểm tra định dạng.
- Tamper tests và signed-valid policy tests là hai nhóm khác nhau; cần cả hai để chứng minh integrity lẫn issuer/audience/type/claims policy.
- Header tests nên bao gồm alg, kid, typ, crit, jku/x5u và thay đổi JSON representation.
- Payload tests nên bao gồm iss, aud, sub, scope, roles, tenant, exp, nbf, iat và required claims.
- Serialization tests cần bao phủ số segment, Base64URL, JSON malformed và duplicate member.
- Một token bị từ chối phải không tạo principal, trả dữ liệu được bảo vệ hoặc tạo side effect.
- Kiểm tra các verifier, instance, region và đường gọi trực tiếp; không chỉ test API Gateway.
- JWE dùng authentication tag và quy trình giải mã riêng; không nhầm với signature verification của JWS.

**Tài liệu tham khảo kỹ thuật:** RFC 7515 (JSON Web Signature); RFC 7516 (JSON Web Encryption); RFC 7517 (JSON Web Key); RFC 7518 (JSON Web Algorithms); RFC 7519 (JSON Web Token); RFC 8725 (JSON Web Token Best Current Practices); RFC 6750 (The OAuth 2.0 Authorization Framework: Bearer Token Usage). Các chuẩn này xác định serialization, chữ ký, mã hóa và cách xử lý token; test harness cần xác minh đúng byte signing input và các security invariant của ứng dụng.
