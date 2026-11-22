# Kiểm thử vòng đọc ghi, nội dung rỗng và dữ liệu Unicode — tệp văn bản Java 11

## Mục tiêu học tập

Một thao tác ghi tệp không ném ngoại lệ chưa đủ để kết luận dữ liệu được bảo toàn. Lỗi thường xuất hiện ở **byte mã hóa**, **dấu xuống dòng**, **ghi đè nội dung cũ**, **trường hợp tệp rỗng**, và dữ liệu Unicode mà màn hình hiển thị khó phân biệt.

Bài này trình bày cách xây dựng bộ kiểm thử **round trip** (*ghi → đọc lại → so sánh*) cho tệp văn bản nhỏ bằng API Java 11 vẫn còn được hỗ trợ ở các JDK hiện hành. Sau khi hoàn thành, bạn có thể:

- Phân biệt tệp chưa tồn tại, tệp 0 byte, tệp chỉ chứa khoảng trắng và tệp có dòng trống.
- Kiểm tra cả giá trị `String` sau đọc, **byte UTF-8 thực tế**, kích thước tệp và hành vi ghi đè/append.
- Bảo toàn tiếng Việt có dấu, dạng Unicode NFC/NFD, ký tự bổ sung ngoài BMP, non-breaking space và zero-width space.
- Kiểm tra dấu xuống dòng **LF, CRLF, CR** và ký tự xuống dòng ở cuối tệp.
- Tạo fixture UTF-8 bị hỏng để xác minh xử lý lỗi giải mã, đồng thời xác định chính sách cho UTF-8 BOM.
- Dùng tệp tạm và điều kiện kiểm tra tự chạy để test được trong CI, không cần thư viện ngoài JDK.

## 1. Hợp đồng đọc/ghi văn bản trên Java 11

### 1.1. `Files.writeString` và `Files.readString`

Hai API được giới thiệu ở Java 11:

~~~java
// Doan minh hoa: can imports va xu ly IOException.
Files.writeString(path, text, StandardCharsets.UTF_8);
String readBack = Files.readString(path, StandardCharsets.UTF_8);
~~~

Các overload **không có tham số charset** cũng dùng **UTF-8**:

~~~java
Files.writeString(path, text);
String readBack = Files.readString(path);
~~~

`Files.writeString(Path, CharSequence, Charset, OpenOption...)` chuyển ký tự thành bytes theo charset đã chọn. `Files.readString(Path, Charset)` giải mã bytes thành chuỗi. Đọc và ghi dùng chung charset **đúng theo hợp đồng file**: với văn bản UTF-8, chọn rõ `StandardCharsets.UTF_8`; tránh dựa vào encoding mặc định của hệ điều hành, editor hay terminal.

`Files.writeString` ghi chính xác các ký tự được cung cấp, kể cả dấu phân tách dòng; không tự thêm newline cuối tệp. `Files.readString` giữ các dấu phân tách dòng hiện có. Cả hai làm việc với toàn bộ nội dung, phù hợp với các tệp văn bản nhỏ hoặc kích thước có thể tải trọn vào bộ nhớ. Đối với tệp lớn, nên chuyển sang xử lý theo luồng và viết các bài test tương ứng.

### 1.2. Tạo mới, ghi đè và nối thêm

Mặc định khi **không truyền `OpenOption`**, `Files.writeString` hành xử như có ba option:

- `CREATE` — tạo tệp mới khi chưa tồn tại;
- `TRUNCATE_EXISTING` — xóa nội dung hiện tại của một tệp có sẵn trước khi ghi;
- `WRITE` — mở tệp để ghi.

Do đó:

~~~java
Files.writeString(path, "abcdef", StandardCharsets.UTF_8);
Files.writeString(path, "x", StandardCharsets.UTF_8);
// File bay gio chua dung "x" (1 byte ASCII).
~~~

Khi truyền `""`, tệp vẫn tồn tại nhưng có kích thước **0 byte**. Khi muốn nối thêm vào **tệp đã tồn tại**, dùng `APPEND` rõ ràng:

~~~java
Files.writeString(path, "y", StandardCharsets.UTF_8,
        StandardOpenOption.APPEND);
~~~

Khi ấy nội dung sau ví dụ là `"xy"`. Không dùng `APPEND` và `TRUNCATE_EXISTING` cùng nhau. `APPEND` không mặc nhiên bảo đảm nguyên tử khi nhiều luồng hoặc tiến trình khác nhau ghi đồng thời; bài kiểm thử này dùng luồng tuần tự.

### 1.3. Bốn trạng thái rất dễ nhầm

| Trạng thái | Quan sát trong test | Ý nghĩa |
| --- | --- | --- |
| **Không có tệp** | `Files.notExists(path) == true` khi fixture mới được tạo; `Files.readString` báo `IOException`. | Dữ liệu chưa được tạo, không phải chuỗi rỗng. |
| **Có tệp 0 byte** | `Files.exists(path)`; `Files.size(path) == 0`; đọc ra `""`. | Có tệp, nhưng không có ký tự. |
| **Có dấu cách/TAB** | Đọc ra `" \t"`; `isEmpty() == false`; `isBlank() == true`. | Có byte dù nội dung được coi là blank theo Java. |
| **Chỉ chứa xuống dòng** | `"\n"` → 1 byte `0A`; `"\r\n"` → 2 bytes `0D 0A`. | Tệp chứa ký tự thật; không đồng nhất với 0 byte. |

`String.isEmpty()`, `String.isBlank()` và `Files.size` trả lời **ba câu hỏi khác nhau**. Khi kiểm thử bảo toàn byte, không thay `String.equals()` bằng so sánh `trim()` hoặc `strip()` vì những phương thức đó có thể làm mất khoảng trắng và dấu phân tách dòng vốn cần được giữ nguyên.

## 2. Ma trận dữ liệu đầu vào cần kiểm thử

Một ma trận test hữu ích phải có **cả trường hợp thành công và thất bại**, với đầu vào cụ thể và kết quả có thể xác minh bằng máy.

### 2.1. Nội dung rỗng và ký tự điều khiển

| Fixture | Kỳ vọng sau round trip | Kỳ vọng byte UTF-8 |
| --- | --- | --- |
| `""` | Giữ nguyên chuỗi rỗng; tệp vẫn tồn tại. | 0 byte |
| `" "` | Giữ đúng một SPACE. | `20` |
| `"\t"` | Giữ TAB. | `09` |
| `"\n"` | Giữ LF và dòng trống. | `0A` |
| `"\r\n"` | Giữ CRLF, không đổi thành LF. | `0D 0A` |
| `"A\n"` | Phân biệt với `"A"`. | `41 0A` |
| `"A\r\nB\nC\r"` | Giữ hỗn hợp CRLF, LF, CR cuối. | Kiểm `Arrays.equals(expectedBytes, actualBytes)` |

**Bẫy thường gặp:** `Files.readAllLines` hoặc `String.lines` trả về các dòng logic nhưng không nhằm bảo toàn nguyên bản dấu xuống dòng. Đừng dùng các API tách dòng đó để xác nhận một phép round trip byte-exact.

### 2.2. Tiếng Việt và Unicode có dấu

| Fixture | Điều phải bảo toàn |
| --- | --- |
| `"Ti\u1EBFng Vi\u1EC7t"` | Chữ tiếng Việt có dấu, mã hóa UTF-8 đúng. |
| `"\u1EAF"` | Chữ **ắ** dạng tạo sẵn, một Unicode code point. |
| `"a\u0306\u0301"` | Dạng tách `a + dấu breve + dấu sắc`, ba code points. |
| `"\u0111"` | Chữ **đ**; không được tự đổi thành `d`. |
| `U+1F642` từ `Character.toChars(0x1F642)` | 2 đơn vị UTF-16 `char` nhưng 1 Unicode code point và 4 byte UTF-8. |
| `"\u00A0|\u200B|\u202F|\u3000"` | Non-breaking space, zero-width space, narrow NBSP và ideographic space. |

Hai chuỗi `"\u1EAF"` và `"a\u0306\u0301"` có thể nhìn gần giống nhau nhưng **không bằng nhau theo `String.equals`**. `Normalizer.normalize(text, Normalizer.Form.NFC)` có thể cho kết quả tương đương về chuẩn hóa canonical; tuy nhiên `Files.writeString`/`readString` **không tự chuẩn hóa** chuỗi. Phép thử bảo toàn dữ liệu phải giữ đúng dãy code points gốc, trừ khi quy tắc ứng dụng yêu cầu chuyển đổi.

Những ký tự nhìn như khoảng trắng cũng cần được kiểm bằng code points và bytes. Đặc biệt `U+00A0` là non-breaking space và `U+200B` là zero-width space; chúng không được `String.isBlank()` coi là Java whitespace, nhưng vẫn là dữ liệu thực sự cần bảo toàn khi ghi/đọc.

### 2.3. Trường hợp lỗi và byte đầu tệp

- **Missing file:** `Files.readString(path)` báo `IOException`, không trả `""`.
- **Malformed UTF-8:** dãy bytes `C3 28` không hợp lệ theo UTF-8; `Files.readString(path, UTF_8)` báo `IOException` thay vì tạo chuỗi hợp lệ.
- **UTF-8 BOM:** bytes `EF BB BF` ở đầu tệp giải mã thành ký tự `U+FEFF`. Khi dùng `Files.readString`, ký tự này vẫn hiện diện trong chuỗi đọc, nên cần xác định rõ quy tắc giữ/bỏ BOM.
- **Ghi đè:** ghi `"abcdef"` rồi `"x"` phải để lại đúng `"x"`, không sót bytes cũ.
- **Ghi chuỗi rỗng:** ghi `""` lên tệp có nội dung phải đưa file size về 0.
- **APPEND tường minh:** sau khi có `"A"`, nối `"B"` phải thành `"AB"`.

## 3. Bộ kiểm thử hoàn chỉnh chạy được bằng Java 11

Tạo tệp **TextFileRoundTripTest.java**. Mỗi case làm việc trong **một thư mục tạm riêng cho lần chạy**, không chạm tệp người dùng. Hàm `verify` ném `AssertionError` khi điều kiện sai; vì vậy test vẫn hoạt động khi không bật tùy chọn Java `-ea`. `finally` dọn tệp tạm ngay cả khi test thất bại.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.text.Normalizer;
import java.util.Arrays;

public class TextFileRoundTripTest {
    private static void verify(boolean valid, String message) {
        if (!valid) {
            throw new AssertionError(message);
        }
    }

    private static Path roundTrip(Path dir, String name, String expected)
            throws IOException {
        Path file = dir.resolve(name + ".txt");
        verify(Files.notExists(file), "file should not exist: " + name);

        Files.writeString(file, expected, StandardCharsets.UTF_8);
        verify(Files.isRegularFile(file), "file not created: " + name);

        String actual = Files.readString(file, StandardCharsets.UTF_8);
        verify(expected.equals(actual), "text changed: " + name);
        verify(Arrays.equals(expected.codePoints().toArray(),
                actual.codePoints().toArray()), "code points changed: " + name);

        byte[] bytes = expected.getBytes(StandardCharsets.UTF_8);
        verify(Arrays.equals(bytes, Files.readAllBytes(file)),
                "UTF-8 bytes changed: " + name);
        verify(Files.size(file) == bytes.length,
                "byte length changed: " + name);
        verify(expected.equals(Files.readString(file)),
                "default UTF-8 read changed: " + name);
        return file;
    }

    private static void testEmpty(Path dir) throws IOException {
        Path empty = roundTrip(dir, "empty", "");
        verify(Files.exists(empty), "empty file should exist");
        verify(Files.size(empty) == 0, "empty file must have 0 bytes");
        verify(Files.readString(empty).isEmpty(), "empty string expected");

        String blanks = Files.readString(roundTrip(dir, "spaces", " \t"));
        verify(!blanks.isEmpty(), "whitespace is not empty text");
        verify(blanks.isBlank(), "space and TAB are Java whitespace");

        Path line = roundTrip(dir, "newline-only", "\n");
        verify(Files.size(line) == 1, "LF must occupy one byte");

        Path nbsp = roundTrip(dir, "nbsp", "\u00A0");
        verify(Files.size(nbsp) == 2, "NBSP UTF-8 byte count");
        verify(!Files.readString(nbsp).isBlank(),
                "NBSP is not Java whitespace");
    }

    private static void testUnicode(Path dir) throws IOException {
        String vietnamese = "Ti\u1EBFng Vi\u1EC7t";
        String composed = "\u1EAF";
        String decomposed = "a\u0306\u0301";
        String emoji = new String(Character.toChars(0x1F642));
        String specialSpaces = "\u00A0|\u200B|\u202F|\u3000";
        String input = vietnamese + "|" + composed + "|" + decomposed
                + "|" + emoji + "|" + specialSpaces;

        String actual = Files.readString(roundTrip(dir, "unicode", input));
        verify(actual.contains(decomposed), "decomposed Unicode lost");
        verify(!composed.equals(decomposed), "distinct representations");
        verify(Normalizer.normalize(decomposed, Normalizer.Form.NFC)
                .equals(composed), "NFC canonical equivalence");
        verify(emoji.length() == 2, "UTF-16 surrogate pair");
        verify(emoji.codePointCount(0, emoji.length()) == 1,
                "one supplementary code point");
        verify(emoji.getBytes(StandardCharsets.UTF_8).length == 4,
                "four UTF-8 bytes for supplementary character");
        verify(actual.contains(emoji), "supplementary code point lost");
        verify(actual.contains("\u200B") && actual.contains("\u202F"),
                "special whitespace lost");
    }

    private static void testLineEndings(Path dir) throws IOException {
        String mixed = "A\r\nB\nC\r";
        Path file = roundTrip(dir, "mixed-newlines", mixed);
        verify(mixed.equals(Files.readString(file)),
                "CRLF, LF or trailing CR changed");

        Path noLf = roundTrip(dir, "no-final-newline", "A");
        Path withLf = roundTrip(dir, "with-final-newline", "A\n");
        verify(Files.size(noLf) == 1, "extra newline was added");
        verify(Files.size(withLf) == 2, "final newline was removed");
    }

    private static void testOverwrite(Path dir) throws IOException {
        Path file = dir.resolve("overwrite.txt");
        Files.writeString(file, "abcdef", StandardCharsets.UTF_8);
        Files.writeString(file, "x", StandardCharsets.UTF_8);
        verify(Files.readString(file).equals("x"),
                "default write must truncate");

        Files.writeString(file, "", StandardCharsets.UTF_8);
        verify(Files.exists(file), "file should still exist");
        verify(Files.size(file) == 0, "empty overwrite must truncate");

        Files.writeString(file, "A", StandardCharsets.UTF_8);
        Files.writeString(file, "B", StandardCharsets.UTF_8,
                StandardOpenOption.APPEND);
        verify(Files.readString(file).equals("AB"),
                "APPEND must preserve original content");

        Path defaultUtf8 = dir.resolve("default-charset.txt");
        String text = "Ti\u1EBFng Vi\u1EC7t";
        Files.writeString(defaultUtf8, text);
        verify(text.equals(Files.readString(defaultUtf8)),
                "default UTF-8 round trip");
        verify(Arrays.equals(text.getBytes(StandardCharsets.UTF_8),
                Files.readAllBytes(defaultUtf8)), "default UTF-8 bytes");
    }

    private static void testMissing(Path dir) throws IOException {
        Path missing = dir.resolve("missing.txt");
        verify(Files.notExists(missing), "missing fixture");
        boolean failed = false;
        try {
            Files.readString(missing, StandardCharsets.UTF_8);
        } catch (IOException expected) {
            failed = true;
        }
        verify(failed, "missing file must cause IOException");
    }

    private static void testInvalidUtf8(Path dir) throws IOException {
        Path invalid = dir.resolve("invalid-utf8.bin");
        Files.write(invalid, new byte[] { (byte) 0xC3, (byte) 0x28 });
        boolean failed = false;
        try {
            Files.readString(invalid, StandardCharsets.UTF_8);
        } catch (IOException expected) {
            failed = true;
        }
        verify(failed, "malformed UTF-8 must cause IOException");
    }

    private static void testBom(Path dir) throws IOException {
        Path file = dir.resolve("bom.txt");
        Files.write(file, new byte[] {
                (byte) 0xEF, (byte) 0xBB, (byte) 0xBF, (byte) 'A'
        });
        String actual = Files.readString(file, StandardCharsets.UTF_8);
        verify(actual.equals("\uFEFFA"), "UTF-8 BOM must be preserved");
    }

    private static void cleanup(Path dir) throws IOException {
        try (DirectoryStream<Path> files = Files.newDirectoryStream(dir)) {
            for (Path file : files) {
                Files.deleteIfExists(file);
            }
        }
        Files.deleteIfExists(dir);
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("text-roundtrip-");
        try {
            testEmpty(dir);
            System.out.println("PASS empty and whitespace");

            testUnicode(dir);
            System.out.println("PASS Unicode UTF-8");

            testLineEndings(dir);
            System.out.println("PASS exact line endings");

            testOverwrite(dir);
            System.out.println("PASS overwrite and append");

            testMissing(dir);
            System.out.println("PASS missing file");

            testInvalidUtf8(dir);
            System.out.println("PASS malformed UTF-8");

            testBom(dir);
            System.out.println("PASS UTF-8 BOM");

            System.out.println("ALL TEXT FILE TESTS PASSED");
        } finally {
            cleanup(dir);
        }
    }
}
~~~

### Biên dịch và chạy

Trong thư mục chứa tệp nguồn:

~~~bash
javac --release 11 -encoding UTF-8 TextFileRoundTripTest.java
java TextFileRoundTripTest
~~~

Kết quả chuẩn khi mọi điều kiện đúng:

~~~text
PASS empty and whitespace
PASS Unicode UTF-8
PASS exact line endings
PASS overwrite and append
PASS missing file
PASS malformed UTF-8
PASS UTF-8 BOM
ALL TEXT FILE TESTS PASSED
~~~

`--release 11` kiểm tra cú pháp và API Java công khai tương thích Java 11, ngay cả khi máy đang sử dụng trình biên dịch mới hơn. Nếu sản phẩm cần hỗ trợ runtime Java 11, CI nên có một lượt chạy trên **JDK/JRE 11 thực**; kiểm tra biên dịch không thay thế toàn bộ kiểm thử runtime.

Bộ kiểm thử cố ý dùng `\uXXXX` cho các ký tự dễ bị thay đổi khi sao chép và `Character.toChars` cho ký tự bổ sung. Chương trình không dựa vào font hiển thị, mặc định xuống dòng hay encoding của hệ điều hành. Tệp sinh ra nằm trong thư mục tạm riêng và được xóa sau chạy. Hàm `cleanup` chỉ phù hợp với thư mục được chính chương trình tạo và chỉ chứa tệp thường; không dùng nó để xóa thư mục người dùng.

## 4. Giải thích cách phát hiện lỗi thật

### 4.1. So sánh cả chuỗi và byte

Đoạn kiểm thử then chốt:

~~~java
String actual = Files.readString(file, StandardCharsets.UTF_8);
verify(expected.equals(actual), "text changed");

byte[] actualBytes = Files.readAllBytes(file);
byte[] expectedBytes = expected.getBytes(StandardCharsets.UTF_8);
verify(Arrays.equals(expectedBytes, actualBytes), "bytes changed");
~~~

**Vì sao cả hai?** Nếu hệ thống lỡ dùng cùng một charset sai ở hai phía, có thể vẫn round trip được về mặt String nhưng file không đáp ứng quy ước trao đổi UTF-8. So sánh byte tạo bằng `StandardCharsets.UTF_8` phát hiện lỗi giao thức đó. Kiểm tra `Files.size(file)` bổ sung xác minh tệp 0 byte hoặc không còn đuôi từ lần ghi trước.

Không nên chỉ đọc `Files.readString(file).isBlank()`: chuỗi `""`, `"\n"` và `" \t"` đều blank theo Java nhưng có kích thước file khác nhau. Đối với dữ liệu văn bản được yêu cầu giữ nguyên, dùng `equals` chính xác thay vì so sánh sau `trim/strip`.

### 4.2. Kiểm tra đúng Unicode

Chữ **ắ** có thể là một code point `U+1EAF` hoặc ba code points `U+0061 U+0306 U+0301`. Việc `Normalizer.normalize(decomposed, NFC).equals(composed)` là `true` chứng minh chúng tương đương canonical; **không** có nghĩa bộ đọc/ghi được phép tự chuẩn hóa khi hợp đồng yêu cầu byte-exact.

Một ký tự supplementary như `U+1F642` có `length() == 2` (hai UTF-16 code units) nhưng `codePointCount() == 1` và dài 4 byte khi mã hóa UTF-8. Kiểm thử chỉ dùng `length` có thể bỏ qua lỗi cắt giữa hai surrogate.

Các ký tự `U+00A0`, `U+200B`, `U+202F` và `U+3000` được cố định bằng escape để tránh việc copy/paste biến chúng thành SPACE thông thường. Chúng có thể khó nhìn thấy nhưng phải được ghi và đọc lại chính xác. Đừng tự loại chúng trong vòng đọc/ghi nếu nghiệp vụ chưa cho phép.

### 4.3. Giữ nguyên dấu xuống dòng

`Files.writeString` ghi lại toàn bộ ký tự trong `CharSequence` và `Files.readString` giữ các dấu dòng. Vì thế kiểm thử phải phân biệt `\r\n`, `\n` và `\r`, cũng như có hoặc không có newline cuối. Chỉ đếm số dòng hoặc gọi `String.lines()` không đủ để xác minh tính toàn vẹn của các separator.

Nếu nguồn dữ liệu yêu cầu chuẩn hóa tất cả dòng sang LF, đó là **bước biến đổi nghiệp vụ rõ ràng** và cần test riêng: so với đầu ra đã được xác định sau chuẩn hóa, không giả định Java sẽ tự làm.

### 4.4. Thử nhánh lỗi thay vì chỉ happy path

Tệp chưa tồn tại phải báo lỗi đọc. Đối với chương trình cần cấu hình mặc định khi file thiếu, logic ứng dụng có thể bắt ngoại lệ và chọn xử lý khác, nhưng **bài kiểm thử `Files.readString`** không được chấp nhận chuỗi rỗng thay cho file missing.

Dãy byte `C3 28` không phải UTF-8 hợp lệ. Javadoc `Files.readString(Path, Charset)` quy định `IOException` cho byte malformed/unmappable. Chương trình tạo dữ liệu lỗi qua `Files.write` để kiểm tra rằng quá trình đọc không âm thầm «sửa» lỗi rồi coi là thành công. Các cách chuyển bytes thành String khác có thể thay dữ liệu lỗi bằng `U+FFFD`; đừng coi các API đó tương đương về chính sách báo lỗi.

Khi có BOM UTF-8 `EF BB BF`, `Files.readString` giữ ký tự `U+FEFF` ở đầu kết quả trong ví dụ. Nếu hệ thống muốn loại BOM, hãy định nghĩa rõ chỉ loại ở **đầu tệp** và kiểm thử cả hai nhánh có/không có BOM. Đừng dựa vào `strip()` để xóa BOM một cách ngầm định.

## 5. Đưa bộ kiểm thử vào dự án

Khi dự án đã dùng **JUnit Jupiter**, có thể chuyển mỗi `test...` thành một test method và quản lý thư mục bằng `@TempDir`. Giữ nguyên các fixture có mã code point xác định và dùng assertion của framework. Nếu dùng test dạng data-driven, mỗi hàng trong ma trận đầu vào là một case với tên rõ ràng để khi lỗi xuất hiện biết ngay ký tự/charset nào bị sai.

Ở lớp ứng dụng thật, ngoài kiểm thử trực tiếp `Files` còn cần test **đường đi dữ liệu qua service**. Ví dụ service có thể gọi `strip` hoặc `Normalizer` trước khi ghi, hoặc xử lý file missing bằng giá trị mặc định; các quyết định ấy phải được đặc tả và kiểm thử rõ ràng, không gộp vào kết luận về hành vi mặc định của JDK.

Khuyến nghị cho CI:

- Chạy `javac --release 11` hoặc cấu hình tương đương trong Maven/Gradle, và chạy test trên một Java 11 runtime nếu Java 11 là baseline.
- Chỉ định UTF-8 cho source/test resources cũng như các lệnh I/O có hợp đồng UTF-8. Không phụ thuộc mã hóa mặc định của máy.
- Sử dụng file tạm riêng cho mỗi lượt; không viết đè fixture nằm trong repository hoặc dữ liệu người dùng.
- Test mọi biến thể của newline và Unicode bằng ký tự thật hoặc escape chính xác, không suy đoán theo cách font hiển thị.
- Với tệp lớn hoặc đòi hỏi durability khi mất điện, thiết kế **kiểm thử riêng** cho streaming, resource lifecycle, flush, ghi tạm/đổi tên và các failure modes; bài test `readString/writeString` chỉ chứng minh tính đúng của vòng đọc–ghi cho fixture nhỏ.

### Lỗi phổ biến

| Lỗi | Vì sao nguy hiểm | Cách phòng tránh |
| --- | --- | --- |
| Test chỉ kiểm `Files.exists`. | Tệp có thể có nội dung sai. | Kiểm String, bytes và size. |
| Test `isBlank` để xác định file 0 byte. | File chỉ chứa LF/SPACE cũng blank. | `Files.size == 0` và String `isEmpty`. |
| Ghi rồi đọc với hai charset không đúng nhưng giống nhau. | Có thể mất tương thích với hệ thống khác. | Đối chiếu bytes UTF-8 theo hợp đồng. |
| Bỏ qua NFC/NFD và emoji. | Có thể mất dấu, thay đổi chuỗi kết hợp hoặc cắt surrogate. | Fixture Unicode có code points cụ thể. |
| Chuyển newline bằng `trim/lines` trước khi so sánh. | Che giấu thay đổi CRLF hoặc newline cuối tệp. | So sánh exact String/bytes. |
| Không kiểm ghi lần hai. | Dễ bỏ sót nội dung cũ hoặc xóa dữ liệu ngoài ý muốn. | Test truncate và append tách biệt. |
| Không thử file missing/malformed bytes. | Chỉ có happy path; sai chính sách xử lý lỗi. | Negative tests kỳ vọng `IOException`. |
| Bỏ qua BOM. | Ký tự `U+FEFF` có thể ảnh hưởng parsing hoặc so sánh. | Xác định quy tắc BOM, test cả có/không. |
| Dùng file cố định trong cùng thư mục khi chạy song song. | Flaky test, nguy cơ ghi đè dữ liệu thật. | `Files.createTempDirectory` hoặc `@TempDir`. |
| Dùng Java `assert` mà không bật `-ea`. | Các phép kiểm tra có thể bị tắt. | `AssertionError` tường minh hoặc JUnit. |

## 6. Câu hỏi ôn tập

**1.** Ghi `Files.writeString(path, "")` rồi đọc có giống một tệp chưa từng tồn tại không?

**Đáp án:** Không. File tồn tại và có 0 byte; `readString` trả `""`. Đọc tệp chưa tồn tại báo `IOException`.

**2.** Ghi `"abcdef"` sau đó `"x"` bằng `Files.writeString` mặc định tạo nội dung nào?

**Đáp án:** `"x"`, vì tùy chọn mặc định có `TRUNCATE_EXISTING`.

**3.** Vì sao cả `expected.equals(actual)` lẫn so sánh byte UTF-8 đều có ích?

**Đáp án:** `equals` kiểm tính toàn vẹn của String; so byte với `expected.getBytes(StandardCharsets.UTF_8)` kiểm mã hóa đúng hợp đồng trao đổi và kích thước bytes.

**4.** `"a\u0306\u0301"` có tự thành `"\u1EAF"` sau `writeString/readString` không?

**Đáp án:** Không. API đọc/ghi không thực hiện Unicode normalization; nếu có thay đổi đó, phải do quy tắc ứng dụng xác định và test riêng.

**5.** Vì sao `"A\r\nB"` không được xem bằng `"A\nB"` trong bài test này?

**Đáp án:** Dấu phân cách dòng chứa số ký tự và bytes khác nhau; vòng đọc–ghi có mục tiêu bảo toàn nguyên bản.

**6.** Tệp chỉ có một byte `0A` có bị xem là rỗng không?

**Đáp án:** Không. Nó chứa một ký tự LF, đọc ra `"\n"`; `isBlank()` có thể là true nhưng `isEmpty()` là false.

**7.** Đọc file bytes `C3 28` như UTF-8 có nên âm thầm trả chuỗi có ký tự thay thế và báo test PASS không?

**Đáp án:** Không. Với `Files.readString(..., UTF_8)`, kỳ vọng `IOException` cho dữ liệu malformed; xử lý thay thế chỉ được dùng nếu ứng dụng xác định rõ chính sách khác.

**8.** Nếu file có BOM UTF-8, ký tự đầu tiên trong kết quả đọc của ví dụ là gì?

**Đáp án:** `U+FEFF`. Quy tắc có giữ hay loại BOM phải được quyết định và kiểm thử riêng.

## Checklist hoàn thành

- [ ] Đã test file missing, file 0 byte, file chỉ có whitespace và file chỉ chứa newline.
- [ ] Đã test String, code points, bytes UTF-8 và kích thước file.
- [ ] Đã test tiếng Việt tạo sẵn và dấu kết hợp, supplementary Unicode, non-breaking/zero-width spaces.
- [ ] Đã test CRLF/LF/CR, dấu xuống dòng cuối và không có dấu cuối.
- [ ] Đã test truncate mặc định, ghi chuỗi rỗng và `APPEND` tường minh.
- [ ] Đã test malformed UTF-8 và BOM theo hợp đồng đọc.
- [ ] Chạy được ví dụ với `javac --release 11`, các assertion thực sự hoạt động và file tạm được dọn.
- [ ] Phân biệt kiểm thử tính đúng của `Files` với kiểm thử các quy tắc riêng của hệ thống.

## Tài liệu chính thức

- [Java SE 11 — java.nio.file.Files: readString, writeString, readAllBytes, createTempDirectory](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html)
- [Java SE 11 — StandardOpenOption: CREATE, TRUNCATE_EXISTING, APPEND](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [Java SE 11 — StandardCharsets.UTF_8](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Java SE 11 — String: length, codePoints, isBlank](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html)
- [Java SE 11 — Normalizer: Unicode NFC/NFD](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/text/Normalizer.html)
- [Java SE 27 API Specification — đối chiếu API được duy trì ở JDK hiện hành (tháng 11/2026)](https://docs.oracle.com/en/java/javase/27/docs/api/)
