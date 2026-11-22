# Tiện ích một tệp xử lý văn bản Unicode (Java 11)

## 1. Mục tiêu và phạm vi

Xây dựng **một tệp nguồn Java duy nhất** tên `UnicodeTextTool.java`, chạy được với Java 11, để xử lý một tệp văn bản UTF-8 theo quy trình:

1. Nhận đường dẫn tệp đầu vào, đầu ra và tùy chọn `--strip-lines`.
2. Đọc **rõ ràng bằng UTF-8**, không phụ thuộc charset mặc định của hệ điều hành.
3. Chuẩn hóa Unicode sang **NFC** (Canonical Composition).
4. Nếu có `--strip-lines`, bỏ khoảng trắng ở **đầu/cuối từng dòng**, giữ nguyên kiểu ký tự xuống dòng.
5. Ghi kết quả thành tệp UTF-8 **mới**; không tự ghi đè tệp đã tồn tại.
6. Báo số Unicode code point, số đơn vị mã UTF-16 và số byte UTF-8 của **kết quả sau xử lý**.

Đây là tiện ích nhỏ cho tệp văn bản vừa với bộ nhớ máy. Nó không chuyển mã tất cả định dạng tài liệu, không tách từ tiếng Việt, không loại emoji và không thay thế quy trình kiểm tra an toàn nội dung.

## 2. Ba khái niệm dễ nhầm trong Unicode

- **Byte UTF-8:** đơn vị lưu trữ tệp; một code point thường dùng 1–4 byte. Luôn chỉ định `StandardCharsets.UTF_8` khi đọc/ghi.
- **UTF-16 code unit:** đơn vị mà `String.length()` đếm trong Java. Code point ngoài BMP (ví dụ `🙂`) cần **hai** code unit (surrogate pair).
- **Unicode code point:** giá trị ký tự Unicode; dùng `codePointCount(0, text.length())` hoặc `text.codePoints()` để đếm/duyệt. Một code point **chưa chắc** là một ký tự người dùng nhìn thấy.

Ví dụ `"🙂"` có 4 byte UTF-8, 2 code unit UTF-16, 1 code point. Chuỗi `"e\u0301"` gồm chữ `e` và dấu sắc kết hợp (2 code point) nhưng thường hiển thị thành một cụm chữ. Emoji cờ `🇻🇳` gồm hai regional-indicator code point mà người dùng thường thấy thành một cờ. Vì vậy, **code point count không phải số grapheme cluster** (cụm ký tự hiển thị); nếu cần xử lý vị trí con trỏ, emoji ZWJ hoặc phân đoạn chữ chuẩn Unicode mới nhất, phải dùng bộ tách grapheme được kiểm chứng và cập nhật theo phiên bản Unicode phù hợp.

Trong Java, tránh cắt chuỗi ở chỉ số `char` một cách tùy tiện: có thể chia đôi surrogate pair. Để duyệt từng code point:

```java
String s = "A🙂";
s.codePoints().forEach(cp ->
        System.out.printf("U+%04X%n", cp));
```

Kết quả:

```text
U+0041
U+1F642
```

`codePoints()` trả về các giá trị code point theo thứ tự; với dữ liệu `String` chứa surrogate không hợp lệ, cần có chính sách kiểm tra riêng khi nhập dữ liệu không tin cậy. Đọc tệp UTF-8 hợp lệ bằng `Files.readString` tránh việc tự tách byte thành `char`.

## 3. Vì sao chọn NFC?

Unicode cho phép nhiều cách biểu diễn tương đương về mặt *canonical*. Chẳng hạn, `"A\u0301"` (chữ A và dấu sắc kết hợp) được NFC chuyển thành `"Á"` (U+00C1). Chuẩn hóa giúp dữ liệu nhất quán hơn khi lưu, hiển thị và so sánh văn bản. Java hỗ trợ bằng `java.text.Normalizer`:

```java
String nfc = Normalizer.normalize(text, Normalizer.Form.NFC);
boolean alreadyNfc = Normalizer.isNormalized(text, Normalizer.Form.NFC);
```

- **NFC:** kết hợp canonical, được tiện ích này áp dụng theo mặc định; không có nghĩa là xóa dấu hay chuyển toàn bộ ký tự sang ASCII.
- **NFD:** phân rã canonical; hữu ích khi bài toán thật sự cần làm việc với dấu kết hợp.
- **NFKC/NFKD:** có cả biến đổi *compatibility*, có thể đổi hình thức và ý nghĩa biểu diễn (ví dụ `①` thành `1` dưới NFKC). Không tự ý sử dụng cho văn bản cần giữ nguyên đặc điểm gốc.

NFC **không** loại bỏ ký tự dễ nhầm hình dạng, không xác thực danh tính, không thay thế bước chống homograph/phishing và không tự giải quyết khác biệt chữ hoa/chữ thường. Việc đổi chữ hoa/thường trong ngôn ngữ tự nhiên còn phụ thuộc `Locale`; vì thế tiện ích không ép toàn bộ văn bản sang chữ thường.

## 4. Chương trình hoàn chỉnh: `UnicodeTextTool.java`

Đặt toàn bộ mã sau vào một tệp đúng tên `UnicodeTextTool.java`. Mã sử dụng các API còn được hỗ trợ trong Java hiện đại và chạy trên **JDK 11 trở lên**; không cần thư viện ngoài.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.text.Normalizer;

public final class UnicodeTextTool {
    private UnicodeTextTool() {
    }

    public static void main(String[] args) {
        if (args.length < 2 || args.length > 3
                || (args.length == 3 && !"--strip-lines".equals(args[2]))) {
            System.err.println(
                    "Usage: java UnicodeTextTool.java <input.txt> <output.txt> [--strip-lines]");
            System.exit(2);
            return;
        }

        Path input = Path.of(args[0]);
        Path output = Path.of(args[1]);

        try {
            // Đọc đúng UTF-8; dữ liệu byte sai mã hóa dẫn đến IOException.
            String text = Files.readString(input, StandardCharsets.UTF_8);

            // Chuẩn hóa canonical để các biểu diễn tương đương nhất quán hơn.
            String result = Normalizer.normalize(text, Normalizer.Form.NFC);

            if (args.length == 3) {
                result = stripLines(result);
            }

            // CREATE_NEW chống ghi đè: output phải chưa tồn tại.
            Files.writeString(
                    output,
                    result,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            System.out.println("Saved: " + output);
            System.out.println(
                    "Code points: " + result.codePointCount(0, result.length()));
            System.out.println("UTF-16 code units: " + result.length());
            System.out.println(
                    "UTF-8 bytes: " + result.getBytes(StandardCharsets.UTF_8).length);
        } catch (IOException e) {
            System.err.println("I/O error: " + e.getMessage());
            System.exit(1);
        }
    }

    // Chỉ cắt khoảng trắng tại biên mỗi dòng; giữ nguyên dấu xuống dòng.
    private static String stripLines(String text) {
        StringBuilder out = new StringBuilder(text.length());
        int from = 0;
        int i = 0;

        while (i < text.length()) {
            char c = text.charAt(i);

            // Các ký tự xuống dòng đều nằm trong BMP và là một char.
            boolean lineBreak = c == '\r' || c == '\n'
                    || c == '\u0085' || c == '\u2028' || c == '\u2029';

            if (!lineBreak) {
                i++;
                continue;
            }

            out.append(text.substring(from, i).strip());

            if (c == '\r' && i + 1 < text.length()
                    && text.charAt(i + 1) == '\n') {
                out.append("\r\n");
                i += 2;
            } else {
                out.append(c);
                i++;
            }
            from = i;
        }

        out.append(text.substring(from).strip());
        return out.toString();
    }
}
```

**Phân tích những điểm cần giữ đúng:**

1. `Path.of`, `Files.readString` và `Files.writeString` đều có trong Java 11. Nêu charset rõ ràng giúp kết quả trên Windows, Linux và macOS nhất quán.
2. `Normalizer.Form.NFC` xử lý quan hệ canonical trên chuỗi *trước* khi ghi. Không sử dụng `String.replace` để tự thay dấu tiếng Việt: rất dễ bỏ sót tổ hợp Unicode.
3. `String.strip()` (Java 11) dùng tiêu chí `Character.isWhitespace`. Nó xử lý nhiều khoảng trắng Unicode tốt hơn `trim()` kiểu cũ, **nhưng không bao gồm mọi ký tự khoảng trắng**: ví dụ NBSP U+00A0 thường được giữ lại. Đừng tự khẳng định `strip()` xóa mọi khoảng trắng Unicode.
4. Hàm `stripLines` xử lý CR (`\r`), LF (`\n`), cặp CRLF, NEL (U+0085), LINE SEPARATOR (U+2028), PARAGRAPH SEPARATOR (U+2029). Nó chỉ cắt khoảng trắng ở hai đầu nội dung từng dòng, **giữ nguyên chuỗi ký tự xuống dòng** và giữ các dòng trống. Chỉ bật tùy chọn khi việc mất khoảng trắng đầu/cuối dòng là chấp nhận được.
5. `StandardOpenOption.CREATE_NEW` khiến lệnh thất bại nếu tệp đích đã tồn tại, tránh ghi đè dữ liệu ngoài ý muốn. Thư mục cha của đầu ra phải tồn tại. Tệp nguồn không bị sửa.
6. Số đếm và dung lượng được đo trên **chuỗi đã biến đổi**. `getBytes(UTF_8).length` đo byte UTF-8 thực tế, không lấy `length()` để suy ra kích thước.
7. Lỗi đọc/ghi (không có tệp đầu vào, lỗi UTF-8, không có quyền, đích đã tồn tại…) được báo ra `stderr` với mã thoát `1`; lỗi cú pháp tham số có mã `2`. Không nuốt lỗi rồi in thông báo thành công.

**Giới hạn có chủ đích:** `Files.readString` giữ toàn bộ nội dung trong bộ nhớ. Với tệp rất lớn, cân nhắc xử lý streaming bằng `BufferedReader`/`BufferedWriter` có charset và thiết kế cẩn thận khi tổ hợp Unicode vượt ranh giới khối. Không cắt NFC theo các khối byte tùy ý vì dấu kết hợp có thể nằm ở khối kế tiếp. Không thêm logic chuyển mã hay xóa BOM ngầm: nếu có U+FEFF ở đầu, chương trình này coi nó là nội dung và giữ lại.

## 5. Chạy như một chương trình một tệp

Từ thư mục chứa `UnicodeTextTool.java` và `input.txt`:

```bash
# JDK 11+: chạy trực tiếp mã nguồn, không cần lệnh javac riêng
java UnicodeTextTool.java input.txt output.txt

# Hoặc biên dịch và chạy theo cách thông thường
javac UnicodeTextTool.java
java UnicodeTextTool input.txt output2.txt

# Chỉ khi muốn cắt khoảng trắng ở hai đầu mỗi dòng
java UnicodeTextTool.java input.txt output3.txt --strip-lines
```

Các tên `output.txt`, `output2.txt`, `output3.txt` là các **đường dẫn mới chưa tồn tại**. Khi chạy lại, đổi đường dẫn đầu ra hoặc chủ động xóa tệp kết quả cũ trước đó; tiện ích không ghi đè.

Để thử chính xác Unicode tổ hợp, tạo `input.txt` chứa **đúng** ba thành phần, không có dấu xuống dòng: chữ `A` (U+0041), dấu sắc kết hợp (U+0301), emoji `🙂` (U+1F642). Có thể tạo bằng JShell của JDK 11:

```java
java.nio.file.Files.writeString(
        java.nio.file.Path.of("input.txt"),
        "A\u0301\uD83D\uDE42",
        java.nio.charset.StandardCharsets.UTF_8);
```

Đoạn trên là **biểu thức dùng trong JShell**, không phải một chương trình Java độc lập. Mở bằng lệnh `jshell` rồi nhập biểu thức; hoặc tự tạo tệp UTF-8 có đúng nội dung đó bằng trình soạn thảo thích hợp.

Chạy:

```bash
java UnicodeTextTool.java input.txt output.txt
```

Với `output.txt` chưa tồn tại, stdout chính xác:

```text
Saved: output.txt
Code points: 2
UTF-16 code units: 3
UTF-8 bytes: 6
```

Vì NFC chuyển `A + U+0301` thành `Á` (mã UTF-8 2 byte), còn `🙂` có 4 byte UTF-8 và chiếm 2 đơn vị UTF-16. Nội dung tệp kết quả là `Á🙂`, không có newline.

## 6. Các trường hợp kiểm thử đáng làm

| Ca thử | Dữ liệu/flag | Điều cần kiểm chứng |
| --- | --- | --- |
| Dấu tiếng Việt dạng tổ hợp | `A\u0301` | NFC cho `Á`; biểu diễn canonical được hợp nhất. |
| Emoji ngoài BMP | `🙂` | 1 code point, 2 UTF-16 code units, 4 byte UTF-8. |
| Dòng Windows | `"  A  \r\n  B  \r\n"` và `--strip-lines` | Thu được `"A\r\nB\r\n"`, giữ CRLF và newline cuối. |
| Dòng Linux/macOS | `"  A \n  B  "` và `--strip-lines` | Thu được `"A\nB"`. |
| NBSP | `"\u00A0A\u00A0"` và `--strip-lines` | NBSP vẫn còn; `strip()` không có nghĩa xóa mọi `Space_Separator`. |
| Ký tự compatibility | `①` | NFC không biến nó thành `1`; đó là loại biến đổi của NFKC. |
| Tệp đích tồn tại | Chạy lại cùng `output.txt` | Báo lỗi I/O; không ghi đè tệp. |
| Byte không hợp lệ UTF-8 | Tệp chứa chuỗi byte sai UTF-8 | Đọc thất bại; không phát hành kết quả “thành công” với ký tự thay thế âm thầm. |
| Tệp rỗng | Input rỗng, output chưa có | Tạo output rỗng, ba số đếm bằng 0. |
| Nội dung có dấu cách có ý nghĩa | `"  code  "` | Không dùng `--strip-lines` nếu cần bảo toàn khoảng trắng gốc. |

Đối chiếu **byte** khi kiểm thử line ending hay NFC; nhìn bằng mắt không chứng minh hai chuỗi mã hóa giống nhau. Có thể dùng `Files.readAllBytes(Path.of("output.txt"))` và in hex, hoặc công cụ so sánh byte trên hệ điều hành.

## 7. Lỗi thường gặp và cách áp dụng đúng

- **Dùng `charAt(i)` để duyệt “từng ký tự”.** `char` là code unit UTF-16; với emoji ngoài BMP, hai phần surrogate không được xem như hai code point độc lập. Dùng `codePoints()` hoặc `codePointAt` kết hợp `Character.charCount` khi cần.
- **Cho rằng chuẩn hóa NFC loại dấu.** NFC giữ thông tin chính tả, chỉ thống nhất các biểu diễn canonical. Tìm kiếm không phân biệt dấu cần một chính sách và kiểm thử riêng.
- **Mặc định byte = ký tự = `length()`.** Ba khái niệm khác nhau. Một emoji hoặc ký tự có dấu kết hợp đủ làm sai kết quả thống kê.
- **Quên chọn UTF-8 khi đọc/ghi.** Dựa vào charset mặc định sẽ làm chương trình có hành vi khác nhau giữa các môi trường.
- **Ghép dòng bằng `String.lines()` + `Collectors.joining("\n")` nhưng nghĩ vẫn giữ nguyên định dạng.** Cách đó có thể thay CRLF thành LF và mất newline cuối. Bản này chủ động giữ ký tự xuống dòng gốc.
- **Tự động đổi hoa/thường hoặc NFKC cho mọi đầu vào.** Chuyển case phụ thuộc ngôn ngữ; compatibility normalization có thể thay đổi thông tin gốc. Chỉ thêm khi yêu cầu dữ liệu thực sự cho phép.
- **Dùng code point làm chỉ số caret/selection trong giao diện.** Một grapheme có thể gồm nhiều code point. Bài toán biên tập văn bản cần thuật toán grapheme cluster phù hợp.
- **Ghi đè đầu ra hoặc xử lý khối tùy ý khi file quá lớn.** Chọn chính sách file đích rõ ràng; Unicode normalization và grapheme không nhất thiết độc lập giữa hai khối.

**Hoàn thành bài thực hành khi:** chương trình chạy bằng JDK 11+, tạo đúng output UTF-8, chuẩn hóa NFC, giữ dấu xuống dòng khi `--strip-lines`, đếm đúng ví dụ `Á🙂`, báo lỗi rõ ràng và không ghi đè tệp cũ.