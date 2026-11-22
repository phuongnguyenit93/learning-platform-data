# 3.2 Base64, HexFormat và sự khác biệt giữa biểu diễn dữ liệu với bảo vệ bí mật

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **encoding (biểu diễn/mã hóa dữ liệu)** khác **encryption (mã hóa bảo mật)**, hashing, MAC và chữ ký số như thế nào.
- Hiểu cơ chế chuyển byte thành Base64 và hexadecimal (hex), chi phí kích thước và tình huống dùng thích hợp.
- Sử dụng đúng **java.util.Base64** và **java.util.HexFormat** (Java 17+) để mã hóa biểu diễn, giải mã và kiểm tra round-trip; phân biệt Base64 Basic, URL-safe và MIME.
- Xử lý đúng byte, charset UTF-8, đầu vào không hợp lệ, dữ liệu nhị phân và nguy cơ canonicalization.
- Nhận diện các sai lầm bảo mật: coi Base64/hex là bí mật, đưa secret đã encode vào log/URL, hiểu sai Basic Authentication, JWT hoặc chuỗi hash.

## 1. Bắt đầu từ byte, không bắt đầu từ chuỗi hiển thị

Máy tính lưu và truyền thông tin dưới dạng **byte**. Khi cần đưa byte vào môi trường thiên về văn bản (JSON, cấu hình, HTTP header, log chẩn đoán, QR code, tệp text, giao thức chỉ chấp nhận ký tự in được), ta dùng một cách **biểu diễn** byte thành chuỗi có thể đọc/truyền an toàn theo quy tắc cụ thể.

Ví dụ, chuỗi ký tự **Java!** theo UTF-8 tạo năm byte:

~~~text
Text:                 Java!
UTF-8 bytes (hex):    4a 61 76 61 21
Base64 của các byte:  SmF2YSE=
Hex của các byte:     4a61766121
~~~

Cả **SmF2YSE=** và **4a61766121** đều biểu diễn **cùng năm byte gốc**. Người khác chỉ cần biết quy tắc Base64/hex là có thể khôi phục chính xác năm byte đó. Không cần mật khẩu hay khóa bí mật.

Cần phân biệt hai tầng chuyển đổi:

~~~text
Ký tự Unicode --[UTF-8 encode]--> byte[]
                                  |
                           +------+------+
                           |             |
                        [Base64]       [Hex]
                           |             |
                          text          text
                           |             |
                         decode        parse
                           |             |
                           +------v------+
                                  |
                                byte[]
                        --[UTF-8 decode]--> Ký tự Unicode
~~~

**UTF-8** là cách biến ký tự thành byte; **Base64/hex** biến byte thành ký tự từ bảng chữ cái giới hạn. Chúng giải quyết các vấn đề tương thích biểu diễn, không giải quyết việc giữ bí mật. Byte của dữ liệu nhị phân bất kỳ, chẳng hạn ảnh, chữ ký, nonce hoặc ciphertext, không nhất thiết là văn bản UTF-8 hợp lệ: đừng tùy tiện chuyển byte[] bất kỳ thành String để “đọc” nội dung.

### 1.1 Bốn nhóm thao tác thường bị nhầm

| Thao tác | Mục tiêu | Đầu vào → đầu ra | Cần khóa bí mật? | Có khôi phục bản gốc không? |
| --- | --- | --- | --- | --- |
| **Encoding** (Base64, hex, UTF-8) | Đổi cách biểu diễn cho lưu/truyền/hiển thị | Byte ↔ ký tự theo quy tắc | Không | Có, khi đúng định dạng/charset |
| **Encryption** (ví dụ AES-GCM) | Giữ bí mật dữ liệu, thường có xác thực toàn vẹn | Plaintext → ciphertext | Có | Có, nếu có khóa và tham số hợp lệ |
| **Hash** (ví dụ SHA-256) | Tạo dấu vân tay có độ dài cố định từ dữ liệu | Byte → digest | Không đối với hash thông thường | Không có phép giải mã ngược; dữ liệu yếu có thể bị đoán/brute-force |
| **MAC/chữ ký số** (HMAC, Ed25519, v.v.) | Kiểm tra tính toàn vẹn/xác thực theo mô hình khóa | Dữ liệu + khóa → mã xác thực/chữ ký | Có khóa bí mật hoặc private key để tạo | Không dùng để khôi phục dữ liệu gốc |

**Một chuỗi trông như ký tự ngẫu nhiên chưa chắc được bảo mật.** Mức độ khó đọc bằng mắt không phải thuộc tính an toàn.

## 2. Base64 hoạt động như thế nào?

### 2.1 Cơ chế 6 bit và padding

Base64 đọc luồng bit theo nhóm **6 bit**, mỗi nhóm ánh xạ vào một trong 64 ký tự. Ba byte chứa 24 bit được biểu diễn thành bốn ký tự Base64. Vì vậy:

- Ba byte đầu vào → bốn ký tự.
- Một byte đầu vào → hai ký tự dữ liệu và thường hai ký tự **==** làm padding.
- Hai byte đầu vào → ba ký tự dữ liệu và thường một ký tự **=**.
- Nếu đầu vào chia hết cho ba byte thì không cần padding.

Với **Base64 Basic có padding**, độ dài đầu ra theo ký tự là **4 × ceil(số_byte / 3)**. Đây là mở rộng kích thước khoảng 33,3% với dữ liệu đủ lớn, cộng tác động của padding khi dữ liệu ngắn. Không được dùng độ dài String của một chuỗi Unicode thay cho số byte khi tính kích thước.

**Padding không chứa bí mật**; nó làm rõ phần byte cuối của dữ liệu. Một số biến thể bỏ padding vì quy tắc giao thức đã cho phép bên nhận tự suy ra. Thêm/bớt padding không biến Base64 thành phương tiện mã hóa bảo mật.

### 2.2 Ba biến thể trong Java

Java cung cấp ba cặp encoder/decoder chính ở **java.util.Base64**:

| Biến thể | Java API | Alphabet/đặc tính | Tình huống |
| --- | --- | --- | --- |
| **Basic** | Base64.getEncoder() / getDecoder() | A–Z, a–z, 0–9, **+** và **/**; padding **=** khi cần; không chèn xuống dòng | JSON, cấu hình, dữ liệu nhị phân trong text không hạn chế dấu + và / |
| **URL-safe** | Base64.getUrlEncoder() / getUrlDecoder() | Dùng **-** thay **+**, **_** thay **/**; có thể bỏ padding bằng withoutPadding() | Thành phần URL, token định dạng Base64URL, tên/ID theo giao thức |
| **MIME** | Base64.getMimeEncoder() / getMimeDecoder() | Có thể ngắt dòng (thông thường 76 ký tự, CRLF); decoder MIME chấp nhận một số ký tự ngoài alphabet và bỏ qua chúng | Nội dung MIME/email theo đặc tả phù hợp |

**Không tráo biến thể một cách tùy tiện.** Base64 Basic có dấu **+** và **/**: dấu **+** có thể bị xử lý thành khoảng trắng trong một số dạng query/form encoding, còn **/** có ý nghĩa phân tách path. Base64URL thay hai ký tự đó, nhưng vẫn không tự đem lại tính bí mật, chống sửa đổi hay chống phát lại.

**MIME decoder không thích hợp làm bộ kiểm tra nghiêm ngặt cho token bảo mật**, vì quy tắc bỏ qua ký tự của nó rộng hơn Basic/URL. Chọn decoder theo giao thức; đặt giới hạn độ dài và kiểm tra nội dung hợp lệ trước khi sử dụng.

### 2.3 Base64 không gắn với kiểu dữ liệu gốc

Base64 chỉ biết **byte[]**, không biết byte đó là ảnh PNG, JSON UTF-8, một khóa AES, một chữ ký số hay dữ liệu ngẫu nhiên. Muốn khôi phục ý nghĩa, ứng dụng phải biết từ **giao thức/metadata**:

- Byte nào đang được biểu diễn?
- Sau khi decode có được xem là UTF-8, protobuf, ảnh hay ciphertext?
- Cần bản mã được giải mã bằng khóa nào, nonce nào, thuật toán nào?
- Payload có được xác thực và kiểm tra quyền trước khi tin tưởng không?

Không dùng vẻ ngoài Base64 làm bằng chứng dữ liệu đã được mã hóa, ký hay kiểm tra toàn vẹn.

## 3. Hexadecimal và Java 17 HexFormat

**Hex** dùng hệ cơ số 16: mỗi **nibble 4 bit** biểu diễn bằng một chữ số từ 0–9, a–f. Một byte 8 bit tương ứng **hai chữ số hex**.

Ví dụ:

~~~text
Byte nhị phân:     1111 1011
Hex:               FB
Byte nhị phân:     0000 0000
Hex:               00
Ba byte:           FB FF 00
Hex liền mạch:     fbff00
Hex có dấu phân tách: FB:FF:00
~~~

Hex thích hợp để đọc dump byte, in giá trị hash, định danh, fingerprint, nonce/IV và địa chỉ dưới dạng văn bản. Khi dùng hex nguyên bản không thêm separator, kích thước **đúng gấp đôi số byte**: 32 byte → 64 ký tự hex. Hex thường dài hơn Base64, đổi lại dễ đối chiếu byte và đọc bằng mắt.

Java 17 đưa vào **java.util.HexFormat**, tránh tự viết vòng lặp đổi byte sang hex hoặc phụ thuộc thư viện ngoài cho thao tác cơ bản.

- **HexFormat.of().formatHex(bytes):** tạo chuỗi hex liên tục, mặc định chữ thường.
- **HexFormat.of().parseHex(text):** chuyển chuỗi hex hợp lệ về byte[], mặc định không có dấu phân tách.
- **HexFormat.of().withUpperCase():** chọn A–F viết hoa khi format.
- **HexFormat.ofDelimiter(":"):** dùng dấu **:** giữa các byte; parse và format cần thống nhất định dạng đã định.
- **formatHex** không tự thêm ký hiệu **0x**, dấu cách hay các ký tự tùy ý; định dạng ấy phải được quy định và xử lý rõ ràng.

Đầu vào lẻ số chữ số, ký tự không thuộc hex hoặc dấu phân tách không phù hợp sẽ bị từ chối (ví dụ IllegalArgumentException). Đừng âm thầm bỏ các ký tự lỗi, cắt ngắn hoặc tự sửa đầu vào chưa rõ quy tắc.

## 4. Thực hành Java 17+: round-trip Base64, Base64URL và HexFormat

Tạo tệp **RepresentationDemo.java** (lưu UTF-8):

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;

public class RepresentationDemo {
    public static void main(String[] args) {
        byte[] textBytes = "Java!".getBytes(StandardCharsets.UTF_8);

        String basic = Base64.getEncoder().encodeToString(textBytes);
        String hex = HexFormat.of().formatHex(textBytes);

        byte[] fromBase64 = Base64.getDecoder().decode(basic);
        byte[] fromHex = HexFormat.of().parseHex(hex);

        System.out.println("Base64: " + basic);
        System.out.println("Hex: " + hex);
        System.out.println("Base64 round-trip: "
                + Arrays.equals(textBytes, fromBase64));
        System.out.println("Hex round-trip: "
                + Arrays.equals(textBytes, fromHex));
        System.out.println("Text round-trip: "
                + new String(fromBase64, StandardCharsets.UTF_8));

        // Các byte này có bit 1 cao, không phải text UTF-8 để đọc trực tiếp.
        byte[] binary = {(byte) 0xFB, (byte) 0xFF, 0x00};

        System.out.println("Basic binary: "
                + Base64.getEncoder().encodeToString(binary));
        System.out.println("URL binary: "
                + Base64.getUrlEncoder().encodeToString(binary));
        System.out.println("Hex binary: "
                + HexFormat.ofDelimiter(":")
                        .withUpperCase()
                        .formatHex(binary));
        System.out.println("Base64URL one byte: "
                + Base64.getUrlEncoder()
                        .withoutPadding()
                        .encodeToString(new byte[] {(byte) 0xFF}));
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 RepresentationDemo.java
java RepresentationDemo
~~~

Stdout chính xác:

~~~text
Base64: SmF2YSE=
Hex: 4a61766121
Base64 round-trip: true
Hex round-trip: true
Text round-trip: Java!
Basic binary: +/wA
URL binary: -_wA
Hex binary: FB:FF:00
Base64URL one byte: _w
~~~

Giải thích:

1. **getBytes(StandardCharsets.UTF_8)** xác định rõ cách chuyển text thành byte. Khi khôi phục text cũng dùng UTF-8 tương ứng; không dựa vào default charset của môi trường.
2. **encodeToString** tạo chuỗi biểu diễn từ byte; **decode** trả lại byte[]. Hai phép biến đổi là nghịch đảo nhau đối với dữ liệu hợp lệ.
3. **formatHex/parseHex** thực hiện cặp biến đổi tương tự, nhưng dùng hai chữ số hex cho mỗi byte. Kết quả Arrays.equals cho thấy các byte giữ nguyên.
4. Với byte **FB FF 00**, Base64 Basic là **+/wA**, Base64URL là **-_wA**; khác alphabet nhưng đều biểu diễn cùng ba byte.
5. Một byte **FF** thành **_w** khi Base64URL bỏ padding; nếu dùng encoder có padding, kết quả là **_w==**. Padding không phải một cơ chế an toàn.
6. **HexFormat.ofDelimiter(":").withUpperCase()** định dạng ba byte thành **FB:FF:00**; nếu cần parse dạng này, dùng HexFormat.ofDelimiter(":").parseHex(...) theo đúng quy tắc.

**Lưu ý về bộ nhớ:** Base64/hex chuyển dữ liệu thành String sẽ tạo bản sao mới. Nếu dữ liệu gốc là secret thì bản sao cũng là secret. Không in secret thật ra log để “kiểm tra format”.

## 5. Vì sao Base64/Hex không bảo vệ bí mật?

**Encoding không có khóa.** Kẻ nhận hoặc đọc được chuỗi có thể giải mã bằng thuật toán công khai. Ví dụ một chuỗi cấu hình:

~~~text
apiKeyBase64: ZGVtby1zZWNyZXQ=
~~~

Chỉ cần Base64 decode là nhận được văn bản **demo-secret**. Việc đặt tên biến **encryptedPassword**, thêm tiền tố bí hiểm hoặc mã hóa Base64 nhiều lần không làm xuất hiện tính bí mật.

Một chuỗi hex của token, số thẻ, mật khẩu, private key hay dữ liệu cá nhân cũng **nhạy cảm ngang với byte gốc**. Chuỗi có thể dài và khó đọc nhưng vẫn khôi phục được nguyên vẹn. Không gửi vào log, analytics, URL, ticket hoặc nơi công khai chỉ vì “đã encode”.

### 5.1 Ví dụ Java 17+: encode có thể đảo ngược, digest chỉ được biểu diễn

Tạo **RepresentationVsProtectionDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;

public class RepresentationVsProtectionDemo {
    public static void main(String[] args) throws Exception {
        // Chỉ là chuỗi minh họa công khai, KHÔNG phải secret thật.
        byte[] sample = "demo-secret".getBytes(StandardCharsets.UTF_8);

        String encoded = Base64.getEncoder().encodeToString(sample);
        String recovered = new String(
                Base64.getDecoder().decode(encoded),
                StandardCharsets.UTF_8);

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(sample);
        String digestHex = HexFormat.of().formatHex(digest);
        String digestBase64 = Base64.getEncoder().encodeToString(digest);

        System.out.println("Recovered: " + recovered);
        System.out.println("SHA-256 bytes: " + digest.length);
        System.out.println("Digest hex chars: " + digestHex.length());
        System.out.println("Digest Base64 chars: " + digestBase64.length());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 RepresentationVsProtectionDemo.java
java RepresentationVsProtectionDemo
~~~

Stdout:

~~~text
Recovered: demo-secret
SHA-256 bytes: 32
Digest hex chars: 64
Digest Base64 chars: 44
~~~

Điều cần quan sát: mã Base64 có thể khôi phục **demo-secret** ngay lập tức. Ngược lại, **SHA-256** trả về digest 32 byte; hex hoặc Base64 chỉ là hai cách **hiển thị cùng digest**, hoàn toàn không thêm/bớt thuộc tính mật mã của hash.

Hash không có hàm “decrypt” để phục hồi chuỗi đầu vào. Tuy vậy dữ liệu có không gian đoán nhỏ, như mật khẩu yếu, vẫn có thể bị dò bằng cách hash các ứng viên và so sánh. **Không dùng SHA-256 thuần để lưu mật khẩu**; dùng cơ chế password hashing có salt riêng và tham số chi phí, ví dụ Argon2id/scrypt/bcrypt/PBKDF2 theo yêu cầu hệ thống.

### 5.2 Thứ cần mã hóa bảo mật thực sự

Nếu mục tiêu là **giữ bí mật**, hãy dùng **encryption** thích hợp như AES-GCM (AEAD) với khóa bí mật, nonce duy nhất trong phạm vi cùng khóa, xác thực tag và quản lý khóa đúng cách. Sau đó, khi một API chỉ cho phép văn bản, mới biểu diễn byte ciphertext bằng Base64 hoặc hex:

~~~text
Plaintext bytes
    |
[AES-GCM encrypt: secret key + nonce + AAD]
    |
Ciphertext + authentication tag (binary bytes)
    |
[Base64 / hex, chỉ để đóng gói văn bản]
    |
Text mang ciphertext qua JSON / cấu hình / giao thức
    |
[Base64 / hex decode]
    |
Ciphertext + tag (binary bytes)
    |
[AES-GCM decrypt + verify tag]
    |
Plaintext bytes
~~~

Decoder Base64 **không** kiểm tra tag GCM, không xác thực người gửi và không tự giải mã plaintext. Khóa, nonce, AAD và phiên bản định dạng phải được xử lý ở tầng mật mã. Đừng nhầm **có thể decode** với **có quyền decrypt**.

Với xác thực nguồn gốc và toàn vẹn, dùng **MAC** như HMAC hoặc **chữ ký số** theo đúng giao thức. Chuỗi Base64 chứa một chữ ký không trở thành chữ ký chỉ nhờ Base64; phải có quy trình ký và kiểm tra chữ ký thật sự.

## 6. Định dạng ở các ranh giới giao thức

### 6.1 HTTP Basic Authentication

Header HTTP Basic Authentication về mặt định dạng có thể chứa:

~~~text
Authorization: Basic <Base64 của user-id:password>
~~~

Chuỗi **user-id:password** có thể được lấy lại bằng Base64 decode. Vì vậy Basic Authentication **phải dùng cùng kết nối TLS được xác thực hợp lệ**, không được xem Base64 là bảo vệ mật khẩu. Tránh sao chép header Authorization sang log, error tracker hoặc debug dump. Xác thực thông tin đăng nhập và giới hạn quyền vẫn do hệ thống xử lý, không do Base64.

### 6.2 JWT/JWS/JWE và thông tin có thể nhìn thấy

Một **JWT dạng JWS compact** thường có ba đoạn Base64URL phân cách bằng dấu chấm: header.payload.signature. Payload có thể được decode và đọc mà không cần private key. **Chữ ký JWS giúp phát hiện sửa đổi và xác thực theo khóa**, nhưng không giữ bí mật payload. Nếu cần bí mật, dùng cơ chế mã hóa payload được thiết kế cho mục tiêu đó, ví dụ JWE hoặc mã hóa ở tầng ứng dụng phù hợp.

Không đặt mật khẩu, private key hay dữ liệu cá nhân nhạy cảm vào payload JWT ký thông thường rồi giả định đã “ẩn” vì nó là Base64URL. Việc decode token không tương đương xác minh chữ ký, issuer, audience, expiration và các điều kiện sử dụng token.

### 6.3 API JSON, byte[], key fingerprint và ciphertext

- **Nhị phân trong JSON:** Base64 thường gọn hơn hex. Metadata phải mô tả content type và encoding. Không tự đoán từ ký tự trông giống Base64.
- **Digest/fingerprint/debug:** hex thường trực quan khi đối chiếu từng byte. Các giá trị fingerprint có thể công khai hay nhạy cảm tùy ngữ cảnh.
- **Ciphertext lưu trong DB dạng text:** Base64/hex hỗ trợ cột text; vẫn cần encryption thật và lưu đủ metadata (key ID/version, nonce, tag, AAD nếu giao thức yêu cầu).
- **Raw binary:** nếu protocol/database hỗ trợ BLOB hoặc binary frame, có thể lưu/truyền byte trực tiếp, tránh overhead text encoding.
- **Token ngẫu nhiên:** token có entropy đủ cao có thể được tạo bằng SecureRandom rồi biểu diễn bằng Base64URL. **Độ khó đoán đến từ entropy của byte ngẫu nhiên**, không đến từ Base64URL. Token vẫn là bearer secret nếu ai sở hữu nó đều có thể sử dụng.

## 7. Unicode, charset và tính chuẩn hóa dữ liệu

Encoding nhị phân không quyết định cách mã hóa ký tự. Nếu dữ liệu ban đầu là String, phải **thống nhất charset** ở hai đầu, thường là UTF-8:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
~~~

Hai dòng trên minh họa một phần chương trình, cần biến text và import java.nio.charset.StandardCharsets khi sử dụng; đây không phải chương trình độc lập.

Lỗi kinh điển là dùng charset khác ở hai đầu, hoặc gọi **new String(rawBinaryBytes, UTF_8)** cho ciphertext/digest bất kỳ. Dữ liệu nhị phân có thể chứa chuỗi byte không phải UTF-8 hợp lệ, dẫn đến ký tự thay thế và mất khả năng round-trip. Với byte nhị phân, dùng Base64/hex trước rồi parse về byte.

Ngay cả khi dùng cùng UTF-8, văn bản nhìn giống nhau chưa chắc có **cùng byte**. Ví dụ chữ **é** có thể ở dạng một code point U+00E9 (UTF-8: **c3a9**) hoặc ký tự **e** cộng dấu U+0301 (UTF-8: **65cc81**). Nếu hệ thống ký số/hash trên byte, hai dạng đó tạo đầu vào khác nhau. Chỉ áp dụng Unicode normalization khi giao thức đã quy định nhất quán trước phép hash/ký; không tùy tiện chuẩn hóa dữ liệu đã ký hoặc thay đổi bytes sau khi xác thực.

### 7.1 Không lẫn lộn canonicalization với decoding

Một decoder có thể chấp nhận nhiều cách viết cùng biểu diễn byte, tùy variant và padding. Ví dụ một số chuỗi Base64 có hoặc không có dấu **=** cuối vẫn decode được cùng byte. Đừng mặc định **so sánh chuỗi encoded** là tương đương so sánh byte hoặc tương đương xác minh nội dung an toàn.

Với token/chữ ký, luôn tuân thủ chính xác **dạng canonical và signing input mà giao thức quy định**. Có giao thức ký trên byte payload đã canonicalize; có giao thức như JWS ký trên chính các đoạn encoded. Tự bỏ padding, đổi hoa/thường hex, thêm newline hay đổi Base64 Basic ↔ URL-safe trước khi xác minh có thể khiến chữ ký sai hoặc tạo lỗ hổng xử lý không thống nhất.

Nếu giao thức yêu cầu biểu diễn chuẩn, khi chấp nhận chuỗi ngoài hệ thống có thể thực hiện **decode rồi re-encode theo encoder canonical**, đối chiếu với đầu vào ban đầu và xử lý không khớp theo chính sách. Đây là bước kiểm tra định dạng, **không thay thế MAC/chữ ký số**.

## 8. Thiết kế parser và xử lý lỗi khi nhận dữ liệu không tin cậy

Hãy coi chuỗi Base64/hex nhận từ bên ngoài là **untrusted input** dù về mặt cú pháp nó đã hợp lệ. Quy trình khuyến nghị:

1. **Giới hạn kích thước chuỗi** trước khi decode để tránh cấp phát byte[] quá lớn. Với upload lớn, cân nhắc stream và giới hạn kích thước dữ liệu gốc ở tầng transport.
2. **Chọn đúng variant/định dạng**: Base64 Basic, URL-safe, MIME hoặc hex có delimiter. Ghi rõ trong hợp đồng API.
3. **Reject dữ liệu sai**: bắt IllegalArgumentException của decoder/parser tại ranh giới input và trả lỗi có kiểm soát, không in payload/secret ra log.
4. **Giới hạn kích thước sau decode** và kiểm tra cấu trúc: nonce, digest, key ID, độ dài field, media type, version.
5. **Xác thực/kiểm tra toàn vẹn và quyền truy cập** theo mô hình ứng dụng. Dữ liệu có thể decode không có nghĩa dữ liệu là đáng tin.
6. **Xử lý dữ liệu nhạy cảm thận trọng**: tránh lưu chuỗi mã hóa biểu diễn vào log, metric label, exception message, URL hoặc crash dump; giới hạn thời gian lưu trong bộ nhớ và bản sao không cần thiết.

Một số trường hợp lỗi cần tách bạch:

| Đầu vào | Kết quả mong đợi |
| --- | --- |
| Base64 Basic chứa ký tự không thuộc alphabet | Basic decoder báo lỗi; không lặng lẽ bỏ qua |
| Base64URL chứa dấu **+** hoặc **/** thay vì **-** hoặc **_** | Dùng URL decoder đúng chuẩn, không tự tráo ký tự thiếu quy định |
| Hex có số chữ số lẻ, ký tự ngoài 0–9/A–F/a–f | HexFormat.parseHex báo lỗi |
| Hex có dấu **:** nhưng parser mặc định không có delimiter | Chọn HexFormat.ofDelimiter(":") hoặc reject theo API contract |
| Decode thành byte[] nhưng loại nội dung không khớp (ví dụ cần 32 byte digest mà nhận 5 byte) | Reject sau kiểm tra ràng buộc kiểu/độ dài |
| Base64 decode hợp lệ nhưng ciphertext bị sửa hoặc sai tag | Tầng AEAD xác thực thất bại; không được tin plaintext |
| Token decode hợp lệ nhưng chữ ký sai hoặc token hết hạn | Tầng xác thực token phải reject |

**Không** tự sửa dữ liệu bằng cách bỏ ký tự tùy ý, chuyển charset nhiều lần hoặc cắt chuỗi đến khi parser chấp nhận. Chính sách tolerant parsing chỉ nên áp dụng khi đặc tả giao thức yêu cầu và đã đánh giá hệ quả bảo mật.

## 9. So sánh để chọn nhanh

| Tiêu chí | Base64 | Hex |
| --- | --- | --- |
| Đơn vị biểu diễn | Nhóm 6 bit → một ký tự | 4 bit → một ký tự |
| Kích thước text | Khoảng 4/3 số byte, có padding tùy variant | Đúng 2 lần số byte (không delimiter) |
| Dễ đọc từng byte | Khó hơn | Rất thuận tiện, mỗi byte hai chữ số |
| Ký tự đặc biệt | Basic có + / và =; URL-safe có - _ | Thường chỉ 0–9 a–f hoặc A–F |
| Java 17+ | java.util.Base64 | java.util.HexFormat |
| Bảo mật bí mật/toàn vẹn | Không có | Không có |
| Dùng phổ biến | JSON, binary-to-text, chuỗi token, ciphertext dạng text | Digest, fingerprint, log chẩn đoán an toàn, địa chỉ/buffer/debug |

Ví dụ với 32 byte dữ liệu bất kỳ:

- Hex liên tục: **64 ký tự**.
- Base64 Basic có padding: **44 ký tự** (có một dấu **=** cuối).
- Base64URL bỏ padding: **43 ký tự**.

**Lựa chọn dựa trên giao thức và khả năng đọc/chi phí kích thước**. Nếu dữ liệu cần giữ bí mật, hãy chọn và triển khai một cơ chế bảo vệ độc lập trước khi nghĩ đến định dạng biểu diễn.

## 10. Sai lầm phổ biến và cách sửa

1. **“Tôi đã Base64 encode mật khẩu/API key rồi nên có thể đưa lên Git.”** Sai: ai cũng decode được. Dùng secret manager/KMS, giữ bí mật và tránh commit; mật khẩu đăng nhập lưu bằng password hashing phù hợp.
2. **“Đưa bí mật vào URL sau Base64URL thì không ai biết.”** Sai: Base64URL không che dữ liệu. URL có thể vào browser history, access log, referrer, monitoring. Dùng kênh và cơ chế xác thực phù hợp, không đặt long-lived secret vào URL.
3. **“Chỉ cần HexFormat cho checksum là đủ chống giả mạo.”** Sai: hex là biểu diễn. Digest hash công khai không chứng minh người gửi; dùng HMAC/chữ ký số để chống sửa đổi có chủ đích.
4. **“Base64URL không có dấu + / nên chắc là dữ liệu được mã hóa an toàn.”** Sai: URL-safe chỉ đổi alphabet để phù hợp cú pháp.
5. **“Một JWT có ba đoạn Base64URL là nội dung không đọc được.”** Sai với JWS compact thông thường: header/payload đọc được sau decode, chữ ký xác thực chứ không giữ bí mật.
6. **“Đã decode Base64 thành công thì nội dung đáng tin.”** Sai: parse hợp lệ chỉ nói chuỗi có đúng dạng; mọi xác thực, phân quyền, schema validation vẫn cần thiết.
7. **“String.length() cho biết số byte cần mã hóa.”** Sai với Unicode/UTF-8; phải dùng độ dài của byte[] sau charset encode.
8. **“Ciphertext có thể đưa thẳng vào new String(bytes, UTF_8).”** Sai: ciphertext là byte nhị phân tùy ý. Dùng Base64/hex hoặc binary transport.
9. **“MIME decoder luôn là lựa chọn linh hoạt và an toàn nhất.”** Sai: nó có thể bỏ qua ký tự không thuộc alphabet; với token cần yêu cầu định dạng nghiêm ngặt.
10. **“Encode hai hoặc ba lần là đủ an toàn.”** Sai: mọi lớp encoding công khai đều có thể tháo ngược; không tạo ra khóa bí mật hoặc authentication tag.

## 11. Tình huống luyện tập và câu hỏi tự kiểm tra

**Tình huống A – Lưu digest SHA-256:** một hệ thống có digest 32 byte muốn lưu trong cột text và dễ so sánh bằng mắt. Hex 64 ký tự là lựa chọn thuận tiện; Base64 44 ký tự gọn hơn. Cả hai biểu diễn cùng digest, nên độ an toàn của SHA-256 không đổi khi đổi format. Digest này không phải password hash được thiết kế cho mật khẩu.

**Tình huống B – Token trong URL:** một hệ thống sinh 32 byte token bằng SecureRandom, rồi biểu diễn bằng Base64URL không padding, độ dài 43 ký tự. Khả năng khó đoán đến từ 32 byte ngẫu nhiên được sinh đúng cách; việc trình bày 43 ký tự không tạo thêm entropy. Token vẫn nhạy cảm và cần kiểm soát nơi truyền/lưu, hạn dùng và quyền sử dụng.

**Tình huống C – API nhận ciphertext:** một field JSON là Base64 của ciphertext AES-GCM. Server phải Base64 decode, kiểm tra định dạng/version/nonce, xác thực tag bằng khóa đúng rồi mới dùng plaintext. Dữ liệu Base64 đúng cú pháp vẫn có thể là ciphertext giả mạo, bị hỏng hoặc đến từ bên không có quyền.

**Tự kiểm tra:**

1. Chuỗi **SmF2YSE=** cần khóa nào để đọc lại? → Không cần khóa; đó là Base64 của năm byte UTF-8 cho **Java!**.
2. 16 byte dữ liệu đổi thành bao nhiêu ký tự hex và Base64 Basic có padding? → **32** ký tự hex và **24** ký tự Base64.
3. Vì sao Base64URL khác Base64 Basic? → Thay **+ / ** bằng **- _** để phù hợp hơn với URL; không thay đổi bí mật hay tính xác thực.
4. HexFormat.of().formatHex(byte[]) khác gì HexFormat.of().parseHex(String)? → Một hàm byte[] → text hex, một hàm text hex hợp lệ → byte[].
5. Một mật khẩu đã Base64 encode có thể lưu vào DB như password hash không? → Không. Base64 đảo ngược được; dùng password hashing có salt và chi phí phù hợp.
6. Nếu một giá trị Base64 decode được và có 32 byte thì đã là SHA-256 hợp lệ chưa? → Chỉ biết độ dài phù hợp, chưa biết nguồn gốc, cách tính hoặc tính toàn vẹn của giá trị.
7. Vì sao cần nêu charset khi đổi text sang byte[]? → Cùng ký tự nhưng charset hoặc chuẩn hóa Unicode khác có thể tạo byte khác, ảnh hưởng round-trip, digest và chữ ký.

**Nguyên tắc nhớ lâu:** **Base64 và HexFormat là cách viết dữ liệu dưới dạng text.** Chúng có thể bọc plaintext, ciphertext, hash, chữ ký hoặc token, nhưng bản thân chúng **không mã hóa bảo mật, không kiểm tra toàn vẹn, không xác thực và không cấp quyền truy cập**. Thiết kế bảo mật phải xác định yêu cầu bí mật/toàn vẹn/xác thực trước; encoding chỉ là lớp biểu diễn khi cần lưu, truyền hoặc hiển thị byte.
