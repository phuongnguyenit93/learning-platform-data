# Token hợp lệ theo từng thuật toán và từng hồ sơ được hỗ trợ

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Kiểm thử bảo mật. Bài viết tập trung vào kiểm thử JWT độc lập với ngôn ngữ lập trình, nền tảng hoặc framework.

## 1. Mục tiêu: chứng minh đúng tổ hợp thuật toán và token profile được chấp nhận

Một JWT chỉ được xem là hợp lệ khi đồng thời đáp ứng các điều kiện của thuật toán, khóa, nguồn phát hành, token profile và ngữ cảnh sử dụng. Chữ ký đúng là một điều kiện quan trọng, nhưng chưa đủ để kết luận token có thể được chấp nhận.

Ví dụ, một JWS có chữ ký RS256 hợp lệ vẫn phải bị từ chối nếu issuer không nằm trong danh sách tin cậy, public key không thuộc JWKS đã gắn với issuer, audience không dành cho resource server hiện tại, token hết hạn, typ hoặc claim không phù hợp loại token mà endpoint đang chờ, hoặc thuật toán không nằm trong policy của endpoint.

Bài kiểm thử cần trả lời hai câu hỏi:

1. Với mỗi thuật toán mà hệ thống tuyên bố hỗ trợ, token được ký đúng cách và dùng khóa phù hợp có được xác minh thành công không?
2. Với mỗi token profile được hỗ trợ, token có đúng thuật toán, header, claim và ngữ cảnh mà profile quy định có được chấp nhận không?

Phạm vi kiểm thử là **giao điểm giữa thuật toán được bật và profile cho phép thuật toán đó**. Không phải mọi thuật toán đều phù hợp với mọi loại JWT.

## 2. Phân biệt thuật toán, định dạng và token profile

| Khái niệm | Ví dụ | Điều cần kiểm thử |
| --- | --- | --- |
| Serialization | JWS Compact, JWE Compact, JWS JSON Serialization | Số phần, encoding, cấu trúc và cách parse |
| JWS signing algorithm | HS256, RS256, PS256, ES256, EdDSA | Chữ ký, loại khóa, tham số thuật toán |
| JWE key management algorithm | RSA-OAEP-256, ECDH-ES, A256KW, dir | Cách tạo hoặc phân phối CEK |
| JWE content encryption | A128GCM, A256GCM, A128CBC-HS256 | Mã hóa, IV, authentication tag và giải mã |
| Token profile | OAuth JWT Access Token, OIDC ID Token, DPoP Proof, JWT Client Assertion | Header, claim bắt buộc, audience, issuer và ngữ cảnh |
| Trust configuration | Issuer allowlist, JWKS, certificate trust, key binding | Khóa có thực sự thuộc nguồn phát hành được tin cậy không |

Không viết một bài test chung kiểu “JWT signature valid” rồi coi đó là bằng chứng cho mọi profile. Cần test từng profile bằng validator và policy tương ứng.

Một token có thể đúng về JWS nhưng sai profile. Ví dụ, DPoP proof có chữ ký hợp lệ không phải là access token; ID Token hợp lệ không tự động là credential được phép gửi tới API.

## 3. Lập danh sách thuật toán thực sự được hỗ trợ

Trước khi viết test, xác định cấu hình đang bật ở từng issuer, endpoint và profile. Danh sách thuật toán trong tiêu chuẩn không đồng nghĩa hệ thống phải triển khai tất cả.

### 3.1. JWS signing algorithms

Các nhóm thuật toán JWS phổ biến:

| Nhóm | Giá trị thường gặp | Loại khóa | Điểm cần kiểm thử |
| --- | --- | --- | --- |
| HMAC | HS256, HS384, HS512 | Khóa đối xứng, JWK kty là oct | Độ dài khóa, cách biểu diễn bytes và xác minh MAC |
| RSA PKCS#1 v1.5 | RS256, RS384, RS512 | RSA | Kích thước modulus và đúng hash |
| RSA-PSS | PS256, PS384, PS512 | RSA | PSS padding, MGF1 và salt length |
| ECDSA | ES256, ES384, ES512 | EC | Đúng curve và chữ ký JOSE dạng R || S |
| Edwards-curve | EdDSA | OKP, ví dụ Ed25519/Ed448 nếu thư viện và profile hỗ trợ | Đúng curve, key type và thuật toán |

Một số triển khai có thể hỗ trợ thêm thuật toán được đăng ký hoặc profile chuyên biệt. Chỉ thêm chúng vào ma trận nếu sản phẩm thực sự bật và có chính sách khóa rõ ràng.

Không đưa thuật toán none vào danh sách thuật toán bảo mật cho access token, ID Token hoặc assertion cần xác thực nguồn. Test phải chứng minh token không chữ ký bị từ chối ở endpoint yêu cầu JWS đã xác thực.

### 3.2. Ràng buộc thuật toán với loại khóa

| Thuật toán | Key type/JWK thường dùng | Ràng buộc quan trọng |
| --- | --- | --- |
| HS256/HS384/HS512 | kty=oct | Khóa bí mật đủ dài theo yêu cầu thuật toán |
| RS256/RS384/RS512 | kty=RSA | RSA modulus đạt ngưỡng; chỉ dùng public key để verify |
| PS256/PS384/PS512 | kty=RSA | Đúng RSA-PSS parameters theo JWA |
| ES256 | kty=EC, crv=P-256 | Không dùng nhầm P-384/P-521 |
| ES384 | kty=EC, crv=P-384 | Đúng curve và độ dài chữ ký |
| ES512 | kty=EC, crv=P-521 | Đúng curve P-521, không nhầm với P-512 |
| EdDSA | kty=OKP, curve được profile hỗ trợ | Key curve và thuật toán phải tương thích |

Test cả trường hợp đúng và sai loại khóa. Ví dụ, không được xác minh HS256 bằng bytes của RSA public key hoặc dùng một EC key bất kỳ cho ES256.

### 3.3. Các ràng buộc mật mã cần có trong test

- Với HS256/384/512, khóa phải có độ dài tối thiểu theo RFC 7518, tương ứng ít nhất bằng độ dài đầu ra của hàm hash: 256, 384 hoặc 512 bit. Kiểm thử cả khóa đúng ngưỡng và khóa ngắn hơn.
- Với RS256/384/512 và PS256/384/512, RFC 7518 yêu cầu RSA key có modulus ít nhất 2048 bit. Không dùng khóa yếu trong fixture chấp nhận.
- Với PS256/384/512, kiểm tra đúng RSA-PSS, hash và MGF1 tương ứng; salt length theo yêu cầu JWA bằng độ dài đầu ra hash.
- Với ES256/384/512, kiểm tra đúng curve tương ứng P-256/P-384/P-521. JWS biểu diễn chữ ký ECDSA dưới dạng nối hai số nguyên R || S với độ dài cố định; không nhầm với ASN.1 DER signature thường gặp trong một số API mật mã.
- Với EdDSA, kiểm tra đúng OKP curve và thư viện hỗ trợ. Không suy luận mọi biến thể EdDSA đều được hỗ trợ chỉ vì thuật toán có tên EdDSA.
- Với mọi nhóm, xác minh chữ ký bằng public key tương ứng và bảo đảm private key không xuất hiện trong JWKS công khai hoặc log.

## 4. Ma trận thuật toán × profile

Ma trận là trung tâm của bộ kiểm thử. Hãy điền theo cấu hình thực tế, không suy ra chỉ từ khả năng của thư viện.

Ví dụ minh họa:

| Token profile | HS256 | RS256 | PS256 | ES256 | EdDSA |
| --- | --- | --- | --- | --- | --- |
| OAuth JWT Access Token | Tùy policy/client | Bật | Bật nếu cấu hình | Bật nếu cấu hình | Bật nếu cấu hình |
| OIDC ID Token | Theo quy tắc OP/client | Bật theo cấu hình | Theo cấu hình | Theo cấu hình | Theo cấu hình |
| DPoP Proof | Không dùng HMAC | Theo allowlist bất đối xứng của profile | Theo allowlist bất đối xứng | Có thể hỗ trợ | Có thể hỗ trợ |
| JWT Client Assertion | Theo loại client và policy | Có thể hỗ trợ | Có thể hỗ trợ | Có thể hỗ trợ | Có thể hỗ trợ |
| JWT Bearer Assertion | Theo trust agreement | Có thể hỗ trợ | Có thể hỗ trợ | Có thể hỗ trợ | Có thể hỗ trợ |

Các ô trong ví dụ không phải tuyên bố rằng mọi profile đều bắt buộc hỗ trợ các thuật toán đó. DPoP yêu cầu proof được ký bằng thuật toán bất đối xứng theo profile; không dùng HS256 để tạo proof DPoP. OAuth JWT Access Token có thể dùng nhiều thuật toán tùy cấu hình issuer/resource server, nhưng verifier phải thống nhất allowlist.

Mỗi ô nên được phân loại rõ:

- SUPPORTED: endpoint và profile chấp nhận thuật toán này;
- NOT_CONFIGURED: hệ thống không bật thuật toán này;
- FORBIDDEN_BY_PROFILE: thuật toán có thể được thư viện hiểu nhưng profile cấm;
- LEGACY_MIGRATION: chỉ chấp nhận trong giai đoạn chuyển đổi có thời hạn và policy riêng.

Không để một thuật toán được thư viện hỗ trợ tự động trở thành thuật toán được endpoint chấp nhận.

## 5. Xác định các token profile phải kiểm thử

### 5.1. OAuth JWT Access Token

Nếu hệ thống triển khai JWT Access Token Profile theo RFC 9068, test phải xác minh các yêu cầu của profile, bao gồm:

- JOSE header typ phù hợp, thường dùng at+jwt theo profile;
- iss đúng authorization server;
- aud chứa resource server dự kiến;
- exp hợp lệ;
- iat hợp lệ;
- sub theo ngữ nghĩa của profile;
- client_id xác định client;
- jti định danh token;
- scope/authorization claims được xử lý theo policy.

RFC 9068 yêu cầu các claim cốt lõi của profile như iss, exp, aud, sub, client_id, iat và jti. Test phải dùng đúng phiên bản profile và policy mà hệ thống tuyên bố triển khai. Không áp dụng quy tắc access token cho ID Token.

### 5.2. OpenID Connect ID Token

Với ID Token, test theo OIDC Core và Authentication Request tương ứng:

- iss phải khớp OpenID Provider đã tin cậy;
- sub phải có giá trị hợp lệ;
- aud phải chứa Client ID dự kiến;
- exp và iat phải hợp lệ;
- kiểm tra azp theo quy tắc khi có nhiều audience hoặc khi claim xuất hiện;
- nếu request gửi nonce, ID Token phải chứa và khớp nonce;
- nếu request gửi max_age, kiểm tra auth_time;
- kiểm tra at_hash hoặc c_hash khi flow yêu cầu;
- xác minh chữ ký bằng thuật toán được OP công bố và client cho phép.

Không chấp nhận ID Token chỉ vì chữ ký hợp lệ. ID Token được phát hành cho client khác hoặc Authentication Request khác phải bị từ chối.

### 5.3. DPoP Proof JWT

DPoP proof có profile riêng. Test token hợp lệ phải kiểm tra:

- JOSE typ phù hợp dpop+jwt;
- thuật toán bất đối xứng nằm trong allowlist DPoP;
- header jwk chứa public key phù hợp và không chứa private material;
- proof signature xác minh bằng public JWK đó;
- claim htm khớp HTTP method;
- claim htu khớp target URI theo quy tắc chuẩn hóa của RFC 9449;
- claim iat nằm trong cửa sổ tuổi cho phép;
- claim jti có tính duy nhất và được xử lý theo replay policy;
- ath khớp access token khi quy tắc DPoP yêu cầu;
- nonce khớp challenge server nếu server đã yêu cầu;
- access token DPoP-bound có cnf.jkt khớp thumbprint của public key trong proof.

JWK nhúng trong DPoP proof là ngoại lệ có mục đích. Không dùng ngoại lệ này để chấp nhận JWK nhúng làm trust anchor cho access token hoặc ID Token thông thường.

### 5.4. JWT Client Assertion và JWT Bearer Assertion

Nếu hỗ trợ RFC 7523, cần phân biệt hai cách sử dụng JWT:

- Client Authentication bằng JWT Bearer Client Assertion;
- JWT Bearer Authorization Grant.

Các test phải xác minh iss, sub, aud, exp và các ràng buộc khác theo đúng loại assertion. Với client assertion, iss và sub thường gắn với client theo profile; audience phải dành cho authorization server/token endpoint. Assertion đã dùng cần được xử lý theo replay policy, thường dùng jti và cửa sổ thời gian.

Không dùng cùng validator cho client assertion, access token và ID Token chỉ vì tất cả đều là JWT. Cùng một chữ ký có thể hợp lệ về mật mã nhưng sai loại credential.

### 5.5. Profile nội bộ hoặc tùy chỉnh

Nếu hệ thống có JWT nội bộ, cần tài liệu hóa:

- issuer và nguồn khóa;
- audience/resource;
- typ hoặc token purpose;
- thuật toán và key type được phép;
- claim bắt buộc và claim tùy chọn;
- thời hạn và clock skew;
- semantics của subject, client, tenant và scope;
- quy tắc replay, revocation và key rotation;
- endpoint nào được phép chấp nhận profile.

Test phải thể hiện profile tùy chỉnh như một hợp đồng rõ ràng, không dựa trên “JWT chung” hoặc các giả định ngầm.

## 6. Tạo fixture hợp lệ cho từng thuật toán

### 6.1. Dùng khóa kiểm thử riêng

Tạo bộ khóa test dành riêng cho test suite:

- khóa HMAC ngẫu nhiên đủ độ dài;
- RSA key có kích thước tối thiểu theo policy;
- EC key đúng curve cho ES256/384/512;
- OKP key đúng curve nếu EdDSA được bật;
- private key chỉ nằm trong test signer/fixture;
- public key được đưa vào JWKS test tương ứng;
- mỗi issuer fixture có namespace và kid riêng.

Không dùng private signing key production trong unit test, CI, ví dụ tài liệu hoặc repository. Khóa test phải được tạo và quản lý độc lập với môi trường production.

### 6.2. Fixture nên có metadata

Một fixture có thể mô tả:

~~~yaml
fixture_id: access-token-rs256-valid
profile: oauth-jwt-access-token
issuer: https://issuer.test.example
audience:
  - https://orders.test.example
algorithm: RS256
key_id: test-rsa-2026-a
key_type: RSA
claims:
  iss: https://issuer.test.example
  sub: user-123
  aud: https://orders.test.example
  client_id: portal-test
  iat: 1900000000
  exp: 1900000300
  jti: test-jti-001
expected_result: ACCEPT
~~~

Metadata này là ví dụ mô tả fixture, không phải token thật. Thời gian trong fixture phải được kiểm tra với test clock cố định hoặc được tạo tương đối theo clock của test; tránh dùng timestamp đã hết hạn khi bộ test chạy trong tương lai.

### 6.3. Fixture không nên phụ thuộc một thư viện duy nhất

Nếu cùng một thư viện vừa ký token vừa xác minh token, một lỗi chung trong serialization hoặc encoding có thể khiến test vẫn pass.

Nên kết hợp:

- known-answer test vectors từ RFC hoặc bộ kiểm thử đã được tin cậy;
- token được tạo bởi implementation độc lập;
- token do test signer tạo và verifier của hệ thống kiểm tra;
- token do hệ thống phát hành và verifier độc lập kiểm tra;
- fixture được lưu cùng metadata thuật toán/profile/key ID;
- test interoperability giữa các implementation có hỗ trợ cùng profile.

Không lấy token production hoặc dữ liệu người dùng thật làm fixture.

## 7. Kiểm thử dương tính cho từng thuật toán JWS

Mỗi thuật toán được bật cần ít nhất một test token hợp lệ, với khóa đúng loại và profile cho phép.

| Test ID | Token được tạo bằng | Kiểm tra thành công |
| --- | --- | --- |
| JWS-HS256 | HMAC SHA-256 với secret đủ dài | MAC hợp lệ và profile chấp nhận HS256 |
| JWS-HS384 | HMAC SHA-384 với secret đủ dài | MAC hợp lệ và profile chấp nhận HS384 |
| JWS-HS512 | HMAC SHA-512 với secret đủ dài | MAC hợp lệ và profile chấp nhận HS512 |
| JWS-RS256 | RSA PKCS#1 v1.5 + SHA-256 | Chữ ký hợp lệ với RSA public key tin cậy |
| JWS-RS384 | RSA PKCS#1 v1.5 + SHA-384 | Chữ ký hợp lệ với RSA public key tin cậy |
| JWS-RS512 | RSA PKCS#1 v1.5 + SHA-512 | Chữ ký hợp lệ với RSA public key tin cậy |
| JWS-PS256 | RSA-PSS + SHA-256 | PSS parameters và chữ ký hợp lệ |
| JWS-PS384 | RSA-PSS + SHA-384 | PSS parameters và chữ ký hợp lệ |
| JWS-PS512 | RSA-PSS + SHA-512 | PSS parameters và chữ ký hợp lệ |
| JWS-ES256 | ECDSA P-256 + SHA-256 | Curve đúng và chữ ký JOSE R\|\|S hợp lệ |
| JWS-ES384 | ECDSA P-384 + SHA-384 | Curve đúng và chữ ký JOSE R\|\|S hợp lệ |
| JWS-ES512 | ECDSA P-521 + SHA-512 | Curve đúng và chữ ký JOSE R\|\|S hợp lệ |
| JWS-EdDSA | EdDSA với OKP curve được hỗ trợ | Chữ ký và key curve hợp lệ |

Chỉ chạy các hàng được cấu hình hỗ trợ. Với hàng không được hỗ trợ, cần test từ chối rõ ràng thay vì bỏ qua mà không có kết quả.

Với mỗi test dương tính, xác minh không chỉ kết quả ACCEPT mà còn kiểm tra đúng issuer/key source, thuật toán được chọn, key ID, token profile, claim type, audience và thời gian. Không có warning hoặc fallback ngoài dự kiến và không có outbound fetch tới URL do token tự cung cấp.

## 8. Kiểm thử JWE nếu hệ thống hỗ trợ token mã hóa

JWE có hai trục thuật toán:

- alg: thuật toán quản lý hoặc phân phối Content Encryption Key (CEK);
- enc: thuật toán mã hóa nội dung.

Không gộp alg của JWE với alg ký JWS. Một JWE hợp lệ cần cả tổ hợp key management và content encryption được profile cho phép.

| Trục | Ví dụ | Điều cần kiểm thử |
| --- | --- | --- |
| Key management | dir | CEK trực tiếp có đúng kích thước và key policy |
| Key management | RSA-OAEP-256 | RSA key và OAEP hash/parameters đúng |
| Key management | ECDH-ES | Curve, ephemeral key và derivation context |
| Key management | A256KW | AES key wrap với key đúng kích thước |
| Content encryption | A128GCM, A256GCM | Key, IV, authentication tag và decrypt |
| Content encryption | A128CBC-HS256 | Kích thước key, MAC và padding theo JWA |

Test dương tính JWE cần:

1. Tạo JWE bằng tổ hợp alg/enc đã bật.
2. Dùng key đúng loại, kích thước và nguồn tin cậy.
3. Giải mã thành công.
4. Kiểm tra authentication tag và integrity.
5. Parse plaintext theo token profile bên trong.
6. Nếu là nested JWT, xác minh lớp JWT bên trong theo policy riêng.
7. Không coi giải mã thành công là bằng chứng issuer đã xác thực nếu payload bên trong chưa có chữ ký hoặc cơ chế xác thực nguồn phù hợp.

Nếu không hỗ trợ JWE, ghi rõ phạm vi test chỉ gồm JWS; không tạo giả định rằng mọi JWT phải được mã hóa.

## 9. Kiểm thử token hợp lệ theo từng profile

Bên cạnh thuật toán, mỗi profile cần fixture dương tính riêng.

| Profile | Fixture hợp lệ phải chứng minh |
| --- | --- |
| OAuth JWT Access Token | typ, issuer, audience, claims theo RFC 9068 và scope/resource policy |
| OIDC ID Token | Claim OIDC, audience client, nonce nếu gửi và các ràng buộc flow |
| DPoP Proof | typ, asymmetric key, htm, htu, iat, jti, nonce/ath khi áp dụng và key binding |
| JWT Client Assertion | Client identity, audience token endpoint, thời hạn và replay policy |
| JWT Bearer Assertion | Issuer/subject/audience và authorization grant policy |
| Internal JWT | Hợp đồng profile nội bộ, token purpose, key source và claims đã đặc tả |

Test profile cần chứng minh token đúng loại được chấp nhận tại endpoint đúng. Cùng token đó nên bị từ chối ở endpoint chờ một profile khác nếu profile không tương thích.

Ví dụ:

- ID Token hợp lệ tại OIDC client không được tự động chấp nhận như access token tại Orders API.
- Access token hợp lệ không được chấp nhận làm ID Token để tạo phiên đăng nhập.
- DPoP proof hợp lệ không được chấp nhận thay access token.
- Client assertion hợp lệ cho token endpoint không được dùng như bearer credential gọi resource server.

## 10. Test header và claim của profile

### 10.1. Protected header

Với mỗi fixture, xác minh các trường header cần thiết:

- alg thuộc allowlist của profile/endpoint;
- kid chọn đúng key trong JWKS của issuer;
- typ đúng khi profile yêu cầu;
- crit chỉ chứa extension mà verifier hiểu và hỗ trợ;
- cty đúng nếu dùng nested JWT;
- jwk, jku, x5u, x5c được xử lý theo policy của profile;
- không có thuật toán hoặc key type bị thay thế ngoài dự kiến.

Không bắt buộc mọi profile phải có kid nếu profile cho phép chọn khóa theo cách khác. Nhưng khi có nhiều khóa hoặc key rotation, test phải chứng minh lựa chọn khóa không mơ hồ.

### 10.2. Claims và kiểu dữ liệu

Test claim không chỉ kiểm tra có/không. Cần kiểm tra kiểu dữ liệu, semantics và quan hệ giữa các claim.

| Claim | Điều cần kiểm thử |
| --- | --- |
| iss | Chuỗi chính xác, khớp issuer tin cậy |
| sub | Kiểu và semantics đúng profile |
| aud | Chuỗi hoặc mảng theo JWT, có recipient mong đợi |
| exp | NumericDate hợp lệ và còn hiệu lực |
| iat | NumericDate hợp lệ, không nằm ngoài chính sách |
| nbf | Nếu có, token chưa bị dùng trước thời điểm cho phép |
| jti | Có khi profile yêu cầu; uniqueness/replay policy |
| scope / roles | Định dạng và quyền trong phạm vi policy |
| client_id | Khớp client theo profile |
| nonce | Khớp transaction nếu request đã gửi |
| auth_time | Có và đạt max_age khi yêu cầu |
| acr / amr | Ngữ nghĩa và allowlist theo issuer/policy |
| cnf | Key binding đúng với sender-constrained token |

Không chuyển đổi kiểu tùy tiện, ví dụ chấp nhận exp là chuỗi số nếu profile yêu cầu NumericDate dạng number. Không biến claim thiếu thành giá trị mặc định để token vượt validation.

## 11. Kiểm thử nguồn khóa và key rotation

Một test token hợp lệ phải được xác minh bằng khóa có nguồn gốc tin cậy. Test cần bao phủ:

- khóa public tương ứng private key ký fixture;
- kid khớp duy nhất trong JWKS của issuer;
- JWK kty, use, key_ops, alg, crv và key size phù hợp;
- cache JWKS được namespace theo issuer;
- khóa mới đã được công bố trước khi issuer dùng để ký;
- trong giai đoạn overlap, khóa cũ và mới đều được chấp nhận theo policy;
- sau khi khóa cũ bị loại bỏ và hết thời gian chuyển tiếp, token dùng khóa cũ bị từ chối;
- unknown kid có thể kích hoạt refresh có kiểm soát từ JWKS URI đã cấu hình;
- không fallback sang JWK nhúng hoặc jku tùy ý.

Một fixture hợp lệ với khóa test A phải bị từ chối khi verifier được cấu hình chỉ tin issuer/key set B, dù thuật toán và chữ ký đều hợp lệ theo khóa A.

## 12. Kiểm thử thời gian và ranh giới hiệu lực

Dùng clock có thể điều khiển trong test để tránh phụ thuộc thời gian thật. Mỗi profile có thể quy định TTL và leeway khác nhau.

Các trường hợp dương tính:

- exp ở tương lai trong giới hạn TTL profile;
- iat hợp lệ và không vượt quá giới hạn tuổi;
- nbf đã tới hoặc không được đặt nếu profile không yêu cầu;
- thời gian nằm trong clock skew cho phép;
- auth_time đáp ứng max_age với OIDC;
- proof DPoP có iat nằm trong cửa sổ cho phép.

Các trường hợp biên cần test từ chối:

- token hết hạn ngay trước thời điểm xác minh;
- iat nằm trong tương lai vượt leeway;
- nbf ở tương lai;
- TTL vượt mức profile;
- exp sai kiểu hoặc không hợp lệ;
- auth_time quá cũ;
- proof quá cũ hoặc nonce hết hạn.

Không dùng cùng một leeway rộng cho mọi profile chỉ để giảm lỗi test. Leeway phải là policy rõ ràng và nhất quán giữa các verifier.

## 13. Kiểm thử liên thông và known-answer vectors

Một bộ test tốt không chỉ chứng minh implementation tự tương thích với chính nó.

### 13.1. Known-answer test

Dùng vector đã được công bố hoặc bộ test vector đáng tin cậy cho từng thuật toán. Kiểm tra input signing bytes chính xác, protected header và payload bytes, public key/secret fixture, chữ ký mong đợi, kết quả verify và lỗi khi sửa một byte trong signing input hoặc signature.

Đối với thuật toán có randomness như RSA-PSS hoặc ECDSA không deterministic trong implementation, không nhất thiết chữ ký sinh ra phải giống từng byte với vector. Thay vào đó, dùng fixed known-answer signature để verify và kiểm tra signer/verifier tương thích theo chuẩn.

### 13.2. Kiểm thử hai implementation độc lập

Nếu có thể, tạo fixture từ implementation A và xác minh bằng implementation B. Sau đó tạo token từ implementation B và xác minh bằng implementation A.

Điều này giúp phát hiện sai encoding chữ ký, nhầm ECDSA DER với JOSE R||S, sai PSS salt length, sai cách parse Base64URL hoặc NumericDate, khác biệt về typ, aud hay claim semantics và chấp nhận extension không tương thích.

### 13.3. Test vector có version

Mỗi fixture nên có ID và phiên bản, profile, thuật toán, kid và key type, thời gian tạo, nguồn vector, expected result, lý do expected result và hash của file fixture nếu cần bảo đảm tính toàn vẹn.

Khi tiêu chuẩn hoặc policy thay đổi, tạo phiên bản fixture mới và giữ lịch sử để biết vì sao một test bắt đầu pass/fail.

## 14. Mã giả chạy ma trận test

~~~text
for each profile in configuredProfiles:
    policy = loadValidationPolicy(profile)

    for each algorithm in policy.allowedAlgorithms:
        fixture = fixtureCatalog.find(
            profile = profile.name,
            algorithm = algorithm,
            status = "valid"
        )

        require fixture exists
        require fixture.keyType matches algorithm
        require fixture.issuer is trusted for profile
        require fixture.audience matches test endpoint

        result = verifier.verify(
            token = fixture.token,
            profile = profile,
            clock = fixedTestClock
        )

        assert result.accepted
        assert result.algorithm == algorithm
        assert result.keyId == fixture.keyId
        assert result.profile == profile.name
        assert result.issuer == fixture.issuer
        assert result.audience contains fixture.expectedAudience
~~~

Đây là pseudocode mô tả cách tổ chức test. configuredProfiles và allowedAlgorithms phải lấy từ policy thực tế hoặc test configuration độc lập; không tự lấy header alg của token làm danh sách thuật toán cần chấp nhận.

Một ma trận kết quả có thể lưu:

~~~json
{
  "profile": "oauth-jwt-access-token",
  "algorithm": "PS256",
  "fixture": "access-ps256-valid-v1",
  "key_id": "test-pss-2026-a",
  "expected": "ACCEPT",
  "actual": "ACCEPT",
  "signature": "PASS",
  "claims": "PASS",
  "issuer": "PASS",
  "audience": "PASS",
  "time": "PASS"
}
~~~

Không đưa raw token, secret hoặc private key vào test report. Fixture ID và metadata đủ để truy vết kết quả.

## 15. Test từ chối để xác nhận ranh giới hỗ trợ

Bên cạnh positive test, cần các negative test để chứng minh endpoint chỉ chấp nhận đúng tập đã công bố:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Thuật toán không nằm trong allowlist | Từ chối |
| alg=none tại endpoint yêu cầu chữ ký | Từ chối |
| HS token được xác minh bằng RSA public key hoặc ngược lại | Từ chối |
| ECDSA curve không khớp thuật toán | Từ chối |
| RSA key dưới ngưỡng policy | Từ chối |
| HMAC secret ngắn hơn yêu cầu | Từ chối |
| PS256 dùng sai PSS parameters | Từ chối |
| ECDSA signature dùng sai encoding | Từ chối |
| Chữ ký bị thay đổi một byte | Từ chối |
| kid không tồn tại hoặc mơ hồ | Từ chối |
| Khóa đến từ issuer khác | Từ chối |
| iss hoặc aud sai | Từ chối |
| Token đúng chữ ký nhưng sai typ/profile | Từ chối |
| Claim bắt buộc thiếu hoặc sai kiểu | Từ chối |
| Token hết hạn hoặc nbf chưa tới | Từ chối |
| ID Token nonce không khớp | Từ chối |
| DPoP proof dùng HMAC hoặc key binding sai | Từ chối |
| Access token bị dùng thay ID Token hoặc assertion | Từ chối |
| JWE dùng tổ hợp alg/enc không hỗ trợ | Từ chối |

Negative test không thay thế positive test. Một validator từ chối tất cả token sẽ pass mọi negative test nhưng không thực hiện được chức năng. Cần bảo đảm cả hai phía: token hợp lệ được chấp nhận, token ngoài policy bị từ chối.

## 16. Kiểm thử cấu hình và thay đổi policy

Thuật toán được hỗ trợ có thể thay đổi theo môi trường hoặc đợt chuyển đổi khóa. Test phải phát hiện cấu hình ngoài dự kiến:

- production chỉ bật thuật toán đã được phê duyệt;
- test/staging có thể dùng fixture riêng nhưng không làm rộng policy production;
- không có fallback ngầm sang thuật toán yếu hơn;
- cấu hình profile không bị ghi đè bởi header token;
- thay đổi allowlist có test review và regression;
- key rotation không làm validator thử mọi thuật toán hoặc mọi issuer;
- thư viện được nâng cấp không tự bật thuật toán mới;
- cấu hình thuật toán của issuer và resource server không lệch nhau.

Nếu đang chuyển từ thuật toán cũ sang thuật toán mới, xác định thời điểm bắt đầu/kết thúc chấp nhận từng loại token. Test cả giai đoạn overlap và trạng thái sau khi loại bỏ thuật toán cũ. Không để hỗ trợ legacy tồn tại vô thời hạn.

## 17. Kiểm thử hiệu năng và khả năng chịu lỗi

Kiểm thử hợp lệ theo thuật toán cũng cần đo chi phí và hành vi khi phụ thuộc bên ngoài gặp lỗi:

- throughput và latency theo từng thuật toán;
- kích thước khóa và token lớn nhất được phép;
- cache hit/miss JWKS;
- nhiều request đầu tiên sau key rotation;
- unknown kid không gây JWKS refresh storm;
- JWKS endpoint timeout hoặc trả dữ liệu sai;
- verifier không dùng khóa stale ngoài policy;
- memory/CPU khi parse nhiều token hoặc payload lớn;
- hành vi khi clock source hoặc key store không sẵn sàng.

Không ghi token vào benchmark log. Dùng fixture tổng hợp, request ID và profile/algorithm label. Tránh dùng kid, jti, subject hoặc token fingerprint làm metric label có cardinality cao.

## 18. Các lỗi kiểm thử thường gặp

- Chỉ kiểm tra một thuật toán mặc định và suy ra các thuật toán khác cũng hoạt động.
- Chỉ kiểm tra thư viện ký và verify cùng một implementation.
- Tạo token chữ ký đúng nhưng claim/profile sai rồi vẫn coi là positive fixture.
- Dùng một key cho nhiều thuật toán không tương thích.
- Không kiểm tra độ dài HMAC key hoặc RSA modulus.
- Không kiểm tra đúng curve ECDSA.
- Không kiểm tra JOSE R||S encoding.
- Không kiểm tra PSS salt length và MGF1.
- Không phân biệt JWS alg với JWE alg/enc.
- Dùng cùng validator cho ID Token, access token, DPoP proof và assertion.
- Không kiểm tra typ, issuer, audience hoặc key source.
- Chỉ test token mới, bỏ qua key rotation và overlap.
- Dùng timestamp cố định đã hết hạn khi fixture chạy ở thời điểm khác.
- Không kiểm tra clock skew ở ranh giới.
- Cho thuật toán mới tự động được bật sau khi nâng cấp thư viện.
- Không lưu metadata fixture nên không biết test đã chứng minh điều gì.

## 19. Checklist hoàn tất bộ test

**Phạm vi và policy:**

- [ ] Có inventory thuật toán JWS/JWE thực sự được bật.
- [ ] Có inventory token profile và endpoint tương ứng.
- [ ] Có ma trận thuật toán × profile.
- [ ] Mỗi tổ hợp hỗ trợ có positive fixture.
- [ ] Tổ hợp không hỗ trợ có negative test.

**Thuật toán và khóa:**

- [ ] HS key đủ độ dài.
- [ ] RSA key đạt ngưỡng kích thước.
- [ ] PS parameters đúng JWA.
- [ ] ES curve và R||S encoding đúng.
- [ ] EdDSA curve/key type đúng.
- [ ] JWK kty, use, key_ops, alg, crv được kiểm tra.
- [ ] Không dùng nhầm khóa giữa thuật toán hoặc issuer.

**Token profile:**

- [ ] Access Token Profile được kiểm tra theo RFC 9068 nếu triển khai.
- [ ] ID Token được kiểm tra theo OIDC Core.
- [ ] DPoP proof được kiểm tra theo RFC 9449.
- [ ] Client/bearer assertion được kiểm tra theo RFC 7523 nếu hỗ trợ.
- [ ] Profile nội bộ có hợp đồng header/claim rõ ràng.
- [ ] Token đúng chữ ký nhưng sai profile bị từ chối.

**Chất lượng và vận hành:**

- [ ] Có known-answer vectors và implementation độc lập.
- [ ] Có fixed clock cho test thời gian.
- [ ] Có test key rotation và unknown kid.
- [ ] Có test hiệu năng, JWKS outage và refresh storm.
- [ ] Test report không chứa raw token hoặc key material.
- [ ] Kết quả ghi rõ fixture, profile, thuật toán và reason code.

## 20. Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): cấu trúc JWS và chữ ký.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): cấu trúc JWE và xử lý mã hóa.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và thuộc tính khóa.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JWS/JWE, key size và encoding chữ ký.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và registered claims.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): định danh JWK bằng thumbprint.
- [RFC 8037 — CFRG Elliptic Curve Diffie-Hellman (ECDH) and Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037): thuật toán EdDSA và OKP trong JOSE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, issuer/audience validation và token profile separation.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token và xác minh theo flow.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof JWT và key binding.
- [RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): JWT assertion cho OAuth.

**Ghi nhớ:** Một bộ kiểm thử đầy đủ phải chứng minh từng thuật toán đang bật hoạt động với đúng loại khóa và từng token profile được chấp nhận theo đúng header, claim, issuer, audience và thời gian. Hãy test theo ma trận thuật toán × profile, dùng fixture độc lập và known-answer vectors, kiểm tra key rotation cùng các ranh giới mật mã, đồng thời từ chối rõ ràng mọi tổ hợp không được policy hỗ trợ.

