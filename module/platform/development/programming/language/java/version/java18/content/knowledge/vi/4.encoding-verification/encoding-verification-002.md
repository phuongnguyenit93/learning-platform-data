# Tạo bộ dữ liệu kiểm chứng gồm ASCII, tiếng Việt, emoji, ký tự tổ hợp và dòng rỗng

## 1. Mục tiêu của bộ dữ liệu

Trong module **JAVA_VERSION_JAVA18**, thay đổi **UTF-8 là charset mặc định từ Java 18** theo [JEP 400](https://openjdk.org/jeps/400) giúp nhiều API xử lý văn bản ổn định hơn giữa các môi trường. Tuy nhiên, kết quả đúng phải được chứng minh ở **ranh giới byte ↔ ký tự**: tệp, tài nguyên classpath, tiến trình con và phản hồi HTTP vẫn cần hợp đồng mã hóa của riêng chúng.

Bài thuộc chương **Kiểm chứng mã hóa** và hướng dẫn xây dựng một bộ dữ liệu kiểm thử (fixture) nhỏ nhưng đủ khả năng phát hiện các lỗi phổ biến:

- Mã hóa ASCII đúng nhưng làm hỏng tiếng Việt hay emoji.
- Đồng nhất sai hai chuỗi hiển thị gần giống nhau nhưng có các **code point** khác nhau.
- Mất dòng rỗng, tự ý loại khoảng trắng hoặc thay đổi dấu xuống dòng khi đọc/ghi.
- Ngầm dùng charset của máy, hoặc thay byte UTF-8 lỗi bằng ký tự thay thế mà không báo lỗi.

Bộ dữ liệu được xác định bằng **nội dung, thứ tự dòng, UTF-8, dấu kết thúc dòng LF (byte `0A`) và một LF ở cuối tệp**. Đây là hợp đồng kiểm thử; không phụ thuộc charset mặc định của hệ điều hành hay cấu hình IDE.

## 2. Thiết kế bộ dữ liệu có chủ đích

Hãy tạo **tám dòng dữ liệu**, đánh số từ 0. Dòng 5 thực sự rỗng, dòng 6 chứa **đúng một dấu cách**, và dòng 7 là dấu mốc giúp phát hiện dòng rỗng bị bỏ qua.

| Dòng | Loại | Giá trị mong đợi | Lỗi có thể phát hiện |
| --- | --- | --- | --- |
| 0 | ASCII | `ASCII|ABC xyz 123 !?` | Sai ký tự cơ bản hoặc dấu phân cách. |
| 1 | Tiếng Việt | `VI_NFC|Tiếng Việt: cà phê, đường phố` | Sai charset, lỗi hiển thị dấu tiếng Việt. |
| 2 | Emoji | `EMOJI|🚀 👩‍💻` | Cắt nhầm surrogate pair hoặc bỏ mất ký tự nối emoji. |
| 3 | Ký tự dựng sẵn (NFC) | `NFC|á` | Đối chiếu với cách viết tương đương ở dòng 4. |
| 4 | Ký tự tổ hợp (NFD) | `NFD|a\u0301`, tức `a` + U+0301 | Chuẩn hóa Unicode không chủ ý. |
| 5 | Dòng rỗng | Chuỗi rỗng `""` | Bị bỏ qua bởi bước lọc dòng trống. |
| 6 | Dòng có khoảng trắng | `" "` | Bị gọi nhầm là rỗng vì dùng `isBlank()` hoặc `trim()`. |
| 7 | Dấu mốc kết thúc | `END|DONE` | Phát hiện mất/chèn dòng trước đó. |

**Lưu ý về ký tự tổ hợp:** trong mã Java, `"a\u0301"` chứa hai code point: U+0061 (`a`) và U+0301 (COMBINING ACUTE ACCENT). Trong khi đó, `"á"` chứa một code point U+00E1. Hai biểu diễn có thể trông giống nhau nhưng **khác nhau khi so sánh `String.equals` và khác byte UTF-8**. `Normalizer.normalize(..., Normalizer.Form.NFC)` là một phép chuẩn hóa có chủ đích; fixture gốc phải giữ nguyên cả hai biểu diễn để kiểm thử việc bảo toàn dữ liệu.

### Các byte mốc độc lập cần biết

| Chuỗi | Các code point | Số đơn vị mã UTF-16 (`length()`) | UTF-8 dạng hex |
| --- | --- | ---: | --- |
| `A` | U+0041 | 1 | `41` |
| `á` | U+00E1 | 1 | `c3 a1` |
| `a\u0301` | U+0061, U+0301 | 2 | `61 cc 81` |
| `🚀` | U+1F680 | 2 | `f0 9f 9a 80` |
| `👩‍💻` | U+1F469, U+200D, U+1F4BB | 5 | `f0 9f 91 a9 e2 80 8d f0 9f 92 bb` |
| `""` | Không có code point | 0 | Không có byte ký tự; **dấu LF của dòng** vẫn là `0a`. |

Một emoji có thể gồm nhiều code point và được trình bày như một cụm ký tự (grapheme cluster): `👩‍💻` có ba code point nhưng thường hiển thị như một emoji ghép. Vì vậy **`String.length()`, số code point, số ký tự người dùng nhìn thấy và số byte không phải một đại lượng**.

## 3. Chọn định dạng fixture để phép thử lặp lại được

Để phép thử rõ ràng, ta dùng định dạng văn bản từng dòng với các quy tắc:

1. Byte được mã hóa theo `StandardCharsets.UTF_8`. Không ghi byte order mark (BOM) ở đầu tệp.
2. Mỗi dòng ngăn bởi ký tự LF `\n` (U+000A, byte `0A`). Không sử dụng `System.lineSeparator()` vì khác nhau giữa nền tảng.
3. Tệp có **một LF cuối cùng** sau `END|DONE`. Dòng rỗng nằm **giữa** các dòng có nội dung, giúp phân biệt một bản ghi rỗng với dấu kết thúc tệp.
4. Không gọi `trim()`, `strip()`, `filter(String::isBlank)`, hoặc chuẩn hóa NFC/NFD trong quá trình ghi/đọc fixture, bởi các thao tác ấy làm thay đổi dữ liệu đang cần kiểm thử.
5. Giữ riêng fixture hợp lệ và trường hợp byte UTF-8 **không hợp lệ**. Không chèn byte lỗi vào tệp chuẩn.

Sơ đồ quá trình kiểm tra:

```text
List<String> (8 dòng, gồm "" và " ")
      |
      | String.join("\n", rows) + "\n"
      v
String payload
      |
      | getBytes(UTF_8)
      v
byte[] kỳ vọng ---- so sánh ----> Files.readAllBytes(file)
                                        |
                                        | CharsetDecoder: REPORT
                                        v
                                   String đọc lại
                                        |
                 đối chiếu nguyên vẹn + tách dòng
                                        |
                           List<String> gồm 8 dòng
```

**Vì sao phải kiểm tra cả byte lẫn dòng?** Một bước xử lý văn bản có thể chuyển `\n` thành `\r\n`, chèn BOM hoặc thay đổi chuẩn hóa Unicode. Khi chỉ so sánh nội dung hiển thị, nhiều lỗi định dạng sẽ lọt qua. Ngược lại, chỉ đối chiếu độ dài byte không thể phát hiện mọi byte sai.

## 4. Chương trình Java 18+ tự sinh và kiểm chứng fixture

Lưu đoạn sau thành `UnicodeFixture.java` dưới UTF-8. Đây là chương trình Java độc lập, không cần thư viện bên thứ ba; các API như `HexFormat`, `Files.readString` và `CharsetDecoder` đều có sẵn trên Java 18 và các JDK hiện đại.

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;

public final class UnicodeFixture {
    private static final Path OUTPUT = Path.of("fixture-utf8-lf.txt");

    // Dòng 5 = "", dòng 6 = " " (chính xác một dấu cách).
    private static final List<String> ROWS = List.of(
            "ASCII|ABC xyz 123 !?",
            "VI_NFC|Tiếng Việt: cà phê, đường phố",
            "EMOJI|🚀 👩‍💻",
            "NFC|á",
            "NFD|a\u0301",
            "",
            " ",
            "END|DONE"
    );

    public static void main(String[] args) throws Exception {
        // Quy định LF, kể cả LF cuối tệp, thay vì newline của OS.
        String expectedText = String.join("\n", ROWS) + "\n";
        byte[] expectedBytes = expectedText.getBytes(StandardCharsets.UTF_8);

        // Ghi byte chính xác, không nhờ charset mặc định của Writer.
        Files.write(OUTPUT, expectedBytes);

        byte[] actualBytes = Files.readAllBytes(OUTPUT);
        check(Arrays.equals(expectedBytes, actualBytes),
                "Byte trên đĩa khác byte UTF-8 kỳ vọng");

        // Kiểm chứng giải mã nghiêm ngặt, không âm thầm thay byte hỏng.
        String decoded = decodeUtf8Strict(actualBytes);
        check(expectedText.equals(decoded),
                "Nội dung đọc lại khác chuỗi ban đầu");
        check(expectedText.equals(Files.readString(
                OUTPUT, StandardCharsets.UTF_8)),
                "Files.readString trả nội dung khác kỳ vọng");

        // Files.readAllLines loại ký tự kết thúc dòng, giữ dòng rỗng ở giữa.
        List<String> actualRows = Files.readAllLines(
                OUTPUT, StandardCharsets.UTF_8);
        check(ROWS.equals(actualRows),
                "Sai số lượng, thứ tự hoặc giá trị dòng");
        check(actualRows.size() == 8, "Fixture phải có 8 dòng");
        check(actualRows.get(5).isEmpty(), "Dòng 5 phải rỗng");
        check(actualRows.get(6).equals(" "),
                "Dòng 6 phải chứa đúng một dấu cách");

        // Byte-level: 8 LF, không có CR; không có BOM UTF-8 ở đầu.
        int lfCount = 0;
        for (byte b : actualBytes) {
            if (b == 0x0A) lfCount++;
            check(b != 0x0D, "Phát hiện CR, fixture phải dùng LF");
        }
        check(lfCount == ROWS.size(), "Số LF phải bằng 8");
        check(actualBytes[actualBytes.length - 1] == 0x0A,
                "Thiếu LF kết thúc tệp");
        boolean hasBom = actualBytes.length >= 3
                && (actualBytes[0] & 0xFF) == 0xEF
                && (actualBytes[1] & 0xFF) == 0xBB
                && (actualBytes[2] & 0xFF) == 0xBF;
        check(!hasBom, "Không được chèn BOM");

        checkUnicodeProperties();
        checkInvalidUtf8IsRejected();

        System.out.println("PASS: " + ROWS.size()
                + " dòng, " + actualBytes.length + " byte UTF-8");
        System.out.println("Path: " + OUTPUT.toAbsolutePath());
    }

    private static void checkUnicodeProperties() {
        String nfc = "á";
        String nfd = "a\u0301";

        check(!nfc.equals(nfd), "NFC và NFD phải khác byte/ký tự");
        check(Normalizer.normalize(nfd, Normalizer.Form.NFC).equals(nfc),
                "Hai biểu diễn phải tương đương sau chuẩn hóa NFC");

        check(hex("A").equals("41"), "ASCII sai");
        check(hex(nfc).equals("c3a1"), "UTF-8 NFC sai");
        check(hex(nfd).equals("61cc81"), "UTF-8 dấu tổ hợp sai");
        check(hex("🚀").equals("f09f9a80"), "Emoji rocket sai");
        check(hex("👩‍💻").equals("f09f91a9e2808df09f92bb"),
                "Emoji ghép sai");

        check(nfc.codePointCount(0, nfc.length()) == 1,
                "NFC phải có 1 code point");
        check(nfd.codePointCount(0, nfd.length()) == 2,
                "NFD phải có 2 code point");

        String joinedEmoji = "👩‍💻";
        check(joinedEmoji.length() == 5,
                "Emoji ghép phải có 5 đơn vị UTF-16");
        check(joinedEmoji.codePointCount(0, joinedEmoji.length()) == 3,
                "Emoji ghép phải có 3 code point");
    }

    private static String hex(String value) {
        return HexFormat.of().formatHex(
                value.getBytes(StandardCharsets.UTF_8));
    }

    private static String decodeUtf8Strict(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    private static void checkInvalidUtf8IsRejected() throws Exception {
        byte[] broken = {(byte) 0xC3, 0x28};
        try {
            decodeUtf8Strict(broken);
            throw new AssertionError("Đã chấp nhận byte UTF-8 không hợp lệ");
        } catch (CharacterCodingException expected) {
            // PASS: bộ giải mã nghiêm ngặt đã phát hiện byte lỗi.
        }
    }

    private static void check(boolean condition, String reason) {
        if (!condition) throw new AssertionError(reason);
    }
}
```

Chạy từ thư mục chứa tệp nguồn trên JDK 18 hoặc mới hơn:

```bash
javac -encoding UTF-8 UnicodeFixture.java
java UnicodeFixture
```

Chương trình tạo tệp `fixture-utf8-lf.txt` trong thư mục chạy, rồi in `PASS` kèm số dòng và số byte khi mọi điều kiện đúng. Tệp `.java` cần được lưu đúng UTF-8 để bảo toàn ký tự tiếng Việt và emoji trong mã nguồn. Tham số `-encoding UTF-8` ở lệnh biên dịch ghi rõ yêu cầu này ngay cả khi máy có cấu hình khác.

**Không dùng Java `assert` làm kiểm thử bắt buộc** nếu chưa bật `-ea`, vì các biểu thức `assert` mặc định có thể không được thực thi. Đoạn mã dùng `AssertionError` tường minh để kiểm tra luôn chạy.

### Vì sao có các phép kiểm tra khác nhau?

| Phép kiểm tra | Bảo vệ điều gì? | Điểm cần hiểu |
| --- | --- | --- |
| `Arrays.equals(expectedBytes, actualBytes)` | Byte trên đĩa trùng với định dạng kỳ vọng | Kiểm chứng ở tầng byte, gồm cả dấu xuống dòng. |
| `decodeUtf8Strict` | Dữ liệu thực sự là UTF-8 hợp lệ | `new String(bytes, UTF_8)` có thể thay các chuỗi byte lỗi bằng U+FFFD. |
| `expectedText.equals(decoded)` | Không mất hay chèn ký tự khi giải mã | Giữ nguyên thứ tự và cả dòng rỗng. |
| `Files.readAllLines(...).equals(ROWS)` | Cấu trúc đúng tám dòng | Phân biệt `""` và `" "`; bản thân phép đọc dòng không cho biết byte newline gốc. |
| Đếm byte `0A`, từ chối `0D`, kiểm tra BOM | Định dạng newline và tiền tố tệp | Tách biệt với nội dung các dòng sau khi parse. |
| So hex và `Normalizer` | Ký tự dựng sẵn và tổ hợp được giữ nguyên | Phát hiện thay đổi Unicode dù glyph có thể nhìn giống nhau. |

## 5. Các lỗi khó thấy mà fixture cần phát hiện

### 5.1. NFC và NFD không được tự ý hoán đổi

```java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Arrays;

String nfc = "á";
String nfd = "a\u0301";

System.out.println(nfc.equals(nfd)); // false
System.out.println(Arrays.equals(
        nfc.getBytes(StandardCharsets.UTF_8),
        nfd.getBytes(StandardCharsets.UTF_8))); // false
System.out.println(Normalizer.normalize(
        nfd, Normalizer.Form.NFC).equals(nfc)); // true
```

Sử dụng chuẩn hóa có chủ đích khi bài toán yêu cầu so sánh hoặc tìm kiếm văn bản tương đương về mặt Unicode. Với **kiểm thử byte nguyên vẹn**, việc chuẩn hóa tự động trước khi so sánh sẽ che giấu thay đổi dữ liệu. Nếu hệ thống có hợp đồng chuẩn hóa NFC, hãy tạo thêm phép thử cho hợp đồng đó, nhưng vẫn giữ fixture gốc để biết byte đầu vào đã bị biến đổi ở đâu.

### 5.2. Dòng rỗng khác dòng chỉ chứa khoảng trắng và khác EOF

```java
"".isEmpty();      // true
" ".isEmpty();     // false
" ".isBlank();     // true
```

Khi đọc dòng, `readLine()` trả `""` cho **một dòng rỗng đang tồn tại** và trả `null` khi đã gặp EOF. Không được viết `if (line.isBlank()) continue;` nếu định dạng cho phép dòng rỗng hoặc khoảng trắng có ý nghĩa.

Trong fixture, các dòng 5 và 6 nằm giữa những dòng mang dữ liệu, nên nếu một bước xử lý loại bỏ một dòng thì vị trí của `END|DONE` sẽ dịch chuyển, khiến kiểm tra danh sách thất bại. Lưu ý phương thức `Files.readAllLines` **loại các ký tự kết thúc dòng**: để bảo toàn đúng số lượng và kiểu newline ban đầu, vẫn phải kiểm tra `byte[]` hoặc chuỗi thô.

### 5.3. Dấu xuống dòng phụ thuộc nền tảng

```java
String portable = String.join("\n", List.of("A", "", "B")) + "\n";
// Byte UTF-8 kỳ vọng: 41 0a 0a 42 0a
```

Không dùng `System.lineSeparator()` trong dữ liệu chuẩn mà định dạng đã quy định LF. Trên một số máy, lời gọi đó có thể sinh CRLF (`0D 0A`), khiến cùng một test cho ra các file byte khác nhau. Khi thực tế cần chấp nhận cả LF lẫn CRLF, hãy viết **hai fixture riêng với kết quả mong đợi riêng**; đừng vô tình chuẩn hóa rồi bỏ qua sai khác.

### 5.4. Không đo kích thước byte bằng `String.length()`

```java
String rocket = "🚀";
System.out.println(rocket.length());                 // 2 đơn vị UTF-16
System.out.println(rocket.codePointCount(0, 2));    // 1 code point
System.out.println(rocket.getBytes(
        StandardCharsets.UTF_8).length);             // 4 byte
```

Mọi kích thước khai báo theo byte trong giao thức hay định dạng tệp phải dựa trên **byte sau khi encode**. Kể cả ASCII, phép tính `String.length()` chỉ tình cờ bằng số byte UTF-8 nếu nội dung thuần ASCII.

### 5.5. Mã hóa sai nhưng phép thử nội dung vẫn “có vẻ đúng”

Không đủ để ghi rồi đọc bằng **cùng một charset sai**: hai đầu có thể hoàn nguyên lại cùng một chuỗi trong môi trường thử nhưng không đáp ứng hợp đồng dữ liệu với hệ thống bên ngoài. Fixture vì thế nên chứa **byte mốc độc lập** (như `c3a1`, `61cc81` và `f09f9a80`), cùng yêu cầu UTF-8 tường minh, để kiểm tra điều kiện của chuẩn đầu ra.

Nếu đang nhận byte từ đối tác, hãy kiểm tra chính byte đầu vào bằng `CharsetDecoder` với `CodingErrorAction.REPORT`. Một chuỗi đã bị thay bằng ký tự `�` không thể dùng để khôi phục byte lỗi ban đầu; lỗi phải được phát hiện trước hoặc tại điểm giải mã.

## 6. Tái sử dụng cùng fixture tại các ranh giới

Bộ dữ liệu này hữu ích nhất khi được sử dụng **nguyên vẹn ở nhiều nơi**. Giá trị chuẩn để đối chiếu luôn là `expectedText` và `expectedBytes` tạo từ mã ở mục 4.

| Ranh giới | Cách đưa fixture qua ranh giới | Bằng chứng cần so sánh |
| --- | --- | --- |
| Tệp | Dùng `Files.write(path, expectedBytes)`, sau đó `Files.readAllBytes(path)` | Byte đầu ra, BOM và LF khớp; các dòng không bị cắt. |
| Classpath/JAR | Đóng gói file fixture làm resource, mở bằng `Class.getResourceAsStream(...)` | Byte resource khớp byte đã chuẩn bị; không tự đổi encoding khi build. |
| Tiến trình con | Cho chương trình con xuất đúng byte fixture lên `stdout`; cha đọc `Process.getInputStream()` | Byte pipe khớp. Kiểm soát `stderr` để tránh pipe đầy. |
| HTTP | Server trả byte fixture, chẳng hạn `text/plain; charset=utf-8`; client dùng `BodyHandlers.ofByteArray()` | Nội dung byte và metadata khớp; không dùng độ dài `String` cho kích thước body. |

Nếu phải dùng định dạng có chuyển đổi riêng (chẳng hạn JSON escape, HTTP nén, tệp CSV có quy ước dòng), xác định **byte kỳ vọng sau chuyển đổi theo đúng định dạng đó**. Không so trực tiếp byte giữa hai lớp dữ liệu khác nhau. Dữ liệu fixture gốc vẫn dùng để đối chiếu kết quả giải mã sau khi xử lý lớp vận chuyển.

## 7. Bài thực hành mở rộng có tiêu chí đạt rõ ràng

1. **Kiểm thử tiếng Việt:** sửa chữ `đường` trong dòng 1, sinh lại fixture và đối chiếu UTF-8 bằng cả chuỗi giải mã lẫn byte. Thử giải mã bằng charset không đúng để quan sát lỗi và ghi rõ nguyên nhân.
2. **Kiểm thử Unicode tổ hợp:** thay `NFD|a\u0301` thành `NFD|á` nhưng giữ byte mốc của dạng NFD. Phép kiểm tra byte phải thất bại; chỉ phép so sánh **sau khi chuẩn hóa NFC** mới cho kết quả tương đương.
3. **Kiểm thử dòng rỗng:** loại bỏ dòng `""` hoặc thay dòng `" "` bằng `""`. Kiểm tra cấu trúc tám dòng phải thất bại. Thay `\n` bằng `\r\n`: phép kiểm tra byte newline phải thất bại.
4. **Kiểm thử byte hỏng:** đưa byte `c3 28` vào bộ giải mã nghiêm ngặt. Kết quả đúng là ném `CharacterCodingException`; byte lỗi này không thuộc fixture hợp lệ.
5. **Kiểm thử nhiều môi trường:** chạy cùng chương trình trên JDK hiện đại ở hai hệ điều hành khác nhau; byte UTF-8/LF của file kết quả phải trùng nhau, ngay cả khi ký tự được hiển thị khác nhau bởi font hoặc terminal.

**Điều kiện hoàn thành:** bạn có một fixture xác định gồm ASCII, tiếng Việt, emoji, cả hai dạng NFC/NFD, dòng rỗng và dòng chỉ chứa dấu cách; chương trình sinh và đọc lại giữ đúng byte UTF-8, tám dòng và tám LF; phép thử từ chối byte lỗi và làm lộ thay đổi Unicode không chủ ý. Đây là nền tảng hữu ích để kiểm chứng tác động của UTF-8 mặc định từ Java 18 trên những JDK hiện đại, thay vì phụ thuộc vào cách hiển thị của console.

**Tài liệu tham khảo:** [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400), [Java `Normalizer` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html), [Unicode Normalization Forms (UAX #15)](https://www.unicode.org/reports/tr15/).
