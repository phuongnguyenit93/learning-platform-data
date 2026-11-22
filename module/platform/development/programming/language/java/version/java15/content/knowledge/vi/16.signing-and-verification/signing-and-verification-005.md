# Đảm bảo cùng dãy byte khi ký và xác minh (Java 15+)

## Mục tiêu

Hiểu và thực hành nguyên tắc cốt lõi khi dùng chữ ký số trong Java: **bên ký và bên xác minh phải đưa cùng một dãy byte của thông điệp vào thuật toán chữ ký**. Hai chuỗi nhìn giống nhau trên màn hình **chưa chắc mã hóa thành cùng các byte**; JSON, Unicode, xuống dòng, khoảng trắng, charset hoặc một bước truyền tải có thể âm thầm làm thay đổi dữ liệu và khiến xác minh thất bại.

Bài học sử dụng **Ed25519** qua API chuẩn **java.security.Signature**, **KeyPairGenerator**, **StandardCharsets.UTF_8** và **Normalizer**. Hỗ trợ EdDSA và các giao diện EdEC là tính năng chính thức từ **Java 15**, tiếp tục sử dụng được ở **Java 17 trở lên**; ví dụ biên dịch bằng **--release 17**, không dùng API lỗi thời.

Bạn sẽ biết cách:

1. Chuyển thông điệp thành **byte[]** bằng một quy tắc xác định và không sửa dãy byte giữa ký và xác minh.
2. Thực hiện đúng ba bước **initSign → update → sign** và **initVerify → update → verify**.
3. Phân biệt chữ ký được truyền đi với nội dung được ký, và phân biệt **Base64 của chữ ký** với dữ liệu thông điệp.
4. Xử lý các nguyên nhân lệch byte thực tế: **UTF-8, NFC/NFD, LF/CRLF, BOM, JSON serialization, khoảng trắng và thay đổi trường dữ liệu**.
5. Kiểm tra byte-for-byte và thiết kế một hợp đồng biểu diễn thông điệp nhất quán giữa các dịch vụ.

## 1. Chữ ký số gắn với byte, không gắn với giao diện hiển thị

Trong mô hình chữ ký số:

- **Bên ký** giữ private key, cung cấp lần lượt các byte của thông điệp **M** cho Signature, rồi tạo chữ ký **S**.
- **Bên xác minh** dùng public key tương ứng, cung cấp các byte của thông điệp **M'** và chữ ký **S** cho Signature.
- Với chữ ký hợp lệ và khóa đúng, việc xác minh thành công khi dữ liệu được ký và dữ liệu xác minh **trùng khớp chính xác theo thuật toán đã thống nhất**.
- Nếu **M' khác M**, chữ ký của M không xác nhận cho M', ngay cả khi một giao diện người dùng hiển thị hai thông điệp gần như giống hệt nhau.

Điều kiện **cùng byte là cần thiết nhưng không đủ**: còn cần **đúng khóa công khai, thuật toán, tham số và chữ ký**, cũng như xác thực public key thực sự thuộc chủ thể được tin cậy. Một kết quả verify = true chỉ chứng minh quan hệ chữ ký–dữ liệu–public key; nó không tự chứng minh danh tính nếu public key chưa được xác thực.

Ed25519 thuộc họ **EdDSA** dùng chữ ký số, không phải mã hóa dữ liệu và không phải X25519 thỏa thuận khóa. Dữ liệu và chữ ký là **hai đối tượng khác nhau**; không ký nhầm Base64 của chữ ký thay vì thông điệp, hoặc đưa bytes của chữ ký vào **Signature.update** rồi mong verify thành công.

## 2. Luồng Java Signature đúng

### Bên ký

~~~java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(messageBytes);
byte[] signatureBytes = signer.sign();
~~~

Đây là **đoạn mã minh họa trong một phương thức Java** đã có privateKey kiểu PrivateKey, messageBytes kiểu byte[] và xử lý ngoại lệ bảo mật. Thông điệp thực tế được ký là **toàn bộ byte[]** truyền qua update.

### Bên xác minh

~~~java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(publicKey);
verifier.update(messageBytes);
boolean valid = verifier.verify(signatureBytes);
~~~

Đây cũng là **đoạn minh họa**, với publicKey kiểu PublicKey và đúng messageBytes, signatureBytes.

**Giải thích ba pha:**

| Pha | Bên ký | Bên xác minh |
| --- | --- | --- |
| Khởi tạo | **initSign(privateKey)** | **initVerify(publicKey)** |
| Cung cấp thông điệp | Một hoặc nhiều **update(byte[])** | Cùng dãy byte, cùng thứ tự qua **update(...)** |
| Hoàn tất | **sign()** trả byte[] chữ ký | **verify(signatureBytes)** trả boolean hoặc ném exception khi có lỗi |

**Không nên dùng chung một đối tượng Signature đồng thời từ nhiều thread.** Mỗi yêu cầu hoặc luồng xử lý có thể tạo một Signature riêng, hoặc quản lý vòng đời và trạng thái rõ ràng. Theo hợp đồng Java, **sign()** và **verify()** sau khi hoàn tất sẽ reset trạng thái xử lý thông điệp về trạng thái đã init tương ứng; tuy nhiên, khi xử lý một giao dịch độc lập, tạo/khởi tạo rõ ràng giúp hạn chế nhầm dữ liệu cũ và dùng sai khóa.

**Chỉ gọi verify() sau khi update đúng thông điệp**; verify() không tự đọc messageBytes từ chữ ký.

## 3. Cùng nội dung nhìn thấy không đảm bảo cùng byte UTF-8

Java **String** chứa văn bản ở dạng ký tự Unicode, nhưng **Signature.update** nhận bytes. Nếu người ký và người xác minh tự chuyển String sang bytes theo các cách khác nhau, họ có thể ký hai thông điệp khác nhau.

### 3.1. Charset phải được quy định

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
~~~

Đoạn code minh họa nằm trong phương thức có String text. **StandardCharsets.UTF_8** là lựa chọn dễ tương tác và rõ ràng cho dữ liệu văn bản hiện đại. Dù Java bản mới mặc định UTF-8 trong nhiều hoàn cảnh, **không dùng charset mặc định như một phần hợp đồng chữ ký giữa các hệ thống**; hãy chỉ định charset ở cả bên ký và bên xác minh.

Không đồng nhất **ký String** với **ký byte[] của UTF-8**. Định dạng đang ký phải được xác định trước: UTF-8 của văn bản nào, sau những bước chuẩn hóa nào, và những byte đầu/cuối nào được tính vào thông điệp.

### 3.2. Unicode NFC/NFD và các biểu diễn tương đương

Ký tự **é** có thể được biểu diễn thành:

- Một code point được tạo sẵn **U+00E9**.
- Hai code point **U+0065** (e) và **U+0301** (combining acute accent).

Hai cách có thể hiển thị rất giống nhau nhưng có **UTF-8 bytes khác nhau**. Ví dụ:

~~~java
String composed = "Caf\u00E9";
String decomposed = "Cafe\u0301";
boolean equal = java.util.Arrays.equals(
        composed.getBytes(StandardCharsets.UTF_8),
        decomposed.getBytes(StandardCharsets.UTF_8)); // false
~~~

Đây là đoạn minh họa; dấu **\u00E9** và **\u0301** là Unicode escapes trong Java source. Để hai bên ký/xác minh cùng biểu diễn, **nếu giao thức quy định NFC**, chuẩn hóa **trước khi encode**:

~~~java
String nfc = Normalizer.normalize(text, Normalizer.Form.NFC);
byte[] canonicalBytes = nfc.getBytes(StandardCharsets.UTF_8);
~~~

Cần import **java.text.Normalizer** và có String text trong phương thức. **Không tự động normalize sau khi đã ký** rồi kỳ vọng chữ ký cũ vẫn hợp lệ. Nếu bên ký không normalize, bên xác minh cũng phải dùng **đúng bytes ban đầu**; chỉ áp dụng NFC khi **cả giao thức đã thống nhất**.

**NFC không giống case-folding, loại dấu, trim hoặc thay thế khoảng trắng**. Những thao tác biến đổi mạnh hơn có thể thay đổi ý nghĩa dữ liệu; không thêm nếu giao thức chưa định nghĩa.

## 4. Ký tự xuống dòng và khoảng trắng là dữ liệu

Các chuỗi sau khác byte:

~~~text
A\nB    (LF: 0A)
A\r\nB  (CRLF: 0D 0A)
~~~

Phần trên là **ký hiệu biểu diễn bytes**, không phải hai dòng văn bản tùy ý. Nếu ký bytes của **"A\nB"** mà gửi qua công cụ đổi sang CRLF, phía xác minh đang thấy **thêm byte 0D**, nên chữ ký không còn xác nhận thông điệp ấy.

Các trường hợp rất thường gặp:

- **LF vs CRLF vs CR** trong file văn bản trên hệ điều hành khác nhau.
- **Dấu xuống dòng cuối file** có hoặc không có.
- **Space/U+0020**, **tab/U+0009**, space cuối dòng hoặc dòng trắng cuối file.
- **UTF-8 BOM (EF BB BF)** có hoặc không có ở đầu file.
- **Ký tự khoảng trắng Unicode**: non-breaking space (U+00A0) khác space thường.
- **Thêm tiền tố, hậu tố, header hoặc delimiter** trước/sau payload; chỉ một byte thêm cũng tạo thông điệp khác.

Với **byte[] đã được ký**, không gọi **trim()**, **strip()**, **stripIndent()**, chuyển newline, đổi tab thành space hoặc định dạng lại rồi đưa vào verify. Chỉ thay đổi dữ liệu **trước khi ký** nếu đó là quy tắc chuẩn hóa đã được cả hai bên thống nhất.

**Đường dẫn đáng tin cậy nhất** cho file hoặc dữ liệu nhị phân là ký **bytes của chính dữ liệu sẽ truyền/lưu**, không đọc thành String rồi encode lại:

~~~java
byte[] payload = Files.readAllBytes(path);
signer.update(payload);
~~~

Đây là đoạn minh họa với signer đã initSign, path kiểu Path và import **java.nio.file.Files**; dùng cho file nhỏ/đã kiểm soát kích thước. Với file lớn, xem mục 8 về đọc theo khối.

## 5. Thông điệp có cấu trúc: JSON, CSV, XML và HTTP

Đối với JSON, hai chuỗi sau có thể biểu diễn cùng một object về mặt dữ liệu nhưng **không phải cùng bytes**:

~~~json
{"id":7,"status":"ok"}
~~~

và:

~~~json
{ "status": "ok", "id": 7 }
~~~

JSON cho phép whitespace không đáng kể giữa token và không bắt buộc giữ thứ tự các thành viên object. Nếu một dịch vụ **serialize lại** JSON theo thứ tự khóa khác, thay dấu cách, đổi biểu diễn số, hoặc escape Unicode khác cách, byte[] thay đổi.

Có hai chiến lược đúng, cần **chọn một chiến lược dứt khoát**:

1. **Ký raw bytes của payload.** Bên nhận **xác minh đúng raw bytes trước khi parse hoặc serialize lại**. Không để proxy, middleware hoặc thư viện tự sửa payload giữa các bước này.
2. **Ký biểu diễn chuẩn tắc do giao thức quy định.** Hai bên dùng **cùng thuật toán canonicalization** (ví dụ **JSON Canonicalization Scheme – RFC 8785** nếu phù hợp dữ liệu và yêu cầu liên thông), cùng phiên bản, quy tắc xử lý Unicode/số/trường; bên nhận chuẩn hóa **đúng theo quy tắc đó** trước khi verify.

**Không tự viết một canonicalizer JSON bằng cách sort vài khóa rồi xóa khoảng trắng** và cho là tương thích tất cả JSON. Dữ liệu JSON có nhiều quy tắc về số thực, ký tự escape, trùng tên khóa, số âm 0 và phân tích Unicode; một giao thức cần định nghĩa và kiểm tra đầy đủ, có test vectors liên thông.

**CSV/XML** cũng cần cẩn thận với mã hóa, thứ tự trường, quote/escape, namespace, khoảng trắng và định dạng serializer. Nếu ký một đối tượng HTTP ở mức ứng dụng, cần biết chính xác **phạm vi bytes**: body, một phần headers, URL, method, content-encoding, content-type hoặc một canonical request. Đừng giả định chữ ký body xác thực cả header/URL nếu những phần đó không được đưa vào dữ liệu ký.

**Lưu ý an ninh:** Xác minh phải dựa vào **đúng biểu diễn mà hệ thống dùng để thực hiện hành động**. Nếu kiểm tra chữ ký trên một bản canonicalized nhưng xử lý một bản có cách hiểu khác do parser, có thể xuất hiện sai lệch nghiêm trọng. Ràng buộc chính xác phạm vi đã ký và từ chối đầu vào nhập nhằng.

## 6. Định nghĩa hợp đồng ký rõ ràng

Một hợp đồng dữ liệu đáng tin cậy cần trả lời:

| Câu hỏi | Thông tin cần thống nhất |
| --- | --- |
| Thuật toán nào? | Ví dụ **Ed25519**, không tự chuyển thành Ed448 hoặc X25519 |
| Dùng public key nào? | Key ID, kho khóa tin cậy, chu kỳ luân chuyển và cách xác thực public key |
| Dữ liệu ký là gì? | Raw body bytes, snapshot nội dung hoặc canonical representation được đặc tả |
| Charset? | Ví dụ **UTF-8** cho trường text |
| Unicode normalization? | Raw text, NFC hay quy tắc khác; **không ngầm định** |
| Xuống dòng/BOM? | LF/CRLF, chính sách BOM, ký tự newline cuối payload |
| Cấu trúc/serialization? | Thứ tự trường, số, khoảng trắng, escape, bản canonicalization |
| Trường metadata nào được xác thực? | Version, loại thông điệp, ID, timestamp, nonce, audience… nếu nghiệp vụ cần |
| Chữ ký truyền bằng gì? | byte[] nhị phân hoặc Base64/base64url theo giao thức, không phải String tùy ý |
| Chống replay? | Timestamp, nonce, TTL/expiry, audience và kiểm tra server-side nếu cần |

**Cùng bytes không đủ để phòng replay.** Một thông điệp đã được ký đúng có thể bị phát lại nếu hệ thống không kiểm soát nonce, thời hạn, ID yêu cầu, ngữ cảnh sử dụng và trạng thái xử lý. Những trường bảo vệ đó phải **được bao gồm trong dữ liệu được ký**, không chỉ đặt bên ngoài trong một header có thể sửa.

Có thể phân tách thông điệp bằng **định dạng độ dài–giá trị (length-prefix)** hoặc một schema có phân định không nhập nhằng. Ví dụ nếu ký hai trường A và B mà chỉ nối String, cặp ("ab","c") và ("a","bc") đều tạo "abc"; vì vậy cần cấu trúc biểu diễn chính xác trước khi ký.

## 7. Chương trình Java 17+ hoàn chỉnh

Chương trình dùng **KeyPairGenerator Ed25519** tạo cặp khóa ngẫu nhiên; ký UTF-8 của văn bản có ký tự **é** và LF; rồi thử nhiều đường xác minh:

- Bytes **nguyên gốc**.
- Cùng bytes nhưng chia thành các chunk **3 byte** để gọi Signature.update nhiều lần.
- Chuỗi trông tương tự nhưng khác biểu diễn Unicode (**NFD so với NFC**).
- Chuẩn hóa về **NFC** trước khi encode, tạo lại đúng bytes ban đầu.
- Đổi **LF** thành **CRLF**.
- Thay nội dung từ **status=ok** thành **status=no**.
- Encode/decode **chữ ký** bằng Base64 mà không thay đổi bytes chữ ký.

Lưu vào tệp **SameBytesSignatureDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.Base64;

public class SameBytesSignatureDemo {
    private static byte[] sign(byte[] data, PrivateKey key) throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(key);
        signer.update(data);
        return signer.sign();
    }

    private static boolean verify(byte[] data, byte[] signature, PublicKey key)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        verifier.update(data);
        return verifier.verify(signature);
    }

    private static boolean verifyInChunks(byte[] data, byte[] signature, PublicKey key)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        for (int offset = 0; offset < data.length; offset += 3) {
            int length = Math.min(3, data.length - offset);
            verifier.update(data, offset, length);
        }
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair keys = generator.generateKeyPair();

        String source = "Caf\u00E9\nstatus=ok";
        String decomposed = "Cafe\u0301\nstatus=ok";
        byte[] original = source.getBytes(StandardCharsets.UTF_8);
        byte[] visuallySame = decomposed.getBytes(StandardCharsets.UTF_8);
        byte[] normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC).getBytes(StandardCharsets.UTF_8);
        byte[] crlf = source.replace("\n", "\r\n")
                .getBytes(StandardCharsets.UTF_8);
        byte[] changed = "Caf\u00E9\nstatus=no".getBytes(StandardCharsets.UTF_8);

        byte[] signature = sign(original, keys.getPrivate());
        String transported = Base64.getEncoder().encodeToString(signature);
        byte[] decodedSignature = Base64.getDecoder().decode(transported);

        System.out.println("UTF-8 source bytes: " + original.length);
        System.out.println("Ed25519 signature bytes: " + signature.length);
        System.out.println("Base64 round-trip: "
                + Arrays.equals(signature, decodedSignature));
        System.out.println("Original verify: "
                + verify(original, decodedSignature, keys.getPublic()));
        System.out.println("Verify chunked (3 bytes): "
                + verifyInChunks(original, decodedSignature, keys.getPublic()));
        System.out.println("Unicode unnormalized equal bytes: "
                + Arrays.equals(original, visuallySame));
        System.out.println("Unicode unnormalized verify: "
                + verify(visuallySame, signature, keys.getPublic()));
        System.out.println("NFC equal bytes: "
                + Arrays.equals(original, normalized));
        System.out.println("NFC verify: "
                + verify(normalized, signature, keys.getPublic()));
        System.out.println("CRLF verify: "
                + verify(crlf, signature, keys.getPublic()));
        System.out.println("Changed text verify: "
                + verify(changed, signature, keys.getPublic()));
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 SameBytesSignatureDemo.java
java SameBytesSignatureDemo
~~~

**Stdout chính xác**, đã đối chiếu sau khi biên dịch với **--release 17** và chạy trên JDK 24:

~~~text
UTF-8 source bytes: 15
Ed25519 signature bytes: 64
Base64 round-trip: true
Original verify: true
Verify chunked (3 bytes): true
Unicode unnormalized equal bytes: false
Unicode unnormalized verify: false
NFC equal bytes: true
NFC verify: true
CRLF verify: false
Changed text verify: false
~~~

**Giải thích kết quả:**

1. **15 byte** là độ dài của văn bản "Café\nstatus=ok" khi mã hóa UTF-8 (é được mã hóa thành nhiều byte). Không tính số ký tự Java rồi đoán số byte.
2. **64 byte** là độ dài chữ ký chuẩn của **Ed25519**. Giá trị bytes chữ ký cụ thể phụ thuộc khóa được tạo ngẫu nhiên, nhưng chiều dài vẫn là 64 byte.
3. **Base64 round-trip: true:** bytes chữ ký không đổi khi encode/decode Base64. Việc encode chữ ký để truyền không thay thế hoặc chuẩn hóa dữ liệu thông điệp được ký.
4. **Original verify: true:** đúng public key, signature và dữ liệu bytes nguyên gốc.
5. **Verify chunked: true:** các lần update lần lượt nối **đúng dãy byte**; ranh giới chunk không làm thay đổi thông điệp. Việc tách chunk có thể cắt giữa hai byte của một ký tự UTF-8 mà vẫn hợp lệ vì Signature xử lý **bytes**, không tự giải mã ký tự.
6. **Unicode unnormalized: false:** hai dạng Unicode trông gần như nhau nhưng có bytes khác. Chữ ký của dạng composed không xác minh được với bytes decomposed.
7. **NFC verify: true:** sau khi chuyển chuỗi decomposed về NFC và encode UTF-8, bytes khớp lại dữ liệu ký. Đây là **chính sách chuẩn hóa ví dụ**, không phải hành vi mà API Signature tự thực hiện.
8. **CRLF verify: false:** chỉ cần thay **\n** bằng **\r\n**, dữ liệu ký đã đổi.
9. **Changed text verify: false:** sửa giá trị nghiệp vụ làm chữ ký không hợp lệ.

**Điểm an toàn:** Ví dụ không in private key hoặc chữ ký Base64 thực tế. Khi triển khai thật, phải **xác thực public key** trước khi dùng để xác minh, và quản lý private key trong keystore/provider thích hợp.

## 8. Ký file và dữ liệu lớn theo từng chunk

Nếu dữ liệu là một file nhị phân hoặc muốn giữ chính xác bytes gốc, không cần chuyển thành String. Có thể gọi **Signature.update(byte[], offset, length)** nhiều lần theo đúng thứ tự:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = input.read(buffer)) != -1) {
        if (n > 0) {
            signature.update(buffer, 0, n);
        }
    }
}
~~~

Đây là **đoạn minh họa** trong phương thức có biến signature kiểu Signature đã gọi initSign hoặc initVerify, biến path kiểu Path; cần import **java.io.InputStream** và **java.nio.file.Files**, đồng thời xử lý IOException/SignatureException.

Hai bên phải cập nhật **cùng nội dung theo cùng thứ tự byte**. Kích thước chunk 8192 chỉ là cách chia dữ liệu để đọc; chunk **không phải một phần có ý nghĩa mật mã**. Nếu bên ký chia 8192 byte/lần, bên xác minh chia 4096 byte/lần vẫn có thể nhận chữ ký hợp lệ, miễn dãy byte cập nhật là một.

**Cảnh báo về bộ nhớ:** Việc đọc từng chunk tránh tạo một byte[] lớn ở phía ứng dụng, nhưng **không bảo đảm provider EdDSA không lưu nội bộ toàn bộ thông điệp** khi tính chữ ký. Đừng suy ra footprint bộ nhớ có giới hạn 8192 byte chỉ từ việc dùng Signature.update theo khối.

**Cảnh báo về thay đổi file:** Nếu file được chỉnh trong thời gian ký, hoặc file được truyền rồi biên tập trước khi xác minh, hai phía có thể đọc hai snapshot khác nhau. Với dữ liệu quan trọng, hãy ký **một snapshot bất biến** hoặc kiểm soát phiên bản/khóa truy cập file phù hợp.

### Không tùy tiện tự băm thông điệp trước khi dùng Ed25519

~~~java
// Không thay messageBytes bằng SHA-256(messageBytes)
// nếu giao thức yêu cầu chữ ký Ed25519 trên chính messageBytes.
signer.update(messageBytes);
~~~

Đây là minh họa. Ed25519 thực hiện các phép băm theo **thuật toán EdDSA được đặc tả**; việc ứng dụng đổi input thành một hash SHA-256 trước khi gọi update làm **đổi thông điệp được ký**, không còn tương thích với chữ ký Ed25519 trên bytes gốc. Các biến thể prehash (nếu giao thức dùng) là **thuật toán/tham số được định nghĩa riêng**, không phải tự hash bất kỳ rồi ghi nhãn "Ed25519".

## 9. Xác định nguyên nhân verify thất bại

Khi **Signature.verify(signatureBytes)** trả false, không đoán ngay rằng private key hoặc thuật toán lỗi. Kiểm tra có hệ thống:

1. **Đúng public key không?** Khóa công khai phải thuộc cặp khóa của signer và được tin cậy; kiểm tra key ID, curve/algorithm, certificate hoặc nguồn phân phối.
2. **Đúng chữ ký bytes không?** Nếu truyền bằng Base64, giải mã đúng một lần, không đổi Base64 sang bytes bằng cách đơn thuần gọi String.getBytes().
3. **Đúng message bytes không?** Kiểm tra độ dài bytes tại hai phía và byte đầu tiên khác nhau. Chỉ làm việc này bằng dữ liệu test hoặc log được phép.
4. **Dữ liệu có bị parse rồi serialize lại không?** So sánh raw payload trước và sau middleware, HTTP framework hoặc JSON serializer.
5. **Encoding và normalization có khớp không?** UTF-8, NFC/NFD, escaping, BOM, LF/CRLF, dấu newline cuối file.
6. **Có thiếu hoặc thừa chunk update không?** Kiểm tra offset, length, thứ tự, xử lý khi read(...) trả 0 và có dùng chung state Signature sai cách không.
7. **Thuật toán/parameters có khớp không?** Ed25519 khác Ed448 hoặc Ed25519 với dữ liệu đã băm trước; kiểm tra mode cấu hình nếu giao thức có quy định.
8. **Signature có thuộc đúng phạm vi dữ liệu cần xác thực không?** Chữ ký chỉ trên body không bảo vệ header/URL không nằm trong bytes đã ký.
9. **Đầu vào chữ ký có đúng định dạng không?** Signature.verify có thể **ném SignatureException** đối với chữ ký sai kiểu/mã hóa không hợp lệ; không mặc định coi mọi lỗi là false.

### Debug byte an toàn

Trong môi trường thử nghiệm, có thể dùng:

~~~java
System.out.println(Arrays.equals(sentBytes, receivedBytes));
System.out.println(sentBytes.length + " / " + receivedBytes.length);
~~~

Đây là đoạn minh họa với hai byte[] được phép kiểm thử. Nếu muốn so sánh fingerprint/digest của payload tại hai hệ thống, hãy thỏa thuận cùng thuật toán hash như SHA-256 **chỉ cho việc chẩn đoán**, không nhầm digest đó với **dữ liệu mà Ed25519 đang ký**. Không ghi log nguyên văn dữ liệu nhạy cảm, khóa riêng, token, tài liệu mật, hoặc digest có thể bị lợi dụng để dò dữ liệu ít entropy.

Tốt nhất nên có **test vector cố định**: cùng một byte[] ở dạng hex/base64, expected signature cho khóa test, và những trường hợp âm tính như đổi một byte, đổi newline, đổi Unicode representation. Test vector giúp phát hiện lỗi liên thông giữa Java và ngôn ngữ khác trước khi đưa vào production.

## 10. Những lỗi phổ biến cần tránh

1. **Dùng getBytes() không chỉ rõ charset.** Luôn thống nhất **UTF-8** hoặc encoding đã được giao thức đặc tả.
2. **Ký String rồi xác minh String đã được normalize/trim.** Chuẩn hóa thay đổi bytes; quy tắc phải áp dụng như nhau **trước ký và trước xác minh**.
3. **So sánh văn bản hiển thị thay vì bytes.** Hai chuỗi chứa Unicode tổ hợp và ký tự precomposed có thể nhìn giống nhưng khác dữ liệu ký.
4. **Đọc và ghi lại file văn bản khiến LF thành CRLF.** Với raw signed payload, không chuyển newline ngoài hợp đồng.
5. **Nhầm Base64 signature với Base64 payload.** Signature.verify cần chữ ký đã giải mã thành bytes và cùng messageBytes như bên ký.
6. **Để JSON serializer tự thay thứ tự key, whitespace, escape hoặc biểu diễn số.** Dùng raw bytes nguyên vẹn hoặc canonicalization chuẩn đã thống nhất.
7. **Ký từng trường bằng cách nối chuỗi không có delimiter an toàn.** Dễ tạo các cặp dữ liệu khác nhau nhưng cùng dãy bytes; dùng framing/schema không nhập nhằng.
8. **Gọi update thừa/thiếu một lần hoặc sai thứ tự.** Signature ký/verify trên **dãy nối của tất cả byte cập nhật**.
9. **Ký hash của dữ liệu nhưng bên nhận xác minh raw dữ liệu.** Đó là hai thông điệp khác nhau, cho dù cùng tên thuật toán Signature.
10. **Nghĩ verify=true xác thực danh tính người gửi mà không xác thực public key.** Cần trust binding giữa key và chủ thể.
11. **Không đưa timestamp, nonce hoặc scope vào dữ liệu được ký.** Có thể bị replay hoặc sử dụng chữ ký vào ngữ cảnh khác.
12. **Dùng một Signature object đồng thời từ nhiều thread.** Có thể trộn trạng thái update hoặc thay đổi khóa; quản lý state theo tác vụ riêng.
13. **Đọc file qua Reader rồi encode lại khi cần ký raw bytes.** Việc giải mã và encode lại có thể đổi BOM, byte lỗi hoặc newline.
14. **Coi false luôn là hỏng chữ ký, không phân biệt SignatureException.** Sai định dạng chữ ký hoặc thao tác API có thể ném exception.
15. **Tin rằng chia nhỏ update chắc chắn bảo đảm bộ nhớ cố định cho EdDSA.** Implementation mật mã có thể giữ nội bộ dữ liệu; cần đo và kiểm thử nếu file rất lớn.

## 11. Tự kiểm tra

**Câu 1:** Hai chuỗi hiển thị "Café" nhưng một chuỗi dùng U+00E9, chuỗi khác dùng U+0065 U+0301. Chữ ký Ed25519 trên UTF-8 của chuỗi thứ nhất xác minh trực tiếp trên bytes chuỗi thứ hai được không?  
**Đáp án:** Không. UTF-8 khác byte; cần cùng biểu diễn gốc hoặc quy tắc chuẩn hóa thống nhất như NFC **trước** các bước ký/xác minh.

**Câu 2:** Ký với một lần update(byte[]) và xác minh bằng nhiều lần update(byte[], off, len) có được không?  
**Đáp án:** Có, nếu dãy bytes nối lại **đúng nội dung và đúng thứ tự**.

**Câu 3:** Nếu thông điệp chuyển từ LF sang CRLF nhưng ký không đổi, verify có thành công không?  
**Đáp án:** Không, vì thêm byte CR và làm đổi thông điệp đã ký.

**Câu 4:** Đưa SHA-256(message) vào Signature.update("Ed25519") thay message có giữ nguyên chữ ký Ed25519 trên message không?  
**Đáp án:** Không; đó là ký một thông điệp khác. Không tự thay giao thức bằng tiền băm.

**Câu 5:** Base64.encode(signatureBytes) rồi Base64.decode có làm chữ ký mất hiệu lực không?  
**Đáp án:** Không, nếu decode trả lại chính xác signatureBytes và dữ liệu message, khóa, thuật toán vẫn đúng.

**Câu 6:** Cùng dữ liệu nhưng verify=false; nên kiểm tra gì trước?  
**Đáp án:** Xác nhận đúng public key/signature/algorithm, so sánh **bytes thực tế** hai bên (có thể theo test fixture), rồi kiểm tra charset, Unicode, newline và serializer.

**Câu 7:** Ký raw JSON body có mặc định bảo vệ HTTP method và URL không?  
**Đáp án:** Không. Chỉ các trường/bytes thực sự nằm trong thông điệp ký mới được chữ ký bảo vệ.

## 12. Ghi nhớ

**Chữ ký số xác nhận dãy byte, không phải văn bản trông giống nhau.** Với Java Ed25519, cung cấp **cùng byte[]** theo cùng thứ tự vào **Signature.update(...)**, dùng public key và thuật toán chính xác, rồi gọi verify(signatureBytes). Đặt rõ quy tắc UTF-8, chuẩn hóa Unicode, xuống dòng và canonicalization **trước** khi ký. Khi truyền dữ liệu, giữ raw bytes bất biến hoặc canonicalize theo một chuẩn được cả hai bên cùng triển khai và kiểm thử.

**Nếu dữ liệu khác một byte, hãy xem đó là một thông điệp khác.**

## Tài liệu tham khảo chính thức

- Oracle, **Signature API – initSign, initVerify, update, sign và verify**, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html
- Oracle, **Java Cryptography Architecture (JCA) Reference Guide**, Java SE 17: https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html
- Oracle, **Normalizer**, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html
- Oracle, **StandardCharsets.UTF_8**, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html
- IETF, **RFC 8032 – Edwards-Curve Digital Signature Algorithm (EdDSA)**: https://www.rfc-editor.org/rfc/rfc8032
- IETF, **RFC 8785 – JSON Canonicalization Scheme (JCS)**: https://www.rfc-editor.org/rfc/rfc8785
