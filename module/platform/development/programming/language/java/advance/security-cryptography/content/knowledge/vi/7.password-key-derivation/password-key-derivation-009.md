# 7.9 Tương thích charset, Unicode và quy tắc chuyển đổi mật khẩu giữa các hệ thống

Người dùng có thể gõ **cùng một mật khẩu theo cảm nhận** trên web, ứng dụng Java, Python, Node.js hay một hệ thống cũ nhưng bị từ chối đăng nhập. Một nguyên nhân khó phát hiện là các nền tảng tạo ra **những dãy byte khác nhau trước khi chạy hàm dẫn xuất khóa (KDF) hoặc password hash**: charset khác nhau, Unicode có nhiều biểu diễn hợp lệ, chuỗi bị `trim`/chuyển chữ hoa thường, hoặc thư viện có quy tắc riêng cho giới hạn byte.

Bài này đi từ ký tự → Unicode → byte → KDF, cách thiết lập hợp đồng tương thích, kiểm thử xuyên hệ thống và di chuyển password verifier cũ. **Chính sách chuyển đổi mật khẩu phải được quy định, có phiên bản và kiểm thử bằng byte thật**; một thay đổi làm người dùng không thể đăng nhập, hoặc khiến hai mật khẩu vốn khác nhau trở thành một, đều là lỗi bảo mật.

## 1. Mục tiêu học tập

Sau bài học, bạn sẽ:

1. Giải thích được sự khác nhau giữa **ký tự hiển thị, Unicode code point, UTF-16 code unit, grapheme cluster và byte**.
2. Chỉ ra vì sao `"é"` dựng sẵn và `"e"` + dấu tổ hợp có thể trông giống nhưng tạo byte khác; phân biệt **NFC, NFD, NFKC, NFKD**.
3. Xây dựng một **password profile**: decode, validate, normalize, encode, KDF, salt, tham số, metadata, version và chính sách lỗi.
4. Sử dụng Java 17+ để kiểm thử UTF-8 strict, `Normalizer`, độ dài Unicode, `PBEKeySpec` và `PBKDF2WithHmacSHA256`.
5. Thiết kế **golden vectors** để kiểm tương thích Java/Python/JavaScript và kế hoạch chuyển đổi từ password hash cũ mà không mất tài khoản.

## 2. Phân biệt ba lớp dữ liệu mật khẩu

~~~text
Phím gõ / copy-paste / IME
          |
          v
Dãy Unicode người dùng nhập
          |
          | validate, policy đã định nghĩa, normalization (nếu có)
          v
Dãy Unicode theo password profile
          |
          | encode bằng charset quy định (thường UTF-8 strict)
          v
Dãy byte password
          |
          | password KDF/hash + salt + work factor (+ pepper nếu có)
          v
Verifier lưu trữ: algorithm, profile id, params, salt, hash
~~~

**Ký tự hiển thị** là điều mắt người đọc nhận thấy; **Unicode code point** là mã trừu tượng cho ký tự; **Java `String`** lưu các code point dưới dạng đơn vị UTF-16; còn **KDF** hoạt động theo hợp đồng đầu vào của thư viện, có thể là byte hoặc `char[]`. Đừng gộp cả ba thành một khái niệm “chuỗi password”.

Ví dụ:

| Chuỗi theo code point | Byte UTF-8 | Nhìn trên UI |
| --- | --- | --- |
| `U+00E9` (LATIN SMALL LETTER E WITH ACUTE) | `C3 A9` | é |
| `U+0065 U+0301` (e + COMBINING ACUTE ACCENT) | `65 CC 81` | e + dấu, thường thấy như é |

Hai chuỗi có **byte UTF-8 khác nhau** trước normalization. Vì vậy `hash(passwordBytes)` hoặc KDF trên byte nguyên bản sẽ cho kết quả khác, trừ trường hợp va chạm cực kỳ khó xảy ra của KDF. Khi cùng chọn NFC, cả hai biểu diễn chuyển về cùng một chuỗi Unicode rồi mới encode.

**Không dùng SHA-256 thô để lưu mật khẩu**: ví dụ `hash(passwordBytes)` ở đây là minh họa sự phụ thuộc vào byte, không phải khuyến nghị triển khai. Mật khẩu cần password hashing/KDF chuyên dụng như Argon2id, scrypt hoặc PBKDF2 theo tiêu chuẩn và ràng buộc ứng dụng.

## 3. Charset: Java String không phải byte UTF-8

**Charset** là quy tắc mã hóa ký tự thành byte và giải mã ngược lại. Cùng chuỗi Unicode có thể sinh byte khác nhau:

| Charset | Nhận xét |
| --- | --- |
| **UTF-8** | Mỗi Unicode scalar value mã hóa bằng 1–4 byte; phù hợp cho giao thức mới có tiếng Việt/emoji. |
| **UTF-16LE / UTF-16BE** | Thứ tự byte khác; ký tự ngoài BMP dùng surrogate pair (4 byte); không giống UTF-8. |
| **ISO-8859-1** | Bộ mã một byte, không thể biểu diễn toàn bộ tiếng Việt/emoji. |
| **Windows-1252** | Bộ mã legacy thường thấy; có khác biệt với ISO-8859-1 ở một số mã byte. |
| **Default charset** | Có thể thay đổi theo JVM version/hệ điều hành/cấu hình. Không đủ làm hợp đồng password lâu dài. |

Ví dụ Java sai về khả năng di chuyển:

~~~java
byte[] raw = password.getBytes(); // dùng charset mặc định của môi trường
~~~

Nếu contract là UTF-8 và đầu vào hợp lệ:

~~~java
byte[] raw = password.getBytes(StandardCharsets.UTF_8);
~~~

Cách thứ hai dùng đúng charset tường minh, nhưng phải hiểu **unpaired surrogate**: một `String` Java có thể chứa một code unit UTF-16 thuộc dải surrogate nhưng không có cặp đúng. Một số encoder/decoder tiện ích có thể âm thầm **thay** dữ liệu malformed thay vì từ chối. Để kiểm soát byte mật khẩu, hãy dùng `CharsetEncoder`/`CharsetDecoder` với `CodingErrorAction.REPORT` và **reject** chuỗi/byte Unicode không hợp lệ thay vì thay bằng `?` hoặc ký tự U+FFFD.

Với HTTP/JSON, bước **transport decode** phải rõ ràng. `%C3%A9` trong URL-form-encoded input là biểu diễn của byte UTF-8; nếu gateway đã decode thành chữ `é` thì ứng dụng **không decode thêm lần nữa** hoặc băm nguyên 6 ký tự `%C3%A9`. Không đưa mật khẩu vào URL query: URL thường bị ghi log, lưu lịch sử hoặc chia sẻ qua hệ thống phân tích. Truyền credential qua TLS và luồng xử lý xác thực phù hợp.

## 4. Unicode normalization và lý do phải chọn đúng form

Trong Java:

~~~java
String normalized = Normalizer.normalize(
        password, Normalizer.Form.NFC);
~~~

Unicode đưa ra bốn dạng normalization:

| Form | Cách chuẩn hóa | Tác động tới mật khẩu |
| --- | --- | --- |
| **NFC** | Canonical decomposition + composition | Hợp nhất nhiều chuỗi *canonically equivalent* như `é` dựng sẵn và `e` + dấu tổ hợp. |
| **NFD** | Canonical decomposition | Biểu diễn chuẩn dạng phân rã; khác byte NFC, phải dùng cùng profile. |
| **NFKC** | Compatibility decomposition + composition | Hợp nhất thêm nhiều khác biệt tương thích/hình thức, ví dụ fullwidth `Ａ` và ASCII `A`. |
| **NFKD** | Compatibility decomposition | Có tác động tương thích như NFKC nhưng giữ dạng phân rã. |
| **Không normalize** | Giữ nguyên code point người dùng nhập | Phân biệt cả các chuỗi canonically equivalent; nếu đây là policy lịch sử thì phải giữ khi xác minh hash cũ. |

Các ví dụ:

~~~text
NFC("\u00E9") == NFC("e\u0301")    → true
NFC("Ａ")     == NFC("A")          → false
NFKC("Ａ")    == NFKC("A")         → true
~~~

`Ａ` là FULLWIDTH LATIN CAPITAL LETTER A (U+FF21). NFKC không phải “NFC mạnh hơn nhưng luôn an toàn hơn”: nó **thay đổi tập cặp mật khẩu được coi là tương đương**, có thể gộp các mật khẩu mà người dùng tưởng khác. NFD/NFKD cũng không tự mang lại an toàn cao hơn; sự phù hợp phụ thuộc chính sách sản phẩm và hợp đồng đã lưu.

**NIST SP 800-63B hiện hành khuyến nghị NFC** cho hệ thống chấp nhận Unicode password, trước bước hashing: https://pages.nist.gov/800-63-4/sp800-63b.html . Theo Unicode, NFC xử lý canonical equivalence, trong khi NFKC thêm compatibility equivalence: https://www.unicode.org/faq/normalization.html . Lựa chọn cho hệ thống mới có thể dựa trên khuyến nghị này, nhưng **không được tự động đổi chính sách một cơ sở hash legacy** vì sẽ làm thay byte đầu vào khi login.

### 4.1. Nhìn giống nhau không có nghĩa Unicode tương đương

- Latin `a` (U+0061) khác Cyrillic `а` (U+0430), dù font có thể khiến chúng khó phân biệt. NFC không tự gộp.
- Unicode có **variation selector**, dấu tổ hợp, zero-width joiner và emoji nhiều code point; một hình vẽ trên UI có thể ứng với nhiều dãy code point.
- ASCII space `U+0020` khác non-breaking space `U+00A0` hoặc nhiều loại khoảng trắng Unicode.
- Bộ gõ tiếng Việt, bàn phím di động và copy-paste có thể sinh dạng Unicode khác nhau; không thể bảo đảm byte giống nhau bằng cách chỉ nhìn màn hình.
- Normalization không tự bảo đảm mọi chuỗi trông tương tự thành giống nhau, cũng không hợp thức hóa malformed Unicode.

**Chọn một form cho profile mới rồi dùng đúng form đó tại verifier.** Không normalize thêm “cho chắc” ở nhiều tầng theo những quy tắc khác nhau.

## 5. Những biến đổi nguy hiểm ngoài hợp đồng

Một ứng dụng có thể vô tình đổi password qua các thao tác quen thuộc:

| Biến đổi | Hậu quả |
| --- | --- |
| `trim()` / `strip()` | Xóa whitespace đầu/cuối: `" secret "` khác `"secret"`. |
| `toLowerCase()` / `toUpperCase()` | Làm mất phân biệt chữ hoa thường; quy tắc locale có thể khác nhau. |
| Bỏ dấu tiếng Việt / transliteration | Nhiều chuỗi khác nhau trở thành một; giảm số mật khẩu được phân biệt. |
| Chuyển sang ISO-8859-1 rồi tự thay ký tự ngoài bảng mã | Có thể làm mất thông tin, gây va chạm password sau chuyển đổi. |
| Cắt sau N byte hoặc N `char` | Có thể bỏ phần cuối bí mật hoặc làm hỏng surrogate pair. |
| Thêm BOM, newline, byte NUL kết thúc | Byte input KDF thay đổi; có thể tương tác sai với thư viện legacy. |
| Decode URL/Base64/JSON escape hai lần | Kết quả không còn là chuỗi người dùng gửi theo hợp đồng. |
| Normalize ở client NFKC nhưng server NFC | Dữ liệu qua nhiều đường truy cập khác nhau có thể tạo verifier khác nhau. |

**Một người có quyền dùng khoảng trắng đầu/cuối hoặc chữ viết hoa trong password phải được phân biệt đúng**, trừ khi giao thức được công bố rõ khác đi. Không sử dụng `String.toLowerCase(Locale.ROOT)` hay accent stripping để “ổn định” mật khẩu. Case folding có thể hữu ích với **username**, nhưng là thiết kế khác với password.

Nếu cần **từ chối** một lớp ký tự (ví dụ các control character không được ứng dụng hỗ trợ), công bố/kiểm tra chính sách lúc tạo mật khẩu và áp dụng nhất quán ở login. Từ chối rõ ràng tốt hơn âm thầm đổi dữ liệu. Tránh các quy tắc thành phần bắt buộc không cần thiết làm người dùng khó tạo password mạnh.

## 6. Độ dài phải đo đúng đơn vị

Một emoji khóa `🔒` có:

~~~text
Java String.length()                = 2 UTF-16 code units
String.codePointCount(0, length())  = 1 Unicode code point
UTF-8 encoded length                = 4 bytes
~~~

| Đơn vị | Ý nghĩa | Trong Java |
| --- | --- | --- |
| **UTF-16 code unit** | Đơn vị `char` 16 bit; ký tự ngoài BMP thường dùng một cặp surrogate | `String.length()` |
| **Unicode code point** | Giá trị U+0000...U+10FFFF đại diện một ký tự mã hóa; có thể nhiều code point cho một cụm hiển thị | `String.codePointCount(0, s.length())` với Unicode hợp lệ |
| **Grapheme cluster** | Cụm ký tự hiển thị người dùng thường cảm nhận là một đơn vị | Phân đoạn grapheme theo Unicode; không mặc nhiên bằng code point |
| **UTF-8 byte** | Số byte thực sẽ đưa cho KDF/giao thức có byte interface | `s.getBytes(StandardCharsets.UTF_8).length` khi chuỗi hợp lệ |

Theo NIST, **độ dài password có Unicode được tính theo Unicode code point**, còn giới hạn của thuật toán có thể theo **byte**; hai quy tắc đều cần được xem xét. Hệ thống phải có trần tài nguyên hợp lý để chống quá tải, nhưng **không được âm thầm truncate** password rồi chỉ hash phần đầu. Ở bước tạo/đổi password, báo lỗi chính sách rõ; ở đăng nhập, xử lý nhất quán với account verifier đã lưu.

**bcrypt legacy:** nhiều triển khai bcrypt truyền thống chỉ xử lý **72 byte đầu**, trong khi một số thư viện mới từ chối đầu vào dài hơn thay vì cắt. 72 byte **không phải 72 code point**. Hệ thống cũ còn có thể xử lý byte NUL đặc biệt. Khi di chuyển, phải kiểm thử đúng version/variant/provider và quy tắc xử lý vượt giới hạn; không tự tiếp tục cắt 72 byte trong profile mới.

## 7. Định nghĩa password profile xuyên hệ thống

Để Java, Python, JavaScript và dịch vụ legacy xác minh cùng password, hãy định nghĩa **byte-level contract**. Ví dụ một profile **mới**:

~~~text
profile_id: pwd-utf8-nfc-v1

Transport:
  - Request được giải mã theo protocol xác định, UTF-8 strict.
  - Reject malformed Unicode/UTF-8; không thay bằng U+FFFD.
Input policy:
  - Chấp nhận Unicode hợp lệ, áp dụng giới hạn độ dài đã định nghĩa.
  - Không trim/casefold/loại dấu, không tự decode lớp escape lần hai.
Transform:
  - Unicode normalization = NFC.
  - Encode UTF-8 strict, không BOM, không NUL terminator.
KDF:
  - Algorithm + implementation/variant + salt bytes + work factor
    + output length + pepper policy (nếu có) đều được quy định.
Stored verifier:
  - algorithm, profile_id, cost params, salt, derived verifier;
    không lưu plaintext hoặc normalized password.
~~~

Pipeline phải có **thứ tự rõ ràng**:

1. Decode input theo giao thức bằng decoder strict; reject malformed sequences.
2. Kiểm tra chính sách đầu vào như giới hạn tài nguyên và tập ký tự cho phép.
3. Normalize đúng form đã ghi trong profile; không dùng form khác khi login.
4. Encode thành byte UTF-8 strict; xác minh độ dài/limit theo thuật toán.
5. Thực hiện password KDF với chính xác salt và các tham số tương ứng account.
6. Gọi bộ xác minh của thư viện chuẩn; trả kết quả, không ghi lại mật khẩu.

**Số lần normalize**: dùng cùng một phép chuẩn hóa cố định là idempotent (áp dụng lại không đổi kết quả), nhưng các tầng không được sử dụng những phép biến đổi **khác nhau** ngoài contract. Chính sách mới cần rõ ai làm việc này: UI có thể hỗ trợ người dùng, nhưng **verifier phía server** phải là nơi quyết định và thực hiện chính sách mật mã.

### 7.1. KDF cũng có hợp đồng dữ liệu riêng

Với PBKDF2, cả hai bên phải thống nhất:

- PRF chính xác: `HmacSHA256` khác `HmacSHA1` hoặc `HmacSHA512`.
- **Password bytes** hoặc cách provider chuyển `char[]` thành password material.
- **Salt bytes**, cách giải mã salt hex/Base64 nếu lưu dưới dạng text; salt phải được sinh ngẫu nhiên riêng khi tạo verifier thật.
- **Iteration count**, length key và đơn vị: `PBEKeySpec(..., keyLength)` nhận **bit**, nhiều thư viện khác dùng byte.
- Provider/version và định dạng kết quả; xác minh qua **golden vectors Unicode**.
- Nếu có pepper: secret ngoài DB, pepper version/key ID, vị trí áp dụng trước/sau KDF theo thiết kế được thẩm định.

Với Argon2id, hợp đồng còn gồm memory cost, time cost, parallelism, version và length; với bcrypt cần variant `$2a$`/`$2b$`/`$2y$`, cost, giới hạn đầu vào, preprocessing. Không có lý do để tự viết lại KDF nhằm đạt tương thích: sử dụng thư viện chuẩn và kiểm byte chính xác.

### 7.2. Ranh giới `PBEKeySpec` của Java

`javax.crypto.spec.PBEKeySpec` nhận password bằng `char[]`, **không nhận byte UTF-8 trực tiếp**. Tài liệu JCA nêu các cơ chế password-based encryption khác nhau có thể sử dụng các phần bit khác nhau của từng `char`; vì vậy **không thể suy từ tên thuật toán rằng tất cả Java providers và thư viện Python/Node chuyển Unicode thành byte như nhau**. Với `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")`, phải biết triển khai thực tế và xác minh các vector trên Unicode.

Java `PBEKeySpec` clone mảng password đầu vào; gọi `clearPassword()` xóa bản sao nội bộ, còn chủ sở hữu `char[]` phải xóa mảng của mình. `String` immutable và normalization thường tạo String trung gian nên việc xóa hết mọi bản sao memory không hoàn toàn bảo đảm. Hạn chế thời gian sống của secret, không in log, không cố giữ mật khẩu dưới dạng String lâu dài trong production.

## 8. Ví dụ Java 17+ chạy được

Chương trình dùng **các mẫu vô hại**, không dùng password người thật. Nó minh họa byte UTF-8, normalization, số code unit/code point, kiểm charset lỗi và kết quả PBKDF2 trong **cùng một provider Java**. Phần PBKDF2 đặt **10.000 iteration CHỈ để demo nhanh**; cấu hình production phải theo tiêu chuẩn và benchmark hiện hành với salt mới cho mỗi password.

Lưu tên file chính xác **`PasswordInteropDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class PasswordInteropDemo {
    static byte[] strictUtf8(char[] chars) throws CharacterCodingException {
        ByteBuffer buffer = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(chars));
        byte[] result = new byte[buffer.remaining()];
        buffer.get(result);
        return result;
    }

    // Tham số chỉ cho demo; không dùng 10.000 rounds trong production.
    static byte[] deriveNfc(String password, byte[] salt) throws Exception {
        char[] normalized = Normalizer
                .normalize(password, Normalizer.Form.NFC).toCharArray();
        PBEKeySpec spec = new PBEKeySpec(normalized, salt, 10_000, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
            Arrays.fill(normalized, '\0');
        }
    }

    public static void main(String[] args) throws Exception {
        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("Raw equal           = " +
                composed.equals(decomposed));
        System.out.println("UTF-8 composed      = " +
                HexFormat.of().formatHex(
                        strictUtf8(composed.toCharArray())));
        System.out.println("UTF-8 decomposed    = " +
                HexFormat.of().formatHex(
                        strictUtf8(decomposed.toCharArray())));
        System.out.println("NFC equal           = " +
                Normalizer.normalize(composed, Normalizer.Form.NFC).equals(
                Normalizer.normalize(decomposed, Normalizer.Form.NFC)));

        String wideA = "\uFF21";
        System.out.println("NFC fullwidth == A  = " +
                Normalizer.normalize(wideA, Normalizer.Form.NFC)
                        .equals("A"));
        System.out.println("NFKC fullwidth == A = " +
                Normalizer.normalize(wideA, Normalizer.Form.NFKC)
                        .equals("A"));

        String emoji = "\uD83D\uDD12";
        System.out.println("Emoji UTF-16 units  = " + emoji.length());
        System.out.println("Emoji code points   = " +
                emoji.codePointCount(0, emoji.length()));
        System.out.println("Emoji UTF-8 bytes   = " +
                strictUtf8(emoji.toCharArray()).length);
        System.out.println("Spaces preserved    = " +
                !" pass ".equals("pass"));

        byte[] salt = HexFormat.of().parseHex(
                "000102030405060708090a0b0c0d0e0f");
        byte[] keyA = deriveNfc(composed, salt);
        byte[] keyB = deriveNfc(decomposed, salt);
        try {
            System.out.println("NFC PBKDF2 equal    = " +
                    MessageDigest.isEqual(keyA, keyB));
        } finally {
            Arrays.fill(keyA, (byte) 0);
            Arrays.fill(keyB, (byte) 0);
        }

        boolean malformedRejected = false;
        try {
            strictUtf8(new char[] { (char) 0xD800 });
        } catch (CharacterCodingException expected) {
            malformedRejected = true;
        }
        System.out.println("Unpaired rejected   = " +
                malformedRejected);
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac PasswordInteropDemo.java
java PasswordInteropDemo
~~~

Stdout chính xác:

~~~text
Raw equal           = false
UTF-8 composed      = c3a9
UTF-8 decomposed    = 65cc81
NFC equal           = true
NFC fullwidth == A  = false
NFKC fullwidth == A = true
Emoji UTF-16 units  = 2
Emoji code points   = 1
Emoji UTF-8 bytes   = 4
Spaces preserved    = true
NFC PBKDF2 equal    = true
Unpaired rejected   = true
~~~

**Đọc kết quả:**

1. Hai cách biểu diễn `é` khác byte trước NFC; sau NFC chúng cho cùng chuỗi.
2. NFKC làm fullwidth `Ａ` thành ASCII A, NFC giữ khác biệt.
3. `String.length()` không phải số Unicode code point hoặc UTF-8 byte; emoji cần 2 code units và 4 byte UTF-8.
4. Hàm encoder strict từ chối unpaired surrogate; các luồng nhận UTF-8 từ mạng cũng cần **decoder strict** trước khi tạo String.
5. PBKDF2 bằng nhau vì đầu vào NFC, salt, iteration, keyLength và provider giống nhau. **Chưa chứng minh Java/Python/Node interop**; phải chạy test vector thật trên mọi implementation.
6. `10_000` iterations và **salt cố định** chỉ phục vụ kiểm thử bài học. Với password thật, tạo **salt mới, đủ dài và ngẫu nhiên bằng SecureRandom cho mỗi password**, chọn password KDF/work factor phù hợp; không in derived key trong log.

Trong demo, `Normalizer.normalize` sinh String trung gian không thể xóa trực tiếp. Các mảng `char[]` do chương trình quản lý được xóa và `PBEKeySpec.clearPassword()` xóa bản sao nội bộ; đây là giảm rủi ro, **không bảo đảm dọn mọi bản sao bí mật khỏi RAM**.

## 9. So sánh Java, Python và JavaScript

| Nền tảng | Biểu diễn nội bộ | Điểm cần kiểm |
| --- | --- | --- |
| **Java** | `String`/`char[]` chứa UTF-16 code units; `PBEKeySpec` nhận char[] | Charset mặc định, `Normalizer`, strict encoder, provider char→byte. |
| **Python 3** | `str` Unicode; `unicodedata.normalize`; `encode` | Cùng form Unicode, UTF-8 strict và KDF nhận đúng raw bytes. |
| **Node.js** | JS String dùng UTF-16; `String.normalize`; `Buffer.from(..., "utf8")` | Đếm `length` là code units, unpaired surrogate cần xử lý và library hash có byte rules riêng. |
| **Legacy** | Có thể dùng ISO-8859-1, Windows-1252, UTF-16LE hay byte array NUL-terminated | Xác định chính xác bytes trước hash, giới hạn độ dài/loại bỏ ký tự và cách normalize cũ. |

Đoạn chuyển Unicode thành UTF-8 theo profile NFC bên Python:

~~~python
import unicodedata

# password đã được kiểm tra tính hợp lệ theo giao thức.
password_bytes = unicodedata.normalize("NFC", password).encode(
    "utf-8", errors="strict"
)
~~~

Đoạn tương ứng bên Node.js:

~~~javascript
// Phải validate Unicode, đặc biệt unpaired surrogate, trước bước này.
const passwordBytes = Buffer.from(password.normalize("NFC"), "utf8");
~~~

Đó chỉ là **bước tạo byte**, không phải phương thức hash password hoàn chỉnh. Một số API JS sẽ thay surrogate lỗi khi tạo buffer; vì vậy phải có bước kiểm input strict trước đó. Khi Java dùng `PBEKeySpec` nhưng Python nhận raw bytes, hãy so **golden vectors chứa Unicode** để xác nhận provider Java thực sự dẫn xuất từ cùng dãy byte theo hợp đồng; đừng dựa vào tên `PBKDF2WithHmacSHA256` là đủ.

**Bẫy khác:** Bên A đưa byte của password vào KDF, bên B lại đưa **chuỗi hex hoặc Base64 của các byte**. Hex/Base64 là **biểu diễn**, không có lý do để dùng thêm một lớp encode trước KDF trừ khi profile lịch sử quy định chính xác như vậy.

## 10. Golden vectors: kiểm tương thích bit-for-bit

Dùng mẫu thử cố định **không chứa credential thật** và ghi cả dãy byte sau preprocessing:

| Vector | Điều kiện kiểm | Kết quả sau profile NFC + UTF-8 |
| --- | --- | --- |
| ASCII `abc` | Baseline | `61 62 63` |
| `é` = U+00E9 | Precomposed | `C3 A9` |
| `e` + U+0301 | Decomposed | **Cũng** `C3 A9` |
| `Ａ` = U+FF21 | NFC không compatibility-fold | **Khác** `A` ASCII |
| `" pass "` | Không trim | Khác `"pass"` |
| `🔒` | Ngoài BMP | 1 code point, 2 code units, 4 byte |
| Latin `a` và Cyrillic `а` | Confusable | Không bị NFC gộp |
| Unpaired surrogate | Malformed UTF-16 | Reject |
| Malformed UTF-8 từ transport | Malformed input | Reject, không thay U+FFFD |
| Chuỗi vượt giới hạn policy | Không truncate | Trả lỗi theo chính sách |

Golden vectors cho **KDF** còn chứa byte salt, PRF/algorithm, iteration hoặc memory/time cost, output length, variant, pepper giả cho test (nếu có) và **expected derived bytes**. Mỗi implementation phải trả **cùng byte** đối với cùng vector. Đừng chỉ dùng ASCII: UTF-8 và nhiều bộ mã cũ giống nhau trên ASCII, che giấu lỗi với password tiếng Việt.

Quy trình kiểm:

~~~text
1. Parse input theo protocol, reject malformed.
2. Validate Unicode và policy.
3. Normalize đúng profile.
4. Encode UTF-8 strict, so expected passwordBytes.
5. Gọi KDF với fixed test salt + params.
6. So derived result/verify với expected value.
7. Chạy negative tests: khác charset, khác normalization,
   whitespace, emoji, malformed input, key length, salt, cost.
~~~

Chạy lại vector khi nâng cấp JVM, JCE provider, Unicode tables, thư viện password hash hoặc thay đổi gateway/API. Một phép round-trip `decode(encode(s)) == s` **chưa đủ** để chứng minh hai hệ thống chọn cùng charset hoặc cùng KDF policy, và chưa phát hiện lỗi decoder thay ký tự đầu vào.

## 11. Lưu hash với profile để tương thích dài hạn

Một verifier lưu trữ nên có đủ metadata để kiểm bằng **đúng phiên bản đã tạo**:

~~~text
account_id
password_profile_id = pwd-utf8-nfc-v1
password_algorithm  = Argon2id / PBKDF2-HMAC-SHA256 / bcrypt...
salt                 = binary or documented Base64 form
cost_parameters      = iterations / memory / time / parallelism
hash_or_derived_key  = binary or documented encoded form
algorithm_variant    = ...
pepper_key_id        = ... (nếu có)
~~~

Một số thư viện tự chứa thuật toán/cost/salt trong encoded hash, chẳng hạn PHC-format cho Argon2id hoặc modular crypt format cho bcrypt. Tuy vậy, **charset và normalization policy không nhất thiết nằm trong đó**; hãy lưu `password_profile_id` nếu muốn tương thích/migrate rõ ràng.

- **Salt** công khai, riêng mỗi password và ngẫu nhiên; không nên dùng salt cố định chung cho mọi người.
- **Pepper** là bí mật server giữ ngoài DB nếu lựa chọn dùng; cần quản lý key/version, không thay salt.
- **Work factor** nên được chọn theo tham chiếu bảo mật và benchmark phù hợp hệ thống; nâng cost phải xử lý migration.
- Không lưu plaintext, normalized text, password bytes hay dấu vết debug của chúng.
- Không dùng `String.hashCode()`, checksum, SHA-256 thuần hoặc Base64 thay password hashing chuyên dụng.

## 12. Migration từ hệ thống đã có password hash

**Không thể biến password hash cũ thành hash mới chỉ bằng cách hash hash cũ** để tương ứng với byte Unicode mới: KDF một chiều, không chứa thông tin gốc cần normalize/encode. Cách làm thông dụng là **xác minh theo profile cũ trước**, sau đó rehash **candidate password người dùng vừa cung cấp** theo profile mới.

~~~text
login(account, candidate):
    record = loadVerifier(account)
    profile = lookupById(record.password_profile_id)

    if !verifyWithRecordedProfile(candidate, record, profile):
        denyAccess()

    if isEligibleForUpgrade(record):
        replacement = newVerifier(candidate, newProfile, newRandomSalt)
        atomicCompareAndSwap(record, replacement)

    allowLogin()
~~~

Đây là **pseudocode** giải thích luồng, không phải Java độc lập. Cần lưu ý:

1. **Chọn đúng một profile theo metadata account** để verify. Không thử hàng loạt encoding/normalization tùy tiện vì có thể **mở rộng tập mật khẩu được chấp nhận** và làm phức tạp audit/timing.
2. Với legacy chưa có metadata, phải dựa vào bằng chứng cấu hình/thời điểm tạo/tenant hoặc có lộ trình **đặt lại mật khẩu**. Không thể đoán byte password gốc chỉ từ hash.
3. Sau khi xác thực thành công, rehash bằng profile mới và **salt mới**; cập nhật atomically để không ghi đè lần đổi password đồng thời.
4. Nếu từ “raw bytes” sang NFC, một số cách gõ trước đây từng là **mật khẩu khác** nay có thể được coi là cùng password. Cần đánh giá tác động với người dùng và quy tắc xác thực.
5. Với bcrypt cũ có giới hạn 72 byte hoặc xử lý NUL, xác minh chính xác theo thư viện cũ và cân nhắc **yêu cầu đổi password** trước khi chuyển, tránh giữ quy tắc truncate không an toàn.
6. Không chuyển profile ID của DB khi chưa tạo verifier mới, không lưu plaintext để “migrate hàng loạt”.

Một ví dụ cụ thể: hệ cũ dùng Windows-1252 rồi PBKDF2; Java mới dùng NFC + UTF-8. Password ASCII có thể vẫn chạy. Password có tiếng Việt hoặc dấu tổ hợp có thể thất bại vì Windows-1252 không biểu diễn được. Cách giải quyết không phải **decode hash cũ sang UTF-8**, mà là kiểm đúng account bằng quy tắc cũ đã biết rồi thay verifier sau khi người dùng nhập đúng password, hoặc reset nếu hành vi cũ không thể tái hiện an toàn.

## 13. Lỗi vận hành và an toàn thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Dùng `password.getBytes()` với charset mặc định | Kết quả phụ thuộc runtime, đặc biệt hệ cũ | UTF-8 tường minh và test vector. |
| Đếm `String.length()` như số ký tự hiển thị | Sai giới hạn, emoji bị tính hai | Tách code unit, code point, byte. |
| `trim` trước hash | Hai password khác nhau bị gộp | Giữ nguyên whitespace trừ policy có chủ ý. |
| NFKC bất ngờ sau nâng cấp | Compatibility characters bị gộp với ASCII | Dùng profile/version và migration. |
| Encoder/decoder thay malformed input | Mất byte gốc, hai chuỗi khác thành giống | `CodingErrorAction.REPORT` và reject. |
| Nhầm hex/Base64 salt text với raw salt bytes | PBKDF2 luôn lệch | Decode salt đúng theo stored format. |
| Nhầm length 256 bit và 256 byte | Derived key mismatch | Quy định đơn vị tham số rõ ràng. |
| Băm JSON text chứa password thay vì password value | Byte khác hệ thống kia | Decode đúng JSON, xác định trường value. |
| Test chỉ `"password123"` | ASCII che giấu charset mismatch | Golden vectors chứa Unicode, emoji, combining mark. |
| Thử mọi legacy charset trên login | Chấp nhận thêm password ngoài dự kiến, khó kiểm toán | Profile định danh theo record và reset nếu không xác định. |
| Rehash hash cũ sang profile mới | Không thể tạo verifier của password input mới | Verify candidate rồi rehash, hoặc reset. |
| Log normalized password/derived key để debug | Rò rỉ credential | Chỉ log mã lỗi, metric không nhạy cảm. |
| Nhầm salt và pepper | Quản lý key/salt sai | Salt công khai riêng mỗi password; pepper bí mật tách khỏi DB. |
| Dùng mã SHA-256 thô để lưu password | Băm quá nhanh cho tấn công đoán offline | Dùng password hashing/KDF phù hợp và cost đủ mạnh. |

**Ghi nhớ lỗi phổ biến trên HTTP:** Một password đi qua browser, reverse proxy, framework request parser, authentication middleware, thư viện hash rồi DB. Nếu **mỗi tầng tự ý áp charset/normalize**, khó tìm nguyên nhân. Hãy đưa profile tập trung vào verifier và kiểm thử end-to-end cả JSON, form encoding, request length, byte payload, KDF và DB metadata. Không ghi mật khẩu vào trace khi điều tra.

## 14. Câu hỏi tự kiểm tra và đáp án

**Câu 1:** `é` (U+00E9) và `e` + U+0301 có chắc cho cùng KDF key không?

**Đáp án:** Chỉ khi **cùng profile** (chẳng hạn NFC trước UTF-8), cùng salt/cost/algorithm/provider và cùng input bytes theo định nghĩa KDF. Nếu băm raw UTF-8 bytes thì hai dạng khác nhau.

**Câu 2:** `Ａ` và `A` có như nhau theo NFC không? Theo NFKC thì sao?

**Đáp án:** NFC giữ khác; NFKC compatibility-fold có thể đưa `Ａ` về ASCII `A`, nên hai mật khẩu trở thành tương đương theo policy NFKC.

**Câu 3:** Emoji `🔒` có `String.length()==2`. Vậy nó dài 2 byte?

**Đáp án:** Không. Đó là 2 UTF-16 code units, **1 code point** và **4 UTF-8 byte**. Với ký tự tổ hợp, số code point cũng chưa chắc bằng số grapheme cluster hiển thị.

**Câu 4:** Có nên `strip()` password cho người dùng dễ nhập?

**Đáp án:** Không tự ý. Khoảng trắng có thể là thành phần password, và strip sẽ âm thầm gộp nhiều mật khẩu thành một.

**Câu 5:** Java và Python đều dùng PBKDF2-HMAC-SHA256 nhưng hash tiếng Việt khác nhau, nên điều tra gì?

**Đáp án:** Kiểm Unicode code points, normalization, UTF-8/legacy charset, provider char→byte, salt bytes, iteration, derived-key length bit/byte, pepper, version/variant và test vector cụ thể.

**Câu 6:** Có thể chuyển tất cả hash cũ từ Latin-1 sang UTF-8/NFC mà không biết password?

**Đáp án:** Không. Verifier là hàm một chiều. Cần verify theo profile cũ bằng candidate hợp lệ rồi tạo verifier mới, hoặc reset password khi cần.

**Câu 7:** bcrypt cũ nhận tối đa 72 byte, mật khẩu có 60 ký tự tiếng Việt chắc chắn nằm dưới 72 byte?

**Đáp án:** Không. UTF-8 có thể dùng nhiều byte cho mỗi ký tự; phải đo **byte** và xác định hành vi thật của bcrypt implementation. Không âm thầm cắt.

**Câu 8:** Vì sao encoder strict từ chối unpaired surrogate hữu ích cho tương thích bảo mật?

**Đáp án:** Nếu một bên thay surrogate lỗi bằng `?`/U+FFFD còn bên kia từ chối hoặc thay khác, dữ liệu mật khẩu bị mất thông tin và tạo byte khác. Reject rõ ràng giúp thống nhất hành vi.

**Câu 9:** Golden vector chứa ASCII và đúng 1 salt có đủ chứng minh Java/Node/legacy tương thích?

**Đáp án:** Không. Cần vector Unicode (composed/decomposed, fullwidth, emoji, spaces), malformed input, limits, salt/iterations/params và expected derived bytes, chạy cùng bộ test trên mọi runtime.

## 15. Checklist trước khi đưa vào production

- [ ] Có **profile ID/version** cho cách nhận Unicode, normalize, encode và KDF.
- [ ] HTTP/JSON/transport decode strict, không thay malformed UTF-8/UTF-16 bằng ký tự khác.
- [ ] NFC/NFD/NFKC/none được chọn rõ; không trim, casefold, loại dấu ngoài contract.
- [ ] UTF-8 byte input được kiểm bằng test vector; không thêm BOM/NUL/newline ngoài giao thức.
- [ ] Chiều dài code point, UTF-16 code unit và byte được phân biệt; không truncate password.
- [ ] Xác nhận giới hạn password KDF/bcrypt và hành vi của provider/version đang dùng.
- [ ] Salt riêng ngẫu nhiên, cost/algorithm/PRF/length/variant rõ ràng, metadata đủ verify.
- [ ] Các ngôn ngữ cùng chạy **Unicode golden vectors và negative cases**.
- [ ] Legacy account được verify theo **đúng policy lúc tạo**, chỉ migrate sau đăng nhập hợp lệ hoặc reset.
- [ ] Không lưu/log plaintext, normalized password, byte password, derived key hay secrets.
- [ ] Sử dụng password hashing/KDF theo tiêu chuẩn/thư viện đáng tin và cost production đã được benchmark.

**Kết luận:** **Byte đầu vào KDF là kết quả của cả một hợp đồng chuyển đổi**, không chỉ của hàm hash. Muốn password tương thích qua Java và các hệ thống khác, phải cố định và kiểm thử toàn bộ chuỗi **transport → Unicode → normalization → UTF-8 → password KDF + salt/params**, sau đó version hóa để nâng cấp hoặc chuyển đổi mà không phá vỡ cách xác minh của tài khoản cũ.
