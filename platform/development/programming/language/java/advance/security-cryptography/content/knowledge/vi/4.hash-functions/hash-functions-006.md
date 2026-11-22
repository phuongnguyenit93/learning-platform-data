# 4.6. So sánh digest bằng MessageDigest.isEqual và phạm vi bảo đảm của API

## 1. Bối cảnh: so sánh giá trị băm có thể liên quan đến bảo mật

Digest (giá trị băm) là một mảng byte được tạo từ thông điệp bằng thuật toán băm, ví dụ `SHA-256` trả về **32 byte (256 bit)**. Trong Java, ta thường cần so sánh:

- Digest tính lại từ dữ liệu với digest kỳ vọng đã lưu để phát hiện dữ liệu bị thay đổi.
- Giá trị HMAC nhận được với HMAC do bên xác minh tính bằng **khóa bí mật**.
- Các giá trị mật mã mà thời gian xác minh có thể bị bên ngoài đo, dù thông tin sai khác bên trong phải được hạn chế lộ.

Nếu cách so sánh thoát sớm ngay khi gặp byte khác đầu tiên, thời gian thực thi có thể phụ thuộc vị trí byte sai đầu tiên. `java.security.MessageDigest.isEqual` là một API so sánh hai byte array có **đặc tính hạn chế kiểu rò rỉ này**, trong phạm vi được tài liệu Java công bố.

Cần phân biệt hai câu hỏi: **hai mảng byte có bằng nhau không?** và **nguồn dữ liệu có đáng tin không?** Phương thức `isEqual` chỉ trả lời câu thứ nhất; câu thứ hai cần thuật toán, nguồn giá trị kỳ vọng và chính sách an ninh thích hợp.

## 2. Chữ ký, dữ liệu đầu vào và giá trị trả về

API:

```java
public static boolean isEqual(byte[] digesta, byte[] digestb)
```

Đây là **phương thức static**: gọi `MessageDigest.isEqual(expected, actual)` mà không cần tạo đối tượng `MessageDigest`. Nó **không tự tính digest**, không gọi SHA-256/HMAC và không xác thực algorithm/provider đã dùng để tạo mảng.

Với **hai mảng byte không null**:

- Trả `true` nếu độ dài bằng nhau và từng byte cùng vị trí bằng nhau.
- Trả `false` nếu độ dài khác hoặc có ít nhất một byte khác.
- Không tự chuyển hex/Base64 thành byte, không bỏ qua khoảng trắng, không chuẩn hóa Unicode, không cho phép prefix khớp được tính là toàn bộ digest.
- Việc digest bằng nhau không phải chứng minh toán học hai **thông điệp gốc** giống nhau: một hàm băm hữu hạn đầu ra luôn có khả năng collision; độ khó tìm collision phụ thuộc thuật toán băm.

**Không dùng `==` hoặc `byte[].equals` để kiểm tra nội dung hai digest.** Đối với array, cả hai là phép so sánh tham chiếu; hai mảng khác object nhưng cùng 32 byte SHA-256 sẽ được xem là khác bằng `==`.

Ví dụ tối thiểu (đoạn mã đặt trong một chương trình đã import `MessageDigest` và `StandardCharsets`):

```java
byte[] a = MessageDigest.getInstance("SHA-256")
        .digest("hello".getBytes(StandardCharsets.UTF_8));
byte[] b = MessageDigest.getInstance("SHA-256")
        .digest("hello".getBytes(StandardCharsets.UTF_8));
boolean equal = MessageDigest.isEqual(a, b); // true
```

Ở đây `MessageDigest.digest` thực hiện phép băm, còn `MessageDigest.isEqual` chỉ thực hiện so sánh. Java không tự ghi nhớ nguồn, thuật toán hay ý nghĩa mật mã của mỗi byte array.

## 3. Timing side-channel: vì sao so sánh thông thường chưa đủ?

Xét đoạn mã tự viết sau:

```java
// Ví dụ để PHÂN TÍCH, không dùng cho so sánh dữ liệu mật mã.
static boolean earlyExit(byte[] a, byte[] b) {
    if (a.length != b.length) return false;
    for (int i = 0; i < a.length; i++) {
        if (a[i] != b[i]) return false;
    }
    return true;
}
```

Với hai mảng cùng độ dài, sai ở byte đầu làm vòng lặp dừng ngay; sai ở byte cuối khiến vòng lặp đi gần hết. Trong một giao thức cụ thể, đối thủ có khả năng gửi nhiều phép thử và đo thời gian có thể phân tích tương quan này. Khả năng khai thác phụ thuộc độ nhiễu mạng, quyền truy cập, thiết kế protocol, tốc độ máy và nhiều yếu tố; vài phép đo nhanh/chậm **không** đủ để chứng minh có lỗ hổng.

So sánh các cách viết phổ biến:

| Cách viết | Kiểm tra nội dung byte? | Phù hợp để so sánh MAC/digest khi cần hạn chế timing leak? |
| --- | --- | --- |
| `a == b` | Không, kiểm tra reference | Không |
| `a.equals(b)` với `byte[]` | Không, mảng kế thừa `Object.equals` | Không |
| `Arrays.equals(a, b)` | Có | Không có hợp đồng thời gian dành cho mục tiêu mật mã; có đường kết thúc sớm |
| `String.equals` với chuỗi hex/Base64 | So sánh ký tự | Không bảo đảm thời gian cho dữ liệu bí mật |
| `MessageDigest.isEqual(a, b)` | Có | Được thiết kế để giảm rò rỉ vị trí sai khác, theo phạm vi API |

`Arrays.equals` thường là lựa chọn đúng cho byte array **không nhạy cảm về timing**. Với digest/tag cần so sánh tránh rò rỉ vị trí byte sai, nên chọn API chuyên dụng `MessageDigest.isEqual`.

**Không biến byte digest thô thành `String` bằng UTF-8 rồi so sánh.** Digest là byte tùy ý, không bảo đảm UTF-8 hợp lệ. Nếu giao thức truyền digest bằng Base64/hex, hãy giải mã chặt chẽ về `byte[]` rồi so sánh.

## 4. “Constant-time” của isEqual bảo đảm tới đâu?

### 4.1. Điều Java mô tả

Tài liệu Java SE 17 cho `isEqual` ghi trong **Implementation Note** rằng các byte của `digesta` được xét khi so sánh và thời gian tính toán được thiết kế phụ thuộc vào **độ dài `digesta`**, không phụ thuộc nội dung hai mảng hay độ dài `digestb`. Tài liệu các JDK mới hơn, ví dụ Java SE 24, giải thích rõ ngoại lệ khi `digestb` là `null` hoặc có độ dài **0 byte**.

Vì vậy với đầu vào thông thường là **hai mảng không null, không rỗng**, ta nên đặt digest/tag *kỳ vọng có độ dài cố định* ở đối số đầu: `MessageDigest.isEqual(expectedTag, receivedTag)`. Với HmacSHA256 không cắt ngắn, expected tag là 32 byte.

Khi so sánh theo hướng đó, logic không cần dừng ngay ở vị trí byte đầu tiên không khớp. Đây là **một đặc tính thuật toán của phép so sánh**, không phải chứng minh mọi đường thực thi đều có cùng thời gian tường (wall-clock).

### 4.2. Những ngoại lệ và giới hạn quan trọng

1. **Đối số thứ nhất có thể thay đổi độ dài.** Implementation Note cho phép thời gian phụ thuộc `digesta.length`. Nếu độ dài này được điều khiển bởi bên không tin cậy, không suy ra thời gian độc lập mọi chiều dài đầu vào.
2. **`null` và mảng rỗng được xử lý đặc biệt.** Một số đường trong OpenJDK có fast-path khi `digesta == digestb`, khi một mảng là `null`, hoặc `digestb.length == 0`. Do đó, không khẳng định “mọi trường hợp đều đi qua đủ byte”. API không phải hợp đồng an ninh cho phép nhận `null`/rỗng như tag hợp lệ.
3. **Trường hợp cùng tham chiếu:** OpenJDK có thể trả `true` ngay khi hai tham số trỏ tới cùng một byte array. Không dùng alias/same-reference để benchmark thuộc tính timing; đối với xác minh thật, expected tag được tính lại độc lập với dữ liệu nhận.
4. **Độ dài tag không nhất thiết là bí mật.** Ứng dụng có thể từ chối nhanh tag sai độ dài vì định dạng chuẩn đã quy định 32 byte. Nếu độ dài chính nó là thông tin bí mật, cần phân tích thiết kế bao trùm hơn thay vì trông chờ `isEqual` che giấu.
5. **Các bước xung quanh vẫn có thời gian riêng:** parse request, kiểm tra quyền, decode Base64, tính SHA/HMAC, đọc DB, lỗi JSON, exception và trả HTTP đều nằm ngoài hợp đồng thời gian của `isEqual`.
6. **Máy ảo và phần cứng có nhiễu:** JIT, garbage collection, CPU cache, scheduling, tối ưu hóa compiler và network khiến thời gian quan sát thực tế biến đổi. “Constant-time” trong tài liệu không có nghĩa cùng số nano-giây trong mọi môi trường.
7. **Không bảo đảm an toàn khi thuật toán hoặc nguồn kỳ vọng sai.** So sánh SHA-256 không khóa với digest do client tự khai báo không biến nó thành xác thực; dùng API đúng không sửa được thiết kế mật mã sai.

Bảng trạng thái để tránh nhầm:

| Hai đối số | Kết quả logic cần kỳ vọng | Lưu ý về bảo mật |
| --- | --- | --- |
| Không null, cùng độ dài và cùng byte | `true` | Mặc định của so sánh nội dung |
| Không null, cùng độ dài nhưng khác ít nhất một byte | `false` | Không cần tự viết vòng lặp dừng sớm |
| Không null, khác độ dài | `false` | Không chấp nhận tag bị cắt nếu giao thức đòi đủ độ dài |
| Cùng một tham chiếu byte array | `true` | Có fast-path trong OpenJDK; không dùng để kiểm thử timing |
| `null` hoặc tag rỗng | Bên gọi **tự từ chối trước** | Đừng dựa vào hành vi triển khai của trường hợp biên |

## 5. Ví dụ Java 17+ độc lập: SHA-256 và xác minh HMAC

Chương trình sau minh họa hai mục đích khác nhau:

- **SHA-256:** so sánh digest của cùng thông điệp, thông điệp khác và digest bị cắt ngắn.
- **HmacSHA256:** tạo khóa ngẫu nhiên cho demo; tính tag bằng `Mac` và kiểm tra bằng `MessageDigest.isEqual`; sửa thông điệp, sửa tag hoặc thiếu tag đều bị từ chối.

Tạo file `DigestCompareDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public class DigestCompareDemo {
    private static byte[] utf8(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] sha256(byte[] data) throws GeneralSecurityException {
        return MessageDigest.getInstance("SHA-256").digest(data);
    }

    private static byte[] hmacSha256(byte[] data, SecretKey key)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key);
        return mac.doFinal(data);
    }

    private static boolean verifyHmac(byte[] data, byte[] suppliedTag,
            SecretKey key) throws GeneralSecurityException {
        byte[] expectedTag = hmacSha256(data, key);
        if (suppliedTag == null || suppliedTag.length != expectedTag.length) {
            return false;
        }
        return MessageDigest.isEqual(expectedTag, suppliedTag);
    }

    public static void main(String[] args) throws Exception {
        byte[] original = utf8("message=v1");
        byte[] modified = utf8("message=v2");

        byte[] digestA = sha256(original);
        byte[] digestBCopy = sha256(original);
        byte[] digestDifferent = sha256(modified);

        System.out.println("SHA-256 length: " + digestA.length);
        System.out.println("Same message: " +
                MessageDigest.isEqual(digestA, digestBCopy));
        System.out.println("Different message: " +
                MessageDigest.isEqual(digestA, digestDifferent));
        System.out.println("Short digest: " +
                MessageDigest.isEqual(digestA,
                        Arrays.copyOf(digestBCopy, digestBCopy.length - 1)));

        KeyGenerator generator = KeyGenerator.getInstance("HmacSHA256");
        generator.init(256);
        SecretKey key = generator.generateKey();
        byte[] tag = hmacSha256(original, key);
        byte[] tamperedTag = tag.clone();
        tamperedTag[0] ^= 1;

        System.out.println("HMAC valid: " + verifyHmac(original, tag, key));
        System.out.println("HMAC changed message: " +
                verifyHmac(modified, tag, key));
        System.out.println("HMAC changed tag: " +
                verifyHmac(original, tamperedTag, key));
        System.out.println("HMAC missing tag: " +
                verifyHmac(original, null, key));
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac DigestCompareDemo.java
java DigestCompareDemo
```

Stdout chính xác (dù key và tag được tạo ngẫu nhiên mỗi lần):

```text
SHA-256 length: 32
Same message: true
Different message: false
Short digest: false
HMAC valid: true
HMAC changed message: false
HMAC changed tag: false
HMAC missing tag: false
```

**Giải thích theo các bước:**

1. Hai lần băm `message=v1` tạo ra hai mảng riêng nhưng cùng byte. `MessageDigest.isEqual(digestA, digestBCopy)` trả `true`; phép so sánh reference `digestA == digestBCopy` sẽ trả `false`.
2. `message=v2` khác thông điệp ban đầu nên trong ví dụ tạo ra digest khác. Cắt bớt một byte của digest khiến độ dài chỉ còn 31 byte, kết quả cũng `false`.
3. `KeyGenerator.getInstance("HmacSHA256")` tạo **khóa bí mật dùng để minh họa**, không hardcode key trong source. Hệ thống thật phải quản lý key bằng keystore/KMS hoặc cơ chế tương đương.
4. `Mac.getInstance("HmacSHA256")` và `mac.init(key)` tạo tag từ khóa và byte thông điệp. Bên nhận tính lại `expectedTag` từ *cùng khóa* và *cùng byte thông điệp*.
5. `verifyHmac` từ chối tag thiếu/sai độ dài theo hợp đồng **đủ 32 byte**, sau đó gọi `MessageDigest.isEqual(expectedTag, suppliedTag)`. Expected tag đặt bên trái và được tính độc lập.
6. Đổi byte thông điệp hoặc tag làm xác minh thất bại; null cũng bị từ chối. Đây là hành vi của hệ thống mẫu, không phải chứng minh không tồn tại mọi kiểu tấn công.

**Phạm vi demo:** chương trình sinh key mới ở mỗi lần chạy và tạo tag/verify trong cùng process. Muốn xác minh tag do ứng dụng khác tạo, hai bên phải sử dụng cùng khóa được phân phối an toàn và thống nhất định dạng byte. Không được khởi tạo một khóa ngẫu nhiên mới mỗi lần xác minh tag đã nhận.

## 6. Digest thường và MAC: cùng dùng isEqual, khác nhau về bảo đảm

### 6.1. SHA-256 chỉ kiểm tra digest

Nếu ta có SHA-256 của một tệp từ **nguồn tin cậy**, tính lại digest rồi so sánh sẽ giúp phát hiện sai khác dữ liệu. Đây là chức năng kiểm tra tính toàn vẹn trong điều kiện **giá trị kỳ vọng được bảo vệ**.

Nếu kẻ tấn công có thể sửa cả tệp **và** digest đi kèm, họ chỉ cần tính lại SHA-256. Phép so sánh trả `true` dù dữ liệu không còn đáng tin. `isEqual` không tạo ra bí mật hay quyền hạn.

### 6.2. HMAC dùng để xác thực tính toàn vẹn và nguồn biết khóa

HMAC lấy khóa bí mật và thông điệp làm đầu vào. Bên xác minh giữ khóa hợp lệ, tự tính tag kỳ vọng, rồi so sánh với tag nhận được. Theo giả định an toàn của HMAC và quản lý khóa đúng, kẻ không có khóa không thể tùy ý thay thông điệp và tạo tag hợp lệ.

```text
BÊN GỬI                              BÊN NHẬN
message bytes                        message bytes
     |                                    |
key + Mac(HmacSHA256)          key + Mac(HmacSHA256)
     |                                    |
     v                                    v
receivedTag  ---------------->      expectedTag
                                         |
                         MessageDigest.isEqual(
                             expectedTag, receivedTag)
                                         |
                                   true / false
```

Sơ đồ này không cho thấy việc **truyền key**: key phải được chia sẻ bảo mật từ trước hoặc truy xuất qua hệ thống quản lý khóa. HMAC không mã hóa nội dung, không chặn replay nếu giao thức thiếu nonce/timestamp/messageId, không tự kiểm tra quyền truy cập. Cần đưa metadata bảo mật quan trọng vào thông điệp đã xác thực và áp dụng chính sách server phù hợp.

### 6.3. Không áp dụng trực tiếp cho mật khẩu hoặc chữ ký số

- **Mật khẩu:** Lưu `SHA-256(password)` rồi dùng `isEqual` không chống được dò mật khẩu offline khi database rò rỉ. Dùng password-hashing/KDF chuyên dụng có salt và chi phí phù hợp (Argon2id, scrypt, bcrypt hoặc PBKDF2 theo yêu cầu hệ thống), và hàm verify của thư viện được chọn.
- **Chữ ký số:** Muốn kiểm tra chữ ký của bên giữ private key thì dùng `java.security.Signature.verify` với khóa public, thuật toán và policy thích hợp. So sánh hai digest bằng `isEqual` không thay thế chữ ký số.
- **Bảo mật nội dung:** `isEqual` không mã hóa dữ liệu. Muốn bảo mật tính riêng tư và toàn vẹn, dùng cơ chế mã hóa được xác thực như AES-GCM theo thiết kế đúng.

## 7. Cách tổ chức verification trong sản phẩm

1. **Xác định chuẩn byte:** tên thuật toán, UTF-8, thứ tự trường, canonicalization, số phiên bản, định dạng Base64/hex và điều gì chính xác được đưa vào HMAC. JSON có thể có cùng ý nghĩa nhưng khác whitespace/thứ tự trường; nếu byte không giống, MAC sẽ khác.
2. **Giới hạn dữ liệu đầu vào:** kiểm tra kích thước request, phiên bản, cú pháp và độ dài tag **trước** khi xử lý dữ liệu lớn. Nếu yêu cầu full HmacSHA256, không chấp nhận tag 31 byte hay giá trị rỗng. Đừng tự thêm zero byte hoặc cắt tag để cho khớp.
3. **Lấy khóa từ nguồn tin cậy:** dùng keyId đã xác minh, phân quyền theo tenant, rotation và tách key khỏi ciphertext/tag. Không log hoặc hardcode khóa production.
4. **Tính expected tag ở server:** dùng `Mac` và cùng thông điệp được canonical hóa. Instance `Mac` có trạng thái, vì vậy tránh chia sẻ cùng instance đang update giữa nhiều thread không có cơ chế kiểm soát.
5. **So sánh bytes, không so sánh hex string:** decode tag đúng định dạng, xác nhận độ dài, rồi `MessageDigest.isEqual(expectedTag, receivedTag)`. Khi cần che tín hiệu thời gian nhạy cảm hơn, đánh giá cả đường request, including parse và error response; không coi phép so sánh đơn lẻ là tất cả.
6. **Kiểm tra nghiệp vụ và replay:** MAC hợp lệ vẫn có thể là một thông điệp cũ được gửi lại. Nếu yêu cầu, đưa timestamp/nonce/messageId được xác thực vào protocol, lưu trạng thái dùng một lần và kiểm tra hết hạn.

Về chuỗi hex/Base64: `Base64` chỉ mã hóa cách trình bày byte, không mã hóa bí mật. Với digest nhị phân không dùng `new String(digestBytes)` hoặc `digestBytes.toString()` để kiểm tra. Decoder phải rõ ràng khi gặp ký tự lạ, chuỗi sai padding hay byte vượt giới hạn; không làm ngầm nhiều kiểu decode khác nhau.

### Về truncated MAC

Một số giao thức chuẩn có thể quy định tag HMAC được cắt ngắn với chính sách độ dài cố định. Việc cắt ngắn làm thay đổi độ khó giả mạo; không cho client tự quyết định giữ bao nhiêu byte và không chấp nhận “prefix khớp” nếu protocol yêu cầu tag nguyên vẹn. Ví dụ trong chương trình dùng **full tag HmacSHA256 32 byte**, vì vậy kiểm tra `suppliedTag.length != expectedTag.length` là chủ đích.

## 8. Bảng kiểm tra phạm vi bảo đảm

| Nhận định | Đúng hay sai? |
| --- | --- |
| `MessageDigest.isEqual` tính SHA-256 cho ta | **Sai**: nó chỉ so sánh hai `byte[]`. |
| Hai mảng có cùng độ dài và từng byte giống nhau sẽ được coi bằng nhau | **Đúng** với đầu vào digest hợp lệ. |
| API có đặc tính thời gian nhằm tránh lộ vị trí byte sai khác | **Đúng**, với phạm vi và các ngoại lệ nêu trong Implementation Note. |
| Thời gian **mọi** lời gọi luôn bằng nhau, kể cả `null`/rỗng/cùng reference | **Sai**; có đường xử lý biên và đặc tính thời gian chỉ cho phép suy luận có điều kiện. |
| Toàn bộ HTTP endpoint trở thành constant-time nhờ dùng `isEqual` | **Sai**: decode, I/O, hash, authentication, JIT, network ngoài phạm vi đó. |
| So sánh SHA-256 thông thường tạo ra xác thực nguồn gửi | **Sai** nếu không bảo vệ digest kỳ vọng; kẻ tấn công có thể tính lại. |
| So sánh HMAC đúng bằng API giúp hạn chế timing leak tại bước đối chiếu tag | **Đúng**, nhưng cần HMAC với khóa bí mật an toàn và giao thức đúng. |
| Digest bằng nhau tuyệt đối chứng minh hai thông điệp gốc giống nhau | **Sai** về mặt toán học vì có thể xảy ra collision. |
| `isEqual` tự chặn replay, tăng độ khó dò mật khẩu, mã hóa nội dung hoặc xác minh chữ ký số | **Sai**; từng việc cần cơ chế riêng. |

## 9. Các lỗi thường gặp

| Lỗi | Hậu quả | Sửa |
| --- | --- | --- |
| Dùng `==` hay `byte[].equals` cho digest | Hai mảng cùng nội dung nhưng khác object bị xem là không bằng | Dùng `MessageDigest.isEqual`; `Arrays.equals` nếu không cần thuộc tính timing. |
| Dùng `Arrays.equals`/vòng lặp có `return` sớm cho HMAC | Không có bảo đảm tránh phụ thuộc vào vị trí byte sai | `MessageDigest.isEqual` với expected tag cố định. |
| Dùng `String.equals` trên hex/Base64 | So sánh chuỗi, nguy cơ xử lý encoding không nhất quán và không có hợp đồng timing | Decode nghiêm ngặt thành `byte[]`. |
| Coi “constant-time” là phản hồi HTTP luôn cùng thời gian | Bỏ qua parse, I/O, lỗi và thay đổi độ dài | Xác định threat model và đánh giá pipeline đầy đủ. |
| Tin tag `null`, rỗng hoặc sai độ dài | Mở thêm đường xử lý ngoài hợp đồng | Từ chối theo định dạng giao thức. |
| Client gửi cả message lẫn plain SHA digest, server coi là authenticated | Kẻ tấn công có thể gửi message giả cùng digest tự tính | HMAC với khóa server hoặc chữ ký số. |
| Hai phía hash JSON/Unicode khác byte | MAC hợp lệ từ phía gửi vẫn không khớp phía nhận | Thống nhất canonical byte representation. |
| Lưu SHA-256(password) thay vì password KDF | Dễ bị dò offline với mật khẩu yếu | Password hash/KDF có salt và cấu hình chi phí an toàn. |
| So sánh kết quả nhưng không kiểm tra quyền/replay | MAC có thể hợp lệ cho hành động sai ngữ cảnh hoặc request cũ | Bao phủ metadata trong MAC và kiểm soát nghiệp vụ, replay, keyId. |

## 10. Bài tập tự kiểm tra

1. Hai `byte[]` khác reference nhưng chứa cùng 32 byte: `a == b`, `Arrays.equals(a,b)` và `MessageDigest.isEqual(a,b)` trả những gì?
2. Vì sao phép so sánh `SHA-256(file)` với checksum do client gửi không tự chứng minh file đáng tin?
3. Khi so sánh HMAC, vì sao nên đặt tag kỳ vọng **được tính lại** ở đối số thứ nhất?
4. Điều gì không được bảo đảm khi tag bên nhận là `null`, rỗng hoặc có độ dài sai?
5. Tại sao thời gian xử lý trong HTTP endpoint có thể khác nhau dù `MessageDigest.isEqual` đã dùng đúng?
6. Giữa plain SHA-256, HmacSHA256, password hashing và chữ ký số, trường hợp nào cần khóa bí mật chung, trường hợp nào dùng public key?
7. Nếu tag HMAC hợp lệ nhưng request được gửi lại lần thứ hai, `isEqual` có tự phát hiện replay không?

**Thực hành:** thay byte đầu hoặc byte cuối của một digest/tag trong ví dụ và quan sát Boolean; so sánh với `Arrays.equals` về **ngữ nghĩa kết quả**, không dùng vài lần đo thời gian để tuyên bố an ninh timing. Thêm kiểm tra thay payload, tag ngắn 31 byte và request trùng messageId theo chính sách của ứng dụng.

## 11. Tài liệu chính thức

- [Java SE 17: MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html) — `isEqual`, `digest` và Implementation Note.
- [Java SE 24: MessageDigest](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/MessageDigest.html) — Implementation Note làm rõ trường hợp đối số thứ hai `null`/rỗng.
- [Java SE 17: Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html) — tạo và xác minh MAC/HMAC.
- [OpenJDK: MessageDigest.java](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/security/MessageDigest.java) — tham khảo mã nguồn; chi tiết implementation có thể thay đổi theo phiên bản.
