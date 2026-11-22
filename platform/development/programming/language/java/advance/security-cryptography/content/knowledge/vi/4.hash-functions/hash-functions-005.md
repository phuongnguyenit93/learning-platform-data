# 4.5 Phân biệt checksum, Object.hashCode và digest mật mã

Ba cách gọi “hash” dễ bị đánh đồng trong Java: **checksum** để phát hiện lỗi truyền/lưu dữ liệu, **`hashCode()`** để hỗ trợ tìm kiếm và so sánh đối tượng trong các cấu trúc như `HashMap`, và **digest mật mã** để tạo dấu vân tay có tính kháng tấn công của một chuỗi byte. Chúng có thể cùng trả về các con số hoặc chuỗi hex, nhưng **mục tiêu, dữ liệu đầu vào, tính chất va chạm và mức độ an toàn hoàn toàn khác nhau**.

Bài học thuộc chủ đề **Hàm băm** và tập trung vào việc chọn đúng kỹ thuật trong Java, không nhầm “kiểm tra lỗi” với “xác thực nguồn gốc”.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Phân biệt **checksum chống lỗi ngẫu nhiên**, **`hashCode()` phục vụ cấu trúc dữ liệu**, và **cryptographic digest** như SHA-256.
2. Nêu chính xác hợp đồng `equals()`/`hashCode()`, ý nghĩa va chạm và hậu quả khi khóa của `HashMap` bị thay đổi.
3. Biết tại sao CRC32/CRC32C/Adler32 khác SHA-256, và tại sao **SHA-256 riêng lẻ cũng không xác thực được người gửi**.
4. Viết Java 17+ tính checksum, `String.hashCode()` và SHA-256; đọc đúng từng kết quả và biết khi nào cần truyền **byte**, khi nào cần định nghĩa **đối tượng**.
5. Biết chọn checksum, digest, HMAC/chữ ký số hoặc password KDF theo yêu cầu thực tế.

## 2. Bảng đối chiếu nhanh

| Tiêu chí | Checksum | `Object.hashCode()` / phương thức `hashCode()` | Digest mật mã |
| --- | --- | --- | --- |
| Câu hỏi giải quyết | Byte có **vô tình** bị hỏng/thay đổi không? | Đặt/tìm đối tượng vào **bucket** nào và nhanh chóng lọc ứng viên so sánh? | Hai nội dung byte có cùng **dấu vân tay mật mã** không, dưới giả định thuật toán kháng va chạm? |
| Đầu vào thường gặp | Chuỗi byte theo định dạng đã xác định | Một đối tượng, qua phương thức `hashCode()` của lớp | Chuỗi byte bất kỳ; có thể đưa vào theo nhiều chunk |
| Ví dụ | CRC32, CRC32C, Adler32 | `String.hashCode()`, `record.hashCode()`, `Objects.hash(...)` | SHA-256, SHA-384/512, SHA-3 |
| Kết quả | Thường checksum ngắn (ví dụ CRC32 là 32 bit) | Java trả về **`int` có dấu 32 bit** | SHA-256 trả về **32 byte (256 bit)**; hiển thị hex thành 64 ký tự |
| Tính chất chính | Phát hiện tốt các dạng **lỗi truyền/lưu không chủ ý** theo thiết kế mã kiểm lỗi | Bằng nhau theo `equals()` thì **bắt buộc** có cùng hash; khác nhau **có thể** cùng hash | Được thiết kế chống tìm tiền ảnh, tiền ảnh thứ hai và va chạm một cách hiệu quả |
| Kẻ tấn công chủ động | Có thể sửa dữ liệu rồi tính lại checksum; CRC không phải cơ chế bảo mật | Có thể tạo nhiều đối tượng khác nhau cùng `hashCode()`; không xác thực và không bảo mật | Khó tạo va chạm có chủ đích với thuật toán mạnh, nhưng **ai cũng tính được digest** của dữ liệu họ chọn |
| Mục đích đúng | Kiểm lỗi gói tin, bản ghi, định dạng lưu trữ, hệ thống kiểm soát lỗi | `HashMap`, `HashSet`, khóa bảng băm, nhận diện ứng viên trước khi so `equals` | So khớp file với digest **đáng tin cậy**, content addressing, thành phần của HMAC/chữ ký số và giao thức mật mã |

**Ba câu cần nhớ:**

- **Checksum khác digest mật mã:** phát hiện byte hỏng ngẫu nhiên khác với chống người cố tình tạo nội dung giả trùng dấu vân tay.
- **`hashCode()` khác digest:** trả về cùng một số **không nói rằng hai đối tượng bằng nhau**, càng không nói dữ liệu chưa bị sửa.
- **Digest khác xác thực:** SHA-256 đủ mạnh về va chạm vẫn không chứng minh **ai** đã cung cấp byte hoặc ai công bố digest; muốn chống giả mạo nguồn gốc cần điểm neo tin cậy, MAC hoặc chữ ký số.

## 3. Checksum: phát hiện lỗi dữ liệu ngoài ý muốn

### 3.1. Cơ chế

Một checksum tính từ byte dữ liệu:

~~~text
Dữ liệu gốc: bytes ──checksum algorithm──> checksum A
Dữ liệu nhận: bytes ─checksum algorithm──> checksum B
A == B ?  →  nhiều khả năng dữ liệu không bị hỏng theo mô hình lỗi của thuật toán
~~~

Các giao thức lưu trữ/truyền tải thường đặt checksum bên cạnh nội dung để phát hiện lỗi do nhiễu tín hiệu, lỗi ghi đọc, lỗi đường truyền hoặc ghi nhận sai. **Không thể suy luận “A == B thì hai chuỗi byte chắc chắn giống nhau”**: đầu ra hữu hạn khiến va chạm tồn tại.

**CRC (Cyclic Redundancy Check)** diễn giải dữ liệu dưới dạng bit và tính số dư theo một đa thức quy ước. Thiết kế đa thức giúp phát hiện hiệu quả nhiều mẫu lỗi (chẳng hạn một bit bị lật hoặc nhiều lỗi burst trong phạm vi năng lực mã). CRC **không được thiết kế để ngăn người tấn công cố ý thay dữ liệu**, vì thuật toán và phép tính đều công khai, có cấu trúc đại số cho phép điều chỉnh/tính lại checksum.

- **CRC32 (`java.util.zip.CRC32`)** thường gặp trong ZIP/GZIP và nhiều định dạng cũ; với `"abc"` dưới UTF-8 có giá trị hex `352441c2`.
- **CRC32C (`java.util.zip.CRC32C`)** dùng đa thức Castagnoli, được nhiều hệ thống lưu trữ/truyền tải chọn; với đúng byte `"abc"` cho `364b3fb7`. **CRC32 và CRC32C không hoán đổi được**, dù cùng là checksum 32 bit. Bên gửi và bên nhận phải thống nhất biến thể, thứ tự byte và quy ước đóng gói.
- **Adler32 (`java.util.zip.Adler32`)** dùng phép cộng kiểm tra dạng khác, thường dùng trong zlib; `"abc"` cho `024d0127`. Nó cũng **không phải hàm băm mật mã**.
- Checksum rất đơn giản kiểu tổng byte đôi khi dùng cho nhu cầu phát hiện lỗi cơ bản, nhưng dễ bỏ sót nhiều dạng lỗi hơn CRC chuyên dụng.

Một CRC32 có **32 bit đầu ra** nên không thể ánh xạ duy nhất mọi thông điệp. Với hai giá trị phân phối gần đều, xác suất trùng ngẫu nhiên xấp xỉ `2^-32`; đây **không phải** xác suất bảo đảm chống sửa đổi có chủ đích. CRC có những quan hệ tuyến tính khiến kẻ tấn công có thể chủ động dựng dữ liệu cùng CRC theo nhiều cách.

Trong Java, `Checksum.update(byte[], offset, len)` nạp byte, `Checksum.getValue()` trả giá trị dưới dạng `long` (vì checksum 32 bit thường xem là **không dấu**), còn `reset()` cho phép tái sử dụng đối tượng. Muốn tạo checksum cho **hai thông điệp độc lập**, cần `reset()` trước thông điệp mới hoặc tạo đối tượng mới; đừng vô tình tính checksum của dữ liệu nối tiếp.

### 3.2. Checksum dùng khi nào?

Dùng checksum khi mục tiêu là **phát hiện sai hỏng không chủ ý** và giao thức đã quy định thuật toán. Ví dụ một gói dữ liệu trên đường truyền đã được **bảo vệ an ninh bằng cơ chế khác** vẫn có thể dùng CRC để kiểm lỗi hiệu quả ở tầng thấp. Nếu cần chứng minh **nhà phát hành đáng tin** hoặc chống đối thủ giả mạo, checksum **không thay** HMAC/chữ ký số.

Một checksum khớp là tín hiệu đáng tin **trong đúng mô hình lỗi và nguồn checksum đã xác định**, không phải bằng chứng không thể sửa hay bằng chứng danh tính.

## 4. `Object.hashCode()`: cơ chế hỗ trợ cấu trúc dữ liệu Java

### 4.1. `hashCode()` thực chất là gì?

`Object` khai báo phương thức:

~~~java
public int hashCode()
~~~

Lớp con có thể **ghi đè** để định nghĩa mã băm dựa trên trạng thái có ý nghĩa của đối tượng. `String.hashCode()` là ví dụ nổi bật; `record` trong Java cũng cung cấp triển khai `equals()`/`hashCode()` phù hợp với các thành phần record.

Một `HashMap<K,V>` dùng mã băm để xác định vị trí/nhóm bucket ứng viên, rồi sử dụng `equals()` để phân biệt các khóa có mã băm trùng nhau. `HashSet` áp dụng tương tự cho phần tử.

- **Hợp đồng bắt buộc:** Nếu `a.equals(b) == true` thì `a.hashCode() == b.hashCode()`.
- **Chiều ngược lại sai:** Hai đối tượng **không bằng nhau** vẫn có thể có cùng `hashCode()` (collision).
- Nếu trạng thái liên quan `equals` không đổi, gọi `hashCode()` nhiều lần trong cùng một lần chạy phải nhất quán. Không có yêu cầu chung rằng hash code của mọi lớp phải ổn định qua những lần chạy JVM riêng biệt.
- Nếu ghi đè `equals()`, cần ghi đè `hashCode()` nhất quán. Thiếu một trong hai sẽ làm các collection dựa trên hash hoạt động sai về mặt logic.

**Ví dụ va chạm có thể tái hiện:**

~~~text
"Aa".hashCode() = 2112
"BB".hashCode() = 2112
"Aa".equals("BB") = false
~~~

Điều này **không khiến `HashMap` coi `"Aa"` và `"BB"` là cùng khóa**. Nó phải kiểm tra `equals()` sau khi các ứng viên cùng nhóm hash. Bảng băm chịu được va chạm; va chạm dày đặc có thể ảnh hưởng hiệu năng, nên chất lượng phân phối hash code vẫn rất quan trọng.

### 4.2. `Object` mặc định, `String` và `Objects` không giống nhau

- `new Object().hashCode()` dùng triển khai mặc định của `Object`, thường gắn với nhận diện đối tượng trong JVM, nhưng **không được Java cam kết** là địa chỉ bộ nhớ, giá trị duy nhất hoặc định danh bền vững.
- `String.hashCode()` ghi đè theo nội dung chuỗi với thuật toán xác định trong đặc tả Java; nhiều chuỗi khác nhau vẫn có thể va chạm. Nó là một `int` và **không** phải SHA-256.
- `System.identityHashCode(obj)` lấy kiểu hash nhận diện của `Object` ngay cả khi lớp ghi đè `hashCode()`; vẫn không duy nhất, không bền vững và không có tính chất mật mã.
- `Objects.hashCode(obj)` là tiện ích xử lý `null` (trả 0 nếu null, ngược lại gọi `obj.hashCode()`); `Objects.hash(fields...)` kết hợp nhiều trường theo cách phục vụ hợp đồng Java, **không phải hàm băm mật mã**. Đối với mã hiệu năng nhạy cảm, cân nhắc chi phí tạo mảng varargs từ `Objects.hash(...)`.

**Khóa có thể thay đổi là bẫy:** Nếu bạn đưa một đối tượng vào `HashMap` rồi sửa trường tham gia `equals/hashCode`, lần tra cứu sau có thể tìm ở bucket khác và thất bại dù đối tượng vẫn tồn tại trong map. Ưu tiên **khóa bất biến**, ví dụ `String` hoặc `record` chứa các thành phần bất biến, và không thay đổi trạng thái làm nên danh tính khóa.

Một hash code 32 bit cũng **không phải ID duy nhất**, fingerprint nội dung, khóa bảo mật hoặc giá trị phù hợp để đưa ra quyết định quyền truy cập.

## 5. Digest mật mã: dấu vân tay byte có tính kháng tấn công

### 5.1. Cơ chế và tính chất

Một hàm băm mật mã như SHA-256 nhận chuỗi byte độ dài bất kỳ rồi trả digest độ dài cố định:

~~~text
UTF-8("abc") → [0x61, 0x62, 0x63]
SHA-256(bytes) → 32 byte
Hex biểu diễn digest → ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

**Hex không phải digest khác:** Nó chỉ là cách hiển thị digest nhị phân. Với SHA-256, 32 byte hiển thị thành 64 ký tự hex. Base64 cũng có thể biểu diễn chính 32 byte ấy dưới dạng text khác.

Một hash mật mã an toàn hướng tới:

1. **Preimage resistance:** biết `H(m)`, khó tìm được một `m` cho ra đúng digest ấy.
2. **Second-preimage resistance:** biết trước `m`, khó tìm `m' != m` có cùng digest.
3. **Collision resistance:** khó chủ động tìm **bất kỳ** cặp `m != m'` nào có cùng digest. Với digest lý tưởng 256 bit, chi phí tìm va chạm theo phương pháp sinh nhật cỡ `2^128` phép thử, khác với không gian tất cả `2^256` digest.

“Khó” có nghĩa về **chi phí tính toán khi dùng đúng thuật toán/độ dài**, không có nghĩa toán học không tồn tại va chạm. Bởi vậy digest thường phù hợp so khớp nội dung hoặc content-addressing, nhưng vẫn cần xác minh byte, ngữ cảnh, thuật toán và nguồn digest tùy mục đích.

- **SHA-256** là lựa chọn phổ biến và có sẵn trong JDK qua `MessageDigest.getInstance("SHA-256")`.
- **SHA-512/SHA-3** có thể phù hợp khi giao thức/yêu cầu chỉ rõ. Đừng tự thay thuật toán hai đầu nếu định dạng cố định.
- **MD5 và SHA-1** có vấn đề va chạm nghiêm trọng; không chọn cho yêu cầu chống kẻ tấn công tạo nội dung giả trùng digest.
- **SHA-256 không dùng để lưu mật khẩu trực tiếp:** mật khẩu thường có entropy thấp. Dùng password hashing/KDF chậm và có salt riêng (Argon2id, scrypt hoặc PBKDF2 theo hệ sinh thái và thông số an toàn), khác việc hash một file.

### 5.2. Digest không tự xác thực nguồn gốc

Giả sử website cho tải `app.zip` và cũng đặt `SHA256SUMS` ngay cùng website. Nếu attacker chiếm website, họ có thể **thay cả file và dòng SHA-256** cho khớp file độc hại. Kết quả `MessageDigest` của bạn sẽ khớp nhưng **không chứng minh đúng nhà phát hành**.

Chọn bổ sung theo mô hình đe dọa:

- **Digest từ kênh đáng tin độc lập**: có thể dùng làm giá trị kỳ vọng để phát hiện thay đổi trên bản tải về.
- **HMAC**: hai bên có cùng secret có thể tạo/xác minh thẻ xác thực gắn với byte dữ liệu; phù hợp xác thực thông điệp trong hệ thống cùng chia sẻ khóa.
- **Chữ ký số**: bên ký giữ private key; người nhận dùng **public key đã được xác thực** để kiểm chữ ký, phù hợp phân phối artifact cho nhiều bên kiểm tra.
- **TLS/AEAD**: khi cần bảo vệ nội dung trong quá trình truyền hoặc lưu trữ, dùng giao thức/thuật toán phù hợp; SHA-256 **không mã hóa** nội dung.

Cả checksum, `hashCode()` lẫn SHA-256 đều không cần secret để tính. **Sự khác biệt về bảo mật nằm ở tính chất toán học và cách sử dụng**, còn bằng chứng danh tính phải đến từ giao thức tin cậy.

## 6. Đối tượng Java và chuỗi byte không phải cùng dữ liệu đầu vào

Muốn so sánh chính xác, phải xác định **đang băm cái gì**.

| Đầu vào/thao tác | Ý nghĩa |
| --- | --- |
| `"abc".hashCode()` | Mã băm theo nội dung `String` dùng cho collection; giá trị `int` là `96354`. |
| `CRC32.update("abc".getBytes(UTF_8))` | Checksum của **3 byte** UTF-8: `61 62 63`. |
| `SHA-256("abc".getBytes(UTF_8))` | Digest mật mã của **cùng 3 byte** UTF-8, 32 byte kết quả. |
| `sha256(fileBytes)` | Hash chính xác byte của file, **không** mặc nhiên là hash chuỗi filename hay nội dung đã normalize. |
| `sha256(serialize(object))` | Hash bản serialize theo quy tắc đã định; thay serialization có thể thay digest dù đối tượng có cùng ý nghĩa nghiệp vụ. |

**Những khác biệt thường bị bỏ sót:**

- **Encoding:** `UTF-8` khác `UTF-16`. `String.hashCode()` dựa trên các đơn vị ký tự UTF-16 của `String`, trong khi `MessageDigest` nhận **byte**; phải chọn `StandardCharsets.UTF_8` hoặc định dạng đã thống nhất.
- **Xuống dòng:** `"abc"`, `"abc\n"`, file dùng LF và file dùng CRLF có byte khác nhau → SHA-256/CRC khác.
- **Unicode normalization:** hai chuỗi trông giống nhau có thể có chuỗi mã Unicode/byte khác nhau (ví dụ ký tự có dấu ở dạng kết hợp và dựng sẵn). Chỉ normalize **nếu giao thức quy định** rồi băm đúng bản đã được chuẩn hóa.
- **JSON và dữ liệu có cấu trúc:** khác thứ tự field, khoảng trắng hoặc biểu diễn số có thể cho byte khác dù nghiệp vụ coi tương đương. Nếu cần ký/hash dữ liệu có cấu trúc qua nhiều ngôn ngữ, thống nhất **canonical serialization** trước.
- **Định dạng/lý lịch thuật toán:** gửi cùng checksum cần kèm hoặc quy định rõ CRC32 hay CRC32C, cách đóng gói và byte order. Với digest, cần biết SHA-256 hay thuật toán khác; biểu diễn hex có thể chữ hoa/chữ thường nhưng **byte digest** mới là bản chất.

**Không sử dụng `Object.toString()`, `hashCode()` hoặc serialize mặc định tùy tiện để tạo digest bền vững của đối tượng.** Chúng không hứa hẹn canonicalization, ổn định liên phiên bản hay mức độ xác thực phù hợp.

## 7. Ví dụ Java 17+: một chương trình, ba loại giá trị

Ví dụ dùng API chuẩn trong JDK, không cần Maven hay thư viện ngoài. Chương trình cố tình chọn `"Aa"` và `"BB"` để tạo **va chạm `String.hashCode()`**, rồi chứng minh `HashMap` vẫn lưu được cả hai khóa. Đồng thời tính checksum và digest của `"abc"`.

Lưu dưới tên **`ChecksumHashDigestDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.HashMap;
import java.util.Map;
import java.util.zip.Adler32;
import java.util.zip.CRC32;
import java.util.zip.CRC32C;
import java.util.zip.Checksum;

public class ChecksumHashDigestDemo {
    static byte[] utf8(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    static String checksum(Checksum checksum, byte[] data) {
        checksum.update(data, 0, data.length);
        return "%08x".formatted(checksum.getValue());
    }

    static byte[] sha256(byte[] data) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(data);
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = utf8("abc");
        System.out.println("CRC32(abc)     = " + checksum(new CRC32(), bytes));
        System.out.println("CRC32C(abc)    = " + checksum(new CRC32C(), bytes));
        System.out.println("Adler32(abc)   = " + checksum(new Adler32(), bytes));
        System.out.println("SHA-256(abc)   = "
                + HexFormat.of().formatHex(sha256(bytes)));

        String first = "Aa";
        String second = "BB";
        System.out.println("hashCode(Aa)   = " + first.hashCode());
        System.out.println("hashCode(BB)   = " + second.hashCode());
        System.out.println("Aa equals BB?  = " + first.equals(second));

        Map<String, String> values = new HashMap<>();
        values.put(first, "first");
        values.put(second, "second");
        System.out.println("Map size       = " + values.size());
        System.out.println("Map[BB]        = " + values.get("BB"));

        System.out.println("SHA equals?    = " + MessageDigest.isEqual(
                sha256(utf8(first)), sha256(utf8(second))));
        System.out.println("CRC32 matches? = " + checksum(new CRC32(), bytes)
                .equals(checksum(new CRC32(), utf8("abd"))));
    }
}
~~~

Chạy:

~~~bash
javac ChecksumHashDigestDemo.java
java ChecksumHashDigestDemo
~~~

Kết quả chính xác với JDK 17+:

~~~text
CRC32(abc)     = 352441c2
CRC32C(abc)    = 364b3fb7
Adler32(abc)   = 024d0127
SHA-256(abc)   = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
hashCode(Aa)   = 2112
hashCode(BB)   = 2112
Aa equals BB?  = false
Map size       = 2
Map[BB]        = second
SHA equals?    = false
CRC32 matches? = false
~~~

**Phân tích output:**

1. CRC32, CRC32C và Adler32 nhận **cùng 3 byte** nhưng tạo kết quả khác nhau do thuật toán khác nhau. Không dùng giá trị từ thuật toán này để xác minh thuật toán kia.
2. SHA-256 nhận đúng các byte ấy nhưng kết quả dài 256 bit, có các mục tiêu chống tấn công mà CRC không có. Digest hex dài 64 ký tự.
3. `"Aa"` và `"BB"` **cùng `hashCode` nhưng `equals()` trả `false`**. `HashMap` dùng cả mã băm và quan hệ bằng nhau nên có hai entry; không có chuyện cứ trùng hash là bị ghi đè khóa.
4. SHA-256 của `"Aa"` và `"BB"` không bằng nhau. Đây **không** chứng minh SHA-256 không bao giờ va chạm; chỉ là phép kiểm cụ thể cho hai thông điệp này.
5. Checksum của `"abc"` và `"abd"` khác nhau trong ví dụ. **Không** suy ra CRC có thể chống người cố ý sửa byte rồi tạo checksum trùng.

Ở ví dụ, mỗi checksum dùng đối tượng `new CRC32()`/`new CRC32C()`/`new Adler32()` riêng, tránh cộng dồn trạng thái giữa các thông điệp. `MessageDigest.getInstance("SHA-256").digest(data)` tính digest trên byte; `HexFormat` chỉ chuyển digest thành ký tự hex. `MessageDigest.isEqual` so sánh hai mảng digest mà không dừng ngay ở byte khác đầu tiên; với các giao thức xác thực, vẫn phải xác minh tất cả điều kiện đầu vào và độ dài theo thiết kế.

### 7.1. Hash file lớn bằng luồng, tránh đọc toàn bộ vào RAM

Khi file có thể lớn, đừng buộc `Files.readAllBytes(...)` nạp hết nội dung. Dùng `MessageDigest.update(...)` nhiều lần; kết quả tương đương hash một lần với **đúng chuỗi byte nối lại**, không phụ thuộc cách chia các chunk.

Đoạn **phương thức minh họa sau đây cần đặt trong một class Java**, không phải một chương trình độc lập. Nó sử dụng các import `java.io.InputStream`, `java.nio.file.Files`, `java.nio.file.Path` và `java.security.MessageDigest`:

~~~java
static byte[] sha256File(Path file) throws Exception {
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    try (InputStream in = Files.newInputStream(file)) {
        byte[] buffer = new byte[8192];
        int count;
        while ((count = in.read(buffer)) != -1) {
            digest.update(buffer, 0, count);
        }
    }
    return digest.digest();
}
~~~

Gọi `HexFormat.of().formatHex(sha256File(Path.of("archive.zip")))` để nhận chuỗi hex cho byte file thực tế. Muốn kiểm tra bản tải, so kết quả với digest kỳ vọng từ **nguồn tin cậy**. Ghi nhận thêm thuật toán, thời điểm, tên artifact và kênh nhận digest để giảm nhập nhằng trong vận hành.

**Lưu ý API:** Các đối tượng `MessageDigest`/`Checksum` có trạng thái bên trong. Không chia sẻ cùng một instance cho các luồng đang cập nhật độc lập nếu không có đồng bộ và quy tắc reset rõ ràng. Ví dụ đầy đủ tạo instance cho mỗi phép tính.

## 8. Chọn đúng kỹ thuật trong tình huống thực tế

| Tình huống | Kỹ thuật thích hợp | Lý do |
| --- | --- | --- |
| Đọc bản ghi từ đĩa, muốn phát hiện bit hỏng ngẫu nhiên | Checksum theo chuẩn định dạng, như CRC32C | Nhanh, tập trung vào lỗi ngẫu nhiên; chưa chứng minh nguồn gốc |
| Một định dạng ZIP/GZIP quy định CRC32 | **CRC32 chính xác theo đặc tả** | Không được thay bằng CRC32C hoặc SHA-256 tùy ý |
| Triển khai `HashMap<CustomerKey, Order>` | `equals()` và `hashCode()` đúng hợp đồng; khóa bất biến | Chỉ phục vụ phân phối/tìm kiếm khóa |
| Dùng mã băm làm khóa định danh file phát hành | **SHA-256 của byte file** | Tính kháng va chạm tốt hơn checksum/hashCode cho content ID |
| Kiểm file tải xuống từ máy chủ có thể bị giả mạo | SHA-256 **từ kênh tin cậy** hoặc chữ ký số với khóa công khai đã xác thực | Digest tự công bố kèm file không chống kẻ sửa cả hai |
| Xác thực webhook giữa hai dịch vụ có shared secret | **HMAC-SHA256** cộng quy tắc chống replay | SHA-256 trần không có khóa xác thực |
| Cho nhiều khách hàng kiểm tra nhà phát hành bản cập nhật | **Chữ ký số**, ví dụ Ed25519 | Người kiểm có public key; chỉ người giữ private key ký |
| Lưu mật khẩu người dùng | **Password hashing/KDF** phù hợp, salt riêng và tham số chi phí đúng | SHA-256 đơn lẻ quá nhanh và không giải quyết tấn công đoán mật khẩu |
| Dùng CRC hoặc SHA-256 làm “mã hóa dữ liệu” | **Không đúng mục tiêu**; cần encryption nếu dữ liệu phải bí mật | Cả checksum lẫn digest đều không cung cấp cách giữ bí mật nội dung |

### 8.1. Case study: “File tải về và hash khớp mà vẫn nhiễm mã độc”

Quy trình yếu:

~~~text
Trang bị chiếm quyền
  ├── file release.zip  bị thay thành file độc hại
  └── SHA256SUMS       được tính lại tương ứng
Người dùng tải cả hai → SHA-256 khớp → vẫn có thể nhận file độc hại
~~~

Quy trình mạnh hơn: lấy khóa công khai nhà phát hành qua **kênh tin cậy**, xác minh chữ ký trên đúng artifact hoặc manifest đã định nghĩa, đồng thời kiểm dữ liệu và chính sách phiên bản. Digest hỗ trợ ràng buộc byte, chữ ký bảo vệ giá trị tham chiếu/người ký. Cơ chế phân phối khóa và thu hồi khóa vẫn quan trọng.

### 8.2. Case study: “Tôi lưu `hashCode()` của object vào database để deduplicate”

Thiết kế này sai vì:

- Chỉ có 32 bit, va chạm là bình thường khi dữ liệu tăng.
- Cách tính phụ thuộc lớp, trường, triển khai `equals/hashCode`; thay phiên bản code có thể thay giá trị.
- Một số hash code mặc định gắn với nhận diện đối tượng, không ổn định sau khi tạo đối tượng mới hay restart.
- Hai object được coi bằng nhau theo logic Java chưa chắc có cùng **byte serialize**, và ngược lại.

Muốn content-addressing, hãy tạo **serialization canonical** của những trường định nghĩa nội dung, rồi băm bằng SHA-256 (cùng namespace/schema version để tránh nhập nhằng). Vẫn phải dùng các ràng buộc dữ liệu và so sánh thích hợp nếu cần chắc chắn về danh tính nghiệp vụ, không coi digest là quyền sở hữu hay chữ ký.

### 8.3. Case study: “CRC32 mismatch nhưng SHA-256 match”

Nếu hai bên thực sự tính trên **chính xác cùng byte** và cùng thuật toán SHA-256, digest khớp nhưng CRC32 tính khác có thể do **quy trình CRC khác nhau**: một bên dùng CRC32C, quên reset `Checksum`, băm dữ liệu khác phạm vi, hoặc biểu diễn/đóng gói số dư theo endianness khác. Đừng vội suy ra một primitive “bị lỗi”. Đối chiếu byte đầu vào, thuật toán, thứ tự chunk, độ dài và metadata trước.

Nếu cả hai phép tính đều dùng chung thuật toán và byte chuẩn, về mặt toán học digest và CRC mỗi loại vẫn có khả năng va chạm riêng. Vì vậy **tránh khẳng định tuyệt đối** chỉ từ sự khớp của một giá trị băm.

## 9. Lỗi thường gặp khi code Java

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `hashCode()` để phát hiện file bị sửa | Va chạm và không ổn định/không phù hợp với byte file | SHA-256 hoặc checksum phù hợp; định nghĩa nguồn tham chiếu đáng tin |
| Ghi đè `equals()` nhưng không ghi đè `hashCode()` | `HashMap`/`HashSet` có thể không tra cứu đúng khóa bằng nhau | Viết và kiểm tra cả hai theo cùng trường định danh |
| Dùng key mutable trong `HashMap` và đổi trường ảnh hưởng hash | Khóa có thể “biến mất” khi tra cứu | Dùng khóa bất biến hoặc không thay đổi trường định danh |
| Tưởng `hashCode(a)==hashCode(b)` là `a.equals(b)` | Gộp nhầm dữ liệu khi có collision | Dùng `equals` để kết luận bằng nhau |
| Thay CRC32 bằng CRC32C vì đều 32 bit | Hai đầu ra khác nhau, kiểm lỗi không tương thích | Giữ đúng biến thể, seed, xử lý byte và cách đóng gói giao thức |
| Không reset đối tượng `Checksum` giữa hai payload | Kết quả của payload thứ hai cộng dồn payload đầu | Dùng instance mới hoặc `reset()` đúng chỗ |
| Hash `String.getBytes()` mà không chỉ rõ charset | Byte thay đổi theo môi trường/cấu hình và giao thức khó kiểm | Dùng `StandardCharsets.UTF_8` hoặc charset đã quy định |
| Hash JSON ở một bên với field order khác bên còn lại | Digest/tag không khớp | Dùng cùng canonicalization/serialization |
| So SHA-256 với digest nhận từ chính nguồn bị tấn công | False sense of security | Dùng nguồn digest tin cậy, HMAC hoặc chữ ký số |
| Dùng MD5/SHA-1 chống dữ liệu giả mạo | Bị khai thác va chạm trong nhiều kịch bản | Chọn SHA-256/SHA-3 theo giao thức đã thẩm định |
| Băm mật khẩu bằng SHA-256 đơn thuần | Dễ thử đoán offline với số lượng lớn | Dùng Argon2id/scrypt/PBKDF2, salt riêng, cost phù hợp |
| Đưa `MessageDigest` hay `Checksum` chung cho nhiều thread | Race condition, kết quả bị trộn trạng thái | Tạo instance riêng hoặc kiểm soát đồng bộ |
| Dùng digest để thay mã hóa | Digest không giúp người có quyền giải mã lại dữ liệu và không che bí mật của dữ liệu có entropy thấp | Dùng encryption cho tính bí mật, digest cho fingerprint |

## 10. Bài tập tự kiểm tra (có đáp án)

**Bài 1.** Hai `String` khác nhau có cùng `hashCode()`. `HashMap` có bắt buộc xem chúng là cùng khóa?

**Đáp án:** Không. `HashMap` dùng hash để khoanh vùng và `equals()` để kiểm khóa thực sự bằng nhau. `"Aa"` và `"BB"` là ví dụ thực tế: hash 2112 như nhau nhưng `equals` false.

**Bài 2.** Sau khi `hashCode()` của một khóa mutable thay đổi, vì sao `map.get(key)` có thể không tìm lại được giá trị?

**Đáp án:** Map có thể tìm theo bucket của mã băm **mới**, còn entry đã nằm ở bucket theo mã băm **cũ**. Cần giữ ổn định các trường tham gia `equals/hashCode` trong lúc object được dùng làm key.

**Bài 3.** File A và B cùng checksum CRC32. Có kết luận chúng giống hệt nhau và do người phát hành đáng tin tạo ra không?

**Đáp án:** Không. CRC32 là 32 bit nên có va chạm và không chống sửa đổi có chủ đích; không có cơ chế xác thực danh tính.

**Bài 4.** Tại sao CRC32(`"abc"`) và CRC32C(`"abc"`) lại khác dù đều 32 bit?

**Đáp án:** Chúng sử dụng **đa thức/thuật toán CRC khác nhau**. Tên số “32” chỉ độ rộng checksum, không khẳng định công thức tương thích.

**Bài 5.** Bạn tải `installer.jar` và `installer.sha256` từ cùng server. Hash khớp; điều này đủ bảo vệ trước server bị xâm nhập chưa?

**Đáp án:** Chưa. Kẻ tấn công có thể thay cả file lẫn digest. Cần điểm neo tin cậy độc lập, ví dụ checksum từ kênh được xác thực hoặc chữ ký số với public key đáng tin.

**Bài 6.** Hai service cùng tính SHA-256 của cùng ý nghĩa JSON, nhưng digest khác nhau. Phải sửa hàm SHA-256 không?

**Đáp án:** Thường không. Kiểm tra byte nguồn, UTF-8, thứ tự field, khoảng trắng, newline, Unicode normalization và canonicalization trước. SHA-256 hoạt động trên **byte**, không dựa vào ý nghĩa JSON.

**Bài 7.** Khi nào cần HMAC-SHA256 thay vì SHA-256 trên request webhook?

**Đáp án:** Khi cần xác thực bên gửi **cùng giữ secret**, chống người không có secret tự tạo request hợp lệ. Giao thức cũng phải có cơ chế chống replay; HMAC một mình không chặn phát lại request nguyên vẹn.

## 11. Checklist chọn thuật toán

Trước khi viết code, hãy tự hỏi tuần tự:

1. **Có đối thủ chủ động sửa/giả mạo không?** Nếu chỉ kiểm lỗi ngẫu nhiên và định dạng quy định CRC/Adler, dùng checksum. Nếu có đối thủ chủ động, không dừng ở CRC.
2. **Đang băm object hay bytes?** Nếu để triển khai khóa `HashMap`, làm đúng `equals/hashCode` và giữ khóa bất biến. Nếu băm file/message, xác định chính xác byte.
3. **Có cần dấu vân tay khó va chạm trước đối thủ không?** Chọn SHA-256 hoặc thuật toán được giao thức chỉ định, nhận byte qua `MessageDigest`.
4. **Digest kỳ vọng từ đâu và ai được quyền công bố?** Nếu cần xác thực nguồn, thêm HMAC/chữ ký số hoặc nguồn tham chiếu đáng tin. Không coi SHA-256 tự động là chữ ký.
5. **Có cần giữ bí mật hay lưu mật khẩu không?** Dùng encryption/AEAD cho tính bí mật và password KDF cho mật khẩu; không gán công việc đó cho checksum, `hashCode()` hay SHA-256 đơn lẻ.

**Kết luận trọng tâm:** **checksum** đo sai hỏng dữ liệu theo mô hình lỗi; **`hashCode()`** phục vụ quan hệ bằng nhau và cấu trúc tra cứu trong Java; **digest mật mã** tạo fingerprint có tính kháng va chạm và tiền ảnh. Kết quả giống hình thức số/hex nhưng **không thể thay thế cho nhau**, và không cái nào tự cung cấp danh tính người gửi khi đứng riêng lẻ.
