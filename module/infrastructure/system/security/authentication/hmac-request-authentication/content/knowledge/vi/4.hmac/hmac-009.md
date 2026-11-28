# Độ dài tag

## 1. Tag HMAC là gì và vì sao độ dài quan trọng?

Khi một client gọi API bằng cơ chế **HMAC request authentication**, client và server cùng biết một **shared secret**. Client tạo **canonical request** từ những thành phần đã thỏa thuận, như HTTP method, URI, header quan trọng, hash của body, timestamp và nonce. Sau đó client tính HMAC và đính kèm kết quả vào request.

**Tag** (còn gọi là *authentication tag* hoặc giá trị MAC) là dãy byte đầu ra của thuật toán HMAC được dùng để xác minh rằng bên gửi biết shared secret và dữ liệu được ký không bị thay đổi. Với HMAC-SHA-256:

```text
canonicalRequestBytes
        |
        | HMAC-SHA-256(sharedSecret, canonicalRequestBytes)
        v
fullTag = 32 bytes (256 bits)
        |
        +-- Gửi đủ 32 bytes: full-length tag
        |
        +-- Lấy 16 bytes đầu: truncated tag 128 bits
```

HMAC có thể tạo tag với kích thước cố định theo hàm băm bên trong, nhưng một **hợp đồng ký** có thể quy định chỉ truyền một phần đầu của tag (*truncation*). Rút ngắn tag giúp giảm số byte truyền tải hoặc kích thước trường lưu trữ, đồng thời làm giảm số bit mà kẻ tấn công phải đoán để giả mạo một tag.

Bài học thuộc chương **HMAC**, trong mô-đun **`SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`**. Mục tiêu là hiểu chính xác sự khác nhau giữa **độ dài đầu ra HMAC**, **độ dài tag được truyền**, **độ dài chuỗi Base64/hex**, và tác động của chúng đến xác thực HTTP request. Khi thiết kế hệ thống thực tế, ta còn phải giữ canonical request nhất quán, chống replay bằng timestamp/nonce, quản lý key rotation và kiểm tra phân quyền độc lập.

## 2. Phân biệt bit, byte, ký tự mã hóa và độ dài khóa

Một lỗi dễ gặp là nói “tag dài 32” mà không nói rõ đó là **32 byte** hay **32 ký tự**.

- **Bit** là đơn vị độ dài mật mã: 1 byte = 8 bit.
- **Tag bytes** là dãy byte MAC thực tế. Với HMAC-SHA-256 đầy đủ: 32 byte = 256 bit.
- **Chuỗi hexadecimal (hex)** dùng 2 ký tự để biểu diễn 1 byte. Tag 32 byte thành 64 ký tự hex.
- **Base64 chuẩn** mã hóa 3 byte thành 4 ký tự, có thể có dấu đệm `=`. Tag 32 byte thành 44 ký tự Base64.
- **Shared-secret bytes** là độ dài khóa bí mật, là một tham số **khác** với độ dài tag. Khóa 32 byte không có nghĩa buộc phải gửi tag 32 byte, và gửi tag 16 byte không biến secret thành khóa 16 byte.

Ví dụ về định dạng:

```text
Tag hex 16 bytes:
  00112233445566778899aabbccddeeff
  32 ký tự hex = 16 bytes = 128 bits

Tag hex 32 bytes:
  00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff
  64 ký tự hex = 32 bytes = 256 bits
```

Bảng kích thước khi sử dụng **HMAC-SHA-256**:

| Cách truyền tag | Số byte | Số bit | Số ký tự hex | Số ký tự Base64 chuẩn |
| --- | ---: | ---: | ---: | ---: |
| Tag đầy đủ | 32 | 256 | 64 | 44, kết thúc bằng `=` |
| Truncate còn 24 byte | 24 | 192 | 48 | 32, không cần padding |
| Truncate còn 16 byte | 16 | 128 | 32 | 24, kết thúc bằng `==` |
| Truncate còn 8 byte | 8 | 64 | 16 | 12, kết thúc bằng `=` |

**Base64URL không padding** lại có độ dài khác: tag 32 byte thành 43 ký tự, tag 16 byte thành 22 ký tự. Không được suy ra số bit bảo mật từ số ký tự biểu diễn khi chưa biết encoding. Dấu `=` của Base64 là ký tự đệm, **không phải một byte của HMAC**.

## 3. Kích thước tag phụ thuộc vào thuật toán nào?

Mỗi thuật toán HMAC cho đầu ra có độ dài tương ứng với hàm băm của nó:

| Thuật toán | Tag đầy đủ | Ví dụ độ dài hex |
| --- | --- | ---: |
| HMAC-SHA-256 | 32 byte / 256 bit | 64 ký tự |
| HMAC-SHA-384 | 48 byte / 384 bit | 96 ký tự |
| HMAC-SHA-512 | 64 byte / 512 bit | 128 ký tự |

Tên `HmacSHA256` trong Java xác định thuật toán tính **MAC đầy đủ**, nhưng không tự quy định giao thức có truyền đủ 32 byte hay rút ngắn còn 16 byte. Nếu ứng dụng chọn truyền 16 byte, **hai phía phải ghi rõ quy tắc ấy trong hợp đồng**.

Không thể tự động kết luận “SHA-512 luôn an toàn hơn SHA-256” chỉ từ độ dài tag. Mức bảo mật thực tế còn phụ thuộc vào entropy của secret, việc triển khai, thuật toán đã được chọn, cấu trúc thông điệp được ký, giới hạn số lần thử và mô hình đe dọa.

### 3.1. Full-length tag

Với HMAC-SHA-256, tag đầy đủ gồm 32 byte:

```text
HMAC-SHA256(secret, message) → 32 bytes
SendTag = fullTag[0..31]    → 32 bytes
```

Đây là lựa chọn mặc định đơn giản khi giao thức không yêu cầu tối ưu kích thước: ít tham số, dễ trao đổi test vector và dễ tránh nhầm lẫn giữa byte và ký tự.

### 3.2. Truncated tag

Một hợp đồng có thể quy định lấy **16 byte đầu** của kết quả HMAC-SHA-256:

```text
fullTag = HMAC-SHA256(secret, canonicalRequestBytes)  // 32 bytes
sendTag = first 16 bytes of fullTag                    // 16 bytes
header = Base64(sendTag)                               // 24 characters
```

**Thứ tự đúng:** tính HMAC đầy đủ → cắt **byte tag** theo số byte cố định → mã hóa thành Base64 hoặc hex. Không được cắt 16 ký tự của chuỗi Base64 hay 16 ký tự hex rồi cho rằng đó là “tag 16 byte”: 16 ký tự hex chỉ biểu diễn 8 byte, còn cắt Base64 còn có thể phá vỡ encoding.

Nếu giao thức chọn cắt một phần khác (ví dụ 20 byte đầu), đó là **một hợp đồng khác**, phải công bố rõ. Không nên cho bên gửi tùy ý chọn độ dài tag cho từng request.

## 4. Độ dài tag ảnh hưởng thế nào đến khả năng giả mạo?

Giả sử đối thủ **không biết secret**, HMAC được dùng đúng cách và một tag `t` bit có tính chất gần như ngẫu nhiên đối với đối thủ. Nếu họ thử đoán một tag mới cho một thông điệp chưa được cấp chữ ký hợp lệ, xác suất thành công của **một lần đoán độc lập** xấp xỉ:

```text
P(one forgery guess succeeds) ≈ 1 / 2^t
P(success within q guesses)  ≲ q / 2^t
```

Dấu `≲` là **cận gần đúng trong mô hình giả định** khi `q` nhỏ hơn nhiều so với `2^t`. Đây không phải một bảo đảm tuyệt đối cho mọi cấu hình HMAC: secret yếu, secret bị lộ, thiết kế canonical request thiếu trường, lỗi xác minh hoặc cách phát lại request có chữ ký hợp lệ đều có thể làm hệ thống bị tấn công mà không cần đoán tag.

| Tag | Xác suất đoán trúng trong một lần thử (xấp xỉ) | Đánh giá thực tiễn |
| --- | --- | --- |
| 64 bit | `2^-64` ≈ 5,4 × 10⁻²⁰ | Biên độ nhỏ hơn khi lượng thử lớn; không phù hợp làm mặc định cho API nhạy cảm |
| 96 bit | `2^-96` ≈ 1,3 × 10⁻²⁹ | Lớn hơn nhiều so với 64 bit nhưng cần chính sách rõ |
| 128 bit | `2^-128` ≈ 2,9 × 10⁻³⁹ | Mức bảo vệ mạnh cho nhiều thiết kế xác thực ứng dụng nếu các giả định còn đúng |
| 256 bit | `2^-256` ≈ 8,6 × 10⁻⁷⁸ | Tag HMAC-SHA-256 đầy đủ, tránh mất bit do truncation |

Ví dụ minh họa: nếu kẻ tấn công được thử đến **một tỷ (`10^9`) chữ ký tự đoán**, cận gần đúng với tag 64 bit là khoảng `5,4 × 10^-11`, còn với tag 128 bit là khoảng `2,9 × 10^-30`. Các con số này chỉ minh họa **đoán MAC trực tiếp**; không đại diện cho toàn bộ xác suất hệ thống bị xâm nhập.

### 4.1. Phân biệt giả mạo tag với tìm collision

Hai thông điệp bất kỳ có thể va chạm về giá trị tag; với đầu ra `t` bit ngẫu nhiên, các bài toán **tìm một cặp va chạm** thường có ước lượng kiểu birthday khoảng `2^(t/2)` phép thử. Nhưng mục tiêu của đối thủ với HTTP request authentication là tạo ra một **request tùy chọn được server chấp nhận** mà không có secret. Không được dùng trực tiếp công thức birthday để kết luận rằng tag HMAC 128 bit chỉ còn 64 bit bảo mật trước kiểu giả mạo online thông thường.

Dù tag dài đến đâu, một bản sao request đã có **HMAC hợp lệ** vẫn có thể bị gửi lại. Chống phát lại là việc của timestamp đã ký, nonce đã ký và bộ nhớ chống replay bên server; **không được dùng tag dài hơn để thay thế nonce**.

## 5. Nên chọn độ dài tag nào cho HTTP request authentication?

Một chính sách dễ triển khai với HMAC-SHA-256:

1. **Ưu tiên 32 byte đầy đủ** nếu không có ràng buộc truyền tải cụ thể. Đây là cấu hình dễ hiểu và hạn chế tham số cần thương lượng.
2. **16 byte / 128 bit** là một lựa chọn truncation có biên độ mạnh cho nhiều bài toán khi tiết kiệm kích thước tag thực sự có lợi và mô hình đe dọa cho phép.
3. Không chọn tag quá ngắn chỉ để giảm vài byte. Đặc biệt tránh dùng **8 byte / 64 bit** làm mặc định cho API giao dịch nhạy cảm hoặc hệ thống có nhiều cơ hội thử chữ ký.
4. Công bố **một độ dài bắt buộc cho mỗi phiên bản hợp đồng**, cùng thuật toán và encoding. Không tự ý chấp nhận mọi tag từ 8 đến 32 byte.
5. Kết hợp rate limiting, phát hiện hành vi bất thường, bảo vệ secret, timestamp/nonce, idempotency và kiểm soát quyền; tag length chỉ là một lớp bảo vệ.

**Ví dụ chính sách phiên bản:**

```text
Signing contract: HMAC-SHA256-V1
MAC algorithm:    HMAC-SHA-256
MAC output:       32 bytes
Sent tag:         first 16 bytes of MAC output
Header encoding:  standard Base64 with padding
Expected length:  exactly 16 decoded bytes (24 Base64 characters)
```

Một phiên bản khác có thể chọn tag đầy đủ 32 byte. Khi đó cần triển khai thành **phiên bản giao thức rõ ràng** thay vì “để server tự đoán” qua độ dài chữ ký client gửi.

## 6. Định nghĩa độ dài tag trong hợp đồng canonical request

HMAC xác thực **chính xác dữ liệu được ký**. Ví dụ, một request thanh toán:

```http
POST /v1/payments?merchantId=m-42 HTTP/1.1
Host: payments.example.test
Content-Type: application/json
X-Client-Id: client-42
X-Key-Id: key-2026-11
X-Timestamp: 1795856400
X-Nonce: x9vgWv4UOMjVz2UZAxNZhw
X-Signature: <base64-cua-16-byte-tag>

{"orderId":"O-42","amount":250000,"currency":"VND"}
```

Hợp đồng ký minh họa sử dụng các dòng sau, nối bằng LF (không có LF cuối), sau đó mã hóa UTF-8:

```text
HMAC-SHA256-V1
POST
/v1/payments
merchantId=m-42
content-type:application/json
x-client-id:client-42
x-key-id:key-2026-11
x-timestamp:1795856400
x-nonce:x9vgWv4UOMjVz2UZAxNZhw
<lowercase-hex-sha256-of-raw-body-bytes>
```

Các chuỗi trong dấu `<...>` là chỗ giữ chỗ; timestamp là ví dụ tĩnh. Giá trị chữ ký không được tự chèn vào canonical request vì sẽ tạo phụ thuộc vòng (*circular dependency*). Server phải **tự tính body hash từ byte nhận được**; không thể tin một header body hash chỉ vì bên ngoài cung cấp.

Trong hợp đồng trên, client và server phải quy định thêm cách lấy **public path/query**, quy tắc percent-encoding, xử lý query trùng và cách xử lý header. Nếu gateway thay đổi path, query hoặc body giữa lúc ký và xác minh, kết quả HMAC sai dù tag dài đúng 16 byte. Việc chẩn đoán chữ ký sai phải kiểm tra cả **canonical bytes** lẫn **tag policy**.

### 6.1. Thông tin tag length nên nằm ở đâu?

Độ dài tag lý tưởng được cố định **trong cấu hình server theo phiên bản giao thức**, có liên hệ rõ ràng với client hoặc `keyId` và chính sách hiệu lực. Không nên để header tùy ý kiểu `X-Mac-Length: 8` do client cung cấp được dùng để hạ mức kiểm tra mà không có chính sách chặn.

Nếu hỗ trợ nhiều phiên bản trong giai đoạn migration, server cần whitelist phiên bản đang hiệu lực cho client; phiên bản và thông tin ảnh hưởng đến lựa chọn khóa/thuật toán cần được **ràng buộc vào thông điệp được ký** hoặc vào ngữ cảnh xác thực bất biến của server. Không thử nghiệm lần lượt các độ dài để tìm một giá trị “có vẻ khớp”.

## 7. Triển khai Java: tạo tag cố định 16 byte

Ví dụ sau dùng Java 17+, `javax.crypto.Mac` để tính HMAC-SHA-256. Đoạn mã **chỉ đảm nhận MAC/tag**, nên hàm gọi có trách nhiệm tạo đúng canonical request, bảo vệ secret, kiểm tra timestamp/nonce, chọn `keyId` và phân quyền.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Base64;
import java.util.Objects;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacTag128 {
    private static final int TAG_BYTES = 16; // 128-bit tag
    private static final int B64_CHARS = 24; // 16 bytes -> 24 chars, with "=="

    private HmacTag128() {}

    private static byte[] fullMac(byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {
        Objects.requireNonNull(secret, "secret");
        Objects.requireNonNull(canonicalBytes, "canonicalBytes");

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonicalBytes); // exactly 32 bytes
    }

    public static String sign(byte[] secret, String canonicalRequest)
            throws GeneralSecurityException {
        byte[] canonicalBytes =
                canonicalRequest.getBytes(StandardCharsets.UTF_8);
        byte[] fullTag = fullMac(secret, canonicalBytes);
        byte[] sentTag = Arrays.copyOf(fullTag, TAG_BYTES);
        return Base64.getEncoder().encodeToString(sentTag);
    }

    public static boolean verify(byte[] secret,
                                 String canonicalRequest,
                                 String suppliedSignature)
            throws GeneralSecurityException {
        // Reject other tag sizes before comparing any MAC bytes.
        if (suppliedSignature == null
                || suppliedSignature.length() != B64_CHARS) {
            return false;
        }

        final byte[] suppliedTag;
        try {
            suppliedTag = Base64.getDecoder().decode(suppliedSignature);
        } catch (IllegalArgumentException invalidBase64) {
            return false;
        }

        if (suppliedTag.length != TAG_BYTES) {
            return false;
        }

        // Reject alternative text representations of the same bytes.
        // This checks public encoding syntax, not a secret MAC value.
        if (!Base64.getEncoder().encodeToString(suppliedTag)
                .equals(suppliedSignature)) {
            return false;
        }

        byte[] canonicalBytes =
                canonicalRequest.getBytes(StandardCharsets.UTF_8);
        byte[] fullTag = fullMac(secret, canonicalBytes);
        byte[] expectedTag = Arrays.copyOf(fullTag, TAG_BYTES);

        // Compare MAC bytes without exposing where the values differ.
        return MessageDigest.isEqual(expectedTag, suppliedTag);
    }
}
```

Sử dụng:

```java
// secretBytes: khóa bí mật đủ entropy lấy từ secret manager;
// canonical: biểu diễn request được tạo theo hợp đồng ký.
String transmitted = HmacTag128.sign(secretBytes, canonical);
boolean valid = HmacTag128.verify(secretBytes, canonical, transmitted);
```

Đoạn gọi minh họa dùng các biến do ứng dụng cung cấp. **Không đưa secret production vào ví dụ, mã nguồn hoặc log.** Trong ứng dụng thực tế, nên dùng secret ngẫu nhiên có entropy cao và quản lý vòng đời key theo `clientId`/`keyId`.

Các điểm đáng chú ý:

- `Mac.doFinal()` luôn tạo 32 byte với `HmacSHA256`. Việc rút xuống 16 byte là **quyết định của giao thức**, thực hiện sau khi tính MAC.
- Hàm `verify` kiểm tra chính xác **24 ký tự Base64 chuẩn** và **16 byte sau giải mã**, ngăn đầu vào thay đổi độ dài xác thực.
- `MessageDigest.isEqual` được dùng để so sánh MAC theo byte. Việc từ chối sớm các độ dài và encoding **công khai** là hợp lệ; không nên dùng `String.equals` để so sánh trực tiếp các MAC bí mật dạng chuỗi.
- `String.getBytes(UTF_8)` chỉ có thể tương thích nếu hai phía thực sự có cùng canonical string. Với canonical request được xác định ở mức byte, có thể chuyển thẳng `byte[]` vào hàm ký để tránh re-encode sai.
- Khi dùng tag đầy đủ 32 byte, cần **cập nhật đồng bộ** `TAG_BYTES`, số ký tự Base64 mong đợi (44) và phiên bản giao thức; không để một verifier tự động chấp nhận đồng thời mọi độ dài.

### 7.1. Sai lầm bảo mật: tin độ dài do phía gửi quyết định

Không viết verifier theo kiểu sau:

```java
// SAI: độ dài kiểm tra bị điều khiển bởi input không tin cậy.
byte[] received = Base64.getDecoder().decode(headerSignature);
byte[] fullExpected = computeFullHmac(secret, canonicalBytes);
byte[] expected = Arrays.copyOf(fullExpected, received.length);
return MessageDigest.isEqual(expected, received);
```

Đây là **mã minh họa lỗi**, không phải hàm chạy độc lập. Nếu attacker gửi mảng rỗng, cả hai mảng so sánh đều có độ dài 0 và hàm có thể trả `true`. Ngay cả khi đầu vào rỗng bị chặn riêng, một tag chỉ 1 byte sẽ làm mức độ khó giả mạo giảm xuống còn khoảng 1/256 mỗi lần đoán.

**Cách đúng:** server quyết định `TAG_BYTES` bằng cấu hình tin cậy; từ chối mọi độ dài khác trước khi so sánh. Chỉ lấy **đúng số byte cố định** từ MAC đầy đủ.

### 7.2. Sai lầm định dạng: cắt chuỗi Base64

```java
// SAI: cắt chuỗi Base64 không tương đương cắt 16 MAC bytes.
String fullBase64 = Base64.getEncoder().encodeToString(fullMacBytes);
String badTag = fullBase64.substring(0, 16);
```

Bộ giải mã của server có thể nhận ra một chuỗi byte khác hoặc từ chối vì định dạng không hợp lệ; quan trọng hơn, số byte được xác minh không phải **16 byte** như hợp đồng mong muốn. Phải cắt `byte[]` trước khi mã hóa.

## 8. Test vector và bộ kiểm thử tag length

Một **test vector** giúp phát hiện lỗi thuật toán, truncation, encoding hoặc thứ tự xử lý byte. Ví dụ thử nghiệm HMAC-SHA-256 phổ biến (chỉ dùng khóa giả để học):

```text
Key (hex):  0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b
Data (UTF-8): "Hi There"

HMAC-SHA256 full (hex):
b0344c61d8db38535ca8afceaf0bf12b
881dc200c9833da726e9376c2e32cff7

First 16 bytes (hex):
b0344c61d8db38535ca8afceaf0bf12b
```

Đây là **vector thử nghiệm kỹ thuật**, không phải khóa đủ mạnh để dùng trong sản phẩm. Ghép hai dòng full hex thành một chuỗi 64 ký tự; giá trị rút ngắn chỉ lấy **16 byte đầu**, tức 32 ký tự hex đầu. Mã Java `HmacTag128` có thể dùng dữ liệu ấy để so sánh kết quả sau khi giải mã Base64 về byte.

| Ca kiểm thử | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| HMAC hợp lệ, tag 16 byte | Cùng secret, canonical bytes, Base64 padding chuẩn | Xác minh thành công |
| HMAC sai 1 bit | Đổi một bit trong chữ ký đã giải mã | Từ chối |
| Signature rỗng | Header vắng hoặc chuỗi rỗng | Từ chối |
| Tag 8 hoặc 15 byte | Gửi Base64 của tag ngắn hơn | Từ chối vì sai độ dài |
| Tag 17 hoặc 32 byte | Gửi Base64 của tag dài hơn | Từ chối nếu hợp đồng yêu cầu 16 byte |
| Base64 sai cú pháp | Chứa ký tự không thuộc encoding quy định | Từ chối |
| Base64URL không padding | Gửi 22 ký tự trong khi hợp đồng yêu cầu Base64 chuẩn | Từ chối |
| MAC tính trên body khác | Thay một byte payload sau khi ký | Từ chối |
| Method/URI/header đổi | Giữ tag cũ nhưng đổi dữ liệu nằm trong hợp đồng ký | Từ chối |
| Timestamp hết cửa sổ | HMAC vẫn đúng nhưng request quá cũ | Từ chối theo chính sách thời gian |
| Nonce bị dùng lại | Gửi lại đúng request có tag hợp lệ | Chặn replay |
| Version/key khác | Dùng key/version không còn được chấp nhận | Từ chối |
| Qua gateway | Gateway rewrite URI hoặc thay byte body đã ký | Phát hiện sai canonical request hoặc xác minh tại ranh giới được thống nhất |
| Client đã xác thực nhưng thiếu quyền | Tag/nonce hợp lệ, merchant không thuộc client | Tầng phân quyền từ chối |

Nên chạy **positive và negative test** trên cả sender/verifier, thêm kiểm tra qua môi trường proxy/gateway thực tế. Không chỉ cho hàm ký tự kiểm chứng chính kết quả của nó: hai bên có thể cùng mắc một lỗi canonicalization mà vẫn cho kết quả “đúng”. Kiểm thử độc lập bằng vector chuẩn sẽ phát hiện sai khác nhanh hơn.

## 9. Độ dài tag và chống replay là hai vấn đề khác nhau

Giả sử client ký một request thanh toán với tag đầy đủ **256 bit**. Nếu attacker thu thập được **chính request hợp lệ**, họ không cần đoán 256 bit nào cả: họ có thể gửi lại chữ ký đã được tạo.

Một thiết kế an toàn cần:

1. Đưa timestamp, nonce, method, public URI và các trường ảnh hưởng nghiệp vụ vào **canonical request** theo hợp đồng ký.
2. Server kiểm tra timestamp trong cửa sổ cho phép.
3. Server xác minh **đúng tag length** và giá trị HMAC.
4. **Chỉ sau khi HMAC hợp lệ**, server ghi nonce theo thao tác nguyên tử (*insert-if-absent*) trong kho dùng chung, giữ đến khi request không còn có thể được chấp nhận theo timestamp.
5. Server kiểm tra **phân quyền** theo client, scope, merchant/tài nguyên.
6. Hệ thống có **idempotency key** nghiệp vụ nếu lệnh có tác dụng phụ và cần retry an toàn.

Trình tự này làm rõ vai trò: **tag length** chống đoán giả mạo, **timestamp/nonce** chống phát lại, **authorization** chặn hành động vượt quyền và **idempotency** ngăn tạo hiệu ứng nghiệp vụ lặp lại từ các request mới hợp lệ.

## 10. Độ dài tag khi xoay khóa và nâng phiên bản giao thức

**Key rotation** thay đổi secret được dùng để tạo MAC, nhưng không nhất thiết thay đổi độ dài tag. Khi sender chuyển từ `key-A` sang `key-B` và cả hai khóa dùng cùng `HMAC-SHA256-V1`, tag vẫn dài 16 byte nếu đó là độ dài mà phiên bản hợp đồng yêu cầu.

Trường hợp cần tăng từ **16 byte lên 32 byte**:

- Phát hành phiên bản hợp đồng mới có thuật toán, canonicalization, encoding và tag length được quy định rõ, ví dụ `HMAC-SHA256-V2`.
- Chỉ cho phép các client cụ thể dùng phiên bản đang có hiệu lực; không hạ độ dài khi nhận chữ ký sai hoặc do header không đáng tin cậy đề nghị.
- Sender chọn **key ID và phiên bản hợp đồng phù hợp** rồi tạo đúng tag size; verifier xác định phiên bản được phép dựa trên cấu hình và dữ liệu được ràng buộc.
- Trong giai đoạn chuyển đổi, theo dõi tỷ lệ lỗi do sai phiên bản/key mà không ghi secret hoặc chữ ký nguyên vẹn trong log.
- Khi thu hồi phiên bản cũ, server **thực sự từ chối** tag dùng định dạng cũ; không để fallback vô hạn.

Nếu secret bị lộ, kẻ tấn công có thể tính MAC đúng với bất kỳ độ dài tag nào mà giao thức cho phép. **Tăng từ 16 lên 32 byte không chữa được việc lộ secret**: cần thu hồi key, cấp khóa mới và rà soát quyền truy cập.

## 11. Khác biệt giữa tag length, URL/header và gateway

Tag thường được đặt trong header như `X-Signature`, có khi nằm trong query string của webhook callback hoặc một trường ở body. Việc rút ngắn 32 byte xuống 16 byte chỉ giúp tiết kiệm khoảng **16 byte tag thô**, tương ứng với Base64 chuẩn giảm từ 44 xuống 24 ký tự.

Sự khác biệt này đôi khi có giá trị với giao thức giới hạn kích thước nghiêm ngặt hoặc hàng tỷ request, nhưng với API HTTP thông thường, chi phí tối ưu vài chục ký tự thường nhỏ hơn rủi ro triển khai sai hoặc buộc phải hỗ trợ nhiều phiên bản song song.

Các điểm cần kiểm tra với proxy/gateway:

- Proxy có giữ nguyên **giá trị chữ ký** hay không? Header có bị trùng, ghép giá trị hoặc cắt ngắn khi đi qua không?
- Bộ xử lý có tự chuyển Base64 chuẩn sang Base64URL, bỏ padding hoặc thay ký tự `+`/`/` không?
- Client ký public path nhưng verifier dựng lại internal path có làm sai canonical request không?
- Body có bị thay đổi encoding, giải nén hay serialize lại trước điểm xác minh không?
- Server có cho phép client chủ động thay tag length, algorithm hoặc version qua header không được ràng buộc không?

**Độ dài đúng chưa đủ để chữ ký đúng.** Khi điều tra lỗi, cần tách riêng lỗi định dạng tag, lỗi sai secret/keyId, lỗi canonical request và lỗi timestamp/nonce.

## 12. Bài tập thực hành

Thiết kế tích hợp Java client → API gateway → backend payment. Hợp đồng yêu cầu HMAC-SHA-256, tag truyền trong `X-Signature` bằng Base64 chuẩn, độ dài cố định **16 byte**.

**Bài tập A — Phân tích độ dài:** Hãy xác định số bit của tag, số ký tự hex và số ký tự Base64; nếu client gửi 64 ký tự hex, có đúng hợp đồng tag 16 byte không?

**Bài tập B — Xác minh an toàn:** Verifier giải mã Base64 thành `byte[]`. Có nên lấy `expectedMac[0..supplied.length-1]` để so sánh không? Điều gì xảy ra nếu phía gửi đưa tag rỗng hoặc chỉ 1 byte?

**Bài tập C — Replay:** Một request với tag 256 bit hợp lệ bị ghi lại ở log nội bộ, sau đó bị gửi thêm lần nữa trước khi timestamp hết hạn. Tag 256 bit có ngăn được không? Server cần bổ sung trạng thái gì?

**Bài tập D — Nâng cấp:** Client A đã chuyển sang V2 tag 32 byte, client B vẫn trong giai đoạn V1 tag 16 byte. Server nên dựa vào cơ chế nào để chọn phiên bản chấp nhận? Có nên tự thử tag ngắn hơn nếu xác minh V2 thất bại?

**Bài tập E — HTTP gateway:** Client ký `POST /api/payments`; gateway rewrite sang `POST /internal/payments`. Nếu chữ ký sai, nên kiểm tra những lớp thông tin nào trước khi kết luận rằng tag 16 byte quá ngắn?

### Gợi ý đáp án

- **A:** 16 byte = 128 bit, 32 ký tự hex và 24 ký tự Base64 chuẩn có padding. Chuỗi 64 ký tự hex là 32 byte, khác hợp đồng.
- **B:** Không. Server phải cố định 16 byte, không để đối thủ chọn độ dài. Kiểm tra độ dài rỗng/1 byte là bắt buộc.
- **C:** Không. Replay dùng lại tag hợp lệ, không cần đoán. Cần timestamp và nonce đã ký, lưu nonce nguyên tử với TTL phù hợp.
- **D:** Theo cấu hình tin cậy và phiên bản giao thức được chấp nhận cho client/key; tuyệt đối không tự động fallback khi xác minh thất bại.
- **E:** So sánh canonical URI trước/sau gateway, các header đã ký, byte body, key ID, phiên bản thuật toán và encoding chữ ký. Tag length chỉ là một trong nhiều khả năng.

## 13. Những nguyên tắc cần nhớ

**Độ dài tag là một phần của giao thức xác thực, không phải tham số bên ngoài được tự do điều chỉnh.** Với HMAC-SHA-256, tag đầy đủ dài 32 byte; nếu lựa chọn rút ngắn còn 16 byte, phải cắt **16 byte đầu của MAC thô** rồi mới mã hóa. Sender và verifier phải biết chính xác thuật toán, số byte và encoding, và server phải từ chối mọi độ dài không hợp lệ.

Dùng tag mạnh không thay thế quản lý shared secret, canonical request nhất quán, timestamp/nonce chống replay, key rotation, kiểm thử gateway hay kiểm tra phân quyền. Một thiết kế tốt phải giữ đúng tất cả các lớp đó: **chữ ký đúng, tag đủ dài, request còn mới, client có quyền và nghiệp vụ không bị thực thi trùng**.

