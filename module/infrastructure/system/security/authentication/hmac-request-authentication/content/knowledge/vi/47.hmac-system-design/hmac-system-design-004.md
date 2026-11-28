# Chọn thuật toán MAC cho hệ thống HMAC Request Authentication

## 1. Bài toán thiết kế và mục tiêu

Trong một hệ thống xác thực HTTP request bằng HMAC, mỗi client được cấp **shared secret**. Client tạo **canonical request** từ phương thức HTTP, URI, các header cần bảo vệ, timestamp/nonce và có thể cả nội dung body hoặc digest của body; sau đó tính mã xác thực thông điệp (*Message Authentication Code*, MAC). Server phải tái tạo đúng các byte đã ký, lấy secret tương ứng, tính lại MAC và xác minh trước khi xử lý nghiệp vụ.

Lựa chọn thuật toán MAC là một quyết định kiến trúc: nó ảnh hưởng đến mức an toàn, độ tương thích giữa Java và SDK đối tác, kích thước header, chi phí tính toán, key lifecycle và khả năng nâng cấp khi tiêu chuẩn hoặc chính sách bảo mật thay đổi. Chọn một thuật toán mạnh **không** tự sửa được lỗi canonicalization, nonce hoặc phân quyền.

Trong bài này, hệ thống giả định có API gateway, nhiều instance Java/Spring Security, các client tích hợp bằng nhiều ngôn ngữ và một kho credential quản lý key theo `keyId`.

**Mục tiêu học tập:**

- Phân biệt MAC với hash thông thường, chữ ký số và mã hóa.
- Đánh giá HMAC-SHA-256, HMAC-SHA-384, HMAC-SHA-512, HMAC-SHA-3 và các lựa chọn khác theo yêu cầu thực tế.
- Chốt định dạng thuật toán, độ dài tag, shared secret và canonical request trong một **signing profile** có version.
- Thiết kế lựa chọn thuật toán dựa trên chính sách server, ngăn hạ cấp (*downgrade*) và quản lý key rotation.
- Viết, kiểm thử và vận hành bộ xác minh HMAC trong Java mà không làm mất kiểm soát replay, proxy/gateway và authorization.

## 2. MAC bảo vệ điều gì và không bảo vệ điều gì?

**MAC** là giá trị có kích thước giới hạn được tính từ thông điệp và khóa bí mật. Khi thuật toán và khóa an toàn, người không có secret khó tạo một tag hợp lệ cho thông điệp mới. Trong HMAC, primitive bên dưới là hàm băm mật mã nhưng cách sử dụng **có khóa** và cấu trúc HMAC là phần thiết yếu.

| Cơ chế | Có secret/key? | Chức năng chính | Dùng làm xác thực HTTP request thế nào? |
| --- | --- | --- | --- |
| `SHA-256(request)` | Không | Phát hiện khác biệt dữ liệu nếu digest được tin cậy từ nguồn khác | **Không phải MAC**: ai cũng tính lại hash sau khi sửa request |
| `HMAC-SHA-256(secret, request)` | Shared secret | Kiểm tra tính toàn vẹn và khả năng sở hữu secret | Phù hợp giữa client/server đã chia sẻ khóa |
| Chữ ký số Ed25519, ECDSA, RSA-PSS | Cặp private/public key | Chữ ký có thể kiểm tra bằng public key | Phù hợp khi không muốn server giữ shared secret có thể giả mạo chữ ký của client |
| AES-GCM/AEAD | Khóa đối xứng và nonce | Mã hóa có xác thực, bảo vệ tính bí mật và toàn vẹn | Không phải bản thay thế trực tiếp cho MAC trên HTTP request có plaintext |
| `SHA-256(body)` nằm trong canonical request có HMAC | Hash body không khóa + HMAC toàn request | Ràng buộc body bytes với chữ ký request | Phù hợp nếu server **tự tính lại** digest từ body thực nhận |

HMAC không mã hóa payload. HMAC cũng không chứng minh phía ký là một con người cụ thể: nếu shared secret bị lộ, kẻ tấn công vẫn tạo được MAC hợp lệ. Do cả client lẫn server đều biết secret, HMAC không cung cấp **non-repudiation** theo nghĩa chữ ký số.

Sau xác thực còn cần kiểm tra client có quyền gọi route, đọc tenant hoặc thực hiện thao tác hay không. Chữ ký hợp lệ là đầu vào cho **authentication**; quyết định cho phép là **authorization** riêng.

## 3. Lựa chọn thuật toán: ưu tiên nào trong thực tế?

Đối với một giao thức HMAC HTTP mới cần tương thích rộng giữa Java, gateway và các SDK, **HMAC-SHA-256 với tag đầy đủ 32 byte** là lựa chọn mặc định hợp lý. Nó được hỗ trợ phổ biến, có mức an toàn thích hợp khi dùng secret ngẫu nhiên đủ mạnh và không làm tăng kích thước header nhiều.

| Ứng viên | Độ dài MAC đầy đủ | Ưu điểm | Điểm phải xem xét |
| --- | ---: | --- | --- |
| **HMAC-SHA-256** | 32 byte / 256 bit | Hỗ trợ rộng; triển khai Java/SDK thuận tiện; profile mặc định tốt | Vẫn cần canonicalization, key entropy và quản trị nonce đúng |
| **HMAC-SHA-384** | 48 byte / 384 bit | Có thể phù hợp yêu cầu thuật toán thuộc họ SHA-2 cụ thể | Tag dài hơn; cần xác minh khả năng tương thích, hiệu năng, provider |
| **HMAC-SHA-512** | 64 byte / 512 bit | Khả dụng trong nhiều thư viện; một số nền tảng 64-bit có hiệu năng tốt | Header lớn hơn; không mặc nhiên tăng an toàn hệ thống khi secret hoặc protocol vẫn yếu |
| **HMAC-SHA3-256** | 32 byte / 256 bit | Họ hàm băm SHA-3 độc lập với SHA-2 | Cần kiểm tra provider và SDK hỗ trợ; không phải alias của HMAC-SHA-256 |
| **HMAC-SHA-1** | 20 byte / 160 bit | Có thể tồn tại ở tích hợp cũ | Không chọn cho thiết kế mới; cần kế hoạch ngừng hỗ trợ nếu đang dùng |
| **HMAC-MD5** | 16 byte / 128 bit | Chỉ gặp trong một số hệ thống rất cũ | Tránh trong thiết kế mới; ưu tiên loại bỏ |

**Lưu ý về SHA-1:** Các tấn công va chạm lên SHA-1 **không đồng nghĩa** tự động có cách giả mạo HMAC-SHA-1 với cùng chi phí. Tuy vậy, HMAC-SHA-1 là lựa chọn legacy với dư địa an toàn và chấp nhận chính sách kém hơn; không có lý do tốt để đưa vào một giao thức HMAC mới khi HMAC-SHA-256 sẵn có.

HMAC-SHA-512 không “tốt hơn gấp đôi” chỉ vì output 512 bit. Mức an toàn thực tế còn bị giới hạn bởi entropy của secret, độ dài tag được gửi, số lần cho phép thử xác minh, độ an toàn của hàm băm và lỗi triển khai. Chọn thuật toán lớn hơn mà vẫn dùng secret đoán được hoặc nonce không được kiểm tra không giải quyết nguyên nhân.

### 3.1. Tiêu chí quyết định trong một hệ thống cụ thể

1. **Yêu cầu bảo mật và chính sách tổ chức:** xác định độ mạnh mục tiêu, thuật toán đã được chấp thuận trong môi trường triển khai và hạn chế tuân thủ nếu có. Nếu cần provider FIPS, phải xác minh *provider và chế độ hoạt động cụ thể*, không suy từ tên thuật toán.
2. **Khả năng tương thích:** SDK Java, Node.js, Go, Python, thiết bị nhúng, API gateway và môi trường chạy có hỗ trợ cùng một MAC hay không. Kiểm tra đúng tên thuật toán ở từng thư viện.
3. **Tính ổn định của hợp đồng ký:** hai bên phải đồng ý mọi byte của canonical request và cách mã hóa MAC. Đây thường là nguồn sự cố thực tế lớn hơn việc chọn SHA-256 hay SHA-512.
4. **Độ dài tag và kích thước header:** cân nhắc encoding Base64/hex, header limit của proxy và nhu cầu rút ngắn tag có chủ ý.
5. **Hiệu năng:** đo trên kích cỡ request, số chữ ký/giây và tài nguyên CPU thực tế; bao gồm chi phí canonicalization, body digest, tra cứu key và nonce store. Không kết luận chỉ từ một phép benchmark hash đơn lẻ.
6. **Khả năng thay đổi:** xác định ngay `profileVersion`, key metadata, cơ chế ngừng thuật toán cũ và test vector đa ngôn ngữ.

### 3.2. Các MAC khác có được dùng thay HMAC không?

**AES-CMAC**, **KMAC**, **GMAC**, chế độ keyed hash của **BLAKE3** hay **Poly1305** đều có thể xuất hiện trong các giao thức được thiết kế chuyên biệt. Chúng **không phải alias của HMAC** và có giả định, format tag, key usage và yêu cầu triển khai riêng. Chẳng hạn GMAC và Poly1305 trong nhiều cách sử dụng có yêu cầu nonce/key uniqueness rất nghiêm ngặt. Không thay đổi thuật toán bằng cách đổi `Mac.getInstance` khi định dạng key, nonce, tag và profile ký chưa được thiết kế lại.

Nếu bài toán hiện tại chỉ là xác thực request HTTP với shared secret, HMAC-SHA-256 là điểm khởi đầu dễ kiểm chứng hơn việc tự xây một MAC dựa trên phép nối `SHA256(secret || message)`. **Không tự phát minh thuật toán MAC** từ hash, AES hoặc phép XOR.

## 4. Secret, tag và mức an toàn thực tế

### 4.1. Chất lượng shared secret

Khuyến nghị thực dụng cho HMAC-SHA-256 mới là **32 byte ngẫu nhiên mật mã (256 bit)** được sinh bởi CSPRNG, tách riêng theo client và môi trường. HMAC hỗ trợ nhiều độ dài khóa; 32 byte ở đây là chính sách mặc định dễ áp dụng, không phải điều kiện máy móc do JCA bắt buộc.

Trong Java:

~~~java
import java.security.SecureRandom;

byte[] newSecret = new byte[32];
new SecureRandom().nextBytes(newSecret);
// Lưu qua KMS/secret manager an toàn; không log hay nhúng vào source code.
~~~

Không lấy tên client, mật khẩu con người, timestamp, UUID dễ đoán hoặc một chuỗi hardcode làm secret. Không dùng chung secret cho mọi khách hàng hay giữa production và test. Thiết lập `keyId` không bí mật để tra cứu credential, còn giá trị secret phải được giữ bí mật và có quy trình cấp phát, thu hồi, rotation rõ ràng.

Với HMAC, khóa dài hơn block size của hash được xử lý theo định nghĩa thuật toán; tăng độ dài string tùy tiện không tạo thêm entropy nếu nguồn sinh khóa vẫn dự đoán được. Nếu phải dẫn xuất key từ secret chủ, cần KDF được thiết kế đúng với **domain separation** theo mục đích, client và môi trường; không tự hash chuỗi để “chia khóa” một cách tùy tiện.

### 4.2. Độ dài tag và encoding

HMAC-SHA-256 cho ra **32 byte**. Một hệ thống mới nên dùng tag đầy đủ:

- Base64 chuẩn: 44 ký tự có padding đối với đầu ra 32 byte.
- Hex: 64 ký tự; tăng kích thước header so với Base64 nhưng dễ đọc.

Thống nhất Base64 chuẩn hay URL-safe, quy tắc padding, chữ hoa/thường của hex và cách từ chối chuỗi sai. Không dùng kiểu dữ liệu `String` làm dữ liệu để so MAC theo ký tự: **decode thành byte**, kiểm tra độ dài và so sánh bằng API phù hợp.

Có thể dùng **truncated MAC**, chẳng hạn 16 byte đầu của HMAC-SHA-256, nếu cả hai phía thống nhất profile và threat model cho phép. Với tag `t` bit và các giả định MAC an toàn, khả năng đoán đúng trong một lần thử xấp xỉ `2^-t`; nhiều lần thử và giới hạn rate ảnh hưởng đến rủi ro tích lũy. Một thiết kế request authentication công khai thường không cần tiết kiệm 16 byte tới mức phải rút tag.

Không bao giờ dùng “so khớp prefix theo độ dài client gửi”. Nếu profile quy định tag 32 byte, tag 1 byte hoặc 8 byte phải bị từ chối ngay. Nếu profile quy định rút gọn 16 byte, so **đúng 16 byte đã định** và bảo vệ lựa chọn profile bằng chính sách server.

### 4.3. Secret rotation và ràng buộc thuật toán

Mỗi credential nên có `keyId`, owner/client, thuật toán hoặc danh sách profile được chấp thuận, thời điểm hiệu lực, hết hạn và trạng thái `active/rotating/revoked`. Khi chuyển thuật toán, ưu tiên **phát hành key mới gắn với profile mới**, thay vì cho cùng một secret hoạt động vô thời hạn trên nhiều giao thức.

Với incident lộ secret, thu hồi key đó ngay cả khi hệ thống đang trong giai đoạn key rotation có overlap. Từ chối request từ key đã revoked, không hồi sinh credential cũ khi rollback.

## 5. Ràng buộc MAC vào canonical request và signing profile

Thuật toán MAC chỉ an toàn nếu **toàn bộ thông tin ảnh hưởng đến ý nghĩa request** được bao phủ theo hợp đồng ký. Profile cần quy định rõ:

| Trường của hợp đồng | Ví dụ minh họa | Ý nghĩa |
| --- | --- | --- |
| Profile/version | `HMAC-HTTP-V1` | Tránh dùng chữ ký của giao thức khác trong cùng hệ thống |
| Thuật toán | `HMAC-SHA256` (JCA `HmacSHA256`) | Chọn MAC duy nhất; tránh parser đoán thuật toán |
| `keyId` | `client-a-key-2026-01` | Liên kết request với key metadata và client |
| HTTP method | `POST` | Không đổi `GET` thành `POST` mà giữ MAC |
| Canonical URI/query | `/orders?currency=VND&page=2` | Giữ semantics path/query trước các biến đổi proxy |
| Timestamp | `2026-11-28T06:00:00Z` | Giới hạn cửa sổ request |
| Nonce | `d4c7ae80e15b` | Phát hiện dùng lại request trong cửa sổ |
| Signed headers | Ví dụ `content-type`, `x-hmac-timestamp` | Chống sửa các header có ý nghĩa |
| Body digest | SHA-256 của **body bytes thực nhận** | Liên kết payload với chữ ký; verifier phải tự tính lại digest |

Giả sử hệ thống thiết kế profile `HMAC-HTTP-V1` dùng HMAC-SHA-256, canonical string **minh họa** như sau:

~~~text
HMAC-HTTP-V1
HMAC-SHA256
client-a-key-2026-01
POST
/orders?currency=VND&page=2
x-hmac-timestamp:2026-11-28T06:00:00Z
x-hmac-nonce:d4c7ae80e15b
content-type:application/json
body-sha256:<lowercase-hex-sha256>
~~~

Đây là **format do ứng dụng định nghĩa**, không phải chuẩn chung của mọi HMAC API. Hợp đồng thật phải xác định UTF-8, dòng `LF`, có newline cuối hay không, thứ tự và canonicalization của query, percent-encoding, header lặp, khoảng trắng header, body rỗng và path sau proxy. Các marker như `<lowercase-hex-sha256>` là placeholder.

Nếu body digest được mang qua một header riêng, verifier **phải tự băm body thực nhận** và so sánh giá trị đó với digest được ký. Chỉ đưa chuỗi digest do client gửi vào MAC mà không kiểm tra lại payload sẽ không chứng minh được body khớp với giá trị đã ký.

### 5.1. Không để thuật toán từ header tự quyết định chính sách

Giả sử request chứa:

~~~http
Authorization: HMAC keyId="client-a-key-2026-01",alg="HMAC-SHA256",signature="<base64>"
X-HMAC-Timestamp: 2026-11-28T06:00:00Z
X-HMAC-Nonce: d4c7ae80e15b
~~~

Tên scheme, cú pháp header ở trên chỉ là ví dụ. Trường `alg` từ HTTP ban đầu **chưa đáng tin**. Server có thể dùng nó làm dấu hiệu chọn parser, nhưng phải tra cứu danh sách **profile/thuật toán được phép** từ credential store và kiểm tra giá trị được chọn phù hợp với profile. Không hỗ trợ thuật toán tùy ý từ client hay tự tạo tên class/provider theo dữ liệu người gửi.

Với profile chỉ có HMAC-SHA-256, phương án đơn giản nhất là **không cần header `alg`**: version đã cố định thuật toán. Nếu muốn algorithm agility, hãy thiết kế profile version riêng và đưa định danh thuật toán/version vào dữ liệu ký hoặc ràng buộc bằng khóa/profile riêng, để không thể đổi `HMAC-SHA256` thành biến thể khác rồi được server chấp nhận.

Quy tắc xác minh: **chọn đúng một profile trước khi tính MAC; nếu xác minh thất bại thì từ chối, không thử lại bằng một thuật toán yếu hơn**. Đồng thời từ chối header trùng, xung đột hoặc hai profile được gửi trong cùng request nếu hợp đồng không cho phép.

### 5.2. Chống replay là phần độc lập của thuật toán

HMAC-SHA-512 mạnh hơn HMAC-SHA-256 về độ dài tag nhưng không ngăn kẻ tấn công **gửi lại nguyên request đã ký**. Vì vậy phải ký timestamp/nonce vào canonical request, giới hạn clock skew và claim nonce bằng thao tác **insert-if-absent nguyên tử** trong một kho dùng chung giữa các instance.

Ràng buộc nonce với credential/client đáng tin và giữ ít nhất hết cửa sổ chấp nhận timestamp cùng sai lệch đồng hồ cho phép. Nếu cùng credential được phép dùng cả profile cũ và mới, tránh tách namespace nonce theo thuật toán theo cách cho phép tái sử dụng cùng nonce xuyên profile. Chỉ claim nonce cho request có MAC hợp lệ để người ngoài không chiếm nonce bằng request giả mạo.

## 6. Quy trình ra quyết định chọn MAC

Một ADR (*Architecture Decision Record*) cho hệ thống HMAC có thể ghi:

| Quyết định | Ví dụ lựa chọn |
| --- | --- |
| Bài toán | Client-to-server HTTP request authentication với shared secret |
| Thuật toán mặc định | `HMAC-SHA256`, JCA `HmacSHA256` |
| Tag | Đủ 32 byte, Base64 chuẩn có padding |
| Secret | 32 byte từ CSPRNG, riêng theo client/môi trường |
| Hợp đồng ký | `HMAC-HTTP-V1`, ghi rõ method, canonical URI/query, signed headers, body digest, timestamp, nonce |
| Replay | Cửa sổ timestamp giới hạn; nonce store phân tán có insert nguyên tử |
| Tính tương thích | Golden vectors Java + các SDK, gateway, HTTP/1.1 và HTTP/2 |
| Algorithm agility | Phiên bản mới + key metadata + chuyển tiếp có thời hạn |
| Revocation | `keyId` có trạng thái; revoked luôn bị từ chối |
| Authorization | Kiểm tra quyền dựa trên principal đã xác thực, không suy từ MAC |

Quy trình:

1. Xác định trust boundary, ai giữ secret, các route chịu tác động và yêu cầu tuân thủ.
2. Chọn HMAC-SHA-256 nếu không có ràng buộc cụ thể buộc dùng họ MAC khác; xác minh mọi nền tảng mục tiêu cùng hỗ trợ.
3. Chốt canonical request và wire format bằng tài liệu có version, **trước** khi phát hành SDK.
4. Sinh secret an toàn, thiết kế key metadata, thu hồi và rotation.
5. Xuất golden vectors với byte canonical, secret thử nghiệm và MAC kỳ vọng; kiểm tra liên ngôn ngữ.
6. Đo performance trên request thật qua gateway, bao gồm body digest và nonce store.
7. Quy định quy trình thay thế thuật toán bằng profile/key mới, theo dõi adoption và mốc sunset.

Không chọn MAC dựa trên độ dài output đơn thuần. Nếu bottleneck là nonce store hoặc canonicalization body 10 MB, việc đổi từ HMAC-SHA-256 sang HMAC-SHA-512 thường không giải quyết điểm nghẽn cần tối ưu.

## 7. Java: tính và xác minh HMAC-SHA-256 đúng profile

Ví dụ dưới đây dùng Java 17 và JCA để **chỉ tính/so MAC** trên `canonicalRequestBytes` đã được chuẩn hóa. Nó không tự suy ra thuật toán từ header, không tự parse URI và không tự xử lý nonce. Các nhiệm vụ đó thuộc bộ xác thực request bao quanh.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacSha256Mac {
    private static final String JCA_NAME = "HmacSHA256";
    private static final int FULL_TAG_LENGTH = 32;

    private HmacSha256Mac() {}

    public static byte[] compute(byte[] sharedSecret, byte[] canonicalRequestBytes)
            throws GeneralSecurityException {
        if (sharedSecret == null || sharedSecret.length == 0
                || canonicalRequestBytes == null) {
            throw new IllegalArgumentException("Invalid HMAC inputs");
        }

        // Tạo Mac riêng cho mỗi phép tính; không dùng chung đối tượng
        // Mac mutable giữa nhiều request/luồng.
        Mac mac = Mac.getInstance(JCA_NAME);
        mac.init(new SecretKeySpec(sharedSecret, JCA_NAME));
        return mac.doFinal(canonicalRequestBytes);
    }

    public static boolean verify(
            byte[] sharedSecret,
            byte[] canonicalRequestBytes,
            String signatureBase64) throws GeneralSecurityException {

        if (signatureBase64 == null || signatureBase64.length() != 44) {
            return false; // Profile yêu cầu Base64 chuẩn có padding.
        }

        byte[] provided;
        try {
            provided = Base64.getDecoder().decode(signatureBase64);
        } catch (IllegalArgumentException invalidEncoding) {
            return false;
        }
        if (provided.length != FULL_TAG_LENGTH) {
            return false;
        }

        byte[] expected = compute(sharedSecret, canonicalRequestBytes);
        return MessageDigest.isEqual(expected, provided);
    }
}
~~~

**Phân tích:**

- `Mac.getInstance("HmacSHA256")` dùng HMAC-SHA-256 có sẵn trên nhiều Java provider. `SHA-256` không phải tên thay thế cho `HmacSHA256` trong API `Mac`.
- `compute` nhận **byte canonical** đã hoàn tất. Nếu client ký UTF-8 còn server tự chuyển sang charset khác, cùng secret cũng sinh MAC khác.
- `Base64.getDecoder()` thuộc Base64 chuẩn. Kiểm tra 44 ký tự và 32 byte thể hiện profile có padding; triển khai thật cần kiểm tra grammar Base64 **chính xác/canonical** nếu yêu cầu không chấp nhận nhiều cách encode cùng tag.
- `MessageDigest.isEqual` so sánh byte digest để hạn chế thông tin timing theo vị trí khác biệt; kiểm tra độ dài tag cố định trước đó là chủ ý.
- `Mac` là object có trạng thái: không dùng một instance chung cho đồng thời nhiều request nếu không có đồng bộ/thiết kế phù hợp.
- `sharedSecret` đến từ credential store đã kiểm tra trạng thái `active`, scope, owner và profile được phép. Không lấy shared secret hoặc thuật toán từ giá trị header do client tự khai.
- Ngoại lệ JCA/secret store cần được xử lý thành lỗi hạ tầng có kiểm soát, tránh tiết lộ key, thuật toán nội bộ hay dữ liệu ký trong HTTP response và log.

Ví dụ này chưa có các thành phần cần thiết để là **HTTP authentication filter** hoàn chỉnh: strict parser của `Authorization`, canonical path/query, body digest, timestamp window, nonce store, audit, key revocation, client block và authorization. Không ghép nhanh đoạn mã này vào controller rồi xem là toàn bộ lớp bảo vệ.

### 7.1. Golden vector độc lập cho HMAC-SHA-256

Để kiểm tra bản thân primitive và cách encode trước khi thử HTTP canonicalization, dùng một vector HMAC-SHA-256 phổ biến:

~~~text
key (hex): 0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b
message (UTF-8): Hi There
HMAC-SHA-256 (hex):
b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7
~~~

Đây là **test vector của primitive** (secret cố ý công khai để kiểm thử), không phải secret có thể dùng trong production. Sau đó phải xây dựng test vector thứ hai cho **canonical HTTP request hoàn chỉnh**, gồm method, URI, signed headers, body bytes, timestamp, nonce, chuỗi canonical và MAC đã biết. Vector primitive chạy đúng không đảm bảo hệ thống HTTP sẽ ký đúng.

## 8. Đặt MAC vào kiến trúc hệ thống

~~~mermaid
flowchart TD
    A[Client có shared secret] --> B[Tạo canonical request và HMAC tag]
    B --> C[HTTPS + gateway/WAF]
    C --> D[HMAC request parser / chọn profile]
    D --> E[Tra keyId và profile tại credential store]
    E --> F{Key active và profile hợp lệ?}
    F -- Không --> G[401 - lỗi xác thực chung]
    F -- Có --> H[Tạo canonical bytes + tính HMAC]
    H --> I{MAC đúng và body digest khớp?}
    I -- Không --> G
    I -- Có --> J[Timestamp + nonce store phân tán]
    J --> K{Fresh và nonce chưa dùng?}
    K -- Không --> G
    K -- Có --> L[Tạo trusted principal]
    L --> M[Chặn client / authorization]
    M --> N{Có quyền?}
    N -- Không --> O[403 Forbidden]
    N -- Có --> P[Xử lý nghiệp vụ]
~~~

**Proxy/gateway:** xác định chính xác canonical URI được ký ở đâu. Một gateway có thể rewrite path, query, host, encoding hoặc body. Nếu verifier ở backend, cần bảo đảm thông tin nó nhận tương ứng byte mà client đã ký; metadata request-target gốc chỉ đáng tin khi được gateway chuyển qua kênh nội bộ bảo vệ và header do client bên ngoài tự khai đã bị xóa. Nếu gateway xác thực tập trung rồi forward principal, downstream phải chỉ tin danh tính do gateway tạo và được xác thực, không nhận header giả mạo trực tiếp từ Internet.

**Body:** với payload lớn, body digest có thể là bước tốn thời gian hơn tính HMAC trên canonical string ngắn. Verifier phải tự tính body hash từ byte payload đúng theo hợp đồng; xử lý streaming/buffering có giới hạn để không làm cạn bộ nhớ hoặc thay đổi body trước controller.

**Thứ tự bảo mật:** xác minh chữ ký, timestamp/nonce, kiểm tra credential và block policy trước khi thực thi side effect; sau đó mới ra quyết định authorization. Một request có HMAC hợp lệ vẫn có thể bị `403` do thiếu quyền. Request dùng key revoked bị từ chối kể cả MAC tính ra đúng.

**HTTP status/observability:** có thể dùng `401` cho credential hoặc MAC sai, `403` cho principal hợp lệ nhưng thiếu quyền/bị chặn và `429` cho rate limit. Trả lỗi chung ra bên ngoài; log/audit nội bộ phân biệt `BAD_PROFILE`, `KEY_REVOKED`, `INVALID_MAC`, `REPLAY` và `AUTHORIZATION_DENIED` mà không ghi secret hoặc full signature.

## 9. Algorithm agility: đổi thuật toán mà không bị downgrade

Chọn HMAC-SHA-256 hôm nay không có nghĩa phải khóa chặt hệ thống vào một tên thuật toán mãi mãi. Tuy nhiên “hỗ trợ mọi thuật toán trong một header” là một anti-pattern.

### 9.1. Mẫu migration có kiểm soát

1. Tạo profile mới, chẳng hạn `HMAC-HTTP-V2`, quy định thuật toán mới, format chữ ký và canonical request tường minh.
2. Tạo `keyId`/shared secret mới cho client được nâng cấp. Credential metadata gắn với tập profile cho phép; khóa cũ không được tự cấp quyền cho thuật toán mới.
3. Triển khai server hiểu `V1` và `V2`, nhưng mỗi request chỉ được chọn **một profile**, kiểm tra đúng policy, không thử fallback khi MAC không khớp.
4. Canary một số client, đối chiếu golden vectors và kết quả qua tất cả gateway/region.
5. Chuyển client/key sang `V2-only`, giám sát tỷ lệ sử dụng V1 và công bố ngày sunset.
6. Thu hồi key V1 theo lịch, xóa code/credential legacy sau khi hết cửa sổ hỗ trợ. Nếu key lộ, revoked ngay không phụ thuộc thời hạn migration.

Khi hai profile tạm thời có thể dùng chung một credential, phải kiểm soát **replay xuyên profile** và ràng buộc profile/thuật toán vào nội dung ký. Tránh để `V1` và `V2` diễn giải cùng chuỗi byte theo hai ý nghĩa nghiệp vụ khác nhau.

### 9.2. Khi thuật toán không sẵn có

Một provider Java hoặc SDK có thể không hỗ trợ `HmacSHA3-256` dù hỗ trợ `HmacSHA256`. Đó là lỗi tương thích cần phát hiện ở thời điểm khởi động/canary, không phải lý do tự động chuyển sang `HmacSHA1` hay bỏ xác minh MAC. Server chỉ cho phép những profile đã được cấu hình, và nếu không thể xác minh đúng profile đã yêu cầu thì **từ chối request hoặc từ chối khởi động tính năng** theo thiết kế.

Thay đổi provider cũng cần kiểm tra lại vector và giới hạn môi trường: cùng algorithm name chưa đủ nếu mỗi phía dùng canonical bytes, encoding hoặc tag truncation khác nhau.

## 10. Kiểm thử để xác nhận lựa chọn thuật toán

| Ca kiểm thử | Điều kiện | Kết quả kỳ vọng |
| --- | --- | --- |
| Primitive vector | Key và message ở mục 7.1 | HMAC-SHA-256 hex khớp chính xác |
| MAC hợp lệ | Key active, canonical bytes đúng, Base64 tag đủ 32 byte | Xác thực thành công, chuyển sang chống replay và authorization |
| Sai secret | Dùng secret thuộc client khác | `401`; không cấp principal |
| Sai method | Thay `POST` thành `GET` sau khi ký | MAC không khớp |
| Sai URI/query | Thay một query param hoặc thay path | MAC không khớp |
| Sai signed header | Sửa timestamp, nonce hoặc header được ký | MAC không khớp |
| Sai body | Sửa body bytes, giữ body digest cũ | Từ chối vì body digest không khớp |
| Tag thiếu | Chỉ gửi một phần prefix MAC khi profile yêu cầu đủ 32 byte | Từ chối, không so prefix |
| Tag encode lỗi | Base64 malformed hoặc variant không được profile cho phép | Từ chối |
| Profile giả mạo | Client tự gửi `alg=HMAC-SHA512` khi key chỉ có V1/SHA256 | Từ chối theo chính sách |
| Downgrade | MAC V2 sai rồi thử làm request V1 | Không fallback V1 |
| Key revoked | MAC được tính đúng bằng secret đã thu hồi | `401`, không cấp principal |
| Timestamp cũ | HMAC đúng nhưng timestamp ngoài cửa sổ | Từ chối |
| Replay | Request có MAC đúng nhưng nonce đã được claim | Từ chối lần dùng lại |
| Nhiều instance | Nonce được claim ở node A, request lặp tới B | Node B cũng từ chối |
| Gateway rewrite | Path/query/body khác trước và sau proxy | Xác minh đúng representation đã được quy định; phát hiện mismatch |
| Thiếu quyền | HMAC đúng, client không có quyền vào tenant/route | `403` theo authorization |
| Key rotation | Key cũ/new key cùng được phép trong cửa sổ overlap | Đúng policy; key revoked luôn bị từ chối |
| Provider/SDK | Cùng golden vectors trên Java và SDK đối tác | MAC bytes giống nhau cho cùng key/canonical message |
| Hiệu năng | Benchmark request nhỏ/lớn ở tải mục tiêu | Đạt mục tiêu SLO; biết chi phí MAC, body digest, key lookup, nonce store |

Nên bổ sung kiểm thử đối kháng với duplicate query/header, percent-encoding khác nhau, body rỗng, UTF-8 bất thường, proxy forward header giả và MAC có độ dài khác nhau. Đối chiếu cả **side effect**: request sai MAC hoặc replay không được tạo giao dịch, xuất dữ liệu hoặc phát hành job.

### Những lỗi thường bị quy nhầm cho thuật toán

- **Sai chữ ký hàng loạt sau khi cập nhật proxy:** có thể do URI/query/body bị rewrite, không phải do HMAC-SHA-256 “không ổn định”.
- **Một client ký đúng nhưng gọi API ngoài quyền:** đây là authorization, không giải quyết bằng đổi sang SHA-512.
- **Request lặp vẫn được chấp nhận:** cần sửa timestamp/nonce store/idempotency, không phải chọn MAC dài hơn.
- **Một secret bị lộ:** phải revoke/rotate credential và điều tra; tăng tag từ 256 lên 512 bit không khôi phục bí mật.
- **CPU tăng sau thêm HMAC:** đo chi phí tính body digest, JSON serialization, cache miss, secret manager và replay store trước khi chọn thuật toán khác.

## 11. Checklist triển khai và quyết định cuối cùng

- [ ] Mục tiêu là xác thực HTTP request bằng shared secret, nên MAC phù hợp với threat model.
- [ ] Thuật toán của profile mới được chốt rõ, ưu tiên **HMAC-SHA-256** khi không có yêu cầu đặc biệt.
- [ ] Secret sinh từ CSPRNG, tách theo client/môi trường, lưu an toàn và có vòng đời/rotation/revocation.
- [ ] Tag đầy đủ 32 byte hoặc độ dài rút gọn **cố định được phê duyệt**, encoding được quy định rõ.
- [ ] Signing profile có version, algorithm binding, canonical method/URI/query/headers/body và domain separation.
- [ ] Key metadata kiểm soát profile được phép; không lấy `alg` từ request làm quyền quyết định thuật toán.
- [ ] Không fallback MAC khi verify thất bại; từ chối header xung đột, duplicate và profile không được hỗ trợ.
- [ ] So MAC bằng byte và API phù hợp; không log secret, chữ ký thô hoặc dữ liệu nhạy cảm.
- [ ] Timestamp và nonce đã được ký; replay store nguyên tử, dùng chung giữa instance/region.
- [ ] Gateway/proxy/SDK có golden vectors và test end-to-end với raw URI, signed headers và body bytes.
- [ ] Key revoked bị từ chối; client block và authorization tiếp tục hoạt động độc lập.
- [ ] Có benchmark tải thật, kế hoạch algorithm agility, canary, sunset và rollback an toàn.

**Kết luận thiết kế:** Đối với đa số API HMAC dùng shared secret, hãy bắt đầu bằng **HMAC-SHA-256, secret ngẫu nhiên 32 byte, tag đầy đủ 32 byte và một signing profile cố định có version**. Bảo đảm hai bên tạo cùng canonical bytes, xác minh nonce/timestamp, quản lý key đúng và phân quyền sau xác thực. Khi yêu cầu mới buộc thay thuật toán, thực hiện bằng profile và credential có chính sách rõ ràng, kiểm thử đa hệ thống và không cho phép downgrade ngầm.
