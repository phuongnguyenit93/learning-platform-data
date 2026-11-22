# Giới hạn độ dài, kiểu dữ liệu và các tham số header được chấp nhận

## 1. Vì sao phải kiểm soát JOSE Header?

JOSE Header là metadata điều khiển cách xử lý JSON Web Signature (JWS) hoặc JSON Web Encryption (JWE). Nó có thể xác định thuật toán, khóa, chứng thư, loại nội dung và các phần mở rộng ảnh hưởng trực tiếp đến quá trình xác minh hoặc giải mã.

Trong JWT, header nằm ở đầu token nên thường được parse trước khi chữ ký được xác minh hoặc nội dung JWE được giải mã. Vì vậy, dữ liệu header là **đầu vào chưa đáng tin cậy**. Một token có thể chứa:

- Header quá lớn hoặc JSON lồng quá sâu để gây tiêu hao bộ nhớ/CPU.
- Giá trị sai kiểu, ví dụ alg là object thay vì string.
- Tham số trùng lặp khiến hai parser hiểu cùng token theo hai cách khác nhau.
- Thuật toán, khóa hoặc URI ngoài chính sách.
- Tham số mở rộng chưa được hỗ trợ nhưng lại ảnh hưởng đến cách diễn giải token.
- Các trường hợp mã hóa Base64URL hoặc UTF-8 không hợp lệ.

Do đó, bên nhận cần giới hạn kích thước, parse JSON nghiêm ngặt, kiểm tra kiểu dữ liệu và áp dụng allowlist tham số theo profile. Mục tiêu là bảo đảm mọi thành phần trong hệ thống hiểu cùng một header và chỉ thực hiện các thao tác đã được cấu hình cho phép.

Bài này áp dụng cho JOSE/JWT tổng quát, không phụ thuộc ngôn ngữ lập trình hay framework.

## 2. Cấu trúc header trong JWS và JWE

### Compact Serialization

JWS Compact có ba phần được ngăn cách bởi dấu chấm:

~~~text
BASE64URL(protected-header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

JWE Compact có năm phần:

~~~text
BASE64URL(protected-header)
.
BASE64URL(encrypted-key)
.
BASE64URL(iv)
.
BASE64URL(ciphertext)
.
BASE64URL(authentication-tag)
~~~

Phần đầu tiên là protected JOSE Header được mã hóa Base64URL từ một JSON object. Trong JWS, protected header được đưa vào signing input. Trong JWE, protected header được dùng làm dữ liệu xác thực bổ sung (AAD) theo cấu trúc JWE.

### JSON Serialization

JWS JSON Serialization và JWE JSON Serialization có thể tách header thành các vùng:

- Protected Header: được bảo vệ toàn vẹn bởi chữ ký JWS hoặc authentication tag của JWE.
- Unprotected Header: không được bảo vệ toàn vẹn bởi lớp JOSE tương ứng.
- JWE Per-Recipient Header: metadata dành riêng cho từng recipient.

Một ứng dụng cần biết tham số nằm ở vùng nào. Thông tin quyết định thuật toán, khóa, danh tính, cách giải mã hoặc cách diễn giải payload phải được bảo vệ theo quy tắc JOSE và profile ứng dụng. Không lấy giá trị ở unprotected header để ghi đè một giá trị protected hoặc để thay đổi chính sách tin cậy.

Trong các serialization, tên header parameter không được trùng lặp trong các header có hiệu lực của cùng đối tượng. Nếu một tham số xuất hiện ở nhiều vùng gây xung đột, từ chối thay vì tùy tiện chọn giá trị đầu tiên hoặc cuối cùng.

## 3. Giới hạn độ dài và tài nguyên

Các RFC JOSE không đưa ra một giới hạn byte chung áp dụng cho mọi hệ thống và mọi loại token. Ứng dụng cần đặt giới hạn theo giao thức, kích thước token dự kiến và năng lực vận hành. Giới hạn phải được áp dụng **trước khi cấp phát bộ nhớ lớn hoặc thực hiện thao tác mật mã tốn kém**.

Các lớp giới hạn nên xem xét:

| Thành phần | Giới hạn cần đặt | Lý do |
| --- | --- | --- |
| Toàn bộ token | Số byte tối đa trước khi parse | Ngăn request body hoặc header token quá lớn |
| Protected header segment | Số byte Base64URL tối đa | Giới hạn dữ liệu cần decode và parse |
| JSON header sau decode | Số byte, số thành viên và độ sâu lồng nhau | Ngăn JSON quá lớn hoặc parser DoS |
| Tên parameter | Độ dài tối đa theo profile | Tránh tên bất thường hoặc payload đầu vào phình to |
| Giá trị string | Độ dài tối đa theo từng parameter | Ví dụ kid, typ, URI và giá trị extension |
| Mảng x5c/crit | Số phần tử và kích thước từng phần tử | Giới hạn số chứng thư hoặc extension |
| JWK | Kích thước tham số và số thành viên | Ngăn khóa cực lớn hoặc cấu trúc bất thường |
| JWE recipients | Số recipient tối đa trong JSON Serialization | Giới hạn công việc chọn khóa và giải mã |
| Nested JWT | Số lớp lồng nhau tối đa | Tránh đệ quy không giới hạn |
| Thời gian xử lý | Timeout parse, tải khóa, xác minh và giải mã | Giảm nguy cơ tiêu hao CPU và giữ tài nguyên quá lâu |

Ví dụ một profile nội bộ có thể đặt giới hạn token 32 KiB, protected header 4 KiB, tối đa 32 header parameters, độ sâu JSON tối đa 8 và tối đa 4 chứng thư trong x5c. Đây chỉ là **giá trị minh họa**, không phải giới hạn bắt buộc của RFC. Mỗi hệ thống cần đo token thực tế và đặt giới hạn đủ dùng nhưng có kiểm soát.

Không chỉ kiểm tra độ dài chuỗi sau khi đã decode. Cần giới hạn kích thước đầu vào Base64URL trước, rồi giới hạn kích thước dữ liệu sau decode và parse. Tương tự, giới hạn response khi tải JWKS hoặc chứng thư phải được áp dụng cả trước và sau giải nén nếu HTTP client hỗ trợ nén.

### Tránh tiêu hao tài nguyên trong JWE

Nếu profile cho phép tham số zip để nén plaintext trước khi mã hóa, cần cân nhắc tắt nếu không có nhu cầu. Khi bật nén:

- Giới hạn kích thước plaintext sau giải nén.
- Giới hạn tỷ lệ giữa kích thước sau và trước giải nén.
- Giới hạn thời gian và bộ nhớ cho thao tác giải nén.
- Không giải nén trước khi JWE authentication tag được xác minh thành công.
- Không để kết quả giải nén không giới hạn đi vào parser JSON hoặc ứng dụng.

Giải mã thành công không đồng nghĩa nội dung đã an toàn để xử lý. Payload vẫn phải tuân theo giới hạn và schema của profile.

## 4. Parse JSON Header một cách nghiêm ngặt

Protected header trong Compact Serialization là JSON object được mã hóa Base64URL. Sau khi decode, cần parse theo JSON chuẩn và từ chối dữ liệu sai định dạng.

Các điều kiện nên kiểm tra:

1. Base64URL chỉ dùng bảng ký tự được JOSE cho phép và segment không bị cắt cụt.
2. Dữ liệu sau decode là UTF-8 hợp lệ.
3. JSON phải là object ở cấp cao nhất, không phải array, string, number, boolean hoặc null.
4. Không chấp nhận comment, trailing comma hoặc cú pháp mở rộng không thuộc JSON.
5. Tên thành viên JSON không được trùng lặp.
6. Độ sâu, số thành viên, kích thước string và tổng kích thước nằm trong giới hạn.
7. Kiểu dữ liệu từng parameter phải khớp đặc tả; không tự ép kiểu.
8. Không chuẩn hóa tên parameter theo kiểu chữ thường/hoa.

Tên JOSE Header Parameter phân biệt chữ hoa và chữ thường. Ví dụ alg và ALG là hai tên khác nhau; ALG không trở thành alg chỉ vì parser tự chuyển về lowercase. Tên không được nhận diện phải được xử lý theo quy tắc extension và profile, không tự đoán.

### Vì sao phải từ chối tên JSON trùng lặp?

Ví dụ:

~~~json
{
  "alg": "PS256",
  "alg": "none",
  "kid": "issuer-key-01"
}
~~~

Một parser có thể giữ giá trị đầu tiên, parser khác giữ giá trị cuối cùng, và parser khác nữa có thể báo lỗi. Nếu một thành phần kiểm tra PS256 nhưng thành phần xác minh đọc none, các bước có thể không còn cùng một cách hiểu.

RFC 7515 và RFC 7516 yêu cầu tên header parameter phải duy nhất trong các vùng header tương ứng. Cách an toàn là từ chối JSON có tên thành viên trùng lặp ngay khi parse, thay vì phụ thuộc hành vi của parser.

## 5. Kiểu dữ liệu của các JOSE Header Parameter thường gặp

Mỗi parameter có kiểu dữ liệu và ngữ nghĩa riêng. Không được chấp nhận chỉ vì giá trị “trông giống” một giá trị hợp lệ.

| Parameter | Kiểu dữ liệu JSON | Ví dụ/ghi chú |
| --- | --- | --- |
| alg | String | Định danh thuật toán JWS hoặc thuật toán quản lý khóa JWE |
| enc | String | Định danh thuật toán mã hóa nội dung JWE |
| typ | String | Loại đối tượng, ví dụ JWT hoặc profile media type |
| cty | String | Kiểu nội dung payload, ví dụ JWT trong nested JWT |
| kid | String | Định danh khóa trong tập khóa theo ngữ cảnh |
| jku | String | URI tham chiếu tới JWKS |
| x5u | String | URI tham chiếu tới chứng thư/chuỗi chứng thư |
| jwk | Object | Một JSON Web Key |
| x5c | Array of strings | Mỗi phần tử là Base64 của chứng thư DER |
| x5t | String | Certificate thumbprint SHA-1 được mã hóa Base64URL |
| x5t#S256 | String | Certificate thumbprint SHA-256 được mã hóa Base64URL |
| crit | Array of strings | Danh sách tên extension critical |
| b64 | Boolean | Quy định payload JWS có được Base64URL encode trong signing input hay không |
| zip | String | Định danh thuật toán nén plaintext của JWE |
| epk | Object | JWK biểu diễn ephemeral public key trong thuật toán thỏa thuận khóa |
| apu | String | PartyUInfo được mã hóa Base64URL trong thuật toán ECDH-ES |
| apv | String | PartyVInfo được mã hóa Base64URL trong thuật toán ECDH-ES |
| p2s | String | Salt được mã hóa Base64URL trong PBES2 |
| p2c | Integer | Số vòng lặp PBES2 theo giới hạn thuật toán/profile |

Bảng trên liệt kê các tham số phổ biến, không phải toàn bộ IANA JOSE Header Parameter Registry. Một profile có thể chỉ hỗ trợ một tập con. Một extension hoặc thuật toán mới có thể định nghĩa parameter bổ sung và phải có đặc tả riêng.

### Kiểu đúng chưa đủ

Ví dụ alg là string vẫn chưa đủ để chấp nhận. Giá trị phải thuộc allowlist và phù hợp với loại khóa. Tương tự, x5c là array nhưng từng phần tử vẫn phải Base64-decode thành chứng thư DER hợp lệ; jwk là object nhưng phải có tham số khóa đúng cấu trúc.

Các trường dạng số như p2c phải được parse thành integer trong miền an toàn, không chấp nhận string "4096", số thực 4096.0 hoặc số vượt giới hạn chỉ vì parser có thể chuyển đổi. Profile cần đặt min/max theo yêu cầu thuật toán.

## 6. Kiểm tra giá trị theo từng parameter

### alg và enc

- alg phải là string không rỗng và nằm trong allowlist cấu hình cho đúng loại đối tượng.
- Với JWS, alg là thuật toán chữ ký/MAC; với JWE, alg là thuật toán quản lý/thỏa thuận khóa.
- Với JWE, enc phải là string thuộc allowlist thuật toán mã hóa nội dung.
- Không suy ra allowlist từ header hoặc từ khả năng hỗ trợ của thư viện.
- Ràng buộc thuật toán với loại khóa và mục đích sử dụng khóa.
- Từ chối none cho token dùng xác thực hoặc cấp quyền, trừ khi một giao thức đặc biệt có quy định rõ và được thiết kế riêng.

### typ và cty

- typ và cty phải là string nếu xuất hiện.
- So khớp loại token theo profile; không dùng một JWT bất kỳ ở mọi endpoint.
- cty: JWT chỉ phù hợp khi payload của đối tượng JOSE là một JWT khác theo quy tắc nested JWT.
- Không coi typ hoặc cty là bằng chứng xác thực nguồn phát hành.

### kid, jku và x5u

- kid phải là string có giới hạn độ dài và chỉ được dùng để tìm khóa trong tập đã tin cậy.
- Không ghép kid trực tiếp thành đường dẫn file, truy vấn SQL hoặc lệnh.
- jku/x5u phải được kiểm soát theo nguồn tin cậy của issuer; không tự động tải URL bất kỳ từ token.
- Khi tải tài nguyên, kiểm soát HTTPS/TLS, hostname, DNS/IP, redirect, timeout và kích thước response.

### jwk và x5c

- jwk phải là JSON object theo JWK; kiểm tra kty, tham số bắt buộc, kích thước, đường cong, alg/use/key_ops nếu có.
- Không chấp nhận private key hoặc symmetric secret trong header công khai.
- x5c phải là mảng chuỗi Base64 của DER certificate; giới hạn số lượng và kích thước.
- Sau khi parse chứng thư, xác minh PKIX path, trust anchor, danh tính issuer/recipient, Key Usage và trạng thái thu hồi theo profile.

### crit và b64

- crit phải là mảng chuỗi không rỗng, tên duy nhất và mỗi tên phải tồn tại trong cùng protected header.
- crit và mọi extension được liệt kê phải được bảo vệ toàn vẹn.
- Nếu extension critical không được hiểu hoặc không thể xử lý chính xác, từ chối.
- b64 phải là boolean. Nếu b64=false, nó phải được liệt kê trong crit theo RFC 7797 và xử lý đúng quy tắc JWS unencoded payload.

## 7. Allowlist parameter theo profile

Không nên chấp nhận mọi parameter chỉ vì chúng có trong JOSE registry. Endpoint cần định nghĩa rõ tập parameter phù hợp với loại token và chức năng của nó.

Ví dụ profile khái niệm cho access token JWS:

~~~yaml
accessTokenJws:
  serialization: compact
  allowedAlgorithms:
    - PS256
  allowedHeaderParameters:
    - alg
    - typ
    - kid
  requiredHeaderParameters:
    - alg
    - typ
  expectedType: at+jwt
  allowCriticalExtensions: false
  maxTokenBytes: 32768
  maxProtectedHeaderBytes: 4096
~~~

Đây là ví dụ cấu hình ứng dụng, không phải schema bắt buộc của RFC. Nếu endpoint dùng x5c, jwk hoặc extension khác thì phải thêm chúng cùng các quy tắc kiểm tra tương ứng. Nếu endpoint không cần jku/x5u thì không đưa chúng vào allowlist.

Một profile JWE có thể cần alg, enc, kid, cty và các tham số thuật toán như epk, apu, apv, p2s, p2c. Chỉ cho phép đúng tập con cần thiết cho thuật toán được chọn.

### Unknown parameter

JOSE được thiết kế có khả năng mở rộng. Theo quy tắc JWS/JWE, parameter không được nhận diện và không được đánh dấu critical có thể bị bỏ qua. Parameter được liệt kê trong crit thì bắt buộc phải được hiểu và xử lý.

Tuy nhiên, profile ứng dụng có thể áp dụng chính sách chặt hơn, ví dụ từ chối mọi parameter ngoài allowlist để giảm khác biệt giữa các implementation. Nếu profile làm vậy, cần bảo đảm bên phát hành và bên nhận thống nhất danh sách; không tự ý bỏ qua extension đã được giao thức yêu cầu.

Không được nhầm “unknown non-critical có thể bỏ qua” với “mọi giá trị trong header đều an toàn”. Các parameter đã biết vẫn phải kiểm tra kiểu, giá trị, vị trí bảo vệ và ngữ cảnh sử dụng.

## 8. Protected và unprotected header: quy tắc chấp nhận

Trong Compact Serialization, header là protected. Trong JSON Serialization, một số parameter có thể nằm trong vùng unprotected theo quy tắc của từng định dạng. Bên nhận cần xác định parameter nào có thể được đặt ở đâu.

Các thông tin thường phải được bảo vệ khi tham gia quyết định bảo mật:

- alg của JWS và alg/enc của JWE.
- kid, jwk, jku, x5c, x5u, x5t hoặc x5t#S256 khi được dùng để chọn khóa hoặc nguồn khóa.
- typ/cty khi profile dùng chúng để phân loại hoặc chọn quy trình xử lý.
- crit và tất cả extension được liệt kê.
- Các parameter ảnh hưởng tới cách dựng signing input, quản lý khóa, giải mã hoặc diễn giải payload.

Nếu cùng một parameter xuất hiện trong protected và unprotected header hoặc nhiều header vùng khác nhau, từ chối theo quy tắc duplicate của JOSE. Không để parser gộp object theo cách ghi đè khiến quyết định bảo mật phụ thuộc thứ tự.

Việc bảo vệ header không xác thực danh tính người gửi nếu khóa xác minh chưa được tin cậy. Sau khi integrity check thành công, vẫn phải xác minh khóa, issuer và claims.

## 9. Quy trình validate header trước khi xử lý token

Quy trình tổng quát:

1. Chọn endpoint/profile từ cấu hình tin cậy.
2. Kiểm tra kích thước token thô trước khi decode.
3. Kiểm tra số segment và cấu trúc Compact/JSON Serialization đúng với profile.
4. Decode Base64URL theo quy tắc JOSE; từ chối dữ liệu sai bảng ký tự hoặc sai định dạng.
5. Parse UTF-8 JSON nghiêm ngặt; yêu cầu object và từ chối duplicate member names.
6. Kiểm tra kích thước, số parameter, độ sâu JSON, kiểu dữ liệu và miền giá trị.
7. Kiểm tra parameter có nằm trong allowlist/profile và đúng vùng protected/unprotected.
8. Kiểm tra alg/enc với allowlist; ràng buộc với loại khóa và mục đích.
9. Kiểm tra crit và thực thi đầy đủ các extension được liệt kê.
10. Chọn khóa từ nguồn tin cậy; không để token tự chỉ định nguồn khóa tùy ý.
11. Xác minh chữ ký JWS hoặc xác thực/giải mã JWE.
12. Sau khi lớp mật mã thành công, kiểm tra issuer, audience, thời gian, loại token và quy tắc nghiệp vụ.

~~~mermaid
flowchart TD
    A["Nhận token chưa tin cậy"] --> B["Giới hạn kích thước token"]
    B --> C["Kiểm tra serialization và Base64URL"]
    C --> D["Parse JSON nghiêm ngặt"]
    D --> E{"Không duplicate, đúng kiểu và giới hạn?"}
    E -- Không --> X["Từ chối"]
    E -- Có --> F["Kiểm tra allowlist và vị trí header"]
    F --> G{"alg/enc/crit hợp lệ?"}
    G -- Không --> X
    G -- Có --> H["Chọn khóa từ nguồn tin cậy"]
    H --> I["Xác minh JWS hoặc xác thực/giải mã JWE"]
    I --> J{"Bảo vệ mật mã hợp lệ?"}
    J -- Không --> X
    J -- Có --> K["Kiểm tra claims và profile"]
    K --> L{"Claims hợp lệ?"}
    L -- Không --> X
    L -- Có --> M["Chấp nhận token"]
~~~

### Mã giả độc lập nền tảng

~~~text
function validateJoseHeader(token, profile):
    require byteLength(token) <= profile.maxTokenBytes
    parts = parseExpectedSerialization(token, profile.serialization)
    protectedBytes = strictBase64UrlDecode(parts.protectedHeader)
    require byteLength(protectedBytes) <= profile.maxProtectedHeaderBytes

    header = parseUtf8JsonObjectStrictly(
        protectedBytes,
        rejectDuplicateNames = true,
        maxDepth = profile.maxJsonDepth,
        maxMembers = profile.maxHeaderParameters
    )

    require allParameterTypesAreCorrect(header)
    require allParameterValuesWithinLimits(header, profile)
    require headerNamesAreAllowed(header, profile)
    require protectedAndUnprotectedNamesDoNotConflict(parts)
    require algorithmAndKeyPolicyMatch(header, profile)
    require allCriticalExtensionsAreSupported(header, profile)

    return header
~~~

Đây là mã giả cho bước validate cấu trúc/header. Nó không thay thế bước xác minh chữ ký, authentication tag, issuer hoặc claims.

## 10. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Không giới hạn kích thước token/header | Memory exhaustion hoặc parser DoS | Giới hạn trước decode và sau decode |
| Chỉ giới hạn toàn token nhưng không giới hạn độ sâu JSON | Parser có thể bị tiêu hao bởi cấu trúc lồng sâu | Giới hạn depth, members và arrays |
| Chấp nhận duplicate JSON member names | Parser differential giữa các thành phần | Từ chối duplicate ngay khi parse |
| Tự chuyển tên parameter về lowercase | Thay đổi ý nghĩa tên case-sensitive hoặc tạo alias không mong muốn | So khớp chính xác tên JOSE |
| Ép kiểu string/number/boolean | Hai implementation có thể diễn giải khác nhau | Kiểm tra kiểu JSON chính xác, không coercion |
| Cho phép mọi parameter thư viện hỗ trợ | Bề mặt xử lý rộng hơn profile | Dùng allowlist theo endpoint/token type |
| Bỏ qua unknown critical extension | Diễn giải token sai so với bên phát hành | Từ chối nếu không hỗ trợ crit |
| Để parameter bảo mật trong unprotected header | Giá trị có thể bị thay đổi ngoài bảo vệ mật mã | Yêu cầu protected header theo profile |
| Cho phép alg/enc tùy ý từ token | Algorithm confusion hoặc downgrade | Allowlist độc lập và key binding |
| Tự tải jku/x5u không giới hạn | SSRF, tải dữ liệu lớn hoặc nguồn khóa giả | Trust source, network controls và response limits |
| Không giới hạn zip/decompression | Decompression bomb | Tắt hoặc giới hạn kích thước/tỷ lệ giải nén |
| Parse header rồi cấp quyền trước khi verify | Payload giả được coi là đã xác thực | Chỉ cấp quyền sau toàn bộ bước mật mã và claim validation |

## 11. Bộ ca kiểm thử

Giả sử endpoint chỉ nhận JWS Compact access token với allowlist alg=PS256, typ=at+jwt, kid là string, không cho extension critical và giới hạn header 4 KiB.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Header JSON hợp lệ, alg/typ đúng profile, chữ ký và claims hợp lệ | **Chấp nhận** |
| Token vượt giới hạn kích thước tổng | **Từ chối trước khi parse** |
| Protected header vượt giới hạn byte | **Từ chối trước khi parse JSON** |
| Header sau decode không phải UTF-8/JSON hợp lệ | **Từ chối** |
| JSON cấp cao nhất là array hoặc string thay vì object | **Từ chối** |
| Header chứa tên parameter alg trùng lặp | **Từ chối** |
| Header có kiểu alg là object hoặc number | **Từ chối** |
| kid là array/object hoặc vượt độ dài profile | **Từ chối** |
| alg là RS256 hoặc none ngoài allowlist | **Từ chối** |
| Header chứa parameter không thuộc allowlist chặt của profile | **Từ chối** theo profile |
| Header chứa unknown non-critical parameter và profile cho phép bỏ qua | Có thể **tiếp tục** nếu mọi điều kiện khác hợp lệ |
| crit liệt kê extension chưa hỗ trợ | **Từ chối** |
| crit là mảng rỗng, có tên trùng hoặc tên không tồn tại | **Từ chối** |
| crit/extension chỉ nằm trong unprotected header | **Từ chối** |
| Header có ký tự Base64URL sai hoặc segment bị cắt | **Từ chối** |
| JSON lồng sâu hoặc có quá nhiều member/array elements | **Từ chối theo giới hạn** |
| Header hợp lệ nhưng chữ ký sai | **Từ chối** |
| Header và chữ ký hợp lệ nhưng iss/aud/exp sai | **Từ chối** |

Các ca kiểm thử phải xác nhận parser không tạo authenticated context hoặc thực hiện hành động ứng dụng trước khi chữ ký được xác minh và claims được kiểm tra.

## 12. Ghi nhớ

- JOSE Header là đầu vào chưa đáng tin cậy cho tới khi lớp bảo vệ mật mã tương ứng được xác minh.
- Đặt giới hạn cho toàn token, protected header, JSON depth, số parameter, string, array, JWK, certificate chain, recipient và nested JWT.
- Parse JSON nghiêm ngặt: UTF-8 hợp lệ, object cấp cao nhất, không duplicate names, không coercion và không tự chuẩn hóa tên parameter.
- Mỗi parameter có kiểu dữ liệu riêng; kiểm tra cả kiểu, miền giá trị và ngữ cảnh sử dụng.
- Dùng allowlist parameter/algorithm theo endpoint và token profile; không mở rộng chính sách từ dữ liệu header.
- Unknown non-critical parameter có thể được bỏ qua theo quy tắc JOSE, nhưng unknown critical extension bắt buộc bị từ chối; profile có thể đặt chính sách chặt hơn.
- Parameter ảnh hưởng đến xác minh, khóa, giải mã hoặc diễn giải payload phải được bảo vệ theo quy tắc JOSE.
- Chỉ cấp quyền sau khi xác minh chữ ký/JWE authentication và kiểm tra đầy đủ claims.

### Tài liệu chuẩn tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): cấu trúc JWS, header parameters, serialization và critical extensions.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): cấu trúc JWE, protected/unprotected header và xử lý header parameters.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): cấu trúc JWK/JWKS và metadata khóa.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): các thuật toán và tham số JOSE.
- [RFC 7797 — JWS Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797): tham số b64 và critical marking.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): cú pháp JSON và tên thành viên object.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xử lý JWT an toàn theo profile và ngữ cảnh.
