# Cấu hình danh sách thuật toán và claims bắt buộc một cách tường minh

## 1. Vì sao cấu hình JWT phải tường minh?

Một thư viện JWT có thể cung cấp nhiều thao tác: giải mã compact token, xác minh chữ ký, kiểm tra thời hạn, đọc claims, lấy khóa từ JWKS và chuyển claims thành principal. Các thao tác này không có cùng mức bảo đảm.

Đọc được payload chỉ cho biết token chứa dữ liệu gì. Nó không chứng minh chữ ký hợp lệ, issuer đáng tin, audience phù hợp hoặc token thuộc đúng mục đích. Nếu ứng dụng dựa vào mặc định của thư viện, nó có thể vô tình chấp nhận thuật toán ngoài dự kiến, bỏ qua claim bắt buộc hoặc dùng một validator cho nhiều loại token.

Ví dụ một access token:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "iat": 1900000000,
  "exp": 1900000300,
  "scope": "invoice:read"
}
~~~

Chỉ kiểm tra chữ ký và exp là chưa đủ. Resource server còn phải biết:

- Thuật toán nào được phép dùng để ký token?
- Khóa nào được phép xác minh token của issuer này?
- Issuer có đúng với cấu hình tin cậy không?
- Audience có chứa chính resource server đang xử lý request không?
- Token có đúng profile access token mà endpoint yêu cầu không?
- Claims nào bắt buộc, kiểu dữ liệu và ngữ nghĩa của chúng là gì?
- Khi claim thiếu, sai kiểu, mâu thuẫn hoặc không thể kiểm tra thì hệ thống phản ứng ra sao?

**Cấu hình tường minh** biến những yêu cầu này thành hợp đồng có thể đọc, review, kiểm thử và vận hành. Nó cũng giúp nâng cấp thư viện hoặc thay đổi issuer mà không làm thay đổi ngầm chính sách bảo mật.

Nguyên tắc cốt lõi:

> **Không để JWT tự quyết định thuật toán, nguồn khóa, issuer, audience hoặc loại token mà ứng dụng chấp nhận. Những giới hạn đó phải được cấu hình từ trust policy và token profile của ứng dụng.**

Bài này thuộc phạm vi Security chung của JSON Web Token (JWT), áp dụng khi tích hợp bất kỳ thư viện hoặc nền tảng xác minh JWT nào. Nội dung tập trung vào thiết kế cấu hình và hợp đồng xác minh, không phụ thuộc ngôn ngữ lập trình hay framework cụ thể.

## 2. Tách cấu hình thành các lớp độc lập

Không nên gom tất cả quy tắc vào một cờ enable/disable hoặc một hàm validate tổng quát. Một cấu hình dễ review thường tách ít nhất năm lớp:

| Lớp | Câu hỏi cần trả lời | Ví dụ cấu hình |
| --- | --- | --- |
| **Token profile** | Endpoint nhận loại JWT nào? | OAuth JWT Access Token theo RFC 9068. |
| **Issuer trust** | Ai được phép phát hành token? | Issuer URI và trust record đã phê duyệt. |
| **Algorithm policy** | Thuật toán và loại khóa nào được phép? | RS256 với RSA public key đạt kích thước tối thiểu. |
| **Claim policy** | Claim nào bắt buộc và phải có kiểu/ngữ nghĩa nào? | iss, aud, sub, exp, iat, jti theo profile. |
| **Runtime policy** | Xử lý clock skew, cache, rotation và lỗi thế nào? | Clock skew giới hạn, JWKS refresh có rate limit. |

Các lớp liên quan nhưng không thay thế nhau:

- Allowlist thuật toán không xác định issuer.
- Issuer đúng không làm audience tự động đúng.
- Chữ ký hợp lệ không chứng minh token thuộc đúng profile.
- Claim có mặt không chứng minh giá trị của nó đúng kiểu hoặc có thẩm quyền.
- Library báo signature valid không có nghĩa toàn bộ authorization đã thành công.

## 3. Cấu hình allowlist thuật toán chữ ký

JOSE header có trường alg để chỉ thuật toán được dùng cho JWS/JWT. Header này nằm trong token do người gửi cung cấp, vì vậy verifier phải đối chiếu nó với policy đã cấu hình.

### 3.1. Không để token tự chọn thuật toán

Một JWT có thể tự khai báo:

~~~json
{
  "alg": "HS256",
  "kid": "key-01"
}
~~~

Nếu ứng dụng chỉ đọc alg rồi chuyển thẳng giá trị đó cho thư viện mà không có allowlist, attacker có thể thử các thuật toán hoặc cách diễn giải khóa mà ứng dụng không dự kiến.

Quy tắc:

1. Cấu hình trước tập thuật toán được phép cho từng issuer và token profile.
2. Khi nhận token, đọc alg như dữ liệu chưa tin cậy.
3. Từ chối nếu alg không thuộc allowlist.
4. Chỉ chọn khóa tương thích với thuật toán đã được policy cho phép.
5. Xác minh chữ ký bằng thuật toán và khóa đã chọn.

Không dùng một cấu hình chung quá rộng cho mọi issuer hoặc mọi loại JWT chỉ vì thư viện hỗ trợ nhiều thuật toán.

### 3.2. Từ chối thuật toán none trong access token có chữ ký

Thuật toán none biểu thị JWS không có chữ ký. Với access token cần bảo vệ tính toàn vẹn, verifier phải từ chối token không có chữ ký theo profile được cấu hình.

Không bật hỗ trợ unsecured JWT chỉ để tương thích với token lạ hoặc dữ liệu thử nghiệm trong môi trường production. Nếu một giao thức đặc biệt thật sự cần JWT không chữ ký, nó phải có profile, trust boundary và endpoint tách biệt; không dùng chung validator với access token đã ký.

### 3.3. Không trộn HMAC và chữ ký bất đối xứng tùy tiện

HMAC như HS256 dùng cùng một secret để ký và xác minh. Bên nào có secret đều có khả năng tạo token mới.

Chữ ký bất đối xứng như RS256, PS256 hoặc ES256 dùng private key để ký và public key để xác minh. Resource server có thể chỉ giữ public key, giảm số thành phần có khả năng phát hành token.

Các rủi ro khi trộn thuật toán:

- Một public key bị diễn giải nhầm thành HMAC secret.
- Một validator cho phép cùng key được dùng với nhiều thuật toán không tương thích.
- Một dịch vụ chỉ cần quyền verify nhưng lại giữ secret có khả năng sign.
- Cấu hình key rotation hoặc phân phối khóa không nhất quán.

RFC 8725 yêu cầu thuật toán phải được kiểm tra rõ ràng và mỗi khóa chỉ được dùng với đúng một thuật toán. Nếu dùng HMAC, secret phải được sinh ngẫu nhiên đủ mạnh, bảo vệ như signing key và không dùng mật khẩu người dùng làm khóa.

### 3.4. Chọn thuật toán theo policy mật mã

Không có một thuật toán phù hợp cho mọi hệ thống. Lựa chọn cần xét:

- Chuẩn mật mã được tổ chức phê duyệt.
- Khả năng tương thích giữa issuer và mọi resource server.
- Kích thước khóa và mức an toàn.
- Hiệu năng, thiết bị và môi trường triển khai.
- Khả năng rotate và thu hồi khóa.
- Yêu cầu của token profile.

Ví dụ các thuật toán chữ ký thường gặp:

| Thuật toán | Nhóm | Điểm cần cấu hình |
| --- | --- | --- |
| RS256 | RSA PKCS#1 v1.5 với SHA-256 | RSA key phù hợp; không dùng cùng key như HMAC secret. |
| PS256 | RSA-PSS với SHA-256 | Cấu hình chính xác padding/PSS parameters theo chuẩn. |
| ES256 | ECDSA với P-256 và SHA-256 | Chỉ chấp nhận curve và key type phù hợp. |
| HS256 | HMAC với SHA-256 | Secret ngẫu nhiên tối thiểu 256 bit và kiểm soát chặt nơi giữ secret. |

Bảng chỉ là ví dụ kỹ thuật. Hãy dùng thuật toán nằm trong chính sách mật mã hiện hành của tổ chức và được hỗ trợ đúng bởi profile đang triển khai.

### 3.5. Độ mạnh của khóa cũng phải được kiểm tra

Allowlist alg không đủ nếu khóa quá yếu hoặc sai loại.

- RSA cần kích thước khóa đáp ứng yêu cầu chuẩn và chính sách hiện hành; RFC 7518 quy định mức tối thiểu 2048 bit cho các thuật toán RSA JWA liên quan.
- HMAC cần secret có entropy đủ lớn; với HS256, khóa phải có ít nhất 256 bit.
- ECDSA cần đúng curve tương ứng với thuật toán, không chấp nhận curve tùy ý.
- Không dùng khóa mã hóa để xác minh chữ ký.
- Không chấp nhận khóa có tham số thiếu, sai định dạng hoặc không hợp lệ về mật mã.

Không tự hạ mức kiểm tra chỉ để chấp nhận một khóa cũ. Hãy xử lý việc thay khóa theo kế hoạch migration.

## 4. Gắn mỗi khóa với đúng issuer và thuật toán

Khi dùng JWKS, verifier không nên chọn khóa chỉ dựa trên kid. Key lookup cần có ngữ cảnh issuer, token profile và thuật toán.

### 4.1. kid chỉ là định danh chọn ứng viên

JOSE header có thể chứa:

~~~json
{
  "alg": "RS256",
  "kid": "billing-signing-2026-01"
}
~~~

Verifier dùng kid để tìm ứng viên trong JWKS đã được gắn với issuer tin cậy. kid không chứng minh nguồn phát hành và không làm cho một khóa ngoài trust store trở nên hợp lệ.

Hai issuer có thể cùng dùng kid = key-01. Vì vậy, cache/key lookup cần namespace theo issuer:

~~~text
key lookup = (trusted issuer, token profile, kid, allowed algorithm)
~~~

Không dùng một map toàn cục chỉ theo kid cho nhiều issuer.

### 4.2. Kiểm tra thuộc tính JWK

Khi JWK công bố các thuộc tính sau, verifier cần kiểm tra theo policy:

| Thuộc tính | Điều cần xác minh |
| --- | --- |
| kty | Loại khóa tương thích với thuật toán. |
| kid | Khớp khóa ứng viên theo issuer/JWKS đã chọn. |
| use | Nếu có, phải phù hợp với mục đích chữ ký, thường là sig. |
| key_ops | Nếu có, phải cho phép verify. |
| alg | Nếu có, phải khớp thuật toán được policy cho phép. |
| crv | Với EC, curve phải đúng thuật toán. |
| n, e | Với RSA, tham số khóa công khai phải hợp lệ và đủ mạnh. |

Nếu nhiều khóa cùng kid tạo ra lựa chọn nhập nhằng, không chọn tùy tiện. Từ chối hoặc xử lý theo một quy tắc xác định rõ, có thể kiểm toán.

### 4.3. Một khóa chỉ dùng với một thuật toán

RFC 8725 khuyến nghị mỗi khóa chỉ được dùng với một thuật toán. Không dùng cùng một key pair cho HS256 và RS256, hoặc cho nhiều thuật toán khác nhau chỉ vì thư viện cho phép.

Nếu cần thay thuật toán:

1. Tạo hoặc chọn khóa phù hợp cho thuật toán mới.
2. Gán kid mới.
3. Publish public key mới trong JWKS.
4. Cập nhật allowlist và verifier.
5. Chuyển issuer sang ký bằng khóa/thuật toán mới.
6. Giữ khóa cũ trong thời gian overlap phù hợp với token còn hiệu lực.
7. Loại khóa cũ sau khi token cũ hết hạn và cache đã cập nhật.

Không đổi ý nghĩa của một kid đang được cache bằng cách gắn nó với khóa hoặc thuật toán khác.

### 4.4. Không lấy khóa từ token

Không tự động fetch jku hoặc x5u từ JOSE header do token gửi. Không tin JWK nhúng trong header như trust anchor. Nguồn khóa phải đến từ cấu hình hoặc metadata/JWKS đã được xác minh theo issuer tin cậy.

## 5. Required claims: phải định nghĩa theo token profile

Theo RFC 7519, các registered claims như iss, sub, aud, exp, nbf, iat và jti nhìn chung là tùy chọn ở cấp định dạng JWT. Một profile hoặc ứng dụng cụ thể có thể yêu cầu một tập claim bắt buộc.

Do đó, không nên có một danh sách required claims duy nhất áp dụng cho mọi JWT. Cần xác định token profile trước, rồi cấu hình claim bắt buộc và ngữ nghĩa tương ứng.

### 5.1. Ví dụ các profile khác nhau

| Token profile | Claims/headers cần chú ý | Mục đích |
| --- | --- | --- |
| JWT Access Token theo RFC 9068 | iss, exp, aud, sub, client_id, iat, jti; typ at+jwt | Resource server xác minh access token. |
| OIDC ID Token | iss, sub, aud, exp, iat; nonce khi authentication request có gửi nonce; các kiểm tra OIDC khác | OIDC client xác minh kết quả đăng nhập. |
| DPoP Proof theo RFC 9449 | typ dpop+jwt; jti, htm, htu, iat; ath khi proof đi cùng access token tại resource server; nonce khi được yêu cầu | Chứng minh quyền sở hữu key cho request. |
| JWT nội bộ của ứng dụng | Theo hợp đồng riêng, thường gồm iss, aud, exp và định danh subject | Trao đổi context giữa các thành phần được tin cậy. |

Bảng này giúp định hướng, không thay thế đặc tả đầy đủ của từng profile. Ví dụ, access token theo RFC 9068 có tập claim bắt buộc riêng; không được lấy tập đó áp dụng nguyên xi cho OIDC ID Token hoặc DPoP proof.

### 5.2. Cấu hình required claims phải có ý nghĩa

Ví dụ một resource server chỉ nhận JWT access token theo RFC 9068:

~~~yaml
token_profile: oauth_jwt_access_token
required_header:
  typ: at+jwt
required_claims:
  - iss
  - exp
  - aud
  - sub
  - client_id
  - iat
  - jti
expected_issuer: https://identity.example.test
expected_audience: https://api.example.test/billing
~~~

Đây là cấu hình minh họa. Ứng dụng cần xác minh toàn bộ yêu cầu RFC 9068, bao gồm chữ ký, kiểu dữ liệu, thuật toán, issuer, audience và các quy tắc thời gian.

### 5.3. Không nhầm claim có mặt với claim hợp lệ

Một thư viện có thể hỗ trợ danh sách required claims và chỉ kiểm tra key tồn tại. Điều đó chưa đủ.

Ví dụ:

~~~json
{
  "iss": 123,
  "sub": {},
  "aud": [],
  "exp": "tomorrow",
  "iat": -1
}
~~~

Các trường có thể xuất hiện nhưng sai kiểu hoặc giá trị. Validator phải kiểm tra:

- Claim có mặt khi profile yêu cầu.
- Kiểu JSON đúng.
- Giá trị không rỗng nếu profile yêu cầu.
- Ngữ nghĩa phù hợp.
- Quan hệ giữa các claim hợp lệ.

## 6. Kiểm tra issuer và audience một cách chính xác

### 6.1. Issuer phải khớp chính xác

Issuer xác định không gian định danh và bên phát hành token. Không so khớp issuer bằng prefix, substring hoặc domain suffix.

Nếu cấu hình mong đợi:

~~~text
https://identity.example.test
~~~

thì các giá trị sau là issuer khác:

~~~text
https://identity.example.test/tenant-a
https://identity.example.test.attacker.example
https://attacker.example/identity.example.test
~~~

Verifier nên nhận issuer dự kiến từ trust registry/cấu hình đã phê duyệt. Không dùng iss chưa xác minh làm URL tự do để fetch Discovery hoặc JWKS.

### 6.2. Audience phải dành cho recipient hiện tại

Audience có thể là string hoặc array theo JWT. Verifier phải kiểm tra identifier của chính resource server theo profile:

~~~text
expected audience = https://api.example.test/billing
~~~

Không chấp nhận token chỉ vì audience có cùng hostname hoặc prefix. Không coi scope thay thế audience.

### 6.3. Không bỏ qua audience khi có Gateway

Token dành cho API Gateway không tự động dành cho backend. Backend phải có audience riêng hoặc nhận token/assertion được cấp cho nó theo một cơ chế tin cậy rõ ràng, chẳng hạn OAuth Token Exchange.

### 6.4. Kiểm tra kiểu dữ liệu aud

Verifier cần xử lý đúng StringOrURI hoặc mảng audience theo profile. Nếu profile yêu cầu một audience duy nhất, phải từ chối trường hợp không đáp ứng. Không chuyển mọi kiểu JSON thành chuỗi rồi so sánh.

## 7. Cấu hình thời gian và vòng đời claims

### 7.1. exp là điều kiện bắt buộc theo profile

Nếu profile yêu cầu exp, token thiếu exp phải bị từ chối. Không tự coi token thiếu exp là không hết hạn.

exp là NumericDate, biểu diễn thời gian theo số giây kể từ epoch. Không chấp nhận string ngày giờ hoặc kiểu số không hợp lệ chỉ vì thư viện có thể chuyển đổi.

### 7.2. nbf và clock skew

Nếu token có nbf, verifier không chấp nhận token trước thời điểm này, trừ sai lệch đồng hồ nhỏ được policy cho phép.

Clock skew phải được cấu hình rõ và giữ ở mức hợp lý. Một cửa sổ quá rộng có thể kéo dài thời gian chấp nhận token hết hạn hoặc chưa có hiệu lực.

### 7.3. iat và token age

iat cho biết thời điểm phát hành. Nếu profile yêu cầu, claim phải có kiểu NumericDate và không được nằm quá xa trong tương lai so với clock skew.

Một số hệ thống còn giới hạn tuổi tối đa của token, ví dụ:

~~~text
now - iat <= maximum_token_age
~~~

Đây là chính sách bổ sung của ứng dụng; không nhầm nó với exp. Một token có thể chưa hết hạn nhưng vẫn quá cũ theo yêu cầu của một thao tác nhạy cảm.

### 7.4. jti không tự chống replay

jti là định danh token. Chỉ yêu cầu jti xuất hiện không làm token one-time và không tự ngăn replay.

Nếu cần phát hiện token đã được sử dụng, server phải duy trì trạng thái hoặc dùng cơ chế sender-constrained/proof-of-possession phù hợp. Với access token bearer thông thường, không giả định jti tự tạo ra replay protection.

## 8. Kiểm tra kiểu dữ liệu và schema của claims

Một token profile nên định nghĩa schema cho từng claim được sử dụng.

| Claim | Kiểu thường gặp | Kiểm tra cần thiết |
| --- | --- | --- |
| iss | String | So khớp chính xác issuer được tin cậy. |
| sub | String | Không rỗng; ánh xạ principal theo issuer. |
| aud | String hoặc array of strings | Kiểm tra recipient theo profile. |
| exp, nbf, iat | NumericDate | Kiểu số hợp lệ và quy tắc thời gian. |
| jti | String | Định dạng/độ dài theo policy; có trạng thái replay nếu cần. |
| client_id | String | Khớp client/grant theo profile. |
| scope | String trong OAuth access token profile | Parse theo quy tắc scope; không dùng substring. |
| roles | Thường là array theo hợp đồng ứng dụng | Chỉ chấp nhận giá trị đã định nghĩa; kiểm tra namespace/phạm vi. |
| permissions | Array hoặc cấu trúc theo hợp đồng | Kiểm tra từng permission và nguồn thẩm quyền. |
| tenant_id | String hoặc định danh theo schema | Đối chiếu membership và resource hiện hành. |

### 8.1. Không dùng ép kiểu dễ dãi

Không tự chuyển:

- Số thành string.
- String thành boolean.
- Object thành array.
- Giá trị null thành giá trị mặc định có quyền.

Ví dụ, nếu policy yêu cầu scope là chuỗi phân tách bằng khoảng trắng, một mảng JSON scope không nên được chấp nhận trừ khi profile của ứng dụng định nghĩa rõ dạng đó.

### 8.2. Parse scope theo phần tử chính xác

Không kiểm tra scope bằng substring:

~~~text
if "invoice:read" appears anywhere in scope:
    allow
~~~

Một giá trị invoice:read-all hoặc x-invoice:read không nên bị nhầm với scope invoice:read.

Hãy parse scope thành các phần tử theo đúng profile rồi so sánh phần tử chính xác. Tương tự, không tìm role bằng chuỗi con trong một chuỗi JSON tùy ý.

### 8.3. Claim tùy chỉnh cần namespace và chủ sở hữu

Các claim như tenant_id, department, risk_level, roles hoặc permissions là quy ước ứng dụng. Cần định nghĩa:

- Issuer nào có thẩm quyền phát hành?
- Claim áp dụng toàn cục, theo tenant hay theo resource?
- Kiểu và miền giá trị hợp lệ là gì?
- Claim có thể thay đổi nhanh đến mức nào?
- Có cần đối chiếu dữ liệu hiện hành không?
- API nào được phép dùng claim đó để quyết định?

Không tự coi claim tùy chỉnh là đáng tin chỉ vì nó nằm trong JWT có chữ ký hợp lệ.

### 8.4. Xử lý JSON member trùng lặp

JWT payload và JOSE header là JSON. JSON object có thể gặp tên member trùng lặp trong dữ liệu lỗi hoặc cố ý được tạo để khai thác khác biệt giữa parser.

Các parser có thể diễn giải member trùng lặp khác nhau, ví dụ dùng giá trị đầu tiên hoặc cuối cùng. Sự khác biệt này có thể khiến thành phần xác minh và thành phần sử dụng claims hiểu token khác nhau.

Theo hướng dẫn JWT BCP, parser nên từ chối JSON có member trùng lặp hoặc bảo đảm mọi thành phần sử dụng cùng một quy tắc rõ ràng. Với dữ liệu bảo mật, từ chối cấu trúc nhập nhằng là lựa chọn an toàn hơn.

## 9. Cấu hình JOSE header và token profile

Không chỉ payload claims cần được kiểm tra. JOSE header cũng phải tuân theo policy.

### 9.1. typ

typ giúp phân biệt token profile. Ví dụ JWT access token theo RFC 9068 dùng at+jwt; DPoP proof dùng dpop+jwt.

Nếu profile yêu cầu typ, verifier phải kiểm tra đúng giá trị. Không chấp nhận typ chỉ vì token tự khai báo; chữ ký và issuer vẫn phải được xác minh.

### 9.2. kid

kid dùng chọn key trong JWKS đã được tin cậy. Nếu thiếu kid và có nhiều key phù hợp, không chọn key đầu tiên. Nếu kid không tồn tại, refresh JWKS theo cơ chế có giới hạn rồi từ chối nếu vẫn không tìm được key.

### 9.3. crit

JOSE header parameter crit chỉ ra extension quan trọng mà verifier phải hiểu và xử lý. Nếu token có crit chứa extension mà thư viện hoặc ứng dụng không hỗ trợ, phải từ chối token. Không bỏ qua crit rồi tiếp tục xác minh như thể extension không tồn tại.

### 9.4. jku, x5u và jwk

Không tự động tải key theo URL jku hoặc x5u do token cung cấp. Không dùng JWK nhúng trong header như trust anchor. Chỉ dùng nguồn khóa đã được liên kết với issuer theo trust policy.

### 9.5. cty và nested JWT

cty mô tả content type của nội dung được bảo vệ bên trong, có thể liên quan nested JWT/JWE. Không dùng cty thay typ để phân biệt access token với ID Token.

Nếu ứng dụng hỗ trợ nested JWT, phải định nghĩa rõ:

- Lớp ngoài là JWE hay JWS.
- Lớp trong là loại JWT nào.
- Thứ tự decrypt/verify.
- Issuer, audience và profile nào áp dụng cho từng lớp.
- Thuật toán mã hóa và chữ ký được allowlist ra sao.

Không tự động chấp nhận mọi cấu trúc lồng nhau mà thư viện có thể parse.

## 10. Một token profile, một validator chuyên biệt

RFC 8725 khuyến nghị các loại JWT có bộ quy tắc xác minh loại trừ lẫn nhau để token hợp lệ trong profile này không thể được dùng ở profile khác.

Ví dụ:

~~~text
validateBillingAccessToken(...)
validateOidcIdToken(...)
validateDpopProof(...)
validateOAuthClientAssertion(...)
validateLogoutToken(...)
~~~

Đây là tên khái niệm. Điều quan trọng là mỗi validator có cấu hình riêng về issuer, audience, algorithm, typ, required claims, thời gian và các điều kiện đặc thù.

### 10.1. Không có validateAnyJwt cho mọi endpoint

Một hàm tổng quát chỉ xác minh chữ ký rồi trả claims có thể bị dùng sai ở endpoint khác. Nếu endpoint không biết token profile, nó không thể áp dụng đầy đủ các điều kiện cần thiết.

Endpoint phải xác định trước loại token mà nó nhận. Request không được tự chọn validator bằng một claim chưa xác minh.

### 10.2. Không dùng chung cấu hình chỉ vì issuer giống nhau

Cùng một issuer có thể phát hành:

- OIDC ID Token cho client.
- OAuth access token cho resource server.
- Client assertion cho token endpoint.
- Logout token cho back-channel logout.
- DPoP proof do client tạo.

Chúng có thể khác audience, typ, key policy và claims. Cùng issuer không đồng nghĩa cùng mục đích.

### 10.3. Dedicated signing keys là lớp phòng vệ bổ sung

Issuer có thể dùng key pair riêng cho các profile khác nhau. Điều đó giúp giảm nguy cơ cross-JWT confusion, nhưng không thay thế issuer/audience/type validation.

Nếu verifier chấp nhận sai audience hoặc sai typ, việc dùng key riêng cũng không sửa được logic validator yếu.

## 11. Cấu hình mẫu hoàn chỉnh cho JWT Access Token

Ví dụ dưới đây là cấu hình khái niệm cho một Billing API nhận access token theo RFC 9068. Tên trường là quy ước minh họa, không phải schema của một thư viện cụ thể.

~~~yaml
jwt_validation:
  profile: oauth_jwt_access_token
  enabled: true

  issuer:
    expected: https://identity.example.test
    discovery_source: trusted_issuer_registry
    exact_match: true

  audience:
    expected:
      - https://api.example.test/billing
    match_mode: exact_membership
    reject_unexpected_multi_audience: true

  signature:
    required: true
    allowed_algorithms:
      - RS256
    reject_none: true
    require_algorithm_key_binding: true
    minimum_rsa_bits: 2048

  jwks:
    source: issuer_verified_metadata
    allowed_hosts:
      - identity.example.test
    require_https: true
    cache_ttl_seconds: 300
    unknown_kid_refresh_rate_limited: true

  jose_header:
    required_typ: at+jwt
    reject_unsupported_critical_headers: true
    reject_untrusted_key_urls: true

  required_claims:
    - iss
    - exp
    - aud
    - sub
    - client_id
    - iat
    - jti

  claim_types:
    iss: string
    sub: non_empty_string
    aud: string_or_array_of_strings
    exp: numeric_date
    iat: numeric_date
    jti: non_empty_string
    client_id: non_empty_string
    scope: space_delimited_string

  time:
    clock_skew_seconds: 30
    reject_future_iat_beyond_skew: true
    maximum_token_age_seconds: 900

  parsing:
    reject_duplicate_json_members: true
    reject_malformed_base64url: true
    reject_unknown_profile_extensions: true

  failure:
    invalid_signature: reject
    invalid_issuer: reject
    invalid_audience: reject
    missing_required_claim: reject
    wrong_claim_type: reject
    unsupported_algorithm: reject
    unknown_key_after_refresh: reject
    metadata_or_jwks_unavailable: reject_unless_trusted_cache_policy_allows
~~~

Các giá trị như TTL, clock skew và maximum token age phải được chọn theo threat model và thời hạn token thực tế. Không sao chép nguyên các con số ví dụ vào production mà không đánh giá.

### 11.1. Tách cấu hình theo môi trường

Issuer, audience, key set và thuật toán của development, staging và production cần được quản lý riêng. Không để production vô tình chấp nhận token hoặc khóa thử nghiệm.

### 11.2. Không để cấu hình runtime từ request ghi đè policy

Client không được gửi tham số như allowed_algorithms, expected_issuer hoặc required_claims để thay đổi validator. Những giá trị đó phải đến từ cấu hình được quản trị và triển khai có kiểm soát.

## 12. Pipeline xác minh trong quá trình tích hợp thư viện

Một quy trình xác minh có thứ tự rõ ràng:

~~~mermaid
flowchart TD
    A["Endpoint nhận credential"] --> B["Chọn token profile theo endpoint"]
    B --> C["Lấy issuer từ trust configuration"]
    C --> D["Lấy metadata/JWKS đã xác minh"]
    D --> E["Parse compact JWT có giới hạn"]
    E --> F["Kiểm tra JOSE header theo allowlist"]
    F --> G["Chọn key tương thích issuer/kid/alg"]
    G --> H["Xác minh chữ ký"]
    H --> I["Kiểm tra iss và aud"]
    I --> J["Kiểm tra typ và required claims"]
    J --> K["Kiểm tra kiểu dữ liệu và thời gian"]
    K --> L["Tạo verified principal"]
    L --> M["Authorization trên action/resource"]
    M --> N["ALLOW hoặc DENY"]
~~~

### 12.1. Giới hạn kích thước và định dạng đầu vào

Trước khi parse, giới hạn:

- Tổng kích thước compact JWT.
- Kích thước header và payload.
- Độ dài kid và các trường string.
- Số lượng phần tử trong array claims.
- Độ sâu JSON nếu parser có giới hạn.
- Kích thước JWKS response và số lượng JWK.

Điều này giảm nguy cơ tiêu thụ CPU/bộ nhớ hoặc tạo dữ liệu bất thường để làm parser lỗi.

### 12.2. Parse không đồng nghĩa verify

Thư viện thường có thao tác decode/parse không xác minh chữ ký. Không dùng kết quả đó làm principal, role hoặc permission.

Các claims chỉ được đưa vào luồng authorization sau khi token vượt qua toàn bộ validation profile. Nếu ứng dụng cần đọc header trước để chọn key, coi header là dữ liệu chưa tin cậy và chỉ dùng nó trong phạm vi allowlist đã cấu hình.

### 12.3. Không tạo principal một phần

Nếu signature hợp lệ nhưng audience sai, không tạo principal authenticated. Nếu token thiếu claim bắt buộc hoặc sai profile, không để một phần claims được dùng ở tầng nghiệp vụ.

Kết quả xác minh nên có trạng thái rõ: verified token theo profile cụ thể hoặc reject. Không trả object principal chưa hoàn chỉnh khi validation thất bại.

## 13. Pseudocode: xác minh theo cấu hình tường minh

~~~text
function validateAccessToken(compactJwt, endpointProfile):
    profile = trustedValidationConfig.get(endpointProfile)
    if profile is null or not profile.enabled:
        return REJECT

    if compactJwt is empty or size(compactJwt) > profile.maxTokenBytes:
        return REJECT

    header = parseUntrustedJoseHeader(compactJwt)
    if header.alg not in profile.signature.allowedAlgorithms:
        return REJECT
    if header.alg == "none" and profile.signature.required:
        return REJECT
    if profile.joseHeader.requiredTyp exists
       and header.typ != profile.joseHeader.requiredTyp:
        return REJECT
    if containsUnsupportedCriticalHeader(header.crit):
        return REJECT

    issuer = profile.issuer.expected
    key = trustedKeyStore.find(
        issuer = issuer,
        kid = header.kid,
        algorithm = header.alg,
        profile = profile.name
    )
    if key is null:
        key = refreshTrustedJwksWithRateLimit(issuer, profile)
    if key is null:
        return REJECT

    if not keyCompatibleWithAlgorithm(key, header.alg):
        return REJECT
    if not verifySignature(compactJwt, key, header.alg):
        return REJECT

    claims = parseVerifiedClaims(compactJwt)
    if not hasAllRequiredClaims(claims, profile.requiredClaims):
        return REJECT
    if not claimsMatchDeclaredTypes(claims, profile.claimTypes):
        return REJECT
    if claims.iss != profile.issuer.expected:
        return REJECT
    if not exactAudienceMatch(claims.aud, profile.audience.expected):
        return REJECT
    if not validTimeClaims(claims, profile.time):
        return REJECT
    if not profileSpecificRulesPass(header, claims, profile):
        return REJECT

    return VERIFIED_TOKEN(
        profile = profile.name,
        issuer = claims.iss,
        subject = claims.sub,
        claims = claims
    )
~~~

Đây là pseudocode mô tả hợp đồng tích hợp, không phải API của thư viện cụ thể. Trong thực tế, phải dùng đúng cơ chế xác minh chữ ký và claim validation của thư viện đã được kiểm chứng; không tự viết thuật toán mật mã hoặc so sánh chữ ký bằng thao tác chuỗi.

## 14. Ánh xạ lỗi thư viện thành kết quả an toàn

Thư viện có thể trả nhiều loại lỗi:

- Token malformed.
- Unsupported algorithm.
- Key not found.
- Signature invalid.
- Issuer mismatch.
- Audience mismatch.
- Expired/not-yet-valid.
- Missing claim.
- Claim type invalid.
- Unsupported critical header.
- JWKS/network failure.

Ứng dụng nên ánh xạ chúng thành các nhóm kết quả rõ ràng:

| Nhóm | Hành vi |
| --- | --- |
| Invalid credential | Từ chối request xác thực; không tạo principal. |
| Invalid token profile | Từ chối token vì sai loại hoặc sai ngữ nghĩa. |
| Trust configuration error | Từ chối và cảnh báo vận hành; không tự mở rộng trust. |
| Key source unavailable | Dùng cache chỉ khi policy cho phép và khóa đã được tin trước đó; nếu không thì từ chối. |
| Internal validation error | Không biến lỗi thành ALLOW; ghi nhận an toàn và trả lỗi phù hợp. |

### 14.1. Không bắt lỗi rồi bỏ qua

Mẫu xử lý nguy hiểm:

~~~text
try:
    verify(token)
catch any_error:
    continue_request()
~~~

Lỗi xác minh phải dẫn tới từ chối hoặc trạng thái lỗi có kiểm soát. Không tiếp tục request bằng claims đã decode trước đó.

### 14.2. Không tiết lộ quá nhiều chi tiết cho caller

Phản hồi công khai nên tránh tiết lộ:

- Issuer nội bộ được tin cậy.
- kid nào đang được dùng.
- Cấu trúc key store.
- Chi tiết lỗi chữ ký.
- Sự tồn tại của subject hoặc grant.

Chi tiết kỹ thuật nên được ghi trong audit/log bảo vệ, có correlation ID và không chứa raw token.

## 15. Key rotation và thay đổi allowlist

Thay đổi thuật toán hoặc khóa cần được triển khai theo một quy trình có kiểm soát.

### 15.1. Rotation bình thường

~~~text
1. Tạo key pair mới phù hợp thuật toán mới/đang dùng.
2. Publish public key mới vào JWKS.
3. Resource server refresh và xác minh key mới.
4. Issuer bắt đầu ký token mới bằng key mới.
5. Token cũ tiếp tục được xác minh trong overlap đã định.
6. Token cũ hết hạn.
7. Loại public key cũ khỏi JWKS và cache theo policy.
~~~

### 15.2. Migration thuật toán

Nếu chuyển từ RS256 sang PS256:

- Thêm thuật toán mới vào allowlist theo một release có kiểm soát.
- Publish key tương thích với PS256 và kid mới.
- Xác minh mọi resource server hỗ trợ đúng thuật toán.
- Chuyển issuer sang ký bằng thuật toán mới.
- Theo dõi token cũ/new algorithm.
- Gỡ thuật toán cũ sau khi token cũ hết hạn và các client liên quan đã chuyển đổi.

Không giữ allowlist rộng vô thời hạn để tương thích. Không dùng cùng một key với nhiều thuật toán trong thời gian migration nếu điều đó trái với key policy.

### 15.3. Khóa bị compromise

Nếu signing key bị lộ:

- Ngừng ký bằng khóa đó.
- Đưa kid vào emergency deny policy.
- Thu hồi hoặc rotate khóa.
- Buộc resource server refresh/invalid cache theo cơ chế khẩn cấp.
- Đánh giá token đã phát hành.
- Ghi audit và điều tra phạm vi ảnh hưởng.

Chỉ xóa key khỏi JWKS có thể chưa đủ nếu resource server còn cache khóa cũ.

## 16. Kiểm thử cấu hình thuật toán và claims

Kiểm thử phải chứng minh token hợp lệ được chấp nhận và token sai profile bị từ chối. Dùng token có chữ ký hợp lệ nhưng sai audience/type/claim là cách quan trọng để phát hiện validator yếu.

### 16.1. Algorithm tests

~~~text
Token dùng thuật toán trong allowlist, key phù hợp
    -> có thể tiếp tục validation

Token dùng thuật toán ngoài allowlist
    -> reject

Token dùng alg = none
    -> reject

Token dùng HS256 khi profile chỉ cho RS256
    -> reject

Token dùng key type không tương thích với alg
    -> reject

RSA key yếu hơn policy
    -> reject

JWK có use = enc hoặc key_ops không có verify
    -> reject

Cùng kid nhưng issuer khác
    -> không dùng chéo key
~~~

### 16.2. Required claims tests

- Thiếu iss.
- Thiếu aud.
- Thiếu exp.
- Thiếu sub hoặc client_id trong profile yêu cầu.
- Thiếu iat hoặc jti trong profile yêu cầu.
- Claim xuất hiện nhưng sai kiểu.
- NumericDate là string hoặc giá trị không hợp lệ.
- Scope là object/array khi profile yêu cầu string.
- Scope có chuỗi con gần giống nhưng không có phần tử chính xác.
- Claim tùy chỉnh có giá trị ngoài miền cho phép.

### 16.3. Issuer và audience tests

- Issuer đúng.
- Issuer khác nhưng cùng hostname.
- Issuer giả có prefix/suffix gần giống.
- Audience là string đúng.
- Audience array có recipient theo profile.
- Audience chỉ chứa API khác.
- Audience có path khác.
- Token cho Gateway được gửi tới backend.

### 16.4. JOSE header tests

- typ đúng profile.
- typ sai hoặc thiếu trong profile bắt buộc.
- crit chứa extension không hỗ trợ.
- kid không tồn tại.
- kid trùng nhiều JWK gây nhập nhằng.
- jku/x5u trỏ tới host không tin cậy.
- JWK nhúng chứa private key material.
- Header quá lớn hoặc sai định dạng.

### 16.5. Time and parser tests

- Token hết hạn.
- Token chưa tới nbf.
- iat nằm quá xa trong tương lai.
- Token quá tuổi tối đa theo policy.
- JSON header/payload có member trùng.
- Base64url malformed.
- Payload quá lớn hoặc JSON quá sâu.
- Clock skew ở biên cho phép và ngoài biên.

### 16.6. Profile separation tests

- ID Token hợp lệ được gửi tới access-token validator.
- Access Token hợp lệ được gửi tới ID Token validator.
- DPoP proof được gửi thay access token.
- Client assertion được gửi tới resource API.
- JWT nghiệp vụ được gửi tới endpoint OAuth.
- Token có cùng issuer/key nhưng sai audience và typ.

## 17. Những lỗi thường gặp

| Sai lầm | Rủi ro | Cách phòng tránh |
| --- | --- | --- |
| Dùng mặc định thư viện mà không review | Thuật toán hoặc claim validation có thể không phù hợp. | Cấu hình rõ algorithm, issuer, audience, profile và required claims. |
| Lấy alg từ token làm policy | Algorithm confusion. | Allowlist độc lập theo issuer/profile. |
| Cho phép none | Token không chữ ký được chấp nhận. | Bắt buộc chữ ký cho access token theo profile. |
| Trộn HMAC và asymmetric key | Một public key có thể bị hiểu nhầm thành secret hoặc nhiều bên có quyền ký. | Tách thuật toán, key type và quyền sign/verify. |
| Dùng một key cho nhiều thuật toán | Tăng nguy cơ confusion và sai key policy. | Một key gắn với một thuật toán. |
| Chọn key chỉ bằng kid | Dùng nhầm key của issuer khác. | Key lookup theo issuer, profile và thuật toán. |
| Chỉ kiểm tra claim có mặt | Giá trị sai kiểu hoặc sai ngữ nghĩa vẫn được chấp nhận. | Schema/type/semantic validation. |
| Áp dụng một required-claim list cho mọi JWT | Từ chối token hợp lệ hoặc chấp nhận token sai profile. | Required claims theo profile cụ thể. |
| Không kiểm tra aud | Token dành cho API khác được chấp nhận. | Audience match chính xác. |
| So khớp scope bằng substring | Quyền gần giống bị nhầm thành quyền thật. | Parse và so sánh scope theo phần tử. |
| Bỏ qua crit | Extension quan trọng không được xử lý. | Từ chối critical header không hỗ trợ. |
| Dùng decode như verify | Claims chưa xác thực được dùng để cấp quyền. | Chỉ sử dụng claims sau validation hoàn chỉnh. |
| Bắt mọi exception rồi tiếp tục | Lỗi xác minh trở thành ALLOW. | Fail closed theo policy. |
| Fetch jku/x5u từ token | SSRF hoặc attacker-controlled key. | Dùng JWKS từ issuer trust đã xác minh. |
| Không kiểm tra duplicate JSON members | Các parser có thể hiểu payload khác nhau. | Từ chối JSON nhập nhằng hoặc chuẩn hóa parser thống nhất. |
| Không kiểm thử token hợp lệ nhưng sai profile | Cross-JWT confusion không bị phát hiện. | Negative tests theo issuer, audience, typ và claims. |

## 18. Checklist tích hợp JWT library

Trước khi đưa validator vào production, hãy trả lời:

1. **Profile:** endpoint nhận loại JWT nào và profile chuẩn nào áp dụng?
2. **Library behavior:** thao tác nào chỉ decode, thao tác nào thực sự verify?
3. **Algorithm allowlist:** thuật toán nào được phép; có từ chối none và thuật toán ngoài policy không?
4. **Key policy:** key type, size, curve, use, key_ops và alg có được kiểm tra không?
5. **Issuer binding:** issuer lấy từ trust registry nào và được so khớp chính xác không?
6. **Audience:** expected audience có được cấu hình theo recipient hiện tại không?
7. **Required claims:** danh sách bắt buộc có xuất phát từ đúng profile không?
8. **Claim schema:** kiểu, miền giá trị và quan hệ giữa claims có được kiểm tra không?
9. **JOSE header:** typ, kid, crit và key URL parameters có policy rõ không?
10. **Time:** exp, nbf, iat, clock skew và maximum token age có được cấu hình không?
11. **Key source:** JWKS có gắn với issuer; unknown kid refresh có rate limit không?
12. **Profile separation:** ID Token, access token, DPoP proof và assertion có validator riêng không?
13. **Failure behavior:** missing claim, wrong type, key source failure và internal error có fail closed không?
14. **Logging:** log có tránh raw token và secret không?
15. **Rotation:** thay key/algorithm có overlap, cache invalidation và emergency revoke không?
16. **Testing:** có positive/negative test cho alg, key, iss, aud, typ, claims, time và parser không?
17. **Review:** cấu hình bảo mật có được review và version control như code không?

## 19. Ghi nhớ trọng tâm

- Decode JWT không phải xác minh JWT. Chỉ dùng claims sau khi token vượt qua validation profile hoàn chỉnh.
- Thuật toán phải được cấu hình bằng allowlist độc lập với JOSE header; từ chối thuật toán ngoài policy và none trong access token đã ký.
- Mỗi khóa cần được gắn với đúng issuer, key type và một thuật toán theo key policy.
- Required claims phải được xác định theo token profile; RFC 7519 không biến mọi registered claim thành bắt buộc cho mọi JWT.
- Claim có mặt vẫn cần đúng kiểu, miền giá trị và ngữ nghĩa.
- Kiểm tra issuer và audience chính xác; không dùng prefix, substring hoặc scope thay cho audience.
- typ, crit, kid và các JOSE header khác cần được xử lý theo profile và trust policy.
- Dùng validator chuyên biệt với mutually exclusive validation rules cho ID Token, access token, DPoP proof, client assertion và token nghiệp vụ.
- Cấu hình thời gian, JWKS cache, unknown-kid refresh và key rotation phải có giới hạn rõ.
- Lỗi xác minh hoặc thiếu bằng chứng không được biến thành ALLOW; không ghi raw token vào log.

**Tài liệu tham khảo kỹ thuật:** RFC 7519 (JSON Web Token); RFC 7515 (JSON Web Signature); RFC 7517 (JSON Web Key); RFC 7518 (JSON Web Algorithms); RFC 7638 (JSON Web Key Thumbprint); RFC 8725 (JSON Web Token Best Current Practices); RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens); OpenID Connect Core 1.0; RFC 9449 (OAuth 2.0 Demonstrating Proof of Possession). Các chuẩn này xác định định dạng JWT, thuật toán, key và token profile; cấu hình thư viện cần hiện thực đúng trust policy và yêu cầu của profile mà ứng dụng chấp nhận.
