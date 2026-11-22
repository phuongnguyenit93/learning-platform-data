# Tương thích chữ ký ECDSA giữa JOSE và API mật mã

## 1. Vì sao hai hệ thống cùng dùng ECDSA vẫn không xác minh được chữ ký?

ECDSA là thuật toán chữ ký số dựa trên đường cong elliptic. JOSE và nhiều thư viện mật mã đều hỗ trợ ECDSA, nhưng điều đó không có nghĩa byte chữ ký do một bên tạo ra có thể chuyển trực tiếp sang bên kia.

Khác biệt phổ biến nằm ở cách tuần tự hóa chữ ký:

- JWS theo JOSE biểu diễn chữ ký ECDSA bằng hai số nguyên không dấu có độ dài cố định, ghép nối theo thứ tự R rồi S.
- Nhiều API mật mã tổng quát biểu diễn chữ ký ECDSA dưới dạng ASN.1 DER: một SEQUENCE chứa hai INTEGER có độ dài biến đổi.

Hai dạng này biểu diễn cùng một cặp giá trị toán học (r, s), nhưng byte khác nhau. Nếu đưa chữ ký DER trực tiếp vào trường signature của JWS, hoặc đưa chữ ký JOSE raw vào API chỉ nhận DER, xác minh thường thất bại.

Ngoài định dạng chữ ký, hai bên còn phải thống nhất:

- Đường cong elliptic và kích thước khóa.
- Thuật toán băm.
- Dữ liệu chính xác được ký.
- API nhận message hay digest đã băm.
- Cách mã hóa Base64URL trong JWS.
- Cách biểu diễn public key và private key.
- Quy tắc kiểm tra chữ ký và xử lý lỗi.

Vì vậy, kiểm tra “cả hai đều hỗ trợ ECDSA” là chưa đủ. Cần đối chiếu toàn bộ hợp đồng JOSE và hợp đồng API mật mã.

## 2. Các thuật toán ECDSA trong JWA

RFC 7518 định nghĩa ba thuật toán ECDSA phổ biến cho JWS:

| JWS alg | Đường cong | Hàm băm | Độ rộng mỗi số R/S | Độ dài chữ ký JOSE |
| --- | --- | --- | ---: | ---: |
| ES256 | P-256 (secp256r1/prime256v1) | SHA-256 | 32 byte | 64 byte |
| ES384 | P-384 (secp384r1) | SHA-384 | 48 byte | 96 byte |
| ES512 | P-521 (secp521r1) | SHA-512 | 66 byte | 132 byte |

Tên ES512 chỉ định ECDSA trên đường cong P-521 kết hợp SHA-512. Nó không có nghĩa đường cong có kích thước 512 bit. P-521 có trường 521 bit, nên mỗi tọa độ/số nguyên chữ ký cần tối đa 66 byte.

### 2.1. Đường cong phải khớp chính xác

P-256, P-384 và P-521 là các lựa chọn đường cong cụ thể. Không thay thế bằng một đường cong khác chỉ vì kích thước gần tương đương hoặc thư viện dùng tên alias khác.

Một số tên thường gặp:

- P-256 có thể xuất hiện dưới tên secp256r1 hoặc prime256v1.
- P-384 thường có tên secp384r1.
- P-521 thường có tên secp521r1.

Tên alias có thể khác giữa API, nhưng tham số đường cong phải chỉ cùng một nhóm toán học. Không nhầm P-256 với secp256k1; chúng là hai đường cong khác nhau.

### 2.2. Thuật toán băm là một phần của alg

Không tự chọn SHA-256 cho mọi ECDSA signature. JWS ES256, ES384 và ES512 lần lượt gắn với SHA-256, SHA-384 và SHA-512 theo JWA.

Nếu bên ký dùng P-256/SHA-384 trong khi bên xác minh xử lý theo ES256/P-256/SHA-256, chữ ký sẽ không khớp. Cặp curve/hash phải được ràng buộc bởi token profile và thuật toán JOSE được cho phép.

## 3. Hai định dạng chữ ký: JOSE raw và ASN.1 DER

### 3.1. Dạng JOSE: R nối S với độ rộng cố định

Trong JWS, chữ ký ECDSA được tạo từ hai số nguyên r và s:

~~~text
JOSE_SIGNATURE = I2OSP(r, width) || I2OSP(s, width)
~~~

I2OSP biểu diễn một số nguyên không dấu thành chuỗi octet big-endian có độ rộng cố định. width là 32 byte cho ES256, 48 byte cho ES384 và 66 byte cho ES512.

Vì độ rộng cố định, chữ ký JOSE có độ dài chính xác:

- ES256: 32 + 32 = 64 byte.
- ES384: 48 + 48 = 96 byte.
- ES512: 66 + 66 = 132 byte.

Không có byte tag ASN.1, không có trường length và không có separator giữa R và S. Consumer biết điểm chia từ thuật toán/curve đã được cấu hình.

### 3.2. Dạng ASN.1 DER: SEQUENCE hai INTEGER

Nhiều API mật mã trả về chữ ký dạng ASN.1 Distinguished Encoding Rules (DER), có cấu trúc khái quát:

~~~text
ECDSA-Signature ::= SEQUENCE {
    r INTEGER,
    s INTEGER
}
~~~

DER là encoding có cấu trúc:

- SEQUENCE có tag và length.
- Mỗi INTEGER có tag, length và nội dung.
- INTEGER ASN.1 là số nguyên có dấu theo biểu diễn two's complement.
- Độ dài INTEGER thay đổi theo giá trị và quy tắc biểu diễn số dương.

Nếu byte cao nhất của một INTEGER dương có bit cao bằng 1, DER thêm byte 00 ở đầu để tránh diễn giải thành số âm. Nếu có các byte zero dư thừa ở đầu, DER canonical loại bỏ chúng.

Vì vậy, chữ ký DER có độ dài biến đổi. Nó không có độ dài 64/96/132 byte cố định như chữ ký JOSE.

### 3.3. Minh họa sự khác nhau

Giả sử R và S đều có độ rộng 32 byte:

~~~text
JOSE:
    R[32 bytes] || S[32 bytes]
    Total = 64 bytes

DER:
    SEQUENCE
      INTEGER(length varies, positive signed encoding)
      INTEGER(length varies, positive signed encoding)
    Total length varies
~~~

Hai chữ ký có thể chứa cùng giá trị r và s, nhưng DER có tag/length và quy tắc INTEGER; JOSE chỉ ghép hai octet string có độ rộng cố định. Không thể chỉ đổi tên định dạng hoặc Base64URL encode lại để chuyển đổi.

## 4. Vị trí chữ ký trong JWS Compact Serialization

JWS Compact Serialization gồm ba phần Base64URL:

~~~text
BASE64URL(protected-header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Với ECDSA, phần signature là Base64URL encoding không padding của chuỗi byte JOSE R || S, không phải ASN.1 DER.

Ví dụ header:

~~~json
{
  "alg": "ES256",
  "kid": "ec-signing-2026",
  "typ": "JWT"
}
~~~

Signing input chính xác là:

~~~text
ASCII(
  BASE64URL(UTF8(protected-header))
  || "."
  || BASE64URL(payload-bytes)
)
~~~

Chữ ký được tạo trên signing input này theo thuật toán ES256. Sau đó byte signature JOSE được Base64URL encode và nối thành compact token.

### 4.1. Không ký JSON object trừu tượng

Verifier phải dùng chính xác các byte signing input trong JWS. Không decode JSON rồi serialize lại header hoặc payload trước khi verify. Việc serialize lại có thể thay đổi:

- Thứ tự member.
- Khoảng trắng.
- Escape sequence.
- Cách biểu diễn số.
- Encoding Unicode.

Các biểu diễn JSON khác nhau có thể mang cùng ý nghĩa ở tầng ứng dụng nhưng tạo ra byte khác nhau và chữ ký khác nhau. JWS xác minh byte được ký, không xác minh một object JSON đã được chuẩn hóa ngầm.

### 4.2. Base64URL không phải bước chuyển đổi DER

Base64URL chỉ biến byte thành chuỗi ký tự để truyền trong compact serialization. Nó không chuyển ASN.1 DER thành JOSE raw.

Sai:

~~~text
JWS signature segment = BASE64URL(DER_signature)
~~~

Đúng:

~~~text
JWS signature segment = BASE64URL(R_fixed_width || S_fixed_width)
~~~

Nếu API ký trả DER, phải chuyển DER sang JOSE raw trước khi Base64URL encode. Nếu API verify nhận DER, phải chuyển JOSE raw sang DER trước khi gọi API đó.

## 5. Chuyển đổi DER sang JOSE raw

Chuyển đổi phải thực hiện trên cấu trúc ASN.1 đã parse và kiểm tra, không cắt byte theo offset giả định.

Quy trình khái quát:

1. Parse DER như một ASN.1 SEQUENCE.
2. Yêu cầu sequence chứa đúng hai INTEGER là R và S.
3. Xác nhận encoding DER hợp lệ/canonical theo parser và policy.
4. Xác nhận R và S là số nguyên dương, khác zero và nhỏ hơn bậc của nhóm đường cong.
5. Lấy biểu diễn unsigned big-endian của từng giá trị.
6. Loại bỏ byte zero dẫn đầu chỉ phục vụ biểu diễn số dương trong DER.
7. Left-pad mỗi giá trị bằng byte zero đến đúng độ rộng của curve.
8. Ghép hai phần theo thứ tự R rồi S.

~~~text
function derToJose(derSignature, width, curveOrder):
    sequence = strictDerParseSequence(derSignature)
    require sequence has exactly two INTEGER values

    r = parsePositiveInteger(sequence.r)
    s = parsePositiveInteger(sequence.s)

    require 1 <= r < curveOrder
    require 1 <= s < curveOrder

    rBytes = unsignedBigEndian(r)
    sBytes = unsignedBigEndian(s)

    require length(rBytes) <= width
    require length(sBytes) <= width

    rFixed = leftPadWithZero(rBytes, width)
    sFixed = leftPadWithZero(sBytes, width)

    return rFixed || sFixed
~~~

Điểm quan trọng là bỏ byte 00 chỉ khi nó là sign-padding của DER INTEGER. Không được xóa mọi byte zero ở đầu sau khi đã chuyển sang fixed-width, vì zero đầu là một phần bắt buộc của biểu diễn JOSE.

## 6. Chuyển đổi JOSE raw sang DER

Chiều ngược lại cũng cần parse đúng độ rộng:

1. Xác định curve/width từ alg đã được policy cho phép.
2. Yêu cầu signature có đúng 2 * width byte.
3. Chia chính xác thành R và S.
4. Parse mỗi nửa như unsigned big-endian integer.
5. Kiểm tra 1 <= r < n và 1 <= s < n, trong đó n là bậc nhóm.
6. Mã hóa mỗi giá trị thành ASN.1 DER INTEGER dương canonical.
7. Bọc hai INTEGER trong ASN.1 DER SEQUENCE.
8. Truyền DER signature cho API mật mã nếu API đó yêu cầu DER.

~~~text
function joseToDer(joseSignature, width, curveOrder):
    require length(joseSignature) == 2 * width

    rBytes = joseSignature[0 : width]
    sBytes = joseSignature[width : 2 * width]

    r = unsignedBigEndian(rBytes)
    s = unsignedBigEndian(sBytes)

    require 1 <= r < curveOrder
    require 1 <= s < curveOrder

    rInteger = derEncodePositiveInteger(r)
    sInteger = derEncodePositiveInteger(s)

    return derEncodeSequence(rInteger, sInteger)
~~~

derEncodePositiveInteger phải tạo encoding DER canonical: bỏ zero đầu không cần thiết và thêm một byte 00 khi bit cao nhất của byte đầu tiên là 1 để INTEGER không bị hiểu là âm. Với P-521, sequence DER có thể cần dạng length nhiều byte vì tổng nội dung có thể vượt 127 byte.

### 6.1. Không dùng độ dài DER cố định

Không giả định ES256 DER luôn dài 70 hoặc 71/72 byte, ES384 luôn dài một số byte cố định, hoặc ES512 luôn có một kích thước cố định. Giá trị R/S và sign-padding ảnh hưởng độ dài. Parser phải đọc tag và length theo ASN.1 DER.

Không chấp nhận một cấu trúc có INTEGER thứ ba, trailing bytes, INTEGER âm, encoding không canonical hoặc giá trị nằm ngoài miền hợp lệ.

## 7. Độ rộng cố định và leading zero

Một lỗi chuyển đổi phổ biến là loại bỏ zero đầu của R hoặc S rồi ghép trực tiếp. Điều này làm chữ ký ngắn hơn độ dài JOSE yêu cầu và khiến điểm chia R/S sai.

Ví dụ với ES256:

~~~text
R mathematical value:
    0x012345...

R JOSE:
    32-byte unsigned big-endian
    left-pad with 0x00 when needed

S JOSE:
    32-byte unsigned big-endian
    left-pad with 0x00 when needed

Signature:
    R[32] || S[32] = 64 bytes
~~~

DER INTEGER lại dùng độ dài tối thiểu để biểu diễn số dương. Nếu giá trị có byte đầu 0x80 đến 0xFF, DER thêm 0x00 để giữ dấu dương. Byte này không thuộc giá trị toán học.

Đối với P-521:

- Độ rộng JOSE của R và S là 66 byte.
- Không được dùng 65 byte chỉ vì nhiều thư viện hiển thị số nguyên theo số bit gần nhất.
- Giá trị nhỏ hơn 2^520 có thể cần zero padding ở đầu để đủ 66 byte.
- Vì P-521 chỉ cần 521 bit trong trường 528 bit, byte đầu của số R/S luôn có các bit cao bằng zero; INTEGER DER của giá trị hợp lệ có thể dài tối đa 66 byte. Tuy nhiên, SEQUENCE chứa hai INTEGER có thể vượt 127 byte và cần dạng length nhiều byte.

## 8. JWK key representation khác signature representation

JWK EC thường biểu diễn public key bằng:

- kty: loại khóa, thường là EC.
- crv: đường cong, ví dụ P-256, P-384, P-521.
- x, y: tọa độ public.
- d: tham số private nếu JWK chứa private key; không được công bố trong JWKS public.

x, y là Base64urlUInt theo quy tắc JWK, còn chữ ký JOSE ECDSA là hai phần fixed-width. Không dùng cùng một hàm encode/decode cho cả hai nếu hàm không thể hiện rõ quy tắc biểu diễn.

Với Base64urlUInt, số nguyên được biểu diễn bằng số byte tối thiểu cần thiết. Khi tạo EC public key cho API yêu cầu tọa độ đúng độ rộng, cần chuyển về độ rộng curve tương ứng. Với signature JOSE, R và S luôn có độ rộng cố định theo thuật toán.

Không nhầm:

| Dữ liệu | Biểu diễn thường gặp |
| --- | --- |
| JWK x, y | Base64urlUInt của tọa độ public |
| JWK d | Base64urlUInt của tham số private; phải giữ bí mật |
| JWS ECDSA signature | Fixed-width R || S, rồi Base64URL |
| API ECDSA signature | Có thể là ASN.1 DER hoặc raw P1363 tùy API |
| EC private key file | PEM/DER container như PKCS#8 hoặc định dạng khác |
| EC public key file | PEM/DER container như SubjectPublicKeyInfo hoặc định dạng khác |

PEM, PKCS#8 và SubjectPublicKeyInfo mô tả container/encoding của key. Chúng không tự cho biết chữ ký đầu ra dùng DER hay JOSE raw.

Raw ECDSA theo IEEE P1363 thường cũng là hai số unsigned fixed-width ghép R || S. Nếu API thực sự dùng quy ước P1363, cùng curve, cùng độ rộng và cùng thứ tự big-endian, byte signature có thể tương thích trực tiếp với JOSE mà không cần chuyển đổi DER. Vẫn phải kiểm tra tài liệu API và test vector; tên “raw” đơn lẻ chưa đủ để kết luận định dạng.

## 9. Phân biệt API nhận message và API nhận digest

Ngoài định dạng signature, API có thể khác nhau ở điểm băm dữ liệu.

### 9.1. API ký message

Một API cấp cao có thể nhận message bytes và tự áp dụng hash được chọn:

~~~text
signature = sign(messageBytes, ECDSA_P256_SHA256)
~~~

Trong trường hợp này, caller truyền đúng JWS Signing Input. Không tự SHA-256 trước nếu API sẽ tự hash, nếu không sẽ ký trên SHA-256 của digest thay vì trên signing input theo ES256.

### 9.2. API ký digest

Một API cấp thấp có thể yêu cầu digest đã tính:

~~~text
digest = SHA256(jwsSigningInput)
signature = signDigest(privateKey, digest)
~~~

Chỉ dùng API digest-level khi hợp đồng xác định rõ nó mong đợi digest nào và không tự hash lần nữa. Cần kiểm tra API có tự truncation digest theo quy tắc ECDSA/curve hay caller phải xử lý.

### 9.3. Tránh double hashing và hash mismatch

Các lỗi thường gặp:

- Hash signing input trước rồi truyền vào API SignData vốn tự hash.
- Truyền raw JSON payload thay vì JWS Signing Input.
- Băm chuỗi compact JWT hoàn chỉnh, bao gồm cả signature segment.
- Dùng SHA-256 cho ES384/ES512.
- Một bên ký digest, bên kia verify message.

Kiểm thử cần chứng minh cả hai phía dùng cùng signing input và cùng quy tắc hash.

## 10. ECDSA nonce k và tính an toàn của quá trình ký

ECDSA dùng một giá trị nonce bí mật tạm thời k cho mỗi lần ký. Nonce này khác với JWT claim jti, OAuth nonce hoặc DPoP server nonce.

Nếu cùng private key tái sử dụng cùng k cho hai thông điệp khác nhau, hoặc nonce có thể đoán/thiên lệch, attacker có thể suy ra private key từ các chữ ký. Vì vậy:

- Nguồn ngẫu nhiên phải đủ mạnh nếu API dùng nonce ngẫu nhiên.
- Không tự triển khai sinh k bằng PRNG thông thường.
- Không tái sử dụng nonce giữa các lần ký.
- Bảo vệ khỏi side-channel và lỗi triển khai trong thiết bị ký.
- Ưu tiên thư viện/cryptographic module được duy trì và có kiểm chứng.

RFC 6979 định nghĩa cách tạo nonce ECDSA xác định từ private key và digest, giúp tránh phụ thuộc vào random nonce cho mỗi lần ký. Chữ ký xác định theo RFC 6979 vẫn là chữ ký ECDSA hợp lệ; tuy nhiên, việc hai bên có cùng deterministic implementation không phải điều kiện để xác minh lẫn nhau.

Hai chữ ký ECDSA khác byte vẫn có thể hợp lệ cho cùng signing input và public key vì nonce k có thể khác nhau. Interoperability test phải kiểm tra verify thành công, không yêu cầu hai lần ký tạo ra chuỗi signature giống hệt nhau.

## 11. High-S/low-S và tính chuẩn hóa chữ ký

Với một chữ ký ECDSA hợp lệ (r, s), cặp (r, n - s) cũng có thể xác minh hợp lệ trong cùng nhóm, với n là bậc của nhóm. Đây là một dạng signature malleability: một thông điệp có thể có nhiều biểu diễn chữ ký hợp lệ.

Một số giao thức hoặc hệ sinh thái áp dụng quy tắc low-S để chọn một biểu diễn chuẩn, thường yêu cầu s <= n/2. Tuy nhiên, không nên tự áp đặt quy tắc low-S lên mọi JWS ECDSA nếu token profile hoặc giao thức không yêu cầu.

Khi tích hợp:

- Xác định verifier có enforce low-S hay không.
- Không giả định mọi API ký đều normalize S giống nhau.
- Nếu profile yêu cầu low-S, normalize hoặc reject theo đúng contract và test hai phía.
- Không thay đổi S tùy tiện sau khi ký mà không hiểu tác động đến chữ ký và semantics.
- Không dùng signature bytes làm định danh duy nhất của thông điệp nếu hệ thống phải chịu được malleability.

Đối với JWT, nên dùng claims/identifier phù hợp như jti và trạng thái nghiệp vụ để nhận diện token/operation, không dựa vào hash của signature bytes như một định danh logic duy nhất.

## 12. Ràng buộc thuật toán, curve và key

Khi verify JWS, thuật toán trong JOSE header là dữ liệu đầu vào. Verifier phải có allowlist và ràng buộc key với algorithm/curve.

Ví dụ các điều kiện cho ES256:

- JWS alg là ES256.
- JWK kty là EC.
- JWK crv là P-256.
- Public key có tọa độ hợp lệ trên curve.
- Key được phép dùng cho verify/sign theo metadata và policy.
- Hash là SHA-256.
- Signature segment decode thành đúng 64 byte JOSE raw.

Tương tự, ES384 phải dùng P-384/SHA-384/96-byte signature; ES512 phải dùng P-521/SHA-512/132-byte signature.

Không:

- Dùng khóa P-256 để xác minh token khai báo ES384.
- Chấp nhận alg chỉ vì API mật mã có thể thử một số thuật toán.
- Dùng private JWK lấy từ token làm nguồn khóa tin cậy.
- Lấy public key từ URL tùy ý trong header.
- Dùng cùng key ID cho nhiều issuer mà không namespace theo issuer.
- Tự fallback từ ES256 sang thuật toán khác khi verify thất bại.

## 13. Quy trình tích hợp giữa JOSE và API mật mã

### 13.1. Khi ký JWS bằng API mật mã trả DER

~~~text
1. Tạo protected header và payload bytes.
2. Base64URL encode header và payload theo JWS.
3. Tạo signing input chính xác: encodedHeader + "." + encodedPayload.
4. Ký signing input bằng đúng curve và hash theo ES alg.
5. Nhận DER signature từ crypto API.
6. Parse DER và kiểm tra R/S.
7. Chuyển R/S thành fixed-width JOSE raw.
8. Base64URL encode raw signature, không padding.
9. Ghép ba phần thành JWS Compact Serialization.
~~~

### 13.2. Khi verify JWS bằng API mật mã nhận DER

~~~text
1. Parse compact JWS và giới hạn kích thước đầu vào.
2. Đọc header chưa xác minh; chỉ dùng để chọn profile/key trong cấu hình tin cậy.
3. Kiểm tra alg được allowlist và curve/key tương ứng.
4. Decode signature segment từ Base64URL.
5. Kiểm tra độ dài raw signature là 2 * curveWidth.
6. Tách R và S, kiểm tra miền giá trị.
7. Chuyển JOSE raw thành ASN.1 DER canonical.
8. Tạo đúng signing input từ hai phần compact đầu.
9. Gọi crypto API verify với đúng curve/hash/key.
10. Nếu chữ ký hợp lệ, tiếp tục validate iss, aud, exp, nbf, typ và profile.
~~~

Nếu thư viện JOSE đã xử lý chuyển đổi raw/DER nội bộ, không chuyển đổi lần thứ hai. Chỉ thêm adapter khi ranh giới API thực sự yêu cầu.

## 14. Các lỗi tích hợp phổ biến

| Lỗi | Nguyên nhân | Biểu hiện/cách xử lý |
| --- | --- | --- |
| Đưa DER trực tiếp vào JWS | JOSE yêu cầu fixed-width R||S | Chuyển DER sang raw trước Base64URL |
| Đưa raw JOSE vào API chỉ nhận DER | API parser chờ ASN.1 SEQUENCE | Chuyển raw sang DER canonical |
| Signature dài sai | Sai curve hoặc bỏ leading zero | Kiểm tra độ dài 64/96/132 byte |
| R/S bị đảo | Adapter ghép sai thứ tự | Luôn dùng R trước S |
| Mất zero padding | Cắt zero đầu trong fixed-width raw | Left-pad từng số đúng độ rộng |
| DER INTEGER bị âm | Không xử lý sign-padding | Parse INTEGER dương canonical |
| Dùng SHA-256 cho mọi ES alg | Không ràng buộc hash theo alg | ES256/384/512 dùng đúng hash |
| Double hashing | Dùng API message và tự băm trước | Chọn message API hoặc digest API |
| Ký payload thay signing input | Không tuân theo JWS | Ký đúng encodedHeader + "." + encodedPayload |
| Re-serialize JSON khi verify | Signing bytes thay đổi | Dùng nguyên compact signing input |
| Dùng curve alias sai | Nhầm curve tương tự | Kiểm tra tham số curve, không chỉ tên |
| So sánh byte signature của hai lần ký | ECDSA có nonce khác nhau | Verify kết quả, không so byte |
| Tự áp low-S | Hai phía khác policy | Chốt profile và kiểm thử tương thích |
| Chấp nhận DER malformed | Parser quá dễ dãi | Strict DER parsing và kiểm tra miền R/S |

## 15. Kiểm thử tương thích liên thư viện

Test interoperability nên có ít nhất hai hướng:

- Bên JOSE ký, API mật mã xác minh.
- API mật mã ký, bên JOSE xác minh.

Thực hiện riêng cho từng thuật toán/curve được triển khai.

### 15.1. Ma trận kiểm thử

| Test | ES256 | ES384 | ES512 | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| JOSE sign → JOSE verify | Có | Có | Có | Thành công |
| JOSE sign → API verify | Có | Có | Có | Thành công sau adapter nếu cần |
| API sign → JOSE verify | Có | Có | Có | Thành công sau adapter nếu cần |
| DER signature bị đưa trực tiếp vào JWS | Có | Có | Có | Bị phát hiện/từ chối |
| Raw signature đưa vào DER-only API | Có | Có | Có | Adapter chuyển đổi trước verify |
| Signature thiếu byte leading zero | Có | Có | Có | Từ chối độ dài sai |
| Signature thừa byte | Có | Có | Có | Từ chối |
| R/S bằng zero hoặc ngoài bậc curve | Có | Có | Có | Từ chối |
| Sai hash hoặc sai curve | Có | Có | Có | Từ chối |
| Payload/header bị sửa | Có | Có | Có | Từ chối chữ ký |

### 15.2. Test vector và property test

Nên dùng test vector chuẩn từ RFC 7515 và RFC 7518, cùng test vector của thư viện/crypto provider đang tích hợp.

Property test hữu ích:

- DER sang JOSE rồi về DER giữ nguyên giá trị toán học R/S.
- JOSE sang DER rồi về JOSE tạo lại đúng chuỗi fixed-width ban đầu nếu đầu vào hợp lệ.
- Mọi signature JOSE được tạo ra có độ dài chính xác theo curve.
- DER malformed không được parser chấp nhận.
- Signature hợp lệ verify được ở thư viện độc lập thứ hai.
- Signature bytes bị sửa phải verify thất bại.

Không yêu cầu sign(message) chạy hai lần phải tạo byte giống nhau. Với ECDSA dùng nonce ngẫu nhiên, chữ ký có thể khác nhau nhưng đều verify thành công. Nếu hệ thống yêu cầu deterministic signature, đó là yêu cầu riêng về cách sinh nonce, không phải điều kiện interoperability cơ bản.

## 16. Kiểm tra lỗi và giới hạn đầu vào

Chữ ký là dữ liệu không đáng tin cậy. Adapter phải từ chối dữ liệu sai trước khi gọi crypto API hoặc phải xử lý exception theo hướng fail-closed.

Kiểm tra:

- Base64URL sai định dạng hoặc vượt giới hạn kích thước.
- JWS không có đúng ba phần compact.
- Signature segment decode ra độ dài không đúng.
- DER thiếu SEQUENCE/INTEGER, length sai hoặc có trailing bytes.
- INTEGER âm, zero, vượt độ rộng hoặc vượt bậc curve.
- DER có encoding không canonical.
- Key curve không khớp alg.
- Public key không nằm trên curve hoặc tham số không hợp lệ.
- Header có alg không được cho phép.
- kid không thuộc key set của issuer tin cậy.

Không thử lần lượt DER, raw, nhiều curve hoặc nhiều hash cho đến khi một cách verify thành công. Tự động dò định dạng làm mờ contract, mở rộng bề mặt tấn công và có thể tạo cách diễn giải khác nhau giữa các verifier.

## 17. Di trú từ API ECDSA hiện có sang JOSE

Khi chuyển một hệ thống ký ECDSA hiện hữu sang JWT/JWS, cần kiểm kê rõ:

1. Curve và key pair hiện tại.
2. Hash đang được API áp dụng.
3. API nhận message hay digest.
4. Signature output là DER hay raw P1363.
5. Public key được phân phối dưới PEM, DER hay JWK.
6. JOSE alg tương ứng có được hỗ trợ không.
7. Adapter chuyển đổi nằm ở bên ký, bên verify hay thư viện JOSE.
8. Cách rotation và kid được quản lý.
9. Consumer nào cần cập nhật và thứ tự rollout.

Không đổi đồng thời curve, hash, key format, signature format và token profile nếu không cần thiết. Di trú theo từng bước giúp xác định lỗi tương thích.

### 17.1. Chiến lược rollout

- Tạo key mới hoặc xác định key hiện có có đúng curve/profile không.
- Công bố public JWK phù hợp, không công bố private parameter.
- Bổ sung adapter/JOSE library và kiểm thử hai chiều.
- Chạy shadow verification trên token test hoặc traffic được kiểm soát; không dùng kết quả shadow để cấp quyền.
- Triển khai verifier hỗ trợ key/alg mới trước khi issuer bắt đầu phát hành token.
- Phát hành token mới với alg, kid và profile rõ ràng.
- Theo dõi lỗi verify theo issuer, kid, alg và consumer.
- Loại bỏ đường xác minh cũ sau khi hết thời gian chuyển tiếp và token cũ không còn được chấp nhận.

Nếu cần hỗ trợ đồng thời token cũ và mới, dùng allowlist profile rõ ràng. Không cho phép một token tự chọn format hoặc thuật toán bất kỳ.

## 18. Quan sát vận hành và xử lý sự cố

Khi chữ ký không tương thích, log/metric nên phân biệt:

- Signature length mismatch.
- JOSE raw/DER format mismatch.
- ASN.1 parse failure.
- Curve/key mismatch.
- Algorithm/hash mismatch.
- Signature verification failure.
- Unknown kid/key lookup failure.
- Issuer/audience/profile validation failure.

Không ghi private key, raw token hoặc toàn bộ signature/payload nhạy cảm vào log. Có thể ghi alg, kid, issuer đã chuẩn hóa, độ dài signature và mã lỗi kỹ thuật. Hạn chế log chi tiết parser ở môi trường production để tránh lộ dữ liệu hoặc tạo log injection.

Một lỗi format thường xuất hiện đồng loạt ở một nhóm consumer sau khi rollout thư viện hoặc adapter. Theo dõi tỷ lệ lỗi theo phiên bản producer/consumer giúp khoanh vùng nhanh hơn.

## 19. Tình huống tự kiểm tra

Issuer phát hành JWS với alg=ES256. API mật mã của một consumer nhận message bytes và trả về chữ ký ASN.1 DER. Nhóm tích hợp Base64URL encode trực tiếp byte DER thành signature segment. Một consumer JOSE khác từ chối mọi token, dù public key và curve đều là P-256.

**Câu hỏi 1:** Vì sao chữ ký bị từ chối?

**Trả lời:** JWS ECDSA yêu cầu signature segment là Base64URL của R || S với mỗi phần 32 byte. Consumer đang nhận Base64URL của ASN.1 DER SEQUENCE, nên định dạng và độ dài không đúng JOSE.

**Câu hỏi 2:** Có cần đổi private/public key không?

**Trả lời:** Không nhất thiết. Nếu key pair là P-256 hợp lệ và hash là SHA-256, có thể giữ key và chuyển DER signature sang JOSE raw bằng adapter đúng chuẩn. Cần xác nhận API thực sự ký đúng JWS Signing Input.

**Câu hỏi 3:** Nếu bỏ zero đầu của R/S để rút ngắn DER thì có đúng không?

**Trả lời:** Không được thao tác bằng cách cắt byte tùy tiện. DER phải được parse theo ASN.1; JOSE raw phải left-pad mỗi số về đúng 32 byte. Zero đầu có ý nghĩa khác nhau trong hai định dạng.

**Câu hỏi 4:** Hai lần ký cùng payload có bắt buộc tạo signature bytes giống nhau không?

**Trả lời:** Không. ECDSA có thể dùng nonce k khác nhau và tạo các chữ ký khác byte nhưng đều hợp lệ. Kiểm tra tương thích bằng verify, không bằng so sánh byte chữ ký.

## 20. Ghi nhớ

JOSE ECDSA và nhiều API mật mã dùng cùng thuật toán toán học nhưng có thể khác định dạng byte. JWS yêu cầu chữ ký raw R || S với độ rộng cố định: 64 byte cho ES256, 96 byte cho ES384 và 132 byte cho ES512. Nhiều API trả ASN.1 DER có độ dài biến đổi.

Muốn liên thông, phải chuyển đổi DER/raw đúng quy tắc, giữ leading zero theo đúng định dạng, ràng buộc curve/hash với JOSE alg và ký chính xác JWS Signing Input. Cũng cần phân biệt API nhận message với API nhận digest, quản lý nonce ECDSA an toàn và không so sánh byte giữa các chữ ký ECDSA khác lần ký.

**Tương thích ECDSA không chỉ là cùng curve và cùng hash; nó còn là cùng dữ liệu được ký, cùng quy tắc xử lý digest và đúng định dạng chữ ký ở ranh giới JOSE/API.**

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS Signing Input, Compact Serialization và test vector ECDSA.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): cấu trúc JWK/JWKS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): ES256, ES384, ES512 và định dạng ECDSA signature trong JOSE.
- [RFC 6979 — Deterministic Usage of the Digital Signature Algorithm (DSA) and Elliptic Curve Digital Signature Algorithm (ECDSA)](https://www.rfc-editor.org/rfc/rfc6979): sinh nonce ECDSA xác định.
- [SEC 1 — Elliptic Curve Cryptography](https://www.secg.org/sec1-v2.pdf): biểu diễn và thao tác chữ ký/khóa elliptic curve.
- [ITU-T X.690 — ASN.1 encoding rules](https://www.itu.int/rec/T-REC-X.690): BER/CER/DER và encoding ASN.1.
