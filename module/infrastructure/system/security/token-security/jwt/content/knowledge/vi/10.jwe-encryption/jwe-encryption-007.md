# Ràng buộc thuật toán mã hóa được phép và khả năng liên thông

## 1. Vì sao phải có chính sách thuật toán rõ ràng?

JSON Web Encryption (JWE) hỗ trợ nhiều thuật toán quản lý khóa và mã hóa nội dung. Sự linh hoạt này giúp các hệ thống dùng nhiều loại khóa và nền tảng khác nhau, nhưng cũng tạo ra một yêu cầu quan trọng: **bên nhận phải chủ động giới hạn thuật toán được chấp nhận**.

Một JWE thường mang các tham số:

- `alg`: thuật toán quản lý khóa, dùng để chuyển giao, bảo vệ hoặc suy ra CEK.
- `enc`: thuật toán mã hóa nội dung, dùng CEK để mã hóa và xác thực payload.
- `kid`: định danh/gợi ý chọn khóa.
- Các tham số khác như `epk`, `apu`, `apv`, `zip`, `cty` hoặc `crit` tùy thuật toán và định dạng.

Các giá trị header đến từ token bên ngoài. Chúng mô tả cách người tạo token đã cấu hình JWE, nhưng **không phải chính sách tin cậy của bên nhận**. Nếu ứng dụng chấp nhận mọi giá trị `alg` hoặc `enc` mà token tự khai báo, kẻ tấn công có thể ép hệ thống xử lý một thuật toán không được phê duyệt, dùng sai loại khóa hoặc rơi về cấu hình yếu hơn.

Một chính sách an toàn cần trả lời:

1. Hệ thống cho phép những thuật toán quản lý khóa nào?
2. Hệ thống cho phép những thuật toán mã hóa nội dung nào?
3. Những **cặp `alg` + `enc`** nào được phép dùng cùng nhau?
4. Loại khóa, kích thước khóa và mục đích sử dụng nào tương thích với từng thuật toán?
5. Hai hệ thống đã thống nhất serialization, header, định dạng khóa và quy tắc kiểm tra token chưa?

Bài học này thuộc phần **Mã hóa JWE** của học phần **Security - JSON Web Token (JWT)** (`SECURITY_TOKEN_SECURITY_JWT`). Các nguyên tắc áp dụng cho JWT/JOSE nói chung, không phụ thuộc Java, Spring Security hay framework cụ thể.

## 2. Allowlist phải do ứng dụng cấu hình

### 2.1. Không lấy header của token làm nguồn cấp quyền

Ví dụ một token có protected header:

```json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "recipient-key-2026"
}
```

Bên nhận chỉ được xử lý token nếu chính sách của ứng dụng cho phép:

- `RSA-OAEP-256` trong ngữ cảnh recipient và loại khóa đang dùng.
- `A256GCM` cho nội dung.
- Cặp `RSA-OAEP-256 + A256GCM` theo profile tích hợp.
- Khóa tương ứng với `kid` thuộc kho khóa tin cậy, có đúng mục đích và trạng thái.

Không được làm theo kiểu “đọc `alg` từ token rồi tự động bật thuật toán đó”. Header chỉ là đầu vào để kiểm tra với policy đã cấu hình.

### 2.2. Allowlist nên ràng buộc theo cặp thuật toán

Chỉ cấu hình hai danh sách riêng đôi khi chưa đủ. Giả sử hệ thống cho phép các giá trị:

- `alg`: `RSA-OAEP-256` và `ECDH-ES+A256KW`.
- `enc`: `A128GCM` và `A256GCM`.

Nếu chỉ kiểm tra từng trường độc lập, hệ thống có thể vô tình chấp nhận cả bốn tổ hợp, dù hợp đồng tích hợp chỉ kiểm thử hai tổ hợp. Tốt hơn là định nghĩa rõ **profile cặp thuật toán**:

| Profile | `alg` | `enc` | Mục đích |
| --- | --- | --- | --- |
| Profile A | `RSA-OAEP-256` | `A256GCM` | Mã hóa CEK cho recipient có RSA public key |
| Profile B | `ECDH-ES+A256KW` | `A256GCM` | Thỏa thuận KEK bằng ECDH rồi wrap CEK |
| Profile C | `A256KW` | `A128GCM` | Wrap CEK bằng KEK AES 256 bit, nội dung dùng AES-GCM 128 bit |
| Profile D | `dir` | `A256GCM` | Khóa chia sẻ trực tiếp làm CEK trong một phạm vi tin cậy hẹp |

Đây là ví dụ profile, không phải danh sách bắt buộc cho mọi hệ thống. Chỉ đưa vào những tổ hợp mà các bên thực sự hỗ trợ, đã kiểm thử và được chính sách mật mã cho phép.

### 2.3. Kiểm tra trước khi giải mã

Quy trình kiểm tra phía nhận nên theo thứ tự có kiểm soát:

1. Kiểm tra cấu trúc và serialization của JWE.
2. Phân tích protected header và recipient header theo quy tắc JWE.
3. Xác định profile dựa trên ngữ cảnh tích hợp và recipient đã biết.
4. Kiểm tra `alg` và `enc` có nằm trong profile được phép không.
5. Kiểm tra loại khóa, kích thước khóa, curve, mục đích sử dụng và trạng thái khóa.
6. Chọn khóa từ kho tin cậy; không tải khóa tùy ý theo chỉ dẫn không tin cậy trong token.
7. Thực hiện quản lý khóa, xác thực tag và giải mã bằng thư viện JOSE.
8. Kiểm tra nội dung JWT, issuer, audience, thời hạn và quyền; xác minh chữ ký JWS nếu yêu cầu xác thực nguồn phát hành.

Nếu bất kỳ bước nào không đạt, phải từ chối token. Không tự động thử thuật toán yếu hơn hoặc chuyển sang một loại khóa khác để “cố giải mã”.

## 3. Chọn thuật toán và khóa tương thích

`alg` và `enc` có vai trò khác nhau, nên yêu cầu khóa cũng khác nhau.

### 3.1. Một số thuật toán quản lý khóa và yêu cầu khóa

| `alg` | Loại vật liệu khóa | Điều kiện cần kiểm tra |
| --- | --- | --- |
| `RSA-OAEP-256` | Cặp khóa RSA của recipient | Public key dùng bảo vệ CEK; private key tương ứng dùng giải mã; độ dài RSA đáp ứng chính sách (thông thường tối thiểu 2048 bit) |
| `A128KW` / `A192KW` / `A256KW` | KEK đối xứng | KEK lần lượt có độ dài 128/192/256 bit |
| `A128GCMKW` / `A192GCMKW` / `A256GCMKW` | KEK đối xứng dùng AES-GCM để wrap CEK | Độ dài khóa, IV và tag của bước wrap phải đúng JWA |
| `ECDH-ES` | Khóa ECDH của recipient và khóa tạm thời của bên gửi | Curve và KDF được hai bên hỗ trợ; tạo CEK đúng yêu cầu của `enc` |
| `ECDH-ES+A256KW` | Khóa ECDH để suy ra KEK, rồi AES Key Wrap | Curve, KDF, KEK và CEK phải đúng profile |
| `dir` | Khóa đối xứng dùng trực tiếp làm CEK | Độ dài khóa phải đúng với `enc`; các bên giữ khóa phải được kiểm soát chặt |

Với RSA, không chỉ kiểm tra `kty = RSA`. Cần xác minh khóa có kích thước phù hợp, nguồn gốc tin cậy, trạng thái còn hiệu lực và mục đích dùng đúng. Với ECDH, cần thống nhất curve, loại khóa EC/OKP được thuật toán hỗ trợ và các tham số KDF.

### 3.2. Một số thuật toán mã hóa nội dung

| `enc` | CEK | IV | Tag |
| --- | ---: | ---: | ---: |
| `A128GCM` | 128 bit | 96 bit | 128 bit |
| `A192GCM` | 192 bit | 96 bit | 128 bit |
| `A256GCM` | 256 bit | 96 bit | 128 bit |
| `A128CBC-HS256` | 256 bit tổng cộng | 128 bit | 128 bit |
| `A192CBC-HS384` | 384 bit tổng cộng | 128 bit | 192 bit |
| `A256CBC-HS512` | 512 bit tổng cộng | 128 bit | 256 bit |

Với AES-GCM, CEK có độ dài đúng bằng kích thước khóa AES. Với AES-CBC-HMAC, CEK được chia thành phần khóa MAC và phần khóa mã hóa theo JWA. Không thể dùng một khóa chỉ vì tổng số byte trùng nhau.

### 3.3. JWK cần khớp với thuật toán và mục đích

Nếu khóa được biểu diễn bằng JSON Web Key (JWK), cần xem xét các trường:

- `kty`: loại khóa, ví dụ `RSA`, `EC` hoặc `oct`.
- `crv`: curve đối với khóa EC/OKP.
- `use`: mục đích tổng quát, thường `enc` cho khóa mã hóa.
- `key_ops`: các thao tác được phép, ví dụ `encrypt`, `decrypt`, `wrapKey`, `unwrapKey` hoặc `deriveKey` theo cách dùng.
- `alg`: thuật toán dự kiến của khóa nếu trường này được khai báo.
- `kid`: định danh khóa trong kho khóa.

Không phải JWK nào cũng phải chứa tất cả các trường trên, nhưng nếu có thì các giá trị phải nhất quán với profile. Ví dụ, một khóa chỉ dành cho chữ ký không được lấy làm khóa giải mã JWE. Không được bỏ qua xung đột giữa `use`, `key_ops`, `alg` và thuật toán thực tế chỉ vì phép toán mật mã có thể chạy.

Tách khóa ký JWS và khóa giải mã/quản lý CEK JWE theo mục đích giúp giảm rủi ro dùng nhầm khóa giữa các giao thức.

## 4. Tránh thuật toán yếu và hạ cấp cấu hình

### 4.1. Không chấp nhận thuật toán ngoài chính sách

Các thuật toán cũ có thể còn xuất hiện vì tương thích với hệ thống lâu năm. Một số điểm cần chú ý:

- `RSA1_5` là phương thức mã hóa khóa cũ, có lịch sử rủi ro oracle; không nên bật cho thiết kế mới.
- `RSA-OAEP` dùng cấu hình OAEP khác với `RSA-OAEP-256`. Hai tên không thể xem là tương đương: biến thể `RSA-OAEP` trong JWA dùng SHA-1, còn `RSA-OAEP-256` dùng SHA-256.
- AES-CBC-HMAC vẫn là tổ hợp JWA chuẩn, nhưng cần triển khai đúng quy trình MAC và tránh padding oracle. Với hệ thống mới, AES-GCM thường đơn giản hơn khi quản lý nonce đúng cách.
- `dir` không phải “không mã hóa”; nó dùng khóa chia sẻ trực tiếp làm CEK. Rủi ro chính là phạm vi các bên cùng giữ khóa và quản lý nonce nếu khóa được dùng lâu dài.

Không đưa thuật toán vào allowlist chỉ vì một thư viện hỗ trợ nó. Cần xem xét tiêu chuẩn hiện hành, chính sách tổ chức, năng lực quản lý khóa và nhu cầu tương thích.

### 4.2. Không fallback khi giải mã thất bại

Ví dụ một hệ thống dự kiến chỉ nhận `RSA-OAEP-256 + A256GCM`. Nếu token dùng `RSA-OAEP` hoặc `A128CBC-HS256`, hệ thống phải từ chối theo policy.

Không nên thực hiện chuỗi fallback như:

```text
Thử RSA-OAEP-256 + A256GCM
Nếu lỗi -> thử RSA-OAEP + A256GCM
Nếu lỗi -> thử RSA1_5 + A128CBC-HS256
```

Cách fallback này làm mờ ranh giới bảo mật, tăng bề mặt tấn công và có thể tạo oracle khác nhau. Nếu cần chuyển đổi thuật toán, phải thực hiện qua rollout có kế hoạch và profile được định danh rõ ràng.

### 4.3. Thuật toán trong token không được ghi đè policy

Một số nguyên tắc:

- Không chấp nhận giá trị `alg` hoặc `enc` chỉ vì nó xuất hiện trong protected header.
- Không cho `kid` quyết định thuật toán ngoài profile đã gắn với key.
- Không dùng JWK hoặc URL do token cung cấp như nguồn khóa đáng tin mà chưa xác thực.
- Không bỏ qua tham số bắt buộc trong `crit`. Nếu gặp critical parameter không được hỗ trợ, phải từ chối.
- Không xử lý một token như JWS chỉ vì JWE giải mã thất bại, hoặc ngược lại. Loại token phải được xác định theo endpoint và profile đã cấu hình.

## 5. Khả năng liên thông giữa các thư viện và hệ thống

Hai hệ thống đều nói “hỗ trợ JWE” chưa chắc đã trao đổi được token cho nhau. Khả năng liên thông đòi hỏi thống nhất **toàn bộ profile**, không chỉ một tên thuật toán.

### 5.1. Những điểm phải thống nhất

| Hạng mục | Điều cần thống nhất | Lỗi thường gặp |
| --- | --- | --- |
| Serialization | Compact, Flattened JSON hay General JSON | Một bên chỉ hỗ trợ Compact, bên kia gửi General JSON |
| `alg` | Tên thuật toán chính xác và cách quản lý CEK | Nhầm `RSA-OAEP` với `RSA-OAEP-256` |
| `enc` | Thuật toán nội dung và kích thước CEK/IV/tag | Một bên gửi A256GCM, bên kia chỉ bật A128GCM |
| Key type | RSA, EC, oct và curve cụ thể | Gửi EC key trong khi profile yêu cầu RSA |
| Key size | Độ dài RSA, AES hoặc CEK | Khóa sai kích thước hoặc không đáp ứng policy |
| Key identification | `kid`, key version và nguồn khóa | Hai bên hiểu `kid` theo namespace khác nhau |
| Header | Vị trí protected, unprotected và recipient header | Đặt `alg` hoặc tham số khác sai vùng |
| ECDH parameters | `epk`, `apu`, `apv` và KDF | Khác biệt encoding hoặc cách dựng AlgorithmID |
| AAD | Protected header và AAD bổ sung | Hai bên tạo chuỗi AAD khác nhau |
| Base64url | Encoding không padding và xử lý byte | Dùng Base64 chuẩn có dấu `+`, `/` hoặc padding |
| Plaintext | UTF-8, JSON, nested JWT và content type | Một bên mong JWT lồng nhau, bên kia gửi JSON thuần |
| Critical parameters | Quy tắc `crit` và extension | Bên nhận bỏ qua extension bắt buộc |
| Error behavior | Từ chối token, không fallback | Khác biệt khiến hệ thống vô tình chấp nhận cấu hình ngoài policy |

### 5.2. Khác biệt tên thuật toán có ý nghĩa mật mã

Ví dụ:

- `RSA-OAEP` và `RSA-OAEP-256` dùng cấu hình hash khác nhau trong OAEP.
- `A256GCM` yêu cầu CEK 256 bit, IV 96 bit và tag 128 bit theo JWA.
- `A128GCM` yêu cầu CEK 128 bit; không thể gửi CEK 256 bit và mong bên nhận tự cắt ngắn.
- `ECDH-ES` trực tiếp suy ra CEK, còn `ECDH-ES+A256KW` suy ra KEK để wrap CEK. Hai bên phải thống nhất đúng biến thể và tham số KDF.
- Với AES-CBC-HMAC, thứ tự chia CEK, MAC input, độ dài tag và padding phải đúng chuẩn.

Không nên chỉ so sánh tên thuật toán bằng chuỗi ở một nơi rồi bỏ qua các tham số khóa hoặc serialization liên quan.

### 5.3. Base64url và cấu trúc JSON

JOSE dùng Base64url theo quy tắc của RFC 7515/7516, thường không có ký tự padding `=`. Base64url khác Base64 thông thường ở bảng ký tự và cách xử lý padding.

Một số lỗi liên thông:

- Giữ lại dấu padding ở nơi không phù hợp.
- Dùng Base64 chuẩn có `+` hoặc `/`.
- Chuyển chuỗi JSON sang encoding khác UTF-8.
- Thay đổi thứ tự hoặc cách tuần tự hóa protected header sau khi đã tạo tag.
- Tự parse rồi serialize lại header trước khi xác thực, khiến AAD không còn giống phần protected header gốc.

Bên nhận phải xác thực trên đúng dữ liệu được mã hóa Base64url theo cấu trúc JWE; không tự dựng lại AAD từ một JSON object đã parse rồi serialize lại.

## 6. JWE Compact và JSON Serialization trong hợp đồng tích hợp

### 6.1. Compact Serialization

Compact Serialization gồm đúng năm phần, ngăn cách bằng dấu chấm:

```text
protected.encrypted_key.iv.ciphertext.tag
```

Đặc điểm:

- Gọn, phù hợp cho một recipient.
- Protected header là vùng header duy nhất.
- Encrypted key có thể rỗng với thuật toán quản lý khóa trực tiếp như `dir` hoặc `ECDH-ES`.
- Không biểu diễn nhiều recipient trong cùng một token.

### 6.2. Flattened JSON và General JSON

Flattened JSON biểu diễn một recipient bằng JSON object. General JSON dùng mảng `recipients` để biểu diễn nhiều recipient.

Trong General JSON:

- `enc` áp dụng cho nội dung mã hóa chung.
- Mỗi recipient có thông tin quản lý khóa riêng; `alg` có thể khác nhau theo recipient.
- Ciphertext, IV và tag được dùng chung.
- Những trường header nằm ở protected, shared unprotected hoặc recipient header phải theo đúng quy tắc của RFC 7516.

Nếu một bên chỉ hỗ trợ Compact, bên còn lại không được mặc định gửi General JSON chỉ vì thư viện có hỗ trợ. Serialization phải được thống nhất trong hợp đồng tích hợp.

## 7. Xây dựng một interoperability profile

Một profile là tập hợp các quy tắc cụ thể mà hai hoặc nhiều hệ thống cam kết tuân thủ. Ví dụ:

```yaml
profile: partner-jwe-v1
serialization: compact
key_management_algorithm: RSA-OAEP-256
content_encryption_algorithm: A256GCM
recipient_key:
  type: RSA
  minimum_modulus_bits: 2048
  use: enc
plaintext:
  encoding: UTF-8
  format: nested-jwt
headers:
  protected:
    - alg
    - enc
    - kid
    - cty
  critical_parameters: []
key_source:
  configured_trust_store: partner-recipient-keys
validation:
  verify_jwe_authentication_tag: true
  verify_inner_jws_if_nested: true
  check_issuer_audience_expiry: true
failure:
  reject_unlisted_algorithm: true
  reject_unknown_critical_parameter: true
  no_algorithm_fallback: true
```

Đây là ví dụ profile nội bộ để minh họa; không phải schema cấu hình chuẩn của RFC. Hai bên cần thống nhất ý nghĩa và cách triển khai từng trường.

### 7.1. Profile phải nêu rõ

1. Serialization nào được gửi/nhận.
2. Cặp `alg` + `enc` được phép.
3. Loại khóa, kích thước, curve và mục đích.
4. Nguồn khóa, cách xác minh và cách ánh xạ `kid`.
5. Các protected header bắt buộc, header tùy chọn và critical parameters.
6. Encoding plaintext, JSON hoặc nested JWT.
7. Quy tắc kiểm tra tag, chữ ký lồng nhau và claim.
8. Kích thước token tối đa, timeout và giới hạn xử lý.
9. Cách thay khóa, overlap khi rotation và thời hạn chấp nhận key version cũ.
10. Mã lỗi và hành vi từ chối token không hợp lệ.

## 8. Rollout và thay đổi thuật toán an toàn

Thuật toán có thể cần thay đổi theo chính sách, năng lực thư viện hoặc vòng đời khóa. Không nên chuyển đồng loạt mà thiếu giai đoạn tương thích.

Một kế hoạch rollout thường gồm:

1. **Kiểm kê:** xác định các issuer, recipient, thư viện, key type, serialization và cặp thuật toán đang sử dụng.
2. **Chọn profile đích:** chọn thuật toán được phê duyệt và được tất cả bên liên quan hỗ trợ.
3. **Bổ sung hỗ trợ nhận:** triển khai profile mới ở bên nhận, nhưng chỉ bật cho đúng đối tác và khóa đã xác thực.
4. **Kiểm thử liên thông:** chạy test vectors và kiểm thử hai chiều giữa các thư viện thực tế.
5. **Chuyển bên phát hành:** bắt đầu tạo JWE mới theo profile mới.
6. **Theo dõi:** đo tỷ lệ thành công, lỗi thuật toán, lỗi key selection, lỗi tag và tỷ lệ token còn dùng profile cũ.
7. **Ngừng profile cũ:** sau thời gian chuyển tiếp, loại thuật toán cũ khỏi allowlist và ngừng khóa tương ứng theo kế hoạch.

Trong giai đoạn chuyển tiếp, có thể cho phép hai profile đã được duyệt. Tuy nhiên, lựa chọn profile phải dựa trên cấu hình đối tác/issuer và trạng thái rollout, không phải “thử lần lượt mọi thuật toán cho đến khi một cái chạy được”.

### Ví dụ chuyển đổi

| Giai đoạn | Bên phát hành | Bên nhận |
| --- | --- | --- |
| Ban đầu | Gửi Profile A | Chỉ nhận Profile A |
| Chuẩn bị | Vẫn gửi A | Nhận A và B đã được phê duyệt |
| Chuyển đổi | Bắt đầu gửi B cho đối tác đã sẵn sàng | Nhận B theo cấu hình đối tác; tiếp tục A trong thời hạn |
| Kết thúc | Chỉ gửi B | Loại A khỏi allowlist và ngừng key version cũ |

Không kéo dài giai đoạn chấp nhận profile cũ vô thời hạn. Mỗi profile cũ phải có thời điểm ngừng cụ thể và người chịu trách nhiệm.

## 9. Kiểm thử khả năng liên thông

Kiểm thử không nên chỉ xác nhận “token giải mã được trên cùng thư viện đã tạo ra nó”. Cần có test độc lập giữa các bên.

### 9.1. Test dương tính

- Token được phát hành bởi thư viện A và giải mã bởi thư viện B.
- Token dùng từng cặp `alg` + `enc` trong profile.
- Kiểm tra JWE Compact, Flattened JSON hoặc General JSON theo hợp đồng.
- Kiểm tra JWK RSA/EC/oct và key version hợp lệ.
- Kiểm tra ECDH với curve và tham số KDF đã thống nhất.
- Kiểm tra nested JWT nếu profile sử dụng.

### 9.2. Test âm tính

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| `alg` không nằm trong allowlist | Từ chối trước khi thực hiện thuật toán |
| `enc` không nằm trong allowlist | Từ chối |
| Cặp `alg` + `enc` không được profile cho phép | Từ chối |
| Key type hoặc key size không phù hợp | Từ chối |
| `kid` không ánh xạ được vào khóa tin cậy | Từ chối |
| Authentication tag bị sửa | Từ chối |
| Unknown critical parameter trong `crit` | Từ chối |
| Serialization không được profile hỗ trợ | Từ chối |
| Khóa hết hạn hoặc bị thu hồi | Từ chối theo chính sách |
| JWE giải mã được nhưng JWS lồng nhau có chữ ký sai | Từ chối |
| Token dùng profile cũ sau thời điểm ngừng | Từ chối |

### 9.3. Dùng test vectors và kiểm thử đa thư viện

Nên dùng test vectors từ RFC và bộ kiểm thử của thư viện JOSE. Bên gửi và nhận cần trao đổi các mẫu đã biết kết quả để kiểm tra:

- Header chính xác và AAD chính xác.
- Base64url và byte encoding.
- CEK, encrypted key, IV, ciphertext và tag.
- Các trường hợp ECDH, key wrapping và nhiều recipient.
- Hành vi lỗi khi tag sai, key sai hoặc thuật toán không được phép.

Không đưa khóa production hoặc plaintext nhạy cảm vào test vectors công khai. Dùng khóa thử nghiệm và dữ liệu giả lập.

## 10. Ví dụ kiểm tra profile ở mức khái niệm

Đoạn mã giả sau minh họa việc kiểm tra policy trước khi giải mã. Tên hàm không phải API của một thư viện cụ thể.

```text
policy = {
    "partner-A": {
        "serialization": ["compact"],
        "allowedPairs": [
            ["RSA-OAEP-256", "A256GCM"]
        ],
        "trustedKeyIds": ["partner-A-recipient-v4"]
    }
}

function decryptForPartner(token, partnerId) {
    partnerPolicy = policy[partnerId]
    if partnerPolicy is missing:
        reject()

    jwe = parseJWE(token)

    if jwe.serialization not in partnerPolicy.serialization:
        reject()

    alg = jwe.protectedHeader.alg
    enc = jwe.protectedHeader.enc
    kid = jwe.protectedHeader.kid

    if [alg, enc] not in partnerPolicy.allowedPairs:
        reject()

    if kid not in partnerPolicy.trustedKeyIds:
        reject()

    key = trustedKeyStore.get(partnerId, kid)
    validateKeyTypeSizeUseAndStatus(key, alg)

    plaintext = JOSE.decryptAndAuthenticate(
        jwe,
        key,
        allowedAlgs = [alg],
        allowedEncs = [enc]
    )

    return validatePlaintextAndClaims(plaintext)
}
```

Trong triển khai thật, cần xử lý riêng trường hợp `alg` nằm trong recipient header của JSON Serialization, xác thực protected header, áp dụng profile cho đúng recipient và dùng thư viện JOSE. Không tự parse Compact và General JSON theo một giả định header giống nhau.

## 11. Checklist allowlist và liên thông

- [ ] Allowlist được cấu hình trong ứng dụng hoặc profile tin cậy, không lấy từ token.
- [ ] Chính sách ràng buộc cặp `alg` + `enc` thay vì chỉ kiểm tra từng danh sách riêng.
- [ ] Loại khóa, kích thước, curve, `use`, `key_ops` và mục đích sử dụng được kiểm tra.
- [ ] `kid` chỉ được dùng để chọn khóa trong kho tin cậy đã cấu hình.
- [ ] Không bật thuật toán yếu hoặc thuật toán cũ chỉ để tương thích nếu chưa có phê duyệt.
- [ ] Không fallback sang thuật toán khác khi giải mã thất bại.
- [ ] Serialization và vị trí header được thống nhất giữa các bên.
- [ ] Base64url, UTF-8, AAD, IV, tag và ECDH parameters được kiểm thử liên thông.
- [ ] Critical parameters không được hỗ trợ dẫn đến từ chối token.
- [ ] Có profile version, thời hạn chuyển tiếp và lịch ngừng profile cũ.
- [ ] Có test vectors và kiểm thử chéo giữa các thư viện độc lập.
- [ ] Có test âm tính cho thuật toán không cho phép, khóa sai, tag sai và profile hết hạn.
- [ ] Sau giải mã, vẫn kiểm tra claim và chữ ký JWS nếu token cần xác thực nguồn.

**Kết luận:** Khả năng liên thông JWE không chỉ là việc hai thư viện cùng hỗ trợ một thuật toán. Các bên phải thống nhất profile gồm cặp `alg` + `enc`, loại và mục đích khóa, serialization, header, encoding, nguồn khóa và quy tắc xác thực. Bên nhận luôn áp dụng allowlist do ứng dụng kiểm soát, từ chối cấu hình ngoài policy và không fallback sang thuật toán yếu hơn. Một profile rõ ràng cùng test vectors và rollout có kiểm soát giúp hệ thống trao đổi JWE an toàn, ổn định.

### Tài liệu tiêu chuẩn

- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
