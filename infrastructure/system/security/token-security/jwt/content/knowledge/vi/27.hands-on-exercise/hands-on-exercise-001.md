# Quan sát một JWT mẫu và phân biệt nội dung đọc được với nội dung đã xác minh

## Mục tiêu thực hành

Sau bài thực hành này, bạn có thể:

- Nhận diện cấu trúc compact serialization của một JSON Web Token (JWT) dạng JWS.
- Giải mã Base64URL để đọc header và payload, đồng thời giải thích vì sao thao tác này không chứng minh token hợp lệ.
- Xác minh chữ ký trên đúng chuỗi byte đã được ký và hiểu vai trò của khóa xác minh.
- Phân biệt ba kết quả: đọc được nội dung, chữ ký hợp lệ và token được phép sử dụng trong một ngữ cảnh cụ thể.
- Nhận ra các lỗi phổ biến như tin claim trước khi xác minh, tin thuật toán do token tự khai báo hoặc coi chữ ký hợp lệ là đủ để cấp quyền.

Bài học thuộc module **Security - JSON Web Token (JWT)**, chương **Thực hành tổng hợp**. Các thao tác và nguyên tắc áp dụng ở mức giao thức, không phụ thuộc Java, Spring hay một framework cụ thể.

## 1. Chuẩn bị: JWT đang quan sát là loại nào?

JWT là một định dạng biểu diễn các claim. JWT có thể được bảo vệ bằng JWS (ký hoặc xác thực tính toàn vẹn) hoặc JWE (mã hóa). Bài này dùng một JWT dạng **JWS compact**, có ba phần được ngăn cách bởi dấu chấm:

```text
BASE64URL(protected-header).
BASE64URL(payload).
BASE64URL(signature)
```

Trong một JWS compact:

1. Phần đầu là protected header, mô tả thông tin như thuật toán và kiểu nội dung.
2. Phần giữa là payload, chứa các claim.
3. Phần cuối là chữ ký hoặc giá trị xác thực được tính theo thuật toán đã chọn.

Header và payload được mã hóa Base64URL để vận chuyển thuận tiện. Base64URL chỉ là cách biểu diễn dữ liệu, không phải mã hóa bí mật. Người có token thường có thể giải mã hai phần đầu mà không cần khóa.

Chữ ký JWS được tính trên chuỗi ký có dạng chính xác:

```text
ASCII(BASE64URL(protected-header) + "." + BASE64URL(payload))
```

Vì vậy, việc thay đổi một byte trong header hoặc payload thường làm chữ ký không còn khớp. Phần chữ ký không phải nội dung JSON có thể đọc trực tiếp; muốn kiểm tra nó cần thực hiện phép xác minh phù hợp với thuật toán và khóa.

> **Phạm vi:** JWT dạng JWE compact thường có năm phần, trong đó phần nội dung được mã hóa và không thể đọc như payload JWS nếu không giải mã bằng khóa phù hợp. Không áp dụng kết luận “payload JWT luôn đọc được” cho mọi JWT; kết luận ở đây dành cho JWS đang thực hành.

## 2. Dữ liệu thực hành

Sử dụng token mẫu sau. Đây là ví dụ kiểm thử công khai theo định dạng JWS, không phải thông tin đăng nhập đang hoạt động:

```text
eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJqb2UiLCJleHAiOjEzMDA4MTkzODAsImh0dHA6Ly9leGFtcGxlLmNvbS9pc19yb290Ijp0cnVlfQ.dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
```

Thông tin khóa dùng để xác minh chữ ký HMAC trong fixture này là 32 byte, mỗi byte có giá trị hex `0b`:

```text
0b 0b 0b 0b 0b 0b 0b 0b
0b 0b 0b 0b 0b 0b 0b 0b
0b 0b 0b 0b 0b 0b 0b 0b
0b 0b 0b 0b 0b 0b 0b 0b
```

Header khai báo `HS256`, tức HMAC với SHA-256. Trong bài thực hành, thuật toán mong đợi được cấu hình trước là `HS256`; không lấy giá trị `alg` từ token làm quyết định duy nhất cho verifier.

**Cảnh báo sử dụng khóa:** khóa trên chỉ dành cho ví dụ công khai. Vì khóa và token đều đã được công bố, tuyệt đối không dùng chúng trong production, không dùng khóa mẫu để ký token thật và không suy ra quy tắc chọn khóa production từ fixture này.

## 3. Bước 1 — Tách ba phần và giải mã header/payload

Tách token tại dấu chấm (`.`). Với JWS compact hợp lệ, cần có đúng ba phần. Sau khi tách:

| Phần | Giá trị được giải mã | Ý nghĩa ban đầu |
|---|---|---|
| Header | `{"typ":"JWT","alg":"HS256"}` | Token tự khai báo kiểu và thuật toán |
| Payload | `{"iss":"joe","exp":1300819380,"http://example.com/is_root":true}` | Các claim được người tạo token đưa vào |
| Signature | Dãy byte nhị phân | Giá trị cần xác minh bằng thuật toán và khóa phù hợp |

Hai chuỗi đầu dùng Base64URL. Quy trình giải mã cơ bản là:

1. Chuyển ký tự `-` thành `+` và `_` thành `/` để ánh xạ về bảng Base64 tương ứng.
2. Bổ sung ký tự đệm `=` nếu cần để độ dài chia hết cho 4.
3. Giải mã Base64 và diễn giải byte kết quả theo UTF-8 đối với JSON.

Ví dụ, header đã giải mã cho biết `alg` là `HS256`. Thông tin này chỉ là dữ liệu do bên tạo token cung cấp. Bản thân header chưa chứng minh rằng token được ký bằng HS256, rằng chữ ký khớp hoặc rằng người gửi có quyền phát hành token.

Payload cũng chỉ là dữ liệu có thể đọc. Claim `iss` có giá trị `joe` không tự chứng minh issuer là `joe`; claim tùy chỉnh `http://example.com/is_root` có giá trị `true` không tự cấp quyền quản trị. Trước khi xác minh và áp dụng chính sách, mọi claim trong token đều phải được xem là đầu vào chưa đáng tin cậy.

### Quan sát quan trọng

- Đọc được `{"alg":"HS256"}` không đồng nghĩa chữ ký đã được kiểm tra.
- Đọc được `{"iss":"joe"}` không đồng nghĩa issuer đã được tin cậy.
- Đọc được `{"exp":...}` không đồng nghĩa token còn hạn.
- Đọc được một claim vai trò hoặc quyền không đồng nghĩa ứng dụng phải cấp quyền đó.

## 4. Bước 2 — Hiểu chính xác dữ liệu được xác minh

Với JWS dùng HMAC SHA-256, verifier tính lại MAC từ chuỗi ký và khóa bí mật đã biết, sau đó so sánh kết quả với chữ ký trong token. Về mặt khái niệm:

```text
signing_input = encoded_header + "." + encoded_payload
expected_mac  = HMAC-SHA-256(secret_key, ASCII(signing_input))
valid         = constant_time_equal(expected_mac, decoded_signature)
```

Điểm cần chú ý:

1. Đầu vào là hai phần Base64URL nguyên gốc, nối bằng một dấu chấm ASCII. Không giải mã JSON rồi serialize lại trước khi tính MAC.
2. Thứ tự thuộc tính JSON, khoảng trắng, cách escape và từng byte của chuỗi đã mã hóa đều có thể ảnh hưởng đến chữ ký.
3. Chữ ký trong token phải được giải mã Base64URL thành byte trước khi so sánh.
4. So sánh giá trị xác thực nên dùng phép so sánh constant-time do thư viện mật mã cung cấp để hạn chế rò rỉ thông tin qua thời gian thực thi.
5. Thuật toán và loại khóa được phép phải đến từ cấu hình tin cậy của ứng dụng. Không để token tự chọn một thuật toán ngoài chính sách.

Với HS256, cả bên ký và bên xác minh đều nắm cùng một khóa bí mật. Vì vậy, bất kỳ bên nào có khóa đều có khả năng tạo MAC hợp lệ. Khi cần xác minh bằng khóa công khai mà không trao quyền ký cho verifier, hệ thống thường dùng thuật toán chữ ký bất đối xứng phù hợp, chẳng hạn một thuật toán thuộc họ RSA, ECDSA hoặc EdDSA được hỗ trợ và cấu hình an toàn.

Chữ ký hợp lệ chỉ cho biết dữ liệu được bảo vệ khớp với khóa xác minh theo thuật toán đã chọn. Ý nghĩa “ai đã ký” còn phụ thuộc vào việc khóa đó được phân phối, gắn với danh tính issuer và quản lý đáng tin cậy như thế nào.

## 5. Bước 3 — Chạy phép kiểm tra minh họa

Đoạn Python sau dùng thư viện chuẩn để minh họa cách đọc fixture và xác minh HMAC. Python chỉ là công cụ thực hành; cùng một quy trình có thể triển khai bằng bất kỳ ngôn ngữ nào có thư viện JWT/mật mã phù hợp.

```python
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

TOKEN = (
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9."
    "eyJpc3MiOiJqb2UiLCJleHAiOjEzMDA4MTkzODAs"
    "Imh0dHA6Ly9leGFtcGxlLmNvbS9pc19yb290Ijp0cnVlfQ."
    "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
)

EXPECTED_ALGORITHM = "HS256"  # Chính sách tin cậy của bài thực hành
SECRET_KEY = bytes([0x0B]) * 32  # Chỉ là khóa kiểm thử công khai


def b64url_decode(segment: str) -> bytes:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    if not segment or any(char not in alphabet for char in segment):
        raise ValueError("Segment Base64URL không hợp lệ")
    padded = segment + "=" * (-len(segment) % 4)
    return base64.b64decode(padded, altchars=b"-_", validate=True)


parts = TOKEN.split(".")
if len(parts) != 3:
    raise ValueError("JWS compact phải có đúng ba phần")

header_b64, payload_b64, signature_b64 = parts
header = json.loads(b64url_decode(header_b64))
claims = json.loads(b64url_decode(payload_b64))

print("Header:", header)
print("Payload:", claims)

# Chọn thuật toán theo allowlist cấu hình, không theo giá trị tùy ý từ token.
if header.get("alg") != EXPECTED_ALGORITHM:
    raise ValueError("Thuật toán không nằm trong chính sách cho phép")

signing_input = (header_b64 + "." + payload_b64).encode("ascii")
expected_mac = hmac.new(SECRET_KEY, signing_input, hashlib.sha256).digest()
received_mac = b64url_decode(signature_b64)
signature_valid = hmac.compare_digest(expected_mac, received_mac)
print("Signature valid:", signature_valid)

if not signature_valid:
    raise ValueError("Chữ ký không hợp lệ")

now = int(datetime.now(timezone.utc).timestamp())
expired = "exp" not in claims or now >= claims["exp"]
print("Expired or missing exp:", expired)
```

Kết quả mong đợi khi chạy với fixture nguyên vẹn:

```text
Header: {'typ': 'JWT', 'alg': 'HS256'}
Payload: {'iss': 'joe', 'exp': 1300819380, 'http://example.com/is_root': True}
Signature valid: True
Expired or missing exp: True
```

`exp` trong ví dụ là một thời điểm thuộc năm 2011, nên token mẫu đã hết hạn ở thời điểm hiện tại. Đây là chủ ý của bài tập: **chữ ký có thể hợp lệ về mật mã trong khi token vẫn phải bị từ chối vì claim thời gian**. Kết quả xác minh chữ ký không thay thế bước kiểm tra claim.

Đoạn mã trên chỉ minh họa một phép kiểm tra HMAC cho fixture. Nó không phải JWT verifier production: chưa kiểm tra đầy đủ issuer, audience, loại token, chính sách claim, giới hạn kích thước, quy tắc parser và các yêu cầu vận hành khác. Trong ứng dụng thật, sử dụng thư viện JWT được duy trì và cấu hình verifier theo chính sách rõ ràng; không tự xây dựng toàn bộ bộ xác minh từ đoạn mã mẫu.

## 6. Bước 4 — Thử thay đổi dữ liệu và quan sát kết quả

Giữ nguyên khóa kiểm thử và thực hiện từng thay đổi riêng biệt. Với mỗi trường hợp, ghi lại liệu bạn vẫn đọc được payload hay không và liệu chữ ký còn hợp lệ hay không.

| Thử nghiệm | Thay đổi | Có thể đọc header/payload? | Kết quả xác minh dự kiến |
|---|---|---|---|
| A | Dùng token gốc | Có | Chữ ký hợp lệ với khóa fixture |
| B | Đổi `iss` từ `joe` thành `mallory`, Base64URL hóa lại payload nhưng giữ chữ ký cũ | Có | Chữ ký không hợp lệ |
| C | Giữ header và payload, sửa một ký tự của signature | Có | Chữ ký không hợp lệ |
| D | Đổi `alg` thành `none` nhưng giữ các phần còn lại | Có | Bị từ chối theo allowlist trước khi xác minh |
| E | Giữ nguyên token gốc | Có | Chữ ký hợp lệ, nhưng claim `exp` đã hết hạn |

### Giải thích kết quả

- **Thử nghiệm B:** payload mới vẫn là JSON Base64URL hợp lệ nên người quan sát vẫn đọc được `iss: mallory`. Tuy nhiên, chữ ký cũ được tạo cho payload cũ. Verifier tính MAC trên chuỗi ký mới và nhận kết quả khác.
- **Thử nghiệm C:** chữ ký là dữ liệu đầu vào cho phép so sánh. Một thay đổi nhỏ thường đủ làm MAC không khớp.
- **Thử nghiệm D:** header là dữ liệu không đáng tin cậy. Nếu verifier cho phép token tự chuyển sang `none` hoặc thuật toán khác ngoài allowlist, kẻ tấn công có thể khai thác sai sót trong chính sách xác minh.
- **Thử nghiệm E:** phép xác minh chữ ký không đánh giá token còn hạn hay không. Sau khi xác minh chữ ký, ứng dụng vẫn phải kiểm tra `exp` và các điều kiện claim bắt buộc.

Khi tạo payload thay thế, hãy giữ đúng cấu trúc compact và mã hóa lại phần payload bằng Base64URL không padding. Không cần tạo chữ ký mới cho các thử nghiệm B và C; mục tiêu là quan sát verifier từ chối dữ liệu đã bị sửa.

## 7. Bước 5 — Phân biệt ba tầng kết luận

Một hệ thống xác thực cần tách biệt ít nhất ba tầng đánh giá:

```mermaid
flowchart TD
    A[Nhận token từ nguồn không tin cậy] --> B[Phân tích cấu trúc và giải mã]
    B --> C[Đọc được header và payload]
    C --> D[Kiểm tra thuật toán theo allowlist và xác minh chữ ký]
    D --> E{Chữ ký hợp lệ?}
    E -- Không --> X[Từ chối token]
    E -- Có --> F[Kiểm tra issuer, audience, thời gian và chính sách claim]
    F --> G{Mọi điều kiện đều đạt?}
    G -- Không --> X
    G -- Có --> H[Chấp nhận token trong đúng ngữ cảnh]
```

| Tầng | Câu hỏi | Kết quả có thể kết luận |
|---|---|---|
| Phân tích/giải mã | Dữ liệu có đúng định dạng và có thể đọc không? | Có thể diễn giải header/payload; chưa có bảo đảm về nguồn gốc hay tính toàn vẹn |
| Xác minh mật mã | Chữ ký/MAC có khớp với dữ liệu và khóa tin cậy không? | Dữ liệu được bảo vệ khớp với khóa theo thuật toán đã cấu hình |
| Xác thực claim và ngữ cảnh | Issuer, audience, thời gian, loại token và chính sách ứng dụng có đạt không? | Token có thể được chấp nhận cho đúng mục đích đang xét |

Ngay cả khi cả ba tầng đạt, việc cấp quyền cho một thao tác cụ thể vẫn cần chính sách authorization của ứng dụng. Xác thực token và quyết định người dùng được phép làm gì là hai quyết định liên quan nhưng khác nhau.

## 8. Các kiểm tra claim cần thực hiện sau khi chữ ký hợp lệ

Sau khi xác minh chữ ký bằng khóa tin cậy và thuật toán được cho phép, ứng dụng cần kiểm tra claim theo hợp đồng bảo mật của token:

| Claim/điều kiện | Cách đánh giá |
|---|---|
| `iss` | Phải khớp chính xác issuer được cấu hình tin cậy; không tin issuer chỉ vì token tự khai báo |
| `aud` | Phải chứa định danh của resource/server dự kiến nhận token khi chính sách yêu cầu audience |
| `exp` | Thời điểm hiện tại phải trước thời điểm hết hạn, có áp dụng clock skew nhỏ và được quy định rõ nếu cần |
| `nbf` | Không chấp nhận trước thời điểm token bắt đầu có hiệu lực, trừ sai lệch đồng hồ trong giới hạn chính sách |
| `iat` | Có thể dùng để kiểm tra token được phát hành trong khoảng thời gian hợp lý; không tự nó chứng minh token còn hiệu lực |
| `sub` | Diễn giải subject theo issuer và loại token; không giả định giá trị này là định danh toàn cục |
| Claim tùy chỉnh | Chỉ sử dụng khi issuer, audience, loại token và ý nghĩa claim đã được xác định, xác minh và cho phép |

Các claim có thể là tùy chọn theo chuẩn hoặc theo profile, nhưng ứng dụng cần xác định rõ claim nào bắt buộc cho loại token của mình. Không tự động chấp nhận token thiếu claim quan trọng chỉ vì thư viện không báo lỗi. Đồng thời, tránh dùng một token cho nhiều mục đích khác nhau nếu không có quy tắc phân biệt rõ ràng; kiểm tra `typ`, audience, issuer và các claim phân biệt theo profile khi thích hợp.

## 9. Những lỗi cần tránh khi quan sát JWT

1. **Coi Base64URL là mã hóa bí mật:** bất kỳ ai có JWS đều có thể đọc header và payload nếu không có lớp mã hóa riêng.
2. **Tin payload trước khi xác minh:** kẻ tấn công có thể tự tạo JSON với `role: admin`, `iss` giả hoặc thời hạn tùy ý.
3. **Tin `alg` do token khai báo:** thuật toán phải được giới hạn bởi cấu hình của ứng dụng và loại khóa tương ứng.
4. **Chỉ kiểm tra chữ ký:** chữ ký hợp lệ không đảm bảo token chưa hết hạn, đúng issuer, đúng audience hoặc phù hợp mục đích.
5. **Serialize lại JSON rồi xác minh:** việc thay đổi byte của header/payload làm thay đổi signing input; phải xác minh trên đúng các segment đã nhận.
6. **Dùng khóa kiểm thử trong production:** khóa công khai hoặc khóa yếu làm mất ý nghĩa của xác minh.
7. **Nhầm HMAC với chữ ký bất đối xứng:** với HMAC, bên xác minh có khóa bí mật cũng có quyền tạo MAC.
8. **Đưa token thật lên website giải mã công cộng:** token có thể chứa dữ liệu cá nhân, quyền truy cập hoặc thông tin phiên; chỉ phân tích fixture giả lập hoặc môi trường được phê duyệt.
9. **Ghi toàn bộ token vào log:** log nên tránh lưu bearer token và dữ liệu bí mật; nếu cần điều tra, dùng định danh tương quan hoặc bản ghi đã loại bỏ thông tin nhạy cảm.

## 10. Bài tập tự đánh giá

Hãy trả lời trước khi xem đáp án gợi ý:

1. Vì sao người không có khóa vẫn đọc được `iss` trong JWS mẫu?
2. Việc đọc được `alg: HS256` có chứng minh token được ký bằng HS256 không?
3. Nếu thay `iss` thành `mallory` rồi mã hóa payload lại, tại sao payload vẫn đọc được nhưng chữ ký không còn hợp lệ?
4. Nếu verifier xác minh chữ ký thành công, vì sao token mẫu vẫn phải bị từ chối?
5. Với HS256, vì sao mọi dịch vụ có khóa xác minh cũng cần được bảo vệ như một nơi có quyền ký token?
6. Nếu token có chữ ký hợp lệ nhưng `aud` không chứa resource hiện tại, resource có nên chấp nhận token không? Vì sao?
7. Nếu một token JWE có năm phần, có thể áp dụng trực tiếp thao tác giải mã payload của JWS ba phần không?

### Đáp án gợi ý

1. Vì header và payload của JWS compact chỉ được Base64URL hóa, không được mã hóa bí mật.
2. Không. `alg` là dữ liệu trong protected header; verifier phải so sánh với allowlist tin cậy và thực hiện phép xác minh thực tế.
3. Base64URL chỉ biểu diễn lại dữ liệu nên payload mới vẫn đọc được. Chữ ký cũ gắn với signing input cũ, vì vậy MAC không khớp với signing input mới.
4. Vì claim `exp` của fixture đã ở trong quá khứ. Chữ ký hợp lệ không làm token hết hạn trở lại có hiệu lực.
5. Vì HS256 dùng chung một khóa bí mật cho ký và xác minh. Bên nắm khóa có thể tự tạo MAC hợp lệ.
6. Không, nếu chính sách yêu cầu audience phải chứa resource đó. Token có thể được phát hành cho một dịch vụ khác và không được dùng chéo mục đích.
7. Không. JWE compact có cấu trúc và quy trình giải mã khác; cần xử lý năm phần theo quy tắc JWE và khóa phù hợp.

## 11. Checklist hoàn thành thực hành

- [ ] Tách được đúng ba phần của JWS compact.
- [ ] Giải mã được header và payload bằng Base64URL.
- [ ] Giải thích được vì sao đọc được claim không chứng minh claim đáng tin.
- [ ] Xác định đúng signing input là hai segment đầu nối bằng dấu chấm.
- [ ] Xác minh được HMAC bằng khóa fixture và phép so sánh an toàn.
- [ ] Làm cho chữ ký thất bại khi sửa payload hoặc signature.
- [ ] Giải thích được vì sao `alg` phải được giới hạn bằng allowlist.
- [ ] Phân biệt chữ ký hợp lệ với token còn hạn và đúng audience/issuer.
- [ ] Không sử dụng khóa hoặc token fixture trong môi trường thật.

## Kết luận

Quan sát một JWT cho thấy phần dữ liệu có thể đọc và phần dữ liệu được bảo vệ là hai vấn đề khác nhau. Với JWS compact, Base64URL giúp đọc header và payload nhưng không tạo ra tính bí mật hay tính xác thực. Chỉ sau khi verifier kiểm tra chữ ký trên đúng signing input bằng thuật toán được cho phép và khóa đáng tin cậy, ứng dụng mới có cơ sở tin vào tính toàn vẹn của dữ liệu. Sau đó vẫn phải kiểm tra issuer, audience, thời hạn, loại token và chính sách claim trước khi chấp nhận token trong một ngữ cảnh cụ thể.
