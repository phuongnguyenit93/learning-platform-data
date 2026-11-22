# Luồng xác minh từ dữ liệu đầu vào đến kết quả tin cậy

## 1. Mục tiêu của luồng xác minh JWT

Trong bảo mật JSON Web Token (JWT), **nhận được một chuỗi token** không đồng nghĩa với **nhận được một danh tính đáng tin cậy**. Header và payload của token có thể được đọc trước khi xác minh chữ ký; tại thời điểm đó, mọi giá trị như người dùng, đơn vị phát hành, quyền truy cập hay thời điểm hết hạn đều chỉ là dữ liệu do phía gửi cung cấp.

Luồng xác minh là chuỗi các quyết định chuyển một đầu vào chưa được tin cậy thành một kết quả có thể sử dụng trong hệ thống. Muốn chấp nhận JWT, bên nhận cần trả lời đồng thời những câu hỏi sau:

1. **Đúng loại dữ liệu không?** Token có đúng định dạng và loại token mà điểm tiếp nhận hỗ trợ không?
2. **Có bằng chứng mật mã hợp lệ không?** Chữ ký JWS có được xác minh bằng khóa đáng tin cậy và thuật toán được phép không? Nếu dùng JWE, quá trình giải mã có hợp lệ và có đủ bằng chứng về nguồn phát hành theo hợp đồng không?
3. **Các tuyên bố (claims) có phù hợp không?** Token do đúng issuer phát hành, dành cho đúng audience, còn hiệu lực và đáp ứng hợp đồng token không?
4. **Có phù hợp với yêu cầu hiện tại không?** Token có đúng mục đích sử dụng, đúng ngữ cảnh người gọi và đáp ứng chính sách truy cập hoặc trạng thái thu hồi khi cần không?

Ba kết quả cần phân biệt:

- **Không hợp lệ (invalid):** Có lỗi ở định dạng, chữ ký, khóa, thuật toán, claims hoặc hợp đồng xác minh; phải từ chối.
- **Hợp lệ về mặt token (validated):** Đã vượt qua tất cả kiểm tra JWT bắt buộc và có thể xây dựng ngữ cảnh danh tính/tuyên bố đáng tin cậy trong phạm vi chính sách đã chọn.
- **Được phép thực hiện hành động (authorized):** Ngoài token hợp lệ, yêu cầu còn vượt qua các kiểm tra quyền đối với tài nguyên, hành động và trạng thái hệ thống. **Token hợp lệ không tự động đồng nghĩa có quyền truy cập.**

Chương này tập trung vào quy trình xác minh JWT nói chung, độc lập với ngôn ngữ lập trình, framework hoặc thư viện cụ thể.

## 2. Xác lập hợp đồng tin cậy trước khi đọc token

Điểm khởi đầu đúng không phải là hỏi token tự khai báo dùng thuật toán nào hay được phát hành bởi ai. **Bên nhận phải có sẵn một chính sách xác minh (validation policy) từ cấu hình đáng tin cậy.** Chính sách này thường được chọn dựa trên dịch vụ, endpoint, loại yêu cầu hoặc hợp đồng tích hợp.

| Thành phần chính sách | Điều bên nhận cần quyết định trước |
| --- | --- |
| Loại token/serialization | Chấp nhận JWS Compact, JWE Compact hoặc một cấu hình JOSE cụ thể; có yêu cầu phân biệt access token và ID token không |
| Issuer | Danh sách issuer tin cậy, cách so khớp chính xác với claim **iss** |
| Audience | Định danh tài nguyên/dịch vụ phải xuất hiện trong claim **aud** |
| Thuật toán | Danh sách thuật toán chữ ký hoặc mã hóa được phép cho từng loại token, không chọn theo ý token |
| Nguồn khóa | Khóa tin cậy hoặc JWKS được gắn với issuer cụ thể; quy tắc chọn khóa theo **kid**, loại khóa và mục đích sử dụng |
| Claims | Claims bắt buộc, cách kiểm tra kiểu dữ liệu và quan hệ giữa các claims |
| Thời gian | Đồng hồ chuẩn, độ lệch được phép (clock skew), thời lượng sống tối đa và giới hạn tuổi token nếu có |
| Bối cảnh | Token dùng cho API nào, tenant nào, loại người gọi nào; các yêu cầu về scope, quyền, thu hồi và chống phát lại |

Ví dụ một chính sách **minh họa** dành cho JWT access token có chữ ký:

~~~yaml
representation: JWS Compact
tokenType: at+jwt
trustedIssuer: https://identity.example.org/
expectedAudience: https://api.example.org/invoices
allowedSignatureAlgorithms: [RS256]
trustedJwksSource: https://identity.example.org/keys
requiredClaims: [iss, sub, aud, exp, iat]
clockSkewSeconds: 60
maxTokenAgeSeconds: 900
~~~

Đây là mô tả hợp đồng, không phải cú pháp cấu hình chuẩn áp dụng cho mọi hệ thống. Một hệ thống khác có thể chọn thuật toán, claims, loại token hoặc thời lượng khác theo tiêu chuẩn và mô hình đe dọa của mình. Chẳng hạn, **typ: at+jwt** là chỉ dấu loại token được sử dụng trong profile JWT access token của OAuth 2.0; không phải mọi JWT đều bắt buộc có giá trị này.

Nếu hỗ trợ nhiều issuer, có thể dùng claim **iss** chưa xác minh **chỉ như gợi ý định tuyến** để chọn giữa các chính sách đã cấu hình sẵn, sau đó bắt buộc xác minh chữ ký và so khớp lại issuer. Không dùng **iss**, **jku**, **x5u** hay URL nằm trong token để tự động tạo nguồn tin cậy mới hoặc tải khóa từ địa chỉ tùy ý.

## 3. Bản đồ luồng từ đầu vào đến quyết định

~~~mermaid
flowchart TD
    A["Nhận chuỗi token chưa tin cậy"] --> B["Chọn chính sách xác minh từ ngữ cảnh đáng tin cậy"]
    B --> C{"Định dạng, kích thước và loại token phù hợp?"}
    C -- "Không" --> X["Từ chối: token không hợp lệ"]
    C -- "Có" --> D["Đọc cấu trúc JOSE có kiểm soát"]
    D --> E{"Thuật toán, header và khóa thuộc chính sách tin cậy?"}
    E -- "Không" --> X
    E -- "Có" --> F["Xác minh mật mã bằng thư viện được kiểm chứng"]
    F --> G{"Chữ ký hoặc bảo vệ mật mã hợp lệ?"}
    G -- "Không" --> X
    G -- "Có" --> H["Xác minh claims và ràng buộc thời gian"]
    H --> I{"Issuer, audience, loại token, hiệu lực đều đúng?"}
    I -- "Không" --> X
    I -- "Có" --> J["Kiểm tra ngữ cảnh, thu hồi và phát lại nếu áp dụng"]
    J --> K{"Token đáp ứng chính sách chấp nhận?"}
    K -- "Không" --> X
    K -- "Có" --> L["Tạo ngữ cảnh danh tính/claims đã xác minh"]
    L --> M["Đánh giá quyền cho hành động và tài nguyên"]
    M --> N{"Được phép truy cập?"}
    N -- "Không" --> Y["Từ chối truy cập"]
    N -- "Có" --> Z["Thực hiện yêu cầu"]
~~~

Sơ đồ mô tả nhánh phổ biến là **JWT được ký dưới dạng JWS**. Với **JWE** (JWT được mã hóa), phải dùng luồng giải mã và xác thực bảo vệ mã hóa phù hợp trước khi đọc nội dung bên trong; nếu nội dung là JWS lồng nhau, tiếp tục xác minh chữ ký của JWS đó. Quy trình và thứ tự xử lý cụ thể phải tuân theo hợp đồng JOSE, không áp dụng nguyên xi bộ kiểm tra JWS ba thành phần cho JWE năm thành phần.

## 4. Từng chặng của quá trình xác minh

### 4.1. Tiếp nhận đầu vào và xác định ranh giới tin cậy

Token có thể đến từ header **Authorization: Bearer**, cookie hoặc một cơ chế truyền được thỏa thuận trước. Bên nhận cần kiểm tra cơ chế truyền trước khi đụng đến nội dung JWT:

- Chỉ nhận token từ vị trí được phép theo hợp đồng; xử lý trường hợp thiếu, trùng lặp hoặc kết hợp nhiều nguồn token theo quy tắc rõ ràng.
- Áp dụng giới hạn kích thước và thời gian xử lý để tránh đầu vào rất lớn gây cạn tài nguyên.
- Bảo vệ kênh truyền, thông thường bằng TLS; tránh đưa bearer token vào URL vì dễ lọt vào lịch sử, log hoặc hệ thống phân tích.
- Không ghi nguyên token, chữ ký, khóa hoặc claims nhạy cảm vào log. Nếu cần truy vết, ghi mã nguyên nhân lỗi, ID yêu cầu hoặc dấu định danh đã được xử lý an toàn.

Tại chặng này, token vẫn hoàn toàn **chưa đáng tin cậy**, kể cả khi có thể giải mã Base64URL và hiển thị payload dễ đọc.

### 4.2. Kiểm tra hình thức và parse JOSE một cách nghiêm ngặt

Một **JWS Compact** thông thường có ba thành phần, ngăn bởi dấu chấm:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Một **JWE Compact** có năm thành phần. Việc đếm thành phần chỉ là kiểm tra cấu trúc sơ bộ; không chứng minh token hợp lệ. Đối với profile JWT Compact thông thường, bộ phân tích nên:

- Kiểm tra số thành phần, giới hạn độ dài, ký tự Base64URL, khả năng giải mã và cấu trúc JSON của header/payload khi được phép đọc.
- Từ chối cấu trúc mơ hồ như tên thuộc tính JSON trùng lặp, kiểu dữ liệu sai hoặc các phần mở rộng JOSE không được hỗ trợ.
- Hiểu và thực thi những tham số header quan trọng như **alg**, **kid**, **typ**, **crit** theo profile đã chọn; từ chối **crit** mà bên nhận không hiểu.
- Không giả định mọi biến thể JWS đều có payload được mã hóa Base64URL theo cách mặc định: các mở rộng như **b64=false** cần được hỗ trợ rõ ràng hoặc bị từ chối theo hợp đồng.

Header có thể nói **alg: RS256** hay **kid: key-7**, nhưng tại thời điểm này đó vẫn là dữ liệu chưa xác minh. Parse thành công không phải là xác minh chữ ký.

### 4.3. Ràng buộc thuật toán với nguồn khóa tin cậy

Sau khi đọc header để xác định cách xử lý, bên nhận phải so sánh nó với chính sách đã có:

1. Thuật toán trong **alg** phải nằm trong allowlist áp dụng cho endpoint và issuer. Mặc định không chấp nhận **alg: none** đối với luồng yêu cầu JWT có chữ ký.
2. Khóa xác minh phải đến từ cấu hình tin cậy, kho khóa hoặc **JWKS** đã được gắn trước với issuer. **kid** chỉ là định danh tra cứu *trong tập khóa đó*, không phải đường dẫn tệp hay địa chỉ tải khóa.
3. Thuật toán, loại khóa và công dụng khóa phải tương thích: ví dụ không lấy khóa công khai RSA làm bí mật HMAC chỉ vì token yêu cầu **HS256**.
4. Nếu không tìm được khóa phù hợp, có nhiều khóa mơ hồ, hoặc khóa không được phép dùng để xác minh chữ ký, phải từ chối. Có thể làm mới JWKS khi luân chuyển khóa theo cơ chế có giới hạn tần suất và chính sách cache an toàn.

Với khóa bất đối xứng, bên phát hành ký bằng khóa riêng, bên nhận xác minh bằng khóa công khai được tin cậy. Với HMAC, bên ký và bên xác minh dùng chung bí mật; vì vậy việc phân phối và giới hạn người có quyền dùng bí mật quan trọng không kém bản thân thuật toán.

Không tự động tin vào khóa được nhúng trong header (ví dụ **jwk**) hoặc tự đi theo URL **jku/x5u** do token chỉ định. Nếu một giao thức thực sự sử dụng những trường đó, phải có cơ chế ràng buộc và allowlist riêng để ngăn đánh tráo nguồn khóa hoặc truy cập mạng ngoài ý muốn.

### 4.4. Xác minh bằng chứng mật mã

Với JWS thông thường, bên nhận xác minh chữ ký trên **chính xác chuỗi dữ liệu đã được ký** theo chuẩn JWS, không xây dựng lại JSON rồi ký/so sánh trên phiên bản đã định dạng lại. Việc này nên giao cho thư viện JOSE/JWT đã được đánh giá và cập nhật.

Chữ ký hợp lệ chỉ chứng minh dữ liệu không bị thay đổi so với nội dung được ký bằng khóa xác minh tương ứng. Nó **chưa đủ** để kết luận JWT được phép dùng ở dịch vụ hiện tại: token ký bằng khóa hợp lệ nhưng sai issuer, audience, thời gian hoặc mục đích vẫn phải bị từ chối.

Với JWE, bên nhận kiểm tra cơ chế bảo vệ mã hóa và giải mã bằng khóa/thuật toán được phép. Khả năng giải mã thành công hoặc thẻ xác thực mã hóa hợp lệ **không tự động chứng minh danh tính của issuer** trong mọi mô hình: bên nhận còn phải xem ai có thể tạo ra ciphertext hợp lệ và hợp đồng có yêu cầu chữ ký bên trong hay không. Nếu sử dụng nested JWT, xác minh lớp bên trong đúng thứ tự theo cấu trúc đã thỏa thuận.

### 4.5. Kiểm tra claims đã được bảo vệ

Chỉ sau khi xác minh bảo vệ mật mã thành công mới được dùng các claims làm cơ sở tin cậy. Các quy tắc điển hình:

| Claim/thuộc tính | Câu hỏi xác minh | Lỗi thường gặp |
| --- | --- | --- |
| **iss** | Có khớp chính xác issuer đã tin cậy không? | Chấp nhận một token chỉ vì issuer có tiền tố URL tương tự |
| **aud** | Có chứa đúng định danh của dịch vụ nhận token không? | Nhận token được cấp cho API khác; không xử lý dạng chuỗi hoặc mảng đúng quy cách |
| **exp** | Token còn thời hạn không? | Chỉ kiểm tra chữ ký mà bỏ qua hết hạn |
| **nbf** | Đã tới thời điểm token được phép sử dụng chưa? | Chấp nhận token chưa có hiệu lực |
| **iat** | Thời điểm phát hành hợp lý và có đáp ứng giới hạn tuổi token không? | Coi iat tự thân là bằng chứng token còn hiệu lực |
| **sub** | Chủ thể có định dạng và ý nghĩa đúng với hợp đồng không? | Mặc định sub là người dùng cuối trong mọi loại token |
| **typ**/loại token | Token có đúng loại dành cho endpoint không? | Đưa ID token vào API chỉ chấp nhận access token |
| **jti**, **nonce**, scope, tenant... | Những ràng buộc bổ sung có phù hợp profile và yêu cầu không? | Áp một claim tùy chọn như tiêu chuẩn bắt buộc toàn cục |

**exp**, **nbf** và **iat** sử dụng giá trị **NumericDate** (số giây kể từ mốc Unix theo định nghĩa RFC 7519), không mặc định là mili giây. Không phải mọi claim trong bảng đều bắt buộc theo bản thân chuẩn JWT: **hợp đồng ứng dụng/profile** quyết định claim nào phải có. Khi đã quy định là bắt buộc, claim thiếu, sai kiểu hoặc không hợp lệ phải làm token bị từ chối.

Giả sử thời điểm hiện tại là **now** và hệ thống cho phép sai số đồng hồ **leeway**:

- Không có sai số đồng hồ: từ chối khi **now ≥ exp** hoặc **now < nbf**.
- Có leeway: chỉ nới lỏng ranh giới thời gian trong phạm vi hữu hạn đã cấu hình; không biến token hết hạn lâu thành token hợp lệ.
- Nếu kiểm tra **iat**, từ chối thời điểm phát hành nằm quá xa trong tương lai; nếu có chính sách tuổi tối đa, kiểm tra **now − iat** với giới hạn ấy, ngay cả khi **exp** còn xa.
- Có thể kiểm tra thêm **exp > iat**, thời lượng sống tối đa, thứ tự **nbf/exp** và các ràng buộc đặc thù của loại token.

Leeway nên nhỏ, đồng nhất và được giám sát. Đồng hồ hệ thống cần đồng bộ; không dùng clock skew lớn để che lỗi lệch giờ nghiêm trọng.

### 4.6. Ràng buộc token với mục đích và ngữ cảnh yêu cầu

Một token có chữ ký chính xác, đúng issuer và chưa hết hạn vẫn có thể không phù hợp với yêu cầu hiện tại.

Ví dụ: issuer cấp một JWT có **aud = https://api.example.org/profile**. Token đó không được dùng để gọi **https://api.example.org/invoices**, dù hai API cùng tin issuer và cùng dùng một JWKS. Tương tự, ID token được cấp để client xác nhận quá trình đăng nhập không đương nhiên là access token dành cho API.

Để tránh **nhầm lẫn giữa các loại JWT (cross-JWT confusion)**, có thể kết hợp nhiều ranh giới độc lập: audience riêng, loại token/profile riêng, claims hoặc chính sách riêng, và khi phù hợp cả khóa ký riêng. Nếu hệ thống đa tenant, phải ràng buộc tenant được tin cậy với tài nguyên đang truy cập; không mặc định tenant trong token cho phép đọc mọi tài nguyên thuộc tenant ấy.

Các yêu cầu thu hồi token, khóa tài khoản, vô hiệu phiên hoặc chống replay cũng nằm ở chặng này nếu mô hình bảo mật đòi hỏi. Chữ ký và **exp** không tự cung cấp khả năng thu hồi tức thời. Một **jti** duy nhất chỉ có ích cho chống phát lại nếu có cơ chế lưu/kiểm tra trạng thái sử dụng, thời hạn và xử lý đồng thời phù hợp.

Sau khi hoàn thành việc chấp nhận token, hệ thống mới đánh giá **quyền truy cập** theo tài nguyên, hành động, scope/role và dữ liệu nghiệp vụ hiện hành. Điều này giúp phân biệt rõ token không hợp lệ với token hợp lệ nhưng thiếu quyền.

### 4.7. Tạo kết quả đáng tin cậy hoặc từ chối an toàn

Khi thành công, lớp xác minh nên trả về một cấu trúc có ý nghĩa rõ ràng, chẳng hạn:

~~~text
ValidatedTokenContext {
  issuer:          issuer đã khớp chính sách
  subject:         chủ thể đã được xác minh theo hợp đồng
  audience:        các tài nguyên mà token được cấp cho
  tokenType:       loại token đã kiểm tra
  issuedAt:        thời điểm phát hành đã kiểm tra
  expiresAt:       thời điểm hết hạn đã kiểm tra
  claims:          claims đã vượt qua xác minh mật mã
  policyId:        chính sách xác minh đã được áp dụng
}
~~~

Các phần khác của ứng dụng nên nhận **kết quả đã xác minh**, tránh tự ý dùng một đối tượng payload thô được parse trước chữ ký. Nếu thất bại ở bất kỳ kiểm tra bắt buộc nào, luồng phải **fail closed**: không tạo danh tính mặc định, không bỏ qua lỗi JWKS và không tiếp tục bằng claims chưa xác minh.

Với API dùng bearer token, phản hồi thực tế thường phân biệt **401 Unauthorized** khi thông tin xác thực không có hoặc không hợp lệ, và **403 Forbidden** khi danh tính/token đã được chấp nhận nhưng không đủ quyền. Chi tiết mã lỗi phải phù hợp giao thức API; phản hồi công khai không nên tiết lộ khóa, nội dung token hoặc nội tình kiểm tra mật mã. Log nội bộ có thể lưu mã lỗi an toàn phục vụ điều tra.

## 5. Mã giả cho nhánh JWT có chữ ký

Mã giả sau mô tả thứ tự ra quyết định. Các thao tác parse và xác minh JWS phải được hiện thực bằng thư viện chuẩn, không tự viết thuật toán mật mã.

~~~text
function validateSignedAccessToken(rawToken, requestContext, now):
    policy = trustedPolicyFor(requestContext.endpoint)
    require policy expects signed JWT access tokens

    require rawToken comes from an allowed transport location
    require length(rawToken) <= policy.maxTokenLength
    jws = strictParseJwsCompact(rawToken)

    require jws.protectedHeader.alg in policy.allowedAlgorithms
    require jws.protectedHeader.typ matches policy.requiredTokenType
    require all critical JOSE headers are understood and allowed

    key = policy.trustedKeys.lookup(
        kid = jws.protectedHeader.kid,
        algorithm = jws.protectedHeader.alg
    )
    require key exists and is allowed for signature verification
    require verifyJwsSignature(jws, key) == true

    claims = parseVerifiedClaims(jws.payload)
    require all policy.requiredClaims are present and well-typed
    require claims.iss exactly equals policy.trustedIssuer
    require claims.aud contains policy.expectedAudience
    require tokenTimeChecksPass(claims, now, policy.clockSkew)
    require tokenAgeAndLifetimeChecksPass(claims, now, policy)
    require tokenPurposeAndContextChecksPass(claims, requestContext, policy)
    require revocationAndReplayChecksPassIfRequired(claims, policy)

    return ValidatedTokenContext(claims, policy.id)

function handleRequest(request):
    tokenContext = validateSignedAccessToken(
        extractToken(request), request.context, trustedClock.now()
    )
    require authorizationPolicy.allows(tokenContext, request.action, request.resource)
    return processRequest(request, tokenContext)
~~~

Hàm **parseVerifiedClaims** biểu thị việc đọc payload **sau khi** đã xác minh chữ ký. Nếu thư viện trả về claims ngay khi parse, bên gọi vẫn phải xem chúng là chưa tin cậy cho tới khi mọi bước xác minh thành công. Hàm **tokenTimeChecksPass** phải kiểm tra chính xác các điều kiện thời gian, không chỉ kiểm tra claim có tồn tại.

## 6. Ví dụ: một JWT được chấp nhận ở đâu?

Giả sử dịch vụ hóa đơn chỉ nhận JWT access token do **https://identity.example.org/** phát hành, có audience **https://api.example.org/invoices**, thuật toán **RS256**, thời hạn tối đa 15 phút và scope **invoice:read** cho thao tác đọc hóa đơn.

| Đầu vào/tình huống | Kết quả mong đợi | Lý do |
| --- | --- | --- |
| JWS hợp lệ, đúng issuer, audience, thời gian, loại token và scope | Chấp nhận token, sau đó kiểm tra quyền trên hóa đơn cụ thể | Các ranh giới chấp nhận đã được đáp ứng |
| Chữ ký hợp lệ nhưng **aud** là API hồ sơ | Từ chối token | Token được cấp cho đối tượng nhận khác |
| **alg: none** hoặc **HS256** trong khi chính sách chỉ cho **RS256** | Từ chối token | Không được hạ hoặc tự chuyển thuật toán |
| **kid** tham chiếu khóa ngoài kho tin cậy | Từ chối token | Không có khóa xác minh đáng tin cậy |
| Payload sửa **scope** sau khi phát hành | Từ chối token | Chữ ký không còn khớp |
| Chữ ký hợp lệ nhưng **exp** đã hết hạn ngoài leeway | Từ chối token | Không còn hiệu lực thời gian |
| ID token được gửi đến endpoint chỉ nhận access token | Từ chối token | Sai mục đích/loại token |
| Token hợp lệ, có scope đọc nhưng gọi thao tác xóa hóa đơn | Từ chối hành động | Không đáp ứng chính sách quyền của thao tác |
| Token hợp lệ nhưng **jti** đã sử dụng trong luồng chỉ cho phép dùng một lần | Từ chối theo chính sách chống replay | Tính hợp lệ mật mã không loại trừ phát lại |

Trường hợp cuối cùng cũng cho thấy **phạm vi kết luận** rất quan trọng: hệ thống có thể xác minh token thành công ở tầng mật mã nhưng vẫn chặn yêu cầu ở tầng ngữ cảnh hoặc quyền.

## 7. Những lỗi thiết kế phổ biến cần tránh

**Giải mã rồi tin ngay.** Nhiều công cụ có thể đọc payload JWT mà không cần khóa. Dùng kết quả giải mã để tạo session, chọn quyền hay quyết định tenant trước khi xác minh là mở cửa cho giả mạo claims.

**Để token quyết định thuật toán hoặc nguồn khóa.** Tin hoàn toàn vào **alg**, **kid**, **jku** hoặc khóa nhúng trong token có thể dẫn đến nhầm lẫn thuật toán, đánh tráo khóa và yêu cầu mạng ngoài ý muốn. Mọi lựa chọn phải nằm trong chính sách được phép từ trước.

**Kiểm tra chữ ký nhưng bỏ qua audience.** Chữ ký của issuer là điều kiện cần, nhưng một issuer có thể phát hành token cho nhiều client và API. Nếu bỏ qua **aud** hoặc loại token, dịch vụ dễ chấp nhận token dành cho bên khác.

**Bỏ qua profile và kiểu dữ liệu claims.** Không nên so sánh một mảng audience như một chuỗi tùy tiện, diễn giải NumericDate là mili giây, hoặc dùng logic chuyển kiểu lỏng lẻo. Những sai khác parser có thể tạo ra kết quả xác minh không nhất quán giữa các dịch vụ.

**Nhầm token hợp lệ với quyền truy cập.** Scope, role hoặc nhóm ghi trong token có thể chưa đủ để truy cập một đối tượng nghiệp vụ cụ thể; quyền sở hữu, tenant, trạng thái tài khoản và quyết định cấp quyền hiện hành có thể phải được kiểm tra riêng.

**Bỏ qua vòng đời khóa và token.** Khi đổi khóa ký, JWKS cache cần cơ chế cập nhật an toàn; khi cần chặn token trước hạn, phải có chiến lược thu hồi/phiên. Việc chỉ kiểm tra chữ ký và **exp** không giải quyết hết hai bài toán này.

## 8. Danh sách kiểm thử tối thiểu cho một bộ xác minh

| Nhóm kiểm thử | Các trường hợp đáng kiểm tra |
| --- | --- |
| Đầu vào | Thiếu token, token trùng nguồn, token quá dài, sai số thành phần, Base64URL/JSON không hợp lệ, thuộc tính JSON trùng |
| JOSE và khóa | **alg: none**, thuật toán không cho phép, **kid** không tồn tại, khóa sai loại/sai issuer, **crit** không hỗ trợ, luân chuyển khóa |
| Mật mã | Chữ ký sai, payload/header bị sửa, chữ ký ký bởi khóa không tin cậy, dữ liệu JWE bị thay đổi |
| Claims và thời gian | Thiếu/sai kiểu claim bắt buộc, **iss** sai, **aud** sai, **exp** ở sát ranh giới, **nbf** ở tương lai, **iat** bất thường, vượt tuổi tối đa |
| Ngữ cảnh | Dùng nhầm ID token/access token, sai tenant, sai scope, tài nguyên không được phép, token bị thu hồi, **jti** bị phát lại nếu áp dụng |
| Vận hành | JWKS không sẵn sàng, cache hết hạn, hạn chế refresh khi **kid** lạ, sai lệch đồng hồ, phản hồi lỗi và log không lộ token |

Các ca ở ranh giới **exp**, **nbf** cần được kiểm thử với đồng hồ cố định và nhiều mức leeway để tránh lỗi so sánh lớn hơn/nhỏ hơn. Đối với hệ thống nhiều dịch vụ, nên kiểm tra tính nhất quán của hợp đồng xác minh giữa các thành phần, đặc biệt với issuer, audience, thuật toán, loại token và đồng bộ giờ.

## 9. Nguyên tắc ghi nhớ và tài liệu chuẩn

Một JWT chỉ nên trở thành dữ liệu tin cậy sau khi **chính sách xác minh đã được chọn từ nguồn tin cậy**, **bằng chứng mật mã đã được kiểm tra**, **claims phù hợp với bên nhận và thời điểm sử dụng**, rồi **các ràng buộc ngữ cảnh cần thiết đều đạt**. Xác minh token cung cấp một ngữ cảnh có căn cứ để đánh giá quyền; chính sách ủy quyền vẫn phải đưa ra quyết định cuối cho hành động cụ thể.

Các tài liệu tiêu chuẩn liên quan để tra cứu chuyên sâu:

- **RFC 7519 — JSON Web Token (JWT):** định nghĩa JWT và các registered claim names như iss, sub, aud, exp, nbf, iat, jti.
- **RFC 7515 — JSON Web Signature (JWS)** và **RFC 7517 — JSON Web Key (JWK):** biểu diễn chữ ký, header và biểu diễn khóa.
- **RFC 7516 — JSON Web Encryption (JWE):** cách biểu diễn token mã hóa và xử lý nội dung được bảo vệ.
- **RFC 8725 — JSON Web Token Best Current Practices:** lựa chọn thuật toán, bảo vệ nguồn khóa, xác thực audience/issuer và phòng nhầm lẫn giữa các loại JWT.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** hợp đồng riêng khi JWT được sử dụng làm OAuth 2.0 access token.
