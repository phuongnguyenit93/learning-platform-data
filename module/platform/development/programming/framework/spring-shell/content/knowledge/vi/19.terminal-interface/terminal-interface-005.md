# Unicode, độ rộng ký tự và văn bản tiếng Việt

Một dòng chữ có thể trông rất ngắn nhưng chiếm nhiều đơn vị lưu trữ, hoặc ngược lại. Khi hiển thị tiếng Việt trong terminal, cần phân biệt byte UTF-8, đơn vị mã UTF-16 của Java, Unicode code point, grapheme cluster và ô hiển thị của terminal. Mỗi khái niệm trả lời một câu hỏi khác nhau.

Ví dụ, chữ **ệ** có thể được mã hóa bằng một code point dựng sẵn hoặc bằng chữ **e** kết hợp với các dấu phụ. Người dùng nhìn thấy một chữ trong cả hai trường hợp. Java có thể đếm chúng thành số đơn vị khác nhau, nhưng terminal thường hiển thị chúng trong cùng một ô. Nếu dùng **String.length()** để căn cột, cắt chuỗi hoặc đo chiều dài giao diện, bảng có thể lệch và dấu tiếng Việt có thể bị tách khỏi chữ cái.

Bài này giải thích cách Java và terminal biểu diễn Unicode, cách đo độ rộng hiển thị bằng JLine, cách xử lý NFC/NFD và những điểm cần kiểm tra khi phát triển Spring Shell có giao diện tiếng Việt.

## 1. Năm khái niệm cần phân biệt

| Khái niệm | Đơn vị được đếm | Câu hỏi nó trả lời |
|---|---|---|
| Byte UTF-8 | Byte trong chuỗi mã hóa | Dữ liệu chiếm bao nhiêu byte khi truyền hoặc lưu? |
| UTF-16 code unit | Đơn vị 16 bit trong Java String | String có bao nhiêu đơn vị chỉ số Java? |
| Unicode code point | Giá trị mã Unicode | Chuỗi có bao nhiêu điểm mã? |
| Grapheme cluster | Nhóm code point người dùng cảm nhận như một ký tự | Người dùng có thể di chuyển con trỏ hoặc xóa theo bao nhiêu đơn vị ký tự? |
| Terminal cell | Ô cột trong lưới terminal | Văn bản chiếm bao nhiêu cột khi hiển thị? |

Các số đo này không thể thay thế lẫn nhau. Byte count phục vụ I/O; UTF-16 code unit phục vụ chỉ số String; code point phục vụ xử lý Unicode; grapheme cluster phục vụ thao tác theo ký tự người dùng cảm nhận; terminal cell phục vụ căn lề và xuống dòng.

Ví dụ minh họa:

| Nội dung | UTF-16 code units | Code points | Grapheme clusters | Cột terminal thường gặp |
|---|---:|---:|---:|---:|
| A | 1 | 1 | 1 | 1 |
| ệ ở dạng NFC | 1 | 1 | 1 | 1 |
| e + dấu phụ ở dạng NFD | 3 | 3 | 1 | 1 |
| 中 | 1 | 1 | 1 | 2 |
| 😀 | 2 | 1 | 1 | Thường là 2 |
| 🇻🇳 | 4 | 2 | 1 | Thường là 2, tùy terminal |

Độ rộng terminal trong bảng là giá trị thường gặp, không phải cam kết giống nhau trên mọi terminal, font và thuật toán Unicode.

## 2. Java String đếm UTF-16 code unit

Java lưu nội dung **String** theo UTF-16. Phương thức **length()** trả về số code unit 16 bit, không phải số byte UTF-8, số code point hay số ký tự người dùng nhìn thấy.

Các ký tự Unicode trong vùng Basic Multilingual Plane thường dùng một code unit. Code point ngoài vùng này, ví dụ nhiều emoji, dùng một cặp surrogate gồm hai code unit.

~~~java
String vietnamese = "Tiếng Việt";
String emoji = "😀";

System.out.println(vietnamese.length()); // 10
System.out.println(emoji.length());      // 2
~~~

Nếu cần số code point, dùng **codePointCount()**:

~~~java
int codePoints = emoji.codePointCount(0, emoji.length());
System.out.println(codePoints); // 1
~~~

Nếu cần số byte khi mã hóa UTF-8, dùng charset rõ ràng:

~~~java
import java.nio.charset.StandardCharsets;

String text = "Tiếng Việt";
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;
~~~

Không dùng **length()** để tính dung lượng truyền tải, và không dùng số byte để căn cột terminal. Một ký tự có thể chiếm nhiều byte UTF-8 nhưng chỉ một ô hiển thị.

## 3. Code point không phải lúc nào cũng là một ký tự người dùng cảm nhận

Một ký tự có dấu có thể gồm một code point dựng sẵn hoặc một chữ cơ sở cộng với các combining mark. Unicode gọi đơn vị gần với điều người dùng cảm nhận là một ký tự là **grapheme cluster**.

Ví dụ, chữ **ệ**:

- Dạng NFC thường dùng một code point dựng sẵn.
- Dạng NFD được phân rã thành chữ e và các dấu kết hợp.
- Cả hai biểu diễn là tương đương chuẩn tắc và người đọc nhìn thấy cùng một chữ.

Java cung cấp **Normalizer** để chuyển đổi giữa các dạng chuẩn Unicode:

~~~java
import java.text.Normalizer;

String composed = "\u1EC7"; // ệ, dạng dựng sẵn
String decomposed =
        Normalizer.normalize(composed, Normalizer.Form.NFD);
String normalizedAgain =
        Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.equals(normalizedAgain)); // true
System.out.println(composed.length()); // 1
System.out.println(decomposed.length()); // 3
System.out.println(
        decomposed.codePointCount(0, decomposed.length())
); // 3
~~~

Hai chuỗi có thể hiển thị giống nhau nhưng **String.equals()** vẫn trả về false nếu biểu diễn Unicode khác nhau. Nếu nghiệp vụ coi các biểu diễn tương đương chuẩn tắc là cùng một nội dung, hãy chuẩn hóa về một dạng thống nhất trước khi so sánh hoặc lưu trữ.

### 3.1. Đếm grapheme cluster bằng BreakIterator

**BreakIterator.getCharacterInstance()** xác định ranh giới ký tự theo quy tắc phân đoạn văn bản của Java. Trên các JDK hiện đại, character boundary analysis tuân theo Extended Grapheme Cluster của Unicode.

~~~java
import java.text.BreakIterator;
import java.util.Locale;

static int graphemeCount(String text) {
    BreakIterator iterator =
            BreakIterator.getCharacterInstance(Locale.ROOT);
    iterator.setText(text);

    int count = 0;
    iterator.first();
    while (iterator.next() != BreakIterator.DONE) {
        count++;
    }
    return count;
}
~~~

Có thể dùng hàm trên để đếm ký tự người dùng cảm nhận:

~~~java
String composed = "\u1EC7";
String decomposed =
        Normalizer.normalize(composed, Normalizer.Form.NFD);

System.out.println(graphemeCount(composed));   // 1
System.out.println(graphemeCount(decomposed)); // 1
~~~

**BreakIterator** giải quyết ranh giới ký tự; nó không tính số cột terminal. Một grapheme cluster có thể chiếm một hoặc hai cột tùy nội dung và cách terminal hiển thị.

## 4. Vì sao văn bản tiếng Việt dễ làm lệch bảng terminal?

Tiếng Việt dùng chữ Latin kết hợp nhiều dấu thanh và dấu phụ. Các chữ như **ă**, **â**, **ê**, **ô**, **ơ**, **ư**, **đ** và các dạng có dấu thanh có thể xuất hiện dưới dạng code point dựng sẵn hoặc chuỗi chữ cơ sở cộng combining mark.

Trong terminal dùng font phù hợp, một chữ tiếng Việt thường chiếm một cột. Ở dạng phân rã, dấu kết hợp thường có độ rộng bằng 0 và được vẽ trên chữ cơ sở. Vì vậy, chuỗi NFD có thể có nhiều code point hơn nhưng không chiếm thêm cột.

Ví dụ bảng sau có thể bị lệch nếu tính chiều rộng bằng **String.length()**:

~~~text
Tên                 Trạng thái
Nguyễn Thị Ánh      Hoạt động
Lê                   Chờ xử lý
Trần Văn Bình        Hoạt động
~~~

Nếu dữ liệu chứa dạng NFC và NFD trộn lẫn, số code unit khác nhau dù nội dung nhìn tương đương. Dùng **String.length()** hoặc đếm code point để đệm khoảng trắng sẽ không phản ánh chính xác cột mà terminal đã sử dụng.

Các nguyên nhân khác cũng làm bảng lệch:

- Ký tự CJK thường chiếm hai cột.
- Emoji thường rộng hai cột, nhưng chuỗi emoji có ZWJ, cờ hoặc variation selector có thể gồm nhiều code point.
- Combining mark thường không chiếm cột riêng.
- Ký tự East Asian Ambiguous có thể rộng một hoặc hai cột tùy ngữ cảnh và terminal.
- Tab di chuyển con trỏ tới tab stop tiếp theo; độ rộng phụ thuộc vị trí hiện tại.
- ANSI escape sequence đổi màu hoặc kiểu chữ nhưng không chiếm cột hiển thị.

## 5. Độ rộng hiển thị và East Asian Width

Unicode Standard Annex #11 định nghĩa thuộc tính **East_Asian_Width** với các nhóm Wide, Fullwidth, Halfwidth, Narrow, Ambiguous và Neutral. Thuộc tính này hữu ích cho xử lý văn bản Đông Á, nhưng không phải thuật toán đo cột dùng trực tiếp cho mọi terminal hiện đại.

Quy tắc thường gặp trong terminal:

| Loại ký tự | Độ rộng thường gặp |
|---|---:|
| Chữ Latin, chữ tiếng Việt dựng sẵn | 1 cột |
| Combining mark | 0 cột |
| Chữ Hán, Hiragana, Katakana, Hangul fullwidth | 2 cột |
| Emoji presentation | Thường 2 cột |
| Ký tự điều khiển | Không hiển thị như ký tự thông thường |
| Ký tự ambiguous | 1 hoặc 2 cột tùy ngữ cảnh |

Một số dấu câu, ký hiệu toán học hoặc ký tự Hy Lạp có thể được xem là ambiguous. Khi không có thông tin ngữ cảnh, UAX #11 khuyến nghị cách giải quyết narrow; terminal vẫn có thể áp dụng quy tắc riêng.

Độ rộng thực tế còn phụ thuộc:

- Terminal emulator và cách triển khai wcwidth.
- Font đang dùng và font fallback.
- Locale hoặc cấu hình hiển thị Đông Á.
- Hỗ trợ grapheme cluster và emoji sequence.
- Phiên bản dữ liệu Unicode mà thư viện đo độ rộng sử dụng.

Vì vậy, không nên tự viết một bảng quy tắc đơn giản kiểu "ASCII là 1, ký tự khác là 2". Cách đó sẽ tính sai tiếng Việt có dấu, combining mark, ký hiệu và emoji.

## 6. Đo độ rộng bằng JLine

JLine cung cấp **WCWidth** để xác định độ rộng hiển thị của ký tự Unicode và **AttributedString.columnLength()** để đo cả chuỗi theo số cột terminal. AttributedString tính đến ký tự rộng, combining mark không có độ rộng và nội dung ẩn.

Trong Spring Shell 4, module core không còn phụ thuộc JLine. Nếu ứng dụng cần JLine console và các API đo độ rộng của JLine, hãy thêm dependency **spring-shell-jline** theo phiên bản Spring Shell đang dùng. Ứng dụng Spring Shell 4 vẫn có thể dùng console chuẩn của JDK mà không cần JLine.

Với Gradle, khai báo module JLine do Spring Shell cung cấp:

~~~gradle
dependencies {
    implementation("org.springframework.shell:spring-shell-jline")
}
~~~

Để tránh lệch phiên bản, dùng Spring Shell dependency management hoặc BOM của dự án thay vì tự chọn một phiên bản JLine khác với phiên bản mà Spring Shell đã kiểm thử.

Ví dụ đo độ rộng khi ứng dụng đã có một JLine Terminal:

~~~java
import org.jline.terminal.Terminal;
import org.jline.utils.AttributedString;

static int terminalColumns(String text, Terminal terminal) {
    return new AttributedString(text).columnLength(terminal);
}
~~~

Truyền terminal đang được ứng dụng quản lý vào hàm đo. Không tự tạo thêm một terminal khác bên trong Spring Shell chỉ để tính chiều rộng, vì terminal mới có thể đọc input hoặc ghi output trên một thiết bị khác.

JLine cũng có thể đo chuỗi không cần truyền terminal:

~~~java
int columns = new AttributedString("Nguyễn Thị Ánh").columnLength();
~~~

Khi truyền **Terminal**, JLine có thể sử dụng thông tin grapheme-cluster mode của terminal để đo các chuỗi nhiều code point như emoji ZWJ hoặc cờ theo cách con trỏ terminal di chuyển. Khi terminal không hỗ trợ chế độ đó, phép đo vẫn dựa trên các quy tắc độ rộng ký tự mà JLine triển khai.

### 6.1. Căn cột bằng display width

Nếu tự dựng bảng, hãy tính số cột cần đệm bằng độ rộng terminal:

~~~java
import org.jline.terminal.Terminal;
import org.jline.utils.AttributedString;

static String padRight(
        String value,
        int targetColumns,
        Terminal terminal) {

    int usedColumns =
            AttributedString.fromAnsi(value).columnLength(terminal);
    int spaces = Math.max(0, targetColumns - usedColumns);
    return value + " ".repeat(spaces);
}
~~~

Ví dụ dùng:

~~~java
String header = padRight("Tên", 24, terminal) + "Trạng thái";
String row = padRight("Nguyễn Thị Ánh", 24, terminal) + "Hoạt động";
~~~

Ví dụ giả định mỗi cell là một dòng văn bản đơn, không chứa tab hoặc ký tự xuống dòng. **fromAnsi()** phân tích ANSI style trước khi đo nên escape sequence không bị tính thành cột. Nếu có tab, cần mở rộng tab theo tab stop trước khi đo.

### 6.2. Cắt chuỗi theo cột hiển thị

Không cắt chuỗi bằng **substring(0, maxColumns)** khi mục tiêu là giới hạn số cột. Chỉ số substring là UTF-16 offset; nó có thể cắt đôi surrogate pair hoặc tách combining mark khỏi chữ cơ sở.

Một cách an toàn hơn là:

1. Dùng **BreakIterator** để tìm ranh giới grapheme cluster.
2. Dùng JLine đo độ rộng của từng cluster hoặc đoạn tích lũy.
3. Chỉ thêm cluster tiếp theo nếu tổng số cột vẫn nằm trong giới hạn.
4. Nếu cần, dành trước một cột cho dấu ba chấm.

Grapheme boundary ngăn việc tách dấu tiếng Việt khỏi chữ cái. JLine display width giúp giới hạn theo cột thực tế. Cả hai bước đều cần thiết; chỉ dùng code point count vẫn chưa đủ.

## 7. Chuẩn hóa Unicode cho văn bản tiếng Việt

Unicode cho phép một số chữ có dấu được biểu diễn theo dạng dựng sẵn hoặc dạng phân rã. Hai dạng này có thể tương đương chuẩn tắc nhưng có byte sequence và code point khác nhau.

**NFC** thường là lựa chọn phù hợp cho văn bản trao đổi và lưu trữ tổng quát. Java cung cấp:

~~~java
import java.text.Normalizer;

String canonicalText =
        Normalizer.normalize(input, Normalizer.Form.NFC);
~~~

Nên chuẩn hóa khi hợp đồng dữ liệu yêu cầu các biểu diễn tương đương có cùng dạng, ví dụ trước khi so sánh tên hiển thị hoặc tạo khóa tìm kiếm. Không cần chuẩn hóa lặp lại ở mọi lần render nếu dữ liệu đã có quy ước lưu trữ rõ ràng.

Không tự động xóa dấu tiếng Việt để sửa lỗi căn lề. **"Toàn"**, **"Toản"**, **"Toãn"** và **"Toạn"** là các nội dung khác nhau. Xóa dấu sẽ làm mất thông tin và có thể tạo ra tên trùng nhau.

Không dùng **NFKC** thay cho NFC một cách tùy tiện. NFKC còn gộp một số khác biệt tương thích và có thể làm thay đổi nội dung. Chỉ dùng khi yêu cầu nghiệp vụ cho phép gộp các dạng tương thích đó.

Nếu cần sắp xếp tên tiếng Việt theo quy tắc ngôn ngữ, **String.compareTo()** không thực hiện sắp xếp theo bảng chữ cái tiếng Việt. Dùng **Collator** với locale phù hợp:

~~~java
import java.text.Collator;
import java.util.Locale;

Collator vietnameseCollator =
        Collator.getInstance(Locale.forLanguageTag("vi-VN"));
names.sort(vietnameseCollator);
~~~

Collation là quy tắc so sánh và sắp xếp; normalization là quy tắc chuẩn hóa biểu diễn; display width là phép đo cột. Ba việc này cần được xử lý riêng.

## 8. Encoding UTF-8 và font terminal

Để hiển thị tiếng Việt đúng, toàn bộ đường đi của dữ liệu phải thống nhất encoding:

1. File nguồn và file cấu hình được lưu bằng UTF-8.
2. JVM đọc dữ liệu từ file, network hoặc database bằng charset phù hợp.
3. Terminal nhận output bằng encoding tương thích, thường là UTF-8.
4. Font terminal có glyph cho các ký tự tiếng Việt và dấu kết hợp.

Với ứng dụng tự tạo JLine Terminal, có thể chỉ định encoding:

~~~java
import org.jline.terminal.Terminal;
import org.jline.terminal.TerminalBuilder;

Terminal terminal = TerminalBuilder.builder()
        .encoding("UTF-8")
        .build();
~~~

Đây là ví dụ cho ứng dụng tự quản lý terminal. Trong Spring Shell, hãy cấu hình terminal mà runner đang dùng; không tạo terminal thứ hai chỉ để áp dụng encoding.

Encoding đúng không đảm bảo glyph sẽ hiển thị đẹp. Nếu terminal hiện ô vuông, dấu hỏi hoặc ký tự thay thế, hãy kiểm tra font và font fallback. Nếu chữ hiển thị thành chuỗi mojibake như **Tiáº¿ng Viá»‡t**, hãy kiểm tra encoding ở nơi đọc và nơi ghi dữ liệu thay vì xóa dấu.

Trên Windows, PowerShell, Windows Terminal, Command Prompt và IDE terminal có thể có cấu hình console khác nhau. Hãy thử trực tiếp trong môi trường mà người dùng sẽ chạy ứng dụng. Không giả định thiết lập locale của Linux có cùng ý nghĩa trên Windows.

## 9. Màu sắc ANSI và ký tự điều khiển

ANSI escape sequence có thể đổi màu, in đậm, gạch chân hoặc di chuyển con trỏ. Các byte điều khiển này không phải ký tự hiển thị, nhưng nếu đo chiều dài chuỗi thô, chúng vẫn làm tăng **String.length()**.

Khi dùng JLine, hãy tạo **AttributedString** và **AttributedStyle** để tách nội dung khỏi kiểu hiển thị. Nếu nhận một chuỗi đã có ANSI escape, dùng parser ANSI của JLine trước khi đo hoặc căn cột.

Không nên đưa raw escape sequence vào dữ liệu mà script hoặc consumer cần parse. Giữ style cho chế độ tương tác; với output máy đọc, hãy tắt màu và chỉ xuất nội dung theo schema.

Tab và control character cũng cần quy tắc riêng:

- Tab phụ thuộc vị trí con trỏ và tab stop, không có một độ rộng cố định.
- CR/LF kết thúc dòng, không phải một cột văn bản thông thường.
- Backspace, bell và escape có thể thay đổi hành vi terminal.
- Dữ liệu người dùng không tin cậy có thể chứa control character làm hỏng bố cục hoặc giả mạo thông báo.

Nếu hiển thị tên hoặc mô tả do người dùng cung cấp, hãy cân nhắc loại bỏ hoặc escape control character theo hợp đồng hiển thị. Không xóa combining mark vì chúng là thành phần hợp lệ của chữ tiếng Việt.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Bảng lệch khi tên có dấu | Dùng String.length() để căn cột | Đo display width bằng JLine hoặc thư viện wcwidth |
| Dấu tiếng Việt bị tách khỏi chữ | Cắt chuỗi giữa base character và combining mark | Cắt theo grapheme cluster |
| Emoji làm con trỏ lệch | Đếm code point như một ô | Dùng phép đo display width và grapheme mode khi terminal hỗ trợ |
| Ký tự CJK làm cột rộng hơn dự kiến | Coi mọi code point chiếm một cột | Xử lý ký tự wide thường là hai cột |
| Chữ tiếng Việt thành ký tự lạ | Encoding đọc và ghi không thống nhất | Dùng UTF-8 xuyên suốt và kiểm tra console |
| Chữ hiển thị thành ô vuông | Font thiếu glyph hoặc font fallback không phù hợp | Chọn font có hỗ trợ tiếng Việt và Unicode cần dùng |
| Hai chuỗi nhìn giống nhưng equals trả false | NFC và NFD khác nhau | Chuẩn hóa trước khi so sánh nếu hợp đồng yêu cầu |
| Sắp xếp tên sai thứ tự tiếng Việt | Dùng String.compareTo() | Dùng Collator với locale vi-VN |
| Căn lề sai khi có màu ANSI | Đo raw string chứa escape sequence | Dùng AttributedString hoặc loại bỏ ANSI trước khi đo |
| Cột thay đổi khi có tab | Giả định tab luôn có một cột | Mở rộng tab theo tab stop trước khi đo |
| Ký tự bị mất sau khi chuẩn hóa | Dùng NFKC hoặc xóa dấu không phù hợp | Chọn normalization theo yêu cầu dữ liệu và giữ nguyên dấu tiếng Việt |

## 11. Kiểm thử giao diện terminal với Unicode

Kiểm thử nên dùng chuỗi thực tế thay vì chỉ dùng ASCII:

| Nhóm dữ liệu | Ví dụ | Điều cần xác minh |
|---|---|---|
| Tiếng Việt NFC | Nguyễn Thị Ánh | Dấu được hiển thị và căn cột đúng |
| Tiếng Việt NFD | Chữ dựng lại bằng Normalizer.Form.NFD | Không tách dấu và có độ rộng hiển thị phù hợp |
| Ký tự ngoài BMP | 😀 | Không cắt đôi surrogate pair |
| Emoji sequence | 🇻🇳, 👨‍👩‍👧‍👦 | Con trỏ và căn cột phù hợp với khả năng terminal |
| CJK | 中, 日, 한 | Ký tự wide chiếm đúng số cột |
| Combining mark | e + dấu kết hợp | Mark không bị đếm như một cột độc lập |
| Ambiguous width | Ký hiệu toán học, dấu câu | Kiểm tra theo terminal và font mục tiêu |
| ANSI style | Dòng có màu và in đậm | Đo độ rộng không tính escape sequence |
| Tab và newline | Nội dung nhiều dòng | Wrap và căn lề theo tab stop và line break |
| Terminal resize | Thay đổi chiều rộng cửa sổ | Bảng được tính lại và không giữ độ rộng cũ |

Nên kiểm thử ít nhất trên:

- Terminal tương tác thực tế mà người dùng mục tiêu sử dụng.
- Windows Terminal hoặc terminal Windows đang được hỗ trợ.
- Terminal Linux/macOS nếu ứng dụng được phân phối đa nền tảng.
- Font chính và font fallback.
- JLine terminal có và không có grapheme-cluster mode nếu ứng dụng sử dụng JLine.

Với test tự động, kiểm tra riêng số code unit, code point, grapheme cluster và display width. Không dùng một assertion duy nhất dựa trên **String.length()** để kết luận giao diện đã căn đúng.

## 12. Checklist trước khi phát hành CLI tiếng Việt

1. Source, resource và file cấu hình được lưu bằng UTF-8.
2. Input và output dùng charset được xác định rõ.
3. Dữ liệu tiếng Việt NFC/NFD được xử lý theo một quy ước nhất quán.
4. Không dùng String.length() hoặc byte count để căn cột terminal.
5. Không cắt chuỗi ở giữa surrogate pair hoặc grapheme cluster.
6. Độ rộng CJK, combining mark và emoji được tính bằng thuật toán phù hợp.
7. Tab, ANSI escape và control character có quy tắc xử lý rõ.
8. Font terminal hỗ trợ các glyph cần thiết.
9. Sắp xếp văn bản tiếng Việt dùng locale phù hợp khi cần thứ tự ngôn ngữ.
10. Bảng và prompt được kiểm thử sau khi terminal resize.
11. JLine được khai báo rõ nếu ứng dụng Spring Shell 4 cần JLine APIs.
12. Các giới hạn của terminal mục tiêu được ghi nhận và kiểm thử.

Giao diện terminal tiếng Việt ổn định khi ứng dụng tôn trọng cả cách mã hóa Unicode lẫn cách terminal chiếm cột. Hãy dùng code point và grapheme cluster cho thao tác trên văn bản, dùng display width cho căn lề, và kiểm tra encoding cùng font trong terminal thực tế.

## Tài liệu tham khảo

- [Java SE — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html) — UTF-16 code unit, codePointAt, codePointCount và chỉ số String.
- [Java SE — BreakIterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/BreakIterator.html) — phân tích ranh giới ký tự, từ và câu.
- [Java SE — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html) — chuẩn hóa Unicode NFC, NFD, NFKC và NFKD.
- [Unicode Standard Annex #11 — East Asian Width](https://www.unicode.org/reports/tr11/) — thuộc tính độ rộng Unicode và lưu ý khi dùng trong môi trường terminal.
- [Unicode Standard Annex #29 — Text Segmentation](https://www.unicode.org/reports/tr29/) — grapheme cluster, word boundary và sentence boundary.
- [Unicode FAQ — Normalization](https://www.unicode.org/faq/normalization.html) — tương đương chuẩn tắc và lựa chọn NFC/NFD.
- [JLine — Unicode Support](https://jline.org/docs/advanced/unicode-support/) — encoding terminal, Unicode input/output và độ rộng ký tự.
- [JLine — Grapheme Cluster Mode](https://jline.org/docs/advanced/grapheme-cluster-mode/) — chế độ terminal 2027 và chuỗi emoji nhiều code point.
- [JLine API — WCWidth](https://javadoc.io/doc/org.jline/jline/3.30.17/org/jline/utils/WCWidth.html) — đo độ rộng ký tự Unicode trong terminal.
- [JLine API — AttributedCharSequence](https://javadoc.io/doc/org.jline/jline/3.30.17/org/jline/utils/AttributedCharSequence.html) — đo display width theo cột và hỗ trợ grapheme-cluster mode.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — JLine được tách khỏi core và có thể bổ sung qua module spring-shell-jline.
