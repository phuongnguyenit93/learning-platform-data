# Đọc header chưa tin cậy chỉ để áp dụng quy tắc chọn khóa có kiểm soát

## 1. Header JWT giúp chọn cách xác minh, không tạo ra niềm tin

Trong một JWT, JOSE header mô tả cách token được bảo vệ và có thể chứa thông tin giúp bên nhận tìm đúng khóa. Ví dụ, một JWS có thể mang các trường **alg: RS256** và **kid: signing-key-2026-01**. Bộ xác minh cần đọc các giá trị đó để biết token đang tự khai báo thuật toán nào và chỉ ra khóa nào trong tập khóa đã biết.

Tuy nhiên, header nằm trong chính token do bên gửi cung cấp. Kẻ tấn công có thể tự tạo một chuỗi JWT với bất kỳ header nào, kể cả tên thuật toán, mã khóa, URL, chứng chỉ hay loại token. Vì vậy, trước khi chữ ký hoặc cơ chế bảo vệ mã hóa được xác minh, header là **dữ liệu chưa tin cậy**.

Nguyên tắc quan trọng của bài này:

> **Chỉ đọc header để đối chiếu với chính sách và chọn một ứng viên khóa trong vùng tin cậy đã cấu hình trước. Không để header tạo chính sách, tạo nguồn tin cậy, mở rộng quyền truy cập hoặc quyết định danh tính.**

Điều này tạo ra ranh giới giữa hai việc khác nhau:

- **Chọn ứng viên xác minh:** dùng một số trường header đã parse nghiêm ngặt, như alg và kid, để tìm khóa phù hợp trong tập khóa được tin cậy từ trước.
- **Xác minh token:** dùng khóa được chọn để kiểm tra chữ ký JWS hoặc thực hiện thao tác mật mã JWE, sau đó kiểm tra issuer, audience, thời gian, loại token và các điều kiện khác.

Việc tìm được khóa theo kid không chứng minh token do chủ sở hữu khóa tạo ra. Việc header khai báo alg hợp lệ cũng không chứng minh chữ ký đúng. Chỉ khi phép xác minh mật mã thành công và toàn bộ hợp đồng token được kiểm tra, claims mới được sử dụng làm dữ liệu tin cậy.

Nội dung áp dụng cho bảo mật JWT/JOSE nói chung, độc lập với ngôn ngữ lập trình, framework hoặc thư viện xác thực.

## 2. Vị trí của header trong luồng xác minh

Với JWT được ký dưới dạng JWS Compact, ba phần thường có dạng:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Protected header được mã hóa Base64URL để truyền trong chuỗi Compact. Việc giải mã nó chỉ giúp đọc JSON; chữ ký chưa được xác minh nên mọi trường vẫn có thể do người gửi tùy ý tạo ra.

Luồng xử lý ở mức khái quát:

~~~mermaid
flowchart TD
    A["Nhận JWT chưa tin cậy"] --> B["Chọn chính sách theo endpoint và ngữ cảnh tin cậy"]
    B --> C["Kiểm tra giới hạn và parse protected header"]
    C --> D{"Header đúng cú pháp và đúng kiểu?"}
    D -- "Không" --> X["Từ chối"]
    D -- "Có" --> E["Đối chiếu alg với allowlist của chính sách"]
    E --> F{"Thuật toán được phép?"}
    F -- "Không" --> X
    F -- "Có" --> G["Dùng kid/metadata làm gợi ý chọn khóa trong kho tin cậy"]
    G --> H{"Có đúng một ứng viên khóa hợp lệ?"}
    H -- "Không" --> X
    H -- "Có" --> I["Xác minh chữ ký hoặc xử lý mật mã theo profile"]
    I --> J{"Bằng chứng mật mã hợp lệ?"}
    J -- "Không" --> X
    J -- "Có" --> K["Xác minh issuer, audience, thời gian, loại token và claims"]
    K --> L{"Toàn bộ chính sách đạt?"}
    L -- "Không" --> X
    L -- "Có" --> M["Tạo ngữ cảnh token đã xác minh"]
~~~

**Chính sách phải có trước bước đọc header.** Ví dụ, endpoint hóa đơn đã được cấu hình chỉ chấp nhận access token do một issuer cụ thể phát hành, dùng RS256 và khóa ký lấy từ JWKS được ghim với issuer đó. Header chỉ giúp xác định token có phù hợp với chính sách và khóa nào trong JWKS cần được thử.

Không được làm ngược lại bằng cách đọc header rồi mới quyết định tin issuer nào, cho phép thuật toán nào hoặc lấy khóa ở đâu.

## 3. Xác lập chính sách tin cậy trước khi parse

Trước khi nhận token, bên xác minh cần có một cấu hình tin cậy. Một chính sách có thể gồm:

| Thành phần | Quy tắc cần xác lập trước |
| --- | --- |
| Điểm tiếp nhận | Endpoint hoặc loại yêu cầu được phép nhận loại JWT nào |
| Issuer | Issuer chính xác được tin cậy và cách gắn issuer với kho khóa |
| Thuật toán | Allowlist thuật toán cho từng profile; phân biệt thuật toán chữ ký và thuật toán mã hóa |
| Nguồn khóa | JWKS hoặc kho khóa được cấu hình/gắn với issuer; nguồn bí mật đối xứng nếu dùng HMAC |
| Điều kiện khóa | Loại khóa, mục đích sử dụng, kích thước, đường cong hoặc thuật toán khóa được chấp nhận |
| Header | Các trường bắt buộc, tùy chọn, bị cấm và các giá trị typ/crit được hỗ trợ |
| Tra cứu | Cách xử lý kid thiếu, không tìm thấy hoặc trùng; giới hạn số ứng viên |
| Làm mới khóa | Cache, thời hạn, làm mới khi có khóa mới và giới hạn tần suất refresh |
| Claims | Audience, thời gian, loại token và các claims bắt buộc |

Ví dụ chính sách minh họa cho một API chỉ nhận JWS access token:

~~~yaml
trustedTokenProfile:
  issuer: https://identity.example.org/
  expectedAudience: https://api.example.org/invoices
  tokenType: at+jwt
  serialization: JWS-Compact
  allowedAlgorithms:
    - RS256
  trustedKeySet:
    source: configured-issuer-jwks
    issuerBinding: https://identity.example.org/
    refreshOnUnknownKid: true
    minimumRefreshIntervalSeconds: 60
  keySelection:
    requireCompatibleKeyType: true
    requireSignatureUseWhenPresent: true
    requireVerifyOperationWhenPresent: true
    rejectAmbiguousCandidates: true
    maxCandidates: 2
~~~

Đây là cấu hình minh họa, không phải cú pháp chuẩn của JWT hay JOSE. Tên trường và giới hạn phải được điều chỉnh theo hệ thống. Điểm bắt buộc là danh sách thuật toán, issuer và nguồn khóa đều xuất phát từ cấu hình tin cậy.

Nếu một dịch vụ phục vụ nhiều issuer, cần ánh xạ từng issuer được cho phép tới một chính sách và một kho khóa tương ứng. Có thể dùng một giá trị issuer chưa xác minh như **gợi ý định tuyến** vào một bảng ánh xạ tĩnh đã cấu hình, nhưng sau khi xác minh chữ ký phải kiểm tra lại claim iss chính xác. Không dùng giá trị từ token để tự khám phá issuer mới, dựng URL tùy ý hoặc tải metadata không giới hạn.

## 4. Parse protected header với giới hạn nghiêm ngặt

Trước khi sử dụng bất kỳ trường header nào, phải kiểm soát đầu vào:

1. Kiểm tra token đúng loại serialization mà endpoint cho phép, đúng số thành phần và không vượt giới hạn kích thước.
2. Giải mã thành phần protected header bằng Base64URL decoder nghiêm ngặt.
3. Kiểm tra byte UTF-8 và parse thành JSON object.
4. Từ chối tên thuộc tính trùng nhau để tránh hai parser hiểu header khác nhau.
5. Giới hạn độ sâu, số thuộc tính, độ dài chuỗi và tổng kích thước header.
6. Kiểm tra kiểu dữ liệu của từng trường theo đặc tả JOSE.
7. Chỉ sau đó mới đối chiếu giá trị header với chính sách tin cậy.

Header JSON phải là object. Ví dụ sau cần bị từ chối vì có hai thuộc tính alg:

~~~json
{
  "alg": "RS256",
  "kid": "key-a",
  "alg": "none"
}
~~~

Một parser có thể lấy giá trị đầu, parser khác lấy giá trị cuối. Nếu các thành phần khác nhau trong hệ thống diễn giải khác nhau, kẻ tấn công có thể khai thác sự không nhất quán. Từ chối tên trường trùng là lựa chọn rõ ràng và an toàn.

Không tự động bỏ ký tự lạ, chuẩn hóa header hoặc thử parse lại bằng nhiều chế độ dễ dãi. Nếu cú pháp không đúng profile đã chọn, từ chối token.

## 5. Các trường header và giới hạn sử dụng

Không phải mọi trường JOSE header đều có thể dùng để chọn khóa. Cần phân biệt giá trị có ích để đối chiếu với giá trị có thể tạo ra hành vi nguy hiểm nếu tin theo.

| Trường | Ý nghĩa | Cách dùng an toàn trước xác minh |
| --- | --- | --- |
| **alg** | Thuật toán bảo vệ của JWS; trong JWE là thuật toán quản lý khóa | Bắt buộc đối chiếu chính xác với allowlist đã cấu hình; không tự mở rộng thuật toán |
| **kid** | Định danh khóa do bên phát hành đặt | Dùng như gợi ý tra cứu trong tập khóa tin cậy đã gắn với issuer; không phải URL hay bằng chứng sở hữu khóa |
| **typ** | Loại nội dung/token | Có thể dùng để từ chối loại token không phù hợp; không chứng minh danh tính hoặc chữ ký |
| **cty** | Loại nội dung bên trong, thường hữu ích với nested JWT | Chỉ dùng để chọn cách xử lý đã được cho phép; giới hạn số lớp và xác minh từng lớp |
| **crit** | Danh sách tham số header mở rộng mang tính bắt buộc | Phải hiểu và thực thi tất cả phần mở rộng được liệt kê; nếu có phần tử không hỗ trợ thì từ chối |
| **jku** | URL của JWK Set | Không tự động tải URL do token cung cấp; có thể gây SSRF hoặc thay đổi nguồn tin cậy |
| **jwk** | Một JWK được nhúng trong header | Không coi khóa nhúng là đáng tin cậy chỉ vì nó nằm trong token |
| **x5u** | URL chứng chỉ X.509 | Không tự động truy cập URL; nếu profile cần dùng phải có nguồn và chính sách chứng chỉ riêng |
| **x5c** | Chuỗi chứng chỉ X.509 | Không tin chỉ vì chứng chỉ được nhúng; phải xác minh chuỗi và chính sách neo tin cậy đã cấu hình |
| **x5t / x5t#S256** | Dấu vân tay chứng chỉ | Có thể dùng để đối chiếu chứng chỉ đã tin cậy; không thay thế xác minh chữ ký hoặc chuỗi tin cậy |
| **zip** | Phương pháp nén trong một số JWE | Chỉ xử lý nếu profile cho phép; cần giới hạn đầu ra giải nén |

### 5.1. alg là lời khai cần đối chiếu

Trường **alg** cho biết token tự khai đang sử dụng thuật toán nào. Bộ xác minh cần giá trị này để chọn phép kiểm tra tương ứng, nhưng không được xem nó như một chỉ thị có quyền thay đổi chính sách.

Ví dụ, endpoint chỉ cho phép RS256:

- **alg: RS256:** tiếp tục nếu khóa ứng viên và các điều kiện khác cũng phù hợp.
- **alg: HS256:** từ chối vì không nằm trong allowlist, kể cả khi có một giá trị khóa nào đó có thể diễn giải thành bí mật HMAC.
- **alg: none:** từ chối trong profile yêu cầu chữ ký.
- **alg** thiếu, sai kiểu hoặc không hỗ trợ: từ chối.

Không được thử nhiều thuật toán cho đến khi một phép xác minh thành công. Không tự hạ cấp sang thuật toán yếu hơn khi khóa không khớp. Việc chọn thuật toán phải gắn với endpoint, issuer và profile, không phụ thuộc ý muốn của người gửi token.

### 5.2. kid chỉ là định danh trong phạm vi kho khóa

**kid** giúp phân biệt các khóa trong một JWK Set hoặc kho khóa. Nó thường hữu ích khi issuer luân chuyển khóa, nhưng không có ý nghĩa toàn cục và không nhất thiết duy nhất giữa các issuer hoặc các kho khóa.

Do đó:

- Tra cứu kid trong đúng kho khóa đã gắn với issuer của chính sách hiện tại.
- Không dùng kid làm tên file, tên bảng tùy ý, URL, đường dẫn mạng hoặc câu truy vấn không được ràng buộc.
- Không tự chuyển chữ hoa/thường, chuẩn hóa Unicode hoặc thay đổi giá trị kid trước khi so khớp, trừ khi hợp đồng khóa định nghĩa rõ.
- Nếu kid không tồn tại, chỉ thực hiện quy trình refresh có kiểm soát; sau đó vẫn phải tra trong nguồn tin cậy.
- Nếu nhiều khóa cùng kid và cùng phù hợp, từ chối do mơ hồ hoặc áp dụng quy tắc phân giải đã được định nghĩa rõ trong chính sách. Không tùy tiện lấy khóa đầu tiên.

kid không phải bí mật, không phải chữ ký và không chứng minh người gửi sở hữu khóa tương ứng.

### 5.3. typ và cty chỉ hỗ trợ phân loại

Trường **typ** có thể giúp phân biệt loại token, ví dụ profile JWT access token có thể dùng giá trị **at+jwt**. Tuy nhiên, người tấn công cũng có thể tự đặt typ thành giá trị mong muốn. Vì thế, typ chỉ là điều kiện phân loại bổ sung; token vẫn phải vượt qua xác minh mật mã và claims.

Trường **cty** có thể cho biết payload chứa một JWT khác trong mô hình nested JWT. Nếu hỗ trợ nested token, phải xác định trước loại lớp ngoài/lớp trong, thứ tự xử lý và giới hạn số lớp. Không để cty tùy ý kích hoạt một parser hoặc giao thức bất kỳ.

## 6. Chọn thuật toán và khóa theo các ràng buộc đồng thời

Một khóa chỉ là ứng viên phù hợp khi đồng thời thỏa mãn chính sách thuật toán và thuộc tính khóa. Không nên chỉ so kid rồi đưa bất kỳ khóa nào vào thư viện xác minh.

### 6.1. Ràng buộc thuật toán với loại khóa

| Nhóm thuật toán | Loại khóa phù hợp | Điểm cần kiểm tra |
| --- | --- | --- |
| RS256, RS384, RS512 | RSA | Khóa công khai RSA, kích thước khóa tối thiểu theo chính sách, thuật toán JWK nếu có |
| PS256, PS384, PS512 | RSA | Tham số PSS theo chuẩn, kích thước khóa và allowlist riêng |
| ES256, ES384, ES512 | EC | Đường cong tương ứng, tọa độ hợp lệ và thuật toán được phép |
| EdDSA | OKP/Edwards curve được hỗ trợ | Đường cong và dạng khóa đúng profile |
| HS256, HS384, HS512 | Bí mật đối xứng | Bí mật đủ mạnh từ secret store; không lấy public key làm HMAC secret |

Đây là các ví dụ thuật toán phổ biến, không phải danh sách được tự động cho phép. Hệ thống phải chọn một tập thuật toán nhỏ phù hợp nhu cầu và triển khai.

Một lỗi thiết kế nghiêm trọng là **algorithm confusion**: ví dụ cùng một chuỗi byte của khóa RSA công khai bị diễn giải như bí mật HMAC khi token đổi alg từ RS256 sang HS256. Để tránh lỗi này, thuật toán và loại khóa phải được ràng buộc độc lập; không dùng cùng một vật liệu khóa cho hai vai trò không tương thích.

Với JWE, cần phân biệt:

- **alg:** thuật toán quản lý khóa hoặc thiết lập khóa nội dung.
- **enc:** thuật toán mã hóa nội dung.

Chính sách JWE phải allowlist cả hai chiều phù hợp, ràng buộc loại khóa với alg, và kiểm tra kích thước/loại IV, ciphertext, authentication tag theo thuật toán. Không áp dụng cách hiểu alg của JWS cho JWE.

### 6.2. Đối chiếu metadata của JWK

Nếu nguồn khóa là JWKS, một JWK có thể chứa các trường như **kty**, **kid**, **use**, **key_ops**, **alg**, **crv**, **n**, **e**, **x**, **y**. Việc chọn khóa nên kiểm tra:

1. **kty:** loại khóa phải tương thích với thuật toán được phép.
2. **kid:** nếu chính sách yêu cầu kid, phải khớp chính xác trong đúng issuer/JWKS.
3. **use:** nếu có, phải phù hợp với mục đích. Với JWS xác minh chữ ký, giá trị thường là sig.
4. **key_ops:** nếu có, phải cho phép thao tác cần dùng, ví dụ verify cho JWS. Nếu cả use và key_ops xuất hiện, chúng phải nhất quán.
5. **alg:** nếu JWK giới hạn thuật toán, giá trị phải tương thích với thuật toán đang xác minh.
6. **crv / n / e / x / y:** vật liệu khóa và tham số phải hợp lệ cho loại khóa, đường cong và kích thước được cho phép.
7. **Private key material:** public JWKS không được chứa thành phần bí mật/riêng như d, p, q, dp, dq, qi hoặc k đối với khóa đối xứng.

Không phải mọi trường đều bắt buộc phải xuất hiện trong mọi JWK. Chính sách cần áp dụng quy tắc theo loại khóa và profile, đồng thời từ chối khóa sai cấu trúc, sai công dụng hoặc có vật liệu riêng không được phép công bố.

Đối với HMAC, bí mật không nên được phát hành như một public JWK Set. Bộ xác minh lấy bí mật từ kho bí mật đáng tin cậy và giới hạn thành phần nào được phép sử dụng bí mật đó.

## 7. Nguồn khóa phải được tin cậy độc lập với header

### 7.1. JWKS được gắn với issuer từ cấu hình

Trong mô hình phổ biến, issuer công bố một JWK Set tại endpoint đã được xác định qua cấu hình tin cậy hoặc metadata discovery đã xác minh. Bên nhận lưu mối quan hệ:

~~~text
issuer được tin cậy
    -> cấu hình discovery/endpoint đã được xác minh
        -> JWKS URI được chấp nhận
            -> tập JWK đã được kiểm tra
                -> ứng viên khóa phù hợp với alg và kid
~~~

Mối quan hệ này phải được thiết lập trước hoặc thông qua một quy trình discovery có kiểm soát. Không được lấy **jku** hay **x5u** từ header chưa xác minh rồi gửi HTTP request tới địa chỉ đó. Hành vi này có thể tạo **Server-Side Request Forgery (SSRF)**, đọc tài nguyên nội bộ hoặc cho phép kẻ tấn công cung cấp khóa của chính họ.

Nếu hệ thống hỗ trợ discovery:

- Chỉ bắt đầu từ issuer đã nằm trong danh sách tin cậy.
- Xác minh chính xác issuer trong metadata và gắn JWKS URI với issuer đó.
- Yêu cầu HTTPS và xác minh chứng thư TLS.
- Áp dụng egress allowlist, kiểm soát redirect, DNS/IP và chặn truy cập vùng mạng nội bộ hoặc địa chỉ nhạy cảm.
- Giới hạn timeout, kích thước phản hồi, số khóa, số lần retry và tốc độ refresh.
- Parse JWKS nghiêm ngặt; kiểm tra từng JWK trước khi đưa vào cache.

### 7.2. Không coi khóa nhúng trong token là nguồn tin cậy

Một JWS có thể mang trường **jwk**, hoặc chuỗi chứng chỉ **x5c**. Những dữ liệu này nằm trong thông điệp do người gửi tạo ra. Nếu bộ xác minh lấy khóa nhúng làm khóa tin cậy rồi xác minh chữ ký bằng chính khóa đó, bất kỳ ai cũng có thể tự tạo cặp khóa, ký token và tự đưa public key vào header.

Nếu một profile yêu cầu dùng khóa/chứng chỉ nhúng, nó phải quy định cách liên kết với một trust anchor được cấu hình từ trước, kiểm tra chuỗi chứng chỉ, mục đích sử dụng, thời hạn, thu hồi và danh tính. Chỉ có chứng chỉ hoặc khóa nằm trong token không tạo ra trust anchor.

## 8. Quy trình chọn khóa có kiểm soát

Quy trình thực tế có thể mô tả theo các bước sau:

1. **Chọn policy:** dựa trên endpoint và ngữ cảnh đáng tin cậy.
2. **Parse header có giới hạn:** chỉ đọc protected header đúng serialization, từ chối JSON mơ hồ.
3. **Kiểm tra alg:** phải thuộc allowlist của policy. Với JWE, kiểm tra alg và enc riêng.
4. **Chọn kho khóa:** lấy từ cấu hình issuer/policy; không lấy từ URL trong header.
5. **Lọc ứng viên:** dùng kid nếu có, sau đó kiểm tra kty, use, key_ops, alg, curve/kích thước và trạng thái khóa.
6. **Giới hạn số ứng viên:** không thử một số lượng khóa không giới hạn. Nếu không có kid, chỉ cho phép quy tắc dự phòng được định nghĩa rõ, ví dụ đúng một khóa hoạt động phù hợp.
7. **Xử lý không tìm thấy:** có thể refresh JWKS một lần theo giới hạn tần suất, sau đó tra lại. Nếu vẫn không có khóa phù hợp thì từ chối.
8. **Xử lý mơ hồ:** nếu có nhiều ứng viên tương đương mà không có quy tắc phân giải đáng tin cậy, từ chối.
9. **Xác minh mật mã:** dùng khóa đã chọn và thuật toán đã được policy cho phép.
10. **Kiểm tra claims:** xác minh issuer, audience, thời gian, loại token và những điều kiện còn lại.

### 8.1. Mã giả chọn khóa cho JWS

~~~text
function selectTrustedJwsKey(rawToken, endpointContext):
    policy = trustedPolicyFor(endpointContext)
    require policy expects signed JWT

    compact = strictParseJwsCompactWithinLimits(rawToken)
    header = strictParseProtectedHeader(compact.protectedHeader)

    require header.alg is a string
    require header.alg in policy.allowedSignatureAlgorithms
    require all header.crit parameters are understood and permitted
    require header.typ matches policy.requiredType when type is required

    keySet = trustedKeySetFor(policy.issuer)
    candidates = keySet.keys

    if header.kid exists:
        candidates = candidates where key.kid exactly matches header.kid
    else:
        require policy permits kid-less selection

    candidates = candidates where key.kty is compatible with header.alg
    candidates = candidates where key.use is absent or permits signature use
    candidates = candidates where key.key_ops is absent or permits verify
    candidates = candidates where key.alg is absent or equals header.alg
    candidates = candidates where key material and size meet policy

    require count(candidates) >= 1
    require count(candidates) <= policy.maxKeyCandidates
    require candidates are not ambiguous under policy

    return candidates[0]

function validateJws(rawToken, endpointContext):
    policy = trustedPolicyFor(endpointContext)
    key = selectTrustedJwsKey(rawToken, endpointContext)
    require verifyJwsSignatureWithOriginalInput(rawToken, key)
    claims = parseVerifiedPayload(rawToken)
    require validateIssuerAudienceTimeAndTokenProfile(claims, policy)
    return ValidatedTokenContext(claims, policy.id)
~~~

Mã giả chỉ mô tả logic. Khi không có kid, chính sách có thể cho phép tìm một khóa duy nhất phù hợp trong một tập nhỏ đã cấu hình; nếu có nhiều khóa hoặc phải thử quá nhiều khóa, từ chối. Không được âm thầm bỏ điều kiện kid nếu hợp đồng yêu cầu kid bắt buộc.

Thư viện JOSE được chọn có thể thực hiện một phần quy trình chọn khóa. Dù vậy, ứng dụng vẫn phải cấu hình rõ allowlist thuật toán, nguồn khóa, ràng buộc issuer và cách xử lý kid/metadata; không giả định mặc định của thư viện phù hợp với mô hình tin cậy của hệ thống.

## 9. Làm mới JWKS, cache và luân chuyển khóa

Khóa ký có thể thay đổi theo thời gian. Issuer có thể công bố khóa mới trước khi bắt đầu ký bằng khóa đó, giữ khóa cũ trong giai đoạn chuyển tiếp rồi loại bỏ khi token cũ đã hết hiệu lực. Bộ xác minh cần quy trình cache phù hợp để vừa hỗ trợ luân chuyển vừa hạn chế việc bị lợi dụng làm mới khóa liên tục.

### 9.1. Khi kid không được tìm thấy

Kẻ tấn công có thể gửi nhiều token với kid ngẫu nhiên để buộc bên nhận tải JWKS liên tục. Đây là dạng **refresh amplification**. Cần:

- Giới hạn số lần refresh theo issuer và theo khoảng thời gian.
- Gộp các refresh đồng thời (single-flight) để nhiều request cùng chờ một lần tải.
- Giới hạn thời gian, kích thước phản hồi, số lần thử và số redirect.
- Có thể cache ngắn kết quả kid không tồn tại, với thời hạn và dung lượng giới hạn để tránh negative-cache exhaustion.
- Sau một lần refresh hợp lệ mà vẫn không có khóa phù hợp, từ chối token.

Không tải URL khác chỉ vì kid không tìm thấy. Không coi lỗi mạng là lý do để bỏ qua xác minh hoặc tin khóa do token cung cấp.

### 9.2. Thiết kế cache

Cache khóa nên gắn với **issuer và nguồn JWKS đã xác minh**, không chỉ gắn với kid. Các dữ liệu nên quản lý gồm:

- URI nguồn khóa đã được cấu hình/xác minh.
- Thời điểm lấy, thời hạn cache và chính sách stale khi nguồn tạm lỗi.
- Phiên bản hoặc dấu vân tay tập khóa để phát hiện thay đổi.
- Trạng thái từng khóa, bao gồm khóa đã bị vô hiệu hóa theo chính sách nội bộ.
- Giới hạn dung lượng và cơ chế loại bỏ an toàn.

Không dùng cache cũ vô thời hạn. Nếu cho phép dùng stale key khi JWKS tạm không truy cập được, phải xác định thời gian tối đa và đánh giá rủi ro khóa đã bị thu hồi. Với tình huống khẩn cấp, cần có khả năng vô hiệu hóa khóa hoặc làm mới cache trên toàn bộ các điểm xác minh.

### 9.3. Luân chuyển khóa an toàn

Một quy trình luân chuyển phổ biến:

1. Issuer tạo khóa mới và công bố public key mới trong JWKS.
2. Bên nhận có thời gian tải và cache khóa mới.
3. Issuer bắt đầu ký token mới bằng khóa mới với kid tương ứng.
4. Trong giai đoạn chuyển tiếp, issuer tiếp tục công bố khóa cũ để xác minh token còn hiệu lực đã ký trước đó.
5. Sau khi token cũ hết hạn cộng với clock skew và thời gian cache hợp lý, issuer loại bỏ khóa cũ.
6. Bên nhận cập nhật cache theo TTL và cơ chế refresh đã giới hạn.

Nếu khóa riêng bị lộ, không chờ quy trình chuyển tiếp thông thường: cần vô hiệu hóa khóa bị ảnh hưởng, loại bỏ khỏi tập khóa được chấp nhận, làm mới cache và xử lý token/phiên đã phát hành theo kế hoạch ứng phó.

## 10. Những cách chọn khóa nguy hiểm

| Cách làm sai | Rủi ro | Cách xử lý đúng |
| --- | --- | --- |
| Dùng alg bất kỳ do header khai báo | Algorithm confusion, downgrade hoặc chấp nhận thuật toán yếu | Đối chiếu allowlist gắn với endpoint và issuer |
| Dùng kid làm URL hoặc đường dẫn file | SSRF, path traversal hoặc truy cập tài nguyên ngoài ý muốn | kid chỉ tra trong kho khóa đã tin cậy |
| Tải jku/x5u tùy ý | SSRF và attacker-controlled key | Dùng JWKS URI/certificate source được cấu hình và kiểm soát |
| Tin jwk/x5c nhúng trong token | Người gửi tự cung cấp khóa để xác minh chữ ký của chính họ | Ràng buộc với trust anchor và xác minh chuỗi riêng |
| Chỉ khớp kid, bỏ qua kty/use/key_ops | Chọn nhầm khóa hoặc dùng sai mục đích | Kiểm tra toàn bộ thuộc tính khóa tương thích |
| Tìm mọi khóa rồi thử vô hạn | Tốn CPU, dễ tạo DoS và hành vi không nhất quán | Giới hạn ứng viên, từ chối khi mơ hồ |
| Cache khóa theo kid toàn cục | Va chạm giữa issuer, tenant hoặc nguồn JWKS | Khóa cache theo issuer và nguồn khóa đã xác minh |
| Khi không tìm thấy khóa thì bỏ qua chữ ký | Chấp nhận token không có bằng chứng mật mã | Từ chối sau quy trình refresh giới hạn |
| Dùng public RSA key làm HMAC secret | Algorithm confusion | Tách loại khóa, nguồn khóa và allowlist thuật toán |
| Coi typ là bằng chứng token đúng loại | Token giả có thể tự khai typ mong muốn | Dùng typ như điều kiện phụ; xác minh issuer/audience/profile |

## 11. Ví dụ tình huống và quyết định

Giả sử API hóa đơn có policy: issuer là **https://identity.example.org/**, audience là **https://api.example.org/invoices**, chỉ cho phép RS256 và lấy khóa từ JWKS đã gắn với issuer đó.

| Header hoặc tình huống | Quyết định | Giải thích |
| --- | --- | --- |
| alg=RS256, kid=key-2026-a; có đúng một RSA signing key phù hợp trong JWKS tin cậy | Tiếp tục xác minh chữ ký | Header phù hợp policy và tìm được một ứng viên khóa hợp lệ |
| alg=HS256 | Từ chối | Thuật toán không nằm trong allowlist, không thử đổi cách diễn giải khóa |
| alg=none | Từ chối | Endpoint yêu cầu chữ ký |
| kid=unknown-123 | Refresh theo giới hạn, tra lại một lần, rồi từ chối nếu vẫn không thấy | kid không tạo quyền tải nguồn khóa mới |
| kid trùng trên hai khóa cùng đủ điều kiện | Từ chối do mơ hồ | Không chọn khóa tùy tiện |
| Không có kid và policy không cho phép tra cứu không kid | Từ chối | Không tự bỏ điều kiện định danh khóa |
| jku trỏ tới địa chỉ nội bộ | Bỏ qua/từ chối theo profile; không gửi request | Tránh SSRF và nguồn khóa do token điều khiển |
| jwk chứa public key do người gửi tự tạo | Không tin làm trust anchor | Khóa nhúng không tự chứng minh danh tính |
| typ=at+jwt nhưng chữ ký sai | Từ chối | typ không thay thế xác minh chữ ký |
| Header hợp lệ, chữ ký đúng nhưng claim aud là API hồ sơ | Từ chối token ở bước claims | Token không được cấp cho API hóa đơn |

Ví dụ cho thấy header chỉ tham gia một phần trong quyết định. Kết quả cuối cùng phụ thuộc cả khóa, phép xác minh mật mã và hợp đồng claims.

## 12. Kiểm thử quy tắc parse header và chọn khóa

Nên có kiểm thử riêng cho từng lớp, sau đó kiểm thử tích hợp toàn bộ luồng:

| Nhóm | Ca kiểm thử |
| --- | --- |
| Cú pháp header | Header thiếu, sai Base64URL, UTF-8 lỗi, JSON root không phải object, thuộc tính trùng, JSON quá lớn/quá sâu |
| Kiểu dữ liệu | alg/kid/typ sai kiểu, crit không phải mảng, phần tử crit không phải chuỗi |
| Thuật toán | alg nằm trong allowlist, ngoài allowlist, none, sai chữ hoa/thường, alg không phù hợp loại token |
| kid | kid đúng, không tồn tại, quá dài, rỗng, trùng giữa issuer, trùng trong cùng JWKS, không có kid |
| Metadata khóa | kty sai, use sai, key_ops không có verify, alg JWK xung đột, đường cong hoặc kích thước không hợp lệ |
| Nguồn khóa | JWKS URI tin cậy, jku tùy ý, x5u tùy ý, redirect, TLS lỗi, DNS đổi sang địa chỉ nội bộ |
| Refresh/cache | Nhiều kid lạ đồng thời, refresh liên tục, JWKS timeout, cache hết hạn, khóa mới, khóa cũ bị loại |
| Mật mã và claims | Chữ ký đúng/sai, issuer sai, audience sai, token hết hạn, typ đúng nhưng chữ ký sai |
| Đa issuer | kid giống nhau ở hai issuer, issuer lạ, issuer hint không khớp claim iss sau xác minh |

Kiểm thử fuzzing cho header JSON và JWK Set có ích để phát hiện lỗi parser, lỗi cấp phát và sai khác giữa thư viện. Kiểm thử mạng nên xác nhận không có yêu cầu HTTP nào được gửi tới URL do header chưa xác minh chỉ định.

## 13. Quan sát vận hành và xử lý lỗi

Các lỗi chọn khóa cần được ghi nhận đủ để vận hành nhưng không làm lộ token hoặc bí mật. Có thể sử dụng mã lỗi như:

- **HEADER_PARSE_FAILED:** header sai cú pháp hoặc vượt giới hạn.
- **UNSUPPORTED_ALGORITHM:** alg không nằm trong allowlist.
- **KEY_NOT_FOUND:** không có khóa phù hợp sau quy trình tra cứu được phép.
- **AMBIGUOUS_KEY:** có nhiều ứng viên mà policy không phân giải được.
- **KEY_METADATA_MISMATCH:** kty, use, key_ops, alg hoặc tham số khóa không phù hợp.
- **TRUSTED_KEY_SOURCE_UNAVAILABLE:** nguồn JWKS tin cậy không truy cập được.
- **SIGNATURE_INVALID:** phép xác minh chữ ký thất bại.
- **TOKEN_CLAIM_INVALID:** chữ ký hợp lệ nhưng issuer, audience, thời gian hoặc profile không đạt.

Nên theo dõi số lần kid không tìm thấy, số lần refresh JWKS, thời gian tải JWKS, số khóa trong cache, tỷ lệ lỗi parse và tỷ lệ xác minh thất bại. Nếu số lượng kid lạ tăng đột biến, đó có thể là dấu hiệu dò khóa hoặc cố ý kích hoạt refresh.

Không ghi toàn bộ JWT, Authorization header, khóa riêng, HMAC secret hay claims nhạy cảm. Không đưa kid/issuer chưa xác minh trực tiếp vào log theo cách cho phép log injection; cần giới hạn độ dài và mã hóa an toàn khi ghi dữ liệu do người gửi kiểm soát.

## 14. Checklist trước khi đưa vào sử dụng

1. [ ] Policy được chọn từ endpoint/ngữ cảnh đáng tin cậy trước khi đọc header.
2. [ ] Header được parse trong giới hạn kích thước, độ sâu và số trường; từ chối JSON có thuộc tính trùng.
3. [ ] alg luôn được đối chiếu với allowlist riêng cho token profile; không thử thuật toán tùy ý.
4. [ ] kid chỉ tra trong kho khóa đã gắn với issuer; không dùng làm URL hoặc đường dẫn.
5. [ ] kty, use, key_ops, alg và tham số vật liệu khóa được kiểm tra tương thích.
6. [ ] Không tin jku, x5u, jwk hoặc x5c chỉ vì chúng nằm trong header.
7. [ ] JWKS URI và issuer được cấu hình/xác minh độc lập; có TLS, kiểm soát egress, redirect, DNS, timeout và kích thước phản hồi.
8. [ ] Số ứng viên khóa, số lần refresh và tải đồng thời đều có giới hạn.
9. [ ] Cache khóa gắn với issuer/nguồn tin cậy; có kế hoạch rotation và vô hiệu hóa khóa.
10. [ ] Sau khi chọn khóa, chữ ký hoặc cơ chế bảo vệ mật mã vẫn được xác minh; claims được kiểm tra đầy đủ trước khi sử dụng.
11. [ ] Có kiểm thử algorithm confusion, kid lạ, nguồn khóa tùy ý, JWKS lỗi và đa issuer.
12. [ ] Log không ghi token hoặc bí mật; có chỉ số theo dõi hành vi tra cứu và refresh bất thường.

## 15. Tài liệu tiêu chuẩn liên quan

- **RFC 7515 — JSON Web Signature (JWS):** JOSE header, protected header và chữ ký JWS.
- **RFC 7516 — JSON Web Encryption (JWE):** header và thuật toán quản lý khóa/mã hóa nội dung trong JWE.
- **RFC 7517 — JSON Web Key (JWK):** JWK, JWKS và các thuộc tính khóa như kty, use, key_ops, alg, kid.
- **RFC 7518 — JSON Web Algorithms (JWA):** tên và tham số thuật toán mật mã JOSE.
- **RFC 7519 — JSON Web Token (JWT):** JWT Claims Set và cấu trúc token.
- **RFC 7638 — JSON Web Key (JWK) Thumbprint:** cách tạo thumbprint từ các thành phần JWK được chỉ định.
- **RFC 8725 — JSON Web Token Best Current Practices:** ràng buộc thuật toán, nguồn khóa, issuer/audience và phòng nhầm lẫn JWT.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** metadata của authorization server, bao gồm thông tin endpoint khóa trong mô hình OAuth.

**Điểm cần nhớ:** Header là đầu vào để đối chiếu và chọn ứng viên khóa trong một tập tin cậy đã có. **Chính sách quyết định thuật toán và nguồn khóa; phép xác minh mật mã quyết định chữ ký có đúng; claims và ngữ cảnh quyết định token có được chấp nhận cho dịch vụ hay không.**
