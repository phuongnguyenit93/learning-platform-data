# Định dạng chữ ký ECDSA trong JOSE và lỗi chuyển đổi giữa hệ thống

## 1. Vì sao định dạng chữ ký ECDSA dễ gây lỗi liên thông?

ECDSA tạo chữ ký từ hai số nguyên `r` và `s`. Tuy nhiên, các thư viện mật mã không phải lúc nào cũng trả hai số này theo cùng một cách:

- Nhiều API mật mã tổng quát trả chữ ký dưới dạng **ASN.1 DER**, một cấu trúc có độ dài biến thiên.
- Một số API trả dạng **IEEE P1363**, tức nối hai số nguyên thành các trường có độ rộng cố định.
- **JOSE/JWS yêu cầu dạng nối cố định `R || S`**, không phải ASN.1 DER.

Nếu issuer lấy DER rồi Base64URL trực tiếp để tạo JWT, verifier tuân thủ JWS có thể từ chối chữ ký. Ngược lại, nếu verifier đưa raw `R || S` vào API chỉ nhận DER, xác minh cũng thất bại. Đây là lỗi tích hợp định dạng, không nhất thiết là lỗi khóa hoặc thuật toán ECDSA.

Bài học thuộc chương **Thuật toán chữ ký** của module **Security - JSON Web Token (JWT)**. Phạm vi tập trung vào định dạng chữ ký ECDSA trong JOSE, chuyển đổi DER và raw, xử lý byte đầu, độ dài, kiểm tra miền giá trị và kiểm thử liên thông. Nội dung áp dụng chung, không phụ thuộc ngôn ngữ lập trình hay framework.

## 2. ECDSA tạo ra hai số nguyên R và S

### 2.1. Chữ ký toán học

ECDSA ký thông điệp bằng private key và tạo ra một cặp số nguyên:

~~~text
signature = (r, s)
~~~

Hai giá trị này thuộc miền số nguyên modulo cấp `n` của điểm sinh đường cong:

~~~text
1 <= r < n
1 <= s < n
~~~

Public key và đường cong tương ứng được dùng để xác minh cặp `(r,s)`. Các số này không phải hai tọa độ X/Y của public key; cũng không phải hai digest độc lập.

### 2.2. Mỗi đường cong có độ rộng khác nhau

Trong JWS, mỗi số nguyên được mã hóa thành số byte cố định theo độ rộng của đường cong:

| JWS `alg` | Đường cong | Độ rộng mỗi số R/S | Độ dài chữ ký |
| --- | --- | ---: | ---: |
| `ES256` | P-256 | 32 byte | 64 byte |
| `ES384` | P-384 | 48 byte | 96 byte |
| `ES512` | P-521 | 66 byte | 132 byte |

Với P-521, cần 66 byte để chứa một số nguyên 521 bit. Hai trường R và S do đó chiếm tổng cộng 132 byte.

### 2.3. JWS không lưu cặp số dưới dạng JSON

JWS không đặt `r` và `s` thành hai trường JSON, cũng không dùng chuỗi hex có dấu phân cách. Hai số được mã hóa thành byte theo quy tắc chuẩn rồi nối trực tiếp:

~~~text
signatureBytes = I2OSP(r, width) || I2OSP(s, width)
~~~

Trong đó:

- `I2OSP` chuyển số nguyên không dấu thành chuỗi byte có độ rộng cố định.
- Byte được sắp theo thứ tự **big-endian**.
- Nếu số nguyên cần ít byte hơn độ rộng quy định, thêm các byte `0x00` ở bên trái.
- `||` biểu thị phép nối byte.

## 3. Định dạng ECDSA trong JOSE/JWS

### 3.1. Raw fixed-width R || S

Theo RFC 7518, mục 3.4, chữ ký ECDSA của JWS là hai chuỗi octet có độ dài bằng nhau, nối lại thành một chuỗi duy nhất:

~~~text
R = I2OSP(r, width)
S = I2OSP(s, width)
JWS_signature = R || S
~~~

Độ dài bắt buộc:

| Thuật toán | Raw signature sau khi giải mã Base64URL |
| --- | ---: |
| ES256 | Chính xác 64 byte |
| ES384 | Chính xác 96 byte |
| ES512 | Chính xác 132 byte |

Định dạng này thường được gọi là **raw ECDSA**, **P1363** hoặc **IEEE P1363 fixed-width** trong tài liệu của một số thư viện. Khi dùng các tên này, vẫn cần kiểm tra tài liệu API để chắc chắn byte đầu ra đúng thứ tự R trước, S sau và đúng độ rộng JWS.

### 3.2. ASN.1 DER là gì?

DER là một cách mã hóa dữ liệu ASN.1 theo quy tắc Distinguished Encoding Rules. Chữ ký ECDSA DER thường có cấu trúc:

~~~text
SEQUENCE {
    INTEGER r
    INTEGER s
}
~~~

Mỗi INTEGER là số nguyên có dấu theo biểu diễn two's complement. Vì R và S của ECDSA phải là số dương, DER có thể cần một byte `0x00` ở đầu INTEGER để biểu diễn số dương nếu byte dữ liệu đầu tiên có bit cao nhất bằng 1.

Ví dụ cấu trúc minh họa:

~~~text
30 <sequence-length>
   02 <r-length> <r-integer-bytes>
   02 <s-length> <s-integer-bytes>
~~~

Các byte `30`, `02` là tag ASN.1 thường gặp cho SEQUENCE và INTEGER. Độ dài được mã hóa theo quy tắc DER. Nếu độ dài phần nội dung lớn hơn 127 byte, DER dùng dạng long-form length; chữ ký P-521 có thể rơi vào trường hợp này.

**Độ dài DER thay đổi** theo cách biểu diễn R và S. Một INTEGER có thể cần byte dấu `0x00`, còn INTEGER khác thì không. Do đó DER không có độ dài cố định 64/96/132 byte như chữ ký JWS.

### 3.3. DER và raw P1363 không thể dùng thay thế trực tiếp

| Đặc điểm | ASN.1 DER | JOSE raw R \|\| S |
| --- | --- | --- |
| Cấu trúc | SEQUENCE chứa hai INTEGER | Hai trường byte nối trực tiếp |
| Độ dài | Biến thiên | Cố định theo đường cong |
| INTEGER | Có quy tắc dấu và độ dài DER | Không dấu, big-endian, độ rộng cố định |
| Byte `0x00` đầu | Có thể là byte dấu bắt buộc | Có thể là byte đệm để đủ độ rộng |
| Dùng trực tiếp trong JWS | Không | Có |
| Dùng trực tiếp với API chỉ nhận DER | Có | Không, trừ khi API hỗ trợ P1363 |

Không được Base64URL toàn bộ DER rồi coi đó là đoạn chữ ký JWS. Cũng không được cắt bỏ hai byte tag đầu hoặc chia DER thành hai nửa theo độ dài cố định. Cần parse ASN.1 đúng chuẩn và chuyển đổi R/S.

## 4. Quy tắc chuyển đổi DER sang JOSE raw R || S

### 4.1. Xác định độ rộng theo thuật toán

Trước khi chuyển đổi, xác định thuật toán JWS từ cấu hình tin cậy và curve của khóa:

| `alg` | Curve | Width |
| --- | --- | ---: |
| ES256 | P-256 | 32 byte |
| ES384 | P-384 | 48 byte |
| ES512 | P-521 | 66 byte |

Không chọn width bằng cách đoán từ độ dài DER. DER có độ dài biến thiên và có thể có nhiều biểu diễn tùy độ dài R/S.

### 4.2. Parse DER nghiêm ngặt

Quy trình DER sang raw:

1. Parse một DER SEQUENCE hoàn chỉnh.
2. Xác nhận SEQUENCE chỉ chứa đúng hai INTEGER: R và S.
3. Xác nhận length encoding là DER hợp lệ, definite length và tối giản theo DER.
4. Xác nhận không còn byte thừa sau SEQUENCE.
5. Xác nhận R và S là số nguyên dương, không rỗng, không âm và không có leading zero dư thừa.
6. Nếu INTEGER bắt đầu bằng `0x00`, chỉ bỏ byte đó khi nó là sign-padding cần thiết vì byte kế tiếp có bit cao nhất bằng 1.
7. Sau khi loại sign-padding hợp lệ, kiểm tra mỗi số không dài hơn width yêu cầu.
8. Thêm byte `0x00` ở bên trái để mỗi số đủ width.
9. Chuyển thành `R || S` và kiểm tra `1 <= r,s < n` theo order của curve.

Parser phải từ chối DER sai định dạng, INTEGER âm, INTEGER bằng 0, INTEGER quá dài, length không tối giản, thiếu INTEGER hoặc có byte thừa. Không cố “sửa” dữ liệu không hợp lệ để tạo chữ ký có vẻ đúng.

### 4.3. Vì sao phải xử lý byte 0x00 đầu?

DER INTEGER là số nguyên có dấu. Nếu byte đầu của giá trị dương có bit cao nhất bằng 1, DER thêm byte `0x00` để biểu diễn số dương:

~~~text
DER INTEGER:
00 A7 31 ...
   ^
   byte dấu, có thể bỏ khi chuyển sang số nguyên không dấu
~~~

Trong raw JWS, trường R/S là số nguyên **không dấu**. Byte `0x00` ở đầu raw có thể là byte đệm cần thiết để đạt độ rộng cố định; không được tự động xóa nó.

Có hai thao tác khác nhau:

- **DER -> raw:** bỏ đúng byte sign-padding của DER nếu có, rồi left-pad về width cố định.
- **Raw -> DER:** bỏ các byte zero ở đầu biểu diễn unsigned để lấy số nguyên tối giản, sau đó thêm một byte `0x00` nếu cần tránh diễn giải âm.

Nhầm hai thao tác này là nguyên nhân phổ biến làm mất byte hoặc tạo số nguyên sai.

### 4.4. Mã giả chuyển DER sang raw

~~~text
function derToJose(derSignature, width, curveOrder):
    sequence = parseStrictDerSequence(derSignature)
    require sequence.consumesAllInput
    require sequence.containsExactlyTwoIntegers

    rBytes = parsePositiveMinimalDerInteger(sequence.integer1)
    sBytes = parsePositiveMinimalDerInteger(sequence.integer2)

    require rBytes is not empty
    require sBytes is not empty

    r = OS2IP(rBytes)
    s = OS2IP(sBytes)
    require 1 <= r < curveOrder
    require 1 <= s < curveOrder

    require length(rBytes) <= width
    require length(sBytes) <= width

    R = leftPadWithZeroBytes(rBytes, width)
    S = leftPadWithZeroBytes(sBytes, width)

    return R || S
~~~

`parsePositiveMinimalDerInteger` phải thực hiện kiểm tra DER thực sự: từ chối INTEGER âm và leading zero dư thừa; chỉ bỏ byte `0x00` đầu nếu byte đó là sign-padding hợp lệ. Không nên viết parser DER tùy tiện bằng cách tìm tag byte `02` trong chuỗi.

## 5. Quy tắc chuyển đổi JOSE raw R || S sang DER

### 5.1. Tách hai trường cố định

Khi verifier dùng API chỉ nhận DER, cần chuyển chữ ký JWS raw sang DER:

1. Giải mã Base64URL của đoạn chữ ký.
2. Xác định width từ `alg` và curve đã được policy cho phép.
3. Kiểm tra tổng độ dài đúng bằng `2 * width`.
4. Lấy width byte đầu làm R và width byte tiếp theo làm S.
5. Chuyển từng trường từ unsigned big-endian thành số nguyên.
6. Kiểm tra `1 <= r,s < n`.
7. Mã hóa từng số thành DER INTEGER dương, tối giản.
8. Nối hai INTEGER vào DER SEQUENCE với length hợp lệ.
9. Đưa DER cho API xác minh ECDSA.

### 5.2. Mã giả chuyển raw sang DER

~~~text
function joseToDer(rawSignature, width, curveOrder):
    require length(rawSignature) == 2 * width

    R = rawSignature[0 : width]
    S = rawSignature[width : 2 * width]

    r = OS2IP(R)
    s = OS2IP(S)
    require 1 <= r < curveOrder
    require 1 <= s < curveOrder

    derR = encodeMinimalPositiveDerInteger(r)
    derS = encodeMinimalPositiveDerInteger(s)

    return encodeDerSequence(derR || derS)
~~~

`encodeMinimalPositiveDerInteger` phải:

- Bỏ các byte zero ở đầu của biểu diễn unsigned để tạo INTEGER tối giản.
- Giữ lại ít nhất một byte nếu cần biểu diễn giá trị.
- Thêm một byte `0x00` ở đầu nếu byte đầu tiên còn lại có bit cao nhất bằng 1.
- Ghi độ dài DER chính xác.

Nếu một thư viện hỗ trợ trực tiếp P1363/fixed-width signature, có thể truyền raw R||S trực tiếp và tránh bước chuyển đổi. Phải xác nhận chế độ API bằng tài liệu chính thức và kiểm thử, không dựa vào tên hàm chung chung.

## 6. Minh họa độ dài và lỗi byte đầu

### 6.1. ES256

ES256 dùng P-256 nên mỗi trường có 32 byte:

~~~text
raw signature:
+-------------------------------+-------------------------------+
| R: 32 bytes                   | S: 32 bytes                   |
+-------------------------------+-------------------------------+
|<---------------- 64 bytes total ------------------------------>|
~~~

Sau Base64URL không padding, đoạn chữ ký có 86 ký tự. DER thường dài khoảng 70-72 byte, nhưng độ dài thực tế có thể thay đổi do R/S cần hoặc không cần sign-padding.

### 6.2. ES384 và ES512

| Thuật toán | R | S | Raw tổng | Base64URL không padding |
| --- | ---: | ---: | ---: | ---: |
| ES256 | 32 byte | 32 byte | 64 byte | 86 ký tự |
| ES384 | 48 byte | 48 byte | 96 byte | 128 ký tự |
| ES512 | 66 byte | 66 byte | 132 byte | 176 ký tự |

Với ES512, DER có thể vượt 127 byte phần nội dung và cần long-form length. Parser chỉ hỗ trợ short-form length sẽ có thể hoạt động với ES256 nhưng thất bại với ES512.

### 6.3. Byte zero đầu trường raw không phải byte thừa

Giả sử R có giá trị cần 31 byte nhưng width của ES256 là 32 byte. Raw R phải có một byte `0x00` ở đầu để đạt 32 byte. Nếu bỏ byte đó, tổng chữ ký chỉ còn 63 byte và vị trí bắt đầu của S cũng bị lệch.

Ngược lại, DER INTEGER có thể bắt đầu bằng `0x00` vì quy tắc dấu. Byte đó không nhất thiết là một phần có ý nghĩa của giá trị unsigned. Chuyển đổi phải hiểu ngữ nghĩa của từng định dạng, không dùng thao tác trim zero chung.

## 7. Đặt chuyển đổi đúng vị trí trong luồng JWS

### 7.1. Khi ký JWT

Luồng ký đúng:

~~~text
header64 = BASE64URL(UTF8(protectedHeaderJSON))
payload64 = BASE64URL(UTF8(payloadJSON))
signingInput = ASCII(header64 + "." + payload64)

derSignature = ECDSA_SIGN(privateKey, signingInput, hash)
rawSignature = DER_TO_JOSE(derSignature, curveWidth)

jwt = header64 + "." + payload64 + "." + BASE64URL(rawSignature)
~~~

Nếu API ký đã trả raw P1363 đúng width, bỏ bước DER_TO_JOSE. Không chuyển đổi signing input hoặc payload; chỉ chuyển đổi **byte chữ ký**.

### 7.2. Khi xác minh JWT

Luồng xác minh:

~~~text
(header64, payload64, signature64) = parseJws(token)
header = parseProtectedHeader(BASE64URL_DECODE(header64))

require header.alg in configuredAllowlist
key = resolveTrustedKey(issuerPolicy, header.kid, header.alg)
rawSignature = BASE64URL_DECODE(signature64)

signingInput = ASCII(header64 + "." + payload64)
derSignature = JOSE_TO_DER(rawSignature, curveWidth, curveOrder)

require ECDSA_VERIFY(key, signingInput, derSignature, hash)
validateClaimsAndAuthorizationPolicy()
~~~

Nếu API xác minh nhận raw P1363, có thể bỏ bước JOSE_TO_DER. Không parse JSON rồi serialize lại để dựng signing input; phải dùng nguyên văn hai đoạn Base64URL đầu.

### 7.3. Sơ đồ chuyển đổi giữa issuer và verifier

~~~mermaid
flowchart TD
    A[Issuer tạo header64.payload64] --> B[Signing input]
    B --> C[Thư viện ECDSA]
    C --> D{Định dạng API ký}
    D -->|DER| E[DER sang raw R||S]
    D -->|P1363 raw| F[Kiểm tra fixed width]
    E --> G[Base64URL chữ ký]
    F --> G
    G --> H[JWS Compact]
    H --> I[Verifier giải mã Base64URL]
    I --> J{Định dạng API verify}
    J -->|Nhận DER| K[Raw R||S sang DER]
    J -->|Nhận raw| L[Kiểm tra fixed width]
    K --> M[ECDSA verify]
    L --> M
~~~

## 8. Các lỗi chuyển đổi phổ biến

| Lỗi | Nguyên nhân | Hậu quả | Cách xử lý |
| --- | --- | --- | --- |
| Đưa DER trực tiếp vào JWS | Nhầm DER với raw R||S | Verifier từ chối do sai định dạng/độ dài | Chuyển DER sang fixed-width raw |
| Đưa raw vào API chỉ nhận DER | Không chuyển đổi ngược | API parse ASN.1 thất bại | Raw sang DER đúng chuẩn |
| Cắt DER thành hai nửa | DER có tag/length và độ dài biến thiên | R/S sai hoàn toàn | Parse ASN.1 thay vì chia chuỗi |
| Bỏ mọi byte zero đầu | Nhầm sign-padding DER với padding raw | Mất độ rộng, lệch S hoặc đổi giá trị | Chỉ bỏ sign-padding DER hợp lệ; raw phải giữ width |
| Không thêm zero khi raw cần đủ width | Chuyển số nguyên không fixed-width | Chữ ký ngắn hơn quy định | Left-pad R/S về đúng width |
| Không xử lý DER long-form length | Parser chỉ giả định length một byte | ES512 có thể thất bại | Dùng parser DER chuẩn |
| Chấp nhận INTEGER âm hoặc zero | Parser lỏng | Giá trị R/S không hợp lệ | Kiểm tra INTEGER dương và miền giá trị |
| Không kiểm tra byte thừa | Chỉ parse phần đầu | Chấp nhận input mơ hồ | Yêu cầu parser tiêu thụ toàn bộ input |
| Dùng sai width | Nhầm ES512 với P-512 hoặc curve sai | Chữ ký sai độ dài | Lấy width từ JWA algorithm/curve |
| Nhầm thứ tự R và S | Thư viện hoặc adapter khác quy ước | Chữ ký không xác minh được | Chuẩn hóa R trước, S sau |
| So sánh chữ ký byte-for-byte giữa hai lần ký | ECDSA có thể dùng nonce khác nhau | Test sai dù cả hai chữ ký hợp lệ | Kiểm tra verify, không giả định byte giống nhau |

### 8.1. Không đoán định dạng chỉ bằng độ dài

Một adapter không nên thử DER, rồi nếu lỗi thì coi dữ liệu là raw, hoặc ngược lại. Cách tự động đoán dễ che giấu cấu hình sai và tạo hành vi khác nhau giữa các phiên bản.

Định dạng đầu ra của API phải được xác định rõ trong cấu hình/tích hợp:

- DER ASN.1.
- Raw/P1363 fixed-width.
- Một kiểu đóng gói riêng có tài liệu.

Sau khi xác định, kiểm tra độ dài và cấu trúc tương ứng. Nếu dữ liệu không khớp định dạng đã cấu hình, từ chối với lỗi rõ ràng.

### 8.2. Không nhầm lỗi chữ ký với lỗi claims

Verifier có thể báo token không hợp lệ vì nhiều nguyên nhân:

- Chuyển đổi DER/raw sai: lỗi định dạng hoặc xác minh mật mã.
- Public key không đúng: lỗi key selection.
- Curve/alg không khớp: lỗi cấu hình thuật toán.
- Chữ ký hợp lệ nhưng `iss`, `aud`, `exp` hoặc quyền sai: lỗi chính sách token.

Log vận hành nên phân loại lỗi nhưng không ghi private key, secret, toàn bộ token hoặc dữ liệu nhạy cảm. Khi debug, có thể ghi `kid`, `alg`, issuer đã cấu hình, độ dài chữ ký và mã lỗi an toàn.

## 9. Kiểm thử liên thông giữa thư viện

### 9.1. Ma trận API ký và xác minh

Lập ma trận cho mọi cặp signer/verifier quan trọng:

| Signer trả về | Verifier nhận | Xử lý cần có | Kết quả |
| --- | --- | --- | --- |
| DER | DER | Không cần chuyển đổi định dạng ở adapter | PASS |
| DER | Raw/P1363 | DER sang raw | PASS |
| Raw/P1363 | DER | Raw sang DER | PASS |
| Raw/P1363 | Raw/P1363 | Không cần chuyển đổi định dạng | PASS |
| DER | Raw nhưng gửi nguyên DER | Sai định dạng | FAIL |
| Raw | DER nhưng gửi nguyên raw | Sai định dạng | FAIL |

Các trường hợp PASS cần được kiểm tra bằng token thật và đúng curve. Không chỉ test hàm chuyển đổi riêng lẻ.

### 9.2. Test vector và trường hợp biên

Với mỗi curve, kiểm thử:

1. R/S có byte đầu high-bit bằng 1 khiến DER cần sign-padding.
2. R hoặc S có nhiều byte zero đầu trong độ rộng raw cố định.
3. R/S có độ dài tối thiểu sau khi bỏ sign-padding DER.
4. DER có short-form và long-form length hợp lệ.
5. DER có leading zero dư thừa, INTEGER âm hoặc INTEGER rỗng.
6. DER có thiếu R/S, thêm INTEGER thứ ba hoặc byte thừa.
7. Raw signature ngắn hơn hoặc dài hơn đúng width.
8. R/S bằng 0 hoặc lớn hơn/equal curve order.
9. Chữ ký được tạo ở một thư viện và xác minh ở thư viện khác.
10. Token bị sửa một byte sau khi ký.

Nên dùng test vector chuẩn của thuật toán và bổ sung test chuyển đổi. Không chỉ dựa vào một chữ ký ngẫu nhiên tình cờ không có byte đầu đặc biệt.

### 9.3. ECDSA không nhất thiết tạo cùng byte chữ ký

ECDSA có thể sử dụng nonce ngẫu nhiên, nên cùng một signing input và private key có thể tạo ra các cặp R/S khác nhau. Cả hai vẫn hợp lệ. Một số triển khai dùng nonce xác định theo RFC 6979, nhưng không nên giả định mọi thư viện đều làm như vậy.

Vì thế, kiểm thử liên thông nên:

- Ký ở hệ thống A, xác minh ở hệ thống B.
- Ký ở hệ thống B, xác minh ở hệ thống A.
- So sánh kết quả xác minh và claims, không mặc định chữ ký của hai lần ký phải giống byte-for-byte.
- Dùng test vector cố định khi cần kiểm tra kết quả mã hóa chính xác.

### 9.4. Kiểm thử đúng môi trường triển khai

Kiểm tra cùng phiên bản thư viện, crypto provider, runtime, container image và KMS/HSM được sử dụng ở production. Một thư viện có thể thay đổi mặc định định dạng chữ ký giữa phiên bản hoặc cung cấp các chế độ DER/P1363 khác nhau.

Ghi nhận:

- Tên và phiên bản thư viện JOSE/JWT.
- Tên và phiên bản API mật mã.
- Định dạng chữ ký API trả về/nhận vào.
- Curve và thuật toán JWS.
- Kích thước chữ ký trước/sau Base64URL.
- Kết quả test chéo và test âm tính.

## 10. Checklist triển khai

### 10.1. Phía issuer

- [ ] Đã xác định chính xác JWS `alg` và curve.
- [ ] Đã xác nhận API ký trả DER hay raw/P1363.
- [ ] Nếu API trả DER, đã chuyển thành raw fixed-width R||S.
- [ ] R và S được mã hóa unsigned big-endian.
- [ ] Mỗi trường có đúng width 32/48/66 byte.
- [ ] Đã kiểm tra miền giá trị R/S.
- [ ] Chỉ Base64URL sau khi có raw signature đúng chuẩn.
- [ ] Signing input là nguyên văn `header64.payload64`.

### 10.2. Phía verifier

- [ ] Đã allowlist `ES256`, `ES384` hoặc `ES512`.
- [ ] Public key thuộc đúng issuer và curve.
- [ ] Đoạn chữ ký được Base64URL decode nghiêm ngặt.
- [ ] Raw signature có đúng 64/96/132 byte.
- [ ] Nếu API chỉ nhận DER, đã chuyển raw sang DER chuẩn.
- [ ] DER parser từ chối INTEGER âm, length sai và byte thừa.
- [ ] Xác minh chữ ký trước khi tin claims.
- [ ] Kiểm tra `iss`, `aud`, `exp`, `nbf`, token type và quyền.

### 10.3. Toàn hệ thống

- [ ] Đã chạy test vector và test biên cho từng curve.
- [ ] Đã kiểm thử signer-verifier chéo.
- [ ] Đã xác nhận gateway và các service cùng hiểu định dạng.
- [ ] Đã kiểm thử trên đúng provider/KMS/HSM production.
- [ ] Đã phân loại lỗi định dạng, lỗi chữ ký và lỗi claims.
- [ ] Không log private key, secret hoặc token nhạy cảm.

## 11. Câu hỏi tự kiểm tra

1. Vì sao JWS không sử dụng nguyên ASN.1 DER cho chữ ký ECDSA?
2. Định dạng raw R||S khác DER ở cấu trúc, độ dài và cách biểu diễn INTEGER như thế nào?
3. ES256, ES384 và ES512 cần raw signature dài bao nhiêu byte?
4. Vì sao DER INTEGER dương đôi khi có byte `0x00` ở đầu?
5. Khi chuyển DER sang raw, vì sao phải left-pad mỗi số về width cố định?
6. Khi chuyển raw sang DER, vì sao phải xử lý lại byte dấu?
7. Tại sao parser DER cần từ chối byte thừa và length encoding không hợp lệ?
8. Vì sao không nên tự động đoán API đang trả DER hay P1363 chỉ từ một mẫu chữ ký?
9. Vì sao hai lần ký ECDSA cùng thông điệp có thể tạo byte chữ ký khác nhau nhưng đều xác minh được?
10. Nếu chữ ký xác minh thành công nhưng `aud` sai, verifier có được chấp nhận JWT không?

## 12. Tiêu chuẩn và tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515), cấu trúc JWS Compact, signing input và đoạn chữ ký.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518), đặc biệt **mục 3.4** quy định ES256/ES384/ES512 và biểu diễn R||S.
- [RFC 3279 — Algorithms and Identifiers for the Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc3279), định dạng chữ ký ECDSA ASN.1 trong hệ sinh thái X.509.
- [ITU-T X.690 — ASN.1 encoding rules: BER, CER and DER](https://www.itu.int/rec/T-REC-X.690), quy tắc mã hóa ASN.1 DER.
- [RFC 6979 — Deterministic Usage of DSA and ECDSA](https://www.rfc-editor.org/rfc/rfc6979), nonce xác định và test ECDSA.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725), xác minh thuật toán, khóa và ngữ cảnh JWT.
