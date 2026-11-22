# 3.1 Chuyển String thành byte[] với charset xác định và quy tắc chuẩn hóa dữ liệu

Trong Java, `String` biểu diễn văn bản; `byte[]` biểu diễn dãy byte. Mật mã, hash, HMAC, chữ ký số, lưu trữ và giao thức mạng cuối cùng đều xử lý **byte cụ thể**, không xử lý “chữ trông giống nhau”. Bởi vậy, trước khi đưa văn bản vào một thuật toán mật mã, cần quyết định rõ **cách mã hóa ký tự (charset)** và **quy tắc chuẩn hóa dữ liệu (normalization/canonicalization)**. Một quyết định thiếu nhất quán có thể tạo digest khác nhau, làm xác minh chữ ký thất bại, khiến dữ liệu giải mã không khớp hoặc gây ra bất đồng về danh tính/ủy quyền.

Ví dụ, hai chuỗi cùng hiển thị gần như “Café”:

- `"Café"`: chữ `é` là một Unicode code point U+00E9.
- `"Cafe\u0301"`: chữ `e` U+0065 đi cùng dấu sắc kết hợp U+0301.

Chúng có thể nhìn giống nhau nhưng **`String.equals` trả `false` và byte UTF-8 ban đầu khác nhau**. Chuẩn hóa NFC có thể đưa chúng về một biểu diễn tương đương trước khi mã hóa UTF-8, nếu đó là chính sách đã được hai bên thống nhất.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Phân biệt `String`, UTF-16 code unit, Unicode code point, ký tự người dùng nhìn thấy (*grapheme cluster*) và byte.
2. Chuyển đổi văn bản bằng `StandardCharsets.UTF_8` theo cách xác định, thay vì phụ thuộc charset mặc định của môi trường.
3. Hiểu NFC, NFD, NFKC, NFKD; chọn đúng chuẩn hóa cho **từng loại dữ liệu**, nhận biết trường hợp không nên chuẩn hóa.
4. Nhận biết và chủ động xử lý input Unicode/UTF-8 không hợp lệ.
5. Thiết kế byte đầu vào nhất quán cho digest, HMAC, chữ ký số, AEAD AAD và lưu trữ; phân biệt chuẩn hóa văn bản với canonicalization của một giao thức.
6. Kiểm thử được kết quả byte, tính tương thích giữa các hệ thống và các tình huống Unicode khó.

## 2. Các lớp biểu diễn: từ người đọc đến byte

Có ít nhất bốn lớp cần tách rõ:

| Lớp | Đơn vị hoặc cấu trúc | Ví dụ | Điều cần nhớ |
| --- | --- | --- | --- |
| Văn bản hiển thị | Grapheme cluster; có thể gồm nhiều code point | Chữ `e` kèm dấu sắc | “Một ký tự nhìn thấy” không nhất thiết là một phần tử của `char[]` |
| Unicode | Code point như U+00E9, U+0301, U+1F510 | `é`, dấu kết hợp, emoji | Code point là giá trị trừu tượng; không đồng nhất với số byte |
| Java `String` | Chuỗi **UTF-16 code unit**; `char` là 16 bit | Emoji 🔐 cần một cặp surrogate, tức hai `char` | `String.length()` đếm code unit, không đếm code point |
| Byte | Chuỗi octet theo charset đã chọn | `é` thành `C3 A9` khi dùng UTF-8 | Mật mã làm việc trên chính các byte này |

Cần phân biệt:

- `String.length()`: số **UTF-16 code unit**.
- `String.codePointCount(0, s.length())`: số **code point** theo biểu diễn UTF-16; không đếm chính xác số grapheme cluster.
- `s.getBytes(StandardCharsets.UTF_8).length`: số byte sau khi mã hóa; thường khác cả hai con số trên.
- `byte[].length`: độ dài byte thực sự để lưu, truyền, băm hoặc ký.

Ví dụ emoji **🔐** là một Unicode code point, nhưng trong Java có `length() == 2` và khi mã hóa UTF-8 hợp lệ dài **4 byte**. Không dùng `substring` hoặc phép cắt theo chỉ số `char` tùy tiện ở giữa cặp surrogate.

### Charset là quy tắc ánh xạ, không phải “bộ chữ” trên giao diện

Charset quy định cách ánh xạ ký tự sang byte và ngược lại:

```text
String (Unicode/UTF-16 trong Java)
    -- [charset encoder: UTF-8] -->
byte[] (octet cụ thể)
    -- [charset decoder: UTF-8] -->
String (Unicode/UTF-16 trong Java)
```

Cùng văn bản, charset khác nhau có thể cho byte khác nhau. Với `"é"`:

- UTF-8: `C3 A9` — hai byte.
- UTF-16BE: `00 E9` — hai byte, big-endian.
- UTF-16LE: `E9 00` — hai byte, little-endian.

Với ký tự ngoài ASCII, giải mã bằng **khác charset** có thể tạo mojibake, thay ký tự hoặc lỗi. Với dữ liệu nhị phân thuần túy như ciphertext, salt, nonce, khóa, digest, không có “charset đúng” để chuyển thành String một cách tùy ý; dùng các định dạng nhị phân hoặc **Base64/hex** khi thật sự cần biểu diễn văn bản.

## 3. Quy tắc Java: chỉ định charset tường minh

Trong ứng dụng hiện đại, dùng UTF-8 khi hợp đồng giao thức chưa yêu cầu charset khác:

```java
import java.nio.charset.StandardCharsets;

String message = "Xin chào Java 🔐";
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

Đây là **đoạn mã minh họa**, có thể đặt trong một method có import như trên. `StandardCharsets.UTF_8` là hằng có sẵn trong JDK, không cần tra tên charset khi chạy. Tương tự, JDK cung cấp `US_ASCII`, `ISO_8859_1`, `UTF_16`, `UTF_16BE` và `UTF_16LE`; chỉ dùng khi giao thức thực sự quy định chúng.

Tránh xây dựng hợp đồng bảo mật dựa trên:

```java
byte[] bytes = message.getBytes();    // Không chỉ rõ charset
String text = new String(bytes);       // Không chỉ rõ charset
```

Các overload không có tham số dùng default charset của runtime. Java 18+ mặc định UTF-8 theo JEP 400 trong các tình huống thông thường, còn Java 17 và một số môi trường/cấu hình có thể khác; **giao thức không nên phụ thuộc vào chi tiết này**. Ngay cả khi mọi máy hiện tại dùng UTF-8, vẫn nên ghi charset trong code và trong đặc tả dữ liệu.

Cũng không dùng `getBytes("UTF-8")` khi `StandardCharsets.UTF_8` đã có sẵn, trừ khi API yêu cầu tên charset; đối tượng `Charset` có kiểu dữ liệu rõ ràng và tránh checked exception do tìm kiếm tên charset không hợp lệ.

### Tính xác định cần cả hai hướng

Với input Unicode hợp lệ và cùng charset, quá trình mã hóa UTF-8 là xác định. Tuy nhiên, `new String(bytes, UTF_8)` **có thể thay byte UTF-8 không hợp lệ bằng ký tự thay thế U+FFFD**, và `String.getBytes(UTF_8)` có thể thay một `char` surrogate lẻ không hợp lệ bằng byte thay thế. Cách tiện lợi này hữu ích cho hiển thị văn bản hỏng nhưng có thể làm mất thông tin về byte đầu vào.

Nếu byte phải được kiểm tra nghiêm ngặt, ví dụ giao thức ký, định danh, giải mã bản tin hoặc API bảo mật, dùng `CharsetEncoder` / `CharsetDecoder` với `CodingErrorAction.REPORT` và xử lý `CharacterCodingException`. Bài chạy đầy đủ ở mục 7 minh họa cả hai chiều.

**Quy tắc:** đầu vào nhị phân đến từ mạng/file phải được giải mã theo một charset được công bố, có chính sách lỗi rõ ràng; không âm thầm “sửa” chuỗi mà bạn sắp đưa vào phép kiểm chứng mật mã.

## 4. Unicode normalization: cùng ý nghĩa hiển thị chưa chắc cùng byte

Unicode cho phép nhiều cách biểu diễn tương đương về mặt chuẩn. Java có `java.text.Normalizer` với bốn dạng:

| Form | Loại | Đặc tính | Cách dùng điển hình |
| --- | --- | --- | --- |
| **NFC** | Canonical composition | Tách theo quy tắc tương đương chuẩn tắc, rồi kết hợp thành dạng soạn trước khi có thể | Mặc định hợp lý cho nhiều trường văn bản cần so sánh ổn định |
| **NFD** | Canonical decomposition | Phân rã các ký tự tương đương chuẩn tắc thành dạng phân tách | Xử lý văn bản cần tách dấu, khi có mục đích rõ |
| **NFKC** | Compatibility composition | Thêm phân rã tương thích rồi kết hợp; có thể gộp biểu diễn khác nghĩa/kiểu chữ | Một số chính sách định danh được đặc tả kỹ, không phải mặc định toàn hệ thống |
| **NFKD** | Compatibility decomposition | Phân rã tương thích và giữ dạng tách | Pipeline xử lý đặc thù, không phải lựa chọn tự động cho secret |

API Java:

```java
import java.text.Normalizer;

String nfc  = Normalizer.normalize(input, Normalizer.Form.NFC);
String nfd  = Normalizer.normalize(input, Normalizer.Form.NFD);
String nfkc = Normalizer.normalize(input, Normalizer.Form.NFKC);
String nfkd = Normalizer.normalize(input, Normalizer.Form.NFKD);
```

Đây là đoạn mã minh họa; giả sử `input` là một `String` hợp lệ. Một ví dụ dễ kiểm chứng:

```text
"Café"           -> UTF-8 raw: 43 61 66 C3 A9
"Cafe\u0301"      -> UTF-8 raw: 43 61 66 65 CC 81

normalize(NFC) cả hai -> "Café"
UTF-8 sau NFC         -> 43 61 66 C3 A9
```

Ví dụ tương thích: ký tự ligature `ﬃ` (U+FB03) vẫn là `ﬃ` khi dùng NFC; khi NFKC có thể thành chuỗi `ffi`. Do đó NFKC **có khả năng gộp biểu diễn mang sự khác biệt mà ứng dụng quan tâm**.

Không suy ra rằng normalization giải quyết mọi trường hợp “trông giống nhau”:

- `a` Latin và một chữ tương tự thuộc bảng chữ khác có thể nhìn giống nhưng **không phải cùng code point**, không tự trở thành một ký tự sau NFC.
- Chữ hoa/chữ thường, khoảng trắng, dấu gạch, dấu xuống dòng `\r\n`/`\n`, ký tự zero-width, URL percent-encoding, HTML entity và thứ tự thuộc tính JSON là **các vấn đề riêng**. NFC không thay thế mọi phép canonicalization đó.
- `Normalizer` không phải API phát hiện Unicode spoofing hoặc tính an toàn của identifier. Với ID công khai, cần chính sách tập ký tự, phát hiện nhầm lẫn và kiểm soát đăng ký tên theo sản phẩm.
- Một chuỗi có thể chứa code point không hợp lệ ở mức Unicode scalar value do surrogate lẻ trong Java; normalize không thay cho strict encoding.
- Việc dùng `toLowerCase(Locale.ROOT)` nếu có chính sách không phân biệt hoa/thường **không tương đương** với đầy đủ Unicode case folding. Không ghép lowercase tùy ý vào quy tắc định danh mật mã nếu hai hệ thống chưa thống nhất thuật toán.

### Đặt normalization trước hay sau mã hóa?

Normalization áp dụng lên **văn bản Unicode**. Quy trình có chủ đích:

```text
input text -> kiểm tra chính sách trường dữ liệu
           -> Unicode normalization đã chọn
           -> kiểm tra lại tính hợp lệ của dạng chuẩn
           -> encode UTF-8 nghiêm ngặt
           -> byte[] cho thuật toán/giao thức
```

Nếu nguồn là byte UTF-8: **decode strict -> normalize theo chính sách -> encode strict**. Nếu bạn đang cần kiểm tra chữ ký trên **body byte gốc**, phải kiểm chữ ký theo đặc tả trên byte gốc; không decode/normalize rồi giả định byte sau đó vẫn là body mà bên gửi đã ký.

Tính *idempotent* là yêu cầu tốt cho pipeline: sau khi áp cùng một form lên dữ liệu đã chuẩn hóa, lần lặp không nên tiếp tục thay đổi dữ liệu. Nhưng nếu pipeline còn thêm trim, lowercase, collapse whitespace, URL decode, serialize JSON hoặc quy tắc nghiệp vụ, hãy đánh giá các bước đó **riêng** và định nghĩa thứ tự chính xác.

## 5. Chọn chính sách theo dữ liệu, không áp dụng một hàm cho tất cả

**NFC + UTF-8 không phải “công thức vạn năng”.** Charset có thể thống nhất toàn giao thức, nhưng normalization cần dựa trên ý nghĩa trường dữ liệu và yêu cầu tương thích.

| Dữ liệu đầu vào | Gợi ý chính sách | Vì sao |
| --- | --- | --- |
| Tên hiển thị hoặc văn bản tìm kiếm | Có thể lưu/so sánh ở NFC nếu hợp đồng quy định; giữ bản gốc khi cần | Giúp giảm khác biệt chuẩn tắc nhưng vẫn tôn trọng cách người dùng nhập |
| Định danh tài khoản/tenant do người dùng chọn | Chính sách định danh riêng: form, tập ký tự, case handling, độ dài, reserved names, uniqueness | Tránh hai tên trông khác/giống đi qua các kiểm tra không nhất quán; cần chống mạo danh |
| Mã tài liệu, mã giao dịch có định dạng máy | Validate theo grammar rõ ràng (ví dụ ASCII giới hạn); không tự thay đổi ngoài quy tắc | ID là khóa nghiệp vụ và đầu vào phân quyền |
| Mật khẩu, passphrase | Tuân thủ **chính xác** quy ước đã công bố ở đăng ký và xác thực; không tự trim/lowercase/đổi form giữa chừng | Bất kỳ byte khác nào tạo kết quả xác minh khác; thay đổi chính sách cần migration có chủ đích |
| Dữ liệu/JSON đã được ký bởi bên khác | Ký/xác minh theo **byte chính xác** hoặc canonicalization mà giao thức chữ ký công bố | Hai cách serialize “cùng dữ liệu” thường cho byte khác |
| Chuỗi đưa vào AAD của AES-GCM | Dùng byte và thứ tự trường được định nghĩa, có version; giữ khả năng tái tạo trong lần giải mã | AAD lệch một byte khiến kiểm tra tag thất bại |
| Base64 của ciphertext/nonce/salt/key | Decode Base64 thành byte; không Unicode-normalize nội dung nhị phân | Secret/ciphertext là byte chứ không phải văn bản tự nhiên |
| Email, hostname quốc tế hoặc URL | Tuân thủ đặc tả xử lý **đúng miền** (IDNA, URL parser, case rules, v.v.) | NFC đơn lẻ không mô tả toàn bộ cú pháp, bảo mật và so sánh |

**Đặc biệt với mật khẩu:** nếu hệ thống đang dùng chính sách giữ nguyên chuỗi, đăng nhập phải dùng chính xác quy tắc của đăng ký. Nếu tiêu chuẩn nghiệp vụ yêu cầu normalization, cả hai đầu phải thống nhất từ đầu và có kế hoạch phiên bản dữ liệu. Không tự động xóa dấu, đổi chữ hoa, trim hoặc chuyển NFKC một cách âm thầm chỉ vì muốn “dễ đăng nhập”. Sau khi xác định byte, mật khẩu phải đi qua **password hashing/KDF chuyên dụng** với salt và tham số cost (chẳng hạn Argon2id theo chính sách), không dùng SHA-256 đơn lẻ, và không trực tiếp dùng `getBytes` làm khóa AES.

Với token ngẫu nhiên, khóa, IV/nonce và ciphertext, lựa chọn đúng là **bảo toàn byte**. Chuỗi Base64/hex là một *encoding dành cho vận chuyển*, không biến dữ liệu thành “chữ cần normalize”.

## 6. Ví dụ Java 17+ hoàn chỉnh: charset, NFC và xử lý lỗi nghiêm ngặt

Lưu chính xác thành file **`UnicodeBytesDemo.java`** với nội dung sau:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;

public class UnicodeBytesDemo {
    static byte[] strictUtf8(String text) throws CharacterCodingException {
        ByteBuffer buffer = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(text));
        byte[] bytes = new byte[buffer.remaining()];
        buffer.get(bytes);
        return bytes;
    }

    static String strictDecode(byte[] bytes) throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString();
    }

    static byte[] canonicalBytes(String text) throws CharacterCodingException {
        if (text == null) {
            throw new IllegalArgumentException("text must not be null");
        }
        return strictUtf8(Normalizer.normalize(text, Normalizer.Form.NFC));
    }

    static String hex(byte[] bytes) {
        return HexFormat.of().formatHex(bytes);
    }

    public static void main(String[] args) throws Exception {
        String composed = "Café";
        String decomposed = "Cafe\u0301";
        System.out.println("Same raw String: " + composed.equals(decomposed));
        System.out.println("Composed UTF-8: " + hex(strictUtf8(composed)));
        System.out.println("Decomposed UTF-8: " + hex(strictUtf8(decomposed)));

        byte[] a = canonicalBytes(composed);
        byte[] b = canonicalBytes(decomposed);
        System.out.println("NFC bytes equal: " + Arrays.equals(a, b));
        System.out.println("NFC UTF-8: " + hex(a));
        System.out.println("NFC digest equal: " + Arrays.equals(
                MessageDigest.getInstance("SHA-256").digest(a),
                MessageDigest.getInstance("SHA-256").digest(b)));

        System.out.println("NFKC of ligature: " +
                Normalizer.normalize("ﬃ", Normalizer.Form.NFKC));

        String emoji = "🔐";
        System.out.println("Emoji UTF-16 units: " + emoji.length());
        System.out.println("Emoji code points: " + emoji.codePointCount(0, emoji.length()));
        System.out.println("Emoji UTF-8 bytes: " + strictUtf8(emoji).length);
        System.out.println("UTF-8 round trip: " +
                composed.equals(strictDecode(strictUtf8(composed))));

        try {
            strictUtf8(String.valueOf((char) 0xD800));
            System.out.println("Malformed surrogate accepted");
        } catch (CharacterCodingException e) {
            System.out.println("Malformed surrogate rejected");
        }

        try {
            strictDecode(new byte[] {(byte) 0xC3, 0x28});
            System.out.println("Malformed UTF-8 accepted");
        } catch (CharacterCodingException e) {
            System.out.println("Malformed UTF-8 rejected");
        }
    }
}
```

Lệnh chạy ở thư mục chứa file, sử dụng JDK **17 trở lên**:

```bash
javac --release 17 UnicodeBytesDemo.java
java UnicodeBytesDemo
```

**Stdout chính xác:**

```text
Same raw String: false
Composed UTF-8: 436166c3a9
Decomposed UTF-8: 43616665cc81
NFC bytes equal: true
NFC UTF-8: 436166c3a9
NFC digest equal: true
NFKC of ligature: ffi
Emoji UTF-16 units: 2
Emoji code points: 1
Emoji UTF-8 bytes: 4
UTF-8 round trip: true
Malformed surrogate rejected
Malformed UTF-8 rejected
```

Diễn giải từng nhóm kết quả:

1. `equals` trên hai `String` thô là `false`. Các hex khác nhau vì `C3 A9` mã hóa U+00E9, còn `65 CC 81` mã hóa hai code point U+0065 và U+0301.
2. `Normalizer.Form.NFC` khiến byte của hai chuỗi này bằng nhau. Digest SHA-256 sau cùng cũng bằng nhau vì **input byte đã bằng nhau**; SHA-256 không tự chuẩn hóa Unicode.
3. `NFKC` đổi ligature `ﬃ` thành `ffi`. Đây là lý do không chọn NFKC chỉ vì “trông bình thường hơn”.
4. Emoji chứng tỏ code unit, code point và số byte là ba đại lượng khác nhau.
5. Encoder/decoder ở chế độ `REPORT` từ chối surrogate lẻ và byte UTF-8 sai, thay vì âm thầm làm mất khả năng kiểm tra byte nguyên gốc.

`MessageDigest` ở ví dụ này chỉ dùng để **minh họa tính phụ thuộc vào byte**, không phải ví dụ lưu trữ mật khẩu. `HexFormat` được thêm từ Java 17; với Java 11 không thể dùng nguyên ví dụ này mà không đổi phần hiển thị hex.

### Khi nào nên dùng encoding/decoding strict?

Có hai chế độ thường gặp:

- **Thuận tiện:** `text.getBytes(UTF_8)`, `new String(bytes, UTF_8)`. Hợp lý cho văn bản đã được kiểm tra hoặc hiển thị với chính sách cho phép replacement.
- **Bảo toàn tính hợp lệ:** `CharsetEncoder/Decoder` với `REPORT`. Nên cân nhắc cho định danh, chữ ký, bản tin có cú pháp nghiêm ngặt và bất kỳ nơi nào thay thế ký tự có thể làm thay đổi quyết định bảo mật.

Không xử lý lỗi bằng cách “thử charset khác” sau khi UTF-8 không hợp lệ, trừ khi giao thức **thật sự có cơ chế phát hiện charset** rõ ràng. Thử lùi qua nhiều encoding có thể làm hai thành phần hiểu cùng dữ liệu theo cách khác nhau.

## 7. Ứng dụng trong hash, HMAC và chữ ký số

Các phép mật mã phụ thuộc chính xác vào byte: `SHA256(byte[])`, `Mac.doFinal(byte[])` và `Signature.update(byte[])`. Vì vậy, câu “hai bên cùng ký nội dung text” chưa đủ làm đặc tả. Hai bên phải thống nhất:

1. **Dữ liệu nào được ký:** raw HTTP body, string field sau parse, hay một cấu trúc canonical được serialize?
2. **Bộ mã ký tự:** thường UTF-8; có BOM hay không; chấp nhận byte UTF-8 sai không?
3. **Normalization:** không normalize, hay NFC, hay một profile/version cụ thể?
4. **Cấu trúc và ranh giới trường:** thứ tự trường, separator, quy tắc escape, null/empty, độ dài, cách ký số và thời gian.
5. **Vòng đời chính sách:** trường phiên bản trong dữ liệu ký, cách xử lý bản ghi cũ nếu chính sách đổi.

### 7.1 Digest của chuỗi

Ví dụ:

```text
Digest A = SHA-256( UTF8("Café") )
Digest B = SHA-256( UTF8("Cafe\u0301") )
Digest A != Digest B

Digest C = SHA-256( UTF8(NFC("Café")) )
Digest D = SHA-256( UTF8(NFC("Cafe\u0301")) )
Digest C == Digest D
```

Kết quả không xuất phát từ “SHA-256 hiểu Unicode”; SHA-256 chỉ nhận dãy byte. Với dữ liệu gốc phải giữ nguyên (file upload, artifact, forensic log), **hash byte gốc**, đừng tự normalize. Đối với chuỗi được định nghĩa bằng chính sách NFC, mới hash byte đã qua NFC.

### 7.2 HMAC và chữ ký cho HTTP/JSON

Giả sử đối tác gửi JSON:

```json
{"name":"Café","amount":10}
```

Bên khác có thể tạo JSON có cùng dữ liệu nhưng thêm khoảng trắng, đảo thứ tự field, escape ký tự thành `\uXXXX` hoặc dùng `10.0` thay `10`. Các body đó có thể cho **byte khác**, dù parser có thể xây dựng cấu trúc tương tự. Unicode NFC **không canonicalize JSON**.

Hai cách hợp lệ phải được đặc tả rõ:

- **Ký raw body bytes:** sender tạo HMAC/chữ ký trên đúng body byte đã gửi; receiver kiểm tra trên **byte nhận nguyên vẹn**, trước khi deserialize/serialize lại. Đừng chuyển body thành String rồi dựng JSON lại để kiểm chữ ký.
- **Ký representation canonical:** cả sender và receiver tuân theo cùng một đặc tả canonical serialization (bao gồm UTF-8, thứ tự khóa, số, escape và các giới hạn khác), cùng version. Nếu dùng JSON Canonicalization Scheme (RFC 8785), hiểu chính xác các quy tắc của chuẩn; **không tự giả định nó chuẩn hóa Unicode string về NFC**.

Khi nối nhiều field để tạo input ký, tránh nối không có ranh giới: `("ab", "c")` và `("a", "bc")` đều tạo `"abc"`. Hãy dùng một canonical serialization có grammar rõ ràng hoặc **length-prefix** trên byte, kèm domain separation cho mục đích ký. Một dấu `:` đơn lẻ chưa đủ nếu dữ liệu được phép chứa `:` mà không escape.

**Tình huống dễ lỗi:** người gửi ký `method + path + body` sau khi URL decode một lần, còn người nhận canonicalize path khác hoặc decode hai lần. Khi đó có thể xảy ra mismatch chữ ký hoặc bỏ qua kiểm tra quyền. Normalization Unicode không thay thế canonicalization URL, path, query, header và request body theo đặc tả giao thức.

### 7.3 Timing và so sánh kết quả bảo mật

So sánh chữ ký/HMAC phải dùng cơ chế kiểm tra an toàn do thư viện/giao thức cung cấp. Khi so sánh hai digest/MAC byte cùng dạng trong code Java thuần, `MessageDigest.isEqual(a, b)` là công cụ thích hợp hơn `Arrays.equals` cho mục đích kiểm tra kết quả bảo mật; tuy nhiên, tính an toàn của toàn quy trình còn phụ thuộc phân tích độ dài, giao thức, key, algorithm và các bước trước khi so sánh. Trong ví dụ mục 6, `Arrays.equals` chỉ dùng để minh họa hai dãy byte hoặc digest từ dữ liệu công khai giống nhau; **đó không phải logic xác thực MAC**.

Không tự viết mật mã, MAC hoặc parser canonicalization tùy ý khi đã có thư viện và chuẩn giao thức được duy trì.

## 8. Mã hóa, giải mã và AAD: nhất quán byte qua nhiều năm

Khi AES-GCM được sử dụng cùng **AAD** (*Additional Authenticated Data*), bản mã được bảo vệ bằng authentication tag gắn với AAD byte ban đầu. Ví dụ AAD có thể mã hóa `tenantId`, `documentId` và phiên bản schema. Nếu hệ thống mã hóa bằng `UTF8(NFC(tenantId))` nhưng giải mã bằng UTF-8 thô hoặc đổi thứ tự các trường, kiểm tra tag có thể thất bại, dù nội dung hiển thị giống nhau.

Thiết kế phù hợp:

- Định nghĩa **định dạng nhị phân hoặc serialization không mơ hồ** cho AAD; ví dụ version + tên miền mục đích + các trường có length-prefix.
- Chuẩn hóa những **trường văn bản được phép chuẩn hóa**, trước khi serialize theo đặc tả; không normalize `byte[]` ciphertext/nonce/salt/key.
- Lưu version hoặc đủ metadata để dựng lại byte AAD khi đọc dữ liệu cũ; nếu có thể, lưu chính xác AAD đã xác thực hoặc một canonical representation được đặc tả bền vững.
- Dùng API AEAD đúng cách, gồm yêu cầu **không tái sử dụng nonce với cùng khóa** cho AES-GCM. Việc chọn charset/normalization **không thay thế** các yêu cầu sử dụng mật mã an toàn đó.

### Truyền dữ liệu nhị phân bằng Base64

**Sai về nguyên tắc:**

```java
String ciphertextAsText = new String(ciphertext, StandardCharsets.UTF_8);
```

Đây là **đoạn minh họa anti-pattern**, giả sử `ciphertext` là `byte[]`. Ciphertext ngẫu nhiên có thể chứa byte UTF-8 không hợp lệ. Việc ép nó thành String thường làm mất dữ liệu; khi encode ngược lại sẽ không thu được dãy byte gốc.

**Đúng khi cần lưu/truyền bằng văn bản:**

```java
import java.util.Base64;

String encoded = Base64.getEncoder().encodeToString(ciphertext);
byte[] restoredCiphertext = Base64.getDecoder().decode(encoded);
```

Các dòng là đoạn minh họa, biến `ciphertext` đã có từ trước. Base64 là **mã hóa biểu diễn**, không phải mã hóa bảo mật: ai có chuỗi Base64 cũng có thể decode. Không ghi ciphertext, key hay token vào log chỉ vì chúng đã ở dạng Base64.

## 9. Nguy cơ bảo mật từ canonicalization không thống nhất

Một hệ thống có thể thực hiện nhiều kiểm tra trên cùng chuỗi: gateway, bộ lọc đầu vào, authorization, cache, DB, file system. Nếu mỗi lớp hiểu chuỗi khác nhau, dữ liệu có thể được kiểm tra theo một danh tính nhưng truy xuất dưới danh tính khác.

Ví dụ nghiệp vụ:

- Gateway kiểm tra quyền đối với một đường dẫn đã decode **một lần**, service hoặc proxy khác decode **thêm lần nữa** và truy cập đường dẫn khác.
- Application lưu `username` với NFC, nhưng uniqueness check so với input thô. Hai biểu diễn chuẩn tắc tương đương có thể đi qua hai quyết định khác nhau.
- API xác thực `tenantId` theo chuỗi đã trim, còn truy vấn DB sử dụng giá trị chưa trim; authorization và retrieval có thể lệch nhau.
- Một client so sánh Unicode bằng quy tắc case-insensitive khác server, rồi chọn nhầm tài khoản hoặc đối tượng.
- Ứng dụng thay newline `\r\n` thành `\n` trước khi kiểm HMAC trong khi đối tác ký byte raw; chữ ký hợp lệ bị từ chối.

Quy tắc phòng tránh không chỉ là “normalize mọi thứ”. Quy trình đúng:

1. **Đọc byte theo một giao thức rõ ràng.** HTTP, JSON, path, query và form có quy tắc giải mã riêng.
2. **Phân tích cấu trúc và kiểm tra sự hợp lệ**, từ chối chuỗi sai encoding, ambiguous encoding hoặc input ngoài giới hạn theo chính sách.
3. **Chuẩn hóa ở ranh giới nghiệp vụ phù hợp**, chỉ với những trường mà policy quy định và theo đúng thứ tự.
4. **So sánh, kiểm tra quyền, lưu và truy vấn trên cùng dạng định danh**, không dùng bản raw ở một lớp và bản normalized ở lớp khác.
5. **Bảo toàn dữ liệu nguyên gốc khi cần:** file, raw body để kiểm chữ ký, log điều tra, chứng từ, dữ liệu bên thứ ba; đừng thay đổi chứng cứ trước khi hash.
6. **Gắn version và kiểm thử liên hệ nhiều hệ thống** nếu thuật toán canonicalization là phần của hợp đồng dài hạn.

Tránh double decoding, double normalization cộng với sửa khoảng trắng tùy tiện; việc gọi NFC nhiều lần vẫn ổn định, nhưng một chuỗi biến đổi khác nhau giữa các lớp có thể tạo bất đồng. Khi xác thực/ủy quyền, coi dữ liệu vào là không tin cậy dù truyền qua TLS.

## 10. Quản lý hợp đồng dữ liệu khi tích hợp nhiều ngôn ngữ

Java, JavaScript, Python, Go và các SDK khác có cách truy cập Unicode và byte khác nhau. Đừng truyền sang đối tác một câu chung chung “mã hóa string theo UTF-8”; nên công bố một **canonicalization profile** có ví dụ kiểm thử:

| Thuộc tính | Ví dụ mô tả trong đặc tả |
| --- | --- |
| Tên và version | `canonical-text-v1` |
| Nguồn dữ liệu | Trường `displayName` đã giải mã từ JSON UTF-8 |
| Form Unicode | NFC, không trim, không case folding |
| Charset đầu ra | UTF-8, không BOM |
| Input không hợp lệ | Reject malformed UTF-8 và Unicode scalar không hợp lệ |
| Giới hạn | Độ dài byte UTF-8 và ký tự sau normalize theo chính sách; phân biệt rõ đơn vị |
| Chuyển đổi khác | Không tự đổi newline, HTML/URL escape hay dấu câu |
| Serializing nhiều trường | Format canonical riêng có định nghĩa thứ tự, null/empty, length-prefix |
| Cập nhật chính sách | Tạo version mới; giữ cách đọc dữ liệu v1 trong thời gian migration |

Cùng một Unicode normalization form đã được đặt tên, nhưng trong hệ thống dài hạn nên ghi rõ thư viện/runtime và tương thích phiên bản Unicode khi cần. Unicode normalization có các bảo đảm ổn định theo tiêu chuẩn, nhưng đừng vì thế bỏ qua **thử nghiệm liên nền tảng** của toàn bộ pipeline (bao gồm parser, validation, case mapping, JSON và storage).

Một *golden vector* tối thiểu nên có:

```text
Input visible: Café
Unicode source A: U+0043 U+0061 U+0066 U+00E9
Unicode source B: U+0043 U+0061 U+0066 U+0065 U+0301
Policy: NFC + UTF-8 strict
Expected canonical hex for both: 436166c3a9
```

Golden vectors cần được chạy qua cả phía producer và consumer. Để kiểm chữ ký đa ngôn ngữ, bổ sung output HMAC/signature của một khóa và thông điệp **dành riêng cho test**, không bao giờ dùng key thật.

## 11. Kiểm thử và xử lý tình huống biên

Một bộ kiểm thử tốt gồm cả tính đúng đắn lẫn trường hợp có khả năng khiến hai hệ thống bất đồng:

| Input / tình huống | Điều cần xác minh |
| --- | --- |
| ASCII `Hello` | UTF-8 chính xác là `48 65 6C 6C 6F`; round trip ổn |
| `é` so với `e\u0301` | Byte thô khác; NFC rồi UTF-8 phải bằng nhau |
| Ligature `ﬃ` so với `ffi` | NFC không buộc chúng bằng nhau; NFKC có thể gộp; chính sách nào được phép? |
| Emoji, ký tự ngoài BMP | `String.length()` khác code point count và byte length; không cắt giữa surrogate |
| Chuỗi chứa surrogate lẻ | Encoder strict từ chối; không âm thầm thay byte trước khi ký |
| Byte UTF-8 sai, ví dụ `C3 28` | Decoder strict từ chối; xác định HTTP status/lỗi xử lý rõ ràng |
| Chuỗi chứa NUL, tab, newline | Parser, validation và serialization phải có quy tắc thống nhất |
| `\r\n`, `\n`, space đầu/cuối | Chỉ biến đổi nếu giao thức/field profile cho phép |
| Username giống hình dáng giữa các bảng chữ | Unicode NFC không giải quyết confusable/homograph; cần chính sách identifier |
| Giá trị `null`, chuỗi rỗng, whitespace-only | Phân biệt ý nghĩa dữ liệu, không nhập nhằng với missing field |
| Bản mã, nonce, digest chứa byte tùy ý | Base64 decode/encode round trip; không dùng `new String(ciphertext, UTF_8)` |
| JSON cùng semantic khác serialization | Raw-body signature khác; canonical JSON chỉ giống nếu cả hai theo cùng chuẩn |
| Nhiều dịch vụ khác phiên bản | Golden vectors khớp giữa các ngôn ngữ và thời điểm triển khai |
| Input rất dài | Kiểm giới hạn kích thước trước và sau normalize; tránh tiêu thụ CPU/bộ nhớ quá mức |

Khi log lỗi, có thể ghi **mã lỗi, request ID và thông tin độ dài/loại encoding đã được làm sạch**; hạn chế in raw password, token, khóa, payload nhạy cảm hoặc String chứa ký tự điều khiển. Nếu cần debug byte có vấn đề, chỉ dùng dữ liệu kiểm thử nhân tạo hoặc cơ chế quan sát được kiểm soát.

### Tách lỗi encoding khỏi lỗi normalization

- `MalformedInputException`/`CharacterCodingException`: input không hợp lệ ở tầng mã hóa/giải mã ký tự.
- Unicode normalization: một **phép chuyển biểu diễn** theo chính sách, không mặc nhiên là phép validation.
- Validation: giới hạn ký tự, độ dài, cấu trúc và quy tắc nghiệp vụ. Nên áp dụng trên dạng mà hệ thống dùng để lưu/so sánh, đồng thời giới hạn cả kích thước đầu vào gốc để chống lạm dụng.
- Authorization: quyết định quyền dựa trên định danh đã được xác thực và một canonical representation nhất quán. Không thể thay bằng charset conversion.

Khi có lỗi, nên từ chối rõ ràng thay vì sửa im lặng rồi để chữ ký/danh tính được xác minh theo một chuỗi khác.

## 12. Lỗi thường gặp và cách sửa

**1. Dùng charset mặc định:** `getBytes()` / `new String(bytes)` tạo hành vi phụ thuộc môi trường. Sửa bằng một `Charset` được ghi rõ trong hợp đồng, thường `StandardCharsets.UTF_8`.

**2. Giả định String giống nhau về hiển thị thì byte giống nhau:** ký tự soạn sẵn và tổ hợp dấu có thể cho byte khác. Sửa bằng chính sách equivalence/normalization theo từng field, hoặc cố tình giữ byte nguyên gốc nếu đó là yêu cầu.

**3. Dùng `String.length()` để giới hạn byte gửi, kích thước DB hoặc khóa:** UTF-8 có độ dài biến thiên, emoji có surrogate pair. Sửa bằng đo đúng đơn vị, nhất là `strictUtf8(text).length` sau normalization và giới hạn input để tránh lạm dụng.

**4. “Chuẩn hóa để mọi thứ tương đương” bằng NFKC/lowercase/trim:** có thể thay đổi tên, mật khẩu và khóa định danh. Sửa bằng chính sách có chủ đích và test các cặp có thể bị nhập làm một.

**5. Giải mã ciphertext bằng UTF-8 để tiện truyền:** byte tùy ý không phải văn bản. Sửa bằng `byte[]`, Base64 hoặc hex cho lớp vận chuyển.

**6. Xác minh HMAC của JSON bằng cách serialize object lại:** whitespace/thứ tự/escape/số có thể đổi. Sửa bằng ký đúng raw bytes hoặc thực hiện canonicalization của giao thức đã thỏa thuận.

**7. Normalize nội dung trước khi kiểm chữ ký raw-body:** thay byte và luôn làm lệch signature ở một số trường hợp. Sửa bằng xác minh theo đúng lớp biểu diễn mà giao thức yêu cầu.

**8. Cho phép encoder/decoder tự thay dữ liệu lỗi:** replacement có thể biến input hỏng thành byte khác và che mất vấn đề. Sửa bằng `REPORT` khi sự chính xác byte là yêu cầu bảo mật.

**9. Thay đổi chính sách giữa chừng mà không version:** signature cũ, dữ liệu AAD cũ hoặc username cũ có thể không xác minh được. Sửa bằng versioned policy, migration và golden vectors.

**10. Để validation và lookup dùng hai dạng chuỗi:** kiểm tra quyền trên ID khác với ID được truy xuất. Sửa bằng một representation được định nghĩa từ đầu đến cuối, kiểm thử tại ranh giới parser–authorization–storage.

## 13. Bài tập thực hành

Một API Java nhận yêu cầu tạo tài liệu có `title` (hiển thị cho người dùng), `externalId` (ID bên đối tác) và `payload` (JSON được đối tác ký bằng HMAC trên raw request body).

Hãy thiết kế giải pháp trước khi code:

1. Đối với `title`, quyết định có dùng NFC hay giữ nguyên; định nghĩa byte UTF-8 để lưu/search và một golden vector cho `é` so với `e\u0301`.
2. Với `externalId`, công bố grammar, validation, canonicalization và mức độ phân biệt chữ hoa/thường; đảm bảo uniqueness check, cache key, authorization và DB lookup dùng nhất quán cùng quy tắc.
3. Với `payload`, mô tả cách lấy **raw request body bytes** và xác minh HMAC **trước khi parse lại JSON**, nếu đúng hợp đồng bên gửi ký raw bytes. Kiểm thử body thêm một khoảng trắng làm thay đổi HMAC.
4. Chỉ ra hành vi khi request chứa malformed UTF-8 hoặc input `String` có surrogate lẻ; xây dựng unit test cho decoder/encoder strict.
5. Thử round trip hai hướng `UTF8 -> String -> UTF8` với văn bản hợp lệ và `byte[] -> Base64 -> byte[]` với dữ liệu ngẫu nhiên. Giải thích vì sao không áp dụng phép round trip đầu tiên cho ciphertext.
6. Nếu sau này đổi chính sách title từ “giữ nguyên” sang NFC, chỉ rõ cách xử lý bản ghi cũ, khóa tra cứu, dữ liệu đã được ký và version của quy tắc.

**Tiêu chí đạt:** biết chính xác **byte nào** được băm/ký/mã hóa, **vì sao** một chuỗi có hoặc không được chuẩn hóa, lúc nào cần giữ nguyên raw bytes, và cách chứng minh Java cùng hệ thống đối tác cho output giống nhau.

## Tài liệu tham khảo

- [Java 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn.
- [Java 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC, NFD, NFKC, NFKD.
- [Java 17 — CharsetEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html) và [CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): xử lý dữ liệu không hợp lệ.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://unicode.org/reports/tr15/): định nghĩa chuẩn tắc và tương thích.
- [RFC 3629 — UTF-8](https://www.rfc-editor.org/rfc/rfc3629): quy tắc biểu diễn UTF-8.
- [RFC 8785 — JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785): canonical JSON cho trường hợp cần serialization xác định.
