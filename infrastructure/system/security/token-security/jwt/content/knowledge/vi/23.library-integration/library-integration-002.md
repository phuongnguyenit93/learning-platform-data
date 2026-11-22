# Kiểm tra thuật toán, biểu diễn và hồ sơ thư viện hỗ trợ

## 1. Vì sao cần đánh giá khả năng hỗ trợ trước khi tích hợp?

Một thư viện quảng cáo hỗ trợ JWT chưa chắc đáp ứng được mọi yêu cầu của hệ thống. JWT là định dạng claims; các thao tác mật mã và cách biểu diễn được định nghĩa trong hệ sinh thái JOSE, còn OAuth 2.0 và OpenID Connect (OIDC) bổ sung các profile quy định token được dùng trong ngữ cảnh nào và phải kiểm tra điều gì.

Một thư viện có thể:

- Parse và tạo JWT Compact nhưng không hỗ trợ JSON Serialization.
- Verify JWS với RSA nhưng không hỗ trợ ECDSA hoặc EdDSA.
- Hỗ trợ thuật toán JWE nhưng không hỗ trợ nhiều recipient.
- Đọc JWK nhưng không tải và làm mới JWKS an toàn.
- Verify chữ ký nhưng không kiểm tra issuer, audience, thời hạn hoặc quy tắc của access token profile.
- Tạo DPoP proof JWT nhưng không triển khai đầy đủ việc kiểm tra proof ở resource server.
- Có tính năng trong phiên bản mới nhưng phiên bản đang triển khai lại thiếu hoặc có lỗi.

Vì vậy, không nên chọn thư viện chỉ dựa trên tên sản phẩm, số lượng thuật toán được liệt kê hoặc một ví dụ decode/verify đơn giản. Cần xác định profile và luồng giao thức thực tế, lập ma trận tính năng, kiểm tra tài liệu đúng phiên bản, sau đó xác minh bằng test vector và kiểm thử liên thông.

Bài học này thuộc chương **Tích hợp thư viện** của học phần **Security - JSON Web Token (JWT)** (SECURITY_TOKEN_SECURITY_JWT). Nội dung áp dụng cho thư viện JWT/JOSE ở mọi ngôn ngữ và nền tảng, không phụ thuộc Java hoặc Spring Security.

## 2. Phân biệt các lớp tiêu chuẩn cần thư viện hỗ trợ

Không nên xem JWT, JOSE, OAuth và OIDC là những tên gọi thay thế cho nhau.

| Lớp | Phạm vi | Ví dụ tiêu chuẩn |
| --- | --- | --- |
| JWT | Định dạng claims được biểu diễn bằng JWS, JWE hoặc cấu trúc lồng | RFC 7519 |
| JWS | Chữ ký số hoặc MAC bảo vệ nội dung | RFC 7515 |
| JWE | Mã hóa nội dung có xác thực | RFC 7516 |
| JWK / JWKS | Biểu diễn một khóa hoặc tập khóa JSON | RFC 7517 |
| JWA | Tên thuật toán, tham số và quy tắc sử dụng khóa | RFC 7518 |
| JOSE extensions | Mở rộng cách biểu diễn hoặc proof | RFC 7797, RFC 8037 |
| OAuth token profile | Quy tắc dùng JWT làm access token hoặc assertion | RFC 9068, RFC 7523 |
| OpenID Connect | Quy tắc phát hành và xác minh ID Token | OpenID Connect Core |
| DPoP | Proof of possession gắn với request OAuth | RFC 9449 |

Một thư viện có thể hỗ trợ đầy đủ JWS Compact nhưng không biết access token JWT theo RFC 9068 phải có typ và các claim nào. Tương tự, thư viện có thể tạo JWT có chữ ký nhưng không tự triển khai các bước OIDC như kiểm tra nonce, azp hoặc at_hash khi chúng được yêu cầu.

Cần đánh giá riêng:

1. **Primitive JOSE:** thuật toán ký, MAC, quản lý khóa và mã hóa nội dung.
2. **Serialization:** Compact, Flattened JSON, General JSON và các extension được dùng.
3. **Key management:** JWK/JWKS, import/export, key selection, rotation và HSM/KMS.
4. **JWT claims:** parse, type handling, thời gian và claim validation.
5. **Protocol profile:** OAuth access token, OIDC ID Token, client assertion, DPoP hoặc profile khác.
6. **Operational behavior:** giới hạn tài nguyên, lỗi, logging, cập nhật phiên bản và interoperability.

## 3. Kiểm tra hỗ trợ thuật toán JWS

JWS dùng tham số alg để chỉ thuật toán chữ ký hoặc MAC. Tên thuật toán phải được ánh xạ đúng với loại khóa và policy của issuer.

### 3.1. Các nhóm thuật toán thường gặp

| Nhóm | Tên JOSE thường gặp | Loại khóa | Điểm cần xác minh |
| --- | --- | --- | --- |
| HMAC | HS256, HS384, HS512 | Secret đối xứng | Độ dài và entropy của secret; mọi bên giữ secret đều có thể ký |
| RSA PKCS#1 v1.5 | RS256, RS384, RS512 | RSA private/public key | Kích thước khóa, khả năng tương thích và policy hiện hành |
| RSA-PSS | PS256, PS384, PS512 | RSA private/public key | Salt length, hash và tham số PSS theo JWA |
| ECDSA | ES256, ES384, ES512 | EC key trên curve tương ứng | Curve và định dạng chữ ký JOSE |
| Edwards-curve | EdDSA | OKP, thường Ed25519 hoặc Ed448 | Hỗ trợ curve, thư viện mật mã và định dạng JWK |

Không cần bật tất cả thuật toán. Chọn allowlist nhỏ nhất đáp ứng issuer, client, resource server và yêu cầu interoperability.

### 3.2. HMAC: đơn giản nhưng mở rộng ranh giới tin cậy

Với HMAC, cùng một secret được dùng để ký và xác minh. Bất kỳ service nào có secret để verify cũng có khả năng tạo token giả hợp lệ.

Khi đánh giá thư viện và kiến trúc, cần kiểm tra:

- Secret có được tạo ngẫu nhiên với entropy đủ mạnh không?
- Độ dài secret có đáp ứng yêu cầu của thuật toán không?
- Secret có bị hard-code, commit vào source hoặc phân phối cho quá nhiều service không?
- Có hỗ trợ lấy secret từ KMS/HSM hoặc secret manager không?
- Có thể xoay secret và hỗ trợ giai đoạn chuyển tiếp giữa key version không?

Không dùng password người dùng hoặc chuỗi dễ đoán làm HMAC key. Không chọn HS256 chỉ vì API đơn giản nếu nhiều resource server chỉ cần xác minh mà không nên có quyền ký.

### 3.3. RSA và RSA-PSS

Với RSA, issuer ký bằng private key; resource server xác minh bằng public key. Đây thường là mô hình phù hợp khi nhiều service cần xác minh nhưng chỉ một issuer được phép phát hành token.

Cần xác minh:

- Thư viện hỗ trợ đúng RS256 và PS256 theo policy hay chỉ hỗ trợ một số biến thể.
- Kích thước RSA tối thiểu và định dạng key được chấp nhận.
- RSA-PSS dùng hash và salt length đúng yêu cầu của JWA.
- Private key có thể được sử dụng từ HSM/KMS mà không cần export hay không.
- Key metadata như kty, use, key_ops và alg có được kiểm tra phù hợp không.

Không suy ra rằng thư viện hỗ trợ RSA signing thì chắc chắn hỗ trợ RSA-PSS. Đây là các thuật toán khác nhau dù cùng loại khóa RSA.

### 3.4. ECDSA và định dạng chữ ký JOSE

Một lỗi interoperability thường gặp là nhầm chữ ký ECDSA theo ASN.1 DER với định dạng JWS.

Trong JWS, chữ ký ECDSA được biểu diễn bằng phép nối hai số nguyên cố định độ dài R || S theo quy tắc JOSE. Nhiều API mật mã cấp thấp lại trả chữ ký DER. Thư viện JWT phải chuyển đổi đúng giữa hai dạng.

Khi kiểm tra ES256, ES384, ES512, cần xác minh:

- Curve tương ứng là P-256, P-384 hoặc P-521.
- Độ dài chữ ký JOSE đúng theo curve.
- Chuyển đổi DER và JOSE chính xác ở cả chiều ký lẫn verify.
- Xử lý giá trị R và S có padding đúng độ dài.
- Có test vector liên thông với implementation khác.

Một cặp khóa EC hợp lệ không đồng nghĩa mọi chữ ký do mọi API ECDSA tạo ra đều có thể đặt trực tiếp vào JWS.

### 3.5. EdDSA

EdDSA trong JOSE được định nghĩa cho các đường cong Edwards được tiêu chuẩn hỗ trợ, gồm Ed25519 và Ed448. Cần kiểm tra chính xác curve mà thư viện, runtime và kho khóa hỗ trợ.

Đừng chỉ thấy thư viện ghi EdDSA rồi mặc định mọi biến thể EdDSA đều dùng được. Kiểm tra:

- JWK có kty là OKP và giá trị crv phù hợp.
- Định dạng public/private key được hỗ trợ.
- Khả năng ký và xác minh trên các môi trường triển khai.
- Hành vi khi key metadata không khớp thuật toán.

### 3.6. Thuật toán không nên bật chỉ vì thư viện hỗ trợ

Một số thư viện có thể còn hỗ trợ none hoặc các lựa chọn cũ vì lý do tương thích. Hỗ trợ trong mã nguồn không có nghĩa thuật toán đó phù hợp với production.

- Không chấp nhận alg none trong luồng xác thực thông thường.
- Không tự fallback sang thuật toán yếu hơn khi verify thất bại.
- Tránh các thuật toán đã có cảnh báo hoặc không còn phù hợp với policy hiện hành.
- Không để token tự chọn thuật toán ngoài allowlist.
- Không dùng cùng một key material tùy tiện cho nhiều mục đích hoặc nhiều thuật toán.

## 4. Kiểm tra hỗ trợ thuật toán JWE

JWE tách thuật toán quản lý khóa alg khỏi thuật toán mã hóa nội dung enc. Đây là hai lựa chọn khác nhau và phải được đánh giá riêng.

### 4.1. Thuật toán quản lý khóa alg

| Nhóm | Ví dụ | Vai trò | Điều cần kiểm tra |
| --- | --- | --- | --- |
| Direct | dir | Dùng CEK đã chia sẻ trực tiếp | Quản lý CEK và phân phối khóa đối xứng |
| RSA-OAEP | RSA-OAEP, RSA-OAEP-256 | Mã hóa CEK bằng public key recipient | Hash/MGF parameters và key size |
| AES Key Wrap | A128KW, A192KW, A256KW | Wrap CEK bằng KEK đối xứng | Độ dài KEK và quy trình rotation |
| ECDH-ES | ECDH-ES và biến thể kết hợp Key Wrap | Thiết lập khóa bằng ECDH | Curve, ephemeral public key và Concat KDF |
| PBES2 | PBES2-HS256+A128KW và biến thể | Tạo KEK từ password | Salt, iteration count và rủi ro password yếu |

Nếu chỉ cần mã hóa cho một recipient, profile có thể chọn một thuật toán quản lý khóa cụ thể. Nếu cần nhiều recipient, phải xác minh hỗ trợ JWE JSON General Serialization và cách thư viện xử lý CEK dùng chung.

Đặc biệt:

- Không chấp nhận thuật toán ngoài allowlist.
- Không dùng password yếu làm nguồn khóa JWE.
- Không dùng RSA1_5 trong profile mới; cần tuân thủ hướng dẫn bảo mật hiện hành và tránh rủi ro padding oracle.
- Với ECDH-ES, kiểm tra curve, epk, apu, apv và KDF theo đặc tả.
- Không cho header không tin cậy kích hoạt key retrieval từ URL tùy ý.

### 4.2. Thuật toán mã hóa nội dung enc

| Nhóm | Ví dụ | Đặc điểm | Điểm cần xác minh |
| --- | --- | --- | --- |
| AES-GCM | A128GCM, A192GCM, A256GCM | AEAD, cung cấp confidentiality và integrity | Nonce/IV, tag length, xác thực trước khi trả plaintext |
| AES-CBC-HMAC | A128CBC-HS256, A192CBC-HS384, A256CBC-HS512 | Kết hợp mã hóa CBC và MAC | Kiểm tra MAC đúng thứ tự trước khi dùng plaintext |

AES-GCM thường là lựa chọn phù hợp cho profile mới nếu các bên đều hỗ trợ. Các biến thể CBC-HMAC có thể cần cho interoperability hoặc hệ thống cũ; phải xác minh cách thư viện thực hiện kiểm tra MAC và xử lý lỗi.

Cần phân biệt rõ:

- alg bảo vệ hoặc tạo CEK.
- enc mã hóa plaintext bằng CEK.
- Authentication tag xác thực ciphertext và AAD theo thuật toán.
- Thành công ở JWE không tự chứng minh danh tính issuer.

Không chọn alg hoặc enc chỉ từ token. Verifier phải có allowlist và policy theo issuer, recipient, endpoint hoặc profile.

### 4.3. Compression và tham số mở rộng

Nếu thư viện hỗ trợ zip, hãy xác định:

- Có thật sự cần nén hay không.
- Có chỉ chấp nhận thuật toán nén trong profile không.
- Có giới hạn kích thước sau giải nén và thời gian xử lý không.
- Có tránh nén secret cùng dữ liệu do attacker kiểm soát để giảm side-channel không.
- Có tuân thủ yêu cầu integrity protection của header zip không.

Không bật compression chỉ để làm token nhỏ hơn. Với dữ liệu lớn, nên xem lại thiết kế claims và cách truyền dữ liệu.

## 5. Kiểm tra hỗ trợ serialization

JOSE định nghĩa nhiều cách biểu diễn. Một thư viện hỗ trợ Compact không mặc nhiên hỗ trợ mọi dạng JSON Serialization.

### 5.1. JWS Compact Serialization

JWS Compact có ba phần:

```text
BASE64URL(protected-header)
.
BASE64URL(payload)
.
BASE64URL(signature)
```

Phù hợp với nhiều access token JWT thông thường và dễ truyền trong HTTP header. Cần xác minh thư viện:

- Tạo và parse đúng ba segment.
- Xử lý Base64url không padding theo chuẩn.
- Xác minh chính xác signing input.
- Từ chối segment sai định dạng hoặc token quá lớn.
- Không tự coi payload đã decode là đáng tin trước verify.

### 5.2. JWS JSON Serialization

JWS JSON Serialization có hai dạng:

- **Flattened:** một signature với cấu trúc JSON gọn.
- **General:** có thể chứa nhiều signature entries.

Một số hệ thống cần nhiều chữ ký hoặc cần trao đổi JOSE object dưới dạng JSON. Nếu thư viện chỉ hỗ trợ Compact, nó có thể không xử lý được những use case này.

Khi kiểm tra, xác minh cách thư viện xử lý:

- protected, unprotected, header, signature.
- Nhiều signature và thứ tự xử lý.
- Header không được bảo vệ.
- Payload detached hoặc unencoded nếu profile sử dụng.
- Critical header parameters.

Không dùng unprotected header làm căn cứ xác thực thuật toán, issuer hoặc quyền.

### 5.3. JWE Compact Serialization

JWE Compact có năm phần:

```text
BASE64URL(protected-header)
.
BASE64URL(encrypted-key)
.
BASE64URL(iv)
.
BASE64URL(ciphertext)
.
BASE64URL(authentication-tag)
```

Cần kiểm tra thư viện hỗ trợ đúng cả key management và content encryption. Chỉ có hàm decrypt không đủ nếu thư viện bỏ qua hoặc không xác minh authentication tag trước khi trả plaintext.

### 5.4. JWE JSON Serialization

JWE JSON Serialization có:

- **Flattened:** một recipient.
- **General:** một hoặc nhiều recipient entries.

General JSON Serialization cho phép nhiều recipient cùng nhận một plaintext thông qua CEK được bảo vệ riêng cho từng recipient. Nếu use case yêu cầu nhiều recipient, cần kiểm tra:

- Có hỗ trợ tạo và parse General JSON không?
- Có giới hạn số recipient không?
- Có xác minh đúng recipient key và encrypted key không?
- Có xử lý đúng protected, shared unprotected và per-recipient headers không?
- Có từ chối metadata không hợp lệ hoặc không nhất quán không?

Nếu hệ thống chỉ dùng một recipient, có thể ưu tiên Compact hoặc Flattened theo profile để giảm độ phức tạp.

## 6. Kiểm tra JOSE extensions và trường hợp đặc biệt

### 6.1. Critical header parameters crit

Header crit chỉ ra các tham số mở rộng mà bên nhận phải hiểu và xử lý. Nếu thư viện gặp critical parameter không được hỗ trợ, token phải bị từ chối.

Cần xác minh:

- Thư viện có thực thi crit hay chỉ parse header?
- Có từ chối tham số critical không được hỗ trợ không?
- Có cho ứng dụng đăng ký handler một cách an toàn không?
- Có ngăn một extension làm thay đổi semantics mà verifier không hiểu không?

Không bỏ qua crit để tăng tương thích.

### 6.2. Unencoded payload b64 false

RFC 7797 cho phép JWS dùng payload không Base64url-encode trong một số trường hợp. Đây không phải mặc định của JWT Compact thông thường và cần xử lý đặc biệt với crit.

Nếu hệ thống không cần tính năng này, có thể từ chối. Nếu cần, phải xác minh thư viện triển khai đúng signing input, giới hạn ký tự và cách xử lý payload detached.

### 6.3. Detached payload

Một số JWS không mang payload trực tiếp trong token; bên nhận lấy payload từ kênh khác. Điều này đòi hỏi hợp đồng rõ ràng về:

- Nguồn payload và binding với request.
- Encoding và byte representation chính xác.
- Cách xác minh chữ ký trên payload được cung cấp bên ngoài.
- Ngăn thay thế payload hoặc dùng nhầm payload giữa các request.

Không coi việc chữ ký hợp lệ trên một detached payload là bằng chứng payload đến từ đúng resource nếu ứng dụng không kiểm tra binding.

## 7. Kiểm tra JWK, JWKS và quản lý khóa

### 7.1. Khả năng đọc và ghi JWK

JWK biểu diễn key dưới dạng JSON. Cần kiểm tra thư viện có hỗ trợ loại khóa mà profile yêu cầu:

| Key type | Mục đích thường gặp | Metadata cần kiểm tra |
| --- | --- | --- |
| oct | Secret đối xứng/HMAC hoặc một số khóa đối xứng | k, alg, use, key_ops |
| RSA | RSA signing, verification hoặc key management | n, e, private parameters nếu cần, alg, use |
| EC | ECDSA hoặc ECDH trên curve hỗ trợ | crv, x, y, d nếu là private key |
| OKP | EdDSA hoặc curve OKP được hỗ trợ | crv, x, d nếu là private key |

JWK/JWKS là cách biểu diễn khóa trong JSON, còn PEM, DER, PKCS#8, PKCS#1, SubjectPublicKeyInfo và chứng thư X.509 là các dạng key/certificate encoding khác. Cần kiểm tra thư viện có import được đúng định dạng mà hệ thống cấp, có phân biệt private key với public key và có thể sử dụng khóa từ provider bên ngoài hay không. Hỗ trợ JWK không đồng nghĩa tự động hỗ trợ mọi định dạng PEM/DER, và hỗ trợ PEM không có nghĩa thư viện hiểu JWKS.

Không xuất private key thành JWK công khai. Khi serialize JWKS cho verifier, chỉ phát hành public parameters cần thiết.

### 7.2. Key metadata và thuật toán phải nhất quán

Các trường thường cần xét:

- kty: loại khóa.
- crv: curve đối với EC/OKP.
- use: mục đích như sig hoặc enc.
- key_ops: thao tác được phép.
- alg: thuật toán liên quan nếu được chỉ định.
- kid: định danh khóa.

Không chỉ chọn key theo kid. Verifier phải kiểm tra loại khóa, thuật toán, mục đích và issuer. kid không phải bí mật và không phải bằng chứng khóa đáng tin.

### 7.3. JWKS retrieval và rotation

Nếu thư viện có thể tải JWKS từ xa, kiểm tra:

- JWKS URI lấy từ cấu hình tin cậy hoặc metadata đã xác minh.
- Không dùng jku/x5u trong token không tin cậy để tải URL tùy ý.
- Có timeout, TLS validation, cache và giới hạn refresh.
- Có xử lý kid không tồn tại mà không gây request storm.
- Có hỗ trợ rotation với key overlap: issuer phát hành bằng khóa mới trong khi verifier còn cần xác minh token ký bằng khóa cũ.
- Có xử lý key bị thu hồi hoặc compromised theo policy.

Không refresh JWKS vô hạn mỗi khi gặp kid lạ. Thư viện hoặc lớp tích hợp cần negative cache, single-flight và rate limit phù hợp.

### 7.4. HSM, KMS và khóa không xuất được

Một thư viện có thể chỉ hỗ trợ key material trong bộ nhớ hoặc file. Hệ thống production có thể cần:

- HSM hoặc cloud KMS.
- PKCS#11 hoặc provider tương đương.
- Remote signing API.
- Private key không export được.
- Quyền ký riêng theo workload hoặc issuer.

Cần kiểm tra thư viện có abstraction cho external signer/verifier hay không. Nếu không, có thể cần adapter nhưng phải bảo đảm adapter không làm lộ private key hoặc thay đổi signing input.

## 8. Kiểm tra hỗ trợ JWT và protocol profiles

Đây là bước thường bị bỏ sót. Hỗ trợ JWS/JWE không đồng nghĩa hỗ trợ đầy đủ profile giao thức.

### 8.1. JWT access token profile — RFC 9068

Nếu hệ thống dùng JWT làm OAuth access token theo RFC 9068, kiểm tra thư viện hoặc lớp tích hợp có thể:

- Xác minh chữ ký và thuật toán theo issuer configuration.
- Kiểm tra issuer và audience.
- Kiểm tra thời hạn và claim bắt buộc theo profile.
- Xử lý đúng loại token, thường dùng typ với giá trị at+jwt theo profile.
- Kiểm tra các claim bắt buộc của profile, gồm iss, exp, aud, sub, client_id, iat và jti.
- Phân biệt access token với ID Token hoặc JWT assertion khác.
- Kiểm tra scope và authorization theo resource server policy.

Thư viện có thể chỉ hỗ trợ JWT generic. Khi đó, ứng dụng phải tự triển khai validator cho RFC 9068 hoặc dùng một thành phần chuyên biệt.

### 8.2. OpenID Connect ID Token

ID Token có quy tắc riêng trong OIDC Core. Ngoài verify chữ ký, client cần kiểm tra các điều kiện theo flow và request, chẳng hạn:

- iss khớp issuer đã cấu hình.
- aud chứa client ID phù hợp.
- azp được kiểm tra khi cần theo quy tắc OIDC.
- exp và iat hợp lệ theo policy.
- nonce khớp giá trị client đã gửi khi request yêu cầu nonce.
- at_hash hoặc c_hash được kiểm tra khi flow và response yêu cầu.
- sub được xử lý theo issuer và subject identifier rules.

Một API verifyJwt generic có thể không biết request OIDC ban đầu hoặc client ID. Do đó, không mặc định thư viện JWT generic tự xác minh đầy đủ ID Token.

### 8.3. JWT assertion và client authentication — RFC 7523

OAuth có thể dùng JWT làm authorization grant hoặc client authentication assertion. Hai mục đích này có yêu cầu khác nhau và phải cấu hình đúng endpoint.

Cần kiểm tra các claim và điều kiện như:

- iss và sub theo loại assertion.
- aud trỏ đúng authorization server/token endpoint theo profile.
- exp có thời hạn ngắn.
- jti có thể được dùng để phát hiện assertion reuse theo policy.
- Chữ ký được xác minh bằng khóa client/issuer đã đăng ký.

Không dùng access token thông thường làm client assertion nếu authorization server không quy định như vậy.

### 8.4. DPoP proof — RFC 9449

DPoP dùng JWT làm proof cho một HTTP request. Hỗ trợ ký JWT chưa đủ để nói thư viện hỗ trợ DPoP.

Cần xác minh có thể thực hiện đầy đủ:

- Tạo proof với typ là dpop+jwt.
- Đưa public JWK phù hợp vào protected header.
- Tạo jti, htm, htu, iat và ath theo đúng ngữ cảnh.
- Xử lý server-provided nonce khi được yêu cầu.
- Kiểm tra proof signature, method, URI, access token hash và binding với token.
- Chống proof replay theo policy.
- Phân biệt lỗi proof với lỗi access token.

Nếu thư viện chỉ cung cấp JOSE primitive, phần DPoP protocol validation vẫn phải được triển khai ở tầng ứng dụng hoặc thư viện OAuth chuyên biệt.

### 8.5. Lập ma trận profile thực tế

| Profile | Primitive cần có | Validation riêng cần có |
| --- | --- | --- |
| JWT generic JWS | JWS signing/verify | Issuer, audience, thời hạn, loại token theo ứng dụng |
| JWT generic JWE | JWE encrypt/decrypt | Recipient, key policy và claims sau giải mã |
| OAuth JWT access token theo RFC 9068 | JWS signing/verify | RFC 9068, issuer, audience, typ, các claim bắt buộc và scope |
| OIDC ID Token | JWS verify, có thể JWE theo cấu hình | OIDC Core, nonce, audience, azp, hash claims khi áp dụng |
| JWT client assertion | JWS verify/sign | RFC 7523, issuer/subject/audience/expiry/replay |
| DPoP proof | JWS signing/verify, JWK | RFC 9449, method/URI/ath/nonce/replay |
| Nested JWT | JWS và JWE | Thứ tự xử lý, cty, profile bên trong và giới hạn nesting |

## 9. Đọc tài liệu thư viện đúng cách

Khi đánh giá thư viện, cần dùng tài liệu đúng phiên bản và đúng module/package đang triển khai.

Các nguồn nên kiểm tra:

1. Tài liệu API và reference của phiên bản cụ thể.
2. Danh sách thuật toán được hỗ trợ và điều kiện runtime/provider.
3. Hướng dẫn key import/export và JWKS.
4. Hướng dẫn serialization và các JOSE extension.
5. Ghi chú bảo mật, advisory và changelog.
6. Test suite hoặc test vector của dự án.
7. Tài liệu interoperability với issuer, identity provider hoặc hệ thống đích.

Đừng dựa vào:

- Một bài blog cũ.
- Một ví dụ chỉ decode token.
- Một bảng thuật toán không ghi phiên bản.
- Tính năng của edition thương mại khi dự án đang dùng edition miễn phí.
- API có tên verify mà không đọc rõ nó kiểm tra gì.
- Một README nói JWT support nhưng không nêu JWE, JWK, serialization hoặc profile.

### 9.1. Kiểm tra phiên bản và dependency

Một tính năng có thể chỉ xuất hiện từ một phiên bản nhất định. Cần ghi nhận:

- Phiên bản thư viện chính xác.
- Phiên bản dependency mật mã bên dưới.
- Runtime/OS/provider được hỗ trợ.
- Module bổ sung có cần cài riêng không.
- License và điều kiện phân phối.
- Lịch cập nhật bảo mật và khả năng nâng cấp.
- Các CVE hoặc advisory áp dụng cho phiên bản đang dùng.

Không nâng cấp production chỉ vì một phiên bản mới tuyên bố hỗ trợ thuật toán; cần kiểm thử tương thích và security regression.

## 10. Ma trận đánh giá thư viện

Nên tạo ma trận theo use case thực tế thay vì ghi một dòng JWT supported.

Ví dụ biểu mẫu:

| Nhóm | Tính năng cần kiểm tra | Bắt buộc? | Kết quả thư viện | Bằng chứng |
| --- | --- | --- | --- | --- |
| JWS | ES256 signing/verify | Theo issuer | Chưa đánh giá | API docs + test vector |
| JWS | PS256 signing/verify | Theo issuer | Chưa đánh giá | PSS parameter test |
| JWS | EdDSA | Theo issuer | Chưa đánh giá | Curve/format test |
| JWE | RSA-OAEP-256 | Theo recipient | Chưa đánh giá | Round-trip + interop |
| JWE | A256GCM | Theo profile | Chưa đánh giá | Tamper/tag test |
| Serialization | JWS Compact | Theo profile | Chưa đánh giá | RFC test vector |
| Serialization | JWS JSON General | Nếu dùng | Chưa đánh giá | Multi-signature test |
| Serialization | JWE JSON General | Nếu dùng | Chưa đánh giá | Multi-recipient test |
| Keys | JWK/JWKS + rotation | Theo kiến trúc | Chưa đánh giá | Unknown/rotated kid test |
| Profiles | RFC 9068 / OIDC / DPoP | Theo giao thức | Chưa đánh giá | Profile conformance tests |
| Operations | HSM/KMS, timeout, limits | Theo môi trường | Chưa đánh giá | Integration/load tests |

Điền kết quả bằng một trong các trạng thái rõ ràng:

- **Supported:** có API chính thức và test xác nhận.
- **Supported with constraints:** hỗ trợ nhưng giới hạn thuật toán, key type, serialization hoặc runtime.
- **Requires application code:** thư viện cung cấp primitive, ứng dụng phải triển khai profile validation.
- **Not supported:** không có tính năng cần thiết.
- **Not verified:** chưa có bằng chứng đủ tin cậy.

Không đánh dấu Supported chỉ vì thư viện có thể parse một token mẫu.

## 11. Kiểm thử interoperability và negative cases

### 11.1. Round-trip test chưa đủ

Round-trip test thường làm như sau:

1. Dùng thư viện tạo JWT.
2. Dùng chính thư viện đó verify hoặc decrypt.
3. Kiểm tra claims giống ban đầu.

Test này hữu ích nhưng có thể bỏ sót lỗi vì signer và verifier cùng chia sẻ một cách triển khai sai. Ví dụ cả hai cùng dùng sai định dạng ECDSA hoặc cùng bỏ qua một tham số.

Cần bổ sung test vector chuẩn và kiểm thử chéo giữa ít nhất hai implementation độc lập khi use case yêu cầu interoperability.

### 11.2. Test vector chuẩn

Dùng test vector từ RFC hoặc bộ test chính thức để kiểm tra:

- JWS signing input và signature.
- JWE CEK, encrypted key, IV, ciphertext và tag.
- JWK parsing và key metadata.
- Base64url và JSON serialization.
- Các trường hợp lỗi phải bị từ chối.

Không tự coi ví dụ tự tạo là test vector chuẩn.

### 11.3. Negative tests bắt buộc

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Payload bị sửa nhưng giữ chữ ký cũ | Verify thất bại |
| Chữ ký được tạo bởi khóa không tin cậy | Từ chối |
| alg ngoài allowlist hoặc none | Từ chối |
| Key type không khớp thuật toán | Từ chối |
| kid không tồn tại | Từ chối có kiểm soát, không tải URL tùy ý |
| ECDSA DER được đưa trực tiếp vào nơi cần JOSE raw signature | Từ chối hoặc chuyển đổi đúng theo API |
| JWE authentication tag bị sửa | Decrypt thất bại, không trả plaintext |
| JWE recipient key không đúng | Decrypt thất bại |
| Critical header không được hỗ trợ | Từ chối |
| JSON Serialization có cấu trúc không hợp lệ | Từ chối |
| Duplicate claim names | Xử lý xác định, ưu tiên từ chối theo profile |
| Token sai iss, aud, exp hoặc nbf | Claims validation từ chối |
| ID Token thiếu hoặc sai nonce khi yêu cầu | OIDC validation từ chối |
| DPoP proof sai htm, htu hoặc ath | DPoP validation từ chối |
| Token vượt kích thước/độ sâu cho phép | Từ chối trước khi tiêu thụ quá nhiều tài nguyên |

### 11.4. Test key rotation

Kiểm tra các giai đoạn:

1. Verifier nhận token ký bằng key hiện tại.
2. Issuer công bố key mới và bắt đầu ký bằng key mới.
3. Verifier nhận cả token ký bằng key mới và token cũ còn hạn.
4. Key cũ được gỡ sau khi hết cửa sổ token hợp lệ theo policy.
5. kid lạ không gây JWKS refresh liên tục.
6. Key bị compromised được xử lý theo quy trình thu hồi.

## 12. Ví dụ quy trình lựa chọn thư viện

Một quy trình có thể áp dụng cho bất kỳ ngôn ngữ hoặc nền tảng nào:

```text
1. Xác định protocol profile:
   - JWT access token, OIDC ID Token, JWE, DPoP hay assertion?

2. Xác định yêu cầu mật mã:
   - JWS alg, JWE alg/enc, key type và curve?

3. Xác định serialization:
   - Compact, Flattened JSON, General JSON, detached payload?

4. Xác định key integration:
   - JWK/JWKS, rotation, KMS/HSM, non-exportable key?

5. Đọc tài liệu đúng phiên bản:
   - API, defaults, limitations, security advisories?

6. Điền capability matrix:
   - Supported, constrained, application code, unsupported, unverified.

7. Chạy test vector và negative tests:
   - Kiểm tra cả primitive và profile.

8. Chạy interoperability/load tests:
   - Cross-library, key rotation, malformed input và resource limits.

9. Chốt policy production:
   - Allowlist thuật toán, issuer/audience, key source và error handling.

10. Ghi lại bằng chứng và kế hoạch nâng cấp:
   - Phiên bản, dependency, test results và owner.
```

Không đưa thư viện vào production chỉ vì test happy path thành công. Các điều kiện về key trust, profile validation, negative cases và update path cũng phải được xác nhận.

## 13. Các câu hỏi cần trả lời trước khi phê duyệt thư viện

- Thư viện hỗ trợ chính xác JWS/JWE và những serialization nào?
- Có hỗ trợ đúng thuật toán mà issuer và recipient yêu cầu không?
- Key type, curve, key size và metadata có được kiểm tra không?
- Có hỗ trợ JWK/JWKS và rotation an toàn không?
- Có thể dùng HSM/KMS hoặc private key không xuất được không?
- Có xử lý crit, b64, detached payload và nested JWT nếu profile cần không?
- API verify có kiểm tra claims nào, và claim nào ứng dụng phải tự kiểm tra?
- Có hỗ trợ RFC 9068, OIDC Core, RFC 7523 hoặc RFC 9449 ở mức protocol hay chỉ có JOSE primitives?
- Có giới hạn kích thước, độ sâu, recipients, signatures và thời gian xử lý không?
- Có test vector chuẩn, negative tests và interoperability evidence không?
- Phiên bản đang dùng còn được bảo trì và có đường cập nhật bảo mật không?
- Có thể tắt các thuật toán hoặc serialization không cần thiết để thu hẹp attack surface không?

## 14. Checklist tích hợp thư viện JWT/JOSE

- [ ] Đã xác định use case và protocol profile cụ thể.
- [ ] Đã lập allowlist JWS algorithms và key types.
- [ ] Đã đánh giá riêng JWE key management alg và content encryption enc.
- [ ] Đã kiểm tra curve, key size, signature format và tham số thuật toán.
- [ ] Đã xác định Compact, Flattened JSON và General JSON Serialization cần dùng.
- [ ] Đã đánh giá crit, b64, detached payload và nested JWT nếu có.
- [ ] JWK/JWKS key metadata, trust source và rotation đã được kiểm tra.
- [ ] Không tải key từ URL do token không tin cậy cung cấp.
- [ ] Đã kiểm tra hỗ trợ KMS/HSM hoặc external signer khi kiến trúc yêu cầu.
- [ ] Đã phân biệt JOSE primitive support với RFC 9068, OIDC, RFC 7523 và DPoP profile validation.
- [ ] Đã đọc tài liệu, changelog và security advisory đúng phiên bản.
- [ ] Đã chạy RFC test vectors và kiểm thử chéo implementation.
- [ ] Có negative tests cho chữ ký, tag, key, claims, headers và malformed serialization.
- [ ] Có test key rotation và xử lý kid không tồn tại.
- [ ] Đã kiểm tra giới hạn tài nguyên, timeout, logging và lỗi.
- [ ] Đã ghi lại capability matrix và bằng chứng cho từng tính năng bắt buộc.
- [ ] Đã có kế hoạch cập nhật thư viện và dependency mật mã.

**Kết luận:** Đánh giá thư viện JWT phải dựa trên thuật toán, loại khóa, serialization, quản lý khóa và protocol profile mà hệ thống thực sự cần. JWS/JWE primitive support không đồng nghĩa thư viện tự triển khai đầy đủ OAuth hoặc OIDC validation. Hãy kiểm tra tài liệu đúng phiên bản, lập capability matrix, xác minh bằng RFC test vectors, negative tests và interoperability tests, rồi chỉ bật allowlist tối thiểu trong production.

### Tài liệu tiêu chuẩn

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7797 — JSON Web Signature (JWS) Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797)
- [RFC 8037 — CFRG Elliptic Curve Diffie-Hellman (ECDH) and Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
