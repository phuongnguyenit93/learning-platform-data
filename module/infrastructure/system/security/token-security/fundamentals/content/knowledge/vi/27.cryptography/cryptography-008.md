# Constant-time comparison

Một API nhận mã xác thực (MAC) đi kèm request. Server tự tính lại MAC từ dữ liệu request và khóa bí mật, sau đó kiểm tra mã khách hàng gửi có đúng hay không. Một lập trình viên viết vòng lặp so sánh hai mảng byte và **trả về ngay khi gặp byte đầu tiên khác nhau**. Kết quả logic hoàn toàn đúng: MAC sai bị từ chối, MAC đúng được chấp nhận. Tuy nhiên, thời gian chạy có thể vô tình tiết lộ **bao nhiêu byte đầu của MAC đã khớp**.

Đó là một dạng **timing side channel**: một thông tin phụ về bí mật được phản ánh qua thời gian thực thi. Nếu kẻ tấn công có thể gửi nhiều giá trị tự chọn và phân biệt các mức thời gian đủ chính xác, một phép so sánh tưởng chừng vô hại có thể trở thành **oracle** để tìm dần dữ liệu cần được bảo vệ.

**Constant-time comparison** là kỹ thuật thiết kế phép kiểm tra sao cho, đối với đầu vào có kích thước công khai đã được xác định, đường thực thi **không phụ thuộc vào vị trí byte đầu tiên khác nhau hoặc giá trị bí mật đang so sánh**. Trong ứng dụng Java, nên ưu tiên primitive hoặc thư viện mật mã đã được duy trì và kiểm tra, chẳng hạn **`MessageDigest.isEqual`** cho các digest/MAC dạng byte array thích hợp, thay vì tự viết vòng lặp thoát sớm.

> **Điều cần phân biệt:** “constant-time” không có nghĩa mọi HTTP request đều tốn chính xác số nanosecond bằng nhau. Scheduling, GC, JIT, I/O, cache CPU, độ dài đầu vào và đường xử lý ứng dụng vẫn có thể gây biến thiên. Mục tiêu là **không để nội dung bí mật điều khiển phép so sánh theo cách tiết lộ từng phần**.

Bài thuộc chương **Cryptography** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung liên hệ trực tiếp với việc bảo vệ JWT, opaque token, access token, refresh token, client authentication, OAuth 2.0/OIDC, claims, scope, audience, phát hành, xác minh, lưu trữ, thu hồi và chống token bị đánh cắp hoặc replay.

Sau bài, bạn sẽ phân biệt đúng so sánh thường và so sánh giảm rò rỉ thời gian, sử dụng API Java phù hợp, xử lý trường hợp sai độ dài, đặt kỹ thuật này đúng chỗ trong luồng xác minh token và xây dựng kiểm thử cả về **tính đúng đắn** lẫn **rủi ro side channel**.

## 1. Vì sao thời gian chạy có thể trở thành thông tin bảo mật?

Lấy một bí mật dài bốn byte để dễ nhìn:

~~~text
expected = [0xA7, 0x10, 0x5C, 0xE2]

request A = [0x00, 0x00, 0x00, 0x00]  -> sai ngay byte 0
request B = [0xA7, 0x00, 0x00, 0x00]  -> sai tại byte 1
request C = [0xA7, 0x10, 0x00, 0x00]  -> sai tại byte 2
request D = [0xA7, 0x10, 0x5C, 0x00]  -> sai tại byte 3
~~~

Nếu comparator duyệt lần lượt rồi dừng khi sai, số byte đã kiểm tra tương ứng khoảng **1, 2, 3, 4**. Trong môi trường thật, một lời gọi có thể quá nhanh và nhiễu để nhìn trực tiếp; nhưng việc gửi nhiều requests, đo nhiều lần hoặc khai thác một điểm kiểm tra nằm gần attacker có thể cải thiện khả năng phân biệt.

~~~mermaid
flowchart LR
    A["Attacker gửi giá trị đoán"] --> B["Server so sánh bí mật"]
    B --> C{"Sai ở byte thứ mấy?"}
    C --> D["Trả lỗi với thời gian khác nhau"]
    D --> E["Đo lặp lại / thống kê"]
    E --> F["Suy đoán prefix bí mật"]
    F --> A
~~~

Sơ đồ minh họa **nguy cơ của phép so sánh thoát sớm** khi có oracle quan sát được. Nó không chứng minh mọi hệ thống có thể bị khai thác từ xa; khả năng khai thác phụ thuộc vào độ chính xác đo, nhiễu, rate limit, định dạng dữ liệu và cách server xử lý request.

### Phân biệt thông tin đầu vào công khai và bí mật

Nếu server từ chối một token có cú pháp sai hoặc chuỗi dài hàng megabyte từ bước parse, thời gian xử lý có thể khác token đúng định dạng. Điều này không tự động là lỗ hổng timing: **độ dài/cú pháp của đầu vào do attacker gửi là công khai**. Điều nguy hiểm là **thời gian khác nhau theo nội dung bí mật chưa được phép tiết lộ**, chẳng hạn số byte đầu tiên của MAC dự kiến đã khớp.

**Constant-time comparison không sửa được mọi side channel** của cả ứng dụng, nhưng là một lớp bảo vệ thiết thực ở điểm so sánh secret/MAC/digest.

## 2. Mô hình đe dọa: kẻ tấn công biết và điều khiển những gì?

Không phải mọi phép so sánh đều cần cùng một biện pháp. Trước khi chọn API, hãy xác định:

| Câu hỏi | Ví dụ | Ảnh hưởng tới thiết kế |
|---|---|---|
| Giá trị nào bí mật? | MAC dự kiến, token verifier, reset token, secret key | Không để nội dung ấy ảnh hưởng đường xử lý so sánh |
| Đối thủ có chọn đầu vào không? | MAC tự đoán trong request | Có thể so nhiều giá trị để tìm quan hệ timing |
| Đối thủ đo được ở đâu? | Trong cùng máy, cùng mạng, qua HTTP | Độ nhiễu và khả năng đo khác nhau |
| Kích thước bí mật có cố định không? | HMAC-SHA-256 dài 32 byte | Có thể chuẩn hóa rồi so sánh cố định độ dài |
| Kẻ tấn công được thử bao nhiêu lần? | Không rate limit hoặc một lần/giây | Rate limiting làm giảm cơ hội thu thập mẫu |
| Có các lỗi khác tiết lộ thông tin không? | Khác HTTP status, account enumeration, log chứa token | CT compare đơn lẻ không đủ |
| Bí mật có entropy cao không? | Token ngẫu nhiên 256 bit so với PIN sáu chữ số | CT compare không biến PIN ngắn thành bí mật khó đoán |

Ví dụ **MAC của chữ ký request** là trường hợp điển hình cần tránh timing oracle. Với **opaque bearer token** được sinh bằng CSPRNG và có entropy cao, việc attacker đoán ngẫu nhiên vẫn cực khó; tuy nhiên điểm xác minh token vẫn nên tránh so sánh bí mật thoát sớm, vì thực hành an toàn giúp giảm rủi ro nếu format hoặc entropy thay đổi về sau.

**Không suy diễn “phép so sánh không constant-time = token chắc chắn bị lấy được”.** Nó là điểm yếu cần đánh giá theo threat model. Ngược lại, cũng không nói “request chạy qua Internet nên không ai đo được”: số lượng phép thử và chất lượng tín hiệu có thể thay đổi theo môi trường.

## 3. Mã so sánh thoát sớm sai ở đâu?

Một đoạn Java dễ viết:

~~~java
static boolean insecureEquals(byte[] expected, byte[] supplied) {
    if (expected.length != supplied.length) {
        return false;
    }
    for (int i = 0; i < expected.length; i++) {
        if (expected[i] != supplied[i]) {
            return false; // Dừng ngay tại byte khác đầu tiên
        }
    }
    return true;
}
~~~

**Kết quả boolean là đúng**, nhưng thời gian vòng lặp phụ thuộc vị trí byte sai. Các cách viết tương tự:

~~~java
// Đều không nên tự xem là constant-time theo nội dung bí mật.
boolean a = java.util.Arrays.equals(expectedMac, suppliedMac);
boolean b = expectedMacHex.equals(suppliedMacHex);
boolean c = expectedTokenString.contentEquals(suppliedTokenString);
~~~

**`Arrays.equals` và `String.equals` là API so sánh giá trị**, không mang cam kết mật mã về timing. Không lấy một benchmark ngẫu nhiên “thấy có vẻ đều nhanh” làm bằng chứng chúng constant-time.

### Không chỉ có vòng lặp rõ ràng

Một vài kiểu sai khác:

~~~text
if (supplied.startsWith(expectedSecretPrefix)) ...
if (supplied.substring(0, 8).equals(expected.substring(0, 8))) ...
if (firstHalfMatches) then compareSecondHalf ...
lookup(secretFromDatabase) then return error depending on matching prefix
~~~

Những pattern này có thể làm lộ **một phần nội dung bí mật** hoặc tạo nhánh khác nhau theo từng giai đoạn. Trong hệ thống bảo mật, không nên tách MAC/tag thành từng phần để xác minh với logic tùy biến.

## 4. Constant-time comparison thực sự bảo đảm điều gì?

Trong mô hình lý tưởng, đối với **cùng độ dài công khai**, số bước xử lý không phụ thuộc vào các byte bí mật.

~~~text
Input A và B có độ dài cố định N.

Naive comparison:
  thời gian ~ vị trí byte khác đầu tiên

Constant-time style:
  thời gian không dựa trên vị trí byte khác đầu tiên
  và không trả sớm dựa trên từng byte bí mật
~~~

Tính chất này không có nghĩa **thời gian tuyệt đối luôn cố định**: CPU caches, JIT compilation, interpreter, GC và system scheduling vẫn làm số đo biến thiên. Các primitive thư viện có thể cung cấp bảo đảm theo **nội dung digest** trong phạm vi API/implementation, không phải bảo đảm *toàn bộ endpoint* không lộ bất kỳ tín hiệu nào.

### Những điều không được lẫn lộn

1. **Constant-time comparison**: hạn chế rò nội dung bí mật qua đường so sánh.
2. **Constant-time cryptography**: thuật toán ký/xác minh hoặc xử lý khóa bí mật có thể cần chống side channel sâu hơn (nhánh, tra bảng, bộ nhớ, microarchitecture).
3. **Uniform API errors**: giảm lộ thông tin qua mã lỗi, thông báo và response shape.
4. **Rate limiting**: giảm số phép thử có thể quan sát.
5. **Cryptographic strength**: HMAC, AEAD, digital signatures và entropy của token quyết định các bảo đảm khác; CT comparator không thay thế thuật toán mạnh.

Ví dụ một endpoint trả **HTTP 401** giống nhau cho mọi MAC sai nhưng dùng comparator thoát sớm vẫn có thể lộ thời gian. Ngược lại, dùng comparator tốt nhưng trả **`first 6 bytes match`** trong lỗi vẫn tự tiết lộ bí mật qua nội dung.

## 5. Java: ưu tiên MessageDigest.isEqual cho byte arrays thích hợp

Trong Java, **`java.security.MessageDigest.isEqual(byte[] digesta, byte[] digestb)`** được dùng để so sánh hai digest. Tài liệu JDK hiện đại mô tả cách triển khai hướng tới thời gian **không phụ thuộc nội dung** các mảng được so sánh; thời gian có thể phụ thuộc **độ dài của đối số thứ nhất (`digesta`)**. Vì vậy nên dùng **digest dự kiến đã được chuẩn hóa và cố định độ dài ở đối số thứ nhất**.

~~~java
import java.security.MessageDigest;

public final class DigestChecks {
    private DigestChecks() {}

    public static boolean equalsMac(byte[] expectedMac, byte[] suppliedMac) {
        // expectedMac nên có độ dài cố định đúng thuật toán,
        // ví dụ HMAC-SHA-256 là 32 bytes.
        if (expectedMac == null || expectedMac.length != 32
                || suppliedMac == null || suppliedMac.length != 32) {
            return false;
        }
        return MessageDigest.isEqual(expectedMac, suppliedMac);
    }
}
~~~

### Ví dụ dùng đúng với HMAC-SHA-256

~~~java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

public final class HmacRequestVerifier {
    private HmacRequestVerifier() {}

    public static boolean verify(
            byte[] key,
            byte[] canonicalRequestBytes,
            byte[] suppliedTag
    ) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        byte[] expectedTag = mac.doFinal(canonicalRequestBytes);

        // Với HmacSHA256, expectedTag có 32 bytes.
        // Không dùng Arrays.equals hoặc String.equals với tag bí mật.
        return suppliedTag != null && suppliedTag.length == 32
                && MessageDigest.isEqual(expectedTag, suppliedTag);
    }
}
~~~

**Điều kiện quan trọng:** `canonicalRequestBytes` phải được hai bên định nghĩa **cùng một cách bất biến** (method, path, query, body hash, timestamp/nonce nếu có). Nếu cách canonicalization không đúng, comparator có an toàn về timing cũng không cứu được một giao thức xác thực request sai.

Không tạo `SecretKeySpec` từ literal hard-coded trong code production. HMAC key cần đủ entropy, kho quản lý khóa, rotation và quyền sử dụng phù hợp. Tránh log **key**, raw request mang PII, expectedTag hoặc suppliedTag.

### Giới hạn của phương thức

- `MessageDigest.isEqual` không xác minh **nguồn gốc khóa**, **hết hạn request**, **nonce bị replay**, scope hay audience.
- Nếu caller gửi `suppliedTag` sai độ dài, ứng dụng có thể **từ chối vì độ dài không đúng**; độ dài của mã thuật toán thường là **thông số giao thức công khai**.
- Khi đặc tả yêu cầu tag cố định độ dài, **không được tự cắt ngắn tag** để so cho vừa đầu vào; chỉ chấp nhận dạng truncation nếu **giao thức xác định rõ** độ dài tag và mức an ninh còn phù hợp.
- Dùng **implementation/JDK được duy trì**; đặc tính timing cụ thể phụ thuộc phạm vi cam kết của JDK và hệ thống thực thi, không phải chứng minh toàn bộ chương trình chạy constant-time.

## 6. Độ dài khác nhau: từ chối ngay có vi phạm constant-time không?

Với MAC/AEAD tag có kích thước được giao thức quy định, **độ dài là thông tin công khai**. Một input 7 bytes gửi tới chỗ cần HMAC-SHA-256 32 bytes có thể bị từ chối tại lớp **validation**; điều đó không tiết lộ byte bí mật nào từ tag dự kiến.

Tuy nhiên, cần phân biệt:

| Độ dài | Bản chất | Cách xử lý |
|---|---|---|
| Độ dài MAC theo thuật toán (32 bytes cho HMAC-SHA-256) | Công khai | Validate rõ, không chấp nhận mã thiếu |
| Độ dài token format do server thiết kế | Có thể công khai nếu format cố định | Giới hạn input để chống DoS và lỗi parser |
| Độ dài mật khẩu của người dùng | **Thông tin nhạy cảm trong nhiều ngữ cảnh** | Không tạo endpoint tiết lộ thông tin độ dài password |
| Độ dài private key, plaintext hay dữ liệu bên trong cryptographic operation | Có thể nhạy cảm theo protocol | Dựa vào thư viện/protocol chống side channel |
| Độ dài digest expected trong JDK | Cần ổn định theo thuật toán | Đặt digest fixed-length ở đối số thứ nhất |

### Không tự viết thuật toán xử lý độ dài bằng bí mật

Một đoạn “constant time” tự chế:

~~~java
// KHÔNG khuyến nghị dùng như primitive mật mã:
int diff = a.length ^ b.length;
for (int i = 0; i < Math.min(a.length, b.length); i++) {
    diff |= a[i] ^ b[i];
}
return diff == 0;
~~~

Đoạn này có thể không thoát sớm theo byte, nhưng **thời gian phụ thuộc `min(length)`**, độ dài có thể thuộc secret-dependent input, và JIT/compiler/hardware không cung cấp bảo đảm constant-time tổng quát cho code Java tự viết. Hãy ưu tiên primitive đã được duy trì/thử nghiệm.

**Đừng tự điền zero để ép hai mảng khác độ dài thành giống nhau** rồi chấp nhận kết quả. Nếu tag bắt buộc 32 bytes, phải kiểm **đúng 32 bytes** trước khi xác minh; padding tự phát có thể gây chấp nhận nhiều biểu diễn của một credential.

## 7. So sánh bytes, hex, Base64URL: canonicalization trước hay sau?

HMAC/JWT/token thường được vận chuyển dưới dạng **hex** hoặc **Base64URL**. Hai chuỗi văn bản có thể khác cách biểu diễn, trong khi bytes sau decode giống hoặc khác tùy quy tắc encoding.

~~~text
Wire format:
  "RANDOM_BASE64URL_STRING"
          |
          v
strict decode according to protocol
          |
          v
byte[] suppliedTag
          |
          v
MessageDigest.isEqual(expectedFixedLengthTag, suppliedTag)
~~~

### Nguyên tắc

1. **Kiểm format và giới hạn độ dài đầu vào** để tránh DoS/parser ambiguity.
2. Decode theo **một chuẩn được giao thức quy định** (ví dụ Base64URL không padding nếu đó là format đã chọn).
3. Không tự động trim whitespace, đổi case, decode URL nhiều vòng hoặc chấp nhận encoding khác ngoài contract.
4. Dùng **bytes đã decode** để so sánh MAC/digest, không dùng `String.equals` trên biểu diễn văn bản rồi coi là cryptographically safe.
5. Nếu cần **canonical encoding**, yêu cầu input có dạng chính tắc và từ chối representation thay thế không được phép.
6. Không phản hồi khác nhau để tiết lộ từng byte MAC đúng; format errors có thể phân loại riêng, nhưng cân nhắc uniform public failure tại boundary nhạy cảm.

**Hex chữ hoa/thường và Base64URL padding** cần chính sách rõ. Một giao thức chấp nhận hai dạng tương đương có thể hợp lệ nếu được thiết kế như thế; nhưng khi token được dùng làm key trong cache, audit hoặc chữ ký, biểu diễn không canonical có thể gây khác biệt trạng thái và phát lại ngoài dự kiến.

## 8. MAC, digital signature và AEAD tag cần cách xác minh khác nhau

Không dùng một hàm `equals` để thay thế mọi thuật toán mật mã.

| Đối tượng | Primitive xác minh nên dùng | Vai trò của constant-time comparison |
|---|---|---|
| **HMAC-SHA-256/HMAC-SHA-512** | Tính lại MAC bằng khóa đúng, so byte tag | Hữu ích khi kiểm tag dự kiến và tag nhận |
| **HMAC chữ ký JWT `HS256`** | JOSE/JWT library với key và alg được cấu hình | Library xử lý thuật toán, canonical signing input và compare |
| **RSA/ECDSA/EdDSA JWT signature** | **`Signature.verify`**/JOSE verifier phù hợp | Không tự so signature bytes với một digest tự tạo |
| **AES-GCM/ChaCha20-Poly1305 tag** | AEAD decrypt+verify bằng thư viện mật mã | Không tự trích tag và so thủ công thay `Cipher.doFinal` |
| **Opaque token handle** | Lookup/verify bằng AS, token binding/expiry | Nếu so secret verifier/digest, tránh early exit |
| **Password** | Argon2id/scrypt/bcrypt/PBKDF2 theo policy + library verifier | CT compare ở một lớp không thay slow password hashing |
| **One-time code (OTP)** | Giao thức TOTP/HOTP/step-up có giới hạn thử | Comparator tốt nhưng rate limit, TTL, single-use quan trọng hơn |

Đặc biệt, khi xác minh **JWT RS256**, không được làm:

~~~text
hash(payload) == jwt.signature
~~~

RSA/ECDSA/EdDSA là các thuật toán xác minh chữ ký với encoding, key, hash và điều kiện riêng. JWT verifier phải kiểm **thuật toán được chấp nhận, key từ issuer tin cậy, chữ ký, iss, aud, exp, token type và scope**. Không chỉ so sánh một trường chữ ký bằng `MessageDigest.isEqual`.

**Constant-time comparison là điểm cuối của một bước đối chiếu byte-secret cụ thể, không phải một cách viết lại toàn bộ cryptographic verification.**

## 9. JWT và OAuth: khi nào dùng, khi nào không cần?

Đối với access token JWT, Resource Server thường làm:

~~~mermaid
flowchart TD
    A["Bearer JWT"] --> B["Parse cấu trúc, giới hạn kích thước"]
    B --> C["Chọn issuer và key theo cấu hình tin cậy"]
    C --> D["JOSE library verify signature"]
    D --> E{"Signature và algorithm hợp lệ?"}
    E -->|Không| X["Reject"]
    E -->|Có| F["Kiểm iss, aud, exp, nbf và token profile"]
    F --> G{"Scope và resource policy cho phép?"}
    G -->|Không| X
    G -->|Có| H["Allow resource access"]
~~~

**`iss`, `aud`, scope, HTTP method và resource IDs** thường là dữ liệu có ngữ nghĩa giao thức/ủy quyền, không phải secret cần so constant-time từng ký tự. So chúng bằng logic chuẩn hóa/cấu hình đúng là quan trọng hơn việc ép toàn bộ `String.equals` thành constant-time.

**Vị trí constant-time hữu ích** ở JWT có thể là:

- Bên trong JOSE library khi kiểm **HMAC signature**.
- Khi so một **nonce/state bí mật, cố định độ dài** theo protocol riêng.
- Khi so digest được dẫn xuất từ token/credential sau khi parse đúng.

**Không được viết JWT verifier thủ công chỉ để dùng một comparator constant-time.** Dùng thư viện JOSE đáng tin; kiểm **alg allowlist**, key binding tới issuer, `kid` chỉ là gợi ý tìm key, không tải key từ URL chưa tin cậy, và tách ID token khỏi access token.

## 10. Opaque access token và refresh token: đừng so secret bằng String.equals

Một opaque token là **giá trị bearer**: ai nắm nó có thể thử sử dụng nó theo quyền và thời hạn. Khi AS chọn cách phát token ngẫu nhiên entropy cao rồi lưu **hash/HMAC fingerprint**, nó có thể kiểm credential dựa trên giá trị dẫn xuất.

~~~text
Client giữ:
  raw opaque token T

Authorization Server lưu:
  token_ref / grant_ref / client_id
  protected token digest/fingerprint
  expires_at / revoked_at / token_type

Khi client gửi T:
  validate format/length -> derive digest -> tìm record
  -> kiểm client/grant/purpose/exp/revocation
  -> chỉ dùng constant-time compare nếu cần đối chiếu secret digest
~~~

### Hash index và constant-time compare là hai vấn đề khác nhau

Một database query:

~~~sql
SELECT token_id, client_id, token_type, expires_at, revoked_at
FROM oauth_tokens
WHERE token_digest = :computed_digest;
~~~

**SQL query, B-tree/hash index và I/O không được mặc định constant-time**. Tính thời gian truy vấn có thể phụ thuộc token có tìm thấy hay không. Nhưng với **random token đủ entropy**, kẻ tấn công không thể đoán từng prefix chỉ nhờ một lookup theo digest với thuộc tính mật mã tốt; query không trả ra “đã khớp bao nhiêu byte”.

Khi hệ thống có **selector công khai + verifier bí mật** hoặc phải đối chiếu **expected digest với supplied digest** bên trong một record đã chọn, hãy dùng **constant-time byte comparison** ở bước đối chiếu.

Đừng tự hứa “gọi MessageDigest.isEqual sẽ làm toàn bộ database-backed token validation constant-time”. An toàn tổng thể còn phụ thuộc entropy token, kiểu index, lookup semantics, response errors, rate limiting và trạng thái token.

### Phân biệt access token và refresh token

- **Access token** dùng tại Resource Server được chỉ định bởi audience/scope.
- **Refresh token** dùng tại Authorization Server token endpoint để xin token mới theo grant/client binding.
- **OIDC ID token** dùng tại RP để kiểm chứng kết quả đăng nhập, không thay access token.

Một phép so sánh đúng không cho phép **refresh token** được chấp nhận làm Bearer ở API. Cần kiểm **token type/purpose**, `iss`, `aud`, scope, client/subject, time claims hoặc trạng thái introspection phù hợp.

## 11. Java: xác minh một token verifier tách khỏi selector công khai

Một thiết kế cho token ngẫu nhiên có thể chia thành:

~~~text
Token cấp cho client:
    tk1.<public-selector>.<secret-verifier>

Server lưu:
    selector (index để tìm record)
    expected_verifier_mac = HMAC(serverPepper, secret-verifier)
    client_id, token_type, grant_ref, expires_at, revoked_at
~~~

**Selector không phải secret xác thực**: nó chỉ giúp tìm record. **Secret verifier** phải sinh bằng **CSPRNG, entropy đủ cao** và chỉ được client thấy ở lần cấp. Dạng hai phần là **một thiết kế nội bộ giả định**, không phải format bắt buộc của OAuth 2.0. Trong hệ thống chuẩn, có thể dùng opaque token dạng một chuỗi ngẫu nhiên và tra cứu trực tiếp bằng digest.

### Pseudocode kiểu Java: một nơi dành riêng cho việc so bytes

~~~java
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

// PSEUDOCODE: các loại TokenRecord, TokenRepository,
// ParsedOpaqueToken và PolicyEngine là thành phần của ứng dụng.
public final class OpaqueVerifierService {
    private final TokenRepository repository;
    private final byte[] serverPepper;

    public OpaqueVerifierService(
            TokenRepository repository, byte[] serverPepper
    ) {
        this.repository = repository;
        this.serverPepper = serverPepper.clone();
    }

    public TokenDecision verify(
            ParsedOpaqueToken presented,
            TrustedRequestContext context
    ) throws Exception {
        // Parser đã kiểm version, kích thước và encoding công khai.
        TokenRecord record = repository.findByPublicSelector(
                presented.selector()
        );

        byte[] computed = hmacSha256(
                serverPepper, presented.verifierBytes()
        );

        // Digest giả là fixed-length, giúp không phải bỏ qua
        // bước so sánh chỉ vì selector chưa tìm thấy.
        // Không tuyên bố cách này làm DB lookup constant-time.
        byte[] expected = record == null
                ? repository.fixedDummyDigest32()
                : record.expectedVerifierDigest32();

        boolean matched = MessageDigest.isEqual(expected, computed);

        if (record == null || !matched) {
            return TokenDecision.reject();
        }

        // Phần dưới KHÔNG thuộc bảo đảm của constant-time comparison.
        if (!record.isActive()
                || record.isExpired(context.clock())
                || !record.isForClientAndPurpose(context)
                || !record.hasExpectedIssuerAndAudience(context)
                || !context.policy().mayUse(record)) {
            return TokenDecision.reject();
        }
        return TokenDecision.allow(record);
    }

    private static byte[] hmacSha256(byte[] key, byte[] value)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(value);
    }
}
~~~

**Ví dụ không phải code production copy-paste**. Nó giả định repository trả về record được kiểm soát và **expectedVerifierDigest32** luôn đúng **32 bytes**, không chứa raw verifier. Trong thực tế:

- **Tạo verifier ngẫu nhiên đủ entropy** khi phát token; không dùng password do người dùng đặt cho loại token handle này.
- **Kiểm version/format/độ dài hợp lệ** trước HMAC để tránh memory/CPU DoS.
- **Không lấy serverPepper từ client** hay gắn một secret của tenant khác vào phép kiểm.
- **Không dùng `record == null` như bằng chứng mọi timing path đã được cân bằng**: query database, cache miss, client lookup, logging và policy khác nhau vẫn có thể được quan sát.
- **Giữ các trường cần kiểm ở nguồn đáng tin**: token type, expiry, client binding, issuer, audience, grant và revocation. Selector chỉ chọn record, không quyết định quyền.
- **Không dùng cùng một HMAC key cho nhiều mục đích tùy ý**; phân tách purpose/namespace hoặc dùng khóa dẫn xuất rõ ràng.
- Khi policy cần thu hồi ngay, database/current-state hoặc introspection/cache phải có freshness thích hợp; phép so HMAC đúng không chứng minh token vẫn active.

### Vì sao không dùng `equals` của object record?

Một `record` Java tự sinh `equals` để kiểm các field theo thứ tự, không mang bảo đảm thời gian độc lập bí mật. Đừng gọi `storedToken.equals(presentedToken)` khi object chứa secret rồi kết luận đã có cryptographic verification. Tốt hơn là tạo **API verify riêng** không lộ raw token qua `toString()`, logs hoặc exception.

## 12. HMAC fingerprint và bảo vệ dữ liệu trong kho token

Nhiều OAuth deployments lưu **HMAC-SHA-256 của token** làm key tra cứu thay vì lưu raw bearer token. Điều này có thể giảm hậu quả khi database/token index bị đọc trái phép, miễn là:

1. Token thực có **entropy cao và độc lập**.
2. Khóa HMAC/pepper nằm ở **secret manager/KMS hoặc vùng quản lý thích hợp**, không cùng quyền truy cập với mọi bản sao database.
3. Dùng **purpose separation** cho token fingerprint (access, refresh, recovery hoặc cache key) theo thiết kế.
4. Không log raw token, secret key hay toàn bộ Authorization header.
5. Tính đến **rotation** và cách kiểm các token còn hiệu lực khi đổi key.

### Ví dụ hàm tạo fingerprint

~~~java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public final class TokenFingerprint {
    private TokenFingerprint() {}

    public static String hmacHex(byte[] key, String opaqueToken)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        byte[] digest = mac.doFinal(
                opaqueToken.getBytes(StandardCharsets.UTF_8)
        );
        return HexFormat.of().formatHex(digest);
    }
}
~~~

Hàm có tác dụng tạo **fingerprint**, **không phải comparator**. Một nơi khác có thể dùng fingerprint làm key tìm token record. Đối với một mật khẩu có entropy thấp, việc dùng HMAC đơn thuần **không thay thế password hashing** và không phải kết luận rằng kho credential đã đủ an toàn.

### Cache key khác verifier

~~~text
introspection cache key:
    trusted issuer + resource server + caller identity
    + HMAC(cacheKeySecret, rawAccessToken)

database verifier:
    token lookup / protected digest, client/grant binding,
    expiry + revocation checks
~~~

Hai mục đích có thể dùng **key material khác nhau**. Cache entry của RS còn phải tách theo **issuer, audience và introspection caller context**, tránh dùng token state từ RS này cho một RS khác. Cache key có HMAC **không bảo đảm active=true vẫn tươi** sau revocation.

**Không lấy một fingerprint SHA-256 không khóa, có thể đoán brute-force, làm định danh công khai cho mã OTP ngắn**. Dữ liệu có không gian nhỏ vẫn dễ bị dò nếu attacker có digest và biết thuật toán; dùng thiết kế dành riêng cho OTP với rate limits, TTL, one-time semantics và lưu trữ an toàn.

## 13. Client authentication: secret, private_key_jwt và mTLS

Trong OAuth 2.0, một **confidential client** có thể được xác thực bằng:

- **client_secret_basic/client_secret_post** theo profile và policy của AS.
- **private_key_jwt**: client ký JWT assertion bằng private key; AS kiểm chữ ký với public key thuộc registration của đúng client.
- **mTLS**: xác thực client bằng chứng thư/mutual TLS theo hợp đồng.

### Không so sánh client secret dạng String đơn giản

Một triển khai tự viết:

~~~java
// Không nên coi phép này là bảo đảm constant-time theo secret.
if (configuredClientSecret.equals(suppliedClientSecret)) {
    authenticateClient();
}
~~~

Hướng phù hợp hơn là dùng **thành phần client authentication của Authorization Server framework**, có cơ chế kiểm secret/hashed secret được duy trì, policies, throttling và audit. Nếu có tình huống phải kiểm digest/MAC dạng byte array, dùng primitive thích hợp thay vì `String.equals` thoát sớm.

### Không áp dụng comparator cho private_key_jwt sai chỗ

AS không xác thực private_key_jwt bằng cách so chuỗi JWT với một secret lưu sẵn:

~~~text
Sai:
  suppliedJwt.equals(registeredPublicKey)

Đúng về mô hình:
  parse JWT assertion
  -> validate allowed alg, JOSE header, iss=sub=client_id
  -> validate aud đúng token endpoint/AS theo policy
  -> validate exp, iat, jti/replay protections
  -> verify digital signature với public key của client
  -> kiểm client registration và grant policy
~~~

**Chữ ký số dùng primitive xác minh riêng**. Dùng **JOSE library/JCA Signature.verify** với alg/key binding đúng profile; không tự viết so sánh chữ ký để thay verification.

### mTLS không phải so chuỗi certificate

mTLS dựa vào TLS stack, chứng thư, trust anchors, key possession và client binding. So hai chuỗi **subject DN** hoặc bytes chứng thư bằng `MessageDigest.isEqual` không thay được path validation và possession proof. Constant-time comparator chỉ là một công cụ trong hệ thống mật mã, không phải cơ chế xác thực client đầy đủ.

## 14. OAuth state, nonce và PKCE: so sánh đúng nhưng phải ràng buộc flow

Trong **Authorization Code + PKCE** và OIDC:

| Giá trị | Vai trò chính | Điều cần kiểm |
|---|---|---|
| **state** | Client tương quan authorization response với yêu cầu đã tạo, chống mix-up/CSRF theo flow | Giữ nguyên, đúng browser/transaction, TTL và issuer binding |
| **nonce (OIDC)** | Liên kết ID token với authentication request trong các flow áp dụng | ID token đã verify, nonce đúng request, chống replay |
| **code_verifier** | Secret chứng minh client nắm verifier khi đổi authorization code | AS kiểm quan hệ với **code_challenge** đã lưu, code/client/redirect binding |
| **code_challenge** | Dẫn xuất từ verifier theo phương thức PKCE được hỗ trợ | Phải kiểm **S256** theo policy, không chấp nhận downgrade |
| **authorization code** | Credential ngắn hạn để đổi lấy token | Đúng client, redirect URI, TTL, single-use, PKCE |

Ví dụ PKCE S256:

\[
\text{code\_challenge} =
\operatorname{BASE64URL\_NO\_PAD}\left(\operatorname{SHA256}(
\operatorname{ASCII}(\text{code\_verifier}))\right)
\]

AS phải tính lại challenge từ code_verifier được trình bày, đối chiếu với **challenge đã ràng buộc với chính authorization code**, rồi kiểm các điều kiện còn lại. Nếu tự triển khai so bytes digest/challenge, tránh early-exit comparator; tốt hơn là dùng thư viện OAuth PKCE đáng tin và kiểm format theo RFC.

### Constant-time không thay state binding

Giả sử `state` được so bằng `MessageDigest.isEqual` và khớp chính xác, nhưng client dùng nó trong transaction thuộc **issuer khác**, hoặc dùng một state chung cho mọi browser. Hệ thống vẫn có thể mắc **login CSRF, mix-up hoặc replay**.

**Sự khớp bằng byte là điều kiện cần trong một số bước, không phải chứng cứ toàn bộ OAuth flow hợp lệ.** Phải kiểm transaction chưa dùng, đúng session/browser, đúng issuer, redirect URI và các ràng buộc PKCE theo profile.

### Nếu state sai format?

Giới hạn độ dài và định dạng công khai ngay ở parser là bình thường. Không giữ state quá dài hoặc chứa dữ liệu nhạy cảm thô; tốt nhất dùng **giá trị random opaque**, lưu binding trong server-side state. Đừng biến một state có format khác nhau thành oracle tiết lộ cấu trúc session bí mật.

## 15. Password, PIN và OTP: constant-time không chữa entropy thấp

Một hệ thống đăng nhập có thể kiểm password, PIN hoặc TOTP. Các credential này khác HMAC tag ngẫu nhiên 256-bit:

| Credential | Vấn đề trọng tâm | Hướng bảo vệ |
|---|---|---|
| **User password** | Entropy có thể thấp, bị brute force/credential stuffing | Password hashing có salt và cost phù hợp (Argon2id/bcrypt/scrypt/PBKDF2 theo policy), rate limits, MFA |
| **PIN ngắn** | Không gian nhỏ | Giới hạn thử, lockout/challenge/risk signals, TTL khi thích hợp |
| **TOTP/HOTP code** | Mã ngắn, có cửa sổ thời gian/counter | Rate limits, chống replay, kiểm time window, secret storage |
| **Recovery token ngẫu nhiên** | Bearer credential có entropy cao | TTL ngắn, one-time use, HMAC/digest storage và đối chiếu an toàn |
| **MAC/tag** | Có thể là secret-dependent expected bytes | Dùng HMAC/AEAD cryptographic verification, CT compare khi phù hợp |

### Không so plaintext password bằng equals

~~~java
// Sai: không được lưu password dưới dạng plaintext.
if (storedPassword.equals(inputPassword)) {
    login();
}
~~~

Đúng về nguyên tắc:

~~~text
User nhập password
    -> password hashing verifier từ thư viện uy tín
    -> xác minh hash có salt/cost đúng profile
    -> kết hợp account status, rate limits, MFA và session policy
~~~

**Không chỉ SHA-256 password rồi so bằng constant-time**: một hash nhanh dù so đúng timing vẫn có nguy cơ brute-force offline khi database bị lộ. Dùng **password hashing có cost**, salt và cấu hình được cập nhật. Nếu username không tồn tại và server bỏ qua hoàn toàn bước password hashing, khác biệt thời gian có thể góp phần tạo **account enumeration**; chính sách có thể dùng dummy verifier đúng cost để giảm khác biệt, đồng thời dùng generic errors và throttling. Điều đó **không bảo đảm** mọi đường DB/network có thời gian giống nhau.

### OTP cần kiểm single-use

Giả sử TOTP của user đúng, comparator constant-time trả true. Nếu server cho dùng cùng code 20 lần trong cửa sổ 30 giây mà không có chính sách replay, attacker có thể phát lại mã. Vì vậy **time window, attempt budget, one-time/replay detection và atomicity** quan trọng song song với việc so mã.

Không dùng constant-time comparison để né thiết kế **rate limiting** cho mã 6 chữ số — một attacker vẫn có thể đoán một mã bất kỳ trong không gian nhỏ qua nhiều attempts nếu server cho phép.

## 16. Thời gian tổng thể của endpoint vẫn có thể tiết lộ thông tin

Một lỗi kiến trúc:

~~~text
1. Parse token.
2. Database lookup.
3. Nếu không tìm thấy token: trả 401 trong 1 ms.
4. Nếu tìm thấy: tính HMAC, kiểm expiry, gọi policy service.
5. Trả 401 trong 20 ms nếu secret sai.
~~~

Dù bước kiểm HMAC ở mục 4 là constant-time, attacker có thể quan sát **hai nhóm thời gian**. Điều đó có thể tiết lộ **selector/token ID tồn tại hay không**, hoặc khác biệt giữa account còn hoạt động và account bị khóa.

### Phân loại những rò rỉ cần đánh giá

- **Token/account existence** qua query miss/hit.
- **Credential prefix match** qua comparator thoát sớm.
- **Trạng thái token** (unknown/expired/revoked) qua HTTP code hoặc thông báo quá chi tiết.
- **Tenant/client membership** qua policy service I/O.
- **Cache state** (valid token cache hit nhanh, invalid token cache miss chậm).
- **Trạng thái signing key** qua lựa chọn nhánh crypto khác nhau.
- **Server error/timeout** qua dependency hoặc fallback bất thường.

Không phải mọi khác biệt đều có thể loại bỏ hoàn toàn hoặc nhất thiết là lỗ hổng có thể khai thác. Điều cần làm là **đánh giá bí mật nào bị lộ, mức độ đo được và hậu quả**, sau đó thiết kế lớp phòng thủ phù hợp.

### Không biến mọi request thành sleep cố định

Một biện pháp phổ biến nhưng yếu là:

~~~text
if invalid:
    sleep(100 milliseconds)
    return 401
~~~

Sleep cố định **không làm các đường xử lý trước đó biến mất**; attacker vẫn có thể thống kê phần chênh lệch, còn hệ thống bị tăng latency và chi phí DoS. **Random sleep** cũng không thay thế comparator mật mã hay response policy. Hãy sửa điểm rò chính, dùng thư viện an toàn, áp dụng rate limits và giới hạn số phép thử.

## 17. Timing attack khi so MAC: vì sao một byte lại quan trọng?

Xét một server tự so MAC dài 32 byte:

~~~text
expected HMAC tag:
  [b0, b1, b2, ... b31]  (không cho attacker biết)

Attacker đoán:
  [g0, g1, g2, ... g31]

Naive comparator:
  dừng khi gi != bi lần đầu
~~~

Nếu thời gian có tương quan đủ rõ với **số byte đầu khớp**, attacker về mặt mô hình có thể:

1. Cố định các byte đầu đã suy ra.
2. Thử các giá trị khác nhau cho byte kế tiếp.
3. Lặp nhiều mẫu để phân biệt giá trị có thời gian so sánh dài hơn.
4. Tiếp tục tới hết tag nếu oracle và attempt budget cho phép.

Đây là **mô hình phân tích điểm yếu**, không phải cam kết một tấn công từ xa luôn thực hiện được; khác biệt vài instruction thường bị nhiễu, một số cách triển khai so sánh đã được tối ưu/chống rò, và rate limits có thể cắt khả năng lấy mẫu.

**Trọng tâm phòng thủ:** dùng một cryptographic verifier không có đường thoát theo byte đầu tiên khác và không cho attacker thử vô hạn. Không cần viết một tấn công thật vào production để chứng minh đoạn `return false` trong vòng lặp theo secret là thiết kế không phù hợp.

## 18. Những gì constant-time comparison không bảo vệ

| Rủi ro | Comparator tốt có giải quyết không? | Lớp cần bổ sung |
|---|---|---|
| Token bị lộ qua **log/analytics** | **Không** | Redaction từ nguồn, không lưu raw credential |
| Token bị đánh cắp và **replay** | **Không** | TTL, scope/audience, sender-constraining và revoke |
| JWT dùng **alg/key sai** | **Không** | JOSE verifier, issuer/key binding, alg allowlist |
| Opaque token đã **expired/revoked** | **Không** | AS/RS state validation, introspection và cache freshness |
| Access token gửi tới **sai audience** | **Không** | Audience và resource policy enforcement |
| Refresh token bị dùng làm **access token** | **Không** | Token purpose validation và đúng endpoint |
| OTP entropy thấp | **Không** | Rate limits, TTL, single-use và MFA policy |
| Password yếu/brute-force offline | **Không** | Slow password KDF, salt, MFA và password policy |
| Open redirect sau OAuth logout | **Không** | Exact registered redirect URI và state binding |
| CSRF/OIDC state mix-up | **Không** | Session/transaction/issuer binding |
| DB lookup tiết lộ token existence | **Không tự động** | Query/error policy và threat modeling |
| Spectre/cache-timing/microarchitectural attacks | **Không thể mặc định** | Crypto implementations và hạ tầng có bảo vệ thích hợp |

**Đừng nhầm một thuộc tính của hàm so sánh với sự an toàn của cả giao thức**. Hệ thống OAuth/OIDC còn phụ thuộc token issuance, validation, storage, transport, consent, revocation và phân quyền API.

## 19. Java: verify HMAC tag theo định dạng Base64URL cố định

Đây là ví dụ **Java 17+** nhỏ có thể đặt trong một class để kiểm **HMAC-SHA-256** trên một thông điệp đã được canonicalize. Nó tách **validation của wire format** (độ dài/cú pháp công khai) khỏi **đối chiếu tag theo nội dung**.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class FixedLengthHmacVerifier {
    private static final String ALGORITHM = "HmacSHA256";
    private static final int TAG_BYTES = 32;
    private static final int TAG_BASE64URL_CHARS = 43;

    private FixedLengthHmacVerifier() {}

    public static boolean verify(
            byte[] hmacKey,
            byte[] canonicalMessage,
            String suppliedTagBase64Url
    ) throws GeneralSecurityException {
        if (hmacKey == null || hmacKey.length == 0
                || canonicalMessage == null
                || suppliedTagBase64Url == null
                || suppliedTagBase64Url.length() != TAG_BASE64URL_CHARS) {
            return false;
        }

        byte[] supplied;
        try {
            supplied = Base64.getUrlDecoder().decode(suppliedTagBase64Url);
        } catch (IllegalArgumentException invalidEncoding) {
            return false;
        }

        if (supplied.length != TAG_BYTES) {
            return false;
        }

        // Bảo đảm một dạng biểu diễn Base64URL không padding duy nhất.
        // Đây là so sánh biểu diễn công khai do client gửi,
        // KHÔNG phải so expected secret MAC.
        String canonicalTag =
                Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(supplied);
        if (!canonicalTag.equals(suppliedTagBase64Url)) {
            return false;
        }

        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(hmacKey, ALGORITHM));
        byte[] expected = mac.doFinal(canonicalMessage);
        if (expected.length != TAG_BYTES) {
            throw new GeneralSecurityException("Unexpected HMAC output");
        }

        // expected là digest có kích thước cố định từ thuật toán.
        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

### Các giới hạn phải hiểu trước khi dùng

1. Đầu vào **canonicalMessage** phải được xây từ **giao thức có định nghĩa rõ**. Nếu attacker thay đổi JSON whitespace, HTTP header hoặc đường dẫn để cả hai bên hiểu khác, constant-time compare không giải quyết được.
2. **HMAC key** phải đến từ trusted key management và thuộc đúng client/issuer/purpose. Không tin key được gửi trong request.
3. Định dạng ví dụ là **HMAC-SHA-256 đầy đủ 32 bytes**, encode Base64URL **không padding** thành 43 ký tự. Không tự cắt tag nếu không có profile cụ thể quy định tag truncation.
4. Nhánh từ chối do sai format/length không tiết lộ expected tag; đó là **quy tắc giao thức công khai**. Tuy nhiên, ứng dụng vẫn cần giới hạn request size trước khi allocate/parse.
5. `Mac` không nên được chia sẻ tự do giữa các threads vì đối tượng có trạng thái; ví dụ tạo instance cho mỗi lần verify.
6. Không phản hồi **expected HMAC**, không log **hmacKey, suppliedTag** hay raw data nhạy cảm trong exception.
7. Hàm chỉ xác minh MAC, **không chứng minh authorization của token**. Cần kiểm timestamp, nonce, replay protection, client binding, scope/audience và resource policy khi protocol yêu cầu.

**Một MAC hợp lệ nhưng bị replay có thể vẫn được nhận lại** nếu request không gắn timestamp/nonce hoặc server không ngăn reuse. Constant-time giúp bảo vệ quá trình đối chiếu, không thay anti-replay state.

## 20. Java/JUnit: test đúng-sai, không dùng stopwatch chứng minh constant-time

Một bộ unit test cơ bản có thể kiểm:

- MAC đúng được chấp nhận.
- MAC sai từ byte đầu, giữa hoặc cuối đều bị từ chối.
- Tag không đúng độ dài, Base64URL lỗi hoặc không canonical bị từ chối.
- Cùng dữ liệu nhưng khác key bị từ chối.
- Request thay đổi nội dung phải bị từ chối.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.Test;

final class FixedLengthHmacVerifierTest {
    private static final byte[] KEY = new byte[32];
    private static final byte[] MESSAGE =
            "POST:/orders:body-sha256".getBytes(StandardCharsets.UTF_8);

    private static String tag(byte[] message) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(KEY, "HmacSHA256"));
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(mac.doFinal(message));
    }

    @Test
    void acceptsCorrectTagAndRejectsChangedMessage() throws Exception {
        String correct = tag(MESSAGE);
        assertTrue(FixedLengthHmacVerifier.verify(KEY, MESSAGE, correct));
        assertFalse(FixedLengthHmacVerifier.verify(
                KEY, "modified".getBytes(StandardCharsets.UTF_8), correct));
    }

    @Test
    void rejectsMismatchesAtDifferentPositions() throws Exception {
        byte[] bytes = Base64.getUrlDecoder().decode(tag(MESSAGE));
        for (int i : new int[]{0, 15, 31}) {
            byte[] tampered = Arrays.copyOf(bytes, bytes.length);
            tampered[i] ^= 1;
            String candidate = Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(tampered);
            assertFalse(FixedLengthHmacVerifier.verify(
                    KEY, MESSAGE, candidate));
        }
    }

    @Test
    void rejectsWrongLengthAndMalformedEncoding() throws Exception {
        assertFalse(FixedLengthHmacVerifier.verify(KEY, MESSAGE, "abc"));
        assertFalse(FixedLengthHmacVerifier.verify(KEY, MESSAGE, null));
        assertFalse(FixedLengthHmacVerifier.verify(
                KEY, MESSAGE, "!".repeat(43)));
    }
}
~~~

Các test này **chỉ kiểm kết quả logic**. Chúng **không thể chứng minh constant-time** và không kiểm AS/Resource Server integration. Trong một bài kiểm thử thực tế còn phải xác minh key không có giá trị test-only, không được dùng dữ liệu toàn byte 0 làm khóa thật, và xử lý các lỗi parse theo contract.

### Vì sao không assert thời gian bằng `System.nanoTime()` trong JUnit?

~~~java
// Không nên dùng làm chứng minh bảo mật:
long start = System.nanoTime();
boolean ok = MessageDigest.isEqual(expected, supplied);
assertTrue(System.nanoTime() - start < 1000);
~~~

Kết quả chạy trên CI chịu **JIT, GC, OS scheduling, CPU frequency và test runner noise**. Một giới hạn nanosecond có thể flake hoặc bị bỏ qua nguy cơ thật. Phép đo performance/timing cần **thiết kế thí nghiệm riêng**; unit tests chứng minh API trả kết quả đúng, không chứng minh tính không phụ thuộc secret của machine code.

## 21. Phân tích side channel: đo hiệu năng khác chứng minh an toàn

Các công cụ benchmark như **JMH** có ích để đo performance trong JVM, nhưng bản thân một benchmark ngắn **không chứng minh** hàm constant-time. Tình huống cần đánh giá side channel nghiêm túc đòi quy trình threat modeling và phân tích thống kê phù hợp.

### Điều gì nên được so sánh?

| Nhóm thử | Dữ liệu đầu vào | Mục tiêu |
|---|---|---|
| **Equal** | Hai MAC bytes giống nhau | Kiểm đường thành công |
| **First-byte mismatch** | Cùng length, khác byte 0 | Phát hiện early-exit ở đầu |
| **Middle-byte mismatch** | Cùng length, khác byte giữa | So với đường sai khác ở đầu |
| **Last-byte mismatch** | Cùng length, khác byte cuối | Phát hiện timing tăng theo prefix |
| **Different length** | Giá trị đầu vào sai length công khai | Kiểm parsing/format behavior |
| **Different key/config** | Client có key version khác | Kiểm path selection, không chỉ comparator |
| **Unknown token/account** | Lookup không tồn tại | Phân tích endpoint enumeration risks |
| **Valid but expired/revoked** | MAC đúng, trạng thái bị cấm | Phân biệt crypto verification với lifecycle checks |

### Những điều cần thận trọng

1. Chạy **warmup đủ** để giảm lệch giữa interpreter và JIT-compiled code.
2. Cố định **public input size** khi đánh giá phụ thuộc nội dung bí mật.
3. Tránh phụ thuộc dữ liệu cached của một trường hợp mà nhóm khác không có.
4. Đo trong môi trường được kiểm soát; **remote timing** có nhiễu khác local timing.
5. Dùng phương pháp thống kê được thiết kế cho side-channel analysis khi mức rủi ro đủ cao (ví dụ phương pháp test leakage), không chỉ so trung bình của vài request.
6. Duyệt **source và dependency version**, xem primitive nào cung cấp contract mật mã; khi cần assurance cao, dùng thư viện/provider có tài liệu và đánh giá thích hợp.
7. Đọc kết quả như **bằng chứng hỗ trợ**, không biến “không thấy khác biệt trong 100 lần đo” thành kết luận an toàn tuyệt đối.

**Cách phòng thủ ưu tiên vẫn là loại bỏ comparator thoát sớm và dùng cryptographic libraries đã được kiểm chứng**, sau đó áp dụng giới hạn giao thức, rate limit, logging và policy để giảm các kênh khác.

## 22. Constant-time comparison trong môi trường đa phiên bản khóa

Một Authorization Server có thể xoay HMAC key hoặc lưu nhiều key versions. Đoạn code sau tạo rủi ro:

~~~text
for key in allActiveKeys:
    if HMAC(key, message) == suppliedTag:
        return true
return false
~~~

Nếu dừng ở key đầu tiên khớp, thời gian có thể tiết lộ **key version** hoặc thành công sau bao nhiêu lần thử. Điều đó có thể không phải secret theo mọi giao thức, nhưng cần tránh khi version hoặc key status là thông tin cần bảo vệ. Quan trọng hơn, việc **thử mọi key** có thể vô tình chấp nhận một key cũ đã bị thu hồi.

### Cách thiết kế đúng ranh giới

- Dùng **key ID/kid công khai** khi profile cho phép để chọn khóa **từ trusted registry**; không lấy key material từ URL do attacker tự khai.
- Chỉ chọn key có **purpose/issuer/algorithm/client binding** đúng và còn được phép xác minh.
- Nếu cần hỗ trợ nhiều key trong rotation, **quy định rõ thời gian overlap** và loại token được phép tiếp tục dùng key cũ.
- Dùng primitive xác minh đúng cho từng thuật toán; không trộn HS256 với RS256 hoặc tin header **alg** như quyền tự chọn cách verify.
- Có thể cần **độ dài/đường xử lý tương đương** giữa các key candidates trong threat model đặc biệt; không tự khẳng định một vòng lặp Java là constant-time toàn bộ.

**Constant-time comparison không phải biện pháp thay thế key rotation, HSM/KMS hay kiểm key compromise.** Khi issuer signing key bị xâm phạm, phải xử lý niềm tin của key/token lineage; một comparator tốt không ngăn việc attacker dùng khóa thật để tạo MAC hoặc chữ ký hợp lệ.

## 23. Từ code review tới threat model: các câu hỏi cần hỏi

Khi review một điểm xác minh bí mật:

1. **Đang xác minh cái gì?** MAC bytes, password hash, JWT signature, opaque token verifier, OTP hay public claim?
2. **Đầu vào nào do attacker kiểm soát?** Value, length, encoding, algorithm, key ID, issuer URL, HTTP method?
3. **Giá trị expected đến từ đâu?** Trusted key store, client registration, AS introspection, DB record hay raw header chưa tin?
4. **Có return/break sớm theo nội dung bí mật không?** `String.equals`, `Arrays.equals`, `startsWith` hoặc vòng lặp thủ công?
5. **Library/primitive có hỗ trợ timing-safe comparison không?** Java `MessageDigest.isEqual`, JOSE/JCA verifier hoặc password/AEAD library?
6. **Có khóa ràng buộc đúng client/issuer/purpose không?** Một tag đúng với key sai context không tạo quyền.
7. **Kích thước/encoding có contract cố định không?** Cấm tag thiếu, format mơ hồ, double decoding.
8. **Đường xử lý thành công/sai có tiết lộ metadata không?** Status, error body, cache hit, user existence?
9. **Có rate limiting và replay protection không?** Đặc biệt với OTP/nonce/refresh tokens.
10. **Có kiểm thời hạn, revocation và scope/audience không?** Comparator đúng vẫn có thể chấp nhận token đã revoked nếu logic bỏ qua state.
11. **Raw secret đi đâu?** Logs, exceptions, tracing, cache key, analytics, crash dumps?
12. **Có test đúng-sai và kiểm thử hệ thống không?** Đừng chỉ assert Boolean mà quên token lifecycle và quyền API.

Ví dụ một PR chỉ đổi:

~~~diff
- if (expectedMac.equals(suppliedMac)) {
+ if (MessageDigest.isEqual(expectedBytes, suppliedBytes)) {
~~~

có thể là **cải tiến đúng** nếu code trước đó so MAC bytes, nhưng cần kiểm **expectedBytes có được tính từ key đúng**, **suppliedBytes có decode/length đúng**, **MAC có gắn request/nonce** và **không còn đường khác chấp nhận request sai**. Bảo mật không hoàn thành chỉ vì đổi tên method.

## 24. Ứng cứu nếu phát hiện comparator thoát sớm

Giả sử kiểm tra bảo mật phát hiện endpoint webhook dùng:

~~~java
String supplied = request.getHeader("X-Webhook-Signature");
if (!expectedHexSignature.equals(supplied)) {
    return unauthorized();
}
~~~

Không thể từ đoạn này suy ngay “HMAC key đã bị lộ”. Nhưng cần xử lý nghiêm túc:

1. **Xác định phạm vi:** endpoint nào, thuật toán MAC, secret/key được lưu ở đâu, có bao nhiêu client hoặc tenants chịu ảnh hưởng.
2. **Kiểm khả năng khai thác:** attacker có thể chọn tag, thử bao nhiêu lần, đo local/remote, có log/status khác rò thông tin không.
3. **Chuyển sang verifier/library phù hợp**, kiểm raw/canonical request và fixed-length tag; triển khai version an toàn.
4. **Giới hạn thử** và giám sát abuse trong giai đoạn chuyển đổi; không phá dịch vụ hợp lệ một cách tùy tiện.
5. **Kiểm nhật ký an toàn**: có bất thường về tỷ lệ MAC sai, attempts nhiều, API side effects hay token issuance trái phép không; không trích raw tag/key lên dashboard.
6. **Đánh giá credential exposure**: nếu có bằng chứng khóa bị lấy hoặc MAC forgery thành công, thực hiện **key rotation/revocation** theo phạm vi và ảnh hưởng.
7. **Kiểm replay**: ngay cả MAC hợp lệ cũng phải bị ngăn dùng lại nếu protocol yêu cầu nonce/timestamp.
8. **Regression tests:** sai byte đầu/giữa/cuối, malformed input, wrong key/client, replay, expiry, shared cache/issuer boundaries.

**Không tự rotate toàn bộ issuer signing keys chỉ vì có một comparator thường** nếu chưa có bằng chứng hoặc chính sách yêu cầu; và không trì hoãn sửa comparator chỉ vì chưa chứng minh được exploitation qua Internet.

### Đừng dùng log để “tái dựng MAC”

Không ghi full expected tag/supplied tag để điều tra: chính các log ấy có thể trở thành nguồn credential leakage. Sử dụng request ID, error reason codes chuẩn hóa, trusted client reference, counts và thời gian theo buckets/histogram.

## 25. Ba tình huống xuyên suốt trong hệ thống OAuth và API

### Tình huống A — BFF ký webhook với HMAC

Một **BFF** gọi tới dịch vụ Billing API bằng webhook. Billing API yêu cầu HMAC-SHA-256 của **canonical request**, kèm timestamp và nonce.

~~~text
Trusted configuration:
  key_for_client = secret từ KMS của billing-webhook-client
  algorithm      = HMAC-SHA-256
  tag_length     = 32 bytes

Request:
  method         = POST
  target         = /billing/events
  timestamp      = thời gian từ protocol
  nonce          = random unique value
  signature      = Base64URL(HMAC(canonicalMessage))

Verification:
  1. Xác định client từ trusted registration.
  2. Kiểm TLS, format, body size, timestamp window.
  3. Tạo canonicalMessage theo đúng giao thức.
  4. Tính expected HMAC bằng key đúng client.
  5. MessageDigest.isEqual(expectedBytes, suppliedBytes).
  6. Nếu MAC hợp lệ, kiểm và tiêu thụ nonce atomically.
  7. Áp dụng policy nghiệp vụ trước side effect.
~~~

**Nếu dùng `String.equals` cho MAC**, có thể tạo timing signal theo vị trí byte khác đầu tiên. **Nếu chỉ sửa comparator nhưng bỏ timestamp/nonce**, một request hợp lệ bị chặn trên đường truyền vẫn có thể bị phát lại. **Nếu key từ tenant-A bị dùng để xác minh tenant-B**, constant-time không ngăn việc xác thực sai miền tin cậy.

### Tình huống B — Opaque refresh token được revoke

Authorization Server phát **RT-42** có entropy cao và lưu protected fingerprint/verifier. Client đã ngắt kết nối, nên AS đánh dấu RT-42 **REVOKED**.

~~~text
Token endpoint nhận refresh(RT-42):
  parse/lookup/verify token secret
  -> token record found
  -> check status: REVOKED
  -> reject refresh (no new AT)

Revocation endpoint nhận revoke(RT-42) lần nữa:
  client authentication/ownership
  -> request hợp lệ với token đã invalid
  -> no-op idempotent theo RFC 7009
~~~

**Constant-time verifier giúp ngăn rò prefix bí mật khi đối chiếu token**, nhưng **revocation state** mới quyết định token đã được dùng tiếp hay chưa. Nếu token RT-42 trước đó bị **rotate**, lần gửi nó tới **token endpoint** có thể là refresh-token reuse cần xem xét; lần gửi nó tới **revocation endpoint** để xóa quyền lại là thao tác idempotent, không được trộn hai semantics.

### Tình huống C — JWT access token hợp chữ ký nhưng sai audience

Một access token JWT được ký hợp lệ bởi AS, có claims:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "client_id": "reports-client",
  "scope": "orders:read",
  "exp": 1795400900
}
~~~

**Đây là payload minh họa, không phải JWT đã ký.** Payments API nhận token này. Kể cả JOSE library xác minh chữ ký bằng một thuật toán chống side channel và có MAC comparator tốt, **Payments API phải từ chối** vì **audience không dành cho payments-api**.

Tương tự, Orders API vẫn phải từ chối yêu cầu đọc đơn không thuộc quyền user/tenant hiện tại. **Chữ ký đúng và phép so sánh đúng không đồng nghĩa cấp quyền đúng.**

## 26. Ma trận kiểm thử Constant-time comparison

Ma trận dưới đây chủ ý phân biệt **functional unit tests**, **side-channel review** và **system integration tests**. Không có một assert boolean đơn lẻ nào chứng minh được toàn bộ chương trình constant-time.

| ID | Loại | Trường hợp | Kết quả mong đợi |
|---|---|---|---|
| **S01** | Unit | Hai digest HMAC-SHA-256 cùng 32 byte và cùng giá trị | `MessageDigest.isEqual` trả true |
| **S02** | Unit | Khác byte đầu của tag | Trả false |
| **S03** | Unit | Khác byte giữa của tag | Trả false |
| **S04** | Unit | Khác byte cuối của tag | Trả false |
| **S05** | Unit | HMAC từ payload và key hợp lệ | Request được xác minh nếu các policy khác đạt |
| **S06** | Integration | Opaque token hợp lệ, đúng type/issuer/audience/scope | AS/RS có thể chấp nhận theo grant/policy |
| **S07** | Integration | Client xác thực bằng private_key_jwt đúng profile | AS xác minh chữ ký bằng public key đúng client |
| **F01** | Unit | HMAC sai byte đầu, code dùng `Arrays.equals` | Code review nhận diện thiếu bảo đảm CT; thay bằng primitive phù hợp |
| **F02** | Unit | HMAC sai byte cuối, code dùng vòng lặp return false sớm | Code review đánh dấu timing-dependent prefix |
| **F03** | Unit | Hai digest khác độ dài | Từ chối; không chấp nhận tag cắt ngắn |
| **F04** | Unit | Tag Base64URL malformed | Từ chối, không throw lộ stack trace/secret |
| **F05** | Unit | Tag Base64URL có biểu diễn không canonical | Từ chối theo strict encoding policy |
| **F06** | Unit | HMAC đúng bytes nhưng key của client khác | Từ chối |
| **F07** | Unit | HMAC đúng key nhưng request body bị sửa | Từ chối |
| **F08** | Unit | HMAC đúng key nhưng HTTP path/method bị sửa | Từ chối nếu được đưa vào canonical request |
| **F09** | Security | MAC hợp lệ bị phát lại với nonce đã dùng | Từ chối theo anti-replay policy |
| **F10** | Security | MAC hợp lệ nhưng timestamp ngoài cửa sổ | Từ chối |
| **F11** | Security | Attacker gửi tag quá dài/hàng MB | Parser giới hạn kích thước; không OOM/CPU DoS |
| **F12** | Security | Attacker gửi quá nhiều tag sai | Rate limit/throttling và bảo vệ hạ tầng hoạt động |
| **F13** | Security | Server trả lỗi khác nhau theo byte prefix khớp | Không rò số byte matching trong error response |
| **F14** | Review | User account không tồn tại bỏ qua password KDF | Đánh giá account-enumeration timing, không coi CT digest là đủ |
| **F15** | Review | Password được hash một lần bằng SHA-256 nhanh | Bị coi là không đủ password-hardening |
| **F16** | Security | OTP đúng được gửi lại nhiều lần | One-time/replay protection ngăn dùng lại theo policy |
| **F17** | Security | OTP sai được đoán liên tục | Rate limits/lockout hoạt động, không dựa duy nhất vào CT |
| **F18** | OAuth | OIDC nonce đúng bytes nhưng thuộc auth transaction khác | Từ chối do transaction binding |
| **F19** | OAuth | State đúng nhưng issuer khác với transaction | Từ chối mix-up |
| **F20** | OAuth | PKCE verifier sai được gửi đổi authorization code | Token endpoint từ chối |
| **F21** | OAuth | Code bị dùng lại sau một lần đổi thành công | Token endpoint từ chối replay |
| **F22** | OAuth | Refresh token dùng làm Bearer ở Resource Server | RS từ chối sai token purpose |
| **F23** | OAuth | ID token dùng làm access token | RS từ chối sai token purpose/audience |
| **F24** | OAuth | JWT signature đúng nhưng `aud` sai API | RS từ chối |
| **F25** | OAuth | JWT đúng signature nhưng hết `exp` | RS từ chối |
| **F26** | OAuth | Opaque token verifier khớp nhưng token revoked | AS/RS từ chối theo state |
| **F27** | OAuth | Access token đúng scope nhưng sai tenant/resource | RS từ chối theo object-level authorization |
| **F28** | Crypto | JWT header `alg` yêu cầu thuật toán không allowlist | JOSE verifier từ chối, không downgrade |
| **F29** | Crypto | JWT `kid` trỏ nguồn key không tin cậy | Không fetch/accept untrusted key |
| **F30** | Crypto | HMAC key version đã revoke vẫn được thử | Không nhận key không còn được phép |
| **F31** | Token store | DB lookup theo public selector khác biệt thời gian | Phân tích enumeration threat; CT byte compare không bị coi là đủ |
| **F32** | Token store | Token raw bị ghi vào Redis key/log/metric label | Kiểm thử phát hiện lộ credential |
| **F33** | Cache | Token AT bị revoke, positive cache introspection còn stale | Độ trễ ngừng truy cập không vượt policy |
| **F34** | Cache | Cùng token string thử dưới hai issuer/RS context | Cache không trộn trusted contexts |
| **F35** | Review | Dev viết vòng lặp `diff |= a[i] ^ b[i]` | Không tự tuyên bố có CT guarantee cho JVM/hardware |
| **F36** | Review | Unit test đo nanoTime rồi assert dưới ngưỡng | Không coi đó là chứng minh CT |
| **F37** | Review | Code so raw JWT signature bằng digest tự tạo thay JCA | Dùng cryptographic verifier đúng thuật toán/profile |
| **F38** | Review | AES-GCM tag tự tách và so bằng equals | Dùng AEAD implementation thay so tag thủ công |
| **F39** | Review | Secret được dùng làm dynamic substring/prefix search | Loại bỏ secret-dependent early-exit path |
| **F40** | Operations | Log/exception in `expectedTag` hoặc HMAC key | Không để credential bí mật rời trusted boundary |

### Integration test A — MAC đúng nhưng nonce đã dùng

~~~text
Given:
  Client C1 và AS/API chia sẻ key HMAC theo policy.
  Client tạo request R với timestamp T, nonce N và MAC M.
  Request lần đầu được xác minh và nonce N được consume atomically.
When:
  Client/attacker gửi lại nguyên R, T, N, M.
Then:
  MAC comparison vẫn có thể trả true.
  Server từ chối request lần hai do nonce đã dùng.
  Không có side effect nghiệp vụ thứ hai.
~~~

**Mục tiêu của test:** chứng minh **constant-time MAC verification khác replay prevention**, không kiểm oracle timing bằng cách gọi cùng một request hai lần rồi so nanoseconds.

### Integration test B — Token verifier khớp nhưng token revoked

~~~text
Given:
  Opaque access token AT1 được AS phát hợp lệ.
  AS lưu verifier digest và trạng thái ACTIVE.
When:
  AT1 bị revoke tại AS.
  Client gửi lại AT1 tới RS/token introspection path.
Then:
  Digest/secret comparison có thể khớp.
  AS trả inactive theo chính sách đối với AT1.
  RS từ chối token theo introspection/current-state policy.
  Không ghi raw AT1 trong debug log hoặc audit.
~~~

**Mục tiêu của test:** kiểm **token lifecycle** tách khỏi cryptographic equality. Nếu RS cache `active=true`, phải kiểm thêm revocation freshness SLO và invalidation, không quy trách nhiệm sai cho comparator.

### Integration test C — So sánh MAC không được phụ thuộc byte sai đầu tiên

~~~text
Given:
  Server kiểm HMAC-SHA-256 tag cố định 32 bytes.
  Tester chuẩn bị tags sai ở byte 0, 15, 31.
When:
  Gửi các tags trong một môi trường kiểm soát.
Then:
  Cả ba bị từ chối nhất quán về logic và public error.
  Source/code review xác nhận dùng primitive có contract phù hợp.
  Nếu mức assurance yêu cầu, thực hiện kiểm tra side-channel
  chuyên dụng trong môi trường đo có thiết kế thống kê.
  Không chỉ dựa vào JUnit nanoTime hay một vài mẫu HTTP.
~~~

**Quan trọng:** Không đặt kỳ vọng “ba request phải có cùng thời gian chính xác”. Đồng đều tuyệt đối qua mạng là yêu cầu không thực tế; xác minh tập trung vào primitive, thiết kế secret-independent và bằng chứng đo chuyên dụng theo mức rủi ro.

## 27. Checklist triển khai Constant-time comparison

1. **Đúng đối tượng:** Có xác định đây là MAC, secret verifier, password/OTP, JWT signature hay public claim?
2. **Threat model:** Có biết attacker điều khiển gì, đo được ở đâu, có bao nhiêu attempts và bí mật entropy bao nhiêu?
3. **Không early exit theo bí mật:** Tránh `String.equals`, `Arrays.equals`, `startsWith` và vòng lặp tự thoát sớm cho MAC/digest.
4. **Thư viện chuẩn:** Với digest/MAC fixed-length dùng `MessageDigest.isEqual` phù hợp; chữ ký số/AEAD/password dùng verifier chuyên biệt.
5. **Thứ tự đối số:** Khi dùng Java `MessageDigest.isEqual`, expected digest cố định độ dài đứng trước.
6. **Format:** Input có max size, encoding strict, expected byte length và canonicalization rõ?
7. **Không chấp nhận tag cắt ngắn:** Trừ khi giao thức có profile truncation được phê duyệt riêng.
8. **Key material:** Secret/HMAC key đến từ key manager đúng issuer/client/purpose; không hard-code, không log?
9. **Request binding:** MAC gắn đúng method/path/body/timestamp/nonce nếu giao thức dùng các trường đó?
10. **Replay:** OTP, nonce, PKCE code và refresh token reuse được kiểm độc lập so với MAC equality?
11. **JWT:** Sử dụng JOSE library, alg allowlist, đúng key, iss, aud, exp/nbf và token profile?
12. **OAuth:** Phân biệt access/refresh/ID token, đúng RS audience và scope, grant/client binding?
13. **Status:** Expired/revoked token phải bị từ chối dù digest/verifier khớp?
14. **Storage:** Token raw không nằm trong log, cache key, analytics, error response hoặc ORM `toString`?
15. **High-entropy secrets:** Random bearer token do CSPRNG tạo, không xây từ username/timestamp/counter?
16. **Password:** Dùng slow password hashing, salt, MFA và chống account enumeration; không chỉ HMAC/CT compare.
17. **OTP:** Rate limit, giới hạn thời gian và one-time semantics; không dựa chỉ vào CT compare.
18. **Error policy:** Public failures không tiết lộ số byte khớp hoặc sensitive metadata không cần thiết?
19. **Dependency paths:** DB lookup/cache/token existence timing được đánh giá riêng, không mặc nhiên constant-time?
20. **Concurrency:** One-time state và revocation được thực thi atomic nếu có nhiều AS/RS instances?
21. **Tests:** Có valid/invalid, first/middle/last mismatch, wrong key/client, malformed/length, replay và revoked cases?
22. **Measurement:** Không dùng stopwatch unit test làm chứng minh; khi cần dùng controlled side-channel methodology?
23. **Dependency versions:** JDK, JOSE, cryptography provider được duy trì và theo dõi cảnh báo lỗ hổng?
24. **Operations:** Có rate limits, logging redaction, incident handling và quy trình key rotation phù hợp?

## 28. Câu hỏi tự đánh giá

**1. Constant-time comparison nhằm loại bỏ tín hiệu nào?** Sự khác biệt đường xử lý phụ thuộc **nội dung bí mật**, đặc biệt vị trí byte đầu tiên khác nhau khi so MAC/digest.

**2. `String.equals` và `Arrays.equals` có được xem là constant-time cryptographic comparators không?** Không nên xem như vậy. Chúng là API kiểm giá trị, không mang bảo đảm chống timing leak theo secret.

**3. Java có API nào phù hợp để so digest/MAC dạng byte array?** **`MessageDigest.isEqual`** trong phạm vi contract của JDK; nên đặt **expected digest fixed-length ở đối số thứ nhất** và xác minh toàn bộ protocol conditions.

**4. Nếu MAC có độ dài 32 bytes, từ chối một input 7 bytes trước khi so có sai không?** Không mặc định, vì độ dài tag theo thuật toán là **tham số công khai**. Nhưng không dùng sai độ dài để tiết lộ nội dung bí mật hoặc chấp nhận tag thiếu.

**5. Dùng `MessageDigest.isEqual` có xác minh được JWT RS256 không?** Không. Cần **JCA/JOSE digital signature verifier**, đúng key, algorithm allowlist và các claims/profile.

**6. Nếu tag HMAC đúng nhưng request bị replay, server có nên chấp nhận không?** Không nếu protocol yêu cầu one-time/nonce/timestamp. MAC equality không thay chống replay.

**7. Nếu bearer access token khớp verifier nhưng đã revoked thì sao?** Token phải bị từ chối theo AS/RS state policy. Xác minh secret không tự chứng minh token còn hiệu lực.

**8. Vì sao cần canonicalize request trước khi tính HMAC?** Để hai bên ký/kiểm **cùng bytes có ý nghĩa**, tránh parser ambiguity và việc chỉ bảo vệ một phần request.

**9. HMAC-SHA-256 có thay password hashing chuyên dụng được không?** Không. Password cần slow/adaptive KDF và salt; HMAC comparator không giải quyết brute-force offline của password yếu.

**10. Vì sao 6-digit OTP vẫn cần rate limit nếu dùng constant-time?** Vì không gian OTP nhỏ. Attacker vẫn có thể thử nhiều mã nếu server không giới hạn.

**11. Có thể kết luận toàn endpoint constant-time chỉ vì một hàm MessageDigest.isEqual không?** Không. DB lookup, parsing, cache, policy, status/errors và hạ tầng cũng tạo tín hiệu.

**12. Unit test nanoTime có chứng minh constant-time không?** Không. JIT, GC và nhiễu khiến số đo ngắn hạn thiếu giá trị xác nhận bảo mật.

**13. `kid` trong JWT có được dùng để tải public key từ URL bất kỳ không?** Không. Chỉ chọn key từ **issuer/trusted key registry** và kiểm thuật toán/profiles phù hợp.

**14. Xác minh chữ ký hoặc MAC đúng có tự cấp quyền API không?** Không. Resource Server vẫn kiểm **issuer, audience, thời hạn, token type, scope và quyền của tài nguyên cụ thể**.

**15. Nên làm gì khi phát hiện vòng lặp thoát sớm trong code xác minh MAC?** Thay bằng primitive phù hợp, rà format/key/purpose, đánh giá oracle và rate limit, kiểm test, logging và ảnh hưởng; chỉ rotate key theo chứng cứ/chính sách.

## 29. Tài liệu tham khảo và kết luận

Khi triển khai cho hệ thống thật, hãy đối chiếu tài liệu API/tiêu chuẩn được dùng:

- **Java SE `java.security.MessageDigest.isEqual`**: so sánh digest byte arrays và phạm vi hành vi timing do JDK cung cấp.
- **Java Cryptography Architecture (JCA/JCE)**: **`Mac`**, **`Signature.verify`** và **`Cipher`** cho các primitive khác nhau.
- **RFC 2104 / HMAC**: nguyên tắc xác minh MAC và cấu tạo HMAC.
- **RFC 7515 / JSON Web Signature (JWS)** và **RFC 7518 / JSON Web Algorithms (JWA)**: chữ ký/MAC trong JOSE.
- **RFC 8725 / JSON Web Token Best Current Practices**: kiểm thuật toán, tránh algorithm confusion và kiểm chéo ngữ cảnh.
- **RFC 7636 / PKCE**: `code_verifier`, `code_challenge` và xác minh S256.
- **RFC 6749 / OAuth 2.0**, **RFC 7009 / Token Revocation**, **RFC 7662 / Introspection**: vai trò của token issuance, revocation và Resource Server.
- **OWASP Authentication Cheat Sheet / Password Storage Cheat Sheet**: lớp bảo vệ liên quan account enumeration, rate limiting và password hashing.

**Không có một “so sánh constant-time” duy nhất thay thế thiết kế an toàn của hệ thống mật mã.** Đối với secrets/MAC/digest có format và độ dài cố định, hãy **tránh đường thoát sớm theo byte bí mật, dùng primitive/thư viện được duy trì**, và không dùng `String.equals` hoặc vòng lặp tự chế như bằng chứng chống side channel. Sau phép so sánh, mọi tầng khác vẫn phải thực hiện đúng vai trò: **JWT signature verification, OAuth client binding, token purpose, issuer, audience, scope, expiration, revocation, replay protection, key lifecycle và Resource Server authorization**. **Constant-time comparison bảo vệ một bước đối chiếu; mô hình tin cậy và vòng đời token mới quyết định request được phép hay bị từ chối.**
