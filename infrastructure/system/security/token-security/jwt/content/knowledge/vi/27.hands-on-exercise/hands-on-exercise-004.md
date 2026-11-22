# Thực nghiệm thay đổi claims và phát hiện chữ ký không hợp lệ

## 1. Mục tiêu thực hành

Trong bài này, bạn sẽ tạo và kiểm tra một JWT có chữ ký trong môi trường lab, sau đó thay đổi từng phần của token để quan sát sự khác nhau giữa lỗi cấu trúc, lỗi chữ ký và lỗi policy claims.

Điểm cần chứng minh qua thực nghiệm:

- JWT có thể được decode và đọc payload mà không cần xác minh chữ ký.
- Thay đổi payload hoặc protected header mà giữ nguyên chữ ký ban đầu làm thay đổi signing input và khiến xác minh JWS thất bại.
- Thay đổi signature hoặc cắt ghép các segment cũng phải bị phát hiện.
- Một JWT được ký lại hợp lệ vẫn có thể bị từ chối vì issuer, audience, thời gian, scope hoặc tenant không phù hợp.
- Hệ thống chỉ được tin claims sau khi xác minh mật mã và hoàn tất các kiểm tra profile cần thiết.

Đây là bài thực hành tổng hợp thuộc module Security - JSON Web Token (JWT), chương Thực hành tổng hợp. Các bước sử dụng khái niệm và pseudocode độc lập ngôn ngữ, dựa trên thư viện JOSE/JWT đã được kiểm chứng. Phạm vi không phụ thuộc Java, Spring Security hoặc framework cụ thể.

## 2. Phạm vi và an toàn của lab

Chỉ thực hiện trong môi trường kiểm thử do bạn kiểm soát:

- Dùng issuer giả lập và API giả lập.
- Dùng private key được tạo riêng cho lab.
- Dùng subject, tenant và dữ liệu giả.
- Không sử dụng token, khóa, tài khoản hoặc dữ liệu production.
- Không gửi token đã sửa tới hệ thống bên ngoài.
- Không thử thay đổi JWT của người khác hoặc tìm cách vượt qua hệ thống không được phép kiểm thử.

Lab dùng JWS ký bất đối xứng để tách rõ vai trò:

- Issuer test giữ private key để ký token.
- Resource Server test chỉ giữ public key để xác minh.
- Người thực hành tạo các biến thể token trong phạm vi lab.

Có thể dùng thuật toán chữ ký được thư viện JOSE hỗ trợ và policy cho phép, ví dụ RS256 hoặc ES256. Không tự viết thuật toán mật mã. Nếu hệ thống thực tế dùng thuật toán khác, điều chỉnh fixture theo profile được hỗ trợ.

## 3. Kiến trúc và dữ liệu mẫu

Mô hình lab:

~~~mermaid
flowchart LR
    I["Test Issuer"] -->|"JWS + private signing key"| C["JWT Test Client"]
    C -->|"Bearer token"| R["Test Resource Server"]
    R --> K["Trusted public key"]
    R --> P["Validation policy"]
    P --> O["Accept hoặc Reject"]
~~~

Thông tin cố định:

| Thành phần | Giá trị |
| --- | --- |
| Issuer | https://lab-id.example.test/ |
| Resource Server | Orders API |
| Audience mong đợi | https://lab-api.example.test/orders |
| Subject | user-42 |
| Client | lab-web-client |
| Tenant | tenant-blue |
| Scope | orders:read |
| Signing algorithm | RS256 hoặc thuật toán bất đối xứng được lab cho phép |
| Token profile | JWT Access Token theo policy của lab |

Resource Server được cấu hình sẵn:

- Trust đúng issuer lab.
- Public key tương ứng với private key của issuer lab.
- Allowlist thuật toán cố định.
- Audience chính xác của Orders API.
- Token profile mong đợi.
- Test clock cố định để kiểm tra exp và nbf.
- Quyền đọc dữ liệu chỉ dành cho tenant-blue.

Không lấy issuer, key URL hoặc allowlist thuật toán từ token chưa xác minh. Cấu hình tin cậy được chọn từ endpoint của lab.

## 4. Chuẩn bị token gốc

Yêu cầu Test Issuer tạo một JWS có claims sau:

~~~json
{
  "iss": "https://lab-id.example.test/",
  "sub": "user-42",
  "aud": "https://lab-api.example.test/orders",
  "client_id": "lab-web-client",
  "tenant_id": "tenant-blue",
  "scope": "orders:read",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456900,
  "jti": "lab-token-0001"
}
~~~

Protected header mẫu:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "lab-signing-key-01"
}
~~~

Các timestamp ở trên chỉ là fixture minh họa. Khi chạy lab, cấu hình test clock tương ứng hoặc sinh iat, nbf và exp theo thời điểm test. Không để kết quả phụ thuộc vào thời gian thực ngẫu nhiên.

Lưu token gốc trong bộ nhớ hoặc file fixture được bảo vệ của môi trường lab. Đặt tên biến thể là:

- T0: token gốc hợp lệ.
- T1: payload bị thay nhưng giữ chữ ký cũ.
- T2: protected header bị thay nhưng giữ chữ ký cũ.
- T3: signature bị thay.
- T4: token được ký lại nhưng audience sai.
- T5: token được ký lại nhưng thời gian sai.
- T6: token được ký lại nhưng tenant hoặc scope sai.

Không đưa raw token vào log, screenshot hoặc báo cáo.

## 5. Hiểu cấu trúc JWS trước khi sửa

JWS Compact Serialization có ba segment, phân cách bằng hai dấu chấm:

~~~text
BASE64URL(protected-header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Ví dụ biểu diễn:

~~~text
eyJhbGciOiJSUzI1NiIsInR5cCI6ImF0K2p3dCIsImtpZCI6ImxhYi1zaWduaW5nLWtleS0wMSJ9
.
eyJpc3MiOiJodHRwczovL2xhYi1pZC5leGFtcGxlLnRlc3QvIiwic3ViIjoidXNlci00MiIsLi4ufQ
.
<signature-bytes-encoded>
~~~

Các chuỗi trên chỉ minh họa hình dạng, không phải token hoàn chỉnh có thể dùng.

### 5.1. Payload có thể đọc được nhưng chưa đáng tin

Base64URL là cách mã hóa biểu diễn dữ liệu, không phải mã hóa bí mật. Có thể decode hai segment đầu để xem JSON mà không cần private key hoặc public key.

Tuy nhiên:

- Decode không xác minh chữ ký.
- JSON parse thành công không chứng minh token do issuer phát hành.
- Claims nhìn có vẻ hợp lệ vẫn có thể bị sửa.
- Không được dùng dữ liệu vừa decode để cấp quyền trước khi verify.

### 5.2. Signing input là byte sequence cụ thể

Với JWS Compact, signing input là:

~~~text
ASCII(BASE64URL(protected-header) + "." + BASE64URL(payload))
~~~

Chữ ký được tính trên chính byte sequence này. Nếu đổi payload, header, cách biểu diễn hoặc một byte trong signing input, chữ ký cũ không còn khớp.

Không parse JSON rồi serialize lại theo cách tùy ý trước khi xác minh. Không tự tái tạo signing input bằng logic riêng khi thư viện JOSE có thể xử lý token gốc.

## 6. Bước 1: xác minh token gốc

Gửi T0 tới endpoint kiểm thử của Orders API.

Quy trình xác minh kỳ vọng:

1. Parse token theo giới hạn kích thước.
2. Chọn policy Orders API từ cấu hình endpoint.
3. Kiểm tra thuật toán nằm trong allowlist.
4. Tìm public key trong JWKS hoặc trust store đã cấu hình.
5. Xác minh JWS bằng thư viện JOSE.
6. Kiểm tra typ và Access Token profile.
7. Kiểm tra iss và aud.
8. Kiểm tra exp, nbf và các claim bắt buộc.
9. Kiểm tra scope và tenant.
10. Thực hiện authorization trên tài nguyên giả lập.

Kết quả mong đợi:

| Hạng mục | Kết quả |
| --- | --- |
| Parse | Thành công |
| Signature | Hợp lệ |
| Issuer | Khớp |
| Audience | Khớp Orders API |
| Token profile | Khớp |
| Thời gian | Trong hiệu lực |
| Scope | Đủ orders:read |
| Tenant | tenant-blue |
| Kết quả | Chấp nhận nếu subject được phép đọc tài nguyên |

Ghi nhận fixture ID, policy ID, kết quả và request ID. Không ghi token.

## 7. Bước 2: thay đổi payload nhưng giữ nguyên chữ ký

Đây là thí nghiệm chính để chứng minh chữ ký bảo vệ payload.

### 7.1. Thay subject

Tạo bản sao của T0. Decode payload, đổi:

~~~json
"sub": "user-42"
~~~

thành:

~~~json
"sub": "user-admin"
~~~

Encode payload mới bằng Base64URL, sau đó ghép với protected header và signature cũ. Không ký lại token.

Gửi biến thể tới endpoint lab.

Kết quả mong đợi:

- Token có thể parse về mặt cấu trúc.
- Payload decode được và hiển thị subject mới.
- Signing input đã thay đổi.
- Chữ ký cũ không còn hợp lệ.
- Resource Server từ chối trước khi dùng subject mới cho authorization.

Điểm quan sát: nếu hệ thống vẫn chấp nhận token hoặc dùng subject mới dù chữ ký sai, đây là lỗi nghiêm trọng ở ranh giới xác minh.

### 7.2. Thay scope

Trên một bản sao mới từ T0, đổi:

~~~json
"scope": "orders:read"
~~~

thành:

~~~json
"scope": "orders:read orders:write"
~~~

Giữ nguyên chữ ký.

Kết quả mong đợi là signature verification failure. API không được cấp quyền ghi chỉ vì payload hiển thị thêm scope.

### 7.3. Thay audience

Đổi audience từ Orders API sang:

~~~json
"aud": "https://lab-api.example.test/admin"
~~~

Giữ nguyên chữ ký.

Kết quả mong đợi: xác minh chữ ký thất bại. Không được coi audience mới là dữ liệu đã xác thực.

### 7.4. Thay thời gian

Đổi exp thành một giá trị rất xa trong tương lai, giữ chữ ký cũ. Kết quả phải là signature verification failure. Không được chấp nhận token chỉ vì exp mới có vẻ còn hiệu lực.

### 7.5. Thay tenant

Đổi tenant-blue thành tenant-red, giữ chữ ký cũ. Kết quả phải là signature verification failure. Không được truy cập dữ liệu tenant-red.

## 8. Bước 3: thay protected header nhưng giữ chữ ký cũ

Protected header là một phần của signing input. Vì vậy, sửa header cũng làm chữ ký cũ không còn hợp lệ.

Thử từng biến thể trên bản sao độc lập:

| Thay đổi | Kết quả mong đợi |
| --- | --- |
| Đổi kid sang khóa khác | Từ chối; không dùng khóa ngoài trust store |
| Đổi typ từ at+jwt sang loại khác | Từ chối do chữ ký sai hoặc profile không khớp |
| Đổi alg sang thuật toán ngoài allowlist | Từ chối theo policy trước hoặc trong bước xác minh |
| Thêm header parameter không được hỗ trợ | Từ chối nếu profile/parser yêu cầu |
| Thay thứ tự hoặc nội dung header rồi serialize lại | Chữ ký cũ không còn khớp signing input |

Thứ tự kiểm tra lỗi cụ thể phụ thuộc thư viện. Có thể hệ thống từ chối alg không được phép trước khi thực hiện verify; điều quan trọng là token không được chấp nhận.

Không thay alg để thử ép verifier dùng một thuật toán khác. Đây là test âm trong lab để xác nhận allowlist và key binding.

## 9. Bước 4: thay signature

Tạo các biến thể:

- Đổi một ký tự trong segment signature.
- Xóa một phần signature.
- Thêm ký tự không thuộc Base64URL.
- Thay signature bằng chuỗi rỗng.
- Dùng signature của một token khác cùng issuer nhưng payload khác.

Kết quả mong đợi:

- Token malformed bị từ chối ở bước parse.
- Token có cấu trúc nhưng signature không khớp bị từ chối ở bước verify.
- Signature lấy từ token khác không xác minh được signing input hiện tại.
- Không có biến thể nào được tạo validated token context.

Không cần đoán hoặc tự tính signature. Dùng thư viện JOSE để tạo token gốc và thực hiện mutation trên các segment trong test harness.

## 10. Bước 5: phân biệt signature failure với claims failure

Các bước trước chứng minh sửa dữ liệu mà giữ chữ ký cũ sẽ làm xác minh chữ ký thất bại. Bước này chứng minh một token có chữ ký hợp lệ vẫn có thể sai policy.

Trong lab, dùng Test Issuer và private key lab để ký lại payload đã thay đổi. Đây là hành động mô phỏng issuer phát hành một token không phù hợp policy; không sử dụng khóa production hoặc khóa của bên khác.

Luồng:

1. Tạo claims mới.
2. Ký bằng private key của Test Issuer.
3. Giữ protected header và thuật toán được lab cho phép.
4. Gửi token tới Resource Server.
5. Xác nhận chữ ký hợp lệ.
6. Xác nhận policy claims từ chối token.

### 10.1. Audience sai nhưng chữ ký hợp lệ

Claims:

~~~json
{
  "iss": "https://lab-id.example.test/",
  "sub": "user-42",
  "aud": "https://lab-api.example.test/profiles",
  "scope": "orders:read",
  "iat": 1893456000,
  "exp": 1893456900
}
~~~

Ký lại bằng private key lab.

Kết quả mong đợi:

- Signature: hợp lệ.
- Issuer: hợp lệ.
- Audience: sai đối với Orders API.
- Kết quả cuối: từ chối do audience mismatch.

### 10.2. Issuer sai nhưng chữ ký hợp lệ

Tạo token được ký bằng key lab nhưng claim iss khai báo issuer khác với issuer policy.

Kết quả mong đợi:

- Nếu key resolver được chọn từ policy issuer lab, chữ ký có thể hợp lệ bằng key lab.
- Claim iss không khớp trust configuration.
- Token bị từ chối.

Không dùng claim iss chưa xác minh để tự động tải JWKS hoặc thay trust configuration.

### 10.3. Token hết hạn nhưng chữ ký hợp lệ

Ký token có exp nằm trong quá khứ theo test clock. Không dựa vào thời gian thực; đặt test clock rõ ràng.

Kết quả mong đợi:

- Signature: hợp lệ.
- Issuer/audience/profile: hợp lệ.
- exp: không hợp lệ.
- Kết quả cuối: từ chối do expired token.

### 10.4. Token chưa tới nbf

Ký token có nbf nằm sau test clock nhiều hơn leeway được cấu hình.

Kết quả mong đợi: signature hợp lệ nhưng token bị từ chối do chưa tới thời điểm có hiệu lực.

### 10.5. Scope không đủ

Ký token hợp lệ với audience Orders API nhưng scope chỉ là:

~~~json
"scope": "orders:read"
~~~

Gửi request thực hiện thao tác ghi yêu cầu orders:write.

Kết quả mong đợi:

- Signature và claims cơ bản hợp lệ.
- Audience hợp lệ.
- Scope không đủ cho thao tác.
- Authorization từ chối.

Đây là authorization failure, không phải signature failure.

### 10.6. Tenant không khớp

Ký token hợp lệ với tenant-blue nhưng gửi request tới tài nguyên tenant-red.

Kết quả mong đợi:

- Signature hợp lệ.
- Audience hợp lệ.
- Tenant/resource context không khớp.
- Từ chối tại tenant/resource authorization boundary.
- Không đọc, sửa hoặc phát event liên quan tenant-red.

## 11. Bảng phân loại kết quả

| Loại biến thể | Signature | Claims/profile | Kết quả |
| --- | --- | --- | --- |
| Token gốc | Hợp lệ | Hợp lệ | Chấp nhận nếu authorization đạt |
| Payload bị sửa, giữ chữ ký cũ | Không hợp lệ | Không được tin | Từ chối |
| Header bị sửa, giữ chữ ký cũ | Không hợp lệ hoặc bị policy từ chối trước | Không được tin | Từ chối |
| Signature bị sửa | Không hợp lệ | Không được tin | Từ chối |
| Token ký lại, aud sai | Hợp lệ | Sai audience | Từ chối |
| Token ký lại, iss sai | Có thể hợp lệ bằng key lab | Sai issuer | Từ chối |
| Token ký lại, exp quá khứ | Hợp lệ | Hết hạn | Từ chối |
| Token ký lại, nbf tương lai | Hợp lệ | Chưa hiệu lực | Từ chối |
| Token ký lại, scope thiếu | Hợp lệ | Claims hợp lệ cho quyền thấp hơn | Authorization từ chối |
| Token ký lại, tenant không khớp tài nguyên | Hợp lệ | Context không phù hợp | Từ chối |

Không gộp mọi lỗi thành “invalid signature”. Cần phân loại lỗi để vận hành và kiểm thử chính xác, nhưng phản hồi bên ngoài không nên tiết lộ chi tiết nội bộ nhạy cảm.

## 12. Quy trình xác minh an toàn

Một Resource Server nên xử lý theo thứ tự có kiểm soát:

~~~mermaid
flowchart TD
    A["Nhận token"] --> B["Parse có giới hạn"]
    B --> C["Chọn policy từ endpoint tin cậy"]
    C --> D["Kiểm tra alg và tìm key trong trust store"]
    D --> E["Verify chữ ký bằng JOSE library"]
    E --> F{"Signature hợp lệ?"}
    F -- "Không" --> X["Từ chối: invalid token"]
    F -- "Có" --> G["Kiểm tra typ/profile, iss và aud"]
    G --> H["Kiểm tra exp, nbf, iat và claims"]
    H --> I["Kiểm tra revocation/binding nếu yêu cầu"]
    I --> J["Authorization: scope, tenant, ownership"]
    J --> K{"Được phép?"}
    K -- "Không" --> Y["Từ chối authorization"]
    K -- "Có" --> Z["Xử lý request"]
~~~

Header và payload chưa xác minh chỉ là dữ liệu đầu vào không đáng tin. Không dùng sub, scope hoặc tenant từ token trước khi chữ ký và profile đã được xác minh.

Nếu có nested JWT, cần xác minh từng lớp theo profile. Nếu dùng JWE, chỉ xử lý plaintext sau khi authenticated decryption thành công.

## 13. Pseudocode cho test harness

~~~text
function createBaselineToken(testIssuer, validClaims, policy):
    return joseLibrary.sign(
        claims = validClaims,
        privateKey = testIssuer.privateKey,
        algorithm = policy.allowedSigningAlgorithm,
        protectedHeader = policy.expectedProtectedHeader
    )

function mutateSegmentWithoutResigning(token, segment, mutation):
    parts = splitCompactJws(token)
    parts[segment] = mutation(parts[segment])
    return joinWithDots(parts)

function runValidationCase(token, endpoint, expected):
    result = resourceServer.validate(token, endpoint)

    assert result.accepted == expected.accepted
    assert result.failureCategory == expected.failureCategory
    assert noUnauthorizedSideEffectOccurred()
    assert auditDoesNotContainRawToken()

function testPayloadTampering():
    original = createBaselineToken(testIssuer, validClaims, policy)
    changed = mutateSegmentWithoutResigning(
        original,
        PAYLOAD_SEGMENT,
        replaceSubject("user-42", "user-admin")
    )
    runValidationCase(
        changed,
        ordersEndpoint,
        expected = { accepted: false, failureCategory: SIGNATURE_INVALID }
    )

function testSignedButWrongAudience():
    claims = copy(validClaims)
    claims.aud = profileApiAudience
    newlySigned = createBaselineToken(testIssuer, claims, policy)
    runValidationCase(
        newlySigned,
        ordersEndpoint,
        expected = { accepted: false, failureCategory: AUDIENCE_MISMATCH }
    )
~~~

Pseudocode mô tả trách nhiệm của test harness; tên hàm không phải API của một thư viện cụ thể. Hàm mutateSegmentWithoutResigning chỉ dùng fixture của lab. Không ghi raw token ra console hoặc test report.

## 14. Kiểm tra dữ liệu không bị sử dụng trước khi verify

Một lỗi nguy hiểm là ứng dụng decode payload, đọc sub hoặc scope rồi thực hiện một phần logic trước khi verify chữ ký.

Tạo test có payload bị sửa thành subject quản trị nhưng giữ signature cũ. Sau đó quan sát:

- Không truy vấn dữ liệu theo subject giả trước khi verify.
- Không tạo session hoặc cache entry dựa trên claims chưa xác minh.
- Không gửi message/event chứa subject giả.
- Không ghi audit rằng người dùng quản trị đã thực hiện thao tác.
- Không trả response chứa dữ liệu thuộc subject giả.

Nếu ứng dụng có middleware hoặc gateway, kiểm tra cả đường đi trước và sau middleware. Không chỉ test validator riêng lẻ.

## 15. Các biến thể bổ sung

### 15.1. Thay đổi JSON nhưng giữ nguyên ý nghĩa

Thử thay đổi whitespace, thứ tự thuộc tính JSON hoặc escape trong payload rồi giữ chữ ký cũ.

Kết quả: signing input thay đổi nên chữ ký cũ không còn hợp lệ, dù JSON sau khi parse có thể biểu diễn dữ liệu tương đương.

### 15.2. Duplicate JSON member

Tạo payload kiểm thử có hai thuộc tính cùng tên, ví dụ hai giá trị aud. Các parser có thể xử lý duplicate member khác nhau.

Kết quả an toàn là từ chối cấu trúc mơ hồ theo parser/profile policy. Không để gateway và downstream diễn giải hai giá trị khác nhau.

### 15.3. Claim sai kiểu dữ liệu

Ký lại token lab với các trường hợp:

- exp là chuỗi thay vì NumericDate.
- aud là object.
- scope là object thay vì dạng được profile hỗ trợ.
- tenant_id là mảng trong khi policy yêu cầu một giá trị.
- iat là số vượt phạm vi hợp lý.

Signature có thể hợp lệ nhưng claims/profile validation phải từ chối.

### 15.4. Base64URL hoặc Compact Serialization sai

Thử:

- Segment rỗng không được phép.
- Thiếu hoặc thừa dấu chấm.
- Ký tự không thuộc Base64URL.
- Token có quá nhiều segment.
- Token vượt giới hạn kích thước.

Kết quả phải là parse failure trước khi tạo validated context.

## 16. Ma trận kiểm thử tổng hợp

| ID | Thao tác | Signature | Policy/Authorization | Kết quả |
| --- | --- | --- | --- | --- |
| L-001 | Token gốc | Hợp lệ | Đạt | Chấp nhận |
| L-002 | Sửa sub, giữ signature | Sai | Không đánh giá claims | Từ chối |
| L-003 | Sửa scope, giữ signature | Sai | Không đánh giá claims | Từ chối |
| L-004 | Sửa aud, giữ signature | Sai | Không đánh giá claims | Từ chối |
| L-005 | Sửa exp, giữ signature | Sai | Không đánh giá claims | Từ chối |
| L-006 | Sửa tenant, giữ signature | Sai | Không đánh giá claims | Từ chối |
| L-007 | Sửa protected header | Sai hoặc bị policy từ chối trước | Không được chấp nhận | Từ chối |
| L-008 | Sửa signature | Sai | Không đánh giá claims | Từ chối |
| L-009 | Dùng signature từ token khác | Sai | Không đánh giá claims | Từ chối |
| L-010 | Ký lại với audience sai | Đúng | Audience sai | Từ chối |
| L-011 | Ký lại với issuer sai | Có thể đúng bằng key lab | Issuer sai | Từ chối |
| L-012 | Ký lại với exp quá khứ | Đúng | Hết hạn | Từ chối |
| L-013 | Ký lại với nbf tương lai | Đúng | Chưa hiệu lực | Từ chối |
| L-014 | Ký lại thiếu scope ghi | Đúng | Scope không đủ | Authorization từ chối |
| L-015 | Ký lại tenant-blue, truy cập tenant-red | Đúng | Tenant mismatch | Từ chối |
| L-016 | JSON duplicate member | Theo fixture | Cấu trúc mơ hồ | Từ chối |
| L-017 | Claim sai kiểu | Đúng | Profile sai | Từ chối |
| L-018 | Token malformed | Không tới bước verify | Parse failure | Từ chối |
| L-019 | Token đúng nhưng đã revoke | Đúng | Revocation policy fail | Từ chối |
| L-020 | Token đúng chữ ký nhưng sai typ | Đúng | Token profile mismatch | Từ chối |

## 17. Tiêu chí đánh giá kết quả

Lab đạt yêu cầu khi:

- T0 được chấp nhận trong điều kiện fixture và policy hợp lệ.
- Mọi thay đổi payload/header/signature mà không ký lại đều không qua xác minh JWS.
- Không có claim chưa xác minh nào được dùng cho authorization hoặc side effect.
- Token được ký lại bằng khóa test nhưng có audience/issuer/time/profile sai vẫn bị từ chối.
- Token có chữ ký và claims hợp lệ nhưng thiếu scope vẫn bị từ chối thao tác tương ứng.
- Tenant mismatch không làm rò rỉ dữ liệu hoặc tạo side effect.
- Lỗi được phân loại đủ rõ trong test harness.
- Log và report không chứa raw token, private key hoặc dữ liệu nhạy cảm.
- Kết quả nhất quán qua các replica dùng cùng policy.

Nếu token bị sửa vẫn được chấp nhận, dừng lab và kiểm tra:

1. Endpoint có thật sự gọi verifier không?
2. Có đường code nào chỉ decode JWT mà không verify không?
3. Có validator nào cấu hình bỏ qua signature không?
4. Có thuật toán ngoài allowlist hoặc key confusion không?
5. Có cache hoặc middleware trả kết quả cũ không?
6. Downstream có tin header identity do client gửi không?

Không sửa policy theo hướng nới lỏng để làm test pass.

## 18. Lỗi thường gặp khi thực hiện lab

| Lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Chỉ decode token rồi kết luận hợp lệ | Decode không xác minh chữ ký | Gọi verify bằng trusted key |
| Sửa payload nhưng quên giữ signature cũ | Không còn kiểm tra đúng thí nghiệm tampering | Tạo fixture mutation rõ ràng |
| Sửa payload rồi ký lại nhưng kỳ vọng signature fail | Chữ ký mới có thể hợp lệ | Phân loại thành claims/policy test |
| Dùng private key production | Tạo rủi ro credential thật | Chỉ dùng key pair lab |
| Chỉ test token malformed | Không kiểm tra policy với chữ ký hợp lệ | Dùng token ký hợp lệ nhưng sai claims |
| Dùng clock thực không cố định | Test exp/nbf không ổn định | Dùng test clock |
| Chỉ kiểm tra HTTP status | Có thể có side effect trước khi từ chối | Kiểm tra database, event và cache |
| Log toàn bộ token để debug | Làm lộ bearer credential | Log fixture ID và error category |
| Cho phép validator tự tải key từ header | Tạo trust/SSRF risk | Dùng trusted key resolver |
| Gộp signature và authorization thành một lỗi | Khó xác định lớp lỗi | Phân loại cryptographic, claims và authorization |

## 19. Báo cáo kết quả lab

Mỗi ca kiểm thử nên lưu:

| Trường | Nội dung |
| --- | --- |
| Test ID | Ví dụ L-002 |
| Fixture ID | T1, T4 hoặc tên fixture |
| Endpoint | Orders API |
| Mutation | Payload subject, audience, signature... |
| Signature result | Valid/Invalid/Not evaluated |
| Claims result | Pass/Fail/Not evaluated |
| Authorization result | Allow/Deny/Not evaluated |
| Side effect | None hoặc mô tả fixture state thay đổi |
| Policy version | Phiên bản policy test |
| Result | PASS/FAIL |

Không ghi raw token. Nếu cần đối chiếu fixture, dùng ID ngẫu nhiên riêng cho lab hoặc fingerprint chỉ dùng trong môi trường test; không dùng hash ổn định của production token.

## 20. Checklist kết thúc

1. [ ] Tạo issuer và key pair riêng cho lab.
2. [ ] Cấu hình trusted issuer, audience, algorithm allowlist và token profile.
3. [ ] Tạo T0 có chữ ký hợp lệ và claims đúng.
4. [ ] Xác minh T0 được chấp nhận.
5. [ ] Sửa từng claim trong payload nhưng giữ signature cũ.
6. [ ] Xác nhận mọi payload mutation đều làm verify thất bại.
7. [ ] Sửa protected header và signature để kiểm tra phát hiện tampering.
8. [ ] Ký lại các fixture bằng private key lab với audience/issuer/time/tenant/scope sai.
9. [ ] Xác nhận signature hợp lệ không làm token vượt claims policy.
10. [ ] Kiểm tra token sai scope bị authorization từ chối.
11. [ ] Kiểm tra tenant mismatch không đọc hoặc sửa dữ liệu.
12. [ ] Kiểm tra không dùng claims trước khi verify.
13. [ ] Kiểm tra parse error, duplicate member, sai kiểu và giới hạn kích thước.
14. [ ] Kiểm tra revocation, typ và kết quả giữa các replica.
15. [ ] Xác nhận log/report không chứa raw token hoặc secret.
16. [ ] Thu hồi hoặc xóa key, token fixture và dữ liệu lab theo quy trình cleanup.

## 21. Tài liệu tiêu chuẩn liên quan

- **RFC 7515 — JSON Web Signature (JWS):** signing input, protected header và xác minh chữ ký.
- **RFC 7518 — JSON Web Algorithms (JWA):** thuật toán chữ ký và cách biểu diễn trong JOSE.
- **RFC 7519 — JSON Web Token (JWT):** claims và NumericDate.
- **RFC 7517 — JSON Web Key (JWK):** biểu diễn khóa và JWKS.
- **RFC 8725 — JSON Web Token Best Current Practices:** algorithm verification, issuer/audience validation, explicit typing và phòng token confusion.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile Access Token dạng JWT.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** sử dụng bearer token và phản hồi lỗi.

**Nguyên tắc ghi nhớ:** Sửa payload hoặc protected header mà giữ chữ ký cũ phải làm JWS verification thất bại. Nếu một token được ký lại bằng khóa issuer nhưng claims sai, chữ ký vẫn có thể hợp lệ và policy phải từ chối nó ở bước phù hợp. Kiểm thử cả hai trường hợp mới chứng minh được hệ thống phân biệt integrity, token validation và authorization.
