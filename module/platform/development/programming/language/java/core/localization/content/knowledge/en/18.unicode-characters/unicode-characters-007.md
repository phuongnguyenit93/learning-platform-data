# Phân biệt không gian Unicode với bộ mã bên ngoài trong Java

## 1. Vì sao hai khái niệm này cần được tách rõ?

Khi một ứng dụng Java đọc tên người, bản dịch tiếng Việt, biểu tượng cảm xúc hoặc dữ liệu JSON từ hệ thống khác, chúng ta phải giải quyết **hai câu hỏi độc lập**:

1. **Ký tự nào đang được nói đến?** Unicode định danh các ký tự và các phần tử văn bản bằng **code point**, chẳng hạn `U+0041` cho chữ `A`, `U+00E9` cho `é`, `U+1F600` cho biểu tượng `😀`.
2. **Làm sao các ký tự đó trở thành byte để lưu hoặc truyền?** Một **character encoding/charset** (như UTF-8, UTF-16BE, ISO-8859-1 hoặc Windows-1252) xác định quy tắc biểu diễn hay chuyển giữa dữ liệu ký tự và chuỗi byte.

**Unicode code point không phải là một byte; UTF-8 không phải “một ngôn ngữ khác”; Java `String` không phải một tệp UTF-8.**

Ví dụ chuỗi có nội dung `Aé😀` là cùng một dãy Unicode code point dù được chuyển thành:

- Dãy byte UTF-8: `41 C3 A9 F0 9F 98 80` (7 byte).
- Dãy byte UTF-16BE: `00 41 00 E9 D8 3D DE 00` (8 byte, **không tính BOM**).
- Với ISO-8859-1: **không thể mã hóa đầy đủ**, vì bảng mã đó không có biểu diễn cho `😀`.

Việc chọn encoding khác không làm thay đổi ký tự mà chúng ta **muốn** biểu diễn; nó làm thay đổi dãy byte và khả năng biểu diễn chính xác các ký tự đó. Nếu một đầu trong hệ thống ghi UTF-8 nhưng đầu kia giải mã thành Windows-1252, văn bản có thể biến thành các ký tự sai (*mojibake*), dù byte lúc truyền không bị mất.

### Mục tiêu bài học

Sau khi học xong, bạn có thể phân biệt:

- **Unicode code point space**, Unicode scalar value và code point viết bằng `U+...`.
- **Java UTF-16 code unit** (`char`, `String.length()`) với số code point, số byte và ký tự nhìn thấy.
- **Encoding** (UTF-8/UTF-16/legacy charset) với **decoding** và vị trí xảy ra chuyển đổi tại ranh giới I/O.
- Lỗi **mã hóa không biểu diễn được**, **giải mã sai charset**, **byte sequence hỏng**, **replacement character** và **normalization**.
- Cách ghi/đọc byte an toàn bằng `StandardCharsets`, xử lý lỗi nghiêm ngặt và xây kiểm thử round-trip.

## 2. “Không gian Unicode” là gì?

Unicode cung cấp hệ định danh chung cho văn bản. Mỗi **code point** có giá trị số viết dưới dạng `U+XXXX` hoặc nhiều chữ số hơn (ví dụ `U+1F600`). Không gian giá trị code point có phạm vi:

```text
U+0000 ................................. U+10FFFF
```

Trong khoảng ấy:

- `U+0000` đến `U+10FFFF` là phạm vi giá trị code point hợp lệ theo định nghĩa không gian Unicode.
- Khoảng `U+D800`–`U+DFFF` dành cho **UTF-16 surrogate code points**. Chúng **không phải Unicode scalar values**, không được dùng như ký tự Unicode độc lập hợp lệ để mã hóa thành UTF-8 chuẩn.
- Một **Unicode scalar value** là code point nằm ngoài vùng surrogate.
- Một code point có thể được gán cho ký tự, được giữ để dùng sau, có chức năng đặc biệt hoặc nằm trong nhóm không phải ký tự thông thường; **không phải mọi số trong không gian đều là một chữ cái được nhìn thấy**.
- Một số biểu diễn văn bản gồm nhiều code point, chẳng hạn một chữ cái đi kèm dấu tổ hợp (*combining mark*) hoặc emoji ghép bằng zero-width joiner.

Một số ví dụ:

| Biểu diễn | Code point | Ghi chú |
| --- | --- | --- |
| `A` | `U+0041` | Chữ Latin A. |
| `é` | `U+00E9` | Chữ e có dấu sắc ở dạng dựng sẵn (*precomposed*). |
| `e◌́` | `U+0065` + `U+0301` | Chữ e và dấu sắc tổ hợp: hai code point, có thể trông như `é`. |
| `😀` | `U+1F600` | Code point ngoài Basic Multilingual Plane (BMP). |
| Dấu cách thường | `U+0020` | Khác NBSP và nhiều loại khoảng trắng Unicode. |
| `U+FEFF` | `U+FEFF` | Có thể xuất hiện ở đầu text do BOM hoặc dữ liệu chứa ký tự này; cần xử lý theo giao thức. |

**Một “ký tự” trong lời nói hằng ngày không luôn tương ứng một code point.** Unicode có khái niệm grapheme cluster (*cụm ký tự được người dùng nhận là một đơn vị*). Một grapheme cluster có thể chứa nhiều code point, và một code point ngoài BMP chiếm hai `char` UTF-16 trong Java.

### BMP và supplementary code points

**Basic Multilingual Plane (BMP)** là phạm vi `U+0000`–`U+FFFF`. Những Unicode scalar values nằm ngoài BMP gọi là **supplementary code points** (`U+10000`–`U+10FFFF`). Để biểu diễn một supplementary code point trong UTF-16, cần **hai code unit**, gọi là **surrogate pair**.

`😀` (U+1F600) có surrogate pair:

```text
High surrogate: U+D83D
Low surrogate:  U+DE00
```

Đừng coi `U+D83D` là một ký tự `😀` hoàn chỉnh. Nếu xử lý một nửa surrogate pair như ký tự độc lập, bạn có thể cắt hỏng text, ghi ra byte không hợp lệ hoặc làm mất thông tin trong quá trình encoding.

## 3. Java String, char và code point không giống byte

Java `char` là **một UTF-16 code unit 16-bit**, không phải một Unicode character bất kỳ và cũng không phải một byte. Java `String` cung cấp cách truy cập theo vị trí code unit UTF-16. Vì vậy:

- `String.length()` đếm **UTF-16 code units**, không phải số Unicode code point hay số byte UTF-8.
- `String.charAt(index)` trả **một code unit**, có thể là high/low surrogate của một code point bổ sung.
- `String.codePointAt(index)` có thể trả code point đầy đủ khi index trỏ tới high surrogate đi kèm low surrogate hợp lệ.
- `String.codePointCount(beginIndex, endIndex)` đếm code point trên đoạn UTF-16, còn `String.codePoints()` cung cấp `IntStream` các code point.
- `Character.charCount(codePoint)` trả số code unit UTF-16 cần dùng cho code point (thông thường 1 hoặc 2 tùy phạm vi).
- `String.offsetByCodePoints(...)` có thể dùng khi muốn di chuyển theo code point thay vì cộng bừa chỉ số `char`.

Ví dụ:

```java
String text = "A\u00E9\uD83D\uDE00"; // Aé😀

System.out.println(text.length());                 // 4
System.out.println(text.codePointCount(0, 4));      // 3
System.out.println(text.codePointAt(2) == 0x1F600); // true
```

Trong chuỗi:

```text
UTF-16 index   0        1        2           3
code unit     0041     00E9     D83D        DE00
ký tự         A        é        [hai code unit tạo 😀]
```

Vì vậy, khi viết UI:

- Không cắt “100 ký tự” bằng `substring(0, 100)` mà mặc định đây là 100 ký tự mà người dùng thấy; nó có thể cắt giữa surrogate pair hoặc grapheme cluster.
- Giới hạn độ dài dữ liệu phải nói rõ đó là **byte**, **UTF-16 code unit**, **Unicode code point** hay **grapheme cluster**.
- Các form nhập tên, emoji hay lời nhắn thường cần tính theo cụm ký tự được người dùng thấy. Java core có `BreakIterator` cho việc phân đoạn văn bản, nhưng hỗ trợ chi tiết các chuỗi emoji/grapheme có thể phụ thuộc phiên bản và thuật toán; nếu cần đúng Unicode extended grapheme cluster ở mọi trường hợp, phải chọn và kiểm thử một triển khai phù hợp.

**Điểm thực thi:** Java không cam kết byte layout bên trong đối tượng `String` giống hệt file UTF-16BE. Các JDK hiện đại có thể tối ưu vùng nhớ lưu chuỗi; điều mà các API `charAt`/`length` cam kết là **ngữ nghĩa UTF-16 code unit**, không phải một định dạng byte công khai.

## 4. Encoding là ánh xạ giữa dữ liệu ký tự và byte

Một **charset/character encoding** xác định cách mã hóa ký tự thành byte và giải mã byte thành ký tự. Trong Java, API chính là `java.nio.charset.Charset`, các lớp `CharsetEncoder`/`CharsetDecoder`, và các hằng `StandardCharsets`.

Quy trình ở biên I/O:

```text
                             ENCODE
Java String / dãy ký tự ------------------> byte[]
        ^                                   |
        |                                   | file / socket / HTTP /
        |                                   | database driver / stream
        |                                   v
        +-------------------------------  byte[]
                             DECODE
```

Cần biết charset tại **hai bên ranh giới**. Nếu sender dùng UTF-8 và receiver lại dùng ISO-8859-1, hai phía bất đồng về cách diễn giải byte.

### Những encoding thường gặp

| Charset | Nguyên tắc | Đặc điểm cần nhớ |
| --- | --- | --- |
| `UTF-8` | Mã hóa Unicode scalar values bằng 1–4 byte mỗi code point. | ASCII dùng 1 byte; phổ biến trên web, JSON, file văn bản hiện đại. |
| `UTF-16BE` | UTF-16 code units được ghi big-endian. | 2 byte/code unit; supplementary code point dùng surrogate pair = 4 byte. |
| `UTF-16LE` | UTF-16 code units được ghi little-endian. | Byte order ngược BE; không nên lẫn nếu không có BOM/thỏa thuận. |
| `UTF-16` (charset Java) | UTF-16 với quy tắc BOM/endianness của charset. | Có thể sinh/nhận BOM theo quy tắc UTF-16; không đồng nhất với UTF-16BE. |
| `US-ASCII` | Bảng ký tự 7-bit. | Không biểu diễn được chữ Việt có dấu và nhiều ký tự ngoài ASCII. |
| `ISO-8859-1` | Bộ mã legacy một byte, chủ yếu Latin Tây Âu. | Biểu diễn được `é` nhưng không biểu diễn được emoji hay phần lớn tiếng Việt. |
| `windows-1252` | Legacy single-byte charset của Windows Tây Âu. | Không đồng nhất ISO-8859-1 ở vùng byte `0x80`–`0x9F`. |

**Unicode và UTF-8 không phải hai đối thủ:** Unicode là không gian định danh và các quy tắc văn bản; UTF-8 là **một encoding form/encoding scheme để biểu diễn Unicode trong byte**. UTF-16 và UTF-32 cũng là các cách biểu diễn Unicode. Trong khi đó, các bảng mã legacy thường chỉ biểu diễn được một tập ký tự hạn chế.

### Cùng nội dung, byte khác nhau

Xét chuỗi `Aé😀`:

| Đơn vị | Kết quả | Lý do |
| --- | --- | --- |
| Unicode code points | `U+0041 U+00E9 U+1F600` | Ba giá trị Unicode. |
| Java UTF-16 code units | `0041 00E9 D83D DE00` | Emoji cần hai code unit. |
| UTF-8 bytes | `41 C3 A9 F0 9F 98 80` | Tổng 7 byte. |
| UTF-16BE bytes, không BOM | `00 41 00 E9 D8 3D DE 00` | Tổng 8 byte. |
| ISO-8859-1 | Không thể round-trip đầy đủ | `😀` không nằm trong repertoire của charset. |

Đừng lấy `String.length()` để suy ra dung lượng file UTF-8, kích thước JSON body hoặc giới hạn số byte của database. Muốn số byte sau mã hóa, dùng `text.getBytes(charset).length` với charset thực sự dùng; cũng lưu ý cấu trúc protocol và escaping có thể thêm byte ngoài bản thân chuỗi text.

## 5. Encoding và decoding là hai chiều phải khớp nhau

### Mã hóa đúng

`String.getBytes(StandardCharsets.UTF_8)` chuyển text thành UTF-8 bytes; `new String(bytes, StandardCharsets.UTF_8)` giải mã chúng trở lại. Ví dụ:

```java
String message = "Xin chào!";
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
String copy = new String(bytes, StandardCharsets.UTF_8);
System.out.println(message.equals(copy)); // true
```

Hai API trên dùng charset tường minh. Một round-trip đúng chứng minh dữ liệu có thể được tái tạo qua đường đi tương ứng cho chuỗi đã chọn. Nó không chứng minh một hệ thống khác thực tế đang dùng UTF-8, cũng không đảm bảo không có thay đổi khi text đi qua các tầng khác.

### Giải mã sai charset gây mojibake

Ví dụ ký tự `é` (U+00E9) được encode UTF-8 thành hai byte `C3 A9`. Nếu lại giải mã hai byte đó như ISO-8859-1, chúng được hiểu là hai code point khác (`U+00C3` và `U+00A9`), tạo ra chuỗi nhìn như `Ã©`.

```text
Unicode U+00E9 "é"
        |
      UTF-8 encode
        v
bytes C3 A9
        |
      ISO-8859-1 decode (SAI!)
        v
Unicode U+00C3 U+00A9 "Ã©"
```

Bản chất lỗi là **bất đồng về encoding** ở ranh giới byte/text, không phải Unicode “thiếu chữ”. Nếu chuỗi sai này được encode lại và lưu vào database như dữ liệu thật, vấn đề có thể lan rộng.

Để khắc phục, xác định **byte gốc, charset đã dùng khi encode, charset đã dùng khi decode và tầng nào bị sai**. Không dùng một chuỗi thay thế `"Ã" -> ...` trên toàn bộ dữ liệu, vì có thể làm hỏng text vốn đã đúng hoặc text chứa ký tự ấy thật sự.

### Charset mặc định không phải hợp đồng trao đổi dữ liệu

Trong Java, `String.getBytes()` không tham số sử dụng charset mặc định của môi trường Java. Ở Java 17, kết quả có thể phụ thuộc hệ điều hành/JVM và cấu hình chạy; từ Java 18, UTF-8 là default theo chính sách chuẩn hóa mới nhưng vẫn có một số chế độ/ngoại lệ cấu hình. **Dữ liệu trao đổi qua file, API hoặc message queue nên dùng charset tường minh** thay vì dựa vào mặc định.

`javac -encoding UTF-8` chỉ định encoding của **tệp nguồn Java**, không tự quyết định encoding cho file đọc bằng ứng dụng lúc chạy hoặc mọi byte từ HTTP.

## 6. Ví dụ Java 17+ hoàn chỉnh: Unicode, byte và lỗi charset

Tạo tệp **`UnicodeBoundaryDemo.java`** dưới đây. Chương trình chỉ xử lý dữ liệu trong bộ nhớ, không ghi file và không phụ thuộc charset console để in biểu tượng cảm xúc. Các byte được in bằng `HexFormat`, vốn có từ Java 17.

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.HexFormat;
import java.util.Locale;

public class UnicodeBoundaryDemo {

    private static String hex(byte[] bytes) {
        return HexFormat.of().withUpperCase().formatHex(bytes);
    }

    public static void main(String[] args) {
        String text = "A\u00E9\uD83D\uDE00"; // Aé😀

        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints="
                + text.codePointCount(0, text.length()));
        System.out.println("emoji=U+"
                + Integer.toHexString(text.codePointAt(2))
                        .toUpperCase(Locale.ROOT));

        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        System.out.println("utf8=" + hex(utf8));
        System.out.println("utf16be="
                + hex(text.getBytes(StandardCharsets.UTF_16BE)));

        String roundTrip =
                new String(utf8, StandardCharsets.UTF_8);
        System.out.println("roundTrip="
                + text.equals(roundTrip));

        String wrongDecode =
                new String(utf8, StandardCharsets.ISO_8859_1);
        System.out.println("wrongDecodeMatches="
                + text.equals(wrongDecode));

        CharsetEncoder latin1 = StandardCharsets.ISO_8859_1
                .newEncoder()
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            latin1.encode(CharBuffer.wrap(text));
            System.out.println("latin1=OK");
        } catch (CharacterCodingException ex) {
            System.out.println("latin1=UNMAPPABLE");
        }

        byte[] broken = {
                (byte) 0xC3, (byte) 0x28
        };
        CharsetDecoder strict = StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT);

        try {
            strict.decode(ByteBuffer.wrap(broken));
            System.out.println("malformedUtf8=ACCEPTED");
        } catch (CharacterCodingException ex) {
            System.out.println("malformedUtf8=REJECTED");
        }

        String lenient =
                new String(broken, StandardCharsets.UTF_8);
        System.out.println("lenientHasReplacement="
                + lenient.contains("\uFFFD"));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("directEqual="
                + composed.equals(decomposed));
        System.out.println("nfcEqual="
                + composed.equals(Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 UnicodeBoundaryDemo.java
java UnicodeBoundaryDemo
```

**Stdout chính xác của ví dụ:**

```text
utf16Units=4
codePoints=3
emoji=U+1F600
utf8=41C3A9F09F9880
utf16be=004100E9D83DDE00
roundTrip=true
wrongDecodeMatches=false
latin1=UNMAPPABLE
malformedUtf8=REJECTED
lenientHasReplacement=true
directEqual=false
nfcEqual=true
```

### Giải thích từng phép thử

1. `utf16Units=4` vì `A` và `é` mỗi ký tự chiếm một UTF-16 code unit, còn `😀` chiếm hai. `codePoints=3` là số code point.
2. `emoji=U+1F600` nhờ `codePointAt(2)` đọc đúng surrogate pair bắt đầu ở UTF-16 index 2.
3. `utf8` và `utf16be` in byte thực, minh họa các encoding khác nhau của **cùng một dãy ký tự**.
4. `roundTrip=true` vì encode/decode đều dùng UTF-8. `wrongDecodeMatches=false` vì byte UTF-8 bị đọc như ISO-8859-1.
5. `latin1=UNMAPPABLE` thể hiện legacy charset không có biểu diễn cho emoji. Encoder dùng `CodingErrorAction.REPORT` để **báo lỗi thay vì âm thầm thay ký tự**.
6. `malformedUtf8=REJECTED` vì cặp byte `C3 28` không tạo thành một chuỗi UTF-8 hợp lệ. Decoder nghiêm ngặt phát hiện byte hỏng.
7. `lenientHasReplacement=true` minh họa một đường decode dùng ký tự thay thế `U+FFFD` khi input hỏng. Văn bản đã chứa replacement character thường không thể suy ra lại byte gốc.
8. `directEqual=false` giữa hai cách biểu diễn `é`. `nfcEqual=true` vì chuẩn hóa về NFC cho kết quả tương đương trong ví dụ.

**Quan trọng:** đây là ví dụ cho **ranh giới biểu diễn**, không phải cách phân loại “có tiếng Việt hay không”. Một charset không phù hợp có thể mã hóa được một số chữ Việt nhưng vẫn làm mất các code point khác; kiểm thử phải dùng đúng tập ký tự mà sản phẩm thực sự hỗ trợ.

## 7. Khi byte hoặc ký tự không hợp lệ: thay thế hay báo lỗi?

### 7.1. Encoder có thể gặp unmappable character

Giả sử gửi text `Aé😀` đến một hệ thống chỉ nhận ISO-8859-1. Ký tự `😀` không biểu diễn được. Các chính sách có thể là:

- **REPORT:** dừng và báo `UnmappableCharacterException` (qua API `CharsetEncoder`).
- **REPLACE:** thay ký tự bằng một chuỗi byte thay thế do encoder cấu hình; thông thường là dấu hỏi hoặc ký hiệu thay thế tương ứng.
- **IGNORE:** bỏ ký tự không biểu diễn được; rất dễ làm mất dữ liệu.

`String.getBytes(Charset)` sử dụng hành vi thay thế khi có đầu vào không thể biểu diễn trọn vẹn; nếu dữ liệu quan trọng, đừng xem một lời gọi `getBytes` thành công là chứng minh không mất thông tin. Muốn kiểm soát nghiêm ngặt, dùng `CharsetEncoder` với `CodingErrorAction.REPORT` cho `onMalformedInput(...)` và `onUnmappableCharacter(...)` theo chính sách.

Ví dụ minh họa (đặt trong phương thức Java với import phù hợp):

```java
CharsetEncoder encoder = StandardCharsets.ISO_8859_1
        .newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

ByteBuffer result = encoder.encode(
        CharBuffer.wrap("A\u00E9\uD83D\uDE00"));
// Ném CharacterCodingException do emoji không thể mã hóa.
```

Đoạn này chủ ý gây exception khi chạy với text đó. Không phải mọi exception khi encode đều là “byte UTF-8 sai”; đây là lỗi **không thể biểu diễn Unicode character trong charset đích**.

### 7.2. Decoder có thể gặp malformed byte sequence

Một decoder cần biết byte nào là một chuỗi hợp lệ của charset. Với UTF-8, byte `C3` phải theo sau bởi một continuation byte hợp lệ. Byte `28` là `(` và **không phải** continuation byte, nên `C3 28` bị coi là malformed.

```java
CharsetDecoder decoder = StandardCharsets.UTF_8
        .newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String text = decoder.decode(
        ByteBuffer.wrap(new byte[] {(byte) 0xC3, 0x28}))
        .toString();
// Ném CharacterCodingException.
```

Đây là đoạn minh họa với import tương ứng; không phải chương trình độc lập. Tùy bài toán:

- **Dữ liệu giao dịch, văn bản cần toàn vẹn:** cân nhắc REPORT để không âm thầm thay ký tự.
- **Giao diện đọc log hỏng hoặc tài liệu legacy:** có thể hiển thị replacement character nhưng phải biết dữ liệu đã hỏng/mất khả năng khôi phục.
- **Dữ liệu từ nguồn không tin cậy:** xác minh charset và giới hạn kích thước; không cố “đoán” encoding rồi nuốt lỗi.

Một lỗi decode được phát hiện không có nghĩa hệ thống chắc chắn biết charset đúng. Nó chỉ chứng minh byte không hợp lệ **theo charset đang thử**. Có nhiều byte sequence hợp lệ ở charset sai nhưng lại diễn giải thành ký tự không đúng (mojibake), nên chỉ kiểm tra khả năng decode không đủ xác nhận dữ liệu đúng.

### 7.3. Surrogate không ghép cặp là trường hợp riêng

Một Java `String` có thể chứa một UTF-16 code unit surrogate đơn lẻ do bị cắt chuỗi sai hoặc nhận dữ liệu hỏng. Đó không phải Unicode scalar value. Khi encode UTF-8, encoder phải xử lý như **malformed input** theo chính sách, không phải tự phát minh code point độc lập.

Có thể kiểm tra chuỗi về surrogate bằng cách duyệt code unit/code point hoặc xác nhận nghiêm ngặt trước khi trao đổi dữ liệu quan trọng. Không cắt `String` theo chỉ số code unit một cách bừa bãi rồi kỳ vọng UTF-8 encoder giữ nguyên “nửa emoji”.

## 8. Normalization không phải encoding

Unicode có thể có nhiều dãy code point biểu diễn văn bản tương đương về ngữ nghĩa, ví dụ:

```text
é dựng sẵn:           U+00E9
e + dấu sắc tổ hợp:   U+0065 U+0301
```

Cả hai có thể trông giống nhau khi hiển thị, nhưng dãy code point khác, nên:

```java
String a = "\u00E9";
String b = "e\u0301";

System.out.println(a.equals(b)); // false
System.out.println(a.equals(
        Normalizer.normalize(b, Normalizer.Form.NFC))); // true
```

Đây là đoạn code minh họa trong một phương thức Java, cần import `java.text.Normalizer`.

**Normalization:** `Normalizer.Form.NFC`, `NFD`, `NFKC`, `NFKD` là các phép biến đổi giữa những dạng biểu diễn Unicode theo quy tắc chuẩn hóa. Chúng không biến byte UTF-8 thành byte UTF-16, không phát hiện đúng/sai charset gốc và không tự phục hồi mojibake.

- **NFC:** chuẩn hóa dạng có kết hợp chuẩn tắc; thường phù hợp khi muốn lưu/so sánh văn bản đã được chuẩn hóa theo hợp đồng ứng dụng.
- **NFD:** phân rã theo quy tắc tương đương chuẩn tắc; thường tạo dạng gồm base character + combining marks khi thích hợp.
- **NFKC/NFKD:** dùng *compatibility equivalence* có thể thay đổi phân biệt biểu diễn có ý nghĩa trong một số ngữ cảnh; không áp dụng vô điều kiện với mã định danh, mật khẩu hoặc nội dung cần giữ nguyên.

Normalization **không giải quyết mọi trường hợp “nhìn giống nhau”**: chữ Latin và Cyrillic trông tương tự vẫn có thể là code point khác; đây là vấn đề confusable/security và chính sách định danh. Cũng không phải mọi tổ hợp emoji hay kí tự đặc biệt đều trở thành một code point sau NFC.

### Hai sai lầm phổ biến

1. “Hai chuỗi nhìn như nhau thì `String.equals` phải trả `true`”: sai nếu dãy code point khác hoặc có ký tự ẩn/combining marks.
2. “Để sửa chữ bị `Ã©`, chỉ cần `Normalizer.normalize`”: sai vì mojibake liên quan **byte được decode bằng charset không đúng**, không phải chỉ khác dạng chuẩn hóa Unicode.

## 9. BOM, byte order và các ranh giới ngoài Java

### 9.1. UTF-16 byte order

Một UTF-16 code unit có 16 bit, nên cần quy định thứ tự byte:

- `UTF-16BE`: byte cao trước, ví dụ `A` → `00 41`.
- `UTF-16LE`: byte thấp trước, ví dụ `A` → `41 00`.
- Charset `UTF-16` có quy tắc BOM/endianness riêng khi đọc/ghi.

**BOM (Byte Order Mark)** là một chuỗi byte/ký hiệu đầu luồng có thể dùng để chỉ thứ tự byte trong các dạng UTF-16. Với UTF-8, BOM `EF BB BF` không cần để xác định byte order; một số file có BOM vì lý do tương thích, nhưng các ứng dụng/giao thức có chính sách xử lý khác nhau. Không tự động thêm hoặc bỏ BOM nếu chưa biết định dạng đầu vào.

Nếu đọc một file UTF-8 có BOM bằng API không loại bỏ BOM, ký tự `U+FEFF` có thể nằm đầu chuỗi. Điều này có thể ảnh hưởng key lookup, header CSV hay so sánh chuỗi. Hãy test BOM theo định dạng file thực tế, không trông chờ mọi reader “tự xử lý”.

### 9.2. Ghi và đọc file bằng charset tường minh

Ví dụ code minh họa trong phương thức Java:

```java
Path path = Path.of("message.txt");
String message = "Tiếng Việt – 😀";

Files.writeString(path, message, StandardCharsets.UTF_8);
String loaded = Files.readString(path, StandardCharsets.UTF_8);

System.out.println(message.equals(loaded)); // true
```

Cần import `java.nio.file.Path`, `java.nio.file.Files`, `java.nio.charset.StandardCharsets`; phương thức gọi phải xử lý hoặc khai báo `IOException`. Đoạn này **thực sự ghi tệp** nếu chạy; nó là minh họa cho chương trình có quyền ghi, không nằm trong demo độc lập ở mục 6.

Một ứng dụng legacy có thể dùng `InputStreamReader`, `OutputStreamWriter`, `BufferedReader` hoặc `Writer`; hãy đưa `Charset` rõ ràng ở nơi chuyển stream byte sang text, không dùng constructor dựa vào default charset khi giao thức đã có encoding quy định.

### 9.3. HTTP, JSON, CSV và database

| Ranh giới | Cần xác định | Lỗi thường gặp |
| --- | --- | --- |
| HTTP request/response | Quy ước charset của media type và framework; tham số charset nếu giao thức hỗ trợ. | Encode UTF-8 nhưng server/client giải mã theo một charset khác. |
| JSON | JSON trao đổi giữa các hệ thống hiện đại thường dùng UTF-8 theo chuẩn áp dụng; có quy tắc escaping riêng. | Nhầm `\\uXXXX` trong JSON với byte gốc hoặc dùng charset không phù hợp. |
| CSV | Quy ước encoding, BOM, delimiter, quote của file và hệ thống nhập. | Bảng tính mở file UTF-8 như legacy encoding; tiêu đề/tiếng Việt bị lỗi. |
| Database | Charset/collation của database, connection/driver và trường text. | Driver hoặc schema không lưu được code point ngoài BMP; dữ liệu bị thay mất. |
| Logs/console | Charset console, logging appender, font hiển thị. | Bytes đúng nhưng terminal/render không hiển thị glyph đúng; ngược lại. |
| File tên/đường dẫn | Cách OS và API xử lý text của path, normalization khác nhau. | So sánh tên file dựa vào dạng Unicode, ký tự không hiển thị hoặc khác chuẩn hóa. |

Đừng khẳng định “tất cả lỗi font là lỗi encoding”. Một chuỗi Unicode có thể hoàn toàn đúng, byte đã decode đúng, nhưng **font không có glyph** để render. Đây là một tầng khác với character encoding. Nên kiểm tra lần lượt byte → decode → dãy code point → font/layout.

### 9.4. JSON escape không phải UTF-8 encoding

Một ký tự có thể xuất hiện trong JSON dưới dạng trực tiếp hoặc escape:

```json
{"message":"é"}
```

hoặc:

```json
{"message":"\u00E9"}
```

Sau khi JSON parser xử lý đúng, hai trường có thể tạo cùng giá trị Unicode trong `String`. Tuy nhiên, cách viết escape trong JSON là **cú pháp serialization**, không phải cách xác định charset của luồng byte mang JSON. Dữ liệu JSON cuối cùng vẫn phải được mã hóa thành byte theo giao thức.

Với supplementary code point như `U+1F600`, JSON escape có thể dùng cặp `\uD83D\uDE00`; parser cần hiểu hai surrogate escape như một code point khi sử dụng chúng cùng nhau. Không tự cắt chuỗi escape rồi coi từng nửa surrogate là một ký tự đầy đủ.

## 10. Kiểm thử Unicode và charset đúng ở boundary

Một test tốt cần kiểm tra cả dữ liệu và điều kiện chuyển đổi, không chỉ “màn hình trông đúng”. Ma trận sau giúp tách lỗi:

| Trường hợp | Kiểm tra | Kỳ vọng |
| --- | --- | --- |
| ASCII `A` | UTF-8, UTF-16BE | Byte khác, code point vẫn `U+0041`. |
| `é` | UTF-8 round-trip | `U+00E9` được tái tạo. |
| `😀` | `String.length` và `codePointCount` | 2 UTF-16 code units, 1 code point. |
| `Aé😀` | UTF-8 vs UTF-16BE bytes | 7 byte vs 8 byte, không BOM. |
| `Aé😀` tới ISO-8859-1 | Strict encoder | Từ chối unrepresentable character. |
| `C3 28` giải mã UTF-8 | Strict decoder | Báo malformed input. |
| `C3 28` qua lenient decoder | Replacement behavior | Có thể chứa `U+FFFD`; cần biết đã mất dữ liệu. |
| UTF-8 bytes đọc như ISO-8859-1 | So sánh code points | Chuỗi khác, dù byte đầu vào không thay đổi. |
| `é` và `e` + combining accent | `String.equals` trước/sau NFC | Khác trước, bằng sau chuẩn hóa phù hợp. |
| Chuỗi có unpaired surrogate | Encode strict UTF-8 | Không âm thầm coi là Unicode scalar hợp lệ. |
| File UTF-8 có BOM | Reader ứng dụng | Chính sách giữ/bỏ BOM được test rõ ràng. |
| JSON có emoji escape | Parser JSON | Code point và round-trip đúng khi escape hợp lệ. |
| Độ dài/giới hạn field | Byte/code point/grapheme | Phù hợp đúng đơn vị giới hạn đã ghi trong hợp đồng. |

### Lưu ý an toàn đầu vào

- Hạn chế kích thước byte và độ dài text theo ngữ cảnh để tránh tốn tài nguyên khi decode, normalize hoặc xử lý grapheme.
- Khi xác thực chữ ký hoặc hash, phải quy định rõ **byte sequence** được ký; hai biểu diễn Unicode tương đương về ngữ nghĩa nhưng byte khác nhau có thể tạo hash khác nhau.
- Khi tạo mã định danh, đường dẫn hay username, cân nhắc chuẩn hóa, chữ hoa/chữ thường, Unicode confusable và các ký tự vô hình theo chính sách; không tự suy rằng normalization giải quyết mọi vấn đề an ninh.
- Với dữ liệu pháp lý hoặc văn bản cần giữ nguyên từng byte, cần phân biệt “nội dung Unicode” với “byte gốc” và có thể phải lưu cả hai theo yêu cầu.

## 11. Sai lầm thường gặp và hướng khắc phục

| Nhầm lẫn | Hậu quả | Cách đúng |
| --- | --- | --- |
| “Unicode chính là UTF-8.” | Nhầm danh tính ký tự với biểu diễn byte. | Unicode là không gian code point, UTF-8 là encoding. |
| “Một ký tự Java = một code point.” | Cắt hỏng emoji/surrogate pair. | Phân biệt `char` UTF-16 code unit và code point. |
| “`String.length()` là số byte UTF-8.” | Sai giới hạn dung lượng và validation. | Đếm bytes sau khi encode đúng charset. |
| “UTF-16BE byte là nội dung bộ nhớ `String`.” | Phụ thuộc layout nội bộ JDK. | Chỉ dựa vào contract của API và `getBytes(UTF_16BE)`. |
| “Mọi code point đều là scalar value.” | Có surrogate values không phải scalar. | Loại `U+D800`–`U+DFFF` trong dữ liệu Unicode scalar. |
| “Legacy charset ghi được mọi chữ Việt và emoji.” | Ký tự có thể bị thay/bỏ. | Dùng UTF-8 khi giao thức cho phép, strict error handling. |
| “Gọi `getBytes()` không tham số luôn giống nhau.” | Hành vi có thể phụ thuộc runtime/default charset. | Truyền `StandardCharsets.UTF_8` hoặc charset đã thỏa thuận. |
| “Giải mã không ném lỗi nghĩa là charset đúng.” | Có thể xảy ra mojibake hợp lệ về byte. | Kiểm tra charset contract và dữ liệu nguồn. |
| “Normalizer sửa được mojibake.” | Không thể khôi phục dãy byte đã hiểu sai chỉ bằng normalization. | Chẩn đoán đúng đường encode/decode. |
| “Mọi ký tự nhìn giống nhau đều `equals`.” | Khác code point hoặc combining marks. | Dùng normalization và chính sách so sánh phù hợp. |
| “BOM UTF-8 luôn tự biến mất.” | Có thể còn `U+FEFF` trong text. | Xử lý theo định dạng và test API đọc thực tế. |
| “Font lỗi tức UTF-8 sai.” | Text có thể đúng nhưng thiếu glyph. | Kiểm tra từng tầng decode, code points, font. |
| “Unicode `\uXXXX` là bốn byte.” | Đây có thể là ký pháp escape trong Java/JSON, không phải byte UTF-8. | Phân biệt syntax escape, code point và encoding. |

## 12. Bài tập thực hành

**Bài 1 — Đếm đúng đơn vị:** cho các chuỗi `"ABC"`, `"é"`, `"e\u0301"`, `"😀"` và `"Aé😀"`. In `String.length()`, `codePointCount(...)`, `getBytes(UTF_8).length`. Ghi lại vì sao cả ba con số có thể khác nhau.

**Bài 2 — Vẽ đường chuyển đổi:** từ `Aé😀`, liệt kê code points, các UTF-16 code units và UTF-8 bytes. Thử giải mã byte UTF-8 bằng ISO-8859-1, in chuỗi sai và giải thích cụ thể khâu nào đã dùng charset không khớp.

**Bài 3 — Mã hóa legacy:** thử `US_ASCII` và `ISO_8859_1` với các từ `"Hello"`, `"café"` và `"Tiếng Việt"`. Dùng `CharsetEncoder` + `CodingErrorAction.REPORT`; phân biệt input *malformed* với ký tự *unmappable*.

**Bài 4 — Dữ liệu UTF-8 hỏng:** tạo các byte không hợp lệ `C3 28`; so sánh `CharsetDecoder` REPORT với đường decode thay thế. Vì sao việc thay bằng `U+FFFD` có thể làm mất dữ liệu không thể khôi phục?

**Bài 5 — Normalization:** so sánh `"\u00E9"` và `"e\u0301"` trước/sau `Normalizer.Form.NFC`. Sau đó thử một chuỗi có hai ký tự nhìn giống nhưng thuộc bảng chữ khác và chỉ ra vì sao NFC không giải quyết sự nhầm lẫn ấy.

**Bài 6 — File UTF-8:** ghi một file text chứa tiếng Việt và emoji bằng `Files.writeString(..., UTF_8)`, đọc lại bằng `Files.readString(..., UTF_8)`. Kiểm tra content equality và byte round-trip. Sau đó thử đọc bằng charset sai trên bản sao thử nghiệm, không ghi đè file gốc.

**Bài 7 — Thiết kế hợp đồng API:** quy định một field nhập liệu được giới hạn 100 UTF-8 bytes thay vì 100 ký tự người dùng thấy. Viết validator đúng đơn vị, test emoji, chữ tiếng Việt tổ hợp, chuỗi có ký tự ghép và surrogate pair; nêu khi nào giới hạn theo grapheme cluster phù hợp hơn.

### Checklist hoàn thành

- [ ] Phân biệt Unicode code point space và character encoding/charset ngoài.
- [ ] Biết `U+0000`–`U+10FFFF` và vùng surrogate `U+D800`–`U+DFFF` không phải scalar values.
- [ ] Hiểu `char`, `String.length`, code point, byte, grapheme cluster là các đơn vị khác nhau.
- [ ] Có thể giải thích cùng chuỗi `Aé😀` tạo byte UTF-8/UTF-16BE khác nhau.
- [ ] Dùng `StandardCharsets` tường minh khi encode/decode qua boundary.
- [ ] Biết phân biệt lỗi malformed bytes, unmappable characters, mojibake và replacement character.
- [ ] Hiểu normalization là biến đổi chuỗi Unicode, không phải chuyển đổi encoding.
- [ ] Kiểm soát file/HTTP/database/console, BOM và charset contract theo từng giao thức.
- [ ] Viết được test round-trip và xác thực đúng đơn vị độ dài theo nghiệp vụ.

**Kết luận:** Unicode trả lời câu hỏi **“ký tự nào?”** bằng code point, còn charset/encoding trả lời **“biểu diễn thành byte thế nào?”** tại ranh giới lưu trữ và truyền tin. Trong Java, `String` hoạt động theo UTF-16 code units; muốn trao đổi dữ liệu an toàn, phải xác định charset rõ ràng, kiểm soát lỗi decode/encode và phân biệt normalization với encoding.