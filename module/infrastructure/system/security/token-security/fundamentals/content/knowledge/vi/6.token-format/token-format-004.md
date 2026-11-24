# Base64url không phải mã hóa bí mật

Trong chương **Token format** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, một nguyên tắc cơ bản cần nắm chắc là: **Base64url chỉ biến đổi cách biểu diễn dữ liệu thành chuỗi ký tự thuận tiện cho việc truyền tải; nó không giữ bí mật dữ liệu, không ngăn sửa dữ liệu và không xác thực người gửi.**

Đặc biệt, nhiều access token và ID token ở dạng JWT nhìn giống một chuỗi khó hiểu gồm các ký tự và dấu chấm. Điều đó khiến người mới học dễ tưởng rằng nội dung đã được mã hóa an toàn. Thực tế, **payload của JWT dạng JWS thông thường có thể được đọc mà không cần khóa**. Muốn API tin token, cần kiểm tra chữ ký và các điều kiện bảo mật; muốn bảo vệ tính bí mật của nội dung, phải có cơ chế **mã hóa thực sự** và quản lý khóa thích hợp.

Bài học liên hệ Base64url với JWT, opaque token, access token, refresh token và OAuth 2.0/OpenID Connect (OIDC), đồng thời phân biệt rõ **đọc được dữ liệu**, **xác minh được nguồn phát hành** và **được phép sử dụng token**.

## 1. Base64url giải quyết vấn đề gì?

Các hệ thống trao đổi thông tin thường cần đưa **byte tùy ý** vào một môi trường ưu tiên hoặc giới hạn ký tự, chẳng hạn URL, phần tử JSON, HTTP header hay một phần của cấu trúc token.

**Base64** là một phép *encoding*: nhóm các bit từ dữ liệu đầu vào và biểu diễn lại dưới dạng các ký tự ASCII. **Base64url** là biến thể của Base64 định nghĩa trong RFC 4648, sử dụng bảng ký tự phù hợp hơn với URL và tên tệp.

| Tiêu chí | Base64 truyền thống | Base64url |
|---|---|---|
| Bộ ký tự | `A-Z`, `a-z`, `0-9`, `+`, `/` | `A-Z`, `a-z`, `0-9`, `-`, `_` |
| Ký tự thứ 62 và 63 | `+` và `/` | `-` và `_` |
| Padding | Thường dùng `=` | Có thể có hoặc được lược bỏ theo quy tắc của giao thức |
| Mục đích | Biểu diễn dữ liệu nhị phân thành ký tự | Biểu diễn dữ liệu tương tự trong bối cảnh URL-safe |
| Bảo vệ bí mật | **Không** | **Không** |
| Chống giả mạo | **Không** | **Không** |

Base64url **không phải URL encoding** theo kiểu percent-encoding. Ví dụ `%20` là cách biểu diễn dấu cách trong URL; Base64url là cách biến đổi toàn bộ dãy byte bằng bảng ký tự 64 phần tử.

Dữ liệu được Base64url encoding vẫn có thể được khôi phục bằng **decoder công khai**, không cần password, khóa công khai hay khóa bí mật.

### Ví dụ đơn giản nhất

Chuỗi UTF-8:

~~~text
Dữ liệu gốc:          hello
Byte UTF-8 (hex):     68 65 6C 6C 6F
Base64url:            aGVsbG8

Decode "aGVsbG8" -> byte 68 65 6C 6C 6F -> "hello"
~~~

Người nhận biết chuỗi `aGVsbG8` có thể tự decode ra `hello`. Không có khóa bí mật nào tham gia.

Một ví dụ làm rõ sự khác biệt ký tự:

~~~text
Byte gốc (hex):       FB FF FF
Base64 thông thường:  +///
Base64url:            -___
~~~

Hai chuỗi biểu diễn **cùng ba byte**. Việc thay `+` bằng `-` và `/` bằng `_` giúp thuận tiện khi đưa vào ngữ cảnh URL; không tăng độ bí mật.

## 2. Base64url biến đổi dữ liệu như thế nào?

Một byte gồm 8 bit. Base64 chia dữ liệu thành nhóm **6 bit**, ánh xạ mỗi nhóm thành một ký tự trong bảng 64 phần tử. Ba byte đầu vào (24 bit) tạo thành bốn nhóm 6 bit.

~~~mermaid
flowchart LR
    A["Dãy byte gốc"] --> B["Ghép bit theo thứ tự"]
    B --> C["Chia thành các nhóm 6 bit"]
    C --> D["Ánh xạ bằng bảng ký tự Base64url"]
    D --> E["Chuỗi Base64url"]
    E --> F["Decoder đảo ngược ánh xạ"]
    F --> G["Khôi phục byte gốc"]
~~~

Nếu số bit không đủ để tạo nhóm cuối, thuật toán dùng quy tắc bổ sung bit và, trong nhiều biểu diễn, ký tự **padding `=`**. Khi một giao thức cho phép bỏ padding, decoder vẫn có thể xác định số byte gốc từ độ dài chuỗi và cấu trúc mã hóa hợp lệ.

Với n byte đầu vào, độ dài Base64 có padding thường là `4 × ceil(n / 3)` ký tự. Dữ liệu thường **dài hơn**, khoảng một phần ba, chứ không được nén. Việc bỏ padding chỉ giảm 0–2 ký tự cuối, không thay đổi ý nghĩa dữ liệu.

Điểm cần nhớ về padding:

- **Base64url** là định nghĩa về bảng ký tự và quy tắc mã hóa; việc có/không có `=` tùy chuẩn áp dụng.
- Trong **JWS/JWT Compact Serialization** thông thường, từng phần được Base64url encoding **không có padding**.
- Decoder cần tuân thủ cú pháp và giới hạn của giao thức cụ thể. Không nên tự động “sửa” mọi chuỗi sai định dạng để cố giải mã.

Ký tự được dùng chỉ là hình thức hiển thị. Vì giải mã khả nghịch, **đổi cách hiển thị không làm cho dữ liệu trở nên bí mật**.

## 3. Encoding, encryption, hashing và signing khác nhau ở đâu?

Bốn thuật ngữ dễ bị nhầm nhưng giải quyết các mục tiêu khác nhau.

| Kỹ thuật | Câu hỏi nó giải quyết | Có cần khóa bí mật? | Có khôi phục dữ liệu gốc? | Tự cung cấp bảo mật gì? |
|---|---|---|---|---|
| **Encoding** (Base64url) | Biểu diễn byte bằng ký tự thuận tiện thế nào? | Không | Có, ai cũng decode được | Không cung cấp tính bí mật, toàn vẹn hoặc xác thực |
| **Encryption** (mã hóa) | Làm sao người không có khóa không đọc được nội dung? | Có khóa phù hợp | Có, với khóa giải mã | Tính bí mật; mức bảo vệ toàn vẹn/xác thực tùy sơ đồ, nên dùng mã hóa có xác thực |
| **Cryptographic hash** | Tạo giá trị tóm tắt một chiều để phát hiện thay đổi trong ngữ cảnh đúng? | Không đối với hash thường; HMAC có khóa | Không thể đảo ngược một cách thực tế đối với hàm hash an toàn | Không tự xác thực nguồn dữ liệu; hash không khóa có thể bị tính lại |
| **Digital signature / MAC** | Làm sao phát hiện sửa đổi và xác minh bên có khóa hợp lệ? | Có khóa ký bí mật/private key hoặc khóa HMAC | Chữ ký/MAC không phải cơ chế khôi phục payload | Toàn vẹn và xác thực bên sở hữu khóa, **không che nội dung** |

Ví dụ:

- `Base64url("hello") = "aGVsbG8"`: mọi người đều có thể decode.
- Mã hóa có xác thực như AES-GCM: người thiếu khóa giải mã không đọc được plaintext và không thể sửa ciphertext mà không bị phát hiện, nếu dùng đúng cách.
- SHA-256: tạo một digest một chiều; **một digest được công bố công khai không chứng minh ai tạo dữ liệu**, vì bất cứ ai cũng có thể tính SHA-256 của dữ liệu mình bịa.
- JWS dùng chữ ký số hoặc MAC theo thuật toán đã chỉ định: phía xác minh có thể phát hiện payload đã bị sửa khi dùng đúng khóa và thuật toán được cho phép.

Một hệ thống có thể **vừa mã hóa, vừa ký/xác thực, rồi Base64url encoding** dữ liệu để dễ truyền. Các lớp có thể cùng xuất hiện, nhưng chức năng của chúng không thể thay thế cho nhau.

## 4. Vì sao JWT có nhiều ký tự lạ mà vẫn đọc được?

**JWT (JSON Web Token)** là một định dạng claims. Trong trường hợp phổ biến **JWT được bảo vệ bằng JWS**, Compact Serialization có dạng ba phân đoạn:

~~~text
BASE64URL(UTF8(header)).
BASE64URL(payload).
BASE64URL(signature_bytes)
~~~

Cấu trúc minh họa:

~~~mermaid
flowchart TD
    T["JWS Compact Token: header.payload.signature"] --> H["Phần 1: Protected header"]
    T --> P["Phần 2: Payload / claims"]
    T --> S["Phần 3: Signature"]
    H --> HD["Base64url decode -> JSON header"]
    P --> PD["Base64url decode -> JSON claims"]
    S --> SD["Byte chữ ký/MAC"]
    HD --> V["Xác minh bằng cấu hình và khóa tin cậy"]
    PD --> V
    SD --> V
    V --> A["Chỉ khi PASS mới xét iss, aud, exp, scope và policy"]
~~~

Hai phân đoạn đầu của JWT dạng JWS thông thường là dữ liệu **đọc được sau khi decode**. Phân đoạn chữ ký được biểu diễn bằng Base64url để vận chuyển thuận tiện; **chữ ký mới là cơ chế kiểm tra toàn vẹn/xác thực bằng khóa phù hợp**, không phải bản thân Base64url.

Header minh họa:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-11"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000600
}
~~~

Đây là **hai đối tượng JSON giải thích nội dung**, không phải JWT có chữ ký thật. Claim `sub`, `scope` và `aud` có thể bị người xem đọc được từ token JWS. Vì thế, **không nhúng mật khẩu, refresh token, dữ liệu y tế/tài chính chi tiết hay bí mật không cần thiết vào payload có thể đọc**.

Với JWS, header `alg` cho biết thuật toán được sử dụng, `kid` giúp tìm khóa trong tập khóa tin cậy đã được cấu hình. Đừng để dữ liệu header do client cung cấp quyết định thuật toán hoặc nguồn tải khóa theo cách không được kiểm soát.

> Một token có ba phần phân tách bằng dấu chấm chưa chắc là JWT hợp lệ. Ngay cả khi cả hai phần đầu decode thành JSON, đó vẫn chưa phải bằng chứng token do Authorization Server tin cậy phát hành.

### Có thể thay `scope` rồi encode lại không?

Có thể tạo **một chuỗi mới** bằng cách thay payload và Base64url encoding lại. Ví dụ người nào đó sửa:

~~~text
Payload ban đầu:  "scope": "orders:read"
Payload bị sửa:  "scope": "orders:write"
~~~

Nếu JWT có JWS signature hợp lệ, thay payload sẽ khiến chữ ký **không còn khớp**. Resource Server xác minh chữ ký đúng cách phải từ chối. Nhưng nếu backend chỉ decode Base64url và tin `scope`, người sửa có thể tự nâng quyền bằng cách thay claims.

Điều quan trọng không phải kẻ tấn công có thể đọc payload hay không; mà là **API có kiểm tra chữ ký và policy trước khi tin payload hay không**.

## 5. JWS và JWE: chữ ký khác mã hóa

JWT có thể được biểu diễn bằng **JWS** (JSON Web Signature) hoặc **JWE** (JSON Web Encryption), tùy thiết kế và profile.

| Thuộc tính | JWT dạng JWS thông thường | JWT dạng JWE Compact |
|---|---|---|
| Số phân đoạn thường thấy | 3 | 5 |
| Các phân đoạn | Protected header, payload, signature | Protected header, encrypted key, IV, ciphertext, authentication tag |
| Payload có thể Base64url decode trực tiếp thành claims? | Thường **có**, nhưng chưa đáng tin trước khi xác minh chữ ký | **Không**: claims nằm trong ciphertext cần giải mã |
| Tính bí mật của payload | Không | Có, nếu dùng đúng mã hóa và quản lý khóa |
| Toàn vẹn/xác thực | JWS signature/MAC và khóa xác minh phù hợp | Cơ chế mã hóa có xác thực bảo vệ nội dung; việc tin danh tính nguồn phát hành còn phụ thuộc khóa, profile và cách kiểm tra |
| Có thể thay cho kiểm tra `iss`, `aud`, `exp`, scope? | Không | Không |

JWE Compact có hình thức:

~~~text
BASE64URL(protected_header).
BASE64URL(encrypted_key).
BASE64URL(initialization_vector).
BASE64URL(ciphertext).
BASE64URL(authentication_tag)
~~~

Protected header của JWE vẫn có thể đọc được; **ciphertext không thể giải mã bằng Base64url đơn thuần**. Muốn lấy claims phải có khóa giải mã và dùng thuật toán, chế độ xác thực đúng chuẩn.

**Không suy luận “năm phần luôn an toàn hơn ba phần”.** Tính an toàn của JWE phụ thuộc sơ đồ mật mã, khóa, thuật toán, profile và việc xác thực claims sau giải mã. Một JWE được giải mã thành công nhưng không đúng issuer/audience hoặc thiếu quyền vẫn phải bị từ chối. Nếu cần vừa chứng minh danh tính người phát hành vừa giữ bí mật payload, có thể áp dụng mô hình ký và mã hóa lồng nhau theo profile thích hợp.

Trong thực tế, nhiều hệ thống dùng **JWT access token ký JWS** vì Resource Server cần xác minh nhanh, còn dữ liệu bí mật được giữ trong hệ thống backend. Không phải mọi token trong OAuth đều cần JWE.

## 6. Ví dụ Java: encode và decode Base64url

Java có sẵn `java.util.Base64` từ Java 8. Các hàm dưới đây minh họa rõ ràng tính **thuận nghịch**, không hề sử dụng mật mã:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class Base64UrlDemo {
    public static void main(String[] args) {
        String original = "hello";
        byte[] raw = original.getBytes(StandardCharsets.UTF_8);

        String encoded = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(raw);

        byte[] decodedBytes = Base64.getUrlDecoder().decode(encoded);
        String decoded = new String(
                decodedBytes, StandardCharsets.UTF_8
        );

        System.out.println("Encoded: " + encoded);
        System.out.println("Decoded: " + decoded);

        byte[] binary = {
            (byte) 0xFB, (byte) 0xFF, (byte) 0xFF
        };

        System.out.println(
            "Base64: " + Base64.getEncoder().encodeToString(binary)
        );
        System.out.println(
            "Base64url: " + Base64.getUrlEncoder()
                .withoutPadding().encodeToString(binary)
        );
    }
}
~~~

Kết quả mong đợi:

~~~text
Encoded: aGVsbG8
Decoded: hello
Base64: +///
Base64url: -___
~~~

`getUrlEncoder()` và `getUrlDecoder()` chỉ biết xử lý byte/encoding, **không biết gì về issuer, audience, signature, scope, token hết hạn hoặc quyền tài nguyên**.

### Decode payload JWT để quan sát cấu trúc

Khi phát triển hoặc học tập, có thể tách một **JWS Compact** thành ba phần, rồi decode phần giữa:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class JwtPayloadInspector {
    // CHỈ DÙNG CHO QUAN SÁT CẤU TRÚC TRONG MÔI TRƯỜNG HỌC TẬP.
    // KHÔNG trả kết quả này cho logic xác thực hay phân quyền.
    static String decodeUntrustedPayload(String compactJws) {
        String[] parts = compactJws.split("\\.", -1);

        if (parts.length != 3) {
            throw new IllegalArgumentException(
                "Expected three JWS Compact segments"
            );
        }

        byte[] payloadBytes = Base64.getUrlDecoder()
                .decode(parts[1]);

        return new String(payloadBytes, StandardCharsets.UTF_8);
    }
}
~~~

**Không dùng đoạn code này để chấp nhận token.** Nó không xác minh bất kỳ chữ ký nào và không bảo đảm phân đoạn thứ hai chứa JSON, đúng kiểu token hay đúng nguồn phát hành. Cũng không ghi token hoặc payload chứa dữ liệu riêng tư vào log production.

Đối với JWE Compact năm phân đoạn, cách `decode(parts[1])` chỉ trả byte encrypted key hoặc phần biểu diễn liên quan, **không cho bạn JSON claims gốc**.

## 7. Từ “decode” sang “verify”: khác biệt quyết định bảo mật

Giả sử API đơn hàng nhận request:

~~~http
GET /orders/123 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Bước đầu, API có thể phân tích cú pháp để nhận biết định dạng. **Nhưng việc parse/decoder thành công không tạo ra độ tin cậy.** Với JWT access token ký JWS, hệ thống cần dùng thư viện bảo mật được duy trì để:

1. **Giới hạn issuer đáng tin cậy** và cấu hình chính xác nơi lấy khóa công khai/JWKS. Không chấp nhận URL khóa tùy ý trong token để tự tải.
2. **Chỉ cho phép các thuật toán ký phù hợp** theo cấu hình/profile. Không chấp nhận `alg: none` hay nhầm khóa đối xứng và bất đối xứng.
3. **Xác minh chữ ký** trên đúng dữ liệu theo chuẩn JWS. Không tin `payload` cho tới khi chứng thực nguồn và tính toàn vẹn.
4. **Kiểm tra token đúng loại** theo profile, đặc biệt tránh nhận ID token thay access token.
5. **Kiểm tra `iss`, `aud`, `exp`, `nbf`** và các ràng buộc thời gian/claims bắt buộc. Audience phải dành cho API đang nhận request.
6. **Kiểm tra `scope`/role/quyền được cấp** theo hợp đồng, sau đó kiểm tra **quyền trên tài nguyên cụ thể** như chủ đơn hàng hoặc tenant.
7. **Kiểm tra tình trạng thu hồi hoặc sender constraint nếu hệ thống yêu cầu**, chẳng hạn denylist, phiên server, DPoP/mTLS hoặc introspection.
8. **Từ chối khi kiểm tra thất bại**, không tiếp tục phân quyền dựa trên payload chưa xác thực.

Pseudocode theo tư duy “verify rồi mới authorize”:

~~~text
function getOrder(request, orderId):
    bearer = extractAccessToken(request)

    verified = verifyAccessTokenWithTrustedConfiguration(
        bearer,
        issuer = "https://auth.example.test",
        audience = "https://orders-api.example.test",
        allowedSignatureAlgorithms = ["RS256"],
        trustedKeySet = configuredIssuerJWKS
    )

    if verified is invalid or tokenExpired(verified):
        return 401

    if "orders:read" not in verified.scopes:
        return 403

    order = database.getOrder(orderId)

    if order is missing:
        return 404

    if not mayReadOrder(
        subject = verified.subject,
        client = verified.clientId,
        order = order
    ):
        return 403

    return 200, order
~~~

Đây là **mã giả**, không phải API bảo mật thực của một thư viện Java. Nó cho thấy rõ: quyền được kiểm tra dựa trên **claims đã xác minh**, đồng thời phải kiểm tra quyền với đơn hàng cụ thể. Token có `orders:read` không cho phép đọc mọi đơn hàng.

### Mẫu sai phổ biến

~~~text
payload = Base64UrlDecode(token.middleSegment)
claims = parseJson(payload)

if claims["scope"] contains "admin":
    allowAdminAction()    // LỖI NGHIÊM TRỌNG
~~~

Người gửi token có thể tự tạo phần giữa chứa `admin`. Nếu API không xác minh chữ ký, việc dùng `scope` như dữ liệu có thẩm quyền là một lỗ hổng phân quyền trực tiếp.

Tương tự, không được lấy `sub` từ ID token chưa xác minh rồi lập phiên đăng nhập. Với OIDC, client cần xác minh ID token theo quy tắc issuer, audience/client ID, signature, `exp`, `nonce` khi có dùng và các ràng buộc liên quan.

## 8. Base64url và các loại token trong OAuth 2.0/OIDC

**Token dùng để làm gì** là một câu hỏi; **token biểu diễn thế nào** lại là câu hỏi khác.

| Token | Mục đích | Có luôn là Base64url/JWT không? | Thành phần cần kiểm tra |
|---|---|---|---|
| **Access token** | Client trình cho Resource Server để truy cập API | Không. Có thể JWT/JWS, JWE hoặc opaque theo thiết kế | API kiểm tra token, audience, scope, thời gian, trạng thái và quyền từng tài nguyên |
| **Refresh token** | Client gửi token endpoint để xin access token mới | Không. Thường là chuỗi bí mật opaque; AS có thể dùng định dạng khác | AS kiểm tra client, grant, thời hạn, rotation, revocation và ràng buộc nếu có |
| **ID token (OIDC)** | Client nhận thông tin về sự kiện xác thực user | Theo OIDC, thường là JWT được ký; một số profile cho phép các cấu hình bảo vệ khác | Client kiểm tra signature/issuer/audience/nonce/thời gian theo OIDC |
| **Opaque token** | Một định dạng token không có claims để API tự đọc trực tiếp | Không suy đoán từ hình thức chuỗi | API cần introspection hoặc nguồn trạng thái đáng tin cậy |

Ví dụ access token opaque:

~~~text
2Gj6mQ1nxN7vAq3eK5Lf...    (chỉ là chuỗi minh họa)
~~~

Dù chuỗi này trông như Base64url, **không thể suy ra nội dung claims bằng cách decode**. Có thể chuỗi chỉ là một handle ngẫu nhiên trỏ tới bản ghi token phía AS. Cách kiểm tra đúng là introspection hoặc hợp đồng tra trạng thái mà Resource Server và AS đã thiết kế.

Một access token JWT còn hợp lệ về chữ ký có thể đã bị **thu hồi** theo chính sách. Base64url hoàn toàn không cho biết trạng thái đó; muốn thu hồi trước `exp` thì các thành phần phải có cơ chế trạng thái, denylist, token ngắn hạn hoặc tín hiệu phù hợp.

## 9. Đọc được payload có làm token “không an toàn” không?

Không thể kết luận như vậy. Với JWS, **tính bí mật** không được thiết kế là mục tiêu; mục tiêu là **tính toàn vẹn và xác thực bằng khóa**. Điều cần xét là token có chứa dữ liệu không nên lộ hay không, được truyền/lưu thế nào và bên nhận có kiểm tra đầy đủ không.

Ví dụ một access token cho API đơn hàng có:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read",
  "exp": 1800000600
}
~~~

Một người lấy được JWT JWS có thể decode để thấy subject và scope. Đây là lý do **không coi payload JWT như kho bí mật**. Tuy nhiên, người đó không thể tùy ý thay `scope` mà vẫn tạo chữ ký RS256 hợp lệ nếu không có khóa ký tương ứng và verifier được triển khai đúng.

Cần phân biệt hai kiểu rủi ro:

- **Đọc nội dung:** người nhìn thấy token có thể thấy claims không được mã hóa; đây là nguy cơ lộ thông tin nếu đưa dữ liệu riêng tư vào JWS.
- **Sử dụng lại bearer token:** người giữ bản sao **toàn bộ access token** có thể gửi lại cho API trong thời gian token còn được chấp nhận. Chữ ký JWS giúp chống giả mạo payload nhưng **không tự ngăn replay**.

Bởi vậy, dù JWT có chữ ký mạnh, **bản thân bearer token vẫn là thông tin nhạy cảm về quyền truy cập**. Cần bảo vệ toàn bộ chuỗi token trước rò rỉ, không chỉ bảo vệ dữ liệu bí mật chứa bên trong.

## 10. Bảo vệ token trên đường truyền và tại nơi lưu trữ

| Nguy cơ | Vì sao Base64url không giúp | Biện pháp thực tế |
|---|---|---|
| Token lộ trong HTTP không mã hóa | Encoding ai cũng đảo ngược được | Dùng HTTPS/TLS, kiểm tra chứng chỉ và endpoint |
| Token nằm trong query URL | Có thể lọt vào log, lịch sử, referrer, analytics | Truyền access token trong `Authorization: Bearer` khi phù hợp; không đặt token vào URL |
| JWT chứa email, dữ liệu cá nhân quá chi tiết | Payload JWS đọc được sau Base64url decode | Giảm claim tối thiểu, giữ dữ liệu riêng tư phía server; cân nhắc JWE khi có nhu cầu bí mật thực |
| Token lưu ở `localStorage` | XSS có thể đọc token qua JavaScript | Ưu tiên BFF/phiên backend khi phù hợp; giảm thời gian lưu trên browser và chống XSS |
| Token rơi vào log | Log người khác đọc được chuỗi nguyên vẹn | Không log bearer token, refresh token, authorization code, cookie phiên hoặc dữ liệu nhạy cảm |
| Refresh token bị sao chép | Kẻ tấn công có thể đổi ra access token mới | Kho lưu bí mật an toàn, rotation/reuse detection hoặc sender-constrained token |
| Access token bị replay | Chữ ký vẫn đúng trên bản sao | Scope tối thiểu, TTL ngắn, DPoP/mTLS khi hỗ trợ, thu hồi/trạng thái khi cần |
| Phân quyền sai ở API | Decode đúng không chứng minh user có quyền đối tượng | Xác minh chữ ký/claims và ACL, tenant, chủ sở hữu dữ liệu ở từng request |

Ví dụ truyền access token hợp lệ:

~~~http
GET /orders/123 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

Kể cả khi transport đã dùng HTTPS, vẫn cần kiểm tra token ở Resource Server: **mã hóa đường truyền bảo vệ dữ liệu khi di chuyển; xác minh JWT bảo vệ nguồn claims; phân quyền API bảo vệ tài nguyên**. Ba nhiệm vụ khác nhau.

Một ứng dụng web dùng BFF có thể giữ token ở backend, còn browser giữ cookie phiên có `Secure`, `HttpOnly` và `SameSite` phù hợp. Kiến trúc này giảm việc JavaScript trực tiếp tiếp cận token, nhưng vẫn cần chống XSS, CSRF, session fixation và kiểm tra quyền từng thao tác.

## 11. Phân tích lỗi từ tình huống thực tế

Một nhóm phát triển xây API nhận access token JWT do `auth.example.test` cấp. Trong code cũ, middleware chỉ dùng decoder để đọc payload, kiểm tra `exp` và `role`, rồi cho phép gọi API. Một người kiểm thử tạo một chuỗi JSON có `"role":"admin"`, Base64url encode payload và gửi một JWT tự tạo.

**Vì sao lỗ hổng xuất hiện?** Bởi vì server đã coi dữ liệu do người gửi tự cung cấp là thông tin đáng tin, không kiểm tra chữ ký. Bất kỳ ai cũng có thể thực hiện encoding tương tự.

**Cách sửa theo đúng nguyên lý:**

1. Dùng thư viện xác minh JWT đáng tin cậy, cấu hình issuer chính xác và lấy khóa từ JWKS của AS được tin cậy.
2. Chỉ chấp nhận thuật toán phù hợp, xác minh chữ ký trước khi dùng claims; từ chối token sai `iss`, `aud` hoặc quá hạn.
3. Xác định đúng access token profile và scope; không dùng ID token của client để thay thế.
4. Kiểm tra scope/role ở endpoint và quyền trên tài nguyên cụ thể; không chỉ kiểm tra `role` rồi cho xem mọi dữ liệu.
5. Kiểm soát logging, TLS, lưu trữ và thời hạn token; nếu cần thu hồi JWT tức thời, bổ sung cơ chế trạng thái thay vì trông chờ Base64url.

### Bảng đánh giá nhanh

| Tình huống | Kết luận |
|---|---|
| JWT JWS có payload được Base64url decode thành JSON | **Chưa xác thực**; chỉ đọc được dữ liệu |
| Người nhận thay `orders:read` thành `orders:write` rồi encode lại | Chuỗi mới có thể tạo được, nhưng **chữ ký cũ không còn hợp lệ** |
| API chỉ kiểm tra `exp` từ JSON decode | **Sai**: người gửi tự bịa `exp` được |
| JWT JWS có chữ ký hợp lệ nhưng `aud` là API khác | **Từ chối**: sai nơi nhận |
| JWT JWS đã xác minh nhưng `sub` không có quyền đọc đơn hàng 123 | **Từ chối**: thiếu quyền tài nguyên |
| JWT JWS bị đánh cắp nguyên vẹn | Có thể bị replay trong thời gian còn hiệu lực nếu là bearer token và không có cơ chế ngăn phù hợp |
| JWE có năm phân đoạn | Không thể decode ciphertext thành claims bằng Base64url đơn thuần; cần giải mã hợp lệ |
| Một opaque token trông giống Base64url | Không tự suy ra claims; API theo cơ chế introspection/tra cứu được tin cậy |

## 12. Thực hành tự kiểm tra kiến thức

**Bài tập 1 — Khôi phục dữ liệu.** Tại sao chuỗi `aGVsbG8` không được coi là bí mật? Vì bất kỳ ai biết Base64url đều decode thành `hello`, không cần khóa.

**Bài tập 2 — Đánh giá claims.** Một JWT có `scope: "files:read"`, nhưng bạn mới chỉ decode phần payload. Có được cho truy cập API đọc file không? **Không.** Cần xác minh chữ ký/issuer/audience/thời gian/profile, sau đó kiểm tra quyền với file cụ thể.

**Bài tập 3 — So sánh JWS/JWE.** Nhìn thấy JWT ba phần JWS thường cho biết payload có thể đọc được. JWT năm phần JWE có ciphertext cần khóa để giải mã. Nhưng **cả hai** vẫn cần được kiểm tra claims và policy sau bước bảo vệ mật mã tương ứng.

**Bài tập 4 — Tránh nhầm token.** ID token đã được client xác minh thành công có dùng làm access token cho API không? **Không.** Trong OIDC, ID token chủ yếu dành cho client; Resource Server cần access token hợp lệ dành cho API.

**Bài tập 5 — Quyền sau khi thu hồi.** Một JWT JWS có `exp` chưa tới nhưng người dùng đã đăng xuất. Base64url có thể cho biết token đã bị thu hồi chưa? **Không.** API cần cơ chế trạng thái/denylist hoặc chờ hết thời hạn theo thiết kế.

## 13. Checklist khi gặp chuỗi Base64url/JWT

1. **Nhận diện đúng mục tiêu:** Base64url encoding để biểu diễn byte, không che giấu bí mật hay xác minh chủ thể.
2. **Không đánh đồng decode và verify:** đọc payload trước xác minh chỉ dùng cho quan sát, không dùng làm căn cứ phân quyền.
3. **Phân biệt JWS và JWE:** JWS thông thường ba phần, payload có thể đọc; JWE Compact năm phần, ciphertext cần giải mã.
4. **Không đưa bí mật vào JWS payload:** chỉ giữ claims cần thiết, giảm dữ liệu nhạy cảm.
5. **Xác minh token bằng thư viện tin cậy:** kiểm tra thuật toán, chữ ký/khóa, issuer, audience, loại token, thời gian và policy.
6. **Kiểm tra quyền ở Resource Server:** scope không tự cho quyền với mọi object hoặc tenant.
7. **Phân biệt token theo mục đích:** access token cho API, refresh token cho AS, ID token cho client OIDC; opaque token tra trạng thái theo hợp đồng.
8. **Bảo vệ bản thân bearer token:** TLS, storage an toàn, không URL/log, TTL phù hợp, thu hồi và chống replay khi cần.
9. **Không suy đoán sự an toàn từ hình thức chuỗi:** dài, nhiều ký tự lạ hoặc có dấu chấm không có nghĩa được mã hóa hay hợp lệ.
10. **Đọc chuẩn kỹ thuật theo ngữ cảnh:** Base64url, JOSE/JWS/JWE, JWT và OAuth mỗi thứ có yêu cầu riêng.

**Ý chính cần nhớ:** Base64url có thể được đảo ngược công khai và chỉ phục vụ **biểu diễn dữ liệu**. **JWS signature** dùng để kiểm tra tính toàn vẹn và nguồn ký theo khóa tin cậy; **JWE encryption** dùng để giữ bí mật nội dung khi triển khai đúng; **OAuth/OIDC và Resource Server** quyết định token có đúng mục đích, còn hạn, đủ scope và quyền truy cập hay không. Không một bước Base64url decode nào có thể thay thế các kiểm tra đó.

### Tài liệu tham khảo

- [RFC 4648 — Base Data Encodings](https://www.rfc-editor.org/rfc/rfc4648), đặc biệt Section 5: bảng ký tự Base64url.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): cấu trúc JWS và xác minh chữ ký.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): cấu trúc JWE, ciphertext và bảo vệ nội dung.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claims và định dạng JWT.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): tránh nhầm token, thuật toán và các lỗi xác minh.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): yêu cầu với JWT access token.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách gửi bearer token và rủi ro nếu bị đánh cắp.
