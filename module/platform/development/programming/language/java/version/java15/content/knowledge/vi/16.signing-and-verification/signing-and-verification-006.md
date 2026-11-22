# Charset, chuẩn hóa văn bản và biểu diễn thông điệp khi ký/xác minh trong Java

Một chữ ký số **không được tính trên “câu chữ mà mắt nhìn thấy”**, mà trên **dãy byte chính xác** được đưa cho thuật toán ký. Vì vậy, hai chuỗi văn bản trông giống nhau trên màn hình vẫn có thể tạo ra byte khác nhau; một JSON chứa cùng dữ liệu nhưng đổi thứ tự thuộc tính vẫn có thể làm xác minh chữ ký thất bại. Khi sử dụng chữ ký số trong Java, **charset, Unicode normalization, ký tự xuống dòng và quy tắc serialize thông điệp** là một phần của giao thức bảo mật, không phải chi tiết trình bày tùy ý.

Trong Java 15, **EdDSA** (bao gồm Ed25519 và Ed448) được bổ sung vào JDK theo **JEP 339**. Các nguyên tắc biểu diễn dữ liệu dưới đây vẫn áp dụng cho **Java 15 và Java hiện đại** cùng API JCA `java.security.Signature`. Ví dụ hoàn chỉnh dùng Java 17+ và thuật toán Ed25519.

**Quy tắc trung tâm:** bên ký và bên xác minh phải thống nhất *đúng chuỗi byte được ký*. Nếu giao thức quy định chuẩn hóa dữ liệu trước khi ký, **cả hai bên phải áp dụng cùng một phép biến đổi đã được định nghĩa trước**. Nếu giao thức ký **byte nguyên gốc khi truyền**, bên xác minh phải dùng đúng byte nguyên gốc, **không tự sửa nội dung**.

## 1. Ba tầng: văn bản, mã hóa và byte được ký

Với một thông điệp do người dùng nhập, luồng có thể là:

```text
Nội dung nghiệp vụ (ví dụ: tên, số tiền, mã giao dịch)
                |
                v
Biểu diễn thông điệp theo quy tắc giao thức
  - trật tự trường
  - dấu phân cách, escaping và kiểu dữ liệu
  - chuẩn hóa Unicode nếu hợp đồng có quy định
  - line endings, whitespace và định dạng ngày/số
                |
                v
Mã hóa ký tự bằng charset xác định (ví dụ UTF-8)
                |
                v
byte[] CHÍNH XÁC --------------------+
                |                    |
                v                    v
       Signature.update(bytes)   Truyền/lưu bytes đã ký
                |
                v
              sign()
                |
                v
        byte[] chữ ký số

Bên xác minh: tái tạo/lấy đúng byte[] theo giao thức
               + public key đáng tin cậy
               + byte[] chữ ký
                  |
          initVerify -> update -> verify
```

Ba thuật ngữ dễ nhầm:

- **`String`**: văn bản Unicode trong Java, có các vị trí logic UTF-16; không phải tự thân là một định dạng truyền trên mạng.
- **Charset**: quy tắc chuyển giữa ký tự và byte, ví dụ UTF-8, UTF-16LE hoặc ISO-8859-1.
- **Biểu diễn thông điệp** (*message representation/serialization*): quy tắc quyết định văn bản hoặc cấu trúc dữ liệu nào, với dấu phân cách và thứ tự nào, được chuyển thành byte để ký.

Đầu vào của `Signature.update(...)` là **byte**; nó không tự chọn charset, không tự chuẩn hóa Unicode, không tự sắp xếp JSON và không tự diễn giải nội dung văn bản.

## 2. Charset: không để hệ thống tự đoán

Ví dụ ký một câu tiếng Việt:

```java
import java.nio.charset.StandardCharsets;

String message = "Đã nhận đơn hàng";
byte[] signedBytes = message.getBytes(StandardCharsets.UTF_8);
```

`StandardCharsets.UTF_8` cung cấp charset UTF-8 xác định và luôn được Java hỗ trợ. Khi xác minh, bên nhận phải dùng **chính dãy byte UTF-8** ấy, hoặc tái tạo y hệt theo đúng hợp đồng giao thức.

**Không nên viết:**

```java
byte[] signedBytes = message.getBytes();
```

Overload không có tham số dùng **default charset** của môi trường JVM. Trên Java 15/17, mặc định có thể phụ thuộc cấu hình/OS; từ Java 18, JEP 400 chuẩn hóa UTF-8 làm default trong các trường hợp thông thường nhưng vẫn có các chế độ tương thích. **Không dùng charset mặc định cho một giao thức chữ ký**, kể cả khi môi trường triển khai hiện tại trả về UTF-8.

Cũng không thay bằng:

```java
byte[] otherBytes = message.getBytes(StandardCharsets.UTF_16LE);
```

Dù hai cách bắt đầu từ cùng một `String`, UTF-8 và UTF-16LE tạo ra **dãy byte khác nhau**. Chữ ký trên UTF-8 không xác minh được với phiên bản UTF-16LE. Nếu một giao thức đã chọn UTF-16LE thì có thể dùng nó, nhưng **hai bên phải chọn giống nhau**, gồm cả byte order và cách xử lý BOM.

### Một số khác biệt quan trọng

| Yếu tố | Tại sao ảnh hưởng đến chữ ký? | Quy tắc tốt |
| --- | --- | --- |
| UTF-8 so với UTF-16LE | Byte khác nhau ngay cả khi văn bản giống nhau | Chỉ định charset trong đặc tả |
| Có/không có UTF-8 BOM (`EF BB BF`) | BOM là ba byte thực nếu nằm trong payload được ký | Nêu rõ payload có BOM hay không; không tự thêm/xóa |
| Mã hóa không biểu diễn được ký tự | Có thể gây thay thế ký tự hoặc lỗi | Với dữ liệu cần toàn vẹn, nên từ chối input malformed |
| `getBytes()` mặc định | Kết quả có thể phụ thuộc môi trường/cấu hình | Dùng `getBytes(StandardCharsets.UTF_8)` |
| Chuyển byte sang `String` rồi mã hóa lại | Có thể thay byte nếu decode sai, có dữ liệu malformed hoặc biến đổi văn bản | Giữ byte gốc nếu giao thức ký byte gốc |

**Không nhầm byte với độ dài String:** `String.length()` đếm UTF-16 code unit; không cho biết số byte UTF-8, số code point hoặc số “ký tự hiển thị”. Vì vậy không cắt `byte[]` theo `message.length()` khi truyền vào `update(...)`.

## 3. Unicode normalization: NFC, NFD và các dạng khác

Một chữ có dấu có thể có nhiều biểu diễn Unicode tương đương về mặt chuẩn tắc:

- **NFC** (*Normalization Form C*): thường dùng dạng **composed**, ví dụ `é` là code point `U+00E9`.
- **NFD** (*Normalization Form D*): dạng **decomposed**, ví dụ `e` (`U+0065`) + dấu sắc kết hợp `U+0301`.

Hai chuỗi thường hiển thị thành một hình chữ giống nhau nhưng byte UTF-8 **khác nhau**:

```java
String composed = "\u00E9";
String decomposed = "e\u0301";
System.out.println(composed.equals(decomposed)); // false
```

Java có API chuẩn hiện hành:

```java
import java.text.Normalizer;

String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
```

**NFC/NFD không tự được JCA áp dụng.** Nếu bên ký ký chuỗi NFC còn bên xác minh truyền thẳng NFD vào `Signature.update(...)`, xác minh sẽ thất bại dù người đọc nghĩ hai chuỗi giống nhau.

### Nên chuẩn hóa vào lúc nào?

Có **hai kiểu giao thức hợp lệ**, nhưng không được trộn tùy tiện:

**Kiểu A — Ký byte gốc:** gửi chính byte payload đã được ký. Bên xác minh phải giữ nguyên và xác minh **trên byte ấy**, không tự gọi `Normalizer.normalize(...)`, không trim, không sửa line endings.

**Kiểu B — Ký biểu diễn chuẩn tắc đã thỏa thuận:** cả bên ký và bên xác minh cùng biến đổi một đối tượng thông điệp thành **cùng một biểu diễn chuẩn**, ví dụ quy định rõ các trường text được chuyển sang NFC, phân cách xuống dòng LF, UTF-8 không BOM, thứ tự trường cố định; sau đó ký byte kết quả. Hợp đồng phải được thống nhất và kiểm thử ở tất cả hệ thống.

Trong kiểu B, việc chuẩn hóa phải được quy định **trước khi triển khai**; không nên chữa một chữ ký không hợp lệ bằng cách thử lần lượt NFC, NFD, trim, bỏ BOM hoặc đổi charset đến khi verify thành công. Việc “thử hết các phiên bản” làm mờ ranh giới dữ liệu thực sự đã được ký.

Ngoài NFC và NFD còn có **NFKC/NFKD** (*compatibility normalization*). Các dạng này có thể thay đổi sự phân biệt mang nghĩa giữa các ký tự tương thích; **không tự đổi sang NFKC khi giao thức chỉ yêu cầu NFC**. Đối với định danh, mật khẩu, tên pháp lý, mã giao dịch hoặc dữ liệu cần bảo toàn chính xác, hãy định nghĩa chính sách rõ ràng thay vì chuẩn hóa tất cả.

## 4. Dấu xuống dòng và khoảng trắng là byte dữ liệu

Ví dụ cùng một câu có dấu xuống dòng:

```java
String lf = "order=123\n";
String crlf = "order=123\r\n";
```

- LF: một ký tự `\n`, byte `0A` trong UTF-8.
- CRLF: hai ký tự `\r\n`, byte `0D 0A` trong UTF-8.

Hai chuỗi có thể được trình soạn thảo hiển thị gần giống nhau nhưng không có cùng byte. Các phép thay đổi sau cũng có tác động:

- Đổi LF sang CRLF khi gửi file từ Windows sang môi trường khác.
- Bỏ dấu xuống dòng cuối file hoặc thêm một newline cuối thông điệp.
- Thêm khoảng trắng cuối dòng, tab hoặc ký tự không ngắt dòng `U+00A0`.
- Gọi `.strip()`, `.trim()`, `.stripIndent()`, `.indent()` hoặc `.lines()` rồi ghép lại.
- Dùng `System.lineSeparator()` để tạo payload ở hai hệ điều hành.
- Chuyển text block sang chuỗi và thay đổi quy tắc thụt lề/line terminator.

**Đối với dữ liệu cần ký, một whitespace cũng có thể thay đổi chữ ký.**

Text block là cú pháp tiện dụng trong Java 15 (đã trở thành tính năng chính thức), nhưng **không có nghĩa nó giữ nguyên nguyên văn từng byte từ file nguồn**: Java xử lý incidental indentation và line terminators của text block theo ngữ nghĩa ngôn ngữ. Nếu dùng text block để tạo payload ký, cần kiểm tra **chính xác chuỗi tạo ra** và chuyển sang byte bằng charset rõ ràng.

Không chuẩn hóa CRLF thành LF chỉ ở bên xác minh khi bên ký thực tế đã ký byte CRLF nguyên gốc.

## 5. Định dạng dữ liệu có cấu trúc: JSON, XML, form và header

**Nội dung logic tương đương không đồng nghĩa byte biểu diễn bằng nhau.** Ví dụ:

```json
{"name":"Lan","count":1}
```

và:

```json
{"count":1,"name":"Lan"}
```

đều có thể đại diện cho một đối tượng JSON cùng các trường/giá trị, nhưng dãy byte UTF-8 khác nhau. Một chữ ký tạo trên JSON đầu tiên **không xác minh được** nếu bên nhận tự serialize thành JSON thứ hai trước khi kiểm tra.

Các nguồn biến đổi thường gặp:

- **Thứ tự thuộc tính JSON**, khoảng trắng ngoài string, dấu xuống dòng và indentation.
- **Cách escape string JSON**: một ký tự có thể xuất hiện trực tiếp hoặc qua escape Unicode, khiến **byte JSON** khác dù giá trị sau parse tương đương.
- **Cách biểu diễn số**: `1`, `1.0`, `1e0` có thể được ứng dụng xem gần nhau nhưng là những chuỗi byte khác nhau.
- **Unicode normalization**, nếu một phía tự thực hiện mà phía kia không.
- **Thứ tự header/field**, cách encode URL/query string hoặc percent-encoding.
- **XML namespace, attribute order và whitespace**, tùy parser/serializer.
- **Định dạng ngày giờ, timezone, dấu thập phân, locale và số chữ số** nếu ứng dụng xây thông điệp dạng văn bản.

### Hai thiết kế đúng

**Thiết kế 1 — Ký trực tiếp payload gốc:** nếu giao thức quy định ký byte body HTTP nguyên gốc, hệ thống phải có cách lấy, lưu, gửi và verify **chính byte body đã ký**, không parse JSON rồi tái tạo “bản tương đương”.

**Thiết kế 2 — Ký một canonical serialization:** chọn rõ một đặc tả canonicalization và phiên bản. Với JSON, có **RFC 8785 — JSON Canonicalization Scheme (JCS)**, quy định chi tiết xử lý số, chuỗi, sắp xếp thuộc tính và mã hóa UTF-8. **Chỉ sắp xếp key bằng tay chưa đủ để trở thành JCS**; cần tuân thủ toàn bộ quy tắc, gồm ràng buộc I-JSON, xử lý Unicode không hợp lệ và serialization nguyên thủy.

**Chi tiết quan trọng của RFC 8785:** JCS **không thực hiện Unicode normalization**; dữ liệu Unicode trong các JSON string phải được giữ nguyên. Vì vậy, **không được vừa tuyên bố áp dụng JCS vừa tự thêm NFC cho mọi string** nếu giao thức không định nghĩa tầng xử lý riêng như vậy. Quy tắc canonicalization phải là một hợp đồng duy nhất và có kiểm thử liên ngôn ngữ.

Nếu dùng một chuẩn chữ ký có định dạng riêng như **JWS**, phải theo đúng quy tắc signing input của chuẩn đó; không tự ý thay chữ ký lên body đã giải mã hoặc một phiên bản JSON mới serialize khi chuẩn không yêu cầu.

## 6. Ví dụ Java 17+ chạy được: nhìn thấy sai khác khi xác minh Ed25519

Chương trình sau tạo khóa Ed25519 và kiểm tra chữ ký với nhiều biểu diễn của cùng nội dung. Một phần thông điệp được định nghĩa thành **NFC + LF + UTF-8** theo *giao thức ví dụ*, để chứng minh:

1. Chuỗi NFC và NFD không bằng nhau ở mức `String.equals` và UTF-8 bytes.
2. NFD đưa nguyên vào `verify` sẽ thất bại so với chữ ký NFC.
3. Chuẩn hóa NFD sang NFC **đúng theo hợp đồng ví dụ** làm hai bên tạo cùng byte.
4. Thay LF bằng CRLF hoặc UTF-8 bằng UTF-16LE làm chữ ký không hợp lệ.
5. Đổi thứ tự trường JSON làm chữ ký trên **raw JSON bytes** không hợp lệ.
6. Chuỗi có surrogate không ghép cặp được **strict UTF-8 encoder** từ chối, tránh âm thầm thay dữ liệu.

**Chương trình minh họa một hợp đồng do ví dụ đặt ra, không phải khuyến nghị mọi giao thức chữ ký đều phải normalize NFC.** Với byte gốc, phải ký và verify byte gốc theo đúng giao thức đã được thiết kế.

Lưu file `SignedTextRepresentationDemo.java` theo UTF-8:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.text.Normalizer;
import java.util.Arrays;

public class SignedTextRepresentationDemo {
    private static byte[] sign(PrivateKey key, byte[] message)
            throws Exception {
        Signature signature = Signature.getInstance("Ed25519");
        signature.initSign(key);
        signature.update(message);
        return signature.sign();
    }

    private static boolean verify(PublicKey key, byte[] message, byte[] signed)
            throws Exception {
        Signature signature = Signature.getInstance("Ed25519");
        signature.initVerify(key);
        signature.update(message);
        return signature.verify(signed);
    }

    public static void main(String[] args) throws Exception {
        String nfc = "Caf\u00e9";
        String nfd = "Cafe\u0301";

        // Hợp đồng demo: NFC, kết thúc LF, encode UTF-8.
        String canonicalText = Normalizer.normalize(
                nfc, Normalizer.Form.NFC) + "\n";
        byte[] message = canonicalText.getBytes(StandardCharsets.UTF_8);

        KeyPair pair = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        byte[] signed = sign(pair.getPrivate(), message);

        System.out.println("textEquals=" + nfc.equals(nfd));
        System.out.println("nfcEquals=" + Normalizer.normalize(
                nfc, Normalizer.Form.NFC).equals(
                Normalizer.normalize(nfd, Normalizer.Form.NFC)));
        System.out.println("sameUtf8Bytes=" + Arrays.equals(
                nfc.getBytes(StandardCharsets.UTF_8),
                nfd.getBytes(StandardCharsets.UTF_8)));

        System.out.println("original=" +
                verify(pair.getPublic(), message, signed));
        System.out.println("rawNfd=" + verify(pair.getPublic(),
                (nfd + "\n").getBytes(StandardCharsets.UTF_8), signed));
        System.out.println("normalizedNfd=" + verify(pair.getPublic(),
                (Normalizer.normalize(nfd, Normalizer.Form.NFC) + "\n")
                        .getBytes(StandardCharsets.UTF_8), signed));
        System.out.println("crlf=" + verify(pair.getPublic(),
                (nfc + "\r\n").getBytes(StandardCharsets.UTF_8), signed));
        System.out.println("utf16le=" + verify(pair.getPublic(),
                (nfc + "\n").getBytes(StandardCharsets.UTF_16LE), signed));
        System.out.println("signatureBytes=" + signed.length);

        // Ở đây JSON được ký trên RAW UTF-8; không dùng JCS.
        String jsonA = "{\"name\":\"Lan\",\"count\":1}";
        String jsonB = "{\"count\":1,\"name\":\"Lan\"}";
        byte[] jsonSignature = sign(pair.getPrivate(),
                jsonA.getBytes(StandardCharsets.UTF_8));
        System.out.println("jsonOriginal=" + verify(pair.getPublic(),
                jsonA.getBytes(StandardCharsets.UTF_8), jsonSignature));
        System.out.println("jsonReordered=" + verify(pair.getPublic(),
                jsonB.getBytes(StandardCharsets.UTF_8), jsonSignature));

        // Strict encoder từ chối surrogate UTF-16 bị cắt đôi.
        String malformed = new String(new char[]{(char) 0xD800});
        try {
            StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(malformed));
            System.out.println("malformedRejected=false");
        } catch (CharacterCodingException e) {
            System.out.println("malformedRejected=true");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SignedTextRepresentationDemo.java
java SignedTextRepresentationDemo
```

**Đầu ra đúng, đã kiểm chứng trên JDK 24 (có provider Ed25519):**

```text
textEquals=false
nfcEquals=true
sameUtf8Bytes=false
original=true
rawNfd=false
normalizedNfd=true
crlf=false
utf16le=false
signatureBytes=64
jsonOriginal=true
jsonReordered=false
malformedRejected=true
```

`signatureBytes=64` là độ dài chữ ký Ed25519 theo RFC 8032. Cặp khóa ngẫu nhiên thay đổi mỗi lần chạy, nhưng kết quả logic nêu trên không phụ thuộc giá trị private key trên JDK hỗ trợ Ed25519 và tuân thủ đặc tả.

### Vì sao normalizedNfd=true?

Bên ký đưa vào `canonicalText` được tạo từ NFC + `"\n"` + UTF-8. Khi xác minh, bên nhận **cũng áp dụng đúng phép chuyển đổi đó** cho văn bản NFD nên byte cuối cùng trùng với byte đã ký. Không phải thuật toán Ed25519 tự bỏ qua khác biệt Unicode.

### Vì sao jsonReordered=false?

Hai chuỗi JSON trong demo không cùng byte, và chúng được ký **trên biểu diễn raw**. Nếu cả hai bên thống nhất áp dụng **đúng RFC 8785** (hoặc một định dạng chuẩn tắc khác được đặc tả) trước khi ký, kết quả có thể trùng nhau theo quy tắc canonicalization. Không có triển khai JCS trong chương trình vì sẽ cần một canonicalizer đầy đủ; không nhầm `jsonB` tự động đã được canonicalize.

## 7. Mã hóa lỗi: tránh thay thế ký tự âm thầm

Trong Java, `String` có thể chứa **surrogate UTF-16 không ghép cặp**. Một dãy byte đến từ network cũng có thể chứa UTF-8 không hợp lệ. Đây là những trường hợp cần chú ý khi xác minh chữ ký, nhất là khi một phía **decode rồi encode lại** dữ liệu.

Các API tiện dụng:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String text = new String(bytes, StandardCharsets.UTF_8);
```

hai dòng trên là **mẫu riêng** (không thể đặt nối tiếp trong cùng scope vì trùng tên nếu dùng nguyên xi). Với dữ liệu malformed, các API tiện dụng tương ứng **có thể thay thế dữ liệu lỗi bằng ký tự/byte thay thế mặc định**. Điều này khiến byte mới không còn giống payload ban đầu. Nếu mục tiêu là **bảo toàn byte chính xác**, hãy ưu tiên không decode/re-encode trước khi verify.

Khi hợp đồng yêu cầu dữ liệu văn bản Unicode hợp lệ và phải **từ chối đầu vào lỗi**, dùng `CharsetDecoder`/`CharsetEncoder` với `CodingErrorAction.REPORT`.

Mẫu kiểm tra nghiêm ngặt khi **decode** (đoạn minh họa, cần biến `byte[] raw`):

```java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

String decoded = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(raw))
        .toString();
```

Mẫu kiểm tra khi **encode** (đoạn minh họa, cần biến `String text`):

```java
import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var encoded = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .encode(CharBuffer.wrap(text));
```

Hai mẫu có thể ném `CharacterCodingException` và cần bắt hoặc khai báo khi đặt trong method. Đặc biệt, UTF-8 hợp lệ có thể chứa ký tự thay thế `U+FFFD` **một cách hợp lệ**; không được coi **mọi** `U+FFFD` là bằng chứng dữ liệu lỗi nếu chưa biết bytes gốc. Phát hiện malformed phải thực hiện tại **lúc decode/encode**, không dựa trên đoán ký tự sau đó.

## 8. Biểu diễn số, thời gian và locale

Nếu thông điệp được dựng từ dữ liệu nghiệp vụ, các giá trị ngoài text thuần cũng phải có định dạng **không mơ hồ**.

**Số:** `String.format("%f", amount)` có thể phản ánh locale mặc định; thập phân có thể hiển thị với dấu chấm hoặc dấu phẩy tùy ngôn ngữ. Nếu tự thiết kế giao thức, nêu rõ cách biểu diễn số, dấu thập phân, số chữ số, làm tròn và tránh phụ thuộc locale mặc định.

**Thời gian:** hai thời điểm tương đương có thể biểu diễn khác nhau bởi timezone/offset, precision, dấu `Z` hoặc độ dài phần giây. Hợp đồng cần quy định định dạng, timezone và đơn vị thời gian, ví dụ dạng ISO-8601 cụ thể.

**Map/collection:** `Map.toString()` không phải định dạng canonical serialization. Thứ tự phần tử có thể thay đổi theo implementation và dữ liệu; không ký chuỗi debug `toString()` rồi kỳ vọng có thể xác minh liên hệ thống.

**Text block và String.formatted:** chúng chỉ định dạng chuỗi theo ngữ nghĩa Java; `String.formatted(...)` không biến kết quả thành payload canonical. Cần một hàm serialize được đặc tả và kiểm thử.

Một cách làm tốt là chuẩn hóa dữ liệu **một lần trong tầng serialization có kiểm soát**, không để mỗi nơi tạo thông điệp có những quy tắc ngầm riêng.

## 9. Thiết kế một hợp đồng biểu diễn thông điệp

Trước khi phát hành API ký/xác minh, mô tả chính xác những thông tin sau:

| Thành phần hợp đồng | Ví dụ câu trả lời cần xác định |
| --- | --- |
| Payload nào được ký? | HTTP body raw, bytes của một file hay canonical JSON? |
| Loại dữ liệu | Binary thuần, UTF-8 text hay object cấu trúc? |
| Charset | UTF-8 có/không BOM, hoặc charset cụ thể khác |
| Unicode | Giữ nguyên, NFC, NFD hay quy tắc đặc thù? |
| Newline | LF, CRLF, không có newline cuối hay luôn có? |
| Whitespace | Giữ nguyên hay loại bỏ theo quy tắc đã viết rõ? |
| Serialization | Tên trường, thứ tự, escaping, số, null, mảng, dữ liệu lồng nhau |
| Version | Có version để tránh thay đổi ngầm khi nâng cấp không? |
| Thuật toán | Ed25519/Ed448 và tham số nào? |
| Key identity | Public key đáng tin được lấy từ kho/certificate/registry nào? |
| Signature encoding | Raw bytes, Base64, base64url hay format giao thức khác? |
| Domain/context binding | Có ký cả loại lệnh, version, ID, timestamp/nonce nếu cần không? |
| Replay prevention | Có số thứ tự/nonce và cơ chế lưu dấu đã sử dụng không? |

Ví dụ *giao thức tự thiết kế* muốn ký nội dung text dạng bản ghi có thể quy định:

```text
version = 1
type = "payment"
charset = UTF-8 without BOM
unicode = NFC for text fields
line-ending = LF
field-order = fixed schema order
number = ASCII decimal with fixed scale
signature-alg = Ed25519
```

Đây chỉ là **một ví dụ hợp đồng**, chưa phải đặc tả hoàn chỉnh để đưa trực tiếp vào sản phẩm: còn phải định nghĩa escaping và dấu phân cách để tránh nhập nhằng, encoding của null/binary, giới hạn kích thước, canonicalization cụ thể và test vectors. Trong ứng dụng thật, ưu tiên **một chuẩn đã được đặc tả và có thư viện duy trì** hơn là tự sáng tạo chuẩn chữ ký.

### Quy trình an toàn khi nhận dữ liệu

1. Xác định **giao thức và phiên bản** trước khi xử lý. Chọn thuật toán/chính sách được phép, không cho payload tùy ý ép downgrade.
2. Lấy **payload bytes gốc** nếu hợp đồng ký trên raw body; tránh mất chúng trong bước parse.
3. Nếu hợp đồng ký canonical representation, parse/validate theo quy tắc rõ ràng và **canonicalize bằng cùng thuật toán** mà bên ký dùng.
4. Xác nhận **public key đáng tin**, không lấy vô điều kiện public key do đối tượng cần xác minh cung cấp.
5. Gọi `Signature.getInstance("Ed25519")`, `initVerify(publicKey)`, `update(exactBytes)`, `verify(signatureBytes)`.
6. Chỉ xử lý hành động nhạy cảm khi verify thành công; phân biệt kết quả `false` với lỗi provider/key/encoding.
7. Nếu nghiệp vụ yêu cầu, kiểm tra **nonce/timestamp/sequence/context** đã nằm trong dữ liệu ký và thực hiện chống replay.

Không log private key hay toàn bộ thông điệp nhạy cảm. Khi debug mismatch, có thể so sánh **length, hash/checksum chẩn đoán của payload, charset policy, code point và biểu diễn hex của vài byte không nhạy cảm** ở hai đầu. Tránh làm lộ dữ liệu cá nhân hoặc bí mật qua log.

## 10. Các lỗi thường gặp

| Cách nghĩ sai | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Hai chuỗi hiển thị như nhau thì chữ ký phải verify được | NFC/NFD có thể tạo byte khác nhau | Quy định rõ giữ byte gốc hay normalization |
| `Signature.update(String)` tự biết UTF-8 | API `update` nhận byte/ByteBuffer, không nhận `String` | Chuyển bằng charset explicit |
| Dùng `getBytes()` là đủ cho mọi JDK | Default charset có thể khác và là phụ thuộc ngầm | `StandardCharsets.UTF_8` |
| Bên ký dùng LF, bên nhận đổi CRLF không ảnh hưởng | Newline là byte được ký | Giữ nguyên hoặc chuẩn hóa theo hợp đồng trước khi ký |
| Chỉ cần parse JSON rồi serialize lại | Thứ tự/whitespace/escaping/số có thể đổi bytes | Ký raw bytes hoặc canonicalization chuẩn |
| JCS nghĩa là normalize NFC mọi chuỗi | RFC 8785 **không** Unicode-normalize string data | Tuân thủ chính xác RFC 8785 |
| Sort key JSON là đã triển khai JCS | JCS còn quy định số, chuỗi, kiểu dữ liệu và encoding | Dùng canonicalizer chuẩn, có test vector |
| Bỏ BOM/trim đến khi verify thành công | Đã đổi dữ liệu xác minh và có thể tạo chấp nhận mơ hồ | Không thử tùy tiện biến thể |
| `new String(bytes, UTF_8)` bảo toàn mọi byte lỗi | Decoder tiện dụng có thể thay thế malformed | Giữ bytes hoặc dùng strict decoder |
| `text.getBytes(UTF_8)` luôn báo lỗi khi text UTF-16 malformed | Overload tiện dụng thường dùng replacement | Dùng `CharsetEncoder` + `CodingErrorAction.REPORT` |
| `verify=true` xác định người gửi dù key do payload cung cấp | Key có thể thuộc kẻ tấn công | Xác thực nguồn public key và danh tính |
| Chỉ cần ký payload, không cần định danh ngữ cảnh | Chữ ký có thể bị dùng sai loại thao tác hoặc replay | Ký kèm context/version/nonce nếu giao thức yêu cầu |

## 11. Bài tập tự kiểm tra

**Bài 1.** A ký `"Caf\u00e9"` ở dạng NFC với UTF-8. B nhận `"Cafe\u0301"` rồi mã hóa UTF-8 nguyên trạng. Có thể mặc định `verify=true` không?

**Bài 2.** A ký raw HTTP body `{"id":7,"ok":true}`. B parse JSON rồi serialize thành `{"ok":true,"id":7}` trước khi verify. Vì sao có thể thất bại?

**Bài 3.** Giao thức ghi rõ “UTF-8 không BOM, NFC cho trường `name`, newline LF”. Tầng serialization đã áp dụng đúng các quy tắc này trước khi ký. Khi nhận, B nên làm gì?

**Bài 4.** Một hệ thống công bố sử dụng **RFC 8785 JCS**. Nhà phát triển tự thêm bước `Normalizer.normalize(value, NFC)` vào mọi JSON string trước khi ký nhưng không có quy định bổ sung. Cách đó có tuân thủ nguyên văn JCS không?

**Bài 5.** File text có CRLF và ký byte gốc. Một bộ đọc file tự động chuyển CRLF thành LF khi decode. Có thể dùng kết quả chuyển đổi để xác minh chữ ký gốc không?

**Bài 6.** Cùng một string Java chứa một surrogate cao không có surrogate thấp. Sử dụng `getBytes(StandardCharsets.UTF_8)` có bảo đảm báo lỗi để ứng dụng từ chối dữ liệu không?

**Đáp án:**

1. Không. Dạng composed và decomposed có byte UTF-8 khác nhau; chỉ khi hợp đồng có normalization chung và cả hai áp dụng đúng bước đó mới có thể tạo cùng byte.
2. Thứ tự thuộc tính đã đổi khiến **raw JSON bytes khác nhau**. Với raw-body signatures, B phải verify byte body gốc; nếu dùng canonical JSON thì phải chọn và triển khai cùng chuẩn canonicalization ở cả hai phía.
3. Dùng đúng hàm tạo canonical representation theo hợp đồng, kiểm tra dữ liệu hợp lệ và encode UTF-8 không BOM; sau đó verify **chính byte kết quả** với public key đáng tin.
4. Không. RFC 8785 yêu cầu **giữ nguyên Unicode string data**, không thêm Unicode normalization tự động. Nếu giao thức định nghĩa tiền xử lý bổ sung thì phải gọi tên và mô tả riêng bước đó.
5. Không khi chữ ký trên **raw bytes** có CRLF. Chuyển thành LF đã sửa payload.
6. Không. Overload tiện dụng có thể thay dữ liệu malformed; dùng strict `CharsetEncoder` với `REPORT` nếu hợp đồng yêu cầu từ chối input UTF-16 không hợp lệ.

## Tài liệu hiện hành

- [Oracle Java SE 26 — Signature](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html): `update(byte[])`, `initVerify(...)`, `verify(...)` và hợp đồng trạng thái.
- [Oracle Java SE 26 — String](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html): `getBytes(Charset)` và hành vi thay thế dữ liệu malformed.
- [Oracle Java SE 26 — Normalizer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): Unicode NFC, NFD, NFKC và NFKD.
- [Oracle Java SE 26 — StandardCharsets](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): charset được bảo đảm hỗ trợ, gồm UTF-8.
- [Oracle Java SE 26 — CharsetEncoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetEncoder.html): cách cấu hình `CodingErrorAction.REPORT`.
- [OpenJDK — JEP 339: Edwards-Curve Digital Signature Algorithm](https://openjdk.org/jeps/339): EdDSA/Ed25519/Ed448 được bổ sung ở Java 15.
- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400): lý do không phụ thuộc default charset giữa các bản Java.
- [RFC 8785 — JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785): canonical JSON, số, chuỗi, thứ tự thuộc tính, UTF-8 và yêu cầu **không Unicode-normalize**.
- [RFC 8032 — EdDSA](https://www.rfc-editor.org/rfc/rfc8032): Ed25519 và định dạng chữ ký 64 byte.