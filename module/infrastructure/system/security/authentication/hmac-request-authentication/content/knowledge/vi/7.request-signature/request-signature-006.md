# Signature length: độ dài chữ ký trong HMAC request authentication

Khi thiết kế xác thực HTTP request bằng HMAC, nhiều API đặt mã xác thực vào header có tên `X-Signature` hoặc `Authorization`. Từ **signature** trong ngữ cảnh này thường chỉ **HMAC tag** (mã xác thực đối xứng), không phải chữ ký số bất đối xứng như RSA hay Ed25519. Độ dài tag ảnh hưởng tới khả năng kẻ tấn công đoán một giá trị hợp lệ; song cần phân biệt **số byte MAC**, **số ký tự biểu diễn MAC** và **số byte khóa bí mật**.

Bài học thuộc chương **Request signature** trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Trọng tâm là chọn, biểu diễn và xác minh **signature length** nhất quán cho hợp đồng ký canonical HTTP request gồm method, URI, các header hoặc body. Để triển khai thực tế, bài còn liên hệ độ dài chữ ký với key rotation, chống replay bằng timestamp/nonce, proxy/gateway và việc tách bạch xác thực với phân quyền.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích HMAC-SHA256 tạo **32 byte tag** và vì sao cùng tag có thể biểu diễn thành **64 ký tự hex**, **44 ký tự Base64 chuẩn có padding** hoặc **43 ký tự Base64URL không padding**.
2. Phân biệt độ dài secret, digest, HMAC tag và nonce; không nhầm độ dài chuỗi sau encode với độ mạnh mật mã.
3. Đánh giá việc cắt tag theo một độ dài cố định, hiểu xác suất đoán tag và vì sao không chấp nhận độ dài do client tùy ý khai báo.
4. Viết client/verifier Java 17 tạo và kiểm tra đúng độ dài HMAC-SHA256, reject tag lỗi, dùng so sánh byte phù hợp.
5. Xây test cho dấu padding, prefix, key rotation, canonical request, replay và biến đổi qua gateway.

## 2. Độ dài chữ ký là độ dài của dữ liệu nào?

Với HMAC-SHA256:

~~~text
canonicalBytes = UTF8(canonicalRequest)
tagBytes       = HMAC_SHA256(sharedSecretBytes, canonicalBytes)
                 └── 32 byte = 256 bit

signatureHeader = Base64(tagBytes)
                  └── 44 ký tự ASCII nếu dùng Base64 chuẩn có padding
~~~

**`tagBytes` mới là kết quả mật mã.** Base64 và hex chỉ là cách biểu diễn byte trong HTTP header. Encode không tạo thêm entropy, không làm MAC mạnh hơn và cũng không làm mất bit nếu encode đủ toàn bộ tag.

| Thuật toán MAC | Độ dài tag đầy đủ | Hex chữ thường | Base64 chuẩn có padding | Base64URL không padding |
| --- | ---: | ---: | ---: | ---: |
| HMAC-SHA256 | **32 byte = 256 bit** | 64 ký tự | **44 ký tự** (thường kết thúc bằng `=`) | **43 ký tự** |
| HMAC-SHA384 | 48 byte = 384 bit | 96 ký tự | 64 ký tự (không cần padding) | 64 ký tự |
| HMAC-SHA512 | 64 byte = 512 bit | 128 ký tự | 88 ký tự (thường kết thúc bằng `==`) | 86 ký tự |

Những độ dài này giả định mã hóa đủ tag, không thêm prefix như `sha256=`, dấu ngoặc kép hoặc khoảng trắng. Nếu API gửi chuỗi `sha256=<base64>` thì tổng độ dài header value **lớn hơn** số ký tự Base64, nhưng số bit MAC không đổi.

### Công thức độ dài Base64

Với đầu vào `n` byte:

~~~text
Base64 chuẩn có padding: length = 4 × ceil(n / 3)

32 byte -> 4 × ceil(32 / 3) = 44 ký tự
16 byte -> 4 × ceil(16 / 3) = 24 ký tự
 8 byte -> 4 × ceil(8 / 3)  = 12 ký tự
~~~

Base64URL là một bảng chữ cái khác (`-` và `_` thay `+` và `/`); phiên bản **không padding** có thể ngắn hơn. Trong Java, `Base64.getEncoder()` khác `Base64.getUrlEncoder().withoutPadding()`. Client và verifier phải thống nhất **một** định dạng và quy tắc padding theo signing contract; không tự động chấp nhận tất cả các biến thể chỉ để “tương thích”.

**Đừng nhầm lẫn:**

- **Secret length:** số byte khóa mà client và verifier cùng giữ; 32 byte được tạo ngẫu nhiên bằng CSPRNG là lựa chọn thực dụng cho HMAC-SHA256 mới. Đây là **độ dài khóa**, không phải độ dài chữ ký.
- **Body digest length:** SHA-256(body bytes) cũng dài 32 byte; nhưng đây là **hash không khóa**, mọi bên có body đều tính được. Body digest thường được đưa vào canonical request để HMAC bảo vệ.
- **Nonce length:** có thể sinh 16 byte ngẫu nhiên (128 bit) và biểu diễn thành 32 ký tự hex để chống replay khi server lưu nonce. Đây là **độ dài nonce**, không phải số bit tag HMAC.
- **Signature length:** số byte tag HMAC mà client truyền và server chấp nhận, theo hợp đồng đã khóa cố định.

## 3. Full tag và truncated tag

**Full tag:** sử dụng đủ 32 byte HMAC-SHA256. Đây là mặc định đơn giản cho hầu hết API HTTP mới; không phát sinh quy tắc cắt tag và không có lợi ích lớn khi tiết kiệm vài chục byte header.

**Truncated tag:** lấy đúng **t byte đầu** của tag đầy đủ để truyền, với `t` được quy định trước trong hợp đồng:

~~~text
fullTag = HMAC_SHA256(secret, canonicalBytes)   // 32 byte
tag16   = first 16 bytes of fullTag             // 16 byte = 128 bit

client:    X-Signature = Base64(tag16)
verifier:  expected = first 16 bytes of HMAC_SHA256(secret, canonicalBytes)
           chấp nhận chỉ khi supplied.length == 16 và MAC đúng
~~~

Đây chỉ là **hợp đồng ví dụ có chủ ý truncation**. Không phải vì `Mac.doFinal()` tự trả về 16 byte. Nếu dịch vụ chọn full tag 32 byte thì tag 16 byte **phải bị từ chối**, ngay cả khi nó trùng chính xác 16 byte đầu của tag server tính.

| Chính sách tag | Số bit | Số ký tự Base64 chuẩn có padding | Cách đánh giá |
| --- | ---: | ---: | --- |
| Full HMAC-SHA256 | **256** | **44** | Nên là mặc định cho API mới. |
| Cắt còn 16 byte | 128 | 24 | Có thể chấp nhận khi giao thức đã cố định và có đánh giá số lần thử, vòng đời khóa. |
| Cắt còn 8 byte | 64 | 12 | Không nên là lựa chọn mặc định cho endpoint công khai hoặc cần bảo vệ lâu dài. |
| Cắt còn 4 byte | 32 | 8 | Rất yếu trước nhiều lần thử; không phù hợp cho xác thực request. |
| Client tự chọn số byte | Biến thiên | Biến thiên | **Nguy hiểm:** tạo cơ hội downgrade và lỗi so sánh prefix. |

Không được tự động “cắt cho bằng độ dài tag client gửi”:

~~~java
// SAI: phía đối thủ có thể gửi 1-2 byte đầu đúng của MAC.
byte[] expected = computeHmac(secret, canonicalBytes);
byte[] prefix = Arrays.copyOf(expected, supplied.length);
return MessageDigest.isEqual(prefix, supplied);
~~~

Một số ngôn ngữ có hàm so sánh prefix hoặc `startsWith`; dùng chúng để verify MAC cũng sai. Nếu tag length bị rút đến một byte, kẻ tấn công có thể thử rất ít giá trị. Verifier phải **kiểm tra độ dài chính xác trước** và chỉ so sánh với đúng số byte mà **server policy** quy định.

## 4. Độ dài tag và xác suất đoán chữ ký

Giả sử đối thủ **không biết secret**, mỗi lần gửi một tag đoán ngẫu nhiên độc lập và verifier trả về kết quả. Với tag có `t` bit, xác suất đoán đúng cho một lần thử gần bằng `1 / 2^t` trong mô hình lý tưởng. Với `q` lần thử và `q` nhỏ hơn rất nhiều so với `2^t`:

\[
P(\text{đoán thành công ít nhất một lần}) \approx \frac{q}{2^t}
\]

Ví dụ với **một triệu lần thử** (chỉ để định lượng, không phải hạn mức đề xuất):

| Độ dài tag | Xác suất gần đúng với \(q=10^6\) | Ý nghĩa |
| --- | ---: | --- |
| 32 bit | \(2{,}33 \times 10^{-4}\) | Không thể xem là an toàn cho API cần xác thực. |
| 64 bit | \(5{,}42 \times 10^{-14}\) | Nhỏ trong ví dụ này nhưng kém bền vững hơn trước khối lượng thử lớn, nhiều key, thời gian dài. |
| 128 bit | \(2{,}94 \times 10^{-33}\) | Rất nhỏ dưới các giả định nêu trên. |
| 256 bit | \(8{,}64 \times 10^{-72}\) | Rất nhỏ đối với đoán ngẫu nhiên; không phải đánh giá toàn bộ hệ thống. |

Các phép tính trên **chỉ mô tả tấn công đoán tag ngẫu nhiên**, không thể dùng làm đảm bảo an toàn tổng thể. Nếu shared secret yếu hoặc bị lộ, cách tính này không còn thích hợp. Nếu canonical request bỏ method/URI/tenant, attacker có thể sửa trường đó mà **không cần đoán tag**. Nếu một request đã ký hợp lệ bị replay, signature vẫn đúng dù tag dài 256 bit.

**Lưu ý mật mã:** độ khó tìm va chạm tổng quát của SHA-256 thường được nêu cỡ `2^128`, nhưng điều đó **không có nghĩa** kẻ tấn công giả mạo HMAC-SHA256 full tag với xác suất `2^-128` mỗi lần đoán. Collision resistance của hash không khóa và unforgeability của MAC có khóa là các khái niệm khác nhau. HMAC còn phụ thuộc cấu trúc, khóa và mô hình tấn công, vì thế không thể suy ra “độ mạnh thật” chỉ từ độ dài digest.

**Giới hạn thử online:** rate limit, quota, giám sát và giới hạn tuổi thọ khóa giúp giảm cơ hội thử tag. Chúng không thay thế key ngẫu nhiên hoặc tag đủ dài.

## 5. Hợp đồng ký phải cố định signature length

Một hợp đồng minh họa cho API thanh toán:

~~~text
HMAC-V1
alg:hmac-sha256
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

Các dòng được nối bằng **LF (byte 0A)**, **không có LF cuối** rồi mã hóa UTF-8. `X-Content-SHA256` là hex chữ thường của SHA-256 trên đúng **byte body được gửi**, và trường hash đó được HMAC bảo vệ. Method, raw path/raw query, audience, client/key ID, timestamp, nonce và Content-Type đều có nghĩa bảo mật nên phải nhất quán trong hai phía.

Hợp đồng quyết định:

1. **Thuật toán:** HmacSHA256, không fallback sang HmacSHA1/MD5 hoặc thuật toán tùy ý do request khai báo.
2. **Số byte tag:** 32 (full tag). Nếu dùng phiên bản contract khác có truncation, phải công bố rõ **16 byte đầu** và không chấp nhận độ dài tùy biến.
3. **Wire encoding:** ví dụ **Base64 chuẩn có padding**, nên 32 byte phải được biểu diễn thành 44 ký tự Base64 canonical.
4. **Header mang tag:** ví dụ `X-Signature` có **đúng một giá trị**; từ chối header thiếu, lặp, mơ hồ hoặc sai định dạng. Giá trị Base64 được decode thành byte trước khi so sánh.
5. **Key selection:** chỉ chọn key từ (client ID, key ID) đã cấp và chính sách server; key phải ràng buộc đúng algorithm, tag bytes, audience và thời hạn hiệu lực.
6. **Canonical input:** verifier **tự xây** từ request thực nhận ở trust boundary đáng tin và đúng thứ tự/encoding đã định nghĩa, không tin một chuỗi canonical được client tự gửi.

Không nên để client gửi `X-Signature-Length: 8` rồi verifier thay chính sách full tag bằng 8 byte. Nếu contract hỗ trợ nhiều phiên bản, mỗi phiên bản và key record phải có **tag length cố định, kiểm tra trước khi xử lý**, và quy trình bỏ phiên bản cũ.

### Signature length có nằm trong canonical request không?

Nếu **toàn bộ contract có version cố định** (`HMAC-V1` luôn HmacSHA256, full 32 byte, Base64 chuẩn), tag length đã được ràng buộc gián tiếp bởi version và policy của verifier. Không cần một trường `signature-length` có thể thay đổi.

Nếu giao thức thực sự cho phép nhiều độ dài tag, cần định nghĩa lựa chọn **không thể bị hạ cấp**: gắn tag policy với key ID/algorithm và phiên bản được server cấu hình, và nếu có trường negotiation thì trường đó cũng phải nằm trong dữ liệu được xác thực. Không dùng giá trị chưa xác thực do client khai báo để tự do hạ thấp độ dài trước khi xác minh.

## 6. Java 17: ký, biểu diễn và kiểm tra đúng độ dài

Đoạn mã sau tập trung vào tính toán/kiểm tra MAC, dùng test vector **RFC 4231 test case 1**: key gồm 20 byte `0x0b` và thông điệp ASCII `Hi There`. Đây là **key test công khai**, không dùng làm secret thực tế.

Ví dụ triển khai hai policy **riêng biệt**: full 32 byte và truncated 16 byte. Một verifier đã chọn full tag sẽ từ chối 16 byte, kể cả khi prefix đúng. Mục đích minh họa cả cách biểu diễn Base64 lẫn cách khóa độ dài bằng chính sách.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacSignatureLengthExample {
    private static final String ALGORITHM = "HmacSHA256";
    private static final int FULL_TAG_BYTES = 32;
    private static final int SHORT_TAG_BYTES = 16;

    static byte[] hmacSha256(byte[] secret, byte[] message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(secret, ALGORITHM));
        return mac.doFinal(message);
    }

    // Server policy quy định tagBytes là 32 hoặc 16 theo contract.
    static String sign(byte[] secret, byte[] canonicalBytes, int tagBytes)
            throws GeneralSecurityException {
        if (tagBytes != FULL_TAG_BYTES && tagBytes != SHORT_TAG_BYTES) {
            throw new IllegalArgumentException("Policy tag không hợp lệ");
        }
        byte[] full = hmacSha256(secret, canonicalBytes);
        byte[] toSend = Arrays.copyOf(full, tagBytes);
        return Base64.getEncoder().encodeToString(toSend);
    }

    // Chỉ dùng expectedTagBytes từ cấu hình server, KHÔNG lấy từ request.
    static boolean verify(byte[] secret, byte[] canonicalBytes,
            String encodedSignature, int expectedTagBytes)
            throws GeneralSecurityException {
        if (expectedTagBytes != FULL_TAG_BYTES &&
            expectedTagBytes != SHORT_TAG_BYTES) {
            return false;
        }
        if (encodedSignature == null) {
            return false;
        }

        final byte[] supplied;
        try {
            supplied = Base64.getDecoder().decode(encodedSignature);
        } catch (IllegalArgumentException invalidBase64) {
            return false;
        }
        if (supplied.length != expectedTagBytes) {
            return false; // Không cho phép giả mạo bằng prefix quá ngắn.
        }

        // Nếu contract yêu cầu Base64 chuẩn canonical có padding, kiểm tra
        // biểu diễn bằng cách encode lại. Đây là phép kiểm tra public text,
        // không phải phép so sánh hai giá trị MAC bí mật.
        String canonicalBase64 = Base64.getEncoder().encodeToString(supplied);
        if (!canonicalBase64.equals(encodedSignature)) {
            return false;
        }

        byte[] expectedFull = hmacSha256(secret, canonicalBytes);
        byte[] expected = Arrays.copyOf(expectedFull, expectedTagBytes);
        return MessageDigest.isEqual(expected, supplied);
    }

    public static void main(String[] args) throws Exception {
        byte[] testKey = new byte[20];
        Arrays.fill(testKey, (byte) 0x0b);
        byte[] message = "Hi There".getBytes(StandardCharsets.US_ASCII);

        byte[] full = hmacSha256(testKey, message);
        String expectedHex = "b0344c61d8db38535ca8afceaf0bf12b"
            + "881dc200c9833da726e9376c2e32cff7";
        if (!expectedHex.equals(HexFormat.of().formatHex(full))) {
            throw new AssertionError("RFC 4231 test vector không khớp");
        }

        String fullSignature = sign(testKey, message, FULL_TAG_BYTES);
        String shortSignature = sign(testKey, message, SHORT_TAG_BYTES);

        if (fullSignature.length() != 44 ||
            shortSignature.length() != 24) {
            throw new AssertionError("Độ dài Base64 không đúng");
        }
        if (!verify(testKey, message, fullSignature, FULL_TAG_BYTES)) {
            throw new AssertionError("Full tag phải hợp lệ");
        }
        if (!verify(testKey, message, shortSignature, SHORT_TAG_BYTES)) {
            throw new AssertionError("Tag 16 byte hợp lệ theo policy riêng");
        }
        if (verify(testKey, message, shortSignature, FULL_TAG_BYTES)) {
            throw new AssertionError("Full-tag verifier phải từ chối prefix");
        }
        String changed = "Hi There!";
        if (verify(testKey, changed.getBytes(StandardCharsets.US_ASCII),
                fullSignature, FULL_TAG_BYTES)) {
            throw new AssertionError("Không chấp nhận message đã bị sửa");
        }
        if (verify(testKey, message, "not@base64!", FULL_TAG_BYTES)) {
            throw new AssertionError("Không chấp nhận Base64 sai");
        }

        System.out.println("PASS: RFC 4231, encoding, tag length, tampering");
    }
}
~~~

**Giải thích từng kiểm tra quan trọng:**

- `Mac.getInstance("HmacSHA256")` và `SecretKeySpec` tính HMAC có khóa; `doFinal` trả **32 byte**.
- `Arrays.copyOf(full, 16)` thực hiện truncation **chỉ theo policy**; nếu dịch vụ triển khai full tag, bỏ lựa chọn short tag khỏi code production.
- `Base64.getDecoder().decode` đưa chữ ký về byte để kiểm tra số byte thật. Kiểm tra `encodedSignature.length() == 44` **một mình** không đủ, vì một chuỗi dài 44 ký tự có thể có ký tự sai hoặc biểu diễn không hợp lệ.
- Kiểm tra **re-encode** minh họa cách bắt buộc Base64 chuẩn canonical có padding. Nếu contract chọn Base64URL thì phải thay đồng bộ cả encoder, decoder và quy tắc độ dài.
- `MessageDigest.isEqual` dùng để so sánh byte MAC theo thời gian tương đối ổn định; kiểm tra độ dài trước khi so sánh là hợp lý vì tag length **không phải bí mật** mà là policy công khai.
- 20 byte `0x0b` của test vector RFC **không** đại diện cho yêu cầu entropy của secret production; hệ thống mới nên dùng secret đủ ngẫu nhiên được quản lý qua key store, ví dụ 32 byte từ CSPRNG.

Đoạn mã tập trung vào kiểm chứng độ dài tag; verifier HTTP thực tế còn phải parse request, tự dựng canonical, kiểm tra timestamp/nonce, key scope, chống replay và phân quyền. Không lấy trực tiếp tham số `expectedTagBytes` từ header do bên gọi cung cấp.

## 7. Trong HTTP request thật: ký gì và ký ở đâu?

Các giá trị khác nhau có thể bị sửa trong quá trình request đi qua proxy/gateway:

~~~mermaid
flowchart LR
    A["Client chuẩn bị raw URI, signed headers, body bytes"] --> B["SHA-256(body bytes)"]
    B --> C["Canonical request bytes"]
    C --> D["HMAC-SHA256 với secret"]
    D --> E["32-byte tag -> Base64 -> X-Signature"]
    E --> F["Proxy / gateway"]
    F --> G["Verifier: dựng canonical và kiểm tra full tag"]
    G --> H["Timestamp + nonce, sau đó phân quyền"]
~~~

Hợp đồng ký trong mục 5 cần được triển khai đúng tại **client lẫn verifier**. Những lỗi phổ biến dù signature dài 32 byte và secret an toàn:

| Hiện tượng | Lý do | Biện pháp |
| --- | --- | --- |
| Chữ ký Base64 dài 44 ký tự nhưng không verify | Cùng độ dài không đảm bảo cùng nội dung; key/byte canonical khác nhau | So sánh digest/body bytes, method, raw URI, header và key ID theo contract. |
| Server dùng hex còn client gửi Base64 | Hai encoding của cùng byte bị nhầm với nhau | Cố định wire encoding, reject sai định dạng thay vì đoán. |
| Proxy đổi thứ tự query hoặc decode `%2F` | Request target khác khi dựng canonical | Xác minh ở trust boundary phù hợp, trước rewrite hoặc bảo vệ metadata gốc. |
| Gateway thêm hoặc sửa Content-Type/Content-Encoding | Header đã ký hoặc body representation thay đổi | Ký giá trị cuối cùng theo contract; không tự ý biến đổi sau ký. |
| Body được serialize lại sau khi ký | SHA-256 body bytes thay đổi | Serialize một lần; hash và gửi đúng byte đó. |
| Client khai báo signature-length=8 | Verifier thiếu policy và có thể nhận prefix quá ngắn | Lấy tag length từ server key/contract policy, không tin header. |
| Request có hai X-Signature | Proxy/backend chọn giá trị khác nhau | Reject duplicate/mơ hồ trước xác minh. |
| Chữ ký hợp lệ nhưng request được phát lại | HMAC không tự ngăn replay | Timestamp và nonce được ký; nonce store nguyên tử dùng chung. |

Nếu proxy do kẻ tấn công kiểm soát và thấy plaintext, nó có thể **đọc** request và replay bản sao chữ ký hợp lệ, dù không biết secret. HMAC không mã hóa nội dung hay xác thực response; **HTTPS đến điểm tin cậy thích hợp** vẫn cần thiết. Không tin `X-Verified`, `X-Authenticated-User` hay `X-Original-URI` do proxy ngoài kiểm soát tự khai báo. Gateway chỉ có thể chuyển tiếp identity “đã xác minh” cho backend qua kênh nội bộ được xác thực và không có đường bypass.

## 8. Replay protection, key rotation và phân quyền

### 8.1. Tag dài không thay thế chống replay

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy giữ bản sao
    participant V as Verifier
    participant N as Nonce store
    C->>P: Request + timestamp + nonce + tag 32 byte
    P->>V: Forward request hợp lệ
    V->>N: Claim nonce nguyên tử
    N-->>V: Chưa tồn tại
    V-->>P: Chấp nhận sau khi xác minh MAC
    P->>V: Replay nguyên request, tag vẫn đúng
    V->>N: Claim lại cùng nonce
    N-->>V: Đã tồn tại
    V-->>P: Từ chối replay
~~~

Server phải kiểm tra timestamp trong cửa sổ có chính sách (ví dụ ±300 giây, **không phải hằng số bắt buộc của HMAC**), chỉ nhận nonce từ request có chữ ký hợp lệ và **claim nonce nguyên tử** trên store chia sẻ giữa các replica. Nonce 128 bit ngẫu nhiên tạo bằng CSPRNG giúp xác suất trùng tự nhiên thấp, nhưng không thay thế bước server ghi nhận nonce.

Với giao dịch có side effect, một retry được **ký lại** bằng timestamp/nonce mới có thể là request hoàn toàn hợp lệ mà vẫn thực hiện nghiệp vụ hai lần khi response đầu mất. Cần **idempotency key** được ràng buộc bằng chữ ký và xử lý đúng trong logic giao dịch.

### 8.2. Key rotation và policy tag

Gắn chính sách với từng cặp **(client ID, key ID)**:

~~~text
clientId       = partner-42
keyId          = key-2026-11
algorithm      = HmacSHA256
signatureBytes = 32
encoding       = base64-standard-padded
audience       = payments-api
keyStatus      = ACTIVE
~~~

Khi rotate, cấp secret và key ID mới qua kênh an toàn; verifier có thể cho phép cặp key cũ/mới trong thời gian chuyển đổi đã định, rồi thu hồi key cũ. Key ID và thuật toán phải được ràng buộc với phạm vi dịch vụ và thời gian hiệu lực. Không dùng key ID sai để fallback sang nhiều thuật toán hoặc độ dài tag khác nhau. Nếu một hệ thống đang di trú từ tag cắt 16 byte sang full 32 byte, hãy dùng **version/key policy rõ ràng** và chặn việc client tự hạ cấp về 16 byte ngoài giai đoạn được phép.

**Độ dài key khác độ dài tag:** secret 32 byte và tag 32 byte có thể cùng kích thước trong HMAC-SHA256, nhưng chúng có hai vai trò hoàn toàn khác nhau. Secret phải được bảo vệ; tag được phép xuất hiện công khai trên đường truyền. Độ dài tag cố định không chứng minh key có đủ entropy, được giữ an toàn hay chưa hết hạn.

### 8.3. Authentication không tự cấp quyền

Một chữ ký đúng chỉ xác nhận rằng request phù hợp với shared secret và các byte đã ký. Nó **không tự cho phép** client đọc hóa đơn của client khác, sửa tenant hoặc gọi endpoint quản trị. Sau bước xác minh HMAC, backend vẫn cần kiểm tra quyền theo client identity, scope, action, tenant và tài nguyên đích. Tag 512 bit cũng không làm thay bước kiểm tra này.

## 9. Thực hành kiểm thử signature length

Hãy dùng secret test, tạo canonical HTTP request ổn định và viết verifier tự dựng canonical tại trust boundary. Dùng các giá trị timestamp/nonce mới ở mỗi request test độc lập; riêng test replay phải gửi lại đúng nonce cũ. Bảng dưới đây mô tả kết quả mong đợi.

| Ca kiểm thử | Đầu vào hoặc thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Độ dài full HMAC-SHA256 | 32 byte MAC | Hex 64 ký tự; Base64 chuẩn 44 ký tự; Base64URL không padding 43 ký tự. |
| Độ dài truncated 16 byte | Cắt 16 byte đầu tag HMAC-SHA256 | 16 byte; hex 32; Base64 chuẩn 24; chỉ hợp lệ nếu policy cho phép. |
| RFC 4231 case 1 | Key 20 byte 0x0b, message “Hi There” | Full tag bằng hex b0344c61…2e32cff7. |
| Full-tag policy | Gửi đúng 32 byte tag | Được xét HMAC; kết quả còn tùy key/canonical. |
| Prefix attack | Gửi 1, 8 hoặc 16 byte đầu HMAC tới verifier yêu cầu 32 byte | **Từ chối** vì sai độ dài, kể cả prefix trùng. |
| Base64 không canonical | Bỏ `=`, dùng Base64URL hoặc thêm ký tự ngoài bảng | Từ chối nếu hợp đồng yêu cầu Base64 chuẩn có padding. |
| Hex thay vì Base64 | Gửi 64 ký tự hex vào X-Signature | Từ chối theo encoding đã chọn. |
| Không có/duplicate header chữ ký | Thiếu X-Signature hoặc có hai giá trị | Từ chối request sai contract/mơ hồ. |
| Thay method/path/query/body | Giữ tag cũ sau khi sửa dữ liệu đã ký | Từ chối HMAC. |
| Thay key ID/algorithm | Gửi tag của key A nhưng khai key B hoặc HMAC-SHA1 | Từ chối vì key/algorithm policy không khớp. |
| Replay trong cửa sổ timestamp | Gửi lại đúng request, tag 32 byte vẫn hợp lệ | Từ chối theo nonce đã claim. |
| Proxy rewrite/HTTP/2 | Đổi raw path/query hoặc chuyển protocol khiến target bị diễn giải khác | Verify và route dùng cùng nghĩa theo contract; reject dạng mơ hồ. |
| Authorization | Client ký đúng nhưng truy cập tenant khác | Authentication PASS, authorization DENY. |

### Bài tập tình huống

**Bài 1 — Dài bao nhiêu?** Một API dùng HMAC-SHA256 nhưng tài liệu ghi “signature dài 44 byte”. Đây có phải độ dài MAC không? Hãy giải thích 32 byte raw tag, 44 ký tự Base64 và trường hợp 43 ký tự Base64URL không padding.

**Bài 2 — Prefix hợp lệ?** Verifier tính HMAC-SHA256 đủ 32 byte nhưng cắt `expected` bằng độ dài byte mà client gửi để so sánh. Vì sao attacker có thể khai thác? Hãy sửa thiết kế để chấp nhận **chỉ** 32 byte hoặc **chỉ** 16 byte theo phiên bản giao thức do server quyết định.

**Bài 3 — Giảm băng thông.** Đội phát triển muốn tiết kiệm 20 ký tự trên header bằng truncation từ 32 byte xuống 16 byte. Những điều kiện contract, key management, giới hạn thử và đánh giá rủi ro nào phải có? Tại sao không nên chọn 4 byte?

**Bài 4 — Chữ ký đúng mà giao dịch sai.** Client ký body nhưng không ký query `currency=VND`; proxy đổi nó thành `currency=USD`. Độ dài tag có giải quyết được lỗ hổng này không? Hãy bổ sung trường ký và điểm xác minh qua gateway.

**Bài 5 — Replay và rotation.** Server hỗ trợ key cũ tag 16 byte và key mới tag 32 byte. Thiết kế (client ID, key ID) → algorithm, tag bytes, audience và thời gian hiệu lực như thế nào để ngăn downgrade? Replay request có tag 32 byte cần kiểm soát thêm điều gì?

## 10. Checklist triển khai

- [ ] Hợp đồng ký ghi rõ **thuật toán**, **số byte tag**, **Base64/hex và padding**, phiên bản và thứ tự canonical fields.
- [ ] Với API mới, cân nhắc **HMAC-SHA256 full 32 byte** làm mặc định; không lấy ký tự Base64 làm độ dài mật mã.
- [ ] Tag ngắn hơn chỉ được dùng khi **policy server cố định rõ** và đã đánh giá rủi ro; không dùng độ dài do client khai báo.
- [ ] Verifier Base64 decode, kiểm tra **chính xác số byte**, kiểm tra encoding theo contract và so sánh MAC bytes bằng hàm phù hợp.
- [ ] Secret được tạo đủ entropy và lưu trong secret manager; key ID chọn đúng algorithm/tag policy/audience; có rotation và thu hồi.
- [ ] Canonical request bảo vệ method, raw URI/query, header nghiệp vụ và body hash/bytes, với quy tắc delimiter và charset thống nhất.
- [ ] Đặt verifier tại trust boundary đáng tin, kiểm thử proxy rewrite, header trùng, HTTP/1.1↔HTTP/2 và body encoding.
- [ ] Timestamp và nonce được ký, được server kiểm tra và ghi nhận bằng nonce store nguyên tử; idempotency bảo vệ side effect.
- [ ] HTTPS, rate limits, monitoring và phân quyền được triển khai riêng; HMAC tag dài không thay các kiểm soát này.

**Ghi nhớ:** **Signature length** trong HMAC là số bit/byte của **tag đã được server cho phép**, khác với độ dài chuỗi Base64/hex. HMAC-SHA256 đầy đủ có **32 byte**, thường mã hóa thành **44 ký tự Base64 chuẩn**. Việc cắt tag phải là quyết định cố định của hợp đồng ký; verifier không bao giờ tự so sánh prefix theo độ dài mà bên gọi cung cấp. Độ dài chữ ký chỉ là một phần của bảo mật request: còn cần khóa đủ mạnh, canonical request đúng, chống replay, quản lý key và phân quyền.
