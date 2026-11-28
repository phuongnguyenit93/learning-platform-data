# Hash function trong HMAC request authentication

Một **hash function** (hàm băm) nhận dữ liệu có độ dài bất kỳ và trả về một giá trị có độ dài xác định, thường gọi là **digest**. Trong xác thực HTTP request bằng HMAC, hàm băm mật mã có hai vai trò liên quan nhưng **khác nhau**: tạo dấu vân tay cho body và làm thành phần bên trong thuật toán **HMAC** dùng shared secret để xác thực canonical request.

Bài học thuộc chương **HMAC** của module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Mục tiêu không dừng ở việc gọi hàm SHA-256 trong Java mà còn là hiểu chính xác **đang băm những byte nào**, vì sao body digest chưa phải chữ ký, cách ký method/URI/header/body theo hợp đồng, cũng như hệ quả của timestamp, nonce, key rotation và proxy/gateway đối với quá trình xác minh.

## 1. Mô hình cơ bản của một hàm băm mật mã

Ký hiệu hàm băm là H:

~~~text
H: byte[] có độ dài bất kỳ -> digest cố định độ dài

messageBytes = UTF8("abc")
SHA256(messageBytes)
  = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

SHA-256 nhận chuỗi byte và tạo digest **256 bit = 32 byte**, thường trình bày thành **64 ký tự hexadecimal** hoặc **44 ký tự Base64** có padding. Chuỗi hex/Base64 chỉ là **cách biểu diễn** cùng một digest; không phải đầu ra mới của thuật toán. SHA-256 xử lý dữ liệu theo khối 512 bit (64 byte), nhưng độ dài **khối xử lý** khác độ dài **digest** 256 bit.

Những thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa thực tế |
| --- | --- |
| Xác định (deterministic) | Cùng đúng byte đầu vào và cùng thuật toán thì luôn cho cùng digest. |
| Đầu ra cố định | Dữ liệu có thể dài hàng byte hoặc hàng gigabyte; SHA-256 vẫn trả 32 byte. |
| Dễ tính xuôi | Có thể băm dữ liệu lớn hiệu quả theo từng khối; không cần giữ tất cả dữ liệu trong RAM chỉ để tính SHA-256. |
| Kháng tìm tiền ảnh (preimage resistance) | Với một digest cho trước, việc tìm một thông điệp có digest đó phải rất khó đối với thiết kế băm mật mã tốt. |
| Kháng tiền ảnh thứ hai (second-preimage resistance) | Với một thông điệp đã biết, khó tìm một thông điệp khác có cùng digest. |
| Kháng va chạm (collision resistance) | Khó tìm **bất kỳ hai** thông điệp khác nhau có cùng digest. |
| Hiệu ứng khuếch tán (avalanche effect) | Thay một chút đầu vào thường làm nhiều bit digest thay đổi; không dự đoán digest mới chỉ bằng việc nhìn digest cũ. |

Vì số thông điệp có thể có là vô hạn còn digest chỉ có 2^256 giá trị, **va chạm chắc chắn tồn tại về mặt toán học**; an toàn là ở việc tìm được va chạm đủ khó. Với mô hình tấn công tổng quát lý tưởng, độ phức tạp va chạm của hash 256 bit cỡ 2^128 phép thử (hiệu ứng birthday), còn tìm tiền ảnh cỡ 2^256; đây là trực giác về mức an toàn, không phải cam kết tuyệt đối cho mọi thuật toán hay mọi mô hình đối thủ.

Hàm băm **không mã hóa**, nên không có thao tác “giải mã hash”. Nó cũng không tự xác thực danh tính: người nào có body đều có thể tính SHA-256 của body đó. Vì vậy **digest không có khóa** là dữ liệu kiểm tra tính nhất quán, chưa phải bằng chứng request đến từ client hợp lệ.

### Ví dụ byte và digest

~~~text
UTF-8 bytes của "abc":
61 62 63

SHA-256("abc"):
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad

SHA-256(body rỗng, 0 byte):
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Hai giá trị trên là **test vector** có thể tính lại bằng Java, không phải secret. Digest của body rỗng là digest của **mảng 0 byte**, không phải chuỗi rỗng thay thế cho trường digest trong canonical request.

## 2. Phân biệt hash, checksum, mã hóa và MAC

| Công cụ | Cần khóa bí mật? | Đích sử dụng | Có xác thực người gửi? |
| --- | --- | --- | --- |
| CRC32, checksum thông thường | Không | Phát hiện lỗi truyền dẫn ngẫu nhiên | Không. Đối thủ có thể tính lại checksum sau khi sửa dữ liệu. |
| SHA-256 không khóa | Không | Tạo digest, kiểm tra nội dung so với giá trị tin cậy có sẵn | Không. Bất kỳ ai cũng tính được digest mới. |
| AES-GCM với khóa bí mật | Có | Mã hóa và xác thực dữ liệu theo chế độ AEAD | Có tính toàn vẹn/xác thực đối với bên giữ khóa, đồng thời bảo mật plaintext. |
| HMAC-SHA256 với shared secret | Có | Xác thực tính toàn vẹn và bên có khả năng sử dụng secret | Có, trong phạm vi quản lý key; **không** mã hóa nội dung. |
| Chữ ký số như Ed25519 | Khóa riêng để ký, khóa công khai để kiểm tra | Xác thực chữ ký bất đối xứng | Có theo mô hình khóa công khai, khác HMAC shared secret. |

Không dùng MD5 hay SHA-1 làm **hàm băm mới** cho các cơ chế cần collision resistance; chúng đã có các tấn công va chạm thực tế. Với HMAC trong hệ thống mới, **HMAC-SHA256** là lựa chọn thông dụng và được thư viện Java hỗ trợ. Mật khẩu người dùng cần thuật toán băm mật khẩu chuyên dụng như Argon2id, scrypt hoặc PBKDF2 với tham số phù hợp, **không** dùng SHA-256 thuần vì SHA-256 được thiết kế chạy nhanh.

Một sai lầm khác là tự tạo MAC bằng SHA256(secret || message), hoặc SHA256(message || secret). Các kết cấu tự chế có thể gặp lỗi phân tách trường, tấn công mở rộng độ dài (length extension đối với một số cấu trúc, đặc biệt dạng secret || message với SHA-256), hoặc thiếu những phân tích bảo mật mà HMAC đã có. Hãy dùng **javax.crypto.Mac với HmacSHA256** thay vì tự ghép key vào message rồi băm.

## 3. Hai tầng băm trong quy trình ký HTTP request

Giả sử client muốn gửi:

~~~http
POST /v1/payments?currency=VND&dryRun=true HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"orderId":"ord-123","amount":50000}
~~~

Quy trình đúng theo hợp đồng ký minh họa:

~~~mermaid
flowchart TD
    A["Tạo HTTP method, raw URI, header và body bytes"] --> B["SHA-256(body bytes)"]
    B --> C["Encode digest thành hex chữ thường"]
    C --> D["Dựng canonical request: method, URI, signed headers, body digest"]
    D --> E["UTF-8(canonical request)"]
    E --> F["HMAC-SHA256 với shared secret"]
    F --> G["Base64 chữ ký và gắn header"]
    G --> H["Gửi chính body bytes đã băm/ký"]
    H --> I["Server dựng lại canonical, so sánh HMAC và chống replay"]
~~~

Hai phép tính khác nhau:

~~~text
bodyHash  = lowercaseHex(SHA256(bodyBytes))
canonical = Canonicalize(method, requestTarget, signedHeaders, bodyHash)
signature = Base64(HMAC_SHA256(secretBytes, UTF8(canonical)))
~~~

**SHA-256(bodyBytes)** có chức năng rút toàn bộ body về 32 byte để đưa vào canonical request mà không phải đặt một JSON lớn trực tiếp vào chuỗi ký. **HMAC-SHA256** xác thực toàn bộ canonical request, trong đó có body hash, bằng shared secret. Cách làm này là một **thiết kế hợp đồng ký** thường gặp, không phải yêu cầu mọi giao thức HMAC đều phải dùng riêng X-Content-SHA256. Một giao thức khác có thể HMAC trực tiếp trên body hoặc dùng representation khác nếu client và server đã thống nhất.

Giả sử kẻ tấn công sửa body và tính lại SHA-256; nếu digest **không nằm trong dữ liệu HMAC bảo vệ**, server có thể nhận body/digest giả mạo. Khi digest được ràng buộc vào HMAC, kẻ tấn công không biết secret sẽ không thể tạo chữ ký hợp lệ cho canonical request mới theo giả định bảo mật của HMAC.

Không nên hiểu SHA-256(body) là một cách xác thực riêng, cũng không nên nghĩ chỉ ký body là đủ. Request còn có **method, path, query, Content-Type, identity/audience, timestamp và nonce**; nếu một trường ảnh hưởng nghiệp vụ mà bị bỏ khỏi canonical, proxy có thể thay nó mà chữ ký trên body vẫn giữ nguyên.

## 4. HMAC sử dụng hàm băm như thế nào?

HMAC là một **Message Authentication Code dựa trên hàm băm**, được thiết kế với hai lần áp dụng hash cùng một khóa được biến đổi bằng các hằng số nội/ngoại.

Với H = SHA-256 và khóa K, ký hiệu chuẩn là:

~~~text
K' = NormalizeKey(K, blockSize=64 bytes)

HMAC(K, m) =
    H((K' XOR opad) || H((K' XOR ipad) || m))

ipad = byte 0x36 lặp lại trên cả block 64 byte
opad = byte 0x5c lặp lại trên cả block 64 byte
||   = nối byte, XOR = phép XOR từng byte
~~~

Nếu K dài hơn block size, bước chuẩn hóa khóa băm K trước, rồi đệm zero cho đủ block; nếu K ngắn hơn thì đệm zero ngay. Kết quả HMAC-SHA256 cũng có **32 byte** nhưng **không phải** SHA-256 thuần của message. HMAC sử dụng khóa và cấu trúc hai lớp nhằm tạo tính xác thực; nó không có cùng rủi ro length-extension của phép tự ghép SHA256(secret || message).

Không cần tự triển khai những bước trên trong dự án. Java cung cấp thuật toán **HmacSHA256** qua javax.crypto.Mac; thư viện đảm nhiệm việc xử lý khóa, ipad/opad và hash an toàn, giảm nguy cơ sai giao thức.

Hàm hash bên trong HMAC vẫn là một primitive mật mã, nhưng **tính an toàn của HMAC không thể quy về câu nói “khó tìm va chạm SHA-256”**. Khi đánh giá cơ chế request authentication, còn phải xét entropy của secret, canonical format, khóa áp dụng cho dịch vụ nào, replay, điểm xác minh, so sánh chữ ký và lỗi triển khai.

## 5. Hợp đồng ký mẫu dùng body digest

Ví dụ này tự định nghĩa hợp đồng **HMAC-V1**, có phạm vi cố định cho API thanh toán. Nó **không phải chuẩn chung** bắt buộc tương thích với AWS, HTTP Message Signatures hay mọi nhà cung cấp API khác. Chỉ dùng hợp đồng này khi client và server cùng chấp nhận nó.

| Thành phần | Quy định trong ví dụ | Vì sao cần bảo vệ? |
| --- | --- | --- |
| HMAC-V1 | Marker ở dòng đầu tiên | Tách phiên bản/miền sử dụng khi format thay đổi. |
| Method | POST, chữ hoa ASCII | Ngăn đổi GET/POST/DELETE mà vẫn giữ chữ ký. |
| Request target | Raw path + raw query, giữ nguyên thứ tự và percent-encoding | Ngăn sửa endpoint, account ID, query điều khiển nghiệp vụ. |
| Audience | payments-api | Không cho dùng cùng chữ ký ở API đích khác nếu verifier kiểm tra audience. |
| X-Client-Id | partner-42 | Xác định client được phép dùng key. |
| X-Key-Id | key-2026-11 | Cho verifier chọn đúng phiên bản secret. |
| X-Timestamp | Unix epoch seconds, chuỗi số thập phân | Giới hạn thời gian chấp nhận khi server kiểm tra. |
| X-Nonce | 16 byte ngẫu nhiên mã hóa hex chữ thường | Cho server phát hiện replay nếu nonce được lưu nguyên tử. |
| Content-Type | application/json, giá trị chính xác | Không cho thay đổi cách diễn giải body. |
| X-Content-SHA256 | 64 ký tự hex chữ thường của SHA-256(body bytes) | Ràng buộc body vào HMAC. |

Canonical request của ví dụ là những dòng sau, nối bằng **LF (0x0A), không có LF cuối**:

~~~text
HMAC-V1
POST
/v1/payments?currency=VND&dryRun=true
audience:payments-api
x-client-id:partner-42
x-key-id:key-2026-11
x-timestamp:<epoch-seconds>
x-nonce:<32-lowercase-hex-characters>
content-type:application/json
x-content-sha256:<64-lowercase-hex-characters>
~~~

Các giá trị trong dấu ngoặc nhọn/nhỏ ở trên chỉ để minh họa vị trí dữ liệu, không phải giá trị chữ ký hoặc hash. Không ký trực tiếp chính header **X-Signature**, vì như vậy tạo vòng phụ thuộc tự tham chiếu. X-Signature được gửi bên ngoài canonical, chứa **Base64 tiêu chuẩn** của kết quả HMAC-SHA256 32 byte. Khóa secret được cấp riêng, giải mã từ Base64 của cấu hình (ví dụ secret manager), **không** truyền theo header.

Quy tắc nhất quán cần chốt trước:

1. Client và verifier dùng **cùng UTF-8**, thứ tự dòng, tên header chữ thường, ký tự phân cách và quy tắc whitespace. Không có dòng trắng ở cuối.
2. Request target là **raw path + raw query như thực sự được gửi**. Không tự sắp xếp query, giải mã %2F thành /, gộp //, chuẩn hóa ký tự Unicode hoặc đổi dấu + và %20. Các trường hợp parser mơ hồ cần từ chối nếu contract không quy định.
3. Body hash tính trên **chính byte body được gửi/xác minh**. Hai JSON có ý nghĩa tương tự nhưng khoảng trắng hoặc thứ tự field khác nhau tạo digest khác, vì hash tính trên byte chứ không tính trên “ý nghĩa JSON”.
4. Nếu server/gateway giải nén gzip, tự thêm charset hoặc rewrite path trước khi xác minh, hợp đồng phải quy định rõ **ở điểm nào** và **trên representation nào** thực hiện bước hash và ký. Không âm thầm băm một dạng rồi xác minh dạng khác.
5. Từ chối header quan trọng bị lặp, chứa CR/LF hoặc có nhiều cách diễn giải. Giá trị audience phải được verifier ràng buộc với **dịch vụ đang xử lý**, không tin header forwarded do bên ngoài tự cung cấp.

## 6. Cài đặt Java 17: SHA-256 và HMAC-SHA256

Đoạn Java sau minh họa nguyên vẹn quá trình lấy body bytes, kiểm thử SHA-256 bằng test vector, xây canonical request và dùng HMAC để tạo header chữ ký. Nó tạo một HttpRequest sẵn sàng gửi nhưng **không thực hiện kết nối tới tên miền ví dụ**.

Client thực tế phải đọc khóa qua secret manager hay biến môi trường **HMAC_SHARED_SECRET_B64** (Base64 của secret ngẫu nhiên có ít nhất 32 byte), và **HMAC_KEY_ID** (phiên bản key server đã cấp). Không đưa secret thực vào source code, Git, log hoặc HTTP header.

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacHashExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String CONTENT_TYPE = "application/json";

    public static void main(String[] args) throws Exception {
        // Test vector công khai: SHA-256 của đúng 3 byte ASCII "abc".
        String expected = "ba7816bf8f01cfea414140de5dae"
            + "2223b00361a396177a9cb410ff61f20015ad";
        String actual = sha256Hex("abc".getBytes(StandardCharsets.UTF_8));
        if (!expected.equals(actual)) {
            throw new AssertionError("SHA-256 test vector không khớp");
        }

        // Serialize body một lần; dùng cùng bytes để hash và gửi.
        byte[] body = "{\"orderId\":\"ord-123\",\"amount\":50000}"
            .getBytes(StandardCharsets.UTF_8);
        String bodyHash = sha256Hex(body);

        String clientId = "partner-42";
        String keyId = requiredEnv("HMAC_KEY_ID");
        byte[] secret = Base64.getDecoder().decode(
            requiredEnv("HMAC_SHARED_SECRET_B64")
        );
        if (secret.length < 32) {
            throw new IllegalArgumentException("Secret test cần >= 32 byte");
        }

        String timestamp = Long.toString(Instant.now().getEpochSecond());
        byte[] nonceBytes = new byte[16];
        RANDOM.nextBytes(nonceBytes);
        String nonce = HexFormat.of().formatHex(nonceBytes);

        String target = "/v1/payments?currency=VND&dryRun=true";
        String canonical = String.join("\n",
            "HMAC-V1",
            "POST",
            target,
            "audience:payments-api",
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:" + CONTENT_TYPE,
            "x-content-sha256:" + bodyHash
        );
        String signature = hmacBase64(secret, canonical);

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + target))
            .header("Content-Type", CONTENT_TYPE)
            .header("X-Client-Id", clientId)
            .header("X-Key-Id", keyId)
            .header("X-Timestamp", timestamp)
            .header("X-Nonce", nonce)
            .header("X-Content-SHA256", bodyHash)
            .header("X-Signature", signature)
            .POST(HttpRequest.BodyPublishers.ofByteArray(body))
            .build();

        // API example.test là ví dụ; không gửi request thật.
        System.out.println("Đã ký request: " + request.method());
    }

    private static String sha256Hex(byte[] input)
            throws GeneralSecurityException {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] digest = md.digest(input);
        return HexFormat.of().formatHex(digest); // hex chữ thường
    }

    private static String hmacBase64(byte[] key, String canonical)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        byte[] tag = mac.doFinal(
            canonical.getBytes(StandardCharsets.UTF_8)
        );
        return Base64.getEncoder().encodeToString(tag);
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến môi trường: " + key);
        }
        return value;
    }
}
~~~

**Giải thích những dòng quan trọng:**

- **MessageDigest.getInstance("SHA-256")** tạo đối tượng hash SHA-256; digest(body) nhận **byte[]**, không tự chuyển một String ngầm định sang charset mặc định. Có thể dùng update(...) nhiều lần cho body lớn rồi digest() khi kết thúc, nhưng tất cả chunk phải đúng thứ tự và đúng byte thực sự gửi.
- **HexFormat.of().formatHex(...)** biến 32 byte digest thành 64 ký tự hex chữ thường theo contract. Nếu server cần Base64, phải đổi cả hai đầu; không được lẫn kiểu biểu diễn.
- **Mac.getInstance("HmacSHA256")** là API xác thực dùng key bí mật; khác với MessageDigest.getInstance("SHA-256"). Đầu ra HMAC 32 byte được mã hóa Base64 để chuyển trong header.
- **String.join("\n", ...)** định nghĩa ranh giới dòng và thứ tự field. Với giá trị header tùy ý từ request, cần **validate** và reject CR/LF, duplicate header và các trường không được phép; code minh họa dùng giá trị cố định hoặc có định dạng được kiểm soát.
- **BodyPublishers.ofByteArray(body)** giữ đúng byte array mà client đã băm. Nếu middleware hoặc gateway làm biến đổi body sau ký, server cần quy tắc tương ứng, nếu không chữ ký sẽ sai.
- **Key ID** là định danh khóa, không phải khóa; server phải dùng cặp client ID/key ID để chọn đúng secret, xác minh audience và kiểm tra vòng đời key.

Ở hệ thống xử lý request đồng thời, không chia sẻ một instance **MessageDigest** hoặc **Mac** có trạng thái giữa nhiều thread nếu không đồng bộ; tạo instance riêng cho mỗi phép tính hoặc dùng cơ chế quản lý trạng thái đúng. Ví dụ trên tạo instance mới cho từng lần gọi.

### 6.1. Server kiểm tra kết quả như thế nào?

Từ request đã nhận tại trust boundary phù hợp, server:

1. Xác thực định dạng method/request target/header; chặn header trùng hoặc mơ hồ, giới hạn body size và xác định byte representation cần băm.
2. Lấy secret bằng client ID + key ID đã được cấp, kiểm tra key đang hiệu lực và **audience:payments-api** đúng với dịch vụ này.
3. Tính lại SHA-256(body bytes), so sánh với X-Content-SHA256; dựng lại canonical request từ **giá trị thực nhận** theo cùng hợp đồng.
4. Tính HMAC-SHA256 rồi so sánh **byte chữ ký** sau Base64 decode bằng phép so sánh thời gian hằng tương đối, ví dụ **MessageDigest.isEqual(expected, supplied)**, không so sánh chuỗi HMAC theo cách thông thường.
5. Chỉ khi HMAC hợp lệ mới đánh dấu nonce đã dùng bằng thao tác nguyên tử, kiểm tra timestamp nằm trong cửa sổ cho phép và áp dụng phân quyền trước hành động nghiệp vụ. Thứ tự kiểm tra timestamp so với HMAC có thể được tối ưu để từ chối input sai sớm, nhưng **không** ghi nhận nonce chưa xác thực.

**Không dùng** việc so sánh body hash đúng làm điều kiện duy nhất để xác thực: body hash do người gửi tự tính được, còn HMAC mới ràng buộc nó với shared secret. Server cũng không được lấy client identity từ X-Authenticated-User hoặc X-Verified do proxy không đáng tin tự đưa vào.

## 7. “Cùng nội dung” chưa chắc “cùng byte”

Hàm hash hoạt động trên **chuỗi byte**, không hiểu cú pháp JSON, XML hay query string. Thay đổi trình bày có thể đổi digest:

~~~json
{"amount":50000,"currency":"VND"}
~~~

~~~json
{
  "currency": "VND",
  "amount": 50000
}
~~~

Hai tài liệu có thể biểu diễn cùng trường nghiệp vụ nhưng byte UTF-8 khác nhau do whitespace và thứ tự field. Tương tự, chuỗi tiếng Việt có thể dùng các chuỗi Unicode code point khác nhau nhưng trông giống nhau; nếu encode không thống nhất, byte và SHA-256 sẽ khác. Không tự chuẩn hóa Unicode ở một phía trừ khi hợp đồng quy định cùng cách chuẩn hóa ở cả hai phía.

| Sai lệch tại client/proxy/gateway | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Ký JSON compact nhưng gửi JSON được pretty-print lại | Body SHA-256 server khác client | Serialize một lần thành byte[]; dùng đúng byte[] cho hash và send. |
| Client UTF-8, server đọc String rồi encode bằng charset khác | Digest không khớp | Định nghĩa charset; ưu tiên hash raw body bytes trước parse. |
| Một phía hash trên body gzip, phía kia hash trên body đã giải nén | Digest sai dù nội dung sau parse giống nhau | Quy định rõ encoded/decoded representation và vị trí giải nén. |
| Proxy đổi Content-Type hoặc charset sau ký | Có thể làm backend diễn giải khác | Ký các header ảnh hưởng cách hiểu body. |
| Gateway đổi raw URI (%2F thành /, đổi thứ tự query) | Canonical request và chữ ký sai hoặc route không nhất quán | Xác minh trước rewrite tại thành phần tin cậy hoặc chuyển metadata gốc qua kênh có xác thực. |
| Hash trước khi proxy thêm/xóa byte cuối body | Digest mismatch | Tính trên đúng stream được gửi/xác minh; kiểm tra filter/interceptor. |
| Request body rỗng | Digest SHA-256 vẫn có giá trị 32 byte | Hash mảng byte rỗng; đừng bỏ trường vì body không có nội dung. |

**Proxy không tin cậy** không thể tạo HMAC hợp lệ cho body đã sửa khi không có secret, nhưng nó có thể thay các trường **chưa nằm trong canonical**, phát lại một request đã ký hoặc làm thay đổi route thông qua khác biệt parser. Vì vậy bảo vệ request là bài toán gồm cả **hợp đồng hash + canonical + trust boundary**, không chỉ kiểm tra SHA-256.

## 8. Timestamp, nonce, key rotation và phân quyền liên quan gì đến hash?

**Timestamp và nonce** thường được chuyển thành text rồi đặt vào canonical request **trước khi tính HMAC**, nhằm ràng buộc giá trị đó với chữ ký. HMAC hợp lệ vẫn có thể bị replay nguyên văn; server phải kiểm tra cửa sổ timestamp (ví dụ ±300 giây theo chính sách hệ thống), đồng thời lưu nonce đã sử dụng theo client/key trong storage chia sẻ giữa mọi replica. Nonce cần sinh mới đủ ngẫu nhiên, ví dụ 128 bit từ SecureRandom; thao tác ghi nonce nên có ngữ nghĩa insert-if-absent **nguyên tử** và TTL đủ bao phủ khoảng request còn được chấp nhận.

Với retry của giao dịch tài chính, mỗi lần ký có thể tạo timestamp/nonce mới, nhưng **idempotency key** vẫn cần được bảo vệ trong hợp đồng ký và áp dụng ở tầng nghiệp vụ để tránh thực hiện hai lần khi response đầu tiên bị mất. HMAC đúng không đảm bảo “chỉ xử lý một lần”.

**Key rotation:** Client chọn key ID đang active và dùng đúng secret tương ứng; server chỉ chấp nhận các key ID theo chính sách thời gian hiệu lực, giai đoạn chuyển đổi và thu hồi. Đưa key ID vào canonical để chống sửa lựa chọn key trên đường truyền. Shared secret phải được lưu an toàn, không dùng giá trị body digest như secret và không dùng một key cho nhiều dịch vụ có phạm vi quyền khác nhau nếu không có ràng buộc audience và chính sách thích hợp.

**Authentication khác authorization:** Một chữ ký HMAC đúng chứng minh bên gọi có thể sử dụng secret đã cấp và request đã ký không bị sửa theo hợp đồng. Nó **không chứng minh** bên gọi được đọc đơn hàng của người khác, ghi xóa tài nguyên hoặc thay đổi tenant. Sau xác thực, backend phải kiểm tra quyền theo client identity, resource, action, scope và các quy tắc nghiệp vụ.

## 9. Lỗi bảo mật phổ biến khi dùng hash function

| Lỗi | Tại sao nguy hiểm hoặc không đúng? | Cách khắc phục |
| --- | --- | --- |
| Chỉ gửi SHA-256(body) làm “chữ ký” | Đối thủ có thể sửa body rồi tính lại digest | Dùng HMAC với shared secret trên canonical chứa body digest. |
| Tự viết SHA256(secret || message) làm MAC | Dễ sai thiết kế, có nguy cơ length extension | Dùng javax.crypto.Mac với HmacSHA256. |
| Chỉ ký body, không ký method/URI/query | Proxy đổi route hoặc tham số nghiệp vụ mà HMAC không phát hiện | Ký đủ các thành phần ảnh hưởng quyết định xử lý. |
| Cho client gửi “canonical string” rồi tin nguyên văn | Server có thể ký/xác minh khác dữ liệu request đang thực thi | Verifier **tự dựng** canonical từ request đã được parse theo contract tại boundary tin cậy. |
| Dùng hash làm secret hoặc coi body digest là bí mật | Hash được tính công khai, có thể dò dữ liệu đoán được | Secret phải là key ngẫu nhiên được cấp riêng; không log digest của dữ liệu nhạy cảm nếu dễ suy đoán. |
| Đưa secret vào HTTP request hoặc hard-code source | Proxy/người truy cập source có thể lấy key và tự ký | Dùng secret manager, biến môi trường được bảo vệ; rotate khi nghi lộ. |
| So sánh chữ ký bằng String.equals | Có thể để lộ tín hiệu timing trong một số bối cảnh | Base64 decode và dùng phép so sánh byte MAC thời gian hằng tương đối. |
| Bỏ timestamp hoặc nonce vì “HMAC đã an toàn” | Request hợp lệ có thể bị phát lại | Dùng timestamp/nonce được ký, nonce store nguyên tử. |
| Chọn HMAC-MD5/SHA-1 cho giao thức mới | Khó đáp ứng chính sách mật mã mới, tạo nợ kỹ thuật | Dùng HMAC-SHA256 hoặc thuật toán được chính sách hiện hành cho phép. |
| Bỏ qua proxy/gateway rewrite | Client/server hash hoặc canonical trên biểu diễn khác nhau | Kiểm thử trên HTTP stack, encoding và các điểm chuyển đổi thực tế. |

## 10. Thực hành và kiểm thử

Thực hiện một service client và verifier test với shared secret chỉ dùng trong môi trường học. Lần lượt thay đổi body bytes, method, query, các header ký và key ID. Ghi nhật ký **mã lỗi** và **trace ID**, không ghi shared secret hoặc payload nhạy cảm. Các trường hợp mong đợi:

| Ca thử | Kết quả cần đạt |
| --- | --- |
| SHA-256 của chuỗi byte UTF-8 “abc” | Bằng test vector ba7816bf…f20015ad ở mục 1. |
| SHA-256 của mảng byte rỗng | Bằng e3b0c442…b7852b855 ở mục 1, không phải giá trị trống. |
| Băm cùng byte[] nhiều lần | Digest luôn giống nhau. |
| Đổi một byte trong body | Thông thường digest thay đổi; server từ chối request nếu giữ chữ ký cũ. |
| JSON đổi thứ tự field/whitespace nhưng cùng ý nghĩa | Digest đổi vì byte khác; không tự bỏ qua sự khác biệt. |
| Client thay method hoặc query đã ký | Chữ ký sai khi verifier dựng lại canonical từ request nhận. |
| Giữ body nhưng thay trường header không được ký và ảnh hưởng nghiệp vụ | Xác định được lỗ hổng thiết kế; bổ sung trường đó vào contract. |
| Đổi key ID mà giữ secret cũ | Server dùng key mới theo ID sẽ từ chối chữ ký không phù hợp. |
| Cùng secret, khác canonical request | HMAC-SHA256 khác; không nhầm với SHA-256 thuần của body. |
| Replay hai lần cùng nonce trong cửa sổ timestamp | Lần sau bị từ chối sau bước HMAC hợp lệ; test cả hai replica đồng thời. |
| Chữ ký hợp lệ nhưng thiếu quyền sửa tài nguyên | Xác thực thành công nhưng phân quyền từ chối. |
| Request qua proxy đổi body encoding hoặc raw URI | Xác minh tuân theo hợp đồng; dữ liệu bị biến đổi không hợp lệ phải bị từ chối. |

### Câu hỏi tự đánh giá

1. Vì sao giá trị SHA-256 của body không thể tự xác thực client, ngay cả khi được gửi trong một header mang tên “Signature”?
2. HMAC-SHA256 khác SHA-256(secret || message) ở điểm nào? Vì sao nên dùng API Mac có sẵn?
3. Hai JSON có cấu trúc logic giống nhau nhưng khác whitespace sẽ có cùng SHA-256 không? Cần làm gì để client và server ký cùng byte?
4. Nếu proxy sửa path mà không sửa body, việc chỉ ký body hash có phát hiện được không?
5. Vì sao cần nonce store và idempotency nếu timestamp và chữ ký đã hợp lệ?
6. Khi rotate key, key ID và secret phải được server kiểm tra như thế nào, và HMAC hợp lệ có thay thế kiểm tra quyền được không?

**Ghi nhớ:** SHA-256 là **hàm băm mật mã không khóa** trên byte; nó giúp ràng buộc body với một digest cố định nhưng **không tự chứng minh danh tính**. HMAC-SHA256 dùng shared secret để xác thực **canonical request**; muốn hệ thống HTTP an toàn cần thống nhất byte representation, phạm vi trường được ký, điểm xác minh qua proxy/gateway, replay protection và phân quyền.
