# Kiểm tra round-trip bằng cả chuỗi và byte để phát hiện mất dữ liệu

## 1. Mục tiêu: chứng minh dữ liệu đi qua ranh giới mà không bị mất

Trong module **JAVA_VERSION_JAVA18**, Java 18 chuẩn hóa UTF-8 thành charset mặc định của các API chịu ảnh hưởng bởi [JEP 400](https://openjdk.org/jeps/400). Thay đổi này vẫn hữu ích trên các JDK hiện đại, nhưng **UTF-8 mặc định không bảo đảm rằng byte từ tệp, tài nguyên classpath, tiến trình con hoặc HTTP đã được tạo bằng UTF-8**. Vì vậy, khi kiểm tra một luồng xử lý văn bản, ta cần xác minh **hợp đồng mã hóa** và những phép chuyển đổi thực tế.

Bài thuộc chương **Kiểm chứng mã hóa** và tập trung vào kỹ thuật **round-trip (đi rồi quay về)**:

- **Kiểm tra chuỗi:** văn bản sau khi mã hóa, truyền/lưu và giải mã có bằng chính xác văn bản đầu vào không?
- **Kiểm tra byte:** dãy byte được lưu/truyền có bằng dãy byte kỳ vọng không, và khi giải mã rồi mã hóa lại có giữ nguyên từng byte không?
- **Kiểm tra tính hợp lệ:** byte đầu vào có giải mã được theo charset đã thỏa thuận không? Chuỗi đầu vào có mã hóa được mà không thay thế ký tự lỗi không?
- **Kiểm tra độc lập:** so sánh với chuỗi chuẩn hoặc các vector byte chuẩn đã biết, tránh hai bước sai nhưng triệt tiêu lỗi của nhau.

Ở đây, “bảo toàn” được định nghĩa theo yêu cầu: **bảo toàn văn bản** đòi hỏi cùng dãy đơn vị mã Unicode trong Java `String`; **bảo toàn byte** đòi hỏi mọi byte giống hệt, kể cả BOM và dấu xuống dòng. Có hệ thống chỉ yêu cầu tương đương ngữ nghĩa, nhưng khi mục tiêu là phát hiện mất dữ liệu, phải bắt đầu từ so sánh nghiêm ngặt, rồi mới cân nhắc những chuyển đổi được hợp đồng cho phép.

## 2. Hai loại round-trip và bốn kết quả có thể quan sát

### 2.1. Round-trip bắt đầu bằng chuỗi

```text
String gốc S
   │
   ├── encode bằng charset C ───> byte[] B
   │                               │
   │                               ├── ghi vào tệp / HTTP / pipe / tài nguyên
   │                               │
   │                               └── byte[] B' đọc từ đích
   │                                       │
   │                               decode bằng charset C
   │                                       │
   └────────────────────────────> String S'
```

Điều kiện cần kiểm tra:

- `S.equals(S')`: **chuỗi** giữ nguyên, bao gồm dấu tiếng Việt, emoji, ký tự tổ hợp và khoảng trắng.
- `Arrays.equals(B, B')`: byte ở đích giống byte tạo ra từ chuỗi gốc.
- `Arrays.equals(B', encode(S', C))`: giải mã và mã hóa lại không làm thay đổi byte đã nhận.

Nên kiểm tra cả ba điều kiện, vì một bước xử lý trung gian có thể đổi định dạng byte nhưng khi parse lại vẫn cho kết quả nhìn “đúng”.

### 2.2. Round-trip bắt đầu bằng byte

```text
byte[] gốc B ── decode nghiêm ngặt (C) ──> String S
    ^                                          │
    └──────────────── encode nghiêm ngặt (C) ──┘
                       byte[] B'
```

Điều kiện `Arrays.equals(B, B')` chứng minh những byte **hợp lệ theo charset C** được bảo toàn qua việc giải mã rồi mã hóa lại. Tuy nhiên, phép thử này **không xác nhận charset C đúng với ý nghĩa của dữ liệu** nếu bạn tự chọn nhầm C. Cần thêm văn bản chuẩn hoặc hợp đồng bên phát.

Ví dụ byte UTF-8 `c3 a9` biểu diễn ký tự `é`. Nếu nhầm giải mã bằng ISO-8859-1 thì được chuỗi `Ã©`; mã hóa chuỗi sai đó trở lại ISO-8859-1 vẫn cho đúng hai byte `c3 a9`. **Round-trip byte có thể đạt trong khi văn bản sai.**

### 2.3. Ma trận chẩn đoán

| So chuỗi với `S` chuẩn | So byte với `B` chuẩn | Cách diễn giải |
| --- | --- | --- |
| Bằng | Bằng | Đạt cả hai hợp đồng đang kiểm tra. |
| Bằng | Khác | Văn bản vẫn được hiểu đúng nhưng định dạng byte thay đổi, ví dụ chuyển UTF-8 sang charset khác, thay newline hoặc thêm/xóa BOM ở lớp xử lý trước khi so chuỗi. |
| Khác | Bằng | Cùng byte nhưng cách giải mã/diễn giải khác nhau; kiểm tra charset, decoder và tầng parse. |
| Khác | Khác | Có thay đổi cả văn bản và dữ liệu byte; khoanh vùng theo từng ranh giới. |

Ma trận chỉ có ý nghĩa khi `S` chuẩn, `B` chuẩn và đường giải mã được xác định rõ. Nếu tạo “giá trị kỳ vọng” từ chính dữ liệu đã bị xử lý sai thì hai phép so sánh có thể cùng báo đạt.

## 3. Dữ liệu chuẩn có thể bắt các lỗi khó thấy

Dùng một fixture mang đủ loại ký tự và cấu trúc dòng:

```java
import java.util.List;

String original = String.join("\n", List.of(
        "ASCII|Hello 123",
        "VI|Tôi đang học Java 18",
        "NFC|é",
        "NFD|e\u0301",
        "EMOJI|🚀",
        "",             // Dòng thực sự rỗng
        " ",            // Dòng chứa một dấu cách
        "END|OK"
)) + "\n";             // LF cuối tệp, bất kể hệ điều hành
```

Quy tắc của fixture:

1. Charset là **`StandardCharsets.UTF_8`**; không có BOM.
2. Tám dòng theo thứ tự ghi trong mã; dòng thứ sáu (`index 5`) rỗng, dòng tiếp theo (`index 6`) chứa một dấu cách.
3. Tất cả dấu kết thúc dòng là LF `\n` (byte `0a`); có một LF sau `END|OK`.
4. `"NFC|é"` dùng U+00E9 và `"NFD|e\u0301"` dùng U+0065 kết hợp U+0301. Hai biểu diễn Unicode **không có cùng byte**, dù phần chữ sau tiền tố có thể nhìn giống nhau.
5. Mọi phép chuẩn hóa hoặc chuyển đổi dòng phải được ghi nhận riêng; không tự động `strip()`, `trim()` hoặc `Normalizer.normalize()` trước khi so sánh.

Một vài **vector byte độc lập** để phát hiện hợp đồng charset bị dùng sai:

| Đầu vào | UTF-8 dạng hex | Ý nghĩa |
| --- | --- | --- |
| `A` | `41` | ASCII đơn giản. |
| `é` (U+00E9) | `c3 a9` | Ký tự dựng sẵn. |
| `e\u0301` (U+0065, U+0301) | `65 cc 81` | Chữ và dấu kết hợp. |
| `🚀` (U+1F680) | `f0 9f 9a 80` | Code point ngoài BMP, hai đơn vị mã UTF-16. |
| `\n` | `0a` | Một dòng kết thúc bằng LF. |
| `\r\n` | `0d 0a` | Hai byte CRLF, khác LF. |

Với nội dung `"🚀"`, `String.length()` trả **2**, `codePointCount(0, length())` trả **1** còn số byte UTF-8 là **4**. Không dùng độ dài `String` thay số byte của giao thức hoặc file.

## 4. Bộ kiểm chứng hoàn chỉnh trên Java 18+

Đoạn sau là một lớp độc lập, sử dụng API còn phù hợp trên các JDK hiện đại. Chương trình vừa tạo một tệp UTF-8/LF, vừa thử chuỗi → byte → chuỗi và byte → chuỗi → byte; kiểm tra thêm các lỗi không được bỏ qua. Lưu mã thành `RoundTripAudit.java` bằng UTF-8.

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;

public final class RoundTripAudit {
    private static final Path FILE = Path.of("roundtrip-utf8-lf.txt");

    public static void main(String[] args) throws Exception {
        String original = String.join("\n", List.of(
                "ASCII|Hello 123",
                "VI|Tôi đang học Java 18",
                "NFC|é",
                "NFD|e\u0301",
                "EMOJI|🚀",
                "",
                " ",
                "END|OK"
        )) + "\n";

        // Golden bytes: hợp đồng đầu ra là UTF-8, không BOM và dùng LF.
        byte[] expected = encodeUtf8Strict(original);
        Files.write(FILE, expected);

        // Ranh giới tệp: đối chiếu BYTE đọc từ đích với BYTE kỳ vọng.
        byte[] actual = Files.readAllBytes(FILE);
        requireSameBytes("File", expected, actual);

        // Chiều 1: String -> UTF-8 -> String; so sánh toàn bộ String.
        String restored = decodeUtf8Strict(actual);
        require(original.equals(restored),
                "Mất hoặc đổi ký tự qua ranh giới tệp");

        // Chiều 2: UTF-8 bytes -> String -> UTF-8 bytes.
        byte[] encodedAgain = encodeUtf8Strict(restored);
        requireSameBytes("Decode/encode", actual, encodedAgain);

        // Các vector byte đã biết, độc lập với file mới tạo.
        requireHex("A", "41");
        requireHex("é", "c3a9");
        requireHex("e\u0301", "65cc81");
        requireHex("🚀", "f09f9a80");

        // Cấu trúc dòng và dấu cách cũng là dữ liệu.
        List<String> lines = Files.readAllLines(FILE, StandardCharsets.UTF_8);
        require(lines.size() == 8, "Phải có đúng 8 dòng");
        require(lines.get(5).isEmpty(), "Mất dòng rỗng");
        require(lines.get(6).equals(" "), "Mất dòng một dấu cách");
        int lfCount = 0;
        for (byte b : actual) {
            if (b == 0x0A) lfCount++;
            require(b != 0x0D, "Phát hiện CR thay vì LF");
        }
        require(lfCount == 8 && actual[actual.length - 1] == 0x0A,
                "Sai số lượng LF hoặc mất LF cuối tệp");
        require(!startsWithUtf8Bom(actual), "Tệp có BOM ngoài hợp đồng");

        // Chuẩn hóa Unicode và CRLF là thay đổi byte có thể đo được.
        String normalized = Normalizer.normalize(
                original, Normalizer.Form.NFC);
        require(!Arrays.equals(expected, encodeUtf8Strict(normalized)),
                "Bất ngờ không phát hiện thay đổi NFC");
        require(!Arrays.equals(expected,
                        encodeUtf8Strict(original.replace("\n", "\r\n"))),
                "Bất ngờ không phát hiện thay đổi LF/CRLF");

        // Hai lỗi đầu vào phải bị từ chối, không âm thầm thay ký tự.
        expectInvalidUtf8();
        expectInvalidUtf16();

        // Round-trip byte đạt nhưng charset sai: cần chuỗi chuẩn.
        byte[] utf8EAcute = HexFormat.of().parseHex("c3a9");
        String wrong = new String(utf8EAcute, StandardCharsets.ISO_8859_1);
        require(Arrays.equals(utf8EAcute,
                wrong.getBytes(StandardCharsets.ISO_8859_1)),
                "Ví dụ cần bảo toàn byte theo charset sai");
        require(!wrong.equals("é"),
                "Ví dụ cần cho thấy văn bản sai dù byte giống");

        System.out.println("PASS: bảo toàn chuỗi và "
                + actual.length + " byte UTF-8 qua " + FILE);
    }

    private static String decodeUtf8Strict(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString();
    }

    private static byte[] encodeUtf8Strict(String value)
            throws CharacterCodingException {
        ByteBuffer encoded = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(value));

        byte[] bytes = new byte[encoded.remaining()];
        encoded.get(bytes);
        return bytes;
    }

    private static void requireHex(String text, String expectedHex)
            throws CharacterCodingException {
        String actualHex = HexFormat.of().formatHex(encodeUtf8Strict(text));
        require(actualHex.equals(expectedHex),
                "Sai UTF-8 của " + text + ": " + actualHex);
    }

    private static boolean startsWithUtf8Bom(byte[] bytes) {
        return bytes.length >= 3
                && (bytes[0] & 0xFF) == 0xEF
                && (bytes[1] & 0xFF) == 0xBB
                && (bytes[2] & 0xFF) == 0xBF;
    }

    private static void requireSameBytes(
            String where, byte[] expected, byte[] actual) {
        int i = Arrays.mismatch(expected, actual);
        if (i >= 0) {
            throw new AssertionError(where + " khác ở byte offset " + i
                    + " (expected=" + byteAt(expected, i)
                    + ", actual=" + byteAt(actual, i) + ")"
                    + "; lengths=" + expected.length + "/" + actual.length);
        }
    }

    private static String byteAt(byte[] array, int index) {
        return index >= array.length ? "<EOF>"
                : "0x" + HexFormat.of().toHexDigits(array[index]);
    }

    private static void expectInvalidUtf8() throws Exception {
        byte[] broken = {(byte) 0xC3, 0x28};
        try {
            decodeUtf8Strict(broken);
            throw new AssertionError("Đã chấp nhận UTF-8 lỗi");
        } catch (CharacterCodingException expected) {
            // PASS: c3 28 là chuỗi byte UTF-8 không hợp lệ.
        }
    }

    private static void expectInvalidUtf16() throws Exception {
        // U+D800 đứng một mình: high surrogate không có low surrogate.
        String broken = String.valueOf((char) 0xD800);
        try {
            encodeUtf8Strict(broken);
            throw new AssertionError("Đã mã hóa surrogate lẻ");
        } catch (CharacterCodingException expected) {
            // PASS: tránh thay dấu ? hoặc byte thay thế một cách im lặng.
        }
    }

    private static void require(boolean valid, String reason) {
        if (!valid) throw new AssertionError(reason);
    }
}
```

Biên dịch và chạy tại thư mục chứa mã nguồn:

```bash
javac -encoding UTF-8 RoundTripAudit.java
java RoundTripAudit
```

Khi đạt, chương trình in `PASS`, số byte thực tế và đường dẫn tương đối của fixture đã ghi. Nếu sai, `AssertionError` hoặc `CharacterCodingException` xuất hiện ngay tại phép kiểm tra. Với `requireSameBytes`, thông báo có **offset byte đầu tiên khác** và giá trị ở hai phía, giúp xác định sai lệch ở đâu trong luồng xử lý. Đây là một ví dụ học tập; khi tích hợp vào dự án, nên dùng framework test và quản lý tệp tạm theo cơ chế của dự án.

### 4.1. Vì sao dùng `CharsetDecoder` và `CharsetEncoder` nghiêm ngặt?

Các lời gọi thuận tiện:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
byte[] output = text.getBytes(StandardCharsets.UTF_8);
```

có thể **thay thế dữ liệu không biểu diễn hợp lệ** thay vì ném lỗi:

- Trong chiều byte → chuỗi, `new String(bytes, UTF_8)` thay các chuỗi UTF-8 hỏng bằng U+FFFD (`�`). Ví dụ `c3 28` có thể trở thành `�(`; mã hóa lại không thể khôi phục hai byte gốc.
- Trong chiều chuỗi → byte, một `String` chứa **surrogate lẻ** (ví dụ U+D800 không có low surrogate theo sau) không biểu diễn một code point Unicode hợp lệ. `getBytes(UTF_8)` thường thay dữ liệu lỗi khi mã hóa.

Bởi vậy, trong bài kiểm chứng **mất dữ liệu**, đặt `CodingErrorAction.REPORT` cho cả decoder và encoder. Nếu luồng xử lý cho phép thay ký tự lỗi theo một chính sách xác định, cần kiểm thử chính sách thay thế đó như một kết quả **có chủ đích**, đồng thời lưu byte gốc để điều tra.

### 4.2. Vì sao cần byte chuẩn bên ngoài round-trip?

`expected = encodeUtf8Strict(original)` và `encodedAgain = encodeUtf8Strict(restored)` đều dựa vào encoder đang chạy. Chỉ cần hai bên dùng nhất quán một charset sai, phép byte → chuỗi → byte có thể vẫn đạt.

Các vector `é → c3 a9`, `e\u0301 → 65 cc 81` và `🚀 → f0 9f 9a 80` là các giá trị UTF-8 **đã biết trước**. Chúng cung cấp điểm kiểm tra độc lập; còn khi tích hợp hệ thống thật, cần có **golden file/byte mẫu** do hợp đồng định dạng quy định. Nếu API đối tác chỉ giao byte đầu vào mà không có văn bản chuẩn, bạn chỉ có thể xác nhận byte là UTF-8 hợp lệ và round-trip không mất byte; **không thể tự chứng minh nội dung được phía phát hiểu đúng**.

## 5. Các phản ví dụ: round-trip đạt vẫn có thể mất dữ liệu

### 5.1. Byte giữ nguyên nhưng chuỗi hỏng

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

byte[] utf8Bytes = HexFormat.of().parseHex("c3a9"); // "é" trong UTF-8
String wrongText = new String(
        utf8Bytes, StandardCharsets.ISO_8859_1);    // "Ã©"
byte[] roundTrip = wrongText.getBytes(StandardCharsets.ISO_8859_1);

System.out.println(Arrays.equals(utf8Bytes, roundTrip)); // true
System.out.println(wrongText.equals("é"));                // false
```

Do đó phải so chuỗi với **nguồn tin cậy** và biết charset đầu phát. Đừng dùng kết quả `Arrays.equals` để kết luận văn bản đã được giải mã đúng.

### 5.2. Chuỗi có thể “giống về mặt nhìn thấy” nhưng byte khác

```java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Arrays;

String composed = "é";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed)); // false
System.out.println(Arrays.equals(
        composed.getBytes(StandardCharsets.UTF_8),
        decomposed.getBytes(StandardCharsets.UTF_8))); // false
System.out.println(Normalizer.normalize(
        decomposed, Normalizer.Form.NFC).equals(composed)); // true
```

Chuẩn hóa NFC/NFD hữu ích trong xử lý văn bản nhưng **là một phép chuyển đổi**. Nếu định dạng yêu cầu bảo toàn byte, phải báo việc thay đổi; nếu hợp đồng yêu cầu chuẩn hóa NFC, hãy **chuẩn hóa ở bước được chỉ định** và so với bộ dữ liệu kỳ vọng sau bước đó.

### 5.3. Dữ liệu rỗng hoặc khoảng trắng bị loại bỏ

```java
"".isEmpty();  // true
" ".isEmpty(); // false
" ".isBlank(); // true
```

Các thao tác `trim()`, `strip()`, `filter(String::isBlank)` có thể khiến dữ liệu không được giữ nguyên. Sự khác biệt giữa `""` và `" "` dễ bị che giấu khi log. Với nội dung theo dòng, hãy kiểm tra **số dòng, vị trí dòng rỗng và byte newline**; `Files.readAllLines` không cho biết newline ban đầu là LF hay CRLF vì ký tự kết thúc dòng đã bị bỏ.

### 5.4. Văn bản đọc lại giống nhau, byte xuống dòng không giống nhau

Hai tệp chứa:

```text
41 0a 42 0a       # "A\nB\n" dùng LF
41 0d 0a 42 0d 0a # "A\r\nB\r\n" dùng CRLF
```

đều có thể cho danh sách dòng `["A", "B"]` qua `Files.readAllLines`, nhưng byte khác nhau. Nếu hợp đồng yêu cầu LF, phải so byte thô. Trường hợp khác tương tự là BOM UTF-8 `ef bb bf` ở đầu tệp: một lớp đọc có thể loại bỏ BOM trước khi chuyển cho ứng dụng và làm mất thông tin về tệp nguồn.

### 5.5. Round-trip văn bản đạt nhưng sai định dạng truyền

Giả sử phía gửi và nhận đều dùng UTF-16 cho một chuỗi tiếng Việt, `S.equals(S')` có thể đúng, song giao thức lại yêu cầu UTF-8. Khi đó byte truyền khác byte theo hợp đồng. Cần kiểm tra `B` ở chính **ranh giới vận chuyển**, không chỉ chuỗi sau giải mã.

## 6. Áp dụng cùng nguyên lý ở bốn ranh giới

| Ranh giới | Lấy byte thô ở đâu? | Lấy chuỗi so sánh ở đâu? | Sai lệch cần chú ý |
| --- | --- | --- | --- |
| **Tệp** | `Files.readAllBytes(path)` | `decodeUtf8Strict(bytes)` hoặc reader đã cam kết charset | BOM, CRLF, tệp cũ không phải UTF-8, cắt dữ liệu. |
| **Classpath/JAR** | `getResourceAsStream(...).readAllBytes()` | Giải mã bằng charset tài nguyên quy định | Công cụ build đổi mã hóa, nhầm đường dẫn tài nguyên, tự xử lý `.properties` khác quy tắc. |
| **Tiến trình con** | `Process.getInputStream()` và `getErrorStream()` | Giải mã mỗi pipe theo hợp đồng của chương trình con | Locale/charset riêng, `stderr` bị bỏ quên gây treo, đầu ra có cả byte nhị phân. |
| **HTTP** | `HttpResponse.BodyHandlers.ofByteArray()` | Giải mã sau các lớp vận chuyển theo `Content-Type`/định dạng | Sai `charset`, byte body bị biến đổi, nén `Content-Encoding`, độ dài byte khác số ký tự. |

Khi kiểm tra qua HTTP có nén, phải xác định liệu đang so **byte của body đã giải nén** hay **byte truyền có nén**, bởi hai tầng có hợp đồng khác nhau. Với JSON, parser có thể chuyển escape (`"\u00e9"`) thành ký tự `é`; hai payload JSON có thể tương đương về dữ liệu nhưng khác byte. Bài kiểm tra phải chỉ rõ đang so **ngữ nghĩa JSON** hay **byte payload**.

Tương tự, `Charset.defaultCharset()` từ Java 18 thông thường là UTF-8, nhưng không quyết định charset của mọi tệp có sẵn, chương trình ngoài hoặc giao thức. Viết `StandardCharsets.UTF_8` tại điểm ranh giới nếu định dạng thật sự là UTF-8. Với định dạng khác, dùng đúng charset được hợp đồng chỉ định.

## 7. Quy trình xác định vị trí mất dữ liệu

Khi phép kiểm tra thất bại, đừng chỉ in cả chuỗi dài ra console, vì terminal có thể hiển thị không đúng. Hãy chẩn đoán theo thứ tự:

1. **Chốt nguồn chuẩn:** ghi nhận chuỗi chuẩn, charset, yêu cầu BOM, quy tắc LF/CRLF, chuẩn hóa Unicode và byte mẫu tin cậy.
2. **Chụp byte trước và sau từng ranh giới:** bằng `Files.readAllBytes`, input stream của process, HTTP byte body hoặc resource stream. Dùng `HexFormat` hay digest để đối chiếu; digest giúp nhận biết khác biệt nhưng không cho vị trí byte sai.
3. **Đọc bằng decoder nghiêm ngặt:** nếu gặp `CharacterCodingException`, báo lỗi tại chính ranh giới chứa byte không hợp lệ; không tiếp tục dựa vào chuỗi đã được thay `�`.
4. **So chuỗi nguyên vẹn:** `String.equals` và khi cần thì liệt kê các code point bằng `String.codePoints()` để phân biệt dấu tổ hợp, ký tự ngoài BMP hoặc ký tự vô hình.
5. **So byte và offset sai đầu tiên:** `Arrays.mismatch` chỉ ra vị trí khác; kiểm tra BOM đầu tệp, `0d 0a` thay `0a`, byte bị cắt, hoặc charset khác.
6. **Xác minh phép chuyển đổi được phép:** nếu chuẩn hóa hoặc canonicalization là yêu cầu, so hai phiên bản theo **đúng từng giai đoạn**, không che giấu việc đổi byte bằng cách chỉ kiểm tra văn bản cuối cùng.

Ví dụ log gọn cho byte và code point mà không lệ thuộc vào font terminal:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String value = "e\u0301🚀";
String bytesHex = HexFormat.of().formatHex(
        value.getBytes(StandardCharsets.UTF_8));
String codePoints = value.codePoints()
        .mapToObj(cp -> String.format("U+%04X", cp))
        .reduce((a, b) -> a + " " + b)
        .orElse("(empty)");
System.out.println("bytes=" + bytesHex);
System.out.println("codePoints=" + codePoints);
// bytes=65cc81f09f9a80
// codePoints=U+0065 U+0301 U+1F680
```

## 8. Bài thực hành và tiêu chí đánh giá

1. **Mất dữ liệu ở chiều decode:** lấy byte `c3 28`, thử `new String(bytes, UTF_8)` và `decodeUtf8Strict(bytes)`. Đối chiếu chuỗi nhận được, byte sau mã hóa lại và ngoại lệ. Kết quả mong đợi: decoder nghiêm ngặt từ chối byte lỗi.
2. **Mất dữ liệu ở chiều encode:** tạo `String.valueOf((char) 0xD800)`, thử `getBytes(UTF_8)` và `encodeUtf8Strict`. Kết quả mong đợi: encoder nghiêm ngặt từ chối surrogate lẻ.
3. **Chuẩn hóa không chủ ý:** thay `e\u0301` thành `é` trong fixture. Phép so byte nguyên vẹn phải báo khác; kiểm tra chuẩn hóa NFC có thể cho cùng dạng sau chuẩn hóa, nếu đó là điều hợp đồng cho phép.
4. **Thay newline:** đổi LF thành CRLF. `Files.readAllLines` có thể còn trả cùng danh sách dòng, nhưng so byte và kiểm tra LF/CR phải báo lỗi.
5. **Sai charset nhưng byte round-trip đạt:** đưa byte `c3 a9` qua decoder và encoder ISO-8859-1. Xác nhận byte giữ nguyên nhưng chuỗi khác `é`, rồi sửa decoder sang UTF-8.
6. **Đổi kênh vận chuyển:** dùng tệp chuẩn làm resource classpath, nội dung `stdout` của một tiến trình con hoặc HTTP body. Kiểm tra cả byte và chuỗi ở mỗi điểm; ghi rõ charset do ai quyết định.

**Tiêu chí hoàn thành:** bạn phát hiện được ít nhất ba dạng sai lệch khác nhau (byte lỗi, Unicode bị chuẩn hóa và newline bị thay đổi), giải thích được một trường hợp **byte round-trip đạt nhưng chuỗi sai**, và chỉ ra bằng chứng byte lẫn chuỗi tại mỗi ranh giới. Đây là cách kiểm chứng **bảo toàn dữ liệu thực tế** khi sử dụng thay đổi UTF-8 mặc định của Java 18 trên các JDK hiện đại.

### Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): phạm vi và tác động của UTF-8 mặc định từ Java 18.
- [Java SE `CharsetDecoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html) và [`CharsetEncoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html): giải mã/mã hóa với chính sách báo lỗi.
- [Java SE `Arrays.mismatch`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html): xác định offset đầu tiên khác nhau.
- [Unicode Standard Annex #15 — Normalization Forms](https://www.unicode.org/reports/tr15/): ý nghĩa NFC, NFD và các dạng chuẩn hóa.
