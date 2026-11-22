# Ngăn sử dụng API decode như bằng chứng xác thực

## 1. Đọc được JWT không có nghĩa là đã xác thực JWT

Một JSON Web Token (JWT) thường có dạng ba phần được ngăn bằng dấu chấm:

~~~text
BASE64URL(protected-header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Với JWS Compact Serialization, header và payload được mã hóa Base64URL. Đây là encoding để truyền dữ liệu, không phải cơ chế mã hóa bí mật. Bất kỳ ai có token đều có thể decode hai phần đầu và đọc JSON mà không cần khóa ký.

Vì vậy, một thư viện có thể trả về subject, role, scope, issuer hoặc expiration sau khi decode token, ngay cả khi:

- Chữ ký bị sửa hoặc hoàn toàn không hợp lệ.
- Token được ký bởi một issuer không được tin cậy.
- Token dành cho API khác.
- Token đã hết hạn hoặc chưa đến thời điểm có hiệu lực.
- Token thuộc loại khác, chẳng hạn ID Token thay vì access token.
- Claims không đáp ứng hợp đồng của API.

Nếu ứng dụng lấy claims từ kết quả decode rồi dùng chúng để đăng nhập, cấp quyền hoặc xác định danh tính, nó đang biến dữ liệu do người gửi kiểm soát thành dữ liệu tin cậy.

**Decode chỉ giúp đọc nội dung. Xác minh chữ ký và kiểm tra token theo đúng profile mới có thể thiết lập niềm tin cần thiết để sử dụng claims.**

## 2. Phân biệt các thao tác của thư viện JWT

Tên hàm giữa các thư viện không thống nhất. Không được suy luận mức bảo vệ chỉ từ tên decode, parse, verify hoặc validate; cần đọc tài liệu và hợp đồng của phiên bản thư viện đang dùng.

| Thao tác | Việc thường thực hiện | Điều chưa thể kết luận |
| --- | --- | --- |
| Decode | Giải mã Base64URL và đọc JSON header/payload | Không chứng minh chữ ký, issuer hoặc quyền |
| Parse | Phân tích cấu trúc, kiểm tra định dạng; tùy thư viện có thể kèm verify | Không mặc nhiên có nghĩa token đã được xác thực |
| Verify signature | Kiểm tra chữ ký theo thuật toán và khóa được cung cấp | Không tự bảo đảm issuer/audience/thời gian/profile hợp lệ |
| Validate token/profile | Kiểm tra chữ ký hoặc cơ chế bảo vệ cùng các ràng buộc theo policy/profile | Chỉ có ý nghĩa nếu policy bao gồm đầy đủ điều kiện cần thiết |
| Decrypt JWE | Giải mã nội dung được mã hóa | Không tự chứng minh mọi claim đúng hoặc bên gửi là issuer được tin cậy |

Một số thư viện có API decode với tùy chọn verifySignature=true; thư viện khác tách decode và verify. Có thư viện parse trả về object đã xác minh khi được truyền key và algorithm; cũng có thư viện chỉ parse cấu trúc. Một API có tên validate vẫn có thể chỉ kiểm tra một số claim hoặc sử dụng cấu hình mặc định không phù hợp.

Hãy kiểm tra chính xác:

- Hàm có xác minh chữ ký hay chỉ decode?
- Hàm lấy key từ đâu?
- Thuật toán được cho phép lấy từ cấu hình hay tự động chấp nhận alg trong token?
- Có kiểm tra iss, aud, exp, nbf và token type không?
- Có hỗ trợ required claims và schema không?
- Lỗi xác minh được ném ra, trả về trạng thái hay bị chuyển thành kết quả rỗng?
- Có tùy chọn nào vô tình tắt signature verification hoặc claim validation?

## 3. Ranh giới tin cậy: dữ liệu trước và sau verify

Trước khi chữ ký hoặc cơ chế bảo vệ được xác minh, token là dữ liệu đầu vào không đáng tin cậy. Header và payload có thể do bất kỳ ai tạo ra.

Ví dụ attacker có thể tự tạo một chuỗi JWT với payload:

~~~json
{
  "sub": "admin",
  "role": "administrator",
  "iss": "https://identity.example.org",
  "aud": "https://api.example.org",
  "exp": 1999999999
}
~~~

Nếu ứng dụng chỉ decode và đọc role, attacker có thể sửa payload thành administrator mà không cần khóa ký. Việc token có đúng số phần và JSON hợp lệ không làm claims đáng tin hơn.

Một quy tắc triển khai dễ áp dụng:

- Dữ liệu decode trước verify chỉ dùng cho chẩn đoán có kiểm soát hoặc làm gợi ý tra cứu trong allowlist tin cậy.
- Không dùng claims chưa xác minh để tạo principal, cấp role, chọn tenant, đọc dữ liệu hoặc thực hiện side effect.
- Chỉ chuyển kết quả sang trusted context sau khi mọi bước bắt buộc đã thành công.
- Nếu verify hoặc validate thất bại, không tiếp tục xử lý bằng claims đã decode.

Ngay cả sau khi chữ ký hợp lệ, claims vẫn phải được hiểu theo issuer, audience và profile. Chữ ký chứng minh dữ liệu được ký bằng khóa tương ứng; nó không chứng minh issuer đã cấp claim đúng nghiệp vụ hoặc claim phù hợp với endpoint hiện tại.

## 4. Vì sao chữ ký hợp lệ vẫn chưa đủ?

Không nên thay lỗi chỉ decode bằng giả định chỉ verify signature là đủ. Xác minh chữ ký là một bước trong quá trình chấp nhận token.

| Kiểm tra | Câu hỏi cần trả lời |
| --- | --- |
| Cấu trúc | Token có đúng dạng và nằm trong giới hạn kích thước không? |
| Thuật toán | alg có nằm trong allowlist của profile không? |
| Khóa | Khóa có đến từ nguồn tin cậy và đúng issuer không? |
| Chữ ký | Chữ ký có hợp lệ trên đúng signing input không? |
| Issuer | iss có khớp issuer được cấu hình không? |
| Audience | aud có chứa định danh resource server hiện tại không? |
| Thời gian | exp, nbf, iat có hợp lệ theo policy không? |
| Token type | Đây có phải loại token endpoint đang chấp nhận không? |
| Claims/profile | Claims bắt buộc, kiểu dữ liệu và ngữ nghĩa có đúng không? |
| Authorization | Chủ thể có quyền thực hiện hành động trên tài nguyên cụ thể không? |

Ví dụ, một access token được ký đúng bởi issuer tin cậy nhưng có audience dành cho API hồ sơ không được chấp nhận tại API thanh toán. Chữ ký hợp lệ không thay thế kiểm tra audience.

## 5. Chọn thuật toán từ policy, không từ token

JOSE header có trường alg để chỉ thuật toán. Trước khi xác minh, header này vẫn là dữ liệu do người gửi cung cấp.

Không để thư viện tự chọn bất kỳ thuật toán nào mà token yêu cầu. Ứng dụng phải cấu hình allowlist theo issuer và token profile. Nếu profile chỉ cho phép RS256, token khai báo HS256, none hoặc thuật toán khác phải bị từ chối.

Các nguyên tắc quan trọng:

- Không chấp nhận alg=none trong profile yêu cầu chữ ký.
- Không nhầm khóa RSA công khai với HMAC secret.
- Không dùng một khóa cho nhiều thuật toán không tương thích.
- Kiểm tra loại khóa, mục đích sử dụng và thuật toán được cấu hình.
- Không tự động fallback sang thuật toán khác khi verify thất bại.

Nếu thư viện có tùy chọn algorithms, allowedAlgorithms, verificationMethod hoặc tên tương tự, phải cấu hình rõ thay vì để mặc định mở rộng.

## 6. Chọn khóa xác minh từ nguồn tin cậy

### 6.1. kid chỉ là gợi ý tìm khóa

Header có thể chứa kid để chỉ ra khóa trong JWKS. Có thể cần đọc header trước khi verify để chọn khóa, nhưng không được coi kid là bằng chứng về nguồn phát hành.

Quy trình an toàn:

1. Xác định issuer dự kiến từ cấu hình hoặc một danh sách issuer được tin cậy.
2. Đọc kid chưa xác minh như một chỉ mục tra cứu.
3. Chỉ tìm khóa trong tập khóa đã gắn với issuer đó.
4. Kiểm tra key type, algorithm, key use và trạng thái khóa.
5. Verify chữ ký.
6. Sau verify, kiểm tra iss khớp chính xác issuer đã chọn.

Không lấy khóa từ URL tùy ý trong token như jku hoặc x5u. Không dùng kid làm đường dẫn file hoặc URL. Không thử khóa của mọi issuer rồi chấp nhận khóa nào xác minh được.

### 6.2. JWKS và cache

Nếu dùng JWKS, endpoint phải được lấy từ metadata/configuration tin cậy. Cần có chính sách cache, refresh khi gặp kid mới, xử lý khóa bị thu hồi và giới hạn số lần refresh để tránh DoS.

Nếu không tìm được khóa phù hợp, từ chối token. Không fallback sang decode-only hoặc bỏ qua chữ ký khi JWKS endpoint tạm thời không khả dụng.

### 6.3. Không dùng key do token tự cung cấp làm trust anchor

Một số JOSE header có thể chứa jwk hoặc certificate chain theo profile. Dữ liệu này có thể giúp xác minh một proof hoặc cung cấp public key, nhưng tự nó không chứng minh issuer là bên đáng tin cậy.

Ví dụ DPoP dùng public JWK trong proof JWT để xác minh proof-of-possession. Resource server vẫn phải kiểm tra binding giữa proof và access token theo RFC 9449. Không áp dụng cách chọn public key do token mang vào cho access token thông thường rồi coi chữ ký là đáng tin.

## 7. Kiểm tra issuer, audience và thời gian sau verify

### 7.1. Issuer

So khớp iss với issuer được cấu hình chính xác. Không chấp nhận token chỉ vì iss có dạng URL hoặc thuộc một domain có vẻ quen thuộc. Nếu hỗ trợ nhiều issuer, mỗi issuer phải có trust configuration, thuật toán, key set và profile riêng.

### 7.2. Audience

Kiểm tra aud theo định danh của resource server. Theo RFC 7519, aud có thể là chuỗi hoặc mảng chuỗi; consumer phải xử lý đúng dạng theo profile và so khớp chính xác.

Không dùng chuỗi con, wildcard lỏng lẻo hoặc tiền tố để kết luận audience phù hợp. Token dành cho một API khác phải bị từ chối dù chữ ký hợp lệ.

### 7.3. Thời gian

- exp: từ chối token đã hết hạn theo quy tắc NumericDate và clock skew được cấu hình.
- nbf: không chấp nhận token trước thời điểm bắt đầu hiệu lực.
- iat: kiểm tra hợp lý và áp dụng max token age nếu profile yêu cầu.

Không mặc định thư viện luôn kiểm tra mọi claim thời gian. Có thư viện chỉ kiểm tra exp nếu bật tùy chọn; có thư viện không yêu cầu exp trừ khi ứng dụng đặt required claims. Hãy cấu hình rõ các điều kiện bắt buộc.

## 8. Kiểm tra đúng token type và profile

Một JWT có thể là access token, ID Token, client assertion, request object hoặc một token nội bộ. Không chấp nhận mọi JWT có chữ ký đúng ở mọi endpoint.

- API thường yêu cầu access token có audience của resource server.
- OIDC client kiểm tra ID Token theo OIDC Core; audience của ID Token là client.
- Token endpoint xác minh client assertion theo profile riêng.
- DPoP verifier kiểm tra proof JWT theo RFC 9449.

Nếu profile quy định typ, hãy kiểm tra theo profile. Ví dụ JWT access token theo RFC 9068 dùng media type at+jwt. typ không thay thế chữ ký, issuer, audience, thời gian hoặc claims bắt buộc.

Phân biệt profile giúp tránh cross-JWT confusion: một token hợp lệ cho mục đích này bị sử dụng nhầm ở mục đích khác.

## 9. JWE: decrypt cũng không đồng nghĩa với token được chấp nhận

Với JWE, thư viện có thể giải mã nội dung thành công. Điều đó cho biết recipient có khóa phù hợp và nội dung vượt qua kiểm tra mã hóa/toàn vẹn theo thuật toán được dùng. Nhưng không phải mọi mô hình JWE đều xác thực danh tính người gửi.

Ví dụ, khi dùng mã hóa khóa công khai đến recipient, bất kỳ bên nào có public encryption key của recipient có thể tạo JWE gửi đến recipient. Giải mã thành công không chứng minh nội dung do issuer mong đợi phát hành.

Nếu cần xác thực nguồn phát hành, profile có thể yêu cầu JWS lồng bên trong JWE hoặc cơ chế xác thực sender riêng. Sau khi decrypt, vẫn phải kiểm tra chữ ký (nếu profile yêu cầu), issuer, audience, thời gian, token type và authorization.

Không nhầm:

- Decode: đọc dữ liệu đã encoding.
- Decrypt: giải mã nội dung được bảo vệ bằng JWE.
- Verify: xác minh chữ ký/MAC theo khóa.
- Validate: kiểm tra toàn bộ điều kiện chấp nhận theo profile và policy.

## 10. Cấu hình thư viện theo hướng fail-closed

Một cách triển khai an toàn nên có một điểm vào rõ ràng cho từng token profile. Ví dụ pseudocode:

~~~text
function authenticateAccessToken(compactToken):
    enforceTokenSizeLimit(compactToken)

    header = parseUntrustedProtectedHeader(compactToken)
    untrustedClaims = parseUntrustedClaims(compactToken)
    issuerConfig = trustedIssuerRegistry.find(untrustedClaims.iss)
    if issuerConfig is missing:
        reject("untrusted issuer")

    require header.alg in issuerConfig.allowedAlgorithms
    key = issuerConfig.keySet.find(header.kid)
    require key exists
    require key.type and key.use match configured profile

    verified = jwtLibrary.verifySignature(
        compactToken,
        key,
        algorithms = issuerConfig.allowedAlgorithms
    )
    require verified

    claims = jwtLibrary.readVerifiedClaims(compactToken)
    require claims.iss == issuerConfig.issuer
    require audienceMatches(claims.aud, thisResourceServer)
    require timeClaimsAreValid(claims)
    require tokenTypeMatches(claims, header, "access-token-profile")
    require claimsConformToProfile(claims)

    return TrustedPrincipal.fromVerifiedClaims(claims)
~~~

Đây là pseudocode mô tả các ranh giới; tên hàm không đại diện API cụ thể của một thư viện. Issuer chưa xác minh chỉ được dùng như một lookup hint trong registry cố định đã tin cậy; không dùng giá trị này để tạo trust mới hoặc tải metadata/JWKS từ URL do token cung cấp. Nếu endpoint chỉ chấp nhận một issuer hoặc issuer được xác định theo tenant/route, hãy lấy issuer dự kiến từ cấu hình của endpoint và sau verify vẫn so khớp claim iss chính xác.

Hàm trả về TrustedPrincipal chỉ được gọi sau khi toàn bộ điều kiện bắt buộc đạt. Không trả object claims chưa xác minh rồi trông chờ caller nhớ tự kiểm tra.

### 10.1. Tách API decode và API authenticate

Nếu ứng dụng có nhu cầu decode để hiển thị/debug, hãy đặt tên và kiểu dữ liệu thể hiện rõ kết quả chưa tin cậy, ví dụ:

~~~text
UntrustedTokenPreview decodeForDiagnostics(rawToken)
TrustedPrincipal authenticateAccessToken(rawToken)
~~~

Không dùng chung một kiểu User, Principal hoặc Claims cho cả dữ liệu chưa xác minh và dữ liệu đã xác minh. Kiểu dữ liệu tách biệt giúp code review nhận ra luồng dữ liệu có thể đi vào authorization hay không.

Không cho phép code nghiệp vụ gọi decode trực tiếp rồi tự tạo principal. Tập trung việc xác minh trong một boundary có cấu hình rõ ràng và kiểm thử độc lập.

## 11. Những lỗi API/library integration thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gọi decode rồi tin claims | Token giả có thể tạo principal/role giả | Chỉ dùng kết quả sau verify và validate |
| Cho rằng parse luôn xác minh chữ ký | Có thể dùng parser chỉ đọc cấu trúc | Đọc hợp đồng và kiểm tra test của thư viện |
| Gọi verify nhưng không kiểm tra audience | Token của API khác vẫn được chấp nhận | Validate aud theo resource server |
| Dùng key lấy từ URL trong header | Attacker có thể điều khiển nguồn khóa | Dùng issuer/JWKS đã cấu hình tin cậy |
| Cho thư viện tự chọn mọi alg | Algorithm confusion hoặc chấp nhận thuật toán không mong muốn | Allowlist thuật toán |
| Tắt expiration validation để sửa lỗi test | Token hết hạn có thể được chấp nhận ở production | Dùng clock/test fixture phù hợp, giữ validation bật |
| Bắt mọi exception rồi tiếp tục bằng decoded claims | Verify failure bị biến thành success | Fail-closed, trả lỗi xác thực rõ ràng |
| Dùng chung validator cho mọi token type | ID Token/assertion có thể bị dùng làm access token | Validator riêng theo profile |
| Tin JWE decrypt là issuer authentication | Nội dung do bên khác tạo có thể được chấp nhận | Xác minh sender/profile bổ sung |
| Dùng một validator với issuer/key không phân biệt | Token từ issuer khác có thể bị gán nhầm trust | Ràng buộc issuer, key set và profile |

## 12. Xử lý lỗi xác minh an toàn

Token không hợp lệ phải dẫn đến từ chối xác thực. Không được tiếp tục bằng claims đã decode, fallback sang một khóa tùy ý hoặc chuyển sang một thuật toán yếu hơn.

Nên phân biệt lỗi nội bộ để quan sát:

- Malformed token hoặc vượt giới hạn kích thước.
- Thuật toán không được phép.
- Không tìm thấy khóa hoặc khóa không phù hợp.
- Chữ ký không hợp lệ.
- Issuer/audience/token type sai.
- Token hết hạn hoặc chưa có hiệu lực.
- Claims không đáp ứng schema/profile.
- Dependency như JWKS endpoint không khả dụng.

Ở phía client/API, phản hồi nên tuân theo giao thức đang sử dụng và không tiết lộ chi tiết nội bộ như public key selection, cấu hình issuer hoặc stack trace. Log có thể ghi mã lỗi và correlation ID nhưng không ghi raw JWT, secret hoặc toàn bộ claims nhạy cảm.

Khi JWKS endpoint hoặc validation dependency không khả dụng, không biến lỗi đó thành xác minh thành công. Dùng cache hợp lệ theo policy đã định hoặc từ chối; không fallback sang decode-only.

## 13. Kiểm tra dữ liệu đầu vào trước khi gọi thư viện

Thư viện JWT là một phần của parser-facing attack surface. Cần giới hạn đầu vào và chọn parser an toàn:

- Giới hạn tổng kích thước token và kích thước header/payload.
- Giới hạn số phần và chỉ chấp nhận serialization được profile hỗ trợ.
- Xử lý JSON sai định dạng và encoding không hợp lệ như lỗi.
- Có chính sách với duplicate JSON member names; tránh parser khác nhau diễn giải cùng token theo cách khác nhau.
- Xử lý crit đúng theo JOSE; từ chối critical header parameter không được hỗ trợ.
- Không tự động tải URL hoặc tham chiếu ngoài chỉ vì header có trường tương ứng.
- Không cho phép thuật toán, key type hoặc compression ngoài profile.
- Cập nhật thư viện để nhận bản vá bảo mật.

Đừng tự viết lại thuật toán chữ ký hoặc giải mã JWT nếu thư viện chuẩn đã cung cấp triển khai được duy trì. Phần ứng dụng nên tập trung cấu hình trust policy, token profile và xử lý lỗi.

## 14. Kiểm thử để chứng minh decode không bị dùng thay verify

Một bộ kiểm thử tốt cần có cả token hợp lệ và token cố tình sai:

| Kịch bản | Decode/parse có thể thành công? | Kết quả authenticate mong đợi |
| --- | --- | --- |
| Token đúng chữ ký, issuer, audience, thời gian và profile | Có | Chấp nhận |
| Payload bị sửa nhưng giữ chữ ký cũ | Có thể | Từ chối chữ ký |
| Token tự tạo với role=admin, không có chữ ký tin cậy | Có | Từ chối |
| alg=none trong profile yêu cầu chữ ký | Có | Từ chối |
| Thuật toán không nằm trong allowlist | Có | Từ chối |
| Chữ ký đúng bằng khóa không thuộc issuer được tin | Có | Từ chối |
| iss không khớp | Có | Từ chối |
| aud dành cho API khác | Có | Từ chối |
| exp đã qua hoặc nbf ở tương lai | Có | Từ chối |
| Token đúng chữ ký nhưng sai typ/profile | Có | Từ chối |
| ID Token được gửi đến API | Có | Từ chối |
| kid không tồn tại | Có | Từ chối sau refresh có giới hạn |
| JWKS endpoint không khả dụng và không có khóa cache hợp lệ | Có | Từ chối |
| JWE decrypt thành công nhưng thiếu sender authentication theo profile | Có | Không tự động chấp nhận |
| Claims thiếu trường bắt buộc hoặc sai kiểu | Có | Từ chối |

Ngoài unit test, cần có integration test với đúng cấu hình thư viện và key source production-like. Test nên xác nhận cả positive path lẫn negative path, đồng thời kiểm tra không có nhánh fallback nào biến verify failure thành authenticated principal.

## 15. Code review checklist

Khi review một tích hợp JWT library, hãy hỏi:

- Hàm nào thực sự xác minh chữ ký/MAC?
- Có đường code nào chỉ gọi decode rồi sử dụng claims không?
- Kết quả unverified và verified có kiểu dữ liệu/API riêng không?
- Allowlist thuật toán có được cấu hình tĩnh theo issuer/profile không?
- Khóa được lấy từ trust configuration/JWKS đáng tin cậy không?
- kid chỉ được dùng như lookup hint trong key set phù hợp không?
- Có kiểm tra issuer, audience, expiration, not-before và token type không?
- Required claims và schema có được xác minh không?
- Có phân biệt access token, ID Token, assertion và proof JWT không?
- Lỗi verify, key lookup hoặc dependency có fail-closed không?
- Token có bị ghi vào log, URL, exception hoặc tracing không?
- Có test token bị sửa payload, sai issuer, sai audience, hết hạn và sai thuật toán không?

Nếu không trả lời rõ được hàm thư viện đang làm gì, chưa nên dùng nó để tạo principal hoặc cấp quyền.

## 16. Tình huống tự kiểm tra

Một API dùng thư viện JWT. Developer gọi decode, lấy claim sub và roles, rồi tạo user context. Trong test, token có roles=[admin] và API trả về thành công. Sau khi triển khai, attacker tự tạo token với payload tương tự nhưng không có chữ ký hợp lệ.

**Câu hỏi 1:** Vì sao test có thể vẫn pass?

**Trả lời:** Test chỉ chứng minh parser đọc được payload và code sử dụng claims; nó không chứng minh chữ ký được xác minh. Nếu test fixture không kiểm tra chữ ký hoặc dùng một nhánh decode-only, token giả vẫn tạo được user context.

**Câu hỏi 2:** Chỉ đổi decode thành verify có đủ không?

**Trả lời:** Chưa chắc. Cần xác minh API verify của thư viện thực sự kiểm tra chữ ký bằng khóa tin cậy và thuật toán allowlist, sau đó kiểm tra issuer, audience, thời gian, token type và schema.

**Câu hỏi 3:** Nếu signature verification thành công nhưng aud là API khác thì sao?

**Trả lời:** Từ chối. Chữ ký hợp lệ không làm token dành cho API khác trở thành token hợp lệ tại API hiện tại.

**Câu hỏi 4:** Có thể decode token trước verify để chọn khóa theo kid không?

**Trả lời:** Có thể đọc header chưa xác minh như một gợi ý tra cứu trong key set đã gắn với issuer tin cậy. Không được tin kid như bằng chứng, tải khóa từ URL do token chỉ định hoặc dùng claims chưa xác minh để cấp quyền.

## 17. Ghi nhớ

Decode và parse có thể chỉ đọc cấu trúc token; chúng không mặc nhiên xác minh chữ ký. Verify signature chỉ chứng minh chữ ký phù hợp với thuật toán và khóa được sử dụng; nó chưa đủ để kết luận token dành cho API, còn hiệu lực, đúng loại và đáp ứng profile.

Hãy cấu hình allowlist thuật toán, lấy khóa từ nguồn tin cậy, kiểm tra issuer/audience/time/token type/schema và chỉ tạo principal từ kết quả đã xác minh đầy đủ. Không fallback sang decoded claims khi bất kỳ bước bảo vệ nào thất bại.

**Đừng hỏi “thư viện đã đọc được JWT chưa?”; hãy hỏi “thư viện đã xác minh token theo đúng trust policy và profile của consumer chưa?”.**

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): signing input và xác minh chữ ký.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): giải mã và bảo vệ nội dung JWE.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK và JWKS.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh thuật toán, issuer, audience và phân biệt token profile.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile access token JWT.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): public JWK và xác minh proof JWT theo ngữ cảnh.
