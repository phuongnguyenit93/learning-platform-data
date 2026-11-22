# Kiểm thử tiếng Việt, ký tự bổ sung và dữ liệu qua nhiều hệ điều hành trong Java

## 1. Mục tiêu và phạm vi

Một chuỗi tiếng Việt có thể nhìn đúng trên máy lập trình viên nhưng bị lỗi khi đọc từ file, chuyển qua Windows/Linux/macOS hoặc hiển thị trong terminal. Các nguyên nhân thường gặp: **không thống nhất charset**, **cắt giữa surrogate pair**, **nhầm số byte với số ký tự**, **dạng NFC/NFD khác nhau**, **line ending CRLF/LF**, **UTF-8 BOM**, **dữ liệu byte lỗi**, hoặc **đường dẫn phụ thuộc hệ điều hành**.

Bài này xây dựng một bộ kiểm thử hiện hành cho chủ đề **Bảng mã**, sử dụng Java 17+ để chứng minh từng hiện tượng với chương trình độc lập. Java 7 đã cung cấp `java.nio.file` và `StandardCharsets.UTF_8`; các API dùng trong ví dụ như `Files.readString/writeString` (Java 11+) và `String.codePoints()` (Java 8+) được ghi rõ mốc. Kiến thức xử lý Unicode, charset và portability vẫn áp dụng với Java hiện đại.

Sau bài này, bạn sẽ:

1. Kiểm tra round-trip **String → UTF-8 bytes → file → String** và so sánh cả văn bản lẫn byte.
2. Phân biệt **UTF-8 byte**, **UTF-16 code unit (`char`)**, **Unicode code point** và **grapheme cluster**.
3. Xử lý ký tự bổ sung như emoji, tránh cắt giữa high/low surrogate.
4. Kiểm tra tiếng Việt ở dạng Unicode **NFC/NFD** và hiểu khi nào chuẩn hóa là phù hợp.
5. Phát hiện **UTF-8 malformed**, thử decoder REPORT/REPLACE, và mã hóa String có surrogate không hợp lệ.
6. Kiểm tra **CRLF/LF**, **BOM** và sự khác nhau giữa văn bản nhìn giống nhau với byte giống nhau.
7. Viết thao tác file bằng `Path.resolve` và charset tường minh, thay vì separator hoặc default charset.
8. Lập ma trận kiểm thử **Windows, Linux, macOS** mà không lẫn kết quả chạy trên một máy với bằng chứng đã chạy mọi OS.

**Phạm vi kiểm chứng:** Tám chương trình minh họa được biên dịch bằng `javac -encoding UTF-8 --release 17` và chạy với stdout khớp kết quả nêu trong bài trên môi trường kiểm thử. Chúng được thiết kế có thể chạy lại trên nhiều OS; chưa tuyên bố chúng đã được chạy trên cả Windows, Linux và macOS. Muốn xác nhận đa hệ điều hành, cần chạy CI trên các runner thật.

## 2. Tầng ký tự và byte không phải một

~~~text
Dữ liệu Unicode logic
        |
        v
java.lang.String (UTF-16 code units trong API)
        |
        | Mã hóa bằng charset rõ ràng
        v
UTF-8 bytes -> file / network / queue
        |
        | Giải mã bằng cùng charset
        v
java.lang.String ở nơi nhận
        |
        | Nếu hợp đồng yêu cầu: normalize NFC
        v
So sánh, lưu trữ, tìm kiếm, hiển thị
~~~

**Ba loại kiểm tra cần tách biệt:**

- **String equality:** văn bản ban đầu và đọc lại có `equals()` không?
- **Byte equality:** các byte được lưu/truyền có đúng quy định, bao gồm BOM và newline, không?
- **Canonical equivalence:** hai chuỗi Unicode trông tương đương nhưng khác code points có cần được normalize trước khi so sánh không?

Một font thiếu emoji không khiến file UTF-8 tự biến thành sai. Ngược lại, hai file nhìn giống nhau có thể khác byte do NFC/NFD hoặc CRLF/LF.

| Khái niệm | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- |
| UTF-8 byte | Đơn vị octet của file/giao thức, một code point có thể cần 1–4 byte | `text.getBytes(UTF_8).length` |
| UTF-16 code unit | Đơn vị `char` 16-bit trong API của `String` | `text.length()` |
| Unicode code point | Giá trị như `U+0111` hoặc `U+1F680` | `text.codePointCount(0,text.length())` |
| Grapheme cluster | “Ký tự” người dùng nhìn thấy, đôi khi gồm nhiều code points | Cần API phân đoạn grapheme |
| Charset | Quy tắc mã hóa và giải mã byte ↔ ký tự | `StandardCharsets.UTF_8` |
| Normalization | Canonical/compatibility transform, ví dụ NFC/NFD | `java.text.Normalizer` |
| Line ending | Ký tự phân dòng trong dữ liệu | `\n`, `\r\n`, `\r` |
| UTF-8 BOM | Byte signature đầu file (nếu định dạng có) | `EF BB BF` → có thể hiện U+FEFF |

Bộ fixture không nên chỉ có ASCII. Với tiếng Việt, dùng các mẫu có `ă â ê ô ơ ư đ`, dấu sắc/huyền/hỏi/ngã/nặng, chữ hoa, biểu diễn tổ hợp dấu, cùng một vài emoji.

## 3. Charset tường minh: nguyên tắc đầu tiên

Với Java 17+:

~~~java
Files.writeString(file, text, StandardCharsets.UTF_8);
String restored = Files.readString(file, StandardCharsets.UTF_8);
~~~

Đây là đoạn trong phương thức với `file` kiểu `Path`, `text` kiểu `String` và các import phù hợp.

- `Files.writeString/readString` dùng charset đã chỉ rõ; không dựa vào encoding mặc định của máy.
- Overload không có tham số charset của **riêng hai API này** cũng dùng UTF-8 theo hợp đồng từ Java 11. Việc ghi tường minh vẫn giúp code rõ ràng.
- Từ Java 18, JEP 400 áp dụng UTF-8 mặc định cho các Java SE API thuộc phạm vi thay đổi, nhưng vẫn có cấu hình tương thích và những ngoại lệ được tài liệu hóa.
- Với JDK 17 trở xuống, default charset có thể phụ thuộc OS/locale. Không giả định một file bên ngoài tự động trở thành UTF-8 chỉ vì môi trường chạy JDK mới.
- Charset file **khác** encoding đọc tệp nguồn `.java` lúc biên dịch và khác cả encoding/font hiển thị terminal.

Lưu source file chứa tiếng Việt/emoji bằng UTF-8, biên dịch bằng tùy chọn `javac -encoding UTF-8`. Nếu giao thức cố định UTF-8, khai báo charset ở mỗi ranh giới I/O. Chỉ dùng charset khác khi hợp đồng dữ liệu bên ngoài yêu cầu thật sự.

Nguồn: [Files Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html), [StandardCharsets Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html), [JEP 400](https://openjdk.org/jeps/400).

## 4. Ví dụ 1: round-trip tiếng Việt qua file thực

Tạo file `VietnameseRoundTripDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class VietnameseRoundTripDemo {
    public static void main(String[] args) throws Exception {
        String original =
                "Tiếng Việt: Trường, Nguyễn, ă â ê ô ơ ư đ, 🚀";
        Path file = Files.createTempFile("unicode-roundtrip-", ".txt");

        try {
            Files.writeString(file, original, StandardCharsets.UTF_8);
            String restored = Files.readString(file, StandardCharsets.UTF_8);
            byte[] disk = Files.readAllBytes(file);

            System.out.println("sameText=" + original.equals(restored));
            System.out.println("sameBytes=" + Arrays.equals(disk,
                    original.getBytes(StandardCharsets.UTF_8)));
            System.out.println("containsVietnamese=" +
                    restored.contains("Nguyễn"));
            System.out.println("containsRocket=" +
                    restored.contains("🚀"));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 VietnameseRoundTripDemo.java
java VietnameseRoundTripDemo
~~~

Stdout đã kiểm chứng:

~~~text
sameText=true
sameBytes=true
containsVietnamese=true
containsRocket=true
~~~

Giải thích:

1. File tạm được tạo bằng API, không hardcode đường dẫn cho Windows hay Unix.
2. `writeString` chuyển String thành UTF-8; `readString` giải mã bằng UTF-8.
3. `equals` so sánh toàn bộ nội dung thực, không chỉ kiểm tra có in được dấu tiếng Việt trên terminal.
4. `Files.readAllBytes` lấy các byte thật trong file; `Arrays.equals` đối chiếu với byte kỳ vọng từ `original.getBytes(UTF_8)`.
5. Hai phép `contains` xác nhận test vector thực sự có tiếng Việt và ký tự ngoài BMP.
6. `finally` dọn file; không in đường dẫn tạm ngẫu nhiên vào stdout vì nó thay đổi theo máy.

**Giới hạn:** Round-trip giữa encoder/decoder dùng cùng một quy trình vẫn có thể bỏ sót một lỗi cả hai cùng mắc. Với định dạng cần chính xác byte, thêm **fixture byte chuẩn** được xác nhận độc lập (ví dụ expected hex hoặc một file đã kiểm tra checksum), không chỉ dựa vào `writeString` rồi `readString` của cùng thư viện.

### 4.1. Bộ dữ liệu thử nên có

| Loại | Ví dụ | Tác dụng |
| --- | --- | --- |
| ASCII | `Hello 123` | Đường cơ sở |
| Tiếng Việt NFC | `Tiếng Việt, Trường, Nguyễn` | Chữ có dấu |
| Hoa/thường | `ĐẮK LẮK / đắk lắk` | Dấu thanh và Đ |
| Dấu tổ hợp | `a + U+0306 + U+0301` | NFD/canonical equivalence |
| Ký tự bổ sung | `🚀` U+1F680 | Surrogate pair và 4 byte UTF-8 |
| Emoji ghép ZWJ | Một emoji nhiều code points | Grapheme khác code point |
| Chuỗi rỗng | `""` | Zero-length |
| Line endings | LF, CRLF, CR | Byte khác dù dòng logic như nhau |
| Byte sai | `C3 28` | Decode REPORT/REPLACE |
| UTF-8 BOM | `EF BB BF` | Chính sách U+FEFF |
| Surrogate đơn lẻ | High surrogate không có low surrogate | Encode malformed |

Nếu file được đọc từ đối tác, nên thêm fixture từ byte thực do đối tác cung cấp và lưu format/charset theo hợp đồng.

## 5. Ví dụ 2: ký tự bổ sung không phải một `char`

Chuỗi Java được đánh chỉ số bằng UTF-16 code units. Emoji `🚀` là **một code point** U+1F680, nhưng cần **hai code units**: high surrogate và low surrogate.

Với `"A🚀đ"`:

| Phần | UTF-16 units | Code points | UTF-8 bytes |
| --- | ---: | ---: | ---: |
| `A` | 1 | 1 | 1 |
| `🚀` | 2 | 1 | 4 |
| `đ` | 1 | 1 | 2 |
| **Tổng** | **4** | **3** | **7** |

Tạo `SupplementaryCodePointsDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.stream.Collectors;

public class SupplementaryCodePointsDemo {
    public static void main(String[] args) {
        String text = "A🚀đ";

        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" +
                text.codePointCount(0, text.length()));
        System.out.println("utf8Bytes=" +
                text.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("highSurrogate=" +
                Character.isHighSurrogate(text.charAt(1)));
        System.out.println("lowSurrogate=" +
                Character.isLowSurrogate(text.charAt(2)));
        System.out.println("rocketCodePoint=" +
                String.format("U+%04X", text.codePointAt(1)));
        System.out.println("afterSecondCp=" +
                text.offsetByCodePoints(0, 2));
        System.out.println("stream=" + text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(",")));
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 SupplementaryCodePointsDemo.java
java SupplementaryCodePointsDemo
~~~

Stdout:

~~~text
utf16Units=4
codePoints=3
utf8Bytes=7
highSurrogate=true
lowSurrogate=true
rocketCodePoint=U+1F680
afterSecondCp=3
stream=U+0041,U+1F680,U+0111
~~~

- `charAt(1)` và `charAt(2)` là hai nửa surrogate, không phải hai emoji.
- `codePointAt(1)` trả đầy đủ U+1F680.
- Hai code points đầu tiên chiếm ba UTF-16 units, nên `offsetByCodePoints(0,2)==3`.
- `String.codePoints()` trả `IntStream` từ Java 8.
- Code point **chưa phải grapheme cluster**: chữ có dấu dạng tổ hợp và emoji ZWJ có thể gồm nhiều code points nhưng một ký tự người dùng cảm nhận.

### 5.1. Tránh cắt giữa surrogate pair

Đoạn **có nguy cơ làm hỏng Unicode**:

~~~java
String text = "A🚀đ";
String broken = text.substring(1, 2); // Chỉ một high surrogate.
~~~

Đây là đoạn trong phương thức, không phải file độc lập. Cách lấy đúng code point thứ hai:

~~~java
int from = text.offsetByCodePoints(0, 1);
int to = text.offsetByCodePoints(0, 2);
String rocket = text.substring(from, to);
~~~

Phải kiểm tra số code points/biên nếu offset đến từ dữ liệu bên ngoài. Khi chia chuỗi dài để lưu/truyền, cũng tránh cắt giữa surrogate pair. Nếu giới hạn UI tính theo số **grapheme** hiển thị, dùng công cụ phân đoạn Unicode thích hợp thay vì chỉ `length()`/`codePointCount()`.

Nguồn: [String Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html), [Character Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.html).

## 6. Ví dụ 3: chữ Việt NFC/NFD và `String.equals()`

Chữ Việt `ắ` có thể là:

- Dạng ghép **NFC**: một code point `U+1EAF`.
- Dạng tách **NFD**: `a` U+0061 + dấu breve U+0306 + dấu sắc U+0301.

Hai chuỗi có thể hiển thị giống nhau, nhưng **code point và byte UTF-8 khác nhau**. `String.equals()` không tự thực hiện Unicode normalization. UTF-8 encoder cũng không normalize văn bản.

Tạo `VietnameseNormalizationDemo.java`:

~~~java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class VietnameseNormalizationDemo {
    public static void main(String[] args) {
        String nfc = "\u1EAF";
        String nfd = "a\u0306\u0301";

        System.out.println("visuallySameButEquals=" + nfc.equals(nfd));
        System.out.println("nfcCodePoints=" +
                nfc.codePointCount(0, nfc.length()));
        System.out.println("nfdCodePoints=" +
                nfd.codePointCount(0, nfd.length()));
        System.out.println("sameAfterNfc=" +
                Normalizer.normalize(nfd, Normalizer.Form.NFC).equals(nfc));
        System.out.println("sameAfterNfd=" +
                Normalizer.normalize(nfc, Normalizer.Form.NFD).equals(nfd));
        System.out.println("rawBytesEqual=" + Arrays.equals(
                nfc.getBytes(StandardCharsets.UTF_8),
                nfd.getBytes(StandardCharsets.UTF_8)));
        System.out.println("normalizedBytesEqual=" + Arrays.equals(
                Normalizer.normalize(nfc, Normalizer.Form.NFC)
                        .getBytes(StandardCharsets.UTF_8),
                Normalizer.normalize(nfd, Normalizer.Form.NFC)
                        .getBytes(StandardCharsets.UTF_8)));
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 VietnameseNormalizationDemo.java
java VietnameseNormalizationDemo
~~~

Stdout:

~~~text
visuallySameButEquals=false
nfcCodePoints=1
nfdCodePoints=3
sameAfterNfc=true
sameAfterNfd=true
rawBytesEqual=false
normalizedBytesEqual=true
~~~

**Chọn chính sách rõ ràng:**

1. Nếu ứng dụng cần tìm kiếm/so sánh theo **canonical equivalence**, normalize NFC ở các ranh giới được quy định và áp dụng nhất quán cho cả hai phía.
2. Nếu cần lưu byte gốc, tính checksum hoặc chữ ký số, **không normalize ngầm** rồi tuyên bố dữ liệu nguyên vẹn.
3. Không tự thay NFC bằng NFKC/NFKD: compatibility normalization có thể bỏ những phân biệt về ký tự/format mà nghiệp vụ cần giữ.
4. Không tự gán quy tắc normalization cho **nội dung file** dựa trên OS. Có thể có quy tắc riêng cho **tên file** của filesystem, nhưng nội dung file là một đường dữ liệu khác.

Nguồn: [Normalizer Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html) và [Unicode normalization FAQ](https://www.unicode.org/faq/normalization.html).

## 7. Ví dụ 4: kiểm thử line endings CRLF và LF

Ba sequence thường gặp:

| Dạng | Ký tự | Byte UTF-8/ASCII |
| --- | --- | --- |
| LF | `\n` | `0A` |
| CRLF | `\r\n` | `0D 0A` |
| CR | `\r` | `0D` |

Một file LF và một file CRLF có thể nhìn như cùng hai dòng nhưng **byte và hash khác nhau**.

Tạo `LineEndingRoundTripDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class LineEndingRoundTripDemo {
    public static void main(String[] args) throws Exception {
        String lf = "dong1\ndong2\n";
        String crlf = "dong1\r\ndong2\r\n";
        Path file = Files.createTempFile("line-endings-", ".txt");

        try {
            Files.writeString(file, crlf, StandardCharsets.UTF_8);
            String restored =
                    Files.readString(file, StandardCharsets.UTF_8);

            System.out.println("exactCrlf=" + restored.equals(crlf));
            System.out.println("sameAsLf=" + restored.equals(lf));
            System.out.println("crlfCount=" + restored.lines().count());
            System.out.println("lfCount=" + lf.lines().count());

            String canonical = restored
                    .replace("\r\n", "\n")
                    .replace("\r", "\n");
            System.out.println("normalizedEqualsLf=" +
                    canonical.equals(lf));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 LineEndingRoundTripDemo.java
java LineEndingRoundTripDemo
~~~

Stdout:

~~~text
exactCrlf=true
sameAsLf=false
crlfCount=2
lfCount=2
normalizedEqualsLf=true
~~~

**Điều cần nhớ:**

- `Files.readString` giữ line separators có trong file, không tự chuyển CRLF thành LF.
- `String.lines()` từ Java 11 tách thành dòng logic, không giữ separators trong các dòng, nên hai dữ liệu khác byte vẫn đếm cùng số dòng.
- Nếu định dạng yêu cầu **LF canonical**, có thể normalize có chủ đích bằng cách thay CRLF trước rồi CR, như ví dụ. Nếu định dạng yêu cầu giữ nguyên, **không normalize**.
- `System.lineSeparator()` phụ thuộc môi trường, không dùng làm quy tắc tạo LF cố định.
- Một số overload ghi *lines* dùng separator của nền tảng. Hãy đọc hợp đồng đúng method, đừng suy luận tất cả overload `Files.write` giống nhau.
- Với repository có chuyển line endings khi checkout, cần bảo vệ fixture byte; test chính xác byte không thể dựa vào việc file được editor tự sửa.

## 8. Ví dụ 5: UTF-8 không hợp lệ — REPORT hay REPLACE?

Byte `C3 28` không hợp lệ trong UTF-8: `C3` là byte mở đầu chuỗi nhiều byte, nhưng `28` không phải continuation byte hợp lệ.

Ba chính sách có thể chọn:

- `CodingErrorAction.REPORT`: báo lỗi để hệ thống xử lý/không lưu dữ liệu sai.
- `CodingErrorAction.REPLACE`: thay đoạn không hợp lệ bằng ký tự `U+FFFD`; nội dung **không còn nguyên bản**.
- `CodingErrorAction.IGNORE`: bỏ phần lỗi; chỉ dùng với hợp đồng có chủ đích vì có thể làm mất nội dung.

Tạo file `MalformedUtf8Demo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class MalformedUtf8Demo {
    public static void main(String[] args) throws Exception {
        byte[] invalid = {(byte) 0xC3, (byte) 0x28};
        Path file = Files.createTempFile("invalid-utf8-", ".txt");

        try {
            Files.write(file, invalid);

            try {
                Files.readString(file, StandardCharsets.UTF_8);
                System.out.println("readString=accepted");
            } catch (java.io.IOException ex) {
                System.out.println("readString=" +
                        ex.getClass().getSimpleName());
            }

            try {
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(invalid));
                System.out.println("strict=accepted");
            } catch (CharacterCodingException ex) {
                System.out.println("strict=" +
                        ex.getClass().getSimpleName());
            }

            String replacement = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPLACE)
                    .decode(ByteBuffer.wrap(invalid)).toString();

            System.out.println("replacementFirstCp=" +
                    String.format("U+%04X", replacement.codePointAt(0)));
            System.out.println("replacementSecond=" +
                    replacement.charAt(1));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 MalformedUtf8Demo.java
java MalformedUtf8Demo
~~~

Stdout đã kiểm chứng:

~~~text
readString=MalformedInputException
strict=MalformedInputException
replacementFirstCp=U+FFFD
replacementSecond=(
~~~

Diễn giải: `Files.write(file, invalid)` ghi **byte thô** vào file. `Files.readString(...,UTF_8)` trong trường hợp này ném một `IOException` thuộc lớp `MalformedInputException`. Decoder strict REPORT từ chối; decoder REPLACE chèn U+FFFD và tiếp tục đọc dấu `(` từ byte hợp lệ.

**Không dùng `new String(bytes,UTF_8)` làm bộ validator nghiêm ngặt** nếu hợp đồng là phát hiện mọi byte lỗi: các overload tiện ích có thể thay thế byte malformed, không ném lỗi. Nếu chất lượng dữ liệu quan trọng, ghi nhận lỗi và yêu cầu nguồn gửi đúng encoding, thay vì tự đoán một charset khác.

Nguồn: [CharsetDecoder Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html) và [CodingErrorAction Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CodingErrorAction.html).

## 9. Ví dụ 6: surrogate không ghép cặp lúc mã hóa

Một `String` có thể chứa một high surrogate không có low surrogate tương ứng, ví dụ do cắt giữa emoji theo `substring`. Khi mã hóa nghiêm ngặt thành UTF-8, chuỗi đó phải được coi là malformed Unicode input.

Tạo `UnpairedSurrogateDemo.java`:

~~~java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class UnpairedSurrogateDemo {
    public static void main(String[] args) {
        String broken = "\uD83D";

        System.out.println("units=" + broken.length());
        System.out.println("unpairedHigh=" +
                Character.isHighSurrogate(broken.charAt(0)));

        try {
            StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(broken));
            System.out.println("strict=accepted");
        } catch (CharacterCodingException ex) {
            System.out.println("strict=" +
                    ex.getClass().getSimpleName());
        }

        byte[] replaced = broken.getBytes(StandardCharsets.UTF_8);
        System.out.println("convenienceBytes=" + replaced.length);
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 UnpairedSurrogateDemo.java
java UnpairedSurrogateDemo
~~~

Stdout:

~~~text
units=1
unpairedHigh=true
strict=MalformedInputException
convenienceBytes=1
~~~

**Không nhầm** dòng `convenienceBytes=1` là dữ liệu Unicode được bảo toàn. API tiện ích đã dùng byte thay thế cho đầu vào malformed; emoji ban đầu không thể được khôi phục từ phần surrogate đơn lẻ. Nếu cần truyền dữ liệu chính xác, tránh chia chuỗi giữa surrogate pair và kiểm tra strict encoding khi thích hợp.

Nguồn: [CharsetEncoder Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetEncoder.html).

## 10. Ví dụ 7: UTF-8 BOM

BOM UTF-8 là ba byte `EF BB BF` ở đầu một số file. Khi giải mã theo API nhất định, nó có thể trở thành một ký tự `U+FEFF` **ở đầu String**, khiến so sánh nguyên văn thất bại. UTF-8 không cần BOM để xác định byte order; việc có chấp nhận hoặc bỏ BOM phụ thuộc hợp đồng định dạng/giao thức.

Tạo `Utf8BomDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8BomDemo {
    public static void main(String[] args) throws Exception {
        String content = "Xin chào";
        byte[] payload = content.getBytes(StandardCharsets.UTF_8);
        byte[] withBom = new byte[payload.length + 3];

        withBom[0] = (byte) 0xEF;
        withBom[1] = (byte) 0xBB;
        withBom[2] = (byte) 0xBF;
        System.arraycopy(payload, 0, withBom, 3, payload.length);

        Path file = Files.createTempFile("bom-", ".txt");
        try {
            Files.write(file, withBom);
            String read = Files.readString(file, StandardCharsets.UTF_8);

            System.out.println("hasLeadingBom=" +
                    (!read.isEmpty() &&
                     read.charAt(0) == '\uFEFF'));
            System.out.println("equalsWithoutHandling=" +
                    content.equals(read));

            String stripped = read.startsWith("\uFEFF")
                    ? read.substring(1) : read;
            System.out.println("equalsAfterExplicitStrip=" +
                    content.equals(stripped));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 Utf8BomDemo.java
java Utf8BomDemo
~~~

Stdout được kiểm chứng với `Files.readString(..., UTF_8)`:

~~~text
hasLeadingBom=true
equalsWithoutHandling=false
equalsAfterExplicitStrip=true
~~~

**Chính sách đúng:** Nếu format cho phép bỏ BOM, chỉ xử lý dấu hiệu **ở đầu stream**. Không xóa mọi U+FEFF trong văn bản một cách máy móc. Nếu yêu cầu bảo toàn byte hoặc có chữ ký số, không được tự thay đổi file rồi kết luận dữ liệu không đổi. Kiểm thử với parser CSV/JSON/XML thực tế: mỗi định dạng/thư viện có thể có quy tắc BOM riêng.

Nguồn: [Unicode BOM FAQ](https://www.unicode.org/faq/utf_bom.html).

## 11. Ví dụ 8: đường dẫn tệp portable với `Path.resolve`

Encoding **nội dung file** khác với cách ghi **đường dẫn**. Không nên hardcode một đường dẫn như `"data\\reports\\text.txt"` rồi giả định dấu gạch ngược là separator trên mọi OS. Với NIO, dùng `Path.resolve`:

~~~java
Path file = root.resolve("data").resolve("sample.txt");
~~~

Đây là đoạn minh họa với `root` kiểu `Path`.

Tạo `CrossPlatformPathDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class CrossPlatformPathDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("portable-text-");
        Path child = root.resolve("data");
        Path file = child.resolve("sample.txt");
        String original = "Lập trình Java - 😃";

        try {
            Files.createDirectories(child);
            Files.writeString(file, original, StandardCharsets.UTF_8);

            System.out.println("exists=" + Files.isRegularFile(file));
            System.out.println("name=" + file.getFileName());
            System.out.println("textEqual=" +
                    original.equals(Files.readString(file,
                            StandardCharsets.UTF_8)));
            System.out.println("bytesEqual=" +
                    Arrays.equals(original.getBytes(StandardCharsets.UTF_8),
                            Files.readAllBytes(file)));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(child);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 CrossPlatformPathDemo.java
java CrossPlatformPathDemo
~~~

Stdout khi filesystem cho phép tạo thư mục/file tạm:

~~~text
exists=true
name=sample.txt
textEqual=true
bytesEqual=true
~~~

Chương trình không in đường dẫn tuyệt đối ngẫu nhiên, nên kết quả kiểm tra độc lập tên thư mục tạm và separator. Cleanup xóa file trước, thư mục con sau, thư mục cha cuối.

**Giới hạn portability:** `Path.resolve` không bảo đảm mọi filesystem có cùng quy tắc về tên Unicode, reserved names, phân biệt chữ hoa-thường, normalization tên, quyền truy cập, độ dài path và dung lượng. Nếu yêu cầu lưu **tên file tiếng Việt/emoji**, cần chạy test tạo/đọc tên thật trên Windows/Linux/macOS và filesystem cụ thể. Không suy diễn hành vi của nội dung file từ cách một OS chuẩn hóa tên file.

Nguồn: [Path Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html).

## 12. Thiết kế ma trận kiểm thử cross-platform

Một kết quả thành công trên một máy chỉ chứng minh code hoạt động **trên môi trường đó**. Để tuyên bố hỗ trợ Windows/Linux/macOS, cần chạy cùng bộ test/fixture trên các runner thật.

| Bộ test | Windows | Linux | macOS | Kết quả nên so sánh |
| --- | --- | --- | --- | --- |
| UTF-8 tiếng Việt + emoji | Chạy CI | Chạy CI | Chạy CI | String và byte bằng |
| Code points/surrogate | Chạy | Chạy | Chạy | 4 UTF-16 units, 3 code points, 7 bytes |
| Unicode NFC/NFD | Chạy | Chạy | Chạy | Raw khác, NFC canonical bằng |
| UTF-8 malformed | Chạy | Chạy | Chạy | REPORT từ chối, REPLACE U+FFFD |
| Unpaired surrogate | Chạy | Chạy | Chạy | Strict encoder từ chối |
| CRLF/LF | Chạy | Chạy | Chạy | Byte nguyên văn và canonicalization đúng |
| BOM | Chạy | Chạy | Chạy | U+FEFF theo reader/format |
| Path/file tạm | Chạy | Chạy | Chạy | Tạo, đọc byte, xóa được |
| Tên file có dấu/emoji | Test filesystem thật | Test filesystem thật | Test filesystem thật | Policy xử lý thành công/lỗi |
| CLI và terminal | Các terminal mục tiêu | Locale mục tiêu | Font/terminal mục tiêu | Tách hiển thị glyph khỏi byte |
| JDK release | Minimum và hiện hành | Minimum và hiện hành | Minimum và hiện hành | Compile/test đúng API |

### 12.1. Kỳ vọng nào không nên hardcode?

Đừng đưa các giá trị sau vào stdout bắt buộc phải giống nhau ở mọi OS:

- `System.getProperty("os.name")` hoặc `file.separator`.
- `System.lineSeparator()`.
- `Charset.defaultCharset()` nếu không kiểm soát JDK/configuration.
- Đường dẫn được trả bởi `Files.createTempFile` hoặc `createTempDirectory`.
- Nguyên văn thông báo lỗi của compiler/JVM.
- Cách font và terminal vẽ trực tiếp emoji/dấu tiếng Việt.

**Nên giữ ổn định** các assertion về byte, code point, boolean equality và expected error branch của cùng fixture. Điều này giúp xác định lỗi dữ liệu thay vì nhầm với khác biệt hiển thị.

### 12.2. Lưu fixture đúng cách trong dự án

- Dùng file UTF-8 đã được xác nhận byte, không phụ thuộc editor tự sửa.
- Thêm fixture LF và CRLF riêng; cẩn thận cấu hình checkout/Git có thể tự đổi line endings.
- Dùng raw byte fixture malformed và BOM, tránh tạo bằng writer rồi gọi là byte chuẩn một cách vòng lặp.
- Nếu dùng checksum, xác nhận nó từ dữ liệu canonical đã được review.
- Lưu thông tin JDK, OS, locale, filesystem và charset khi test fail.
- Giới hạn log dữ liệu nhạy cảm: không in toàn bộ input người dùng chỉ để debug mã hóa.

### 12.3. Source, file và terminal là các ranh giới khác nhau

- **Source:** file Java mã hóa UTF-8 và `javac -encoding UTF-8`.
- **File/network:** `StandardCharsets.UTF_8` hoặc charset theo contract.
- **Terminal:** cấu hình xuất stdout, console code page và font ảnh hưởng hiển thị. File có byte đúng nhưng console thiếu glyph không có nghĩa nội dung đã hỏng.

JEP 400 của JDK 18 không cho phép kết luận rằng mọi terminal/console sẽ luôn hiển thị emoji đúng. Kiểm thử CLI riêng nếu sản phẩm phụ thuộc terminal.

## 13. Khi dữ liệu đi qua HTTP, CSV, JSON và database

Charset chỉ là **một lớp** của giao thức. Để bảo toàn tiếng Việt qua hệ thống:

**HTTP/JSON:** Biết đúng encoding và media type; dùng parser/serializer JSON phù hợp để kiểm tra escaping và cấu trúc. Không nối chuỗi bất kỳ rồi xem nó thành JSON hợp lệ.

**CSV:** Charset không giải quyết quoting. Trường tiếng Việt có dấu phẩy, dấu nháy hoặc xuống dòng cần parser/serializer CSV theo format. Chọn rõ separator và newline theo định dạng trao đổi.

**Database:** Driver, kiểu cột và collation phải phù hợp Unicode. Không sửa mojibake bằng các vòng `getBytes`/`new String` thiếu nguồn gốc. Normalization và so sánh chuỗi theo DB có thể khác chính sách của Java.

**Hash/chữ ký:** NFC/NFD, BOM và CRLF/LF có thể đổi byte và do đó đổi digest. Định nghĩa canonicalization trước khi tính hash/chữ ký, không sửa sau khi ký.

**Độ dài tối đa:** Nếu mạng giới hạn **byte**, đếm `getBytes(UTF_8).length`; nếu tính **code point**, dùng `codePointCount`; nếu tính số chữ/glyph người dùng cảm nhận, cần grapheme segmentation. Không dùng một hàm độ dài cho cả ba.

**File lớn:** `Files.readString` đọc toàn bộ vào String; với file lớn dùng `Files.newBufferedReader(path, UTF_8)` và xử lý streaming, nhớ rằng đọc từng dòng không giữ nguyên separator nếu mục tiêu là round-trip byte exact.

## 14. Những lỗi thường gặp

| Ngộ nhận | Kết luận đúng |
| --- | --- |
| “Mặc định Java mới là UTF-8 nên không cần biết encoding dữ liệu bên ngoài.” | Charset của giao thức phải được xác định riêng; JEP 400 không sửa file cũ. |
| “Chữ hiển thị đẹp nên file byte chắc đúng.” | Cần kiểm tra UTF-8 bytes và nội dung. |
| “`String.length()` là số ký tự hiển thị.” | Đếm UTF-16 units, không phải graphemes. |
| “Emoji luôn chỉ một `char`.” | Ký tự bổ sung cần surrogate pair. |
| “Cắt mọi UTF-16 offset đều an toàn.” | Có thể tạo surrogate không ghép cặp. |
| “Hai chữ Việt nhìn giống nhau chắc `equals`.” | NFC/NFD có thể khác chuỗi/byte. |
| “UTF-8 encoder tự normalize Unicode.” | Không. Chọn normalization tường minh. |
| “Normalize không làm thay đổi dữ liệu ký số.” | Có thể thay byte và hash. |
| “`new String(bytes,UTF_8)` luôn báo lỗi cho byte malformed.” | Có thể thay thế; strict decoder dùng REPORT. |
| “Nếu encoder đưa ra một byte thì surrogate ban đầu được giữ.” | Có thể là replacement. |
| “CRLF và LF là cùng byte.” | CRLF dùng hai byte, LF một byte. |
| “`String.lines()` chứng minh giữ nguyên line separator.” | Nó tách dòng logic và bỏ separator. |
| “UTF-8 BOM phải xóa bất kỳ ở đâu.” | Xử lý đầu stream theo contract. |
| “Ghép path bằng `\\` luôn chạy được trên Unix.” | Dùng `Path.resolve`. |
| “Nội dung file trên macOS luôn NFD.” | Tên file và nội dung file là hai lớp riêng. |
| “Test một OS tức đã kiểm thử cross-platform.” | Phải chạy các OS mục tiêu. |
| “Terminal không vẽ emoji là byte hỏng.” | Có thể chỉ thiếu glyph/font hoặc cấu hình output. |

## 15. Checklist trước khi chấp nhận pull request

1. Test có tiếng Việt đủ dấu, NFC/NFD, emoji, surrogate không ghép cặp, byte lỗi, BOM, LF/CRLF?
2. File nguồn Java lưu UTF-8 và build biết encoding đúng?
3. Các ranh giới file/network/DB có charset theo hợp đồng, không phụ thuộc default bất ngờ?
4. Test có so sánh cả String lẫn byte khi cần round-trip nguyên vẹn?
5. Mã nguồn có phân biệt byte / UTF-16 unit / code point / grapheme khi xử lý độ dài?
6. Có tránh cắt surrogate pair?
7. Có policy NFC hoặc bảo toàn raw rõ ràng?
8. Có giữ line endings khi cần và normalize chỉ ở nơi có yêu cầu?
9. Có xử lý BOM đầu file đúng hợp đồng?
10. Decoder strict có báo lỗi thay vì làm mất thông tin im lặng?
11. File lớn có được đọc theo stream khi cần?
12. Đường dẫn dùng `Path` và có test tên file Unicode thật nếu sản phẩm cần?
13. CI đã chạy Windows/Linux/macOS ở JDK mục tiêu?
14. Có fixture byte độc lập, tránh test writer/reader cùng mắc lỗi nhưng vẫn báo pass?
15. Có tách kiểm tra glyph console khỏi kiểm tra dữ liệu byte?
16. Có ghi nhận OS/JDK/charset trong báo cáo test fail?
17. Có dọn file/thư mục tạm và xử lý IOException đúng?
18. Có tránh lộ dữ liệu nhạy cảm khi log lỗi Unicode?
19. Có parser/serializer thật cho CSV/JSON, thay vì chỉ đổi charset?
20. Có báo rõ **môi trường nào đã chạy** và **môi trường nào chỉ mới lên kế hoạch**?

## 16. Câu hỏi tự kiểm tra

**1.** `"A🚀đ".length()` là bao nhiêu?  
**Đáp án:** 4 UTF-16 code units; có 3 code points, 7 UTF-8 bytes.

**2.** Vì sao cắt `substring(1,2)` ở ví dụ này sai?  
**Đáp án:** Chỉ lấy high surrogate của emoji, tạo chuỗi UTF-16 lỗi.

**3.** NFC `"ắ"` và NFD `"a\u0306\u0301"` có cùng byte không?  
**Đáp án:** Không. Sau khi normalize NFC nhất quán, chúng mới cho kết quả canonical cùng dạng.

**4.** Mã hóa UTF-8 tự normalize mọi chữ tiếng Việt không?  
**Đáp án:** Không. UTF-8 là byte encoding, normalization là thao tác khác.

**5.** Byte `C3 28` có hợp lệ theo UTF-8?  
**Đáp án:** Không. Strict decoder REPORT từ chối; REPLACE có thể sinh U+FFFD.

**6.** High surrogate không ghép cặp có thể strict encode UTF-8 nguyên vẹn không?  
**Đáp án:** Không. Encoder báo malformed input.

**7.** `Files.readString` có giữ CRLF khi file chứa CRLF không?  
**Đáp án:** Có; không tự đổi mọi newline thành LF.

**8.** Tại sao `String.lines()` không đủ để kiểm tra byte newline?  
**Đáp án:** Nó biểu diễn dòng logic và không giữ separator gốc.

**9.** UTF-8 BOM gồm những byte nào?  
**Đáp án:** `EF BB BF` ở đầu file, có thể thành U+FEFF sau decode.

**10.** Có nên xóa mọi U+FEFF trong file không?  
**Đáp án:** Không. Chỉ xử lý BOM ở đầu theo quy định, hoặc giữ nguyên nếu cần byte exact.

**11.** Vì sao dùng `Path.resolve`?  
**Đáp án:** Không hardcode separator riêng của OS; provider xử lý đường dẫn phù hợp.

**12.** Java 18 mặc định UTF-8 có đảm bảo mọi console in emoji đẹp không?  
**Đáp án:** Không. Terminal/font/encoding output còn là tầng khác.

**13.** `javac -encoding UTF-8` dùng cho source hay output file runtime?  
**Đáp án:** Dành cho compiler đọc source file Java.

**14.** Nếu file rất lớn, dùng `Files.readString` có luôn tốt không?  
**Đáp án:** Không; nên dùng buffered reader/streaming để giới hạn memory.

**15.** Chạy đúng một lần trên Windows có chứng minh chạy đúng Linux/macOS không?  
**Đáp án:** Không. Cần runner thật trên từng OS sản phẩm hỗ trợ.

## 17. Nguồn chính thức

- [Java SE 26 — StandardCharsets](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8 và các charset bắt buộc.
- [Java SE 26 — Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): readString/writeString, byte I/O, newline, lỗi decode.
- [Java SE 26 — String](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html): UTF-16 units, surrogate và code points.
- [Java SE 26 — Character](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.html): code point và surrogate pair.
- [Java SE 26 — Normalizer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): NFC/NFD.
- [Java SE 26 — CharsetDecoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html): chính sách decode lỗi.
- [Java SE 26 — CharsetEncoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetEncoder.html): strict encode và unpaired surrogate.
- [Java SE 26 — CodingErrorAction](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CodingErrorAction.html): REPORT, REPLACE, IGNORE.
- [Java SE 26 — Path](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html): xử lý path theo provider.
- [Java SE 7 — StandardCharsets](https://docs.oracle.com/javase/7/docs/api/java/nio/charset/StandardCharsets.html): mốc có `UTF_8` từ Java 7, không dùng thay tài liệu API hiện hành.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi từ JDK 18.
- [Unicode — Normalization FAQ](https://www.unicode.org/faq/normalization.html): Unicode canonical forms.
- [Unicode — BOM FAQ](https://www.unicode.org/faq/utf_bom.html): BOM và U+FEFF.
- [Oracle — Migrating from JDK 8](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html): mặc định charset và nâng cấp JDK.

**Ghi nhớ:** Dữ liệu văn bản portable không chỉ là “trên máy tôi hiển thị đúng”. Hãy xác định **UTF-8 tại ranh giới byte**, phân biệt **UTF-16/code points/graphemes**, kiểm tra **NFC/NFD**, dữ liệu lỗi, BOM và CRLF/LF, dùng **Path API**, rồi chạy một bộ fixture cố định trên **Windows/Linux/macOS**. Chỉ kết luận nền tảng nào đã PASS sau khi test thật sự được chạy trên nền tảng đó.