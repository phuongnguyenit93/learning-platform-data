# Cấu trúc JWT, chữ ký và vì sao nội dung không mặc nhiên được mã hóa

> **Chủ đề:** Spring Security – fundamentals → **Token và giao thức**. Mục tiêu: đọc đúng cấu trúc JSON Web Token (JWT), hiểu Base64url, phân biệt chữ ký/MAC với mã hóa, biết JWT nào là JWS/JWE, kiểm tra chữ ký **và** claims trước khi tin token, đồng thời áp dụng an toàn trong Spring Security OAuth2 Resource Server. Ví dụ dùng Java 17+ và Spring Boot 3.x/Spring Security 6.x.

## 1. JWT là gì? JWT không đồng nghĩa với “chuỗi dữ liệu đã mã hóa”

**JWT (JSON Web Token)** là định dạng truyền các **claims** (các phát biểu về một subject) dưới dạng JSON, được đóng gói theo chuẩn JOSE. Claims có thể được **ký hoặc bảo vệ tính toàn vẹn** bằng JSON Web Signature (JWS), hoặc được **mã hóa** bằng JSON Web Encryption (JWE). Một JWT thậm chí có thể không được bảo vệ nếu sử dụng dạng unsecured theo đặc tả; các JWT kiểu này **không phù hợp để tin dùng làm thông tin xác thực** khi không có lớp bảo vệ độc lập được thiết kế rõ ràng.

Ba nhận định thường bị nhầm:

1. **JWT là một định dạng token**, không tự đảm bảo token đáng tin, còn hạn, đúng đối tượng hay mang quyền thích hợp.
2. **JWS bảo vệ tính toàn vẹn và nguồn phát hành** khi thuật toán và khóa được chọn/xác minh đúng, nhưng payload JWS thông thường **không bí mật**. Bất kỳ ai giữ chuỗi JWT dạng JWS compact đều có thể Base64url-decode header và payload.
3. **JWE là lớp bảo mật nội dung bằng mã hóa**; recipient có khóa phù hợp mới giải mã được. JWE cũng cần kiểm tra thuật toán, key, tag xác thực, claims và chính sách người nhận.

Câu nói “JWT đã có signature nên payload được mã hóa” là **sai**. Chữ ký số (signature) và mã hóa (encryption) giải quyết các mục tiêu khác nhau. Trong API dùng access token JWT theo OAuth2, hình thức phổ biến là **signed JWT/JWS**, vì API cần biết claim có bị sửa hay không nhưng không mặc định cần che payload khỏi bên cầm token. Trái lại, nếu claims thực sự cần bí mật với những bên không sở hữu khóa giải mã, cần thiết kế **JWE hoặc mô hình truyền dữ liệu nhạy cảm khác**.

## 2. Ba mục tiêu bảo mật không được đánh đồng

| Mục tiêu | Câu hỏi | Cơ chế tiêu biểu | Điều không được suy ra |
|---|---|---|---|
| **Tính toàn vẹn (integrity)** | Token có bị thay nội dung không? | JWS signature/MAC xác minh bằng khóa được tin cậy | Nội dung bên trong đã bị che |
| **Tính xác thực của bên ký** | Có đúng hệ thống được phép phát hành/ký không? | Chữ ký + khóa tin cậy, ràng buộc issuer, policy thuật toán | Người cầm token hiện tại là chủ hợp pháp hoặc có đủ quyền |
| **Bí mật (confidentiality)** | Người khác có đọc được claims không? | JWE mã hóa, quản lý khóa, TLS khi truyền | Mã hóa tự quyết định người gọi được thao tác gì |
| **Tính hợp lệ của claims** | Issuer/audience/thời hạn/loại token đúng mục đích không? | `iss`, `aud`, `exp`, `nbf`, token type và policy chuyên biệt | Chỉ cần signature đúng là đủ |
| **Phân quyền (authorization)** | Subject/scope/role này được gọi API nào, dữ liệu nào? | Spring Security rules + business authorization | Có JWT hợp lệ thì làm được mọi thứ |

**Quy tắc vận hành:** một access token chỉ được chấp nhận khi **đủ cả ba tầng**: cấu trúc/thuật toán/khóa đúng → chữ ký hoặc JWE được xác minh và claims hợp lệ → quyền đối với request/tài nguyên được kiểm tra. Không bỏ qua tầng cuối vì JWT chứa `role=ADMIN`.

## 3. Cấu trúc một JWT dạng JWS compact: ba phần

Đối với JWT dùng **JWS Compact Serialization**, định dạng thường gặp là:

```text
BASE64URL(UTF-8(JOSE header))
.
BASE64URL(UTF-8(claims payload))
.
BASE64URL(signature-or-MAC)
```

Khi viết gọn:

```text
xxxxx.yyyyy.zzzzz
  1     2     3
  │     │     └─ signature/MAC
  │     └─────── JWT claims payload
  └───────────── JOSE header
```

Tách bằng **hai dấu chấm** thành **ba segment**. Ba phần trong ví dụ đều được Base64url-encode, nhưng **Base64url không phải mã hóa bí mật**. Nó chỉ biến bytes thành chuỗi phù hợp để truyền an toàn trong URL/header.

### 3.1. JOSE header: metadata về cách bảo vệ token

Ví dụ:

```json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "key-2026-11"
}
```

- `alg`: thuật toán được sử dụng cho JWS; `RS256` là chữ ký RSA với SHA-256, `ES256` là ECDSA P-256/SHA-256, `HS256` là HMAC-SHA-256. **Server không được tin mù giá trị `alg` do attacker gửi**; chỉ chấp nhận thuật toán được cấu hình trong policy.
- `typ`: gợi ý kiểu đối tượng, ví dụ `JWT`. Chỉ có `typ=JWT` **không chứng minh token là access token**, không chứng minh issuer, signature hay quyền.
- `kid`: key identifier giúp chọn khóa trong **tập khóa đã tin cậy** (ví dụ JWKS được cấu hình). Nó **không phải một lệnh cho server tải khóa từ URL bất kỳ**; giá trị này cũng là nội dung do bên gửi token kiểm soát cho tới khi xác minh token.
- Các header parameter khác như `jwk`, `jku`, `x5u`, `crit` cần xử lý theo chính sách/đặc tả; nếu không hỗ trợ thì từ chối, không tự đi fetch URL ngoại lai từ header.

Header **có thể đọc được** trước khi xác minh; tuy nhiên “đọc được” không có nghĩa là “đáng tin”. Việc đọc `kid` để chọn khóa trong danh sách tin cậy là một bước kỹ thuật, còn quyết định chấp nhận `alg`/khóa/claims phải xuất phát từ cấu hình server.

### 3.2. Payload: các claims dạng JSON

Ví dụ claims payload minh họa:

```json
{
  "iss": "https://issuer.example.com",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1793491200,
  "nbf": 1793491200,
  "exp": 1793494800,
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a"
}
```

Đây là **JSON ví dụ**, không phải bằng chứng token thực sự được issuer tin cậy ký. Các giá trị `iat`/`nbf`/`exp` là **NumericDate theo giây**, không phải milliseconds; ví dụ trên chỉ minh họa hình dạng. Việc claims có đủ hoặc đúng cho một ứng dụng phụ thuộc chính sách phát hành và xác minh token thực tế.

Những claim phổ biến:

| Claim | Ý nghĩa | Kiểm tra quan trọng |
|---|---|---|
| `iss` (issuer) | Ai là bên phát hành token | Phải khớp chính xác issuer tin cậy |
| `sub` (subject) | Token nói về ai | Gắn đúng user/service; không đồng nghĩa người đó đang sở hữu browser |
| `aud` (audience) | Token được cấp cho resource/service nào | Phải chứa audience của API hiện tại |
| `exp` (expiration time) | Mốc hết hiệu lực | Không chấp nhận token đã hết hạn, trừ clock skew nhỏ được quy định |
| `nbf` (not before) | Thời điểm token bắt đầu có hiệu lực | Từ chối token chưa tới thời gian hiệu lực |
| `iat` (issued at) | Thời điểm phát hành | Hỗ trợ kiểm tra hợp lý/tuổi token, không phải tất cả hệ thống đều kiểm tra cùng chính sách |
| `jti` (JWT ID) | ID token | Có ích cho audit/denylist/chống replay theo thiết kế |
| `scope`/`scp` | Quyền OAuth2 | Format và cách map thành authorities phụ thuộc issuer/framework |
| `roles`/`permissions` | Role/quyền riêng | Không có một schema thống nhất cho mọi issuer |
| `tenant_id` | Tenant theo thiết kế hệ thống | Phải dựa vào issuer đáng tin và kiểm soát ownership/tenant ở server |

**Cẩn thận dữ liệu nhạy cảm:** payload JWS không nên chứa mật khẩu, khóa bí mật, số thẻ, dữ liệu cá nhân không cần thiết hoặc token có thể dùng để truy cập hệ thống khác. Dù có HTTPS bảo vệ đường truyền, chính **người đang cầm token** vẫn có thể giải mã payload JWS. JWT đưa vào log, ticket, URL hoặc công cụ ngoài cũng khiến nội dung có nguy cơ bị lộ.

### 3.3. Signature hoặc MAC: không phải “mật khẩu mã hóa”

Với JWS, phần thứ ba là kết quả tính chữ ký/MAC trên **encoded header + dấu chấm + encoded payload**:

```text
signingInput =
    BASE64URL(header bytes) + "." + BASE64URL(payload bytes)

signatureBytes =
    SIGN_OR_MAC(private-or-secret-key, signingInput)

compactJws =
    BASE64URL(header) + "." +
    BASE64URL(payload) + "." +
    BASE64URL(signatureBytes)
```

**HMAC (HS256)**: bên phát hành và bên xác minh có thể cùng dùng một **secret key**; ai giữ secret đều có thể tạo MAC hợp lệ. Không nên chia sẻ HMAC secret quá rộng giữa nhiều service.

**Chữ ký bất đối xứng (RS256/ES256)**: issuer giữ **private key** để ký, resource server dùng **public key** tin cậy để xác minh; biết public key không cho phép ký ra token hợp lệ. Đây là mô hình phù hợp khi nhiều API cần xác minh nhưng không nên có quyền phát hành token.

Để chữ ký có nghĩa, phải xác minh **đúng thuật toán**, **đúng khóa tin cậy**, **đúng signing input** và **đúng claims**. Một chuỗi nhìn giống signature không chứng minh rằng đã được kiểm tra.

## 4. Base64url khác Base64 thường và khác mã hóa

Base64url là biến thể Base64 dùng tập ký tự phù hợp URL: thường thay `+` bằng `-`, `/` bằng `_` và bỏ padding `=` trong compact token. Cả hai đều là cách biểu diễn dữ liệu, không phải cipher hay hash.

| Phép xử lý | Có thể đảo ngược chỉ bằng dữ liệu đầu vào? | Có bí mật? | Ví dụ |
|---|---|---|---|
| Base64 / Base64url | **Có**, chỉ cần decoder | **Không** | Header/payload JWS |
| SHA-256 hash | Không thể giải ngược trực tiếp | Không phải encryption | Fingerprint/digest |
| HMAC-SHA256 | Cần secret để tính/kiểm tra MAC hợp lệ | Không giấu payload | `HS256` |
| RSA/ECDSA signature | Xác minh bằng public key, ký bằng private key | Không giấu payload | `RS256`, `ES256` |
| Authenticated encryption | Cần đúng key và tag | Có, theo thiết kế | JWE với AES-GCM |

**Đừng nhầm:** “Đã Base64url-encode JSON thành chuỗi khó đọc” chỉ làm dữ liệu ít trực quan, không phải bảo mật nội dung. Một trang web/đoạn code bất kỳ có thể decode JWS payload **mà không cần khóa ký**. Việc decode payload để hiển thị chỉ là thao tác đọc chuỗi, **không tạo ra authentication**.

## 5. Ví dụ Java 17 độc lập: ký HMAC và chứng minh payload vẫn đọc được

Ví dụ này có hai mục tiêu: (1) tự tạo JWS compact 3 phần để thấy cấu trúc, (2) giả mạo payload sau khi ký để xem xác minh MAC thất bại. Nó dùng **JDK 17 thuần**, không cần Spring/Maven.

**Giới hạn an toàn:** secret trong source chỉ phục vụ demo, không dùng production. Chương trình chỉ minh họa integrity; **không thực hiện đầy đủ JWT validation** (`iss`, `aud`, `exp`, `nbf`, rotation, loại token...) và không được đưa làm cơ chế authentication của API thật. Production nên dùng thư viện JOSE/JWT chuẩn đã được cập nhật và quản lý khóa bằng vault/KMS.

Tệp `JwtStructureDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class JwtStructureDemo {

    // CHỈ DÙNG TRONG BÀI HỌC; secret hardcode không phù hợp production.
    private static final byte[] DEMO_SECRET =
        "demo-only-secret-with-32-plus-bytes!".getBytes(
            StandardCharsets.UTF_8);

    private static final String HEADER =
        "{\"alg\":\"HS256\",\"typ\":\"JWT\"}";

    private static String encode(String text) {
        return Base64.getUrlEncoder().withoutPadding()
            .encodeToString(text.getBytes(StandardCharsets.UTF_8));
    }

    private static String decode(String segment) {
        return new String(
            Base64.getUrlDecoder().decode(segment),
            StandardCharsets.UTF_8
        );
    }

    private static byte[] hmac(String signingInput)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(DEMO_SECRET, "HmacSHA256"));
        return mac.doFinal(
            signingInput.getBytes(StandardCharsets.US_ASCII));
    }

    private static String issue(String payload)
            throws GeneralSecurityException {
        String input = encode(HEADER) + "." + encode(payload);
        String signature =
            Base64.getUrlEncoder().withoutPadding()
                .encodeToString(hmac(input));
        return input + "." + signature;
    }

    private static boolean signatureValid(String token)
            throws GeneralSecurityException {
        String[] parts = token.split("\\.", -1);
        if (parts.length != 3) {
            return false;
        }
        try {
            // Chỉ nhận đúng header cố định trong mô hình minh họa.
            if (!HEADER.equals(decode(parts[0]))) {
                return false;
            }
            byte[] received =
                Base64.getUrlDecoder().decode(parts[2]);
            byte[] expected = hmac(parts[0] + "." + parts[1]);

            return MessageDigest.isEqual(received, expected);
        } catch (IllegalArgumentException invalidBase64) {
            return false;
        }
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        String payload = "{\"sub\":\"alice\",\"scope\":\"read\"}";
        String token = issue(payload);
        String[] parts = token.split("\\.", -1);

        System.out.println("Parts: " + parts.length);
        System.out.println("Header: " + decode(parts[0]));
        System.out.println("Payload: " + decode(parts[1]));
        System.out.println("Valid signature: " + signatureValid(token));

        String changedPayload =
            "{\"sub\":\"admin\",\"scope\":\"read\"}";
        String tampered = parts[0] + "." +
            encode(changedPayload) + "." + parts[2];

        System.out.println("Tampered valid: " +
            signatureValid(tampered));
    }
}
```

Biên dịch và chạy (JDK 17+):

```bash
javac JwtStructureDemo.java
java JwtStructureDemo
```

Stdout chính xác của chương trình:

```text
Parts: 3
Header: {"alg":"HS256","typ":"JWT"}
Payload: {"sub":"alice","scope":"read"}
Valid signature: true
Tampered valid: false
```

Phân tích:

1. `Header` và `Payload` in ra được **không cần secret**, vì JWS không tự mã hóa hai phần đó.
2. MAC hợp lệ chứng minh bytes trong hai phần chưa bị sửa **theo khóa demo**, nhưng không tự chứng minh token chứa identity, issuer, audience hay thời hạn hợp lệ.
3. Khi thay payload thành `sub=admin` mà giữ signature cũ, kiểm tra HMAC trả `false`.
4. Kẻ tấn công **có secret HMAC** có thể tự ký payload mới, vì vậy bảo vệ, rotation và phạm vi phân phối secret cực kỳ quan trọng.
5. Chương trình cố định thuật toán HS256 để minh họa. Trong ứng dụng thật, **không tự viết decoder/validator**, không dựa vào header từ token để tự chọn thuật toán bất kỳ và không dùng dữ liệu demo cho production.

## 6. JWT được ký (JWS) khác JWT được mã hóa (JWE) ra sao?

JWT có thể dùng **JWS** hoặc **JWE**, theo RFC 7519. Dạng JWS compact có **3 phần**; dạng JWE compact có **5 phần**:

```text
JWS (thường thấy trong API):
BASE64URL(protectedHeader)
.
BASE64URL(payload)
.
BASE64URL(signature)

JWE Compact Serialization:
BASE64URL(protectedHeader)
.
BASE64URL(encryptedKey)
.
BASE64URL(initializationVector)
.
BASE64URL(ciphertext)
.
BASE64URL(authenticationTag)
```

Lưu ý `encryptedKey` có thể **rỗng** với một số chế độ key management như direct encryption, nhưng định dạng JWE compact vẫn có đủ **năm vị trí**, cách nhau bằng bốn dấu chấm.

### 6.1. JWS: bảo vệ integrity nhưng payload thông thường lộ rõ

Với JWS payload được Base64url-encode, ai cầm token đều giải mã được JSON. Đừng coi `iat`, `sub`, email, role, tenant ID, business metadata là bí mật chỉ vì chúng nằm trong token.

Ví dụ khi QA thấy:

```json
{"alg":"RS256","typ":"JWT"}
```

và một payload:

```json
{"sub":"alice","scope":"orders.read"}
```

thì việc đọc được `sub=alice` **không có nghĩa** một người có thể đổi `sub=admin` mà vẫn có token hợp lệ: thay payload sẽ làm chữ ký sai nếu server xác minh đúng. **Chống sửa dữ liệu không đồng nghĩa che giấu dữ liệu**.

### 6.2. JWE: mã hóa dữ liệu, vẫn cần validate claims

JWE dùng thuật toán quản lý khóa và mã hóa nội dung, thường kèm authentication tag để phát hiện sửa ciphertext. Recipient hợp lệ giải mã để lấy payload; người ngoài không có khóa tương ứng không dễ đọc được claims. Nhưng sau khi giải mã, backend **vẫn phải kiểm tra** issuer/audience/thời hạn, mục đích token, quyền và các ràng buộc khác. Không chấp nhận token chỉ vì nó “giải mã được”.

Nếu cần vừa **chữ ký của issuer** vừa **bí mật đối với người ngoài**, có thể dùng **nested JWT**, ví dụ ký JWS rồi mã hóa JWS trong JWE theo profile thích hợp. Cần xác minh cả các lớp theo đúng thứ tự và chính sách của ứng dụng, tránh tự triển khai cryptographic protocol.

### 6.3. JWT không mặc nhiên phải ký

Đặc tả cho phép **Unsecured JWT** dạng JWS có `alg=none` và segment chữ ký rỗng. Điều này **không** có nghĩa Resource Server phải chấp nhận chúng; khi làm authentication/authorization, phải thiết kế policy chỉ nhận các thuật toán được cho phép và xác minh signature/MAC hoặc một cơ chế bảo vệ được định nghĩa rõ ràng. Đối với bearer access tokens thông thường, **từ chối `alg=none`**.

Không có quy tắc “hễ ba phần là bảo mật”. Ba segment chỉ cho biết hình thức compact JWS; **khóa và cách kiểm tra quyết định tính đáng tin**.

## 7. JWT không giống access token, và access token cũng không mặc nhiên là JWT

Có ba khái niệm độc lập:

- **JWT:** định dạng các claims.
- **Access token:** credential mà client trình cho resource server khi gọi API; có thể là JWT **hoặc opaque token** không đọc được cấu trúc ở phía client.
- **ID token (OpenID Connect):** một JWT phục vụ client xác minh sự kiện xác thực/identity của user theo OIDC; audience thường là client application. **Không mặc nhiên dùng ID token như access token** để gọi API.

Đặc biệt nguy hiểm là lỗi **cross-JWT confusion**: một ID token được ký hợp lệ cho frontend có thể có `sub` và `iss` nhìn rất thuyết phục, nhưng **`aud` không phải API**. Nếu API chỉ kiểm tra signature mà bỏ kiểm tra audience/token purpose, nó có thể nhận sai loại token.

Mọi JWT dùng cho xác thực ở Resource Server phải được đánh giá theo **profile** cụ thể: có phải access token dành cho API này không, issuer tin cậy không, token type/`typ` nếu profile yêu cầu có phù hợp không, claims/scope nào có ý nghĩa, có ràng buộc với client hoặc proof-of-possession hay không. Đừng đồng nhất “token hợp lệ về mật mã” với “token dùng được ở mọi endpoint”.

## 8. Những gì Resource Server bắt buộc phải xác minh

Các bước logic đối với bearer JWT khi nhận qua HTTP:

```text
Request
  └─ Authorization: Bearer <access-token>
          ↓
       JWT Decoder
          ├─ Cú pháp compact, base64url, JSON hợp lệ
          ├─ Thuật toán được cho phép, không tin alg tùy ý
          ├─ Chọn khóa từ trust store/JWKS cấu hình sẵn
          ├─ Xác minh chữ ký hoặc MAC
          └─ Kiểm tra claims: iss, aud, exp, nbf, ...
          ↓
       Authentication đã xác minh
          ↓
       Chuyển scope/role/permission → GrantedAuthority
          ↓
       HTTP authorization: method/path/authority
          ↓
       Resource authorization: tenant/owner/state
          ↓
       Controller / service
```

Nếu một trong các điều kiện bắt buộc sai, phải từ chối. Không “fallback” sang parse payload unsigned để tiếp tục cho phép. Cũng không cho client tự cung cấp issuer/jwks URL để server quyết định nơi tìm public key.

### 8.1. `iss` — đúng bên phát hành

API chỉ nên chấp nhận issuer đã được cấu hình là nguồn token đáng tin. Kẻ tấn công có thể tự tạo JWT và tự ký bằng khóa của họ; điều đó vẫn **không biến họ thành issuer mà API tin cậy**. `iss` phải được kiểm tra đồng thời với chữ ký/key chain gắn với issuer.

### 8.2. `aud` — token được cấp đúng API

Một issuer có thể cấp token cho nhiều resource server. Token hợp lệ cho service `billing-api` **không tự hợp lệ** với `orders-api`. Nếu resource server bỏ `aud`, token từ một dịch vụ có thể bị đem sang dịch vụ khác (**token substitution/confused deputy**).

`aud` có thể là chuỗi hoặc mảng chuỗi. API phải xác minh audience mong đợi **có mặt** theo quy tắc của issuer và profile; không dùng `sub` hay `client_id` để thay cho audience nếu policy không định nghĩa vậy.

### 8.3. `exp`, `nbf` và `iat`

- `exp`: hết hạn; từ chối token khi current time đã tới/past mốc hết hiệu lực theo chính sách clock skew.
- `nbf`: trước mốc này token chưa được phép dùng.
- `iat`: lúc phát hành; có thể kiểm tra tuổi tối đa, thời điểm phát hành hợp lý, nhưng **chỉ có iat không thay thế exp**.
- Tất cả đều dùng đơn vị **giây** trong JWT NumericDate, không phải UNIX milliseconds như nhiều ứng dụng Java/JavaScript nhầm.
- Phải đồng bộ clock giữa các hệ thống và cấu hình leeway/clock skew **nhỏ, có chủ đích**; không kéo leeway quá rộng để giải quyết lỗi hệ thống.

### 8.4. Authority, scope và business authorization

Spring Security mặc định thường ánh xạ scope token thành authority dạng `SCOPE_<scope>`. Ví dụ token chứa `"scope": "orders.read orders.write"` có thể tạo `SCOPE_orders.read` và `SCOPE_orders.write` theo converter phù hợp.

**Không tự suy ra**:

- Claim `role=ADMIN` tự thành `ROLE_ADMIN`.
- `scope=orders.read` nghĩa là được đọc mọi đơn của mọi tenant.
- Có token hợp lệ nghĩa là đã có điều kiện đủ để sửa bản ghi theo ID.
- Một `aud` đúng nhưng user không có role thì vẫn được admin access.

Quyền trên từng dữ liệu phải dựa trên principal đã được xác minh và kiểm tra `owner/tenant/state` ở service/data layer, không tin `tenant_id` hoặc `userId` đến từ JSON body khi nó mâu thuẫn với identity đã xác thực.

## 9. Những lỗi bảo mật khi xử lý JWT

### 9.1. Chỉ decode, không verify

**Sai:**

```text
token.split(".")
→ Base64url decode payload
→ parse JSON
→ nếu roles chứa ADMIN thì cho phép
```

Client có thể tự sửa claim `roles` nếu backend không xác minh chữ ký. “Đọc JWT” bằng decoder đơn giản chưa phải “xác thực JWT”. Ngay cả khi decoder trả claims nhìn hợp lý, **không sử dụng claims để cấp quyền** trước khi hoàn thành xác minh.

### 9.2. `alg=none` và algorithm confusion

Không để JWT quyết định sẽ bỏ qua xác minh vì header có `"alg":"none"`. Không tự động hoán đổi HS256/RS256 chỉ theo chuỗi `alg` từ token. Một số lỗi triển khai cũ đã có thể dùng nhầm public key RSA như HMAC secret khi engine trộn thuật toán và key type; thư viện an toàn phải ràng buộc thuật toán/kind of key theo cấu hình, không theo đầu vào của attacker.

**Quy tắc:** tại API, khóa và thuật toán hợp lệ phải do **trusted configuration** quyết định. Chỉ hỗ trợ những thuật toán cụ thể do hệ thống thật cần; không tự cho phép “mọi thuật toán JOSE”.

### 9.3. `kid`, `jku` và key-selection attacks

`kid` giúp xoay khóa, nhưng một giá trị `kid` mới không mặc nhiên làm JWT đáng tin. Chỉ tìm key trong **JWKS/trust store** của issuer cấu hình từ trước, qua HTTPS với chính sách trust chain phù hợp. Không lấy `jku` hoặc `x5u` từ token rồi thực hiện HTTP GET đến URL tùy ý (SSRF/trust injection). Không dùng `kid` làm file path/SQL string mà không kiểm soát.

Nếu issuer rotate key, JWKS có thể thay đổi theo thời gian; cache/refresh cần phù hợp, nhưng **không fallback sang khóa không tin cậy** khi không tìm được key.

### 9.4. Thiếu audience, token type và issuer binding

Một token được ký bằng khóa được chấp nhận nhưng dành cho client/API khác vẫn phải bị từ chối theo `aud`/purpose. Lập bảng test riêng cho đúng issuer và sai issuer, đúng audience và sai audience, token hết hạn và token chưa tới thời điểm có hiệu lực. Không trộn identity token với access token chỉ vì JSON claims giống nhau.

### 9.5. Lộ payload hoặc token qua hệ thống phụ trợ

Bearer token là credential: ai lấy được có thể thử dùng nó trong thời hạn hiệu lực. Payload JWS dễ decode. Không đưa token vào query parameter, crash report, ticket hỗ trợ, error response, browser console, access log, analytics, screenshots hoặc công cụ giải mã bên thứ ba bằng token production. Mask/redact `Authorization` ở proxy, observability và mọi client log.

### 9.6. Token còn hạn dù user đã logout/đổi quyền

JWT signed tự chứa có thể được API xác minh cục bộ mà không hỏi issuer mỗi request. Vì vậy token chưa hết `exp` có thể còn hợp lệ dù user vừa bấm logout hoặc role bị thu hồi, **trừ khi** hệ thống có cơ chế revoke/denylist, token version, introspection hoặc chiến lược kiểm soát riêng. Giải pháp tùy threat model: access token ngắn hạn, refresh token rotation, revoke và event-driven cache invalidation, hoặc opaque token với introspection khi cần kiểm soát tức thời. Không coi `jti` hiện diện tự động làm token bị thu hồi được.

## 10. Ví dụ Spring Boot MVC: Resource Server kiểm tra JWT

Dưới đây là cấu hình **có thể dùng trong một ứng dụng Spring Boot Servlet/MVC**. Nó không tự phát hành token: cần có **authorization server/issuer thật**, JWKS hoặc khóa public tin cậy và một JWT access token hợp lệ do issuer phát hành. Các URL `issuer.example.com` là địa chỉ **minh họa, không phải issuer hoạt động để chạy trực tiếp**.

### 10.1. Dependencies Maven

Trong `pom.xml` của ứng dụng Spring Boot 3.x, cần các starter tương ứng:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

Cần có Spring Boot parent/BOM để quản lý phiên bản tương thích và Java 17+. Không tự thêm thư viện parse JWT rồi bỏ qua Resource Server decoder nếu framework đã xử lý việc này.

### 10.2. `application.yml` với issuer và audience

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://issuer.example.com"
          audiences:
            - "orders-api"
```

Trong Spring Boot 3.5, `issuer-uri` để cấu hình tin cậy tới issuer/metadata/JWKS theo thiết lập, còn `audiences` đặt audience mà resource server dự kiến trong `aud`. Với cấu hình chuẩn Spring Security, JWT decoder cũng kiểm tra chữ ký và các thời điểm như `exp`/`nbf`. Nếu ứng dụng sử dụng custom `JwtDecoder` hoặc security configuration khác, cần xác minh lại các validator đã được gắn đầy đủ.

Nếu issuer cung cấp JWKS ở URI tùy chỉnh, có thể cấu hình thêm `jwk-set-uri` theo tài liệu provider **cùng với issuer-uri** để vẫn kiểm tra `iss` và tránh phụ thuộc vào discovery tại startup. Chỉ trỏ JWKS tới endpoint **được cấu hình tin cậy**, không lấy URL từ `jku` trong token.

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://issuer.example.com"
          jwk-set-uri: "https://issuer.example.com/oauth2/jwks"
          audiences:
            - "orders-api"
```

Đoạn này là **lựa chọn cấu hình thay thế**, không có ý yêu cầu khai báo trùng cả hai YAML. Địa chỉ JWKS phải là endpoint thật của issuer, phù hợp TLS, key rotation và chính sách triển khai.

### 10.3. `JwtApiSecurityConfig.java`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class JwtApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
```

Đây là **một lớp cấu hình Spring**, cần nằm trong package của ứng dụng Java 17+/Boot 3.x và có các starter nói trên; không biên dịch độc lập bằng mỗi `javac`. Nó trình bày **bearer JWT authentication** qua `Authorization: Bearer <token>`, không phải HTTP Basic hoặc tự ký token.

Giải thích:

1. Request tới API mang `Authorization: Bearer <access-token>`. Resource Server decoder xác minh signature và claims theo issuer/audience/time đã cấu hình.
2. Sau khi xác minh, Spring Security tạo `Authentication` với authorities được chuyển đổi từ claims, ví dụ `SCOPE_orders.read`. Claim `scope` và định dạng authority phải được kiểm tra với issuer thực.
3. `GET /api/orders/**` đòi `SCOPE_orders.read`; `POST` đòi `SCOPE_orders.write`. Một token ký hợp lệ nhưng thiếu permission vẫn bị **403**.
4. `anyRequest().denyAll()` từ chối method/route chưa liệt kê để giảm nguy cơ endpoint mới tự mở.
5. `SessionCreationPolicy.STATELESS` yêu cầu Spring Security không dùng HTTP session để lưu security context; **không đồng nghĩa** toàn ứng dụng không thể tạo state do thành phần khác.
6. Ví dụ không vô hiệu CSRF. Với API thuần bearer token ở header và không sử dụng cookie/session tự động gửi từ browser, có thể có threat model khác ứng dụng dùng cookie; cân nhắc chính sách CSRF **dựa trên kiến trúc thực tế**, không tắt theo quán tính.
7. Resource server chỉ bảo vệ tầng HTTP. Nếu người có `orders.read` chỉ được xem order thuộc tenant của mình, service/repository phải kiểm tra thêm tenant/owner/state.

### 10.4. Gọi API có JWT đúng

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.example.signature
```

**Chuỗi token ở trên chỉ là hình dạng minh họa, không phải JWT hợp lệ.** Trong thực tế dùng JWT được issuer cấp, qua HTTPS. Khi thiếu token hoặc chữ ký/claims không hợp lệ, API thường trả `401` và có `WWW-Authenticate: Bearer...` theo RFC 6750; khi token hợp lệ nhưng thiếu quyền, thường `403`. Đừng dùng HTTP status thay cho việc kiểm tra log/exception/test fixture vì security policy khác cũng có thể tạo cùng status.

### 10.5. Controller chỉ làm việc với principal đã được xác minh

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class JwtDemoController {

    @GetMapping("/api/orders/whoami")
    public String whoAmI(@AuthenticationPrincipal Jwt jwt) {
        return jwt.getSubject();
    }
}
```

Trong route policy ở ví dụ, `GET /api/orders/whoami` đòi `SCOPE_orders.read`. Spring Security đưa vào `Jwt` sau khi xác minh; controller không cần `Base64url.decode` để quyết định caller là ai. Không log nguyên JWT, và không tự biến `sub` thành quyền truy cập mọi order. Phương thức này cần được gọi trong ứng dụng có OAuth2 Resource Server được cấu hình và issuer thật.

## 11. Spring WebFlux: cùng nguyên tắc, chain reactive khác

Một WebFlux Resource Server dùng `ServerHttpSecurity` và `SecurityWebFilterChain` thay vì `HttpSecurity`/`SecurityFilterChain`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveJwtSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

- Dùng `spring-boot-starter-webflux` + `spring-boot-starter-security` + `spring-boot-starter-oauth2-resource-server`.
- Cùng nhóm property `spring.security.oauth2.resourceserver.jwt.issuer-uri` và `audiences` có thể áp dụng cho Servlet lẫn Reactive trong Spring Boot.
- Xác minh JWT thực thi trong reactive security pipeline. Nếu logic custom phải gọi IO/repository bất đồng bộ, dùng `Mono`/`Flux` và Reactor Context; **không `block()`/`subscribe()` thủ công** để xác minh quyền.
- Đoạn WebFlux là cấu hình của **ứng dụng reactive riêng**, không đặt song song với cấu hình MVC như thể hai builder xử lý cùng một HTTP runtime.
- `@AuthenticationPrincipal Jwt` hoặc cơ chế lấy principal reactive thích hợp giúp đọc subject đã xác minh; vẫn cần business authorization trước khi trả dữ liệu.

## 12. JWT validation và authorization: ma trận test cần có

Thiết kế dữ liệu test với issuer hợp lệ, khóa ký tin cậy, audience API hiện tại và các trường hợp sai. Đừng chỉ kiểm tra “token parse được” hoặc “trang trả 200”.

| Tình huống | Kỳ vọng |
|---|---|
| Không có bearer token đến endpoint protected | **401** / challenge phù hợp |
| Token bị sửa payload nhưng giữ signature | **401** vì chữ ký/MAC sai |
| Token do issuer lạ ký bằng khóa của họ | Bị từ chối vì không thuộc trust chain |
| Header `alg=none` hoặc thuật toán không cho phép | Bị từ chối |
| `kid` không tìm thấy trong JWKS tin cậy | Bị từ chối, không tự fetch key lạ |
| JWT hết `exp` | Bị từ chối |
| JWT chưa tới `nbf` | Bị từ chối |
| `iss` không đúng issuer được cấu hình | Bị từ chối |
| `aud` thiếu `orders-api` | Bị từ chối dù signature hợp lệ |
| Token đúng issuer/audience/thời hạn nhưng chỉ có `orders.read`, gọi POST | **403** do thiếu write scope |
| Token có `orders.read`, GET order của tenant khác | Bị từ chối ở tầng business authorization |
| JWS có payload xem được sau decode | **Điều bình thường**, không phải lỗi cryptography |
| JWE ciphertext không đọc được nếu thiếu key | **Điều dự kiến** của encryption |
| ID token cho frontend được gửi thay access token đến API | Bị từ chối nếu purpose/audience không đúng |

### 12.1. MockMvc test: phân biệt authorization test và cryptographic validation test

`spring-security-test` có request post-processor `jwt()` giúp dựng một `JwtAuthenticationToken` giả lập trong kiểm thử **authorization**. Ví dụ trích đoạn với `MockMvc` đã cấu hình và route phù hợp:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
```

**Cảnh báo quan trọng:** `.with(jwt())` **bỏ qua bước xác minh chữ ký JWT thật** vì nó mô phỏng authentication cho test; nó chỉ phù hợp để kiểm tra mapping quyền/endpoint. Để chứng minh chữ ký sai/issuer sai/audience sai bị chặn, cần integration test đưa **Bearer header thật** qua `BearerTokenAuthenticationFilter` và `JwtDecoder`/public JWKS key tin cậy, dùng JWT ký bằng khóa test phù hợp.

Ngoài ra, `status().isOk()` chỉ đúng nếu controller `/api/orders/42` tồn tại, fixture có data và trả 200. Nếu chưa có route thật, test có thể trả 404 sau khi đã qua security gate. Không lấy 404 làm bằng chứng cryptographic validation thất bại.

### 12.2. Các ca test cần fixture tin cậy

Với integration test thực:

1. Tạo issuer test và bộ khóa test riêng. Không dùng production key trong unit test.
2. Cấp JWT hợp lệ cho đúng `iss`, `aud`, `exp`; kiểm tra API nhận và map scope đúng.
3. Sửa một byte payload/signature; xác nhận JWT bị từ chối.
4. Tạo JWT ký bằng khóa khác, algorithm khác và `kid` không có trong trusted JWKS; xác nhận fail closed.
5. Tạo JWT đã hết hạn, chưa tới `nbf`; test clock skew nhỏ đã định nghĩa.
6. Tạo token audience khác và ID token profile không dùng cho API; xác nhận từ chối.
7. Có token scope đọc nhưng không scope ghi; xác nhận 403 ở HTTP layer.
8. Có token hợp lệ nhưng order thuộc tenant khác; xác nhận không đọc được dữ liệu và không phát sinh side effects.

Các test tương đương trong WebFlux có thể dùng `WebTestClient` và hỗ trợ `mockJwt()` để test HTTP authorization. Cần tách rõ test security mocking khỏi test crypto validation.

## 13. TTL, token rotation và bảo mật phía client

JWT signature không thay thế quản lý vòng đời:

- **Access token ngắn hạn:** giảm cửa sổ tái sử dụng nếu token bị đánh cắp.
- **Refresh token:** dùng kênh và lưu trữ an toàn phù hợp; trong các ứng dụng cần quyền thu hồi, áp dụng refresh rotation, phát hiện reuse và revoke.
- **Issuer key rotation:** JWKS có thể chứa nhiều public keys theo `kid` trong thời gian chuyển đổi; server chỉ tin các keys từ issuer đáng tin. Cần quy trình xoay khóa, thu hồi khóa lỗi và kiểm tra cache.
- **Logout:** xóa token phía client không làm một JWT chưa hết hạn tự mất hiệu lực nếu API xác minh offline. Nếu yêu cầu “logout ngay lập tức”, cân nhắc denylist theo `jti`, introspection/opaque tokens hoặc kiến trúc thu hồi token khác.
- **Scope tối thiểu:** không cấp một access token với mọi quyền chỉ vì tiện cho frontend.
- **Bảo vệ nơi lưu:** bearer token bị lấy cắp thường có thể bị tái sử dụng; đánh giá XSS, cookie `HttpOnly`/`Secure`/`SameSite`, CSRF, token storage và API gateway theo thiết kế thật. Không có cách lưu token phía browser hoàn toàn miễn nhiễm khi trang bị XSS.
- **Không cho URL mang token:** query string dễ xuất hiện trong browser history, referrer và log.
- **Không để claim nhạy cảm trong JWS:** người cầm token có thể decode payload; chỉ gửi claim tối thiểu.
- **TLS:** cần HTTPS khi truyền bearer token, kể cả token có chữ ký; signature không ngăn người nghe lén **sao chép** token và dùng lại.

## 14. Các lỗi tư duy thường gặp

1. “JWT có ba phần, trông khó đọc nên đã mã hóa.” — **Sai**; JWS thường chỉ Base64url-encode header/payload.
2. “Signature hợp lệ thì đúng user và đúng API.” — **Sai**; còn phải check issuer, audience, subject, thời hạn, loại token, quyền và trust key.
3. “Chỉ cần Base64url decode payload để đăng nhập user.” — **Sai**; chưa verify nên attacker sửa claims được.
4. “Thấy `alg=RS256` thì cứ tìm public key trên URL `jku` của token.” — **Sai**; URL và key phải thuộc trust configuration của issuer.
5. “Đưa `alg=none` là cách tắt signature cho demo; có thể để trong production.” — **Không an toàn** cho bearer authentication.
6. “HS256 dùng public key giống RS256.” — **Sai**; HS256 dùng secret đối xứng, RS256 dùng cặp private/public.
7. “JWT ký rồi thì mã hóa thêm là không cần thiết với mọi loại dữ liệu.” — **Sai**; dữ liệu cần bí mật đòi JWE hoặc cơ chế bảo mật phù hợp.
8. “JWE giải mã được là đủ tin.” — **Sai**; phải kiểm tra policy, claims và tính xác thực người phát hành/recipient.
9. “`exp` trong JWT là milliseconds.” — **Sai**; NumericDate thường là giây.
10. “Có `sub` thì không cần `aud`.” — **Sai**; subject và người nhận token khác nhau.
11. “JWT access token và OIDC ID token có thể đổi chỗ.” — **Sai**; khác mục đích/profile/audience.
12. “Có role ADMIN là được đọc toàn bộ tenant.” — **Sai**; phải có chính sách resource/tenant riêng.
13. “`kid` được phép trỏ tới bất kỳ key nào.” — **Sai**; chỉ chọn từ trusted key set đã cấu hình.
14. “Khi logout, tất cả JWT cũ tự bị vô hiệu.” — **Sai**; signed token có thể dùng đến hết hạn nếu thiếu revoke mechanism.
15. “Token ký hợp lệ chống được đánh cắp.” — **Sai**; bearer token bị lấy cắp có thể được tái sử dụng.
16. “`MockMvc.with(jwt())` chứng minh server verify signature thành công.” — **Sai**; helper mock authentication, không chạy JWT decoder thật.
17. “Tắt CSRF là bắt buộc với mọi API dùng JWT.” — **Không phải quy tắc tổng quát**; threat model phụ thuộc browser/cookie tự gửi và cơ chế authentication.
18. “Cứ lấy scopes từ một string tùy ý để làm authorities.” — **Sai**; chỉ tin claims từ JWT đã được xác minh và mapping đã cấu hình.
19. “Có mã hóa JWE nên không cần TLS.” — **Sai**; TLS vẫn quan trọng cho metadata, chống replay, bảo vệ token bearer và toàn bộ transport.
20. “Một thư viện parse JSON token là đủ thay Spring Security Resource Server.” — **Sai**; cần cryptographic verification và security policy đầy đủ.

## 15. Checklist trước khi triển khai JWT Resource Server

- [ ] Xác định token sử dụng JWS hay JWE; không xem Base64url là encryption.
- [ ] Chỉ chấp nhận đúng JWT profile/algorithm từ issuer tin cậy; tuyệt đối không dùng `alg=none` cho bearer authentication.
- [ ] Chọn key từ JWKS/trust store được cấu hình, không tin URL từ token header.
- [ ] Xác minh signature/MAC trước khi sử dụng claims; với JWE, giải mã và xác thực đúng lớp bảo vệ.
- [ ] Kiểm tra `iss`, `aud`, `exp`, `nbf` và các claim bắt buộc theo policy; NumericDate theo giây.
- [ ] Ràng buộc token type/purpose; không dùng OIDC ID token như API access token.
- [ ] Mapping `scope`/`roles`/`permissions` sang `GrantedAuthority` có kiểm thử, không đoán prefix.
- [ ] HTTP authorization được kiểm tra, kèm business authorization cho owner/tenant/state.
- [ ] Không đưa password, secret, PII không cần thiết vào JWS payload.
- [ ] Mọi request mang bearer token đi qua HTTPS; log/traces/access log phải redact Authorization.
- [ ] Token TTL, refresh rotation, key rotation và revoke/logout có chiến lược được mô tả rõ.
- [ ] Test cả token hợp lệ, chữ ký sai, issuer/audience sai, exp/nbf sai, kid/alg lạ và sai quyền.
- [ ] Phân biệt mock JWT authorization test và integration test dùng decoder thật.
- [ ] Với Servlet/WebFlux, cấu hình đúng builder, filter chain và loại decoder.

## 16. Tài liệu chuẩn và tài liệu Spring Security

- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa JWT, claims, JWS/JWE, unsecured JWT và validation.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): protected header, payload, signature và compact serialization.
- [RFC 7516 — JSON Web Encryption](https://www.rfc-editor.org/rfc/rfc7516): ciphertext, key management và JWE compact năm thành phần.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm confusion, token substitution, issuer/audience và key management.
- [Spring Security — Servlet OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): decoder, issuer, audiences, JWKS, authentication và scopes.
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): xác minh JWT trên WebFlux.
- [Spring Boot 3.5 — Spring Security / Resource Server](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html): `issuer-uri`, `jwk-set-uri`, `audiences` và cấu hình ứng dụng.

**Ghi nhớ:** JWT **không mặc nhiên được mã hóa**. Ở JWS compact, header và claims payload chỉ được **Base64url-encode** nên có thể đọc công khai; signature/MAC bảo vệ **tính toàn vẹn và xác thực theo khóa tin cậy**, không che giấu thông tin. Khi muốn bảo mật nội dung phải dùng JWE hoặc thiết kế khác. Trong Spring Security, chỉ sau khi token được xác minh bằng issuer/key/algorithm/claims đúng policy mới tạo authentication, rồi vẫn phải kiểm tra quyền endpoint và quyền trên tài nguyên.